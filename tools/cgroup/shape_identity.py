#!/usr/bin/env python3
"""Canonical KFPS shape identity helpers.

This module separates visual resources from game shape words. Numeric identities
are authoritative in exported JSON; resource labels are a fallback for resource-
only inputs, not permission to reinterpret an existing ID.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from kfps_shapes.identity import VINYL_TYPE_BASES, parse_int


TYPE_CODE_BASE = 0x100000


# Slots are canonical resource indices, not positions in FM8's shape picker.
# All 160 community raw IDs match the canonical IDs in saved/live grid validation.
FM8_COMMUNITY_SLOT_WORDS = {
    f"Community_Vinyls_{tab}": tuple(range(base, base + 40))
    for tab, base in enumerate((2101, 2201, 2301, 2401), 1)
}

FM8_EXPORT_RESOURCE_MAP = {
    word: (family, index)
    for family, words in FM8_COMMUNITY_SLOT_WORDS.items()
    for index, word in enumerate(words, 1)
}

FM8_COMPACT_TAB_BASES = {
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


@dataclass(frozen=True)
class ShapeIdentity:
    word: int
    type_code: int
    source: str
    conflict: str | None = None




def explicit_shape_word(shape: dict[str, Any]) -> int | None:
    type_code = parse_int(shape.get("type"))
    # Match the editor and preview: a full native type is stronger than a stale
    # redundant low-word field. Legacy geometry IDs still use their explicit word.
    if type_code is not None and TYPE_CODE_BASE <= type_code <= TYPE_CODE_BASE + 0xFFFF:
        return type_code & 0xFFFF
    for key in ("type_word", "typeWord", "shape_word", "shapeWord"):
        value = parse_int(shape.get(key))
        if value is not None:
            return value & 0xFFFF
    if type_code is not None:
        return type_code & 0xFFFF
    return None


def resource_shape_word(family: str, index: int) -> int | None:
    family = str(family)
    index = parse_int(index)
    if index is None or not 1 <= index <= 40:
        return None
    base = VINYL_TYPE_BASES.get(family)
    if base is None:
        return None
    return (base & 0xFFFF) + index - 1


def normalize_game_key(game: str | None) -> str:
    try:
        from game_adapters import get_adapter_or_default

        return get_adapter_or_default(game).shape_schema.canonical_game
    except ImportError:
        # Keep direct copies of this standalone codec usable outside the app root.
        pass
    text = str(game or "fh6").strip().lower()
    if text in {"fm", "fm8", "forza motorsport", "forza motorsport 8", "motorsport"}:
        return "fm8"
    if text in {"fh4", "forza horizon 4"}:
        return "fh4"
    if text in {"fh5", "forza horizon 5"}:
        return "fh5"
    return "fh6"


def canonical_resource_for_word(word: int) -> tuple[str, int] | None:
    """Resolve a canonical KFPS/FH type word to its visible resource slot."""
    type_code = TYPE_CODE_BASE + (int(word) & 0xFFFF)
    for family, base in VINYL_TYPE_BASES.items():
        offset = type_code - int(base)
        if 0 <= offset < 40:
            return family, offset + 1
    return None


def target_game_shape_word(shape: dict[str, Any], identity_word: int, target_game: str | None = "fh6") -> int:
    game_key = normalize_game_key(target_game)
    source_game = shape.get("source_game") or shape.get("sourceGame")
    if source_game and normalize_game_key(source_game) == game_key:
        raw_word = parse_int(shape.get("source_raw_type_word") or shape.get("sourceRawTypeWord"))
        if raw_word is None:
            raw_word = explicit_shape_word(shape)
        if raw_word is not None:
            return raw_word & 0xFFFF
    # All 1,400 verified native slots share IDs across these games. FM8 picker
    # positions and legacy descriptive labels must not remap a resolved ID.
    return int(identity_word) & 0xFFFF


def fm8_resource_for_word(raw_word: int) -> tuple[str, int] | None:
    raw_word = int(raw_word) & 0xFFFF
    mapped = FM8_EXPORT_RESOURCE_MAP.get(raw_word)
    if mapped:
        return mapped
    for base_word, family in sorted(FM8_COMPACT_TAB_BASES.items(), reverse=True):
        offset = raw_word - int(base_word)
        if 0 <= offset < 40:
            return family, offset + 1
    return None


def normalize_game_shape_word(raw_word: int, game: str | None) -> dict[str, Any] | None:
    game_key = normalize_game_key(game)
    raw_word = int(raw_word) & 0xFFFF
    if game_key != "fm8":
        return None
    resource = fm8_resource_for_word(raw_word)
    if not resource:
        return None
    family, index = resource
    canonical_word = resource_shape_word(family, index)
    if canonical_word is None:
        return None
    return {
        "game": game_key,
        "raw_word": raw_word,
        "raw_type": TYPE_CODE_BASE + raw_word,
        "canonical_word": canonical_word,
        "canonical_type": TYPE_CODE_BASE + canonical_word,
        "resource_family": family,
        "resource_index": int(index),
    }


def canonical_shape_identity(shape: dict[str, Any]) -> ShapeIdentity:
    explicit = explicit_shape_word(shape)
    family = shape.get("resource_family") or shape.get("resourceFamily")
    index = parse_int(shape.get("resource_index") or shape.get("resourceIndex"))
    resource_word = resource_shape_word(str(family), index) if family and index is not None else None
    conflict = None
    if explicit is not None and resource_word is not None and explicit != resource_word:
        conflict = f"explicit word {explicit} disagrees with {family}/{index} -> {resource_word}"
    if explicit is not None:
        return ShapeIdentity(explicit, TYPE_CODE_BASE + explicit, "explicit", conflict)
    if resource_word is not None:
        return ShapeIdentity(resource_word, TYPE_CODE_BASE + resource_word, "resource")
    raise ValueError("shape has no usable type_word, shape_word, type, or resource identity")


def canonicalize_shape(shape: dict[str, Any]) -> tuple[dict[str, Any], ShapeIdentity]:
    identity = canonical_shape_identity(shape)
    out = dict(shape)
    out["type"] = identity.type_code
    out["type_word"] = identity.word
    out["type_word_hex"] = f"0x{identity.word:04x}"
    resource = canonical_resource_for_word(identity.word)
    if resource:
        out["resource_family"], out["resource_index"] = resource
        out.pop("resourceFamily", None)
        out.pop("resourceIndex", None)
    if identity.conflict:
        out["shape_identity_conflict"] = identity.conflict
    return out, identity
