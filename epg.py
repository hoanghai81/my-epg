import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import subprocess

CHANNELS_FILE = "channels.txt"
OUTPUT_FILE = "docs/epg.xml"

def parse_channels():
    channels = []
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                channels.append({
                    "id": parts[0],
                    "url": parts[1],
                    "name": parts[2]
                })
    return channels

def load_epg_from_url(url):
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return ET.fromstring(r.content)
    except Exception as e:
        print(f"[!] Lỗi tải EPG từ {url}: {e}")
        return None

def filter_programmes(root, channel_id):
    programmes = []
    for p in root.findall("programme"):
        if p.attrib.get("channel", "").lower() == channel_id.lower():
            programmes.append(p)
    return programmes

def generate_epg(channels):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "my-epg")

    total_count = 0

    for ch in channels:
        print(f"=> Xử lý kênh: {ch['name']} ({ch['id']})")

        epg_root = load_epg_from_url(ch["url"])
        if epg_root is None:
            continue

        programmes = filter_programmes(epg_root, ch["id"])
        print(f"   - Số chương trình lấy được: {len(programmes)}")

        # Thêm phần channel
        ch_elem = ET.SubElement(tv, "channel", id=ch["id"])
        disp = ET.SubElement(ch_elem, "display-name")
        disp.text = ch["name"]

        # Giữ lại chương trình trong 2 ngày (hôm nay + mai)
        today = datetime.now()
        end_time = today + timedelta(days=2)
        for p in programmes:
            start = p.attrib.get("start", "")
            if start and len(start) >= 8:
                try:
                    dt = datetime.strptime(start[:8], "%Y%m%d")
                    if dt <= end_time:
                        tv.append(p)
                        total_count += 1
                except:
                    continue

    ET.ElementTree(tv).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"-> written {OUTPUT_FILE} ({total_count} chương trình)")
    print("=== HOÀN TẤT ===")
    return total_count

def git_commit_and_push():
    try:
        subprocess.run(["git", "config", "--global", "user.email", "github-actions@github.com"])
        subprocess.run(["git", "config", "--global", "user.name", "github-actions"])
        subprocess.run(["git", "add", OUTPUT_FILE])
        subprocess.run(["git", "commit", "-m", f"update EPG {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"], check=False)
        subprocess.run(["git", "push"])
        print("✅ Đã commit + push lên GitHub")
    except Exception as e:
        print(f"[!] Lỗi git: {e}")

if __name__ == "__main__":
    print("=== BẮT ĐẦU SINH EPG ===")
    channels = parse_channels()
    count = generate_epg(channels)
    if count > 0:
        git_commit_and_push()
        
