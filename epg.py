import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz, re

# Proxy Cloudflare Worker của anh
PROXY = "https://epg-proxy.haikoc.workers.dev"

# Danh sách kênh
CHANNELS = [
    ("VTV1", "https://vtv.vn/lich-phat-song.htm", "VTV1 HD"),
    ("VTV2", "https://vtv.vn/lich-phat-song.htm", "VTV2 HD"),
    ("SCTV1", "https://www.sctv.com.vn/lich-phat-song", "SCTV1"),
    ("SCTV2", "https://www.sctv.com.vn/lich-phat-song", "SCTV2"),
    ("ONSports", "https://dichvu.vtvcab.vn/lich-phat-song", "ON Sports"),
    ("ONVieGiaiTri", "https://dichvu.vtvcab.vn/lich-phat-song", "ON Vie Giải Trí"),
]

# Lấy giờ VN
tz = pytz.timezone("Asia/Ho_Chi_Minh")
today = datetime.now(tz).strftime("%Y-%m-%d")
print(f"=> Lấy EPG cho ngày {today}")

def fetch(url):
    try:
        proxied = f"{PROXY}/?url={url}"
        res = requests.get(proxied, timeout=30)
        print(f"    [fetch] {url} -> {res.status_code}, {res.headers.get('content-type')}")
        return res.text
    except Exception as e:
        print("    [fetch error]", e)
        return ""

def parse_vtv(channel):
    html = fetch("https://vtv.vn/lich-phat-song.htm")
    soup = BeautifulSoup(html, "lxml")
    items = []
    # Mỗi block chương trình theo kênh
    blocks = soup.select("div.content-box")
    for block in blocks:
        name = block.select_one("h3 a, h2 a")
        if not name or channel.lower() not in name.text.lower():
            continue
        for row in block.select("ul > li"):
            time_tag = row.select_one(".time")
            title_tag = row.select_one(".name")
            if time_tag and title_tag:
                try:
                    h, m = map(int, time_tag.text.strip().split(":"))
                    start = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
                    stop = start + timedelta(minutes=30)
                    title = title_tag.text.strip()
                    items.append((start, stop, title))
                except:
                    pass
    return items

def parse_sctv(channel):
    html = fetch("https://www.sctv.com.vn/lich-phat-song")
    soup = BeautifulSoup(html, "lxml")
    items = []
    blocks = soup.select("div.tab-content div.tab-pane")
    for b in blocks:
        name = b.get("id", "").lower()
        if channel.lower() not in name:
            continue
        for row in b.select("li"):
            time_tag = row.select_one(".time")
            title_tag = row.select_one(".name")
            if time_tag and title_tag:
                try:
                    h, m = map(int, time_tag.text.strip().split(":"))
                    start = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
                    stop = start + timedelta(minutes=30)
                    title = title_tag.text.strip()
                    items.append((start, stop, title))
                except:
                    pass
    return items

def parse_vtvcab(channel):
    html = fetch("https://dichvu.vtvcab.vn/lich-phat-song")
    soup = BeautifulSoup(html, "lxml")
    items = []
    # Tìm các block có tên kênh trùng
    for b in soup.select(".schedule-item"):
        name = b.select_one(".channel-name")
        if not name or channel.lower().replace(" ", "") not in name.text.lower().replace(" ", ""):
            continue
        for row in b.select(".program-item"):
            time_tag = row.select_one(".time")
            title_tag = row.select_one(".title")
            if time_tag and title_tag:
                try:
                    h, m = map(int, time_tag.text.strip().split(":"))
                    start = datetime.now(tz).replace(hour=h, minute=m, second=0, microsecond=0)
                    stop = start + timedelta(minutes=30)
                    title = title_tag.text.strip()
                    items.append((start, stop, title))
                except:
                    pass
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
        for start, stop, title in items:
            s = start.strftime("%Y%m%d%H%M%S +0700")
            e = stop.strftime("%Y%m%d%H%M%S +0700")
            xml.append(f'<programme start="{s}" stop="{e}" channel="{code}"><title>{title}</title></programme>')
    xml.append("</tv>")
    open("docs/epg.xml", "w", encoding="utf-8").write("\n".join(xml))
    print("-> written docs/epg.xml")

make_epg(CHANNELS)
