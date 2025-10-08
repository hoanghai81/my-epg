#!/usr/bin/env python3
# epg.py - improved EPG generator with fallbacks (VT VTV, SCTV, VTVCAB)
# Copy this file into repo root and run.

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import os
import re
import sys

# ---------- Config ----------
TIME_RE = re.compile(r'([01]?\d|2[0-3])[:.][0-5]\d')
TIME_TITLE_RE = re.compile(r'([01]?\d|2[0-3])[:.][0-5]\d\s*[-–—:]?\s*([^\n<]{3,200})')
SNIPPET_LEN = 12000  # chars to take around channel name for generic parsing
TZ = pytz.timezone("Asia/Ho_Chi_Minh")
# ----------------------------

def read_channels(path="channels.txt"):
    chans = []
    if not os.path.exists(path):
        print("channels.txt not found!", file=sys.stderr)
        return chans
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [p.strip() for p in ln.split("|")]
            if len(parts) < 2:
                continue
            cid = parts[0]
            url = parts[1]
            disp = parts[2] if len(parts) > 2 else cid
            chans.append({"id": cid, "url": url, "display": disp})
    return chans

def fetch_html(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (EPG-Generator)"}
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("  ! fetch error:", e)
        return None

# ---- Specific parsers (attempt CSS-based parse first) ----

def parse_vtv_by_dom(html, channel_id):
    """Try parsing VTV page structure"""
    try:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        # vtv uses boxes with class containing 'boxLichChuongTrinh' (observed)
        for box in soup.select(".boxLichChuongTrinh"):
            h2 = box.select_one("h2")
            if not h2: 
                continue
            if channel_id.lower() in h2.get_text(strip=True).lower():
                # li entries inside
                for li in box.select("li"):
                    t_el = li.select_one(".time")
                    p_el = li.select_one(".title")
                    if t_el and p_el:
                        t = t_el.get_text(strip=True)
                        p = p_el.get_text(strip=True)
                        out.append({"time": t, "title": p})
        return out
    except Exception as e:
        print("  vtv DOM parse error:", e)
        return []

def parse_sctv_by_dom(html, channel_id):
    try:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for block in soup.select(".schedule__content"):
            title_el = block.select_one(".schedule__title")
            if not title_el:
                continue
            if channel_id.lower() in title_el.get_text(strip=True).lower():
                for row in block.select(".schedule__item"):
                    t_el = row.select_one(".schedule__time")
                    p_el = row.select_one(".schedule__name")
                    if t_el and p_el:
                        out.append({"time": t_el.get_text(strip=True), "title": p_el.get_text(strip=True)})
        return out
    except Exception as e:
        print("  sctv DOM parse error:", e)
        return []

def parse_vtvcab_by_dom(html, channel_id):
    try:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for div in soup.select(".list-channel"):
            name_el = div.select_one(".name-channel")
            if not name_el:
                continue
            nm = name_el.get_text(strip=True).lower()
            # normalize channel_id (e.g. "ON Sports" => "sports" or check substring)
            check = channel_id.lower().replace("on ", "").strip()
            if check in nm:
                for row in div.select(".row-program"):
                    t_el = row.select_one(".time")
                    p_el = row.select_one(".name-program")
                    if t_el and p_el:
                        out.append({"time": t_el.get_text(strip=True), "title": p_el.get_text(strip=True)})
        return out
    except Exception as e:
        print("  vtvcab DOM parse error:", e)
        return []

# ---- Generic fallback parser: find channel name in HTML and regex extract times+titles ----

def parse_generic_by_snippet(html, channel_id):
    html_lower = html.lower()
    key = channel_id.lower()
    idx = html_lower.find(key)
    if idx == -1:
        # not found, try partial like remove spaces or digits
        key2 = re.sub(r'\d+', '', key).strip()
        idx = html_lower.find(key2) if key2 else -1
    if idx == -1:
        # last resort: search first 15000 chars for times and pick them
        snippet = html[:SNIPPET_LEN]
    else:
        start = max(0, idx - 2000)
        end = min(len(html), idx + SNIPPET_LEN)
        snippet = html[start:end]
    # replace html tags with newlines to reduce noise
    text = re.sub(r'<(script|style).*?</\1>', ' ', snippet, flags=re.S|re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;|\xa0', ' ', text)
    # find time-title pairs
    items = []
    for m in TIME_TITLE_RE.finditer(text):
        timestr = m.group(1).replace('.', ':')
        title = m.group(2).strip()
        # strip leading punctuation
        title = re.sub(r'^[\s\-\*\:\–\—]+', '', title)
        # avoid capturing long garbage
        if len(title) > 200:
            title = title[:200].strip()
        items.append({"time": timestr, "title": title})
    # dedupe while preserving order
    seen = set()
    out = []
    for it in items:
        keyt = (it["time"], it["title"])
        if keyt in seen: continue
        seen.add(keyt)
        out.append(it)
    return out

# ---- Unified schedule getter ----

def fetch_schedule_for_channel(ch):
    url = ch.get("url", "")
    html = fetch_html(url)
    if not html:
        return []
    # try site-specific DOM parsers first
    lower = url.lower()
    res = []
    if "vtv.vn" in lower:
        res = parse_vtv_by_dom(html, ch["id"])
        if res:
            return res
    if "sctv.com.vn" in lower:
        res = parse_sctv_by_dom(html, ch["id"])
        if res:
            return res
    if "vtvcab.vn" in lower or "dichvu.vtvcab" in lower:
        res = parse_vtvcab_by_dom(html, ch["id"])
        if res:
            return res
    # fallback generic
    res = parse_generic_by_snippet(html, ch["id"])
    return res

# ---- build programmes into xml ----

def build_programmes(channels):
    tv = ET.Element("tv", attrib={"generator-info-name":"github-epg-generator"})
    today = datetime.now(TZ).date()

    # add channels
    for ch in channels:
        ce = ET.SubElement(tv, "channel", id=ch["id"])
        dn = ET.SubElement(ce, "display-name")
        dn.text = ch.get("display", ch["id"])

    # get schedules
    for ch in channels:
        print("=> Lấy lịch cho:", ch["id"])
        try:
            sched = fetch_schedule_for_channel(ch)
        except Exception as e:
            print("  ! exception fetching:", e)
            sched = []
        print("   - items found:", len(sched))
        if not sched:
            # leave no programme (so file still valid); optionally add a placeholder
            continue

        prev_dt = None
        for i, item in enumerate(sched):
            # parse HH:MM
            parsed = re.search(r'([01]?\d|2[0-3])[:.][0-5]\d', item["time"] or "")
            if not parsed:
                continue
            hhmm = parsed.group(0).replace('.', ':')
            hh, mm = [int(x) for x in hhmm.split(':')]
            dt_start = datetime(year=today.year, month=today.month, day=today.day, hour=hh, minute=mm, tzinfo=TZ)
            # if previous start exists and dt_start <= prev -> assume next day
            if prev_dt and dt_start <= prev_dt:
                dt_start = dt_start + timedelta(days=1)
            # compute stop time
            dt_stop = None
            if i + 1 < len(sched):
                parsed2 = re.search(r'([01]?\d|2[0-3])[:.][0-5]\d', sched[i+1]["time"] or "")
                if parsed2:
                    hh2, mm2 = [int(x) for x in parsed2.group(0).replace('.',':').split(':')]
                    dt_stop = datetime(year=today.year, month=today.month, day=today.day, hour=hh2, minute=mm2, tzinfo=TZ)
                    if dt_stop <= dt_start:
                        dt_stop = dt_stop + timedelta(days=1)
            if dt_stop is None:
                dt_stop = dt_start + timedelta(minutes=30)

            prog = ET.SubElement(tv, "programme", {
                "start": dt_start.strftime("%Y%m%d%H%M%S") + " +0700",
                "stop": dt_stop.strftime("%Y%m%d%H%M%S") + " +0700",
                "channel": ch["id"]
            })
            t = ET.SubElement(prog, "title", {"lang":"vi"})
            t.text = item.get("title") or ""
            d = ET.SubElement(prog, "desc", {"lang":"vi"})
            d.text = ""
            prev_dt = dt_start

    return tv

def write_xml(tv_elem, out="docs/epg.xml"):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tree = ET.ElementTree(tv_elem)
    tree.write(out, encoding="utf-8", xml_declaration=True)
    print("-> written", out)

def main():
    chans = read_channels()
    if not chans:
        print("No channels found in channels.txt", file=sys.stderr)
        return
    tv = build_programmes(chans)
    write_xml(tv)

if __name__ == "__main__":
    main()
