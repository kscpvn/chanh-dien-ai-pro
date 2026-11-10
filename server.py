import asyncio
import json
import logging
import os
import random
import sys
import time
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from config import HOST, PORT, TIKTOK_USERNAME, FB_LIVE_VIDEO_ID, FB_ACCESS_TOKEN, YT_LIVE_VIDEO_ID, AUTO_APPROVE_COMMENTS
from database import init_db, add_activity, get_global_stats, reset_database
from ai_service import (
    sanitize_text, is_clean_text, is_fortune_request,
    detect_avatar_type, generate_ai_fortune, generate_tts_base64,
    generate_choir_tts_base64, SUTRA_LIBRARY
)
from platforms import MultiPlatformManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MasterServer")

app = FastAPI(title="Chánh Điện Online 2.5D AI Multi-Platform Server")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
overlay_clients: set[WebSocket] = set()
control_clients: set[WebSocket] = set()

# Trạng thái kiểm duyệt Human-in-the-Loop
moderation_state = {
    "auto_approve": AUTO_APPROVE_COMMENTS,
    "pending_queue": []  # Danh sách các sự kiện chờ con người bấm Duyệt khi auto_approve = False
}

# Trạng thái Tự Hành 24/7 (Autopilot lúc vắng khách)
last_interaction_time = time.time()
autopilot_state = {
    "enabled": True,
    "interval_seconds": 22
}

audio_settings = {
    "chant_volume": 1.5,         # Âm lượng Tiếng Tụng Kinh TT. Thích Trí Thoát (150%)
    "ambient_volume": 0.25,      # Âm lượng Nhạc Thiền MP3 chạy nền nhẹ nhàng (25%)
    "continuous_chant": True,    # Tự động hiển thị chữ kinh & phát tụng kinh liên tục
    "sutra_mode": "mp3_kinh_phat" # Mặc định: Chú Đại Bi 108 biến (có chữ) - TT. Thích Trí Thoát
}

sutra_cursor = {
    "index": 0,
    "is_generating": False
}

def get_active_sutra_list(mode: str = None) -> list:
    m = mode or audio_settings.get("sutra_mode", "mp3_kinh_phat")
    if m == "mp3_kinh_phat":
        return SUTRA_LIBRARY["chu_dai_bi"]
    if m == "mp3_tam_kinh":
        return SUTRA_LIBRARY["niem_phat"]
    if m in SUTRA_LIBRARY:
        return SUTRA_LIBRARY[m]
    return SUTRA_LIBRARY["chu_dai_bi"]

async def broadcast_next_sutra_verse(force_mode: str = None):
    if sutra_cursor["is_generating"]:
        return
    sutra_cursor["is_generating"] = True
    try:
        if force_mode:
            audio_settings["sutra_mode"] = force_mode
            sutra_cursor["index"] = 0

        mode = audio_settings.get("sutra_mode", "mp3_kinh_phat")
        verses = get_active_sutra_list(mode)
        if not verses:
            return
        idx = sutra_cursor["index"] % len(verses)
        sutra_cursor["index"] = (idx + 1) % len(verses)
        title, full_text, short_chant = verses[idx]

        logger.info(f"[TỤNG KINH CHÁNH ĐIỆN] Đang tụng ({mode}): {title}")
        add_activity("Đạo Tràng Chánh Điện", "system", merit_delta=3, incense_delta=2, wooden_fish_delta=0)

        # Với Chú Đại Bi (TT. Thích Trí Thoát) và Niệm Phật MP3 thật: phát trực tiếp file MP3 gốc,
        # chỉ hiển thị chữ kinh (có chữ) đồng bộ trên màn hình, KHÔNG phát giọng đọc TTS nhân tạo đè lên!
        if mode in ("mp3_kinh_phat", "chu_dai_bi", "mp3_tam_kinh"):
            clean_audio = ""
        else:
            clean_audio = await generate_tts_base64(full_text)

        await broadcast_to_overlays({
            "type": "CHOIR_CHANT",
            "platform": "system",
            "user": "Thượng Tọa Thích Trí Thoát",
            "title": title,
            "text": full_text,
            "short_chant": short_chant,
            "avatar_type": "high_monk",
            "audio": clean_audio,
            "audio_settings": audio_settings
        })
        await broadcast_to_controls()
    finally:
        sutra_cursor["is_generating"] = False

AUTOPILOT_PRAYERS = [
    ("Nam Mô A Di Đà Phật", "Nam Mô A Di Đà Phật. Nam Mô A Di Đà Phật. Nam Mô A Di Đà Phật. Cầu chúc bá tánh thập phương vạn sự bình an, thân tâm thường lạc."),
    ("Tụng Kinh Cầu An", "Nam Mô Bổn Sư Thích Ca Mâu Ni Phật. Nguyện đem công đức này, hướng về khắp tất cả, đệ tử và chúng sinh, đều trọn thành Phật đạo."),
    ("Bát Nhã Tâm Kinh", "Quán Tự Tại Bồ Tát hành thâm Bát Nhã Ba La Mật Đa thời, chiếu kiến ngũ uẩn giai không, độ nhất thiết khổ ách. Tâm an vạn sự an."),
    ("Tích Thiện Phùng Thời", "Nam Mô Đại Từ Đại Bi Quán Thế Âm Bồ Tát. Lòng thành dâng hương tích thiện, phước báu vô lượng, gia đạo hưng long, tài lộc dồi dào."),
    ("Gieo Quẻ Cát Tường", "Tiếng mõ ngân vang thức tỉnh lòng người. Kính mời quý thí chủ bình luận tên và ước nguyện để Chánh Điện dâng sớ cầu an và gieo quẻ đầu năm.")
]

donation_config = {
    "bank_id": "VPBank",
    "account_no": "614577808",
    "account_name": "NGUYEN BA VUONG",
    "note_prefix": "CONG DUC HUONG DEN",
    "show_qr_badge": True,
    "qr_image_url": "/static/qr_vpbank_vuong.png?v=614577808",
    "qr_square_url": "/static/qr_vpbank_square.png?v=614577808"
}

async def broadcast_to_overlays(payload: dict):
    payload["global_stats"] = get_global_stats()
    payload["donation_config"] = donation_config
    msg = json.dumps(payload, ensure_ascii=False)
    dead = set()
    for ws in overlay_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    overlay_clients.difference_update(dead)

async def broadcast_to_controls():
    status_payload = {
        "type": "CONTROL_STATE",
        "auto_approve": moderation_state["auto_approve"],
        "pending_queue": moderation_state["pending_queue"],
        "autopilot_enabled": autopilot_state["enabled"],
        "audio_settings": audio_settings,
        "donation_config": donation_config,
        "platforms": platform_manager.get_status(),
        "global_stats": get_global_stats()
    }
    msg = json.dumps(status_payload, ensure_ascii=False)
    dead = set()
    for ws in control_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    control_clients.difference_update(dead)

async def execute_approved_event(item: dict):
    """Thực thi sự kiện sau khi đã qua kiểm duyệt (Auto hoặc Human-in-the-loop)"""
    global last_interaction_time
    last_interaction_time = time.time()
    platform = item.get("platform", "tiktok")
    event_type = item.get("event_type", "COMMENT")
    user = sanitize_text(item.get("user", "Thí Chủ"), 30)
    text = sanitize_text(item.get("text", ""), 120)
    text_lower = text.lower().strip()
    avatar_type = item.get("avatar_type") or detect_avatar_type(text)

    if event_type == "LIKE":
        count = int(item.get("count", 1))
        add_activity(user, platform, merit_delta=count, incense_delta=1, wooden_fish_delta=count)
        await broadcast_to_overlays({
            "type": "LIKE",
            "platform": platform,
            "user": user,
            "count": count,
            "highlight_btn": "incense"
        })

    elif event_type == "GIFT":
        gift_name = sanitize_text(item.get("gift_name", "HƯƠNG ĐÈN HOA ĐĂNG"), 30).upper()
        repeat_count = int(item.get("repeat_count", 1))
        diamonds = int(item.get("diamonds", 1))
        merit_added = max(20, diamonds * 20)

        add_activity(user, platform, merit_delta=merit_added, incense_delta=3, avatar_type="high_monk", is_vip=True)
        wish_context = f"Ủng hộ hương đèn {repeat_count} {gift_name}, cầu gia đạo bình an, tài lộc hưng thịnh"
        fortune = await generate_ai_fortune(username=user, wish_text=wish_context, is_vip=True)
        poem_clean = fortune["poem"].replace("\n", ", ")
        tts_text = (
            f"Cảm tạ đại thí chủ {user} công đức hương đèn {gift_name}, tích thêm {merit_added} công đức. "
            f"Ứng với {fortune['id']}, {fortune['title']}. Thơ rằng: {poem_clean}. Lời bàn: {fortune['meaning']}"
        )
        audio_b64 = await generate_tts_base64(tts_text)

        await broadcast_to_overlays({
            "type": "GIFT",
            "platform": platform,
            "user": user,
            "gift_name": gift_name,
            "count": repeat_count,
            "merit_added": merit_added,
            "avatar_type": "high_monk",
            "fortune": fortune,
            "audio": audio_b64,
            "highlight_btn": "lamp"
        })

    elif event_type == "COMMENT":
        # TƯƠNG TÁC TỰ NHIÊN TRÊN TIKTOK LIVE / YOUTUBE LIVE / FACEBOOK LIVE (KHÔNG CẦN GÕ SỐ 1, 2, 3...)
        # 1. Nút [🚶 Đứng Lên Thắp Hương]: Gõ "thắp hương", "dâng hương", "lên hương", "thắp nhang", "cắm hương", "lễ phật"
        is_incense_cmd = (
            text_lower == "1"
            or text_lower.startswith("1 ")
            or any(k in text_lower for k in (
                "thắp hương", "thap huong", "dâng hương", "dang huong",
                "lên hương", "len huong", "thắp nhang", "thap nhang",
                "cắm hương", "nén nhang", "lễ phật", "vái phật"
            ))
        )
        # 2. Nút [🧘 Ngồi Thiền Tại Chỗ]: Gõ "ngồi thiền", "tọa thiền", "tĩnh tọa", "thiền định"
        is_meditate_cmd = (
            text_lower == "2"
            or text_lower.startswith("2 ")
            or any(k in text_lower for k in ("ngồi thiền", "ngoi thien", "tọa thiền", "tĩnh tọa", "ngồi tại chỗ", "thiền định"))
        )
        # 3. Nút [🔄 Đổi Chỗ / Lên Hàng Đầu]: Gõ "đổi chỗ", "chuyển chỗ", "cho tui lên", "lên trên", "gần phật"
        is_move_cmd = (
            text_lower == "3"
            or text_lower.startswith("3 ")
            or any(k in text_lower for k in ("đổi chỗ", "doi cho", "chuyển chỗ", "cho tui lên", "lên hàng đầu", "lên trên", "gần phật"))
        )
        # 4. Nút [✍️ Đặt Tên & Cầu Nguyện]: Gõ "đặt tên ...", "tên tôi là ...", "an vị ..."
        is_name_cmd = (
            text_lower.startswith("4 ")
            or text_lower.startswith("đặt tên")
            or text_lower.startswith("dat ten")
            or text_lower.startswith("tên là")
            or text_lower.startswith("an vị")
            or (avatar_type and len(text.split()) <= 2 and not is_fortune_request(text))
        )
        # 5. Nút [🎋 Xin Quẻ AI]: Gõ "xin quẻ", "rút quẻ", "gieo quẻ", "xin xăm", "quẻ tình duyên", "quẻ tài lộc"...
        is_fortune_cmd = (
            text_lower == "5"
            or text_lower.startswith("5 ")
            or is_fortune_request(text)
            or any(k in text_lower for k in ("xin quẻ", "xin que", "rút quẻ", "gieo quẻ", "xin xăm", "bói quẻ"))
        )
        # 6. Nút [🏮 Ủng Hộ Hương Đèn / Cúng Nhang Đèn]: Gõ "hương đèn", "nhang đèn", "cúng dường", "hoa đăng", "đã ck", "stk", "mã qr"
        is_lamp_cmd = (
            text_lower == "6"
            or text_lower.startswith("6 ")
            or any(k in text_lower for k in (
                "hương đèn", "huong den", "nhang đèn", "nhang den",
                "dâng đèn", "hoa đăng", "cúng dường", "cung duong",
                "ủng hộ", "ung ho", "công đức", "đã ck", "da ck",
                "chuyển khoản", "stk", "mã qr", "qr cúng"
            ))
        )

        if is_lamp_cmd:
            merit_added = 100
            add_activity(user, platform, merit_delta=merit_added, incense_delta=3, avatar_type="high_monk", is_vip=True)
            tts_text = f"Nam Mô A Di Đà Phật. Cảm niệm công đức đại thí chủ {user} phát tâm cúng dường hương đèn Tam Bảo, tích thêm {merit_added} công đức."
            audio_b64 = await generate_tts_base64(tts_text)
            await broadcast_to_overlays({
                "type": "GIFT",
                "platform": platform,
                "user": user,
                "gift_name": "CÚNG HƯƠNG ĐÈN TAM BẢO",
                "count": 1,
                "merit_added": merit_added,
                "avatar_type": "high_monk",
                "audio": audio_b64,
                "highlight_btn": "lamp",
                "pop_qr_spotlight": True
            })
        elif is_incense_cmd:
            wish_msg = text[1:].strip() if text_lower.startswith("1") else text
            if not wish_msg or wish_msg == "1":
                wish_msg = "Thành tâm đứng lên dâng hương cầu bình an 🙏"
            add_activity(user, platform, merit_delta=10, incense_delta=3, avatar_type=avatar_type or None)
            tts_text = f"Thí chủ {user} bước lên trước Đỉnh Đồng dâng ba nén tâm hương, cầu nguyện: {wish_msg[:55]}"
            audio_b64 = await generate_tts_base64(tts_text)
            await broadcast_to_overlays({
                "type": "STAND_INCENSE",
                "platform": platform,
                "user": user,
                "text": wish_msg,
                "avatar_type": avatar_type or "male",
                "merit_added": 10,
                "audio": audio_b64,
                "highlight_btn": "incense"
            })
        elif is_meditate_cmd:
            wish_msg = text[1:].strip() if text_lower.startswith("2") else text
            if not wish_msg or wish_msg == "2":
                wish_msg = "Nam Mô A Di Đà Phật 🙏🙏🙏"
            add_activity(user, platform, merit_delta=8, incense_delta=1, avatar_type=avatar_type or None)
            await broadcast_to_overlays({
                "type": "SIT_MEDITATE",
                "platform": platform,
                "user": user,
                "text": wish_msg,
                "avatar_type": avatar_type or "male",
                "merit_added": 8,
                "highlight_btn": "meditate"
            })
        elif is_move_cmd:
            wish_msg = text[1:].strip() if text_lower.startswith("3") else text
            if not wish_msg or wish_msg == "3":
                wish_msg = "Đang đổi chỗ lên gần Đức Phật 🙏"
            add_activity(user, platform, merit_delta=5, incense_delta=1, avatar_type=avatar_type or None)
            await broadcast_to_overlays({
                "type": "CHANGE_SEAT",
                "platform": platform,
                "user": user,
                "text": wish_msg,
                "avatar_type": avatar_type or "male",
                "highlight_btn": "move"
            })
        elif is_name_cmd:
            clean_name = user
            wish_msg = text
            for prefix in ("4 ", "đặt tên:", "đặt tên ", "dat ten ", "an vị: ", "an vị "):
                if text_lower.startswith(prefix):
                    extracted = text[len(prefix):].strip()
                    if extracted:
                        parts = extracted.split("-", 1)
                        clean_name = sanitize_text(parts[0].strip(), 26) or user
                        wish_msg = sanitize_text(parts[1].strip(), 80) if len(parts) > 1 else "Nam Mô A Di Đà Phật 🙏"
                    break
            chosen_av = avatar_type or "male"
            add_activity(clean_name, platform, merit_delta=5, incense_delta=1, avatar_type=chosen_av)
            tts_text = f"Phật tử {clean_name} thành tâm cầu nguyện: {wish_msg[:50]}"
            audio_b64 = await generate_tts_base64(tts_text)
            await broadcast_to_overlays({
                "type": "AVATAR_CHANGE",
                "platform": platform,
                "user": clean_name,
                "avatar_type": chosen_av,
                "text": wish_msg,
                "audio": audio_b64,
                "highlight_btn": "name"
            })
        elif is_fortune_cmd:
            wish_query = text[2:].strip() if text_lower.startswith("5 ") else text
            if not wish_query or wish_query == "5":
                wish_query = "Xin quẻ cầu bình an, tài lộc hanh thông"
            add_activity(user, platform, merit_delta=15, incense_delta=1, avatar_type=avatar_type or None)
            fortune = await generate_ai_fortune(username=user, wish_text=wish_query, is_vip=False)
            poem_clean = fortune["poem"].replace("\n", ", ")
            tts_text = (
                f"Thí chủ {user} rút được {fortune['id']}, {fortune['rank']}, {fortune['title']}. "
                f"Thơ rằng: {poem_clean}. Lời bàn: {fortune['meaning']}"
            )
            audio_b64 = await generate_tts_base64(tts_text)
            await broadcast_to_overlays({
                "type": "FORTUNE",
                "platform": platform,
                "user": user,
                "text": wish_query,
                "avatar_type": avatar_type or "male",
                "fortune": fortune,
                "audio": audio_b64,
                "highlight_btn": "fortune"
            })
        else:
            add_activity(user, platform, merit_delta=5, incense_delta=1, avatar_type=avatar_type or None)
            tts_text = f"Thí chủ {user} cầu nguyện: {text[:55]}"
            audio_b64 = await generate_tts_base64(tts_text)
            await broadcast_to_overlays({
                "type": "COMMENT",
                "platform": platform,
                "user": user,
                "text": text,
                "avatar_type": avatar_type or "male",
                "audio": audio_b64,
                "highlight_btn": "name"
            })

    await broadcast_to_controls()

async def handle_platform_event(platform: str, event_type: str, user: str, text: str = "",
                                count: int = 1, gift_name: str = "ROSE", repeat_count: int = 1, diamonds: int = 1):
    if event_type == "COMMENT" and not is_clean_text(text):
        logger.warning(f"Đã chặn bình luận vi phạm từ [{user}]: {text}")
        return

    event_obj = {
        "id": str(uuid.uuid4())[:8],
        "platform": platform,
        "event_type": event_type,
        "user": user,
        "text": text,
        "count": count,
        "gift_name": gift_name,
        "repeat_count": repeat_count,
        "diamonds": diamonds
    }

    # LIKE và GIFT luôn chạy ngay; COMMENT đi qua chế độ Human-in-the-loop nếu tắt auto_approve
    if event_type in ("LIKE", "GIFT") or moderation_state["auto_approve"]:
        await execute_approved_event(event_obj)
    else:
        moderation_state["pending_queue"].append(event_obj)
        if len(moderation_state["pending_queue"]) > 30:
            moderation_state["pending_queue"].pop(0)
        await broadcast_to_controls()

platform_manager = MultiPlatformManager(event_callback=handle_platform_event)

async def autopilot_loop():
    global last_interaction_time
    logger.info("Chế độ Đạo Tràng Đồng Tụng Liên Tục 24/7 đã sẵn sàng.")
    await asyncio.sleep(2)
    if overlay_clients and autopilot_state["enabled"]:
        await broadcast_next_sutra_verse()
    while True:
        await asyncio.sleep(6)
        if not autopilot_state["enabled"]:
            continue
        now = time.time()
        if now - last_interaction_time >= autopilot_state["interval_seconds"]:
            last_interaction_time = now
            if overlay_clients:
                await broadcast_next_sutra_verse()

@app.on_event("startup")
async def on_startup():
    init_db()
    asyncio.create_task(autopilot_loop())
    logger.info(f"🚀 Hệ thống khởi chạy! Mở Overlay OBS: http://{HOST}:{PORT}/overlay")
    logger.info(f"🎛️ Mở Bảng Điều Khiển (Control Panel): http://{HOST}:{PORT}/control")

@app.get("/", response_class=HTMLResponse)
@app.get("/phattu", response_class=HTMLResponse)
@app.get("/overlay", response_class=HTMLResponse)
async def serve_overlay():
    with open(os.path.join(STATIC_DIR, "overlay.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/control", response_class=HTMLResponse)
async def serve_control():
    with open(os.path.join(STATIC_DIR, "control.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/overlay")
async def ws_overlay_endpoint(websocket: WebSocket):
    await websocket.accept()
    overlay_clients.add(websocket)
    await websocket.send_text(json.dumps({
        "type": "INIT",
        "global_stats": get_global_stats(),
        "audio_settings": audio_settings,
        "donation_config": donation_config
    }, ensure_ascii=False))
    if autopilot_state["enabled"]:
        asyncio.create_task(broadcast_next_sutra_verse())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        overlay_clients.discard(websocket)

@app.websocket("/ws/control")
async def ws_control_endpoint(websocket: WebSocket):
    await websocket.accept()
    control_clients.add(websocket)
    await broadcast_to_controls()
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        control_clients.discard(websocket)

class PlatformConnectReq(BaseModel):
    platform: str
    action: str
    tiktok_username: str = ""
    fb_video_id: str = ""
    fb_access_token: str = ""
    yt_video_id: str = ""

@app.post("/api/platform")
async def api_platform(req: PlatformConnectReq):
    if req.platform == "tiktok":
        if req.action == "start":
            await platform_manager.start_tiktok(req.tiktok_username or TIKTOK_USERNAME)
        else:
            await platform_manager.stop_tiktok()
    elif req.platform == "facebook":
        if req.action == "start":
            await platform_manager.start_facebook(req.fb_video_id or FB_LIVE_VIDEO_ID, req.fb_access_token or FB_ACCESS_TOKEN)
        else:
            await platform_manager.stop_facebook()
    elif req.platform == "youtube":
        if req.action == "start":
            await platform_manager.start_youtube(req.yt_video_id or YT_LIVE_VIDEO_ID)
        else:
            await platform_manager.stop_youtube()
    await broadcast_to_controls()
    return JSONResponse({"status": "ok", "platforms": platform_manager.get_status()})

class ModerationReq(BaseModel):
    action: str  # "toggle_auto", "approve", "reject", "reset_db"
    item_id: str = ""
    auto_approve: bool = True

@app.post("/api/moderation")
async def api_moderation(req: ModerationReq):
    if req.action == "toggle_auto":
        moderation_state["auto_approve"] = req.auto_approve
    elif req.action == "approve":
        for idx, item in enumerate(moderation_state["pending_queue"]):
            if item["id"] == req.item_id:
                approved_item = moderation_state["pending_queue"].pop(idx)
                await execute_approved_event(approved_item)
                break
    elif req.action == "reject":
        moderation_state["pending_queue"] = [i for i in moderation_state["pending_queue"] if i["id"] != req.item_id]
    elif req.action == "reset_db":
        reset_database()
        await broadcast_to_overlays({"type": "INIT"})
    await broadcast_to_controls()
    return JSONResponse({"status": "ok"})

class AutopilotReq(BaseModel):
    enabled: bool

@app.post("/api/autopilot")
async def api_autopilot(req: AutopilotReq):
    autopilot_state["enabled"] = req.enabled
    await broadcast_to_controls()
    return JSONResponse({"status": "ok", "autopilot_enabled": autopilot_state["enabled"]})

class AudioControlReq(BaseModel):
    action: str  # "update_volume", "knock_wooden_fish", "ring_bell", "chant_now", "next_sutra", "select_sutra"
    chant_volume: float = 2.4
    wooden_fish_volume: float = 1.8
    ambient_volume: float = 1.4
    auto_wooden_fish: bool = True
    continuous_chant: bool = True
    sutra_mode: str = "all"
    knocks: int = 10

@app.post("/api/audio_control")
async def api_audio_control(req: AudioControlReq):
    global last_interaction_time
    if req.action == "update_volume":
        audio_settings["chant_volume"] = req.chant_volume
        audio_settings["wooden_fish_volume"] = req.wooden_fish_volume
        audio_settings["ambient_volume"] = req.ambient_volume
        audio_settings["auto_wooden_fish"] = req.auto_wooden_fish
        audio_settings["continuous_chant"] = req.continuous_chant
        await broadcast_to_overlays({
            "type": "AUDIO_SETTINGS",
            "audio_settings": audio_settings
        })
    elif req.action == "knock_wooden_fish":
        add_activity("Chánh Điện AI", "system", merit_delta=req.knocks, wooden_fish_delta=req.knocks)
        await broadcast_to_overlays({
            "type": "WOODEN_FISH_BURST",
            "knocks": req.knocks
        })
    elif req.action == "ring_bell":
        await broadcast_to_overlays({
            "type": "RING_TEMPLE_BELL"
        })
    elif req.action in ("chant_now", "next_sutra"):
        last_interaction_time = time.time()
        asyncio.create_task(broadcast_next_sutra_verse())
    elif req.action == "select_sutra":
        last_interaction_time = time.time()
        asyncio.create_task(broadcast_next_sutra_verse(force_mode=req.sutra_mode))
    await broadcast_to_controls()
    return JSONResponse({"status": "ok", "audio_settings": audio_settings})

class CameraZoomReq(BaseModel):
    count: int

@app.post("/api/test_camera_zoom")
async def api_test_camera_zoom(req: CameraZoomReq):
    await broadcast_to_overlays({
        "type": "SET_DEVOTEES_COUNT",
        "count": req.count
    })
    return JSONResponse({"status": "ok", "count": req.count})

class SimulateReq(BaseModel):
    platform: str = "tiktok"
    event_type: str = "FORTUNE"
    user: str = "Bá Vương"
    text: str = "Xin quẻ triển khai dự án mới tại Hải Phòng"
    gift_name: str = "ROSE"
    diamonds: int = 1

@app.post("/api/simulate")
async def api_simulate(req: SimulateReq):
    await handle_platform_event(
        platform=req.platform,
        event_type=req.event_type,
        user=req.user,
        text=req.text,
        gift_name=req.gift_name,
        repeat_count=1,
        diamonds=req.diamonds
    )
    return JSONResponse({"status": "simulated"})

class ViewerActionReq(BaseModel):
    action_type: str  # "set_name", "ask_fortune", "light_incense", "donate_lamp"
    user: str = "Thí Chủ Thiện Tâm"
    text: str = ""
    avatar_type: str = "male"
    offering_name: str = "ĐÈN HOA ĐĂNG LIÊN HOA"
    diamonds: int = 3

@app.post("/api/viewer_action")
async def api_viewer_action(req: ViewerActionReq):
    user_clean = sanitize_text(req.user or "Phật Tử Thiện Tâm", 30)
    wish_clean = sanitize_text(req.text or "", 90)
    av_clean = req.avatar_type or "female"

    if req.action_type in ("light_incense", "stand_incense"):
        wish = wish_clean or "Thành tâm đứng lên dâng hương cầu bình an 🙏"
        add_activity(user_clean, "web", merit_delta=15, incense_delta=3, avatar_type=av_clean)
        await broadcast_to_overlays({
            "type": "STAND_INCENSE",
            "platform": "web",
            "user": user_clean,
            "text": wish,
            "avatar_type": av_clean,
            "merit_added": 15,
            "highlight_btn": "incense"
        })
    elif req.action_type == "sit_meditate":
        wish = wish_clean or "Nam Mô A Di Đà Phật 🙏🙏🙏"
        add_activity(user_clean, "web", merit_delta=10, incense_delta=1, avatar_type=av_clean)
        await broadcast_to_overlays({
            "type": "SIT_MEDITATE",
            "platform": "web",
            "user": user_clean,
            "text": wish,
            "avatar_type": av_clean,
            "merit_added": 10,
            "highlight_btn": "meditate"
        })
    elif req.action_type == "change_seat":
        wish = wish_clean or "Đang đổi chỗ"
        add_activity(user_clean, "web", merit_delta=5, incense_delta=1, avatar_type=av_clean)
        await broadcast_to_overlays({
            "type": "CHANGE_SEAT",
            "platform": "web",
            "user": user_clean,
            "text": wish,
            "avatar_type": av_clean,
            "highlight_btn": "move"
        })
    elif req.action_type == "set_name":
        wish = wish_clean or "Cầu gia đạo bình an, vạn sự hanh thông 🙏"
        add_activity(user_clean, "web", merit_delta=5, incense_delta=1, avatar_type=av_clean)
        await broadcast_to_overlays({
            "type": "AVATAR_CHANGE",
            "platform": "web",
            "user": user_clean,
            "avatar_type": av_clean,
            "text": wish,
            "highlight_btn": "name"
        })
    elif req.action_type == "chat":
        msg = wish_clean or "Nam Mô A Di Đà Phật 🙏"
        add_activity(user_clean, "web", merit_delta=5, incense_delta=1, avatar_type=av_clean)
        await broadcast_to_overlays({
            "type": "COMMENT",
            "platform": "web",
            "user": user_clean,
            "avatar_type": av_clean,
            "text": msg
        })
    elif req.action_type == "ask_fortune":
        wish = wish_clean or "Xin quẻ cầu gia đạo bình an, tài lộc hanh thông"
        add_activity(user_clean, "web", merit_delta=15, incense_delta=1, avatar_type=av_clean)
        fortune = await generate_ai_fortune(username=user_clean, wish_text=wish, is_vip=False)
        await broadcast_to_overlays({
            "type": "FORTUNE",
            "platform": "web",
            "user": user_clean,
            "text": wish,
            "avatar_type": av_clean,
            "fortune": fortune,
            "highlight_btn": "fortune"
        })
    elif req.action_type == "donate_lamp":
        await execute_approved_event({
            "platform": "web",
            "event_type": "GIFT",
            "user": user_clean,
            "gift_name": req.offering_name or "HƯƠNG ĐÈN TAM BẢO",
            "repeat_count": 1,
            "diamonds": max(1, req.diamonds)
        })
    return JSONResponse({"status": "ok"})

class DonationConfigReq(BaseModel):
    bank_id: str = "VPBank"
    account_no: str = "614577808"
    account_name: str = "NGUYEN BA VUONG"
    note_prefix: str = "CONG DUC HUONG DEN"
    show_qr_badge: bool = True

@app.post("/api/donation_config")
async def api_donation_config(req: DonationConfigReq):
    donation_config["bank_id"] = sanitize_text(req.bank_id, 20)
    donation_config["account_no"] = sanitize_text(req.account_no, 30)
    donation_config["account_name"] = sanitize_text(req.account_name, 50)
    donation_config["note_prefix"] = sanitize_text(req.note_prefix, 40)
    donation_config["show_qr_badge"] = req.show_qr_badge
    await broadcast_to_overlays({
        "type": "DONATION_CONFIG",
        "donation_config": donation_config
    })
    await broadcast_to_controls()
    return JSONResponse({"status": "ok", "donation_config": donation_config})

@app.post("/api/bank_webhook")
async def api_bank_webhook(request: Request):
    """
    Nhận thông báo biến động số dư tự động (SePay / Casso / VietQR) hoặc xác nhận nhanh từ Bảng Điều Khiển
    khi Phật tử chuyển khoản vào tài khoản VPBank 614577808 - NGUYEN BA VUONG.
    """
    try:
        data = await request.json()
    except Exception:
        data = {}

    donor_name = sanitize_text(
        data.get("donor_name") or data.get("subAccount") or data.get("accountName") or "Đại Thí Chủ Công Đức",
        30
    )
    amount_vnd = int(data.get("amount_vnd") or data.get("transferAmount") or data.get("amount") or 50000)
    raw_content = sanitize_text(
        data.get("wish") or data.get("content") or data.get("description") or "Cúng dường hương đèn Tam Bảo, cầu gia đạo bình an",
        90
    )

    # Nếu nội dung chuyển khoản có dạng "CD [Tên] [Lời cầu]", tách tên tự động
    if donor_name == "Đại Thí Chủ Công Đức" and raw_content:
        cleaned = raw_content.replace("CONG DUC HUONG DEN", "").replace("CONG DUC", "").strip()
        if cleaned:
            parts = cleaned.split()
            if len(parts) >= 2:
                donor_name = sanitize_text(" ".join(parts[:3]), 28)

    merit_added = max(50, int(amount_vnd / 500))
    amount_str = f"{amount_vnd:,}".replace(",", ".") + "đ"
    gift_label = f"CÚNG HƯƠNG ĐÈN ({amount_str})"

    add_activity(donor_name, "bank_qr", merit_delta=merit_added, incense_delta=5, avatar_type="high_monk", is_vip=True)
    fortune = await generate_ai_fortune(username=donor_name, wish_text=raw_content, is_vip=True)
    tts_text = (
        f"Nam Mô A Di Đà Phật. Đại Hùng Bảo Điện xin thành tâm tán thán công đức đại thí chủ {donor_name} "
        f"đã phát tâm cúng dường hương đèn Tam Bảo {amount_str}, tích thêm {merit_added} công đức. "
        f"Nguyện cầu hồng ân Tam Bảo gia hộ cho thí chủ {donor_name} gia đạo bình an, vạn sự cát tường như ý."
    )
    audio_b64 = await generate_tts_base64(tts_text)

    await broadcast_to_overlays({
        "type": "GIFT",
        "platform": "bank_qr",
        "user": donor_name,
        "gift_name": gift_label,
        "count": 1,
        "merit_added": merit_added,
        "avatar_type": "high_monk",
        "fortune": fortune,
        "audio": audio_b64,
        "highlight_btn": "lamp",
        "pop_qr_spotlight": True
    })
    await broadcast_to_controls()
    return JSONResponse({"status": "ok", "donor": donor_name, "merit_added": merit_added})

if __name__ == "__main__":
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)
