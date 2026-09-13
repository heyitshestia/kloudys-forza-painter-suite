"""Real native startup timeout, activate/retry, busy IPC and occupied port."""
import json
import os
import socket
import sys
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root / "KFPS.Editor/src"))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from kfps_editor.host import EditorDesktop
from kfps_editor.ipc import forward_request, instance_name, EditorConnectionError

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
runtime = out / "runtime/fabric-editor"
runtime.mkdir(parents=True, exist_ok=True)
sentinel = runtime / "projects/untouched.fabric-project.json"
sentinel.parent.mkdir()
sentinel.write_text('{"privateTestSentinel":true}')
expected = sentinel.read_bytes()
occupied = socket.socket()
occupied.bind(("127.0.0.1", 0))
occupied.listen()
port = occupied.getsockname()[1]
(runtime / "desktop-port.json").write_text(json.dumps({"port": port}))
host = EditorDesktop(root, runtime)
from native_window_policy import keep_in_background
keep_in_background(host)
results = []


def wait(predicate, timeout=15):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        app.processEvents()
        if predicate():
            return
        time.sleep(.01)
    raise TimeoutError("Native condition did not complete")


def forward(request, bridge=False):
    code = """
import json, sys
from PySide6.QtCore import QCoreApplication
sys.path.insert(0, sys.argv[1])
from kfps_editor.ipc import forward_request
app = QCoreApplication([])
try:
    if sys.argv[4] == 'bridge':
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        root, runtime = Path(sys.argv[5]), Path(sys.argv[6])
        sys.path.insert(0, str(root / 'KFPS.UI/src'))
        from kfps_ui.editor_launch import launch_editor
        request = json.loads(sys.argv[3])
        with patch('kfps_ui.editor_launch.subprocess.Popen', side_effect=AssertionError('Live bridge spawned a second editor')):
            message = launch_editor(SimpleNamespace(app_root=root, runtime_root=runtime.parent), project=request.get('project',''), mode=request.get('mode','activate'))
        print(json.dumps({'ok':bool(message)}))
    else:
        print(json.dumps({'ok': forward_request(sys.argv[2], json.loads(sys.argv[3]), timeout=1500)}))
except Exception as exc: print(json.dumps({'error': str(exc)}))
"""
    child = subprocess.Popen([sys.executable, "-c", code, str(root / "KFPS.Editor/src"), instance_name(root, runtime), json.dumps(request), "bridge" if bridge else "ipc", str(root), str(runtime)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    wait(lambda: child.poll() is not None)
    stdout, stderr = child.communicate()
    assert child.returncode == 0, stderr
    response = json.loads(stdout)
    return EditorConnectionError(response["error"]) if "error" in response else response["ok"]


try:
    assert host.start({"mode": "activate", "project": ""})
    host.show()
    wait(lambda: host._ready)
    assert host.url.port() != port
    results.append({"occupiedPortFallback": True})
    assert forward({"mode": "activate"}, bridge=True) is True
    results.append({"kfpsBridgeActivatedExistingEditor": True})
    host._closing = True
    assert isinstance(forward({"mode": "new"}), EditorConnectionError)
    assert isinstance(forward({"mode": "new"}, bridge=True), EditorConnectionError)
    host._closing = False
    assert not host._queued_requests
    results.append({"busyRequestRejectedWithoutQueueing": True})
    original_get = host.module.Handler.do_GET
    def blank_page(handler):
        if handler.path.split('?', 1)[0] == '/tools/fabric-editor/index.html':
            body = b'<html><body>Injected startup without editor JavaScript</body></html>'
            handler.send_response(200)
            handler.send_header('Content-Type', 'text/html')
            handler.send_header('Content-Length', str(len(body)))
            handler.send_header('Cache-Control', 'no-store')
            handler.end_headers()
            handler.wfile.write(body)
        else:
            original_get(handler)
    host.module.Handler.do_GET = blank_page
    host.startup_timer.setInterval(1200)
    host.reload_editor()
    wait(lambda: host._failed)
    assert host.stack.currentWidget() is host.error_panel
    assert json.loads((runtime / "desktop.json").read_text())["state"] == "failed"
    host.grab().save(str(out / "startup-failure.png"))
    host.module.Handler.do_GET = original_get
    host.startup_timer.setInterval(60000)
    response = forward({"mode": "activate"})
    assert response is True, repr(response)
    host.startup_timer.setInterval(60000)
    wait(lambda: host._ready)
    assert not host._failed
    assert sentinel.read_bytes() == expected
    results.append({"blankStartupDeadlineAndExternalActivateRetry": True, "savedFileUnchanged": True})
    import psutil
    psutil.Process(host.page.renderProcessPid()).terminate()
    wait(lambda: host._failed)
    assert forward({"mode": "activate"}) is True
    wait(lambda: host._ready)
    assert sentinel.read_bytes() == expected
    results.append({"rendererCrashExternalActivateRetry": True})
    host.grab().save(str(out / "reopened.png"))
    (out / "results.json").write_text(json.dumps(results, indent=2))
finally:
    (out / "last-state.json").write_text(json.dumps({"ready": host._ready, "failed": host._failed, "label": host.error_label.text(), "url": host.page.url().toString(), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    host._allow_close = True
    host.close()
    host.shutdown()
    occupied.close()
    app.processEvents()
