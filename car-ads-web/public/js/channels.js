// ---------- پیش‌نمایش زنده‌ی نام کانال + افزودن ----------
function onChannelInputChange() {
  clearTimeout(channelPreviewTimeout);
  const username = document
    .getElementById("newChannelInput")
    .value.trim()
    .replace(/^@/, "");
  const previewEl = document.getElementById("channelPreview");

  if (!username) {
    previewEl.textContent = "";
    previewEl.className = "channel-preview";
    return;
  }

  previewEl.textContent = "در حال جستجو...";
  previewEl.className = "channel-preview loading";

  channelPreviewTimeout = setTimeout(async () => {
    try {
      const res = await fetch(
        `/api/car-ads-channel-preview?username=${encodeURIComponent(username)}`
      );
      const json = await res.json();
      if (json.found) {
        previewEl.textContent = "✅ " + json.title;
        previewEl.className = "channel-preview found";
      } else {
        previewEl.textContent = "❌ کانالی با این نام پیدا نشد";
        previewEl.className = "channel-preview not-found";
      }
    } catch (err) {
      previewEl.textContent = "";
      previewEl.className = "channel-preview";
    }
  }, CHANNEL_PREVIEW_DEBOUNCE_MS);
}

function onChannelInputKeydown(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    addChannel();
  }
}

async function addChannel() {
  const input = document.getElementById("newChannelInput");
  const previewEl = document.getElementById("channelPreview");
  const username = input.value.trim().replace(/^@/, "");
  if (!username) return;

  try {
    const res = await fetch("/api/car-ads-channels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const json = await res.json();

    if (json.status === "duplicate") {
      previewEl.textContent = "⚠️ این کانال تکراری است — از قبل اضافه شده";
      previewEl.className = "channel-preview duplicate";
      return;
    }

    input.value = "";
    previewEl.textContent = "";
    previewEl.className = "channel-preview";

    if (
      document.getElementById("channelsModalOverlay").style.display === "flex"
    ) {
      await loadChannelsModal();
    }
  } catch (err) {
    previewEl.textContent = "❌ خطا در افزودن کانال";
    previewEl.className = "channel-preview not-found";
  }
}

// ---------- مدال لیست کانال‌ها ----------
async function openChannelsModal() {
  document.getElementById("searchChannelsModal").value = "";
  document.getElementById("channelsModalOverlay").style.display = "flex";
  await loadChannelsModal();
}

async function loadChannelsModal() {
  const list = document.getElementById("channelsModalList");
  list.innerHTML = '<div class="empty">در حال بارگذاری...</div>';
  try {
    const res = await fetch("/api/car-ads-channels");
    const json = await res.json();
    allChannels = json.data || [];
    filterChannelsModal();
  } catch (err) {
    list.innerHTML = `<div class="empty">❌ خطا: ${err.message}</div>`;
  }
}

function filterChannelsModal() {
  const q = document
    .getElementById("searchChannelsModal")
    .value.trim()
    .toLowerCase();
  const filtered = allChannels.filter((ch) =>
    ch.username.toLowerCase().includes(q)
  );
  renderChannelsModal(filtered);
}

function renderChannelsModal(channels) {
  const list = document.getElementById("channelsModalList");
  list.innerHTML = "";

  const activeCount = allChannels.filter((ch) => ch.active).length;
  document.getElementById("channelsModalMeta").textContent =
    `${allChannels.length.toLocaleString(
      "fa-IR"
    )} کانال کل — ${activeCount.toLocaleString("fa-IR")} فعال` +
    (channels.length !== allChannels.length
      ? ` — ${channels.length.toLocaleString("fa-IR")} نتیجه‌ی جستجو`
      : "");

  if (channels.length === 0) {
    list.innerHTML = '<div class="empty">کانالی پیدا نشد</div>';
    return;
  }

  channels.forEach((ch, idx) => {
    const row = document.createElement("div");
    row.className = "channel-row";

    const rowNum = document.createElement("span");
    rowNum.className = "channel-row-num";
    rowNum.textContent = (idx + 1).toLocaleString("fa-IR");

    const nameSpan = document.createElement("span");
    nameSpan.className = "channel-name";
    nameSpan.textContent = "@" + ch.username;
    nameSpan.title = "@" + ch.username;

    const statusSpan = document.createElement("span");
    statusSpan.className = `channel-status ${
      ch.active ? "active" : "inactive"
    }`;
    statusSpan.textContent = ch.active ? "فعال" : "غیرفعال";

    const btn = document.createElement("button");
    btn.textContent = ch.active ? "حذف" : "فعال‌سازی";
    btn.onclick = async () => {
      if (ch.active) {
        await fetch(
          `/api/car-ads-channels/${encodeURIComponent(ch.username)}`,
          { method: "DELETE" }
        );
      } else {
        await fetch("/api/car-ads-channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: ch.username }),
        });
      }
      await loadChannelsModal();
    };

    row.appendChild(rowNum);
    row.appendChild(nameSpan);
    row.appendChild(statusSpan);
    row.appendChild(btn);
    list.appendChild(row);
  });
}

function closeChannelsModal() {
  document.getElementById("channelsModalOverlay").style.display = "none";
}
function closeChannelsModalOnOverlay(event) {
  if (event.target.id === "channelsModalOverlay") closeChannelsModal();
}

// ---------- جستجوی کانال ----------
function openChannelSearchModal() {
  document.getElementById("channelSearchInput").value = "";
  document.getElementById("channelSearchStats").style.display = "none";
  document.querySelector("#channelSearchTable tbody").innerHTML =
    '<tr><td colspan="8" class="empty-cell">نام کانال را در بالا تایپ کن</td></tr>';
  document.getElementById("channelSearchModalOverlay").style.display = "flex";
  setTimeout(() => document.getElementById("channelSearchInput").focus(), 50);
}

function onChannelSearchInput() {
  clearTimeout(channelSearchDebounceTimeout);
  const value = document.getElementById("channelSearchInput").value.trim();
  if (!value) {
    document.getElementById("channelSearchStats").style.display = "none";
    document.querySelector("#channelSearchTable tbody").innerHTML =
      '<tr><td colspan="8" class="empty-cell">نام کانال را در بالا تایپ کن</td></tr>';
    return;
  }
  channelSearchDebounceTimeout = setTimeout(
    () => searchByChannel(value),
    CHANNEL_SEARCH_DEBOUNCE_MS
  );
}

async function searchByChannel(channelName) {
  const tbody = document.querySelector("#channelSearchTable tbody");
  tbody.innerHTML =
    '<tr><td colspan="8" class="empty-cell">در حال جستجو...</td></tr>';
  try {
    const res = await fetch(
      `/api/car-ads-by-channel?channel=${encodeURIComponent(
        channelName
      )}&hours=168`
    );
    const json = await res.json();
    if (json.error) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">❌ ${json.error}</td></tr>`;
      document.getElementById("channelSearchStats").style.display = "none";
      return;
    }
    const ads = json.data || [];
    document.getElementById("channelSearchStats").style.display = "flex";
    document.getElementById("statTotalAds").textContent =
      ads.length.toLocaleString("fa-IR");

    if (ads.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">هیچ آگهی‌ای از این کانال پیدا نشد — یا کانال دقیقاً همین نام را ندارد، یا پیامی از آن پردازش نشده است</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    ads.forEach((ad, i) => {
      const tr = document.createElement("tr");
      tr.onclick = () =>
        openAdDetailModal(ad, "جزئیات آگهی — کانال " + ad.channel);
      const adTypeLabel = ad.ad_type === "wanted_to_buy" ? "خریدارم" : "فروش";
      tr.innerHTML = `
          <td class="row-num">${(i + 1).toLocaleString("fa-IR")}</td>
          <td>${ad.car_name || "—"}</td>
          <td>${formatToman(ad.price_amount)}</td>
          <td>${ad.color || "—"}</td>
          <td>${ad.production_year || "—"}</td>
          <td>${
            ad.mileage_km
              ? ad.mileage_km.toLocaleString("fa-IR") + " کیلومتر"
              : "صفر"
          }</td>
          <td>${adTypeLabel}</td>
          <td>${formatDate(ad.telegram_date || ad.created_at)}</td>
        `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">❌ خطا: ${err.message}</td></tr>`;
  }
}

function closeChannelSearchModal() {
  document.getElementById("channelSearchModalOverlay").style.display = "none";
}
function closeChannelSearchModalOnOverlay(event) {
  if (event.target.id === "channelSearchModalOverlay")
    closeChannelSearchModal();
}
