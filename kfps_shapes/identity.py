"""Neutral shape resource bases and integer parsing shared across KFPS."""
from __future__ import annotations
from typing import Any

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
