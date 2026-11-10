import os
import sys
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

EXCLUDE_WORDS = ["làm thế nào", "pháp thoại", "giảng", "hỏi đáp", "vấn đáp", "chuyện", "sự tích", "talk", "lecture"]

def find_and_download_archive_mp3(query: str, target_filename: str, file_keyword: str = "", min_mb: float = 0.8, max_mb: float = 18.0) -> bool:
    target_path = os.path.join(AUDIO_DIR, target_filename)
    search_url = "https://archive.org/advancedsearch.php"
    params = {
        "q": f"({query}) AND mediatype:(audio)",
        "fl[]": ["identifier", "title"],
        "rows": 30,
        "page": 1,
        "output": "json"
    }
    with httpx.Client(timeout=25.0, headers=HEADERS, follow_redirects=True) as client:
        r = client.get(search_url, params=params)
        if r.status_code != 200:
            return False
        docs = r.json().get("response", {}).get("docs", [])
        for doc in docs:
            ident = doc.get("identifier", "")
            title = doc.get("title", "")
            if any(w in title.lower() for w in EXCLUDE_WORDS):
                continue
            meta_url = f"https://archive.org/metadata/{ident}"
            mr = client.get(meta_url)
            if mr.status_code != 200:
                continue
            files = mr.json().get("files", [])
            for f in files:
                fname = f.get("name", "")
                if not fname.lower().endswith(".mp3"):
                    continue
                if any(w in fname.lower() for w in EXCLUDE_WORDS):
                    continue
                if file_keyword and file_keyword.lower() not in fname.lower() and file_keyword.lower() not in title.lower():
                    continue
                size_bytes = int(f.get("size", 0) or 0)
                size_mb = size_bytes / (1024 * 1024)
                if min_mb <= size_mb <= max_mb:
                    dl_url = f"https://archive.org/download/{ident}/{fname}"
                    print(f"Đang tải [{title}] -> {fname} ({size_mb:.2f} MB)...")
                    with client.stream("GET", dl_url) as stream:
                        if stream.status_code == 200:
                            with open(target_path, "wb") as out_f:
                                for chunk in stream.iter_bytes(chunk_size=65536):
                                    out_f.write(chunk)
                            print(f"✅ Đã lưu thành công: {target_path} ({size_mb:.2f} MB)")
                            return True
    return False

if __name__ == "__main__":
    print("1. Tìm & tải file MP3 Trì Tụng Chú Đại Bi thật...")
    ok1 = find_and_download_archive_mp3(
        'title:("Chu Dai Bi" OR "Chú Đại Bi" OR "Maha Karuna Dharani" OR "Dai Bi Chu")',
        "tung_kinh_chu_dai_bi.mp3",
        min_mb=0.8, max_mb=16.0
    )
    if not ok1:
        find_and_download_archive_mp3(
            '("Chu Dai Bi" OR "Om Mani Padme Hum" OR "Buddhist Chanting")',
            "tung_kinh_chu_dai_bi.mp3",
            min_mb=0.8, max_mb=16.0
        )

    print("2. Tìm & tải file MP3 Tụng Niệm Phật / Om Mani Padme Hum thật...")
    find_and_download_archive_mp3(
        'title:("Om Mani Padme Hum" OR "Amitabha" OR "A Di Da Phat" OR "Heart Sutra")',
        "niem_phat.mp3",
        min_mb=0.8, max_mb=16.0
    )
