"""Convert generated primitives only at the file-import boundary."""
from copy import deepcopy

from .model import MAX_SHAPES, TYPE_BASE, ValidationError, _number, validate_shapes


def import_shapes(payload, resolve_resource):
    from tools.cgroup.cgroup_codec import (
        LEGACY_RECTANGLE_TYPES, LEGACY_ELLIPSE_TYPES, LEGACY_RECTANGLE_WORD,
        LEGACY_ELLIPSE_WORD, LEGACY_RECTANGLE_DIVISOR, LEGACY_ELLIPSE_DIVISOR,
    )

    if not isinstance(payload, dict) or set(payload) != {"shapes"}:
        raise ValidationError("Expected an object containing only shapes.")
    shapes = payload["shapes"]
    if not isinstance(shapes, list) or not 1 <= len(shapes) <= MAX_SHAPES + 1:
        raise ValidationError("A vinyl must contain 1 to 3000 native shapes.")
    legacy, bounds = {}, []
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise ValidationError(f"Shape {index + 1} must be an object.")
        kind = shape.get("type")
        if type(kind) is not int or kind not in LEGACY_RECTANGLE_TYPES | LEGACY_ELLIPSE_TYPES:
            continue
        # A legacy ID must never override an explicit native/raster identity.
        if any(key in shape for key in ("type_word", "typeWord", "shape_word", "shapeWord",
                "font_shape", "fontShape", "resource_family", "resourceFamily", "raster_id", "is_raster_logo")):
            raise ValidationError("Generated shape has conflicting native identity.")
        data = shape.get("data")
        if not isinstance(data, list) or not 4 <= len(data) <= 7:
            raise ValidationError("Generated shape needs [x,y,width,height,rotation?,skew?,mask?].")
        values = [_number(item, "Generated shape transform") for item in data[:6]]
        values += [0.0] * (6 - len(values))
        x, y, width, height, rotation, skew = values
        if max(abs(x), abs(y), abs(width), abs(height)) >= 50000 or abs(rotation) > 10000 or abs(skew) >= 200:
            raise ValidationError("Placement position exceeds the decoder bounds.")
        word = LEGACY_RECTANGLE_WORD if kind in LEGACY_RECTANGLE_TYPES else LEGACY_ELLIPSE_WORD
        divisor = LEGACY_RECTANGLE_DIVISOR if kind in LEGACY_RECTANGLE_TYPES else LEGACY_ELLIPSE_DIVISOR
        native = {**deepcopy(shape), "type": TYPE_BASE + word,
                  "data": [x, -y, width / divisor, height / divisor,
                           (360.0 - rotation) % 360 if kind in (2, 16) else 0.0, skew,
                           *data[6:]]}
        # Reuse native validation for colours, masks, resources and scale limits.
        validate_shapes({"shapes": [native]}, resolve_resource)
        legacy[index] = native
        bounds.append((x - abs(width) / 2, y - abs(height) / 2,
                       x + abs(width) / 2, y + abs(height) / 2))
    offset_x = (min(b[0] for b in bounds) + max(b[2] for b in bounds)) / 2 if bounds else 0
    offset_y = (min(b[1] for b in bounds) + max(b[3] for b in bounds)) / 2 if bounds else 0
    result = []
    for index, shape in enumerate(shapes):
        native = legacy.get(index)
        if native is None:
            result.append(deepcopy(shape))
            continue
        # Match the Vinyl Editor's generated-canvas centering and leading spacer.
        masked = native.get("mask", len(native["data"]) == 7 and native["data"][6] == 1)
        if index == 0 and shape["type"] == 1 and shape["color"][3] == 0 and not masked:
            continue
        native["data"][0] -= offset_x
        native["data"][1] += offset_y
        result.append(native)
    validate_shapes({"shapes": result}, resolve_resource)
    return {"shapes": result}
