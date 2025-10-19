#!/usr/bin/env python3
# epgtest.py
# Test EPG loader: supports .xml.gz, .xml, and "API" links that return XML content
# Reads channels from channels.txt and writes docs/epgtest.xml
# Improved error reporting and final summary with per-source errors.

import os
import gzip
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import traceback

CHANNEL_FILE = "channels.txt"
OUTPUT_FILE = "docs/epgtest.xml"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
DAYS = 2  # today + next day

def log(msg=""):
    print(msg, flush=True)

def safe_makedirs(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def download_content(url, timeout=30):
    """Download content bytes from url; return bytes or raise."""
    headers = {"User-Agent": "my-epg-test/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content, r.headers

def decode_content_bytes(content, url):
    """
    Try to decode content bytes to text:
    - If gzip header detected, decompress.
    - Else decode as utf-8 (ignore errors).
    """
    # detect gzip magic bytes
    if len(content) >= 2 and content[:2] == b'\x1f\x8b':
        try:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip (detected by magic)"
        except Exception as e:
            # try fallback
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    txt = f.read().decode("utf-8", errors="ignore")
                    return txt, "gzip (fallback)"
            except Exception:
                raise
    # not gzip by magic — decode as text
    try:
        txt = content.decode("utf-8", errors="ignore")
        return txt, "plain"
    except Exception as e:
        # final fallback: try gzip decompress anyway
        try:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip (fallback-decompress)"
        except Exception:
            raise

def parse_xml_text(xml_text, url):
    try:
        root = ET.fromstring(xml_text)
        return root
    except ET.ParseError as e:
        # rethrow with context
        raise ValueError(f"XML parse error for {url}: {e}")

def read_channels_file():
    if not os.path.exists(CHANNEL_FILE):
        raise FileNotFoundError(f"{CHANNEL_FILE} not found")
    channels = []
    with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            channels.append({
                "id": parts[0],
                "url": parts[1],
                "name": parts[2],
            })
    return channels

def parse_programme_time(start_str):
    # Expect format like: 20251010120000 +0700 or 20251010120000+0700 or at least YYYYMMDDhhmmss...
    if not start_str:
        return None
    s = start_str.strip()
    # take first 14 digits if present
    if len(s) >= 14 and s[:14].isdigit():
        try:
            dt = datetime.strptime(s[:14], "%Y%m%d%H%M%S")
            # localize to VN tz (we assume times are local or with explicit offset; this is simple)
            dt = TIMEZONE.localize(dt)
            return dt
        except Exception:
            pass
    # fallback: try to parse more flexibly
    try:
        # try parsing ignoring timezone
        from dateutil import parser as dateparser
        dt = dateparser.parse(s)
        if dt.tzinfo is None:
            dt = TIMEZONE.localize(dt)
        else:
            dt = dt.astimezone(TIMEZONE)
        return dt
    except Exception:
        return None

def main():
    log("=== BẮT ĐẦU SINH EPG TEST ===")
    try:
        channels = read_channels_file()
    except Exception as e:
        log(f"[!] Cannot read channels file: {e}")
        return

    log(f"=> Tổng kênh trong channels.txt: {len(channels)}")
    now = datetime.now(TIMEZONE)
    end_time = now + timedelta(days=DAYS)
    log(f"=> Window: {now} -> {end_time} ({TIMEZONE})\n")

    # Data structures
    all_channels_meta = {}   # channel_id -> {id,name,logo}
    all_programmes = []      # list of programme Element-like dicts
    source_results = {}      # url -> {"ok":bool, "error":None or msg, "channels":n, "programmes":n}

    # Pre-group channels by source URL so we only fetch each source once
    url_to_channel_ids = {}
    for ch in channels:
        url_to_channel_ids.setdefault(ch["url"], []).append(ch)

    for src_url, ch_list in url_to_channel_ids.items():
        log(f"=> Downloading: {src_url}")
        source_results[src_url] = {"ok": False, "error": None, "channels": 0, "programmes": 0}
        try:
            content_bytes, headers = download_content(src_url)
        except Exception as e:
            msg = f"Download error: {e}"
            source_results[src_url]["error"] = msg
            log(f"[!] {msg}")
            continue

        # decode bytes -> text
        try:
            xml_text, how = decode_content_bytes(content_bytes, src_url)
            log(f"   -> decoded ({how}), length={len(xml_text)}")
        except Exception as e:
            msg = f"Decode error: {e}"
            source_results[src_url]["error"] = msg
            log(f"[!] {msg}")
            continue

        # parse xml
        try:
            root = parse_xml_text(xml_text, src_url)
            if root is None or root.tag is None:
                raise ValueError("Empty or invalid root")
            log(f"   -> Parsed root tag: {root.tag}")
        except Exception as e:
            msg = f"Parse error: {e}"
            source_results[src_url]["error"] = msg
            log(f"[!] {msg}")
            continue

        # mark OK
        source_results[src_url]["ok"] = True

        # Gather channel metadata present in source
        channels_in_source = {}
        for ch_node in root.findall("channel"):
            cid = ch_node.attrib.get("id", "").strip()
            if not cid:
                continue
            # display-name pick first available
            dname = None
            dn = ch_node.find("display-name")
            if dn is not None and dn.text:
                dname = dn.text.strip()
            icon = None
            ic = ch_node.find("icon")
            if ic is not None and "src" in ic.attrib:
                icon = ic.attrib["src"]
            channels_in_source[cid.lower()] = {"id": cid, "name": dname, "icon": icon}

        # Count channels seen
        source_results[src_url]["channels"] = len(channels_in_source)

        # For each channel we requested from this source, find programmes
        progs_found_total = 0
        for requested in ch_list:
            req_id = requested["id"]
            req_id_l = req_id.lower()

            # metadata fallback: if source contains metadata for this id, use it; otherwise use requested name
            meta = channels_in_source.get(req_id_l)
            if meta:
                all_channels_meta[requested["id"]] = {
                    "id": requested["id"],
                    "name": meta.get("name") or requested["name"],
                    "logo": meta.get("icon")
                }
            else:
                # fallback: add minimal meta using channels.txt name
                all_channels_meta[requested["id"]] = {
                    "id": requested["id"],
                    "name": requested["name"],
                    "logo": None
                }
                log(f"   - Warning: channel metadata for '{requested['id']}' not found in source; using fallback display name")

            # find programmes in root where programme@channel matches (case-insensitive)
            found = 0
            for p in root.findall("programme"):
                ch_attr = p.attrib.get("channel", "")
                if ch_attr.lower() != req_id_l:
                    continue
                start_str = p.attrib.get("start", "")
                # parse start time
                dt = None
                if start_str:
                    # try 14-digit parse first
                    try:
                        dt = datetime.strptime(start_str[:14], "%Y%m%d%H%M%S")
                        dt = TIMEZONE.localize(dt)
                    except Exception:
                        # try dateutil if available
                        try:
                            from dateutil import parser as dateparser
                            dt = dateparser.parse(start_str)
                            if dt.tzinfo is None:
                                dt = TIMEZONE.localize(dt)
                            else:
                                dt = dt.astimezone(TIMEZONE)
                        except Exception:
                            dt = None

                # filter by window
                if dt is None:
                    # if cannot parse time, skip programme (but count as skipped)
                    continue
                if not (now <= dt <= end_time):
                    continue

                # extract title/desc safely
                title = ""
                desc = ""
                tnode = p.find("title")
                if tnode is not None and tnode.text:
                    title = tnode.text.strip()
                dnode = p.find("desc")
                if dnode is not None and dnode.text:
                    desc = dnode.text.strip()

                # store programme as a dict (we will serialize later)
                all_programmes.append({
                    "start": p.attrib.get("start", ""),
                    "stop": p.attrib.get("stop", ""),
                    "channel": requested["id"],
                    "title": title,
                    "desc": desc
                })
                found += 1

            progs_found_total += found
            log(f"   - {requested['id']} -> matched {found} programmes")

        source_results[src_url]["programmes"] = progs_found_total
        log(f"   -> total programmes matched from this source: {progs_found_total}\n")

    # End for each source

    # Write output XML
    safe_makedirs(OUTPUT_FILE)
    try:
        root_out = ET.Element("tv", attrib={"generator-info-name": "my-epg test"})
        # write channels
        for cid, meta in all_channels_meta.items():
            ch_el = ET.SubElement(root_out, "channel", id=meta["id"])
            dn = ET.SubElement(ch_el, "display-name")
            dn.text = meta.get("name") or meta["id"]
            if meta.get("logo"):
                ET.SubElement(ch_el, "icon", src=meta["logo"])

        # write programmes
        for p in all_programmes:
            p_el = ET.SubElement(root_out, "programme", start=p["start"], stop=p["stop"], channel=p["channel"])
            t_el = ET.SubElement(p_el, "title")
            t_el.text = p["title"]
            if p["desc"]:
                d_el = ET.SubElement(p_el, "desc")
                d_el.text = p["desc"]

        ET.ElementTree(root_out).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
        log(f"-> written {OUTPUT_FILE} ({len(all_programmes)} programmes, {len(all_channels_meta)} channels)\n")
    except Exception as e:
        log(f"[!] Error writing output file: {e}")
        traceback.print_exc()
        return

    # Print SUMMARY
    log("=== SUMMARY ===")
    log(f"Total channels requested: {len(channels)}")
    # per channel counts (from all_programmes)
    per_channel_counts = {ch["id"]: 0 for ch in channels}
    for p in all_programmes:
        per_channel_counts.setdefault(p["channel"], 0)
        per_channel_counts[p["channel"]] += 1

    for ch in channels:
        cnt = per_channel_counts.get(ch["id"], 0)
        log(f"- {ch['id']} ({ch['name']}): {cnt}")

    total_programmes = len(all_programmes)
    log(f"Total programmes: {total_programmes}\n")

    # per-source summary (success / error)
    log("=== SOURCE SUMMARY ===")
    ok_count = 0
    fail_count = 0
    for src, info in source_results.items():
        if info["ok"]:
            ok_count += 1
            log(f"- OK: {src} -> channels_in_source={info['channels']} programmes_matched={info['programmes']}")
        else:
            fail_count += 1
            log(f"- FAIL: {src} -> error: {info['error']}")
    log(f"Sources OK: {ok_count} | Failed: {fail_count}")

    log("\n=== HOÀN TẤT ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("=== UNHANDLED EXCEPTION ===")
        log(str(e))
        traceback.print_exc()
        raise
            
