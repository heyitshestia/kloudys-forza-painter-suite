"""Stock and artwork workflow boundaries, without opening user windows."""
from types import SimpleNamespace
from unittest.mock import patch
import json
import hashlib
import threading
import unittest

import test_garage_launch as fixtures
from test_garage_launch import VEHICLE
from kfps_ui.experimental.full_livery import operations


class GarageWorkflowTests(unittest.TestCase):
    setUpClass = fixtures.NativeGarageLaunchTests.__dict__["setUpClass"]
    setUp = fixtures.NativeGarageLaunchTests.setUp
    complete_garage_worker = fixtures.NativeGarageLaunchTests.complete_garage_worker

    def stock(self):
        self.garage._catalogue = {456: {"title": "Stock car", "modelCode": "QA_STOCK"}}
        self.garage._sources_dirty = True
        self.garage._rebuild()
        self.garage.select("catalogue:456")

    def test_stock_launch_needs_no_owned_snapshot_and_exact_model(self):
        self.stock()
        received = []
        self.garage.stockPreviewRequested.connect(received.append)
        asset = SimpleNamespace(car_id=456, model_code="QA_STOCK")
        with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=asset) as resolve:
            self.garage.openPreview()
            self.complete_garage_worker()
        self.assertEqual([{"car_id": 456, "model_code": "QA_STOCK"}], received)
        self.assertEqual("QA_STOCK", resolve.call_args.kwargs["model_code"])
        self.assertIsNone(self.garage._row())

    def test_stock_selection_change_discards_completed_launch(self):
        self.stock()
        received = []
        self.garage.stockStudioRequested.connect(received.append)
        with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=SimpleNamespace(car_id=456, model_code="QA_STOCK")):
            self.garage.openStudio()
            self.garage.select("1")
            self.complete_garage_worker()
        self.assertEqual([], received)

    def test_stock_preview_has_explicit_mode_and_safe_retry(self):
        with patch.object(self.preview._tasks, "start", return_value=True) as start:
            self.assertTrue(self.preview.previewStockCar(VEHICLE))
            request = start.call_args.args[1]
            self.assertTrue(request["stock"])
            self.assertNotIn("garage_build", request)
            self.assertEqual("stock", start.call_args.kwargs["metadata"]["garage_fingerprint"])
            self.preview._viewer_preparation_progress({"request_serial": self.preview._mesh_serial,
                "garage_fingerprint": "stock", "message": "Stock progress"})
            self.assertEqual("Stock progress", self.preview.status)
            self.preview._running = False
            self.assertTrue(self.preview.retryGaragePreview())
        with patch.object(self.preview._inspector, "start") as viewer:
            self.preview._apply_garage_result({"request_serial": self.preview._mesh_serial,
                "garage_fingerprint": "stock", "ok": True, "payload": {
                    "identity": VEHICLE, "garage_fingerprint": "wrong"}})
            viewer.assert_not_called()

    def artwork(self):
        source = self.root / "account/Profile/garage.json"
        self.garage._source = str(source)
        owned = self.root / "account/Livery_test/C_livery"
        other = self.root / "other/Livery_test/C_livery"
        for file in (owned, other):
            file.parent.mkdir(parents=True)
            file.write_bytes(b"fixture")
        package = self.root / "artwork.kfpslivery"
        package.write_bytes(b"fixture")
        self.preview._replace_source_rows([
            {"path": str(owned), "carId": 123, "title": "Owned", "exportable": True},
            {"path": str(other), "carId": 123, "title": "Other account", "exportable": True}])
        self.preview.packageModel.replace([
            {"path": str(package), "carId": 123, "title": "Package", "available": True},
            {"path": str(package) + "missing", "carId": 123, "available": False},
            {"path": str(package) + "other", "carId": 456, "available": True}])
        self.garage._sources_dirty = True
        self.garage._rebuild()
        return owned, package

    def test_artwork_choices_use_current_copy_and_only_compatible_local_library(self):
        owned, package = self.artwork()
        options = self.garage.artworkOptions
        self.assertEqual({str(owned), str(package)}, {r["path"] for r in options})
        received = []
        self.garage.artworkRequested.connect(lambda *args: received.append(args))
        with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=SimpleNamespace(**VEHICLE)):
            self.garage.select("2")
            self.garage.openArtwork(str(package), "package")
            self.complete_garage_worker()
        self.assertEqual((str(package), "package"), received[0][2:4])
        self.assertEqual(hashlib.sha256(b"fixture").hexdigest(), received[0][4])
        self.assertEqual(30, received[0][1]["parts"]["RearWing"])
        self.assertEqual(b"fixture", package.read_bytes())

    def test_removed_artwork_and_selection_change_cannot_launch(self):
        _, package = self.artwork()
        received = []
        self.garage.artworkRequested.connect(lambda *args: received.append(args))
        with patch("kfps_ui.garage_service.resolve_body_vehicle", return_value=SimpleNamespace(**VEHICLE)):
            self.garage.openArtwork(str(package), "package")
            self.preview.packageModel.replace([])
            self.garage._sources_dirty = True
            self.garage._rebuild()
            self.complete_garage_worker()
        self.assertEqual([], received)
        self.assertIn("changed", self.garage.status)
        self.garage.openArtwork(str(package), "package")
        self.assertIn("no longer available", self.garage.status)

    def test_artwork_changed_before_worker_is_rejected_before_car_resolution(self):
        _, package = self.artwork()
        received = []
        self.garage.artworkRequested.connect(lambda *args: received.append(args))
        with patch.object(self.garage, "_start_worker") as start:
            self.garage.openArtwork(str(package), "package")
        package.write_bytes(b"different artwork")
        with patch("kfps_ui.garage_service.resolve_body_vehicle") as resolve:
            start.call_args.args[0]()
            self.app.processEvents()
            resolve.assert_not_called()
        self.assertEqual([], received)
        self.assertIn("changed", self.garage.status)

    def test_artwork_fingerprint_is_cancelled_and_bounded(self):
        from kfps_ui.garage_index import artwork_identity, artwork_fingerprint
        _, package = self.artwork()
        stamp = artwork_identity(package, "package")
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            artwork_fingerprint(package, "package", stamp, cancel)
        with self.assertRaises(ValueError):
            artwork_identity(package, "invalid")

    def test_stock_worker_rejects_ambiguous_mode_and_validates_descriptor(self):
        paths = SimpleNamespace(app_root=self.root, vehicle_index=self.root / "index.json")
        payload = {"identity": VEHICLE, "game_folder": str(self.root), "stock": True}
        with patch.object(operations, "studio_module") as adapter:
            for changes in ({"stock": "true"}, {"garage_build": fixtures.build()}, {"garage_build": None}):
                with self.assertRaises(ValueError):
                    operations.prepare_garage(paths, {**payload, **changes}, threading.Event())
            adapter.assert_not_called()
        descriptor = self.root / "stock.json"
        descriptor.write_text(json.dumps({"manifest": {"package_id": "stock-123", "vehicle": VEHICLE,
            "inspection_runtime": {}}}))
        from tools.livery.vehicle_assets import sha256_file
        adapter = SimpleNamespace(prepare_stock=fixtures.Mock(return_value={"readonly_descriptor": str(descriptor),
            "readonly_descriptor_sha256": sha256_file(descriptor)}))
        with patch("kfps_ui.garage_index.resolve_body_vehicle", return_value=SimpleNamespace(**VEHICLE)), \
                patch.object(operations, "studio_module", return_value=adapter):
            value = operations.prepare_garage(paths, payload, threading.Event())
            self.assertEqual("stock", value["garage_fingerprint"])
            self.assertEqual("stock-123", value["preview_id"])


if __name__ == "__main__":
    unittest.main()
