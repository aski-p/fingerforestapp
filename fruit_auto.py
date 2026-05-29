#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import os
import signal
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
PID_PATH = DATA_DIR / "daemon.pid"
WEB_PUSH_SCRIPT_PATH = BASE_DIR / "send_web_push.js"
DEFAULT_RUN_INTERVAL_MINUTES = 5
MIN_RUN_INTERVAL_MINUTES = 5
MAX_RUN_INTERVAL_MINUTES = 60
WAKE_REQUESTED = False
QUIET_LOG_ACTIONS = {"balance", "check"}
SESSION_SCHEMA_VERSION = 4
SESSION_TTL_SECONDS = 60 * 60

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
    "nextRunAt": None,
    "ownerKey": None,
    "senderEmployeeId": None,
    "senderEmployeeName": None,
    "giftMessage": "자동 전달",
    "sendBerryCount": 1,
    "sendAllBerries": False,
    "runIntervalMinutes": DEFAULT_RUN_INTERVAL_MINUTES,
    "pushEnabled": True,
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
    tmp = path.with_suffix(path.suffix + ".tmp")
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
    return (
        event.get("type") == "transfer"
        and event.get("action") == "sent"
        and bool(event.get("ownerKey"))
        and bool(event.get("targetEmployeeId"))
        and int(event.get("berries") or 0) > 0
    )


def record_transfer_history(event):
    event = dict(event)
    event["type"] = "transfer"
    event["action"] = "sent"
    if not is_transfer_history_event(event):
        raise FruitAutoError("invalid transfer history event")
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
    secrets = load_secrets()
    subscriptions = secrets.setdefault("webPushSubscriptions", {})
    endpoint = subscription.get("endpoint")
    for existing_owner_key, existing_subscriptions in subscriptions.items():
        if existing_owner_key == owner_key:
            continue
        existing_subscriptions[:] = [
            item for item in existing_subscriptions if item.get("endpoint") != endpoint
        ]
    owner_subscriptions = subscriptions.setdefault(owner_key, [])
    owner_subscriptions[:] = [
        item for item in owner_subscriptions if item.get("endpoint") != endpoint
    ]
    owner_subscriptions.append(subscription)
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
        target_owner_key = owner_key_for_employee_id(result.get("targetEmployeeId"))
        push_owner_keys = [target_owner_key] if target_owner_key else []
        if push_owner_keys and not is_push_enabled(target_owner_key):
            log_event(
                {
                    "action": "push_notify_skipped",
                    "reason": "push_disabled",
                    "ownerKey": owner_key,
                    "targetOwnerKey": target_owner_key,
                }
            )
            return False
        web_pushed = notify_web_push(received_notification_payload(result), push_owner_keys)
        if web_pushed:
            return True
        log_event(
            {
                "action": "push_notify_skipped",
                "reason": "no_receiver_subscription",
                "ownerKey": owner_key,
                "targetOwnerKey": target_owner_key,
            }
        )
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


def history(limit=40, owner_key=None, date=None, timezone_offset_minutes=0):
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
        if not is_transfer_history_event(event):
            continue
        if date and event_local_date(event, timezone_offset_minutes) != date:
            continue
        sent_by_me = event.get("ownerKey") == owner_key
        received_by_me = my_employee_id and str(event.get("targetEmployeeId") or "") == my_employee_id
        if not sent_by_me and not received_by_me:
            continue
        berries = int(event.get("berries") or 0)
        if sent_by_me:
            action = "sent"
            counterpart = display_employee(
                event.get("target") or event.get("targetEmployeeName"),
                event.get("targetPositionName") or state.get("targetPositionName"),
            )
            sender_employee_id = my_employee_id or event.get("senderEmployeeId")
            avatar_employee_id = sender_employee_id
            sender_name = display_employee(
                state.get("senderEmployeeName")
                or state.get("loginUser")
                or event.get("senderEmployeeName"),
                event.get("senderPositionName") or state.get("senderPositionName"),
                "나",
            )
            delta = -berries
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
            sender_name = counterpart or "보낸사람"
            delta = berries
        if action == "received":
            display_seeds = state.get("lastSeedCount")
            display_remaining = event.get("receiverRemaining")
            if display_remaining is None:
                display_remaining = berries
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
            "senderName": sender_name,
            "senderPositionName": event.get("senderPositionName"),
            "displayName": counterpart,
            "senderIsMe": sent_by_me,
            "seeds": display_seeds,
            "berries": event.get("berries"),
            "remaining": display_remaining,
            "delta": delta,
            "content": "[열매선물]" + (event.get("message") or "자동 전달"),
        }
        rows.append(item)
        if len(rows) >= limit:
            break
    return rows


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
        target_name = state.get("targetEmployeeName")
        target_id = state.get("targetEmployeeId")
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


def session_device_hash(device_id):
    value = str(device_id or "").strip()
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_device_id(device_id):
    value = str(device_id or "").strip()
    if not value:
        raise FruitAutoError("기기 ID가 없는 세션은 사용할 수 없습니다. 앱을 업데이트한 뒤 다시 로그인하세요.")
    return value


def account_device_hash(account):
    if not isinstance(account, dict):
        return None
    return account.get("deviceHash") or account.get("deviceCidHash")


def assert_account_device(secrets, owner_key, device_id):
    device_id = require_device_id(device_id)
    account = secrets.get("accounts", {}).get(owner_key) or {}
    expected_hash = account_device_hash(account)
    if not expected_hash:
        raise FruitAutoError("이 계정은 아직 기기 CID가 등록되지 않았습니다. 다시 로그인하세요.")
    if expected_hash != session_device_hash(device_id):
        raise FruitAutoError("등록된 기기 CID와 현재 기기 CID가 일치하지 않습니다. 이 기기에서는 로그인할 수 없습니다.")
    return True


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


def new_session_record(owner_key, device_id=None):
    device_id = require_device_id(device_id)
    return {
        "version": SESSION_SCHEMA_VERSION,
        "ownerKey": owner_key,
        "deviceHash": session_device_hash(device_id),
        "createdAt": now_iso(),
        "expiresAt": session_expires_at(),
    }


def owner_from_session(session_token, device_id=None):
    if not session_token:
        return None
    device_id = str(device_id or "").strip()
    if not device_id:
        return None
    secrets = load_secrets()
    sessions = secrets.setdefault("sessions", {})
    session = sessions.get(session_token)
    if session_expired(session):
        sessions.pop(session_token, None)
        save_secrets(secrets)
        return None
    owner_key = session_owner_key(session)
    expected_device_hash = session.get("deviceHash")
    if not expected_device_hash or expected_device_hash != session_device_hash(device_id):
        return None
    if owner_key and owner_key in secrets.get("accounts", {}):
        try:
            assert_account_device(secrets, owner_key, device_id)
        except FruitAutoError:
            return None
        session["expiresAt"] = session_expires_at()
        save_secrets(secrets)
        return owner_key
    return None


def issue_session(owner_key=None, device_id=None):
    device_id = require_device_id(device_id)
    owner_key = require_owner(owner_key)
    secrets = load_secrets()
    assert_account_device(secrets, owner_key, device_id)
    sessions = secrets.setdefault("sessions", {})
    changed = False
    for session_token, session_owner in list(sessions.items()):
        if session_expired(session_owner):
            sessions.pop(session_token, None)
            changed = True
            continue
        if session_owner_key(session_owner) == owner_key and session_owner.get("deviceHash") == session_device_hash(device_id):
            session_owner["expiresAt"] = session_expires_at()
            save_secrets(secrets)
            return {"sessionToken": session_token, "ownerKey": owner_key}
    session_token = uuid.uuid4().hex
    sessions[session_token] = new_session_record(owner_key, device_id)
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
    device_id = require_device_id(device_id)
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
    device_hash = session_device_hash(device_id)
    secrets.setdefault("accounts", {})
    existing_secret = secrets["accounts"].get(owner_key) or {}
    existing_device_hash = account_device_hash(existing_secret)
    if existing_device_hash and existing_device_hash != device_hash:
        revoke_sessions_for_owner(secrets, owner_key)
        save_secrets(secrets)
        raise FruitAutoError("등록된 기기 CID와 현재 기기 CID가 일치하지 않습니다. 이 기기에서는 로그인할 수 없습니다.")
    secrets["accounts"] = {
        owner_key: {
            **existing_secret,
            "pms_id": pms_id,
            "pms_password": pms_password,
            "deviceHash": device_hash,
            "deviceBoundAt": existing_secret.get("deviceBoundAt") or now_iso(),
            "deviceUpdatedAt": now_iso(),
        }
    }
    secrets["sessions"] = {
        token: session
        for token, session in secrets.get("sessions", {}).items()
        if session_owner_key(session) == owner_key
    }
    session_token = uuid.uuid4().hex
    secrets["sessions"][session_token] = new_session_record(owner_key, device_id)
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
    save_single_account_state(owner_key, account)
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
    state.update(
        {
            "targetEmployeeId": emp_id,
            "targetEmployeeName": name or state.get("targetEmployeeName"),
            "targetDutyId": duty_id,
            "targetDeptName": dept_nm,
            "targetPositionName": pos_nm,
            "targetLocked": True,
            "targetSelectedAt": now_iso(),
            "updatedAt": now_iso(),
        }
    )
    save_account_state(owner_key, state)
    log_event({"action": "target_set", "ownerKey": owner_key, "targetEmployeeId": emp_id, "targetEmployeeName": name})
    return state


def set_message(message, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    state["giftMessage"] = message or DEFAULT_STATE["giftMessage"]
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    return state


def set_send_berry_count(count, send_all=False, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
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
        last_attempt = parse_iso(state.get("lastAttemptAt"))
        base = last_attempt or dt.datetime.now(dt.timezone.utc)
        state["nextRunAt"] = iso_after(next_minutes * 60, base)
    state["updatedAt"] = now_iso()
    save_account_state(owner_key, state)
    log_event({"action": "interval_set", "ownerKey": owner_key, "runIntervalMinutes": next_minutes})
    return state


def set_enabled(enabled, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    if enabled and not state.get("targetEmployeeId"):
        raise FruitAutoError("대상 직원을 먼저 검색해서 선택하세요.")
    interval_seconds = get_run_interval_seconds(state)
    state.update(
        {
            "enabled": enabled,
            "status": "on" if enabled else "off",
            "nextRunAt": iso_after(interval_seconds) if enabled else None,
            "updatedAt": now_iso(),
        }
    )
    save_account_state(owner_key, state)
    log_event({"action": "enabled" if enabled else "disabled", "ownerKey": owner_key})
    return state


def logout(owner_key=None, session_token=None):
    owner_key = require_owner(owner_key)
    secrets = load_secrets()
    secrets["sessions"] = {}
    secrets["accounts"] = {}
    save_secrets(secrets)
    state = remove_account_state(owner_key)
    log_event({"action": "logged_out", "ownerKey": owner_key})
    return state


def check_once(dry_run=False, force=False, owner_key=None):
    owner_key = require_owner(owner_key)
    state = get_account_state(owner_key)
    interval_seconds = get_run_interval_seconds(state)
    enabled = bool(state.get("enabled"))
    if not enabled and not force:
        state.update({"status": "off", "lastCheckedAt": now_iso(), "nextRunAt": None})
        save_account_state(owner_key, state)
        return {"action": "skipped", "reason": "disabled", "enabled": enabled, "ownerKey": owner_key}

    last_attempt_age = seconds_since(state.get("lastAttemptAt"))
    if not force and last_attempt_age is not None and last_attempt_age < interval_seconds:
        state["nextRunAt"] = iso_after(interval_seconds - last_attempt_age)
        save_account_state(owner_key, state)
        return {
            "action": "skipped",
            "reason": "already_attempted_this_interval",
            "ownerKey": owner_key,
            "intervalSeconds": interval_seconds,
            "remainingSeconds": max(0, int(interval_seconds - last_attempt_age)),
            "lastAttemptResult": state.get("lastAttemptResult"),
            "nextRunAt": state.get("nextRunAt"),
        }

    slot = int(time.time() // interval_seconds)
    attempt_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    state.update(
        {
            "lastAttemptAt": attempt_at.isoformat(),
            "lastAttemptSlot": slot,
            "lastAttemptIntervalSeconds": interval_seconds,
            "lastAttemptResult": "running",
            "nextRunAt": iso_after(interval_seconds, attempt_at),
        }
    )
    save_account_state(owner_key, state)

    try:
        client, employee_info, login_dataset, employee, sender_employee_id, sender_employee_name = account_login(owner_key)
        target_name = state.get("targetEmployeeName")
        target_id = state.get("targetEmployeeId")
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
        seeds, berries = current_seed_fruit(client, employee)
        state.update(
            {
                "enabled": enabled,
                "status": "on" if enabled else "forced",
                "targetEmployeeName": target.get("emp_nm") or target_name,
                "targetEmployeeId": target.get("emp_id"),
                "targetPositionName": employee_position(target),
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
        if dry_run:
            state["lastResult"] = f"dry_run_would_send_{send_berries}"
            state["lastAttemptResult"] = state["lastResult"]
            save_account_state(owner_key, state)
            return {"action": "dry_run", "berries": send_berries, "requestedBerries": requested_berries, "sendAllBerries": send_all_berries, "availableBerries": berries, "target": target_name, "targetEmployeeId": target.get("emp_id"), "ownerKey": owner_key}

        give_all_berries(client, employee_info, target, send_berries, message)
        remaining_seeds, remaining = current_seed_fruit(client, employee)
        state.update(
            {
                "lastSentAt": now_iso(),
                "lastSeedCount": remaining_seeds,
                "lastBerryCount": remaining,
                "balanceCheckedAt": now_iso(),
                "lastResult": f"sent_{send_berries}_remaining_{remaining}",
                "lastAttemptResult": f"sent_{send_berries}_remaining_{remaining}",
            }
        )
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


def enabled_owner_keys():
    state = load_all_state()
    secrets = load_secrets()
    return [
        owner_key
        for owner_key, account in state.get("accounts", {}).items()
        if account.get("enabled") and owner_key in secrets.get("accounts", {})
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
        if not account.get("enabled") or owner_key not in secrets.get("accounts", {}):
            continue
        delay = account_next_run_delay(account, now)
        if delay <= 0:
            due.append(owner_key)
        elif next_delay is None or delay < next_delay:
            next_delay = delay
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
                    result = check_once(owner_key=owner_key)
                    if result.get("reason") != "already_attempted_this_interval":
                        log_event({"action": "daemon_tick", "ownerKey": owner_key, "result": result})
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
