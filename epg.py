import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz, json, re, dateutil.parser

# Proxy worker Cloudflare của anh
PROXY = "https://epg-proxy.haikoc.workers.dev"

# Danh sách kênh và nguồn
CHANNELS = [
    ("VTV1", "https://vtv.vn/lich-phat-song.htm", "VTV1 HD"),
    ("VTV2", "https://vtv.vn/lich-phat-song.htm", "VTV2 HD"),
    ("SCTV1", "https://www.sctv.com.vn/lich-phat-song", "SCTV1"),
    ("SCTV2", "https://www.sctv.com.vn/lich-phat-song", "SCTV2"),
    ("ONSports", "https://dichvu.vtvcab.vn/lich-phat-song", "ON Sports"),
    ("ONVieGiaiTri", "https://dichvu.vtvcab.vn/lich-phat-song", "ON Vie Giải Trí")
]

today = datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%Y-%m-%d")
print(f"=> Lấy EPG cho ngày {today}")

def fetch(url):
    try:
        res = requests.get(f"{PROXY}/?url={url}", timeout=20)
        print(f"    [fetch] proxied {url} -> status {res.status_code}, content-type: {res.headers.get('content-type')}, length={len(res.text)}")
        return res.text
    except Exception as e:
        print("    [fetch error]", e)
        return ""

def parse_vtv(code):
    url = f"https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code={code.lower()}&date={today}"
    html = fetch(url)
    try:
        data = json.loads(html)
        items = []
        for i in data.get("data", []):
            title = i["title"].strip()
            start = dateutil.parser.parse(i["start_time"])
            stop = dateutil.parser.parse(i["end_time"])
            items.append((start, stop, title))
        return items
    except Exception as e:
        print(f"  [!] Parse lỗi VTV: {e}")
        html = fetch("https://vtv.vn/lich-phat-song.htm")
        soup = BeautifulSoup(html, "lxml")
        blocks = soup.select(".list-item")
        items = []
        for b in blocks:
            ch = b.select_one(".name")
            if not ch or code not in ch.text: continue
            time = b.select_one(".time")
            title = b.select_one(".title")
            if time and title:
                h, m = map(int, time.text.strip().split(":"))
                start = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
                stop = start
                items.append((start, stop, title.text.strip()))
        return items

def parse_sctv(code):
    html = fetch("https://www.sctv.com.vn/lich-phat-song")
    soup = BeautifulSoup(html, "lxml")
    items = []
    chan = soup.find("div", {"class": "channel-name"}, string=re.compile(code, re.I))
    if chan:
        parent = chan.find_parent("div", {"class": "channel"})
        if parent:
            for li in parent.select("li"):
                time = li.find("span", {"class": "time"})
                title = li.find("span", {"class": "name"})
                if time and title:
                    h, m = map(int, time.text.strip().split(":"))
                    start = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
                    stop = start
                    items.append((start, stop, title.text.strip()))
    return items

def parse_vtvcab(code):
    html = fetch("https://dichvu.vtvcab.vn/lich-phat-song")
    soup = BeautifulSoup(html, "lxml")
    items = []
    blocks = soup.select(".schedule-item")
    for b in blocks:
        ch = b.select_one(".channel-name")
        if not ch or code.lower().replace(" ", "") not in ch.text.lower().replace(" ", ""):
            continue
        for row in b.select(".program-item"):
            time = row.select_one(".time")
            title = row.select_one(".title")
            if time and title:
                h, m = map(int, time.text.strip().split(":"))
                start = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
                stop = start
                items.append((start, stop, title.text.strip()))
    return items

def make_epg(channels):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="my-epg">']
    for code, src, name in channels:
        print(f"=> Lấy lịch cho: {code}")
        if "vtv.vn" in src:
            items = parse_vtv(code)
        elif "sctv.com.vn" in src:
            items = parse_sctv(code)
        elif "vtvcab.vn" in src:
            items = parse_vtvcab(code)
        else:
            items = []

        print(f"   - items found: {len(items)}")
        xml.append(f'<channel id="{code}"><display-name>{name}</display-name></channel>')
        for (start, stop, title) in items:
            s = start.strftime("%Y%m%d%H%M%S +0700")
            e = stop.strftime("%Y%m%d%H%M%S +0700")
            xml.append(f'<programme start="{s}" stop="{e}" channel="{code}"><title>{title}</title></programme>')
    xml.append("</tv>")
    open("docs/epg.xml", "w", encoding="utf-8").write("\n".join(xml))
    print("-> written docs/epg.xml")

make_epg(CHANNELS)
                    
