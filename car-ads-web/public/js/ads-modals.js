// ---------- مودال جزئیات مشترک ----------
function openAdDetailModal(ad, titlePrefix) {
  document.getElementById("adDetailTitle").textContent =
    titlePrefix || "جزئیات آگهی";
  const body = document.getElementById("adDetailBody");

  const priceText = ad.price_amount
    ? formatToman(ad.price_amount)
    : ad.price_label
    ? ad.price_label
    : '<span class="no-price">بدون قیمت مشخص</span>';
  const detailsParts = [];
  if (ad.car_name) detailsParts.push("مدل: " + ad.car_name);
  if (ad.color) detailsParts.push("رنگ: " + ad.color);
  if (ad.trim) detailsParts.push("تیپ: " + ad.trim);
  if (ad.production_year) detailsParts.push("سال: " + ad.production_year);
  if (ad.mileage_km)
    detailsParts.push(
      "کارکرد: " + ad.mileage_km.toLocaleString("fa-IR") + " کیلومتر"
    );
  if (ad.city) detailsParts.push("شهر: " + ad.city);
  if (ad.channel) detailsParts.push("کانال: @" + ad.channel);

  body.innerHTML = `
      <div class="ad-row"><div class="price-group"><strong>${priceText}</strong></div>
        ${
          ad.telegram_link
            ? `<a href="${ad.telegram_link}" target="_blank" rel="noopener" class="ad-link">مشاهده در تلگرام ↗</a>`
            : ""
        }</div>
      ${
        detailsParts.length
          ? `<div class="ad-details">${detailsParts.join(" — ")}</div>`
          : ""
      }
      ${ad.phone ? `<div class="ad-phone">📞 ${ad.phone}</div>` : ""}
      ${ad.notes ? `<div class="ad-notes">${ad.notes}</div>` : ""}
      ${
        ad.message_text
          ? `<div class="ad-text">${ad.message_text}</div>`
          : '<div class="empty">متن پیامی ثبت نشده</div>'
      }
      <div class="ad-date">${formatDate(
        ad.telegram_date || ad.created_at
      )}</div>
    `;
  document.getElementById("adDetailModalOverlay").style.display = "flex";
}
function closeAdDetailModal() {
  document.getElementById("adDetailModalOverlay").style.display = "none";
}
function closeAdDetailModalOnOverlay(event) {
  if (event.target.id === "adDetailModalOverlay") closeAdDetailModal();
}

// ---------- مودال آگهی‌های بدون قیمت — جدولی + صفحه‌بندی ----------
async function openNoPriceAdsModal() {
  document.getElementById("searchNoPriceModal").value = "";
  document.getElementById("modalMetaNoPrice").textContent =
    "در حال بارگذاری...";
  document.querySelector("#noPriceAdsTable tbody").innerHTML = "";
  currentNoPriceAdsPage = 1;
  document.getElementById("noPriceAdsModalOverlay").style.display = "flex";
  try {
    const res = await fetch("/api/car-ads-no-price-ads");
    const json = await res.json();
    if (json.error) {
      document.getElementById("modalMetaNoPrice").textContent =
        "❌ " + json.error;
      return;
    }
    currentNoPriceAds = json.data || [];
    document.getElementById(
      "modalMetaNoPrice"
    ).textContent = `${currentNoPriceAds.length.toLocaleString(
      "fa-IR"
    )} آگهی بدون قیمت`;
    renderNoPriceAdsTable(currentNoPriceAds);
  } catch (err) {
    document.getElementById("modalMetaNoPrice").textContent =
      "❌ خطا: " + err.message;
  }
}

function renderNoPriceAdsTable(ads) {
  const tbody = document.querySelector("#noPriceAdsTable tbody");
  const totalPages = Math.max(1, Math.ceil(ads.length / ROWS_PER_PAGE));
  currentNoPriceAdsPage = Math.min(
    Math.max(1, currentNoPriceAdsPage),
    totalPages
  );
  const startIdx = (currentNoPriceAdsPage - 1) * ROWS_PER_PAGE;
  const pageItems = ads.slice(startIdx, startIdx + ROWS_PER_PAGE);
  tbody.innerHTML = "";
  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">آگهی بدون قیمتی پیدا نشد</td></tr>`;
  } else {
    pageItems.forEach((ad, i) => {
      const tr = document.createElement("tr");
      tr.onclick = () => openAdDetailModal(ad, "جزئیات آگهی بدون قیمت");
      tr.innerHTML = `
          <td class="row-num">${(startIdx + i + 1).toLocaleString("fa-IR")}</td>
          <td>${ad.car_name || "—"}</td>
          <td>${ad.price_label || "—"}</td>
          <td>${ad.color || "—"}</td>
          <td>${ad.production_year || "—"}</td>
          <td>${ad.city || "—"}</td>
          <td>${ad.phone || "—"}</td>
        `;
      tbody.appendChild(tr);
    });
  }
  renderGenericPagination(
    "noPriceAdsPagination",
    ads.length,
    totalPages,
    currentNoPriceAdsPage,
    (p) => {
      currentNoPriceAdsPage = p;
      renderNoPriceAdsTable(getFilteredNoPriceAds());
    }
  );
}

function getFilteredNoPriceAds() {
  const q = document
    .getElementById("searchNoPriceModal")
    .value.trim()
    .toLowerCase();
  if (!q) return currentNoPriceAds;
  return currentNoPriceAds.filter((ad) => {
    const haystack = [
      ad.car_name,
      ad.phone,
      ad.color,
      ad.trim,
      ad.notes,
      ad.message_text,
      ad.city,
      ad.price_label,
      ad.channel,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

function filterNoPriceAds() {
  currentNoPriceAdsPage = 1;
  renderNoPriceAdsTable(getFilteredNoPriceAds());
}

function closeNoPriceAdsModal() {
  document.getElementById("noPriceAdsModalOverlay").style.display = "none";
}
function closeNoPriceAdsModalOnOverlay(event) {
  if (event.target.id === "noPriceAdsModalOverlay") closeNoPriceAdsModal();
}

// ---------- مودال خودروهای کارکرده ----------
async function openUsedCarsModal() {
  document.getElementById("searchUsedCarsModal").value = "";
  document.getElementById("modalMetaUsedCars").textContent =
    "در حال بارگذاری...";
  document.querySelector("#usedCarsTable tbody").innerHTML = "";
  currentUsedCarsPage = 1;
  document.getElementById("usedCarsModalOverlay").style.display = "flex";
  try {
    const res = await fetch(
      `/api/car-ads-used-cars?hours=${currentHoursFilter}`
    );
    const json = await res.json();
    if (json.error) {
      document.getElementById("modalMetaUsedCars").textContent =
        "❌ " + json.error;
      return;
    }
    currentUsedCars = json.data || [];
    document.getElementById(
      "modalMetaUsedCars"
    ).textContent = `${currentUsedCars.length.toLocaleString(
      "fa-IR"
    )} آگهی کارکرده`;
    renderUsedCarsTable(currentUsedCars);
  } catch (err) {
    document.getElementById("modalMetaUsedCars").textContent =
      "❌ خطا: " + err.message;
  }
}

function renderUsedCarsTable(cars) {
  const tbody = document.querySelector("#usedCarsTable tbody");
  const totalPages = Math.max(1, Math.ceil(cars.length / ROWS_PER_PAGE));
  currentUsedCarsPage = Math.min(Math.max(1, currentUsedCarsPage), totalPages);
  const startIdx = (currentUsedCarsPage - 1) * ROWS_PER_PAGE;
  const pageItems = cars.slice(startIdx, startIdx + ROWS_PER_PAGE);
  tbody.innerHTML = "";
  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="empty-cell">آگهی کارکرده‌ای پیدا نشد</td></tr>`;
  } else {
    pageItems.forEach((ad, i) => {
      const tr = document.createElement("tr");
      tr.onclick = () => openAdDetailModal(ad, "جزئیات خودروی کارکرده");
      tr.innerHTML = `
          <td class="row-num">${(startIdx + i + 1).toLocaleString("fa-IR")}</td>
          <td>${ad.car_name || "—"}</td>
          <td>${formatToman(ad.price_amount)}</td>
          <td>${ad.color || "—"}</td>
          <td>${ad.trim || "—"}</td>
          <td>${ad.production_year || "—"}</td>
          <td>${
            ad.mileage_km ? ad.mileage_km.toLocaleString("fa-IR") : "—"
          }</td>
          <td>${ad.city || "—"}</td>
          <td>${ad.phone || "—"}</td>
        `;
      tbody.appendChild(tr);
    });
  }
  renderGenericPagination(
    "usedCarsPagination",
    cars.length,
    totalPages,
    currentUsedCarsPage,
    (p) => {
      currentUsedCarsPage = p;
      renderUsedCarsTable(getFilteredUsedCars());
    }
  );
}

function getFilteredUsedCars() {
  const q = document
    .getElementById("searchUsedCarsModal")
    .value.trim()
    .toLowerCase();
  if (!q) return currentUsedCars;
  return currentUsedCars.filter((ad) => {
    const haystack = [
      ad.car_name,
      ad.color,
      ad.trim,
      ad.phone,
      ad.city,
      ad.notes,
      ad.message_text,
      ad.channel,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

function filterUsedCars() {
  currentUsedCarsPage = 1;
  renderUsedCarsTable(getFilteredUsedCars());
}

function closeUsedCarsModal() {
  document.getElementById("usedCarsModalOverlay").style.display = "none";
}
function closeUsedCarsModalOnOverlay(event) {
  if (event.target.id === "usedCarsModalOverlay") closeUsedCarsModal();
}

// ---------- مودال آگهی‌های خریدارم ----------
async function openWantedAdsModal() {
  document.getElementById("searchWantedAdsModal").value = "";
  document.getElementById("modalMetaWanted").textContent = "در حال بارگذاری...";
  document.querySelector("#wantedAdsTable tbody").innerHTML = "";
  currentWantedAdsPage = 1;
  document.getElementById("wantedAdsModalOverlay").style.display = "flex";
  try {
    const res = await fetch("/api/car-ads-wanted-ads");
    const json = await res.json();
    if (json.error) {
      document.getElementById("modalMetaWanted").textContent =
        "❌ " + json.error;
      return;
    }
    currentWantedAds = json.data || [];
    document.getElementById(
      "modalMetaWanted"
    ).textContent = `${currentWantedAds.length.toLocaleString(
      "fa-IR"
    )} آگهی خریدارم`;
    renderWantedAdsTable(currentWantedAds);
  } catch (err) {
    document.getElementById("modalMetaWanted").textContent =
      "❌ خطا: " + err.message;
  }
}

function renderWantedAdsTable(ads) {
  const tbody = document.querySelector("#wantedAdsTable tbody");
  const totalPages = Math.max(1, Math.ceil(ads.length / ROWS_PER_PAGE));
  currentWantedAdsPage = Math.min(
    Math.max(1, currentWantedAdsPage),
    totalPages
  );
  const startIdx = (currentWantedAdsPage - 1) * ROWS_PER_PAGE;
  const pageItems = ads.slice(startIdx, startIdx + ROWS_PER_PAGE);
  tbody.innerHTML = "";
  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-cell">آگهی «خریدارم»ی پیدا نشد</td></tr>`;
  } else {
    pageItems.forEach((ad, i) => {
      const tr = document.createElement("tr");
      tr.onclick = () => openAdDetailModal(ad, "جزئیات آگهی خریدارم");
      const priceText = ad.price_amount
        ? formatToman(ad.price_amount)
        : ad.price_label || "—";
      tr.innerHTML = `
          <td class="row-num">${(startIdx + i + 1).toLocaleString("fa-IR")}</td>
          <td>${ad.car_name || "—"}</td>
          <td>${priceText}</td>
          <td>${ad.color || "—"}</td>
          <td>${ad.production_year || "—"}</td>
          <td>${ad.city || "—"}</td>
          <td>${ad.phone || "—"}</td>
        `;
      tbody.appendChild(tr);
    });
  }
  renderGenericPagination(
    "wantedAdsPagination",
    ads.length,
    totalPages,
    currentWantedAdsPage,
    (p) => {
      currentWantedAdsPage = p;
      renderWantedAdsTable(getFilteredWantedAds());
    }
  );
}

function getFilteredWantedAds() {
  const q = document
    .getElementById("searchWantedAdsModal")
    .value.trim()
    .toLowerCase();
  if (!q) return currentWantedAds;
  return currentWantedAds.filter((ad) => {
    const haystack = [
      ad.car_name,
      ad.phone,
      ad.color,
      ad.notes,
      ad.message_text,
      ad.city,
      ad.price_label,
      ad.channel,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
}

function filterWantedAds() {
  currentWantedAdsPage = 1;
  renderWantedAdsTable(getFilteredWantedAds());
}

function closeWantedAdsModal() {
  document.getElementById("wantedAdsModalOverlay").style.display = "none";
}
function closeWantedAdsModalOnOverlay(event) {
  if (event.target.id === "wantedAdsModalOverlay") closeWantedAdsModal();
}

// ---------- کمکی: صفحه‌بندی عمومی ----------
function renderGenericPagination(
  containerId,
  totalCount,
  totalPages,
  page,
  onPageChange
) {
  const container = document.getElementById(containerId);
  if (totalCount === 0) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `
      <span class="pagination-info">صفحه ${page.toLocaleString(
        "fa-IR"
      )} از ${totalPages.toLocaleString("fa-IR")}</span>
      <div class="pagination-buttons">
        <button id="${containerId}_prev" ${
    page <= 1 ? "disabled" : ""
  }>قبلی</button>
        <button id="${containerId}_next" ${
    page >= totalPages ? "disabled" : ""
  }>بعدی</button>
      </div>
    `;
  document.getElementById(`${containerId}_prev`).onclick = () =>
    onPageChange(page - 1);
  document.getElementById(`${containerId}_next`).onclick = () =>
    onPageChange(page + 1);
}
