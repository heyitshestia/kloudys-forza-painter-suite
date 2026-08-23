from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import fh6_import_typecode_json as live_import  # noqa: E402


def layer_blob():
    raw = bytearray(live_import.FULL_LAYER_SIZE)
    struct.pack_into("<ff", raw, 0x18, 0.0, 0.0)
    struct.pack_into("<ff", raw, 0x28, 1.0, 1.0)
    struct.pack_into("<f", raw, 0x50, 0.0)
    struct.pack_into("<f", raw, 0x70, 0.0)
    raw[0x74:0x78] = b"\xff\xff\xff\xff"
    raw[0x78] = 0
    struct.pack_into("<H", raw, 0x7A, 102)
    return bytes(raw)


class Fh6ImportSafetyTests(unittest.TestCase):
    @staticmethod
    def shape():
        return {
            "index": 0,
            "type_code": 0x100066,
            "source_type_code": 0x100066,
            "source_shape_word": 102,
            "shape_byte": 102,
            "shape_word": 102,
            "page_byte": 0,
            "font_shape": None,
            "x": 12.0,
            "y": 24.0,
            "sx": 2.0,
            "sy": 3.0,
            "rotation": 45.0,
            "skew": 0.0,
            "extra_data": [],
            "color": [10, 20, 30, 255],
            "mask": False,
            "score": None,
        }

    def test_preflight_rejects_invalid_pointer_before_reading_layers(self):
        table = 0x180000
        raw_table = struct.pack("<QQ", 0x200000, 0x10)
        with patch.object(live_import, "read_memory", return_value=raw_table), patch.object(
            live_import, "read_layer_blob"
        ) as read_layer:
            with self.assertRaisesRegex(RuntimeError, "invalid layer pointer at slot 2"):
                live_import.preflight_layer_table(object(), table, 2)
        read_layer.assert_not_called()

    def test_main_performs_zero_writes_when_preflight_rejects_table(self):
        table = 0x180000
        raw_table = struct.pack("<QQ", 0x200000, 0x10)
        shape = self.shape()
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            argv = [
                "fh6_import_typecode_json.py",
                "--pid",
                "123",
                "--table",
                hex(table),
                "--json",
                str(temp_path / "input.json"),
                "--template-count",
                "2",
                "--backup",
                str(temp_path / "backup.json"),
                "--report",
                str(temp_path / "report.json"),
                "--write",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                live_import, "load_shapes", return_value=([shape], [])
            ), patch.object(
                live_import, "open_process", return_value=object()
            ), patch.object(
                live_import, "close_handle"
            ), patch.object(
                live_import, "read_memory", return_value=raw_table
            ), patch.object(
                live_import, "write_memory"
            ) as write_memory:
                with self.assertRaisesRegex(RuntimeError, "invalid layer pointer at slot 2"):
                    live_import.main()

        write_memory.assert_not_called()

    def test_mid_write_failure_rolls_back_completed_writes(self):
        table = 0x180000
        pointer = 0x200000
        raw_table = struct.pack("<Q", pointer)
        original = bytearray(layer_blob())
        memory = bytearray(original)
        failed_once = False

        def fake_read(_handle, address, size):
            if address == table and size == len(raw_table):
                return raw_table
            offset = address - pointer
            if 0 <= offset and offset + size <= len(memory):
                return bytes(memory[offset:offset + size])
            raise RuntimeError(f"unexpected read at 0x{address:x}")

        def fake_write(_handle, address, raw, write, *, original=None, rollback_writes=None):
            nonlocal failed_once
            if not write:
                return
            if address == pointer + 0x28 and rollback_writes is not None and not failed_once:
                failed_once = True
                raise OSError("forced write failure")
            offset = address - pointer
            memory[offset:offset + len(raw)] = raw
            if rollback_writes is not None and original is not None:
                rollback_writes.append((address, bytes(original)))

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            argv = [
                "fh6_import_typecode_json.py",
                "--pid",
                "123",
                "--table",
                hex(table),
                "--json",
                str(temp_path / "input.json"),
                "--template-count",
                "1",
                "--backup",
                str(temp_path / "backup.json"),
                "--report",
                str(temp_path / "report.json"),
                "--write",
            ]
            with patch.object(sys, "argv", argv), patch.object(
                live_import, "load_shapes", return_value=([self.shape()], [])
            ), patch.object(
                live_import, "open_process", return_value=object()
            ), patch.object(
                live_import, "close_handle"
            ), patch.object(
                live_import, "read_memory", side_effect=fake_read
            ), patch.object(
                live_import, "write_memory", side_effect=fake_write
            ):
                with self.assertRaisesRegex(RuntimeError, "all completed memory writes were rolled back"):
                    live_import.main()

            self.assertTrue((temp_path / "backup.json").is_file())
            self.assertFalse((temp_path / "report.json").exists())

        self.assertEqual(bytes(original), bytes(memory))

    def test_preflight_accepts_unique_plausible_layers_and_rechecks_table(self):
        table = 0x180000
        pointers = [0x200000, 0x201000]
        raw_table = struct.pack("<QQ", *pointers)
        with patch.object(live_import, "read_memory", return_value=raw_table), patch.object(
            live_import,
            "read_layer_blob",
            side_effect=[(layer_blob(), live_import.FULL_LAYER_SIZE)] * 2,
        ):
            actual_pointers, layers = live_import.preflight_layer_table(object(), table, 2)

        self.assertEqual(pointers, actual_pointers)
        self.assertEqual(2, len(layers))


if __name__ == "__main__":
    unittest.main()
