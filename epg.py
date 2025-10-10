#!/usr/bin/env python3
"""
epg.py
- Read channels.txt (id | source_url | display-name)
- Download every distinct source_url (supports .xml and .xml.gz)
- Parse programmes from all sources, handle timezone offsets correctly
- Produce docs/epg.xml (XMLTV) containing channels + programmes for 2 days (today + next day)
- Log per-source and per-channel counts
Requires: requests, python-dateutil, pytz
"""
import os, io, gzip, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import pytz
from dateutil import parser as dparser

# CONFIG
CHANNELS_FILE = "channels.txt"
OUTPUT_FILE = "docs/epg.xml"
TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def log(*args, **kwargs):
    print(*args, **kwargs, flush=True)

def read_channels(path=CHANNELS_FILE):
    chans = []
    if not os.path.exists(path):
        log(f"[!] channels.txt not found: {path}")
        return chans
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [p.strip() for p in ln.split("|")]
            if len(parts) < 3:
                continue
            chans.append({
                "id": parts[0],
                "url": parts[1],
                "name": parts[2]
            })
    return chans

def fetch_source(url):
    log(f"=> Downloading: {url}")
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        content = r.content
        # if gz (by header or url)
        if url.endswith(".gz") or (r.headers.get("content-encoding","").lower() == "gzip"):
            try:
                data = gzip.decompress(content)
            except Exception as e:
                # try via fileobj
                data = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
        else:
            data = content
        return data
    except Exception as e:
        log(f"[!] Error downloading {url}: {e}")
        return None

def parse_xml_bytes(data):
    try:
        root = ET.fromstring(data)
        return root
    except Exception as e:
        log(f"[!] Error parsing XML: {e}")
        return None

def parse_dt_with_offset(s):
    """Parse start/stop like '20251008060000 +0000' or ISO text.
       Returns timezone-aware datetime in its original tz, or None."""
    if not s:
        return None
    s = s.strip()
    # try full ISO or strings with offset using dateutil
    try:
        dt = dparser.parse(s)
        if dt.tzinfo is None:
            # assume it's local VN if no tz info
            return TZ.localize(dt)
        return dt
    except Exception:
        # fallback: try to parse leading 14 digits as local (assume VN)
        try:
            lead = s[:14]
            dt = datetime.strptime(lead, "%Y%m%d%H%M%S")
            return TZ.localize(dt)
        except Exception:
            return None

def to_vn(dt):
    """Return datetime converted to VN tz (timezone-aware)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = TZ.localize(dt)
        return dt
    return dt.astimezone(TZ)

def format_output_time(dt):
    """Return 'YYYYmmddHHMMSS +0700' with VN offset"""
    dt_vn = to_vn(dt)
    return dt_vn.strftime("%Y%m%d%H%M%S +0700")

def collect_all_from_sources(source_urls):
    """Download each source once, parse xml, return list of roots"""
    roots = []
    for url in source_urls:
        data = fetch_source(url)
        if not data:
            log(f"   [!] No data from {url}")
            continue
        root = parse_xml_bytes(data)
        if root is None:
            log(f"   [!] Parse failed for {url}")
            continue
        roots.append((url, root))
        log(f"   -> Parsed root tag: {root.tag}")
    return roots

def build_program_index(roots):
    """Return dict channel_id -> list(program_element, src_url)"""
    idx = {}
    for src_url, root in roots:
        for p in root.findall("programme"):
            ch = p.attrib.get("channel","")
            if not ch:
                continue
            idx.setdefault(ch, []).append((p, src_url))
    return idx

def build_channelinfo_from_sources(roots):
    """Collect channel elements from sources by id (prefer first occurrence)"""
    info = {}
    for src_url, root in roots:
        for ch in root.findall("channel"):
            cid = ch.get("id")
            if not cid:
                continue
            if cid in info:
                continue
            # store element for reproduction (but copy text only)
            dn = ch.find("display-name")
            icon = ch.find("icon")
            info[cid] = {
                "display-name": dn.text.strip() if dn is not None and dn.text else cid,
                "icon": icon.get("src") if icon is not None and icon.get("src") else None
            }
    return info

def main():
    log("=== BẮT ĐẦU SINH EPG (multi-source, 2 ngày) ===")
    channels = read_channels()
    if not channels:
        log("[!] No channels in channels.txt")
        return

    # unique sources to download
    source_urls = []
    for ch in channels:
        url = ch["url"]
        if url not in source_urls:
            source_urls.append(url)

    # fetch all sources
    roots = collect_all_from_sources(source_urls)
    if not roots:
        log("[!] No sources parsed successfully. Exiting.")
        return

    # build indexes
    prog_index = build_program_index(roots)
    channel_info = build_channelinfo_from_sources(roots)

    # time window: now .. now+2days
    now = datetime.now(TZ)
    end_time = now + timedelta(days=2)
    log(f"=> Window (VN): {now.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # build output root
    out_root = ET.Element("tv", {
        "generator-info-name": "my-epg",
        "source-info-name": "multi",
        "source-info-url": ",".join(source_urls)
    })

    total = 0
    stats = []

    # process each channel defined in channels.txt (preserve order)
    for ch in channels:
        cid = ch["id"]
        cname = ch["name"]
        # add channel element (use display-name from channels.txt; fallback to source info)
        ch_el = ET.SubElement(out_root, "channel", id=cid)
        dn = ET.SubElement(ch_el, "display-name", {"lang":"vi"})
        dn.text = cname if cname else (channel_info.get(cid,{}).get("display-name", cid))
        # add icon if available from source info (optional)
        icon_url = channel_info.get(cid,{}).get("icon")
        if icon_url:
            ET.SubElement(ch_el, "icon", {"src": icon_url})

        matched = 0
        items = prog_index.get(cid, [])
        # parse and filter by time window
        for p_elem, src in items:
            s_attr = p_elem.attrib.get("start","")
            e_attr = p_elem.attrib.get("stop","")
            s_dt = parse_dt_with_offset(s_attr)
            if s_dt is None:
                # skip unparseable times
                continue
            s_dt_vn = to_vn(s_dt)
            if not (now <= s_dt_vn < end_time):
                continue

            # stop time: try parse stop, else estimate = start + 30m
            stop_dt = parse_dt_with_offset(e_attr)
            if stop_dt is None or to_vn(stop_dt) <= s_dt_vn:
                stop_dt = s_dt + timedelta(minutes=30)

            # build programme element standardized
            prog = ET.SubElement(out_root, "programme", {
                "start": format_output_time(s_dt),
                "stop": format_output_time(stop_dt),
                "channel": cid
            })
            # copy title/desc/category etc
            title = p_elem.find("title")
            if title is not None and title.text and title.text.strip():
                t = ET.SubElement(prog, "title", {"lang":"vi"})
                t.text = title.text.strip()
            else:
                t = ET.SubElement(prog, "title", {"lang":"vi"})
                t.text = "Chưa có tiêu đề"

            desc = p_elem.find("desc")
            if desc is not None and desc.text and desc.text.strip():
                d = ET.SubElement(prog, "desc", {"lang":"vi"})
                d.text = desc.text.strip()

            # copy other children except title/desc
            for child in p_elem:
                if child.tag in ("title","desc"):
                    continue
                newc = ET.SubElement(prog, child.tag, child.attrib)
                if child.text:
                    newc.text = child.text

            matched += 1
            total += 1

        stats.append((cid, cname, matched))
        log(f"   - matched {matched} programmes for {cid} ({cname})")

    # pretty indent
    try:
        ET.indent(out_root, space="  ")
    except Exception:
        pass

    # write output
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    ET.ElementTree(out_root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    log(f"-> written {OUTPUT_FILE} ({total} programmes)")

    # summary
    log("\n=== SUMMARY ===")
    log(f"Total channels requested: {len(channels)}")
    for cid, cname, cnt in stats:
        log(f"- {cid} ({cname}): {cnt}")
    log(f"Total programmes: {total}")
    log("=== DONE ===")

if __name__ == "__main__":
    main()
