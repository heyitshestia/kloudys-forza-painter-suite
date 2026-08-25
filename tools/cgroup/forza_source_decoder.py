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
    from .shape_identity import (
        TYPE_CODE_BASE,
        VINYL_TYPE_BASES,
        normalize_game_key,
        normalize_game_shape_word,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from shape_identity import (
        TYPE_CODE_BASE,
        VINYL_TYPE_BASES,
        normalize_game_key,
        normalize_game_shape_word,
    )


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
    mask_authoritative: bool = False
    section: str | None = None
    is_raster_logo: bool = False
    raster_id: int | None = None


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
    skipped_children: int = 0
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
    inline_for_first_child: bool = False
    child_bitmap: bytes = b""
    control_bytes: bytes = b""


@dataclass
class WalkState:
    stack: list[GroupNode]
    pending_transform: Transform | None = None
    pending_marker: bytes = b""
    pending_prefix: bytes = b""
    pending_flags: int = 0
    pending_mask: bool = False
    decoded_shapes: int = 0
    fm8_legacy_shapes: int = 0


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


def probe_forza_source_kind(
    path: Path | str,
    *,
    max_payload_prefix: int = 0x200,
    max_compressed_probe: int = 1024 * 1024,
) -> str | None:
    """Identify a Forza artifact without trusting its filename or expanding it fully."""

    source = Path(path)
    if not source.is_file():
        return None
    try:
        file_size = source.stat().st_size
        with source.open("rb") as handle:
            header = handle.read(8)
            if header.startswith(b"gyvl"):
                return "cgroup"
            if header.startswith(b"vlrc"):
                return "clivery"
            if len(header) < 8:
                return None

            compressed_len, payload_len = struct.unpack("<II", header)
            if compressed_len <= 0 or payload_len < 4 or compressed_len > file_size - 8:
                return None

            decompressor = zlib.decompressobj()
            payload_prefix = bytearray()
            remaining = min(compressed_len, max_compressed_probe)
            while remaining > 0 and len(payload_prefix) < max_payload_prefix:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                payload_prefix.extend(
                    decompressor.decompress(chunk, max_payload_prefix - len(payload_prefix))
                )
                if decompressor.eof:
                    break
    except (OSError, struct.error, zlib.error, ValueError):
        return None

    prefix = bytes(payload_prefix)
    if prefix.startswith(b"gyvl"):
        return "cgroup"
    if prefix.startswith(b"vlrc") or b"gyvl" in prefix:
        return "clivery"
    return None


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
        message = "privacy guard: this vinyl group belongs to another player"
        if not allow_locked:
            raise DecodeError(message)
        warnings.append(message)
    if kind == "clivery":
        privacy = inspect_clivery_privacy(payload)
        messages = []
        if not privacy["source_owned"]:
            messages.append("privacy guard: this full livery belongs to another player")
        if privacy["foreign_group_count"]:
            messages.append("privacy guard: this full livery contains vinyl groups created by another player")
        if messages and not allow_locked:
            raise DecodeError(messages[0])
        warnings.extend(messages)
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


def is_extended_livery_transform_at(data: bytes, pos: int, end: int) -> bool:
    return (
        pos >= 0
        and pos + 8 <= end
        and bytes_at(data, pos, b"\x00\x02\x00\x01\x00\x00\x00", end)
        and data[pos + 7] in (0x01, 0x03)
    )


def canonical_shape_id(shape_id: int) -> int:
    """Normalize the one FH wire alias used by the shared shape registry."""

    value = int(shape_id) & 0xFFFF
    return 0x07D1 if value == 0x07D0 else value


def is_known_shape_id(shape_id: int) -> bool:
    """Return whether a wire word resolves to one of KFPS's native shape assets."""

    value = canonical_shape_id(shape_id)
    for base in VINYL_TYPE_BASES.values():
        start = int(base) & 0xFFFF
        if start <= value < start + 40:
            return True
    return False


def is_valid_shape_at(data: bytes, pos: int, end: int) -> bool:
    if pos < 0 or pos >= end or pos >= len(data):
        return False
    if is_extended_livery_transform_at(data, pos, end):
        return False
    if bytes_at(data, pos, b"\x00\x02", end) or bytes_at(data, pos, b"\x01\x02", end):
        if pos + 32 > end:
            return False
        shape_id = read_u16(data, pos + 2)
        offset = 0
    elif data[pos] == 0x02:
        if pos + 31 > end:
            return False
        shape_id = read_u16(data, pos + 1)
        offset = -1
    else:
        return False
    rotation = read_f32(data, pos + 4 + offset)
    x = read_f32(data, pos + 8 + offset)
    y = read_f32(data, pos + 12 + offset)
    sx = read_f32(data, pos + 16 + offset)
    sy = read_f32(data, pos + 20 + offset)
    skew = read_f32(data, pos + 24 + offset)
    return (
        is_known_shape_id(shape_id)
        and math.isfinite(rotation)
        and abs(rotation) <= 10000.0
        and math.isfinite(x)
        and math.isfinite(y)
        and abs(x) < 50000.0
        and abs(y) < 50000.0
        and math.isfinite(sx)
        and math.isfinite(sy)
        and 1e-6 < abs(sx) < 200.0
        and 1e-6 < abs(sy) < 200.0
        and math.isfinite(skew)
        and abs(skew) < 200.0
    )


def is_fm8_legacy_shape_at(data: bytes, pos: int, end: int) -> bool:
    """Recognize the older shape record retained by FM8 legacy imports."""

    if (
        pos < 0
        or pos + 31 > end
        or pos + 31 > len(data)
        or data[pos] != 0x01
    ):
        return False
    shape_id = read_u16(data, pos + 1)
    rotation = read_f32(data, pos + 3)
    x = read_f32(data, pos + 7)
    y = read_f32(data, pos + 11)
    sx = read_f32(data, pos + 15)
    sy = read_f32(data, pos + 19)
    skew = read_f32(data, pos + 23)
    return (
        is_known_shape_id(shape_id)
        and math.isfinite(rotation)
        and abs(rotation) <= 10000.0
        and math.isfinite(x)
        and math.isfinite(y)
        and abs(x) < 50000.0
        and abs(y) < 50000.0
        and math.isfinite(sx)
        and math.isfinite(sy)
        and 1e-6 < abs(sx) < 200.0
        and 1e-6 < abs(sy) < 200.0
        and math.isfinite(skew)
        and abs(skew) < 200.0
    )


def decode_fm8_legacy_shape_at(
    data: bytes, pos: int, is_mask: bool = False, flags: int = 0
) -> ShapeNode:
    b, g, r, a = data[pos + 27 : pos + 31]
    return ShapeNode(
        shape_id=read_u16(data, pos + 1),
        rotation=read_f32(data, pos + 3),
        x=read_f32(data, pos + 7),
        y=read_f32(data, pos + 11),
        sx=read_f32(data, pos + 15),
        sy=read_f32(data, pos + 19),
        skew=read_f32(data, pos + 23),
        color_rgba=(r, g, b, a),
        offset=pos,
        marker=data[pos : pos + 1],
        flags=flags,
        mask=is_mask,
        mask_authoritative=False,
    )


def is_unsupported_shape_record_at(data: bytes, pos: int, end: int) -> bool:
    """Recognize an unknown framed record that still occupies a group child slot."""

    if (
        pos < 0
        or pos + 32 > end
        or pos + 32 > len(data)
        or data[pos] not in (0x00, 0x01)
        or data[pos + 1] != 0x02
    ):
        return False
    shape_id = canonical_shape_id(read_u16(data, pos + 2))
    if shape_id == 0 or is_known_shape_id(shape_id) or data[pos + 31] != 0xFF:
        return False
    rotation = read_f32(data, pos + 4)
    x = read_f32(data, pos + 8)
    y = read_f32(data, pos + 12)
    sx = read_f32(data, pos + 16)
    sy = read_f32(data, pos + 20)
    skew = read_f32(data, pos + 24)
    return (
        math.isfinite(rotation)
        and abs(rotation) <= 10000.0
        and math.isfinite(x)
        and math.isfinite(y)
        and abs(x) < 50000.0
        and abs(y) < 50000.0
        and math.isfinite(sx)
        and math.isfinite(sy)
        and 1e-6 < abs(sx) < 200.0
        and 1e-6 < abs(sy) < 5000.0
        and math.isfinite(skew)
        and abs(skew) < 200.0
    )


def livery_logo_record_size_at(data: bytes, pos: int, end: int) -> int:
    """Return the size of one built-in raster decal placement, or zero."""

    framed = bytes_at(data, pos, b"\x00\x02", end) or bytes_at(
        data, pos, b"\x01\x02", end
    )
    size = 32 if framed else 31
    field_offset = 0 if framed else -1
    if (
        pos < 0
        or pos + size > end
        or pos + size > len(data)
        or (not framed and data[pos] != 0x02)
    ):
        return 0
    raw_shape_id = read_u16(data, pos + 2 + field_offset)
    if not (raw_shape_id & 0x8000) or (raw_shape_id & 0x7FFF) == 0:
        return 0
    rotation = read_f32(data, pos + 4 + field_offset)
    x = read_f32(data, pos + 8 + field_offset)
    y = read_f32(data, pos + 12 + field_offset)
    sx = read_f32(data, pos + 16 + field_offset)
    sy = read_f32(data, pos + 20 + field_offset)
    skew = read_f32(data, pos + 24 + field_offset)
    valid = (
        math.isfinite(rotation)
        and abs(rotation) <= 10000.0
        and math.isfinite(x)
        and math.isfinite(y)
        and abs(x) < 50000.0
        and abs(y) < 50000.0
        and math.isfinite(sx)
        and math.isfinite(sy)
        and 1e-6 < abs(sx) < 200.0
        and 1e-6 < abs(sy) < 200.0
        and math.isfinite(skew)
        and abs(skew) < 200.0
    )
    return size if valid else 0


def is_livery_logo_at(data: bytes, pos: int, end: int) -> bool:
    """Recognize one built-in raster decal placement in a C_livery stream."""

    return livery_logo_record_size_at(data, pos, end) > 0


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
        mask_authoritative=False,
    )


def decode_livery_logo_at(data: bytes, pos: int, is_mask: bool = False, flags: int = 0) -> ShapeNode:
    shape = decode_shape_at(data, pos, is_mask=is_mask, flags=flags)
    shape.is_raster_logo = True
    shape.raster_id = shape.shape_id & 0x7FFF
    return shape


def transform_markers_at(
    data: bytes,
    pos: int,
    end: int,
    livery: bool = False,
    game: str | None = None,
) -> list[bytes]:
    if pos >= end:
        return []
    markers: list[bytes] = []
    term = 0x01 if livery else 0x03
    game_key = normalize_game_key(game)
    if not livery and game_key == "fm8" and data[pos] == 0x02:
        markers.append(b"\x02")
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


def read_transform_record(
    data: bytes,
    pos: int,
    end: int,
    livery: bool = False,
    game: str | None = None,
) -> tuple[int, Transform, bytes] | None:
    for marker in transform_markers_at(data, pos, end, livery=livery, game=game):
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


LIVERY_TRANSFORM_TRAILER_SIZE = 9
LIVERY_TRANSFORM_MIRROR_TRAILER_SIZE = 13


def livery_transform_trailer(
    data: bytes, pos: int, end: int
) -> tuple[int, float | None] | None:
    if (
        pos < 0
        or pos + LIVERY_TRANSFORM_TRAILER_SIZE > end
        or data[pos] not in (0x21, 0x31)
        or data[pos + 7] != 0x09
        or data[pos + 8] != 0x00
    ):
        return None
    if data[pos] == 0x21:
        return LIVERY_TRANSFORM_TRAILER_SIZE, None
    if pos + LIVERY_TRANSFORM_MIRROR_TRAILER_SIZE > end:
        return None
    sy = read_f32(data, pos + LIVERY_TRANSFORM_TRAILER_SIZE)
    if not (0.0001 <= abs(sy) <= 5000.0):
        return None
    return LIVERY_TRANSFORM_MIRROR_TRAILER_SIZE, sy


def parser_livery_transform_trailer(
    data: bytes, pos: int, end: int
) -> tuple[int, float | None] | None:
    """Return the transform trailer used by the FH6 livery tree grammar.

    The privacy scanner deliberately recognizes the broader 0x31 protected
    wrapper above. In the artwork grammar, however, only the fixed nine-byte
    0x21 trailer belongs to a transform. Treating 0x31 as an artwork trailer
    turns section-leading control bytes into a false group header and applies
    a frame that the game/FLS scene importer does not use.
    """

    if (
        pos < 0
        or pos + LIVERY_TRANSFORM_TRAILER_SIZE > end
        or data[pos] != 0x21
        or data[pos + 7] != 0x09
        or data[pos + 8] != 0x00
    ):
        return None
    return LIVERY_TRANSFORM_TRAILER_SIZE, None


def livery_transform_marker_sizes(data: bytes, pos: int, end: int) -> list[int]:
    if pos < 0 or pos >= end:
        return []
    sizes: list[int] = [8] if is_extended_livery_transform_at(data, pos, end) else []
    if data[pos] == 0x00:
        cursor = pos + 1
        while cursor < end and data[cursor] == 0x01:
            cursor += 1
        sizes.extend(range(cursor - pos, 1, -1))
    sizes.append(1)
    return sizes


def livery_transform_trailer_at(data: bytes, pos: int, end: int) -> bool:
    return livery_transform_trailer(data, pos, end) is not None


def _livery_group_after_transform(
    data: bytes, pos: int, end: int
) -> tuple[GroupInfo, int, int, float | None] | None:
    group = valid_counted_group_at(data, pos, end, livery=True) or valid_markerless_group_at(
        data, pos, end, True, True
    )
    if group:
        return group, pos, 0, None
    if pos + 1 < end and not is_valid_shape_at(data, pos, end) and not is_livery_logo_at(data, pos, end):
        group = valid_counted_group_at(
            data, pos + 1, end, livery=True
        ) or valid_markerless_group_at(data, pos + 1, end, True, True)
        if group:
            return group, pos + 1, 0, None
    trailer = parser_livery_transform_trailer(data, pos, end)
    if trailer:
        trailer_size, trailing_sy = trailer
        group_pos = pos + trailer_size
        group = valid_counted_group_at(
            data, group_pos, end, livery=True
        ) or valid_markerless_group_at(data, group_pos, end, True, True)
        if group:
            return group, group_pos, trailer_size, trailing_sy
    return None


def group_at_or_after_control_byte(data: bytes, pos: int, end: int, livery: bool) -> bool:
    if valid_counted_group_at(data, pos, end, livery) or valid_markerless_group_at(
        data, pos, end, False, livery
    ):
        return True
    return bool(
        livery
        and pos + 1 < end
        and not is_valid_shape_at(data, pos, end)
        and not is_livery_logo_at(data, pos, end)
        and (
            valid_counted_group_at(data, pos + 1, end, True)
            or valid_markerless_group_at(data, pos + 1, end, False, True)
        )
    )


def read_livery_transform(
    data: bytes,
    pos: int,
    end: int,
    *,
    invert_odd_rotation: bool = True,
) -> tuple[int, Transform, bytes] | None:
    if pos >= end or (
        data[pos] != 0x00
        and (is_valid_shape_at(data, pos + 1, end) or is_livery_logo_at(data, pos + 1, end))
    ):
        return None
    for marker_size in livery_transform_marker_sizes(data, pos, end):
        transform = read_transform_payload(data, pos + marker_size, end)
        if not transform:
            continue
        size = marker_size + 16
        sy_pos = pos + size
        if sy_pos + 5 <= end and (data[sy_pos] & ~0x40) == 0x30:
            sy = read_f32(data, sy_pos + 1)
            if 0.0001 <= abs(sy) <= 5000.0:
                transform.sy = sy
                size += 5
        successor = _livery_group_after_transform(data, pos + size, end)
        if successor is None:
            continue
        group, _, trailer_size, trailing_sy = successor
        if trailing_sy is not None:
            transform.sy = trailing_sy
        marker = data[pos : pos + marker_size]
        mirrored = transform.sx * transform.sy < 0.0
        scaled_first_child = bool(
            group.inline_transform
            and group.inline_for_first_child
            and (
                abs(abs(group.inline_transform.sx) - 1.0) > 1e-6
                or abs(abs(group.inline_transform.sy) - 1.0) > 1e-6
            )
        )
        if (
            invert_odd_rotation
            and marker == b"\x01"
            and not (group.flags & 0x40)
            and not mirrored
            and scaled_first_child
        ):
            transform.rotation = -transform.rotation
        return size + trailer_size, transform, marker
    return None


def _read_inline_transform(data: bytes, extra: int, end: int, livery: bool) -> tuple[int, Transform, bytes] | None:
    # A framed livery shape starts with the same zero byte accepted by the
    # transform marker grammar. Child records win at an established group
    # boundary; otherwise the shape payload can be swallowed as a 17-byte
    # inline transform and the section drifts into the following slot.
    if livery and (is_valid_shape_at(data, extra, end) or is_livery_logo_at(data, extra, end)):
        return None
    markers = transform_markers_at(data, extra, end, livery=livery)
    for marker in markers:
        if livery and marker[-1] == 0x01 and (
            is_valid_shape_at(data, extra + 1, end) or is_livery_logo_at(data, extra + 1, end)
        ):
            continue
        transform = read_transform_payload(data, extra + len(marker), end)
        if not transform:
            continue
        if livery and (abs(transform.x) >= 50000.0 or abs(transform.y) >= 50000.0):
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


def _raw_livery_counted_group_at(data: bytes, pos: int, end: int) -> bool:
    if pos < 0 or pos + 7 > end or data[pos] not in (0x20, 0x60):
        return False
    count = read_u16(data, pos + 1)
    child_blocks = (count + 7) // 8
    return (
        count > 0
        and read_u16(data, pos + 3) == child_blocks
        and pos + 7 + child_blocks <= end
    )


def _raw_livery_markerless_group_at(data: bytes, pos: int, end: int) -> bool:
    if pos < 0 or pos + 4 > end:
        return False
    count = read_u16(data, pos)
    child_blocks = (count + 7) // 8
    return (
        count > 0
        and read_u16(data, pos + 2) == child_blocks
        and pos + 6 + child_blocks <= end
    )


def _livery_markerless_header_fields_match(data: bytes, pos: int, end: int) -> bool:
    if pos < 0 or pos + 4 > end:
        return False
    count = read_u16(data, pos)
    return count >= 2 and read_u16(data, pos + 2) == (count + 7) // 8


def _is_shifted_livery_markerless_header(data: bytes, pos: int, end: int, count: int) -> bool:
    return (
        count >= 256
        and count % 256 == 0
        and _livery_markerless_header_fields_match(data, pos + 1, end)
    )


def _livery_child_boundary_score(data: bytes, pos: int, end: int) -> int:
    if is_valid_shape_at(data, pos, end) or is_livery_logo_at(data, pos, end):
        return 8
    if _raw_livery_counted_group_at(data, pos, end):
        return 7
    if _raw_livery_markerless_group_at(data, pos, end):
        return 6
    trailer = livery_transform_trailer(data, pos, end)
    if trailer:
        return max(0, _livery_child_boundary_score(data, pos + trailer[0], end) - 1)
    if pos + 1 < end and data[pos] in (0x01, 0x02, 0x03, 0x0F, 0xFF):
        return max(0, _livery_child_boundary_score(data, pos + 1, end) - 2)
    return 0


def _livery_markerless_candidate(
    data: bytes,
    pos: int,
    end: int,
    min_count: int,
) -> tuple[GroupInfo, int] | None:
    if pos + 4 > end:
        return None
    count = read_u16(data, pos)
    child_blocks = (count + 7) // 8
    if (
        count < min_count
        or child_blocks <= 0
        or read_u16(data, pos + 2) != child_blocks
        or _is_shifted_livery_markerless_header(data, pos, end, count)
    ):
        return None
    control_start = pos + 4
    bitmap_start = control_start + 2
    base_size = 4 + 2 + child_blocks
    if pos + base_size > end:
        return None
    info = GroupInfo(
        count=count,
        child_blocks=child_blocks,
        size=base_size,
        marker=b"",
        child_bitmap=data[bitmap_start : bitmap_start + child_blocks],
        control_bytes=data[control_start:bitmap_start],
    )
    inline = _read_inline_transform(data, pos + base_size, end, True)
    if inline:
        size, transform, marker = inline
        info.size += size
        info.inline_transform = transform
        info.inline_for_first_child = group_at_or_after_control_byte(data, pos + info.size, end, True)
        info.marker = marker
    elif info.child_bitmap and (info.child_bitmap[0] & 0x01):
        extra = pos + base_size
        transform = read_transform_payload(data, extra, end)
        if transform:
            transform_size = 16
            child = extra + transform_size
            if child + 5 <= end and (data[child] & ~0x40) == 0x30:
                sy = read_f32(data, child + 1)
                if 0.0001 <= abs(sy) <= 5000.0:
                    transform.sy = sy
                    transform_size += 5
                    child += 5
            trailer = parser_livery_transform_trailer(data, child, end)
            if trailer:
                trailer_size, trailing_sy = trailer
                transform_size += trailer_size
                child += trailer_size
                if trailing_sy is not None:
                    transform.sy = trailing_sy
            if group_at_or_after_control_byte(data, child, end, True):
                info.inline_transform = transform
                info.inline_for_first_child = True
                info.size += transform_size
    return info, _livery_child_boundary_score(data, pos + info.size, end)


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
    if livery:
        min_count = 1 if allow_count_one else 2
        candidate = _livery_markerless_candidate(data, pos, end, min_count)
        if candidate is None:
            return None
        info, _ = candidate
        extra = pos + info.size
        if info.inline_transform:
            return info
        child_here = (
            is_valid_shape_at(data, extra, end)
            or is_livery_logo_at(data, extra, end)
            or valid_counted_group_at(data, extra, end, True)
            or valid_markerless_group_at(data, extra, end, False, True)
            or livery_transform_then_child_at(data, extra, end)
        )
        if child_here:
            return info
        if extra + 1 < end and (
            is_valid_shape_at(data, extra + 1, end)
            or is_livery_logo_at(data, extra + 1, end)
            or valid_counted_group_at(data, extra + 1, end, True)
            or valid_markerless_group_at(data, extra + 1, end, False, True)
            or livery_transform_then_child_at(data, extra + 1, end)
        ):
            info.flags |= data[extra] & ~0x40
            info.size += 1
            return info
        return None

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
    child_here = is_valid_shape_at(data, extra, end) or (
        livery and is_livery_logo_at(data, extra, end)
    ) or valid_counted_group_at(data, extra, end, livery) or (
        livery and livery_transform_then_child_at(data, extra, end)
    )
    if child_here:
        return info
    if extra + 1 < end and (
        is_valid_shape_at(data, extra + 1, end)
        or (livery and is_livery_logo_at(data, extra + 1, end))
        or valid_counted_group_at(data, extra + 1, end, livery)
        or (livery and livery_transform_then_child_at(data, extra + 1, end))
    ):
        info.flags |= data[extra] & ~0x40
        info.size += 1
        return info
    return None


def valid_counted_group_at(data: bytes, pos: int, end: int, livery: bool = False) -> GroupInfo | None:
    if livery:
        if pos + 5 > end or data[pos] not in (0x20, 0x60):
            return None
        count = read_u16(data, pos + 1)
        stored_child_blocks = read_u16(data, pos + 3)
        child_blocks = (count + 7) // 8
        if count <= 0 or stored_child_blocks != child_blocks:
            return None
        control_start = pos + 5
        bitmap_start = control_start + 2
        base_size = 5 + 2 + child_blocks
        if pos + base_size > end:
            return None
        info = GroupInfo(
            count=count,
            child_blocks=child_blocks,
            size=base_size,
            flags=0x40 if data[pos] == 0x60 else 0,
            marker=data[pos : pos + 1],
            child_bitmap=data[bitmap_start : bitmap_start + child_blocks],
            control_bytes=data[control_start:bitmap_start],
        )
        extra = pos + base_size
        inline = _read_inline_transform(data, extra, end, True)
        if inline:
            size, transform, marker = inline
            info.size += size
            info.inline_transform = transform
            info.inline_for_first_child = group_at_or_after_control_byte(data, pos + info.size, end, True)
            info.marker = marker
            return info
        if extra < end and data[extra] in (0x02, 0x03, 0xFF):
            info.flags |= data[extra] & ~0x40
            info.size += 1
        elif extra + 1 < end and data[extra] == 0x01 and not is_valid_shape_at(data, extra, end):
            if is_valid_shape_at(data, extra + 1, end) or is_livery_logo_at(
                data, extra + 1, end
            ) or valid_counted_group_at(
                data, extra + 1, end, True
            ):
                info.flags |= 0x01
                info.size += 1
        return info

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
        if is_valid_shape_at(data, extra + 1, end) or is_livery_logo_at(
            data, extra + 1, end
        ) or valid_counted_group_at(data, extra + 1, end, True):
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


def apply_group_record(
    node: GroupNode,
    info: GroupInfo,
    source: str,
    pending_flags: int = 0,
    pending_mask: bool = False,
    apply_inline_transform: bool = True,
) -> None:
    node.expected_children = info.count
    node.flags = info.flags | pending_flags
    node.mask = bool(node.flags & 0x40) or pending_mask
    node.source = source
    node.marker = info.marker
    if apply_inline_transform and info.inline_transform:
        node.transform = info.inline_transform


def group_complete(group: GroupNode) -> bool:
    return (
        group.expected_children is not None
        and len(group.items) + group.skipped_children >= group.expected_children
    )


def next_child_is_group(group: GroupNode) -> bool | None:
    if group.expected_children is None:
        return None
    child_index = len(group.items) + group.skipped_children
    if child_index >= group.expected_children:
        return None
    byte_index = child_index // 8
    if byte_index >= len(group.child_bitmap):
        return None
    return bool(group.child_bitmap[byte_index] & (1 << (child_index % 8)))


def close_complete_stack(stack: list[GroupNode]) -> None:
    while len(stack) > 1 and group_complete(stack[-1]):
        stack.pop()


def mark_previous_direct_shape_as_mask(state: WalkState, authoritative: bool = False) -> bool:
    if not state.stack or not state.stack[-1].items:
        return False
    previous = state.stack[-1].items[-1]
    if not isinstance(previous, ShapeNode):
        return False
    previous.mask = True
    previous.mask_authoritative = previous.mask_authoritative or authoritative
    previous.flags |= 0x40
    return True


def mark_previous_terminal_shape_as_mask(state: WalkState, authoritative: bool = False) -> bool:
    if not state.stack or not state.stack[-1].items:
        return False
    previous: ShapeNode | GroupNode = state.stack[-1].items[-1]
    while isinstance(previous, GroupNode):
        if not previous.items:
            return False
        previous = previous.items[-1]
    previous.mask = True
    previous.mask_authoritative = previous.mask_authoritative or authoritative
    previous.flags |= 0x40
    return True


def consume_root_close_suffix(data: bytes, pos: int, state: WalkState) -> bool:
    """Consume an exact FH root close sequence and preserve its final mask bit."""
    if not state.stack or not group_complete(state.stack[0]):
        return False
    suffix = data[pos:]
    if len(suffix) < 2 or suffix[0] not in (0x00, 0x01) or any(byte != 0x01 for byte in suffix[1:]):
        return False
    if suffix[0] & 0x01:
        mark_previous_terminal_shape_as_mask(state, authoritative=True)
    return True


def push_markerless_group(data: bytes, pos: int, end: int, info: GroupInfo, state: WalkState, livery: bool = False) -> int:
    inline_for_first = bool(
        info.inline_transform
        and (
            info.inline_for_first_child
            if livery
            else inline_transform_for_first_child(info.marker)
        )
    )
    node = GroupNode(offset=pos)
    apply_group_record(
        node,
        info,
        "markerless",
        state.pending_flags,
        state.pending_mask,
        apply_inline_transform=not inline_for_first,
    )
    node.child_bitmap = info.child_bitmap
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


def walk_step(
    data: bytes,
    pos: int,
    end: int,
    state: WalkState,
    livery: bool = False,
    game: str | None = None,
    livery_invert_odd_rotation: bool = True,
) -> int:
    game_key = normalize_game_key(game)
    expected_group = next_child_is_group(state.stack[-1])
    may_decode_group = expected_group is None or expected_group
    may_decode_shape = expected_group is None or not expected_group

    markerless = (
        valid_markerless_group_at(data, pos, end, False, livery)
        if state.pending_transform and may_decode_group
        else None
    )
    if markerless:
        return push_markerless_group(data, pos, end, markerless, state, livery)

    counted = valid_counted_group_at(data, pos, end, livery) if may_decode_group else None
    if counted:
        inline_for_first = bool(
            counted.inline_transform
            and (
                counted.inline_for_first_child
                if livery
                else inline_transform_for_first_child(counted.marker)
            )
        )
        node = GroupNode(offset=pos, child_bitmap=counted.child_bitmap)
        apply_group_record(
            node,
            counted,
            "counted",
            state.pending_flags,
            state.pending_mask,
            apply_inline_transform=not inline_for_first,
        )
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

    # The eight-byte livery transform lead is byte-identical to a zero control
    # byte followed by a two-child markerless group header. The parent bitmap
    # resolves that ambiguity: when this direct child must be a group, consume
    # the control byte first and let the next step decode the group. Treating
    # the header as a transform discards the nested subtree and shifts every
    # later section boundary.
    group_follows_control = bool(
        livery
        and expected_group is True
        and pos + 1 < end
        and not is_valid_shape_at(data, pos, end)
        and not is_livery_logo_at(data, pos, end)
        and (
            valid_counted_group_at(data, pos + 1, end, True)
            or valid_markerless_group_at(data, pos + 1, end, False, True)
        )
    )

    logo_record_size = (
        livery_logo_record_size_at(data, pos, end) if livery and may_decode_shape else 0
    )
    if logo_record_size:
        if bytes_at(data, pos, b"\x01\x02", end):
            mark_previous_terminal_shape_as_mask(state)
        flags = state.pending_flags | (0x01 if bytes_at(data, pos, b"\x01\x02", end) else 0)
        shape = decode_livery_logo_at(data, pos, is_mask=state.pending_mask, flags=flags)
        state.stack[-1].items.append(shape)
        state.decoded_shapes += 1
        state.pending_transform = None
        state.pending_flags = 0
        state.pending_mask = False
        state.pending_marker = b""
        state.pending_prefix = b""
        return pos + logo_record_size

    if may_decode_shape and is_valid_shape_at(data, pos, end):
        if bytes_at(data, pos, b"\x01\x02", end):
            # In livery streams the previous drawable can be the terminal
            # descendant of a just-closed group rather than a direct sibling.
            if livery:
                mark_previous_terminal_shape_as_mask(state)
            else:
                mark_previous_direct_shape_as_mask(
                    state, authoritative=len(state.stack) == 1
                )
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
        state.decoded_shapes += 1
        state.pending_flags = 0
        state.pending_mask = False
        state.pending_marker = b""
        state.pending_prefix = b""
        return pos + (32 if bytes_at(data, pos, b"\x00\x02", end) or bytes_at(data, pos, b"\x01\x02", end) else 31)

    if game_key == "fm8" and may_decode_shape and is_fm8_legacy_shape_at(data, pos, end):
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
        shape = decode_fm8_legacy_shape_at(
            data,
            pos,
            is_mask=state.pending_mask,
            flags=state.pending_flags,
        )
        state.stack[-1].items.append(shape)
        state.decoded_shapes += 1
        state.fm8_legacy_shapes += 1
        state.pending_flags = 0
        state.pending_mask = False
        state.pending_marker = b""
        state.pending_prefix = b""
        return pos + 31

    # Livery streams have a broader transform dialect whose leading bytes can
    # also look like a generic group transform. Resolve the more specific
    # grammar first so those bytes cannot be consumed by the generic decoder.
    if livery and not group_follows_control:
        livery_transform = read_livery_transform(
            data, pos, end, invert_odd_rotation=livery_invert_odd_rotation
        )
        if livery_transform:
            size, transform, marker = livery_transform
            if marker and marker[0] & 0x01:
                mark_previous_terminal_shape_as_mask(state)
            state.pending_transform = transform
            state.pending_marker = marker
            state.pending_prefix = b""
            return pos + size

    transform_record = (
        read_transform_record(data, pos, end, livery=False, game=game)
        if not state.pending_transform and may_decode_group
        else None
    )
    if transform_record:
        size, transform, marker = transform_record
        if marker and marker[0] & 0x01:
            mark_previous_terminal_shape_as_mask(state)
        state.pending_transform = transform
        state.pending_marker = state.pending_prefix + marker
        state.pending_prefix = b""
        return pos + size

    if (
        not state.pending_transform
        and may_decode_shape
        and is_unsupported_shape_record_at(data, pos, end)
    ):
        state.stack[-1].skipped_children += 1
        state.decoded_shapes += 1
        state.pending_marker = b""
        state.pending_prefix = b""
        state.pending_flags = 0
        state.pending_mask = False
        return pos + 32

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


def build_cgroup_tree(payload: bytes, game: str | None = "fh6") -> tuple[GroupNode, int, list[str], dict[str, Any]]:
    warnings: list[str] = []
    game_key = normalize_game_key(game)
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
    initial = read_initial_child_transform(layer_data, pos, len(layer_data), game=game_key)
    if initial:
        pos, state.pending_transform, state.pending_marker = initial
    while pos < len(layer_data) and guard < len(layer_data) + 4096:
        guard += 1
        close_complete_stack(state.stack)
        if consume_root_close_suffix(layer_data, pos, state):
            pos = len(layer_data)
            break
        next_pos = walk_step(layer_data, pos, len(layer_data), state, game=game_key)
        if next_pos <= pos:
            warnings.append(f"decoder made no progress at layer-data offset 0x{pos:x}")
            break
        pos = next_pos
    if pos < len(layer_data):
        warnings.append(f"decoder stopped before end: 0x{pos:x}/0x{len(layer_data):x}")
    stats = cgroup_tree_stats(root)
    if game_key == "fm8":
        stats["fm8_pre_group_transform_records"] = count_fm8_pre_group_transform_records(layer_data)
        stats["fm8_legacy_shape_records"] = state.fm8_legacy_shapes
        stats["offline_decode_profile"] = "fm8_local_save_cgroup_v1"
    else:
        stats["offline_decode_profile"] = "standard_cgroup_v1"
    return root, layer_start, warnings, stats


def read_initial_child_transform(
    data: bytes,
    pos: int,
    end: int,
    game: str | None = "fh6",
) -> tuple[int, Transform, bytes] | None:
    for candidate in range(pos, min(end, pos + 8)):
        record = read_transform_record(data, candidate, end, livery=False, game=game)
        if record:
            size, transform, marker = record
            if valid_counted_group_at(data, candidate + size, end):
                return candidate + size, transform, marker
    if pos + 16 <= end and valid_counted_group_at(data, pos + 16, end):
        transform = read_transform_payload(data, pos, end)
        if transform:
            return pos + 16, transform, b""
    return None


def transform_is_identity(transform: Transform) -> bool:
    return (
        abs(float(transform.x)) <= 1e-6
        and abs(float(transform.y)) <= 1e-6
        and abs(float(transform.sx) - 1.0) <= 1e-6
        and abs(float(transform.sy) - 1.0) <= 1e-6
        and abs(normalize_rotation(float(transform.rotation))) <= 1e-6
    )


def cgroup_tree_stats(root: GroupNode) -> dict[str, Any]:
    stats = {
        "group_nodes": 0,
        "non_identity_group_transforms": 0,
        "max_group_depth": 0,
    }

    def walk(node: GroupNode, depth: int) -> None:
        for item in node.items:
            if not isinstance(item, GroupNode):
                continue
            stats["group_nodes"] += 1
            stats["max_group_depth"] = max(int(stats["max_group_depth"]), depth + 1)
            if not transform_is_identity(item.transform):
                stats["non_identity_group_transforms"] += 1
            walk(item, depth + 1)

    walk(root, 0)
    return stats


def count_fm8_pre_group_transform_records(data: bytes) -> int:
    count = 0
    end = len(data)
    for pos in range(0, max(0, end - 17) + 1):
        if data[pos] != 0x02:
            continue
        transform = read_transform_payload(data, pos + 1, end)
        if transform and valid_counted_group_at(data, pos + 17, end):
            count += 1
    return count


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
                record_mask = item.mask and (item.mask_authoritative or not has_color_data(item.color_rgba))
                is_mask = current_mask or record_mask
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
                        "is_raster_logo": item.is_raster_logo,
                        "raster_id": item.raster_id,
                    }
                )
            else:
                walk(item, node_matrix, current_mask, current_section)

    walk(root, affine(1.0, 0.0, 0.0, 0.0, 1.0, 0.0), False, section)
    return layers


def cgroup_to_layers(payload: bytes, game: str | None = "fh6") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root, layer_start, warnings, stats = build_cgroup_tree(payload, game=game)
    layers = flatten_tree(root, layer_start=layer_start)
    return layers, {
        "source_kind": "cgroup",
        "payload_size": len(payload),
        "layer_data_start": layer_start,
        "root_expected_children": root.expected_children,
        **stats,
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


def _privacy_markerless_group_at(data: bytes, pos: int, end: int) -> GroupInfo | None:
    """Recognize privacy wrappers without routing them through artwork parsing."""

    # Privacy metadata exists in both compact and wide markerless wrappers.
    # The renderer intentionally follows the narrower FLS artwork grammar, so
    # this safety check must not depend on valid_markerless_group_at().
    if pos < 0 or pos + 3 > end:
        return None
    count = read_u16(data, pos)
    if count <= 0:
        return None
    child_blocks = (count + 7) // 8
    candidates: list[GroupInfo] = []
    if (
        child_blocks <= 0xFF
        and data[pos + 2] == child_blocks
        and pos + 3 + child_blocks + 2 <= end
    ):
        candidates.append(
            GroupInfo(
                count=count,
                child_blocks=child_blocks,
                size=3 + child_blocks + 2,
                marker=b"",
            )
        )
    if (
        pos + 4 <= end
        and read_u16(data, pos + 2) == child_blocks
        and pos + 4 + child_blocks + 2 <= end
    ):
        candidates.append(
            GroupInfo(
                count=count,
                child_blocks=child_blocks,
                size=4 + child_blocks + 2,
                marker=b"",
            )
        )
    for candidate in candidates:
        child = pos + candidate.size
        if (
            is_valid_shape_at(data, child, end)
            or is_livery_logo_at(data, child, end)
            or is_unsupported_shape_record_at(data, child, end)
            or _raw_livery_counted_group_at(data, child, end)
            or _raw_livery_markerless_group_at(data, child, end)
        ):
            return candidate
    return None


def _protected_livery_group_at(data: bytes, pos: int, end: int) -> tuple[int, GroupInfo] | None:
    """Return the protected group wrapper at a structurally valid livery boundary."""
    trailer = livery_transform_trailer(data, pos, end)
    if trailer is None:
        return None
    trailer_size, _ = trailer
    group_pos = pos + trailer_size
    group = _privacy_markerless_group_at(data, group_pos, end)
    if group is None:
        return None

    # The wrapper must immediately follow a valid livery transform. This keeps
    # coincidental byte patterns inside shape/color records from becoming a
    # privacy decision.
    direct_transform = pos >= 16 and read_transform_payload(data, pos - 16, end) is not None
    scaled_transform = (
        pos >= 21
        and (data[pos - 5] & ~0x40) == 0x30
        and read_transform_payload(data, pos - 21, end) is not None
    )
    if not direct_transform and not scaled_transform:
        return None
    return trailer_size, group


def inspect_clivery_privacy(payload: bytes) -> dict[str, Any]:
    """Inspect ownership and embedded-group privacy without decoding artwork."""
    if len(payload) < 12 or payload[:4] != b"vlrc":
        raise DecodeError("C_livery privacy inspection requires a valid livery payload")
    body, _, _ = extract_livery_payload(payload)
    protected_offsets: list[int] = []
    pos = 0
    end = len(body)
    while pos < end:
        protected = _protected_livery_group_at(body, pos, end)
        if protected is None:
            pos += 1
            continue
        trailer_size, group = protected
        protected_offsets.append(pos)
        pos += trailer_size + max(1, group.size)
    return {
        "source_owned": read_u32(payload, 8) != 1,
        "foreign_group_count": len(protected_offsets),
        "contains_foreign_groups": bool(protected_offsets),
        "protected_group_offsets": protected_offsets,
    }


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
        reserved_tail = LIVERY_POPULATED_REMNANT_SIZE
        for later_slot in range(slot + 1, len(LIVERY_SECTION_NAMES)):
            later_target = counts[later_slot] if later_slot < len(counts) else 0
            reserved_tail += LIVERY_EMPTY_SLOT_SIZE if later_target <= 0 else later_target * 32
        walk_limit = max(pos, end - reserved_tail)
        guard = 0
        while state.decoded_shapes < target and pos < walk_limit and guard < end + 4096:
            guard += 1
            close_complete_stack(state.stack)
            if len(state.stack) < 2:
                warnings.append(f"{name}: parser stack closed before reaching target {target}")
                break
            at_section_root = state.stack[-1] is section_root
            deficit = target - state.decoded_shapes
            next_slot_populated = (
                slot + 1 < len(LIVERY_SECTION_NAMES)
                and slot + 1 < len(counts)
                and counts[slot + 1] > 0
            )
            if (
                at_section_root
                and not state.pending_transform
                and next_slot_populated
                and 0 < deficit <= 8
            ):
                next_section = valid_markerless_group_at(
                    body,
                    pos + LIVERY_POPULATED_REMNANT_SIZE,
                    end,
                    allow_count_one=True,
                    livery=True,
                )
                if next_section and next_section.count >= 8:
                    break
            if at_section_root and not state.pending_transform:
                markerless = valid_markerless_group_at(body, pos, end, allow_count_one=True, livery=True)
                if markerless:
                    pos = push_markerless_group(body, pos, end, markerless, state, livery=True)
                    continue
            next_pos = walk_step(
                body,
                pos,
                end,
                state,
                livery=True,
                livery_invert_odd_rotation=slot != 2,
            )
            if next_pos <= pos:
                warnings.append(f"{name}: decoder made no progress at body offset 0x{pos:x}")
                break
            pos = next_pos
        close_complete_stack(state.stack)
        # A populated livery section can store the mask state for its final
        # shape in the first byte after the shape stream. The main loop stops
        # as soon as the declared placement count is reached, so consume that
        # terminal state before flattening the section tree.
        if pos < end and body[pos] == 0x01:
            mark_previous_terminal_shape_as_mask(state)
        decoded = flatten_tree(section_root, layer_start=0, section=name)
        if slot == 5:
            for layer in decoded:
                data = layer.get("data") or []
                if len(data) >= 5:
                    data[0] = -float(data[0])
                    data[1] = -float(data[1])
                    data[4] = normalize_rotation(float(data[4]) + 180.0)
        if len(decoded) != target:
            warnings.append(f"{name}: decoded {len(decoded)} layer(s), stats target is {target}")
        for layer in decoded:
            layer["section_start"] = section_start
            layers.append(layer)
        pos = min(pos, walk_limit)
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
        is_raster_logo = bool(layer.get("is_raster_logo"))
        normalized = None if is_raster_logo else normalize_game_shape_word(raw_word, game_key)
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
        if is_raster_logo:
            shape["is_raster_logo"] = True
            shape["raster_id"] = int(layer.get("raster_id") or (raw_word & 0x7FFF))
            shape["source_raw_type_word"] = raw_word
            shape["source_raw_type_word_hex"] = f"0x{raw_word:04x}"
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
        layers, report = cgroup_to_layers(payload, game=game_key)
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
