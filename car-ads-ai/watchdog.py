# -*- coding: utf-8 -*-
"""
watchdog.py — اجرا و مانیتور listener.py

این فایل listener.py رو به‌جای خودت اجرا می‌کنه و خروجیش رو لحظه‌ای می‌خونه.

دو حالت رو خودش تشخیص می‌ده و ریستارت می‌کنه:
  ۱) همون خطای تکراری «Security error...wrong session ID» چند بار پشت‌سرهم.
  ۲) خروج زودهنگام listener.py به هر دلیل دیگه (مثلاً listener.py خودش
     به‌خاطر تایم‌اوت اتصال/warm-up با کد خطا خارج شده باشه).

اگه چندبار پشت‌سرهم listener.py ظرف کمتر از یک دقیقه بمیره، احتمالش بیشتره
که خودِ تونل پراکسی (v2rayN/Xray) گیر کرده باشه، نه فقط یه نوسان موقت —
در این حالت watchdog هم یه هشدار صریح می‌ده و هم فاصله‌ی بین تلاش‌ها رو
به‌تدریج بیشتر می‌کنه (backoff) تا روی یه پراکسی خراب مدام چرخ نزنه.

listener.py با همون پایتونی اجرا می‌شه که خودِ watchdog.py باهاش در حال اجراست
(sys.executable) — این یعنی اگه watchdog.py از یه venv خاص (مثلاً با
--interpreter توی PM2) اجرا شده باشه، listener.py هم دقیقاً همون venv رو
می‌گیره، نه پایتون سراسری سیستم.

اجرا:
    py watchdog.py

توقف کامل:
    Ctrl+C
"""

import io
import os
import subprocess
import sys
import time
from collections import deque
from datetime import datetime

# روی ویندوز (مخصوصاً زیر PM2) stdout/stderr خودِ watchdog معمولاً با codepage
# پیش‌فرض سیستم (مثلاً cp1252) باز می‌شود که نمی‌تواند حروف فارسی/ایموجی را
# encode کند و با UnicodeEncodeError کرش می‌کند. اینجا صریحاً به UTF-8
# سوییچ می‌کنیم تا این مشکل دیگر اتفاق نیفتد.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ----------------- تنظیمات -----------------
SCRIPT_TO_RUN = [sys.executable, "listener.py"]
ERROR_PATTERN = "Security error while unpacking a received message"
ERROR_THRESHOLD = 5            # چند بار همین خطا پشت‌سرهم دیده شه تا ریستارت کنیم
ERROR_WINDOW_SECONDS = 15      # توی چه بازه‌ی زمانی (ثانیه)

BASE_RESTART_DELAY_SECONDS = 5     # فاصله‌ی پایه بین ریستارت‌ها
MAX_RESTART_DELAY_SECONDS = 120    # سقف فاصله (تا بی‌نهایت زیاد نشه)
QUICK_FAIL_SECONDS = 60            # اگه کمتر از این مدت زنده بمونه، یعنی "خروج سریع"
QUICK_FAIL_WARNING_COUNT = 3       # بعد از چند تا خروج سریع پشت‌سرهم هشدار بدیم

LOG_FILE = "watchdog.log"
# --------------------------------------------


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # لاگ‌نوشتن نباید کل برنامه رو متوقف کنه


def run_once() -> float:
    """یک بار listener.py را اجرا و مانیتور می‌کند. مدت زمان زنده‌ماندنش (ثانیه) را برمی‌گرداند."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    log(f"🚀 اجرای: {' '.join(SCRIPT_TO_RUN)}")
    start_time = time.time()
    process = subprocess.Popen(
        SCRIPT_TO_RUN,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    error_timestamps = deque()

    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\n")
            print(line, flush=True)  # خروجی همونطور که هست نمایش داده میشه

            if ERROR_PATTERN in line:
                now = time.time()
                error_timestamps.append(now)
                while error_timestamps and now - error_timestamps[0] > ERROR_WINDOW_SECONDS:
                    error_timestamps.popleft()

                if len(error_timestamps) >= ERROR_THRESHOLD:
                    log(
                        f"⚠️ {ERROR_THRESHOLD} بار «Security error» توی "
                        f"{ERROR_WINDOW_SECONDS} ثانیه دیده شد — در حال ریستارت listener..."
                    )
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return time.time() - start_time

        # listener.py خودش (بدون این‌که ما بکشیمش) تموم شده
        process.wait()
        log(f"⛔ listener.py با کد خروج {process.returncode} متوقف شد.")
        return time.time() - start_time

    except KeyboardInterrupt:
        log("⏹️ متوقف شد توسط کاربر (Ctrl+C).")
        process.terminate()
        raise


def main() -> None:
    log("====== Watchdog شروع شد ======")
    consecutive_quick_fails = 0

    try:
        while True:
            duration = run_once()

            if duration < QUICK_FAIL_SECONDS:
                consecutive_quick_fails += 1
            else:
                consecutive_quick_fails = 0

            if consecutive_quick_fails >= QUICK_FAIL_WARNING_COUNT:
                log(
                    "⚠️⚠️ چند بار پشت‌سرهم ظرف کمتر از یک دقیقه قطع شد — "
                    "به‌احتمال زیاد خودِ تونل پراکسی/VPN (v2rayN/Xray) گیر کرده، "
                    "نه فقط یه نوسان موقت. بهتره دستی v2rayN/Xray رو کامل ببندی، "
                    "چند ثانیه صبر کنی، و دوباره بازش کنی."
                )

            delay = min(
                BASE_RESTART_DELAY_SECONDS * (2 ** max(0, consecutive_quick_fails - 1)),
                MAX_RESTART_DELAY_SECONDS,
            )
            log(f"⏳ {delay} ثانیه صبر و اجرای دوباره...")
            time.sleep(delay)

    except KeyboardInterrupt:
        pass

    log("====== Watchdog متوقف شد ======")


if __name__ == "__main__":
    main()