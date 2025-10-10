import requests
import gzip
import io
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz

OUTPUT = "docs/tvg_ids.txt"

def fetch_xml(url):
    """Tự động tải và đọc nội dung từ file XML hoặc XML.GZ"""
    print(f"=> Đang tải {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    if url.endswith(".gz"):
        print("   Đang giải nén (gzip)...")
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
            data = gz.read()
        return data.decode("utf-8", errors="ignore")
    else:
        return resp.text

def extract_tvg_ids(xml_content):
    """Trích xuất toàn bộ tvg-id duy nhất"""
    print("=> Đang phân tích EPG XML...")
    root = ET.fromstring(xml_content)
    ids = set()
    for ch in root.findall("channel"):
        cid = ch.attrib.get("id")
        if cid:
            ids.add(cid.strip())
    return sorted(ids)

def save_ids_to_file(ids, filename=OUTPUT):
    """Lưu danh sách ID ra file"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("# Danh sách tvg-id (tự động sinh)\n")
        f.write(f"# Cập nhật lúc: {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        for cid in ids:
            f.write(cid + "\n")
    print(f"=> Đã lưu {len(ids)} ID vào {filename}")

if __name__ == "__main__":
    sources = [
        "https://vnepg.site/epgu.xml",
        # có thể thêm: "https://example.com/epg.xml"
    ]

    all_ids = set()
    for src in sources:
        try:
            xml_data = fetch_xml(src)
            ids = extract_tvg_ids(xml_data)
            all_ids.update(ids)
            print(f"   + {len(ids)} ID từ {src}")
        except Exception as e:
            print(f"[!] Lỗi khi xử lý {src}: {e}")

    save_ids_to_file(sorted(all_ids))
    print("=== HOÀN TẤT ===")
