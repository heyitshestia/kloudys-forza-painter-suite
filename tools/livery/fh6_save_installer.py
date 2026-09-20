"""Fail-closed same-car FH6 full-livery save installation.

The installer never replaces an existing livery. It validates a share package,
rewrites only destination-owned identity metadata, stages a new Livery_* folder,
and independently reopens every committed file before reporting success.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
import shutil
import struct
import uuid
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from tools.cgroup.fh6_identity import (
    ACCOUNT_NAME,
    CreatorIdentity,
    FH6CreatorNameNotFound,
    FH6IdentityError,
    SaveAccount,
    resolve_creator,
    select_account,
)
from tools.cgroup.forza_source_decoder import (
    clivery_to_layers,
    extract_livery_payload,
    inspect_clivery_privacy,
    unwrap_forza_container,
    unwrap_forza_container_bytes,
)

from .package import FullLiveryPackageError, validate_full_livery_package


class FullLiveryInstallError(RuntimeError):
    pass


class FullLiveryConcurrentChangeError(FullLiveryInstallError):
    pass


@dataclass(frozen=True)
class HeaderMetadata:
    format_version: int
    title: str
    description: str
    year: int
    month: int
    day_of_week: int
    day: int
    hour: int
    minute: int
    second: int
    millisecond: int
    date_trailing: bytes
    creator_tag: bytes
    creator_name: str
    section_prefix: bytes
    type_value: int
    car_id: int
    asset_guid: bytes
    trailing: bytes

    @property
    def record_kind(self) -> str:
        # This is the save record kind, not proof of server publication state.
        return {3: "saved", 4: "base", 5: "soulbound"}.get(
            int.from_bytes(self.date_trailing, "little"), "unknown"
        )


@dataclass(frozen=True)
class DestinationIdentity:
    creator: CreatorIdentity
    livery_evidence: Path | None = None
    livery_digest: str = ""

    @property
    def containers_root(self) -> Path:
        return self.creator.account.containers

    @property
    def creator_tag(self) -> bytes:
        return self.creator.account.user_id.to_bytes(8, "little")

    @property
    def creator_name(self) -> str:
        return self.creator.name

    def revalidate(self) -> None:
        try:
            self.creator.revalidate()
            if self.livery_evidence is not None:
                if _sha256(self.livery_evidence.read_bytes()) != self.livery_digest:
                    raise FH6IdentityError("FH6 livery identity evidence changed.")
        except (OSError, ValueError) as exc:
            raise FullLiveryConcurrentChangeError(
                "The FH6 account or creator evidence changed during installation. "
                "Select the active account's current save and try again."
            ) from exc


@dataclass(frozen=True)
class FullLiveryInstallResult:
    package_path: Path
    containers_root: Path
    installed_folder: Path
    backup_path: Path
    car_id: int
    model_code: str
    title: str
    placement_count: int
    thumbnail_written: bool


_HEADER_DATE_COMPONENT_BYTES = 16
_HEADER_DATE_TRAILING_BYTES = 4
_HEADER_DATE_BYTES = _HEADER_DATE_COMPONENT_BYTES + _HEADER_DATE_TRAILING_BYTES
_HEADER_CREATOR_TAG_BYTES = 8
_HEADER_SECTION_PREFIX_BYTES = 28
_HEADER_GUID_BYTES = 16
_CLIVERY_STATE_OFFSET = 0x08
_CLIVERY_CAR_ID_OFFSET = 0x10
_CLIVERY_INFO_TAG_OFFSET = 0x1A
_CLIVERY_CREATOR_TAG_OFFSET = 0x22
_MAX_HEADER_TEXT_UNITS = 4096


def _read_u32(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise FullLiveryInstallError(f"FH6 {label} is truncated.")
    return struct.unpack_from("<I", data, offset)[0]


def _read_utf16(data: bytes, offset: int, units: int, label: str) -> tuple[str, int]:
    if units < 0 or units > _MAX_HEADER_TEXT_UNITS:
        raise FullLiveryInstallError(f"FH6 {label} has an unsafe length.")
    end = offset + units * 2
    if offset < 0 or end > len(data):
        raise FullLiveryInstallError(f"FH6 {label} is truncated.")
    try:
        return data[offset:end].decode("utf-16le"), end
    except UnicodeDecodeError as exc:
        raise FullLiveryInstallError(f"FH6 {label} is not valid UTF-16.") from exc


def parse_fh6_header(data: bytes) -> HeaderMetadata:
    if not 8 <= len(data) <= 65536:
        raise FullLiveryInstallError("FH6 livery header size is invalid.")
    offset = 0
    format_version = _read_u32(data, offset, "header version")
    if format_version != 7:
        raise FullLiveryInstallError("Unsupported FH6 livery header version.")
    offset += 4
    title_units = _read_u32(data, offset, "header title")
    offset += 4
    title, offset = _read_utf16(data, offset, title_units, "header title")
    description_units = _read_u32(data, offset, "header description")
    offset += 4
    description, offset = _read_utf16(data, offset, description_units, "header description")
    if offset + _HEADER_DATE_BYTES > len(data):
        raise FullLiveryInstallError("FH6 livery header date is truncated.")
    year, month, day_of_week, day, hour, minute, second, millisecond = struct.unpack_from(
        "<8H", data, offset
    )
    try:
        datetime(year, month, day, hour, minute, second, millisecond * 1000)
    except ValueError as exc:
        raise FullLiveryInstallError("FH6 livery header date is invalid.") from exc
    if day_of_week > 6:
        raise FullLiveryInstallError("FH6 livery header weekday is invalid.")
    offset += _HEADER_DATE_COMPONENT_BYTES
    date_trailing = data[offset : offset + _HEADER_DATE_TRAILING_BYTES]
    offset += _HEADER_DATE_TRAILING_BYTES
    fixed_end = offset + _HEADER_CREATOR_TAG_BYTES
    if fixed_end > len(data):
        raise FullLiveryInstallError("FH6 livery header identity is truncated.")
    creator_tag = data[offset : offset + _HEADER_CREATOR_TAG_BYTES]
    offset += _HEADER_CREATOR_TAG_BYTES
    creator_units = _read_u32(data, offset, "header creator")
    offset += 4
    creator_name, offset = _read_utf16(data, offset, creator_units, "header creator")
    prefix_end = offset + _HEADER_SECTION_PREFIX_BYTES
    marker_end = prefix_end + 9
    if marker_end + 8 + _HEADER_GUID_BYTES > len(data):
        raise FullLiveryInstallError("FH6 livery header section metadata is truncated.")
    section_prefix = data[offset:prefix_end]
    if data[prefix_end : prefix_end + 2] != b"\x01\x02":
        raise FullLiveryInstallError("FH6 livery header section marker is invalid.")
    offset = marker_end
    type_value = _read_u32(data, offset, "header placement count")
    car_id = _read_u32(data, offset + 4, "header car identity")
    offset += 8
    asset_guid = data[offset : offset + _HEADER_GUID_BYTES]
    offset += _HEADER_GUID_BYTES
    return HeaderMetadata(
        format_version=format_version,
        title=title,
        description=description,
        year=year,
        month=month,
        day_of_week=day_of_week,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        millisecond=millisecond,
        date_trailing=date_trailing,
        creator_tag=creator_tag,
        creator_name=creator_name,
        section_prefix=section_prefix,
        type_value=type_value,
        car_id=car_id,
        asset_guid=asset_guid,
        trailing=data[offset:],
    )


def build_destination_header(
    *,
    title: str,
    car_id: int,
    placement_count: int,
    creator_tag: bytes,
    creator_name: str,
    now: datetime,
    asset_guid: bytes | None = None,
) -> bytes:
    """Create a local saved-livery record; never copy base/online metadata."""
    clean_title = " ".join(str(title).replace("\x00", " ").split()) or "KFPS Livery"
    title_bytes = clean_title.encode("utf-16le")[:128]
    clean_title = title_bytes.decode("utf-16le", errors="ignore")
    title_bytes = clean_title.encode("utf-16le")
    clean_creator = creator_name.strip()
    if (not clean_creator or clean_creator.casefold() == "kfps"
            or any(ord(char) < 32 for char in clean_creator)
            or len(clean_creator.encode("utf-16le")) > 512):
        raise FullLiveryInstallError("A verified FH6 creator name is required.")
    creator_bytes = clean_creator.encode("utf-16le")
    if len(creator_tag) != _HEADER_CREATOR_TAG_BYTES or not any(creator_tag):
        raise FullLiveryInstallError("Destination FH6 creator identity must be 8 nonzero-identity bytes.")
    if not (0 < car_id < 2**32 and 0 < placement_count < 2**32):
        raise FullLiveryInstallError("Invalid FH6 car or placement count.")
    guid = uuid.uuid4().bytes_le if asset_guid is None else bytes(asset_guid)
    if len(guid) != _HEADER_GUID_BYTES or not any(guid):
        raise FullLiveryInstallError("Destination FH6 asset GUID must be 16 bytes and not zero.")
    moment = now.astimezone()
    output = bytearray(struct.pack("<II", 7, len(title_bytes) // 2))
    output.extend(title_bytes)
    output.extend(struct.pack("<I", 0))
    output.extend(
        struct.pack(
            "<8H",
            moment.year,
            moment.month,
            (moment.weekday() + 1) % 7,
            moment.day,
            moment.hour,
            moment.minute,
            moment.second,
            moment.microsecond // 1000,
        )
    )
    output.extend(struct.pack("<I", 3))
    output.extend(creator_tag)
    output.extend(struct.pack("<I", len(creator_bytes) // 2))
    output.extend(creator_bytes)
    output.extend(bytes(_HEADER_SECTION_PREFIX_BYTES))
    output.extend(b"\x01\x02" + b"\x00" * 7)
    output.extend(struct.pack("<II", int(placement_count), int(car_id)))
    output.extend(guid)
    parsed = parse_fh6_header(bytes(output))
    if parsed.title != clean_title or parsed.car_id != car_id or parsed.type_value != placement_count:
        raise FullLiveryInstallError("Destination FH6 header failed independent verification.")
    if (parsed.creator_tag != creator_tag or parsed.asset_guid != guid
            or parsed.creator_name != clean_creator or parsed.record_kind != "saved"
            or parsed.description or any(parsed.section_prefix) or parsed.trailing):
        raise FullLiveryInstallError("Destination FH6 header identity failed independent verification.")
    if (
        parsed.year,
        parsed.month,
        parsed.day_of_week,
        parsed.day,
        parsed.hour,
        parsed.minute,
        parsed.second,
        parsed.millisecond,
    ) != (
        moment.year,
        moment.month,
        (moment.weekday() + 1) % 7,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
        moment.microsecond // 1000,
    ):
        raise FullLiveryInstallError("Destination FH6 header date failed independent verification.")
    return bytes(output)


def _clivery_creator_tag(payload: bytes) -> bytes:
    if len(payload) < _CLIVERY_CREATOR_TAG_OFFSET + _HEADER_CREATOR_TAG_BYTES:
        raise FullLiveryInstallError("FH6 C_livery identity record is truncated.")
    if payload[_CLIVERY_INFO_TAG_OFFSET : _CLIVERY_INFO_TAG_OFFSET + 4] != b"yrvl":
        raise FullLiveryInstallError("FH6 C_livery identity record is missing.")
    if _read_u32(payload, _CLIVERY_INFO_TAG_OFFSET + 4, "C_livery identity record") < 8:
        raise FullLiveryInstallError("FH6 C_livery identity record is invalid.")
    return payload[_CLIVERY_CREATOR_TAG_OFFSET : _CLIVERY_CREATOR_TAG_OFFSET + _HEADER_CREATOR_TAG_BYTES]


def rewrite_destination_identity(payload: bytes, creator_tag: bytes) -> bytes:
    if len(creator_tag) != _HEADER_CREATOR_TAG_BYTES:
        raise FullLiveryInstallError("Destination FH6 creator identity must be exactly 8 bytes.")
    _clivery_creator_tag(payload)
    rewritten = bytearray(payload)
    struct.pack_into("<I", rewritten, _CLIVERY_STATE_OFFSET, 0)
    rewritten[
        _CLIVERY_CREATOR_TAG_OFFSET : _CLIVERY_CREATOR_TAG_OFFSET + _HEADER_CREATOR_TAG_BYTES
    ] = creator_tag
    result = bytes(rewritten)
    allowed = set(range(_CLIVERY_STATE_OFFSET, _CLIVERY_STATE_OFFSET + 4))
    allowed.update(range(_CLIVERY_CREATOR_TAG_OFFSET, _CLIVERY_CREATOR_TAG_OFFSET + _HEADER_CREATOR_TAG_BYTES))
    changed = {index for index, (left, right) in enumerate(zip(payload, result)) if left != right}
    if not changed.issubset(allowed):
        raise FullLiveryInstallError("FH6 destination rewrite changed artwork bytes.")
    privacy = inspect_clivery_privacy(result)
    if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
        raise FullLiveryInstallError("FH6 destination ownership verification failed.")
    return result


def _wrap_payload(payload: bytes) -> bytes:
    compressed = zlib.compress(payload)
    return struct.pack("<II", len(compressed), len(payload)) + compressed


def _creator_from_livery(account: SaveAccount) -> DestinationIdentity:
    records = []
    for folder in account.containers.iterdir():
        if not folder.name.startswith(("Livery_", "BaseLivery_")):
            continue
        source = folder / "C_livery"
        header_path = folder / "header"
        try:
            if (folder.resolve().parent != account.containers
                    or source.resolve().parent != folder.resolve()
                    or header_path.resolve().parent != folder.resolve()
                    or header_path.stat().st_size > 65536):
                continue
            raw_header = header_path.read_bytes()
            header = parse_fh6_header(raw_header)
            expected_tag = account.user_id.to_bytes(8, "little")
            if (header.creator_tag != expected_tag or header.record_kind not in ("saved", "base")
                    or not header.creator_name.strip() or header.creator_name.strip().casefold() == "kfps"
                    or any(ord(char) < 32 for char in header.creator_name)
                    or len(header.creator_name.encode("utf-16le")) > 512 or not any(header.asset_guid)):
                continue
            raw_source = source.read_bytes()
            payload = unwrap_forza_container_bytes(raw_source, source)
            privacy = inspect_clivery_privacy(payload)
            if (not privacy["source_owned"] or _clivery_creator_tag(payload) != expected_tag
                    or _read_u32(payload, _CLIVERY_CAR_ID_OFFSET, "C_livery car identity") != header.car_id):
                continue
            created = datetime(header.year, header.month, header.day, header.hour,
                               header.minute, header.second, header.millisecond * 1000)
            creator = CreatorIdentity(account, header.creator_name.strip(), header_path, raw_header)
            records.append((created, creator, source, _sha256(raw_source)))
        except (OSError, FullLiveryInstallError, ValueError, zlib.error):
            continue
    if not records:
        raise FullLiveryInstallError(
            "The FH6 account is verified, but its creator name could not be confirmed. "
            "Save one small vinyl or personal design in FH6, then retry."
        )
    newest = max(row[0] for row in records)
    latest = [row for row in records if row[0] == newest]
    if len({row[1].name for row in latest}) != 1:
        raise FullLiveryInstallError(
            "Conflicting FH6 creator names were found. Save one small vinyl in FH6, then retry."
        )
    _, creator, source, digest = latest[0]
    return DestinationIdentity(creator, source, digest)


def _select_destination_account(
    scan_roots: Iterable[Path | str], *, destination: Path | str | None = None,
    local_app_data: Path | None = None,
) -> SaveAccount:
    try:
        selected = Path(destination).resolve(strict=True) if destination is not None else None
        if selected is not None and not selected.is_dir():
            raise FH6IdentityError("Select an FH6 account save folder.")
        exact = selected is not None and any(
            ACCOUNT_NAME.fullmatch(path.name) for path in (selected, *selected.parents)
        )
        return select_account(
            [selected] if selected is not None else (Path(root) for root in scan_roots),
            destination=selected if exact else None,
            local_app_data=local_app_data,
            use_saved_locations=selected is None,
        )
    except (OSError, FH6IdentityError) as exc:
        raise FullLiveryInstallError(f"FH6 destination could not be verified: {exc}") from exc


def select_destination_identity(
    scan_roots: Iterable[Path | str], *, destination: Path | str | None = None,
    local_app_data: Path | None = None,
) -> DestinationIdentity:
    account = _select_destination_account(
        scan_roots, destination=destination, local_app_data=local_app_data
    )
    try:
        return DestinationIdentity(resolve_creator(account))
    except FH6CreatorNameNotFound:
        return _creator_from_livery(account)
    except (OSError, FH6IdentityError) as exc:
        raise FullLiveryInstallError(f"FH6 creator name could not be verified: {exc}") from exc


def _snapshot(root: Path, *, exclude: Path | None = None) -> tuple[tuple[str, int, str], ...]:
    rows: list[tuple[str, int, str]] = []
    excluded = exclude.resolve() if exclude is not None else None
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if excluded is not None and (resolved == excluded or excluded in resolved.parents):
            continue
        relative = path.relative_to(root)
        data = path.read_bytes()
        rows.append((relative.as_posix(), len(data), _sha256(data)))
    return tuple(rows)


def _check_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise concurrent.futures.CancelledError()


def _write_exclusive(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_path(root: Path, stem: str) -> Path:
    candidate = root / stem
    suffix = 2
    while candidate.exists():
        candidate = root / f"{stem}_{suffix}"
        suffix += 1
    return candidate


def _thumbnail_from_package(bundle: zipfile.ZipFile, manifest: dict[str, Any]) -> bytes:
    names = {str(item.get("path") or "") for item in manifest.get("files") or [] if isinstance(item, dict)}
    if "source/fh6/bigThumb.webp" in names:
        data = bundle.read("source/fh6/bigThumb.webp")
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "WEBP" or image.size != (670, 376):
                raise FullLiveryInstallError("The package FH6 thumbnail is invalid.")
            image.verify()
        return data
    rendered = [
        str(item.get("path") or "")
        for item in (manifest.get("files") or [])
        if isinstance(item, dict) and str(item.get("path") or "").startswith("projection/rendered/")
    ]
    if not rendered:
        return b""
    with Image.open(io.BytesIO(bundle.read(sorted(rendered)[0]))) as source:
        image = source.convert("RGBA")
    image.thumbnail((670, 376), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (670, 376), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((670 - image.width) // 2, (376 - image.height) // 2))
    output = io.BytesIO()
    canvas.save(output, format="WEBP", lossless=True, method=6)
    return output.getvalue()


def install_full_livery_package(
    package_path: Path | str,
    *,
    scan_roots: Iterable[Path | str],
    backup_root: Path | str,
    expected_model_code: str,
    destination: Path | str | None = None,
    local_app_data: Path | None = None,
    now: datetime | None = None,
    cancel_event=None,
) -> FullLiveryInstallResult:
    _check_cancelled(cancel_event)
    package = Path(package_path).resolve()
    manifest = validate_full_livery_package(package)
    sharing = manifest.get("sharing") or {}
    if sharing.get("exportable") is not True or sharing.get("preview_only") is True:
        raise FullLiveryInstallError("Only verified shareable full-livery packages can be installed.")
    livery = manifest.get("livery") or {}
    vehicle = manifest.get("vehicle") or {}
    car_id = int(livery.get("target_car_id") or 0)
    placement_count = int(livery.get("logical_placement_count") or 0)
    package_model = str(vehicle.get("model_code") or "").strip()
    expected_model = str(expected_model_code or "").strip()
    if car_id <= 0 or placement_count <= 0:
        raise FullLiveryInstallError("The package has no installable FH6 livery placements.")
    if not package_model or not expected_model or package_model.casefold() != expected_model.casefold():
        raise FullLiveryInstallError(
            "Same-car safety check failed: the package car model does not match this FH6 installation."
        )
    scan_roots = tuple(scan_roots)
    identity = select_destination_identity(
        scan_roots, destination=destination, local_app_data=local_app_data
    )

    def revalidate_destination() -> None:
        identity.revalidate()
        try:
            current = _select_destination_account(
                scan_roots, destination=destination, local_app_data=local_app_data
            )
            if current != identity.creator.account:
                raise FullLiveryInstallError("FH6 destination selection changed.")
        except FullLiveryInstallError as exc:
            raise FullLiveryConcurrentChangeError(
                "The active FH6 save selection changed during installation. "
                "Select the intended account's current save and retry."
            ) from exc

    with zipfile.ZipFile(package) as bundle:
        raw_container = bundle.read("source/fh6/C_livery")
        source_payload = unwrap_forza_container_bytes(raw_container, package)
        try:
            source_header = parse_fh6_header(bundle.read("source/fh6/header"))
        except KeyError as exc:
            raise FullLiveryInstallError(
                "This package has no exact-car FH6 header and cannot be installed safely."
            ) from exc
        thumbnail = _thumbnail_from_package(bundle, manifest)
    if _read_u32(source_payload, _CLIVERY_CAR_ID_OFFSET, "C_livery car identity") != car_id:
        raise FullLiveryInstallError("Package source does not target its declared FH6 car.")
    if source_header.car_id != car_id or source_header.type_value != placement_count:
        raise FullLiveryInstallError("Package header does not match its declared FH6 car or placement count.")
    _check_cancelled(cancel_event)
    privacy = inspect_clivery_privacy(source_payload)
    if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
        raise FullLiveryInstallError("The source livery is not eligible for identity rewriting.")
    source_layers, source_report = clivery_to_layers(source_payload)
    rewritten_payload = rewrite_destination_identity(source_payload, identity.creator_tag)
    _, counts, _ = extract_livery_payload(rewritten_payload)
    if sum(counts) != placement_count:
        raise FullLiveryInstallError("Destination livery placement count changed during identity rewriting.")
    decoded, report = clivery_to_layers(rewritten_payload)
    if len(decoded) != placement_count or decoded != source_layers or report != source_report:
        raise FullLiveryInstallError(
            "Destination identity rewriting changed the decoded artwork. No save was changed."
        )
    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.astimezone()
    title = str(livery.get("title") or "KFPS Livery")
    header = build_destination_header(
        title=title,
        car_id=car_id,
        placement_count=placement_count,
        creator_tag=identity.creator_tag,
        creator_name=identity.creator_name,
        now=moment,
    )
    container = _wrap_payload(rewritten_payload)
    if unwrap_forza_container_bytes(container, "staged FH6 livery") != rewritten_payload:
        raise FullLiveryInstallError("Staged FH6 C_livery failed compression verification.")
    root = identity.containers_root
    revalidate_destination()
    original_snapshot = _snapshot(root)
    _check_cancelled(cancel_event)
    stamp = moment.strftime("%Y%m%d%H%M%S")
    final_folder = _unique_path(root, f"Livery_{car_id:04d}_{stamp}")
    staging = root / f".{final_folder.name}.kfps-{uuid.uuid4().hex}.tmp"
    backup_parent = Path(backup_root)
    backup_parent.mkdir(parents=True, exist_ok=True)
    backup = _unique_path(backup_parent, f"{final_folder.name}-{moment.strftime('%Y%m%d-%H%M%S')}")
    backup.mkdir(parents=True, exist_ok=False)
    _write_exclusive(backup / "C_livery", container)
    _write_exclusive(backup / "header", header)
    if thumbnail:
        _write_exclusive(backup / "bigThumb.webp", thumbnail)
    transaction = {
        "format": "kfps_fh6_full_livery_install_backup_v1",
        "created_utc": moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "package_path": str(package),
        "package_sha256": _sha256(package.read_bytes()),
        "containers_root": str(root),
        "installed_folder_name": final_folder.name,
        "identity_evidence_folder": identity.creator.evidence.parent.name,
        "header_record_kind": "saved",
        "target_car_id": car_id,
        "model_code": package_model,
        "placement_count": placement_count,
        "files": {
            "C_livery": _sha256(container),
            "header": _sha256(header),
            **({"bigThumb.webp": _sha256(thumbnail)} if thumbnail else {}),
        },
    }
    _write_exclusive(backup / "install.json", (json.dumps(transaction, indent=2) + "\n").encode("utf-8"))
    committed = False
    try:
        revalidate_destination()
        staging.mkdir()
        _write_exclusive(staging / "C_livery", container)
        _write_exclusive(staging / "header", header)
        if thumbnail:
            _write_exclusive(staging / "bigThumb.webp", thumbnail)
        _check_cancelled(cancel_event)
        if _snapshot(root, exclude=staging) != original_snapshot:
            raise FullLiveryConcurrentChangeError(
                "The FH6 save changed while KFPS staged the livery. Nothing was installed."
            )
        _check_cancelled(cancel_event)
        revalidate_destination()
        os.replace(staging, final_folder)
        committed = True
        installed_payload = unwrap_forza_container(final_folder / "C_livery")
        installed_header_bytes = (final_folder / "header").read_bytes()
        installed_header = parse_fh6_header(installed_header_bytes)
        if installed_header_bytes != header:
            raise FullLiveryInstallError("Installed FH6 header differs from the verified staging record.")
        installed_privacy = inspect_clivery_privacy(installed_payload)
        installed_layers, installed_report = clivery_to_layers(installed_payload)
        if installed_payload != rewritten_payload:
            raise FullLiveryInstallError("Installed FH6 livery bytes do not match the verified staging record.")
        if installed_header.car_id != car_id or installed_header.type_value != placement_count:
            raise FullLiveryInstallError("Installed FH6 header does not match the package car or placement count.")
        if installed_header.creator_tag != identity.creator_tag or installed_privacy["source_owned"] is not True:
            raise FullLiveryInstallError("Installed FH6 livery is not owned by the destination account.")
        if (
            installed_privacy["contains_foreign_groups"]
            or len(installed_layers) != placement_count
            or installed_layers != source_layers
            or installed_report != source_report
        ):
            raise FullLiveryInstallError("Installed FH6 livery failed its ownership or placement verification.")
        if thumbnail:
            with Image.open(final_folder / "bigThumb.webp") as image:
                if image.format != "WEBP" or image.size != (670, 376):
                    raise FullLiveryInstallError("Installed FH6 thumbnail failed verification.")
                image.verify()
        revalidate_destination()
        return FullLiveryInstallResult(
            package_path=package,
            containers_root=root,
            installed_folder=final_folder,
            backup_path=backup,
            car_id=car_id,
            model_code=package_model,
            title=installed_header.title,
            placement_count=placement_count,
            thumbnail_written=bool(thumbnail),
        )
    except BaseException as exc:
        if committed and final_folder.is_dir():
            try:
                shutil.rmtree(final_folder)
            except OSError as rollback_exc:
                raise FullLiveryInstallError(
                    f"KFPS could not remove a failed install at {final_folder}. "
                    f"Use the recovery record at {backup} before opening FH6."
                ) from rollback_exc
            if final_folder.exists():
                raise FullLiveryInstallError(
                    f"KFPS could not verify rollback of {final_folder}. "
                    f"Use the recovery record at {backup} before opening FH6."
                ) from exc
        raise
    finally:
        if staging.is_dir():
            try:
                shutil.rmtree(staging)
            except OSError:
                pass
