"""Synthetic-only FH5 WGS tests; all generated files stay in the dated run root."""
from __future__ import annotations

import concurrent.futures
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from tools.cgroup import fh5_offline as fh5
from tools.cgroup import xbox_wgs as wgs
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, wrap_payload

RUN_ROOT = ROOT / "runtime" / "offline-transfer-20261020" / "synthetic"
OWNER = int("000901F000000001", 16)
ASSET = uuid.UUID("22222222-3333-4444-8555-666666666666")


def header_bytes(count=1, owner=OWNER, creator="Fixture Owner", asset=ASSET, version=6):
    def text(value):
        data = value.encode("utf-16le")
        return struct.pack("<I", len(data) // 2) + data
    return (struct.pack("<I", version) + text("Fixture") + text("")
            + struct.pack("<8HIQ", 2026, 10, 2, 20, 12, 0, 0, 0, 2, owner)
            + text(creator) + bytes(28) + b"\x01\x02" + bytes(3)
            + struct.pack("<I", count) + asset.bytes_le)


def payload_bytes(count=2):
    return build_flat_payload([
        CGroupLayer(101, float(index), 2.0, 1.0, 1.0, 0.0, 0.0, (20, 80, 150, 255))
        for index in range(count)
    ])


def png_bytes():
    output = BytesIO()
    Image.new("RGBA", (256, 256), (20, 80, 150, 255)).save(output, "PNG")
    return output.getvalue()


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def fixture(root, owner=OWNER):
    slot = root / fh5.FH5_PACKAGE / "SystemAppData" / "wgs" / f"{owner:016X}_{'0' * 32}"
    folder_id = uuid.UUID("11111111-2222-4333-8444-555555555555")
    folder = slot / folder_id.hex.upper()
    folder.mkdir(parents=True)
    blobs = (("C_group", wrap_payload(payload_bytes(1))),
             ("header", header_bytes(owner=owner)), ("thumb.png", png_bytes()))
    entries = []
    for index, (name, data) in enumerate(blobs, start=10):
        file_id = uuid.UUID(int=index)
        (folder / file_id.hex.upper()).write_bytes(data)
        entries.append((name, file_id, file_id))
    descriptor = folder / "container.3"
    descriptor.write_bytes(wgs.serialize_wgs_file_list(3, entries))
    stamp = wgs.datetime_to_filetime(datetime(2026, 10, 20, tzinfo=timezone.utc))
    entry = wgs.WgsFolderEntry("LayerGroup_0000_fixture", "LayerGroup_0000_fixture", "cloud-revision",
                               3, 1, folder_id, stamp, 123, sum(len(data) for _, data in blobs))
    index = wgs.WgsIndex(14, 0, fh5.FH5_PACKAGE + "!Game", stamp, 0, "index-identity", 456, (entry,))
    (slot / "containers.index").write_bytes(wgs.serialize_wgs_index(index))
    (slot / "unrelated-profile.bin").write_bytes(b"unrelated account data")
    return slot, descriptor


@unittest.skipUnless(os.name == "nt", "WGS writing is Windows-only")
class FH5OfflineTransferTests(unittest.TestCase):
    def setUp(self):
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="fh5-", dir=RUN_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.slot, self.descriptor = fixture(self.root / "saves")
        self.target = fh5.inspect_fh5_wgs_target(self.descriptor)
        self.before = snapshot(self.slot)
        self.cancel = threading.Event()

    def install(self, target=None, **changes):
        target = target or self.target
        args = dict(payload=payload_bytes(), header_data=fh5.build_fh5_vinyl_header(target, "Imported", 2),
                    thumbnail_data=png_bytes(), expected_layers=2, backup_root=self.root / "backups",
                    check_ready=lambda: None, cancel_event=self.cancel)
        args.update(changes)
        return fh5.create_fh5_wgs_layer_group(target, **args)

    def assert_original(self):
        self.assertEqual(self.before, snapshot(self.slot))

    def test_additive_import_preserves_originals_and_full_verified_backup(self):
        result = self.install()
        self.assertEqual(self.before, snapshot(result.backup_path))
        for path, data in self.before.items():
            if path != "containers.index":
                self.assertEqual(data, (self.slot / path).read_bytes())
        index = wgs.read_wgs_index(self.slot)
        self.assertEqual(2, len(index.folders))
        self.assertEqual(self.target.group.folder, index.folders[0])
        self.assertEqual("cloud-revision", index.folders[0].cloud_id)
        self.assertEqual(456, index.unknown)
        header = fh5.parse_fh5_vinyl_header(result.header_path.read_bytes())
        self.assertEqual((6, OWNER, "Fixture Owner", 2),
                         (header.version, header.creator_id, header.creator, header.layer_count))
        self.assertNotEqual(ASSET, header.asset_id)
        self.assertFalse(list(self.slot.glob("*.tmp")))

    def test_header_unicode_uses_utf16_units_and_fresh_guid(self):
        title = "Test \U0001f680"
        header = fh5.parse_fh5_vinyl_header(fh5.build_fh5_vinyl_header(self.target, title, 2))
        self.assertEqual(title, header.title)
        self.assertNotEqual(ASSET, header.asset_id)
        index = wgs.read_wgs_index(self.slot)
        from dataclasses import replace
        value = replace(index, index_guid=title)
        self.assertEqual(value, wgs.parse_wgs_index_bytes(wgs.serialize_wgs_index(value)))

    def test_3000_layers_and_terminal_mask_reopen(self):
        layers = [CGroupLayer(101, float(index % 100), float(index // 100), 1.0, 1.0,
                              0.0, 0.0, (255, 255, 255, 255), mask=(index == 2999))
                  for index in range(3000)]
        result = self.install(payload=build_flat_payload(layers), expected_layers=3000,
                              header_data=fh5.build_fh5_vinyl_header(self.target, "3000", 3000))
        decoded = fh5.decode_forza_source(result.cgroup_path, game="fh5")
        self.assertEqual(3000, len(decoded.layers))
        self.assertTrue(decoded.layers[-1]["mask"])

    def test_v4_donor_header_is_readable_but_new_header_must_be_v6(self):
        self.assertEqual(4, fh5.parse_fh5_vinyl_header(header_bytes(version=4)).version)
        with self.assertRaises(wgs.WgsFormatError):
            self.install(header_data=header_bytes(count=2, version=4, asset=uuid.uuid4()))
        self.assert_original()

    def test_shared_encoder_nested_groups_and_zero_alpha_mask_reopen(self):
        import json
        from tools.cgroup.vinyl_document import encode_vinyl_json

        shapes = [
            {"type": 0x100000 + 101, "data": [index, 2, 1, 1, 0, 0, int(index == 1)],
             "color": [20, 80, 150, 0 if index == 1 else 255],
             "editor_group_path": [{"id": "outer", "name": "Outer"},
                                   {"id": "inner", "name": "Inner"}]}
            for index in range(2)
        ]
        source = self.root / "nested.json"
        source.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
        payload, report = encode_vinyl_json(source, "fh5")
        self.assertGreaterEqual(report["groups"], 2)
        result = self.install(payload=payload, expected_layers=report["layers"],
                              header_data=fh5.build_fh5_vinyl_header(self.target, "Nested", report["layers"]))
        decoded = fh5.decode_forza_source(result.cgroup_path, game="fh5")
        self.assertEqual(2, len(decoded.layers))
        self.assertTrue(decoded.layers[-1]["mask"])
        self.assertEqual(0, decoded.layers[-1]["color"][3])

    def test_header_owner_count_guid_and_version_fail_closed(self):
        bad_headers = [header_bytes(count=2, owner=OWNER + 1, asset=uuid.uuid4()),
                       header_bytes(count=1, asset=uuid.uuid4()), header_bytes(count=2),
                       header_bytes(count=2, creator="Other Owner", asset=uuid.uuid4()),
                       header_bytes(count=2, version=7, asset=uuid.uuid4())]
        for header in bad_headers:
            with self.subTest(header=header[:4]), self.assertRaises(wgs.WgsFormatError):
                self.install(header_data=header)
            self.assert_original()

    def test_invalid_payload_and_thumbnail_never_write(self):
        for args in ({"expected_layers": 3}, {"payload": payload_bytes()[:-8]},
                     {"thumbnail_data": b"not PNG"}, {"payload": payload_bytes(0)}):
            with self.subTest(args=list(args)), self.assertRaises(Exception):
                self.install(**args)
            self.assert_original()

    def test_explicit_second_account_never_falls_back(self):
        slot, descriptor = fixture(self.root / "other", OWNER + 1)
        target = fh5.inspect_fh5_wgs_target(descriptor)
        result = self.install(target)
        self.assertEqual(slot, result.slot_path)
        self.assertEqual(OWNER + 1, fh5.parse_fh5_vinyl_header(result.header_path.read_bytes()).creator_id)
        self.assert_original()

    def test_steam_layout_and_unregistered_descriptor_are_rejected(self):
        steam = self.root / "Steam" / "userdata" / "1551360" / "remote"
        shutil.copytree(self.descriptor.parent, steam)
        with self.assertRaisesRegex(wgs.WgsFormatError, "Steam"):
            fh5.inspect_fh5_wgs_target(steam / self.descriptor.name)
        stale = self.descriptor.with_name("container.4")
        stale.write_bytes(self.descriptor.read_bytes())
        with self.assertRaises(wgs.WgsFormatError):
            fh5.inspect_fh5_wgs_target(stale)

    def test_template_wrong_owner_or_count_is_rejected(self):
        for header in (header_bytes(owner=OWNER + 1), header_bytes(count=2)):
            self.target.group.header_path.write_bytes(header)
            with self.assertRaises(wgs.WgsFormatError):
                fh5.inspect_fh5_wgs_target(self.descriptor)

    def test_distinct_guid_pair_and_duplicate_logical_names_are_rejected(self):
        entries = [(item.name, item.primary_guid, item.secondary_guid) for item in self.target.group.file_list.entries]
        unequal = list(entries)
        unequal[0] = (entries[0][0], entries[0][1], uuid.uuid4())
        self.descriptor.write_bytes(wgs.serialize_wgs_file_list(3, unequal))
        with self.assertRaises(wgs.WgsFormatError):
            fh5.inspect_fh5_wgs_target(self.descriptor)
        self.descriptor.write_bytes(wgs.serialize_wgs_file_list(3, entries + [entries[0]]))
        with self.assertRaises(wgs.WgsFormatError):
            fh5.inspect_fh5_wgs_target(self.descriptor)

    def test_changed_selection_and_unready_game_abort(self):
        def unready():
            raise ValueError("Close FH5")
        with self.assertRaisesRegex(ValueError, "Close FH5"):
            self.install(check_ready=unready)
        self.assert_original()
        self.target.group.header_path.write_bytes(header_bytes(creator="Renamed"))
        changed = snapshot(self.slot)
        with self.assertRaises(wgs.WgsConcurrentChangeError):
            self.install()
        self.assertEqual(changed, snapshot(self.slot))

    def test_cancel_before_work_and_during_backup(self):
        self.cancel.set()
        with self.assertRaises(concurrent.futures.CancelledError):
            self.install()
        self.assert_original()
        self.cancel.clear()
        original = shutil.copy2
        def copy(source, destination):
            result = original(source, destination)
            self.cancel.set()
            return result
        with patch.object(wgs.shutil, "copy2", side_effect=copy), self.assertRaises(concurrent.futures.CancelledError):
            self.install()
        self.assert_original()

    def test_cancel_after_staging_removes_only_staging(self):
        original = wgs._write_bytes_fsync
        def write(path, data):
            original(path, data)
            if path.name.startswith("container."):
                self.cancel.set()
        with patch.object(wgs, "_write_bytes_fsync", side_effect=write), self.assertRaises(concurrent.futures.CancelledError):
            self.install()
        self.assert_original()

    def test_late_cancel_returns_committed_result_not_cancelled(self):
        original = wgs._replace_bytes_fsync
        def commit(path, data):
            original(path, data)
            self.cancel.set()
        with patch.object(wgs, "_replace_bytes_fsync", side_effect=commit):
            result = self.install()
        self.assertTrue(result.cgroup_path.is_file())
        self.assertEqual(2, len(wgs.read_wgs_index(self.slot).folders))

    def test_backup_corruption_prevents_any_save_write(self):
        original = shutil.copy2
        def copy(source, destination):
            result = original(source, destination)
            if Path(source).name == "unrelated-profile.bin":
                Path(destination).write_bytes(b"corrupt backup")
            return result
        with patch.object(wgs.shutil, "copy2", side_effect=copy), self.assertRaisesRegex(wgs.WgsFormatError, "backup"):
            self.install()
        self.assert_original()

    def test_external_change_during_backup_is_not_overwritten(self):
        original = shutil.copy2
        def copy(source, destination):
            result = original(source, destination)
            if Path(source).name == "unrelated-profile.bin":
                Path(source).write_bytes(b"external writer")
            return result
        with patch.object(wgs.shutil, "copy2", side_effect=copy), self.assertRaises(wgs.WgsConcurrentChangeError):
            self.install()
        self.assertEqual(self.before["containers.index"], (self.slot / "containers.index").read_bytes())
        self.assertEqual(b"external writer", (self.slot / "unrelated-profile.bin").read_bytes())

    def test_preflight_index_change_cannot_be_used_with_a_later_snapshot(self):
        original = wgs.parse_wgs_index_bytes
        mutated = False
        def parse(data, source="containers.index"):
            nonlocal mutated
            result = original(data, source)
            if not mutated:
                mutated = True
                (self.slot / "unrelated-profile.bin").write_bytes(b"changed at preflight")
            return result
        with patch.object(wgs, "parse_wgs_index_bytes", side_effect=parse), self.assertRaises(wgs.WgsConcurrentChangeError):
            wgs.create_wgs_layer_group(self.slot, self.target.group, cgroup_data=wrap_payload(payload_bytes()),
                header_data=header_bytes(), thumbnail_data=png_bytes(), backup_root=self.root / "backups")
        self.assertEqual(self.before["containers.index"], (self.slot / "containers.index").read_bytes())

    def test_os_lock_blocks_another_worker_and_releases(self):
        with wgs._slot_write_lock(self.slot.resolve()):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.install)
                with self.assertRaises(wgs.WgsConcurrentChangeError):
                    future.result(timeout=10)
        self.assert_original()
        self.install()

    def test_os_lock_blocks_a_separate_hidden_process(self):
        code = (
            "import sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\n"
            "from tools.cgroup.xbox_wgs import _slot_write_lock, WgsConcurrentChangeError\n"
            "try:\n    with _slot_write_lock(Path(sys.argv[2])):\n        sys.exit(2)\n"
            "except WgsConcurrentChangeError:\n    print('blocked')\n"
        )
        with wgs._slot_write_lock(self.slot.resolve()):
            result = subprocess.run(
                [sys.executable, "-B", "-c", code, str(ROOT), str(self.slot.resolve())],
                capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("blocked", result.stdout.strip())
        self.assert_original()

    def test_directory_collision_does_not_overwrite(self):
        original = os.rename
        collisions = []
        def rename(source, destination):
            destination.mkdir()
            (destination / "foreign.txt").write_bytes(b"keep")
            collisions.append(destination)
            original(source, destination)
        with patch.object(wgs.os, "rename", side_effect=rename), self.assertRaises(FileExistsError):
            self.install()
        self.assertEqual(b"keep", (collisions[0] / "foreign.txt").read_bytes())
        self.assertEqual(self.before["containers.index"], (self.slot / "containers.index").read_bytes())

    def fail_reopen(self, path, **kwargs):
        if path.parent != self.target.group.folder_path and ".kfps-" not in path.parent.name:
            raise wgs.WgsFormatError("forced post-commit verification failure")
        return self.original_decode(path, **kwargs)

    def test_commit_failure_and_post_commit_failure_restore_original(self):
        with patch.object(wgs, "_replace_bytes_fsync", side_effect=OSError("commit failed")), self.assertRaises(OSError):
            self.install()
        self.assert_original()
        self.original_decode = fh5.decode_forza_source
        with patch.object(fh5, "decode_forza_source", side_effect=self.fail_reopen), self.assertRaises(wgs.WgsFormatError):
            self.install()
        self.assert_original()

    def test_failed_rollback_keeps_referenced_container_and_backup(self):
        original = wgs._replace_bytes_fsync
        self.original_decode = fh5.decode_forza_source
        def replace(path, data):
            if data == self.before["containers.index"]:
                raise OSError("restore failed")
            original(path, data)
        with patch.object(wgs, "_replace_bytes_fsync", side_effect=replace), \
                patch.object(fh5, "decode_forza_source", side_effect=self.fail_reopen), \
                self.assertRaisesRegex(wgs.WgsRecoveryRequiredError, "Safety backup"):
            self.install()
        self.assertEqual(2, len(wgs.read_wgs_layer_groups(self.slot)))
        backups = list((self.root / "backups").iterdir())
        self.assertEqual(self.before, snapshot(backups[0]))

    def test_foreign_post_commit_index_is_never_rolled_back(self):
        self.original_decode = fh5.decode_forza_source
        def decode(path, **kwargs):
            if path.parent != self.target.group.folder_path and ".kfps-" not in path.parent.name:
                (self.slot / "containers.index").write_bytes(b"external index")
                raise wgs.WgsFormatError("external write")
            return self.original_decode(path, **kwargs)
        with patch.object(fh5, "decode_forza_source", side_effect=decode), self.assertRaises(wgs.WgsRecoveryRequiredError):
            self.install()
        self.assertEqual(b"external index", (self.slot / "containers.index").read_bytes())

    def test_backup_inside_slot_is_rejected(self):
        with self.assertRaises(wgs.WgsFormatError):
            self.install(backup_root=self.slot / "backup")
        self.assert_original()


if __name__ == "__main__":
    unittest.main()
