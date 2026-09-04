from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from tools.livery import (
    PACKAGE_COMPILER_REVISION,
    compatibility_decision,
)
from tools.livery.vehicle_assets import (
    discover_fh6_game_folder,
)

from .app_paths import AppPaths
from .experimental.full_livery.catalog import FullLiveryCatalog
from .experimental.full_livery.diagnostics import export_diagnostic_bundle
from .experimental.full_livery.feature_gate import FullLiveryFeatureGate
from .experimental.full_livery.paths import FullLiveryPaths
from .experimental.full_livery.protocol import write_json_atomic
from .experimental.full_livery.supervisor import (
    FullLiveryInspectorSupervisor,
    FullLiveryTaskSupervisor,
)
from .log_service import LogService
from .lifecycle import discard_queued_events
from .models import DictListModel
from .qt_utils import safe_file_part


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
        self._closed = False
        self.paths = paths
        self.log = log
        # Retained for compatibility with launchers from the supporter-gated prototype.
        del supporter
        self._experiment_paths = FullLiveryPaths.for_app(paths)
        self._experiment_paths.ensure()
        try:
            app_version = (paths.app_root / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            app_version = ""
        self._gate = FullLiveryFeatureGate.resolve(
            demo=demo,
            qualification_file=self._experiment_paths.qualification_file,
            app_version=app_version,
        )
        self._package_root = self._experiment_paths.package_root
        self._settings_file = self._experiment_paths.settings_file
        self._settings = self._load_settings()
        self._game_folder = self._resolve_initial_game_folder()
        if self._game_folder and self._settings.get("fh6_game_folder") != self._game_folder:
            self._settings["fh6_game_folder"] = self._game_folder
            self._save_settings()
        self._save_root = str(self._settings.get("fh6_save_root") or "")
        self._active = False
        self._resume_after_cancel = False
        self._running = False
        self._status = "Experimental · " + self._gate.stage.title()
        self._summary = self._gate.describe()
        self._selected_source = ""
        self._active_source_preview = ""
        self._active_source_fingerprint = ""
        self._source_fingerprints: dict[str, str] = {}
        self._source_privacy: dict[str, dict[str, Any]] = {}
        self._selected_package = str(self._settings.get("last_package") or "")
        self._viewer_url = ""
        self._current_manifest: dict[str, Any] = {}
        self._sources = DictListModel(self.SOURCE_ROLES, self)
        self._packages = DictListModel(self.PACKAGE_ROLES, self)
        self._decisions = DictListModel(self.DECISION_ROLES, self)
        self._selection_serial = 0
        self._source_preview_serial = 0
        self._mesh_serial = 0
        self._catalog = FullLiveryCatalog(
            self._experiment_paths.catalog_file,
            self._experiment_paths.quarantine,
        )
        self._tasks = FullLiveryTaskSupervisor(paths, self._experiment_paths, log, self)
        self._tasks.completed.connect(self._route_worker_result)
        self._tasks.stateChanged.connect(self._sync_task_state)
        self._inspector = FullLiveryInspectorSupervisor(paths, self._experiment_paths, self)
        self._inspector.ready.connect(self._inspector_ready)
        self._inspector.failed.connect(self._inspector_failed)
        self._viewer_memory_timer = QTimer(self)
        self._viewer_memory_timer.setInterval(1000)
        self._viewer_memory_timer.timeout.connect(self._monitor_viewer_memory)
        self._viewer_memory_baseline = 0
        self._viewer_memory_peak = 0
        self._resultReady.connect(self._apply_result)
        self._meshResultReady.connect(self._apply_mesh_result)
        self._load_catalog_models()

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
        if not self._gate.can_install or not self._current_manifest:
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

    @Property(str, notify=changed)
    def featureStage(self):
        return self._gate.stage

    @Property(bool, notify=changed)
    def featureEnabled(self):
        return self._gate.enabled

    @Property(bool, notify=changed)
    def featureStable(self):
        return self._gate.is_stable

    @Property(bool, notify=changed)
    def pageActive(self):
        return self._active

    def _load_settings(self) -> dict[str, Any]:
        return self._experiment_paths.load_settings()

    def _save_settings(self) -> None:
        self._experiment_paths.save_settings(self._settings)

    def _load_catalog_models(self) -> None:
        source_rows = self._catalog.source_rows()
        source_rows = [row for row in source_rows if row.get("_visible")]
        self._source_fingerprints = {
            str(row.get("path") or ""): str(row.get("_contentHash") or "")
            for row in source_rows
            if row.get("path")
        }
        source_rows = [
            {key: value for key, value in row.items() if not key.startswith("_")}
            for row in source_rows
        ]
        source_rows.sort(
            key=lambda row: (str(row.get("modified") or ""), str(row.get("title") or "").casefold()),
            reverse=True,
        )
        package_rows = self._catalog.package_rows()
        package_rows.sort(
            key=lambda row: (int(row.get("mtimeNs") or 0), str(row.get("title") or "").casefold()),
            reverse=True,
        )
        for row in package_rows:
            row.pop("mtimeNs", None)
        self._sources.replace(source_rows)
        self._packages.replace(package_rows)
        self._source_privacy = {
            str(row.get("path") or ""): {
                "exportable": bool(row.get("exportable")),
                "privacyDetail": str(row.get("privacyDetail") or ""),
                "carId": int(row.get("carId") or 0),
                "title": str(row.get("title") or ""),
            }
            for row in source_rows
            if row.get("path")
        }

    @Slot()
    def _sync_task_state(self) -> None:
        running = self._tasks.running
        if running != self._running:
            self._running = running
            self.changed.emit()

    @Slot()
    def activate(self):
        if self._closed or self._active:
            return
        self._active = True
        self._load_catalog_models()
        if not self._gate.enabled:
            self._status = "Full Liveries disabled"
            self._summary = self._gate.describe()
            self.changed.emit()
            return
        if self._tasks.running:
            self._resume_after_cancel = True
            self._running = True
            self._status = "Finishing previous livery cleanup"
            self._summary = "KFPS is releasing the previous experimental worker before reopening the workspace."
            self.changed.emit()
            return
        self._status = "Opening experimental workspace"
        self._summary = self._gate.describe()
        self.changed.emit()
        self.scanSaves()

    @Slot()
    def deactivate(self):
        if not self._active:
            return
        self._active = False
        self._resume_after_cancel = False
        self._selection_serial += 1
        self._source_preview_serial += 1
        self._mesh_serial += 1
        self._viewer_url = ""
        self._stop_viewer_memory_guard()
        self._inspector.stop()
        self._tasks.cancel("livery page closed")
        self._running = self._tasks.running
        self._status = "Experimental workspace paused"
        self._summary = "The livery worker and 3D viewer have been released. Cached indexes remain ready for next time."
        self.changed.emit()

    def _worker_payload(self, **values: Any) -> dict[str, Any]:
        return {
            "game_folder": self._game_folder,
            "save_root": self._save_root,
            **values,
        }

    def _route_worker_result(self, result: dict[str, Any]) -> None:
        if "payload" not in result and isinstance(result.get("value"), dict):
            result = {**result, "payload": result["value"]}
        resume = self._resume_after_cancel and self._active and bool(result.get("cancelled"))
        if str(result.get("kind") or "") == "mesh":
            self._meshResultReady.emit(result)
        else:
            self._resultReady.emit(result)
        if resume:
            self._resume_after_cancel = False
            self.scanSaves()

    @Slot(str)
    def _inspector_ready(self, url: str) -> None:
        if not self._active or not url:
            self._inspector.stop()
            return
        self._viewer_url = url
        self._viewer_memory_baseline = self._process_tree_memory()
        self._viewer_memory_peak = self._viewer_memory_baseline
        self._viewer_memory_timer.start()
        self._running = False
        self._status = "Local livery preview ready"
        self._summary = "The isolated 3D viewer is ready. Leaving this page releases it completely."
        self.changed.emit()

    @Slot(str)
    def _inspector_failed(self, message: str) -> None:
        self._viewer_url = ""
        self._stop_viewer_memory_guard()
        self._running = False
        self._status = "3D viewer failed"
        self._summary = str(message or "The isolated 3D viewer stopped before it was ready.")
        self.changed.emit()

    @staticmethod
    def _process_tree_memory() -> int:
        try:
            root = psutil.Process(os.getpid())
            processes = [root, *root.children(recursive=True)]
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return 0
        total = 0
        for process in processes:
            try:
                total += int(process.memory_info().rss)
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return total

    def _stop_viewer_memory_guard(self) -> None:
        self._viewer_memory_timer.stop()
        self._viewer_memory_baseline = 0
        self._viewer_memory_peak = 0

    @Slot()
    def _monitor_viewer_memory(self) -> None:
        if not self._viewer_url or not self._active:
            self._stop_viewer_memory_guard()
            return
        current = self._process_tree_memory()
        if current <= 0:
            return
        self._viewer_memory_peak = max(self._viewer_memory_peak, current)
        growth = max(0, current - self._viewer_memory_baseline)
        if growth <= 4 * 1024 * 1024 * 1024:
            return
        try:
            write_json_atomic(
                self._experiment_paths.diagnostics / "viewer-memory-guard.json",
                {
                    "time": datetime.now().isoformat(),
                    "baseline_bytes": self._viewer_memory_baseline,
                    "peak_bytes": self._viewer_memory_peak,
                    "growth_bytes": growth,
                    "selected_package": Path(self._selected_package).name,
                },
            )
        except OSError:
            pass
        self._viewer_url = ""
        self._inspector.stop()
        self._stop_viewer_memory_guard()
        self._running = False
        self._status = "3D preview stopped safely"
        self._summary = (
            "The livery viewer used an abnormal amount of memory and was closed before it could affect KFPS. "
            "Export Diagnostics from this page before trying that car again."
        )
        self.changed.emit()

    def _resolve_initial_game_folder(self) -> str:
        configured_value = str(self._settings.get("fh6_game_folder") or "").strip()
        discovered = discover_fh6_game_folder(configured_value or None)
        return str(discovered) if discovered else ""

    @Slot()
    def chooseGameFolder(self):
        if not self._gate.enabled:
            return
        start = Path(self._game_folder) if self._game_folder else self.paths.app_root
        folder = QFileDialog.getExistingDirectory(None, "Choose the FH6 game or Content folder", str(start))
        if not folder:
            return
        self._running = True
        self._status = "Linking FH6 assets"
        self._summary = "Building the private car and projection index in the isolated livery worker."
        self.changed.emit()
        self._tasks.start(
            "link-game",
            self._worker_payload(folder=folder),
            kind="link-game",
        )

    @Slot()
    def chooseSaveRoot(self):
        if not self._gate.enabled:
            return
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
        if self._running or not self._gate.enabled:
            return
        reopen_source = self._active_source_preview or self._selected_source
        reopen_package = "" if reopen_source else self._selected_package
        self._cancel_source_preview()
        self._cancel_mesh_preparation()
        self._inspector.stop()
        self._current_manifest = {}
        self._selected_package = ""
        self._viewer_url = ""
        self._active_source_preview = ""
        self._running = True
        self._status = "Clearing full-livery cache"
        self._summary = "Removing rebuildable car meshes, section atlases, previews, and the FH6 vehicle index."
        self.changed.emit()
        self._tasks.start(
            "clear-cache",
            self._worker_payload(),
            kind="clear-cache",
            metadata={"reopen_source": reopen_source, "reopen_package": reopen_package},
        )

    @Slot()
    def scanSaves(self):
        if self._closed or self._running or not self._gate.can_preview:
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
        if not self._tasks.start("scan-saves", self._worker_payload(), kind="scan"):
            self._running = False
            self._status = "Livery worker busy"
            self._summary = "Finish or cancel the current full-livery task before scanning saves."
            self.changed.emit()

    @Slot(str)
    def selectSource(self, path: str):
        if not self._gate.can_preview:
            return
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
            resolved_source = str(source.resolve())
            same_source_is_active = (
                resolved_source == self._selected_source
                and (self._tasks.running or self._active_source_preview == resolved_source)
            )
            if same_source_is_active:
                return
            self._cancel_mesh_preparation()
            self._cancel_source_preview()
            self._reset_inspector_session()
            self._selected_source = resolved_source
            self._active_source_preview = ""
            request_serial = self._source_preview_serial
            self._running = True
            self._status = "Preparing local livery preview"
            selected_privacy = self._source_privacy.get(self._selected_source) or {}
            self._summary = (
                selected_privacy.get("privacyDetail")
                or "Building or reopening this livery's private local car preview."
            )
            self.changed.emit()
            self._tasks.start(
                "preview-source",
                self._worker_payload(source=resolved_source),
                kind="preview",
                metadata={"source_path": resolved_source, "request_serial": request_serial},
                supersede=True,
            )

    @Slot(str)
    def selectPackage(self, path: str):
        if not self._gate.can_preview:
            return
        self._selected_source = ""
        self._cancel_source_preview()
        self._cancel_mesh_preparation()
        self._reset_inspector_session()
        self._active_source_preview = ""
        try:
            selected = str(Path(path).resolve())
            if not Path(selected).is_file():
                raise FileNotFoundError("The selected full-livery package no longer exists.")
        except Exception as exc:
            self._status = "Package rejected"
            self._summary = str(exc)
            self.changed.emit()
            return
        self._selected_package = selected
        self._running = True
        self._status = "Verifying full-livery package"
        self._summary = "Reopening the package in the isolated livery worker before rendering it."
        self.changed.emit()
        self._tasks.start(
            "open-package",
            self._worker_payload(path=selected, remember=True),
            kind="open-package",
            metadata={"package_path": selected},
            supersede=True,
        )

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
        self._tasks.start(
            "migrate-package",
            self._worker_payload(path=path, remember=remember),
            kind="migrate-package",
            supersede=True,
        )

    def _open_package(self, path: str, *, remember: bool) -> None:
        selected = str(Path(path).resolve())
        self._selected_package = selected
        self._running = True
        self._tasks.start(
            "open-package",
            self._worker_payload(path=selected, remember=remember),
            kind="open-package",
            metadata={"package_path": selected},
            supersede=True,
        )

    def _accept_open_package(self, path: str, manifest: dict[str, Any], *, remember: bool) -> None:
        selected = str(Path(path).resolve())
        self._current_manifest = manifest
        self._selected_package = selected
        self._viewer_url = ""
        if remember:
            self._settings["last_package"] = selected
            self._save_settings()
        unresolved = list((manifest.get("livery") or {}).get("unresolved_raster_ids") or [])
        self._status = "Package open"
        self._summary = (
            "The package passed its integrity checks. Preparing its local FH6 preview; "
            "unresolved referenced artwork remains preserved in the original livery data."
            if unresolved
            else "The package passed its integrity checks. Preparing its exact local FH6 preview."
        )
        self._refresh_decisions()
        self.changed.emit()
        self._prepare_local_mesh(manifest, selected)

    def _cancel_source_preview(self) -> None:
        self._source_preview_serial += 1
        if self._tasks.current_operation == "preview-source":
            self._tasks.cancel("source selection changed")

    def _reset_inspector_session(self) -> None:
        self._viewer_url = ""
        self._stop_viewer_memory_guard()
        self._current_manifest = {}
        self._selected_package = ""
        self._active_source_fingerprint = ""
        self._decisions.replace([])
        self._inspector.stop()

    def _refresh_active_source_after_scan(
        self,
        rows: list[dict[str, Any]],
        fingerprints: dict[str, str],
    ) -> bool:
        active = self._active_source_preview
        if not active:
            return False
        visible_paths = {str(row.get("path") or "") for row in rows}
        if active not in visible_paths:
            self._inspector.stop()
            self._current_manifest = {}
            self._selected_package = ""
            self._viewer_url = ""
            self._active_source_preview = ""
            self._active_source_fingerprint = ""
            if self._selected_source == active:
                self._selected_source = ""
            return False
        if self._active_source_fingerprint and fingerprints.get(active) == self._active_source_fingerprint:
            return False
        self._selected_source = ""
        self.selectSource(active)
        return True

    @Slot()
    def choosePackage(self):
        if not self._gate.enabled:
            return
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
        if self._running or not self._gate.enabled:
            self._status = "Another full-livery task is already running"
            self.changed.emit()
            return
        self._cancel_mesh_preparation()
        self._running = True
        self._status = "Verifying full-livery package"
        self._summary = "Checking the package against its embedded FH6 source before adding it."
        self.changed.emit()
        self._tasks.start(
            "add-package",
            self._worker_payload(selected=selected),
            kind="add-package",
        )

    @Slot(str, result=bool)
    def addPackage(self, selected: str) -> bool:
        path = Path(str(selected or ""))
        if (
            self._running
            or not self._gate.enabled
            or not path.is_file()
            or path.suffix.casefold() != ".kfpslivery"
        ):
            self._status = "Package not added"
            self._summary = "Choose an existing KFPS full-livery package after the current task finishes."
            self.changed.emit()
            return False
        self._start_add_package(str(path.resolve()))
        return True

    def _complete_added_package(self, payload: dict[str, Any]) -> None:
        upgraded = payload.get("upgraded_from_revision")
        if upgraded is not None:
            self.log.append(
                f"Upgraded an imported full-livery package from compiler revision {upgraded} "
                f"to {PACKAGE_COMPILER_REVISION}."
            )
        target = str(payload.get("path") or "")
        self._refresh_packages_then_open(target)

    def _automatic_package_target(self, source: Path, car_id: int) -> Path:
        metadata = self._source_privacy.get(str(source.resolve())) or {}
        title = str(metadata.get("title") or source.parent.name or "FH6 full livery")
        stem = safe_file_part(f"{title} - FH6 {car_id}", f"FH6-livery-{car_id}")[:120].rstrip(" .")
        target = self._package_root / f"{stem}.kfpslivery"
        suffix = 2
        while target.exists():
            target = self._package_root / f"{stem} ({suffix}).kfpslivery"
            suffix += 1
        return target

    @Slot()
    def exportSelected(self):
        if self._running or not self._gate.can_export:
            return
        source = Path(self._selected_source)
        if not source.is_file():
            self._status = "Choose an FH6 livery"
            self._summary = "Select one shareable local full-car livery before exporting a package."
            self.changed.emit()
            return
        metadata = self._source_privacy.get(str(source.resolve())) or {}
        if not metadata or not bool(metadata.get("exportable")):
            self._status = "Export unavailable"
            self._summary = (
                str(metadata.get("privacyDetail") or "Scan FH6 saves again before exporting this livery.")
            )
            self.changed.emit()
            return
        car_id = int(metadata.get("carId") or 0)
        if car_id <= 0:
            self._status = "Export unavailable"
            self._summary = "KFPS could not resolve this livery's exact FH6 car. Scan saves again."
            self.changed.emit()
            return
        output = self._automatic_package_target(source, car_id)
        self._running = True
        self._status = "Building full-livery package"
        self._summary = "Building and verifying the package before adding it to Saved packages."
        self.changed.emit()
        self._tasks.start(
            "export-package",
            self._worker_payload(source=str(source.resolve()), output=str(output.resolve())),
            kind="export",
        )

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
        self._running = True
        self._status = "Installing exact-car FH6 livery"
        self._summary = "Verifying the package, creating a recovery record, and staging a new local livery."
        self.changed.emit()
        self._tasks.start(
            "install-package",
            self._worker_payload(package=str(package.resolve())),
            kind="install",
        )

    @Slot()
    def refreshPackages(self):
        if self._closed:
            return
        cached = self._catalog.package_rows()
        cached.sort(key=lambda row: int(row.get("mtimeNs") or 0), reverse=True)
        for row in cached:
            row.pop("mtimeNs", None)
        self._packages.replace(cached)
        if self._running or not self._active or not self._gate.enabled:
            self.changed.emit()
            return
        self._running = True
        self._status = "Indexing saved livery packages"
        self.changed.emit()
        self._tasks.start("refresh-packages", self._worker_payload(), kind="refresh-packages")

    def _refresh_packages_then_open(self, package: str) -> None:
        self._running = True
        self._status = "Updating saved package index"
        self._summary = "Recording the verified package before opening it."
        self.changed.emit()
        if not self._tasks.start(
            "refresh-packages",
            self._worker_payload(),
            kind="refresh-packages",
            metadata={"open_package": str(package)},
        ):
            self._running = False
            self._status = "Package index busy"
            self._summary = "The package is safe on disk; reopen the Liveries tab to index it."
            self.changed.emit()

    @Slot()
    def openPackageFolder(self):
        self._package_root.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self._package_root))

    def _prepare_local_mesh(self, manifest: dict[str, Any], package_path: str) -> None:
        self._cancel_mesh_preparation()
        if not self._gate.can_preview:
            return
        if not self._game_folder:
            self._status = "FH6 assets needed for 3D"
            self._summary = "The package is valid. Choose the local FH6 game folder to resolve its inspection mesh."
            self.changed.emit()
            return
        package_id = str(manifest.get("package_id") or "")
        car_id = int((manifest.get("livery") or {}).get("target_car_id") or 0)
        vehicle = manifest.get("vehicle") or {}
        request_serial = self._mesh_serial
        self._running = True
        self._status = "Preparing local chassis"
        self._summary = "Reading this car's neutral inspection geometry and livery UV map from the local FH6 installation."
        self.changed.emit()
        self._tasks.start(
            "prepare-mesh",
            self._worker_payload(
                package_id=package_id,
                car_id=car_id,
                expected_model_code=str(vehicle.get("model_code") or ""),
                expected_archive_sha256=str(vehicle.get("archive_sha256") or ""),
                package_path=package_path,
            ),
            kind="mesh",
            metadata={"package_path": package_path, "request_serial": request_serial},
            supersede=True,
        )

    def _cancel_mesh_preparation(self) -> None:
        self._mesh_serial += 1
        if self._tasks.current_operation == "prepare-mesh":
            self._tasks.cancel("mesh selection changed")

    @Slot(object)
    def _apply_result(self, result):
        if self._closed:
            return
        kind = result.get("kind")
        if kind == "preview":
            if int(result.get("request_serial") or -1) != self._source_preview_serial:
                return
            if str(result.get("source_path") or "") != self._selected_source:
                return
        self._running = False
        if result.get("cancelled"):
            if self._active and not self._tasks.running:
                self._status = "Full-livery task cancelled"
                self._summary = str(result.get("error") or "The isolated task stopped safely.")
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
            fingerprints = {
                str(path): str(fingerprint)
                for path, fingerprint in dict(payload.get("fingerprints") or {}).items()
            }
            inspected = int(payload.get("inspected") or 0)
            locked = int(payload.get("locked") or 0)
            foreign_blocked = int(payload.get("foreign_blocked") or 0)
            incomplete_blocked = int(payload.get("incomplete_blocked") or 0)
            empty = int(payload.get("empty") or 0)
            game_assets_ready = bool(payload.get("game_assets_ready"))
            stale_index = bool(payload.get("stale_index"))
            self._source_privacy = {
                str(row.get("path") or ""): {
                    "exportable": bool(row.get("exportable")),
                    "privacyDetail": str(row.get("privacyDetail") or ""),
                    "carId": int(row.get("carId") or 0),
                    "title": str(row.get("title") or ""),
                }
                for row in rows
                if row.get("path")
            }
            self._source_fingerprints = fingerprints
            self._sources.replace(rows)
            self._status = "FH6 livery scan complete"
            if stale_index:
                self._status = "Showing last complete livery index"
                self._summary = str(payload.get("warning") or "The configured FH6 save folder is unavailable.")
            elif rows:
                livery_label = "livery" if len(rows) == 1 else "liveries"
                foreign_verb = "requires" if foreign_blocked == 1 else "require"
                incomplete_verb = "contains" if incomplete_blocked == 1 else "contain"
                excluded_label = "livery" if locked == 1 else "liveries"
                scan_summary = (
                    f"Found {len(rows):,} owned full-car {livery_label} from {inspected:,} local records. "
                    f"{foreign_blocked:,} {foreign_verb} foreign vinyls to be removed before export. "
                    f"{incomplete_blocked:,} {incomplete_verb} incomplete or unsupported source data. "
                    f"Excluded {locked:,} {excluded_label} owned by other players and {empty:,} empty records."
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
            if self._refresh_active_source_after_scan(rows, fingerprints):
                return
            self.changed.emit()
            self.refreshPackages()
            return
        elif kind == "refresh-packages":
            rows = list(payload.get("rows") or [])
            self._packages.replace(rows)
            cache_hits = int(payload.get("cache_hits") or 0)
            self._status = "Full-livery index ready"
            self._summary = (
                f"Indexed {len(rows):,} saved packages; reused {cache_hits:,} unchanged catalog entries."
            )
            open_package = str(result.get("open_package") or "")
            if open_package and Path(open_package).is_file():
                self.selectPackage(open_package)
                return
        elif kind == "link-game":
            self._game_folder = str(payload.get("game_folder") or "")
            self._settings["fh6_game_folder"] = self._game_folder
            self._save_settings()
            self._status = "FH6 assets linked"
            self._summary = (
                f"Indexed {int(payload.get('vehicle_count') or 0):,} FH6 cars and projection contracts."
            )
            self.changed.emit()
            self.scanSaves()
            return
        elif kind == "export":
            path = str(payload.get("path") or "")
            self._status = "Full-livery package created"
            self._summary = (
                f"Saved {Path(path).name} in Saved packages after a complete reopen and hash verification."
            )
            self.log.append(f"Created portable full-livery package: {path}")
            self._refresh_packages_then_open(path)
            return
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
            manifest = payload.get("manifest") or {}
            self._accept_open_package(preview_path, manifest, remember=False)
            self._active_source_preview = str(result.get("source_path") or "")
            self._active_source_fingerprint = self._source_fingerprints.get(
                self._active_source_preview,
                "",
            )
        elif kind == "add-package":
            self._complete_added_package(payload)
        elif kind == "open-package":
            selected = str(payload.get("path") or result.get("package_path") or "")
            manifest = payload.get("manifest") or {}
            migrated = payload.get("migrated_from_revision")
            if migrated is not None:
                self.log.append(
                    f"Updated a saved full-livery package from compiler revision {migrated} "
                    f"to {PACKAGE_COMPILER_REVISION}."
                )
            self._accept_open_package(selected, manifest, remember=bool(payload.get("remember", True)))
        elif kind == "migrate-package":
            self.log.append(
                f"Updated a saved full-livery package from compiler revision "
                f"{payload.get('migrated_from_revision', 0)} to {PACKAGE_COMPILER_REVISION}."
            )
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

    @Slot()
    def exportDiagnostics(self):
        suggested = self._experiment_paths.diagnostics / (
            f"KFPS-Full-Livery-Diagnostics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        )
        selected, _ = QFileDialog.getSaveFileName(
            None,
            "Save full-livery diagnostics",
            str(suggested),
            "ZIP archives (*.zip)",
        )
        if not selected:
            return
        target = Path(selected)
        if target.suffix.casefold() != ".zip":
            target = target.with_suffix(".zip")
        try:
            export_diagnostic_bundle(
                target,
                sessions_root=self._experiment_paths.sessions,
                recovery_root=self._experiment_paths.recovery,
                catalog_stats=self._catalog.stats(),
                release_state={
                    "stage": self._gate.stage,
                    "source": self._gate.source,
                    "stable": self._gate.is_stable,
                    "qualification": (
                        {
                            "qualified": self._gate.qualification.qualified,
                            "missing": list(self._gate.qualification.missing),
                            "invalid": list(self._gate.qualification.invalid),
                        }
                        if self._gate.qualification is not None else None
                    ),
                },
            )
            self._status = "Diagnostics exported"
            self._summary = f"Saved privacy-scrubbed full-livery diagnostics to {target.name}."
        except Exception as exc:
            self._status = "Diagnostic export failed"
            self._summary = str(exc)
        self.changed.emit()

    @Slot(object)
    def _apply_mesh_result(self, result):
        if self._closed:
            return
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
            self._running = True
            self._status = "Starting isolated 3D viewer"
            self._summary = "Opening the prepared car in a disposable local viewer process."
            self._inspector.start(
                package=self._selected_package,
                mesh=str(payload.get("mesh_path") or ""),
                render_root=str(payload.get("render_root") or ""),
                render_contract=payload.get("render_contract") or {},
            )
            unresolved = list((self._current_manifest.get("livery") or {}).get("unresolved_raster_ids") or [])
            viewer_detail = f"Resolved {payload.get('model_code')} and its direct FH6 livery mapping from this PC's installation."
            if unresolved:
                viewer_detail += (
                    " Some referenced artwork is unavailable in the preview; the original FH6 livery data remains preserved."
                )
            if payload.get("revision_warning"):
                viewer_detail += f" Viewer note: {payload['revision_warning']}."
            self.log.append(viewer_detail)
        except Exception as exc:
            self._running = False
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
        if self._closed:
            return
        self._closed = True
        self._stop_viewer_memory_guard()
        self._inspector.close()
        self._tasks.close()
        discard_queued_events(self)
