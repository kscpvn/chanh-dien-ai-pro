import os
from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME", "@primecase18")
FB_LIVE_VIDEO_ID = os.getenv("FB_LIVE_VIDEO_ID", "")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")
YT_LIVE_VIDEO_ID = os.getenv("YT_LIVE_VIDEO_ID", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_COOLDOWN = float(os.getenv("GEMINI_COOLDOWN", "4.0"))
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-NamMinhNeural")
AUTO_APPROVE_COMMENTS = os.getenv("AUTO_APPROVE_COMMENTS", "true").lower() == "true"

DB_PATH = os.path.join(os.path.dirname(__file__), "chanh_dien.db")

BAD_WORDS = [
    "sống chó", "chửi thề", "phản động", "cờ bạc", "lừa đảo",
    "cá độ", "lô đề", "chết tiệt", "đồ điên", "bịp bợm", "tục tĩu"
]

FORTUNE_KEYWORDS = [
    "xin xăm", "xin quẻ", "rút quẻ", "gieo quẻ", "cầu",
    "xin vía", "quẻ", "xăm", "mua đất", "tài lộc", "tình duyên", "bình an", "kinh doanh"
]

# Từ khóa đổi hình nhân vật (Học tập và mở rộng từ kentjuno/chanh-dien-online)
AVATAR_KEYWORDS = {
    "high_monk": ["cao tăng", "hòa thượng", "đại sư", "trụ trì"],
    "monk": ["sư thầy", "nhà sư", "thầy", "sư"],
    "nun": ["ni cô", "sư cô", "ni"],
    "novice": ["chú tiểu", "tiểu"],
    "elder": ["cụ bà", "lão", "bà"],
    "female": ["nữ", "chị", "cô gái", "em gái", "mẹ"],
    "male": ["nam", "anh", "chú", "ông"]
}

FORTUNE_DB = [
    {
        "id": "Quẻ Số 01",
        "rank": "THƯỢNG THƯỢNG CÁT",
        "title": "Long Môn Vũ Hóa (Cá Chép Hóa Rồng)",
        "poem": "Mây mù tan biến thấy trăng thanh,\nVạn sự từ nay ắt đạt thành.\nTài lộc dồi dào nhân nghĩa trọn,\nGia đường hưng vượng phúc an lành.",
        "meaning": "Cầu tài đắc tài, cầu danh đắc vị, mọi dự định lớn đều gặp quý nhân phù trợ."
    },
    {
        "id": "Quẻ Số 08",
        "rank": "THƯỢNG CÁT",
        "title": "Khô Mộc Phùng Xuân (Cây Khô Gặp Mùa Xuân)",
        "poem": "Đông qua xuân tới lộc đâm chồi,\nGian khó lùi xa phúc đến rồi.\nBình tâm vững chí đường hanh thông,\nPhú quý vinh hoa rạng đất trời.",
        "meaning": "Giai đoạn vất vả đã qua, công việc và tiền bạc sắp đón vận hội mới rất tốt đẹp."
    },
    {
        "id": "Quẻ Số 16",
        "rank": "ĐẠI CÁT",
        "title": "Thuận Buồm Xuôi Gió",
        "poem": "Gió thuận buồm căng vượt biển khơi,\nBình an vô sự khắp muôn nơi.\nLàm ăn phát đạt thêm hưng thịnh,\nGia đạo sum vầy rộn tiếng cười.",
        "meaning": "Xuất hành thuận lợi, đầu tư kinh doanh suôn sẻ, gia đình hòa thuận ấm êm."
    },
    {
        "id": "Quẻ Số 29",
        "rank": "TRUNG CÁT",
        "title": "Tích Thiện Phùng Thời (Tích Phúc Gặp Thời)",
        "poem": "Lòng thành giữ trọn chữ nhân tâm,\nTrời Phật chứng tri chẳng phụ phần.\nChậm chắc từng bước nền móng vững,\nThu về quả ngọt gấp mười lần.",
        "meaning": "Kiên trì giữ chữ tín và làm việc thiện lành thì tài lộc tự khắc tìm đến."
    },
    {
        "id": "Quẻ Số 68",
        "rank": "THƯỢNG THƯỢNG CÁT",
        "title": "Khai Hoa Kết Quả (Hoa Nở Kết Trái Vàng)",
        "poem": "Lộc biếc hoa vàng rộ khắp sân,\nTình duyên viên mãn, phúc muôn phần.\nTiền tài như nước về biển lớn,\nSức khỏe dồi dào vạn tuổi xuân.",
        "meaning": "Tình duyên, sức khỏe và tài chính đều đạt độ viên mãn, cầu gì được nấy."
    }
]
