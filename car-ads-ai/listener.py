"""
مرحله‌ی دیتابیس: نتیجه‌ی هر آگهی واقعی (is_ad=true) در «بشکه» (SQLite) ذخیره می‌شود.
طبق اصل بشکه‌ی خالی: فقط پیام‌های از این لحظه به بعد، بدون بک‌فیل تاریخچه.

هر شب راس ساعت ۰۰:۰۰ به وقت تهران، آرشیو دیروز پر و کل جدول car_ads پاک می‌شود.

account_status_loop: هر چند دقیقه یک‌بار، تعداد کانال/گروه‌هایی که این
اکانت الان واقعاً عضوشان است را مستقیم از تلگرام می‌خواند و در جدول
settings ذخیره می‌کند.

نکته‌ی مهم درباره‌ی لاگ‌گیری: هر پیامی که به هر دلیلی رد می‌شود (چه چون
کانال هنوز در active_channels نیست، چه چون بدون متن است) باید حتماً یک
خط لاگ صریح بگذارد — قبلاً بعضی رد شدن‌ها کاملاً بی‌صدا بودند (مثلاً
پیامی که channel_name اش هنوز در active_channels نبود)، که باعث می‌شد
اگر کانالی به‌تازگی اضافه شده بود ولی هنوز sync نشده بود، پیام‌هایش
بدون هیچ ردی از بین بروند و عیب‌یابی غیرممکن شود.
"""
import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
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

ACCOUNT_USERNAME_KEY = "telegram_account_username"
ACCOUNT_CHANNEL_COUNT_KEY = "telegram_account_channel_count"
ACCOUNT_UPDATED_AT_KEY = "telegram_account_updated_at"

INTERACTIVE_LOGIN = "--login" in sys.argv

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


def process_message(text: str, source: str):
    if not text or not text.strip():
        print(f"⏭️  پیام بدون متن (احتمالاً فقط عکس) از {source} — رد شد")
        return None

    print("\n" + "=" * 60)
    print(f"📩 پیام از {source}:\n{text}")
    print("-" * 60)
    try:
        result = extract_car_ad(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    except Exception as e:
        print(f"❌ خطا در استخراج: {e}")
        return None


@client.on(events.NewMessage())
async def live_handler(event):
    if not event.is_channel:
        # پیام از یک چت خصوصی یا گروه معمولی است، نه کانال — عمداً و بی‌صدا
        # رد می‌شود، چون این پروژه فقط کانال‌ها را دنبال می‌کند.
        return

    if event.chat is None:
        print("⏭️  آپدیتی با چت ناشناس (event.chat=None) دریافت شد — رد شد")
        return

    channel_name = event.chat.username or str(event.chat_id)

    if channel_name not in active_channels:
        # این لاگ عمداً صریح و همیشگی است — قبلاً این حالت کاملاً بی‌صدا رد
        # می‌شد که باعث می‌شد پیام‌های کانال‌های تازه‌اضافه‌شده (که هنوز
        # channel_sync_loop به‌روزشان نکرده) بدون هیچ ردی گم شوند.
        print(
            f"⏭️  پیام از «{channel_name}» رد شد — این کانال هنوز در لیست کانال‌های فعال "
            f"(active_channels) نیست. اگر همین الان این کانال را اضافه کرده‌اید، تا "
            f"{CHANNEL_SYNC_INTERVAL_SECONDS} ثانیه صبر کنید تا sync بعدی انجام شود."
        )
        return

    text = event.message.message
    telegram_date = event.message.date.astimezone(TEHRAN_TZ).isoformat()

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, process_message, text, f"🔴 زنده @{channel_name}"
    )

    if result and result.get("is_ad"):
        save_ad(
            channel=channel_name,
            message_id=event.message.id,
            message_text=text,
            extracted=result,
            telegram_date=telegram_date,
        )
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
        # is_ad=false بوده — یعنی AI تشخیص داده این پیام آگهی خودرو نیست.
        # عمداً لاگ می‌شود تا مشخص باشد پیام واقعاً پردازش شده، فقط رد شده.
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
        await asyncio.sleep(2)


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

    asyncio.create_task(channel_sync_loop())
    asyncio.create_task(midnight_cleanup_loop())
    asyncio.create_task(account_status_loop())

    print("\n👂 در حال گوش‌دادن به کانال‌های فعال (لیست داینامیک از دیتابیس)")
    print("(هیچ پیام قدیمی خوانده نمی‌شود — طبق اصل بشکه‌ی خالی، Ctrl+C برای توقف)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())