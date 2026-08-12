from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_export_typecode_json as live_export  # noqa: E402
from fh6_live_group_policy import MIN_HEADER_SIZE, assess_group_tree, classify_group_header  # noqa: E402
from tools.cgroup.forza_source_decoder import (  # noqa: E402
    ShapeNode,
    Transform,
    decompose_matrix,
    group_matrix,
    matmul,
    shape_matrix,
)
sys.path.insert(0, str(ROOT / "KFPS.UI" / "bridges"))
import transfer_bridge  # noqa: E402


def policy_header(state: int = 0) -> bytes:
    raw = bytearray(MIN_HEADER_SIZE)
    struct.pack_into("<I", raw, MIN_HEADER_SIZE - 4, state)
    return bytes(raw)


class Fh6LiveGroupPolicyTests(unittest.TestCase):
    def test_header_states_fail_closed(self):
        self.assertEqual("clear", classify_group_header(policy_header(0)))
        self.assertEqual("clear", classify_group_header(policy_header(0x20)))
        self.assertEqual("restricted", classify_group_header(policy_header(0x21)))
        self.assertEqual("unknown", classify_group_header(policy_header(0x7F)))
        self.assertEqual("unknown", classify_group_header(b"short"))

    def test_restricted_nested_child_blocks_clear_root(self):
        headers = {0x1000: policy_header(), 0x2000: policy_header(0x21)}
        children = {0x1000: [0x2000], 0x2000: []}
        result = assess_group_tree(0x1000, headers.__getitem__, lambda group: children[group])
        self.assertFalse(result.allowed)
        self.assertEqual("restricted", result.status)
        self.assertEqual(2, result.group_count)
        self.assertNotIn("0x", result.reason)

    def test_unknown_state_and_recursive_hierarchy_are_rejected(self):
        unknown = assess_group_tree(1, lambda _group: policy_header(5), lambda _group: ())
        self.assertFalse(unknown.allowed)
        self.assertEqual("unknown", unknown.status)

        recursive = assess_group_tree(1, lambda _group: policy_header(), lambda _group: (1,))
        self.assertFalse(recursive.allowed)
        self.assertEqual("unknown", recursive.status)

    def test_clear_hierarchy_has_stable_structure_fingerprint(self):
        headers = {1: policy_header(), 2: policy_header(0x20), 3: policy_header(0x20)}
        first = assess_group_tree(1, headers.__getitem__, lambda group: {1: (2, 3), 2: (), 3: ()}[group])
        second = assess_group_tree(1, headers.__getitem__, lambda group: {1: (2, 3), 2: (), 3: ()}[group])
        changed = assess_group_tree(1, headers.__getitem__, lambda group: {1: (3, 2), 2: (), 3: ()}[group])
        self.assertTrue(first.allowed)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertNotEqual(first.fingerprint, changed.fingerprint)

    def test_fast_locator_accepts_only_verified_recursive_exports(self):
        session = {
            "type": "fh6_session_location_v1",
            "game": "fh6",
            "layer_count": 8,
            "group_address": 0x1000,
            "table_address": 0x2000,
            "capacity_count": 2,
            "vector_count": 2,
            "validated_entries": 8,
            "flattened_from_groups": True,
            "export_access_verified": True,
            "group_graph": {"is_flat_orphan": False},
            "samples": [{} for _ in range(8)],
        }
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertTrue(ok, reasons)
        self.assertTrue(live_export.locator_allows_flattened(session))

        session["export_access_verified"] = False
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertFalse(ok)
        self.assertTrue(reasons)
        self.assertFalse(live_export.locator_allows_flattened(session))

    def test_fh4_fast_locator_requires_verified_recursive_export(self):
        session = {
            "type": "fh6_session_location_v1",
            "game": "fh4",
            "layer_count": 8,
            "group_address": 0x1000,
            "table_address": 0x2000,
            "capacity_count": 2,
            "vector_count": 2,
            "validated_entries": 8,
            "flattened_from_groups": True,
            "export_access_verified": False,
            "group_graph": {"is_flat_orphan": False},
            "samples": [{} for _ in range(8)],
        }
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertFalse(ok)
        self.assertIn("complete live vinyl hierarchy", " ".join(reasons))
        self.assertFalse(live_export.locator_allows_flattened(session))

        session["export_access_verified"] = True
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertTrue(ok, reasons)
        self.assertTrue(live_export.locator_allows_flattened(session))

    def test_fh5_fast_locator_requires_verified_recursive_export(self):
        session = {
            "type": "fh6_session_location_v1",
            "game": "fh5",
            "layer_count": 8,
            "group_address": 0x1000,
            "table_address": 0x2000,
            "capacity_count": 2,
            "vector_count": 2,
            "validated_entries": 8,
            "flattened_from_groups": True,
            "export_access_verified": False,
            "group_graph": {"is_flat_orphan": False},
            "samples": [{} for _ in range(8)],
        }
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertFalse(ok)
        self.assertIn("complete live vinyl hierarchy", " ".join(reasons))
        self.assertFalse(live_export.locator_allows_flattened(session))

        session["export_access_verified"] = True
        ok, reasons = live_export.validate_fast_session_report(session, 8, 0x1000, 0x2000)
        self.assertTrue(ok, reasons)
        self.assertTrue(live_export.locator_allows_flattened(session))

    def test_live_affine_composition_matches_serialized_decoder_contract(self):
        parent = [120.0, 45.0, 1.8, 0.75, 32.0, 0.0]
        child = [-18.0, 26.0, 0.8, 1.25, 14.0, 0.12]
        live_matrix = live_export.multiply_matrix(
            live_export.fh6_matrix_from_data(parent),
            live_export.fh6_matrix_from_data(child),
        )
        live_data = live_export.fh6_data_from_matrix(live_matrix)

        serialized_matrix = matmul(
            group_matrix(Transform(x=parent[0], y=parent[1], sx=parent[2], sy=parent[3], rotation=parent[4])),
            shape_matrix(
                ShapeNode(
                    shape_id=102,
                    x=child[0],
                    y=child[1],
                    sx=child[2],
                    sy=child[3],
                    rotation=child[4],
                    skew=child[5],
                    color_rgba=(255, 255, 255, 255),
                    offset=0,
                )
            ),
        )
        serialized_data = decompose_matrix(serialized_matrix)
        for actual, expected in zip(live_data, serialized_data):
            self.assertAlmostEqual(expected, actual, places=5)

    def test_recursive_pointer_collection_preserves_depth_first_layer_order(self):
        groups = {
            0x1000: {"group": 0x1000, "table": 0x1100, "vector_count": 3, "capacity_count": 3},
            0x2000: {"group": 0x2000, "table": 0x2100, "vector_count": 2, "capacity_count": 2},
        }
        slots = {
            (0x1100, 0): 0x3001,
            (0x1100, 1): 0x2000,
            (0x1100, 2): 0x3002,
            (0x2100, 0): 0x4001,
            (0x2100, 1): 0x4002,
        }
        transforms = {
            0x1000: {"x": 10.0, "y": 20.0, "sx": 1.0, "sy": 1.0, "rotation": 0.0, "skew": 0.0},
            0x2000: {"x": 5.0, "y": 0.0, "sx": 2.0, "sy": 2.0, "rotation": 0.0, "skew": 0.0},
        }

        def group_info(_handle, address, _vtable=None):
            return groups.get(address)

        with patch.object(live_export, "read_group_vector_info", side_effect=group_info), patch.object(
            live_export, "ptr_at", side_effect=lambda _handle, table, index: slots[(table, index)]
        ), patch.object(
            live_export, "read_transform_fields", side_effect=lambda _handle, address: transforms[address]
        ), patch.object(
            live_export, "layer_pointer_exportable", side_effect=lambda _handle, address: address in {0x3001, 0x3002, 0x4001, 0x4002}
        ), patch.object(
            live_export, "read_group_parent", side_effect=lambda _handle, address: 0x1000 if address == 0x2000 else 0
        ), patch.object(live_export, "pointer_has_group_signature", return_value=False):
            pointers, stats = live_export.collect_export_layer_pointers(
                object(),
                0x1000,
                0x1100,
                4,
                {"vtable": 0xAA, "flattened_from_groups": True, "export_access_verified": True},
            )

        self.assertEqual([0x3001, 0x4001, 0x4002, 0x3002], [item[0] for item in pointers])
        self.assertEqual(2, stats["group_count"])
        self.assertEqual(1, stats["max_depth"])
        child_matrix = pointers[1][1]
        child_origin = live_export.fh6_data_from_matrix(child_matrix)
        self.assertAlmostEqual(15.0, child_origin[0], places=5)
        self.assertAlmostEqual(20.0, child_origin[1], places=5)

    def test_fallback_locator_returns_its_own_report_when_fast_locator_has_no_match(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                command = [str(item) for item in command]
                if any(item.endswith("fh6_probe.py") for item in command):
                    session = Path(command[command.index("--write-session") + 1])
                    session.write_text(
                        '{"type":"fh6_session_location_v1","layer_count":8}',
                        encoding="utf-8",
                    )
                    return 0
                report = run_dir / "fh6-group8-probe-test.json"
                report.write_text(
                    '{"count":8,"candidates":[{"group":"0x1000","table":"0x2000",'
                    '"valid_ptrs":8,"invalid_ptrs":0,"layer_ok_count":8,"vector_ok":true,'
                    '"vector_count":8,"capacity_count":8,"score":100}]}',
                    encoding="utf-8",
                )
                return 0

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                group, table, report = transfer_bridge.locate_universal_template(
                    "fh6", 123, 8, run_dir, "export-template"
                )

            self.assertEqual("0x1000", group)
            self.assertEqual("0x2000", table)
            self.assertEqual(run_dir / "fallback-export-template-probe.json", report)
            self.assertTrue(report.exists())

    def test_fast_policy_refusal_is_terminal_and_never_runs_fallback_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            calls = []

            def fake_subprocess(command, timeout=None):
                del timeout
                command = [str(item) for item in command]
                calls.append(command)
                session = Path(command[command.index("--write-session") + 1])
                session.write_text(
                    '{"type":"fh6_session_location_v1","layer_count":8,"refused":true,'
                    '"refusal_reason":"Export refused: this vinyl contains content that is not owned by the current profile."}',
                    encoding="utf-8",
                )
                return 0

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "not owned"):
                    transfer_bridge.locate_universal_template("fh6", 123, 8, run_dir, "export-template")

            self.assertEqual(1, len(calls))
            self.assertFalse((run_dir / "fallback-export-template-probe.json").exists())


if __name__ == "__main__":
    unittest.main()
