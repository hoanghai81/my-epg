import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import os
import re

def read_channels():
    channels = []
    with open("channels.txt", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 3:
                continue
            cid, url, display = parts
            channels.append({
                "id": cid.strip(),
                "url": url.strip(),
                "display": display.strip()
            })
    return channels

# --- helpers to parse times like "HH:MM" or "H:MM" ---
def parse_time_hhmm(timestr):
    try:
        parts = timestr.strip().split(":")
        if len(parts) == 2:
            hh = int(parts[0])
            mm = int(parts[1])
            return hh, mm
    except:
        pass
    return None

# ========== Parsers cho từng nguồn ==========

def get_vtv_schedule(channel):
    """Lấy lịch từ vtv.vn/lich-phat-song.htm"""
    url = "https://vtv.vn/lich-phat-song.htm"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print("  lỗi fetch VTV:", e)
        return []

    schedules = []
    # Trang vtv có các box .boxLichChuongTrinh cho mỗi kênh
    for box in soup.select(".boxLichChuongTrinh"):
        # tiêu đề kênh
        h2 = box.select_one("h2")
        if not h2:
            continue
        ch_name = h2.get_text(strip=True).lower()
        if channel["id"].lower() in ch_name:
            # tìm các <li>
            for li in box.select("li"):
                time_el = li.select_one(".time")
                prog_el = li.select_one(".title")
                if time_el and prog_el:
                    t = time_el.get_text(strip=True)
                    p = prog_el.get_text(strip=True)
                    schedules.append({"time": t, "title": p})
    return schedules

def get_sctv_schedule(channel):
    """Lấy lịch từ sctv.com.vn"""
    url = "https://www.sctv.com.vn/lich-phat-song"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print("  lỗi fetch SCTV:", e)
        return []

    schedules = []
    # cấu trúc trang SCTV: .schedule__content chứa từng kênh
    for block in soup.select(".schedule__content"):
        title_el = block.select_one(".schedule__title")
        if not title_el:
            continue
        name = title_el.get_text(strip=True).lower()
        if channel["id"].lower() in name:
            # tìm các dòng item
            for row in block.select(".schedule__item"):
                t_el = row.select_one(".schedule__time")
                p_el = row.select_one(".schedule__name")
                if t_el and p_el:
                    t = t_el.get_text(strip=True)
                    p = p_el.get_text(strip=True)
                    schedules.append({"time": t, "title": p})
    return schedules

def get_vtvcab_schedule(channel):
    """Lấy lịch từ dichvu.vtvcab.vn/lich-phat-song"""
    url = "https://dichvu.vtvcab.vn/lich-phat-song"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print("  lỗi fetch VTVCAB:", e)
        return []

    schedules = []
    # cấu trúc trang VTVCab: có .list-channel cho từng kênh
    for div in soup.select(".list-channel"):
        name_el = div.select_one(".name-channel")
        if not name_el:
            continue
        nm = name_el.get_text(strip=True).lower()
        # kiểm tra nếu tên kênh trùng (loại bỏ "on " nếu cần)
        if channel["id"].lower().replace("on ", "") in nm:
            # tìm các chương trình row-program
            for row in div.select(".row-program"):
                t_el = row.select_one(".time")
                p_el = row.select_one(".name-program")
                if t_el and p_el:
                    t = t_el.get_text(strip=True)
                    p = p_el.get_text(strip=True)
                    schedules.append({"time": t, "title": p})
    return schedules

def fetch_schedule(channel):
    url = channel["url"]
    if "vtv.vn" in url:
        return get_vtv_schedule(channel)
    elif "sctv.com.vn" in url:
        return get_sctv_schedule(channel)
    elif "vtvcab.vn" in url:
        return get_vtvcab_schedule(channel)
    else:
        print("  nguồn không xử lý được:", url)
        return []

def generate_epg(channels):
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    today = datetime.now(tz).date()

    tv = ET.Element("tv", attrib={"generator-info-name": "GitHub-EPG"})

    # Tạo các <channel>
    for ch in channels:
        ch_el = ET.SubElement(tv, "channel", id=ch["id"])
        dn = ET.SubElement(ch_el, "display-name")
        dn.text = ch["display"]

    # Với mỗi kênh, lấy lịch và tạo chương trình
    for ch in channels:
        print("Lấy lịch cho:", ch["id"])
        sched = fetch_schedule(ch)
        if not sched:
            # nếu không lấy được gì, bỏ qua
            continue

        # biến để giữ thời điểm trước để xác định stop
        prev_dt = None
        for i, item in enumerate(sched):
            parsed = parse_time_hhmm(item["time"])
            if not parsed:
                continue
            hh, mm = parsed
            dt_start = datetime(year=today.year, month=today.month, day=today.day,
                                hour=hh, minute=mm, tzinfo=tz)
            # nếu lịch trước đó tồn tại và dt_start <= prev, xử lý nhảy ngày
            if prev_dt and dt_start <= prev_dt:
                dt_start = dt_start + timedelta(days=1)
            # tìm dt_stop: nếu có mục tiếp theo, dùng giờ của mục tiếp, else + 30 phút
            dt_stop = None
            if i + 1 < len(sched):
                parsed2 = parse_time_hhmm(sched[i+1]["time"])
                if parsed2:
                    hh2, mm2 = parsed2
                    dt_stop = datetime(year=today.year, month=today.month, day=today.day,
                                       hour=hh2, minute=mm2, tzinfo=tz)
                    if dt_stop <= dt_start:
                        dt_stop = dt_stop + timedelta(days=1)
            if dt_stop is None:
                dt_stop = dt_start + timedelta(minutes=30)

            # tạo programme
            prog_el = ET.SubElement(tv, "programme", {
                "start": dt_start.strftime("%Y%m%d%H%M%S") + " +0700",
                "stop": dt_stop.strftime("%Y%m%d%H%M%S") + " +0700",
                "channel": ch["id"]
            })
            t_el = ET.SubElement(prog_el, "title", {"lang": "vi"})
            t_el.text = item["title"]
            d_el = ET.SubElement(prog_el, "desc", {"lang": "vi"})
            d_el.text = ""

            prev_dt = dt_start

    # tạo thư mục docs nếu chưa có
    os.makedirs("docs", exist_ok=True)
    out_path = os.path.join("docs", "epg.xml")
    tree = ET.ElementTree(tv)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print("Đã viết EPG vào", out_path)

if __name__ == "__main__":
    channels = read_channels()
    generate_epg(channels)
            
