from __future__ import annotations

import hashlib
import os
import shutil
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from tools.cgroup.forza_source_decoder import (
    LIVERY_SECTION_NAMES,
    build_livery_sections,
    extract_livery_payload,
    inspect_clivery_privacy,
    unwrap_forza_container,
)
from tools.livery import (
    PACKAGE_COMPILER_REVISION,
    FullLiveryPackageError,
    create_full_livery_package,
    create_local_livery_preview,
    inspect_full_livery_package,
    install_full_livery_package,
    migrate_full_livery_package,
    package_compiler_revision,
    validate_full_livery_package,
    validate_livery_inspection_artifact,
)
from tools.livery.portable_mesh_converter import (
    LOCAL_CHASSIS_FORMAT_REVISION,
    PortableMeshConverterError,
    convert_vehicle_model_to_glb,
    validate_local_chassis_glb,
)
from tools.livery.render_contract import build_local_livery_atlases
from tools.livery.vehicle_assets import (
    normalize_fh6_game_folder,
    load_or_build_vehicle_asset_index,
    sha256_file,
)

from .catalog import FullLiveryCatalog
from .paths import CACHE_REVISION


SOURCE_INDEX_REVISION = 2
SOURCE_PREVIEW_CACHE_REVISION = 3
INSPECTION_MESH_CACHE_REVISION = LOCAL_CHASSIS_FORMAT_REVISION


@dataclass(frozen=True)
class JobPaths:
    app_root: Path
    inspector_root: Path
    root: Path
    state: Path
    cache: Path
    sessions: Path
    diagnostics: Path
    recovery: Path
    quarantine: Path
    package_root: Path
    settings_file: Path
    catalog_file: Path
    qualification_file: Path
    vehicle_index: Path
    mesh_cache: Path
    render_cache: Path
    preview_cache: Path

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> "JobPaths":
        values = dict(request["paths"])
        paths = cls(**{name: Path(values[name]).resolve() for name in cls.__dataclass_fields__})
        paths.assert_contained()
        return paths

    def assert_contained(self) -> None:
        for candidate in (
            self.state,
            self.cache,
            self.sessions,
            self.diagnostics,
            self.recovery,
            self.quarantine,
            self.settings_file,
            self.catalog_file,
            self.qualification_file,
            self.vehicle_index,
            self.mesh_cache,
            self.render_cache,
            self.preview_cache,
        ):
            candidate.relative_to(self.root)
        self.inspector_root.relative_to(self.app_root)
        self.package_root.relative_to(self.app_root)

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.state,
            self.cache,
            self.sessions,
            self.diagnostics,
            self.recovery,
            self.quarantine,
            self.package_root,
            self.vehicle_index.parent,
            self.mesh_cache,
            self.render_cache,
            self.preview_cache,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _header_title(path: Path) -> str:
    header = path.parent / "header"
    if not header.is_file():
        return ""
    data = header.read_bytes()
    if len(data) < 8:
        return ""
    units = struct.unpack_from("<I", data, 4)[0]
    if units <= 0 or units > 4096 or 8 + units * 2 > len(data):
        return ""
    return data[8 : 8 + units * 2].decode("utf-16le", errors="replace").strip("\x00 \t\r\n")


def _scan_roots(configured_root: str) -> list[Path]:
    if configured_root:
        configured = Path(configured_root)
        if configured.is_dir():
            return [configured.resolve()]
        # A manually selected root is authoritative. Falling back to another
        # drive here would hide its last complete catalog behind unrelated data.
        return []
    candidates = [Path(r"C:\XboxGames\GameSave")]
    for partition in psutil.disk_partitions(all=False):
        candidates.append(Path(partition.mountpoint) / "XboxGames" / "GameSave")
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        resolved = candidate.resolve()
        key = str(resolved).casefold()
        if key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def _source_parser_revision(game_folder: str, vehicle_index: Path) -> int:
    digest = hashlib.sha256()
    digest.update(f"source-index:{SOURCE_INDEX_REVISION}".encode("ascii"))
    digest.update(str(game_folder or "").casefold().encode("utf-8", errors="surrogatepass"))
    try:
        stat = vehicle_index.stat()
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
    except OSError:
        digest.update(b"no-index")
    return int.from_bytes(digest.digest()[:8], "little") & 0x7FFF_FFFF_FFFF_FFFF


def _visible_source_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("_visible"):
        return None
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _source_block_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    foreign = 0
    incomplete = 0
    for row in rows:
        if not row.get("_sourceOwned"):
            continue
        if row.get("_sourceComplete") is False:
            incomplete += 1
        if row.get("_containsForeignGroups") is True:
            foreign += 1
        elif "_containsForeignGroups" not in row and "_sourceComplete" not in row:
            # Revision-1 cache records used exportable=false only for foreign groups.
            foreign += not bool(row.get("exportable"))
    return foreign, incomplete


def refresh_packages(paths: JobPaths, _payload: dict[str, Any], _cancel_event) -> dict[str, Any]:
    catalog = FullLiveryCatalog(paths.catalog_file, paths.quarantine)
    snapshot = catalog.package_snapshot()
    token = f"packages-{time.time_ns()}"
    rows = []
    catalog_records = []
    cache_hits = 0
    rejected = 0
    for package in paths.package_root.glob("*.kfpslivery"):
        if _cancel_event.is_set():
            raise InterruptedError("Package indexing was cancelled.")
        try:
            stat = package.stat()
            revision = package_compiler_revision(package)
            identity = snapshot.get(str(package.resolve()))
            cached = (
                identity.get("row")
                if identity is not None
                and int(identity["size"]) == stat.st_size
                and int(identity["mtime_ns"]) == stat.st_mtime_ns
                and int(identity["compiler_revision"]) == revision
                else None
            )
            if isinstance(cached, dict):
                rows.append(cached)
                cache_hits += 1
                row = cached
            else:
                info = (
                    inspect_full_livery_package(package, allow_legacy=True)
                    if revision != PACKAGE_COMPILER_REVISION
                    else inspect_full_livery_package(package)
                )
                placement_count = int(info.get("logical_placement_count") or 0)
                if placement_count <= 0:
                    continue
                row = {
                    "title": info.get("title") or package.stem,
                    "path": str(package.resolve()),
                    "carId": int(info.get("target_car_id") or 0),
                    "modelCode": info.get("model_code") or "Unresolved car",
                    "placementCount": placement_count,
                    "portableMesh": False,
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "detail": (
                        "Older package; KFPS will update it when opened"
                        if revision != PACKAGE_COMPILER_REVISION
                        else "Shareable artwork; chassis resolved from the local FH6 installation"
                    ),
                    "mtimeNs": int(stat.st_mtime_ns),
                }
                rows.append(row)
            catalog_records.append({
                "path": package,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "compiler_revision": revision,
                "row": row,
            })
        except (OSError, FullLiveryPackageError, ValueError):
            rejected += 1
    removed = catalog.apply_package_scan(token, catalog_records)
    rows.sort(key=lambda row: (int(row.get("mtimeNs") or 0), str(row.get("title") or "").casefold()), reverse=True)
    for row in rows:
        row.pop("mtimeNs", None)
    return {
        "rows": rows,
        "cache_hits": cache_hits,
        "indexed": len(rows) - cache_hits,
        "rejected": rejected,
        "removed": removed,
        "catalog": catalog.stats(),
    }


def link_game(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    normalized = normalize_fh6_game_folder(str(payload.get("folder") or ""))
    if cancel_event.is_set():
        raise InterruptedError("FH6 linking was cancelled.")
    index = load_or_build_vehicle_asset_index(normalized, paths.vehicle_index)
    return {
        "game_folder": str(normalized),
        "vehicle_count": len(index),
    }


def scan_saves(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    roots = _scan_roots(str(payload.get("save_root") or ""))
    catalog = FullLiveryCatalog(paths.catalog_file, paths.quarantine)
    if not roots:
        indexed_rows = [row for row in catalog.source_rows() if row.get("_visible")]
        foreign_blocked, incomplete_blocked = _source_block_counts(indexed_rows)
        return {
            "rows": [visible for row in indexed_rows if (visible := _visible_source_row(row)) is not None],
            "fingerprints": {
                str(row.get("path") or ""): str(row.get("_contentHash") or "")
                for row in indexed_rows
                if row.get("path")
            },
            "roots": [],
            "inspected": 0,
            "rejected": 0,
            "locked": 0,
            "foreign_blocked": foreign_blocked,
            "incomplete_blocked": incomplete_blocked,
            "empty": 0,
            "cache_hits": len(indexed_rows),
            "removed": 0,
            "game_assets_ready": False,
            "stale_index": True,
            "warning": "No FH6 GameSave folder was found. The last complete index is shown; choose the save folder manually.",
            "catalog": catalog.stats(),
        }
    game_folder = str(payload.get("game_folder") or "")
    vehicle_index = {}
    game_asset_error = ""
    if game_folder:
        try:
            vehicle_index = load_or_build_vehicle_asset_index(game_folder, paths.vehicle_index)
        except Exception as exc:
            game_asset_error = str(exc)
    parser_revision = _source_parser_revision(game_folder, paths.vehicle_index)
    snapshot = catalog.source_snapshot(roots)
    token = f"sources-{time.time_ns()}"
    catalog_records = []
    by_hash: dict[str, dict[str, Any]] = {}
    completed_roots: list[Path] = []
    stale_roots: list[Path] = []
    inspected = rejected = hidden = empty = cache_hits = 0
    for root in roots:
        record_start = len(catalog_records)
        prior_by_hash = dict(by_hash)
        prior_counts = (inspected, rejected, hidden, empty, cache_hits)
        try:
            candidates = root.rglob("C_livery")
            for path in candidates:
                if cancel_event.is_set():
                    raise InterruptedError("Save indexing was cancelled.")
                inspected += 1
                try:
                    stat = path.stat()
                    identity = snapshot.get(str(path.resolve()))
                    cached = (
                        identity.get("row")
                        if identity is not None
                        and int(identity["size"]) == stat.st_size
                        and int(identity["mtime_ns"]) == stat.st_mtime_ns
                        and int(identity["parser_revision"]) == parser_revision
                        else None
                    )
                    if isinstance(cached, dict):
                        cache_hits += 1
                        row = cached
                        content_hash = str(identity.get("content_hash") or row.get("_contentHash") or "")
                    else:
                        raw = path.read_bytes()
                        content_hash = hashlib.sha256(raw).hexdigest()
                        decoded = unwrap_forza_container(path)
                        if decoded[:4] != b"vlrc" or len(decoded) < 0x1A:
                            raise ValueError("Not a usable C_livery payload")
                        state = struct.unpack_from("<I", decoded, 0x08)[0]
                        if state == 1:
                            row = {
                                "_visible": False,
                                "_reason": "hidden",
                                "_contentHash": content_hash,
                                "path": str(path.resolve()),
                            }
                        else:
                            privacy = inspect_clivery_privacy(decoded)
                            source_owned = bool(privacy["source_owned"])
                            contains_foreign_groups = bool(privacy["contains_foreign_groups"])
                            car_id = struct.unpack_from("<I", decoded, 0x10)[0]
                            body, counts, _ = extract_livery_payload(decoded)
                            placement_count = sum(counts)
                            if placement_count <= 0:
                                row = {
                                    "_visible": False,
                                    "_reason": "empty",
                                    "_contentHash": content_hash,
                                    "path": str(path.resolve()),
                                }
                            else:
                                layers, _ = build_livery_sections(body, counts)
                                decoded_counts = [
                                    sum(layer.get("section") == section for layer in layers)
                                    for section in LIVERY_SECTION_NAMES
                                ]
                                section_mismatches = [
                                    {
                                        "section": section,
                                        "declared": int(declared),
                                        "decoded": int(actual),
                                    }
                                    for section, declared, actual in zip(
                                        LIVERY_SECTION_NAMES,
                                        counts,
                                        decoded_counts,
                                    )
                                    if int(declared) != int(actual)
                                ]
                                decoded_placement_count = sum(decoded_counts)
                                # Protected foreign groups are intentionally opaque to the
                                # renderer and already fail the ownership gate. Their source
                                # completeness is unknown, rather than damaged.
                                source_complete = (
                                    None if contains_foreign_groups else not section_mismatches
                                )
                                exportable = (
                                    source_owned
                                    and not contains_foreign_groups
                                    and source_complete is True
                                )
                                privacy_reasons = []
                                if contains_foreign_groups:
                                    privacy_reasons.append(
                                        "Remove every foreign vinyl group in FH6 and save the livery again."
                                    )
                                if source_complete is False:
                                    privacy_reasons.append(
                                        f"KFPS decoded {decoded_placement_count:,} of "
                                        f"{placement_count:,} declared placements."
                                    )
                                asset = vehicle_index.get(car_id)
                                row = {
                                    "_visible": True,
                                    "_reason": "",
                                    "_contentHash": content_hash,
                                    "_sourceOwned": source_owned,
                                    "_sourceComplete": source_complete,
                                    "_containsForeignGroups": contains_foreign_groups,
                                    "_mtimeNs": int(stat.st_mtime_ns),
                                    "_priority": 1 if "\\current\\" in str(path).casefold() else 0,
                                    "title": _header_title(path) or path.parent.name,
                                    "path": str(path.resolve()),
                                    "carId": car_id,
                                    "modelCode": asset.model_code if asset else "Unresolved car",
                                    "placementCount": placement_count,
                                    "decodedPlacementCount": decoded_placement_count,
                                    "sourceComplete": source_complete,
                                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                    "detail": (
                                        "Preview only · contains vinyls created by another player"
                                        if contains_foreign_groups
                                        else "Unsupported livery data · no standard shapes decoded"
                                        if decoded_placement_count <= 0
                                        else "Preview only · source data is incomplete"
                                        if source_complete is False
                                        else "Link the local FH6 folder to preview or export"
                                        if not vehicle_index
                                        else "This car ID is not present in the linked FH6 installation"
                                        if asset is None
                                        else "Ready to export"
                                    ),
                                    "hasHeader": (path.parent / "header").is_file(),
                                    "exportable": exportable,
                                    "privacyDetail": (
                                        "" if exportable else "Export unavailable. " + " ".join(privacy_reasons)
                                    ),
                                }
                    catalog_records.append({
                        "path": path,
                        "root": root,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "content_hash": str(row.get("_contentHash") or content_hash),
                        "parser_revision": parser_revision,
                        "row": row,
                    })
                    reason = str(row.get("_reason") or "")
                    if reason == "hidden":
                        hidden += 1
                        continue
                    if reason == "empty":
                        empty += 1
                        continue
                    digest = str(row.get("_contentHash") or "")
                    previous = by_hash.get(digest)
                    if previous is None or (
                        int(row.get("_priority") or 0), int(row.get("_mtimeNs") or 0)
                    ) > (
                        int(previous.get("_priority") or 0), int(previous.get("_mtimeNs") or 0)
                    ):
                        by_hash[digest] = row
                except Exception:
                    rejected += 1
            completed_roots.append(root)
        except OSError:
            del catalog_records[record_start:]
            by_hash = prior_by_hash
            inspected, rejected, hidden, empty, cache_hits = prior_counts
            rejected += 1
            stale_roots.append(root)
            root_key = str(root.resolve())
            for identity in snapshot.values():
                if str(identity.get("root") or "") != root_key:
                    continue
                row = identity.get("row")
                if not isinstance(row, dict) or not row.get("_visible"):
                    continue
                digest = str(row.get("_contentHash") or identity.get("content_hash") or "")
                previous = by_hash.get(digest)
                if previous is None or (
                    int(row.get("_priority") or 0), int(row.get("_mtimeNs") or 0)
                ) > (
                    int(previous.get("_priority") or 0), int(previous.get("_mtimeNs") or 0)
                ):
                    by_hash[digest] = row
    removed = catalog.apply_source_scan(completed_roots, token, catalog_records)
    indexed_rows = sorted(
        by_hash.values(),
        key=lambda item: (int(item.get("_mtimeNs") or 0), str(item.get("title") or "").casefold()),
        reverse=True,
    )
    foreign_blocked, incomplete_blocked = _source_block_counts(indexed_rows)
    rows = [visible for row in indexed_rows if (visible := _visible_source_row(row)) is not None]
    return {
        "rows": rows,
        "fingerprints": {
            str(row.get("path") or ""): str(row.get("_contentHash") or "")
            for row in indexed_rows
            if row.get("path")
        },
        "roots": [str(root) for root in roots],
        "inspected": inspected,
        "rejected": rejected,
        "locked": hidden,
        "foreign_blocked": foreign_blocked,
        "incomplete_blocked": incomplete_blocked,
        "empty": empty,
        "cache_hits": cache_hits,
        "removed": removed,
        "game_assets_ready": bool(vehicle_index),
        "stale_index": bool(stale_roots),
        "warning": (
            "One or more FH6 save folders could not be read completely. "
            "Their last complete indexed results are shown."
            if stale_roots else ""
        ),
        "game_asset_error": game_asset_error,
        "catalog": catalog.stats(),
    }


def open_package(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    selected = Path(str(payload.get("path") or "")).resolve()
    if cancel_event.is_set():
        raise InterruptedError("Package opening was cancelled.")
    previous_revision = package_compiler_revision(selected)
    if previous_revision != PACKAGE_COMPILER_REVISION:
        manifest = migrate_full_livery_package(
            selected,
            selected,
            game_folder=str(payload.get("game_folder") or "") or None,
            vehicle_index_cache=paths.vehicle_index,
        )
    else:
        manifest = validate_full_livery_package(
            selected,
            game_folder=str(payload.get("game_folder") or "") or None,
            verify_previews=False,
        )
    return {
        "path": str(selected),
        "manifest": manifest,
        "migrated_from_revision": previous_revision if previous_revision != PACKAGE_COMPILER_REVISION else None,
        "remember": bool(payload.get("remember", True)),
    }


def _preview_target(paths: JobPaths, source: Path, game_folder: str) -> tuple[Path, str]:
    digest = hashlib.sha256()
    digest.update(source.read_bytes())
    header = source.parent / "header"
    if header.is_file():
        digest.update(header.read_bytes())
    digest.update(game_folder.encode("utf-8", errors="surrogatepass"))
    if paths.vehicle_index.is_file():
        stat = paths.vehicle_index.stat()
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode("ascii"))
    digest.update(f"package:{PACKAGE_COMPILER_REVISION}".encode("ascii"))
    digest.update(f"preview:{SOURCE_PREVIEW_CACHE_REVISION}".encode("ascii"))
    key = digest.hexdigest()
    return paths.preview_cache / f"{key[:24]}.kfpspreview", key


def preview_source(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    source = Path(str(payload.get("source") or "")).resolve()
    game_folder = str(payload.get("game_folder") or "")
    target, cache_key = _preview_target(paths, source, game_folder)
    try:
        manifest = validate_livery_inspection_artifact(target)
        cache_hit = True
    except (OSError, FullLiveryPackageError):
        cache_hit = False
        temporary = target.with_name(f"{target.stem}.{os.getpid()}.tmp.kfpspreview")
        temporary.unlink(missing_ok=True)
        try:
            manifest = create_local_livery_preview(
                source,
                temporary,
                game_folder=game_folder or None,
                vehicle_index_cache=paths.vehicle_index,
                _cancel_event=cancel_event,
            )
            validate_livery_inspection_artifact(temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    FullLiveryCatalog(paths.catalog_file, paths.quarantine).record_cache_entry(
        cache_key,
        kind="preview",
        path=target,
        source_fingerprint=cache_key,
        revision=SOURCE_PREVIEW_CACHE_REVISION,
    )
    return {
        "source_path": str(source),
        "path": str(target.resolve()),
        "manifest": manifest,
        "cache_hit": cache_hit,
    }


def add_package(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    selected = Path(str(payload.get("selected") or "")).resolve()
    game_folder = str(payload.get("game_folder") or "")
    temporary: Path | None = None
    migration: Path | None = None
    try:
        source = selected
        previous_revision = package_compiler_revision(source)
        if previous_revision != PACKAGE_COMPILER_REVISION:
            if source.parent == paths.package_root:
                migrate_full_livery_package(
                    source, source, game_folder=game_folder or None, vehicle_index_cache=paths.vehicle_index
                )
            else:
                migration = paths.root / f"incoming-{os.getpid()}.kfpslivery"
                migration.unlink(missing_ok=True)
                migrate_full_livery_package(
                    source, migration, game_folder=game_folder or None, vehicle_index_cache=paths.vehicle_index
                )
                source = migration
        else:
            validate_full_livery_package(source, game_folder=game_folder or None, verify_previews=bool(game_folder))
        if cancel_event.is_set():
            raise InterruptedError("Package import was cancelled.")
        manifest = validate_full_livery_package(source, game_folder=game_folder or None, verify_previews=False)
        package_id = str(manifest.get("package_id") or "package")[:12]
        target = paths.package_root / selected.name
        source_hash = _file_hash(source)
        if target.exists() and _file_hash(target) != source_hash:
            base = paths.package_root / f"{source.stem}-{package_id}{source.suffix}"
            target = base
            suffix = 2
            while target.exists() and _file_hash(target) != source_hash:
                target = base.with_name(f"{base.stem}-{suffix}{base.suffix}")
                suffix += 1
        if not (target.exists() and _file_hash(target) == source_hash) and source != target.resolve():
            temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
            shutil.copy2(source, temporary)
            validate_full_livery_package(temporary, game_folder=game_folder or None, verify_previews=False)
            os.replace(temporary, target)
            temporary = None
        return {
            "path": str(target.resolve()),
            "upgraded_from_revision": previous_revision if previous_revision != PACKAGE_COMPILER_REVISION else None,
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if migration is not None:
            migration.unlink(missing_ok=True)


def migrate_package(paths: JobPaths, payload: dict[str, Any], _cancel_event) -> dict[str, Any]:
    path = Path(str(payload.get("path") or "")).resolve()
    result = migrate_full_livery_package(
        path,
        path,
        game_folder=str(payload.get("game_folder") or "") or None,
        vehicle_index_cache=paths.vehicle_index,
    )
    return {
        "path": str(path),
        "remember": bool(payload.get("remember", True)),
        "migrated_from_revision": result.get("migrated_from_revision"),
    }


def export_package(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    source = Path(str(payload.get("source") or "")).resolve()
    output = Path(str(payload.get("output") or "")).resolve()
    output.parent.relative_to(paths.package_root)
    game_folder = str(payload.get("game_folder") or "")
    if not game_folder:
        raise FullLiveryPackageError("Choose the local FH6 game folder before exporting a package.")
    decoded = unwrap_forza_container(source)
    privacy = inspect_clivery_privacy(decoded)
    if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
        raise FullLiveryPackageError(
            "This livery contains vinyl groups created by another player. Remove every foreign vinyl group "
            "in FH6 and save the livery again before exporting it from KFPS."
        )
    car_id = struct.unpack_from("<I", decoded, 0x10)[0]
    index = load_or_build_vehicle_asset_index(game_folder, paths.vehicle_index)
    if index.get(car_id) is None:
        raise FullLiveryPackageError(f"No local FH6 car archive advertises target car ID {car_id}.")
    if cancel_event.is_set():
        raise InterruptedError("Package export was cancelled.")
    manifest = create_full_livery_package(
        source, output, game_folder=game_folder, vehicle_index_cache=paths.vehicle_index
    )
    return {"manifest": manifest, "path": manifest["package_path"]}


def install_package(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    package = Path(str(payload.get("package") or "")).resolve()
    game_folder = str(payload.get("game_folder") or "")
    manifest = validate_full_livery_package(package, game_folder=game_folder, verify_previews=False)
    livery = manifest.get("livery") or {}
    vehicle = manifest.get("vehicle") or {}
    car_id = int(livery.get("target_car_id") or 0)
    index = load_or_build_vehicle_asset_index(game_folder, paths.vehicle_index)
    asset = index.get(car_id)
    if asset is None:
        raise FullLiveryPackageError(f"This FH6 installation has no exact car archive for package car ID {car_id}.")
    package_model = str(vehicle.get("model_code") or "").strip()
    if not package_model or asset.model_code.casefold() != package_model.casefold():
        raise FullLiveryPackageError("The package car does not exactly match the car in this FH6 installation.")
    result = install_full_livery_package(
        package,
        scan_roots=_scan_roots(str(payload.get("save_root") or "")),
        backup_root=paths.recovery / "install-backups",
        expected_model_code=asset.model_code,
        cancel_event=cancel_event,
    )
    return {
        "installed_folder": str(result.installed_folder),
        "backup_path": str(result.backup_path),
        "title": result.title,
        "car_id": result.car_id,
        "model_code": result.model_code,
        "placement_count": result.placement_count,
    }


def prepare_mesh(paths: JobPaths, payload: dict[str, Any], cancel_event) -> dict[str, Any]:
    game_folder = str(payload.get("game_folder") or "")
    car_id = int(payload.get("car_id") or 0)
    package_path = Path(str(payload.get("package_path") or "")).resolve()
    index = load_or_build_vehicle_asset_index(game_folder, paths.vehicle_index)
    asset = index.get(car_id)
    if asset is None:
        raise FullLiveryPackageError(f"The local FH6 installation has no car archive for target ID {car_id}.")
    warnings = []
    expected_model = str(payload.get("expected_model_code") or "")
    if expected_model and asset.model_code.casefold() != expected_model.casefold():
        warnings.append(f"local model code {asset.model_code} differs from package model {expected_model}")
    expected_hash = str(payload.get("expected_archive_sha256") or "")
    if expected_hash and sha256_file(Path(asset.archive_path)) != expected_hash:
        warnings.append("the local car archive is a different game revision")
    mesh_path = paths.mesh_cache / (
        f"{asset.model_code}-{asset.archive_mtime_ns}.local-chassis-v{INSPECTION_MESH_CACHE_REVISION}.glb"
    )
    mesh_cache_hit = True
    try:
        validate_local_chassis_glb(mesh_path)
    except (OSError, PortableMeshConverterError):
        mesh_cache_hit = False
        mesh_path.unlink(missing_ok=True)
        mesh_path.parent.mkdir(parents=True, exist_ok=True)
        convert_vehicle_model_to_glb(asset, mesh_path, cancel_event=cancel_event)
    if cancel_event.is_set():
        raise InterruptedError("Local chassis preparation was cancelled.")
    package_key = _file_hash(package_path)[:24]
    render_root = paths.render_cache / f"{package_key}-{asset.archive_mtime_ns}"
    render_contract = build_local_livery_atlases(
        package_path,
        asset,
        render_root,
        mesh_path=mesh_path,
    )
    catalog = FullLiveryCatalog(paths.catalog_file, paths.quarantine)
    catalog.record_cache_entry(
        f"mesh:{asset.model_code}:{asset.archive_mtime_ns}",
        kind="mesh",
        path=mesh_path,
        source_fingerprint=str(asset.archive_mtime_ns),
        revision=INSPECTION_MESH_CACHE_REVISION,
    )
    return {
        "package_id": str(payload.get("package_id") or ""),
        "package_path": str(package_path),
        "mesh_path": str(mesh_path.resolve()),
        "render_root": render_contract["root"],
        "render_contract": render_contract,
        "model_code": asset.model_code,
        "revision_warning": "; ".join(warnings),
        "mesh_cache_hit": mesh_cache_hit,
    }


def clear_cache(paths: JobPaths, _payload: dict[str, Any], _cancel_event) -> dict[str, int]:
    paths.cache.relative_to(paths.root)
    if paths.cache.name != f"v{CACHE_REVISION}":
        raise RuntimeError("Refusing to clear an unexpected full-livery cache revision.")
    files = bytes_removed = 0
    if paths.cache.is_dir():
        for candidate in paths.cache.rglob("*"):
            if candidate.is_file():
                files += 1
                try:
                    bytes_removed += candidate.stat().st_size
                except OSError:
                    pass
        shutil.rmtree(paths.cache)
    paths.ensure()
    FullLiveryCatalog(paths.catalog_file, paths.quarantine).invalidate_cache()
    return {"files": files, "bytes": bytes_removed}


OPERATIONS = {
    "link-game": link_game,
    "refresh-packages": refresh_packages,
    "scan-saves": scan_saves,
    "open-package": open_package,
    "preview-source": preview_source,
    "add-package": add_package,
    "migrate-package": migrate_package,
    "export-package": export_package,
    "install-package": install_package,
    "prepare-mesh": prepare_mesh,
    "clear-cache": clear_cache,
}


def execute_operation(request: dict[str, Any], cancel_event) -> dict[str, Any]:
    paths = JobPaths.from_request(request)
    paths.ensure()
    operation = str(request["operation"])
    return OPERATIONS[operation](paths, dict(request.get("payload") or {}), cancel_event)
