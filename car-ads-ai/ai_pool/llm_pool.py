"""
موتور سوییچ خودکار بین providerها.
هر provider چندبار (retry) امتحان می‌شود قبل از رفتن به provider بعدی —
چون شکست‌های موقت (تایم‌اوت لحظه‌ای، ۵xx گذرا) با یک تلاش دوم معمولاً حل می‌شوند.

چون هر پیام تلگرام توی یک ترد جدا (run_in_executor) پردازش می‌شود، اگه چندتا
پیام خیلی نزدیک به‌هم برسند، چندتا ترد ممکن است هم‌زمان بخواهند به همون
provider درخواست بزنند و از سهمیه‌ی نرخش (rate limit) رد بشوند — دقیقاً
همون خطای 429. برای همین، قبل از هر تماس، یک محدودکننده‌ی نرخ سراسری
(thread-safe) حداقل یک فاصله‌ی زمانی مشخص بین تماس‌های پشت‌سرهم را تضمین
می‌کند، حتی اگه چندتا ترد هم‌زمان منتظر باشند.

این فاصله از جدول settings (دیتابیس) خوانده می‌شود — یعنی از داشبورد (آیکون
تنظیمات) قابل تغییر است، بدون نیاز به ری‌استارت listener.py. اگه هنوز هیچ
مقداری ثبت نشده باشد، پیش‌فرض ۱۰ ثانیه است.
"""
import os
import threading
import time
import logging
import requests
from .config import PROVIDERS, ProviderConfig
from db import get_setting

logger = logging.getLogger("llm_pool")

AI_RATE_LIMIT_SETTING_KEY = "ai_rate_limit_seconds"
DEFAULT_MIN_SECONDS_BETWEEN_CALLS = 10.0

_rate_limit_lock = threading.Lock()
_last_call_time = 0.0


def _get_min_seconds_between_calls() -> float:
    raw_value = get_setting(AI_RATE_LIMIT_SETTING_KEY, default=str(DEFAULT_MIN_SECONDS_BETWEEN_CALLS))
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_SECONDS_BETWEEN_CALLS


def _wait_for_rate_limit() -> None:
    """قبل از هر تماس صدا زده می‌شود؛ اگه لازم باشه، همین‌جا (داخل ترد خودش) می‌خوابد."""
    global _last_call_time
    min_seconds = _get_min_seconds_between_calls()
    with _rate_limit_lock:
        now = time.time()
        elapsed = now - _last_call_time
        wait_time = min_seconds - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        _last_call_time = time.time()


class AllProvidersFailedError(Exception):
    """وقتی هیچ‌کدام از providerهای در لیست جواب ندادند."""


def _get_key(provider: ProviderConfig) -> str:
    api_key = os.getenv(provider.api_key_env)
    if not api_key:
        raise RuntimeError(f"environment variable «{provider.api_key_env}» ست نشده")
    return api_key


def _call_openai_chat(provider: ProviderConfig, messages: list[dict]) -> tuple[str, str | None]:
    """خروجی: (متن پاسخ، اسم واقعی مدلی که جواب داده — طبق فیلد model در پاسخ)."""
    api_key = _get_key(provider)
    response = requests.post(
        f"{provider.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": provider.model,
            "messages": messages,
            "temperature": 0,
        },
        timeout=provider.timeout,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    model_used = data.get("model")
    return content, model_used


def _call_anthropic_messages(provider: ProviderConfig, messages: list[dict]) -> tuple[str, str | None]:
    """خروجی: (متن پاسخ، اسم واقعی مدلی که جواب داده)."""
    api_key = _get_key(provider)

    system_prompt = None
    chat_messages = []
    for m in messages:
        if m["role"] == "system":
            system_prompt = m["content"]
        else:
            chat_messages.append(m)

    payload = {
        "model": provider.model,
        "max_tokens": 3000,
        "messages": chat_messages,
    }
    if system_prompt:
        payload["system"] = system_prompt

    response = requests.post(
        f"{provider.base_url}/messages",
        headers={
            "x-api-key": api_key,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=provider.timeout,
    )
    response.raise_for_status()
    data = response.json()
    model_used = data.get("model")

    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"], model_used

    raise RuntimeError(f"هیچ بلاک متنی در پاسخ پیدا نشد: {data}")


def _call_provider(provider: ProviderConfig, messages: list[dict]) -> tuple[str, str | None]:
    if provider.protocol == "anthropic_messages":
        return _call_anthropic_messages(provider, messages)
    return _call_openai_chat(provider, messages)


def call_with_fallback(
    messages: list[dict],
    providers: list[ProviderConfig] | None = None,
    retries_per_provider: int = 2,
):
    """
    روی providerها به ترتیب اولویت تلاش می‌کند؛ هر provider تا retries_per_provider
    بار امتحان می‌شود (برای جذب شکست‌های موقت) قبل از رفتن به provider بعدی.
    خروجی: tuple (متن پاسخ خام، اسم provider موفق، اسم واقعی مدل طبق پاسخ API —
    این آخری می‌تواند None باشد اگر provider مقدارش را برنگرداند)
    """
    providers = providers or PROVIDERS
    last_error: Exception | None = None

    for provider in providers:
        for attempt in range(1, retries_per_provider + 1):
            try:
                _wait_for_rate_limit()
                logger.info(f"🔄 تلاش {attempt}/{retries_per_provider} با provider: {provider.name}")
                content, model_used = _call_provider(provider, messages)
                logger.info(f"✅ provider «{provider.name}» (مدل: {model_used}) با موفقیت جواب داد")
                return content, provider.name, model_used
            except Exception as exc:
                logger.warning(f"⛔ provider «{provider.name}» تلاش {attempt} شکست خورد ({exc})")
                last_error = exc
                if attempt < retries_per_provider:
                    time.sleep(2)
        logger.warning(f"⛔ provider «{provider.name}» بعد از {retries_per_provider} تلاش رد شد — سوییچ به بعدی...")

    raise AllProvidersFailedError(f"همه‌ی providerها شکست خوردند. آخرین خطا: {last_error}")