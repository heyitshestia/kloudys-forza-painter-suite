from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from kfps_ui.community_preview_service import CommunityPreviewService
from kfps_ui.community_preview_photos import read_photos
from kfps_ui.community_preview_store import PreviewError
from test_full_livery_package import build_package

APP = QApplication.instance() or QApplication([])


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.package = self.root / "test.kfpslivery"
        build_package(self.package)
        self.photos = []
        for i, color in enumerate(("red", "green", "blue")):
            image = QImage(320, 200, QImage.Format_RGB32)
            image.fill(color)
            image.setText("private-location", "must not survive")
            path = self.root / f"photo-{i}.png"
            image.save(str(path))
            self.photos.append(str(path))
        cover = QImage(670, 376, QImage.Format_RGB32)
        cover.fill('yellow')
        cover_path = self.root / 'game.webp'
        cover.save(str(cover_path), 'WEBP')
        build_package(self.package, thumbnail=cover_path.read_bytes())

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def wait(self):
        end = time.monotonic() + 30
        while self.service.busy and time.monotonic() < end:
            APP.processEvents()
            time.sleep(.01)
        self.assertFalse(self.service.busy)

    def prepare(self):
        self.service.inspectPath(str(self.package))
        self.wait()
        self.assertFalse(self.service.hasError, self.service.status)

    def publish(self):
        self.service.publish(dict(title="Photo livery", rights=True, compatibility=True))

    def test_photos_metadata_size_and_invalid_inputs(self):
        normalized = read_photos(self.photos)
        self.assertEqual(len(normalized), 3)
        image = QImage.fromData(normalized[0])
        self.assertEqual(image.size(), QImage(self.photos[0]).size())
        self.assertEqual(image.textKeys(), [])
        with self.assertRaises(PreviewError): read_photos(self.photos + self.photos[:1])
        with self.assertRaises(PreviewError): read_photos([])
        bad = self.root / "bad.png"
        bad.write_bytes(b"not a photo")
        with self.assertRaises(PreviewError): read_photos([str(bad)])
        bad.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20"/></svg>')
        with self.assertRaises(PreviewError): read_photos([str(bad)])
        big = QImage(2500, 1200, QImage.Format_RGB32)
        big.fill("blue")
        big.save(str(bad))
        image = QImage.fromData(read_photos([str(bad)])[0])
        self.assertEqual(image.width(), 1920)
        self.assertLess(abs(image.height() - 1920 * 1200 / 2500), 1)
        with bad.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
        with self.assertRaises(PreviewError): read_photos([str(bad)])

    def test_upload_without_photos_keeps_game_cover(self):
        self.prepare()
        cover = self.service.upload['previewUrl']
        self.publish()
        self.assertFalse(self.service.hasError, self.service.status)
        self.assertEqual(self.service.selected['previewUrl'], cover)
        self.assertEqual(self.service.selected['photoUrls'], [cover])

    def test_optional_photos_and_failed_replace_preserves_them(self):
        self.prepare()
        cover = self.service.upload['previewUrl']
        self.service.inspectPhotos(self.photos)
        self.wait()
        old = self.service.upload["photoUrls"][:]
        self.service.inspectPhotos(self.photos * 2)
        self.wait()
        self.assertTrue(self.service.hasError)
        self.assertEqual(self.service.upload["photoUrls"], old)
        self.service.removePhoto(1)
        self.assertEqual(len(self.service.upload["photoUrls"]), 2)
        self.publish()
        self.assertFalse(self.service.hasError, self.service.status)
        ident = self.service.selected["id"]
        self.assertEqual(len(self.service.selected["photoUrls"]), 3)
        self.assertEqual(self.service.selected['photoUrls'][0], cover)
        self.assertEqual(self.service.selected['previewUrl'], cover)
        self.assertEqual(self.service.store.render_payload(ident, "Member"), self.package.read_bytes())
        self.service.close()
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.service.filter("scope", "Browse")
        self.assertEqual(len(self.service.selected["photoUrls"]), 3)
        self.assertEqual(self.service.selected['photoUrls'][0], cover)
        self.assertEqual(self.service.selected["downloads"], 0)

    def test_livery_tab_only_lists_liveries_and_browse_restores_vinyls(self):
        self.service.store.add(dict(title='Car', kind='livery'), b'car', b'', 'Creator')
        self.service.store.add(dict(title='Vinyl', kind='vinyl'), b'vinyl', b'', 'Creator')
        self.service.filter('scope', 'Livery')
        self.assertEqual([row['title'] for row in self.service.rows], ['Car'])
        self.service.filter('scope', 'Browse')
        self.assertEqual(len(self.service.rows), 2)

    def test_timed_filter_browse_boundaries_and_photo_purge(self):
        store = self.service.store
        now = self.service.now()
        photos = read_photos(self.photos)
        meta = dict(title="Timed", kind="livery")
        ident = store.add(meta, self.package.read_bytes(), photos[0], "Creator", starts=now-1, ends=now+3, photos=photos)
        store.add(dict(title="Normal", kind="vinyl"), b"vinyl", b"", "Creator")
        store.add(dict(meta, title="Future"), b"future", photos[0], "Creator", starts=now+4, ends=now+10, photos=photos)
        self.service.filter("scope", "Browse")
        self.assertEqual(len(self.service.rows), 2)
        self.service.filter("scope", "Timed Releases")
        self.assertEqual([r["id"] for r in self.service.rows], [ident])
        self.service.advanceClock(3)
        self.assertEqual(self.service.rows, [])
        self.assertEqual(store.photos(ident, "Creator", now+3), [])
        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM photos WHERE artwork=?", (ident,)).fetchone()[0], 0)
        self.service.advanceClock(2)
        self.assertEqual([r["title"] for r in self.service.rows], ["Future"])

    def test_render_access_hash_and_session_cleanup(self):
        store = self.service.store
        ident = store.add(dict(title="Private", kind="livery", supporter=True), self.package.read_bytes(), b"cover", "Creator")
        for mode in ("Visitor", "Member"):
            with self.assertRaises(PreviewError): store.render_payload(ident, mode)
        self.service.filter("scope", "Browse")
        session = MagicMock()
        # The UI property needs a QObject; the mock session is only lifecycle evidence.
        session.service = None
        with patch("kfps_ui.community_preview_livery.PreviewLiverySession", return_value=session):
            self.service.openRender()
            session.start.assert_called_once()
            self.service.setAccount("Member")
            session.close.assert_called_once()
            self.assertIsNone(self.service.liveryViewer)
            self.service.openRender()
            self.assertTrue(self.service.hasError)
        store.db.execute("UPDATE artwork SET payload=? WHERE id=?", (b"tampered", ident))
        with self.assertRaises(PreviewError): store.render_payload(ident, "Creator")

    def test_preview_session_isolated_and_does_not_scan_saves(self):
        from kfps_ui.community_preview_livery import PreviewLiverySession
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            session = PreviewLiverySession(ROOT, self.root / "render", self.package.read_bytes())
        folder = Path(session.temporary.name)
        service = session.service
        try:
            self.assertTrue(service._experiment_paths.package_root.is_relative_to(folder))
            self.assertTrue(service._settings_file.is_relative_to(folder))
            self.assertEqual(service._save_root, "")
            with patch.object(service, "selectPackage") as select, patch.object(service, "scanSaves") as scan:
                session.start()
                select.assert_called_once_with(session.package)
                scan.assert_not_called()
            service._current_manifest = {"vehicle": {}}
            service._selected_package = session.package
            with patch.object(service, "scanSaves") as scan, patch.object(service, "_prepare_local_mesh") as prepare:
                service._apply_result({"ok": True, "kind": "link-game", "payload": {"game_folder": "test-assets"}})
                scan.assert_not_called()
                prepare.assert_called_once()
        finally:
            session.close()
        self.assertFalse(folder.exists())

    def test_open_render_closes_at_expiry(self):
        now = self.service.now()
        ident = self.service.store.add(dict(title="Expiring", kind="livery"), self.package.read_bytes(), b"cover", "Creator", starts=now-1, ends=now+2)
        self.service.filter("scope", "Browse")
        self.service.select(ident)
        session = MagicMock()
        session.service = None
        with patch("kfps_ui.community_preview_livery.PreviewLiverySession", return_value=session):
            self.service.openRender()
            self.service.advanceClock(3)
        session.close.assert_called_once()
        self.assertEqual(self.service.rows, [])


if __name__ == "__main__":
    unittest.main()
