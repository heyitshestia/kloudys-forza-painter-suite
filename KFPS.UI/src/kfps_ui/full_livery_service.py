from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import struct
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from tools.cgroup.forza_source_decoder import extract_livery_payload, inspect_clivery_privacy, unwrap_forza_container
from tools.livery import (
    PACKAGE_COMPILER_REVISION,
    FullLiveryPackageError,
    compatibility_decision,
    create_full_livery_package,
    create_local_livery_preview,
    inspect_full_livery_package,
    install_full_livery_package,
    migrate_full_livery_package,
    package_compiler_revision,
    validate_livery_inspection_artifact,
    validate_full_livery_package,
)
from tools.livery.inspector_server import LiveryInspectorServer
from tools.livery.portable_mesh_converter import (
    ChassisConversionCancelled,
    PortableMeshConverterError,
    convert_vehicle_model_to_glb,
    validate_local_chassis_glb,
)
from tools.livery.render_contract import build_local_livery_atlases
from tools.livery.vehicle_assets import (
    discover_fh6_game_folder,
    load_or_build_vehicle_asset_index,
    normalize_fh6_game_folder,
    sha256_file,
)

from .app_paths import AppPaths
from .log_service import LogService
from .models import DictListModel
from .qt_utils import safe_file_part


INSPECTION_MESH_CACHE_REVISION = 6


class FullLiveryService(QObject):
    changed = Signal()
    _resultReady = Signal(object)
    _meshResultReady = Signal(object)

    SOURCE_ROLES = (
        "title", "path", "carId", "modelCode", "placementCount",
        "modified", "detail", "hasHeader", "exportable", "privacyDetail",
    )
    PACKAGE_ROLES = (
        "title", "path", "carId", "modelCode", "placementCount", "portableMesh",
        "created", "detail",
    )
    DECISION_ROLES = ("action", "item", "detail")

    def __init__(self, paths: AppPaths, log: LogService, supporter=None, demo: bool = False, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.log = log
        # Retained for compatibility with launchers from the supporter-gated prototype.
        del supporter, demo
        self._runtime = paths.runtime_root / "full-livery"
        self._package_root = paths.exported_root / "full-liveries"
        self._settings_file = self._runtime / "settings.json"
        self._cache_root = self._runtime / "cache"
        self._vehicle_index_cache = self._cache_root / "fh6-vehicle-index.json"
        self._mesh_cache = self._cache_root / "meshes"
        self._render_cache = self._cache_root / "section-render"
        self._source_preview_cache = self._cache_root / "source-previews"
        self._inspector_root = paths.app_root / "tools" / "livery-inspector"
        self._runtime.mkdir(parents=True, exist_ok=True)
        self._package_root.mkdir(parents=True, exist_ok=True)
        self._settings = self._load_settings()
        self._game_folder = self._resolve_initial_game_folder()
        if self._game_folder and self._settings.get("fh6_game_folder") != self._game_folder:
            self._settings["fh6_game_folder"] = self._game_folder
            self._save_settings()
        self._save_root = str(self._settings.get("fh6_save_root") or "")
        self._running = False
        self._status = "Ready"
        self._summary = "Scan local FH6 livery files or open a portable KFPS full-livery package."
        self._selected_source = ""
        self._active_source_preview = ""
        self._source_privacy: dict[str, dict[str, Any]] = {}
        self._selected_package = str(self._settings.get("last_package") or "")
        self._viewer_url = ""
        self._current_manifest: dict[str, Any] = {}
        self._sources = DictListModel(self.SOURCE_ROLES, self)
        self._packages = DictListModel(self.PACKAGE_ROLES, self)
        self._decisions = DictListModel(self.DECISION_ROLES, self)
        self._inspector = LiveryInspectorServer(self._inspector_root)
        self._selection_serial = 0
        self._preview_future = None
        self._preview_cancel_event: threading.Event | None = None
        self._mesh_future = None
        self._mesh_cancel_event: threading.Event | None = None
        self._install_future = None
        self._install_cancel_event: threading.Event | None = None
        self._mesh_serial = 0
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="full-livery")
        self._resultReady.connect(self._apply_result)
        self._meshResultReady.connect(self._apply_mesh_result)
        self._purge_legacy_source_previews()
        self._refresh_packages(open_remembered=True)

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def summary(self):
        return self._summary

    @Property(QObject, constant=True)
    def sourceModel(self):
        return self._sources

    @Property(QObject, constant=True)
    def packageModel(self):
        return self._packages

    @Property(QObject, constant=True)
    def decisionModel(self):
        return self._decisions

    @Property(str, notify=changed)
    def selectedSource(self):
        return self._selected_source

    @Property(bool, notify=changed)
    def selectedSourceExportable(self):
        return bool((self._source_privacy.get(self._selected_source) or {}).get("exportable"))

    @Property(str, notify=changed)
    def selectedSourcePrivacyMessage(self):
        return str((self._source_privacy.get(self._selected_source) or {}).get("privacyDetail") or "")

    @Property(str, notify=changed)
    def selectedPackage(self):
        return self._selected_package

    @Property(bool, notify=changed)
    def selectedPackageInstallable(self):
        if not self._current_manifest:
            return False
        sharing = self._current_manifest.get("sharing") or {}
        if sharing.get("exportable") is not True or sharing.get("preview_only") is True:
            return False
        members = {
            str(item.get("path") or "")
            for item in (self._current_manifest.get("files") or [])
            if isinstance(item, dict)
        }
        if "source/fh6/header" not in members:
            return False
        return bool(compatibility_decision(self._current_manifest, "fh6").get("installable"))

    @Property(str, notify=changed)
    def viewerUrl(self):
        return self._viewer_url

    @Property(str, notify=changed)
    def gameFolder(self):
        return self._game_folder

    @Property(str, notify=changed)
    def saveRoot(self):
        return self._save_root

    @Property(str, notify=changed)
    def packageFolder(self):
        return str(self._package_root)

    @Property(str, notify=changed)
    def selectedTitle(self):
        return str((self._current_manifest.get("livery") or {}).get("title") or "No package open")

    @Property(str, notify=changed)
    def selectedVehicle(self):
        vehicle = self._current_manifest.get("vehicle") or {}
        livery = self._current_manifest.get("livery") or {}
        code = vehicle.get("model_code") or "Unresolved model"
        return f"{code} · car ID {livery.get('target_car_id') or '?'}"

    @Property(str, notify=changed)
    def selectedCounts(self):
        livery = self._current_manifest.get("livery") or {}
        logical = int(livery.get("logical_placement_count") or 0)
        decoded = int(livery.get("decoded_layer_count") or 0)
        return f"{logical:,} logical placements · {decoded:,} decoded layers"

    @Property(bool, notify=changed)
    def selectedHasPortableMesh(self):
        return bool((self._current_manifest.get("vehicle") or {}).get("portable_mesh"))

    def _load_settings(self) -> dict[str, Any]:
        try:
            value = json.loads(self._settings_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _purge_legacy_source_previews(self) -> None:
        if not self._source_preview_cache.is_dir():
            return
        for pattern in ("*.kfpslivery", "*.tmp.kfpslivery"):
            for path in self._source_preview_cache.glob(pattern):
                try:
                    path.unlink()
                except OSError as exc:
                    self.log.append(f"Could not remove an obsolete full-livery preview cache file: {exc}", "warning")

    def _save_settings(self) -> None:
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._settings_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._settings, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self._settings_file)

    def _resolve_initial_game_folder(self) -> str:
        configured_value = str(self._settings.get("fh6_game_folder") or "").strip()
        discovered = discover_fh6_game_folder(configured_value or None)
        return str(discovered) if discovered else ""

    @Slot()
    def chooseGameFolder(self):
        start = Path(self._game_folder) if self._game_folder else self.paths.app_root
        folder = QFileDialog.getExistingDirectory(None, "Choose the FH6 game or Content folder", str(start))
        if not folder:
            return
        try:
            normalized = normalize_fh6_game_folder(folder)
            load_or_build_vehicle_asset_index(normalized, self._vehicle_index_cache)
        except Exception as exc:
            self._status = "FH6 assets not found"
            self._summary = str(exc)
            self.changed.emit()
            return
        self._game_folder = str(normalized)
        self._settings["fh6_game_folder"] = self._game_folder
        self._save_settings()
        self._status = "FH6 assets linked"
        self._summary = "KFPS can now resolve car IDs, projection records, and local inspection meshes."
        self._refresh_packages(open_remembered=False)
        self.changed.emit()
        self.scanSaves()

    @Slot()
    def chooseSaveRoot(self):
        start = Path(self._save_root) if self._save_root else Path(r"C:\XboxGames\GameSave")
        folder = QFileDialog.getExistingDirectory(None, "Choose an FH6 GameSave folder", str(start))
        if not folder:
            return
        self._save_root = str(Path(folder).resolve())
        self._settings["fh6_save_root"] = self._save_root
        self._save_settings()
        self.changed.emit()
        self.scanSaves()

    @Slot()
    def clearFullLiveryCache(self):
        if self._running:
            return
        reopen_source = self._active_source_preview or self._selected_source
        reopen_package = "" if reopen_source else self._selected_package
        self._cancel_source_preview()
        self._cancel_mesh_preparation()
        self._inspector.close()
        self._inspector = LiveryInspectorServer(self._inspector_root)
        self._current_manifest = {}
        self._selected_package = ""
        self._viewer_url = ""
        self._active_source_preview = ""
        self._running = True
        self._status = "Clearing full-livery cache"
        self._summary = "Removing rebuildable car meshes, section atlases, previews, and the FH6 vehicle index."
        self.changed.emit()
        future = self._executor.submit(self._clear_full_livery_cache_work)
        future.add_done_callback(
            lambda item: self._resultReady.emit(
                {
                    **self._future_result("clear-cache", item),
                    "reopen_source": reopen_source,
                    "reopen_package": reopen_package,
                }
            )
        )

    def _clear_full_livery_cache_work(self) -> dict[str, int]:
        runtime = self._runtime.resolve()
        cache = self._cache_root.resolve()
        if cache.parent != runtime or cache.name.casefold() != "cache":
            raise RuntimeError("Refusing to clear a path outside the full-livery cache.")
        files = 0
        bytes_removed = 0
        if cache.is_dir():
            for path in cache.rglob("*"):
                if path.is_file():
                    files += 1
                    try:
                        bytes_removed += path.stat().st_size
                    except OSError:
                        pass
            shutil.rmtree(cache)
        cache.mkdir(parents=True, exist_ok=True)
        return {"files": files, "bytes": bytes_removed}

    @Slot()
    def scanSaves(self):
        if self._running:
            return
        if not self._game_folder:
            discovered = discover_fh6_game_folder()
            if discovered:
                self._game_folder = str(discovered)
                self._settings["fh6_game_folder"] = self._game_folder
                self._save_settings()
        self._running = True
        self._status = "Scanning FH6 liveries"
        self._summary = "Reading local full-car livery records without changing save data."
        self.changed.emit()
        future = self._executor.submit(self._scan_saves_work)
        future.add_done_callback(lambda item: self._resultReady.emit(self._future_result("scan", item)))

    @Slot(str)
    def selectSource(self, path: str):
        if not self._game_folder:
            self._status = "FH6 folder required"
            self._summary = (
                "KFPS found the save, but it needs this PC's FH6 game or Content folder "
                "before it can resolve the car and build a 3D preview."
            )
            self.changed.emit()
            return
        source = Path(str(path or ""))
        if source.is_file() and source.name.casefold() == "c_livery":
            if self._running and not (self._preview_future and not self._preview_future.done()):
                return
            self._selected_source = str(source.resolve())
            self._active_source_preview = ""
            self._cancel_mesh_preparation()
            self._cancel_source_preview()
            cancel_event = threading.Event()
            self._preview_cancel_event = cancel_event
            self._running = True
            self._status = "Preparing local livery preview"
            selected_privacy = self._source_privacy.get(self._selected_source) or {}
            self._summary = (
                selected_privacy.get("privacyDetail")
                or "Building or reopening this livery's private local car preview."
            )
            self.changed.emit()
            selected = self._selected_source
            self._preview_future = self._executor.submit(self._preview_source_work, source, cancel_event)
            self._preview_future.add_done_callback(
                lambda item, selected_path=selected: self._resultReady.emit(
                    {**self._future_result("preview", item), "source_path": selected_path}
                )
            )

    @Slot(str)
    def selectPackage(self, path: str):
        if self._preview_future is not None and not self._preview_future.done():
            self._selected_source = ""
            self._cancel_source_preview()
            self._running = False
        self._active_source_preview = ""
        try:
            selected = str(Path(path).resolve())
            if package_compiler_revision(selected) != PACKAGE_COMPILER_REVISION:
                self._start_saved_package_migration(selected, remember=True)
                return
        except Exception as exc:
            self._status = "Package rejected"
            self._summary = str(exc)
            self.changed.emit()
            return
        self._open_package(selected, remember=True)

    def _start_saved_package_migration(self, path: str, *, remember: bool) -> None:
        if self._running:
            self._status = "Another full-livery task is already running"
            self.changed.emit()
            return
        self._cancel_mesh_preparation()
        self._running = True
        self._status = "Updating saved full-livery package"
        self._summary = "Rebuilding this older package from its embedded FH6 source before opening it."
        self.changed.emit()
        future = self._executor.submit(self._migrate_saved_package_work, path, remember)
        future.add_done_callback(
            lambda item: self._resultReady.emit(self._future_result("migrate-package", item))
        )

    def _migrate_saved_package_work(self, path: str, remember: bool) -> dict[str, Any]:
        result = migrate_full_livery_package(
            path,
            path,
            game_folder=self._game_folder or None,
            vehicle_index_cache=self._vehicle_index_cache,
        )
        return {
            "path": str(Path(path).resolve()),
            "remember": remember,
            "migrated_from_revision": result.get("migrated_from_revision"),
        }

    def _open_package(self, path: str, *, remember: bool) -> None:
        candidate: LiveryInspectorServer | None = None
        try:
            selected = str(Path(path).resolve())
            candidate = LiveryInspectorServer(self._inspector_root)
            manifest = candidate.set_package(selected)
            previous = self._inspector
            self._inspector = candidate
            candidate = None
            previous.close()
            self._current_manifest = manifest
            self._selected_package = selected
            self._viewer_url = ""
            if remember:
                self._settings["last_package"] = self._selected_package
                self._save_settings()
            self._status = "Package open"
            self._summary = "The package passed its integrity checks. Preparing its exact local FH6 preview."
            self._refresh_decisions()
            self.changed.emit()
            self._prepare_local_mesh(manifest, selected)
        except Exception as exc:
            if candidate is not None:
                candidate.close()
            self._status = "Package rejected"
            self._summary = str(exc)
            self.log.append(f"Full-livery package rejected: {exc}", "error")
            self.changed.emit()

    def _source_preview_target(self, source: Path) -> Path:
        source = source.resolve()
        digest = hashlib.sha256()
        digest.update(source.read_bytes())
        header = source.parent / "header"
        if header.is_file():
            digest.update(header.read_bytes())
        digest.update(self._game_folder.encode("utf-8", errors="surrogatepass"))
        if self._vehicle_index_cache.is_file():
            digest.update(str(self._vehicle_index_cache.stat().st_mtime_ns).encode("ascii"))
        digest.update(f"package-compiler:{PACKAGE_COMPILER_REVISION}".encode("ascii"))
        self._source_preview_cache.mkdir(parents=True, exist_ok=True)
        return self._source_preview_cache / f"{digest.hexdigest()[:24]}.kfpspreview"

    def _preview_source_work(
        self,
        source: Path,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, str]:
        source = source.resolve()
        if cancel_event is not None and cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        target = self._source_preview_target(source)
        try:
            validate_livery_inspection_artifact(target)
        except (OSError, FullLiveryPackageError):
            temporary = target.with_name(f"{target.stem}.{os.getpid()}.tmp.kfpspreview")
            temporary.unlink(missing_ok=True)
            try:
                create_local_livery_preview(
                    source,
                    temporary,
                    game_folder=self._game_folder or None,
                    vehicle_index_cache=self._vehicle_index_cache,
                    _cancel_event=cancel_event,
                )
                validate_livery_inspection_artifact(temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return {"source_path": str(source), "path": str(target.resolve())}

    def _cancel_source_preview(self) -> None:
        if self._preview_cancel_event is not None:
            self._preview_cancel_event.set()
        if self._preview_future is not None and not self._preview_future.done():
            self._preview_future.cancel()

    def _refresh_active_source_after_scan(self, rows: list[dict[str, Any]]) -> bool:
        active = self._active_source_preview
        if not active:
            return False
        visible_paths = {str(row.get("path") or "") for row in rows}
        if active not in visible_paths:
            self._inspector.close()
            self._inspector = LiveryInspectorServer(self._inspector_root)
            self._current_manifest = {}
            self._selected_package = ""
            self._viewer_url = ""
            self._active_source_preview = ""
            if self._selected_source == active:
                self._selected_source = ""
            return False
        try:
            expected = str(self._source_preview_target(Path(active)).resolve())
        except OSError:
            return False
        if expected == self._selected_package:
            return False
        self.selectSource(active)
        return True

    @Slot()
    def choosePackage(self):
        selected, _ = QFileDialog.getOpenFileName(
            None,
            "Add a KFPS full-livery package",
            str(self._package_root),
            "KFPS full liveries (*.kfpslivery);;All files (*)",
        )
        if not selected:
            return
        self._start_add_package(selected)

    def _start_add_package(self, selected: str) -> None:
        if self._running:
            self._status = "Another full-livery task is already running"
            self.changed.emit()
            return
        self._cancel_mesh_preparation()
        self._running = True
        self._status = "Verifying full-livery package"
        self._summary = "Checking the package against its embedded FH6 source before adding it."
        self.changed.emit()
        future = self._executor.submit(self._add_package_work, selected)
        future.add_done_callback(
            lambda item: self._resultReady.emit(self._future_result("add-package", item))
        )

    @Slot(str, result=bool)
    def addPackage(self, selected: str) -> bool:
        try:
            payload = self._add_package_work(selected)
            self._complete_added_package(payload)
            return True
        except Exception as exc:
            self._status = "Package not added"
            self._summary = str(exc)
            self.changed.emit()
            return False

    def _add_package_work(self, selected: str) -> dict[str, Any]:
        temporary: Path | None = None
        migration: Path | None = None
        try:
            source = Path(selected).resolve()
            previous_revision = package_compiler_revision(source)
            if previous_revision != PACKAGE_COMPILER_REVISION:
                if source.parent == self._package_root.resolve():
                    manifest = migrate_full_livery_package(
                        source,
                        source,
                        game_folder=self._game_folder or None,
                        vehicle_index_cache=self._vehicle_index_cache,
                    )
                else:
                    migration = self._runtime / f"incoming-{os.getpid()}.kfpslivery"
                    migration.unlink(missing_ok=True)
                    manifest = migrate_full_livery_package(
                        source,
                        migration,
                        game_folder=self._game_folder or None,
                        vehicle_index_cache=self._vehicle_index_cache,
                    )
                    source = migration
            else:
                manifest = validate_full_livery_package(
                    source,
                    game_folder=self._game_folder or None,
                    verify_previews=bool(self._game_folder),
                )
            package_id = str(manifest.get("package_id") or "package")[:12]
            selected_path = Path(selected).resolve()
            target = self._package_root / selected_path.name
            source_hash = self._file_hash(source)
            if target.exists() and self._file_hash(target) != source_hash:
                base = self._package_root / f"{source.stem}-{package_id}{source.suffix}"
                target = base
                suffix = 2
                while target.exists() and self._file_hash(target) != source_hash:
                    target = base.with_name(f"{base.stem}-{suffix}{base.suffix}")
                    suffix += 1
            if target.exists() and self._file_hash(target) == source_hash:
                pass
            elif source != target.resolve():
                temporary = target.with_suffix(target.suffix + f".{os.getpid()}.tmp")
                shutil.copy2(source, temporary)
                validate_full_livery_package(
                    temporary,
                    game_folder=self._game_folder or None,
                    verify_previews=False,
                )
                os.replace(temporary, target)
                temporary = None
            return {
                "path": str(target.resolve()),
                "upgraded_from_revision": previous_revision
                if previous_revision != PACKAGE_COMPILER_REVISION
                else None,
            }
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if migration is not None:
                migration.unlink(missing_ok=True)

    def _complete_added_package(self, payload: dict[str, Any]) -> None:
        upgraded = payload.get("upgraded_from_revision")
        if upgraded is not None:
            self.log.append(
                f"Upgraded an imported full-livery package from compiler revision {upgraded} "
                f"to {PACKAGE_COMPILER_REVISION}."
            )
        target = str(payload.get("path") or "")
        self._refresh_packages(open_remembered=False)
        self.selectPackage(target)

    @staticmethod
    def _file_hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _automatic_package_target(self, source: Path, car_id: int) -> Path:
        title = self._header_title(source) or source.parent.name or "FH6 full livery"
        stem = safe_file_part(f"{title} - FH6 {car_id}", f"FH6-livery-{car_id}")[:120].rstrip(" .")
        target = self._package_root / f"{stem}.kfpslivery"
        suffix = 2
        while target.exists():
            target = self._package_root / f"{stem} ({suffix}).kfpslivery"
            suffix += 1
        return target

    @Slot()
    def exportSelected(self):
        if self._running:
            return
        source = Path(self._selected_source)
        if not source.is_file():
            self._status = "Choose an FH6 livery"
            self._summary = "Select one shareable local full-car livery before exporting a package."
            self.changed.emit()
            return
        try:
            payload = unwrap_forza_container(source)
            privacy = inspect_clivery_privacy(payload)
            car_id = struct.unpack_from("<I", payload, 0x10)[0]
        except Exception as exc:
            self._status = "Livery privacy check failed"
            self._summary = str(exc)
            self.changed.emit()
            return
        if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
            self._status = "Export unavailable"
            self._summary = (
                "This livery contains vinyl groups created by another player. Remove every foreign vinyl group "
                "in FH6 and save the livery again before exporting it from KFPS."
            )
            self.changed.emit()
            return
        output = self._automatic_package_target(source, car_id)
        self._running = True
        self._status = "Building full-livery package"
        self._summary = "Building and verifying the package before adding it to Saved packages."
        self.changed.emit()
        future = self._executor.submit(self._export_work, source, output)
        future.add_done_callback(lambda item: self._resultReady.emit(self._future_result("export", item)))

    @Slot()
    def installSelectedPackage(self):
        if self._running:
            return
        package = Path(self._selected_package)
        if not package.is_file() or not self.selectedPackageInstallable:
            self._status = "Choose an installable FH6 package"
            self._summary = "Only a verified package for its exact FH6 car can be installed."
            self.changed.emit()
            return
        if not self._game_folder:
            self._status = "FH6 folder required"
            self._summary = "Choose this PC's FH6 folder so KFPS can verify the package's exact car."
            self.changed.emit()
            return
        self._cancel_mesh_preparation()
        cancel_event = threading.Event()
        self._install_cancel_event = cancel_event
        self._running = True
        self._status = "Installing exact-car FH6 livery"
        self._summary = "Verifying the package, creating a recovery record, and staging a new local livery."
        self.changed.emit()
        future = self._executor.submit(self._install_package_work, package, cancel_event)
        self._install_future = future
        future.add_done_callback(lambda item: self._resultReady.emit(self._future_result("install", item)))

    @Slot()
    def refreshPackages(self):
        self._refresh_packages(open_remembered=False)

    def _refresh_packages(self, *, open_remembered: bool) -> None:
        rows = []
        for path in self._package_root.glob("*.kfpslivery"):
            try:
                revision = package_compiler_revision(path)
                info = (
                    inspect_full_livery_package(path, allow_legacy=True)
                    if revision != PACKAGE_COMPILER_REVISION
                    else inspect_full_livery_package(path)
                )
                placement_count = int(info.get("logical_placement_count") or 0)
                if placement_count <= 0:
                    continue
                stat = path.stat()
                rows.append({
                    "title": info.get("title") or path.stem,
                    "path": str(path.resolve()),
                    "carId": int(info.get("target_car_id") or 0),
                    "modelCode": info.get("model_code") or "Unresolved car",
                    "placementCount": placement_count,
                    "portableMesh": False,
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "_mtime": stat.st_mtime,
                    "detail": (
                        "Older package; KFPS will update it when opened"
                        if revision != PACKAGE_COMPILER_REVISION
                        else "Shareable artwork; chassis resolved from the local FH6 installation"
                    ),
                })
            except (OSError, FullLiveryPackageError):
                continue
        rows.sort(key=lambda row: row["_mtime"], reverse=True)
        for row in rows:
            row.pop("_mtime", None)
        self._packages.replace(rows)
        remembered = Path(self._selected_package) if self._selected_package else None
        if (
            open_remembered
            and remembered
            and remembered.is_file()
            and any(row["path"] == str(remembered.resolve()) for row in rows)
        ):
            self.selectPackage(str(remembered))
        self.changed.emit()

    @Slot()
    def openPackageFolder(self):
        self._package_root.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self._package_root))

    def _scan_roots(self) -> list[Path]:
        candidates: list[Path] = []
        if self._save_root:
            configured = Path(self._save_root)
            if configured.is_dir():
                return [configured.resolve()]
        candidates.append(Path(r"C:\XboxGames\GameSave"))
        for partition in psutil.disk_partitions(all=False):
            root = Path(partition.mountpoint)
            candidates.append(root / "XboxGames" / "GameSave")
        result: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            key = str(candidate.resolve()).casefold()
            if key not in seen:
                seen.add(key)
                result.append(candidate.resolve())
        return result

    @staticmethod
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

    def _scan_saves_work(self) -> dict[str, Any]:
        roots = self._scan_roots()
        if not roots:
            return {"rows": [], "roots": [], "warning": "No FH6 GameSave folder was found. Choose it manually."}
        vehicle_index = {}
        game_asset_error = ""
        if self._game_folder:
            try:
                vehicle_index = load_or_build_vehicle_asset_index(self._game_folder, self._vehicle_index_cache)
            except Exception as exc:
                game_asset_error = str(exc)
                vehicle_index = {}
        by_hash: dict[str, dict[str, Any]] = {}
        inspected = 0
        rejected = 0
        locked = 0
        empty = 0
        for root in roots:
            for path in root.rglob("C_livery"):
                inspected += 1
                try:
                    raw = path.read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    payload = unwrap_forza_container(path)
                    if payload[:4] != b"vlrc" or len(payload) < 0x1A:
                        rejected += 1
                        continue
                    state = struct.unpack_from("<I", payload, 0x08)[0]
                    if state == 1:
                        locked += 1
                        continue
                    privacy = inspect_clivery_privacy(payload)
                    source_owned = bool(privacy["source_owned"])
                    exportable = source_owned and not privacy["contains_foreign_groups"]
                    car_id = struct.unpack_from("<I", payload, 0x10)[0]
                    _, counts, _ = extract_livery_payload(payload)
                    placement_count = sum(counts)
                    if placement_count <= 0:
                        empty += 1
                        continue
                    asset = vehicle_index.get(car_id)
                    stat = path.stat()
                    title = self._header_title(path) or path.parent.name
                    row = {
                        "title": title,
                        "path": str(path.resolve()),
                        "carId": car_id,
                        "modelCode": asset.model_code if asset else "Unresolved car",
                        "placementCount": placement_count,
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "detail": (
                            "Link the local FH6 folder to preview or export"
                            if not vehicle_index
                            else "This car ID is not present in the linked FH6 installation"
                            if asset is None
                            else "Ready to export"
                            if exportable
                            else "Preview only · contains vinyls created by another player"
                        ),
                        "hasHeader": (path.parent / "header").is_file(),
                        "exportable": exportable,
                        "privacyDetail": (
                            ""
                            if exportable
                            else "Export unavailable. Remove every foreign vinyl group in FH6 and save the livery again."
                        ),
                        "_source_owned": source_owned,
                        "_mtime": stat.st_mtime,
                        "_priority": 1 if "\\current\\" in str(path).casefold() else 0,
                    }
                    previous = by_hash.get(digest)
                    if previous is None or (row["_priority"], row["_mtime"]) > (previous["_priority"], previous["_mtime"]):
                        by_hash[digest] = row
                except Exception:
                    rejected += 1
        rows = sorted(by_hash.values(), key=lambda item: (item["_mtime"], item["title"].casefold()), reverse=True)
        foreign_blocked = sum(bool(row["_source_owned"]) and not bool(row["exportable"]) for row in rows)
        for row in rows:
            row.pop("_source_owned", None)
            row.pop("_mtime", None)
            row.pop("_priority", None)
        return {
            "rows": rows,
            "roots": [str(root) for root in roots],
            "inspected": inspected,
            "rejected": rejected,
            "locked": locked,
            "foreign_blocked": foreign_blocked,
            "empty": empty,
            "game_assets_ready": bool(vehicle_index),
            "game_asset_error": game_asset_error,
        }

    def _export_work(self, source: Path, output: Path) -> dict[str, Any]:
        if not self._game_folder:
            raise FullLiveryPackageError(
                "Choose the local FH6 game folder first so KFPS can resolve the car metadata and local inspection assets."
            )
        payload = unwrap_forza_container(source)
        privacy = inspect_clivery_privacy(payload)
        if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
            raise FullLiveryPackageError(
                "This livery contains vinyl groups created by another player. Remove every foreign vinyl group "
                "in FH6 and save the livery again before exporting it from KFPS."
            )
        car_id = struct.unpack_from("<I", payload, 0x10)[0]
        index = load_or_build_vehicle_asset_index(self._game_folder, self._vehicle_index_cache)
        asset = index.get(car_id)
        if asset is None:
            raise FullLiveryPackageError(f"No local FH6 car archive advertises target car ID {car_id}.")
        manifest = create_full_livery_package(
            source,
            output,
            game_folder=self._game_folder,
            vehicle_index_cache=self._vehicle_index_cache,
        )
        return {"manifest": manifest, "path": manifest["package_path"]}

    def _install_package_work(self, package: Path, cancel_event=None) -> dict[str, Any]:
        manifest = validate_full_livery_package(
            package,
            game_folder=self._game_folder,
            verify_previews=False,
        )
        livery = manifest.get("livery") or {}
        vehicle = manifest.get("vehicle") or {}
        car_id = int(livery.get("target_car_id") or 0)
        index = load_or_build_vehicle_asset_index(self._game_folder, self._vehicle_index_cache)
        asset = index.get(car_id)
        if asset is None:
            raise FullLiveryPackageError(
                f"This FH6 installation has no exact car archive for package car ID {car_id}."
            )
        package_model = str(vehicle.get("model_code") or "").strip()
        if not package_model or asset.model_code.casefold() != package_model.casefold():
            raise FullLiveryPackageError(
                "The package car does not exactly match the car in this FH6 installation."
            )
        result = install_full_livery_package(
            package,
            scan_roots=self._scan_roots(),
            backup_root=self._runtime / "install-backups",
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

    def _cached_mesh_path(self, asset) -> Path:
        return self._mesh_cache / (
            f"{asset.model_code}-{asset.archive_mtime_ns}.local-chassis-v{INSPECTION_MESH_CACHE_REVISION}.glb"
        )

    def _prepare_local_mesh(self, manifest: dict[str, Any], package_path: str) -> None:
        self._cancel_mesh_preparation()
        if not self._game_folder:
            self._status = "FH6 assets needed for 3D"
            self._summary = "The package is valid. Choose the local FH6 game folder to resolve its inspection mesh."
            self.changed.emit()
            return
        package_id = str(manifest.get("package_id") or "")
        car_id = int((manifest.get("livery") or {}).get("target_car_id") or 0)
        vehicle = manifest.get("vehicle") or {}
        request_serial = self._mesh_serial
        cancel_event = threading.Event()
        self._mesh_cancel_event = cancel_event
        self._status = "Preparing local chassis"
        self._summary = "Reading this car's neutral inspection geometry and livery UV map from the local FH6 installation."
        self.changed.emit()
        future = self._executor.submit(
            self._prepare_mesh_work,
            request_serial,
            cancel_event,
            package_id,
            car_id,
            str(vehicle.get("model_code") or ""),
            str(vehicle.get("archive_sha256") or ""),
            package_path,
        )
        self._mesh_future = future
        future.add_done_callback(
            lambda item, selected=package_path, serial=request_serial: self._meshResultReady.emit(
                {**self._future_result("mesh", item), "package_path": selected, "request_serial": serial}
            )
        )

    def _cancel_mesh_preparation(self) -> None:
        self._mesh_serial += 1
        if self._mesh_cancel_event is not None:
            self._mesh_cancel_event.set()
        if self._mesh_future is not None and not self._mesh_future.done():
            self._mesh_future.cancel()

    def _prepare_mesh_work(
        self,
        request_serial: int,
        cancel_event: threading.Event,
        package_id: str,
        car_id: int,
        expected_model_code: str,
        expected_archive_sha256: str,
        package_path: str,
    ) -> dict[str, Any]:
        if cancel_event.is_set():
            raise ChassisConversionCancelled("Local chassis preparation was superseded.")
        index = load_or_build_vehicle_asset_index(self._game_folder, self._vehicle_index_cache)
        asset = index.get(car_id)
        if asset is None:
            raise FullLiveryPackageError(f"The local FH6 installation has no car archive for target ID {car_id}.")
        revision_warnings = []
        if expected_model_code and asset.model_code.casefold() != expected_model_code.casefold():
            revision_warnings.append(
                f"local model code {asset.model_code} differs from package model {expected_model_code}"
            )
        if expected_archive_sha256 and sha256_file(Path(asset.archive_path)) != expected_archive_sha256:
            revision_warnings.append("the local car archive is a different game revision")
        mesh_path = self._cached_mesh_path(asset)
        try:
            validate_local_chassis_glb(mesh_path)
        except (OSError, PortableMeshConverterError):
            mesh_path.unlink(missing_ok=True)
            mesh_path.parent.mkdir(parents=True, exist_ok=True)
            convert_vehicle_model_to_glb(asset, mesh_path, cancel_event=cancel_event)
        if cancel_event.is_set():
            raise ChassisConversionCancelled("Local chassis preparation was superseded.")
        package_cache_key = self._file_hash(Path(package_path))[:24]
        render_root = self._render_cache / f"{package_cache_key}-{asset.archive_mtime_ns}"
        render_contract = build_local_livery_atlases(package_path, asset, render_root)
        return {
            "request_serial": request_serial,
            "package_id": package_id,
            "package_path": package_path,
            "mesh_path": str(mesh_path.resolve()),
            "render_root": render_contract["root"],
            "render_contract": render_contract,
            "model_code": asset.model_code,
            "revision_warning": "; ".join(revision_warnings),
        }

    @staticmethod
    def _future_result(kind: str, future) -> dict[str, Any]:
        try:
            return {"ok": True, "kind": kind, "payload": future.result()}
        except concurrent.futures.CancelledError:
            return {"ok": False, "kind": kind, "cancelled": True, "error": "Task superseded."}
        except ChassisConversionCancelled as exc:
            return {"ok": False, "kind": kind, "cancelled": True, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "kind": kind, "error": str(exc)}

    @Slot(object)
    def _apply_result(self, result):
        kind = result.get("kind")
        if kind == "preview" and str(result.get("source_path") or "") != self._selected_source:
            return
        if kind == "install":
            self._install_future = None
            self._install_cancel_event = None
        self._running = False
        if result.get("cancelled"):
            self.changed.emit()
            return
        if not result.get("ok"):
            self._status = "Full-livery task failed"
            self._summary = str(result.get("error") or "Unknown error")
            self.log.append(f"Full-livery task failed: {self._summary}", "error")
            self.changed.emit()
            return
        payload = result.get("payload") or {}
        if kind == "scan":
            rows = payload.get("rows") or []
            inspected = int(payload.get("inspected") or 0)
            locked = int(payload.get("locked") or 0)
            foreign_blocked = int(payload.get("foreign_blocked") or 0)
            empty = int(payload.get("empty") or 0)
            game_assets_ready = bool(payload.get("game_assets_ready"))
            self._source_privacy = {
                str(row.get("path") or ""): {
                    "exportable": bool(row.get("exportable")),
                    "privacyDetail": str(row.get("privacyDetail") or ""),
                }
                for row in rows
                if row.get("path")
            }
            self._sources.replace(rows)
            self._status = "FH6 livery scan complete"
            if rows:
                scan_summary = (
                    f"Found {len(rows):,} owned full-car liveries from {inspected:,} local records. "
                    f"{foreign_blocked:,} require foreign vinyls to be removed before export. "
                    f"Excluded {locked:,} liveries owned by other players and {empty:,} empty records."
                )
                if game_assets_ready:
                    self._summary = scan_summary
                else:
                    self._status = "FH6 folder required"
                    detail = str(payload.get("game_asset_error") or "").strip()
                    self._summary = (
                        "The saves were found, but the FH6 installation was not. Choose this PC's FH6 game "
                        "or Content folder to resolve the cars and build previews."
                        + (f" {detail}" if detail else "")
                    )
            elif locked:
                self._summary = f"No owned full-car liveries found. Excluded {locked:,} liveries owned by other players."
            else:
                self._summary = str(payload.get("warning") or "No shareable FH6 full-car livery records were found.")
            if self._refresh_active_source_after_scan(rows):
                return
        elif kind == "export":
            path = str(payload.get("path") or "")
            self._status = "Full-livery package created"
            self._summary = (
                f"Saved {Path(path).name} in Saved packages after a complete reopen and hash verification."
            )
            self.log.append(f"Created portable full-livery package: {path}")
            self._refresh_packages(open_remembered=False)
            self.selectPackage(path)
        elif kind == "install":
            self._status = "FH6 livery installed"
            self._summary = (
                f"Added {payload.get('title') or 'the livery'} as a new same-car FH6 save entry. "
                "The package was reopened and verified after installation."
            )
            self.log.append(
                f"Installed same-car FH6 full livery at {payload.get('installed_folder')}; "
                f"recovery record: {payload.get('backup_path')}"
            )
            self.changed.emit()
            self.scanSaves()
            return
        elif kind == "preview":
            preview_path = str(payload.get("path") or "")
            self._open_package(preview_path, remember=False)
            if self._selected_package == str(Path(preview_path).resolve()):
                self._active_source_preview = str(result.get("source_path") or "")
        elif kind == "add-package":
            self._complete_added_package(payload)
        elif kind == "migrate-package":
            self.log.append(
                f"Updated a saved full-livery package from compiler revision "
                f"{payload.get('migrated_from_revision', 0)} to {PACKAGE_COMPILER_REVISION}."
            )
            self._refresh_packages(open_remembered=False)
            self._open_package(str(payload.get("path") or ""), remember=bool(payload.get("remember")))
        elif kind == "clear-cache":
            files = int(payload.get("files") or 0)
            bytes_removed = int(payload.get("bytes") or 0)
            removed_mib = bytes_removed / (1024 * 1024)
            self._status = "Full-livery cache cleared"
            self._summary = f"Removed {files:,} cached files ({removed_mib:.1f} MiB)."
            self.log.append(self._summary)
            reopen_source = str(result.get("reopen_source") or "")
            reopen_package = str(result.get("reopen_package") or "")
            if reopen_source and Path(reopen_source).is_file():
                self.selectSource(reopen_source)
                return
            if reopen_package and Path(reopen_package).is_file():
                self._open_package(reopen_package, remember=False)
                return
        self.changed.emit()

    @Slot(object)
    def _apply_mesh_result(self, result):
        if int(result.get("request_serial") or -1) != self._mesh_serial:
            return
        if str(result.get("package_path") or "") != self._selected_package:
            return
        if result.get("cancelled"):
            return
        if not result.get("ok"):
            self._status = "Package open; 3D unavailable"
            self._summary = str(result.get("error") or "The matching local car mesh could not be prepared.")
            self.log.append(f"Full-livery inspection mesh unavailable: {self._summary}", "warning")
            self.changed.emit()
            return
        payload = result.get("payload") or {}
        if (
            str(payload.get("package_path") or "") != self._selected_package
            or str(self._current_manifest.get("package_id") or "") != str(payload.get("package_id") or "")
        ):
            return
        try:
            self._inspector.set_local_mesh(payload.get("mesh_path"))
            self._inspector.set_local_render_contract(
                payload.get("render_root"), payload.get("render_contract") or {}
            )
            base = self._inspector.start()
            self._selection_serial += 1
            self._viewer_url = (
                f"{base}?selection={self._selection_serial}"
                f"&package={payload.get('package_id', '')}"
                f"&mesh={Path(payload.get('mesh_path')).stat().st_mtime_ns}"
            )
            self._status = "Exact local livery preview ready"
            self._summary = (
                f"Resolved {payload.get('model_code')} and its direct FH6 livery mapping from this PC's installation."
            )
            if payload.get("revision_warning"):
                self._summary += f" Viewer note: {payload['revision_warning']}."
        except Exception as exc:
            self._status = "Package open; 3D unavailable"
            self._summary = str(exc)
        self.changed.emit()

    def _refresh_decisions(self) -> None:
        if not self._current_manifest:
            self._decisions.replace([])
            return
        decision = compatibility_decision(self._current_manifest, "fh6")
        rows = [
            {
                "action": "STATUS",
                "item": str(decision.get("status") or "unknown").replace("-", " ").title(),
                "detail": decision.get("reason") or "",
            }
        ]
        for item in decision.get("keep_roles") or []:
            rows.append({"action": "KEEP", "item": str(item).replace("-", " ").title(), "detail": "Retained from this package."})
        for item in decision.get("translate") or []:
            rows.append({"action": "CHANGE", "item": str(item).replace("-", " ").title(), "detail": "Must be rewritten for the destination."})
        discarded = decision.get("discard_roles") or decision.get("discard_roles_on_game_install") or []
        for item in discarded:
            rows.append({"action": "DISCARD", "item": str(item).replace("-", " ").title(), "detail": "Not written into the destination save."})
        self._decisions.replace(rows)

    @Slot()
    def close(self):
        self._cancel_source_preview()
        self._cancel_mesh_preparation()
        if self._install_cancel_event is not None:
            self._install_cancel_event.set()
        if self._preview_future is not None and not self._preview_future.done():
            try:
                self._preview_future.result(timeout=3.0)
            except Exception:
                pass
        if self._mesh_future is not None and not self._mesh_future.done():
            try:
                self._mesh_future.result(timeout=3.0)
            except Exception:
                pass
        if self._install_future is not None and not self._install_future.done():
            try:
                self._install_future.result(timeout=5.0)
            except Exception:
                pass
        self._inspector.close()
        self._executor.shutdown(wait=False, cancel_futures=True)
