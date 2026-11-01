"""Standalone Studio startup; reusable widgets live in studio_host.py."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
if __package__:
    from .studio_window import LAB, NativeOwnerError, validate_window_url
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from studio_window import LAB, NativeOwnerError, validate_window_url


NATIVE_CATALOG = LAB / "src/web/locales/messages.json"
MAX_NATIVE_CATALOG_BYTES = 1024 * 1024
READINESS_SCRIPT = """(() => {
    const root = document.documentElement;
    if (!root) return null;
    const language = root.lang;
    return JSON.stringify({ready:!!window.__liveryLab?.ready,
        document:window.__kfpsStudioNativeDocument,
        language:['en','ko','ja'].includes(language) ? language : 'en'});
})()"""


class NativePresentation:
    """Reuse Studio's catalog; the page supplies only its allowlisted locale."""

    def __init__(self):
        self.language = "en"
        self._messages = {}
        try:
            with NATIVE_CATALOG.open("rb") as source:
                raw = source.read(MAX_NATIVE_CATALOG_BYTES + 1)
            catalog = json.loads(raw) if len(raw) <= MAX_NATIVE_CATALOG_BYTES else None
            if isinstance(catalog, dict):
                for key in ("Save Studio export", "A file is still being saved. Close again after it finishes."):
                    row = catalog.get(key)
                    if (isinstance(row, list) and len(row) == 2
                            and all(isinstance(value, str) and 0 < len(value) <= 512
                                    and value.strip() and not any(ord(c) < 32 or ord(c) == 127 for c in value)
                                    for value in row)):
                        self._messages[key] = tuple(row)
        except (OSError, ValueError, RecursionError):
            pass  # An unavailable translation must never block saving or closing.

    def set_language(self, language):
        self.language = language if isinstance(language, str) and language in ("en", "ko", "ja") else "en"

    def text(self, source):
        row = self._messages.get(source)
        return row[0 if self.language == "ko" else 1] if row and self.language != "en" else source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--offscreen", action="store_true")
    parser.add_argument("--auto-close", type=float, default=0)
    parser.add_argument("--test-control", action="store_true")
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((LAB / "runs").resolve()) or run == (LAB / "runs").resolve():
        raise ValueError("Invalid native host run directory.")
    validate_window_url(args.url)
    run.mkdir(parents=True, exist_ok=True)

    def test_control():
        if not (args.offscreen and args.test_control):
            return {}
        try:
            with (run / "control.json").open("rb") as source:
                body = source.read(4097)
            value = json.loads(body) if len(body) <= 4096 else {}
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def test_event(kind, **data):
        if args.offscreen and args.test_control:
            with (run / "events.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps(dict(kind=kind, **data)) + "\n")

    def record(status, **data):
        temporary = run / "host.tmp"
        temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), **data)), encoding="utf-8")
        temporary.replace(run / "host.json")

    host = None
    try:
        root = args.root.resolve()
        sys.path.insert(0, str(root / "KFPS.Editor/src"))
        from kfps_editor import graphics, baseline
        baseline.verify_import_origins(root / "python")
        selection = graphics.select_policy(root)
        graphics.configure_environment(os.environ, selection)
        diagnostics = graphics.configure_qt(selection)
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import QApplication
        if __package__:
            from .studio_host import StudioHost
        else:
            from studio_host import StudioHost

        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(["KFPS Livery Studio"])
        app.setOrganizationName("KFPS")
        app.setApplicationName("Livery Studio")
        host = StudioHost(args.url, run, hosted=False, offscreen=args.offscreen,
                          diagnostic_policy=selection.backend, test_control=test_control, test_event=test_event)
        area = app.primaryScreen().availableGeometry()
        host.window.resize(1760 if args.offscreen else min(1760, area.width()),
                           1040 if args.offscreen else min(1040, area.height()))
        if args.offscreen:
            host.view.resize(1760, 1040)
            host.window.show()
            host.page.setVisible(True)

        def failure(message):
            record("failed", error=message)
            app.exit(1)

        def ready(value):
            if not value:
                return
            record("ready", graphics=diagnostics, engine=baseline.engine_identity(), offscreen=args.offscreen)
            if not args.offscreen:
                host.window.show()
            if args.auto_close and args.offscreen:
                QTimer.singleShot(int(args.auto_close * 1000), host.window.close)

        host.failed.connect(failure)
        host.readyChanged.connect(ready)
        host.closed.connect(app.quit)
        control_timer = QTimer(host)
        if args.offscreen and args.test_control:
            def controlled_close():
                control = test_control()
                if control.get("resume_download"):
                    for item in list(host.pending_downloads.values()):
                        item.resume()
                command = control.get("close")
                if command and command != getattr(controlled_close, "last", None):
                    controlled_close.last = command
                    host.window.close()
            control_timer.setInterval(200)
            control_timer.timeout.connect(controlled_close)
            control_timer.start()
        code = app.exec()
        control_timer.stop()
        host.shutdown()
        if code == 0:
            record("closed", graphics=diagnostics, offscreen=args.offscreen)
        return code
    except Exception as exc:
        record("failed", error=str(exc) if isinstance(exc, NativeOwnerError)
               else f"Native Studio startup failed ({type(exc).__name__}).")
        raise
    finally:
        if host is not None:
            host.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
