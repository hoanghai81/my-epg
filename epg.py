import requests
from bs4 import BeautifulSoup
import os

EPG_SOURCE = "https://lichphatsong.site/schedule/epg.xml"
CHANNELS = ["VTV1"]  # sau này anh chỉ cần thêm vào đây: ["VTV1", "VTV2", "VTV3", ...]

def main():
    print("=== BẮT ĐẦU SINH EPG ===")
    print(f"=> Tải dữ liệu từ {EPG_SOURCE}")

    try:
        res = requests.get(EPG_SOURCE, timeout=30)
        res.raise_for_status()
    except Exception as e:
        print(f"[!] Lỗi tải EPG: {e}")
        return

    soup = BeautifulSoup(res.text, "xml")

    # Lọc các kênh mong muốn
    channels = soup.find_all("channel")
    programmes = soup.find_all("programme")

    selected_channels = []
    selected_programmes = []

    for ch in channels:
        ch_id = ch.get("id", "").upper()
        if ch_id in [c.upper() for c in CHANNELS]:
            selected_channels.append(ch)

    for prog in programmes:
        ch_id = prog.get("channel", "").upper()
        if ch_id in [c.upper() for c in CHANNELS]:
            selected_programmes.append(prog)

    print(f"=> Lấy được {len(selected_programmes)} chương trình cho các kênh {CHANNELS}")

    # Tạo thư mục docs nếu chưa có
    os.makedirs("docs", exist_ok=True)

    # Ghi file XML
    with open("docs/epg.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')

        for ch in selected_channels:
            f.write(str(ch) + "\n")
        for prog in selected_programmes:
            f.write(str(prog) + "\n")

        f.write("</tv>\n")

    print(f"-> written docs/epg.xml ({len(selected_programmes)} chương trình)")
    print("=== HOÀN TẤT ===")


if __name__ == "__main__":
    main()
            
