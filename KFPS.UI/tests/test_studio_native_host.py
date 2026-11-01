"""Real offscreen Qt host contracts; all state stays in the selected workspace run."""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import trace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _test_evidence import evidence_directory

ROOT = Path(__file__).resolve().parents[2]
RUN = evidence_directory("studio-host-20261026", "KFPS_STUDIO_HOST_TEST_RUN")
RUN.mkdir(parents=True, exist_ok=True)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
for key, folder in (("TEMP", "temp"), ("TMP", "temp"), ("APPDATA", "appdata"),
                    ("LOCALAPPDATA", "localappdata"), ("XDG_CACHE_HOME", "cache")):
    location = RUN / folder
    location.mkdir(exist_ok=True)
    os.environ[key] = str(location)
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))

if "--standalone-child" in sys.argv:
    from kfps_livery_lab import native_host, studio_window
    studio_window.LAB = Path(os.environ.get("KFPS_STUDIO_OWNER_TEST_ROOT", RUN))
    native_host.LAB = RUN / "standalone"
    url = sys.argv[sys.argv.index("--standalone-child") + 1]
    sys.argv = [str(Path(native_host.__file__)), "--root", str(ROOT), "--url", url,
                "--run", str(native_host.LAB / "runs/session"), "--offscreen", "--auto-close", ".2",
                "--test-control"]
    raise SystemExit(native_host.main())

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow
from PySide6.QtWebEngineCore import QWebEnginePage
from shiboken6 import isValid

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
TOKEN_PATH = "/" + "a" * 43 + "/"
PAGE = b"""<!doctype html><html lang="en"><body>
<button style="width:180px;height:60px" onclick="window.dirty=true; edits++">Edit</button>
<script>
window.dirty=false; window.edits=0; window.hideCount=0; window.downloadResults=[];
window.__liveryLab={ready:true,getProject:()=>({edits})};
window.addEventListener('beforeunload',event=>{
  if(window.dirty){event.preventDefault();event.returnValue='';}
});
window.addEventListener('pagehide',()=>{hideCount++;window.__liveryLab.ready=false;});
window.__kfpsStudioDownloadFinished=(url,result)=>downloadResults.push(result);
window.exportBlob=()=>{const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob(['studio-fixture-bytes'],{type:'application/json'}));
  a.download='layout.json';a.click();return a.href;};
</script></body></html>"""


def pump_until(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("Timed out waiting for offscreen host condition")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


class StudioHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from kfps_livery_lab.studio_host import StudioHost
        cls.Host = StudioHost
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}{TOKEN_PATH}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(2)

    def setUp(self):
        from kfps_livery_lab import studio_window
        self.owner_path_patch = patch.object(studio_window, "LAB", RUN)
        self.owner_path_patch.start()
        self.addCleanup(self.owner_path_patch.stop)
        self.output = RUN / self._testMethodName
        self.output.mkdir(exist_ok=True)
        self.controls = {}
        self.events = []
        self.graphics_api = QQuickWindow.graphicsApi()
        self.parent = QMainWindow()
        self.parent.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.parent.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.addCleanup(self.parent.deleteLater)
        self.host = self.Host(self.url, self.output, parent=self.parent,
                              offscreen=True, test_control=lambda: dict(self.controls),
                              test_event=lambda kind, **data: self.events.append({"kind": kind, **data}))
        self.addCleanup(self.host.shutdown)
        self.assertFalse(self.host.window.isVisible())
        self.parent.setCentralWidget(self.host.window)
        self.parent.resize(640, 480)
        self.parent.show()
        self.host.page.setVisible(True)
        pump_until(lambda: self.host.ready)
        self.assert_no_foreground()
        self.dialog_patch = patch.object(QFileDialog, "getSaveFileName",
                                         side_effect=AssertionError("Unexpected native file dialog"))
        self.dialog_patch.start()
        self.addCleanup(self.dialog_patch.stop)

    def tearDown(self):
        self.assert_no_foreground()
        (self.output / "events.json").write_text(json.dumps(self.events, indent=2), encoding="utf-8")

    def assert_no_foreground(self):
        if os.name == "nt":
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = ctypes.c_void_p
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(ctypes.c_void_p(user32.GetForegroundWindow()), ctypes.byref(pid))
            self.assertNotEqual(pid.value, os.getpid(), "Test process took foreground")

    def js(self, expression):
        values = []
        self.host.page.runJavaScript("JSON.stringify((" + expression + "))", values.append)
        pump_until(lambda: bool(values))
        return json.loads(values[0]) if values[0] else None

    def dirty(self):
        self.js("document.querySelector('button').click()")
        pump_until(lambda: self.js("window.dirty") is True)

    def prepare(self):
        answers = []
        self.host.prepare_close(answers.append)
        self.assertEqual(answers, [], "Close callback must be asynchronous")
        pump_until(lambda: bool(answers))
        return answers

    def test_constructor_does_not_reconfigure_application_or_show_itself(self):
        self.assertIs(QApplication.instance(), APP)
        self.assertFalse(self.host.window.isWindow())
        self.assertTrue(self.host.window.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen))
        self.assertEqual(QQuickWindow.graphicsApi(), self.graphics_api)
        self.assertFalse(APP.quitOnLastWindowClosed())

    def test_second_native_host_is_blocked_before_page_creation_with_dirty_first(self):
        from kfps_livery_lab.studio_window import NativeOwnerError
        self.dirty()
        before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]")
        for hosted in (True, False):
            for token in ("a", "b"):
                with self.subTest(hosted=hosted, token=token), self.assertRaises(NativeOwnerError):
                    self.Host(self.url.replace("a" * 43, token * 43), self.output / "blocked",
                              hosted=hosted, offscreen=True)
        self.assertFalse((self.output / "blocked").exists())
        self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]"), before)
        self.assertTrue(self.host._native_owner.isLocked())

    def test_shared_backend_guard_preserves_actual_token_and_dirty_native_document(self):
        import test_studio_preview_quality_routes as routes
        from kfps_livery_lab import host_bridge
        from kfps_livery_lab.studio_window import NativeOwnerError
        fixture = routes.PreviewQualityRouteTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        (fixture.web / "index.html").write_bytes(PAGE)
        self.host.shutdown()
        url = fixture.server.origin + fixture.prefix
        self.host = self.Host(url, self.output / "real-backend", hosted=False, offscreen=True)
        self.addCleanup(self.host.shutdown)
        pump_until(lambda: self.host.ready)
        self.dirty()
        before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]")
        token = fixture.server.token
        with self.assertRaises(NativeOwnerError):
            self.Host(url, self.output / "second", hosted=True, offscreen=True)
        ready = {"url": url, "host_layout_handoff": True, "reused": True,
                 "vehicle": fixture.prepared["editor_config"]["vehicle"]}
        with patch.object(host_bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: False)):
            with self.assertRaisesRegex(ValueError, "another open page"):
                host_bridge._check_package_target(ROOT, ready,
                    {"layout": {"vehicle": {"car_id": 3307, "model_code": "OTHER"}}})
        self.assertEqual(fixture.server.token, token)
        self.assertEqual(fixture.request("GET", "api/editor-config")[0], 200)
        self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]"), before)

    def test_second_owner_rejected_before_theme_mutation_but_own_host_is_admitted(self):
        from kfps_livery_lab import host_bridge, studio_window
        self.dirty()
        before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]")
        theme = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        ready = {"url": self.url, "reused": True, "host_theme_handoff": True}
        with patch.object(host_bridge.launcher, "ensure_ready", return_value=ready), \
                patch.object(host_bridge.launcher, "_window_module", return_value=studio_window), \
                patch.object(studio_window, "use_chrome", return_value=False), \
                patch.object(host_bridge, "_publish_theme") as publish:
            with self.assertRaises(studio_window.NativeOwnerError):
                host_bridge.launch_from_host(ROOT, {"ui_theme": theme})
            publish.assert_not_called()
            host_bridge.launch_from_host(ROOT, {"ui_theme": theme}, native_owner=self.host._native_owner)
            publish.assert_called_once()
        self.assertTrue(self.host._native_owner.isLocked())
        self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]"), before)

    @contextmanager
    def workspace(self):
        from PySide6.QtGui import QWindow
        from shiboken6 import delete
        sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
        sys.path.insert(0, str(ROOT / "tools/livery-studio/src/kfps_livery_lab"))
        from kfps_ui.workspace_host import WorkspaceWindow
        from kfps_ui.workspace_controller import WorkspaceController
        import studio_window as direct_window
        main = QWindow()
        shell = WorkspaceWindow(main, offscreen=True)
        root = self.output / "installation"
        owner = WorkspaceController(shell, SimpleNamespace(app_root=root, runtime_root=root / "runtime"), Mock(),
            SimpleNamespace(graphics=SimpleNamespace(backend="auto")))
        try:
            with patch.object(direct_window, "LAB", RUN), \
                    patch("kfps_ui.workspace_controller._studio_module_path",
                          return_value=ROOT / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"):
                yield owner
        finally:
            owner.close()
            shell.shutdown()
            delete(shell)
            delete(main)

    def test_standalone_then_workspace_install_preserves_dirty_first(self):
        self.host.shutdown()
        self.host = self.Host(self.url, self.output / "standalone-first", hosted=False, offscreen=True)
        self.addCleanup(self.host.shutdown)
        pump_until(lambda: self.host.ready)
        self.dirty()
        before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]")
        with self.workspace() as controller:
            pending = {"done": threading.Event(), "error": "", "result": {"url": self.url}}
            controller._install_studio(pending)
            self.assertTrue(pending["done"].is_set())
            self.assertIn("already open", pending["error"])
            self.assertNotIn("Studio", controller.shell.owners)
        self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]"), before)

    def test_workspace_then_real_standalone_process_rejects_without_touching_page(self):
        self.host.shutdown()
        with self.workspace() as controller:
            pending = {"done": threading.Event(), "error": "", "result": {"url": self.url}}
            controller._install_studio(pending)
            pump_until(lambda: pending["done"].is_set())
            self.assertEqual(pending["error"], "")
            self.host = controller.shell.owners["Studio"]
            self.dirty()
            before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]")
            environment = dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN=str(self.output),
                               KFPS_STUDIO_OWNER_TEST_ROOT=str(RUN))
            child = subprocess.run([str(ROOT / "python/python.exe"), "-I", "-B", str(Path(__file__)),
                    "--standalone-child", self.url], env=environment, cwd=self.output,
                    capture_output=True, text=True, timeout=25,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertNotEqual(child.returncode, 0)
            status = json.loads((self.output / "standalone/runs/session/host.json").read_text())
            self.assertEqual(status["status"], "failed")
            self.assertIn("already open", status["error"])
            self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument,location.href]"), before)

    def test_shutdown_releases_owner_only_after_page_destruction(self):
        from kfps_livery_lab.studio_window import acquire_native_owner
        lock, page = self.host._native_owner, self.host.page
        self.assertTrue(lock.isLocked())
        self.host.shutdown()
        self.host.shutdown()
        self.assertFalse(isValid(page))
        self.assertFalse(lock.isLocked())
        replacement = acquire_native_owner(self.url)
        self.addCleanup(replacement.unlock)

    def test_parent_destruction_retains_lease_until_page_is_gone(self):
        from shiboken6 import delete
        self.host.shutdown()
        parent = QMainWindow()
        parent.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        host = self.Host(self.url, self.output / "parent-owned", parent=parent, offscreen=True)
        lock, page = host._native_owner, host.page
        held = []
        parent.destroyed.connect(lambda: held.append(lock.isLocked()))
        delete(parent)
        self.assertEqual(held, [True])
        self.assertFalse(isValid(page))
        self.assertFalse(lock.isLocked())

    def test_constructor_failure_releases_owner(self):
        from kfps_livery_lab import studio_host
        self.host.shutdown()
        with patch.object(studio_host, "QWebEngineProfile", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.Host(self.url, self.output / "failed", offscreen=True)
        from kfps_livery_lab.studio_window import acquire_native_owner
        replacement = acquire_native_owner(self.url)
        self.addCleanup(replacement.unlock)

    def test_clean_prepare_is_non_destructive_and_cancel_restores_editing(self):
        document = self.js("window.__kfpsStudioNativeDocument")
        self.assertEqual(self.prepare(), [True])
        self.assertEqual(self.js("[hideCount,__liveryLab.ready,edits]"), [0, True, 0])
        self.assertTrue(isValid(self.host.page))
        self.host.cancel_close()
        self.assertFalse(self.host.commit_close())
        self.dirty()
        self.assertEqual(self.js("window.__kfpsStudioNativeDocument"), document)
        self.assertEqual(self.js("edits"), 1)

    def test_dirty_reject_then_accept_then_cancel_keeps_exact_document(self):
        self.dirty()
        self.controls["confirm"] = False
        self.assertEqual(self.prepare(), [False])
        self.assertTrue(any(event == {"kind": "confirm", "accepted": False} for event in self.events))
        self.controls["confirm"] = True
        self.assertEqual(self.prepare(), [True])
        self.assertEqual(self.js("[dirty,edits,hideCount,__liveryLab.ready]"), [True, 1, 0, True])
        self.host.cancel_close()
        self.dirty()
        self.assertEqual(self.js("edits"), 2)

    def test_cancel_before_native_reply_fences_late_approval(self):
        first, second = [], []
        callbacks = []
        state = json.dumps({"document": self.host.native_document, "dirty": False, "modal": False})
        with patch.object(self.host.page, "runJavaScript", side_effect=lambda _script, callback: callbacks.append(callback)):
            self.host.prepare_close(first.append)
            self.host.cancel_close()
            self.host.prepare_close(second.append)
            callbacks[0](state)
            pump_until(lambda: bool(first))
            self.assertEqual(first, [False])
            self.assertEqual(second, [])
            self.assertFalse(self.host.commit_close())
            callbacks[1](state)
            pump_until(lambda: bool(second))
            self.assertEqual(second, [True])
        self.host.cancel_close()
        self.assertEqual(self.prepare(), [True])

    def test_timeout_keeps_page_and_rejects_late_reply(self):
        answers = []
        callbacks = []
        with patch.object(self.host.page, "runJavaScript", side_effect=lambda _script, callback: callbacks.append(callback)):
            self.host.prepare_close(answers.append)
            self.host.close_timer.timeout.emit()
            pump_until(lambda: bool(answers))
            self.assertEqual(answers, [False])
            callbacks[0](json.dumps({"document": self.host.native_document, "dirty": False, "modal": False}))
            APP.processEvents()
            self.assertFalse(self.host.commit_close())
        self.assertTrue(self.js("__liveryLab.ready"))

    def test_cancel_after_approval_before_delivery_returns_false_once(self):
        answers = []
        callbacks = []
        with patch.object(self.host.page, "runJavaScript", side_effect=lambda _script, callback: callbacks.append(callback)):
            self.host.prepare_close(answers.append)
            callbacks[0](json.dumps({"document": self.host.native_document, "dirty": False, "modal": False}))
            self.host.cancel_close()
            pump_until(lambda: bool(answers))
        self.assertEqual(answers, [False])

    def test_navigation_invalidates_prepared_close(self):
        self.assertEqual(self.prepare(), [True])
        self.host.page.load(QUrl(self.url))
        pump_until(lambda: self.host.ready and self.host.generation >= 2)
        self.assertFalse(self.host.commit_close())

    def test_hosted_window_close_requests_shell_not_application_exit(self):
        requested = []
        self.host.closeRequested.connect(lambda: requested.append(True))
        with patch.object(APP, "quit") as quit_app, patch.object(APP, "exit") as exit_app:
            self.host.window.close()
            APP.processEvents()
            self.assertEqual(requested, [True])
            quit_app.assert_not_called()
            exit_app.assert_not_called()
            self.assertTrue(isValid(self.host.page))

    def test_renderer_failure_reports_without_quitting_or_destroying_other_owner(self):
        failures = []
        self.host.failed.connect(failures.append)
        with patch.object(APP, "quit") as quit_app, patch.object(APP, "exit") as exit_app:
            self.host.page.renderProcessTerminated.emit(QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus, 1)
            self.assertTrue(failures)
            self.assertFalse(self.host.ready)
            self.assertEqual(self.prepare(), [False])
            quit_app.assert_not_called()
            exit_app.assert_not_called()
        self.assertTrue(isValid(self.parent))

    def test_failed_host_requires_explicit_discard_then_releases_lease(self):
        from kfps_livery_lab.studio_window import acquire_native_owner
        self.dirty()
        before = self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument]")
        self.host._failure("injected transient failure")
        self.controls["confirm"] = False
        self.assertEqual(self.prepare(), [False])
        self.assertTrue(self.host._native_owner.isLocked())
        self.assertEqual(self.js("[dirty,edits,hideCount,__kfpsStudioNativeDocument]"), before)
        self.controls["confirm"] = True
        self.assertEqual(self.prepare(), [True])
        self.host.cancel_close()
        self.assertFalse(self.host.commit_close())
        self.assertTrue(isValid(self.host.page))
        self.assertEqual(self.prepare(), [True])
        closed = []
        self.host.closed.connect(lambda: closed.append(True))
        self.assertTrue(self.host.commit_close())
        self.assertEqual(closed, [True])
        self.assertFalse(isValid(self.host.page))
        lock = acquire_native_owner(self.url)
        self.addCleanup(lock.unlock)

    def test_workspace_failed_host_can_be_explicitly_retired_and_reopened(self):
        self.host.shutdown()
        with self.workspace() as controller:
            pending = {"done": threading.Event(), "error": "", "result": {"url": self.url}}
            controller._install_studio(pending)
            pump_until(lambda: pending["done"].is_set())
            host = controller.shell.owners["Studio"]
            host.test_control = lambda: {"confirm": True}
            host._failure("fixture failed page")
            controller.shell.close_surface("Studio")
            pump_until(lambda: "Studio" not in controller.shell.owners and not controller.shell._closing)
            self.assertFalse(host._native_owner.isLocked())
            retry = {"done": threading.Event(), "error": "", "result": {"url": self.url}}
            controller._install_studio(retry)
            pump_until(lambda: retry["done"].is_set())
            self.assertEqual(retry["error"], "")
            self.assertIsNot(controller.shell.owners["Studio"], host)

    def test_commit_requires_approval_and_shutdown_is_idempotent(self):
        closed = []
        self.host.closed.connect(lambda: closed.append(True))
        self.assertFalse(self.host.commit_close())
        self.assertEqual(self.prepare(), [True])
        page, profile = self.host.page, self.host.profile
        with patch.object(APP, "quit") as quit_app, patch.object(APP, "exit") as exit_app:
            self.assertTrue(self.host.commit_close())
            pump_until(lambda: self.host.stopped)
            self.host.shutdown()
            self.host.shutdown()
            self.assertFalse(isValid(page))
            self.assertFalse(isValid(profile))
            self.assertEqual(closed, [True])
            quit_app.assert_not_called()
            exit_app.assert_not_called()
        self.assertTrue(isValid(self.parent))
        self.assertEqual(self.prepare(), [False])

    def test_exact_navigation_guards_and_no_popups(self):
        page = self.host.page
        kind = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        self.assertTrue(page.acceptNavigationRequest(QUrl(self.url), kind, True))
        self.assertTrue(page.acceptNavigationRequest(QUrl(self.url + "#vinyl=" + "b" * 32), kind, True))
        for url in (self.url + "?query=1", self.url + "api/editor-config", "https://example.invalid/",
                    self.url.replace("127.0.0.1", "localhost"), self.url.replace("http:", "file:"),
                    self.url.replace("127.0.0.1", "user@127.0.0.1")):
            with self.subTest(url=url):
                self.assertFalse(page.acceptNavigationRequest(QUrl(url), kind, True))
        self.assertIsNone(page.createWindow(QWebEnginePage.WebWindowType.WebBrowserTab))

    def test_request_interceptor_preserves_local_data_and_blob_only(self):
        for url, blocked in ((self.url + "asset.js", False), ("data:image/png;base64,AA==", False),
                             ("blob:" + self.url, False), ("blob:https://example.invalid/x", True),
                             ("https://example.invalid/x", True), ("file:///C:/private.txt", True)):
            info = Mock()
            info.requestUrl.return_value = QUrl(url)
            self.host.interceptor.interceptRequest(info)
            self.assertEqual(info.block.called, blocked, url)

    def test_download_completed_bytes_reopen_and_ack_once(self):
        self.controls["download"] = "save"
        self.js("exportBlob()")
        pump_until(lambda: len(self.events) >= 1 and any(e["kind"] == "download" for e in self.events))
        pump_until(lambda: bool(self.js("downloadResults")))
        self.assertEqual((self.output / "downloads/layout.json").read_bytes(), b"studio-fixture-bytes")
        self.assertEqual(self.js("downloadResults.map(x=>x.status)"), ["completed"])
        self.assertFalse(self.host.pending_downloads)

    def test_download_cancel_and_failure_are_not_success(self):
        self.js("exportBlob()")
        pump_until(lambda: len(self.js("downloadResults")) == 1)
        self.controls["download"] = "fail"
        self.js("exportBlob()")
        pump_until(lambda: len(self.js("downloadResults")) == 2)
        self.assertEqual(self.js("downloadResults.map(x=>x.status)"), ["cancelled", "failed"])

    def test_close_during_picker_is_vetoed_and_download_remains_owned(self):
        self.controls.update(download="save", hold_picker=True)
        answers = []
        def close_during_picker():
            self.host.prepare_close(answers.append)
            self.controls["release_picker"] = True
        QTimer.singleShot(150, close_during_picker)
        self.js("exportBlob()")
        pump_until(lambda: bool(answers))
        self.assertEqual(answers, [False])
        pump_until(lambda: bool(self.js("downloadResults")))
        self.assertTrue(isValid(self.host.page))

    def test_download_from_wrong_page_or_origin_is_cancelled(self):
        for url, page in (("blob:https://example.invalid/x", self.host.page),
                          ("blob:" + self.url, object())):
            item = Mock()
            item.url.return_value = QUrl(url)
            item.page.return_value = page
            self.host.download(item)
            item.cancel.assert_called_once()
            item.accept.assert_not_called()

    def test_new_download_invalidates_prepared_close(self):
        self.assertEqual(self.prepare(), [True])
        self.js("exportBlob()")
        pump_until(lambda: bool(self.js("downloadResults")))
        self.assertFalse(self.host.commit_close())

    def test_dirty_commit_does_not_prompt_twice(self):
        self.dirty()
        self.controls["confirm"] = True
        self.assertEqual(self.prepare(), [True])
        confirms = [event for event in self.events if event["kind"] == "confirm"]
        self.controls["confirm"] = False
        self.assertTrue(self.host.commit_close())
        pump_until(lambda: self.host.stopped)
        self.assertEqual([event for event in self.events if event["kind"] == "confirm"], confirms)

    def test_open_document_dialog_vetoes_prepare_without_disposal(self):
        self.js("(() => {const d=document.createElement('dialog');document.body.append(d);d.showModal();return true;})()")
        self.assertEqual(self.prepare(), [False])
        self.assertEqual(self.js("hideCount"), 0)

    def test_cancel_inside_confirmation_nested_loop_cannot_approve(self):
        self.dirty()
        def cancel():
            self.host.cancel_close()
            return {"confirm": True}
        self.host.test_control = cancel
        self.assertEqual(self.prepare(), [False])
        self.assertFalse(self.host.commit_close())
        self.assertTrue(self.host.view.isEnabled())

    def test_invalid_close_states_fail_closed(self):
        states = (None, "", "{", "[]", "x" * 4097,
                  json.dumps({"document": self.host.native_document, "dirty": 1, "modal": False}),
                  json.dumps({"document": "wrong", "dirty": False, "modal": False}))
        for state in states:
            with self.subTest(state=str(state)[:50]):
                with patch.object(self.host.page, "runJavaScript", side_effect=lambda _script, callback: callback(state)):
                    self.assertEqual(self.prepare(), [False])
                self.assertFalse(self.host.commit_close())
        with self.assertRaises(TypeError):
            self.host.prepare_close(None)

    def test_repeated_prepare_preserves_first_attempt(self):
        first, second = [], []
        callbacks = []
        with patch.object(self.host.page, "runJavaScript", side_effect=lambda _script, callback: callbacks.append(callback)):
            self.host.prepare_close(first.append)
            self.host.prepare_close(second.append)
            pump_until(lambda: bool(second))
            self.assertEqual(second, [False])
            self.assertEqual(first, [])
            callbacks[0](json.dumps({"document": self.host.native_document, "dirty": False, "modal": False}))
            pump_until(lambda: bool(first))
            self.assertEqual(first, [True])

    def test_cancellation_restores_previously_disabled_input(self):
        self.host.view.setEnabled(False)
        self.assertEqual(self.prepare(), [True])
        self.host.cancel_close()
        self.assertFalse(self.host.view.isEnabled())

    def test_readiness_invalid_stale_and_timeout(self):
        failures = []
        self.host.failed.connect(failures.append)
        self.host.ready = False
        for value in (None, "x" * 4097, "{", "[]", "{}"):
            self.host._readiness(value, self.host.generation)
            self.assertFalse(self.host.ready)
        self.host._readiness(json.dumps({"document": "stale", "ready": True}), self.host.generation - 1)
        self.assertNotEqual(self.host.native_document, "stale")
        self.host.started = time.monotonic() - 60
        self.host._poll()
        self.assertEqual(failures, ["Studio page did not finish loading."])
        self.assertFalse(self.host.timer.isActive())

    def test_readiness_script_waits_for_document_root_and_preserves_language(self):
        from kfps_livery_lab.native_host import READINESS_SCRIPT
        body = "return (" + READINESS_SCRIPT + ");"
        result = self.js("(() => { const probe = new Function('document', 'window', " + json.dumps(body) + ");"
            "const state = {__liveryLab:{ready:true},__kfpsStudioNativeDocument:'fixture'};"
            "return [probe({documentElement:null}, state),"
            "probe({documentElement:{lang:'ko'}}, state),"
            "probe({documentElement:{lang:'untrusted'}}, state)]; })()")
        self.assertIsNone(result[0])
        self.assertEqual(json.loads(result[1]), {"ready": True, "document": "fixture", "language": "ko"})
        self.assertEqual(json.loads(result[2])["language"], "en")
        self.host.ready = False
        self.host._readiness(result[0], self.host.generation)
        self.assertFalse(self.host.ready)

    def test_late_readiness_after_failure_cannot_revive_owner(self):
        self.host._failure("fixture renderer failure")
        self.host._readiness(json.dumps({"document": self.host.native_document, "ready": True}),
                             self.host.generation)
        self.assertFalse(self.host.ready)

    def test_final_commit_is_dispatched_once(self):
        self.assertEqual(self.prepare(), [True])
        with patch.object(self.host.page, "triggerAction") as action:
            self.assertTrue(self.host.commit_close())
            self.assertFalse(self.host.commit_close())
            self.host.cancel_close()
            action.assert_called_once()

    def test_navigation_during_commit_rejects_stale_native_close(self):
        self.assertEqual(self.prepare(), [True])
        with patch.object(self.host.page, "triggerAction"):
            self.assertTrue(self.host.commit_close())
            self.host._navigating()
            self.host.page.windowCloseRequested.emit()
        self.assertFalse(self.host.stopped)
        self.assertFalse(self.host.commit_close())
        self.assertTrue(self.host.view.isEnabled())

    def test_shutdown_clears_readiness_and_preserves_parent(self):
        self.host.shutdown()
        self.assertFalse(self.host.ready)
        self.assertTrue(isValid(self.parent))

    def test_offscreen_surface_capture_is_nonblank(self):
        picture = self.host.view.grab().toImage()
        self.assertFalse(picture.isNull())
        colors = {picture.pixelColor(x, y).rgba() for x in range(10, picture.width(), 20)
                  for y in range(10, picture.height(), 20)}
        self.assertGreater(len(colors), 1)
        self.assertTrue(picture.save(str(self.output / "host-surface.png")))

    def fake_download(self, identifier=987):
        item = Mock()
        item.url.return_value = QUrl(f"blob:http://127.0.0.1:{self.server.server_port}/fixture")
        item.page.return_value = self.host.page
        item.id.return_value = identifier
        item.suggestedFileName.return_value = "../layout.json"
        return item

    def test_download_limits_early_readiness_and_chooser_failure(self):
        self.host.pending_downloads = {key: Mock() for key in range(16)}
        item = self.fake_download()
        self.host.download(item)
        item.cancel.assert_called_once()
        item.accept.assert_not_called()
        self.host.pending_downloads.clear()
        original = self.host.native_document
        self.host.native_document = ""
        item = self.fake_download()
        self.host.download(item)
        item.cancel.assert_called_once()
        self.host.native_document = original
        self.controls["download"] = "save"
        item = self.fake_download()
        with patch.object(self.host, "_download_path", side_effect=OSError("test destination denied")):
            self.host.download(item)
        item.cancel.assert_called_once()
        self.assertFalse(self.host.pending_downloads)

    def test_late_download_result_after_navigation_or_shutdown_is_not_delivered(self):
        from PySide6.QtWebEngineCore import QWebEngineDownloadRequest
        self.controls["download"] = "save"
        item = self.fake_download()
        self.host.download(item)
        callback = item.stateChanged.connect.call_args.args[0]
        self.host._navigating()
        callback(QWebEngineDownloadRequest.DownloadState.DownloadCompleted)
        APP.processEvents()
        self.assertEqual(self.js("downloadResults"), [])
        self.host.native_document = self.js("__kfpsStudioNativeDocument")
        item = self.fake_download(988)
        self.host.download(item)
        callback = item.stateChanged.connect.call_args.args[0]
        self.host.shutdown()
        callback(QWebEngineDownloadRequest.DownloadState.DownloadInterrupted)
        item.cancel.assert_called_once()
        self.assertFalse(self.host.pending_downloads)

    def test_empty_destination_cancels_download(self):
        self.controls["download"] = "save"
        item = self.fake_download()
        with patch.object(self.host, "_download_path", return_value=""):
            self.host.download(item)
        item.cancel.assert_called_once()
        item.accept.assert_not_called()

    def test_guards_handle_invalid_port_and_constructor_url(self):
        self.assertFalse(self.host.local("http://127.0.0.1:bad/"))
        for url in ("https://example.invalid/", self.url + "?query=yes"):
            with self.assertRaises(ValueError):
                self.Host(url, self.output / "rejected", offscreen=True)
        self.assertFalse((self.output / "rejected").exists())

    def test_standalone_close_uses_native_request_and_does_not_quit_by_itself(self):
        self.host.hosted = False
        self.host.pending_downloads[1] = Mock()
        self.host.window.close()
        self.assertFalse(self.host.stopped)
        self.host.pending_downloads.clear()
        closed = []
        self.host.closed.connect(lambda: closed.append(True))
        self.host.window.close()
        pump_until(lambda: self.host.stopped)
        self.assertEqual(closed, [True])

    def test_standalone_wrapper_real_process_closes_cleanly(self):
        self.host.shutdown()
        environment = dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN=str(self.output))
        command = [str(ROOT / "python/python.exe"), "-I", "-B", str(Path(__file__)),
                   "--standalone-child", self.url]
        with (self.output / "standalone.stdout.log").open("wb") as out, (self.output / "standalone.stderr.log").open("wb") as err:
            child = subprocess.Popen(command, env=environment, cwd=self.output, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                child.wait(timeout=25)
            finally:
                if child.poll() is None:
                    import psutil
                    descendants = psutil.Process(child.pid).children(recursive=True)
                    child.kill()
                    child.wait(5)
                    for process in descendants:
                        try:
                            process.kill()
                        except psutil.Error:
                            pass
        self.assertEqual(child.returncode, 0, (self.output / "standalone.stderr.log").read_text())
        status = json.loads((self.output / "standalone/runs/session/host.json").read_text())
        self.assertEqual(status["status"], "closed")
        self.assertIs(status["offscreen"], True)


if __name__ == "__main__":
    with (RUN / "tests.log").open("w", encoding="utf-8") as log:
        class Output:
            def write(self, value):
                sys.stderr.write(value)
                log.write(value)
            def flush(self):
                sys.stderr.flush()
                log.flush()
        tracer = trace.Trace(count=True, trace=False, ignoredirs=[str(ROOT / "python")])
        result = tracer.runfunc(unittest.TextTestRunner(stream=Output(), verbosity=2).run,
                               unittest.defaultTestLoader.loadTestsFromTestCase(StudioHostTests))
    target = ROOT / "tools/livery-studio/src/kfps_livery_lab/studio_host.py"
    executable = set(trace._find_executable_linenos(str(target))) if target.is_file() else set()
    executed = {line for (filename, line), count in tracer.results().counts.items()
                if count and Path(filename).resolve() == target.resolve()}
    (RUN / "coverage.json").write_text(json.dumps({
        "file": str(target), "executable_lines": len(executable), "covered_lines": len(executable & executed),
        "percent": round(100 * len(executable & executed) / len(executable), 2) if executable else 0,
        "missing_lines": sorted(executable - executed), "method": "stdlib trace line coverage; not branch coverage"
    }, indent=2), encoding="utf-8")
    (RUN / "result.json").write_text(json.dumps({
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "success": result.wasSuccessful(), "platform": APP.platformName(),
        "limitations": "Offscreen native protocol fixture; not full Studio rendering or physical input qualification."
    }, indent=2), encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
