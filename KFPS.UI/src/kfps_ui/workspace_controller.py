"""Connect existing launch boundaries to retained native workspace owners."""
import importlib.util
import hashlib
import json
import os
import sys
import threading
import uuid
from urllib.parse import urlsplit
from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtNetwork import QLocalServer
from shiboken6 import isValid
from .editor_service import _studio_module_path
from .editor_launch import editor_is_open
from . import workspace_paths
from .workspace_diagnostics import operation, record


class WorkspaceController(QObject):
    studioPrepared = Signal(object)
    sourceReturned = Signal()
    sessionChanged = Signal()
    studioExplicitOpen = Signal()

    def __init__(self, shell, paths, service, runtime):
        super().__init__(shell)
        self.shell, self.paths, self.service, self.runtime = shell, paths, service, runtime
        self.log = getattr(service, "log", None)
        diagnostic = operation()
        record(self.log, "workspace.connection", "started", op=diagnostic)
        self.closed = False
        self._session = None
        self._session_opening = False
        self._pending = []
        self._sockets = set()
        self._bridge = None
        self._studio_native_owner = None
        self._bridge_lock = threading.Lock()
        self._backend_lock = threading.Lock()
        self._studio_backends = {}
        self._backend_shutdown = False
        from kfps_editor.ipc import instance_name
        from kfps_editor.instance_lock import EditorInstanceLock
        try:
            directory = workspace_paths.workspace_connection_dir(paths.app_root)
        except RuntimeError:
            record(self.log, "workspace.connection", "blocked", op=diagnostic, stage="ipc")
            raise
        directory.mkdir(parents=True, exist_ok=True)
        self._studio_marker = directory / "studio-session.json"
        self._studio_session = None
        self.lock = getattr(runtime, "workspace_lock", None)
        self._owns_lock = self.lock is None
        if self.lock is not None:
            if self.lock.runtime.resolve() != directory.resolve() or not self.lock.isLocked():
                raise RuntimeError("The workspace startup lease is not owned by this installation.")
        else:
            self.lock = EditorInstanceLock(directory)
        if not self.lock.isLocked() and not self.lock.tryLock(0):
            record(self.log, "workspace.connection", "blocked", op=diagnostic, stage="lock")
            raise RuntimeError("A workspace for this KFPS installation is already open.")
        self.ipc = QLocalServer(self)
        self.ipc.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        name = instance_name(paths.app_root, directory)
        QLocalServer.removeServer(name)
        if not self.ipc.listen(name):
            if self._owns_lock:
                self.lock.unlock()
            record(self.log, "workspace.connection", "failed", op=diagnostic, stage="ipc")
            raise RuntimeError("Could not open the workspace connection.")
        self.ipc.newConnection.connect(self._accept_source)
        self.sourceReturned.connect(lambda: self.shell.show_surface("Studio", background=True))
        service.workspace_editor = self.open_editor
        service.workspace_studio = self.prepare_studio
        shell.reserve_surface("Editor")
        shell.reserve_surface("Studio")
        shell.surfaceRequested.connect(self._requested)
        self.studioPrepared.connect(self._install_studio)
        self.studioExplicitOpen.connect(lambda: self.session.explicit_open("Studio") if self.session else None)
        record(self.log, "workspace.connection", "ready", op=diagnostic)

    def configure_session(self, settings, app_controller):
        """Call once after construction; persistence is independent of SettingsService."""
        if self.session is None and not self.closed:
            from .workspace_session import WorkspaceSession
            self._session = WorkspaceSession(self, app_controller)
            self.session.changed.connect(self.sessionChanged)
            self.sessionChanged.emit()
        return self

    @Property(QObject, notify=sessionChanged)
    def session(self):
        return self._session

    @Property(bool, notify=sessionChanged)
    def reopenPreviousSession(self):
        return bool(self.session and self.session.enabled)

    @Property(bool, notify=sessionChanged)
    def sessionRestoreAvailable(self):
        return bool(self.session and self.session.previous["surfaces"])

    @Property(str, notify=sessionChanged)
    def sessionStatus(self):
        return self.session.status if self.session else "Session reopening is not configured."

    @Slot(bool)
    def setReopenPreviousSession(self, enabled):
        if self.session and not self.closed:
            self.session.set_enabled(enabled)

    @Slot(result=bool)
    def reopenLastSession(self):
        return bool(self.session and self.session.reopen())

    @Slot(str)
    def discardSessionRestore(self, name):
        if self.session:
            self.session.explicit_open(name)

    def _accept_source(self):
        while self.ipc.hasPendingConnections():
            socket = self.ipc.nextPendingConnection()
            self._sockets.add(socket)
            buffer = bytearray()
            def read(socket=socket, buffer=buffer):
                buffer.extend(bytes(socket.readAll()))
                if len(buffer) > 8192:
                    record(self.log, "handoff.source", "blocked", stage="ipc")
                    socket.abort();return
                if b"\n" not in buffer:return
                try:
                    self._open_source(json.loads(bytes(buffer).split(b"\n",1)[0]))
                    socket.write(b"ok\n")
                except (OSError, ValueError, RuntimeError, TypeError) as exc:
                    record(self.log, "handoff.source", "failed", stage="ipc", error=exc)
                    socket.write(b"error\n")
                socket.flush();socket.disconnectFromServer()
            def finished(socket=socket):
                self._sockets.discard(socket);socket.deleteLater()
            socket.readyRead.connect(read);socket.disconnected.connect(finished)
            QTimer.singleShot(10000,socket,socket.abort)
            if socket.bytesAvailable():read()

    def _open_source(self, payload):
        diagnostic = operation()
        record(self.log, "handoff.source", "started", op=diagnostic)
        try:
            result = self._open_source_request(payload)
        except Exception as exc:
            record(self.log, "handoff.source", "failed", op=diagnostic, error=exc)
            raise
        record(self.log, "handoff.source", "ready", op=diagnostic)
        return result

    def _open_source_request(self, payload):
        from kfps_editor.ipc import validate_request
        from kfps_editor.host import EditorDesktop
        request = validate_request(payload)
        if self.closed or self.shell._closing or request.get("json") or request["mode"] != "activate":
            raise ValueError("Workspace cannot open this source request.")
        path = _studio_module_path(self.paths.app_root, "source_editor.py")
        spec = importlib.util.spec_from_file_location("_kfps_workspace_source", path)
        helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        candidate = self.paths.app_root / request["project"]
        runtime = candidate.parent.parent
        context = helper.editor_context(runtime, private=True)
        if not context or candidate.name != context["projectId"] or candidate.parent.name != "projects":
            raise ValueError("Invalid Studio source project.")
        studio = self.shell.owners.get("Studio")
        if studio is None or not context["returnUrl"].startswith(studio.page.url().toString().split('#')[0] + "api/source-editor/"):
            raise ValueError("This source belongs to another Studio session.")
        name = "Source " + context["jobId"][:8]
        if name in self.shell.owners:
            self.shell.show_surface(name, background=True);return
        if sum(key.startswith("Source ") for key in self.shell.owners) >= 4:
            raise ValueError("Close an existing source editor first.")
        host = EditorDesktop(self.paths.app_root, runtime, baseline=self.runtime.baseline,
                             update_guard=self.runtime.borrow_guard())
        host.workspace_present = lambda **kwargs: self.shell.show_surface(name, **kwargs)
        host.workspace_source_name = context["name"]
        try:
            if not host.start({"mode":"activate","project":context["projectId"]}):
                raise RuntimeError("This source editor is already open.")
            host.server.workspace_source_returned = self.sourceReturned.emit
            host.server.workspace_studio_open = self.prepare_studio
            self.shell.add_surface(name, host, host)
            self.shell.show_surface(name, background=True)
        except Exception:
            host.shutdown();host.deleteLater();raise

    def _requested(self, name):
        value = self.session.take(name) if self.session else None
        if value is not None and name == "Editor":
            try:
                request = self.session.editor_request(value)
                self._session_opening = True
                project = str(self.session.store.editor_path(request["project"])) if request["project"] else ""
                self.service._launch(project, request["mode"])
            except (OSError, ValueError) as exc:
                self.session.explicit_open(name)
                self.session.message(str(exc))
            finally:
                self._session_opening = False
            return
        if name == "Editor":
            self.service.activate()
        elif name == "Studio":
            self.service.launchLiveryStudio()

    def _write_studio_owner(self, host):
        if not isValid(self) or self.closed or not isValid(self.shell) or self.shell.owners.get("Studio") is not host:
            return
        if not self._marker_directory_valid():
            record(self.log, "handoff.marker", "blocked", stage="persist")
            return
        target = urlsplit(host.page.url().toString())._replace(query="", fragment="").geturl()
        session = hashlib.sha256(target.encode("utf-8")).hexdigest()
        temporary = self._studio_marker.with_suffix("." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump({"format":"kfps-workspace-studio/1", "pid":os.getpid(), "session":session}, stream)
            os.replace(temporary, self._studio_marker)
            self._studio_session = session
        except OSError as exc:
            record(self.log, "handoff.marker", "failed", stage="persist", error=exc)
            self.shell.statusBar().showMessage("Source editing will open separately because the workspace connection could not be saved.", 10000)
        finally:
            try:
                if self._marker_directory_valid():
                    temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _marker_directory_valid(self):
        root = self.paths.app_root.resolve()
        try:
            return (self._studio_marker.parent.resolve() == root / "runtime/workspace"
                    and not any(path.is_symlink() or path.is_junction() for path in
                                (root / "runtime", self._studio_marker.parent, self._studio_marker)))
        except OSError:
            return False

    def _clear_studio_owner(self, host=None):
        if not isValid(self) or not isValid(self.shell) or self._studio_session is None:
            return
        if not self._marker_directory_valid():
            return
        current = self.shell.owners.get("Studio")
        if host is not None and current is not None and current is not host:
            return
        try:
            if self._studio_marker.stat().st_size <= 4096:
                value = json.loads(self._studio_marker.read_text(encoding="utf-8"))
                if value.get("pid") == os.getpid() and value.get("session") == self._studio_session:
                    self._studio_marker.unlink()
        except (OSError, ValueError, AttributeError):
            pass
        self._studio_session = None

    def open_editor(self, request):
        diagnostic = operation()
        record(self.log, "handoff.editor", "started", op=diagnostic)
        try:
            result = self._open_editor(request, diagnostic)
        except Exception as exc:
            record(self.log, "handoff.editor", "failed", op=diagnostic, error=exc)
            raise
        record(self.log, "handoff.editor", "deferred" if result else "fallback", op=diagnostic)
        return result

    def _open_editor(self, request, diagnostic):
        from kfps_editor.launch_preferences import use_chrome
        from kfps_editor.ipc import validate_request
        from kfps_editor.host import EditorDesktop
        request = validate_request(request)
        if self.closed or self.shell._closing:
            raise RuntimeError("The workspace is closing.")
        if self.session and not self._session_opening:
            self.session.explicit_open("Editor")
        host = self.shell.owners.get("Editor")
        if host is None and (use_chrome(self.paths.app_root) or editor_is_open(self.paths)):
            return False
        if host is not None:
            if host._closing or host._close_prompt or host._open_uncertain:
                raise RuntimeError("Finish the current editor operation first.")
            host.activate_request(request)
            self._wait_editor(host, diagnostic)
            return True
        host = EditorDesktop(self.paths.app_root, self.paths.runtime_root / "fabric-editor",
                             baseline=self.runtime.baseline, update_guard=self.runtime.borrow_guard())
        host.workspace_present = lambda **kwargs: self.shell.show_surface("Editor", **kwargs)
        try:
            if not host.start(request):
                host.shutdown();host.deleteLater()
                return False
            host.server.workspace_studio_open = self.prepare_studio
            self.shell.install_surface("Editor", host, host)
            self.shell.show_surface("Editor", background=True)
        except Exception:
            host.shutdown();host.deleteLater()
            raise
        self._wait_editor(host, diagnostic)
        return True

    def _wait_editor(self, host, diagnostic=None):
        timer = QTimer(self)
        timer.setInterval(100)
        def ready():
            gone = not isValid(host) or self.shell.owners.get("Editor") is not host
            if self.closed or gone or host._ready or host._failed:
                timer.stop();timer.deleteLater()
                if not self.closed:
                    ok = not gone and host._ready
                    record(self.log, "handoff.editor", "ready" if ok else "failed", op=diagnostic, stage="load")
                    message = "Editor tab closed." if gone else "Editor opened in the workspace." if ok else host.error_label.text()
                    self.service._finish_launch(ok, "workspace", message)
        timer.timeout.connect(ready);timer.start()

    def prepare_studio(self, request, cancelled=None):
        """Called only by existing service/server worker threads, never the GUI."""
        diagnostic = operation()
        record(self.log, "handoff.studio", "started", op=diagnostic)
        try:
            result = self._prepare_studio(request, cancelled, diagnostic)
        except Exception as exc:
            outcome = "timeout" if isinstance(exc, TimeoutError) else (
                "cancelled" if self.closed or (cancelled is not None and cancelled.is_set()) else "failed")
            record(self.log, "handoff.studio", outcome, op=diagnostic, error=exc)
            raise
        record(self.log, "handoff.studio", "ready", op=diagnostic)
        return result

    def _prepare_studio(self, request, cancelled, diagnostic):
        if any(request.get(kind) is not None for kind in ("vinyl", "layout", "project")):
            self.studioExplicitOpen.emit()
        path = _studio_module_path(self.paths.app_root, "host_bridge.py")
        with self._bridge_lock:
            if self._bridge is None:
                spec = importlib.util.spec_from_file_location("_kfps_workspace_studio_bridge", path)
                bridge = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bridge)
                self._bridge = bridge
        bridge = self._bridge
        root = self.paths.app_root
        sys.path.insert(0, str(path.parent)) if str(path.parent) not in sys.path else None
        from studio_window import use_chrome
        if use_chrome(root):
            record(self.log, "handoff.studio", "fallback", op=diagnostic, mode="chrome")
            return bridge.launch_from_host(root, request, open_window=True, cancelled=cancelled)
        if self.closed:
            raise RuntimeError("The workspace is closing.")
        result = bridge.launch_from_host(root, request, open_window=False, cancelled=cancelled,
                                         native_owner=self._studio_native_owner, backend_ready=self._remember_studio_backend)
        pending = {"result": result, "done": threading.Event(), "error": "", "cancelled": cancelled,
                   "diagnostic": diagnostic}
        self.studioPrepared.emit(pending)
        for _ in range(1200):
            if pending["done"].wait(.1):
                if pending["error"]:raise RuntimeError(pending["error"])
                return result
            if self.closed or (cancelled is not None and cancelled.is_set()):
                pending["error"] = "Studio launch cancelled."
                pending["done"].set()
                raise RuntimeError(pending["error"])
        pending["error"] = "Studio is taking too long to open. Check its workspace tab."
        pending["done"].set()
        raise TimeoutError(pending["error"])

    def _install_studio(self, pending):
        self._pending.append(pending)
        def finish(error=""):
            if not pending["done"].is_set():
                record(self.log, "handoff.studio", "failed" if error else "ready",
                       op=pending.get("diagnostic"), stage="workspace")
            pending["error"] = error;pending["done"].set()
            if pending in self._pending:self._pending.remove(pending)
        cancelled = pending.get("cancelled")
        if self.closed or self.shell._closing or pending["done"].is_set() or (cancelled is not None and cancelled.is_set()):
            finish("The workspace is closing.");return
        try:
            path = _studio_module_path(self.paths.app_root, "host_bridge.py")
            if str(path.parent) not in sys.path:sys.path.insert(0, str(path.parent))
            from studio_host import StudioHost
            from studio_window import validate_window_url
            url = validate_window_url(pending["result"]["url"])
            host = self.shell.owners.get("Studio")
            if host is not None:
                if host.stopped or not host.ready:
                    raise RuntimeError("Studio is not ready. Wait for it to load, or close its tab and try again.")
                current, target = urlsplit(host.page.url().toString()), urlsplit(url)
                if (current.scheme,current.netloc,current.path) != (target.scheme,target.netloc,target.path):
                    raise RuntimeError("Studio is already open with another car. Use its car selector or reopen the workspace.")
                if target.fragment:host.page.setUrl(QUrl(url))
                self.shell.show_surface("Studio", background=True)
                finish();return
            run = self.paths.app_root / "tools/livery-studio/runs/workspace-windows" / uuid.uuid4().hex
            host = StudioHost(url, run, parent=self.shell, hosted=True,
                              offscreen=os.environ.get("QT_QPA_PLATFORM") == "offscreen",
                              diagnostic_policy=self.runtime.graphics.backend)
            self._studio_native_owner = host._native_owner
            self.shell.install_surface("Studio", host.window, host)
            self._write_studio_owner(host)
            host.page.urlChanged.connect(lambda *_: self._write_studio_owner(host))
            host.closed.connect(lambda: self._clear_studio_owner(host))
            host.destroyed.connect(lambda *_: self._clear_studio_owner(host))
            self.shell.show_surface("Studio", background=True)
            host.closeRequested.connect(lambda: self.shell.close_surface("Studio"))
            host.closed.connect(lambda: finish("Studio tab closed.") if not pending["done"].is_set() else None)
            host.failed.connect(lambda message: (self.shell.statusBar().showMessage(message),finish(message)))
            host.readyChanged.connect(lambda ready: finish() if ready and not pending["done"].is_set() else None)
        except Exception as exc:
            finish(str(exc));self.shell.statusBar().showMessage(str(exc))

    def _remember_studio_backend(self, value):
        if (not isinstance(value, dict) or value.get('managed') is not True
                or type(value.get('pid')) is not int or type(value.get('created')) not in (int, float)):
            return
        backend = {key: value.get(key) for key in ('pid', 'created', 'workspace', 'managed', 'url')}
        with self._backend_lock:
            stopping = self._backend_shutdown
            if not stopping:
                self._studio_backends[(backend['pid'], backend['created'])] = backend
        if stopping:
            self._stop_studio_backend(backend)

    def _stop_studio_backend(self, backend):
        diagnostic = operation()
        record(self.log, 'studio.backend', 'started', op=diagnostic, stage='cleanup')
        try:
            result = self._bridge.launcher.stop_workspace_backend(backend, expected_kfps_root=self.paths.app_root)
            outcome = {'stopped': 'completed', 'gone': 'missing', 'not-owned': 'blocked',
                       'in-use': 'blocked', 'shared': 'blocked'}.get(result, 'failed')
            record(self.log, 'studio.backend', outcome, op=diagnostic, stage='cleanup')
            return outcome != 'failed'
        except Exception as exc:
            record(self.log, 'studio.backend', 'failed', op=diagnostic, stage='cleanup', error=exc)
            return False

    def shutdown_studio_backends(self):
        """Run after native documents and launch workers have been drained."""
        with self._backend_lock:
            self._backend_shutdown = True
            backends = list(self._studio_backends.values())
            self._studio_backends.clear()
        completed = True
        for backend in backends:
            if not self._stop_studio_backend(backend):
                completed = False
        return completed

    def close(self):
        if self.closed:
            return
        if self.session:
            self.session.close()
        self.closed = True
        self._clear_studio_owner()
        self.ipc.close()
        for socket in list(self._sockets):socket.abort()
        if self._owns_lock and self.lock.isLocked():self.lock.unlock()
        self.service.workspace_editor = self.service.workspace_studio = None
        for pending in list(self._pending):
            pending["error"] = "Workspace closed.";pending["done"].set()
        self._pending.clear()
        record(self.log, "workspace.connection", "completed", stage="close")
