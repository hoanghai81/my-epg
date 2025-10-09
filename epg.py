import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os

def fetch_vtv1_schedule(date_str):
    """
    Crawl lịch phát sóng VTV1 từ lichphatsong.site theo ngày (YYYY-MM-DD)
    Trả về list các item: [{"start": "...", "title": "..."}]
    """
    url = "https://lichphatsong.site/kenh/vtv1"
    print(f"=> Lấy lịch VTV1 cho ngày {date_str} từ {url}")
    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
    except Exception as e:
        print(f"[!] Lỗi tải trang: {e}")
        return []

    soup = BeautifulSoup(res.text, "lxml")
    all_days = soup.find_all("div", class_="tab-pane")
    items = []

    for day in all_days:
        date_attr = day.get("id", "")
        if date_attr.endswith(date_str):
            for li in day.find_all("li", class_="list-group-item"):
                time_tag = li.find("span", class_="time")
                title_tag = li.find("span", class_="name")
                if not time_tag or not title_tag:
                    continue
                start_time = time_tag.get_text(strip=True)
                title = title_tag.get_text(strip=True)
                start_dt = f"{date_str} {start_time}"
                items.append({"start": start_dt, "title": title})
    print(f"   - items found: {len(items)}")
    return items

def make_epg_xml(channel_id, channel_name, schedules):
    xml = [f'  <channel id="{channel_id}">']
    xml.append(f'    <display-name>{channel_name}</display-name>')
    xml.append("  </channel>")
    for prog in schedules:
        try:
            start_dt = datetime.strptime(prog["start"], "%Y-%m-%d %H:%M")
            stop_dt = start_dt + timedelta(minutes=30)
            start_fmt = start_dt.strftime("%Y%m%d%H%M%S +0700")
            stop_fmt = stop_dt.strftime("%Y%m%d%H%M%S +0700")
            title = prog["title"].replace("&", "&amp;")
            xml.append(f'  <programme start="{start_fmt}" stop="{stop_fmt}" channel="{channel_id}">')
            xml.append(f'    <title lang="vi">{title}</title>')
            xml.append("  </programme>")
        except Exception as e:
            print(f"[!] Lỗi parse chương trình: {e}")
    return "\n".join(xml)

def main():
    print("=== BẮT ĐẦU SINH EPG ===")

    today = datetime.now()
    dates = [
        today.strftime("%Y-%m-%d"),
        (today + timedelta(days=1)).strftime("%Y-%m-%d"),
    ]

    all_items = []
    for date_str in dates:
        items = fetch_vtv1_schedule(date_str)
        all_items.extend(items)

    # Sinh XML
    header = '<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="lichphatsong.site">'
    body = make_epg_xml("VTV1", "VTV1 HD", all_items)
    footer = "</tv>"
    xml_content = "\n".join([header, body, footer])

    os.makedirs("docs", exist_ok=True)
    with open("docs/epg.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"-> written docs/epg.xml ({len(all_items)} chương trình)")
    print("=== HOÀN TẤT ===")

if __name__ == "__main__":
    main()
    
