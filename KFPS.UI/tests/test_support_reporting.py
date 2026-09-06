import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui import support_report as support
from kfps_ui import support_browser
from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService

APP = QCoreApplication.instance() or QCoreApplication([])


class SupportReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def build(self, **extra):
        context = {"page": "outputs", "version": "3.1.60", "theme": "default", "log": "", "services": {"transfer": {"status": "Export failed", "liveLog": "Transfer failed with exit code 1", "selectedLayers": 3000, "selectedPath": "private-artwork.json"}}}
        context.update(extra)
        return support.build_support_report(self.root, context, since=time.time() - 30, collect=lambda: {"hardware": {"gpus": [{"name": "Synthetic GPU"}]}})

    def test_prefill_allowlist_and_sensitive_text(self):
        self.assertNotIn("Private Contest", support.redact("Selected: Private Contest Entry.json"))
        report = self.build(log='Bearer abcdef\nFailed C:\\Users\\Sensitive User\\Contest Entry.json\nEmail private@example.test\nhttps://example.test/private\n123456789012345678')
        text = json.dumps(report)
        for value in ("abcdef", "Sensitive User", "Contest Entry", "private@example", "example.test/private", "123456789012345678", "selectedPath", "private-artwork"):
            self.assertNotIn(value, text)
        self.assertEqual(report["feature"], "Import and export")
        self.assertEqual(report["description"], "Transfer failed with exit code 1")
        self.assertEqual(report["technical"]["states"]["transfer"]["selectedLayers"], 3000)

    def test_unicode_and_handoff_roundtrip_without_network(self):
        report = self.build(log="Synthetischer Fehler: Gr\u00f6\u00dfe ung\u00fcltig")
        path, handoff = support.save_handoff(self.root, report)
        self.assertEqual(json.loads(path.read_text()), report)
        html = handoff.read_text()
        encoded = html.split("#draft=", 1)[1].split('"', 1)[0]
        decoded = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        self.assertEqual(decoded, report)
        self.assertEqual(json.loads((self.root / "runtime/support-reports/latest.json").read_text()), report)
        self.assertNotIn("fetch(", html)

    def test_invalid_handoff_address_and_id_do_not_write(self):
        for origin in ("https://evil.test", support.FORM_ORIGIN + "/other", support.FORM_ORIGIN + "?secret=x"):
            with self.assertRaises(ValueError):
                support.save_handoff(self.root, self.build(), origin=origin)
        report = self.build(); report["id"] = "../../escape"
        with self.assertRaises(ValueError): support.save_handoff(self.root, report)
        self.assertFalse((self.root / "runtime").exists())

    def test_log_size_is_bounded_and_hardware_failure_is_recoverable(self):
        started = time.monotonic()
        report = self.build(log="x" * 1000000)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertLess(len(json.dumps(report)), support.MAX_REPORT_BYTES)
        self.assertLessEqual(len(report["technical"]["logs"][-1]["text"]), 6500)
        def fail(): raise OSError("hardware not accessible")
        report = support.build_support_report(self.root, {}, since=time.time(), collect=fail)
        self.assertIn("collection_warning", report["technical"])

    def test_stale_malformed_or_oversized_locator_report_is_not_used(self):
        path = self.root / "runtime/live-memory/reports/latest.json"
        path.parent.mkdir(parents=True)
        for data in ("invalid", "x" * (2 * 1024 * 1024 + 1), json.dumps({"created_utc": "2000-01-01T00:00:00Z"})):
            path.write_text(data)
            self.assertEqual(support.recent_locator_summary(self.root, since=time.time() - 30, now=time.time()), {})

    def test_recent_locator_retains_only_outcome_and_not_shape_or_pointer_data(self):
        path = self.root / "runtime/live-memory/reports/latest.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"created_utc": datetime.now(timezone.utc).isoformat(), "request": {"game":"FH6", "layer_count":3000, "path":"private"}, "outcome":{"status":"no_match", "pointer":"secret-pointer"}, "candidates":["secret-candidate"], "shapes":["secret-art"]}))
        value = support.recent_locator_summary(self.root, since=time.time() - 30, now=time.time())
        self.assertEqual(value["request"]["layer_count"], 3000)
        self.assertNotIn("secret", json.dumps(value)); self.assertNotIn("private", json.dumps(value))

    def test_atomic_replace_retries_locked_file_then_cleans_temporary(self):
        path = self.root / "saved.json"
        original = os.replace; attempts = []
        def locked(a, b):
            attempts.append(1)
            if len(attempts) < 3: raise PermissionError("locked")
            return original(a, b)
        with patch.object(support.os, "replace", side_effect=locked), patch.object(support.time, "sleep"):
            support.atomic_text(path, "new")
        self.assertEqual(path.read_text(), "new"); self.assertEqual(len(attempts), 3)
        with patch.object(support.os, "replace", side_effect=PermissionError("locked")), patch.object(support.time, "sleep"):
            with self.assertRaises(PermissionError): support.atomic_text(path, "broken")
        self.assertEqual(path.read_text(), "new"); self.assertEqual(list(self.root.glob("*.tmp")), [])

    def service(self):
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        log = LogService(); service = ReportService(paths, log, SimpleNamespace(localVersion="3.1.60"))
        self.addCleanup(log.close); self.addCleanup(service.close)
        return service

    def wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents(); time.sleep(.005)
        self.assertTrue(predicate())

    def test_service_real_worker_saves_opens_once_and_ignores_repeated_click(self):
        service = self.service(); gate = threading.Event()
        def collect(*args, **kwargs): gate.wait(2); return self.build()
        with patch("kfps_ui.report_service.build_support_report", side_effect=collect) as build, patch("kfps_ui.report_service.open_support_handoff", return_value="prefilled") as open_url:
            service.openSupportForm("outputs"); service.openSupportForm("editor")
            self.assertTrue(service.supportBusy); gate.set()
            self.wait(lambda: not service.supportBusy)
            self.assertEqual(build.call_count, 1); self.assertEqual(open_url.call_count, 1)
            self.assertTrue(Path(service.latestPath).is_file())
            self.assertIn("Nothing is sent", service.supportStatus)

    def test_service_close_during_collection_never_opens_browser(self):
        service = self.service()
        def collect(*args, **kwargs): time.sleep(.03); return self.build()
        with patch("kfps_ui.report_service.build_support_report", side_effect=collect), patch("kfps_ui.report_service.open_support_handoff") as open_url:
            service.openSupportForm("editor"); service.close(); APP.processEvents()
            self.assertEqual(open_url.call_count, 0)
            service.openSupportForm("editor"); self.assertEqual(open_url.call_count, 0)

    def test_service_failure_clears_busy_and_browser_failure_preserves_report(self):
        service = self.service()
        with patch("kfps_ui.report_service.build_support_report", side_effect=OSError("Permission denied")):
            service.openSupportForm("outputs"); self.wait(lambda: not service.supportBusy)
            self.assertIn("Could not prepare", service.supportStatus)
        with patch("kfps_ui.report_service.build_support_report", side_effect=lambda *a,**k:self.build()), patch("kfps_ui.report_service.open_support_handoff", return_value="failed"):
            service.openSupportForm("outputs"); self.wait(lambda: not service.supportBusy)
            self.assertIn("Report saved", service.supportStatus)
            self.assertTrue(Path(service.latestPath).is_file())

    def test_existing_local_markdown_report_is_unchanged(self):
        service = self.service()
        text = service.previewReport("Bug", "Title", "Details", True, False, False)
        self.assertIn("# KFPS Report", text); self.assertNotIn("runtime log", text)
        path = service.saveReport("Bug", "Title", "Details", True, False, False)
        self.assertIn("Details", Path(path).read_text())

    def test_handoff_uses_web_browser_executable_not_html_association(self):
        _report, handoff = support.save_handoff(self.root / "spaces & unicode \u00e9", self.build())
        with patch.object(support_browser, "default_browser_executable", return_value="C:/Browser With Spaces/browser.exe"), patch.object(support_browser.QProcess, "startDetached", return_value=(True, 42)) as launch, patch.object(support_browser.QDesktopServices, "openUrl") as shell:
            self.assertEqual(support_browser.open_support_handoff(str(handoff)), "prefilled")
            launch.assert_called_once_with("C:/Browser With Spaces/browser.exe", [handoff.as_uri()])
            shell.assert_not_called()

    def test_missing_or_failed_browser_uses_https_only_and_preserves_report(self):
        _report, handoff = support.save_handoff(self.root, self.build())
        for executable in ("", "C:/Removed Browser/browser.exe"):
            with patch.object(support_browser, "default_browser_executable", return_value=executable), patch.object(support_browser.QProcess, "startDetached", return_value=(False, 0)), patch.object(support_browser.QDesktopServices, "openUrl", return_value=True) as shell:
                self.assertEqual(support_browser.open_support_handoff(str(handoff)), "manual")
                self.assertEqual(shell.call_args.args[0].toString(), support.FORM_ORIGIN)
                self.assertTrue(handoff.is_file())
        with patch.object(support_browser, "default_browser_executable", return_value=""), patch.object(support_browser.QDesktopServices, "openUrl", return_value=False):
            self.assertEqual(support_browser.open_support_handoff(str(handoff)), "failed")

    def test_missing_handoff_never_launches_a_browser(self):
        with patch.object(support_browser.QProcess, "startDetached") as launch, patch.object(support_browser.QDesktopServices, "openUrl") as shell:
            self.assertEqual(support_browser.open_support_handoff(str(self.root / "missing.html")), "failed")
            launch.assert_not_called(); shell.assert_not_called()


if __name__ == "__main__": unittest.main()
