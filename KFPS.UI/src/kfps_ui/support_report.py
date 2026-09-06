"""Bounded, on-demand support context. Never reads artwork, saves, or game memory."""
from __future__ import annotations

import base64
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psutil


SCHEMA = "kfps-support-report/1"
MAX_REPORT_BYTES = 48 * 1024
FORM_ORIGIN = "https://kfps-support-staging.hestia-cummings.workers.dev"
DISCORD_URL = "https://discord.gg/XT8dG8bDKy"
FEATURES = {
    "create": "Generator", "generate": "Generator", "outputs": "Import and export",
    "editor": "Editor", "liveries": "Liveries", "community": "Community",
    "update": "Updater",
}
_SECRET_LINE = re.compile(
    r"(?im)^.*\b(?:authorization|cookie|password|secret|bearer|api[ _-]?key|"
    r"activation[ _-]?key|access[ _-]?token|refresh[ _-]?token|receipt)\b.*$"
)
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)
_WIN_PATH = re.compile(r"(?i)\b[a-z]:[\\/][^\r\n\"'<>|]*")
_UNC_PATH = re.compile(r"\\\\[^\r\n\"'<>|]+")
_POSIX_HOME = re.compile(r"/(?:home|Users)/[^\s\"'<>]+")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]{1,128}@[\w.-]{1,253}\.[A-Za-z]{2,24}")
_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b")
_FILE = re.compile(r"(?<![^\s\"'<>:/\\])[^\s\"'<>:/\\]{1,240}\.(?:json|png|jpe?g|webp|bmp|svg|kfpslivery|zip|7z)\b", re.I)
_IDENTIFIER = re.compile(r"\b(?:\d{15,20}|[a-f0-9]{32,})\b", re.I)
_ERROR = re.compile(r"\b(?:error|failed|failure|refused|exception|unavailable|denied|crash)\b", re.I)


def redact(value: object, limit: int = 1600) -> str:
    text = str(value or "")[:60000]
    text = _SECRET_LINE.sub("[sensitive line removed]", text)
    text = _URL.sub("[url removed]", text)
    text = _WIN_PATH.sub("[local path removed]", text)
    text = _UNC_PATH.sub("[network path removed]", text)
    text = _POSIX_HOME.sub("[local path removed]", text)
    text = _TOKEN.sub("[credential removed]", text)
    text = _EMAIL.sub("[email removed]", text)
    text = _IDENTIFIER.sub("[identifier removed]", text)
    text = "\n".join("[file reference removed]" if _FILE.search(line) else line for line in text.split("\n"))
    # Remove control characters but retain layout in reviewed text.
    text = "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))
    return text[:limit]


def _small_mapping(value: object, keys: tuple[str, ...]) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in keys:
        item = value.get(key)
        if isinstance(item, str):
            result[key] = redact(item, 700)
        elif isinstance(item, (bool, int)) or (isinstance(item, float) and math.isfinite(item)):
            result[key] = item
    return result


def recent_locator_summary(root: Path, *, since: float, now: float) -> dict:
    path = root / "runtime" / "live-memory" / "reports" / "latest.json"
    try:
        if not path.resolve().is_relative_to((root / "runtime").resolve()):
            return {}
        stat = path.stat()
        if stat.st_size > 2 * 1024 * 1024 or not since <= stat.st_mtime <= now + 5:
            return {}
        with path.open("rb") as handle:
            raw = handle.read(2 * 1024 * 1024 + 1)
        report = json.loads(raw)
        if not isinstance(report, dict) or len(raw) > 2 * 1024 * 1024:
            return {}
        created = datetime.fromisoformat(str(report.get("created_utc", "")).replace("Z", "+00:00")).timestamp()
        if not since <= created <= now + 5:
            return {}
    except (OSError, ValueError, TypeError):
        return {}
    return {
        "engine_version": redact(report.get("engine_version"), 100),
        "created_utc": report.get("created_utc"),
        "request": _small_mapping(report.get("request"), ("game", "purpose", "layer_count")),
        "outcome": _small_mapping(report.get("outcome"), ("status", "reason", "authoritative", "failure_reason", "refusal_reason")),
        "store_variant": redact(report.get("store_variant"), 80),
    }


def collect_technical() -> dict:
    from live_memory_locator.diagnostics import environment_snapshot, infer_store_variant
    from game_adapters import find_running_supported_games

    environment = environment_snapshot({})
    hardware = _small_mapping(environment, ("platform", "architecture", "processor", "logical_cpu_count", "memory_bytes"))
    hardware["gpus"] = [
        _small_mapping(gpu, ("name", "driver_version"))
        for gpu in (environment.get("gpus") or [])[:8] if isinstance(gpu, dict)
    ]
    games = []
    for game in find_running_supported_games()[:4]:
        try:
            executable = psutil.Process(game.pid).exe()
        except (psutil.Error, OSError):
            executable = ""
        games.append({"game": game.adapter.key.upper(), "store": infer_store_variant({"name": game.process_name, "executable": executable})})
    dependencies = {}
    for name in ("PySide6", "numpy", "Pillow", "opencv-python", "opencv-python-headless", "psutil"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "not installed under this package name"
    return {
        "hardware": hardware, "running_games": games, "dependencies": dependencies,
        "python": platform.python_version(), "python_bits": 64 if sys.maxsize > 2**32 else 32,
    }


def build_support_report(root: Path, context: dict, *, since: float, collect=collect_technical) -> dict:
    now = time.time()
    page = str(context.get("page") or "other")
    feature = FEATURES.get(page, "Other")
    states = {}
    logs = []
    for name, values in context.get("services", {}).items():
        states[name] = _small_mapping(values, (
            "status", "running", "lastError", "activeGame", "selectedLayers", "selectedShapes",
            "candidateCount", "exportedCount", "skippedCount", "viewerReady", "packageAddError",
            "dependenciesText", "pythonText", "runtimeText", "selectedPresetIndex",
        ))
        if values.get("liveLog"):
            lines = str(values["liveLog"]).splitlines()[-45:]
            logs.append({"source": name, "text": redact("\n".join(lines), 4500)})
    logs.append({"source": "app", "text": redact("\n".join(str(context.get("log") or "").splitlines()[-65:]), 6500)})
    current_name = {"create": "generator", "generate": "generator", "outputs": "transfer",
                    "liveries": "liveries", "community": "community", "editor": "editor", "update": "updater"}.get(page)
    current = next((entry["text"] for entry in logs if entry["source"] == current_name), "")
    errors = [line for line in current.splitlines() if _ERROR.search(line)]
    last_error = errors[-1] if errors else states.get(current_name, {}).get("lastError", "")
    if not last_error and current_name and _ERROR.search(str(states.get(current_name, {}).get("status", ""))):
        last_error = states[current_name]["status"]
    try:
        technical = collect()
    except Exception:
        technical = {"collection_warning": "Some system details could not be collected."}
    technical["app"] = {
        "version": redact(context.get("version"), 60), "theme": redact(context.get("theme"), 80),
        "page": page, "uptime_seconds": max(0, int(now - since)),
    }
    technical["states"] = states
    if page == "outputs":
        technical["locator"] = recent_locator_summary(root, since=max(since, now - 3600), now=now)
    technical["logs"] = logs
    report = {
        "schema": SCHEMA, "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(), "source": "kfps",
        "feature": feature, "title": redact(last_error or f"{feature} issue", 100),
        "description": redact(last_error, 1600), "technical": technical,
    }
    if len(json.dumps(report).encode()) > MAX_REPORT_BYTES:
        report["technical"]["logs"] = []
        report["technical"]["collection_warning"] = "Log excerpt omitted to keep this report bounded."
    if len(json.dumps(report).encode()) > MAX_REPORT_BYTES:
        raise ValueError("The support report exceeds its size limit.")
    return report


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.08 * (attempt + 1))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_handoff(root: Path, report: dict, *, origin: str = FORM_ORIGIN) -> tuple[Path, Path]:
    url = urlsplit(origin)
    if origin != FORM_ORIGIN and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}):
        raise ValueError("The support form address is not trusted.")
    if url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}:
        raise ValueError("Invalid support form address.")
    report_id = str(uuid.UUID(report["id"]))
    payload = json.dumps(report, ensure_ascii=True, separators=(",", ":"))
    if len(payload.encode()) > MAX_REPORT_BYTES:
        raise ValueError("The support report exceeds its size limit.")
    folder = root / "runtime" / "support-reports" / report_id
    json_path = folder / "report.json"
    handoff = folder / "open-report.html"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    destination = origin.rstrip("/") + "/#draft=" + encoded
    # All injected data is JSON-escaped; only the reviewed, sanitized report is carried.
    script_url = json.dumps(destination).replace("<", "\\u003c")
    html = '<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
    html += '<title>KFPS support report</title><p>Opening the report review form...</p>'
    html += f'<script>location.replace({script_url});</script>'
    atomic_text(json_path, payload + "\n")
    atomic_text(handoff, html)
    atomic_text(root / "runtime" / "support-reports" / "latest.json", payload + "\n")
    return json_path, handoff
