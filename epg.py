#!/usr/bin/env python3
# epg.py - build XMLTV (2 days) from lichphatsong.site epg.xml.gz filtered by channels.txt

import requests, gzip, io, re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import sys
import os

EPG_GZ_URL = "https://lichphatsong.site/schedule/epg.xml.gz"
CHANNELS_FILE = "channels.txt"
OUTPUT_FILE = "docs/epg.xml"
TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def log(msg=""):
    print(msg, flush=True)

def load_channels(path=CHANNELS_FILE):
    if not os.path.exists(path):
        log(f"[!] channels.txt not found at {path}")
        return []
    chans = []
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

def fetch_and_parse_gz(url=EPG_GZ_URL):
    try:
        log(f"=> Downloading {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = gzip.decompress(io.BytesIO(r.content).read())
        root = ET.fromstring(data)
        log(f"=> Parsed XML, root tag: {root.tag}")
        return root
    except Exception as e:
        log(f"[!] Error fetching/parsing gz: {e}")
        return None

# parse time like "20251008060000 +0700" or at least starting digits YYYYMMDDhhmmss
TIME_RE = re.compile(r"^(\d{14})")

def parse_start_dt(start_str):
    if not start_str:
        return None
    m = TIME_RE.match(start_str.strip())
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
        # localize to Vietnam tz
        return TZ.localize(dt)
    except Exception:
        return None

def format_epg_time(dt):
    # dt must be timezone-aware
    return dt.strftime("%Y%m%d%H%M%S +0700")

def clone_element_text(src_elem, dst_parent):
    # copy child tags (title, desc, category, etc.) preserving text and attributes (lang)
    for child in src_elem:
        new = ET.SubElement(dst_parent, child.tag, child.attrib)
        if child.text:
            new.text = child.text

def build_epg(root_xml, channels):
    now = datetime.now(TZ)
    end_time = now + timedelta(days=2)  # now .. next day (2 days total)
    log(f"=> Window: {now.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')} ({TZ})")

    out_root = ET.Element("tv", {
        "generator-info-name": "my-epg",
        "source-info-name": "lichphatsong.site",
        "source-info-url": "https://lichphatsong.site"
    })

    total_prog = 0
    per_channel_stats = []

    # Prebuild index of programmes by channel to speed filtering
    progs_by_channel = {}
    for p in root_xml.findall("programme"):
        ch = p.attrib.get("channel","")
        if not ch:
            continue
        progs_by_channel.setdefault(ch, []).append(p)

    log(f"=> Total channels in source: {len(progs_by_channel)}")

    for ch in channels:
        ch_id = ch["id"]
        ch_name = ch["name"]
        log(f"=> Processing channel: {ch_id} ({ch_name})")

        # add channel element
        ch_el = ET.SubElement(out_root, "channel", id=ch_id)
        dn = ET.SubElement(ch_el, "display-name", {"lang":"vi"})
        dn.text = ch_name

        matched = 0
        items = progs_by_channel.get(ch_id, [])
        for p in items:
            start_attr = p.attrib.get("start","")
            start_dt = parse_start_dt(start_attr)
            if not start_dt:
                continue
            if not (now <= start_dt < end_time):
                continue

            # determine stop: use existing stop if parseable, else +30min
            stop_attr = p.attrib.get("stop","")
            stop_dt = parse_start_dt(stop_attr)
            if not stop_dt or stop_dt <= start_dt:
                stop_dt = start_dt + timedelta(minutes=30)

            # create programme element with standardized times
            prog_el = ET.SubElement(out_root, "programme", {
                "start": format_epg_time(start_dt),
                "stop": format_epg_time(stop_dt),
                "channel": ch_id
            })
            # copy children like title, desc, category, etc.
            # prefer to add title with lang="vi" if possible
            title = p.find("title")
            if title is not None and (title.text and title.text.strip()):
                t_el = ET.SubElement(prog_el, "title", {"lang":"vi"})
                t_el.text = title.text.strip()
            else:
                t_el = ET.SubElement(prog_el, "title", {"lang":"vi"})
                t_el.text = "Chưa có tiêu đề"

            # copy desc if present
            desc = p.find("desc")
            if desc is not None and desc.text and desc.text.strip():
                d_el = ET.SubElement(prog_el, "desc", {"lang":"vi"})
                d_el.text = desc.text.strip()

            # copy other children (category, episode-num...) except title/desc
            for child in p:
                tag = child.tag
                if tag in ("title","desc"):
                    continue
                # copy element with attributes and text
                newc = ET.SubElement(prog_el, tag, child.attrib)
                if child.text:
                    newc.text = child.text

            matched += 1
            total_prog += 1

        per_channel_stats.append((ch_id, ch_name, matched))
        log(f"   - matched {matched} programmes for {ch_id}")

    # pretty indent (Python 3.9+)
    try:
        ET.indent(out_root, space="  ")
    except Exception:
        pass

    return out_root, per_channel_stats, total_prog

def write_output(root_elem, path=OUTPUT_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tree = ET.ElementTree(root_elem)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    log(f"-> Wrote {path}")

def main():
    channels = load_channels()
    if not channels:
        log("[!] No channels defined in channels.txt")
        sys.exit(1)

    src_root = fetch_and_parse_gz()
    if src_root is None:
        sys.exit(1)

    out_root, stats, total = build_epg(src_root, channels)

    # Logging summary
    log("\n=== SUMMARY ===")
    log(f"Total channels processed: {len(channels)}")
    for cid, cname, cnt in stats:
        log(f"- {cid} ({cname}): {cnt} programmes")
    log(f"Total programmes: {total}")
    log("==============\n")

    write_output(out_root)
    log("=== DONE ===")

if __name__ == "__main__":
    main()
    
