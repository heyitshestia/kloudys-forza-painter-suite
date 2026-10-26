"""Synthetic FH3 WGS acquisition, native service and no-save-write regressions."""
from __future__ import annotations

import json
import os
import struct
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import test_fh3_offline_files as legacy_tests
from test_fh3_offline_files import fixture_header, shape
from test_fh4_offline_transfer import build_wgs_fixture
from game_adapters import get_adapter
from game_adapters.discovery import discover_save_roots
from tools.cgroup.cgroup_codec import wrap_payload
from tools.cgroup.fh3_save_reader import discover_sources
from tools.cgroup.fh3_files import read_vinyl
from tools.cgroup.vinyl_document import encode_vinyl_document
from tools.cgroup.xbox_wgs import read_wgs_index, serialize_wgs_file_list


def build_fh3_fixture(root: Path, document=None):
    document = document or {"shapes": [shape(0), shape(1, ("A", "B")), shape(2, ("A", "B"))]}
    wgs, slot, _ = build_wgs_fixture(root, package_name="Microsoft.OpusPG_8wekyb3d8bbwe",
                                    app_name="OpusReleaseFinal")
    index = read_wgs_index(slot)
    folder = slot / index.folders[0].directory_name
    payload = folder / "AAAAAAAABBBB4CCC8DDDEEEEEEEEEEEE"
    header = folder / "123456781234423492341234567890AB"
    encoded, _ = encode_vinyl_document(document, "fh3")
    payload.write_bytes(wrap_payload(encoded))
    header.write_bytes(fixture_header("fh3", len(document["shapes"]), "FH3 nested fixture"))
    return wgs, slot, payload, header


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class Fh3DiscoveryTests(unittest.TestCase):
    setUpClass = legacy_tests.LegacyFileTests.__dict__["setUpClass"]
    setUp = legacy_tests.LegacyFileTests.setUp
    service = legacy_tests.LegacyFileTests.service
    wait = legacy_tests.LegacyFileTests.wait

    def test_auto_scan_finds_package_nested_groups_and_preserves_all_sources(self):
        local = self.root / "Local"
        wgs, _, _, _ = build_fh3_fixture(local / "Packages")
        before = snapshot(local)
        service = self.service()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), patch(
            "kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", side_effect=AssertionError("No picker")
        ):
            self.assertEqual([wgs], discover_save_roots(get_adapter("fh3")))
            service.scanSaves("FH3")
            self.wait(service)
            saved = Path(service.lastOutput)
            doc = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual("FH3 nested fixture", doc["metadata"]["title"])
            self.assertEqual(2, len(doc["shapes"][1]["editor_group_path"]))
            self.assertTrue(saved.with_suffix(".preview.png").is_file())
            service.scanSaves("fh3")
            self.wait(service)
            self.assertEqual(saved, Path(service.lastOutput))
            self.assertIn("1 unchanged", service.summary)
        self.assertEqual(before, snapshot(local))

    def test_manual_folder_is_remembered_across_service_restart(self):
        wgs, _, _, _ = build_fh3_fixture(self.root / "copied")
        service = self.service()
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=str(wgs)):
            service.browseFh3Saves()
            self.wait(service)
        target = service.lastOutput
        restarted = self.service()
        with patch.object(restarted, "_default_save_roots", return_value=[]):
            restarted.scanSaves("fh3")
            self.wait(restarted)
        self.assertEqual(target, restarted.lastOutput)

    def test_cancelled_folder_picker_does_nothing(self):
        service = self.service()
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=""):
            service.browseFh3Saves()
        self.assertIsNone(service._future)
        self.assertFalse(service._root_cache_file("fh3").exists())

    def test_no_saves_is_actionable_and_other_games_are_not_detected(self):
        local = self.root / "Local"
        build_wgs_fixture(local / "Packages")
        service = self.service()
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
            self.assertEqual([], discover_save_roots(get_adapter("fh3")))
            service.scanSaves("fh3")
            self.wait(service)
        self.assertIn("Save folder / Extract file", service.summary)
        self.assertFalse(service.lastOutput)
        _, errors = discover_sources([local / "Packages"])
        self.assertTrue(any("not identified as Forza Horizon 3" in e for e in errors))

    def test_stale_descriptor_and_primary_blob_are_never_used(self):
        wgs, _, payload, header = build_fh3_fixture(self.root / "copy")
        stale = uuid.uuid4()
        (payload.parent / stale.hex.upper()).write_bytes(b"OLD DATA")
        (payload.parent / "container.255").write_bytes(b"newer filename but not active")
        (payload.parent / "container.3").write_bytes(serialize_wgs_file_list(3, [
            ("C_group", stale, uuid.UUID(payload.name)),
            ("header", uuid.UUID(header.name), uuid.UUID(header.name)),
        ]))
        sources, errors = discover_sources([wgs])
        self.assertEqual([], errors)
        self.assertEqual(payload, sources[0].payload)
        self.assertEqual(3, len(read_vinyl(payload, "fh3", header_path=header)[0]["shapes"]))
        payload.unlink()
        sources, errors = discover_sources([wgs])
        self.assertEqual([], sources)
        self.assertEqual(1, len(errors))

    def test_wrong_header_protected_and_mismatched_counts_rejected(self):
        wgs, _, payload, header = build_fh3_fixture(self.root / "copy")
        service = self.service()
        for data in (fixture_header("fh3", 3, version=0), fixture_header("fh3", 10), b"broken"):
            header.write_bytes(data)
            result = service._scan_fh3_work(wgs)
            self.assertEqual([], result["outputs"])
            self.assertTrue(result["issues"])
        header.write_bytes(fixture_header("fh3", 3))
        from tools.cgroup.fh3_files import read_payload
        raw = bytearray(read_payload(payload))
        raw[0x1d] = 0x21
        payload.write_bytes(wrap_payload(bytes(raw)))
        result = service._scan_fh3_work(wgs)
        self.assertEqual([], result["outputs"])
        self.assertIn("privacy guard", result["issues"][0])

    def test_unsupported_index_or_descriptor_is_reported_without_salvage(self):
        wgs, slot, payload, _ = build_fh3_fixture(self.root / "copy")
        index = slot / "containers.index"
        original = index.read_bytes()
        index.write_bytes(struct.pack("<I", 999) + original[4:])
        sources, errors = discover_sources([wgs])
        self.assertEqual([], sources)
        self.assertIn("unsupported WGS index version", errors[0])
        index.write_bytes(original)
        (payload.parent / "container.3").write_bytes(b"bad")
        sources, errors = discover_sources([wgs])
        self.assertEqual([], sources)
        self.assertTrue(errors)

    def test_changed_save_during_extraction_cannot_commit(self):
        wgs, _, payload, header = build_fh3_fixture(self.root / "copy")
        source = discover_sources([wgs])[0][0]
        service = self.service()
        original = header.read_bytes()
        def changed():
            header.write_bytes(original + b"changed")
            source.verify()
        with self.assertRaisesRegex(ValueError, "changed while reading"):
            service._read_legacy_vinyl_work(payload, "fh3", header_path=header,
                                          validate_source=changed, cache_key=source.cache_key)
        self.assertEqual([], list(service._library_root("fh3").iterdir()))

    def test_multiple_profiles_one_corrupt_does_not_hide_valid_profile(self):
        wgs, slot, _, _ = build_fh3_fixture(self.root / "copy")
        bad = wgs / "other-profile"
        bad.mkdir()
        (bad / "containers.index").write_bytes(b"broken")
        result = self.service()._scan_fh3_work(wgs)
        self.assertEqual(1, len(result["outputs"]))
        self.assertEqual(1, len(result["issues"]))

    def test_cancellation_before_discovery_does_not_write(self):
        wgs, _, _, _ = build_fh3_fixture(self.root / "copy")
        service = self.service()
        service._cancel_event.set()
        with self.assertRaisesRegex(ValueError, "cancelled"):
            service._scan_fh3_work(wgs)
        self.assertFalse(service._library_root("fh3").exists())

    def test_protected_vinyl_does_not_stop_other_readable_vinyls(self):
        from tools.cgroup.fh3_files import read_payload
        root = self.root / "copies"
        build_fh3_fixture(root / "owned")
        _, _, protected, _ = build_fh3_fixture(root / "protected")
        payload = bytearray(read_payload(protected))
        payload[0x1d] = 0x21
        protected.write_bytes(wrap_payload(bytes(payload)))
        before = snapshot(root)
        result = self.service()._scan_fh3_work(root)
        self.assertEqual(1, len(result["outputs"]))
        self.assertEqual(1, len(result["issues"]))
        self.assertIn("privacy guard", result["issues"][0])
        self.assertEqual(before, snapshot(root))

    def test_rescan_preserves_edited_library_document(self):
        wgs, _, _, _ = build_fh3_fixture(self.root / "copy")
        service = self.service()
        first = service._scan_fh3_work(wgs)
        target = Path(first["outputs"][0])
        edited = json.loads(target.read_text(encoding="utf-8"))
        edited["metadata"]["title"] = "My edited vinyl"
        target.write_text(json.dumps(edited), encoding="utf-8")
        before = snapshot(service._library_root("fh3"))
        result = service._scan_fh3_work(wgs)
        self.assertEqual([], result["outputs"])
        self.assertIn("preserved, not overwritten", result["issues"][0])
        self.assertEqual(before, snapshot(service._library_root("fh3")))

    def test_cancel_after_completed_entry_keeps_it_and_reports_it(self):
        root = self.root / "copies"
        build_fh3_fixture(root / "one")
        build_fh3_fixture(root / "two")
        before = snapshot(root)
        service = self.service()
        with patch.object(service, "_write_preview", side_effect=lambda _: service._cancel_event.set()):
            with self.assertRaisesRegex(ValueError, "1 completed Library entry"):
                service._scan_fh3_work(root)
        entries = list(service._library_root("fh3").iterdir())
        self.assertEqual(1, len(entries))
        self.assertFalse(entries[0].name.startswith(".kfps-legacy-"))
        self.assertEqual(before, snapshot(root))

    def test_3000_nested_shapes_from_wgs(self):
        document = {"shapes": [shape(i, ("outer", "inner")) for i in range(3000)]}
        wgs, _, _, _ = build_fh3_fixture(self.root / "copy", document)
        before = snapshot(wgs)
        result = self.service()._scan_fh3_work(wgs)
        self.assertEqual([], result["issues"])
        decoded = json.loads(Path(result["outputs"][0]).read_text(encoding="utf-8"))
        self.assertEqual(3000, len(decoded["shapes"]))
        self.assertEqual(2, len(decoded["shapes"][-1]["editor_group_path"]))
        self.assertEqual(before, snapshot(wgs))


if __name__ == "__main__":
    unittest.main()
