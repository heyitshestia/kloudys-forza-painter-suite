import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT)]
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEnginePage
from kfps_ui import support_browser as browser
from kfps_ui.support_window import ReportPage, ReportWindow


class BrowserLaunchTests(unittest.TestCase):
    url = QUrl("https://support.example/auth/native?ticket=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    executable = "C:/Browser With Spaces/default-browser.exe"

    def test_direct_default_browser_wins_even_when_qt_handler_is_broken(self):
        with patch.object(browser, "default_browser_executable", return_value=self.executable), \
             patch.object(browser.QProcess, "startDetached", return_value=(True, 42)) as direct, \
             patch.object(browser.QDesktopServices, "openUrl", return_value=False) as system, \
             self.assertLogs("kfps-report-window", level="INFO") as logs:
            self.assertEqual(browser.open_browser_url(self.url), "default-executable")
            direct.assert_called_once_with(self.executable, [self.url.toString()])
            system.assert_not_called()
        self.assertNotIn("ticket", " ".join(logs.output))
        self.assertNotIn(self.executable, " ".join(logs.output))

    def test_failed_or_missing_executable_uses_system_default_handler(self):
        for executable, result in (("", (False, 0)), (self.executable, (False, 0)),
                                   (self.executable, OSError("synthetic")),
                                   (self.executable, RuntimeError("synthetic"))):
            with self.subTest(executable=executable, result=result), \
                 patch.object(browser, "default_browser_executable", return_value=executable), \
                 patch.object(browser.QProcess, "startDetached", side_effect=result if isinstance(result, Exception) else None,
                              return_value=result) as direct, \
                 patch.object(browser.QDesktopServices, "openUrl", return_value=True) as system:
                self.assertEqual(browser.open_browser_url(self.url), "system-handler")
                system.assert_called_once_with(self.url)
                self.assertEqual(direct.call_count, bool(executable))

    def test_both_methods_fail_without_raising_or_choosing_another_browser(self):
        for result in (False, OSError("private details"), RuntimeError("private details")):
            with self.subTest(result=result), \
                 patch.object(browser, "default_browser_executable", return_value=self.executable), \
                 patch.object(browser.QProcess, "startDetached", return_value=(False, 0)), \
                 patch.object(browser.QDesktopServices, "openUrl", side_effect=result if isinstance(result, Exception) else None,
                              return_value=result), self.assertLogs("kfps-report-window", level="INFO") as logs:
                self.assertEqual(browser.open_browser_url(self.url), "failed")
                self.assertNotIn("private details", " ".join(logs.output))

    def test_url_is_one_encoded_argument_and_unsafe_schemes_are_refused(self):
        with patch.object(browser, "default_browser_executable", return_value=self.executable), \
             patch.object(browser.QProcess, "startDetached", return_value=(True, 42)) as direct:
            self.assertEqual(browser.open_browser_url(QUrl('https://example.test/a b?q="x"&v=two')), "default-executable")
            args = direct.call_args.args[1]
            self.assertEqual(len(args), 1)
            self.assertIn("%20", args[0])
            self.assertIn("%22", args[0])
        for value in ("", "file:///C:/test.exe", "javascript:alert(1)", "ms-edge:https://example.test",
                      "https://user:password@example.test", "https://"):
            with self.subTest(value=value), patch.object(browser.QProcess, "startDetached") as direct, \
                 patch.object(browser.QDesktopServices, "openUrl") as system:
                self.assertEqual(browser.open_browser_url(QUrl(value)), "failed")
                direct.assert_not_called(); system.assert_not_called()

    def test_native_auth_validates_ticket_and_acknowledges_launch_failure(self):
        identifier = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        window = SimpleNamespace(auth_inflight=True, origin="https://support.example", run=Mock(), logger=logging.getLogger("test"))
        valid = {"id": identifier, "url": self.url.toString()}
        with patch("kfps_ui.support_window.open_browser_url", return_value="failed") as opened:
            for value in (None, {}, {**valid, "id": "../private"}, {**valid, "url": valid["url"] + "#bad"},
                          {**valid, "url": "https://elsewhere.test/"}):
                ReportWindow.launch_auth(window, value)
            opened.assert_not_called(); window.run.assert_not_called()
            ReportWindow.launch_auth(window, valid)
            opened.assert_called_once_with(self.url)
            self.assertIn(",false)", window.run.call_args.args[0])
            self.assertFalse(window.auth_inflight)

    def test_real_user_links_use_external_browser_never_embedded_discord(self):
        click = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        other = QWebEnginePage.NavigationType.NavigationTypeOther
        page = SimpleNamespace(form_origin="https://support.example")
        with patch("kfps_ui.support_window.open_browser_url", return_value="default-executable") as opened:
            self.assertFalse(ReportPage.acceptNavigationRequest(page, self.url, click, True))
            opened.assert_called_once_with(self.url)
            opened.reset_mock()
            self.assertFalse(ReportPage.acceptNavigationRequest(page, self.url, other, True))
            self.assertTrue(ReportPage.acceptNavigationRequest(page, QUrl("https://support.example/"), other, True))
            opened.assert_not_called()
            window = SimpleNamespace(origin=page.form_origin)
            request = SimpleNamespace(requestedUrl=lambda: self.url, isUserInitiated=lambda: True)
            ReportWindow.open_external(window, request)
            opened.assert_called_once_with(self.url)
            opened.reset_mock()
            request.isUserInitiated = lambda: False
            ReportWindow.open_external(window, request)
            opened.assert_not_called()

    def test_language_switch_updates_native_chrome_without_launching_auth(self):
        window = SimpleNamespace(auth_inflight=True, korean=False, _status_copy=("Retry loading", "다시 불러오기"),
                                 retry=Mock(), status=Mock(), setWindowTitle=Mock(), launch_auth=Mock())
        window.tr_text=lambda en,ko:ko if window.korean else en
        ReportWindow.review_state(window,{"language":"ko","request":None})
        self.assertTrue(window.korean)
        window.setWindowTitle.assert_called_with("KFPS - 문제 신고")
        window.retry.setText.assert_called_with("다시 시도")
        window.status.setText.assert_called_with("다시 불러오기")
        ReportWindow.review_state(window,{"language":"invalid","request":None})
        self.assertTrue(window.korean)
        ReportWindow.review_state(window,{"language":"en","request":None})
        self.assertFalse(window.korean)
        window.setWindowTitle.assert_called_with("KFPS - Report a Problem")
        self.assertTrue(all(call.args==(None,) for call in window.launch_auth.call_args_list))


if __name__ == "__main__":
    unittest.main()
