"""Synthetic FH3 file tests. No private art, real identities or saves."""
from __future__ import annotations

import copy
import json
import math
import os
import random
import struct
import sys
import tempfile
import time
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from game_adapters import get_adapter
from game_profiles import PROFILES, get_profile
from tools.cgroup.cgroup_codec import wrap_payload, layer_from_shape
from tools.cgroup.forza_source_decoder import cgroup_to_layers, layers_to_kfps_json_layers
from tools.cgroup.fh3_files import parse_header, read_payload, read_vinyl
from tools.cgroup.vinyl_document import encode_vinyl_document, _linear


def shape(index=0, path=()):
    return {"type": 1048677 + index % 4, "data": [index * 2.5, -index, -0.5, 1.3, 32, 0.15, 0],
            "color": [30, 180, 220, 210], "editor_group_path": [{"id": k, "name": k} for k in path]}


def fixture_header(game, count=1, title="Synthetic fixture", *, version=1):
    def text(value):
        raw = value.encode("utf-16le")
        return struct.pack("<I", len(raw) // 2) + raw
    assert game == "fh3"
    return (struct.pack("<I", version) + text(title) + text("")
            + struct.pack("<8HIQ", 2026, 10, 5, 23, 10, 0, 0, 0, 2, 123456)
            + text("Synthetic Test") + bytes(16 + version) + struct.pack("<I", count) + b"TESTID01")


def fixture_payload(game, *, generation=2):
    # Independent one-square fixture, not produced by the writer under test.
    assert game == "fh3"
    return (b"gyvl" + struct.pack("<II", 1, 0)
            + bytes((generation,)) + struct.pack("<ffff", 0, 0, 1, 0)
            + bytes((0 if generation == 1 else 0x20,)) + struct.pack("<HH", 1, 1) + bytes(3)
            + b"\x01" + struct.pack("<Hffffff4B", 101, 0, 0, 0, 1, 1, 0, 0, 0, 255, 255)
            + (b"\x01" if generation == 2 else b""))


def strict_tree(payload, generation):
    """Independent bounded grammar walk: no recovery, skipped bytes or guessed closes."""
    pos = 0

    def take(count):
        nonlocal pos
        raw = payload[pos:pos + count]
        if len(raw) != count:
            raise ValueError("truncated record")
        pos += count
        return raw

    if take(12) != b"gyvl\x01\0\0\0\0\0\0\0":
        raise ValueError("preamble")

    def group(depth=0):
        if depth > 64 or take(1) != bytes((generation,)):
            raise ValueError("transform/depth")
        transform = struct.unpack("<ffff", take(16))
        marker = take(1)[0]
        count, blocks = struct.unpack("<HH", take(4))
        expected_marker = 0 if generation == 1 and (depth == 0 or count > 1) else 0x20
        if marker != expected_marker or not count or blocks != (count + 7) // 8 or take(2) != bytes(2):
            raise ValueError("child header")
        bitmap = take(blocks)
        children = []
        for i in range(count):
            if bitmap[i // 8] & 1 << (i % 8):
                children.append(group(depth + 1))
            else:
                if take(1) != b"\x01":
                    raise ValueError("shape marker")
                children.append(struct.unpack("<Hffffff4B", take(30)))
        if generation == 2 and take(1) != b"\x01":
            raise ValueError("missing close")
        return {"transform": transform, "children": children}

    root = group()
    if pos != len(payload):
        raise ValueError("trailing bytes")
    return root


class LegacyCodecTests(unittest.TestCase):
    def test_handwritten_flat_fixture_matches_writer_exactly(self):
        item = {"type": 1048677, "data": [0, 0, 1, 1, 0, 0], "color": [255, 0, 0, 255]}
        for game in ("fh3",):
            payload, report = encode_vinyl_document({"shapes": [item]}, game)
            self.assertEqual(fixture_payload(game), payload)
            self.assertEqual(1, report["layers"])
            strict_tree(payload, 2)

    def check_roundtrip(self, items, game):
        before = copy.deepcopy(items)
        payload, report = encode_vinyl_document({"shapes": items}, game)
        strict_tree(payload, 2)
        layers, decoded = cgroup_to_layers(payload, game)
        self.assertEqual([], decoded["warnings"])
        self.assertEqual(len(items), len(layers))
        self.assertEqual(before, items)
        for item, actual in zip(items, layers):
            expected = layer_from_shape(item, 0, game)
            self.assertEqual(expected.shape_id, actual["shape_id"])
            self.assertEqual(list(expected.color_rgba), actual["color_rgba"])
            x, y, sx, sy, angle, skew = actual["data"][:6]
            values = (x, y, *_linear(sx, sy, angle, skew))
            expected_values = (expected.x, expected.y, *_linear(expected.sx, expected.sy, expected.rotation, expected.skew))
            for a, b in zip(values, expected_values):
                self.assertTrue(math.isclose(a, b, abs_tol=1e-5, rel_tol=2e-6))
        shapes, _ = layers_to_kfps_json_layers(layers, game)
        self.assertTrue(all(s["source_game"] == game for s in shapes))
        again, _ = encode_vinyl_document({"shapes": shapes}, game)
        self.assertEqual(payload, again)
        return layers, report

    def test_nested_loose_siblings_single_child_and_interleaved_groups(self):
        cases = [[shape(0), shape(1, ("A", "B")), shape(2, ("A", "B")),
                  shape(3, ("A",)), shape(4), shape(5, ("C",))],
                 [shape(0, ("A",)), shape(1), shape(2, ("A",))],
                 [shape(0, tuple(f"G{i}" for i in range(64)))]]
        for game in ("fh3",):
            for items in cases:
                with self.subTest(game=game, count=len(items)):
                    self.check_roundtrip(items, game)

    def test_3000_shapes_flat_grouped_and_separate_groups(self):
        for game in ("fh3",):
            for mode in (0, 1, 2):
                items = [shape(i, () if mode == 0 else ("A",) if mode == 1 else (f"G{i}",)) for i in range(3000)]
                with self.subTest(game=game, mode=mode):
                    self.check_roundtrip(items, game)

    def test_randomized_group_trees_and_transforms(self):
        rng = random.Random(231023)
        for game in ("fh3",):
            for run in range(30):
                items = []
                for i in range(rng.randint(1, 80)):
                    depth = rng.randrange(5)
                    item = shape(i, tuple(f"G{i // 8}-{d}" for d in range(depth)))
                    item["data"][:6] = [rng.uniform(-1000, 1000), rng.uniform(-1000, 1000),
                                        rng.choice((-1, 1)) * rng.uniform(0.1, 2), rng.uniform(0.1, 2),
                                        rng.uniform(-360, 360), rng.uniform(-0.5, 0.5)]
                    items.append(item)
                self.check_roundtrip(items, game)

    def test_masks_rasters_unknown_ids_and_bad_geometry_are_rejected(self):
        for game in ("fh3",):
            for update in ({"mask": True}, {"is_mask": True}, {"isMask": True},
                           {"data": [0, 0, 1, 1, 0, 0, 1]}, {"is_raster_logo": True},
                           {"type": 0x10FFFF}, {"data": [math.nan, 0, 1, 1]},
                           {"data": [1e100, 0, 1, 1]}):
                with self.subTest(game=game, update=update), self.assertRaises(ValueError):
                    encode_vinyl_document({"shapes": [{**shape(), **update}]}, game)
            with self.assertRaises(ValueError):
                encode_vinyl_document({"shapes": [shape()] * 3001}, game)

    def test_strict_checker_rejects_damage_recovery_might_accept(self):
        for game, generation in (("fh3", 2),):
            payload, _ = encode_vinyl_document({"shapes": [shape(0, ("A",)), shape(1)]}, game)
            for corrupt in (payload[:-1], payload + b"\0", payload[:37] + payload[54:]):
                with self.assertRaises(ValueError):
                    strict_tree(corrupt, generation)


class LegacyFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.source = self.root / "nested.json"
        self.document = {"shapes": [shape(0), shape(1, ("A", "B")), shape(2, ("A", "B")), shape(3, ("A",))]}
        self.source.write_text(json.dumps(self.document), encoding="utf-8")

    def fixture(self, game):
        folder = self.root / game
        folder.mkdir(exist_ok=True)
        (folder / "header").write_bytes(fixture_header(game))
        (folder / "C_group").write_bytes(wrap_payload(fixture_payload(game)))
        return folder

    def service(self):
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        service = CGroupLibraryService(paths, None, Mock(), SimpleNamespace(append=Mock()))
        self.addCleanup(service.close)
        return service

    def wait(self, service):
        deadline = time.monotonic() + 30
        while service.running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertFalse(service.running)
        self.assertEqual("Complete", service.status, service.summary)

    def test_header_unicode_is_preserved_without_rewriting_identity(self):
        for game in ("fh3",):
            title = "\u65e5\u672c\u8a9e \ud55c\uad6d\uc5b4 \U0001f600"
            header = parse_header(fixture_header(game, 3, title), game)
            self.assertEqual(title, header.title)
            self.assertEqual(123456, header.creator_id)
            self.assertEqual(b"TESTID01", header.asset_id)
            self.assertEqual(3, header.count)

    def test_truncated_wrong_version_wrong_kind_and_counts(self):
        for game in ("fh3",):
            raw = fixture_header(game)
            for end in range(len(raw)):
                with self.assertRaises(ValueError):
                    parse_header(raw[:end], game)
            with self.assertRaises(ValueError):
                parse_header(struct.pack("<I", 0) + raw[4:], game)
            for count in (0, 3001):
                with self.assertRaises(ValueError):
                    parse_header(fixture_header(game, count), game)
            bad = bytearray(raw)
            offset = 4 + 4 + len("Synthetic fixture") * 2 + 4
            struct.pack_into("<I", bad, offset + 16, 3)
            with self.assertRaisesRegex(ValueError, "full livery"):
                parse_header(bytes(bad), game)

    def test_read_fh3_accepts_generation1_without_guessing_fh6(self):
        folder = self.fixture("fh3")
        (folder / "C_group").write_bytes(wrap_payload(fixture_payload("fh3", generation=1)))
        document, report, _ = read_vinyl(folder, "fh3")
        self.assertEqual("generation_1", report["record_generation"])
        self.assertEqual("fh3", document["shapes"][0]["source_game"])

    def test_read_rejects_mismatch_current_generation_protected_and_corrupt(self):
        folder = self.fixture("fh3")
        (folder / "header").write_bytes(fixture_header("fh3", 2))
        with self.assertRaisesRegex(ValueError, "count"):
            read_vinyl(folder, "fh3")
        (folder / "header").unlink()
        bad_private = bytearray(fixture_payload("fh3"))
        bad_private[29] = 0x21
        for raw in (b"vlrc" + bytes(100), fixture_payload("fh3", generation=3), bytes(bad_private),
                    fixture_payload("fh3")[:-4], b"garbage"):
            (folder / "C_group").write_bytes(raw)
            with self.assertRaises((ValueError, RuntimeError)):
                read_vinyl(folder, "fh3")

    def test_compression_bombs_trailing_data_and_size_mismatch(self):
        source = self.root / "C_group"
        compressed = zlib.compress(b"x" * 10000)
        cases = [struct.pack("<II", len(compressed), 10) + compressed,
                 struct.pack("<II", len(compressed), 10**9) + compressed,
                 wrap_payload(fixture_payload("fh3")) + b"junk",
                 struct.pack("<II", len(compressed) + 4, 10000) + compressed + b"junk"]
        for raw in cases:
            source.write_bytes(raw)
            with self.assertRaises(ValueError):
                read_payload(source)

    def test_public_extraction_preserves_groups_source_and_existing_library(self):
        for game in ("fh3",):
            folder = self.fixture(game)
            payload, _ = encode_vinyl_document(self.document, game)
            (folder / "C_group").write_bytes(wrap_payload(payload))
            (folder / "header").write_bytes(fixture_header(game, 4))
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            service = self.service()
            outputs = []
            for _ in range(2):
                with patch("kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=(str(folder / "C_group"), "")), patch.object(
                    service, "_default_save_roots", side_effect=AssertionError("No automatic save access")
                ):
                    service.extractFh3File()
                    self.wait(service)
                target = Path(service.lastOutput)
                outputs.append(target)
                saved = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(4, len(saved["shapes"]))
                self.assertEqual(2, len(saved["shapes"][1]["editor_group_path"]))
                self.assertTrue(service.jsons.selectPath.called)
                self.assertTrue(target.with_suffix(".preview.png").is_file())
            self.assertNotEqual(*outputs)
            self.assertTrue(all(p.is_file() for p in outputs))
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_cancellation_and_commit_failure_leave_no_partial_library_entry(self):
        for game in ("fh3",):
            folder = self.fixture(game)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            service = self.service()
            library = service._library_root(game)
            library.mkdir(parents=True, exist_ok=True)
            keep = library / "existing.json"
            keep.write_text("keep")
            for cancel in (Mock(return_value=True), Mock(side_effect=[False, True])):
                with patch.object(service._cancel_event, "is_set", cancel), self.assertRaisesRegex(ValueError, "cancelled"):
                    service._read_legacy_vinyl_work(folder / "C_group", game)
                self.assertEqual([keep], list(library.iterdir()))
            with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=OSError("write failure")):
                with self.assertRaises(OSError):
                    service._read_legacy_vinyl_work(folder / "C_group", game)
            self.assertEqual([keep], list(library.iterdir()))
            self.assertEqual("keep", keep.read_text())
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_extraction_picker_cancel_and_bad_header_do_not_add_library_entry(self):
        folder = self.fixture("fh3")
        service = self.service()
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=("", "")):
            service.extractFh3File()
        self.assertIsNone(service._future)
        (folder / "header").write_bytes(b"bad")
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName", return_value=(str(folder / "C_group"), "")):
            service.extractFh3File()
            deadline = time.monotonic() + 10
            while service.running and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
        self.assertFalse(service.running)
        self.assertEqual("Failed", service.status)
        self.assertFalse(service._library_root("fh3").exists())

    def test_game_import_calls_are_blocked_without_dialogs_or_workers(self):
        service = self.service()
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for game in ("fh3",):
            with patch("kfps_ui.cgroup_library_service.QFileDialog.getOpenFileName") as picker, patch(
                "kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory"
            ) as folder_picker, patch("kfps_ui.cgroup_library_service.QMessageBox.question") as confirm:
                service.createLayerGroupFromSelectedJson(str(self.source), game)
                self.assertEqual(f"{game.upper()} offline import disabled", service.status)
                self.assertIn("extraction-only", service.summary)
                self.assertIsNone(service._future)
                picker.assert_not_called()
                folder_picker.assert_not_called()
                confirm.assert_not_called()
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_extracted_nested_artwork_can_be_encoded_for_current_games(self):
        for source_game in ("fh3",):
            folder = self.fixture(source_game)
            payload, _ = encode_vinyl_document(self.document, source_game)
            (folder / "C_group").write_bytes(wrap_payload(payload))
            (folder / "header").write_bytes(fixture_header(source_game, 4))
            extracted, _, _ = read_vinyl(folder, source_game)
            for target_game in ("fh4", "fh5", "fh6", "fm8"):
                with self.subTest(source=source_game, target=target_game):
                    encoded, report = encode_vinyl_document(extracted, target_game)
                    layers, decoded = cgroup_to_layers(encoded, target_game)
                    shapes, warnings = layers_to_kfps_json_layers(layers, target_game)
                    self.assertEqual(4, report["layers"])
                    self.assertEqual(2, report["groups"])
                    self.assertEqual([], decoded["warnings"])
                    self.assertEqual([], warnings)
                    for old, new in zip(extracted["shapes"], shapes):
                        self.assertEqual(old["type"], new["type"])
                        self.assertEqual(old["color"], new["color"])
                        self.assertEqual(len(old.get("editor_group_path", [])), len(new.get("editor_group_path", [])))
                        for a, b in zip(old["data"][:6], new["data"][:6]):
                            self.assertAlmostEqual(a, b, places=4)

    def test_legacy_does_not_enable_live_memory_or_implicit_save_install(self):
        service = self.service()
        self.assertEqual(["fh6", "fh5", "fh4", "fm"], list(PROFILES))
        for game in ("fh3",):
            self.assertFalse(get_adapter(game).supports("live_import"))
            self.assertFalse(get_adapter(game).supports("live_export"))
            self.assertFalse(get_adapter(game).supports("offline_import"))
            self.assertTrue(get_adapter(game).supports("offline_export"))
            self.assertFalse(get_adapter(game).offline_import_handler)
            self.assertIn("Unavailable", service.offlineImportLabel(game))
            with self.assertRaises(ValueError):
                get_profile(game)
            with self.assertRaises(ValueError):
                service._create_folder_install_work(self.source, game)

    def test_retired_fh2_is_not_offered_or_redirected_to_another_game(self):
        service = self.service()
        self.assertNotIn("FH2", service.gameTargets)
        with self.assertRaises(ValueError):
            get_adapter("fh2")
        with self.assertRaises(ValueError):
            encode_vinyl_document(self.document, "fh2")
        with self.assertRaises(ValueError):
            parse_header(fixture_header("fh3"), "fh2")
        service.scanSaves("fh2")
        service.createLayerGroupFromSelectedJson(str(self.source), "fh2")
        self.assertIsNone(service._future)

    def test_live_bridge_cli_does_not_advertise_legacy_targets(self):
        import subprocess
        result = subprocess.run([sys.executable, str(UI / "bridges/transfer_bridge.py"), "export", "--help"],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("{fh4,fh5,fh6,fm}", result.stdout)
        self.assertNotIn("fh2", result.stdout)
        self.assertNotIn("fh3", result.stdout)


if __name__ == "__main__":
    unittest.main()
