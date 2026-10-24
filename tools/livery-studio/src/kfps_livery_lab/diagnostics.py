"""Local, privacy-allowlisted Studio diagnostics. Never retain caller text."""
from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import re
import secrets
import stat
import threading
import time

from .storage_paths import SafeRoot

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "runs" / "diagnostics"
FILES = ("studio.jsonl", "studio.1.jsonl", "studio.2.jsonl")
MAX_FILE_BYTES = 256 * 1024
MAX_BODY_BYTES = 8192
MAX_EVENT_BYTES = 1024
MAX_BATCH = 16
MAX_SNAPSHOT_BYTES = 48 * 1024
ENUMS = {
    "event": {"host", "readiness", "render", "counts", "action", "error", "request", "closed"},
    "host": {"backend", "native", "chrome", "unknown"},
    "gpu_policy": {"auto", "opengl", "d3d11", "browser-default", "unknown"},
    "action": {"launch", "import", "edit", "undo", "redo", "save", "reopen", "source_edit",
               "source_return", "cancel", "car_switch", "export", "checkpoint", "theme", "language",
               "component", "reset", "render", "library", "recovery", "selection"},
    "outcome": {"start", "ok", "error", "cancelled", "stale", "busy", "requested"},
    "error_code": {"http_4xx", "http_5xx", "network", "aborted", "javascript", "preview",
                   "context_lost", "shader", "operation", "timeout", "unknown"},
}
NUMBERS = {
    **dict.fromkeys(("duration_ms", "frame_ms", "frame_mean_ms", "frame_max_ms", "compose_ms", "load_ms"), 600000),
    "canvas_width": 32768, "canvas_height": 32768, "pixel_ratio": 8,
    "source_count": 4096, "placement_count": 65536, "section_count": 64, "shape_count": 1000000,
    "geometries": 1000000, "textures": 1000000, "programs": 100000, "draw_calls": 1000000,
    "triangles": 1000000000, "resource_bytes": 16 * 1024**3, "frame_count": 2**31-1, "http_status": 599,
}
BOOLEANS = {"ready", "webgl", "visible"}
VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}\Z", re.ASCII)
META = {"schema_version", "utc", "session", "sequence"}


def sanitize_event(value):
    """Reject unknown keys and types; no coercion, truncation, or error strings."""
    try:
        if type(value) is not dict or not 1 <= len(value) <= 40 or "event" not in value:
            return None
        clean = {}
        for key, item in value.items():
            if key in ENUMS:
                if type(item) is not str or item not in ENUMS[key]:
                    return None
            elif key in NUMBERS:
                if type(item) not in (int, float) or not math.isfinite(item) or not 0 <= item <= NUMBERS[key]:
                    return None
                if not key.endswith("_ms") and key != "pixel_ratio" and type(item) is not int:
                    return None
                item = round(item, 2)
            elif key in BOOLEANS:
                if type(item) is not bool:
                    return None
            elif key == "app_version":
                if type(item) is not str or not VERSION.fullmatch(item):
                    return None
            else:
                return None
            clean[key] = item
        if len(json.dumps(clean, separators=(",", ":"), allow_nan=False)) > MAX_EVENT_BYTES - 160:
            return None
        return clean
    except (TypeError, ValueError, OverflowError):
        return None


def application_version(root):
    try:
        with (Path(root) / "VERSION").open("rb") as stream:
            value = stream.read(33).decode("ascii").strip()
        return value if VERSION.fullmatch(value) else None
    except (OSError, UnicodeError):
        return None


def clean_record(value):
    """Neutral collector API: return one canonical record or None, never text."""
    try:
        if type(value) is not dict or not META.issubset(value) or len(value) > 44:
            return None
        if (type(value["schema_version"]) is not int or value["schema_version"] != 1
                or type(value["sequence"]) is not int or not 1 <= value["sequence"] <= 2**53-1
                or type(value["session"]) is not str or not re.fullmatch("[0-9a-f]{16}", value["session"])
                or type(value["utc"]) is not str or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value["utc"], re.ASCII)):
            return None
        fields = sanitize_event({k: v for k, v in value.items() if k not in META})
        if fields is None:
            return None
        result = {"schema_version": 1, "utc": value["utc"], "session": value["session"],
                  "sequence": value["sequence"], **fields}
        if len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode("ascii")) > MAX_EVENT_BYTES:
            return None
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def _read_records(safe, path, maximum):
    if safe.check(path, directory=False, missing=True) is None:
        return b"", []
    data = safe.read(path, maximum)
    if data and not data.endswith(b"\n"):
        raise ValueError("incomplete diagnostic file")
    records = []
    for line in data.splitlines():
        if len(line) > MAX_EVENT_BYTES:
            raise ValueError("invalid diagnostic record")
        row = clean_record(json.loads(line))
        if row is None:
            raise ValueError("unfamiliar diagnostic file")
        records.append(row)
    return data, records


def read_snapshot(root=None):
    """Read-only, <=48 KiB collector snapshot. No mkdir, threads, locks or UI."""
    result = {"schema_version": 1, "persistence": "missing", "records": [], "truncated": False}
    try:
        root = Path(root) if root is not None else DEFAULT_ROOT
        safe = SafeRoot(root)
        retained = deque(maxlen=32)
        for name in reversed(FILES):
            data, records = _read_records(safe, root / name, MAX_FILE_BYTES)
            if data:
                result["persistence"] = "ok"
            result["truncated"] |= len(retained) + len(records) > 32
            retained.extend(records)
        result["records"] = list(retained)
        while len(json.dumps(result, ensure_ascii=True).encode("ascii")) > MAX_SNAPSHOT_BYTES:
            result["records"].pop(0)
            result["truncated"] = True
    except Exception:
        result = {"schema_version": 1, "persistence": "unavailable", "records": [], "truncated": False}
    return result


def request_action(method, relative):
    """Classify paths without storing path components, query strings or IDs."""
    path = relative.split("?", 1)[0]
    if method == "POST":
        if path == "api/projects":
            return "save"
        if path.startswith("api/source-editor/"):
            return {"return": "source_return", "take": "source_return", "cancel": "cancel"}.get(path.rsplit("/", 1)[-1])
        if path == "api/source-editor":
            return "source_edit"
        if path.startswith("api/car-switch"):
            return "cancel" if path.endswith("/cancel") else "car_switch"
        if path.startswith("api/recovery"):
            return "recovery"
        return {"api/import-vinyl": "import", "api/render-vinyl": "render", "api/export-experiment": "export", "api/export-section": "export",
                "api/ui-theme": "theme", "api/host-theme": "theme", "api/language": "language"}.get(path)
    if method == "GET":
        if path.startswith("api/projects/"):
            return "reopen"
        if path.startswith("api/vinyl-library/file") or path.startswith("api/host-vinyl/"):
            return "import"
    return None


class DiagnosticLog:
    def __init__(self, root=None, *, max_bytes=MAX_FILE_BYTES, clock=time.monotonic):
        self.root = Path(root) if root is not None else DEFAULT_ROOT
        self.max_bytes = max(2048, min(MAX_FILE_BYTES, max_bytes))
        self.clock = clock
        self.session = secrets.token_hex(8)
        self.pending = queue.Queue(maxsize=64)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.recent = deque(maxlen=32)
        self.tokens, self.refill = 32., clock()
        self.sequence = self.written = self.dropped = 0
        self.status = "starting"
        self.worker = threading.Thread(target=self._run, name="studio-diagnostics", daemon=True)
        try:
            self.worker.start()
        except Exception:
            self.status = "unavailable"
            self.stop.set()

    def record(self, event, **fields):
        try:
            value = sanitize_event({"event": event, **fields})
            with self.lock:
                now = self.clock()
                self.tokens = min(32., self.tokens + max(0, now - self.refill) * 2)
                self.refill = now
                if value is None or self.stop.is_set() or self.tokens < 1:
                    self.dropped += 1
                    return False
                self.tokens -= 1
                self.sequence += 1
                record = {"schema_version": 1, "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "session": self.session, "sequence": self.sequence, **value}
                try:
                    self.pending.put_nowait(record)
                    return True
                except queue.Full:
                    self.dropped += 1
                    return False
        except Exception:
            return False

    def accept(self, value):
        if type(value) is not dict or set(value) != {"events"} or type(value["events"]) is not list or not 1 <= len(value["events"]) <= MAX_BATCH:
            return 0
        count = 0
        for event in value["events"]:
            clean = sanitize_event(event)
            if clean is not None:
                count += self.record(**clean)
        return count

    def report(self):
        with self.lock:
            return {"schema_version": 1, "persistence": self.status, "written": self.written,
                    "dropped": self.dropped, "queued": self.pending.qsize(), "recent": list(self.recent)}

    def close(self):
        self.stop.set()
        if self.worker.ident is not None:
            self.worker.join(timeout=.3)

    def _existing(self, safe, path):
        return _read_records(safe, path, self.max_bytes)

    def _write(self, rows):
        safe = SafeRoot(self.root)
        body = b"".join((json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii") for row in rows)
        if len(body) > self.max_bytes:
            raise ValueError("diagnostic batch exceeds file budget")
        with safe.lock():
            paths = [self.root / name for name in FILES]
            # Validate only the three owned filenames. Preserve unfamiliar/corrupt files.
            existing = [self._existing(safe, path) for path in paths]
            if not rows:
                return [row for _data, records in reversed(existing) for row in records][-32:]
            if len(existing[0][0]) + len(body) > self.max_bytes:
                if paths[2].exists():
                    paths[2].unlink()
                if paths[1].exists():
                    paths[1].replace(paths[2])
                if paths[0].exists():
                    paths[0].replace(paths[1])
            fd = os.open(paths[0], os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                info, current = os.fstat(fd), safe.check(paths[0], directory=False)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                        or info.st_size + len(body) > self.max_bytes):
                    raise ValueError("diagnostic file changed")
                with os.fdopen(fd, "ab", closefd=False) as stream:
                    stream.write(body)
                    stream.flush()
            finally:
                os.close(fd)
        return rows

    def _run(self):
        retry_at = 0
        try:
            prior = self._write([])
            with self.lock:
                self.recent.extend(prior)
                self.status = "ok"
        except Exception:
            with self.lock:
                self.status = "unavailable"
            retry_at = self.clock() + 30
        while not self.stop.is_set() or not self.pending.empty():
            try:
                row = self.pending.get(timeout=.1)
            except queue.Empty:
                continue
            rows = [row]
            # A small file budget is useful in isolated rotation tests.
            while len(rows) < min(MAX_BATCH, max(1, self.max_bytes // MAX_EVENT_BYTES)):
                try:
                    rows.append(self.pending.get_nowait())
                except queue.Empty:
                    break
            try:
                if self.clock() < retry_at:
                    raise OSError("diagnostic cooldown")
                self._write(rows)
                with self.lock:
                    self.written += len(rows)
                    self.recent.extend(rows)
                    self.status = "ok"
            except Exception:
                if self.clock() >= retry_at:
                    retry_at = self.clock() + 30
                with self.lock:
                    self.dropped += len(rows)
                    self.status = "unavailable"
            finally:
                for _ in rows:
                    self.pending.task_done()
