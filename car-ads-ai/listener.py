"""
مرحله‌ی دیتابیس: نتیجه‌ی هر آگهی واقعی (is_ad=true) در «بشکه» (SQLite) ذخیره می‌شود.
طبق اصل بشکه‌ی خالی: فقط پیام‌های از این لحظه به بعد، بدون بک‌فیل تاریخچه.

لیست کانال‌ها دیگر ثابت توی کد نیست — از جدول channels (دیتابیس) خوانده می‌شود
تا بشود از فرانت‌اند کانال اضافه/حذف کرد. هر کانال جدیدی که فعال می‌شود،
خودش به‌صورت خودکار join می‌شود (JoinChannelRequest) — همین join، اصل بشکه‌ی
خالی را طبیعتاً برآورده می‌کند: پیام‌های جدید فقط از لحظه‌ی join به بعد می‌رسند.
"""
import os
import sys
import json
import asyncio
import python_socks
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest

from ai_pool.extractor import extract_car_ad
from db import init_db, save_ad, list_channels

load_dotenv()

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")

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

    channel_name = event.chat.username or str(event.chat_id)
    if channel_name not in active_channels:
        return  # کانالی که هنوز فعال نشده یا غیرفعال شده — رد می‌شود

    text = event.message.message

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
        )
        print(f"💾 ذخیره شد توی بشکه (channel={channel_name}, message_id={event.message.id})")


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

    print("\n👂 در حال گوش‌دادن به کانال‌های فعال (لیست داینامیک از دیتابیس)")
    print("(هیچ پیام قدیمی خوانده نمی‌شود — طبق اصل بشکه‌ی خالی، Ctrl+C برای توقف)\n")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())