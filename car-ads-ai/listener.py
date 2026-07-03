"""
مرحله‌ی دیتابیس: نتیجه‌ی هر آگهی واقعی (is_ad=true) در «بشکه» (SQLite) ذخیره می‌شود.
طبق اصل بشکه‌ی خالی: فقط پیام‌های از این لحظه به بعد، بدون بک‌فیل تاریخچه.

لیست کانال‌ها دیگر ثابت توی کد نیست — از جدول channels (دیتابیس) خوانده می‌شود
تا بشود از فرانت‌اند کانال اضافه/حذف کرد. هر کانال جدیدی که فعال می‌شود،
خودش به‌صورت خودکار join می‌شود (JoinChannelRequest) — همین join، اصل بشکه‌ی
خالی را طبیعتاً برآورده می‌کند: پیام‌های جدید فقط از لحظه‌ی join به بعد می‌رسند.

هر شب راس ساعت ۰۰:۰۰ به وقت تهران:
  ۱) ابتدا محتوای فعلی car_ads (که تا این لحظه «امروز» بوده) در جدول
     archived_ads آرشیو می‌شود (فقط همین یک روز، بدون انباشت).
  ۲) سپس کل جدول car_ads پاک می‌شود تا روز جدید از صفر شروع شود.
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
from db import init_db, save_ad, list_channels, clear_all_ads, check_and_record_alert_matches, archive_yesterday_ads

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

TEHRAN_TZ = ZoneInfo("Asia/Tehran")

# پراکسی فقط وقتی لازمه که از ایران/پشت یه فیلترشکن وصل می‌شیم (مثلاً کامپیوتر
# خونه). روی سرور آلمان (دسترسی مستقیم) باید USE_PROXY ست نشه یا false باشه.
USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", "10808"))
PROXY_CONFIG = (python_socks.ProxyType.SOCKS5, PROXY_HOST, PROXY_PORT) if USE_PROXY else None

# اگه اتصال بیشتر از این طول بکشد، یعنی تونل پراکسی گیر کرده —
# به‌جای آویزون‌ماندن بی‌نهایت، با کد خطا خارج می‌شویم تا watchdog از صفر اجراش کند.
CONNECT_TIMEOUT_SECONDS = 30
JOIN_TIMEOUT_SECONDS = 20
CHANNEL_SYNC_INTERVAL_SECONDS = 15
# اجرای دستی با --login یعنی لاگین تعاملی (شماره/کد/رمز دومرحله‌ای) در پیش
# است؛ Telethon همون لحظه‌ی ساخت TelegramClient فایل session رو خالی می‌سازه
# (حتی قبل از authorize شدن)، پس نمی‌شه با چک‌کردن وجود فایل تشخیص داد —
# باید صریح با همین پرچم مشخص کنیم.
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

# این دو ست در حافظه نگه‌داری می‌شوند و توسط channel_sync_loop بروز می‌شوند:
joined_channels: set[str] = set()   # کانال‌هایی که این پروسه از اول اجرا join‌شان کرده
active_channels: set[str] = set()   # کانال‌هایی که الان باید پردازش شوند (از دیتابیس)


def process_message(text: str, source: str):
    """
    توجه: این تابع synchronous است (extract_car_ad از requests/HTTP blocking
    استفاده می‌کند). عمداً به همین شکل نگه داشته شده — جایی که صدا زده می‌شود
    (live_handler) از run_in_executor استفاده می‌کند تا این بلاک‌شدن هیچ‌وقت
    کل event loop را قفل نکند.
    """
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
    # فقط کانال‌ها برامون مهمن، نه چت خصوصی یا گروه
    if not event.is_channel:
        return

    # گاهی Telethon می‌تواند آپدیت یک کانال را با is_channel=True بدهد ولی
    # خودِ entity چت (event.chat) را نتواند resolve کند — در این حالت
    # event.chat می‌شود None و قبلاً همین‌جا با AttributeError کرش می‌کردیم.
    # چنین پیامی برای ما قابل‌شناسایی نیست (نمی‌دانیم از کدام کانال آمده)،
    # پس بی‌خطر رد می‌شود.
    if event.chat is None:
        print("⏭️  آپدیتی با چت ناشناس (event.chat=None) دریافت شد — رد شد")
        return

    channel_name = event.chat.username or str(event.chat_id)
    if channel_name not in active_channels:
        return  # کانالی که هنوز فعال نشده یا غیرفعال شده — رد می‌شود

    text = event.message.message

    # زمان واقعی پست‌شدن پیام در تلگرام (event.message.date همیشه UTC-aware
    # است) — به وقت تهران تبدیل می‌شود تا در دیتابیس/فرانت‌اند یکدست باشد.
    telegram_date = event.message.date.astimezone(TEHRAN_TZ).isoformat()

    # extract_car_ad (داخل process_message) یک تماس HTTP synchronous است که
    # موقع تایم‌اوت providerها تا ۴۰+ ثانیه طول می‌کشد. با run_in_executor
    # این تماس را به یک ترد جدا می‌سپاریم تا event loop همیشه آزاد بماند.
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

        # بررسی مطابقت با قانون‌های هشدار قیمت — سبک و synchronous است (فقط
        # یک کوئری کوچک SQLite)، پس نیازی به run_in_executor ندارد.
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


async def channel_sync_loop():
    """
    هر چند ثانیه لیست کانال‌های فعال را از دیتابیس می‌خواند:
      - کانال‌های جدید را join می‌کند (تا آپدیت‌های لحظه‌ای‌شان شروع شود)
      - active_channels را بروز می‌کند تا live_handler بداند کدام کانال‌ها
        را پردازش کند.
    حذف یک کانال (active=0 توی دیتابیس) فقط از پردازش حذفش می‌کند؛ از خود
    کانال در تلگرام leave نمی‌کنیم — اگه بعداً دوباره فعال شد، نیازی به
    join مجدد نیست.
    """
    global active_channels
    while True:
        try:
            channels = list_channels(active_only=True)
            active_channels = {c["username"] for c in channels}

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
                    print(f"⚠️ خطا در پیوستن به «{ch}»: {e}")
        except Exception as e:
            print(f"⚠️ خطا در sync کانال‌ها: {e}")

        await asyncio.sleep(CHANNEL_SYNC_INTERVAL_SECONDS)


def _seconds_until_next_midnight_tehran() -> float:
    """چند ثانیه تا نیمه‌شب بعدی به وقت تهران مانده — برای زمان‌بندی دقیق پاکسازی."""
    now = datetime.now(TEHRAN_TZ)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_midnight - now).total_seconds()


async def midnight_cleanup_loop():
    """
    هر شب دقیقاً ساعت ۰۰:۰۰ به وقت تهران:
      ۱) ابتدا archive_yesterday_ads() صدا زده می‌شود — محتوای فعلی car_ads
         (که تا همین لحظه «امروز» بوده) به‌عنوان آرشیو «دیروز» کپی می‌شود.
      ۲) سپس clear_all_ads() کل جدول car_ads را پاک می‌کند تا روز جدید از
         صفر شروع شود.
    جدول channels و settings دست‌نخورده می‌مانند. اگه این پروسه بین راه
    ری‌استارت شود (مثلاً توسط watchdog)، دوباره فاصله تا نیمه‌شب بعدی
    محاسبه می‌شود — هیچ پاکسازی‌ای دوبار یا جا نمی‌افتد به‌جز در حالت خیلی
    نادر خاموش‌بودن دقیقاً وسط نیمه‌شب.
    """
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
        # کمی مکث برای اطمینان از عبور کامل از لحظه‌ی نیمه‌شب قبل از محاسبه‌ی دوباره
        await asyncio.sleep(2)


async def main():
    init_db()
    if USE_PROXY:
        print(f"🌐 اتصال از طریق پراکسی SOCKS5 ({PROXY_HOST}:{PROXY_PORT})")
    else:
        print("🌐 اتصال مستقیم (بدون پراکسی)")
    print("🔌 در حال اتصال به تلگرام ...")

    if INTERACTIVE_LOGIN:
        # لاگین تعاملی — شماره موبایل، کد تایید، و (اگه فعال داری) رمز
        # دومرحله‌ای می‌خواهد. محدودیت زمانی نمی‌گذاریم تا وقت کافی برای
        # تایپ داشته باشی.
        print("ℹ️ حالت لاگین تعاملی (--login) — بدون محدودیت زمانی.")
        await client.start()
    else:
        # اتصال خودکار (از طریق watchdog) با session از قبل authorize‌شده —
        # نباید نیاز به ورودی انسانی داشته باشد. اگه طول کشید، یعنی تونل
        # پراکسی گیر کرده — خارج می‌شویم تا watchdog دوباره اجرا کند.
        try:
            await asyncio.wait_for(client.start(), timeout=CONNECT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            print(f"❌ اتصال بیش از {CONNECT_TIMEOUT_SECONDS} ثانیه طول کشید — تونل پراکسی احتمالاً گیر کرده.")
            sys.exit(1)

    print("✅ وصل شد.")

    asyncio.create_task(channel_sync_loop())
    asyncio.create_task(midnight_cleanup_loop())

    print("\n👂 در حال گوش‌دادن به کانال‌های فعال (لیست داینامیک از دیتابیس)")
    print("(هیچ پیام قدیمی خوانده نمی‌شود — طبق اصل بشکه‌ی خالی، Ctrl+C برای توقف)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())