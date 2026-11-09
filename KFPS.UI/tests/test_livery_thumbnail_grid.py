from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]

from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.log_service import LogService
from kfps_ui.experimental.full_livery.thumbnails import MAX_THUMBNAIL_BYTES, source_grid_row


class LiveryThumbnailGridTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Livery with spaces #1" / "C_livery"
        self.source.parent.mkdir()
        self.source.write_bytes(b"synthetic source")
        self.thumb = self.source.parent / "bigThumb.webp"
        self.row = {
            "path": str(self.source.resolve()), "title": "Blue [Track]",
            "carId": 1296, "modelCode": "TEST_CAR", "placementCount": 52,
            "exportable": True, "privacyDetail": "", "modified": "2026-09-09",
        }

    def service(self, rows=None, *, load_scan=True):
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            service = FullLiveryService(paths, LogService(), demo=True)
        self.addCleanup(service.close)
        refresh = patch.object(service, "refreshPackages")
        refresh.start()
        self.addCleanup(refresh.stop)
        if load_scan:
            service._apply_result({"kind": "scan", "ok": True,
                                   "payload": {"rows": [self.row] if rows is None else rows}})
        return service

    def test_thumbnail_is_exact_sibling_and_url_is_escaped(self):
        self.thumb.write_bytes(b"image fixture")
        row = source_grid_row(self.row)
        self.assertTrue(row["thumbnailUrl"].startswith(self.thumb.resolve().as_uri() + "?v="))
        self.assertIn("%23", row["thumbnailUrl"])
        other = self.root / "Different livery" / "C_livery"
        other.parent.mkdir()
        other.write_bytes(b"same car")
        self.assertEqual("", source_grid_row({**self.row, "path": str(other)})["thumbnailUrl"])
        self.assertNotIn("thumbnailUrl", self.row)

    def test_availability_is_independent_of_thumbnail_and_export_rights(self):
        service = self.service([{**self.row, "exportable": False}])
        self.assertTrue(service.sourceModel.rows[0]["available"])
        self.assertEqual("", service.sourceModel.rows[0]["thumbnailUrl"])
        self.source.unlink()
        service._replace_source_rows([self.row])
        self.assertFalse(service.sourceModel.rows[0]["available"])

    def test_package_availability_updates_when_local_file_disappears(self):
        service = self.service()
        package = self.root / 'local.kfpslivery'
        package.write_bytes(b'fixture')
        row = {'path': str(package), 'carId': 1296, 'title': 'Local package'}
        service._replace_package_rows([row])
        self.assertTrue(service.packageModel.rows[0]['available'])
        package.unlink()
        service._replace_package_rows([row])
        self.assertFalse(service.packageModel.rows[0]['available'])

    def test_changed_thumbnail_refreshes_even_if_artwork_is_unchanged(self):
        self.thumb.write_bytes(b"first")
        first = source_grid_row(self.row)["thumbnailUrl"]
        self.thumb.write_bytes(b"second image")
        os.utime(self.thumb, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))
        self.assertNotEqual(first, source_grid_row(self.row)["thumbnailUrl"])
        self.thumb.unlink()
        self.assertEqual("", source_grid_row(self.row)["thumbnailUrl"])

    def test_missing_empty_oversized_or_orphaned_thumbnail_is_not_loaded(self):
        self.assertEqual("", source_grid_row(self.row)["thumbnailUrl"])
        self.thumb.touch()
        self.assertEqual("", source_grid_row(self.row)["thumbnailUrl"])
        with self.thumb.open("wb") as stream:
            stream.truncate(MAX_THUMBNAIL_BYTES + 1)
        self.assertEqual("", source_grid_row(self.row)["thumbnailUrl"])
        self.thumb.write_bytes(b"image")
        self.source.unlink()
        self.assertEqual("", source_grid_row(self.row)["thumbnailUrl"])

    def test_search_is_literal_case_insensitive_and_keeps_canonical_model(self):
        service = self.service()
        for query in ("blue", "[track]", "test_car", "1296"):
            service.setSourceSearch(query)
            self.assertEqual(1, service.sourceGridModel.rowCount(), query)
        service.setSourceSearch(".*")
        self.assertEqual(0, service.sourceGridModel.rowCount())
        self.assertEqual(1, service.sourceModel.rowCount())
        service.setSourceSearch("")
        self.assertEqual(1, service.sourceGridModel.rowCount())

    def test_browsing_without_game_assets_selects_without_starting_a_worker(self):
        service = self.service()
        with patch.object(service._tasks, "start") as start, \
                patch.object(service, "_prepare_local_mesh") as mesh:
            service.browseSource(str(self.source.resolve()))
        start.assert_not_called()
        mesh.assert_not_called()
        self.assertEqual(str(self.source.resolve()), service.selectedSource)
        self.assertEqual("Blue [Track]", service.selectedTitle)
        self.assertEqual("52 placements", service.selectedCounts)
        self.assertIn("1296", service.selectedVehicle)
        self.assertEqual("", service.viewerUrl)
        self.assertTrue(service.selectedSourceExportable)
        self.assertFalse(service.selectedPackageInstallable)

    def test_preview_is_explicit_and_requires_game_assets(self):
        service = self.service()
        service.browseSource(str(self.source.resolve()))
        with patch.object(service._tasks, "start", return_value=True) as start:
            service.previewSelectedSource()
            start.assert_not_called()
            service._game_folder = "C:/Fixture-FH6"
            service.previewSelectedSource()
        self.assertEqual("preview-source", start.call_args.args[0])
        self.assertEqual(str(self.source.resolve()), start.call_args.args[1]["source"])

    def test_return_to_grid_invalidates_pending_preview_without_deselecting(self):
        service = self.service()
        service.browseSource(str(self.source.resolve()))
        old_serial = service._source_preview_serial
        service._viewer_url = "http://127.0.0.1/old-preview"
        service._active_source_preview = str(self.source.resolve())
        service.showSourceGrid()
        service._apply_result({"kind": "preview", "ok": True,
                               "source_path": str(self.source.resolve()),
                               "request_serial": old_serial,
                               "payload": {"path": "must-not-open"}})
        self.assertEqual("", service.viewerUrl)
        self.assertEqual("", service._active_source_preview)
        self.assertEqual(str(self.source.resolve()), service.selectedSource)

    def test_missing_or_unindexed_source_never_starts_work(self):
        service = self.service()
        with patch.object(service._tasks, "start") as start:
            service.browseSource(str(self.root / "not-indexed" / "C_livery"))
            self.assertEqual("", service.selectedSource)
            self.source.unlink()
            service.browseSource(str(self.source.resolve()))
        start.assert_not_called()
        self.assertEqual("", service.selectedSource)
        self.assertEqual("Livery unavailable", service.status)

    def test_rescan_updates_thumbnail_without_resetting_search(self):
        service = self.service()
        service.setSourceSearch("blue")
        service.browseSource(str(self.source.resolve()))
        self.thumb.write_bytes(b"new image")
        service._apply_result({"kind": "scan", "ok": True,
                               "payload": {"rows": [self.row]}})
        self.assertTrue(service.sourceModel.row(0)["thumbnailUrl"])
        self.assertEqual(1, service.sourceGridModel.rowCount())
        service._apply_result({"kind": "scan", "ok": True, "payload": {"rows": []}})
        self.assertEqual("", service.selectedSource)

    def test_restart_hydrates_original_thumbnails_from_the_existing_catalog(self):
        service = self.service()
        stat = self.source.stat()
        service._catalog.upsert_source(
            self.source, root=self.root, size=stat.st_size, mtime_ns=stat.st_mtime_ns,
            content_hash="unchanged-livery", parser_revision=1, seen_token="fixture",
            row={**self.row, "_visible": True},
        )
        service.setSourceSearch("not a match")
        service.close()
        self.thumb.write_bytes(b"new thumbnail after shutdown")
        restarted = self.service(load_scan=False)
        self.assertEqual(1, restarted.sourceGridModel.rowCount())
        self.assertTrue(restarted.sourceModel.row(0)["thumbnailUrl"])
        restarted.browseSource(str(self.source.resolve()))
        self.assertEqual(self.row["title"], restarted.selectedTitle)
        self.assertEqual("52 placements", restarted.selectedCounts)

    def test_preview_only_record_remains_browsable_but_not_exportable(self):
        service = self.service([{**self.row, "exportable": False, "privacyDetail": "Preview only"}])
        with patch.object(service._tasks, "start") as start:
            service.browseSource(str(self.source.resolve()))
        start.assert_not_called()
        self.assertEqual(str(self.source.resolve()), service.selectedSource)
        self.assertFalse(service.selectedSourceExportable)
        self.assertEqual("Preview only", service.selectedSourcePrivacyMessage)


if __name__ == "__main__":
    unittest.main()
