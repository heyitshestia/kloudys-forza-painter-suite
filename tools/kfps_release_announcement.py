"""Offline, per-install release notice shared by all KFPS hosts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import errno
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import threading
import time
import webbrowser

from tools.kfps_display_language import display_language

WINDOW_SECONDS = 7 * 24 * 60 * 60
LEASE_SECONDS = 30
SUPPORT_URL = "https://ko-fi.com/O7O020EQNQ"
_LOG = logging.getLogger(__name__)
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RELEASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_CLIENT = re.compile(r"[a-f0-9]{32}\Z")
_TOKEN = re.compile(r"[a-f0-9]{48}\Z")


def _date(value):
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise ValueError("Expected a UTC publication timestamp ending in Z.")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def publication_metadata(release_id, published_at):
    """Release tooling must stamp the actual public timestamp, never build time."""
    if not isinstance(release_id, str) or not _RELEASE.fullmatch(release_id):
        raise ValueError("Invalid release ID.")
    expiry = _date(published_at) + timedelta(seconds=WINDOW_SECONDS)
    return {"releaseId": release_id, "publishedAt": published_at,
            "expiresAt": expiry.strftime("%Y-%m-%dT%H:%M:%SZ")}


def _ordinary(info, directory=False):
    return ((stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400
            and (directory or info.st_nlink == 1))


def _lock(handle, unlock=False):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK if unlock else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN if unlock else fcntl.LOCK_EX | fcntl.LOCK_NB)


class ReleaseAnnouncement:
    def __init__(self, app_root, *, state_root=None, content_path=None, clock=time.time,
                 language=None, opener=None):
        app_root = Path(app_root).absolute()
        self.root = Path(state_root or app_root / "runtime/release-announcement").absolute()
        self.clock = clock
        self.locale = language if language is not None else display_language()
        if self.locale not in ("ko", "ja"):
            self.locale = "en"
        self.opener = opener or webbrowser.open_new_tab
        self._mutex = threading.RLock()
        self._issued = set()
        self._data = {}
        self._start = self._expiry = 0.0
        try:
            path = Path(content_path or app_root / "KFPS.UI/content/release-announcement.json")
            with path.open("rb") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise ValueError("Oversized release notice.")
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get("schema") != 1:
                raise ValueError("Invalid release notice.")
            expected = publication_metadata(data.get("releaseId"), data.get("publishedAt"))
            if data.get("expiresAt") != expected["expiresAt"]:
                raise ValueError("Release expiry must be exactly seven days after publication.")
            for locale in ("en", "ko", "ja"):
                content = data["locales"][locale]
                for key in ("title", "closeLabel", "supportLabel", "closing"):
                    if not isinstance(content[key], str) or not 1 <= len(content[key]) <= 500:
                        raise ValueError("Invalid release text.")
                if not isinstance(content["blocks"], list) or not 1 <= len(content["blocks"]) <= 30:
                    raise ValueError("Invalid release paragraphs.")
                for block in content["blocks"]:
                    if (not isinstance(block, dict) or set(block) - {"heading", "text"}
                            or not isinstance(block.get("text"), str) or not 1 <= len(block["text"]) <= 8000
                            or not isinstance(block.get("heading", ""), str)):
                        raise ValueError("Invalid release paragraph.")
            self._data = data
            self._start = _date(data["publishedAt"]).timestamp()
            self._expiry = _date(data["expiresAt"]).timestamp()
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            # Unpublished sources and an unreadable optional notice never block startup.
            pass
        key = hashlib.sha256(str(self._data.get("releaseId", "unpublished")).encode()).hexdigest()
        self.path = self.root / (key + ".json")
        self.lock_path = self.root / (key + ".lock")

    def _active(self):
        return bool(self._data) and self._start <= self.clock() < self._expiry

    def _status(self, seen=False, healthy=True):
        return {"releaseId": self._data.get("releaseId"),
                "publishedAt": self._data.get("publishedAt"), "expiresAt": self._data.get("expiresAt"),
                "locale": self.locale, "acknowledged": bool(seen),
                "eligible": bool(healthy and not seen and self._active())}

    def _check(self):
        for directory in reversed((self.root, *self.root.parents)):
            try:
                info = directory.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info, True):
                raise OSError("Release notice storage is redirected.")
        for path in (self.path, self.lock_path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not _ordinary(info):
                raise OSError("Release notice storage is not an ordinary private file.")

    @contextmanager
    def _locked(self):
        with self._mutex:
            self._check()
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "r+b") as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > 1:
                    raise OSError("Invalid release notice lock.")
                deadline = time.monotonic() + 2
                while True:
                    try:
                        _lock(handle)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK) or time.monotonic() >= deadline:
                            raise
                        time.sleep(.01)
                try:
                    if os.fstat(handle.fileno()).st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    self._check()
                    yield
                finally:
                    _lock(handle, True)

    def _read(self):
        try:
            with self.path.open("rb") as handle:
                info = os.fstat(handle.fileno())
                if not _ordinary(info) or info.st_size > 2048:
                    raise ValueError("Invalid release notice state.")
                raw = handle.read(2049)
        except FileNotFoundError:
            return {"version": 1, "releaseId": self._data["releaseId"], "seen": False,
                    "token": "", "client": "", "until": 0}
        value = json.loads(raw)
        if (not isinstance(value, dict) or set(value) != {"version", "releaseId", "seen", "token", "client", "until"}
                or value["version"] != 1 or value["releaseId"] != self._data["releaseId"]
                or type(value["seen"]) is not bool or not isinstance(value["token"], str)
                or (value["token"] and not _TOKEN.fullmatch(value["token"]))
                or not isinstance(value["client"], str) or (value["client"] and not _CLIENT.fullmatch(value["client"]))
                or type(value["until"]) not in (float, int) or not math.isfinite(value["until"])):
            raise ValueError("Invalid release notice state.")
        return value

    def _write(self, value):
        self._check()
        descriptor, name = tempfile.mkstemp(prefix=".notice-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            self._check()
            os.replace(name, self.path)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass

    def read_status(self):
        """Diagnostics-safe snapshot: no text, client IDs, tokens, paths or writes."""
        if not self._data:
            return self._status()
        try:
            self._check()
            return self._status(self._read()["seen"])
        except (OSError, ValueError, TypeError, RecursionError):
            return self._status(healthy=False)

    def dispatch(self, body):
        if not isinstance(body, dict):
            raise ValueError("Expected a release notice action.")
        action = body.get("action")
        keys = {"status": {"action"}, "claim": {"action", "client"},
                "presented": {"action", "token"}, "release": {"action", "token"},
                "support": {"action", "token"}}
        if not isinstance(action, str) or action not in keys or set(body) != keys[action]:
            raise ValueError("Invalid release notice action.")
        field, pattern = ("client", _CLIENT) if action == "claim" else ("token", _TOKEN)
        if action != "status" and (not isinstance(body[field], str) or not pattern.fullmatch(body[field])):
            raise ValueError("Invalid release notice identity.")
        if action == "status" or not self._active():
            return self.read_status()
        open_support = False
        try:
            with self._locked():
                if not self._active():
                    return self.read_status()
                value = self._read()
                result = self._status(value["seen"])
                if action == "claim" and not value["seen"]:
                    if value["until"] > self.clock() and value["client"] != body["client"]:
                        return {**result, "retryAfterMs": int((value["until"] - self.clock()) * 1000) + 50}
                    if value["until"] <= self.clock():
                        value.update(token=secrets.token_hex(24), client=body["client"],
                                     until=min(self.clock() + LEASE_SECONDS, self._expiry))
                        self._write(value)
                    self._issued = {value["token"]}
                    return {**result, "token": value["token"], "content": self._data["locales"][self.locale],
                            "remainingMs": max(0, int((self._expiry - self.clock()) * 1000)),
                            "leaseMs": max(0, int((value["until"] - self.clock()) * 1000))}
                token = body.get("token")
                matching = token in self._issued and secrets.compare_digest(value["token"], token)
                if action == "presented" and matching and not value["seen"] and value["until"] > self.clock():
                    value["seen"] = True
                    self._write(value)
                elif action == "release" and matching and not value["seen"]:
                    value.update(token="", client="", until=0)
                    self._write(value)
                    self._issued.discard(token)
                elif action == "support" and matching and value["seen"]:
                    open_support = True
                result = self._status(value["seen"])
        except (OSError, ValueError, TypeError, RecursionError):
            _LOG.warning("Optional release notice storage unavailable; notice suppressed.")
            return self._status(healthy=False)
        if open_support:
            try:
                self.opener(SUPPORT_URL)
            except Exception:
                _LOG.warning("Could not open the explicit support link.")
        return result

    def close(self):
        for token in tuple(self._issued):
            self.dispatch({"action": "release", "token": token})
        self._issued.clear()
