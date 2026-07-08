"""
لایه‌ی تحلیل/تجمیع قیمت‌ها — روی داده‌های «بشکه» (car_ads.db).
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

DB_PATH = Path(__file__).parent / "car_ads.db"


def _effective_date(item: dict) -> str:
    return item.get("telegram_date") or item.get("created_at") or ""


def _dedupe_rows(rows: list[sqlite3.Row]) -> list[dict]:
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
    if trim and trim.strip():
        return f"{car_name} ({trim.strip()})"
    return car_name


def _matches_search(item: dict, search_lower: str) -> bool:
    fields = [
        item.get("car_name"),
        item.get("trim"),
        item.get("color"),
        item.get("phone"),
        item.get("notes"),
        item.get("message_text"),
        item.get("city"),
        item.get("price_label"),
    ]
    haystack = " ".join(f for f in fields if f).lower()
    return search_lower in haystack


def get_price_analytics(hours: int = 24, only_new: bool = True, search: str | None = None) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT *
            FROM car_ads
            WHERE COALESCE(telegram_date, created_at) >= ?
              AND car_name IS NOT NULL
              AND TRIM(car_name) != ''
              AND ad_type = 'for_sale'
        """
        if only_new:
            query += " AND (mileage_km IS NULL OR mileage_km = 0)"
        query += " ORDER BY COALESCE(telegram_date, created_at) DESC"

        rows = conn.execute(query, (cutoff,)).fetchall()
    finally:
        conn.close()

    deduped = _dedupe_rows(rows)

    if search and search.strip():
        search_lower = search.strip().lower()
        deduped = [item for item in deduped if _matches_search(item, search_lower)]

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


def get_ads_for_model(car_name: str, trim: str | None = None, hours: int = 24, only_new: bool = True) -> list[dict]:
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
            """
            params: tuple = (cutoff, car_name)
        else:
            query = """
                SELECT *
                FROM car_ads
                WHERE COALESCE(telegram_date, created_at) >= ?
                  AND car_name = ?
                  AND trim = ?
                  AND ad_type = 'for_sale'
            """
            params = (cutoff, car_name, trim)

        if only_new:
            query += " AND (mileage_km IS NULL OR mileage_km = 0)"
        query += " ORDER BY COALESCE(telegram_date, created_at) DESC"

        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_ads_by_channel(channel: str, hours: int = 168) -> list[dict]:
    """
    همه‌ی آگهی‌های ذخیره‌شده‌ی یک کانال خاص را برمی‌گرداند (بدون توجه به
    مدل خودرو یا صفر/کارکرده‌بودن) — برای پیدا کردن سریع پیام‌های یک کانال
    مشخص که کاربر شک دارد شاید پردازش نشده باشند. تطبیق نام کانال
    case-insensitive و دقیق (نه substring) است.
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
              AND channel = ? COLLATE NOCASE
            ORDER BY COALESCE(telegram_date, created_at) DESC
            """,
            (cutoff, channel.strip()),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_daily_lowest_prices() -> list[dict]:
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


def get_wanted_ads(hours: int = 168) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM car_ads
            WHERE COALESCE(telegram_date, created_at) >= ?
              AND ad_type = 'wanted_to_buy'
            ORDER BY COALESCE(telegram_date, created_at) DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_no_price_ads(hours: int = 168) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM car_ads
            WHERE COALESCE(telegram_date, created_at) >= ?
              AND ad_type = 'for_sale'
              AND price_amount IS NULL
            ORDER BY COALESCE(telegram_date, created_at) DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_used_cars_report(hours: int = 24) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM car_ads
            WHERE COALESCE(telegram_date, created_at) >= ?
              AND ad_type = 'for_sale'
              AND mileage_km IS NOT NULL
              AND mileage_km > 0
            ORDER BY car_name ASC, price_amount ASC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def get_archived_ads() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM archived_ads
            WHERE ad_type = 'for_sale'
              AND price_amount IS NOT NULL
            ORDER BY price_amount ASC
            """
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