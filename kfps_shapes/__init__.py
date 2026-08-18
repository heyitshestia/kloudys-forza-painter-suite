"""Canonical KFPS vinyl JSON contracts shared by every app surface."""

from .fd6 import FD6_FORMAT, convert_fd6_payload, is_fd6_payload
from .resources import (
    resolve_full_type_resource,
    resolve_vinyl_resource,
    shape_word_from_shape,
    shape_word_resource_map,
)
from .schema import (
    SchemaDetection,
    detect_payload_schema,
    payload_uses_typecodes,
    shape_list,
)

__all__ = [
    "FD6_FORMAT",
    "SchemaDetection",
    "convert_fd6_payload",
    "detect_payload_schema",
    "is_fd6_payload",
    "payload_uses_typecodes",
    "resolve_full_type_resource",
    "resolve_vinyl_resource",
    "shape_list",
    "shape_word_from_shape",
    "shape_word_resource_map",
]
