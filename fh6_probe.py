import argparse
import base64
import ctypes
import json
import struct
import sys
import time
import zlib
from bisect import bisect_right
from ctypes import wintypes
from pathlib import Path

import psutil

from fh6_live_group_policy import LIVE_OWNERSHIP_GAMES, MIN_HEADER_SIZE, assess_group_tree
from game_profiles import PROFILES, get_profile
from fh6_rtti_registry import load_runtime_profiles
from native import (
    dereference_pointer,
    get_base_address,
    process_memory_session,
    read_int,
    read_process_memory,
)


MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
PAGE_READONLY = 0x02
PAGE_READWRITE = 0x04
READABLE_WRITABLE_MASK = 0xCC
ROOT = Path(__file__).resolve().parent

FH6_CALIBRATED_RTTI_PROFILE = {
    "update_code": b"91173565759607",
    "descriptor_offset": 0x9E2C940,
    "vtable_offsets": [0x680FC00],
    "base_class_count": 4,
    "module_size": 187719680,
    "game_build": "3.382.893.0",
}

FH6_GROUP_GRAPH_ACCEPT_CAP = 5
FH6_GROUP_GRAPH_SCAN_CAP = 4096
FH6_LOCATOR_CANDIDATE_CAP = 5
FH6_REGION_SCAN_CHUNK_SIZE = 64 * 1024 * 1024
FH6_COUNT_SCAN_CHUNK_SIZE = 8 * 1024 * 1024
FH6_SMALL_REGIONS_PER_LARGE_CHUNK = 16
FH6_GROUP_ARENA_MIN_SIZE = 8 * 1024 * 1024
FH6_GROUP_ARENA_MAX_SIZE = 16 * 1024 * 1024
FH6_DEFAULT_ALLOCATOR_WINDOWS = ((0x270000000, 0x280000000),)
FH6_DISCOVERED_ALLOCATOR_WINDOW_SIZE = 0x10000000
FH6_LOCATOR_CACHE_FORMAT = "kfps_fh6_allocator_cache_v2"
FH6_LOCATOR_CACHE_PATH = ROOT / "runtime" / "fh6-rtti" / "live-locator-cache.json"
LAST_LOCATOR_DIAGNOSTICS = {}


class LocatorRefused(RuntimeError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def record_locator_diagnostic(name, **values):
    LAST_LOCATOR_DIAGNOSTICS[str(name)] = values


def runtime_diagnostic_identity():
    def read_text(name):
        try:
            return (ROOT / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    return {
        "kfps_version": read_text("VERSION"),
        "build_commit": read_text("BUILD_COMMIT"),
    }


def normalize_allocator_windows(values):
    windows = []
    for value in values or []:
        try:
            start, end = (int(item) for item in value)
        except (TypeError, ValueError):
            continue
        if start < 0x10000 or end <= start or end > 0x800000000000:
            continue
        if end - start > 0x100000000:
            continue
        windows.append((start, end))
    windows.sort()
    merged = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged[:8]


def allocator_window_for_address(address):
    size = FH6_DISCOVERED_ALLOCATOR_WINDOW_SIZE
    start = int(address) & ~(size - 1)
    return start, start + size


def load_fh6_allocator_cache(rtti):
    empty = {"windows": []}
    profile_id = str(rtti.get("profile_id") or "").strip()
    if not profile_id:
        return empty
    try:
        raw = json.loads(FH6_LOCATOR_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return empty
    if not isinstance(raw, dict) or raw.get("format") != FH6_LOCATOR_CACHE_FORMAT:
        return empty
    profiles = raw.get("profiles")
    profile_cache = profiles.get(profile_id) if isinstance(profiles, dict) else None
    if not isinstance(profile_cache, dict):
        return empty
    return {
        "windows": normalize_allocator_windows(profile_cache.get("allocator_windows")),
    }


def save_fh6_allocator_cache(rtti, allocator_windows):
    profile_id = str(rtti.get("profile_id") or "").strip()
    if not profile_id:
        return
    try:
        raw = json.loads(FH6_LOCATOR_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict) or raw.get("format") != FH6_LOCATOR_CACHE_FORMAT:
        raw = {"format": FH6_LOCATOR_CACHE_FORMAT, "profiles": {}}
    profiles = raw.setdefault("profiles", {})
    if not isinstance(profiles, dict):
        profiles = {}
        raw["profiles"] = profiles
    windows = normalize_allocator_windows(allocator_windows)
    profiles[profile_id] = {
        "allocator_windows": [[start, end] for start, end in windows],
        "updated": time.time(),
    }
    if len(profiles) > 16:
        ordered = sorted(
            profiles.items(),
            key=lambda item: float(item[1].get("updated") or 0.0) if isinstance(item[1], dict) else 0.0,
            reverse=True,
        )
        raw["profiles"] = dict(ordered[:16])
    try:
        FH6_LOCATOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = FH6_LOCATOR_CACHE_PATH.with_name(
            f".{FH6_LOCATOR_CACHE_PATH.name}.{time.time_ns()}.tmp"
        )
        temporary.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        temporary.replace(FH6_LOCATOR_CACHE_PATH)
    except OSError:
        pass


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wintypes.LPVOID),
        ("AllocationBase", wintypes.LPVOID),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.VirtualQueryEx.argtypes = (
    wintypes.HANDLE,
    wintypes.LPCVOID,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION),
    ctypes.c_size_t,
)


def is_readable_writable(protect):
    if protect & PAGE_GUARD or protect & PAGE_NOACCESS:
        return False
    return bool(protect & READABLE_WRITABLE_MASK)


def is_readable(protect):
    if protect & PAGE_GUARD or protect & PAGE_NOACCESS:
        return False
    return bool(protect & 0xFE)


def iter_regions(pid, min_address=0x10000, max_address=0x7FFFFFFFFFFF, type_filter=None, writable_only=True):
    with process_memory_session(pid) as session:
        handle = session.handle
        address = min_address
        info = MEMORY_BASIC_INFORMATION()
        while address < max_address:
            result = kernel32.VirtualQueryEx(handle, address, ctypes.byref(info), ctypes.sizeof(info))
            if not result:
                address += 0x10000
                continue
            base = int(info.BaseAddress)
            size = int(info.RegionSize)
            type_ok = type_filter is None or int(info.Type) == type_filter
            protect_ok = is_readable_writable(info.Protect) if writable_only else is_readable(info.Protect)
            if info.State == MEM_COMMIT and type_ok and protect_ok:
                yield base, size, int(info.Protect), int(info.Type)
            next_address = base + size
            if next_address <= address:
                break
            address = next_address


def is_user_pointer(value):
    return 0x10000 <= value <= 0x7FFFFFFFFFFF


def is_private_writable_address(pid, address):
    if not is_user_pointer(address):
        return False
    try:
        with process_memory_session(pid) as session:
            handle = session.handle
            info = MEMORY_BASIC_INFORMATION()
            result = kernel32.VirtualQueryEx(handle, address, ctypes.byref(info), ctypes.sizeof(info))
            if not result:
                return False
            return info.State == MEM_COMMIT and is_readable_writable(info.Protect)
    except OSError:
        return False


def read_pointer(pid, address):
    try:
        return dereference_pointer(pid, address)
    except Exception:
        return 0


def read_float_pair(pid, address):
    raw = read_process_memory(pid, address, 8)
    if len(raw) != 8:
        return None
    return struct.unpack("ff", raw)


def read_float_value(pid, address):
    raw = read_process_memory(pid, address, 4)
    if len(raw) != 4:
        return None
    return struct.unpack("<f", raw)[0]


def parse_int(value):
    if value is None:
        return None
    return int(str(value), 0)


def format_bytes(raw, width=16):
    lines = []
    for offset in range(0, len(raw), width):
        chunk = raw[offset:offset + width]
        lines.append(f"  +0x{offset:03x}: " + " ".join(f"{byte:02x}" for byte in chunk))
    return "\n".join(lines)


def plausible_float(value):
    return value == value and -100000.0 < value < 100000.0


def inspect_layer_blob(raw):
    float_hits = []
    byte_hits = []
    u32_hits = []
    for offset in range(0, max(0, len(raw) - 8 + 1), 4):
        a, b = struct.unpack_from("<ff", raw, offset)
        if plausible_float(a) and plausible_float(b) and (abs(a) > 0.0001 or abs(b) > 0.0001):
            float_hits.append((offset, a, b))
        value = struct.unpack_from("<I", raw, offset)[0]
        if 1_000_000 <= value <= 2_000_000:
            u32_hits.append((offset, value))
    for offset, value in enumerate(raw):
        if value in (1, 16, 100, 101, 102):
            byte_hits.append((offset, value))
    return float_hits, byte_hits, u32_hits


def inspect_table(pid, table_address, layer_count, blob_size, max_layers, start_index=0):
    print(f"Inspecting located layer table: layers={layer_count} start={start_index}")
    valid = 0
    end_index = min(layer_count, start_index + max_layers)
    for index in range(start_index, end_index):
        pointer = read_pointer(pid, table_address + index * 8)
        print(f"table[{index}] pointer detail omitted")
        if not is_user_pointer(pointer):
            continue
        raw = read_process_memory(pid, pointer, blob_size)
        if len(raw) != blob_size:
            print(f"  unreadable or short read: {len(raw)} bytes")
            continue
        valid += 1
        float_hits, byte_hits, u32_hits = inspect_layer_blob(raw)
        print("  float-pair candidates:")
        for offset, a, b in float_hits[:24]:
            print(f"    offset {offset}: {a:.6g}, {b:.6g}")
        if not float_hits:
            print("    none")
        print("  byte candidates:", " ".join(f"offset{offset}={value}" for offset, value in byte_hits[:32]) or "none")
        print("  u32 candidates:", " ".join(f"offset{offset}={value}" for offset, value in u32_hits[:24]) or "none")
        print("  raw:")
        print("    raw byte preview omitted")
    print(f"Valid pointer entries inspected: {valid}")


def dump_layer(pid, profile, table_address, layer_count, blob_size, layer_index, output_path=None, shape_meta=None):
    if layer_index < 0 or layer_index >= layer_count:
        raise ValueError(f"Layer index {layer_index} is out of range for layer count {layer_count}.")
    pointer = read_pointer(pid, table_address + layer_index * 8)
    if not is_user_pointer(pointer):
        raise ValueError(f"Layer pointer at index {layer_index} is invalid: 0x{pointer:x}")
    raw = read_process_memory(pid, pointer, blob_size)
    if len(raw) != blob_size:
        raise ValueError(f"Short read for layer {layer_index}: expected {blob_size} bytes, got {len(raw)}")
    float_hits, byte_hits, u32_hits = inspect_layer_blob(raw)
    state = read_layer_state(pid, profile, pointer, raw=raw)
    payload = {
        "type": "fh6_shape_layer_dump_v1",
        "pid": pid,
        "process": psutil.Process(pid).name(),
        "layer_count": layer_count,
        "table_address": table_address,
        "layer_index_zero_based": layer_index,
        "layer_index_one_based": layer_index + 1,
        "pointer": pointer,
        "blob_size": blob_size,
        "shape_meta": shape_meta or {},
        "known_fields": state["known_fields"],
        "layer_search": {},
        "float_hits": [{"offset": offset, "a": a, "b": b} for offset, a, b in float_hits],
        "byte_hits": [{"offset": offset, "value": value} for offset, value in byte_hits],
        "u32_hits": [{"offset": offset, "value": value} for offset, value in u32_hits],
        "raw_hex": raw.hex(),
        "created": time.time(),
    }
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Dumped layer {layer_index + 1} to {output_path}")
    else:
        print(json.dumps(payload, indent=2))
    return payload


def read_layer_state(pid, profile, pointer, raw=None):
    pos = read_float_pair(pid, pointer + profile.layer_position_offset)
    scale = read_float_pair(pid, pointer + profile.layer_scale_offset)
    rotation = read_float_value(pid, pointer + profile.layer_rotation_offset)
    color = read_process_memory(pid, pointer + profile.layer_color_offset, 4)
    shape = read_process_memory(pid, pointer + profile.layer_shape_id_offset, 1)
    mask = read_process_memory(pid, pointer + profile.layer_mask_offset, 1)
    raw = raw if raw is not None else read_process_memory(pid, pointer, 0x140)
    float_hits, byte_hits, u32_hits = inspect_layer_blob(raw) if raw else ([], [], [])
    known_fields = {
        "position": [pos[0], pos[1]] if pos else None,
        "scale": [scale[0], scale[1]] if scale else None,
        "rotation": rotation,
        "color_rgba": list(color) if len(color) == 4 else None,
        "shape_byte": shape[0] if shape else None,
        "mask_byte": mask[0] if mask else None,
    }
    score, checks = score_layer_pointer(pid, pointer, profile)
    live_score = score_live_layer(known_fields)
    return {
        "known_fields": known_fields,
        "structural_score": score,
        "live_score": live_score,
        "checks": checks,
        "float_hits": float_hits,
        "byte_hits": byte_hits,
        "u32_hits": u32_hits,
    }


def score_live_layer(known_fields):
    score = 0
    color = known_fields.get("color_rgba") or [0, 0, 0, 0]
    rotation = known_fields.get("rotation")
    scale = known_fields.get("scale") or [0.0, 0.0]
    position = known_fields.get("position") or [0.0, 0.0]
    shape_byte = known_fields.get("shape_byte")

    if len(color) == 4:
        alpha = int(color[3])
        rgb_sum = int(color[0]) + int(color[1]) + int(color[2])
        if alpha > 0:
            score += 12
        if rgb_sum > 0:
            score += 10
        if alpha not in (0, 255):
            score += 4
    if rotation is not None and plausible_float(rotation) and abs(rotation) <= 720.0 and abs(rotation) > 0.01:
        score += 8
    if scale and all(abs(v) > 0.001 for v in scale):
        score += 4
    if position and any(abs(v) > 0.01 for v in position):
        score += 2
    if shape_byte not in (None, 0):
        score += 4
    return score


def read_memory_window(pid, center, before, after):
    start = max(0x10000, int(center) - int(before))
    size = int(before) + int(after)
    raw = read_process_memory(pid, start, size)
    if len(raw) != size:
        return None
    return {
        "start_address": start,
        "center_address": int(center),
        "before": int(before),
        "after": int(after),
        "raw_hex": raw.hex(),
    }


def summarize_slot(pid, profile, table_address, layer_count, blob_size, layer_index):
    if layer_index < 0 or layer_index >= layer_count:
        return None
    pointer = read_pointer(pid, table_address + layer_index * 8)
    if not is_user_pointer(pointer):
        return {
            "layer_index_zero_based": layer_index,
            "layer_index_one_based": layer_index + 1,
            "pointer": pointer,
            "valid_pointer": False,
        }
    raw = read_process_memory(pid, pointer, blob_size)
    if len(raw) != blob_size:
        return {
            "layer_index_zero_based": layer_index,
            "layer_index_one_based": layer_index + 1,
            "pointer": pointer,
            "valid_pointer": True,
            "short_read": len(raw),
        }
    state = read_layer_state(pid, profile, pointer, raw=raw)
    return {
        "layer_index_zero_based": layer_index,
        "layer_index_one_based": layer_index + 1,
        "pointer": pointer,
        "valid_pointer": True,
        "live_score": state["live_score"],
        "structural_score": state["structural_score"],
        "known_fields": state["known_fields"],
        "checks": state["checks"],
        "byte_hits": [{"offset": offset, "value": value} for offset, value in state["byte_hits"][:16]],
        "u32_hits": [{"offset": offset, "value": value} for offset, value in state["u32_hits"][:16]],
        "float_hits": [{"offset": offset, "a": a, "b": b} for offset, a, b in state["float_hits"][:8]],
        "raw_prefix_hex": raw[: min(len(raw), 0x80)].hex(),
    }


def summarize_table_candidate(pid, profile, table, layer_count, blob_size, requested_index, slot_radius):
    table_address = table["table_address"]
    overview = []
    for idx in range(min(layer_count, 12)):
        pointer = read_pointer(pid, table_address + idx * 8)
        overview.append({
            "layer_index_zero_based": idx,
            "layer_index_one_based": idx + 1,
            "pointer": pointer,
        })
    start = max(0, requested_index - min(slot_radius, 4))
    end = min(layer_count - 1, requested_index + min(slot_radius, 4))
    slot_window = []
    for idx in range(start, end + 1):
        summary = summarize_slot(pid, profile, table_address, layer_count, blob_size, idx)
        if summary is not None:
            slot_window.append(summary)
    return {
        "table_address": table_address,
        "table_score": table["score"],
        "locator": table.get("count_kind"),
        "count_address": table.get("count_address"),
        "group_address": table.get("group_address"),
        "table_pointer_field": table.get("table_pointer_field"),
        "validated_entries": table.get("validated_entries"),
        "first_slot_pointers": overview,
        "slot_window": slot_window,
    }


def collect_auto_locate_tables(pid, profile, layer_count, max_seconds=None):
    groups = []
    if profile.key == "fh6":
        groups.extend(locate_clivery_groups_by_rtti(pid, profile, layer_count))
        if not groups:
            groups.extend(locate_clivery_groups_by_layout_count(pid, profile, layer_count, max_seconds=max_seconds))
    else:
        groups.extend(locate_clivery_groups_by_rtti(pid, profile, layer_count))
        if not groups:
            groups.extend(locate_clivery_groups_by_layout_count(pid, profile, layer_count, max_seconds=max_seconds))
    deduped = []
    seen = set()
    for item in sorted(groups, key=lambda entry: entry["score"], reverse=True):
        table_address = item.get("table_address")
        if not table_address or table_address in seen:
            continue
        seen.add(table_address)
        deduped.append(item)
    return deduped


def search_table_slots(pid, profile, table_address, layer_count, requested_index, blob_size, slot_radius):
    candidates = []
    start = max(0, requested_index - slot_radius)
    end = min(layer_count - 1, requested_index + slot_radius)
    for layer_index in range(start, end + 1):
        pointer = read_pointer(pid, table_address + layer_index * 8)
        if not is_user_pointer(pointer):
            continue
        raw = read_process_memory(pid, pointer, blob_size)
        if len(raw) != blob_size:
            continue
        state = read_layer_state(pid, profile, pointer, raw=raw)
        total_score = state["live_score"] * 100 + state["structural_score"] * 10 - abs(layer_index - requested_index)
        candidates.append({
            "layer_index": layer_index,
            "pointer": pointer,
            "score": total_score,
            "live_score": state["live_score"],
            "structural_score": state["structural_score"],
            "known_fields": state["known_fields"],
            "checks": state["checks"],
        })
    candidates.sort(
        key=lambda item: (
            item["score"],
            -abs(item["layer_index"] - requested_index),
        ),
        reverse=True,
    )
    return candidates


def auto_dump_layer(pid, profile, layer_count, blob_size, requested_index, output_path=None, shape_meta=None, slot_radius=8, max_seconds=20):
    candidates = collect_auto_locate_tables(pid, profile, layer_count, max_seconds=max_seconds)
    if not candidates:
        raise ValueError("No safe FH6 layer table candidates were found.")

    searched = []
    candidate_tables = []
    best = None
    for table in candidates[:12]:
        table_address = table["table_address"]
        candidate_tables.append(
            summarize_table_candidate(pid, profile, table, layer_count, blob_size, requested_index, slot_radius)
        )
        slot_matches = search_table_slots(pid, profile, table_address, layer_count, requested_index, blob_size, slot_radius)
        if not slot_matches:
            continue
        top = slot_matches[0]
        searched.append({
            "table_address": table_address,
            "table_score": table["score"],
            "locator": table.get("count_kind"),
            "resolved_index_zero_based": top["layer_index"],
            "resolved_index_one_based": top["layer_index"] + 1,
            "pointer": top["pointer"],
            "score": top["score"],
            "live_score": top["live_score"],
            "structural_score": top["structural_score"],
            "known_fields": top["known_fields"],
            "checks": top["checks"],
        })
        candidate_key = (
            top["live_score"],
            top["structural_score"],
            -abs(top["layer_index"] - requested_index),
            table["score"],
        )
        if best is None or candidate_key > best[0]:
            best = (candidate_key, table, top)

    if best is None:
        raise ValueError("No readable live-looking layer slot was found near the requested index.")

    _candidate_key, table, slot = best
    print(
        f"Auto-dump resolved requested slot {requested_index + 1} to "
        f"table=0x{table['table_address']:x} slot={slot['layer_index'] + 1} "
        f"pointer=0x{slot['pointer']:x} liveScore={slot['live_score']} tableScore={table['score']}",
        flush=True,
    )
    for item in searched[:8]:
        print(
            f"  candidate table=0x{item['table_address']:x} slot={item['resolved_index_one_based']} "
            f"score={item['score']} live={item['live_score']} struct={item['structural_score']} "
            f"locator={item['locator']}",
            flush=True,
        )

    payload = dump_layer(
        pid,
        profile,
        table["table_address"],
        layer_count,
        blob_size,
        slot["layer_index"],
        output_path=output_path,
        shape_meta=shape_meta,
    )
    payload["layer_search"] = {
        "requested_index_zero_based": requested_index,
        "requested_index_one_based": requested_index + 1,
        "slot_radius": slot_radius,
        "resolved_table_address": table["table_address"],
        "resolved_index_zero_based": slot["layer_index"],
        "resolved_index_one_based": slot["layer_index"] + 1,
        "resolved_pointer": slot["pointer"],
        "resolved_live_score": slot["live_score"],
        "resolved_structural_score": slot["structural_score"],
        "table_locator": table.get("count_kind"),
        "table_score": table["score"],
        "candidates": searched[:12],
        "candidate_tables": candidate_tables,
        "resolved_pointer_window": read_memory_window(pid, slot["pointer"], 0x80, min(blob_size + 0x80, 0x240)),
        "resolved_table_entry_window": read_memory_window(pid, table["table_address"] + slot["layer_index"] * 8, 0x40, 0x80),
        "resolved_slot_summary": summarize_slot(pid, profile, table["table_address"], layer_count, blob_size, slot["layer_index"]),
    }
    if output_path:
        Path(output_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Updated auto-dump metadata in {output_path}")
    else:
        print(json.dumps(payload, indent=2))
    return payload


def read_u16(pid, address):
    raw = read_process_memory(pid, address, 2)
    if len(raw) != 2:
        return None
    return struct.unpack("<H", raw)[0]


def read_u32(pid, address):
    raw = read_process_memory(pid, address, 4)
    if len(raw) != 4:
        return None
    return struct.unpack("<I", raw)[0]


def read_u64(pid, address):
    raw = read_process_memory(pid, address, 8)
    if len(raw) != 8:
        return None
    return struct.unpack("<Q", raw)[0]


def read_pe_image_size(pid, module_base):
    """Read SizeOfImage from a live 64-bit PE header."""
    try:
        dos = read_process_memory(pid, module_base, 0x40)
        if len(dos) != 0x40 or dos[:2] != b"MZ":
            return None
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        header = read_process_memory(pid, module_base + pe_offset, 0x58)
        if len(header) != 0x58 or header[:4] != b"PE\x00\x00":
            return None
        return struct.unpack_from("<I", header, 0x50)[0]
    except Exception:
        return None


def validate_group_vector(pid, profile, group_address, table_address, layer_count):
    """Verify the CLiveryGroup vector begin/end/capacity matches the layer table."""
    if not group_address or not table_address:
        return False, {}
    if not is_private_writable_address(pid, group_address):
        return False, {}
    table_end = read_u64(pid, group_address + profile.layer_table_offset + 8)
    table_capacity = read_u64(pid, group_address + profile.layer_table_offset + 16)
    if table_end is None or table_capacity is None:
        return False, {}
    expected_end = int(table_address) + int(layer_count) * 8
    if table_end != expected_end:
        return False, {
            "table_end": table_end,
            "table_capacity": table_capacity,
            "vector_count": (table_end - table_address) // 8 if table_end >= table_address else None,
        }
    if table_capacity < table_end:
        return False, {"table_end": table_end, "table_capacity": table_capacity}
    if (table_end - table_address) % 8 or (table_capacity - table_address) % 8:
        return False, {"table_end": table_end, "table_capacity": table_capacity}
    if not is_private_writable_address(pid, table_end - 1) or not is_private_writable_address(pid, table_capacity - 1):
        return False, {"table_end": table_end, "table_capacity": table_capacity}
    vector_count = (table_end - table_address) // 8
    capacity_count = (table_capacity - table_address) // 8
    if vector_count != layer_count:
        return False, {"table_end": table_end, "table_capacity": table_capacity, "vector_count": vector_count}
    if capacity_count < layer_count or capacity_count > max(layer_count + 10000, layer_count * 16):
        return False, {
            "table_end": table_end,
            "table_capacity": table_capacity,
            "vector_count": vector_count,
            "capacity_count": capacity_count,
        }
    return True, {
        "table_end": table_end,
        "table_capacity": table_capacity,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
    }


def inspect_count_address(pid, profile, count_address, layer_count, radius, blob_size):
    print(f"Process: {psutil.Process(pid).name()} detected.")
    print(f"Inspecting count candidate for layer count {layer_count}")
    print(f"Current values: {read_current_count_values(pid, count_address)}")

    raw_start = max(0x10000, count_address - min(radius, 0x100))
    raw = read_process_memory(pid, raw_start, min(radius * 2, 0x240))
    if raw:
        print("Neighborhood raw bytes:")
        print("raw byte preview omitted")

    print("Nearby scalar count-like fields:")
    for address in range(count_address - radius, count_address + radius + 1):
        try:
            u16 = read_u16(pid, address)
            u32 = read_u32(pid, address)
        except Exception:
            continue
        hits = []
        if u16 in (layer_count, layer_count - 1, layer_count + 1):
            hits.append(f"u16={u16}")
        if u32 in (layer_count, layer_count - 1, layer_count + 1):
            hits.append(f"u32={u32}")
        if hits:
            print(f"  relative={address - count_address:+#x} {' '.join(hits)}")

    print("Nearby pointer fields and possible layer tables:")
    pointer_hits = []
    pointer_start = max(0x10000, count_address - radius) & ~0x7
    pointer_end = (count_address + radius + 7) & ~0x7
    for address in range(pointer_start, pointer_end + 1, 8):
        try:
            value = read_u64(pid, address)
        except Exception:
            continue
        if not value or not is_user_pointer(value):
            continue
        score, samples = score_table(pid, profile, value, min(layer_count, 16))
        pointer_hits.append((score, address, value, samples))
    pointer_hits.sort(key=lambda item: item[0], reverse=True)
    for score, field_address, value, samples in pointer_hits[:40]:
        print(f"  field relative={field_address - count_address:+#x} tableScore={score}")
        for index, ptr, layer_score, checks in samples[:4]:
            print(f"    table[{index}] score={layer_score} {'; '.join(checks)}")

    best_tables = [item for item in pointer_hits if item[0] > 0]
    if best_tables:
        print("Best table candidate detail:")
        _score, field_address, table_address, _samples = best_tables[0]
        print(f"  table field relative={field_address - count_address:+#x}")
        inspect_table(pid, table_address, min(layer_count, 16), blob_size, 8)
    else:
        print("No nearby table-like pointers scored with current FH5-style layer offsets.")


def find_best_table_near_count(pid, profile, count_address, layer_count, radius):
    best = None
    pointer_start = max(0x10000, count_address - radius) & ~0x7
    pointer_end = (count_address + radius + 7) & ~0x7
    for field_address in range(pointer_start, pointer_end + 1, 8):
        try:
            table_address = read_u64(pid, field_address)
        except Exception:
            continue
        if not table_address or not is_user_pointer(table_address):
            continue
        score, samples = score_table(pid, profile, table_address, min(layer_count, 16))
        if score <= 0:
            continue
        item = {
            "score": score,
            "count_address": count_address,
            "table_pointer_field": field_address,
            "table_address": table_address,
            "samples": samples,
        }
        if not best or item["score"] > best["score"]:
            best = item
    return best


def find_best_table_near_count_fast(pid, profile, count_address, layer_count, radius):
    best = None
    pointer_start = max(0x10000, count_address - radius) & ~0x7
    pointer_end = (count_address + radius + 7) & ~0x7
    raw = read_process_memory(pid, pointer_start, pointer_end - pointer_start + 8)
    if len(raw) < 8:
        return None
    for offset in range(0, len(raw) - 7, 8):
        field_address = pointer_start + offset
        table_address = struct.unpack_from("<Q", raw, offset)[0]
        if not table_address or not is_user_pointer(table_address):
            continue
        if not is_private_writable_address(pid, table_address):
            continue
        score, samples = score_table(pid, profile, table_address, min(layer_count, 64))
        if score <= 0:
            continue
        item = {
            "score": score,
            "count_address": count_address,
            "table_pointer_field": field_address,
            "table_address": table_address,
            "samples": samples,
        }
        if not best or item["score"] > best["score"]:
            best = item
    return best


def find_table_at_known_group_delta(pid, profile, count_address, layer_count):
    group_address = count_address - profile.livery_count_offset
    field_address = count_address + (profile.layer_table_offset - profile.livery_count_offset)
    table_address = read_pointer(pid, field_address)
    if not table_address or not is_user_pointer(table_address):
        return None
    if not is_private_writable_address(pid, table_address):
        return None
    if profile.key == "fh6":
        vector_ok, _vector = validate_group_vector(pid, profile, group_address, table_address, layer_count)
        if not vector_ok:
            return None
    score, samples = score_table(pid, profile, table_address, min(layer_count, 64))
    if score <= 0:
        return None
    return {
        "score": score + 40,
        "group_address": group_address,
        "count_address": count_address,
        "table_pointer_field": field_address,
        "table_address": table_address,
        "samples": samples,
    }


def load_shared_rtti_profiles(refresh=True):
    fallback = {
        "game": "fh6",
        "module_size": FH6_CALIBRATED_RTTI_PROFILE["module_size"],
        "descriptor_offset": FH6_CALIBRATED_RTTI_PROFILE["descriptor_offset"],
        "vtable_offsets": FH6_CALIBRATED_RTTI_PROFILE["vtable_offsets"],
        "update_code": FH6_CALIBRATED_RTTI_PROFILE["update_code"].decode("ascii"),
        "base_class_count": FH6_CALIBRATED_RTTI_PROFILE["base_class_count"],
        "game_build": FH6_CALIBRATED_RTTI_PROFILE["game_build"],
        "created_utc": "2026-07-06T16:17:49Z",
        "calibrator_version": "1.0.0",
        "evidence": {
            "workflow": "six_step_template_calibration",
            "confidence": "legacy",
            "scan_count": 5,
            "distinct_counts": [3000, 2997, 2994, 2991, 2988],
        },
    }
    profiles, status = load_runtime_profiles(ROOT, fallback, refresh=refresh)
    refresh_status = status.get("refresh") or {}
    if refresh_status.get("updated"):
        print(
            f"Updated shared FH6 locator profiles ({refresh_status.get('profile_count', 0)} available).",
            flush=True,
        )
    elif refresh_status.get("result") == "error":
        print("Shared FH6 locator update unavailable; using cached or built-in profiles.", flush=True)
    if status.get("load_errors"):
        print("Ignored an invalid local FH6 locator profile file.", flush=True)
    return profiles


def load_update_code_patterns(calibrated_profiles=None, profile=None):
    patterns = list(getattr(profile, "fixed_rtti_descriptor_names", ()) or ())
    profile_key = str(getattr(profile, "key", "") or "").lower()

    # Runtime and remotely calibrated codes belong to FH6. Retired games use
    # their packaged profile codes so a current FH6 value cannot be mistaken
    # for an FH5/FH4 locator candidate.
    if not profile_key or profile_key == "fh6":
        paths = [
            ROOT / "update-codes.dat",
            ROOT / "forza-codes.dat",
            ROOT.parent / "forza-codes.dat",
        ]
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_bytes().splitlines():
                item = line.strip()
                if item:
                    patterns.append(item)
            break
        profiles = calibrated_profiles if calibrated_profiles is not None else load_shared_rtti_profiles()
        for runtime_profile in profiles:
            update_code = str(runtime_profile.get("update_code") or "").encode("ascii", "ignore").strip()
            if update_code:
                patterns.append(update_code)
        if not profiles:
            patterns.append(FH6_CALIBRATED_RTTI_PROFILE["update_code"])
    patterns.append(b".?AVCLiveryGroup@@")
    seen = set()
    unique = []
    for pattern in patterns:
        if pattern not in seen:
            seen.add(pattern)
            unique.append(pattern)
    return unique


def read_region(pid, base, size, max_size=256 * 1024 * 1024):
    if size <= 0 or size > max_size:
        return b""
    try:
        memory = read_process_memory(pid, base, size)
    except Exception:
        return b""
    if len(memory) != size:
        return b""
    return memory


def build_region_contains(regions):
    ranges = sorted((int(base), int(base) + int(size)) for base, size, _protect, _type in regions)
    starts = [start for start, _end in ranges]

    def contains(address, size=1):
        address = int(address or 0)
        size = int(size or 0)
        if address < 0x10000 or size < 1:
            return False
        index = bisect_right(starts, address) - 1
        if index < 0:
            return False
        start, end = ranges[index]
        return start <= address and address + size <= end

    return contains


def iter_region_chunks(pid, base, size, *, chunk_size=FH6_REGION_SCAN_CHUNK_SIZE, overlap=0):
    base = int(base)
    size = int(size)
    chunk_size = max(4096, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    offset = 0
    while offset < size:
        requested = min(chunk_size, size - offset)
        memory = read_region(pid, base + offset, requested, max_size=chunk_size)
        if memory:
            yield base + offset, memory
        if offset + requested >= size or requested <= overlap:
            break
        offset += requested - overlap


def iter_balanced_region_chunks(
    pid,
    regions,
    *,
    chunk_size=FH6_REGION_SCAN_CHUNK_SIZE,
    overlap=0,
    small_regions_per_large=FH6_SMALL_REGIONS_PER_LARGE_CHUNK,
    preferred_size_range=None,
):
    """Interleave large heap stripes with complete small allocations.

    Scanning regions smallest-first can leave every large allocation untouched
    when a deadline expires. Scanning a large allocation to completion first has
    the opposite failure mode. This schedule advances through large allocations
    one chunk at a time while continuing to cover address-ordered small regions.
    """
    chunk_size = max(4096, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    small_regions_per_large = max(1, int(small_regions_per_large))
    normalized = [tuple(region) for region in regions if int(region[1]) > 0]
    preferred_regions = []
    if preferred_size_range:
        preferred_min, preferred_max = (int(value) for value in preferred_size_range)
        preferred_regions = sorted(
            (
                region
                for region in normalized
                if preferred_min <= int(region[1]) <= preferred_max
            ),
            key=lambda region: int(region[0]),
        )
        preferred_keys = {(int(region[0]), int(region[1])) for region in preferred_regions}
        normalized = [
            region
            for region in normalized
            if (int(region[0]), int(region[1])) not in preferred_keys
        ]
    small_regions = sorted(
        (region for region in normalized if int(region[1]) <= chunk_size),
        key=lambda region: int(region[0]),
    )
    large_regions = sorted(
        (region for region in normalized if int(region[1]) > chunk_size),
        key=lambda region: (-int(region[1]), int(region[0])),
    )

    def large_chunks():
        step = chunk_size - overlap
        offset = 0
        while True:
            emitted = False
            for region in large_regions:
                base, size = int(region[0]), int(region[1])
                if offset >= size:
                    continue
                requested = min(chunk_size, size - offset)
                memory = read_region(pid, base + offset, requested, max_size=chunk_size)
                emitted = True
                if memory:
                    unique_size = len(memory) if offset == 0 else max(0, len(memory) - overlap)
                    yield region, base + offset, memory, unique_size
            if not emitted:
                break
            offset += step

    large_iter = iter(large_chunks())
    small_iter = iter(small_regions)
    for region in preferred_regions:
        base, size = int(region[0]), int(region[1])
        memory = read_region(pid, base, size, max_size=chunk_size)
        if memory:
            yield region, base, memory, len(memory)
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
                base, size = int(region[0]), int(region[1])
                memory = read_region(pid, base, size, max_size=chunk_size)
                if memory:
                    yield region, base, memory, len(memory)


def scan_typed_regions(pid, pattern, region_type, writable_only=False, alignment=1, stop_after=None):
    if not pattern:
        return []
    matches = []
    for base, size, _protect, _type in iter_regions(pid, type_filter=region_type, writable_only=writable_only):
        memory = read_region(pid, base, size)
        if not memory:
            continue
        start = 0
        while True:
            pos = memory.find(pattern, start)
            if pos == -1:
                break
            address = base + pos
            if alignment <= 1 or address % alignment == 0:
                matches.append(address)
                if stop_after and len(matches) >= stop_after:
                    return matches
            start = pos + max(1, alignment)
    return matches


def find_first_pattern_in_typed_regions(pid, patterns, region_type):
    patterns = [pattern for pattern in patterns if pattern]
    for base, size, _protect, _type in iter_regions(pid, type_filter=region_type, writable_only=False):
        memory = read_region(pid, base, size)
        if not memory:
            continue
        best = None
        for pattern in patterns:
            pos = memory.find(pattern)
            if pos == -1:
                continue
            if best is None or pos < best[0]:
                best = (pos, pattern)
        if best:
            pos, pattern = best
            return base + pos, pattern
    return None, None


def locate_calibrated_clivery_group_rtti(pid, profile, calibrated_profiles=None):
    if getattr(profile, "key", "") != "fh6":
        return None
    module_base = get_base_address(pid)
    module_size = read_pe_image_size(pid, module_base)
    profiles = calibrated_profiles if calibrated_profiles is not None else load_shared_rtti_profiles()
    record_locator_diagnostic(
        "rtti_profile",
        module_size=module_size,
        profile_count=len(profiles),
        matched=False,
    )
    for candidate in profiles:
        try:
            descriptor_offset = int(candidate["descriptor_offset"])
            vtable_offsets = [int(offset) for offset in candidate["vtable_offsets"]]
            update_code = str(candidate["update_code"]).encode("ascii", "strict").strip()
        except (KeyError, TypeError, ValueError, UnicodeEncodeError):
            continue
        descriptor_address = module_base + descriptor_offset
        try:
            found_code = read_process_memory(pid, descriptor_address + 0x10, len(update_code)).rstrip(b"\x00 ")
        except Exception:
            continue
        if not found_code or found_code != update_code.rstrip(b"\x00 "):
            continue
        source = str(candidate.get("_registry_source") or "profile")
        record_locator_diagnostic(
            "rtti_profile",
            module_size=module_size,
            profile_count=len(profiles),
            matched=True,
            registry_source=source,
            profile_id=candidate.get("profile_id"),
            game_build=candidate.get("game_build"),
        )
        print(f"Using verified FH6 group locator profile ({source}).", flush=True)
        return {
            "descriptor_address": descriptor_address,
            "descriptor_offset": descriptor_offset,
            "info_addresses": [],
            "vtables": [module_base + offset for offset in vtable_offsets],
            "source": "calibrated_profile",
            "registry_source": source,
            "profile_id": candidate.get("profile_id"),
            "update_code": update_code.decode("ascii", "replace"),
        }
    print("No shared FH6 locator profile matched this game build; trying fallback locator.", flush=True)
    return None


def locate_static_clivery_group_rtti(pid, profile):
    """Resolve a retired game's immutable RTTI profile with live validation."""
    descriptor_offset = int(getattr(profile, "static_rtti_descriptor_offset", 0) or 0)
    vtable_offsets = tuple(getattr(profile, "static_rtti_vtable_offsets", ()) or ())
    if not descriptor_offset or not vtable_offsets:
        return None

    module_base = get_base_address(pid)
    actual_module_size = read_pe_image_size(pid, module_base)
    expected_module_size = int(getattr(profile, "static_module_size", 0) or 0)
    game_name = str(getattr(profile, "key", "game")).upper()
    if expected_module_size and actual_module_size != expected_module_size:
        print(
            f"The packaged {game_name} locator does not match this executable build; "
            "trying the verified fallback locator.",
            flush=True,
        )
        return None

    descriptor_name = bytes(getattr(profile, "static_rtti_descriptor_name", b".?AVCLiveryGroup@@"))
    descriptor_address = module_base + descriptor_offset
    try:
        found_name = read_process_memory(pid, descriptor_address + 0x10, len(descriptor_name))
    except Exception:
        found_name = b""
    if found_name != descriptor_name:
        print(f"The packaged {game_name} RTTI descriptor did not validate; trying fallback.", flush=True)
        return None

    vtables = []
    module_end = module_base + int(actual_module_size or expected_module_size or 0)
    for offset in vtable_offsets:
        vtable = module_base + int(offset)
        try:
            locator = read_u64(pid, vtable - 8)
            signature = read_u32(pid, locator)
            type_descriptor_offset = read_u32(pid, locator + 0xC)
        except Exception:
            continue
        if module_end and not module_base <= locator < module_end:
            continue
        if signature != 1 or type_descriptor_offset != descriptor_offset:
            continue
        vtables.append(vtable)
    if not vtables:
        print(f"The packaged {game_name} vtable did not validate; trying fallback.", flush=True)
        return None

    build = str(getattr(profile, "static_build", "") or "final build")
    print(f"Using verified {game_name} static group locator ({build}).", flush=True)
    return {
        "descriptor_address": descriptor_address,
        "descriptor_offset": descriptor_offset,
        "info_addresses": [],
        "vtables": vtables,
        "source": "static_profile",
        "game_build": build,
        "module_size": actual_module_size,
    }


def locate_clivery_group_rtti(pid, profile=None):
    calibrated_profiles = (
        load_shared_rtti_profiles()
        if profile is not None and getattr(profile, "key", "") == "fh6"
        else []
    )
    static_profile = locate_static_clivery_group_rtti(pid, profile) if profile is not None else None
    if static_profile:
        return static_profile
    calibrated = (
        locate_calibrated_clivery_group_rtti(pid, profile, calibrated_profiles)
        if profile is not None
        else None
    )
    if calibrated:
        return calibrated
    patterns = load_update_code_patterns(calibrated_profiles, profile=profile)
    game_name = str(getattr(profile, "key", "FH6")).upper()
    print(f"Loaded {len(patterns)} {game_name} group locator pattern(s).", flush=True)
    descriptor_match, descriptor_pattern = find_first_pattern_in_typed_regions(pid, patterns, MEM_IMAGE)
    descriptor_address = descriptor_match - 0x10 if descriptor_match else None
    if not descriptor_address:
        print("Fast locator pattern was not found; trying layout-count fallback.", flush=True)
        return None

    module_base = get_base_address(pid)
    descriptor_offset = descriptor_address - module_base
    if not 0 <= descriptor_offset <= 0xFFFFFFFF:
        print("Fast locator candidate is outside the main module.", flush=True)
        return None
    print("Fast locator candidate found.", flush=True)

    info_pattern = struct.pack("<I", descriptor_offset)
    info_addresses = []
    for address in scan_typed_regions(pid, info_pattern, MEM_IMAGE, writable_only=False, alignment=4):
        info_address = address - 0xC
        try:
            signature = read_process_memory(pid, info_address, 1)
        except Exception:
            signature = b""
        # MSVC x64 CompleteObjectLocator starts with signature 1.
        if signature == b"\x01":
            info_addresses.append(info_address)
    info_addresses = sorted(set(info_addresses))
    print(f"Info found: {len(info_addresses)}", flush=True)
    if not info_addresses:
        return None

    vtables = []
    for info_address in info_addresses:
        pattern = struct.pack("<Q", info_address)
        for address in scan_typed_regions(pid, pattern, MEM_IMAGE, writable_only=False, alignment=8):
            vtables.append(address + 8)
    vtables = sorted(set(vtables))
    print(f"Group type candidates found: {len(vtables)}", flush=True)
    if not vtables:
        return None

    fixed_patterns = tuple(getattr(profile, "fixed_rtti_descriptor_names", ()) or ())
    return {
        "descriptor_address": descriptor_address,
        "descriptor_offset": descriptor_offset,
        "info_addresses": info_addresses,
        "vtables": vtables,
        "source": "fixed_profile_pattern" if descriptor_pattern in fixed_patterns else "pattern_scan",
        "update_code": descriptor_pattern.decode("ascii", "replace") if descriptor_pattern else None,
    }


def build_clivery_group_candidate(pid, profile, layer_count, rtti, group_address, vtable, count_kind):
    count_address = group_address + profile.livery_count_offset
    table_field = group_address + profile.layer_table_offset
    try:
        current_count = read_u16(pid, count_address)
        table_address = read_u64(pid, table_field)
    except Exception:
        return None
    if current_count != layer_count:
        return None
    if not table_address or not is_user_pointer(table_address):
        return None
    if not is_private_writable_address(pid, table_address):
        return None
    vector_ok, vector = validate_group_vector(pid, profile, group_address, table_address, layer_count)
    if not vector_ok:
        return None
    score, samples = score_table(pid, profile, table_address, min(layer_count, 64))
    if score <= 0:
        return None
    ok, checked, valid_entries = validate_table_layer_coverage(pid, profile, table_address, layer_count)
    if not ok:
        print(
            f"Rejected calibrated group candidate: exact layer validation {valid_entries}/{layer_count}, checked={checked}",
            flush=True,
        )
        return None
    shape_word_counts = {}
    if (
        int(getattr(profile, "import_template_shape_word", -1)) >= 0
        and float(getattr(profile, "import_template_min_ratio", 0.0)) > 0
    ):
        shape_word_counts = table_shape_word_counts(pid, profile, table_address, layer_count)
    return {
        "score": score + 120,
        "group_address": group_address,
        "count_address": count_address,
        "table_pointer_field": table_field,
        "table_address": table_address,
        "count_kind": count_kind,
        "current_u16": current_count,
        "current_u32": current_count,
        "samples": samples,
        "validated_entries": valid_entries,
        "shape_word_counts": shape_word_counts,
        "vector_count": vector.get("vector_count"),
        "capacity_count": vector.get("capacity_count"),
        "vtable": vtable,
        "rtti_source": rtti.get("source") or "pattern_scan",
        "rtti_update_code": rtti.get("update_code"),
        "rtti_descriptor_offset": rtti.get("descriptor_offset"),
    }


def locate_clivery_groups_by_calibrated_count(pid, profile, layer_count, rtti, max_seconds=20, max_count_hits=250000):
    """Use the calibrated vtable as a direct validator for count-offset candidates."""
    vtables = set(rtti.get("vtables") or [])
    if not vtables:
        return []
    started = time.monotonic()
    pattern = struct.pack("<H", layer_count)
    regions = list(iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True))
    writable_contains = build_region_contains(regions)
    total_bytes = sum(int(region[1]) for region in regions)
    scanned = 0
    hits = 0
    next_progress = 512 * 1024 * 1024
    stopped_by_time = False
    for region, chunk_base, memory, unique_size in iter_balanced_region_chunks(
        pid,
        regions,
        chunk_size=FH6_COUNT_SCAN_CHUNK_SIZE,
        overlap=len(pattern) - 1,
    ):
        if max_seconds and time.monotonic() - started > max_seconds:
            print(f"Stopped calibrated locator count scan after {max_seconds} seconds.", flush=True)
            stopped_by_time = True
            break
        scanned += unique_size
        if scanned >= next_progress:
            print(
                f"Calibrated locator count scan checked {scanned // (1024 * 1024)} MB, "
                f"count hits={hits}.",
                flush=True,
            )
            next_progress += 512 * 1024 * 1024
        region_base = int(region[0])
        start = 0
        while True:
            pos = memory.find(pattern, start)
            if pos == -1:
                break
            start = pos + 1
            hits += 1
            if hits % 4096 == 0 and max_seconds and time.monotonic() - started > max_seconds:
                print(f"Stopped calibrated locator count scan after {max_seconds} seconds.", flush=True)
                stopped_by_time = True
                break
            if hits > max_count_hits:
                print(f"Stopped calibrated locator count scan after {max_count_hits} count hits.", flush=True)
                record_locator_diagnostic(
                    "calibrated_count",
                    scanned_mb=scanned // (1024 * 1024),
                    total_mb=total_bytes // (1024 * 1024),
                    count_hits=hits,
                    stopped_by="hit_limit",
                )
                return []
            count_address = chunk_base + pos
            group_address = count_address - profile.livery_count_offset
            if group_address < region_base:
                continue
            vtable = read_u64(pid, group_address)
            if vtable not in vtables:
                continue
            group_info = read_calibrated_group_vector(
                pid,
                profile,
                group_address,
                vtables,
                max_vector_count=3000,
                writable_contains=writable_contains,
            )
            if not group_info or group_info.get("parent_group"):
                continue
            access = assess_calibrated_group_access(
                pid,
                profile,
                group_info,
                vtables,
                writable_contains=writable_contains,
            )
            if access is not None and not access.allowed:
                raise LocatorRefused(
                    access.reason,
                    {"matched_group_count": 1, "access_status": access.status},
                )
            candidate = None
            if int(group_info.get("vector_count") or -1) == int(layer_count):
                candidate = build_clivery_group_candidate(
                    pid,
                    profile,
                    layer_count,
                    rtti,
                    group_address,
                    vtable,
                    "u16_rtti_calibrated_count",
                )
            else:
                flat = flatten_calibrated_group(
                    pid,
                    profile,
                    group_info,
                    vtables,
                    layer_count,
                    writable_contains=writable_contains,
                )
                if flat["shape_count"] == layer_count and flat["invalid_count"] == 0:
                    candidate = {
                        "score": 400 + min(layer_count, 3000) + flat["group_count"] * 10,
                        "group_address": group_info["group_address"],
                        "count_address": group_info["count_address"],
                        "table_pointer_field": group_info["table_pointer_field"],
                        "table_address": group_info["table_address"],
                        "count_kind": "u16_rtti_calibrated_recursive",
                        "current_u16": group_info.get("current_u16"),
                        "current_u32": group_info.get("current_u32"),
                        "samples": flat["samples"],
                        "validated_entries": flat["shape_count"],
                        "vector_count": group_info["vector_count"],
                        "capacity_count": group_info["capacity_count"],
                        "top_vector_count": group_info["vector_count"],
                        "flattened_from_groups": True,
                        "flattened_group_count": flat["group_count"],
                        "flattened_max_depth": flat["max_depth"],
                        "group_graph": {
                            "has_parent": False,
                            "has_children": True,
                            "is_flat_orphan": False,
                            "parent_count": 0,
                            "child_count": max(1, flat["group_count"] - 1),
                        },
                        "vtable": group_info["vtable"],
                        "rtti_source": rtti.get("source") or "pattern_scan",
                        "rtti_update_code": rtti.get("update_code"),
                        "rtti_descriptor_offset": rtti.get("descriptor_offset"),
                    }
                    candidate.update(flattened_import_target(flat, layer_count))
            if candidate:
                candidate["export_access_verified"] = access is None or access.allowed
                record_locator_diagnostic(
                    "calibrated_count",
                    scanned_mb=scanned // (1024 * 1024),
                    total_mb=total_bytes // (1024 * 1024),
                    count_hits=hits,
                    stopped_by="match",
                )
                print(
                    f"Calibrated group candidate validated {candidate['validated_entries']}/{layer_count} layer(s).",
                    flush=True,
                )
                return [candidate]
        if stopped_by_time:
            break
    print(
        f"Calibrated locator count scan checked {scanned // (1024 * 1024)} MB, "
        f"count hits={hits}, candidates=0.",
        flush=True,
    )
    record_locator_diagnostic(
        "calibrated_count",
        scanned_mb=scanned // (1024 * 1024),
        total_mb=total_bytes // (1024 * 1024),
        count_hits=hits,
        stopped_by="time_limit" if stopped_by_time else "complete",
    )
    return []


def read_calibrated_group_vector(
    pid,
    profile,
    group_address,
    vtables,
    max_vector_count=3000,
    writable_contains=None,
):
    contains = writable_contains or (lambda address, size=1: is_private_writable_address(pid, address))
    if not group_address or not contains(group_address, profile.layer_table_offset + 24):
        return None
    try:
        vtable = read_u64(pid, group_address)
    except Exception:
        return None
    if vtable not in vtables:
        return None
    table_address = read_u64(pid, group_address + profile.layer_table_offset)
    table_end = read_u64(pid, group_address + profile.layer_table_offset + 8)
    table_capacity = read_u64(pid, group_address + profile.layer_table_offset + 16)
    count_u16 = read_u16(pid, group_address + profile.livery_count_offset)
    parent_group = read_u64(pid, group_address + 0x60)
    if not table_address or table_end is None or table_capacity is None:
        return None
    if not is_user_pointer(table_address) or not contains(table_address, 1):
        return None
    if table_end < table_address or table_capacity < table_end:
        return None
    if (table_end - table_address) % 8 or (table_capacity - table_address) % 8:
        return None
    vector_count = (table_end - table_address) // 8
    capacity_count = (table_capacity - table_address) // 8
    if vector_count <= 0 or vector_count > max_vector_count:
        return None
    if capacity_count < vector_count or capacity_count > max(max_vector_count + 10000, max_vector_count * 16):
        return None
    if not contains(table_address, max(1, vector_count * 8)) or not contains(table_capacity - 1, 1):
        return None
    return {
        "group_address": group_address,
        "count_address": group_address + profile.livery_count_offset,
        "table_pointer_field": group_address + profile.layer_table_offset,
        "table_address": table_address,
        "table_end": table_end,
        "table_capacity": table_capacity,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "current_u16": count_u16,
        "current_u32": count_u16,
        "vtable": vtable,
        "parent_group": parent_group or 0,
    }


def assess_calibrated_group_access(pid, profile, group_info, vtables, writable_contains=None):
    if profile.key not in LIVE_OWNERSHIP_GAMES:
        return None

    def read_header(address):
        try:
            return read_process_memory(pid, address, MIN_HEADER_SIZE)
        except Exception:
            return b""

    def read_group(address):
        if writable_contains is None:
            return read_calibrated_group_vector(
                pid,
                profile,
                address,
                vtables,
                max_vector_count=3000,
            )
        return read_calibrated_group_vector(
            pid,
            profile,
            address,
            vtables,
            max_vector_count=3000,
            writable_contains=writable_contains,
        )

    def read_children(address):
        info = read_group(address)
        if not info:
            raise RuntimeError("live group vector is unreadable")
        children = []
        for ptr in read_group_pointer_table(pid, info["table_address"], info["vector_count"]):
            child = read_group(ptr)
            if child:
                if int(child.get("parent_group") or 0) != int(address):
                    raise RuntimeError("live child group parent link is inconsistent")
                children.append(ptr)
        return children

    return assess_group_tree(
        group_info["group_address"],
        read_header,
        read_children,
        allow_transformed_child_state=profile.key == "fh5",
    )


def read_group_pointer_table(pid, table_address, count):
    count = max(0, min(int(count), 3000))
    if not count:
        return []
    try:
        raw = read_process_memory(pid, table_address, count * 8)
    except Exception:
        raw = b""
    if len(raw) == count * 8:
        return list(struct.unpack(f"<{count}Q", raw))
    pointers = []
    for index in range(count):
        try:
            pointers.append(read_pointer(pid, table_address + index * 8))
        except Exception:
            pointers.append(0)
    return pointers


def locate_clivery_groups_by_calibrated_graph(pid, profile, layer_count, rtti, max_seconds=18, accept_cap=FH6_GROUP_GRAPH_ACCEPT_CAP):
    """Build a compact CLiveryGroup graph and accept only exact-count flat orphans."""
    vtables = set(rtti.get("vtables") or [])
    if not vtables:
        return []

    started = time.monotonic()
    patterns = [(vtable, struct.pack("<Q", vtable)) for vtable in vtables]
    instances = {}
    scanned = 0
    vtable_hits = 0
    stopped_by_time = False

    for base, size, _protect, _type in iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True):
        if max_seconds and time.monotonic() - started > max_seconds:
            stopped_by_time = True
            break
        memory = read_region(pid, base, size)
        if not memory:
            continue
        scanned += len(memory)
        for vtable, pattern in patterns:
            start = 0
            while True:
                pos = memory.find(pattern, start)
                if pos == -1:
                    break
                start = pos + 8
                if pos % 8:
                    continue
                vtable_hits += 1
                group_address = base + pos
                if group_address in instances:
                    continue
                info = read_calibrated_group_vector(pid, profile, group_address, vtables, max_vector_count=3000)
                if not info:
                    continue
                count_u16 = int(info.get("current_u16") or 0)
                vector_count = int(info.get("vector_count") or 0)
                if not (1 <= count_u16 <= 3000) or not (1 <= vector_count <= 3000):
                    continue
                pointer_count = min(vector_count, 3000)
                pointers = read_group_pointer_table(pid, info["table_address"], pointer_count)
                valid_pointer_count = sum(1 for ptr in pointers if is_private_writable_address(pid, ptr))
                if valid_pointer_count <= 0:
                    continue
                info["table_pointers"] = pointers
                info["valid_pointer_count"] = valid_pointer_count
                instances[group_address] = info
                if len(instances) > FH6_GROUP_GRAPH_SCAN_CAP:
                    details = {
                        "global_group_count": len(instances),
                        "global_group_cap": FH6_GROUP_GRAPH_SCAN_CAP,
                        "scanned_mb": scanned // (1024 * 1024),
                        "vtable_hits": vtable_hits,
                    }
                    raise LocatorRefused(
                        "KFPS found too many live group structures to identify the open vinyl safely.",
                        details,
                    )

    group_addresses = set(instances)
    for group_address, info in instances.items():
        ptrs = set(info.get("table_pointers") or [])
        parents = [parent for parent, parent_info in instances.items() if parent != group_address and group_address in set(parent_info.get("table_pointers") or [])]
        header_parent = int(info.get("parent_group") or 0)
        if header_parent and header_parent not in parents:
            parents.append(header_parent)
        children = [child for child in group_addresses if child != group_address and child in ptrs]
        info["group_graph"] = {
            "has_parent": bool(parents),
            "has_children": bool(children),
            "is_flat_orphan": not parents and not children,
            "parent_count": len(parents),
            "child_count": len(children),
        }

    exact_groups = [info for info in instances.values() if int(info.get("current_u16") or 0) == int(layer_count)]
    groups = []
    access_refusals = []
    for info in exact_groups:
        if int(info.get("vector_count") or -1) != int(layer_count):
            continue
        graph = info.get("group_graph") or {}
        if not graph.get("is_flat_orphan"):
            continue
        access = assess_calibrated_group_access(pid, profile, info, vtables)
        if access is not None and not access.allowed:
            access_refusals.append(access)
            continue
        candidate = build_clivery_group_candidate(
            pid,
            profile,
            layer_count,
            rtti,
            info["group_address"],
            info["vtable"],
            "rtti_group_graph_flat_orphan",
        )
        if not candidate:
            continue
        candidate["group_graph"] = graph
        candidate["group_graph_complete"] = not stopped_by_time
        candidate["group_graph_partial"] = bool(stopped_by_time)
        candidate["global_group_count"] = len(instances)
        candidate["graph_scan_mb"] = scanned // (1024 * 1024)
        candidate["export_access_verified"] = access is None or access.allowed
        groups.append(candidate)

    for info in exact_groups:
        graph = info.get("group_graph") or {}
        if graph.get("has_parent") or not graph.get("has_children"):
            continue
        flat = flatten_calibrated_group(pid, profile, info, vtables, layer_count)
        if flat["shape_count"] != layer_count or flat["invalid_count"]:
            continue
        access = assess_calibrated_group_access(pid, profile, info, vtables)
        if access is not None and not access.allowed:
            access_refusals.append(access)
            continue
        candidate = {
            "score": 400 + min(layer_count, 3000) + flat["group_count"] * 10,
            "group_address": info["group_address"],
            "count_address": info["count_address"],
            "table_pointer_field": info["table_pointer_field"],
            "table_address": info["table_address"],
            "count_kind": "rtti_group_graph_recursive",
            "current_u16": info.get("current_u16"),
            "current_u32": info.get("current_u32"),
            "samples": flat["samples"],
            "validated_entries": flat["shape_count"],
            "vector_count": info["vector_count"],
            "capacity_count": info["capacity_count"],
            "top_vector_count": info["vector_count"],
            "flattened_from_groups": True,
            "flattened_group_count": flat["group_count"],
            "flattened_max_depth": flat["max_depth"],
            "group_graph": graph,
            "group_graph_complete": not stopped_by_time,
            "group_graph_partial": bool(stopped_by_time),
            "global_group_count": len(instances),
            "graph_scan_mb": scanned // (1024 * 1024),
            "vtable": info["vtable"],
            "rtti_source": rtti.get("source") or "pattern_scan",
            "rtti_update_code": rtti.get("update_code"),
            "rtti_descriptor_offset": rtti.get("descriptor_offset"),
            "export_access_verified": access is None or access.allowed,
        }
        candidate.update(flattened_import_target(flat, layer_count))
        groups.append(candidate)

    groups.sort(key=lambda item: item["score"], reverse=True)
    if groups:
        suffix = " from partial graph" if stopped_by_time else ""
        print(
            f"Calibrated group graph accepted {len(groups[:accept_cap])} verified candidate(s){suffix}.",
            flush=True,
        )
    elif instances:
        print(
            f"Calibrated group graph found {len(instances)} group(s), no exact verified candidate.",
            flush=True,
        )
    if not groups and access_refusals:
        refusal = access_refusals[0]
        raise LocatorRefused(
            refusal.reason,
            {
                "matched_group_count": len(access_refusals),
                "access_status": refusal.status,
            },
        )
    return groups[:accept_cap]


def flatten_calibrated_group(
    pid,
    profile,
    group_info,
    vtables,
    requested_count,
    depth=0,
    seen_groups=None,
    writable_contains=None,
):
    if seen_groups is None:
        seen_groups = set()
    group_address = group_info["group_address"]
    if group_address in seen_groups or depth > 12:
        return {
            "shape_count": 0,
            "invalid_count": 1,
            "group_count": 0,
            "max_depth": depth,
            "samples": [],
            "leaf_groups": [],
        }
    seen_groups.add(group_address)
    shape_count = 0
    invalid_count = 0
    group_count = 1
    max_depth = depth
    samples = []
    leaf_groups = []
    direct_shape_count = 0
    child_group_count = 0
    table_address = group_info["table_address"]
    vector_count = group_info["vector_count"]
    contains = writable_contains or (lambda address, size=1: is_private_writable_address(pid, address))
    pointers = read_group_pointer_table(pid, table_address, vector_count)
    for ptr in pointers:
        if not contains(ptr, 1):
            invalid_count += 1
            continue
        child_info = read_calibrated_group_vector(
            pid,
            profile,
            ptr,
            vtables,
            max_vector_count=max(3000, requested_count),
            writable_contains=contains,
        )
        if child_info:
            child_group_count += 1
            child = flatten_calibrated_group(
                pid,
                profile,
                child_info,
                vtables,
                requested_count,
                depth=depth + 1,
                seen_groups=seen_groups,
                writable_contains=contains,
            )
            shape_count += child["shape_count"]
            invalid_count += child["invalid_count"]
            group_count += child["group_count"]
            max_depth = max(max_depth, child["max_depth"])
            samples.extend(child["samples"])
            leaf_groups.extend(child.get("leaf_groups") or [])
        elif export_layer_pointer_ok(pid, ptr, profile):
            shape_count += 1
            direct_shape_count += 1
            if len(samples) < 16:
                layer_score, checks = score_layer_pointer(pid, ptr, profile)
                samples.append((shape_count - 1, ptr, max(layer_score, 3), checks or ["export-layer"]))
        else:
            invalid_count += 1
        if shape_count > requested_count and invalid_count:
            break
    if child_group_count == 0 and invalid_count == 0 and direct_shape_count == vector_count:
        leaf_groups.append({
            "group_address": group_info["group_address"],
            "count_address": group_info["count_address"],
            "table_pointer_field": group_info["table_pointer_field"],
            "table_address": group_info["table_address"],
            "vector_count": group_info["vector_count"],
            "capacity_count": group_info["capacity_count"],
            "shape_count": direct_shape_count,
        })
    candidate = {
        "shape_count": shape_count,
        "invalid_count": invalid_count,
        "group_count": group_count,
        "max_depth": max_depth,
        "samples": samples,
        "leaf_groups": leaf_groups,
    }
    return candidate


def flattened_import_target(flat, requested_count):
    """Return the only direct layer vector that can safely receive an import."""
    matches = [
        item
        for item in (flat.get("leaf_groups") or [])
        if int(item.get("shape_count") or 0) == int(requested_count)
        and int(item.get("vector_count") or 0) == int(requested_count)
    ]
    if len(matches) != 1:
        return {}
    target = matches[0]
    return {
        "import_group_address": target["group_address"],
        "import_count_address": target["count_address"],
        "import_table_pointer_field": target["table_pointer_field"],
        "import_table_address": target["table_address"],
        "import_vector_count": target["vector_count"],
        "import_capacity_count": target["capacity_count"],
        "import_target_verified": True,
    }


def regions_in_allocator_windows(regions, windows):
    selected = []
    for base, size, protect, region_type in regions:
        region_end = int(base) + int(size)
        for window_start, window_end in windows:
            start = max(int(base), int(window_start))
            end = min(region_end, int(window_end))
            if end > start:
                selected.append((start, end - start, protect, region_type))
    return selected


def evaluate_exact_calibrated_root(
    pid,
    profile,
    layer_count,
    rtti,
    group_address,
    writable_contains,
    *,
    locator_kind,
):
    vtables = set(rtti.get("vtables") or [])
    group_info = read_calibrated_group_vector(
        pid,
        profile,
        int(group_address),
        vtables,
        max_vector_count=max(3000, layer_count),
        writable_contains=writable_contains,
    )
    if not group_info or int(group_info.get("parent_group") or 0) != 0:
        return None, None
    if int(group_info.get("current_u16") or -1) != int(layer_count):
        return None, None
    access = assess_calibrated_group_access(
        pid,
        profile,
        group_info,
        vtables,
        writable_contains=writable_contains,
    )
    if access is not None and not access.allowed:
        return None, access
    flat = flatten_calibrated_group(
        pid,
        profile,
        group_info,
        vtables,
        layer_count,
        writable_contains=writable_contains,
    )
    if int(flat["shape_count"]) != int(layer_count) or int(flat["invalid_count"]):
        return None, None
    is_recursive = int(flat["group_count"]) > 1
    candidate = {
        "score": 500 + min(layer_count, 3000) + int(flat["group_count"]) * 10,
        "group_address": group_info["group_address"],
        "count_address": group_info["count_address"],
        "table_pointer_field": group_info["table_pointer_field"],
        "table_address": group_info["table_address"],
        "count_kind": locator_kind,
        "current_u16": group_info.get("current_u16"),
        "current_u32": group_info.get("current_u32"),
        "samples": flat["samples"],
        "validated_entries": flat["shape_count"],
        "vector_count": group_info["vector_count"],
        "capacity_count": group_info["capacity_count"],
        "top_vector_count": group_info["vector_count"],
        "flattened_from_groups": is_recursive,
        "flattened_group_count": flat["group_count"],
        "flattened_max_depth": flat["max_depth"],
        "group_graph": {
            "has_parent": False,
            "has_children": is_recursive,
            "is_flat_orphan": not is_recursive,
            "parent_count": 0,
            "child_count": max(0, int(flat["group_count"]) - 1),
        },
        "vtable": group_info["vtable"],
        "rtti_source": rtti.get("source") or "pattern_scan",
        "rtti_update_code": rtti.get("update_code"),
        "rtti_descriptor_offset": rtti.get("descriptor_offset"),
        "export_access_verified": access is None or access.allowed,
    }
    candidate.update(flattened_import_target(flat, layer_count))
    return candidate, None


def scan_exact_calibrated_vtables(
    pid,
    profile,
    layer_count,
    rtti,
    all_regions,
    scan_regions,
    *,
    diagnostic_name,
    locator_kind,
    stop_on_candidate=False,
    progress_mb=512,
):
    vtables = set(rtti.get("vtables") or [])
    if not vtables:
        return [], [], {"complete": True, "failed_regions": []}
    patterns = [(vtable, struct.pack("<Q", vtable)) for vtable in vtables]
    writable_contains = build_region_contains(all_regions)
    total_bytes = sum(int(region[1]) for region in scan_regions)
    scanned = 0
    failed_bytes = 0
    raw_hits = 0
    seen_groups = set()
    candidates = {}
    refusals = []
    failed_regions = []
    started = time.monotonic()
    next_progress = max(1, int(progress_mb)) * 1024 * 1024

    for base, size, protect, region_type in scan_regions:
        overlap = 7
        offset = 0
        first_chunk = True
        while offset < int(size):
            requested = min(FH6_REGION_SCAN_CHUNK_SIZE, int(size) - offset)
            chunk_base = int(base) + offset
            memory = read_region(
                pid,
                chunk_base,
                requested,
                max_size=FH6_REGION_SCAN_CHUNK_SIZE,
            )
            unique_size = requested if first_chunk else max(0, requested - overlap)
            first_chunk = False
            if not memory:
                failed_bytes += unique_size
                failed_regions.append((chunk_base, requested, protect, region_type))
            else:
                scanned += unique_size
                for _vtable, pattern in patterns:
                    start = 0
                    while True:
                        position = memory.find(pattern, start)
                        if position == -1:
                            break
                        start = position + 8
                        group_address = chunk_base + position
                        if group_address % 8 or group_address in seen_groups:
                            continue
                        seen_groups.add(group_address)
                        raw_hits += 1
                        candidate, refusal = evaluate_exact_calibrated_root(
                            pid,
                            profile,
                            layer_count,
                            rtti,
                            group_address,
                            writable_contains,
                            locator_kind=locator_kind,
                        )
                        if candidate:
                            candidates[int(candidate["group_address"])] = candidate
                            if stop_on_candidate:
                                stats = {
                                    "scanned_mb": scanned // (1024 * 1024),
                                    "total_mb": total_bytes // (1024 * 1024),
                                    "failed_mb": failed_bytes // (1024 * 1024),
                                    "vtable_hits": raw_hits,
                                    "candidate_count": len(candidates),
                                    "complete": False,
                                    "stopped_by": "match",
                                    "elapsed_seconds": round(time.monotonic() - started, 3),
                                    "failed_regions": failed_regions,
                                }
                                record_locator_diagnostic(
                                    diagnostic_name,
                                    **{key: value for key, value in stats.items() if key != "failed_regions"},
                                )
                                return list(candidates.values()), refusals, stats
                        elif refusal is not None:
                            refusals.append(refusal)
            if scanned + failed_bytes >= next_progress:
                print(
                    f"Exact RTTI recovery checked {(scanned + failed_bytes) // (1024 * 1024)}/"
                    f"{max(1, total_bytes // (1024 * 1024))} MB, type hits={raw_hits}.",
                    flush=True,
                )
                next_progress += max(1, int(progress_mb)) * 1024 * 1024
            if offset + requested >= int(size) or requested <= overlap:
                break
            offset += requested - overlap

    complete = failed_bytes == 0 and scanned >= total_bytes
    stats = {
        "scanned_mb": scanned // (1024 * 1024),
        "total_mb": total_bytes // (1024 * 1024),
        "failed_mb": failed_bytes // (1024 * 1024),
        "vtable_hits": raw_hits,
        "candidate_count": len(candidates),
        "complete": complete,
        "stopped_by": "complete" if complete else "read_failure",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "failed_regions": failed_regions,
    }
    record_locator_diagnostic(
        diagnostic_name,
        **{key: value for key, value in stats.items() if key != "failed_regions"},
    )
    return list(candidates.values()), refusals, stats


def finish_incomplete_exact_scan(
    pid,
    profile,
    layer_count,
    rtti,
    all_regions,
    candidates,
    refusals,
    stats,
    *,
    diagnostic_name,
    locator_kind,
):
    if stats.get("complete"):
        return candidates, refusals
    failed_regions = stats.get("failed_regions") or []
    if not failed_regions:
        raise LocatorRefused(
            "KFPS could not prove complete coverage of the FH6 livery allocator.",
            {"scan_status": stats.get("stopped_by") or "incomplete"},
        )
    print("Retrying FH6 livery allocator pages that changed during the scan.", flush=True)
    retry_candidates, retry_refusals, retry_stats = scan_exact_calibrated_vtables(
        pid,
        profile,
        layer_count,
        rtti,
        all_regions,
        failed_regions,
        diagnostic_name=diagnostic_name,
        locator_kind=locator_kind,
    )
    candidates.extend(retry_candidates)
    refusals.extend(retry_refusals)
    if not retry_stats.get("complete"):
        raise LocatorRefused(
            "KFPS could not read every eligible FH6 livery allocator page.",
            {
                "failed_mb": retry_stats.get("failed_mb"),
                "vtable_hits": retry_stats.get("vtable_hits"),
            },
        )
    return candidates, refusals


def select_exact_calibrated_candidate(candidates):
    unique = {int(item["group_address"]): item for item in candidates}
    if len(unique) == 1:
        return next(iter(unique.values()))
    if len(unique) > 1:
        raise LocatorRefused(
            "KFPS found multiple exact live FH6 groups with the requested layer count.",
            {"matched_group_count": len(unique)},
        )
    return None


def locate_clivery_group_by_allocator(pid, profile, layer_count, rtti):
    all_regions = list(iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True))
    cache = load_fh6_allocator_cache(rtti)
    learned_windows = normalize_allocator_windows(cache.get("windows"))
    record_locator_diagnostic(
        "calibrated_allocator_cache",
        learned_window_count=len(learned_windows),
    )

    allocator_windows = normalize_allocator_windows(
        [*FH6_DEFAULT_ALLOCATOR_WINDOWS, *learned_windows]
    )
    allocator_regions = regions_in_allocator_windows(all_regions, allocator_windows)
    print(
        f"Searching the FH6 livery allocator ({sum(region[1] for region in allocator_regions) // (1024 * 1024)} MB committed).",
        flush=True,
    )
    candidates, refusals, allocator_stats = scan_exact_calibrated_vtables(
        pid,
        profile,
        layer_count,
        rtti,
        all_regions,
        allocator_regions,
        diagnostic_name="calibrated_allocator",
        locator_kind="rtti_allocator_exact",
    )
    candidates, refusals = finish_incomplete_exact_scan(
        pid,
        profile,
        layer_count,
        rtti,
        all_regions,
        candidates,
        refusals,
        allocator_stats,
        diagnostic_name="calibrated_allocator_retry",
        locator_kind="rtti_allocator_exact_retry",
    )
    winner = select_exact_calibrated_candidate(candidates)
    if winner:
        save_fh6_allocator_cache(
            rtti,
            [*allocator_windows, allocator_window_for_address(winner["group_address"])],
        )
        print("FH6 group resolved from the dedicated livery allocator.", flush=True)
        return [winner]

    print(
        "The active group was not in a known allocator window. Running one complete exact-RTTI recovery scan.",
        flush=True,
    )
    recovery_candidates, recovery_refusals, recovery_stats = scan_exact_calibrated_vtables(
        pid,
        profile,
        layer_count,
        rtti,
        all_regions,
        all_regions,
        diagnostic_name="calibrated_exact_recovery",
        locator_kind="rtti_exact_recovery",
        stop_on_candidate=True,
    )
    refusals.extend(recovery_refusals)
    if recovery_candidates:
        discovered_window = allocator_window_for_address(recovery_candidates[0]["group_address"])
        discovered_regions = regions_in_allocator_windows(all_regions, [discovered_window])
        verified_candidates, verified_refusals, verified_stats = scan_exact_calibrated_vtables(
            pid,
            profile,
            layer_count,
            rtti,
            all_regions,
            discovered_regions,
            diagnostic_name="calibrated_discovered_allocator",
            locator_kind="rtti_discovered_allocator_exact",
        )
        verified_candidates, verified_refusals = finish_incomplete_exact_scan(
            pid,
            profile,
            layer_count,
            rtti,
            all_regions,
            verified_candidates,
            verified_refusals,
            verified_stats,
            diagnostic_name="calibrated_discovered_allocator_retry",
            locator_kind="rtti_discovered_allocator_exact_retry",
        )
        refusals.extend(verified_refusals)
        winner = select_exact_calibrated_candidate(verified_candidates)
        if winner:
            save_fh6_allocator_cache(
                rtti,
                [*allocator_windows, discovered_window],
            )
            print("FH6 group resolved and its allocator window was cached for this build.", flush=True)
            return [winner]

    if not recovery_stats.get("complete"):
        retry_regions = recovery_stats.get("failed_regions") or []
        if retry_regions:
            print("Retrying memory pages that changed during the exact RTTI scan.", flush=True)
            retry_candidates, retry_refusals, retry_stats = scan_exact_calibrated_vtables(
                pid,
                profile,
                layer_count,
                rtti,
                all_regions,
                retry_regions,
                diagnostic_name="calibrated_exact_retry",
                locator_kind="rtti_exact_retry",
            )
            refusals.extend(retry_refusals)
            winner = select_exact_calibrated_candidate(retry_candidates)
            if winner:
                discovered_window = allocator_window_for_address(winner["group_address"])
                save_fh6_allocator_cache(
                    rtti,
                    [*allocator_windows, discovered_window],
                )
                return [winner]
            if not retry_stats.get("complete"):
                raise LocatorRefused(
                    "KFPS could not read every eligible FH6 memory page during exact RTTI recovery.",
                    {
                        "failed_mb": retry_stats.get("failed_mb"),
                        "vtable_hits": retry_stats.get("vtable_hits"),
                    },
                )

    if refusals:
        refusal = refusals[0]
        raise LocatorRefused(
            refusal.reason,
            {"matched_group_count": len(refusals), "access_status": refusal.status},
        )
    record_locator_diagnostic(
        "calibrated_exact_authoritative",
        complete=True,
        active_group_found=False,
    )
    return []


def locate_clivery_groups_by_calibrated_flattened(pid, profile, layer_count, rtti, max_seconds=12):
    """Directly scan for verified group vtables, then validate one exact root tree."""
    vtables = set(rtti.get("vtables") or [])
    if not vtables:
        return []
    started = time.monotonic()
    patterns = [(vtable, struct.pack("<Q", vtable)) for vtable in vtables]
    regions = list(iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True))
    writable_contains = build_region_contains(regions)
    total_bytes = sum(int(region[1]) for region in regions)
    scanned = 0
    hits = 0
    best_miss = None
    seen_groups = set()
    stopped_by_time = False
    scheduled_chunks = iter_balanced_region_chunks(
        pid,
        regions,
        overlap=7,
        preferred_size_range=(FH6_GROUP_ARENA_MIN_SIZE, FH6_GROUP_ARENA_MAX_SIZE),
    )
    for chunk_index, (_region, chunk_base, memory, unique_size) in enumerate(scheduled_chunks, start=1):
        if max_seconds and time.monotonic() - started > max_seconds:
            print(f"Stopped calibrated flattened-group scan after {max_seconds} seconds.", flush=True)
            stopped_by_time = True
            break
        scanned += unique_size
        for vtable, pattern in patterns:
            start = 0
            while True:
                pos = memory.find(pattern, start)
                if pos == -1:
                    break
                start = pos + 8
                hits += 1
                group_address = chunk_base + pos
                if group_address % 8 or group_address in seen_groups:
                    continue
                seen_groups.add(group_address)
                group_info = read_calibrated_group_vector(
                    pid,
                    profile,
                    group_address,
                    vtables,
                    max_vector_count=max(3000, layer_count),
                    writable_contains=writable_contains,
                )
                if not group_info or int(group_info.get("parent_group") or 0) != 0:
                    continue
                # The count field stores the flattened shape total. A grouped
                # root can legitimately have a one-entry child vector.
                if int(group_info.get("current_u16") or -1) != int(layer_count):
                    continue
                access = assess_calibrated_group_access(
                    pid,
                    profile,
                    group_info,
                    vtables,
                    writable_contains=writable_contains,
                )
                if access is not None and not access.allowed:
                    raise LocatorRefused(
                        access.reason,
                        {"matched_group_count": 1, "access_status": access.status},
                    )
                flat = flatten_calibrated_group(
                    pid,
                    profile,
                    group_info,
                    vtables,
                    layer_count,
                    writable_contains=writable_contains,
                )
                miss = abs(int(flat["shape_count"]) - int(layer_count)) + int(flat["invalid_count"]) * 10
                if best_miss is None or miss < best_miss[0]:
                    best_miss = (miss, group_info, flat)
                if flat["shape_count"] != layer_count or flat["invalid_count"]:
                    continue
                is_recursive = int(flat["group_count"]) > 1
                print(
                    f"Direct group candidate validated: top={group_info['vector_count']} flat={flat['shape_count']} "
                    f"groups={flat['group_count']} depth={flat['max_depth']}",
                    flush=True,
                )
                record_locator_diagnostic(
                    "calibrated_flattened",
                    scanned_mb=scanned // (1024 * 1024),
                    total_mb=total_bytes // (1024 * 1024),
                    vtable_hits=hits,
                    stopped_by="match",
                )
                candidate = {
                    "score": 420 + min(layer_count, 3000) + flat["group_count"] * 10,
                    "group_address": group_info["group_address"],
                    "count_address": group_info["count_address"],
                    "table_pointer_field": group_info["table_pointer_field"],
                    "table_address": group_info["table_address"],
                    "count_kind": "rtti_direct_recursive" if is_recursive else "rtti_direct_flat",
                    "current_u16": group_info.get("current_u16"),
                    "current_u32": group_info.get("current_u32"),
                    "samples": flat["samples"],
                    "validated_entries": flat["shape_count"],
                    "vector_count": group_info["vector_count"],
                    "capacity_count": group_info["capacity_count"],
                    "top_vector_count": group_info["vector_count"],
                    "flattened_from_groups": is_recursive,
                    "flattened_group_count": flat["group_count"],
                    "flattened_max_depth": flat["max_depth"],
                    "group_graph": {
                        "has_parent": False,
                        "has_children": is_recursive,
                        "is_flat_orphan": not is_recursive,
                        "parent_count": 0,
                        "child_count": max(0, flat["group_count"] - 1),
                    },
                    "vtable": group_info["vtable"],
                    "rtti_source": rtti.get("source") or "pattern_scan",
                    "rtti_update_code": rtti.get("update_code"),
                    "rtti_descriptor_offset": rtti.get("descriptor_offset"),
                    "export_access_verified": access is None or access.allowed,
                    "locator_scan_mb": scanned // (1024 * 1024),
                    "locator_vtable_hits": hits,
                    "locator_scan_complete": not stopped_by_time,
                }
                candidate.update(flattened_import_target(flat, layer_count))
                return [candidate]
            if max_seconds and time.monotonic() - started > max_seconds:
                print(f"Stopped calibrated flattened-group scan after {max_seconds} seconds.", flush=True)
                stopped_by_time = True
                break
        if stopped_by_time:
            break
        if chunk_index % 500 == 0:
            print(
                f"Calibrated grouped scan checked {scanned // (1024 * 1024)} MB, "
                f"type hits={hits}.",
                flush=True,
            )
    if best_miss:
        _miss, group_info, flat = best_miss
        print(
            f"Best grouped candidate miss: top={group_info['vector_count']} flat={flat['shape_count']} "
            f"invalid={flat['invalid_count']} groups={flat['group_count']} depth={flat['max_depth']}",
            flush=True,
        )
    print(
        f"Direct group scan checked {scanned // (1024 * 1024)} MB, "
        f"type hits={hits}, candidates=0.",
        flush=True,
    )
    record_locator_diagnostic(
        "calibrated_flattened",
        scanned_mb=scanned // (1024 * 1024),
        total_mb=total_bytes // (1024 * 1024),
        vtable_hits=hits,
        stopped_by="time_limit" if stopped_by_time else "complete",
    )
    return []


def locate_clivery_groups_by_rtti(pid, profile, layer_count):
    rtti = locate_clivery_group_rtti(pid, profile)
    if not rtti:
        return []

    if rtti.get("source") == "fixed_profile_pattern":
        groups = locate_clivery_groups_by_calibrated_flattened(pid, profile, layer_count, rtti)
        if groups:
            return groups[:FH6_LOCATOR_CANDIDATE_CAP]
        groups = locate_clivery_groups_by_calibrated_count(pid, profile, layer_count, rtti)
        if groups:
            return groups[:FH6_LOCATOR_CANDIDATE_CAP]
        groups = locate_clivery_groups_by_calibrated_graph(pid, profile, layer_count, rtti)
        return groups[:FH6_LOCATOR_CANDIDATE_CAP]

    if rtti.get("source") == "static_profile":
        # A retired title's verified vtable makes the count scan both faster
        # and stricter than starting with a process-wide type scan. The graph
        # fallback still handles nested groups and verifies their full tree.
        groups = locate_clivery_groups_by_calibrated_count(pid, profile, layer_count, rtti)
        if groups:
            return groups[:FH6_LOCATOR_CANDIDATE_CAP]
        groups = locate_clivery_groups_by_calibrated_graph(pid, profile, layer_count, rtti)
        return groups[:FH6_LOCATOR_CANDIDATE_CAP]

    if rtti.get("source") == "calibrated_profile":
        return locate_clivery_group_by_allocator(pid, profile, layer_count, rtti)

    groups = []
    vtable_patterns = [(vtable, struct.pack("<Q", vtable)) for vtable in rtti["vtables"]]
    private_regions = list(iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True))
    for base, size, _protect, _type in private_regions:
        memory = read_region(pid, base, size)
        if not memory:
            continue
        for vtable, pattern in vtable_patterns:
            start = 0
            while True:
                pos = memory.find(pattern, start)
                if pos == -1:
                    break
                group_address = base + pos
                start = pos + 8
                candidate = build_clivery_group_candidate(
                    pid,
                    profile,
                    layer_count,
                    rtti,
                    group_address,
                    vtable,
                    "u16_rtti",
                )
                if candidate:
                    groups.append(candidate)
    groups.sort(key=lambda item: item["score"], reverse=True)
    return groups[:FH6_LOCATOR_CANDIDATE_CAP]


def locate_clivery_groups_by_layout_count(pid, profile, layer_count, max_seconds=None, max_candidates=750000):
    game_name = str(getattr(profile, "key", "FH6")).upper()
    started = time.monotonic()
    pattern = struct.pack("<H", layer_count)
    groups = []
    candidates = 0
    scanned = 0
    stopped = False
    # Keep the independent layout fallback in virtual-address order. The RTTI
    # passes use a balanced large/small schedule, so this pass intentionally
    # provides a different coverage order instead of repeating the same blind
    # spot under another validator.
    regions = list(iter_regions(pid, type_filter=MEM_PRIVATE, writable_only=True))
    for base, size, _protect, _type in regions:
        if max_seconds and time.monotonic() - started > max_seconds:
            print(f"Stopped {game_name} layout-count scan after {max_seconds} seconds.", flush=True)
            break
        first_chunk = True
        for chunk_base, memory in iter_region_chunks(pid, base, size, overlap=len(pattern) - 1):
            scanned += len(memory) if first_chunk else max(0, len(memory) - (len(pattern) - 1))
            first_chunk = False
            start = 0
            while True:
                pos = memory.find(pattern, start)
                if pos == -1:
                    break
                start = pos + 1
                candidates += 1
                if candidates % 4096 == 0 and max_seconds and time.monotonic() - started > max_seconds:
                    print(f"Stopped {game_name} layout-count scan after {max_seconds} seconds.", flush=True)
                    stopped = True
                    break
                if candidates > max_candidates:
                    print(f"Stopped {game_name} layout-count scan after {max_candidates} count hits.", flush=True)
                    return groups
                count_address = chunk_base + pos
                group_address = count_address - profile.livery_count_offset
                if group_address < base:
                    continue
                table_field = group_address + profile.layer_table_offset
                try:
                    table_address = read_u64(pid, table_field)
                except Exception:
                    continue
                if not table_address or not is_user_pointer(table_address):
                    continue
                if not is_private_writable_address(pid, table_address):
                    continue
                vector_ok, vector = validate_group_vector(pid, profile, group_address, table_address, layer_count)
                if not vector_ok:
                    continue
                score, samples = score_table(pid, profile, table_address, min(layer_count, 64))
                if score <= 0:
                    continue
                ok, checked, valid_entries = validate_table_layer_coverage(pid, profile, table_address, layer_count)
                if not ok:
                    continue
                groups.append({
                    "score": score + 60,
                    "group_address": group_address,
                    "count_address": count_address,
                    "table_pointer_field": table_field,
                    "table_address": table_address,
                    "count_kind": "u16_group_layout",
                    "current_u16": layer_count,
                    "current_u32": layer_count,
                    "samples": samples,
                    "validated_entries": valid_entries,
                    "vector_count": vector.get("vector_count"),
                    "capacity_count": vector.get("capacity_count"),
                })
                print(
                    f"Layout candidate validated {valid_entries}/{layer_count} layer(s).",
                    flush=True,
                )
            if stopped or groups:
                break
        if stopped:
            break
        if groups:
            break
    print(f"{game_name} layout-count scan checked {scanned // (1024 * 1024)} MB, count hits={candidates}.", flush=True)
    groups.sort(key=lambda item: item["score"], reverse=True)
    return groups


def serialize_samples(samples):
    result = []
    for index, ptr, layer_score, checks in samples[:8]:
        result.append({
            "index": index,
            "pointer": ptr,
            "score": layer_score,
            "checks": checks,
        })
    return result


def auto_locate_count_table(pid, profile, layer_count, limit_mb, max_matches, progress_every, radius, output_path=None, max_seconds=None):
    game_name = str(getattr(profile, "key", "FH6")).upper()
    LAST_LOCATOR_DIAGNOSTICS.clear()
    print(f"Process: {psutil.Process(pid).name()} detected.")
    print(f"Auto-locating {game_name} layer count/table for count {layer_count}...")
    started = time.monotonic()

    try:
        if profile.key == "fh6":
            fast_groups = locate_clivery_groups_by_rtti(pid, profile, layer_count)
            exact_authoritative = bool(
                (LAST_LOCATOR_DIAGNOSTICS.get("calibrated_exact_authoritative") or {}).get("complete")
            )
            if not fast_groups and not exact_authoritative:
                fast_groups = locate_clivery_groups_by_layout_count(pid, profile, layer_count, max_seconds=max_seconds)
        else:
            exact_authoritative = False
            fast_groups = locate_clivery_groups_by_rtti(pid, profile, layer_count)
            if not fast_groups:
                fast_groups = locate_clivery_groups_by_layout_count(pid, profile, layer_count, max_seconds=max_seconds)
    except LocatorRefused as exc:
        payload = {
            "type": "fh6_session_location_v1",
            "pid": pid,
            "process": psutil.Process(pid).name(),
            "game": profile.key,
            "layer_count": layer_count,
            "created": time.time(),
            **runtime_diagnostic_identity(),
            "refused": True,
            "refusal_reason": str(exc),
            "locator_details": exc.details,
            "locator_diagnostics": dict(LAST_LOCATOR_DIAGNOSTICS),
        }
        print(str(exc), flush=True)
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(f"Wrote {game_name} session location to {output_path}")
        return payload
    if fast_groups:
        print(f"Fast {game_name} layer group candidates: {len(fast_groups)}", flush=True)
        winner = fast_groups[0]
        best = fast_groups[:FH6_LOCATOR_CANDIDATE_CAP]
        for item in best:
            print(
                f"candidate score={item['score']} kind={item['count_kind']} validated={item['validated_entries']}",
                flush=True,
            )
            for index, ptr, layer_score, checks in item["samples"][:4]:
                print(f"  sample[{index}] score={layer_score} {'; '.join(checks)}")
        import_group_address = winner.get("import_group_address")
        import_count_address = winner.get("import_count_address")
        import_table_pointer_field = winner.get("import_table_pointer_field")
        import_table_address = winner.get("import_table_address")
        import_vector_count = winner.get("import_vector_count")
        import_capacity_count = winner.get("import_capacity_count")
        import_target_verified = winner.get("import_target_verified") is True
        if not winner.get("flattened_from_groups") and int(winner.get("vector_count") or 0) == int(layer_count):
            import_group_address = winner["group_address"]
            import_count_address = winner["count_address"]
            import_table_pointer_field = winner["table_pointer_field"]
            import_table_address = winner["table_address"]
            import_vector_count = winner.get("vector_count")
            import_capacity_count = winner.get("capacity_count")
            import_target_verified = True
        shape_word_counts = {}
        if import_target_verified and import_table_address:
            shape_word_counts = table_shape_word_counts(pid, profile, import_table_address, layer_count)
        payload = {
            "type": "fh6_session_location_v1",
            "pid": pid,
            "process": psutil.Process(pid).name(),
            "game": profile.key,
            "layer_count": layer_count,
            "created": time.time(),
            **runtime_diagnostic_identity(),
            "group_address": winner["group_address"],
            "count_address": winner["count_address"],
            "table_pointer_field": winner["table_pointer_field"],
            "table_address": winner["table_address"],
            "score": winner["score"],
            "locator": winner["count_kind"],
            "validated_entries": winner.get("validated_entries"),
            "shape_word_counts": shape_word_counts or winner.get("shape_word_counts") or {},
            "vector_count": winner.get("vector_count"),
            "capacity_count": winner.get("capacity_count"),
            "top_vector_count": winner.get("top_vector_count"),
            "flattened_from_groups": bool(winner.get("flattened_from_groups")),
            "flattened_group_count": winner.get("flattened_group_count"),
            "flattened_max_depth": winner.get("flattened_max_depth"),
            "import_group_address": import_group_address,
            "import_count_address": import_count_address,
            "import_table_pointer_field": import_table_pointer_field,
            "import_table_address": import_table_address,
            "import_vector_count": import_vector_count,
            "import_capacity_count": import_capacity_count,
            "import_target_verified": import_target_verified,
            "export_access_verified": winner.get("export_access_verified") is True,
            "group_graph": winner.get("group_graph"),
            "group_graph_complete": winner.get("group_graph_complete"),
            "group_graph_partial": winner.get("group_graph_partial"),
            "global_group_count": winner.get("global_group_count"),
            "graph_scan_mb": winner.get("graph_scan_mb"),
            "locator_scan_mb": winner.get("locator_scan_mb"),
            "locator_vtable_hits": winner.get("locator_vtable_hits"),
            "locator_scan_complete": winner.get("locator_scan_complete"),
            "vtable": winner.get("vtable"),
            "rtti_source": winner.get("rtti_source"),
            "rtti_update_code": winner.get("rtti_update_code"),
            "rtti_descriptor_offset": winner.get("rtti_descriptor_offset"),
            "locator_diagnostics": dict(LAST_LOCATOR_DIAGNOSTICS),
            "samples": serialize_samples(winner["samples"]),
        }
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(f"Wrote {game_name} session location to {output_path}")
        return payload

    if profile.key == "fh6" and exact_authoritative:
        failure_reason = (
            "A complete exact-RTTI scan did not find the requested live FH6 group. "
            "Confirm the vinyl is open in the editor and its displayed layer count is correct."
        )
        print(failure_reason, flush=True)
        print("No noisy layer-count fallback will be used after complete RTTI coverage.", flush=True)
        payload = {
            "type": "fh6_session_location_v1",
            "pid": pid,
            "process": psutil.Process(pid).name(),
            "game": profile.key,
            "layer_count": layer_count,
            "created": time.time(),
            **runtime_diagnostic_identity(),
            "no_match": True,
            "authoritative_no_match": True,
            "refused": False,
            "failure_reason": failure_reason,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "locator_diagnostics": dict(LAST_LOCATOR_DIAGNOSTICS),
        }
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(f"Wrote {game_name} session location to {output_path}")
        return None

    if profile.key == "fh6":
        print(f"No safe {game_name} layer group found by the fast layout locator. Trying slower count/table fallback before giving up.")
        started = time.monotonic()

    best = []
    quick = []
    fallback_addresses = []
    seen = set()
    for kind, address in find_count_candidates(pid, layer_count, limit_mb, max_matches, progress_every):
        if max_seconds and time.monotonic() - started > max_seconds:
            print(f"Stopped auto-locate after {max_seconds} seconds.", flush=True)
            break
        if address in seen:
            continue
        seen.add(address)
        try:
            u16 = read_u16(pid, address)
            u32 = read_u32(pid, address)
        except Exception:
            continue
        if u32 != layer_count:
            continue
        if not is_private_writable_address(pid, address):
            continue
        table = find_table_at_known_group_delta(pid, profile, address, layer_count)
        if not table:
            if len(fallback_addresses) < 512:
                fallback_addresses.append((kind, address, u16, u32))
            continue
        if table["score"] < 20:
            continue
        table["count_kind"] = kind
        table["current_u16"] = u16
        table["current_u32"] = u32
        quick.append(table)
        quick.sort(key=lambda item: item["score"], reverse=True)
        del quick[16:]

    if not quick:
        for kind, address, u16, u32 in fallback_addresses:
            if max_seconds and time.monotonic() - started > max_seconds:
                print(f"Stopped fallback table scoring after {max_seconds} seconds.", flush=True)
                break
            table = find_best_table_near_count_fast(pid, profile, address, layer_count, radius)
            if not table or table["score"] < 20:
                continue
            table["count_kind"] = kind
            table["current_u16"] = u16
            table["current_u32"] = u32
            quick.append(table)
            quick.sort(key=lambda item: item["score"], reverse=True)
            del quick[16:]

    if quick:
        print(f"Quick count/table candidates before safety validation: {len(quick)}", flush=True)

    rejected = 0
    best_rejected_strict = 0
    for table in quick:
        group_address = table.get("group_address") or (table["count_address"] - profile.livery_count_offset)
        if profile.key == "fh6":
            vector_ok, vector = validate_group_vector(pid, profile, group_address, table["table_address"], layer_count)
            if not vector_ok:
                rejected += 1
                print(
                f"Rejected fallback candidate score={table['score']} because group metadata did not match the active editor state.",
                flush=True,
            )
                continue
            table["group_address"] = group_address
            table["vector_count"] = vector.get("vector_count")
            table["capacity_count"] = vector.get("capacity_count")
        ok, checked, valid_entries = validate_table_layer_coverage(pid, profile, table["table_address"], layer_count)
        if not ok:
            rejected += 1
            best_rejected_strict = max(best_rejected_strict, valid_entries)
            print(
                f"Rejected fallback candidate score={table['score']}: exact layer validation {valid_entries}/{layer_count}, checked={checked}",
                flush=True,
            )
            continue
        table["validated_entries"] = valid_entries
        best.append(table)
        print(
            f"Fallback candidate score={table['score']} kind={table['count_kind']} validated={checked}",
            flush=True,
        )

    best.sort(key=lambda item: item["score"], reverse=True)
    best = best[:FH6_LOCATOR_CANDIDATE_CAP]
    print(f"Auto-locate candidates: {len(best)}")
    for item in best:
        print(
            f"score={item['score']} kind={item['count_kind']} count16={item['current_u16']} count32={item['current_u32']}"
        )
        for index, ptr, layer_score, checks in item["samples"][:4]:
            print(f"  sample[{index}] score={layer_score} {'; '.join(checks)}")

    if not best:
        failure_reason = "No safe live layer group matched the requested layer count."
        if rejected:
            print(f"Rejected {rejected} unsafe count/table candidates. Best strong-layer coverage: {best_rejected_strict}/{layer_count}.")
        print("No safe FH6 layer group found with the current locator. Import should stop before writing.")
        payload = {
            "type": "fh6_session_location_v1",
            "pid": pid,
            "process": psutil.Process(pid).name(),
            "game": profile.key,
            "layer_count": layer_count,
            "created": time.time(),
            **runtime_diagnostic_identity(),
            "no_match": True,
            "refused": False,
            "failure_reason": failure_reason,
            "rejected_candidate_count": rejected,
            "best_rejected_layer_coverage": best_rejected_strict,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "locator_diagnostics": dict(LAST_LOCATOR_DIAGNOSTICS),
        }
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print(f"Wrote {game_name} session location to {output_path}")
        return None

    winner = best[0]
    payload = {
        "type": "fh6_session_location_v1",
        "pid": pid,
        "process": psutil.Process(pid).name(),
        "game": profile.key,
        "layer_count": layer_count,
        "created": time.time(),
        **runtime_diagnostic_identity(),
        "group_address": winner.get("group_address"),
        "count_address": winner["count_address"],
        "table_pointer_field": winner["table_pointer_field"],
        "table_address": winner["table_address"],
        "score": winner["score"],
        "vector_count": winner.get("vector_count"),
        "capacity_count": winner.get("capacity_count"),
        "samples": serialize_samples(winner["samples"]),
    }
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"Wrote FH6 session location to {output_path}")
    return payload


def score_layer_pointer(pid, pointer, profile):
    score = 0
    checks = []
    if not is_user_pointer(pointer):
        return 0, checks

    pos = read_float_pair(pid, pointer + profile.layer_position_offset)
    scale = read_float_pair(pid, pointer + profile.layer_scale_offset)
    color = read_process_memory(pid, pointer + profile.layer_color_offset, 4)
    shape = read_process_memory(pid, pointer + profile.layer_shape_id_offset, 1)
    mask = read_process_memory(pid, pointer + profile.layer_mask_offset, 1)

    if pos and all(-10000.0 < value < 10000.0 for value in pos):
        score += 1
        checks.append(f"pos={pos[0]:.2f},{pos[1]:.2f}")
    if scale and all(0.0 <= abs(value) < 10000.0 for value in scale):
        score += 1
        checks.append(f"scale={scale[0]:.3f},{scale[1]:.3f}")
    if len(color) == 4:
        score += 1
        checks.append("color=" + color.hex(" "))
    if shape and shape[0] in (0, 1, 2, 100, 101, 102):
        score += 1
        checks.append(f"shape={shape[0]}")
    if mask and mask[0] in (0, 1):
        score += 1
        checks.append(f"mask={mask[0]}")
    return score, checks


def score_table(pid, profile, table_address, sample_count):
    if not is_private_writable_address(pid, table_address):
        return 0, []
    scores = []
    pointers = []
    layer_like = 0
    total = 0
    sample_total = min(sample_count, 64)
    for index in range(sample_total):
        ptr = read_pointer(pid, table_address + index * 8)
        if not is_private_writable_address(pid, ptr):
            return 0, []
        pointers.append(ptr)
        score, checks = score_layer_pointer(pid, ptr, profile)
        total += score
        if score >= 3:
            layer_like += 1
        if score and index < 8:
            scores.append((index, ptr, score, checks))
    if sample_total >= 16 and len(set(pointers)) < max(8, int(sample_total * 0.75)):
        return 0, []
    if sample_total >= 16 and layer_like < max(8, sample_total // 2):
        return 0, []
    return total + layer_like, scores


def export_layer_pointer_ok(pid, pointer, profile):
    if not is_private_writable_address(pid, pointer):
        return False
    try:
        raw = read_process_memory(pid, pointer, max(profile.layer_shape_id_offset + 2, profile.layer_mask_offset + 1, 0x7C))
    except Exception:
        return False
    if len(raw) < 0x7C:
        return False
    try:
        pos = struct.unpack_from("<ff", raw, profile.layer_position_offset)
        scale = struct.unpack_from("<ff", raw, profile.layer_scale_offset)
        rotation = struct.unpack_from("<f", raw, profile.layer_rotation_offset)[0]
        skew = struct.unpack_from("<f", raw, 0x70)[0]
        shape_word = struct.unpack_from("<H", raw, profile.layer_shape_id_offset)[0]
        mask = raw[profile.layer_mask_offset]
    except Exception:
        return False
    if not all(-100000.0 < value < 100000.0 for value in (*pos, *scale, rotation, skew)):
        return False
    if abs(scale[0]) < 0.0001 and abs(scale[1]) < 0.0001:
        return False
    if not 0 <= int(shape_word) <= 0xFFFF:
        return False
    if mask not in (0, 1):
        return False
    return True


def validate_table_layer_coverage(pid, profile, table_address, layer_count):
    if not is_private_writable_address(pid, table_address):
        return False, 0, 0
    required = min(int(layer_count), 3000)
    if required <= 0:
        return False, 0, 0
    valid = 0
    seen = set()
    for index in range(required):
        ptr = read_pointer(pid, table_address + index * 8)
        if ptr in seen:
            return False, index + 1, valid
        seen.add(ptr)
        if not export_layer_pointer_ok(pid, ptr, profile):
            return False, index + 1, valid
        valid += 1
    return True, required, valid


def table_shape_word_counts(pid, profile, table_address, layer_count):
    counts = {}
    for index in range(min(int(layer_count), 3000)):
        ptr = read_pointer(pid, table_address + index * 8)
        try:
            raw = read_process_memory(pid, ptr + profile.layer_shape_id_offset, 2)
        except Exception:
            return {}
        if len(raw) != 2:
            return {}
        word = struct.unpack("<H", raw)[0]
        counts[str(word)] = counts.get(str(word), 0) + 1
    return counts


def find_count_candidates(pid, count, limit_mb, max_matches, progress_every):
    needles = [
        ("u32", struct.pack("<I", count)),
        ("u16", struct.pack("<H", count)),
    ]
    scanned = 0
    matches = 0
    next_progress = progress_every * 1024 * 1024 if progress_every else None
    for base, size, protect, _region_type in iter_regions(pid):
        if limit_mb and scanned >= limit_mb * 1024 * 1024:
            break
        read_size = min(size, 64 * 1024 * 1024)
        if limit_mb:
            read_size = min(read_size, limit_mb * 1024 * 1024 - scanned)
        scanned += read_size
        if next_progress and scanned >= next_progress:
            print(f"Scanned {scanned // (1024 * 1024)} MB, matches={matches}", flush=True)
            next_progress += progress_every * 1024 * 1024
        try:
            memory = read_process_memory(pid, base, read_size)
        except Exception:
            continue
        for kind, needle in needles:
            start = 0
            while True:
                pos = memory.find(needle, start)
                if pos == -1:
                    break
                matches += 1
                if max_matches and matches > max_matches:
                    print(f"Stopped after {max_matches} count matches. Use a smaller layer count/template or raise --max-matches.", flush=True)
                    return
                yield kind, base + pos
                start = pos + 1


def iter_memory_chunks(pid, limit_mb, progress_every, chunk_size=8 * 1024 * 1024):
    scanned = 0
    next_progress = progress_every * 1024 * 1024 if progress_every else None
    for base, size, protect, _region_type in iter_regions(pid):
        offset = 0
        while offset < size:
            if limit_mb and scanned >= limit_mb * 1024 * 1024:
                return
            read_size = min(size - offset, chunk_size)
            if limit_mb:
                read_size = min(read_size, limit_mb * 1024 * 1024 - scanned)
            address = base + offset
            scanned += read_size
            if next_progress and scanned >= next_progress:
                print(f"Snapshotted {scanned // (1024 * 1024)} MB", flush=True)
                next_progress += progress_every * 1024 * 1024
            try:
                memory = read_process_memory(pid, address, read_size)
            except Exception:
                offset += read_size
                continue
            if len(memory) == read_size:
                yield address, memory
            offset += read_size


def collect_count_addresses(pid, count, limit_mb, max_matches, progress_every):
    results = []
    for kind, address in find_count_candidates(pid, count, limit_mb, max_matches, progress_every):
        results.append({"kind": kind, "address": address})
    return results


def save_count_snapshot(pid, count, limit_mb, max_matches, progress_every, output_path):
    print(f"Process: {psutil.Process(pid).name()} detected.")
    print(f"Saving count snapshot for layer count {count}...")
    results = collect_count_addresses(pid, count, limit_mb, max_matches, progress_every)
    payload = {
        "pid": pid,
        "process": psutil.Process(pid).name(),
        "count": count,
        "created": time.time(),
        "matches": results,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"Saved {len(results)} matches to {output_path}")


def group_matches_by_address(matches):
    by_address = {}
    for item in matches:
        address = int(item["address"])
        by_address.setdefault(address, set()).add(str(item.get("kind", "?")))
    return by_address


def read_current_count_values(pid, address):
    values = []
    try:
        raw1 = read_process_memory(pid, address, 1)
    except Exception:
        raw1 = b""
    if len(raw1) == 1:
        values.append(f"u8={raw1[0]}")
    try:
        raw2 = read_process_memory(pid, address, 2)
    except Exception:
        raw2 = b""
    if len(raw2) == 2:
        values.append(f"u16={struct.unpack('<H', raw2)[0]}")
    try:
        raw4 = read_process_memory(pid, address, 4)
    except Exception:
        raw4 = b""
    if len(raw4) == 4:
        values.append(f"u32={struct.unpack('<I', raw4)[0]}")
    return ", ".join(values) or "unreadable"


def compare_count_snapshot(pid, count, limit_mb, max_matches, progress_every, input_path):
    print(f"Process: {psutil.Process(pid).name()} detected.")
    with open(input_path, "r", encoding="utf-8") as handle:
        previous = json.load(handle)
    previous_by_address = group_matches_by_address(previous["matches"])
    print(f"Loaded {len(previous_by_address)} previous addresses for count {previous['count']} from {input_path}")
    current = collect_count_addresses(pid, count, limit_mb, max_matches, progress_every)
    current_by_address = group_matches_by_address(current)
    stable_changes = sorted(set(previous_by_address) & set(current_by_address))
    print(f"Current addresses for count {count}: {len(current_by_address)}")
    print(f"Same addresses that changed from {previous['count']} to {count}: {len(stable_changes)}")
    for address in stable_changes[:200]:
        previous_kinds = ",".join(sorted(previous_by_address[address]))
        current_kinds = ",".join(sorted(current_by_address[address]))
        values = read_current_count_values(pid, address)
        print(f"candidate detail omitted previousKinds={previous_kinds} currentKinds={current_kinds} current={values}")
    if len(stable_changes) > 200:
        print(f"... {len(stable_changes) - 200} more")
    if not stable_changes:
        print("No changed count addresses found. Keep the same editor/menu state, change only the layer count by one, then compare again.")


def transition_patterns(previous_count, current_count):
    specs = []
    values = [
        ("count", previous_count, current_count),
        ("count_minus_1", previous_count - 1, current_count - 1),
        ("count_plus_1", previous_count + 1, current_count + 1),
    ]
    for semantic, old_value, new_value in values:
        if 0 <= old_value <= 0xFF and 0 <= new_value <= 0xFF:
            specs.append((f"u8_{semantic}", bytes([old_value]), bytes([new_value])))
        if 0 <= old_value <= 0xFFFF and 0 <= new_value <= 0xFFFF:
            specs.append((f"u16_{semantic}", struct.pack("<H", old_value), struct.pack("<H", new_value)))
        if 0 <= old_value <= 0xFFFFFFFF and 0 <= new_value <= 0xFFFFFFFF:
            specs.append((f"u32_{semantic}", struct.pack("<I", old_value), struct.pack("<I", new_value)))
        specs.append((f"f32_{semantic}", struct.pack("<f", float(old_value)), struct.pack("<f", float(new_value))))
    return specs


def default_transition_candidates_path(input_path, current_count):
    path = Path(input_path)
    return path.with_name(f"{path.stem}-to-{current_count}-candidates.json")


def load_transition_candidate_addresses(input_path):
    with open(input_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {int(item["address"]) for item in payload.get("candidates", [])}


def validate_live_transition_matches(pid, grouped, expected_by_name):
    valid = {}
    rejected = 0
    for address, names in grouped.items():
        live_names = set()
        for name in names:
            expected = expected_by_name.get(name)
            if not expected:
                continue
            try:
                current = read_process_memory(pid, address, len(expected))
            except Exception:
                current = b""
            if current == expected:
                live_names.add(name)
        if live_names:
            valid[address] = live_names
        else:
            rejected += 1
    return valid, rejected


def save_memory_snapshot(pid, count, limit_mb, progress_every, output_path):
    print(f"Process: {psutil.Process(pid).name()} detected.")
    print(f"Saving compressed memory snapshot for layer count {count}...")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    chunks = 0
    bytes_written = 0
    with open(output_path, "w", encoding="utf-8") as handle:
        header = {
            "type": "memory_snapshot_v1",
            "pid": pid,
            "process": psutil.Process(pid).name(),
            "count": count,
            "created": time.time(),
            "limit_mb": limit_mb,
        }
        handle.write(json.dumps(header) + "\n")
        for address, memory in iter_memory_chunks(pid, limit_mb, progress_every):
            compressed = zlib.compress(memory, level=1)
            payload = {
                "base": address,
                "size": len(memory),
                "data": base64.b64encode(compressed).decode("ascii"),
            }
            handle.write(json.dumps(payload) + "\n")
            chunks += 1
            bytes_written += len(memory)
    print(f"Saved {chunks} chunks, {bytes_written // (1024 * 1024)} MB raw snapshot to {output_path}")


def collect_memory_transition_matches(pid, count, max_matches, input_path):
    print(f"Process: {psutil.Process(pid).name()} detected.")
    matches = []
    chunks = 0
    skipped = 0
    with open(input_path, "r", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        if header.get("type") != "memory_snapshot_v1":
            raise ValueError("Not a memory snapshot. Use --compare-count-snapshot for exact count-address snapshots.")
        previous_count = int(header["count"])
        patterns = transition_patterns(previous_count, count)
        print(f"Loaded memory snapshot for count {previous_count} from {input_path}")
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            base = int(item["base"])
            size = int(item["size"])
            old_memory = zlib.decompress(base64.b64decode(item["data"]))
            try:
                current_memory = read_process_memory(pid, base, size)
            except Exception:
                skipped += 1
                continue
            if len(current_memory) != len(old_memory):
                skipped += 1
                continue
            chunks += 1
            for name, old_pattern, new_pattern in patterns:
                start = 0
                while True:
                    pos = old_memory.find(old_pattern, start)
                    if pos == -1:
                        break
                    end = pos + len(new_pattern)
                    if current_memory[pos:end] == new_pattern:
                        matches.append((base + pos, name))
                        if max_matches and len(matches) >= max_matches:
                            break
                    start = pos + 1
                if max_matches and len(matches) >= max_matches:
                    break
            if max_matches and len(matches) >= max_matches:
                break
    return previous_count, chunks, skipped, matches


def write_transition_candidates(output_path, previous_count, current_count, source_snapshot, matches, stable_from=None):
    grouped = {}
    for address, name in matches:
        grouped.setdefault(address, set()).add(name)
    payload = {
        "type": "memory_transition_candidates_v1",
        "previous_count": previous_count,
        "current_count": current_count,
        "source_snapshot": str(source_snapshot),
        "stable_from": str(stable_from) if stable_from else None,
        "created": time.time(),
        "candidates": [
            {"address": address, "patterns": sorted(patterns)}
            for address, patterns in sorted(grouped.items())
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return payload


def compare_memory_snapshot(pid, count, max_matches, input_path, output_path=None, intersect_path=None):
    previous_count, chunks, skipped, matches = collect_memory_transition_matches(pid, count, max_matches, input_path)
    grouped = {}
    for address, name in matches:
        grouped.setdefault(address, set()).add(name)
    expected_by_name = {name: new_pattern for name, _old_pattern, new_pattern in transition_patterns(previous_count, count)}

    if intersect_path:
        previous_addresses = load_transition_candidate_addresses(intersect_path)
        grouped = {address: patterns for address, patterns in grouped.items() if address in previous_addresses}
        print(f"Intersected with {intersect_path}")
        print(f"Stable candidates present in both transitions: {len(grouped)}")

    grouped, rejected = validate_live_transition_matches(pid, grouped, expected_by_name)
    print(f"Live value validation rejected {rejected} stale/volatile candidates.")

    filtered_matches = [(address, name) for address, patterns in grouped.items() for name in patterns]
    output_path = output_path or default_transition_candidates_path(input_path, count)
    write_transition_candidates(output_path, previous_count, count, input_path, filtered_matches, intersect_path)

    print(f"Compared {chunks} chunks, skipped {skipped} unreadable/moved chunks.")
    print(f"Count-transition candidates from {previous_count} to {count}: {len(grouped)}")
    for address, patterns in sorted(grouped.items())[:300]:
        print(f"candidate detail omitted {','.join(sorted(patterns))} current={read_current_count_values(pid, address)}")
    if len(grouped) > 300:
        print(f"... {len(grouped) - 300} more")
    print(f"Wrote candidates to {output_path}")
    if not grouped:
        print("No count-transition candidates found. Increase --limit-mb or keep the editor fully unchanged except for one layer.")


def probe_count(pid, profile, count, limit_mb, max_matches, max_seconds, progress_every):
    started = time.monotonic()
    print(f"Process: {psutil.Process(pid).name()} detected.")
    print(f"Layer count target: {count}")
    print("Scanning readable/writable memory for count candidates...")

    count_offsets = range(0x40, 0x91)
    table_offsets = range(0x40, 0xC1, 8)
    best = []
    seen = set()
    tested = 0
    for kind, count_address in find_count_candidates(pid, count, limit_mb, max_matches, progress_every):
        if max_seconds and time.monotonic() - started > max_seconds:
            print(f"Stopped after {max_seconds} seconds.", flush=True)
            break
        for count_offset in count_offsets:
            group_base = count_address - count_offset
            if group_base in seen:
                continue
            seen.add(group_base)
            if not is_user_pointer(group_base):
                continue
            for table_offset in table_offsets:
                tested += 1
                table_address = read_pointer(pid, group_base + table_offset)
                score, samples = score_table(pid, profile, table_address, count)
                if score >= 8:
                    best.append((score, kind, group_base, count_offset, table_offset, table_address, samples))
                    print(
                        f"candidate score={score} countOffset={count_offset} tableOffset={table_offset}",
                        flush=True,
                    )

    best.sort(key=lambda item: item[0], reverse=True)
    print(f"Tested {tested} table candidates.", flush=True)
    if not best:
        print("No strong candidates found. Try again while a known ungrouped template is loaded and selected.")
        return

    print(f"Top {min(len(best), 20)} candidates:")
    for score, kind, group_base, count_offset, table_offset, table_address, samples in best[:20]:
        current_count = read_int(pid, group_base + count_offset)
        print(
            f"score={score} countKind={kind} countOffset={count_offset} count={current_count} "
            f"tableOffset={table_offset}"
        )
        for index, ptr, layer_score, checks in samples[:4]:
            print(f"  layer[{index}] score={layer_score} {'; '.join(checks)}")


def main():
    parser = argparse.ArgumentParser(description="Read-only FH6 vinyl structure probe.")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--game", default="fh6", choices=tuple(PROFILES.keys()))
    parser.add_argument("--layer-count", type=int, required=True, help="Exact ungrouped layer count currently loaded.")
    parser.add_argument("--inspect-table", type=parse_int, default=None, help="Inspect a known layer table address, e.g. 0x16e5cf34168.")
    parser.add_argument("--inspect-count", type=parse_int, default=None, help="Inspect memory around a candidate layer-count address.")
    parser.add_argument("--auto-locate", action="store_true", help="Find a FH6 count/table pair from the current --layer-count.")
    parser.add_argument("--inspect-layers", type=int, default=12, help="Number of table entries to inspect.")
    parser.add_argument("--inspect-start", type=int, default=0, help="First table entry index for --inspect-table.")
    parser.add_argument("--blob-size", type=parse_int, default=0x140, help="Layer blob bytes to read per pointer.")
    parser.add_argument("--dump-layer-index", type=int, default=None, help="Zero-based layer index to dump from --inspect-table.")
    parser.add_argument("--dump-layer-output", default=None, help="Write a single-layer dump JSON to this path.")
    parser.add_argument("--auto-dump-layer", action="store_true", help="Auto-locate candidate tables and search nearby slots for a live edited layer before dumping.")
    parser.add_argument("--dump-slot-radius", type=int, default=8, help="Search this many slots before/after the requested slot for --auto-dump-layer.")
    parser.add_argument("--dump-layer-shape-code", default=None)
    parser.add_argument("--dump-layer-shape-name", default=None)
    parser.add_argument("--dump-layer-shape-section", default=None)
    parser.add_argument("--dump-layer-shape-page", default=None)
    parser.add_argument("--dump-layer-shape-row", default=None)
    parser.add_argument("--dump-layer-shape-column", default=None)
    parser.add_argument("--inspect-radius", type=parse_int, default=0x300, help="Bytes before/after count address to inspect.")
    parser.add_argument("--save-count-snapshot", default=None, help="Save all raw addresses currently containing --layer-count.")
    parser.add_argument("--compare-count-snapshot", default=None, help="Compare current --layer-count addresses with a previous snapshot.")
    parser.add_argument("--save-memory-snapshot", default=None, help="Save compressed readable/writable memory for later count-transition diff.")
    parser.add_argument("--compare-memory-snapshot", default=None, help="Compare current memory with a previous compressed memory snapshot.")
    parser.add_argument("--write-candidates", default=None, help="Write memory-transition candidates to this JSON file.")
    parser.add_argument("--intersect-candidates", default=None, help="Only keep candidates whose addresses are also in this previous candidate JSON.")
    parser.add_argument("--write-session", default=None, help="Write auto-located FH6 count/table session JSON.")
    parser.add_argument("--limit-mb", type=int, default=512, help="Readable/writable memory scan cap.")
    parser.add_argument("--max-matches", type=int, default=20000, help="Stop after this many raw count matches.")
    parser.add_argument("--max-seconds", type=int, default=90, help="Stop after this many seconds.")
    parser.add_argument("--progress-every", type=int, default=64, help="Print progress every N scanned MB.")
    args = parser.parse_args()

    profile = get_profile(args.game)
    snapshot_modes = [
        args.save_count_snapshot,
        args.compare_count_snapshot,
        args.save_memory_snapshot,
        args.compare_memory_snapshot,
    ]
    if sum(1 for item in snapshot_modes if item) > 1:
        parser.error("Use only one snapshot/compare mode at a time.")
    if args.save_memory_snapshot:
        save_memory_snapshot(args.pid, args.layer_count, args.limit_mb, args.progress_every, args.save_memory_snapshot)
        return
    if args.compare_memory_snapshot:
        compare_memory_snapshot(
            args.pid,
            args.layer_count,
            args.max_matches,
            args.compare_memory_snapshot,
            args.write_candidates,
            args.intersect_candidates,
        )
        return
    if args.save_count_snapshot:
        save_count_snapshot(
            args.pid,
            args.layer_count,
            args.limit_mb,
            args.max_matches,
            args.progress_every,
            args.save_count_snapshot,
        )
        return
    if args.compare_count_snapshot:
        compare_count_snapshot(
            args.pid,
            args.layer_count,
            args.limit_mb,
            args.max_matches,
            args.progress_every,
            args.compare_count_snapshot,
        )
        return
    if args.inspect_count:
        inspect_count_address(args.pid, profile, args.inspect_count, args.layer_count, args.inspect_radius, args.blob_size)
        return
    if args.auto_locate:
        auto_locate_count_table(
            args.pid,
            profile,
            args.layer_count,
            args.limit_mb,
            args.max_matches,
            args.progress_every,
            args.inspect_radius,
            args.write_session,
            args.max_seconds,
        )
        return
    if args.auto_dump_layer:
        auto_dump_layer(
            args.pid,
            profile,
            args.layer_count,
            args.blob_size,
            args.dump_layer_index if args.dump_layer_index is not None else args.inspect_start,
            args.dump_layer_output,
            shape_meta={
                "code": args.dump_layer_shape_code,
                "name": args.dump_layer_shape_name,
                "section": args.dump_layer_shape_section,
                "page": args.dump_layer_shape_page,
                "row": args.dump_layer_shape_row,
                "column": args.dump_layer_shape_column,
            },
            slot_radius=max(0, args.dump_slot_radius),
            max_seconds=args.max_seconds,
        )
        return
    if args.dump_layer_output:
        if args.inspect_table is None:
            parser.error("--dump-layer-output requires --inspect-table.")
        dump_layer(
            args.pid,
            profile,
            args.inspect_table,
            args.layer_count,
            args.blob_size,
            args.dump_layer_index if args.dump_layer_index is not None else args.inspect_start,
            args.dump_layer_output,
            shape_meta={
                "code": args.dump_layer_shape_code,
                "name": args.dump_layer_shape_name,
                "section": args.dump_layer_shape_section,
                "page": args.dump_layer_shape_page,
                "row": args.dump_layer_shape_row,
                "column": args.dump_layer_shape_column,
            },
        )
        return
    if args.inspect_table:
        print(f"Process: {psutil.Process(args.pid).name()} detected.")
        inspect_table(args.pid, args.inspect_table, args.layer_count, args.blob_size, args.inspect_layers, args.inspect_start)
        return
    probe_count(args.pid, profile, args.layer_count, args.limit_mb, args.max_matches, args.max_seconds, args.progress_every)


def command_pid(argv):
    for index, value in enumerate(argv):
        if value == "--pid" and index + 1 < len(argv):
            return int(argv[index + 1])
        if value.startswith("--pid="):
            return int(value.split("=", 1)[1])
    return None


if __name__ == "__main__":
    if sys.maxsize <= 2**32:
        print("Use 64-bit Python.")
        sys.exit(1)
    requested_pid = command_pid(sys.argv[1:])
    if requested_pid is None:
        main()
    else:
        with process_memory_session(requested_pid):
            main()
