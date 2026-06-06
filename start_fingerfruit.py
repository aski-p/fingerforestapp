#!/usr/bin/env python3
import os
import signal
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def terminate(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("PORT", "8765")
    worker = subprocess.Popen([sys.executable, str(BASE_DIR / "tick_worker.py")], cwd=str(BASE_DIR))
    web = subprocess.Popen([sys.executable, str(BASE_DIR / "web_server.py"), host, str(port)], cwd=str(BASE_DIR))

    stopping = False

    def handle_stop(signum, _frame):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        terminate(web)
        terminate(worker)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    try:
        while True:
            web_status = web.poll()
            if web_status is not None:
                return web_status
            if worker.poll() is not None:
                worker = subprocess.Popen([sys.executable, str(BASE_DIR / "tick_worker.py")], cwd=str(BASE_DIR))
            try:
                web.wait(timeout=10)
            except subprocess.TimeoutExpired:
                continue
    finally:
        terminate(worker)


if __name__ == "__main__":
    sys.exit(main())
