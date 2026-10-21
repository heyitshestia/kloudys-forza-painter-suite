"""Bounded, additive FH5 WGS imports; no discovery, UI, or Steam writes.

Uses KFPS's existing v14/v4 WGS writer, not FLS's replacement implementation.
Native FH5 acceptance of new registrations still requires game qualification.
The caller owns the game-closed/cloud-idle gate and supplies validated artwork.
"""
from __future__ import annotations

import hashlib
import struct
from concurrent.futures import CancelledError
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from .cgroup_codec import wrap_payload
from .forza_source_decoder import cgroup_to_layers, decode_forza_source
from .horizon_vinyl_header import HorizonVinylHeader, build_vinyl_header, parse_vinyl_header
from .xbox_wgs import (
    WGS_SLOT_PATTERN, WgsConcurrentChangeError, WgsCreateResult, WgsFormatError,
    WgsLayerGroup, create_wgs_layer_group, parse_wgs_file_list, read_wgs_index,
)

FH5_PACKAGE = "Microsoft.624F8B84B80_8wekyb3d8bbwe"


FH5VinylHeader = HorizonVinylHeader


def parse_fh5_vinyl_header(raw: bytes) -> FH5VinylHeader:
    try:
        return parse_vinyl_header(raw, "fh5")
    except ValueError as exc:
        raise WgsFormatError(str(exc)) from exc


@dataclass(frozen=True)
class FH5WgsTarget:
    group: WgsLayerGroup
    header: FH5VinylHeader
    evidence: tuple[tuple[Path, bytes], ...]

    def revalidate(self) -> None:
        for path, digest in self.evidence:
            if path.is_symlink() or path.is_junction() or hashlib.sha256(path.read_bytes()).digest() != digest:
                raise WgsConcurrentChangeError("The selected FH5 account or template changed; select it again")


def inspect_fh5_wgs_target(descriptor_path: Path | str) -> FH5WgsTarget:
    """Inspect exactly the selected active container.N; never choose an account."""
    selected = Path(descriptor_path)
    if any(path.is_symlink() or path.is_junction() for path in (selected, *selected.parents)):
        raise WgsFormatError("Linked FH5 save paths are unsupported")
    descriptor = selected.resolve(strict=True)
    slot = descriptor.parent.parent
    if (not WGS_SLOT_PATTERN.fullmatch(slot.name)
            or slot.parent.name.casefold() != "wgs"
            or slot.parent.parent.name.casefold() != "systemappdata"
            or slot.parent.parent.parent.name.casefold() != FH5_PACKAGE.casefold()):
        raise WgsFormatError("Choose an FH5 Microsoft Store/Xbox WGS container.N; Steam/Helium/PGS writes are unsupported")
    owner = int(slot.name.split("_", 1)[0], 16)
    index_path = slot / "containers.index"
    index_bytes = index_path.read_bytes()
    index = read_wgs_index(slot)
    if index.package_name.partition("!")[0].casefold() != FH5_PACKAGE.casefold() or not owner:
        raise WgsFormatError("FH5 WGS package or account identity does not match its directory")
    matches = [entry for entry in index.folders if entry.directory_name.casefold() == descriptor.parent.name.casefold()]
    if len(matches) != 1:
        raise WgsFormatError("The selected FH5 container is not uniquely registered")
    folder = matches[0]
    if (not folder.name.casefold().startswith("layergroup_") or folder.flags != 1
            or descriptor.name.casefold() != f"container.{folder.sequence}"):
        raise WgsFormatError("Select an active, synchronized FH5 LayerGroup descriptor")
    descriptor_bytes = descriptor.read_bytes()
    files = parse_wgs_file_list(descriptor)
    if {item.name.casefold() for item in files.entries} != {"c_group", "header", "thumb.png"}:
        raise WgsFormatError("Only the verified three-blob FH5 vinyl layout is supported")
    if any(item.primary_guid != item.secondary_guid for item in files.entries):
        raise WgsFormatError("FH5 descriptors with distinct blob GUID pairs require further format qualification")
    group = WgsLayerGroup(slot, folder, files)
    evidence_paths = [index_path, descriptor, *(item.actual_path for item in files.entries)]
    evidence = tuple((path, hashlib.sha256(path.read_bytes()).digest()) for path in evidence_paths)
    if (hashlib.sha256(index_bytes).digest() != evidence[0][1]
            or hashlib.sha256(descriptor_bytes).digest() != evidence[1][1]):
        raise WgsConcurrentChangeError("FH5 index or descriptor changed during inspection")
    header = parse_fh5_vinyl_header(group.header_path.read_bytes())
    decoded = decode_forza_source(group.cgroup_path, allow_locked=False, game="fh5")
    if header.creator_id != owner or len(decoded.layers) != header.layer_count or decoded.report.get("warnings"):
        raise WgsFormatError("FH5 template ownership, header and decoded layer count must agree")
    target = FH5WgsTarget(group, header, evidence)
    target.revalidate()
    return target


def build_fh5_vinyl_header(target: FH5WgsTarget, title: str, layer_count: int) -> bytes:
    """Build a fresh minimal v6 draft using only the selected account's identity."""
    try:
        return build_vinyl_header(target.header, title, layer_count, "fh5")
    except ValueError as exc:
        raise WgsFormatError(str(exc)) from exc


def create_fh5_wgs_layer_group(
    target: FH5WgsTarget, *, payload: bytes, header_data: bytes, thumbnail_data: bytes,
    expected_layers: int, backup_root: Path | str, check_ready: Callable[[], None], cancel_event=None,
) -> WgsCreateResult:
    """Add, never replace. check_ready must raise unless game closed/cloud idle.

    Cancellation is honored through staging; index publication and verification
    finish as one non-cancellable section. A late cancel cannot report no writes.
    """
    if not callable(check_ready):
        raise TypeError("An explicit game-closed/cloud-idle readiness check is required")

    def ready() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("FH5 import cancelled before publishing save files")
        check_ready()
        target.revalidate()

    ready()
    fresh = inspect_fh5_wgs_target(target.group.file_list.path)
    if fresh != target:
        raise WgsConcurrentChangeError("The selected FH5 destination changed")
    header = parse_fh5_vinyl_header(header_data)
    if (len(payload) < 0x24 or payload[:4] != b"gyvl"
            or struct.unpack_from("<I", payload, 4)[0] != 1 or payload[0x1D] not in (0x20, 0x60)):
        raise WgsFormatError("FH5 requires a supported, unlocked gyvl version-1 payload")
    layers, report = cgroup_to_layers(payload, game="fh5")
    if (header.version != 6 or not 1 <= expected_layers <= 3000
            or header.layer_count != expected_layers
            or len(layers) != expected_layers or report.get("warnings")
            or report.get("max_group_depth", 0) > 64):
        raise WgsFormatError("FH5 payload and version-6 draft header must agree on all layers")
    if (header.creator_id != target.header.creator_id or header.creator != target.header.creator
            or header.asset_id == target.header.asset_id):
        raise WgsFormatError("FH5 import requires the selected creator and a fresh asset GUID")
    from PIL import Image

    if len(thumbnail_data) > 4 * 1024 * 1024:
        raise WgsFormatError("FH5 thumbnail is too large")
    with Image.open(BytesIO(thumbnail_data)) as image:
        if image.format != "PNG" or image.size != (256, 256):
            raise WgsFormatError("FH5 import requires a 256x256 PNG thumbnail")
        image.verify()

    def verify(cgroup: Path, header_path: Path, _thumbnail: Path) -> None:
        actual_header = parse_fh5_vinyl_header(header_path.read_bytes())
        decoded = decode_forza_source(cgroup, allow_locked=False, game="fh5")
        if actual_header != header or len(decoded.layers) != expected_layers or decoded.report.get("warnings"):
            raise WgsFormatError("FH5 imported files failed independent reopen verification")

    return create_wgs_layer_group(
        target.group.slot_path, target.group, cgroup_data=wrap_payload(payload), header_data=header_data,
        thumbnail_data=thumbnail_data, backup_root=backup_root, check_ready=ready, verify=verify,
    )
