from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .log_service import LogService
from .lifecycle import discard_queued_events
from .models import DictListModel
from .preview_service import PreviewService


class EditorService(QObject):
    changed = Signal()
    editorOutputsChanged = Signal()
    launchCompleted = Signal(bool, str, str)
    previewCompleted = Signal(str, str)

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
        self._server_process: subprocess.Popen | None = None
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
        root = self.paths.project_root
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        now = time.time()
        for path in root.rglob("*.fabric-project.json"):
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
            shape_count = self._project_shape_count(path)
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
        self._all_projects = rows
        self._apply_filter()
        if self._selected and not Path(self._selected).is_file():
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
        self._launch("", "")

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
        self.desktop.openFolder(str(self.paths.app_root / "tools" / "fabric-editor"))

    def _project_shape_count(self, path: Path) -> int | None:
        try:
            with path.open("r", encoding="utf-8") as stream:
                prefix = stream.read(64 * 1024)
                match = re.search(
                    r'"layer_count"\s*:\s*(\d+)',
                    prefix,
                )
                if match:
                    return int(match.group(1))
                data = json.loads(prefix + stream.read())
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
        launcher = self.paths.app_root / "tools" / "fabric-editor" / "start_fabric_editor.py"
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
        self._status = "Connecting to the local editor..."
        self.changed.emit()
        self._start_thread(
            target=self._launch_worker,
            args=(launcher, project_id, mode),
            name="kfps-editor-launch",
        )

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
        worker.start()
        return worker

    def _launch_worker(self, launcher: Path, project_id: str, mode: str):
        try:
            if self._cancel_event.is_set():
                return
            base_url = self._active_server_url()
            started = False
            if not base_url:
                started = True
                log_path = self.paths.runtime_root / "fabric-editor" / "server.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as stream:
                    flags = (
                        subprocess.CREATE_NO_WINDOW
                        if hasattr(subprocess, "CREATE_NO_WINDOW")
                        else 0
                    )
                    self._server_process = subprocess.Popen(
                        [
                            self.paths.python_executable,
                            str(launcher),
                            "--no-browser",
                        ],
                        cwd=self.paths.app_root,
                        creationflags=flags,
                        stdout=stream,
                        stderr=stream,
                    )
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline and not self._cancel_event.is_set():
                    time.sleep(0.12)
                    base_url = self._active_server_url()
                    if base_url:
                        break
                if not base_url:
                    if self._cancel_event.is_set():
                        return
                    raise RuntimeError(
                        f"The local editor service did not respond. See {log_path}"
                    )

            query = ""
            if project_id:
                query = f"?project={quote(project_id, safe='')}"
            elif mode == "json":
                query = "?browse=json"
            document_url, separator, fragment = base_url.partition("#")
            launch_url = f"{document_url}{query}"
            if separator:
                launch_url += f"#{fragment}"
            message = (
                "Editor service started."
                if started
                else "Connected to the existing editor service."
            )
            if not self._closed:
                self.launchCompleted.emit(True, launch_url, message)
        except Exception as exc:
            if not self._closed:
                self.launchCompleted.emit(False, "", str(exc))

    def _active_server_url(self) -> str:
        marker = self.paths.runtime_root / "fabric-editor" / "server.json"
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            if str(payload.get("service") or "") != "kfps-fabric-editor":
                return ""
            if Path(str(payload.get("root") or "")).resolve() != self.paths.app_root.resolve():
                return ""
            port = int(payload.get("port") or 0)
            if not 0 < port < 65536:
                return ""
            session_token = str(payload.get("session_token") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", session_token):
                return ""
            health_url = f"http://127.0.0.1:{port}/api/fabric-editor/health"
            with urllib.request.urlopen(health_url, timeout=0.65) as response:
                health = json.loads(response.read().decode("utf-8"))
            if not health.get("ok") or Path(str(health.get("root") or "")).resolve() != self.paths.app_root.resolve():
                return ""
            return (
                f"http://127.0.0.1:{port}/tools/fabric-editor/index.html"
                f"#session={quote(session_token, safe='')}"
            )
        except (OSError, ValueError, TypeError, urllib.error.URLError, json.JSONDecodeError):
            return ""

    @Slot(bool, str, str)
    def _finish_launch(self, ok: bool, url: str, message: str):
        if self._closed:
            return
        self._launching = False
        self._running = ok
        if ok:
            opened = QDesktopServices.openUrl(QUrl(url))
            if opened:
                self._status = "Editor opened in your browser."
                self._last_error = ""
                self.log.append(message)
            else:
                self._running = False
                self._status = "The editor is running, but Windows could not open the browser."
                self._last_error = f"Open this address manually: {url}"
                self.log.append(self._last_error, "error")
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
        process = self._server_process
        self._server_process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1.5)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=1.5)
                except Exception:
                    pass
        with self._threads_lock:
            threads = list(self._threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=2.0)
        discard_queued_events(self)
