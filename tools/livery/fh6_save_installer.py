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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

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
    published: bool
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


@dataclass(frozen=True)
class DestinationIdentity:
    containers_root: Path
    template_folder: Path
    creator_tag: bytes
    creator_name: str
    header_template: HeaderMetadata
    latest_owned_mtime_ns: int


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
    if len(data) < 8:
        raise FullLiveryInstallError("FH6 livery header is too small.")
    offset = 0
    format_version = _read_u32(data, offset, "header version")
    offset += 4
    title_units = _read_u32(data, offset, "header title")
    offset += 4
    title, offset = _read_utf16(data, offset, title_units, "header title")
    description_units = _read_u32(data, offset, "header description")
    offset += 4
    published = description_units != 0
    description = ""
    if published:
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
        published=published,
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
    template: HeaderMetadata,
    *,
    title: str,
    car_id: int,
    placement_count: int,
    creator_tag: bytes,
    now: datetime,
    asset_guid: bytes | None = None,
) -> bytes:
    clean_title = " ".join(str(title).replace("\x00", " ").split())[:64] or "KFPS Livery"
    clean_creator = " ".join(template.creator_name.replace("\x00", " ").split())[:128]
    if len(creator_tag) != _HEADER_CREATOR_TAG_BYTES:
        raise FullLiveryInstallError("Destination FH6 creator identity must be exactly 8 bytes.")
    guid = bytes(asset_guid or uuid.uuid4().bytes)
    if len(guid) != _HEADER_GUID_BYTES:
        raise FullLiveryInstallError("Destination FH6 asset GUID must be exactly 16 bytes.")
    moment = now.astimezone()
    date_trailing = template.date_trailing[:_HEADER_DATE_TRAILING_BYTES].ljust(
        _HEADER_DATE_TRAILING_BYTES, b"\x00"
    )
    output = bytearray(struct.pack("<II", 7, len(clean_title)))
    output.extend(clean_title.encode("utf-16le"))
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
    output.extend(date_trailing)
    output.extend(creator_tag)
    output.extend(struct.pack("<I", len(clean_creator)))
    output.extend(clean_creator.encode("utf-16le"))
    output.extend(template.section_prefix[:_HEADER_SECTION_PREFIX_BYTES].ljust(_HEADER_SECTION_PREFIX_BYTES, b"\x00"))
    output.extend(b"\x01\x02" + b"\x00" * 7)
    output.extend(struct.pack("<II", int(placement_count), int(car_id)))
    output.extend(guid)
    output.extend(template.trailing)
    parsed = parse_fh6_header(bytes(output))
    if parsed.title != clean_title or parsed.car_id != car_id or parsed.type_value != placement_count:
        raise FullLiveryInstallError("Destination FH6 header failed independent verification.")
    if parsed.creator_tag != creator_tag or parsed.asset_guid != guid:
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


def _containers_roots(scan_roots: Iterable[Path | str]) -> list[Path]:
    found: dict[str, Path] = {}
    for raw in scan_roots:
        root = Path(raw)
        candidates: list[Path] = []
        if root.is_dir() and root.name.casefold() == "containersroot":
            candidates.append(root)
        if root.is_dir():
            try:
                candidates.extend(path for path in root.rglob("ContainersRoot") if path.is_dir())
            except OSError:
                pass
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            found[str(resolved).casefold()] = resolved
    return sorted(found.values(), key=lambda path: str(path).casefold())


def inspect_destination_identity(containers_root: Path | str, *, car_id: int) -> DestinationIdentity:
    root = Path(containers_root).resolve()
    if not root.is_dir() or root.name.casefold() != "containersroot":
        raise FullLiveryInstallError("Choose an FH6 ContainersRoot save folder.")
    records: list[tuple[int, bool, Path, bytes, HeaderMetadata]] = []
    creator_tags: set[bytes] = set()
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        source = folder / "C_livery"
        header_path = folder / "header"
        if not source.is_file() or not header_path.is_file():
            continue
        try:
            payload = unwrap_forza_container(source)
            privacy = inspect_clivery_privacy(payload)
            if not privacy["source_owned"]:
                continue
            source_car_id = _read_u32(payload, _CLIVERY_CAR_ID_OFFSET, "C_livery car identity")
            tag = _clivery_creator_tag(payload)
            header = parse_fh6_header(header_path.read_bytes())
            modified = max(source.stat().st_mtime_ns, header_path.stat().st_mtime_ns)
        except (OSError, FullLiveryInstallError, ValueError, zlib.error):
            continue
        creator_tags.add(tag)
        records.append((modified, source_car_id == car_id, folder, tag, header))
    if not records:
        raise FullLiveryInstallError(
            "No owned FH6 livery was found in this account save. Save one personal livery in FH6 first."
        )
    if len(creator_tags) != 1:
        raise FullLiveryInstallError(
            "This FH6 save contains conflicting local ownership identities. Choose the exact account ContainersRoot."
        )
    records.sort(key=lambda row: (row[1], row[0]), reverse=True)
    modified, _, folder, tag, header = records[0]
    return DestinationIdentity(root, folder, tag, header.creator_name, header, modified)


def select_destination_identity(scan_roots: Iterable[Path | str], *, car_id: int) -> DestinationIdentity:
    identities: list[DestinationIdentity] = []
    for root in _containers_roots(scan_roots):
        try:
            identities.append(inspect_destination_identity(root, car_id=car_id))
        except FullLiveryInstallError:
            continue
    if not identities:
        raise FullLiveryInstallError(
            "No writable FH6 account save with an owned livery was found. Choose that account's ContainersRoot folder."
        )
    identity_tags = {item.creator_tag for item in identities}
    if len(identity_tags) != 1:
        raise FullLiveryInstallError(
            "More than one FH6 account save was found. Choose the exact account's ContainersRoot folder."
        )
    identities.sort(key=lambda item: item.latest_owned_mtime_ns, reverse=True)
    return identities[0]


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


def _published_header_as_draft(header: HeaderMetadata) -> HeaderMetadata:
    return replace(header, published=False, description="")


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
    identity = select_destination_identity(scan_roots, car_id=car_id)
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
    destination_template = replace(
        _published_header_as_draft(source_header),
        creator_name=identity.creator_name,
    )
    header = build_destination_header(
        destination_template,
        title=title,
        car_id=car_id,
        placement_count=placement_count,
        creator_tag=identity.creator_tag,
        now=moment,
    )
    container = _wrap_payload(rewritten_payload)
    if unwrap_forza_container_bytes(container, "staged FH6 livery") != rewritten_payload:
        raise FullLiveryInstallError("Staged FH6 C_livery failed compression verification.")
    root = identity.containers_root
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
        "template_folder_name": identity.template_folder.name,
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
        os.replace(staging, final_folder)
        committed = True
        installed_payload = unwrap_forza_container(final_folder / "C_livery")
        installed_header = parse_fh6_header((final_folder / "header").read_bytes())
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
