"""
مخزن providerهای هوش مصنوعی.
فعلاً فقط یک provider داریم: سرور freellmapi خودمان، که خودش پشت صحنه
بین ۱۶ provider رایگان (Groq, OpenRouter, Gemini, Cerebras, ...) سوییچ می‌کند.

آدرس freellmapi با FREELLMAPI_BASE_URL در .env قابل تغییر است — پیش‌فرض همون
نسخه‌ی روی سرور آلمان (llm.k1khodro.com) است؛ اگه خواستی موقتاً به نسخه‌ی
لوکال (مثلاً موقع تست روی همین کامپیوتر) برگردی، توی .env این رو بگذار:
    FREELLMAPI_BASE_URL=http://localhost:3001/v1
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    model: str
    protocol: str = "openai_chat"
    timeout: int = 20


FREELLMAPI_BASE_URL = os.getenv("FREELLMAPI_BASE_URL", "https://llm.k1khodro.com/v1")

PROVIDERS = [
    ProviderConfig(
        name="freellmapi",
        base_url=FREELLMAPI_BASE_URL,
        api_key_env="FREELLMAPI_API_KEY",
        model="auto",
        protocol="openai_chat",
        timeout=60,
    ),
]
