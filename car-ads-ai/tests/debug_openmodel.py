"""
اسکریپت یک‌بارمصرف فقط برای دیدن ساختار خام پاسخ OpenModel.
چندبار تلاش می‌کند چون اتصال از طریق پراکسی گاهی timeout می‌کند.
بعد از حل مشکل می‌تونی این فایل رو پاک کنی.
"""
import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENMODEL_API_KEY")

for attempt in range(1, 4):
    print(f"\n--- تلاش {attempt} ---")
    try:
        response = requests.post(
            "https://api.openmodel.ai/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "deepseek-v4-flash",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": "فقط بنویس: سلام"}],
            },
            timeout=60,
        )
        print("Status code:", response.status_code)
        print("\nRaw JSON response:\n")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
        break  # موفق شد، دیگه نیازی به تلاش بعدی نیست
    except Exception as e:
        print(f"❌ شکست خورد: {e}")
        time.sleep(3)