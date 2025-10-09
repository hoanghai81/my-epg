import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz

# Múi giờ Việt Nam
tz = pytz.timezone("Asia/Ho_Chi_Minh")

# Đọc danh sách kênh
channels = []
with open("channels.txt", "r", encoding="utf-8") as f:
    for line in f:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            channels.append({
                "id": parts[0],
                "url": parts[1],
                "name": parts[2]
            })

# Tạo root XML
tv = ET.Element("tv", attrib={
    "generator-info-name": "my-epg-generator",
    "source-info-url": "https://lichphatsong.site"
})

# Hàm định dạng thời gian chuẩn EPG (YYYYMMDDhhmmss +0700)
def format_time(dt):
    return dt.strftime("%Y%m%d%H%M%S +0700")

# Duyệt qua từng kênh
for ch in channels:
    # Thêm thẻ channel
    ch_el = ET.SubElement(tv, "channel", id=ch["id"])
    ET.SubElement(ch_el, "display-name").text = ch["name"]

    try:
        r = requests.get(ch["url"], timeout=10)
        r.encoding = "utf-8"
        data = ET.fromstring(r.text)

        for prog in data.findall("programme"):
            start = prog.attrib.get("start")
            stop = prog.attrib.get("stop")
            title_el = prog.find("title")

            # Bỏ qua nếu thiếu thời gian
            if not start or not stop or title_el is None:
                continue

            # Thêm vào EPG chính
            p_el = ET.SubElement(tv, "programme", {
                "start": start,
                "stop": stop,
                "channel": ch["id"]
            })
            title = ET.SubElement(p_el, "title", lang="vi")
            title.text = title_el.text or "Chưa có tiêu đề"

            desc_el = prog.find("desc")
            if desc_el is not None and desc_el.text:
                desc = ET.SubElement(p_el, "desc", lang="vi")
                desc.text = desc_el.text.strip()

    except Exception as e:
        print(f"Lỗi khi xử lý {ch['name']}: {e}")

# Ghi file epg.xml
tree = ET.ElementTree(tv)
tree.write("docs/epg.xml", encoding="utf-8", xml_declaration=True)
print("✅ Đã tạo xong file docs/epg.xml theo chuẩn EPG XML.")
