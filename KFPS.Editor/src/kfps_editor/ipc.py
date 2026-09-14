"""Editor-owned instance protocol and readiness; no main-application imports."""
from __future__ import annotations
import hashlib
import json
import os
import re
import time
from pathlib import Path, PurePosixPath
from .activation import grant_pipe_foreground, process_running

STARTUP_TIMEOUT = 65

class EditorConnectionError(RuntimeError):
    """A live instance must not be replaced or replayed after an uncertain ACK."""

def instance_name(app_root: Path, runtime: Path) -> str:
    identity = f"{app_root.resolve()}\0{runtime.resolve()}"
    if os.name == "nt":
        identity = identity.casefold()
    return "kfps-editor-" + hashlib.sha256(identity.encode()).hexdigest()[:32]

def validate_request(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"project", "mode", "background"}:
        raise ValueError("Invalid editor launch request.")
    project = payload.get("project", "")
    mode = payload.get("mode", "activate")
    if not isinstance(project, str) or len(project) > 2048 or "\\" in project or ":" in project:
        raise ValueError("Invalid editor project path.")
    path = PurePosixPath(project)
    if project and (path.is_absolute() or ".." in path.parts or "\x00" in project or not project.endswith(".fabric-project.json")):
        raise ValueError("The requested project must be inside the editor project folder.")
    if not isinstance(mode, str) or mode not in {"activate", "new", "json", "tutorial"}:
        raise ValueError("Invalid editor launch mode.")
    if "background" in payload and type(payload["background"]) is not bool:
        raise ValueError("Invalid editor activation request.")
    request = {"project": project, "mode": mode}
    if payload.get("background"):
        request["background"] = True
    return request

def _local_socket():
    from PySide6.QtNetwork import QLocalSocket
    return QLocalSocket()


def _accepted_reply(result: bytes) -> bool:
    if len(result) > 64:
        raise EditorConnectionError("The open editor returned an invalid response. Close it normally and try again.")
    if b"\n" not in result:
        return False
    if result.strip() != b"ok":
        raise EditorConnectionError("The editor is busy starting, opening a document, or closing. Finish the current operation and try again.")
    return True


def forward_before_qt(name: str, request: dict, timeout: int = 800) -> bool:
    """Use the existing Qt named pipe without importing potentially updating DLLs."""
    if os.name != "nt" or not re.fullmatch(r"kfps-editor-[a-f0-9]{32}", name):
        raise ValueError("Invalid local editor pipe.")
    # _winapi is built into the pinned CPython, not an external extension. Its
    # overlapped operations provide bounded waits and cancellation before Qt loads.
    import _winapi
    payload = json.dumps(validate_request(request)).encode() + b"\n"
    deadline = time.monotonic() + max(1, timeout) / 1000
    try:
        handle = _winapi.CreateFile("\\\\.\\pipe\\" + name, _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
                                    0, 0, _winapi.OPEN_EXISTING, _winapi.FILE_FLAG_OVERLAPPED, 0)
    except OSError as error:
        if error.winerror in (2, 231):
            return False
        raise EditorConnectionError("The open editor could not be contacted. Close it normally and try again.") from error

    def finish(operation):
        try:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if _winapi.WaitForSingleObject(operation.event, remaining) != _winapi.WAIT_OBJECT_0:
                raise EditorConnectionError("The open editor has not responded yet. Give it a moment and try again; no second editor was started.")
            count, error = operation.GetOverlappedResult(False)
            if error:
                raise OSError(error, "Editor pipe operation failed")
            return count
        finally:
            operation.cancel()
            operation.GetOverlappedResult(True)

    try:
        if not request.get("background"):
            grant_pipe_foreground(handle)
        operation, _ = _winapi.WriteFile(handle, payload, overlapped=True)
        if finish(operation) != len(payload):
            raise EditorConnectionError("The open editor received an incomplete request. No second editor was started.")
        result = bytearray()
        while time.monotonic() < deadline:
            operation, _ = _winapi.ReadFile(handle, 65 - len(result), overlapped=True)
            count = finish(operation)
            if not count:
                raise EditorConnectionError("The open editor disconnected before confirming the request. No second editor was started.")
            result.extend(operation.getbuffer())
            if _accepted_reply(bytes(result)):
                return True
        raise EditorConnectionError("The open editor has not responded yet. Give it a moment and try again; no second editor was started.")
    except OSError as error:
        raise EditorConnectionError("The open editor disconnected before confirming the request. No second editor was started.") from error
    finally:
        _winapi.CloseHandle(handle)


def forward_request(name: str, request: dict, timeout: int = 800) -> bool:
    payload = json.dumps(validate_request(request)).encode() + b"\n"
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        socket = _local_socket()
        socket.connectToServer(name)
        if socket.waitForConnected(min(250, timeout)):
            if not request.get("background"):
                grant_pipe_foreground(socket.socketDescriptor())
            socket.write(payload)
            socket.flush()
            result = bytearray()
            while time.monotonic() < deadline:
                if socket.bytesAvailable() or socket.waitForReadyRead(200):
                    result.extend(bytes(socket.readAll()))
                    try:
                        accepted = _accepted_reply(bytes(result))
                    except EditorConnectionError:
                        socket.abort()
                        raise
                    if accepted:
                        socket.disconnectFromServer()
                        return True
            socket.abort()
            raise EditorConnectionError("The open editor has not responded yet. Give it a moment and try again; no second editor was started.")
        socket.abort()
        if timeout <= 800:
            return False
        time.sleep(0.1)
    return False

def read_desktop_state(runtime: Path, name: str) -> dict:
    try:
        marker = runtime / "desktop.json"
        if marker.stat().st_size > 16384:
            return {}
        state = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("instance") != name:
            return {}
        if process_running(state.get("pid")) is False:
            return {}
        return state
    except (OSError, ValueError):
        return {}

def wait_until_ready(runtime: Path, name: str, cancelled=None, process=None, connected=True, *, background=False) -> str:
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if cancelled is not None and cancelled.is_set():
            return "Editor continues independently."
        if process is not None and process.poll() not in (None, 0):
            detail = ""
            try:
                report = json.loads((runtime / "desktop-startup-error.json").read_text(encoding="utf-8"))
                if report.get("pid") == process.pid:
                    detail = str(report.get("error", ""))[:2000]
            except (OSError, ValueError, AttributeError):
                pass
            raise RuntimeError(f"The editor could not start. {detail}\nSee {runtime / 'desktop.log'}")
        if not connected:
            try:
                request = {"mode": "activate", "project": ""}
                if background:
                    request["background"] = True
                connected = forward_request(name, request, timeout=300)
            except EditorConnectionError:
                # Activation is idempotent; never replay the opening request.
                pass
        if connected:
            state = read_desktop_state(runtime, name)
            if state.get("state") == "failed":
                raise RuntimeError(f"{state.get('error') or 'The editor could not finish starting.'}\nSee {runtime / 'desktop.log'}")
            if state.get("state") == "ready":
                return "Editor opened in its own window."
        time.sleep(0.12)
    raise RuntimeError(f"The editor is taking too long to become ready. Check its window and try Reopen Editor. Saved projects and recovery files are unchanged.\nSee {runtime / 'desktop.log'}")
