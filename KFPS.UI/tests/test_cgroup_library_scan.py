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
    cgroup_to_layers,
    decode_forza_source,
    flatten_tree,
    is_extended_livery_transform_at,
    is_valid_shape_at,
    livery_transform_marker_sizes,
    mark_previous_direct_shape_as_mask,
    mark_previous_terminal_shape_as_mask,
    probe_forza_source_kind,
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
