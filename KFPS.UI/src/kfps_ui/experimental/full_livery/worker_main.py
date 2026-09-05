from __future__ import annotations

import concurrent.futures

import argparse
import json
import os
import threading
import time
import traceback
from pathlib import Path

import psutil

from .diagnostics import DiagnosticSession
from .jobs import execute_operation
from .protocol import read_request, write_json_atomic


def _watch_cancellation(cancel_file: Path, parent_pid: int, event: threading.Event) -> None:
    while not event.wait(0.05):
        if cancel_file.exists():
            event.set()
            return
        if parent_pid > 0 and not psutil.pid_exists(parent_pid):
            event.set()
            return


def run_request(request_file: str | Path, result_file: str | Path, parent_pid: int = 0) -> int:
    request = read_request(request_file)
    request_id = str(request.get("request_id") or "unknown")
    operation = str(request["operation"])
    session_dir = Path(str(request.get("session_dir") or Path(result_file).parent)).resolve()
    cancel_file = Path(str(request.get("cancel_file") or session_dir / "cancel"))
    diagnostic = DiagnosticSession(session_dir, operation, request_id)
    cancel_event = threading.Event()
    watcher = threading.Thread(
        target=_watch_cancellation,
        args=(cancel_file, int(parent_pid or 0), cancel_event),
        name="full-livery-cancel-watch",
        daemon=True,
    )
    watcher.start()
    started = time.monotonic()
    try:
        diagnostic.event("operation_started")
        def progress(message: str) -> None:
            write_json_atomic(session_dir / "progress.json", {"request_id": request_id, "message": message})
            diagnostic.event("progress", message=message)

        value = execute_operation(request, cancel_event, progress=progress)
        if cancel_event.is_set():
            raise InterruptedError("The full-livery task was cancelled.")
        response = {
            "protocol": int(request["protocol"]),
            "request_id": request_id,
            "operation": operation,
            "ok": True,
            "elapsed_seconds": time.monotonic() - started,
            "value": value,
        }
        write_json_atomic(result_file, response)
        diagnostic.complete(True)
        return 0
    except BaseException as exc:
        response = {
            "protocol": int(request.get("protocol") or 0),
            "request_id": request_id,
            "operation": operation,
            "ok": False,
            "cancelled": isinstance(exc, (InterruptedError, KeyboardInterrupt, concurrent.futures.CancelledError)),
            "elapsed_seconds": time.monotonic() - started,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        write_json_atomic(result_file, response)
        (session_dir / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
        diagnostic.complete(False, error_type=type(exc).__name__, error=str(exc))
        return 2
    finally:
        cancel_event.set()
        watcher.join(timeout=0.25)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--parent-pid", type=int, default=os.getppid())
    args = parser.parse_args(argv)
    return run_request(args.request, args.result, args.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
