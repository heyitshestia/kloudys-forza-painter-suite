"""Run page workflows through the installed Chrome host, always in background."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(sys.argv[1]).resolve()
SCRIPTS = [Path(p).resolve() for p in sys.argv[2:]]
assert OUT.is_relative_to(ROOT / "runtime/test-runs") and not OUT.exists()
assert SCRIPTS and all(p.is_relative_to(Path(__file__).resolve().parent) and p.is_file() for p in SCRIPTS)
OUT.mkdir(parents=True)
sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_editor.baseline import verify
from kfps_editor.browser_host import BrowserDesktop

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
host = BrowserDesktop(ROOT, OUT / "profile", background=True, export_root=OUT / "exports", baseline=verify(ROOT))


unexpected_dialogs = []


def unexpected_dialog(kind, title, *args, **kwargs):
    unexpected_dialogs.append({"kind": str(kind), "title": str(title)})
    return QMessageBox.StandardButton.Cancel


host._message_box = unexpected_dialog
child = None
try:
    assert host.start({"mode": "activate"})
    host.page.sync("Emulation.setFocusEmulationEnabled", {"enabled": True})
    deadline = time.monotonic() + 240
    while not host._ready:
        app.processEvents()
        if host._failed or time.monotonic() > deadline:
            raise RuntimeError("Chrome editor failed to become ready")
        time.sleep(.01)
    port = (host.page.profile / "DevToolsActivePort").read_text().splitlines()[0]
    (OUT / "host.json").write_text(json.dumps({"background": True, "browserPid": host.page.process.pid,
        "runtime": str(host.runtime), "ready": host._ready}), encoding="utf-8")
    with (OUT / "runner.log").open("w", encoding="utf-8") as log:
        child_env = os.environ.copy()
        options = json.loads(child_env.get("KFPS_TEST_OPTIONS", "{}"))
        options["browserHost"] = True
        child_env["KFPS_TEST_OPTIONS"] = json.dumps(options)
        child = subprocess.Popen([shutil.which("node"), str(Path(__file__).with_name("run-native-page.cjs")),
            port, str(OUT), *map(str, SCRIPTS)], cwd=OUT, env=child_env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        while child.poll() is None:
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError("Chrome workflow exceeded four minutes")
            time.sleep(.005)
        result = child.returncode or (1 if unexpected_dialogs else 0)
    if result == 0:
        allowance = host.page.sync("Runtime.evaluate", {"expression": "window.__KfpsBrowserCloseAllowed === true", "returnByValue": True})
        if allowance.get("result", {}).get("value") is not False:
            raise RuntimeError("Test navigation allowance survived a reload")
        host.close()
        close_deadline = time.monotonic() + 20
        while not host._allow_close and not unexpected_dialogs and time.monotonic() < close_deadline:
            app.processEvents()
            time.sleep(.005)
        if not host._allow_close or unexpected_dialogs:
            raise RuntimeError("Chrome normal close handshake failed")
        (OUT / "normal-close.json").write_text(json.dumps({"passed": True, "navigationAllowanceCleared": True}), encoding="utf-8")
finally:
    (OUT / "native-dialogs.json").write_text(json.dumps(unexpected_dialogs), encoding="utf-8")
    if child and child.poll() is None:
        child.kill()
        child.wait()
    host.shutdown()
    host.hide()
print((OUT / "runner.log").read_text(encoding="utf-8"))
sys.exit(result)
