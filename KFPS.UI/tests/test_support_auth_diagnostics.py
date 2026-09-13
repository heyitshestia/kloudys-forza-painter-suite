import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui.support_auth_diagnostics import record_signin_events
from kfps_ui.support_window import ReportWindow


class SigninDiagnosticsTests(unittest.TestCase):
    def event(self, **values):
        return dict(sequence=1, attempt=1, stage="start", result="timeout", http_status=0,
                    elapsed_ms=15000, **values)

    def test_fixed_fields_only_and_duplicate_callbacks_do_not_repeat(self):
        event = self.event(url="https://secret/?ticket=private", code="ABCD-1234", cookie="private", error="private")
        logger = logging.getLogger("signin-test")
        with self.assertLogs(logger, level="INFO") as logs:
            cursor = record_signin_events([event], 0, logger)
            self.assertEqual(record_signin_events([event], cursor, logger), 1)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("stage=start result=timeout http_status=0 elapsed_ms=15000", logs.output[0])
        for secret in ("private", "ticket", "ABCD", "https", "cookie"):
            self.assertNotIn(secret, logs.output[0])

    def test_malformed_or_unbounded_renderer_data_is_not_logged(self):
        logger = Mock()
        valid = self.event()
        for key, value in (("sequence", True), ("sequence", 2**53), ("sequence", -1),
                           ("attempt", "private"), ("attempt", 1000001), ("stage", ["start"]),
                           ("stage", "start\nprivate"), ("result", {"cookie": "private"}),
                           ("result", "token-private"), ("http_status", 999),
                           ("http_status", True), ("elapsed_ms", float("nan")), ("elapsed_ms", 600001)):
            self.assertEqual(record_signin_events([{**valid, key: value}], 0, logger), 0)
        for value in (None, {}, "private", [None], [valid] * 65):
            self.assertEqual(record_signin_events(value, 0, logger), 0)
        logger.info.assert_not_called()

    def test_bounded_history_reports_missing_events_without_dumping_payload(self):
        logger = Mock()
        self.assertEqual(record_signin_events([{**self.event(), "sequence": 7}], 3, logger), 7)
        logger.info.assert_any_call("sign-in diagnostics-skipped=%s", 3)

    def test_native_bridge_reads_cursor_and_logs_in_real_review_callback(self):
        logger = Mock()
        window = SimpleNamespace(auth_inflight=False, auth_diagnostic_cursor=0, logger=logger,
                                 korean=False, launch_auth=Mock(), closed=False,
                                 origin="https://support.example", page=Mock(), run=Mock())
        from PySide6.QtCore import QUrl
        window.page.url.return_value = QUrl(window.origin)
        window.review_state = lambda value: ReportWindow.review_state(window, value)
        ReportWindow.poll_auth(window)
        self.assertIn("diagnostics?.(0)", window.run.call_args.args[0])
        window.run.call_args.args[1]({"language": "en", "diagnostics": [self.event()], "request": None})
        self.assertEqual(window.auth_diagnostic_cursor, 1)
        self.assertEqual(logger.info.call_count, 1)
        ReportWindow.poll_auth(window)
        self.assertIn("diagnostics?.(1)", window.run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
