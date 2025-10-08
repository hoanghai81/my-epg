import requests, datetime, pytz, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

tz = pytz.timezone("Asia/Ho_Chi_Minh")
today = datetime.datetime.now(tz).strftime("%Y-%m-%d")

def fetch_vtv(channel):
    ids = {"VTV1": "1", "VTV2": "2"}
    cid = ids.get(channel)
    if not cid:
        return []
    url = f"https://vtv.vn/truyen-hinh-truc-tuyen/lich-phat-song.htm?channel={cid}"
    try:
        r = requests.get(f"https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv{cid}&date={today}")
        data = r.json().get("data", [])
        progs = []
        for item in data:
            start = f"{today} {item.get('start_time','00:00')}"
            title = item.get("name", "").strip()
            progs.append({"start": start, "title": title})
        return progs
    except Exception as e:
        print(f"  [!] Lỗi lấy {channel}: {e}")
        return []

def fetch_sctv(channel):
    try:
        r = requests.get("https://www.sctv.com.vn/lich-phat-song")
        soup = BeautifulSoup(r.text, "lxml")
        ch_blocks = soup.select(".tab-content .tab-pane")
        progs = []
        for block in ch_blocks:
            name = block.get("id", "").strip().upper()
            if channel.lower() in name.lower():
                items = block.select("li")
                for it in items:
                    time = it.select_one("span.time").get_text(strip=True)
                    title = it.select_one("span.name").get_text(strip=True)
                    progs.append({"start": f"{today} {time}", "title": title})
        return progs
    except Exception as e:
        print(f"  [!] Lỗi lấy {channel}: {e}")
        return []

def fetch_vtvcab(channel):
    ids = {
        "ON Sports": "onsports-hd",
        "ON Vie Giải Trí": "on-vie-giai-tri",
    }
    cid = ids.get(channel)
    if not cid:
        return []
    try:
        url = f"https://dichvu.vtvcab.vn/ajax/get_schedule?channel={cid}&date={today}"
        r = requests.get(url)
        data = r.json()
        progs = []
        for item in data:
            start = f"{today} {item.get('time','00:00')}"
            title = item.get("title", "").strip()
            progs.append({"start": start, "title": title})
        return progs
    except Exception as e:
        print(f"  [!] Lỗi lấy {channel}: {e}")
        return []

def create_epg(channels):
    tv = ET.Element("tv", attrib={"generator-info-name": "GitHub-EPG"})
    for ch_name, source, display_name in channels:
        print(f"=> Lấy lịch cho: {ch_name}")
        if "vtv" in source:
            progs = fetch_vtv(ch_name)
        elif "sctv" in source:
            progs = fetch_sctv(ch_name)
        elif "vtvcab" in source:
            progs = fetch_vtvcab(ch_name)
        else:
            progs = []
        print(f"   - items found: {len(progs)}")

        ch_elem = ET.SubElement(tv, "channel", id=ch_name)
        ET.SubElement(ch_elem, "display-name").text = display_name

        for p in progs:
            prog_elem = ET.SubElement(tv, "programme", start=p["start"].replace("-", "").replace(":", "").replace(" ", "") + " +0700", channel=ch_name)
            ET.SubElement(prog_elem, "title").text = p["title"]
    tree = ET.ElementTree(tv)
    tree.write("docs/epg.xml", encoding="utf-8", xml_declaration=True)
    print("-> written docs/epg.xml")

def read_channels():
    channels = []
    with open("channels.txt", encoding="utf-8") as f:
        for line in f:
            if "|" in line and not line.strip().startswith("#"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    channels.append(parts[:3])
    return channels

if __name__ == "__main__":
    channels = read_channels()
    create_epg(channels)
