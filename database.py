import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger("Database")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS global_counters (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            username TEXT PRIMARY KEY,
            platform TEXT DEFAULT 'tiktok',
            score INTEGER NOT NULL DEFAULT 0,
            avatar_type TEXT DEFAULT 'male',
            is_vip INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Khởi tạo giá trị mặc định khớp với ảnh mẫu nếu chưa có
    defaults = [("incense", 697), ("merit", 24979), ("wooden_fish", 2344)]
    for k, v in defaults:
        cur.execute("INSERT OR IGNORE INTO global_counters (key, value) VALUES (?, ?)", (k, v))

    seed_users = [
        ("Đại Thí Chủ M...", "tiktok", 1839, "high_monk", 1),
        ("Diệu Thảo Tâm An", "tiktok", 1440, "female", 1),
        ("Ngọc Anh Nguy...", "tiktok", 1430, "female", 0),
        ("Thỏ", "tiktok", 1200, "novice", 0)
    ]
    cur.execute("SELECT COUNT(*) as cnt FROM leaderboard")
    if cur.fetchone()["cnt"] == 0:
        for u, p, s, a, vip in seed_users:
            cur.execute(
                "INSERT INTO leaderboard (username, platform, score, avatar_type, is_vip) VALUES (?, ?, ?, ?, ?)",
                (u, p, s, a, vip)
            )
    conn.commit()
    conn.close()
    logger.info("SQLite Database đã sẵn sàng.")

def add_activity(username: str, platform: str, merit_delta: int = 0, incense_delta: int = 0,
                 wooden_fish_delta: int = 0, avatar_type: str = None, is_vip: bool = False):
    conn = get_connection()
    cur = conn.cursor()
    if incense_delta > 0:
        cur.execute("UPDATE global_counters SET value = value + ? WHERE key = 'incense'", (incense_delta,))
    if merit_delta > 0:
        cur.execute("UPDATE global_counters SET value = value + ? WHERE key = 'merit'", (merit_delta,))
    if wooden_fish_delta > 0:
        cur.execute("UPDATE global_counters SET value = value + ? WHERE key = 'wooden_fish'", (wooden_fish_delta,))

    if username and merit_delta > 0:
        cur.execute("SELECT score, avatar_type, is_vip FROM leaderboard WHERE username = ?", (username,))
        row = cur.fetchone()
        if row:
            new_score = row["score"] + merit_delta
            new_avatar = avatar_type if avatar_type else row["avatar_type"]
            new_vip = 1 if (is_vip or row["is_vip"]) else 0
            cur.execute("""
                UPDATE leaderboard
                SET score = ?, platform = ?, avatar_type = ?, is_vip = ?, updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
            """, (new_score, platform, new_avatar, new_vip, username))
        else:
            cur.execute("""
                INSERT INTO leaderboard (username, platform, score, avatar_type, is_vip)
                VALUES (?, ?, ?, ?, ?)
            """, (username, platform, merit_delta, avatar_type or "male", 1 if is_vip else 0))

    conn.commit()
    conn.close()

def get_global_stats(top_n: int = 4) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM global_counters")
    counters = {row["key"]: row["value"] for row in cur.fetchall()}

    cur.execute("SELECT username, platform, score, avatar_type, is_vip FROM leaderboard ORDER BY score DESC LIMIT ?", (top_n,))
    lb = [
        {
            "name": row["username"],
            "platform": row["platform"],
            "score": row["score"],
            "avatar_type": row["avatar_type"],
            "is_vip": bool(row["is_vip"])
        }
        for row in cur.fetchall()
    ]
    conn.close()
    return {
        "incense": counters.get("incense", 697),
        "merit": counters.get("merit", 24979),
        "wooden_fish": counters.get("wooden_fish", 2344),
        "leaderboard": lb
    }

def reset_database():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE global_counters SET value = 0")
    cur.execute("DELETE FROM leaderboard")
    conn.commit()
    conn.close()
