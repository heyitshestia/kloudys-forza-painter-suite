"""Thin native Windows Studio host; the existing authenticated backend remains separate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_window import LAB, validate_window_url


NATIVE_CATALOG = LAB / "src/web/locales/messages.json"
MAX_NATIVE_CATALOG_BYTES = 1024 * 1024
READINESS_SCRIPT = """(() => {
    const language = document.documentElement.lang;
    return JSON.stringify({ready:!!window.__liveryLab?.ready,
        document:window.__kfpsStudioNativeDocument,
        language:['en','ko','ja'].includes(language) ? language : 'en'});
})()"""


class NativePresentation:
    """Reuse Studio's catalog; the page supplies only its allowlisted locale."""

    def __init__(self):
        self.language = "en"
        self._messages = {}
        try:
            with NATIVE_CATALOG.open("rb") as source:
                raw = source.read(MAX_NATIVE_CATALOG_BYTES + 1)
            catalog = json.loads(raw) if len(raw) <= MAX_NATIVE_CATALOG_BYTES else None
            if isinstance(catalog, dict):
                for key in ("Save Studio export", "A file is still being saved. Close again after it finishes."):
                    row = catalog.get(key)
                    if (isinstance(row, list) and len(row) == 2
                            and all(isinstance(value, str) and 0 < len(value) <= 512
                                    and value.strip() and not any(ord(c) < 32 or ord(c) == 127 for c in value)
                                    for value in row)):
                        self._messages[key] = tuple(row)
        except (OSError, ValueError, RecursionError):
            pass  # An unavailable translation must never block saving or closing.

    def set_language(self, language):
        self.language = language if isinstance(language, str) and language in ("en", "ko", "ja") else "en"

    def text(self, source):
        row = self._messages.get(source)
        return row[0 if self.language == "ko" else 1] if row and self.language != "en" else source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--auto-close", type=float, default=0)
    parser.add_argument("--test-control", action="store_true")
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((LAB / "runs").resolve()) or run == (LAB / "runs").resolve():
        raise ValueError("Invalid native host run directory.")
    validate_window_url(args.url)
    origin = urlsplit(args.url)
    run.mkdir(parents=True, exist_ok=True)

    def test_control():
        if not (args.offscreen and args.test_control):
            return {}
        try:
            with (run / "control.json").open("rb") as source:
                body = source.read(4097)
            value = json.loads(body) if len(body) <= 4096 else {}
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def test_event(kind, **data):
        if args.offscreen and args.test_control:
            with (run / "events.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps(dict(kind=kind, **data)) + "\n")

    def record(status, **data):
        temporary = run / "host.tmp"
        temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), **data)), encoding="utf-8")
        temporary.replace(run / "host.json")

    try:
        # Reuse the exact 2D renderer policy, not its editor URL/security/startup path.
        root = args.root.resolve()
        sys.path.insert(0, str(root / "KFPS.Editor/src"))
        from kfps_editor import graphics, baseline
        baseline.verify_import_origins(root / "python")
        selection = graphics.select_policy(root)
        graphics.configure_environment(os.environ, selection)
        diagnostics = graphics.configure_qt(selection)
        from PySide6.QtCore import QTimer, QUrl, Qt, QEventLoop
        from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebEngineScript, QWebEngineDownloadRequest
        from PySide6.QtWebEngineWidgets import QWebEngineView

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(["KFPS Livery Studio"])
        app.setOrganizationName("KFPS")
        app.setApplicationName("Livery Studio")
        presentation = NativePresentation()

        def local(url):
            try:
                parsed = urlsplit(url)
                return parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == origin.port and not parsed.username and not parsed.password
            except ValueError:
                return False

        class Requests(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info):
                url = info.requestUrl().toString()
                if not local(url) and not url.startswith("data:") and not (url.startswith("blob:") and local(url[5:])):
                    info.block(True)

        class Page(QWebEnginePage):
            def acceptNavigationRequest(self, url, navigation_type, main_frame):
                if not local(url.toString()):
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
                if args.offscreen:
                    accepted = test_control().get("confirm") is True
                    test_event("confirm", accepted=accepted)
                else:
                    accepted = super().javaScriptConfirm(security_origin, message)
                if not accepted:
                    window.closing = False
                return accepted

            def javaScriptConsoleMessage(self, level, message, line, source):
                # Do not log bearer URLs, document content or personal local filenames.
                if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    print(f"Studio JavaScript error at line {line}", flush=True)

        class Window(QMainWindow):
            allow_close = False
            closing = False

            def closeEvent(self, event):
                if self.allow_close:
                    event.accept()
                    return
                event.ignore()
                if self.closing:
                    return
                if pending_downloads:
                    window.statusBar().showMessage(presentation.text("A file is still being saved. Close again after it finishes."), 5000)
                    test_event("close_waits_for_downloads")
                    return
                # Chromium's beforeunload confirmation protects unsaved Studio edits.
                # RequestClose emits windowCloseRequested only after the user accepts.
                self.closing = True
                page.triggerAction(QWebEnginePage.WebAction.RequestClose)

        window = Window()
        window.setWindowTitle("KFPS Livery Studio")
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, args.offscreen)
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, args.offscreen)
        profile = QWebEngineProfile("studio", window)
        profile.setPersistentStoragePath(str(run / "profile"))
        profile.setCachePath(str(run / "cache"))
        profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        interceptor = Requests(profile)
        profile.setUrlRequestInterceptor(interceptor)
        view = QWebEngineView(window)
        page = Page(profile, view)
        view.setPage(page)
        marker = QWebEngineScript()
        marker.setName("kfps-studio-native-downloads")
        marker.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        marker.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        marker.setRunsOnSubFrames(False)
        diagnostic_policy = selection.backend if selection.backend in ("auto", "opengl", "d3d11") else "unknown"
        marker.setSourceCode("window.__kfpsStudioNativeDownloads = true; window.__kfpsStudioNativeDocument = crypto.randomUUID();"
                             + "window.__kfpsStudioDiagnosticPolicy = " + json.dumps(diagnostic_policy) + ";")
        page.scripts().insert(marker)
        window.setCentralWidget(view)
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        page.fullScreenRequested.connect(lambda request: (request.accept(), window.showFullScreen() if request.toggleOn() else window.showNormal()))
        page.featurePermissionRequested.connect(lambda url, feature: page.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
        area = app.primaryScreen().availableGeometry()
        window.resize(1760 if args.offscreen else min(1760, area.width()),
                      1040 if args.offscreen else min(1040, area.height()))
        if args.offscreen:
            view.resize(1760, 1040)  # Exercise a sized page without displaying a native window.
            window.show()
            page.setVisible(True)

        generation = 0
        native_document = ""
        pending_downloads = {}

        def navigating():
            nonlocal generation, native_document, ready, started
            generation += 1
            native_document = ""
            presentation.set_language("en")
            ready = False
            started = time.monotonic()
            timer.start()

        page.loadStarted.connect(navigating)

        def download(item):
            url = item.url().toString()
            if item.page() != page or not url.startswith(f"blob:http://127.0.0.1:{origin.port}/"):
                item.cancel()
                return
            captured = generation
            identifier = item.id()
            document = native_document
            completed = False

            def deliver(status, message, current_document):
                if captured != generation or not isinstance(current_document, str) or not current_document:
                    return
                payload = json.dumps({"status": status, "message": message})
                page.runJavaScript(f"if(window.__kfpsStudioNativeDocument === {json.dumps(current_document)}) window.__kfpsStudioDownloadFinished?.({json.dumps(url)}, {payload});")

            def finished(status, message=""):
                nonlocal completed
                if completed:
                    return
                completed = True
                pending_downloads.pop(identifier, None)
                test_event("download", status=status)
                if captured == generation:
                    if document:
                        deliver(status, message, document)
                    else:
                        # Early download before readiness cached the document ID:
                        # cancel synchronously, then settle only this exact document.
                        page.runJavaScript("window.__kfpsStudioNativeDocument", lambda value: deliver(status, message, value))

            def state_changed(state):
                if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                    finished("completed")
                elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
                    finished("cancelled")
                elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
                    finished("failed", "The file could not be saved. Choose a writable location and try again.")

            try:
                item.stateChanged.connect(state_changed)
                if len(pending_downloads) >= 16:
                    finished("failed", "Too many files are being saved. Wait for them to finish and try again.")
                    item.cancel()
                    return
                pending_downloads[identifier] = item
                if not document:
                    finished("cancelled")
                    item.cancel()
                    return
                decision = test_control().get("download") if args.offscreen else None
                if args.offscreen and decision not in ("save", "fail"):
                    item.cancel()
                    finished("cancelled")
                    return
                name = Path(item.suggestedFileName().replace("\\", "/")).name or "studio-export.json"
                exports = run / "downloads" if args.offscreen else LAB / "runs/exports"
                exports.mkdir(parents=True, exist_ok=True)
                if args.offscreen:
                    if test_control().get("hold_picker"):
                        # Test-only analogue of the chooser's nested event loop.
                        # Keep the real Qt request outstanding while close is tried.
                        loop = QEventLoop()
                        check = QTimer()
                        check.setInterval(50)
                        check.timeout.connect(lambda: loop.quit() if test_control().get("release_picker") else None)
                        check.start()
                        QTimer.singleShot(10000, loop.quit)
                        loop.exec()
                        check.stop()
                    path = str(exports / ("blocked" if decision == "fail" else name))
                    if decision == "fail":
                        Path(path).mkdir(exist_ok=True)
                else:
                    path, _ = QFileDialog.getSaveFileName(window, presentation.text("Save Studio export"), str(exports / name))
                if not path:
                    item.cancel()
                    finished("cancelled")
                    return
                item.setDownloadDirectory(str(Path(path).parent))
                item.setDownloadFileName(Path(path).name)
                item.accept()
                if args.offscreen and test_control().get("pause_download"):
                    item.pause()
            except Exception:
                finished("failed", "The save destination could not be opened. Choose a writable location and try again.")
                item.cancel()

        profile.downloadRequested.connect(download)

        def close_accepted():
            if pending_downloads:
                window.closing = False
                test_event("close_waits_for_downloads")
                return
            window.allow_close = True
            window.close()
            app.quit()

        page.windowCloseRequested.connect(close_accepted)
        page.renderProcessTerminated.connect(lambda *_: (record("failed", error="Studio web renderer stopped."), app.exit(1)))
        started = time.monotonic()
        ready = False

        def result(value):
            nonlocal ready, native_document
            if not isinstance(value, str) or len(value) > 4096:
                return
            try:
                data = json.loads(value)
            except ValueError:
                return
            if not isinstance(data, dict) or not data.get("document"):
                return
            native_document = data["document"]
            presentation.set_language(data.get("language"))
            if ready or not data.get("ready"):
                return
            ready = True
            timer.stop()
            record("ready", graphics=diagnostics, engine=baseline.engine_identity(), offscreen=args.offscreen)
            if not args.offscreen:
                window.show()
            if args.auto_close and args.offscreen:
                QTimer.singleShot(int(args.auto_close * 1000), close_accepted)

        def poll():
            if not ready and time.monotonic() - started > 55:
                record("failed", error="Studio page did not finish loading.")
                app.exit(1)
                return
            captured = generation
            page.runJavaScript(READINESS_SCRIPT,
                               lambda value: result(value) if captured == generation else None)

        timer = QTimer(window)
        timer.setInterval(200)
        timer.timeout.connect(poll)
        timer.start()
        control_timer = QTimer(window)
        if args.offscreen and args.test_control:
            def controlled_close():
                control = test_control()
                if control.get("resume_download"):
                    for item in list(pending_downloads.values()): item.resume()
                command = control.get("close")
                if command and command != getattr(controlled_close, "last", None):
                    controlled_close.last = command
                    window.close()
            control_timer.setInterval(200)
            control_timer.timeout.connect(controlled_close)
            control_timer.start()
        view.load(QUrl(args.url))
        code = app.exec()
        # Destroy the page before its profile; no backend lifecycle is coupled to this window.
        from shiboken6 import delete
        timer.stop()
        control_timer.stop()
        for item in list(pending_downloads.values()): item.cancel()
        delete(page)
        delete(view)
        delete(profile)
        delete(window)
        if code == 0:
            record("closed", graphics=diagnostics, offscreen=args.offscreen)
        return code
    except Exception as exc:
        record("failed", error=f"Native Studio startup failed ({type(exc).__name__}).")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
