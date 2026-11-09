"""Native Garage launch boundaries; no game, renderer, network or user windows."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent), str(UI / "tests")]
from PySide6.QtCore import QCoreApplication
from kfps_ui import garage_index as index
from kfps_ui.app_paths import AppPaths
from kfps_ui.editor_service import EditorService
from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
from kfps_ui.experimental.full_livery import operations
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from test_garage_index import car

VEHICLE = {"car_id": 123, "model_code": "QA_CAR"}


def build(wing=3):
    return index.body_snapshot(index.normalize_garage([{**car(ChassisStiffness=8), "RearWing": wing}])[0])


class GarageBuildContractTests(unittest.TestCase):
    def test_launch_logging_keeps_only_outcomes_and_bounded_counts(self):
        log = Mock()
        snapshot = build(123456789)
        snapshot.update(instanceId="PRIVATE_COPY", source="PRIVATE_SOURCE")
        index.log_body_launch(log, "preview", "ready", snapshot)
        line = log.append.call_args.args[0]
        self.assertIn("body_slots=7; known_parts=7; unknown_parts=0", line)
        self.assertIn("outcome=ready", line)
        for private in ("PRIVATE_COPY", "PRIVATE_SOURCE", "123456789", snapshot["fingerprint"], "CarBody"):
            self.assertNotIn(private, line)
        self.assertFalse(log.append.call_args.kwargs["update_status"])
        index.log_body_launch(log, "PRIVATE_TARGET", "PRIVATE_OUTCOME", {"parts": {"private": 123}})
        self.assertIn("body_slots=0; known_parts=0; unknown_parts=0", log.append.call_args.args[0])
        self.assertNotIn("PRIVATE", log.append.call_args.args[0])

    def test_snapshot_is_minimal_stable_and_detached(self):
        raw = car(ChassisStiffness=8)
        a = index.normalize_garage([raw])[0]
        b = index.normalize_garage([{**raw, "Id": 99, "TuneFileName": "Private", "WheelStyle": 25}])[0]
        value = index.body_snapshot(a)
        self.assertEqual(value, index.body_snapshot(b))
        self.assertEqual(set(value), {"version", "parts", "fingerprint"})
        self.assertEqual(set(value["parts"]), set(index.BODY_PARTS))
        self.assertEqual(value["fingerprint"], index.digest({"version": 1, "parts": value["parts"]}))
        a["parts"]["RearWing"] = 99
        self.assertEqual(3, value["parts"]["RearWing"])

    def test_optional_chassis_keeps_absence_for_catalogue_validation_but_not_missing_fields(self):
        row = index.normalize_garage([car()])[0]
        self.assertIsNone(row["parts"]["ChassisStiffness"])
        self.assertIsNone(index.body_snapshot(row)["parts"]["ChassisStiffness"])
        del row["parts"]["ChassisStiffness"]
        with self.assertRaisesRegex(index.GarageError, "Refresh"):
            index.body_snapshot(row)

    def test_bounded_snapshot_validation_and_fingerprint(self):
        original = build()
        self.assertEqual(original, index.validate_body_snapshot(original))
        invalid = [None, {**original, "private": "no"}, {**original, "version": True},
                   {**original, "fingerprint": "A" * 64}, {**original, "fingerprint": "a" * 64}]
        for part in (True, "3", 2**31, -2):
            changed = copy.deepcopy(original)
            changed["parts"]["RearWing"] = part
            invalid.append(changed)
        changed = copy.deepcopy(original)
        del changed["parts"]["Hood"]
        invalid.append(changed)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(index.GarageError):
                index.validate_body_snapshot(value)
        nullable = copy.deepcopy(original)
        nullable["parts"]["Hood"] = None
        nullable["fingerprint"] = index.digest({"version": 1, "parts": nullable["parts"]})
        self.assertEqual(nullable, index.validate_body_snapshot(nullable))

    def test_identity_is_exact_and_never_coerced(self):
        self.assertEqual(VEHICLE, index.validate_vehicle_identity(VEHICLE))
        for value in ({}, {**VEHICLE, "car_id": True}, {**VEHICLE, "car_id": "123"},
                      {**VEHICLE, "model_code": "../QA"}, {**VEHICLE, "extra": 2}):
            with self.subTest(value=value), self.assertRaises(index.GarageError):
                index.validate_vehicle_identity(value)

    def test_old_cache_requires_scan_without_losing_old_comparison_records(self):
        with tempfile.TemporaryDirectory() as root:
            store = index.GarageStore(root)
            rows = index.normalize_garage([car()])
            old = copy.deepcopy(rows)
            del old[0]["parts"]["ChassisStiffness"]
            old[0]["buildSignature"] = index.digest([123, old[0]["parts"]])
            self.assertEqual(rows, index.validate_rows(old))
            state = store.publish("a" * 64, "b" * 64, rows, history=False)
            state["cars"] = old
            state["checksum"] = index.digest({k: v for k, v in state.items() if k != "checksum"})
            index.atomic_json(store.path("a" * 64), state)
            self.assertIsNone(store.load("a" * 64))

    def test_exact_asset_lookup_cannot_substitute_a_model_or_ignore_cancellation(self):
        cancel = threading.Event()
        asset = SimpleNamespace(car_id=123, model_code="QA_CAR")
        with patch("tools.livery.vehicle_assets.load_or_build_vehicle_asset_index", return_value={123: asset}) as load:
            self.assertIs(asset, index.resolve_body_vehicle("game", "cache", 123, model_code="QA_CAR", cancel_event=cancel))
            with self.assertRaisesRegex(index.GarageError, "exactly"):
                index.resolve_body_vehicle("game", "cache", 123, model_code="qa_car")
            with self.assertRaisesRegex(index.GarageError, "exact archive"):
                index.resolve_body_vehicle("game", "cache", 456)
            cancel.set()
            load.reset_mock()
            with self.assertRaises(InterruptedError):
                index.resolve_body_vehicle("game", "cache", 123, cancel_event=cancel)
            load.assert_not_called()


class NativeGarageLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="garage-launch-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        self.log = LogService()
        self.addCleanup(self.log.close)
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None):
            self.preview = FullLiveryService(self.paths, self.log, demo=True)
        self.preview._gate = FullLiveryFeatureGate("candidate", "test")
        self.preview._game_folder = str(self.root / "game")
        self.preview._active = True
        self.addCleanup(self.preview.close)
        self.garage = GarageService(self.paths, self.log, self.preview)
        self.addCleanup(self.garage.close)
        self.garage._set_state({"cars": index.normalize_garage([car(1, ChassisStiffness=8),
            {**car(2, ChassisStiffness=8), "RearWing": 30}]), "scope": "", "scannedAt": "test"})
        self.garage.select("1")
        with patch.object(EditorService, "refresh"):
            self.editor = EditorService(self.paths, Mock(), Mock(), self.log)
        self.addCleanup(self.editor.close)

    def complete_garage_worker(self):
        self.garage._thread.join(timeout=3)
        self.assertFalse(self.garage._thread.is_alive())
        self.app.processEvents()
        self.assertFalse(self.garage.busy)

    def test_exact_selected_copy_handoffs_with_no_idle_work_or_private_identity(self):
        previews, studios = [], []
        self.garage.previewRequested.connect(lambda *values: previews.append(values))
        self.garage.studioRequested.connect(lambda *values: studios.append(values))
        self.assertIsNone(self.garage._thread)
        asset = SimpleNamespace(car_id=123, model_code="QA_CAR")
        with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=asset):
            self.garage.openPreview()
            self.complete_garage_worker()
            self.garage.select("2")
            self.garage.openStudio()
            self.complete_garage_worker()
        self.assertEqual(VEHICLE, previews[0][0])
        self.assertEqual(3, previews[0][1]["parts"]["RearWing"])
        self.assertEqual(30, studios[0][1]["parts"]["RearWing"])
        self.assertEqual("Garage body build", studios[0][2])
        self.assertNotIn("instanceId", json.dumps([previews, studios]))
        self.assertEqual("", self.preview.selectedPackage)

    def test_missing_chassis_does_not_launch_or_silently_scan(self):
        self.garage._set_state({"cars": index.normalize_garage([car()])})
        del self.garage._state["cars"][0]["parts"]["ChassisStiffness"]
        with patch("kfps_ui.garage_service.resolve_body_vehicle") as resolve, patch.object(self.garage, "scanSource") as scan:
            self.garage.openPreview()
            self.garage.openStudio()
            self.assertIn("Refresh", self.garage.status)
            self.assertIsNone(self.garage._thread)
            resolve.assert_not_called()
            scan.assert_not_called()

    def test_cancel_and_selection_change_discard_resolved_build(self):
        received = []
        self.garage.previewRequested.connect(lambda *values: received.append(values))
        asset = SimpleNamespace(car_id=123, model_code="QA_CAR")
        for action in (self.garage.cancel, lambda: (self.garage.select("2"), self.garage.select("1"))):
            with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=asset):
                self.garage.openPreview()
                action()
                self.complete_garage_worker()
            self.assertIn("cancelled", self.garage.status)
        self.assertEqual([], received)

    def test_close_cancels_joins_build_workers_and_rejects_late_handoff(self):
        entered = threading.Event()
        received = []
        self.garage.previewRequested.connect(lambda *values: received.append(values))
        def resolve(*args, cancel_event=None, **kwargs):
            entered.set()
            self.assertTrue(cancel_event.wait(2))
            raise InterruptedError("cancelled")
        with patch("kfps_ui.garage_service.resolve_body_vehicle", side_effect=resolve):
            self.garage.openPreview()
            self.assertTrue(entered.wait(2))
            self.assertTrue(self.garage.close())
        self.app.processEvents()
        self.assertEqual([], received)
        self.assertFalse(self.garage._thread.is_alive())
        worker = self.editor._start_thread(target=lambda: self.editor._cancel_event.wait(2), args=(), name="garage-close-test")
        self.editor.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(set(), self.editor._threads)

    def test_changed_game_folder_discards_resolved_build(self):
        received = []
        self.garage.previewRequested.connect(lambda *values: received.append(values))
        self.garage.studioRequested.connect(lambda *values: received.append(values))
        asset = SimpleNamespace(car_id=123, model_code='QA_CAR')
        for launch in (self.garage.openPreview, self.garage.openStudio):
            with patch('kfps_ui.garage_service.resolve_body_vehicle', return_value=asset):
                launch()
                self.garage._thread.join(timeout=3)
                self.preview._game_folder += '-changed'
                self.app.processEvents()
            self.assertFalse(self.garage.busy)
            self.assertIn('changed', self.garage.status.lower())
        self.assertEqual([], received)

    def test_build_worker_start_failure_recovers_and_can_retry(self):
        received = []
        self.garage.previewRequested.connect(lambda *values: received.append(values))
        with patch('kfps_ui.garage_service.threading.Thread.start', side_effect=RuntimeError('PRIVATE_FAILURE')):
            self.garage.openPreview()
        self.assertFalse(self.garage.busy)
        self.assertIsNone(self.garage._thread)
        self.assertIsNone(self.garage._build_row)
        self.assertNotIn('PRIVATE_FAILURE', self.garage.status)
        with patch('kfps_ui.garage_service.resolve_body_vehicle', return_value=SimpleNamespace(car_id=123, model_code='QA_CAR')):
            self.garage.openPreview()
            self.complete_garage_worker()
        self.assertEqual(1, len(received))

    def test_editor_detaches_request_and_theme_and_does_not_double_launch(self):
        snapshot, identity = build(), dict(VEHICLE)
        theme = {"name": "Test", "variables": {"--accent": "#ee4477"}}
        with patch.object(self.editor, "_start_thread") as start:
            self.editor.launchGarageInLiveryStudio(identity, snapshot, "Garage body build", theme)
            identity["car_id"] = 999
            snapshot["parts"]["RearWing"] = 99
            theme["variables"]["--accent"] = "changed"
            self.editor.launchGarageInLiveryStudio(VEHICLE, build(), "Second")
            start.assert_called_once()
            args = start.call_args.kwargs["args"]
            self.assertEqual((123, 3, "#ee4477"), (args[0]["car_id"], args[1]["parts"]["RearWing"], args[3]["variables"]["--accent"]))
            self.assertEqual("", self.editor.studioPackagePath)

    def test_editor_invalid_requests_fail_before_worker(self):
        with patch.object(self.editor, "_start_thread") as start:
            self.editor.launchGarageInLiveryStudio({}, build(), "Garage")
            self.editor.launchGarageInLiveryStudio(VEHICLE, {}, "Garage")
            self.editor.launchGarageInLiveryStudio(VEHICLE, build(), "bad\nname")
            self.editor.launchGarageInLiveryStudio(VEHICLE, build(), "Garage", {"name": "x" * 32769})
            self.editor.launchGarageInLiveryStudio(VEHICLE, build(), "Garage", {"bad": float("nan")})
            self.assertFalse(self.editor.studioLaunching)
            start.assert_not_called()

    def test_editor_uses_real_host_validator_and_layout_without_artwork(self):
        bridge = UI.parent / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"
        with patch("tools.livery.vehicle_assets.discover_fh6_game_folder", return_value=self.root / "game"), \
                patch("kfps_ui.garage_index.resolve_body_vehicle") as resolve, \
                patch("kfps_ui.editor_service._studio_module_path", return_value=bridge), \
                patch.object(self.editor, "_launch_studio_worker") as launch:
            self.editor._launch_garage_studio_worker(VEHICLE, build(), "Garage body build", None)
            self.assertEqual("QA_CAR", resolve.call_args.kwargs["model_code"])
            layout = launch.call_args.args[0]["layout"]
            self.assertEqual(VEHICLE, layout["vehicle"])
            self.assertEqual(build(), layout["garage_build"])
            self.assertEqual(([], []), (layout["vinyls"], layout["placements"]))
            self.editor._cancel_event.set()
            launch.reset_mock()
            self.editor._launch_garage_studio_worker(VEHICLE, build(), "Garage", None)
            launch.assert_not_called()

    def start_preview(self, snapshot=None):
        with patch.object(self.preview._tasks, "start", return_value=True) as start:
            self.assertTrue(self.preview.previewGarageBuild(VEHICLE, snapshot or build()))
            return start.call_args

    def result(self, call, **updates):
        return {"kind": "garage-mesh", **call.kwargs["metadata"], "ok": True,
                "payload": {"identity": dict(VEHICLE), "garage_fingerprint": build()["fingerprint"],
                            "preview_id": "descriptor-id", "readonly_descriptor": "local-descriptor.json",
                            "readonly_descriptor_sha256": "a" * 64}, **updates}

    def test_preview_dedicated_worker_never_sets_package_state(self):
        self.preview._settings["last_package"] = "keep.kfpslivery"
        self.preview._selected_package = "old.kfpslivery"
        self.preview._current_manifest = {"package_id": "old"}
        call = self.start_preview()
        self.assertEqual("prepare-garage", call.args[0])
        self.assertEqual(build(), call.args[1]["garage_build"])
        self.assertNotIn("save_root", call.args[1])
        self.assertEqual(("", {}), (self.preview.selectedPackage, self.preview._current_manifest))
        self.assertEqual("keep.kfpslivery", self.preview._settings["last_package"])
        self.assertIn("No artwork", self.preview.selectedCounts)
        with patch.object(self.preview._inspector, "start") as inspector:
            self.preview._route_worker_result(self.result(call))
            self.assertEqual("descriptor-id", inspector.call_args.kwargs["package_id"])
            self.assertEqual("", inspector.call_args.kwargs["package"])

    def test_preview_cancel_failure_stale_result_and_return_to_grid(self):
        old = self.start_preview()
        new = self.start_preview(build(30))
        with patch.object(self.preview._inspector, "start") as inspector:
            self.preview._route_worker_result(self.result(old))
            inspector.assert_not_called()
            self.preview._route_worker_result(self.result(new, cancelled=True, ok=False))
            self.assertIn("cancelled", self.preview.status)
            self.preview._route_worker_result(self.result(new, ok=False, error="Unknown part"))
            self.assertEqual("Unknown part", self.preview.summary)
            inspector.assert_not_called()
            self.preview.showSourceGrid()
            self.assertIsNone(self.preview._garage_preview)
            self.preview._route_worker_result(self.result(new))
            inspector.assert_not_called()

    def test_failed_or_inactive_preview_does_not_destroy_previous_state(self):
        self.preview._selected_package = "current"
        with patch.object(self.preview._tasks, "start") as start:
            self.assertFalse(self.preview.previewGarageBuild({}, build()))
            self.assertEqual("current", self.preview.selectedPackage)
            self.preview._active = False
            self.assertFalse(self.preview.previewGarageBuild(VEHICLE, build()))
            start.assert_not_called()

    def test_preview_quality_change_never_reverts_to_stock_package(self):
        self.start_preview()
        with patch.object(self.preview, "_prepare_local_mesh") as prepare:
            self.preview.setViewerQuality(2)
            prepare.assert_not_called()
            self.assertIsNotNone(self.preview._garage_preview)

    def test_retry_uses_same_frozen_build_never_browsed_package(self):
        call = self.start_preview()
        self.preview._browsed_package = "unrelated.kfpslivery"
        self.preview._route_worker_result(self.result(call, ok=False, error="Try again"))
        with patch.object(self.preview._tasks, "start", return_value=True) as start:
            self.assertTrue(self.preview.retryGaragePreview())
            self.assertEqual("prepare-garage", start.call_args.args[0])
            self.assertEqual(build(), start.call_args.args[1]["garage_build"])
        self.preview.showSourceGrid()
        self.assertFalse(self.preview.retryGaragePreview())

    def test_rejected_dispatch_and_mismatched_payload_do_not_start_inspector(self):
        with patch.object(self.preview._tasks, "start", return_value=False):
            self.assertFalse(self.preview.previewGarageBuild(VEHICLE, build()))
            self.assertFalse(self.preview.running)
            self.assertFalse(self.preview.hasGaragePreview)
        call = self.start_preview()
        value = self.result(call)
        value["payload"]["identity"]["car_id"] = 456
        with patch.object(self.preview._inspector, "start") as inspector:
            self.preview._route_worker_result(value)
            inspector.assert_not_called()
            self.assertFalse(self.preview.running)
            self.assertIn("does not match", self.preview.summary)

    def test_preview_first_frame_logs_ready_counts_without_owned_identity(self):
        self.start_preview()
        self.preview._viewer_url = "http://127.0.0.1:1234/test/"
        self.preview.viewerEvent(self.preview._viewer_url, json.dumps({"event": "ready"}))
        self.assertTrue(self.preview.viewerReady)
        self.assertIn("No artwork", self.preview.summary)
        lines = "\n".join(self.log._diagnostic_lines)
        self.assertIn("target=preview; outcome=ready; body_slots=7; known_parts=7", lines)
        self.assertNotIn(build()["fingerprint"], lines)
        self.assertNotIn("instanceId", lines)


class GaragePreviewOperationTests(unittest.TestCase):
    def test_descriptor_identity_is_preserved_and_no_package_is_created(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            snapshot = build()
            descriptor = root / "readonly.json"
            descriptor.write_text(json.dumps({"manifest": {"package_id": "actual-descriptor-id",
                "vehicle": VEHICLE, "inspection_runtime": {"garage_build": snapshot}}}))
            from tools.livery.vehicle_assets import sha256_file
            adapter = SimpleNamespace(prepare_garage=Mock(return_value={"readonly_descriptor": str(descriptor),
                "readonly_descriptor_sha256": sha256_file(descriptor), "preview_evidence": {"example": True}}))
            paths = SimpleNamespace(app_root=root, vehicle_index=root / "index.json")
            payload = {"identity": VEHICLE, "garage_build": snapshot, "game_folder": str(root / "game")}
            with patch("kfps_ui.garage_index.resolve_body_vehicle", return_value=SimpleNamespace(model_code="QA_CAR")), \
                    patch.object(operations, "studio_module", return_value=adapter):
                result = operations.prepare_garage(paths, payload, threading.Event())
                self.assertEqual("actual-descriptor-id", result["preview_id"])
                self.assertEqual(snapshot["fingerprint"], result["garage_fingerprint"])
                self.assertEqual(VEHICLE, result["identity"])
                self.assertNotIn("package_path", result)
                self.assertEqual([descriptor], list(root.iterdir()))
                descriptor.write_text("{}")
                with self.assertRaisesRegex(ValueError, "changed"):
                    operations.prepare_garage(paths, payload, threading.Event())


if __name__ == "__main__":
    unittest.main()
