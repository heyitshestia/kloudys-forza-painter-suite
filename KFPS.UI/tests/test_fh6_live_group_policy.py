from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_export_typecode_json as live_export  # noqa: E402
import fh6_probe  # noqa: E402
from fh6_live_group_policy import (  # noqa: E402
    MIN_HEADER_SIZE,
    assess_group_tree,
    classify_group_header,
    minimum_header_size,
)
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
from live_memory_locator import DIAGNOSTIC_SCHEMA  # noqa: E402


def policy_header(state: int = 0, *, game: str = "fh6") -> bytes:
    size = minimum_header_size(game)
    raw = bytearray(size)
    struct.pack_into("<I", raw, size - 4, state)
    return bytes(raw)


def write_engine_report(command, *, status, reason="", selected=None):
    command = [str(item) for item in command]
    output = Path(command[command.index("--output") + 1])
    game = command[command.index("--game") + 1]
    pid = int(command[command.index("--pid") + 1])
    count = int(command[command.index("--layer-count") + 1])
    purpose = command[command.index("--purpose") + 1]
    if isinstance(selected, dict):
        selected = {
            "validated_entries": count,
            "vector_count": count,
            "capacity_count": count,
            **selected,
        }
        if purpose == "import":
            selected.setdefault("import_vector_count", count)
            selected.setdefault("import_capacity_count", count)
    output.write_text(
        json.dumps(
            {
                "schema": DIAGNOSTIC_SCHEMA,
                "outcome": {"status": status, "reason": reason, "authoritative": True},
                "request": {
                    "game": game,
                    "pid": pid,
                    "layer_count": count,
                    "purpose": purpose,
                },
                "selected": selected,
            }
        ),
        encoding="utf-8",
    )
    return {"located": 0, "refused": 2, "no_match": 3, "error": 4}[status]


class Fh6LiveGroupPolicyTests(unittest.TestCase):
    def test_export_group_metadata_uses_the_minimum_required_read(self):
        raw = bytearray(live_export.GROUP_METADATA_READ_SIZE)
        struct.pack_into("<H", raw, live_export.GROUP_COUNT_OFFSET, 2923)
        struct.pack_into("<QQQ", raw, live_export.GROUP_TABLE_BEGIN_OFFSET, 0x2000, 0x2008, 0x2008)
        with patch.object(live_export, "read_memory", return_value=bytes(raw)) as read:
            metadata = live_export.read_group_metadata(99, 0x1000)

        read.assert_called_once_with(99, 0x1000, live_export.GROUP_TABLE_CAPACITY_OFFSET + 8)
        self.assertEqual(2923, metadata["count_u16_0x5a"])
        self.assertEqual(1, metadata["vector_count"])

    def test_fm8_export_accepts_verified_low_address_root(self):
        table = 0x341E28048
        metadata = {
            "group": "0x81578e00",
            "count_u16_0x5a": 65,
            "table_begin_0x78": hex(table),
            "table_end_0x80": hex(table + 8),
            "table_capacity_0x88": hex(table + 8),
            "vector_count": 1,
            "capacity_count": 1,
        }

        passed, reasons = live_export.validate_editable_group(
            metadata,
            65,
            table,
            allow_flattened=True,
            game="fm",
        )

        self.assertTrue(passed, reasons)

    def test_fh6_export_still_rejects_low_address_root(self):
        table = 0x341E28048
        metadata = {
            "group": "0x81578e00",
            "count_u16_0x5a": 65,
            "table_begin_0x78": hex(table),
            "table_end_0x80": hex(table + 8),
            "table_capacity_0x88": hex(table + 8),
            "vector_count": 1,
            "capacity_count": 1,
        }

        passed, reasons = live_export.validate_editable_group(
            metadata,
            65,
            table,
            allow_flattened=True,
            game="fh6",
        )

        self.assertFalse(passed)
        self.assertIn("group header address is outside the normal FH6 editable group range", reasons)

    def test_exact_locator_success_returns_candidate_and_refusal_tuple(self):
        group = {
            "group_address": 0x1000,
            "count_address": 0x105A,
            "table_pointer_field": 0x1078,
            "table_address": 0x1100,
            "vector_count": 3,
            "capacity_count": 3,
            "current_u16": 3,
            "current_u32": 3,
            "parent_group": 0,
            "vtable": 0xAA,
        }
        flat = {
            "shape_count": 3,
            "invalid_count": 0,
            "group_count": 1,
            "max_depth": 0,
            "samples": [],
            "leaf_groups": [{**group, "shape_count": 3}],
        }
        with patch.object(fh6_probe, "read_calibrated_group_vector", return_value=group), patch.object(
            fh6_probe, "assess_calibrated_group_access", return_value=None
        ), patch.object(
            fh6_probe, "flatten_calibrated_group", return_value=flat
        ):
            candidate, refusal = fh6_probe.evaluate_exact_calibrated_root(
                99,
                fh6_probe.get_profile("fh6"),
                3,
                {"vtables": [0xAA]},
                0x1000,
                lambda _address, _size=1: True,
                locator_kind="test_exact",
            )

        self.assertIsNone(refusal)
        self.assertEqual("test_exact", candidate["count_kind"])
        self.assertEqual(0x1100, candidate["import_table_address"])

    def test_nested_import_target_uses_verified_leaf_table_not_root_table(self):
        root = {
            "group_address": 0x1000,
            "count_address": 0x105A,
            "table_pointer_field": 0x1078,
            "table_address": 0x1100,
            "vector_count": 1,
            "capacity_count": 1,
        }
        child = {
            "group_address": 0x2000,
            "count_address": 0x205A,
            "table_pointer_field": 0x2078,
            "table_address": 0x2100,
            "vector_count": 3,
            "capacity_count": 3,
        }
        tables = {0x1100: [0x2000], 0x2100: [0x3000, 0x3100, 0x3200]}

        with patch.object(
            fh6_probe,
            "read_group_pointer_table",
            side_effect=lambda _pid, table, _count: tables[table],
        ), patch.object(
            fh6_probe,
            "read_calibrated_group_vector",
            side_effect=lambda _pid, _profile, address, _vtables, **_kwargs: child if address == 0x2000 else None,
        ), patch.object(
            fh6_probe,
            "export_layer_pointer_ok",
            side_effect=lambda _pid, address, _profile: address in {0x3000, 0x3100, 0x3200},
        ), patch.object(
            fh6_probe,
            "score_layer_pointer",
            return_value=(5, ["layer"]),
        ):
            flat = fh6_probe.flatten_calibrated_group(
                99,
                fh6_probe.get_profile("fh6"),
                root,
                {0xAA},
                3,
                writable_contains=lambda _address, _size=1: True,
            )

        target = fh6_probe.flattened_import_target(flat, 3)
        self.assertEqual(3, flat["shape_count"])
        self.assertEqual(2, flat["group_count"])
        self.assertEqual(0x2000, target["import_group_address"])
        self.assertEqual(0x2100, target["import_table_address"])
        self.assertNotEqual(root["table_address"], target["import_table_address"])

    def test_fast_import_uses_dedicated_leaf_addresses(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                return write_engine_report(
                    command,
                    status="located",
                    selected={
                        "group_address": 0x10000,
                        "table_address": 0x11000,
                        "flattened_from_groups": True,
                        "import_group_address": 0x20000,
                        "import_table_address": 0x21000,
                        "import_target_verified": True,
                        "locator": "rtti_allocator_exact",
                    },
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                group, table, _report = transfer_bridge.locate_universal_template(
                    "fh6", 123, 3, run_dir, "import-template"
                )

        self.assertEqual("0x20000", group)
        self.assertEqual("0x21000", table)

    def test_header_states_fail_closed(self):
        self.assertEqual("clear", classify_group_header(policy_header(0)))
        self.assertEqual("clear", classify_group_header(policy_header(0x20)))
        self.assertEqual("restricted", classify_group_header(policy_header(0x21)))
        self.assertEqual("unknown", classify_group_header(policy_header(0x30)))
        self.assertEqual("unknown", classify_group_header(policy_header(0x31)))
        self.assertEqual(
            "clear",
            classify_group_header(policy_header(0x30), allow_transformed_child_state=True),
        )
        self.assertEqual(
            "restricted",
            classify_group_header(policy_header(0x31), allow_transformed_child_state=True),
        )
        for state in (0x60, 0x70):
            self.assertEqual(
                "clear",
                classify_group_header(policy_header(state), allow_transformed_child_state=True),
            )
        for state in (0x61, 0x71):
            self.assertEqual(
                "restricted",
                classify_group_header(policy_header(state), allow_transformed_child_state=True),
            )
        self.assertEqual("unknown", classify_group_header(policy_header(0x10)))
        for state in (0x10, 0x40, 0x50, 0x22, 0x72):
            self.assertEqual(
                "unknown",
                classify_group_header(policy_header(state), allow_transformed_child_state=True),
            )
        self.assertEqual("unknown", classify_group_header(policy_header(0x22)))
        self.assertEqual("unknown", classify_group_header(policy_header(0x7F)))
        self.assertEqual("unknown", classify_group_header(b"short"))

    def test_fm8_uses_its_own_live_ownership_field(self):
        self.assertGreater(minimum_header_size("fm"), MIN_HEADER_SIZE)
        self.assertEqual("clear", classify_group_header(policy_header(0x20, game="fm"), game="fm"))
        self.assertEqual("restricted", classify_group_header(policy_header(0x21, game="fm"), game="fm"))
        self.assertEqual("unknown", classify_group_header(policy_header(0x21), game="fm"))

        headers = {
            0x1000: policy_header(0, game="fm"),
            0x2000: policy_header(0x21, game="fm"),
        }
        children = {0x1000: [0x2000], 0x2000: []}
        result = assess_group_tree(
            0x1000,
            headers.__getitem__,
            lambda group: children[group],
            game="fm",
        )
        self.assertFalse(result.allowed)
        self.assertEqual("restricted", result.status)

    def test_fm8_dynamic_rtti_prioritizes_the_root_arena(self):
        profile = fh6_probe.get_profile("fm")
        candidate = {"group_address": 0x81000000, "score": 10}
        with patch.object(
            fh6_probe,
            "locate_clivery_group_rtti",
            return_value={"source": "pattern_scan", "vtables": [0xAA]},
        ), patch.object(
            fh6_probe,
            "locate_fm8_clivery_group_by_root_arena",
            return_value=[candidate],
        ) as arena, patch.object(
            fh6_probe,
            "locate_clivery_groups_by_calibrated_count",
        ) as count_scan:
            located = fh6_probe.locate_clivery_groups_by_rtti(99, profile, 65)

        self.assertEqual([candidate], located)
        arena.assert_called_once()
        count_scan.assert_not_called()

    def test_fm8_root_arena_scan_excludes_high_memory_regions(self):
        profile = fh6_probe.get_profile("fm")
        candidate = {"group_address": 0x81000000, "score": 10}
        regions = [
            (0x80000000, 0x200000, 0, fh6_probe.MEM_PRIVATE),
            (0x10E000000, 0x200000, 0, fh6_probe.MEM_PRIVATE),
            (0x140000000, 0x200000, 0, fh6_probe.MEM_PRIVATE),
        ]
        stats = {"complete": True, "failed_regions": []}
        with patch.object(fh6_probe, "iter_regions", return_value=regions), patch.object(
            fh6_probe,
            "scan_exact_calibrated_vtables",
            return_value=([candidate], [], stats),
        ) as scan, patch.object(
            fh6_probe,
            "finish_incomplete_exact_scan",
            return_value=([candidate], []),
        ):
            located = fh6_probe.locate_fm8_clivery_group_by_root_arena(
                99,
                profile,
                65,
                {"vtables": [0xAA]},
            )

        self.assertEqual([candidate], located)
        scanned_regions = scan.call_args.args[5]
        self.assertEqual(
            [
                (0x80000000, 0x200000, 0, fh6_probe.MEM_PRIVATE),
                (0x10E000000, 0x200000, 0, fh6_probe.MEM_PRIVATE),
            ],
            scanned_regions,
        )

    def test_fm8_known_arena_miss_does_not_scan_the_entire_low_address_space(self):
        profile = fh6_probe.get_profile("fm")
        regions = [(0x80000000, 0x200000, 0, fh6_probe.MEM_PRIVATE)]
        stats = {"complete": True, "failed_regions": []}
        with patch.object(fh6_probe, "iter_regions", return_value=regions), patch.object(
            fh6_probe,
            "scan_exact_calibrated_vtables",
            return_value=([], [], stats),
        ) as scan, patch.object(
            fh6_probe,
            "finish_incomplete_exact_scan",
            return_value=([], []),
        ):
            located = fh6_probe.locate_fm8_clivery_group_by_root_arena(
                99,
                profile,
                500,
                {"vtables": [0xAA]},
            )

        self.assertEqual([], located)
        scan.assert_called_once()

    def test_fm8_discovered_window_is_merged_into_profile_cache(self):
        profile = fh6_probe.get_profile("fm")
        rtti = {"profile_id": "fm8-test-profile"}
        with patch.object(
            fh6_probe,
            "load_fm8_allocator_cache",
            return_value={"windows": [(0x80000000, 0x90000000)]},
        ), patch.object(fh6_probe, "save_fm8_allocator_cache") as save:
            fh6_probe.remember_fm8_group_window(profile, rtti, 0x10EDF1C00)

        save.assert_called_once_with(
            rtti,
            [
                (0x80000000, 0x90000000),
                (0x100000000, 0x110000000),
            ],
        )

    def test_fm8_unverified_fast_session_never_uses_research_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            calls = []

            def fake_subprocess(command, timeout=None):
                del timeout
                calls.append(command)
                return write_engine_report(
                    command,
                    status="no_match",
                    reason="No verified FM8 group matched.",
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "No verified FM8 group matched"):
                    transfer_bridge.locate_universal_template("fm", 123, 65, run_dir, "import-template")

            self.assertEqual(1, len(calls))
            self.assertFalse((run_dir / "fallback-import-template-probe.json").exists())

    def test_transformed_clear_child_is_allowed_but_transformed_restricted_child_is_blocked(self):
        children = {0x1000: [0x2000], 0x2000: []}
        clear_headers = {0x1000: policy_header(), 0x2000: policy_header(0x30)}
        unverified = assess_group_tree(
            0x1000,
            clear_headers.__getitem__,
            lambda group: children[group],
        )
        self.assertFalse(unverified.allowed)
        self.assertEqual("unknown", unverified.status)

        clear = assess_group_tree(
            0x1000,
            clear_headers.__getitem__,
            lambda group: children[group],
            allow_transformed_child_state=True,
        )
        self.assertTrue(clear.allowed)
        self.assertEqual("clear", clear.status)

        restricted_headers = {0x1000: policy_header(), 0x2000: policy_header(0x31)}
        restricted = assess_group_tree(
            0x1000,
            restricted_headers.__getitem__,
            lambda group: children[group],
            allow_transformed_child_state=True,
        )
        self.assertFalse(restricted.allowed)
        self.assertEqual("restricted", restricted.status)

    def test_fh6_nested_layout_flags_preserve_owned_and_restricted_states(self):
        children = {1: (2, 3, 4), 2: (), 3: (), 4: ()}
        clear_headers = {
            1: policy_header(),
            2: policy_header(0x30),
            3: policy_header(0x60),
            4: policy_header(0x70),
        }
        clear = assess_group_tree(
            1,
            clear_headers.__getitem__,
            children.__getitem__,
            game="fh6",
            allow_transformed_child_state=True,
        )
        self.assertTrue(clear.allowed)
        self.assertEqual(4, clear.group_count)

        for restricted_state in (0x31, 0x61, 0x71):
            headers = dict(clear_headers)
            headers[3] = policy_header(restricted_state)
            restricted = assess_group_tree(
                1,
                headers.__getitem__,
                children.__getitem__,
                game="fh6",
                allow_transformed_child_state=True,
            )
            self.assertFalse(restricted.allowed)
            self.assertEqual("restricted", restricted.status)

    def test_fh5_nested_layout_flag_preserves_owned_and_restricted_states(self):
        children = {1: (2,), 2: ()}
        clear = assess_group_tree(
            1,
            {1: policy_header(), 2: policy_header(0x30)}.__getitem__,
            children.__getitem__,
            game="fh5",
            allow_transformed_child_state=True,
        )
        self.assertTrue(clear.allowed)
        self.assertEqual("clear", clear.status)

        restricted = assess_group_tree(
            1,
            {1: policy_header(), 2: policy_header(0x31)}.__getitem__,
            children.__getitem__,
            game="fh5",
            allow_transformed_child_state=True,
        )
        self.assertFalse(restricted.allowed)
        self.assertEqual("restricted", restricted.status)

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

    def test_locator_bridge_uses_one_canonical_report_for_research_success(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            calls = []

            def fake_subprocess(command, timeout=None):
                del timeout
                calls.append(command)
                return write_engine_report(
                    command,
                    status="located",
                    selected={
                        "group_address": 0x10000,
                        "table_address": 0x20000,
                        "locator": "research_count_header",
                    },
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                group, table, report = transfer_bridge.locate_universal_template(
                    "fh6", 123, 8, run_dir, "export-template"
                )

            self.assertEqual("0x10000", group)
            self.assertEqual("0x20000", table)
            self.assertEqual(run_dir / "locator-session.json", report)
            self.assertTrue(report.exists())
            self.assertEqual(1, len(calls))
            self.assertIn("live_memory_locator", [str(item) for item in calls[0]])

    def test_fallback_locator_rejects_duplicate_vector_invalid_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                return write_engine_report(
                    command,
                    status="no_match",
                    reason="#1: vector metadata invalid",
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "vector metadata invalid"):
                    transfer_bridge.locate_universal_template(
                        "fh6", 123, 100, run_dir, "export-template"
                    )

    def test_fast_policy_refusal_is_terminal_and_never_runs_fallback_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            calls = []

            def fake_subprocess(command, timeout=None):
                del timeout
                calls.append(command)
                return write_engine_report(
                    command,
                    status="refused",
                    reason="Export refused: this vinyl contains content that is not owned by the current profile.",
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "not owned"):
                    transfer_bridge.locate_universal_template("fh6", 123, 8, run_dir, "export-template")

            self.assertEqual(1, len(calls))
            self.assertFalse((run_dir / "fallback-export-template-probe.json").exists())

    def test_authoritative_exact_no_match_never_runs_fallback_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            calls = []

            def fake_subprocess(command, timeout=None):
                del timeout
                calls.append(command)
                return write_engine_report(
                    command,
                    status="no_match",
                    reason="Exact RTTI coverage found no open 82-layer group.",
                )

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "Exact RTTI coverage"):
                    transfer_bridge.locate_universal_template(
                        "fh6", 123, 82, run_dir, "export-template"
                    )

            self.assertEqual(1, len(calls))
            self.assertFalse((run_dir / "fallback-export-template-probe.json").exists())

    def test_locator_bridge_rejects_a_report_for_another_process(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                code = write_engine_report(
                    command,
                    status="located",
                    selected={
                        "group_address": 0x10000,
                        "table_address": 0x20000,
                        "locator": "rtti_allocator_exact",
                    },
                )
                report = run_dir / "locator-session.json"
                payload = json.loads(report.read_text(encoding="utf-8"))
                payload["request"]["pid"] = 999
                report.write_text(json.dumps(payload), encoding="utf-8")
                return code

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    transfer_bridge.locate_universal_template(
                        "fh6", 123, 8, run_dir, "export-template"
                    )

    def test_locator_bridge_rejects_success_report_with_failed_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                write_engine_report(
                    command,
                    status="located",
                    selected={
                        "group_address": 0x10000,
                        "table_address": 0x20000,
                        "locator": "rtti_allocator_exact",
                    },
                )
                return 4

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "reported success but exited"):
                    transfer_bridge.locate_universal_template(
                        "fh6", 123, 8, run_dir, "export-template"
                    )

    def test_locator_bridge_rejects_non_authoritative_success(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)

            def fake_subprocess(command, timeout=None):
                del timeout
                code = write_engine_report(
                    command,
                    status="located",
                    selected={
                        "group_address": 0x10000,
                        "table_address": 0x20000,
                        "locator": "rtti_allocator_exact",
                    },
                )
                report = run_dir / "locator-session.json"
                payload = json.loads(report.read_text(encoding="utf-8"))
                payload["outcome"]["authoritative"] = False
                report.write_text(json.dumps(payload), encoding="utf-8")
                return code

            with patch.object(transfer_bridge, "run_subprocess", side_effect=fake_subprocess):
                with self.assertRaisesRegex(RuntimeError, "authoritative"):
                    transfer_bridge.locate_universal_template(
                        "fh6", 123, 8, run_dir, "export-template"
                    )


if __name__ == "__main__":
    unittest.main()
