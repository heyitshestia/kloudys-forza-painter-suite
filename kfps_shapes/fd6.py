from __future__ import annotations

from pathlib import Path
from typing import Any


FD6_FORMAT = "fd6.shapes"
KFPS_RECTANGLE_TYPE = 1048677
KFPS_ELLIPSE_TYPE = 1048678
KFPS_RECTANGLE_WORD = 0x0065
KFPS_ELLIPSE_WORD = 0x0066
FD6_RECTANGLE_DIVISOR = 127.0
FD6_ELLIPSE_DIVISOR = 63.0


def _safe_float(value: Any, default=0.0):
    try:
        if value is None or isinstance(value, bool):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def is_fd6_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and str(payload.get("format") or "").strip().lower() == FD6_FORMAT


def _color(value: Any) -> list[int] | None:
    if isinstance(value, dict):
        raw = [value.get("r"), value.get("g"), value.get("b"), value.get("a", 255)]
    elif isinstance(value, (list, tuple)):
        raw = list(value[:4])
        if len(raw) == 3:
            raw.append(255)
    else:
        return None
    if len(raw) != 4:
        return None
    try:
        numbers = [float(item) for item in raw]
    except (TypeError, ValueError):
        return None
    if all(0.0 <= item <= 1.0 for item in numbers):
        numbers = [item * 255.0 for item in numbers]
    return [max(0, min(255, int(round(item)))) for item in numbers]


def _shape_bounds(shape: Any):
    if not isinstance(shape, dict):
        return None
    kind = str(shape.get("type") or "").strip().lower()
    x = _safe_float(shape.get("x"), None)
    y = _safe_float(shape.get("y"), None)
    if x is None or y is None:
        return None
    if kind == "circle":
        radius = abs(_safe_float(shape.get("r"), 0.0))
        return x - radius, y - radius, x + radius, y + radius
    if kind in {"ellipse", "rotated_ellipse"}:
        radius_x = abs(_safe_float(shape.get("rx"), 0.0))
        radius_y = abs(_safe_float(shape.get("ry"), 0.0))
        radius = max(radius_x, radius_y) if kind == "rotated_ellipse" else None
        return (x - radius, y - radius, x + radius, y + radius) if radius else (
            x - radius_x, y - radius_y, x + radius_x, y + radius_y
        )
    if kind in {"rectangle", "rotated_rectangle"}:
        half_width = abs(_safe_float(shape.get("hw"), 0.0))
        half_height = abs(_safe_float(shape.get("hh"), 0.0))
        radius = (half_width * half_width + half_height * half_height) ** 0.5 if kind == "rotated_rectangle" else None
        return (x - radius, y - radius, x + radius, y + radius) if radius else (
            x - half_width, y - half_height, x + half_width, y + half_height
        )
    return None


def _conversion_center(payload: dict, shapes: list) -> tuple[float, float, str]:
    size = payload.get("image_size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        width = _safe_float(size[0], 0.0)
        height = _safe_float(size[1], 0.0)
        if width > 0 and height > 0:
            return width / 2.0, height / 2.0, "image_center"
    bounds = [item for item in (_shape_bounds(shape) for shape in shapes) if item]
    if bounds:
        return (
            (min(item[0] for item in bounds) + max(item[2] for item in bounds)) / 2.0,
            (min(item[1] for item in bounds) + max(item[3] for item in bounds)) / 2.0,
            "bounds_center",
        )
    return 0.0, 0.0, "zero"


def _rounded(value: float) -> float:
    result = round(float(value), 6)
    return 0.0 if result == -0.0 else result


def convert_fd6_payload(payload: dict, source: str | Path) -> tuple[dict, int, int]:
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list) or not shapes:
        raise ValueError("FD6 JSON must contain a non-empty shapes list.")
    center_x, center_y, origin = _conversion_center(payload, shapes)
    converted = []
    skipped = 0
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            skipped += 1
            continue
        kind = str(shape.get("type") or "").strip().lower()
        color = _color(shape.get("color"))
        if not color or color[3] <= 0:
            skipped += 1
            continue
        x = _safe_float(shape.get("x"), None)
        y = _safe_float(shape.get("y"), None)
        angle = _safe_float(shape.get("angle"), 0.0)
        type_code = type_word = resource_index = None
        scale_x = scale_y = None
        if kind == "circle":
            radius = abs(_safe_float(shape.get("r"), 0.0))
            scale_x = scale_y = radius / FD6_ELLIPSE_DIVISOR
            type_code, type_word, resource_index = KFPS_ELLIPSE_TYPE, KFPS_ELLIPSE_WORD, 2
        elif kind in {"ellipse", "rotated_ellipse"}:
            scale_x = abs(_safe_float(shape.get("rx"), 0.0)) / FD6_ELLIPSE_DIVISOR
            scale_y = abs(_safe_float(shape.get("ry"), 0.0)) / FD6_ELLIPSE_DIVISOR
            type_code, type_word, resource_index = KFPS_ELLIPSE_TYPE, KFPS_ELLIPSE_WORD, 2
        elif kind in {"rectangle", "rotated_rectangle"}:
            scale_x = abs(_safe_float(shape.get("hw"), 0.0)) * 2.0 / FD6_RECTANGLE_DIVISOR
            scale_y = abs(_safe_float(shape.get("hh"), 0.0)) * 2.0 / FD6_RECTANGLE_DIVISOR
            type_code, type_word, resource_index = KFPS_RECTANGLE_TYPE, KFPS_RECTANGLE_WORD, 1
        if x is None or y is None or type_code is None or not scale_x or not scale_y:
            skipped += 1
            continue
        converted.append({
            "type": type_code,
            "type_word": type_word,
            "data": [
                _rounded(x - center_x),
                _rounded(-(y - center_y)),
                _rounded(scale_x),
                _rounded(scale_y),
                _rounded((360.0 - angle) % 360.0),
                0,
                0,
            ],
            "color": color,
            "resource_family": "Primitives",
            "resource_index": resource_index,
            "source_format": FD6_FORMAT,
            "fd6_type": kind,
            "fd6_source_index": index,
        })
    if not converted:
        raise ValueError("FD6 JSON did not contain any supported visible shapes.")
    source = Path(source)
    display_name = f"{source.stem} (FD6 converted)"
    metadata = {
        "title": display_name,
        "display_name": display_name,
        "source_format": FD6_FORMAT,
        "source_file": source.name,
        "fd6_source_image": payload.get("source_image") or "",
        "fd6_profile": payload.get("profile") or "",
        "fd6_generated_at": payload.get("generated_at") or "",
        "fd6_sticker_mode": bool(payload.get("sticker_mode", False)),
        "fd6_origin": origin,
        "fd6_offset": [_rounded(center_x), _rounded(center_y)],
        "conversion": "fd6.shapes->kfps.typecode.v1",
        "target_game": "fh6",
        "layers": len(converted),
        "layer_count": len(converted),
        "shape_count": len(converted),
        "skipped_shapes": skipped,
    }
    return {"format": "kfps.fd6.converted.v1", "metadata": metadata, "shapes": converted}, len(converted), skipped
