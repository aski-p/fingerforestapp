#!/usr/bin/env python3
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FRUIT_AUTO_DATA_DIR") or BASE_DIR).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = DATA_DIR / "tick_worker.log"
WAKE_PATH = DATA_DIR / "tick_worker.wake"
HEARTBEAT_PATH = DATA_DIR / "tick_worker.heartbeat.json"
INTERVAL_SECONDS = int(os.environ.get("FRUIT_TICK_INTERVAL_SECONDS", "60"))
TICK_TIMEOUT_SECONDS = int(os.environ.get("FRUIT_TICK_TIMEOUT_SECONDS", "240"))
STOP = False
LAST_WAKE_MTIME = 0.0


def log(message):
    timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} {message}\n")


def handle_stop(_signum, _frame):
    global STOP
    STOP = True


def wake_requested():
    global LAST_WAKE_MTIME
    try:
        mtime = WAKE_PATH.stat().st_mtime
    except FileNotFoundError:
        return False
    if mtime <= LAST_WAKE_MTIME:
        return False
    LAST_WAKE_MTIME = mtime
    return True


def sleep_interruptible(seconds):
    deadline = time.time() + max(1, seconds)
    while not STOP:
        if wake_requested():
            return
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5))


def write_heartbeat(next_sleep_seconds=None):
    payload = {
        "pid": os.getpid(),
        "updatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "intervalSeconds": INTERVAL_SECONDS,
        "nextSleepSeconds": next_sleep_seconds,
    }
    HEARTBEAT_PATH.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def next_sleep_from_output(output):
    try:
        result = json.loads(output)
    except (TypeError, ValueError):
        return INTERVAL_SECONDS
    delay = result.get("nextDelaySeconds")
    if delay is None:
        return INTERVAL_SECONDS
    try:
        delay = int(delay)
    except (TypeError, ValueError):
        return INTERVAL_SECONDS
    return max(1, min(INTERVAL_SECONDS, delay))


def run_tick():
    started = time.time()
    try:
        completed = subprocess.run(
            [sys.executable, str(BASE_DIR / "fruit_auto.py"), "tick"],
            cwd=str(BASE_DIR),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=TICK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        log(f"tick timeout after {TICK_TIMEOUT_SECONDS}s output={output[:1000]!r}")
        return INTERVAL_SECONDS
    elapsed = int(time.time() - started)
    raw_output = (completed.stdout or "").strip()
    output = raw_output.replace("\n", " ")
    log(f"tick exit={completed.returncode} elapsed={elapsed}s output={output[:1500]!r}")
    if completed.returncode != 0:
        return INTERVAL_SECONDS
    return next_sleep_from_output(raw_output)


def main():
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    log(f"worker started interval={INTERVAL_SECONDS}s timeout={TICK_TIMEOUT_SECONDS}s")
    while not STOP:
        next_sleep = run_tick()
        write_heartbeat(next_sleep)
        sleep_interruptible(next_sleep)
    log("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
