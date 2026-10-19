"""Opt-out, period-scoped installation counts. Never use account or device data."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://kfps-community-library.hestia-cummings.workers.dev"
PRIVACY_TEXT = (
    "Send an anonymous activity count, at most once per UTC day, when KFPS, the editor "
    "or Studio is open. Separate random identifiers count active installations today, "
    "this ISO week and this calendar month. No account, key, hardware ID, artwork or "
    "file path is sent. KFPS stores no IP address; Cloudflare processes the connection. "
    "Period identifiers are scheduled for deletion 48 hours after each period ends. "
    "Cleanup delays and platform backups may retain them longer; aggregate counts remain. "
    "You can turn this off without losing any features."
)
STATE_DIRECTORY = "runtime/activity-private"
MAX_STATE_BYTES = 8192
MAX_RESPONSE_BYTES = 1024
MAX_ATTEMPTS = 3
UTC = timezone.utc
STATUS_VALUES = frozenset({"never_sent", "pending", "counted", "network_unavailable",
    "invalid_response", "unsupported_server", "server_unavailable", "storage_unavailable"})


def period_starts(day: str) -> dict[str, str]:
    d = datetime.strptime(day, "%Y-%m-%d").date()
    if d.isoformat() != day:
        raise ValueError("Invalid activity date")
    return {"day": day, "week": (d - timedelta(days=d.weekday())).isoformat(),
            "month": d.replace(day=1).isoformat()}


def activity_payload(seed: bytes, day: str) -> dict:
    if len(seed) != 32:
        raise ValueError("Invalid private activity seed")
    return {"v": 1, "periods": {kind: {"start": start, "token": hmac.new(
        seed, f"kfps-activity-v1|{kind}|{start}".encode("ascii"), hashlib.sha256).hexdigest()}
        for kind, start in period_starts(day).items()}}


def _protect(raw: bytes, *, decrypt=False) -> bytes:
    if os.name != "nt":
        return raw
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = Blob(len(raw), buffer)
    dest = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise OSError("Activity private storage unavailable")
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        kernel.LocalFree(dest.data)


def _ordinary(info, *, directory=False):
    return ((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            and not (getattr(info, "st_file_attributes", 0) & 0x400)
            and (directory or info.st_nlink == 1))


def _check_path(path: Path, *, directory=False):
    for item in reversed(path.parents):
        if not _ordinary(item.lstat(), directory=True):
            raise OSError("Unsafe activity directory")
    if path.exists() or path.is_symlink():
        if not _ordinary(path.lstat(), directory=directory):
            raise OSError("Unsafe activity file")


@contextmanager
def _locked(directory: Path, *, create=True):
    # Kernel locks release on crash; no stale lock-file timeout races.
    _check_path(directory.parent, directory=True)
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    _check_path(directory, directory=True)
    path = directory / "state.lock"
    _check_path(path)
    fd = os.open(path, os.O_RDWR | (os.O_CREAT if create else 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b", buffering=0) as handle:
        if not _ordinary(os.fstat(handle.fileno())):
            raise OSError("Unsafe activity lock")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _send(endpoint: str, payload: dict) -> tuple[int, dict]:
    request = Request(endpoint + "/v1/activity/ping", method="POST",
        data=json.dumps(payload, separators=(",", ":")).encode("ascii"),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "KFPS-Activity/1"})
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=4)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return response.code, {}
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            value = {}
        return response.code, value if isinstance(value, dict) else {}


class ActivityCounter:
    """Non-blocking host adapter. All public methods fail open for application use."""

    def __init__(self, app_root, *, endpoint=ENDPOINT, clock=time.time, transport=None):
        self.directory = Path(app_root).absolute() / STATE_DIRECTORY
        self.clock = clock
        self.transport = transport or _send
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.path not in ("", "/")
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Activity endpoint must be a bare HTTPS origin")
        self.endpoint = endpoint.rstrip("/")
        self._stop = threading.Event()
        self._thread = None
        self._mutex = threading.Lock()

    def _read(self):
        path = self.directory / "state.json"
        if not self.directory.exists():
            return {"schema": 1, "enabled": True}
        _check_path(path)
        if not path.exists():
            return {"schema": 1, "enabled": True}
        with path.open("rb") as file:
            if not _ordinary(os.fstat(file.fileno())):
                raise OSError("Unsafe activity state")
            raw = file.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            raise ValueError("Activity state too large")
        state = json.loads(raw)
        if (not isinstance(state, dict) or state.get("schema") != 1
                or type(state.get("enabled")) is not bool
                or set(state) - {"schema", "enabled", "seed", "success_day", "attempt_day",
                                 "attempts", "next_attempt", "clock_offset", "success_at", "last_status"}):
            raise ValueError("Invalid activity state")
        for name in ("success_day", "attempt_day"):
            if state.get(name):
                period_starts(state[name])
        if type(state.get("attempts", 0)) is not int or not 0 <= state.get("attempts", 0) <= MAX_ATTEMPTS:
            raise ValueError("Invalid attempt count")
        for name in ("next_attempt", "clock_offset", "success_at"):
            value = state.get(name, 0)
            if type(value) not in (float, int) or not math.isfinite(value) or abs(value) > 10**11:
                raise ValueError("Invalid activity timing")
        if "seed" in state and (not isinstance(state["seed"], str) or len(state["seed"]) > 2048):
            raise ValueError("Invalid private activity state")
        if state.get("last_status", "never_sent") not in STATUS_VALUES:
            raise ValueError("Invalid activity status")
        return state

    def _write(self, state):
        raw = json.dumps(state, separators=(",", ":"), allow_nan=False).encode("ascii")
        if len(raw) > MAX_STATE_BYTES:
            raise ValueError("Activity state too large")
        path = self.directory / "state.json"
        _check_path(path)
        temporary = self.directory / (".state-" + secrets.token_hex(8) + ".tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_runtime(self):
        runtime = self.directory.parent
        _check_path(runtime, directory=True)
        runtime.mkdir(mode=0o700, exist_ok=True)

    def enabled(self) -> bool:
        if os.environ.get("KFPS_ACTIVITY_DISABLED") == "1":
            return False
        try:
            if not self.directory.exists():
                return True
            # Windows readers otherwise briefly prevent an atomic state replacement.
            with _locked(self.directory):
                return self._read()["enabled"]
        except Exception:
            return False  # Damaged preferences never silently turn collection back on.

    def set_enabled(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            return False
        try:
            self._ensure_runtime()
            with _locked(self.directory):
                state = self._read()
                state["enabled"] = enabled
                self._write(state)
            return True
        except Exception:
            return False

    def usage_status(self) -> dict:
        """Read-only diagnostics allowlist. Never returns any seed, token or path."""
        disabled = os.environ.get("KFPS_ACTIVITY_DISABLED") == "1"
        result = {"enabled": not disabled, "status": "disabled" if disabled else "never_sent",
                  "last_success_utc": None, "last_success_age_seconds": None}
        try:
            if not self.directory.exists():
                return result
            with _locked(self.directory, create=False):
                state = self._read()
            result["enabled"] = state["enabled"] and not disabled
            result["status"] = "disabled" if not result["enabled"] else state.get("last_status", "never_sent")
            if state.get("success_at") is not None:
                stamp = state["success_at"]
                result["last_success_utc"] = datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                result["last_success_age_seconds"] = max(0, min(10 * 366 * 86400,
                    int(self.clock() + state.get("clock_offset", 0) - stamp)))
        except Exception:
            return {"enabled": False if disabled else None, "status": "state_unavailable",
                    "last_success_utc": None, "last_success_age_seconds": None}
        return result

    def run_once(self) -> str:
        """Call on a background thread only; fixed enums, never sensitive errors."""
        if self._stop.is_set() or not self.enabled():
            return "disabled"
        try:
            self._ensure_runtime()
            with _locked(self.directory):
                state = self._read()
                if not state["enabled"] or self._stop.is_set():
                    return "disabled"
                def failed(status):
                    state["last_status"] = status
                    self._write(state)
                    return status
                for correction in range(2):
                    wall = self.clock()
                    now = wall + state.get("clock_offset", 0)
                    day = datetime.fromtimestamp(now, UTC).date().isoformat()
                    if state.get("success_day") == day:
                        return "already_counted"
                    if state.get("attempt_day") != day:
                        state.update(attempt_day=day, attempts=0, next_attempt=0)
                    if state.get("attempts", 0) >= MAX_ATTEMPTS:
                        return "retry_limit"
                    delay = state.get("next_attempt", 0) - now
                    if 0 < delay <= 86400 and not correction:
                        return "backoff"
                    if "seed" not in state:
                        state["seed"] = _protect(secrets.token_bytes(32)).hex()
                    seed = _protect(bytes.fromhex(state["seed"]), decrypt=True)
                    payload = activity_payload(seed, day)
                    state["attempts"] += 1
                    state["next_attempt"] = now + (300 if state["attempts"] == 1 else 1800)
                    state["last_status"] = "pending"
                    self._write(state)  # Reserve retry budget before I/O, even if the host crashes.
                    try:
                        status, body = self.transport(self.endpoint, payload)
                    except Exception:
                        return failed("network_unavailable")
                    if not isinstance(body, dict):
                        return failed("invalid_response")
                    if status == 200 and body.get("ok") is True and body == {"ok": True, "day": day}:
                        state["success_day"] = day
                        state["success_at"] = now
                        state["next_attempt"] = 0
                        state["last_status"] = "counted"
                        self._write(state)
                        return "counted"
                    if (status == 409 and not correction and body.get("error") == "activity_period_changed"
                            and set(body) == {"error", "day", "utc"}):
                        try:
                            server = datetime.strptime(body["utc"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
                        except (ValueError, TypeError):
                            return failed("invalid_response")
                        if server.date().isoformat() != body["day"]:
                            return failed("invalid_response")
                        offset = server.timestamp() - self.clock()
                        if abs(offset) > 10 * 366 * 86400:
                            return failed("invalid_response")
                        # Preserve the attempts when changing period after clock correction.
                        state.update(clock_offset=offset, attempt_day=body["day"], next_attempt=0)
                        self._write(state)
                        continue
                    if status in (404, 405, 410):
                        state["attempts"] = MAX_ATTEMPTS
                        return failed("unsupported_server")
                    return failed("server_unavailable")
                return failed("invalid_response")
        except Exception:
            return "storage_unavailable"

    def start(self):
        with self._mutex:
            if self._thread and self._thread.is_alive():
                return self
            if self._stop.is_set() or os.environ.get("KFPS_ACTIVITY_DISABLED") == "1":
                return self
            try:
                self._thread = threading.Thread(target=self._run, daemon=True, name="kfps-activity")
                self._thread.start()
            except Exception:
                self._thread = None  # Optional metrics must not prevent a host from opening.
        return self

    def _run(self):
        if self._stop.wait(15 + secrets.randbelow(31)):
            return
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(60)

    def stop(self):
        # Non-blocking. An in-flight request may finish; sockets use a 4s I/O timeout.
        self._stop.set()


def usage_status(app_root) -> dict:
    """Collector entry point; construction does not start the counter."""
    return ActivityCounter(app_root).usage_status()
