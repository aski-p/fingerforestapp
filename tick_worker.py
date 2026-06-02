#!/usr/bin/env python3
import datetime as dt
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "tick_worker.log"
INTERVAL_SECONDS = int(os.environ.get("FRUIT_TICK_INTERVAL_SECONDS", "300"))
TICK_TIMEOUT_SECONDS = int(os.environ.get("FRUIT_TICK_TIMEOUT_SECONDS", "240"))
STOP = False


def log(message):
    timestamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} {message}\n")


def handle_stop(_signum, _frame):
    global STOP
    STOP = True


def sleep_interruptible(seconds):
    deadline = time.time() + max(1, seconds)
    while not STOP:
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5))


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
        return
    elapsed = int(time.time() - started)
    output = (completed.stdout or "").strip().replace("\n", " ")
    log(f"tick exit={completed.returncode} elapsed={elapsed}s output={output[:1500]!r}")


def main():
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    log(f"worker started interval={INTERVAL_SECONDS}s timeout={TICK_TIMEOUT_SECONDS}s")
    while not STOP:
        run_tick()
        sleep_interruptible(INTERVAL_SECONDS)
    log("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
