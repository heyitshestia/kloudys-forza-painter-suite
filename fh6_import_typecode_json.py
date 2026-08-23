#!/usr/bin/env python3
"""Import a KFPS type-code JSON into a supported live Forza layer table."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import re
import struct
import time
from ctypes import wintypes
from pathlib import Path

from game_profiles import PROFILES
from tools.cgroup.shape_identity import target_game_shape_word


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
FULL_LAYER_SIZE = 0x140
GROUPED_SAFE_LAYER_SIZE = 0xC0
MIN_IMPORT_READ_SIZE = 0x7C
CLEAR_REQUIRED_SIZE = 0x80
ROOT = Path(__file__).resolve().parent
FONT_REGISTRY_PATH = ROOT / "data" / "fh6_font_registry.json"

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
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = (
    wintypes.HANDLE,
    wintypes.LPVOID,
    wintypes.LPCVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hx(value):
    return f"0x{int(value):x}"


def parse_int(value):
    return int(str(value), 0)


def open_process(pid, write):
    access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if write:
        access |= PROCESS_VM_OPERATION | PROCESS_VM_WRITE
    handle = k32.OpenProcess(access, False, int(pid))
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


def write_memory(handle, address, raw, write, *, original=None, rollback_writes=None):
    if not write:
        return
    buf = ctypes.create_string_buffer(raw)
    written = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(handle, int(address), buf, len(raw), ctypes.byref(written))
    if not ok or written.value != len(raw):
        raise ctypes.WinError(ctypes.get_last_error())
    if rollback_writes is not None and original is not None:
        rollback_writes.append((int(address), bytes(original)))


def ptr_at(handle, table, index):
    return struct.unpack("<Q", read_memory(handle, table + index * 8, 8))[0]


def try_read_memory(handle, address, size):
    try:
        return read_memory(handle, address, size)
    except Exception:
        return b""


def is_user_pointer(value):
    return 0x10000 <= int(value) <= 0x7FFFFFFFFFFF


def plausible_layer_blob(raw):
    if len(raw) < CLEAR_REQUIRED_SIZE:
        return False
    try:
        values = (
            *struct.unpack_from("<ff", raw, 0x18),
            *struct.unpack_from("<ff", raw, 0x28),
            struct.unpack_from("<f", raw, 0x50)[0],
            struct.unpack_from("<f", raw, 0x70)[0],
        )
    except (struct.error, ValueError):
        return False
    if not all(math.isfinite(value) and -100000.0 < value < 100000.0 for value in values):
        return False
    if abs(values[2]) < 0.0001 and abs(values[3]) < 0.0001:
        return False
    return raw[0x78] in (0, 1)


def read_table_snapshot(handle, table, layer_count):
    count = int(layer_count)
    if count <= 0:
        raise RuntimeError("live import requires a positive template layer count")
    raw = read_memory(handle, int(table), count * 8)
    pointers = list(struct.unpack(f"<{count}Q", raw))
    if len(set(pointers)) != count:
        raise RuntimeError("live import safety preflight rejected duplicate layer pointers")
    invalid = [index for index, pointer in enumerate(pointers) if not is_user_pointer(pointer)]
    if invalid:
        raise RuntimeError(
            f"live import safety preflight rejected an invalid layer pointer at slot {invalid[0] + 1}"
        )
    return pointers


def assert_table_unchanged(handle, table, pointers):
    current = read_table_snapshot(handle, table, len(pointers))
    if current != pointers:
        raise RuntimeError("live import template changed during safety validation; no further writes were attempted")


def preflight_layer_table(handle, table, layer_count):
    pointers = read_table_snapshot(handle, table, layer_count)
    layers = []
    for index, pointer in enumerate(pointers):
        raw, read_size = read_layer_blob(handle, pointer)
        if not plausible_layer_blob(raw):
            raise RuntimeError(
                f"live import safety preflight rejected unreadable or invalid layer {index + 1} at {hx(pointer)}"
            )
        layers.append((pointer, raw, read_size))
    assert_table_unchanged(handle, table, pointers)
    return pointers, layers


def rollback_memory(handle, rollback_writes):
    restored = 0
    failed = 0
    for address, original in reversed(rollback_writes):
        try:
            write_memory(handle, address, original, True)
            restored += 1
        except Exception:
            failed += 1
    return restored, failed


def decode(raw):
    return {
        "shape_id_byte": raw[0x7A],
        "shape_word": struct.unpack_from("<H", raw, 0x7A)[0],
        "color_rgba": list(raw[0x74:0x78]),
        "position": list(struct.unpack_from("<ff", raw, 0x18)),
        "scale": list(struct.unpack_from("<ff", raw, 0x28)),
        "rotation": struct.unpack_from("<f", raw, 0x50)[0],
        "resource_ptr_0xa8": hx(struct.unpack_from("<Q", raw, 0xA8)[0]),
    }


def read_layer_blob(handle, ptr):
    raw = try_read_memory(handle, ptr, FULL_LAYER_SIZE)
    if len(raw) == FULL_LAYER_SIZE:
        return raw, FULL_LAYER_SIZE
    raw = try_read_memory(handle, ptr, GROUPED_SAFE_LAYER_SIZE)
    if len(raw) == GROUPED_SAFE_LAYER_SIZE:
        return raw, GROUPED_SAFE_LAYER_SIZE
    return raw, len(raw)


def decode_partial(raw):
    out = {
        "bytes_read": len(raw),
    }
    if len(raw) > 0x7A:
        out["shape_id_byte"] = raw[0x7A]
    if len(raw) >= 0x7C:
        out["shape_word"] = struct.unpack_from("<H", raw, 0x7A)[0]
    if len(raw) >= 0x78:
        out["color_rgba"] = list(raw[0x74:0x78])
    if len(raw) >= 0x20:
        out["position"] = list(struct.unpack_from("<ff", raw, 0x18))
    if len(raw) >= 0x30:
        out["scale"] = list(struct.unpack_from("<ff", raw, 0x28))
    if len(raw) >= 0x54:
        out["rotation"] = struct.unpack_from("<f", raw, 0x50)[0]
    if len(raw) >= 0xB0:
        out["resource_ptr_0xa8"] = hx(struct.unpack_from("<Q", raw, 0xA8)[0])
    return out


def clamp_color(values):
    vals = list(values or [255, 255, 255, 255])
    if len(vals) == 3:
        vals.append(255)
    if len(vals) != 4:
        raise ValueError(f"invalid color: {values}")
    return bytes(max(0, min(255, int(v))) for v in vals)


def shape_mask_flag(shape, data):
    for key in ("mask", "is_mask", "isMask"):
        if key in shape:
            return bool(shape.get(key))
    if len(data) > 6:
        try:
            return bool(int(float(data[6])))
        except (TypeError, ValueError):
            return bool(data[6])
    return False


SUPPORTED_PAGE1_CODES = {
    1048677,  # Square
    1048678,  # Circle
    1048679,  # Triangle
    1048688,  # Circle Border
    1048712,  # Ellipse
}

LEGACY_RECTANGLE_TYPES = {1, 2}
LEGACY_ELLIPSE_TYPES = {8, 16}
LEGACY_RECTANGLE_WORD = 0x0065
LEGACY_ELLIPSE_WORD = 0x0066
LEGACY_RECTANGLE_DIVISOR = 127.0
LEGACY_ELLIPSE_DIVISOR = 63.0


def parse_numeric_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 0)
        except ValueError:
            return None
    return None


def load_font_registry():
    if not FONT_REGISTRY_PATH.exists():
        return {}
    payload = json.loads(FONT_REGISTRY_PATH.read_text(encoding="utf-8"))
    rows = payload.get("glyphs", payload if isinstance(payload, list) else [])
    registry = {
        "by_key": {},
        "by_name": {},
    }
    for row in rows:
        try:
            font = int(row["font"])
            block = normalize_font_block(row["block"])
            glyph = normalize_font_glyph(row["glyph"], block)
            word = int(row["fh6_shape_word"])
        except (KeyError, TypeError, ValueError):
            continue
        item = {
            "font": font,
            "block": block,
            "glyph": glyph,
            "shape_word": word & 0xFFFF,
            "shape_byte": word & 0xFF,
            "shape_name": row.get("shape_name") or f"Forza Font {font} {glyph}",
            "source": "fh6_font_registry_v1",
        }
        registry["by_key"][(font, block, glyph)] = item
        registry["by_name"][normalize_name(item["shape_name"])] = item
    return registry


def normalize_name(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def normalize_font_block(value):
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "uppercase": "upper",
        "upper_case": "upper",
        "capital": "upper",
        "capitals": "upper",
        "lowercase": "lower",
        "lower_case": "lower",
        "numbers": "number",
        "numeric": "number",
        "upper_symbols": "upper_symbol",
        "upper_symbol": "upper_symbol",
        "uppercase_symbol": "upper_symbol",
        "uppercase_symbols": "upper_symbol",
        "lower_symbols": "lower_symbol",
        "lower_symbol": "lower_symbol",
        "lowercase_symbol": "lower_symbol",
        "lowercase_symbols": "lower_symbol",
    }
    return aliases.get(text, text)


def normalize_font_glyph(value, block=None):
    glyph = str(value if value is not None else "").strip()
    named = {
        "exclamation": "!",
        "exclamation mark": "!",
        "question": "?",
        "question mark": "?",
        "ampersand": "&",
        "at": "@",
        "at symbol": "@",
        "hash": "#",
        "pound": "£",
        "pound sign": "£",
        "yen": "¥",
        "yen sign": "¥",
        "euro": "€",
        "euro sign": "€",
        "dollar": "$",
        "dollar sign": "$",
        "percent": "%",
        "percent sign": "%",
        "colon": ":",
        "semicolon": ";",
        "slash": "/",
        "caret": "^",
        "caret symbol": "^",
        "plus": "+",
        "plus symbol": "+",
        "eszett": "ß",
        "eszett symbol": "ß",
        "ae": "æ",
    }
    glyph = named.get(glyph.lower(), glyph)
    if block == "upper" and len(glyph) == 1:
        return glyph.upper()
    if block == "lower" and len(glyph) == 1:
        return glyph.lower()
    return glyph


def infer_font_block(glyph, explicit_block=None):
    if explicit_block:
        return normalize_font_block(explicit_block)
    glyph = normalize_font_glyph(glyph)
    if len(glyph) == 1 and glyph.isalpha():
        return "upper" if glyph == glyph.upper() else "lower"
    if str(glyph).isdigit():
        return "number"
    if glyph in ("!", "?", "&"):
        return "upper_symbol"
    return "lower_symbol"


def resolve_font_from_name(value, registry):
    name = normalize_name(value)
    if not name:
        return None
    if name in registry.get("by_name", {}):
        return registry["by_name"][name]
    match = re.search(r"forza font\s+(\d+)\s+(.+)", name)
    if not match:
        return None
    font = int(match.group(1))
    tail = match.group(2).strip()
    block = None
    glyph_text = tail
    for prefix, prefix_block in (
        ("upper ", "upper"),
        ("lower ", "lower"),
        ("number ", "number"),
    ):
        if tail.startswith(prefix):
            block = prefix_block
            glyph_text = tail[len(prefix):]
            break
    symbol_names = {
        "exclamation mark": ("upper_symbol", "!"),
        "question mark": ("upper_symbol", "?"),
        "ampersand": ("upper_symbol", "&"),
        "at symbol": (block or "lower_symbol", "@"),
        "percent sign": ("lower_symbol", "%"),
        "colon": ("lower_symbol", ":"),
        "semicolon": ("lower_symbol", ";"),
        "slash": ("lower_symbol", "/"),
        "dollar sign": ("lower_symbol", "$"),
        "pound sign": ("lower_symbol", "£"),
        "yen sign": ("lower_symbol", "¥"),
        "euro sign": ("lower_symbol", "€"),
        "ae": ("lower_symbol", "æ"),
        "caret symbol": ("lower_symbol", "^"),
        "eszett symbol": ("lower_symbol", "ß"),
        "hash": ("lower_symbol", "#"),
        "plus symbol": ("lower_symbol", "+"),
    }
    if tail in symbol_names:
        block, glyph = symbol_names[tail]
    else:
        glyph = normalize_font_glyph(glyph_text, block)
        block = infer_font_block(glyph, block)
    return registry.get("by_key", {}).get((font, block, normalize_font_glyph(glyph, block)))


def resolve_font_shape(shape, registry):
    for key in ("font_shape", "fontShape", "shape_name", "shapeName", "name", "type"):
        value = shape.get(key)
        if isinstance(value, str) and parse_numeric_int(value) is None:
            item = resolve_font_from_name(value, registry)
            if item:
                return item
    font = None
    for key in ("font", "font_index", "fontIndex", "forza_font", "forzaFont"):
        if key in shape:
            font = parse_numeric_int(shape.get(key))
            break
    glyph = None
    for key in ("glyph", "char", "character", "text"):
        if key in shape:
            glyph = shape.get(key)
            break
    if font is None or glyph is None:
        return None
    block = infer_font_block(glyph, shape.get("block") or shape.get("font_block") or shape.get("fontBlock"))
    glyph = normalize_font_glyph(glyph, block)
    return registry.get("by_key", {}).get((int(font), block, glyph))


def shape_type_fields(shape, font_registry):
    explicit_word = parse_numeric_int(shape.get("shape_word", shape.get("shapeWord", shape.get("type_word", shape.get("typeWord")))))
    if explicit_word is not None:
        type_code = parse_numeric_int(shape.get("type")) or explicit_word
        return type_code, explicit_word & 0xFFFF, None
    type_code = parse_numeric_int(shape.get("type"))
    if type_code is not None:
        return type_code, type_code & 0xFFFF, None
    font_item = resolve_font_shape(shape, font_registry)
    if font_item:
        word = int(font_item["shape_word"]) & 0xFFFF
        return 0x100000 + word, word, font_item
    raise ValueError(f"shape type is not numeric and does not resolve to a known font glyph: {shape.get('type')!r}")


def is_transparent_canvas_sentinel(index, shape):
    if index != 0:
        return False
    type_code = parse_numeric_int(shape.get("type"))
    if type_code != 1:
        return False
    data = shape.get("data")
    if not isinstance(data, list) or len(data) != 4:
        return False
    try:
        x, y, width, height = [float(v) for v in data]
    except (TypeError, ValueError):
        return False
    if x != 0 or y != 0 or width <= 0 or height <= 0:
        return False
    try:
        color = clamp_color(shape.get("color"))
    except ValueError:
        return False
    return color[3] <= 0


def legacy_geometry_shape(index, shape):
    """Convert old generated geometry JSON into memory-ready FH6 shape fields.

    The universal importer normally expects exported FH6 type-code JSON where
    data is already memory-position/scale/rotation. Some shared "handmade" JSONs
    are actually old generator geometry: type 1/2 rectangles and type 8/16
    ellipses with pixel-space x,y,width,height,rotation. Supporting that format
    here avoids aborting before import, while keeping the written memory model
    identical to the normal importer.
    """
    if any(key in shape for key in ("shape_word", "shapeWord", "type_word", "typeWord", "font_shape", "fontShape")):
        return None
    type_code = parse_numeric_int(shape.get("type"))
    if type_code not in LEGACY_RECTANGLE_TYPES and type_code not in LEGACY_ELLIPSE_TYPES:
        return None
    data = shape.get("data")
    if not isinstance(data, list) or len(data) < 4:
        return None
    try:
        x, y, width, height = [float(v) for v in data[:4]]
        rotation = float(data[4]) if len(data) >= 5 else 0.0
    except (TypeError, ValueError):
        return None
    color = list(clamp_color(shape.get("color")))
    if color[3] <= 0:
        return {
            "skip": {
                "source_index": index,
                "source_layer": index + 1,
                "type_code": type_code,
                "hex": f"0x{type_code:x}",
                "reason": "transparent legacy geometry shape",
            }
        }
    if type_code in LEGACY_RECTANGLE_TYPES:
        shape_word = LEGACY_RECTANGLE_WORD
        divisor = LEGACY_RECTANGLE_DIVISOR
        rotation = rotation if type_code == 2 else 0.0
        full_code = 1048677
    else:
        shape_word = LEGACY_ELLIPSE_WORD
        divisor = LEGACY_ELLIPSE_DIVISOR
        rotation = rotation if type_code == 16 else 0.0
        full_code = 1048678
    return {
        "index": index,
        "type_code": full_code,
        "shape_byte": shape_word & 0xFF,
        "shape_word": shape_word & 0xFFFF,
        "page_byte": (shape_word >> 8) & 0xFF,
        "font_shape": None,
        "x": float(x),
        "y": float(-y),
        "sx": float(width) / divisor,
        "sy": float(height) / divisor,
        "rotation": float((360.0 - rotation) % 360.0),
        "skew": float(data[5]) if len(data) > 5 else 0.0,
        "extra_data": list(data[5:]),
        "color": color,
        "mask": shape_mask_flag(shape, data),
        "score": shape.get("score"),
        "source_format": "legacy_geometry",
    }


def load_shapes(path, allow_unknown_low_byte=False, target_game="fh6"):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    shapes = payload.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        raise ValueError("JSON must contain non-empty shapes list.")
    out = []
    skipped = []
    font_registry = load_font_registry()
    for i, shape in enumerate(shapes):
        if is_transparent_canvas_sentinel(i, shape):
            skipped_item = {
                "source_index": i,
                "source_layer": i + 1,
                "type_code": parse_numeric_int(shape.get("type")),
                "hex": "0x1",
                "reason": "transparent canvas/background sentinel",
            }
            skipped.append(skipped_item)
            print("[skip] transparent canvas/background sentinel at source layer 1", flush=True)
            continue
        legacy_shape = legacy_geometry_shape(i, shape)
        if isinstance(legacy_shape, dict) and "skip" in legacy_shape:
            skipped.append(legacy_shape["skip"])
            print(f"[skip] transparent legacy geometry shape at source layer {i + 1}", flush=True)
            continue
        if legacy_shape:
            out.append(legacy_shape)
            continue
        code, source_shape_word, font_item = shape_type_fields(shape, font_registry)
        if (
            code not in SUPPORTED_PAGE1_CODES
            and font_item is None
            and not allow_unknown_low_byte
        ):
            skipped_item = {
                "source_index": i,
                "source_layer": i + 1,
                "type_code": code,
                "hex": f"0x{code:x}",
                "reason": "unsupported non-page-1 primitive code",
            }
            skipped.append(skipped_item)
            print(f"[skip] unsupported type code {code} / 0x{code:x} at source layer {i + 1}", flush=True)
            continue
        shape_word = target_game_shape_word(shape, source_shape_word, target_game)
        data = shape["data"]
        if len(data) < 5:
            raise ValueError(f"shape {i} data must have x,y,sx,sy,rotation")
        out.append({
            "index": i,
            "type_code": 0x100000 + shape_word,
            "source_type_code": code,
            "source_shape_word": source_shape_word,
            "shape_byte": shape_word & 0xFF,
            "shape_word": shape_word & 0xFFFF,
            "page_byte": (shape_word >> 8) & 0xFF,
            "font_shape": font_item,
            "x": float(data[0]),
            "y": float(data[1]),
            "sx": float(data[2]),
            "sy": float(data[3]),
            "rotation": float(data[4]),
            "skew": float(data[5]) if len(data) > 5 else 0.0,
            "extra_data": list(data[5:]),
            "color": list(clamp_color(shape.get("color"))),
            "mask": shape_mask_flag(shape, data),
            "score": shape.get("score"),
        })
    return out, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--template-count", type=int, default=None)
    parser.add_argument("--clear-unused", action="store_true")
    parser.add_argument(
        "--compact-supported-layers",
        action="store_true",
        help="Pack supported source shapes into consecutive target layers, removing holes from skipped unsupported shapes.",
    )
    parser.add_argument("--allow-unknown-low-byte", action="store_true")
    parser.add_argument("--game", default="fh6", choices=tuple(PROFILES))
    parser.add_argument("--backup", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    shapes, skipped_shapes = load_shapes(
        args.json,
        allow_unknown_low_byte=args.allow_unknown_low_byte,
        target_game=args.game,
    )
    if args.limit is not None:
        shapes = shapes[: args.limit]
    if not args.template_count:
        raise ValueError("live import requires --template-count for a complete safety preflight")
    template_count = int(args.template_count)
    if len(shapes) > template_count:
        raise ValueError(f"import has {len(shapes)} shapes but the template has only {template_count} layers")
    table = parse_int(args.table)
    handle = open_process(args.pid, args.write)
    backup_layers = []
    report_layers = []
    failures = []
    partial_clears = []
    rollback_writes = []
    try:
        log(f"validating all {template_count} template layers before any memory write")
        pointers, preflight_layers = preflight_layer_table(handle, table, template_count)
        backup_layers = [
            {
                "index": index,
                "ptr": hx(pointer),
                "read_size": read_size,
                "raw_hex": raw.hex(),
                "decoded": decode(raw) if len(raw) >= 0xB0 else decode_partial(raw),
                "partial": len(raw) < FULL_LAYER_SIZE,
            }
            for index, (pointer, raw, read_size) in enumerate(preflight_layers)
        ]
        backup = {
            "format": "fh6_typecode_json_import_backup_v2",
            "pid": args.pid,
            "table": args.table,
            "source_json": args.json,
            "template_count": template_count,
            "layers": backup_layers,
        }
        backup_path = Path(args.backup)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        log(f"complete pre-write backup saved: {args.backup}")
        assert_table_unchanged(handle, table, pointers)

        used_indices = set()
        for target_idx, item in enumerate(shapes):
            idx = target_idx if args.compact_supported_layers else item["index"]
            if idx < 0 or idx >= template_count:
                raise RuntimeError(f"source layer {item['index'] + 1} maps outside the verified template")
            if target_idx % 64 == 0:
                assert_table_unchanged(handle, table, pointers)
            used_indices.add(idx)
            ptr, before, before_size = preflight_layers[idx]
            writes = [
                (0x18, struct.pack("<ff", item["x"], item["y"])),
                (0x28, struct.pack("<ff", item["sx"], item["sy"])),
                (0x50, struct.pack("<f", item["rotation"])),
                (0x70, struct.pack("<f", item["skew"])),
                (0x74, bytes(item["color"])),
                (0x78, b"\x01" if item.get("mask") else b"\x00"),
                (0x7A, struct.pack("<H", item["shape_word"])),
            ]
            for offset, raw in writes:
                write_memory(
                    handle,
                    ptr + offset,
                    raw,
                    args.write,
                    original=before[offset:offset + len(raw)],
                    rollback_writes=rollback_writes,
                )
                if args.write and read_memory(handle, ptr + offset, len(raw)) != raw:
                    raise RuntimeError(f"write verification failed for layer {idx + 1} at offset {hx(offset)}")
            after, after_size = read_layer_blob(handle, ptr) if args.write else (before, before_size)
            if len(after) < MIN_IMPORT_READ_SIZE:
                raise RuntimeError(f"post-write validation could not read layer {idx + 1}")
            report_layers.append({
                "index": idx,
                "target_index": idx,
                "source_index": item["index"],
                "ptr": hx(ptr),
                "read_size": before_size,
                "shape": item,
                "before": decode(before) if len(before) >= 0xB0 else decode_partial(before),
                "after": decode(after) if len(after) >= 0xB0 else decode_partial(after),
                "after_read_size": after_size,
            })
            if target_idx == 0 or (target_idx + 1) % 10 == 0 or target_idx == len(shapes) - 1:
                log(
                    f"{'wrote' if args.write else 'would write'} "
                    f"target {idx + 1}, source {item['index'] + 1} "
                    f"({target_idx + 1}/{len(shapes)}) code={item['type_code']} "
                    f"word=0x{item['shape_word']:04x} byte={item['shape_byte']} page={item['page_byte']}"
                )
        if args.clear_unused:
            clear_writes = [
                (0x18, struct.pack("<ff", 0.0, 0.0)),
                (0x28, struct.pack("<ff", 0.001, 0.001)),
                (0x50, struct.pack("<f", 0.0)),
                (0x74, bytes([0, 0, 0, 0])),
                (0x78, b"\x00"),
            ]
            first_clear = None
            for idx in range(template_count):
                if idx in used_indices:
                    continue
                if first_clear is None:
                    first_clear = idx
                if idx % 64 == 0:
                    assert_table_unchanged(handle, table, pointers)
                ptr, before, _before_size = preflight_layers[idx]
                for offset, raw in clear_writes:
                    write_memory(
                        handle,
                        ptr + offset,
                        raw,
                        args.write,
                        original=before[offset:offset + len(raw)],
                        rollback_writes=rollback_writes,
                    )
                    if args.write and read_memory(handle, ptr + offset, len(raw)) != raw:
                        raise RuntimeError(f"clear verification failed for layer {idx + 1} at offset {hx(offset)}")
                if idx == first_clear or (idx + 1) % 100 == 0 or idx == template_count - 1:
                    log(f"{'cleared' if args.write else 'would clear'} unused layer {idx + 1}/{template_count}")
        assert_table_unchanged(handle, table, pointers)
    except Exception as exc:
        if args.write and rollback_writes:
            try:
                assert_table_unchanged(handle, table, pointers)
            except Exception:
                log("live import aborted after the template changed; rollback was withheld to avoid stale-pointer writes")
            else:
                restored, rollback_failures = rollback_memory(handle, rollback_writes)
                log(f"live import aborted; rollback restored {restored} write(s), failures={rollback_failures}")
                if rollback_failures:
                    raise RuntimeError(
                        f"live import failed and rollback was incomplete ({rollback_failures} restore failures)"
                    ) from exc
                raise RuntimeError("live import failed; all completed memory writes were rolled back") from exc
        raise
    finally:
        close_handle(handle)

    report = {
        "format": "fh6_typecode_json_import_report_v1",
        "pid": args.pid,
        "table": args.table,
        "source_json": args.json,
        "target_game": args.game,
        "write": args.write,
        "safety_preflight": "complete",
        "preflight_layer_count": template_count,
        "backup_format": "fh6_typecode_json_import_backup_v2",
        "preferred_layer_read_size": hx(FULL_LAYER_SIZE),
        "fallback_layer_read_size": hx(GROUPED_SAFE_LAYER_SIZE),
        "minimum_import_read_size": hx(MIN_IMPORT_READ_SIZE),
        "compact_supported_layers": args.compact_supported_layers,
        "unsupported_shape_count": len(skipped_shapes),
        "unsupported_shapes": skipped_shapes,
        "imported_layer_count": sum(1 for row in report_layers if "after" in row),
        "import_failure_count": sum(1 for row in failures if row.get("phase") == "import"),
        "clear_failure_count": sum(1 for row in failures if row.get("phase") == "clear"),
        "partial_clear_count": len(partial_clears),
        "partial_clears": partial_clears,
        "failure_count": len(failures),
        "failures": failures,
        "layers": report_layers,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"backup: {args.backup}")
    log(f"report: {args.report}")
    log(f"failures: {len(failures)}")


if __name__ == "__main__":
    main()
