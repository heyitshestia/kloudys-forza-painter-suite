"""Scoped Windows process-memory access used by KFPS live locators.

The compatibility functions at the bottom preserve the original call surface,
but handles now belong to an explicit context instead of a module global.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import ctypes
from ctypes import wintypes
import struct
import sys

import win32process


ERROR_PARTIAL_COPY = 0x012B
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400
READ_ACCESS = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
WRITE_ACCESS = READ_ACCESS | PROCESS_VM_OPERATION | PROCESS_VM_WRITE
SIZE_T = ctypes.c_size_t
PSIZE_T = ctypes.POINTER(SIZE_T)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    SIZE_T,
    PSIZE_T,
)
kernel32.WriteProcessMemory.restype = wintypes.BOOL
kernel32.WriteProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    SIZE_T,
    PSIZE_T,
)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


class ProcessMemorySession:
    """Own one least-privilege process handle for a bounded operation."""

    def __init__(self, pid: int, *, writable: bool = False, api=None, module_enumerator=None):
        self.pid = int(pid)
        self.writable = bool(writable)
        self._api = api or kernel32
        self._module_enumerator = module_enumerator or win32process.EnumProcessModules
        self._handle = None

    @property
    def access(self) -> int:
        return WRITE_ACCESS if self.writable else READ_ACCESS

    @property
    def handle(self):
        if self._handle is None:
            raise RuntimeError("Process-memory session is not open.")
        return self._handle

    @property
    def closed(self) -> bool:
        return self._handle is None

    def open(self) -> "ProcessMemorySession":
        if self._handle is not None:
            return self
        handle = self._api.OpenProcess(self.access, False, self.pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle = handle
        return self

    def close(self) -> None:
        handle, self._handle = self._handle, None
        if handle:
            self._api.CloseHandle(handle)

    def __enter__(self) -> "ProcessMemorySession":
        return self.open()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def read(self, address: int, size: int, *, strict: bool = False) -> bytes:
        size = int(size)
        if size < 0:
            raise ValueError("Memory read size cannot be negative.")
        if size == 0:
            return b""
        buffer = (ctypes.c_char * size)()
        count = SIZE_T()
        ctypes.set_last_error(0)
        ok = self._api.ReadProcessMemory(
            self.handle,
            int(address),
            buffer,
            size,
            ctypes.byref(count),
        )
        if strict and (not ok or count.value != size):
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
            raise RuntimeError(
                f"Short process-memory read at 0x{int(address):x}: wanted {size}, got {count.value}."
            )
        return bytes(buffer[: count.value])

    def write(self, address: int, data: bytes | bytearray | memoryview) -> int:
        if not self.writable:
            raise PermissionError("This process-memory session is read-only.")
        raw = bytes(data)
        if not raw:
            return 0
        buffer = ctypes.create_string_buffer(raw)
        count = SIZE_T()
        ctypes.set_last_error(0)
        ok = self._api.WriteProcessMemory(
            self.handle,
            int(address),
            buffer,
            len(raw),
            ctypes.byref(count),
        )
        if not ok or count.value != len(raw):
            error = ctypes.get_last_error()
            if error:
                raise ctypes.WinError(error)
            raise RuntimeError(
                f"Short process-memory write at 0x{int(address):x}: wanted {len(raw)}, got {count.value}."
            )
        return int(count.value)

    def module_base(self) -> int:
        modules = self._module_enumerator(self.handle)
        if not modules:
            raise RuntimeError(f"Process {self.pid} has no enumerable modules.")
        return int(modules[0])


_ACTIVE_SESSION: ContextVar[ProcessMemorySession | None] = ContextVar(
    "kfps_active_process_memory_session",
    default=None,
)


def active_process_memory_session(pid: int | None = None) -> ProcessMemorySession | None:
    session = _ACTIVE_SESSION.get()
    if session is None or session.closed:
        return None
    if pid is not None and session.pid != int(pid):
        return None
    return session


@contextmanager
def process_memory_session(pid: int, *, writable: bool = False):
    """Bind a session for legacy pid/address helpers within this context."""

    current = active_process_memory_session(pid)
    if current is not None and (current.writable or not writable):
        yield current
        return
    with ProcessMemorySession(pid, writable=writable) as session:
        token = _ACTIVE_SESSION.set(session)
        try:
            yield session
        finally:
            _ACTIVE_SESSION.reset(token)


def _with_session(pid: int, callback, *, writable: bool = False):
    session = active_process_memory_session(pid)
    if session is not None and (session.writable or not writable):
        return callback(session)
    with ProcessMemorySession(pid, writable=writable) as temporary:
        return callback(temporary)


def is_64bit() -> bool:
    return struct.calcsize("P") == 8


def get_base_address(pid: int) -> int:
    return _with_session(pid, lambda session: session.module_base())


def read_process_memory(pid: int, address: int, size: int) -> bytes:
    return _with_session(pid, lambda session: session.read(address, size))


def write_process_memory(pid: int, address: int, buffer) -> None:
    _with_session(pid, lambda session: session.write(address, buffer), writable=True)


def scan_block(pid: int, start_address: int, block_size: int, scan_for: bytes) -> int:
    return read_process_memory(pid, start_address, block_size).find(scan_for)


def dereference_pointer(pid: int, pointer_address: int) -> int:
    address_bytes = read_process_memory(pid, pointer_address, 8)
    return int.from_bytes(address_bytes, byteorder=sys.byteorder)


def read_int(pid: int, int_address: int) -> int:
    int_bytes = read_process_memory(pid, int_address, 4)
    return int.from_bytes(int_bytes, byteorder=sys.byteorder)


def read_long(pid: int, int_address: int) -> int:
    long_bytes = read_process_memory(pid, int_address, 8)
    return int.from_bytes(long_bytes, byteorder=sys.byteorder)
