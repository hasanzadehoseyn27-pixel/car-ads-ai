// ---------- ثابت‌ها ----------
const REFRESH_INTERVAL_STORAGE_KEY = "carAdsRefreshIntervalMs";
const DEFAULT_REFRESH_INTERVAL_MS = 10000;
const CHANNEL_PREVIEW_DEBOUNCE_MS = 450;
const TABLE_SEARCH_DEBOUNCE_MS = 450;
const CHANNEL_SEARCH_DEBOUNCE_MS = 450;
const ROWS_PER_PAGE = 10;
const ALERT_CHECK_INTERVAL_MS = 15000;
const ACCOUNT_STATUS_REFRESH_MS = 20000;
const EXTRACTION_PROGRESS_POLL_MS = 2000;

// ---------- متغیرهای وضعیت سراسری ----------
let REFRESH_INTERVAL_MS =
  parseInt(localStorage.getItem(REFRESH_INTERVAL_STORAGE_KEY), 10) ||
  DEFAULT_REFRESH_INTERVAL_MS;
let refreshTimer = null;
let alertCheckTimer = null;
let accountStatusTimer = null;
let extractionProgressTimer = null;
let currentHoursFilter = 24;
let tableSearchDebounceTimeout = null;
let channelSearchDebounceTimeout = null;
let currentAlertPriceMode = "range";
let currentExtractionRunId = null;
let shownProgressIds = new Set();

let allAnalyticsData = [];
let visibleAnalyticsData = [];
let currentPage = 1;

let currentModalAds = [];
let modalOpenCarName = null;
let modalOpenTrim = null;
let allChannels = [];
let channelPreviewTimeout = null;

let currentNoPriceAds = [];
let currentNoPriceAdsPage = 1;
let currentWantedAds = [];
let currentWantedAdsPage = 1;
let currentUsedCars = [];
let currentUsedCarsPage = 1;

let selectedModels = new Set();
