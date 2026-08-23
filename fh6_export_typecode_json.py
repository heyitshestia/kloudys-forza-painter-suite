#!/usr/bin/env python3
"""Export a supported live Forza layer table into importer-compatible JSON."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import re
import struct
import sys
import time
from collections import Counter
from ctypes import wintypes
from pathlib import Path

from fh6_live_group_policy import LIVE_OWNERSHIP_GAMES, assess_group_tree, minimum_header_size
from game_profiles import PROFILES
from tools.cgroup.shape_identity import canonical_resource_for_word


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
FULL_LAYER_SIZE = 0x140
GROUPED_SAFE_LAYER_SIZE = 0xC0
MIN_LAYER_DECODE_SIZE = 0x7C
TYPE_CODE_BASE = 0x100000
GROUP_HEADER_READ_SIZE = 0x300
GROUP_COUNT_OFFSET = 0x5A
GROUP_PARENT_OFFSET = 0x60
GROUP_TABLE_BEGIN_OFFSET = 0x78
GROUP_TABLE_END_OFFSET = 0x80
GROUP_TABLE_CAPACITY_OFFSET = 0x88
MIN_NORMAL_GROUP_ADDRESS = 0x100000000
EXPORT_REFUSAL_MESSAGE = (
    "Export refused: KFPS could not verify this live vinyl as exportable. "
    "Remove any content you do not own from the vinyl, save it, reopen it, and try again."
)
EXPORT_VALIDATION_WARNING = (
    "Export validation failed: the located live vinyl did not pass every required safety check."
)

# Motorsport uses the same visible library order, but several raw layer words
# differ from FH5/FH6. Convert FM exports to canonical FH6 words so exported
# JSON can be imported into FH6, while preserving raw FM words in the report.
FM_EXPORT_RESOURCE_MAP = {
    2103: ("Community_Vinyls_1", 1),
    2107: ("Community_Vinyls_1", 2),
    2123: ("Community_Vinyls_1", 3),
    2136: ("Community_Vinyls_1", 4),
    2109: ("Community_Vinyls_1", 5),
    2110: ("Community_Vinyls_1", 6),
    2132: ("Community_Vinyls_1", 7),
    2125: ("Community_Vinyls_1", 8),
    2139: ("Community_Vinyls_1", 9),
    2119: ("Community_Vinyls_1", 10),
    2135: ("Community_Vinyls_1", 11),
    2117: ("Community_Vinyls_1", 12),
    2127: ("Community_Vinyls_1", 13),
    2133: ("Community_Vinyls_1", 14),
    2129: ("Community_Vinyls_1", 15),
    2116: ("Community_Vinyls_1", 16),
    2138: ("Community_Vinyls_1", 17),
    2115: ("Community_Vinyls_1", 18),
    2137: ("Community_Vinyls_1", 19),
    2101: ("Community_Vinyls_1", 20),
    2105: ("Community_Vinyls_1", 21),
    2108: ("Community_Vinyls_1", 22),
    2126: ("Community_Vinyls_1", 23),
    2118: ("Community_Vinyls_1", 24),
    2106: ("Community_Vinyls_1", 25),
    2124: ("Community_Vinyls_1", 26),
    2131: ("Community_Vinyls_1", 27),
    2140: ("Community_Vinyls_1", 28),
    2102: ("Community_Vinyls_1", 29),
    2111: ("Community_Vinyls_1", 30),
    2104: ("Community_Vinyls_1", 31),
    2112: ("Community_Vinyls_1", 32),
    2134: ("Community_Vinyls_1", 33),
    2113: ("Community_Vinyls_1", 34),
    2114: ("Community_Vinyls_1", 35),
    2120: ("Community_Vinyls_1", 36),
    2128: ("Community_Vinyls_1", 37),
    2130: ("Community_Vinyls_1", 38),
    2122: ("Community_Vinyls_1", 39),
    2121: ("Community_Vinyls_1", 40),
    2201: ("Community_Vinyls_2", 1),
    2218: ("Community_Vinyls_2", 2),
    2226: ("Community_Vinyls_2", 3),
    2210: ("Community_Vinyls_2", 4),
    2230: ("Community_Vinyls_2", 5),
    2240: ("Community_Vinyls_2", 6),
    2238: ("Community_Vinyls_2", 7),
    2217: ("Community_Vinyls_2", 8),
    2231: ("Community_Vinyls_2", 9),
    2209: ("Community_Vinyls_2", 10),
    2202: ("Community_Vinyls_2", 11),
    2219: ("Community_Vinyls_2", 12),
    2227: ("Community_Vinyls_2", 13),
    2211: ("Community_Vinyls_2", 14),
    2206: ("Community_Vinyls_2", 15),
    2234: ("Community_Vinyls_2", 16),
    2239: ("Community_Vinyls_2", 17),
    2205: ("Community_Vinyls_2", 18),
    2223: ("Community_Vinyls_2", 19),
    2233: ("Community_Vinyls_2", 20),
    2203: ("Community_Vinyls_2", 21),
    2220: ("Community_Vinyls_2", 22),
    2228: ("Community_Vinyls_2", 23),
    2212: ("Community_Vinyls_2", 24),
    2222: ("Community_Vinyls_2", 25),
    2235: ("Community_Vinyls_2", 26),
    2225: ("Community_Vinyls_2", 27),
    2215: ("Community_Vinyls_2", 28),
    2224: ("Community_Vinyls_2", 29),
    2208: ("Community_Vinyls_2", 30),
    2204: ("Community_Vinyls_2", 31),
    2221: ("Community_Vinyls_2", 32),
    2229: ("Community_Vinyls_2", 33),
    2213: ("Community_Vinyls_2", 34),
    2214: ("Community_Vinyls_2", 35),
    2237: ("Community_Vinyls_2", 36),
    2236: ("Community_Vinyls_2", 37),
    2207: ("Community_Vinyls_2", 38),
    2232: ("Community_Vinyls_2", 39),
    2216: ("Community_Vinyls_2", 40),
    2301: ("Community_Vinyls_3", 1),
    2321: ("Community_Vinyls_3", 2),
    2317: ("Community_Vinyls_3", 3),
    2308: ("Community_Vinyls_3", 4),
    2327: ("Community_Vinyls_3", 5),
    2310: ("Community_Vinyls_3", 6),
    2339: ("Community_Vinyls_3", 7),
    2335: ("Community_Vinyls_3", 8),
    2316: ("Community_Vinyls_3", 9),
    2325: ("Community_Vinyls_3", 10),
    2302: ("Community_Vinyls_3", 11),
    2311: ("Community_Vinyls_3", 12),
    2318: ("Community_Vinyls_3", 13),
    2337: ("Community_Vinyls_3", 14),
    2336: ("Community_Vinyls_3", 15),
    2329: ("Community_Vinyls_3", 16),
    2332: ("Community_Vinyls_3", 17),
    2334: ("Community_Vinyls_3", 18),
    2324: ("Community_Vinyls_3", 19),
    2333: ("Community_Vinyls_3", 20),
    2322: ("Community_Vinyls_3", 21),
    2312: ("Community_Vinyls_3", 22),
    2319: ("Community_Vinyls_3", 23),
    2307: ("Community_Vinyls_3", 24),
    2338: ("Community_Vinyls_3", 25),
    2330: ("Community_Vinyls_3", 26),
    2303: ("Community_Vinyls_3", 27),
    2305: ("Community_Vinyls_3", 28),
    2314: ("Community_Vinyls_3", 29),
    2304: ("Community_Vinyls_3", 30),
    2331: ("Community_Vinyls_3", 31),
    2309: ("Community_Vinyls_3", 32),
    2328: ("Community_Vinyls_3", 33),
    2326: ("Community_Vinyls_3", 34),
    2323: ("Community_Vinyls_3", 35),
    2320: ("Community_Vinyls_3", 36),
    2313: ("Community_Vinyls_3", 37),
    2306: ("Community_Vinyls_3", 38),
    2315: ("Community_Vinyls_3", 39),
    2340: ("Community_Vinyls_3", 40),
    2401: ("Community_Vinyls_4", 1),
    2421: ("Community_Vinyls_4", 2),
    2417: ("Community_Vinyls_4", 3),
    2408: ("Community_Vinyls_4", 4),
    2427: ("Community_Vinyls_4", 5),
    2413: ("Community_Vinyls_4", 6),
    2406: ("Community_Vinyls_4", 7),
    2430: ("Community_Vinyls_4", 8),
    2414: ("Community_Vinyls_4", 9),
    2410: ("Community_Vinyls_4", 10),
    2402: ("Community_Vinyls_4", 11),
    2411: ("Community_Vinyls_4", 12),
    2418: ("Community_Vinyls_4", 13),
    2437: ("Community_Vinyls_4", 14),
    2436: ("Community_Vinyls_4", 15),
    2433: ("Community_Vinyls_4", 16),
    2435: ("Community_Vinyls_4", 17),
    2434: ("Community_Vinyls_4", 18),
    2424: ("Community_Vinyls_4", 19),
    2420: ("Community_Vinyls_4", 20),
    2422: ("Community_Vinyls_4", 21),
    2412: ("Community_Vinyls_4", 22),
    2419: ("Community_Vinyls_4", 23),
    2407: ("Community_Vinyls_4", 24),
    2438: ("Community_Vinyls_4", 25),
    2425: ("Community_Vinyls_4", 26),
    2440: ("Community_Vinyls_4", 27),
    2404: ("Community_Vinyls_4", 28),
    2432: ("Community_Vinyls_4", 29),
    2415: ("Community_Vinyls_4", 30),
    2431: ("Community_Vinyls_4", 31),
    2409: ("Community_Vinyls_4", 32),
    2428: ("Community_Vinyls_4", 33),
    2426: ("Community_Vinyls_4", 34),
    2423: ("Community_Vinyls_4", 35),
    2429: ("Community_Vinyls_4", 36),
    2416: ("Community_Vinyls_4", 37),
    2405: ("Community_Vinyls_4", 38),
    2403: ("Community_Vinyls_4", 39),
    2439: ("Community_Vinyls_4", 40),
}

FM_EXPORT_COMPACT_TAB_BASES = {
    101: "Primitives",
    201: "Gradient_Shapes",
    301: "Stripes",
    401: "Tears",
    501: "Racing_Icons",
    601: "Flames",
    701: "Paint_Splats",
    801: "Tribal",
    901: "Nature",
}


CANONICAL_COMPACT_TAB_BASES = {
    "Primitives": 101,
    "Gradient_Shapes": 201,
    "Stripes": 301,
    "Tears": 401,
    "Racing_Icons": 501,
    "Flames": 601,
    "Paint_Splats": 701,
    "Tribal": 801,
    "Nature": 901,
}

CANONICAL_COMMUNITY_TAB_BASES = {
    "Community_Vinyls_1": 2101,
    "Community_Vinyls_2": 2201,
    "Community_Vinyls_3": 2301,
    "Community_Vinyls_4": 2401,
}

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


def log(message):
    text = re.sub(r"0x[0-9a-fA-F]+", "<detail>", str(message))
    text = re.sub(r"\b(group|table|count|descriptor|vtable|ptr|pointer)=<detail>", r"\1=<detail>", text)
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def parse_int(value):
    return int(str(value), 0)


def finite(value, limit=100000.0):
    return math.isfinite(value) and -limit <= value <= limit


def open_process(pid):
    handle = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, int(pid))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def close_handle(handle):
    if handle:
        k32.CloseHandle(handle)


def read_memory(handle, address, size):
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(handle, int(address), buf, int(size), ctypes.byref(read))
    if not ok or read.value != size:
        raise RuntimeError(f"read failed at {hx(address)} wanted={size} got={read.value}")
    return buf.raw[: read.value]


def try_read_memory(handle, address, size):
    try:
        return read_memory(handle, address, size)
    except Exception:
        return b""


def ptr_at(handle, table, index):
    return struct.unpack("<Q", read_memory(handle, table + index * 8, 8))[0]


def read_group_parent(handle, group):
    raw = try_read_memory(handle, group + GROUP_PARENT_OFFSET, 8)
    if len(raw) != 8:
        return None
    return struct.unpack("<Q", raw)[0]


def read_group_metadata(handle, group):
    raw = read_memory(handle, group, GROUP_HEADER_READ_SIZE)
    begin = struct.unpack_from("<Q", raw, GROUP_TABLE_BEGIN_OFFSET)[0]
    end = struct.unpack_from("<Q", raw, GROUP_TABLE_END_OFFSET)[0]
    capacity = struct.unpack_from("<Q", raw, GROUP_TABLE_CAPACITY_OFFSET)[0]
    vector_count = (end - begin) // 8 if begin and end >= begin else None
    capacity_count = (capacity - begin) // 8 if begin and capacity >= begin else None
    return {
        "group": hx(group),
        "count_u16_0x5a": struct.unpack_from("<H", raw, GROUP_COUNT_OFFSET)[0],
        "count_u32_0x58": struct.unpack_from("<I", raw, GROUP_COUNT_OFFSET - 2)[0],
        "table_begin_0x78": hx(begin),
        "table_end_0x80": hx(end),
        "table_capacity_0x88": hx(capacity),
        "vector_count": vector_count,
        "capacity_count": capacity_count,
    }


def validate_editable_group(metadata, requested_count, expected_table, allow_flattened=False, game="fh6"):
    reasons = []
    try:
        begin = parse_int(metadata.get("table_begin_0x78", "0"))
        end = parse_int(metadata.get("table_end_0x80", "0"))
        capacity = parse_int(metadata.get("table_capacity_0x88", "0"))
    except Exception:
        begin = end = capacity = 0
        reasons.append("group vector addresses could not be parsed")
    if not allow_flattened and int(metadata.get("count_u16_0x5a") or -1) != int(requested_count):
        reasons.append(f"group layer count does not match requested count ({metadata.get('count_u16_0x5a')} != {requested_count})")
    # FM8 keeps the editable root header in a low-address arena. Its locator
    # independently verifies the RTTI root, hierarchy, ownership, and table.
    if str(game).lower() != "fm" and parse_int(metadata.get("group", "0")) < MIN_NORMAL_GROUP_ADDRESS:
        reasons.append("group header address is outside the normal FH6 editable group range")
    if not begin or not end or not capacity:
        reasons.append("group vector begin/end/capacity is missing")
    elif not (begin < capacity and begin <= end <= capacity):
        reasons.append("group vector begin/end/capacity is not ordered like a readable layer table")
    vector_count = metadata.get("vector_count")
    capacity_count = metadata.get("capacity_count")
    required_capacity = int(vector_count) if allow_flattened and vector_count is not None else int(requested_count)
    if capacity_count is None or int(capacity_count) < required_capacity:
        reasons.append(f"group vector capacity is smaller than requested count ({capacity_count} < {requested_count})")
    if int(expected_table) != begin:
        reasons.append(f"located table does not match group vector table ({hx(expected_table)} != {hx(begin)})")
    return not reasons, reasons


def validate_probe_report(probe_report, requested_count, selected_group, selected_table):
    reasons = []
    try:
        probe = json.loads(Path(probe_report).read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"locator validation report could not be read: {exc}"]
    if probe.get("type") == "fh6_session_location_v1":
        return validate_fast_session_report(probe, requested_count, selected_group, selected_table)
    if int(probe.get("count") or -1) != int(requested_count):
        reasons.append(f"locator report count does not match requested count ({probe.get('count')} != {requested_count})")
    candidates = probe.get("candidates") or []
    min_sample_ok = min(8, int(requested_count))
    strong_count = 0
    selected_seen = False
    selected_strong = False
    for index, candidate in enumerate(candidates, start=1):
        group = candidate.get("group")
        table = candidate.get("table")
        valid_ptrs = int(candidate.get("valid_ptrs") or 0)
        invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, int(requested_count) - valid_ptrs))
        sample_ok = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
        capacity_count = candidate.get("capacity_count")
        is_selected = bool(
            group
            and table
            and parse_int(group) == int(selected_group)
            and parse_int(table) == int(selected_table)
        )
        if is_selected:
            selected_seen = True
        is_strong = bool(
            group
            and table
            and (capacity_count is None or int(capacity_count) >= int(requested_count))
            and valid_ptrs >= int(requested_count)
            and invalid_ptrs == 0
            and sample_ok >= min_sample_ok
        )
        if is_strong:
            strong_count += 1
            if is_selected:
                selected_strong = True
    if strong_count <= 0:
        reasons.append("locator report contains no strong editable group candidate")
    if not selected_seen:
        reasons.append("selected group/table was not confirmed by the locator report")
    elif not selected_strong:
        reasons.append("selected group/table did not pass full pointer/vector validation")
    return not reasons, reasons


def validate_fast_session_report(session, requested_count, selected_group, selected_table):
    reasons = []
    if session.get("refused"):
        reasons.append(str(session.get("refusal_reason") or "locator refused this editor state"))
        return False, reasons
    if int(session.get("layer_count") or -1) != int(requested_count):
        reasons.append(f"locator session count does not match requested count ({session.get('layer_count')} != {requested_count})")
    group = session.get("group_address")
    table = session.get("table_address")
    if group is None or table is None:
        reasons.append("locator session does not contain a group/table address")
    else:
        try:
            selected_seen = int(group) == int(selected_group) and int(table) == int(selected_table)
        except Exception:
            selected_seen = False
        if not selected_seen:
            reasons.append("selected group/table was not confirmed by the locator session")
    capacity_count = session.get("capacity_count")
    vector_count = session.get("vector_count")
    validated_entries = int(session.get("validated_entries") or 0)
    flattened = bool(session.get("flattened_from_groups"))
    graph = session.get("group_graph") or {}
    if graph and not graph.get("is_flat_orphan") and not flattened:
        reasons.append("locator session describes a grouped hierarchy without a verified flattened export")
    if session.get("game") in LIVE_OWNERSHIP_GAMES and session.get("export_access_verified") is not True:
        reasons.append("locator session did not verify the complete live vinyl hierarchy")
    if flattened and not locator_allows_flattened(session):
        reasons.append("locator session did not authorize recursive grouped export")
    if not flattened and vector_count is not None and int(vector_count) != int(requested_count):
        reasons.append(f"locator session vector count does not match requested count ({vector_count} != {requested_count})")
    required_capacity = int(vector_count) if flattened and vector_count is not None else int(requested_count)
    if capacity_count is not None and int(capacity_count) < required_capacity:
        reasons.append(f"locator session capacity is smaller than requested count ({capacity_count} < {requested_count})")
    if validated_entries < int(requested_count):
        reasons.append(f"locator session did not validate every layer pointer ({validated_entries} < {requested_count})")
    samples = session.get("samples") or []
    min_sample_ok = min(8, int(requested_count))
    if len(samples) < min_sample_ok:
        reasons.append(f"locator session has too few validated sample layers ({len(samples)} < {min_sample_ok})")
    return not reasons, reasons


def write_refusal_report(args, table, group, report_path, metadata=None, reasons=None, policy=None):
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report = {
        "format": "fh6_typecode_json_export_report_v1",
        "created_utc": created,
        "refused": True,
        "refusal_reason": EXPORT_REFUSAL_MESSAGE,
        "validation_reasons": list(reasons or []),
        "pid": int(args.pid),
        "group": hx(group) if group is not None else None,
        "table": hx(table),
        "requested_count": int(args.count),
        "editable_group_check": {
            "passed": False,
            "metadata": metadata,
            "reasons": list(reasons or []),
        },
        "live_export_policy": policy.report() if policy is not None else None,
        "exported_shape_count": 0,
        "read_layer_count": 0,
        "failure_count": 0,
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(EXPORT_REFUSAL_MESSAGE)
    if reasons:
        log("Technical validation details were written to the saved report.")


def decode_layer(raw, index, ptr, include_raw=False):
    x, y = struct.unpack_from("<ff", raw, 0x18)
    sx, sy = struct.unpack_from("<ff", raw, 0x28)
    rotation = struct.unpack_from("<f", raw, 0x50)[0]
    skew = struct.unpack_from("<f", raw, 0x70)[0]
    color = list(raw[0x74:0x78])
    mask = bool(raw[0x78])
    shape_word = struct.unpack_from("<H", raw, 0x7A)[0]
    type_code = TYPE_CODE_BASE + int(shape_word)
    valid_numbers = all(finite(v, 1000000.0) for v in (x, y, sx, sy, rotation, skew))
    shape = {
        "type": type_code,
        "type_word": shape_word,
        "type_word_hex": hx(shape_word),
        "data": [x, y, sx, sy, rotation, skew, 1 if mask else 0],
        "color": color,
        "mask": mask,
        "score": 0,
    }
    layer = {
        "index": index,
        "layer": index + 1,
        "ptr": hx(ptr),
        "ok": valid_numbers,
        "type_code": type_code,
        "type_word": shape_word,
        "color": color,
        "mask": mask,
        "data": [x, y, sx, sy, rotation, skew],
    }
    if include_raw:
        layer["raw_hex"] = raw.hex()
    return shape, layer


def canonical_fh6_word_for_resource(family, index):
    family = str(family)
    index = int(index)
    if family == "Primitives":
        return 100 + index
    if family in CANONICAL_COMPACT_TAB_BASES:
        return int(CANONICAL_COMPACT_TAB_BASES[family]) + index - 1
    if family in CANONICAL_COMMUNITY_TAB_BASES:
        return int(CANONICAL_COMMUNITY_TAB_BASES[family]) + index - 1
    return None


def fm_direct_community_resource(raw_word):
    for base_word, family in (
        (2100, "Community_Vinyls_1"),
        (2200, "Community_Vinyls_2"),
        (2300, "Community_Vinyls_3"),
        (2400, "Community_Vinyls_4"),
    ):
        index = int(raw_word) - base_word
        if 1 <= index <= 40:
            return family, index
    return None


def annotate_fm_export_resource(shape, layer, game):
    if str(game).lower() != "fm":
        return False
    raw_word = int(shape.get("type_word") or 0) & 0xFFFF
    resource = FM_EXPORT_RESOURCE_MAP.get(raw_word)
    if not resource:
        for base_word, family in sorted(FM_EXPORT_COMPACT_TAB_BASES.items(), reverse=True):
            offset = raw_word - int(base_word)
            if 0 <= offset < 40:
                resource = (family, offset + 1)
                break
    if not resource:
        return False
    family, index = resource
    raw_type = int(shape.get("type") or 0)
    raw_word = int(shape.get("type_word") or 0) & 0xFFFF
    canonical_word = canonical_fh6_word_for_resource(family, int(index))
    shape["resource_family"] = family
    shape["resource_index"] = int(index)
    if canonical_word is not None:
        shape["type_word"] = canonical_word
        shape["type_word_hex"] = hx(canonical_word)
        shape["type"] = TYPE_CODE_BASE + canonical_word
        layer["fm_raw_type_word"] = raw_word
        layer["fm_raw_type_word_hex"] = hx(raw_word)
        layer["fm_raw_type"] = raw_type
        layer["fh6_type_word"] = canonical_word
        layer["fh6_type_word_hex"] = hx(canonical_word)
        layer["fh6_type"] = TYPE_CODE_BASE + canonical_word
        layer["type_word"] = canonical_word
        layer["type_code"] = TYPE_CODE_BASE + canonical_word
    layer["resource_family"] = family
    layer["resource_index"] = int(index)
    layer["resource_normalized_for_game"] = "fm"
    return True


def annotate_canonical_export_resource(shape, layer):
    if shape.get("resource_family") and shape.get("resource_index"):
        return False
    resource = canonical_resource_for_word(int(shape.get("type_word") or 0))
    if not resource:
        return False
    family, index = resource
    shape["resource_family"] = family
    shape["resource_index"] = int(index)
    layer["resource_family"] = family
    layer["resource_index"] = int(index)
    return True


def read_transform_fields(handle, address):
    raw = try_read_memory(handle, address, 0x74)
    if len(raw) < 0x74:
        return {"x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0, "rotation": 0.0, "skew": 0.0}
    try:
        x, y = struct.unpack_from("<ff", raw, 0x18)
        sx, sy = struct.unpack_from("<ff", raw, 0x28)
        rotation = struct.unpack_from("<f", raw, 0x50)[0]
        skew = struct.unpack_from("<f", raw, 0x70)[0]
    except Exception:
        return {"x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0, "rotation": 0.0, "skew": 0.0}
    if not all(finite(value, 1000000.0) for value in (x, y, sx, sy, rotation, skew)):
        return {"x": 0.0, "y": 0.0, "sx": 1.0, "sy": 1.0, "rotation": 0.0, "skew": 0.0}
    return {"x": x, "y": y, "sx": sx, "sy": sy, "rotation": rotation, "skew": skew}


IDENTITY_MATRIX = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply_matrix(a, b):
    return (
        a[0] * b[0] + a[2] * b[1],
        a[1] * b[0] + a[3] * b[1],
        a[0] * b[2] + a[2] * b[3],
        a[1] * b[2] + a[3] * b[3],
        a[0] * b[4] + a[2] * b[5] + a[4],
        a[1] * b[4] + a[3] * b[5] + a[5],
    )


def translation_matrix(x, y):
    return (1.0, 0.0, 0.0, 1.0, float(x), float(y))


def scale_matrix(sx, sy):
    return (float(sx), 0.0, 0.0, float(sy), 0.0, 0.0)


def rotation_matrix(degrees):
    radians = math.radians(float(degrees))
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    return (cos_v, sin_v, -sin_v, cos_v, 0.0, 0.0)


def skew_x_matrix(value):
    return (1.0, 0.0, float(value), 1.0, 0.0, 0.0)


def fh6_matrix_from_data(data):
    x = float(data[0]) if len(data) > 0 else 0.0
    y = float(data[1]) if len(data) > 1 else 0.0
    sx = float(data[2]) if len(data) > 2 and abs(float(data[2])) > 0.000001 else 1.0
    sy = float(data[3]) if len(data) > 3 and abs(float(data[3])) > 0.000001 else 1.0
    rotation = float(data[4]) if len(data) > 4 else 0.0
    skew = float(data[5]) if len(data) > 5 else 0.0
    matrix = IDENTITY_MATRIX
    for item in (
        translation_matrix(x, -y),
        rotation_matrix(-rotation),
        skew_x_matrix(-skew),
        scale_matrix(sx, sy),
    ):
        matrix = multiply_matrix(matrix, item)
    return matrix


def fh6_matrix_from_transform(transform):
    return fh6_matrix_from_data([
        transform.get("x", 0.0),
        transform.get("y", 0.0),
        transform.get("sx", 1.0),
        transform.get("sy", 1.0),
        transform.get("rotation", 0.0),
        transform.get("skew", 0.0),
    ])


def fh6_data_from_matrix(matrix, preferred_sx_sign=1.0):
    a, b, c, d, x, y_canvas = [float(value) for value in matrix]
    sign_x = -1.0 if float(preferred_sx_sign or 1.0) < 0 else 1.0
    sx = sign_x * (math.hypot(a, b) or 1.0)
    theta = math.atan2(b / sx, a / sx)
    det = a * d - b * c
    sy = det / sx if abs(sx) > 0.000001 else 1.0
    if abs(sy) < 0.000001:
        sy = 1.0
    cos_v = math.cos(-theta)
    sin_v = math.sin(-theta)
    local_c = cos_v * c - sin_v * d
    skew = -(local_c / sy) if abs(sy) > 0.000001 else 0.0
    rotation = ((-theta * 180.0 / math.pi) % 360.0 + 360.0) % 360.0
    return [x, -y_canvas, sx, sy, rotation, skew]


def matrix_is_identity(matrix):
    return all(abs(float(value) - IDENTITY_MATRIX[index]) < 0.000001 for index, value in enumerate(matrix))


def sign_for(value):
    try:
        return -1.0 if float(value) < 0 else 1.0
    except Exception:
        return 1.0


def apply_parent_transform(shape, layer, parent_matrix, parent_sx_sign=1.0):
    if matrix_is_identity(parent_matrix):
        return
    original = [float(value) for value in shape["data"][:6]]
    final_matrix = multiply_matrix(parent_matrix, fh6_matrix_from_data(original))
    transformed = fh6_data_from_matrix(final_matrix, preferred_sx_sign=original[2] * parent_sx_sign)
    for index, value in enumerate(transformed[:6]):
        shape["data"][index] = value
        layer["data"][index] = value
    layer["applied_parent_transform"] = {
        "matrix": [round(float(value), 8) for value in parent_matrix],
        "original_data": original,
        "parent_sx_sign": parent_sx_sign,
    }


def load_locator_report(path):
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def locator_allows_flattened(locator):
    return bool(
        locator.get("flattened_from_groups")
        and locator.get("export_access_verified") is True
    )


def locator_group_vtable(locator):
    value = locator.get("vtable")
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        try:
            return parse_int(value)
        except Exception:
            return None


def metadata_vector_addresses(metadata):
    try:
        begin = parse_int(metadata.get("table_begin_0x78", "0"))
        end = parse_int(metadata.get("table_end_0x80", "0"))
        capacity = parse_int(metadata.get("table_capacity_0x88", "0"))
    except Exception:
        return None
    if not begin or not end or not capacity or end < begin or capacity < end:
        return None
    if (end - begin) % 8 or (capacity - begin) % 8:
        return None
    vector_count = (end - begin) // 8
    capacity_count = (capacity - begin) // 8
    if vector_count <= 0 or vector_count > 3000:
        return None
    if capacity_count < vector_count or capacity_count > max(13000, vector_count * 16):
        return None
    return begin, vector_count, capacity_count


def read_group_vector_info(handle, group, expected_vtable=None):
    if expected_vtable is not None:
        raw_vtable = try_read_memory(handle, group, 8)
        if len(raw_vtable) != 8 or struct.unpack("<Q", raw_vtable)[0] != int(expected_vtable):
            return None
    try:
        metadata = read_group_metadata(handle, group)
    except Exception:
        return None
    vector = metadata_vector_addresses(metadata)
    if not vector:
        return None
    begin, vector_count, capacity_count = vector
    # Confirm the pointer table itself can be read before treating the object as a group.
    if len(try_read_memory(handle, begin, min(vector_count, 8) * 8)) != min(vector_count, 8) * 8:
        return None
    return {
        "group": group,
        "table": begin,
        "vector_count": vector_count,
        "capacity_count": capacity_count,
        "metadata": metadata,
    }


def read_object_vtable(handle, address):
    raw = try_read_memory(handle, address, 8)
    if len(raw) != 8:
        return None
    return struct.unpack("<Q", raw)[0]


def assess_fh6_live_group(handle, group, locator, *, game="fh6"):
    expected_vtable = locator_group_vtable(locator) or read_object_vtable(handle, group)
    if expected_vtable is None:
        return assess_group_tree(
            group,
            lambda _address: b"",
            lambda _address: (),
            game=game,
            allow_transformed_child_state=game == "fh5",
        )

    def read_header(address):
        return try_read_memory(handle, address, minimum_header_size(game))

    def read_children(address):
        info = read_group_vector_info(handle, address, expected_vtable)
        if not info:
            raise RuntimeError("live group vector is unreadable")
        children = []
        for index in range(int(info["vector_count"])):
            ptr = ptr_at(handle, int(info["table"]), index)
            if read_object_vtable(handle, ptr) != expected_vtable:
                continue
            child = read_group_vector_info(handle, ptr, expected_vtable)
            if not child:
                raise RuntimeError("live child group vector is unreadable")
            if read_group_parent(handle, ptr) != int(address):
                raise RuntimeError("live child group parent link is inconsistent")
            children.append(ptr)
        return children

    return assess_group_tree(
        group,
        read_header,
        read_children,
        game=game,
        allow_transformed_child_state=game == "fh5",
    )


def pointer_has_group_signature(handle, ptr, expected_vtable=None):
    if expected_vtable is not None:
        raw_vtable = try_read_memory(handle, ptr, 8)
        if len(raw_vtable) == 8 and struct.unpack("<Q", raw_vtable)[0] == int(expected_vtable):
            return True
    try:
        metadata = read_group_metadata(handle, ptr)
    except Exception:
        return False
    vector = metadata_vector_addresses(metadata)
    if not vector:
        return False
    begin, vector_count, _capacity_count = vector
    sample_count = min(vector_count, 8)
    return len(try_read_memory(handle, begin, sample_count * 8)) == sample_count * 8


def layer_pointer_exportable(handle, ptr):
    raw = try_read_memory(handle, ptr, MIN_LAYER_DECODE_SIZE)
    if len(raw) < MIN_LAYER_DECODE_SIZE:
        return False
    try:
        x, y = struct.unpack_from("<ff", raw, 0x18)
        sx, sy = struct.unpack_from("<ff", raw, 0x28)
        rotation = struct.unpack_from("<f", raw, 0x50)[0]
        skew = struct.unpack_from("<f", raw, 0x70)[0]
        mask = raw[0x78]
    except Exception:
        return False
    if not all(finite(value, 1000000.0) for value in (x, y, sx, sy, rotation, skew)):
        return False
    if abs(sx) < 0.0001 and abs(sy) < 0.0001:
        return False
    return mask in (0, 1)


def collect_export_layer_pointers(handle, group, table, requested_count, locator):
    expected_vtable = locator_group_vtable(locator)
    flatten = locator_allows_flattened(locator)
    if not flatten:
        return [(ptr_at(handle, table, index), IDENTITY_MATRIX) for index in range(int(requested_count))], {
            "flattened": False,
            "top_level_count": int(requested_count),
            "group_count": 0,
            "max_depth": 0,
            "invalid_entries": 0,
        }

    root = read_group_vector_info(handle, group, expected_vtable)
    if not root:
        raise RuntimeError("flattened export could not read the selected root group vector")
    if int(root["table"]) != int(table):
        raise RuntimeError(f"flattened export root table changed ({hx(root['table'])} != {hx(table)})")

    pointers = []
    invalid = []
    seen_groups = set()
    max_depth = 0
    group_count = 0
    group_transforms = []

    def walk(group_info, parent_matrix=None, parent_sx_sign=1.0, depth=0):
        nonlocal max_depth, group_count
        parent_matrix = parent_matrix or IDENTITY_MATRIX
        group_address = int(group_info["group"])
        if group_address in seen_groups:
            invalid.append({"group": hx(group_address), "reason": "recursive group reference"})
            return
        seen_groups.add(group_address)
        group_count += 1
        max_depth = max(max_depth, depth)
        group_transform = read_transform_fields(handle, group_address)
        group_matrix = fh6_matrix_from_transform(group_transform)
        current_matrix = multiply_matrix(parent_matrix, group_matrix)
        current_sx_sign = parent_sx_sign * sign_for(group_transform.get("sx", 1.0))
        if len(group_transforms) < 32:
            group_transforms.append({
                "group": hx(group_address),
                "depth": depth,
                "vector_count": int(group_info["vector_count"]),
                "local_translation": [group_transform["x"], group_transform["y"]],
                "scale": [group_transform["sx"], group_transform["sy"]],
                "rotation": group_transform["rotation"],
                "skew": group_transform["skew"],
                "cumulative_sx_sign": current_sx_sign,
                "local_matrix": [round(float(value), 8) for value in group_matrix],
                "cumulative_matrix": [round(float(value), 8) for value in current_matrix],
            })
        for index in range(int(group_info["vector_count"])):
            ptr = ptr_at(handle, int(group_info["table"]), index)
            child = read_group_vector_info(handle, ptr, expected_vtable)
            if child:
                if read_group_parent(handle, ptr) != group_address:
                    invalid.append({"ptr": hx(ptr), "index": index, "depth": depth, "reason": "inconsistent child parent link"})
                    continue
                walk(child, current_matrix, current_sx_sign, depth + 1)
            elif pointer_has_group_signature(handle, ptr, expected_vtable):
                invalid.append({"ptr": hx(ptr), "index": index, "depth": depth, "reason": "unresolved child group"})
            elif layer_pointer_exportable(handle, ptr):
                pointers.append((ptr, current_matrix, current_sx_sign))
            else:
                invalid.append({"ptr": hx(ptr), "index": index, "depth": depth, "reason": "not a layer or known child group"})

    walk(root)
    stats = {
        "flattened": True,
        "top_level_count": int(root["vector_count"]),
        "group_count": group_count,
        "max_depth": max_depth,
        "invalid_entries": len(invalid),
        "invalid_samples": invalid[:24],
        "group_transforms": group_transforms,
    }
    if invalid:
        raise RuntimeError(
            f"flattened export found {len(invalid)} unreadable hierarchy entr{'y' if len(invalid) == 1 else 'ies'}"
        )
    if len(pointers) != int(requested_count):
        stats["count_mismatch"] = {
            "resolved_shape_layers": len(pointers),
            "requested_count": int(requested_count),
            "group_count": group_count,
            "invalid_entries": len(invalid),
            "note": "Export stopped because the resolved shape count changed.",
        }
        raise RuntimeError(
            f"flattened export resolved {len(pointers)} shape layers, expected {requested_count}; "
            f"groups={group_count}, invalid={len(invalid)}"
        )
    return pointers, stats


def rounded_values(values, digits=6):
    return [round(float(value), digits) for value in values]


def layer_fingerprint_item(shape):
    data = list(shape.get("data") or [])
    return {
        "type": int(shape.get("type") or 0),
        "data": rounded_values(data[:7]),
        "color": [int(value) for value in shape.get("color") or []],
        "mask": bool(shape.get("mask")),
    }


def content_hash(shapes):
    digest = hashlib.sha256()
    for shape in shapes:
        digest.update(json.dumps(layer_fingerprint_item(shape), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def summarize_export(shapes, layers):
    type_counts = Counter(str(shape.get("type")) for shape in shapes)
    color_counts = Counter(" ".join(str(int(value)) for value in shape.get("color", [])) for shape in shapes)
    mask_count = sum(1 for shape in shapes if shape.get("mask"))
    read_size_counts = Counter(str(layer.get("read_size")) for layer in layers)
    resource_counts = Counter(str(layer.get("resource_ptr_0xa8")) for layer in layers if layer.get("resource_ptr_0xa8"))
    uniform_template = False
    if shapes:
        first = layer_fingerprint_item(shapes[0])
        uniform_template = all(layer_fingerprint_item(shape) == first for shape in shapes)
    return {
        "content_hash_sha256": content_hash(shapes),
        "type_counts": dict(type_counts.most_common(32)),
        "color_counts": dict(color_counts.most_common(32)),
        "mask_layer_count": mask_count,
        "read_size_counts": dict(read_size_counts.most_common()),
        "resource_ptr_0xa8_counts": dict(resource_counts.most_common(16)),
        "uniform_layer_template": uniform_template,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--group", default=None)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", default=None)
    parser.add_argument("--probe-report", default=None)
    parser.add_argument("--game", default="fh6", choices=tuple(PROFILES))
    parser.add_argument("--include-raw", action="store_true")
    parser.add_argument("--skip-transparent", action="store_true")
    args = parser.parse_args()

    table = parse_int(args.table)
    group = parse_int(args.group) if args.group else None
    report_path = Path(args.report) if args.report else Path(args.out).with_suffix(".report.json")
    locator_report = load_locator_report(args.probe_report)
    handle = open_process(args.pid)
    shapes = []
    layers = []
    failures = []
    flatten_stats = {}
    validation_warnings = []
    live_policy_before = None
    live_policy_after = None
    fm_resource_normalizations = 0
    try:
        if not args.probe_report:
            write_refusal_report(args, table, group, report_path, reasons=["export requires a locator validation report"])
            sys.exit(2)
        probe_ok, probe_reasons = validate_probe_report(args.probe_report, int(args.count), group or 0, table)
        if not probe_ok:
            write_refusal_report(args, table, group, report_path, reasons=probe_reasons)
            sys.exit(2)
        if group is None:
            write_refusal_report(args, table, group, report_path, reasons=["export requires a located game group header"])
            sys.exit(2)
        try:
            group_metadata = read_group_metadata(handle, group)
        except Exception as exc:
            write_refusal_report(args, table, group, report_path, reasons=[f"group header could not be read: {exc}"])
            sys.exit(2)
        editable_ok, editable_reasons = validate_editable_group(
            group_metadata,
            int(args.count),
            table,
            allow_flattened=locator_allows_flattened(locator_report),
            game=args.game,
        )
        if not editable_ok:
            write_refusal_report(args, table, group, report_path, metadata=group_metadata, reasons=editable_reasons)
            sys.exit(2)
        if args.game in LIVE_OWNERSHIP_GAMES:
            root_parent = read_group_parent(handle, group)
            if root_parent is None or root_parent != 0:
                write_refusal_report(
                    args,
                    table,
                    group,
                    report_path,
                    metadata=group_metadata,
                    reasons=["KFPS could not verify the selected live vinyl root."],
                )
                sys.exit(2)
            live_policy_before = assess_fh6_live_group(
                handle,
                group,
                locator_report,
                game=args.game,
            )
            if not live_policy_before.allowed:
                write_refusal_report(
                    args,
                    table,
                    group,
                    report_path,
                    metadata=group_metadata,
                    reasons=[live_policy_before.reason],
                    policy=live_policy_before,
                )
                sys.exit(2)
        try:
            export_pointers, flatten_stats = collect_export_layer_pointers(
                handle,
                group,
                table,
                int(args.count),
                locator_report,
            )
        except Exception as exc:
            write_refusal_report(args, table, group, report_path, metadata=group_metadata, reasons=validation_warnings + [str(exc)])
            sys.exit(2)
        for index, pointer_item in enumerate(export_pointers):
            parent_sx_sign = 1.0
            if isinstance(pointer_item, (list, tuple)) and len(pointer_item) == 3:
                ptr, parent_matrix, parent_sx_sign = pointer_item
            elif isinstance(pointer_item, (list, tuple)) and len(pointer_item) == 2:
                ptr, parent_matrix = pointer_item
            else:
                ptr, parent_matrix = pointer_item, IDENTITY_MATRIX
            raw = try_read_memory(handle, ptr, FULL_LAYER_SIZE)
            layer_size = FULL_LAYER_SIZE
            if len(raw) != FULL_LAYER_SIZE:
                raw = try_read_memory(handle, ptr, GROUPED_SAFE_LAYER_SIZE)
                layer_size = GROUPED_SAFE_LAYER_SIZE
            if len(raw) < MIN_LAYER_DECODE_SIZE:
                failures.append({
                    "index": index,
                    "layer": index + 1,
                    "ptr": hx(ptr),
                    "reason": f"short read {len(raw)}",
                })
                continue
            shape, layer = decode_layer(raw, index, ptr, include_raw=args.include_raw)
            if annotate_fm_export_resource(shape, layer, args.game):
                fm_resource_normalizations += 1
            annotate_canonical_export_resource(shape, layer)
            apply_parent_transform(shape, layer, parent_matrix, parent_sx_sign)
            layer["read_size"] = layer_size
            if len(raw) >= 0xB0:
                layer["resource_ptr_0xa8"] = hx(struct.unpack_from("<Q", raw, 0xA8)[0])
            layers.append(layer)
            if args.skip_transparent and int(shape["color"][3]) <= 0:
                continue
            shapes.append(shape)
        if failures:
            write_refusal_report(
                args,
                table,
                group,
                report_path,
                metadata=group_metadata,
                reasons=[f"KFPS could not read {len(failures)} live vinyl layer(s) completely."],
                policy=live_policy_before,
            )
            sys.exit(2)
        if args.game in LIVE_OWNERSHIP_GAMES:
            if read_group_parent(handle, group) != 0:
                write_refusal_report(
                    args,
                    table,
                    group,
                    report_path,
                    metadata=group_metadata,
                    reasons=["The selected live vinyl root changed while KFPS was reading it."],
                    policy=live_policy_before,
                )
                sys.exit(2)
            live_policy_after = assess_fh6_live_group(
                handle,
                group,
                locator_report,
                game=args.game,
            )
            if not live_policy_after.allowed:
                write_refusal_report(
                    args,
                    table,
                    group,
                    report_path,
                    metadata=group_metadata,
                    reasons=[live_policy_after.reason],
                    policy=live_policy_after,
                )
                sys.exit(2)
            if live_policy_before.fingerprint != live_policy_after.fingerprint:
                write_refusal_report(
                    args,
                    table,
                    group,
                    report_path,
                    metadata=group_metadata,
                    reasons=["The live vinyl hierarchy changed while KFPS was reading it."],
                    policy=live_policy_after,
                )
                sys.exit(2)
    finally:
        close_handle(handle)

    summary = summarize_export(shapes, layers)
    payload = {
        "format": "fh6_typecode_json_export_v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "game": str(args.game).lower(),
            "pid": int(args.pid),
            "group": hx(group) if group is not None else None,
            "table": hx(table),
            "layer_count": int(args.count),
            "coordinate_model": "fh6_live_layer_offsets",
            "type_model": "type = 0x100000 + uint16_at_layer_0x7A; importer writes low uint16 back to 0x7A",
            "resource_identity_model": "canonical KFPS resource family/index with target-game word remapping when available",
            "editable_group_check": {
                "passed": bool(probe_ok and editable_ok),
                "metadata": group_metadata,
                "warnings": validation_warnings,
            },
            "flattened_export": flatten_stats,
            "live_export_policy": live_policy_after.report() if live_policy_after is not None else None,
            "fm_resource_normalization": {
                "game": str(args.game).lower(),
                "normalized_shape_count": fm_resource_normalizations,
            },
        },
        "summary": summary,
        "shapes": shapes,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report = {
        "format": "fh6_typecode_json_export_report_v1",
        "created_utc": payload["created_utc"],
        "pid": int(args.pid),
        "group": payload["source"]["group"],
        "table": hx(table),
        "requested_count": int(args.count),
        "editable_group_check": {
            "passed": bool(probe_ok and editable_ok),
            "metadata": group_metadata,
            "warnings": validation_warnings,
        },
        "validation_warnings": validation_warnings,
        "flattened_export": flatten_stats,
        "live_export_policy": live_policy_after.report() if live_policy_after is not None else None,
        "fm_resource_normalization": {
            "game": str(args.game).lower(),
            "normalized_shape_count": fm_resource_normalizations,
        },
        "preferred_layer_read_size": hx(FULL_LAYER_SIZE),
        "fallback_layer_read_size": hx(GROUPED_SAFE_LAYER_SIZE),
        "minimum_decode_size": hx(MIN_LAYER_DECODE_SIZE),
        "exported_shape_count": len(shapes),
        "read_layer_count": len(layers),
        "failure_count": len(failures),
        "summary": summary,
        "output_json": str(out),
        "layers": layers,
        "failures": failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log(f"Exported {len(shapes)} layer(s) to {out}")
    log(f"Report: {report_path}")
    if failures:
        log(f"Failures: {len(failures)} unreadable layer(s)")


if __name__ == "__main__":
    main()
