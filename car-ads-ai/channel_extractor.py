"""
channel_extractor.py — استخراج خودکار کانال‌های مبدا از یک گروه تلگرامی که
پست‌های فوروواردشده از کانال‌های مختلف را جمع می‌کند.

از یک session کاملاً جدا و مستقل (channel_extractor_session) استفاده
می‌کند — تا با car_ads_session (که listener.py استفاده می‌کند) تداخل نکند.

قبل از اولین استفاده، این session باید یک‌بار دستی لاگین شود:
    py channel_extractor.py --login

بعد از اولین استخراج دستی یک گروه، آن گروه به‌صورت خودکار به
monitored_groups اضافه می‌شود و از آن پس هر ۲۴ ساعت (daily_scan_loop) فقط
پیام‌های جدید (از آخرین اسکن به بعد) بررسی می‌شوند.

هر اجرای استخراج (چه دستی چه خودکار) یک run_id یکتا دارد؛ هر بار کانال
جدیدی پیدا شود، همان لحظه با record_extraction_progress ثبت می‌شود تا
فرانت‌اند با polling این پیشرفت را تقریباً زنده نشان دهد.
"""
import logging
import os
import re
import sys
import asyncio
from datetime import datetime, timedelta, timezone

import python_socks
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError

from db import (
    add_channel,
    list_channels,
    add_monitored_group,
    list_monitored_groups,
    update_monitored_group_scan_time,
    add_extraction_log,
    start_extraction_run,
    record_extraction_progress,
)

load_dotenv()

logger = logging.getLogger("channel_extractor")

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", "10808"))
PROXY_CONFIG = (python_socks.ProxyType.SOCKS5, PROXY_HOST, PROXY_PORT) if USE_PROXY else None

CONNECT_TIMEOUT_SECONDS = 30
JOIN_TIMEOUT_SECONDS = 20
DEFAULT_EXTRACTION_DAYS = 3
MAX_MESSAGES_TO_SCAN = 5000
DAILY_SCAN_CHECK_INTERVAL_SECONDS = 3600
GROUP_SCAN_GAP_SECONDS = 5

SESSION_NAME = "channel_extractor_session"


def _build_client() -> TelegramClient:
    return TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH,
        proxy=PROXY_CONFIG,
        connection_retries=5,
        retry_delay=3,
        timeout=30,
    )


async def _connect_authorized_client() -> TelegramClient:
    client = _build_client()
    try:
        await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        raise RuntimeError("اتصال به تلگرام بیش از حد طول کشید")

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "این قابلیت هنوز روی سرور لاگین نشده — یک‌بار روی سرور دستور "
            "«py channel_extractor.py --login» را اجرا کن."
        )
    return client


def _normalize_group_link(text: str) -> str | None:
    text = text.strip()
    link_match = re.search(r"(?:https?://)?t\.me/(\+?[A-Za-z0-9_][A-Za-z0-9_\-]*)", text, re.IGNORECASE)
    if link_match:
        value = link_match.group(1).strip()
        return value if value.startswith("+") else value.lstrip("@")
    at_match = re.search(r"@([A-Za-z0-9_]{4,})", text)
    if at_match:
        return at_match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", text):
        return text
    return None


async def _join_if_needed(client: TelegramClient, entity):
    try:
        await asyncio.wait_for(client(JoinChannelRequest(entity)), timeout=JOIN_TIMEOUT_SECONDS)
    except UserAlreadyParticipantError:
        pass
    except Exception:
        pass


async def _scan_forwarded_channels(
    client: TelegramClient, entity, cutoff: datetime, run_id: str | None = None
) -> tuple[dict[str, str | None], int]:
    """
    پیام‌های گروه را از جدیدترین به قدیمی‌ترین می‌خواند تا به cutoff برسد،
    و برای هر پیام فوروواردشده، یوزرنیم و اسم کانال مبدا را جمع می‌کند.

    اگر run_id داده شود، همان لحظه که یک یوزرنیم *تازه* (که قبلاً در این
    اجرا دیده نشده) پیدا شود، فوری با record_extraction_progress ثبت
    می‌شود — این باعث نمایش زنده‌ی پیشرفت در فرانت‌اند می‌شود.

    خروجی: (دیکشنری یوزرنیم -> اسم کانال یا None، تعداد پیام‌های بررسی‌شده)
    """
    found: dict[str, str | None] = {}
    scanned = 0

    async for message in client.iter_messages(entity, limit=MAX_MESSAGES_TO_SCAN):
        scanned += 1
        if message.date and message.date < cutoff:
            break

        fwd = getattr(message, "forward", None)
        if not fwd:
            continue

        try:
            src_chat = await message.get_forward_chat()
        except Exception:
            src_chat = None

        if src_chat is None:
            continue

        src_username = getattr(src_chat, "username", None)
        if not src_username:
            continue

        if src_username not in found:
            src_title = getattr(src_chat, "title", None)
            found[src_username] = src_title
            if run_id:
                record_extraction_progress(run_id, src_username, src_title)

    return found, scanned


def _classify_and_add_channels(found: dict[str, str | None]) -> tuple[list[dict], list[dict]]:
    """
    کانال‌های تازه را به جدول channels اضافه می‌کند.
    خروجی: (لیست اضافه‌شده‌ها, لیست تکراری‌ها) — هرکدام لیستی از
    {"username": ..., "title": ...}.
    """
    existing_active = {c["username"] for c in list_channels(active_only=True)}
    added: list[dict] = []
    skipped: list[dict] = []

    for uname in sorted(found.keys()):
        title = found[uname]
        if uname in existing_active:
            skipped.append({"username": uname, "title": title})
        else:
            add_channel(uname)
            added.append({"username": uname, "title": title})

    return added, skipped


async def extract_channels_from_group(
    group_link: str, days: int = DEFAULT_EXTRACTION_DAYS, run_id: str | None = None
) -> dict:
    """
    استخراج (دستی یا بازاسکن دستی) — بازه‌ی «days» روز اخیر گروه را
    می‌خواند، کانال‌های یکتا را استخراج و اضافه می‌کند، و همین گروه را
    برای اسکن خودکار روزانه در monitored_groups ثبت/به‌روز می‌کند.

    اگر run_id داده نشود، خودش یکی می‌سازد (تا همیشه یک شناسه برای
    polling وجود داشته باشد).
    """
    username = _normalize_group_link(group_link)
    if not username:
        raise ValueError("لینک یا یوزرنیم گروه نامعتبر است")

    if not run_id:
        run_id = start_extraction_run()

    client = await _connect_authorized_client()
    try:
        try:
            entity = await client.get_entity(username)
        except Exception as e:
            raise ValueError(f"دسترسی به گروه «{username}» ممکن نشد: {e}")

        await _join_if_needed(client, entity)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        found, scanned = await _scan_forwarded_channels(client, entity, cutoff, run_id=run_id)
        added, skipped = _classify_and_add_channels(found)

        now_iso = datetime.now(timezone.utc).isoformat()
        add_monitored_group(username, last_scanned_at=now_iso)
        add_extraction_log(username, run_at=now_iso, added_channels=added)

        return {
            "group": username,
            "run_id": run_id,
            "scanned_messages": scanned,
            "total_found": len(found),
            "added": added,
            "skipped_duplicates": skipped,
        }
    finally:
        await client.disconnect()


async def rescan_monitored_group_now(group_username: str, days: int = DEFAULT_EXTRACTION_DAYS, run_id: str | None = None) -> dict:
    """
    بازاسکن دستی و فوری یک گروهِ از قبل مانیتورشونده — برخلاف اسکن
    افزایشی خودکار (که فقط از آخرین اسکن به بعد را می‌خواند)، این تابع
    عمداً دوباره «days» روز کامل اخیر را بررسی می‌کند — چون کاربر آن را
    دستی و برای اطمینان کامل درخواست کرده، نه صرفاً برای پیدا کردن
    تازه‌ترین‌ها.
    """
    result = await extract_channels_from_group(group_username, days=days, run_id=run_id)
    return result


async def scan_monitored_group_incremental(group_username: str, since_iso: str) -> dict:
    """اسکن افزایشی خودکار — فقط پیام‌های بعد از since_iso را می‌خواند."""
    client = await _connect_authorized_client()
    try:
        try:
            entity = await client.get_entity(group_username)
        except Exception as e:
            raise ValueError(f"دسترسی به گروه «{group_username}» ممکن نشد: {e}")

        try:
            cutoff = datetime.fromisoformat(since_iso)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except Exception:
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)

        found, scanned = await _scan_forwarded_channels(client, entity, cutoff)
        added, skipped = _classify_and_add_channels(found)

        now_iso = datetime.now(timezone.utc).isoformat()
        update_monitored_group_scan_time(group_username, now_iso)
        add_extraction_log(group_username, run_at=now_iso, added_channels=added)

        return {
            "group": group_username,
            "scanned_messages": scanned,
            "added": added,
            "skipped_duplicates": skipped,
        }
    finally:
        await client.disconnect()


async def daily_scan_loop(check_interval_seconds: int = DAILY_SCAN_CHECK_INTERVAL_SECONDS):
    while True:
        await asyncio.sleep(check_interval_seconds)
        try:
            groups = list_monitored_groups()
            now = datetime.now(timezone.utc)
            for group in groups:
                try:
                    last_scanned = datetime.fromisoformat(group["last_scanned_at"])
                    if last_scanned.tzinfo is None:
                        last_scanned = last_scanned.replace(tzinfo=timezone.utc)
                except Exception:
                    last_scanned = now - timedelta(days=2)

                if now - last_scanned >= timedelta(hours=24):
                    try:
                        result = await scan_monitored_group_incremental(
                            group["group_username"], group["last_scanned_at"]
                        )
                        logger.info(
                            f"🔎 اسکن روزانه‌ی «{group['group_username']}»: "
                            f"{len(result['added'])} کانال جدید پیدا شد."
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ خطا در اسکن روزانه‌ی «{group['group_username']}»: {e}")
                    await asyncio.sleep(GROUP_SCAN_GAP_SECONDS)
        except Exception as e:
            logger.warning(f"⚠️ خطا در حلقه‌ی اسکن روزانه: {e}")


async def _interactive_login():
    client = _build_client()
    print("ℹ️ حالت لاگین تعاملی برای channel_extractor — شماره موبایل و کد تایید لازم است.")
    await client.start()
    print("✅ لاگین موفق بود. از این به بعد این قابلیت بدون ورودی انسانی کار می‌کند.")
    await client.disconnect()


if __name__ == "__main__":
    if "--login" in sys.argv:
        asyncio.run(_interactive_login())
    else:
        print("برای لاگین اولیه: py channel_extractor.py --login")