from __future__ import annotations

import copy
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.cgroup.cgroup_codec import build_flat_payload, layer_from_shape
from tools.cgroup.forza_source_decoder import cgroup_to_layers, layers_to_kfps_json_layers
from tools.cgroup.vinyl_document import encode_vinyl_document, _linear


GAMES = ("fh4", "fh5", "fh6", "fm8")


def shape(index=0, groups=(), mask=False):
    result = {"type": 0x100000 + 101 + index % 4,
              "data": [index * 2.5, -index * 1.25, -0.5, 1.25, 17.5, 0.2, int(mask)],
              "color": [20, 70, 200, 255], "mask": mask}
    if groups:
        result["editor_group_path"] = [{"id": key, "name": key} for key in groups]
        result["editor_group_id"] = groups[-1]
        result["editor_group_name"] = groups[-1]
    return result


class OfflineVinylCodecTests(unittest.TestCase):
    def check_roundtrip(self, shapes, game):
        before = copy.deepcopy(shapes)
        payload, report = encode_vinyl_document({"shapes": shapes}, target_game=game)
        layers, decoded = cgroup_to_layers(payload, game=game)
        self.assertEqual([], decoded["warnings"])
        self.assertEqual(len(shapes), len(layers))
        self.assertEqual(len(shapes), report["layers"])
        for original, actual in zip(shapes, layers):
            expected = layer_from_shape(original, 0, game)
            self.assertEqual(expected.shape_id, actual["shape_id"])
            self.assertEqual(list(expected.color_rgba), actual["color_rgba"])
            self.assertEqual(expected.mask, actual["mask"])
            x, y, sx, sy, angle, skew = original["data"][:6]
            ax, ay, asx, asy, aangle, askew = actual["data"][:6]
            for left, right in zip((x, y, *_linear(sx, sy, angle, skew)),
                                   (ax, ay, *_linear(asx, asy, aangle, askew))):
                self.assertAlmostEqual(left, right, places=4)
        self.assertEqual(before, shapes)
        return payload, layers, report

    def test_flat_output_remains_byte_compatible(self):
        for game in GAMES:
            items = [shape(i, mask=i == 8) for i in range(9)]
            raw, _, report = self.check_roundtrip(items, game)
            self.assertEqual(build_flat_payload(layer_from_shape(s, i, game) for i, s in enumerate(items)), raw)
            self.assertEqual(0, report["groups"])

    def test_verification_rejects_lost_or_changed_group_membership(self):
        items = [shape(0, ("A", "B")), shape(1, ("A", "B")), shape(2, ("A",)), shape(3)]
        for game in GAMES:
            for corruption in ("strip", "swap", "collapse"):
                def decode(payload, game):
                    layers, report = cgroup_to_layers(payload, game=game)
                    if corruption == "strip":
                        for layer in layers:
                            layer.pop("editor_group_path", None)
                    elif corruption == "swap":
                        layers[3]["editor_group_path"] = layers[0].pop("editor_group_path")
                    else:
                        for layer in layers:
                            path = layer.get("editor_group_path", [])
                            if len(path) > 1:
                                layer["editor_group_path"] = path[:-1]
                    return layers, report
                with self.subTest(game=game, corruption=corruption):
                    with mock.patch("tools.cgroup.vinyl_document.cgroup_to_layers", side_effect=decode):
                        with self.assertRaisesRegex(ValueError, "group"):
                            encode_vinyl_document({"shapes": items}, game)

    def test_nested_groups_masks_and_loose_siblings(self):
        items = [shape(0), shape(1, ("A",)), shape(2, ("A", "B"), True),
                 shape(3, ("A", "B")), shape(4, ("A",), True),
                 shape(5, ("C",), True), shape(6)]
        for game in GAMES:
            with self.subTest(game=game):
                raw, layers, report = self.check_roundtrip(items, game)
                converted, _ = layers_to_kfps_json_layers(layers, game)
                self.assertTrue(converted[1].get("editor_group_path"))
                self.assertGreater(len(converted[2]["editor_group_path"]), len(converted[1]["editor_group_path"]))
                again, second = encode_vinyl_document({"shapes": converted}, target_game=game)
                reparsed, checks = cgroup_to_layers(again, game=game)
                self.assertEqual([], checks["warnings"])
                self.assertEqual([s["mask"] for s in layers], [s["mask"] for s in reparsed])
                self.assertGreaterEqual(report["groups"], 3)
                self.assertEqual(report["groups"], second["groups"])

    def test_interleaved_groups_split_without_reordering(self):
        items = [shape(0, ("A",)), shape(1), shape(2, ("A",))]
        for game in GAMES:
            _, _, report = self.check_roundtrip(items, game)
            self.assertTrue(report["warnings"])

    def test_3000_shapes_large_direct_child_bitmap_and_many_groups(self):
        for game in GAMES:
            for grouped in (True, False):
                with self.subTest(game=game, grouped=grouped):
                    items = [shape(i, ("A",) if grouped else (f"G{i}",), i % 29 == 0) for i in range(3000)]
                    self.check_roundtrip(items, game)

    def test_invalid_inputs_fail_before_writing(self):
        invalid = [{}, {"shapes": []}, {"shapes": [None]}, {"shapes": [shape()] * 3001}]
        for field in range(6):
            for value in (math.nan, math.inf, -math.inf, "bad"):
                item = shape()
                item["data"][field] = value
                invalid.append({"shapes": [item]})
        for groups in ([{"id": "x", "name": "x"}] * 2, [{"id": "x", "name": "x"}] * 65, "bad"):
            item = shape()
            item["editor_group_path"] = groups
            invalid.append({"shapes": [item]})
        for item in invalid:
            with self.subTest(item=str(item)[:160]), self.assertRaises(ValueError):
                encode_vinyl_document(item)

    def test_conflicting_group_parent_or_name_rejected(self):
        for second in (shape(1, ("B", "A")), shape(1, ("A",))):
            if len(second["editor_group_path"]) == 1:
                second["editor_group_path"][0]["name"] = "different"
            with self.assertRaises(ValueError):
                encode_vinyl_document({"shapes": [shape(0, ("A",)), second]})

    def test_zero_alpha_mask_is_not_discarded(self):
        for game in GAMES:
            for groups in ((), ("A",)):
                mask = shape(1, groups, True)
                mask["color"][3] = 0
                self.check_roundtrip([shape(0, groups), mask], game)

    def test_maximum_supported_depth_and_native_mask_overflow(self):
        path = tuple(f"G{i}" for i in range(64))
        self.check_roundtrip([shape(0, path)], "fh6")
        with self.assertRaisesRegex(ValueError, "64-level"):
            encode_vinyl_document({"shapes": [shape(0, path), shape(1, path, True)]})

    def test_invalid_mask_values_and_conflicting_aliases_fail(self):
        for value in ("false", "true", None, [], {}, 2, -1, 0.5, math.nan, math.inf):
            for key in ("mask", "is_mask", "isMask", "embedded"):
                item = shape()
                if key == "embedded":
                    item["data"][6] = value
                else:
                    item[key] = value
                with self.subTest(value=value, key=key), self.assertRaisesRegex(ValueError, "mask"):
                    encode_vinyl_document({"shapes": [item]})
        item = shape(mask=True)
        item["is_mask"] = False
        with self.assertRaisesRegex(ValueError, "conflicting mask"):
            encode_vinyl_document({"shapes": [item]})

    def test_legacy_explicit_mask_precedence_is_preserved(self):
        for key in ("mask", "is_mask", "isMask"):
            item = shape()
            del item["mask"]
            item[key] = True
            for game in GAMES:
                self.check_roundtrip([item], game)

    def test_legacy_zero_alpha_mask_is_retained(self):
        item = {"type": 8, "data": [0, 0, 60, 40, 0], "color": [0, 0, 0, 0], "mask": True}
        for game in GAMES:
            payload, report = encode_vinyl_document({"shapes": [item]}, game)
            layers, _ = cgroup_to_layers(payload, game=game)
            self.assertEqual(1, report["layers"])
            self.assertTrue(layers[0]["mask"])
            self.assertEqual(0, layers[0]["color_rgba"][3])


if __name__ == "__main__":
    unittest.main()
