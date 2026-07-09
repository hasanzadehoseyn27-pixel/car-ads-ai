// ---------- وضعیت زنده‌ی اکانت ----------
async function loadAccountStatus() {
  try {
    const res = await fetch("/api/car-ads-account-status");
    const json = await res.json();
    const textEl = document.getElementById("accountStatusText");
    if (json.error || !json.username) {
      textEl.textContent = "وضعیت اکانت هنوز در دسترس نیست";
      return;
    }
    textEl.innerHTML =
      `اکانت <span class="account-username">@${json.username}</span> — عضو ` +
      `<span class="account-count">${(json.channel_count || 0).toLocaleString(
        "fa-IR"
      )}</span> کانال/گروه`;
  } catch (err) {
    document.getElementById("accountStatusText").textContent =
      "خطا در دریافت وضعیت اکانت";
  }
}

function startAccountStatusRefresh() {
  if (accountStatusTimer) clearInterval(accountStatusTimer);
  loadAccountStatus();
  accountStatusTimer = setInterval(
    loadAccountStatus,
    ACCOUNT_STATUS_REFRESH_MS
  );
}

// ---------- تنظیمات ----------
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(load, REFRESH_INTERVAL_MS);
  const seconds = REFRESH_INTERVAL_MS / 1000;
  const label =
    seconds >= 60
      ? "هر ۱ دقیقه"
      : `هر ${seconds.toLocaleString("fa-IR")} ثانیه`;
  document.getElementById("liveDot").title = `بروزرسانی خودکار ${label}`;
}

function openSettingsModal() {
  document.getElementById("refreshIntervalSelect").value =
    String(REFRESH_INTERVAL_MS);
  document.getElementById("settingsModalOverlay").style.display = "flex";
  loadAiRateLimit();
}

async function loadAiRateLimit() {
  const statusEl = document.getElementById("aiRateLimitStatus");
  const selectEl = document.getElementById("aiRateLimitSelect");
  statusEl.textContent = "در حال بارگذاری...";
  try {
    const res = await fetch("/api/car-ads-settings");
    const json = await res.json();
    if (json.error) {
      statusEl.textContent = "❌ " + json.error;
      return;
    }
    const value = json.ai_rate_limit_seconds;
    const options = Array.from(selectEl.options).map((o) =>
      parseFloat(o.value)
    );
    const closest = options.reduce((a, b) =>
      Math.abs(b - value) < Math.abs(a - value) ? b : a
    );
    selectEl.value = String(closest);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.textContent = "❌ خطا: " + err.message;
  }
}

async function onAiRateLimitChange() {
  const statusEl = document.getElementById("aiRateLimitStatus");
  const value = parseFloat(document.getElementById("aiRateLimitSelect").value);
  statusEl.textContent = "در حال ذخیره...";
  try {
    const res = await fetch("/api/car-ads-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ai_rate_limit_seconds: value }),
    });
    const json = await res.json();
    if (json.error) {
      statusEl.textContent = "❌ " + json.error;
      return;
    }
    statusEl.textContent = "✅ ذخیره شد";
  } catch (err) {
    statusEl.textContent = "❌ خطا: " + err.message;
  }
}

function closeSettingsModal() {
  document.getElementById("settingsModalOverlay").style.display = "none";
}
function closeSettingsModalOnOverlay(event) {
  if (event.target.id === "settingsModalOverlay") closeSettingsModal();
}

function onRefreshIntervalChange() {
  const value = parseInt(
    document.getElementById("refreshIntervalSelect").value,
    10
  );
  REFRESH_INTERVAL_MS = value;
  localStorage.setItem(REFRESH_INTERVAL_STORAGE_KEY, String(value));
  startAutoRefresh();
}

// ---------- سیستم هشدار قیمت ----------
function onAlertPriceInput(inputEl) {
  const num = formatNumberInputLive(inputEl);
  const targetId =
    inputEl.id === "alertMinPrice"
      ? "alertMinPriceWords"
      : "alertMaxPriceWords";
  document.getElementById(targetId).textContent = num
    ? toPersianPriceWords(num)
    : "";
}

function setAlertPriceMode(mode) {
  currentAlertPriceMode = mode;

  document
    .getElementById("tabRange")
    .classList.toggle("active", mode === "range");
  document
    .getElementById("tabBelow")
    .classList.toggle("active", mode === "below");
  document
    .getElementById("tabAbove")
    .classList.toggle("active", mode === "above");

  const minWrap = document.getElementById("fieldMinWrap");
  const maxWrap = document.getElementById("fieldMaxWrap");
  const minInput = document.getElementById("alertMinPrice");
  const maxInput = document.getElementById("alertMaxPrice");

  if (mode === "range") {
    minWrap.classList.remove("hidden");
    maxWrap.classList.remove("hidden");
    minInput.placeholder = "حداقل قیمت (تومان)";
    maxInput.placeholder = "حداکثر قیمت (تومان)";
  } else if (mode === "below") {
    minWrap.classList.add("hidden");
    maxWrap.classList.remove("hidden");
    minInput.value = "";
    document.getElementById("alertMinPriceWords").textContent = "";
    maxInput.placeholder = "کمتر از چه قیمتی (تومان)";
  } else if (mode === "above") {
    minWrap.classList.remove("hidden");
    maxWrap.classList.add("hidden");
    maxInput.value = "";
    document.getElementById("alertMaxPriceWords").textContent = "";
    minInput.placeholder = "بیشتر از چه قیمتی (تومان)";
  }
}

async function checkUnseenAlerts() {
  try {
    const res = await fetch("/api/car-ads-alert-matches?unseen_only=true");
    const json = await res.json();
    if (json.error) return;

    const count = json.count || 0;
    const badge = document.getElementById("bellBadge");
    const bellBtn = document.getElementById("bellBtn");

    if (count > 0) {
      badge.textContent = count > 99 ? "۹۹+" : count.toLocaleString("fa-IR");
      badge.style.display = "flex";
      bellBtn.classList.add("has-unseen");
    } else {
      badge.style.display = "none";
      bellBtn.classList.remove("has-unseen");
    }
  } catch (err) {}
}

function startAlertChecking() {
  if (alertCheckTimer) clearInterval(alertCheckTimer);
  checkUnseenAlerts();
  alertCheckTimer = setInterval(checkUnseenAlerts, ALERT_CHECK_INTERVAL_MS);
}

function populateAlertCarNameSelect() {
  const select = document.getElementById("alertCarNameSelect");
  const uniqueCarNames = Array.from(
    new Set(allAnalyticsData.map((item) => item.car_name))
  ).sort((a, b) => a.localeCompare(b, "fa"));

  select.innerHTML = "";
  if (uniqueCarNames.length === 0) {
    const option = document.createElement("option");
    option.textContent = "هنوز مدلی در جدول نیست";
    option.disabled = true;
    select.appendChild(option);
    return;
  }

  uniqueCarNames.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });
}

async function openAlertsModal() {
  document.getElementById("alertFormError").textContent = "";
  document.getElementById("alertMinPrice").value = "";
  document.getElementById("alertMaxPrice").value = "";
  document.getElementById("alertMinPriceWords").textContent = "";
  document.getElementById("alertMaxPriceWords").textContent = "";
  setAlertPriceMode("range");
  populateAlertCarNameSelect();
  document.getElementById("alertsModalOverlay").style.display = "flex";
  await Promise.all([loadAlertRules(), loadAlertMatches()]);

  try {
    await fetch("/api/car-ads-alert-matches/mark-seen", { method: "POST" });
    checkUnseenAlerts();
  } catch (err) {}
}

async function loadAlertRules() {
  const container = document.getElementById("alertRulesList");
  container.innerHTML = '<div class="empty">در حال بارگذاری...</div>';
  try {
    const res = await fetch("/api/car-ads-price-alerts");
    const json = await res.json();
    const rules = json.data || [];

    if (rules.length === 0) {
      container.innerHTML = '<div class="empty">هنوز هیچ قانونی ثبت نشده</div>';
      return;
    }

    container.innerHTML = "";
    rules.forEach((rule) => {
      const card = document.createElement("div");
      card.className = "alert-rule-card";

      let rangeText, badgeClass, badgeLabel;
      if (rule.min_price !== null && rule.max_price !== null) {
        rangeText = `${formatToman(rule.min_price)} تا ${formatToman(
          rule.max_price
        )}`;
        badgeClass = "range";
        badgeLabel = "بین دو قیمت";
      } else if (rule.min_price !== null) {
        rangeText = `بیشتر از ${formatToman(rule.min_price)}`;
        badgeClass = "above";
        badgeLabel = "بیشتر از";
      } else {
        rangeText = `کمتر از ${formatToman(rule.max_price)}`;
        badgeClass = "below";
        badgeLabel = "کمتر از";
      }

      card.innerHTML = `
          <div class="alert-rule-info">
            <div class="rule-car-name">${rule.car_name}</div>
            <div class="rule-range"><span class="rule-range-badge ${badgeClass}">${badgeLabel}</span>${rangeText}</div>
          </div>
        `;

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "danger-outline";
      deleteBtn.textContent = "حذف";
      deleteBtn.onclick = async () => {
        await fetch(`/api/car-ads-price-alerts/${rule.id}`, {
          method: "DELETE",
        });
        await loadAlertRules();
      };

      card.appendChild(deleteBtn);
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty">❌ خطا: ${err.message}</div>`;
  }
}

async function loadAlertMatches() {
  const container = document.getElementById("alertMatchesList");
  container.innerHTML = '<div class="empty">در حال بارگذاری...</div>';
  try {
    const res = await fetch("/api/car-ads-alert-matches");
    const json = await res.json();
    const matches = json.data || [];

    if (matches.length === 0) {
      container.innerHTML =
        '<div class="empty">هنوز هیچ آگهی‌ای با قانون‌های شما مطابقت نداشته</div>';
      return;
    }

    container.innerHTML = "";
    matches.forEach((match) => {
      const card = document.createElement("div");
      card.className = "ad-card";
      card.innerHTML = `
          <div class="ad-row">
            <div>
              <div class="match-car-name">${match.car_name}</div>
              <div class="match-price">${formatToman(match.price_amount)}</div>
            </div>
            <a href="${
              match.telegram_link
            }" target="_blank" rel="noopener" class="ad-link">مشاهده در تلگرام ↗</a>
          </div>
          <div class="match-rule-info">مطابق قانون: ${
            match.alert_car_name || "—"
          }</div>
          <div class="ad-date">${formatDate(match.matched_at)}</div>
        `;
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty">❌ خطا: ${err.message}</div>`;
  }
}

async function addPriceAlert() {
  const errorEl = document.getElementById("alertFormError");
  errorEl.textContent = "";

  const carName = document.getElementById("alertCarNameSelect").value;
  const minRaw = document
    .getElementById("alertMinPrice")
    .value.replace(/[^\d]/g, "");
  const maxRaw = document
    .getElementById("alertMaxPrice")
    .value.replace(/[^\d]/g, "");

  if (!carName) {
    errorEl.textContent = "لطفاً یک مدل خودرو انتخاب کن.";
    return;
  }

  const payload = { car_name: carName };

  if (currentAlertPriceMode === "range") {
    if (!minRaw && !maxRaw) {
      errorEl.textContent = "حداقل یکی از حداقل یا حداکثر قیمت را وارد کن.";
      return;
    }
    if (minRaw) payload.min_price = parseInt(minRaw, 10);
    if (maxRaw) payload.max_price = parseInt(maxRaw, 10);
  } else if (currentAlertPriceMode === "below") {
    if (!maxRaw) {
      errorEl.textContent = "قیمتی که می‌خواهی کمتر از آن باشد را وارد کن.";
      return;
    }
    payload.max_price = parseInt(maxRaw, 10);
  } else if (currentAlertPriceMode === "above") {
    if (!minRaw) {
      errorEl.textContent = "قیمتی که می‌خواهی بیشتر از آن باشد را وارد کن.";
      return;
    }
    payload.min_price = parseInt(minRaw, 10);
  }

  try {
    const res = await fetch("/api/car-ads-price-alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const json = await res.json();
    if (json.error) {
      errorEl.textContent = "❌ " + json.error;
      return;
    }

    document.getElementById("alertMinPrice").value = "";
    document.getElementById("alertMaxPrice").value = "";
    document.getElementById("alertMinPriceWords").textContent = "";
    document.getElementById("alertMaxPriceWords").textContent = "";
    await loadAlertRules();
  } catch (err) {
    errorEl.textContent = "❌ خطا: " + err.message;
  }
}

function closeAlertsModal() {
  document.getElementById("alertsModalOverlay").style.display = "none";
}
function closeAlertsModalOnOverlay(event) {
  if (event.target.id === "alertsModalOverlay") closeAlertsModal();
}
