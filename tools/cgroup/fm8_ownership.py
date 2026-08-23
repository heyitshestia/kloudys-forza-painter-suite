"""Fail-closed ownership checks for local Forza Motorsport vinyl groups."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


_HEADER_FIXED_METADATA_SIZE = 28
_LOCAL_HEADER_STATE = 0
_DOWNLOADED_HEADER_STATE = 1
_PAYLOAD_STATE_OFFSET = 0x1D
_CLEAR_PAYLOAD_STATES = frozenset((0x20, 0x60))
_RESTRICTED_PAYLOAD_STATE = 0x21
_MAX_TEXT_LENGTH = 4096


@dataclass(frozen=True)
class FM8HeaderMetadata:
    version: int
    title: str
    description: str
    creator: str
    catalog_state: int


@dataclass(frozen=True)
class FM8OwnershipResult:
    allowed: bool
    status: str
    reason: str
    header: FM8HeaderMetadata | None
    payload_state: int | None

    def report(self) -> dict:
        return {
            "passed": bool(self.allowed),
            "status": self.status,
            "title": self.header.title if self.header else "",
            "creator": self.header.creator if self.header else "",
        }


def _read_utf16_field(raw: bytes, offset: int, field_name: str) -> tuple[str, int]:
    if offset < 0 or offset + 4 > len(raw):
        raise ValueError(f"FM8 header is missing its {field_name} length")
    length = struct.unpack_from("<I", raw, offset)[0]
    if length > _MAX_TEXT_LENGTH:
        raise ValueError(f"FM8 header {field_name} is unreasonably long")
    start = offset + 4
    end = start + int(length) * 2
    if end > len(raw):
        raise ValueError(f"FM8 header {field_name} is truncated")
    try:
        value = raw[start:end].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise ValueError(f"FM8 header {field_name} is not valid UTF-16") from exc
    if "\x00" in value:
        raise ValueError(f"FM8 header {field_name} contains an embedded terminator")
    return value, end


def parse_fm8_header(raw: bytes) -> FM8HeaderMetadata:
    if len(raw) < 8:
        raise ValueError("FM8 header is truncated")
    version = struct.unpack_from("<I", raw, 0)[0]
    title, offset = _read_utf16_field(raw, 4, "title")
    description, offset = _read_utf16_field(raw, offset, "description")
    offset += _HEADER_FIXED_METADATA_SIZE
    creator, offset = _read_utf16_field(raw, offset, "creator")
    if offset + 4 > len(raw):
        raise ValueError("FM8 header is missing its catalog state")
    catalog_state = struct.unpack_from("<I", raw, offset)[0]
    return FM8HeaderMetadata(
        version=int(version),
        title=title,
        description=description,
        creator=creator,
        catalog_state=int(catalog_state),
    )


def assess_fm8_layer_group(header_raw: bytes, payload: bytes) -> FM8OwnershipResult:
    try:
        header = parse_fm8_header(header_raw)
    except ValueError:
        return FM8OwnershipResult(
            allowed=False,
            status="unknown",
            reason="KFPS could not verify this FM8 vinyl group's local ownership metadata.",
            header=None,
            payload_state=None,
        )

    if len(payload) <= _PAYLOAD_STATE_OFFSET or payload[:4] != b"gyvl":
        return FM8OwnershipResult(
            allowed=False,
            status="unknown",
            reason="KFPS could not verify this FM8 vinyl group's content metadata.",
            header=header,
            payload_state=None,
        )

    payload_state = int(payload[_PAYLOAD_STATE_OFFSET])
    if header.catalog_state == _DOWNLOADED_HEADER_STATE or payload_state == _RESTRICTED_PAYLOAD_STATE:
        return FM8OwnershipResult(
            allowed=False,
            status="restricted",
            reason="This FM8 vinyl group contains content that is not owned by the current profile.",
            header=header,
            payload_state=payload_state,
        )
    if header.catalog_state != _LOCAL_HEADER_STATE or payload_state not in _CLEAR_PAYLOAD_STATES:
        return FM8OwnershipResult(
            allowed=False,
            status="unknown",
            reason="KFPS could not verify this FM8 vinyl group's ownership safely.",
            header=header,
            payload_state=payload_state,
        )
    return FM8OwnershipResult(
        allowed=True,
        status="clear",
        reason="",
        header=header,
        payload_state=payload_state,
    )


def assess_fm8_layer_group_files(data_path: Path | str) -> FM8OwnershipResult:
    data_path = Path(data_path)
    header_path = data_path.parent / "header"
    try:
        header_raw = header_path.read_bytes()
        payload = data_path.read_bytes()
    except OSError:
        return FM8OwnershipResult(
            allowed=False,
            status="unknown",
            reason="KFPS could not read the complete FM8 vinyl group.",
            header=None,
            payload_state=None,
        )
    return assess_fm8_layer_group(header_raw, payload)
