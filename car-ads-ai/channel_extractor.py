"""
channel_extractor.py — استخراج خودکار کانال‌های مبدا از یک گروه تلگرامی که
پست‌های فوروواردشده از کانال‌های مختلف را جمع می‌کند (مثلاً یک گروه بازار
که آگهی‌های چند کانال را در خودش می‌بیند).

چون این ماژول باید هم‌زمان با listener.py (که از session جداگانه‌ای به اسم
car_ads_session استفاده می‌کند) کار کند، عمداً از یک session کاملاً جدا و
مستقل به اسم channel_extractor_session استفاده می‌کند — تا هیچ‌وقت دو
پروسه هم‌زمان سعی نکنند یک فایل session مشترک را باز کنند.

قبل از اولین استفاده، این session باید یک‌بار به‌صورت دستی لاگین شود:
    py channel_extractor.py --login

بعد از اولین استخراج دستی یک گروه (extract_channels_from_group)، آن گروه
به‌صورت خودکار به monitored_groups اضافه می‌شود و از آن پس هر ۲۴ ساعت
(daily_scan_loop) فقط پیام‌های جدید (از آخرین اسکن به بعد) بررسی می‌شوند
تا کانال‌های تازه‌ی احتمالی پیدا و اضافه شوند — بدون نیاز به هیچ اقدام
دستی دوباره.
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
DAILY_SCAN_CHECK_INTERVAL_SECONDS = 3600  # هر ۱ ساعت چک می‌کند کدام گروه‌ها ۲۴+ ساعت از آخرین اسکنشان گذشته
GROUP_SCAN_GAP_SECONDS = 5  # فاصله‌ی کوچک بین اسکن هر گروه، برای احتیاط در برابر فلود

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
        # ممکن است دعوت خصوصی لازم باشد یا از قبل عضو باشیم؛ در هر صورت با
        # خواندن پیام‌ها ادامه می‌دهیم — join‌نبودن الزاماً مانع خواندن نیست.
        pass


async def _scan_forwarded_channels(client: TelegramClient, entity, cutoff: datetime) -> tuple[set[str], int]:
    """
    پیام‌های گروه را از جدیدترین به قدیمی‌ترین می‌خواند تا به cutoff برسد،
    و یوزرنیم کانال‌های مبدا هر پیام فوروواردشده را جمع می‌کند.
    خروجی: (مجموعه‌ی یوزرنیم‌های یکتا، تعداد پیام‌های واقعاً بررسی‌شده).
    """
    found_usernames: set[str] = set()
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
        if src_username:
            found_usernames.add(src_username)

    return found_usernames, scanned


def _classify_and_add_channels(found_usernames: set[str]) -> tuple[list[str], list[str]]:
    """کانال‌های تازه را به جدول channels اضافه می‌کند؛ برمی‌گرداند: (اضافه‌شده‌ها, تکراری‌ها)."""
    existing_active = {c["username"] for c in list_channels(active_only=True)}
    added: list[str] = []
    skipped: list[str] = []

    for uname in sorted(found_usernames):
        if uname in existing_active:
            skipped.append(uname)
        else:
            add_channel(uname)
            added.append(uname)

    return added, skipped


async def extract_channels_from_group(group_link: str, days: int = DEFAULT_EXTRACTION_DAYS) -> dict:
    """
    استخراج اولیه (دستی) — یک هفته‌ی اخیر گروه را می‌خواند، کانال‌های
    یکتا را استخراج و اضافه می‌کند، و همین گروه را برای اسکن خودکار روزانه
    در monitored_groups ثبت می‌کند.
    """
    username = _normalize_group_link(group_link)
    if not username:
        raise ValueError("لینک یا یوزرنیم گروه نامعتبر است")

    client = await _connect_authorized_client()
    try:
        try:
            entity = await client.get_entity(username)
        except Exception as e:
            raise ValueError(f"دسترسی به گروه «{username}» ممکن نشد: {e}")

        await _join_if_needed(client, entity)

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        found_usernames, scanned = await _scan_forwarded_channels(client, entity, cutoff)
        added, skipped = _classify_and_add_channels(found_usernames)

        now_iso = datetime.now(timezone.utc).isoformat()
        add_monitored_group(username, last_scanned_at=now_iso)
        add_extraction_log(username, run_at=now_iso, added_channels=added)

        return {
            "group": username,
            "scanned_messages": scanned,
            "total_found": len(found_usernames),
            "added": added,
            "skipped_duplicates": skipped,
        }
    finally:
        await client.disconnect()


async def scan_monitored_group_incremental(group_username: str, since_iso: str) -> dict:
    """
    اسکن افزایشی یک گروه از قبل مانیتورشونده — فقط پیام‌های بعد از
    since_iso را می‌خواند (نه کل تاریخچه را دوباره). برای اسکن روزانه‌ی
    خودکار استفاده می‌شود.
    """
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

        found_usernames, scanned = await _scan_forwarded_channels(client, entity, cutoff)
        added, skipped = _classify_and_add_channels(found_usernames)

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
    """
    هر ساعت چک می‌کند که آیا ۲۴ ساعت یا بیشتر از آخرین اسکن هر گروهِ
    مانیتورشونده گذشته یا نه؛ اگه گذشته باشد، همان گروه را اسکن افزایشی
    می‌کند و نتیجه (حتی اگه خالی بود) را در channel_extraction_log ثبت
    می‌کند تا داشبورد بتواند «هنوز کانال جدید پیدا نشده» را هم نشان دهد.

    طراحی به این شکل (چک ساعتی به‌جای خواب ۲۴ساعته‌ی یک‌باره) عمداً است —
    اگه پروسه بین راه ری‌استارت شود (مثلاً توسط pm2)، تایمر از صفر شروع
    نمی‌شود و هیچ گروهی بیش از حد معطل نمی‌ماند.
    """
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