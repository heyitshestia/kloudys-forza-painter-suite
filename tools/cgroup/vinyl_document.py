"""Validated offline vinyl encoding using KFPS's existing shape/group metadata.

Native groups have identity transforms; world-space shape geometry stays in the
leaves. No live-memory code or external implementation is used here.
"""

from __future__ import annotations

import json
import math
import struct
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .cgroup_codec import CGroupLayer, build_flat_payload, default_payload_prefix, layer_from_shape, pack_shape
from .forza_source_decoder import cgroup_to_layers

MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_LAYERS = 3000
MAX_GROUP_DEPTH = 64
MAX_GROUPS = 8192
GAMES = {"fh4", "fh5", "fh6", "fm8"}


@dataclass
class _Group:
    children: list = field(default_factory=list)
    mask: bool = False


def _group_path(shape: dict, index: int) -> tuple[tuple[str, str], ...]:
    path = shape.get("editor_group_path")
    if path is None:
        key = shape.get("editor_group_id")
        path = [{"id": key, "name": shape.get("editor_group_name") or ""}] if key else []
    if not isinstance(path, list) or len(path) > MAX_GROUP_DEPTH:
        raise ValueError(f"Shape {index + 1} has an invalid or excessively nested group path.")
    result = []
    seen = set()
    for group in path:
        if not isinstance(group, dict):
            raise ValueError(f"Shape {index + 1} has an invalid group.")
        key, name = group.get("id"), group.get("name", "")
        if (not isinstance(key, str) or not key or len(key) > 256 or key in seen
                or not isinstance(name, str) or len(name) > 1024):
            raise ValueError(f"Shape {index + 1} has invalid group metadata.")
        seen.add(key)
        result.append((key, name))
    if shape.get("editor_group_id") and (not result or result[-1][0] != shape["editor_group_id"]):
        raise ValueError(f"Shape {index + 1} has conflicting group metadata.")
    return tuple(result)


def _linear(sx, sy, angle, skew):
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return cosine * sx, (cosine * skew - sine) * sy, sine * sx, (sine * skew + cosine) * sy


def _validate_masks(shape: dict, data: list, index: int) -> None:
    explicit = [shape[key] for key in ("mask", "is_mask", "isMask") if key in shape]
    values = explicit + ([data[6]] if len(data) > 6 else [])
    if any(not isinstance(value, (bool, int, float)) or value not in (0, 1) for value in values):
        raise ValueError(f"Shape {index + 1} has an invalid mask flag; use true/false or 0/1.")
    if explicit and any(bool(value) != bool(explicit[0]) for value in explicit):
        raise ValueError(f"Shape {index + 1} has conflicting mask aliases.")
    # Existing KFPS files use an explicit mask flag to override a default data[6].


def _group_spans(root: _Group | None) -> Counter:
    spans = Counter()
    cursor = 0

    def walk(node: _Group, include: bool) -> None:
        nonlocal cursor
        start = cursor
        for child in node.children:
            if isinstance(child, _Group):
                walk(child, True)
            else:
                cursor += 1
        if include:
            spans[(start, cursor)] += 1

    if root is not None:
        walk(root, False)
    return spans


def _decoded_group_spans(layers: list[dict]) -> Counter:
    groups = {}
    parents = {}
    for index, layer in enumerate(layers):
        parent = None
        seen = set()
        for group in layer.get("editor_group_path", []):
            key = group["id"]
            if key in seen or (key in parents and parents[key] != parent):
                raise ValueError("Offline vinyl verification failed: inconsistent nested groups.")
            seen.add(key)
            parents[key] = parent
            start, end = groups.get(key, (index, index))
            if end != index:
                raise ValueError("Offline vinyl verification failed: noncontiguous group membership.")
            groups[key] = (start, index + 1)
            parent = key
    return Counter(groups.values())


def _verify(payload: bytes, expected: list[CGroupLayer], game: str, root: _Group | None) -> dict:
    actual, report = cgroup_to_layers(payload, game=game)
    if report["warnings"] or len(actual) != len(expected):
        raise ValueError("Offline vinyl verification failed: incomplete or unsupported native records.")
    if report["max_group_depth"] > MAX_GROUP_DEPTH:
        raise ValueError("Native mask/group nesting exceeds the editor's 64-level limit. Simplify the deepest groups.")
    # Native names/IDs are regenerated. Compare exact leaf ranges and multiplicity
    # instead, including helper mask groups and nested groups with identical bounds.
    if _decoded_group_spans(actual) != _group_spans(root):
        raise ValueError("Offline vinyl verification failed: nested group membership changed.")
    for index, (source, decoded) in enumerate(zip(expected, actual), 1):
        if (source.shape_id != decoded["shape_id"] or list(source.color_rgba) != decoded["color_rgba"]
                or source.mask != decoded["mask"]):
            raise ValueError(f"Offline vinyl verification failed at shape {index}: identity, colour or mask changed.")
        x, y, sx, sy, angle, skew = decoded["data"][:6]
        before = (source.x, source.y, *_linear(source.sx, source.sy, source.rotation, source.skew))
        after = (x, y, *_linear(sx, sy, angle, skew))
        if any(not math.isfinite(b) or not math.isclose(a, b, rel_tol=2e-6, abs_tol=1e-5)
               for a, b in zip(before, after)):
            raise ValueError(f"Offline vinyl verification failed at shape {index}: its placement changed.")
    return report


def _materialize_masks(group: _Group) -> None:
    for child in group.children:
        if isinstance(child, _Group):
            _materialize_masks(child)
    if group.children and all(child.mask for child in group.children):
        group.mask = True
        group.children = [replace(child, mask=False) if isinstance(child, CGroupLayer) else child
                          for child in group.children]
    else:
        group.children = [_Group([replace(child, mask=False)], mask=True)
                          if isinstance(child, CGroupLayer) and child.mask else child
                          for child in group.children]


def _encode_group(group: _Group, inherited_mask: bool = False) -> bytes:
    count = len(group.children)
    bitmap = bytearray((count + 7) // 8)
    for index, item in enumerate(group.children):
        if isinstance(item, _Group):
            bitmap[index // 8] |= 1 << (index % 8)
    result = bytearray(bytes((0x60 if group.mask else 0x20,)))
    result.extend(struct.pack("<HH", count, len(bitmap)))
    result.extend(b"\x00\x00")
    result.extend(bitmap)
    masked = inherited_mask or group.mask
    for item in group.children:
        if isinstance(item, _Group):
            # Native traversal requires a transform even for identity groups.
            result.extend(b"\x03" + struct.pack("<ffff", 0.0, 0.0, 1.0, 0.0))
            result.extend(_encode_group(item, masked))
        else:
            # The control byte belongs after this shape, not before the first
            # child. Explicit closes are required; child counts alone won't do.
            result.extend(pack_shape(item)[1:])
            result.append(int(masked or item.mask))
    result.append(0x01)
    return bytes(result)


def encode_vinyl_document(document: dict, target_game: str = "fh6") -> tuple[bytes, dict[str, Any]]:
    if target_game not in GAMES:
        raise ValueError("Offline vinyl encoding requires FH4, FH5, FH6 or FM8.")
    shapes = document.get("shapes") if isinstance(document, dict) else None
    if not isinstance(shapes, list) or not shapes or len(shapes) > MAX_LAYERS:
        raise ValueError(f"A vinyl must contain between 1 and {MAX_LAYERS} shapes.")
    records = []
    identities = {}
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise ValueError(f"Shape {index + 1} is not an object.")
        data = shape.get("data")
        if not isinstance(data, list) or len(data) < 4:
            raise ValueError(f"Shape {index + 1} has invalid geometry.")
        for value in data[:6]:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Shape {index + 1} has non-finite or invalid geometry.")
        _validate_masks(shape, data, index)
        color = shape.get("color")
        if color is not None and (not isinstance(color, list) or len(color) not in (3, 4)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in color)):
            raise ValueError(f"Shape {index + 1} has invalid colour data.")
        path = _group_path(shape, index)
        parent = None
        for key, name in path:
            value = (parent, name)
            if key in identities and identities[key] != value:
                raise ValueError("The vinyl has conflicting group parents or names.")
            identities[key] = value
            parent = key
        try:
            layer = layer_from_shape(shape, index, target_game)
            if layer:
                # Packing once rejects values outside the native float32 range.
                pack_shape(layer)
                records.append((layer, path))
        except (TypeError, OverflowError, struct.error) as exc:
            raise ValueError(f"Shape {index + 1} cannot be represented in a native vinyl.") from exc
    if not records:
        raise ValueError("The vinyl contains no visible shapes.")
    expected = [item[0] for item in records]
    warnings = []
    root = None
    if not any(path for _, path in records):
        payload = build_flat_payload(expected)
    else:
        root = _Group()
        stack = [root]
        previous = ()
        opened = set()
        split = set()
        count = 0
        for layer, path in records:
            shared = 0
            while shared < min(len(path), len(previous)) and path[shared] == previous[shared]:
                shared += 1
            del stack[shared + 1:]
            for key, _ in path[shared:]:
                if key in opened:
                    split.add(key)
                opened.add(key)
                child = _Group()
                stack[-1].children.append(child)
                stack.append(child)
                count += 1
            # Mask groups make terminal/nested masks explicit, without ambiguous
            # trailing controls accidentally applying to a different sibling.
            stack[-1].children.append(layer)
            count += int(layer.mask)
            if count > MAX_GROUPS:
                raise ValueError("The vinyl has too many native groups for safe export.")
            previous = path
        if split:
            warnings.append(f"Split {len(split)} interleaved editor group(s) to preserve drawing order.")
        _materialize_masks(root)
        if len(root.children) > 2040:
            root = _Group([root])
        payload = default_payload_prefix() + _encode_group(root)
    verified = _verify(payload, expected, target_game, root)
    return payload, {"format": "kfps_offline_vinyl_v1", "game": target_game,
                     "layers": len(expected), "groups": verified["group_nodes"],
                     "skipped_transparent": len(shapes) - len(expected), "warnings": warnings}


def encode_vinyl_json(path: Path | str, target_game: str = "fh6") -> tuple[bytes, dict[str, Any]]:
    with Path(path).open("rb") as source:
        raw = source.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("The vinyl JSON exceeds the 64 MiB input limit.")
    return encode_vinyl_document(json.loads(raw.decode("utf-8-sig")), target_game)
