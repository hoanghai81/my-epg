import requests
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET
import pytz
import html
import re

TODAY = datetime.now().strftime("%Y-%m-%d")
VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def log(msg):
    print(msg, flush=True)

def parse_vtvgo(api_url, display_name):
    try:
        url = api_url.replace("{date}", TODAY)
        log(f"   [fetch JSON] {url}")
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            log(f"   [!] HTTP {r.status_code}")
            return []
        data = r.json()
        schedules = data.get("data", {}).get("schedules", [])
        results = []
        for item in schedules:
            start = item.get("time")
            title = item.get("name") or item.get("program_name", "Chưa rõ")
            if not start:
                continue
            start_dt = VN_TZ.localize(datetime.strptime(f"{TODAY} {start}", "%Y-%m-%d %H:%M"))
            results.append({
                "start": start_dt,
                "title": title.strip()
            })
        return results
    except Exception as e:
        log(f"   [!] Lỗi parse VTVGo: {e}")
        return []

def parse_vtv_html(url, code):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.select("div.lps-time-item")
        results = []
        for b in blocks:
            ch = b.find_previous("div", class_="lps-cat-title")
            if not ch or code.lower() not in ch.text.lower():
                continue
            for item in b.select("ul > li"):
                time_tag = item.select_one("span.time")
                title_tag = item.select_one("a") or item.select_one("span.name")
                if not time_tag or not title_tag:
                    continue
                start = time_tag.text.strip()
                title = title_tag.text.strip()
                start_dt = VN_TZ.localize(datetime.strptime(f"{TODAY} {start}", "%Y-%m-%d %H:%M"))
                results.append({
                    "start": start_dt,
                    "title": html.unescape(title)
                })
        return results
    except Exception as e:
        log(f"   [!] Lỗi parse VTV HTML: {e}")
        return []

def parse_sctv(url, code):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for box in soup.select("div.view-content div.views-row"):
            title_el = box.select_one(".views-field-title span")
            time_el = box.select_one(".views-field-field-thoi-gian span")
            if not title_el or not time_el:
                continue
            start = time_el.text.strip()
            title = title_el.text.strip()
            start_dt = VN_TZ.localize(datetime.strptime(f"{TODAY} {start}", "%Y-%m-%d %H:%M"))
            results.append({"start": start_dt, "title": html.unescape(title)})
        return results
    except Exception as e:
        log(f"   [!] Lỗi parse SCTV: {e}")
        return []

def parse_vtvcab(url, code):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".tv-schedule-item"):
            title_el = item.select_one(".tv-schedule-title")
            time_el = item.select_one(".tv-schedule-time")
            if not title_el or not time_el:
                continue
            start = time_el.text.strip()
            title = title_el.text.strip()
            start_dt = VN_TZ.localize(datetime.strptime(f"{TODAY} {start}", "%Y-%m-%d %H:%M"))
            results.append({"start": start_dt, "title": html.unescape(title)})
        return results
    except Exception as e:
        log(f"   [!] Lỗi parse VTVCab: {e}")
        return []

def main():
    log(f"=> Lấy EPG cho ngày {TODAY}")
    channels = []
    with open("channels.txt", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("|")
                if len(parts) >= 3:
                    channels.append({
                        "code": parts[0].strip(),
                        "url": parts[1].strip(),
                        "name": parts[2].strip()
                    })

    root = ET.Element("tv")
    for ch in channels:
        code, url, display = ch["code"], ch["url"], ch["name"]
        log(f"=> Lấy lịch cho: {display}")
        programmes = []
        if "api.vtvgo.vn" in url:
            programmes = parse_vtvgo(url, display)
        elif "vtv.vn" in url:
            programmes = parse_vtv_html(url, code)
        elif "sctv.com.vn" in url:
            programmes = parse_sctv(url, code)
        elif "vtvcab.vn" in url:
            programmes = parse_vtvcab(url, code)
        else:
            log(f"   [!] Không nhận dạng được nguồn: {url}")

        ch_elem = ET.SubElement(root, "channel", id=code)
        ET.SubElement(ch_elem, "display-name").text = display
        log(f"   - items found: {len(programmes)}")

        for prog in programmes:
            prog_elem = ET.SubElement(root, "programme", {
                "start": prog["start"].strftime("%Y%m%d%H%M%S %z"),
                "channel": code
            })
            ET.SubElement(prog_elem, "title").text = prog["title"]

    tree = ET.ElementTree(root)
    tree.write("docs/epg.xml", encoding="utf-8", xml_declaration=True)
    log("-> written docs/epg.xml")

if __name__ == "__main__":
    main()
    
