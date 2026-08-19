import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.cgroup_library_service import CGroupLibraryService
from kfps_ui.app_paths import AppPaths
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, parse_flat_payload, wrap_payload
from tools.cgroup.forza_source_decoder import (
    GroupNode,
    ShapeNode,
    WalkState,
    build_livery_sections,
    cgroup_to_layers,
    decode_forza_source,
    flatten_tree,
    is_extended_livery_transform_at,
    is_unsupported_shape_record_at,
    is_valid_shape_at,
    livery_transform_marker_sizes,
    mark_previous_direct_shape_as_mask,
    mark_previous_terminal_shape_as_mask,
    probe_forza_source_kind,
    read_livery_transform,
    Transform,
    valid_counted_group_at,
    valid_markerless_group_at,
    walk_step,
)


def write_wrapped(path: Path, payload: bytes) -> None:
    compressed = zlib.compress(payload)
    path.write_bytes(struct.pack("<II", len(compressed), len(payload)) + compressed)


class CGroupLibraryScanTests(unittest.TestCase):
    @staticmethod
    def _shape(color=(255, 255, 255, 255)) -> ShapeNode:
        return ShapeNode(0x0066, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, color, 0)

    @staticmethod
    def _framed_shape(shape_id: int, *, sy: float = 1.0) -> bytes:
        return (
            b"\x00\x02"
            + struct.pack("<Hffffff", shape_id, 0.0, 1.0, 2.0, 1.0, sy, 0.0)
            + bytes((255, 255, 255, 255))
        )

    def test_livery_extended_transform_header_is_not_decoded_as_shape_word_0100(self):
        record = (
            b"\x00\x02\x00\x01\x00\x00\x00\x03"
            + struct.pack("<ffff", 12.0, -34.0, 2.5, 180.0)
            + b"\x20\x01\x00\x01\x00\x00\x00\x00"
        )

        self.assertTrue(is_extended_livery_transform_at(record, 0, len(record)))
        self.assertFalse(is_valid_shape_at(record, 0, len(record)))
        self.assertEqual(8, livery_transform_marker_sizes(record, 0, len(record))[0])

    def test_livery_parent_bitmap_wins_over_ambiguous_extended_transform(self):
        child_group = (
            struct.pack("<HH", 2, 1)
            + b"\x00\x00\x00"
            + self._framed_shape(0x0066)
            + self._framed_shape(0x0067)
        )
        ambiguous_group = (
            b"\x00"
            + struct.pack("<HH", 2, 1)
            + b"\x00\x00\x03"
            + struct.pack("<ffff", 12.0, -34.0, 2.5, 180.0)
            + child_group
        )
        parent = GroupNode(expected_children=1, child_bitmap=b"\x01")
        pending = Transform(x=4.0, y=5.0, sx=1.0, sy=1.0, rotation=0.0)
        state = WalkState(stack=[parent], pending_transform=pending)

        pos = walk_step(ambiguous_group, 0, len(ambiguous_group), state, livery=True)
        self.assertEqual(1, pos)
        self.assertIs(state.pending_transform, pending)

        pos = walk_step(ambiguous_group, pos, len(ambiguous_group), state, livery=True)
        self.assertGreater(pos, 1)
        self.assertEqual(1, len(parent.items))
        self.assertIsInstance(parent.items[0], GroupNode)
        self.assertEqual(2, parent.items[0].expected_children)

    def test_livery_protected_wrapper_is_not_consumed_as_section_group_transform(self):
        child_group = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00\x00"
            + self._framed_shape(0x0066)
        )
        protected_wrapper = (
            b"\x31"
            + bytes(6)
            + b"\x09\x00"
            + struct.pack("<f", 0.47)
        )
        section_lead = (
            struct.pack("<HH", 1, 1)
            + b"\x00\x00\x01"
            + struct.pack("<ffff", 120.0, -39.5, -0.47, 0.0)
            + protected_wrapper
            + child_group
        )

        self.assertIsNone(
            valid_markerless_group_at(
                section_lead, 0, len(section_lead), allow_count_one=True, livery=True
            )
        )

    def test_counted_group_does_not_capture_zero_led_child_transform(self):
        leaf_group = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00\x00"
            + self._framed_shape(0x0066)
        )
        child_transform = b"\x00" + struct.pack("<ffff", 0.16, -0.05, 0.03, 266.9)
        group = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00\x01"
            + child_transform
            + leaf_group
        )

        info = valid_counted_group_at(group, 0, len(group), livery=True)

        self.assertIsNotNone(info)
        self.assertIsNone(info.inline_transform)
        self.assertEqual(8, info.size)

    def test_separate_livery_rotation_keeps_sign_when_child_frame_is_unmarked(self):
        leaf_group = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00\x00"
            + self._framed_shape(0x0066)
        )
        successor = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00\x01"
            + b"\x00"
            + struct.pack("<ffff", 0.16, -0.05, 0.03, 266.9)
            + leaf_group
        )
        record = b"\x01" + struct.pack("<ffff", 27.0, -73.5, 1.0, 91.9) + successor

        decoded = read_livery_transform(record, 0, len(record), invert_odd_rotation=True)

        self.assertIsNotNone(decoded)
        self.assertAlmostEqual(91.9, decoded[1].rotation, places=4)

    def test_shape_validation_rejects_control_payload_but_keeps_real_word_0200(self):
        self.assertFalse(is_valid_shape_at(self._framed_shape(0x0200, sy=0.0), 0, 32))
        self.assertTrue(is_valid_shape_at(self._framed_shape(0x0200), 0, 32))

    def test_library_visibility_does_not_unlock_offline_save_tools(self):
        class DummyLog:
            def __init__(self):
                self.messages = []

            def append(self, message, level="info"):
                self.messages.append((str(message), str(level)))

        with tempfile.TemporaryDirectory() as temp:
            app_root = Path(temp)
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            log = DummyLog()
            service = CGroupLibraryService(
                paths, object(), object(), log,
                supporter=SimpleNamespace(unlocked=False),
                demo=True,
            )
            self.addCleanup(service.close)
            try:
                with patch.object(service._executor, "submit") as submit:
                    service.scanSaves("fh6")
                    service.createLayerGroupFromSelectedJson(str(app_root / "fixture.json"), "fh6")
                    service.installJsonToFH6LayerGroup(
                        str(app_root / "fixture.json"), str(app_root / "LayerGroup"),
                    )
                submit.assert_not_called()
                self.assertFalse(service.running)
                self.assertEqual(service.status, "Supporter unlock required")
                self.assertTrue(all("unlock" in message.lower() for message, _level in log.messages))
            finally:
                service.close()

    def test_final_root_close_preserves_last_flat_mask(self):
        payload = bytearray(
            build_flat_payload(
                [CGroupLayer(0x0066, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, (204, 231, 249, 255))]
            )
        )
        payload[-2:] = b"\x01\x01"

        layers, report = cgroup_to_layers(bytes(payload), game="fh6")
        parsed = parse_flat_payload(bytes(payload))

        self.assertEqual(report["decoded_layers"], 1)
        self.assertTrue(layers[0]["mask"])
        self.assertTrue(parsed["layers"][0]["mask"])
        self.assertEqual(parsed["trailer_hex"], "0101")

    def test_normal_root_close_keeps_last_flat_shape_visible(self):
        payload = build_flat_payload(
            [CGroupLayer(0x0066, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, (204, 231, 249, 255))]
        )

        layers, _report = cgroup_to_layers(payload, game="fh6")

        self.assertFalse(layers[0]["mask"])
        self.assertFalse(parse_flat_payload(payload)["layers"][0]["mask"])

    def test_mask_markers_respect_parent_boundaries(self):
        nested_shape = self._shape()
        nested = GroupNode(items=[nested_shape])
        root = GroupNode(expected_children=2, items=[nested])
        state = WalkState(stack=[root])

        self.assertFalse(mark_previous_direct_shape_as_mask(state))
        self.assertFalse(nested_shape.mask)
        self.assertTrue(mark_previous_terminal_shape_as_mask(state))
        self.assertTrue(nested_shape.mask)

    def test_explicit_mask_group_remains_authoritative_for_colored_shapes(self):
        colored = self._shape((204, 231, 249, 255))
        root = GroupNode(items=[GroupNode(mask=True, items=[colored])])

        layers = flatten_tree(root)

        self.assertTrue(layers[0]["mask"])

    def test_ambiguous_colored_record_mask_is_not_promoted(self):
        colored = self._shape((204, 231, 249, 255))
        colored.mask = True
        root = GroupNode(items=[colored])

        layers = flatten_tree(root)

        self.assertFalse(layers[0]["mask"])

    def test_livery_section_terminal_mask_marks_its_final_shape(self):
        shape = self._framed_shape(0x0066)
        body = shape + b"\x01" + bytes(17 + 23 * 10)

        layers, warnings = build_livery_sections(body, [1] + [0] * 10)

        self.assertEqual(warnings, [])
        self.assertEqual(len(layers), 1)
        self.assertTrue(layers[0]["mask"])

    def test_spoiler_section_uses_its_section_canvas_orientation(self):
        shape = (
            b"\x00\x02"
            + struct.pack("<Hffffff", 0x0066, 15.0, 12.0, -34.0, 1.5, 2.0, 0.25)
            + bytes((255, 255, 255, 255))
        )
        body = bytes(23 * 5) + shape + bytes(18 + 23 * 5)

        layers, warnings = build_livery_sections(body, [0] * 5 + [1] + [0] * 5)

        self.assertEqual(warnings, [])
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["section"], "Spoiler")
        self.assertAlmostEqual(layers[0]["data"][0], -12.0)
        self.assertAlmostEqual(layers[0]["data"][1], 34.0)
        self.assertAlmostEqual(layers[0]["data"][4], 195.0)

    def test_livery_markerless_group_uses_control_then_child_bitmap(self):
        nested_shape = self._framed_shape(0x0066)
        direct_shape = self._framed_shape(0x0067)
        counted_child = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00"
            + b"\x00"
            + nested_shape
        )
        markerless_root = (
            struct.pack("<HH", 2, 1)
            + b"\x00\x00"
            + b"\x01"
            + counted_child
            + direct_shape
        )
        body = markerless_root + bytes(18 + 23 * 10)

        layers, warnings = build_livery_sections(body, [2] + [0] * 10)

        self.assertEqual(warnings, [])
        self.assertEqual([layer["shape_id"] for layer in layers], [0x0066, 0x0067])

    def test_livery_mask_control_does_not_hide_colored_terminal_shape(self):
        colored_shape = self._framed_shape(0x0066)[:-4] + bytes((10, 20, 30, 255))
        control_shape = b"\x01" + self._framed_shape(0x0067)[1:]
        counted_child = (
            b"\x20"
            + struct.pack("<HH", 1, 1)
            + b"\x00\x00"
            + b"\x00"
            + colored_shape
        )
        markerless_root = (
            struct.pack("<HH", 2, 1)
            + b"\x00\x00"
            + b"\x01"
            + counted_child
            + control_shape
        )
        body = markerless_root + bytes(18 + 23 * 10)

        layers, warnings = build_livery_sections(body, [2] + [0] * 10)

        self.assertEqual(warnings, [])
        self.assertFalse(layers[0]["mask"])
        self.assertFalse(layers[1]["mask"])

    def test_unsupported_livery_record_occupies_child_without_shifting_next_section(self):
        unsupported = self._framed_shape(0x0BB8)
        front_shape = self._framed_shape(0x0066)
        back_shape = self._framed_shape(0x0067)
        front = (
            struct.pack("<HH", 2, 1)
            + b"\x00\x00"
            + b"\x00"
            + unsupported
            + front_shape
        )
        body = front + bytes(18) + back_shape + bytes(18 + 23 * 9)

        self.assertTrue(is_unsupported_shape_record_at(unsupported, 0, len(unsupported)))
        layers, warnings = build_livery_sections(body, [2, 1] + [0] * 9)

        self.assertEqual(
            [(layer["section"], layer["shape_id"]) for layer in layers],
            [("Front", 0x0066), ("Back", 0x0067)],
        )
        self.assertEqual(warnings, ["Front: decoded 1 layer(s), stats target is 2"])

    def test_fh5_wgs_discovers_opaque_direct_and_wrapped_groups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = (
                Path(temp)
                / "Microsoft.624F8B84B80_8wekyb3d8bbwe"
                / "SystemAppData"
                / "wgs"
            )
            slot = root / "000901F_TEST"
            slot.mkdir(parents=True)
            direct = slot / "A1B2C3D4E5F6"
            wrapped = slot / "001122334455"
            livery = slot / "FFEEDDCCBBAA"
            payload = build_flat_payload(
                [CGroupLayer(0x0065, 1.0, 2.0, 1.0, 1.0, 0.0, 0.0, (255, 0, 0, 255))]
            )
            direct.write_bytes(payload)
            wrapped.write_bytes(wrap_payload(payload))
            write_wrapped(livery, b"vlrc" + bytes(128))
            (slot / "container.index").write_bytes(b"not a forza artifact")

            self.assertEqual(probe_forza_source_kind(direct), "cgroup")
            self.assertEqual(probe_forza_source_kind(wrapped), "cgroup")
            self.assertEqual(probe_forza_source_kind(livery), "clivery")
            self.assertEqual(len(decode_forza_source(direct, game="fh5").layers), 1)
            self.assertEqual(len(decode_forza_source(wrapped, game="fh5").layers), 1)
            found = CGroupLibraryService._discover_save_artifacts([root], "fh5")
            self.assertEqual({path.name for path in found}, {direct.name, wrapped.name})

    def test_fh6_structured_scan_returns_more_than_old_180_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "XboxGames" / "GameSave"
            containers = root / "pgs" / "user" / "slot" / "ContainersRoot"
            for index in range(500):
                folder = containers / f"LayerGroup_{index:04d}"
                folder.mkdir(parents=True)
                (folder / "C_group").write_bytes(b"gyvl" + bytes(32))

            found = CGroupLibraryService._discover_save_artifacts([root], "fh6")
            self.assertEqual(len(found), 500)

    def test_partial_scan_does_not_prune_unseen_valid_library_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            library.mkdir()
            source_a = Path(temp) / "save" / "LayerGroup_A" / "C_group"
            source_b = Path(temp) / "save" / "LayerGroup_B" / "C_group"

            def add_entry(name: str, source: Path) -> Path:
                entry = library / name
                entry.mkdir()
                manifest = {
                    "source_path": str(source),
                    "source_folder": source.parent.name,
                    "source_kind": "cgroup",
                    "target_game": "fh6",
                }
                (entry / f"{name}.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                return entry

            current_a = add_entry("source-a-current", source_a)
            old_a = add_entry("source-a-old", source_a)
            unseen_b = add_entry("source-b-cached", source_b)
            CGroupLibraryService._prune_non_layergroup_library_entries(
                library,
                {current_a.name},
                {CGroupLibraryService._source_path_key(source_a)},
                "fh6",
            )

            self.assertTrue(current_a.exists())
            self.assertFalse(old_a.exists())
            self.assertTrue(unseen_b.exists())

    def test_pruning_keeps_opaque_fh5_group_names(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "library"
            entry = library / "opaque-fh5-current"
            entry.mkdir(parents=True)
            source = Path(temp) / "SystemAppData" / "wgs" / "ABCDEF012345"
            manifest = {
                "source_path": str(source),
                "source_folder": source.parent.name,
                "source_kind": "cgroup",
                "target_game": "fh5",
            }
            (entry / "opaque-fh5-current.manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            CGroupLibraryService._prune_non_layergroup_library_entries(
                library,
                {entry.name},
                {CGroupLibraryService._source_path_key(source)},
                "fh5",
            )

            self.assertTrue(entry.exists())


if __name__ == "__main__":
    unittest.main()
