"""
لایه‌ی ذخیره‌سازی — «بشکه»: هر آگهی واقعی (is_ad=true) اینجا ذخیره می‌شود.
فعلاً SQLite برای تست محلی؛ بعداً می‌شود به PostgreSQL سوییچ کرد بدون تغییر listener.py.

جدول channels: لیست کانال‌هایی که listener.py باید گوش بدهد.
جدول settings: تنظیمات کلید-مقدار عمومی.
ستون telegram_date: زمان واقعی پست در تلگرام.
جدول price_alerts / alert_matches: سیستم هشدار قیمت.
جدول archived_ads: آرشیو «دیروز» — قبل از پاکسازی نیمه‌شب پر می‌شود.
جدول monitored_groups / channel_extraction_log: استخراج خودکار روزانه‌ی کانال از گروه.
جدول extraction_progress: وضعیت لحظه‌ای یک اجرای در حال انجام استخراج.
جدول message_log: شمارنده‌ی همه‌ی پیام‌های دریافتی (چه آگهی چه غیرآگهی).

توابع get_existing_message_ids_for_channel و count_ads_for_channel_since
در انتهای فایل، مخصوص ابزار «ترمیم/بک‌فیل» (backfill.py) هستند — برای
تشخیص اینکه کدام پیام‌های یک کانال قبلاً به‌عنوان آگهی ذخیره شده‌اند و
کدام هنوز بررسی نشده‌اند.

نکته‌ی مهم درباره‌ی هم‌زمانی: این فایل هم‌زمان توسط چند پروسه نوشته
می‌شود؛ همه‌ی اتصال‌ها از تابع _connect() عبور می‌کنند که WAL mode و
busy_timeout بالا دارد تا خطای «database is locked» رخ ندهد.
"""
import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "car_ads.db"

_CONNECT_TIMEOUT_SECONDS = 10


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=_CONNECT_TIMEOUT_SECONDS)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS car_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            message_text TEXT,
            ad_type TEXT,
            car_name TEXT,
            trim TEXT,
            color TEXT,
            production_year TEXT,
            mileage_km INTEGER,
            city TEXT,
            delivery_unit TEXT,
            delivery_status TEXT,
            phone TEXT,
            price_amount INTEGER,
            price_label TEXT,
            notes TEXT,
            provider_used TEXT,
            created_at TEXT NOT NULL,
            telegram_date TEXT,
            UNIQUE(channel, message_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1,
            added_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_name TEXT NOT NULL,
            min_price INTEGER,
            max_price INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL REFERENCES price_alerts(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            car_name TEXT NOT NULL,
            price_amount INTEGER,
            matched_at TEXT NOT NULL,
            seen INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archived_ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            message_text TEXT,
            ad_type TEXT,
            car_name TEXT,
            trim TEXT,
            color TEXT,
            production_year TEXT,
            mileage_km INTEGER,
            city TEXT,
            delivery_unit TEXT,
            delivery_status TEXT,
            phone TEXT,
            price_amount INTEGER,
            price_label TEXT,
            notes TEXT,
            provider_used TEXT,
            created_at TEXT NOT NULL,
            telegram_date TEXT,
            archived_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monitored_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_username TEXT NOT NULL UNIQUE,
            added_at TEXT NOT NULL,
            last_scanned_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_extraction_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_username TEXT NOT NULL,
            run_at TEXT NOT NULL,
            added_channels TEXT NOT NULL,
            added_count INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS extraction_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            username TEXT NOT NULL,
            title TEXT,
            found_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_extraction_progress_run_id
        ON extraction_progress(run_id)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            received_at TEXT NOT NULL,
            is_ad INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_log_channel
        ON message_log(channel)
    """)

    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(car_ads)").fetchall()}
    if "telegram_date" not in existing_columns:
        conn.execute("ALTER TABLE car_ads ADD COLUMN telegram_date TEXT")

    conn.commit()
    conn.close()


def save_ad(channel: str, message_id: int, message_text: str, extracted: dict, telegram_date: str | None = None):
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO car_ads (
                channel, message_id, message_text, ad_type, car_name, trim, color,
                production_year, mileage_km, city, delivery_unit, delivery_status,
                phone, price_amount, price_label, notes, provider_used, created_at,
                telegram_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel, message_id, message_text,
                extracted.get("ad_type"), extracted.get("car_name"), extracted.get("trim"),
                extracted.get("color"), extracted.get("production_year"), extracted.get("mileage_km"),
                extracted.get("city"), extracted.get("delivery_unit"), extracted.get("delivery_status"),
                extracted.get("phone"), extracted.get("price_amount"), extracted.get("price_label"),
                extracted.get("notes"), extracted.get("_provider_used"),
                now_iso, telegram_date or now_iso,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def archive_yesterday_ads():
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute("DELETE FROM archived_ads")
        conn.execute(
            """
            INSERT INTO archived_ads (
                channel, message_id, message_text, ad_type, car_name, trim, color,
                production_year, mileage_km, city, delivery_unit, delivery_status,
                phone, price_amount, price_label, notes, provider_used, created_at,
                telegram_date, archived_at
            )
            SELECT
                channel, message_id, message_text, ad_type, car_name, trim, color,
                production_year, mileage_km, city, delivery_unit, delivery_status,
                phone, price_amount, price_label, notes, provider_used, created_at,
                telegram_date, ?
            FROM car_ads
            """,
            (now_iso,),
        )
        conn.commit()
    finally:
        conn.close()


def clear_all_ads():
    conn = _connect()
    try:
        conn.execute("DELETE FROM car_ads")
        conn.execute("DELETE FROM alert_matches")
        conn.commit()
    finally:
        conn.close()


def add_channel(username: str):
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO channels (username, active, added_at)
            VALUES (?, 1, ?)
            ON CONFLICT(username) DO UPDATE SET active = 1, added_at = excluded.added_at
            """,
            (username, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def channel_exists_active(username: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM channels WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def remove_channel(username: str):
    conn = _connect()
    try:
        conn.execute("UPDATE channels SET active = 0 WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def list_channels(active_only: bool = False) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        query = "SELECT * FROM channels"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY added_at DESC"
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def get_setting(key: str, default: str | None = None) -> str | None:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )
        conn.commit()
    finally:
        conn.close()


def add_price_alert(car_name: str, min_price: int | None, max_price: int | None) -> int:
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO price_alerts (car_name, min_price, max_price, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (car_name.strip(), min_price, max_price, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_price_alerts() -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM price_alerts ORDER BY id DESC").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def delete_price_alert(alert_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()


def check_and_record_alert_matches(car_name: str, price_amount: int | None, channel: str, message_id: int) -> int:
    if price_amount is None or not car_name:
        return 0

    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        alerts = conn.execute(
            "SELECT * FROM price_alerts WHERE car_name = ? COLLATE NOCASE",
            (car_name.strip(),),
        ).fetchall()

        matched_count = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for alert in alerts:
            min_price = alert["min_price"]
            max_price = alert["max_price"]
            if min_price is not None and price_amount < min_price:
                continue
            if max_price is not None and price_amount > max_price:
                continue

            conn.execute(
                """
                INSERT INTO alert_matches (alert_id, channel, message_id, car_name, price_amount, matched_at, seen)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (int(alert["id"]), channel, message_id, car_name, price_amount, now_iso),
            )
            matched_count += 1

        if matched_count:
            conn.commit()
        return matched_count
    finally:
        conn.close()


def list_alert_matches(unseen_only: bool = False) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT am.*, pa.car_name AS alert_car_name, pa.min_price AS alert_min_price, pa.max_price AS alert_max_price
            FROM alert_matches am
            LEFT JOIN price_alerts pa ON pa.id = am.alert_id
        """
        if unseen_only:
            query += " WHERE am.seen = 0"
        query += " ORDER BY am.matched_at DESC"
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        item["telegram_link"] = f"https://t.me/{item['channel']}/{item['message_id']}"
        result.append(item)
    return result


def mark_all_alert_matches_seen() -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE alert_matches SET seen = 1 WHERE seen = 0")
        conn.commit()
    finally:
        conn.close()


def add_monitored_group(group_username: str, last_scanned_at: str) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO monitored_groups (group_username, added_at, last_scanned_at)
            VALUES (?, ?, ?)
            ON CONFLICT(group_username) DO UPDATE SET last_scanned_at = excluded.last_scanned_at
            """,
            (group_username, now_iso, last_scanned_at),
        )
        conn.commit()
    finally:
        conn.close()


def list_monitored_groups() -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM monitored_groups ORDER BY added_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def remove_monitored_group(group_username: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM monitored_groups WHERE group_username = ?", (group_username,))
        conn.commit()
    finally:
        conn.close()


def update_monitored_group_scan_time(group_username: str, scanned_at: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE monitored_groups SET last_scanned_at = ? WHERE group_username = ?",
            (scanned_at, group_username),
        )
        conn.commit()
    finally:
        conn.close()


def add_extraction_log(group_username: str, run_at: str, added_channels: list[dict]) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO channel_extraction_log (group_username, run_at, added_channels, added_count)
            VALUES (?, ?, ?, ?)
            """,
            (group_username, run_at, json.dumps(added_channels, ensure_ascii=False), len(added_channels)),
        )
        conn.commit()
    finally:
        conn.close()


def list_extraction_logs(group_username: str | None = None, limit: int = 100) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if group_username:
            rows = conn.execute(
                "SELECT * FROM channel_extraction_log WHERE group_username = ? ORDER BY run_at DESC LIMIT ?",
                (group_username, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM channel_extraction_log ORDER BY run_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()

    result = []
    for row in rows:
        item = dict(row)
        try:
            item["added_channels"] = json.loads(item["added_channels"])
        except Exception:
            item["added_channels"] = []
        result.append(item)
    return result


def start_extraction_run() -> str:
    return uuid.uuid4().hex


def record_extraction_progress(run_id: str, username: str, title: str | None) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO extraction_progress (run_id, username, title, found_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, username, title, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def list_extraction_progress(run_id: str) -> list[dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM extraction_progress WHERE run_id = ? ORDER BY found_at ASC",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def clear_extraction_progress(run_id: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM extraction_progress WHERE run_id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def log_received_message(channel: str, is_ad: bool) -> None:
    """
    هر پیامی که از یک کانال فعال دریافت و توسط AI پردازش می‌شود، اینجا
    ثبت می‌شود — چه آگهی تشخیص داده شود چه نه.
    """
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO message_log (channel, received_at, is_ad) VALUES (?, ?, ?)",
            (channel, datetime.now(timezone.utc).isoformat(), 1 if is_ad else 0),
        )
        conn.commit()
    finally:
        conn.close()


def get_message_counts_per_channel() -> list[dict]:
    """
    برای هر کانال، تعداد کل پیام‌های دریافتی امروز (چه آگهی چه غیرآگهی) و
    تعداد آن‌هایی که واقعاً آگهی تشخیص داده شده‌اند را برمی‌گرداند.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                channel,
                COUNT(*) AS total_messages,
                SUM(is_ad) AS ad_messages
            FROM message_log
            GROUP BY channel
            ORDER BY total_messages DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def clear_message_log() -> None:
    """پاکسازی جدول message_log — برای اجرا در کنار پاکسازی نیمه‌شب."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM message_log")
        conn.commit()
    finally:
        conn.close()


def get_existing_message_ids_for_channel(channel: str, since_iso: str) -> set[int]:
    """
    مجموعه‌ی message_id هایی که از این کانال، از since_iso به بعد، از قبل
    توی car_ads ذخیره شده‌اند — برای ابزار «ترمیم/بک‌فیل» استفاده می‌شود تا
    پیام‌هایی که قبلاً بررسی و به‌عنوان آگهی واقعی ذخیره شده‌اند، دوباره به
    AI فرستاده نشوند. توجه: پیام‌هایی که قبلاً بررسی شده ولی is_ad=false
    بوده‌اند، چون در car_ads ذخیره نمی‌شوند، در این مجموعه نیستند — یعنی
    ابزار ترمیم ممکن است بعضی پیام‌های غیرآگهی را دوباره چک کند؛ این یک
    هزینه‌ی قابل‌قبول است، نه یک باگ.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT message_id FROM car_ads WHERE channel = ? COLLATE NOCASE AND COALESCE(telegram_date, created_at) >= ?",
            (channel, since_iso),
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def count_ads_for_channel_since(channel: str, since_iso: str) -> int:
    """تعداد آگهی‌های واقعی ذخیره‌شده‌ی این کانال از since_iso به بعد."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM car_ads WHERE channel = ? COLLATE NOCASE AND COALESCE(telegram_date, created_at) >= ?",
            (channel, since_iso),
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else 0