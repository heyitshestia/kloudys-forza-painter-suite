"""Portable receipt and Studio lifecycle regressions; no game/private fixtures."""
from __future__ import annotations

from contextlib import ExitStack
import copy
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/livery-studio/src"), str(ROOT)]

from PIL import Image
from kfps_livery_lab import car_workspace as cars
from kfps_livery_lab import prepare


class PreparationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in ("mesh", "render", "internal"):
            (self.root / name).mkdir()
        (self.root / "mesh/vehicle.glb").write_bytes(b"synthetic mesh; validator result supplied below")
        (self.root / "component-coverage.json").write_text("{}", encoding="utf-8")
        (self.root / "internal/blank-sections.zip").write_bytes(b"synthetic internal input")
        (self.root / "render/index.json").write_text("{}", encoding="utf-8")
        self.images = ["render/paint.png", *[f"render/mask-{i}.png" for i in range(3)]]
        for name in self.images:
            Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(self.root / name)
        self.validation = {"valid": True, "mesh_count": 1}
        self.prepared = {
            "format": prepare.PREPARE_FORMAT, "validation": self.validation,
            "files": {"mesh": "mesh/vehicle.glb", "coverage": "component-coverage.json",
                      "paint": self.images[0], "masks": self.images[1:], "native_textures": {}},
            "file_sha256": {name: prepare.file_hash(self.root / name) for name in
                            ["mesh/vehicle.glb", "component-coverage.json", *self.images]},
        }
        self.dependencies = {"code": "v1", "source": "source-hash", "materials": "material-hash"}
        prepare.atomic_json(self.root / "prepared.json", self.prepared)
        prepare._write_receipt(self.root, self.dependencies)

    def matches(self, *, dependencies=None, validation=None, cancel_event=None):
        return prepare._receipt_matches(
            self.root, self.prepared,
            self.dependencies if dependencies is None else dependencies,
            self.validation if validation is None else validation, cancel_event)

    def test_receipt_roundtrip_revalidates_all_artifacts_without_changing_output(self):
        before = (self.root / "prepared.json").read_bytes()
        with patch.object(prepare, "_validate_prepared_files", wraps=prepare._validate_prepared_files) as verify:
            stamps = self.matches()
        verify.assert_called_once()
        self.assertEqual(set(self.prepared["file_sha256"]) |
                         {"internal/blank-sections.zip", "render/index.json"}, set(stamps))
        self.assertEqual(before, (self.root / "prepared.json").read_bytes())

    def test_dependency_or_current_mesh_validation_change_invalidates_receipt(self):
        self.assertIsNone(self.matches(dependencies={**self.dependencies, "code": "v2"}))
        self.assertIsNone(self.matches(validation={"valid": True, "mesh_count": 2}))

    def test_changed_prepared_metadata_invalidates_receipt(self):
        prepare.atomic_json(self.root / "prepared.json", {**self.prepared, "extra": "changed"})
        self.assertIsNone(self.matches())

    def test_missing_or_corrupt_artifact_invalidates_receipt(self):
        for name in (*self.prepared["file_sha256"], "internal/blank-sections.zip", "render/index.json"):
            path = self.root / name
            before = path.read_bytes()
            with self.subTest(name=name, failure="missing"):
                path.unlink()
                self.assertIsNone(self.matches())
            with self.subTest(name=name, failure="corrupt"):
                path.write_bytes(b"corrupt")
                self.assertIsNone(self.matches())
            path.write_bytes(before)

    def test_invalid_png_is_rejected_even_with_matching_fingerprint(self):
        path = self.root / self.images[0]
        path.write_bytes(b"not a PNG")
        self.prepared["file_sha256"][self.images[0]] = prepare.file_hash(path)
        prepare.atomic_json(self.root / "prepared.json", self.prepared)
        prepare._write_receipt(self.root, self.dependencies)
        self.assertIsNone(self.matches())

    def test_missing_malformed_duplicate_nonfinite_and_oversized_receipt_are_misses(self):
        receipt = self.root / "preparation-receipt.json"
        receipt.unlink()
        self.assertIsNone(self.matches())
        for body in (b"{bad", b"[]", b'{"format":1,"format":2}', b'{"x":NaN}', b" " * 65537):
            with self.subTest(body=body[:40]):
                receipt.write_bytes(body)
                self.assertIsNone(self.matches())

    def test_image_inventory_rejects_traversal_aliases_and_missing_hashes(self):
        for name in ("../outside.png", "C:/outside.png", "render\\paint.png", "render/./paint.png", ""):
            with self.subTest(name=name):
                value = copy.deepcopy(self.prepared)
                value["files"]["paint"] = name
                with self.assertRaises(ValueError):
                    prepare._prepared_images(value)
        value = copy.deepcopy(self.prepared)
        value["files"]["masks"][0] = value["files"]["paint"]
        with self.assertRaises(ValueError):
            prepare._prepared_images(value)
        value = copy.deepcopy(self.prepared)
        value["file_sha256"].pop("mesh/vehicle.glb")
        with self.assertRaises(ValueError):
            prepare._prepared_images(value)

    def test_cancellation_is_propagated_not_treated_as_a_cache_miss(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            self.matches(cancel_event=cancel)
        with patch.object(prepare, "workspace_environment") as workspace, self.assertRaises(InterruptedError):
            prepare.prepare_car(self.root, self.root, "CAR.zip", self.root, cancel_event=cancel)
        workspace.assert_not_called()

    def test_output_hardlinks_are_rejected(self):
        path = self.root / self.images[0]
        try:
            os.link(path, self.root / "paint-alias.png")
        except OSError as exc:
            self.skipTest(f"Hardlinks unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "linked"):
            prepare._check_output_paths(self.root)
        self.assertIsNone(self.matches())

    def test_output_symlinks_are_rejected(self):
        path = self.root / self.images[0]
        target = self.root / "original.png"
        path.rename(target)
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "redirected"):
            prepare._check_output_paths(self.root)
        self.assertIsNone(self.matches())

    def test_readonly_source_hardlink_reaches_normal_identity_and_hash_checks(self):
        from tools.livery import vehicle_assets

        game = self.root / "game"
        source = game / "media/Cars/CAR.zip"
        source.parent.mkdir(parents=True)
        original = self.root / "source.zip"
        original.write_bytes(b"synthetic read-only source")
        try:
            os.link(original, source)
        except OSError as exc:
            self.skipTest(f"Hardlinks unavailable: {exc}")
        output = self.root / "output"
        output.mkdir()
        with patch.object(prepare, "workspace_environment", return_value=output), \
                patch.object(prepare, "load_baseline", return_value=ROOT), \
                patch.object(vehicle_assets, "_car_clip_in_archive", return_value=(1, "car.clipd")) as identity, \
                patch.object(prepare, "file_hash", wraps=prepare.file_hash) as hashes, \
                patch.object(prepare, "lab_converter", side_effect=RuntimeError("converter boundary")), \
                self.assertRaisesRegex(RuntimeError, "converter boundary"):
            prepare.prepare_car(ROOT, game, source.name, output)
        identity.assert_called_once_with(source)
        hashes.assert_any_call(source)
        self.assertEqual(b"synthetic read-only source", original.read_bytes())


class StudioSessionReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.lab = self.base / "lab"
        self.session = self.lab / "runs/session"
        self.session.mkdir(parents=True)
        self.stack = self.enterContext(ExitStack())
        self.rows = {f"{i:032x}": {"id": f"{i:032x}", "archive": f"CAR_{i}.zip", "car_id": i,
                                  "name": f"Car {i}", "model_code": f"CAR_{i}",
                                  "_path": self.base / f"CAR_{i}.zip", "_size": 1, "_mtime": 1}
                     for i in range(1, 6)}
        self.stack.enter_context(patch.object(cars, "LAB_ROOT", self.lab))
        self.stack.enter_context(patch.object(cars, "catalogue", return_value=self.rows))
        self.calls = []
        self.failure = False

        def worker(record):
            self.calls.append(record["root"])
            if self.failure:
                (record["root"] / "identity.txt").write_text("partial", encoding="utf-8")
                raise ValueError("verification failed")
            (record["root"] / "identity.txt").write_text(record["car"]["id"], encoding="utf-8")
            return {"identity": record["car"]["id"]}, {}

        self.worker = self.stack.enter_context(patch.object(cars.CarWorkspace, "_prepare", side_effect=worker))
        self.validate = self.stack.enter_context(patch.object(
            cars, "validate_prepared", side_effect=lambda root, car: ({"identity": car["id"]}, {})))
        self.manager = cars.CarWorkspace(self.session, self.base, self.base)
        self.addCleanup(self.manager.close)
        self.current = "INITIAL.zip"

    def start(self, index):
        identifier = self.manager.start(f"{index:032x}", self.current)["id"]
        thread = self.manager.records[identifier]["thread"]
        thread.join(3)
        self.assertFalse(thread.is_alive())
        return identifier

    def switch(self, index):
        identifier = self.start(index)
        self.assertEqual("ready", self.manager.poll(identifier)["status"])
        self.manager.commit(identifier, lambda *args: "local-session")
        self.current = self.rows[f"{index:032x}"]["archive"]
        return identifier

    def reject_commit(self, identifier):
        with self.assertRaises(cars.CarError):
            self.manager.commit(identifier, lambda *args: self.fail("stale job committed"))

    def test_a_b_a_reuses_only_inactive_root_with_new_job_and_worker(self):
        first = self.switch(1)
        root_a = self.manager.active_root
        second = self.switch(2)
        root_b = self.manager.active_root
        third = self.switch(1)
        self.assertEqual(3, len({first, second, third}))
        self.assertEqual(root_a, self.manager.active_root)
        self.assertEqual([root_a, root_b, root_a], self.calls)
        self.assertEqual(2, len(self.manager.owned))
        self.assertEqual(3, self.validate.call_count)
        self.reject_commit(first)
        self.assertEqual(f"{2:032x}", (root_b / "identity.txt").read_text())

    def test_missing_owned_root_is_ledger_only_miss_then_fresh_allocation(self):
        first = self.switch(1)
        missing = self.manager.active_root
        self.switch(2)
        self.assertTrue(missing.resolve().is_relative_to(self.session.resolve()))
        shutil.rmtree(missing)
        with patch.object(cars.shutil, "rmtree", side_effect=AssertionError("no filesystem cleanup for missing root")):
            self.switch(1)
        self.assertNotEqual(missing, self.manager.active_root)
        self.assertNotIn(missing, self.manager.owned)
        self.assertFalse(missing.exists())
        self.reject_commit(first)

    def test_missing_root_can_be_evicted_at_capacity(self):
        self.switch(1)
        missing = self.manager.active_root
        self.switch(2)
        self.switch(3)
        self.assertTrue(missing.resolve().is_relative_to(self.session.resolve()))
        shutil.rmtree(missing)
        self.switch(4)
        self.assertNotIn(missing, self.manager.owned)
        self.assertEqual(cars.MAX_WORKSPACES, len(self.manager.owned))

    def test_active_root_is_not_a_reuse_candidate(self):
        self.switch(1)
        active = self.manager.active_root
        self.current = "stale-current.zip"
        pending = self.start(1)
        self.assertNotEqual(active, self.manager.records[pending]["root"])
        self.assertEqual(active, self.manager.active_root)
        self.manager.cancel(pending)

    def test_unfamiliar_persisted_directory_is_never_adopted(self):
        old = self.manager.root / ("a" * 32)
        old.mkdir(parents=True)
        (old / "prepared.json").write_text("{}", encoding="utf-8")
        self.switch(1)
        self.assertNotEqual(old, self.manager.active_root)
        self.assertNotIn(old, self.manager.owned)
        self.assertTrue(old.exists())

    def test_failed_reuse_requires_new_worker_and_does_not_revive_old_job(self):
        first = self.switch(1)
        root = self.manager.active_root
        self.switch(2)
        active = self.manager.active_root
        self.failure = True
        failed = self.start(1)
        self.assertEqual(root, self.manager.records[failed]["root"])
        self.assertEqual("failed", self.manager.poll(failed)["status"])
        self.assertEqual(active, self.manager.active_root)
        self.reject_commit(first)
        self.reject_commit(failed)
        self.failure = False
        again = self.switch(1)
        self.assertEqual(3, len({first, failed, again}))
        self.assertEqual(root, self.manager.active_root)
        self.assertEqual(4, len(self.calls))
        self.assertEqual(f"{1:032x}", (root / "identity.txt").read_text())
        self.assertEqual("failed", self.manager.poll(failed)["status"])

    def test_preparing_or_ready_reuse_blocks_start_despite_old_committed_record(self):
        self.switch(1)
        self.switch(2)
        entered, release = threading.Event(), threading.Event()
        original = self.worker.side_effect

        def blocked(record):
            entered.set()
            if not release.wait(3):
                raise AssertionError("test worker timed out")
            return original(record)

        self.worker.side_effect = blocked
        identifier = self.manager.start(f"{1:032x}", self.current)["id"]
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaises(cars.CarError):
                self.manager.start(f"{1:032x}", self.current)
        finally:
            release.set()
            self.manager.records[identifier]["thread"].join(3)
        self.assertEqual("ready", self.manager.poll(identifier)["status"])
        with self.assertRaises(cars.CarError):
            self.manager.start(f"{1:032x}", self.current)
        self.manager.cancel(identifier)

    def test_cancelled_ready_root_revalidates_with_new_id(self):
        cancelled = self.start(1)
        root = self.manager.records[cancelled]["root"]
        self.manager.cancel(cancelled)
        current = self.switch(1)
        self.assertEqual(root, self.manager.active_root)
        self.assertNotEqual(cancelled, current)
        self.assertEqual(2, len(self.calls))
        self.reject_commit(cancelled)

    def test_redirected_missing_root_is_rejected_not_treated_as_a_miss(self):
        self.switch(1)
        root = self.manager.active_root
        self.switch(2)
        self.assertTrue(root.resolve().is_relative_to(self.session.resolve()))
        shutil.rmtree(root)
        try:
            root.symlink_to(self.base / "missing-target", target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlinks unavailable: {exc}")
        self.addCleanup(root.unlink)
        calls = len(self.calls)
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.manager.start(f"{1:032x}", self.current)
        self.assertEqual(calls, len(self.calls))
        self.assertIn(root, self.manager.owned)

    def test_commit_revalidates_reused_root_before_activation(self):
        self.switch(1)
        self.switch(2)
        active = self.manager.active_root
        pending = self.start(1)
        self.validate.side_effect = ValueError("changed artifact")
        with self.assertRaisesRegex(ValueError, "changed artifact"):
            self.manager.commit(pending, lambda *args: self.fail("invalid output activated"))
        self.assertEqual(active, self.manager.active_root)
        self.manager.cancel(pending)

    def test_workspace_and_record_caps_survive_repeated_reuse(self):
        identifiers = [self.switch(index % 2 + 1) for index in range(cars.MAX_RECORDS + 2)]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(2, len(self.manager.owned))
        self.assertLessEqual(len(self.manager.records), cars.MAX_RECORDS)
        self.switch(3)
        active = self.manager.active_root
        self.switch(4)
        self.assertEqual(cars.MAX_WORKSPACES, len(self.manager.owned))
        self.assertTrue(active.exists())


if __name__ == "__main__":
    unittest.main()
