import requests
import gzip
import xml.etree.ElementTree as ET

URL = "https://vnepg.site/epgu.xml"
OUTPUT = "docs/tvg_ids.txt"

print("=== BẮT ĐẦU TẢI EPG ===")
try:
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    print(f"Tải thành công ({len(response.content)} bytes)")
except Exception as e:
    print(f"[!] Lỗi tải file: {e}")
    exit(1)

print("=== GIẢI NÉN ===")
try:
    xml_data = gzip.decompress(response.content).decode("utf-8")
except Exception as e:
    print(f"[!] Lỗi giải nén: {e}")
    exit(1)

print("=== PHÂN TÍCH XML ===")
try:
    root = ET.fromstring(xml_data)
    ids = set()
    for ch in root.findall("channel"):
        tvg_id = ch.get("id")
        if tvg_id:
            ids.add(tvg_id.strip())
    print(f"✅ Lấy được {len(ids)} tvg-id khác nhau")
except Exception as e:
    print(f"[!] Lỗi phân tích XML: {e}")
    exit(1)

print("=== GHI FILE ===")
with open(OUTPUT, "w", encoding="utf-8") as f:
    for i in sorted(ids):
        f.write(i + "\n")

print(f"✅ Đã ghi danh sách vào {OUTPUT}")
      
