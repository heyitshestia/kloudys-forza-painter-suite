"""Shared KFPS JSON preview renderer.

This renders FH5-style primitive geometry and FH6/editor type-code JSONs into
small PNG thumbnails without writing preview files. It is used by both the Qt app
and the Fabric editor browser so JSON previews stay consistent.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry


ROOT = Path(__file__).resolve().parent
VINYL_RESOURCE_ROOT = ROOT / "tools" / "fabric-editor" / "Resources" / "Vinyls"
SHAPE_WORDS_PATH = ROOT / "tools" / "fabric-editor" / "shape-words.json"
PREVIEW_MAX = 420

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

VINYL_RESOURCE_CACHE: dict[tuple[str, int], list[list[tuple[float, float]]]] = {}
SHAPE_WORD_RESOURCE_CACHE: dict[int, tuple[str, int] | None] | None = None


def _resource_count_for_family(family: str) -> int:
    if str(family).startswith("Upper_Letters_"):
        return 26
    return 40


def _resolve_full_type_resource(type_code: int) -> tuple[str, int] | None:
    if int(type_code) <= 1000000:
        return None
    for family, base in VINYL_TYPE_BASES.items():
        delta = int(type_code) - int(base)
        if 0 <= delta < _resource_count_for_family(family):
            return family, delta + 1
    return None


def render_json_preview(path: Path | str, max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    path = Path(path)
    if _looks_like_typecode_preview(path):
        return _render_typecode_preview(path, max_size, transparent_background=transparent_background) or _render_primitive_preview(path, max_size, transparent_background=transparent_background)
    return _render_primitive_preview(path, max_size, transparent_background=transparent_background) or _render_typecode_preview(path, max_size, transparent_background=transparent_background)


def _shape_word_from_shape(shape: dict, type_code: int) -> int:
    for key in ("type_word", "typeWord", "shape_word", "shapeWord"):
        if key in shape:
            try:
                return int(shape.get(key)) & 0xFFFF
            except (TypeError, ValueError):
                pass
    return int(type_code) & 0xFFFF


def _looks_like_typecode_preview(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list):
        return False
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        if shape.get("source_format") == "fh6_typecode":
            return True
        if any(key in shape for key in ("type_word", "typeWord", "shape_word", "shapeWord", "resource_family", "resource_index")):
            return True
        try:
            if int(shape.get("type", 0)) > 1000000:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _checkerboard(size: tuple[int, int]):
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGBA", size, (38, 38, 38, 255))
    draw = ImageDraw.Draw(image)
    tile = 16
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(58, 58, 58, 255))
    return image


def _color_tuple(value) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    values = list(value[:4])
    if len(values) == 3:
        values.append(255)
    try:
        nums = [float(item) for item in values]
    except (TypeError, ValueError):
        return None
    if all(0.0 <= item <= 1.0 for item in nums):
        nums = [item * 255.0 for item in nums]
    out = [max(0, min(255, int(round(item)))) for item in nums]
    return out[0], out[1], out[2], out[3]


def _compensated_ellipse_size(width: float, height: float) -> tuple[float, float]:
    major = max(width, height)
    minor = max(1.0, min(width, height))
    aspect = major / minor
    uniform_scale = 1.0
    if major >= 220:
        uniform_scale *= 0.985
    if major >= 300:
        uniform_scale *= 0.975
    major_axis_scale = 1.0
    if aspect >= 2.0:
        major_axis_scale *= 0.985
    if aspect >= 3.5:
        major_axis_scale *= 0.970
    if aspect >= 6.0:
        major_axis_scale *= 0.955
    if width >= height:
        return max(1.0, width * uniform_scale * major_axis_scale), max(1.0, height * uniform_scale)
    return max(1.0, width * uniform_scale), max(1.0, height * uniform_scale * major_axis_scale)


def _ellipse_points(cx: float, cy: float, width: float, height: float, rot_deg: float, steps: int = 48) -> list[tuple[float, float]]:
    rx, ry = _compensated_ellipse_size(width / 2.0, height / 2.0)
    rot = math.radians(rot_deg)
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    points = []
    for step in range(steps):
        angle = math.tau * step / steps
        px = math.cos(angle) * rx
        py = math.sin(angle) * ry
        points.append((cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r))
    return points


def _rect_points(cx: float, cy: float, width: float, height: float, rot_deg: float) -> list[tuple[float, float]]:
    hw = width / 2.0
    hh = height / 2.0
    rot = math.radians(rot_deg)
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    points = []
    for px, py in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]:
        points.append((cx + px * cos_r - py * sin_r, cy + px * sin_r + py * cos_r))
    return points


def _shape_word_resource_map() -> dict[int, tuple[str, int] | None]:
    global SHAPE_WORD_RESOURCE_CACHE
    if SHAPE_WORD_RESOURCE_CACHE is not None:
        return SHAPE_WORD_RESOURCE_CACHE
    mapping: dict[int, tuple[str, int] | None] = {}
    for family, base in VINYL_TYPE_BASES.items():
        base_word = int(base) & 0xFFFF
        for index in range(1, _resource_count_for_family(family) + 1):
            mapping.setdefault((base_word + index - 1) & 0xFFFF, (family, index))
    if SHAPE_WORDS_PATH.exists():
        try:
            payload = json.loads(SHAPE_WORDS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for family, values in (payload.get("families") or {}).items():
            if not isinstance(values, dict):
                continue
            for index, word in values.items():
                try:
                    mapping.setdefault(int(word) & 0xFFFF, (family, int(index)))
                except (TypeError, ValueError):
                    continue
    SHAPE_WORD_RESOURCE_CACHE = mapping
    return mapping


def _resolve_vinyl_resource(type_code: int, shape: dict | None = None) -> tuple[str, int] | None:
    shape = shape or {}
    full_resource = _resolve_full_type_resource(type_code)
    if full_resource:
        return full_resource
    family = shape.get("resource_family")
    index = shape.get("resource_index")
    if family and index:
        try:
            return str(family), int(index)
        except (TypeError, ValueError):
            pass
    word = _shape_word_from_shape(shape, type_code)
    return _shape_word_resource_map().get(word)


def _resource_triangles(family: str, index: int) -> list[list[tuple[float, float]]] | None:
    key = (family, int(index))
    if key in VINYL_RESOURCE_CACHE:
        return VINYL_RESOURCE_CACHE[key]
    path = VINYL_RESOURCE_ROOT / family / str(index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    vertices = payload.get("Vertices") or []
    indices = payload.get("Indices") or []
    triangles = []
    for pos in range(0, len(indices) - 2, 3):
        tri = []
        for raw_index in indices[pos : pos + 3]:
            try:
                vertex = vertices[int(raw_index)]
                tri.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
            except (TypeError, ValueError, IndexError, AttributeError):
                break
        if len(tri) == 3:
            triangles.append(tri)
    if not triangles:
        points = []
        for vertex in vertices:
            try:
                points.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
            except (TypeError, ValueError, AttributeError):
                continue
        if len(points) >= 3:
            triangles = [points]
    if not triangles:
        return None
    VINYL_RESOURCE_CACHE[key] = triangles
    return triangles


def _fallback_triangles(word: int) -> list[list[tuple[float, float]]]:
    if (int(word) & 0xFFFF) == 0x65:
        return [[(-64.0, -64.0), (64.0, -64.0), (64.0, 64.0), (-64.0, 64.0)]]
    return [[(math.cos(math.tau * step / 32) * 64.0, math.sin(math.tau * step / 32) * 64.0) for step in range(32)]]


def _transform_resource_polygon(points: list[tuple[float, float]], data: list) -> list[tuple[float, float]]:
    x = float(data[0]) if len(data) > 0 else 0.0
    y = float(data[1]) if len(data) > 1 else 0.0
    sx = float(data[2]) if len(data) > 2 else 1.0
    sy = float(data[3]) if len(data) > 3 else 1.0
    rot = math.radians(-(float(data[4]) if len(data) > 4 else 0.0))
    skew = float(data[5]) if len(data) > 5 else 0.0
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    transformed = []
    for px, py in points:
        lx = float(px) * sx
        ly = float(py) * sy
        if skew:
            lx += float(py) * sy * -skew
        editor_x = x + lx * cos_r - ly * sin_r
        editor_y = -y + lx * sin_r + ly * cos_r
        # _render_polygons is y-up; the editor matrix above is y-down.
        transformed.append((editor_x, -editor_y))
    return transformed


def _render_polygons(polygons: list[dict], max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    from PIL import Image, ImageDraw

    all_points = [point for item in polygons for poly in item["polygons"] for point in poly]
    if not all_points:
        return None
    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    span = max(max_x - min_x, max_y - min_y, 1.0)
    padding = max(12.0, min(80.0, span * 0.05))
    world_w = max(1.0, (max_x - min_x) + padding * 2.0)
    world_h = max(1.0, (max_y - min_y) + padding * 2.0)
    scale = min(float(max_size) / max(world_w, world_h), 4.0)
    width = max(1, int(round(world_w * scale)))
    height = max(1, int(round(world_h * scale)))

    def to_canvas(point: tuple[float, float]) -> tuple[float, float]:
        return ((point[0] - min_x + padding) * scale, (max_y - point[1] + padding) * scale)

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0)) if transparent_background else _checkerboard((width, height))
    for item in polygons:
        color = item["color"]
        if color[3] <= 0:
            continue
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer, "RGBA")
        for poly in item["polygons"]:
            points = [to_canvas(point) for point in poly]
            if len(points) >= 3:
                draw.polygon(points, fill=color)
        image = Image.alpha_composite(image, layer)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _render_primitive_preview(path: Path, max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    try:
        data = load_normalized_geometry(path)
        shapes = data["shapes"]
        background = shapes[0]
    except Exception:
        return None
    polygons = []
    for shape in shapes[1:]:
        color = _color_tuple(shape.get("color"))
        if not color or color[3] <= 0:
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        try:
            x, y, width, height = [float(item) for item in data[:4]]
            rot = float(data[4]) if len(data) >= 5 else 0.0
        except (TypeError, ValueError):
            continue
        shape_type = int(shape.get("type", ROTATED_ELLIPSE))
        if shape_type in (RECTANGLE, ROTATED_RECTANGLE):
            poly = _rect_points(x, -y, abs(width), abs(height), -rot)
        else:
            poly = _ellipse_points(x, -y, abs(width), abs(height), -rot)
        polygons.append({"polygons": [poly], "color": color})
    if polygons:
        return _render_polygons(polygons, max_size=max_size, transparent_background=transparent_background)
    color = _color_tuple(background.get("color"))
    if color and color[3] > 0:
        return _render_polygons([{"polygons": [[(-1, -1), (1, -1), (1, 1), (-1, 1)]], "color": color}], max_size=max_size, transparent_background=transparent_background)
    return None


def _render_typecode_preview(path: Path, max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    shapes = payload.get("shapes") if isinstance(payload, dict) else None
    if not isinstance(shapes, list):
        return None
    polygons = []
    for shape in shapes:
        if not isinstance(shape, dict):
            continue
        color = _color_tuple(shape.get("color"))
        if not color or color[3] <= 0:
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        try:
            [float(item) for item in data[:4]]
        except (TypeError, ValueError):
            continue
        try:
            type_code = int(shape.get("type", ROTATED_ELLIPSE))
        except (TypeError, ValueError):
            type_code = ROTATED_ELLIPSE
        word = _shape_word_from_shape(shape, type_code)
        if type_code <= 1000000 and not any(key in shape for key in ("type_word", "typeWord", "shape_word", "shapeWord", "resource_family", "resource_index")):
            continue
        resource = _resolve_vinyl_resource(type_code, shape)
        triangles = _resource_triangles(*resource) if resource else None
        if not triangles:
            triangles = _fallback_triangles(word)
        transformed = [_transform_resource_polygon(poly, data) for poly in triangles]
        if transformed:
            polygons.append({"polygons": transformed, "color": color})
    return _render_polygons(polygons, max_size=max_size, transparent_background=transparent_background) if polygons else None
