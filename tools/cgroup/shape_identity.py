#!/usr/bin/env python3
"""Canonical KFPS shape identity helpers.

This module separates visual resources from game shape words. The editor often
knows both `resource_family/resource_index` and `type_word`; finished export
code should prefer a verified resource mapping and report conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


TYPE_CODE_BASE = 0x100000

VINYL_TYPE_BASES = {
    "Primitives": 1048677,
    "Community_Vinyls_1": 1050677,
    "Community_Vinyls_2": 1050777,
    "Community_Vinyls_3": 1050877,
    "Community_Vinyls_4": 1050977,
    "Gradient_Shapes": 1048777,
    "Stripes": 1048877,
    "Tears": 1048977,
    "Racing_Icons": 1049077,
    "Flames": 1049177,
    "Paint_Splats": 1049277,
    "Tribal": 1049377,
    "Nature": 1049477,
    "Upper_Letters_1": 1050477,
    "Lower_Letters_1": 1050577,
    "Upper_Letters_2": 1049877,
    "Lower_Letters_2": 1049977,
    "Upper_Letters_3": 1050077,
    "Lower_Letters_3": 1050177,
    "Upper_Letters_4": 1050277,
    "Lower_Letters_4": 1050377,
    "Upper_Letters_5": 1051077,
    "Lower_Letters_5": 1051177,
    "Upper_Letters_6": 1051277,
    "Lower_Letters_6": 1051377,
    "Upper_Letters_7": 1051477,
    "Lower_Letters_7": 1051577,
    "Upper_Letters_8": 1051677,
    "Lower_Letters_8": 1051777,
    "Upper_Letters_9": 1051877,
    "Lower_Letters_9": 1051977,
    "Upper_Letters_10": 1052077,
    "Lower_Letters_10": 1052177,
    "Upper_Letters_11": 1052277,
    "Lower_Letters_11": 1052377,
}

FM8_COMMUNITY_SLOT_WORDS = {
    "Community_Vinyls_1": (
        2103, 2107, 2123, 2136, 2109, 2110, 2132, 2125, 2139, 2119,
        2135, 2117, 2127, 2133, 2129, 2116, 2138, 2115, 2137, 2101,
        2105, 2108, 2126, 2118, 2106, 2124, 2131, 2140, 2102, 2111,
        2104, 2112, 2134, 2113, 2114, 2120, 2128, 2130, 2122, 2121,
    ),
    "Community_Vinyls_2": (
        2201, 2218, 2226, 2210, 2230, 2240, 2238, 2217, 2231, 2209,
        2202, 2219, 2227, 2211, 2206, 2234, 2239, 2205, 2223, 2233,
        2203, 2220, 2228, 2212, 2222, 2235, 2225, 2215, 2224, 2208,
        2204, 2221, 2229, 2213, 2214, 2237, 2236, 2207, 2232, 2216,
    ),
    "Community_Vinyls_3": (
        2301, 2321, 2317, 2308, 2327, 2310, 2339, 2335, 2316, 2325,
        2302, 2311, 2318, 2337, 2336, 2329, 2332, 2334, 2324, 2333,
        2322, 2312, 2319, 2307, 2338, 2330, 2303, 2305, 2314, 2304,
        2331, 2309, 2328, 2326, 2323, 2320, 2313, 2306, 2315, 2340,
    ),
    "Community_Vinyls_4": (
        2401, 2421, 2417, 2408, 2427, 2413, 2406, 2430, 2414, 2410,
        2402, 2411, 2418, 2437, 2436, 2433, 2435, 2434, 2424, 2420,
        2422, 2412, 2419, 2407, 2438, 2425, 2440, 2404, 2432, 2415,
        2431, 2409, 2428, 2426, 2423, 2429, 2416, 2405, 2403, 2439,
    ),
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


def parse_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
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


def explicit_shape_word(shape: dict[str, Any]) -> int | None:
    for key in ("type_word", "typeWord", "shape_word", "shapeWord"):
        value = parse_int(shape.get(key))
        if value is not None:
            return value & 0xFFFF
    type_code = parse_int(shape.get("type"))
    if type_code is not None:
        return type_code & 0xFFFF
    return None


def resource_shape_word(family: str, index: int) -> int | None:
    family = str(family)
    try:
        index = int(index)
    except (TypeError, ValueError):
        return None
    if index < 1:
        return None
    if family == "Primitives":
        return 100 + index if index <= 40 else None
    base = VINYL_TYPE_BASES.get(family)
    if base is None:
        return None
    if family.startswith("Upper_Letters_"):
        return (base & 0xFFFF) + index - 1 if index <= 40 else None
    if family.startswith("Lower_Letters_"):
        # Lower-letter tabs have special symbols and historic ordering quirks.
        # Prefer explicit words for now unless a fixture proves every slot.
        return None
    return (base & 0xFFFF) + index - 1 if index <= 40 else None


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
    if game_key != "fm8":
        return int(identity_word) & 0xFFFF

    raw_word = parse_int(shape.get("source_raw_type_word") or shape.get("sourceRawTypeWord"))
    if raw_word is not None and normalize_game_key(source_game) == "fm8":
        return raw_word & 0xFFFF

    family = shape.get("resource_family") or shape.get("resourceFamily")
    index = parse_int(shape.get("resource_index") or shape.get("resourceIndex"))
    if family and index is not None:
        family = str(family)
        if family in FM8_COMMUNITY_SLOT_WORDS and 1 <= index <= len(FM8_COMMUNITY_SLOT_WORDS[family]):
            return int(FM8_COMMUNITY_SLOT_WORDS[family][index - 1]) & 0xFFFF
        for base_word, base_family in FM8_COMPACT_TAB_BASES.items():
            if family == base_family and 1 <= index <= 40:
                return (int(base_word) + index - 1) & 0xFFFF

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
    index = shape.get("resource_index") or shape.get("resourceIndex")
    resource_word = resource_shape_word(str(family), int(index)) if family and index is not None else None
    if resource_word is not None:
        conflict = None
        if explicit is not None and explicit != resource_word:
            conflict = f"explicit word {explicit} disagrees with {family}/{index} -> {resource_word}"
        return ShapeIdentity(resource_word, TYPE_CODE_BASE + resource_word, "resource", conflict)
    if explicit is not None:
        return ShapeIdentity(explicit, TYPE_CODE_BASE + explicit, "explicit")
    raise ValueError("shape has no usable type_word, shape_word, type, or resource identity")


def canonicalize_shape(shape: dict[str, Any]) -> tuple[dict[str, Any], ShapeIdentity]:
    identity = canonical_shape_identity(shape)
    out = dict(shape)
    out["type"] = identity.type_code
    out["type_word"] = identity.word
    out["type_word_hex"] = f"0x{identity.word:04x}"
    if identity.conflict:
        out["shape_identity_conflict"] = identity.conflict
    return out, identity
