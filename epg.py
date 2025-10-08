#!/usr/bin/env python3
import os, sys, requests, re
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import urllib.parse

TZ = pytz.timezone("Asia/Ho_Chi_Minh")
TODAY = datetime.now(TZ).date().strftime("%Y-%m-%d")

EPG_PROXY_URL = os.environ.get("EPG_PROXY_URL")
EPG_PROXY_TOKEN = os.environ.get("EPG_PROXY_TOKEN")

HEADERS = {"User-Agent": "Mozilla/5.0 (EPG-Generator)"}

def proxy_fetch(target_url):
    if EPG_PROXY_URL:
        q = {"url": target_url}
        prox = EPG_PROXY_URL.rstrip("/") + "?" + urllib.parse.urlencode(q)
        headers = HEADERS.copy()
        if EPG_PROXY_TOKEN:
            headers["x-epg-token"] = EPG_PROXY_TOKEN
        try:
            r = requests.get(prox, headers=headers, timeout=25)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print("  ! proxy fetch error:", e)
            return None
    else:
        try:
            r = requests.get(target_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print("  ! direct fetch error:", e)
            return None

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
            chans.append({"id": parts[0], "url": parts[1], "display": parts[2] if len(parts) > 2 else parts[0]})
    return chans

def parse_vtv_html(html, channel_id):
    out = []
    soup = BeautifulSoup(html, "html.parser")
    for box in soup.select(".boxLichChuongTrinh"):
        h2 = box.select_one("h2")
        if not h2:
            continue
        if channel_id.lower() in h2.get_text(strip=True).lower():
            for li in box.select("li"):
                t_el = li.select_one(".time")
                p_el = li.select_one(".title")
                if t_el and p_el:
                    out.append({"time": t_el.get_text(strip=True), "title": p_el.get_text(strip=True)})
    return out

def parse_sctv_html(html, channel_id):
    out = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for block in soup.select(".schedule__content"):
        title_el = block.select_one(".schedule__title")
        if not title_el:
            continue
        if channel_id.lower() in title_el.get_text(strip=True).lower():
            for row in block.select(".schedule__item"):
                t = row.select_one(".schedule__time")
                p = row.select_one(".schedule__name")
                if t and p:
                    out.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    return out

def parse_vtvcab_html(html, channel_id):
    out = []
    soup = BeautifulSoup(html, "html.parser")
    for div in soup.select(".list-channel"):
        name_el = div.select_one(".name-channel")
        if name_el and channel_id.lower().replace("on ", "") in name_el.get_text(strip=True).lower():
            for row in div.select(".row-program"):
                t = row.select_one(".time")
                p = row.select_one(".name-program")
                if t and p:
                    out.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    return out

def generic_regex(html, channel_id):
    html_low = html.lower()
    idx = html_low.find(channel_id.lower())
    snippet = html
    if idx != -1:
        snippet = html[max(0, idx-2000): idx+8000]
    items = []
    for m in re.finditer(r'([01]?\d|2[0-3])[:.][0-5]\d\s*[-–—:]?\s*([^\n<]{3,200})', snippet):
        t = m.group(1).replace('.', ':')
        tt = m.group(2).strip()
        items.append({"time": t, "title": tt})
    seen = set()
    out = []
    for it in items:
        key = (it["time"], it["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def fetch_schedule(ch):
    txt = proxy_fetch(ch["url"])
    if not txt:
        return []
    if "vtv.vn" in ch["url"]:
        res = parse_vtv_html(txt, ch["id"])
        if res:
            return res
    if "sctv.com.vn" in ch["url"]:
        res = parse_sctv_html(txt, ch["id"])
        if res:
            return res
    if "vtvcab" in ch["url"] or "dichvu.vtvcab" in ch["url"]:
        res = parse_vtvcab_html(txt, ch["id"])
        if res:
            return res
    # fallback
    return generic_regex(txt, ch["id"])

def build_epg(channels):
    tv = ET.Element("tv", attrib={"generator-info-name":"github-epg-generator"})
    for ch in channels:
        c = ET.SubElement(tv, "channel", id=ch["id"])
        dn = ET.SubElement(c, "display-name")
        dn.text = ch["display"]
    for ch in channels:
        print("=> Lấy lịch cho:", ch["id"])
        sched = fetch_schedule(ch)
        print("   - items found:", len(sched))
        prev_dt = None
        for i, it in enumerate(sched):
            m = re.search(r'([01]?\d|2[0-3])[:.][0-5]\d', it["time"])
            if not m:
                continue
            hhmm = m.group(0).replace('.', ':')
            hh, mm = map(int, hhmm.split(":"))
            start = datetime.fromordinal(1)  # dummy
            try:
                start = datetime(year=int(TODAY.split("-")[0]), month=int(TODAY.split("-")[1]), day=int(TODAY.split("-")[2]),
                                  hour=hh, minute=mm, tzinfo=TZ)
            except Exception:
                continue
            if prev_dt and start <= prev_dt:
                start = start + timedelta(days=1)
            # stop
            stop = None
            if i+1 < len(sched):
                m2 = re.search(r'([01]?\d|2[0-3])[:.][0-5]\d', sched[i+1]["time"])
                if m2:
                    hh2, mm2 = map(int, m2.group(0).replace('.',':').split(":"))
                    stop = datetime(year=int(TODAY.split("-")[0]), month=int(TODAY.split("-")[1]), day=int(TODAY.split("-")[2]),
                                    hour=hh2, minute=mm2, tzinfo=TZ)
                    if stop <= start:
                        stop = stop + timedelta(days=1)
            if not stop:
                stop = start + timedelta(minutes=30)
            prog = ET.SubElement(tv, "programme", {
                "start": start.strftime("%Y%m%d%H%M%S") + " +0700",
                "stop": stop.strftime("%Y%m%d%H%M%S") + " +0700",
                "channel": ch["id"]
            })
            t = ET.SubElement(prog, "title", {"lang":"vi"})
            t.text = it.get("title", "")
            d = ET.SubElement(prog, "desc", {"lang":"vi"})
            d.text = ""
            prev_dt = start
    return tv

def write_xml(tv_elem, out="docs/epg.xml"):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tree = ET.ElementTree(tv_elem)
    tree.write(out, encoding="utf-8", xml_declaration=True)
    print("-> written", out)

def main():
    chans = read_channels()
    if not chans:
        print("No channels in channels.txt", file=sys.stderr)
        return
    tv = build_epg(chans)
    write_xml(tv)

if __name__ == "__main__":
    main()
