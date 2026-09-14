from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QFile, QIODevice, QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from shiboken6 import delete, isValid
from .localization import EditorTranslator, editor_system_language
from .ipc import forward_request, instance_name, validate_request
from .update_guard import acquire_update_guard, updater_state_root
from .instance_lock import EditorInstanceLock
from .activation import present
from .bootstrap_log import record_startup


def load_editor_server(app_root: Path):
    from .manifest import native_source
    path = native_source("server", app_root)
    spec = importlib.util.spec_from_file_location("kfps_desktop_local_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start_local_server(module, runtime: Path, *, paths):
    marker = runtime / "desktop-port.json"
    try:
        port = json.loads(marker.read_text(encoding="utf-8")).get("port")
        if type(port) is not int or not 1024 <= port <= 65535:
            port = 0
    except (OSError, ValueError, AttributeError):
        port = 0
    try:
        server = module.EditorServer(("127.0.0.1", port), module.Handler, paths=paths)
    except OSError:
        if port == 0:
            raise
        server = module.EditorServer(("127.0.0.1", 0), module.Handler, paths=paths)
    try:
        module._write_json_atomic(marker, {"port": server.server_address[1]})
    except Exception:
        server.server_close()
        raise
    return server


class EditorPage(QWebEnginePage):
    def __init__(self, profile, origin: QUrl, parent=None):
        super().__init__(profile, parent)
        self.origin = origin

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        local = (url.scheme(), url.host(), url.port()) == (self.origin.scheme(), self.origin.host(), self.origin.port())
        if local and url.path() == "/tools/fabric-editor/index.html":
            return True
        if url.toString() == "about:blank":
            return True
        if is_main_frame and navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)
        return False

    def createWindow(self, window_type):
        return None

    def javaScriptConsoleMessage(self, level, message, line, source):
        severity = {QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "console-error",
                    QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "console-warning"}.get(level)
        host = self.parent()
        if severity and getattr(host, "server", None):
            # Console text can contain filenames or artwork metadata. Keep error
            # class and a known script/line, never arbitrary messages or URLs.
            from .diagnostics import ASSETS
            path = QUrl(source).path().removeprefix("/tools/fabric-editor/")
            error = next((name for name in ("TypeError", "RangeError", "ReferenceError", "SyntaxError", "SecurityError", "QuotaExceededError") if name in message[:200]), "unknown")
            host.server.diagnostics().record(severity, line=int(line), source=path if path in ASSETS else "unknown", error=error)


class EditorBridge(QObject):
    result = Signal(str, str)
    operation_progress = Signal(str, str)

    @Slot(str, str)
    def completed(self, request_id: str, payload: str):
        if len(request_id) <= 64 and len(payload) <= 16384:
            self.result.emit(request_id, payload)

    @Slot(str, str)
    def progress(self, request_id: str, phase: str):
        if len(request_id) <= 64 and phase in {"working", "user-wait"}:
            self.operation_progress.emit(request_id, phase)


class EditorDesktop(QMainWindow):
    def __init__(self, app_root: Path, runtime: Path, *, background=False, baseline=None, update_guard=None, export_root=None):
        super().__init__()
        self._background = bool(background)
        if self._background:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnBottomHint, True)
        self.app_root = app_root.resolve()
        self.runtime = runtime.resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.system_language = editor_system_language()
        self.translator = EditorTranslator(self.app_root, self.runtime, self.system_language)
        self.instance = QLocalServer(self)
        self.instance.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.instance.newConnection.connect(self._accept_connection)
        self.lock = EditorInstanceLock(self.runtime)
        self._started_at = time.time()
        self.module = None
        self._server_paths = None
        self._export_root = export_root
        self.server = None
        self.server_thread = None
        self.profile = None
        self.page = None
        self.view = None
        self._sockets = set()
        self._commands = {}
        self._queued_requests = []
        self._ready = False
        self._closing = False
        self._page_epoch = 0
        self._close_epoch = 0
        self._close_request_id = None
        self._close_phase = None
        self._close_prompt = False
        self._open_request_id = None
        self._open_phase = None
        self._open_probing = False
        self._open_uncertain = False
        self.open_timer = QTimer(self)
        self.open_timer.setSingleShot(True)
        self.open_timer.setInterval(60000)
        self.open_timer.timeout.connect(self._open_deadline)
        self._allow_close = False
        self._stopped = False
        self._failed = False
        self._update_guard = update_guard
        self._baseline = baseline
        self._updates = None
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.setInterval(15000)
        self.close_timer.timeout.connect(self._close_timed_out)
        self.setWindowTitle(self.translator.tr("KFPS Vinyl Editor"))
        self.setWindowIcon(QIcon(str(self.app_root / "assets" / "kfps-logo.ico")))
        self.resize(1440, 900)
        self.setMinimumSize(900, 640)
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self.error_panel = QWidget()
        layout = QVBoxLayout(self.error_panel)
        self.error_label = QLabel()
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        retry = QPushButton(self.translator.tr("Reopen Editor"))
        retry.clicked.connect(self.reload_editor)
        layout.addWidget(retry)
        layout.addStretch()
        self.stack.addWidget(self.error_panel)
        self.ready_timer = QTimer(self)
        self.ready_timer.setInterval(250)
        self.ready_timer.timeout.connect(self._check_ready)
        self._checking_ready = False
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.setInterval(60000)
        self.startup_timer.timeout.connect(lambda: self._show_failure(
            "The editor could not finish starting. Reopen Editor to retry without reopening the selected project. Saved projects and recovery files are unchanged."))
        self.diagnostic_timer = QTimer(self)
        self.diagnostic_timer.setInterval(2000)
        self.diagnostic_timer.timeout.connect(self._diagnostic_tick)
        self._last_diagnostic_tick = time.monotonic()
        self._heartbeat_stale = False

    def _publish_update_status(self):
        if self.server is not None and self._updates is not None:
            self.server.update_status = self._updates.snapshot()

    def start(self, request: dict) -> bool:
        request = validate_request(request)
        if not self.lock.tryLock(1500):
            return False
        if os.name == "nt" and self._update_guard is None:
            state = updater_state_root(self.app_root) if self.runtime == self.app_root / "runtime" / "fabric-editor" else self.runtime / "update-state"
            self._update_guard = acquire_update_guard(state)
        name = instance_name(self.app_root, self.runtime)
        QLocalServer.removeServer(name)
        if not self.instance.listen(name):
            raise RuntimeError(f"Could not start the editor launcher connection: {self.instance.errorString()}")
        self.module = load_editor_server(self.app_root)
        self._server_paths = self.module.ServerPaths.for_runtime(self.app_root, self.runtime, exports=self._export_root)
        self.server = start_local_server(self.module, self.runtime, paths=self._server_paths)
        from tools.kfps_update_status import VersionService
        self._updates = VersionService(self.app_root / "VERSION", parent=self, blink=False)
        self._updates.changed.connect(self._publish_update_status)
        self._publish_update_status()
        from .baseline import engine_identity
        self.server.diagnostics().set_runtime_identity(self._baseline or {"status": "development", **engine_identity()})
        self.server.diagnostics().record("native-start", source="native")
        self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, name="kfps-editor-local", daemon=True)
        self.server_thread.start()
        port = self.server.server_address[1]
        self.module._write_server_marker(port, self.server.editor_session_token, paths=self._server_paths)
        self._write_state("starting")
        query = (f"?project={quote(request['project'], safe='')}" if request["project"]
                 else "?browse=json" if request["mode"] == "json"
                 else f"?mode={request['mode']}" if request["mode"] in {"new", "tutorial"} else "")
        self.url = QUrl(f"http://127.0.0.1:{port}/tools/fabric-editor/index.html#session={quote(self.server.editor_session_token, safe='')}")
        startup_url = QUrl(self.url)
        startup_url.setQuery(query.lstrip("?"))
        self.profile = QWebEngineProfile("KFPS-Editor", self)
        self.profile.setPersistentStoragePath(str(self.runtime / "web-profile"))
        self.profile.setCachePath(str(self.runtime / "web-cache"))
        # Keep durable user storage, but never reuse executable assets from an
        # earlier process/update. Resources can still be cached within a session.
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
        self.profile.downloadRequested.connect(self._download)
        self.page = EditorPage(self.profile, self.url, self)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.bridge = EditorBridge(self)
        self.bridge.result.connect(self._command_result)
        self.bridge.operation_progress.connect(self._command_progress)
        channel = QWebChannel(self.page)
        channel.registerObject("editor", self.bridge)
        self.page.setWebChannel(channel)
        source = QFile(":/qtwebchannel/qwebchannel.js")
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise RuntimeError("The bundled Qt WebChannel runtime is missing.")
        javascript = bytes(source.readAll()).decode("utf-8")
        source.close()
        script = QWebEngineScript()
        script.setName("KFPS editor desktop bridge")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode("window.KfpsEditorSystemLanguage = " + json.dumps(self.system_language) + ";\n" + javascript + "\nnew QWebChannel(qt.webChannelTransport, channel => { window.KfpsDesktopBridge = channel.objects.editor; });")
        self.page.scripts().insert(script)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.stack.addWidget(self.view)
        self.stack.setCurrentWidget(self.view)
        self.page.loadFinished.connect(self._loaded)
        self.page.loadStarted.connect(self._page_load_started)
        self.page.loadingChanged.connect(self._loading_changed)
        self.page.renderProcessTerminated.connect(self._renderer_stopped)
        self.page.titleChanged.connect(lambda title: self.setWindowTitle(title or self.translator.tr("KFPS Vinyl Editor")))
        if request["mode"] == "tutorial":
            self._queued_requests.append({"mode": "tutorial", "project": ""})
        self.startup_timer.start()
        self.page.load(startup_url)
        self.diagnostic_timer.start()
        return True

    def _diagnostic_tick(self):
        if self._stopped or not self.server:
            return
        now = time.monotonic()
        diagnostics = self.server.diagnostics()
        visible = self.isVisible() and not self.isMinimized()
        diagnostics.native_tick(ready=self._ready, visible=visible, focused=self.isActiveWindow(),
                                minimized=self.isMinimized(), uiLag=max(0, (now - self._last_diagnostic_tick) * 1000 - 2000),
                                rendererPid=int(self.page.renderProcessPid()) if self.page else 0)
        self._last_diagnostic_tick = now
        received = diagnostics.snapshot().get("page_received", 0)
        stale = self._ready and visible and (not received or time.time() - received > 10)
        if stale and not self._heartbeat_stale:
            diagnostics.record("heartbeat-stale", source="native")
        self._heartbeat_stale = stale

    def _write_state(self, state, error=""):
        if self.module:
            self.module._write_json_atomic(self.runtime / "desktop.json", {
                "service": "kfps-editor-desktop", "pid": os.getpid(), "root": str(self.app_root),
                "instance": instance_name(self.app_root, self.runtime), "state": state, "error": error[:2000],
                "started_at": self._started_at, "updated_at": time.time(),
            })
            record_startup(self.runtime, "instance-state", state=state)

    def present_window(self, *, background=False):
        focused = present(self, background=background)
        record_startup(self.runtime, "window-presented", focused=focused, background=background)

    def _accept_connection(self):
        while self.instance.hasPendingConnections():
            socket = self.instance.nextPendingConnection()
            self._sockets.add(socket)
            buffer = bytearray()

            def read(socket=socket, buffer=buffer):
                buffer.extend(bytes(socket.readAll()))
                if len(buffer) > 8192:
                    socket.abort()
                    return
                if b"\n" not in buffer:
                    return
                try:
                    request = validate_request(json.loads(bytes(buffer).split(b"\n", 1)[0]))
                    if self._closing or self._close_prompt or self._open_uncertain or len(self._queued_requests) >= 8:
                        self.present_window(background=request.get("background", False))
                        raise ValueError("Editor is busy")
                    self.activate_request(request)
                    socket.write(b"ok\n")
                    socket.flush()
                except (ValueError, TypeError):
                    socket.write(b"error\n")
                    socket.flush()
                socket.disconnectFromServer()

            def finished(socket=socket):
                self._sockets.discard(socket)
                socket.deleteLater()

            socket.readyRead.connect(read)
            socket.disconnected.connect(finished)
            QTimer.singleShot(3000, socket, socket.abort)
            if socket.bytesAvailable():
                read()

    def activate_request(self, request):
        self.present_window(background=request.get("background", False))
        if self._failed:
            self._failed = False
            self._write_state("starting")
            # Recreating Chromium's page can take longer than the IPC ACK budget.
            QTimer.singleShot(0, self.reload_editor)
        if not request["project"] and request["mode"] == "activate":
            return
        self._queued_requests.append(request)
        self._dispatch_open()

    def _loaded(self, ok):
        if not ok:
            return
        self._checking_ready = False
        self.ready_timer.start()

    def _page_load_started(self):
        if self._stopped:
            return
        self._invalidate_page_commands()
        self._ready = False
        self._failed = False
        self.ready_timer.stop()
        self.startup_timer.start()
        try:
            self._write_state("starting")
        except OSError as exc:
            self._show_failure(str(exc))

    def _loading_changed(self, info):
        # Reopen cancels an older navigation. A cancellation is not a page failure.
        if not self._stopped and info.status() == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            self._show_failure("The editor page could not be loaded. Your saved projects and recovery files have not been removed.")

    def _check_ready(self):
        if self._checking_ready or not self.page:
            return
        self._checking_ready = True
        epoch = self._page_epoch
        def checked(state):
            if epoch != self._page_epoch or self._stopped:
                return
            self._checking_ready = False
            if self._stopped or self._failed:
                return
            try:
                state = json.loads(state)
            except (ValueError, TypeError):
                return
            if not isinstance(state, dict):
                return
            if state.get("error"):
                self._show_failure(str(state["error"]))
                return
            if not state.get("ready"):
                return
            self.ready_timer.stop()
            self.startup_timer.stop()
            try:
                self._write_state("ready")
            except OSError as exc:
                self._show_failure(str(exc))
                return
            self._ready = True
            if self.isActiveWindow() and self.view:
                self.view.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            self.server.diagnostics().record("native-ready", source="native")
            self._dispatch_open()
        self.page.runJavaScript("JSON.stringify({ready: Boolean(window.KfpsDesktop?.ready && window.KfpsDesktopBridge), error: window.KfpsDesktop?.error || ''})", checked)

    def _dispatch_open(self):
        if not self._ready or self._commands or not self._queued_requests or self._closing or self._close_prompt:
            return
        request = self._queued_requests.pop(0)
        self._open_phase = "working"
        self._open_uncertain = False
        self._open_probing = False
        self.open_timer.start(60000)
        self._open_request_id = self.command("open", request, self._open_result)

    def _open_result(self, result):
        self.open_timer.stop()
        self._open_request_id = None
        self._open_phase = None
        self._open_probing = self._open_uncertain = False
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        if result.get("ok") is not True or not (value.get("ok") is True or value.get("cancelled") is True):
            message = next((text for text in (result.get("error"), value.get("error")) if isinstance(text, str) and text), "Invalid editor response")
            self._close_message("warning", self.translator.tr("Could not open in editor"), self.translator.message(message))
        self._dispatch_open()

    def _open_deadline(self):
        if not self._open_request_id or self._stopped:
            return
        request_id, epoch = self._open_request_id, self._page_epoch
        if not self._open_probing:
            self._open_probing = True
            # Query a bounded outcome receipt; never execute the operation again.
            self.open_timer.start(5000)
            def checked(raw):
                if epoch != self._page_epoch or request_id != self._open_request_id or not self._open_probing:
                    return
                try:
                    outcome = json.loads(raw)
                except (ValueError, TypeError):
                    outcome = {}
                if isinstance(outcome, dict) and outcome.get("state") == "complete":
                    self._command_result(request_id, json.dumps(outcome.get("result")))
                    return
                self._open_deadline()
            self.page.runJavaScript(f"JSON.stringify(window.KfpsDesktop?.outcome?.({json.dumps(request_id)}))", checked)
            return
        self.open_timer.stop()
        self._open_uncertain = True
        self.server.diagnostics().record("command", source="native", action="load", state="failed")
        choice = self._close_message("warning", self.translator.tr("Editor operation delayed"),
            self.translator.tr("The open request has not finished. It will not be repeated automatically. Cancel keeps this window open while waiting. Retry reopens the editor; unsaved changes may be lost."),
            QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Retry and epoch == self._page_epoch and request_id == self._open_request_id:
            self._queued_requests.clear()
            self.reload_editor()

    def command(self, operation, payload, callback):
        request_id = uuid.uuid4().hex
        self._commands[request_id] = callback
        args = json.dumps([request_id, operation, payload])
        self.page.runJavaScript(f"window.KfpsDesktop.execute(...{args});")
        return request_id

    @Slot(str, str)
    def _command_result(self, request_id, payload):
        callback = self._commands.pop(request_id, None)
        if callback and not self._stopped and not self._allow_close:
            try:
                result = json.loads(payload)
                if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                    raise ValueError("Invalid response envelope")
                if result["ok"] and not isinstance(result.get("value"), dict):
                    raise ValueError("Invalid response value")
                if "error" in result and not isinstance(result["error"], str):
                    raise ValueError("Invalid response error")
            except (ValueError, TypeError):
                result = {"ok": False, "error": "Invalid editor response"}
            callback(result)

    def _cancel_close_attempt(self):
        self.close_timer.stop()
        self._close_epoch += 1
        self._closing = False
        if self._close_request_id:
            self._commands.pop(self._close_request_id, None)
        self._close_request_id = None
        self._close_phase = None

    def _invalidate_page_commands(self):
        self._page_epoch += 1
        self._checking_ready = False
        self._cancel_close_attempt()
        self._commands.clear()
        self.open_timer.stop()
        self.open_timer.setInterval(60000)
        self._open_request_id = None
        self._open_phase = None
        self._open_probing = self._open_uncertain = False

    def _close_command(self, operation, payload, callback):
        epoch = self._close_epoch
        def completed(result):
            if not self._closing or epoch != self._close_epoch:
                return
            self._close_request_id = None
            callback(result)
        self._close_phase = "working"
        self.close_timer.start()
        self._close_request_id = self.command(operation, payload, completed)

    @Slot(str, str)
    def _command_progress(self, request_id, phase):
        if request_id == self._open_request_id and phase in {"working", "user-wait"} and not self._open_uncertain:
            if phase == "user-wait" or phase != self._open_phase:
                self._open_probing = False
                self.open_timer.start(60000)
            self._open_phase = phase
            return
        if (not self._closing or request_id != self._close_request_id
                or phase not in {"working", "user-wait"}):
            return
        # Only a live human dialog renews the deadline. Repeated machine-work
        # heartbeats must not hide a stuck save or recovery request.
        if phase == "user-wait" or phase != self._close_phase:
            self.close_timer.start()
        self._close_phase = phase

    def _close_message(self, *args):
        self._close_prompt = True
        try:
            return self._message_box(*args)
        finally:
            self._close_prompt = False

    def _message_box(self, kind, title, text, buttons=QMessageBox.StandardButton.Ok, default=QMessageBox.StandardButton.Ok):
        box = QMessageBox(self)
        icons = {"information": QMessageBox.Icon.Information,
                 "question": QMessageBox.Icon.Question, "warning": QMessageBox.Icon.Warning}
        box.setIcon(icons[kind])
        box.setWindowTitle(self.translator.message(title))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(self.translator.message(text))
        box.setStandardButtons(buttons)
        box.setDefaultButton(default)
        for flag, label in ((QMessageBox.StandardButton.Save, "Save"),
                            (QMessageBox.StandardButton.Discard, "Discard"),
                            (QMessageBox.StandardButton.Cancel, "Cancel"),
                            (QMessageBox.StandardButton.Retry, "Retry"),
                            (QMessageBox.StandardButton.Close, "Close"),
                            (QMessageBox.StandardButton.Ok, "OK")):
            button = box.button(flag)
            if button is not None:
                button.setText(self.translator.tr(label))
        return QMessageBox.StandardButton(box.exec())

    def _download(self, download):
        path, _ = QFileDialog.getSaveFileName(self, self.translator.tr("Save Export"), download.downloadFileName())
        if not path:
            download.cancel()
            return
        target = Path(path)
        download.setDownloadDirectory(str(target.parent))
        download.setDownloadFileName(target.name)
        download.accept()

    def _renderer_stopped(self, status, exit_code):
        if not self._stopped:
            self.server.diagnostics().record("renderer-stopped", code=int(exit_code), source="native")
            self._show_failure(f"The editor renderer stopped (code {exit_code}). Reopen the editor to check for recoverable work. Saved projects are unchanged.")

    def _show_failure(self, message):
        if self.server:
            self.server.diagnostics().record("native-failed", source="native")
        self._ready = False
        self._failed = True
        self._invalidate_page_commands()
        self.ready_timer.stop()
        self.startup_timer.stop()
        self.close_timer.stop()
        try:
            self._write_state("failed", message)
        except OSError as exc:
            print(f"Editor startup status could not be written: {exc}", flush=True)
        self.error_label.setText(self.translator.message(message))
        self.stack.setCurrentWidget(self.error_panel)

    def reload_editor(self):
        if self._stopped or not self.page:
            return
        self.server.diagnostics().record("native-reload", source="native")
        self._invalidate_page_commands()
        self._failed = False
        self._ready = False
        self._checking_ready = False
        try:
            self._write_state("starting")
        except OSError as exc:
            self._show_failure(str(exc))
            return
        self.startup_timer.start()
        self.stack.setCurrentWidget(self.view)
        # The script removes the session fragment. Restoring only that fragment is
        # a same-document navigation, not a reload, even after a failed startup.
        restart_url = QUrl(self.url)
        restart_url.setQuery(f"restart={uuid.uuid4().hex}")
        self.page.load(restart_url)

    def closeEvent(self, event):
        if self._allow_close or self._failed or not self.page:
            event.accept()
            return
        event.ignore()
        if self._closing or self._close_prompt:
            return
        if not self._ready:
            self._allow_close = True
            self.close()
            return
        if self._commands:
            if self._open_uncertain:
                self._closing = True
                self._close_timed_out()
                return
            self._close_message("information", "Editor is busy", "Finish or cancel the current editor operation before closing.")
            return
        self._closing = True
        self._close_command("state", {}, self._confirm_close)

    def _confirm_close(self, result):
        self.close_timer.stop()
        state = result.get("value") if isinstance(result.get("value"), dict) else {}
        if (result.get("ok") is not True or type(state.get("dirty")) is not bool
                or type(state.get("saving")) is not bool or state["saving"]):
            self._cancel_close_attempt()
            self._close_message("information", "Editor is busy", "Wait for the current save or open operation to finish before closing.")
            return
        action = "keep-recovery"
        if state.get("dirty"):
            epoch = self._close_epoch
            choice = self._close_message("question", "Save before closing?", "This project has unsaved changes.", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if epoch != self._close_epoch or not self._closing:
                return
            if choice not in {QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard}:
                self._cancel_close_attempt()
                return
            if choice == QMessageBox.StandardButton.Save:
                action = "save"
        self._close_command("close", {"action": action}, self._close_prepared)

    def _close_timed_out(self):
        if not self._closing or self._close_prompt:
            return
        self.server.diagnostics().record("close-timeout", source="native")
        # Modal Qt dialogs run a nested event loop. Retire this attempt BEFORE
        # showing one, so an arriving success cannot close behind the question.
        self._cancel_close_attempt()
        epoch = self._page_epoch
        choice = self._close_message("warning", "Editor is not responding", "The editor has not responded to the close request. Keep it open to give it more time, or close anyway. Unsaved changes may be lost.", QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Close and epoch == self._page_epoch and not self._stopped:
            self._allow_close = True
            self.close()

    def _close_prepared(self, result):
        self._cancel_close_attempt()
        value = result.get("value") if isinstance(result.get("value"), dict) else {}
        if result.get("ok") is not True or value.get("ok") is not True:
            if value.get("cancelled") is True:
                return
            message = next((text for text in (result.get("error"), value.get("error")) if isinstance(text, str) and text), "The latest recovery or settings could not be written.")
            epoch = self._page_epoch
            choice = self._close_message("warning", "Could not finish saving", self.translator.message(message) + self.translator.tr("\n\nClose anyway? Recent changes may be lost."), QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if choice != QMessageBox.StandardButton.Close or epoch != self._page_epoch or self._stopped:
                return
        self._allow_close = True
        self.close()

    def shutdown(self):
        if self._stopped:
            return getattr(self, "_shutdown_complete", True)
        self._stopped = True
        self._shutdown_complete = False
        unsafe = []

        def cleanup(phase, operation, *, critical=False):
            try:
                operation()
            except Exception as error:
                record_startup(self.runtime, "shutdown-error", phase=phase,
                               error=type(error).__name__, winerror=getattr(error, "winerror", None))
                if critical:
                    unsafe.append(phase)

        cleanup("closing-state", lambda: self._write_state("closing"))
        cleanup("commands", self._invalidate_page_commands)
        for timer in (self.diagnostic_timer, self.ready_timer, self.startup_timer, self.close_timer):
            cleanup("timer", timer.stop)
        if self.server:
            cleanup("diagnostics", lambda: self.server.diagnostics().record("native-close", source="native"))
        if self._updates is not None:
            cleanup("updates", self._updates.close)
        cleanup("ipc", self.instance.close)
        for socket in list(self._sockets):
            cleanup("socket", socket.abort)
        if self.page:
            cleanup("page-stop", lambda: self.page.triggerAction(QWebEnginePage.WebAction.Stop))
        # Dispose every component even if an earlier one raises. Keep ownership
        # until process exit if a component that can write user data survives.
        for item in (self.view, self.page, self.profile):
            if item is not None and isValid(item):
                cleanup("webengine-dispose", lambda item=item: delete(item), critical=True)
        self.view = self.page = self.profile = None
        self._commands.clear()
        if self.server:
            if self.server_thread and self.server_thread.is_alive():
                cleanup("server-stop", self.server.shutdown, critical=True)
            cleanup("server-close", self.server.server_close, critical=True)
        if self.server_thread:
            cleanup("server-join", lambda: self.server_thread.join(timeout=2), critical=True)
            if self.server_thread.is_alive():
                unsafe.append("server-still-running")
        if self.module:
            if self._server_paths is not None:
                cleanup("server-marker", lambda: self.module._remove_owned_server_marker(paths=self._server_paths))
            marker = self.runtime / "desktop.json"
            try:
                if json.loads(marker.read_text(encoding="utf-8")).get("pid") == os.getpid():
                    marker.unlink()
            except (OSError, ValueError):
                pass
        if not unsafe:
            if self.lock.isLocked():
                cleanup("instance-unlock", self.lock.unlock, critical=True)
            if self._update_guard is not None:
                cleanup("update-unlock", self._update_guard.Close, critical=True)
                self._update_guard = None
        self._shutdown_complete = not unsafe
        record_startup(self.runtime, "shutdown-complete", released=self._shutdown_complete)
        return self._shutdown_complete
