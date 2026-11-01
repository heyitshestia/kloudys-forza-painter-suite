"""Bounded session references; document content and recovery remain owner-managed."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import uuid
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from shiboken6 import isValid
from .workspace_diagnostics import operation, record, surface


MAX_BYTES = 16384
SURFACES = {"Editor", "Studio"}
PAGES = {"create", "outputs", "editor", "tools", "settings", "help"}


def project_id(value):
    if not isinstance(value, str) or not 0 < len(value) <= 1024:
        raise ValueError("Invalid saved project reference.")
    parts = PurePosixPath(value).parts
    if (not parts or any(p in ("", ".", "..") or p.endswith((".", " ")) for p in value.split("/"))
            or any(c in value for c in '\\:<>"|?*') or value.startswith("/")
            or any(ord(c) < 32 for c in value) or not value.endswith(".fabric-project.json")):
        raise ValueError("Invalid saved project reference.")
    return value


def reference(name, value):
    if name not in SURFACES or not isinstance(value, dict):
        raise ValueError("Invalid session surface.")
    allowed = {"project", "dirty"} if name == "Editor" else {"project", "dirty", "car"}
    if set(value) - allowed or type(value.get("dirty", False)) is not bool:
        raise ValueError("Invalid session reference.")
    result = {"dirty": value.get("dirty", False)}
    if "project" in value and not isinstance(value["project"], str):
        raise ValueError("Invalid saved project reference.")
    if value.get("project"):
        identifier = value["project"]
        if name == "Editor":
            identifier = project_id(identifier)
        elif not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid Studio project reference.")
        result["project"] = identifier
    if name == "Studio":
        car = value.get("car")
        if (not isinstance(car, dict) or set(car) != {"car_id", "model_code"}
                or type(car["car_id"]) is not int or not 0 < car["car_id"] < 2**31
                or not isinstance(car["model_code"], str)
                or not re.fullmatch(r"[A-Za-z0-9_ -]{1,160}", car["model_code"])):
            raise ValueError("Invalid saved car reference.")
        result["car"] = dict(car)
    return result


def validate_manifest(value):
    if (not isinstance(value, dict) or set(value) != {"version", "reopen", "page", "surfaces"}
            or type(value["version"]) is not int or value["version"] != 1
            or type(value["reopen"]) is not bool or not isinstance(value["page"], str) or value["page"] not in PAGES
            or not isinstance(value["surfaces"], dict) or set(value["surfaces"]) - SURFACES):
        raise ValueError("Invalid workspace session.")
    return {"version": 1, "reopen": value["reopen"], "page": value["page"],
            "surfaces": {name: reference(name, item) for name, item in value["surfaces"].items()}}


class SessionStore:
    def __init__(self, app_root, runtime_root=None):
        self.root = Path(app_root).resolve()
        self.runtime = Path(runtime_root or self.root / "runtime").absolute()
        self.path = self.runtime / "workspace/session.json"

    def check_path(self):
        for path in (self.runtime, self.path.parent, self.path):
            if path.is_symlink() or path.is_junction() or (path.is_file() and path.stat().st_nlink != 1):
                raise ValueError("Workspace session storage is redirected.")
        if self.runtime.resolve() != self.runtime or self.path.parent.resolve() != self.runtime / "workspace":
            raise ValueError("Workspace session storage is redirected.")

    def read(self):
        self.check_path()
        try:
            with self.path.open("rb") as stream:
                body = stream.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return {"version": 1, "reopen": False, "page": "create", "surfaces": {}}
        if len(body) > MAX_BYTES:
            raise ValueError("Workspace session is too large.")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("Duplicate session field.")
                result[key] = value
            return result
        try:
            value = json.loads(body, object_pairs_hook=pairs)
        except RecursionError as error:
            raise ValueError("Workspace session is nested too deeply.") from error
        return validate_manifest(value)

    def write(self, value):
        data = json.dumps(validate_manifest(value), ensure_ascii=True, sort_keys=True).encode("utf-8")
        if len(data) > MAX_BYTES:
            raise ValueError("Workspace session is too large.")
        self.check_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(".session-" + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self.check_path()
            os.replace(temporary, self.path)
        finally:
            self.check_path()
            temporary.unlink(missing_ok=True)

    def editor_path(self, identifier):
        identifier = project_id(identifier)
        root = self.runtime / "fabric-editor/projects"
        path = root / identifier
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("The saved Editor project is missing or outside its project folder.")
        for part in (self.runtime, root.parent, root, *path.parents):
            if part == self.runtime.parent:
                break
            if part.is_symlink() or part.is_junction():
                raise ValueError("The saved Editor project folder is redirected.")
        if path.is_symlink() or path.stat().st_nlink != 1:
            raise ValueError("The saved Editor project is redirected.")
        return path


EDITOR_SNAPSHOT = """(() => {
    if (!window.KfpsDesktop?.ready) return null;
    return JSON.stringify({project:editorProjects.association?.target_id || '',
        dirty:isDocumentDirty()});
})()"""

STUDIO_SNAPSHOT = "JSON.stringify(window.kfpsWorkspaceSession?.snapshot() ?? null)"


def studio_navigation_key(url):
    """Keep origin and a digest, never a reusable Studio token or URL."""
    parsed = urlsplit(url.toString())
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.query
            or not re.fullmatch(r"/[A-Za-z0-9_-]{43}/", parsed.path)
            or (parsed.fragment and not re.fullmatch(r"vinyl=[a-f0-9]{32}", parsed.fragment))):
        raise ValueError("Invalid local Studio session page.")
    return (parsed.scheme, parsed.hostname, parsed.port), hashlib.sha256(parsed.path.encode()).hexdigest()


class WorkspaceSession(QObject):
    changed = Signal()

    def __init__(self, controller, app_controller):
        super().__init__(controller)
        self.controller, self.shell, self.app = controller, controller.shell, app_controller
        self.log = getattr(controller, "log", None)
        self._diagnostic_restores = {}
        self.store = SessionStore(controller.paths.app_root, controller.paths.runtime_root)
        self._status = "Session reopening is off. Recovery stays with each editor."
        self.closed = False
        self.blocked = False
        diagnostic = operation()
        try:
            self.previous = self.store.read()
            record(self.log, "session.read", "completed", op=diagnostic)
        except (OSError, ValueError, TypeError) as exc:
            record(self.log, "session.read", "failed", op=diagnostic, error=exc)
            self.previous = {"version": 1, "reopen": False, "page": "create", "surfaces": {}}
            self._status = "The previous session could not be read. Saved projects and recovery were not changed."
            self.blocked = True
        self.enabled = self.previous["reopen"]
        self.current = dict(self.previous["surfaces"])
        self.staged, self.loading, self.inflight, self.nonces = {}, {}, {}, {}
        self.dispatched, self.attempts = set(), {}
        self.navigation, self.transitions = {}, {}
        self.continuing, self.navigating, self.reloading = set(), set(), set()
        self._attached = {}
        self._last_write = None
        self.timer = QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.capture)
        self.shell.surfaceInstalled.connect(self.attach)
        self.shell.surfaceRetired.connect(self.retired)
        self.shell.sessionClosePreparing.connect(self.capture_close)
        self.shell.surfaceSelectionChanged.connect(self.selection_changed)
        self.shell.sessionActivityChanged.connect(self.activity_changed)
        if self.enabled:
            self.reopen()
        for name, owner in self.shell.owners.items():
            self.attach(name, owner)

    @Property(bool, notify=changed)
    def restoreEnabled(self):
        return self.enabled

    @restoreEnabled.setter
    def restoreEnabled(self, value):
        if not self.closed:
            self.set_enabled(value)

    @Property(bool, notify=changed)
    def previousAvailable(self):
        return bool(self.previous["surfaces"])

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Slot(result=bool)
    def restorePrevious(self):
        return self.reopen()

    def message(self, text):
        self._status = text
        self.shell.statusBar().showMessage(text, 12000)
        self.changed.emit()

    def set_enabled(self, enabled):
        previous = self.enabled
        self.enabled = bool(enabled)
        self.blocked = False
        if not self.persist():
            self.enabled = previous
            self.changed.emit()
            return
        if not enabled:
            for name in list(self.staged):
                self.explicit_open(name)
        self.schedule()
        self.message("Previous-session placeholders will reopen on startup." if enabled
                     else "Automatic session reopening is off. Saved recovery is unchanged.")

    def reopen(self):
        if self.closed or self.shell._closing or self.shell._shutdown:
            return False
        for name, value in self.previous["surfaces"].items():
            if name not in self.shell.owners and name not in self.loading:
                self.staged[name] = dict(value)
                self.shell.set_session_placeholder(name, True)
            elif name in self.shell.owners:
                self.staged.pop(name, None)
        self.message("Previous session is ready. Select a tool tab to reopen it; recovery remains separate."
                     if self.staged else "No previous-session tool is available to reopen. Existing tabs were kept.")
        return bool(self.staged)

    def explicit_open(self, name):
        self._finish_restore(name, "cancelled")
        self.staged.pop(name, None)
        self.loading.pop(name, None)
        nonce = self.nonces.pop(name, None)
        self.dispatched.discard(name)
        self.attempts.pop(name, None)
        self.navigation.pop(name, None)
        self.transitions.pop(name, None)
        self.continuing.discard(name)
        self.reloading.discard(name)
        self.inflight.pop(name, None)
        self.shell.set_session_placeholder(name, False)
        owner = self.shell.owners.get(name)
        if nonce and name == "Studio" and owner is not None and callable(getattr(getattr(owner, "page", None), "runJavaScript", None)):
            # The owner may already be committing a car switch. Cancel only the
            # native restore continuation; never stop its committed navigation.
            owner.page.runJavaScript("window.kfpsWorkspaceSession?.cancelRestore(" + json.dumps(nonce) + ");")
        self.schedule()

    def take(self, name):
        value = self.staged.pop(name, None)
        self.shell.set_session_placeholder(name, False)
        if value is not None:
            self._diagnostic_restores[name] = operation()
            record(self.log, "session.restore", "started", op=self._diagnostic_restores[name], surface=surface(name))
            self.loading[name] = value
            self.nonces[name] = uuid.uuid4().hex
            self.attempts[name] = 0
            self.transitions[name] = 0
            nonce = self.nonces[name]
            QTimer.singleShot(120000, self, lambda: self.restore_timeout(name, nonce))
        self.schedule()
        return value

    def _finish_restore(self, name, outcome):
        diagnostic = self._diagnostic_restores.pop(name, None)
        if diagnostic is not None:
            record(self.log, "session.restore", outcome, op=diagnostic, surface=surface(name))

    def restore_timeout(self, name, nonce):
        if self.closed or self.nonces.get(name) != nonce or name not in self.loading:
            return
        self._finish_restore(name, "timeout")
        self.explicit_open(name)
        self.message(name + " session reopening did not finish. Open the saved project or Recovery explicitly.")

    def editor_request(self, value):
        identifier = value.get("project")
        if not identifier or value.get("dirty"):
            self.message("Editor recovery will be checked by the existing editor. No saved project was overwritten.")
            return {"mode": "activate", "project": ""}
        path = self.store.editor_path(identifier)
        recovery = self.store.runtime / "fabric-editor"
        if any(item.is_file() and item.stat().st_mtime_ns > path.stat().st_mtime_ns
               for item in (recovery / "autosave.json", recovery / "autosave.previous.json")):
            self.message("Newer Editor recovery may exist; opening the recovery-aware editor instead of replacing it.")
            return {"mode": "activate", "project": ""}
        return {"mode": "activate", "project": identifier}

    def attach(self, name, owner):
        if (self.closed or name not in SURFACES or self._attached.get(name) is owner
                or not callable(getattr(getattr(owner, "page", None), "runJavaScript", None))):
            return
        self._attached[name] = owner
        self.staged.pop(name, None)
        title_changed = getattr(owner.page, "titleChanged", None)
        if title_changed is not None:
            title_changed.connect(lambda *_: self.owner_activity(name, owner))
        owner.page.loadFinished.connect(lambda ok: self.load_finished(name, owner, ok))
        started = getattr(owner.page, "loadStarted", None)
        if started is not None:
            started.connect(lambda: self.load_started(name, owner))
        if name == "Studio":
            owner.page.urlChanged.connect(lambda url: self.studio_navigated(owner, url))
        self.owner_activity(name, owner, active_only=True)

    def load_started(self, name, owner):
        if not isValid(self) or self.closed or self.shell.owners.get(name) is not owner:
            return
        self.inflight.pop(name, None)
        self.navigating.add(name)
        if name == "Studio" and name in self.dispatched:
            self.reloading.add(name)

    def load_finished(self, name, owner, ok):
        if not isValid(self) or self.closed or self.shell.owners.get(name) is not owner:
            return
        self.navigating.discard(name)
        if name in self.reloading or (not ok and name in self.loading):
            self._finish_restore(name, "failed")
            self.explicit_open(name)
            self.message(name + " session reopening stopped after the page changed. Existing work was kept.")
        if ok:
            self.owner_activity(name, owner, active_only=True)

    def studio_navigated(self, owner, url):
        name = "Studio"
        if (not isValid(self) or self.closed or self.shell.owners.get(name) is not owner
                or name not in self.loading or name not in self.navigation):
            return
        try:
            target = studio_navigation_key(url)
            previous = self.navigation[name]
            if target == previous:
                return
            if target[0] != previous[0] or self.transitions[name] >= 1:
                raise ValueError("Unexpected Studio page transition.")
        except (TypeError, ValueError):
            self._finish_restore(name, "blocked")
            self.explicit_open(name)
            self.message("Studio session reopening stopped because its local page changed unexpectedly.")
            return
        self.inflight.pop(name, None)
        self.transitions[name] += 1
        self.navigation[name] = target
        self.continuing.add(name)
        self.dispatched.discard(name)
        self.reloading.discard(name)

    def owner_activity(self, name, owner, *, active_only=False):
        if (not isValid(self) or self.closed or not isValid(self.shell)
                or self.shell.owners.get(name) is not owner):
            return
        if not active_only or self.shell._selected == name:
            self.capture(name)
        self.schedule()

    def selection_changed(self, previous, selected):
        self.capture(previous)
        self.capture(selected)
        self.schedule()

    def activity_changed(self):
        if self.shell.isVisible() and not self.shell.isMinimized() and not self.shell._closing:
            self.capture()
        self.schedule()

    def capture_close(self):
        self.timer.stop()
        for name in SURFACES:
            self.capture(name)

    def schedule(self):
        name = self.shell._selected
        if (self.closed or self.shell._closing or self.shell._shutdown or name not in SURFACES
                or not self.shell.isVisible() or self.shell.isMinimized()
                or name not in self.shell.owners or (not self.enabled and name not in self.loading)):
            self.timer.stop()
            return
        interval = 2000 if name in self.loading else 30000
        if not self.timer.isActive() or self.timer.interval() != interval:
            self.timer.start(interval)

    def retired(self, name, whole):
        self._finish_restore(name, "cancelled")
        self._attached.pop(name, None)
        self.inflight.pop(name, None)
        self.loading.pop(name, None)
        self.nonces.pop(name, None)
        self.dispatched.discard(name)
        self.attempts.pop(name, None)
        self.navigation.pop(name, None)
        self.transitions.pop(name, None)
        self.continuing.discard(name)
        self.navigating.discard(name)
        self.reloading.discard(name)
        if not whole:
            self.current.pop(name, None)
            self.persist()
        self.schedule()

    def capture(self, name=None):
        if self.closed or self.shell._shutdown:
            return
        if name is None and (not self.shell.isVisible() or self.shell.isMinimized()):
            return
        name = self.shell._selected if name is None else name
        owner = self.shell.owners.get(name)
        if name not in SURFACES or owner is None or not callable(getattr(getattr(owner, "page", None), "runJavaScript", None)):
            return
        if self._attached.get(name) is not owner:
            self.attach(name, owner)
            return
        if name in self.inflight or name in self.navigating:
            return
        if name in self.loading and not self.shell._closing and self.shell._selected == name:
            self.attempts[name] += 1
            if self.attempts[name] > 30:
                self.restore_timeout(name, self.nonces[name])
                return
        marker = object()
        self.inflight[name] = marker
        script = EDITOR_SNAPSHOT if name == "Editor" else STUDIO_SNAPSHOT
        owner.page.runJavaScript(script, lambda value: self.accept(name, owner, marker, value))
        QTimer.singleShot(5000, self, lambda: self.inflight.pop(name, None)
                          if self.inflight.get(name) is marker else None)

    def accept(self, name, owner, marker, value):
        if (not isValid(self) or self.closed or not isValid(self.shell) or self.inflight.get(name) is not marker
                or self.shell.owners.get(name) is not owner):
            return
        self.inflight.pop(name, None)
        try:
            if not isinstance(value, str) or len(value) > MAX_BYTES:
                return
            data = json.loads(value)
            if name == "Studio":
                if not isinstance(data, dict) or data.get("ready") is not True:
                    return
                item = reference(name, data["reference"])
                if name in self.loading:
                    if name in self.continuing and item["car"] != self.loading[name]["car"]:
                        self._finish_restore(name, "blocked")
                        self.explicit_open(name)
                        self.message("Studio opened a different car. The saved project was not applied.")
                        return
                    result = data.get("restore")
                    nonce = self.nonces[name]
                    if isinstance(result, dict) and result.get("requestId") == nonce:
                        state = result.get("state")
                        desired = self.loading[name]
                        if state in {"restored", "recovery"} and (item["car"] != desired["car"]
                                or (state == "restored" and desired.get("project")
                                    and item.get("project") != desired["project"])):
                            self._finish_restore(name, "blocked")
                            self.explicit_open(name)
                            self.message("Studio did not confirm the requested saved reference. Existing work was kept.")
                            return
                        messages = {"restored": "Previous Studio session reopened.",
                            "recovery": "Unsaved Studio work may be available in Recovery. Nothing was restored automatically.",
                            "missing": "The saved Studio project or car is missing. Choose another project or Recovery.",
                            "busy": "Existing Studio work was kept. Open the saved project or Recovery explicitly.",
                            "cancelled": "Studio session reopening was cancelled. Existing work was kept.",
                            "failed": "Studio session reopening failed. Saved projects and recovery are unchanged."}
                        if state in messages:
                            self._finish_restore(name, "completed" if state == "restored" else state)
                            self.loading.pop(name, None)
                            self.nonces.pop(name, None)
                            self.dispatched.discard(name)
                            self.attempts.pop(name, None)
                            self.navigation.pop(name, None)
                            self.transitions.pop(name, None)
                            self.continuing.discard(name)
                            self.message(messages[state])
                            if state not in {"restored", "recovery"}:
                                self.schedule()
                                return
                    elif (name not in self.dispatched and self.shell._selected == name
                          and not self.shell._closing):
                        try:
                            self.navigation[name] = studio_navigation_key(owner.page.url())
                        except (TypeError, ValueError):
                            self._finish_restore(name, "blocked")
                            self.explicit_open(name)
                            self.message("Studio session reopening requires its original local page.")
                            return
                        self.dispatched.add(name)
                        self.continuing.discard(name)
                        owner.page.runJavaScript("window.kfpsWorkspaceSession?.restore("
                            + json.dumps(self.loading[name]) + "," + json.dumps(nonce) + ");")
                data = item
            item = reference(name, data)
            if name not in self.loading or name == "Editor":
                if name == "Editor":
                    self._finish_restore(name, "completed")
                self.current[name] = item
                self.loading.pop(name, None)
                self.nonces.pop(name, None)
                self.attempts.pop(name, None)
                self.persist()
            self.schedule()
        except (ValueError, TypeError, KeyError) as exc:
            record(self.log, "session.snapshot", "failed", surface=surface(name), error=exc)

    def persist(self):
        if self.blocked:
            return False
        page = self.app.currentPage if self.app.currentPage in PAGES else "create"
        value = {"version": 1, "reopen": self.enabled, "page": page, "surfaces": self.current}
        if value == self._last_write:
            return True
        diagnostic = operation()
        try:
            self.store.write(value)
            self._last_write = json.loads(json.dumps(value))
            record(self.log, "session.persist", "completed", op=diagnostic, owner_count=len(self.current))
            return True
        except (OSError, ValueError) as exc:
            record(self.log, "session.persist", "failed", op=diagnostic, error=exc)
            self.message("Session references could not be saved. Your projects and recovery are unchanged.")
            return False

    def close(self):
        if self.closed:
            return
        self.persist()
        for name in list(self._diagnostic_restores):
            self._finish_restore(name, "cancelled")
        self.closed = True
        self.timer.stop()
        self.inflight.clear()
        self.loading.clear()
        self.nonces.clear()
        self.dispatched.clear()
        self.attempts.clear()
        self.navigation.clear()
        self.transitions.clear()
        self.continuing.clear()
        self.navigating.clear()
        self.reloading.clear()
