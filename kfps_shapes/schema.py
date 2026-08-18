from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PRIMITIVE_TYPES = {1, 2, 8, 16}
FORMAT_CATALOG = {
    "kfps.community.v1": ("kfps-community", "KFPS Community JSON", ()),
    "kfps.primitive.v1": ("kfps-primitives", "KFPS primitive geometry", ()),
    "fh6_typecode_json_export_v1": ("forza-typecode-export", "Forza live type-code export", ()),
    "kfps_forza_save_library_json_v1": ("forza-save-library", "KFPS Forza save-library export", ()),
    "kfps_forza_file_export_json_v1": ("forza-file-export", "KFPS decoded Forza file export", ()),
    "kfps_cgroup_flat_json_v1": ("kfps-cgroup-flat", "KFPS flat C_group JSON", ()),
    "kfps.fd6.converted.v1": ("fd6-converted", "Forza Designer 6 conversion", ("FH6",)),
    "fd6.shapes": ("fd6-source", "Forza Designer 6 source", ("FH6",)),
}


@dataclass(frozen=True)
class SchemaDetection:
    schema_id: str
    label: str
    known: bool
    games: tuple[str, ...]


def shape_list(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("The selected file does not contain a JSON object or shape list.")
    for key in ("shapes", "layers", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    raise ValueError("The selected JSON does not contain a supported shape list.")


def _object(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def normalize_game(value: Any) -> str:
    key = "".join(character for character in str(value or "").strip().lower() if character.isalnum())
    if key in {"fh4", "forzahorizon4", "horizon4"}:
        return "FH4"
    if key in {"fh5", "forzahorizon5", "horizon5"}:
        return "FH5"
    if key in {"fh6", "forzahorizon6", "horizon6"}:
        return "FH6"
    if key in {"fm", "fm8", "forzamotorsport", "forzamotorsport8", "motorsport"}:
        return "FM8"
    return ""


def game_origins(payload: Any) -> list[str]:
    root = _object(payload)
    metadata = _object(root.get("metadata"))
    source = _object(root.get("source"))
    candidates = [
        root.get("target_game"),
        root.get("game"),
        metadata.get("target_game"),
        metadata.get("game"),
        source.get("target_game"),
        source.get("game"),
    ]
    for container in (root, metadata, source):
        for key in ("detected_games", "games"):
            values = container.get(key)
            if isinstance(values, list):
                candidates.extend(values)
    games = []
    for candidate in candidates:
        game = normalize_game(candidate)
        if game and game not in games:
            games.append(game)
    return games


def payload_uses_typecodes(payload: Any, shapes: list | None = None) -> bool:
    try:
        rows = shape_list(payload) if shapes is None else shapes
    except ValueError:
        return False
    for shape in rows:
        if not isinstance(shape, dict):
            continue
        if str(shape.get("source_format") or "").strip().lower() == "fh6_typecode":
            return True
        if any(
            key in shape
            for key in (
                "type_word",
                "typeWord",
                "shape_word",
                "shapeWord",
                "resource_family",
                "resourceFamily",
                "resource_index",
                "resourceIndex",
            )
        ):
            return True
        try:
            if int(shape.get("type", 0)) > 1_000_000:
                return True
        except (TypeError, ValueError):
            continue
    return False


def detect_payload_schema(payload: Any, shapes: list | None = None) -> SchemaDetection:
    rows = shape_list(payload) if shapes is None else shapes
    root = _object(payload)
    source_format = str(root.get("format") or "").strip().lower()
    games = game_origins(payload)
    known = FORMAT_CATALOG.get(source_format)
    if known:
        schema_id, label, defaults = known
        for game in defaults:
            if game not in games:
                games.append(game)
        if source_format == "fh6_typecode_json_export_v1" and not games:
            games.append("FH6")
        return SchemaDetection(schema_id, label, True, tuple(games))

    objects = [shape for shape in rows if isinstance(shape, dict)]
    source_formats = {str(shape.get("source_format") or "").strip().lower() for shape in objects}
    primitive_geometry = bool(objects) and len(objects) == len(rows) and all(
        shape.get("type") in PRIMITIVE_TYPES
        and isinstance(shape.get("data"), list)
        and isinstance(shape.get("color"), list)
        for shape in objects
    )
    if source_format:
        safe = source_format if len(source_format) <= 64 and all(
            character.isalnum() or character in "._-" for character in source_format
        ) else ""
        label = f"Unrecognized format: {safe}" if safe else "Unrecognized JSON format"
        return SchemaDetection("unrecognized", label, False, tuple(games))
    if "fh6_typecode" in source_formats:
        if "FH6" not in games:
            games.append("FH6")
        return SchemaDetection("fh6-typecode", "FH6 type-code geometry", True, tuple(games))
    if payload_uses_typecodes(payload, rows):
        return SchemaDetection("forza-typecode", "Forza type-code geometry", True, tuple(games))
    if primitive_geometry:
        return SchemaDetection("kfps-primitives", "KFPS primitive geometry", True, tuple(games))
    return SchemaDetection("unrecognized", "Unrecognized compatible shape list", False, tuple(games))
