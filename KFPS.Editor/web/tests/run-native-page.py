"""Run existing Playwright page regressions in an isolated real Qt editor."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("scripts", nargs="+", type=Path)
parser.add_argument("--timeout", type=int, default=600)
parser.add_argument("--profile", type=Path, help="Reuse an isolated test-run profile")
parser.add_argument("--normal-close", action="store_true", help="Verify the native clean-close handshake")
parser.add_argument("--abrupt-exit", action="store_true", help="Exit a successful isolated suite without the native shutdown handshake")
parser.add_argument("--foreground-test", action="store_true", help="Only for tests that require native focus or unoccluded rendering")
parser.add_argument("--app-root", type=Path, help="Use an isolated staged installation instead of source")
parser.add_argument("--screen-index", type=int, help="Place the real window on this Qt screen without changing display settings")
parser.add_argument("--maximize", action="store_true", help="Use the selected screen's available area")
args = parser.parse_args()
if args.normal_close and args.abrupt_exit:
    parser.error("Normal close and abrupt exit are mutually exclusive")
for script in args.scripts:
    if not script.is_file():
        parser.error(f"Regression script not found: {script}")
root = Path(__file__).resolve().parents[3]
app_root = args.app_root.resolve() if args.app_root else root
if app_root != root and not app_root.is_relative_to(root / "runtime/test-runs"):
    raise ValueError("Staged installations must remain inside runtime/test-runs")
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
profile = args.profile.resolve() if args.profile else out / "profile"
if not profile.is_relative_to(root / "runtime" / "test-runs"):
    raise ValueError("Native regression profiles must remain inside runtime/test-runs")
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = str(port)
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--remote-allow-origins=*")
sys.path.insert(0, str(app_root / "KFPS.Editor/src"))
sys.path.insert(0, str(app_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from kfps_editor.host import EditorDesktop
import kfps_editor.host as host_module
if not Path(host_module.__file__).resolve().is_relative_to(app_root):
    raise RuntimeError("Native host loaded from the wrong installation")

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
host_options = {}
if (app_root / "KFPS.Editor/src/kfps_editor/baseline.py").is_file():
    from kfps_editor.baseline import verify
    identity = verify(app_root)
    identity["test_debugging"] = True
    host_options["baseline"] = identity
# Export IDs remain installation-relative, including isolated test profiles.
export_key = hashlib.sha256(str(profile).casefold().encode()).hexdigest()[:24]
host = EditorDesktop(app_root, profile, export_root=app_root / "runtime/test-runs/native-exports" / export_key, **host_options)
if not args.foreground_test:
    from native_window_policy import keep_in_background
    keep_in_background(host)
child = None
log = None
unexpected_native_dialogs = []
window_events = []


class WindowObservation(QObject):
    def eventFilter(self, watched, event):
        if watched is host and child is not None and child.poll() is None and event.type() in (
            QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.WindowStateChange
        ) and len(window_events) < 128:
            window_events.append({"utc": time.time(), "event": event.type().name,
                                  "geometry": host.geometry().getRect(),
                                  "screen": host.screen().name(), "dpr": host.devicePixelRatioF()})
        return False


window_observation = WindowObservation(host)
host.installEventFilter(window_observation)
def reject_unexpected_native_dialogs():
    # Page suites must arrange document state before reload. A hidden native
    # prompt must fail the suite, not block this processEvents call indefinitely.
    for widget in app.topLevelWidgets():
        if isinstance(widget, QDialog) and widget.isVisible():
            unexpected_native_dialogs.append({"class": widget.metaObject().className(), "title": widget.windowTitle()[:160]})
            widget.reject()
dialog_guard = QTimer()
dialog_guard.timeout.connect(reject_unexpected_native_dialogs)
dialog_guard.start(100)
def check_resource_stop():
    if (out / "stop-test.json").exists():
        raise RuntimeError("External resource guard stopped this isolated native test")

try:
    assert host.start({"mode": "activate", "project": ""})
    host.resize(1600, 1000)
    screens = app.screens()
    if args.screen_index is not None:
        if not 0 <= args.screen_index < len(screens):
            raise ValueError("Requested screen is not available")
        screen = screens[args.screen_index]
        area = screen.availableGeometry()
        host.resize(min(1600, area.width()), min(1000, area.height()))
        host.move(area.x(), area.y())
        host.winId()
        host.windowHandle().setScreen(screen)
    host.show()
    if args.maximize:
        # Some Windows window managers ignore maximize for bottom-most windows.
        # Use the actual selected monitor's available area, without focus changes.
        host.setGeometry(host.screen().availableGeometry())
    app.processEvents()
    (out / "process.json").write_text(json.dumps({
        "pid": os.getpid(), "profile": str(profile), "python": sys.version,
        "appRoot": str(app_root), "hostSource": host_module.__file__,
        "exportRoot": str(host.server.paths.exports),
        "windowPolicy": "foreground" if args.foreground_test else "background-no-activation",
        "started": time.time(), "scripts": [str(script) for script in args.scripts],
        "screens": [{"name": screen.name(), "primary": screen == app.primaryScreen(),
                     "geometry": screen.geometry().getRect(),
                     "available": screen.availableGeometry().getRect(),
                     "dpr": screen.devicePixelRatio()} for screen in screens],
        "selectedScreen": host.screen().name(), "geometry": host.geometry().getRect(),
        "qtScaleFactor": os.environ.get("QT_SCALE_FACTOR"),
    }, indent=2), encoding="utf-8")
    deadline = time.monotonic() + args.timeout
    while not host._ready:
        check_resource_stop()
        app.processEvents()
        if host._failed or time.monotonic() > deadline:
            raise RuntimeError("Native editor failed to become ready")
        time.sleep(.01)
    log = (out / "runner.log").open("w", encoding="utf-8")
    child_env = dict(os.environ, KFPS_TEST_APP_ROOT=str(app_root), KFPS_TEST_PYTHON=sys.executable)
    child = subprocess.Popen([
        shutil.which("node"), str(Path(__file__).with_suffix(".cjs")),
        str(port), str(out), *[str(script.resolve()) for script in args.scripts],
    ], cwd=out, env=child_env, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    while child.poll() is None:
        check_resource_stop()
        app.processEvents()
        if time.monotonic() > deadline:
            raise TimeoutError("Native page regression exceeded its deadline")
        time.sleep(.005)
    host.grab().save(str(out / "native-window.png"))
    result = child.returncode or (1 if unexpected_native_dialogs else 0)
    if args.abrupt_exit and result == 0:
        import psutil
        descendants = [{"pid": process.pid, "started": process.create_time()} for process in psutil.Process().children(recursive=True)]
        (out / "native-abrupt-exit.json").write_text(json.dumps({"passedPageSuite": True, "pid": os.getpid(),
            "children": descendants, "utc": time.time(), "shutdownHandshake": False}), encoding="utf-8")
        (out / "native-window-events.json").write_text(json.dumps(window_events), encoding="utf-8")
        (out / "native-dialogs.json").write_text(json.dumps(unexpected_native_dialogs), encoding="utf-8")
        log.close()
        print((out / "runner.log").read_text(encoding="utf-8"), flush=True)
        os._exit(0)
    if args.normal_close and result == 0:
        unexpected_dialogs = []
        def reject_unexpected_dialogs():
            for widget in app.topLevelWidgets():
                if isinstance(widget, QMessageBox) and widget.isVisible():
                    unexpected_dialogs.append(widget.windowTitle())
                    widget.reject()
        guard = QTimer()
        guard.timeout.connect(reject_unexpected_dialogs)
        guard.start(100)
        host.close()
        close_deadline = time.monotonic() + 20
        while host.isVisible() and not unexpected_dialogs and time.monotonic() < close_deadline:
            check_resource_stop()
            app.processEvents()
            time.sleep(.005)
        guard.stop()
        if unexpected_dialogs or host.isVisible() or not host._allow_close:
            raise RuntimeError(f"Native clean close failed: {unexpected_dialogs}")
        (out / "native-close.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
finally:
    dialog_guard.stop()
    (out / "native-window-events.json").write_text(json.dumps(window_events, indent=2), encoding="utf-8")
    (out / "native-dialogs.json").write_text(json.dumps(unexpected_native_dialogs, indent=2), encoding="utf-8")
    if child and child.poll() is None:
        child.kill()
        child.wait()
    if log:
        log.close()
    host.shutdown()
    host.hide()
print((out / "runner.log").read_text(encoding="utf-8") if (out / "runner.log").exists() else "No runner output")
sys.exit(result)
