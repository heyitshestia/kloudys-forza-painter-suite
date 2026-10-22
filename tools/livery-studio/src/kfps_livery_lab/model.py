"""Strict native-vector input and baseline rendering adapter."""

from __future__ import annotations

import base64
import io
import json
import math
from typing import Callable

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_SHAPES = 3000
SECTION_SIZE = (2048, 1024)
WORLD_BOUNDS = (-1024.0, -512.0, 1024.0, 512.0)
TYPE_BASE = 0x100000
DEFAULT_PREVIEW_QUALITY = "balanced"
PREVIEW_SIZES = {"fast": (1024, 512), "balanced": SECTION_SIZE, "sharp": (4096, 2048)}


class ValidationError(ValueError):
    pass


def validate_preview_quality(value):
    if not isinstance(value, str) or value not in PREVIEW_SIZES:
        raise ValidationError("Preview quality must be fast, balanced or sharp.")
    return value


def decode_json(body: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError("Duplicate JSON field.")
            result[key] = value
        return result

    def constant(_value):
        raise ValidationError("Non-finite JSON numbers are not allowed.")

    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValidationError("Invalid UTF-8 JSON or duplicate/non-finite fields.") from exc


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValidationError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValidationError(f"{label} must be a finite number.")
    return result


def validate_shapes(payload: object, resolve_resource: Callable) -> list[dict]:
    if not isinstance(payload, dict) or set(payload) != {"shapes"}:
        raise ValidationError("Expected an object containing only shapes.")
    shapes = payload["shapes"]
    if not isinstance(shapes, list) or not 1 <= len(shapes) <= MAX_SHAPES:
        raise ValidationError("A vinyl must contain 1 to 3000 native shapes.")
    result = []
    for index, shape in enumerate(shapes, 1):
        if not isinstance(shape, dict):
            raise ValidationError(f"Shape {index} must be an object.")
        kind = shape.get("type")
        if type(kind) is not int or not TYPE_BASE <= kind <= TYPE_BASE + 0x7FFF:
            raise ValidationError(f"Shape {index} needs a native Forza type code.")
        if shape.get("is_raster_logo") or shape.get("raster_id"):
            raise ValidationError("Raster decals are not supported by the vector import API.")
        if "type_word" in shape and (type(shape["type_word"]) is not int or shape["type_word"] != kind - TYPE_BASE):
            raise ValidationError(f"Shape {index} has conflicting native identity.")
        data = shape.get("data")
        if not isinstance(data, list) or not 5 <= len(data) <= 7:
            raise ValidationError(f"Shape {index} needs [x,y,sx,sy,rotation,skew?,mask?].")
        values = [_number(item, f"Shape {index} transform") for item in data[:6]]
        if len(values) == 5:
            values.append(0.0)
        x, y, sx, sy, rotation, skew = values
        if abs(x) >= 50000 or abs(y) >= 50000:
            raise ValidationError("Placement position exceeds the decoder bounds.")
        if not (1e-6 < abs(sx) < 200 and 1e-6 < abs(sy) < 200):
            raise ValidationError("Placement scale exceeds the decoder bounds or is degenerate.")
        if abs(rotation) > 10000 or abs(skew) >= 200:
            raise ValidationError("Placement rotation or skew exceeds the decoder bounds.")
        embedded_mask = data[6] if len(data) == 7 else None
        if embedded_mask is not None and (type(embedded_mask) not in (int, float) or embedded_mask not in (0, 1)):
            raise ValidationError("Mask data must be numeric 0 or 1.")
        mask = shape.get("mask", bool(embedded_mask))
        if type(mask) is not bool or (embedded_mask is not None and mask != bool(embedded_mask)):
            raise ValidationError("Mask fields disagree or are not boolean.")
        color = shape.get("color")
        if not isinstance(color, list) or len(color) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in color):
            raise ValidationError("Color must be four RGBA integers from 0 to 255.")
        # Resolve from authoritative type only; untrusted resource labels cannot redirect reads.
        resource = resolve_resource(kind)
        if not resource:
            raise ValidationError(f"Shape {index} has no exact native resource.")
        result.append({"type": kind, "type_word": kind - TYPE_BASE,
                       "data": [*values, int(mask)], "color": list(color), "mask": mask})
    return result


class NativeVinylRenderer:
    def __init__(self):
        import json_preview_renderer as baseline
        self.baseline = baseline

    def _resource(self, kind):
        resource = self.baseline._resolve_vinyl_resource(kind, {"type": kind})
        if not resource or not self.baseline._resource_alpha_triangles(*resource):
            return None
        return resource

    def _render_canvas(self, shapes, size):
        from PIL import Image
        try:
            png = self.baseline.render_typecode_layers_canvas(
                shapes, width=size[0], height=size[1],
                world_bounds=WORLD_BOUNDS, strict_assets=True,
            )
            if not png:
                buffer = io.BytesIO()
                Image.new("RGBA", size, (0, 0, 0, 0)).save(buffer, format="PNG")
                png = buffer.getvalue()
            with Image.open(io.BytesIO(png)) as image:
                if image.format != "PNG" or image.size != size:
                    raise ValidationError("Renderer returned an invalid section texture.")
                bounds = image.convert("RGBA").getchannel("A").getbbox()
        except (ValueError, OSError) as exc:
            raise ValidationError("Native vinyl could not be rendered exactly.") from exc
        return png, bounds

    def _coverage_shapes(self, shapes):
        coverage=[]
        for shape in shapes:
            alpha=shape["color"][3]
            if shape["mask"]:
                resource=self.baseline._resolve_vinyl_resource(shape["type"],shape)
                triangles=self.baseline._resource_alpha_triangles(*resource)
                # Match the native renderer: solid cutouts ignore paint opacity;
                # native vertex-alpha shapes use their authored alpha coverage.
                if not any(value!=255 for _,values in triangles for value in values):
                    alpha=255
            coverage.append({**shape,"data":[*shape["data"][:6],0],
                             "mask":False,"color":[255,255,255,alpha]})
        return coverage

    def __call__(self, payload):
        if (not isinstance(payload, dict) or "shapes" not in payload
                or set(payload) - {"shapes", "preview_quality"}):
            raise ValidationError("Expected shapes and optional preview_quality only.")
        quality = validate_preview_quality(payload.get("preview_quality", DEFAULT_PREVIEW_QUALITY))
        shapes = validate_shapes({"shapes": payload["shapes"]}, self._resource)
        size = PREVIEW_SIZES[quality]
        # Picking uses the original alpha bounds, including masks, clipping and
        # subpixel coverage. Scaling another resolution's bbox is not equivalent.
        png, bounds = self._render_canvas(shapes, SECTION_SIZE)
        if size != SECTION_SIZE:
            png, _ = self._render_canvas(shapes, size)
        result={"png": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                "width": size[0], "height": size[1],
                "shapes": shapes, "bounds": list(bounds) if bounds else None}
        if any(shape["mask"] for shape in shapes):
            # Any ordered source-over/destination-out stream is C + T*background.
            # C is the existing transparent render; coverage is 1-T. Keeping both
            # preserves cutouts across source boundaries, without per-drag vectors.
            coverage=self._coverage_shapes(shapes)
            erase,mask_bounds=self._render_canvas(coverage,SECTION_SIZE)
            if size!=SECTION_SIZE:
                erase,_=self._render_canvas(coverage,size)
            result.update(mask_compositing="ordered-section-v1",
                          mask_coverage_png="data:image/png;base64,"+base64.b64encode(erase).decode("ascii"),
                          mask_bounds=list(mask_bounds) if mask_bounds else None)
        return result
