from pathlib import Path
import ctypes
import json
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui import display_language
from kfps_ui.settings_service import SettingsService

ACK = "dcinsideKoreanNotice202609Acknowledged"


class DisplayLanguageTests(unittest.TestCase):
    def test_only_korean_ui_language_matches(self):
        for language_id, expected in ((0x0412, True), (0x0812, True), (0x0409, False),
                                      (0x0809, False), (0x0407, False), (0x0411, False),
                                      (0x0804, False), (0x1404, False), (0, False), (0x1400, False)):
            with self.subTest(language_id=language_id):
                kernel = Mock()
                kernel.GetUserDefaultUILanguage.return_value = language_id
                with patch.object(display_language.sys, "platform", "win32"), patch.object(
                    display_language.ctypes, "WinDLL", return_value=kernel, create=True
                ), patch.dict("os.environ", {"LANG": "ko_KR.UTF-8", "LANGUAGE": "ko", "LC_ALL": "ko_KR"}):
                    self.assertEqual(display_language.is_korean_display_language(), expected)
                kernel.GetUserDefaultUILanguage.assert_called_once_with()
                self.assertEqual(kernel.GetUserDefaultUILanguage.argtypes, [])
                self.assertIs(kernel.GetUserDefaultUILanguage.restype, ctypes.c_ushort)
                self.assertEqual(kernel.method_calls, [("GetUserDefaultUILanguage", (), {})])

    def test_detection_failure_does_not_show_korean_notice(self):
        with patch.object(display_language.sys, "platform", "win32"), patch.object(
            display_language.ctypes, "WinDLL", side_effect=OSError("unavailable"), create=True
        ), self.assertLogs("tools.kfps_display_language", level="WARNING"):
            self.assertFalse(display_language.is_korean_display_language())

    def test_non_windows_does_not_use_locale_or_load_windows_api(self):
        with patch.object(display_language.sys, "platform", "linux"), patch.object(
            display_language.ctypes, "WinDLL", create=True
        ) as load:
            self.assertFalse(display_language.is_korean_display_language())
            load.assert_not_called()


class DcinsideKoreanWelcomeTests(unittest.TestCase):
    def test_restart_reset_and_old_preferences_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": True,
                                        "communityJoinNoticeAcknowledged": True,
                                        "backgroundRemoverNoticeAcknowledged": True,
                                        "reducedMotion": True, "backupFolder": "D:/backups"}))
            with patch("kfps_ui.settings_service.is_korean_display_language", return_value=True):
                service = SettingsService(path)
            self.assertTrue(service.koreanDisplayLanguage)
            self.assertFalse(service.dcinsideKoreanNoticeAcknowledged)
            service.acknowledgeDcinsideKoreanNotice()
            restarted = SettingsService(path)
            self.assertTrue(restarted.dcinsideKoreanNoticeAcknowledged)
            self.assertTrue(restarted.supportUpscalerNoticeAcknowledged)
            self.assertTrue(restarted.communityJoinNoticeAcknowledged)
            self.assertTrue(restarted.backgroundRemoverNoticeAcknowledged)
            self.assertTrue(restarted.reducedMotion)
            self.assertEqual(restarted.backupFolder, "D:/backups")
            restarted.reset()
            self.assertTrue(SettingsService(path).dcinsideKoreanNoticeAcknowledged)

    def test_language_is_rechecked_on_launch_and_never_read_from_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"koreanDisplayLanguage": True}))
            with patch("kfps_ui.settings_service.is_korean_display_language", return_value=False):
                service = SettingsService(path)
                self.assertFalse(service.koreanDisplayLanguage)
                self.assertFalse(service.dcinsideKoreanNoticeAcknowledged)
                service.save()
            with patch("kfps_ui.settings_service.is_korean_display_language", return_value=True):
                service = SettingsService(path)
                self.assertTrue(service.koreanDisplayLanguage)
                self.assertFalse(service.dcinsideKoreanNoticeAcknowledged)
                service.acknowledgeDcinsideKoreanNotice()
            with patch("kfps_ui.settings_service.is_korean_display_language", return_value=False):
                self.assertTrue(SettingsService(path).dcinsideKoreanNoticeAcknowledged)
            self.assertNotIn("koreanDisplayLanguage", json.loads(path.read_text()))

    def test_invalid_acknowledgements_and_independent_notices(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for value in ("false", "true", 1, None, [], {}):
                path.write_text(json.dumps({ACK: value}))
                self.assertFalse(SettingsService(path).dcinsideKoreanNoticeAcknowledged)
            service = SettingsService(path)
            service.acknowledgeDcinsideKoreanNotice()
            self.assertFalse(service.supportUpscalerNoticeAcknowledged)
            self.assertFalse(service.communityJoinNoticeAcknowledged)
            self.assertFalse(service.backgroundRemoverNoticeAcknowledged)

    def test_read_only_settings_allow_session_dismissal_but_not_false_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            service = SettingsService(path)
            with patch.object(service, "save", side_effect=PermissionError("read only")), self.assertLogs(
                "kfps_ui.settings_service", level="WARNING"
            ):
                service.acknowledgeDcinsideKoreanNotice()
            self.assertTrue(service.dcinsideKoreanNoticeAcknowledged)
            self.assertFalse(SettingsService(path).dcinsideKoreanNoticeAcknowledged)

    def test_queue_and_message_contract(self):
        main = (UI / "qml/Main.qml").read_text(encoding="utf-8")
        timer = main.rsplit("Timer {", 1)[1]
        for condition in ("window.visible && !screenshotMode && settings.koreanDisplayLanguage",
                          "settings.supportUpscalerNoticeAcknowledged && !featureWelcome.visible",
                          "settings.communityJoinNoticeAcknowledged && !communityWelcome.visible",
                          "settings.backgroundRemoverNoticeAcknowledged && !backgroundRemoverWelcome.visible",
                          "!settings.dcinsideKoreanNoticeAcknowledged && !dcinsideKoreanWelcome.visible"):
            self.assertIn(condition, timer)
        overlay = (UI / "qml/shell/DcinsideKoreanWelcomeOverlay.qml").read_text(encoding="utf-8")
        for required in ("Popup.NoAutoClose", "settings.acknowledgeDcinsideKoreanNotice()",
                         "알겠어요!", "-Kloudy", "공개 지원 게시판", "포함 여부를 직접 선택",
                         "저와 권한이 있는 운영진만", "Discord로 로그인해 전송"):
            self.assertIn(required, overlay)
        for forbidden in ("openUrl", "openSupportForm", "reportService", "저만 볼 수", "자동으로 제 Discord"):
            self.assertNotIn(forbidden, overlay)
        self.assertEqual(overlay.count("PrimaryButton {"), 1)


if __name__ == "__main__":
    unittest.main()
