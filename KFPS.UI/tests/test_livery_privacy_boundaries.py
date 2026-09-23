from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.cgroup.forza_source_decoder import (
    build_livery_sections,
    extract_livery_payload,
    inspect_clivery_privacy,
)

TRANSFORM_MARKERS = (b"\x00", b"\x01", b"\x00\x01", b"\x00\x01\x01",
                     bytes.fromhex("00 02 00 01 00 00 00 01"),
                     bytes.fromhex("00 02 00 01 00 00 00 03"))


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
    def test_all_transform_markers_preserve_numeric_boundaries(self):
        for marker in TRANSFORM_MARKERS:
            for sign in (0, 0x80000000):
                for low_byte in (0x21, 0x31, 0x61, 0x71):
                    for optional_scale in (False, True):
                        with self.subTest(marker=marker.hex(), sign=sign,
                                          low_byte=low_byte, optional_scale=optional_scale):
                            scale = struct.unpack("<f", struct.pack("<I", 0x3CF5C300 | sign | low_byte))[0]
                            transform = marker + struct.pack("<4f", 10, -57, scale, 0)
                            if optional_scale:
                                transform += b"\x30" + struct.pack("<f", -scale)
                            payload = livery_payload(shape_record() + transform + group_record(), 26)
                            body, counts, _ = extract_livery_payload(payload)
                            spans = []
                            layers, warnings = build_livery_sections(body, counts, numeric_spans=spans)
                            self.assertEqual(26, len(layers))
                            self.assertEqual([], warnings)
                            self.assertIn((32 + len(marker), 48 + len(marker)), spans)
                            self.assertFalse(inspect_clivery_privacy(payload)["contains_foreign_groups"])

    def test_real_wrappers_after_every_marker_remain_detected(self):
        for marker in TRANSFORM_MARKERS:
            for wide in (False, True):
                for lead in (0x21, 0x31, 0x61, 0x71):
                    for optional_scale in (False, True):
                        with self.subTest(marker=marker.hex(), wide=wide, lead=lead,
                                          optional_scale=optional_scale):
                            transform = marker + struct.pack("<4f", 10, -57, 0.03, 0)
                            if optional_scale:
                                transform += b"\x30" + struct.pack("<f", -0.04)
                            trailer = bytes([lead]) + bytes.fromhex("01 02 03 04 00 00 09 00")
                            if lead & 0x10:
                                trailer += struct.pack("<f", -0.5)
                            prefix = shape_record() + transform
                            payload = livery_payload(prefix + trailer + group_record(protected=True, wide=wide), 26)
                            self.assertIn(len(prefix), inspect_clivery_privacy(payload)["protected_group_offsets"])

    def test_protected_group_between_ordinary_short_groups_is_not_hidden(self):
        normal = b"\x00" + struct.pack("<4f", 10, -57, 0.030000390484929085, 0) + group_record()
        for wide in (False, True):
            with self.subTest(wide=wide):
                protected, offset = protected_record(extended=False, wide=wide)
                prefix = shape_record() + normal
                payload = livery_payload(prefix + protected + normal, 76)
                hits = inspect_clivery_privacy(payload)["protected_group_offsets"]
                self.assertIn(len(prefix) + offset, hits)

    def test_inline_and_markerless_numeric_payloads_are_traced(self):
        scale = 0.030000390484929085
        numeric = struct.pack("<4f", 10, -57, scale, 0)
        # A parent with one nested group. Inline transforms are consumed as
        # part of the parent header rather than as a standalone walker step.
        parents = (
            b"\x20" + struct.pack("<HH", 1, 1) + b"\x00\x00\x01" + b"\x01",
            struct.pack("<HH", 1, 1) + b"\x00\x00\x01",
        )
        for parent in parents:
            with self.subTest(parent=parent.hex()):
                payload = livery_payload(shape_record() + parent + numeric + group_record(), 26)
                body, counts, _ = extract_livery_payload(payload)
                spans = []
                layers, warnings = build_livery_sections(body, counts, numeric_spans=spans)
                self.assertEqual(26, len(layers))
                self.assertEqual([], warnings)
                self.assertIn((32 + len(parent), 48 + len(parent)), spans)
                self.assertFalse(inspect_clivery_privacy(payload)["contains_foreign_groups"])

    def test_numeric_spans_exclude_markers_and_real_trailers(self):
        protected, offset = protected_record(optional_scale=True)
        body, counts, _ = extract_livery_payload(livery_payload(protected))
        spans = []
        build_livery_sections(body, counts, numeric_spans=spans)
        self.assertIn((8, 24), spans)
        self.assertIn((25, 29), spans)
        self.assertFalse(any(start <= offset < stop for start, stop in spans))
        self.assertFalse(any(start <= 24 < stop for start, stop in spans))

    def test_shape_and_raster_payloads_are_numeric_not_group_headers(self):
        for shape_id in (132, 0x8001):
            for framed in (False, True):
                with self.subTest(shape_id=shape_id, framed=framed):
                    record = b"\x02" + struct.pack("<H6f4B", shape_id, 1, 2, 3, 1, 1, 0, 33, 49, 97, 113)
                    if framed:
                        record = b"\x00" + record
                    body, counts, _ = extract_livery_payload(livery_payload(record, 1))
                    spans = []
                    layers, warnings = build_livery_sections(body, counts, numeric_spans=spans)
                    self.assertEqual(1, len(layers))
                    self.assertEqual([], warnings)
                    self.assertEqual([(len(record) - 28, len(record))], spans)
                    self.assertFalse(inspect_clivery_privacy(livery_payload(record, 1))["contains_foreign_groups"])

    def test_nested_protected_variants_survive_numeric_range_filtering(self):
        parent = b"\x20" + struct.pack("<HH", 1, 1) + b"\x00\x00\x01"
        for depth in (1, 3):
            for extended in (False, True):
                for wide in (False, True):
                    for lead in (0x21, 0x31, 0x61, 0x71):
                        with self.subTest(depth=depth, extended=extended, wide=wide, lead=lead):
                            record, offset = protected_record(extended=extended, wide=wide, trailer_lead=lead)
                            prefix = shape_record() + parent * depth
                            privacy = inspect_clivery_privacy(livery_payload(prefix + record, 26))
                            self.assertIn(len(prefix) + offset, privacy["protected_group_offsets"])

    def test_incomplete_or_unrecognized_sections_keep_suspicious_markers(self):
        record = shape_record() + b"\x00" + struct.pack("<4f", 10, -57, 0.030000390484929085, 0) + group_record()
        for body, count in ((record, 27), (b"\xfe" * 4 + record, 26)):
            with self.subTest(count=count, length=len(body)):
                self.assertTrue(inspect_clivery_privacy(livery_payload(body, count))["contains_foreign_groups"])

    def test_artwork_parser_failure_keeps_privacy_candidates(self):
        record, offset = protected_record(wide=False)
        with patch("tools.cgroup.forza_source_decoder.build_livery_sections", side_effect=ValueError("malformed")):
            self.assertIn(offset, inspect_clivery_privacy(livery_payload(record))["protected_group_offsets"])

    def test_all_truncated_transform_formats_are_safe(self):
        for marker in TRANSFORM_MARKERS:
            record = marker + struct.pack("<4f", 10, -57, 0.030000390484929085, 0) + group_record()
            for length in range(1, len(marker) + 36):
                with self.subTest(marker=marker.hex(), length=length):
                    inspect_clivery_privacy(livery_payload(shape_record() + record[:length], 26))

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
