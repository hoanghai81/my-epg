#!/usr/bin/env python3
# epg.py — improved debug + fallback parsing for VTV / SCTV / VTVCAB via Cloudflare Worker proxy
# Copy & paste this file to replace your current epg.py, then run GH Action.

import os
import sys
import json
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dparser
from datetime import datetime, timedelta
import pytz
import xml.etree.ElementTree as ET

# ---------- config ----------
# If you set secret EPG_PROXY_URL in repo secrets and mapped to env, it will be used.
PROXY_BASE = os.environ.get("EPG_PROXY_URL", "https://epg-proxy.haikoc.workers.dev")
TZ = pytz.timezone("Asia/Ho_Chi_Minh")
TODAY_STR = datetime.now(TZ).date().strftime("%Y-%m-%d")
OUT_PATH = "docs/epg.xml"
# regex to extract "HH:MM - Title" patterns in messy HTML
TIME_TITLE_RE = re.compile(r'([01]?\d|2[0-3])[:.][0-5]\d\s*[-–—:]?\s*([^\n<]{3,200})')
# ----------------------------

def read_channels(path="channels.txt"):
    if not os.path.exists(path):
        print("channels.txt not found!", file=sys.stderr)
        return []
    chans = []
    with open(path, encoding="utf-8") as f:
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

def proxy_fetch_text(target_url):
    """Fetch via Cloudflare Worker (proxy) if configured, else direct.
    Returns tuple: (text_or_None, response_obj_or_None)
    """
    # build proxied URL
    prox = PROXY_BASE.rstrip("/") + "/?url=" + urllib.parse.quote_plus(target_url)
    headers = {"User-Agent": "Mozilla/5.0 (EPG-Generator)"}
    try:
        r = requests.get(prox, headers=headers, timeout=25)
        r.raise_for_status()
        text = r.text
        # log status and content-type to help debugging
        ct = r.headers.get("content-type", "")
        print(f"    [fetch] proxied {target_url} -> status {r.status_code}, content-type: {ct}, length={len(text)}")
        return text, r
    except Exception as e:
        print(f"    [fetch error] {target_url}: {e}")
        return None, None

def try_parse_json(text):
    """Try to parse JSON safely, return object or None"""
    if not text:
        return None
    s = text.strip()
    if not s:
        return None
    if s[0] not in ("{", "["):
        return None
    try:
        return json.loads(s)
    except Exception as e:
        return None

# ---------- site-specific parsers (use proxy_fetch_text) ----------

def parse_vtv_api_or_html(channel):
    """First try API (vtvapi), if response not JSON then fallback to parsing vtv.vn page or regex."""
    # many implementations used vtvapi.vtv.vn but it's often unavailable — we'll attempt and fallback
    # Build API URL patterns commonly used (if channel id contains number)
    ch = channel["id"]
    digits_match = re.search(r'(\d+)', ch)
    api_urls = []
    if digits_match:
        n = digits_match.group(1)
        api_urls.append(f"https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv{n}&date={TODAY_STR}")
    # also try generic schedule page (main site) if provided URL points to it
    # If channel.url already points to a vtv page, include it
    if "vtv.vn" in channel["url"]:
        api_urls.append(channel["url"])
    # try each url
    for url in api_urls:
        txt, resp = proxy_fetch_text(url)
        if not txt:
            continue
        j = try_parse_json(txt)
        if j:
            # try to extract schedule items (structure may vary)
            items = []
            data = j.get("data") if isinstance(j, dict) else j
            if isinstance(data, list):
                for it in data:
                    # Accept several possible fields
                    start = it.get("start_time") or it.get("time") or it.get("start")
                    end = it.get("end_time") or it.get("end")
                    title = it.get("name") or it.get("title") or it.get("program_name") or ""
                    if start and title:
                        items.append({"time": start, "title": title, "end": end})
            # if items found, return normalized list
            if items:
                return normalize_programs(items)
        else:
            # not JSON: print a short debug snippet and then fall back to HTML parsing
            snippet = txt[:500].replace("\n", " ").replace("\r", " ")
            print(f"    [debug] non-JSON response (first 500 chars): {snippet!s}")
            # fallback: attempt to parse html schedule on vtv site
            if "vtv.vn" in url or "lich-phat-song" in url or "vtv" in channel["url"]:
                # fetch main schedule page (use the channel.url if it's the main page)
                main_url = channel["url"] if "vtv.vn" in channel["url"] else "https://vtv.vn/lich-phat-song.htm"
                txt2, _ = proxy_fetch_text(main_url)
                if txt2:
                    out = parse_vtv_html_main(txt2, channel)
                    if out:
                        return out
    # if nothing found, final fallback: try generic regex on channel.url
    txt_final, _ = proxy_fetch_text(channel["url"])
    if txt_final:
        arr = generic_time_title_parse(txt_final, channel["id"])
        return arr
    return []

def parse_vtv_html_main(html_text, channel):
    """Parse vtv.vn main schedule boxes (heuristic)"""
    try:
        soup = BeautifulSoup(html_text, "lxml")
    except Exception:
        soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for box in soup.select(".boxLichChuongTrinh"):
        h2 = box.select_one("h2")
        if not h2:
            continue
        if channel["id"].lower() in h2.get_text(strip=True).lower():
            for li in box.select("li"):
                t_el = li.select_one(".time")
                p_el = li.select_one(".title")
                if t_el and p_el:
                    out.append({"time": t_el.get_text(strip=True), "title": p_el.get_text(strip=True)})
    if out:
        return normalize_programs(out)
    # fallback: try to find a header with the channel name and capture following times
    text = soup.get_text(" ", strip=True)
    return generic_time_title_parse(text, channel["id"])

def parse_sctv_html(channel):
    txt, _ = proxy_fetch_text(channel["url"])
    if not txt:
        return []
    try:
        soup = BeautifulSoup(txt, "lxml")
    except Exception:
        soup = BeautifulSoup(txt, "html.parser")
    out = []
    # try some known selectors
    # blocks with schedule__content
    for block in soup.select(".schedule__content"):
        title_el = block.select_one(".schedule__title")
        if not title_el:
            continue
        if channel["id"].lower() in title_el.get_text(strip=True).lower():
            for row in block.select(".schedule__item"):
                t = row.select_one(".schedule__time")
                p = row.select_one(".schedule__name")
                if t and p:
                    out.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    if out:
        return normalize_programs(out)
    # fallback generic parse near channel id
    return generic_time_title_parse(txt, channel["id"])

def parse_vtvcab_html(channel):
    txt, _ = proxy_fetch_text(channel["url"])
    if not txt:
        return []
    try:
        soup = BeautifulSoup(txt, "lxml")
    except Exception:
        soup = BeautifulSoup(txt, "html.parser")
    out = []
    for div in soup.select(".list-channel"):
        nm_el = div.select_one(".name-channel")
        nm = nm_el.get_text(strip=True).lower() if nm_el else ""
        key = channel["id"].lower().replace("on ", "")
        if key in nm:
            for row in div.select(".row-program"):
                t = row.select_one(".time")
                p = row.select_one(".name-program")
                if t and p:
                    out.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    if out:
        return normalize_programs(out)
    # fallback generic
    return generic_time_title_parse(txt, channel["id"])

# ---------- generic helpers ----------

def generic_time_title_parse(text, channel_id):
    """Generic fallback: search near channel_id for time-title pairs using regex"""
    if not text:
        return []
    txt_low = text.lower()
    idx = txt_low.find(channel_id.lower())
    if idx != -1:
        snippet = text[max(0, idx-2000): idx+8000]
    else:
        snippet = text[:8000]
    items = []
    for m in TIME_TITLE_RE.finditer(snippet):
        timestr = m.group(1).replace('.', ':')
        title = m.group(2).strip()
        items.append({"time": timestr, "title": title})
    return normalize_programs(items)

def normalize_programs(raw_items):
    """Convert list of dicts with 'time' or 'start' into list of dicts with datetime starts and titles.
       raw_item may have 'time' (HH:MM or '08:00') or full datetime strings.
    """
    out = []
    for it in raw_items:
        tstr = it.get("time") or it.get("start") or ""
        title = it.get("title") or ""
        if not tstr or not title:
            continue
        # try to parse robustly
        dt = None
        try:
            # If it's only HH:MM or contains ":" but not a date, combine with TODAY
            if re.match(r'^[0-2]?\d[:.][0-5]\d$', tstr.strip()):
                hhmm = tstr.strip().replace('.', ':')
                hh, mm = [int(x) for x in hhmm.split(":")]
                dt = datetime(year=int(TODAY_STR[:4]), month=int(TODAY_STR[5:7]), day=int(TODAY_STR[8:10]),
                              hour=hh, minute=mm, tzinfo=TZ)
            else:
                # try full parse (ISO etc)
                dt = dparser.parse(tstr)
                if not dt.tzinfo:
                    dt = dt.replace(tzinfo=TZ)
        except Exception:
            # gross fallback: skip
            continue
        out.append({"start": dt, "title": title})
    # sort by start time
    out.sort(key=lambda x: x["start"])
    # remove duplicates (same time+title)
    seen = set()
    uniq = []
    for i in out:
        k = (i["start"].strftime("%H:%M"), i["title"])
        if k in seen: continue
        seen.add(k)
        uniq.append(i)
    return uniq

# ---------- build XML ----------

def build_epg(channels):
    tv = ET.Element("tv", attrib={"generator-info-name": "github-epg"})
    for ch in channels:
        print(f"=> Lấy lịch cho: {ch['id']}")
        programs = []
        try:
            if "vtv.vn" in ch["url"] or "vtvapi" in ch["url"]:
                programs = parse_vtv_api_or_html(ch)
            elif "sctv.com.vn" in ch["url"]:
                programs = parse_sctv_html(ch)
            elif "vtvcab" in ch["url"] or "dichvu.vtvcab" in ch["url"]:
                programs = parse_vtvcab_html(ch)
            else:
                # generic fetch + parse
                txt, _ = proxy_fetch_text(ch["url"])
                programs = generic_time_title_parse(txt, ch["id"]) if txt else []
        except Exception as e:
            print(f"   [!] exception for {ch['id']}: {e}")
            programs = []

        print(f"   - items found: {len(programs)}")
        # print detailed lines
        for p in programs:
            try:
                print("     -", p["start"].strftime("%H:%M"), "-", p["title"])
            except Exception:
                print("     - (bad time) -", p.get("title",""))

        # create channel element and programmes in XML
        if programs:
            ch_el = ET.SubElement(tv, "channel", id=ch["id"])
            dn = ET.SubElement(ch_el, "display-name")
            dn.text = ch["display"]
            # create programme entries
            for idx, p in enumerate(programs):
                start_dt = p["start"]
                # determine stop: either next start or +30min
                if idx + 1 < len(programs):
                    stop_dt = programs[idx+1]["start"]
                    if stop_dt <= start_dt:
                        stop_dt = stop_dt + timedelta(days=1)
                else:
                    stop_dt = start_dt + timedelta(minutes=30)
                prog = ET.SubElement(tv, "programme", {
                    "start": start_dt.strftime("%Y%m%d%H%M%S") + " +0700",
                    "stop": stop_dt.strftime("%Y%m%d%H%M%S") + " +0700",
                    "channel": ch["id"]
                })
                t_el = ET.SubElement(prog, "title", {"lang":"vi"})
                t_el.text = p["title"]
                d_el = ET.SubElement(prog, "desc", {"lang":"vi"})
                d_el.text = ""
    return tv

def write_xml(elem, out=OUT_PATH):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tree = ET.ElementTree(elem)
    # pretty indent if available (py3.9+)
    try:
        ET.indent(elem)
    except Exception:
        pass
    tree.write(out, encoding="utf-8", xml_declaration=True)
    print("-> written", out)

# ---------- main ----------
if __name__ == "__main__":
    chans = read_channels()
    if not chans:
        print("No channels found in channels.txt", file=sys.stderr)
        sys.exit(1)
    tv_elem = build_epg(chans)
    write_xml(tv_elem)
            
