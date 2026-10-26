"""Read-only extraction of FH3 vinyl files into KFPS documents.

Format references and independent-implementation provenance: docs/FH3-OFFLINE.md.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .forza_source_decoder import cgroup_to_layers, enforce_privacy, layers_to_kfps_json_layers
from .vinyl_document import MAX_LAYERS

GAMES = {"fh3": 1}
MAX_CONTAINER = 16 * 1024 * 1024
MAX_PAYLOAD = 8 * 1024 * 1024


def _version(game: str) -> int:
    if game not in GAMES:
        raise ValueError("This file workflow supports FH3 only.")
    return GAMES[game]


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{path.name} exceeds the file size limit.")
    return raw


@dataclass(frozen=True)
class LegacyHeader:
    version: int
    title: str
    creator: str
    creator_id: int
    count: int
    asset_id: bytes


def parse_header(raw: bytes, game: str) -> LegacyHeader:
    version = _version(game)
    if not 4 <= len(raw) <= 65536 or struct.unpack_from("<I", raw)[0] != version:
        raise ValueError(f"Select an extracted {game.upper()} vinyl header (version {version}).")
    offset = 4

    def take(size: int) -> bytes:
        nonlocal offset
        end = offset + size
        if end > len(raw):
            raise ValueError("Truncated legacy vinyl header.")
        value, offset = raw[offset:end], end
        return value

    def string() -> str:
        count = struct.unpack("<I", take(4))[0]
        if count > 4096:
            raise ValueError("Excessive legacy header string length.")
        try:
            value = take(count * 2).decode("utf-16le")
        except UnicodeError as exc:
            raise ValueError("Invalid legacy header text.") from exc
        if any(ord(char) < 32 for char in value):
            raise ValueError("Control characters in legacy header text.")
        return value

    title, description = string(), string()
    fields = take(28)
    kind, creator_id = struct.unpack_from("<IQ", fields, 16)
    creator = string()
    if description or kind != 2 or not creator_id or not creator.strip():
        raise ValueError("Only an owned, unpublished vinyl-group header is supported; not a full livery.")
    take(16 + version)
    count = struct.unpack("<I", take(4))[0]
    asset_id = take(8)
    if not 1 <= count <= MAX_LAYERS or not any(asset_id):
        raise ValueError("Invalid legacy vinyl count or asset identity.")
    return LegacyHeader(version, title, creator, creator_id, count, asset_id)


def read_payload(path: Path) -> bytes:
    raw = _read(path, MAX_CONTAINER)
    if raw.startswith(b"gyvl"):
        if len(raw) > MAX_PAYLOAD:
            raise ValueError("Legacy vinyl exceeds the decompressed size limit.")
        return raw
    if len(raw) < 8:
        raise ValueError("Truncated legacy vinyl container.")
    compressed, expected = struct.unpack_from("<II", raw)
    if compressed != len(raw) - 8 or not 0 < expected <= MAX_PAYLOAD:
        raise ValueError("Invalid legacy vinyl container size.")
    decoder = zlib.decompressobj()
    try:
        payload = decoder.decompress(raw[8:], expected + 1)
    except zlib.error as exc:
        raise ValueError("Invalid legacy vinyl compression.") from exc
    if (len(payload) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail):
        raise ValueError("Incomplete, oversized or trailing legacy vinyl data.")
    return payload


def read_vinyl(source: Path, game: str, *, header_path: Path | None = None) -> tuple[dict, dict, LegacyHeader | None]:
    """Read only; deliberately does not discover or write a game account."""
    _version(game)
    if source.is_dir():
        source = source / "C_group"
    payload = read_payload(source)
    generations = (1, 2)
    if len(payload) < 37 or payload[:12] != b"gyvl\x01\0\0\0\0\0\0\0" or payload[12] not in generations:
        raise ValueError(f"Not a supported {game.upper()} standalone vinyl group; full liveries are not supported.")
    enforce_privacy(source, "cgroup", payload, allow_locked=False)
    layers, report = cgroup_to_layers(payload, game)
    if (report["warnings"] or not 1 <= len(layers) <= MAX_LAYERS
            or report["max_group_depth"] > 64 or any(layer["mask"] for layer in layers)):
        raise ValueError("The legacy vinyl contains incomplete, unsupported or masked records; no partial import was made.")
    shapes, identity_warnings = layers_to_kfps_json_layers(layers, game)
    header_path = header_path if header_path is not None else source.parent / "header"
    identity = parse_header(_read(header_path, 65536), game) if header_path.is_file() else None
    if identity and identity.count != len(shapes):
        raise ValueError("The legacy header count does not match its vinyl. Select a matching extracted pair.")
    document = {"format": "kfps_forza_save_library_json_v1", "target_game": game,
                "source_kind": "cgroup", "source_path": str(source),
                "metadata": {"title": identity.title if identity else source.parent.name,
                             "target_game": game, "asset_type": "vinyl_group", "layers": len(shapes)},
                "shapes": shapes}
    report = {**report, "game": game, "experimental": True, "identity_warnings": identity_warnings}
    return document, report, identity


def _check_cancel(cancel) -> None:
    if cancel is not None and cancel():
        raise ValueError("Vinyl extraction cancelled; no Library entry was written.")
