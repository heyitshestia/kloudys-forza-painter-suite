"""Windows file ownership. Contents describe a lease; the open handle owns it."""
from __future__ import annotations

import ctypes
from ctypes import wintypes


class FileInfo(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                ("volume", wintypes.DWORD), ("sizeHigh", wintypes.DWORD),
                ("sizeLow", wintypes.DWORD), ("links", wintypes.DWORD),
                ("indexHigh", wintypes.DWORD), ("indexLow", wintypes.DWORD)]


def kernel_api():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.WriteFile.argtypes = kernel.ReadFile.argtypes
    kernel.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetEndOfFile.argtypes = [wintypes.HANDLE]
    kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    return kernel


class FileLease:
    def __init__(self, kernel, handle):
        self.kernel, self.value = kernel, handle

    def Close(self):
        if self.value is not None:
            self.kernel.CloseHandle(self.value)
            self.value = None

    def read(self, limit=4096):
        buffer, count = ctypes.create_string_buffer(limit), wintypes.DWORD()
        if not self.kernel.ReadFile(self.value, buffer, limit, ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:count.value]

    def write(self, payload):
        count = wintypes.DWORD()
        if not self.kernel.SetFilePointerEx(self.value, 0, None, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.WriteFile(self.value, payload, len(payload), ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value != len(payload):
            raise OSError("Incomplete startup lock write.")
        if not self.kernel.SetEndOfFile(self.value) or not self.kernel.FlushFileBuffers(self.value):
            raise ctypes.WinError(ctypes.get_last_error())


def acquire_file_lease(path, *, share=0):
    kernel = kernel_api()
    path.parent.mkdir(parents=True, exist_ok=True)
    # OPEN_ALWAYS never truncates. The handle is not inheritable, and prevents
    # write/delete sharing until Close or process exit, including with legacy Qt.
    handle = kernel.CreateFileW(str(path), 0xC0000000, share, None, 4, 0x00200080, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    lease = FileLease(kernel, handle)
    try:
        info = FileInfo()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & (0x400 | 0x10) or info.links != 1:
            raise RuntimeError("The startup lock is not a regular, single-link file.")
        return lease
    except Exception:
        lease.Close()
        raise
