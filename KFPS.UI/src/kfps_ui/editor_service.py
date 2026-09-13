from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .log_service import LogService
from .lifecycle import discard_queued_events
from .models import DictListModel
from .preview_service import PreviewService
from .editor_launch import launch_editor


class EditorService(QObject):
    changed = Signal()
    editorOutputsChanged = Signal()
    launchCompleted = Signal(bool, str, str)
    previewCompleted = Signal(str, str)
    scanCompleted = Signal(int, object, str)

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
        self.refresh()

    @staticmethod
    def _marker_mtime(path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

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
            if self._cancel_event.is_set() or path.stat().st_size > 150 * 1024 * 1024:
                return None
            with path.open("r", encoding="utf-8") as stream:
                prefix = stream.read(64 * 1024)
                match = re.search(
                    r'"layer_count"\s*:\s*(\d+)',
                    prefix,
                )
                if match:
                    return int(match.group(1))
                if self._cancel_event.is_set():
                    return None
                remainder = stream.read(150 * 1024 * 1024 + 1)
                if len(remainder) + len(prefix) > 150 * 1024 * 1024:
                    return None
                data = json.loads(prefix + remainder)
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

    def _launch(self, project: str, mode: str):
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

        self._launching = True
        self._last_error = ""
        self._status = "Opening the editor window..."
        self.changed.emit()
        try:
            self._start_thread(
                target=self._launch_worker,
                args=(launcher, project_id, mode),
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

    def _launch_worker(self, launcher: Path, project_id: str, mode: str):
        try:
            if self._cancel_event.is_set():
                return
            message = launch_editor(self.paths, project_id, mode or "activate", self._cancel_event)
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
            self._status = "Editor opened in its own window."
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
