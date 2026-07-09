// ---------- توابع کمکی مشترک (فرمت‌کردن، سایدبار) ----------

function openSidebarDrawer() {
  document.getElementById("sidebarDrawer").classList.add("open");
  document.getElementById("sidebarScrim").classList.add("open");
}
function closeSidebarDrawer() {
  document.getElementById("sidebarDrawer").classList.remove("open");
  document.getElementById("sidebarScrim").classList.remove("open");
}

function formatToman(amount) {
  if (amount === null || amount === undefined)
    return '<span class="no-price">—</span>';
  return amount.toLocaleString("fa-IR") + " تومان";
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString("fa-IR");
  } catch {
    return iso;
  }
}

function toPersianPriceWords(amount) {
  if (!amount || amount <= 0) return "";
  const billions = Math.floor(amount / 1000000000);
  const afterBillions = amount % 1000000000;
  const millions = Math.floor(afterBillions / 1000000);
  const afterMillions = afterBillions % 1000000;
  const thousands = Math.floor(afterMillions / 1000);
  const parts = [];
  if (billions > 0) parts.push(`${billions.toLocaleString("fa-IR")} میلیارد`);
  if (millions > 0) parts.push(`${millions.toLocaleString("fa-IR")} میلیون`);
  if (billions === 0 && millions === 0 && thousands > 0)
    parts.push(`${thousands.toLocaleString("fa-IR")} هزار`);
  if (parts.length === 0) return `${amount.toLocaleString("fa-IR")} تومان`;
  return parts.join(" و ") + " تومان";
}

function formatNumberInputLive(inputEl) {
  const raw = inputEl.value.replace(/[^\d]/g, "");
  if (!raw) {
    inputEl.value = "";
    return null;
  }
  const num = parseInt(raw, 10);
  inputEl.value = num.toLocaleString("en-US");
  return num;
}

function onPriceFilterInput(inputEl) {
  formatNumberInputLive(inputEl);
  const minRaw = document
    .getElementById("filterPriceMin")
    .value.replace(/[^\d]/g, "");
  const maxRaw = document
    .getElementById("filterPriceMax")
    .value.replace(/[^\d]/g, "");
  const hintEl = document.getElementById("priceFilterWordsHint");
  const parts = [];
  if (minRaw)
    parts.push("از " + toPersianPriceWords(parseInt(minRaw, 10) * 1000000));
  if (maxRaw)
    parts.push("تا " + toPersianPriceWords(parseInt(maxRaw, 10) * 1000000));
  hintEl.textContent = parts.join(" — ");
}

const PERSIAN_WEEKDAYS = [
  "یکشنبه",
  "دوشنبه",
  "سه‌شنبه",
  "چهارشنبه",
  "پنجشنبه",
  "جمعه",
  "شنبه",
];
const PERSIAN_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

function gregorianToJalali(gy, gm, gd) {
  const g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    355666 +
    365 * gy +
    Math.floor((gy2 + 3) / 4) -
    Math.floor((gy2 + 99) / 100) +
    Math.floor((gy2 + 399) / 400) +
    gd +
    g_days_in_month.slice(0, gm - 1).reduce((a, b) => a + b, 0);

  let jy = -1595 + 33 * Math.floor(days / 12053);
  days %= 12053;
  jy += 4 * Math.floor(days / 1461);
  days %= 1461;
  if (days > 365) {
    jy += Math.floor((days - 1) / 365);
    days = (days - 1) % 365;
  }

  let jm, jd;
  if (days < 186) {
    jm = 1 + Math.floor(days / 31);
    jd = 1 + (days % 31);
  } else {
    jm = 7 + Math.floor((days - 186) / 30);
    jd = 1 + ((days - 186) % 30);
  }

  return { jy, jm, jd };
}

function toPersianDigits(input) {
  const persianDigits = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];
  return String(input).replace(/[0-9]/g, (d) => persianDigits[parseInt(d, 10)]);
}

function updateLiveClock() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  document.getElementById("liveClockTime").textContent = `${hh}:${mm}:${ss}`;

  const { jy, jm, jd } = gregorianToJalali(
    now.getFullYear(),
    now.getMonth() + 1,
    now.getDate()
  );
  const weekday = PERSIAN_WEEKDAYS[now.getDay()];
  const monthName = PERSIAN_MONTHS[jm - 1];
  const dateText = `${weekday}، ${toPersianDigits(
    jd
  )} ${monthName} ${toPersianDigits(jy)}`;
  document.getElementById("liveClockDate").textContent = dateText;
}
