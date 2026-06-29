"""
api.py — یک API ساده و داخلی (فقط روی لوکال‌هاست) که داده‌های تحلیل قیمت را
به‌صورت JSON در اختیار بک‌اند اصلی سایت (Fastify) قرار می‌دهد.

چرا یک سرویس جدا به‌جای این‌که Fastify مستقیم فایل car_ads.db را بخواند:
  - car_ads.db هم‌زمان توسط listener.py نوشته می‌شود؛ اگه یک پروسه‌ی دیگر
    (Node.js) مستقیم همین فایل را بخواند، می‌تواند باعث قفل‌شدن SQLite شود
    (همون مشکلی که قبلاً با session lock تجربه کردیم).
  - وقتی بعداً (طبق نقشه‌ی اولیه) به PostgreSQL سوییچ کنیم، قرارداد JSON
    همین می‌ماند و Fastify/فرانت‌اند هیچ تغییری نمی‌خوان — فقط داخل همین
    فایل عوض می‌شود.

نصب (یک‌بار، داخل venv):
    pip install fastapi uvicorn

اجرا:
    py -m uvicorn api:app --host 127.0.0.1 --port 8001

تست سریع (در مرورگر یا با curl):
    http://127.0.0.1:8001/analytics
    http://127.0.0.1:8001/analytics?hours=48
"""
import os
import re

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from analytics import get_price_analytics, get_ads_for_model
from db import list_channels, add_channel, remove_channel, get_setting, set_setting

app = FastAPI(title="car-ads-ai analytics API")

# همون منطق پراکسی listener.py — فقط وقتی از پشت فیلترشکن وصل می‌شیم (کامپیوتر
# خونه/شرکت) لازم است. روی سرور آلمان باید USE_PROXY ست نشه یا false باشه.
USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = os.getenv("PROXY_PORT", "10808")
PROXY_URL = f"socks5h://{PROXY_HOST}:{PROXY_PORT}" if USE_PROXY else None

AI_RATE_LIMIT_SETTING_KEY = "ai_rate_limit_seconds"
DEFAULT_AI_RATE_LIMIT_SECONDS = 10.0


class ChannelIn(BaseModel):
    username: str


class SettingsIn(BaseModel):
    # محدوده‌ی مجاز دقیقاً همون چیزی است که توی UI (۱۰ ثانیه تا ۱ دقیقه) داریم
    ai_rate_limit_seconds: float = Field(..., ge=10, le=60)


def fetch_channel_preview(username: str) -> dict:
    """
    پیش‌نمایش سریع یک کانال عمومی تلگرام، فقط با خواندن صفحه‌ی عمومی
    t.me/{username} — بدون نیاز به کلاینت Telethon (و بدون ریسک قفل‌شدن
    فایل session که قبلاً باهاش مواجه شده بودیم).
    """
    url = f"https://t.me/{username}"
    try:
        resp = requests.get(
            url,
            proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code != 200:
            return {"found": False}

        match = re.search(r'<div class="tgme_page_title">\s*<span[^>]*>([^<]+)</span>', resp.text)
        if not match:
            match = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
        if not match:
            return {"found": False}

        return {"found": True, "title": match.group(1).strip()}
    except Exception:
        return {"found": False}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analytics")
def analytics(
    hours: int = Query(24, ge=1, le=168, description="بازه‌ی زمانی به ساعت (پیش‌فرض ۲۴، حداکثر ۱۶۸ یعنی یک هفته)")
):
    data = get_price_analytics(hours=hours)
    return {
        "hours": hours,
        "models_count": len(data),
        "data": data,
    }


@app.get("/ads")
def ads(
    car_name: str = Query(..., description="نام دقیق مدل خودرو (همانی که در /analytics برگردانده می‌شود)"),
    trim: str | None = Query(None, description="تیپ مشخص (مثلاً «دنده‌ای»)؛ نبودش یعنی گروه «بدون تیپ مشخص»"),
    hours: int = Query(24, ge=1, le=168),
):
    data = get_ads_for_model(car_name=car_name, trim=trim, hours=hours)
    return {
        "car_name": car_name,
        "trim": trim,
        "hours": hours,
        "count": len(data),
        "data": data,
    }


@app.get("/channel-preview")
def channel_preview(username: str = Query(...)):
    username = username.strip().lstrip("@")
    if not username:
        return {"found": False}
    return fetch_channel_preview(username)


@app.get("/channels")
def get_channels():
    return {"data": list_channels()}


@app.post("/channels")
def create_channel(payload: ChannelIn):
    username = payload.username.strip().lstrip("@")
    if not username:
        raise HTTPException(status_code=400, detail="نام کانال خالی است")
    add_channel(username)
    return {"status": "ok", "username": username}


@app.delete("/channels/{username}")
def delete_channel(username: str):
    remove_channel(username)
    return {"status": "ok", "username": username}


@app.get("/settings")
def get_settings():
    """
    تنظیمات قابل‌کنترل از داشبورد. فعلاً فقط فاصله‌ی حداقل بین تماس‌های AI
    (llm_pool.py همین مقدار را مستقیم از دیتابیس می‌خواند، بدون نیاز به
    ری‌استارت listener.py).
    """
    raw_value = get_setting(AI_RATE_LIMIT_SETTING_KEY, default=str(DEFAULT_AI_RATE_LIMIT_SECONDS))
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_AI_RATE_LIMIT_SECONDS
    return {"ai_rate_limit_seconds": value}


@app.post("/settings")
def update_settings(payload: SettingsIn):
    set_setting(AI_RATE_LIMIT_SETTING_KEY, str(payload.ai_rate_limit_seconds))
    return {"status": "ok", "ai_rate_limit_seconds": payload.ai_rate_limit_seconds}