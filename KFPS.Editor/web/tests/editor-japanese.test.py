"""Japanese display-language selection without touching personal settings."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from kfps_editor import localization


class JapaneseSelectionTests(unittest.TestCase):
    def test_persisted_languages_and_unknown_fields_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            for system, saved, expected in [
                ("ja-JP", None, "ja"), ("JA_jp", None, "ja"),
                ("ja-JP", "ko", "ko"), ("ja-JP", "en", "en"),
                ("en-US", "ja", "ja"), ("ko-KR", "ja", "ja"),
                ("ja-JP", "unknown", "ja"), ("en-US", None, "en"),
            ]:
                payload = {"settings": {"kloudyFabricLanguage": saved, "custom-kept": "unchanged"}, "future": {"untouched": [1, 2]}}
                prefs = runtime / "preferences.json"
                prefs.write_text(json.dumps(payload), encoding="utf-8")
                before = prefs.read_bytes()
                self.assertEqual(localization.EditorTranslator(ROOT, runtime, system).language, expected)
                self.assertEqual(prefs.read_bytes(), before)

    def test_windows_ui_language_not_regional_or_keyboard_locale(self):
        class Function:
            def __init__(self, value): self.value = value
            def __call__(self): return self.value

        class Kernel:
            def __init__(self, value): self.GetUserDefaultUILanguage = Function(value)

        for identifier, expected in [(0x0411, "ja"), (0x0412, "ko"), (0x0409, "en"), (0x0811, "ja")]:
            with patch.object(localization.sys, "platform", "win32"), patch("ctypes.WinDLL", return_value=Kernel(identifier)):
                self.assertEqual(localization.editor_system_language(), expected)

    def test_ui_language_query_failure_is_safe(self):
        with patch.object(localization.sys, "platform", "win32"), patch("ctypes.WinDLL", side_effect=OSError("fixture")):
            self.assertEqual(localization.editor_system_language(), "en")


if __name__ == "__main__":
    unittest.main()
