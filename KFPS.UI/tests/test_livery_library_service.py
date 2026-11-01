from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]

from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.log_service import LogService


class LiveryLibraryServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            self.service = FullLiveryService(paths, LogService(), demo=True)
        self.addCleanup(self.service.close)
        refresh = patch.object(self.service, "refreshPackages")
        refresh.start()
        self.addCleanup(refresh.stop)
        self.rows = []
        for i in range(3):
            source = self.root / str(i) / "C_livery"
            source.parent.mkdir()
            source.write_bytes(b"fixture")
            self.rows.append(dict(path=str(source), title=["Beta", "Alpha", "Gamma"][i],
                                 carId=[100, 200, 100][i], modelCode=["CAR_A", "CAR_B", "CAR_A"][i],
                                 placementCount=(i + 1) * 10, modified=f"2026-10-{20+i}",
                                 exportable=i != 2, hasHeader=True,
                                 privacyDetail="Foreign group" if i == 2 else ""))
        self.scan(self.rows)

    def scan(self, rows):
        self.service._apply_result({"kind": "scan", "ok": True,
                                    "payload": {"rows": rows, "game_assets_ready": True}})

    def test_filters_counts_and_car_choices_use_cached_index(self):
        s = self.service
        with patch.object(Path, "stat", side_effect=AssertionError("filter disk IO")):
            self.assertEqual(3, s.sourceCount)
            self.assertEqual([0, 100, 200], [item["value"] for item in s.sourceCars])
            s.setSourceCar(100)
            self.assertEqual(2, s.visibleSourceCount)
            s.setSourceAvailability("preview")
            self.assertEqual(1, s.visibleSourceCount)
            s.setSourceSearch("GAMMA")
            self.assertEqual(1, s.visibleSourceCount)
            s.setSourceSort("placements")
            s.resetSourceFilters()
            self.assertEqual(3, s.visibleSourceCount)
        self.assertEqual("placements", s.sourceSort)
        self.assertEqual(3, s.sourceModel.rowCount())

    def test_filtering_and_rescan_preserve_selection_and_preferences(self):
        s = self.service
        s.browseSource(self.rows[0]["path"])
        s.setSourceCar(200)
        s.setSourceSearch("Alpha")
        s.setSourceAvailability("exportable")
        s.setSourceSort("title")
        self.scan(self.rows)
        self.assertEqual(self.rows[0]["path"], s.selectedSource)
        self.assertEqual((200, "Alpha", "exportable", "title"),
                         (s.sourceCarId, s.sourceSearch, s.sourceAvailability, s.sourceSort))
        self.assertEqual(1, s.visibleSourceCount)

    def test_selected_metadata_is_cached_and_updates_on_scan(self):
        s = self.service
        s.browseSource(self.rows[0]["path"])
        with patch.object(Path, "stat", side_effect=AssertionError("details disk IO")):
            self.assertEqual("2026-10-20", s.sourceDetails["modified"])
            self.assertTrue(s.sourceDetails["hasHeader"])
        self.scan([{**self.rows[0], "modified": "2026-10-29", "exportable": False}])
        self.assertEqual("2026-10-29", s.sourceDetails["modified"])
        self.assertFalse(s.selectedSourceExportable)
        self.scan([])
        self.assertEqual("", s.selectedSource)
        self.assertEqual("", s.sourceDetails["title"])

    def test_car_filter_remains_explicit_when_rescan_removes_its_car(self):
        s = self.service
        s.setSourceCar(200)
        self.scan([self.rows[0]])
        self.assertEqual(0, s.visibleSourceCount)
        choice = next(item for item in s.sourceCars if item["value"] == 200)
        self.assertIn("not in current scan", choice["label"])
        s.resetSourceFilters()
        self.assertEqual([0, 100], [item["value"] for item in s.sourceCars])

    def test_invalid_ui_options_do_not_damage_state(self):
        s = self.service
        s.setSourceCar(-1)
        s.setSourceAvailability("unsafe")
        s.setSourceSort("bad")
        self.assertEqual((0, "all", "modified"),
                         (s.sourceCarId, s.sourceAvailability, s.sourceSort))

    def test_details_never_grant_export_or_install_permission(self):
        s = self.service
        s.browseSource(self.rows[2]["path"])
        self.assertFalse(s.selectedSourceExportable)
        self.assertFalse(s.selectedPackageInstallable)
        self.assertEqual("Foreign group", s.sourceDetails["privacyDetail"])
        s.setSourceAvailability("exportable")
        self.assertFalse(s.selectedSourceExportable)

    def test_section_counts_preserve_zero_but_reject_invalid_values(self):
        self.service._current_manifest = {"livery": {"section_counts": {
            "Top": 12, "Left": 0, "Right": True, "Front": -1, "Rear": "2"}}}
        self.assertEqual([{"name": "Top", "count": 12}, {"name": "Left", "count": 0}],
                         self.service.sectionDetails)

    def test_preview_evidence_is_bound_to_accepted_mesh_session(self):
        s = self.service
        s._mesh_serial = 7
        s._selected_package = "fixture.kfpslivery"
        s._current_manifest = {"package_id": "current"}
        evidence = {"geometry": [{"label": "UV3", "value": "Available", "tone": "neutral"}]}
        result = {"ok": True, "request_serial": 7, "package_path": s._selected_package,
                  "payload": {"package_path": s._selected_package, "package_id": "current",
                              "preview_evidence": evidence}}
        with patch.object(s._inspector, "start"):
            s._apply_mesh_result({**result, "request_serial": 6})
            self.assertEqual({}, s.previewEvidence)
            s._apply_mesh_result(result)
        self.assertEqual(evidence, s.previewEvidence)
        s.showSourceGrid()
        self.assertEqual({}, s.previewEvidence)
        self.assertEqual([], s.sectionDetails)

    def test_malformed_or_wrong_package_evidence_is_not_displayed(self):
        s = self.service
        s._mesh_serial = 4
        s._selected_package = "fixture.kfpslivery"
        s._current_manifest = {"package_id": "current"}
        result = {"ok": True, "request_serial": 4, "package_path": s._selected_package,
                  "payload": {"package_path": s._selected_package, "package_id": "different",
                              "preview_evidence": {"warnings": ["wrong car"]}}}
        with patch.object(s._inspector, "start") as start:
            s._apply_mesh_result(result)
            start.assert_not_called()
            self.assertEqual({}, s.previewEvidence)
            result["payload"].update(package_id="current", preview_evidence=["bad"])
            s._apply_mesh_result(result)
        self.assertEqual({}, s.previewEvidence)

    def test_rescan_removing_active_preview_releases_evidence_and_memory_guard(self):
        s = self.service
        s.browseSource(self.rows[0]["path"])
        s._active_source_preview = s.selectedSource
        s._selected_package = "fixture.kfpslivery"
        s._current_manifest = {"package_id": "old"}
        s._preview_evidence = {"warnings": ["old evidence"]}
        s._viewer_url = "http://127.0.0.1/old-session"
        s._viewer_memory_timer.start()
        serial = s._mesh_serial
        self.scan([])
        self.assertFalse(s._viewer_memory_timer.isActive())
        self.assertEqual({}, s.previewEvidence)
        self.assertEqual("", s.viewerUrl)
        self.assertEqual("", s.selectedPackage)
        self.assertGreater(s._mesh_serial, serial)

    def test_failed_cache_cleanup_cannot_leave_previous_preview_details(self):
        s = self.service
        s._selected_package = "fixture.kfpslivery"
        s._current_manifest = {"package_id": "old"}
        s._preview_evidence = {"quality_scale": 4}
        s._viewer_memory_timer.start()
        with patch.object(s._tasks, "start", return_value=True):
            s.clearFullLiveryCache()
        self.assertEqual({}, s.previewEvidence)
        self.assertFalse(s._viewer_memory_timer.isActive())
        s._apply_result({"kind": "clear-cache", "request_serial": s._mesh_serial,
                         "ok": False, "error": "fixture failure"})
        self.assertEqual({}, s.previewEvidence)
        self.assertEqual("", s.selectedPackage)


if __name__ == "__main__":
    unittest.main()
