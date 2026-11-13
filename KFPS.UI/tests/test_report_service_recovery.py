import concurrent.futures
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService
from kfps_ui.support_window import ReportWindow

APP = QCoreApplication.instance() or QCoreApplication([])


class ReportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = AppPaths(self.root, ROOT / "KFPS.UI", ROOT / "KFPS.UI/qml", ROOT / "KFPS.UI/assets",
                         self.root / "runtime", Path(sys.executable))
        self.log = LogService()
        self.addCleanup(self.log.close)
        self.service = ReportService(paths, self.log, SimpleNamespace(localVersion="test"))
        self.addCleanup(self.service.close)

    def result(self):
        path = self.root / "report.json"
        path.write_text('{"saved":true}')
        return {"path": str(path), "handoff": "synthetic", "report": {"private_logs": {"files": 1}}}

    def test_launch_exception_is_recoverable_and_preserves_saved_report(self):
        self.service._support_busy = True
        with patch("kfps_ui.report_service.open_support_handoff", side_effect=OSError("PRIVATE path")):
            self.service._apply_support(self.result())
        self.assertFalse(self.service.supportBusy)
        self.assertTrue(Path(self.service.latestPath).is_file())
        self.assertIn("Report saved", self.service.supportStatus)
        self.assertNotIn("PRIVATE", self.service.supportStatus)
        self.assertNotIn("repair the app", self.service.supportStatus)

    def test_snapshot_failure_clears_busy_and_is_redacted(self):
        with patch.object(self.log, "diagnostic_snapshot", side_effect=RuntimeError("password=PRIVATE")):
            self.service.openSupportForm("editor")
        self.assertFalse(self.service.supportBusy)
        self.assertIn("Could not prepare", self.service.supportStatus)
        self.assertNotIn("PRIVATE", self.service.supportStatus)

    def test_crashed_child_changes_status_without_destroying_report(self):
        process = Mock(pid=1234)
        process.poll.return_value = None
        def launch(*args, on_launch=None, **kwargs):
            on_launch(process)
            return "review"
        with patch("kfps_ui.report_service.open_support_handoff", side_effect=launch):
            self.service._apply_support(self.result())
        self.assertIn("Opening", self.service.supportStatus)
        process.poll.return_value = -1073741819
        self.service._poll_review_processes()
        self.assertIn("closed unexpectedly", self.service.supportStatus)
        self.assertTrue(Path(self.service.latestPath).is_file())
        self.assertFalse(self.service._review_timer.isActive())
        self.assertIn("-1073741819", self.log.diagnostic_snapshot()[0])

    def test_normal_exit_and_application_close_do_not_kill_reviewer(self):
        process = Mock(pid=1234)
        process.poll.return_value = 0
        self.service._watch_review(process)
        self.service._poll_review_processes()
        self.assertNotIn("unexpectedly", self.service.supportStatus)
        process.poll.return_value = None
        self.service._watch_review(process)
        self.service.close()
        self.assertFalse(self.service._review_timer.isActive())
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_renderer_exit_details_are_retained_without_raw_content(self):
        window = SimpleNamespace(closed=False, logger=logging.getLogger("kfps-report-window"), fail=Mock())
        with self.assertLogs("kfps-report-window", "WARNING") as logs:
            ReportWindow.renderer_failed(window, SimpleNamespace(name="CrashedTerminationStatus"), 15)
        text = " ".join(logs.output)
        self.assertIn("CrashedTerminationStatus", text)
        self.assertIn("exit_code=15", text)
        window.fail.assert_called_once_with("renderer-terminated")

    def test_late_load_callback_after_failure_does_not_resume_transfers(self):
        window = SimpleNamespace(closed=False, failed=True, load_timeout=Mock(), page=Mock(), timer=Mock())
        ReportWindow.load_finished(window, True)
        window.page.url.assert_not_called()
        window.timer.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
