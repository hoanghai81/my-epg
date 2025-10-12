import os
import gzip
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz

# === CẤU HÌNH ===
CHANNEL_FILE = "channels.txt"
OUTPUT_FILE = "docs/epgtest.xml"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
DAYS = 2  # số ngày cần lấy

def log(msg):
    print(msg, flush=True)

def fetch_epg(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Nếu là .gz thì giải nén
        if url.endswith(".gz"):
            return gzip.decompress(response.content)
        else:
            # Nếu không có .gz vẫn thử parse XML
            return response.content

    except Exception as e:
        log(f"[!] Lỗi tải EPG từ {url}: {e}")
        return None

def parse_channels():
    channels = []
    with open(CHANNEL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if "|" in line and not line.strip().startswith("#"):
                parts = [x.strip() for x in line.split("|")]
                if len(parts) >= 3:
                    channels.append({
                        "id": parts[0],
                        "url": parts[1],
                        "name": parts[2],
                    })
    return channels

def write_epg(epg_channels, epg_programmes):
    root = ET.Element("tv", attrib={"generator-info-name": "my-epg test"})
    for ch in epg_channels:
        ch_elem = ET.SubElement(root, "channel", id=ch["id"])
        ET.SubElement(ch_elem, "display-name").text = ch["name"]
        if "logo" in ch and ch["logo"]:
            ET.SubElement(ch_elem, "icon", src=ch["logo"])

    for prog in epg_programmes:
        p_elem = ET.SubElement(
            root, "programme",
            start=prog["start"],
            stop=prog["stop"],
            channel=prog["channel"]
        )
        ET.SubElement(p_elem, "title").text = prog["title"]
        if prog.get("desc"):
            ET.SubElement(p_elem, "desc").text = prog["desc"]

    ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    log(f"-> written {OUTPUT_FILE} ({len(epg_programmes)} chương trình)")

def main():
    log("=== BẮT ĐẦU SINH EPG TEST ===")
    channels = parse_channels()
    log(f"=> Tổng số kênh yêu cầu: {len(channels)}")

    now = datetime.now(TIMEZONE)
    start_time = now
    end_time = now + timedelta(days=DAYS)
    log(f"=> Window: {start_time} -> {end_time}")

    all_channels = {}
    all_programmes = []

    for ch in channels:
        log(f"=> Đang lấy dữ liệu: {ch['name']} ({ch['id']})")
        data = fetch_epg(ch["url"])
        if not data:
            log(f"   - Lỗi hoặc không tải được dữ liệu từ {ch['url']}")
            continue

        try:
            root = ET.fromstring(data)
            found_progs = 0
            for p in root.findall("programme"):
                channel_id = p.attrib.get("channel", "")
                if channel_id.lower() != ch["id"].lower():
                    continue

                start_str = p.attrib.get("start", "")
                stop_str = p.attrib.get("stop", "")
                title_elem = p.find("title")
                desc_elem = p.find("desc")

                if start_str and stop_str and title_elem is not None:
                    found_progs += 1
                    all_programmes.append({
                        "start": start_str,
                        "stop": stop_str,
                        "channel": ch["id"],
                        "title": title_elem.text or "",
                        "desc": desc_elem.text if desc_elem is not None else ""
                    })

            log(f"   - matched {found_progs} programmes cho {ch['id']}")
            all_channels[ch["id"]] = ch

        except ET.ParseError:
            log(f"   - [!] Lỗi parse XML cho {ch['url']}")

    write_epg(list(all_channels.values()), all_programmes)

    log("=== SUMMARY ===")
    log(f"Total channels requested: {len(channels)}")
    for ch in channels:
        count = len([p for p in all_programmes if p['channel'] == ch['id']])
        log(f"- {ch['id']} ({ch['name']}): {count}")
    log(f"Total programmes: {len(all_programmes)}")

    log("=== HOÀN TẤT ===")

if __name__ == "__main__":
    main()
          
