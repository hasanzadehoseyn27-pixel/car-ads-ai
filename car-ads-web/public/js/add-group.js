// ---------- افزودن گروه ----------
async function openAddGroupModal() {
  document.getElementById("groupLinkInput").value = "";
  document.getElementById("addGroupError").textContent = "";
  document.getElementById("addGroupForm").style.display = "flex";
  document.getElementById("addGroupLoading").style.display = "none";
  document.getElementById("liveProgressList").style.display = "none";
  document.getElementById("liveProgressList").innerHTML = "";
  document.getElementById("addGroupResult").style.display = "none";
  document.getElementById("addGroupModalOverlay").style.display = "flex";
  await loadMonitoredGroupsList();
}

function appendLiveProgressItem(item) {
  const key = item.username + "|" + item.found_at;
  if (shownProgressIds.has(key)) return;
  shownProgressIds.add(key);
  const listEl = document.getElementById("liveProgressList");
  const div = document.createElement("div");
  div.className = "live-progress-item";
  div.innerHTML = `<span class="lp-icon">🆕</span><span class="lp-username">@${
    item.username
  }</span>${item.title ? `<span class="lp-title">${item.title}</span>` : ""}`;
  listEl.appendChild(div);
  listEl.scrollTop = listEl.scrollHeight;
}

async function pollExtractionProgress() {
  if (!currentExtractionRunId) return;
  try {
    const res = await fetch(
      `/api/car-ads-extraction-progress?run_id=${encodeURIComponent(
        currentExtractionRunId
      )}`
    );
    const json = await res.json();
    (json.data || []).forEach(appendLiveProgressItem);
  } catch (err) {}
}

function startExtractionPolling() {
  if (extractionProgressTimer) clearInterval(extractionProgressTimer);
  extractionProgressTimer = setInterval(
    pollExtractionProgress,
    EXTRACTION_PROGRESS_POLL_MS
  );
}

function stopExtractionPolling() {
  if (extractionProgressTimer) {
    clearInterval(extractionProgressTimer);
    extractionProgressTimer = null;
  }
}

async function startGroupExtraction() {
  const errorEl = document.getElementById("addGroupError");
  errorEl.textContent = "";
  const link = document.getElementById("groupLinkInput").value.trim();
  if (!link) {
    errorEl.textContent = "لطفاً لینک یا یوزرنیم گروه را وارد کن.";
    return;
  }

  document.getElementById("addGroupForm").style.display = "none";
  document.getElementById("addGroupLoading").style.display = "flex";
  document.getElementById("addGroupLoadingText").textContent =
    "شروع به استخراج کانال‌های غیرتکراری...";
  document.getElementById("liveProgressList").style.display = "block";
  document.getElementById("liveProgressList").innerHTML = "";
  document.getElementById("addGroupResult").style.display = "none";
  shownProgressIds = new Set();

  try {
    const runRes = await fetch("/api/car-ads-channels/start-extraction-run", {
      method: "POST",
    });
    const runJson = await runRes.json();
    currentExtractionRunId = runJson.run_id;
    startExtractionPolling();

    const res = await fetch(
      "/api/car-ads-channels/extract-from-group-with-progress",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          group_link: link,
          run_id: currentExtractionRunId,
        }),
      }
    );
    const json = await res.json();

    stopExtractionPolling();
    await pollExtractionProgress();

    document.getElementById("addGroupLoading").style.display = "none";

    if (json.error) {
      document.getElementById("addGroupForm").style.display = "flex";
      errorEl.textContent = "❌ " + json.error;
      return;
    }

    const resultEl = document.getElementById("addGroupResult");
    resultEl.style.display = "block";
    const addedList =
      (json.added || [])
        .map((c) => `@${c.username}${c.title ? " (" + c.title + ")" : ""}`)
        .join("، ") || "—";
    const dupList =
      (json.skipped_duplicates || []).map((c) => `@${c.username}`).join("، ") ||
      "—";
    resultEl.innerHTML = `
        <div>✅ استخراج تمام شد. این گروه از این پس هر روز به‌صورت خودکار برای کانال‌های جدید چک می‌شود.</div>
        <div>📩 تعداد پیام بررسی‌شده: ${json.scanned_messages.toLocaleString(
          "fa-IR"
        )}</div>
        <div>📡 تعداد کانال یکتای پیدا‌شده: ${json.total_found.toLocaleString(
          "fa-IR"
        )}</div>
        <div>🆕 کانال‌های تازه‌اضافه‌شده (${json.added.length.toLocaleString(
          "fa-IR"
        )}): ${addedList}</div>
        <div>⚠️ کانال‌های تکراری که اضافه نشدند (${json.skipped_duplicates.length.toLocaleString(
          "fa-IR"
        )}): ${dupList}</div>
      `;

    try {
      await fetch(
        `/api/car-ads-extraction-progress/clear?run_id=${encodeURIComponent(
          currentExtractionRunId
        )}`,
        { method: "POST" }
      );
    } catch (e) {}
    currentExtractionRunId = null;

    await loadMonitoredGroupsList();
  } catch (err) {
    stopExtractionPolling();
    document.getElementById("addGroupLoading").style.display = "none";
    document.getElementById("addGroupForm").style.display = "flex";
    errorEl.textContent = "❌ خطا: " + err.message;
  }
}

async function loadMonitoredGroupsList() {
  const container = document.getElementById("monitoredGroupsList");
  container.innerHTML = '<div class="empty">در حال بارگذاری...</div>';
  try {
    const res = await fetch("/api/car-ads-monitored-groups");
    const json = await res.json();
    const groups = json.data || [];
    if (groups.length === 0) {
      container.innerHTML =
        '<div class="empty">هنوز هیچ گروهی اضافه نشده</div>';
      return;
    }
    container.innerHTML = "";
    groups.forEach((g) => {
      const card = document.createElement("div");
      card.className = "monitored-group-card";
      card.innerHTML = `
          <div class="monitored-group-info">
            <div class="mg-username">@${g.group_username}</div>
            <div class="mg-last-scan">آخرین بررسی: ${formatDate(
              g.last_scanned_at
            )}</div>
          </div>
        `;
      const actions = document.createElement("div");
      actions.className = "monitored-group-actions";

      const rescanBtn = document.createElement("button");
      rescanBtn.className = "secondary tiny";
      rescanBtn.textContent = "🔄 بررسی دوباره";
      rescanBtn.onclick = () => rescanGroupNow(g.group_username, rescanBtn);

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "danger-outline tiny";
      deleteBtn.textContent = "حذف گروه";
      deleteBtn.onclick = async () => {
        if (!confirm(`گروه @${g.group_username} از فهرست مانیتورینگ حذف شود؟`))
          return;
        await fetch(
          `/api/car-ads-monitored-groups/${encodeURIComponent(
            g.group_username
          )}`,
          { method: "DELETE" }
        );
        await loadMonitoredGroupsList();
      };

      actions.appendChild(rescanBtn);
      actions.appendChild(deleteBtn);
      card.appendChild(actions);
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty">❌ خطا: ${err.message}</div>`;
  }
}

async function rescanGroupNow(groupUsername, btnEl) {
  const originalText = btnEl.textContent;
  btnEl.disabled = true;
  btnEl.textContent = "در حال بررسی...";
  try {
    const runRes = await fetch("/api/car-ads-channels/start-extraction-run", {
      method: "POST",
    });
    const runJson = await runRes.json();
    const runId = runJson.run_id;

    const res = await fetch("/api/car-ads-channels/rescan-group", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_username: groupUsername, run_id: runId }),
    });
    const json = await res.json();

    try {
      await fetch(
        `/api/car-ads-extraction-progress/clear?run_id=${encodeURIComponent(
          runId
        )}`,
        { method: "POST" }
      );
    } catch (e) {}

    if (json.error) {
      alert("خطا در بررسی دوباره: " + json.error);
    } else {
      const addedCount = (json.added || []).length;
      alert(
        addedCount > 0
          ? `✅ ${addedCount} کانال جدید پیدا و اضافه شد.`
          : "هنوز کانال جدیدی پیدا نشده است."
      );
    }
    await loadMonitoredGroupsList();
  } catch (err) {
    alert("خطا: " + err.message);
  } finally {
    btnEl.disabled = false;
    btnEl.textContent = originalText;
  }
}

function closeAddGroupModal() {
  document.getElementById("addGroupModalOverlay").style.display = "none";
}
function closeAddGroupModalOnOverlay(event) {
  if (event.target.id === "addGroupModalOverlay") closeAddGroupModal();
}

// ---------- مودال مجزا: گزارش استخراج روزانه ----------
async function openDailyReportModal() {
  document.getElementById("dailyReportModalOverlay").style.display = "flex";
  const select = document.getElementById("dailyReportGroupSelect");
  select.innerHTML = '<option value="">در حال بارگذاری...</option>';
  try {
    const res = await fetch("/api/car-ads-monitored-groups");
    const json = await res.json();
    const groups = json.data || [];
    select.innerHTML = "";
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "همه‌ی گروه‌ها";
    select.appendChild(allOption);
    groups.forEach((g) => {
      const option = document.createElement("option");
      option.value = g.group_username;
      option.textContent = "@" + g.group_username;
      select.appendChild(option);
    });
  } catch (err) {
    select.innerHTML = '<option value="">خطا در بارگذاری</option>';
  }
  await loadDailyReport();
}

async function loadDailyReport() {
  const container = document.getElementById("dailyReportList");
  container.innerHTML = '<div class="empty">در حال بارگذاری...</div>';
  const groupUsername = document.getElementById("dailyReportGroupSelect").value;
  try {
    let url = "/api/car-ads-extraction-log";
    if (groupUsername)
      url += `?group_username=${encodeURIComponent(groupUsername)}`;
    const res = await fetch(url);
    const json = await res.json();
    const logs = json.data || [];
    if (logs.length === 0) {
      container.innerHTML = '<div class="empty">هنوز هیچ گزارشی ثبت نشده</div>';
      return;
    }
    container.innerHTML = "";
    logs.forEach((log) => {
      const entry = document.createElement("div");
      entry.className = "daily-log-entry";
      const count = log.added_channels.length;
      const badgeClass = count > 0 ? "" : "zero";
      const channelsHtml =
        count > 0
          ? `<div class="dl-channels">${log.added_channels
              .map((c) => `@${c.username}${c.title ? " — " + c.title : ""}`)
              .join("<br/>")}</div>`
          : '<div class="dl-none">هنوز کانال جدید پیدا نشده است</div>';
      entry.innerHTML = `
          <div class="dl-date">${formatDate(log.run_at)}</div>
          <div class="dl-group">@${
            log.group_username
          }<span class="dl-count-badge ${badgeClass}">${count.toLocaleString(
        "fa-IR"
      )} کانال جدید</span></div>
          ${channelsHtml}
        `;
      container.appendChild(entry);
    });
  } catch (err) {
    container.innerHTML = `<div class="empty">❌ خطا: ${err.message}</div>`;
  }
}

function closeDailyReportModal() {
  document.getElementById("dailyReportModalOverlay").style.display = "none";
}
function closeDailyReportModalOnOverlay(event) {
  if (event.target.id === "dailyReportModalOverlay") closeDailyReportModal();
}
