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
const appVersion = "2.5.0";
const primaryApiBaseUrl = "https://web-production-011c4.up.railway.app";
const fallbackBaseUrl = "https://web-production-011c4.up.railway.app";
const activeApiBaseKey = "fruitActiveApiBaseV25";
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
  storeSet(c_5׋h��춻�q�^uTopModal() {
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
