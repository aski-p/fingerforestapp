const sessionKey = "fruitUiLoggedIn";
const loggedOutKey = "fruitUiLoggedOut";
const fruitSessionKey = "fruitSessionToken";
const fruitOwnerKey = "fruitOwnerKey";
const fruitDeviceKey = "fruitDeviceId";
const cachedStateKey = "fruitCachedState";
const rememberLoginKey = "fruitRememberLogin";
const rememberedLoginIdKey = "fruitRememberLoginId";
const rememberedLoginPwKey = "fruitRememberLoginPw";
const lastReceivedNotificationKey = "fruitLastReceivedNotificationId";
const themeKey = "fruitTheme";
const fontKey = "fruitFont";
const profilePhotoKey = "fruitProfilePhoto";
const profilePhotoCacheKey = "fruitProfilePhotoCache";
const securityMigrationKey = "fruitSecurityMigrationV85";
const releaseNotesSnoozeKey = "fruitReleaseNotesSnoozeUntil";
const supportUrl = "https://qr.kakaopay.com/Ej7ruxJDq";
const appVersion = "2.9";
const primaryApiBaseUrl = "https://web-production-011c4.up.railway.app";
const fallbackBaseUrl = "https://web-production-011c4.up.railway.app";
const activeApiBaseKey = "fruitActiveApiBaseV26";
const apiTimeoutMs = 8000;
const recentNotificationWindowMs = 2 * 60 * 1000;
let latestAppInfo = null;
let releaseNotesShownThisSession = false;

function nativeStoreGet(key) {
  try {
    if (window.FruitAndroid?.getLocal) return window.FruitAndroid.getLocal(key) || "";
  } catch (_err) {
    // Native storage is a durability mirror. Web storage remains the fallback.
  }
  return "";
}

function nativeStoreSet(key, value) {
  try {
    if (window.FruitAndroid?.saveLocal) window.FruitAndroid.saveLocal(key, String(value ?? ""));
  } catch (_err) {
    // Native storage is best-effort.
  }
}

function nativeStoreRemove(key) {
  try {
    if (window.FruitAndroid?.removeLocal) window.FruitAndroid.removeLocal(key);
  } catch (_err) {
    // Native storage is best-effort.
  }
}

function storeGet(key) {
  const webValue = localStorage.getItem(key);
  if (webValue !== null) return webValue;
  const nativeValue = nativeStoreGet(key);
  if (nativeValue) {
    localStorage.setItem(key, nativeValue);
    return nativeValue;
  }
  return "";
}

function storeSet(key, value) {
  const nextValue = String(value ?? "");
  localStorage.setItem(key, nextValue);
  nativeStoreSet(key, nextValue);
}

function storeRemove(key) {
  localStorage.removeItem(key);
  nativeStoreRemove(key);
}

function randomId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const values = new Uint8Array(16);
  window.crypto?.getRandomValues?.(values);
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("") || `${Date.now()}-${Math.random()}`;
}

function deviceId() {
  let value = storeGet(fruitDeviceKey);
  if (!value) {
    value = `device:${randomId()}`;
    storeSet(fruitDeviceKey, value);
  }
  return value;
}

function expectedOwnerKey() {
  return currentOwnerKey || "";
}

const params = new URLSearchParams(location.search);
const token = params.get("token") || storeGet("fruitToken") || "";
if (token) storeSet("fruitToken", token);

function clearSessionStorage() {
  fruitSession = "";
  currentOwnerKey = "";
  authValidated = false;
  storeRemove(fruitSessionKey);
  storeRemove(fruitOwnerKey);
  storeRemove(cachedStateKey);
  storeSet(loggedOutKey, "1");
  try {
    if (window.FruitAndroid?.saveSession) window.FruitAndroid.saveSession("");
  } catch (_err) {
    // Native session clearing is best-effort.
  }
}

function runSecurityMigration() {
  if (storeGet(securityMigrationKey) === "1") return;
  storeRemove(fruitSessionKey);
  storeRemove(fruitOwnerKey);
  storeRemove(cachedStateKey);
  storeRemove(rememberedLoginIdKey);
  storeRemove(rememberedLoginPwKey);
  storeRemove(rememberLoginKey);
  storeRemove(loggedOutKey);
  storeSet(securityMigrationKey, "1");
  try {
    if (window.FruitAndroid?.saveSession) window.FruitAndroid.saveSession("");
    if (window.FruitAndroid?.removeLocal) {
      [
        fruitSessionKey,
        cachedStateKey,
        rememberedLoginIdKey,
        rememberedLoginPwKey,
        rememberLoginKey,
        fruitOwnerKey,
        "fruitSecurityMigrationV70",
        "fruitSecurityMigrationV58",
        "fruitSecurityMigrationV62",
      ].forEach((key) => window.FruitAndroid.removeLocal(key));
    }
  } catch (_err) {
    // Native migration is best-effort.
  }
}

const $ = (id) => document.getElementById(id);
let currentState = {};
let busy = false;
runSecurityMigration();
let fruitSession = "";
let currentOwnerKey = "";
let authValidated = false;
let recoveringSession = null;
let pushSyncing = false;
let selectedHistoryDate = localDateValue(new Date());
let pendingAppearanceSettings = null;
let worklogProjects = [];
let selectedWorklogDates = [];
let selectedWorklogDays = [];
let calendarDraftDates = [];
let worklogCalendarMonth = new Date();
let pendingWorklogTarget = null;
let worklogDraftDirty = false;
let activeAppearanceSettings = { theme: "default", font: "pretendard" };

let koreanPublicHolidays = {
  "2025-01-01": "신정",
  "2025-01-27": "임시공휴일",
  "2025-01-28": "설날 연휴",
  "2025-01-29": "설날",
  "2025-01-30": "설날 연휴",
  "2025-03-01": "삼일절",
  "2025-03-03": "삼일절 대체공휴일",
  "2025-05-01": "노동절",
  "2025-05-05": "어린이날/부처님오신날",
  "2025-05-06": "어린이날/부처님오신날 대체공휴일",
  "2025-06-03": "대통령선거일",
  "2025-06-06": "현충일",
  "2025-07-17": "제헌절",
  "2025-08-15": "광복절",
  "2025-10-03": "개천절",
  "2025-10-05": "추석 연휴",
  "2025-10-06": "추석",
  "2025-10-07": "추석 연휴",
  "2025-10-08": "추석 대체공휴일",
  "2025-10-09": "한글날",
  "2025-12-25": "성탄절",
  "2026-01-01": "신정",
  "2026-02-16": "설날 연휴",
  "2026-02-17": "설날",
  "2026-02-18": "설날 연휴",
  "2026-03-01": "삼일절",
  "2026-03-02": "삼일절 대체공휴일",
  "2026-05-01": "노동절",
  "2026-05-05": "어린이날",
  "2026-05-24": "부처님오신날",
  "2026-05-25": "부처님오신날 대체공휴일",
  "2026-06-03": "전국동시지방선거일",
  "2026-06-06": "현충일",
  "2026-07-17": "제헌절",
  "2026-08-15": "광복절",
  "2026-08-17": "광복절 대체공휴일",
  "2026-09-24": "추석 연휴",
  "2026-09-25": "추석",
  "2026-09-26": "추석 연휴",
  "2026-10-03": "개천절",
  "2026-10-05": "개천절 대체공휴일",
  "2026-10-09": "한글날",
  "2026-12-25": "성탄절",
  "2027-01-01": "신정",
  "2027-02-06": "설날 연휴",
  "2027-02-07": "설날",
  "2027-02-08": "설날 연휴",
  "2027-02-09": "설날 대체공휴일",
  "2027-03-01": "삼일절",
  "2027-05-01": "노동절",
  "2027-05-05": "어린이날",
  "2027-05-13": "부처님오신날",
  "2027-06-06": "현충일",
  "2027-07-17": "제헌절",
  "2027-08-15": "광복절",
  "2027-08-16": "광복절 대체공휴일",
  "2027-09-14": "추석 연휴",
  "2027-09-15": "추석",
  "2027-09-16": "추석 연휴",
  "2027-10-03": "개천절",
  "2027-10-04": "개천절 대체공휴일",
  "2027-10-09": "한글날",
  "2027-10-11": "한글날 대체공휴일",
  "2027-12-25": "성탄절",
  "2027-12-27": "성탄절 대체공휴일",
};

function isIosWebKit() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function enableReliableInputFocus(input) {
  if (!input || !isIosWebKit()) return;
  const focusFromTouch = () => {
    if (document.activeElement !== input) input.focus({ preventScroll: true });
    window.setTimeout(() => input.scrollIntoView({ block: "center", inline: "nearest" }), 80);
  };
  input.addEventListener("touchend", focusFromTouch, { passive: true });
  input.addEventListener("focus", () => {
    window.setTimeout(() => input.scrollIntoView({ block: "center", inline: "nearest" }), 180);
  });
}

["loginId", "loginPw"].forEach((id) => enableReliableInputFocus($(id)));

const themes = [
  { id: "default", label: "Fresh", swatch: ["#f7f9fc", "#10b981", "#111827"] },
  { id: "dark", label: "Dark", swatch: ["#101418", "#34d399", "#e8edf2"] },
  { id: "berry", label: "Berry", swatch: ["#fff0f7", "#ec4899", "#9d174d"] },
  { id: "ocean", label: "Ocean", swatch: ["#f2fbff", "#0ea5e9", "#0f3f5d"] },
  { id: "sunset", label: "Sunset", swatch: ["#fff8f1", "#f97316", "#7c2d12"] },
  { id: "forest", label: "Forest", swatch: ["#f3f8f0", "#84cc16", "#263d12"] },
  { id: "mint", label: "Mint", swatch: ["#f0fdfa", "#14b8a6", "#134e4a"] },
  { id: "lemon", label: "Lemon", swatch: ["#fffde7", "#facc15", "#713f12"] },
  { id: "cherry", label: "Cherry", swatch: ["#fff1f2", "#f43f5e", "#881337"] },
  { id: "lavender", label: "Lavender", swatch: ["#f5f3ff", "#8b5cf6", "#3b0764"] },
  { id: "graphite", label: "Graphite", swatch: ["#f8fafc", "#64748b", "#0f172a"] },
  { id: "cocoa", label: "Cocoa", swatch: ["#fff7ed", "#a16207", "#422006"] },
  { id: "cyber", label: "Cyber", swatch: ["#ecfeff", "#06b6d4", "#164e63"] },
  { id: "peach", label: "Peach", swatch: ["#fff7ed", "#fb7185", "#7c2d12"] },
  { id: "mono", label: "Mono", swatch: ["#fafafa", "#525252", "#171717"] },
  { id: "royal", label: "Royal", swatch: ["#f8fafc", "#2563eb", "#1e1b4b"] },
  { id: "getter", label: "Getter Robo", category: "special", swatch: ["#120306", "#d90429", "#39ff88"] },
];

const fonts = [
  { id: "pretendard", label: "Pretendard" },
  { id: "noto", label: "Noto Sans" },
  { id: "system", label: "System" },
  { id: "rounded", label: "Rounded" },
  { id: "serif", label: "Serif" },
  { id: "mono", label: "Mono" },
  { id: "humanist", label: "Humanist" },
  { id: "condensed", label: "Condensed" },
  { id: "classic", label: "Classic" },
  { id: "editorial", label: "Editorial" },
  { id: "playful", label: "Playful" },
  { id: "clean", label: "Clean" },
  { id: "slab", label: "Slab" },
  { id: "geometric", label: "Geometric" },
  { id: "typewriter", label: "Typewriter" },
];

function intervalMinutes(state = currentState) {
  const minutes = Number(state.runIntervalMinutes || 5);
  if (!Number.isFinite(minutes)) return 5;
  return Math.max(5, Math.min(60, minutes));
}

function isUnlocked() {
  return authValidated && !!fruitSession && storeGet(loggedOutKey) !== "1";
}

function toast(message) {
  $("toast").textContent = message || "";
}

function compareVersions(a, b) {
  const left = String(a || "0").split(".").map((part) => Number(part) || 0);
  const right = String(b || "0").split(".").map((part) => Number(part) || 0);
  const length = Math.max(left.length, right.length);
  for (let i = 0; i < length; i += 1) {
    if ((left[i] || 0) > (right[i] || 0)) return 1;
    if ((left[i] || 0) < (right[i] || 0)) return -1;
  }
  return 0;
}

function installedAppVersion() {
  try {
    if (window.FruitAndroid?.getAppVersion) return window.FruitAndroid.getAppVersion() || appVersion;
    if (window.FruitAndroid) return "0.0";
  } catch (_err) {
    if (window.FruitAndroid) return "0.0";
  }
  return appVersion;
}

function isModalVisible(id) {
  const element = $(id);
  return !!element && !element.classList.contains("hidden");
}

function syncModalOpenState() {
  const visible = [
    "historyModal",
    "settingsModal",
    "profileModal",
    "releaseNotesModal",
    "worklogCalendarModal",
  ].some(isModalVisible);
  document.body.classList.toggle("modal-open", visible);
}

function normalizeBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function apiBaseCandidates() {
  const currentBase = normalizeBaseUrl(location.origin);
  const primaryBase = normalizeBaseUrl(primaryApiBaseUrl);
  const fallbackBase = normalizeBaseUrl(fallbackBaseUrl);
  const activeBase = normalizeBaseUrl(storeGet(activeApiBaseKey));
  return [activeBase, currentBase, primaryBase, fallbackBase].filter((item, index, list) => item && list.indexOf(item) === index);
}

function apiUrl(baseUrl, path) {
  if (/^https?:\/\//.test(path)) return path;
  return `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}

function shouldTryFallback(error, response) {
  if (error) return true;
  if (!response) return false;
  return response.status === 530 || response.status === 522 || response.status === 523 || response.status === 524 || response.status >= 500;
}

async function resilientFetch(path, options = {}) {
  let lastError = null;
  const bases = apiBaseCandidates();
  for (const baseUrl of bases) {
    let response = null;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), apiTimeoutMs);
    try {
      response = await fetch(apiUrl(baseUrl, path), { ...options, signal: controller.signal });
      if (!shouldTryFallback(null, response)) {
        storeSet(activeApiBaseKey, baseUrl);
        return response;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (err) {
      lastError = err;
    } finally {
      clearTimeout(timeoutId);
    }
    if (shouldTryFallback(lastError, response)) continue;
  }
  throw lastError || new Error("서버 연결 실패");
}

async function fetchLatestAppInfo() {
  const bases = apiBaseCandidates();
  const results = await Promise.allSettled(
    bases.map(async (baseUrl) => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), apiTimeoutMs);
      try {
        const res = await fetch(apiUrl(baseUrl, "/api/app-info"), {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!data.ok || !data.result?.latestVersion) throw new Error("invalid app info");
        return { baseUrl, info: data.result };
      } finally {
        clearTimeout(timeoutId);
      }
    }),
  );
  const valid = results
    .filter((result) => result.status === "fulfilled")
    .map((result) => result.value);
  if (!valid.length) throw new Error("앱 버전 정보를 가져오지 못했습니다.");
  const currentVersion = installedAppVersion();
  const preferredBase = normalizeBaseUrl(primaryApiBaseUrl);
  const nonDowngrade = valid.filter((item) => compareVersions(item.info.latestVersion, currentVersion) >= 0);
  const candidates = nonDowngrade.length ? nonDowngrade : valid;
  candidates.sort((a, b) => {
    const versionCompare = compareVersions(b.info.latestVersion, a.info.latestVersion);
    if (versionCompare !== 0) return versionCompare;
    if (a.baseUrl === preferredBase && b.baseUrl !== preferredBase) return -1;
    if (b.baseUrl === preferredBase && a.baseUrl !== preferredBase) return 1;
    const bNotes = Array.isArray(b.info.releaseNotes) ? b.info.releaseNotes.length : 0;
    const aNotes = Array.isArray(a.info.releaseNotes) ? a.info.releaseNotes.length : 0;
    return bNotes - aNotes;
  });
  storeSet(activeApiBaseKey, candidates[0].baseUrl);
  return candidates[0].info;
}

async function checkAppVersion() {
  try {
    const info = await fetchLatestAppInfo();
    latestAppInfo = info;
    if (info.publicHolidays && typeof info.publicHolidays === "object") {
      koreanPublicHolidays = { ...koreanPublicHolidays, ...info.publicHolidays };
      renderWorklogDates();
    }
  } catch (_err) {
    return false;
  }
  return false;
}

function openSupportLink(event) {
  event.preventDefault();
  try {
    if (window.FruitAndroid?.openSupport) {
      window.FruitAndroid.openSupport(supportUrl);
      return;
    }
  } catch (_err) {
    // Fall through to the web link if the native bridge is unavailable.
  }
  window.open(supportUrl, "_blank", "noopener");
}

function getProfilePhoto() {
  return storeGet(profilePhotoKey) || "";
}

function storedSenderProfilePhoto(state = currentState) {
  return state?.senderProfilePhotoUrl || state?.profilePhotoUrl || getProfilePhoto() || "";
}

function profilePhotoCache() {
  try {
    const cache = JSON.parse(storeGet(profilePhotoCacheKey) || "{}");
    return cache && typeof cache === "object" ? cache : {};
  } catch (_err) {
    storeRemove(profilePhotoCacheKey);
    return {};
  }
}

function getCachedProfilePhoto(employeeId) {
  const key = String(employeeId || "");
  if (!key) return "";
  return profilePhotoCache()[key] || "";
}

function currentSenderEmployeeId(state = currentState) {
  return state?.senderEmployeeId || state?.loginUserId || "";
}

function currentSenderPhoto() {
  const senderId = currentSenderEmployeeId();
  return storedSenderProfilePhoto(currentState) || getCachedProfilePhoto(senderId) || appliedAvatarPhoto($("heroProfileBtn").querySelector(".profile-avatar")) || "";
}

function appliedAvatarPhoto(button) {
  if (!button) return "";
  const value = button.style.getPropertyValue("--profile-photo") || "";
  const match = value.match(/^url\(["']?(.*?)["']?\)$/);
  return match ? match[1] : "";
}

function rememberProfilePhoto(employeeId, photoUrl) {
  const key = String(employeeId || "");
  const photo = String(photoUrl || "");
  if (!key || !photo) return;
  const cache = profilePhotoCache();
  cache[key] = photo;
  storeSet(profilePhotoCacheKey, JSON.stringify(cache));
}

function setSenderProfilePhoto(photoUrl) {
  const photo = String(photoUrl || "");
  const senderId = currentSenderEmployeeId();
  if (photo) {
    storeSet(profilePhotoKey, photo);
    currentState.senderProfilePhotoUrl = photo;
    currentState.profilePhotoUrl = photo;
    rememberProfilePhoto(senderId, photo);
    return;
  }
  storeRemove(profilePhotoKey);
  currentState.senderProfilePhotoUrl = "";
  currentState.profilePhotoUrl = "";
  forgetProfilePhoto(senderId);
}

function forgetProfilePhoto(employeeId) {
  const key = String(employeeId || "");
  if (!key) return;
  const cache = profilePhotoCache();
  delete cache[key];
  storeSet(profilePhotoCacheKey, JSON.stringify(cache));
}

function getInitial(label) {
  const clean = String(label || "").trim();
  return (clean[0] || "F").toUpperCase();
}

function applyAvatar(button, initialEl, label, photoUrl = getProfilePhoto()) {
  const photo = String(photoUrl || "").trim();
  button.classList.toggle("has-photo", !!photo);
  button.classList.toggle("hidden", !label && !photo);
  button.style.setProperty("--profile-photo", photo ? `url("${photo}")` : "none");
  initialEl.textContent = getInitial(label);
}

function updateProfileUi(label, unlocked = isUnlocked(), photoUrl = getProfilePhoto()) {
  const displayLabel = unlocked ? label || "사용자" : "fingerfruit";
  const displayPhoto = unlocked ? photoUrl : "";
  document.body.classList.toggle("logged-out", !unlocked);
  $("heroTitleText").textContent = displayLabel;
  $("profileUserName").textContent = displayLabel;
  applyAvatar($("heroProfileBtn").querySelector(".profile-avatar"), $("heroAvatarInitial"), displayLabel, displayPhoto);
  applyAvatar($("profilePreview"), $("profilePreviewInitial"), displayLabel, displayPhoto);
}

function readImageAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("이미지를 읽지 못했습니다."));
    reader.readAsDataURL(file);
  });
}

async function resizeProfilePhoto(file) {
  const dataUrl = await readImageAsDataUrl(file);
  const image = new Image();
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error("지원하지 않는 이미지입니다."));
    image.src = dataUrl;
  });
  const size = 512;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const sourceSize = Math.min(image.naturalWidth || image.width, image.naturalHeight || image.height);
  const sx = ((image.naturalWidth || image.width) - sourceSize) / 2;
  const sy = ((image.naturalHeight || image.height) - sourceSize) / 2;
  ctx.drawImage(image, sx, sy, sourceSize, sourceSize, 0, 0, size, size);
  return canvas.toDataURL("image/jpeg", 0.86);
}

function applyAppearance() {
  const { theme, font } = appearanceSettings();
  previewAppearance({ theme, font });
}

function initializeAppearanceSettings() {
  setAppearanceSettings({
    theme: storeGet(themeKey) || "default",
    font: storeGet(fontKey) || "pretendard",
  });
}

function previewAppearance(settings = appearanceSettings()) {
  const theme = themes.some((item) => item.id === settings.theme) ? settings.theme : "default";
  const font = fonts.some((item) => item.id === settings.font) ? settings.font : "pretendard";
  document.body.classList.remove(...themes.map((item) => `theme-${item.id}`));
  document.body.classList.remove(...fonts.map((item) => `font-${item.id}`));
  if (theme !== "default") document.body.classList.add(`theme-${theme}`);
  document.body.classList.add(`font-${font}`);
  updateAppearanceSelection({ theme, font });
}

function updateAppearanceSelection(settings = appearanceSettings()) {
  document.querySelectorAll("[data-theme-option]").forEach((button) => {
    const selected = button.dataset.themeOption === settings.theme;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  document.querySelectorAll("[data-font-option]").forEach((button) => {
    const selected = button.dataset.fontOption === settings.font;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  });
}

function scrollSelectedAppearanceIntoView() {
  const selectedTheme = document.querySelector("[data-theme-option].selected");
  const selectedFont = document.querySelector("[data-font-option].selected");
  requestAnimationFrame(() => {
    selectedTheme?.scrollIntoView({ block: "nearest", inline: "nearest" });
    selectedFont?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
}

function appearanceSettings() {
  const theme = activeAppearanceSettings.theme || "default";
  const font = activeAppearanceSettings.font || "pretendard";
  return {
    theme: themes.some((item) => item.id === theme) ? theme : "default",
    font: fonts.some((item) => item.id === font) ? font : "pretendard",
  };
}

function setAppearanceSettings(settings = {}) {
  const theme = themes.some((item) => item.id === settings.theme) ? settings.theme : "default";
  const font = fonts.some((item) => item.id === settings.font) ? settings.font : "pretendard";
  activeAppearanceSettings = { theme, font };
  storeSet(themeKey, theme);
  storeSet(fontKey, font);
  applyAppearance();
}

async function loadProfileSettings({ silent = true } = {}) {
  if (!isUnlocked()) return;
  try {
    const settings = await api("/api/profile-settings");
    setAppearanceSettings(settings);
  } catch (err) {
    if (!silent) toast(`설정 불러오기 실패: ${err.message}`);
  }
}

async function saveProfileSettings() {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    const settings = await api("/api/profile-settings", pendingAppearanceSettings || appearanceSettings());
    setAppearanceSettings(settings);
    toast(settings.synced ? "설정을 프로필에 저장했습니다." : "설정을 기기에 저장했습니다. DB 동기화는 나중에 다시 시도됩니다.");
    closeSettingsModal();
  } catch (err) {
    toast(`설정 저장 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
}

function renderAppearanceOptions() {
  const themeBox = $("themeOptions");
  const fontBox = $("fontOptions");
  themeBox.innerHTML = "";
  fontBox.innerHTML = "";
  themes.forEach((theme) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "option-button";
    button.dataset.themeOption = theme.id;
    button.innerHTML = `
      <span class="option-swatch" style="--swatch-a:${theme.swatch[0]};--swatch-b:${theme.swatch[1]};--swatch-c:${theme.swatch[2]}"></span>
      <span class="option-title">${escapeHtml(theme.label)}</span>
      ${theme.category === "special" ? '<span class="option-meta">스페셜 스킨</span>' : ""}
    `;
    button.addEventListener("click", () => {
      pendingAppearanceSettings = { ...(pendingAppearanceSettings || appearanceSettings()), theme: theme.id };
      previewAppearance(pendingAppearanceSettings);
    });
    themeBox.appendChild(button);
  });
  fonts.forEach((font) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `option-button font-${font.id}-sample`;
    button.dataset.fontOption = font.id;
    button.innerHTML = `<span class="option-title">${escapeHtml(font.label)}</span>`;
    button.addEventListener("click", () => {
      pendingAppearanceSettings = { ...(pendingAppearanceSettings || appearanceSettings()), font: font.id };
      previewAppearance(pendingAppearanceSettings);
    });
    fontBox.appendChild(button);
  });
  applyAppearance();
}

function setBusy(nextBusy) {
  busy = nextBusy;
  document.body.classList.toggle("busy", busy);
}

function loadRememberedLogin() {
  const rememberedId = storeGet(rememberedLoginIdKey);
  const rememberedPw = storeGet(rememberedLoginPwKey);
  $("rememberLogin").checked = storeGet(rememberLoginKey) === "1" && (!!rememberedId || !!rememberedPw);
  $("loginId").value = rememberedId || "";
  $("loginPw").value = rememberedPw || "";
}

async function restoreSavedLoginIfNeeded() {
  loadRememberedLogin();
  if (!isUnlocked() || $("loginId").value) return;
  try {
    const data = await api("/api/saved-login");
    if (!data.saved || !data.id) return;
  } catch (_err) {
    // Saved-login restore is best-effort. Manual login remains available.
  }
}

function saveRememberedLogin(id, password) {
  if (!$("rememberLogin").checked || !id || !password) {
    clearRememberedLogin();
    return;
  }
  storeSet(rememberLoginKey, "1");
  storeSet(rememberedLoginIdKey, id);
  storeSet(rememberedLoginPwKey, password);
}

function clearRememberedLogin() {
  storeRemove(rememberLoginKey);
  storeRemove(rememberedLoginIdKey);
  storeRemove(rememberedLoginPwKey);
}

function saveFruitSession(sessionToken) {
  fruitSession = sessionToken || "";
  if (fruitSession) {
    authValidated = true;
    storeRemove(loggedOutKey);
    try {
      if (window.FruitAndroid?.saveSession) window.FruitAndroid.saveSession("");
    } catch (_err) {
      // Native session clearing is best-effort. Login sessions are not persisted.
    }
  }
}

async function recoverSession() {
  if (storeGet(loggedOutKey) === "1") return "";
  if (!recoveringSession) {
    recoveringSession = (async () => {
      const res = await resilientFetch("/api/session", {
        headers: {
          "Content-Type": "application/json",
          "X-Fruit-Token": token,
          "X-Fruit-Session": fruitSession,
          "X-Fruit-Owner": expectedOwnerKey(),
          "X-Fruit-Device": deviceId(),
        },
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "세션 복구 실패");
      saveFruitSession((data.result || {}).sessionToken || "");
      return fruitSession;
    })().finally(() => {
      recoveringSession = null;
    });
  }
  return recoveringSession;
}

function isAuthError(data, response) {
  const error = String(data?.error || "");
  return response?.status === 401 || error.includes("로그인") || error.includes("세션") || error.includes("기기 CID");
}

function clearAuthenticatedUi() {
  clearSessionStorage();
  sessionStorage.removeItem(sessionKey);
  toast("");
  $("results").innerHTML = "";
  $("worklogResults").innerHTML = "";
  $("searchInput").value = "";
  $("worklogSearchInput").value = "";
  closeHistoryModal();
  closeSettingsModal();
  closeProfileModal();
  renderState({});
}

async function api(path, payload, retrying = false) {
  const options = {
    headers: {
      "Content-Type": "application/json",
      "X-Fruit-Token": token,
      "X-Fruit-Session": fruitSession,
      "X-Fruit-Owner": expectedOwnerKey(),
      "X-Fruit-Device": deviceId(),
    },
  };
  if (payload !== undefined) {
    options.method = "POST";
    options.body = JSON.stringify(payload);
  }
  const res = await resilientFetch(path, options);
  const data = await res.json();
  if (
    !data.ok &&
    !retrying &&
    path !== "/api/login" &&
    path !== "/api/session" &&
    isAuthError(data, res)
  ) {
    try {
      await recoverSession();
      if (fruitSession) return api(path, payload, true);
    } catch (_err) {
      clearAuthenticatedUi();
      throw new Error("로그인이 만료되었습니다. 다시 로그인하세요.");
    }
  }
  if (!data.ok && path !== "/api/login" && isAuthError(data, res)) {
    clearAuthenticatedUi();
  }
  if (!data.ok) throw new Error(data.error || "요청 실패");
  if (path !== "/api/login" && path !== "/api/app-info") {
    authValidated = true;
  }
  return data.result || data.state || data;
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replaceAll("-", "+").replaceAll("_", "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

function supportsWebPush() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function supportsNativePush() {
  return !!window.FruitAndroid;
}

function isIosLike() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isStandaloneWebApp() {
  return window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
}

function webPushUnsupportedMessage() {
  if (isIosLike() && !isStandaloneWebApp()) {
    return "iPhone Push는 Safari에서 홈 화면에 추가한 앱으로 열어야 사용할 수 있습니다.";
  }
  return "이 기기는 웹 Push 알림을 지원하지 않습니다.";
}

function shouldShowPushEnabled(state = currentState) {
  if (!isUnlocked() || state.pushEnabled === false) return false;
  if (supportsNativePush()) return true;
  if (!supportsWebPush()) return false;
  return Notification.permission === "granted";
}

async function ensureWebPushSubscription() {
  if (!supportsWebPush()) {
    throw new Error(webPushUnsupportedMessage());
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("기기 알림 권한이 허용되지 않았습니다.");
  }
  const registration = await navigator.serviceWorker.register("/sw.js");
  const keyData = await api("/api/push/public-key");
  let subscription = await registration.pushManager.getSubscription();
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(keyData.publicKey),
    });
  }
  const payload = subscription.toJSON();
  payload.deviceId = deviceId();
  payload.userAgent = navigator.userAgent || "";
  await api("/api/push/subscribe", { subscription: payload });
  return subscription;
}

async function showDeviceNotification(item) {
  if (!item || !item.id) return false;
  const title = item.title || "fingerfruit";
  const body = item.body || "새 열매 수신 내역이 있습니다.";
  try {
    if (window.FruitAndroid?.showNotification) {
      window.FruitAndroid.showNotification(title, body);
      return true;
    }
  } catch (_err) {
    // Android native notification bridge is best-effort.
  }
  if (!("Notification" in window) || Notification.permission !== "granted") return false;
  try {
    const registration = "serviceWorker" in navigator ? await navigator.serviceWorker.getRegistration("/sw.js") : null;
    if (registration?.showNotification) {
      await registration.showNotification(title, {
        body,
        tag: item.tag || item.id,
        icon: "/icons/apple-icon-192.png",
        badge: "/icons/apple-icon-192.png",
        data: { url: item.url || "/" },
      });
      return true;
    }
    new Notification(title, { body, tag: item.tag || item.id });
    return true;
  } catch (_err) {
    return false;
  }
}

async function syncPushSubscriptionIfPossible(state = currentState) {
  if (!isUnlocked() || state.pushEnabled === false || pushSyncing) return;
  if (supportsNativePush()) return;
  if (!supportsWebPush() || Notification.permission !== "granted") return;
  pushSyncing = true;
  try {
    await ensureWebPushSubscription();
  } catch (_err) {
    // The toggle path reports subscription errors. Background sync stays quiet.
  } finally {
    pushSyncing = false;
  }
}

async function checkReceivedNotifications({ silent = true } = {}) {
  if (!isUnlocked() || currentState.pushEnabled === false) return;
  try {
    const data = await api("/api/notifications");
    const latest = (data.items || [])[0];
    if (!latest?.id) return;
    const lastShownId = storeGet(lastReceivedNotificationKey) || "";
    if (!lastShownId) {
      storeSet(lastReceivedNotificationKey, latest.id);
      return;
    }
    if (latest.id === lastShownId) return;
    storeSet(lastReceivedNotificationKey, latest.id);
    const sentAt = latest.at ? new Date(latest.at).getTime() : 0;
    if (!sentAt || Date.now() - sentAt > recentNotificationWindowMs) return;
    const shown = await showDeviceNotification(latest);
    if (!shown && !silent) toast("열매 수신 내역이 있습니다. 알림 권한을 확인하세요.");
  } catch (err) {
    if (!silent) toast(`수신 알림 확인 실패: ${err.message}`);
  }
}

async function disableWebPushSubscription() {
  if (!supportsWebPush()) return;
  const registration = await navigator.serviceWorker.getRegistration("/sw.js");
  const subscription = registration ? await registration.pushManager.getSubscription() : null;
  if (subscription) {
    await api("/api/push/unsubscribe", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }
}

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function fmtDay(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return `${date.getDate()}일`;
}

function fmtHistoryDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

function localDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseLocalDateValue(value) {
  const [year, month, day] = String(value || "").split("-").map((part) => Number(part));
  const date = new Date(year, (month || 1) - 1, day || 1);
  if (
    Number.isNaN(date.getTime()) ||
    date.getFullYear() !== year ||
    date.getMonth() !== (month || 1) - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

function worklogBlockedDateReason(value) {
  const date = parseLocalDateValue(value);
  if (!date) return "날짜 오류";
  const scheduleTime = $("worklogTimeInput")?.value || currentState.worklogScheduleTime || "09:05";
  const [hour, minute] = String(scheduleTime).split(":").map((part) => Number(part));
  const scheduled = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    Number.isFinite(hour) ? hour : 9,
    Number.isFinite(minute) ? minute : 5,
    0,
    0
  );
  if (scheduled <= new Date()) return "지난 예약";
  const completedDate = String(currentState.worklogLastRunKey || "").split("T", 1)[0];
  if (completedDate && completedDate === value) return "이미 전송 완료";
  const day = date.getDay();
  if (day === 0) return "주말";
  if (day === 6) return "주말";
  return koreanPublicHolidays[value] || "";
}

function isWorklogAllowedDate(value) {
  return !worklogBlockedDateReason(value);
}

function fmtHistorySelectedDate(value) {
  if (!value) return "날짜 선택";
  const [year, month, day] = String(value).split("-").map((part) => Number(part));
  const date = new Date(year, (month || 1) - 1, day || 1);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

function syncHistoryDateControls() {
  $("historyDateInput").value = selectedHistoryDate;
  $("historySelectedDate").textContent = fmtHistorySelectedDate(selectedHistoryDate);
}

function fmtTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function fmtHistoryTime(item) {
  const label = item.timeLabel || (item.action === "received" ? "받음" : "보냄");
  if (!item.at) return "데이터없음";
  const time = fmtTime(item.at);
  return `${label} ${time}`;
}

function historyTimeMarkup(item) {
  const label = item.timeLabel || (item.action === "received" ? "받음" : "보냄");
  if (!item.at) return escapeHtml("데이터없음");
  return `<span class="history-time-label">${escapeHtml(label)}</span><span class="history-time-clock">${escapeHtml(fmtTime(item.at))}</span>`;
}

function fmtNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ko-KR") : String(value);
}

function fmtDelta(value) {
  if (value === null || value === undefined) return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number > 0 ? `+${number}` : String(number);
}

function avatarStyle(url) {
  return url ? ` style="--history-photo:url('${String(url).replaceAll("'", "%27")}')"` : "";
}

function setLockedState(unlocked) {
  $("workspace").classList.toggle("locked", !unlocked);
  document.body.classList.toggle("authenticated", unlocked);
  $("loginBadge").textContent = unlocked ? "현재 사용자" : "필요";
  $("loginBadge").className = `badge ${unlocked ? "ok" : "warn"}`;
  $("logoutBtn").classList.toggle("hidden", !unlocked);
  $("loginProfile").classList.toggle("hidden", !unlocked);
  $("loginForm").classList.toggle("hidden", unlocked);
  $("savedLogin").classList.add("hidden");
  const controls = [
    "searchInput",
    "searchBtn",
    "giftMessage",
    "sendBerryCount",
    "sendAllBerries",
    "messageBtn",
    "autoToggle",
    "pushToggle",
    "runBtn",
    "historyOpenBtn",
    "refreshBalanceBtn",
    "intervalAddBtn",
    "intervalResetBtn",
    "worklogSearchInput",
    "worklogSearchBtn",
    "worklogSeedCount",
    "worklogSeedMessage",
    "worklogProjectSelect",
    "worklogContent",
    "worklogCalendarBtn",
    "worklogDateInput",
    "worklogTimeInput",
    "worklogEnabled",
    "worklogSaveBtn",
    "worklogRunBtn",
  ];
  controls.forEach((id) => {
    $(id).disabled = !unlocked;
  });
  $("autoToggle").disabled = !unlocked || !(currentState.targetEmployeeId && currentState.targetEmployeeName);
  $("pushToggle").disabled = !unlocked;
  $("runBtn").disabled = !unlocked || !(currentState.targetEmployeeId && currentState.targetEmployeeName);
  $("pushControl").classList.toggle("hidden", !unlocked);
}

function employeeLabel(name, employeeNo) {
  const safeName = String(name || "").trim();
  const safeNo = String(employeeNo || "").trim();
  if (safeName && safeNo) return `${safeName} ${safeNo}`;
  return safeName || safeNo || "로그인 필요";
}

function employeeDetail(deptName, positionName) {
  return [deptName, positionName]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join(" · ");
}

function personNameLabel(name, fallback) {
  const safeName = String(name || "").trim();
  const safeFallback = String(fallback || "").trim();
  return safeName || safeFallback || "로그인 필요";
}

function personWithPosition(name, position, fallback) {
  const safeName = personNameLabel(name, fallback);
  const safePosition = String(position || "").trim();
  return safePosition && safeName !== "로그인 필요" ? `${safeName} ${safePosition}` : safeName;
}

function mergeStatePhotos(nextState) {
  const merged = { ...(nextState || {}) };
  const previous = currentState || {};
  const cached = cachedStateValue();
  const senderId = merged.senderEmployeeId || merged.loginUserId;
  const targetId = merged.targetEmployeeId;
  const sameSender =
    String(previous.senderEmployeeId || previous.loginUserId || "") ===
    String(senderId || "");
  const sameTarget =
    String(previous.targetEmployeeId || "") === String(targetId || "");
  if (!merged.senderProfilePhotoUrl && sameSender) {
    merged.senderProfilePhotoUrl = previous.senderProfilePhotoUrl || previous.profilePhotoUrl || "";
  }
  if (!merged.targetProfilePhotoUrl && sameTarget) {
    merged.targetProfilePhotoUrl = previous.targetProfilePhotoUrl || "";
  }
  if (!merged.senderProfilePhotoUrl) {
    merged.senderProfilePhotoUrl = merged.profilePhotoUrl || getCachedProfilePhoto(senderId) || getProfilePhoto();
  }
  if (!merged.targetProfilePhotoUrl) {
    merged.targetProfilePhotoUrl = getCachedProfilePhoto(targetId);
  }
  rememberProfilePhoto(senderId, merged.senderProfilePhotoUrl);
  rememberProfilePhoto(targetId, merged.targetProfilePhotoUrl);
  if (merged.credentialsSaved !== false) {
    preserveStateValue(merged, previous, cached, "lastSeedCount");
    preserveStateValue(merged, previous, cached, "lastBerryCount");
    preserveStateValue(merged, previous, cached, "balanceCheckedAt");
    preserveStateValue(merged, previous, cached, "lastCheckedAt");
  }
  return merged;
}

function cachedStateValue() {
  try {
    const cached = JSON.parse(storeGet(cachedStateKey) || "null");
    return cached && cached.sessionToken === fruitSession && cached.state ? cached.state : {};
  } catch (_err) {
    return {};
  }
}

function preserveStateValue(merged, previous, cached, key) {
  if (merged[key] !== null && merged[key] !== undefined) return;
  if (previous[key] !== null && previous[key] !== undefined) {
    merged[key] = previous[key];
    return;
  }
  if (cached[key] !== null && cached[key] !== undefined) {
    merged[key] = cached[key];
  }
}

function renderWorklogDates() {
  const allowedDates = selectedWorklogDates.filter(isWorklogAllowedDate);
  if (allowedDates.length !== selectedWorklogDates.length) {
    selectedWorklogDates = allowedDates;
  }
  const box = $("worklogDateChips");
  box.innerHTML = "";
  const opener = $("worklogDateInput");
  opener.textContent = selectedWorklogDates.length
    ? `${selectedWorklogDates.length}개 날짜 선택됨`
    : "날짜 선택";
  if (!selectedWorklogDates.length) {
    box.innerHTML = '<span class="empty">선택 날짜 없음</span>';
    return;
  }
  selectedWorklogDates.forEach((date) => {
    const chip = document.createElement("span");
    chip.className = "date-chip";
    chip.innerHTML = `${escapeHtml(date)} <button type="button" aria-label="${escapeHtml(date)} 삭제">×</button>`;
    chip.querySelector("button").addEventListener("click", () => {
      selectedWorklogDates = selectedWorklogDates.filter((item) => item !== date);
      markWorklogDraftDirty();
      renderWorklogDates();
    });
    box.appendChild(chip);
  });
}

function markWorklogDraftDirty() {
  worklogDraftDirty = true;
}

function hasWorklogDraft() {
  return worklogDraftDirty && isUnlocked();
}

function renderWorklogCalendar() {
  const grid = $("worklogCalendarGrid");
  const monthLabel = $("worklogCalendarMonth");
  const year = worklogCalendarMonth.getFullYear();
  const month = worklogCalendarMonth.getMonth();
  const todayValue = localDateValue(new Date());
  const firstWeekday = new Date(year, month, 1).getDay();
  const firstVisibleOffset = (firstWeekday + 6) % 7;
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  monthLabel.textContent = `${year}년 ${month + 1}월`;
  grid.innerHTML = "";
  for (let i = 0; i < firstVisibleOffset; i += 1) {
    const blank = document.createElement("span");
    blank.className = "calendar-day blank";
    grid.appendChild(blank);
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = localDateValue(new Date(year, month, day));
    const parsedDate = parseLocalDateValue(date);
    const isWeekend = parsedDate ? parsedDate.getDay() === 0 || parsedDate.getDay() === 6 : false;
    const holidayName = koreanPublicHolidays[date] || "";
    const blockedReason = worklogBlockedDateReason(date);
    const button = document.createElement("button");
    button.type = "button";
    button.className = [
      "calendar-day",
      calendarDraftDates.includes(date) ? "selected" : "",
      date === todayValue ? "today" : "",
      blockedReason ? "blocked" : "",
      isWeekend ? "weekend" : "",
      holidayName ? "holiday" : "",
    ].filter(Boolean).join(" ");
    const label = holidayName || (isWeekend ? "휴무" : "");
    button.innerHTML = `
      <span class="calendar-day-number">${day}</span>
      ${label ? `<small>${escapeHtml(label)}</small>` : ""}
    `;
    button.setAttribute("aria-pressed", calendarDraftDates.includes(date) ? "true" : "false");
    if (blockedReason) {
      button.disabled = true;
      button.title = blockedReason;
      button.setAttribute("aria-label", `${date} ${blockedReason} 업무일지 작성 불가`);
    }
    button.addEventListener("click", () => {
      if (blockedReason) {
        toast(`${date}은(는) ${blockedReason}이라 업무일지를 예약할 수 없습니다.`);
        return;
      }
      calendarDraftDates = calendarDraftDates.includes(date)
        ? calendarDraftDates.filter((item) => item !== date)
        : [...calendarDraftDates, date].sort();
      renderWorklogCalendar();
    });
    grid.appendChild(button);
  }
}

function openWorklogCalendar() {
  calendarDraftDates = selectedWorklogDates.filter(isWorklogAllowedDate);
  selectedWorklogDates = calendarDraftDates;
  renderWorklogDates();
  const anchor = calendarDraftDates[0] || localDateValue(new Date());
  const [year, month] = anchor.split("-").map(Number);
  worklogCalendarMonth = new Date(year || new Date().getFullYear(), (month || new Date().getMonth() + 1) - 1, 1);
  renderWorklogCalendar();
  $("worklogCalendarModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeWorklogCalendar() {
  $("worklogCalendarModal").classList.add("hidden");
  syncModalOpenState();
}

function setWorklogProjects(projects, selectedId = "") {
  worklogProjects = projects || worklogProjects || [];
  const select = $("worklogProjectSelect");
  const current = selectedId || select.value || "";
  select.innerHTML = '<option value="">프로젝트 선택</option>';
  worklogProjects.forEach((project) => {
    const option = document.createElement("option");
    option.value = project.id;
    option.textContent = project.name;
    select.appendChild(option);
  });
  select.value = current;
}

async function loadWorklogProjects() {
  if (!isUnlocked()) return;
  try {
    const data = await api("/api/worklog-projects");
    const selectedId = hasWorklogDraft() ? $("worklogProjectSelect").value : currentState.worklogProjectId || "";
    setWorklogProjects(data.projects || [], selectedId);
  } catch (err) {
    toast(`프로젝트 조회 실패: ${err.message}`);
  }
}

function renderWorklogState(state) {
  const unlocked = isUnlocked();
  const worklogTarget = pendingWorklogTarget || {
    emp_id: state.worklogTargetEmployeeId,
    emp_nm: state.worklogTargetEmployeeName,
    dept_nm: state.worklogTargetDeptName,
    pos_nm: state.worklogTargetPositionName,
    duty_id: state.worklogTargetDutyId,
  };
  if (!hasWorklogDraft()) {
    selectedWorklogDays = [];
    selectedWorklogDates = Array.isArray(state.worklogScheduleDates) ? [...state.worklogScheduleDates] : [];
    $("worklogSeedCount").value = state.worklogSeedCount ?? 0;
    $("worklogSeedMessage").value = state.worklogSeedMessage || "";
    $("worklogContent").value = state.worklogContent || "";
    $("worklogTimeInput").value = state.worklogScheduleTime || "09:05";
    $("worklogEnabled").checked = !!state.worklogEnabled;
  }
  if (worklogTarget.emp_id) {
    const detail = employeeDetail(worklogTarget.dept_nm, worklogTarget.pos_nm);
    $("worklogTarget").innerHTML = `
      <strong>${escapeHtml(employeeLabel(worklogTarget.emp_nm, worklogTarget.emp_id))}</strong>
      ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
    `;
  } else {
    $("worklogTarget").textContent = "선택된 직원 없음";
  }
  setWorklogProjects(worklogProjects, state.worklogProjectId || "");
  const badgeOk = unlocked && state.worklogEnabled;
  $("worklogBadge").textContent = badgeOk ? `예약됨 ${fmtDate(state.worklogNextRunAt)}` : "대기";
  $("worklogBadge").className = `badge ${badgeOk ? "ok" : "neutral"}`;
  renderWorklogDates();
}

function renderState(state) {
  state = mergeStatePhotos(state);
  if (isUnlocked() && expectedOwnerKey() && state.ownerKey && expectedOwnerKey() !== state.ownerKey) {
    clearAuthenticatedUi();
    toast("기기 로그인 정보와 서버 계정이 달라서 세션을 초기화했습니다. 다시 로그인하세요.");
    return;
  }
  currentState = state;
  const unlocked = isUnlocked();
  if (unlocked && currentState.credentialsSaved !== false) {
    try {
      storeSet(cachedStateKey, JSON.stringify({
        sessionToken: fruitSession,
        savedAt: Date.now(),
        state: currentState,
      }));
    } catch (_err) {
      // UI cache is best-effort.
    }
  } else {
    storeRemove(cachedStateKey);
  }
  const enabled = unlocked && !!state.enabled;
  const hasTarget = unlocked && (state.hasTarget === true || !!state.targetEmployeeId);
  const senderLabel = unlocked
    ? personNameLabel(state.loginUser || state.senderEmployeeName, state.senderEmployeeId)
    : "로그인 필요";
  const senderPhoto = unlocked ? storedSenderProfilePhoto(state) || "" : "";
  const targetLabel = hasTarget ? employeeLabel(state.targetEmployeeName, state.targetEmployeeId) : "검색 후 선택";
  const targetPhoto = hasTarget ? state.targetProfilePhotoUrl || "" : "";

  setLockedState(unlocked);
  $("loginUserDisplay").textContent = senderLabel;
  updateProfileUi(senderLabel, unlocked, senderPhoto);
  applyAvatar($("loginUserAvatar"), $("loginUserInitial"), senderLabel, senderPhoto);
  applyAvatar($("targetAvatar"), $("targetInitial"), hasTarget ? targetLabel : "", targetPhoto);
  $("autoState").textContent = unlocked ? (enabled ? "켜짐" : "꺼짐") : "잠김";
  $("targetName").textContent = targetLabel;
  $("seedCount").textContent =
    unlocked && state.lastSeedCount !== null && state.lastSeedCount !== undefined
      ? `${state.lastSeedCount}개`
      : "-";
  $("berryCount").textContent =
    unlocked && state.lastBerryCount !== null && state.lastBerryCount !== undefined
      ? `${state.lastBerryCount}개`
      : "-";
  $("intervalDisplay").textContent = `${intervalMinutes(state)}분`;
  $("balanceStatus").textContent = unlocked
    ? state.balanceError
      ? "조회 오류"
      : `최근 조회 ${fmtDate(state.balanceCheckedAt || state.lastCheckedAt)}`
    : "로그인 필요";
  $("targetBadge").textContent = hasTarget ? "선택됨" : "미선택";
  $("targetBadge").className = `badge ${hasTarget ? "ok" : "neutral"}`;
  $("autoToggle").checked = enabled;
  $("pushToggle").checked = shouldShowPushEnabled(state);
  $("giftMessage").value = state.giftMessage || "자동 전달";
  const sendAllBerries = state.sendAllBerries === true;
  const sendCount = Math.max(1, Number(state.sendBerryCount || 1));
  $("sendBerryCount").value = sendCount;
  $("sendBerryCount").disabled = !unlocked || sendAllBerries;
  $("sendAllBerries").checked = sendAllBerries;
  $("sendAllBerries").disabled = !unlocked;
  const sendModeText = sendAllBerries ? "보유 열매 전부" : `${sendCount}개`;
  const daemonText = state.daemonRunning ? "데몬 실행 중" : "데몬 확인 필요";
  $("controlHint").textContent = enabled
    ? `켜짐 상태입니다. ${daemonText}. 다음 확인 ${fmtDate(state.nextRunAt)}. 전송 수 ${sendModeText}`
    : hasTarget
      ? `켜면 ${intervalMinutes(state)}분마다 한 번씩 보유 열매를 확인하고 ${sendModeText} 보냅니다.`
      : "대상 직원을 먼저 검색해서 선택하세요.";
  renderWorklogState(state);
  try {
    if (unlocked && state.credentialsSaved !== false && window.FruitAndroid?.saveSettings) {
      window.FruitAndroid.saveSettings(enabled, state.pushEnabled !== false, intervalMinutes(state));
    }
  } catch (_err) {
    // Native setting mirroring is best-effort.
  }
  syncPushSubscriptionIfPossible(state);
  if (unlocked) window.setTimeout(showReleaseNotesIfNeeded, 0);
}

function renderCachedState() {
  if (!isUnlocked()) return;
  try {
    const cached = JSON.parse(storeGet(cachedStateKey) || "null");
    if (!cached || typeof cached !== "object") return;
    if (cached.sessionToken !== fruitSession) {
      storeRemove(cachedStateKey);
      return;
    }
    // Do not paint stale authenticated screens on startup. A real API status
    // response must validate the session before user/target controls appear.
  } catch (_err) {
    storeRemove(cachedStateKey);
  }
}

function historyPairKey(item) {
  return `${item.targetEmployeeId || item.avatarEmployeeId || item.target || item.displayName || ""}|${Number(item.berries || Math.abs(Number(item.delta) || 0)) || 0}`;
}

function filterPairedHistoryItems(items) {
  const sorted = Array.isArray(items) ? items : [];
  const usedSentIndexes = new Set();
  const keepReceivedIndexes = new Set();
  sorted.forEach((item, index) => {
    if (item.historyKind === "seed") return;
    if (item.action !== "received") return;
    const receivedAt = Date.parse(item.at || "");
    if (!Number.isFinite(receivedAt)) return;
    const key = historyPairKey(item);
    let bestIndex = -1;
    let bestDelta = Infinity;
    sorted.forEach((candidate, candidateIndex) => {
      if (candidate.action !== "sent" || usedSentIndexes.has(candidateIndex)) return;
      if (historyPairKey(candidate) !== key) return;
      const sentAt = Date.parse(candidate.at || "");
      if (!Number.isFinite(sentAt)) return;
      const delta = sentAt - receivedAt;
      if (delta < 0 || delta > 12 * 60 * 1000) return;
      if (delta < bestDelta) {
        bestDelta = delta;
        bestIndex = candidateIndex;
      }
    });
    if (bestIndex >= 0) {
      usedSentIndexes.add(bestIndex);
      keepReceivedIndexes.add(index);
    }
  });
  return sorted.filter((item, index) => item.historyKind === "seed" || item.action !== "received" || keepReceivedIndexes.has(index));
}

function renderHistory(items) {
  const body = $("historyBody");
  items = filterPairedHistoryItems(items);
  body.innerHTML = "";
  if (!items.length) {
    body.innerHTML = `<div class="history-empty">${escapeHtml(fmtHistorySelectedDate(selectedHistoryDate))} 내역이 없습니다.</div>`;
    return;
  }
  let lastDate = "";
  items.forEach((item) => {
    const itemDate = fmtHistoryDate(item.at);
    if (!selectedHistoryDate && itemDate !== lastDate) {
      const dateHeader = document.createElement("div");
      dateHeader.className = "history-date";
      dateHeader.textContent = itemDate;
      body.appendChild(dateHeader);
      lastDate = itemDate;
    }
    const row = document.createElement("div");
    row.className = `history-row ${item.action === "received" ? "received" : "sent"}`;
    const berryText = item.remaining !== null && item.remaining !== undefined
      ? `${fmtNumber(item.seeds)}/${fmtNumber(item.remaining)}`
      : item.berries !== null && item.berries !== undefined
        ? `${fmtNumber(item.seeds)}/${fmtNumber(item.berries)}`
        : "-";
    const senderName = item.displayName || personWithPosition(
      item.target || item.senderName,
      item.targetPositionName || item.senderPositionName,
      "-"
    );
    const counterpartPhoto = item.avatarProfilePhotoUrl
      || item.senderProfilePhotoUrl
      || getCachedProfilePhoto(item.avatarEmployeeId || item.senderEmployeeId || item.targetEmployeeId);
    const senderPhoto = counterpartPhoto || "";
    const avatarClass = senderPhoto ? "history-avatar has-photo" : "history-avatar";
    row.innerHTML = `
      <time>${historyTimeMarkup(item)}</time>
      <div class="history-main">
        <strong>${escapeHtml(item.content || "-")}</strong>
        <span>${escapeHtml(senderName)} · ${escapeHtml(item.action === "received" ? "받음" : "보냄")}</span>
        <small>씨앗/열매 ${escapeHtml(berryText)}</small>
      </div>
      <span class="${Number(item.delta) < 0 ? "history-delta minus" : Number(item.delta) > 0 ? "history-delta plus" : "history-delta"}">${escapeHtml(fmtDelta(item.delta))}</span>
      <span class="${avatarClass}"${avatarStyle(senderPhoto)}>${senderPhoto ? "" : escapeHtml(getInitial(senderName))}</span>
    `;
    body.appendChild(row);
  });
}

async function refreshHistory({ silent = false } = {}) {
  const body = $("historyBody");
  try {
    syncHistoryDateControls();
    body.innerHTML = '<div class="history-empty">선택한 날짜 내역을 불러오는 중입니다...</div>';
    const query = new URLSearchParams({
      date: selectedHistoryDate,
      tz: String(new Date().getTimezoneOffset()),
    });
    const data = await api(`/api/history?${query.toString()}`);
    renderHistory(data.items || []);
  } catch (err) {
    body.innerHTML = `<div class="history-empty">내역 조회 실패: ${escapeHtml(err.message)}</div>`;
    if (!silent) toast(`내역 조회 실패: ${err.message}`);
  }
}

async function refresh({ silent = false, forceBalance = false } = {}) {
  try {
    const state = forceBalance && isUnlocked()
      ? await api("/api/refresh", {})
      : await api("/api/status");
    renderState(state);
    await loadWorklogProjects();
  } catch (err) {
    if (String(err.message || "").includes("로그인") || String(err.message || "").includes("세션")) {
      clearAuthenticatedUi();
      return;
    }
    if (!silent) toast(`상태 조회 실패: ${err.message}`);
  }
}

async function refreshBalance() {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    toast("FOREST API를 다시 조회 중입니다...");
    const state = await api("/api/refresh", {});
    renderState(state);
    toast(`조회 완료: 씨앗 ${fmtNumber(state.lastSeedCount)}개 / 열매 ${fmtNumber(state.lastBerryCount)}개`);
    if (!$("historyModal").classList.contains("hidden")) {
      await refreshHistory({ silent: true });
    }
  } catch (err) {
    toast(`새로고침 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
}

async function setIntervalMinutes(minutes) {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    const state = await api("/api/interval", { minutes });
    renderState(state);
    toast(`전송 시간을 ${intervalMinutes(state)}분으로 설정했습니다.`);
  } catch (err) {
    toast(`전송 시간 변경 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderResults(results) {
  const box = $("results");
  box.innerHTML = "";
  if (!results.length) {
    box.innerHTML = '<div class="empty">검색 결과가 없습니다.</div>';
    return;
  }
  results.forEach((person) => {
    const item = document.createElement("div");
    item.className = "person";
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(employeeLabel(person.emp_nm, person.emp_id))}</strong>
        <small>${escapeHtml(person.dept_nm || "-")} · ${escapeHtml(person.pos_nm || "-")}</small>
      </div>
      <div class="person-actions">
        <button type="button" data-action="select">선택</button>
        <button type="button" data-action="select-on">선택하고 켜기</button>
      </div>
    `;
    item.querySelector('[data-action="select"]').addEventListener("click", async () => {
      try {
        setBusy(true);
        const state = await api("/api/target", person);
        renderState(state);
        $("results").innerHTML = "";
        $("searchInput").value = "";
        toast(`${person.emp_nm} 직원으로 설정했습니다.`);
      } catch (err) {
        toast(`대상 설정 실패: ${err.message}`);
      } finally {
        setBusy(false);
      }
    });
    item.querySelector('[data-action="select-on"]').addEventListener("click", async () => {
      try {
        setBusy(true);
        await api("/api/target", person);
        const state = await api("/api/on", {});
        renderState(state);
        $("results").innerHTML = "";
        $("searchInput").value = "";
        toast(`${person.emp_nm} 직원으로 설정하고 자동전송을 켰습니다.`);
      } catch (err) {
        toast(`자동전송 시작 실패: ${err.message}`);
      } finally {
        setBusy(false);
      }
    });
    box.appendChild(item);
  });
}

function renderWorklogResults(results) {
  const box = $("worklogResults");
  box.innerHTML = "";
  if (!results.length) {
    box.innerHTML = '<div class="empty">검색 결과가 없습니다.</div>';
    return;
  }
  results.forEach((person) => {
    const item = document.createElement("div");
    item.className = "person";
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(employeeLabel(person.emp_nm, person.emp_id))}</strong>
        <small>${escapeHtml(person.dept_nm || "-")} · ${escapeHtml(person.pos_nm || "-")}</small>
      </div>
      <div class="person-actions">
        <button type="button" data-action="select">선택</button>
      </div>
    `;
    const selectWorklogPerson = async () => {
      try {
        setBusy(true);
        pendingWorklogTarget = {
          emp_id: person.emp_id,
          emp_nm: person.emp_nm,
          dept_nm: person.dept_nm,
          pos_nm: person.pos_nm,
          duty_id: person.duty_id,
        };
        renderWorklogState(currentState);
        $("worklogResults").innerHTML = "";
        $("worklogSearchInput").value = "";
        const state = await api("/api/worklog-target", person);
        pendingWorklogTarget = null;
        renderState(state);
        toast(`${person.emp_nm} 직원으로 설정했습니다.`);
      } catch (err) {
        toast(`업무일지 직원 설정 실패: ${err.message}`);
      } finally {
        setBusy(false);
      }
    };
    item.querySelector('[data-action="select"]').addEventListener("click", selectWorklogPerson);
    item.addEventListener("dblclick", selectWorklogPerson);
    box.appendChild(item);
  });
}

$("loginBtn").addEventListener("click", async () => {
  const id = $("loginId").value.trim();
  const password = $("loginPw").value;
  if (!id || !password) {
    toast("아이디와 비밀번호를 입력하세요.");
    return;
  }
  try {
    setBusy(true);
    const result = await api("/api/login", { id, password });
    saveRememberedLogin(id, password);
    currentOwnerKey = result.ownerKey || "";
    saveFruitSession(result.sessionToken || "");
    sessionStorage.setItem(sessionKey, "1");
    if (!$("rememberLogin").checked) $("loginPw").value = "";
    toast(`${result.user || "사용자"} 로그인 완료`);
    await loadProfileSettings({ silent: true });
    await refresh({ silent: true });
  } catch (err) {
    sessionStorage.removeItem(sessionKey);
    renderState(currentState);
    toast(`로그인 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("resumeBtn").addEventListener("click", async () => {
  sessionStorage.setItem(sessionKey, "1");
  storeRemove(loggedOutKey);
  renderState(currentState);
  await loadProfileSettings({ silent: true });
  toast("앱을 열었습니다.");
});

$("logoutBtn").addEventListener("click", async () => {
  try {
    setBusy(true);
    const state = await api("/api/logout", {});
    clearSessionStorage();
    sessionStorage.removeItem(sessionKey);
    renderState(state);
    $("results").innerHTML = "";
    $("searchInput").value = "";
    loadRememberedLogin();
    closeHistoryModal();
    toast("로그아웃했습니다. 이 계정의 모든 기기 세션을 종료했습니다.");
  } catch (err) {
    if (String(err.message || "").includes("로그인") || String(err.message || "").includes("세션")) {
      clearAuthenticatedUi();
      toast("이미 로그아웃된 세션입니다.");
    } else {
      toast(`로그아웃 실패: ${err.message}`);
    }
  } finally {
    setBusy(false);
  }
});

function openHistoryModal() {
  if (!selectedHistoryDate) selectedHistoryDate = localDateValue(new Date());
  syncHistoryDateControls();
  $("historyModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
  refreshHistory();
}

async function openSettingsModal() {
  $("settingsModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
  await loadProfileSettings({ silent: true });
  pendingAppearanceSettings = appearanceSettings();
  updateAppearanceSelection(pendingAppearanceSettings);
  scrollSelectedAppearanceIntoView();
}

async function openProfileModal() {
  const senderLabel = isUnlocked()
    ? personNameLabel(currentState.loginUser || currentState.senderEmployeeName, currentSenderEmployeeId())
    : $("heroTitleText").textContent;
  const openedPhoto = currentSenderPhoto();
  updateProfileUi(senderLabel, isUnlocked(), openedPhoto);
  $("profileModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
  if (!isUnlocked()) return;
  try {
    const latestState = await api("/api/status");
    renderState(latestState);
    if (!$("profileModal").classList.contains("hidden")) {
      const latestLabel = personNameLabel(currentState.loginUser || currentState.senderEmployeeName, currentSenderEmployeeId());
      updateProfileUi(latestLabel, true, currentSenderPhoto() || openedPhoto);
    }
  } catch (_err) {
    if (!$("profileModal").classList.contains("hidden")) {
      updateProfileUi(senderLabel, true, currentSenderPhoto() || openedPhoto);
    }
  }
}

function closeSettingsModal() {
  $("settingsModal").classList.add("hidden");
  pendingAppearanceSettings = null;
  applyAppearance();
  syncModalOpenState();
}

function closeProfileModal() {
  $("profileModal").classList.add("hidden");
  if (isUnlocked()) {
    renderState(currentState);
  } else {
    updateProfileUi("fingerfruit", false, "");
  }
  syncModalOpenState();
}

function closeHistoryModal() {
  $("historyModal").classList.add("hidden");
  syncModalOpenState();
}

function releaseNotesSnoozed(info = latestAppInfo) {
  if (!info?.latestVersion) return true;
  try {
    const snooze = JSON.parse(storeGet(releaseNotesSnoozeKey) || "null");
    return snooze?.version === info.latestVersion && Number(snooze.until || 0) > Date.now();
  } catch (_err) {
    storeRemove(releaseNotesSnoozeKey);
    return false;
  }
}

function showReleaseNotesIfNeeded() {
  const info = latestAppInfo;
  if (releaseNotesShownThisSession || !isUnlocked() || !info?.latestVersion) return;
  const installed = installedAppVersion();
  if (compareVersions(info.latestVersion, installed) !== 0) return;
  if (info.releaseNotesVersion && info.releaseNotesVersion !== info.latestVersion) return;
  const notes = Array.isArray(info.releaseNotes) ? info.releaseNotes.filter(Boolean) : [];
  if (!notes.length || releaseNotesSnoozed(info)) return;
  releaseNotesShownThisSession = true;
  $("releaseNotesTitle").textContent = `v${info.latestVersion} 수정사항`;
  $("releaseNotesVersion").textContent = `v${info.latestVersion} 업데이트 내용`;
  $("releaseNotesList").innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
  $("releaseNotesSnooze").checked = false;
  $("releaseNotesModal").classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeReleaseNotesModal() {
  if ($("releaseNotesSnooze").checked && latestAppInfo?.latestVersion) {
    storeSet(releaseNotesSnoozeKey, JSON.stringify({
      version: latestAppInfo.latestVersion,
      until: Date.now() + 7 * 24 * 60 * 60 * 1000,
    }));
  }
  $("releaseNotesModal").classList.add("hidden");
  syncModalOpenState();
}

function closeTopModal() {
  if (isModalVisible("worklogCalendarModal")) {
    closeWorklogCalendar();
    return true;
  }
  if (isModalVisible("profileModal")) {
    closeProfileModal();
    return true;
  }
  if (isModalVisible("settingsModal")) {
    closeSettingsModal();
    return true;
  }
  if (isModalVisible("historyModal")) {
    closeHistoryModal();
    return true;
  }
  if (isModalVisible("releaseNotesModal")) {
    closeReleaseNotesModal();
    return true;
  }
  return false;
}

window.FruitAppBack = {
  handleBackPress: closeTopModal,
};

$("historyOpenBtn").addEventListener("click", () => {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  openHistoryModal();
});

$("historyCloseBtn").addEventListener("click", closeHistoryModal);
$("historyCalendarBtn").addEventListener("click", () => {
  const input = $("historyDateInput");
  if (typeof input.showPicker === "function") {
    input.showPicker();
  } else {
    input.focus();
    input.click();
  }
});
$("historyDateInput").addEventListener("change", async (event) => {
  selectedHistoryDate = event.target.value || localDateValue(new Date());
  syncHistoryDateControls();
  await refreshHistory();
});

$("settingsOpenBtn").addEventListener("click", openSettingsModal);
$("heroProfileBtn").addEventListener("click", () => {
  openProfileModal();
});
$("settingsCloseBtn").addEventListener("click", closeSettingsModal);
$("appearanceSaveBtn").addEventListener("click", saveProfileSettings);
$("settingsModal").addEventListener("click", (event) => {
  if (event.target === $("settingsModal")) closeSettingsModal();
});

$("profileCloseBtn").addEventListener("click", closeProfileModal);
$("profileModal").addEventListener("click", (event) => {
  if (event.target === $("profileModal")) closeProfileModal();
});

$("releaseNotesCloseBtn").addEventListener("click", closeReleaseNotesModal);
$("releaseNotesOkBtn").addEventListener("click", closeReleaseNotesModal);
$("releaseNotesModal").addEventListener("click", (event) => {
  if (event.target === $("releaseNotesModal")) closeReleaseNotesModal();
});

$("profilePreview").addEventListener("click", () => $("profilePhotoInput").click());
$("profilePhotoPickBtn").addEventListener("click", () => $("profilePhotoInput").click());
$("profilePhotoInput").addEventListener("change", async () => {
  const file = $("profilePhotoInput").files?.[0];
  if (!file) return;
  try {
    setBusy(true);
    const dataUrl = await resizeProfilePhoto(file);
    setSenderProfilePhoto(dataUrl);
    let savedPhoto = dataUrl;
    try {
      const result = await api("/api/profile-photo", { image: dataUrl });
      savedPhoto = result.profilePhotoUrl || dataUrl;
    } catch (err) {
      console.warn("profile photo sync failed", err);
    }
    setSenderProfilePhoto(savedPhoto);
    updateProfileUi($("heroTitleText").textContent, isUnlocked(), savedPhoto);
    toast("프로필 사진을 변경했습니다.");
  } catch (err) {
    toast(`프로필 사진 변경 실패: ${err.message}`);
  } finally {
    $("profilePhotoInput").value = "";
    setBusy(false);
  }
});
$("profilePhotoResetBtn").addEventListener("click", async () => {
  const senderId = currentSenderEmployeeId();
  setSenderProfilePhoto("");
  forgetProfilePhoto(senderId);
  updateProfileUi($("heroTitleText").textContent, isUnlocked(), "");
  try {
    await api("/api/profile-photo", { image: "" });
  } catch (_err) {
    // Local reset should still work even if server sync fails.
  }
  toast("프로필 사진을 기본 이미지로 돌렸습니다.");
});

$("refreshBalanceBtn").addEventListener("click", refreshBalance);

$("intervalAddBtn").addEventListener("click", () => {
  setIntervalMinutes(Math.min(60, intervalMinutes() + 5));
});

$("intervalResetBtn").addEventListener("click", () => {
  setIntervalMinutes(5);
});

$("historyModal").addEventListener("click", (event) => {
  if (event.target === $("historyModal")) closeHistoryModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && closeTopModal()) {
    event.preventDefault();
  }
});

function selectedWorklogProject() {
  const id = $("worklogProjectSelect").value;
  return worklogProjects.find((project) => String(project.id) === String(id)) || null;
}

function worklogPayload(enabledOverride) {
  const project = selectedWorklogProject();
  const seedCount = Math.max(0, Math.min(3, Math.floor(Number($("worklogSeedCount").value || 0))));
  const target = pendingWorklogTarget || {
    emp_id: currentState.worklogTargetEmployeeId,
    emp_nm: currentState.worklogTargetEmployeeName,
    dept_nm: currentState.worklogTargetDeptName,
    pos_nm: currentState.worklogTargetPositionName,
    duty_id: currentState.worklogTargetDutyId,
  };
  $("worklogSeedCount").value = seedCount;
  return {
    enabled: enabledOverride ?? $("worklogEnabled").checked,
    seedCount,
    seedMessage: $("worklogSeedMessage").value.trim(),
    targetEmployeeId: target.emp_id || "",
    targetEmployeeName: target.emp_nm || "",
    targetDeptName: target.dept_nm || "",
    targetPositionName: target.pos_nm || "",
    targetDutyId: target.duty_id || "",
    projectId: project?.id || "",
    projectName: project?.name || "",
    content: $("worklogContent").value.trim(),
    scheduleDays: selectedWorklogDays,
    scheduleDates: selectedWorklogDates,
    scheduleTime: $("worklogTimeInput").value || "09:05",
  };
}

$("worklogSearchBtn").addEventListener("click", async () => {
  const query = $("worklogSearchInput").value.trim();
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  if (!query) {
    toast("검색어를 입력하세요.");
    return;
  }
  try {
    setBusy(true);
    const data = await api("/api/search", { query });
    renderWorklogResults(data.results || []);
    toast(`검색 결과 ${(data.results || []).length}건`);
  } catch (err) {
    toast(`업무일지 직원 검색 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("worklogSearchInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("worklogSearchBtn").click();
});

$("worklogCalendarBtn").addEventListener("click", () => {
  openWorklogCalendar();
});

$("worklogDateInput").addEventListener("click", () => {
  openWorklogCalendar();
});

$("worklogCalendarCloseBtn").addEventListener("click", closeWorklogCalendar);
$("worklogCalendarModal").addEventListener("click", (event) => {
  if (event.target === $("worklogCalendarModal")) closeWorklogCalendar();
});
$("worklogCalendarPrevBtn").addEventListener("click", () => {
  worklogCalendarMonth = new Date(worklogCalendarMonth.getFullYear(), worklogCalendarMonth.getMonth() - 1, 1);
  renderWorklogCalendar();
});
$("worklogCalendarNextBtn").addEventListener("click", () => {
  worklogCalendarMonth = new Date(worklogCalendarMonth.getFullYear(), worklogCalendarMonth.getMonth() + 1, 1);
  renderWorklogCalendar();
});
$("worklogCalendarResetBtn").addEventListener("click", () => {
  calendarDraftDates = [];
  markWorklogDraftDirty();
  renderWorklogCalendar();
});
$("worklogCalendarApplyBtn").addEventListener("click", () => {
  selectedWorklogDates = calendarDraftDates.filter(isWorklogAllowedDate).sort();
  markWorklogDraftDirty();
  renderWorklogDates();
  closeWorklogCalendar();
});

$("worklogSeedCount").addEventListener("input", () => {
  const value = Math.max(0, Math.min(3, Math.floor(Number($("worklogSeedCount").value || 0))));
  $("worklogSeedCount").value = value;
  markWorklogDraftDirty();
});

[
  "worklogSeedMessage",
  "worklogProjectSelect",
  "worklogContent",
  "worklogTimeInput",
  "worklogEnabled",
].forEach((id) => {
  $(id).addEventListener("input", markWorklogDraftDirty);
  $(id).addEventListener("change", markWorklogDraftDirty);
});

$("worklogSaveBtn").addEventListener("click", async () => {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    const state = await api("/api/worklog-settings", worklogPayload());
    worklogDraftDirty = false;
    renderState(state);
    toast(state.worklogEnabled ? "업무일지 예약을 저장했습니다." : "업무일지 설정을 저장했습니다.");
  } catch (err) {
    toast(`업무일지 저장 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("worklogRunBtn").addEventListener("click", async () => {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    await api("/api/worklog-settings", worklogPayload(false));
    const result = await api("/api/worklog-run-now", {});
    worklogDraftDirty = false;
    renderState(result.state || currentState);
    toast(`업무일지를 작성했습니다. ${result.projectName || ""}`);
  } catch (err) {
    if (isAuthError({ error: err.message }, { status: 401 }) || !isUnlocked()) {
      clearAuthenticatedUi();
      toast("");
    } else {
      toast(`업무일지 즉시 작성 실패: ${err.message}`);
    }
  } finally {
    setBusy(false);
  }
});

$("searchBtn").addEventListener("click", async () => {
  const query = $("searchInput").value.trim();
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  if (!query) {
    toast("검색어를 입력하세요.");
    return;
  }
  try {
    setBusy(true);
    const data = await api("/api/search", { query });
    renderResults(data.results || []);
    toast(`검색 결과 ${(data.results || []).length}건`);
  } catch (err) {
    toast(`검색 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("messageBtn").addEventListener("click", async () => {
  try {
    setBusy(true);
    const { state, count, sendAll } = await saveTransferSettings();
    renderState(state);
    toast(sendAll ? "전송 설정을 저장했습니다. 앞으로 보유 열매를 전부 보냅니다." : `전송 설정을 저장했습니다. 앞으로 최대 ${count}개씩 보냅니다.`);
  } catch (err) {
    toast(`저장 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("sendAllBerries").addEventListener("change", () => {
  const sendAll = $("sendAllBerries").checked;
  $("sendBerryCount").disabled = sendAll;
  if (sendAll) $("sendBerryCount").blur();
});

$("sendBerryCount").addEventListener("input", () => {
  if ($("sendAllBerries").checked) {
    $("sendAllBerries").checked = false;
  }
  $("sendBerryCount").disabled = false;
});

async function saveTransferSettings() {
  const sendAll = $("sendAllBerries").checked;
  $("sendBerryCount").disabled = sendAll;
  const count = Math.max(1, Math.floor(Number($("sendBerryCount").value || 1)));
  await api("/api/message", { message: $("giftMessage").value.trim() });
  const state = await api("/api/send-count", { count, sendAll });
  return { state, count, sendAll };
}

$("autoToggle").addEventListener("change", async () => {
  if (!isUnlocked()) {
    $("autoToggle").checked = false;
    toast("먼저 로그인하세요.");
    return;
  }
  if (!$("autoToggle").checked && !currentState.enabled) return;
  try {
    setBusy(true);
    if ($("autoToggle").checked) {
      await saveTransferSettings();
    }
    const path = $("autoToggle").checked ? "/api/on" : "/api/off";
    const state = await api(path, {});
    renderState(state);
    toast($("autoToggle").checked ? `열매 자동전송을 켰습니다. ${intervalMinutes(state)}분마다 한 번만 실행합니다.` : "열매 자동전송을 껐습니다.");
  } catch (err) {
    $("autoToggle").checked = !!currentState.enabled;
    toast(`상태 변경 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("pushToggle").addEventListener("change", async () => {
  if (!isUnlocked()) {
    $("pushToggle").checked = false;
    toast("먼저 로그인하세요.");
    return;
  }
  const enabled = $("pushToggle").checked;
  try {
    setBusy(true);
    if (enabled && !supportsNativePush()) {
      await ensureWebPushSubscription();
    } else if (!enabled && !supportsNativePush()) {
      await disableWebPushSubscription();
    }
    const state = await api("/api/push", { enabled });
    renderState(state);
    toast(enabled ? "기기 Push 알림을 켰습니다." : "기기 Push 알림을 껐습니다.");
  } catch (err) {
    $("pushToggle").checked = currentState.pushEnabled !== false;
    toast(`Push 설정 실패: ${err.message}`);
  } finally {
    setBusy(false);
  }
});

$("runBtn").addEventListener("click", async () => {
  if (!isUnlocked()) {
    toast("먼저 로그인하세요.");
    return;
  }
  try {
    setBusy(true);
    toast("실행 중입니다...");
    await saveTransferSettings();
    const result = await api("/api/run-now", {});
    if (result.action === "sent") {
      // Successful runs are reflected by the refreshed status/history; no bottom toast needed.
    } else if (result.action === "none") {
      toast(`보낼 열매가 없습니다. 다음 ${intervalMinutes()}분에 다시 확인합니다.`);
    } else if (result.reason === "already_attempted_this_interval") {
      toast(`이번 주기는 이미 확인했습니다. 다음 ${intervalMinutes()}분에 다시 시도합니다.`);
    } else if (result.action === "failed") {
      toast(`실행 실패. 다음 ${intervalMinutes()}분에 다시 확인합니다.`);
    } else {
      toast(`실행 결과: ${result.action}`);
    }
    await refresh({ silent: true });
    if (!$("historyModal").classList.contains("hidden")) {
      await refreshHistory({ silent: true });
    }
  } catch (err) {
    toast(`실행 실패: ${err.message}. 다음 ${intervalMinutes()}분에 다시 확인합니다.`);
  } finally {
    setBusy(false);
  }
});

$("searchInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") $("searchBtn").click();
});

$("rememberLogin").addEventListener("change", () => {
  if (!$("rememberLogin").checked) {
    clearRememberedLogin();
    toast("저장된 아이디를 지웠습니다.");
  } else {
    const id = $("loginId").value.trim();
    const password = $("loginPw").value;
    if (id && password) saveRememberedLogin(id, password);
  }
});

$("supportLink").addEventListener("click", openSupportLink);

async function initApp() {
  initializeAppearanceSettings();
  renderAppearanceOptions();
  if (await checkAppVersion()) return;
  await restoreSavedLoginIfNeeded();
  updateProfileUi("fingerfruit", false);
  renderState({});
  renderCachedState();
  await refresh({ silent: true, forceBalance: true });
  await loadProfileSettings({ silent: true });
  showReleaseNotesIfNeeded();
}

initApp();
setInterval(() => refresh({ silent: true }), 30000);
setInterval(() => checkReceivedNotifications({ silent: true }), 15000);
setTimeout(() => checkReceivedNotifications({ silent: true }), 2500);
