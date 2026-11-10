import asyncio
import base64
import html
import io
import json
import logging
import random
import re
import time
import httpx
import edge_tts
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from config import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_COOLDOWN,
    TTS_VOICE, BAD_WORDS, FORTUNE_KEYWORDS, AVATAR_KEYWORDS, FORTUNE_DB
)

logger = logging.getLogger("AIService")

gemini_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Đã kết nối Gemini API thành công.")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Gemini Client: {e}")
else:
    logger.warning("Chưa cấu hình GEMINI_API_KEY. Hệ thống sẽ dùng kho quẻ chuẩn FORTUNE_DB.")

class FortuneSchema(BaseModel):
    id: str = Field(description="Số thứ tự quẻ, ví dụ: Quẻ Linh Ứng Số 68, Quẻ Số 88...")
    rank: str = Field(description="Cấp độ quẻ: THƯỢNG THƯỢNG CÁT, ĐẠI CÁT, THƯỢNG CÁT, hoặc TRUNG CÁT")
    title: str = Field(description="Tên quẻ 4 chữ Hán Việt kèm nghĩa tiếng Việt trang trọng")
    poem: str = Field(description="Đúng 4 câu thơ lục bát hoặc thất ngôn vần điệu chuẩn, trang trọng, có liên hệ tới lời cầu nguyện, ngăn cách bằng \\n")
    meaning: str = Field(description="Lời bàn giải quẻ ngắn gọn (1-2 câu, dưới 40 chữ), hướng thiện và trả lời đúng trọng tâm câu hỏi")

last_ai_call_time = 0.0

def sanitize_text(text: str, max_len: int = 120) -> str:
    cleaned = html.escape(text.strip())
    return cleaned[:max_len]

def is_clean_text(text: str) -> bool:
    text_lower = text.lower()
    return not any(bad_word in text_lower for bad_word in BAD_WORDS)

def is_fortune_request(text: str) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in FORTUNE_KEYWORDS)

def detect_avatar_type(text: str) -> str:
    text_lower = text.lower()
    for avatar_type, keywords in AVATAR_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return avatar_type
    return ""

async def generate_ai_fortune(username: str, wish_text: str, is_vip: bool = False) -> dict:
    global last_ai_call_time
    now = time.time()

    if not gemini_client or (not is_vip and (now - last_ai_call_time < GEMINI_COOLDOWN)):
        return random.choice(FORTUNE_DB)

    last_ai_call_time = now
    system_instruction = (
        "Bạn là một bậc cao tăng thông tuệ, từ bi, chuyên gieo quẻ cầu an và giải xăm. "
        "Nhiệm vụ: Dựa vào tên thí chủ và lời cầu nguyện, hãy gieo 1 quẻ xăm mang năng lượng tích cực, "
        "hướng thiện, khích lệ tinh thần. Tuyệt đối không phán điều xui rủi, mê tín cực đoan hay cổ xúy cờ bạc. "
        "Thơ giải phải đúng 4 câu lục bát hoặc thất ngôn vần điệu mượt mà, lồng ghép khéo léo mong cầu của thí chủ."
    )
    user_prompt = f"Thí chủ tên là '{username}', đang thành tâm xin quẻ với mong cầu: '{wish_text}'."

    try:
        response = await gemini_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=FortuneSchema,
                temperature=0.75,
            )
        )
        fortune_data = json.loads(response.text)
        logger.info(f"[GEMINI AI] Đã sáng tác quẻ riêng cho [{username}]: {fortune_data['title']}")
        return fortune_data
    except Exception as e:
        logger.error(f"Lỗi gọi Gemini API (Chuyển sang FORTUNE_DB): {e}")
        return random.choice(FORTUNE_DB)

TTS_CACHE: dict[str, str] = {}
CHOIR_CACHE: dict[str, dict[str, str]] = {}

SUTRA_LIBRARY = {
    "chu_dai_bi": [
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 01 - 14)",
            "01. Nam mô hắc ra đát na đa ra dạ da • 02. Nam mô a rị da • 03. Bà lô yết đế thước bát ra da • 04. Bồ Đề tát đỏa bà da • 05. Ma ha tát đỏa bà da • 06. Ma ha ca lô ni ca da • 07. Án • 08. Tát bàn ra phạt duệ • 09. Số đát na đát tỏa • 10. Nam mô tất kiết lật đỏa y mông a rị da • 11. Bà lô kiết đế thất Phật ra lăng đà bà • 12. Nam mô na ra cẩn trì • 13. Hê rị ma ha bàn đa sa mế • 14. Tát bà a tha đậu thâu bằng.",
            "Nam mô hắc ra đát na đa ra dạ da"
        ),
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 15 - 28)",
            "15. A thệ dựng • 16. Tát bà tát đa (Na ma bà tát đa, na ma bà già) • 17. Ma phạt đặc đậu • 18. Đát điệt tha • 19. Án a bà lô hê • 20. Lô ca đế • 21. Ca ra đế • 22. Di hê rị • 23. Ma ha bồ đề tát đỏa • 24. Tát bà tát bà • 25. Ma la ma la • 26. Ma hê ma hê rị đà dựng • 27. Cu lô cu lô kiết mông • 28. Độ lô độ lô phạt xà da đế.",
            "Án a bà lô hê lô ca đế"
        ),
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 29 - 42)",
            "29. Ma ha phạt xà da đế • 30. Đà la đà la • 31. Địa rị ni • 32. Thất Phật ra da • 33. Giá la giá la • 34. Mạ mạ phạt ma ra • 35. Mục đế lệ • 36. Y hê di hê • 37. Thất na thất na • 38. A ra sâm Phật ra xá lợi • 39. Phạt sa phạt sâm • 40. Phật ra xá da • 41. Hô lô hô lô ma ra • 42. Hô lô hô lô hê rị.",
            "Đà la đà la địa rị ni"
        ),
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 43 - 56)",
            "43. Ta ra ta ra • 44. Tất rị tất rị • 45. Tô rô tô rô • 46. Bồ Đề dạ Bồ Đề dạ • 47. Bồ đà dạ bồ đà dạ • 48. Di đế rị dạ • 49. Na ra cẩn trì • 50. Địa rị sắc ni na • 51. Ba dạ ma na • 52. Ta bà ha • 53. Tất đà dạ • 54. Ta bà ha • 55. Ma ha tất đà dạ • 56. Ta bà ha.",
            "Bồ Đề dạ Bồ Đề dạ ta bà ha"
        ),
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 57 - 70)",
            "57. Tất đà du nghệ • 58. Thất bàn ra dạ • 59. Ta bà ha • 60. Na ra cẩn trì • 61. Ta bà ha • 62. Ma ra na ra • 63. Ta bà ha • 64. Tất ra tăng a mục khê da • 65. Ta bà ha • 66. Ta bà ma ha a tất đà dạ • 67. Ta bà ha • 68. Giả kiết ra a tất đà dạ • 69. Ta bà ha • 70. Ba đà ma yết tất đà dạ.",
            "Na ra cẩn trì ta bà ha"
        ),
        (
            "Chú Đại Bi - TT. Thích Trí Thoát (Câu 71 - 84 Viên Mãn)",
            "71. Ta bà ha • 72. Na ra cẩn trì bàn đà ra dạ • 73. Ta bà ha • 74. Ma bà lợi thắng yết ra dạ • 75. Ta bà ha • 76. Nam mô hắc ra đát na đa ra dạ da • 77. Nam mô a rị da • 78. Bà lô yết đế • 79. Thước bàn ra dạ • 80. Ta bà ha • 81. Án tất điện đô • 82. Mạn đa ra • 83. Bạt đà dạ • 84. Ta bà ha.",
            "Án tất điện đô mạn đa ra bạt đà dạ ta bà ha"
        ),
    ],
    "bat_nha_tam_kinh": [
        (
            "Bát Nhã Ba La Mật Đa Tâm Kinh (Đoạn 1)",
            "Quán Tự Tại Bồ Tát hành thâm Bát Nhã Ba La Mật Đa thời, chiếu kiến ngũ uẩn giai không, độ nhất thiết khổ ách. Xá Lợi Tử, sắc bất dị không, không bất dị sắc, sắc tức thị không, không tức thị sắc, thọ tưởng hành thức, diệc phục như thị.",
            "Chiếu kiến ngũ uẩn giai không"
        ),
        (
            "Bát Nhã Ba La Mật Đa Tâm Kinh (Đoạn 2)",
            "Xá Lợi Tử, thị chư pháp không tướng, bất sanh bất diệt, bất cấu bất tịnh, bất tăng bất giảm. Thị cố không trung vô sắc, vô thọ tưởng hành thức, vô nhãn nhĩ tỷ thiệt thân ý, vô sắc thanh hương vị xúc pháp, vô nhãn giới, nãi chí vô ý thức giới.",
            "Tâm vô quái ngại vô hữu khủng bố"
        ),
        (
            "Bát Nhã Ba La Mật Đa Tâm Kinh (Đoạn 3)",
            "Tam thế chư Phật, y Bát Nhã Ba La Mật Đa cố, đắc A Nậu Đa La Tam Miệu Tam Bồ Đề. Cố thuyết Bát Nhã Ba La Mật Đa chú, tức thuyết chú viết: Yết đế yết đế, ba la yết đế, ba la tăng yết đế, Bồ đề tát bà ha.",
            "Yết đế yết đế ba la tăng yết đế"
        ),
    ],
    "kinh_duoc_su": [
        (
            "Chú Dược Sư Lưu Ly Quang Vương Phật",
            "Nam mô Bạc già phạt đế, Bệ sả xã, lũ rô thích lưu ly, bát lặt bà, hắt ra xà dã. Đát tha yết đa da, A ra hắt đế, Tam miệu tam bột đà da. Đát điệt tha: Án, bệ sả thệ, bệ sả thệ, bệ sả xã, tam một yết đế toà ha. Nguyện cầu tật bệnh tiêu trừ, bá tánh bình an.",
            "Nam Mô Dược Sư Lưu Ly Quang Vương Phật"
        ),
    ],
    "ke_dang_huong": [
        (
            "Kệ Dâng Hương Cúng Dường Tam Bảo",
            "Nguyện đem lòng thành kính, gửi theo đám mây hương, phảng phất khắp mười phương, cúng dường ngôi Tam Bảo. Thề trọn đời giữ đạo, theo tự tính làm lành, cùng pháp giới chúng sinh, cầu Phật từ gia hộ, tâm Bồ Đề kiên cố, xa bể khổ nguồn mê, chóng quay về bờ giác.",
            "Thành tâm dâng hương cúng Phật"
        ),
        (
            "Kệ Tán Phật & Hồi Hướng Công Đức",
            "Phật thân thanh tịnh tựa lưu ly, Phật diện như trăng rằm sáng tỏ. Hào quang rực rỡ chiếu mười phương, từ bi hỷ xả độ muôn loài. Nguyện đem công đức này, hướng về khắp tất cả, đệ tử và chúng sinh, đều trọn thành Phật đạo.",
            "Nguyện cầu quốc thái dân an"
        ),
    ],
    "niem_phat": [
        (
            "Đạo Tràng Đồng Niệm Hồng Danh Phật",
            "Nam Mô Bổn Sư Thích Ca Mâu Ni Phật. Nam Mô Tây Phương Cực Lạc Thế Giới Đại Từ Đại Bi A Di Đà Phật. Nam Mô Đại Từ Đại Bi Cứu Khổ Cứu Nạn Quảng Đại Linh Cảm Quán Thế Âm Bồ Tát. Nam Mô Đại Thế Chí Bồ Tát. Nam Mô Địa Tạng Vương Bồ Tát. Nam Mô Thanh Tịnh Đại Hải Chúng Bồ Tát.",
            "Nam Mô A Di Đà Phật"
        ),
    ]
}

async def _synth_voice_b64(text: str, voice: str, rate: str, pitch: str, volume: str) -> str:
    cache_key = f"{voice}|{rate}|{pitch}|{text}"
    if cache_key in TTS_CACHE:
        return TTS_CACHE[cache_key]
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    audio_stream = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_stream.write(chunk["data"])
    b64 = base64.b64encode(audio_stream.getvalue()).decode("utf-8")
    if len(TTS_CACHE) < 80:
        TTS_CACHE[cache_key] = b64
    return b64

def _split_text_chunks(text: str, max_chars: int = 165) -> list[str]:
    sentences = re.split(r'(?<=[.!?।;:])\s+', text.strip())
    chunks = []
    current = ""
    for s in sentences:
        if not s:
            continue
        if len(current) + len(s) + 1 <= max_chars:
            current = f"{current} {s}".strip()
        else:
            if current:
                chunks.append(current)
            if len(s) <= max_chars:
                current = s
            else:
                # Tách thêm theo dấu phẩy nếu câu quá dài
                sub_parts = s.split(",")
                sub_cur = ""
                for sp in sub_parts:
                    if len(sub_cur) + len(sp) + 2 <= max_chars:
                        sub_cur = f"{sub_cur}, {sp}".strip(", ")
                    else:
                        if sub_cur:
                            chunks.append(sub_cur)
                        sub_cur = sp.strip()
                current = sub_cur
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]

async def _synth_google_tts_b64(text: str) -> str:
    if text in TTS_CACHE:
        return TTS_CACHE[text]
    chunks = _split_text_chunks(text, 165)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    audio_parts = []
    async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
        for ch in chunks:
            url = "https://translate.googleapis.com/translate_tts"
            params = {
                "ie": "UTF-8",
                "tl": "vi",
                "client": "tw-ob",
                "q": ch
            }
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.content:
                audio_parts.append(resp.content)
            else:
                logger.warning(f"TTS chunk status {resp.status_code}")
    if not audio_parts:
        return ""
    b64 = base64.b64encode(b"".join(audio_parts)).decode("utf-8")
    if len(TTS_CACHE) < 120:
        TTS_CACHE[text] = b64
    return b64

async def generate_tts_base64(text: str) -> str:
    try:
        b64 = await _synth_google_tts_b64(text)
        if b64:
            return b64
        return await _synth_voice_b64(text, TTS_VOICE, rate="+2%", pitch="-5Hz", volume="+90%")
    except Exception as e:
        logger.error(f"Lỗi sinh giọng đọc TTS: {e}")
        return ""

async def generate_choir_tts_base64(text: str) -> dict:
    """Sinh âm thanh Đạo Tràng Đồng Tụng (Đã xử lý chống lỗi 403 Clock Skew + Cache RAM)"""
    if text in CHOIR_CACHE:
        return CHOIR_CACHE[text]
    try:
        base_b64 = await _synth_google_tts_b64(text)
        if base_b64:
            res = {"male_audio": base_b64, "female_audio": base_b64}
            if len(CHOIR_CACHE) < 80:
                CHOIR_CACHE[text] = res
            logger.info(f"✅ Đã sinh âm thanh Tụng Kinh MP3 ({len(base_b64) // 1024} KB)")
            return res
    except Exception as e:
        logger.error(f"Lỗi sinh giọng Đạo Tràng Đồng Tụng: {e}")
    return {"male_audio": "", "female_audio": ""}
