from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication

from kfps_ui.app_paths import AppPaths
from kfps_ui.json_service import JsonService
from kfps_ui.preview_service import PreviewService
from kfps_ui.qt_utils import file_url

APP = QCoreApplication.instance() or QCoreApplication([])


class DummyPreview:
    def preview_for_json(self, path, source=""):
        return ""


class DummyDesktop:
    def __init__(self, path):
        self.path = str(path)


class DummyLog:
    def append(self, message, level="info"):
        pass


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    APP.processEvents()
    return bool(predicate())


def shutdown(service):
    if hasattr(service, "_thumbnail_poll_timer"):
        service._thumbnail_poll_timer.stop()
    process = getattr(service, "_thumbnail_process", None)
    if process and process.poll() is None:
        process.kill()
        process.communicate(timeout=2)
    wait_for(lambda: not service.indexing)
    service._preview_executor.shutdown(wait=True, cancel_futures=True)
    service._index_executor.shutdown(wait=True, cancel_futures=True)


class OutputExplorerPerformanceTests(unittest.TestCase):
    def test_refresh_does_not_probe_every_indexed_json(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td)
            exported = app_root / "imgs" / "exported"
            exported.mkdir(parents=True)
            payload = json.dumps({"metadata": {"layers": 1}, "shapes": []})
            for index in range(500):
                (exported / f"Artwork {index:04d}.json").write_text(payload, encoding="utf-8")
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", app_root / "python" / "python.exe")
            service = JsonService(paths, DummyPreview(), DummyDesktop(exported), DummyLog())
            try:
                self.assertTrue(wait_for(lambda: len(service._source_index_cache.get(2, {}).get("rows", [])) == 500))
                service.setSource(2)
                original_is_file = Path.is_file
                probes = 0

                def counted_is_file(path):
                    nonlocal probes
                    probes += 1
                    return original_is_file(path)

                with patch("pathlib.Path.is_file", counted_is_file):
                    service._refresh_explorer()

                self.assertEqual(500, service.outputCount)
                self.assertLess(probes, 20, "explorer refresh returned to probing every JSON on disk")
            finally:
                shutdown(service)

    def test_selecting_one_hundred_jsons_does_not_revalidate_them_from_disk(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td)
            exported = app_root / "imgs" / "exported"
            exported.mkdir(parents=True)
            payload = json.dumps({"metadata": {"layers": 1}, "shapes": []})
            for index in range(500):
                (exported / f"Artwork {index:04d}.json").write_text(payload, encoding="utf-8")
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", app_root / "python" / "python.exe")
            service = JsonService(paths, DummyPreview(), DummyDesktop(exported), DummyLog())
            try:
                self.assertTrue(wait_for(lambda: len(service._source_index_cache.get(2, {}).get("rows", [])) == 500))
                service.setSource(2)
                original_is_file = Path.is_file
                probes = 0

                def counted_is_file(path):
                    nonlocal probes
                    probes += 1
                    return original_is_file(path)

                with patch("pathlib.Path.is_file", counted_is_file):
                    started = time.perf_counter()
                    service.selectExplorerEntry(0, False, False)
                    for index in range(1, 10):
                        service.selectExplorerEntry(index, True, False)
                    ten_selection_seconds = time.perf_counter() - started
                    self.assertEqual(10, service.explorerSelectionCount)
                    service.clearExplorerSelection()
                    service.selectExplorerEntry(0, False, False)
                    service.selectExplorerEntry(99, False, True)
                    for _ in range(20):
                        self.assertEqual(100, service.fileOperationSelectionCount)

                self.assertEqual(100, service.explorerSelectionCount)
                self.assertEqual(100, sum(1 for row in service.explorerModel.rows if row["selected"]))
                self.assertLess(ten_selection_seconds, 0.5, "selecting ten JSONs is too slow")
                self.assertLess(probes, 20, "selection returned to validating every selected JSON from disk")
            finally:
                shutdown(service)

    def test_cutting_and_pasting_one_hundred_jsons_stays_responsive(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td)
            exported = app_root / "imgs" / "exported"
            exported.mkdir(parents=True)
            payload = json.dumps({"metadata": {"layers": 3000}, "shapes": [{"type": 1048677}] * 3000})
            for index in range(100):
                (exported / f"Large Artwork {index:04d}.json").write_text(payload, encoding="utf-8")
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", app_root / "python" / "python.exe")
            preview = PreviewService(paths)
            old_caches = []
            for json_path in exported.glob("*.json"):
                cache = preview._cache_target(json_path, "general")
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(b"cached-preview" * 128)
                old_caches.append(cache)
            service = JsonService(paths, preview, DummyDesktop(exported), DummyLog())
            try:
                self.assertTrue(wait_for(lambda: len(service._source_index_cache.get(2, {}).get("rows", [])) == 100))
                service.setSource(2)
                self.assertTrue(service.createFolderIn(str(exported), "Destination"))
                destination = exported / "Destination"
                json_indices = [
                    index for index, row in enumerate(service.explorerModel.rows)
                    if not row["isFolder"]
                ]
                self.assertEqual(100, len(json_indices))
                service.selectExplorerEntry(json_indices[0], False, False)
                for index in json_indices[1:]:
                    service.selectExplorerEntry(index, True, False)

                started = time.perf_counter()
                service.cutSelection()
                cut_seconds = time.perf_counter() - started
                self.assertEqual(100, service.clipboardCount)

                started = time.perf_counter()
                service.pasteIntoFolder(str(destination))
                paste_seconds = time.perf_counter() - started

                self.assertEqual(0, service.clipboardCount)
                self.assertEqual(0, len(list(exported.glob("*.json"))))
                self.assertEqual(100, len(list(destination.glob("*.json"))))
                self.assertTrue(all(not cache.exists() for cache in old_caches))
                self.assertTrue(all(
                    preview._cache_target(json_path, "general").is_file()
                    for json_path in destination.glob("*.json")
                ))
                self.assertLess(cut_seconds, 1.0, f"cut staging took {cut_seconds:.3f}s")
                self.assertLess(paste_seconds, 2.0, f"paste completion took {paste_seconds:.3f}s")
            finally:
                shutdown(service)

    def test_moved_json_keeps_cached_thumbnail_in_destination_row(self):
        with tempfile.TemporaryDirectory() as td:
            app_root = Path(td)
            exported = app_root / "imgs" / "exported"
            destination = exported / "Destination"
            destination.mkdir(parents=True)
            (destination / ".kfps-output-folder").write_text(
                json.dumps({"format": "kfps-output-folder-v1", "displayName": "Destination"}),
                encoding="utf-8",
            )
            source = exported / "Artwork.json"
            source.write_text(json.dumps({"metadata": {"layers": 1}, "shapes": []}), encoding="utf-8")
            paths = AppPaths(app_root, UI, UI / "qml", UI / "assets", app_root / "runtime", app_root / "python" / "python.exe")
            preview = PreviewService(paths)
            service = JsonService(paths, preview, DummyDesktop(source), DummyLog())
            try:
                self.assertTrue(wait_for(lambda: len(service._source_index_cache.get(2, {}).get("rows", [])) == 1))
                service.setSource(2)
                old_cache = preview._cache_target(source, "general")
                old_cache.parent.mkdir(parents=True, exist_ok=True)
                old_cache.write_bytes(b"cached-preview")
                service._update_preview_url(str(source), file_url(old_cache))
                source_index = next(
                    index for index, row in enumerate(service.explorerModel.rows)
                    if row["path"] == str(source)
                )
                service.selectExplorerEntry(source_index, False, False)
                service.cutSelection()
                service.pasteIntoFolder(str(destination))

                target = destination / source.name
                target_key = service._preview_key(target)
                new_cache = preview._cache_target(target, "general")
                row = service._source_index_cache[2]["rowsByKey"][target_key]
                self.assertEqual(file_url(new_cache), row["previewUrl"])
                self.assertEqual(b"cached-preview", new_cache.read_bytes())
                self.assertFalse(old_cache.exists())
                with patch("json_preview_renderer.render_json_preview", side_effect=AssertionError("thumbnail was rerendered")):
                    self.assertEqual(file_url(new_cache), preview.preview_for_json(target, "exported"))
            finally:
                shutdown(service)


if __name__ == "__main__":
    unittest.main()
