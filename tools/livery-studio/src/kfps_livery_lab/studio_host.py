"""Reusable Studio widgets; the caller owns QApplication and backend lifetime."""
from __future__ import annotations

import json
from pathlib import Path
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Qt, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile,
    QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from shiboken6 import delete, isValid

if __package__:
    from .native_host import NativePresentation, READINESS_SCRIPT
    from .studio_window import LAB, acquire_native_owner, validate_window_url
else:
    from native_host import NativePresentation, READINESS_SCRIPT
    from studio_window import LAB, acquire_native_owner, validate_window_url


CLOSE_STATE_SCRIPT = """(() => {
    if (!window.__liveryLab?.ready) return null;
    const event = new Event('beforeunload', {cancelable:true});
    window.dispatchEvent(event);
    return JSON.stringify({document:window.__kfpsStudioNativeDocument,
        dirty:event.defaultPrevented, modal:!!document.querySelector('dialog[open]')});
})()"""


class Requests(QWebEngineUrlRequestInterceptor):
    def __init__(self, owner, parent):
        super().__init__(parent)
        self.owner = owner

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if (not self.owner.local(url) and not url.startswith("data:")
                and not (url.startswith("blob:") and self.owner.local(url[5:]))):
            info.block(True)


class Page(QWebEnginePage):
    def __init__(self, owner, profile, parent):
        super().__init__(profile, parent)
        self.owner = owner

    def acceptNavigationRequest(self, url, navigation_type, main_frame):
        if not self.owner.local(url.toString()):
            return False
        if main_frame:
            try:
                validate_window_url(url.toString())
            except ValueError:
                return False
        return True

    def createWindow(self, _kind):
        return None

    def javaScriptConfirm(self, security_origin, message):
        owner, attempt = self.owner, self.owner._flight
        if owner._committing is not None:
            return owner._committing[0] == owner.generation and not owner.pending_downloads and not owner.stopped
        if owner.offscreen:
            accepted = owner.test_control().get("confirm") is True
            owner.test_event("confirm", accepted=accepted)
        else:
            accepted = super().javaScriptConfirm(security_origin, message)
        # Native dialogs run a nested event loop: cancellation can occur inside it.
        if attempt is not None and (owner._callback is None or owner._callback[0] != attempt):
            accepted = False
        if not accepted:
            owner._native_request = False
        return accepted

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            print(f"Studio JavaScript error at line {line}", flush=True)


class Window(QMainWindow):
    def __init__(self, owner, parent):
        super().__init__(parent, Qt.WindowType.Widget if owner.hosted else Qt.WindowType.Window)
        if owner.hosted:
            self.setWindowFlags(Qt.WindowType.Widget)
        self.owner = owner

    def closeEvent(self, event):
        if self.owner.stopped:
            event.accept()
            return
        event.ignore()
        if self.owner.hosted:
            self.owner.closeRequested.emit()
        else:
            self.owner._standalone_close()


class StudioHost(QObject):
    readyChanged = Signal(bool)
    failed = Signal(str)
    closeRequested = Signal()
    closed = Signal()

    def __init__(self, url, run, *, parent=None, hosted=True, offscreen=False,
                 diagnostic_policy="unknown", test_control=None, test_event=None):
        if not isinstance(QApplication.instance(), QApplication):
            raise RuntimeError("StudioHost requires the caller's QApplication.")
        validate_window_url(url)
        lock = acquire_native_owner(url)
        try:
            super().__init__(parent)
        except BaseException:
            lock.unlock()
            raise
        self._native_owner = lock
        try:
            self._initialize(url, run, parent=parent, hosted=hosted, offscreen=offscreen,
                             diagnostic_policy=diagnostic_policy, test_control=test_control,
                             test_event=test_event)
        except BaseException:
            for name in ("page", "view", "profile", "window"):
                item = getattr(self, name, None)
                if item is not None and isValid(item):
                    delete(item)
            self._native_owner.unlock()
            delete(self)
            raise

    def _initialize(self, url, run, *, parent, hosted, offscreen,
                    diagnostic_policy, test_control, test_event):
        self.origin = urlsplit(url)
        self.run = Path(run).resolve()
        self.run.mkdir(parents=True, exist_ok=True)
        self.hosted, self.offscreen = bool(hosted), bool(offscreen)
        self.test_control = test_control if self.offscreen and test_control else lambda: {}
        self.test_event = test_event if self.offscreen and test_event else lambda *_args, **_data: None
        self.presentation = NativePresentation()
        self.ready = self.stopped = self._failed = False
        self.generation = 0
        self.native_document = ""
        self.pending_downloads = {}
        self._serial = 0
        self._flight = self._callback = self._prepared = None
        self._committing = None
        self._prepared_failed = False
        self._native_request = False
        self._enabled_before_close = None
        self.window = Window(self, parent)
        self.window.setWindowTitle("KFPS Livery Studio")
        self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, self.offscreen)
        self.window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, self.offscreen)
        self.profile = QWebEngineProfile("studio", self.window)
        self.profile.setPersistentStoragePath(str(self.run / "profile"))
        self.profile.setCachePath(str(self.run / "cache"))
        self.profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.interceptor = Requests(self, self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.view = QWebEngineView(self.window)
        self.page = Page(self, self.profile, self.view)
        # Even parent-driven Qt destruction must retain the lease until the page
        # is gone, not merely until the Python wrapper or shell owner disappears.
        lock = self._native_owner
        self.page.destroyed.connect(lambda *_: lock.unlock())
        self.view.setPage(self.page)
        self.window.setCentralWidget(self.view)
        marker = QWebEngineScript()
        marker.setName("kfps-studio-native-downloads")
        marker.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        marker.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        marker.setRunsOnSubFrames(False)
        policy = diagnostic_policy if diagnostic_policy in ("auto", "opengl", "d3d11") else "unknown"
        marker.setSourceCode("window.__kfpsStudioNativeDownloads = true; window.__kfpsStudioNativeDocument = crypto.randomUUID();"
                             + "window.__kfpsStudioDiagnosticPolicy = " + json.dumps(policy) + ";")
        self.page.scripts().insert(marker)
        settings = self.page.settings()
        for option in (QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
                       QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
                       QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows):
            settings.setAttribute(option, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        self.page.fullScreenRequested.connect(self._fullscreen)
        self.page.featurePermissionRequested.connect(lambda url, feature: self.page.setFeaturePermission(
            url, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.setInterval(15000)
        self.close_timer.timeout.connect(self._close_timeout)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._poll)
        self.page.loadStarted.connect(self._navigating)
        self.page.windowCloseRequested.connect(self._native_close_accepted)
        self.page.renderProcessTerminated.connect(lambda *_: self._failure("Studio web renderer stopped."))
        self.profile.downloadRequested.connect(self.download)
        self.started = time.monotonic()
        self.timer.start()
        self.view.load(QUrl(url))

    def local(self, url):
        try:
            parsed = urlsplit(url)
            return (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                    and parsed.port == self.origin.port and not parsed.username and not parsed.password)
        except ValueError:
            return False

    def _fullscreen(self, request):
        request.accept()
        target = self.window.window()
        target.showFullScreen() if request.toggleOn() else target.showNormal()

    def _navigating(self):
        if self.stopped:
            return
        self.cancel_close()
        self.generation += 1
        self.native_document = ""
        self.presentation.set_language("en")
        self.ready = self._failed = False
        self.readyChanged.emit(False)
        self.started = time.monotonic()
        self.timer.start()

    def _readiness(self, value, generation):
        if self.stopped or self._failed or generation != self.generation or not isinstance(value, str) or len(value) > 4096:
            return
        try:
            data = json.loads(value)
        except ValueError:
            return
        if not isinstance(data, dict) or not data.get("document"):
            return
        self.native_document = data["document"]
        self.presentation.set_language(data.get("language"))
        if self.ready or not data.get("ready"):
            return
        self.ready = True
        self.timer.stop()
        self.readyChanged.emit(True)

    def _poll(self):
        if self.stopped or self._failed:
            return
        if not self.ready and time.monotonic() - self.started > 55:
            self._failure("Studio page did not finish loading.")
            return
        generation = self.generation
        self.page.runJavaScript(READINESS_SCRIPT, lambda value: self._readiness(value, generation))

    def _failure(self, message):
        if self.stopped:
            return
        self._failed = True
        self.ready = False
        self.timer.stop()
        self.cancel_close()
        self.readyChanged.emit(False)
        self.failed.emit(message)

    def _restore_input(self):
        if self._enabled_before_close is not None:
            if isValid(self.view):
                self.view.setEnabled(self._enabled_before_close)
            self._enabled_before_close = None

    def prepare_close(self, callback):
        """Consult the existing beforeunload veto without triggering pagehide."""
        if not callable(callback):
            raise TypeError("Close callback must be callable.")
        if self.stopped or self._flight is not None or self._native_request or self.pending_downloads:
            if self.pending_downloads:
                self.window.statusBar().showMessage(self.presentation.text(
                    "A file is still being saved. Close again after it finishes."), 5000)
                self.test_event("close_waits_for_downloads")
            QTimer.singleShot(0, self, lambda: callback(False))
            return
        self.cancel_close()
        self._serial += 1
        attempt = (self.generation, self._serial)
        self._flight = attempt
        self._callback = (attempt, callback)
        self._enabled_before_close = self.view.isEnabled()
        self.view.setEnabled(False)
        if self._failed:
            accepted = self.page.javaScriptConfirm(QUrl(f"http://127.0.0.1:{self.origin.port}/"),
                self.page.tr("Studio could not finish loading or its renderer stopped. Close this failed page? "
                             "Any unsaved work in this page will be discarded."))
            self._close_decided(accepted, attempt, allow_failed=True)
            return
        self.close_timer.start()
        self.page.runJavaScript(CLOSE_STATE_SCRIPT, lambda value: self._close_state(value, attempt))

    def _close_state(self, value, attempt):
        if self.stopped or attempt != self._flight or attempt[0] != self.generation:
            return
        try:
            state = json.loads(value) if isinstance(value, str) and len(value) <= 4096 else None
        except ValueError:
            state = None
        valid = (isinstance(state, dict) and state.get("document") == self.native_document
                 and bool(self.native_document) and type(state.get("dirty")) is bool
                 and state.get("modal") is False)
        accepted = bool(valid)
        if accepted and state["dirty"]:
            accepted = self.page.javaScriptConfirm(QUrl(f"http://127.0.0.1:{self.origin.port}/"),
                self.page.tr("Changes you made may not be saved. Leave this page?"))
        self._close_decided(accepted, attempt)

    def _standalone_close(self):
        if self._native_request or self.stopped:
            return
        if self.pending_downloads:
            self.window.statusBar().showMessage(self.presentation.text(
                "A file is still being saved. Close again after it finishes."), 5000)
            self.test_event("close_waits_for_downloads")
            return
        self._native_request = True
        self.page.triggerAction(QWebEnginePage.WebAction.RequestClose)

    def _native_close_accepted(self):
        if self.stopped or not self._native_request:
            return
        self._native_request = False
        if self._committing is not None and self._committing[0] != self.generation:
            self._committing = None
            self.cancel_close()
            self.failed.emit("Studio navigated while closing. Its current page was not closed.")
            return
        if self.pending_downloads:
            self.test_event("close_waits_for_downloads")
            return
        if self._committing is None and self.hosted:
            return
        self.shutdown()
        self.closed.emit()

    def _close_decided(self, accepted, attempt, *, allow_failed=False):
        if attempt != self._flight:
            return
        self._flight = None
        self.close_timer.stop()
        if self._callback is None or self._callback[0] != attempt:
            return
        _, callback = self._callback
        self._callback = None
        accepted = bool(accepted and not self.stopped and (not self._failed or allow_failed)
                        and attempt[0] == self.generation and not self.pending_downloads)
        if accepted:
            self._prepared = attempt
            self._prepared_failed = bool(allow_failed and self._failed)
        else:
            self._restore_input()
        QTimer.singleShot(0, self, lambda: callback(bool(accepted and self._prepared == attempt
            and not self.stopped and not self.pending_downloads)))

    def cancel_close(self):
        """Invalidate preparation; queued JavaScript replies retain their attempt ID."""
        if self._committing is not None:
            return
        self.close_timer.stop()
        self._prepared = None
        self._prepared_failed = False
        self._flight = None
        pending, self._callback = self._callback, None
        self._restore_input()
        if pending is not None:
            QTimer.singleShot(0, self, lambda: pending[1](False))

    def _close_timeout(self):
        self.cancel_close()
        self.test_event("close_timeout")

    def commit_close(self):
        if (self.stopped or self._prepared is None or self._prepared[0] != self.generation
                or self.pending_downloads or (self._failed and not self._prepared_failed) or self._native_request):
            return False
        self._committing = self._prepared
        if self._prepared_failed:
            self.shutdown()
            self.closed.emit()
            return True
        self._native_request = True
        self.page.triggerAction(QWebEnginePage.WebAction.RequestClose)
        return True

    def download(self, item):
        url = item.url().toString()
        if self.stopped or item.page() != self.page or not url.startswith(f"blob:http://127.0.0.1:{self.origin.port}/"):
            item.cancel()
            return
        self.cancel_close()
        captured = self.generation
        identifier, document, completed = item.id(), self.native_document, False

        def deliver(status, message, current_document):
            if self.stopped or captured != self.generation or not isinstance(current_document, str) or not current_document:
                return
            payload = json.dumps({"status": status, "message": message})
            self.page.runJavaScript(f"if(window.__kfpsStudioNativeDocument === {json.dumps(current_document)}) window.__kfpsStudioDownloadFinished?.({json.dumps(url)}, {payload});")

        def finished(status, message=""):
            nonlocal completed
            if completed:
                return
            completed = True
            self.pending_downloads.pop(identifier, None)
            self.test_event("download", status=status)
            if not self.stopped and captured == self.generation:
                if document:
                    deliver(status, message, document)
                else:
                    self.page.runJavaScript("window.__kfpsStudioNativeDocument", lambda value: deliver(status, message, value))

        def state_changed(state):
            if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                finished("completed")
            elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
                finished("cancelled")
            elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                finished("failed", "The file could not be saved. Choose a writable location and try again.")

        try:
            item.stateChanged.connect(state_changed)
            if len(self.pending_downloads) >= 16:
                finished("failed", "Too many files are being saved. Wait for them to finish and try again.")
                item.cancel()
                return
            self.pending_downloads[identifier] = item
            if not document:
                finished("cancelled")
                item.cancel()
                return
            decision = self.test_control().get("download") if self.offscreen else None
            if self.offscreen and decision not in ("save", "fail"):
                item.cancel()
                finished("cancelled")
                return
            name = Path(item.suggestedFileName().replace("\\", "/")).name or "studio-export.json"
            path = self._download_path(name, decision)
            if self.stopped or captured != self.generation or not path:
                if isValid(item):
                    item.cancel()
                finished("cancelled")
                return
            item.setDownloadDirectory(str(Path(path).parent))
            item.setDownloadFileName(Path(path).name)
            item.accept()
            if self.offscreen and self.test_control().get("pause_download"):
                item.pause()
        except Exception:
            finished("failed", "The save destination could not be opened. Choose a writable location and try again.")
            if isValid(item):
                item.cancel()

    def _download_path(self, name, decision):
        exports = self.run / "downloads" if self.offscreen else LAB / "runs/exports"
        exports.mkdir(parents=True, exist_ok=True)
        if not self.offscreen:
            path, _ = QFileDialog.getSaveFileName(self.window.window(), self.presentation.text("Save Studio export"), str(exports / name))
            return path
        if self.test_control().get("hold_picker"):
            loop = QEventLoop()
            check = QTimer()
            check.setInterval(50)
            check.timeout.connect(lambda: loop.quit() if self.stopped or self.test_control().get("release_picker") else None)
            check.start()
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            check.stop()
        path = exports / ("blocked" if decision == "fail" else name)
        if decision == "fail":
            path.mkdir(exist_ok=True)
        return str(path)

    def shutdown(self):
        """Irreversible owned-widget cleanup; no backend termination or application quit."""
        if self.stopped:
            return
        self._committing = None
        self.cancel_close()
        self.stopped = True
        self.ready = False
        self._native_request = False
        self.generation += 1
        self.timer.stop()
        self.readyChanged.emit(False)
        for item in list(self.pending_downloads.values()):
            item.cancel()
        self.pending_downloads.clear()
        for item in (self.page, self.view, self.profile, self.window):
            if isValid(item):
                delete(item)
