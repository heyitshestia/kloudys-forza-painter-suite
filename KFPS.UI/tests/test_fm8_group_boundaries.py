from __future__ import annotations

import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, default_payload_prefix, pack_shape
from tools.cgroup import forza_source_decoder as decoder


def header(groups, wide=True):
    count = len(groups)
    blocks = (count + 7) // 8
    bitmap = bytes(sum(int(value) << bit for bit, value in enumerate(groups[start:start + 8]))
                   for start in range(0, count, 8))
    sizes = struct.pack("<HH", count, blocks) if wide else struct.pack("<HB", count, blocks)
    return b"\x20" + sizes + b"\x00\x00" + bitmap


def shape(word=3513, *, legacy=False, mask_previous=False):
    item = CGroupLayer(word, 8, -12, 0.7, 1.2, 19, 0.25, (120, 80, 40, 255))
    if legacy:
        return b"\x01" + struct.pack("<Hffffff", word, 19, 8, -12, 0.7, 1.2, 0.25) + bytes((40, 80, 120, 255))
    return pack_shape(item, trailing_mask_for_previous=mask_previous)


def transform(x=32, y=-16, scale=0.15, rotation=27, sy=None):
    data = b"\x02" + struct.pack("<ffff", x, y, scale, rotation)
    return data if sy is None else data + b"\x30" + struct.pack("<f", sy)


def payload(stream, groups):
    return default_payload_prefix() + header(groups) + stream + b"\x00\x01"


def linear(data):
    _, _, sx, sy, angle, skew = data[:6]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return (c * sx, (c * skew - s) * sy, s * sx, (s * skew + c) * sy)


class FM8GroupBoundaryTests(unittest.TestCase):
    def test_nested_first_child_transform_preserves_affine_geometry(self):
        for wide in (False, True):
            for legacy in (False, True):
                for sx, sy, angle in ((0.15, 0.15, 27), (1, 1, 0), (-0.4, 0.8, 135), (1.3, -0.7, 315)):
                    with self.subTest(wide=wide, legacy=legacy, sx=sx, sy=sy, angle=angle):
                        leaf = header([False], wide) + shape(legacy=legacy)
                        parent = header([True], wide) + transform(scale=sx, rotation=angle, sy=sy) + leaf
                        layers, report = decoder.cgroup_to_layers(payload(parent, [True]), game="fm8")
                        self.assertEqual(1, len(layers))
                        self.assertEqual([], report["warnings"])
                        data = layers[0]["data"]
                        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                        self.assertAlmostEqual(32 + c * sx * 8 + s * sy * 12, data[0], places=4)
                        self.assertAlmostEqual(-16 + s * sx * 8 - c * sy * 12, data[1], places=4)
                        a, b, d, e = linear([8, -12, 0.7, 1.2, 19, 0.25])
                        expected = (c * sx * a - s * sy * d, c * sx * b - s * sy * e,
                                    s * sx * a + c * sy * d, s * sx * b + c * sy * e)
                        for expected_value, actual in zip(expected, linear(data)):
                            self.assertAlmostEqual(expected_value, actual, places=5)
                        self.assertEqual(3513, layers[0]["shape_id"])
                        self.assertEqual([120, 80, 40, 255], layers[0]["color_rgba"])
                        self.assertFalse(layers[0]["mask"])

    def test_mask_before_group_is_applied_to_direct_shape_not_next_group(self):
        for nested in (False, True):
            for mask in (False, True):
                for legacy in (False, True):
                    with self.subTest(nested=nested, mask=mask, legacy=legacy):
                        leaf = header([False]) + shape(3514, legacy=legacy)
                        body = shape() + bytes((int(mask),)) + transform() + leaf
                        if nested:
                            body = header([False, True]) + body
                        layers, report = decoder.cgroup_to_layers(payload(body, [True] if nested else [False, True]), game="fm8")
                        self.assertEqual([3513, 3514], [s["shape_id"] for s in layers])
                        self.assertEqual([mask, False], [s["mask"] for s in layers])
                        self.assertEqual([], report["warnings"])

    def test_control_before_group_does_not_mask_a_closed_groups_descendant(self):
        first = header([False]) + shape()
        second = transform() + header([False]) + shape(3514)
        layers, _ = decoder.cgroup_to_layers(payload(first + b"\x01" + second, [True, True]), game="fm8")
        self.assertEqual([False, False], [s["mask"] for s in layers])

    def test_final_mask_survives_flat_writer_for_empty_single_and_many_shapes(self):
        for count in (0, 1, 2, 40, 3000):
            for mask in (False, True):
                items = [CGroupLayer(1901, i, 0, 1, 1, 0, 0, (1, 2, 3, 255), mask=mask and i == count - 1)
                         for i in range(count)]
                for game in ("fh4", "fh5", "fh6", "fm8"):
                    with self.subTest(count=count, mask=mask, game=game):
                        layers, report = decoder.cgroup_to_layers(build_flat_payload(items), game=game)
                        self.assertEqual(count, len(layers))
                        self.assertEqual([s.mask for s in items], [s["mask"] for s in layers])
                        self.assertEqual([], report["warnings"])

    def test_nonfinite_group_transform_is_not_accepted(self):
        for field in range(4):
            for value in (float("nan"), float("inf"), -float("inf")):
                values = [32, -16, 1, 0]
                values[field] = value
                self.assertIsNone(decoder.read_transform_payload(struct.pack("<ffff", *values), 0, 16))

    def test_incomplete_and_unrecognized_records_are_reported_not_silent(self):
        complete = payload(shape() + shape(3514), [False, False])
        first_only = payload(shape(), [False, False])
        for game in ("fh4", "fh5", "fh6", "fm8"):
            with self.subTest(game=game):
                _, report = decoder.cgroup_to_layers(complete, game=game)
                self.assertEqual([], report["warnings"])
                layers, report = decoder.cgroup_to_layers(first_only, game=game)
                self.assertEqual(1, len(layers))
                self.assertEqual(1, report["incomplete_counted_groups"])
                self.assertEqual(1, report["missing_counted_children"])
                self.assertTrue(any("incomplete counted groups" in w for w in report["warnings"]))
                _, report = decoder.cgroup_to_layers(complete[:-10], game=game)
                self.assertGreater(report["unrecognized_byte_count"], 0)
                self.assertLessEqual(len(report["unrecognized_layer_data_offsets"]), 16)
                self.assertTrue(any("unrecognized layer-data bytes" in w for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
