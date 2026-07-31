from __future__ import annotations

import math
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

import fh6_probe  # noqa: E402
from game_profiles import get_profile  # noqa: E402


PROFILE = get_profile("fh6")
TABLE = 0x180000


def layer_blob(*, shape_id=101, alpha=255, mask=0, rotation=0.0):
    raw = bytearray(0x7C)
    struct.pack_into("<ff", raw, PROFILE.layer_position_offset, 12.5, -7.25)
    struct.pack_into("<ff", raw, PROFILE.layer_scale_offset, 1.25, 2.5)
    struct.pack_into("<f", raw, PROFILE.layer_rotation_offset, rotation)
    struct.pack_into("<f", raw, 0x70, 0.125)
    raw[PROFILE.layer_color_offset:PROFILE.layer_color_offset + 4] = bytes((12, 34, 56, alpha))
    raw[PROFILE.layer_mask_offset] = mask
    struct.pack_into("<H", raw, PROFILE.layer_shape_id_offset, shape_id)
    return bytes(raw)


def validate(pointers, blobs, *, writable=None):
    pointer_by_slot = {TABLE + index * 8: pointer for index, pointer in enumerate(pointers)}
    writable_addresses = {TABLE, *pointers} if writable is None else set(writable)

    def fake_pointer(_pid, address):
        if address not in pointer_by_slot:
            raise AssertionError(f"read beyond active vector: 0x{address:x}")
        return pointer_by_slot[address]

    def fake_read(_pid, address, size):
        return blobs.get(address, b"")[:size]

    with patch.object(fh6_probe, "read_pointer", side_effect=fake_pointer), patch.object(
        fh6_probe,
        "read_process_memory",
        side_effect=fake_read,
    ), patch.object(
        fh6_probe,
        "is_private_writable_address",
        side_effect=lambda _pid, address: address in writable_addresses,
    ):
        return fh6_probe.validate_table_layer_coverage(99, PROFILE, TABLE, len(pointers))


class Fh6ProbeLayerValidationTests(unittest.TestCase):
    def test_accepts_diverse_native_shape_ids_and_translucent_layers(self):
        pointers = [0x200000, 0x201000, 0x202000, 0x203000]
        blobs = {
            pointers[0]: layer_blob(shape_id=0x0069, alpha=255),
            pointers[1]: layer_blob(shape_id=0x1234, alpha=127),
            pointers[2]: layer_blob(shape_id=0xFFFF, alpha=1, mask=1),
            pointers[3]: layer_blob(shape_id=0x0000, alpha=0),
        }

        self.assertEqual(validate(pointers, blobs), (True, 4, 4))

    def test_rejects_duplicate_layer_pointers(self):
        pointer = 0x200000
        self.assertEqual(
            validate([pointer, pointer], {pointer: layer_blob()}),
            (False, 2, 1),
        )

    def test_rejects_unreadable_layer_pointer(self):
        pointers = [0x200000, 0x201000]
        blobs = {pointer: layer_blob() for pointer in pointers}
        self.assertEqual(
            validate(pointers, blobs, writable={TABLE, pointers[0]}),
            (False, 2, 1),
        )

    def test_rejects_invalid_mask_and_nonfinite_transform(self):
        pointer = 0x200000
        self.assertEqual(validate([pointer], {pointer: layer_blob(mask=2)}), (False, 1, 0))
        self.assertEqual(
            validate([pointer], {pointer: layer_blob(rotation=math.nan)}),
            (False, 1, 0),
        )

    def test_rejects_empty_layer_table(self):
        with patch.object(fh6_probe, "is_private_writable_address", return_value=True):
            self.assertEqual(
                fh6_probe.validate_table_layer_coverage(99, PROFILE, TABLE, 0),
                (False, 0, 0),
            )


if __name__ == "__main__":
    unittest.main()
