"""
مرحله‌ی دیتابیس: نتیجه‌ی هر آگهی واقعی (is_ad=true) در «بشکه» (SQLite) ذخیره می‌شود.
طبق اصل بشکه‌ی خالی: فقط پیام‌های از این لحظه به بعد، بدون بک‌فیل تاریخچه.

هر شب راس ساعت ۰۰:۰۰ به وقت تهران، آرشیو دیروز پر و کل جدول car_ads و
message_log پاک می‌شوند.

account_status_loop: هر چند دقیقه یک‌بار، تعداد کانال/گروه‌هایی که این
اکانت الان واقعاً عضوشان است را مستقیم از تلگرام می‌خواند و در جدول
settings ذخیره می‌کند.

نکته‌ی مهم درباره‌ی retry: هر پیام (چه در مرحله‌ی استخراج توسط AI، چه در
مرحله‌ی ذخیره‌سازی در دیتابیس) اگر با خطای واقعی (Exception) مواجه شود،
تا MAX_RETRY_ATTEMPTS بار (پیش‌فرض ۵) دوباره تلاش می‌شود — با فاصله‌ی
RETRY_DELAY_SECONDS (پیش‌فرض ۳ ثانیه) بین هر تلاش. اگر بعد از همه‌ی
تلاش‌ها بازهم شکست خورد، پیام در جدول failed_messages ثبت می‌شود تا از
داشبورد (صفحه‌ی failed-messages.html) قابل بررسی و «تلاش دوباره»ی دستی
باشد. این با تصمیم درست AI (is_ad=false، یعنی پیام واقعاً آگهی نبوده)
کاملاً فرق دارد — آن حالت هرگز retry یا ثبت در failed_messages نمی‌شود،
چون خطای فنی نیست.
"""
import os
import sys
import json
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import python_socks
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest

from ai_pool.extractor import extract_car_ad
from db import (
    init_db,
    save_ad,
    list_channels,
    clear_all_ads,
    check_and_record_alert_matches,
    archive_yesterday_ads,
    set_setting,
    log_received_message,
    clear_message_log,
    add_or_update_failed_message,
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
CHANNEL_SYNC_INTERVAL_SECONDS = 15
ACCOUNT_STATUS_INTERVAL_SECONDS = 120

MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 3

ACCOUNT_USERNAME_KEY = "telegram_account_username"
ACCOUNT_CHANNEL_COUNT_KEY = "telegram_account_channel_count"
ACCOUNT_UPDATED_AT_KEY = "telegram_account_updated_at"

RAW_EVENTS_LOG_PATH = Path(__file__).parent / "raw_events.log"

INTERACTIVE_LOGIN = "--login" in sys.argv
SYNC_EXISTING_CHANNELS_MODE = "--sync-existing-channels" in sys.argv

client = TelegramClient(
    "car_ads_session",
    API_ID,
    API_HASH,
    proxy=PROXY_CONFIG,
    connection_retries=15,
    retry_delay=3,
    timeout=30,
)

joined_channels: set[str] = set()
active_channels: set[str] = set()


def log_raw_event(channel_name: str, message_id: int, has_text: bool):
    try:
        now_iso = datetime.now(TEHRAN_TZ).isoformat()
        with open(RAW_EVENTS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{now_iso} | channel={channel_name} | message_id={message_id} | has_text={has_text}\n")
    except Exception:
        pass


def extract_with_retry(text: str, source: str) -> dict | None:
    """
    تلاش برای استخراج آگهی از متن پیام — تا MAX_RETRY_ATTEMPTS بار، با
    فاصله‌ی RETRY_DELAY_SECONDS بین هر تلاش. این تابع sync است و همیشه
    باید از طریق run_in_executor صدا زده شود (توسط live_handler)، چون
    time.sleep داخلش هست.

    خروجی: دیکشنری نتیجه‌ی extract_car_ad اگر موفق بود، یا None اگر بعد
    از همه‌ی تلاش‌ها هم خطا داد (که در این حالت، آخرین خطا هم به‌عنوان
    آیتم دوم tuple برگردانده می‌شود تا فراخوان بتواند در failed_messages
    ثبتش کند).
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            result = extract_car_ad(text)
            return result, None
        except Exception as e:
            last_error = e
            print(f"⚠️ تلاش {attempt}/{MAX_RETRY_ATTEMPTS} برای استخراج پیام از {source} شکست خورد: {e}")
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    return None, last_error


def save_ad_with_retry(channel: str, message_id: int, message_text: str, extracted: dict, telegram_date: str | None) -> Exception | None:
    """
    تلاش برای ذخیره‌ی آگهی در دیتابیس — تا MAX_RETRY_ATTEMPTS بار. این
    تابع sync است و باید از طریق run_in_executor صدا زده شود.
    خروجی: None اگر موفق بود، یا آخرین Exception اگر بعد از همه‌ی
    تلاش‌ها هم شکست خورد.
    """
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            save_ad(
                channel=channel,
                message_id=message_id,
                message_text=message_text,
                extracted=extracted,
                telegram_date=telegram_date,
            )
            return None
        except Exception as e:
            last_error = e
            print(f"⚠️ تلاش {attempt}/{MAX_RETRY_ATTEMPTS} برای ذخیره‌ی آگهی (channel={channel}, message_id={message_id}) شکست خورد: {e}")
            if attempt < MAX_RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    return last_error


def process_message(text: str, source: str):
    """
    نسخه‌ی retry-دار پردازش پیام. خروجی یک tuple است:
    (نتیجه‌ی استخراج یا None, آخرین خطا یا None)
    اگر پیام بدون متن باشد، (None, None) برمی‌گردد — یعنی نه موفقیت نه
    شکست فنی، صرفاً یک پیام غیرقابل‌پردازش (فقط عکس).
    """
    if not text or not text.strip():
        print(f"⏭️  پیام بدون متن (احتمالاً فقط عکس) از {source} — رد شد")
        return None, None

    print("\n" + "=" * 60)
    print(f"📩 پیام از {source}:\n{text}")
    print("-" * 60)

    result, error = extract_with_retry(text, source)
    if result is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result, error


@client.on(events.NewMessage())
async def live_handler(event):
    try:
        raw_channel_name = None
        if event.chat is not None:
            raw_channel_name = getattr(event.chat, "username", None) or str(event.chat_id)
        else:
            raw_channel_name = f"unknown_chat_id_{event.chat_id}"
        log_raw_event(raw_channel_name, event.message.id, bool(event.message.message))
    except Exception as e:
        print(f"⚠️ خطا در ثبت لاگ خام: {e}")

    if not event.is_channel:
        return

    if event.chat is None:
        print("⏭️  آپدیتی با چت ناشناس (event.chat=None) دریافت شد — رد شد")
        return

    channel_name = event.chat.username or str(event.chat_id)

    if channel_name not in active_channels:
        print(
            f"⏭️  پیام از «{channel_name}» رد شد — این کانال هنوز در لیست کانال‌های فعال "
            f"(active_channels) نیست. اگر همین الان این کانال را اضافه کرده‌اید، تا "
            f"{CHANNEL_SYNC_INTERVAL_SECONDS} ثانیه صبر کنید تا sync بعدی انجام شود."
        )
        return

    text = event.message.message
    telegram_date = event.message.date.astimezone(TEHRAN_TZ).isoformat()

    loop = asyncio.get_running_loop()
    result, extraction_error = await loop.run_in_executor(
        None, process_message, text, f"🔴 زنده @{channel_name}"
    )

    if extraction_error is not None:
        # بعد از MAX_RETRY_ATTEMPTS بار تلاش، استخراج بازهم شکست خورد — ثبت در failed_messages
        try:
            await loop.run_in_executor(
                None,
                add_or_update_failed_message,
                channel_name, event.message.id, text, telegram_date,
                "extraction_failed", str(extraction_error), MAX_RETRY_ATTEMPTS,
            )
            print(f"❌ پیام (channel={channel_name}, message_id={event.message.id}) بعد از {MAX_RETRY_ATTEMPTS} تلاش در استخراج شکست خورد — در failed_messages ثبت شد")
        except Exception as e:
            print(f"⚠️ حتی ثبت در failed_messages هم شکست خورد: {e}")
        return

    if result is not None:
        try:
            await loop.run_in_executor(None, log_received_message, channel_name, bool(result.get("is_ad")))
        except Exception as e:
            print(f"⚠️ خطا در ثبت شمارنده‌ی پیام: {e}")

    if result and result.get("is_ad"):
        save_error = await loop.run_in_executor(
            None, save_ad_with_retry, channel_name, event.message.id, text, result, telegram_date
        )

        if save_error is not None:
            # بعد از MAX_RETRY_ATTEMPTS بار تلاش، ذخیره‌سازی بازهم شکست خورد — ثبت در failed_messages
            try:
                await loop.run_in_executor(
                    None,
                    add_or_update_failed_message,
                    channel_name, event.message.id, text, telegram_date,
                    "save_failed", str(save_error), MAX_RETRY_ATTEMPTS,
                )
                print(f"❌ پیام (channel={channel_name}, message_id={event.message.id}) بعد از {MAX_RETRY_ATTEMPTS} تلاش در ذخیره‌سازی شکست خورد — در failed_messages ثبت شد")
            except Exception as e:
                print(f"⚠️ حتی ثبت در failed_messages هم شکست خورد: {e}")
            return

        print(f"💾 ذخیره شد توی بشکه (channel={channel_name}, message_id={event.message.id})")

        try:
            matched = check_and_record_alert_matches(
                car_name=result.get("car_name"),
                price_amount=result.get("price_amount"),
                channel=channel_name,
                message_id=event.message.id,
            )
            if matched:
                print(f"🔔 این آگهی با {matched} قانون هشدار قیمت مطابقت داشت")
        except Exception as e:
            print(f"⚠️ خطا در بررسی هشدار قیمت: {e}")
    elif result is not None:
        print(f"⏭️  پیام از «{channel_name}» پردازش شد ولی is_ad=false بود — رد شد")


async def channel_sync_loop():
    global active_channels
    while True:
        try:
            channels = list_channels(active_only=True)
            new_active_channels = {c["username"] for c in channels}

            added = new_active_channels - active_channels
            removed = active_channels - new_active_channels
            if added:
                print(f"➕ کانال‌های تازه فعال‌شده در sync این دور: {', '.join(sorted(added))}")
            if removed:
                print(f"➖ کانال‌های غیرفعال‌شده در sync این دور: {', '.join(sorted(removed))}")

            active_channels = new_active_channels

            for ch in active_channels:
                if ch in joined_channels:
                    continue
                try:
                    await asyncio.wait_for(client(JoinChannelRequest(ch)), timeout=JOIN_TIMEOUT_SECONDS)
                    joined_channels.add(ch)
                    print(f"✅ به کانال «{ch}» پیوست شد — از این لحظه پیام‌های جدیدش ذخیره می‌شود")
                except asyncio.TimeoutError:
                    print(f"⚠️ پیوستن به «{ch}» بیش از {JOIN_TIMEOUT_SECONDS} ثانیه طول کشید — دوباره تلاش می‌شود")
                except Exception as e:
                    if "AlreadyParticipant" in type(e).__name__ or "already" in str(e).lower():
                        joined_channels.add(ch)
                        print(f"ℹ️ اکانت از قبل عضو «{ch}» بوده — بدون نیاز به join مجدد ادامه می‌دهیم")
                    else:
                        print(f"⚠️ خطا در پیوستن به «{ch}»: {e}")
        except Exception as e:
            print(f"⚠️ خطا در sync کانال‌ها: {e}")

        await asyncio.sleep(CHANNEL_SYNC_INTERVAL_SECONDS)


async def account_status_loop():
    while True:
        try:
            me = await client.get_me()
            username = me.username or (me.first_name or "بدون‌نام")

            channel_count = 0
            async for dialog in client.iter_dialogs():
                if dialog.is_channel or dialog.is_group:
                    channel_count += 1

            now_iso = datetime.now(TEHRAN_TZ).isoformat()
            set_setting(ACCOUNT_USERNAME_KEY, username)
            set_setting(ACCOUNT_CHANNEL_COUNT_KEY, str(channel_count))
            set_setting(ACCOUNT_UPDATED_AT_KEY, now_iso)
            print(f"👤 وضعیت اکانت بروزرسانی شد: @{username} — عضو {channel_count} کانال/گروه")
        except Exception as e:
            print(f"⚠️ خطا در بروزرسانی وضعیت اکانت: {e}")

        await asyncio.sleep(ACCOUNT_STATUS_INTERVAL_SECONDS)


def _seconds_until_next_midnight_tehran() -> float:
    now = datetime.now(TEHRAN_TZ)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_midnight - now).total_seconds()


async def midnight_cleanup_loop():
    while True:
        wait_seconds = _seconds_until_next_midnight_tehran()
        print(f"🕛 پاکسازی بعدی دیتابیس تا {wait_seconds / 3600:.1f} ساعت دیگر (نیمه‌شب به وقت تهران)")
        await asyncio.sleep(wait_seconds)
        try:
            archive_yesterday_ads()
            print("🗄️ آگهی‌های امروز به آرشیو «دیروز» منتقل شدند.")
        except Exception as e:
            print(f"⚠️ خطا در آرشیو کردن قبل از پاکسازی: {e}")
        try:
            clear_all_ads()
            print("🧹 نیمه‌شب شد — کل جدول آگهی‌ها پاک شد. امروز از صفر شروع می‌شود.")
        except Exception as e:
            print(f"⚠️ خطا در پاکسازی نیمه‌شب: {e}")
        try:
            clear_message_log()
            print("🧹 شمارنده‌ی پیام‌های امروز هم پاک شد.")
        except Exception as e:
            print(f"⚠️ خطا در پاکسازی شمارنده‌ی پیام: {e}")
        try:
            if RAW_EVENTS_LOG_PATH.exists():
                RAW_EVENTS_LOG_PATH.unlink()
            print("🧹 فایل لاگ خام (raw_events.log) هم پاک شد.")
        except Exception as e:
            print(f"⚠️ خطا در پاکسازی فایل لاگ خام: {e}")
        await asyncio.sleep(2)


async def sync_existing_channels():
    from db import add_channel, list_channels as _list_channels

    existing_usernames = {c["username"].lower() for c in _list_channels()}
    found_new: list[str] = []
    total_dialogs = 0

    async for dialog in client.iter_dialogs():
        if not (dialog.is_channel or dialog.is_group):
            continue
        total_dialogs += 1
        username = getattr(dialog.entity, "username", None)
        if not username:
            continue
        if username.lower() not in existing_usernames:
            add_channel(username)
            found_new.append(username)
            existing_usernames.add(username.lower())

    print(f"\n📊 بررسی کامل شد — {total_dialogs} کانال/گروه بررسی شد.")
    print(f"🆕 {len(found_new)} کانال جدید به لیست اضافه شد:")
    for uname in found_new:
        print(f"   ✅ @{uname}")
    if not found_new:
        print("   (هیچ کانال جدیدی پیدا نشد — همه از قبل در دیتابیس بودند)")


async def main():
    init_db()
    if USE_PROXY:
        print(f"🌐 اتصال از طریق پراکسی SOCKS5 ({PROXY_HOST}:{PROXY_PORT})")
    else:
        print("🌐 اتصال مستقیم (بدون پراکسی)")
    print("🔌 در حال اتصال به تلگرام ...")

    if INTERACTIVE_LOGIN:
        print("ℹ️ حالت لاگین تعاملی (--login) — بدون محدودیت زمانی.")
        await client.start()
    else:
        try:
            await asyncio.wait_for(client.start(), timeout=CONNECT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            print(f"❌ اتصال بیش از {CONNECT_TIMEOUT_SECONDS} ثانیه طول کشید — تونل پراکسی احتمالاً گیر کرده.")
            sys.exit(1)

    print("✅ وصل شد.")

    if SYNC_EXISTING_CHANNELS_MODE:
        await sync_existing_channels()
        return

    asyncio.create_task(channel_sync_loop())
    asyncio.create_task(midnight_cleanup_loop())
    asyncio.create_task(account_status_loop())

    print("\n👂 در حال گوش‌دادن به کانال‌های فعال (لیست داینامیک از دیتابیس)")
    print("(هیچ پیام قدیمی خوانده نمی‌شود — طبق اصل بشکه‌ی خالی، Ctrl+C برای توقف)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())