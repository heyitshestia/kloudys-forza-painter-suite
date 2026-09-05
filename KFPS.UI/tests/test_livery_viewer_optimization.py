from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PIL import Image
from PySide6.QtCore import QCoreApplication, QProcess
from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.experimental.full_livery.resource_policy import LiveryMemoryBudget, GIB, MIB
from kfps_ui.experimental.full_livery.catalog import FullLiveryCatalog
from tools.livery.derived_cache import validated_derived_file
from tools.livery.render_contract import _vector_paint_tile, _warped_uv_layer, SECTION_TO_SLOT


class ViewerOptimizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            self.service = FullLiveryService(paths, LogService(), demo=True)
        self.service._active = True

    def tearDown(self):
        self.service.close()
        self.temporary.cleanup()

    def open_viewer(self):
        with patch.object(self.service, "_viewer_process_memory", return_value=(0, 0)):
            self.service._inspector_ready("http://127.0.0.1:9876/session/")

    def test_ready_requires_the_first_complete_frame(self):
        self.open_viewer()
        self.assertFalse(self.service.viewerReady)
        self.assertTrue(self.service.running)
        self.service.viewerEvent(self.service.viewerUrl, '{"event":"ready"}')
        self.assertTrue(self.service.viewerReady)
        self.assertFalse(self.service.running)

    def test_stale_or_malformed_events_cannot_reactivate_a_viewer(self):
        self.open_viewer()
        for message in ("null", "[]", "bad", '{"event":"unknown"}', '"x"', "x" * 65537):
            self.service.viewerEvent(self.service.viewerUrl, message)
        self.service.viewerEvent("http://127.0.0.1/old/", '{"event":"ready"}')
        self.assertFalse(self.service.viewerReady)
        self.service.deactivate()
        self.service.viewerEvent("http://127.0.0.1:9876/session/", '{"event":"ready"}')
        self.assertFalse(self.service.viewerReady)
        self.assertEqual("", self.service.viewerUrl)

    def test_context_loss_stops_and_records_the_active_viewer(self):
        self.open_viewer()
        with patch.object(self.service._inspector, "record_viewer_event") as record:
            self.service.viewerEvent(self.service.viewerUrl, '{"event":"context-lost","message":"lost device"}')
        record.assert_called_once()
        self.assertEqual("", self.service.viewerUrl)
        self.assertEqual("lost device", self.service.summary)
        self.assertFalse(self.service._viewer_memory_timer.isActive())

    def test_missing_first_frame_has_a_host_deadline(self):
        self.open_viewer()
        self.service._viewer_started_at = time.monotonic() - 91
        with patch.object(self.service, "_viewer_process_memory", return_value=(0, 0)):
            self.service._monitor_viewer_memory()
        self.assertEqual("", self.service.viewerUrl)
        self.assertIn("first-frame timeout", self.service.summary)
        report = json.loads((self.service._experiment_paths.diagnostics / "viewer-memory-guard.json").read_text())
        self.assertIn("first-frame timeout", report["reason"])

    def test_memory_limits_follow_available_memory_not_a_fixed_six_gib(self):
        small = LiveryMemoryBudget.for_memory(8 * GIB, 2 * GIB)
        large = LiveryMemoryBudget.for_memory(64 * GIB, 48 * GIB)
        self.assertLess(small.worker_bytes, GIB)
        self.assertLess(small.viewer_bytes, GIB)
        self.assertEqual(6 * GIB, large.worker_bytes)
        self.assertEqual(2 * GIB, large.viewer_bytes)
        self.assertEqual("", small.viewer_failure(100 * MIB, 0, GIB))
        self.assertTrue(small.viewer_failure(GIB, 0, GIB))
        self.assertTrue(small.viewer_failure(300 * MIB, 0, 64 * MIB))
        self.assertEqual(small.worker_bytes, small.worker_limit("prepare-mesh"))
        self.assertEqual(small.worker_bytes, small.worker_limit("preview-source"))
        self.assertEqual(6 * GIB, small.worker_limit("export-package"))
        self.assertEqual(6 * GIB, small.worker_limit("install-package"))

    def test_repeated_clicks_do_not_extend_cancellation(self):
        tasks = self.service._tasks
        tasks._request = {"operation": "prepare-mesh"}
        tasks._process = Mock()
        tasks._process.state.return_value = QProcess.ProcessState.Running
        with patch("kfps_ui.experimental.full_livery.supervisor.time.monotonic", return_value=10):
            tasks.cancel("first cancellation")
        with patch("kfps_ui.experimental.full_livery.supervisor.time.monotonic", return_value=12):
            tasks.cancel("another click")
        self.assertEqual(13, tasks._cancel_deadline)
        self.assertEqual("first cancellation", tasks._cancel_reason)
        tasks._process.state.return_value = QProcess.ProcessState.NotRunning

    def test_server_death_after_readiness_is_not_silent(self):
        inspector = self.service._inspector
        inspector._reported_ready = True
        errors = []
        inspector.failed.connect(errors.append)
        inspector._on_finished(0, QProcess.ExitStatus.NormalExit)
        self.assertEqual(1, len(errors))
        self.assertIn("unexpectedly", errors[0])

    def test_leaving_page_clears_pending_work_even_when_already_cancelling(self):
        self.service._tasks._pending = ("prepare-mesh", {}, "mesh", {})
        self.service._tasks._cancel_deadline = 100
        self.service.deactivate()
        self.assertIsNone(self.service._tasks._pending)

    def test_open_completion_cannot_restart_preparation_after_page_closed(self):
        self.service._selected_package = "car.kfpslivery"
        serial = self.service._selection_serial
        self.service.deactivate()
        with patch.object(self.service, "_accept_open_package") as accept:
            self.service._apply_result({"kind": "open-package", "ok": True,
                                        "package_path": "car.kfpslivery", "selection_serial": serial})
        accept.assert_not_called()

    def test_old_package_completion_does_not_replace_new_selection(self):
        self.service._selected_package = "new.kfpslivery"
        self.service._running = True
        with patch.object(self.service, "_accept_open_package") as accept:
            self.service._apply_result({
                "kind": "open-package", "ok": True, "package_path": "old.kfpslivery",
                "payload": {"path": "old.kfpslivery", "manifest": {}},
            })
        accept.assert_not_called()
        self.assertTrue(self.service.running)
        self.assertEqual("new.kfpslivery", self.service.selectedPackage)

    def test_private_preview_source_is_available_before_mesh_preparation(self):
        self.service._selected_source = "owned/C_livery"
        self.service._source_preview_serial = 4
        with patch.object(self.service, "_accept_open_package") as accept:
            accept.side_effect = lambda *args, **kwargs: self.assertEqual(
                "owned/C_livery", self.service._active_source_preview)
            self.service._apply_result({
                "kind": "preview", "ok": True, "request_serial": 4,
                "source_path": "owned/C_livery",
                "payload": {"path": "private.kfpspreview", "manifest": {}},
            })
        accept.assert_called_once()

    def test_repeated_selection_is_ignored_but_failed_selection_can_retry(self):
        package = self.root / "car.kfpslivery"
        package.touch()
        self.service._selected_package = str(package.resolve())
        self.service._viewer_url = "http://127.0.0.1/current/"
        with patch.object(self.service._tasks, "start") as start:
            self.service.selectPackage(str(package))
            start.assert_not_called()
            self.service._viewer_url = ""
            self.service.selectPackage(str(package))
            start.assert_called_once()

    def test_browser_url_is_not_bound_to_broad_service_notifications(self):
        qml = (UI / "qml/pages/LiveryPage.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property string viewerSessionUrl: fullLiveryService.viewerUrl", qml)
        self.assertIn("url: root.viewerSessionUrl", qml)

    def test_derived_mesh_receipt_revalidates_same_size_corruption(self):
        path = self.root / "car.glb"
        path.write_bytes(b"valid")
        validator = Mock(return_value={"mesh_count": 3})
        self.assertEqual({"mesh_count": 3}, validated_derived_file(path, validator, 11))
        validated_derived_file(path, validator, 11)
        self.assertEqual(1, validator.call_count)
        stat = path.stat()
        path.write_bytes(b"other")
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        validated_derived_file(path, validator, 11)
        self.assertEqual(2, validator.call_count)
        validated_derived_file(path, validator, 12)
        self.assertEqual(3, validator.call_count)

    def test_broken_receipt_is_rebuilt_not_trusted(self):
        path = self.root / "car.glb"
        path.write_bytes(b"valid")
        path.with_suffix(".glb.validated.json").write_text("broken")
        validator = Mock(return_value={"mesh_count": 3})
        validated_derived_file(path, validator, 11)
        validator.assert_called_once()

    def test_disk_quota_preserves_active_files_and_saved_packages(self):
        cache = self.root / "cache"
        mesh = cache / "meshes" / "old.glb"
        mesh.parent.mkdir(parents=True)
        mesh.write_bytes(b"x" * 100)
        atlas = cache / "atlases" / "active"
        atlas.mkdir(parents=True)
        (atlas / "paint.png").write_bytes(b"y" * 100)
        saved = self.root / "saved.kfpslivery"
        saved.write_bytes(b"keep")
        os.utime(mesh, (1, 1))
        catalog = FullLiveryCatalog(self.root / "catalog.sqlite")
        result = catalog.prune_derived_cache(cache, protected=[atlas], max_bytes=100)
        self.assertFalse(mesh.exists())
        self.assertTrue(atlas.exists())
        self.assertEqual(b"keep", saved.read_bytes())
        self.assertEqual(100, result["removed_bytes"])

    def test_disk_quota_skips_linked_directories_and_recent_work(self):
        cache = self.root / "cache"
        recent = cache / "atlases" / "building"
        recent.mkdir(parents=True)
        (recent / "paint.png").write_bytes(b"active")
        linked = cache / "meshes"
        linked.mkdir()
        (linked / "outside.glb").write_bytes(b"keep")
        catalog = FullLiveryCatalog(self.root / "catalog.sqlite")
        with patch("kfps_ui.experimental.full_livery.catalog.os.path.isjunction",
                   side_effect=lambda path: Path(path) == linked):
            result = catalog.prune_derived_cache(cache, protected=[], max_bytes=0)
        self.assertEqual(0, result["removed_bytes"])
        self.assertEqual(b"keep", (linked / "outside.glb").read_bytes())
        self.assertEqual(b"active", (recent / "paint.png").read_bytes())

    def test_disk_quota_does_not_fail_when_an_old_entry_is_locked(self):
        cache = self.root / "cache"
        old = cache / "atlases" / "old"
        old.mkdir(parents=True)
        (old / "paint.png").write_bytes(b"locked")
        os.utime(old, (1, 1))
        catalog = FullLiveryCatalog(self.root / "catalog.sqlite")
        with patch("kfps_ui.experimental.full_livery.catalog.shutil.rmtree", side_effect=PermissionError):
            result = catalog.prune_derived_cache(cache, protected=[], max_bytes=0)
        self.assertEqual(0, result["removed_bytes"])
        self.assertTrue(old.exists())

    def test_cropped_vector_tiles_keep_every_native_orientation(self):
        bounds = (970, 440, 1070, 550)
        projection = {"xorigin": "17", "yorigin": "-13"}

        def gradient(width, height, world_bounds):
            x0, y0, x1, y1 = world_bounds
            x = np.arange(width) * (x1-x0)/width + x0 + 1024
            y = y1 - np.arange(height) * (y1-y0)/height
            image = np.zeros((height, width, 4), dtype=np.uint8)
            image[..., 0] = np.clip(x / 8, 0, 255)[None, :]
            image[..., 1] = np.clip((512-y) / 4, 0, 255)[:, None]
            image[..., 2] = 20
            image[..., 3] = 255
            return Image.fromarray(image)

        native = gradient(2048, 1024, (-1024, -512, 1024, 512))
        for section, slot in SECTION_TO_SLOT.items():
            def render(_layers, **kwargs):
                buffer = io.BytesIO()
                gradient(*kwargs["canvas_size"], kwargs["world_bounds"]).save(buffer, format="PNG")
                return {section: buffer.getvalue()}, True, []
            with self.subTest(section=section), patch("tools.livery.render_contract._render_livery_sections", side_effect=render):
                tile = _vector_paint_tile([], section, slot, projection, bounds, 2, None, threading.Event())
                expected = _warped_uv_layer(native, slot, projection).crop(bounds)
                self.assertEqual((200, 220), tile.size)
                reduced = tile.resize(expected.size, Image.Resampling.BOX)
                error = np.abs(np.asarray(reduced).astype(float) - np.asarray(expected).astype(float)).mean()
                self.assertLess(error, 1.0)

    def test_unavailable_referenced_artwork_requires_original_section_image(self):
        with patch("tools.livery.render_contract._render_livery_sections", return_value=({}, False, [123])):
            tile = _vector_paint_tile([], "Front", "front", {}, (100, 100, 120, 120), 2, None, threading.Event())
        self.assertIsNone(tile)

    def test_reduced_quality_is_reported_after_readiness(self):
        self.open_viewer()
        self.service._viewer_quality = 2
        self.service.viewerEvent(self.service.viewerUrl,
                                 '{"event":"ready","diagnostics":{"quality":{"scale":1}}}')
        self.assertIn("Standard resolution", self.service.summary)


if __name__ == "__main__":
    unittest.main()
