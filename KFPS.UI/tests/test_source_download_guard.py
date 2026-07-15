from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kfps_ui.source_download_guard import ALLOW_ENV, evaluate_source_download_guard


class SourceDownloadGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {ALLOW_ENV: ""}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    @staticmethod
    def touch(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def make_source(self, name: str = "kloudys-forza-painter-suite-main") -> Path:
        source = self.root / name
        source.mkdir(parents=True)
        return source

    def test_named_source_archive_is_blocked(self):
        status = evaluate_source_download_guard(self.make_source())
        self.assertTrue(status.blocked)
        self.assertIn("source archive", status.reason.lower())

    def test_source_archive_stays_blocked_when_python_is_added(self):
        source = self.make_source()
        self.touch(source / "python" / "python.exe")
        self.assertTrue(evaluate_source_download_guard(source).blocked)

    def test_source_files_are_detected_after_folder_is_renamed(self):
        source = self.make_source("renamed-download")
        self.touch(source / ".gitignore")
        self.touch(source / "requirements.txt")
        self.touch(source / "tools" / "native_launcher" / "KFPSLauncher.cs")
        self.assertTrue(evaluate_source_download_guard(source).blocked)

    def test_release_layout_without_bundled_python_is_allowed(self):
        outer = self.root / "KFPS-3.0.99-binary"
        app_root = outer / "KloudysFH6Painter"
        app_root.mkdir(parents=True)
        self.touch(outer / "KFPS.exe")
        (outer / "Images").mkdir()
        self.assertFalse(evaluate_source_download_guard(app_root).blocked)

    def test_release_layout_takes_precedence_over_source_markers(self):
        outer = self.root / "KFPS-3.0.99-binary"
        app_root = outer / "KloudysFH6Painter"
        app_root.mkdir(parents=True)
        self.touch(outer / "KFPS.exe")
        (outer / "Images").mkdir()
        self.touch(app_root / ".gitignore")
        self.touch(app_root / "requirements.txt")
        self.touch(app_root / "tools" / "native_launcher" / "KFPSLauncher.cs")
        self.assertFalse(evaluate_source_download_guard(app_root).blocked)

    def test_active_git_checkout_is_allowed(self):
        source = self.make_source()
        (source / ".git").mkdir()
        self.assertFalse(evaluate_source_download_guard(source).blocked)

    def test_explicit_argument_bypasses_guard(self):
        source = self.make_source()
        self.assertFalse(evaluate_source_download_guard(source, allow=True).blocked)

    def test_environment_bypasses_guard(self):
        source = self.make_source()
        os.environ[ALLOW_ENV] = "yes"
        self.assertFalse(evaluate_source_download_guard(source).blocked)

    def test_marker_file_bypasses_guard(self):
        source = self.make_source()
        self.touch(source / "ALLOW_SOURCE_DOWNLOAD.txt")
        self.assertFalse(evaluate_source_download_guard(source).blocked)

    def test_existing_non_source_flat_install_remains_allowed(self):
        app_root = self.root / "KFPS Personal"
        app_root.mkdir()
        self.touch(app_root / "python" / "python.exe")
        self.assertFalse(evaluate_source_download_guard(app_root).blocked)


if __name__ == "__main__":
    unittest.main()
