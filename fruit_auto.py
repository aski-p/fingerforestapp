#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import random
import re
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FRUIT_AUTO_DATA_DIR") or BASE_DIR).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA_DIR / "state.json"
SECRETS_PATH = DATA_DIR / "secrets.json"
LOG_PATH = DATA_DIR / "runs.log"
HISTORY_PATH = DATA_DIR / "history.log"
HISTORY_OBSERVATIONS_PATH = DATA_DIR / "history_observations.sqlite3"
PID_PATH = DATA_DIR / "daemon.pid"
TICK_LOCK_PATH = DATA_DIR / "tick.lock"
TICK_CURSOR_PATH = DATA_DIR / "tick_cursor.json"
WEB_PUSH_SCRIPT_PATH = BASE_DIR / "send_web_push.js"
DEFAULT_TICK_MAX_SECONDS = 240
DEFAULT_TICK_MAX_OWNERS = 50
DEFAULT_RUN_INTERVAL_MINUTES = 60
MIN_RUN_INTERVAL_MINUTES = 60
MAX_RUN_INTERVAL_MINUTES = 23 * 60
RUN_INTERVAL_RANDOM_EXTRA_MINUTES = 59
COMMON_OBSERVE_INTERVAL_SECONDS = 5 * 60
WAKE_REQUESTED = False
QUIET_LOG_ACTIONS = {"balance", "check"}
SESSION_SCHEMA_VERSION = 4
SESSION_TTL_SECONDS = 60 * 60
KST = dt.timezone(dt.timedelta(hours=9))

PMS_LOGIN_PAGE = "http://pms.fingerservice.co.kr/tms/login"
PMS_LOGIN_API = "http://pms.fingerservice.co.kr/tms/v1/common/login"
FOREST_API = "https://forest2.fingerservice.co.kr/api/v1/dw"

DEFAULT_STATE = {
    "enabled": False,
    "status": "off",
    "targetEmployeeName": None,
    "targetEmployeeId": None,
    "targetCycle": [],
    "targetCycleIndex": 0,
    "lastCheckedAt": None,
    "lastSentAt": None,
    "lastSeedCount": None,
    "lastBerryCount": None,
    "balanceCheckedAt": None,
    "lastResult": None,
    "lastAttemptAt": None,
    "lastAttemptSlot": None,
    "lastAttemptResult": None,
    "lastNoBerriesAt": None,
    "lastNoBerriesLogAt": None,
    "lastCommonObservedAt": None,
    "lastCommonObserveResult": None,
    "pendingReceivedAt": None,
    "pendingEligibleAt": None,
    "pendingBerryCount": None,
    "pendingTargetEmployeeId": None,
    "nextRunAt": None,
    "ownerKey": None,
    "senderEmployeeId": None,
    "senderEmployeeName": None,
    "giftMessage": "자동 전달",
    "sendBerryCount": 1,
    "sendAllBerries": False,
    "runIntervalMinutes": DEFAULT_RUN_INTERVAL_MINUTES,
    "pushEnabled": True,
    "worklogEnabled": False,
    "worklogScheduleDays": [],
    "worklogScheduleDates": [],
    "worklogScheduleTime": "09:05",
    "worklogTargetEmployeeName": None,
    "worklogTargetEmployeeId": None,
    "worklogTargetDutyId": None,
    "worklogTargetDeptName": None,
    "worklogTargetPositionName": None,
    "worklogSeedCount": 3,
    "worklogSeedMessage": "감사합니다",
    "worklogProjectId": None,
    "worklogProjectName": None,
    "worklogContent": "",
    "worklogNextRunAt": None,
    "worklogScheduleUpdatedAt": None,
    "worklogLastRunAt": None,
    "worklogLastRunKey": None,
    "worklogRunningRunKey": None,
    "worklogRunningAt": None,
    "worklogLastResult": None,
    "worklogLastError": None,
}

KOREAN_PUBLIC_HOLIDAYS = {
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
}


class FruitAutoError(RuntimeError):
    pass


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def current_run_slot():
    return int(time.time() // get_run_interval_seconds())


def get_run_interval_minutes(state=None):
    state = state or load_json(STATE_PATH, DEFAULT_STATE)
    try:
        minutes = int(state.get("runIntervalMinutes") or DEFAULT_RUN_INTERVAL_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_RUN_INTERVAL_MINUTES
    return max(MIN_RUN_INTERVAL_MINUTES, min(MAX_RUN_INTERVAL_MINUTES, minutes))


def get_run_interval_seconds(state=None):
    return get_run_interval_minutes(state) * 60


def random_run_delay_seconds(state=None):
    base_minutes = get_run_interval_minutes(state)
    extra_minutes = random.randint(1, RUN_INTERVAL_RANDOM_EXTRA_MINUTES)
    return (base_minutes + extra_minutes) * 60


def schedule_next_run(state, base=None):
    delay_seconds = random_run_delay_seconds(state)
    state["nextRunDelaySeconds"] = delay_seconds
    state["nextRunAt"] = iso_after(delay_seconds, base)
    return delay_seconds


def get_history_observe_interval_seconds():
    return COMMON_OBSERVE_INTERVAL_SECONDS


def get_send_berry_count(state=None):
    state = state or load_json(STATE_PATH, DEFAULT_STATE)
    try:
        count = int(state.get("sendBerryCount") or DEFAULT_STATE["sendBerryCount"])
    except (TypeError, ValueError):
        count = DEFAULT_STATE["sendBerryCount"]
    return max(1, count)


def get_send_all_berries(state=None):
    state = state or load_json(STATE_PATH, DEFAULT_STATE)
    return bool(state.get("sendAllBerries"))


def validate_transfer_settings(state):
    target, _cycle, _index = target_from_cycle(state)
    if not target.get("emp_id") or not target.get("emp_nm"):
        raise FruitAutoError("자동전송 받을 직원을 선택해 주세요.")
    if not str(state.get("giftMessage") or "").strip():
        raise FruitAutoError("메시지를 작성해주세요.")
    if not get_send_all_berries(state) and get_send_berry_count(state) <= 0:
        raise FruitAutoError("보낼 열매 수를 작성해주세요.")


def seconds_since(value):
    if not value:
        return None
    try:
        checked = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.datetime.now(dt.timezone.utc) - checked).total_seconds()


def parse_iso(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def iso_after(seconds, base=None):
    base = base or dt.datetime.now(dt.timezone.utc)
    return (base + dt.timedelta(seconds=max(0, int(seconds)))).replace(microsecond=0).isoformat()


def employee_identity(employee, fallback_user_id=None):
    emp_id = employee.get("emp_id")
    emp_name = employee.get("emp_nm")
    key = f"forest:{emp_id}" if emp_id else f"pms:{fallback_user_id}" if fallback_user_id else None
    return key, emp_id, emp_name


def employee_position(employee):
    return (
        employee.get("pos_nm")
        or employee.get("duty_nm")
        or employee.get("positionName")
        or employee.get("targetPositionName")
    )


def display_employee(name, position=None, fallback=None):
    safe_name = str(name or fallback or "").strip()
    safe_position = str(position or "").strip()
    if safe_name and safe_position:
        return f"{safe_name} {safe_position}"
    return safe_name


def employee_record(emp_id=None, name=None, duty_id=None, dept_nm=None, pos_nm=None, source=None):
    source = source or {}
    return {
        "emp_id": str(emp_id or source.get("emp_id") or source.get("targetEmployeeId") or "").strip(),
        "emp_nm": str(name or source.get("emp_nm") or source.get("targetEmployeeName") or "").strip(),
        "duty_id": str(duty_id or source.get("duty_id") or source.get("targetDutyId") or "").strip(),
        "dept_nm": str(dept_nm or source.get("dept_nm") or source.get("targetDeptName") or "").strip(),
        "pos_nm": str(pos_nm or source.get("pos_nm") or source.get("targetPositionName") or "").strip(),
    }


def normalize_target_cycle(state):
    state = state or {}
    raw_cycle = state.get("targetCycle") if isinstance(state.get("targetCycle"), list) else []
    cycle = []
    seen = set()
    for item in raw_cycle:
        if not isinstance(item, dict):
            continue
        record = employee_record(source=item)
        emp_id = record.get("emp_id")
        if not emp_id or emp_id in seen:
            continue
        cycle.append(record)
        seen.add(emp_id)
    legacy = employee_record(
        state.get("targetEmployeeId"),
        state.get("targetEmployeeName"),
        state.get("targetDutyId"),
        state.get("targetDeptName"),
        state.get("targetPositionName"),
    )
    if legacy.get("emp_id") and legacy.get("emp_id") not in seen:
        cycle.insert(0, legacy)
    current_id = str(state.get("targetEmployeeId") or "")
    try:
        index = int(state.get("targetCycleIndex") or 0)
    except (TypeError, ValueError):
        index = 0
    if current_id:
        for item_index, item in enumerate(cycle):
            if item.get("emp_id") == current_id:
                index = item_index
                break
    if cycle:
        index %= len(cycle)
    else:
        index = 0
    return cycle, index


def target_from_cycle(state):
    cycle, index = normalize_target_cycle(state)
    if cycle:
        return cycle[index], cycle, index
    return employee_record(
        state.get("targetEmployeeId"),
        state.get("targetEmployeeName"),
        state.get("targetDutyId"),
        state.get("targetDeptName"),
        state.get("targetPositionName"),
    ), [], 0


def apply_cycle_target(state, target=None, cycle=None, index=None):
    target = target or {}
    if cycle is None or index is None:
        target, cycle, index = target_from_cycle({**(state or {}), **target})
    state["targetCycle"] = cycle or []
    state["targetCycleIndex"] = index or 0
    state["targetEmployeeId"] = target.get("emp_id") or None
    state["targetEmployeeName"] = target.get("emp_nm") or None
    state["targetDutyId"] = target.get("duty_id") or None
    state["targetDeptName"] = target.get("dept_nm") or None
    state["targetPositionName"] = target.get("pos_nm") or None
    return state


def advance_target_cycle(state):
    cycle, index = normalize_target_cycle(state)
    if not cycle:
        return state
    next_index = (index + 1) % len(cycle)
    return apply_cycle_target(state, cycle[next_index], cycle, next_index)


def load_json(path, default):
    if path == STATE_PATH and not path.exists() and os.environ.get("FRUIT_AUTO_STATE_JSON"):
        try:
            data = json.loads(os.environ["FRUIT_AUTO_STATE_JSON"])
            save_json(path, data)
        except (TypeError, json.JSONDecodeError):
            pass
    elif path == SECRETS_PATH and not path.exists() and os.environ.get("FRUIT_AUTO_SECRETS_JSON"):
        try:
            data = json.loads(os.environ["FRUIT_AUTO_SECRETS_JSON"])
            save_json(path, data)
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except (TypeError, json.JSONDecodeError):
            pass
    if not path.exists():
        return dict(default)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    merged = dict(default)
    merged.update(data)
    return merged


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def log_event(event):
    event = dict(event)
    if should_skip_log_event(event):
        return
    event.setdefault("at", now_iso())
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def should_skip_log_event(event):
    if os.environ.get("FRUIT_AUTO_VERBOSE_LOG") == "1":
        return False
    action = event.get("action")
    if action in QUIET_LOG_ACTIONS:
        return True
    if action == "daemon_tick" and (event.get("result") or {}).get("action") != "sent":
        return True
    return False


def append_jsonl(path, event):
    event = dict(event)
    event.setdefault("at", now_iso())
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def is_transfer_history_event(event):
    action = event.get("action")
    if action not in ("sent", "received"):
        return False
    return (
        event.get("type") == "transfer"
        and bool(event.get("ownerKey"))
        and bool(event.get("targetEmployeeId"))
        and int(event.get("berries") or 0) > 0
    )


def is_seed_transfer_history_event(event):
    action = event.get("action")
    return (
        action in ("sent", "received")
        and event.get("type") == "seed_transfer"
        and bool(event.get("ownerKey"))
        and bool(event.get("targetEmployeeId"))
        and int(event.get("seedDelta") or 0) > 0
    )


def record_transfer_history(event):
    event = dict(event)
    event["type"] = "transfer"
    event.setdefault("action", "sent")
    if not is_transfer_history_event(event):
        raise FruitAutoError("invalid transfer history event")
    append_jsonl(HISTORY_PATH, event)


def record_seed_transfer_history(event):
    event = dict(event)
    event["type"] = "seed_transfer"
    event.setdefault("action", "sent")
    if not is_seed_transfer_history_event(event):
        raise FruitAutoError("invalid seed transfer history event")
    append_jsonl(HISTORY_PATH, event)


def employee_id_from_owner_key(owner_key):
    if not owner_key or not str(owner_key).startswith("forest:"):
        return None
    return str(owner_key).split(":", 1)[1]


def owner_key_for_employee_id(employee_id):
    employee_id = str(employee_id or "")
    if not employee_id:
        return None
    direct_owner_key = f"forest:{employee_id}"
    state = load_all_state()
    for account_key, account in state.get("accounts", {}).items():
        if str(account.get("senderEmployeeId") or "") == employee_id:
            return account_key
        if account_key == direct_owner_key:
            return account_key
    if load_secrets().get("webPushSubscriptions", {}).get(direct_owner_key):
        return direct_owner_key
    return None


def known_employee_name(employee_id=None, owner_key=None):
    state = load_all_state()
    employee_id = str(employee_id or employee_id_from_owner_key(owner_key) or "")
    for account_key, account in state.get("accounts", {}).items():
        if account_key == owner_key:
            return account.get("senderEmployeeName") or account.get("loginUser")
        if employee_id and str(account.get("senderEmployeeId") or "") == employee_id:
            return account.get("senderEmployeeName") or account.get("loginUser")
        if employee_id and str(account.get("targetEmployeeId") or "") == employee_id:
            return account.get("targetEmployeeName")
    return employee_id or owner_key


def infer_target_for_account(owner_key, account=None):
    account = dict(account or get_account_state(owner_key))
    target_id = str(account.get("targetEmployeeId") or "")
    target_name = account.get("targetEmployeeName")
    if target_id and target_name:
        return account
    if account.get("targetLocked"):
        return account

    state = load_all_state()
    my_employee_id = str(
        account.get("senderEmployeeId")
        or account.get("loginUserId")
        or employee_id_from_owner_key(owner_key)
        or ""
    )

    if target_id and not target_name:
        account["targetEmployeeName"] = known_employee_name(target_id)
        return account

    if not target_id and my_employee_id:
        for other_owner_key, other in state.get("accounts", {}).items():
            if other_owner_key == owner_key:
                continue
            if str(other.get("targetEmployeeId") or "") == my_employee_id:
                other_employee_id = (
                    other.get("senderEmployeeId")
                    or employee_id_from_owner_key(other_owner_key)
                    or other.get("loginUserId")
                )
                if other_employee_id:
                    account["targetEmployeeId"] = str(other_employee_id)
                    account["targetEmployeeName"] = (
                        other.get("senderEmployeeName")
                        or other.get("loginUser")
                        or known_employee_name(other_employee_id)
                    )
                    account["targetDeptName"] = account.get("targetDeptName") or other.get("targetDeptName")
                    account["targetPositionName"] = account.get("targetPositionName") or other.get("targetPositionName")
                    return account

    return account


def read_jsonl(path, limit=80):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def read_events(limit=80):
    return read_jsonl(LOG_PATH, limit)


def is_process_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        if ") Z " in stat:
            return False
    except OSError:
        pass
    return True


def claim_daemon_pid():
    if PID_PATH.exists():
        try:
            existing_pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            existing_pid = None
        if existing_pid and is_process_alive(existing_pid):
            raise FruitAutoError(f"daemon already running: pid {existing_pid}")
    PID_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")


def release_daemon_pid():
    try:
        if PID_PATH.exists() and PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_PATH.unlink()
    except OSError:
        pass


def claim_tick_lock():
    if TICK_LOCK_PATH.exists():
        try:
            existing_pid = int(TICK_LOCK_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            existing_pid = None
        if existing_pid and is_process_alive(existing_pid):
            raise FruitAutoError(f"tick already running: pid {existing_pid}")
        try:
            TICK_LOCK_PATH.unlink()
        except OSError:
            pass
    TICK_LOCK_PATH.write_text(f"{os.getpid()}\n", encoding="utf-8")


def release_tick_lock():
    try:
        if TICK_LOCK_PATH.exists() and TICK_LOCK_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            TICK_LOCK_PATH.unlink()
    except OSError:
        pass


def tick_limits():
    try:
        max_seconds = int(os.environ.get("FRUIT_TICK_MAX_SECONDS", DEFAULT_TICK_MAX_SECONDS))
    except ValueError:
        max_seconds = DEFAULT_TICK_MAX_SECONDS
    try:
        max_owners = int(os.environ.get("FRUIT_TICK_MAX_OWNERS", DEFAULT_TICK_MAX_OWNERS))
    except ValueError:
        max_owners = DEFAULT_TICK_MAX_OWNERS
    return max(30, max_seconds), max(1, max_owners)


def rotate_tick_owners(owners):
    owners = list(owners)
    if len(owners) <= 1:
        return owners
    cursor = load_json(TICK_CURSOR_PATH, {})
    last_owner = cursor.get("lastOwnerKey")
    if last_owner not in owners:
        return owners
    index = owners.index(last_owner)
    return owners[index + 1:] + owners[:index + 1]


def save_tick_cursor(owner_key):
    if not owner_key:
        return
    save_json(TICK_CURSOR_PATH, {"lastOwnerKey": owner_key, "updatedAt": now_iso()})


def read_openclaw_config():
    config_path = Path(os.environ.get("OPENCLAW_CONFIG_PATH") or "/home/node/.openclaw/openclaw.json")
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def get_telegram_config():
    token = os.environ.get("FRUIT_AUTO_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("FRUIT_AUTO_TELEGRAM_CHAT_ID")
    if token and chat_id:
        return token, chat_id

    config = read_openclaw_config()
    token = token or ((config.get("channels") or {}).get("telegram") or {}).get("botToken")
    if not chat_id:
        for value in config.get("commands", {}).get("ownerAllowFrom", []):
            if isinstance(value, str) and value.startswith("telegram:"):
                chat_id = value.split(":", 1)[1]
                break
    if not token or not chat_id:
        return None, None
    return token, chat_id


def notify_telegram(message):
    try:
        if load_secrets().get("telegramEnabled") is False:
            log_event({"action": "telegram_notify_skipped", "reason": "telegram_disabled"})
            return False
    except Exception:
        pass

    token, chat_id = get_telegram_config()
    if not token or not chat_id:
        log_event({"action": "telegram_notify_skipped", "reason": "missing_config"})
        return False

    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        if not data.get("ok"):
            raise FruitAutoError(f"telegram send failed: {data}")
        log_event({"action": "telegram_notified"})
        return True
    except Exception as exc:
        log_event({"action": "telegram_notify_error", "error": str(exc)})
        return False


def sent_message_text(result):
    sender = (
        result.get("senderEmployeeName")
        or known_employee_name(owner_key=result.get("ownerKey"))
        or "알 수 없는 사용자"
    )
    target = result.get("target") or known_employee_name(result.get("targetEmployeeId")) or "대상"
    berries = result.get("berries")
    remaining = result.get("remaining")
    return (
        f"{sender}님이 {target}님에게 열매 {berries}개 보냈습니다.\n"
        f"남은 열매는 {remaining}개입니다."
    )


def sent_notification_payload(result):
    sender = (
        result.get("senderEmployeeName")
        or known_employee_name(owner_key=result.get("ownerKey"))
        or "알 수 없는 사용자"
    )
    target = result.get("target") or known_employee_name(result.get("targetEmployeeId")) or "대상"
    berries = result.get("berries")
    remaining = result.get("remaining")
    return {
        "title": "열매 전송 완료",
        "body": f"{sender}님이 {target}님에게 열매 {berries}개 보냈습니다.\n남은 열매는 {remaining}개입니다.",
        "tag": f"fruit-transfer-{result.get('ownerKey')}-{result.get('slot') or int(time.time())}",
        "url": "/",
    }


def received_notification_payload(result):
    sender = (
        result.get("senderEmployeeName")
        or known_employee_name(owner_key=result.get("ownerKey"))
        or "알 수 없는 사용자"
    )
    berries = result.get("berries")
    return {
        "title": "열매 받음",
        "body": f"{sender}님에게 열매 {berries}개를 받았습니다.",
        "tag": f"fruit-received-{result.get('ownerKey')}-{result.get('targetEmployeeId')}-{result.get('slot') or int(time.time())}",
        "url": "/",
    }


def worklog_completed_display(result):
    completed_at = parse_iso(result.get("scheduledFor") or result.get("completedAt") or result.get("at"))
    if completed_at is None:
        completed_at = dt.datetime.now(dt.timezone.utc)
    local_completed = completed_at.astimezone(KST)
    return local_completed.strftime("%Y-%m-%d %H:%M")


def worklog_notification_payload(result):
    completed_display = worklog_completed_display(result)
    run_key = result.get("runKey") or result.get("scheduledFor") or result.get("stdDt") or int(time.time())
    return {
        "title": "업무일지 작성 완료",
        "body": f"{completed_display}에 업무일지 작성을 완료하였습니다.",
        "tag": f"worklog-sent-{result.get('ownerKey')}-{run_key}",
        "url": "/",
    }


def ensure_web_push_keys():
    secrets = load_secrets()
    web_push = secrets.setdefault("webPush", {})
    if web_push.get("publicKey") and web_push.get("privateKey"):
        return web_push
    script = "const webpush=require('web-push'); console.log(JSON.stringify(webpush.generateVAPIDKeys()))"
    try:
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=str(BASE_DIR),
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        keys = json.loads(proc.stdout)
    except Exception as exc:
        raise FruitAutoError(f"web push key generation failed: {exc}") from exc
    web_push["publicKey"] = keys["publicKey"]
    web_push["privateKey"] = keys["privateKey"]
    save_secrets(secrets)
    return web_push


def web_push_public_key():
    return ensure_web_push_keys()["publicKey"]


def save_web_push_subscription(owner_key, subscription):
    owner_key = require_owner(owner_key)
    if not isinstance(subscription, dict) or not subscription.get("endpoint"):
        raise FruitAutoError("유효한 Push 구독 정보가 없습니다.")
    saved_at = now_iso()
    device_id = str(
        subscription.get("deviceId")
        or subscription.get("_fingerfruitDeviceId")
        or ""
    ).strip()
    user_agent = str(subscription.get("userAgent") or "")[:240]
    subscription["updatedAt"] = saved_at
    if "createdAt" not in subscription:
        subscription["createdAt"] = saved_at
    if device_id:
        subscription["deviceId"] = device_id
    if user_agent:
        subscription["userAgent"] = user_agent
    secrets = load_secrets()
    subscriptions = secrets.setdefault("webPushSubscriptions", {})
    endpoint = subscription.get("endpoint")
    for existing_owner_key, existing_subscriptions in subscriptions.items():
        if existing_owner_key == owner_key:
            continue
        existing_subscriptions[:] = [
            item for item in existing_subscriptions
            if item.get("endpoint") != endpoint
            and not (device_id and item.get("deviceId") == device_id)
            and not (device_id and user_agent and not item.get("deviceId") and item.get("userAgent") == user_agent)
        ]
    owner_subscriptions = subscriptions.setdefault(owner_key, [])
    owner_subscriptions[:] = [
        item for item in owner_subscriptions
        if item.get("endpoint") != endpoint
        and not (device_id and item.get("deviceId") == device_id)
        and not (device_id and user_agent and not item.get("deviceId") and item.get("userAgent") == user_agent)
    ]
    owner_subscriptions.append(subscription)
    owner_subscriptions[:] = owner_subscriptions[-3:]
    save_secrets(secrets)
    log_event({"action": "web_push_subscribed", "ownerKey": owner_key})
    return {"subscribed": True, "count": len(owner_subscriptions)}


def remove_web_push_subscription(owner_key, endpoint=None):
    owner_key = require_owner(owner_key)
    secrets = load_secrets()
    owner_subscriptions = secrets.setdefault("webPushSubscriptions", {}).setdefault(owner_key, [])
    before = len(owner_subscriptions)
    if endpoint:
        owner_subscriptions[:] = [
            item for item in owner_subscriptions if item.get("endpoint") != endpoint
        ]
    else:
        owner_subscriptions.clear()
    save_secrets(secrets)
    log_event({"action": "web_push_unsubscribed", "ownerKey": owner_key, "removed": before - len(owner_subscriptions)})
    return {"subscribed": False, "count": len(owner_subscriptions)}


def notify_web_push(payload, owner_keys):
    if not owner_keys:
        return False
    try:
        vapid = ensure_web_push_keys()
    except Exception as exc:
        log_event({"action": "web_push_key_error", "error": str(exc)})
        return False

    secrets = load_secrets()
    subscriptions_by_owner = secrets.setdefault("webPushSubscriptions", {})
    sent = 0
    stale = []
    for owner_key in owner_keys:
        if not is_push_enabled(owner_key):
            continue
        for subscription in list(subscriptions_by_owner.get(owner_key, [])):
            if not subscription.get("deviceId"):
                stale.append((owner_key, subscription.get("endpoint")))
                log_event({"action": "web_push_legacy_subscription_removed", "ownerKey": owner_key})
                continue
            request = {
                "subscription": subscription,
                "payload": payload,
                "vapid": vapid,
            }
            try:
                proc = subprocess.run(
                    ["node", str(WEB_PUSH_SCRIPT_PATH)],
                    cwd=str(BASE_DIR),
                    input=json.dumps(request, ensure_ascii=False),
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                if proc.returncode == 0:
                    sent += 1
                    continue
                status = None
                try:
                    status = json.loads(proc.stdout or "{}").get("statusCode")
                except json.JSONDecodeError:
                    pass
                if status in (404, 410):
                    stale.append((owner_key, subscription.get("endpoint")))
                log_event({"action": "web_push_error", "ownerKey": owner_key, "statusCode": status, "error": (proc.stderr or proc.stdout)[-400:]})
            except Exception as exc:
                log_event({"action": "web_push_error", "ownerKey": owner_key, "error": str(exc)})

    if stale:
        for owner_key, endpoint in stale:
            subscriptions_by_owner[owner_key] = [
                item for item in subscriptions_by_owner.get(owner_key, [])
                if item.get("endpoint") != endpoint
            ]
        save_secrets(secrets)
    if sent:
        log_event({"action": "web_push_notified", "count": sent})
    return sent > 0


def notify_result(result):
    owner_key = result.get("ownerKey")
    action = result.get("action")
    if action == "sent":
        if owner_key and not is_push_enabled(owner_key):
            log_event({"action": "push_notify_skipped", "reason": "push_disabled", "ownerKey": owner_key})
            return False
        web_pushed = notify_web_push(sent_notification_payload(result), [owner_key] if owner_key else [])
        if web_pushed:
            return True
        log_event(
            {
                "action": "push_notify_skipped",
                "reason": "no_sender_subscription",
                "ownerKey": owner_key,
            }
        )
        return False
    elif action == "worklog_sent":
        if owner_key and not is_push_enabled(owner_key):
            log_event({"action": "push_notify_skipped", "reason": "push_disabled", "ownerKey": owner_key})
            return False
        if owner_key:
            push_key = result.get("runKey") or f"{result.get('stdDt')}T{result.get('scheduleTime') or ''}"
            state = get_account_state(owner_key)
            if push_key and state.get("worklogLastPushRunKey") == push_key:
                log_event({"action": "push_notify_skipped", "reason": "worklog_push_already_sent", "ownerKey": owner_key, "runKey": push_key})
                return False
        web_pushed = notify_web_push(worklog_notification_payload(result), [owner_key] if owner_key else [])
        if web_pushed:
            if owner_key and push_key:
                state["worklogLastPushRunKey"] = push_key
                state["worklogLastPushAt"] = now_iso()
                save_account_state(owner_key, state)
            return True
        log_event({"action": "push_notify_skipped", "reason": "no_owner_subscription", "ownerKey": owner_key})
        return False
    elif action in ("error", "failed"):
        if owner_key and not is_push_enabled(owner_key):
            log_event({"action": "telegram_notify_skipped", "reason": "push_disabled", "ownerKey": owner_key})
            return False
        error = str(result.get("error") or result.get("lastAttemptResult") or "unknown error")
        return notify_telegram(f"열매 자동전송 오류: {error[:300]}")
    return False


def read_secret(name):
    env_name = "FRUIT_AUTO_" + name.upper()
    if os.environ.get(env_name):
        return os.environ[env_name]
    secrets = load_json(SECRETS_PATH, {})
    value = secrets.get(name)
    if not value:
        raise FruitAutoError(f"missing secret: {name}")
    return value


class Client:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def open(self, request, timeout=25):
        try:
            return self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise FruitAutoError(f"HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise FruitAutoError(f"network error: {exc}") from exc

    def get_text(self, url, headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        return self.open(req).read().decode("utf-8", "replace")

    def post_json(self, url, payload=None):
        body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://forest2.fingerservice.co.kr",
            "Referer": "https://forest2.fingerservice.co.kr/",
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        text = self.open(req).read().decode("utf-8", "replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FruitAutoError(f"invalid JSON from {url}: {text[:500]}") from exc
        result = data.get("result") or {}
        if str(result.get("code")) != "200":
            raise FruitAutoError(f"{url} failed: {result}")
        return result.get("content") or {}


def pms_login(client, pms_id=None, pms_password=None):
    pms_id = pms_id or read_secret("pms_id")
    pms_password = pms_password or read_secret("pms_password")
    client.get_text(PMS_LOGIN_PAGE)
    query = urllib.parse.urlencode({"user_id": pms_id, "user_password": pms_password})
    headers = {
        "Apikey": "vDw17TUSP83JziBu",
        "Lang": "ko",
        "SvcToken": "",
        "DataPage": "1",
        "DataNumber": "10",
    }
    text = client.get_text(f"{PMS_LOGIN_API}?{query}", headers=headers)
    data = json.loads(text)
    if not data.get("success"):
        raise FruitAutoError(f"PMS login failed: {data}")
    dataset = data.get("dataset") or {}
    token = data.get("token") or dataset.get("SESS_TOKENVALUE")
    if not token:
        raise FruitAutoError("PMS login did not return a token")
    return token, dataset


def save_credentials(pms_id, pms_password):
    client = Client()
    token, dataset = pms_login(client, pms_id, pms_password)
    forest_login(client, token)
    data = {"pms_id": pms_id, "pms_password": pms_password}
    save_json(SECRETS_PATH, data)
    try:
        SECRETS_PATH.chmod(0o600)
    except OSError:
        pass
    log_event({"action": "credentials_saved", "user": dataset.get("SESS_USERNAME")})
    state = load_json(STATE_PATH, DEFAULT_STATE)
    previous_login_id = state.get("loginUserId")
    next_login_id = dataset.get("SESS_USERID")
    same_login = not previous_login_id or not next_login_id or previous_login_id == next_login_id
    state.update(
        {
            "enabled": bool(state.get("enabled")) if same_login else False,
            "status": state.get("status", "off") if same_login else "off",
            "loginSavedAt": now_iso(),
            "loginUser": dataset.get("SESS_USERNAME"),
            "loginUserId": next_login_id,
            "loginEmployeeNo": dataset.get("SESS_EMPNO"),
            "targetEmployeeName": state.get("targetEmployeeName") if same_login else None,
            "targetEmployeeId": state.get("targetEmployeeId") if same_login else None,
            "targetDutyId": state.get("targetDutyId") if same_login else None,
            "targetDeptName": state.get("targetDeptName") if same_login else None,
            "targetPositionName": state.get("targetPositionName") if same_login else None,
            "updatedAt": now_iso(),
        }
    )
    save_json(STATE_PATH, state)
    return {
        "success": True,
        "user": dataset.get("SESS_USERNAME"),
        "userId": dataset.get("SESS_USERID"),
        "employeeNo": dataset.get("SESS_EMPNO"),
    }


def forest_login(client, pms_token):
    content = client.post_json(f"{FOREST_API}/pmsForest", {"tokenNO": pms_token})
    rows = content.get("resultMap") or []
    if not rows:
        raise FruitAutoError("Forest token exchange returned no employee")
    emp_id = rows[0].get("emp_id")
    if not emp_id:
        raise FruitAutoError("Forest token exchange returned no emp_id")

    content = client.post_json(f"{FOREST_API}/getPmsEmployee", {"empId": emp_id})
    result_rows = content.get("resultMap") or []
    auth_rows = content.get("forestAuth") or []
    if not result_rows or not auth_rows:
        raise FruitAutoError("Forest employee info is incomplete")
    return content


def current_seed_fruit(client, employee):
    today = dt.datetime.now()
    std_month = f"{today.year}{today.month:02d}"
    payload = {
        "empId": employee["emp_id"],
        "stdMt": std_month,
        "dutyId": employee["duty_id"],
    }
    content = client.post_json(f"{FOREST_API}/headerReset", payload)
    berries = int((content.get("bryCnt") or [{"berryCnt": "0"}])[0].get("berryCnt") or 0)
    seeds = int((content.get("seedCnt") or [{"seedCnt": "0"}])[0].get("seedCnt") or 0)
    return seeds, berries


def forest_level_label(level):
    value = str(level or "").strip()
    labels = {
        "1": "씨앗 1단계",
        "2": "씨앗 2단계",
        "3": "열매 1단계",
        "4": "열매 2단계",
        "5": "나무 단계",
        "6": "숲 단계",
    }
    return labels.get(value, "숲 단계")


def forest_ranking(kind="berry", month=None, owner_key=None, limit=None):
    owner_key = require_owner(owner_key)
    client, employee_info, _login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
    now = dt.datetime.now(KST)
    std_month = str(month or f"{now.year}{now.month:02d}").replace("-", "")[:6]
    if len(std_month) != 6 or not std_month.isdigit():
        std_month = f"{now.year}{now.month:02d}"
    kind = str(kind or "berry")
    payload = {"empId": "", "empNm": "", "stdMt": ""}
    if kind == "berry":
        payload = {
            "empId": sender_employee_id,
            "empNm": sender_employee_name,
            "stdMt": std_month,
        }
    elif kind == "gift":
        payload = {"empId": "", "stdMt": std_month}
    elif kind == "level":
        payload = {"empId": "", "empNm": "", "stdMt": ""}
    else:
        raise FruitAutoError("알 수 없는 랭킹 종류입니다.")

    content = client.post_json(f"{FOREST_API}/bryRank", payload)
    rows = content if isinstance(content, list) else content.get("resultMap") or []
    rows = list(rows or [])
    my_row = None
    ranking_rows = rows
    if kind == "berry":
        my_row = rows[0] if rows else None
        ranking_rows = rows[1:]
    elif kind == "level":
        for row in rows:
            if str(row.get("empId") or row.get("emp_id") or "") == str(sender_employee_id):
                my_row = row
                break

    def int_text(value):
        return parse_int(value, 0)

    def row_name(row):
        return row.get("empNm") or row.get("emp_nm") or row.get("name") or "-"

    items = []
    if limit is None:
        visible_rows = ranking_rows
    else:
        try:
            max_items = int(limit)
        except (TypeError, ValueError):
            max_items = len(ranking_rows)
        visible_rows = ranking_rows[:max(1, max_items)]
    for index, row in enumerate(visible_rows, 1):
        if kind == "level":
            count = int_text(row.get("yrBryCnt") or row.get("sumBerry"))
            items.append({
                "rank": int_text(row.get("rankNo") or row.get("rnk") or index),
                "name": row_name(row),
                "level": forest_level_label(row.get("lvl")),
                "count": count,
            })
        else:
            items.append({
                "rank": int_text(row.get("rnk") or row.get("rankNo") or index) or index,
                "name": row_name(row),
                "count": int_text(row.get("sumBerry") or row.get("yrBryCnt")),
            })

    if my_row:
        if kind == "level":
            my = {
                "rank": int_text(my_row.get("rankNo") or my_row.get("rnk")),
                "name": sender_employee_name,
                "level": forest_level_label(my_row.get("lvl")),
                "count": int_text(my_row.get("yrBryCnt") or my_row.get("sumBerry")),
            }
        else:
            my = {
                "rank": int_text(my_row.get("rnk") or my_row.get("rankNo")),
                "name": sender_employee_name,
                "count": int_text(my_row.get("sumBerry") or my_row.get("yrBryCnt")),
            }
    else:
        my = {
            "rank": 0,
            "name": sender_employee_name,
            "level": "씨앗 1단계" if kind == "level" else "",
            "count": 0,
        }

    return {
        "kind": kind,
        "month": std_month,
        "userName": sender_employee_name,
        "my": my,
        "items": items,
    }


def refresh_balance(force=False):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    checked_at = state.get("balanceCheckedAt") or state.get("lastCheckedAt")
    if not force and checked_at:
        try:
            checked = dt.datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if (dt.datetime.now(dt.timezone.utc) - checked).total_seconds() < 45:
                return state
        except ValueError:
            pass

    client = Client()
    pms_token, login_dataset = pms_login(client)
    employee_info = forest_login(client, pms_token)
    employee = employee_info["resultMap"][0]
    owner_key, sender_employee_id, sender_employee_name = employee_identity(
        employee, login_dataset.get("SESS_USERID")
    )
    seeds, berries = current_seed_fruit(client, employee)
    state.update(
        {
            "lastSeedCount": seeds,
            "lastBerryCount": berries,
            "balanceCheckedAt": now_iso(),
            "lastCheckedAt": now_iso(),
            "ownerKey": owner_key,
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "loginUser": state.get("loginUser") or login_dataset.get("SESS_USERNAME"),
            "loginUserId": state.get("loginUserId") or login_dataset.get("SESS_USERID"),
            "loginEmployeeNo": state.get("loginEmployeeNo") or login_dataset.get("SESS_EMPNO"),
        }
    )
    save_json(STATE_PATH, state)
    log_event(
        {
            "action": "balance",
            "seeds": seeds,
            "berries": berries,
            "ownerKey": owner_key,
        }
    )
    return state


def event_local_date(event, timezone_offset_minutes=0):
    value = event.get("at")
    if not value:
        return ""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    local_time = parsed.astimezone(dt.timezone.utc) - dt.timedelta(minutes=timezone_offset_minutes)
    return local_time.date().isoformat()


def selected_history_month(date=None, timezone_offset_minutes=0):
    if date:
        try:
            parsed = dt.date.fromisoformat(str(date))
            return parsed.strftime("%Y%m")
        except ValueError:
            pass
    local_now = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=timezone_offset_minutes)
    return local_now.strftime("%Y%m")


def selected_history_day(date=None):
    if not date:
        return None
    try:
        return dt.date.fromisoformat(str(date)).day
    except ValueError:
        return None


def parse_int(value, default=0):
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").strip()
        if text == "":
            return default
        return int(text)
    except (TypeError, ValueError):
        return default


def normalize_history_message(value):
    return str(value or "").replace("[열매선물]", "").replace("[씨앗선물]", "").strip()


def history_date_from_month_day(month, day):
    try:
        if day is None:
            return None
        parsed = dt.datetime.strptime(f"{int(month):06d}{int(day):02d}", "%Y%m%d")
        return parsed.date().isoformat()
    except (TypeError, ValueError):
        return None


def normalize_history_month(value=None):
    if value:
        text = re.sub(r"\D", "", str(value or ""))
        if len(text) >= 6:
            return text[:6]
    return dt.datetime.now(KST).strftime("%Y%m")


def observed_time_matches_history_date(value, history_date):
    observed = parse_iso(value)
    if not observed or not history_date:
        return False
    return observed.astimezone(KST).date().isoformat() == str(history_date)


def api_order_history_time(history_date, ordinal, spacing_minutes=5):
    try:
        day = dt.date.fromisoformat(str(history_date))
        offset = max(0, int(ordinal or 0)) * spacing_minutes
    except (TypeError, ValueError):
        return None
    return (
        dt.datetime.combine(day, dt.time(9, 0), tzinfo=KST)
        + dt.timedelta(minutes=offset)
    ).astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def official_history_fingerprint(row):
    payload = {
        "ownerKey": row.get("ownerKey"),
        "employeeId": row.get("historyEmployeeId"),
        "historyDate": row.get("historyDate"),
        "action": row.get("action"),
        "target": row.get("target"),
        "targetEmployeeId": row.get("targetEmployeeId"),
        "berries": row.get("berries"),
        "remaining": row.get("remaining"),
        "seeds": row.get("seeds"),
        "content": normalize_history_message(row.get("content")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def official_seed_history_fingerprint(row):
    payload = {
        "ownerKey": row.get("ownerKey"),
        "employeeId": row.get("historyEmployeeId"),
        "historyDate": row.get("historyDate"),
        "action": row.get("action"),
        "target": row.get("target"),
        "targetEmployeeId": row.get("targetEmployeeId"),
        "seedDelta": abs(parse_int(row.get("delta"), 0)),
        "remainingSeeds": row.get("seeds"),
        "remainingBerries": row.get("remaining"),
        "content": normalize_history_message(row.get("content")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_seed_history_message(value):
    return "씨앗" in str(value or "")


def berry_history_reward_kind(value):
    text = str(value or "")
    if "칭찬" in text:
        return "praise"
    if "업무" in text and "승인" in text:
        return "work_approval"
    if "승인" in text:
        return "approval"
    return "gift"


def parse_seed_berry_counts(value):
    parts = str(value or "0/0").split("/")
    berries = parse_int(parts[0] if len(parts) > 0 else 0)
    seeds = parse_int(parts[1] if len(parts) > 1 else 0)
    return seeds, berries


def history_observation_db():
    conn = sqlite3.connect(HISTORY_OBSERVATIONS_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_history_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_key TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            history_date TEXT NOT NULL,
            row_fingerprint TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            action TEXT NOT NULL,
            counterpart_name TEXT,
            counterpart_employee_id TEXT,
            berries INTEGER,
            remaining INTEGER,
            seeds INTEGER,
            content TEXT,
            first_seen_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(owner_key, employee_id, history_date, row_fingerprint, ordinal)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_official_history_observations_scope "
        "ON official_history_observations(owner_key, employee_id, history_date)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_history_observation_scopes (
            owner_key TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            history_date TEXT NOT NULL,
            bootstrapped_at TEXT NOT NULL,
            PRIMARY KEY(owner_key, employee_id, history_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_seed_history_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_key TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            history_date TEXT NOT NULL,
            row_fingerprint TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            action TEXT NOT NULL,
            counterpart_name TEXT,
            counterpart_employee_id TEXT,
            seed_delta INTEGER,
            remaining_seeds INTEGER,
            remaining_berries INTEGER,
            content TEXT,
            first_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(owner_key, employee_id, history_date, row_fingerprint, ordinal)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_official_seed_history_observations_scope "
        "ON official_seed_history_observations(owner_key, employee_id, history_date)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_seed_history_observation_scopes (
            owner_key TEXT NOT NULL,
            employee_id TEXT NOT NULL,
            history_date TEXT NOT NULL,
            bootstrapped_at TEXT NOT NULL,
            PRIMARY KEY(owner_key, employee_id, history_date)
        )
        """
    )
    return conn


def sync_official_seed_history_observations(owner_key, employee_id, history_date, rows, observed_at=None):
    owner_key = str(owner_key or "")
    employee_id = str(employee_id or "")
    history_date = str(history_date or "")
    scoped_rows = [row for row in rows if row.get("historyDate") == history_date and row.get("_officialSeedFingerprint")]
    if not owner_key or not employee_id or not history_date or not scoped_rows:
        return {}

    now = observed_at or now_iso()
    with history_observation_db() as conn:
        scope_row = conn.execute(
            """
            SELECT bootstrapped_at
            FROM official_seed_history_observation_scopes
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            """,
            (owner_key, employee_id, history_date),
        ).fetchone()
        bootstrapped_at = scope_row["bootstrapped_at"] if scope_row else None
        bootstrap_existing_date = scope_row is None
        existing_by_fingerprint = {}
        for row in conn.execute(
            """
            SELECT *
            FROM official_seed_history_observations
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            ORDER BY ordinal ASC
            """,
            (owner_key, employee_id, history_date),
        ):
            existing_by_fingerprint.setdefault(row["row_fingerprint"], []).append(row)

        requested_by_fingerprint = {}
        for row in scoped_rows:
            requested_by_fingerprint.setdefault(row["_officialSeedFingerprint"], []).append(row)

        for fingerprint, requested_rows in requested_by_fingerprint.items():
            existing_rows = existing_by_fingerprint.get(fingerprint, [])
            for ordinal in range(len(existing_rows) + 1, len(requested_rows) + 1):
                sample = requested_rows[ordinal - 1]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO official_seed_history_observations (
                        owner_key, employee_id, history_date, row_fingerprint, ordinal,
                        action, counterpart_name, counterpart_employee_id, seed_delta,
                        remaining_seeds, remaining_berries, content, first_seen_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner_key,
                        employee_id,
                        history_date,
                        fingerprint,
                        ordinal,
                        sample.get("action") or "",
                        sample.get("target") or "",
                        sample.get("targetEmployeeId") or "",
                        abs(parse_int(sample.get("delta"), 0)),
                        parse_int(sample.get("seeds"), 0),
                        parse_int(sample.get("remaining"), 0),
                        sample.get("content") or "",
                        "" if bootstrap_existing_date else now,
                        now,
                    ),
                )

        conn.execute(
            """
            INSERT OR IGNORE INTO official_seed_history_observation_scopes (
                owner_key, employee_id, history_date, bootstrapped_at
            ) VALUES (?, ?, ?, ?)
            """,
            (owner_key, employee_id, history_date, now),
        )

        lookup = {}
        refreshed = {}
        for row in conn.execute(
            """
            SELECT *
            FROM official_seed_history_observations
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            ORDER BY id ASC
            """,
            (owner_key, employee_id, history_date),
        ):
            refreshed.setdefault(row["row_fingerprint"], []).append(row)
        for fingerprint, observed_rows in refreshed.items():
            for index, row in enumerate(observed_rows, start=1):
                first_seen_at = row["first_seen_at"]
                if (
                    bootstrapped_at
                    and first_seen_at == bootstrapped_at
                    and row["created_at"] == bootstrapped_at
                ):
                    first_seen_at = ""
                lookup[(fingerprint, index)] = first_seen_at
        return lookup


def sync_official_history_observations(owner_key, employee_id, history_date, rows, bootstrap_first_seen_at=None):
    owner_key = str(owner_key or "")
    employee_id = str(employee_id or "")
    history_date = str(history_date or "")
    scoped_rows = [row for row in rows if row.get("historyDate") == history_date and row.get("_officialFingerprint")]
    if not owner_key or not employee_id or not history_date or not scoped_rows:
        return {}

    now = now_iso()
    with history_observation_db() as conn:
        existing_scope = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM official_history_observations
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            """,
            (owner_key, employee_id, history_date),
        ).fetchone()
        scope_bootstrapped = conn.execute(
            """
            SELECT 1
            FROM official_history_observation_scopes
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            """,
            (owner_key, employee_id, history_date),
        ).fetchone()
        existing_by_fingerprint = {}
        for row in conn.execute(
            """
            SELECT *
            FROM official_history_observations
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            ORDER BY ordinal ASC
            """,
            (owner_key, employee_id, history_date),
        ):
            existing_by_fingerprint.setdefault(row["row_fingerprint"], []).append(row)

        requested_by_fingerprint = {}
        for row in scoped_rows:
            requested_by_fingerprint.setdefault(row["_officialFingerprint"], []).append(row)

        bootstrap_existing_date = scope_bootstrapped is None
        for fingerprint, requested_rows in requested_by_fingerprint.items():
            existing_rows = existing_by_fingerprint.get(fingerprint, [])
            for ordinal in range(len(existing_rows) + 1, len(requested_rows) + 1):
                sample = requested_rows[ordinal - 1]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO official_history_observations (
                        owner_key, employee_id, history_date, row_fingerprint, ordinal,
                        action, counterpart_name, counterpart_employee_id, berries,
                        remaining, seeds, content, first_seen_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner_key,
                        employee_id,
                        history_date,
                        fingerprint,
                        ordinal,
                        sample.get("action") or "",
                        sample.get("target") or "",
                        sample.get("targetEmployeeId") or "",
                        parse_int(sample.get("berries"), 0),
                        parse_int(sample.get("remaining"), 0),
                        parse_int(sample.get("seeds"), 0),
                        sample.get("content") or "",
                        None if bootstrap_existing_date else now,
                        now,
                    ),
                )

        if bootstrap_existing_date:
            conn.execute(
                """
                INSERT OR REPLACE INTO official_history_observation_scopes (
                    owner_key, employee_id, history_date, bootstrapped_at
                ) VALUES (?, ?, ?, ?)
                """,
                (owner_key, employee_id, history_date, now),
            )

        lookup = {}
        refreshed = {}
        for row in conn.execute(
            """
            SELECT *
            FROM official_history_observations
            WHERE owner_key = ? AND employee_id = ? AND history_date = ?
            ORDER BY
                CASE WHEN first_seen_at IS NULL THEN 1 ELSE 0 END,
                first_seen_at DESC,
                id DESC
            """,
            (owner_key, employee_id, history_date),
        ):
            refreshed.setdefault(row["row_fingerprint"], []).append(row)
        for fingerprint, observed_rows in refreshed.items():
            for index, row in enumerate(observed_rows, start=1):
                lookup[(fingerprint, index)] = row["first_seen_at"]
        return lookup


def local_transfer_history_for_official(owner_key, employee_id, date=None, timezone_offset_minutes=0, limit=5000):
    events = []
    received_keys = set()
    for event in reversed(read_jsonl(HISTORY_PATH, limit)):
        if not is_transfer_history_event(event) and not is_seed_transfer_history_event(event):
            continue
        if date and event_local_date(event, timezone_offset_minutes) != date:
            continue
        sent_by_me = event.get("ownerKey") == owner_key
        received_by_me = employee_id and str(event.get("targetEmployeeId") or "") == str(employee_id)
        if not sent_by_me and not received_by_me:
            continue
        events.append(event)
        if event.get("action") == "received":
            received_keys.add(
                (
                    str(event.get("ownerKey") or ""),
                    str(event.get("targetEmployeeId") or ""),
                    str(event.get("at") or ""),
                    parse_int(event.get("berries"), 0),
                )
            )
    for event in reversed(read_jsonl(LOG_PATH, limit)):
        if event.get("action") != "send_delay_wait":
            continue
        if str(event.get("ownerKey") or "") != str(owner_key or ""):
            continue
        received_at = event.get("receivedAt")
        if not received_at:
            continue
        received_event = {
            "type": "transfer",
            "action": "received",
            "at": received_at,
            "timeSource": "balance_detected",
            "berries": event.get("berries"),
            "sender": event.get("target"),
            "senderEmployeeName": event.get("target"),
            "senderEmployeeId": event.get("targetEmployeeId") or "",
            "targetEmployeeId": str(employee_id or ""),
            "ownerKey": owner_key,
            "message": event.get("message") or "",
        }
        received_key = (
            str(received_event.get("ownerKey") or ""),
            str(received_event.get("targetEmployeeId") or ""),
            str(received_event.get("at") or ""),
            parse_int(received_event.get("berries"), 0),
        )
        if received_key in received_keys:
            continue
        if date and event_local_date(received_event, timezone_offset_minutes) != date:
            continue
        events.append(received_event)
    events.sort(key=lambda item: parse_iso(item.get("at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    return events


def transfer_history_fingerprint_exists(owner_key, fingerprint, action=None, occurrence=None, limit=20000):
    if not fingerprint:
        return False
    for event in reversed(read_jsonl(HISTORY_PATH, limit)):
        if not is_transfer_history_event(event):
            continue
        if str(event.get("ownerKey") or "") != str(owner_key or ""):
            continue
        if action and event.get("action") != action:
            continue
        if event.get("officialFingerprint") == fingerprint:
            if occurrence is not None and parse_int(event.get("officialOccurrence"), None) != occurrence:
                continue
            return True
    return False


def transfer_history_event_exists(owner_key, action, at, target_employee_id, berries, limit=20000):
    if not at or not target_employee_id:
        return False
    for event in reversed(read_jsonl(HISTORY_PATH, limit)):
        if not is_transfer_history_event(event):
            continue
        if str(event.get("ownerKey") or "") != str(owner_key or ""):
            continue
        if event.get("action") != action:
            continue
        if str(event.get("at") or "") != str(at or ""):
            continue
        if str(event.get("targetEmployeeId") or "") != str(target_employee_id or ""):
            continue
        if parse_int(event.get("berries"), None) != parse_int(berries, None):
            continue
        return True
    return False


def record_balance_detected_received_history(
    owner_key,
    receiver_employee_id,
    receiver_name,
    receiver_position,
    sender_employee_id,
    sender_name,
    sender_position,
    berries,
    received_at,
    seeds=None,
    remaining=None,
):
    received_at = parse_iso(received_at)
    if not received_at:
        return None
    at = received_at.replace(microsecond=0).isoformat()
    if transfer_history_event_exists(owner_key, "received", at, receiver_employee_id, berries):
        return None
    event = {
        "type": "transfer",
        "action": "received",
        "at": at,
        "timeSource": "balance_detected",
        "berries": berries,
        "seeds": seeds,
        "remaining": remaining,
        "receiverRemaining": remaining if remaining is not None else berries,
        "sender": sender_name,
        "senderEmployeeName": sender_name,
        "senderEmployeeId": sender_employee_id,
        "senderPositionName": sender_position,
        "target": receiver_name,
        "targetEmployeeName": receiver_name,
        "targetEmployeeId": receiver_employee_id,
        "targetPositionName": receiver_position,
        "ownerKey": owner_key,
        "message": "열매 선물",
    }
    record_transfer_history(event)
    return event


def official_received_history_rows(client, owner_key, employee_id, employee_name, employee_position, history_date):
    try:
        parsed_date = dt.date.fromisoformat(str(history_date))
    except (TypeError, ValueError):
        parsed_date = dt.datetime.now(KST).date()
    month = parsed_date.strftime("%Y%m")
    selected_day = parsed_date.day
    content = client.post_json(f"{FOREST_API}/dwBerySeed", {"stdMt": month, "empId": employee_id})
    if not isinstance(content, list):
        return []
    rows = []
    for row in content:
        day = parse_int(str(row.get("stdDt") or "").replace("일", ""), None)
        if day != selected_day:
            continue
        delta = parse_int(row.get("stdDBerryPmCnt"))
        if delta <= 0:
            continue
        seed_count, fruit_count = parse_seed_berry_counts(row.get("stdMBerryCnt"))
        item = {
            "at": None,
            "displayTime": row.get("stdDt") or "",
            "timeLabel": "받음",
            "action": "received",
            "ownerKey": owner_key,
            "historyEmployeeId": str(employee_id or ""),
            "historyDate": parsed_date.isoformat(),
            "target": row.get("tgtEmpNm") or "",
            "targetEmployeeId": "",
            "targetPositionName": "",
            "senderEmployeeId": "",
            "avatarEmployeeId": "",
            "avatarName": row.get("tgtEmpNm") or "",
            "displayName": display_employee(employee_name, employee_position),
            "senderIsMe": False,
            "seeds": seed_count,
            "berries": abs(delta),
            "remaining": fruit_count,
            "delta": delta,
            "content": row.get("tgtMsg") or "[열매선물]",
            "source": f"forest_{berry_history_reward_kind(row.get('tgtMsg'))}",
        }
        item["_officialFingerprint"] = official_history_fingerprint(item)
        rows.append(item)
    return rows


def is_recent_observation(value, observed_at, window_seconds=120):
    seen_at = parse_iso(value)
    if not seen_at or not observed_at:
        return False
    return -30 <= (observed_at - seen_at).total_seconds() <= window_seconds


def record_received_history_from_official(
    client,
    owner_key,
    employee_id,
    employee_name,
    employee_position,
    observed_at,
    window_seconds=330,
):
    local_observed_at = observed_at.astimezone(KST)
    history_date = local_observed_at.date().isoformat()
    rows = official_received_history_rows(
        client,
        owner_key,
        employee_id,
        employee_name,
        employee_position,
        history_date,
    )
    if not rows:
        return []
    scope_was_bootstrapped = False
    try:
        with history_observation_db() as conn:
            scope_was_bootstrapped = conn.execute(
                """
                SELECT 1
                FROM official_history_observation_scopes
                WHERE owner_key = ? AND employee_id = ? AND history_date = ?
                """,
                (str(owner_key or ""), str(employee_id or ""), str(history_date or "")),
            ).fetchone() is not None
    except Exception:
        scope_was_bootstrapped = False
    lookup = sync_official_history_observations(
        owner_key,
        employee_id,
        history_date,
        rows,
        bootstrap_first_seen_at=observed_at.replace(microsecond=0).isoformat(),
    )
    if not scope_was_bootstrapped:
        return []
    recorded = []
    occurrence_by_fingerprint = {}
    for row in rows:
        fingerprint = row.get("_officialFingerprint")
        occurrence_by_fingerprint[fingerprint] = occurrence_by_fingerprint.get(fingerprint, 0) + 1
        occurrence = occurrence_by_fingerprint[fingerprint]
        first_seen_at = lookup.get((fingerprint, occurrence))
        if not is_recent_observation(first_seen_at, observed_at, window_seconds):
            continue
        if transfer_history_fingerprint_exists(owner_key, fingerprint, action="received", occurrence=occurrence):
            continue
        event = {
            "type": "transfer",
            "action": "received",
            "at": parse_iso(first_seen_at).replace(microsecond=0).isoformat(),
            "timeSource": "official_observed",
            "officialFingerprint": fingerprint,
            "officialOccurrence": occurrence,
            "berries": row.get("berries"),
            "seeds": row.get("seeds"),
            "remaining": row.get("remaining"),
            "sender": row.get("target"),
            "senderEmployeeName": row.get("target"),
            "senderEmployeeId": row.get("targetEmployeeId") or "",
            "senderPositionName": row.get("targetPositionName") or "",
            "target": employee_name,
            "targetEmployeeName": employee_name,
            "targetEmployeeId": employee_id,
            "targetPositionName": employee_position,
            "ownerKey": owner_key,
            "message": row.get("content"),
        }
        record_transfer_history(event)
        recorded.append(event)
    return recorded


def employee_hint_from_event(event, action):
    if action == "sent":
        return {
            "employeeId": str(event.get("targetEmployeeId") or ""),
            "positionName": event.get("targetPositionName") or "",
        }
    return {
        "employeeId": str(event.get("senderEmployeeId") or ""),
        "positionName": event.get("senderPositionName") or "",
    }


def reliable_history_event_time(event, is_seed_history=False):
    if not event or not event.get("at"):
        return None
    if event.get("timeSource") in {"official_observed"} and not is_seed_history:
        return None
    return event.get("at")


def local_history_hints_by_name(local_events):
    hints = {}
    for event in local_events:
        target_name = event.get("target") or event.get("targetEmployeeName")
        if target_name and event.get("targetEmployeeId"):
            hints[str(target_name)] = {
                "employeeId": str(event.get("targetEmployeeId") or ""),
                "positionName": event.get("targetPositionName") or "",
            }
        sender_name = event.get("senderEmployeeName") or event.get("sender")
        if sender_name and event.get("senderEmployeeId"):
            hints[str(sender_name)] = {
                "employeeId": str(event.get("senderEmployeeId") or ""),
                "positionName": event.get("senderPositionName") or "",
            }
    return hints


def match_official_history_event(local_events, used_indexes, action, counterpart, berries, message, remaining=None, is_seed_history=False):
    normalized_message = normalize_history_message(message)
    for index, event in enumerate(local_events):
        if event.get("timeSource") == "official_observed" and not (is_seed_history and action == "received"):
            continue
        sent_by_me = action == "sent"
        if sent_by_me:
            used_key = (index, "sent")
            if used_key in used_indexes:
                continue
            event_counterpart = event.get("target") or event.get("targetEmployeeName")
            if str(event.get("ownerKey") or "") != str(event.get("_historyOwnerKey") or ""):
                continue
            if remaining is not None and parse_int(event.get("remaining"), None) != remaining:
                continue
        else:
            used_key = (index, "received")
            if used_key in used_indexes:
                continue
            event_counterpart = event.get("senderEmployeeName") or event.get("sender")
            if str(event.get("targetEmployeeId") or "") != str(event.get("_historyEmployeeId") or ""):
                continue
        if is_seed_history and not sent_by_me and event.get("timeSource") in {"balance_detected", "official_observed"}:
            event_amount = parse_int(event.get("seedDelta"), None)
            if event_amount is None:
                event_amount = parse_int(event.get("berries"), None)
            if event_amount != berries:
                continue
            used_indexes.add(used_key)
            return event
        if str(event_counterpart or "") != str(counterpart or ""):
            if sent_by_me:
                continue
            receiver_name = event.get("targetEmployeeName") or event.get("target")
            if str(receiver_name or "") != str(counterpart or ""):
                continue
        if is_seed_history:
            event_amount = parse_int(event.get("seedDelta"), None)
            if event_amount is None:
                event_amount = parse_int(event.get("berries"), None)
        else:
            event_amount = parse_int(event.get("berries"), None)
        if event_amount != berries:
            continue
        event_message = normalize_history_message(event.get("message"))
        if normalized_message and event_message and normalized_message != event_message:
            if not (action == "sent" and event_message == "자동 전달" and normalized_message in {"열매선물", "열매 선물"}):
                continue
        used_indexes.add(used_key)
        return event
    return None


def row_counterpart_key(row):
    return (
        str(row.get("targetEmployeeId") or row.get("target") or ""),
        parse_int(row.get("berries"), 0),
    )


def pair_official_history_transfer_times(rows):
    observe_interval = get_history_observe_interval_seconds()
    paired_received_indexes = set()
    for sent_index, sent in enumerate(rows):
        if sent.get("action") != "sent" or sent.get("timeSource") != "local_log":
            continue
        sent_at = parse_iso(sent.get("at"))
        if not sent_at:
            continue
        best_index = None
        best_rank = None
        for received_index, received in enumerate(rows):
            if received_index in paired_received_indexes:
                continue
            if received.get("action") != "received" or received.get("timeSource") != "received_log":
                continue
            if str(sent.get("target") or "") != str(received.get("target") or ""):
                continue
            received_at = parse_iso(received.get("at"))
            if not received_at:
                continue
            delta_seconds = (received_at - sent_at).total_seconds()
            if abs(delta_seconds) > observe_interval + 180:
                continue
            rank = (abs(sent_index - received_index), abs(delta_seconds))
            if best_rank is None or rank < best_rank:
                best_index = received_index
                best_rank = rank
        if best_index is not None:
            received = rows[best_index]
            received["observedAt"] = received.get("at")
            inferred_at = sent_at - dt.timedelta(seconds=observe_interval)
            received["at"] = inferred_at.replace(microsecond=0).isoformat()
            received["inferredFromSentAt"] = sent_at.replace(microsecond=0).isoformat()
            received["timeSource"] = "paired_sent_log"
            paired_received_indexes.add(best_index)
    return rows


def infer_official_history_times(rows):
    for seed in rows:
        if seed.get("historyKind") != "seed":
            continue
        if seed.get("action") != "received":
            continue
        if seed.get("at"):
            continue
        observed_at = parse_iso(seed.get("observedAt"))
        if not observed_at:
            continue
        detected_at = observed_at.replace(microsecond=0)
        seed["at"] = detected_at.isoformat()
        seed["inferredFromSeedObservedAt"] = observed_at.replace(microsecond=0).isoformat()
        seed["timeSource"] = "seed_detected_from_observed_seed"
    return rows


def remove_future_observed_history_times(rows):
    latest_allowed = None
    for row in rows:
        row_time = parse_iso(row.get("at"))
        if row_time and latest_allowed and row_time > latest_allowed and row.get("timeSource") == "observed_db":
            row["at"] = None
            row["timeSource"] = "missing"
            row_time = None
        if row_time:
            latest_allowed = row_time if latest_allowed is None else min(latest_allowed, row_time)
    return rows


def sort_history_rows(rows):
    def sort_key(row):
        api_index = parse_int(row.get("_apiIndex"), None)
        if api_index is not None:
            return (0, api_index)
        parsed = parse_iso(row.get("at"))
        fallback_time = parsed or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        return (1, -fallback_time.timestamp())

    return sorted(rows, key=sort_key)


def official_history(limit=40, owner_key=None, date=None, timezone_offset_minutes=0):
    owner_key = require_owner(owner_key)
    client, _employee_info, _login_dataset, _employee, sender_employee_id, sender_employee_name = account_login(owner_key)
    state = get_account_state(owner_key)
    sender_position_name = state.get("senderPositionName") or ""
    month = selected_history_month(date, timezone_offset_minutes)
    selected_day = selected_history_day(date)
    content = client.post_json(f"{FOREST_API}/dwBerySeed", {"stdMt": month, "empId": sender_employee_id})
    if not isinstance(content, list):
        raise FruitAutoError("FOREST history did not return a list")

    local_events = local_transfer_history_for_official(owner_key, sender_employee_id, date, timezone_offset_minutes)
    for event in local_events:
        event["_historyOwnerKey"] = owner_key
        event["_historyEmployeeId"] = str(sender_employee_id or "")
    used_local_indexes = set()
    employee_hints = local_history_hints_by_name(local_events)
    rows = []
    seed_api_ordinal_by_date = {}
    for api_index, row in enumerate(content):
        day = parse_int(str(row.get("stdDt") or "").replace("일", ""), None)
        if selected_day is not None and day != selected_day:
            continue
        seed_count, fruit_count = parse_seed_berry_counts(row.get("stdMBerryCnt"))
        delta = parse_int(row.get("stdDBerryPmCnt"))
        action = "received" if delta > 0 else "sent"
        api_counterpart = row.get("tgtEmpNm") or ""
        counterpart = api_counterpart
        content_message = row.get("tgtMsg") or "[열매선물]"
        is_seed_history = is_seed_history_message(content_message)
        matched_event = match_official_history_event(
            local_events,
            used_local_indexes,
            action,
            counterpart,
            abs(delta),
            content_message,
            fruit_count if action == "sent" else None,
            is_seed_history=is_seed_history,
        )
        if action == "received" and matched_event:
            counterpart = matched_event.get("senderEmployeeName") or matched_event.get("sender") or counterpart
        employee_hint = employee_hint_from_event(matched_event, action) if matched_event else employee_hints.get(str(counterpart), {})
        if (
            action == "received"
            and not matched_event
            and str(api_counterpart or "") == str(sender_employee_name or "")
            and state.get("targetEmployeeName")
        ):
            counterpart = state.get("targetEmployeeName") or counterpart
            employee_hint = {
                "employeeId": str(state.get("targetEmployeeId") or ""),
                "positionName": state.get("targetPositionName") or "",
            }
        counterpart_position_name = employee_hint.get("positionName") or ""
        counterpart_employee_id = employee_hint.get("employeeId") or ""
        sender_is_me = action == "sent"
        me_display_name = display_employee(sender_employee_name, sender_position_name, "나")
        if action == "received":
            avatar_employee_id = counterpart_employee_id
            avatar_name = counterpart
            display_name = me_display_name
            display_employee_id = str(sender_employee_id or "")
            display_position_name = sender_position_name
            from_employee_id = counterpart_employee_id
            from_display_name = display_employee(counterpart, counterpart_position_name, counterpart or "-")
            from_avatar_name = counterpart
            to_employee_id = str(sender_employee_id or "")
            to_display_name = me_display_name
            to_avatar_name = sender_employee_name
        else:
            avatar_employee_id = str(sender_employee_id or "")
            avatar_name = sender_employee_name
            display_name = display_employee(counterpart, counterpart_position_name)
            display_employee_id = str(sender_employee_id or "")
            display_position_name = sender_position_name
            from_employee_id = str(sender_employee_id or "")
            from_display_name = me_display_name
            from_avatar_name = sender_employee_name
            to_employee_id = counterpart_employee_id
            to_display_name = display_employee(counterpart, counterpart_position_name, counterpart or "-")
            to_avatar_name = counterpart
        history_date = history_date_from_month_day(month, day)
        item = {
                "at": reliable_history_event_time(matched_event, is_seed_history=is_seed_history),
                "_matchedTimeSource": matched_event.get("timeSource") if matched_event else None,
                "_apiIndex": api_index,
                "displayTime": row.get("stdDt") or "",
                "timeLabel": "받음" if action == "received" else "보냄",
                "action": action,
                "ownerKey": owner_key,
                "historyEmployeeId": str(sender_employee_id or ""),
                "historyDate": history_date,
                "target": counterpart,
                "targetEmployeeId": counterpart_employee_id,
                "targetPositionName": counterpart_position_name,
                "senderEmployeeId": display_employee_id,
                "senderPositionName": display_position_name,
                "avatarEmployeeId": avatar_employee_id,
                "avatarName": avatar_name,
                "displayName": display_name,
                "fromEmployeeId": from_employee_id,
                "fromDisplayName": from_display_name,
                "fromAvatarName": from_avatar_name,
                "toEmployeeId": to_employee_id,
                "toDisplayName": to_display_name,
                "toAvatarName": to_avatar_name,
                "senderIsMe": sender_is_me,
                "seeds": seed_count,
                "berries": abs(delta),
                "remaining": fruit_count,
                "delta": delta,
                "content": content_message,
                "source": "forest_seed" if is_seed_history else f"forest_{berry_history_reward_kind(content_message)}",
                "rewardKind": "seed" if is_seed_history else berry_history_reward_kind(content_message),
                "historyKind": "seed" if is_seed_history else "berry",
        }
        if is_seed_history:
            if action == "received" and matched_event and matched_event.get("timeSource") in {"official_observed", "balance_detected"}:
                item["observedAt"] = matched_event.get("at")
                item["_matchedTimeSource"] = "seed_berry_observed"
            seed_api_ordinal = seed_api_ordinal_by_date.get(history_date, 0)
            seed_api_ordinal_by_date[history_date] = seed_api_ordinal + 1
            item["_apiOrderTime"] = api_order_history_time(history_date, seed_api_ordinal)
            item["_officialSeedFingerprint"] = official_seed_history_fingerprint(item)
            if action == "received":
                item["_officialFingerprint"] = official_history_fingerprint(item)
        else:
            item["_officialFingerprint"] = official_history_fingerprint(item)
        rows.append(item)
    seed_rows_by_date = {}
    for row in rows:
        if row.get("historyKind") == "seed" and row.get("historyDate"):
            seed_rows_by_date.setdefault(row.get("historyDate"), []).append(row)
    for history_date, seed_rows in seed_rows_by_date.items():
        lookup = sync_official_seed_history_observations(
            owner_key,
            sender_employee_id,
            history_date,
            seed_rows,
        )
        occurrence_by_fingerprint = {}
        for row in seed_rows:
            fingerprint = row.get("_officialSeedFingerprint")
            occurrence_by_fingerprint[fingerprint] = occurrence_by_fingerprint.get(fingerprint, 0) + 1
            first_seen_at = lookup.get((fingerprint, occurrence_by_fingerprint[fingerprint]))
            if row.get("action") != "received" and first_seen_at and observed_time_matches_history_date(first_seen_at, row.get("historyDate")):
                row["observedAt"] = first_seen_at
                row["_matchedTimeSource"] = "seed_observed"
    berry_rows_by_date = {}
    for row in rows:
        if row.get("_officialFingerprint") and row.get("historyDate"):
            berry_rows_by_date.setdefault(row.get("historyDate"), []).append(row)
    for history_date, berry_rows in berry_rows_by_date.items():
        lookup = sync_official_history_observations(
            owner_key,
            sender_employee_id,
            history_date,
            berry_rows,
        )
        occurrence_by_fingerprint = {}
        for row in berry_rows:
            if row.get("historyKind") == "seed":
                continue
            fingerprint = row.get("_officialFingerprint")
            occurrence_by_fingerprint[fingerprint] = occurrence_by_fingerprint.get(fingerprint, 0) + 1
            first_seen_at = lookup.get((fingerprint, occurrence_by_fingerprint[fingerprint]))
            if first_seen_at and observed_time_matches_history_date(first_seen_at, row.get("historyDate")):
                row["observedAt"] = first_seen_at
                row["at"] = first_seen_at
                row["_matchedTimeSource"] = "seed_berry_observed" if row.get("historyKind") == "seed" else "observed_db"
    for row in rows:
        if not row.get("at"):
            row["timeSource"] = "missing"
        elif row.get("_matchedTimeSource") == "api_order":
            row["timeSource"] = "api_order"
        elif row.get("_matchedTimeSource") == "seed_observed":
            row["timeSource"] = "seed_observed"
        elif row.get("_matchedTimeSource") == "seed_berry_observed":
            row["timeSource"] = "seed_berry_observed"
        elif row.get("_matchedTimeSource") == "observed_db":
            row["timeSource"] = "observed_db"
        elif row.get("action") == "received" and row.get("_matchedTimeSource") == "balance_detected":
            row["timeSource"] = "received_log"
        else:
            row["timeSource"] = "local_log"
    rows = [row for row in rows if not row.get("_dropUnpairedReceived")]
    rows = infer_official_history_times(remove_future_observed_history_times(sort_history_rows(rows))[:limit])
    for row in rows:
        row.pop("_officialFingerprint", None)
        row.pop("_officialSeedFingerprint", None)
        row.pop("_apiOrderTime", None)
        row.pop("_matchedTimeSource", None)
        row.pop("_apiIndex", None)
        row.pop("_dropUnpairedReceived", None)
        row.pop("ownerKey", None)
        row.pop("historyEmployeeId", None)
    return rows


def history(limit=40, owner_key=None, date=None, timezone_offset_minutes=0):
    try:
        rows = official_history(
            limit=limit,
            owner_key=owner_key,
            date=date,
            timezone_offset_minutes=timezone_offset_minutes,
        )
        if rows:
            return rows
    except Exception as exc:
        log_event({"action": "official_history_fallback", "ownerKey": owner_key, "error": str(exc)})

    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    my_employee_id = str(
        state.get("senderEmployeeId")
        or state.get("loginUserId")
        or employee_id_from_owner_key(owner_key)
        or ""
    )
    rows = []
    scan_limit = 5000 if date else limit * 5
    for event in reversed(read_jsonl(HISTORY_PATH, scan_limit)):
        is_seed_event = is_seed_transfer_history_event(event)
        if not is_transfer_history_event(event) and not is_seed_event:
            continue
        if date and event_local_date(event, timezone_offset_minutes) != date:
            continue
        sent_by_me = event.get("ownerKey") == owner_key
        received_by_me = my_employee_id and str(event.get("targetEmployeeId") or "") == my_employee_id
        if not sent_by_me and not received_by_me:
            continue
        amount = int(event.get("seedDelta") if is_seed_event else event.get("berries") or 0)
        if sent_by_me:
            action = "sent"
            counterpart = display_employee(
                event.get("target") or event.get("targetEmployeeName"),
                event.get("targetPositionName") or state.get("targetPositionName"),
            )
            sender_employee_id = my_employee_id or event.get("senderEmployeeId")
            avatar_employee_id = sender_employee_id
            avatar_name = state.get("senderEmployeeName") or state.get("loginUser") or event.get("senderEmployeeName") or ""
            sender_name = display_employee(
                state.get("senderEmployeeName")
                or state.get("loginUser")
                or event.get("senderEmployeeName"),
                event.get("senderPositionName") or state.get("senderPositionName"),
                "나",
            )
            delta = -amount
        else:
            action = "received"
            counterpart_name = (
                event.get("senderEmployeeName")
                or event.get("sender")
                or known_employee_name(owner_key=event.get("ownerKey"))
            )
            counterpart = display_employee(counterpart_name, event.get("senderPositionName"))
            sender_employee_id = str(event.get("senderEmployeeId") or employee_id_from_owner_key(event.get("ownerKey")) or "")
            avatar_employee_id = sender_employee_id
            avatar_name = counterpart_name
            sender_name = counterpart or "보낸사람"
            delta = amount
        my_display_name = display_employee(
            state.get("senderEmployeeName") or state.get("loginUser") or event.get("targetEmployeeName"),
            state.get("senderPositionName") or event.get("targetPositionName"),
            "나",
        )
        if sent_by_me:
            from_employee_id = sender_employee_id
            from_display_name = sender_name
            from_avatar_name = avatar_name
            to_employee_id = str(event.get("targetEmployeeId") or "")
            to_display_name = counterpart
            to_avatar_name = event.get("target") or event.get("targetEmployeeName") or counterpart
        else:
            from_employee_id = sender_employee_id
            from_display_name = counterpart
            from_avatar_name = avatar_name
            to_employee_id = my_employee_id
            to_display_name = my_display_name
            to_avatar_name = state.get("senderEmployeeName") or state.get("loginUser") or ""
        if action == "received":
            display_seeds = state.get("lastSeedCount")
            display_remaining = event.get("receiverRemaining")
            if display_remaining is None:
                display_remaining = amount
        else:
            display_seeds = event.get("seeds")
            display_remaining = event.get("remaining")
        item = {
            "at": event.get("at"),
            "action": action,
            "target": counterpart,
            "targetPositionName": event.get("targetPositionName"),
            "senderEmployeeId": sender_employee_id,
            "avatarEmployeeId": avatar_employee_id,
            "avatarName": avatar_name,
            "senderName": sender_name,
            "senderPositionName": event.get("senderPositionName"),
            "displayName": counterpart,
            "fromEmployeeId": from_employee_id,
            "fromDisplayName": from_display_name,
            "fromAvatarName": from_avatar_name,
            "toEmployeeId": to_employee_id,
            "toDisplayName": to_display_name,
            "toAvatarName": to_avatar_name,
            "senderIsMe": sent_by_me,
            "seeds": display_seeds,
            "berries": 0 if is_seed_event else event.get("berries"),
            "remaining": display_remaining,
            "delta": delta,
            "content": ("[씨앗선물]" if is_seed_event else "[열매선물]") + (event.get("message") or "자동 전달"),
            "historyKind": "seed" if is_seed_event else "berry",
        }
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


def local_worklog_events_by_date(owner_key, month=None, limit=20000):
    owner_key = str(owner_key or "")
    month = normalize_history_month(month)
    events_by_date = {}
    for event in reversed(read_jsonl(HISTORY_PATH, limit)):
        if event.get("action") != "worklog_sent":
            continue
        if str(event.get("ownerKey") or "") != owner_key:
            continue
        std_dt = re.sub(r"\D", "", str(event.get("stdDt") or ""))
        if len(std_dt) != 8 or not std_dt.startswith(month):
            continue
        history_date = f"{std_dt[:4]}-{std_dt[4:6]}-{std_dt[6:8]}"
        events_by_date.setdefault(history_date, event)
    return events_by_date


def worklog_approvals(owner_key=None, month=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    selected_month = normalize_history_month(month)
    local_events = local_worklog_events_by_date(owner_key, selected_month)
    client, _employee_info, _login_dataset, _employee, sender_employee_id, _sender_employee_name = account_login(owner_key)
    content = client.post_json(f"{FOREST_API}/dwBerySeed", {"stdMt": selected_month, "empId": sender_employee_id})
    if not isinstance(content, list):
        raise FruitAutoError("FOREST history did not return a list")
    approvals = {}
    for row in content:
        message = row.get("tgtMsg") or ""
        if berry_history_reward_kind(message) != "work_approval":
            continue
        day = parse_int(str(row.get("stdDt") or "").replace("일", ""), None)
        history_date = history_date_from_month_day(selected_month, day)
        if not history_date:
            continue
        local = local_events.get(history_date, {})
        project_name = local.get("projectName") or state.get("worklogProjectName") or ""
        target_employee_name = local.get("targetEmployeeName") or row.get("tgtEmpNm") or state.get("worklogTargetEmployeeName") or ""
        content_text = local.get("workDesc") or ""
        if not content_text:
            state_project_matches = not local.get("projectName") or local.get("projectName") == state.get("worklogProjectName")
            state_target_matches = not local.get("targetEmployeeId") or local.get("targetEmployeeId") == state.get("worklogTargetEmployeeId")
            if state_project_matches and state_target_matches:
                content_text = state.get("worklogContent") or ""
        approvals[history_date] = {
            "date": history_date,
            "approved": True,
            "projectName": project_name,
            "content": content_text,
            "seedMessage": local.get("seedMessage") or state.get("worklogSeedMessage") or message,
            "seedCount": local.get("seedCount") if local.get("seedCount") is not None else state.get("worklogSeedCount"),
            "targetEmployeeName": target_employee_name,
            "targetEmployeeId": local.get("targetEmployeeId") or state.get("worklogTargetEmployeeId") or "",
            "completedAt": local.get("completedAt") or local.get("at") or "",
            "officialMessage": message,
        }
    return {"month": selected_month, "items": sorted(approvals.values(), key=lambda item: item["date"])}


def worklog_approvals_local(owner_key=None, month=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    selected_month = normalize_history_month(month)
    approvals = []
    for history_date, local in local_worklog_events_by_date(owner_key, selected_month).items():
        message = local.get("officialMessage") or local.get("message") or "승인 완료"
        approvals.append({
            "date": history_date,
            "approved": True,
            "projectName": local.get("projectName") or state.get("worklogProjectName") or "",
            "content": local.get("workDesc") or state.get("worklogContent") or "",
            "seedMessage": local.get("seedMessage") or state.get("worklogSeedMessage") or message,
            "seedCount": local.get("seedCount") if local.get("seedCount") is not None else state.get("worklogSeedCount"),
            "targetEmployeeName": local.get("targetEmployeeName") or state.get("worklogTargetEmployeeName") or "",
            "targetEmployeeId": local.get("targetEmployeeId") or state.get("worklogTargetEmployeeId") or "",
            "completedAt": local.get("completedAt") or local.get("at") or "",
            "officialMessage": message,
            "source": "local",
        })
    return {"month": selected_month, "items": sorted(approvals, key=lambda item: item["date"])}


def notification_items(limit=20, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    my_employee_id = str(
        state.get("senderEmployeeId")
        or state.get("loginUserId")
        or employee_id_from_owner_key(owner_key)
        or ""
    )
    rows = []
    for event in reversed(read_jsonl(HISTORY_PATH, limit * 5)):
        if event.get("action") == "worklog_sent" and event.get("ownerKey") == owner_key:
            rows.append(
                {
                    "id": f"{event.get('at')}:{event.get('ownerKey')}:worklog:{event.get('stdDt')}",
                    "at": event.get("at"),
                    "direction": "worklog",
                    **worklog_notification_payload(event),
                }
            )
            if len(rows) >= limit:
                break
            continue
        if not is_transfer_history_event(event):
            continue
        received_by_me = my_employee_id and str(event.get("targetEmployeeId") or "") == my_employee_id
        if not received_by_me:
            continue
        rows.append(
            {
                "id": f"{event.get('at')}:{event.get('ownerKey')}:{event.get('targetEmployeeId')}:{event.get('berries')}",
                "at": event.get("at"),
                "direction": "received",
                **received_notification_payload(event),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def list_employees(client):
    content = client.post_json(f"{FOREST_API}/getEmployee", {})
    return [row for row in (content.get("resultMap") or []) if row.get("emp_id")]


def find_target_employee(client, name, emp_id=None):
    employees = list_employees(client)
    if emp_id:
        matches = [row for row in employees if row.get("emp_id") == emp_id]
    else:
        matches = [row for row in employees if row.get("emp_nm") == name]
    if not matches:
        raise FruitAutoError(f"target employee not found: {name or emp_id}")
    if len(matches) > 1:
        ids = ", ".join(f"{m.get('emp_nm')}({m.get('emp_id')})" for m in matches)
        raise FruitAutoError(f"target employee is ambiguous: {ids}")
    return matches[0]


def search_employees(query):
    query = (query or "").strip()
    if not query:
        return []
    client = Client()
    pms_token, _ = pms_login(client)
    forest_login(client, pms_token)
    employees = list_employees(client)
    results = []
    for row in employees:
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("emp_nm", "emp_id", "dept_nm", "pos_nm", "duty_nm")
        )
        if query in haystack:
            results.append(
                {
                    "emp_id": row.get("emp_id"),
                    "emp_nm": row.get("emp_nm"),
                    "dept_nm": row.get("dept_nm"),
                    "pos_nm": row.get("pos_nm"),
                    "duty_id": row.get("duty_id"),
                    "duty_nm": row.get("duty_nm"),
                }
            )
    return results[:30]


def give_all_berries(client, employee_info, target, berry_count, message):
    employee = employee_info["resultMap"][0]
    auth = employee_info["forestAuth"][0]
    payload = {
        "berrySeedGit": [
            {
                "empId": employee["emp_id"],
                "empNm": employee["emp_nm"],
                "tgtEmpId": target["emp_id"],
                "tgtEmpNm": target["emp_nm"],
                "dutyCd": target["duty_id"],
                "dutyCds": employee["duty_id"],
                "seedCnt": auth.get("seedCnt"),
                "pfmBerryCnt": str(berry_count),
                "tgtMsg": message,
            }
        ]
    }
    return client.post_json(f"{FOREST_API}/insBryGit", payload)


def transfer_balance_confirmed(before_berries, sent_berries, after_berries):
    before = parse_int(before_berries, 0)
    sent = parse_int(sent_berries, 0)
    after = parse_int(after_berries, 0)
    if sent <= 0:
        return False
    if before < sent:
        return False
    return after <= max(0, before - sent)


def check_once(dry_run=False, force=False):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    interval_seconds = get_run_interval_seconds(state)
    enabled = bool(state.get("enabled"))
    if not enabled and not force:
        state.update({"status": "off", "lastCheckedAt": now_iso()})
        save_json(STATE_PATH, state)
        return {"action": "skipped", "reason": "disabled", "enabled": enabled}

    last_attempt_age = seconds_since(state.get("lastAttemptAt"))
    if not force and last_attempt_age is not None and last_attempt_age < interval_seconds:
        return {
            "action": "skipped",
            "reason": "already_attempted_this_interval",
            "intervalSeconds": interval_seconds,
            "remainingSeconds": max(0, int(interval_seconds - last_attempt_age)),
            "lastAttemptResult": state.get("lastAttemptResult"),
        }

    slot = int(time.time() // interval_seconds)
    state.update(
        {
            "lastAttemptAt": now_iso(),
            "lastAttemptSlot": slot,
            "lastAttemptIntervalSeconds": interval_seconds,
            "lastAttemptResult": "running",
        }
    )
    save_json(STATE_PATH, state)

    client = Client()
    try:
        pms_token, login_dataset = pms_login(client)
        employee_info = forest_login(client, pms_token)
        employee = employee_info["resultMap"][0]
        owner_key, sender_employee_id, sender_employee_name = employee_identity(
            employee, login_dataset.get("SESS_USERID")
        )
    except Exception as exc:
        state.update(
            {
                "lastCheckedAt": now_iso(),
                "lastResult": "failed",
                "lastAttemptResult": f"failed: {exc}",
            }
        )
        save_json(STATE_PATH, state)
        raise

    try:
        cycle_target, target_cycle, target_cycle_index = target_from_cycle(state)
        apply_cycle_target(state, cycle_target, target_cycle, target_cycle_index)
        target_name = cycle_target.get("emp_nm")
        target_id = cycle_target.get("emp_id")
        if not target_name and not target_id:
            state.update(
                {
                    "enabled": False,
                    "status": "needs_target",
                    "lastCheckedAt": now_iso(),
                    "lastResult": "needs_target",
                    "lastAttemptResult": "needs_target",
                    "ownerKey": owner_key,
                    "senderEmployeeId": sender_employee_id,
                    "senderEmployeeName": sender_employee_name,
                }
            )
            save_json(STATE_PATH, state)
            return {"action": "skipped", "reason": "needs_target", "enabled": False}
        target = find_target_employee(client, target_name, target_id)
        if target.get("emp_id") == employee.get("emp_id"):
            raise FruitAutoError("cannot send berries to yourself")
        target_name = target.get("emp_nm") or target_name
        if target_cycle:
            target_cycle[target_cycle_index] = employee_record(
                target.get("emp_id"),
                target_name,
                target.get("duty_id") or cycle_target.get("duty_id"),
                target.get("dept_nm") or cycle_target.get("dept_nm"),
                employee_position(target),
            )
        seeds, berries = current_seed_fruit(client, employee)

        state.update(
            {
                "enabled": enabled,
                "status": "on" if enabled else "forced",
                "targetEmployeeName": target_name,
                "targetEmployeeId": target.get("emp_id"),
                "ownerKey": owner_key,
                "senderEmployeeId": sender_employee_id,
                "senderEmployeeName": sender_employee_name,
                "senderPositionName": employee_position(employee),
                "lastCheckedAt": now_iso(),
                "lastSeedCount": seeds,
                "lastBerryCount": berries,
                "balanceCheckedAt": now_iso(),
                "lastCommonObservedAt": attempt_at.isoformat(),
                "lastCommonObserveResult": "transfer_check",
            }
        )

        if berries <= 0:
            state["lastResult"] = "no_berries"
            state["lastAttemptResult"] = "no_berries"
            save_json(STATE_PATH, state)
            log_event(
                {
                    "action": "check",
                    "seeds": seeds,
                    "berries": berries,
                    "target": target_name,
                    "ownerKey": owner_key,
                    "slot": slot,
                }
            )
            return {"action": "none", "berries": berries, "target": target_name}

        message = state.get("giftMessage") or "자동 전달"
        if dry_run:
            state["lastResult"] = f"dry_run_would_send_{berries}"
            state["lastAttemptResult"] = state["lastResult"]
            save_json(STATE_PATH, state)
            return {
                "action": "dry_run",
                "berries": berries,
                "target": target_name,
                "targetEmployeeId": target.get("emp_id"),
            }

        give_all_berries(client, employee_info, target, berries, message)
        remaining_seeds, remaining = current_seed_fruit(client, employee)
        if not transfer_balance_confirmed(berries, berries, remaining):
            state.update(
                {
                    "lastSeedCount": remaining_seeds,
                    "lastBerryCount": remaining,
                    "balanceCheckedAt": now_iso(),
                    "lastResult": f"send_not_confirmed_remaining_{remaining}",
                    "lastAttemptResult": f"send_not_confirmed_remaining_{remaining}",
                }
            )
            save_json(STATE_PATH, state)
            log_event(
                {
                    "action": "send_not_confirmed",
                    "berries": berries,
                    "remaining": remaining,
                    "target": target_name,
                    "targetEmployeeId": target.get("emp_id"),
                    "ownerKey": owner_key,
                    "slot": slot,
                }
            )
            return {
                "action": "failed",
                "reason": "send_not_confirmed",
                "berries": berries,
                "remaining": remaining,
                "target": target_name,
                "targetEmployeeId": target.get("emp_id"),
                "ownerKey": owner_key,
            }
        state.update(
            {
                "lastSentAt": now_iso(),
                "lastSeedCount": remaining_seeds,
                "lastBerryCount": remaining,
                "balanceCheckedAt": now_iso(),
                "lastResult": f"sent_{berries}_remaining_{remaining}",
                "lastAttemptResult": f"sent_{berries}_remaining_{remaining}",
            }
        )
        save_json(STATE_PATH, state)
        sent_event = {
            "action": "sent",
            "berries": berries,
            "seeds": remaining_seeds,
            "remaining": remaining,
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "senderPositionName": employee_position(employee),
            "target": target_name,
            "targetEmployeeId": target.get("emp_id"),
            "targetPositionName": employee_position(target),
            "ownerKey": owner_key,
            "slot": slot,
            "message": message,
        }
        log_event(sent_event)
        record_transfer_history(sent_event)
        return {
            "action": "sent",
            "berries": berries,
            "remaining": remaining,
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "senderPositionName": employee_position(employee),
            "target": target_name,
            "targetEmployeeId": target.get("emp_id"),
            "targetPositionName": employee_position(target),
        }
    except Exception as exc:
        state.update(
            {
                "lastCheckedAt": now_iso(),
                "lastResult": "failed",
                "lastAttemptResult": f"failed: {exc}",
                "ownerKey": owner_key,
                "senderEmployeeId": sender_employee_id,
                "senderEmployeeName": sender_employee_name,
            }
        )
        save_json(STATE_PATH, state)
        raise


def set_enabled(enabled):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    if enabled and not (state.get("targetEmployeeId") and state.get("targetEmployeeName")):
        raise FruitAutoError("대상 직원을 먼저 검색해서 선택하세요.")
    if not enabled:
        state.update(
            {
                "targetEmployeeName": None,
                "targetEmployeeId": None,
                "targetDutyId": None,
                "targetDeptName": None,
                "targetPositionName": None,
            }
        )
    state.update(
        {
            "enabled": enabled,
            "status": "on" if enabled else "off",
            "updatedAt": now_iso(),
        }
    )
    save_json(STATE_PATH, state)
    log_event({"action": "enabled" if enabled else "disabled"})
    return state


def set_target_by_name(query):
    query = (query or "").strip()
    if not query:
        raise FruitAutoError("missing target name")

    client = Client()
    pms_token, _ = pms_login(client)
    forest_login(client, pms_token)
    employees = list_employees(client)
    exact_matches = [row for row in employees if row.get("emp_nm") == query]
    matches = exact_matches or [
        row for row in employees
        if query in " ".join(
            str(row.get(key) or "")
            for key in ("emp_nm", "emp_id", "dept_nm", "pos_nm", "duty_nm")
        )
    ]
    if not matches:
        raise FruitAutoError(f"target employee not found: {query}")
    if len(matches) > 1:
        ids = ", ".join(f"{m.get('emp_nm')}({m.get('emp_id')})" for m in matches[:10])
        raise FruitAutoError(f"target employee is ambiguous: {ids}")

    target = matches[0]
    return set_target(
        target.get("emp_id"),
        target.get("emp_nm"),
        target.get("duty_id"),
        target.get("dept_nm"),
        target.get("pos_nm"),
    )


def set_target(emp_id, name=None, duty_id=None, dept_nm=None, pos_nm=None):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    state.update(
        {
            "targetEmployeeId": emp_id,
            "targetEmployeeName": name or state.get("targetEmployeeName"),
            "targetDutyId": duty_id,
            "targetDeptName": dept_nm,
            "targetPositionName": pos_nm,
            "updatedAt": now_iso(),
        }
    )
    save_json(STATE_PATH, state)
    log_event({"action": "target_set", "targetEmployeeId": emp_id, "targetEmployeeName": name})
    return state


def set_message(message):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    state["giftMessage"] = message or DEFAULT_STATE["giftMessage"]
    state["updatedAt"] = now_iso()
    save_json(STATE_PATH, state)
    return state


def logout():
    if SECRETS_PATH.exists():
        SECRETS_PATH.unlink()
    state = load_json(STATE_PATH, DEFAULT_STATE)
    state.update(
        {
            "enabled": False,
            "status": "off",
            "targetEmployeeName": None,
            "targetEmployeeId": None,
            "targetDutyId": None,
            "targetDeptName": None,
            "targetPositionName": None,
            "loginSavedAt": None,
            "loginUser": None,
            "loginUserId": None,
            "loginEmployeeNo": None,
            "senderEmployeeId": None,
            "senderEmployeeName": None,
            "lastResult": "logged_out",
            "lastAttemptResult": "logged_out",
            "nextRunAt": None,
            "updatedAt": now_iso(),
        }
    )
    save_json(STATE_PATH, state)
    log_event({"action": "logged_out"})
    return state


def set_run_interval(minutes):
    try:
        next_minutes = int(minutes)
    except (TypeError, ValueError):
        raise FruitAutoError("전송 간격은 숫자로 입력하세요.")
    next_minutes = max(MIN_RUN_INTERVAL_MINUTES, min(MAX_RUN_INTERVAL_MINUTES, next_minutes))
    state = load_json(STATE_PATH, DEFAULT_STATE)
    state["runIntervalMinutes"] = next_minutes
    state["updatedAt"] = now_iso()
    save_json(STATE_PATH, state)
    log_event({"action": "interval_set", "runIntervalMinutes": next_minutes})
    return state


def failed_slot_result(exc):
    state = load_json(STATE_PATH, DEFAULT_STATE)
    return {
        "action": "failed",
        "error": str(exc),
        "nextRetry": "next_interval",
        "intervalSeconds": get_run_interval_seconds(state),
        "lastAttemptSlot": state.get("lastAttemptSlot"),
        "lastAttemptResult": state.get("lastAttemptResult"),
    }


def run_daemon():
    claim_daemon_pid()

    def handle_stop(_signum, _frame):
        log_event({"action": "daemon_stopped"})
        release_daemon_pid()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    try:
        log_event({"action": "daemon_started", "intervalSeconds": get_run_interval_seconds()})
        while True:
            started = time.time()
            try:
                result = check_once()
                if result.get("reason") != "already_attempted_this_interval":
                    log_event({"action": "daemon_tick", "result": result})
                notify_result(result)
            except Exception as exc:
                log_event({"action": "daemon_error", "error": str(exc)})
                notify_result({"action": "failed", "error": str(exc)})

            state = load_json(STATE_PATH, DEFAULT_STATE)
            interval_seconds = get_run_interval_seconds(state)
            last_attempt_age = seconds_since(state.get("lastAttemptAt"))
            if not state.get("enabled"):
                sleep_seconds = 15
            elif last_attempt_age is None:
                sleep_seconds = 15
            else:
                sleep_seconds = min(15, max(1, interval_seconds - last_attempt_age))
            time.sleep(sleep_seconds)
    finally:
        release_daemon_pid()


# Multi-user account layer. The original state shape is kept for compatibility,
# while active app sessions and daemon work use per-account entries.
ACCOUNT_DEFAULT = {
    key: value
    for key, value in DEFAULT_STATE.items()
    if key not in ("accounts", "sessions")
}


def load_secrets():
    secrets = load_json(SECRETS_PATH, {})
    if "accounts" not in secrets:
        accounts = {}
        if secrets.get("pms_id") and secrets.get("pms_password"):
            legacy_key = load_json(STATE_PATH, DEFAULT_STATE).get("ownerKey") or "legacy"
            accounts[legacy_key] = {
                "pms_id": secrets.get("pms_id"),
                "pms_password": secrets.get("pms_password"),
            }
        secrets = {"accounts": accounts, "sessions": secrets.get("sessions") or {}}
    secrets.setdefault("accounts", {})
    secrets.setdefault("sessions", {})
    return secrets


def save_secrets(secrets):
    save_json(SECRETS_PATH, secrets)
    try:
        SECRETS_PATH.chmod(0o600)
    except OSError:
        pass


def load_all_state():
    state = load_json(STATE_PATH, DEFAULT_STATE)
    state.setdefault("accounts", {})
    if not state["accounts"] and state.get("ownerKey"):
        state["accounts"][state["ownerKey"]] = {
            key: state.get(key)
            for key in ACCOUNT_DEFAULT
            if key in state
        }
    return state


def get_account_state(owner_key):
    state = load_all_state()
    account = dict(ACCOUNT_DEFAULT)
    account.update(state.get("accounts", {}).get(owner_key, {}))
    account["ownerKey"] = owner_key
    return infer_target_for_account(owner_key, account)


def save_account_state(owner_key, account):
    state = load_all_state()
    accounts = state.setdefault("accounts", {})
    account = dict(account)
    account["ownerKey"] = owner_key
    accounts[owner_key] = account
    state["activeOwnerKey"] = owner_key
    # Keep top-level mirrors for older CLI/status callers.
    state.update({key: account.get(key) for key in ACCOUNT_DEFAULT})
    state["accounts"] = accounts
    save_json(STATE_PATH, state)
    return account


def save_single_account_state(owner_key, account):
    state = load_all_state()
    account = dict(account)
    account["ownerKey"] = owner_key
    state["accounts"] = {owner_key: account}
    state["activeOwnerKey"] = owner_key
    state.update({key: account.get(key) for key in ACCOUNT_DEFAULT})
    save_json(STATE_PATH, state)
    return account


def remove_account_state(owner_key):
    state = load_all_state()
    state["accounts"] = {}
    if state.get("activeOwnerKey") == owner_key:
        state["activeOwnerKey"] = None
    logged_out = dict(ACCOUNT_DEFAULT)
    logged_out.update(
        {
            "enabled": False,
            "status": "off",
            "lastResult": "logged_out",
            "lastAttemptResult": "logged_out",
            "updatedAt": now_iso(),
        }
    )
    state.update({key: logged_out.get(key) for key in ACCOUNT_DEFAULT})
    save_json(STATE_PATH, state)
    return logged_out


def revoke_sessions_for_owner(secrets, owner_key):
    sessions = secrets.setdefault("sessions", {})
    for token, session in list(sessions.items()):
        if session_owner_key(session) == owner_key:
            sessions.pop(token, None)
    return secrets


def session_owner_key(session):
    if isinstance(session, dict) and session.get("version") in (2, SESSION_SCHEMA_VERSION):
        return session.get("ownerKey")
    return None


def session_expires_at():
    return iso_after(SESSION_TTL_SECONDS)


def session_expired(session):
    if not isinstance(session, dict):
        return True
    expires_at = session.get("expiresAt")
    if not expires_at:
        return False
    age = seconds_since(expires_at)
    return age is not None and age > 0


def new_session_record(owner_key):
    return {
        "version": SESSION_SCHEMA_VERSION,
        "ownerKey": owner_key,
        "createdAt": now_iso(),
        "expiresAt": session_expires_at(),
    }


def owner_from_session(session_token, device_id=None):
    if not session_token:
        return None
    secrets = load_secrets()
    sessions = secrets.setdefault("sessions", {})
    session = sessions.get(session_token)
    if session_expired(session):
        sessions.pop(session_token, None)
        save_secrets(secrets)
        return None
    owner_key = session_owner_key(session)
    if owner_key and owner_key in secrets.get("accounts", {}):
        session["expiresAt"] = session_expires_at()
        save_secrets(secrets)
        return owner_key
    return None


def issue_session(owner_key=None, device_id=None):
    owner_key = require_owner(owner_key)
    secrets = load_secrets()
    sessions = secrets.setdefault("sessions", {})
    changed = False
    for session_token, session_owner in list(sessions.items()):
        if session_expired(session_owner):
            sessions.pop(session_token, None)
            changed = True
            continue
        if session_owner_key(session_owner) == owner_key:
            session_owner["expiresAt"] = session_expires_at()
            save_secrets(secrets)
            return {"sessionToken": session_token, "ownerKey": owner_key}
    session_token = uuid.uuid4().hex
    sessions[session_token] = new_session_record(owner_key)
    save_secrets(secrets)
    return {"sessionToken": session_token, "ownerKey": owner_key}


def require_owner(owner_key):
    if not owner_key:
        raise FruitAutoError("로그인이 필요합니다.")
    if owner_key not in load_secrets().get("accounts", {}):
        raise FruitAutoError("저장된 로그인 세션이 없습니다. 다시 로그인하세요.")
    return owner_key


def is_push_enabled(owner_key):
    if not owner_key:
        return True
    state = load_all_state()
    account = state.get("accounts", {}).get(owner_key, {})
    return account.get("pushEnabled", DEFAULT_STATE["pushEnabled"]) is not False


def account_credentials(owner_key):
    owner_key = require_owner(owner_key)
    account = load_secrets().get("accounts", {}).get(owner_key) or {}
    if not account.get("pms_id") or not account.get("pms_password"):
        raise FruitAutoError("저장된 PMS 로그인 정보가 없습니다.")
    return account["pms_id"], account["pms_password"]


def account_login(owner_key):
    pms_id, pms_password = account_credentials(owner_key)
    client = Client()
    pms_token, login_dataset = pms_login(client, pms_id, pms_password)
    employee_info = forest_login(client, pms_token)
    employee = employee_info["resultMap"][0]
    actual_owner_key, sender_employee_id, sender_employee_name = employee_identity(
        employee, login_dataset.get("SESS_USERID")
    )
    if actual_owner_key != owner_key:
        raise FruitAutoError("저장된 계정 정보가 현재 세션과 일치하지 않습니다. 다시 로그인하세요.")
    return client, employee_info, login_dataset, employee, sender_employee_id, sender_employee_name


def save_credentials(pms_id, pms_password, device_id=None):
    client = Client()
    token, dataset = pms_login(client, pms_id, pms_password)
    employee_info = forest_login(client, token)
    employee = employee_info["resultMap"][0]
    owner_key, sender_employee_id, sender_employee_name = employee_identity(
        employee, dataset.get("SESS_USERID")
    )
    if not owner_key:
        raise FruitAutoError("Forest employee id를 확인하지 못했습니다.")

    account = get_account_state(owner_key)
    secrets = load_secrets()
    secrets.setdefault("accounts", {})
    existing_secret = secrets["accounts"].get(owner_key) or {}
    secrets["accounts"][owner_key] = {
        **existing_secret,
        "pms_id": pms_id,
        "pms_password": pms_password,
    }
    secrets["sessions"] = {
        token: session
        for token, session in secrets.get("sessions", {}).items()
        if session_owner_key(session) != owner_key
    }
    session_token = uuid.uuid4().hex
    secrets["sessions"][session_token] = new_session_record(owner_key)
    save_secrets(secrets)

    account.update(
        {
            "loginSavedAt": now_iso(),
            "loginUser": dataset.get("SESS_USERNAME"),
            "loginUserId": dataset.get("SESS_USERID"),
            "loginEmployeeNo": dataset.get("SESS_EMPNO"),
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "ownerKey": owner_key,
            "updatedAt": now_iso(),
        }
    )
    save_account_state(owner_key, account)
    log_event({"action": "credentials_saved", "ownerKey": owner_key, "user": dataset.get("SESS_USERNAME")})
    return {
        "success": True,
        "sessionToken": session_token,
        "ownerKey": owner_key,
        "user": dataset.get("SESS_USERNAME"),
        "userId": dataset.get("SESS_USERID"),
        "employeeNo": dataset.get("SESS_EMPNO"),
        **account,
    }


def refresh_balance(force=False, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    checked_at = state.get("balanceCheckedAt") or state.get("lastCheckedAt")
    if not force and checked_at:
        age = seconds_since(checked_at)
        if age is not None and age < 45:
            return state

    client, employee_info, login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
    seeds, berries = current_seed_fruit(client, employee)
    state.update(
        {
            "lastSeedCount": seeds,
            "lastBerryCount": berries,
            "balanceCheckedAt": now_iso(),
            "lastCheckedAt": now_iso(),
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "loginUser": state.get("loginUser") or login_dataset.get("SESS_USERNAME"),
            "loginUserId": state.get("loginUserId") or login_dataset.get("SESS_USERID"),
            "loginEmployeeNo": state.get("loginEmployeeNo") or login_dataset.get("SESS_EMPNO"),
        }
    )
    save_account_state(owner_key, state)
    log_event({"action": "balance", "seeds": seeds, "berries": berries, "ownerKey": owner_key})
    return state


def search_employees(query, owner_key=None):
    owner_key = require_owner(owner_key)
    query = (query or "").strip()
    if not query:
        return []
    client, _employee_info, _login_dataset, _employee, _sender_id, _sender_name = account_login(owner_key)
    employees = list_employees(client)
    results = []
    for row in employees:
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("emp_nm", "emp_id", "dept_nm", "pos_nm", "duty_nm")
        )
        if query in haystack:
            results.append(
                {
                    "emp_id": row.get("emp_id"),
                    "emp_nm": row.get("emp_nm"),
                    "dept_nm": row.get("dept_nm"),
                    "pos_nm": row.get("pos_nm"),
                    "duty_id": row.get("duty_id"),
                    "duty_nm": row.get("duty_nm"),
                }
            )
    return results[:30]


def set_target(emp_id, name=None, duty_id=None, dept_nm=None, pos_nm=None, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    new_target = employee_record(emp_id, name, duty_id, dept_nm, pos_nm)
    if not new_target.get("emp_id") or not new_target.get("emp_nm"):
        raise FruitAutoError("자동전송 받을 직원을 선택해 주세요.")
    cycle, index = normalize_target_cycle(state)
    existing_index = next((i for i, item in enumerate(cycle) if item.get("emp_id") == new_target["emp_id"]), None)
    if existing_index is None:
        cycle.append(new_target)
        if len(cycle) == 1:
            index = 0
    else:
        cycle[existing_index] = {**cycle[existing_index], **new_target}
        if not state.get("targetEmployeeId"):
            index = existing_index
    state.update({"targetLocked": True, "targetSelectedAt": now_iso(), "updatedAt": now_iso()})
    apply_cycle_target(state, cycle[index], cycle, index)
    save_account_state(owner_key, state)
    log_event(
        {
            "action": "target_added",
            "ownerKey": owner_key,
            "targetEmployeeId": new_target.get("emp_id"),
            "targetEmployeeName": new_target.get("emp_nm"),
            "cycleSize": len(cycle),
        }
    )
    return state


def remove_cycle_target(emp_id, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    remove_id = str(emp_id or "").strip()
    if not remove_id:
        raise FruitAutoError("삭제할 대상 직원이 없습니다.")
    cycle, index = normalize_target_cycle(state)
    current_id = str(state.get("targetEmployeeId") or "")
    remove_index = next((i for i, item in enumerate(cycle) if item.get("emp_id") == remove_id), None)
    if remove_index is None:
        return state
    cycle.pop(remove_index)
    if cycle:
        if remove_id == current_id:
            index = min(remove_index, len(cycle) - 1)
        elif remove_index < index:
            index -= 1
        index %= len(cycle)
        apply_cycle_target(state, cycle[index], cycle, index)
    else:
        apply_cycle_target(state, {}, [], 0)
        state["targetLocked"] = False
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    log_event({"action": "target_removed", "ownerKey": owner_key, "targetEmployeeId": remove_id, "cycleSize": len(cycle)})
    return state


def set_message(message, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    message = str(message or "").strip()
    if not message:
        raise FruitAutoError("메시지를 작성해주세요.")
    state["giftMessage"] = message
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    return state


def set_send_berry_count(count, send_all=False, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    if not send_all and str(count or "").strip() == "":
        raise FruitAutoError("보낼 열매 수를 작성해주세요.")
    try:
        requested_count = int(count or 0)
    except (TypeError, ValueError):
        requested_count = 0
    if not send_all and requested_count <= 0:
        raise FruitAutoError("보낼 열매 수를 작성해주세요.")
    state["sendBerryCount"] = get_send_berry_count({"sendBerryCount": count})
    state["sendAllBerries"] = bool(send_all)
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    return state


def set_push_enabled(enabled, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    state["pushEnabled"] = bool(enabled)
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    log_event({"action": "push_enabled" if enabled else "push_disabled", "ownerKey": owner_key})
    return state


def set_run_interval(minutes, owner_key=None):
    owner_key = require_owner(owner_key)
    try:
        next_minutes = int(minutes)
    except (TypeError, ValueError):
        raise FruitAutoError("전송 간격은 숫자로 입력하세요.")
    next_minutes = max(MIN_RUN_INTERVAL_MINUTES, min(MAX_RUN_INTERVAL_MINUTES, next_minutes))
    state = get_account_state(owner_key)
    state["runIntervalMinutes"] = next_minutes
    if state.get("enabled"):
        schedule_next_run(state, dt.datetime.now(dt.timezone.utc))
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    log_event({"action": "interval_set", "ownerKey": owner_key, "runIntervalMinutes": next_minutes})
    return state


def set_enabled(enabled, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    if enabled:
        validate_transfer_settings(state)
    next_run_at = None
    if enabled:
        schedule_next_run(state)
        next_run_at = state.get("nextRunAt")
    state.update(
        {
            "enabled": enabled,
            "status": "on" if enabled else "off",
            "nextRunAt": next_run_at,
            "updatedAt": now_iso(),
        }
    )
    if not enabled:
        state["nextRunDelaySeconds"] = None
    save_account_state(owner_key, state)
    log_event({"action": "enabled" if enabled else "disabled", "ownerKey": owner_key})
    return state


def logout(owner_key=None, session_token=None):
    owner_key = require_owner(owner_key)
    secrets = load_secrets()
    if session_token:
        secrets.setdefault("sessions", {}).pop(session_token, None)
    else:
        revoke_sessions_for_owner(secrets, owner_key)
        secrets.setdefault("accounts", {}).pop(owner_key, None)
    save_secrets(secrets)
    if owner_key in secrets.get("accounts", {}):
        state = get_account_state(owner_key)
        state.update(
            {
                "enabled": False,
                "status": "off",
                "lastResult": "logged_out",
                "lastAttemptResult": "logged_out",
                "updatedAt": now_iso(),
            }
        )
        save_account_state(owner_key, state)
    else:
        state = remove_account_state(owner_key)
    log_event({"action": "logged_out", "ownerKey": owner_key})
    return state


def common_observe_delay(account, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    last_observed = parse_iso(account.get("lastCommonObservedAt"))
    if last_observed is None:
        return 0
    return max(0, int((last_observed + dt.timedelta(seconds=COMMON_OBSERVE_INTERVAL_SECONDS) - now).total_seconds()))


def common_observe_due(account, now=None):
    return common_observe_delay(account, now) <= 0


def observe_received_history(owner_key=None, force=False):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if not force and not common_observe_due(state, now):
        return {
            "action": "skipped",
            "reason": "common_observe_not_due",
            "ownerKey": owner_key,
            "remainingSeconds": common_observe_delay(state, now),
        }

    client, _employee_info, _login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
    seeds, berries = current_seed_fruit(client, employee)
    received_events = record_received_history_from_official(
        client,
        owner_key,
        sender_employee_id,
        sender_employee_name,
        employee_position(employee),
        now,
        window_seconds=COMMON_OBSERVE_INTERVAL_SECONDS + 120,
    )
    state.update(
        {
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "senderPositionName": employee_position(employee),
            "lastSeedCount": seeds,
            "lastBerryCount": berries,
            "balanceCheckedAt": now.isoformat(),
            "lastCommonObservedAt": now.isoformat(),
            "lastCommonObserveResult": f"received_{len(received_events)}",
            "updatedAt": now.isoformat(),
        }
    )
    if received_events:
        state["lastReceivedHistoryAt"] = received_events[0].get("at")
        state["lastReceivedHistoryCount"] = len(received_events)
    save_account_state(owner_key, state)
    for received_event in received_events:
        notify_web_push(received_notification_payload(received_event), [owner_key])
    return {
        "action": "observed",
        "ownerKey": owner_key,
        "seeds": seeds,
        "berries": berries,
        "receivedEvents": len(received_events),
        "observedAt": now.isoformat(),
    }


def check_once(dry_run=False, force=False, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    interval_seconds = get_run_interval_seconds(state)
    enabled = bool(state.get("enabled"))
    if not enabled and not force:
        state.update({"status": "off", "lastCheckedAt": now_iso(), "nextRunAt": None})
        save_account_state(owner_key, state)
        return {"action": "skipped", "reason": "disabled", "enabled": enabled, "ownerKey": owner_key}

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    next_run = parse_iso(state.get("nextRunAt"))
    if not force and next_run is not None and now < next_run:
        remaining_seconds = max(0, int((next_run - now).total_seconds()))
        return {
            "action": "skipped",
            "reason": "waiting_next_run",
            "ownerKey": owner_key,
            "intervalSeconds": interval_seconds,
            "remainingSeconds": remaining_seconds,
            "nextRunAt": state.get("nextRunAt"),
        }

    last_attempt_age = seconds_since(state.get("lastAttemptAt"))
    if not force and last_attempt_age is not None and last_attempt_age < interval_seconds:
        last_attempt = parse_iso(state.get("lastAttemptAt"))
        schedule_next_run(state, last_attempt)
        next_run = parse_iso(state.get("nextRunAt"))
        remaining_seconds = max(0, int((next_run - now).total_seconds())) if next_run else max(0, int(interval_seconds - last_attempt_age))
        save_account_state(owner_key, state)
        return {
            "action": "skipped",
            "reason": "already_attempted_this_interval",
            "ownerKey": owner_key,
            "intervalSeconds": interval_seconds,
            "remainingSeconds": remaining_seconds,
            "lastAttemptResult": state.get("lastAttemptResult"),
            "nextRunAt": state.get("nextRunAt"),
        }

    slot = int(time.time() // interval_seconds)
    attempt_at = now
    next_delay_seconds = schedule_next_run(state, attempt_at)
    state.update(
        {
            "lastAttemptAt": attempt_at.isoformat(),
            "lastAttemptSlot": slot,
            "lastAttemptIntervalSeconds": interval_seconds,
            "lastAttemptResult": "running",
        }
    )
    save_account_state(owner_key, state)

    try:
        client, employee_info, login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
        cycle_target, target_cycle, target_cycle_index = target_from_cycle(state)
        apply_cycle_target(state, cycle_target, target_cycle, target_cycle_index)
        target_name = cycle_target.get("emp_nm")
        target_id = cycle_target.get("emp_id")
        if not target_name and not target_id:
            state.update(
                {
                    "enabled": False,
                    "status": "needs_target",
                    "lastCheckedAt": now_iso(),
                    "lastResult": "needs_target",
                    "lastAttemptResult": "needs_target",
                    "senderEmployeeId": sender_employee_id,
                    "senderEmployeeName": sender_employee_name,
                    "senderPositionName": employee_position(employee),
                }
            )
            save_account_state(owner_key, state)
            return {"action": "skipped", "reason": "needs_target", "enabled": False, "ownerKey": owner_key}

        target = find_target_employee(client, target_name, target_id)
        if target.get("emp_id") == employee.get("emp_id"):
            raise FruitAutoError("cannot send berries to yourself")
        target_name = target.get("emp_nm") or target_name
        if target_cycle:
            target_cycle[target_cycle_index] = employee_record(
                target.get("emp_id"),
                target_name,
                target.get("duty_id") or cycle_target.get("duty_id"),
                target.get("dept_nm") or cycle_target.get("dept_nm"),
                employee_position(target),
            )
        seeds, berries = current_seed_fruit(client, employee)
        state.update(
            {
                "enabled": enabled,
                "status": "on" if enabled else "forced",
                "targetEmployeeName": target.get("emp_nm") or target_name,
                "targetEmployeeId": target.get("emp_id"),
                "targetDutyId": target.get("duty_id") or cycle_target.get("duty_id"),
                "targetDeptName": target.get("dept_nm") or cycle_target.get("dept_nm"),
                "targetPositionName": employee_position(target),
                "targetCycle": target_cycle,
                "targetCycleIndex": target_cycle_index,
                "senderEmployeeId": sender_employee_id,
                "senderEmployeeName": sender_employee_name,
                "senderPositionName": employee_position(employee),
                "lastCheckedAt": now_iso(),
                "lastSeedCount": seeds,
                "lastBerryCount": berries,
                "balanceCheckedAt": now_iso(),
            }
        )
        if berries <= 0:
            checked_at = now_iso()
            last_no_berries_log_age = seconds_since(state.get("lastNoBerriesLogAt"))
            state["lastResult"] = "no_berries"
            state["lastAttemptResult"] = "no_berries"
            state["lastNoBerriesAt"] = checked_at
            state["pendingReceivedAt"] = None
            state["pendingEligibleAt"] = None
            state["pendingBerryCount"] = None
            state["pendingTargetEmployeeId"] = None
            should_log_no_berries = (
                last_no_berries_log_age is None or last_no_berries_log_age >= 3600
            )
            if should_log_no_berries:
                state["lastNoBerriesLogAt"] = checked_at
            save_account_state(owner_key, state)
            if should_log_no_berries:
                log_event(
                    {
                        "action": "no_berries",
                        "seeds": seeds,
                        "berries": berries,
                        "target": target_name,
                        "ownerKey": owner_key,
                        "slot": slot,
                        "nextRunAt": state.get("nextRunAt"),
                    }
                )
            return {"action": "none", "berries": berries, "target": target_name, "ownerKey": owner_key}

        message = state.get("giftMessage") or "자동 전달"
        requested_berries = get_send_berry_count(state)
        send_all_berries = get_send_all_berries(state)
        send_berries = berries if send_all_berries else min(berries, requested_berries)
        pending_received_at = parse_iso(state.get("pendingReceivedAt"))
        pending_target_id = str(state.get("pendingTargetEmployeeId") or "")
        current_target_id = str(target.get("emp_id") or "")
        pending_berry_count = parse_int(state.get("pendingBerryCount"), 0)
        if pending_received_at is None or pending_target_id != current_target_id or send_berries > pending_berry_count:
            pending_received_at = attempt_at
            state["pendingReceivedAt"] = pending_received_at.isoformat()
            state["pendingEligibleAt"] = iso_after(next_delay_seconds, pending_received_at)
            state["pendingTargetEmployeeId"] = target.get("emp_id")
        state["pendingBerryCount"] = send_berries
        received_events = record_received_history_from_official(
            client,
            owner_key,
            sender_employee_id,
            sender_employee_name,
            employee_position(employee),
            attempt_at,
            window_seconds=COMMON_OBSERVE_INTERVAL_SECONDS + 120,
        )
        balance_received_event = None
        if not received_events:
            balance_received_event = record_balance_detected_received_history(
                owner_key,
                sender_employee_id,
                sender_employee_name,
                employee_position(employee),
                target.get("emp_id"),
                target_name,
                employee_position(target),
                send_berries,
                pending_received_at,
                seeds=seeds,
                remaining=berries,
            )
            if balance_received_event:
                received_events = [balance_received_event]
        if received_events:
            state["lastReceivedHistoryAt"] = received_events[0].get("at")
            state["lastReceivedHistoryCount"] = len(received_events)
            for received_event in received_events:
                notify_web_push(received_notification_payload(received_event), [owner_key])
        pending_eligible_at = parse_iso(state.get("pendingEligibleAt"))
        if pending_eligible_at is None:
            pending_eligible_at = pending_received_at + dt.timedelta(seconds=next_delay_seconds)
            state["pendingEligibleAt"] = pending_eligible_at.replace(microsecond=0).isoformat()
        eligible_at = pending_eligible_at
        if not force and attempt_at < eligible_at:
            remaining_seconds = max(0, int((eligible_at - attempt_at).total_seconds()))
            state["nextRunAt"] = eligible_at.replace(microsecond=0).isoformat()
            state["lastResult"] = f"waiting_send_delay_{remaining_seconds}s"
            state["lastAttemptResult"] = state["lastResult"]
            save_account_state(owner_key, state)
            log_event(
                {
                    "action": "send_delay_wait",
                    "berries": berries,
                    "target": target_name,
                    "targetEmployeeId": target.get("emp_id"),
                    "ownerKey": owner_key,
                    "receivedAt": state.get("pendingReceivedAt"),
                    "eligibleAt": state.get("nextRunAt"),
                    "remainingSeconds": remaining_seconds,
                    "slot": slot,
                }
            )
            return {
                "action": "waiting",
                "reason": "send_delay",
                "berries": berries,
                "target": target_name,
                "targetEmployeeId": target.get("emp_id"),
                "ownerKey": owner_key,
                "receivedAt": state.get("pendingReceivedAt"),
                "eligibleAt": state.get("nextRunAt"),
                "remainingSeconds": remaining_seconds,
            }
        if dry_run:
            state["lastResult"] = f"dry_run_would_send_{send_berries}"
            state["lastAttemptResult"] = state["lastResult"]
            save_account_state(owner_key, state)
            return {"action": "dry_run", "berries": send_berries, "requestedBerries": requested_berries, "sendAllBerries": send_all_berries, "availableBerries": berries, "target": target_name, "targetEmployeeId": target.get("emp_id"), "ownerKey": owner_key}

        give_all_berries(client, employee_info, target, send_berries, message)
        remaining_seeds, remaining = current_seed_fruit(client, employee)
        if not transfer_balance_confirmed(berries, send_berries, remaining):
            state.update(
                {
                    "lastSeedCount": remaining_seeds,
                    "lastBerryCount": remaining,
                    "balanceCheckedAt": now_iso(),
                    "lastResult": f"send_not_confirmed_remaining_{remaining}",
                    "lastAttemptResult": f"send_not_confirmed_remaining_{remaining}",
                }
            )
            save_account_state(owner_key, state)
            log_event(
                {
                    "action": "send_not_confirmed",
                    "berries": send_berries,
                    "availableBerries": berries,
                    "remaining": remaining,
                    "target": target_name,
                    "targetEmployeeId": target.get("emp_id"),
                    "ownerKey": owner_key,
                    "slot": slot,
                }
            )
            return {
                "action": "failed",
                "reason": "send_not_confirmed",
                "berries": send_berries,
                "availableBerries": berries,
                "remaining": remaining,
                "target": target_name,
                "targetEmployeeId": target.get("emp_id"),
                "ownerKey": owner_key,
            }
        state.update(
            {
                "lastSentAt": now_iso(),
                "lastSeedCount": remaining_seeds,
                "lastBerryCount": remaining,
                "balanceCheckedAt": now_iso(),
                "lastResult": f"sent_{send_berries}_remaining_{remaining}",
                "lastAttemptResult": f"sent_{send_berries}_remaining_{remaining}",
                "pendingReceivedAt": None,
                "pendingEligibleAt": None,
                "pendingBerryCount": None,
                "pendingTargetEmployeeId": None,
            }
        )
        advance_target_cycle(state)
        state["updatedAt"] = now_iso()
        save_account_state(owner_key, state)
        sent_event = {
            "action": "sent",
            "berries": send_berries,
            "requestedBerries": requested_berries,
            "sendAllBerries": send_all_berries,
            "availableBerries": berries,
            "seeds": remaining_seeds,
            "remaining": remaining,
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "senderPositionName": employee_position(employee),
            "target": target_name,
            "targetEmployeeId": target.get("emp_id"),
            "targetPositionName": employee_position(target),
            "ownerKey": owner_key,
            "slot": slot,
            "message": message,
        }
        log_event(sent_event)
        record_transfer_history(sent_event)
        return {
            "action": "sent",
            "berries": send_berries,
            "requestedBerries": requested_berries,
            "availableBerries": berries,
            "remaining": remaining,
            "senderEmployeeId": sender_employee_id,
            "senderEmployeeName": sender_employee_name,
            "senderPositionName": employee_position(employee),
            "target": target_name,
            "targetEmployeeId": target.get("emp_id"),
            "targetPositionName": employee_position(target),
            "ownerKey": owner_key,
        }
    except Exception as exc:
        state.update({"lastCheckedAt": now_iso(), "lastResult": "failed", "lastAttemptResult": f"failed: {exc}"})
        save_account_state(owner_key, state)
        raise


def list_worklog_projects(owner_key=None):
    owner_key = require_owner(owner_key)
    _client, employee_info, _login_dataset, _employee, _sender_id, _sender_name = account_login(owner_key)
    projects = []
    seen = set()
    for key in ("projEmp", "projInner"):
        for row in employee_info.get(key) or []:
            project_id = row.get("proj_id")
            project_name = row.get("proj_nm")
            if not project_id or not project_name or project_id in seen:
                continue
            seen.add(project_id)
            projects.append({"id": project_id, "name": project_name, "source": key})
    return projects


def set_worklog_target(emp_id, name=None, duty_id=None, dept_nm=None, pos_nm=None, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    state.update(
        {
            "worklogTargetEmployeeId": emp_id,
            "worklogTargetEmployeeName": name or state.get("worklogTargetEmployeeName"),
            "worklogTargetDutyId": duty_id,
            "worklogTargetDeptName": dept_nm,
            "worklogTargetPositionName": pos_nm,
            "updatedAt": now_iso(),
        }
    )
    save_account_state(owner_key, state)
    log_event({"action": "worklog_target_set", "ownerKey": owner_key, "targetEmployeeId": emp_id, "targetEmployeeName": name})
    return state


def normalize_schedule_days(days):
    result = []
    for item in days or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= value <= 4 and value not in result:
            result.append(value)
    return result


def worklog_blocked_date_reason(day):
    if day.weekday() >= 5:
        return "주말"
    return KOREAN_PUBLIC_HOLIDAYS.get(day.isoformat(), "")


def is_worklog_allowed_date(day):
    return not worklog_blocked_date_reason(day)


def normalize_schedule_dates(dates, reject_blocked=True):
    result = []
    for item in dates or []:
        text = str(item or "").strip()
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            continue
        blocked_reason = worklog_blocked_date_reason(day)
        if blocked_reason and reject_blocked:
            raise FruitAutoError(f"{text}은(는) {blocked_reason}이라 업무일지를 예약할 수 없습니다.")
        if blocked_reason:
            continue
        if text not in result:
            result.append(text)
    return result


def prune_expired_schedule_dates(dates, schedule_time, account=None, now=None):
    result = []
    now = now or dt.datetime.now(dt.timezone.utc)
    local_now = now.astimezone(KST)
    hour, minute = [int(part) for part in normalize_schedule_time(schedule_time).split(":")]
    account = account or {}
    for text in normalize_schedule_dates(dates, reject_blocked=False):
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            continue
        scheduled = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=KST)
        if scheduled <= local_now:
            continue
        if text not in result:
            result.append(text)
    return result


def expired_schedule_dates(dates, schedule_time, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    local_now = now.astimezone(KST)
    hour, minute = [int(part) for part in normalize_schedule_time(schedule_time).split(":")]
    expired = []
    for text in normalize_schedule_dates(dates, reject_blocked=False):
        try:
            day = dt.date.fromisoformat(text)
        except ValueError:
            continue
        scheduled = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=KST)
        if scheduled <= local_now:
            expired.append(text)
    return expired


def normalize_schedule_time(value):
    text = str(value or DEFAULT_STATE["worklogScheduleTime"]).strip()
    try:
        hour, minute = [int(part) for part in text.split(":", 1)]
    except (TypeError, ValueError):
        raise FruitAutoError("예약 시간은 HH:MM 형식이어야 합니다.")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise FruitAutoError("예약 시간이 올바르지 않습니다.")
    return f"{hour:02d}:{minute:02d}"


def validate_worklog_available_seeds(seed_count, available_seeds):
    try:
        available = int(available_seeds or 0)
    except (TypeError, ValueError):
        available = 0
    if available <= 0:
        raise FruitAutoError("보유 씨앗이 0개라 업무일지를 예약할 수 없습니다. 씨앗을 받은 뒤 다시 예약해 주세요.")
    if seed_count > available:
        raise FruitAutoError(f"보유 씨앗이 {available}개라 {seed_count}개를 예약할 수 없습니다.")


def set_worklog_settings(payload, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    seed_count = payload.get("seedCount", state.get("worklogSeedCount") or 0)
    try:
        seed_count = int(seed_count or 0)
    except (TypeError, ValueError):
        raise FruitAutoError("씨앗 개수는 숫자로 입력하세요.")
    if seed_count < 0 or seed_count > 3:
        raise FruitAutoError("씨앗 선물은 최대 3개까지 가능합니다.")
    project_id = payload.get("projectId", state.get("worklogProjectId"))
    project_name = payload.get("projectName", state.get("worklogProjectName"))
    seed_message = str(payload.get("seedMessage", state.get("worklogSeedMessage") or "") or "").strip()
    content = str(payload.get("content", state.get("worklogContent") or "") or "").strip()
    enabled = bool(payload.get("enabled", state.get("worklogEnabled")))
    target_employee_id = payload.get("targetEmployeeId", state.get("worklogTargetEmployeeId"))
    target_employee_name = payload.get("targetEmployeeName", state.get("worklogTargetEmployeeName"))
    target_dept_name = payload.get("targetDeptName", state.get("worklogTargetDeptName"))
    target_position_name = payload.get("targetPositionName", state.get("worklogTargetPositionName"))
    target_duty_id = payload.get("targetDutyId", state.get("worklogTargetDutyId"))
    if not project_id or not project_name:
        raise FruitAutoError("업무일지 프로젝트를 선택해주세요.")
    if not seed_message:
        raise FruitAutoError("씨앗 선물 메시지를 입력해주세요.")
    if seed_count <= 0:
        raise FruitAutoError("보낼 씨앗 수를 입력해주세요.")
    if not content:
        raise FruitAutoError("업무일지 내용을 입력해주세요.")
    if not target_employee_id or not target_employee_name:
        raise FruitAutoError("업무씨앗 받을 직원을 선택해 주세요.")
    verified_balance = {}
    if enabled:
        client, _employee_info, _login_dataset, employee, _sender_employee_id, _sender_employee_name = account_login(owner_key)
        available_seeds, available_berries = current_seed_fruit(client, employee)
        validate_worklog_available_seeds(seed_count, available_seeds)
        verified_balance = {
            "lastSeedCount": available_seeds,
            "lastBerryCount": available_berries,
            "balanceCheckedAt": now_iso(),
        }
    saved_at = now_iso()
    schedule_time = normalize_schedule_time(payload.get("scheduleTime", state.get("worklogScheduleTime")))
    if enabled and expired_schedule_dates(payload.get("scheduleDates", state.get("worklogScheduleDates")), schedule_time):
        raise FruitAutoError("오늘 업무일지를 예약하려면 예약 시간을 현재 시간 이후로 설정해주세요.")
    schedule_dates = prune_expired_schedule_dates(
        payload.get("scheduleDates", state.get("worklogScheduleDates")),
        schedule_time,
        state,
    )
    next_values = {
        "worklogEnabled": enabled,
        "worklogScheduleDays": normalize_schedule_days(payload.get("scheduleDays", state.get("worklogScheduleDays"))),
        "worklogScheduleDates": schedule_dates,
        "worklogScheduleTime": schedule_time,
        "worklogSeedCount": seed_count,
        "worklogSeedMessage": seed_message,
        "worklogTargetEmployeeId": target_employee_id,
        "worklogTargetEmployeeName": target_employee_name,
        "worklogTargetDeptName": target_dept_name,
        "worklogTargetPositionName": target_position_name,
        "worklogTargetDutyId": target_duty_id,
        "worklogProjectId": project_id,
        "worklogProjectName": project_name,
        "worklogContent": content,
        "worklogScheduleUpdatedAt": saved_at,
        **verified_balance,
        "updatedAt": saved_at,
    }
    next_values["worklogNextRunAt"] = next_worklog_run_at({**state, **next_values})
    state.update(next_values)
    save_account_state(owner_key, state)
    log_event({"action": "worklog_settings_saved", "ownerKey": owner_key, "enabled": enabled})
    return state


def worklog_schedule_matches(account, local_now):
    schedule_time = normalize_schedule_time(account.get("worklogScheduleTime"))
    hour, minute = [int(part) for part in schedule_time.split(":")]
    scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local_now < scheduled:
        return False, scheduled
    today = local_now.date().isoformat()
    if not is_worklog_allowed_date(local_now.date()):
        return False, scheduled
    weekdays = normalize_schedule_days(account.get("worklogScheduleDays"))
    dates = normalize_schedule_dates(account.get("worklogScheduleDates"), reject_blocked=False)
    if weekdays and local_now.weekday() in weekdays:
        return True, scheduled
    if dates and today in dates:
        return True, scheduled
    return False, scheduled


def worklog_completed_local_date(account):
    run_key = str(account.get("worklogLastRunKey") or "").strip()
    if run_key:
        try:
            return dt.date.fromisoformat(run_key.split("T", 1)[0])
        except ValueError:
            pass
    last_run_at = parse_iso(account.get("worklogLastRunAt"))
    if last_run_at:
        return last_run_at.astimezone(KST).date()
    return None


def worklog_already_completed_for_day(account, day):
    completed_day = worklog_completed_local_date(account)
    return completed_day == day


def next_worklog_run_at(account, now=None):
    if not account.get("worklogEnabled"):
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    local_now = now.astimezone(KST)
    schedule_time = normalize_schedule_time(account.get("worklogScheduleTime"))
    hour, minute = [int(part) for part in schedule_time.split(":")]
    weekdays = normalize_schedule_days(account.get("worklogScheduleDays"))
    dates = normalize_schedule_dates(account.get("worklogScheduleDates"), reject_blocked=False)
    candidates = []
    for offset in range(0, 370):
        day = (local_now + dt.timedelta(days=offset)).date()
        if not is_worklog_allowed_date(day):
            continue
        if worklog_already_completed_for_day(account, day):
            continue
        if weekdays and day.weekday() in weekdays:
            candidates.append(day)
        if dates and day.isoformat() in dates:
            candidates.append(day)
    for day in sorted(set(candidates)):
        candidate = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=KST)
        if candidate > local_now:
            return candidate.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    return None


def worklog_next_run_delay(account, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    next_run = parse_iso(account.get("worklogNextRunAt")) or parse_iso(next_worklog_run_at(account, now))
    if next_run is None:
        return None
    return max(0, int((next_run - now).total_seconds()))


def worklog_due(account, now=None):
    if not account.get("worklogEnabled"):
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    next_run = parse_iso(account.get("worklogNextRunAt"))
    if next_run is None or now < next_run:
        return False
    run_key = next_run.astimezone(KST).strftime("%Y-%m-%dT%H:%M")
    run_day = next_run.astimezone(KST).date()
    return not worklog_already_completed_for_day(account, run_day)


def worklog_run_key_for_next_run(account):
    next_run = parse_iso(account.get("worklogNextRunAt"))
    if next_run is None:
        return None
    return next_run.astimezone(KST).strftime("%Y-%m-%dT%H:%M")


def save_worklog_once(owner_key=None, run_date=None, force=False):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    if not force and not worklog_due(state):
        state["worklogNextRunAt"] = next_worklog_run_at(state)
        save_account_state(owner_key, state)
        return {"action": "skipped", "reason": "worklog_not_due", "ownerKey": owner_key, "nextRunAt": state.get("worklogNextRunAt")}
    if not force:
        due_run_key = worklog_run_key_for_next_run(state)
        if due_run_key:
            running_at = parse_iso(state.get("worklogRunningAt"))
            running_fresh = running_at and (dt.datetime.now(dt.timezone.utc) - running_at).total_seconds() < 15 * 60
            if state.get("worklogRunningRunKey") == due_run_key and running_fresh:
                return {"action": "skipped", "reason": "worklog_already_running", "ownerKey": owner_key, "runKey": due_run_key}
            state["worklogRunningRunKey"] = due_run_key
            state["worklogRunningAt"] = now_iso()
            save_account_state(owner_key, state)

    try:
        if not state.get("worklogProjectId") or not state.get("worklogContent"):
            raise FruitAutoError("업무일지 프로젝트와 내용을 먼저 저장하세요.")
        seed_count = int(state.get("worklogSeedCount") or 0)
        if seed_count < 0 or seed_count > 3:
            raise FruitAutoError("씨앗 선물은 최대 3개까지 가능합니다.")
        if seed_count and not state.get("worklogTargetEmployeeId"):
            raise FruitAutoError("씨앗 선물 대상 직원을 선택하세요.")

        client, employee_info, _login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
        available_seeds = None
        available_berries = None
        if seed_count:
            available_seeds, available_berries = current_seed_fruit(client, employee)
            validate_worklog_available_seeds(seed_count, available_seeds)
        local_now = dt.datetime.now(KST)
        scheduled_for = parse_iso(state.get("worklogNextRunAt")) if not force else None
        if run_date:
            target_date = dt.date.fromisoformat(str(run_date))
        elif scheduled_for is not None:
            target_date = scheduled_for.astimezone(KST).date()
        else:
            matches, scheduled = worklog_schedule_matches(state, local_now)
            target_date = scheduled.date() if matches else local_now.date()
        std_dt = target_date.strftime("%Y%m%d")
        std_mt = target_date.strftime("%Y%m")
        std_yr = target_date.strftime("%Y")
        data = {
            "empId": employee["emp_id"],
            "stdDt": std_dt,
            "projId": state.get("worklogProjectId"),
            "stdMt": std_mt,
            "stdYr": std_yr,
            "empNm": employee.get("emp_nm"),
            "projNm": state.get("worklogProjectName"),
            "workProsRate": 100,
            "workDesc": state.get("worklogContent"),
            "cfmYn": "N",
            "workStTm": f"{std_dt}0900",
            "workEdTm": f"{std_dt}1800",
            "slfWorkPfmBerryCnt": 3,
            "regId": employee["emp_id"],
            "modId": employee["emp_id"],
        }
        if seed_count:
            data.update(
                {
                    "tgtEmpId": state.get("worklogTargetEmployeeId"),
                    "tgtEmpNm": state.get("worklogTargetEmployeeName"),
                    "dutyCd": state.get("worklogTargetDutyId"),
                    "dutyCds": employee.get("duty_id"),
                    "seedCnt": seed_count,
                    "tgtMsg": state.get("worklogSeedMessage") or "",
                }
            )
        api_called_at = now_iso()
        client.post_json(f"{FOREST_API}/saveDw", {"dwInsList": [data]})
        remaining_seeds = available_seeds
        remaining_berries = available_berries
        if seed_count:
            remaining_seeds, remaining_berries = current_seed_fruit(client, employee)
        schedule_time = normalize_schedule_time(state.get("worklogScheduleTime"))
        run_key = f"{target_date.isoformat()}T{schedule_time}"
        scheduled_for_iso = (
            scheduled_for.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
            if scheduled_for is not None
            else dt.datetime.combine(target_date, dt.time.fromisoformat(schedule_time), tzinfo=KST)
            .astimezone(dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )
        state.update(
            {
                "worklogLastRunAt": now_iso(),
                "worklogLastRunKey": run_key,
                "worklogLastResult": "sent",
                "worklogLastError": None,
                "worklogRunningRunKey": None,
                "worklogRunningAt": None,
                **(
                    {
                        "lastSeedCount": remaining_seeds,
                        "lastBerryCount": remaining_berries,
                        "balanceCheckedAt": now_iso(),
                    }
                    if seed_count
                    else {}
                ),
                "worklogNextRunAt": next_worklog_run_at({**state, "worklogLastRunKey": run_key}),
                "senderEmployeeId": sender_employee_id,
                "senderEmployeeName": sender_employee_name,
                "updatedAt": now_iso(),
            }
        )
        save_account_state(owner_key, state)
        event = {
            "type": "worklog",
            "action": "worklog_sent",
            "ownerKey": owner_key,
            "stdDt": std_dt,
            "runKey": run_key,
            "scheduledFor": scheduled_for_iso,
            "scheduleTime": schedule_time,
            "completedAt": now_iso(),
            "projectId": state.get("worklogProjectId"),
            "projectName": state.get("worklogProjectName"),
            "workDesc": state.get("worklogContent"),
            "seedCount": seed_count,
            "seedMessage": state.get("worklogSeedMessage") or "",
            "targetEmployeeId": state.get("worklogTargetEmployeeId"),
            "targetEmployeeName": state.get("worklogTargetEmployeeName"),
        }
        log_event(event)
        append_jsonl(HISTORY_PATH, event)
        if seed_count:
            seed_event = {
                "action": "sent",
                "at": api_called_at,
                "timeSource": "worklog_api_call",
                "seedDelta": seed_count,
                "berries": 0,
                "seeds": remaining_seeds,
                "remaining": remaining_berries,
                "senderEmployeeId": sender_employee_id,
                "senderEmployeeName": sender_employee_name,
                "senderPositionName": employee_position(employee),
                "target": state.get("worklogTargetEmployeeName"),
                "targetEmployeeId": state.get("worklogTargetEmployeeId"),
                "targetPositionName": state.get("worklogTargetPositionName"),
                "ownerKey": owner_key,
                "message": "",
                "worklogStdDt": std_dt,
                "worklogCompletedAt": event["completedAt"],
            }
            log_event({**seed_event, "action": "worklog_seed_sent"})
            record_seed_transfer_history(seed_event)
        return {
            "action": "worklog_sent",
            "ownerKey": owner_key,
            "stdDt": std_dt,
            "runKey": run_key,
            "scheduleTime": schedule_time,
            "scheduledFor": scheduled_for_iso,
            "completedAt": event["completedAt"],
            "projectName": state.get("worklogProjectName"),
            "seedCount": seed_count,
        }
    except Exception:
        if not force:
            latest_state = get_account_state(owner_key)
            if latest_state.get("worklogRunningRunKey") == state.get("worklogRunningRunKey"):
                latest_state["worklogRunningRunKey"] = None
                latest_state["worklogRunningAt"] = None
                save_account_state(owner_key, latest_state)
        raise


def run_worklog_if_due(owner_key):
    state = get_account_state(owner_key)
    if not worklog_due(state):
        next_run = next_worklog_run_at(state)
        if next_run != state.get("worklogNextRunAt"):
            state["worklogNextRunAt"] = next_run
            save_account_state(owner_key, state)
        return {"action": "skipped", "reason": "worklog_not_due", "ownerKey": owner_key}
    try:
        return save_worklog_once(owner_key=owner_key)
    except Exception as exc:
        state = get_account_state(owner_key)
        state.update(
            {
                "worklogLastRunAt": now_iso(),
                "worklogLastResult": "failed",
                "worklogLastError": str(exc),
                "worklogNextRunAt": next_worklog_run_at(state),
                "updatedAt": now_iso(),
            }
        )
        save_account_state(owner_key, state)
        raise


def enabled_owner_keys():
    state = load_all_state()
    secrets = load_secrets()
    return [
        owner_key
        for owner_key, account in state.get("accounts", {}).items()
        if account.get("enabled") and owner_key in secrets.get("accounts", {})
    ]


def active_owner_keys():
    state = load_all_state()
    secrets = load_secrets()
    return [
        owner_key
        for owner_key, account in state.get("accounts", {}).items()
        if owner_key in secrets.get("accounts", {}) and (account.get("enabled") or account.get("worklogEnabled"))
    ]


def failed_slot_result(exc, owner_key=None):
    state = get_account_state(owner_key) if owner_key else load_json(STATE_PATH, DEFAULT_STATE)
    return {
        "action": "failed",
        "error": str(exc),
        "nextRetry": "next_interval",
        "intervalSeconds": get_run_interval_seconds(state),
        "lastAttemptSlot": state.get("lastAttemptSlot"),
        "lastAttemptResult": state.get("lastAttemptResult"),
        "ownerKey": owner_key,
    }


def account_next_run_delay(account, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    interval_seconds = get_run_interval_seconds(account)
    next_run = parse_iso(account.get("nextRunAt"))
    if next_run is None:
        last_attempt = parse_iso(account.get("lastAttemptAt"))
        next_run = last_attempt + dt.timedelta(seconds=interval_seconds) if last_attempt else now
    return max(0, int((next_run - now).total_seconds()))


def scheduled_owner_keys():
    state = load_all_state()
    secrets = load_secrets()
    now = dt.datetime.now(dt.timezone.utc)
    due = []
    next_delay = None
    for owner_key, account in state.get("accounts", {}).items():
        if owner_key not in secrets.get("accounts", {}):
            continue
        account_due = False
        delay = common_observe_delay(account, now)
        if delay <= 0:
            account_due = True
        elif next_delay is None or delay < next_delay:
            next_delay = delay
        if account.get("enabled"):
            delay = account_next_run_delay(account, now)
            if delay <= 0:
                account_due = True
            elif next_delay is None or delay < next_delay:
                next_delay = delay
        if account.get("worklogEnabled"):
            delay = worklog_next_run_delay(account, now)
            if delay is not None:
                if delay <= 0 or worklog_due(account, now):
                    account_due = True
                elif next_delay is None or delay < next_delay:
                    next_delay = delay
        if account_due:
            due.append(owner_key)
    return due, next_delay


def sleep_for(seconds):
    global WAKE_REQUESTED
    deadline = time.time() + max(1, int(seconds))
    while not WAKE_REQUESTED:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(remaining, 60))
    WAKE_REQUESTED = False


def run_daemon():
    claim_daemon_pid()

    def handle_stop(_signum, _frame):
        log_event({"action": "daemon_stopped"})
        release_daemon_pid()
        raise SystemExit(0)

    def handle_wake(_signum, _frame):
        global WAKE_REQUESTED
        WAKE_REQUESTED = True

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, handle_wake)

    try:
        log_event({"action": "daemon_started", "mode": "multi_user_scheduled"})
        while True:
            owners, next_delay = scheduled_owner_keys()
            if not owners:
                sleep_for(next_delay if next_delay is not None else 300)
                continue
            for owner_key in owners:
                try:
                    account = get_account_state(owner_key)
                    transfer_due = account.get("enabled") and account_next_run_delay(account) <= 0
                    if common_observe_due(account) and not transfer_due:
                        result = observe_received_history(owner_key=owner_key)
                        log_event({"action": "daemon_common_observe", "ownerKey": owner_key, "result": result})
                    if transfer_due:
                        result = check_once(owner_key=owner_key)
                        if result.get("reason") != "already_attempted_this_interval":
                            log_event({"action": "daemon_tick", "ownerKey": owner_key, "result": result})
                        notify_result(result)
                    if account.get("worklogEnabled"):
                        result = run_worklog_if_due(owner_key)
                        if result.get("action") == "worklog_sent":
                            log_event({"action": "daemon_worklog_tick", "ownerKey": owner_key, "result": result})
                            notify_result(result)
                except Exception as exc:
                    log_event({"action": "daemon_error", "ownerKey": owner_key, "error": str(exc)})
                    notify_result({"action": "failed", "error": str(exc), "ownerKey": owner_key})
    finally:
        release_daemon_pid()


def run_tick():
    try:
        claim_tick_lock()
    except FruitAutoError as exc:
        result = {"action": "skipped", "reason": "tick_already_running", "error": str(exc)}
        log_event({"action": "tick_skipped", "reason": "already_running", "error": str(exc)})
        return result

    results = []
    processed_owners = []
    started_at = time.time()
    max_seconds, max_owners = tick_limits()
    try:
        owners, next_delay = scheduled_owner_keys()
        owners = rotate_tick_owners(owners)
        if not owners:
            result = {"action": "skipped", "reason": "nothing_due", "nextDelaySeconds": next_delay}
            log_event({"action": "tick", "result": result})
            return result
        for owner_key in owners:
            if len(processed_owners) >= max_owners:
                break
            if time.time() - started_at >= max_seconds:
                break
            processed_owners.append(owner_key)
            try:
                account = get_account_state(owner_key)
                transfer_due = account.get("enabled") and account_next_run_delay(account) <= 0
                if common_observe_due(account) and not transfer_due:
                    result = observe_received_history(owner_key=owner_key)
                    results.append(result)
                    log_event({"action": "tick_common_observe", "ownerKey": owner_key, "result": result})
                if transfer_due:
                    result = check_once(owner_key=owner_key)
                    results.append(result)
                    if result.get("reason") != "already_attempted_this_interval":
                        log_event({"action": "tick_transfer", "ownerKey": owner_key, "result": result})
                    notify_result(result)
                if account.get("worklogEnabled"):
                    result = run_worklog_if_due(owner_key)
                    results.append(result)
                    if result.get("action") == "worklog_sent":
                        log_event({"action": "tick_worklog", "ownerKey": owner_key, "result": result})
                        notify_result(result)
            except Exception as exc:
                result = {"action": "failed", "error": str(exc), "ownerKey": owner_key}
                results.append(result)
                log_event({"action": "tick_error", "ownerKey": owner_key, "error": str(exc)})
                notify_result(result)
        if processed_owners:
            save_tick_cursor(processed_owners[-1])
        remaining_due = max(0, len(owners) - len(processed_owners))
        return {
            "action": "tick_complete",
            "processedOwners": len(processed_owners),
            "remainingDueOwners": remaining_due,
            "maxOwners": max_owners,
            "maxSeconds": max_seconds,
            "elapsedSeconds": int(time.time() - started_at),
            "results": results,
        }
    finally:
        release_tick_lock()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    on = sub.add_parser("on")
    on.add_argument("target_name", nargs="*")
    sub.add_parser("off")
    sub.add_parser("logout")
    sub.add_parser("status")
    sub.add_parser("daemon")
    sub.add_parser("tick")
    login = sub.add_parser("login")
    login.add_argument("--id", required=True)
    login.add_argument("--password", required=True)
    search = sub.add_parser("search")
    search.add_argument("query")
    target = sub.add_parser("set-target")
    target.add_argument("--emp-id", required=True)
    target.add_argument("--name")
    target.add_argument("--duty-id")
    target.add_argument("--dept")
    target.add_argument("--pos")
    msg = sub.add_parser("set-message")
    msg.add_argument("message")
    interval = sub.add_parser("set-interval")
    interval.add_argument("minutes", type=int)
    run = sub.add_parser("run-once")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        if args.cmd == "on":
            if args.target_name:
                set_target_by_name(" ".join(args.target_name))
            result = set_enabled(True)
        elif args.cmd == "off":
            result = set_enabled(False)
        elif args.cmd == "logout":
            result = logout()
        elif args.cmd == "status":
            result = load_json(STATE_PATH, DEFAULT_STATE)
        elif args.cmd == "daemon":
            run_daemon()
            return 0
        elif args.cmd == "tick":
            result = run_tick()
        elif args.cmd == "login":
            result = save_credentials(args.id, args.password)
        elif args.cmd == "search":
            result = {"results": search_employees(args.query)}
        elif args.cmd == "set-target":
            result = set_target(args.emp_id, args.name, args.duty_id, args.dept, args.pos)
        elif args.cmd == "set-message":
            result = set_message(args.message)
        elif args.cmd == "set-interval":
            result = set_run_interval(args.minutes)
        elif args.cmd == "run-once":
            result = check_once(dry_run=args.dry_run, force=args.force)
        else:
            raise FruitAutoError(f"unknown command: {args.cmd}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        log_event({"action": "error", "error": str(exc)})
        if args.cmd == "run-once" and not args.force:
            print(json.dumps(failed_slot_result(exc), ensure_ascii=False, sort_keys=True))
            return 0
        print(json.dumps({"action": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
