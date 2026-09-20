"""Saved-livery imports against isolated, account-verified FH6 save trees."""
from __future__ import annotations

import hashlib
import concurrent.futures
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/src")]

from tools.cgroup.fh6_identity import build_vinyl_header, read_account
from tools.cgroup.forza_source_decoder import clivery_to_layers, unwrap_forza_container
from tools.livery import fh6_save_installer as installer
from tools.livery.package import create_full_livery_package
from test_full_livery_package import build_install_destination


USER_TAG = b"DEST0001"
NOW = datetime(2026, 9, 20, 12, 0, 0).astimezone()


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def save_account(root, *, evidence="vinyl", tag=USER_TAG):
    containers = build_install_destination(root, creator_tag=tag)
    folder = next(containers.glob("Livery_*"))
    if evidence == "base":
        raw = bytearray((folder / "header").read_bytes())
        date_offset = 12 + struct.unpack_from("<I", raw, 4)[0] * 2
        struct.pack_into("<I", raw, date_offset + 16, 4)
        (folder / "header").write_bytes(raw)
        folder.rename(folder.with_name(folder.name.replace("Livery_", "BaseLivery_", 1)))
    elif evidence != "livery":
        for p in folder.iterdir():
            p.unlink()
        folder.rmdir()
    if evidence == "vinyl":
        folder = containers / "LayerGroup_fixture"
        folder.mkdir()
        (folder / "header").write_bytes(build_vinyl_header(
            "Account name", int.from_bytes(tag, "little"), "Local Painter", 1, now=NOW))
    return read_account(containers.parent.parent)


def make_package(root, *, count=1200, car_id=3304):
    """Real decoder, package writer, validator, and renderer; no install mocks."""
    source = root / "source"
    source.mkdir(parents=True)
    payload = bytearray(0x40)
    payload[:4] = b"vlrc"
    struct.pack_into("<I", payload, 4, 1)
    struct.pack_into("<I", payload, 0x10, car_id)
    payload[0x1a:0x1e] = b"yrvl"
    struct.pack_into("<I", payload, 0x1e, 8)
    payload[0x22:0x2a] = b"SOURCE01"
    sections, counts = [], []
    for section in range(11):
        n = min(3000, max(0, count - section * 3000))
        counts.append(n)
        shapes = bytearray()
        for i in range(n):
            shape = bytearray(32)
            shape[:2] = b"\x00\x02"
            struct.pack_into("<H", shape, 2, 101 + i % 2)
            struct.pack_into("<fffff", shape, 4, i % 90,
                             (i % 60 - 30) * 10, (i // 60 - 25) * 10, .15, .15)
            shape[28:32] = bytes((i % 255, 140, 210, 128 if i % 3 == 0 else 255))
            shapes.extend(shape)
        sections.append(shapes + bytes(18 if n else 23))
    payload.extend(b"gyvl" + bytes(0x11) + b"".join(sections) + b"yrvl")
    payload.extend(struct.pack("<11I", *counts))
    (source / "C_livery").write_bytes(installer._wrap_payload(bytes(payload)))
    raw = bytearray(installer.build_destination_header(
        title="Shared test", car_id=car_id, placement_count=count,
        creator_tag=b"SOURCE01", creator_name="Source Creator", now=NOW))
    date_offset = 12 + struct.unpack_from("<I", raw, 4)[0] * 2
    # Simulate a working/base header with source metadata that must not leak.
    struct.pack_into("<I", raw, date_offset + 16, 4)
    prefix_offset = date_offset + 32 + len("Source Creator".encode("utf-16le"))
    raw[prefix_offset:prefix_offset + 28] = b"\x01" + bytes(11) + bytes(range(16))
    raw.extend(b"source-only-metadata")
    (source / "header").write_bytes(raw)
    package = root / "shared.kfpslivery"
    create_full_livery_package(source / "C_livery", package, model_code_override="TEST_CAR")
    return package


class FH6LiveryIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts = tempfile.TemporaryDirectory()
        cls.package = make_package(Path(cls.artifacts.name))

    @classmethod
    def tearDownClass(cls):
        cls.artifacts.cleanup()

    def install(self, root, account, **kwargs):
        return installer.install_full_livery_package(
            self.package, scan_roots=[root], destination=account.containers,
            backup_root=root / "backups", expected_model_code="TEST_CAR", now=NOW, **kwargs)

    def test_first_livery_from_vinyl_only_account_and_repeated_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            before = snapshot(account.containers)
            source = unwrap_forza_container(Path(self.artifacts.name) / "source/C_livery")
            first = self.install(root, account)
            second = self.install(root, account)
            self.assertNotEqual(first.installed_folder, second.installed_folder)
            guids = set()
            for result in (first, second):
                header = installer.parse_fh6_header((result.installed_folder / "header").read_bytes())
                self.assertEqual("Local Painter", header.creator_name)
                self.assertEqual(USER_TAG, header.creator_tag)
                self.assertEqual("saved", header.record_kind)
                self.assertFalse(header.description or any(header.section_prefix) or header.trailing)
                guids.add(header.asset_guid)
                actual = unwrap_forza_container(result.installed_folder / "C_livery")
                self.assertEqual(clivery_to_layers(source), clivery_to_layers(actual))
                self.assertEqual(1200, len(clivery_to_layers(actual)[0]))
                self.assertEqual(USER_TAG, actual[0x22:0x2a])
                self.assertTrue(result.thumbnail_written)
            self.assertEqual(2, len(guids))
            after = snapshot(account.containers)
            self.assertEqual(before, {k: after[k] for k in before})

    def test_base_only_account_can_install_without_a_saved_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root, evidence="base")
            self.assertFalse(list(account.containers.glob("Livery_*")))
            result = self.install(root, account)
            header = installer.parse_fh6_header((result.installed_folder / "header").read_bytes())
            self.assertEqual("Destination", header.creator_name)
            self.assertEqual("saved", header.record_kind)

    def test_description_does_not_classify_publication(self):
        raw = installer.build_destination_header(title="A", car_id=1, placement_count=1,
            creator_tag=USER_TAG, creator_name="Creator", now=NOW)
        offset = 10
        described = raw[:offset] + struct.pack("<I", 1) + "B".encode("utf-16le") + raw[offset + 4:]
        parsed = installer.parse_fh6_header(described)
        self.assertEqual("B", parsed.description)
        self.assertEqual("saved", parsed.record_kind)
        self.assertFalse(hasattr(parsed, "published"))

    def test_unicode_header_counts_utf16_units_and_never_splits_surrogates(self):
        header = installer.parse_fh6_header(installer.build_destination_header(
            title="x" * 63 + "\U0001f680", creator_name="\ud55c\uae00 \U0001f680",
            creator_tag=USER_TAG, car_id=1, placement_count=1, now=NOW))
        self.assertEqual("x" * 63, header.title)
        self.assertEqual("\ud55c\uae00 \U0001f680", header.creator_name)

    def test_invalid_creator_or_guid_never_produces_a_header(self):
        for override in ({"creator_tag": bytes(8)}, {"creator_name": "KFPS"},
                         {"creator_name": ""}, {"creator_name": "A\x00B"},
                         {"asset_guid": bytes(16)}, {"car_id": 0}, {"placement_count": 0}):
            args = dict(title="A", car_id=1, placement_count=1, creator_tag=USER_TAG,
                        creator_name="Creator", now=NOW)
            args.update(override)
            with self.subTest(override=override), self.assertRaises(installer.FullLiveryInstallError):
                installer.build_destination_header(**args)

    def test_unknown_header_version_is_rejected(self):
        raw = installer.build_destination_header(title="A", car_id=1, placement_count=1,
            creator_tag=USER_TAG, creator_name="Creator", now=NOW)
        with self.assertRaisesRegex(installer.FullLiveryInstallError, "version"):
            installer.parse_fh6_header(struct.pack("<I", 99) + raw[4:])

    def test_no_name_evidence_fails_without_inventing_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root, evidence="none")
            before = snapshot(account.containers)
            with self.assertRaisesRegex(installer.FullLiveryInstallError, "creator name"):
                self.install(root, account)
            self.assertEqual(before, snapshot(account.containers))
            self.assertFalse((root / "backups").exists())

    def test_foreign_or_mismatched_livery_is_not_name_evidence(self):
        for mismatch in ("header", "payload", "protected"):
            with tempfile.TemporaryDirectory() as tmp, self.subTest(mismatch=mismatch):
                root = Path(tmp)
                account = save_account(root, evidence="livery")
                folder = next(account.containers.glob("Livery_*"))
                if mismatch == "header":
                    (folder / "header").write_bytes(installer.build_destination_header(
                        title="Foreign", car_id=3304, placement_count=1,
                        creator_tag=b"FOREIGN1", creator_name="Friend", now=NOW))
                else:
                    payload = bytearray(unwrap_forza_container(folder / "C_livery"))
                    if mismatch == "payload":
                        payload[0x22:0x2a] = b"FOREIGN1"
                    else:
                        struct.pack_into("<I", payload, 8, 1)
                    (folder / "C_livery").write_bytes(installer._wrap_payload(payload))
                with self.assertRaisesRegex(installer.FullLiveryInstallError, "creator name"):
                    installer.select_destination_identity([], destination=account.containers)

    def test_conflicting_vinyl_names_do_not_fall_back_to_a_livery(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = save_account(Path(tmp), evidence="livery")
            for i, name in enumerate(("Name A", "Name B")):
                folder = account.containers / f"LayerGroup_{i}"
                folder.mkdir()
                (folder / "header").write_bytes(build_vinyl_header(
                    "A", account.user_id, name, 1, now=NOW))
            with self.assertRaisesRegex(installer.FullLiveryInstallError, "Conflicting"):
                installer.select_destination_identity([], destination=account.containers)

    def test_explicit_destination_overrides_other_accounts_and_system_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = save_account(root / "first")
            other = save_account(root / "other", tag=b"OTHER001")
            local = root / "local"
            pointer = local / "ForzaHorizon6" / f"SaveFolderMetadata_{other.user_id:x}" / "LastSaveFolderLocation"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(str(other.containers), encoding="utf-8")
            for destination in (first.containers, first.directory, root / "first"):
                identity = installer.select_destination_identity([other.directory],
                    destination=destination, local_app_data=local)
                self.assertEqual(first.containers, identity.containers_root)

    def test_steam_and_windows_save_pointers_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            local = root / "local"
            for base in (local / "ForzaHorizon6", local / "Packages" /
                         "Microsoft.ForteBaseGame_8wekyb3d8bbwe/LocalCache/Local"):
                pointer = base / f"SaveFolderMetadata_{account.user_id:x}" / "LastSaveFolderLocation"
                pointer.parent.mkdir(parents=True)
                pointer.write_text(str(account.containers), encoding="utf-8")
                identity = installer.select_destination_identity([], local_app_data=local)
                self.assertEqual(account.containers, identity.containers_root)

    def test_stale_or_missing_explicit_selection_does_not_redirect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            stale = account.directory / "6/ContainersRoot"
            stale.mkdir(parents=True)
            for path in (stale, root / "missing"):
                with self.subTest(path=path), self.assertRaises(installer.FullLiveryInstallError):
                    installer.select_destination_identity([root], destination=path)

    def test_manifest_disagreement_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            path = account.directory / "7.json"
            content = json.loads(path.read_bytes())
            content["Manifest"]["UserId"] = "100"
            path.write_text(json.dumps(content), encoding="utf-8")
            with self.assertRaisesRegex(installer.FullLiveryInstallError, "disagree"):
                installer.select_destination_identity([], destination=account.containers)

    def test_changed_account_manifest_aborts_staged_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            before = snapshot(account.containers)
            real_write = installer._write_exclusive

            def changing_write(path, data):
                real_write(path, data)
                if path.name == "header" and path.parent.name.endswith(".tmp"):
                    (account.directory / "7.json").write_bytes(account.manifest + b" ")

            with patch.object(installer, "_write_exclusive", side_effect=changing_write):
                with self.assertRaises(installer.FullLiveryConcurrentChangeError):
                    self.install(root, account)
            self.assertEqual(before, snapshot(account.containers))
            self.assertFalse(any(p.name.endswith(".tmp") for p in account.containers.iterdir()))

    def test_changed_livery_identity_evidence_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            account = save_account(Path(tmp), evidence="base")
            identity = installer.select_destination_identity([], destination=account.containers)
            identity.livery_evidence.write_bytes(b"changed")
            with self.assertRaises(installer.FullLiveryConcurrentChangeError):
                identity.revalidate()

    def test_cancel_during_staging_removes_partial_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            before = snapshot(account.containers)
            cancelled = threading.Event()
            real_write = installer._write_exclusive

            def cancelling_write(path, data):
                real_write(path, data)
                if path.parent.name.endswith(".tmp"):
                    cancelled.set()

            with patch.object(installer, "_write_exclusive", side_effect=cancelling_write):
                with self.assertRaises(concurrent.futures.CancelledError):
                    self.install(root, account, cancel_event=cancelled)
            self.assertEqual(before, snapshot(account.containers))
            self.assertFalse(any(p.name.endswith(".tmp") for p in account.containers.iterdir()))

    def test_auto_selected_account_switch_aborts_before_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = save_account(root / "first")
            other = save_account(root / "other", tag=b"OTHER001")
            local = root / "local"
            pointer = local / "ForzaHorizon6" / f"SaveFolderMetadata_{first.user_id:x}" / "LastSaveFolderLocation"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(str(first.containers), encoding="utf-8")
            before = snapshot(first.containers)
            real_write = installer._write_exclusive

            def switching_write(path, data):
                real_write(path, data)
                if path.name == "header" and path.parent.name.endswith(".tmp"):
                    pointer.unlink()
                    replacement = pointer.parent.parent / f"SaveFolderMetadata_{other.user_id:x}" / pointer.name
                    replacement.parent.mkdir()
                    replacement.write_text(str(other.containers), encoding="utf-8")

            with patch.object(installer, "_write_exclusive", side_effect=switching_write):
                with self.assertRaises(installer.FullLiveryConcurrentChangeError):
                    installer.install_full_livery_package(self.package, scan_roots=[root],
                        local_app_data=local, backup_root=root / "backups", expected_model_code="TEST_CAR")
            self.assertEqual(before, snapshot(first.containers))
            self.assertFalse(list(other.containers.glob("Livery_*")))

    def test_header_corruption_after_commit_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            before = snapshot(account.containers)
            real_replace = installer.os.replace

            def corrupting_replace(source, target):
                real_replace(source, target)
                header = Path(target) / "header"
                header.write_bytes(header.read_bytes() + b"unexpected")

            with patch.object(installer.os, "replace", side_effect=corrupting_replace):
                with self.assertRaisesRegex(installer.FullLiveryInstallError, "differs"):
                    self.install(root, account)
            self.assertEqual(before, snapshot(account.containers))

    def test_no_rewrite_of_protected_source_even_if_manifest_claims_shareable(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            before = snapshot(account.containers)
            with zipfile.ZipFile(self.package) as bundle:
                entries = {info.filename: bundle.read(info) for info in bundle.infolist()}
            manifest = json.loads(entries["manifest.json"])
            payload = bytearray(installer.unwrap_forza_container_bytes(entries["source/fh6/C_livery"], "fixture"))
            struct.pack_into("<I", payload, 8, 1)
            entries["source/fh6/C_livery"] = installer._wrap_payload(payload)
            package = root / "protected.kfpslivery"
            with zipfile.ZipFile(package, "w") as bundle:
                for name, data in entries.items():
                    bundle.writestr(name, data)
            with patch.object(installer, "validate_full_livery_package", return_value=manifest):
                with self.assertRaisesRegex(installer.FullLiveryInstallError, "not eligible"):
                    installer.install_full_livery_package(package, scan_roots=[root],
                        destination=account.containers, backup_root=root / "backups", expected_model_code="TEST_CAR")
            self.assertEqual(before, snapshot(account.containers))

    def test_worker_install_path_passes_selected_destination(self):
        from kfps_ui.experimental.full_livery import jobs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account = save_account(root)
            paths = SimpleNamespace(vehicle_index=root / "vehicle-index.json", recovery=root / "recovery")
            with patch.object(jobs, "load_or_build_vehicle_asset_index",
                              return_value={3304: SimpleNamespace(model_code="TEST_CAR")}):
                result = jobs.install_package(paths, {
                    "package": str(self.package), "save_root": str(account.containers),
                }, threading.Event())
            self.assertEqual(1200, result["placement_count"])
            self.assertEqual(account.containers, Path(result["installed_folder"]).parent)


if __name__ == "__main__":
    unittest.main()
