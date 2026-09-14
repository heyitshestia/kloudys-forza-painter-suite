"""Independent entry point for the KFPS Vinyl Editor."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(description="KFPS Vinyl Editor")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--mode", choices=("activate", "new", "json", "tutorial"), default="activate")
    parser.add_argument("--runtime-root", type=Path, help="Editor data directory; defaults to the installation runtime/fabric-editor directory.")
    parser.add_argument("--from-kfps", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--background", action="store_true", help="Open without raising the window or taking focus.")
    parser.add_argument("--test-debug-port", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    # A shortcut's working directory or inherited root must not select another install.
    os.environ["KFPS_APP_ROOT"] = str(APP_ROOT)
    runtime = (args.runtime_root or APP_ROOT / "runtime" / "fabric-editor").resolve()
    host = None
    app = None
    update_guard = None
    record_startup = None
    try:
        from .bootstrap_log import prepare_desktop_log, record_startup
        prepare_desktop_log(runtime)
        from .baseline import CONTRACT, development_root, isolated_environment, launch_command, verify
        development = development_root(APP_ROOT) and not (APP_ROOT / CONTRACT).exists()
        if args.test_debug_port is not None and (not development_root(APP_ROOT) or not 1024 <= args.test_debug_port <= 65535):
            raise RuntimeError("Test debugging is only available in a source checkout or its private qualification stage.")
        if not development and (Path(sys.executable).resolve().parent != APP_ROOT / "python" or
                                not sys.flags.isolated or not sys.dont_write_bytecode or not sys.pycache_prefix or
                                isolated_environment() != dict(os.environ)):
            command, environment = launch_command(APP_ROOT, APP_ROOT / "KFPS.Editor/editor.py", sys.argv[1:])
            import subprocess
            from .activation import grant_foreground
            with subprocess.Popen(command, cwd=APP_ROOT, env=environment,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as child:
                if not args.background:
                    grant_foreground(child.pid)
                return child.wait()
        if args.test_debug_port is not None:
            os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = str(args.test_debug_port)
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--remote-allow-origins=*"
        from .ipc import forward_request, instance_name, validate_request, wait_until_ready
        request = validate_request({"project": args.project_id, "mode": args.mode})
        if args.background:
            request["background"] = True
        record_startup(runtime, "launch-request", mode=args.mode, has_project=bool(args.project_id),
                       from_kfps=args.from_kfps, background=args.background)
        name = instance_name(APP_ROOT, runtime)
        if os.name == "nt":
            from .startup import acquire_or_forward
            update_guard = acquire_or_forward(APP_ROOT, runtime, request)
            if update_guard is None:
                wait_until_ready(runtime, name, background=args.background)
                return 0
        baseline = verify(APP_ROOT)
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox
        from tools.source_download_guard import evaluate_source_download_guard
        from .host import EditorDesktop

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv[:1])
        app.setApplicationName("KFPS Vinyl Editor")
        app.setOrganizationName("KFPS")
        if evaluate_source_download_guard(APP_ROOT).blocked:
            raise RuntimeError("GitHub source downloads are not runnable releases. Use a complete KFPS installation.")
        if forward_request(name, request):
            wait_until_ready(runtime, name, background=args.background)
            return 0
        if args.test_debug_port is not None:
            baseline["test_debugging"] = True
        host = EditorDesktop(APP_ROOT, runtime, background=args.background,
                             baseline=baseline, update_guard=update_guard)
        update_guard = None
        if not host.start(request):
            if forward_request(name, request, timeout=8000):
                wait_until_ready(runtime, name, background=args.background)
                return 0
            raise RuntimeError("The editor data folder is locked by another process, and no responding editor was found. Close the other editor or application using this folder and try again. Your saved work has not been changed.")
        host.present_window(background=args.background)
        return app.exec()
    except Exception as exc:
        from .baseline import BaselineError
        if isinstance(exc, BaselineError):
            from .localization import EditorTranslator, editor_system_language
            translator = EditorTranslator(APP_ROOT, runtime, editor_system_language())
            advice = translator.tr("The editor installation needs repair. Close KFPS and run KFPS-Updater.exe, then reopen the editor. Your projects and settings will be kept.")
            exc = BaselineError(advice + "\n\n" + str(exc))
        # A failed launch must release ownership before showing a modal error.
        # Otherwise leaving the error open can block every subsequent retry.
        clean_shutdown = host.shutdown() if host is not None else True
        if update_guard is not None:
            update_guard.Close()
            update_guard = None
        from .localization import EditorTranslator, editor_system_language
        translator = EditorTranslator(APP_ROOT, runtime, editor_system_language())
        localized = translator.message(str(exc))
        if record_startup is not None:
            record_startup(runtime, "launch-failed", error=type(exc).__name__,
                           winerror=getattr(exc, "winerror", getattr(exc.__cause__, "winerror", None)))
        message = f"{localized}\n\nSee {runtime / 'desktop.log'}"
        try:
            runtime.mkdir(parents=True, exist_ok=True)
            from .bootstrap_log import open_desktop_log
            with open_desktop_log(runtime) as log:
                log.write(f"Startup failed in PID {os.getpid()}\n")
                traceback.print_exc(file=log)
        except (OSError, ImportError):
            pass
        try:
            runtime.mkdir(parents=True, exist_ok=True)
            report = runtime / f"desktop-startup-error.{os.getpid()}.tmp"
            report.write_text(json.dumps({"pid": os.getpid(), "error": localized[:2000]}), encoding="utf-8")
            report.replace(runtime / "desktop-startup-error.json")
        except OSError:
            pass
        if not args.from_kfps and clean_shutdown:
            if app is not None:
                QMessageBox.critical(None, translator.tr("KFPS Editor could not start"), message)
            elif os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, translator.tr("KFPS Editor could not start"), 0x10)
        return 1
    finally:
        if host is not None:
            host.shutdown()
        if update_guard is not None:
            update_guard.Close()


if __name__ == "__main__":
    raise SystemExit(main())
