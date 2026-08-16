from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
import shutil
import struct
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from PIL import Image

from tools.cgroup.forza_source_decoder import (
    LIVERY_SECTION_NAMES,
    clivery_to_layers,
    extract_livery_payload,
    inspect_clivery_privacy,
    layers_to_kfps_json_layers,
    unwrap_forza_container,
    unwrap_forza_container_bytes,
)

from .vehicle_assets import (
    VehicleAsset,
    inspect_vehicle_archive,
    load_or_build_vehicle_asset_index,
    read_projection_metadata,
)
from .raster_decals import FH6RasterDecalResolver, RasterDecalError


PACKAGE_FORMAT = "kfps_full_livery_package_v1"
PACKAGE_EXTENSION = ".kfpslivery"
PRIVATE_PREVIEW_FORMAT = "kfps_local_livery_preview_v1"
PRIVATE_PREVIEW_EXTENSION = ".kfpspreview"
# Bump whenever decoding, validation, or section rendering changes derived data.
PACKAGE_COMPILER_REVISION = 8
MAX_PACKAGE_FILES = 256
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024


class FullLiveryPackageError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True) + "\n").encode("utf-8")


def _json_from_bytes(data: bytes) -> Any:
    return json.loads(
        data.decode("utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def _png_pixels_match(first: bytes, second: bytes) -> bool:
    with Image.open(io.BytesIO(first)) as first_image, Image.open(io.BytesIO(second)) as second_image:
        return (
            first_image.size == second_image.size
            and first_image.convert("RGBA").tobytes() == second_image.convert("RGBA").tobytes()
        )


def _safe_member_name(name: str) -> str:
    normalized = str(PurePosixPath(str(name).replace("\\", "/")))
    path = PurePosixPath(normalized)
    if not normalized or normalized.startswith("/") or ".." in path.parts or ":" in path.parts[0]:
        raise FullLiveryPackageError(f"unsafe package member path: {name!r}")
    return normalized


def _canonical_package_id(value: Any) -> str:
    try:
        parsed = uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise FullLiveryPackageError("The package identifier is invalid.") from exc
    canonical = str(parsed)
    if str(value) != canonical:
        raise FullLiveryPackageError("The package identifier is not canonical.")
    return canonical


def _decode_livery_contract(payload: bytes) -> tuple[dict[str, Any], dict[str, Any], list[int], dict[str, Any]]:
    layers, report = clivery_to_layers(payload)
    json_layers, identity_warnings = layers_to_kfps_json_layers(layers, game="fh6")
    _, counts, payload_meta = extract_livery_payload(payload)
    warnings = list(report.get("warnings") or [])
    warnings.extend(identity_warnings)
    report = {**report, "warnings": warnings, "identity_warnings": identity_warnings}
    contract = {
        "format": "kfps_full_livery_layers_v1",
        "game": "fh6",
        "target_car_id": struct.unpack_from("<I", payload, 0x10)[0],
        "section_order": list(LIVERY_SECTION_NAMES),
        "section_counts": dict(zip(LIVERY_SECTION_NAMES, counts)),
        "layers": json_layers,
    }
    return contract, report, counts, payload_meta


def _section_layers(layers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_section = {section: [] for section in LIVERY_SECTION_NAMES}
    for layer in layers:
        section = str(layer.get("source_section") or "")
        if section not in by_section:
            raise FullLiveryPackageError(f"A decoded layer uses unsupported livery section {section!r}.")
        by_section[section].append(layer)
    return by_section


def _render_livery_sections(
    layers: list[dict[str, Any]],
    *,
    game_folder: Path | str | None,
    warnings: list[str] | None = None,
    cancel_event=None,
) -> tuple[dict[str, bytes], bool]:
    from json_preview_renderer import render_typecode_layers_canvas

    section_map = _section_layers(layers)
    has_raster_logos = any(layer.get("is_raster_logo") for layer in layers)
    raster_resolver = None
    raster_verified = not has_raster_logos
    if has_raster_logos and game_folder:
        try:
            raster_resolver = FH6RasterDecalResolver(game_folder)
            raster_verified = True
        except RasterDecalError as exc:
            if warnings is not None:
                warnings.append(f"built-in decal rendering unavailable: {exc}")
    elif has_raster_logos and warnings is not None:
        warnings.append("built-in decal rendering unavailable: choose the local FH6 game or Content folder")

    rendered_sections: dict[str, bytes] = {}
    for section in LIVERY_SECTION_NAMES:
        if cancel_event is not None and cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        current = section_map[section]
        if not current:
            continue
        try:
            rendered = render_typecode_layers_canvas(
                current,
                raster_resolver=raster_resolver,
                cancel_event=cancel_event,
                strict_assets=True,
            )
        except concurrent.futures.CancelledError:
            raise
        except Exception as exc:
            raise FullLiveryPackageError(f"Could not render the {section} livery section: {exc}") from exc
        if not rendered:
            raise FullLiveryPackageError(f"The {section} livery section produced no preview.")
        try:
            with Image.open(io.BytesIO(rendered)) as image:
                if image.size != (2048, 1024) or image.format != "PNG":
                    raise FullLiveryPackageError(
                        f"The {section} livery section preview has an invalid image contract."
                    )
                image.verify()
        except FullLiveryPackageError:
            raise
        except Exception as exc:
            raise FullLiveryPackageError(f"The {section} livery section preview is unreadable.") from exc
        rendered_sections[section] = rendered
    return rendered_sections, raster_verified


def _read_header_title(header: bytes) -> str:
    if len(header) < 8:
        return ""
    units = struct.unpack_from("<I", header, 4)[0]
    if units <= 0 or units > 4096 or 8 + units * 2 > len(header):
        return ""
    return header[8 : 8 + units * 2].decode("utf-16le", errors="replace").strip("\x00 \t\r\n")


def _target_policies(car_id: int) -> dict[str, Any]:
    common_discard = ["inspection-mesh", "inspection-projection", "preview"]
    return {
        "fh6": {
            "status": "exact-source-preserved",
            "strategy": "preserve-fh6-container",
            "requires_target_car_id": car_id,
            "keep_roles": ["source-container", "source-header", "canonical-layers"],
            "translate": ["destination-save-identity", "header-guid", "creator-metadata-when-requested"],
            "discard_roles_on_game_install": common_discard,
        },
        "fh5": {
            "status": "recompile-required-not-implemented",
            "strategy": "rebuild-sections-for-target-car",
            "keep_roles": ["canonical-layers"],
            "translate": ["target-car-id", "shape-identities", "section-projection", "header-dialect"],
            "discard_roles": ["source-container", "source-header", *common_discard],
        },
        "fh4": {
            "status": "recompile-required-not-implemented",
            "strategy": "rebuild-sections-for-target-car",
            "keep_roles": ["canonical-layers"],
            "translate": ["target-car-id", "shape-identities", "section-projection", "header-dialect"],
            "discard_roles": ["source-container", "source-header", *common_discard],
        },
        "fm8": {
            "status": "blocked-until-livery-dialect-encoder-exists",
            "strategy": "none",
            "keep_roles": ["canonical-layers"],
            "translate": ["all-livery-sections", "target-car-id", "shape-identities", "header-dialect"],
            "discard_roles": ["source-container", "source-header", *common_discard],
        },
    }


def compatibility_decision(
    manifest: dict[str, Any],
    target_game: str,
    *,
    target_car_id: int | None = None,
) -> dict[str, Any]:
    """Resolve the package policy for a concrete destination.

    This deliberately describes only transformations KFPS can prove. It never
    presents preserved canonical artwork as an installable cross-game livery.
    """
    game = str(target_game or "").strip().casefold()
    policies = manifest.get("compatibility") or {}
    policy = dict(policies.get(game) or {})
    source_car_id = int((manifest.get("livery") or {}).get("target_car_id") or 0)
    requested_car_id = int(target_car_id or source_car_id)
    if not policy:
        return {
            "target_game": game,
            "target_car_id": requested_car_id,
            "status": "unsupported-target",
            "installable": False,
            "keep_roles": ["canonical-layers"],
            "translate": [],
            "discard_roles": [],
            "reason": "No package policy exists for this target system.",
        }

    decision = {
        "target_game": game,
        "target_car_id": requested_car_id,
        **policy,
        "installable": False,
        "installation_eligible": False,
    }
    if game == "fh6" and requested_car_id == source_car_id:
        decision["installation_eligible"] = True
        decision["installable"] = True
        decision["status"] = "exact-car-install-ready"
        decision["reason"] = (
            "The package targets this exact FH6 car. KFPS can preserve the artwork, rewrite only the "
            "destination account metadata, and install it as a new local livery."
        )
    elif game == "fh6":
        decision["status"] = "different-car-blocked"
        decision["reason"] = (
            "Full-livery installation is restricted to the exact car declared by the package."
        )
    else:
        decision["reason"] = (
            "Canonical section artwork remains available, but this destination needs a verified "
            "livery encoder and target-car projection before installation."
        )
    return decision


def _files_manifest(members: dict[str, bytes]) -> list[dict[str, Any]]:
    roles = {
        "source/fh6/C_livery": "source-container",
        "source/fh6/header": "source-header",
        "source/fh6/bigThumb.webp": "source-thumbnail",
        "livery/layers.json": "canonical-layers",
        "mesh/vehicle.json": "inspection-mesh-metadata",
        "projection/index.json": "inspection-projection-metadata",
        "projection/vehicle-map.json": "vehicle-projection-contract",
    }
    result = []
    for name, data in sorted(members.items()):
        role = roles.get(name)
        if role is None:
            if name.startswith("projection/source/"):
                role = "inspection-projection"
            elif name.startswith("mesh/"):
                role = "inspection-mesh"
            elif name.startswith("projection/rendered/"):
                role = "livery-section-preview"
            elif name.startswith("preview/"):
                role = "preview"
            else:
                role = "package-data"
        result.append({"path": name, "role": role, "size": len(data), "sha256": _sha256(data)})
    return result


def _create_livery_artifact(
    source: Path | str,
    output: Path | str,
    *,
    game_folder: Path | str | None = None,
    vehicle_index_cache: Path | str | None = None,
    model_code_override: str = "",
    private_preview: bool = False,
    _allow_unowned_test_preview: bool = False,
    _cancel_event=None,
    extra_members: dict[str, bytes] | None = None,
    title_override: str = "",
) -> dict[str, Any]:
    if _allow_unowned_test_preview and not private_preview:
        raise FullLiveryPackageError("The unowned-source override is restricted to private test previews.")
    source_path = Path(source)
    if source_path.is_dir():
        source_path = source_path / "C_livery"
    if source_path.name.casefold() != "c_livery" or not source_path.is_file():
        raise FullLiveryPackageError("Choose an FH6 C_livery file or its containing Livery_* folder.")

    raw_container = source_path.read_bytes()
    if _cancel_event is not None and _cancel_event.is_set():
        raise concurrent.futures.CancelledError()
    payload = unwrap_forza_container(source_path)
    if len(payload) < 0x1A or payload[:4] != b"vlrc":
        raise FullLiveryPackageError("The selected file is not an FH6 C_livery container.")
    source_state = struct.unpack_from("<I", payload, 0x08)[0]
    privacy = inspect_clivery_privacy(payload)
    if not privacy["source_owned"] and not _allow_unowned_test_preview:
        raise FullLiveryPackageError("This full livery belongs to another player and cannot be opened or exported by KFPS.")
    if privacy["contains_foreign_groups"] and not private_preview:
        raise FullLiveryPackageError(
            "This livery contains vinyl groups created by another player. Remove every foreign vinyl group in FH6 "
            "and save the livery again before exporting it from KFPS."
        )
    car_id = struct.unpack_from("<I", payload, 0x10)[0]
    category_state = struct.unpack_from("<I", payload, 0x14)[0]
    layers, decode_report, counts, payload_meta = _decode_livery_contract(payload)
    layers_by_section = _section_layers(layers["layers"])
    for section, declared_count in zip(LIVERY_SECTION_NAMES, counts):
        if len(layers_by_section[section]) != int(declared_count):
            raise FullLiveryPackageError(
                f"The {section} livery section decoded {len(layers_by_section[section])} of "
                f"{int(declared_count)} declared placements."
            )
    header_path = source_path.parent / "header"
    header = header_path.read_bytes() if header_path.is_file() else b""
    thumbnail_path = source_path.parent / "bigThumb.webp"
    thumbnail = thumbnail_path.read_bytes() if thumbnail_path.is_file() else b""
    if thumbnail:
        try:
            with Image.open(io.BytesIO(thumbnail)) as image:
                if image.format != "WEBP" or image.size != (670, 376):
                    raise FullLiveryPackageError("The FH6 livery thumbnail has invalid dimensions.")
                image.verify()
        except FullLiveryPackageError:
            raise
        except Exception as exc:
            raise FullLiveryPackageError("The FH6 livery thumbnail is unreadable.") from exc
    title = title_override.strip() or _read_header_title(header) or source_path.parent.name

    vehicle: VehicleAsset | None = None
    vehicle_meta: dict[str, Any] = {
        "car_id": car_id,
        "model_code": model_code_override.strip(),
        "resolution": "manual" if model_code_override.strip() else "unresolved",
        "portable_mesh": False,
    }
    projection_metadata: dict[str, Any] = {}
    if game_folder:
        index = load_or_build_vehicle_asset_index(game_folder, vehicle_index_cache)
        vehicle = index.get(car_id)
        if vehicle:
            vehicle_meta = inspect_vehicle_archive(vehicle)
            vehicle_meta["resolution"] = "local-game-archive-index"
            vehicle_meta["portable_mesh"] = False
            projection_metadata = read_projection_metadata(vehicle)
        elif not model_code_override:
            vehicle_meta["resolution_detail"] = "No local car archive advertised the livery target ID."

    section_textures, raster_verified = _render_livery_sections(
        layers["layers"],
        game_folder=game_folder,
        warnings=decode_report.setdefault("warnings", []),
        cancel_event=_cancel_event,
    )
    projection_index = {
        "format": "kfps_fh6_projection_source_v1",
        "model_code": vehicle_meta.get("model_code", ""),
        "source_inventory": projection_metadata.get("source_inventory", []),
        "vehicle_map_path": "projection/vehicle-map.json" if projection_metadata else "",
        "decoded_for_viewer": False,
    }
    members: dict[str, bytes] = {
        "mesh/vehicle.json": _json_bytes(vehicle_meta),
        "projection/index.json": _json_bytes(projection_index),
    }
    if not private_preview:
        members["source/fh6/C_livery"] = raw_container
        members["livery/layers.json"] = _json_bytes(layers)
        if header:
            members["source/fh6/header"] = header
        if thumbnail:
            members["source/fh6/bigThumb.webp"] = thumbnail
    if projection_metadata:
        members["projection/vehicle-map.json"] = _json_bytes(projection_metadata)
    for section, data in section_textures.items():
        members[f"projection/rendered/{section}.png"] = data
    projection_index["rendered_sections"] = [
        {"section": section, "path": f"projection/rendered/{section}.png", "width": 2048, "height": 1024}
        for section in section_textures
    ]
    projection_index["decoded_for_viewer"] = bool(section_textures)
    projection_index["source_exact"] = True
    projection_index["native_raster_verified"] = raster_verified
    members["mesh/vehicle.json"] = _json_bytes(vehicle_meta)
    members["projection/index.json"] = _json_bytes(projection_index)
    for name, data in (extra_members or {}).items():
        safe_name = _safe_member_name(name)
        if safe_name == "manifest.json" or safe_name in members:
            raise FullLiveryPackageError(f"duplicate or reserved package member: {safe_name}")
        members[safe_name] = bytes(data)

    source_manifest = {
        "game": "fh6",
        "kind": (
            "test-only-unowned-preview"
            if _allow_unowned_test_preview
            else ("local-preview" if private_preview else "C_livery")
        ),
        "source_folder_name": source_path.parent.name,
        "source_state": source_state,
        "owned": bool(privacy["source_owned"]),
    }
    if not private_preview:
        source_manifest.update({
            "container_sha256": _sha256(raw_container),
            "payload_sha256": _sha256(payload),
            "payload_size": len(payload),
            "container_version": struct.unpack_from("<I", payload, 0x04)[0],
            "locked": False,
            "category_state": category_state,
        })

    manifest = {
        "format": PRIVATE_PREVIEW_FORMAT if private_preview else PACKAGE_FORMAT,
        "format_version": 1,
        "compiler_revision": PACKAGE_COMPILER_REVISION,
        "package_id": str(uuid.uuid4()),
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": source_manifest,
        "livery": {
            "title": title,
            "target_car_id": car_id,
            "logical_placement_count": sum(counts),
            "decoded_layer_count": len(layers["layers"]),
            "section_counts": dict(zip(LIVERY_SECTION_NAMES, counts)),
            "decode_warnings": decode_report.get("warnings", []),
            "payload_offsets": payload_meta,
        },
        "vehicle": vehicle_meta,
        "sharing": {
            "exportable": not private_preview,
            "preview_only": private_preview,
            "test_only_unowned_preview": bool(_allow_unowned_test_preview),
            "contains_foreign_vinyl_groups": bool(privacy["contains_foreign_groups"]),
            "foreign_vinyl_group_count": int(privacy["foreign_group_count"]),
            "external_game_assets_embedded": False,
            "mesh_policy": "resolve matching car mesh from the recipient's own local game installation",
            "opaque_source_record": not private_preview,
            "source_identity_policy": (
                "private rendered inspection only"
                if private_preview
                else "rewrite destination-owned identity and creator metadata during supported installation"
            ),
        },
        "compatibility": {} if private_preview else _target_policies(car_id),
        "files": _files_manifest(members),
    }
    manifest_bytes = _json_bytes(manifest)
    output_path = Path(output)
    extension = PRIVATE_PREVIEW_EXTENSION if private_preview else PACKAGE_EXTENSION
    if output_path.suffix.casefold() != extension:
        output_path = output_path.with_suffix(extension)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_fd, temporary_name = tempfile.mkstemp(prefix=output_path.name + ".", suffix=".tmp", dir=output_path.parent)
    os.close(temporary_fd)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.writestr("manifest.json", manifest_bytes)
            for name, data in sorted(members.items()):
                bundle.writestr(name, data)
        if private_preview:
            validate_livery_inspection_artifact(temporary_path)
        else:
            validate_full_livery_package(
                temporary_path,
                game_folder=game_folder,
                verify_previews=True,
            )
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return {**manifest, "package_path": str(output_path.resolve())}


def create_full_livery_package(
    source: Path | str,
    output: Path | str,
    *,
    game_folder: Path | str | None = None,
    vehicle_index_cache: Path | str | None = None,
    model_code_override: str = "",
    extra_members: dict[str, bytes] | None = None,
    title_override: str = "",
) -> dict[str, Any]:
    return _create_livery_artifact(
        source,
        output,
        game_folder=game_folder,
        vehicle_index_cache=vehicle_index_cache,
        model_code_override=model_code_override,
        private_preview=False,
        extra_members=extra_members,
        title_override=title_override,
    )


def create_local_livery_preview(
    source: Path | str,
    output: Path | str,
    *,
    game_folder: Path | str | None = None,
    vehicle_index_cache: Path | str | None = None,
    model_code_override: str = "",
    _allow_unowned_test_preview: bool = False,
    _cancel_event=None,
) -> dict[str, Any]:
    return _create_livery_artifact(
        source,
        output,
        game_folder=game_folder,
        vehicle_index_cache=vehicle_index_cache,
        model_code_override=model_code_override,
        private_preview=True,
        _allow_unowned_test_preview=_allow_unowned_test_preview,
        _cancel_event=_cancel_event,
    )


def _read_manifest(bundle: zipfile.ZipFile, *, allow_private_preview: bool = False) -> dict[str, Any]:
    try:
        info = bundle.getinfo("manifest.json")
    except KeyError as exc:
        raise FullLiveryPackageError("The package has no manifest.json.") from exc
    if info.file_size > MAX_MANIFEST_BYTES:
        raise FullLiveryPackageError("The package manifest is too large.")
    try:
        manifest = _json_from_bytes(bundle.read(info))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FullLiveryPackageError("The package manifest is invalid.") from exc
    allowed_formats = {PACKAGE_FORMAT}
    if allow_private_preview:
        allowed_formats.add(PRIVATE_PREVIEW_FORMAT)
    if not isinstance(manifest, dict) or manifest.get("format") not in allowed_formats:
        raise FullLiveryPackageError("This is not a supported KFPS full-livery package.")
    if manifest.get("format_version") != 1:
        raise FullLiveryPackageError("This package uses an unsupported full-livery format version.")
    return manifest


def _validate_livery_artifact(
    path: Path | str,
    *,
    allow_private_preview: bool,
    allow_legacy: bool = False,
    game_folder: Path | str | None = None,
    verify_previews: bool = False,
) -> dict[str, Any]:
    package = Path(path)
    try:
        with zipfile.ZipFile(package) as bundle:
            infos = bundle.infolist()
            if len(infos) > MAX_PACKAGE_FILES:
                raise FullLiveryPackageError("The package contains too many files.")
            total = 0
            seen: set[str] = set()
            for info in infos:
                safe = _safe_member_name(info.filename)
                folded = safe.casefold()
                if folded in seen:
                    raise FullLiveryPackageError(f"The package contains duplicate path {safe}.")
                seen.add(folded)
                if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
                    raise FullLiveryPackageError(f"Package member {safe} exceeds the size limit.")
                total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise FullLiveryPackageError("The expanded package exceeds the size limit.")
            manifest = _read_manifest(bundle, allow_private_preview=allow_private_preview)
            private_preview = manifest.get("format") == PRIVATE_PREVIEW_FORMAT
            _canonical_package_id(manifest.get("package_id"))
            try:
                compiler_revision = int(manifest.get("compiler_revision") or 0)
            except (TypeError, ValueError) as exc:
                raise FullLiveryPackageError("The package compiler revision is invalid.") from exc
            if compiler_revision > PACKAGE_COMPILER_REVISION:
                raise FullLiveryPackageError(
                    "This package was created by a newer KFPS livery compiler and cannot be opened safely."
                )
            if compiler_revision != PACKAGE_COMPILER_REVISION and not allow_legacy:
                raise FullLiveryPackageError(
                    f"This package uses livery compiler revision {compiler_revision}; "
                    f"revision {PACKAGE_COMPILER_REVISION} is required. Upgrade the package before opening it."
                )
            records = manifest.get("files")
            if not isinstance(records, list):
                raise FullLiveryPackageError("The package file manifest is missing.")
            recorded_names: set[str] = set()
            for record in records:
                if not isinstance(record, dict):
                    raise FullLiveryPackageError("The package file manifest contains an invalid record.")
                name = _safe_member_name(str(record.get("path", "")))
                if name.casefold() in recorded_names:
                    raise FullLiveryPackageError(f"The package manifest repeats member {name}.")
                recorded_names.add(name.casefold())
                try:
                    data = bundle.read(name)
                except KeyError as exc:
                    raise FullLiveryPackageError(f"Required package member {name} is missing.") from exc
                if len(data) != int(record.get("size", -1)) or _sha256(data) != record.get("sha256"):
                    raise FullLiveryPackageError(f"Package member {name} failed its integrity check.")
            required = {"mesh/vehicle.json", "projection/index.json"}
            if not private_preview:
                required.update({"source/fh6/C_livery", "livery/layers.json"})
            if not required.issubset({str(record.get("path", "")) for record in records if isinstance(record, dict)}):
                raise FullLiveryPackageError("The package is missing required full-livery data.")
            archive_names = {info.filename.casefold() for info in infos if info.filename != "manifest.json"}
            if archive_names != recorded_names:
                raise FullLiveryPackageError("The package contains untracked or unlisted members.")

            source = manifest.get("source") or {}
            livery = manifest.get("livery") or {}
            try:
                vehicle = _json_from_bytes(bundle.read("mesh/vehicle.json"))
                projection = _json_from_bytes(bundle.read("projection/index.json"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise FullLiveryPackageError("Canonical layer or vehicle metadata is invalid.") from exc
            actual_car_id = int(livery.get("target_car_id") or -1)
            if private_preview:
                forbidden = {"source/fh6/c_livery", "source/fh6/header", "livery/layers.json"}
                if forbidden.intersection(recorded_names):
                    raise FullLiveryPackageError("A private livery preview contains shareable source data.")
                sharing = manifest.get("sharing") or {}
                if sharing.get("exportable") is not False or sharing.get("preview_only") is not True:
                    raise FullLiveryPackageError("The private livery preview policy is invalid.")
                test_only_unowned = sharing.get("test_only_unowned_preview") is True
                if source.get("owned") is not True:
                    if not test_only_unowned or source.get("kind") != "test-only-unowned-preview":
                        raise FullLiveryPackageError("The private livery preview is not an owned source.")
                elif test_only_unowned:
                    raise FullLiveryPackageError("The private livery preview has an inconsistent test-only policy.")
            else:
                raw_container = bundle.read("source/fh6/C_livery")
                payload = raw_container if raw_container.startswith(b"vlrc") else unwrap_forza_container_bytes(raw_container, package)
                if len(payload) < 0x1A or payload[:4] != b"vlrc":
                    raise FullLiveryPackageError("The preserved source member is not an FH6 C_livery record.")
                privacy = inspect_clivery_privacy(payload)
                if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
                    raise FullLiveryPackageError(
                        "This package contains artwork created by another player and cannot be shared through KFPS."
                    )
                actual_car_id = struct.unpack_from("<I", payload, 0x10)[0]
                actual_state = struct.unpack_from("<I", payload, 0x08)[0]
                if actual_car_id != int(livery.get("target_car_id") or -1):
                    raise FullLiveryPackageError("The manifest car identity does not match the preserved source record.")
                if actual_state != int(source.get("source_state") if source.get("source_state") is not None else -1):
                    raise FullLiveryPackageError("The manifest source state does not match the preserved source record.")
                if _sha256(raw_container) != source.get("container_sha256") or _sha256(payload) != source.get("payload_sha256"):
                    raise FullLiveryPackageError("The source identity hashes do not match the preserved record.")
                try:
                    layers = _json_from_bytes(bundle.read("livery/layers.json"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise FullLiveryPackageError("Canonical layer or vehicle metadata is invalid.") from exc
                if not isinstance(layers, dict) or layers.get("format") != "kfps_full_livery_layers_v1":
                    raise FullLiveryPackageError("Canonical layer data uses an unsupported format.")
                if int(layers.get("target_car_id") or -1) != actual_car_id:
                    raise FullLiveryPackageError("Canonical layer data targets a different car.")
                if compiler_revision == PACKAGE_COMPILER_REVISION:
                    if "source/fh6/bigthumb.webp" in recorded_names:
                        try:
                            with Image.open(io.BytesIO(bundle.read("source/fh6/bigThumb.webp"))) as image:
                                if image.format != "WEBP" or image.size != (670, 376):
                                    raise FullLiveryPackageError("The FH6 source thumbnail is invalid.")
                                image.verify()
                        except FullLiveryPackageError:
                            raise
                        except Exception as exc:
                            raise FullLiveryPackageError("The FH6 source thumbnail is unreadable.") from exc
                    try:
                        canonical_layers, decode_report, counts, payload_meta = _decode_livery_contract(payload)
                    except Exception as exc:
                        raise FullLiveryPackageError(
                            "The preserved source record could not be decoded by the current livery compiler."
                        ) from exc
                    if layers != canonical_layers:
                        raise FullLiveryPackageError(
                            "Canonical layer data does not match the preserved FH6 source record."
                        )
                    expected_counts = dict(zip(LIVERY_SECTION_NAMES, counts))
                    if livery.get("section_counts") != expected_counts:
                        raise FullLiveryPackageError("Manifest section counts do not match the preserved source record.")
                    if int(livery.get("logical_placement_count") or 0) != sum(counts):
                        raise FullLiveryPackageError("Manifest placement count does not match the preserved source record.")
                    if int(livery.get("decoded_layer_count") or 0) != len(canonical_layers["layers"]):
                        raise FullLiveryPackageError("Manifest decoded layer count does not match the preserved source record.")
                    if livery.get("payload_offsets") != payload_meta:
                        raise FullLiveryPackageError("Manifest source offsets do not match the preserved source record.")
                    expected_sections = [
                        section for section, count in zip(LIVERY_SECTION_NAMES, counts) if int(count) > 0
                    ]
                    if not isinstance(projection, dict):
                        raise FullLiveryPackageError("The projection metadata is invalid.")
                    rendered = projection.get("rendered_sections")
                    if not isinstance(rendered, list):
                        raise FullLiveryPackageError("The package has no complete rendered-section inventory.")
                    rendered_sections: list[str] = []
                    for record in rendered:
                        if not isinstance(record, dict):
                            raise FullLiveryPackageError("The rendered-section inventory is invalid.")
                        section = str(record.get("section") or "")
                        member = str(record.get("path") or "")
                        if section not in LIVERY_SECTION_NAMES or member != f"projection/rendered/{section}.png":
                            raise FullLiveryPackageError("The rendered-section inventory contains an invalid entry.")
                        if int(record.get("width") or 0) != 2048 or int(record.get("height") or 0) != 1024:
                            raise FullLiveryPackageError("A rendered-section declaration has invalid dimensions.")
                        if section in rendered_sections:
                            raise FullLiveryPackageError("The rendered-section inventory contains a duplicate section.")
                        rendered_sections.append(section)
                        try:
                            rendered_data = bundle.read(member)
                            with Image.open(io.BytesIO(rendered_data)) as image:
                                if image.size != (2048, 1024) or image.format != "PNG":
                                    raise FullLiveryPackageError(
                                        f"The rendered {section} livery section has invalid dimensions."
                                    )
                                image.verify()
                        except FullLiveryPackageError:
                            raise
                        except Exception as exc:
                            raise FullLiveryPackageError(
                                f"The rendered {section} livery section is missing or unreadable."
                            ) from exc
                    if rendered_sections != expected_sections:
                        raise FullLiveryPackageError(
                            "The package does not contain one complete render for every populated livery section."
                        )
                    if projection.get("source_exact") is not True:
                        raise FullLiveryPackageError("The package does not declare source-exact rendered sections.")
                    if verify_previews:
                        regenerated, raster_verified = _render_livery_sections(
                            canonical_layers["layers"],
                            game_folder=game_folder,
                        )
                        if not raster_verified:
                            raise FullLiveryPackageError(
                                "Choose the local FH6 game folder to verify built-in logo rendering in this package."
                            )
                        for section, expected in regenerated.items():
                            actual = bundle.read(f"projection/rendered/{section}.png")
                            try:
                                pixels_match = _png_pixels_match(actual, expected)
                            except Exception as exc:
                                raise FullLiveryPackageError(
                                    f"The rendered {section} livery section is unreadable."
                                ) from exc
                            if not pixels_match:
                                raise FullLiveryPackageError(
                                    f"The rendered {section} livery section does not match the preserved source record."
                                )
            manifest_vehicle = manifest.get("vehicle") or {}
            if not isinstance(vehicle, dict) or int(vehicle.get("car_id") or -1) != actual_car_id:
                raise FullLiveryPackageError("Vehicle metadata does not match the source car identity.")
            if int(manifest_vehicle.get("car_id") or -1) != actual_car_id:
                raise FullLiveryPackageError("Manifest vehicle metadata does not match the source car identity.")
            if str(manifest_vehicle.get("model_code") or "") != str(vehicle.get("model_code") or ""):
                raise FullLiveryPackageError("Manifest and packaged vehicle model identities disagree.")
            embedded_mesh = "mesh/model.glb" in {str(record.get("path", "")) for record in records}
            if compiler_revision == PACKAGE_COMPILER_REVISION:
                if embedded_mesh or bool(vehicle.get("portable_mesh")):
                    raise FullLiveryPackageError(
                        "Current livery packages must resolve the chassis from the recipient's local game installation."
                    )
                sharing = manifest.get("sharing") or {}
                if sharing.get("external_game_assets_embedded") is not False:
                    raise FullLiveryPackageError("The package game-asset policy is invalid.")
            return manifest
    except FullLiveryPackageError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, KeyError, TypeError, ValueError, struct.error) as exc:
        raise FullLiveryPackageError("The selected file is not a readable ZIP-based livery package.") from exc


def validate_full_livery_package(
    path: Path | str,
    *,
    game_folder: Path | str | None = None,
    verify_previews: bool = False,
) -> dict[str, Any]:
    return _validate_livery_artifact(
        path,
        allow_private_preview=False,
        game_folder=game_folder,
        verify_previews=verify_previews,
    )


def validate_livery_inspection_artifact(path: Path | str) -> dict[str, Any]:
    return _validate_livery_artifact(path, allow_private_preview=True)


def package_compiler_revision(path: Path | str) -> int:
    package = Path(path)
    try:
        with zipfile.ZipFile(package) as bundle:
            manifest = _read_manifest(bundle)
        return int(manifest.get("compiler_revision") or 0)
    except FullLiveryPackageError:
        raise
    except (TypeError, ValueError, zipfile.BadZipFile, OSError) as exc:
        raise FullLiveryPackageError("The selected package has no readable compiler revision.") from exc


def migrate_full_livery_package(
    source: Path | str,
    output: Path | str | None = None,
    *,
    game_folder: Path | str | None = None,
    vehicle_index_cache: Path | str | None = None,
) -> dict[str, Any]:
    source_path = Path(source).resolve()
    manifest = _validate_livery_artifact(
        source_path,
        allow_private_preview=False,
        allow_legacy=True,
    )
    revision = int(manifest.get("compiler_revision") or 0)
    if revision == PACKAGE_COMPILER_REVISION:
        current = validate_full_livery_package(
            source_path,
            game_folder=game_folder,
            verify_previews=bool(game_folder),
        )
        target = Path(output).resolve() if output else source_path
        if target != source_path:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
            temporary.unlink(missing_ok=True)
            try:
                shutil.copy2(source_path, temporary)
                validate_full_livery_package(temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return {**current, "package_path": str(target)}

    target = Path(output).resolve() if output else source_path
    title = str((manifest.get("livery") or {}).get("title") or source_path.stem)
    with tempfile.TemporaryDirectory(prefix="kfps-livery-migration-") as temporary:
        source_root = Path(temporary) / "source"
        source_root.mkdir(parents=True)
        with zipfile.ZipFile(source_path) as bundle:
            (source_root / "C_livery").write_bytes(bundle.read("source/fh6/C_livery"))
            if "source/fh6/header" in bundle.namelist():
                (source_root / "header").write_bytes(bundle.read("source/fh6/header"))
        result = create_full_livery_package(
            source_root / "C_livery",
            target,
            game_folder=game_folder,
            vehicle_index_cache=vehicle_index_cache,
            model_code_override=str((manifest.get("vehicle") or {}).get("model_code") or ""),
            title_override=title,
        )
    result["migrated_from_revision"] = revision
    return result


def inspect_full_livery_package(path: Path | str, *, allow_legacy: bool = False) -> dict[str, Any]:
    manifest = _validate_livery_artifact(
        path,
        allow_private_preview=False,
        allow_legacy=allow_legacy,
    )
    return {
        "path": str(Path(path).resolve()),
        "package_id": manifest.get("package_id", ""),
        "title": manifest.get("livery", {}).get("title", ""),
        "game": manifest.get("source", {}).get("game", ""),
        "target_car_id": manifest.get("livery", {}).get("target_car_id", 0),
        "model_code": manifest.get("vehicle", {}).get("model_code", ""),
        "logical_placement_count": manifest.get("livery", {}).get("logical_placement_count", 0),
        "decoded_layer_count": manifest.get("livery", {}).get("decoded_layer_count", 0),
        "portable_mesh": bool(manifest.get("vehicle", {}).get("portable_mesh")),
        "compatibility": manifest.get("compatibility", {}),
    }


def read_package_member(path: Path | str, member: str, *, allow_private_preview: bool = False) -> bytes:
    safe = _safe_member_name(member)
    if allow_private_preview:
        validate_livery_inspection_artifact(path)
    else:
        validate_full_livery_package(path)
    with zipfile.ZipFile(path) as bundle:
        try:
            return bundle.read(safe)
        except KeyError as exc:
            raise FullLiveryPackageError(f"Package member {safe} is missing.") from exc


def iter_package_files(path: Path | str, *, allow_private_preview: bool = False) -> Iterable[str]:
    if allow_private_preview:
        validate_livery_inspection_artifact(path)
    else:
        validate_full_livery_package(path)
    with zipfile.ZipFile(path) as bundle:
        yield from (info.filename for info in bundle.infolist())
