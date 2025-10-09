import requests, gzip, io, pytz
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import sys

# === Cấu hình cơ bản ===
EPG_SOURCE = "https://lichphatsong.site/schedule/epg.xml.gz"
OUTPUT_FILE = "docs/epg.xml"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

print("=== BẮT ĐẦU SINH EPG (2 ngày gần nhất) ===")

# === Đọc danh sách kênh ===
channels = []
try:
    with open("channels.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    channels.append({
                        "id": parts[0],
                        "url": parts[1],
                        "name": parts[2]
                    })
except FileNotFoundError:
    print("[!] Không tìm thấy file channels.txt")
    sys.exit(1)

# === Tải file EPG nén ===
try:
    print(f"=> Tải dữ liệu từ {EPG_SOURCE}")
    r = requests.get(EPG_SOURCE, timeout=60)
    r.raise_for_status()
    data = gzip.decompress(io.BytesIO(r.content).read())
    root = ET.fromstring(data)
except Exception as e:
    print(f"[!] Lỗi tải hoặc giải nén EPG: {e}")
    sys.exit(1)

# === Giới hạn thời gian lấy dữ liệu (2 ngày) ===
now = datetime.now(TIMEZONE)
end_time = now + timedelta(days=2)
print(f"=> Lọc chương trình từ {now.strftime('%d/%m %H:%M')} đến {end_time.strftime('%d/%m %H:%M')}")

# === Tạo XML đầu ra ===
epg = ET.Element("tv")
total_programmes = 0

for ch in channels:
    ch_id = ch["id"]
    ch_name = ch["name"]

    ch_elem = ET.SubElement(epg, "channel", id=ch_id)
    ET.SubElement(ch_elem, "display-name").text = ch_name

    # Lọc chương trình trong khoảng thời gian cần lấy
    progs = []
    for p in root.findall("programme"):
        if p.attrib.get("channel") != ch_id:
            continue
        start_str = p.attrib.get("start", "")[:14]
        try:
            start_dt = datetime.strptime(start_str, "%Y%m%d%H%M%S")
        except:
            continue
        start_dt = TIMEZONE.localize(start_dt)

        if now <= start_dt <= end_time:
            progs.append(p)

    print(f"=> {ch_name}: {len(progs)} chương trình")
    total_programmes += len(progs)
    for p in progs:
        epg.append(p)

# === Ghi file XML ===
tree = ET.ElementTree(epg)
ET.indent(tree, space="  ")
tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

print(f"\n✅ Đã ghi {OUTPUT_FILE}")
print(f"📺 Tổng cộng: {total_programmes} chương trình ({len(channels)} kênh)")
print("=== HOÀN TẤT ===")
    
