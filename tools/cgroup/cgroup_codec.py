#!/usr/bin/env python3
"""Clean-room flat C_group encoder/decoder prototype.

This is intentionally isolated from the live memory importer/exporter. It
implements the minimal flat payload needed to build deterministic fixtures from
KFPS JSON and read those fixtures back for comparison.
"""

from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from .shape_identity import canonical_shape_identity
except ImportError:  # pragma: no cover - direct script execution fallback
    from shape_identity import canonical_shape_identity


MAX_FLAT_LAYERS = 3000


@dataclass(frozen=True)
class CGroupLayer:
    shape_id: int
    x: float
    y: float
    sx: float
    sy: float
    rotation: float
    skew: float
    color_rgba: tuple[int, int, int, int]
    mask: bool = False
    source_index: int | None = None


def le_u16(value: int) -> bytes:
    return struct.pack("<H", int(value) & 0xFFFF)


def le_u32(value: int) -> bytes:
    return struct.pack("<I", int(value) & 0xFFFFFFFF)


def le_f32(value: float) -> bytes:
    return struct.pack("<f", float(value))


def normalized_rotation(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return value % 360.0


def clamp_byte(value: Any) -> int:
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    if 0.0 <= value <= 1.0:
        value *= 255.0
    return max(0, min(255, int(round(value))))


def normalize_rgba(value: Any) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)):
        return 255, 255, 255, 255
    items = list(value[:4])
    if len(items) == 3:
        items.append(255)
    while len(items) < 4:
        items.append(255)
    return tuple(clamp_byte(item) for item in items[:4])  # type: ignore[return-value]


def default_payload_prefix() -> bytes:
    return (
        b"gyvl"
        + le_u32(1)
        + le_u32(0)
        + b"\x03"
        + le_f32(0.0)
        + le_f32(0.0)
        + le_f32(1.0)
        + le_f32(0.0)
    )


def pack_shape(layer: CGroupLayer, trailing_mask_for_previous: bool = False) -> bytes:
    r, g, b, a = layer.color_rgba
    return b"".join(
        [
            b"\x01" if trailing_mask_for_previous else b"\x00",
            b"\x02",
            le_u16(layer.shape_id),
            le_f32(normalized_rotation(layer.rotation)),
            le_f32(layer.x),
            le_f32(layer.y),
            le_f32(layer.sx),
            le_f32(layer.sy),
            le_f32(layer.skew),
            bytes((b, g, r, a)),
        ]
    )


def build_flat_payload(layers: Iterable[CGroupLayer]) -> bytes:
    visible = list(layers)
    if len(visible) > MAX_FLAT_LAYERS:
        raise ValueError(f"flat C_group export supports at most {MAX_FLAT_LAYERS} layers")
    child_count = len(visible)
    child_blocks = (child_count + 7) // 8
    encoded_child_blocks = min(child_blocks, 0xFF)
    payload = bytearray(default_payload_prefix())
    payload.extend(b"\x20")
    payload.extend(le_u16(child_count))
    payload.append(encoded_child_blocks)
    payload.extend(b"\x00" * (encoded_child_blocks + 2))
    previous_was_mask = False
    for layer in visible:
        payload.extend(pack_shape(layer, trailing_mask_for_previous=previous_was_mask))
        previous_was_mask = bool(layer.mask)
    payload.extend(b"\x00\x01")
    return bytes(payload)


def wrap_payload(payload: bytes) -> bytes:
    compressed = zlib.compress(payload)
    return le_u32(len(compressed)) + le_u32(len(payload)) + compressed


def unwrap_payload(raw: bytes) -> bytes:
    if len(raw) < 8:
        raise ValueError("C_group container is shorter than 8 bytes")
    compressed_length, payload_length = struct.unpack_from("<II", raw, 0)
    compressed = raw[8:]
    if compressed_length != len(compressed):
        raise ValueError("C_group compressed length header does not match file size")
    payload = zlib.decompress(compressed)
    if payload_length != len(payload):
        raise ValueError("C_group decompressed length header does not match payload size")
    return payload


def write_cgroup_file(path: Path | str, payload: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wrap_payload(payload))
    return path


def read_cgroup_payload(path: Path | str) -> bytes:
    path = Path(path)
    if path.is_dir():
        path = path / "C_group"
    return unwrap_payload(path.read_bytes())


def layer_from_shape(shape: dict[str, Any], index: int) -> CGroupLayer | None:
    color = normalize_rgba(shape.get("color"))
    if color[3] <= 0:
        return None
    data = list(shape.get("data") or [])
    if len(data) < 5:
        raise ValueError(f"shape {index + 1} needs data [x,y,sx,sy,rotation]")
    while len(data) < 6:
        data.append(0)
    identity = canonical_shape_identity(shape)
    return CGroupLayer(
        shape_id=identity.word,
        x=float(data[0]),
        y=float(data[1]),
        sx=float(data[2]),
        sy=float(data[3]),
        rotation=float(data[4]),
        skew=float(data[5]),
        color_rgba=color,
        mask=bool(shape.get("mask") or (len(data) > 6 and data[6])),
        source_index=index,
    )


def layers_from_kfps_json(path: Path | str) -> list[CGroupLayer]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list):
        raise ValueError("KFPS JSON must contain a shapes list")
    layers: list[CGroupLayer] = []
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            continue
        layer = layer_from_shape(shape, index)
        if layer:
            layers.append(layer)
    return layers


def build_flat_cgroup_from_json(path: Path | str) -> bytes:
    return build_flat_payload(layers_from_kfps_json(path))


def parse_flat_payload(payload: bytes) -> dict[str, Any]:
    if payload[:4] != b"gyvl":
        raise ValueError("payload does not start with gyvl")
    if len(payload) < 0x24:
        raise ValueError("payload is too short for a root group")
    root_marker_offset = 0x1D
    if payload[root_marker_offset] not in (0x20, 0x60):
        raise ValueError("payload root group marker is not 0x20/0x60")
    count = struct.unpack_from("<H", payload, 0x1E)[0]
    child_blocks = payload[0x20]
    offset = 0x23 + child_blocks
    while offset < len(payload) and payload[offset] == 0:
        # Flat files can carry padding before the first record. Stop if the
        # next byte is the expected shape marker.
        if offset + 1 < len(payload) and payload[offset + 1] == 0x02:
            break
        offset += 1
    layers: list[dict[str, Any]] = []
    markers: list[int] = []
    for index in range(count):
        if offset >= len(payload):
            raise ValueError(f"payload ended before layer {index + 1}")
        marker = payload[offset]
        if marker == 0x02:
            offset += 1
            marker = 0
        elif offset + 1 < len(payload) and payload[offset + 1] == 0x02:
            offset += 2
        else:
            raise ValueError(f"layer {index + 1} is not a flat shape record at 0x{offset:x}")
        if offset + 30 > len(payload):
            raise ValueError(f"layer {index + 1} record is truncated")
        shape_id = struct.unpack_from("<H", payload, offset)[0]
        rotation, x, y, sx, sy, skew = struct.unpack_from("<ffffff", payload, offset + 2)
        b, g, r, a = payload[offset + 26 : offset + 30]
        layers.append(
            {
                "shape_id": shape_id,
                "data": [x, y, sx, sy, rotation, skew],
                "color_rgba": [r, g, b, a],
                "record_marker": marker,
            }
        )
        markers.append(marker)
        offset += 30
    for index in range(1, len(layers)):
        if markers[index] == 1:
            layers[index - 1]["mask"] = True
    if layers:
        layers[-1]["mask"] = False
    return {
        "format": "kfps_flat_cgroup_parse_v1",
        "version": struct.unpack_from("<I", payload, 4)[0],
        "root_marker": payload[root_marker_offset],
        "count": count,
        "child_blocks": child_blocks,
        "layers": layers,
        "payload_size": len(payload),
    }


def read_flat_cgroup(path: Path | str) -> dict[str, Any]:
    return parse_flat_payload(read_cgroup_payload(path))

