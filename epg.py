import requests
import datetime
import dateutil.parser
import xml.etree.ElementTree as ET

# ====== CẤU HÌNH ======
WORKER = "https://epg-proxy.haikoc.workers.dev/"
TODAY = datetime.date.today().strftime("%Y-%m-%d")
OUTPUT = "docs/epg.xml"

CHANNELS = {
    "VTV1": "https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv1&date=" + TODAY,
    "VTV2": "https://vtvapi.vtv.vn/api/v1/schedules?type=channel&code=vtv2&date=" + TODAY,
    "SCTV1": "https://sctvonline.vn/lich-phat-song/kenh-sctv1",
    "SCTV2": "https://sctvonline.vn/lich-phat-song/kenh-sctv2",
    "ON Sports": "https://onsports.vn/lich-phat-song",
    "ON Vie Giải Trí": "https://vieon.vn/lich-chieu.html"
}

# ====== HÀM HỖ TRỢ ======
def get_url(url):
    try:
        full = f"{WORKER}?url={url}"
        r = requests.get(full, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  [!] Lỗi tải {url}: {e}")
        return None

def write_epg(epg_data):
    tv = ET.Element("tv")
    for ch_name, programs in epg_data.items():
        ch_elem = ET.SubElement(tv, "channel", id=ch_name)
        ET.SubElement(ch_elem, "display-name").text = ch_name
        for p in programs:
            prog = ET.SubElement(
                tv,
                "programme",
                start=p["start"],
                stop=p["stop"],
                channel=ch_name
            )
            ET.SubElement(prog, "title").text = p["title"]
            if "desc" in p:
                ET.SubElement(prog, "desc").text = p["desc"]
    ET.ElementTree(tv).write(OUTPUT, encoding="utf-8", xml_declaration=True)
    print(f"-> written {OUTPUT}")

# ====== LẤY DỮ LIỆU ======
def get_vtv_schedule(channel, url):
    html = get_url(url)
    if not html: return []
    try:
        data = requests.utils.json.loads(html)
        items = []
        for item in data.get("data", []):
            start = dateutil.parser.parse(item["start_time"]).strftime("%Y%m%d%H%M%S +0700")
            end = dateutil.parser.parse(item["end_time"]).strftime("%Y%m%d%H%M%S +0700")
            items.append({
                "start": start,
                "stop": end,
                "title": item.get("name", "Chưa rõ"),
                "desc": item.get("description", "")
            })
        print(f"   - items found: {len(items)}")
        return items
    except Exception as e:
        print(f"  [!] Parse lỗi {channel}: {e}")
        return []

def main():
    print(f"=> Lấy EPG cho ngày {TODAY}")
    all_epg = {}
    for ch, url in CHANNELS.items():
        print(f"=> Lấy lịch cho: {ch}")
        if "vtvapi" in url:
            items = get_vtv_schedule(ch, url)
        else:
            items = []
        all_epg[ch] = items
    write_epg(all_epg)

if __name__ == "__main__":
    main()
