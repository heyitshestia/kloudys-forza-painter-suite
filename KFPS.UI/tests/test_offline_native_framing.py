"""Native traversal checks independent of the permissive recovery decoder.

The grammar is checked against a local game-saved grouped FH6 vinyl. These tests
contain only synthetic shapes and format constants, not the private save/artwork.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.cgroup.vinyl_document import encode_vinyl_document


def read_native_tree(payload):
    """Walk every declared record without byte-skipping or inferred group closes."""
    if payload[:12] != b"gyvl\x01\x00\x00\x00\x00\x00\x00\x00":
        raise ValueError("Invalid standalone vinyl preamble")
    pos = 12

    def take(size):
        nonlocal pos
        result = payload[pos:pos + size]
        if len(result) != size:
            raise ValueError(f"Truncated native record at {pos}")
        pos += size
        return result

    def expect(value, label):
        offset = pos
        if take(1)[0] != value:
            raise ValueError(f"Missing {label} at {offset}")

    def group(depth=0):
        if depth > 64:
            raise ValueError("Excessive group nesting")
        expect(3, "group transform")
        transform = struct.unpack("<ffff", take(16))
        marker = take(1)[0]
        if marker & ~0x40 == 0x30:
            take(4)  # Signed Y-scale extension replaces the counted-group lead.
        elif marker not in (0x20, 0x60):
            raise ValueError(f"Invalid group header at {pos - 1}")
        count, blocks = struct.unpack("<HH", take(4))
        if not count or blocks != (count + 7) // 8:
            raise ValueError("Invalid group child count/bitmap")
        if take(2) != b"\x00\x00":
            raise ValueError("Unknown group control bytes")
        bitmap = take(blocks)
        children = []
        for index in range(count):
            if bitmap[index // 8] & (1 << (index % 8)):
                children.append(group(depth + 1))
            else:
                expect(2, "shape record")
                record = take(30)
                mask = take(1)[0]
                if mask not in (0, 1):
                    raise ValueError(f"Invalid trailing shape flag at {pos - 1}")
                children.append({"record": record, "mask": mask})
        expect(1, "group close")
        return {"transform": transform, "children": children, "marker": marker}

    root = group()
    if pos != len(payload):
        raise ValueError(f"Unexpected bytes after root close at {pos}")
    return root


def square(x, path):
    return {"type": 1048677, "data": [x, 0, 1, 1, 0, 0, 0],
            "color": [255, 0, 0, 255],
            "editor_group_path": [{"id": key, "name": key} for key in path]}


class OfflineNativeFramingTests(unittest.TestCase):
    def test_two_studio_groups_have_native_frames_and_closes(self):
        shapes = [square(0, ("A",)), square(10, ("A",)),
                  square(20, ("B",)), square(30, ("B",))]
        # Complete byte layout: transform -> group header -> children -> close.
        transform = bytes.fromhex("03 00000000 00000000 0000803f 00000000")
        group_header = bytes.fromhex("20 0200 0100 0000 00")

        def record(x):
            return b"\x02\x65\x00" + struct.pack("<ffffff", 0, x, 0, 1, 1, 0) + b"\x00\x00\xff\xff\x00"

        expected = (b"gyvl\x01\x00\x00\x00\x00\x00\x00\x00" + transform
                    + bytes.fromhex("20 0200 0100 0000 03")
                    + transform + group_header + record(0) + record(10) + b"\x01"
                    + transform + group_header + record(20) + record(30) + b"\x01\x01")
        for game in ("fh4", "fh5", "fh6", "fm8"):
            with self.subTest(game=game):
                payload, _ = encode_vinyl_document({"shapes": shapes}, game)
                self.assertEqual(expected, payload)
                root = read_native_tree(payload)
                self.assertEqual([2, 2], [len(c["children"]) for c in root["children"]])

    def test_nested_and_mixed_siblings_have_explicit_boundaries(self):
        shapes = [square(0, ()), square(10, ("A", "B")), square(20, ("A", "B")),
                  square(30, ("A",)), square(40, ()), square(50, ("C",)), square(60, ("C",))]
        payload, _ = encode_vinyl_document({"shapes": shapes})
        root = read_native_tree(payload)
        self.assertEqual(4, len(root["children"]))
        self.assertEqual(2, len(root["children"][1]["children"]))

    def test_masks_deep_groups_and_large_bitmaps_are_framed(self):
        for game in ("fh4", "fh5", "fh6", "fm8"):
            cases = [[square(i, ("A",)) for i in range(3000)],
                     [square(i, (f"G{i}",)) for i in range(3000)],
                     [square(i, tuple(f"G{d}" for d in range(64))) for i in range(2)]]
            for shapes in cases:
                with self.subTest(game=game, shapes=len(shapes)):
                    payload, _ = encode_vinyl_document({"shapes": shapes}, game)
                    read_native_tree(payload)
            masked = [square(i, ("A",)) for i in range(4)]
            for index in (1, 3):
                masked[index]["mask"] = True
                masked[index]["data"][6] = 1
                masked[index]["color"][3] = 0
            payload, _ = encode_vinyl_document({"shapes": masked}, game)
            root = read_native_tree(payload)
            children = root["children"][0]["children"]
            self.assertEqual([0, 1, 0, 1], [c.get("mask", c.get("children", [{}])[0].get("mask"))
                                           for c in children])

    def test_checker_rejects_missing_frames_even_if_recovery_decoder_accepts(self):
        from tools.cgroup.forza_source_decoder import cgroup_to_layers
        shapes = [square(i, ("A" if i < 2 else "B",)) for i in range(4)]
        payload, _ = encode_vinyl_document({"shapes": shapes})
        missing_transform = payload[:37] + payload[54:]
        recovered, report = cgroup_to_layers(missing_transform)
        self.assertEqual(4, len(recovered))
        self.assertEqual([], report["warnings"])
        for malformed in (missing_transform, payload[:-1], payload + b"\x00"):
            with self.assertRaises(ValueError):
                read_native_tree(malformed)

    def test_inherited_masks_and_following_unmasked_shape_have_exact_flags(self):
        shapes = [square(i, ("A", "B" if i < 2 else "C")) for i in range(4)]
        for index, item in enumerate(shapes):
            item["mask"] = True
            item["data"][6] = 1
            item["color"][3] = 0 if index % 2 else 255
        shapes.append(square(4, ()))
        for game in ("fh4", "fh5", "fh6", "fm8"):
            payload, _ = encode_vinyl_document({"shapes": shapes}, game)
            root = read_native_tree(payload)
            parent, following = root["children"]
            self.assertEqual(0x60, parent["marker"])
            self.assertEqual([1, 1, 1, 1], [leaf["mask"] for child in parent["children"]
                                           for leaf in child["children"]])
            self.assertEqual(0, following["mask"])


if __name__ == "__main__":
    unittest.main()
