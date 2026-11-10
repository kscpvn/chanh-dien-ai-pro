import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from database import init_db, add_activity, get_global_stats
from ai_service import is_clean_text, is_fortune_request, detect_avatar_type, generate_ai_fortune

async def run_all_tests():
    print("1. Kiểm tra khởi tạo SQLite Database...")
    init_db()
    add_activity("TestUser_VIP", "tiktok", merit_delta=100, incense_delta=1, avatar_type="high_monk", is_vip=True)
    stats = get_global_stats()
    assert stats["merit"] >= 24979, "Lỗi cộng điểm Công Đức!"
    print(f"   ✅ SQLite hoạt động chuẩn: {stats['incense']} hương, {stats['merit']} CĐ.")

    print("2. Kiểm tra Bộ lọc từ cấm & Nhận diện Pháp phục (Avatar)...")
    assert not is_clean_text("Đời khó nên sống chó"), "Lỗi lọt từ cấm!"
    assert detect_avatar_type("Cao tăng xin quẻ bình an") == "high_monk", "Lỗi nhận diện cao tăng!"
    assert detect_avatar_type("Chú tiểu quét chùa") == "novice", "Lỗi nhận diện chú tiểu!"
    assert is_fortune_request("Con thành tâm xin xăm tháng này"), "Lỗi nhận diện xin xăm!"
    print("   ✅ Bộ lọc & Nhận diện Avatar hoạt động chính xác 100%.")

    print("3. Kiểm tra Module Rút Quẻ (Gemini API / Fallback DB)...")
    fortune = await generate_ai_fortune("Nguyễn Bá Vương", "Xin quẻ triển khai dự án mới tại Hải Phòng", is_vip=True)
    assert all(k in fortune for k in ("id", "rank", "title", "poem", "meaning")), "Thiếu trường dữ liệu trong Quẻ!"
    print(f"   ✅ Kết quả Quẻ: {fortune['id']} ({fortune['rank']}) - {fortune['title']}")
    print("🎉 TẤT CẢ CÁC BÀI KIỂM THỬ HỆ THỐNG ĐỀU VƯỢT QUA (PASSED)!")

if __name__ == "__main__":
    asyncio.run(run_all_tests())
