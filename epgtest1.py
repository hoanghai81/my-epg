#!/usr/bin/env python3
# epgtest1.py
# Tự động lấy EPG, lọc theo thời gian, dịch sang tiếng Anh nếu không phải tiếng Việt/Anh.
# Xuất ra: docs/epgtest1.xml + log dịch docs/epgtest1.log

import os
import gzip
import io
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import traceback
from deep_translator import GoogleTranslator
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # fix random detect

CHANNEL_FILE = "channels.txt"
OUTPUT_FILE = "docs/epgtest1.xml"
LOG_FILE = "docs/epgtest1.log"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
DAYS = 1  # Hôm nay + ngày mai

def log(msg=""):
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

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
            return txt, "gzip"
        except Exception:
            with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                txt = f.read().decode("utf-8", errors="ignore")
                return txt, "gzip(fallback)"
    else:
        try:
            return content.decode("utf-8", errors="ignore"), "plain"
        except Exception:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip(fallback2)"

def parse_xml_text(xml_text, url):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error for {url}: {e}")

def read_channels_file():
    if not os.path.exists(CHANNEL_FILE):
        raise FileNotFoundError(f"{CHANNEL_FILE} not found")
    channels = []
    with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            channels.append({"id": parts[0], "url": parts[1], "name": parts[2]})
    return channels

def detect_lang_safe(text):
    try:
        lang = detect(text)
        return lang
    except Exception:
        return "unknown"

def translate_text_if_needed(text, translator):
    if not text.strip():
        return text, False
    lang = detect_lang_safe(text)
    if lang in ["vi", "en"]:
        return text, False
    try:
        translated = translator.translate(text)
        return translated, True
    except Exception:
        return text, False

def main():
    safe_makedirs(LOG_FILE)
    open(LOG_FILE, "w").close()  # clear old log
    log("=== BẮT ĐẦU SINH EPG VÀ DỊCH TỰ ĐỘNG ===")

    try:
        translator = GoogleTranslator(source="auto", target="en")
    except Exception as e:
        log(f"[!] Không thể khởi tạo translator: {e}")
        return

    try:
        channels = read_channels_file()
    except Exception as e:
        log(f"[!] Cannot read channels file: {e}")
        return

    log(f"=> Tổng số kênh: {len(channels)}")
    now = datetime.now(TIMEZONE)
    end_time = now + timedelta(days=DAYS)
    log(f"=> Thời gian lấy EPG: {now} -> {end_time}\n")

    all_channels_meta = {}
    all_programmes = []
    source_results = {}
    translated_channels = set()

    url_to_channel_ids = {}
    for ch in channels:
        url_to_channel_ids.setdefault(ch["url"], []).append(ch)

    for src_url, ch_list in url_to_channel_ids.items():
        log(f"=> Đang tải: {src_url}")
        source_results[src_url] = {"ok": False, "error": None, "channels": 0, "programmes": 0}

        try:
            content_bytes, _ = download_content(src_url)
            xml_text, how = decode_content_bytes(content_bytes, src_url)
            root = parse_xml_text(xml_text, src_url)
            source_results[src_url]["ok"] = True
            log(f"   -> Parsed root tag: {root.tag} ({how})")
        except Exception as e:
            source_results[src_url]["error"] = str(e)
            log(f"[!] Lỗi đọc nguồn {src_url}: {e}")
            continue

        channels_in_source = {}
        for ch_node in root.findall("channel"):
            cid = ch_node.attrib.get("id", "").strip()
            if not cid:
                continue
            dname = ch_node.findtext("display-name", "").strip()
            icon_el = ch_node.find("icon")
            icon = icon_el.attrib["src"] if (icon_el is not None and "src" in icon_el.attrib) else None
            channels_in_source[cid.lower()] = {"id": cid, "name": dname, "icon": icon}

        source_results[src_url]["channels"] = len(channels_in_source)

        for requested in ch_list:
            req_id = requested["id"]
            req_id_l = req_id.lower()
            meta = channels_in_source.get(req_id_l, None)
            if meta:
                all_channels_meta[req_id] = {
                    "id": req_id,
                    "name": meta.get("name") or requested["name"],
                    "logo": meta.get("icon")
                }
            else:
                all_channels_meta[req_id] = {"id": req_id, "name": requested["name"], "logo": None}

            found = 0
            for p in root.findall("programme"):
                ch_attr = p.attrib.get("channel", "")
                if ch_attr.lower() != req_id_l:
                    continue
                start_str = p.attrib.get("start", "")
                try:
                    dt = datetime.strptime(start_str[:14], "%Y%m%d%H%M%S")
                    dt = TIMEZONE.localize(dt)
                except Exception:
                    continue
                if not (now <= dt <= end_time):
                    continue

                title = p.findtext("title", "").strip()
                desc = p.findtext("desc", "").strip()

                title_new, changed_t = translate_text_if_needed(title, translator)
                desc_new, changed_d = translate_text_if_needed(desc, translator)

                if changed_t or changed_d:
                    translated_channels.add(req_id)

                all_programmes.append({
                    "start": p.attrib.get("start", ""),
                    "stop": p.attrib.get("stop", ""),
                    "channel": req_id,
                    "title": title_new,
                    "desc": desc_new
                })
                found += 1
            source_results[src_url]["programmes"] += found
            log(f"   - {req_id} -> {found} programmes")

    # Write output XML
    safe_makedirs(OUTPUT_FILE)
    try:
        root_out = ET.Element("tv", attrib={"generator-info-name": "my-epg translate"})
        for cid, meta in all_channels_meta.items():
            ch_el = ET.SubElement(root_out, "channel", id=meta["id"])
            dn = ET.SubElement(ch_el, "display-name")
            dn.text = meta["name"] or meta["id"]
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
        log(f"-> Đã tạo {OUTPUT_FILE} ({len(all_programmes)} programmes)\n")
    except Exception as e:
        log(f"[!] Lỗi ghi file: {e}")
        traceback.print_exc()
        return

    # Summary
    log("=== TỔNG KẾT ===")
    log(f"Tổng số chương trình: {len(all_programmes)}")
    log(f"Kênh có dịch nội dung: {len(translated_channels)}")
    for cid in sorted(translated_channels):
        log(f"  - {cid}")
    log("\n=== HOÀN TẤT ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("=== LỖI TOÀN CỤC ===")
        log(str(e))
        traceback.print_exc()
