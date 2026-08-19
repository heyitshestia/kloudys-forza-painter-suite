"""Shared KFPS JSON preview renderer.

This renders FH5-style primitive geometry and FH6/editor type-code JSONs into
small PNG thumbnails without writing preview files. It is used by both the Qt app
and the Fabric editor browser so JSON previews stay consistent.
"""

from __future__ import annotations

import concurrent.futures
import base64
import io
import json
import math
from pathlib import Path
from typing import Callable

from geometry_json import ELLIPSE, RECTANGLE, ROTATED_ELLIPSE, ROTATED_RECTANGLE, load_normalized_geometry
from kfps_shapes import (
    payload_uses_typecodes,
    resolve_full_type_resource,
    resolve_vinyl_resource,
    shape_word_from_shape,
    shape_word_resource_map,
)


ROOT = Path(__file__).resolve().parent
VINYL_RESOURCE_ROOT = ROOT / "tools" / "fabric-editor" / "Resources" / "Vinyls"
SHAPE_WORDS_PATH = ROOT / "tools" / "fabric-editor" / "shape-words.json"
PREVIEW_MAX = 420

VINYL_RESOURCE_CACHE: dict[tuple[str, int], list[list[tuple[float, float]]]] = {}
VINYL_RESOURCE_ALPHA_CACHE: dict[
    tuple[str, int],
    list[tuple[list[tuple[float, float]], tuple[int, int, int]]],
] = {}
def _resolve_full_type_resource(type_code: int) -> tuple[str, int] | None:
    return resolve_full_type_resource(type_code)


def render_json_preview(path: Path | str, max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    path = Path(path)
    if _looks_like_typecode_preview(path):
        return _render_typecode_preview(path, max_size, transparent_background=transparent_background) or _render_primitive_preview(path, max_size, transparent_background=transparent_background)
    return _render_primitive_preview(path, max_size, transparent_background=transparent_background) or _render_typecode_preview(path, max_size, transparent_background=transparent_background)


def _shape_word_from_shape(shape: dict, type_code: int) -> int:
    return shape_word_from_shape(shape, type_code)


def _looks_like_typecode_preview(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return payload_uses_typecodes(payload)


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


def _shape_mask_flag(shape: dict, data: list) -> bool:
    """Read every mask spelling accepted by the FH import/export path."""
    for key in ("mask", "is_mask", "isMask"):
        if key in shape:
            return bool(shape.get(key))
    if len(data) > 6:
        try:
            return bool(int(float(data[6])))
        except (TypeError, ValueError):
            return bool(data[6])
    return False


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


def _ellipse_points(cx: float, cy: float, radius_x: float, radius_y: float, rot_deg: float, steps: int = 48) -> list[tuple[float, float]]:
    # Legacy KFPS primitive types 8/16 store ellipse radii. Rectangle types
    # 1/2 use full dimensions and are handled separately by _rect_points.
    rx, ry = _compensated_ellipse_size(radius_x, radius_y)
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
    return shape_word_resource_map(SHAPE_WORDS_PATH)


def _resolve_vinyl_resource(type_code: int, shape: dict | None = None) -> tuple[str, int] | None:
    return resolve_vinyl_resource(type_code, shape, SHAPE_WORDS_PATH)


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


def _resource_alpha_triangles(
    family: str,
    index: int,
) -> list[tuple[list[tuple[float, float]], tuple[int, int, int]]] | None:
    """Return native triangles with their per-vertex FH6 opacity values."""

    key = (family, int(index))
    if key in VINYL_RESOURCE_ALPHA_CACHE:
        return VINYL_RESOURCE_ALPHA_CACHE[key]
    path = VINYL_RESOURCE_ROOT / family / str(index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        vertices = payload.get("Vertices") or []
        indices = payload.get("Indices") or []
        encoded_alpha = payload.get("VerticesAlpha")
        alpha = base64.b64decode(encoded_alpha, validate=True) if encoded_alpha else b""
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if alpha and len(alpha) != len(vertices):
        return None
    if not alpha:
        alpha = bytes([255]) * len(vertices)

    triangles: list[tuple[list[tuple[float, float]], tuple[int, int, int]]] = []
    for pos in range(0, len(indices) - 2, 3):
        points: list[tuple[float, float]] = []
        values: list[int] = []
        for raw_index in indices[pos : pos + 3]:
            try:
                vertex_index = int(raw_index)
                vertex = vertices[vertex_index]
                points.append((float(vertex.get("X", 0.0)), float(vertex.get("Y", 0.0))))
                values.append(alpha[vertex_index])
            except (TypeError, ValueError, IndexError, AttributeError):
                break
        if len(points) == 3:
            triangles.append((points, (values[0], values[1], values[2])))
    if not triangles:
        return None
    VINYL_RESOURCE_ALPHA_CACHE[key] = triangles
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


def _render_raster_layer_canvas(
    source,
    data: list,
    color: tuple[int, int, int, int],
    canvas_size: tuple[int, int],
    world_bounds: tuple[float, float, float, float],
):
    from PIL import Image, ImageChops

    # FH6 decal swatches use the opposite vertical texture convention from
    # the section canvas used by KFPS.
    source = source.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if color != (255, 255, 255, 255):
        source = ImageChops.multiply(source, Image.new("RGBA", source.size, color))
    source_width, source_height = source.size
    canvas_width, canvas_height = canvas_size
    min_x, min_y, max_x, max_y = world_bounds

    def source_to_canvas(u: float, v: float) -> tuple[float, float]:
        local_x = u - source_width / 2.0
        local_y = source_height / 2.0 - v
        world = _transform_resource_polygon([(local_x, local_y)], data)[0]
        return (
            (world[0] - min_x) * canvas_width / (max_x - min_x),
            (max_y - world[1]) * canvas_height / (max_y - min_y),
        )

    origin = source_to_canvas(0.0, 0.0)
    x_axis = source_to_canvas(1.0, 0.0)
    y_axis = source_to_canvas(0.0, 1.0)
    a, d = x_axis[0] - origin[0], x_axis[1] - origin[1]
    b, e = y_axis[0] - origin[0], y_axis[1] - origin[1]
    c, f = origin
    determinant = a * e - b * d
    if abs(determinant) < 1e-12:
        return None
    inverse = (
        e / determinant,
        -b / determinant,
        (b * f - e * c) / determinant,
        -d / determinant,
        a / determinant,
        (d * c - a * f) / determinant,
    )
    return source.transform(
        canvas_size,
        Image.Transform.AFFINE,
        inverse,
        resample=Image.Resampling.BICUBIC,
    )


def _render_polygons(polygons: list[dict], max_size: int = PREVIEW_MAX, transparent_background: bool = False) -> bytes | None:
    from PIL import Image, ImageDraw

    visible_items = [item for item in polygons if not item.get("mask")]
    bounds_items = visible_items or polygons
    all_points = [point for item in bounds_items for poly in item["polygons"] for point in poly]
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

    if not any(item.get("mask") for item in polygons):
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

    artwork = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for item in polygons:
        if item.get("mask"):
            cutout = Image.new("L", (width, height), 0)
            draw = ImageDraw.Draw(cutout)
            for poly in item["polygons"]:
                points = [to_canvas(point) for point in poly]
                if len(points) >= 3:
                    draw.polygon(points, fill=255)
            if cutout.getbbox():
                artwork.paste((0, 0, 0, 0), (0, 0, width, height), cutout)
            continue

        color = item["color"]
        if color[3] > 0:
            layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer, "RGBA")
            for poly in item["polygons"]:
                points = [to_canvas(point) for point in poly]
                if len(points) >= 3:
                    draw.polygon(points, fill=color)
            artwork = Image.alpha_composite(artwork, layer)

    image = artwork if transparent_background else Image.alpha_composite(_checkerboard((width, height)), artwork)
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
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        is_mask = _shape_mask_flag(shape, data)
        color = _color_tuple(shape.get("color"))
        if not is_mask and (not color or color[3] <= 0):
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
            polygons.append({"polygons": transformed, "color": color, "mask": is_mask})
    return _render_polygons(polygons, max_size=max_size, transparent_background=transparent_background) if polygons else None


def _rasterize_vertex_alpha_triangles(
    triangles: list[tuple[list[tuple[float, float]], tuple[int, int, int]]],
    bounds: tuple[int, int, int, int],
    color: tuple[int, int, int, int],
):
    """Rasterize native per-vertex opacity without losing gradient shape behavior."""

    import numpy as np
    from PIL import Image

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    coverage = np.zeros((height, width), dtype=np.float32)
    for points, vertex_alpha in triangles:
        if len(points) != 3:
            continue
        local = [(float(x) - left, float(y) - top) for x, y in points]
        x0, y0 = local[0]
        x1, y1 = local[1]
        x2, y2 = local[2]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denominator) < 1e-10:
            continue
        min_x = max(0, int(math.floor(min(x0, x1, x2))))
        max_x = min(width, int(math.ceil(max(x0, x1, x2))) + 1)
        min_y = max(0, int(math.floor(min(y0, y1, y2))))
        max_y = min(height, int(math.ceil(max(y0, y1, y2))) + 1)
        if min_x >= max_x or min_y >= max_y:
            continue
        xs = np.arange(min_x, max_x, dtype=np.float32) + 0.5
        ys = np.arange(min_y, max_y, dtype=np.float32)[:, None] + 0.5
        weight0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / denominator
        weight1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / denominator
        weight2 = 1.0 - weight0 - weight1
        inside = (weight0 >= -1e-5) & (weight1 >= -1e-5) & (weight2 >= -1e-5)
        interpolated = (
            weight0 * float(vertex_alpha[0])
            + weight1 * float(vertex_alpha[1])
            + weight2 * float(vertex_alpha[2])
        ) / 255.0
        region = coverage[min_y:max_y, min_x:max_x]
        np.maximum(region, np.where(inside, interpolated, 0.0), out=region)

    rgba = np.empty((height, width, 4), dtype=np.uint8)
    rgba[..., 0] = color[0]
    rgba[..., 1] = color[1]
    rgba[..., 2] = color[2]
    rgba[..., 3] = np.clip(
        np.rint(coverage * float(color[3])),
        0,
        255,
    ).astype(np.uint8)
    return Image.fromarray(rgba)


def render_typecode_layers_canvas(
    shapes: list[dict],
    width: int = 2048,
    height: int = 1024,
    world_bounds: tuple[float, float, float, float] = (-1024.0, -512.0, 1024.0, 512.0),
    raster_resolver: Callable[[int], object | None] | None = None,
    cancel_event=None,
    strict_assets: bool = False,
) -> bytes | None:
    """Render type-code layers without auto-cropping their Forza coordinate space."""
    from PIL import Image, ImageDraw

    width = max(1, min(8192, int(width)))
    height = max(1, min(8192, int(height)))
    min_x, min_y, max_x, max_y = [float(value) for value in world_bounds]
    if max_x <= min_x or max_y <= min_y:
        raise ValueError("world_bounds must describe a positive area")

    def to_canvas(point: tuple[float, float]) -> tuple[float, float]:
        return (
            (point[0] - min_x) * width / (max_x - min_x),
            (max_y - point[1]) * height / (max_y - min_y),
        )

    def layer_bounds(polygons: list[list[tuple[float, float]]]) -> tuple[int, int, int, int] | None:
        xs = [point[0] for polygon in polygons for point in polygon]
        ys = [point[1] for polygon in polygons for point in polygon]
        if not xs or not ys:
            return None
        left = max(0, math.floor(min(xs)) - 2)
        top = max(0, math.floor(min(ys)) - 2)
        right = min(width, math.ceil(max(xs)) + 3)
        bottom = min(height, math.ceil(max(ys)) + 3)
        return (left, top, right, bottom) if right > left and bottom > top else None

    def local_polygons(
        polygons: list[list[tuple[float, float]]],
        left: int,
        top: int,
    ) -> list[list[tuple[float, float]]]:
        return [[(x - left, y - top) for x, y in polygon] for polygon in polygons]

    artwork = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    artwork_draw = ImageDraw.Draw(artwork)
    rendered = False
    for shape_index, shape in enumerate(shapes):
        if shape_index % 32 == 0 and cancel_event is not None and cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        if not isinstance(shape, dict):
            continue
        data = list(shape.get("data") or [])
        if len(data) < 4:
            continue
        is_mask = _shape_mask_flag(shape, data)
        color = _color_tuple(shape.get("color"))
        if not is_mask and (not color or color[3] <= 0):
            continue
        try:
            [float(item) for item in data[:4]]
            type_code = int(shape.get("type", ROTATED_ELLIPSE))
        except (TypeError, ValueError):
            continue
        if shape.get("is_raster_logo"):
            if raster_resolver is None:
                if strict_assets:
                    raise ValueError(f"layer {shape_index + 1} needs a built-in raster decal resolver")
                continue
            try:
                raster_id = int(shape.get("raster_id") or 0)
                source = raster_resolver(raster_id) if raster_id > 0 else None
                # Built-in Forza decals retain their authored RGB. Placement
                # color contributes opacity, but it is not an RGB tint.
                raster_color = (255, 255, 255, color[3])
                layer = (
                    _render_raster_layer_canvas(
                        source, data, raster_color, (width, height), world_bounds
                    )
                    if source is not None
                    else None
                )
            except (TypeError, ValueError, OSError):
                layer = None
            if layer is None:
                if strict_assets:
                    raise ValueError(
                        f"layer {shape_index + 1} references unavailable raster decal {shape.get('raster_id')!r}"
                    )
                continue
            if is_mask:
                alpha = layer.getchannel("A")
                if alpha.getbbox():
                    artwork.paste((0, 0, 0, 0), (0, 0, width, height), alpha)
                    rendered = True
            else:
                artwork.alpha_composite(layer)
                rendered = True
            continue
        word = _shape_word_from_shape(shape, type_code)
        resource = _resolve_vinyl_resource(type_code, shape)
        alpha_triangles = _resource_alpha_triangles(*resource) if resource else None
        if not alpha_triangles:
            if strict_assets:
                identity = f"{resource[0]}/{resource[1]}" if resource else f"shape word 0x{word:04X}"
                raise ValueError(f"layer {shape_index + 1} has no exact native resource for {identity}")
            triangles = _resource_triangles(*resource) if resource else None
            if not triangles:
                triangles = _fallback_triangles(word)
            alpha_triangles = [(triangle, (255, 255, 255)) for triangle in triangles]
        transformed_alpha = [
            (_transform_resource_polygon(points, data), values)
            for points, values in alpha_triangles
        ]
        polygons = [points for points, _ in transformed_alpha]
        polygons = [[to_canvas(point) for point in polygon] for polygon in polygons if len(polygon) >= 3]
        if not polygons:
            if strict_assets:
                raise ValueError(f"layer {shape_index + 1} produced no native geometry")
            continue

        canvas_alpha = [
            (polygon, transformed_alpha[index][1])
            for index, polygon in enumerate(polygons)
        ]
        has_vertex_alpha = any(any(value != 255 for value in values) for _, values in canvas_alpha)
        if has_vertex_alpha:
            bounds = layer_bounds(polygons)
            if bounds is None:
                # Section textures are clipped views. A valid placement can
                # sit completely outside one view and should be clipped, not
                # reported as a missing or invalid native asset.
                continue
            gradient_layer = _rasterize_vertex_alpha_triangles(canvas_alpha, bounds, color)
            gradient_alpha = gradient_layer.getchannel("A")
            if gradient_alpha.getbbox() is None:
                # Native gradients can legitimately resolve to zero alpha. They
                # are visual no-ops, not missing geometry or invalid assets.
                continue
            if is_mask:
                artwork.paste((0, 0, 0, 0), bounds, gradient_alpha)
            else:
                artwork.alpha_composite(gradient_layer, dest=(bounds[0], bounds[1]))
            rendered = True
            continue

        if is_mask:
            bounds = layer_bounds(polygons)
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            cutout = Image.new("L", (right - left, bottom - top), 0)
            draw = ImageDraw.Draw(cutout)
            for polygon in local_polygons(polygons, left, top):
                draw.polygon(polygon, fill=255)
            if cutout.getbbox():
                artwork.paste((0, 0, 0, 0), bounds, cutout)
                rendered = True
            continue

        if color[3] == 255:
            for polygon in polygons:
                artwork_draw.polygon(polygon, fill=color)
        else:
            bounds = layer_bounds(polygons)
            if bounds is None:
                continue
            left, top, right, bottom = bounds
            layer = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer, "RGBA")
            for polygon in local_polygons(polygons, left, top):
                draw.polygon(polygon, fill=color)
            artwork.alpha_composite(layer, dest=(left, top))
        rendered = True

    if not rendered:
        return None
    if cancel_event is not None and cancel_event.is_set():
        raise concurrent.futures.CancelledError()
    out = io.BytesIO()
    artwork.save(out, format="PNG", optimize=False)
    return out.getvalue()
