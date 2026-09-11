"""Run existing Playwright page regressions in an isolated real Qt editor."""
import argparse
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
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
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
sys.path.insert(0, str(root / "KFPS.UI/src"))
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_ui.editor_desktop import EditorDesktop

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
host = EditorDesktop(root, profile)
child = None
log = None
try:
    assert host.start({"mode": "activate", "project": ""})
    host.module.EDITOR_JSON_ROOT = profile / "exports"
    host.resize(1600, 1000)
    host.show()
    deadline = time.monotonic() + args.timeout
    while not host._ready:
        app.processEvents()
        if host._failed or time.monotonic() > deadline:
            raise RuntimeError("Native editor failed to become ready")
        time.sleep(.01)
    log = (out / "runner.log").open("w", encoding="utf-8")
    child = subprocess.Popen([
        shutil.which("node"), str(Path(__file__).with_suffix(".cjs")),
        str(port), str(out), *[str(script.resolve()) for script in args.scripts],
    ], cwd=out, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    while child.poll() is None:
        app.processEvents()
        if time.monotonic() > deadline:
            raise TimeoutError("Native page regression exceeded its deadline")
        time.sleep(.005)
    host.grab().save(str(out / "native-window.png"))
    result = child.returncode
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
            app.processEvents()
            time.sleep(.005)
        guard.stop()
        if unexpected_dialogs or host.isVisible() or not host._allow_close:
            raise RuntimeError(f"Native clean close failed: {unexpected_dialogs}")
        (out / "native-close.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
finally:
    if child and child.poll() is None:
        child.kill()
        child.wait()
    if log:
        log.close()
    host.shutdown()
    host.hide()
print((out / "runner.log").read_text(encoding="utf-8") if (out / "runner.log").exists() else "No runner output")
sys.exit(result)
