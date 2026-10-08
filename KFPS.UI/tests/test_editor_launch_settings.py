import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src")]
from kfps_ui.settings_service import SettingsService
from kfps_ui.desktop_service import DesktopService
from kfps_editor.launch_preferences import find_chrome, use_chrome


class EditorLaunchSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "runtime/qml-shell-settings.json"
        self.settings = SettingsService(self.path)

    def test_default_and_repeated_toggle_roundtrips(self):
        self.assertFalse(self.settings.editorUseChrome)
        self.assertFalse(use_chrome(self.root))
        self.assertFalse(self.path.exists())
        for value in (True, False, True, False):
            self.settings.editorUseChrome = value
            self.assertEqual(SettingsService(self.path).editorUseChrome, value)
            self.assertEqual(use_chrome(self.root), value)

    def test_only_explicit_boolean_enables_chrome(self):
        self.path.parent.mkdir()
        for value in (None, [], {}, 1, "true", "chrome", False):
            self.path.write_text(json.dumps({"editorUseChrome": value}))
            self.assertFalse(SettingsService(self.path).editorUseChrome)
            self.assertFalse(use_chrome(self.root))
        for value in (None, [], {}, 1, "true", "chrome"):
            self.settings.editorUseChrome = value
            self.assertFalse(self.settings.editorUseChrome)

    def test_corrupt_oversized_and_unreadable_file_do_not_block_default(self):
        self.path.parent.mkdir()
        for data in (b'{', b'[]', b'null', b'\xff\xfe', b' ' * (1024 * 1024 + 1)):
            self.path.write_bytes(data)
            self.assertFalse(use_chrome(self.root))
            self.assertEqual(self.path.read_bytes(), data)
        with patch.object(Path, 'open', side_effect=PermissionError('locked')):
            self.assertFalse(use_chrome(self.root))

    def test_independent_of_graphics_and_unrelated_settings(self):
        self.settings.editorGraphics = "d3d11"
        self.settings.editorUseChrome = True
        self.settings.reducedMotion = True
        self.assertTrue(use_chrome(self.root))
        self.settings.editorUseChrome = False
        saved = SettingsService(self.path)
        self.assertEqual(saved.editorGraphics, "d3d11")
        self.assertTrue(saved.reducedMotion)

    def test_reset_returns_to_desktop(self):
        self.settings.editorUseChrome = True
        self.settings.reset()
        self.assertFalse(use_chrome(self.root))

    def test_failed_save_rolls_back_choice(self):
        self.settings.editorUseChrome = True
        before = self.path.read_bytes()
        with patch.object(self.settings, "save", side_effect=PermissionError("test")):
            self.settings.editorUseChrome = False
        self.assertTrue(self.settings.editorUseChrome)
        self.assertEqual(self.path.read_bytes(), before)


class ChromeInstallSettingsTests(unittest.TestCase):
    def setUp(self):
        discovery = patch("kfps_ui.desktop_service.find_chrome", return_value=None)
        self.discovery = discovery.start()
        self.addCleanup(discovery.stop)
        self.log = Mock()
        self.desktop = DesktopService(Mock(), self.log)

    def test_detects_install_and_removal_without_restarting(self):
        signals = []
        self.desktop.chromeStatusChanged.connect(lambda: signals.append(True))
        self.assertFalse(self.desktop.chromeInstalled)
        self.discovery.return_value = Path("C:/Chrome/chrome.exe")
        self.desktop.refreshChromeStatus()
        self.assertTrue(self.desktop.chromeInstalled)
        self.desktop.refreshChromeStatus()
        self.assertEqual(len(signals), 1)
        self.discovery.return_value = None
        self.desktop.refreshChromeStatus()
        self.assertFalse(self.desktop.chromeInstalled)
        self.assertEqual(len(signals), 2)

    def test_install_opens_only_official_page_on_explicit_action(self):
        with patch("kfps_ui.desktop_service.QDesktopServices.openUrl", return_value=True) as opened:
            self.desktop.refreshChromeStatus()
            opened.assert_not_called()
            self.desktop.openChromeInstallPage()
            self.assertEqual(opened.call_args.args[0].toString(), "https://www.google.com/chrome/")
            opened.assert_called_once()
            self.assertFalse(self.desktop.chromeInstalled)
            self.assertEqual(self.desktop.chromeInstallError, "")

    def test_already_installed_does_not_open_or_reinstall(self):
        self.discovery.return_value = Path("C:/Chrome/chrome.exe")
        with patch("kfps_ui.desktop_service.QDesktopServices.openUrl") as opened:
            self.desktop.openChromeInstallPage()
            opened.assert_not_called()
        self.assertTrue(self.desktop.chromeInstalled)

    def test_failed_browser_open_is_visible_and_retryable(self):
        with patch("kfps_ui.desktop_service.QDesktopServices.openUrl", return_value=False) as opened:
            self.desktop.openChromeInstallPage()
            self.assertIn("google.com/chrome", self.desktop.chromeInstallError)
            opened.side_effect = OSError("No registered browser")
            self.desktop.openChromeInstallPage()
            self.assertIn("google.com/chrome", self.desktop.chromeInstallError)
            opened.side_effect = None
            opened.return_value = True
            self.desktop.openChromeInstallPage()
            self.assertEqual(self.desktop.chromeInstallError, "")
        self.log.append.assert_any_call(
            "Could not open Chrome installation page: No registered browser", "error")

    def test_detection_after_external_install_clears_page_error(self):
        with patch("kfps_ui.desktop_service.QDesktopServices.openUrl", return_value=False):
            self.desktop.openChromeInstallPage()
        self.discovery.return_value = Path("C:/Chrome/chrome.exe")
        self.desktop.refreshChromeStatus()
        self.assertTrue(self.desktop.chromeInstalled)
        self.assertEqual(self.desktop.chromeInstallError, "")

    def test_shared_discovery_skips_unreadable_install_location(self):
        expected = Path("C:/Programs/Google/Chrome/Application/chrome.exe")
        def check(path):
            if str(path).startswith("C:\\UserLocal"):
                raise PermissionError("unreadable")
            return path == expected
        with patch.dict("os.environ", {"LocalAppData": "C:/UserLocal", "ProgramFiles": "C:/Programs"}, clear=True), \
             patch.object(Path, "is_file", side_effect=check, autospec=True):
            self.assertEqual(find_chrome(), expected)


if __name__ == "__main__":
    unittest.main()
