"""
backfill.py — ابزار دستی «ترمیم/بک‌فیل»: برای یک کانال خاص، تمام پیام‌های
امروز (از نیمه‌شب تهران تا الان) را از تلگرام می‌خواند، پیام‌هایی که هنوز
در car_ads ثبت نشده‌اند را به AI می‌فرستد، و آگهی‌های واقعی جدید را ذخیره
می‌کند.

کاملاً مستقل از listener.py و channel_sync_loop است — از یک session کاملاً
جدا (backfill_session) استفاده می‌کند.

نکته‌ی مهم درباره‌ی معماری job-based: چون عملیات ترمیم می‌تواند چند دقیقه
طول بکشد (رعایت rate limit بین هر تماس AI)، اجرای مستقیم و مسدودکننده در
یک HTTP request باعث timeout می‌شود. برای همین، عملیات در پس‌زمینه
(asyncio.create_task) اجرا می‌شود و پیشرفتش در یک دیکشنری در-حافظه
(_jobs) ثبت می‌شود؛ فرانت‌اند با یک job_id، هر چند ثانیه وضعیت را
poll می‌کند.

قبل از اولین استفاده، یک‌بار باید دستی لاگین شود:
    py backfill.py --login
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import python_socks
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest

from ai_pool.extractor import extract_car_ad
from db import (
    save_ad,
    get_existing_message_ids_for_channel,
    count_ads_for_channel_since,
)

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", "10808"))
PROXY_CONFIG = (python_socks.ProxyType.SOCKS5, PROXY_HOST, PROXY_PORT) if USE_PROXY else None

CONNECT_TIMEOUT_SECONDS = 30
JOIN_TIMEOUT_SECONDS = 20
MAX_MESSAGES_TO_SCAN = 3000

SESSION_NAME = "backfill_session"

# ---------- قفل هم‌زمانی + وضعیت job ها (در-حافظه) ----------
_backfill_running = False
_backfill_current_channel: str | None = None
_jobs: dict[str, dict] = {}  # job_id -> {status, channel, processed, total, added_count, added_ads, error, ...}


def is_backfill_running() -> dict:
    return {"running": _backfill_running, "channel": _backfill_current_channel}


def get_job_progress(job_id: str) -> dict | None:
    return _jobs.get(job_id)


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
            "«py backfill.py --login» را اجرا کن."
        )
    return client


def _midnight_tehran_utc_iso() -> str:
    now_tehran = datetime.now(TEHRAN_TZ)
    midnight_tehran = now_tehran.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_tehran.astimezone(timezone.utc).isoformat()


async def check_channel_status(channel_username: str) -> dict:
    """
    وضعیت لحظه‌ای یک کانال — بدون فرستادن چیزی به AI، فقط شمارش سریع.
    """
    since_iso = _midnight_tehran_utc_iso()
    existing_ads_count = count_ads_for_channel_since(channel_username, since_iso)

    client = await _connect_authorized_client()
    try:
        try:
            entity = await client.get_entity(channel_username)
        except Exception as e:
            raise ValueError(f"دسترسی به کانال «{channel_username}» ممکن نشد: {e}")

        cutoff = datetime.fromisoformat(since_iso)

        total_messages_today = 0
        text_messages_today = 0
        async for message in client.iter_messages(entity, limit=MAX_MESSAGES_TO_SCAN):
            if message.date and message.date < cutoff:
                break
            total_messages_today += 1
            if message.message and message.message.strip():
                text_messages_today += 1

        return {
            "channel": channel_username,
            "existing_ads_count": existing_ads_count,
            "total_messages_today": total_messages_today,
            "text_messages_today": text_messages_today,
        }
    finally:
        await client.disconnect()


def start_backfill_job(channel_username: str) -> str:
    """
    یک job جدید می‌سازد و اجرای واقعی را در پس‌زمینه شروع می‌کند.
    فوراً یک job_id برمی‌گرداند — بدون منتظرماندن برای اتمام کار.
    خروجی: job_id، یا در صورت اشغال‌بودن قفل، RuntimeError.
    """
    global _backfill_running, _backfill_current_channel

    if _backfill_running:
        raise RuntimeError(
            f"یک عملیات ترمیم دیگر (برای کانال «{_backfill_current_channel}») هم‌اکنون در حال اجراست — "
            "لطفاً صبر کن تا تمام شود."
        )

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {
        "status": "starting",  # starting | scanning | processing | done | error
        "channel": channel_username,
        "processed": 0,
        "total": 0,
        "added_count": 0,
        "added_ads": [],
        "total_ads_now": None,
        "total_messages_today": None,
        "error": None,
    }

    _backfill_running = True
    _backfill_current_channel = channel_username

    asyncio.create_task(_run_backfill_job(job_id, channel_username))
    return job_id


async def _run_backfill_job(job_id: str, channel_username: str) -> None:
    """اجرای واقعی — در پس‌زمینه، بدون بلاک‌کردن هیچ HTTP request ای."""
    global _backfill_running, _backfill_current_channel
    job = _jobs[job_id]

    try:
        since_iso = _midnight_tehran_utc_iso()
        cutoff = datetime.fromisoformat(since_iso)
        existing_ids = get_existing_message_ids_for_channel(channel_username, since_iso)

        job["status"] = "scanning"

        client = await _connect_authorized_client()
        try:
            try:
                entity = await client.get_entity(channel_username)
            except Exception as e:
                raise ValueError(f"دسترسی به کانال «{channel_username}» ممکن نشد: {e}")

            try:
                await asyncio.wait_for(client(JoinChannelRequest(entity)), timeout=JOIN_TIMEOUT_SECONDS)
            except Exception:
                pass

            candidate_messages = []
            total_messages_today = 0
            async for message in client.iter_messages(entity, limit=MAX_MESSAGES_TO_SCAN):
                if message.date and message.date < cutoff:
                    break
                total_messages_today += 1
                if message.id in existing_ids:
                    continue
                if not (message.message and message.message.strip()):
                    continue
                candidate_messages.append(message)

            candidate_messages.reverse()  # قدیمی‌ترین به جدیدترین

            job["total"] = len(candidate_messages)
            job["total_messages_today"] = total_messages_today
            job["status"] = "processing"

            added_ads = []
            for idx, message in enumerate(candidate_messages):
                text = message.message
                telegram_date = message.date.astimezone(TEHRAN_TZ).isoformat()

                try:
                    result = extract_car_ad(text)
                except Exception as e:
                    print(f"⚠️ خطا در استخراج پیام {message.id} از «{channel_username}»: {e}")
                    result = None

                if result and result.get("is_ad"):
                    save_ad(
                        channel=channel_username,
                        message_id=message.id,
                        message_text=text,
                        extracted=result,
                        telegram_date=telegram_date,
                    )
                    added_ads.append({
                        "message_id": message.id,
                        "car_name": result.get("car_name"),
                        "price_amount": result.get("price_amount"),
                        "telegram_date": telegram_date,
                        "telegram_link": f"https://t.me/{channel_username}/{message.id}",
                    })

                job["processed"] = idx + 1
                job["added_count"] = len(added_ads)
                job["added_ads"] = added_ads

            total_ads_now = count_ads_for_channel_since(channel_username, since_iso)
            job["total_ads_now"] = total_ads_now
            job["status"] = "done"
        finally:
            await client.disconnect()
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        _backfill_running = False
        _backfill_current_channel = None


async def _interactive_login():
    client = _build_client()
    print("ℹ️ حالت لاگین تعاملی برای backfill — شماره موبایل و کد تایید لازم است.")
    await client.start()
    print("✅ لاگین موفق بود. از این به بعد این قابلیت بدون ورودی انسانی کار می‌کند.")
    await client.disconnect()


if __name__ == "__main__":
    if "--login" in sys.argv:
        asyncio.run(_interactive_login())
    else:
        print("برای لاگین اولیه: py backfill.py --login")