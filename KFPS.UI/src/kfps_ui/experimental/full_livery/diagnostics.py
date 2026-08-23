from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import psutil


_USER_PATH = re.compile(r"(?i)([a-z]:\\users\\)[^\\/]+")


def scrub_text(value: object) -> str:
    text = str(value or "")
    text = _USER_PATH.sub(r"\1<user>", text)
    return text.replace(os.environ.get("USERNAME", "\0"), "<user>")


def environment_snapshot() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "memory_bytes": int(psutil.virtual_memory().total),
        "pid": os.getpid(),
    }


class DiagnosticSession:
    def __init__(self, directory: str | Path, operation: str, request_id: str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.events_file = self.directory / "events.jsonl"
        self.marker = self.directory / "active.json"
        self.operation = str(operation)
        self.request_id = str(request_id)
        self.started = time.time()
        self._write_marker("running")
        self.event("session_started", environment=environment_snapshot())

    def _write_marker(self, state: str, **extra: Any) -> None:
        payload = {
            "request_id": self.request_id,
            "operation": self.operation,
            "state": state,
            "started_at": self.started,
            "updated_at": time.time(),
            **extra,
        }
        temporary = self.marker.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.marker)

    def event(self, name: str, **fields: Any) -> None:
        record = {
            "time": time.time(),
            "request_id": self.request_id,
            "operation": self.operation,
            "event": str(name),
            **fields,
        }
        with self.events_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")

    def complete(self, ok: bool, **fields: Any) -> None:
        self.event("session_completed", ok=bool(ok), elapsed_seconds=time.time() - self.started, **fields)
        self._write_marker("completed" if ok else "failed", **fields)


def recover_abandoned_sessions(sessions_root: str | Path, recovery_root: str | Path) -> list[str]:
    sessions_root = Path(sessions_root)
    recovery_root = Path(recovery_root)
    recovery_root.mkdir(parents=True, exist_ok=True)
    recovered = []
    if not sessions_root.is_dir():
        return recovered
    for marker in sessions_root.glob("*/active.json"):
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("state") != "running":
            continue
        payload["state"] = "abandoned"
        payload["recovered_at"] = time.time()
        target = recovery_root / f"{marker.parent.name}.json"
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        recovered.append(marker.parent.name)
    return recovered


def prune_sessions(sessions_root: str | Path, keep: int = 30) -> None:
    root = Path(sessions_root)
    if not root.is_dir():
        return
    directories = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for directory in directories[max(1, int(keep)):]:
        shutil.rmtree(directory, ignore_errors=True)


def export_diagnostic_bundle(
    output: str | Path,
    *,
    sessions_root: str | Path,
    recovery_root: str | Path,
    catalog_stats: dict[str, Any],
    release_state: dict[str, Any],
) -> Path:
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        summary = {
            "format": "kfps_full_livery_diagnostics_v1",
            "created_at": time.time(),
            "environment": environment_snapshot(),
            "catalog": catalog_stats,
            "release": release_state,
        }
        archive.writestr("summary.json", json.dumps(summary, indent=2) + "\n")
        for root_name, root_value in (("sessions", sessions_root), ("recovery", recovery_root)):
            root = Path(root_value)
            if not root.is_dir():
                continue
            for source in root.rglob("*"):
                if not source.is_file() or source.suffix.casefold() not in {".json", ".jsonl", ".log", ".txt"}:
                    continue
                try:
                    with source.open("rb") as handle:
                        size = source.stat().st_size
                        if size > 2 * 1024 * 1024:
                            handle.seek(size - 2 * 1024 * 1024)
                        text = scrub_text(handle.read().decode("utf-8", errors="replace"))
                except OSError:
                    continue
                archive.writestr(f"{root_name}/{source.relative_to(root).as_posix()}", text)
    os.replace(temporary, target)
    return target
