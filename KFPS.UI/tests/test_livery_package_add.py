from __future__ import annotations

import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT), str(UI / "tests")]

from test_full_livery_package import (
    build_package, livery_payload, raster_livery_payload, full_livery_job_paths, json_bytes,
    refresh_manifest_hashes, rewrite_package,
)
from kfps_ui.app_paths import AppPaths
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.log_service import LogService
from kfps_ui.experimental.full_livery import jobs
from tools.livery.package import (
    FullLiveryPackageError, create_full_livery_package,
    migrate_full_livery_package, validate_full_livery_package,
)


class LiveryPackageAddTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                              self.root / "runtime", Path(sys.executable))
        self.jobs = full_livery_job_paths(self.paths)
        self.cancel = threading.Event()
        source = self.root / "source" / "C_livery"
        source.parent.mkdir()
        source.write_bytes(raster_livery_payload(raster_id=2030))
        self.package = self.root / "received.kfpslivery"
        create_full_livery_package(source, self.package, model_code_override="TEST_CAR")

    def tearDown(self):
        self.temp.cleanup()

    def add(self, path=None):
        return jobs.add_package(self.jobs, {
            "selected": str(path or self.package), "game_folder": "C:/Other-FH6-Build",
        }, self.cancel)

    def test_received_preview_drift_does_not_block_add_index_or_repeat(self):
        with zipfile.ZipFile(self.package) as bundle:
            image = Image.open(io.BytesIO(bundle.read("projection/rendered/Front.png"))).convert("RGBA")
        image.putpixel((0, 0), (1, 2, 3, 255))
        data = io.BytesIO()
        image.save(data, format="PNG")
        original = self.package.read_bytes()
        with patch("tools.livery.package._render_livery_sections",
                   return_value=({"Front": data.getvalue()}, False, [2030])) as render:
            with self.assertRaisesRegex(FullLiveryPackageError, "does not match the preserved source"):
                validate_full_livery_package(self.package, verify_previews=True)
            render.reset_mock()
            first = self.add()
            again = self.add()
            same_folder = self.add(Path(first["path"]))
            indexed = jobs.refresh_packages(self.jobs, {}, self.cancel)
            reopened = jobs.refresh_packages(self.jobs, {}, self.cancel)
            migrated = self.root / "current-copy.kfpslivery"
            migrate_full_livery_package(self.package, migrated, game_folder="C:/Other-FH6-Build")
            render.assert_not_called()
        self.assertEqual(first["path"], again["path"])
        self.assertEqual(first["path"], same_folder["path"])
        self.assertEqual(1, len(indexed["rows"]))
        self.assertEqual(1, reopened["cache_hits"])
        self.assertEqual(0, indexed["rejected"])
        self.assertEqual(original, Path(first["path"]).read_bytes())
        self.assertEqual(original, migrated.read_bytes())
        self.assertEqual(original, self.package.read_bytes())

    def test_damaged_preview_still_fails_integrity_without_being_added(self):
        damaged = self.root / "damaged.kfpslivery"
        rewrite_package(self.package, damaged, lambda entries:
                        entries.__setitem__("projection/rendered/Front.png", b"broken"))
        with self.assertRaisesRegex(FullLiveryPackageError, "integrity check"):
            self.add(damaged)
        self.assertEqual([], list(self.jobs.package_root.iterdir()))

    def test_rehashed_layer_edits_still_fail_source_validation(self):
        forged = self.root / "forged.kfpslivery"
        def alter(entries):
            layers = json.loads(entries["livery/layers.json"])
            layers["layers"][0]["color"] = [1, 2, 3, 255]
            entries["livery/layers.json"] = json_bytes(layers)
            refresh_manifest_hashes(entries)
        rewrite_package(self.package, forged, alter)
        with self.assertRaisesRegex(FullLiveryPackageError, "does not match the preserved FH6 source"):
            self.add(forged)
        self.assertEqual([], list(self.jobs.package_root.iterdir()))

    def test_cancelled_add_leaves_no_copy(self):
        self.cancel.set()
        with self.assertRaises(InterruptedError):
            self.add()
        self.assertEqual([], list(self.jobs.package_root.iterdir()))

    def test_foreign_source_still_cannot_be_added(self):
        foreign = self.root / "foreign.kfpslivery"
        build_package(foreign, payload_override=livery_payload(foreign_group=True))
        with self.assertRaisesRegex(FullLiveryPackageError, "created by another player"):
            self.add(foreign)
        self.assertEqual([], list(self.jobs.package_root.iterdir()))

    def test_rehashed_unreadable_preview_still_cannot_be_added(self):
        damaged = self.root / "unreadable.kfpslivery"
        def alter(entries):
            entries["projection/rendered/Front.png"] = b"not a PNG"
            refresh_manifest_hashes(entries)
        rewrite_package(self.package, damaged, alter)
        with self.assertRaisesRegex(FullLiveryPackageError, "missing or unreadable"):
            self.add(damaged)
        self.assertEqual([], list(self.jobs.package_root.iterdir()))

    def test_add_error_survives_unrelated_status_until_retry(self):
        service = FullLiveryService(self.paths, LogService(), demo=True)
        try:
            service._apply_result({"kind": "add-package", "ok": False, "error": "Damaged package"})
            self.assertEqual("Package add failed", service.status)
            service._apply_result({"kind": "refresh-packages", "ok": True, "payload": {"rows": []}})
            self.assertEqual("Damaged package", service.packageAddError)
            with patch.object(service._tasks, "start", return_value=True):
                self.assertTrue(service.addPackage(str(self.package)))
            self.assertEqual("", service.packageAddError)
        finally:
            service.close()

    def test_file_picker_cancel_is_noop_and_selection_uses_add_path(self):
        service = FullLiveryService(self.paths, LogService(), demo=True)
        try:
            with patch("kfps_ui.full_livery_service.QFileDialog.getOpenFileName", return_value=("", "")), \
                    patch.object(service, "addPackage") as add:
                service.choosePackage()
                add.assert_not_called()
            with patch("kfps_ui.full_livery_service.QFileDialog.getOpenFileName",
                       return_value=(str(self.package), "")), patch.object(service, "addPackage") as add:
                service.choosePackage()
                add.assert_called_once_with(str(self.package))
            self.assertFalse(service.addPackage(str(self.root / "missing.kfpslivery")))
            self.assertTrue(service.packageAddError)
        finally:
            service.close()
