#!/usr/bin/env python3
# epg_translate.py
# Translate programme titles/descriptions for selected channels from docs/epgtest.xml
# Output: docs/epgtest-translated.xml
# Uses deep_translator + langdetect
# Author: ChatGPT assistant (for Hai Vu)

import os
import time
import xml.etree.ElementTree as ET
from langdetect import detect
from deep_translator import GoogleTranslator

INPUT_FILE = "docs/epgtest.xml"
OUTPUT_FILE = "docs/epgtest-translated.xml"
CHANNELS_FILE = "channels_to_translate.txt"

def log(msg=""):
    print(msg, flush=True)

def read_channels_to_translate():
    """Read channel IDs from channels_to_translate.txt"""
    channels = {}
    if not os.path.exists(CHANNELS_FILE):
        log(f"[!] Missing {CHANNELS_FILE}")
        return channels
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                cid = parts[0]
                lang = parts[1].upper()
                channels[cid] = {"lang": lang}
    return channels

def detect_language_safe(text):
    """Safely detect language of a given text"""
    try:
        lang = detect(text)
        return lang
    except Exception:
        return "unknown"

def translate_text_if_needed(text, translator, skip_langs=("en", "vi")):
    """Translate text if not English or Vietnamese"""
    if not text or text.strip() == "":
        return text, False
    lang = detect_language_safe(text)
    if lang in skip_langs:
        return text, False
    try:
        translated = translator.translate(text)
        return translated, True
    except Exception as e:
        log(f"[WARN] Translation failed: {e}")
        return text, False

def translate_epg():
    start_time = time.time()
    translator = GoogleTranslator(source="auto", target="en")

    log("=== START TRANSLATION ===")
    log(f"Input : {INPUT_FILE}")
    log(f"Output: {OUTPUT_FILE}")
    log(f"Channels list: {CHANNELS_FILE}\n")

    channels_to_translate = read_channels_to_translate()
    log(f"Loaded {len(channels_to_translate)} channels to translate.\n")

    if not os.path.exists(INPUT_FILE):
        log(f"[!] Missing input file: {INPUT_FILE}")
        return

    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    stats = {}
    total_programmes = 0
    total_translated = 0
    total_skipped = 0

    for prog in root.findall("programme"):
        channel_id = prog.attrib.get("channel", "")
        if not channel_id:
            continue
        total_programmes += 1
        # chỉ xử lý các kênh có trong danh sách
        if channel_id not in channels_to_translate:
            continue

        stats.setdefault(channel_id, {"total": 0, "translated": 0, "skipped": 0})
        stats[channel_id]["total"] += 1

        title_el = prog.find("title")
        desc_el = prog.find("desc")

        changed = False
        if title_el is not None and title_el.text:
            new_text, did_translate = translate_text_if_needed(title_el.text, translator)
            if did_translate:
                title_el.text = new_text
                stats[channel_id]["translated"] += 1
                changed = True
            else:
                stats[channel_id]["skipped"] += 1

        if desc_el is not None and desc_el.text:
            new_text, did_translate = translate_text_if_needed(desc_el.text, translator)
            if did_translate:
                desc_el.text = new_text
                stats[channel_id]["translated"] += 1
                changed = True
            else:
                stats[channel_id]["skipped"] += 1

        if changed:
            total_translated += 1

    # Write new XML
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    # Summary
    total_skipped = sum(v["skipped"] for v in stats.values())
    duration = time.time() - start_time

    log("\n=== TRANSLATION SUMMARY ===")
    for cid, info in stats.items():
        log(f"Channel {cid}:")
        log(f"  Total programmes: {info['total']}")
        log(f"  Translated: {info['translated']}")
        log(f"  Skipped: {info['skipped']}\n")
    log(f"Overall total programmes processed: {total_programmes}")
    log(f"Total channels translated: {len(stats)}")
    log(f"Total translated: {total_translated}")
    log(f"Total skipped: {total_skipped}")
    log(f"Runtime: {duration:.1f} seconds")
    log("===========================\n")

if __name__ == "__main__":
    translate_epg()
