from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from tools.cgroup.shape_identity import VINYL_TYPE_BASES, parse_int


RESOURCE_SLOTS_PER_FAMILY = 40


def resource_count_for_family(_family: str) -> int:
    return RESOURCE_SLOTS_PER_FAMILY


def resolve_full_type_resource(type_code: int) -> tuple[str, int] | None:
    type_code = int(type_code)
    if type_code <= 1_000_000:
        return None
    for family, base in VINYL_TYPE_BASES.items():
        delta = type_code - int(base)
        if 0 <= delta < RESOURCE_SLOTS_PER_FAMILY:
            return family, delta + 1
    return None


def shape_word_from_shape(shape: dict[str, Any], type_code: int | None = None) -> int:
    for key in ("type_word", "typeWord", "shape_word", "shapeWord"):
        value = parse_int(shape.get(key))
        if value is not None:
            return value & 0xFFFF
    if type_code is None:
        type_code = parse_int(shape.get("type")) or 0
    return int(type_code) & 0xFFFF


@lru_cache(maxsize=8)
def _shape_word_resource_map(path_text: str, modified_ns: int) -> dict[int, tuple[str, int]]:
    del modified_ns
    mapping: dict[int, tuple[str, int]] = {}
    for family, base in VINYL_TYPE_BASES.items():
        base_word = int(base) & 0xFFFF
        for index in range(1, RESOURCE_SLOTS_PER_FAMILY + 1):
            mapping.setdefault((base_word + index - 1) & 0xFFFF, (family, index))
    path = Path(path_text) if path_text else None
    if path and path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        for family, values in (payload.get("families") or {}).items():
            if not isinstance(values, dict):
                continue
            for index, word in values.items():
                parsed_word = parse_int(word)
                parsed_index = parse_int(index)
                if parsed_word is not None and parsed_index is not None:
                    mapping.setdefault(parsed_word & 0xFFFF, (str(family), parsed_index))
    return mapping


def shape_word_resource_map(shape_words_path: str | Path | None = None) -> dict[int, tuple[str, int]]:
    path = Path(shape_words_path).resolve() if shape_words_path else None
    try:
        modified_ns = path.stat().st_mtime_ns if path else 0
    except OSError:
        modified_ns = 0
    return _shape_word_resource_map(str(path) if path else "", modified_ns)


def resolve_vinyl_resource(
    type_code: int,
    shape: dict[str, Any] | None = None,
    shape_words_path: str | Path | None = None,
) -> tuple[str, int] | None:
    shape = shape or {}
    full = resolve_full_type_resource(type_code)
    if full:
        return full
    family = shape.get("resource_family") or shape.get("resourceFamily")
    index = parse_int(shape.get("resource_index") or shape.get("resourceIndex"))
    if family and index is not None and 1 <= index <= RESOURCE_SLOTS_PER_FAMILY:
        return str(family), index
    word = shape_word_from_shape(shape, type_code)
    return shape_word_resource_map(shape_words_path).get(word)
