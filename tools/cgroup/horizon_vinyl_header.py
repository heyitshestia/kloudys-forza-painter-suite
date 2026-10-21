"""Bounded FH4/FH5 draft-vinyl sidecars, shared by Steam and WGS."""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HorizonVinylHeader:
    version: int
    title: str
    creator_id: int
    creator: str
    layer_count: int
    asset_id: uuid.UUID


def parse_vinyl_header(raw: bytes, game: str = "fh5") -> HorizonVinylHeader:
    versions = {"fh4": (4,), "fh5": (4, 6)}
    if game not in versions:
        raise ValueError("Only FH4/FH5 draft vinyl headers are supported")
    label = game.upper()
    if not 4 <= len(raw) <= 65536:
        raise ValueError(f"Invalid {label} header size")
    version = struct.unpack_from("<I", raw)[0]
    if version not in versions[game]:
        raise ValueError(f"Unsupported {label} vinyl header version {version}")
    offset = 4

    def string() -> str:
        nonlocal offset
        if offset + 4 > len(raw):
            raise ValueError(f"Truncated {label} header string")
        units = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        end = offset + units * 2
        if units > 4096 or end > len(raw):
            raise ValueError(f"Invalid {label} UTF-16 string length")
        try:
            text = raw[offset:end].decode("utf-16le")
        except UnicodeError as exc:
            raise ValueError(f"Invalid {label} UTF-16 text") from exc
        offset = end
        if any(ord(char) < 32 for char in text):
            raise ValueError(f"Control characters in {label} header")
        return text

    title, description = string(), string()
    if description or offset + 28 > len(raw):
        raise ValueError(f"Only complete, unpublished {label} vinyl headers are supported")
    year, month, weekday, day, hour, minute, second, millis, kind, owner = struct.unpack_from(
        "<8HIQ", raw, offset,
    )
    try:
        datetime(year, month, day, hour, minute, second, millis * 1000)
    except ValueError as exc:
        raise ValueError(f"Invalid {label} header creation date") from exc
    if weekday > 6 or kind != 2 or owner == 0:
        raise ValueError(f"{label} header is not an owned vinyl group")
    offset += 28
    creator = string()
    if not creator.strip() or creator.strip().casefold() == "kfps":
        raise ValueError(f"{label} header has no verified creator name")
    tail = raw[offset:]
    if len(tail) != 53 or tail[28:30] not in (b"\x01\x02", b"\x00\x02"):
        raise ValueError(f"Unsupported {label} draft vinyl header tail")
    count = struct.unpack_from("<I", tail, 33)[0]
    asset_id = uuid.UUID(bytes_le=tail[37:53])
    if not 1 <= count <= 3000 or not asset_id.int:
        raise ValueError(f"Invalid {label} header count or asset identity")
    return HorizonVinylHeader(version, title, owner, creator, count, asset_id)


def build_vinyl_header(
    identity: HorizonVinylHeader, title: str, layer_count: int, game: str = "fh5",
    *, now: datetime | None = None,
) -> bytes:
    """Fresh draft identity; never retain a donor's asset or publication data."""
    if game not in ("fh4", "fh5") or not 1 <= layer_count <= 3000:
        raise ValueError("FH4/FH5 vinyl imports require 1 to 3000 layers")
    title = " ".join(title.split()) or "KFPS Import"
    title = title.encode("utf-16le")[:128].decode("utf-16le", errors="ignore")

    def string(text: str) -> bytes:
        encoded = text.encode("utf-16le")
        return struct.pack("<I", len(encoded) // 2) + encoded

    now = now or datetime.now()
    raw = (
        struct.pack("<I", 4 if game == "fh4" else 6) + string(title) + string("")
        + struct.pack("<8HIQ", now.year, now.month, (now.weekday() + 1) % 7, now.day,
                      now.hour, now.minute, now.second, now.microsecond // 1000, 2, identity.creator_id)
        + string(identity.creator) + bytes(28) + b"\x01\x02" + bytes(3)
        + struct.pack("<I", layer_count) + uuid.uuid4().bytes_le
    )
    parse_vinyl_header(raw, game)
    return raw
