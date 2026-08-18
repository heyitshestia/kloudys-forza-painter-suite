from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

from kfps_shapes import (
    SchemaDetection,
    convert_fd6_payload,
    detect_payload_schema as detect_canonical_payload_schema,
    is_fd6_payload,
    shape_list,
)

from .qt_utils import file_url


MAX_JSON_BYTES = 24 * 1024 * 1024
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_SHAPES = 3001
THUMBNAIL_SIZE = 480
FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}
UNKNOWN_SCHEMA_WARNING = (
    "This JSON uses a format KFPS does not recognize. Its shape list passed structural checks, "
    "but import compatibility may vary."
)
CommunitySchemaDetection = SchemaDetection


@dataclass
class CommunityUploadInspection:
    path: str
    display_name: str
    shape_count: int
    size_bytes: int
    payload: object
    preview_bytes: bytes
    thumbnail_bytes: bytes
    preview_url: str
    source_sha256: str
    schema_id: str
    schema_label: str
    schema_known: bool
    detected_games: tuple[str, ...]
    schema_warning: str
    normalization_note: str


def _reject_constant(value):
    raise ValueError(f"unsupported JSON number: {value}")


def _shape_list(payload):
    return shape_list(payload)


def detect_payload_schema(payload, shapes=None) -> CommunitySchemaDetection:
    return detect_canonical_payload_schema(payload, shapes)


def _validate_value(value, depth=0, nodes=None):
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > 100_000 or depth > 14:
        raise ValueError("The JSON is too deeply nested or complex.")
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_KEYS:
                raise ValueError("The JSON contains a forbidden object key.")
            _validate_value(child, depth + 1, nodes)
    elif isinstance(value, list):
        for child in value:
            _validate_value(child, depth + 1, nodes)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("The JSON contains a non-finite number.")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError("The JSON contains an unsupported value.")


def validate_payload(payload) -> int:
    _validate_value(payload)
    shapes = _shape_list(payload)
    if not 1 <= len(shapes) <= MAX_SHAPES:
        raise ValueError(f"Community JSONs must contain between 1 and {MAX_SHAPES} shapes.")
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise ValueError(f"Shape {index + 1} is not an object.")
        shape_type = shape.get("type")
        data = shape.get("data")
        color = shape.get("color")
        if isinstance(shape_type, bool) or not isinstance(shape_type, int) or not 0 <= shape_type <= 2_000_000:
            raise ValueError(f"Shape {index + 1} has an invalid type.")
        if not isinstance(data, list) or not 4 <= len(data) <= 12:
            raise ValueError(f"Shape {index + 1} has invalid geometry data.")
        if not isinstance(color, list) or not 3 <= len(color) <= 4:
            raise ValueError(f"Shape {index + 1} has an invalid color.")
        for number in data:
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError(f"Shape {index + 1} contains an invalid number.")
            if not -1_000_000 <= number <= 1_000_000:
                raise ValueError(f"Shape {index + 1} contains geometry outside the supported range.")
        for number in color:
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
                raise ValueError(f"Shape {index + 1} contains an invalid color number.")
            if not 0 <= number <= 255:
                raise ValueError(f"Shape {index + 1} contains a color outside the supported range.")
        type_word = shape.get("type_word", shape.get("typeWord", shape.get("shape_word", shape.get("shapeWord"))))
        if type_word is not None and (
            isinstance(type_word, bool) or not isinstance(type_word, int) or not 0 <= type_word <= 65535
        ):
            raise ValueError(f"Shape {index + 1} has an invalid type word.")
    return len(shapes)


def inspect_upload(path: str | Path, runtime_root: Path) -> CommunityUploadInspection:
    source = Path(path)
    if not source.is_file() or source.suffix.lower() != ".json":
        raise ValueError("Choose an existing JSON file.")
    with source.open("rb") as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    size = len(raw)
    if size < 2 or size > MAX_JSON_BYTES:
        raise ValueError("The JSON is empty or exceeds the 24 MB upload limit.")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except Exception as exc:
        raise ValueError("The selected file is not valid UTF-8 JSON.") from exc
    digest = hashlib.sha256(raw).hexdigest()
    render_source = source
    normalization_note = ""
    if is_fd6_payload(payload):
        try:
            payload, converted_count, skipped_count = convert_fd6_payload(payload, source)
        except Exception as exc:
            raise ValueError(f"KFPS could not convert this Forza Designer 6 JSON: {exc}") from exc
        normalized = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8") + b"\n"
        normalized_root = Path(runtime_root) / "community" / "upload-normalized"
        render_source = normalized_root / f"{digest[:24]}.fd6-converted.json"
        render_source.parent.mkdir(parents=True, exist_ok=True)
        normalized_temporary = render_source.with_suffix(render_source.suffix + ".tmp")
        normalized_temporary.write_bytes(normalized)
        os.replace(normalized_temporary, render_source)
        normalization_note = f"Converted {converted_count} FD6 shapes in the background"
        if skipped_count:
            normalization_note += f"; skipped {skipped_count} unsupported or invisible shapes"
        normalization_note += ". The original file was not changed."
    count = validate_payload(payload)
    schema = detect_payload_schema(payload, _shape_list(payload))
    try:
        from json_preview_renderer import render_json_preview

        preview = b""
        for max_size in (1400, 1100, 900):
            preview = render_json_preview(render_source, max_size=max_size, transparent_background=True)
            if preview and len(preview) <= MAX_PREVIEW_BYTES:
                break
    except Exception as exc:
        raise ValueError(f"KFPS could not render the community preview: {exc}") from exc
    if not preview or len(preview) > MAX_PREVIEW_BYTES or not preview.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("KFPS could not produce a valid PNG preview for this JSON.")
    image = QImage.fromData(preview, "PNG")
    if image.isNull():
        raise ValueError("KFPS could not decode the rendered community preview.")
    scaled_thumbnail = image.scaled(
        THUMBNAIL_SIZE,
        THUMBNAIL_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    thumbnail_image = QImage(
        THUMBNAIL_SIZE,
        THUMBNAIL_SIZE,
        QImage.Format.Format_RGBA8888,
    )
    thumbnail_image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(thumbnail_image)
    try:
        painter.drawImage(
            (THUMBNAIL_SIZE - scaled_thumbnail.width()) // 2,
            (THUMBNAIL_SIZE - scaled_thumbnail.height()) // 2,
            scaled_thumbnail,
        )
    finally:
        painter.end()
    thumbnail_buffer = QBuffer()
    if not thumbnail_buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not thumbnail_image.save(thumbnail_buffer, "PNG"):
        raise ValueError("KFPS could not produce the community thumbnail.")
    thumbnail = bytes(thumbnail_buffer.data())
    thumbnail_buffer.close()
    if not thumbnail or len(thumbnail) > 512 * 1024:
        raise ValueError("The generated community thumbnail exceeds the upload limit.")
    target = Path(runtime_root) / "community" / "upload-previews" / f"{digest[:24]}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(preview)
    os.replace(temporary, target)
    display = source.stem
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        meta = payload["metadata"]
        display = str(meta.get("display_name") or meta.get("title") or display).strip() or display
    return CommunityUploadInspection(
        path=str(source.resolve()),
        display_name=display[:80],
        shape_count=count,
        size_bytes=size,
        payload=payload,
        preview_bytes=preview,
        thumbnail_bytes=thumbnail,
        preview_url=file_url(target),
        source_sha256=digest,
        schema_id=schema.schema_id,
        schema_label=schema.label,
        schema_known=schema.known,
        detected_games=schema.games,
        schema_warning="" if schema.known else UNKNOWN_SCHEMA_WARNING,
        normalization_note=normalization_note,
    )


def validate_download(raw: bytes, expected_sha256: str = "") -> dict:
    if not 2 <= len(raw) <= MAX_JSON_BYTES:
        raise ValueError("The downloaded JSON has an invalid size.")
    actual = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and actual.lower() != expected_sha256.lower():
        raise ValueError("The downloaded JSON checksum does not match the catalog.")
    try:
        payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except Exception as exc:
        raise ValueError("The downloaded file is not valid UTF-8 JSON.") from exc
    validate_payload(payload)
    if not isinstance(payload, dict) or payload.get("format") != "kfps.community.v1":
        raise ValueError("The downloaded file is not a canonical KFPS community JSON.")
    return payload
