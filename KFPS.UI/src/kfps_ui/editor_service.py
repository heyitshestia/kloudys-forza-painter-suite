from __future__ import annotations

import json
import importlib.util
import re
import stat
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService, validated_output_file
from .log_service import LogService
from .lifecycle import discard_queued_events
from .models import DictListModel
from .preview_service import PreviewService
from .editor_launch import launch_editor
from .garage_index import log_body_launch

PROJECT_SCAN_MAX_BYTES = 150 * 1024 * 1024


def _validated_livery_package(paths: AppPaths, value: str) -> Path:
    from .experimental.full_livery.paths import FullLiveryPaths

    message = "Choose an existing package from the Liveries package library."
    if not isinstance(value, str) or not value or len(value) > 32768:
        raise ValueError(message)
    root = FullLiveryPaths.for_app(paths).package_root.absolute()
    candidate = Path(value).absolute()
    if candidate.suffix.casefold() != ".kfpslivery" or not candidate.is_relative_to(root):
        raise ValueError(message)
    for item in (candidate, *candidate.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Redirected livery package paths are not supported.")
    candidate = candidate.resolve(strict=True)
    if not candidate.is_relative_to(root.resolve()) or not root.resolve().is_relative_to(paths.app_root.resolve()):
        raise ValueError(message)
    metadata = candidate.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("Choose an ordinary livery package file.")
    return candidate


def _studio_module_path(app_root: Path, module_name: str) -> Path:
    if module_name not in {"host_bridge.py", "source_editor.py"}:
        raise ValueError("Unsupported Studio module.")
    root = Path(app_root).absolute()
    package = root / "tools/livery-studio"
    boundary = root
    for item in (package, package.parent, root):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Studio package discovery cannot follow redirected paths.")
    if not package.exists() and not package.is_symlink() and not package.is_junction():
        if root.name != "repo":
            raise ValueError("Livery Studio is not installed in tools/livery-studio.")
        package, boundary = root.parent / "livery", root.parent
        config = package / "settings/local-launch.json"
        for item in (config, *config.parents):
            if item.is_symlink() or item.is_junction():
                raise ValueError("Studio workspace discovery cannot follow redirected paths.")
            if item == boundary:
                break
        try:
            with config.open("rb") as stream:
                body = stream.read(65537)
            value = json.loads(body) if len(body) <= 65536 else None
            if not isinstance(value, dict) or not isinstance(value.get("kfpsRoot"), str):
                raise ValueError("Missing workspace host identity.")
            if Path(value["kfpsRoot"]).resolve() != root.resolve():
                raise ValueError("Studio is configured for another KFPS installation.")
        except (OSError, ValueError) as exc:
            raise ValueError("The isolated Studio workspace configuration is unavailable or invalid.") from exc
    path = package / "src/kfps_livery_lab" / module_name
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError("Studio discovery cannot follow redirected paths.")
        if item == boundary:
            break
    if not path.is_file() or not path.resolve().is_relative_to(package.resolve()):
        raise ValueError("Livery Studio is incomplete in its selected package.")
    return path


class EditorService(QObject):
    changed = Signal()
    editorOutputsChanged = Signal()
    launchCompleted = Signal(bool, str, str)
    previewCompleted = Signal(str, str)
    scanCompleted = Signal(int, object, str)
    studioLaunchCompleted = Signal(bool, str)

    def __init__(
        self,
        paths: AppPaths,
        preview: PreviewService,
        desktop: DesktopService,
        log: LogService,
        parent=None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.preview = preview
        self.desktop = desktop
        self.log = log
        self._closed = False
        self.workspace_editor = None
        self.workspace_studio = None
        self._cancel_event = threading.Event()
        self._threads: set[threading.Thread] = set()
        self._threads_lock = threading.Lock()
        self._project_model = DictListModel(
            ["name", "path", "modifiedLabel", "shapeLabel", "shapeCount"]
        )
        self._all_projects: list[dict] = []
        self._selected = ""
        self._preview = ""
        self._preview_loading = False
        self._shapes = "—"
        self._modified = "—"
        self._search = ""
        self._status = "Ready to open the editor."
        self._launching = False
        self._studio_launching = False
        self._studio_status = ""
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        self._running = False
        self._last_error = ""
        self._preview_lock = threading.Lock()
        self._scan_generation = 0
        self._scan_running = False
        self._scan_cache: dict[Path, tuple[tuple[int, int, int], int | None]] = {}
        self._output_change_marker = self.paths.runtime_root / "fabric-editor" / "editor-output-change.json"
        self._project_change_marker = self.paths.runtime_root / "fabric-editor" / "project-change.json"
        self._output_change_mtime = self._marker_mtime(self._output_change_marker)
        self._project_change_mtime = self._marker_mtime(self._project_change_marker)
        self._change_timer = QTimer(self)
        self._change_timer.setInterval(500)
        self._change_timer.timeout.connect(self._poll_editor_changes)
        self._change_timer.start()
        self.launchCompleted.connect(self._finish_launch)
        self.previewCompleted.connect(self._finish_preview)
        self.scanCompleted.connect(self._finish_scan)
        self.studioLaunchCompleted.connect(self._finish_studio_launch)
        self.refresh()

    @staticmethod
    def _marker_mtime(path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

    @Property(bool, notify=changed)
    def studioLaunching(self):
        return self._studio_launching

    @Property(str, notify=changed)
    def studioStatus(self):
        return self._studio_status

    @Property(str, notify=changed)
    def studioPackagePath(self):
        return self._studio_package_path

    @Slot()
    @Slot("QVariantMap")
    def launchLiveryStudio(self, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        self._studio_launching = True
        self._studio_status = "Preparing Livery Studio..."
        self.changed.emit()
        try:
            # Detach the QML snapshot before sending it to the background worker.
            request = {"ui_theme": json.loads(json.dumps(theme, allow_nan=False))} if theme else {}
            self._start_thread(target=self._launch_studio_worker, args=(request,), name="kfps-studio-launch")
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    @Slot(str)
    @Slot(str, "QVariantMap")
    def launchJsonInLiveryStudio(self, path, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        try:
            candidate = validated_output_file(self.paths, path)
            encoded_theme = json.dumps(theme, allow_nan=False) if theme else ""
            if len(encoded_theme.encode("utf-8")) > 32 * 1024:
                raise ValueError("Theme context exceeds 32 KiB.")
            snapshot = json.loads(encoded_theme) if encoded_theme else None
            self._studio_launching = True
            self._studio_status = "Preparing selected vinyl for Livery Studio..."
            self.changed.emit()
            self._start_thread(target=self._launch_json_studio_worker, args=(str(candidate), snapshot),
                               name="kfps-studio-json-launch")
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    def _launch_json_studio_worker(self, path, theme):
        try:
            if self._cancel_event.is_set():
                return
            candidate = validated_output_file(self.paths, path)
            bridge_path = _studio_module_path(self.paths.app_root, "host_bridge.py")
            spec = importlib.util.spec_from_file_location("_kfps_studio_output_adapter", bridge_path)
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            with candidate.open("rb") as source:
                body = source.read(bridge.MAX_BYTES + 1)
            if len(body) > bridge.MAX_BYTES:
                raise ValueError("Vinyl transfer exceeds 8 MiB.")
            payload = bridge.model.decode_json(body)
            if not isinstance(payload, dict) or "shapes" not in payload:
                raise ValueError("Choose a native vinyl JSON containing shapes.")
            request = {"name": candidate.stem[:120], "vinyl": {"shapes": payload["shapes"]}}
            if theme:
                request["ui_theme"] = theme
            request = bridge.validate_request(request)
            if not self._cancel_event.is_set():
                self._launch_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    @Slot(str)
    @Slot(str, "QVariantMap")
    def launchPackageInLiveryStudio(self, path, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_package_path = str(path or "")
        self._studio_garage_snapshot = None
        try:
            candidate = _validated_livery_package(self.paths, path)
            encoded_theme = json.dumps(theme, allow_nan=False) if theme else ""
            if len(encoded_theme.encode("utf-8")) > 32 * 1024:
                raise ValueError("Theme context exceeds 32 KiB.")
            snapshot = json.loads(encoded_theme) if encoded_theme else None
            self._studio_launching = True
            self._studio_status = "Validating package artwork for Livery Studio..."
            self.changed.emit()
            self._start_thread(target=self._launch_package_studio_worker,
                               args=(str(candidate), snapshot), name="kfps-studio-package-launch")
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    def _launch_package_studio_worker(self, path, theme):
        try:
            if self._cancel_event.is_set():
                return
            candidate = _validated_livery_package(self.paths, path)
            bridge_path = _studio_module_path(self.paths.app_root, "host_bridge.py")
            spec = importlib.util.spec_from_file_location("_kfps_studio_package_adapter", bridge_path)
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            request = bridge.request_for_package(candidate)
            if theme:
                request["ui_theme"] = theme
            request = bridge.validate_request(request)
            if not self._cancel_event.is_set():
                self._launch_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    @Slot("QVariantMap", "QVariantMap", str)
    @Slot("QVariantMap", "QVariantMap", str, "QVariantMap")
    def launchGarageInLiveryStudio(self, identity, snapshot, name, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        try:
            from .garage_index import validate_vehicle_identity, validate_body_snapshot
            identity = validate_vehicle_identity(identity)
            snapshot = validate_body_snapshot(snapshot)
            if not isinstance(name, str) or not 0 < len(name) <= 120 or any(ord(c) < 32 for c in name):
                raise ValueError("The Garage build name is invalid.")
            encoded = json.dumps(theme, allow_nan=False) if theme else ""
            if len(encoded.encode("utf-8")) > 32 * 1024:
                raise ValueError("Theme context exceeds 32 KiB.")
            context = json.loads(encoded) if encoded else None
            self._studio_garage_snapshot = snapshot
            self._studio_launching = True
            self._studio_status = "Preparing selected Garage body build for Studio..."
            log_body_launch(self.log, "studio", "queued", snapshot)
            self.changed.emit()
            self._start_thread(target=self._launch_garage_studio_worker,
                               args=(identity, snapshot, name, context), name="kfps-studio-garage-launch")
        except Exception as exc:
            log_body_launch(self.log, "studio", "rejected", self._studio_garage_snapshot)
            self._finish_studio_launch(False, str(exc))

    def _launch_garage_studio_worker(self, identity, snapshot, name, theme):
        try:
            from .garage_index import validate_vehicle_identity, validate_body_snapshot, resolve_body_vehicle
            from .experimental.full_livery.paths import FullLiveryPaths
            from tools.livery.vehicle_assets import discover_fh6_game_folder
            if self._cancel_event.is_set():
                return
            identity = validate_vehicle_identity(identity)
            snapshot = validate_body_snapshot(snapshot)
            paths = FullLiveryPaths.for_app(self.paths)
            configured = paths.load_settings().get("fh6_game_folder")
            game = discover_fh6_game_folder(configured or None)
            resolve_body_vehicle(game, paths.vehicle_index, identity["car_id"],
                                 model_code=identity["model_code"], cancel_event=self._cancel_event)
            path = _studio_module_path(self.paths.app_root, "host_bridge.py")
            spec = importlib.util.spec_from_file_location("_kfps_studio_garage_adapter", path)
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            request = {"name": name, "layout": {"format": "kfps-livery-layout-v1",
                       "vehicle": identity, "vinyls": [], "placements": [], "garage_build": snapshot}}
            if theme:
                request["ui_theme"] = theme
            request = bridge.validate_request(request)
            if not self._cancel_event.is_set():
                self._launch_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    def _garage_studio_bridge(self):
        path = _studio_module_path(self.paths.app_root, "host_bridge.py")
        spec = importlib.util.spec_from_file_location("_kfps_studio_workflow_adapter", path)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        return bridge

    @staticmethod
    def _studio_theme_snapshot(theme):
        encoded = json.dumps(theme, allow_nan=False) if theme else ""
        if len(encoded.encode("utf-8")) > 32 * 1024:
            raise ValueError("Theme context exceeds 32 KiB.")
        return json.loads(encoded) if encoded else None

    def _queue_studio_project(self, request, theme):
        context = self._studio_theme_snapshot(theme)
        if context:
            request['ui_theme'] = context
        request = self._garage_studio_bridge().validate_request(request)
        self._studio_launching = True
        self._studio_status = "Preparing the exact car for Livery Studio..."
        self.changed.emit()
        self._start_thread(target=self._launch_project_studio_worker, args=(request,),
                           name="kfps-studio-project-launch")

    @Slot("QVariantMap")
    @Slot("QVariantMap", "QVariantMap")
    def launchStockInLiveryStudio(self, identity, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_garage_workflow = True
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        try:
            from .garage_index import validate_vehicle_identity
            request = self._garage_studio_bridge().request_for_stock(validate_vehicle_identity(identity))
            self._queue_studio_project(request, theme)
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    @Slot("QVariantMap")
    @Slot("QVariantMap", "QVariantMap")
    def launchLinkedProjectInLiveryStudio(self, project_info, theme=None):
        if self._closed or self._studio_launching:
            return
        self._studio_garage_workflow = True
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        try:
            from .garage_notes import freeze_project_reference
            info = freeze_project_reference(project_info)
            context = self._studio_theme_snapshot(theme)
            self._studio_launching = True
            self._studio_status = 'Reading the current linked Studio project...'
            self.changed.emit()
            self._start_thread(target=self._launch_linked_project_studio_worker,
                args=(info, context), name='kfps-studio-linked-project')
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    def _launch_linked_project_studio_worker(self, info, theme):
        try:
            if self._cancel_event.is_set():
                return
            from .garage_notes import read_linked_project
            project = read_linked_project(info, self.paths.app_root, cancel=self._cancel_event)
            request = {'name': 'Linked Studio project', 'project': project}
            if theme:
                request['ui_theme'] = theme
            request = self._garage_studio_bridge().validate_request(request)
            if not self._cancel_event.is_set():
                self._launch_project_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    def _resolve_studio_vehicle(self, identity):
        from .garage_index import resolve_body_vehicle
        from .experimental.full_livery.paths import FullLiveryPaths
        from tools.livery.vehicle_assets import discover_fh6_game_folder
        paths = FullLiveryPaths.for_app(self.paths)
        configured = paths.load_settings().get("fh6_game_folder")
        game = discover_fh6_game_folder(configured or None)
        resolve_body_vehicle(game, paths.vehicle_index, identity["car_id"],
                             model_code=identity["model_code"], cancel_event=self._cancel_event)

    def _launch_project_studio_worker(self, request):
        try:
            if self._cancel_event.is_set():
                return
            self._resolve_studio_vehicle(request['project']['vehicle'])
            if not self._cancel_event.is_set():
                self._launch_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    @Slot("QVariantMap", "QVariantMap", str, str)
    @Slot("QVariantMap", "QVariantMap", str, str, "QVariantMap")
    @Slot("QVariantMap", "QVariantMap", str, str, "QVariantMap", str)
    def launchGarageArtworkInLiveryStudio(self, identity, snapshot, path, kind="package", theme=None, expected=""):
        if self._closed or self._studio_launching:
            return
        self._studio_garage_workflow = True
        self._studio_package_path = ""
        self._studio_garage_snapshot = None
        try:
            from .garage_index import validate_vehicle_identity, validate_body_snapshot
            identity = validate_vehicle_identity(identity)
            snapshot = validate_body_snapshot(snapshot)
            if not isinstance(expected, str) or expected and not re.fullmatch(r'[a-f0-9]{64}', expected):
                raise ValueError('The artwork fingerprint is invalid. Refresh Garage and retry.')
            if kind not in ('package', 'save'):
                raise ValueError('Choose package or save artwork from the Garage catalogue.')
            if not isinstance(path, str) or not path or len(path) > 32768:
                raise ValueError('Choose an existing Garage artwork entry.')
            candidate = _validated_livery_package(self.paths, path) if kind == 'package' else Path(path).absolute()
            if kind == 'save' and candidate.name != 'C_livery':
                raise ValueError('Choose a scanned C_livery artwork entry.')
            context = self._studio_theme_snapshot(theme)
            self._studio_package_path = str(candidate) if kind == 'package' else ''
            self._studio_garage_snapshot = snapshot
            self._studio_launching = True
            self._studio_status = 'Validating artwork for the selected Garage body...'
            self.changed.emit()
            self._start_thread(target=self._launch_garage_artwork_studio_worker,
                args=(identity, snapshot, str(candidate), kind, context, expected), name='kfps-studio-garage-artwork')
        except Exception as exc:
            self._finish_studio_launch(False, str(exc))

    def _launch_garage_artwork_studio_worker(self, identity, snapshot, path, kind, theme, expected=""):
        try:
            if self._cancel_event.is_set():
                return
            self._resolve_studio_vehicle(identity)
            if kind == 'package':
                path = _validated_livery_package(self.paths, path)
            bridge = self._garage_studio_bridge()
            request = bridge.request_for_garage_artwork(identity, snapshot, path, kind, expected=expected)
            if theme:
                request['ui_theme'] = theme
            request = bridge.validate_request(request)
            if not self._cancel_event.is_set():
                self._launch_studio_worker(request)
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    def _launch_studio_worker(self, request):
        try:
            if self.workspace_studio is not None:
                result = self.workspace_studio(request, self._cancel_event)
                if not self._closed:
                    self.studioLaunchCompleted.emit(True, result["message"])
                return
            path = _studio_module_path(self.paths.app_root, "host_bridge.py")
            spec = importlib.util.spec_from_file_location("_kfps_studio_host", path)
            bridge = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(bridge)
            result = bridge.launch_from_host(self.paths.app_root, request, open_window=True, cancelled=self._cancel_event)
            if not self._closed:
                self.studioLaunchCompleted.emit(True, result["message"])
        except Exception as exc:
            if not self._closed:
                self.studioLaunchCompleted.emit(False, str(exc))

    @Slot(bool, str)
    def _finish_studio_launch(self, ok, message):
        if self._closed:
            return
        self._studio_launching = False
        self._studio_status = message
        if self._studio_garage_snapshot is not None:
            log_body_launch(self.log, "studio", "handoff" if ok else "unavailable", self._studio_garage_snapshot)
            self._studio_garage_snapshot = None
        if getattr(self, '_studio_garage_workflow', False):
            self.log.append('Garage Studio: outcome=' + ('handoff' if ok else 'unavailable'),
                            'info' if ok else 'error', update_status=False)
            self._studio_garage_workflow = False
        else:
            self.log.append(message, "info" if ok else "error")
        self.changed.emit()

    def _poll_editor_changes(self):
        if self._closed:
            return
        output_mtime = self._marker_mtime(self._output_change_marker)
        if output_mtime and output_mtime != self._output_change_mtime:
            self._output_change_mtime = output_mtime
            self.editorOutputsChanged.emit()
        project_mtime = self._marker_mtime(self._project_change_marker)
        if project_mtime and project_mtime != self._project_change_mtime:
            self._project_change_mtime = project_mtime
            self.refresh()

    @Property(QObject, constant=True)
    def projectModel(self):
        return self._project_model

    @Property(str, notify=changed)
    def selectedPath(self):
        return self._selected

    @Property(str, notify=changed)
    def selectedName(self):
        if not self._selected:
            return "—"
        return Path(self._selected).name.removesuffix(".fabric-project.json")

    @Property(str, notify=changed)
    def selectedShapes(self):
        return self._shapes

    @Property(str, notify=changed)
    def selectedModified(self):
        return self._modified

    @Property(str, notify=changed)
    def previewUrl(self):
        return self._preview

    @Property(bool, notify=changed)
    def previewLoading(self):
        return self._preview_loading

    @Property(str, notify=changed)
    def searchText(self):
        return self._search

    @searchText.setter
    def searchText(self, value: str):
        value = str(value or "")
        if value == self._search:
            return
        self._search = value
        self._apply_filter()
        self.changed.emit()

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def lastError(self):
        return self._last_error

    @Property(bool, notify=changed)
    def launching(self):
        return self._launching

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(int, notify=changed)
    def projectCount(self):
        return len(self._all_projects)

    @Slot()
    def refresh(self):
        if self._closed:
            return
        self._scan_generation += 1
        if not self._scan_running:
            self._start_scan()

    def _start_scan(self):
        self._scan_running = True
        try:
            self._start_thread(target=self._scan_worker, args=(self._scan_generation,), name="kfps-editor-project-scan")
        except Exception as exc:
            self._scan_running = False
            self.log.append(f"Could not scan editor projects: {exc}", "warning")

    def _scan_worker(self, generation: int):
        try:
            rows = self._scan_projects()
            error = ""
        except Exception as exc:
            rows, error = [], str(exc)
        if not self._cancel_event.is_set():
            self.scanCompleted.emit(generation, rows, error)

    def _scan_projects(self):
        root = self.paths.project_root
        if self._cancel_event.is_set():
            return []
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        cache = {}
        now = time.time()
        for path in root.rglob("*.fabric-project.json"):
            if self._cancel_event.is_set():
                return []
            try:
                stat = path.stat()
            except OSError:
                continue
            age = max(0, int(now - stat.st_mtime))
            if age < 60:
                modified = "just now"
            elif age < 3600:
                modified = f"{age // 60}m ago"
            elif age < 86400:
                modified = f"{age // 3600}h ago"
            else:
                modified = f"{age // 86400}d ago"
            identity = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            previous = self._scan_cache.get(path)
            shape_count = previous[1] if previous and previous[0] == identity else self._project_shape_count(path)
            cache[path] = (identity, shape_count)
            rows.append(
                {
                    "name": path.name.removesuffix(".fabric-project.json"),
                    "path": str(path),
                    "modifiedLabel": modified,
                    "shapeLabel": (
                        f"{shape_count:,} shapes"
                        if isinstance(shape_count, int)
                        else "Shape count unavailable"
                    ),
                    "shapeCount": shape_count if isinstance(shape_count, int) else -1,
                    "mtime": stat.st_mtime,
                }
            )
        rows.sort(key=lambda row: row["mtime"], reverse=True)
        self._scan_cache = cache
        return rows

    @Slot(int, object, str)
    def _finish_scan(self, generation: int, rows: list, error: str):
        self._scan_running = False
        if self._closed:
            return
        if generation != self._scan_generation:
            self._start_scan()
            return
        if error:
            self.log.append(f"Could not scan editor projects: {error}", "warning")
            return
        self._all_projects = rows
        self._apply_filter()
        if self._selected and not any(row["path"] == self._selected for row in rows):
            self._clear_selection()
        self._status = (
            f"{len(rows):,} saved editor project{'s' if len(rows) != 1 else ''} found."
            if rows
            else "No saved projects yet. Start a blank canvas or import a JSON."
        )
        self.changed.emit()

    @Slot(int)
    def select(self, index: int):
        if self._closed:
            return
        row = self._project_model.row(index)
        if not row:
            return
        self._selected = str(row["path"])
        self._preview = ""
        self._preview_loading = True
        count = int(row.get("shapeCount", -1))
        self._shapes = f"{count:,}" if count >= 0 else "unknown"
        self._modified = str(row.get("modifiedLabel") or "—")
        self._status = f"Selected {row['name']}."
        self.changed.emit()
        self.log.append(f"Selected editor project: {self._selected}")
        self._start_thread(
            target=self._preview_worker,
            args=(self._selected,),
            name="kfps-editor-preview",
        )

    @Slot()
    def clearSelection(self):
        self._clear_selection()
        self._status = "Project selection cleared."
        self.changed.emit()

    @Slot()
    def launch(self):
        self._launch("", "new")

    @Slot()
    def activate(self):
        self._launch("", "activate")

    @Slot()
    def launchJsonBrowser(self):
        self._launch("", "json")

    @Slot()
    def launchSelected(self):
        self._launch(self._selected, "")

    @Slot()
    def resetTutorial(self):
        marker = (
            self.paths.runtime_root
            / "fabric-editor"
            / "startup-help-confirmed.json"
        )
        try:
            marker.unlink(missing_ok=True)
            self._status = "Editor tutorial reset. It will appear on the next editor launch."
            self._last_error = ""
            self.log.append("Reset the vinyl editor startup tutorial.")
        except OSError as exc:
            self._status = "Could not reset the editor tutorial."
            self._last_error = str(exc)
            self.log.append(f"Could not reset the vinyl editor tutorial: {exc}", "error")
        self.changed.emit()

    @Slot()
    def openProjects(self):
        self.paths.project_root.mkdir(parents=True, exist_ok=True)
        self.desktop.openFolder(str(self.paths.project_root))

    @Slot()
    def openEditorFolder(self):
        from tools.editor_manifest import editor_web_root
        self.desktop.openFolder(str(editor_web_root(self.paths.app_root)))

    def _project_shape_count(self, path: Path) -> int | None:
        try:
            if self._cancel_event.is_set() or path.stat().st_size > PROJECT_SCAN_MAX_BYTES:
                return None
            with path.open("r", encoding="utf-8") as stream:
                prefix = stream.read(64 * 1024)
                if len(prefix) > PROJECT_SCAN_MAX_BYTES:
                    return None
                match = re.search(
                    r'"layer_count"\s*:\s*(\d+)',
                    prefix,
                )
                if match:
                    return int(match.group(1))
                if self._cancel_event.is_set():
                    return None
                # A large read(size) allocates that size even for tiny files.
                chunks, size = [prefix], len(prefix)
                while True:
                    if self._cancel_event.is_set():
                        return None
                    chunk = stream.read(min(64 * 1024, PROJECT_SCAN_MAX_BYTES - size + 1))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > PROJECT_SCAN_MAX_BYTES:
                        return None
                    chunks.append(chunk)
                data = json.loads("".join(chunks))
            items = data.get("shapes", data.get("layers", [])) if isinstance(data, dict) else data
            return len(items) if isinstance(items, list) else None
        except (OSError, ValueError, TypeError):
            return None

    def _apply_filter(self):
        needle = self._search.strip().casefold()
        rows = self._all_projects
        if needle:
            rows = [
                row
                for row in rows
                if needle in row["name"].casefold()
                or needle in row["shapeLabel"].casefold()
            ]
        self._project_model.replace(
            [
                {
                    key: row[key]
                    for key in (
                        "name",
                        "path",
                        "modifiedLabel",
                        "shapeLabel",
                        "shapeCount",
                    )
                }
                for row in rows
            ]
        )

    def _clear_selection(self):
        self._selected = ""
        self._preview = ""
        self._preview_loading = False
        self._shapes = "—"
        self._modified = "—"

    def _preview_worker(self, path: str):
        with self._preview_lock:
            if self._cancel_event.is_set() or path != self._selected:
                return
            try:
                preview_url = str(self.preview.preview_for_json(path) or "")
            except Exception as exc:
                self.log.append(
                    f"Could not render editor project preview for {path}: {exc}",
                    "error",
                )
                preview_url = ""
        if not self._closed:
            self.previewCompleted.emit(path, preview_url)

    @Slot(str, str)
    def _finish_preview(self, path: str, preview_url: str):
        if self._closed or path != self._selected:
            return
        self._preview_loading = False
        self._preview = preview_url
        if preview_url:
            self._status = f"Preview ready for {self.selectedName}."
        else:
            self._status = (
                f"{self.selectedName} is selected, but its preview could not be rendered."
            )
        self.changed.emit()

    @Slot(str)
    def launchJson(self, path: str):
        self._launch("", "activate", json_path=path)

    def _launch(self, project: str, mode: str, *, json_path: str | None = None):
        if self._closed:
            return
        if self._launching:
            self._status = "The editor is already starting."
            self.changed.emit()
            return
        launcher = self.paths.app_root / "KFPS.UI" / "editor.py"
        if not launcher.is_file():
            self._last_error = f"Editor launcher not found: {launcher}"
            self._status = "The editor could not be started."
            self.log.append(self._last_error, "error")
            self.changed.emit()
            return

        project_id = ""
        if project:
            try:
                project_id = (
                    Path(project)
                    .resolve()
                    .relative_to(self.paths.project_root.resolve())
                    .as_posix()
                )
            except ValueError:
                self._last_error = "The selected project is outside the editor project folder."
                self._status = "The selected project cannot be opened."
                self.log.append(self._last_error, "error")
                self.changed.emit()
                return

        json_id = ""
        if json_path is not None:
            try:
                candidate = Path(json_path).resolve()
                roots = (self.paths.generated_root, self.paths.editor_json_root,
                         self.paths.exported_root, self.paths.library_root)
                if (not json_path or candidate.suffix.lower() != ".json" or not candidate.is_file()
                        or not any(candidate.is_relative_to(root.resolve()) for root in roots)):
                    raise ValueError("Choose an existing JSON from the Outputs folders.")
                json_id = candidate.relative_to(self.paths.app_root.resolve()).as_posix()
            except (OSError, ValueError) as exc:
                self._last_error = str(exc)
                self._status = "The selected JSON cannot be opened."
                self.log.append(self._last_error, "error")
                self.changed.emit()
                return

        self._launching = True
        self._last_error = ""
        self._status = "Opening the editor window..."
        self.changed.emit()
        try:
            if self.workspace_editor is not None and self.workspace_editor({"project": project_id, "mode": mode or "activate", "json": json_id}):
                return
            self._start_thread(
                target=self._launch_worker,
                args=(launcher, project_id, mode, json_id) if json_id else (launcher, project_id, mode),
                name="kfps-editor-launch",
            )
        except Exception as exc:
            self._finish_launch(False, "", str(exc))

    def _start_thread(self, *, target, args, name):
        def run():
            try:
                target(*args)
            finally:
                with self._threads_lock:
                    self._threads.discard(threading.current_thread())

        worker = threading.Thread(target=run, daemon=True, name=name)
        with self._threads_lock:
            self._threads.add(worker)
        try:
            worker.start()
        except Exception:
            with self._threads_lock:
                self._threads.discard(worker)
            raise
        return worker

    def _launch_worker(self, launcher: Path, project_id: str, mode: str, json_id: str = ""):
        try:
            if self._cancel_event.is_set():
                return
            options = {"json_id": json_id} if json_id else {}
            message = launch_editor(self.paths, project_id, mode or "activate", self._cancel_event, **options)
            if not self._closed:
                self.launchCompleted.emit(True, "", message)
        except Exception as exc:
            if not self._closed:
                self.launchCompleted.emit(False, "", str(exc))

    @Slot(bool, str, str)
    def _finish_launch(self, ok: bool, url: str, message: str):
        if self._closed:
            return
        self._launching = False
        self._running = ok
        if ok:
            self._status = "Editor opened in the workspace." if url == "workspace" else "Editor opened in its own window."
            self._last_error = ""
            self.log.append(message)
        else:
            self._status = "The editor could not be started."
            self._last_error = message
            self.log.append(f"Could not open vinyl editor: {message}", "error")
        self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_event.set()
        self._change_timer.stop()
        # The editor owns its process and storage service; closing KFPS only
        # disconnects this project-list client.
        with self._threads_lock:
            threads = list(self._threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=2.0)
        discard_queued_events(self)
