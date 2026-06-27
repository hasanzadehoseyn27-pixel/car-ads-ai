"""
تست ساده، بدون UI و بدون نیاز به کلید واقعی API.
provider اول را عمداً «خراب» شبیه‌سازی می‌کنیم تا ثابت شود pool خودکار
به provider دوم سوییچ می‌کند و پایپ‌لاین متوقف نمی‌شود.

برای تست با کلیدهای واقعی: فایل .env.example را به .env کپی کن، کلیدها را
بگذار، و خط FAKE را در پایین همین فایل کامنت کن تا از PROVIDERS واقعی استفاده شود.
"""
import json
import logging

from ai_pool import llm_pool, extractor
from ai_pool.config import ProviderConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")

# نمونه‌ی واقعی که خودت فرستادی
SAMPLE_MESSAGE = (
    "کوییک سفید مشکی آر اس RSپلاک تهران ۱۴۰۳ یکسال بیمه صفر "
    "خشک نیست درجهان🌵🌵🌵قیمت 🔥🔥🔥🔥09124367106"
)

# دو provider فیک: اولی همیشه قطعه (شبیه‌سازی خرابی)، دومی جواب می‌دهد
FAKE_PROVIDERS = [
    ProviderConfig(name="provider_A_simulated_down", base_url="x", api_key_env="X", model="x"),
    ProviderConfig(name="provider_B_simulated_up", base_url="x", api_key_env="X", model="x"),
]

MOCK_MODEL_OUTPUT = json.dumps({
    "is_ad": True,
    "car_name": "کوییک",
    "trim": "RS",
    "color": "سفید مشکی",
    "production_year": "1403",
    "mileage_km": 0,
    "delivery_unit": None,
    "delivery_status": "صفر کیلومتر",
    "phone": "09124367106",
    "price_amount": None,
    "price_label": None,
    "notes": "ادعای بدون خط‌وخش، یک سال بیمه — قیمت دقیق در متن ذکر نشده"
}, ensure_ascii=False)


def fake_call_provider(provider, messages):
    """جایگزین موقت _call_provider واقعی، فقط برای این تست."""
    if provider.name == "provider_A_simulated_down":
        raise TimeoutError("شبیه‌سازی قطعی/تایم‌اوت provider اول")
    return MOCK_MODEL_OUTPUT


def main():
    llm_pool._call_provider = fake_call_provider  # تزریق نسخه‌ی فیک فقط برای تست

    raw, used = llm_pool.call_with_fallback(
        [
            {"role": "system", "content": extractor.EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": SAMPLE_MESSAGE},
        ],
        providers=FAKE_PROVIDERS,
    )
    parsed = json.loads(raw)
    parsed["_provider_used"] = used

    print("\n📦 خروجی نهایی استخراج‌شده:\n")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
