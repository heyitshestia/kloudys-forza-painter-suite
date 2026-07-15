#!/usr/bin/env python3
"""Read-only FH6 fast-locator calibrator for KFPS.

This tool is intentionally standalone. It tries to rediscover the fast locator
path used by the FH6 importer/exporter after game updates move addresses.
It never writes to the game process.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import math
import os
import re
import struct
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from fh6_rtti_registry import (
    DEFAULT_BRANCH,
    DEFAULT_REPOSITORY,
    PublishError,
    RegistryError,
    empty_registry,
    github_publish_readiness,
    profile_from_calibration_result,
    publish_profile_to_github,
    registry_with_profile,
    write_registry_file,
)


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
READABLE_MASK = 0xFE
RW_MASK = 0xCC
USER_MIN = 0x10000
USER_MAX = 0x7FFFFFFFFFFF

GROUP_COUNT_OFF = 0x5A
GROUP_TABLE_OFF = 0x78
GROUP_TABLE_END_OFF = 0x80
GROUP_TABLE_CAPACITY_OFF = 0x88
GROUP_HEADER_READ = 0x300
FULL_LAYER_SIZE = 0x140
MAX_FH_LAYER_COUNT = 3000

MAX_IMAGE_READ = 256 * 1024 * 1024
MAX_PRIVATE_READ = 128 * 1024 * 1024
CALIBRATOR_VERSION = "2.0.0"

LEGACY_FH5_DECIMAL_CODES = [
    21530671058802,
    12610023981480,
    545460848954,
    25340307070018,
    9414568340267,
    5222680247029,
    93707596469592,
    57943403799010,
    71476845756855,
    55924769181498,
    84967338023063,
    78370268266092,
    54627689043735,
    12129417143245,
    31671088853161,
    38208029072770,
    37606733671938,
    96580929598483,
    63445256902275,
    10720238371765,
    9534827398028,
    10730546293884,
]


class MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wintypes.LPVOID),
        ("AllocationBase", wintypes.LPVOID),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256),
        ("szExePath", wintypes.WCHAR * 260),
    ]


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
k32.CloseHandle.argtypes = (wintypes.HANDLE,)
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.ReadProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
)
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MBI),
    ctypes.c_size_t,
)
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
k32.Module32FirstW.restype = wintypes.BOOL
k32.Module32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W))
k32.Module32NextW.restype = wintypes.BOOL
k32.Module32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W))
k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
k32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)


def log(message: str) -> None:
    text = re.sub(r"0x[0-9a-fA-F]+", "<detail>", str(message))
    text = text.replace("RTTI", "locator")
    text = text.replace("rtti", "locator")
    text = text.replace("vtables", "type candidates")
    text = text.replace("vtable", "type candidate")
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def hx(value: int | None) -> str | None:
    return None if value is None else f"0x{int(value):x}"


def finite(value: float, limit: float = 100000.0) -> bool:
    return math.isfinite(value) and -limit <= value <= limit


def safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_. -]+", "_", str(text or "capture")).strip()
    return re.sub(r"\s+", "_", text)[:80] or "capture"


def open_process(pid: int, read: bool = True):
    access = PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION
    if read:
        access |= PROCESS_VM_READ
    handle = k32.OpenProcess(access, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle) -> None:
    if handle:
        k32.CloseHandle(handle)


def find_forza_pid() -> tuple[int, str | None]:
    cmd = ["tasklist", "/FI", "IMAGENAME eq forzahorizon6.exe", "/FO", "CSV", "/NH"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    rows = list(csv.reader(result.stdout.splitlines()))
    pids = []
    for row in rows:
        if len(row) >= 2 and row[0].strip('"').lower() == "forzahorizon6.exe":
            try:
                pids.append(int(row[1]))
            except ValueError:
                pass
    if not pids:
        raise RuntimeError("forzahorizon6.exe was not found. Open FH6 and the vinyl editor first.")
    if len(pids) > 1:
        log("Multiple FH6 processes found; using the first detected process.")
    pid = pids[0]
    return pid, process_image_path(pid)


def process_image_path(pid: int) -> str | None:
    handle = open_process(pid, read=False)
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        close_handle(handle)


def find_main_module(pid: int) -> dict | None:
    snap = k32.CreateToolhelp32Snapshot(0x00000008 | 0x00000010, int(pid))
    if snap == wintypes.HANDLE(-1).value:
        return None
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
        ok = k32.Module32FirstW(snap, ctypes.byref(entry))
        modules = []
        while ok:
            modules.append(
                {
                    "name": entry.szModule,
                    "path": entry.szExePath,
                    "base": ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value,
                    "size": int(entry.modBaseSize),
                }
            )
            ok = k32.Module32NextW(snap, ctypes.byref(entry))
    finally:
        close_handle(snap)
    for module in modules:
        if module["name"].lower() == "forzahorizon6.exe":
            return module
    return modules[0] if modules else None


def is_rw(protect: int) -> bool:
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & RW_MASK)


def is_readable(protect: int) -> bool:
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & READABLE_MASK)


def iter_regions(handle, region_type: int | None = None, writable_only: bool = False) -> list[dict]:
    regions = []
    addr = USER_MIN
    info = MBI()
    while addr < USER_MAX:
        if not k32.VirtualQueryEx(handle, addr, ctypes.byref(info), ctypes.sizeof(info)):
            addr += 0x10000
            continue
        base = int(info.BaseAddress)
        size = int(info.RegionSize)
        protect = int(info.Protect)
        if (
            int(info.State) == MEM_COMMIT
            and (region_type is None or int(info.Type) == region_type)
            and (is_rw(protect) if writable_only else is_readable(protect))
        ):
            regions.append(
                {
                    "base": base,
                    "end": base + size,
                    "size": size,
                    "protect": protect,
                    "type": int(info.Type),
                    "allocation_base": int(info.AllocationBase),
                }
            )
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt
    return regions


def build_contains(regions: list[dict]):
    ranges = sorted((r["base"], r["end"]) for r in regions)

    def contains(value: int, size: int = 1) -> bool:
        value = int(value)
        if not (USER_MIN <= value <= USER_MAX) or size < 1:
            return False
        lo, hi = 0, len(ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end = ranges[mid]
            if value < start:
                hi = mid - 1
            elif value + size > end:
                lo = mid + 1
            else:
                return True
        return False

    return contains


def region_for(regions: list[dict], value: int) -> dict | None:
    for region in regions:
        if region["base"] <= value < region["end"]:
            return region
    return None


def read_memory(handle, address: int, size: int) -> bytes:
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value <= 0:
        return b""
    return buf.raw[: read.value]


def read_u16(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 2)
    return struct.unpack("<H", raw)[0] if len(raw) == 2 else None


def read_u32(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 4)
    return struct.unpack("<I", raw)[0] if len(raw) == 4 else None


def read_i32(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 4)
    return struct.unpack("<i", raw)[0] if len(raw) == 4 else None


def read_u64(handle, address: int) -> int | None:
    raw = read_memory(handle, address, 8)
    return struct.unpack("<Q", raw)[0] if len(raw) == 8 else None


def read_c_string(handle, address: int, max_size: int = 256) -> str:
    raw = read_memory(handle, address, max_size)
    if not raw:
        return ""
    raw = raw.split(b"\x00", 1)[0]
    return raw.decode("ascii", "replace")


def read_layer_score(handle, contains, ptr: int) -> tuple[int, list[str]]:
    checks = []
    if not ptr or not contains(ptr, 0x7C):
        return 0, ["bad pointer"]
    raw = read_memory(handle, ptr, FULL_LAYER_SIZE)
    if len(raw) < 0x7C:
        return 0, [f"short read {len(raw)}"]
    score = 0
    px, py = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rot = struct.unpack_from("<f", raw, 0x50)[0]
    color = raw[0x74:0x78]
    shape = struct.unpack_from("<H", raw, 0x7A)[0]
    if finite(px, 2000) and finite(py, 2000):
        score += 2
        checks.append(f"pos={px:.1f},{py:.1f}")
    if finite(sx, 500) and finite(sy, 500) and (abs(sx) > 0.00001 or abs(sy) > 0.00001):
        score += 2
        checks.append(f"scale={sx:.3f},{sy:.3f}")
    if finite(rot, 1000000):
        score += 1
        checks.append(f"rot={rot:.1f}")
    if color[3] <= 255:
        score += 1
        checks.append("rgba=" + " ".join(str(b) for b in color))
    if 0 <= shape <= 2000:
        score += 1
        checks.append(f"shape={shape}")
    return score, checks


def score_table(handle, contains, table: int, count: int) -> tuple[int, list[dict]]:
    if not table or not contains(table, max(8, count * 8)):
        return 0, []
    raw = read_memory(handle, table, count * 8)
    if len(raw) != count * 8:
        return 0, []
    ptrs = struct.unpack(f"<{count}Q", raw)
    sample_count = min(count, 40)
    if count > sample_count:
        indices = sorted(set(list(range(20)) + [round(i * (count - 1) / 19) for i in range(20)]))
    else:
        indices = list(range(count))
    score = 0
    samples = []
    valid_ptrs = 0
    for index in indices:
        ptr = ptrs[index]
        layer_score, checks = read_layer_score(handle, contains, ptr)
        if layer_score > 0:
            valid_ptrs += 1
        score += layer_score
        samples.append({"index": index, "ptr": hx(ptr), "score": layer_score, "checks": checks[:6]})
    return score + valid_ptrs * 2, samples


def scan_layout_candidates(handle, rw_regions, contains, count: int, max_seconds: int = 45) -> list[dict]:
    pattern = struct.pack("<H", count)
    start_time = time.monotonic()
    candidates = []
    seen = set()
    scanned_mb = 0.0
    for idx, region in enumerate(rw_regions, start=1):
        if max_seconds and time.monotonic() - start_time > max_seconds:
            break
        raw = read_memory(handle, region["base"], min(region["size"], MAX_PRIVATE_READ))
        scanned_mb += len(raw) / (1024 * 1024)
        pos = 0
        while raw:
            hit = raw.find(pattern, pos)
            if hit < 0:
                break
            pos = hit + 1
            group = region["base"] + hit - GROUP_COUNT_OFF
            if group in seen or not contains(group, GROUP_HEADER_READ):
                continue
            seen.add(group)
            table = read_u64(handle, group + GROUP_TABLE_OFF)
            table_end = read_u64(handle, group + GROUP_TABLE_END_OFF)
            table_cap = read_u64(handle, group + GROUP_TABLE_CAPACITY_OFF)
            if not table or not table_end or not table_cap:
                continue
            if table_end != table + count * 8 or table_cap < table_end:
                continue
            if not contains(table, count * 8):
                continue
            score, samples = score_table(handle, contains, table, count)
            if score <= 0:
                continue
            vtable = read_u64(handle, group)
            candidates.append(
                {
                    "score": score,
                    "group": group,
                    "table": table,
                    "table_end": table_end,
                    "table_capacity": table_cap,
                    "vtable": vtable,
                    "samples": samples,
                }
            )
            candidates.sort(key=lambda item: item["score"], reverse=True)
            del candidates[40:]
        if idx % 300 == 0:
            log(f"layout scan {idx}/{len(rw_regions)} regions, {scanned_mb:.0f} MB, candidates={len(candidates)}")
    return candidates


def legacy_patterns() -> list[bytes]:
    patterns = [
        b".?AVCLiveryGroup@@",
        b"CLiveryGroup",
        "CLiveryGroup".encode("utf-16le"),
    ]
    for value in LEGACY_FH5_DECIMAL_CODES:
        try:
            patterns.append(int(value).to_bytes(8, "little"))
        except OverflowError:
            pass
    unique = []
    seen = set()
    for pattern in patterns:
        if pattern and pattern not in seen:
            seen.add(pattern)
            unique.append(pattern)
    return unique


def scan_image_for_patterns(handle, image_regions, patterns: list[bytes]) -> list[dict]:
    matches = []
    for region in image_regions:
        raw = read_memory(handle, region["base"], min(region["size"], MAX_IMAGE_READ))
        if not raw:
            continue
        for pattern in patterns:
            start = 0
            while True:
                pos = raw.find(pattern, start)
                if pos < 0:
                    break
                address = region["base"] + pos
                descriptor = address - 0x10 if pattern.startswith(b".?AV") or pattern in (b"CLiveryGroup",) else address
                matches.append(
                    {
                        "address": address,
                        "descriptor_guess": descriptor,
                        "pattern_hex": pattern.hex(),
                        "pattern_text": pattern.decode("ascii", "replace") if all(32 <= b < 127 for b in pattern) else None,
                    }
                )
                start = pos + 1
    return matches


def derive_rtti_from_descriptor(handle, image_contains, module_base: int, descriptor: int) -> dict | None:
    descriptor_offset = descriptor - module_base
    if not 0 <= descriptor_offset <= 0xFFFFFFFF:
        return None
    info_pattern = struct.pack("<I", descriptor_offset)
    info_addresses = []
    image_regions = getattr(derive_rtti_from_descriptor, "_image_regions", [])
    for region in image_regions:
        raw = read_memory(handle, region["base"], min(region["size"], MAX_IMAGE_READ))
        start = 0
        while raw:
            pos = raw.find(info_pattern, start)
            if pos < 0:
                break
            address = region["base"] + pos
            info = address - 0xC
            if read_memory(handle, info, 1) == b"\x01":
                info_addresses.append(info)
            start = pos + 4
    info_addresses = sorted(set(info_addresses))
    vtables = []
    for info in info_addresses:
        pattern = struct.pack("<Q", info)
        for region in image_regions:
            raw = read_memory(handle, region["base"], min(region["size"], MAX_IMAGE_READ))
            start = 0
            while raw:
                pos = raw.find(pattern, start)
                if pos < 0:
                    break
                vtables.append(region["base"] + pos + 8)
                start = pos + 8
    type_name = read_c_string(handle, descriptor + 0x10)
    return {
        "descriptor_address": descriptor,
        "descriptor_offset": descriptor_offset,
        "type_name": type_name,
        "info_addresses": sorted(set(info_addresses)),
        "vtables": sorted(set(vtables)),
    }


def derive_rtti_from_group(handle, image_contains, module_base: int, group: int, vtable: int | None = None) -> dict | None:
    vtable = vtable or read_u64(handle, group)
    if not vtable or not image_contains(vtable, 8):
        return None
    info = read_u64(handle, vtable - 8)
    if not info or not image_contains(info, 0x18):
        return None
    signature = read_u32(handle, info)
    if signature != 1:
        return None
    descriptor_rva = read_u32(handle, info + 0x0C)
    class_descriptor_rva = read_u32(handle, info + 0x10)
    self_rva = read_u32(handle, info + 0x14)
    if descriptor_rva is None:
        return None
    descriptor = module_base + descriptor_rva
    if not image_contains(descriptor, 0x20):
        return None
    direct_type_name = read_c_string(handle, descriptor + 0x10)
    hierarchy_update_code = ""
    base_class_count = None
    base_class_descriptor = None
    hierarchy_type_descriptor = None
    if class_descriptor_rva is not None and self_rva is not None:
        # ADawg's updater walks from the COL to the class hierarchy, then reads
        # the first base class TypeDescriptor. That appears to be the numeric
        # update-code string on current FH6 builds.
        base_address = info - int(self_rva)
        class_hierarchy = base_address + int(class_descriptor_rva)
        if image_contains(class_hierarchy, 0x10):
            base_class_count = read_i32(handle, class_hierarchy + 0x8)
            base_class_array_rva = read_i32(handle, class_hierarchy + 0xC)
            if base_class_array_rva is not None:
                base_class_array = base_address + int(base_class_array_rva)
                first_base_class_rva = read_i32(handle, base_class_array)
                if first_base_class_rva is not None:
                    base_class_descriptor = base_address + int(first_base_class_rva)
                    type_descriptor_rva = read_i32(handle, base_class_descriptor)
                    if type_descriptor_rva is not None:
                        hierarchy_type_descriptor = base_address + int(type_descriptor_rva)
                        if image_contains(hierarchy_type_descriptor, 0x20):
                            hierarchy_update_code = read_c_string(handle, hierarchy_type_descriptor + 0x10, 64)
    return {
        "descriptor_address": descriptor,
        "descriptor_offset": descriptor_rva,
        "type_name": hierarchy_update_code or direct_type_name,
        "direct_type_name": direct_type_name,
        "hierarchy_update_code": hierarchy_update_code,
        "info_addresses": [info],
        "vtables": [vtable],
        "class_descriptor_offset": class_descriptor_rva,
        "self_offset": self_rva,
        "base_class_count": base_class_count,
        "base_class_descriptor": base_class_descriptor,
        "hierarchy_type_descriptor": hierarchy_type_descriptor,
        "source_group": group,
    }


def save_result(out_dir: Path, result: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    result["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result["format"] = "kfps_clivery_rtti_calibration_v1"
    result["calibrator_version"] = CALIBRATOR_VERSION
    json_path = out_dir / "clivery-rtti-latest.json"
    json_path.write_text(json.dumps(result, indent=2, default=hx), encoding="utf-8")

    type_name = str(result.get("rtti", {}).get("type_name") or "")
    if type_name:
        (out_dir / "update-codes.dat").write_bytes(type_name.encode("ascii", "replace") + b"\n")

    offsets_path = out_dir / "clivery-rtti-offsets.txt"
    rtti = result.get("rtti", {})
    module_base = int(str(result["module"]["base"]), 0)
    offsets_path.write_text(
        "\n".join(
            [
                f"descriptor_offset=0x{int(rtti.get('descriptor_offset') or 0):x}",
                "vtables=" + ",".join(f"0x{int(str(v), 0) - module_base:x}" for v in rtti.get("vtables", [])),
                f"type_name={type_name}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return json_path


def build_result(pid: int, exe: str | None, module: dict, rtti: dict, source: str, candidates: list[dict] | None = None) -> dict:
    clean_rtti = dict(rtti)
    clean_rtti["descriptor_address"] = hx(clean_rtti.get("descriptor_address"))
    clean_rtti["info_addresses"] = [hx(v) for v in clean_rtti.get("info_addresses", [])]
    clean_rtti["vtables"] = [hx(v) for v in clean_rtti.get("vtables", [])]
    if clean_rtti.get("source_group") is not None:
        clean_rtti["source_group"] = hx(clean_rtti["source_group"])
    if clean_rtti.get("class_descriptor_offset") is not None:
        clean_rtti["class_descriptor_offset"] = hx(clean_rtti["class_descriptor_offset"])
    if clean_rtti.get("self_offset") is not None:
        clean_rtti["self_offset"] = hx(clean_rtti["self_offset"])
    if clean_rtti.get("base_class_descriptor") is not None:
        clean_rtti["base_class_descriptor"] = hx(clean_rtti["base_class_descriptor"])
    if clean_rtti.get("hierarchy_type_descriptor") is not None:
        clean_rtti["hierarchy_type_descriptor"] = hx(clean_rtti["hierarchy_type_descriptor"])
    return {
        "pid": pid,
        "process": {"name": "forzahorizon6.exe", "exe": exe},
        "module": {
            "name": module.get("name"),
            "path": module.get("path"),
            "base": hx(module.get("base")),
            "size": module.get("size"),
        },
        "source": source,
        "rtti": clean_rtti,
        "candidate_summary": summarize_candidates(candidates or []),
    }


def summarize_candidates(candidates: list[dict]) -> list[dict]:
    summary = []
    for index, candidate in enumerate(candidates[:10], start=1):
        summary.append(
            {
                "rank": index,
                "score": candidate.get("score"),
                "group": hx(candidate.get("group")),
                "table": hx(candidate.get("table")),
                "vtable": hx(candidate.get("vtable")),
                "samples": candidate.get("samples", [])[:4],
            }
        )
    return summary


def fast_descriptor_search(handle, image_regions, image_contains, module_base: int) -> tuple[dict | None, list[dict]]:
    derive_rtti_from_descriptor._image_regions = image_regions
    matches = scan_image_for_patterns(handle, image_regions, legacy_patterns())
    for match in matches:
        rtti = derive_rtti_from_descriptor(handle, image_contains, module_base, int(match["descriptor_guess"]))
        if not rtti:
            continue
        if rtti.get("vtables"):
            rtti["pattern_match"] = match
            return rtti, matches
    return None, matches


def rtti_identity(rtti: dict, module_base: int) -> str:
    descriptor = int(rtti.get("descriptor_address") or 0)
    vtables = [int(v) for v in rtti.get("vtables") or [] if v]
    descriptor_offset = int(rtti.get("descriptor_offset") or max(0, descriptor - module_base))
    vtable_offsets = sorted(v - module_base for v in vtables)
    primary_vtable = vtable_offsets[0] if vtable_offsets else 0
    type_name = str(rtti.get("type_name") or "")
    return f"desc=0x{descriptor_offset:x}|vt=0x{primary_vtable:x}|type={type_name}"


def scan_rtti_evidence(pid: int, module: dict, layer_count: int) -> tuple[list[dict], list[dict], int]:
    handle = open_process(pid, read=True)
    try:
        image_regions = iter_regions(handle, MEM_IMAGE, writable_only=False)
        rw_regions = iter_regions(handle, MEM_PRIVATE, writable_only=True)
        image_contains = build_contains(image_regions)
        rw_contains = build_contains(rw_regions)
        module_base = int(module["base"])

        evidence = []
        rtti, matches = fast_descriptor_search(handle, image_regions, image_contains, module_base)
        if rtti:
            evidence.append(
                {
                    "key": rtti_identity(rtti, module_base),
                    "rtti": rtti,
                    "source": "fast_descriptor_pattern",
                    "candidate": None,
                    "layer_count": layer_count,
                }
            )

        candidates = scan_layout_candidates(handle, rw_regions, rw_contains, layer_count, max_seconds=60)
        for candidate in candidates[:20]:
            rtti = derive_rtti_from_group(
                handle,
                image_contains,
                module_base,
                int(candidate["group"]),
                candidate.get("vtable"),
            )
            if not rtti:
                continue
            type_name = str(rtti.get("type_name") or "")
            rtti["confidence"] = "high" if "CLiveryGroup" in type_name else "medium"
            evidence.append(
                {
                    "key": rtti_identity(rtti, module_base),
                    "rtti": rtti,
                    "source": "live_group_candidate",
                    "candidate": candidate,
                    "layer_count": layer_count,
                }
            )
        return evidence, candidates, len(matches)
    finally:
        close_handle(handle)


def observation_summary(observations: list[dict]) -> dict:
    counts = sorted({int(item["layer_count"]) for item in observations})
    return {
        "scans": len(observations),
        "distinct_counts": counts,
        "count_changes": max(0, len(counts) - 1),
        "sources": sorted({str(item.get("source")) for item in observations}),
    }


def build_locked_result(
    pid: int,
    exe: str | None,
    module: dict,
    key: str,
    observations: list[dict],
    candidates: list[dict],
) -> dict:
    best = observations[-1]
    rtti = dict(best["rtti"])
    summary = observation_summary(observations)
    confidence = "high" if summary["scans"] >= 3 and len(summary["distinct_counts"]) >= 2 else "medium"
    if "CLiveryGroup" in str(rtti.get("type_name") or ""):
        confidence = "very_high" if confidence == "high" else "high"
    rtti["confidence"] = confidence
    result = build_result(pid, exe, module, rtti, "multi_step_count_change", candidates)
    result["lock_key"] = key
    result["lock_summary"] = summary
    result["observations"] = [
        {
            "step": index + 1,
            "layer_count": item["layer_count"],
            "source": item["source"],
            "candidate": summarize_candidates([item["candidate"]]) if item.get("candidate") else [],
        }
        for index, item in enumerate(observations)
    ]
    return result


def continuous_search(layer_count: int, sleep_seconds: int = 4) -> int:
    pid, exe = find_forza_pid()
    module = find_main_module(pid)
    if not module:
        raise RuntimeError("Could not identify the FH6 main module.")
    out_dir = Path("calibration-results") / safe_name(f"fh6_{layer_count}_{time.strftime('%Y%m%d-%H%M%S')}")
    log("Using detected FH6 process.")
    log(f"Main module: {module['name']} size={module['size']}")
    log("Press Ctrl+C to stop. The tool will save automatically when a plausible locator path is found.")

    attempt = 0
    while True:
        attempt += 1
        handle = open_process(pid, read=True)
        try:
            image_regions = iter_regions(handle, MEM_IMAGE, writable_only=False)
            rw_regions = iter_regions(handle, MEM_PRIVATE, writable_only=True)
            image_contains = build_contains(image_regions)
            rw_contains = build_contains(rw_regions)

            log(f"Attempt {attempt}: fast locator scan...")
            rtti, matches = fast_descriptor_search(handle, image_regions, image_contains, int(module["base"]))
            if rtti:
                result = build_result(pid, exe, module, rtti, "fast_descriptor_pattern")
                path = save_result(out_dir, result)
                log(f"Saved locator calibration: {path}")
                log("Calibration identity saved to file.")
                return 0
            log(f"Locator scan did not produce type candidates. Pattern hits={len(matches)}")

            log(f"Attempt {attempt}: scanning current {layer_count}-layer group candidates...")
            candidates = scan_layout_candidates(handle, rw_regions, rw_contains, layer_count, max_seconds=45)
            log(f"Layout candidates: {len(candidates)}")
            for candidate in candidates[:10]:
                rtti = derive_rtti_from_group(
                    handle,
                    image_contains,
                    int(module["base"]),
                    int(candidate["group"]),
                    candidate.get("vtable"),
                )
                if not rtti:
                    continue
                type_name = str(rtti.get("type_name") or "")
                confidence = "high" if "CLiveryGroup" in type_name else "medium"
                rtti["confidence"] = confidence
                result = build_result(pid, exe, module, rtti, f"live_{layer_count}_layer_group_{confidence}", candidates)
                path = save_result(out_dir, result)
                log(f"Saved locator calibration: {path}")
                log("Calibration identity saved to file.")
                log(f"Confidence: {confidence}")
                return 0
        finally:
            close_handle(handle)

        log(f"No locator path found yet. Confirm the {layer_count}-layer group is open; retrying in {sleep_seconds}s.")
        time.sleep(sleep_seconds)


def guided_count_change(required_scans: int = 3) -> int:
    print()
    print("Guided multi-scan mode is read-only.")
    print("Goal: scan, change layer count, scan, change layer count, scan.")
    print("Start with the known 3000-circle template open.")
    current_count = prompt_int("Current visible layer count", 3000)
    print()
    pid, exe = find_forza_pid()
    module = find_main_module(pid)
    if not module:
        raise RuntimeError("Could not identify the FH6 main module.")
    out_dir = Path("calibration-results") / safe_name(f"guided_multi_{time.strftime('%Y%m%d-%H%M%S')}")
    observations_by_key: dict[str, list[dict]] = {}
    latest_candidates: list[dict] = []
    saved_keys: set[str] = set()
    step = 0
    log("Using detected FH6 process.")
    log(f"Main module: {module['name']} size={module['size']}")

    while True:
        step += 1
        print()
        print(f"Step {step}: make sure FH6 shows {current_count} visible layer(s), then press Enter to scan.")
        print("Type Q and press Enter to stop instead.")
        command = input("> ").strip().lower()
        if command == "q":
            return 0 if saved_keys else 1

        evidence, candidates, pattern_hits = scan_rtti_evidence(pid, module, current_count)
        latest_candidates = candidates
        log(
            f"Scan {step}: layer_count={current_count}, layout_candidates={len(candidates)}, "
            f"pattern_hits={pattern_hits}, locator_hits={len(evidence)}"
        )
        for item in evidence:
            observations_by_key.setdefault(item["key"], []).append(item)

        locked = []
        for key, observations in observations_by_key.items():
            summary = observation_summary(observations)
            log(
                f"  evidence candidate: scans={summary['scans']} "
                f"counts={','.join(str(c) for c in summary['distinct_counts']) or 'none'}"
            )
            if summary["scans"] >= required_scans and len(summary["distinct_counts"]) >= 2:
                locked.append((key, observations))

        for key, observations in locked:
            result = build_locked_result(pid, exe, module, key, observations, latest_candidates)
            path = save_result(out_dir, result)
            if key in saved_keys:
                log(f"Updated locked locator with {len(observations)} confirming scan(s): {path}")
            else:
                saved_keys.add(key)
                log(f"LOCKED locator after {len(observations)} confirming scan(s): {path}")
            log(f"Confidence: {result['rtti'].get('confidence')}")

        print()
        print("Now change the vinyl layer count in FH6 by adding or deleting a few simple circles.")
        if current_count >= MAX_FH_LAYER_COUNT:
            print("You are already at 3000, so delete a few circles, for example -2, -3, or -4.")
        else:
            print("Use a small but real change, for example +2, +3, -1, or -4.")
        print("Then type the actual new visible layer count. Type Q to finish.")
        next_count = prompt_next_layer_count(current_count)
        if next_count is None:
            return 0 if saved_keys else 1
        current_count = next_count


def prompt_int(label: str, default: int) -> int:
    while True:
        value = input(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            parsed = int(value, 0)
            if 0 < parsed <= MAX_FH_LAYER_COUNT:
                return parsed
        except ValueError:
            pass
        print(f"Enter a layer count from 1 to {MAX_FH_LAYER_COUNT}.")


def prompt_next_layer_count(current_count: int) -> int | None:
    while True:
        value = input("New visible layer count after your FH6 edit, or Q to finish: ").strip()
        if value.lower() == "q":
            return None
        if not value:
            print("Blank input is ignored. Change FH6 first, then type the actual new visible layer count.")
            continue
        try:
            parsed = int(value, 0)
        except ValueError:
            print("Enter numbers only, for example 3003.")
            continue
        if parsed <= 0:
            print("Layer count must be positive.")
            continue
        if parsed > MAX_FH_LAYER_COUNT:
            print(f"FH6 cannot go above {MAX_FH_LAYER_COUNT} layers. Enter a count at or below {MAX_FH_LAYER_COUNT}.")
            continue
        if parsed == current_count:
            print("That is the same count as the last scan. Add/delete a few circles first, then enter the changed count.")
            continue
        return parsed


def suggested_next_count(current_count: int) -> int:
    if current_count >= MAX_FH_LAYER_COUNT - 1:
        return max(1, current_count - 3)
    return min(MAX_FH_LAYER_COUNT, current_count + 3)



FIXED_SIX_STEP_COUNTS = [3000, 2997, 2994, 2991, 2988, 2985]


def six_step_template_calibration(
    required_scans: int = 3,
    *,
    auto_publish: bool = True,
    dry_run_publish: bool = False,
    repository: str = DEFAULT_REPOSITORY,
    branch: str = DEFAULT_BRANCH,
) -> int:
    print()
    print("KFPS FH6 6-Step Locator Calibration")
    print("READ-ONLY: this tool only scans FH6 memory. It never writes to the game.")
    print()
    print("Prerequisite before pressing Enter:")
    print("  1. Open FH6.")
    print("  2. Open a flat, ungrouped 3000-layer plain circle template in the vinyl editor.")
    print("  3. Keep FH6 open on that editor screen.")
    print()

    pid, exe = find_forza_pid()
    module = find_main_module(pid)
    if not module:
        raise RuntimeError("Could not identify the FH6 main module.")

    out_dir = Path("calibration-results") / safe_name(f"six_step_{time.strftime('%Y%m%d-%H%M%S')}")
    observations_by_key: dict[str, list[dict]] = {}
    latest_candidates: list[dict] = []
    saved_keys: set[str] = set()
    completed_step = 0

    publish_ready = False
    publish_status = "publication disabled"
    if auto_publish and dry_run_publish:
        publish_ready = True
        publish_status = "dry run; no remote file will be changed"
    elif auto_publish:
        publish_ready, publish_status = github_publish_readiness()

    log("Using detected FH6 process.")
    log(f"Main module: {module['name']} size={module['size']}")
    print(f"Shared profile publication: {publish_status}")
    print()

    previous_count = None
    for step, target_count in enumerate(FIXED_SIX_STEP_COUNTS, start=1):
        if step == 1:
            print(f"Step {step}/6: confirm FH6 shows the open {target_count}-layer template.")
            print("Do not change anything yet.")
            prompt = f"Press Enter to scan step {step}/6 at {target_count} layers, or type Q to stop: "
        else:
            delete_count = previous_count - target_count
            print(f"Step {step}/6: delete {delete_count} layer(s) in FH6 so the editor shows {target_count} layers.")
            prompt = f"After FH6 shows {target_count} layers, press Enter to scan step {step}/6, or type Q to stop: "
        command = input(prompt).strip().lower()
        if command == "q":
            break

        evidence, candidates, pattern_hits = scan_rtti_evidence(pid, module, target_count)
        completed_step = step
        latest_candidates = candidates
        log(
            f"Scan {step}: layer_count={target_count}, layout_candidates={len(candidates)}, "
            f"pattern_hits={pattern_hits}, locator_hits={len(evidence)}"
        )
        for item in evidence:
            observations_by_key.setdefault(item["key"], []).append(item)

        locked = []
        for key, observations in observations_by_key.items():
            summary = observation_summary(observations)
            log(
                f"  evidence candidate: scans={summary['scans']} "
                f"counts={','.join(str(c) for c in summary['distinct_counts']) or 'none'}"
            )
            if summary["scans"] >= required_scans and len(summary["distinct_counts"]) >= 2:
                locked.append((key, observations))

        for key, observations in locked:
            result = build_locked_result(pid, exe, module, key, observations, latest_candidates)
            result["workflow"] = {
                "name": "six_step_template_calibration",
                "target_counts": FIXED_SIX_STEP_COUNTS,
                "completed_step": step,
                "required_scans": required_scans,
            }
            path = save_result(out_dir, result)
            if key in saved_keys:
                log(f"Updated locked locator with {len(observations)} confirming scan(s): {path}")
            else:
                saved_keys.add(key)
                log(f"LOCKED locator after {len(observations)} confirming scan(s): {path}")
            log(f"Confidence: {result['rtti'].get('confidence')}")

        if saved_keys and step >= 4:
            print()
            print("A locator was already locked with repeated evidence.")
            print("Continue the remaining steps for stronger confirmation, or type Q at the next prompt to stop.")
        previous_count = target_count
        print()

    if saved_keys:
        publishable = {}
        expected_counts = sorted(FIXED_SIX_STEP_COUNTS)
        for key, observations in observations_by_key.items():
            summary = observation_summary(observations)
            if summary["distinct_counts"] != expected_counts:
                continue
            result = build_locked_result(pid, exe, module, key, observations, latest_candidates)
            result["workflow"] = {
                "name": "six_step_template_calibration",
                "target_counts": FIXED_SIX_STEP_COUNTS,
                "completed_step": completed_step,
                "required_scans": required_scans,
            }
            save_result(out_dir, result)
            try:
                profile = profile_from_calibration_result(result, require_complete=True)
            except RegistryError:
                continue
            publishable[profile["profile_id"]] = (result, profile)

        if completed_step < len(FIXED_SIX_STEP_COUNTS):
            print("Calibration stopped before all six scans completed. Nothing was published.")
            print(f"Local evidence remains in: {out_dir.resolve()}")
            return 1
        if len(publishable) != 1:
            print(
                "Calibration did not produce exactly one stable six-scan profile. "
                "Nothing was published."
            )
            print(f"Keep the local evidence for review: {out_dir.resolve()}")
            return 1

        _result, profile = next(iter(publishable.values()))
        local_registry = registry_with_profile(empty_registry(), profile)
        registry_path = out_dir / "RTTI.dat"
        write_registry_file(registry_path, local_registry)

        print("Calibration complete. Use the newest files in:")
        print(out_dir.resolve())
        print()
        print("Files to use:")
        print("  clivery-rtti-latest.json")
        print("  clivery-rtti-offsets.txt")
        print("  update-codes.dat")
        print("  RTTI.dat (privacy-safe shared profile)")
        print()
        print("The full evidence files stay local. Only RTTI.dat is eligible for publication.")

        if not auto_publish:
            print("Automatic publication was disabled. RTTI.dat was saved locally only.")
            return 0
        if not publish_ready:
            print(f"Automatic publication could not run: {publish_status}")
            print("Install/authenticate GitHub CLI, then use --publish-result with the saved JSON.")
            return 2
        try:
            publication = publish_profile_to_github(
                profile,
                repository=repository,
                branch=branch,
                existing_registry=empty_registry() if dry_run_publish else None,
                dry_run=dry_run_publish,
            )
        except PublishError as exc:
            print(f"Automatic publication failed: {exc}")
            print("RTTI.dat is safe locally; no partial remote update was accepted.")
            return 2
        if publication["dry_run"]:
            print("Publication dry run passed. The remote registry was not changed.")
        else:
            print("Shared FH6 locator profile published successfully.")
            if publication.get("commit_url"):
                print(publication["commit_url"])
        return 0

    print("Calibration did not lock a repeated locator candidate.")
    print("Retry with a flat ungrouped 3000-circle template, or send the calibration-results folder for analysis.")
    return 1


def publish_saved_result(
    path: Path,
    *,
    auto_publish: bool,
    dry_run_publish: bool,
    repository: str,
    branch: str,
) -> int:
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
        profile = profile_from_calibration_result(result, require_complete=True)
    except (OSError, ValueError, RegistryError) as exc:
        print(f"Saved calibration result is not publishable: {exc}")
        return 1

    registry_path = Path(path).resolve().parent / "RTTI.dat"
    write_registry_file(registry_path, registry_with_profile(empty_registry(), profile))
    print(f"Validated privacy-safe profile: {profile['profile_id']}")
    print(f"Local registry: {registry_path}")
    if not auto_publish:
        print("Publication disabled; the remote registry was not changed.")
        return 0

    try:
        publication = publish_profile_to_github(
            profile,
            repository=repository,
            branch=branch,
            existing_registry=empty_registry() if dry_run_publish else None,
            dry_run=dry_run_publish,
        )
    except PublishError as exc:
        print(f"Publication failed: {exc}")
        return 2
    if publication["dry_run"]:
        print("Publication dry run passed. The remote registry was not changed.")
    else:
        print("Shared FH6 locator profile published successfully.")
        if publication.get("commit_url"):
            print(publication["commit_url"])
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only six-step FH6 locator calibrator with privacy-safe shared profile publication."
        )
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Save the validated RTTI.dat locally without updating GitHub.",
    )
    parser.add_argument(
        "--dry-run-publish",
        action="store_true",
        help="Validate the publication payload without changing GitHub.",
    )
    parser.add_argument(
        "--publish-result",
        type=Path,
        metavar="CALIBRATION_JSON",
        help="Validate and publish a previously completed six-step calibration result.",
    )
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY, help=argparse.SUPPRESS)
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.no_publish and args.dry_run_publish:
        parser.error("--no-publish and --dry-run-publish cannot be used together")
    return args


def main() -> int:
    args = parse_args()
    if args.publish_result:
        return publish_saved_result(
            args.publish_result,
            auto_publish=not args.no_publish,
            dry_run_publish=args.dry_run_publish,
            repository=args.repository,
            branch=args.branch,
        )
    if os.name != "nt":
        print("This calibrator only runs on Windows because it reads the FH6 process.")
        return 1
    try:
        return six_step_template_calibration(
            auto_publish=not args.no_publish,
            dry_run_publish=args.dry_run_publish,
            repository=args.repository,
            branch=args.branch,
        )
    except KeyboardInterrupt:
        print()
        log("Stopped by user.")
        return 130
    except Exception as exc:
        log(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
