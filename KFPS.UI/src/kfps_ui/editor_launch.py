from __future__ import annotations

import os
import subprocess
from pathlib import Path
import sys

from PySide6.QtNetwork import QLocalSocket

_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_root / "KFPS.Editor/src"))
from kfps_editor.ipc import (EditorConnectionError, forward_request, instance_name,
                             read_desktop_state, validate_request, wait_until_ready)
from kfps_editor.bootstrap_log import open_desktop_log
from kfps_editor.baseline import launch_command











def editor_is_open(paths) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(instance_name(paths.app_root, paths.runtime_root / "fabric-editor"))
    connected = socket.waitForConnected(150)
    socket.abort()
    return connected






def launch_editor(paths, project: str = "", mode: str = "activate", cancelled=None, *, background=False) -> str:
    request = validate_request({"project": project, "mode": mode or "activate"})
    runtime = paths.runtime_root / "fabric-editor"
    name = instance_name(paths.app_root, runtime)
    if forward_request(name, request):
        return wait_until_ready(runtime, name, cancelled)
    if cancelled is not None and cancelled.is_set():
        return "Editor launch cancelled."
    entry = paths.app_root / "KFPS.Editor" / "editor.py"
    if not entry.is_file():
        raise FileNotFoundError(f"Editor launcher not found: {entry}")
    runtime.mkdir(parents=True, exist_ok=True)
    args = ["--from-kfps", "--runtime-root", str(runtime), "--mode", request["mode"]]
    if background:
        args.append("--background")
    if project:
        args.extend(["--project-id", project])
    args, env = launch_command(paths.app_root, entry, args, fallback=paths.python_executable)
    env["KFPS_APP_ROOT"] = str(paths.app_root)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with open_desktop_log(runtime) as stream:
        process = subprocess.Popen(args, cwd=paths.app_root, env=env, creationflags=flags, close_fds=True, stdout=stream, stderr=stream)
    # The new process receives the opening request on its command line. Only ping
    # for activation here, so startup cannot open the same document twice.
    return wait_until_ready(runtime, name, cancelled, process, connected=False)
