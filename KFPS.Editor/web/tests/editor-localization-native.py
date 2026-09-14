"""Real Qt-owned localized dialogs. Uses a disposable profile, no editor server."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_editor.host import EditorDesktop
from kfps_editor.localization import editor_system_language


class NativeLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipUnless(sys.platform == "win32", "Windows display-language selection")
    def test_display_language_not_regional_format(self):
        with patch("tools.kfps_display_language.is_korean_display_language", return_value=True):
            self.assertEqual(editor_system_language(), "ko")
        with patch("tools.kfps_display_language.is_korean_display_language", return_value=False):
            self.assertEqual(editor_system_language(), "en")

    def test_native_dialogs_preserve_buttons_choice_and_plain_text(self):
        for language in ("en", "ko"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary:
                runtime = Path(temporary)
                (runtime / "preferences.json").write_text(json.dumps({"settings": {"kloudyFabricLanguage": language}}), encoding="utf-8")
                host = EditorDesktop(ROOT, runtime)
                captured = {}
                flags = QMessageBox.StandardButton

                def inspect_and_cancel():
                    box = QApplication.activeModalWidget()
                    if not isinstance(box, QMessageBox):
                        captured["error"] = "Missing native QMessageBox"
                        return
                    try:
                        captured.update(title=box.windowTitle(), text=box.text(), plain=box.textFormat() == Qt.TextFormat.PlainText,
                                        default=box.defaultButton().text(), buttons=[box.button(flag).text() for flag in (flags.Save, flags.Discard, flags.Cancel)])
                        output = os.environ.get("KFPS_LOCALIZATION_SCREENSHOTS")
                        if output:
                            folder = Path(output)
                            folder.mkdir(parents=True, exist_ok=True)
                            box.grab().save(str(folder / f"native-close-{language}.png"))
                    finally:
                        box.button(flags.Cancel).click()

                try:
                    QTimer.singleShot(150, inspect_and_cancel)
                    result = host._message_box("question", "Save before closing?", "This project has unsaved changes.", flags.Save | flags.Discard | flags.Cancel, flags.Cancel)
                    self.assertEqual(result, flags.Cancel)
                    self.assertTrue(captured["plain"])
                    self.assertEqual(captured["title"], host.translator.tr("Save before closing?"))
                    self.assertEqual(captured["buttons"], [host.translator.tr(key) for key in ("Save", "Discard", "Cancel")])
                    self.assertEqual(captured["default"], host.translator.tr("Cancel"))
                    self.assertEqual(host.error_label.textFormat(), Qt.TextFormat.PlainText)
                    literal = "<b>Save {1}</b> 한국어"
                    self.assertEqual(host.translator.message(literal), literal)
                finally:
                    host.shutdown()
                    host.close()
                    host.deleteLater()
                    self.app.processEvents()

    def test_startup_errors_are_available_in_both_languages(self):
        from kfps_editor.localization import EditorTranslator
        for language in ("en", "ko"):
            translator = EditorTranslator(ROOT, Path("missing-test-profile"), language)
            for role in ("instance-lock", "startup"):
                from kfps_editor.manifest import native_source
                import ast
                tree = ast.parse(native_source(role, ROOT).read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                        argument = node.exc.args[0]
                        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                            self.assertIn(argument.value, translator.messages)
                            if language == "ko":
                                self.assertNotEqual(translator.tr(argument.value), argument.value)


if __name__ == "__main__":
    unittest.main()
