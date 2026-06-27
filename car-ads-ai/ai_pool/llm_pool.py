"""
موتور سوییچ خودکار بین providerها.
هر provider چندبار (retry) امتحان می‌شود قبل از رفتن به provider بعدی —
چون شکست‌های موقت (تایم‌اوت لحظه‌ای، ۵xx گذرا) با یک تلاش دوم معمولاً حل می‌شوند.
"""
import os
import time
import logging
import requests
from .config import PROVIDERS, ProviderConfig

logger = logging.getLogger("llm_pool")


class AllProvidersFailedError(Exception):
    """وقتی هیچ provider‌ای در لیست جواب نداد."""


def _get_key(provider: ProviderConfig) -> str:
    api_key = os.getenv(provider.api_key_env)
    if not api_key:
        raise RuntimeError(f"environment variable «{provider.api_key_env}» ست نشده")
    return api_key


def _call_openai_chat(provider: ProviderConfig, messages: list[dict]) -> str:
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
    return data["choices"][0]["message"]["content"]


def _call_anthropic_messages(provider: ProviderConfig, messages: list[dict]) -> str:
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

    for block in data.get("content", []):
        if block.get("type") == "text":
            return block["text"]

    raise RuntimeError(f"هیچ بلاک متنی در پاسخ پیدا نشد: {data}")


def _call_provider(provider: ProviderConfig, messages: list[dict]) -> str:
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
    خروجی: tuple (متن پاسخ خام، اسم provider موفق)
    """
    providers = providers or PROVIDERS
    last_error: Exception | None = None

    for provider in providers:
        for attempt in range(1, retries_per_provider + 1):
            try:
                logger.info(f"🔄 تلاش {attempt}/{retries_per_provider} با provider: {provider.name}")
                content = _call_provider(provider, messages)
                logger.info(f"✅ provider «{provider.name}» با موفقیت جواب داد")
                return content, provider.name
            except Exception as exc:
                logger.warning(f"⛔ provider «{provider.name}» تلاش {attempt} شکست خورد ({exc})")
                last_error = exc
                if attempt < retries_per_provider:
                    time.sleep(2)
        logger.warning(f"⛔ provider «{provider.name}» بعد از {retries_per_provider} تلاش رد شد — سوییچ به بعدی...")

    raise AllProvidersFailedError(f"همه‌ی providerها شکست خوردند. آخرین خطا: {last_error}")