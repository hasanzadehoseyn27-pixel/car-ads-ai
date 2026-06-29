"""
مخزن providerهای هوش مصنوعی.
فعلاً هر دو provider در واقع همون سرور freellmapi خودمان هستند، فقط با
دو مقدار متفاوت برای فیلد model:
  ۱) freellmapi_deepseek — مدل اختصاصی (custom) که توی داشبورد freellmapi
     ساختی و به دیپ‌سیک متصل کردی؛ این همیشه اول امتحان می‌شود.
  ۲) freellmapi_auto — اگه اولی (بعد از تلاش‌های مجدد) شکست خورد، به‌عنوان
     پشتیبان به routing خودکار freellmapi (auto) برمی‌گردیم.

آدرس freellmapi با FREELLMAPI_BASE_URL در .env قابل تغییر است — پیش‌فرض همون
نسخه‌ی روی سرور آلمان (llm.k1khodro.com) است؛ اگه خواستی موقتاً به نسخه‌ی
لوکال برگردی، توی .env این رو بگذار:
    FREELLMAPI_BASE_URL=http://localhost:3001/v1

اسم دقیق مدل اول هم با FREELLMAPI_PRIMARY_MODEL در .env قابل تغییر است —
اگه بعداً اسم مدل custom رو توی داشبورد freellmapi عوض کردی، فقط همینجا
(یا توی .env) عوضش کن، نیازی به تغییر کد نیست.
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
FREELLMAPI_PRIMARY_MODEL = os.getenv("FREELLMAPI_PRIMARY_MODEL", "notthinkingnotsearch")

PROVIDERS = [
    ProviderConfig(
        name="freellmapi_deepseek",
        base_url=FREELLMAPI_BASE_URL,
        api_key_env="FREELLMAPI_API_KEY",
        model=FREELLMAPI_PRIMARY_MODEL,
        protocol="openai_chat",
        timeout=60,
    ),
    ProviderConfig(
        name="freellmapi_auto",
        base_url=FREELLMAPI_BASE_URL,
        api_key_env="FREELLMAPI_API_KEY",
        model="auto",
        protocol="openai_chat",
        timeout=60,
    ),
]