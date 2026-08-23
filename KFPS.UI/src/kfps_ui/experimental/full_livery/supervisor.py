from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .diagnostics import prune_sessions, recover_abandoned_sessions
from .paths import FullLiveryPaths
from .protocol import PROTOCOL_VERSION, new_request_id, write_json_atomic


_TIMEOUT_SECONDS = {
    "link-game": 600.0,
    "refresh-packages": 120.0,
    "scan-saves": 240.0,
    "open-package": 240.0,
    "preview-source": 480.0,
    "add-package": 300.0,
    "migrate-package": 300.0,
    "export-package": 480.0,
    "install-package": 300.0,
    "prepare-mesh": 600.0,
    "clear-cache": 120.0,
}


def _worker_environment(paths) -> QProcessEnvironment:
    environment = QProcessEnvironment.systemEnvironment()
    python_path = [str(paths.ui_root / "src"), str(paths.ui_root.parent)]
    existing = environment.value("PYTHONPATH")
    if existing:
        python_path.append(existing)
    environment.insert("PYTHONPATH", os.pathsep.join(python_path))
    environment.insert("PYTHONUTF8", "1")
    environment.insert("KFPS_APP_ROOT", str(paths.app_root))
    return environment


def _worker_command(paths, request: Path, result: Path) -> tuple[str, list[str]]:
    python_executable = Path(paths.python_executable)
    if python_executable.is_file() and python_executable.name.casefold().startswith(("python", "pythonw")):
        return str(python_executable), [
            str(paths.ui_root / "full_livery_process.py"), "worker",
            "--request", str(request),
            "--result", str(result),
            "--parent-pid", str(os.getpid()),
        ]
    return str(sys.executable), [
        "--full-livery-worker",
        "--full-livery-worker-request", str(request),
        "--full-livery-worker-result", str(result),
        "--full-livery-worker-parent-pid", str(os.getpid()),
    ]


def _inspector_command(paths, config: Path, ready: Path, stop: Path) -> tuple[str, list[str]]:
    python_executable = Path(paths.python_executable)
    if python_executable.is_file() and python_executable.name.casefold().startswith(("python", "pythonw")):
        return str(python_executable), [
            str(paths.ui_root / "full_livery_process.py"), "inspector",
            "--config", str(config),
            "--ready", str(ready),
            "--stop", str(stop),
            "--parent-pid", str(os.getpid()),
        ]
    return str(sys.executable), [
        "--full-livery-inspector",
        "--full-livery-inspector-config", str(config),
        "--full-livery-inspector-ready", str(ready),
        "--full-livery-inspector-stop", str(stop),
        "--full-livery-worker-parent-pid", str(os.getpid()),
    ]


def _terminate_process_tree(pid: int) -> None:
    try:
        root = psutil.Process(int(pid))
        processes = [*root.children(recursive=True), root]
    except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
        return
    for process in reversed(processes):
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    _, alive = psutil.wait_procs(processes, timeout=1.5)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass


def _resident_process_tree(pid: int) -> int:
    try:
        root = psutil.Process(int(pid))
        processes = [root, *root.children(recursive=True)]
    except (psutil.AccessDenied, psutil.NoSuchProcess, ValueError):
        return 0
    total = 0
    for process in processes:
        try:
            total += int(process.memory_info().rss)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return total


class FullLiveryTaskSupervisor(QObject):
    completed = Signal(object)
    stateChanged = Signal()

    def __init__(self, app_paths, experiment_paths: FullLiveryPaths, log, parent=None):
        super().__init__(parent)
        self.app_paths = app_paths
        self.paths = experiment_paths
        self.log = log
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        self._monitor = QTimer(self)
        self._monitor.setInterval(250)
        self._monitor.timeout.connect(self._monitor_process)
        self._closed = False
        self._request: dict[str, Any] | None = None
        self._pending: tuple[str, dict[str, Any], str, dict[str, Any]] | None = None
        self._session: Path | None = None
        self._result_file: Path | None = None
        self._cancel_file: Path | None = None
        self._started = 0.0
        self._deadline = 0.0
        self._cancel_deadline = 0.0
        self._cancel_reason = ""
        self._peak_bytes = 0
        self.paths.ensure()
        recover_abandoned_sessions(self.paths.sessions, self.paths.recovery)
        prune_sessions(self.paths.sessions)

    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    @property
    def current_operation(self) -> str:
        return str((self._request or {}).get("operation") or "")

    def start(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        kind: str | None = None,
        metadata: dict[str, Any] | None = None,
        supersede: bool = False,
    ) -> bool:
        if self._closed:
            return False
        kind = str(kind or operation)
        metadata = dict(metadata or {})
        if self.running:
            if not supersede:
                return False
            self._pending = (operation, dict(payload), kind, metadata)
            self.cancel("superseded")
            return True
        request_id = new_request_id()
        session = self.paths.sessions / f"{time.strftime('%Y%m%d-%H%M%S')}-{request_id[:10]}"
        session.mkdir(parents=True, exist_ok=False)
        request_file = session / "request.json"
        result_file = session / "result.json"
        cancel_file = session / "cancel"
        path_payload = self.paths.as_worker_payload()
        path_payload.update({
            "app_root": str(self.app_paths.app_root.resolve()),
            "inspector_root": str((self.app_paths.app_root / "tools" / "livery-inspector").resolve()),
        })
        request = {
            "protocol": PROTOCOL_VERSION,
            "request_id": request_id,
            "operation": operation,
            "kind": kind,
            "metadata": metadata,
            "paths": path_payload,
            "payload": dict(payload),
            "session_dir": str(session.resolve()),
            "cancel_file": str(cancel_file.resolve()),
        }
        write_json_atomic(request_file, request)
        program, arguments = _worker_command(self.app_paths, request_file, result_file)
        self._process.setWorkingDirectory(str(self.app_paths.ui_root))
        self._process.setProcessEnvironment(_worker_environment(self.app_paths))
        self._process.setStandardOutputFile(str(session / "stdout.log"))
        self._process.setStandardErrorFile(str(session / "stderr.log"))
        self._request = request
        self._session = session
        self._result_file = result_file
        self._cancel_file = cancel_file
        self._started = time.monotonic()
        self._deadline = self._started + _TIMEOUT_SECONDS.get(operation, 300.0)
        self._cancel_deadline = 0.0
        self._cancel_reason = ""
        self._peak_bytes = 0
        self._process.start(program, arguments)
        self._monitor.start()
        self.stateChanged.emit()
        return True

    def _on_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self._request is not None:
            self._emit_start_failure(
                self._process.errorString() or "The isolated full-livery worker did not start."
            )

    def _emit_start_failure(self, error: str) -> None:
        request = self._request or {}
        result = {
            "kind": request.get("kind") or request.get("operation") or "worker",
            "ok": False,
            "error": error,
            **dict(request.get("metadata") or {}),
        }
        self._reset()
        if not self._closed:
            self.completed.emit(result)

    def cancel(self, reason: str = "cancelled") -> None:
        if not self.running:
            return
        self._cancel_reason = str(reason)
        if self._cancel_file is not None:
            self._cancel_file.touch(exist_ok=True)
        self._cancel_deadline = time.monotonic() + (8.0 if self.current_operation == "install-package" else 3.0)

    def _monitor_process(self) -> None:
        if not self.running:
            return
        pid = int(self._process.processId() or 0)
        resident = _resident_process_tree(pid)
        self._peak_bytes = max(self._peak_bytes, resident)
        now = time.monotonic()
        if self._peak_bytes > 6 * 1024 * 1024 * 1024 and not self._cancel_deadline:
            self.cancel("memory limit exceeded")
        if now >= self._deadline and not self._cancel_deadline:
            self.cancel("time limit exceeded")
        if self._cancel_deadline and now >= self._cancel_deadline:
            _terminate_process_tree(pid)
            self._process.kill()

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        self._monitor.stop()
        if self._request is None:
            self._reset()
            return
        request = self._request or {}
        response: dict[str, Any]
        try:
            response = json.loads(self._result_file.read_text(encoding="utf-8")) if self._result_file else {}
            if not isinstance(response, dict):
                raise ValueError
        except (OSError, ValueError):
            response = {
                "ok": False,
                "error": self._cancel_reason or f"The isolated full-livery worker exited with code {exit_code}.",
                "cancelled": bool(self._cancel_reason),
            }
        result = {
            **response,
            "kind": request.get("kind") or request.get("operation") or "worker",
            "operation": request.get("operation") or response.get("operation") or "",
            "request_id": request.get("request_id") or response.get("request_id") or "",
            "peak_resident_bytes": self._peak_bytes,
            **dict(request.get("metadata") or {}),
        }
        self._reset()
        if not self._closed:
            self.completed.emit(result)
        pending = self._pending
        self._pending = None
        if pending and not self._closed:
            operation, payload, kind, metadata = pending
            self.start(operation, payload, kind=kind, metadata=metadata)

    def _reset(self) -> None:
        self._monitor.stop()
        self._request = None
        self._session = None
        self._result_file = None
        self._cancel_file = None
        self._started = self._deadline = self._cancel_deadline = 0.0
        self._cancel_reason = ""
        self._peak_bytes = 0
        self.stateChanged.emit()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pending = None
        if self.running:
            self.cancel("application shutdown")
            if not self._process.waitForFinished(5000):
                _terminate_process_tree(int(self._process.processId() or 0))
                self._process.kill()
                self._process.waitForFinished(2000)
        self._monitor.stop()
        self._reset()


class FullLiveryInspectorSupervisor(QObject):
    ready = Signal(str)
    failed = Signal(str)

    def __init__(self, app_paths, experiment_paths: FullLiveryPaths, parent=None):
        super().__init__(parent)
        self.app_paths = app_paths
        self.paths = experiment_paths
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_process_error)
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._poll_ready)
        self._session: Path | None = None
        self._ready_file: Path | None = None
        self._stop_file: Path | None = None
        self._closed = False
        self._reported_ready = False
        self._stopping = False
        self._failure_reported = False
        self._pending: dict[str, Any] | None = None
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self._force_stop)

    @property
    def running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def start(self, *, package: str, mesh: str, render_root: str, render_contract: dict[str, Any]) -> None:
        if self._closed:
            return
        request = {
            "package": package,
            "mesh": mesh,
            "render_root": render_root,
            "render_contract": render_contract,
        }
        if self.running:
            self._pending = request
            self._request_stop(clear_pending=False)
            return
        self._start_now(request)

    def _start_now(self, request: dict[str, Any]) -> None:
        package = str(request["package"])
        mesh = str(request["mesh"])
        render_root = str(request["render_root"])
        render_contract = dict(request["render_contract"])
        session = self.paths.sessions / f"viewer-{time.strftime('%Y%m%d-%H%M%S')}-{new_request_id()[:10]}"
        session.mkdir(parents=True, exist_ok=False)
        config = session / "config.json"
        ready = session / "ready.json"
        stop = session / "stop"
        write_json_atomic(config, {
            "package": str(Path(package).resolve()),
            "mesh": str(Path(mesh).resolve()),
            "render_root": str(Path(render_root).resolve()),
            "render_contract": render_contract,
            "inspector_root": str((self.app_paths.app_root / "tools" / "livery-inspector").resolve()),
        })
        program, arguments = _inspector_command(self.app_paths, config, ready, stop)
        self._process.setWorkingDirectory(str(self.app_paths.ui_root))
        self._process.setProcessEnvironment(_worker_environment(self.app_paths))
        self._process.setStandardOutputFile(str(session / "stdout.log"))
        self._process.setStandardErrorFile(str(session / "stderr.log"))
        self._session = session
        self._ready_file = ready
        self._stop_file = stop
        self._reported_ready = False
        self._stopping = False
        self._failure_reported = False
        self._process.start(program, arguments)
        self._poll.start()

    def _on_process_error(self, error) -> None:
        if (
            error == QProcess.ProcessError.FailedToStart
            and not self._closed
            and not self._failure_reported
        ):
            self._failure_reported = True
            self.failed.emit(self._process.errorString() or "The isolated 3D viewer did not start.")

    def _poll_ready(self) -> None:
        if self._reported_ready or self._ready_file is None or not self._ready_file.is_file():
            return
        try:
            value = json.loads(self._ready_file.read_text(encoding="utf-8"))
            url = str(value.get("url") or "")
            if not url:
                raise ValueError
        except (OSError, ValueError):
            return
        self._reported_ready = True
        self._poll.stop()
        self.ready.emit(url)

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        self._poll.stop()
        self._stop_timer.stop()
        if (
            not self._closed
            and not self._reported_ready
            and not self._stopping
            and not self._failure_reported
            and exit_code
        ):
            detail = "The isolated 3D viewer stopped before it was ready."
            if self._session is not None:
                error_file = self._session / "error.txt"
                if error_file.is_file():
                    detail = error_file.read_text(encoding="utf-8", errors="replace").strip() or detail
            self.failed.emit(detail)
        self._session = self._ready_file = self._stop_file = None
        self._reported_ready = False
        self._stopping = False
        self._failure_reported = False
        pending = self._pending
        self._pending = None
        if pending is not None and not self._closed:
            self._start_now(pending)

    def stop(self) -> None:
        self._request_stop(clear_pending=True)

    def _request_stop(self, *, clear_pending: bool) -> None:
        self._poll.stop()
        if clear_pending:
            self._pending = None
        if self.running:
            self._stopping = True
            if self._stop_file is not None:
                self._stop_file.touch(exist_ok=True)
            self._stop_timer.start(1500)
            return
        self._session = self._ready_file = self._stop_file = None
        self._reported_ready = False

    def _force_stop(self) -> None:
        if not self.running:
            return
        _terminate_process_tree(int(self._process.processId() or 0))
        self._process.kill()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pending = None
        self._poll.stop()
        self._stop_timer.stop()
        self._force_stop()
