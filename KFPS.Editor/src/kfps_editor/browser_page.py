"""Page bridge for one KFPS-owned Google Chrome profile, never personal tabs."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QEventLoop, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebSockets import QWebSocket

from .launch_preferences import find_chrome


def browser_executable():
    path = find_chrome()
    if path is not None:
        return path
    raise RuntimeError("Google Chrome was not found. Install Google Chrome, or turn off 'Use Google Chrome for editor' in KFPS Settings. / Google Chrome을 찾을 수 없습니다. Chrome을 설치하거나 KFPS 설정에서 'Use Google Chrome for editor'를 꺼 주세요.")


def allowed_request(url, origin, document=False):
    if document:
        parsed = urlsplit(url)
        return url == "about:blank" or (f"{parsed.scheme}://{parsed.netloc}" == origin
                and parsed.path == "/tools/fabric-editor/index.html")
    return url.startswith(origin + "/") or url.startswith("blob:" + origin + "/") or url.startswith("data:")


class OwnedBrowserProcess:
    """Assign the suspended browser to its job before it can spawn children."""
    def __init__(self, flags, job):
        import win32api
        import win32con
        import win32job
        import win32process
        self.code = None
        self.handle, thread, self.pid, _ = win32process.CreateProcess(
            None, subprocess.list2cmdline(flags), None, None, False,
            win32con.CREATE_SUSPENDED | subprocess.CREATE_NO_WINDOW,
            None, None, win32process.STARTUPINFO())
        try:
            win32job.AssignProcessToJobObject(job, self.handle)
            win32process.ResumeThread(thread)
        except Exception:
            win32api.TerminateProcess(self.handle, 1)
            self.wait(5)
            raise
        finally:
            thread.Close()

    def poll(self):
        import win32event
        import win32process
        if self.handle and win32event.WaitForSingleObject(self.handle, 0) == 0:
            self.code = win32process.GetExitCodeProcess(self.handle)
            self.handle.Close()
            self.handle = None
        return self.code

    def wait(self, timeout):
        import win32event
        if self.handle and win32event.WaitForSingleObject(self.handle, int(timeout*1000)) == 258:
            raise subprocess.TimeoutExpired("KFPS browser", timeout)
        return self.poll()

    def terminate(self):
        import win32api
        if self.poll() is None:
            win32api.TerminateProcess(self.handle, 1)

    kill = terminate


def window_for_process(pid):
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    windows = []
    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(hwnd):
            name = ctypes.create_unicode_buffer(128)
            user.GetClassNameW(hwnd, name, len(name))
            # Owned popups/tooltips also use Chrome_WidgetWin classes; they are
            # not additional editor windows and must not defeat focus/cleanup.
            if (name.value.startswith("Chrome_WidgetWin_") and not user.GetWindow(hwnd, 4)
                    and not user.GetWindowLongW(hwnd, -20) & 0x80):
                windows.append(int(hwnd))
        return True
    user.EnumWindows(visit, 0)
    return windows[0] if len(windows) == 1 else None


class BrowserPage(QObject):
    loadStarted = Signal()
    loadFinished = Signal(bool)
    titleChanged = Signal(str)
    renderProcessTerminated = Signal(object, int)
    commandResult = Signal(str, str)
    commandProgress = Signal(str, str)
    closeRequested = Signal()
    closed = Signal()

    def __init__(self, runtime, origin, language, parent=None):
        super().__init__(parent)
        self.profile = Path(runtime) / "browser-profile"
        self.origin = origin.toString().split("/tools/", 1)[0]
        self.language = language
        self.socket = QWebSocket(parent=self)
        self.socket.textMessageReceived.connect(self._message)
        self.socket.disconnected.connect(self._disconnected)
        self.pending = {}
        self.sequence = 0
        self.target = self.session_id = None
        self.process = self.job = None
        self.created = None
        self.disposing = False
        self.disposed = False
        self.disconnected = False
        self.navigating = False
        self.assigned = False
        self.renderer_pid = 0
        self.log = parent.server.diagnostics()

    def call(self, method, params=None, callback=None, *, page=True):
        if self.socket.state().name != "ConnectedState":
            if callback:
                callback({"error": {"message": "Browser disconnected"}})
            return None
        self.sequence += 1
        identifier = self.sequence
        packet = {"id": identifier, "method": method, "params": params or {}}
        if page and self.session_id:
            packet["sessionId"] = self.session_id
        if callback:
            self.pending[identifier] = callback
        self.socket.sendTextMessage(json.dumps(packet))
        return identifier

    def sync(self, method, params=None, *, page=True, timeout=5000):
        loop, result = QEventLoop(), []
        def completed(data):
            result.append(data)
            loop.quit()
        identifier = self.call(method, params, completed, page=page)
        if not result:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(timeout)
            loop.exec()
            timer.stop()
        self.pending.pop(identifier, None)
        if not result or "error" in result[0]:
            raise RuntimeError("Browser command failed: " + method)
        return result[0].get("result", {})

    def _message(self, text):
        try:
            data = json.loads(text)
        except ValueError:
            return
        if "id" in data:
            callback = self.pending.pop(data["id"], None)
            if callback:
                callback(data)
            return
        method, p = data.get("method"), data.get("params", {})
        if method == "Fetch.requestPaused":
            allowed = allowed_request(p["request"]["url"], self.origin, p.get("resourceType") == "Document")
            self.call("Fetch.continueRequest" if allowed else "Fetch.failRequest",
                      {"requestId": p["requestId"], **({} if allowed else {"errorReason": "BlockedByClient"})})
        elif method == "Runtime.bindingCalled" and p.get("name") == "kfpsEditorBridge":
            try:
                envelope = json.loads(p.get("payload", ""))
                if envelope.get("operation") == "external":
                    target = QUrl(str(envelope.get("url", "")))
                    if target.isValid() and target.scheme() in ("http", "https") and not target.userInfo():
                        QDesktopServices.openUrl(target)
                    return
                identifier, value = envelope["id"], envelope["value"]
                if not isinstance(identifier, str) or len(identifier) > 64 or not isinstance(value, str) or len(value) > 16384:
                    return
                if envelope.get("operation") == "result":
                    self.commandResult.emit(identifier, value)
                elif envelope.get("operation") == "progress" and value in ("working", "user-wait"):
                    self.commandProgress.emit(identifier, value)
            except (ValueError, TypeError, KeyError):
                pass
        elif method == "Page.loadEventFired":
            self.navigating = False
            self.loadFinished.emit(True)
            self.runJavaScript("document.title", lambda title: self.titleChanged.emit(str(title or "KFPS Vinyl Editor")))
            self.call("SystemInfo.getProcessInfo", callback=self._process_info, page=False)
        elif method == "Page.javascriptDialogOpening" and p.get("type") == "beforeunload":
            if self.navigating:
                self.call("Page.handleJavaScriptDialog", {"accept": True})
                return
            # Cancel Chromium's unload first, then use the existing KFPS save /
            # recovery handshake. The page remains alive while a user decides.
            self.call("Page.handleJavaScriptDialog", {"accept": False},
                      lambda _: QTimer.singleShot(0, self.closeRequested.emit))
        elif method == "Inspector.targetCrashed":
            self.renderProcessTerminated.emit(None, -1)
        elif method == "Target.targetDestroyed" and p.get("targetId") == self.target:
            # Chromium can close an untouched page without a beforeunload
            # dialog and keep its debugging process alive with no windows.
            if not self.disposing:
                self.closed.emit()
        elif method == "Target.targetCreated" and self.target:
            target = p.get("targetInfo", {})
            if target.get("type") == "page" and target.get("targetId") != self.target:
                self.call("Target.closeTarget", {"targetId": target["targetId"]}, page=False)

    def start(self, *, background=False, width=1440, height=900):
        import psutil
        import win32job
        browser = browser_executable()
        self.profile.mkdir(parents=True, exist_ok=True)
        marker = self.profile / "kfps-owner.json"
        try:
            owner = json.loads(marker.read_text())
            previous = psutil.Process(owner["pid"])
            if abs(previous.create_time()-owner["created"]) < .01:
                raise RuntimeError("Close the previous KFPS browser editor before reopening it. / 이전 KFPS 브라우저 에디터 창을 닫은 뒤 다시 실행해 주세요.")
        except (OSError, ValueError, KeyError, psutil.Error):
            pass
        preferences = self.profile / "Default" / "Preferences"
        if not preferences.exists():
            preferences.parent.mkdir(exist_ok=True)
            preferences.write_text(json.dumps({"download": {"prompt_for_download": True}}))
        port_file = self.profile / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        self.job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, limits)
        # Chromium app mode does not reliably accept about:blank: recent Chrome
        # opens its New Tab page instead. Use an inert local endpoint, then load
        # the editor only after installing the desktop bridge and request guard.
        startup_url = self.origin + "/api/fabric-editor/health"
        flags = [str(browser), "--user-data-dir="+str(self.profile), "--remote-debugging-port=0",
                 "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
                 "--disable-extensions", "--disable-sync", "--disable-background-networking",
                 "--disable-component-update", "--disable-default-apps",
                 f"--window-size={width},{height}", "--no-startup-window" if background else "--app="+startup_url]
        self.process = OwnedBrowserProcess(flags, self.job)
        self.created = psutil.Process(self.process.pid).create_time()
        self.assigned = True
        marker.write_text(json.dumps({"pid": self.process.pid, "created": self.created}))
        end = time.monotonic()+15
        while not port_file.is_file() and time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError("Isolated browser exited during startup")
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        lines = port_file.read_text().splitlines()
        if len(lines) != 2 or not lines[0].isdigit() or not lines[1].startswith("/devtools/browser/"):
            raise RuntimeError("Invalid isolated browser endpoint")
        loop = QEventLoop()
        self.socket.connected.connect(loop.quit)
        self.socket.open(QUrl(f"ws://127.0.0.1:{int(lines[0])}{lines[1]}"))
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        loop.exec()
        timer.stop()
        self.socket.connected.disconnect(loop.quit)
        version = self.sync("Browser.getVersion", page=False)
        from .bootstrap_log import record_startup
        record_startup(self.parent().runtime, "browser-start", browser=version.get("product"), isolated=True)
        end = time.monotonic() + 5
        while True:
            targets = self.sync("Target.getTargets", page=False)["targetInfos"]
            pages = [p for p in targets if p["type"] == "page"]
            if background or (len(pages) == 1 and pages[0]["url"] == startup_url):
                break
            if time.monotonic() >= end or self.process.poll() is not None:
                record_startup(self.parent().runtime, "browser-startup-rejected",
                    pages=[{"scheme": urlsplit(p.get("url", "")).scheme,
                            "path": urlsplit(p.get("url", "")).path} for p in pages])
                raise RuntimeError("The isolated KFPS browser did not open its local startup page")
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        if pages:
            if len(pages) != 1 or pages[0]["url"] != ("about:blank" if background else startup_url):
                raise RuntimeError("Unexpected page in the isolated KFPS browser")
            self.target = pages[0]["targetId"]
        else:
            self.target = self.sync("Target.createTarget", {"url": "about:blank", "newWindow": True,
                        "background": background, "width": width, "height": height}, page=False)["targetId"]
        self.session_id = self.sync("Target.attachToTarget", {"targetId": self.target, "flatten": True}, page=False)["sessionId"]
        self.sync("Page.stopLoading")
        self.sync("Runtime.enable")
        self.sync("Page.enable")
        self.sync("Runtime.addBinding", {"name": "kfpsEditorBridge"})
        script = "window.KfpsEditorSystemLanguage = " + json.dumps(self.language) + ";\n" + """
window.KfpsDesktopBridge = Object.freeze({
 completed(id, value) { kfpsEditorBridge(JSON.stringify({operation:'result', id, value})); },
 progress(id, value) { kfpsEditorBridge(JSON.stringify({operation:'progress', id, value})); }
});
window.addEventListener('beforeunload', event => {
 if (window.__KfpsBrowserCloseAllowed) { event.stopImmediatePropagation(); return; }
 event.preventDefault(); event.returnValue = '';
}, {capture:true});
window.addEventListener('keydown', event => {
 if (event.key === 'F5' || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'r')) event.preventDefault();
}, {capture:true});
window.addEventListener('click', event => {
 const anchor = event.target.closest?.('a[href]');
 if (!anchor) return;
 const url = new URL(anchor.href, location.href);
 if ((url.protocol === 'https:' || url.protocol === 'http:') && url.origin !== location.origin) {
   event.preventDefault();
   if (event.isTrusted) kfpsEditorBridge(JSON.stringify({operation:'external',url:url.href}));
 }
}, {capture:true});
"""
        self.sync("Page.addScriptToEvaluateOnNewDocument", {"source": script})
        self.sync("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
        self.sync("Target.setDiscoverTargets", {"discover": True}, page=False)
        if background:
            self.present(background=True)

    def load(self, url):
        if not allowed_request(url.toString(), self.origin, document=True):
            raise ValueError("Editor navigation is outside its local session")
        self.navigating = True
        self.loadStarted.emit()
        self.call("Page.navigate", {"url": url.toString()},
                  lambda r: self.loadFinished.emit(False) if "error" in r or r.get("result", {}).get("errorText") else None)

    def runJavaScript(self, expression, callback=None):
        if callback is None:
            expression = "(function(){" + expression + "\n})()"
        def completed(data):
            if "error" in data or data.get("result", {}).get("exceptionDetails"):
                self.log.record("console-error", source="native", error="Error")
            if callback:
                callback(data.get("result", {}).get("result", {}).get("value"))
        self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True}, completed)

    def renderProcessPid(self):
        return self.renderer_pid if self.process and self.process.poll() is None else 0

    def _process_info(self, reply):
        renderers = [int(p["id"]) for p in reply.get("result", {}).get("processInfo", [])
                     if p.get("type") == "renderer"]
        self.renderer_pid = renderers[0] if len(renderers) == 1 else 0

    def triggerAction(self, _action):
        self.call("Page.stopLoading")

    def present(self, *, background=False):
        hwnd = window_for_process(self.process.pid) if self.process and self.process.poll() is None else None
        if not hwnd:
            return False
        user = ctypes.WinDLL("user32")
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [wintypes.HWND]
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        if background:
            user.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0010 | 0x0001 | 0x0002)
            return False
        from .activation import grant_foreground
        grant_foreground(self.process.pid)
        user.ShowWindow(hwnd, 9)
        return bool(user.SetForegroundWindow(hwnd))

    def _disconnected(self):
        self.disconnected = True
        pending, self.pending = self.pending, {}
        for callback in pending.values():
            callback({"error": {"message": "Browser disconnected"}})
        if not self.disposing:
            self.closed.emit()

    def dispose(self):
        if self.disposed:
            return
        self.disposing = True
        if self.socket.state().name == "ConnectedState":
            try:
                self.sync("Runtime.evaluate", {"expression": "window.__KfpsBrowserCloseAllowed=true"}, timeout=1000)
            except RuntimeError:
                pass
            self.call("Browser.close", page=False)
            self.socket.flush()
        end = time.monotonic()+2
        while self.process and self.process.poll() is None and time.monotonic() < end:
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
        self.socket.close()
        if self.job:
            self.job.Close()
            self.job = None
        if self.process and not self.assigned and self.process.poll() is None:
            # Job assignment can fail during startup. This handle is exclusively
            # the process just created above, not a browser found by its name.
            self.process.terminate()
        if self.process:
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                # Never fall back to killing a browser by name or profile search.
                raise RuntimeError("The owned browser did not stop")
        self.disposed = True
