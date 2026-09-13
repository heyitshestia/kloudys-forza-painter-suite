"""Native close lifecycle faults; run separately from QCoreApplication suites."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from PySide6.QtCore import QUrl
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import delete
from kfps_editor.host import EditorDesktop

APP = QApplication.instance() or QApplication([])
BUTTON = QMessageBox.StandardButton


class CloseLifecycleTests(unittest.TestCase):
    def setUp(self):
        run = ROOT / "runtime/test-runs/editor-modernization-2026-09-12/runs/unit-profiles"
        run.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=run)
        self.host = EditorDesktop(ROOT, Path(self.temp.name))
        self.host.page = Mock()
        self.host.server = Mock()
        self.host._write_state = Mock()
        self.host.close = Mock()
        self.host._message_box = Mock(return_value=BUTTON.Cancel)
        self.host._ready = True

    def tearDown(self):
        self.host.page = self.host.server = None
        self.host.shutdown()
        delete(self.host)
        self.temp.cleanup()

    def request(self):
        script = self.host.page.runJavaScript.call_args.args[0]
        return json.loads(script.removeprefix("window.KfpsDesktop.execute(...").removesuffix(");"))

    def reply(self, value, *, request=None, ok=True):
        request = request or self.request()[0]
        self.host._command_result(request, json.dumps({"ok": ok, "value": value}))

    def begin(self, dirty=False, choice=BUTTON.Discard):
        self.host._message_box.return_value = choice
        self.host.closeEvent(QCloseEvent())
        self.assertEqual(self.request()[1], "state")
        self.reply({"dirty": dirty, "saving": False})

    def test_status_and_final_close_both_have_watchdogs(self):
        self.host.closeEvent(QCloseEvent())
        self.assertTrue(self.host.close_timer.isActive())
        self.reply({"dirty": False, "saving": False})
        self.assertEqual(self.request()[1:], ["close", {"action": "keep-recovery"}])
        self.assertTrue(self.host.close_timer.isActive())

    def test_success_closes_once_and_disposes_watchdog(self):
        self.begin()
        request = self.request()[0]
        self.reply({"ok": True})
        self.reply({"ok": True}, request=request)
        self.host.close.assert_called_once()
        self.assertTrue(self.host._allow_close)
        self.assertFalse(self.host.close_timer.isActive())
        self.assertFalse(self.host._commands)

    def test_discard_preserves_recovery(self):
        self.begin(dirty=True)
        self.assertEqual(self.request()[2], {"action": "keep-recovery"})

    def test_save_uses_save_action(self):
        self.begin(dirty=True, choice=BUTTON.Save)
        self.assertEqual(self.request()[2], {"action": "save"})

    def test_cancel_save_question_leaves_open(self):
        self.begin(dirty=True, choice=BUTTON.Cancel)
        self.assertFalse(self.host._closing)
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.close_timer.isActive())
        self.host.close.assert_not_called()

    def test_name_dialog_cancel_leaves_open(self):
        self.begin(dirty=True, choice=BUTTON.Save)
        self.host._message_box.reset_mock()
        self.reply({"ok": False, "cancelled": True})
        self.host._message_box.assert_not_called()
        self.host.close.assert_not_called()
        self.assertFalse(self.host._closing)

    def test_storage_failure_keeps_open_by_default(self):
        self.begin()
        self.host._message_box.return_value = BUTTON.Cancel
        self.reply({"ok": False, "error": "The latest recovery or settings could not be written."})
        self.host.close.assert_not_called()
        self.assertFalse(self.host._allow_close)
        self.assertFalse(self.host._closing)

    def test_explicit_force_after_storage_failure_closes(self):
        self.begin()
        self.host._message_box.return_value = BUTTON.Close
        self.reply({"ok": False})
        self.host.close.assert_called_once()

    def test_repeated_close_does_not_report_a_premature_timeout(self):
        self.begin()
        self.host._message_box.reset_mock()
        self.host.closeEvent(QCloseEvent())
        self.host._message_box.assert_not_called()

    def test_late_completion_during_timeout_prompt_cannot_close(self):
        self.begin()
        request = self.request()[0]
        def timeout_prompt(*args):
            self.reply({"ok": True}, request=request)
            self.host.close.assert_not_called()
            return BUTTON.Cancel
        self.host._message_box.side_effect = timeout_prompt
        self.host._close_timed_out()
        self.assertFalse(self.host._closing)
        self.assertFalse(self.host._commands)
        self.host.close.assert_not_called()

    def test_late_status_reply_after_cancel_does_not_prompt_again(self):
        self.host.closeEvent(QCloseEvent())
        request = self.request()[0]
        self.host._close_timed_out()
        self.host._message_box.reset_mock()
        self.reply({"dirty": True, "saving": False}, request=request)
        self.host._message_box.assert_not_called()
        self.assertFalse(self.host._commands)

    def test_timeout_cancel_can_retry_without_replaying_old_completion(self):
        self.begin()
        old = self.request()[0]
        self.host._message_box.return_value = BUTTON.Cancel
        self.host._close_timed_out()
        self.begin()
        current = self.request()[0]
        self.reply({"ok": True}, request=old)
        self.host.close.assert_not_called()
        self.assertIn(current, self.host._commands)
        self.reply({"ok": True}, request=current)
        self.host.close.assert_called_once()

    def test_force_close_ignores_late_completion(self):
        self.begin()
        request = self.request()[0]
        self.host._message_box.return_value = BUTTON.Close
        self.host._close_timed_out()
        self.reply({"ok": True}, request=request)
        self.host.close.assert_called_once()

    def test_busy_state_does_not_enter_final_close(self):
        self.host.closeEvent(QCloseEvent())
        self.reply({"dirty": True, "saving": True})
        self.assertEqual(self.request()[1], "state")
        self.assertFalse(self.host._closing)
        self.assertFalse(self.host.close_timer.isActive())

    def test_malformed_envelopes_become_failed_outcomes(self):
        for payload in ("[]", "null", "1", '"text"', "{}", '{"ok":"yes"}', '{"ok":true,"value":[]}', "{"):
            with self.subTest(payload=payload):
                callback = Mock()
                self.host.command("state", {}, callback)
                self.host._command_result(self.request()[0], payload)
                result = callback.call_args.args[0]
                self.assertIs(result.get("ok"), False)
                self.assertIsInstance(result.get("error"), str)

    def test_incomplete_state_is_not_treated_as_clean(self):
        self.host.closeEvent(QCloseEvent())
        self.reply({})
        self.assertEqual(self.request()[1], "state")
        self.assertFalse(self.host._closing)
        self.host.close.assert_not_called()

    def test_truthy_non_boolean_success_does_not_close(self):
        self.begin()
        self.host._message_box.return_value = BUTTON.Cancel
        self.reply({"ok": "yes"})
        self.host.close.assert_not_called()

    def test_unknown_result_is_ignored(self):
        self.host._command_result("unknown", '{"ok":true,"value":{}}')
        self.assertFalse(self.host._commands)

    def test_live_user_wait_renews_watchdog_but_working_heartbeat_does_not(self):
        self.begin(dirty=True, choice=BUTTON.Save)
        request = self.request()[0]
        self.host.close_timer.stop()
        self.host._command_progress(request, "user-wait")
        self.assertTrue(self.host.close_timer.isActive())
        self.host.close_timer.stop()
        self.host._command_progress(request, "working")
        self.assertTrue(self.host.close_timer.isActive())
        self.host.close_timer.stop()
        self.host._command_progress(request, "working")
        self.assertFalse(self.host.close_timer.isActive())

    def test_unknown_progress_cannot_keep_close_alive(self):
        self.begin()
        self.host.close_timer.stop()
        self.host._command_progress("unknown", "user-wait")
        self.host._command_progress(self.request()[0], "nonsense")
        self.assertFalse(self.host.close_timer.isActive())

    def test_reload_fences_old_readiness_poll(self):
        self.host._ready = False
        self.host._check_ready()
        checked = self.host.page.runJavaScript.call_args.args[1]
        self.host.url = QUrl("http://127.0.0.1:9999/tools/fabric-editor/index.html")
        self.host.view = self.host.error_panel
        self.host.reload_editor()
        checked('{"ready":true}')
        self.assertFalse(self.host._ready)

    def test_reload_cancels_old_commands_and_close_watchdog(self):
        self.begin()
        request = self.request()[0]
        self.host.url = QUrl("http://127.0.0.1:9999/tools/fabric-editor/index.html")
        self.host.view = self.host.error_panel
        self.host.reload_editor()
        self.reply({"ok": True}, request=request)
        self.host.close.assert_not_called()
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.close_timer.isActive())

    def test_renderer_failure_discards_pending_close(self):
        self.begin()
        request = self.request()[0]
        self.host._show_failure("Renderer stopped")
        self.reply({"ok": True}, request=request)
        self.host.close.assert_not_called()
        self.assertFalse(self.host.close_timer.isActive())

    def test_reentrant_close_in_save_question_does_not_open_warning(self):
        self.host.closeEvent(QCloseEvent())
        def choose(*args):
            self.host.closeEvent(QCloseEvent())
            return BUTTON.Cancel
        self.host._message_box.side_effect = choose
        self.reply({"dirty": True, "saving": False})
        self.host._message_box.assert_called_once()

    def test_external_open_does_not_dispatch_behind_close_prompt(self):
        self.host._close_prompt = True
        self.host._queued_requests.append({"mode": "new", "project": ""})
        self.host._dispatch_open()
        self.host.page.runJavaScript.assert_not_called()
        self.assertEqual(len(self.host._queued_requests), 1)

    def test_repeated_close_while_busy_does_not_recurse(self):
        self.host.command("open", {}, Mock())
        def busy(*args):
            self.host.closeEvent(QCloseEvent())
            return BUTTON.Ok
        self.host._message_box.side_effect = busy
        self.host.closeEvent(QCloseEvent())
        self.host._message_box.assert_called_once()

    def test_dismissed_save_question_is_cancel_not_discard(self):
        self.begin(dirty=True, choice=BUTTON.NoButton)
        self.assertFalse(self.host._closing)
        self.assertFalse(self.host._commands)
        self.host.close.assert_not_called()

    def test_shutdown_invalidates_callbacks_without_reclosing(self):
        self.begin()
        request = self.request()[0]
        self.host.page = self.host.server = None
        self.host.shutdown()
        self.reply({"ok": True}, request=request)
        self.host.close.assert_not_called()
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.close_timer.isActive())

    def open_request(self):
        self.host._queued_requests.append({"mode": "new", "project": ""})
        self.host._dispatch_open()
        return self.host._open_request_id

    def test_open_failure_is_presented_and_does_not_strand_queue(self):
        request = self.open_request()
        self.host._command_result(request, json.dumps({"ok": False, "error": "Failed to open"}))
        self.host._message_box.assert_called_once()
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.open_timer.isActive())

    def test_lost_open_reply_reads_receipt_without_reexecuting(self):
        request = self.open_request()
        self.host._open_deadline()
        query, checked = self.host.page.runJavaScript.call_args.args
        self.assertIn(".outcome", query)
        checked(json.dumps({"state": "complete", "result": {"ok": True, "value": {"ok": True}}}))
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.open_timer.isActive())
        self.assertEqual(self.host.page.runJavaScript.call_count, 2)
        self.host._message_box.assert_not_called()

    def test_uncertain_open_keeps_request_and_can_force_close(self):
        request = self.open_request()
        self.host._open_deadline()
        checked = self.host.page.runJavaScript.call_args.args[1]
        checked('{"state":"working"}')
        self.assertTrue(self.host._open_uncertain)
        self.assertIn(request, self.host._commands)
        self.host._message_box.return_value = BUTTON.Close
        self.host.closeEvent(QCloseEvent())
        self.host.close.assert_called_once()

    def test_user_wait_keeps_open_deadline_alive(self):
        request = self.open_request()
        self.host.open_timer.stop()
        self.host._command_progress(request, "user-wait")
        self.assertTrue(self.host.open_timer.isActive())
        self.host.open_timer.stop()
        self.host._command_progress(request, "working")
        self.assertTrue(self.host.open_timer.isActive())
        self.host.open_timer.stop()
        self.host._command_progress(request, "working")
        self.assertFalse(self.host.open_timer.isActive())

    def test_arbitrary_navigation_invalidates_pending_reply(self):
        request = self.open_request()
        self.host._page_load_started()
        self.assertFalse(self.host._ready)
        self.host._command_result(request, json.dumps({"ok": True, "value": {"ok": True}}))
        self.assertFalse(self.host._commands)
        self.assertFalse(self.host.open_timer.isActive())

    def test_stale_receipt_probe_cannot_change_new_page(self):
        self.open_request()
        self.host._open_deadline()
        checked = self.host.page.runJavaScript.call_args.args[1]
        self.host._page_load_started()
        checked('{"state":"working"}')
        self.assertFalse(self.host._open_uncertain)
        self.host._message_box.assert_not_called()


if __name__ == "__main__":
    unittest.main()
