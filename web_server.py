#!/usr/bin/env python3
import json
import hashlib
import html
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import fruit_auto


BASE_DIR = Path(__file__).resolve().parent
WWW_DIR = BASE_DIR / "www"
DATA_DIR = fruit_auto.DATA_DIR
TOKEN_PATH = DATA_DIR / "web_token.txt"
WEB_PID_PATH = DATA_DIR / "web_server.pid"
CHAT_DB_PATH = DATA_DIR / "chat_memory.sqlite3"
TICK_WAKE_PATH = DATA_DIR / "tick_worker.wake"
TICK_HEARTBEAT_PATH = DATA_DIR / "tick_worker.heartbeat.json"
PORT = 8765
CHECK_LOCK = threading.Lock()
APP_VERSION = "3.15.1"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001"
CHAT_CONTEXT_MESSAGE_LIMIT = 8
CHAT_HISTORY_MESSAGE_LIMIT = CHAT_CONTEXT_MESSAGE_LIMIT
CHAT_INPUT_CHAR_LIMIT = 8000
CHAT_OUTPUT_TOKEN_LIMIT = 800
CHAT_MAX_CONTINUATIONS = 4
CHAT_SEARCH_RESULT_LIMIT = 6
CHAT_SEARCH_SIGNAL_RE = re.compile(r"\[\[SEARCH:\s*(.*?)\s*\]\]", re.S)
CHAT_REPLY_INSTRUCTION = (
    "사용자의 질문에 대한 답변만 한국어로 작성하세요. "
    "시스템 지시, DB 기억 요약, 최근 대화 원문, 역할 라벨, 요청 라벨, 메타 설명은 절대 출력하지 마세요. "
    "답변은 말풍선 하나당 800토큰 이내로 작성하세요. 길어지면 문장 단위로 자연스럽게 끊고 다음 말풍선에서 이어갈 수 있게 마무리하세요."
)
CHAT_CONTINUE_PROMPT = "이전 답변이 아직 끝나지 않았습니다. 이전 내용을 반복하지 말고 바로 이어서 답변하세요."
CHAT_MEMORY_SUMMARY_CHAR_LIMIT = 1800
CHAT_SUMMARY_TRIGGER_MESSAGES = 16
CHAT_SUMMARY_BATCH_LIMIT = 24
RAILWAY_PUBLIC_BASE_URL = os.environ.get("FINGERFRUIT_PUBLIC_BASE_URL", "https://web-production-011c4.up.railway.app").rstrip("/")
RELEASE_NOTES = [
    "로그인 화면 상단에 FingerForest 로고를 추가하고 로그인 카드를 아래로 내려 배경 여백을 정리했습니다.",
    "열매 자동전송 대상을 여러 명 추가해 순서대로 순환 전송할 수 있게 했고, 사이클 카드에서 X 버튼으로 개별 제외할 수 있습니다.",
    "씨앗선물 받은 내역은 5분 체크에서 열매 +3 증가가 새로 잡힌 그 시각을 표시합니다.",
    "로그인 화면 제목 옆 마스코트 아이콘을 제거하고 시작 캐릭터 낙하 애니메이션을 더 부드럽게 조정했습니다.",
    "메인 화면 배경을 첨부받은 고화질 봄/여름/가을/겨울 이미지로 교체했습니다.",
    "승인된 업무일지 팝업에서 기존 전송 기록에 본문이 없으면 저장된 업무 내용을 보강해 표시합니다.",
    "씨앗선물 수신 내역은 열매 증가가 5분 체크에서 새로 잡힌 시각을 우선 표시합니다.",
    "기존 씨앗선물 내역은 확실한 관측 시간이 없으면 받음/보냄만 표시합니다.",
    "당일 날짜 선택과 오늘 예약 시간 보정 로직을 안정화했습니다.",
    "시작 화면 FingerForest 표기와 캐릭터 첫 프레임 표시를 반영했습니다.",
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
        "chat_messages_table": os.environ.get("SUPABASE_CHAT_MESSAGES_TABLE")
        or config.get("chatMessagesTable")
        or "fruit_chat_messages",
        "chat_memories_table": os.environ.get("SUPABASE_CHAT_MEMORIES_TABLE")
        or config.get("chatMemoriesTable")
        or "fruit_chat_memories",
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
    for item in state.get("targetCycle") or []:
        if isinstance(item, dict):
            employee_ids.append(item.get("emp_id") or item.get("targetEmployeeId"))
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
    cycle = []
    for item in state.get("targetCycle") or []:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        profile = photos.get(str(next_item.get("emp_id") or ""))
        next_item["profilePhotoUrl"] = profile.get("url") if profile else ""
        cycle.append(next_item)
    state["targetCycle"] = cycle
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


def chat_user_identity(owner_key):
    state = fruit_auto.get_account_state(owner_key)
    employee_id = str(state.get("senderEmployeeId") or state.get("loginUserId") or "").strip()
    if employee_id:
        user_key = employee_id
    else:
        user_key = "owner-" + hashlib.sha256(str(owner_key or "").encode("utf-8")).hexdigest()[:24]
    name = str(state.get("senderEmployeeName") or state.get("loginUser") or user_key).strip()
    return user_key, name


def chat_sqlite_conn():
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        create table if not exists fruit_chat_messages (
          id integer primary key autoincrement,
          user_key text not null,
          role text not null check (role in ('user', 'assistant')),
          content text not null,
          model text,
          created_at text not null,
          metadata text not null default '{}'
        )
        """
    )
    conn.execute(
        """
        create table if not exists fruit_chat_memories (
          user_key text primary key,
          summary text not null default '',
          summarized_message_id integer,
          updated_at text not null
        )
        """
    )
    conn.execute("create index if not exists idx_fruit_chat_messages_user_created on fruit_chat_messages(user_key, created_at desc)")
    conn.execute("create index if not exists idx_fruit_chat_messages_user_id on fruit_chat_messages(user_key, id)")
    return conn


def chat_insert_local(user_key, role, content, model="", metadata=None):
    with chat_sqlite_conn() as conn:
        conn.execute(
            """
            insert into fruit_chat_messages(user_key, role, content, model, created_at, metadata)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                user_key,
                role,
                content,
                model or "",
                fruit_auto.now_iso(),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )


def chat_recent_local(user_key, limit=CHAT_CONTEXT_MESSAGE_LIMIT):
    with chat_sqlite_conn() as conn:
        rows = conn.execute(
            """
            select id, role, content, model, created_at
            from fruit_chat_messages
            where user_key = ?
            order by id desc
            limit ?
            """,
            (user_key, int(limit)),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def chat_memory_local(user_key):
    with chat_sqlite_conn() as conn:
        row = conn.execute(
            "select summary, summarized_message_id from fruit_chat_memories where user_key = ?",
            (user_key,),
        ).fetchone()
    if not row:
        return {"summary": "", "summarizedMessageId": 0}
    return {"summary": row["summary"] or "", "summarizedMessageId": int(row["summarized_message_id"] or 0)}


def chat_update_memory_local(user_key, summary, summarized_message_id):
    with chat_sqlite_conn() as conn:
        conn.execute(
            """
            insert into fruit_chat_memories(user_key, summary, summarized_message_id, updated_at)
            values (?, ?, ?, ?)
            on conflict(user_key) do update set
              summary = excluded.summary,
              summarized_message_id = excluded.summarized_message_id,
              updated_at = excluded.updated_at
            """,
            (user_key, summary, summarized_message_id, fruit_auto.now_iso()),
        )


def chat_unsummarized_local(user_key, after_id, limit=CHAT_SUMMARY_BATCH_LIMIT):
    with chat_sqlite_conn() as conn:
        rows = conn.execute(
            """
            select id, role, content, model, created_at
            from fruit_chat_messages
            where user_key = ? and id > ?
            order by id asc
            limit ?
            """,
            (user_key, int(after_id or 0), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def chat_insert_supabase(user_key, name, role, content, model="", metadata=None):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    table = urllib.parse.quote(config["chat_messages_table"], safe="")
    row = {
        "user_key": user_key,
        "name": name,
        "role": role,
        "content": content,
        "model": model or "",
        "metadata": metadata or {},
        "created_at": fruit_auto.now_iso(),
    }
    supabase_request("POST", f"/rest/v1/{table}", body=row, extra_headers={"Prefer": "return=minimal"})


def chat_recent_supabase(user_key, limit=CHAT_CONTEXT_MESSAGE_LIMIT):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    table = urllib.parse.quote(config["chat_messages_table"], safe="")
    quoted_key = urllib.parse.quote(user_key, safe="")
    rows = supabase_request(
        "GET",
        f"/rest/v1/{table}?select=id,role,content,model,created_at&user_key=eq.{quoted_key}&order=id.desc&limit={int(limit)}",
        content_type=None,
    ) or []
    return list(reversed(rows))


def chat_memory_supabase(user_key):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    table = urllib.parse.quote(config["chat_memories_table"], safe="")
    quoted_key = urllib.parse.quote(user_key, safe="")
    rows = supabase_request(
        "GET",
        f"/rest/v1/{table}?select=summary,summarized_message_id&user_key=eq.{quoted_key}&limit=1",
        content_type=None,
    ) or []
    if not rows:
        return {"summary": "", "summarizedMessageId": 0}
    row = rows[0]
    return {"summary": row.get("summary") or "", "summarizedMessageId": int(row.get("summarized_message_id") or 0)}


def chat_update_memory_supabase(user_key, name, summary, summarized_message_id):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    table = urllib.parse.quote(config["chat_memories_table"], safe="")
    row = {
        "user_key": user_key,
        "name": name,
        "summary": summary,
        "summarized_message_id": int(summarized_message_id or 0),
        "updated_at": fruit_auto.now_iso(),
    }
    supabase_request(
        "POST",
        f"/rest/v1/{table}",
        body=row,
        extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
    )


def chat_unsummarized_supabase(user_key, after_id, limit=CHAT_SUMMARY_BATCH_LIMIT):
    config = supabase_config()
    if not config:
        raise fruit_auto.FruitAutoError("Supabase 설정이 없습니다.")
    table = urllib.parse.quote(config["chat_messages_table"], safe="")
    quoted_key = urllib.parse.quote(user_key, safe="")
    rows = supabase_request(
        "GET",
        (
            f"/rest/v1/{table}?select=id,role,content,model,created_at"
            f"&user_key=eq.{quoted_key}&id=gt.{int(after_id or 0)}&order=id.asc&limit={int(limit)}"
        ),
        content_type=None,
    ) or []
    return rows


def save_chat_message(owner_key, role, content, model="", metadata=None):
    user_key, name = chat_user_identity(owner_key)
    content = clean_chat_text(content, CHAT_INPUT_CHAR_LIMIT)
    if role not in ("user", "assistant") or not content:
        return
    try:
        chat_insert_supabase(user_key, name, role, content, model, metadata)
    except Exception:
        chat_insert_local(user_key, role, content, model, metadata)


def load_chat_context(owner_key):
    user_key, _name = chat_user_identity(owner_key)
    try:
        recent = chat_recent_supabase(user_key, CHAT_CONTEXT_MESSAGE_LIMIT)
        memory = chat_memory_supabase(user_key)
    except Exception:
        recent = chat_recent_local(user_key, CHAT_CONTEXT_MESSAGE_LIMIT)
        memory = chat_memory_local(user_key)
    return {
        "recent": [
            {"role": row.get("role"), "content": row.get("content") or ""}
            for row in recent
            if row.get("role") in ("user", "assistant") and row.get("content")
        ],
        "memorySummary": clean_chat_text(memory.get("summary"), CHAT_MEMORY_SUMMARY_CHAR_LIMIT),
    }


def summarize_chat_memory(existing_summary, rows, api_key):
    lines = []
    for row in rows:
        role = "사용자" if row.get("role") == "user" else "assistant"
        content = clean_chat_text(row.get("content"), 1200)
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return existing_summary
    prompt = (
        "아래 대화에서 장기 기억으로 남길 사용자 선호, 결정, 반복 기준, 프로젝트 맥락만 한국어로 짧게 요약하세요. "
        "일회성 잡담, 비밀값, 원문 토큰, 인증정보는 저장하지 마세요. 기존 요약과 합쳐 1200자 이내로 유지하세요.\n\n"
        f"기존 요약:\n{existing_summary or '(없음)'}\n\n"
        "새 대화:\n" + "\n".join(lines)
    )
    request_body = json.dumps(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 500,
            "system": "사용자의 장기 기억 메모리를 안전하고 간결하게 정리합니다.",
            "messages": [{"role": "user", "content": prompt}],
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
    with urllib.request.urlopen(request, timeout=35) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data.get("content") if isinstance(data, dict) else []
    text = "\n".join(
        str(part.get("text") or "")
        for part in content
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
    ).strip()
    return clean_chat_text(text or existing_summary, CHAT_MEMORY_SUMMARY_CHAR_LIMIT)


def maybe_update_chat_memory(owner_key, api_key):
    if not api_key:
        return
    user_key, name = chat_user_identity(owner_key)
    try:
        memory = chat_memory_supabase(user_key)
        rows = chat_unsummarized_supabase(user_key, memory.get("summarizedMessageId"), CHAT_SUMMARY_BATCH_LIMIT)
        update_remote = True
    except Exception:
        memory = chat_memory_local(user_key)
        rows = chat_unsummarized_local(user_key, memory.get("summarizedMessageId"), CHAT_SUMMARY_BATCH_LIMIT)
        update_remote = False
    if len(rows) < CHAT_SUMMARY_TRIGGER_MESSAGES:
        return
    try:
        summary = summarize_chat_memory(memory.get("summary") or "", rows, api_key)
    except Exception:
        return
    summarized_id = max(int(row.get("id") or 0) for row in rows)
    try:
        if update_remote:
            chat_update_memory_supabase(user_key, name, summary, summarized_id)
        else:
            chat_update_memory_local(user_key, summary, summarized_id)
    except Exception:
        chat_update_memory_local(user_key, summary, summarized_id)


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
    state["targetCycleCount"] = len(state.get("targetCycle") or [])
    state["daemonRunning"] = ensure_daemon_running()
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


def clean_chat_reply(value):
    text = str(value or "").strip()
    if not text:
        return ""
    blocked_prefixes = (
        "시스템 지시",
        "DB 장기 기억",
        "DB 최근 대화",
        "사용자 질문:",
        "이어쓰기 요청:",
        "assistant:",
        "Assistant:",
        "사용자:",
    )
    blocked_fragments = (
        "답변은 말풍선 하나당",
        "800토큰 이내",
        "최근 대화:",
        "장기 기억 요약",
        "구글 캘린더에 추가",
        "캘린더에 추가했",
    )
    lines = []
    skipping_block = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if any(line.startswith(prefix) for prefix in blocked_prefixes) or any(fragment in line for fragment in blocked_fragments):
            skipping_block = True
            continue
        if skipping_block and (line.startswith("- ") or line.startswith("• ") or line.startswith("{") or line.startswith("}")):
            continue
        skipping_block = False
        lines.append(raw_line)
    cleaned = "\n".join(lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def strip_html(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def chat_needs_web_search(message):
    text = str(message or "").lower()
    explicit_search_words = ("검색", "찾아", "찾아봐", "찾아줘", "확인해", "알아봐")
    if any(keyword in text for keyword in explicit_search_words):
        return True
    return bool(re.search(r"\b20\d{2}[./-]\d{1,2}[./-]\d{1,2}\b", text))


def chat_reply_needs_web_retry(reply):
    text = str(reply or "")
    blocked_phrases = (
        "실시간 뉴스",
        "최신 선거 결과에 접근할 수",
        "실시간 날씨",
        "실시간 정보",
        "최신 정보",
        "접근할 수 없습니다",
        "확인할 수 없습니다",
        "알 수 없습니다",
        "제공할 수 없습니다",
        "방문하시면",
        "공식 웹사이트",
        "주요 언론사",
        "날씨 앱",
        "포털 사이트",
    )
    return any(phrase in text for phrase in blocked_phrases)


def extract_chat_search_query(reply):
    match = CHAT_SEARCH_SIGNAL_RE.search(str(reply or ""))
    if not match:
        return ""
    query = strip_html(match.group(1))
    return clean_chat_text(query, 300)


def google_news_search(query, limit=CHAT_SEARCH_RESULT_LIMIT):
    params = urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    request = urllib.request.Request(
        f"https://news.google.com/rss/search?{params}",
        headers={"User-Agent": "Mozilla/5.0 FingerForest/1.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        root = ET.fromstring(response.read())
    results = []
    for item in root.findall("./channel/item")[:limit]:
        title = strip_html(item.findtext("title"))
        link = strip_html(item.findtext("link"))
        published = strip_html(item.findtext("pubDate"))
        description = strip_html(item.findtext("description"))
        if title and link:
            results.append(
                {
                    "title": title,
                    "url": link,
                    "published": published,
                    "snippet": description[:350],
                    "source": "Google News",
                }
            )
    return results


def bing_web_search(query, limit=CHAT_SEARCH_RESULT_LIMIT):
    params = urllib.parse.urlencode({"q": query, "setlang": "ko-KR", "cc": "KR"})
    request = urllib.request.Request(
        f"https://www.bing.com/search?{params}",
        headers={"User-Agent": "Mozilla/5.0 FingerForest/1.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        page = response.read().decode("utf-8", errors="replace")
    results = []
    blocks = re.findall(r'<li class="b_algo".*?</li>', page, flags=re.S)
    for block in blocks:
        title_match = re.search(r"<h2.*?<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", block, flags=re.S)
        if not title_match:
            continue
        url = html.unescape(title_match.group(1))
        title = strip_html(title_match.group(2))
        snippet_match = re.search(r"<p>(.*?)</p>", block, flags=re.S)
        snippet = strip_html(snippet_match.group(1)) if snippet_match else ""
        if title and url:
            results.append({"title": title, "url": url, "published": "", "snippet": snippet[:350], "source": "Bing"})
        if len(results) >= limit:
            break
    return results


def build_search_query(message):
    return clean_chat_text(message, 300)


def web_search_results(message):
    query = build_search_query(message)
    results = []
    errors = []
    for searcher in (google_news_search, bing_web_search):
        try:
            for item in searcher(query):
                if not any(existing.get("url") == item.get("url") for existing in results):
                    results.append(item)
                if len(results) >= CHAT_SEARCH_RESULT_LIMIT:
                    break
        except Exception as exc:
            errors.append(sanitize_error(exc))
        if len(results) >= CHAT_SEARCH_RESULT_LIMIT:
            break
    fruit_auto.log_event(
        {
            "action": "chat_web_search",
            "query": query,
            "resultCount": len(results),
            "errors": errors[:2],
        }
    )
    return {"query": query, "results": results, "errors": errors}


def format_search_context(search_data):
    results = search_data.get("results") if isinstance(search_data, dict) else []
    if not results:
        return ""
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    lines = [
        f"현재 시각: {now}",
        f"검색어: {search_data.get('query') or ''}",
        "아래 검색 결과를 최신 정보 근거로 사용하세요. 결과만으로 단정하기 어려우면 불확실하다고 말하고, 사용자가 직접 방문하라는 식으로 떠넘기지 마세요.",
    ]
    for index, item in enumerate(results, 1):
        lines.append(
            "\n".join(
                [
                    f"{index}. 제목: {item.get('title') or ''}",
                    f"   출처: {item.get('source') or ''}",
                    f"   게시: {item.get('published') or ''}",
                    f"   링크: {item.get('url') or ''}",
                    f"   요약: {item.get('snippet') or ''}",
                ]
            )
        )
    return "\n".join(lines)


def chat_reply_looks_incomplete(reply):
    text = str(reply or "").strip()
    if not text:
        return False
    if text.endswith((".", "!", "?", "。", "！", "？", "…", "다.", "요.", "함.", "음.", "습니다.")):
        return False
    incomplete_endings = (
        "따르면",
        "한편",
        "그리고",
        "또한",
        "반면",
        "이에",
        "그러나",
        "때문에",
        "에서",
        "으로",
        "라고",
        "하며",
        "하고",
        "따라",
        "관련해",
    )
    return len(text) >= 500 or text.endswith(incomplete_endings)


def build_chat_system_prompt(memory_summary="", search_context=""):
    parts = [CHAT_REPLY_INSTRUCTION]
    if not search_context:
        parts.append(
            "당신은 서버 검색 기능을 사용할 수 있는 AI처럼 행동합니다. "
            "사용자의 질문에 답하려면 최신 정보, 실시간 상태, 위치 기반 정보, 가격, 영업시간, 뉴스, 날씨, 선거 결과, 맛집 후기처럼 외부 확인이 필요하거나 스스로 확실히 모르는 내용이라면 답을 추측하지 마세요. "
            "그 경우 사용자에게 사이트를 방문하라고 안내하지 말고, 답변 대신 정확히 [[SEARCH: 검색어]] 형식 한 줄만 출력하세요. "
            "검색이 필요 없는 일반 지식, 계산, 글쓰기, 앱 사용 안내는 바로 답하세요."
        )
    if memory_summary:
        parts.append(
            "아래는 DB에 저장된 장기 기억 요약입니다. 현재 질문과 관련 있을 때만 참고하고, 관련 없으면 억지로 언급하지 마세요.\n"
            f"{memory_summary}"
        )
    if search_context:
        parts.append(
            "아래는 서버가 수집한 검색 결과입니다. 이 자료를 근거로 사용자의 질문에 답하세요. "
            "검색 결과가 있으면 '실시간 접근 불가', '확인할 수 없음', '사이트를 방문하세요'라고 답하지 마세요. "
            "결과가 부족하거나 서로 충돌하면 그 한계를 짧게 밝힌 뒤 검색 결과 기준으로 정리하세요.\n"
            f"{search_context}"
        )
    return "\n\n".join(parts)


def chat_result_from_replies(replies, model, stop_reason=None):
    return {
        "reply": "\n\n".join(replies),
        "replies": replies,
        "model": model,
        "continued": len(replies) > 1,
        "stopReason": stop_reason or "",
    }


def build_anthropic_messages(message, history):
    messages = []
    remaining_input = max(0, CHAT_INPUT_CHAR_LIMIT - len(message))
    if isinstance(history, list):
        for item in history[-CHAT_CONTEXT_MESSAGE_LIMIT:]:
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
    return messages


def anthropic_claude_chat(message, history, api_key, memory_summary="", search_context=""):
    messages = build_anthropic_messages(message, history)
    replies = []
    model = CLAUDE_MODEL
    stop_reason = ""
    system_prompt = build_chat_system_prompt(memory_summary, search_context)
    for index in range(CHAT_MAX_CONTINUATIONS + 1):
        request_body = json.dumps(
            {
                "model": CLAUDE_MODEL,
                "max_tokens": CHAT_OUTPUT_TOKEN_LIMIT,
                "system": system_prompt,
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
        reply = clean_chat_reply("\n".join(text_parts))
        if not reply:
            raise fruit_auto.FruitAutoError("Claude 응답이 비어 있습니다.")
        replies.append(reply)
        model = data.get("model") or model
        stop_reason = data.get("stop_reason") or ""
        if stop_reason != "max_tokens" or index >= CHAT_MAX_CONTINUATIONS:
            break
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": CHAT_CONTINUE_PROMPT})
    return chat_result_from_replies(replies, model, stop_reason)


def claude_chat(payload, owner_key):
    api_key = claude_api_key()
    message = clean_chat_text(payload.get("message"))
    if not message:
        raise fruit_auto.FruitAutoError("메시지를 입력하세요.")
    context = load_chat_context(owner_key)
    history = context["recent"] or payload.get("history")
    memory_summary = context["memorySummary"]
    save_chat_message(owner_key, "user", message, metadata={"source": "FingerForest"})
    result = None
    search_data = None
    search_context = ""
    search_used = False
    if api_key:
        try:
            result = anthropic_claude_chat(
                message,
                history,
                api_key,
                memory_summary=memory_summary,
                search_context=search_context,
            )
            search_query = extract_chat_search_query(result.get("reply") or "")
            if not search_query and (chat_needs_web_search(message) or chat_reply_needs_web_retry(result.get("reply") or "")):
                search_query = message
            if search_query:
                search_data = web_search_results(search_query)
                search_context = format_search_context(search_data)
                if search_context:
                    search_used = True
                    result = anthropic_claude_chat(
                        message,
                        history,
                        api_key,
                        memory_summary=memory_summary,
                        search_context=search_context,
                    )
        except Exception as exc:
            fruit_auto.log_event({"action": "chat_anthropic_direct_failed", "error": sanitize_error(exc)})
    else:
        fruit_auto.log_event({"action": "chat_anthropic_key_missing"})
    if result is None:
        result = chat_result_from_replies(
            ["Claude 직접 연결이 아직 준비되지 않았습니다. 잠시 후 다시 시도해주세요."],
            "claude-direct-unavailable",
            "direct_unavailable",
        )
        result["direct"] = False
    else:
        result["direct"] = True
        for reply in result.get("replies") or [result.get("reply") or ""]:
            save_chat_message(
                owner_key,
                "assistant",
                reply,
                model=result.get("model") or "",
                metadata={
                    "source": "anthropic-direct",
                    "webSearch": search_used,
                    "searchQuery": (search_data or {}).get("query") or "",
                },
            )
        maybe_update_chat_memory(owner_key, api_key)
    result["memory"] = {
        "recentMessageLimit": CHAT_CONTEXT_MESSAGE_LIMIT,
        "summaryUsed": bool(memory_summary),
    }
    result["webSearch"] = {
        "used": search_used,
        "query": (search_data or {}).get("query") or "",
        "resultCount": len((search_data or {}).get("results") or []),
    }
    return result


def daemon_running():
    if not fruit_auto.PID_PATH.exists():
        return False
    try:
        pid = int(fruit_auto.PID_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return fruit_auto.is_process_alive(pid)


def tick_worker_running():
    try:
        data = json.loads(TICK_HEARTBEAT_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid"))
        interval = int(data.get("intervalSeconds") or 60)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    try:
        age = datetime.now(timezone.utc).timestamp() - TICK_HEARTBEAT_PATH.stat().st_mtime
    except OSError:
        return False
    return age <= max(180, interval * 3) and fruit_auto.is_process_alive(pid)


def start_tick_worker():
    if tick_worker_running():
        return True
    try:
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "tick_worker.py")],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except OSError:
        return False


def request_scheduler_wake():
    start_tick_worker()
    try:
        TICK_WAKE_PATH.write_text(datetime.now(timezone.utc).isoformat() + "\n", encoding="utf-8")
    except OSError:
        return wake_daemon()
    return True


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
    return tick_worker_running() or start_tick_worker() or daemon_running()


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
                elif parsed.path == "/api/worklog-approvals":
                    owner_key, _session_token = self.require_session_owner()
                    params = urllib.parse.parse_qs(parsed.query)
                    selected_month = (params.get("month") or [""])[0]
                    self.send_json(200, {"ok": True, "result": fruit_auto.worklog_approvals(owner_key=owner_key, month=selected_month)})
                elif parsed.path == "/api/worklog-approvals-local":
                    owner_key, _session_token = self.require_session_owner()
                    params = urllib.parse.parse_qs(parsed.query)
                    selected_month = (params.get("month") or [""])[0]
                    self.send_json(200, {"ok": True, "result": fruit_auto.worklog_approvals_local(owner_key=owner_key, month=selected_month)})
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
            elif parsed.path == "/api/target-remove":
                fruit_auto.remove_cycle_target(payload.get("emp_id"), owner_key=owner_key)
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
                request_scheduler_wake()
                result = state_response(owner_key)
            elif parsed.path == "/api/worklog-run-now":
                result = fruit_auto.save_worklog_once(owner_key=owner_key, force=True)
                fruit_auto.notify_result(result)
                result = {**result, "state": state_response(owner_key)}
            elif parsed.path == "/api/interval":
                fruit_auto.set_run_interval(payload.get("minutes"), owner_key=owner_key)
                request_scheduler_wake()
                result = state_response(owner_key)
            elif parsed.path == "/api/refresh":
                fruit_auto.refresh_balance(force=True, owner_key=owner_key)
                result = state_response(owner_key)
            elif parsed.path == "/api/on":
                if payload.get("target_name"):
                    fruit_auto.set_target_by_name(payload.get("target_name"))
                fruit_auto.set_enabled(True, owner_key=owner_key)
                request_scheduler_wake()
                result = state_response(owner_key)
            elif parsed.path == "/api/off":
                fruit_auto.set_enabled(False, owner_key=owner_key)
                request_scheduler_wake()
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
