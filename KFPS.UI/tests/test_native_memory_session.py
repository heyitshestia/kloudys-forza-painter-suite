from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import native


class FakeKernel32:
    def __init__(self, memory=b"abcdefgh"):
        self.memory = bytes(memory)
        self.opens = []
        self.closes = []
        self.reads = []
        self.writes = []

    def OpenProcess(self, access, inherit, pid):
        self.opens.append((int(access), bool(inherit), int(pid)))
        return 0xCAFE + len(self.opens)

    def CloseHandle(self, handle):
        self.closes.append(int(handle))
        return 1

    def ReadProcessMemory(self, handle, address, buffer, size, count_pointer):
        raw = self.memory[: int(size)]
        ctypes.memmove(buffer, raw, len(raw))
        ctypes.cast(count_pointer, native.PSIZE_T).contents.value = len(raw)
        self.reads.append((int(handle), int(address), int(size)))
        return 1

    def WriteProcessMemory(self, handle, address, buffer, size, count_pointer):
        raw = ctypes.string_at(buffer, int(size))
        ctypes.cast(count_pointer, native.PSIZE_T).contents.value = len(raw)
        self.writes.append((int(handle), int(address), raw))
        return 1


class ProcessMemorySessionTests(unittest.TestCase):
    def test_real_read_only_session_can_read_this_test_process(self):
        marker = ctypes.create_string_buffer(b"KFPS-session-check")
        with native.ProcessMemorySession(os.getpid()) as session:
            actual = session.read(ctypes.addressof(marker), len(marker.raw), strict=True)
        self.assertEqual(marker.raw, actual)

    def test_read_only_session_uses_minimum_access_and_closes_once(self):
        api = FakeKernel32()
        with native.ProcessMemorySession(42, api=api, module_enumerator=lambda handle: [0x1234]) as session:
            self.assertEqual(b"abcd", session.read(0x1000, 4, strict=True))
            self.assertEqual(0x1234, session.module_base())
        self.assertEqual([(native.READ_ACCESS, False, 42)], api.opens)
        self.assertEqual(1, len(api.closes))

    def test_write_requires_explicit_writable_session(self):
        read_api = FakeKernel32()
        with native.ProcessMemorySession(42, api=read_api) as session:
            with self.assertRaises(PermissionError):
                session.write(0x2000, b"data")
        self.assertFalse(read_api.writes)

        write_api = FakeKernel32()
        with native.ProcessMemorySession(42, writable=True, api=write_api) as session:
            self.assertEqual(4, session.write(0x2000, b"data"))
        self.assertEqual([(native.WRITE_ACCESS, False, 42)], write_api.opens)
        self.assertEqual([(0xCAFF, 0x2000, b"data")], write_api.writes)

    def test_compatibility_reads_reuse_bound_session(self):
        api = FakeKernel32()
        real_session = native.ProcessMemorySession

        def factory(pid, *, writable=False):
            return real_session(pid, writable=writable, api=api)

        with patch.object(native, "ProcessMemorySession", side_effect=factory):
            with native.process_memory_session(77):
                self.assertEqual(b"ab", native.read_process_memory(77, 0x10, 2))
                self.assertEqual(b"abc", native.read_process_memory(77, 0x20, 3))
                self.assertIsNotNone(native.active_process_memory_session(77))
            self.assertIsNone(native.active_process_memory_session(77))
        self.assertEqual(1, len(api.opens))
        self.assertEqual(1, len(api.closes))
        self.assertEqual(2, len(api.reads))

    def test_compatibility_read_without_scope_is_still_bounded(self):
        api = FakeKernel32()
        real_session = native.ProcessMemorySession

        def factory(pid, *, writable=False):
            return real_session(pid, writable=writable, api=api)

        with patch.object(native, "ProcessMemorySession", side_effect=factory):
            native.read_process_memory(11, 0x10, 2)
            native.read_process_memory(11, 0x20, 2)
        self.assertEqual(2, len(api.opens))
        self.assertEqual(2, len(api.closes))

    def test_partial_reads_preserve_probe_compatibility(self):
        api = FakeKernel32(memory=b"xy")
        with native.ProcessMemorySession(42, api=api) as session:
            self.assertEqual(b"xy", session.read(0x1000, 8))
            with self.assertRaises(RuntimeError):
                session.read(0x1000, 8, strict=True)


if __name__ == "__main__":
    unittest.main()
