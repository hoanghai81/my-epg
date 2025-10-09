import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import os

# Lấy múi giờ Hà Nội
tz = pytz.timezone("Asia/Ho_Chi_Minh")
today = datetime.now(tz).date()
tomorrow = today + timedelta(days=1)

print("=== BẮT ĐẦU SINH EPG ===")

# Đọc danh sách kênh
channels = []
with open("channels.txt", "r", encoding="utf-8") as f:
    for line in f:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 2:
                channels.append((parts[0], parts[1]))

all_programs = []
for ch_id, source in channels:
    print(f"=> Lấy lịch cho: {ch_id}")
    try:
        r = requests.get(source, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  [!] Lỗi tải nguồn {source}: {e}")
        continue

    try:
        xml_data = r.text
        root = ET.fromstring(xml_data)
        count = 0
        for prog in root.findall("programme"):
            channel = prog.get("channel", "").lower()
            if ch_id.lower() in channel:
                start = prog.get("start")
                start_dt = datetime.strptime(start[:8], "%Y%m%d").date()
                if start_dt in (today, tomorrow):
                    all_programs.append(prog)
                    count += 1
        print(f"   - items found: {count}")
    except Exception as e:
        print(f"  [!] Lỗi parse XML: {e}")

# Tạo file epg.xml
out_dir = "docs"
os.makedirs(out_dir, exist_ok=True)
out_file = os.path.join(out_dir, "epg.xml")

epg_root = ET.Element("tv")
for p in all_programs:
    epg_root.append(p)
tree = ET.ElementTree(epg_root)
tree.write(out_file, encoding="utf-8", xml_declaration=True)

print(f"-> written {out_file} ({len(all_programs)} chương trình)")
print("=== HOÀN TẤT ===")
