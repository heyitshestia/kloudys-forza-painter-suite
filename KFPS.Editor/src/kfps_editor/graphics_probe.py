"""Read current Windows display-device identities before Qt initialization."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re


@dataclass(frozen=True)
class Adapter:
    vendor: int | None
    device: int | None
    subsystem: int | None
    driver: str


def adapter_identity(hardware_ids, driver):
    for hardware_id in hardware_ids:
        match = re.fullmatch(
            r"PCI\\VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})&SUBSYS_([0-9A-F]{8})(?:&REV_[0-9A-F]{2})?",
            hardware_id, re.IGNORECASE)
        if match:
            return Adapter(*(int(part, 16) for part in match.groups()), driver)
    return Adapter(None, None, None, driver)


def present_adapters():
    if os.name != "nt":
        return ()
    import ctypes as c
    from ctypes import wintypes as w
    import uuid

    class GUID(c.Structure):
        _fields_ = [("a", w.DWORD), ("b", w.WORD), ("c", w.WORD), ("d", c.c_ubyte * 8)]

        @classmethod
        def parse(cls, value):
            return cls.from_buffer_copy(uuid.UUID(value).bytes_le)

    class DeviceInfo(c.Structure):
        _fields_ = [("size", w.DWORD), ("guid", GUID), ("instance", w.DWORD),
                    ("reserved", c.c_size_t)]

    class PropertyKey(c.Structure):
        _fields_ = [("guid", GUID), ("pid", w.DWORD)]

    api = c.WinDLL("setupapi", use_last_error=True)
    api.SetupDiGetClassDevsW.argtypes = [c.POINTER(GUID), w.LPCWSTR, w.HWND, w.DWORD]
    api.SetupDiGetClassDevsW.restype = w.HANDLE
    api.SetupDiEnumDeviceInfo.argtypes = [w.HANDLE, w.DWORD, c.POINTER(DeviceInfo)]
    api.SetupDiEnumDeviceInfo.restype = w.BOOL
    api.SetupDiGetDevicePropertyW.argtypes = [w.HANDLE, c.POINTER(DeviceInfo), c.POINTER(PropertyKey),
                                            c.POINTER(w.DWORD), c.c_void_p, w.DWORD,
                                            c.POINTER(w.DWORD), w.DWORD]
    api.SetupDiGetDevicePropertyW.restype = w.BOOL
    api.SetupDiDestroyDeviceInfoList.argtypes = [w.HANDLE]
    api.SetupDiDestroyDeviceInfoList.restype = w.BOOL
    display_class = GUID.parse("4d36e968-e325-11ce-bfc1-08002be10318")
    ids_key = PropertyKey(GUID.parse("a45c254e-df1c-4efd-8020-67d146a850e0"), 3)
    driver_key = PropertyKey(GUID.parse("a8b865dd-2e3d-4094-ad97-e593a70c75d6"), 3)
    devices = api.SetupDiGetClassDevsW(c.byref(display_class), None, None, 2)  # DIGCF_PRESENT
    if devices == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())

    def read_property(info, key, expected_type):
        size, kind = w.DWORD(), w.DWORD()
        ok = api.SetupDiGetDevicePropertyW(devices, c.byref(info), c.byref(key), c.byref(kind),
                                          None, 0, c.byref(size), 0)
        if not ok and c.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
            raise c.WinError(c.get_last_error())
        if not 2 <= size.value <= 32768 or size.value % 2:
            raise ValueError("Invalid device property size")
        buffer = c.create_string_buffer(size.value)
        if not api.SetupDiGetDevicePropertyW(devices, c.byref(info), c.byref(key), c.byref(kind),
                                            buffer, len(buffer), c.byref(size), 0):
            raise c.WinError(c.get_last_error())
        if kind.value != expected_type:
            raise ValueError("Unexpected device property type")
        return buffer.raw[:size.value].decode("utf-16-le").rstrip("\0")

    try:
        adapters = []
        for index in range(64):
            info = DeviceInfo()
            info.size = c.sizeof(info)
            if not api.SetupDiEnumDeviceInfo(devices, index, c.byref(info)):
                if c.get_last_error() == 259:  # ERROR_NO_MORE_ITEMS
                    return tuple(adapters)
                raise c.WinError(c.get_last_error())
            ids = read_property(info, ids_key, 0x2012).split("\0")  # STRING_LIST
            driver = read_property(info, driver_key, 0x12)  # STRING
            adapters.append(adapter_identity(ids, driver))
        raise ValueError("Too many display devices")
    finally:
        api.SetupDiDestroyDeviceInfoList(devices)
