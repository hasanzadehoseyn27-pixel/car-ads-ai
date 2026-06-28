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


def _dedupe_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """
    آگهی‌هایی که شماره تلفن + مدل خودرو یکسان دارند، یک «بازنشر» همان آگهی
    در نظر گرفته می‌شوند (مثلاً وقتی فروشنده برای بالا آمدن در کانال دوباره
    پست می‌کند). از هر گروه فقط تازه‌ترین رکورد نگه داشته می‌شود، با یک
    فیلد اضافه‌ی repost_count که تعداد تکرار را نشان می‌دهد.

    آگهی‌هایی که شماره تلفن ندارند قابل تشخیص هویت نیستند، پس هرکدام
    جدا (بدون دیداپ) حساب می‌شوند.

    توجه: این فقط روی نتیجه‌ی محاسبه‌شده اثر می‌گذارد؛ هیچ ردیفی از
    car_ads.db حذف نمی‌شود.
    """
    groups: dict[tuple, dict] = {}
    standalone: list[dict] = []

    for row in rows:
        item = dict(row)
        phone = (item.get("phone") or "").strip()
        if not phone:
            item["repost_count"] = 1
            standalone.append(item)
            continue

        key = (phone, item["car_name"])
        existing = groups.get(key)
        if existing is None or item["created_at"] > existing["created_at"]:
            item["repost_count"] = (existing["repost_count"] + 1) if existing else 1
            groups[key] = item
        else:
            existing["repost_count"] += 1

    return list(groups.values()) + standalone


def get_price_analytics(hours: int = 24) -> list[dict]:
    """
    خروجی: لیستی از دیکشنری‌ها، هر کدوم برای یک car_name:
        {
            "car_name": str,
            "total_ads": int,    # تعداد آگهی‌های یکتا (بعد از دیداپ بازنشرها)
            "priced_ads": int,   # تعداد آگهی‌هایی که قیمت مشخص دارند
            "min_price": int | None,
            "avg_price": int | None,
            "max_price": int | None,
            "last_seen": str,    # آخرین زمان دیده‌شدن (UTC ISO)
        }
    مرتب‌شده بر اساس تعداد آگهی (پرتکرارترین مدل‌ها اول).

    دیداپ: آگهی‌هایی با شماره تلفن + مدل یکسان، یک آگهی حساب می‌شوند
    (جزئیات در _dedupe_rows). داده‌ی خام car_ads.db دست‌نخورده می‌ماند.

    توجه: فقط آگهی‌های ad_type='for_sale' حساب می‌شوند — آگهی‌های «خریدارم»
    (wanted_to_buy) با اینکه در دیتابیس ذخیره می‌مانند، از این تجمیع کنار
    گذاشته می‌شوند، چون «بودجه‌ی پیشنهادی خریدار» قیمت فروش واقعی نیست و
    می‌تواند min/avg/max را گمراه‌کننده کند.

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
            SELECT *
            FROM car_ads
            WHERE created_at >= ?
              AND car_name IS NOT NULL
              AND TRIM(car_name) != ''
              AND ad_type = 'for_sale'
            ORDER BY created_at DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    deduped = _dedupe_rows(rows)

    by_model: dict[str, list[dict]] = {}
    for item in deduped:
        by_model.setdefault(item["car_name"], []).append(item)

    result = []
    for car_name, items in by_model.items():
        prices = [it["price_amount"] for it in items if it["price_amount"] is not None]
        result.append(
            {
                "car_name": car_name,
                "total_ads": len(items),
                "priced_ads": len(prices),
                "min_price": min(prices) if prices else None,
                "avg_price": round(sum(prices) / len(prices)) if prices else None,
                "max_price": max(prices) if prices else None,
                "last_seen": max(it["created_at"] for it in items),
            }
        )

    result.sort(key=lambda x: x["total_ads"], reverse=True)
    return result


def get_ads_for_model(car_name: str, hours: int = 24) -> list[dict]:
    """
    همه‌ی آگهی‌های یک مدل خاص (car_name) در بازه‌ی زمانی مشخص را برمی‌گرداند —
    چه با قیمت و چه بدون قیمت. برای نمایش در مدال جزئیات استفاده می‌شود.
    هر ردیف یک فیلد اضافه‌ی telegram_link هم دارد که مستقیم به همان پیام
    اصلی توی تلگرام لینک می‌دهد (channel + message_id را که از قبل
    ذخیره می‌کنیم استفاده می‌کند).

    توجه: فقط آگهی‌های ad_type='for_sale' برگردانده می‌شوند، با همون منطق
    get_price_analytics (آگهی‌های «خریدارم» را کنار می‌گذاریم تا بودجه‌ی
    پیشنهادی خریدار توی برچسب کمترین/بیشترین قیمت مدال هم اثر نگذارد).
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
              AND ad_type = 'for_sale'
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