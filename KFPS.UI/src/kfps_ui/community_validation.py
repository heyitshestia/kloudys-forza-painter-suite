from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

from .qt_utils import file_url


MAX_JSON_BYTES = 24 * 1024 * 1024
MAX_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_SHAPES = 3001
FORBIDDEN_KEYS = {"__proto__", "prototype", "constructor"}
PRIMITIVE_TYPES = {1, 2, 8, 16}
UNKNOWN_SCHEMA_WARNING = (
    "This JSON uses a format KFPS does not recognize. Its shape list passed structural checks, "
    "but import compatibility may vary."
)
KNOWN_FORMATS = {
    "kfps.community.v1": ("kfps-community", "KFPS Community JSON", ()),
    "kfps.primitive.v1": ("kfps-primitives", "KFPS primitive geometry", ()),
    "fh6_typecode_json_export_v1": ("forza-typecode-export", "Forza live type-code export", ()),
    "kfps_forza_save_library_json_v1": ("forza-save-library", "KFPS Forza save-library export", ()),
    "kfps_forza_file_export_json_v1": ("forza-file-export", "KFPS decoded Forza file export", ()),
    "kfps_cgroup_flat_json_v1": ("kfps-cgroup-flat", "KFPS flat C_group JSON", ()),
    "kfps.fd6.converted.v1": ("fd6-converted", "Forza Designer 6 conversion", ("FH6",)),
}


@dataclass(frozen=True)
class CommunitySchemaDetection:
    schema_id: str
    label: str
    known: bool
    games: tuple[str, ...]


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
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("The selected file does not contain a JSON object or shape list.")
    for key in ("shapes", "layers", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    raise ValueError("The selected JSON does not contain a supported shape list.")


def _object_value(value):
    return value if isinstance(value, dict) else {}


def _normalize_game(value):
    key = "".join(character for character in str(value or "").strip().lower() if character.isalnum())
    if key in {"fh5", "forzahorizon5", "horizon5"}:
        return "FH5"
    if key in {"fh6", "forzahorizon6", "horizon6"}:
        return "FH6"
    if key in {"fm", "fm8", "forzamotorsport", "forzamotorsport8", "motorsport"}:
        return "FM8"
    return ""


def _game_origins(payload):
    root = _object_value(payload)
    metadata = _object_value(root.get("metadata"))
    source = _object_value(root.get("source"))
    candidates = [
        root.get("target_game"), root.get("game"),
        metadata.get("target_game"), metadata.get("game"),
        source.get("target_game"), source.get("game"),
    ]
    for container in (root, metadata, source):
        for key in ("detected_games", "games"):
            values = container.get(key)
            if isinstance(values, list):
                candidates.extend(values)
    games = []
    for candidate in candidates:
        game = _normalize_game(candidate)
        if game and game not in games:
            games.append(game)
    return games


def detect_payload_schema(payload, shapes=None) -> CommunitySchemaDetection:
    shapes = _shape_list(payload) if shapes is None else shapes
    root = _object_value(payload)
    source_format = str(root.get("format") or "").strip().lower()
    games = _game_origins(payload)
    known = KNOWN_FORMATS.get(source_format)
    if known:
        schema_id, label, default_games = known
        for game in default_games:
            if game not in games:
                games.append(game)
        if source_format == "fh6_typecode_json_export_v1" and not games:
            games.append("FH6")
        return CommunitySchemaDetection(schema_id, label, True, tuple(games))

    rows = [shape for shape in shapes if isinstance(shape, dict)]
    row_source_formats = {str(shape.get("source_format") or "").strip().lower() for shape in rows}
    fh6_type_codes = "fh6_typecode" in row_source_formats
    type_code_geometry = any(
        int(shape.get("type") or 0) > 1_000_000
        or any(key in shape for key in ("type_word", "typeWord", "shape_word", "shapeWord", "resource_family", "resource_index"))
        for shape in rows
    )
    primitive_geometry = bool(rows) and len(rows) == len(shapes) and all(
        shape.get("type") in PRIMITIVE_TYPES
        and isinstance(shape.get("data"), list)
        and isinstance(shape.get("color"), list)
        for shape in rows
    )

    if source_format:
        safe_format = source_format if len(source_format) <= 64 and all(
            character.isalnum() or character in "._-" for character in source_format
        ) else ""
        label = f"Unrecognized format: {safe_format}" if safe_format else "Unrecognized JSON format"
        return CommunitySchemaDetection("unrecognized", label, False, tuple(games))
    if fh6_type_codes:
        if "FH6" not in games:
            games.append("FH6")
        return CommunitySchemaDetection("fh6-typecode", "FH6 type-code geometry", True, tuple(games))
    if type_code_geometry:
        return CommunitySchemaDetection("forza-typecode", "Forza type-code geometry", True, tuple(games))
    if primitive_geometry:
        return CommunitySchemaDetection("kfps-primitives", "KFPS primitive geometry", True, tuple(games))
    return CommunitySchemaDetection("unrecognized", "Unrecognized compatible shape list", False, tuple(games))


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
    if isinstance(payload, dict) and str(payload.get("format") or "").strip().lower() == "fd6.shapes":
        try:
            from .json_service import JsonService

            payload, converted_count, skipped_count = JsonService._convert_fd6_payload(payload, source)
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
    thumbnail_image = image.scaled(
        480,
        480,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
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
