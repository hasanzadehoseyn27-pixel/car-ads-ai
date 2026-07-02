"""
لایه‌ی ذخیره‌سازی — «بشکه»: هر آگهی واقعی (is_ad=true) اینجا ذخیره می‌شود.
فعلاً SQLite برای تست محلی؛ بعداً می‌شود به PostgreSQL سوییچ کرد بدون تغییر listener.py.

جدول channels: لیست کانال‌هایی که listener.py باید گوش بدهد — به‌جای لیست ثابت
توی کد، از اینجا (داینامیک) خوانده می‌شود تا بشود از فرانت‌اند کانال اضافه/حذف کرد.

جدول settings: تنظیمات کلید-مقدار عمومی که از فرانت‌اند (داشبورد) قابل تغییرند
و توسط پروسه‌های پایتون (listener.py/llm_pool.py) خوانده می‌شوند — مثلاً فاصله‌ی
حداقل بین تماس‌های AI. چون این تنظیمات از طریق دیتابیس مشترک منتقل می‌شوند،
بین فرانت‌اند (Node) و بک‌اند (Python) هیچ ارتباط مستقیمی لازم نیست.

ستون telegram_date: زمان واقعی که پیام توی خودِ تلگرام پست شده (نه زمانی که
AI پردازشش کرده) — از event.message.date در listener.py گرفته می‌شود و به
وقت تهران ذخیره می‌شود. created_at (زمان پردازش AI) هم برای دیباگ داخلی نگه
داشته می‌شود، ولی نمایش/مرتب‌سازی در تحلیل‌ها (analytics.py) و فرانت‌اند از
همین telegram_date استفاده می‌کند.

جدول price_alerts: قانون‌های هشدار قیمت که کاربر از داشبورد می‌سازد — هر قانون
یک car_name (بدون تفکیک تیپ) و یک بازه‌ی قیمت (min/max) دارد.

جدول alert_matches: هر آگهی جدیدی که با یکی از قانون‌های price_alerts مطابقت
داشته باشد، اینجا ثبت می‌شود تا زنگوله‌ی داشبورد نشانش دهد. ستون seen مشخص
می‌کند که کاربر آن را دیده یا نه.
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

    # مهاجرت نرم: اگه دیتابیس قدیمی‌تر از قبل بدون ستون telegram_date وجود
    # داشته باشد (یعنی از قبل از این آپدیت ساخته شده)، ستون را اضافه می‌کند
    # بدون اینکه داده‌های موجود را پاک کند.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(car_ads)").fetchall()}
    if "telegram_date" not in existing_columns:
        conn.execute("ALTER TABLE car_ads ADD COLUMN telegram_date TEXT")

    conn.commit()
    conn.close()


def save_ad(channel: str, message_id: int, message_text: str, extracted: dict, telegram_date: str | None = None):
    """
    telegram_date: زمان واقعی پست شدن پیام در تلگرام (ISO format، به وقت تهران)،
    که در listener.py از event.message.date گرفته و پاس داده می‌شود.
    اگه به هر دلیلی ارسال نشود (None)، به‌جایش created_at (زمان پردازش) گذاشته
    می‌شود تا هیچ‌وقت این ستون کاملاً خالی نماند.
    """
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
                now_iso,
                telegram_date or now_iso,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def clear_all_ads():
    """
    پاکسازی کامل جدول car_ads — برای ریست خودکار نیمه‌شب (هر شب ساعت ۰۰:۰۰
    به وقت تهران، توسط listener.py صدا زده می‌شود). جدول channels، settings،
    price_alerts دست‌نخورده می‌مانند؛ فقط آگهی‌ها پاک می‌شوند. alert_matches هم
    عمداً پاک می‌شود تا هر روز زنگوله از صفر شروع شود (چون خودِ آگهی‌های مرجعشان
    هم پاک شده‌اند).
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DELETE FROM car_ads")
        conn.execute("DELETE FROM alert_matches")
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


def get_setting(key: str, default: str | None = None) -> str | None:
    """مقدار یک تنظیم را برمی‌گرداند؛ اگه ثبت نشده بود، default برگردانده می‌شود."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """یک تنظیم را ذخیره/بروز می‌کند."""
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
    """
    ثبت یک قانون هشدار قیمت جدید. حداقل یا حداکثر می‌توانند None باشند
    (یعنی «بدون کف» یا «بدون سقف»)، اما هر دو با هم نمی‌توانند None باشند —
    این چک در api.py انجام می‌شود.
    """
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
    """حذف یک قانون هشدار. چون alert_matches با ON DELETE CASCADE تعریف شده، match‌های مرتبط هم خودکار پاک می‌شوند."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM price_alerts WHERE id = ?", (alert_id,))
        conn.commit()
    finally:
        conn.close()


def check_and_record_alert_matches(car_name: str, price_amount: int | None, channel: str, message_id: int) -> int:
    """
    بعد از ذخیره‌ی هر آگهی جدید صدا زده می‌شود (از listener.py). بررسی می‌کند
    آیا car_name و price_amount این آگهی با کدام‌یک از قانون‌های price_alerts
    مطابقت دارد؛ برای هرکدام که match شد، یک ردیف در alert_matches ثبت می‌شود.

    مطابقت فقط بر اساس car_name خام است (بدون در نظر گرفتن trim)، طبق تصمیم
    طراحی — یعنی «پژو ۲۰۶» با هر تیپی می‌تواند قانونی با car_name="پژو ۲۰۶"
    را فعال کند. اگه price_amount آگهی مشخص نباشد (None)، هیچ قانونی برایش
    match نمی‌شود، چون بازه‌ی قیمت قابل بررسی نیست.

    خروجی: تعداد قانون‌هایی که match شدند (برای لاگ‌گیری در listener.py).
    """
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
    """
    لیست آگهی‌های match‌شده — برای مدال زنگوله در داشبورد. جدیدترین‌ها اول.
    هر ردیف شامل car_name خودِ قانون هم هست (alert_car_name) تا کاربر بداند
    این match مربوط به کدام قانون بوده، حتی اگه بعداً قانون تغییر/حذف شود.
    """
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
    """همه‌ی match‌های دیده‌نشده را seen=1 می‌کند — وقتی کاربر مدال زنگوله را باز می‌کند."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE alert_matches SET seen = 1 WHERE seen = 0")
        conn.commit()
    finally:
        conn.close()