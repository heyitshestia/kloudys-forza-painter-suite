"""Dedicated report review. Only the trusted form receives local report bytes."""
from __future__ import annotations

import argparse
import base64
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QLocale, QLockFile, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget
from shiboken6 import delete, isValid

from .support_report import FORM_ORIGIN
from .support_window_protocol import CHUNK_BYTES, read_source, report_id, window_name


def origin_of(url: QUrl) -> str:
    if url.userName() or url.password():
        return ""
    port = url.port()
    default = 443 if url.scheme() == "https" else 80
    suffix = f":{port}" if port not in (-1, default) else ""
    return f"{url.scheme()}://{url.host()}{suffix}"


class ReportPage(QWebEnginePage):
    def __init__(self, profile, parent, origin):
        super().__init__(profile, parent)
        self.form_origin = origin

    def acceptNavigationRequest(self, url, kind, main_frame):
        if not main_frame:
            return True
        origin = origin_of(url)
        if origin == self.form_origin and url.path() not in {"/auth/start", "/auth/callback", "/auth/native"}:
            return True
        if kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme() == "https":
            QDesktopServices.openUrl(url)
        return False

    def javaScriptConsoleMessage(self, level, message, line, source):
        # OAuth pages and console messages may contain credentials. Do not log them.
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logging.getLogger("kfps-report-window").warning("web-console-error")


class ReportWindow(QMainWindow):
    def __init__(self, root: Path, *, origin=FORM_ORIGIN, background=False):
        super().__init__()
        self.root = root.resolve()
        self.origin = origin
        if origin != FORM_ORIGIN and not (origin.startswith("http://127.0.0.1:") and QUrl(origin).path() == ""):
            raise ValueError("Untrusted support form origin.")
        self.korean = QLocale.system().name().lower().startswith("ko")
        self.closed = False
        self.identifier = ""
        self.data = b""
        self.metadata = {}
        self.epoch = 0
        self.inflight = False
        self.auth_inflight = False
        self.deadline = 0.0
        self.background = background
        self.logger = logging.getLogger("kfps-report-window")
        self.setWindowTitle(self.tr_text("KFPS - Report a Problem", "KFPS - 문제 신고"))
        self.setWindowIcon(QIcon(str(root / "KFPS.UI/assets/kfps-logo.png")))
        self.resize(1080, 840)
        self.setMinimumSize(520, 480)
        if background:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = QLabel(self.tr_text("Opening your report...", "보고서를 여는 중입니다..."), panel)
        self.status.setWordWrap(True)
        self.status.setMargin(12)
        self.retry = QPushButton(self.tr_text("Retry", "다시 시도"), panel)
        self.retry.hide()
        self.retry.clicked.connect(self.reload_review)
        layout.addWidget(self.status)
        layout.addWidget(self.retry)
        self.view = QWebEngineView(panel)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(panel)
        profile_root = root / "runtime/support-reports/browser"
        profile_root.mkdir(parents=True, exist_ok=True)
        if getattr(profile_root.lstat(), "st_file_attributes", 0) & 0x400 or profile_root.is_symlink():
            raise ValueError("Linked report browser profiles are not supported.")
        for child in (profile_root / "storage", profile_root / "cache"):
            child.mkdir(exist_ok=True)
            if child.is_symlink() or getattr(child.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked report browser profiles are not supported.")
        self.profile = QWebEngineProfile("kfps-report-review", self)
        self.profile.setPersistentStoragePath(str(profile_root / "storage"))
        self.profile.setCachePath(str(profile_root / "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.downloadRequested.connect(self.download)
        self.page = ReportPage(self.profile, self, origin)
        script = QWebEngineScript()
        script.setName("kfps-native-report")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(f"if(location.origin==={json.dumps(origin)})Object.defineProperty(window,'KFPSNativeReport',{{value:true}});")
        self.page.scripts().insert(script)
        self.page.permissionRequested.connect(lambda permission: permission.deny())
        self.page.newWindowRequested.connect(self.open_external)
        self.page.certificateError.connect(lambda error: error.rejectCertificate())
        self.page.renderProcessTerminated.connect(self.renderer_failed)
        self.view.setPage(self.page)
        settings = self.page.settings()
        for option in (QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                       QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                       QWebEngineSettings.WebAttribute.AllowRunningInsecureContent,
                       QWebEngineSettings.WebAttribute.FullScreenSupportEnabled):
            settings.setAttribute(option, False)
        self.page.loadStarted.connect(self.load_started)
        self.page.loadFinished.connect(self.load_finished)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.load_timeout = QTimer(self)
        self.load_timeout.setSingleShot(True)
        self.load_timeout.setInterval(75000)
        self.load_timeout.timeout.connect(lambda: self.fail("page-load-timeout"))
        self.auth_timer = QTimer(self)
        self.auth_timer.setInterval(500)
        self.auth_timer.timeout.connect(self.poll_auth)

    def tr_text(self, english, korean):
        return korean if self.korean else english

    def open_report(self, identifier, *, confirm=True):
        identifier = report_id(identifier)
        if confirm and self.identifier and self.identifier != identifier:
            choice = QMessageBox.question(self, self.windowTitle(), self.tr_text(
                "Open the new report? The current report's saved copy remains available; nothing is sent automatically.",
                "새 보고서를 여시겠어요? 현재 보고서의 저장된 사본은 유지되며, 자동으로 전송되는 내용은 없습니다."))
            if choice != QMessageBox.StandardButton.Yes:
                return False
        data, metadata = read_source(self.root, identifier)
        self.identifier, self.data, self.metadata = identifier, data, metadata
        self.reload_review()
        self.show()
        if not self.background:
            self.raise_()
            self.activateWindow()
        self.logger.info("report-open bytes=%s mode=%s", len(data), metadata["mode"])
        return True

    def reload_review(self):
        self.retry.hide()
        self.view.load(QUrl(self.origin + "/"))

    def load_started(self):
        self.epoch += 1
        self.inflight = False
        self.auth_inflight = False
        self.auth_timer.stop()
        self.timer.stop()
        self.load_timeout.start()

    def load_finished(self, success):
        self.load_timeout.stop()
        if self.closed or origin_of(self.page.url()) != self.origin:
            return
        if not success:
            self.fail("network")
            return
        self.status.show()
        self.status.setText(self.tr_text("Adding your report and logs...", "보고서와 로그를 준비하는 중입니다..."))
        self.deadline = time.monotonic() + 90
        self.timer.start()
        self.auth_timer.start()

    def run(self, script, callback):
        epoch = self.epoch
        def completed(value):
            if not self.closed and epoch == self.epoch and origin_of(self.page.url()) == self.origin:
                try:
                    decoded = json.loads(value) if isinstance(value, str) else None
                except (ValueError, TypeError):
                    decoded = None
                callback(decoded)
        # The condition is rechecked inside the renderer to cover a navigation race.
        source = f"JSON.stringify(location.origin === {json.dumps(self.origin)} ? (()=>{{{script}}})() : null)"
        self.page.runJavaScript(source, completed)

    def poll_auth(self):
        if self.closed or self.auth_inflight or origin_of(self.page.url()) != self.origin:
            return
        self.auth_inflight = True
        self.run("return window.KFPSReportSignIn?.request() || null;", self.launch_auth)

    def launch_auth(self, value):
        self.auth_inflight = False
        if not isinstance(value, dict):
            return
        try:
            identifier = report_id(value.get("id", ""))
        except (TypeError, ValueError):
            return
        expected = f"{self.origin}/auth/native?ticket={identifier}"
        if value.get("url") != expected:
            return
        # Windows' HTTPS handler opens the user's default browser, never a named engine.
        success = QDesktopServices.openUrl(QUrl(expected))
        self.run(f"window.KFPSReportSignIn.opened({json.dumps(identifier)},{json.dumps(bool(success))});return true;", lambda _: None)
        self.logger.info("browser-authorization opened=%s", bool(success))

    def poll(self):
        if self.closed or not self.identifier:
            return
        if time.monotonic() > self.deadline:
            self.fail("handoff-timeout")
            return
        if self.inflight:
            return
        if origin_of(self.page.url()) != self.origin:
            return
        self.inflight = True
        self.run(f"return window.KFPSReportTransfer?.status({json.dumps(self.identifier)}) || null;", self.state_ready)

    def state_ready(self, value):
        self.inflight = False
        if not isinstance(value, dict):
            return
        state = value.get("state")
        if state == "ready":
            self.timer.stop()
            self.status.hide()
            self.retry.hide()
            self.logger.info("report-ready bytes=%s", len(self.data))
        elif state == "idle":
            self.inflight = True
            self.run(f"return window.KFPSReportTransfer.begin({json.dumps(self.metadata)});", lambda ok: self.send_chunk(0) if ok is True else self.fail("handoff-start"))
        elif state == "error":
            self.fail("handoff-validation")

    def send_chunk(self, offset):
        if offset >= len(self.data):
            self.run("return window.KFPSReportTransfer.finish();", self.transfer_finished)
            return
        block = self.data[offset:offset + CHUNK_BYTES]
        encoded = base64.b64encode(block).decode("ascii")
        end = offset + len(block)
        self.run(f"return window.KFPSReportTransfer.chunk({offset // CHUNK_BYTES},{json.dumps(encoded)});",
                 lambda received: self.send_chunk(end) if received == end else self.fail("handoff-chunk"))

    def transfer_finished(self, ok):
        self.inflight = False
        if ok is not True:
            self.fail("handoff-finish")

    def fail(self, code):
        self.timer.stop()
        self.load_timeout.stop()
        self.auth_timer.stop()
        self.epoch += 1
        self.inflight = False
        self.status.show()
        self.status.setText(self.tr_text(
            "Your report is saved. The review could not finish loading. Check your connection and retry; nothing has been sent automatically.",
            "보고서는 저장되어 있습니다. 신고 화면을 불러오지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요. 자동으로 전송된 내용은 없습니다."))
        self.retry.show()
        self.logger.warning("review-failed code=%s", code)

    def renderer_failed(self, status, code):
        self.fail("renderer-terminated")

    def open_external(self, request):
        url = request.requestedUrl()
        if request.isUserInitiated() and url.scheme() == "https" and not url.userName() and not url.password():
            QDesktopServices.openUrl(url)

    def download(self, request):
        if origin_of(self.page.url()) != self.origin:
            request.cancel()
            return
        name = Path(request.suggestedFileName()).name
        if not name.endswith((".json", ".json.gz")):
            request.cancel()
            return
        path, _ = QFileDialog.getSaveFileName(self, self.tr_text("Save reviewed logs", "확인한 로그 저장"), name)
        if not path:
            request.cancel()
            return
        request.setDownloadDirectory(str(Path(path).parent))
        request.setDownloadFileName(Path(path).name)
        request.accept()

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.epoch += 1
        self.timer.stop()
        self.load_timeout.stop()
        self.auth_timer.stop()
        self.data = b""
        for obj in (self.view, self.page, self.profile):
            if isValid(obj):
                delete(obj)


def forward(name, identifier, timeout=500):
    socket = QLocalSocket()
    try:
        socket.connectToServer(name)
        if not socket.waitForConnected(timeout):
            return False
        socket.write((report_id(identifier) + "\n").encode("ascii"))
        socket.waitForBytesWritten(timeout)
        return socket.waitForReadyRead(timeout) and bytes(socket.readAll()) == b"accepted\n"
    finally:
        socket.abort()


def listen(server, window):
    def connected():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            socket.setReadBufferSize(128)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(1500)
            def read(socket=socket):
                data = bytes(socket.peek(128))
                if b"\n" not in data:
                    if len(data) >= 128:
                        socket.abort()
                    return
                try:
                    identifier = report_id(bytes(socket.readLine()).decode("ascii").strip())
                    socket.write(b"accepted\n")
                    socket.flush()
                    socket.disconnectFromServer()
                    window.open_report(identifier)
                except (OSError, ValueError):
                    socket.abort()
            socket.readyRead.connect(read)
            socket.disconnected.connect(socket.deleteLater)
            read()
    server.newConnection.connect(connected)


def main(root: Path) -> int:
    parser = argparse.ArgumentParser(description="KFPS report review")
    parser.add_argument("--report-id", required=True)
    args = parser.parse_args()
    app = None
    window = None
    lock = None
    server = None
    guard = None
    logger = logging.getLogger("kfps-report-window")
    try:
        identifier = report_id(args.report_id)
        read_source(root, identifier)
        log_path = root / "runtime/support-reports/report-window.log"
        handler = RotatingFileHandler(log_path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        from kfps_editor.baseline import verify
        verify(root)
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv[:1])
        app.setApplicationName("KFPS Report")
        name = window_name(root)
        if forward(name, identifier):
            return 0
        lock = QLockFile(str(root / "runtime/support-reports/window.lock"))
        if not lock.tryLock(0):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if forward(name, identifier):
                    return 0
                time.sleep(.05)
            raise RuntimeError("The report window is still starting or closing. Try again.")
        if os.name == "nt":
            from kfps_editor.update_guard import acquire_update_guard, updater_state_root
            guard = acquire_update_guard(updater_state_root(root))
        window = ReportWindow(root)
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(name)
        if not server.listen(name):
            raise RuntimeError("Could not start the report window.")
        listen(server, window)
        window.open_report(identifier, confirm=False)
        return app.exec()
    except Exception as error:
        logger.error("startup-failed type=%s", type(error).__name__)
        if app is None:
            app = QApplication(sys.argv[:1])
        korean = QLocale.system().name().lower().startswith("ko")
        QMessageBox.warning(None, "KFPS", "신고 창을 열지 못했습니다. 보고서는 저장되어 있습니다. KFPS-Updater.exe로 앱을 복구한 뒤 다시 시도해 주세요."
                            if korean else "The report window could not open. Your report is saved. Run KFPS-Updater.exe to repair the app and try again.")
        return 1
    finally:
        if server is not None:
            server.close()
        if window is not None:
            window.shutdown()
        if guard is not None:
            guard.Close()
        if lock is not None:
            lock.unlock()
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
