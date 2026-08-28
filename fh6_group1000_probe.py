#!/usr/bin/env python3
"""Read-only FH6 group/table locator for import and export workflows."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import struct
import time
import zlib
from collections import Counter
from ctypes import wintypes
from pathlib import Path

import psutil

from live_memory_locator.diagnostics import write_backend_diagnostic


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
RW_MASK = 0xCC

GROUP_COUNT_OFF = 0x5A
GROUP_TABLE_OFF = 0x78
GROUP_TABLE_END_OFF = 0x80
GROUP_TABLE_CAPACITY_OFF = 0x88
GROUP_HEADER_READ = 0x300
LAYER_SIZE = 0xC0
USER_MIN = 0x10000
USER_MAX = 0x7FFFFFFFFFFF
SCAN_CHUNK_SIZE = 64 * 1024 * 1024
COUNT_SCAN_CHUNK_SIZE = 8 * 1024 * 1024
SMALL_REGIONS_PER_LARGE_CHUNK = 16


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


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def finite(value, limit=100000.0):
    return math.isfinite(value) and -limit <= value <= limit


def find_pid(pid=None):
    if pid:
        return int(pid)
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info.get("name") or "").lower() == "forzahorizon6.exe":
                return int(proc.info["pid"])
        except psutil.Error:
            pass
    raise RuntimeError("forzahorizon6.exe not found")


def process_info(pid):
    try:
        proc = psutil.Process(pid)
        return {"name": proc.name(), "exe": proc.exe()}
    except psutil.Error:
        return {"name": "forzahorizon6.exe", "exe": ""}


def open_process(pid):
    access = PROCESS_QUERY_INFORMATION | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
    handle = k32.OpenProcess(access, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle):
    if handle:
        k32.CloseHandle(handle)


def read_memory(handle, address, size):
    if size <= 0:
        return b""
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value <= 0:
        return b""
    return buf.raw[: read.value]


def read_u16(handle, address):
    raw = read_memory(handle, address, 2)
    return struct.unpack("<H", raw)[0] if len(raw) == 2 else None


def read_u64(handle, address):
    raw = read_memory(handle, address, 8)
    return struct.unpack("<Q", raw)[0] if len(raw) == 8 else None


def is_rw(protect):
    return not (protect & PAGE_GUARD or protect & PAGE_NOACCESS) and bool(protect & RW_MASK)


def iter_regions(handle):
    addr = USER_MIN
    info = MBI()
    while addr < USER_MAX:
        if not k32.VirtualQueryEx(handle, addr, ctypes.byref(info), ctypes.sizeof(info)):
            addr += 0x10000
            continue
        base = int(info.BaseAddress)
        size = int(info.RegionSize)
        if int(info.State) == MEM_COMMIT and int(info.Type) == MEM_PRIVATE and is_rw(int(info.Protect)):
            yield {"base": base, "end": base + size, "size": size}
        nxt = base + size
        if nxt <= addr:
            break
        addr = nxt


def build_contains(regions):
    ranges = sorted((r["base"], r["end"]) for r in regions)

    def contains(value, size=1):
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


def layer_summary(handle, ptr, index):
    raw = read_memory(handle, ptr, LAYER_SIZE)
    if len(raw) < 0xB0:
        return {"index": index, "ptr": hx(ptr), "ok": False, "reason": f"short read {len(raw)}"}
    px, py = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rot = struct.unpack_from("<f", raw, 0x50)[0]
    res = struct.unpack_from("<Q", raw, 0xA8)[0]
    ok = finite(px) and finite(py) and finite(sx) and finite(sy) and finite(rot, 1000000.0)
    return {
        "index": index,
        "ptr": hx(ptr),
        "ok": ok,
        "position": [px, py],
        "scale": [sx, sy],
        "rotation": rot,
        "color_rgba": list(raw[0x74:0x78]),
        "mask": raw[0x78],
        "shape_id_byte": raw[0x7A],
        "resource_ptr_0xa8": hx(res) if USER_MIN <= res <= USER_MAX else None,
        "crc32": f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}",
        "bytes_0x38_0x7c": raw[0x38:0x7C].hex(),
        "raw_hex": raw.hex(),
    }


def candidate_rejection(candidate, expected_count=None):
    count = int(expected_count if expected_count is not None else candidate.get("count") or 0)
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, count - valid_ptrs))
    duplicate_ptrs = int(candidate.get("duplicate_ptr_count") or 0)
    decoded_layers = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
    vector_count = candidate.get("vector_count")
    capacity_count = candidate.get("capacity_count")

    if not candidate.get("group") or not candidate.get("table"):
        return "missing group/table"
    if candidate.get("vector_ok") is not True:
        return "vector metadata invalid"
    if vector_count is None or int(vector_count) != count:
        return f"vector_count={vector_count}"
    if capacity_count is None or int(capacity_count) < count:
        return f"capacity_count={capacity_count}"
    if valid_ptrs != count:
        return f"valid_ptrs={valid_ptrs}"
    if invalid_ptrs:
        return f"invalid_ptrs={invalid_ptrs}"
    if duplicate_ptrs:
        return f"duplicate_ptrs={duplicate_ptrs}"
    if decoded_layers != count:
        return f"decoded_layers={decoded_layers}"
    return ""


def candidate_is_strict(candidate, expected_count=None):
    return not candidate_rejection(candidate, expected_count)


def candidate_sort_key(candidate):
    count = int(candidate.get("count") or 0)
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or 0)
    ok_count = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
    strict = int(candidate_is_strict(candidate, count))
    exact_table = int(valid_ptrs == count and invalid_ptrs == 0)
    exact_ok = int(exact_table and ok_count == count)
    vector_bonus = int(candidate.get("vector_ok") is True)
    source_bonus = 1 if candidate.get("source") == "vector_header" else 0
    return (
        strict,
        exact_ok,
        exact_table,
        valid_ptrs,
        ok_count,
        -invalid_ptrs,
        vector_bonus,
        source_bonus,
        int(candidate.get("score") or 0),
    )


def add_candidate(candidates, item, keep=100):
    if not item:
        return
    candidates.append(item)
    candidates.sort(key=candidate_sort_key, reverse=True)
    del candidates[keep:]


def validate_candidate(handle, contains, group, table, count, report_layers, source):
    if table is None:
        return None
    if not contains(group, GROUP_TABLE_CAPACITY_OFF + 8):
        return None
    if not contains(table, max(8, count * 8)):
        return None
    count_u16 = read_u16(handle, group + GROUP_COUNT_OFF)
    if count_u16 != count:
        return None
    table_end = read_u64(handle, group + GROUP_TABLE_END_OFF)
    table_capacity = read_u64(handle, group + GROUP_TABLE_CAPACITY_OFF)
    if table_end is None or table_capacity is None:
        return None
    expected_end = int(table) + int(count) * 8
    vector_reasons = []
    if table_end != expected_end:
        vector_reasons.append(f"table_end={hx(table_end)} expected={hx(expected_end)}")
    if table_capacity < expected_end:
        return None
    if (table_end - table) % 8 != 0 or (table_capacity - table) % 8 != 0:
        return None
    if not contains(table_capacity - 1):
        return None
    vector_count = (table_end - table) // 8
    capacity_count = (table_capacity - table) // 8
    if vector_count != count:
        vector_reasons.append(f"vector_count={vector_count}")
    if capacity_count < count or capacity_count > max(count + 10000, count * 16):
        return None
    ptr_raw = read_memory(handle, table, count * 8)
    if len(ptr_raw) != count * 8:
        return None
    ptrs = list(struct.unpack(f"<{count}Q", ptr_raw))
    valid_ptrs = [p for p in ptrs if contains(p, 0x7C)]
    min_prefilter_ptrs = min(count, max(4, count // 4))
    if len(valid_ptrs) < min_prefilter_ptrs:
        return None

    sample_indices = list(range(min(count, report_layers)))
    if count > report_layers:
        tail_start = max(report_layers, count - min(20, report_layers))
        sample_indices.extend(range(tail_start, count))
    sample_indices = set(sample_indices)

    sample = []
    sample_shape_counts = Counter()
    sample_colors = Counter()
    all_shape_counts = Counter()
    all_mask_counts = Counter()
    all_colors = Counter()
    square_like = []
    ok_count = 0

    for i, ptr in enumerate(ptrs):
        if not contains(ptr, 0x7C):
            if i in sample_indices:
                sample.append({"index": i, "ptr": hx(ptr), "ok": False, "reason": "not private rw"})
            continue
        item = layer_summary(handle, ptr, i)
        if item.get("ok"):
            ok_count += 1
        shape_id = item.get("shape_id_byte")
        if shape_id is not None:
            all_shape_counts[shape_id] += 1
            if shape_id == 101:
                square_like.append(i)
        if "mask" in item:
            all_mask_counts[item["mask"]] += 1
        if "color_rgba" in item:
            all_colors[tuple(item["color_rgba"])] += 1
        if i in sample_indices:
            sample.append(item)
            if shape_id is not None:
                sample_shape_counts[shape_id] += 1
            if "color_rgba" in item:
                sample_colors[tuple(item["color_rgba"])] += 1

    invalid_ptrs = max(0, len(ptrs) - len(valid_ptrs))
    duplicate_ptr_count = len(ptrs) - len(set(ptrs)) if ptrs else 0
    vector_ok = not vector_reasons
    strict_valid = (
        vector_ok
        and len(valid_ptrs) == count
        and invalid_ptrs == 0
        and duplicate_ptr_count == 0
        and ok_count == count
    )
    exact_bonus = 100000 if strict_valid else 0
    ok_bonus = 50000 if strict_valid else 0
    score = (
        exact_bonus
        + ok_bonus
        + len(valid_ptrs) * 10
        + ok_count * 4
        + (1000 if source == "vector_header" else 0)
        + (500 if vector_ok else 0)
        - len(vector_reasons) * 250
        - invalid_ptrs * 100
        - duplicate_ptr_count * 20
    )
    return {
        "score": score,
        "source": source,
        "group": hx(group),
        "table": hx(table),
        "table_end": hx(table_end),
        "table_capacity": hx(table_capacity),
        "count": count,
        "count_u16_0x5a": count_u16,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "vector_ok": vector_ok,
        "reasons": vector_reasons,
        "valid_ptrs": len(valid_ptrs),
        "invalid_ptrs": invalid_ptrs,
        "duplicate_ptr_count": duplicate_ptr_count,
        "layer_ok_count": ok_count,
        "sample_ok_count": ok_count,
        "strict_valid": strict_valid,
        "shape_id_counts_sample": dict(sample_shape_counts.most_common(24)),
        "shape_id_counts_all": dict(all_shape_counts.most_common(64)),
        "mask_counts_all": dict(all_mask_counts.most_common(16)),
        "square_byte_indices": square_like[:50],
        "color_counts_sample": {" ".join(map(str, k)): v for k, v in sample_colors.most_common(12)},
        "color_counts_all": {" ".join(map(str, k)): v for k, v in all_colors.most_common(32)},
        "layers": sample,
    }


def iter_region_chunks(handle, region, *, chunk_size=SCAN_CHUNK_SIZE, overlap=0):
    size = int(region["size"])
    base = int(region["base"])
    chunk_size = max(4096, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    offset = 0
    while offset < size:
        requested = min(chunk_size, size - offset)
        raw = read_memory(handle, base + offset, requested)
        if raw:
            yield base + offset, raw
        if offset + requested >= size or requested <= overlap:
            break
        offset += requested - overlap


def iter_balanced_region_chunks(
    handle,
    regions,
    *,
    chunk_size=SCAN_CHUNK_SIZE,
    overlap=0,
    small_regions_per_large=SMALL_REGIONS_PER_LARGE_CHUNK,
):
    """Cover large and small allocations throughout a deadline-bound scan."""
    chunk_size = max(4096, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    small_regions_per_large = max(1, int(small_regions_per_large))
    small_regions = sorted(
        (region for region in regions if int(region["size"]) <= chunk_size),
        key=lambda region: int(region["base"]),
    )
    large_regions = sorted(
        (region for region in regions if int(region["size"]) > chunk_size),
        key=lambda region: (-int(region["size"]), int(region["base"])),
    )

    def large_chunks():
        step = chunk_size - overlap
        offset = 0
        while True:
            emitted = False
            for region in large_regions:
                size = int(region["size"])
                if offset >= size:
                    continue
                requested = min(chunk_size, size - offset)
                raw = read_memory(handle, int(region["base"]) + offset, requested)
                emitted = True
                if raw:
                    unique_size = len(raw) if offset == 0 else max(0, len(raw) - overlap)
                    yield region, int(region["base"]) + offset, raw, unique_size
            if not emitted:
                break
            offset += step

    large_iter = iter(large_chunks())
    small_iter = iter(small_regions)
    large_done = False
    small_done = False
    while not (large_done and small_done):
        if not large_done:
            try:
                yield next(large_iter)
            except StopIteration:
                large_done = True
        if not small_done:
            for _ in range(small_regions_per_large):
                try:
                    region = next(small_iter)
                except StopIteration:
                    small_done = True
                    break
                raw = read_memory(handle, int(region["base"]), int(region["size"]))
                if raw:
                    yield region, int(region["base"]), raw, len(raw)


def scan_count_headers(handle, regions, contains, count, deadline, report_layers, candidates, seen):
    pattern = struct.pack("<H", count)
    scanned_bytes = 0
    hit_count = 0
    chunks = 0
    covered_regions = set()
    stopped_by_time = False
    scheduled = iter_balanced_region_chunks(
        handle,
        regions,
        chunk_size=COUNT_SCAN_CHUNK_SIZE,
        overlap=len(pattern) - 1,
    )
    for region, chunk_base, raw, unique_size in scheduled:
        if deadline and time.time() > deadline:
            log("Count-header scan time limit reached.")
            stopped_by_time = True
            break
        chunks += 1
        scanned_bytes += unique_size
        covered_regions.add(int(region["base"]))
        pos = 0
        while True:
            hit = raw.find(pattern, pos)
            if hit < 0:
                break
            pos = hit + 1
            hit_count += 1
            if hit_count % 4096 == 0 and deadline and time.time() > deadline:
                log("Count-header scan time limit reached.")
                stopped_by_time = True
                break
            group = chunk_base + hit - GROUP_COUNT_OFF
            if group in seen or group < int(region["base"]):
                continue
            table = read_u64(handle, group + GROUP_TABLE_OFF)
            item = validate_candidate(handle, contains, group, table, count, report_layers, "count_header")
            if item:
                seen.add(group)
                add_candidate(candidates, item)
        if stopped_by_time:
            break
        if chunks % 512 == 0:
            log(
                f"Count scan {len(covered_regions)}/{len(regions)} regions, "
                f"{scanned_bytes / (1024 * 1024):.0f} MB, candidates={len(candidates)}"
            )
    return {
        "scanned_mb": scanned_bytes / (1024 * 1024),
        "count_hits": hit_count,
        "chunks": chunks,
        "regions_covered": len(covered_regions),
        "complete": not stopped_by_time,
        "stopped_by_time": stopped_by_time,
    }


def scan_vector_headers(handle, regions, contains, count, deadline, report_layers, candidates, seen):
    scanned_bytes = 0
    triple_hits = 0
    chunks = 0
    covered_regions = set()
    stopped_by_time = False
    overlap = GROUP_TABLE_CAPACITY_OFF + 8
    scheduled = iter_balanced_region_chunks(handle, regions, overlap=overlap)
    for region, chunk_base, raw, unique_size in scheduled:
        if deadline and time.time() > deadline:
            log("Vector-header scan time limit reached.")
            stopped_by_time = True
            break
        chunks += 1
        scanned_bytes += unique_size
        covered_regions.add(int(region["base"]))
        limit = len(raw) - GROUP_TABLE_CAPACITY_OFF - 8
        start_offset = (-chunk_base) % 8
        for off in range(start_offset, max(start_offset, limit), 8):
            if off and off % (1024 * 1024) == 0 and deadline and time.time() > deadline:
                log("Vector-header scan time limit reached.")
                stopped_by_time = True
                break
            group = chunk_base + off
            if group in seen:
                continue
            begin = struct.unpack_from("<Q", raw, off + GROUP_TABLE_OFF)[0]
            end = struct.unpack_from("<Q", raw, off + GROUP_TABLE_END_OFF)[0]
            capacity = struct.unpack_from("<Q", raw, off + GROUP_TABLE_CAPACITY_OFF)[0]
            if end != begin + count * 8:
                continue
            if capacity < end or (capacity - begin) % 8:
                continue
            if not contains(begin, max(8, count * 8)) or not contains(end - 1) or not contains(capacity - 1):
                continue
            triple_hits += 1
            item = validate_candidate(handle, contains, group, begin, count, report_layers, "vector_header")
            if item:
                seen.add(group)
                add_candidate(candidates, item)
        if stopped_by_time:
            break
        if chunks % 512 == 0:
            log(
                f"Vector scan {len(covered_regions)}/{len(regions)} regions, "
                f"{scanned_bytes / (1024 * 1024):.0f} MB, candidates={len(candidates)}"
            )
    return {
        "scanned_mb": scanned_bytes / (1024 * 1024),
        "vector_triple_hits": triple_hits,
        "chunks": chunks,
        "regions_covered": len(covered_regions),
        "complete": not stopped_by_time,
        "stopped_by_time": stopped_by_time,
    }


def scan_groups(handle, count, max_seconds, report_layers):
    regions = list(iter_regions(handle))
    contains = build_contains(regions)
    candidates = []
    seen = set()
    started = time.time()
    if max_seconds:
        # Count matching uses CPython's native byte search and is substantially
        # faster than the Python-level vector walk. Give it most of the fallback
        # budget so late private regions are still reached.
        count_deadline = started + max(10, max_seconds * 0.90)
        vector_deadline = started + max_seconds
    else:
        count_deadline = vector_deadline = None
    count_stats = scan_count_headers(handle, regions, contains, count, count_deadline, report_layers, candidates, seen)
    has_exact_table = any(candidate_is_strict(candidate, count) for candidate in candidates)
    if has_exact_table:
        vector_stats = {"skipped": True, "reason": "count scan found exact full table"}
    else:
        vector_stats = scan_vector_headers(handle, regions, contains, count, vector_deadline, report_layers, candidates, seen)
    candidates.sort(key=candidate_sort_key, reverse=True)
    strict_candidates = sum(1 for candidate in candidates if candidate_is_strict(candidate, count))
    log(
        "Scan complete: "
        f"count={count_stats.get('scanned_mb', 0):.0f} MB/{count_stats.get('count_hits', 0)} hits, "
        f"vector={vector_stats.get('scanned_mb', 0):.0f} MB/{vector_stats.get('vector_triple_hits', 0)} hits, "
        f"candidates={len(candidates)}, strict={strict_candidates}"
    )
    return candidates, {
        "regions": len(regions),
        "total_mb": sum(int(region["size"]) for region in regions) / (1024 * 1024),
        "large_regions": sum(1 for region in regions if int(region["size"]) > COUNT_SCAN_CHUNK_SIZE),
        "scan_schedule": "balanced_large_stripes_and_small_regions_v1",
        "count_scan": count_stats,
        "vector_scan": vector_stats,
        "strict_candidate_count": strict_candidates,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--max-seconds", type=int, default=90)
    parser.add_argument("--report-layers", type=int, default=120)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    pid = find_pid(args.pid)
    info = process_info(pid)
    log(f"Opening pid={pid} {info.get('name')}")
    handle = open_process(pid)
    try:
        candidates, scanner = scan_groups(handle, args.count, args.max_seconds, args.report_layers)
    finally:
        close_handle(handle)
    payload = {
        "format": "fh6_group1000_probe_v2",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": pid,
        "process": info,
        "count": args.count,
        "scanner": scanner,
        "candidates": candidates,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"fh6-group{args.count}-probe-{time.strftime('%Y%m%d-%H%M%S')}.json"
    write_backend_diagnostic(out, payload, root=Path(__file__).resolve().parent)
    log(f"Wrote {out}")


if __name__ == "__main__":
    main()
