// ---------- فیلتر ساعتی ----------
function onHoursFilterChange() {
  currentHoursFilter = parseInt(
    document.getElementById("hoursFilterSelect").value,
    10
  );
  currentPage = 1;
  load();
}

// ---------- جدول قیمت‌ها ----------
async function load() {
  const tbody = document.querySelector("#result tbody");
  const searchTerm = document.getElementById("searchTable").value.trim();
  try {
    let url = `/api/car-ads-analytics?hours=${currentHoursFilter}&only_new=true`;
    if (searchTerm) url += `&search=${encodeURIComponent(searchTerm)}`;
    const res = await fetch(url);
    const json = await res.json();

    if (json.error) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">❌ ${json.error}</td></tr>`;
      return;
    }

    allAnalyticsData = json.data;
    visibleAnalyticsData = allAnalyticsData.filter(
      (item) => item.priced_ads > 0
    );

    renderModelCheckboxList();
    renderTable();

    if (modalOpenCarName) {
      refreshModal(modalOpenCarName, modalOpenTrim);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">❌ خطا در دریافت اطلاعات: ${err.message}</td></tr>`;
  }
}

function onFilterChange() {
  currentPage = 1;
  renderTable();
}

function renderModelCheckboxList() {
  const container = document.getElementById("modelCheckboxList");
  const q = document
    .getElementById("modelSearchBox")
    .value.trim()
    .toLowerCase();

  const uniqueModels = Array.from(
    new Set(visibleAnalyticsData.map((item) => item.display_name))
  ).sort((a, b) => a.localeCompare(b, "fa"));

  const filteredModels = q
    ? uniqueModels.filter((name) => name.toLowerCase().includes(q))
    : uniqueModels;

  container.innerHTML = "";

  if (filteredModels.length === 0) {
    container.innerHTML =
      '<div class="model-checkbox-empty">مدلی پیدا نشد</div>';
    return;
  }

  filteredModels.forEach((name, idx) => {
    const checkboxId = `modelCheckbox_${idx}`;
    const wrap = document.createElement("div");
    wrap.className = "model-checkbox-item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = checkboxId;
    checkbox.checked = selectedModels.has(name);
    checkbox.onchange = () => {
      if (checkbox.checked) {
        selectedModels.add(name);
      } else {
        selectedModels.delete(name);
      }
      currentPage = 1;
      renderTable();
    };

    const label = document.createElement("label");
    label.setAttribute("for", checkboxId);
    label.textContent = name;

    wrap.appendChild(checkbox);
    wrap.appendChild(label);
    container.appendChild(wrap);
  });
}

function clearAllFilters() {
  document.getElementById("filterPriceMin").value = "";
  document.getElementById("filterPriceMax").value = "";
  document.getElementById("priceFilterWordsHint").textContent = "";
  document.getElementById("modelSearchBox").value = "";
  document.getElementById("searchTable").value = "";
  selectedModels.clear();
  currentPage = 1;
  renderModelCheckboxList();
  load();
}

function getFilteredData() {
  let data = visibleAnalyticsData;

  if (selectedModels.size > 0)
    data = data.filter((item) => selectedModels.has(item.display_name));

  const minRaw = document
    .getElementById("filterPriceMin")
    .value.replace(/[^\d]/g, "");
  const maxRaw = document
    .getElementById("filterPriceMax")
    .value.replace(/[^\d]/g, "");
  const minToman = minRaw ? parseInt(minRaw, 10) * 1000000 : null;
  const maxToman = maxRaw ? parseInt(maxRaw, 10) * 1000000 : null;

  if (minToman !== null || maxToman !== null) {
    data = data.filter((item) => {
      if (item.min_price === null || item.min_price === undefined) return false;
      if (minToman !== null && item.min_price < minToman) return false;
      if (maxToman !== null && item.min_price > maxToman) return false;
      return true;
    });
  }

  return data;
}

function renderTable() {
  const tbody = document.querySelector("#result tbody");
  const filtered = getFilteredData();
  const totalPages = Math.max(1, Math.ceil(filtered.length / ROWS_PER_PAGE));
  currentPage = Math.min(Math.max(1, currentPage), totalPages);

  const startIdx = (currentPage - 1) * ROWS_PER_PAGE;
  const pageItems = filtered.slice(startIdx, startIdx + ROWS_PER_PAGE);

  tbody.innerHTML = "";

  if (pageItems.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-cell">نتیجه‌ای پیدا نشد</td></tr>`;
  } else {
    pageItems.forEach((item, i) => {
      const tr = document.createElement("tr");
      tr.onclick = () => openModal(item.car_name, item.trim, item.display_name);
      tr.innerHTML = `
          <td class="row-num">${(startIdx + i + 1).toLocaleString("fa-IR")}</td>
          <td>${item.display_name}</td>
          <td>${item.total_ads.toLocaleString("fa-IR")}</td>
          <td>${item.priced_ads.toLocaleString("fa-IR")}</td>
          <td>${formatToman(item.min_price)}</td>
          <td>${formatToman(item.avg_price)}</td>
          <td>${formatToman(item.max_price)}</td>
          <td>${formatDate(item.last_seen)}</td>
        `;
      tbody.appendChild(tr);
    });
  }

  document.getElementById("resultCount").textContent =
    filtered.length > 0
      ? `${filtered.length.toLocaleString("fa-IR")} نتیجه`
      : "";

  renderPagination(filtered.length, totalPages);
}

function renderPagination(totalCount, totalPages) {
  const container = document.getElementById("pagination");

  if (totalCount === 0) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
      <span class="pagination-info">صفحه ${currentPage.toLocaleString(
        "fa-IR"
      )} از ${totalPages.toLocaleString("fa-IR")}</span>
      <div class="pagination-buttons">
        <button id="prevPageBtn" ${
          currentPage <= 1 ? "disabled" : ""
        }>قبلی</button>
        <button id="nextPageBtn" ${
          currentPage >= totalPages ? "disabled" : ""
        }>بعدی</button>
      </div>
    `;

  document.getElementById("prevPageBtn").onclick = () => {
    currentPage--;
    renderTable();
  };
  document.getElementById("nextPageBtn").onclick = () => {
    currentPage++;
    renderTable();
  };
}

function onSearchInput() {
  clearTimeout(tableSearchDebounceTimeout);
  tableSearchDebounceTimeout = setTimeout(() => {
    currentPage = 1;
    load();
  }, TABLE_SEARCH_DEBOUNCE_MS);
}

// ---------- مدال جزئیات هر مدل ----------
async function openModal(carName, trim, displayName) {
  modalOpenCarName = carName;
  modalOpenTrim = trim || null;
  document.getElementById("modalTitle").textContent = displayName || carName;
  document.getElementById("modalMeta").textContent = "در حال بارگذاری...";
  document.getElementById("modalList").innerHTML = "";
  document.getElementById("searchModal").value = "";
  document.getElementById("modalOverlay").style.display = "flex";
  await refreshModal(carName, modalOpenTrim);
}

async function refreshModal(carName, trim) {
  try {
    let url = `/api/car-ads-ads?car_name=${encodeURIComponent(
      carName
    )}&hours=${currentHoursFilter}&only_new=true`;
    if (trim) url += `&trim=${encodeURIComponent(trim)}`;
    const res = await fetch(url);
    const json = await res.json();

    if (json.error) {
      document.getElementById("modalMeta").textContent = "❌ " + json.error;
      return;
    }

    const pricedAds = (json.data || []).filter(
      (ad) => ad.price_amount !== null && ad.price_amount !== undefined
    );
    pricedAds.sort((a, b) => a.price_amount - b.price_amount);
    currentModalAds = pricedAds;
    filterModalAds();

    let metaText = `${currentModalAds.length.toLocaleString(
      "fa-IR"
    )} آگهی با قیمت مشخص`;
    if (currentModalAds.length > 0) {
      const min = currentModalAds[0].price_amount;
      const max = currentModalAds[currentModalAds.length - 1].price_amount;
      metaText += ` — کمترین قیمت: ${formatToman(
        min
      )} — بیشترین قیمت: ${formatToman(max)}`;
    }
    document.getElementById("modalMeta").innerHTML = metaText;
  } catch (err) {
    document.getElementById("modalMeta").textContent = "❌ خطا: " + err.message;
  }
}

function renderModalAds(ads) {
  const list = document.getElementById("modalList");
  list.innerHTML = "";

  if (ads.length === 0) {
    list.innerHTML = '<div class="empty">آگهی‌ای پیدا نشد</div>';
    return;
  }

  const allPrices = currentModalAds
    .map((a) => a.price_amount)
    .filter((p) => p !== null && p !== undefined);
  const minPrice = allPrices.length ? Math.min(...allPrices) : null;
  const maxPrice = allPrices.length ? Math.max(...allPrices) : null;

  ads.forEach((ad) => {
    const priceText = ad.price_amount
      ? formatToman(ad.price_amount)
      : ad.price_label
      ? ad.price_label
      : '<span class="no-price">بدون قیمت مشخص</span>';

    let badge = "";
    if (ad.price_amount !== null && ad.price_amount !== undefined) {
      if (minPrice === maxPrice)
        badge = '<span class="price-badge equal">⭐ تنها قیمت موجود</span>';
      else if (ad.price_amount === minPrice)
        badge = '<span class="price-badge min">🔻 کمترین قیمت</span>';
      else if (ad.price_amount === maxPrice)
        badge = '<span class="price-badge max">🔺 بیشترین قیمت</span>';
    }

    const detailsParts = [];
    if (ad.color) detailsParts.push("رنگ: " + ad.color);
    if (ad.trim) detailsParts.push("تیپ: " + ad.trim);
    if (ad.production_year) detailsParts.push("سال: " + ad.production_year);
    if (ad.mileage_km)
      detailsParts.push(
        "کارکرد: " + ad.mileage_km.toLocaleString("fa-IR") + " کیلومتر"
      );
    if (ad.city) detailsParts.push("شهر: " + ad.city);

    const card = document.createElement("div");
    card.className = "ad-card";
    card.innerHTML = `
        <div class="ad-row">
          <div class="price-group"><strong>${priceText}</strong>${badge}</div>
          <a href="${
            ad.telegram_link
          }" target="_blank" rel="noopener" class="ad-link">مشاهده در تلگرام ↗</a>
        </div>
        ${
          detailsParts.length
            ? `<div class="ad-details">${detailsParts.join(" — ")}</div>`
            : ""
        }
        ${ad.phone ? `<div class="ad-phone">📞 ${ad.phone}</div>` : ""}
        ${ad.notes ? `<div class="ad-notes">${ad.notes}</div>` : ""}
        ${
          ad.message_text ? `<div class="ad-text">${ad.message_text}</div>` : ""
        }
        <div class="ad-date">${formatDate(
          ad.telegram_date || ad.created_at
        )}</div>
      `;
    list.appendChild(card);
  });
}

function filterModalAds() {
  const q = document.getElementById("searchModal").value.trim().toLowerCase();
  if (!q) {
    renderModalAds(currentModalAds);
    return;
  }
  const filtered = currentModalAds.filter((ad) => {
    const haystack = [
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
  renderModalAds(filtered);
}

function closeModal() {
  modalOpenCarName = null;
  modalOpenTrim = null;
  document.getElementById("modalOverlay").style.display = "none";
}
function closeModalOnOverlay(event) {
  if (event.target.id === "modalOverlay") closeModal();
}
