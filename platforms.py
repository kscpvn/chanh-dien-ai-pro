import asyncio
import logging
import re
import httpx
try:
    import pytchat
except ImportError:
    pytchat = None
try:
    from TikTokLive import TikTokLiveClient
    from TikTokLive.events import ConnectEvent, CommentEvent, GiftEvent, LikeEvent
except ImportError:
    TikTokLiveClient = None
    ConnectEvent = CommentEvent = GiftEvent = LikeEvent = None

logger = logging.getLogger("Platforms")

class MultiPlatformManager:
    def __init__(self, event_callback):
        self.event_callback = event_callback
        self.tiktok_client = None
        self.tiktok_task = None
        self.tiktok_username = ""
        self.tiktok_connected = False

        self.fb_task = None
        self.fb_video_id = ""
        self.fb_access_token = ""
        self.fb_connected = False
        self.seen_fb_comments = set()

        self.yt_task = None
        self.yt_video_id = ""
        self.yt_connected = False
        self.yt_chat = None

    async def start_tiktok(self, username: str):
        await self.stop_tiktok()
        self.tiktok_username = username if username.startswith("@") else f"@{username}"
        if TikTokLiveClient is None:
            logger.warning("Thư viện TikTokLive chưa khả dụng trên môi trường Python hiện tại. Hãy dùng Simulator hoặc cài đặt TikTokLive.")
            self.tiktok_connected = False
            return
        logger.info(f"Đang kết nối TikTok Live: {self.tiktok_username}...")

        self.tiktok_client = TikTokLiveClient(unique_id=self.tiktok_username)

        @self.tiktok_client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent):
            self.tiktok_connected = True
            logger.info(f"✅ Đã kết nối TikTok Live: {event.unique_id}")

        @self.tiktok_client.on(CommentEvent)
        async def on_comment(event: CommentEvent):
            await self.event_callback(
                platform="tiktok",
                event_type="COMMENT",
                user=event.user.nickname,
                text=event.comment
            )

        @self.tiktok_client.on(LikeEvent)
        async def on_like(event: LikeEvent):
            await self.event_callback(
                platform="tiktok",
                event_type="LIKE",
                user=event.user.nickname,
                count=event.count
            )

        @self.tiktok_client.on(GiftEvent)
        async def on_gift(event: GiftEvent):
            if event.gift.streakable and not event.streaking:
                diamonds = max(1, event.gift.diamond_count) * event.repeat_count
                await self.event_callback(
                    platform="tiktok",
                    event_type="GIFT",
                    user=event.user.nickname,
                    gift_name=event.gift.name,
                    repeat_count=event.repeat_count,
                    diamonds=diamonds
                )

        async def _run():
            try:
                await self.tiktok_client.start()
            except Exception as e:
                self.tiktok_connected = False
                logger.error(f"TikTok Live ngắt kết nối ({self.tiktok_username}): {e}")

        self.tiktok_task = asyncio.create_task(_run())

    async def stop_tiktok(self):
        if self.tiktok_client:
            try:
                await self.tiktok_client.disconnect()
            except Exception:
                pass
        if self.tiktok_task and not self.tiktok_task.done():
            self.tiktok_task.cancel()
        self.tiktok_connected = False
        logger.info("Đã dừng kết nối TikTok Live.")

    async def start_facebook(self, video_id: str, access_token: str):
        await self.stop_facebook()
        self.fb_video_id = video_id.strip()
        self.fb_access_token = access_token.strip()
        if not self.fb_video_id or not self.fb_access_token:
            logger.warning("Thiếu Facebook Live Video ID hoặc Access Token.")
            return

        self.fb_connected = True
        logger.info(f"✅ Bắt đầu lắng nghe Facebook Live Video ID: {self.fb_video_id}")

        async def _poll_fb():
            url = f"https://graph.facebook.com/v19.0/{self.fb_video_id}/comments"
            params = {
                "access_token": self.fb_access_token,
                "order": "reverse_chronological",
                "limit": 15,
                "fields": "id,from,message,created_time"
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                while self.fb_connected:
                    try:
                        resp = await client.get(url, params=params)
                        if resp.status_code == 200:
                            data = resp.json().get("data", [])
                            for item in reversed(data):
                                cid = item.get("id")
                                if cid and cid not in self.seen_fb_comments:
                                    self.seen_fb_comments.add(cid)
                                    user = item.get("from", {}).get("name", "Phật Tử FB")
                                    msg = item.get("message", "")
                                    if msg:
                                        await self.event_callback(
                                            platform="facebook",
                                            event_type="COMMENT",
                                            user=user,
                                            text=msg
                                        )
                        else:
                            logger.warning(f"Facebook Graph API trả về mã {resp.status_code}: {resp.text}")
                    except Exception as e:
                        logger.error(f"Lỗi kết nối Facebook Live: {e}")
                    await asyncio.sleep(2.5)

        self.fb_task = asyncio.create_task(_poll_fb())

    async def stop_facebook(self):
        self.fb_connected = False
        if self.fb_task and not self.fb_task.done():
            self.fb_task.cancel()
        logger.info("Đã dừng kết nối Facebook Live.")

    async def start_youtube(self, video_id_or_url: str):
        await self.stop_youtube()
        vid = video_id_or_url.strip()
        if "watch?v=" in vid:
            vid = vid.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in vid:
            vid = vid.split("youtu.be/")[1].split("?")[0]
        elif "live/" in vid:
            vid = vid.split("live/")[1].split("?")[0]

        self.yt_video_id = vid
        if not self.yt_video_id:
            logger.warning("Thiếu YouTube Live Video ID hoặc URL.")
            return

        self.yt_connected = True
        logger.info(f"✅ Bắt đầu lắng nghe YouTube Live: {self.yt_video_id}")

        async def _poll_yt():
            if pytchat is not None:
                try:
                    loop = asyncio.get_running_loop()
                    self.yt_chat = await loop.run_in_executor(None, pytchat.create, self.yt_video_id)
                    while self.yt_connected and self.yt_chat.is_alive():
                        data = await loop.run_in_executor(None, self.yt_chat.get)
                        for item in data.sync_items():
                            author = item.author.name
                            msg = item.message
                            amount = getattr(item, "amountString", "") or getattr(item, "amount_string", "")
                            if amount:
                                await self.event_callback(
                                    platform="youtube",
                                    event_type="GIFT",
                                    user=author,
                                    gift_name=f"SUPER CHAT {amount}",
                                    repeat_count=1,
                                    diamonds=15
                                )
                            else:
                                await self.event_callback(
                                    platform="youtube",
                                    event_type="COMMENT",
                                    user=author,
                                    text=msg
                                )
                        await asyncio.sleep(2.0)
                    return
                except Exception as e:
                    logger.warning(f"Pytchat lỗi ({e}), chuyển sang chế độ lấy chat trực tiếp qua HTTPX...")

            # Cơ chế dự phòng lấy YouTube Live Chat trực tiếp bằng HTTPX (không cần pytchat hay API Key)
            seen_yt_ids = set()
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            try:
                async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
                    watch_resp = await client.get(f"https://www.youtube.com/watch?v={self.yt_video_id}")
                    html_text = watch_resp.text
                    key_match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html_text)
                    cont_match = re.search(r'"continuation":"([^"]+)"', html_text)
                    if not key_match or not cont_match:
                        logger.warning(f"Không tìm thấy luồng Live Chat đang mở cho video YouTube: {self.yt_video_id}")
                        self.yt_connected = False
                        return
                    api_key = key_match.group(1)
                    continuation = cont_match.group(1)

                    while self.yt_connected and continuation:
                        chat_url = f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={api_key}"
                        payload = {
                            "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                            "continuation": continuation
                        }
                        r = await client.post(chat_url, json=payload)
                        if r.status_code == 200:
                            j = r.json()
                            cont_contents = j.get("continuationContents", {}).get("liveChatContinuation", {})
                            actions = cont_contents.get("actions", [])
                            for act in actions:
                                item = act.get("addChatItemAction", {}).get("item", {})
                                renderer = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                                if renderer:
                                    cid = renderer.get("id", "")
                                    if cid and cid not in seen_yt_ids:
                                        seen_yt_ids.add(cid)
                                        author = renderer.get("authorName", {}).get("simpleText", "Phật Tử YT")
                                        runs = renderer.get("message", {}).get("runs", [])
                                        msg = "".join(run.get("text", "") for run in runs)
                                        if "purchaseAmountText" in renderer:
                                            amt = renderer["purchaseAmountText"].get("simpleText", "SUPER CHAT")
                                            await self.event_callback(
                                                platform="youtube", event_type="GIFT",
                                                user=author, gift_name=f"SUPER CHAT {amt}", repeat_count=1, diamonds=15
                                            )
                                        elif msg:
                                            await self.event_callback(
                                                platform="youtube", event_type="COMMENT",
                                                user=author, text=msg
                                            )
                        await asyncio.sleep(2.5)
            except Exception as e:
                logger.error(f"Lỗi kết nối YouTube Live ({self.yt_video_id}): {e}")
            finally:
                self.yt_connected = False

        self.yt_task = asyncio.create_task(_poll_yt())

    async def stop_youtube(self):
        self.yt_connected = False
        if self.yt_chat:
            try:
                self.yt_chat.terminate()
            except Exception:
                pass
        if self.yt_task and not self.yt_task.done():
            self.yt_task.cancel()
        logger.info("Đã dừng kết nối YouTube Live.")

    def get_status(self) -> dict:
        return {
            "tiktok_username": self.tiktok_username,
            "tiktok_connected": self.tiktok_connected,
            "fb_video_id": self.fb_video_id,
            "fb_connected": self.fb_connected,
            "yt_video_id": self.yt_video_id,
            "yt_connected": self.yt_connected
        }
