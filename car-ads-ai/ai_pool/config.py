"""
مخزن providerهای هوش مصنوعی.
دو حالت داریم که با متغیر AI_BACKEND توی .env انتخاب می‌شوند:
  - AI_BACKEND=freellmapi  -> فقط از سرور freellmapi خودت استفاده می‌کند (برای خانه)
  - AI_BACKEND=direct      -> مستقیم از OpenModel/Groq/OpenRouter استفاده می‌کند (برای شرکت،
                               جایی که نصب freellmapi به مشکل Visual Studio خورد)
اگر AI_BACKEND ست نشود، پیش‌فرض روی "direct" است.
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


AI_BACKEND = os.getenv("AI_BACKEND", "direct").strip().lower()


FREELLMAPI_PROVIDERS = [
    ProviderConfig(
        name="freellmapi",
        base_url="http://localhost:3001/v1",
        api_key_env="FREELLMAPI_API_KEY",
        model="auto",
        protocol="openai_chat",
        timeout=60,
    ),
]

DIRECT_PROVIDERS = [
    ProviderConfig(
        name="openmodel_deepseek",
        base_url="https://api.openmodel.ai/v1",
        api_key_env="OPENMODEL_API_KEY",
        model="deepseek-v4-flash",
        protocol="anthropic_messages",
    ),
    ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model="llama-3.3-70b-versatile",
        protocol="openai_chat",
    ),
    ProviderConfig(
        name="openrouter_free",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        model="openrouter/free",
        protocol="openai_chat",
    ),
]

PROVIDERS = FREELLMAPI_PROVIDERS if AI_BACKEND == "freellmapi" else DIRECT_PROVIDERS