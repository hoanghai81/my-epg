import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

# ==========================
# CẤU HÌNH
# ==========================
EPG_SOURCE = "https://lichphatsong.site/epg.xml"
TARGET_CHANNEL = "VTV1"
OUTPUT_FILE = "docs/epg.xml"
LOG_FILE = "epg.log"

# ==========================
# HÀM HỖ TRỢ
# ==========================
def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat(sep=' ', timespec='seconds')}] {msg}\n")

def get_target_dates():
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    return [today.strftime("%Y%m%d"), tomorrow.strftime("%Y%m%d")]

# ==========================
# LẤY DỮ LIỆU EPG
# ==========================
def fetch_epg():
    log(f"Đang tải EPG từ {EPG_SOURCE}")
    try:
        resp = requests.get(EPG_SOURCE, timeout=30)
        resp.raise_for_status()
        log(f"Đã tải thành công ({len(resp.content)} bytes)")
        return resp.content
    except Exception as e:
        log(f"[!] Lỗi khi tải EPG: {e}")
        return None

# ==========================
# LỌC VÀ GHI FILE
# ==========================
def filter_epg(epg_data):
    try:
        root = ET.fromstring(epg_data)
        out_root = ET.Element("tv")

        programmes = 0
        dates = get_target_dates()

        for prog in root.findall("programme"):
            ch = prog.attrib.get("channel", "").strip()
            start = prog.attrib.get("start", "")
            if ch == TARGET_CHANNEL and start[:8] in dates:
                out_root.append(prog)
                programmes += 1

        # thêm channel info
        for ch in root.findall("channel"):
            if ch.attrib.get("id") == TARGET_CHANNEL:
                out_root.insert(0, ch)
                break

        tree = ET.ElementTree(out_root)
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

        log(f"✅ Đã lưu {OUTPUT_FILE} — {programmes} chương trình ({TARGET_CHANNEL})")
    except Exception as e:
        log(f"[!] Lỗi khi xử lý EPG: {e}")

# ==========================
# MAIN
# ==========================
if __name__ == "__main__":
    log("=== BẮT ĐẦU SINH EPG ===")
    data = fetch_epg()
    if data:
        filter_epg(data)
    log("=== HOÀN TẤT ===\n")
    
