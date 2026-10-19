"""Native Studio process boundary; no Qt imports or UI work in the calling host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from urllib.parse import urlsplit
import psutil

LAB = Path(__file__).resolve().parents[2]
WINDOWS = LAB / "runs/studio-windows"


def validate_window_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
            or parsed.username or parsed.password or parsed.query
            or not re.fullmatch(r"/[A-Za-z0-9_-]{43}/", parsed.path)
            or (parsed.fragment and not re.fullmatch(r"vinyl=[a-f0-9]{32}", parsed.fragment))):
        raise ValueError("Invalid local Studio window URL.")
    return url


def use_chrome(root):
    try:
        with (Path(root) / "runtime/qml-shell-settings.json").open("rb") as source:
            body = source.read(1024 * 1024 + 1)
        value = json.loads(body) if len(body) <= 1024 * 1024 else None
        return isinstance(value, dict) and value.get("liveryUseChrome") is True
    except (OSError, ValueError):
        return False


def native_preflight(config):
    root = Path(config["kfpsRoot"]).resolve()
    python = Path(config["pythonExe"]).resolve()
    if not python.is_file() or not python.is_relative_to(root / "python"):
        raise ValueError("Livery Studio needs the KFPS bundled Python runtime.")
    required = (root / "KFPS.Editor/src/kfps_editor/graphics.py",
                root / "KFPS.Editor/src/kfps_editor/baseline.py",
                python.parent / "Lib/site-packages/PySide6/QtWebEngineWidgets.pyd")
    if not all(path.is_file() for path in required):
        raise ValueError("The native Studio runtime is incomplete. Repair KFPS or explicitly choose Chrome in Settings.")


def isolated_environment(directory):
    environment = dict(os.environ)
    for key in list(environment):
        if key.upper().startswith(("PYTHON", "QT_", "QTWEBENGINE", "QML", "PYSIDE", "SHIBOKEN", "QSG_")):
            environment.pop(key)
    environment.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    for name in ("temp", "cache", "appdata", "localappdata"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    environment.update(TEMP=str(directory / "temp"), TMP=str(directory / "temp"),
                       TMPDIR=str(directory / "temp"), APPDATA=str(directory / "appdata"),
                       LOCALAPPDATA=str(directory / "localappdata"), XDG_CACHE_HOME=str(directory / "cache"))
    return environment


def open_native(url, config, *, timeout=60, test_options=None, cancelled=None):
    """Wait for actual page readiness; test options are Python-only, never an HTTP input."""
    validate_window_url(url)
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError("Studio window launch was cancelled.")
    native_preflight(config)
    directory = (WINDOWS / uuid.uuid4().hex).resolve()
    if not directory.is_relative_to((LAB / "runs").resolve()):
        raise ValueError("Native window output must be under livery/runs.")
    directory.mkdir(parents=True)
    environment = isolated_environment(directory)
    args = [str(config["pythonExe"]), "-I", "-B", str(Path(__file__).with_name("native_host.py")),
            "--root", str(config["kfpsRoot"]), "--url", url, "--run", str(directory)]
    if test_options:
        args.append("--offscreen")
        environment["QT_QPA_PLATFORM"] = "windows" if test_options.get("hidden_windows") else "offscreen"
        if test_options.get("software"):
            environment["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
        if test_options.get("debug_port"):
            environment["QTWEBENGINE_REMOTE_DEBUGGING"] = f"127.0.0.1:{int(test_options['debug_port'])}"
        if test_options.get("auto_close"):
            args += ["--auto-close", str(float(test_options["auto_close"]))]
        if test_options.get("control"):
            args.append("--test-control")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with (directory / "stdout.log").open("wb") as out, (directory / "stderr.log").open("wb") as err:
        child = subprocess.Popen(args, cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, close_fds=True, **options)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Studio window launch was cancelled.")
            status = directory / "host.json"
            if status.exists():
                value = json.loads(status.read_text(encoding="utf-8"))
                if value.get("status") == "ready" and child.poll() is None:
                    return {"pid": child.pid, "run": str(directory), "mode": "native"}
                if value.get("status") == "failed":
                    raise RuntimeError(value.get("error", "Native Studio failed to load."))
            if child.poll() is not None:
                raise RuntimeError("Native Studio stopped during startup.")
            time.sleep(.1)
        raise TimeoutError("Native Studio did not become ready in time.")
    except BaseException as exc:
        # This is only the just-created window, never the shared backend.
        if child.poll() is None:
            try:
                descendants = psutil.Process(child.pid).children(recursive=True)
            except psutil.Error:
                descendants = []
            child.terminate()
            child.wait(timeout=5)
            for process in reversed(descendants):
                try: process.terminate()
                except psutil.Error: pass
            _, alive = psutil.wait_procs(descendants, timeout=3)
            for process in alive:
                try: process.kill()
                except psutil.Error: pass
            psutil.wait_procs(alive, timeout=2)
        raise RuntimeError(f"{exc} See {directory / 'stderr.log'}. Chrome was not opened.") from exc
