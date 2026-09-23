from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.cgroup.forza_source_decoder import (
    build_livery_sections,
    extract_livery_payload,
    inspect_clivery_privacy,
)


def shape_record() -> bytes:
    return b"\x00\x02" + struct.pack("<H6f4B", 132, 0, 0, 0, 1, 1, 0, 255, 255, 255, 255)


def group_record(*, protected: bool = False, wide: bool = True) -> bytes:
    count = struct.pack("<HH", 25, 4) if wide else struct.pack("<HB", 25, 4)
    return (b"" if protected else b"\x20") + count + bytes(6) + shape_record() * 25


def transform_record(scale_bits=0x3CF5C361, *, extended=True, optional_scale=False,
                     marker_end=3) -> bytes:
    marker = bytes.fromhex("00 02 00 01 00 00 00") + bytes([marker_end]) if extended else b"\x01"
    scale = struct.unpack("<f", struct.pack("<I", scale_bits))[0]
    result = marker + struct.pack("<4f", 16, -0.25, scale, 1)
    return result + (b"\x30" + struct.pack("<f", -0.04) if optional_scale else b"")


def protected_record(*, extended=True, wide=True, trailer_lead=0x21,
                     optional_scale=False) -> tuple[bytes, int]:
    transform = transform_record(extended=extended, optional_scale=optional_scale)
    trailer = bytes([trailer_lead]) + bytes.fromhex("01 02 03 04 00 00 09 00")
    if trailer_lead & 0x10:
        trailer += struct.pack("<f", -0.5)
    return transform + trailer + group_record(protected=True, wide=wide), len(transform)


def livery_payload(body: bytes, count: int = 25, *, state: int = 0) -> bytes:
    header = bytearray(0x40)
    header[:4] = b"vlrc"
    struct.pack_into("<I", header, 4, 1)
    struct.pack_into("<I", header, 8, state)
    struct.pack_into("<I", header, 16, 4267)
    return (bytes(header) + b"gyvl" + bytes(0x11) + body + bytes(18 + 23 * 10)
            + b"yrvl" + struct.pack("<11I", count, *([0] * 10)))


class LiveryPrivacyBoundaryTests(unittest.TestCase):
    def test_scale_float_bytes_are_not_protected_wrappers(self):
        for sign in (0, 0x80000000):
            for low_byte in (0x21, 0x31, 0x61, 0x71):
                for marker_end in (1, 3):
                    for optional_scale in (False, True):
                        with self.subTest(sign=sign, low_byte=low_byte,
                                          marker=marker_end, scale=optional_scale):
                            transform = transform_record(0x3CF5C300 | sign | low_byte,
                                                         marker_end=marker_end,
                                                         optional_scale=optional_scale)
                            payload = livery_payload(transform + group_record())
                            body, counts, _ = extract_livery_payload(payload)
                            layers, warnings = build_livery_sections(body, counts)
                            self.assertEqual(25, len(layers))
                            self.assertEqual([], warnings)
                            self.assertFalse(inspect_clivery_privacy(payload)["contains_foreign_groups"])

    def test_real_wrappers_after_transforms_remain_detected(self):
        for extended in (False, True):
            for wide in (False, True):
                for lead in (0x21, 0x31, 0x61, 0x71):
                    for optional_scale in (False, True):
                        with self.subTest(extended=extended, wide=wide, lead=lead,
                                          scale=optional_scale):
                            record, offset = protected_record(extended=extended, wide=wide,
                                                              trailer_lead=lead,
                                                              optional_scale=optional_scale)
                            privacy = inspect_clivery_privacy(livery_payload(record))
                            self.assertTrue(privacy["contains_foreign_groups"])
                            self.assertIn(offset, privacy["protected_group_offsets"])

    def test_nested_protected_child_remains_detected(self):
        child, offset = protected_record()
        # One group child, with an explicit bitmap entry.
        parent = b"\x20" + struct.pack("<HH", 1, 1) + b"\x00\x00\x01"
        privacy = inspect_clivery_privacy(livery_payload(parent + child))
        self.assertIn(len(parent) + offset, privacy["protected_group_offsets"])

    def test_normal_record_does_not_hide_later_protected_record(self):
        normal = transform_record() + group_record()
        protected, offset = protected_record(wide=False)
        privacy = inspect_clivery_privacy(livery_payload(normal + protected, 50))
        self.assertIn(len(normal) + offset, privacy["protected_group_offsets"])
        self.assertNotIn(16, privacy["protected_group_offsets"])

    def test_unowned_source_is_still_unowned(self):
        payload = livery_payload(transform_record() + group_record(), state=1)
        self.assertFalse(inspect_clivery_privacy(payload)["source_owned"])

    def test_truncated_extended_transform_does_not_crash(self):
        record = transform_record() + group_record()
        for length in range(1, 40):
            with self.subTest(length=length):
                inspect_clivery_privacy(livery_payload(record[:length]))


if __name__ == "__main__":
    unittest.main()
