"""Synthetic UV validation contracts; no game assets or private fixtures."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/livery-studio/src')]

from kfps_livery_lab.component_coverage import _uv_bytes, audit_document


def uv_fixture(words, *, stride=8, view_offset=0, accessor_offset=0):
    count = len(words) // 2
    packed = struct.pack(f'<{len(words)}I', *words)
    length = accessor_offset + (count - 1) * stride + 8
    binary = bytearray(b'\xff' * (view_offset + length))
    for row in range(count):
        begin = view_offset + accessor_offset + row * stride
        binary[begin:begin + 8] = packed[row * 8:row * 8 + 8]
    document = {
        'accessors': [{'bufferView': 0, 'componentType': 5126, 'type': 'VEC2',
                       'count': count, 'byteOffset': accessor_offset}],
        'bufferViews': [{'buffer': 0, 'byteOffset': view_offset, 'byteLength': length,
                         'byteStride': stride}],
    }
    return document, bytes(binary), packed


class UvValidationTests(unittest.TestCase):
    def test_finite_float_bits_are_preserved_exactly(self):
        words = (0x00000000, 0x80000000, 0x00000001, 0x80000001,
                 0x007fffff, 0x807fffff, 0x00800000, 0x80800000,
                 0x7f7fffff, 0xff7fffff, 0x3f800000, 0xbf800000)
        for word in words:
            for position in (0, 1):
                with self.subTest(word=hex(word), position=position):
                    pair = [0x3f800000, 0x3f800000]
                    pair[position] = word
                    document, binary, packed = uv_fixture(pair)
                    before = copy.deepcopy(document)
                    result = _uv_bytes(document, binary, 0, 1)
                    self.assertIs(type(result), bytes)
                    self.assertEqual(result, packed)
                    self.assertEqual(binary, packed)
                    self.assertEqual(document, before)

    def test_infinities_and_signed_quiet_and_signaling_nans_are_rejected(self):
        words = (0x7f800000, 0xff800000, 0x7fc00001, 0xffc00001,
                 0x7f800001, 0xff800001)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            for word in words:
                for position in range(6):
                    with self.subTest(word=hex(word), position=position):
                        values = [0x3f800000] * 6
                        values[position] = word
                        document, binary, _ = uv_fixture(values)
                        with self.assertRaisesRegex(ValueError, '^UV accessor contains a non-finite value\\.$'):
                            _uv_bytes(document, binary, 0, 3)

    def test_float_bytes_are_interpreted_little_endian(self):
        # These bytes mean infinity only if incorrectly read as big endian.
        document, binary, packed = uv_fixture([0x0000807f, 0x000080ff])
        self.assertEqual(packed, b'\x7f\x80\x00\x00\xff\x80\x00\x00')
        self.assertEqual(_uv_bytes(document, binary, 0, 1), packed)
        document, binary, _ = uv_fixture([0x7f800000, 0x3f800000])
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            _uv_bytes(document, binary, 0, 1)

    def test_interleaved_nonfinite_padding_and_offsets_do_not_affect_uv_bytes(self):
        for stride in (8, 12, 20):
            with self.subTest(stride=stride):
                document, binary, packed = uv_fixture(
                    [0x80000000, 1, 0x807fffff, 0x7f7fffff],
                    stride=stride, view_offset=4, accessor_offset=4)
                before = copy.deepcopy(document)
                result = _uv_bytes(document, binary, 0, 2)
                self.assertEqual(result, packed)
                self.assertEqual(document, before)
                self.assertEqual(binary[:8], b'\xff' * 8)
                invalid = bytearray(binary)
                struct.pack_into('<I', invalid, 8 + stride + 4, 0xff800000)
                with self.assertRaisesRegex(ValueError, 'non-finite'):
                    _uv_bytes(document, bytes(invalid), 0, 2)

    def test_malformed_dimensions_and_layouts_still_fail(self):
        changes = [
            ('accessors', 'count', 0), ('accessors', 'count', -1),
            ('accessors', 'count', True), ('accessors', 'count', 1.0),
            ('accessors', 'count', 4_000_001), ('accessors', 'count', 2),
            ('accessors', 'byteOffset', -4), ('accessors', 'byteOffset', 2),
            ('accessors', 'byteOffset', 4), ('accessors', 'byteOffset', False),
            ('accessors', 'componentType', 5125), ('accessors', 'type', 'VEC3'),
            ('accessors', 'normalized', True), ('accessors', 'sparse', {'count': 1}),
            ('bufferViews', 'byteStride', 4), ('bufferViews', 'byteStride', 9),
            ('bufferViews', 'byteStride', True), ('bufferViews', 'byteStride', '8'),
            ('bufferViews', 'byteOffset', -4), ('bufferViews', 'byteOffset', 2),
            ('bufferViews', 'byteOffset', True), ('bufferViews', 'byteLength', 7),
            ('bufferViews', 'byteLength', 9), ('bufferViews', 'byteLength', None),
            ('bufferViews', 'buffer', 1),
        ]
        for group, key, value in changes:
            with self.subTest(group=group, key=key, value=value):
                document, binary, _ = uv_fixture([0, 0])
                document[group][0][key] = value
                with self.assertRaises(ValueError):
                    _uv_bytes(document, binary, 0, 1)
        document, binary, _ = uv_fixture([0, 0])
        for count in (0, 2):
            with self.subTest(expected_count=count), self.assertRaisesRegex(ValueError, 'layout or vertex count'):
                _uv_bytes(document, binary, 0, count)
        with self.assertRaisesRegex(ValueError, 'layout or vertex count'):
            _uv_bytes(document, binary[:-1], 0, 1)

    def test_invalid_accessor_and_view_indices_still_fail(self):
        document, binary, _ = uv_fixture([0, 0])
        for index in (True, -1, 0.0, '0', 1):
            with self.subTest(index=index), self.assertRaises(ValueError):
                _uv_bytes(document, binary, index, 1)
        for index in (True, -1, 0.0, '0', 1):
            with self.subTest(view_index=index):
                document['accessors'][0]['bufferView'] = index
                with self.assertRaises(ValueError):
                    _uv_bytes(document, binary, 0, 1)

    def test_missing_or_wrongly_typed_structures_keep_malformed_error(self):
        for document in ({}, {'accessors': []}, {'accessors': [None]},
                         {'accessors': [{'bufferView': 0}], 'bufferViews': [None]}):
            with self.subTest(document=document), self.assertRaisesRegex(
                    ValueError, '^Malformed converted UV data\\.$'):
                _uv_bytes(document, b'\0' * 8, 0, 1)

    def test_component_audit_keeps_exact_uv_fingerprint_and_rejects_nonfinite(self):
        document, binary, packed = uv_fixture([0x80000000, 1, 0x807fffff, 0x7f7fffff], stride=12)
        digest = hashlib.sha256(packed).hexdigest()
        document['accessors'].append({'count': 2})
        document['meshes'] = [{'extras': {'kfps_role': 'paint', 'kfps_uv_sha256': {'3': digest}},
                              'primitives': [{'attributes': {'POSITION': 1, 'TEXCOORD_3': 0}}]}]
        inventory = {'parts': [], 'model_code': 'SYNTHETIC', 'manifest_sha256': '0' * 64}
        result = audit_document(inventory, document, binary)
        self.assertEqual(result['meshes'][0]['uv_channels']['3'],
                         {'sha256': digest, 'vertices': 2, 'copy_integrity': 'verified'})
        self.assertEqual(result['summary']['verified_uv_channels'], 1)
        self.assertEqual(result['summary']['uv_integrity_errors'], 0)
        invalid = bytearray(binary)
        struct.pack_into('<I', invalid, 0, 0x7fc00001)
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            audit_document(inventory, document, bytes(invalid))


if __name__ == '__main__':
    unittest.main()
