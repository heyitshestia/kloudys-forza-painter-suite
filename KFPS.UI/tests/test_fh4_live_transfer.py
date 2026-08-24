from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_probe  # noqa: E402
import fh6_export_typecode_json  # noqa: E402
import fh6_import_typecode_json  # noqa: E402
from game_profiles import get_profile  # noqa: E402
sys.path.insert(0, str(ROOT / "KFPS.UI" / "bridges"))
import transfer_bridge  # noqa: E402


class Fh4LiveTransferTests(unittest.TestCase):
    def test_final_fh4_profile_has_verified_static_rtti(self):
        profile = get_profile("fh4")
        self.assertEqual(("ForzaHorizon4.exe",), profile.process_names)
        self.assertEqual(0x098DEE00, profile.static_module_size)
        self.assertEqual(0x07C820C0, profile.static_rtti_descriptor_offset)
        self.assertEqual((0x072A31D8,), profile.static_rtti_vtable_offsets)
        self.assertIn("1.478.564.2", profile.static_build)
        self.assertEqual(0x0066, profile.import_template_shape_word)

    def test_static_rtti_requires_pe_descriptor_and_col_agreement(self):
        profile = get_profile("fh4")
        module_base = 0x140000000
        descriptor = module_base + profile.static_rtti_descriptor_offset
        vtable = module_base + profile.static_rtti_vtable_offsets[0]
        locator = module_base + 0x02000000

        def fake_memory(_pid, address, size):
            if address == descriptor + 0x10:
                return profile.static_rtti_descriptor_name[:size]
            return b"\x00" * size

        def fake_u32(_pid, address):
            if address == locator:
                return 1
            if address == locator + 0xC:
                return profile.static_rtti_descriptor_offset
            return 0

        with patch.object(fh6_probe, "get_base_address", return_value=module_base), patch.object(
            fh6_probe, "read_pe_image_size", return_value=profile.static_module_size
        ), patch.object(fh6_probe, "read_process_memory", side_effect=fake_memory), patch.object(
            fh6_probe, "read_u64", return_value=locator
        ), patch.object(fh6_probe, "read_u32", side_effect=fake_u32):
            located = fh6_probe.locate_static_clivery_group_rtti(99, profile)

        self.assertEqual("static_profile", located["source"])
        self.assertEqual([vtable], located["vtables"])

    def test_static_rtti_rejects_an_unknown_fh4_executable(self):
        profile = get_profile("fh4")
        with patch.object(fh6_probe, "get_base_address", return_value=0x140000000), patch.object(
            fh6_probe, "read_pe_image_size", return_value=profile.static_module_size + 0x1000
        ), patch.object(fh6_probe, "read_process_memory") as reader:
            self.assertIsNone(fh6_probe.locate_static_clivery_group_rtti(99, profile))
        reader.assert_not_called()

    def test_static_locator_uses_recursive_root_scan_before_count_and_graph_fallbacks(self):
        profile = get_profile("fh4")
        rtti = {"source": "static_profile", "vtables": [0xAA]}
        candidate = {"score": 10}
        with patch.object(fh6_probe, "locate_clivery_group_rtti", return_value=rtti), patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_flattened", return_value=[candidate]
        ) as direct_scan, patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_count"
        ) as count_scan, patch.object(
            fh6_probe, "locate_clivery_groups_by_calibrated_graph"
        ) as graph_scan:
            located = fh6_probe.locate_clivery_groups_by_rtti(99, profile, 3000)

        self.assertEqual([candidate], located)
        direct_scan.assert_called_once_with(99, profile, 3000, rtti)
        count_scan.assert_not_called()
        graph_scan.assert_not_called()

    def test_fh4_import_requires_a_mostly_plain_circle_template(self):
        valid, detail = transfer_bridge.session_matches_import_template(
            {"shape_word_counts": {"102": 3000}}, "fh4", 3000
        )
        self.assertTrue(valid)
        self.assertIn("3000/3000", detail)

        valid, detail = transfer_bridge.session_matches_import_template(
            {"shape_word_counts": {"102": 2000}}, "fh4", 3000
        )
        self.assertFalse(valid)
        self.assertIn("2000/3000", detail)

    def test_other_games_keep_their_existing_template_policy(self):
        self.assertEqual((True, ""), transfer_bridge.session_matches_import_template({}, "fh5", 3000))

    def test_fh4_native_words_normalize_for_every_live_target(self):
        words = (123, 101, 117)
        payload = {
            "format": "fh6_typecode_json_export_v1",
            "source": {"game": "fh4"},
            "shapes": [
                {
                    "type": 0x100000 + word,
                    "type_word": word,
                    "data": [index * 10.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0],
                    "color": [20, 40, 60, 255],
                    "mask": False,
                }
                for index, word in enumerate(words)
            ],
        }
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "fh4-native.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            for game in ("fh4", "fh5", "fh6", "fm"):
                with self.subTest(game=game):
                    shapes, skipped = fh6_import_typecode_json.load_shapes(
                        source,
                        allow_unknown_low_byte=True,
                        target_game=game,
                    )
                    self.assertEqual([], skipped)
                    self.assertEqual(list(words), [shape["shape_word"] for shape in shapes])

    def test_fh4_exports_add_portable_resource_identity(self):
        for word, expected_index in ((101, 1), (117, 17), (123, 23)):
            with self.subTest(word=word):
                shape = {"type": 0x100000 + word, "type_word": word}
                layer = {}
                self.assertTrue(fh6_export_typecode_json.annotate_canonical_export_resource(shape, layer))
                self.assertEqual("Primitives", shape["resource_family"])
                self.assertEqual(expected_index, shape["resource_index"])
                self.assertEqual(shape["resource_family"], layer["resource_family"])


if __name__ == "__main__":
    unittest.main()
