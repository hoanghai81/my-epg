import os
import gzip
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime, timedelta, timezone

# Timezone Vietnam (+7)
VN_TZ = timezone(timedelta(hours=7))
NOW = datetime.now(VN_TZ)
TODAY = NOW.date()
TOMORROW = TODAY + timedelta(days=1)

# Cấu hình đầu ra
OUTPUT_FILE = "docs/epg.xml"
CHANNELS_FILE = "channels.txt"
LOGO_BASE = "https://raw.githubusercontent.com/hoanghai81/my-epg/main/logos"

# --- Hàm tải dữ liệu EPG từ URL ---
def fetch_epg(url):
    print(f"=> Downloading {url}")
    headers = {"User-Agent": "my-epg/2025"}
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"   ⚠️ Request failed: {e}")
        return None

    content = r.content
    if url.endswith(".gz") or r.headers.get("Content-Encoding") == "gzip":
        try:
            content = gzip.decompress(content)
            print("   ✓ Gzip decompressed")
        except Exception:
            try:
                content = gzip.GzipFile(fileobj=BytesIO(r.content)).read()
                print("   ✓ Fallback decompress successful")
            except Exception as e:
                print(f"   ⚠️ Decompress failed: {e}")
                return None

    try:
        xml_root = ET.fromstring(content)
        if xml_root.tag != "tv":
            print(f"   ⚠️ Unexpected XML root: {xml_root.tag}")
            return None
        print("   ✓ Parsed XML root: <tv>")
        return xml_root
    except Exception as e:
        print(f"   ⚠️ XML parse error: {e}")
        return None


# --- Hàm lọc theo ngày ---
def within_window(start_str):
    try:
        start_time = datetime.strptime(start_str[:14], "%Y%m%d%H%M%S")
        return TODAY <= start_time.date() <= TOMORROW
    except Exception:
        return False


# --- Hàm lấy logo ---
def get_logo_url(channel_id, xml_channel):
    icon = xml_channel.find("icon")
    if icon is not None and "src" in icon.attrib:
        return icon.attrib["src"]
    return f"{LOGO_BASE}/{channel_id}.png"


# --- Main ---
def main():
    print("🛰️  Starting EPG builder...")
    all_channels = {}
    programmes = []

    if not os.path.exists(CHANNELS_FILE):
        print(f"❌ Missing {CHANNELS_FILE}")
        return

    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            print(f"⚠️  Invalid line: {line}")
            continue

        channel_id, epg_url, display_name = parts
        xml_root = fetch_epg(epg_url)
        if xml_root is None:
            continue

        # Lưu thông tin kênh
        ch_node = xml_root.find(f"./channel[@id='{channel_id}']")
        if ch_node is not None:
            logo_url = get_logo_url(channel_id, ch_node)
        else:
            logo_url = f"{LOGO_BASE}/{channel_id}.png"

        all_channels[channel_id] = {
            "id": channel_id,
            "name": display_name,
            "logo": logo_url,
        }

        # Lấy danh sách chương trình
        count = 0
        for prog in xml_root.findall(f"./programme[@channel='{channel_id}']"):
            start = prog.attrib.get("start", "")
            if within_window(start):
                programmes.append(prog)
                count += 1

        print(f"   ✓ {display_name}: {count} programmes")

    # --- Tạo file EPG gộp ---
    tv = ET.Element("tv", {"generator-info-name": "my-epg"})
    for ch in all_channels.values():
        ch_el = ET.SubElement(tv, "channel", {"id": ch["id"]})
        name_el = ET.SubElement(ch_el, "display-name", {"lang": "vi"})
        name_el.text = ch["name"]
        icon_el = ET.SubElement(ch_el, "icon", {"src": ch["logo"]})

    for p in programmes:
        tv.append(p)

    tree = ET.ElementTree(tv)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"✅ Done! Output saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
    
