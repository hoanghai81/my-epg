#!/usr/bin/env python3
# epgtest1.py
# Extended: auto-translate non-Vietnamese/English titles & descriptions before export.

import os
import gzip
import io
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import traceback
from langdetect import detect, DetectorFactory
from deep_translator import GoogleTranslator

DetectorFactory.seed = 0  # for consistent language detection

CHANNEL_FILE = "channels.txt"
OUTPUT_FILE = "docs/epgtest1.xml"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
DAYS = 1  # today + next day

def log(msg=""):
    print(msg, flush=True)

def safe_makedirs(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def download_content(url, timeout=30):
    headers = {"User-Agent": "my-epg-test/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content, r.headers

def decode_content_bytes(content, url):
    if len(content) >= 2 and content[:2] == b'\x1f\x8b':
        try:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip (magic)"
        except Exception:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                txt = f.read().decode("utf-8", errors="ignore")
                return txt, "gzip (fallback)"
    try:
        txt = content.decode("utf-8", errors="ignore")
        return txt, "plain"
    except Exception:
        txt = gzip.decompress(content).decode("utf-8", errors="ignore")
        return txt, "gzip (force)"

def parse_xml_text(xml_text, url):
    try:
        root = ET.fromstring(xml_text)
        return root
    except ET.ParseError as e:
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

def translate_if_needed(text):
    """Detect language and translate to English if not Vietnamese or English."""
    if not text.strip():
        return text, None
    try:
        lang = detect(text)
    except Exception:
        return text, None
    if lang in ("vi", "en"):
        return text, lang
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
        return translated, lang
    except Exception:
        return text, lang

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

    all_channels_meta = {}
    all_programmes = []
    source_results = {}
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

        try:
            xml_text, how = decode_content_bytes(content_bytes, src_url)
            log(f"   -> decoded ({how}), length={len(xml_text)}")
        except Exception as e:
            msg = f"Decode error: {e}"
            source_results[src_url]["error"] = msg
            log(f"[!] {msg}")
            continue

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

        source_results[src_url]["ok"] = True
        channels_in_source = {}
        for ch_node in root.findall("channel"):
            cid = ch_node.attrib.get("id", "").strip()
            if not cid:
                continue
            dname = None
            dn = ch_node.find("display-name")
            if dn is not None and dn.text:
                dname = dn.text.strip()
            icon = None
            ic = ch_node.find("icon")
            if ic is not None and "src" in ic.attrib:
                icon = ic.attrib["src"]
            channels_in_source[cid.lower()] = {"id": cid, "name": dname, "icon": icon}

        source_results[src_url]["channels"] = len(channels_in_source)
        progs_found_total = 0

        for requested in ch_list:
            req_id = requested["id"]
            req_id_l = req_id.lower()

            meta = channels_in_source.get(req_id_l)
            if meta:
                all_channels_meta[requested["id"]] = {
                    "id": requested["id"],
                    "name": meta.get("name") or requested["name"],
                    "logo": meta.get("icon")
                }
            else:
                all_channels_meta[requested["id"]] = {
                    "id": requested["id"],
                    "name": requested["name"],
                    "logo": None
                }
                log(f"   - Warning: channel metadata for '{requested['id']}' not found in source; using fallback display name")

            found = 0
            for p in root.findall("programme"):
                ch_attr = p.attrib.get("channel", "")
                if ch_attr.lower() != req_id_l:
                    continue
                start_str = p.attrib.get("start", "")
                dt = None
                if start_str:
                    try:
                        dt = datetime.strptime(start_str[:14], "%Y%m%d%H%M%S")
                        dt = TIMEZONE.localize(dt)
                    except Exception:
                        try:
                            from dateutil import parser as dateparser
                            dt = dateparser.parse(start_str)
                            if dt.tzinfo is None:
                                dt = TIMEZONE.localize(dt)
                            else:
                                dt = dt.astimezone(TIMEZONE)
                        except Exception:
                            dt = None

                if dt is None or not (now <= dt <= end_time):
                    continue

                title, desc = "", ""
                tnode = p.find("title")
                if tnode is not None and tnode.text:
                    title = tnode.text.strip()
                dnode = p.find("desc")
                if dnode is not None and dnode.text:
                    desc = dnode.text.strip()

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

    safe_makedirs(OUTPUT_FILE)
    try:
        root_out = ET.Element("tv", attrib={"generator-info-name": "my-epg test"})
        for cid, meta in all_channels_meta.items():
            ch_el = ET.SubElement(root_out, "channel", id=meta["id"])
            dn = ET.SubElement(ch_el, "display-name")
            dn.text = meta.get("name") or meta["id"]
            if meta.get("logo"):
                ET.SubElement(ch_el, "icon", src=meta["logo"])

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

    # === Translation phase ===
    log("=== TRANSLATION PHASE ===")
    try:
        tree = ET.parse(OUTPUT_FILE)
        root = tree.getroot()
        translation_report = {}
        total_translated = 0

        for prog in root.findall("programme"):
            ch_id = prog.attrib.get("channel", "")
            t_node = prog.find("title")
            d_node = prog.find("desc")

            if t_node is not None and t_node.text:
                translated, lang = translate_if_needed(t_node.text)
                if lang and lang not in ("vi", "en"):
                    if ch_id not in translation_report:
                        translation_report[ch_id] = {"count": 0, "langs": set()}
                    translation_report[ch_id]["count"] += 1
                    translation_report[ch_id]["langs"].add(lang)
                    total_translated += 1
                t_node.text = translated

            if d_node is not None and d_node.text:
                translated, lang = translate_if_needed(d_node.text)
                if lang and lang not in ("vi", "en"):
                    if ch_id not in translation_report:
                        translation_report[ch_id] = {"count": 0, "langs": set()}
                    translation_report[ch_id]["count"] += 1
                    translation_report[ch_id]["langs"].add(lang)
                    total_translated += 1
                d_node.text = translated

        tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
        log(f"-> Updated translations written to {OUTPUT_FILE}")

        log("\n=== TRANSLATION SUMMARY ===")
        for ch_id, info in translation_report.items():
            langs = ", ".join(info["langs"])
            log(f"- Channel {ch_id}: translated {info['count']} entries (from {langs})")
        log(f"Total translated entries: {total_translated}")
    except Exception as e:
        log(f"[!] Translation phase failed: {e}")

    # === SUMMARY ===
    log("\n=== FINAL SUMMARY ===")
    log(f"Total channels requested: {len(channels)}")
    per_channel_counts = {ch["id"]: 0 for ch in channels}
    for p in all_programmes:
        per_channel_counts.setdefault(p["channel"], 0)
        per_channel_counts[p["channel"]] += 1
    for ch in channels:
        cnt = per_channel_counts.get(ch["id"], 0)
        log(f"- {ch['id']} ({ch['name']}): {cnt}")
    log(f"Total programmes: {len(all_programmes)}")

    ok_count = sum(1 for s in source_results.values() if s["ok"])
    fail_count = sum(1 for s in source_results.values() if not s["ok"])
    log("\n=== SOURCE SUMMARY ===")
    for src, info in source_results.items():
        if info["ok"]:
            log(f"- OK: {src} -> channels_in_source={info['channels']} programmes_matched={info['programmes']}")
        else:
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
