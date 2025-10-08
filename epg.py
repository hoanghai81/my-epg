#!/usr/bin/env python3
# epg.py - simple EPG generator (reads channels.txt and writes docs/epg.xml)

import re, os, requests, datetime, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from dateutil import tz

TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')

def read_channels(path='channels.txt'):
    channels = []
    with open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith('#'):
                continue
            parts = [p.strip() for p in ln.split('|')]
            if len(parts) < 2:
                print("Skip invalid line:", ln)
                continue
            cid = parts[0]
            src = parts[1]
            disp = parts[2] if len(parts) > 2 and parts[2] else cid
            channels.append({'id': cid, 'source': src, 'display': disp})
    return channels

def fetch_html(url):
    headers = {'User-Agent': 'Mozilla/5.0 (EPG-Generator)'}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print("Fetch error:", url, e)
        return None

def find_time_title_pairs_from_soup(soup):
    # Heuristic: find time strings then nearby text for title
    pairs = []
    # First try searching inside elements likely to contain schedule
    candidates = soup.find_all(class_=re.compile(r'(lich|schedule|time|tv-list|program|list-item|item)', re.I))
    for c in candidates:
        for text in c.find_all(string=TIME_RE):
            m = TIME_RE.search(text)
            if not m: 
                continue
            timestr = m.group(0).replace('.', ':')
            # find title near this time node
            title = ''
            # look for next elements that have significant text
            parent = text.parent
            # check parent for title-like tags
            nxt = parent.find_next_sibling()
            if nxt:
                title = nxt.get_text(strip=True)
            if not title:
                # search within parent for anything that looks like a program title
                maybe = parent.find(class_=re.compile(r'(title|name|ten|program|content)', re.I))
                if maybe:
                    title = maybe.get_text(strip=True)
            if not title:
                # fallback: immediate next text node in document
                n = text.find_next(string=True)
                if n and n.strip() and not TIME_RE.search(n):
                    title = n.strip()
            pairs.append({'time': timestr, 'title': title})
    # If none found, fallback to scanning whole doc for times
    if not pairs:
        for text in soup.find_all(string=TIME_RE):
            m = TIME_RE.search(text)
            if not m: 
                continue
            timestr = m.group(0).replace('.', ':')
            # try simple heuristics for title
            title = ''
            n = text.find_next(string=True)
            if n and n.strip() and not TIME_RE.search(n):
                title = n.strip()
            pairs.append({'time': timestr, 'title': title})
    # dedupe by (time,title) appearance order
    seen = set()
    out = []
    for p in pairs:
        key = (p['time'], p['title'])
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

def parse_page_generic(url, html):
    soup = BeautifulSoup(html, 'lxml')
    pairs = find_time_title_pairs_from_soup(soup)
    return pairs

def build_programs(pairs, tzinfo):
    progs = []
    today = datetime.date.today()
    last_dt = None
    for p in pairs:
        t = p['time']
        try:
            hh, mm = [int(x) for x in t.split(':')]
        except:
            continue
        dt = datetime.datetime.combine(today, datetime.time(hh, mm, tzinfo=tzinfo))
        if last_dt and dt <= last_dt:
            # passed midnight -> next day
            dt = dt + datetime.timedelta(days=1)
            today = dt.date()
        progs.append({'start': dt, 'title': p['title']})
        last_dt = dt
    # compute stops
    for i in range(len(progs)):
        start = progs[i]['start']
        if i+1 < len(progs):
            stop = progs[i+1]['start']
        else:
            stop = start + datetime.timedelta(minutes=30)
        progs[i]['stop'] = stop
    return progs

def generate_xml(channels_programs, outpath='docs/epg.xml'):
    tv = ET.Element('tv', {'generator-info-name': 'github-epg-generator'})
    for ch in channels_programs:
        ch_el = ET.SubElement(tv, 'channel', {'id': ch['id']})
        dn = ET.SubElement(ch_el, 'display-name')
        dn.text = ch['display']
    for ch in channels_programs:
        for p in ch['programs']:
            prog = ET.SubElement(tv, 'programme', {
                'start': p['start'].strftime('%Y%m%d%H%M%S') + ' +0700',
                'stop':  p['stop'].strftime('%Y%m%d%H%M%S') + ' +0700',
                'channel': ch['id']
            })
            t = ET.SubElement(prog, 'title', {'lang': 'vi'})
            t.text = p['title'] or ''
            d = ET.SubElement(prog, 'desc', {'lang': 'vi'})
            d.text = ''
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    tree = ET.ElementTree(tv)
    tree.write(outpath, encoding='utf-8', xml_declaration=True)
    print("Written", outpath)

def main():
    channels = read_channels()
    tzinfo = datetime.timezone(datetime.timedelta(hours=7))  # Asia/Bangkok +0700
    result = []
    for ch in channels:
        print("=> Processing", ch['id'], ch['source'])
        html = fetch_html(ch['source'])
        if not html:
            print("   - cannot fetch:", ch['source'])
            result.append({'id': ch['id'], 'display': ch['display'], 'programs': []})
            continue
        pairs = parse_page_generic(ch['source'], html)
        progs = build_programs(pairs, tzinfo)
        print("   - found", len(progs), "program items (heuristic)")
        result.append({'id': ch['id'], 'display': ch['display'], 'programs': progs})
    generate_xml(result, outpath='docs/epg.xml')

if __name__ == '__main__':
    main()
          
