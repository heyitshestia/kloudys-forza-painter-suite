"""Actual compiled launcher -> standalone CLI -> Qt -> page -> native close."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import psutil

parser = argparse.ArgumentParser()
parser.add_argument("stage", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("script", type=Path)
parser.add_argument("--profile", type=Path)
parser.add_argument("--kfps-bridge", action="store_true")
parser.add_argument("--reactivate", action="store_true", help="Verify a second compiled launch reaches the same live editor")
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
stage, out = args.stage.resolve(), args.output.resolve()
if args.kfps_bridge and args.profile:
    parser.error("Cold bridge qualification uses a new isolated runtime")
profile = args.profile.resolve() if args.profile else out / ("runtime/fabric-editor" if args.kfps_bridge else "profile")
for path in (stage, out, profile):
    if not path.is_relative_to(root / "runtime/test-runs"):
        raise ValueError("Native EXE qualification must remain inside test-runs")
out.mkdir(parents=True, exist_ok=False)
profile.mkdir(parents=True, exist_ok=True)
if not args.profile:
    (profile / "desktop.log").write_bytes(b"synthetic previous startup\n" * 100000)
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
env = dict(os.environ, KFPS_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
    QTWEBENGINE_REMOTE_DEBUGGING=str(port), QTWEBENGINE_CHROMIUM_FLAGS="--remote-allow-origins=*",
    KFPS_TEST_APP_ROOT=str(stage), LOCALAPPDATA=str(out / "system-data"))
log = (out / "launcher.log").open("w", encoding="utf-8")
if args.kfps_bridge:
    from types import SimpleNamespace
    from unittest.mock import patch
    from PySide6.QtCore import QCoreApplication
    application = QCoreApplication([])
    sys.path.insert(0, str(root / "KFPS.UI/src"))
    from kfps_ui import editor_launch
    spawned = []
    original_spawn = subprocess.Popen
    def spawn(*values, **options):
        if (stage / "KFPS.Editor/baseline.json").is_file():
            values = ([*values[0], "--test-debug-port", str(port)], *values[1:])
        process = original_spawn(*values, **options)
        spawned.append(process)
        return process
    try:
        with patch.dict(os.environ, env), patch.object(editor_launch.subprocess, "Popen", side_effect=spawn):
            message = editor_launch.launch_editor(SimpleNamespace(app_root=stage, runtime_root=profile.parent,
                python_executable=sys.executable), background=True)
    except BaseException:
        for process in spawned:
            process.terminate()
            process.wait(timeout=5)
        log.close()
        raise
    assert len(spawned) == 1 and message, "KFPS bridge did not cold-start exactly one editor"
    child = spawned[0]
else:
    command = [str(stage / "KFPS Editor.exe"), "--background", "--runtime-root", str(profile)]
    if (stage / "KFPS.Editor/baseline.json").is_file():
        command.extend(["--test-debug-port", str(port)])
    child = subprocess.Popen(command,
        cwd=out, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
owned = None
try:
    until = time.monotonic() + 70
    marker = profile / "desktop.json"
    while time.monotonic() < until:
        if child.poll() is not None:
            raise RuntimeError("Compiled launcher exited before editor readiness")
        try:
            state = json.loads(marker.read_text(encoding="utf-8"))
            if state.get("state") == "ready" and Path(state["root"]).resolve() == stage:
                candidate = psutil.Process(state["pid"])
                command = candidate.cmdline()
                if str(profile) in command and str(stage / "KFPS.Editor/editor.py") in command:
                    owned = candidate
                    break
        except (OSError, ValueError, psutil.Error):
            pass
        time.sleep(.05)
    assert owned is not None, "Standalone editor did not become ready"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    assert pid.value != owned.pid, "Background launch took foreground focus"
    (out / "process.json").write_text(json.dumps({"launcherPid": child.pid, "editorPid": owned.pid,
        "root": str(stage), "profile": str(profile), "background": True, "foregroundTaken": False}, indent=2), encoding="utf-8")
    with (out / "runner.log").open("w", encoding="utf-8") as runner_log:
        completed = subprocess.run([shutil.which("node"), str(Path(__file__).with_name("run-native-page.cjs")),
            str(port), str(out), str(args.script.resolve())], cwd=out, env=env, stdout=runner_log,
            stderr=subprocess.STDOUT, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
    assert completed.returncode == 0, (out / "runner.log").read_text(encoding="utf-8")
    if args.reactivate:
        activation = [str(stage / "KFPS Editor.exe"), "--background", "--runtime-root", str(profile), "--from-kfps"]
        reopened = subprocess.run(activation, cwd=out, env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        assert reopened.returncode == 0, reopened.stderr.decode(errors="replace")
        state_after = json.loads(marker.read_text(encoding="utf-8"))
        assert state_after["pid"] == owned.pid and state_after["state"] == "ready", "Activation replaced the live editor"
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == owned.pid and user32.IsWindowVisible(hwnd) and not user32.GetParent(hwnd):
            windows.append(hwnd)
        return True
    user32.EnumWindows(callback_type(collect), 0)
    assert len(windows) == 1, f"Expected only the test editor window, found {len(windows)}"
    # Address only the PID and executable path verified above. Never foreground,
    # enumerate for actions on, or close a user's editor or another application.
    assert user32.PostMessageW(windows[0], 0x0010, 0, 0), "WM_CLOSE failed"
    child.wait(timeout=25)
    assert child.returncode == 0, child.returncode
    assert not owned.is_running(), "Native CLI did not complete its close handshake"
    if not args.profile:
        assert (profile / "desktop.log.1").stat().st_size <= 2 * 1024 * 1024
    result = {"compiledLauncher": not args.kfps_bridge, "kfpsColdLaunch": args.kfps_bridge,
              "compiledSingletonReactivation": args.reactivate,
              "independentHost": True, "background": True,
              "pageWorkflow": True, "cleanNativeClose": True, "startupLogRetention": True}
    (out / "native-exit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
finally:
    if child.poll() is None:
        try:
            descendants = psutil.Process(child.pid).children(recursive=True)
        except psutil.Error:
            descendants = []
        for process in reversed(descendants):
            try:
                process.terminate()
            except psutil.Error:
                pass
        psutil.wait_procs(descendants, timeout=5)
        child.terminate()
        child.wait(timeout=5)
    log.close()
