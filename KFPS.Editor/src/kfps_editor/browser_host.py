"""Optional browser display; file ownership and save/close stay in EditorDesktop."""
import ctypes
from ctypes import wintypes
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget

from .browser_page import BrowserPage, window_for_process
from .host import EditorDesktop
from .bootstrap_log import record_startup


class BrowserDesktop(EditorDesktop):
    def _create_page(self):
        # A hidden, non-rendering placeholder preserves the host's error/retry UI.
        self.view = QWidget(self)
        self.stack.addWidget(self.view)
        self.page = BrowserPage(self.runtime, self.url, self.system_language, self)
        self.page.commandResult.connect(self._command_result)
        self.page.commandProgress.connect(self._command_progress)
        self.page.loadFinished.connect(self._loaded)
        self.page.loadStarted.connect(self._page_load_started)
        self.page.renderProcessTerminated.connect(self._renderer_stopped)
        self.page.closeRequested.connect(self._request_browser_close)
        self.page.closed.connect(self._browser_closed)
        self.page.start(background=self._background, width=self.width(), height=self.height())
        QApplication.instance().setQuitOnLastWindowClosed(False)

    def present_window(self, *, background=False):
        focused = self.page.present(background=background) if self.page else False
        record_startup(self.runtime, "window-presented", focused=focused, background=background, browser=True)

    def _request_browser_close(self):
        self.present_window(background=self._background)
        self.close()

    def _message_box(self, *args, **kwargs):
        # Keep an in-page Save As prompt reachable after the native question.
        # Restoring a minimized browser also resumes its animation-frame work.
        self.present_window(background=self._background)
        try:
            return super()._message_box(*args, **kwargs)
        finally:
            self.present_window(background=self._background)

    def _diagnostic_tick(self):
        if self._stopped or not self.server or not self.page:
            return
        now = time.monotonic()
        hwnd = window_for_process(self.page.process.pid) if self.page.process else None
        user = ctypes.WinDLL("user32")
        user.IsIconic.argtypes = [wintypes.HWND]
        user.GetForegroundWindow.restype = wintypes.HWND
        minimized = bool(hwnd and user.IsIconic(hwnd))
        visible = bool(hwnd and not minimized)
        diagnostics = self.server.diagnostics()
        diagnostics.native_tick(ready=self._ready, visible=visible, minimized=minimized,
            focused=bool(hwnd and user.GetForegroundWindow() == hwnd),
            uiLag=max(0, (now-self._last_diagnostic_tick)*1000-2000),
            rendererPid=self.page.renderProcessPid())
        self._last_diagnostic_tick = now
        received = diagnostics.snapshot().get("page_received", 0)
        stale = self._ready and visible and (not received or time.time()-received > 10)
        if stale and not self._heartbeat_stale:
            diagnostics.record("heartbeat-stale", source="native")
        self._heartbeat_stale = stale

    def _browser_closed(self):
        if self._stopped:
            return
        # A user-initiated close with a live, activated document goes through
        # beforeunload and the existing Save/Discard/Cancel protocol first.
        # Process loss still retains the normal browser and disk recovery data.
        record_startup(self.runtime, "browser-disconnected")
        self._allow_close = True
        self.close()

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            QTimer.singleShot(0, QApplication.instance().quit)

    def _show_failure(self, message):
        super()._show_failure(message)
        if not self._background:
            self.show()

    def reload_editor(self):
        if self.page and self.page.disconnected:
            self._allow_close = True
            self.close()
            return
        super().reload_editor()

    def shutdown(self):
        page = self.page
        if page is not None and not self._stopped:
            try:
                page.dispose()
            except Exception as error:
                # Keep server/instance ownership while a writer may still exist.
                record_startup(self.runtime, "shutdown-error", phase="browser-stop", error=type(error).__name__)
                return False
        return super().shutdown()
