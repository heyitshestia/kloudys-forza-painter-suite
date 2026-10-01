import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT / "KFPS.Editor/src")]
from kfps_ui.app_paths import AppPaths
from kfps_ui.settings_service import SettingsService
from kfps_editor.graphics import read_preference, select_policy


class EditorGraphicsSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        paths = AppPaths(self.root, self.root, self.root, self.root,
                         self.root / "runtime", Path(sys.executable))
        self.path = paths.settings_file
        self.settings = SettingsService(self.path)

    def test_roundtrip_shared_file_for_both_launch_origins(self):
        self.assertEqual(self.settings.editorGraphics, "auto")
        for mode in ("d3d11", "opengl", "auto"):
            self.settings.editorGraphics = mode
            self.assertEqual(SettingsService(self.path).editorGraphics, mode)
            self.assertEqual(read_preference(self.root)[0], mode)
            self.assertEqual(select_policy(self.root, probe=lambda: ()).backend,
                             "d3d11" if mode == "d3d11" else "opengl")

    def test_bad_values_normalize_or_are_rejected(self):
        for value in (None, [], {}, True, "vulkan", "Direct3D 11"):
            self.path.parent.mkdir(exist_ok=True)
            self.path.write_text(json.dumps({"editorGraphics": value}))
            loaded = SettingsService(self.path)
            self.assertEqual(loaded.editorGraphics, "auto")
            loaded.editorGraphics = value
            self.assertEqual(loaded.editorGraphics, "auto")

    def test_reset_and_unrelated_save_preserve_expected_settings(self):
        self.settings.editorGraphics = "d3d11"
        self.settings.reducedMotion = True
        self.assertEqual(read_preference(self.root)[0], "d3d11")
        self.assertTrue(json.loads(self.path.read_text())["reducedMotion"])
        self.settings.reset()
        self.assertEqual(read_preference(self.root)[0], "auto")

    def test_failed_save_keeps_ui_and_disk_on_previous_choice(self):
        self.settings.editorGraphics = "opengl"
        before = self.path.read_bytes()
        with patch.object(self.settings, "save", side_effect=PermissionError("test")):
            self.settings.editorGraphics = "d3d11"
        self.assertEqual(self.settings.editorGraphics, "opengl")
        self.assertEqual(self.path.read_bytes(), before)

    def test_main_app_renderer_does_not_read_editor_selection(self):
        from kfps_ui.renderer_policy import select_renderer_policy
        self.settings.editorGraphics = "d3d11"
        self.assertEqual(select_renderer_policy({}).name, "opengl")


if __name__ == "__main__":
    unittest.main()
