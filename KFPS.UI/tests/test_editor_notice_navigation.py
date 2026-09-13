import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "KFPS.Editor/src"))
from kfps_editor.host import EditorPage, QUrl, QWebEnginePage


class EditorNoticeNavigationTests(unittest.TestCase):
    def test_support_link_opens_externally_without_replacing_editor(self):
        page = SimpleNamespace(origin=QUrl("http://127.0.0.1:42001"))
        url = QUrl("https://ko-fi.com/O7O020EQNQ")
        clicked = QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        with patch("kfps_editor.host.QDesktopServices.openUrl", return_value=True) as opened:
            self.assertFalse(EditorPage.acceptNavigationRequest(page, url, clicked, True))
            opened.assert_called_once_with(url)

    def test_support_is_not_opened_by_script_or_frame_navigation(self):
        page = SimpleNamespace(origin=QUrl("http://127.0.0.1:42001"))
        with patch("kfps_editor.host.QDesktopServices.openUrl") as opened:
            for kind, main in [(QWebEnginePage.NavigationType.NavigationTypeOther, True),
                               (QWebEnginePage.NavigationType.NavigationTypeLinkClicked, False)]:
                self.assertFalse(EditorPage.acceptNavigationRequest(
                    page, QUrl("https://ko-fi.com/O7O020EQNQ"), kind, main))
            opened.assert_not_called()
