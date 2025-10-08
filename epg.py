import requests, datetime, pytz
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element, SubElement, ElementTree

# ========== CONFIG ==========
OUTPUT_FILE = "docs/epg.xml"
CHANNELS = {
    "VTV1": "https://vtv.vn/lich-phat-song.htm",
    "VTV2": "https://vtv.vn/lich-phat-song.htm",
    "SCTV1": "https://www.sctv.com.vn/lich-phat-song",
    "SCTV2": "https://www.sctv.com.vn/lich-phat-song",
    "ON Sports": "https://dichvu.vtvcab.vn/lich-phat-song",
    "ON Vie Giải Trí": "https://dichvu.vtvcab.vn/lich-phat-song",
}
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
TODAY = datetime.datetime.now(TIMEZONE).strftime("%Y-%m-%d")

# ========== XML INIT ==========
tv = Element("tv")
def add_programme(channel, start, stop, title, desc=""):
    p = SubElement(tv, "programme", {
        "start": start,
        "stop": stop,
        "channel": channel
    })
    SubElement(p, "title", {"lang": "vi"}).text = title
    if desc:
        SubElement(p, "desc", {"lang": "vi"}).text = desc

# ========== FETCHERS ==========

def fetch_vtv(channel):
    print(f"=> Lấy VTV: {channel}")
    r = requests.get(CHANNELS[channel], timeout=10)
    soup = BeautifulSoup(r.text, "lxml")
    lst = soup.select(".list-item-day .box-item")
    count = 0
    for item in lst:
        ch = item.select_one(".name-chanel")
        if ch and channel.lower() in ch.text.lower():
            title = item.select_one(".name-show").get_text(strip=True)
            time = item.select_one(".time").get_text(strip=True)
            h, m = time.split(":")
            start = datetime.datetime.now(TIMEZONE).replace(hour=int(h), minute=int(m), second=0)
            stop = start + datetime.timedelta(minutes=30)
            fmt = "%Y%m%d%H%M%S +0700"
            add_programme(channel, start.strftime(fmt), stop.strftime(fmt), title)
            count += 1
    print(f"   - items found: {count}")

def fetch_sctv(channel):
    print(f"=> Lấy SCTV: {channel}")
    r = requests.get(CHANNELS[channel], timeout=10)
    soup = BeautifulSoup(r.text, "lxml")
    lst = soup.select(".channel-item")
    count = 0
    for c in lst:
        name = c.select_one(".channel-name")
        if not name or channel.lower() not in name.text.lower():
            continue
        for prog in c.select(".schedule-item"):
            time = prog.select_one(".schedule-time").get_text(strip=True)
            title = prog.select_one(".schedule-name").get_text(strip=True)
            h, m = time.split(":")
            start = datetime.datetime.now(TIMEZONE).replace(hour=int(h), minute=int(m), second=0)
            stop = start + datetime.timedelta(minutes=30)
            fmt = "%Y%m%d%H%M%S +0700"
            add_programme(channel, start.strftime(fmt), stop.strftime(fmt), title)
            count += 1
    print(f"   - items found: {count}")

def fetch_vtvcab(channel):
    print(f"=> Lấy VTVCab: {channel}")
    r = requests.get(CHANNELS[channel], timeout=10)
    soup = BeautifulSoup(r.text, "lxml")
    lst = soup.select(".tab-content .schedule-item")
    count = 0
    for prog in lst:
        title = prog.select_one(".name-show")
        if not title: 
            continue
        time = prog.select_one(".time")
        if not time: 
            continue
        title = title.get_text(strip=True)
        time = time.get_text(strip=True)
        h, m = time.split(":")
        start = datetime.datetime.now(TIMEZONE).replace(hour=int(h), minute=int(m), second=0)
        stop = start + datetime.timedelta(minutes=30)
        fmt = "%Y%m%d%H%M%S +0700"
        add_programme(channel, start.strftime(fmt), stop.strftime(fmt), title)
        count += 1
    print(f"   - items found: {count}")

# ========== MAIN ==========
print(f"=> Lấy EPG cho ngày {TODAY}")

for ch in CHANNELS:
    if "VTV" in ch:
        fetch_vtv(ch)
    elif "SCTV" in ch:
        fetch_sctv(ch)
    else:
        fetch_vtvcab(ch)

ElementTree(tv).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
print(f"-> written {OUTPUT_FILE}")
    
