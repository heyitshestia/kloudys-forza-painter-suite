"""Shared application leases keep the exclusive updater out while windows run."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def updater_state_root(app_root: Path) -> Path:
    root = app_root.resolve()
    if root.name.lower() == "kloudysfh6painter":
        root = root.parent
    identity = root.as_posix()
    if os.name == "nt":
        identity = identity.lower()
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(os.environ["LOCALAPPDATA"]) / "KloudysFH6Painter" / "updater" / "installations" / digest


def acquire_update_guard(state_root: Path):
    # Use only the standard library: startup needs this lease before importing
    # any third-party DLL whose baseline has not yet been verified.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    class FileInfo(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                    ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("sizeHigh", wintypes.DWORD),
                    ("sizeLow", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("indexHigh", wintypes.DWORD), ("indexLow", wintypes.DWORD)]
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    state_root.mkdir(parents=True, exist_ok=True)
    # Readers can coexist, but cannot share with the updater's read/write,
    # share-none handle. Do not share writes/deletion or truncate this file.
    handle = kernel.CreateFileW(str(state_root / "updater.lock"), 0x80000000, 1, None, 4, 0x00200080, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code in (32, 33):
            error = RuntimeError("The updater or an older KFPS window holds this installation. Finish the update or close the older window and try again.")
            error.winerror = code
            raise error
        raise ctypes.WinError(code)
    class Lease:
        def __init__(self, value): self.value = value
        def Close(self):
            if self.value is not None:
                kernel.CloseHandle(self.value)
                self.value = None
    lease = Lease(handle)
    try:
        info = FileInfo()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & (0x400 | 0x10) or info.links != 1:
            raise RuntimeError("The updater lock is not a regular, single-link file.")
        return lease
    except Exception:
        lease.Close()
        raise
