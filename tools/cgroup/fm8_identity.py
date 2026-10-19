"""Version-9 metadata for creating a fresh, locally owned FM8 vinyl group."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import struct
import uuid

from .fm8_ownership import FM8HeaderMetadata, _read_utf16_field, parse_fm8_header


class FM8IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class FM8VinylHeader:
    metadata: FM8HeaderMetadata
    creator_id: int
    created_utc: datetime
    asset_id: uuid.UUID
    layer_count: int


def parse_vinyl_header(raw: bytes, *, folder_id: uuid.UUID | None = None) -> FM8VinylHeader:
    if not 4 <= len(raw) <= 65536 or struct.unpack_from("<I", raw)[0] != 9:
        raise FM8IdentityError("Unsupported FM8 vinyl header; a local version-9 save is required.")
    try:
        metadata = parse_fm8_header(raw)
        _, offset = _read_utf16_field(raw, 4, "title")
        _, offset = _read_utf16_field(raw, offset, "description")
        if offset + 28 > len(raw):
            raise ValueError("Truncated FM8 creator metadata.")
        year, month, weekday, day, hour, minute, second, millis, kind, creator_id = struct.unpack_from("<8HIQ", raw, offset)
        if weekday > 6 or millis > 999 or kind != 2 or not creator_id:
            raise ValueError("Unsupported FM8 creator metadata.")
        created = datetime(year, month, day, hour, minute, second, millis * 1000, tzinfo=timezone.utc)
        _, offset = _read_utf16_field(raw, offset + 28, "creator")
        if not metadata.creator.strip() or any(ord(c) < 32 for c in metadata.creator):
            raise ValueError("Missing or invalid FM8 creator name.")
        tail = raw[offset:]
        if len(tail) != 61 or tail[:12] != bytes(12) or tail[28:41] != b"\x01\x02\x00\x00\x00" + b"\xff" * 8:
            raise ValueError("Unsupported or non-local FM8 vinyl metadata.")
        first_id = uuid.UUID(bytes_le=tail[12:28])
        second_id = uuid.UUID(bytes_le=tail[45:61])
        if not first_id.int or first_id != second_id or (folder_id is not None and first_id != folder_id):
            raise ValueError("FM8 vinyl header identifiers do not match its save folder.")
        count = struct.unpack_from("<I", tail, 41)[0]
        if not 1 <= count <= 3000:
            raise ValueError("Invalid FM8 vinyl header shape count.")
    except (ValueError, struct.error) as exc:
        raise FM8IdentityError(str(exc)) from exc
    return FM8VinylHeader(metadata, creator_id, created, first_id, count)


def build_vinyl_header(source: bytes, source_folder_id: uuid.UUID, title: str, layer_count: int,
                       asset_id: uuid.UUID, *, now: datetime | None = None) -> bytes:
    donor = parse_vinyl_header(source, folder_id=source_folder_id)
    if not 1 <= layer_count <= 3000:
        raise FM8IdentityError("FM8 vinyl imports must contain between 1 and 3000 shapes.")
    if not asset_id.int or asset_id == donor.asset_id:
        raise FM8IdentityError("A new FM8 vinyl needs its own unique identifier.")
    title = " ".join(title.replace("\x00", " ").split()) or "KFPS Import"
    title = title.encode("utf-16le")[:128].decode("utf-16le", errors="ignore")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise FM8IdentityError("FM8 creation time must include a time zone.")
    now = now.astimezone(timezone.utc)

    def string(value: str) -> bytes:
        encoded = value.encode("utf-16le")
        return struct.pack("<I", len(encoded) // 2) + encoded

    raw = (
        struct.pack("<I", 9) + string(title) + string("")
        + struct.pack("<8HIQ", now.year, now.month, (now.weekday() + 1) % 7, now.day,
                      now.hour, now.minute, now.second, now.microsecond // 1000, 2, donor.creator_id)
        + string(donor.metadata.creator) + bytes(12) + asset_id.bytes_le
        + b"\x01\x02\x00\x00\x00" + b"\xff" * 8
        + struct.pack("<I", layer_count) + asset_id.bytes_le
    )
    parsed = parse_vinyl_header(raw, folder_id=asset_id)
    if parsed.layer_count != layer_count or parsed.creator_id != donor.creator_id:
        raise FM8IdentityError("FM8 new-vinyl metadata verification failed.")
    return raw
