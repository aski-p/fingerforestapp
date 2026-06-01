#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
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
WEB_PUSH_SCRIPT_PATH = BASE_DIR / "send_web_push.js"
DEFAULT_RUN_INTERVAL_MINUTES = 5
MIN_RUN_INTERVAL_MINUTES = 5
MAX_RUN_INTERVAL_MINUTES = 60
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
    "pendingReceivedAt": None,
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
    "worklogSeedCount": 0,
    "worklogSeedMessage": "",
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
        stat = S~���h��춻�q�^tor not state.get("worklogContent"):
            raise FruitAutoError("업무일지 프로젝트와 내용을 먼저 저장하세요.")
        seed_count = int(state.get("worklogSeedCount") or 0)
        if seed_count < 0 or seed_count > 3:
            raise FruitAutoError("씨앗 선물은 최대 3개까지 가능합니다.")
        if seed_count and not state.get("worklogTargetEmployeeId"):
            raise FruitAutoError("씨앗 선물 대상 직원을 선택하세요.")

        client, employee_info, _login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
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
        remaining_seeds = None
        remaining_berries = None
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
            "seedCount": seed_count,
            "targetEmployeeId": state.get("worklogTargetEmployeeId"),
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
                    if account.get("enabled") and account_next_run_delay(account) <= 0:
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


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    on = sub.add_parser("on")
    on.add_argument("target_name", nargs="*")
    sub.add_parser("off")
    sub.add_parser("logout")
    sub.add_parser("status")
    sub.add_parser("daemon")
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
