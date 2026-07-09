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
    get_ads_by_channel,
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
    remove_monitored_group,
    list_extraction_logs,
    start_extraction_run,
    list_extraction_progress,
    clear_extraction_progress,
    get_message_counts_per_channel,
)
from channel_extractor import extract_channels_from_group, rescan_monitored_group_now, daily_scan_loop
from backfill import (
    check_channel_status,
    start_backfill_job,
    get_job_progress,
    is_backfill_running,
    get_all_channel_backfill_statuses,
)

app = FastAPI(title="car-ads-ai analytics API")

USE_PROXY = os.getenv("USE_PROXY", "false").strip().lower() == "true"
PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = os.getenv("PROXY_PORT", "10808")
PROXY_URL = f"socks5h://{PROXY_HOST}:{PROXY_PORT}" if USE_PROXY else None

AI_RATE_LIMIT_SETTING_KEY = "ai_rate_limit_seconds"
DEFAULT_AI_RATE_LIMIT_SECONDS = 10.0

ACCOUNT_USERNAME_KEY = "telegram_account_username"
ACCOUNT_CHANNEL_COUNT_KEY = "telegram_account_channel_count"
ACCOUNT_UPDATED_AT_KEY = "telegram_account_updated_at"


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


class BackfillChannelIn(BaseModel):
    channel: str


class GroupExtractWithRunIdIn(BaseModel):
    group_link: str
    run_id: str


class RescanGroupIn(BaseModel):
    group_username: str
    run_id: str | None = None


@app.on_event("startup")
async def start_background_tasks():
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
    search: str | None = Query(None),
):
    data = get_price_analytics(hours=hours, only_new=only_new, search=search)
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


@app.get("/ads-by-channel")
def ads_by_channel(channel: str = Query(...), hours: int = Query(168, ge=1, le=168)):
    data = get_ads_by_channel(channel=channel, hours=hours)
    return {"channel": channel, "count": len(data), "data": data}


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


@app.get("/account-status")
def account_status():
    username = get_setting(ACCOUNT_USERNAME_KEY, default=None)
    channel_count = get_setting(ACCOUNT_CHANNEL_COUNT_KEY, default=None)
    updated_at = get_setting(ACCOUNT_UPDATED_AT_KEY, default=None)
    return {
        "username": username,
        "channel_count": int(channel_count) if channel_count else None,
        "updated_at": updated_at,
    }


@app.get("/message-counts")
def message_counts():
    data = get_message_counts_per_channel()
    return {"channels_count": len(data), "data": data}


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
    try:
        result = await extract_channels_from_group(payload.group_link)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطای غیرمنتظره: {e}")


@app.post("/channels/start-extraction-run")
def start_extraction_run_endpoint():
    return {"run_id": start_extraction_run()}


@app.post("/channels/extract-from-group-with-progress")
async def extract_from_group_with_progress(payload: GroupExtractWithRunIdIn):
    try:
        result = await extract_channels_from_group(payload.group_link, run_id=payload.run_id)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطای غیرمنتظره: {e}")


@app.post("/channels/rescan-group")
async def rescan_group(payload: RescanGroupIn):
    try:
        result = await rescan_monitored_group_now(payload.group_username, run_id=payload.run_id)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطای غیرمنتظره: {e}")


@app.delete("/channels/monitored-groups/{group_username}")
def delete_monitored_group(group_username: str):
    remove_monitored_group(group_username)
    return {"status": "ok", "group_username": group_username}


@app.get("/channels/monitored-groups")
def get_monitored_groups():
    return {"data": list_monitored_groups()}


@app.get("/channels/extraction-log")
def get_extraction_log(group_username: str | None = Query(None)):
    data = list_extraction_logs(group_username=group_username)
    return {"data": data}


@app.get("/channels/extraction-progress")
def get_extraction_progress(run_id: str = Query(...)):
    data = list_extraction_progress(run_id)
    return {"data": data}


@app.post("/channels/extraction-progress/clear")
def clear_extraction_progress_endpoint(run_id: str = Query(...)):
    clear_extraction_progress(run_id)
    return {"status": "ok"}


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


@app.get("/backfill/lock-status")
def backfill_lock_status():
    return is_backfill_running()


@app.get("/backfill/channel-status")
async def backfill_channel_status(channel: str = Query(...)):
    try:
        result = await check_channel_status(channel)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطای غیرمنتظره: {e}")


@app.post("/backfill/start")
async def backfill_start(payload: BackfillChannelIn):
    try:
        job_id = start_backfill_job(payload.channel)
        return {"job_id": job_id}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/backfill/progress")
def backfill_progress(job_id: str = Query(...)):
    job = get_job_progress(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="این job پیدا نشد")
    return job


@app.get("/backfill/all-status")
def backfill_all_status():
    """آخرین وضعیت ذخیره‌شده‌ی همه‌ی کانال‌ها — برای پُرکردن صفحه بدون نیاز به بررسی دستی دوباره."""
    return {"data": get_all_channel_backfill_statuses()}