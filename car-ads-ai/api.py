"""
api.py — یک API ساده و داخلی (فقط روی لوکال‌هاست) که داده‌های تحلیل قیمت را
به‌صورت JSON در اختیار بک‌اند اصلی سایت (Fastify) قرار می‌دهد.

اجرا:
    py -m uvicorn api:app --host 127.0.0.1 --port 8001
"""
import os
import re

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from analytics import (
    get_price_analytics,
    get_ads_for_model,
    get_daily_lowest_prices,
    get_wanted_ads,
    get_no_price_ads,
    get_used_cars_report,
    get_archived_ads,
)
from db import (
    list_channels,
    add_channel,
    remove_channel,
    channel_exists_active,
    get_setting,
    set_setting,
    add_price_alert,
    list_price_alerts,
    delete_price_alert,
    list_alert_matches,
    mark_all_alert_matches_seen,
    list_monitored_groups,
    list_extraction_logs,
)
from channel_extractor import extract_channels_from_group, daily_scan_loop

app = FastAPI(title="car-ads-ai analytics API")

USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = os.getenv("PROXY_PORT", "10808")
PROXY_URL = f"socks5h://{PROXY_HOST}:{PROXY_PORT}" if USE_PROXY else None

AI_RATE_LIMIT_SETTING_KEY = "ai_rate_limit_seconds"
DEFAULT_AI_RATE_LIMIT_SECONDS = 10.0


class ChannelIn(BaseModel):
    username: str


class GroupExtractIn(BaseModel):
    group_link: str


class SettingsIn(BaseModel):
    ai_rate_limit_seconds: float = Field(..., ge=10, le=60)


class PriceAlertIn(BaseModel):
    car_name: str
    min_price: int | None = None
    max_price: int | None = None

    @model_validator(mode="after")
    def check_at_least_one_bound(self):
        if self.min_price is None and self.max_price is None:
            raise ValueError("حداقل یکی از حداقل یا حداکثر قیمت باید مشخص باشد")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("حداقل قیمت نمی‌تواند بیشتر از حداکثر قیمت باشد")
        if not self.car_name or not self.car_name.strip():
            raise ValueError("نام مدل خودرو نمی‌تواند خالی باشد")
        return self


@app.on_event("startup")
async def _start_background_tasks():
    """
    حلقه‌ی اسکن روزانه‌ی گروه‌های مانیتورشونده را همراه با بالا‌آمدن خودِ
    API استارت می‌کند — نیازی به پروسه‌ی جداگانه نیست.
    """
    import asyncio
    asyncio.create_task(daily_scan_loop())


def fetch_channel_preview(username: str) -> dict:
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
    hours: int = Query(24, ge=1, le=168),
    only_new: bool = Query(True),
):
    data = get_price_analytics(hours=hours, only_new=only_new)
    return {"hours": hours, "models_count": len(data), "data": data}


@app.get("/ads")
def ads(
    car_name: str = Query(...),
    trim: str | None = Query(None),
    hours: int = Query(24, ge=1, le=168),
    only_new: bool = Query(True),
):
    data = get_ads_for_model(car_name=car_name, trim=trim, hours=hours, only_new=only_new)
    return {"car_name": car_name, "trim": trim, "hours": hours, "count": len(data), "data": data}


@app.get("/daily-report")
def daily_report():
    data = get_daily_lowest_prices()
    return {"models_count": len(data), "data": data}


@app.get("/wanted-ads")
def wanted_ads(hours: int = Query(168, ge=1, le=168)):
    data = get_wanted_ads(hours=hours)
    return {"count": len(data), "data": data}


@app.get("/no-price-ads")
def no_price_ads(hours: int = Query(168, ge=1, le=168)):
    data = get_no_price_ads(hours=hours)
    return {"count": len(data), "data": data}


@app.get("/used-cars")
def used_cars(hours: int = Query(24, ge=1, le=168)):
    data = get_used_cars_report(hours=hours)
    return {"count": len(data), "data": data}


@app.get("/archive")
def archive():
    data = get_archived_ads()
    return {"count": len(data), "data": data}


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
    if channel_exists_active(username):
        return {"status": "duplicate", "username": username}
    add_channel(username)
    return {"status": "ok", "username": username}


@app.delete("/channels/{username}")
def delete_channel(username: str):
    remove_channel(username)
    return {"status": "ok", "username": username}


@app.post("/channels/extract-from-group")
async def extract_from_group(payload: GroupExtractIn):
    """
    استخراج اولیه‌ی کانال‌های یک گروه (۷ روز اخیر) و ثبت آن گروه برای
    اسکن خودکار روزانه‌ی بعدی.
    """
    try:
        result = await extract_channels_from_group(payload.group_link)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطای غیرمنتظره: {e}")


@app.get("/channels/monitored-groups")
def get_monitored_groups():
    """لیست گروه‌هایی که هر روز به‌صورت خودکار برای کانال جدید چک می‌شوند."""
    return {"data": list_monitored_groups()}


@app.get("/channels/extraction-log")
def get_extraction_log(group_username: str | None = Query(None)):
    """
    تاریخچه‌ی استخراج‌ها — برای نمایش «هر روز چه کانال جدیدی پیدا شد» در
    مودال افزودن گروه. اگه group_username داده نشود، تاریخچه‌ی همه‌ی
    گروه‌ها با هم برگردانده می‌شود.
    """
    data = list_extraction_logs(group_username=group_username)
    return {"data": data}


@app.get("/settings")
def get_settings():
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


@app.get("/price-alerts")
def get_price_alerts():
    return {"data": list_price_alerts()}


@app.post("/price-alerts")
def create_price_alert(payload: PriceAlertIn):
    alert_id = add_price_alert(car_name=payload.car_name, min_price=payload.min_price, max_price=payload.max_price)
    return {"status": "ok", "id": alert_id}


@app.delete("/price-alerts/{alert_id}")
def remove_price_alert(alert_id: int):
    delete_price_alert(alert_id)
    return {"status": "ok", "id": alert_id}


@app.get("/alert-matches")
def get_alert_matches(unseen_only: bool = Query(False)):
    data = list_alert_matches(unseen_only=unseen_only)
    return {"count": len(data), "data": data}


@app.post("/alert-matches/mark-seen")
def mark_alert_matches_seen():
    mark_all_alert_matches_seen()
    return {"status": "ok"}