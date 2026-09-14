"""Windows EXE/managed CLI/main-app startup qualification in disposable profiles.

Run with an unused output directory underneath runtime/test-runs. Focus tests
briefly show a helper window; all other cases explicitly stay in the background.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
from kfps_editor.activation import grant_foreground
from kfps_editor.ipc import instance_name, read_desktop_state


def main():
    from PySide6.QtWidgets import QApplication, QPushButton
    import psutil
    from kfps_ui.editor_launch import launch_editor

    out = Path(sys.argv[1]).resolve()
    if not out.is_relative_to(ROOT / "runtime/test-runs") or out.exists():
        raise ValueError("Use a new output directory under this checkout's runtime/test-runs")
    out.mkdir(parents=True)
    runtime = out / "profile/runtime/fabric-editor"
    runtime.mkdir(parents=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    children, owners, results, renderer_children = [], set(), [], []
    helper = QPushButton("Begin isolated startup focus tests")
    helper.setWindowTitle("KFPS startup qualification controller")
    helper.resize(350, 70)
    started = []
    helper.clicked.connect(lambda: started.append(True))

    def wait(predicate, timeout=75):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            app.processEvents()
            value = predicate()
            if value:
                return value
            time.sleep(.04)
        raise TimeoutError("Native startup qualification condition timed out")

    def record(case, **fields):
        results.append(dict(case=case, passed=True, **fields))
        (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results[-1]), flush=True)

    def pid_of(hwnd):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def window(pid):
        matches = []
        @callback_type
        def visit(hwnd, _):
            if pid_of(hwnd) == pid and user.IsWindowVisible(hwnd):
                matches.append(hwnd)
            return True
        user.EnumWindows(visit, 0)
        return matches[0] if matches else None

    def take_focus():
        helper.show()
        helper.raise_()
        helper.activateWindow()
        user.SetForegroundWindow(int(helper.winId()))
        print("Waiting for test controller foreground", flush=True)
        wait(lambda: pid_of(user.GetForegroundWindow()) == os.getpid(), 120)

    def launch(*extra, exe=False, background=True):
        args = ["--runtime-root", str(runtime), "--from-kfps", *extra]
        if background:
            args.append("--background")
        command = [str(ROOT / "KFPS Editor.exe")] if exe else [sys.executable, "-B", str(ROOT / "KFPS.Editor/editor.py")]
        with (out / f"child-{len(children)}.log").open("wb") as stream:
            child = subprocess.Popen(command + args, cwd=ROOT, stdout=stream, stderr=stream,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        children.append(child)
        if not background:
            grant_foreground(child.pid)
        return child

    def ready():
        def check():
            state = read_desktop_state(runtime, instance_name(ROOT, runtime))
            if state.get("state") == "failed":
                raise AssertionError(state.get("error"))
            return state if state.get("state") == "ready" and window(state["pid"]) else None
        state = wait(check)
        owners.add(state["pid"])
        return state["pid"]

    def close(pid):
        handle = window(pid)
        assert handle, "No editor window to close"
        user.PostMessageW(handle, 0x0010, 0, 0)
        wait(lambda: not psutil.pid_exists(pid), 20)
        wait(lambda: all(child.poll() is not None for child in children), 10)
        assert not (runtime / "desktop.json").exists(), "Owned state was not cleaned up"

    paths = SimpleNamespace(app_root=ROOT, runtime_root=runtime.parent,
                            python_executable=Path(sys.executable))
    try:
        helper.show()
        print("Click Begin in the isolated test controller; this establishes a real input owner.", flush=True)
        wait(lambda: started, 180)
        # Let the external click/inspection complete before checking foreground.
        until = time.monotonic() + 3
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.02)
        projects = runtime / "projects"
        projects.mkdir()
        project = projects / "Startup verification.fabric-project.json"
        project.write_text(json.dumps({
            "format": "kloudy_fabric_editor_project_v1", "name": "Startup verification",
            "shapes": [{"type": 1048677, "type_word": 101, "resource_family": "Primitives",
                        "resource_index": 1, "source_format": "fh6_typecode", "color": [80, 180, 210, 255],
                        "data": [(i % 20) * 60 - 600, (i // 20) * 60 - 300, .12, .12, i % 360, 0, 0],
                        "editor_id": f"startup-{i}"} for i in range(200)]}), encoding="utf-8")
        expected_project = project.read_bytes()
        # Legacy foreign-host/PID metadata must not prevent a new owner.
        (runtime / "desktop.lock").write_text("4294967294\npython\nOTHER_MACHINE\n\n\n")
        (runtime / "desktop.json").write_text(json.dumps({"pid": 4294967294, "state": "ready",
            "instance": instance_name(ROOT, runtime)}))
        take_focus()
        start = time.monotonic()
        cold = launch("--project-id", project.name, exe=True)
        pid = ready()
        assert pid_of(user.GetForegroundWindow()) != pid, "Background launch stole focus"
        assert project.read_bytes() == expected_project
        record("exe-stale-marker-background-start", seconds=round(time.monotonic() - start, 3), pid=pid)

        take_focus()
        assert launch_editor(paths)
        wait(lambda: pid_of(user.GetForegroundWindow()) == pid, 5)
        record("main-app-existing-window-foreground")
        user.ShowWindow(window(pid), 6)
        wait(lambda: user.IsIconic(window(pid)), 5)
        take_focus()
        client = launch(exe=True, background=False)
        wait(lambda: client.poll() is not None)
        assert client.returncode == 0
        wait(lambda: pid_of(user.GetForegroundWindow()) == pid and not user.IsIconic(window(pid)), 5)
        record("exe-restores-minimized-window-to-foreground")
        app.primaryScreen().grabWindow(window(pid)).save(str(out / "foreground-editor.png"))
        take_focus()
        clients = [launch() for _ in range(4)]
        wait(lambda: all(child.poll() is not None for child in clients))
        assert all(child.returncode == 0 for child in clients)
        assert ready() == pid and pid_of(user.GetForegroundWindow()) != pid
        record("four-managed-cli-activations-one-owner-background")
        close(pid)
        assert cold.returncode == 0
        assert project.read_bytes() == expected_project
        record("normal-close-cleans-state-preserves-project")

        take_focus()
        start = time.monotonic()
        assert launch_editor(paths, project=project.name)
        pid = ready()
        wait(lambda: pid_of(user.GetForegroundWindow()) == pid, 5)
        record("main-app-cold-start-project-foreground", seconds=round(time.monotonic() - start, 3))
        # Kill only the owner: renderer exit must happen naturally, as in a crash.
        process = psutil.Process(pid)
        descendants = process.children(recursive=True)
        renderer_children.extend(descendants)
        process.kill()
        process.wait(10)
        _, alive = psutil.wait_procs(descendants, timeout=10)
        assert not alive, f"Renderer processes survived host crash: {[child.pid for child in alive]}"
        wait(lambda: not read_desktop_state(runtime, instance_name(ROOT, runtime)), 5)
        assert (runtime / "desktop.lock").exists()
        record("crashed-owner-state-ignored-lock-released", rendererChildrenExited=len(descendants))

        take_focus()
        start = time.monotonic()
        launch("--project-id", project.name, exe=True, background=False)
        pid = ready()
        wait(lambda: pid_of(user.GetForegroundWindow()) == pid, 5)
        assert project.read_bytes() == expected_project
        record("exe-restarts-after-crash-with-project", seconds=round(time.monotonic() - start, 3))
        close(pid)

        # Read-only lock must produce a bounded, actionable failure, not 'busy'.
        lock = runtime / "desktop.lock"
        os.chmod(lock, 0o444)
        try:
            failed = launch()
            wait(lambda: failed.poll() is not None, 30)
            assert failed.returncode == 1
            error = json.loads((runtime / "desktop-startup-error.json").read_text(encoding="utf-8"))
            assert "cannot write its startup lock" in error["error"], error
            from kfps_editor.update_guard import acquire_update_guard, updater_state_root
            lease = acquire_update_guard(updater_state_root(ROOT))
            lease.Close()
            record("permission-failure-releases-updater-lease")
        finally:
            os.chmod(lock, 0o666)
        take_focus()
        launch(exe=True)
        pid = ready()
        close(pid)
        assert project.read_bytes() == expected_project
        record("retry-after-access-restored-project-unchanged")
        take_focus()
        start = time.monotonic()
        concurrent = [launch() for _ in range(4)]
        pid = ready()
        wait(lambda: sum(child.poll() == 0 for child in concurrent) == 3)
        assert sum(child.poll() is None for child in concurrent) == 1
        assert ready() == pid
        record("four-concurrent-cold-launches-one-owner", seconds=round(time.monotonic() - start, 3))
        close(pid)
        assert all(child.returncode == 0 for child in concurrent)
    finally:
        helper.close()
        # Leave no test editors behind on an assertion failure.
        for pid in owners:
            try:
                process = psutil.Process(pid)
                if str(runtime) not in process.cmdline():
                    continue
                descendants = process.children(recursive=True)
                process.kill()
                for child in descendants:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
        for child in renderer_children:
            try:
                if child.is_running():
                    child.kill()
            except psutil.NoSuchProcess:
                pass
        app.processEvents()


if __name__ == "__main__":
    main()
