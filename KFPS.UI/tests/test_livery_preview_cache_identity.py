from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile
import zlib

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "tests"), str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_full_livery_package import (
    destination_header,
    full_livery_job_paths,
    raster_livery_payload,
)
from kfps_ui.app_paths import AppPaths
from kfps_ui.experimental.full_livery import jobs, operations
from tools.cgroup.shape_identity import VINYL_TYPE_BASES
from tools.livery import vehicle_assets
from tools.livery.package import validate_livery_inspection_artifact


class PreviewCacheIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "runtime/test-runs/livery-retry-20261021/identity/tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="case-", dir=temporary_root)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.paths = full_livery_job_paths(AppPaths(
            app_root=self.root,
            ui_root=UI,
            qml_root=UI / "qml",
            asset_root=UI / "assets",
            runtime_root=self.root / "runtime",
            bundled_python=ROOT / "python/python.exe",
        ))
        self.game = self.root / "artificial-game"
        self.cars = self.game / "media/cars"
        self.cars.mkdir(parents=True)
        self.car_id = 3304
        self._write_car("TEST_CAR", self.car_id)
        self.source = self.root / "artificial-source/C_livery"
        self.source.parent.mkdir()
        self.header = self.source.parent / "header"
        self._write_source()
        self.header.write_bytes(destination_header(car_id=self.car_id))
        self.payload = {"source": str(self.source), "game_folder": str(self.game)}
        self.cancel = threading.Event()

    def _write_car(self, name, car_id):
        with zipfile.ZipFile(self.cars / (name + ".zip"), "w") as archive:
            archive.writestr(f"Scene/animations/Mojo/clip/carclips_{car_id}.clipd", b"fixture")

    def _write_source(self, color=(255, 80, 145, 255)):
        payload = bytearray(raster_livery_payload(raster_id=1, car_id=self.car_id))
        shape = 0x40 + 4 + 0x11
        struct.pack_into("<H", payload, shape + 2, VINYL_TYPE_BASES["Primitives"] & 0xFFFF)
        payload[shape + 28:shape + 32] = bytes(color)
        compressed = zlib.compress(payload)
        self.source.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)

    def _inputs(self):
        return {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (self.source, self.header)}

    def _warm_index(self):
        return vehicle_assets.load_or_build_vehicle_asset_index(self.game, self.paths.vehicle_index)

    def _preview(self):
        return jobs.preview_source(self.paths, self.payload, self.cancel)

    def _verify_high_quality_provider(self, preview):
        manifest = validate_livery_inspection_artifact(preview["path"])
        self.assertEqual(manifest["package_id"], preview["manifest"]["package_id"])
        self.assertEqual(1, manifest["livery"]["decoded_layer_count"])
        layers = []

        def prepare(_root, _game, asset, package, **options):
            self.assertEqual(self.car_id, asset.car_id)
            self.assertEqual(Path(preview["path"]), package)
            self.assertEqual(2, options["quality_scale"])
            self.assertTrue(callable(options["layer_provider"]))
            # Run the real first-create identity, ownership and source decoding checks.
            layers.extend(options["layer_provider"]())
            return {"quality_notes": []}

        adapter = SimpleNamespace(prepare_readonly=Mock(side_effect=prepare))
        payload = {
            "package_id": manifest["package_id"],
            "package_path": preview["path"],
            "car_id": self.car_id,
            "source_path": str(self.source),
            "game_folder": str(self.game),
            "quality_scale": 2,
        }
        with (
            patch.object(operations, "studio_module", return_value=adapter),
            patch.object(operations.psutil, "virtual_memory",
                         return_value=SimpleNamespace(available=8 * 1024**3)),
        ):
            jobs.prepare_mesh(self.paths, payload, self.cancel)
        adapter.prepare_readonly.assert_called_once()
        self.assertEqual(1, len(layers))
        return layers

    def _assert_current_target(self, preview):
        expected, _ = jobs._preview_target(self.paths, self.source, str(self.game))
        self.assertEqual(expected, Path(preview["path"]))

    def test_absent_index_first_create_passes_high_quality_source_check(self):
        original = self._inputs()
        self.assertFalse(self.paths.vehicle_index.exists())
        with patch.object(vehicle_assets, "build_vehicle_asset_index",
                          wraps=vehicle_assets.build_vehicle_asset_index) as build:
            preview = self._preview()
            self.assertFalse(preview["cache_hit"])
            self.assertEqual(original, self._inputs())
            self._verify_high_quality_provider(preview)
        build.assert_called_once()
        self._assert_current_target(preview)
        self.assertEqual(original, self._inputs())

    def test_stale_index_first_create_passes_high_quality_source_check(self):
        self._warm_index()
        old_index = self.paths.vehicle_index.read_bytes()
        original = self._inputs()
        self._write_car("ADDED_CAR", 3305)
        with patch.object(vehicle_assets, "build_vehicle_asset_index",
                          wraps=vehicle_assets.build_vehicle_asset_index) as build:
            preview = self._preview()
            self.assertEqual(original, self._inputs())
            self._verify_high_quality_provider(preview)
        build.assert_called_once()
        self.assertFalse(preview["cache_hit"])
        self.assertNotEqual(old_index, self.paths.vehicle_index.read_bytes())
        self._assert_current_target(preview)
        self.assertEqual(original, self._inputs())

    def test_stale_index_invalidates_an_existing_preview_before_reuse(self):
        self._warm_index()
        first = self._preview()
        original = self._inputs()
        self._write_car("ADDED_CAR", 3305)
        with patch.object(vehicle_assets, "build_vehicle_asset_index",
                          wraps=vehicle_assets.build_vehicle_asset_index) as build:
            rebuilt = self._preview()
            self.assertEqual(original, self._inputs())
            self._verify_high_quality_provider(rebuilt)
        build.assert_called_once()
        self.assertFalse(rebuilt["cache_hit"])
        self.assertNotEqual(first["path"], rebuilt["path"])
        self._assert_current_target(rebuilt)
        self.assertEqual(original, self._inputs())

    def test_unchanged_cache_reuses_index_and_preview_without_full_rescan(self):
        self._warm_index()
        first = self._preview()
        files = (self.paths.vehicle_index, Path(first["path"]))
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in files]
        original = self._inputs()
        with (
            patch.object(vehicle_assets, "build_vehicle_asset_index",
                         side_effect=AssertionError("Unchanged index must not be rebuilt")) as build,
            patch.object(jobs, "create_local_livery_preview",
                         side_effect=AssertionError("Unchanged preview must not be rebuilt")) as create,
        ):
            repeated = self._preview()
            self._verify_high_quality_provider(repeated)
        build.assert_not_called()
        create.assert_not_called()
        self.assertTrue(repeated["cache_hit"])
        self.assertEqual(first["path"], repeated["path"])
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in files])
        self.assertEqual(original, self._inputs())

    def _change_input(self, name):
        if name == "source":
            self._write_source(color=(80, 255, 145, 255))
        else:
            self.header.write_bytes(destination_header(car_id=self.car_id, creator_tag=b"CHANGED1"))

    def _check_changed_input(self, name):
        self._warm_index()
        first = self._preview()
        self._change_input(name)
        changed = self._inputs()
        with self.assertRaisesRegex(ValueError, "local livery changed"):
            self._verify_high_quality_provider(first)
        with patch.object(vehicle_assets, "build_vehicle_asset_index",
                          side_effect=AssertionError("Source edits must not rebuild the vehicle index")):
            rebuilt = self._preview()
            self._verify_high_quality_provider(rebuilt)
        self.assertFalse(rebuilt["cache_hit"])
        self.assertNotEqual(first["path"], rebuilt["path"])
        self._assert_current_target(rebuilt)
        self.assertEqual(changed, self._inputs())

    def test_source_change_invalidates_preview_and_rejects_old_provider(self):
        self._check_changed_input("source")

    def test_header_change_invalidates_preview_and_rejects_old_provider(self):
        self._check_changed_input("header")

    def test_changes_during_creation_are_not_blessed_by_rekeying(self):
        self._warm_index()
        for name in ("source", "header"):
            with self.subTest(input=name):
                self._write_source()
                self.header.write_bytes(destination_header(car_id=self.car_id))
                target, _ = jobs._preview_target(self.paths, self.source, str(self.game))
                target.unlink(missing_ok=True)
                create = jobs.create_local_livery_preview

                def create_then_change(*args, **kwargs):
                    manifest = create(*args, **kwargs)
                    self._change_input(name)
                    return manifest

                with patch.object(jobs, "create_local_livery_preview", side_effect=create_then_change):
                    preview = self._preview()
                with self.assertRaisesRegex(ValueError, "local livery changed"):
                    self._verify_high_quality_provider(preview)

    def test_preview_without_game_folder_does_not_require_an_index(self):
        self.payload["game_folder"] = ""
        with patch.object(jobs, "load_or_build_vehicle_asset_index") as load:
            first = self._preview()
            repeated = self._preview()
        load.assert_not_called()
        self.assertFalse(self.paths.vehicle_index.exists())
        self.assertTrue(repeated["cache_hit"])
        self.assertEqual(first["path"], repeated["path"])


if __name__ == "__main__":
    unittest.main()
