"""
export_group_messages.py — یک ابزار دستی و یک‌باره: پیام‌های متنی غیرتکراری
یک گروه/کانال تلگرامی را در یک بازه‌ی زمانی مشخص (پیش‌فرض ۷ روز اخیر)
استخراج و در یک فایل متنی ذخیره می‌کند.

از session جدا (backfill_session، که از قبل لاگین شده) استفاده می‌کند —
هیچ تداخلی با listener.py یا channel_extractor.py ندارد.

غیرتکراری‌سازی بر اساس تطابق دقیق متن پیام (exact match) است.

اجرا:
    py export_group_messages.py <group_username_or_link> [days]

مثال:
    py export_group_messages.py BAZARBOZORGEKHODROIRAN 7
"""
import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

import python_socks
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", "10808"))
PROXY_CONFIG = (python_socks.ProxyType.SOCKS5, PROXY_HOST, PROXY_PORT) if USE_PROXY else None

SESSION_NAME = "backfill_session"  # از session ای که از قبل لاگین شده استفاده می‌کنیم
MAX_MESSAGES_TO_SCAN = 20000  # سقف ایمنی برای گروه‌های بسیار پرترافیک


def _extract_group_username(raw: str) -> str:
    """از یک لینک کامل یا یوزرنیم خام، فقط یوزرنیم خالص را استخراج می‌کند."""
    raw = raw.strip()
    if "t.me/" in raw:
        raw = raw.split("t.me/")[-1]
    return raw.strip("/").lstrip("@")


async def export_messages(group_username: str, days: int) -> None:
    client = TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH,
        proxy=PROXY_CONFIG,
        connection_retries=5,
        retry_delay=3,
        timeout=30,
    )

    await client.connect()
    if not await client.is_user_authorized():
        print("❌ این session هنوز لاگین نشده. یک‌بار «py backfill.py --login» را روی سرور اجرا کن.")
        await client.disconnect()
        return

    try:
        try:
            entity = await client.get_entity(group_username)
        except Exception as e:
            print(f"❌ دسترسی به گروه «{group_username}» ممکن نشد: {e}")
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        seen_texts: set[str] = set()
        unique_messages: list[str] = []
        total_scanned = 0

        print(f"⏳ در حال اسکن پیام‌های «{group_username}» از {days} روز اخیر ...")

        async for message in client.iter_messages(entity, limit=MAX_MESSAGES_TO_SCAN):
            if message.date and message.date < cutoff:
                break
            total_scanned += 1

            text = message.message
            if not text or not text.strip():
                continue

            normalized = text.strip()
            if normalized in seen_texts:
                continue

            seen_texts.add(normalized)
            unique_messages.append(normalized)

        print(f"📊 اسکن کامل شد — {total_scanned} پیام کل بررسی شد، {len(unique_messages)} پیام متنی غیرتکراری پیدا شد.")

        output_path = f"group_export_{group_username}.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"استخراج پیام‌های غیرتکراری گروه «{group_username}» — {days} روز اخیر\n")
            f.write(f"تعداد کل پیام بررسی‌شده: {total_scanned}\n")
            f.write(f"تعداد پیام متنی غیرتکراری: {len(unique_messages)}\n")
            f.write("=" * 70 + "\n\n")
            for idx, msg in enumerate(unique_messages, 1):
                f.write(f"--- پیام {idx} ---\n{msg}\n\n")

        print(f"✅ ذخیره شد در: {output_path}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("استفاده: py export_group_messages.py <group_username_or_link> [days]")
        sys.exit(1)

    group_arg = _extract_group_username(sys.argv[1])
    days_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 7

    asyncio.run(export_messages(group_arg, days_arg))