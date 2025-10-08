import requests
from bs4 import BeautifulSoup
from datetime import datetime
from dateutil import parser
import xml.etree.ElementTree as ET

# --- cấu hình ---
PROXY = "https://epg-proxy.haikoc.workers.dev/?url="
TODAY = datetime.now().strftime("%Y-%m-%d")

CHANNELS = [
    {"id": "VTV1", "url": "https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv1&date=" + TODAY, "name": "VTV1 HD"},
    {"id": "VTV2", "url": "https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv2&date=" + TODAY, "name": "VTV2 HD"},
    {"id": "SCTV1", "url": "https://www.sctv.com.vn/lich-phat-song", "name": "SCTV1"},
    {"id": "SCTV2", "url": "https://www.sctv.com.vn/lich-phat-song", "name": "SCTV2"},
    {"id": "ONSports", "url": "https://dichvu.vtvcab.vn/lich-phat-song", "name": "ON Sports"},
    {"id": "ONVieGiaiTri", "url": "https://dichvu.vtvcab.vn/lich-phat-song", "name": "ON Vie Giải Trí"},
]

def fetch(url):
    full_url = PROXY + requests.utils.quote(url, safe='')
    resp = requests.get(full_url, timeout=20)
    resp.raise_for_status()
    return resp.text

def parse_vtv(data):
    """Parse JSON từ API VTV"""
    try:
        import json
        data = json.loads(data)
        items = []
        for p in data.get("data", []):
            start = parser.parse(p["start_time"])
            title = p["name"].strip()
            items.append({"start": start, "title": title})
        return items
    except Exception as e:
        print(f"  [!] Parse lỗi VTV: {e}")
        return []

def parse_sctv(html, channel_name):
    """Parse lịch từ trang SCTV"""
    soup = BeautifulSoup(html, "lxml")
    ch_div = soup.find("div", {"id": channel_name.lower()})
    items = []
    if not ch_div:
        return items
    for row in ch_div.find_all("div", class_="item"):
        time_tag = row.find("div", class_="time")
        title_tag = row.find("div", class_="title")
        if time_tag and title_tag:
            t = time_tag.text.strip()
            title = title_tag.text.strip()
            start = parser.parse(f"{TODAY} {t}")
            items.append({"start": start, "title": title})
    return items

def parse_vtvcab(html, channel_name):
    """Parse lịch từ trang VTVcab"""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_="card")
    items = []
    for c in cards:
        name = c.find("h4")
        if name and channel_name.lower() in name.text.lower():
            for li in c.find_all("li"):
                parts = li.text.strip().split(" ", 1)
                if len(parts) == 2:
                    t, title = parts
                    try:
                        start = parser.parse(f"{TODAY} {t}")
                        items.append({"start": start, "title": title.strip()})
                    except:
                        continue
    return items

def main():
    print(f"=> Lấy EPG cho ngày {TODAY}")
    root = ET.Element("tv")

    for ch in CHANNELS:
        print(f"=> Lấy lịch cho: {ch['id']}")
        items = []

        try:
            html = fetch(ch["url"])
            if "vtvapi" in ch["url"]:
                items = parse_vtv(html)
            elif "sctv" in ch["url"]:
                items = parse_sctv(html, ch["id"])
            elif "vtvcab" in ch["url"]:
                items = parse_vtvcab(html, ch["name"])
        except Exception as e:
            print(f"  [!] Lỗi lấy {ch['id']}: {e}")

        print(f"   - items found: {len(items)}")
        if len(items):
            ch_el = ET.SubElement(root, "channel", id=ch["id"])
            ET.SubElement(ch_el, "display-name").text = ch["name"]
            for i in items:
                p_el = ET.SubElement(
                    root,
                    "programme",
                    start=i["start"].strftime("%Y%m%d%H%M%S") + " +0700",
                    stop=(i["start"]).strftime("%Y%m%d%H%M%S") + " +0700",
                    channel=ch["id"],
                )
                ET.SubElement(p_el, "title").text = i["title"]

    ET.indent(root)
    ET.ElementTree(root).write("docs/epg.xml", encoding="utf-8", xml_declaration=True)
    print("-> written docs/epg.xml")

if __name__ == "__main__":
    main()
