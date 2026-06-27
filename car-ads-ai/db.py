"""
لایه‌ی ذخیره‌سازی — «بشکه»: هر آگهی واقعی (is_ad=true) اینجا ذخیره می‌شود.
فعلاً SQLite برای تست محلی؛ بعداً می‌شود به PostgreSQL سوییچ کرد بدون تغییر listener.py.

جدول channels: لیست کانال‌هایی که listener.py باید گوش بدهد — به‌جای لیست ثابت
توی کد، از اینجا (داینامیک) خوانده می‌شود تا بشود از فرانت‌اند کانال اضافه/حذف کرد.
"""
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
    conn.commit()
    conn.close()


def save_ad(channel: str, message_id: int, message_text: str, extracted: dict):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO car_ads (
                channel, message_id, message_text, ad_type, car_name, trim, color,
                production_year, mileage_km, city, delivery_unit, delivery_status,
                phone, price_amount, price_label, notes, provider_used, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                channel,
                message_id,
                message_text,
                extracted.get("ad_type"),
                extracted.get("car_name"),
                extracted.get("trim"),
                extracted.get("color"),
                extracted.get("production_year"),
                extracted.get("mileage_km"),
                extracted.get("city"),
                extracted.get("delivery_unit"),
                extracted.get("delivery_status"),
                extracted.get("phone"),
                extracted.get("price_amount"),
                extracted.get("price_label"),
                extracted.get("notes"),
                extracted.get("_provider_used"),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def add_channel(username: str):
    """
    افزودن یک کانال جدید، یا فعال‌سازی دوباره‌ی کانالی که قبلاً غیرفعال شده بود.
    added_at هر بار به «الان» بروز می‌شود — یعنی همون لحظه‌ی فعال‌شدن، طبق
    اصل بشکه‌ی خالی (پیام‌های جدید از این لحظه به بعد پردازش می‌شوند).
    """
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


def remove_channel(username: str):
    """
    غیرفعال‌کردن یک کانال — رکورد حذف نمی‌شود، فقط active=0 می‌شود تا تاریخچه
    بماند و اگه دوباره فعال شد، نیازی به join مجدد توی تلگرام نباشد.
    """
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