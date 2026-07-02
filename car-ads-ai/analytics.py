"""
لایه‌ی تحلیل/تجمیع قیمت‌ها — روی داده‌های «بشکه» (car_ads.db).
برای هر مدل خودرو (car_name)، در یک بازه‌ی زمانی (پیش‌فرض ۲۴ ساعت اخیر)،
حداقل/میانگین/حداکثر قیمت و تعداد آگهی‌ها را محاسبه می‌کند.

تمام فیلترها/مرتب‌سازی‌های زمانی این فایل روی telegram_date (زمان واقعی پست
در تلگرام) انجام می‌شود، نه created_at (زمان پردازش AI) — چون telegram_date
نشان‌دهنده‌ی زمان واقعی آگهی است.

این فایل کاملاً مستقل است؛ به listener.py یا db.py تغییری نمی‌دهد و
فقط همان car_ads.db موجود را می‌خوانَد.
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

DB_PATH = Path(__file__).parent / "car_ads.db"


def _effective_date(item: dict) -> str:
    """telegram_date اگه موجود بود، وگرنه created_at به‌عنوان جایگزین (برای رکوردهای خیلی قدیمی‌تر از قبل این آپدیت)."""
    return item.get("telegram_date") or item.get("created_at") or ""


def _dedupe_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """
    آگهی‌هایی که شماره تلفن + مدل خودرو یکسان دارند، یک «بازنشر» همان آگهی
    در نظر گرفته می‌شوند (مثلاً وقتی فروشنده برای بالا آمدن در کانال دوباره
    پست می‌کند). از هر گروه فقط تازه‌ترین رکورد (بر اساس telegram_date) نگه
    داشته می‌شود، با یک فیلد اضافه‌ی repost_count که تعداد تکرار را نشان می‌دهد.

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

        key = (phone, item["car_name"], item.get("trim"))
        existing = groups.get(key)
        if existing is None or _effective_date(item) > _effective_date(existing):
            item["repost_count"] = (existing["repost_count"] + 1) if existing else 1
            groups[key] = item
        else:
            existing["repost_count"] += 1

    return list(groups.values()) + standalone


def _display_name(car_name: str, trim: str | None) -> str:
    """نام نمایشی ترکیبی — مثلاً «دنا (دنده‌ای)» — وقتی تیپ مشخص باشد."""
    if trim and trim.strip():
        return f"{car_name} ({trim.strip()})"
    return car_name


def get_price_analytics(hours: int = 24) -> list[dict]:
    """
    خروجی: لیستی از دیکشنری‌ها، هر کدوم برای یک ترکیب (car_name, trim):
        {
            "car_name": str,
            "trim": str | None,
            "display_name": str,   # مثلاً "دنا (دنده‌ای)" یا فقط "دنا" اگه تیپ نداشت
            "total_ads": int,    # تعداد آگهی‌های یکتا (بعد از دیداپ بازنشرها)
            "priced_ads": int,   # تعداد آگهی‌هایی که قیمت مشخص دارند
            "min_price": int | None,
            "avg_price": int | None,
            "max_price": int | None,
            "last_seen": str,    # آخرین زمان دیده‌شدن — زمان واقعی پست تلگرام (telegram_date)
        }
    مرتب‌شده بر اساس تعداد آگهی (پرتکرارترین مدل‌ها اول).

    چرا تیپ (trim) هم جزو کلید گروه‌بندی است: برای مدل‌هایی مثل دنا که هم
    دنده‌ای و هم اتومات دارند و قیمتشان واقعاً فرق دارد، قاطی‌کردن همه زیر
    یک میانگین گمراه‌کننده است — هر تیپ ردیف و میانگین جدای خودش را دارد.
    آگهی‌های بدون تیپ مشخص با هم در یک گروه «بدون تیپ» قرار می‌گیرند.

    دیداپ: آگهی‌هایی با شماره تلفن + مدل + تیپ یکسان، یک آگهی حساب می‌شوند
    (جزئیات در _dedupe_rows). داده‌ی خام car_ads.db دست‌نخورده می‌ماند.

    توجه: فقط آگهی‌های ad_type='for_sale' حساب می‌شوند — آگهی‌های «خریدارم»
    (wanted_to_buy) با اینکه در دیتابیس ذخیره می‌مانند، از این تجمیع کنار
    گذاشته می‌شوند، چون «بودجه‌ی پیشنهادی خریدار» قیمت فروش واقعی نیست و
    می‌تواند min/avg/max را گمراه‌کننده کند.

    توجه: car_name همان متنی است که AI استخراج کرده (مثلاً «کیا سراتو»).
    اگه یک مدل با چند املای متفاوت استخراج شده باشد (مثلاً «سراتو» و
    «کیا سراتو»، یا فارسی/انگلیسی) جدا حساب می‌شوند — این یک محدودیت
    شناخته‌شده است؛ پرامپت استخراج (extractor.py) سعی می‌کند با اجباری‌کردن
    نام فارسی همیشگی این مورد را کم کند، ولی خطاهای تک‌حرفی AI کاملاً حذف
    نمی‌شوند.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM car_ads
            WHERE COALESCE(telegram_date, created_at) >= ?
              AND car_name IS NOT NULL
              AND TRIM(car_name) != ''
              AND ad_type = 'for_sale'
            ORDER BY COALESCE(telegram_date, created_at) DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    deduped = _dedupe_rows(rows)

    by_model: dict[tuple, list[dict]] = {}
    for item in deduped:
        key = (item["car_name"], item.get("trim"))
        by_model.setdefault(key, []).append(item)

    result = []
    for (car_name, trim), items in by_model.items():
        prices = [it["price_amount"] for it in items if it["price_amount"] is not None]
        result.append(
            {
                "car_name": car_name,
                "trim": trim,
                "display_name": _display_name(car_name, trim),
                "total_ads": len(items),
                "priced_ads": len(prices),
                "min_price": min(prices) if prices else None,
                "avg_price": round(sum(prices) / len(prices)) if prices else None,
                "max_price": max(prices) if prices else None,
                "last_seen": max(_effective_date(it) for it in items),
            }
        )

    result.sort(key=lambda x: x["total_ads"], reverse=True)
    return result


def get_ads_for_model(car_name: str, trim: str | None = None, hours: int = 24) -> list[dict]:
    """
    همه‌ی آگهی‌های یک ترکیب (car_name, trim) خاص در بازه‌ی زمانی مشخص را
    برمی‌گرداند — چه با قیمت و چه بدون قیمت. برای نمایش در مدال جزئیات
    استفاده می‌شود. هر ردیف یک فیلد اضافه‌ی telegram_link هم دارد که
    مستقیم به همان پیام اصلی توی تلگرام لینک می‌دهد (channel + message_id
    را که از قبل ذخیره می‌کنیم استفاده می‌کند).

    trim=None یعنی گروه «بدون تیپ مشخص» (یعنی ستون trim توی دیتابیس NULL
    است)، نه «هر تیپی». این با همون گروه‌بندی get_price_analytics هم‌خوانه.

    توجه: فقط آگهی‌های ad_type='for_sale' برگردانده می‌شوند، با همون منطق
    get_price_analytics (آگهی‌های «خریدارم» را کنار می‌گذاریم تا بودجه‌ی
    پیشنهادی خریدار توی برچسب کمترین/بیشترین قیمت مدال هم اثر نگذارد).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if trim is None:
            query = """
                SELECT *
                FROM car_ads
                WHERE COALESCE(telegram_date, created_at) >= ?
                  AND car_name = ?
                  AND trim IS NULL
                  AND ad_type = 'for_sale'
                ORDER BY COALESCE(telegram_date, created_at) DESC
            """
            params = (cutoff, car_name)
        else:
            query = """
                SELECT *
                FROM car_ads
                WHERE COALESCE(telegram_date, created_at) >= ?
                  AND car_name = ?
                  AND trim = ?
                  AND ad_type = 'for_sale'
                ORDER BY COALESCE(telegram_date, created_at) DESC
            """
            params = (cutoff, car_name, trim)

        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_daily_lowest_prices() -> list[dict]:
    """
    گزارش روزانه‌ی جدید (صفحه‌ی گزارش در داشبورد): برای هر مدل خودرو
    (بدون تفکیک تیپ)، فقط کمترین قیمت را در میان همه‌ی آگهی‌های for_sale
    فعلی دیتابیس برمی‌گرداند.

    چون کل جدول car_ads هر شب نیمه‌شب پاک می‌شود (طبق midnight_cleanup_loop
    در listener.py)، هرچه الان در دیتابیس هست عملاً «آگهی‌های امروز» است —
    پس نیازی به فیلتر بازه‌ی زمانی جداگانه نیست.

    خروجی: لیستی مرتب‌شده بر اساس نام مدل، هرکدام:
        {
            "car_name": str,
            "min_price": int | None,
            "telegram_link": str | None,   # لینک همان آگهی با کمترین قیمت
        }
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT car_name, price_amount, channel, message_id
            FROM car_ads
            WHERE car_name IS NOT NULL
              AND TRIM(car_name) != ''
              AND ad_type = 'for_sale'
              AND price_amount IS NOT NULL
            """
        ).fetchall()
    finally:
        conn.close()

    best_by_model: dict[str, dict] = {}
    for row in rows:
        car_name = row["car_name"]
        price = row["price_amount"]
        current_best = best_by_model.get(car_name)
        if current_best is None or price < current_best["min_price"]:
            best_by_model[car_name] = {
                "car_name": car_name,
                "min_price": price,
                "telegram_link": f"https://t.me/{row['channel']}/{row['message_id']}",
            }

    result = list(best_by_model.values())
    result.sort(key=lambda x: x["car_name"])
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

    print(f"\n📊 تحلیل قیمت — {hours} ساعت اخیر ({len(data)} گروه)\n")
    for item in data:
        print(f"🚗 {item['display_name']}  —  {item['total_ads']} آگهی ({item['priced_ads']} با قیمت مشخص)")
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