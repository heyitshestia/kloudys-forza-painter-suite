"""Exercise report startup/cleanup with real Windows installation leases."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src")]
from kfps_editor import baseline, update_guard
from kfps_editor.windows_lock import acquire_file_lease
from kfps_ui import support_window as report


class ReportErrorTests(unittest.TestCase):
    def test_repair_advice_only_for_invalid_installation(self):
        for korean in (False, True):
            errors = [report.ReportWindowBusyError(), RuntimeError(), PermissionError()]
            for code in (32, 33):
                error = RuntimeError()
                error.winerror = code
                errors.append(error)
            for error in errors:
                self.assertNotIn("KFPS-Updater.exe", report.startup_error_message(error, korean))
            self.assertIn("KFPS-Updater.exe", report.startup_error_message(baseline.BaselineError(), korean))


@unittest.skipUnless(os.name == "nt", "Windows installation leases")
class ReportStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "update-state"
        self.id = str(uuid.uuid4())
        self.folder = self.root / "runtime/support-reports" / self.id
        self.folder.mkdir(parents=True)
        self.source = self.folder / "report.json"
        self.content = json.dumps({"schema": "kfps-support-report/1", "id": self.id}).encode()
        self.source.write_bytes(self.content)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mock = {}
        for name in ("QApplication", "QLockFile", "QLocalServer", "ReportWindow", "QMessageBox", "listen"):
            self.mock[name] = self.stack.enter_context(patch.object(report, name))
        self.stack.enter_context(patch.object(sys, "argv", ["report.py", "--report-id", self.id]))
        self.verify = self.stack.enter_context(patch.object(baseline, "verify"))
        self.stack.enter_context(patch.object(update_guard, "updater_state_root", return_value=self.state))
        self.forward = self.stack.enter_context(patch.object(report, "forward", return_value=False))
        self.stack.enter_context(patch.object(report, "is_korean_display_language", return_value=False))
        self.app = self.mock["QApplication"].return_value
        self.app.exec.return_value = 0
        self.window = self.mock["ReportWindow"].return_value
        self.server = self.mock["QLocalServer"].return_value
        self.lock = self.mock["QLockFile"].return_value

    def reader(self):
        lease = update_guard.acquire_update_guard(self.state)
        self.addCleanup(lease.Close)
        return lease

    def writer(self):
        self.state.mkdir(exist_ok=True)
        lease = acquire_file_lease(self.state / "updater.lock")
        self.addCleanup(lease.Close)
        return lease

    def assert_writer_blocked(self):
        with self.assertRaises(OSError) as error:
            self.writer()
        self.assertEqual(error.exception.winerror, 32)

    def test_editor_then_report_and_editor_closed_first(self):
        editor = self.reader()
        def run():
            self.assert_writer_blocked()
            editor.Close()
            self.assert_writer_blocked()
            return 0
        self.app.exec.side_effect = run
        self.assertEqual(report.main(self.root), 0)
        self.writer()
        self.mock["QMessageBox"].warning.assert_not_called()
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_report_then_editor_and_report_closed_first(self):
        def run():
            self.reader()
            self.assert_writer_blocked()
            return 0
        self.app.exec.side_effect = run
        self.assertEqual(report.main(self.root), 0)
        self.assert_writer_blocked()
        self.window.shutdown.assert_called_once()
        self.lock.unlock.assert_called_once()

    def test_updater_blocks_report_without_repair_advice(self):
        self.writer()
        self.assertEqual(report.main(self.root), 1)
        self.mock["ReportWindow"].assert_not_called()
        message = self.mock["QMessageBox"].warning.call_args.args[2]
        self.assertIn("Finish the update", message)
        self.assertNotIn("repair", message)
        self.assertEqual(self.source.read_bytes(), self.content)

    def test_listen_failure_releases_all_locks_before_error_dialog(self):
        self.server.listen.return_value = False
        def warning(*args):
            self.writer().Close()
            self.lock.unlock.assert_called_once()
            self.window.shutdown.assert_called_once()
            self.server.close.assert_called_once()
        self.mock["QMessageBox"].warning.side_effect = warning
        self.assertEqual(report.main(self.root), 1)
        self.window.shutdown.assert_called_once()

    def test_renderer_cleanup_error_cannot_leak_update_lease(self):
        self.window.shutdown.side_effect = RuntimeError("synthetic teardown failure")
        self.server.listen.return_value = False
        self.mock["QMessageBox"].warning.side_effect = lambda *args: self.writer().Close()
        self.assertEqual(report.main(self.root), 1)
        self.lock.unlock.assert_called_once()

    def test_forwarded_report_does_not_take_another_lease(self):
        self.forward.return_value = True
        with patch.object(update_guard, "acquire_update_guard") as acquire:
            self.assertEqual(report.main(self.root), 0)
        acquire.assert_not_called()
        self.mock["ReportWindow"].assert_not_called()

    def test_damaged_baseline_does_not_open_window_or_hold_lease(self):
        self.verify.side_effect = baseline.BaselineError("synthetic mismatch")
        self.mock["QMessageBox"].warning.side_effect = lambda *args: self.writer().Close()
        self.assertEqual(report.main(self.root), 1)
        self.assertIn("KFPS-Updater.exe", self.mock["QMessageBox"].warning.call_args.args[2])
        self.mock["ReportWindow"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
