#!/usr/bin/env python3
import json
import hashlib
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
APP_VERSION = "3.4.3"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-3-haiku-20240307"
CHAT_HISTORY_MESSAGE_LIMIT = 10
CHAT_INPUT_CHAR_LIMIT = 8000
CHAT_OUTPUT_TOKEN_LIMIT = 800
CHAT_REPLY_INSTRUCTION = "답변은 800토큰 안에서 끝맺음까지 완결해 주세요. 길면 핵심만 요약하고 문장 중간에서 끊기지 않게 마무리하세요."
RAILWAY_PUBLIC_BASE_URL = os.environ.get("FINGERFRUIT_PUBLIC_BASE_URL", "https://web-production-011c4.up.railway.app").rstrip("/")
RELEASE_NOTES = [
    "업무일지 카드에서 Getter 장식 클래스가 만드는 예약 여백을 제거해 카드 내부 폼이 열매 보내기처럼 맞게 보이도록 수정했습니다.",
    "상단 탭 스와이프 직후 발생하는 버튼 클릭이 전환을 되돌리지 않도록 처리해 탭 스와이프 전환을 복구했습니다.",
    "업무일지 카드 안의 검색/입력/select/textarea 박스가 오른쪽 끝에서 잘리지 않도록 박스 폭 계산을 고정했습니다.",
    "상단 탭 영역 스와이프 임계값을 낮춰 본문 세로 스크롤은 보호하면서도 탭 스와이프 전환은 다시 자연스럽게 동작하게 조정했습니다.",
    "업무일지/열매보내기 본문 세로 스크롤 중 화면이 옆으로 밀리지 않도록 스와이프 전환 감지를 상단 탭 영역으로만 제한했습니다.",
    "왕관 팝업 랭킹 리스트를 서버 기본 제한 없이 전체 조회하도록 바꾸고 팝업 안에서 스크롤해 볼 수 있게 정리했습니다.",
    "메인 화면 왕관 버튼 텍스트를 실제 왕관 이미지로 교체했습니다.",
    "랭킹 1/2/3등 이미지 위에 숫자가 겹쳐 보이지 않도록 배지 이미지만 표시하게 정리했습니다.",
    "랭킹 1등 배지를 문자 왕관이 아닌 실제 왕관 이미지 asset으로 교체하고 2등/3등도 이미지 배지로 바꿨습니다.",
    "설정 버튼 왼쪽에 왕관 버튼을 추가하고 기존 FOREST 랭킹 API로 열매/열매선물/회원레벨 랭킹 팝업을 조회하도록 추가했습니다.",
    "랭킹 팝업의 1등 배지를 반짝이는 왕관 스타일로 바꾸고 2등/3등 배지도 은색/동색 메달 느낌으로 구분했습니다.",
    "열매 보내기 안의 대상 직원, 전송 설정, 자동전송 영역을 업무일지처럼 옅은 카드 배경으로 분리해 섹션 구분을 명확하게 했습니다.",
    "열매 보내기 지금 한 번 실행 결과를 팝업으로 표시해 보낸 열매 개수와 보낼 열매 없음 상태를 명확히 보여주도록 수정했습니다.",
    "스와이프 전환 중 scroll-snap을 잠깐 비활성화해 페이지가 딱딱하게 붙지 않고 부드럽게 이동하도록 보강했습니다.",
    "열매 보내기 합쳐진 카드에 남아 있던 Getter 테마용 오른쪽 예약 여백을 줄여 입력칸과 버튼 간격을 다시 정리했습니다.",
    "Claude 채팅 답변이 800토큰 안에서 완결되도록 서버 지시문과 fallback 요청을 보강했습니다.",
    "업무일지 지금 한 번 작성 성공 시 완료 팝업이 표시되도록 추가했습니다.",
    "업무일지 화면 여백과 버튼 높이를 조정해 꽉 찬 느낌을 줄였습니다.",
    "열매 보내기/업무일지 스와이프 전환에 완만한 애니메이션과 더 높은 전환 임계값을 적용했습니다.",
    "Claude 채팅을 로그인된 본인 세션 기준으로만 호출하게 고정하고 카카오 Claude fallback 사용자 키도 계정별로 분리했습니다.",
    "Android 로그인 실패가 서버 500으로 보이지 않도록 로그인 API 오류 응답을 401로 정리했습니다.",
    "열매 보내기 화면의 대상 직원, 전송 설정, 자동전송을 하나의 카드 안에 합쳐 화면 흐름을 정리했습니다.",
    "Claude 채팅창 메시지 영역에 독립 스크롤을 적용해 긴 답변이 입력창과 화면을 밀어내지 않도록 수정했습니다.",
    "키보드가 올라왔을 때 보이는 화면 높이에 맞춰 Claude 채팅창 위치와 높이를 다시 계산하도록 수정했습니다.",
    "열매 보내기/업무일지 좌우 전환은 상단 작업 메뉴 영역에서만 스와이프되도록 제한했습니다.",
    "열매 보내기 설정을 대상 직원, 전송 설정, 자동전송이 한 화면에 묶이도록 정리하고 업무일지는 좌우 스와이프 패널로 분리했습니다.",
    "Claude 채팅이 FingerFruit 서버에 키가 없을 때 카카오봇 Claude Haiku 서버로 안전하게 이어지도록 수정했습니다.",
    "Claude 채팅 팝업 크기를 모바일 화면에 맞게 줄이고 버튼 아이콘을 말풍선 디자인으로 교체했습니다.",
    "스킨 선택 시 상단/카드/업무일지/내역조회 UI 색상이 선택한 컨셉에 맞게 따라가도록 정리했습니다.",
    "Android 래퍼 설치 버전 표시가 실제 APK 버전과 다르게 남아있던 문제를 수정했습니다.",
    "오른쪽 아래 Claude Haiku 채팅 팝업을 추가했습니다.",
    "내역조회에서 받음 항목 본문 이름을 받은 사람 기준으로 표시하도록 수정했습니다.",
    "Android APK를 고정 서명 release 빌드로 다시 만들어 업데이트 설치 실패 가능성을 줄였습니다.",
    "내역조회에서 기본 FOREST API에 있는 받은 열매 항목이 짝맞춤 필터 때문에 숨겨지는 문제를 수정했습니다.",
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


def list_profile_photos_by_name(names):
    config = supabase_config()
    safe_names = sorted({str(item).strip() for item in names if str(item or "").strip()})
    if not config or not safe_names:
        return {}
    quoted_names = ",".join(urllib.parse.quote(item, safe="") for item in safe_names)
    table = urllib.parse.quote(config["table"], safe="")
    select = "employee_id,name,profile_image_url,profile_image_path,updated_at"
    try:
        rows = supabase_request(
            "GET",
            f"/rest/v1/{table}?select={select}&name=in.({quoted_names})",
            content_type=None,
        ) or []
    except Exception:
        return {}
    result = {}
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        url = row.get("profile_image_url")
        if not url and row.get("profile_image_path"):
            url = profile_public_url(config, row["profile_image_path"])
        result[name] = {
            "url": profile_url_with_version(url, row.get("updated_at")),
            "employeeId": str(row.get("employee_id") or ""),
        }
    return result


def attach_profile_photos(items):
    employee_ids = []
    for item in items:
        employee_ids.extend(
            [
                item.get("avatarEmployeeId") or item.get("senderEmployeeId"),
                item.get("fromEmployeeId"),
                item.get("toEmployeeId"),
            ]
        )
    photos = list_profile_photos(employee_ids)
    missing_names = [
        name
        for item in items
        for name in (
            item.get("avatarName") or item.get("target") or item.get("senderName"),
            item.get("fromAvatarName") or item.get("fromDisplayName"),
            item.get("toAvatarName") or item.get("toDisplayName"),
        )
        if name
    ]
    photos_by_name = list_profile_photos_by_name(missing_names)
    for item in items:
        avatar_key = str(item.get("avatarEmployeeId") or item.get("senderEmployeeId") or "")
        profile = photos.get(avatar_key)
        if not profile:
            profile = photos_by_name.get(str(item.get("avatarName") or item.get("target") or item.get("senderName") or "").strip())
        if profile:
            item["avatarProfilePhotoUrl"] = profile.get("url") or ""
            item["senderProfilePhotoUrl"] = profile.get("url") or ""
        for prefix in ("from", "to"):
            key = str(item.get(f"{prefix}EmployeeId") or "")
            profile = photos.get(key) if key else None
            if not profile:
                profile = photos_by_name.get(str(item.get(f"{prefix}AvatarName") or item.get(f"{prefix}DisplayName") or "").strip())
            if profile:
                item[f"{prefix}ProfilePhotoUrl"] = profile.get("url") or ""
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


def error_status(error, path=""):
    auth_markers = ("로그인", "세션", "기기 CID", "PMS login", "PMS 로그인", "Forest token", "Forest employee")
    if path == "/api/login":
        return 401
    if any(marker in error for marker in auth_markers[:3]):
        return 401
    return 500


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
    android_name = f"fingerfruit-android-v{APP_VERSION}.apk"
    ios_name = f"fingerfruit-ios-v{APP_VERSION}.mobileconfig"
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


def claude_api_key():
    return os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or ""


def clean_chat_text(value, limit=CHAT_INPUT_CHAR_LIMIT):
    return str(value or "").strip()[:limit]


def kakao_chat_user_id(owner_key):
    scoped = hashlib.sha256(str(owner_key or "anonymous").encode("utf-8")).hexdigest()[:16]
    return f"fingerfruit-chat-{scoped}"


def kakao_claude_chat(message, owner_key):
    webhook_url = os.environ.get("KAKAO_CLAUDE_WEBHOOK_URL") or "https://kakao-skill-webhook-production.up.railway.app/kakao-skill-webhook"
    utterance = f"{CHAT_REPLY_INSTRUCTION}\n\n사용자 질문:\n{message}"
    request_body = json.dumps(
        {
            "userRequest": {
                "utterance": utterance,
                "user": {"id": kakao_chat_user_id(owner_key)},
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=request_body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise fruit_auto.FruitAutoError(f"카카오 Claude 서버 오류: {exc.code} {detail}") from exc
    outputs = data.get("template", {}).get("outputs", []) if isinstance(data, dict) else []
    for output in outputs:
        text = output.get("simpleText", {}).get("text") if isinstance(output, dict) else ""
        if text:
            return {"reply": str(text).strip(), "model": "claude-haiku-via-kakao"}
    raise fruit_auto.FruitAutoError("카카오 Claude 응답이 비어 있습니다.")


def claude_chat(payload, owner_key):
    api_key = claude_api_key()
    message = clean_chat_text(payload.get("message"))
    if not message:
        raise fruit_auto.FruitAutoError("메시지를 입력하세요.")
    if not api_key:
        return kakao_claude_chat(message, owner_key)
    messages = []
    remaining_input = max(0, CHAT_INPUT_CHAR_LIMIT - len(message))
    history = payload.get("history")
    if isinstance(history, list):
        for item in history[-CHAT_HISTORY_MESSAGE_LIMIT:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = clean_chat_text(item.get("content"), remaining_input)
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
                remaining_input = max(0, remaining_input - len(content))
            if remaining_input <= 0:
                break
    messages.append({"role": "user", "content": message})
    request_body = json.dumps(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": CHAT_OUTPUT_TOKEN_LIMIT,
            "system": CHAT_REPLY_INSTRUCTION,
            "messages": messages,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=request_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise fruit_auto.FruitAutoError(f"Claude API 오류: {exc.code} {detail}") from exc
    content = data.get("content") if isinstance(data, dict) else []
    text_parts = [
        str(part.get("text") or "")
        for part in content
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
    ]
    reply = "\n".join(text_parts).strip()
    if not reply:
        raise fruit_auto.FruitAutoError("Claude 응답이 비어 있습니다.")
    return {"reply": reply, "model": data.get("model") or CLAUDE_MODEL}


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
    return False


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
            current_apk = versioned_download_file("fingerfruit-android", "apk")
            if current_apk:
                path = current_apk.resolve()
                root = current_apk.parent
        elif parsed.path == "/ios.mobileconfig":
            current_ios = versioned_download_file("fingerfruit-ios", "mobileconfig")
            if current_ios:
                path = current_ios.resolve()
                root = current_ios.parent
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
                elif parsed.path == "/api/ranking":
                    owner_key, _session_token = self.require_session_owner()
                    params = urllib.parse.parse_qs(parsed.query)
                    kind = (params.get("kind") or ["berry"])[0]
                    month = (params.get("month") or [""])[0]
                    self.send_json(200, {"ok": True, "result": fruit_auto.forest_ranking(kind=kind, month=month, owner_key=owner_key)})
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
                self.send_json(error_status(error, parsed.path), {"ok": False, "error": error})
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
            elif parsed.path == "/api/chat":
                owner_key, _session_token = self.require_session_owner()
                result = claude_chat(payload, owner_key)
            else:
                owner_key, session_token = self.require_session_owner()
            if parsed.path == "/api/login":
                pass
            elif parsed.path == "/api/chat":
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
            elif parsed.path == "/api/worklog-run-now":
                result = fruit_auto.save_worklog_once(owner_key=owner_key, force=True)
                fruit_auto.notify_result(result)
                result = {**result, "state": state_response(owner_key)}
            elif parsed.path == "/api/interval":
                fruit_auto.set_run_interval(payload.get("minutes"), owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/refresh":
                fruit_auto.refresh_balance(force=True, owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/on":
                if payload.get("target_name"):
                    fruit_auto.set_target_by_name(payload.get("target_name"))
                fruit_auto.set_enabled(True, owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/off":
                fruit_auto.set_enabled(False, owner_key=owner_key)
                result = state_response(owner_key)
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
            self.send_json(error_status(error, parsed.path), {"ok": False, "error": error})


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
