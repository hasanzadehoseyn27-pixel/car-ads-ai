"""
لایه‌ی تحلیل/تجمیع قیمت‌ها — روی داده‌های «بشکه» (car_ads.db).
برای هر مدل خودرو (car_name)، در یک بازه‌ی زمانی (پیش‌فرض ۲۴ ساعت اخیر)،
حداقل/میانگین/حداکثر قیمت و تعداد آگهی‌ها را محاسبه می‌کند.

این فایل کاملاً مستقل است؛ به listener.py یا db.py تغییری نمی‌دهد و
فقط همان car_ads.db موجود را می‌خوانَد.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

DB_PATH = Path(__file__).parent / "car_ads.db"


def get_price_analytics(hours: int = 24) -> list[dict]:
    """
    خروجی: لیستی از دیکشنری‌ها، هر کدوم برای یک car_name:
        {
            "car_name": str,
            "total_ads": int,    # تعداد کل آگهی‌های این مدل (با/بدون قیمت)
            "priced_ads": int,   # تعداد آگهی‌هایی که قیمت مشخص دارند
            "min_price": int | None,
            "avg_price": int | None,
            "max_price": int | None,
            "last_seen": str,    # آخرین زمان دیده‌شدن (UTC ISO)
        }
    مرتب‌شده بر اساس تعداد آگهی (پرتکرارترین مدل‌ها اول).

    توجه: car_name همان متنی است که AI استخراج کرده (مثلاً «کیا سراتو»).
    اگه یک مدل با چند املای متفاوت استخراج شده باشد (مثلاً «سراتو» و
    «کیا سراتو» جدا حساب می‌شوند) — این یک محدودیت شناخته‌شده در نسخه‌ی
    فعلی است و بعداً می‌شود با نرمال‌سازی اسم مدل (مثلاً قبل از GROUP BY)
    بهترش کرد.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                car_name,
                COUNT(*)            AS total_ads,
                COUNT(price_amount) AS priced_ads,
                MIN(price_amount)   AS min_price,
                AVG(price_amount)   AS avg_price,
                MAX(price_amount)   AS max_price,
                MAX(created_at)     AS last_seen
            FROM car_ads
            WHERE created_at >= ?
              AND car_name IS NOT NULL
              AND TRIM(car_name) != ''
            GROUP BY car_name
            ORDER BY total_ads DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        result.append(
            {
                "car_name": row["car_name"],
                "total_ads": row["total_ads"],
                "priced_ads": row["priced_ads"],
                "min_price": row["min_price"],
                "avg_price": round(row["avg_price"]) if row["avg_price"] is not None else None,
                "max_price": row["max_price"],
                "last_seen": row["last_seen"],
            }
        )
    return result


def get_ads_for_model(car_name: str, hours: int = 24) -> list[dict]:
    """
    همه‌ی آگهی‌های یک مدل خاص (car_name) در بازه‌ی زمانی مشخص را برمی‌گرداند —
    چه با قیمت و چه بدون قیمت. برای نمایش در مدال جزئیات استفاده می‌شود.
    هر ردیف یک فیلد اضافه‌ی telegram_link هم دارد که مستقیم به همان پیام
    اصلی توی تلگرام لینک می‌دهد (channel + message_id را که از قبل
    ذخیره می‌کنیم استفاده می‌کند).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM car_ads
            WHERE created_at >= ?
              AND car_name = ?
            ORDER BY created_at DESC
            """,
            (cutoff, car_name),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def _format_toman(amount):
    if amount is None:
        return "—"
    return f"{amount:,} تومان"


def _print_report(hours: int = 24):
    data = get_price_analytics(hours=hours)
    if not data:
        print(f"هیچ آگهی‌ای در {hours} ساعت اخیر پیدا نشد.")
        return

    print(f"\n📊 تحلیل قیمت — {hours} ساعت اخیر ({len(data)} مدل)\n")
    for item in data:
        print(f"🚗 {item['car_name']}  —  {item['total_ads']} آگهی ({item['priced_ads']} با قیمت مشخص)")
        if item["priced_ads"] > 0:
            print(f"   حداقل:   {_format_toman(item['min_price'])}")
            print(f"   میانگین: {_format_toman(item['avg_price'])}")
            print(f"   حداکثر:  {_format_toman(item['max_price'])}")
        else:
            print("   (هیچ آگهی‌ای با قیمت مشخص نبود)")
        print(f"   آخرین آگهی: {item['last_seen']}")
        print()


if __name__ == "__main__":
    _print_report(hours=24)