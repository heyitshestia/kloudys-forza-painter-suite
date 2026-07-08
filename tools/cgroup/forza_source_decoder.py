#!/usr/bin/env python3
"""Export-only decoder for Forza C_group/C_livery sources.

This module is intentionally isolated from the live memory importer/exporter.
It reads game file artifacts and emits flattened KFPS-style layer data so shape
identity can be validated against the game/save format instead of against a
possibly incorrect KFPS JSON export.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    from .shape_identity import TYPE_CODE_BASE, normalize_game_key, normalize_game_shape_word
except ImportError:  # pragma: no cover - direct script execution fallback
    from shape_identity import TYPE_CODE_BASE, normalize_game_key, normalize_game_shape_word


MAX_SHAPE_ID = 0x2000
LIVERY_SECTION_NAMES = [
    "Front",
    "Back",
    "Top",
    "Left",
    "Right",
    "Spoiler",
    "FrontWindshield",
    "BackWindshield",
    "TopWindow",
    "LeftWindow",
    "RightWindow",
]
LIVERY_EMPTY_SLOT_SIZE = 23
LIVERY_POPULATED_REMNANT_SIZE = 18


class DecodeError(RuntimeError):
    """Raised when a Forza source cannot be decoded safely."""


@dataclass
class Transform:
    x: float = 0.0
    y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    rotation: float = 0.0


@dataclass
class ShapeNode:
    shape_id: int
    x: float
    y: float
    sx: float
    sy: float
    rotation: float
    skew: float
    color_rgba: tuple[int, int, int, int]
    offset: int
    marker: bytes = b""
    flags: int = 0
    mask: bool = False
    section: str | None = None


@dataclass
class GroupNode:
    transform: Transform = field(default_factory=Transform)
    expected_children: int | None = None
    items: list[ShapeNode | "GroupNode"] = field(default_factory=list)
    flags: int = 0
    mask: bool = False
    offset: int = 0
    marker: bytes = b""
    child_bitmap: bytes = b""
    source: str = ""
    section: str | None = None


@dataclass
class GroupInfo:
    count: int
    child_blocks: int
    size: int
    flags: int = 0
    marker: bytes = b""
    inline_transform: Transform | None = None


@dataclass
class WalkState:
    stack: list[GroupNode]
    pending_transform: Transform | None = None
    pending_marker: bytes = b""
    pending_prefix: bytes = b""
    pending_flags: int = 0
    pending_mask: bool = False


@dataclass
class DecodedSource:
    source_path: str
    source_kind: str
    layers: list[dict[str, Any]]
    report: dict[str, Any]


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_f32(data: bytes, offset: int) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def normalize_rotation(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    value = value % 360.0
    if abs(value - 360.0) < 1e-9:
        return 0.0
    return value


def has_color_data(color: tuple[int, int, int, int]) -> bool:
    return color[0] != color[1] or color[1] != color[2]


def unwrap_forza_container(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"gyvl") or raw.startswith(b"vlrc"):
        return raw
    return unwrap_forza_container_bytes(raw, path)


def unwrap_forza_container_bytes(raw: bytes, path: Path) -> bytes:
    if len(raw) < 8:
        raise DecodeError(f"{path} is too short for a Forza container")
    pos = 0
    payloads: list[bytes] = []
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise DecodeError(f"{path} has a truncated Forza container block at 0x{pos:x}")
        compressed_len, payload_len = struct.unpack_from("<II", raw, pos)
        pos += 8
        remaining = len(raw) - pos
        if compressed_len <= 0 or compressed_len > remaining:
            expected = len(raw) - 8 if not payloads else remaining
            raise DecodeError(
                f"{path} compressed length header does not match file size "
                f"({compressed_len} != {expected})"
            )
        compressed = raw[pos : pos + compressed_len]
        pos += compressed_len
        try:
            payload = zlib.decompress(compressed)
        except zlib.error as exc:
            raise DecodeError(f"{path} zlib payload could not be decompressed: {exc}") from exc
        if payload_len != len(payload):
            raise DecodeError(
                f"{path} decompressed length header does not match payload "
                f"({payload_len} != {len(payload)})"
            )
        payloads.append(payload)
    return b"".join(payloads)


def resolve_forza_source(path: Path | str) -> tuple[Path, str]:
    path = Path(path)
    if path.is_dir():
        cgroup = path / "C_group"
        clivery = path / "C_livery"
        data = path / "data"
        if cgroup.is_file():
            return cgroup, "cgroup"
        if clivery.is_file():
            return clivery, "clivery"
        if data.is_file() and path.parent.name.lower() == "layergroups":
            return data, "cgroup"
        if data.is_file() and path.parent.name.lower() == "liveries":
            return data, "clivery"
        raise DecodeError(f"{path} is a folder but does not contain C_group, C_livery, or known Forza data")
    name = path.name.lower()
    if name == "c_group":
        return path, "cgroup"
    if name == "c_livery":
        return path, "clivery"
    raw = path.read_bytes()
    if raw.startswith(b"gyvl"):
        return path, "cgroup"
    if raw.startswith(b"vlrc"):
        return path, "clivery"
    payload = unwrap_forza_container_bytes(raw, path)
    if payload.startswith(b"gyvl"):
        return path, "cgroup"
    if payload.startswith(b"vlrc") or b"gyvl" in payload[:0x200]:
        return path, "clivery"
    raise DecodeError(f"{path} is not recognized as C_group or C_livery")


def enforce_privacy(path: Path, kind: str, payload: bytes, allow_locked: bool = False) -> list[str]:
    warnings: list[str] = []
    if kind == "cgroup" and len(payload) > 0x1D and payload[0x1D] == 0x21:
        message = "privacy guard: C_group has the locked payload marker at 0x1D"
        if not allow_locked:
            raise DecodeError(message)
        warnings.append(message)
    if kind == "clivery" and len(payload) >= 12 and read_u32(payload, 8) == 1:
        message = "privacy guard: C_livery has the locked payload flag at offset 0x08"
        if not allow_locked:
            raise DecodeError(message)
        warnings.append(message)
    return warnings


def read_transform_payload(data: bytes, pos: int, end: int) -> Transform | None:
    if pos + 16 > end:
        return None
    sx = read_f32(data, pos + 8)
    rotation = read_f32(data, pos + 12)
    if not (0.0001 <= abs(sx) <= 200.0 and abs(rotation) <= 10000.0):
        return None
    return Transform(
        x=read_f32(data, pos),
        y=read_f32(data, pos + 4),
        sx=sx,
        sy=sx,
        rotation=rotation,
    )


def bytes_at(data: bytes, pos: int, pattern: bytes, end: int | None = None) -> bool:
    if pos < 0:
        return False
    stop = pos + len(pattern)
    if end is not None and stop > end:
        return False
    return data[pos:stop] == pattern


def is_valid_shape_at(data: bytes, pos: int, end: int) -> bool:
    if pos < 0 or pos >= end or pos >= len(data):
        return False
    if bytes_at(data, pos, b"\x00\x02", end) or bytes_at(data, pos, b"\x01\x02", end):
        if pos + 32 > end:
            return False
        shape_id = read_u16(data, pos + 2)
        x = read_f32(data, pos + 8)
        y = read_f32(data, pos + 12)
        sx = read_f32(data, pos + 16)
        return 0 < shape_id < MAX_SHAPE_ID and abs(x) < 50000.0 and abs(y) < 50000.0 and 1e-6 < abs(sx) < 200.0
    if data[pos] == 0x02:
        if pos + 31 > end:
            return False
        shape_id = read_u16(data, pos + 1)
        x = read_f32(data, pos + 7)
        y = read_f32(data, pos + 11)
        sx = read_f32(data, pos + 15)
        return 0 < shape_id < MAX_SHAPE_ID and abs(x) < 50000.0 and abs(y) < 50000.0 and 1e-6 < abs(sx) < 200.0
    return False


def decode_shape_at(data: bytes, pos: int, is_mask: bool = False, flags: int = 0) -> ShapeNode:
    first = data[pos]
    off = 0 if first in (0x00, 0x01) else -1
    marker_len = 2 if off == 0 else 1
    if off == 0 and flags == 0:
        flags = first
    b, g, r, a = data[pos + 28 + off : pos + 32 + off]
    return ShapeNode(
        shape_id=read_u16(data, pos + 2 + off),
        rotation=read_f32(data, pos + 4 + off),
        x=read_f32(data, pos + 8 + off),
        y=read_f32(data, pos + 12 + off),
        sx=read_f32(data, pos + 16 + off),
        sy=read_f32(data, pos + 20 + off),
        skew=read_f32(data, pos + 24 + off),
        color_rgba=(r, g, b, a),
        offset=pos,
        marker=data[pos : pos + marker_len],
        flags=flags,
        mask=is_mask,
    )


def transform_markers_at(data: bytes, pos: int, end: int, livery: bool = False) -> list[bytes]:
    if pos >= end:
        return []
    markers: list[bytes] = []
    term = 0x01 if livery else 0x03
    if not livery and data[pos] == 0x00:
        cursor = pos + 1
        while cursor < end and data[cursor] == 0x01:
            cursor += 1
        if cursor < end and data[cursor] == term:
            markers.append(data[pos : cursor + 1])
    if pos + 1 < end and (data[pos] & 0x01) and data[pos + 1] == term:
        markers.append(data[pos : pos + 2])
    std_markers = [
        b"\x00\x01\x01\x03",
        b"\x00\x01\x03",
        b"\xdf\x03\x03",
        b"\x03\x03",
        b"\x3f\x03",
        b"\x2f\x03",
        b"\x1f\x03",
        b"\x0f\x03",
        b"\x0d\x03",
        b"\x07\x03",
        b"\x01\x03",
        b"\x00\x03",
        b"\x03",
    ]
    for marker in std_markers:
        if livery and marker[0] == 0x00:
            continue
        candidate = marker[:-1] + bytes([0x01]) if livery else marker
        if data[pos : pos + len(candidate)] == candidate and candidate not in markers:
            markers.append(candidate)
    markers.sort(key=len, reverse=True)
    return markers


def read_transform_record(data: bytes, pos: int, end: int, livery: bool = False) -> tuple[int, Transform, bytes] | None:
    for marker in transform_markers_at(data, pos, end, livery=livery):
        transform = read_transform_payload(data, pos + len(marker), end)
        if not transform:
            continue
        size = len(marker) + 16
        sy_pos = pos + size
        if sy_pos + 5 <= end and (data[sy_pos] & ~0x40) == 0x30:
            sy = read_f32(data, sy_pos + 1)
            if 0.0001 <= abs(sy) <= 5000.0:
                transform.sy = sy
                size += 5
        return size, transform, marker
    return None


def read_livery_transform(data: bytes, pos: int, end: int) -> tuple[int, Transform, bytes] | None:
    if pos >= end or data[pos] not in (0x00, 0x01):
        return None
    transform = read_transform_payload(data, pos + 1, end)
    if not transform:
        return None
    size = 17
    sy_pos = pos + size
    if sy_pos + 5 <= end and (data[sy_pos] & ~0x40) == 0x30:
        sy = read_f32(data, sy_pos + 1)
        if 0.0001 <= abs(sy) <= 5000.0:
            transform.sy = sy
            size += 5
    next_pos = pos + size
    if not (valid_counted_group_at(data, next_pos, end, livery=True) or valid_markerless_group_at(data, next_pos, end, True, True)):
        return None
    return size, transform, data[pos : pos + 1]


def _read_inline_transform(data: bytes, extra: int, end: int, livery: bool) -> tuple[int, Transform, bytes] | None:
    for marker in transform_markers_at(data, extra, end, livery=livery):
        if livery and marker[-1] == 0x01 and is_valid_shape_at(data, extra + 1, end):
            continue
        transform = read_transform_payload(data, extra + len(marker), end)
        if not transform:
            continue
        size = len(marker) + 16
        sy_pos = extra + size
        if sy_pos + 5 <= end and (data[sy_pos] & ~0x40) == 0x30:
            sy = read_f32(data, sy_pos + 1)
            if 0.0001 <= abs(sy) <= 5000.0:
                transform.sy = sy
                size += 5
        return size, transform, marker
    return None


def livery_transform_then_child_at(data: bytes, pos: int, end: int) -> bool:
    result = read_livery_transform(data, pos, end)
    return result is not None


def valid_markerless_group_at(
    data: bytes,
    pos: int,
    end: int,
    allow_count_one: bool = False,
    livery: bool = False,
) -> GroupInfo | None:
    if pos + 3 > end:
        return None
    count = read_u16(data, pos)
    child_blocks = data[pos + 2]
    min_count = 1 if allow_count_one else 2
    if count < min_count or child_blocks <= 0 or child_blocks != (count + 7) // 8:
        return None
    base_size = 3 + child_blocks + 2
    if pos + base_size > end:
        return None
    info = GroupInfo(count=count, child_blocks=child_blocks, size=base_size, marker=b"")
    extra = pos + base_size
    inline = _read_inline_transform(data, extra, end, livery)
    if inline:
        size, transform, marker = inline
        info.size += size
        info.inline_transform = transform
        info.marker = marker
        return info
    child_here = is_valid_shape_at(data, extra, end) or valid_counted_group_at(data, extra, end, livery) or (
        livery and livery_transform_then_child_at(data, extra, end)
    )
    if child_here:
        return info
    if extra + 1 < end and (
        is_valid_shape_at(data, extra + 1, end)
        or valid_counted_group_at(data, extra + 1, end, livery)
        or (livery and livery_transform_then_child_at(data, extra + 1, end))
    ):
        info.flags |= data[extra] & ~0x40
        info.size += 1
        return info
    return None


def valid_counted_group_at(data: bytes, pos: int, end: int, livery: bool = False) -> GroupInfo | None:
    if pos + 4 > end or data[pos] not in (0x20, 0x60):
        return None
    count = read_u16(data, pos + 1)
    child_blocks = data[pos + 3]
    if count <= 0 or child_blocks <= 0 or child_blocks != (count + 7) // 8:
        return None
    base_size = 4 + child_blocks + 2
    if pos + base_size > end:
        return None
    info = GroupInfo(
        count=count,
        child_blocks=child_blocks,
        size=base_size,
        flags=0x40 if data[pos] == 0x60 else 0,
        marker=data[pos : pos + 1],
    )
    extra = pos + base_size
    inline = _read_inline_transform(data, extra, end, livery)
    if inline:
        size, transform, marker = inline
        info.size += size
        info.inline_transform = transform
        info.marker = marker
        return info
    if extra < end and data[extra] in (0x02, 0x03, 0xFF):
        info.flags |= data[extra] & ~0x40
        info.size += 1
    elif livery and extra + 1 < end and data[extra] == 0x01 and not is_valid_shape_at(data, extra, end):
        if is_valid_shape_at(data, extra + 1, end) or valid_counted_group_at(data, extra + 1, end, True):
            info.flags |= 0x01
            info.size += 1
    return info


def inline_transform_for_first_child(marker: bytes) -> bool:
    if len(marker) == 2 and (marker[0] & 0x01) and marker[1] in (0x01, 0x03):
        return True
    bases = [
        b"\xdf\x03\x03",
        b"\x03\x03",
        b"\x3f\x03",
        b"\x2f\x03",
        b"\x1f\x03",
        b"\x0f\x03",
        b"\x0d\x03",
        b"\x07\x03",
        b"\x01\x03",
        b"\x00\x03",
        b"\x03",
    ]
    return marker in bases or any(marker == m[:-1] + b"\x01" for m in bases)


def apply_group_record(node: GroupNode, info: GroupInfo, source: str, pending_flags: int = 0, pending_mask: bool = False) -> None:
    node.expected_children = info.count
    node.flags = info.flags | pending_flags
    node.mask = bool(node.flags & 0x40) or pending_mask
    node.source = source
    node.marker = info.marker
    if info.inline_transform:
        node.transform = info.inline_transform


def group_complete(group: GroupNode) -> bool:
    return group.expected_children is not None and len(group.items) >= group.expected_children


def close_complete_stack(stack: list[GroupNode]) -> None:
    while len(stack) > 1 and group_complete(stack[-1]):
        stack.pop()


def push_markerless_group(data: bytes, pos: int, end: int, info: GroupInfo, state: WalkState, livery: bool = False) -> int:
    inline_for_first = bool(
        info.inline_transform
        and inline_transform_for_first_child(info.marker)
        and (valid_counted_group_at(data, pos + info.size, end, livery) or valid_markerless_group_at(data, pos + info.size, end, False, livery))
    )
    node = GroupNode(offset=pos)
    apply_group_record(node, info, "markerless", state.pending_flags, state.pending_mask)
    if state.pending_transform:
        if not info.inline_transform or inline_for_first:
            node.transform = state.pending_transform
        else:
            node.transform = compose_group_transform(state.pending_transform, node.transform)
    node.marker = info.marker if info.marker else state.pending_marker
    state.stack[-1].items.append(node)
    state.stack.append(node)
    state.pending_transform = info.inline_transform if inline_for_first else None
    state.pending_marker = info.marker if inline_for_first else b""
    state.pending_prefix = b""
    state.pending_flags = 0
    state.pending_mask = False
    return pos + info.size


def walk_step(data: bytes, pos: int, end: int, state: WalkState, livery: bool = False) -> int:
    markerless = valid_markerless_group_at(data, pos, end, False, livery) if state.pending_transform else None
    if markerless:
        return push_markerless_group(data, pos, end, markerless, state, livery)

    counted = valid_counted_group_at(data, pos, end, livery)
    if counted:
        inline_for_first = bool(
            counted.inline_transform
            and inline_transform_for_first_child(counted.marker)
            and (
                valid_counted_group_at(data, pos + counted.size, end, livery)
                or valid_markerless_group_at(data, pos + counted.size, end, False, livery)
            )
        )
        node = GroupNode(offset=pos, child_bitmap=data[pos + 4 : pos + 4 + counted.child_blocks + 2])
        apply_group_record(node, counted, "counted", state.pending_flags, state.pending_mask)
        if state.pending_transform:
            if not counted.inline_transform or inline_for_first:
                node.transform = state.pending_transform
            else:
                node.transform = compose_group_transform(state.pending_transform, node.transform)
        node.marker = data[pos : pos + 1]
        state.stack[-1].items.append(node)
        state.stack.append(node)
        state.pending_transform = counted.inline_transform if inline_for_first else None
        state.pending_marker = counted.marker if inline_for_first else b""
        state.pending_prefix = b""
        state.pending_flags = 0
        state.pending_mask = False
        return pos + counted.size

    if is_valid_shape_at(data, pos, end):
        if state.pending_transform:
            node = GroupNode(
                transform=state.pending_transform,
                expected_children=2,
                flags=state.pending_flags,
                mask=state.pending_mask,
                offset=pos,
                marker=state.pending_marker,
                source="implicit_transform_pair",
            )
            state.stack[-1].items.append(node)
            state.stack.append(node)
            state.pending_transform = None
            state.pending_marker = b""
            state.pending_prefix = b""
            state.pending_flags = 0
            state.pending_mask = False
        flags = state.pending_flags
        if bytes_at(data, pos, b"\x01\x02", end):
            flags |= 0x01
        shape = decode_shape_at(data, pos, is_mask=state.pending_mask, flags=flags)
        state.stack[-1].items.append(shape)
        state.pending_flags = 0
        state.pending_mask = False
        state.pending_marker = b""
        state.pending_prefix = b""
        return pos + (32 if bytes_at(data, pos, b"\x00\x02", end) or bytes_at(data, pos, b"\x01\x02", end) else 31)

    transform_record = read_transform_record(data, pos, end, livery=False)
    if transform_record:
        size, transform, marker = transform_record
        state.pending_transform = transform
        state.pending_marker = state.pending_prefix + marker
        state.pending_prefix = b""
        return pos + size

    if livery:
        livery_transform = read_livery_transform(data, pos, end)
        if livery_transform:
            size, transform, marker = livery_transform
            state.pending_transform = transform
            state.pending_marker = marker
            state.pending_prefix = b""
            return pos + size

    byte = data[pos]
    if byte == 0x60:
        state.pending_flags |= 0x40
        state.pending_mask = True
        state.pending_prefix = b""
    elif byte in (0x01, 0x02, 0x03, 0x0F, 0xFF):
        state.pending_flags |= byte
        state.pending_prefix = b""
    else:
        state.pending_prefix = bytes([byte]) if byte else b""
    return pos + 1


def get_cgroup_layer_data(payload: bytes) -> tuple[bytes, int]:
    if len(payload) > 0x24 and payload[0x1D] in (0x20, 0x60):
        start = 0x24 + payload[0x20]
        if start < len(payload):
            return payload[start:], start
    if len(payload) > 69 and payload[37] == 0x02 and is_valid_shape_at(payload, 37, len(payload)):
        return payload[37:], 37
    return payload[38:], 38


def build_cgroup_tree(payload: bytes) -> tuple[GroupNode, int, list[str]]:
    warnings: list[str] = []
    root = GroupNode(source="root")
    transform = read_transform_payload(payload, 13, len(payload))
    if transform:
        root.transform = transform
    if len(payload) > 0x20 and payload[0x1D] in (0x20, 0x60):
        header_end = min(len(payload), 0x1D + 4 + payload[0x20] + 2)
        group = valid_counted_group_at(payload, 0x1D, header_end)
        if group:
            apply_group_record(root, group, "root")
            bitmap_start = 0x1D + 7
            root.child_bitmap = payload[bitmap_start : bitmap_start + payload[0x20]]
    layer_data, layer_start = get_cgroup_layer_data(payload)
    state = WalkState(stack=[root])
    pos = 0
    guard = 0
    initial = read_initial_child_transform(layer_data, pos, len(layer_data))
    if initial:
        pos, state.pending_transform, state.pending_marker = initial
    while pos < len(layer_data) and guard < len(layer_data) + 4096:
        guard += 1
        close_complete_stack(state.stack)
        next_pos = walk_step(layer_data, pos, len(layer_data), state)
        if next_pos <= pos:
            warnings.append(f"decoder made no progress at layer-data offset 0x{pos:x}")
            break
        pos = next_pos
    if pos < len(layer_data):
        warnings.append(f"decoder stopped before end: 0x{pos:x}/0x{len(layer_data):x}")
    return root, layer_start, warnings


def read_initial_child_transform(data: bytes, pos: int, end: int) -> tuple[int, Transform, bytes] | None:
    for candidate in range(pos, min(end, pos + 8)):
        record = read_transform_record(data, candidate, end, livery=False)
        if record:
            size, transform, marker = record
            if valid_counted_group_at(data, candidate + size, end):
                return candidate + size, transform, marker
    if pos + 16 <= end and valid_counted_group_at(data, pos + 16, end):
        transform = read_transform_payload(data, pos, end)
        if transform:
            return pos + 16, transform, b""
    return None


def compose_group_transform(parent: Transform, child: Transform) -> Transform:
    radians = math.radians(parent.rotation)
    c = math.cos(radians)
    s = math.sin(radians)
    x = parent.x + c * parent.sx * child.x - s * parent.sy * child.y
    y = parent.y + s * parent.sx * child.x + c * parent.sy * child.y
    return Transform(x=x, y=y, sx=child.sx * parent.sx, sy=child.sy * parent.sy, rotation=child.rotation + parent.rotation)


def affine(a: float, b: float, c: float, d: float, e: float, f: float) -> list[list[float]]:
    return [[a, b, c], [d, e, f], [0.0, 0.0, 1.0]]


def matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[sum(left[r][k] * right[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def group_matrix(transform: Transform) -> list[list[float]]:
    radians = math.radians(transform.rotation)
    c = math.cos(radians)
    s = math.sin(radians)
    return affine(c * transform.sx, -s * transform.sy, transform.x, s * transform.sx, c * transform.sy, transform.y)


def shape_matrix(shape: ShapeNode) -> list[list[float]]:
    radians = math.radians(shape.rotation)
    c = math.cos(radians)
    s = math.sin(radians)
    result = affine(1.0, 0.0, shape.x, 0.0, 1.0, shape.y)
    result = matmul(result, affine(c, -s, 0.0, s, c, 0.0))
    result = matmul(result, affine(1.0, shape.skew, 0.0, 0.0, 1.0, 0.0))
    result = matmul(result, affine(shape.sx, 0.0, 0.0, 0.0, shape.sy, 0.0))
    return result


def decompose_matrix(matrix: list[list[float]]) -> tuple[float, float, float, float, float, float]:
    x = matrix[0][2]
    y = matrix[1][2]
    a = matrix[0][0]
    b = matrix[0][1]
    c = matrix[1][0]
    d = matrix[1][1]
    sx_mag = math.hypot(a, c)
    if sx_mag < 1e-8:
        return x, y, 0.0, math.hypot(b, d), 0.0, 0.0
    if a * d - b * c < 0.0:
        sx = -sx_mag
        rotation = math.atan2(-c, -a)
    else:
        sx = sx_mag
        rotation = math.atan2(c, a)
    cos_r = math.cos(rotation)
    sin_r = math.sin(rotation)
    m01 = cos_r * b + sin_r * d
    m11 = -sin_r * b + cos_r * d
    sy = m11
    skew = m01 / m11 if abs(m11) > 1e-8 else 0.0
    return x, y, sx, sy, normalize_rotation(math.degrees(rotation)), skew


def flatten_tree(root: GroupNode, layer_start: int = 0, section: str | None = None) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []

    def walk(node: GroupNode, parent_matrix: list[list[float]], inherited_mask: bool, inherited_section: str | None) -> None:
        current_section = node.section or inherited_section
        current_mask = inherited_mask or node.mask
        node_matrix = matmul(parent_matrix, group_matrix(node.transform))
        for item in node.items:
            if isinstance(item, ShapeNode):
                effective = matmul(node_matrix, shape_matrix(item))
                x, y, sx, sy, rotation, skew = decompose_matrix(effective)
                is_mask = current_mask or item.mask
                if has_color_data(item.color_rgba):
                    is_mask = False
                layers.append(
                    {
                        "shape_id": item.shape_id,
                        "data": [x, y, sx, sy, rotation, skew, 1 if is_mask else 0],
                        "color_rgba": list(item.color_rgba),
                        "mask": bool(is_mask),
                        "flags": item.flags,
                        "marker_hex": item.marker.hex(),
                        "source_offset": layer_start + item.offset,
                        "section": item.section or current_section or section,
                    }
                )
            else:
                walk(item, node_matrix, current_mask, current_section)

    walk(root, affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0), False, section)
    return layers


def cgroup_to_layers(payload: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root, layer_start, warnings = build_cgroup_tree(payload)
    layers = flatten_tree(root, layer_start=layer_start)
    return layers, {
        "source_kind": "cgroup",
        "payload_size": len(payload),
        "layer_data_start": layer_start,
        "root_expected_children": root.expected_children,
        "decoded_layers": len(layers),
        "warnings": warnings,
    }


def extract_livery_payload(raw: bytes) -> tuple[bytes, list[int], dict[str, Any]]:
    gyvl = raw.find(b"gyvl")
    if gyvl < 0:
        raise DecodeError("C_livery has no embedded gyvl chunk")
    body_start = gyvl + 0x15
    body_end = raw.find(b"yrvl", gyvl + 4)
    if body_end < 0:
        body_end = len(raw)
    if body_start > body_end:
        raise DecodeError("C_livery embedded gyvl body is truncated")
    counts = [0] * len(LIVERY_SECTION_NAMES)
    if body_end + 4 + 44 <= len(raw) and raw[body_end : body_end + 4] == b"yrvl":
        counts = [read_u32(raw, body_end + 4 + i * 4) for i in range(len(LIVERY_SECTION_NAMES))]
    return raw[body_start:body_end], counts, {"gyvl_offset": gyvl, "body_start": body_start, "body_end": body_end}


def build_livery_sections(body: bytes, counts: list[int]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    layers: list[dict[str, Any]] = []
    pos = 0
    end = len(body)
    for slot, name in enumerate(LIVERY_SECTION_NAMES):
        target = counts[slot] if slot < len(counts) else 0
        section_start = pos
        if target <= 0:
            pos = min(end, pos + LIVERY_EMPTY_SLOT_SIZE)
            continue
        section_root = GroupNode(source="livery_section", offset=pos, section=name)
        holder = GroupNode(source="livery_holder")
        holder.items.append(section_root)
        state = WalkState(stack=[holder, section_root])
        guard = 0
        while len(flatten_tree(section_root, section=name)) < target and pos < end and guard < end + 4096:
            guard += 1
            close_complete_stack(state.stack)
            if len(state.stack) < 2:
                warnings.append(f"{name}: parser stack closed before reaching target {target}")
                break
            if state.stack[-1] is section_root and not state.pending_transform:
                markerless = valid_markerless_group_at(body, pos, end, allow_count_one=True, livery=True)
                if markerless:
                    pos = push_markerless_group(body, pos, end, markerless, state, livery=True)
                    continue
            next_pos = walk_step(body, pos, end, state, livery=True)
            if next_pos <= pos:
                warnings.append(f"{name}: decoder made no progress at body offset 0x{pos:x}")
                break
            pos = next_pos
        decoded = flatten_tree(section_root, layer_start=0, section=name)
        if len(decoded) != target:
            warnings.append(f"{name}: decoded {len(decoded)} layer(s), stats target is {target}")
        for layer in decoded:
            layer["section_start"] = section_start
            layers.append(layer)
        pos = min(end, pos + LIVERY_POPULATED_REMNANT_SIZE)
    return layers, warnings


def clivery_to_layers(payload: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    body, counts, meta = extract_livery_payload(payload)
    layers, warnings = build_livery_sections(body, counts)
    return layers, {
        "source_kind": "clivery",
        "payload_size": len(payload),
        "section_counts": dict(zip(LIVERY_SECTION_NAMES, counts)),
        "decoded_layers": len(layers),
        "warnings": warnings,
        **meta,
    }


def _load_word_lookup() -> dict[int, list[tuple[str, int, str | None]]]:
    root = Path(__file__).resolve().parents[2]
    words_path = root / "tools" / "fabric-editor" / "shape-words.json"
    names_path = root / "tools" / "fabric-editor" / "shape-names.json"
    if not words_path.exists():
        return {}
    words = json.loads(words_path.read_text(encoding="utf-8")).get("families", {})
    names = {}
    if names_path.exists():
        names = json.loads(names_path.read_text(encoding="utf-8")).get("families", {})
    lookup: dict[int, list[tuple[str, int, str | None]]] = {}
    for family, entries in words.items():
        for index_text, word in entries.items():
            try:
                index = int(index_text)
                word = int(word)
            except (TypeError, ValueError):
                continue
            name = names.get(family, {}).get(index_text) if isinstance(names.get(family, {}), dict) else None
            lookup.setdefault(word, []).append((family, index, name))
    return lookup


def layers_to_kfps_json_layers(layers: Iterable[dict[str, Any]], game: str | None = "fh6") -> tuple[list[dict[str, Any]], list[str]]:
    lookup = _load_word_lookup()
    game_key = normalize_game_key(game)
    warnings: list[str] = []
    output: list[dict[str, Any]] = []
    for index, layer in enumerate(layers, 1):
        raw_word = int(layer["shape_id"]) & 0xFFFF
        word = raw_word
        normalized = normalize_game_shape_word(raw_word, game_key)
        if normalized:
            word = int(normalized["canonical_word"]) & 0xFFFF
        shape: dict[str, Any] = {
            "type": TYPE_CODE_BASE + word,
            "type_word": word,
            "type_word_hex": f"0x{word:04x}",
            "data": [float(v) if isinstance(v, (int, float)) else v for v in layer["data"]],
            "color": [int(v) for v in layer["color_rgba"]],
            "mask": bool(layer.get("mask")),
            "score": 0,
            "source_format": "forza_file_export",
            "source_shape_index": index,
            "source_offset": layer.get("source_offset"),
            "source_marker": layer.get("marker_hex"),
            "source_game": game_key,
        }
        if normalized:
            shape["source_raw_type"] = int(normalized["raw_type"])
            shape["source_raw_type_word"] = raw_word
            shape["source_raw_type_word_hex"] = f"0x{raw_word:04x}"
            shape["resource_family"] = normalized["resource_family"]
            shape["resource_index"] = int(normalized["resource_index"])
            shape["resource_normalized_for_game"] = game_key
        if layer.get("section"):
            shape["source_section"] = layer["section"]
        matches = lookup.get(word, [])
        if normalized:
            for family, slot, name in matches:
                if family == shape.get("resource_family") and int(slot) == int(shape.get("resource_index") or 0):
                    if name:
                        shape["display_name"] = name
                    break
        elif len(matches) == 1:
            family, slot, name = matches[0]
            shape["resource_family"] = family
            shape["resource_index"] = slot
            if name:
                shape["display_name"] = name
        elif len(matches) > 1:
            warnings.append(f"shape word {word} has {len(matches)} resource matches; leaving resource identity unset")
            shape["shape_word_ambiguous_resources"] = [
                {"family": family, "index": slot, "name": name} for family, slot, name in matches[:8]
            ]
        output.append(shape)
    return output, warnings


def decode_forza_source(path: Path | str, allow_locked: bool = False, game: str | None = "fh6") -> DecodedSource:
    game_key = normalize_game_key(game)
    source_path, kind = resolve_forza_source(path)
    payload = unwrap_forza_container(source_path)
    privacy_warnings = enforce_privacy(source_path, kind, payload, allow_locked=allow_locked)
    if kind == "cgroup":
        layers, report = cgroup_to_layers(payload)
    else:
        layers, report = clivery_to_layers(payload)
    json_layers, identity_warnings = layers_to_kfps_json_layers(layers, game=game_key)
    report["privacy_warnings"] = privacy_warnings
    report["identity_warnings"] = identity_warnings
    report["source_path"] = str(source_path)
    report["target_game"] = game_key
    return DecodedSource(
        source_path=str(source_path),
        source_kind=kind,
        layers=json_layers,
        report=report,
    )
