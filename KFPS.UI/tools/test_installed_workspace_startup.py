"""Opt-in installed startup check: real baseline, unified shell, isolated user data."""
from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_case(output, case):
    profile = output / "profile"
    profile.mkdir(exist_ok=True)
    for name in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        directory = profile / name.lower()
        directory.mkdir(exist_ok=True)
        os.environ[name] = str(directory)
    os.environ.update(QT_QPA_PLATFORM="offscreen", KFPS_ACTIVITY_DISABLED="1",
                      KFPS_STARTUP_MUTED="1", QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu")
    sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT / "KFPS.UI/src"),
                    str(ROOT / "KFPS.UI"), str(ROOT)]
    from kfps_ui import workspace_paths

    workspace = load("installed_workspace", ROOT / "KFPS.UI/workspace.py")
    directory = profile / "app/runtime/workspace"
    # Isolate ownership and user files, not the installed-code verification.
    with patch.object(workspace_paths, "workspace_connection_dir", return_value=directory):
        runtime = workspace.WorkspaceRuntime()
        try:
            assert runtime.baseline["status"] == "verified", runtime.baseline
            os.environ.update(QT_QUICK_BACKEND="software", KFPS_QML_GRAPHICS="software")
            module = load("installed_app", ROOT / "KFPS.UI/app.py")
            paths = replace(module.AppPaths.discover(), app_root=profile / "app",
                            runtime_root=profile / "app/runtime")
            paths.runtime_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "VERSION", paths.app_root / "VERSION")
            if case == 2:
                settings = json.loads(paths.settings_file.read_text(encoding="utf-8")) if paths.settings_file.exists() else {}
                settings.update(supportUpscalerNoticeAcknowledged=True,
                                communityJoinNoticeAcknowledged=True,
                                backgroundRemoverNoticeAcknowledged=True,
                                dcinsideKoreanNotice202609Acknowledged=True)
                paths.settings_file.write_text(json.dumps(settings), encoding="utf-8")
            from PySide6.QtCore import QTimer, qInstallMessageHandler
            from PIL import Image
            from kfps_ui.workspace_host import WorkspaceWindow

            messages, result = [], {"case": case, "baseline": runtime.baseline, "passed": False}
            previous_handler = qInstallMessageHandler(lambda _kind, _context, message: messages.append(message))

            def install(app, window, controller, _community, _settings, _jsons, _args):
                started = time.monotonic()

                def check():
                    try:
                        shell = next(w for w in app.topLevelWidgets() if isinstance(w, WorkspaceWindow))
                        assert window.property("inWorkspace"), "Not the unified window"
                        assert shell.isVisible() and shell.tabs.count() == 3
                        assert not shell.owners, "Startup unexpectedly opened Editor or Studio"
                        assert controller.currentPage == "create"
                        assert runtime.workspace_lock.isLocked()
                        import ctypes
                        user32 = ctypes.windll.user32
                        user32.GetForegroundWindow.restype = ctypes.c_void_p
                        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
                        pid = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
                        assert pid.value != os.getpid(), "Startup test took desktop focus"
                        errors = [message for message in messages if any(token in message for token in (
                            "ReferenceError", "TypeError", "SyntaxError", "is not a type",
                            "Cannot assign", "Unable to assign", "Binding loop"))]
                        assert not errors, errors
                        capture = output / f"startup-{case}.png"
                        image = window.grabWindow()
                        assert not image.isNull() and image.save(str(capture)), "Blank window capture"
                        with Image.open(capture) as bitmap:
                            assert bitmap.convert("RGB").entropy() > 1.8, "Blank rendered content"
                        result.update(passed=True, tabs=shell.tabs.count(), focus_taken=False,
                                      event_loop_seconds=round(time.monotonic() - started, 3))
                        shell.close()
                        app.exit(0)
                    except Exception as error:
                        result["error"] = repr(error)
                        app.exit(1)

                QTimer.singleShot(2000, check)
                QTimer.singleShot(30000, lambda: app.exit(124))

            module.install_development_harness = install
            sys.argv = [str(ROOT / "KFPS.UI/app.py"), "--demo", "--theme-preview", "Carbon Dark",
                        "--skip-startup-index", "--width", "1280", "--height", "800"]
            try:
                with patch.object(module.AppPaths, "discover", return_value=paths):
                    code = module.main(workspace_runtime=runtime)
                assert code == 0 and result["passed"], result
            finally:
                result["qt_messages"] = sorted(set(messages))
                (output / f"startup-{case}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
                qInstallMessageHandler(previous_handler)
        finally:
            runtime.close()
        assert runtime.workspace_lock is None and runtime.guard is None
    print(json.dumps({"case": case, "passed": True, "baseline_files": runtime.baseline["files"]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", type=int, choices=(1, 2), help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "runtime"):
        parser.error("Output must be under this installation's runtime directory.")
    if args.case:
        run_case(output, args.case)
        return 0
    output.mkdir(parents=True, exist_ok=False)
    for case in (1, 2):
        command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                   "--output", str(output), "--case", str(case)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        (output / f"startup-{case}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            print(result.stdout + result.stderr, file=sys.stderr)
            return result.returncode
        print(result.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
