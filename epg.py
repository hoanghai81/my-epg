import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Worker URL anh vừa tạo
WORKER = "https://epg1.haikoc.workers.dev"

# Danh sách kênh cần lấy
CHANNELS = [
    {"id": "VTV1", "name": "VTV1"},
    {"id": "VTV2", "name": "VTV2"},
    {"id": "SCTV1", "name": "SCTV1"},
    {"id": "ON Sports", "name": "ON Sports"}
]

def fetch_epg(channel):
    url = f"{WORKER}/?ch={channel['id']}"
    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"Lỗi lấy {channel['id']}: {e}")
        return None

def make_xml(channels):
    tv = ET.Element("tv", attrib={"generator-info-name": "epg-worker"})

    for ch in channels:
        c = ET.SubElement(tv, "channel", id=ch["id"])
        ET.SubElement(c, "display-name").text = ch["name"]

    now = datetime.now().strftime("%Y%m%d%H%M%S +0700")

    for ch in channels:
        data = fetch_epg(ch)
        if not data:
            continue

        # Ghi tạm nội dung dạng sample
        prog = ET.SubElement(tv, "programme", start=now, stop=now, channel=ch["id"])
        ET.SubElement(prog, "title").text = f"Lịch phát sóng {ch['name']}"
        ET.SubElement(prog, "desc").text = "Dữ liệu lấy qua Worker"

    return tv

def save_xml(tree, filename):
    ET.ElementTree(tree).write(filename, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    xml_tree = make_xml(CHANNELS)
    save_xml(xml_tree, "docs/epg.xml")
    print("✅ Đã tạo xong docs/epg.xml")
        
