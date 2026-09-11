"""Bounded local editor diagnostics. Never accepts artwork or free-form user text."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import threading
import time
import uuid


SCHEMA = "kfps-editor-diagnostics/1"
MAX_REQUEST = 24 * 1024
MAX_SNAPSHOT = 48 * 1024
ASSETS = (
    "index.html", "editor.js", "editor-core.js", "editor-fabric-adapter.js",
    "editor-diagnostics.js", "editor-preferences.js", "editor-persistence.js",
    "editor-persistence-worker.js", "editor-pixel-core.js", "editor-pixel-worker.js",
    "editor-assets.js", "editor-i18n.js", "vendor/fabric.min.js", "locales/en.js", "locales/ko.js",
)
KINDS = frozenset((
    "page-start", "action-start", "action-end", "command", "edit", "long-task",
    "frame-stall", "js-error", "rejection", "resource-error", "console-warning",
    "console-error", "webgl-lost", "webgl-restored", "canvas-lost", "canvas-restored",
    "preview-fallback", "recovery-result", "native-start", "native-ready", "native-failed",
    "native-reload", "native-close", "renderer-stopped", "close-timeout", "heartbeat-stale",
))
ACTIONS = frozenset((
    "idle", "pointer", "move", "scale", "skew", "rotate", "pan", "zoom", "guide",
    "select", "reference", "numeric", "nudge", "undo", "redo", "add", "duplicate",
    "delete", "copy", "paste", "color", "mask", "order", "group", "layout", "save",
    "load", "new", "export", "asset", "text", "pixel", "settings", "edit",
))
NUMBERS = frozenset((
    "at", "duration", "line", "code", "shapeType", "selected", "frames", "frameP50",
    "frameP95", "frameP99", "frameMax", "gaps50", "gaps100", "gaps250", "gaps500",
    "tasks", "taskMax", "totalTasks", "totalGaps100", "totalGaps500", "renderMax",
    "renderCount", "layers", "objects", "helpers", "zoom", "width", "height",
    "referenceWidth", "referenceHeight", "referenceChars", "referenceOpacity", "history",
    "heapBytes", "revision", "browserRevision", "serverRevision", "browserAt", "serverAt",
    "pendingRevision", "uiLag", "dropped", "seq", "rendererPid", "rssBytes", "childRssBytes",
    "draws", "totalDraws", "selectedId", "buttons", "modifiers", "clientDrops", "editorRevision",
))
BOOLS = frozenset(("visible", "focused", "referenceAbove", "referenceVisible", "browserOk", "serverOk", "ready", "minimized"))
ENUMS = {
    "kind": KINDS, "action": ACTIONS,
    "renderer": frozenset(("fabric", "gpu-preview", "fallback", "starting")),
    "state": frozenset(("pending", "saved", "failed", "idle", "starting", "ready", "closed")),
    "error": frozenset(("Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError", "SecurityError", "AbortError", "QuotaExceededError", "unknown")),
    "source": frozenset(ASSETS + ("native", "unknown")),
}


def clean_fields(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if key in NUMBERS and type(item) in (int, float) and math.isfinite(item) and abs(item) <= 2**53 - 1:
            result[key] = item
        elif key in BOOLS and type(item) is bool:
            result[key] = item
        elif key in ENUMS and isinstance(item, str) and item in ENUMS[key]:
            result[key] = item
    return result


def clean_packet(value):
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Invalid diagnostic schema")
    if not isinstance(value.get("page"), str) or not re.fullmatch(r"[a-f0-9]{32}", value["page"]):
        raise ValueError("Invalid diagnostic page")
    if type(value.get("seq")) is not int or not 0 <= value["seq"] <= 2**53 - 1:
        raise ValueError("Invalid diagnostic sequence")
    events = value.get("events", [])
    if not isinstance(events, list) or len(events) > 48:
        raise ValueError("Too many diagnostic events")
    return {"page": value["page"], "seq": value["seq"],
            **{key: clean_fields(value.get(key)) for key in ("metrics", "state", "recovery")},
            "events": [entry for item in events if (entry := clean_fields(item)).get("kind")]}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class EditorDiagnostics:
    def __init__(self, root: Path, runtime: Path, *, max_log_bytes=2 * 1024 * 1024):
        self.root, self.runtime = Path(root), Path(runtime)
        self.session = uuid.uuid4().hex
        self.max_log_bytes = max_log_bytes
        self._queue = queue.Queue(maxsize=128)
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._packet = {}
        self._page_at = 0.0
        self._native_at = 0.0
        self._native = {}
        self._recent = deque(maxlen=48)
        self._dropped = 0
        self._accepted = self._written = 0
        self._last_write = 0.0
        self._error = ""
        self._identity = {}
        self._memory_at = 0.0
        self._thread = threading.Thread(target=self._run, name="editor-diagnostics", daemon=True)
        self._thread.start()

    def accept(self, value):
        packet = clean_packet(value)
        with self._lock:
            if packet["page"] == self._packet.get("page") and packet["seq"] <= self._packet.get("seq", -1):
                return self._accepted
            self._packet = packet
            self._page_at = time.time()
        return self._submit({"kind": "sample", **packet})

    def record(self, kind, **fields):
        return self._submit(clean_fields({"kind": kind, **fields}))

    def native_tick(self, **fields):
        with self._lock:
            self._native.update(clean_fields(fields))
            self._native_at = time.time()

    def _submit(self, item):
        if self._closed.is_set():
            return 0
        with self._lock:
            self._accepted += 1
            serial = self._accepted
            item = {"schema": SCHEMA, "session": self.session, "utc": utc_now(), "serial": serial, **item}
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self._dropped += 1
        return serial

    def status(self):
        with self._lock:
            return {"accepted": self._accepted, "written": self._written,
                    "last_write": self._last_write, "error": self._error,
                    "dropped": self._dropped, "queue": self._queue.qsize()}

    def snapshot(self):
        with self._lock:
            return {"schema": SCHEMA, "session": self.session, "updated": time.time(),
                    "page_received": self._page_at, "native_received": self._native_at,
                    "identity": self._identity, "native": dict(self._native),
                    "page": dict(self._packet), "recent": list(self._recent),
                    "logging": {"accepted": self._accepted, "written": self._written,
                                "last_write": self._last_write, "error": self._error, "dropped": self._dropped}}

    def _identify(self):
        identity = {"assets": {}, "version": "unknown"}
        try:
            version = (self.root / "VERSION").read_text(encoding="utf-8").strip()
            if re.fullmatch(r"[0-9.\-a-zA-Z]{1,40}", version):
                identity["version"] = version
        except OSError:
            pass
        for name in ASSETS:
            try:
                identity["assets"][name] = hashlib.sha256((self.root / "tools/fabric-editor" / name).read_bytes()).hexdigest()
            except OSError:
                identity["assets"][name] = "missing"
        with self._lock:
            self._identity = identity

    def _write_batch(self, records):
        if time.monotonic() - self._memory_at > 5:
            self._memory_at = time.monotonic()
            try:
                import psutil
            except ImportError:
                pass
            else:
                try:
                    process = psutil.Process()
                    child_rss = 0
                    for child in process.children(recursive=True):
                        try:
                            child_rss += child.memory_info().rss
                        except psutil.Error:
                            pass
                    with self._lock:
                        self._native.update(rssBytes=process.memory_info().rss, childRssBytes=child_rss)
                except (psutil.Error, OSError):
                    pass
        self.runtime.mkdir(parents=True, exist_ok=True)
        log = self.runtime / "performance.jsonl"
        body = "".join(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n" for record in records)
        if log.exists() and log.stat().st_size + len(body.encode("utf-8")) > self.max_log_bytes:
            previous = log.with_name("performance.1.jsonl")
            if previous.exists():
                os.replace(previous, log.with_name("performance.2.jsonl"))
            os.replace(log, previous)
        with log.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
            handle.flush()
        for record in records:
            entries = record.get("events", []) if record["kind"] == "sample" else [record]
            for entry in entries:
                with self._lock:
                    self._recent.append({"utc": record["utc"], **clean_fields(entry)})
        snapshot = self.snapshot()
        snapshot["logging"].update(written=records[-1]["serial"], last_write=time.time(), error="")
        temporary = self.runtime / ".diagnostics.tmp"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(snapshot, handle, separators=(",", ":"), allow_nan=False)
                handle.flush()
            os.replace(temporary, self.runtime / "diagnostics.json")
        finally:
            temporary.unlink(missing_ok=True)
        with self._lock:
            self._written = records[-1]["serial"]
            self._last_write = snapshot["logging"]["last_write"]
            self._error = ""

    def _run(self):
        self._identify()
        while not self._closed.is_set() or not self._queue.empty():
            try:
                first = self._queue.get(timeout=.25)
            except queue.Empty:
                continue
            records = [first]
            while len(records) < 16:
                try:
                    records.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._write_batch(records)
            except (OSError, ValueError, TypeError) as error:
                with self._lock:
                    self._error = type(error).__name__
                    self._dropped += len(records)
            finally:
                for _ in records:
                    self._queue.task_done()

    def close(self):
        self._closed.set()
        self._thread.join(timeout=2)


def read_support_diagnostics(root: Path):
    """Read only the bounded, schema-checked diagnostic snapshot, never desktop.log."""
    path = Path(root) / "runtime/fabric-editor/diagnostics.json"
    try:
        if not path.resolve().is_relative_to((Path(root) / "runtime").resolve()):
            return {}
        with path.open("rb") as handle:
            raw = handle.read(MAX_SNAPSHOT + 1)
        if len(raw) > MAX_SNAPSHOT:
            return {"unavailable": "snapshot_too_large"}
        snapshot = json.loads(raw)
        if snapshot.get("schema") != SCHEMA:
            return {}
        page = snapshot.get("page") or {}
        updated, page_received = float(snapshot["updated"]), float(snapshot.get("page_received") or 0)
        if not math.isfinite(updated) or not math.isfinite(page_received):
            raise ValueError("Invalid diagnostic timestamps")
        result = {"schema": SCHEMA, "age_seconds": max(0, round(time.time() - updated, 1)),
                  "page_age_seconds": max(0, round(time.time() - page_received, 1)),
                  "native": clean_fields(snapshot.get("native")),
                  "page": clean_packet({"schema": 1, **page}) if page else {},
                  "recent": [clean_fields(item) for item in snapshot.get("recent", [])[-16:]]}
        identity = snapshot.get("identity") or {}
        version = identity.get("version", "")
        result["version"] = version if isinstance(version, str) and re.fullmatch(r"[0-9.\-a-zA-Z]{1,40}", version) else "unknown"
        result["installed_assets"] = {key: value for key, value in identity.get("assets", {}).items()
                                      if key in ASSETS and isinstance(value, str) and (value == "missing" or re.fullmatch(r"[a-f0-9]{64}", value))}
        logging = snapshot.get("logging") or {}
        result["logging"] = {key: value for key, value in logging.items() if key in {"accepted", "written", "dropped", "last_write"} and type(value) in (int, float) and math.isfinite(value)}
        result["logging"]["failed"] = bool(logging.get("error"))
        return result
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"unavailable": "snapshot_unreadable"} if path.exists() else {}
