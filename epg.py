import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import re
import os

# ========== Đọc danh sách kênh ==========
def read_channels():
    channels = []
    with open("channels.txt", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("|")
                if len(parts) == 3:
                    channels.append({"id": parts[0].strip(), "url": parts[1].strip(), "name": parts[2].strip()})
    return channels


# ========== Hàm lấy lịch phát sóng từ từng nguồn ==========

# --- 1. VTV ---
def get_vtv_schedule(channel):
    ch_id = channel["id"].lower()
    resp = requests.get("https://vtv.vn/lich-phat-song.htm", timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    schedules = []
    for item in soup.select(".boxLichChuongTrinh"):
        ch_name = item.select_one("h2").get_text(strip=True).lower()
        if ch_id in ch_name:
            for li in item.select("li"):
                time_ = li.select_one(".time")
                prog_ = li.select_one(".title")
                if time_ and prog_:
                    schedules.append({"time": time_.get_text(strip=True), "title": prog_.get_text(strip=True)})
    return schedules


# --- 2. SCTV ---
def get_sctv_schedule(channel):
    ch_id = channel["id"].lower()
    resp = requests.get("https://www.sctv.com.vn/lich-phat-song", timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    schedules = []
    blocks = soup.select(".schedule__content")
    for block in blocks:
        ch_name = block.select_one(".schedule__title")
        if ch_name and ch_id in ch_name.get_text(strip=True).lower():
            for row in block.select(".schedule__item"):
                t = row.select_one(".schedule__time")
                p = row.select_one(".schedule__name")
                if t and p:
                    schedules.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    return schedules


# --- 3. VTVcab (ON) ---
def get_vtvcab_schedule(channel):
    ch_id = channel["id"].lower()
    resp = requests.get("https://dichvu.vtvcab.vn/lich-phat-song", timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")

    schedules = []
    for div in soup.select(".list-channel"):
        ch_name = div.select_one(".name-channel")
        if ch_name and ch_id.replace("on ", "") in ch_name.get_text(strip=True).lower():
            for row in div.select(".row-program"):
                t = row.select_one(".time")
                p = row.select_one(".name-program")
                if t and p:
                    schedules.append({"time": t.get_text(strip=True), "title": p.get_text(strip=True)})
    return schedules


# ========== Xử lý phân tích nguồn ==========
def fetch_schedule(channel):
    url = channel["url"]
    if "vtv.vn" in url:
        return get_vtv_schedule(channel)
    elif "sctv.com.vn" in url:
        return get_sctv_schedule(channel)
    elif "vtvcab.vn" in url:
        return get_vtvcab_schedule(channel)
    else:
        return []


# ========== Sinh file EPG ==========
def generate_epg(channels):
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)
    today = now.date()

    tv = ET.Element("tv", attrib={"generator-info-name": "GitHub-EPG"})

    for ch in channels:
        print(f"📺 Đang lấy lịch {ch['name']} ...")
        ch_el = ET.SubElement(tv, "channel", id=ch["id"])
        ET.SubElement(ch_el, "display-name").text = ch["name"]

        schedules = fetch_schedule(ch)
        if not schedules:
            ET.SubElement(ET.SubElement(tv, "programme",
                                        start=now.strftime("%Y%m%d%H%M%S +0700"),
                                        stop=(now + timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0700"),
                                        channel=ch["id"]),
                          "title").text = "Không có dữ liệu"
            continue

        for i, item in enumerate(schedules):
            try:
                start_time = datetime.strptime(item["time"], "%H:%M").replace(
                    year=today.year, month=today.month, day=today.day, tzinfo=tz
                )
                if i + 1 < len(schedules):
                    end_time = datetime.strptime(schedules[i + 1]["time"], "%H:%M").replace(
                        year=today.year, month=today.month, day=today.day, tzinfo=tz
                    )
                else:
                    end_time = start_time + timedelta(minutes=30)

                prog_el = ET.SubElement(tv, "programme",
                                        start=start_time.strftime("%Y%m%d%H%M%S +0700"),
                                        stop=end_time.strftime("%Y%m%d%H%M%S +0700"),
                                        channel=ch["id"])
                ET.SubElement(prog_el, "title").text = item["title"]
                ET.SubElement(prog_el, "desc").text = f"Lịch phát sóng {ch['name']}"
            except Exception:
                pass

    os.makedirs("docs", exist_ok=True)
    out_path = os.path.join("docs", "epg.xml")
    tree = ET.ElementTree(tv)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    print("✅ File EPG đã được tạo:", out_path)


if __name__ == "__main__":
    channels = read_channels()
    generate_epg(channels)
    
