import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QSize
from PySide6.QtGui import QImage
from kfps_ui.startup_sequence_service import StartupFrameProvider, StartupSequenceService


class StartupSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.paths = SimpleNamespace(app_root=root, runtime_root=root / "runtime", asset_root=root / "assets")
        self.jsons = SimpleNamespace(indexing=False, warmIndex=Mock())
        self.runtime = SimpleNamespace(checking=False)
        self.logs = Mock()

    def create(self, **kwargs):
        service = StartupSequenceService(self.paths, self.jsons, self.runtime, self.logs, **kwargs)
        self.addCleanup(service.close)
        return service

    def media(self, packaged=False):
        path = (self.paths.asset_root / "themes/ps2/startup.mp4" if packaged else
                self.paths.runtime_root / "theme-assets/ps2/startup.mp4")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test fixture; decoder validation belongs to integration test")
        return path

    def test_missing_media_does_not_claim_an_intro(self):
        service = self.create(enabled=True)
        self.assertFalse(service.enabled)
        self.assertFalse(service.claim())
        self.assertEqual(service.source, "")

    def test_once_per_process_and_disabled_theme(self):
        self.media()
        service = self.create(enabled=True)
        self.assertTrue(service.claim())
        self.assertFalse(service.claim())
        self.assertFalse(self.create(enabled=False).claim())

    def test_local_media_overrides_packaged_media(self):
        self.media(packaged=True)
        self.media()
        self.assertIn("runtime/theme-assets/ps2/startup.mp4", self.create(enabled=True).source)

    def test_packaged_media_can_be_discovered(self):
        self.media(packaged=True)
        self.assertTrue(self.create(enabled=True).enabled)

    def test_empty_media_is_ignored(self):
        self.media().write_bytes(b"")
        self.assertFalse(self.create(enabled=True).enabled)

    def test_begin_loading_uses_existing_scan_once(self):
        service = self.create()
        service.beginLoading(); service.beginLoading()
        self.jsons.warmIndex.assert_called_once()
        self.assertTrue(service.ready)
        self.assertIsNone(service._executor)

    def test_indexing_and_runtime_completion_gate(self):
        self.jsons.indexing = True
        self.runtime.checking = True
        service = self.create()
        service.beginLoading()
        self.assertFalse(service.ready)
        self.jsons.indexing = False
        service._check_ready()
        self.assertFalse(service.ready)
        self.runtime.checking = False
        service._check_ready()
        self.assertTrue(service.ready)
        self.assertFalse(service._timer.isActive())

    def test_disconnected_source_cannot_trap_startup(self):
        self.jsons.indexing = True
        service = self.create()
        service.beginLoading()
        service._started_at = time.monotonic() - 31
        service._check_ready()
        self.assertTrue(service.ready)
        self.assertTrue(self.jsons.indexing)

    def test_registry_refresh_remains_owned_and_optional(self):
        with patch("kfps_ui.startup_sequence_service.refresh_runtime_registry", return_value={"result":"cached"}) as refresh:
            service = self.create(refresh_registry=True)
            service.beginLoading()
            service.close()
            refresh.assert_called_once_with(self.paths.app_root)

    def test_close_is_idempotent_and_late_results_are_ignored(self):
        service = self.create()
        service.close(); service.close(); service.beginLoading()
        self.assertFalse(service.claim())
        self.jsons.warmIndex.assert_not_called()
        service._record_registry_result({"result":"late"})
        self.logs.append.assert_not_called()

    def test_image_provider_keeps_only_latest_frame(self):
        provider = StartupFrameProvider()
        first = QImage(16, 9, QImage.Format_RGB32); first.fill(0xff112233)
        provider.set_frame(first)
        size = QSize()
        result = provider.requestImage("frame-1", size, QSize())
        self.assertEqual(size, QSize(16,9))
        second = QImage(32, 18, QImage.Format_RGB32); second.fill(0xff778899)
        provider.set_frame(second)
        self.assertEqual(provider.requestImage("frame-2", QSize(), QSize()).size(), QSize(32,18))
        self.assertEqual(result.size(), QSize(16,9))
        self.assertEqual(result.pixelColor(0,0).name(), "#112233")

    def test_mute_updates_current_and_future_playback(self):
        service = self.create()
        service.setMuted(True)
        self.assertTrue(service.muted)
        service._audio = Mock()
        service.setMuted(False)
        self.assertFalse(service.muted)
        service._audio.setMuted.assert_called_once_with(False)
        service.setMuted(True)
        service._audio.setMuted.assert_called_with(True)

    def test_test_environment_cannot_be_unmuted(self):
        service = self.create(muted=True)
        service._audio = Mock()
        service.setMuted(False)
        self.assertTrue(service.muted)
        service._audio.setMuted.assert_not_called()

    def test_stop_leaves_a_valid_black_frame_for_queued_image_reads(self):
        service = self.create()
        service.stop()
        image = service.frame_provider.requestImage('stopped', QSize(), QSize())
        self.assertEqual(image.size(), QSize(1, 1))
        self.assertEqual(image.pixelColor(0, 0).name(), '#000000')


if __name__ == "__main__":
    unittest.main()
