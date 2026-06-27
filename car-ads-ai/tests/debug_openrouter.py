"""
اسکریپت یک‌بارمصرف برای دیدن دلیل دقیق خطای OpenRouter.
بعد از حل مشکل می‌تونی پاکش کنی.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENROUTER_API_KEY")

print("کلید (۱۰ کاراکتر اول):", (api_key or "❌ خالی است")[:10])

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={
        "model": "deepseek/deepseek-chat:free",
        "messages": [{"role": "user", "content": "فقط بنویس: سلام"}],
    },
    timeout=30,
)

print("\nStatus code:", response.status_code)
print("\nRaw response body:\n")
print(response.text)