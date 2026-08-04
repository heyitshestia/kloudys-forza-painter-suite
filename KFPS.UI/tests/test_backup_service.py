from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from kfps_ui.app_paths import AppPaths
from kfps_ui.backup_service import BACKUP_FOLDER_NAME, BackupService, create_imgs_snapshot
from kfps_ui.settings_service import SettingsService

APP = QCoreApplication.instance() or QCoreApplication([])


class DummyLog:
    def __init__(self):
        self.messages = []

    def append(self, message, level="info"):
        self.messages.append((message, level))


class BackupServiceTests(unittest.TestCase):
    def test_service_runs_snapshot_off_the_ui_thread_and_reports_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_root = root / "app"
            imgs = app_root / "imgs"
            imgs.mkdir(parents=True)
            (imgs / "Artwork.json").write_text('{"shapes": []}\n', encoding="utf-8")
            destination = root / "destination"
            destination.mkdir()
            runtime = app_root / "runtime"
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", runtime, app_root / "python" / "python.exe")
            settings = SettingsService(runtime / "settings.json")
            settings.backupFolder = str(destination)
            service = BackupService(paths, settings, DummyLog())
            try:
                service.backupImgs()
                deadline = time.monotonic() + 5
                while service.running and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(0.01)
                APP.processEvents()
                self.assertFalse(service.running)
                self.assertIn("Backup complete", service.status)
                self.assertTrue((Path(service.lastSnapshot) / "imgs" / "Artwork.json").is_file())
            finally:
                service._executor.shutdown(wait=True, cancel_futures=True)

    def test_snapshots_are_complete_content_aware_and_append_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            imgs = root / "app" / "imgs"
            destination = root / "backup-drive"
            generated = imgs / "generated"
            previews = imgs / "previews"
            empty = imgs / "empty-folder"
            generated.mkdir(parents=True)
            previews.mkdir(parents=True)
            empty.mkdir(parents=True)
            destination.mkdir()
            artwork = generated / "Artwork.json"
            preview = previews / "Artwork.png"
            artwork.write_text('{"version": 1}\n', encoding="utf-8")
            preview.write_bytes(b"preview-v1")

            first = create_imgs_snapshot(
                imgs,
                destination,
                now=datetime(2026, 8, 4, 10, 0, 0),
            )
            second = create_imgs_snapshot(
                imgs,
                destination,
                now=datetime(2026, 8, 4, 10, 1, 0),
            )

            first_root = Path(first["snapshot"])
            second_root = Path(second["snapshot"])
            self.assertEqual(2, first["fileCount"])
            self.assertEqual(2, second["fileCount"])
            self.assertEqual(2, second["copiedFiles"] + second["reusedFiles"])
            self.assertTrue((first_root / "imgs" / "empty-folder").is_dir())
            self.assertTrue((second_root / "imgs" / "empty-folder").is_dir())

            artwork.write_text('{"version": 2}\n', encoding="utf-8")
            preview.unlink()
            editor = imgs / "editor" / "New.json"
            editor.parent.mkdir()
            editor.write_text('{"new": true}\n', encoding="utf-8")
            third = create_imgs_snapshot(
                imgs,
                destination,
                now=datetime(2026, 8, 4, 10, 2, 0),
            )
            third_root = Path(third["snapshot"])

            self.assertEqual('{"version": 1}\n', (first_root / "imgs" / "generated" / "Artwork.json").read_text(encoding="utf-8"))
            self.assertEqual(b"preview-v1", (first_root / "imgs" / "previews" / "Artwork.png").read_bytes())
            self.assertEqual(b"preview-v1", (second_root / "imgs" / "previews" / "Artwork.png").read_bytes())
            self.assertEqual('{"version": 2}\n', (third_root / "imgs" / "generated" / "Artwork.json").read_text(encoding="utf-8"))
            self.assertTrue((third_root / "imgs" / "editor" / "New.json").is_file())
            self.assertFalse((third_root / "imgs" / "previews" / "Artwork.png").exists())
            snapshots = destination / BACKUP_FOLDER_NAME / "snapshots"
            self.assertEqual(3, len([path for path in snapshots.iterdir() if not path.name.startswith(".")]))
            for snapshot in (first_root, second_root, third_root):
                manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual("kfps-imgs-snapshot-v1", manifest["format"])

    def test_destination_is_remembered_and_missing_destination_prompts_again(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app_root = root / "app"
            imgs = app_root / "imgs"
            imgs.mkdir(parents=True)
            runtime = app_root / "runtime"
            destination = root / "destination"
            destination.mkdir()
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", runtime, app_root / "python" / "python.exe")
            settings = SettingsService(runtime / "settings.json")
            service = BackupService(paths, settings, DummyLog())
            try:
                settings.backupFolder = str(root / "missing")
                with patch(
                    "kfps_ui.backup_service.QFileDialog.getExistingDirectory",
                    return_value=str(destination),
                ) as chooser:
                    self.assertEqual(destination.resolve(), service._choose_destination())
                    chooser.assert_called_once()
                self.assertEqual(str(destination.resolve()), settings.backupFolder)

                with patch(
                    "kfps_ui.backup_service.QFileDialog.getExistingDirectory",
                    side_effect=AssertionError("remembered destinations must not prompt"),
                ):
                    self.assertEqual(destination.resolve(), service._choose_destination())
            finally:
                service._executor.shutdown(wait=True, cancel_futures=True)

    def test_destination_inside_imgs_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            imgs = root / "app" / "imgs"
            inside = imgs / "backups"
            imgs.mkdir(parents=True)
            inside.mkdir()
            with self.assertRaisesRegex(ValueError, "outside the KFPS imgs folder"):
                create_imgs_snapshot(imgs, inside)


if __name__ == "__main__":
    unittest.main()
