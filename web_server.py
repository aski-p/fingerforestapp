#!/usr/bin/env python3
import json
import mimetypes
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import fruit_auto


BASE_DIR = Path(__file__).resolve().parent
WWW_DIR = BASE_DIR / "www"
DATA_DIR = fruit_auto.DATA_DIR
TOKEN_PATH = DATA_DIR / "web_token.txt"
WEB_PID_PATH = DATA_DIR / "web_server.pid"
PORT = 8765
CHECK_LOCK = threading.Lock()
APP_VERSION = "3.1"
RAILWAY_PUBLIC_BASE_URL = os.environ.get("FINGERFRUIT_PUBLIC_BASE_URL", "https://web-production-011c4.up.railway.app").rstrip("/")
RELEASE_NOTES = [
    "내역조회에서 상대 프로필 사진이 로그인 사용자 사진으로 대체 표시되는 문제를 수정했습니다.",
    "한번 실행은 자동 전송 대기시간을 타지 않고 현재 보유 열매를 즉시 전송하도록 수정했습니다.",
    "앱 실행 시 이전 NAS/임시 API 주소 캐시가 남아 있으면 Railway 기준 주소로 자동 복구하도록 수정했습니다.",
    "iPhone 설치 파일 버튼이 프로파일 설치 화면으로 바로 열리도록 수정했습니다.",
    "업무일지 달력 요일이 월화수목금토일 한 줄로 고정되도록 배포 CSS를 수정했습니다.",
    "내역조회 순서를 FOREST API 화면 순서와 동일하게 유지하도록 수정했습니다.",
    "업무일지 날짜 선택 버튼이 깨지는 함수 호출 오류를 수정했습니다.",
    "업무일지 달력에서 지난 예약 날짜와 이미 전송 완료된 날짜가 계속 선택된 것처럼 보이는 문제를 수정했습니다.",
    "업무일지 예약 저장 시 지난 날짜가 서버 상태에 남지 않도록 정리했습니다.",
    "업무일지 달력이 7열로 표시되지 않아 일요일과 날짜가 밀리는 문제를 수정했습니다.",
    "앱 아이콘을 더 깔끔한 새 디자인으로 교체했습니다.",
    "앱과 설치 링크의 기본 접속 기준을 Railway 배포 주소로 고정했습니다.",
    "내역조회에서 공식 내역 시간 매칭이 없을 때도 관측 시간을 표시하도록 보강했습니다.",
    "업무일지 달력을 월화수목금토일 순서로 표시하도록 조정했습니다.",
    "업무일지 예약은 실제 전송 완료 날짜 기준으로 하루 한 번만 실행되도록 수정했습니다.",
    "앱 실행을 막는 업데이트 필요 안내를 제거했습니다.",
]
VALID_THEMES = {
    "default",
    "dark",
    "berry",
    "ocean",
    "sunset",
    "forest",
    "mint",
    "lemon",
    "cherry",
    "lavender",
    "graphite",
    "cocoa",
    "cyber",
    "peach",
    "mono",
    "royal",
    "getter",
}
VALID_FONTS = {
    "pretendard",
    "noto",
    "system",
    "rounded",
    "serif",
    "mono",
    "humanist",
    "condensed",
    "classic",
    "editorial",
    "playful",
    "clean",
    "slab",
    "geometric",
    "typewriter",
}


def supabase_config():
    secrets = fruit_auto.load_secrets()
    config = secrets.get("supabase") if isinstance(secrets.get("supabase"), dict) else {}
    url = os.environ.get("SUPABASE_URL") or config.get("url") or ""
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or config.get("serviceRoleKey") or config.get("service_role_key") or ""
    if not url or not key:
        return None
    return {
        "url": url.rstrip("/"),
        "key": key,
        "bucket": os.environ.get("SUPABASE_PROFILE_BUCKET") or config.get("profileBucket") or "profiles",
        "table": os.environ.get("SUPABASE_PROFILE_TABLE") or config.get("profileTable") or "profiles",
    }


def supabase_request(method, path, body=None, content_type="application/json", extra_headers=None):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "apikey": config["key"],
        "Authorization": f"Bearer {config['key']}",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(config["url"] + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise fruit_auto.FruitAutoError(f"Supabase 요청 실패: {exc.code} {detail}") from exc
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def profile_public_url(config, path):
    quoted = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return f"{config['url']}/storage/v1/object/public/{config['bucket']}/{quoted}"


def profile_url_with_version(url, updated_at):
    if not url:
        return ""
    if not updated_at:
        return url
    return f"{url}{'&' if '?' in url else '?'}v={urllib.parse.quote(str(updated_at))}"


def list_profile_photos(employee_ids):
    config = supabase_config()
    ids = sorted({str(item) for item in employee_ids if item})
    if not config or not ids:
        return {}
    quoted_ids = ",".join(urllib.parse.quote(item, safe="") for item in ids)
    table = urllib.parse.quote(config["table"], safe="")
    select = "employee_id,name,profile_image_url,profile_image_path,updated_at"
    try:
        rows = supabase_request(
            "GET",
            f"/rest/v1/{table}?select={select}&employee_id=in.({quoted_ids})",
            content_type=None,
        ) or []
    except Exception:
        return {}
    result = {}
    for row in rows:
        employee_id = str(row.get("employee_id") or "")
        if not employee_id:
            continue
        url = row.get("profile_image_url")
        if not url and row.get("profile_image_path"):
            url = profile_public_url(config, row["profile_image_path"])
        result[employee_id] = {
            "url": profile_url_with_version(url, row.get("updated_at")),
            "name": row.get("name") or "",
        }
    return result


def attach_profile_photos(items):
    photos = list_profile_photos(
        item.get("avatarEmployeeId") or item.get("senderEmployeeId")
        for item in items
    )
    for item in items:
        profile = photos.get(str(item.get("avatarEmployeeId") or item.get("senderEmployeeId") or ""))
        if profile:
            item["avatarProfilePhotoUrl"] = profile.get("url") or ""
            item["senderProfilePhotoUrl"] = profile.get("url") or ""
    return items


def attach_state_profile_photos(state):
    employee_ids = [
        state.get("senderEmployeeId") or state.get("loginUserId"),
        state.get("targetEmployeeId"),
    ]
    photos = list_profile_photos(employee_ids)
    sender_profile = photos.get(str(employee_ids[0] or ""))
    target_profile = photos.get(str(employee_ids[1] or ""))
    state["senderProfilePhotoUrl"] = (
        state.get("senderProfilePhotoUrl")
        or state.get("profilePhotoUrl")
        or (sender_profile.get("url") if sender_profile else "")
        or ""
    )
    state["targetProfilePhotoUrl"] = (
        state.get("targetProfilePhotoUrl")
        or (target_profile.get("url") if target_profile else "")
        or ""
    )
    return state


def profile_employee_id(owner_key):
    state = fruit_auto.get_account_state(owner_key)
    employee_id = str(state.get("senderEmployeeId") or state.get("loginUserId") or fruit_auto.employee_id_from_owner_key(owner_key) or "")
    if not employee_id:
        raise fruit_auto.FruitAutoError("프로필을 저장할 직원 ID가 없습니다.")
    return employee_id, state


def profile_settings_fallback(owner_key):
    state = fruit_auto.get_account_state(owner_key)
    return {
        "theme": state.get("theme") or "default",
        "font": state.get("font") or "pretendard",
        "synced": False,
    }


def load_profile_settings(owner_key):
    config = supabase_config()
    employee_id, state = profile_employee_id(owner_key)
    fallback = {
        "theme": state.get("theme") or "default",
        "font": state.get("font") or "pretendard",
        "synced": False,
    }
    if not config:
        return fallback
    table = urllib.parse.quote(config["table"], safe="")
    quoted_id = urllib.parse.quote(employee_id, safe="")
    try:
        rows = supabase_request(
            "GET",
            f"/rest/v1/{table}?select=theme,font,ui_settings&employee_id=eq.{quoted_id}&limit=1",
            content_type=None,
        ) or []
    except Exception:
        return fallback
    if not rows:
        return fallback
    row = rows[0]
    settings = row.get("ui_settings") if isinstance(row.get("ui_settings"), dict) else {}
    return {
        "theme": row.get("theme") or settings.get("theme") or fallback["theme"],
        "font": row.get("font") or settings.get("font") or fallback["font"],
        "synced": True,
    }


def save_profile_settings(owner_key, payload):
    employee_id, state = profile_employee_id(owner_key)
    theme = str(payload.get("theme") or "default")
    font = str(payload.get("font") or "pretendard")
    if theme not in VALID_THEMES:
        theme = "default"
    if font not in VALID_FONTS:
        font = "pretendard"
    state["theme"] = theme
    state["font"] = font
    state["updatedAt"] = fruit_auto.now_iso()
    fruit_auto.save_account_state(owner_key, state)

    config = supabase_config()
    if not config:
        return {"theme": theme, "font": font, "synced": False}
    table = urllib.parse.quote(config["table"], safe="")
    row = {
        "employee_id": employee_id,
        "name": state.get("senderEmployeeName") or state.get("loginUser") or employee_id,
        "theme": theme,
        "font": font,
        "ui_settings": {"theme": theme, "font": font},
        "updated_at": fruit_auto.now_iso(),
    }
    try:
        supabase_request(
            "POST",
            f"/rest/v1/{table}",
            body=row,
            extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        return {"theme": theme, "font": font, "synced": True}
    except Exception:
        return {"theme": theme, "font": font, "synced": False}


def saved_login_hint(owner_key=None):
    if not owner_key:
        return {"saved": False}
    account = fruit_auto.load_secrets().get("accounts", {}).get(owner_key) or {}
    if not account.get("pms_id"):
        return {"saved": False}
    return {
        "saved": True,
        "id": account.get("pms_id") or "",
        "ownerKey": owner_key,
    }


def upload_profile_photo(owner_key, data_url):
    employee_id, state = profile_employee_id(owner_key)
    if not data_url:
        state.pop("senderProfilePhotoUrl", None)
        state.pop("profilePhotoUrl", None)
        state["profilePhotoUpdatedAt"] = fruit_auto.now_iso()
        fruit_auto.save_account_state(owner_key, state)
        return {"enabled": True, "employeeId": employee_id, "profilePhotoUrl": ""}
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or "," not in data_url:
        raise fruit_auto.FruitAutoError("지원하지 않는 이미지 형식입니다.")
    meta, encoded = data_url.split(",", 1)
    mime = meta[5:].split(";", 1)[0] or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise fruit_auto.FruitAutoError("jpg, png, webp 이미지만 지원합니다.")
    import base64
    image_bytes = base64.b64decode(encoded)
    if len(image_bytes) > 800_000:
        raise fruit_auto.FruitAutoError("프로필 이미지는 800KB 이하로 줄여주세요.")
    state["senderProfilePhotoUrl"] = data_url
    state["profilePhotoUrl"] = data_url
    state["profilePhotoUpdatedAt"] = fruit_auto.now_iso()
    fruit_auto.save_account_state(owner_key, state)

    config = supabase_config()
    if not config:
        return {"enabled": False, "employeeId": employee_id, "profilePhotoUrl": data_url}

    extension = "webp" if mime == "image/webp" else "png" if mime == "image/png" else "jpg"
    storage_path = f"{employee_id}/avatar.{extension}"
    bucket = urllib.parse.quote(config["bucket"], safe="")
    object_path = "/".join(urllib.parse.quote(part) for part in storage_path.split("/"))
    supabase_request(
        "POST",
        f"/storage/v1/object/{bucket}/{object_path}",
        body=image_bytes,
        content_type=mime,
        extra_headers={"x-upsert": "true", "cache-control": "3600"},
    )
    public_url = profile_public_url(config, storage_path)
    table = urllib.parse.quote(config["table"], safe="")
    row = {
        "employee_id": employee_id,
        "name": state.get("senderEmployeeName") or state.get("loginUser") or employee_id,
        "profile_image_path": storage_path,
        "profile_image_url": public_url,
        "updated_at": fruit_auto.now_iso(),
    }
    supabase_request(
        "POST",
        f"/rest/v1/{table}",
        body=row,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=representation"},
    )
    profile_url = profile_url_with_version(public_url, row["updated_at"])
    state["senderProfilePhotoUrl"] = profile_url
    state["profilePhotoUrl"] = profile_url
    state["profilePhotoUpdatedAt"] = row["updated_at"]
    fruit_auto.save_account_state(owner_key, state)
    return {"enabled": True, "employeeId": employee_id, "profilePhotoUrl": profile_url}

mimetypes.add_type("application/vnd.android.package-archive", ".apk")
mimetypes.add_type("application/x-apple-aspen-config", ".mobileconfig")


def public_state(owner_key=None, refresh_balance=False):
    if owner_key:
        secrets = fruit_auto.load_secrets()
        if owner_key not in secrets.get("accounts", {}):
            state = dict(fruit_auto.DEFAULT_STATE)
            state["credentialsSaved"] = False
        else:
            state = fruit_auto.get_account_state(owner_key)
            state["credentialsSaved"] = True
        missing_balance = state.get("lastSeedCount") is None or state.get("lastBerryCount") is None
        if (refresh_balance or missing_balance) and state["credentialsSaved"]:
            try:
                state = fruit_auto.refresh_balance(owner_key=owner_key)
            except Exception as exc:
                state["balanceError"] = sanitize_error(exc)
    else:
        state = dict(fruit_auto.DEFAULT_STATE)
        state["credentialsSaved"] = False
    state["hasTarget"] = bool(state.get("targetEmployeeId"))
    state["daemonRunning"] = daemon_running()
    state["activeAccountCount"] = len(fruit_auto.active_owner_keys())
    return attach_state_profile_photos(state)


def state_response(owner_key):
    return public_state(owner_key)


def read_token():
    if not TOKEN_PATH.exists() and os.environ.get("FRUIT_AUTO_WEB_TOKEN"):
        TOKEN_PATH.write_text(os.environ["FRUIT_AUTO_WEB_TOKEN"].strip() + "\n", encoding="utf-8")
    if not TOKEN_PATH.exists():
        raise RuntimeError("web token does not exist")
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


def sanitize_error(exc):
    text = str(exc)
    for secret_name in ("pms_password", "token", "cookie"):
        text = text.replace(secret_name, "secret")
    return text[:500]


def public_base_url(handler):
    forwarded_proto = handler.headers.get("X-Forwarded-Proto") or ""
    proto = forwarded_proto.split(",")[0].strip() or "https"
    host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or ""
    return f"{proto}://{host}".rstrip("/") if host else ""


def app_public_base_url(_handler=None):
    return RAILWAY_PUBLIC_BASE_URL or public_base_url(_handler) or ""


def app_info(handler):
    base_url = app_public_base_url(handler)
    install_url = f"{base_url}/install.html" if base_url else "/install.html"
    latest_apk = versioned_download_file("fingerfruit-android", "apk") or latest_download_file("fingerfruit-android-v", ".apk")
    latest_ios = versioned_download_file("fingerfruit-ios", "mobileconfig") or latest_download_file("fingerfruit-ios-v", ".mobileconfig")
    android_name = latest_apk.name if latest_apk else f"fingerfruit-android-v{APP_VERSION}.apk"
    ios_name = latest_ios.name if latest_ios else f"fingerfruit-ios-v{APP_VERSION}.mobileconfig"
    return {
        "latestVersion": APP_VERSION,
        "minSupportedVersion": APP_VERSION,
        "releaseNotesVersion": APP_VERSION,
        "installUrl": install_url,
        "androidApkUrl": f"{base_url}/downloads/{android_name}" if base_url else f"/downloads/{android_name}",
        "iosProfileUrl": f"{base_url}/downloads/{ios_name}" if base_url else f"/downloads/{ios_name}",
        "message": "새 버전이 있습니다. 업데이트 후 다시 실행해주세요.",
        "releaseNotes": RELEASE_NOTES,
        "publicHolidays": fruit_auto.KOREAN_PUBLIC_HOLIDAYS,
    }


def latest_download_file(prefix, suffix):
    def version_key(path):
        name = path.name
        version = name.removeprefix(prefix).removesuffix(suffix).lstrip("v")
        parts = []
        for part in version.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(-1)
        return (parts, path.stat().st_mtime)

    files = sorted((WWW_DIR / "downloads").glob(f"{prefix}*{suffix}"), key=version_key, reverse=True)
    return files[0] if files else None


def versioned_download_file(kind, extension):
    path = WWW_DIR / "downloads" / f"{kind}-v{APP_VERSION}.{extension}"
    return path if path.exists() and path.is_file() else None


def daemon_running():
    if not fruit_auto.PID_PATH.exists():
        return False
    try:
        pid = int(fruit_auto.PID_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return fruit_auto.is_process_alive(pid)


def wake_daemon():
    if not fruit_auto.PID_PATH.exists():
        return False
    try:
        pid = int(fruit_auto.PID_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    if not fruit_auto.is_process_alive(pid):
        return False
    sigusr1 = getattr(__import__("signal"), "SIGUSR1", None)
    if sigusr1 is None:
        return False
    os.kill(pid, sigusr1)
    return True


def ensure_daemon_running():
    if daemon_running():
        return True
    log_path = BASE_DIR / "daemon.log"
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "fruit_auto.py"), "daemon"],
            cwd=str(BASE_DIR.parent.parent),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    return True


def run_check_once(owner_key, force=False):
    with CHECK_LOCK:
        return fruit_auto.check_once(owner_key=owner_key, force=force)


def send_no_cache_headers(handler):
    handler.send_header("Cache-Control", "no-store, no-cache, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Expires", "0")


class Handler(BaseHTTPRequestHandler):
    server_version = "FruitAuto/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        send_no_cache_headers(self)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Fruit-Token, X-Fruit-Session, X-Fruit-Owner, X-Fruit-Device")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Fruit-Token, X-Fruit-Session, X-Fruit-Owner, X-Fruit-Device")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        send_no_cache_headers(self)
        self.end_headers()

    def require_auth(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        token = self.headers.get("X-Fruit-Token") or (query.get("token") or [""])[0]
        return token and token == read_token()

    def device_id(self):
        return (self.headers.get("X-Fruit-Device") or "").strip()

    def expected_owner(self):
        return (self.headers.get("X-Fruit-Owner") or "").strip()

    def session_owner(self):
        session_token = self.headers.get("X-Fruit-Session") or ""
        return fruit_auto.owner_from_session(session_token, self.device_id()), session_token

    def require_session_owner(self):
        owner_key, session_token = self.session_owner()
        if not owner_key:
            raise fruit_auto.FruitAutoError("로그인이 필요합니다.")
        expected_owner = self.expected_owner()
        if expected_owner and expected_owner != owner_key:
            raise fruit_auto.FruitAutoError("현재 기기의 로그인 정보와 서버 세션이 일치하지 않습니다. 다시 로그인하세요.")
        return owner_key, session_token

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_static(self, include_body=True):
        parsed = urllib.parse.urlparse(self.path)
        root = WWW_DIR
        rel = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        if parsed.path.startswith("/fonts/"):
            root = BASE_DIR
        path = (root / rel).resolve()
        if parsed.path == "/android.apk":
            latest_apk = versioned_download_file("fingerfruit-android", "apk") or latest_download_file("fingerfruit-android-v", ".apk")
            if latest_apk:
                path = latest_apk.resolve()
                root = latest_apk.parent
        elif parsed.path == "/ios.mobileconfig":
            latest_ios = versioned_download_file("fingerfruit-ios", "mobileconfig") or latest_download_file("fingerfruit-ios-v", ".mobileconfig")
            if latest_ios:
                path = latest_ios.resolve()
                root = latest_ios.parent
        elif parsed.path.startswith("/downloads/fingerfruit-android-v") and parsed.path.endswith(".apk") and not path.exists():
            latest_apk = latest_download_file("fingerfruit-android-v", ".apk")
            if latest_apk:
                path = latest_apk.resolve()
                root = latest_apk.parent
        elif parsed.path.startswith("/downloads/fingerfruit-ios-v") and parsed.path.endswith(".mobileconfig") and not path.exists():
            latest_ios = latest_download_file("fingerfruit-ios-v", ".mobileconfig")
            if latest_ios:
                path = latest_ios.resolve()
                root = latest_ios.parent
        if not str(path).startswith(str(root.resolve())) or not path.exists() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        is_mobileconfig = path.suffix == ".mobileconfig" or parsed.path == "/ios.mobileconfig"
        if is_mobileconfig:
            ctype = "application/x-apple-aspen-config"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        send_no_cache_headers(self)
        self.send_header("Content-Length", str(len(data)))
        if is_mobileconfig:
            self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        elif parsed.path.startswith("/downloads/") or parsed.path == "/android.apk":
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_error(405)
            return
        self.send_static(include_body=False)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if parsed.path == "/api/app-info":
                self.send_json(200, {"ok": True, "result": app_info(self)})
                return
            if not self.require_auth():
                self.send_json(401, {"ok": False, "error": "unauthorized"})
                return
            try:
                if parsed.path == "/api/status":
                    owner_key, _session_token = self.require_session_owner()
                    self.send_json(200, {"ok": True, "state": public_state(owner_key)})
                elif parsed.path == "/api/session":
                    owner_key, _session_token = self.session_owner()
                    if not owner_key:
                        raise fruit_auto.FruitAutoError("로그인이 필요합니다.")
                    self.send_json(200, {"ok": True, "result": fruit_auto.issue_session(owner_key=owner_key, device_id=self.device_id())})
                elif parsed.path == "/api/saved-login":
                    owner_key, _session_token = self.require_session_owner()
                    self.send_json(200, {"ok": True, "result": saved_login_hint(owner_key)})
                elif parsed.path == "/api/profile-settings":
                    owner_key, _session_token = self.require_session_owner()
                    self.send_json(200, {"ok": True, "result": load_profile_settings(owner_key)})
                elif parsed.path == "/api/history":
                    owner_key, _session_token = self.require_session_owner()
                    params = urllib.parse.parse_qs(parsed.query)
                    selected_date = (params.get("date") or [""])[0]
                    try:
                        timezone_offset = int((params.get("tz") or ["0"])[0])
                    except ValueError:
                        timezone_offset = 0
                    items = attach_profile_photos(
                        fruit_auto.history(
                            owner_key=owner_key,
                            date=selected_date,
                            timezone_offset_minutes=timezone_offset,
                        )
                    )
                    self.send_json(200, {"ok": True, "result": {"items": items}})
                elif parsed.path == "/api/worklog-projects":
                    owner_key, _session_token = self.require_session_owner()
                    self.send_json(200, {"ok": True, "result": {"projects": fruit_auto.list_worklog_projects(owner_key=owner_key)}})
                elif parsed.path == "/api/notifications":
                    owner_key, _session_token = self.require_session_owner()
                    self.send_json(200, {"ok": True, "result": {"items": fruit_auto.notification_items(owner_key=owner_key)}})
                elif parsed.path == "/api/push/public-key":
                    self.send_json(200, {"ok": True, "result": {"publicKey": fruit_auto.web_push_public_key()}})
                else:
                    self.send_json(404, {"ok": False, "error": "not found"})
            except Exception as exc:
                error = sanitize_error(exc)
                self.send_json(401 if "로그인" in error or "세션" in error or "기기 CID" in error else 500, {"ok": False, "error": error})
            return

        self.send_static()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith("/api/") or not self.require_auth():
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            payload = self.read_json()
            if parsed.path == "/api/login":
                result = fruit_auto.save_credentials(payload.get("id"), payload.get("password"), device_id=self.device_id())
            else:
                owner_key, session_token = self.require_session_owner()
            if parsed.path == "/api/login":
                pass
            elif parsed.path == "/api/logout":
                result = fruit_auto.logout(owner_key=owner_key, session_token=session_token)
            elif parsed.path == "/api/search":
                result = {"results": fruit_auto.search_employees(payload.get("query", ""), owner_key=owner_key)}
            elif parsed.path == "/api/target":
                fruit_auto.set_target(
                    payload.get("emp_id"),
                    payload.get("emp_nm"),
                    payload.get("duty_id"),
                    payload.get("dept_nm"),
                    payload.get("pos_nm"),
                    owner_key=owner_key,
                )
                result = state_response(owner_key)
            elif parsed.path == "/api/message":
                fruit_auto.set_message(payload.get("message", ""), owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/send-count":
                fruit_auto.set_send_berry_count(
                    payload.get("count"),
                    send_all=payload.get("sendAll"),
                    owner_key=owner_key,
                )
                result = state_response(owner_key)
            elif parsed.path == "/api/push":
                fruit_auto.set_push_enabled(payload.get("enabled"), owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/push/subscribe":
                result = fruit_auto.save_web_push_subscription(owner_key, payload.get("subscription"))
            elif parsed.path == "/api/push/unsubscribe":
                result = fruit_auto.remove_web_push_subscription(owner_key, payload.get("endpoint"))
            elif parsed.path == "/api/profile-photo":
                result = upload_profile_photo(owner_key, payload.get("image"))
            elif parsed.path == "/api/profile-settings":
                result = save_profile_settings(owner_key, payload)
            elif parsed.path == "/api/worklog-target":
                fruit_auto.set_worklog_target(
                    payload.get("emp_id"),
                    payload.get("emp_nm"),
                    payload.get("duty_id"),
                    payload.get("dept_nm"),
                    payload.get("pos_nm"),
                    owner_key=owner_key,
                )
                result = state_response(owner_key)
            elif parsed.path == "/api/worklog-settings":
                fruit_auto.set_worklog_settings(payload, owner_key=owner_key)
                result = state_response(owner_key)
                ensure_daemon_running()
                wake_daemon()
            elif parsed.path == "/api/worklog-run-now":
                result = fruit_auto.save_worklog_once(owner_key=owner_key, force=True)
                fruit_auto.notify_result(result)
                result = {**result, "state": state_response(owner_key)}
            elif parsed.path == "/api/interval":
                fruit_auto.set_run_interval(payload.get("minutes"), owner_key=owner_key)
                result = state_response(owner_key)
                wake_daemon()
            elif parsed.path == "/api/refresh":
                fruit_auto.refresh_balance(force=True, owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/on":
                if payload.get("target_name"):
                    fruit_auto.set_target_by_name(payload.get("target_name"))
                fruit_auto.set_enabled(True, owner_key=owner_key)
                result = state_response(owner_key)
                ensure_daemon_running()
                wake_daemon()
            elif parsed.path == "/api/off":
                fruit_auto.set_enabled(False, owner_key=owner_key)
                result = state_response(owner_key)
                wake_daemon()
            elif parsed.path == "/api/run-now":
                try:
                    result = run_check_once(owner_key, force=True)
                except Exception as exc:
                    result = fruit_auto.failed_slot_result(exc, owner_key=owner_key)
            else:
                self.send_json(404, {"ok": False, "error": "not found"})
                return
            self.send_json(200, {"ok": True, "result": result})
        except Exception as exc:
            error = sanitize_error(exc)
            self.send_json(401 if "로그인" in error or "세션" in error or "기기 CID" in error else 500, {"ok": False, "error": error})


class FruitThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = int(os.environ.get("FRUIT_AUTO_HTTP_BACKLOG") or "512")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port_arg = sys.argv[2] if len(sys.argv) > 2 else str(PORT)
    if port_arg == "$PORT":
        port_arg = os.environ.get("PORT") or str(PORT)
    port = int(port_arg)
    httpd = FruitThreadingHTTPServer((host, port), Handler)
    WEB_PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")
    print(f"FruitAuto UI listening on http://{host}:{port}/")
    try:
        httpd.serve_forever()
    finally:
        try:
            if WEB_PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
                WEB_PID_PATH.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
