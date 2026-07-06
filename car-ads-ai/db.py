"""
لایه‌ی ذخیره‌سازی — «بشکه»: هر آگهی واقعی (is_ad=true) اینجا ذخیره می‌شود.
فعلاً SQLite برای تست محلی؛ بعداً می‌شود به PostgreSQL سوییچ کرد بدون تغییر listener.py.

جدول channels: لیست کانال‌هایی که listener.py باید گوش بدهد.
جدول settings: تنظیمات کلید-مقدار عمومی.
ستون telegram_date: زمان واقعی پست در تلگرام.
جدول price_alerts / alert_matches: سیستم هشدار قیمت.
جدول archived_ads: آرشیو «دیروز» — قبل از پاکسازی نیمه‌شب پر می‌شود.

جدول monitored_groups: لیست سوپرگروه‌هایی که یک‌بار برایشان استخراج کانال
انجام شده و از این پس هر روز به‌صورت خودکار برای کانال‌های جدید چک می‌شوند.
last_scanned_at آخرین لحظه‌ای است که این گروه اسکن شده — اسکن بعدی فقط
پیام‌های بعد از همین لحظه را بررسی می‌کند (نه کل تاریخچه را دوباره).

جدول channel_extraction_log: تاریخچه‌ی هر بار اسکن (چه دستی چه خودکار) —
برای نمایش «هر روز چه کانال جدیدی پیدا شد» در داشبورد.
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "car_ads.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
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

    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(car_ads)").fetchall()}
    if "telegram_date" not in existing_columns:
        conn.execute("ALTER TABLE car_ads ADD COLUMN telegram_date TEXT")

    conn.commit()
    conn.close()


def save_ad(channel: str, message_id: int, message_text: str, extracted: dict, telegram_date: str | None = None):
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM car_ads")
        conn.execute("DELETE FROM alert_matches")
        conn.commit()
    finally:
        conn.close()


def add_channel(username: str):
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT 1 FROM channels WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def remove_channel(username: str):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE channels SET active = 0 WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def list_channels(active_only: bool = False) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM price_alerts ORDER BY id DESC").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def delete_price_alert(alert_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()


def check_and_record_alert_matches(car_name: str, price_amount: int | None, channel: str, message_id: int) -> int:
    if price_amount is None or not car_name:
        return 0

    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE alert_matches SET seen = 1 WHERE seen = 0")
        conn.commit()
    finally:
        conn.close()


def add_monitored_group(group_username: str, last_scanned_at: str) -> None:
    """
    ثبت (یا بروزکردنِ) یک گروه به‌عنوان «مانیتورشونده» — یعنی هر روز به‌صورت
    خودکار برای کانال جدید چک می‌شود. اگه از قبل ثبت شده بود، فقط
    last_scanned_at آن به‌روز می‌شود (added_at دست‌نخورده می‌ماند).
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM monitored_groups ORDER BY added_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def update_monitored_group_scan_time(group_username: str, scanned_at: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE monitored_groups SET last_scanned_at = ? WHERE group_username = ?",
            (scanned_at, group_username),
        )
        conn.commit()
    finally:
        conn.close()


def add_extraction_log(group_username: str, run_at: str, added_channels: list[str]) -> None:
    """
    ثبت یک رکورد در تاریخچه‌ی استخراج — چه دستی (اولین‌بار) چه خودکار
    (اسکن روزانه). added_channels می‌تواند لیست خالی باشد (یعنی آن روز
    کانال جدیدی پیدا نشد) — این با نبود هیچ کانال جدید فرق دارد با نبود
    رکورد اصلاً؛ فرانت‌اند از روی همین لیست خالی تشخیص می‌دهد که پیام
    «هنوز کانال جدید پیدا نشده است» را نشان دهد.
    """
    conn = sqlite3.connect(DB_PATH)
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


def list_extraction_logs(group_username: str | None = None, limit: int = 60) -> list[dict]:
    """
    تاریخچه‌ی استخراج‌ها — جدیدترین اول. اگه group_username داده نشود،
    تاریخچه‌ی همه‌ی گروه‌های مانیتورشونده با هم برگردانده می‌شود.
    """
    conn = sqlite3.connect(DB_PATH)
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