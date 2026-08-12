from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_probe  # noqa: E402
from fh6_live_group_policy import MIN_HEADER_SIZE  # noqa: E402
from game_profiles import get_profile  # noqa: E402


def policy_header(state: int = 0) -> bytes:
    raw = bytearray(MIN_HEADER_SIZE)
    struct.pack_into("<I", raw, MIN_HEADER_SIZE - 4, state)
    return bytes(raw)


class Fh5LiveTransferTests(unittest.TestCase):
    def test_final_fh5_profile_checks_both_platform_descriptor_names(self):
        profile = get_profile("fh5")
        self.assertEqual(("ForzaHorizon5.exe",), profile.process_names)
        self.assertEqual(
            (b"21530671058802", b"12610023981480"),
            profile.fixed_rtti_descriptor_names,
        )
        self.assertEqual(
            [b"21530671058802", b"12610023981480", b".?AVCLiveryGroup@@"],
            fh6_probe.load_update_code_patterns([], profile=profile),
        )

    def test_both_fh5_fixed_descriptors_are_structurally_resolved(self):
        profile = get_profile("fh5")
        module_base = 0x140000000
        descriptor_offset = 0x200
        descriptor_match = module_base + descriptor_offset + 0x10
        info_address = module_base + 0x500
        vtable = module_base + 0x900

        def fake_scan(_pid, pattern, _region_type, **_kwargs):
            if len(pattern) == 4:
                return [info_address + 0xC]
            if len(pattern) == 8:
                return [vtable - 8]
            return []

        for descriptor_name in profile.fixed_rtti_descriptor_names:
            with self.subTest(descriptor_name=descriptor_name.decode("ascii")), patch.object(
                fh6_probe, "locate_static_clivery_group_rtti", return_value=None
            ), patch.object(fh6_probe, "get_base_address", return_value=module_base), patch.object(
                fh6_probe,
                "find_first_pattern_in_typed_regions",
                return_value=(descriptor_match, descriptor_name),
            ), patch.object(fh6_probe, "scan_typed_regions", side_effect=fake_scan), patch.object(
                fh6_probe, "read_process_memory", return_value=b"\x01"
            ):
                located = fh6_probe.locate_clivery_group_rtti(99, profile)

            self.assertEqual(descriptor_offset, located["descriptor_offset"])
            self.assertEqual([vtable], located["vtables"])
            self.assertEqual("fixed_profile_pattern", located["source"])
            self.assertEqual(descriptor_name.decode("ascii"), located["update_code"])

    def test_fh5_fixed_locator_uses_direct_scan_then_verified_fallbacks(self):
        profile = get_profile("fh5")
        rtti = {"source": "fixed_profile_pattern", "vtables": [0xAA]}
        candidate = {"score": 10}
        with patch.object(fh6_probe, "locate_clivery_group_rtti", return_value=rtti), patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_flattened", return_value=[]
        ) as direct_scan, patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_count", return_value=[]
        ) as count_scan, patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_graph", return_value=[candidate]
        ) as graph_scan:
            located = fh6_probe.locate_clivery_groups_by_rtti(99, profile, 8)

        self.assertEqual([candidate], located)
        direct_scan.assert_called_once_with(99, profile, 8, rtti)
        count_scan.assert_called_once_with(99, profile, 8, rtti)
        graph_scan.assert_called_once_with(99, profile, 8, rtti)

    def test_fh5_direct_scan_authorizes_a_complete_recursive_tree(self):
        profile = get_profile("fh5")
        rtti = {"source": "fixed_profile_pattern", "vtables": [0xAA], "update_code": "test"}
        group = 0x1000
        group_info = {
            "group_address": group,
            "count_address": group + profile.livery_count_offset,
            "table_pointer_field": group + profile.layer_table_offset,
            "table_address": 0x2000,
            "vector_count": 2,
            "capacity_count": 2,
            "current_u16": 8,
            "current_u32": 8,
            "parent_group": 0,
            "vtable": 0xAA,
        }
        access = SimpleNamespace(allowed=True, status="clear", reason="")
        flat = {"shape_count": 8, "invalid_count": 0, "group_count": 2, "max_depth": 1, "samples": []}
        with patch.object(fh6_probe, "iter_regions", return_value=[(group, 8, 0, 0)]), patch.object(
            fh6_probe, "read_region", return_value=struct.pack("<Q", 0xAA)
        ), patch.object(fh6_probe, "read_calibrated_group_vector", return_value=group_info), patch.object(
            fh6_probe, "assess_calibrated_group_access", return_value=access
        ), patch.object(fh6_probe, "flatten_calibrated_group", return_value=flat):
            located = fh6_probe.locate_clivery_groups_by_calibrated_flattened(99, profile, 8, rtti)

        self.assertEqual(1, len(located))
        self.assertTrue(located[0]["flattened_from_groups"])
        self.assertTrue(located[0]["export_access_verified"])
        self.assertEqual("rtti_direct_recursive", located[0]["count_kind"])

    def test_fh5_direct_scan_rejects_a_restricted_tree_before_flattening(self):
        profile = get_profile("fh5")
        rtti = {"source": "fixed_profile_pattern", "vtables": [0xAA]}
        group = 0x1000
        group_info = {
            "group_address": group,
            "current_u16": 8,
            "parent_group": 0,
        }
        access = SimpleNamespace(allowed=False, status="restricted", reason="Export refused")
        with patch.object(fh6_probe, "iter_regions", return_value=[(group, 8, 0, 0)]), patch.object(
            fh6_probe, "read_region", return_value=struct.pack("<Q", 0xAA)
        ), patch.object(fh6_probe, "read_calibrated_group_vector", return_value=group_info), patch.object(
            fh6_probe, "assess_calibrated_group_access", return_value=access
        ), patch.object(fh6_probe, "flatten_calibrated_group") as flatten:
            with self.assertRaises(fh6_probe.LocatorRefused):
                fh6_probe.locate_clivery_groups_by_calibrated_flattened(99, profile, 8, rtti)

        flatten.assert_not_called()

    def test_fh5_nested_restricted_group_fails_closed(self):
        profile = get_profile("fh5")
        root = 0x1000
        child = 0x2000
        infos = {
            root: {"group_address": root, "table_address": 0x1100, "vector_count": 1, "parent_group": 0},
            child: {"group_address": child, "table_address": 0x2100, "vector_count": 1, "parent_group": root},
        }

        def read_memory(_pid, address, _size):
            return policy_header(0x21 if address == child else 0)

        def read_table(_pid, table, _count):
            return [child] if table == 0x1100 else [0x3000]

        with patch.object(fh6_probe, "read_process_memory", side_effect=read_memory), patch.object(
            fh6_probe,
            "read_calibrated_group_vector",
            side_effect=lambda _pid, _profile, address, _vtables, max_vector_count=3000: infos.get(address),
        ), patch.object(fh6_probe, "read_group_pointer_table", side_effect=read_table):
            result = fh6_probe.assess_calibrated_group_access(99, profile, infos[root], [0xAA])

        self.assertFalse(result.allowed)
        self.assertEqual("restricted", result.status)
        self.assertEqual(2, result.group_count)


if __name__ == "__main__":
    unittest.main()
