import requests
import gzip
import io
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
import os
from colorama import Fore, Style, init

init(autoreset=True)

OUTPUT = "docs/tvg_ids.txt"
SOURCE_FILE = "nguonlps.txt"

def log_info(msg):
    print(Fore.CYAN + msg + Style.RESET_ALL)

def log_success(msg):
    print(Fore.GREEN + msg + Style.RESET_ALL)

def log_error(msg):
    print(Fore.RED + msg + Style.RESET_ALL)

def fetch_xml(url):
    """Tải và đọc nội dung XML hoặc XML.GZ"""
    log_info(f"=> Đang tải: {url}")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    if url.endswith(".gz"):
        log_info("   Đang giải nén (gzip)...")
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as gz:
            data = gz.read()
        return data.decode("utf-8", errors="ignore")
    else:
        return resp.text

def extract_tvg_ids(xml_content):
    """Trích xuất toàn bộ tvg-id"""
    root = ET.fromstring(xml_content)
    ids = set()
    for ch in root.findall("channel"):
        cid = ch.attrib.get("id")
        if cid:
            ids.add(cid.strip())
    return sorted(ids)

def save_ids_to_file(result_map, success_count, fail_count):
    """Ghi ra file docs/tvg_ids.txt"""
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("# Danh sách tvg-id từ các nguồn trong nguonlps.txt\n")
        f.write(f"# Cập nhật lúc: {datetime.now(pytz.timezone('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        total = 0
        for src, ids in result_map.items():
            f.write(f"## Nguồn: {src}\n")
            f.write(f"# Tổng cộng: {len(ids)} ID\n")
            for cid in ids:
                f.write(cid + "\n")
            f.write("\n")
            total += len(ids)

        f.write(f"=== Tổng cộng tất cả nguồn: {total} ID ===\n")
        f.write(f"=== Thành công: {success_count} | Thất bại: {fail_count} ===\n")

    log_success(f"=> Đã lưu tổng cộng {total} ID vào {OUTPUT}")
    print(Fore.GREEN + f"=> ✅ Thành công: {success_count}" + Style.RESET_ALL)
    print(Fore.RED + f"=> ❌ Thất bại: {fail_count}" + Style.RESET_ALL)

if __name__ == "__main__":
    if not os.path.exists(SOURCE_FILE):
        log_error(f"[!] Không tìm thấy file {SOURCE_FILE}")
        exit(1)

    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        sources = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not sources:
        log_error("[!] File nguonlps.txt trống hoặc không có link hợp lệ.")
        exit(1)

    all_results = {}
    success_count = 0
    fail_count = 0

    for src in sources:
        try:
            xml_data = fetch_xml(src)
            ids = extract_tvg_ids(xml_data)
            all_results[src] = ids
            log_success(f"   + {len(ids)} ID lấy được từ {src}")
            success_count += 1
        except Exception as e:
            log_error(f"[!] Lỗi khi xử lý {src}: {e}")
            fail_count += 1

    save_ids_to_file(all_results, success_count, fail_count)
    log_info("=== HOÀN TẤT ===")
                            
