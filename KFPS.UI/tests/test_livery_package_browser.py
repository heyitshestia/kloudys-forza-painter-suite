from __future__ import annotations

import copy
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]

from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.livery_library import LiveryLibraryFilter
from kfps_ui.log_service import LogService


class LiveryPackageBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="package-browser-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            self.service = FullLiveryService(paths, LogService(), demo=True)
        self.service._gate = FullLiveryFeatureGate("candidate", "test")
        self.addCleanup(self.service.close)
        self.rows = []
        for i, title in enumerate(("Beta", "Alpha", "Gamma [.*]")):
            path = self.root / f"{i}.kfpslivery"
            path.write_bytes(b"not a package: browsing must not decode this")
            self.rows.append(dict(path=str(path), title=title, carId=(100, 200, 100)[i],
                                 modelCode=("CAR_A", "CAR_B", "CAR_A")[i],
                                 placementCount=(i + 1) * 10, portableMesh=i == 1,
                                 created=f"2026-10-{20+i}T12:00:00Z", detail="Indexed"))
        self.refresh(self.rows)

    def refresh(self, rows):
        self.service._apply_result({"kind": "refresh-packages", "ok": True,
                                    "payload": {"rows": rows}})

    def paths(self):
        model = self.service.packageGridModel
        role = next(role for role, name in model.roleNames().items() if bytes(name) == b"path")
        return [model.data(model.index(i, 0), role) for i in range(model.rowCount())]

    def installable_manifest(self):
        return {"package_id": "verified", "sharing": {"exportable": True},
                "files": [{"path": "source/fh6/header"}],
                "livery": {"title": "Verified", "target_car_id": 100}}

    def test_default_contract_and_dedicated_search_notify(self):
        s = self.service
        self.assertIsInstance(s.packageGridModel, LiveryLibraryFilter)
        self.assertIs(s.packageGridModel.sourceModel(), s.packageModel)
        self.assertEqual((3, 3, "", 0, "title"),
                         (s.packageCount, s.visiblePackageCount, s.packageSearch,
                          s.packageCarId, s.packageSort))
        self.assertEqual([self.rows[i]["path"] for i in (1, 0, 2)], self.paths())
        self.assertEqual("", s.browsedPackage)
        self.assertEqual({}, s.packageDetails)
        prop = s.metaObject().property(s.metaObject().indexOfProperty("packageSearch"))
        self.assertEqual(b"packageSearchChanged", bytes(prop.notifySignal().name()))
        notifications = []
        s.packageSearchChanged.connect(lambda: notifications.append(s.packageSearch))
        s.changed.emit()
        s.setPackageCar(100)
        s.setPackageSort("car")
        self.assertEqual([], notifications)
        s.setPackageSearch("Beta")
        s.setPackageSearch("Beta")
        self.assertEqual(["Beta"], notifications)

    def test_filters_are_literal_independent_and_reset_keeps_sort(self):
        s = self.service
        s._selected_source = "source-selection"
        s.setSourceSearch("source query")
        s.setSourceCar(999)
        s.setSourceSort("modified")
        s.setSourceAvailability("preview")
        original = copy.deepcopy(s.packageModel.rows)
        with patch.object(Path, "stat", side_effect=AssertionError("filter IO")), \
                patch.object(s._catalog, "package_rows", side_effect=AssertionError("catalog IO")):
            s.setPackageSearch("[.*]")
            self.assertEqual([self.rows[2]["path"]], self.paths())
            s.setPackageSearch("car_a")
            s.setPackageCar(100)
            self.assertEqual(2, s.visiblePackageCount)
            s.setPackageSort("placements")
            self.assertEqual([self.rows[i]["path"] for i in (2, 0)], self.paths())
            s.resetPackageFilters()
            self.assertEqual(("", 0, "placements", 3),
                             (s.packageSearch, s.packageCarId, s.packageSort, s.visiblePackageCount))
        self.assertEqual(("source-selection", "source query", 999, "modified", "preview"),
                         (s.selectedSource, s.sourceSearch, s.sourceCarId,
                          s.sourceSort, s.sourceAvailability))
        self.assertEqual(original, s.packageModel.rows)

    def test_invalid_filter_values_leave_state_unchanged(self):
        s = self.service
        s.setPackageSearch("Alpha")
        s.setPackageCar(200)
        s.setPackageSort("car")
        for invalid in (None, [], True, -1, 2 ** 40, "200"):
            s.setPackageCar(invalid)
        for invalid in (None, [], True, "modified", "created", "unsafe"):
            s.setPackageSort(invalid)
        for invalid in (None, [], True, 42):
            s.setPackageSearch(invalid)
        self.assertEqual(("Alpha", 200, "car"), (s.packageSearch, s.packageCarId, s.packageSort))

    def test_browse_uses_cached_fields_and_does_not_parse_start_or_save(self):
        s = self.service
        source = self.root / "C_livery"
        source.write_bytes(b"fixture")
        s._replace_source_rows([{"path": str(source), "title": "Source", "exportable": True}])
        s.browseSource(str(source))
        s.setSourceSearch("Source")
        with patch.object(io, "open", side_effect=AssertionError("package parsing")), \
                patch("builtins.open", side_effect=AssertionError("package parsing")), \
                patch.object(s._tasks, "start") as start, \
                patch.object(s, "_save_settings") as save:
            s.browsePackage(self.rows[0]["path"])
            expected = {key: self.rows[0][key] for key in
                        ("path", "title", "created", "modelCode", "carId", "placementCount", "portableMesh")}
            with patch.object(Path, "stat", side_effect=AssertionError("details IO")):
                self.assertEqual(expected, s.packageDetails)
                self.assertEqual(expected, json.loads(json.dumps(s.packageDetails, allow_nan=False)))
                details = s.packageDetails
                details["title"] = "not the cache"
                self.assertEqual("Beta", s.packageDetails["title"])
            start.assert_not_called()
            save.assert_not_called()
        self.assertEqual(self.rows[0]["path"], s.browsedPackage)
        self.assertEqual((str(source), "Source"), (s.selectedSource, s.sourceSearch))
        self.assertEqual("", s.selectedPackage)
        self.assertFalse(s.selectedPackageInstallable)

    def test_missing_unknown_and_malformed_paths_clear_browsed_details(self):
        s = self.service
        for invalid in (None, [], True, "", str(self.root / "unknown.kfpslivery")):
            s.browsePackage(self.rows[0]["path"])
            with patch.object(Path, "is_file", side_effect=AssertionError("unknown path IO")):
                s.browsePackage(invalid)
            self.assertEqual("", s.browsedPackage)
            self.assertEqual({}, s.packageDetails)
        Path(self.rows[0]["path"]).unlink()
        s.browsePackage(self.rows[0]["path"])
        self.assertEqual({}, s.packageDetails)
        with patch.object(Path, "is_file", side_effect=OSError("unavailable")):
            s.browsePackage(self.rows[1]["path"])
        self.assertEqual("", s.browsedPackage)

    def test_refresh_updates_metadata_and_clears_removed_browsed_package(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        s.setPackageCar(100)
        s.setPackageSearch("Beta")
        self.refresh([{**self.rows[0], "title": "New title"}])
        self.assertEqual("New title", s.packageDetails["title"])
        self.assertEqual(0, s.visiblePackageCount)
        self.refresh([self.rows[1]])
        self.assertEqual(("", {}), (s.browsedPackage, s.packageDetails))
        self.assertEqual((100, "Beta"), (s.packageCarId, s.packageSearch))
        ghost = next(item for item in s.packageCars if item["value"] == 100)
        self.assertIn("not in current", ghost["label"])

    def test_malformed_rows_have_safe_display_values_without_mutation(self):
        malformed = {"path": self.rows[0]["path"], "title": [], "modelCode": {},
                     "created": float("inf"), "carId": True, "placementCount": float("nan"),
                     "portableMesh": "true", "private": object()}
        original = dict(malformed)
        self.refresh([None, [], "bad", {}, {"path": []}, {"path": "bad\0path"}, malformed])
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        self.assertEqual({"path": self.rows[0]["path"], "title": "", "created": "",
                          "modelCode": "", "carId": 0, "placementCount": 0,
                          "portableMesh": False}, s.packageDetails)
        self.assertEqual(1, s.packageCount)
        self.assertEqual(original, malformed)
        json.dumps(s.packageDetails, allow_nan=False)
        self.assertNotIn("modified", s.packageDetails)
        self.assertEqual([0], [item["value"] for item in s.packageCars])

    def test_explicit_preview_uses_existing_verification_route(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        method = s.metaObject().method(s.metaObject().indexOfMethod("previewBrowsedPackage()"))
        self.assertEqual("bool", method.typeName())
        with patch.object(s._tasks, "start", return_value=True) as start:
            self.assertIs(True, s.previewBrowsedPackage())
        self.assertEqual("open-package", start.call_args.args[0])
        self.assertEqual(self.rows[0]["path"], start.call_args.args[1]["path"])
        self.assertEqual(s._selection_serial, start.call_args.kwargs["metadata"]["selection_serial"])
        self.assertEqual(self.rows[0]["path"], s.selectedPackage)
        self.assertFalse(s.selectedPackageInstallable)

    def test_only_accepted_verification_can_restore_installation_rights(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(s._tasks, "start", return_value=True) as start:
            s.installSelectedPackage()
            start.assert_not_called()
            s.previewBrowsedPackage()
        metadata = start.call_args.kwargs["metadata"]
        with patch.object(s, "_prepare_local_mesh") as prepare, \
                patch.object(s, "_refresh_decisions"), patch.object(s, "_save_settings") as save, \
                patch("kfps_ui.full_livery_service.compatibility_decision", return_value={"installable": True}):
            s._apply_result({"kind": "open-package", "ok": True, **metadata,
                             "payload": {"path": self.rows[0]["path"],
                                         "manifest": self.installable_manifest(), "remember": True}})
            self.assertTrue(s.selectedPackageInstallable)
            prepare.assert_called_once()
            save.assert_called_once()
            s.browsePackage(self.rows[0]["path"])
            self.assertFalse(s.selectedPackageInstallable)

    def test_catalog_reload_and_refresh_use_the_same_safe_cached_contract(self):
        s = self.service
        rows = [None, {"path": []}, {**self.rows[0], "mtimeNs": "bad"},
                {**self.rows[1], "mtimeNs": 123}]
        original = copy.deepcopy(rows)
        with patch.object(s._catalog, "source_rows", return_value=[]), \
                patch.object(s._catalog, "package_rows", return_value=rows), \
                patch.object(s._tasks, "start") as start:
            s._load_catalog_models()
            self.assertEqual(2, s.packageCount)
            s.browsePackage(self.rows[0]["path"])
            s.setPackageSearch("Beta")
            s.setPackageSort("placements")
            s.refreshPackages()
            start.assert_not_called()
        self.assertEqual(("Beta", "placements", 1),
                         (s.packageSearch, s.packageSort, s.visiblePackageCount))
        self.assertEqual("Beta", s.packageDetails["title"])
        self.assertEqual(original, rows)

    def test_catalog_refresh_checks_availability_once_per_file_not_per_filter(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(Path, "is_file", return_value=False) as exists:
            self.refresh(self.rows)
            self.assertEqual(len(self.rows), exists.call_count)
            self.assertTrue(all(not row['available'] for row in s.packageModel.rows))
            exists.reset_mock()
            s.setPackageSearch('Beta')
            s.setPackageSort('placements')
            exists.assert_not_called()
        self.assertEqual(("", {}), (s.browsedPackage, s.packageDetails))

    def test_missing_or_malformed_row_collections_are_empty(self):
        for rows in (None, {}, "bad", 5):
            with self.subTest(rows=rows):
                self.refresh(rows)
                self.assertEqual((0, 0), (self.service.packageCount, self.service.visiblePackageCount))

    def test_sort_ties_and_numeric_metadata_are_deterministic(self):
        rows = [dict(self.rows[0], title="alpha", carId="10", placementCount="25", portableMesh=1),
                dict(self.rows[1], title="Alpha", carId=2, placementCount=10, portableMesh="false"),
                dict(self.rows[2], title="beta", carId=True, placementCount=True)]
        self.refresh(list(reversed(rows)))
        s = self.service
        self.assertEqual([row["path"] for row in rows], self.paths())
        s.setPackageSort("car")
        self.assertEqual([rows[i]["path"] for i in (2, 1, 0)], self.paths())
        s.setPackageSort("placements")
        self.assertEqual([row["path"] for row in rows], self.paths())
        s.browsePackage(rows[0]["path"])
        self.assertEqual((10, 25, True), (s.packageDetails["carId"],
                                         s.packageDetails["placementCount"], s.packageDetails["portableMesh"]))

    def test_source_browsing_keeps_package_filters_and_browsed_selection(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        s.setPackageSearch("Beta")
        s.setPackageCar(100)
        s.setPackageSort("placements")
        source = self.root / "C_livery"
        source.write_bytes(b"fixture")
        s._replace_source_rows([{"path": str(source), "title": "Source"}])
        s.browseSource(str(source))
        self.assertEqual((self.rows[0]["path"], "Beta", 100, "placements"),
                         (s.browsedPackage, s.packageSearch, s.packageCarId, s.packageSort))
        self.assertEqual(str(source), s.selectedSource)

    def test_preview_rechecks_removed_file_without_a_worker(self):
        s = self.service
        source = self.root / "C_livery"
        source.write_bytes(b"source A")
        s._replace_source_rows([{"path": str(source), "title": "Source A"}])
        s.browseSource(str(source))
        s.browsePackage(self.rows[0]["path"])
        Path(self.rows[0]["path"]).unlink()
        with patch.object(s._tasks, "start") as start:
            self.assertIs(False, s.previewBrowsedPackage())
            start.assert_not_called()
        self.assertEqual(("", {}), (s.browsedPackage, s.packageDetails))
        self.assertEqual(str(source), s.selectedSource)
        self.assertEqual("", s.selectedPackage)

    def test_package_preview_returns_false_when_closed_or_gated(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(s, "selectPackage") as select:
            with patch.object(s, "_closed", True):
                self.assertIs(False, s.previewBrowsedPackage())
            with patch.object(s, "_gate", FullLiveryFeatureGate("disabled", "test")):
                self.assertIs(False, s.previewBrowsedPackage())
            select.assert_not_called()

    def test_package_preview_returns_false_when_dispatch_is_rejected(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(s._tasks, "start", return_value=False):
            self.assertIs(False, s.previewBrowsedPackage())
        self.assertFalse(s.running)
        self.assertEqual("", s.selectedPackage)
        self.assertEqual(self.rows[0]["path"], s.browsedPackage)

    def test_package_preview_returns_false_if_file_disappears_during_selection(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        Path(self.rows[0]["path"]).unlink()
        with patch.object(s, "_available_package", return_value=True), \
                patch.object(s._tasks, "start") as start:
            self.assertIs(False, s.previewBrowsedPackage())
            start.assert_not_called()
        self.assertEqual("", s.selectedPackage)

    def test_cache_clear_does_not_open_gallery_source_or_browsed_package(self):
        s = self.service
        source = self.root / "C_livery"
        source.write_bytes(b"source A")
        s._replace_source_rows([{"path": str(source), "title": "Source A"}])
        for browse_package in (False, True):
            with self.subTest(browse_package=browse_package):
                s.browseSource(str(source))
                if browse_package:
                    s.browsePackage(self.rows[1]["path"])
                with patch.object(s._tasks, "start", return_value=True) as start, \
                        patch.object(s, "selectSource") as reopen_source, \
                        patch.object(s, "_open_package") as reopen_package:
                    s.clearFullLiveryCache()
                    metadata = start.call_args.kwargs["metadata"]
                    self.assertEqual(("", ""), (metadata["reopen_source"], metadata["reopen_package"]))
                    s._apply_result({"kind": "clear-cache", "ok": True, **metadata, "payload": {}})
                    reopen_source.assert_not_called()
                    reopen_package.assert_not_called()
                    start.assert_called_once()
                self.assertEqual(str(source), s.selectedSource)
                if browse_package:
                    self.assertEqual(self.rows[1]["path"], s.browsedPackage)

    def test_cache_clear_does_not_open_a_remembered_unverified_package(self):
        s = self.service
        s._selected_package = self.rows[0]["path"]
        with patch.object(s._tasks, "start", return_value=True) as start, \
                patch.object(s, "_open_package") as reopen:
            s.clearFullLiveryCache()
            metadata = start.call_args.kwargs["metadata"]
            self.assertEqual("", metadata["reopen_package"])
            s._apply_result({"kind": "clear-cache", "ok": True, **metadata, "payload": {}})
            reopen.assert_not_called()

    def test_cache_clear_preserves_actual_source_and_package_preview_rebuilds(self):
        s = self.service
        source = self.root / "C_livery"
        source.write_bytes(b"source A")
        for source_preview in (True, False):
            with self.subTest(source_preview=source_preview):
                s._selected_source = str(source)
                s._active_source_preview = str(source) if source_preview else ""
                s._selected_package = self.rows[0]["path"]
                s._current_manifest = self.installable_manifest()
                with patch.object(s._tasks, "start", return_value=True) as start, \
                        patch.object(s, "selectSource") as reopen_source, \
                        patch.object(s, "_open_package") as reopen_package:
                    s.clearFullLiveryCache()
                    metadata = start.call_args.kwargs["metadata"]
                    expected = (str(source), "") if source_preview else ("", self.rows[0]["path"])
                    self.assertEqual(expected, (metadata["reopen_source"], metadata["reopen_package"]))
                    s._apply_result({"kind": "clear-cache", "ok": True, **metadata, "payload": {}})
                    if source_preview:
                        reopen_source.assert_called_once_with(str(source))
                        reopen_package.assert_not_called()
                    else:
                        reopen_package.assert_called_once_with(self.rows[0]["path"], remember=False)
                        reopen_source.assert_not_called()

    def test_cache_clear_late_completion_cannot_replace_new_package_browse(self):
        s = self.service
        source = self.root / "C_livery"
        source.write_bytes(b"source A")
        s._selected_source = str(source)
        s._active_source_preview = str(source)
        with patch.object(s._tasks, "start", return_value=True) as start:
            s.clearFullLiveryCache()
        metadata = start.call_args.kwargs["metadata"]
        self.assertEqual(str(source), metadata["reopen_source"])
        s.browsePackage(self.rows[1]["path"])
        with patch.object(s, "selectSource") as reopen_source, \
                patch.object(s, "_open_package") as reopen_package:
            s._apply_result({"kind": "clear-cache", "ok": True, **metadata, "payload": {}})
            reopen_source.assert_not_called()
            reopen_package.assert_not_called()
        self.assertEqual(self.rows[1]["path"], s.browsedPackage)
        self.assertEqual(str(source), s.selectedSource)

    def test_browse_invalidates_verified_preview_and_all_late_preview_results(self):
        s = self.service
        old = self.rows[0]["path"]
        s._selected_package = old
        s._current_manifest = self.installable_manifest()
        s._preview_evidence = {"quality_scale": 4}
        s._viewer_url = "http://127.0.0.1/old"
        s._viewer_memory_timer.start()
        serial, mesh_serial, source_serial = s._selection_serial, s._mesh_serial, s._source_preview_serial
        with patch("kfps_ui.full_livery_service.compatibility_decision", return_value={"installable": True}):
            self.assertTrue(s.selectedPackageInstallable)
            s.browsePackage(self.rows[1]["path"])
            self.assertFalse(s.selectedPackageInstallable)
            self.assertEqual(("", {}, ""), (s.selectedPackage, s.previewEvidence, s.viewerUrl))
            self.assertFalse(s._viewer_memory_timer.isActive())
            # ABA selection must reject an old verification even when the path matches again.
            s.browsePackage(old)
            with patch.object(s._tasks, "start", return_value=True), \
                    patch.object(s._inspector, "start") as inspector, \
                    patch.object(s, "_save_settings") as save:
                s.previewBrowsedPackage()
                s._apply_result({"kind": "open-package", "ok": True, "package_path": old,
                                 "selection_serial": serial,
                                 "payload": {"path": old, "manifest": self.installable_manifest()}})
                s._apply_result({"kind": "preview", "ok": True, "request_serial": source_serial,
                                 "source_path": s.selectedSource,
                                 "payload": {"path": old, "manifest": self.installable_manifest()}})
                s._apply_mesh_result({"ok": True, "package_path": old, "request_serial": mesh_serial,
                                      "payload": {"package_path": old, "package_id": "verified"}})
                inspector.assert_not_called()
                save.assert_not_called()
            self.assertFalse(s.selectedPackageInstallable)
        self.assertGreater(s._selection_serial, serial)
        self.assertGreater(s._mesh_serial, mesh_serial)
        self.assertGreater(s._source_preview_serial, source_serial)

    def test_removed_browsed_package_rejects_inflight_verification(self):
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(s._tasks, "start", return_value=True):
            s.previewBrowsedPackage()
        serial = s._selection_serial
        self.refresh([])
        with patch.object(s, "_accept_open_package") as accept:
            s._apply_result({"kind": "open-package", "ok": True,
                             "package_path": self.rows[0]["path"], "selection_serial": serial,
                             "payload": {"manifest": self.installable_manifest()}})
            accept.assert_not_called()
        self.assertEqual(("", "", {}), (s.browsedPackage, s.selectedPackage, s.packageDetails))

    def test_direct_external_preview_does_not_require_catalog_membership(self):
        external = self.root / "external.kfpslivery"
        external.write_bytes(b"fixture")
        s = self.service
        s.browsePackage(self.rows[0]["path"])
        with patch.object(s._tasks, "start", return_value=True) as start:
            s.openPreviewPackage(str(external))
        self.assertEqual(str(external), s.selectedPackage)
        self.assertEqual("open-package", start.call_args.args[0])
        self.refresh([])
        self.assertEqual(str(external), s.selectedPackage)
        self.assertTrue(s.pageActive)

    def test_late_cancel_completion_still_resumes_activation(self):
        s = self.service
        s._active = True
        s._resume_after_cancel = True
        with patch.object(s, "scanSaves") as scan:
            s._route_worker_result({"kind": "open-package", "ok": True,
                                    "package_path": "old", "selection_serial": -1})
            scan.assert_called_once_with()
        self.assertFalse(s._resume_after_cancel)

    def test_late_index_completion_does_not_auto_open_after_browsing(self):
        s = self.service
        with patch.object(s._tasks, "start", return_value=True) as start:
            s._refresh_packages_then_open(self.rows[0]["path"])
        metadata = start.call_args.kwargs["metadata"]
        self.assertEqual(s._selection_serial, metadata["selection_serial"])
        s.browsePackage(self.rows[1]["path"])
        with patch.object(s, "selectPackage") as select:
            s._apply_result({"kind": "refresh-packages", "ok": True, **metadata,
                             "payload": {"rows": self.rows}})
            select.assert_not_called()
        self.assertEqual(self.rows[1]["path"], s.browsedPackage)
        self.assertEqual("", s.selectedPackage)

    def test_late_add_and_migration_completion_only_refresh_the_index(self):
        s = self.service
        for kind in ("add-package", "migrate-package"):
            with self.subTest(kind=kind):
                s._running = False
                with patch.object(s._tasks, "start", return_value=True) as start:
                    if kind == "add-package":
                        s._start_add_package(self.rows[0]["path"])
                    else:
                        s._start_saved_package_migration(self.rows[0]["path"], remember=True)
                metadata = start.call_args.kwargs["metadata"]
                self.assertEqual(s._selection_serial, metadata["selection_serial"])
                s.browsePackage(self.rows[1]["path"])
                with patch.object(s, "refreshPackages") as refresh, \
                        patch.object(s, "_refresh_packages_then_open") as refresh_open, \
                        patch.object(s, "_open_package") as open_package:
                    s._apply_result({"kind": kind, "ok": True, **metadata,
                                     "payload": {"path": self.rows[0]["path"]}})
                    refresh.assert_called_once_with()
                    refresh_open.assert_not_called()
                    open_package.assert_not_called()
                self.assertEqual("", s.selectedPackage)

    def test_5000_rows_use_cached_filtering_without_repeated_sorting(self):
        rows = [dict(path=str(self.root / f"Package {i:05d}.kfpslivery"),
                     title=f"Package {i:05d}", modelCode=f"CAR_{i % 7}", carId=i % 11 + 1,
                     placementCount=(i * 73) % 12001, created="2026-10-29", portableMesh=False)
                for i in range(5000)]
        original = copy.deepcopy(rows)
        self.refresh(rows)
        s = self.service
        self.assertEqual(5000, s.packageCount)
        self.assertEqual(5000, s.visiblePackageCount)
        started = time.perf_counter()
        with patch.object(Path, "stat", side_effect=AssertionError("filter stat")), \
                patch.object(io, "open", side_effect=AssertionError("filter read")), \
                patch.object(s._catalog, "package_rows", side_effect=AssertionError("catalog read")), \
                patch.object(s.packageGridModel, "lessThan", wraps=s.packageGridModel.lessThan) as compare:
            s.setPackageSearch("Package")
            self.assertEqual(5000, s.visiblePackageCount)
            self.assertEqual(0, compare.call_count)
            s.setPackageCar(3)
            s.setPackageSearch("CAR_2")
            s.setPackageSort("placements")
            expected = [row for row in rows if row["carId"] == 3 and row["modelCode"] == "CAR_2"]
            expected.sort(key=lambda row: (-row["placementCount"], row["path"].casefold(), row["path"]))
            self.assertEqual([row["path"] for row in expected], self.paths())
        self.assertEqual(rows, original)
        print(f"5000-package cached filter/sort: {time.perf_counter() - started:.3f}s")


if __name__ == "__main__":
    unittest.main(verbosity=2)
