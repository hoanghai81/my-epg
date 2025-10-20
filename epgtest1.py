#!/usr/bin/env python3
# epgtest1.py
# Extended EPG test script with title-translation (non-vi/en -> en),
# per-source summary, per-channel counts, and translation summary + log.
#
# Requirements (install in workflow):
# pip install requests pytz python-dateutil deep-translator langdetect

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

# make langdetect deterministic
DetectorFactory.seed = 0

# CONFIG
CHANNEL_FILE = "channels.txt"
OUTPUT_FILE = "docs/epgtest1.xml"
LOG_FILE = "docs/epgtest1.log"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
# Window: today + next day (DAYS=1 means now -> now + 1 day)
DAYS = 1

# Helper logging (console + log file)
def log_print(msg=""):
    print(msg, flush=True)
    try:
        # ensure log dir exists
        d = os.path.dirname(LOG_FILE)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def safe_makedirs_for_file(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# Download + decode utilities
def download_content(url, timeout=30):
    headers = {"User-Agent": "my-epg-test/1.0"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.content, r.headers

def decode_content_bytes(content, url):
    # detect gzip magic bytes
    if len(content) >= 2 and content[:2] == b'\x1f\x8b':
        try:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip(magic)"
        except Exception:
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
                    txt = f.read().decode("utf-8", errors="ignore")
                    return txt, "gzip(fallback)"
            except Exception:
                raise
    # not gzip: decode as text
    try:
        txt = content.decode("utf-8", errors="ignore")
        return txt, "plain"
    except Exception:
        # fallback try gzip
        try:
            txt = gzip.decompress(content).decode("utf-8", errors="ignore")
            return txt, "gzip(fallback2)"
        except Exception:
            raise

def parse_xml_text(xml_text, url):
    try:
        root = ET.fromstring(xml_text)
        return root
    except ET.ParseError as e:
        raise ValueError(f"XML parse error for {url}: {e}")

# Read channels file
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
            channels.append({"id": parts[0], "url": parts[1], "name": parts[2]})
    return channels

# Safe language detect
def detect_lang_safe(text):
    try:
        if not text or not text.strip():
            return None
        return detect(text)
    except Exception:
        return None

# Translator wrapper with cache and heuristic
class TranslatorCache:
    def __init__(self):
        self.cache = {}  # original_text -> translated_text
        try:
            self.translator = GoogleTranslator(source="auto", target="en")
        except Exception:
            # fallback None (should not happen in Actions when dependency installed)
            self.translator = None

    def needs_translation(self, text):
        # empty or short text: still try detect; but we treat empty as no-translate
        if not text or not text.strip():
            return False, None
        lang = detect_lang_safe(text)
        # if lang is None -> check presence of non-ascii chars
        if lang is None:
            # if contains non-ascii => translate
            if any(ord(c) > 127 for c in text):
                return True, None
            return False, None
        # if Vietnamese or English -> keep
        if lang in ("vi", "en"):
            return False, lang
        return True, lang

    def translate(self, text):
        if text in self.cache:
            return self.cache[text]
        # attempt translation
        try:
            if not self.translator:
                # try re-init
                self.translator = GoogleTranslator(source="auto", target="en")
            translated = self.translator.translate(text)
            self.cache[text] = translated
            return translated
        except Exception as e:
            # on failure, fallback to original
            self.cache[text] = text
            return text

def main():
    # Prepare log file
    safe_makedirs_for_file(LOG_FILE)
    # clear existing log
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()
    except Exception:
        pass

    log_print("=== BẮT ĐẦU SINH EPG TEST (with translation) ===")
    try:
        channels = read_channels_file()
    except Exception as e:
        log_print(f"[!] Cannot read channels file: {e}")
        return

    log_print(f"=> Tổng kênh trong channels.txt: {len(channels)}")
    now = datetime.now(TIMEZONE)
    end_time = now + timedelta(days=DAYS)
    log_print(f"=> Window: {now} -> {end_time} ({TIMEZONE})\n")

    # data containers
    all_channels_meta = {}   # id -> {id,name,logo}
    all_programmes = []      # list of dicts
    source_results = {}      # url -> {ok,error,channels,programmes}
    per_channel_matches = {ch["id"]: 0 for ch in channels}  # requested counts

    # group channels by source url so we fetch once
    url_to_channel_ids = {}
    for ch in channels:
        url_to_channel_ids.setdefault(ch["url"], []).append(ch)

    # fetch each source
    for src_url, ch_list in url_to_channel_ids.items():
        log_print(f"=> Downloading: {src_url}")
        source_results[src_url] = {"ok": False, "error": None, "channels": 0, "programmes": 0}
        try:
            content_bytes, _ = download_content(src_url)
        except Exception as e:
            msg = f"Download error: {e}"
            source_results[src_url]["error"] = msg
            log_print(f"[!] {msg}")
            continue

        try:
            xml_text, how = decode_content_bytes(content_bytes, src_url)
            log_print(f"   -> decoded ({how}), length={len(xml_text)}")
        except Exception as e:
            msg = f"Decode error: {e}"
            source_results[src_url]["error"] = msg
            log_print(f"[!] {msg}")
            continue

        try:
            root = parse_xml_text(xml_text, src_url)
            if root is None or root.tag is None:
                raise ValueError("Empty or invalid root")
            log_print(f"   -> Parsed root tag: {root.tag}")
        except Exception as e:
            msg = f"Parse error: {e}"
            source_results[src_url]["error"] = msg
            log_print(f"[!] {msg}")
            continue

        source_results[src_url]["ok"] = True

        # collect channel metadata present in this source
        channels_in_source = {}
        for ch_node in root.findall("channel"):
            cid = ch_node.attrib.get("id", "").strip()
            if not cid:
                continue
            # find first display-name
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

        # for each requested channel from this source, find programmes
        progs_found_total = 0
        for requested in ch_list:
            req_id = requested["id"]
            req_id_l = req_id.lower()

            # meta: try get from source, else fallback to channels.txt name
            meta = channels_in_source.get(req_id_l)
            if meta:
                all_channels_meta[req_id] = {
                    "id": req_id,
                    "name": meta.get("name") or requested["name"],
                    "logo": meta.get("icon")
                }
            else:
                all_channels_meta[req_id] = {
                    "id": req_id,
                    "name": requested["name"],
                    "logo": None
                }
                log_print(f"   - Warning: channel metadata for '{req_id}' not found in source; using fallback display name")

            # scan programmes
            found = 0
            for p in root.findall("programme"):
                ch_attr = p.attrib.get("channel", "")
                if ch_attr.lower() != req_id_l:
                    continue
                start_str = p.attrib.get("start", "")
                if not start_str:
                    continue
                # parse start
                dt = None
                try:
                    # try yyyyMMddHHmmss
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
                if dt is None:
                    continue
                # filter window
                if not (now <= dt <= end_time):
                    continue

                title = p.findtext("title", "").strip()
                desc = p.findtext("desc", "").strip()

                all_programmes.append({
                    "start": p.attrib.get("start", ""),
                    "stop": p.attrib.get("stop", ""),
                    "channel": req_id,
                    "title": title,
                    "desc": desc
                })
                found += 1

            per_channel_matches[req_id] = per_channel_matches.get(req_id, 0) + found
            progs_found_total += found
            log_print(f"   - {req_id} -> matched {found} programmes")

        source_results[src_url]["programmes"] = progs_found_total
        log_print(f"   -> total programmes matched from this source: {progs_found_total}\n")

    # translation: only for <title> (and not for existing en/vi)
    log_print("=== TRANSLATION PHASE (titles only) ===")
    safe_makedirs_for_file(LOG_FILE)
    # prepare translator cache
    translator_cache = {}
    translator = None
    try:
        translator = GoogleTranslator(source="auto", target="en")
    except Exception as e:
        log_print(f"[!] Could not init translator: {e}. Translation will be skipped.")
    translation_report = {}  # channel -> {"count": int, "langs": set()}
    total_translated = 0
    channels_translated = set()

    def should_translate_title(text):
        if not text or not text.strip():
            return False, None
        lang = detect_lang_safe(text)
        if lang in ("vi", "en"):
            return False, lang
        # if detect None but contains non-ascii, treat as needs translation
        if lang is None:
            # heuristic: if contains non-ascii => translate
            if any(ord(c) > 127 for c in text):
                return True, None
            return False, None
        return True, lang

    def translate_with_cache(text):
        # return translated_text, detected_lang
        if text in translator_cache:
            return translator_cache[text]
        # detect + translate
        lang = detect_lang_safe(text)
        try:
            if translator and (lang not in ("vi", "en")):
                translated = translator.translate(text)
                translator_cache[text] = (translated, lang)
                return translated, lang
            else:
                # if lang is vi or en or translator missing, return original
                translator_cache[text] = (text, lang)
                return text, lang
        except Exception as e:
            # on any failure, fallback to original
            translator_cache[text] = (text, lang)
            log_print(f"[!] Translation failed for text: {repr(text)} -> {e}")
            return text, lang

    # iterate programmes and translate title if needed
    for prog in all_programmes:
        ch_id = prog["channel"]
        title = prog.get("title", "") or ""
        need, dlang = should_translate_title(title)
        if need:
            translated_text, detected = translate_with_cache(title)
            # if translation happened (translated != original) or lang indicated non-en/vi
            if translated_text != title:
                # record
                translation_report.setdefault(ch_id, {"count": 0, "langs": set()})
                translation_report[ch_id]["count"] += 1
                if detected:
                    translation_report[ch_id]["langs"].add(detected)
                channels_translated.add(ch_id)
                total_translated += 1
            # put translated text back (even if same)
            prog["title"] = translated_text
        # else keep original title

    # After translations done: write XML output
    safe_makedirs_for_file(OUTPUT_FILE)
    try:
        root_out = ET.Element("tv", attrib={"generator-info-name": "my-epg translate"})
        # channels
        for cid, meta in all_channels_meta.items():
            ch_el = ET.SubElement(root_out, "channel", id=meta["id"])
            dn = ET.SubElement(ch_el, "display-name")
            dn.text = meta.get("name") or meta["id"]
            if meta.get("logo"):
                ET.SubElement(ch_el, "icon", src=meta["logo"])
        # programmes
        for p in all_programmes:
            p_el = ET.SubElement(root_out, "programme", start=p["start"], stop=p["stop"], channel=p["channel"])
            t_el = ET.SubElement(p_el, "title")
            t_el.text = p["title"]
            if p.get("desc"):
                d_el = ET.SubElement(p_el, "desc")
                d_el.text = p["desc"]
        ET.ElementTree(root_out).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
        log_print(f"-> written {OUTPUT_FILE} ({len(all_programmes)} programmes, {len(all_channels_meta)} channels)\n")
    except Exception as e:
        log_print(f"[!] Error writing output file: {e}")
        traceback.print_exc()
        return

    # Write detailed translation log (per translated text)
    try:
        # append details to log file
        with open(LOG_FILE, "a", encoding="utf-8") as lf:
            lf.write("\n=== TRANSLATION DETAILS ===\n")
            for original, (translated, det) in translator_cache.items():
                if translated != original:
                    lf.write(f"ORIG: {original}\nTRAN: {translated}\nDETECT: {det}\n---\n")
    except Exception:
        pass

    # Final summaries
    log_print("=== SUMMARY: channel matches ===")
    total_programmes = len(all_programmes)
    log_print(f"Total channels requested: {len(channels)}")
    for ch in channels:
        cnt = per_channel_matches.get(ch["id"], 0)
        log_print(f"- {ch['id']} ({ch['name']}): {cnt}")

    log_print(f"\nTotal programmes matched: {total_programmes}\n")

    log_print("=== SOURCE SUMMARY ===")
    ok_count = 0
    fail_count = 0
    for src, info in source_results.items():
        if info["ok"]:
            ok_count += 1
            log_print(f"- OK: {src} -> channels_in_source={info['channels']} programmes_matched={info['programmes']}")
        else:
            fail_count += 1
            log_print(f"- FAIL: {src} -> error: {info['error']}")
    log_print(f"Sources OK: {ok_count} | Failed: {fail_count}")

    log_print("\n=== TRANSLATION SUMMARY ===")
    log_print(f"Total translated entries: {total_translated}")
    log_print(f"Total channels with translations: {len(channels_translated)}")
    for ch_id, info in translation_report.items():
        langs = ", ".join(sorted(info["langs"])) if info["langs"] else "unknown"
        log_print(f"- {ch_id}: {info['count']} translated (from {langs})")

    log_print("\n=== HOÀN TẤT ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_print("=== UNHANDLED EXCEPTION ===")
        log_print(str(e))
        traceback.print_exc()
        raise
