"""Keep an installation unchanged while its independent editor is open."""
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
    handle = kernel.CreateFileW(str(state_root / "updater.lock"), 0xC0000000, 0, None, 4, 0x00200080, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code in (32, 33):
            raise RuntimeError("KFPS is updating or the editor is already open. Finish the current operation before opening the editor.")
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
