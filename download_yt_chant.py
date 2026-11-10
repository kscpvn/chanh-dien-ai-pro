import os
import sys
import subprocess
import httpx
import yt_dlp
import shutil

sys.stdout.reconfigure(encoding="utf-8")

URL = "https://www.youtube.com/watch?v=Z2mZix8y22E"
AUDIO_DIR = os.path.join(os.path.dirname(__file__), "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)
TARGET_MP3 = os.path.join(AUDIO_DIR, "tung_kinh_chu_dai_bi.mp3")
TEMP_FILE = os.path.join(AUDIO_DIR, "temp_trithoat_raw.m4a")


def try_youtube_download():
    print("=== 1. Thử tải trực tiếp từ YouTube Z2mZix8y22E (TT. Thích Trí Thoát) ===")
    clients_to_try = [
        ["android_vr"],
        ["tv"],
        ["ios"],
        ["mweb"],
        ["web_creator"],
    ]
    for client_list in clients_to_try:
        print(f"-> Thử player_client={client_list}...")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(AUDIO_DIR, "temp_yt_%(ext)s"),
            "noplaylist": True,
            "quiet": False,
            "extractor_args": {
                "youtube": {
                    "player_client": client_list,
                }
            },
            # Tải 12 phút đầu tiên (khoảng 5-7 biến Chú Đại Bi liên tục) để phát lặp mượt mà
            "download_ranges": yt_dlp.utils.download_range_func(None, [(0, 720)]),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([URL])
            # Tìm file mp3 vừa tạo
            for fname in os.listdir(AUDIO_DIR):
                if fname.startswith("temp_yt_") and fname.endswith(".mp3"):
                    fpath = os.path.join(AUDIO_DIR, fname)
                    if os.path.getsize(fpath) > 500_000:
                        shutil.move(fpath, TARGET_MP3)
                        print(f"[OK] Đã tải từ YouTube thành công: {TARGET_MP3} ({os.path.getsize(TARGET_MP3)//1024} KB)")
                        return True
        except Exception as e:
            print(f"   Lỗi với client {client_list}: {e}")
    return False


def try_archive_thich_tri_thoat():
    print("\n=== 2. Tìm bản thu gốc 'Chú Đại Bi - Thượng Tọa Thích Trí Thoát' trên Archive.org ===")
    queries = [
        '("Thich Tri Thoat" OR "Thích Trí Thoát") AND ("Chu Dai Bi" OR "Chú Đại Bi") AND mediatype:audio',
        '("Thich Tri Thoat" OR "Thích Trí Thoát" OR "Tri Thoat") AND mediatype:audio',
        'title:("Chu Dai Bi" OR "Chú Đại Bi") AND ("Tri Thoat" OR "Trí Thoát")',
    ]
    with httpx.Client(timeout=45.0, follow_redirects=True) as client:
        for q in queries:
            print(f"-> Truy vấn: {q}")
            resp = client.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": q,
                    "fl[]": ["identifier", "title", "creator"],
                    "rows": 25,
                    "page": 1,
                    "output": "json",
                },
            )
            docs = resp.json().get("response", {}).get("docs", [])
            print(f"   Tìm thấy {len(docs)} kết quả.")
            for doc in docs:
                ident = doc.get("identifier")
                title = doc.get("title", "")
                print(f"   * Kiểm tra item: {ident} | {title}")
                meta = client.get(f"https://archive.org/metadata/{ident}").json()
                files = meta.get("files", [])
                # Ưu tiên file có tên Chu Dai Bi / Chú Đại Bi hoặc Thích Trí Thoát
                mp3_candidates = []
                for f in files:
                    name = f.get("name", "")
                    size = int(f.get("size", 0) or 0)
                    if name.lower().endswith(".mp3") and 1_500_000 < size < 80_000_000:
                        score = 0
                        lname = name.lower()
                        if "dai bi" in lname or "daibi" in lname or "đại bi" in lname:
                            score += 10
                        if "tri thoat" in lname or "trí thoát" in lname or "trithoat" in lname:
                            score += 10
                        mp3_candidates.append((score, size, name))
                mp3_candidates.sort(key=lambda x: (-x[0], x[1]))
                for score, size, name in mp3_candidates:
                    # Nếu q là query rộng số 2, bắt buộc tên file hoặc title phải có Đại Bi
                    if "Dai Bi" not in q and score == 0 and "đại bi" not in str(title).lower() and "dai bi" not in str(title).lower():
                        continue
                    dl_url = f"https://archive.org/download/{ident}/{httpx.URL(name).raw_path.decode('utf-8')}"
                    print(f"   -> Đang tải MP3: {name} ({size//1024} KB) từ {dl_url}")
                    with client.stream("GET", dl_url) as r:
                        if r.status_code == 200:
                            tmp_out = TARGET_MP3 + ".part"
                            with open(tmp_out, "wb") as out:
                                for chunk in r.iter_bytes(chunk_size=65536):
                                    out.write(chunk)
                            if os.path.getsize(tmp_out) > 1_000_000:
                                shutil.move(tmp_out, TARGET_MP3)
                                print(f"[OK] Đã tải thành công bản thu Chú Đại Bi - TT. Thích Trí Thoát: {TARGET_MP3} ({os.path.getsize(TARGET_MP3)//1024} KB)")
                                return True
    return False


if __name__ == "__main__":
    ok = try_youtube_download()
    if not ok:
        ok = try_archive_thich_tri_thoat()
    if not ok:
        print("[FAIL] Chưa tải được file.")
        sys.exit(1)
