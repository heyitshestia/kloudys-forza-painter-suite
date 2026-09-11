from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QFile, QIODevice, QLockFile, QObject, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from shiboken6 import delete, isValid
from .editor_localization import EditorTranslator, editor_system_language
from .editor_launch import forward_request, instance_name, validate_request
from .editor_update_guard import acquire_update_guard, updater_state_root


def load_editor_server(app_root: Path, runtime: Path):
    path = app_root / "tools" / "fabric-editor" / "start_fabric_editor.py"
    spec = importlib.util.spec_from_file_location("kfps_desktop_local_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, filename in {
        "STARTUP_HELP_MARKER": "startup-help-confirmed.json",
        "EDITOR_PREFS_MARKER": "preferences.json",
        "EDITOR_AUTOSAVE_MARKER": "autosave.json",
        "EDITOR_SERVER_MARKER": "server.json",
        "EDITOR_OUTPUT_CHANGE_MARKER": "editor-output-change.json",
        "EDITOR_PROJECT_CHANGE_MARKER": "project-change.json",
        "EDITOR_THEME_ROOT": "themes",
        "EDITOR_PROJECT_ROOT": "projects",
        "EDITOR_ASSET_ROOT": "assets",
    }.items():
        setattr(module, key, runtime / filename)
    return module


def start_local_server(module, runtime: Path):
    marker = runtime / "desktop-port.json"
    try:
        port = json.loads(marker.read_text(encoding="utf-8")).get("port")
        if type(port) is not int or not 1024 <= port <= 65535:
            port = 0
    except (OSError, ValueError, AttributeError):
        port = 0
    try:
        server = module.EditorServer(("127.0.0.1", port), module.Handler)
    except OSError:
        if port == 0:
            raise
        server = module.EditorServer(("127.0.0.1", 0), module.Handler)
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
            from tools.fabric_editor_diagnostics import ASSETS
            path = QUrl(source).path().removeprefix("/tools/fabric-editor/")
            error = next((name for name in ("TypeError", "RangeError", "ReferenceError", "SyntaxError", "SecurityError", "QuotaExceededError") if name in message[:200]), "unknown")
            host.server.diagnostics().record(severity, line=int(line), source=path if path in ASSETS else "unknown", error=error)


class EditorBridge(QObject):
    result = Signal(str, str)

    @Slot(str, str)
    def completed(self, request_id: str, payload: str):
        if len(request_id) <= 64 and len(payload) <= 16384:
            self.result.emit(request_id, payload)


class EditorDesktop(QMainWindow):
    def __init__(self, app_root: Path, runtime: Path):
        super().__init__()
        self.app_root = app_root.resolve()
        self.runtime = runtime.resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.system_language = editor_system_language()
        self.translator = EditorTranslator(self.app_root, self.runtime, self.system_language)
        self.instance = QLocalServer(self)
        self.instance.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.instance.newConnection.connect(self._accept_connection)
        self.lock = QLockFile(str(self.runtime / "desktop.lock"))
        self.lock.setStaleLockTime(0)
        self.module = None
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
        self._allow_close = False
        self._stopped = False
        self._failed = False
        self._update_guard = None
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

    def start(self, request: dict) -> bool:
        request = validate_request(request)
        if not self.lock.tryLock(0):
            return False
        if os.name == "nt":
            state = updater_state_root(self.app_root) if self.runtime == self.app_root / "runtime" / "fabric-editor" else self.runtime / "update-state"
            self._update_guard = acquire_update_guard(state)
        name = instance_name(self.app_root, self.runtime)
        QLocalServer.removeServer(name)
        if not self.instance.listen(name):
            raise RuntimeError(f"Could not start the editor launcher connection: {self.instance.errorString()}")
        self.module = load_editor_server(self.app_root, self.runtime)
        self.server = start_local_server(self.module, self.runtime)
        self.server.diagnostics().record("native-start", source="native")
        self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, name="kfps-editor-local", daemon=True)
        self.server_thread.start()
        port = self.server.server_address[1]
        self.module._write_server_marker(port, self.server.editor_session_token)
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
            })

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
                    if self._closing or len(self._queued_requests) >= 8:
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
        self.showNormal() if self.isMinimized() else self.show()
        self.raise_()
        self.activateWindow()
        if self._failed:
            self._failed = False
            self._write_state("starting")
            # Recreating Chromium's page can take longer than the IPC ACK budget.
            QTimer.singleShot(0, self.reload_editor)
        if request == {"project": "", "mode": "activate"}:
            return
        self._queued_requests.append(request)
        self._dispatch_open()

    def _loaded(self, ok):
        if not ok:
            return
        self._checking_ready = False
        self.ready_timer.start()

    def _loading_changed(self, info):
        # Reopen cancels an older navigation. A cancellation is not a page failure.
        if not self._stopped and info.status() == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            self._show_failure("The editor page could not be loaded. Your saved projects and recovery files have not been removed.")

    def _check_ready(self):
        if self._checking_ready or not self.page:
            return
        self._checking_ready = True
        def checked(state):
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
            self.server.diagnostics().record("native-ready", source="native")
            self._dispatch_open()
        self.page.runJavaScript("JSON.stringify({ready: Boolean(window.KfpsDesktop?.ready && window.KfpsDesktopBridge), error: window.KfpsDesktop?.error || ''})", checked)

    def _dispatch_open(self):
        if not self._ready or self._commands or not self._queued_requests or self._closing:
            return
        request = self._queued_requests.pop(0)
        self.command("open", request, lambda result: self._dispatch_open())

    def command(self, operation, payload, callback):
        request_id = uuid.uuid4().hex
        self._commands[request_id] = callback
        args = json.dumps([request_id, operation, payload])
        self.page.runJavaScript(f"window.KfpsDesktop.execute(...{args});")

    @Slot(str, str)
    def _command_result(self, request_id, payload):
        callback = self._commands.pop(request_id, None)
        if callback:
            try:
                result = json.loads(payload)
            except ValueError:
                result = {"ok": False, "error": "Invalid editor response"}
            callback(result)

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
        self._closing = False
        self._commands.clear()
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
        if self._closing:
            self._close_timed_out()
            return
        if not self._ready:
            self._allow_close = True
            self.close()
            return
        if self._commands:
            self._message_box("information", "Editor is busy", "Finish or cancel the current editor operation before closing.")
            return
        self._closing = True
        self.close_timer.start()
        self.command("state", {}, self._confirm_close)

    def _confirm_close(self, result):
        self.close_timer.stop()
        state = result.get("value") or {}
        if not result.get("ok") or state.get("saving"):
            self._closing = False
            self._message_box("information", "Editor is busy", "Wait for the current save or open operation to finish before closing.")
            return
        action = "keep-recovery"
        if state.get("dirty"):
            choice = self._message_box("question", "Save before closing?", "This project has unsaved changes.", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if choice == QMessageBox.StandardButton.Cancel:
                self._closing = False
                return
            if choice == QMessageBox.StandardButton.Save:
                action = "save"
        self.command("close", {"action": action}, self._close_prepared)

    def _close_timed_out(self):
        self.server.diagnostics().record("close-timeout", source="native")
        choice = self._message_box("warning", "Editor is not responding", "The editor has not responded to the close request. Keep it open to give it more time, or close anyway. Unsaved changes may be lost.", QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Close:
            self._allow_close = True
            self.close()
        else:
            self._commands.clear()
            self._closing = False

    def _close_prepared(self, result):
        self.close_timer.stop()
        self._closing = False
        value = result.get("value") or {}
        if not result.get("ok") or not value.get("ok"):
            if value.get("cancelled"):
                return
            message = result.get("error") or value.get("error") or "The latest recovery or settings could not be written."
            choice = self._message_box("warning", "Could not finish saving", self.translator.message(message) + self.translator.tr("\n\nClose anyway? Recent changes may be lost."), QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if choice != QMessageBox.StandardButton.Close:
                return
        self._allow_close = True
        self.close()

    def shutdown(self):
        if self._stopped:
            return
        self._stopped = True
        self.diagnostic_timer.stop()
        if self.server:
            self.server.diagnostics().record("native-close", source="native")
        self.ready_timer.stop()
        self.startup_timer.stop()
        self.close_timer.stop()
        self.instance.close()
        for socket in list(self._sockets):
            socket.abort()
        if self.page:
            self.page.triggerAction(QWebEnginePage.WebAction.Stop)
        # Chromium must release its pages before the persistent profile and before
        # QApplication teardown, including when the window is restarted in tests.
        for item in (self.view, self.page, self.profile):
            if item is not None and isValid(item):
                delete(item)
        self.view = self.page = self.profile = None
        self._commands.clear()
        if self.server:
            if self.server_thread and self.server_thread.is_alive():
                self.server.shutdown()
            self.server.server_close()
        if self.server_thread:
            self.server_thread.join(timeout=2)
        if self.module:
            self.module._remove_owned_server_marker()
            marker = self.runtime / "desktop.json"
            try:
                if json.loads(marker.read_text(encoding="utf-8")).get("pid") == os.getpid():
                    marker.unlink()
            except (OSError, ValueError):
                pass
        if self.lock.isLocked():
            self.lock.unlock()
        if self._update_guard is not None:
            self._update_guard.Close()
            self._update_guard = None
