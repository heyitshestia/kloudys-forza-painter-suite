"""Run page workflows through the installed Chrome host, always in background."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("scripts", nargs="+", type=Path)
parser.add_argument("--installed-root", type=Path)
parser.add_argument("--profile", type=Path, help="Explicit private restart profile")
parser.add_argument("--export-root", type=Path, help="Fresh isolated export folder for cross-root source qualification")
parser.add_argument("--timeout", type=int, default=240)
args = parser.parse_args()
test_options = json.loads(os.environ.get("KFPS_TEST_OPTIONS", "{}"))
if not isinstance(test_options, dict):
    parser.error("Test options must be a JSON object")
if test_options.get("customizationRestart") and test_options.get("preserveStartupNotices") is not True:
    parser.error("Customization restart requires preserveStartupNotices:true before host startup")
REFERENCE = Path(__file__).resolve().parents[3]
ROOT = REFERENCE
SCRIPTS = [p.resolve() for p in args.scripts]
assert SCRIPTS and all(p.is_relative_to(Path(__file__).resolve().parent) and p.is_file() for p in SCRIPTS)
sys.path.insert(0, str(Path(__file__).resolve().parent))
installed = None
if args.installed_root:
    if args.export_root:
        parser.error("Installed qualification already isolates its export folder")
    from installed_workflow_support import (resolve_paths, initialize_private_run, verify_installed,
                                            observe_installed, finish_installed, WORKSPACE)
    # Installed mode never inherits a profile from ambient environment variables.
    installed = resolve_paths(args.installed_root, args.output, profile=args.profile)
    initialize_private_run(installed)
    import atexit
    atexit.register(finish_installed, installed, SCRIPTS)
    ROOT, OUT, PROFILE = installed["app"], installed["out"], installed["profile"]
    export_root = installed["exports"]
else:
    OUT = args.output.resolve()
    assert OUT.is_relative_to(ROOT / "runtime/test-runs") and not OUT.exists()
    PROFILE = (args.profile or Path(os.environ.get("KFPS_TEST_PROFILE", str(OUT / "profile")))).resolve()
    if not PROFILE.is_relative_to(ROOT / "runtime/test-runs"):
        raise ValueError("Chrome regression profiles must remain inside runtime/test-runs")
    OUT.mkdir(parents=True)
    export_root = OUT / "exports"
    if args.export_root:
        from installed_workflow_support import private_path
        export_root = private_path(args.export_root)
        if export_root.exists():
            raise ValueError("Preserve exports: choose a fresh export folder")
sys.path[:0] = [str(ROOT / "KFPS.Editor/src"), str(ROOT)]
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from kfps_editor.baseline import verify
from kfps_editor.browser_host import BrowserDesktop
import kfps_editor.browser_host as host_module
if not Path(host_module.__file__).resolve().is_relative_to(ROOT):
    raise RuntimeError("Chrome host loaded from the wrong installation")
if installed:
    identity = verify_installed(installed)
    from kfps_editor import browser_page
    original_process = browser_page.OwnedBrowserProcess
    class HeadlessProcess(original_process):
        def __init__(self, flags, job):
            flags = [flag for flag in flags if flag != "--no-startup-window"]
            flags += ["--headless=new", "--enable-automation", "--disable-background-timer-throttling", "about:blank"]
            super().__init__(flags, job)
    browser_page.OwnedBrowserProcess = HeadlessProcess
else:
    identity = verify(ROOT)

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
host = BrowserDesktop(ROOT, PROFILE, background=True, export_root=export_root, baseline=identity)
if installed:
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    host.present_window = lambda **kwargs: None


unexpected_dialogs = []


def unexpected_dialog(kind, title, *args, **kwargs):
    unexpected_dialogs.append({"kind": str(kind), "title": str(title)})
    return QMessageBox.StandardButton.Cancel


host._message_box = unexpected_dialog
child = None
try:
    assert host.start({"mode": "activate"})
    host.page.sync("Emulation.setFocusEmulationEnabled", {"enabled": True})
    deadline = time.monotonic() + args.timeout
    while not host._ready:
        if installed:
            observe_installed(installed)
        app.processEvents()
        if host._failed or time.monotonic() > deadline:
            raise RuntimeError("Chrome editor failed to become ready")
        time.sleep(.01)
    port = (host.page.profile / "DevToolsActivePort").read_text().splitlines()[0]
    (OUT / "host.json").write_text(json.dumps({"background": True, "browserPid": host.page.process.pid,
        "runtime": str(host.runtime), "ready": host._ready}), encoding="utf-8")
    (OUT / "process.json").write_text(json.dumps({"pid": os.getpid(), "profile": str(PROFILE),
        "exportRoot": str(export_root), "browserPid": host.page.process.pid,
        "appRoot": str(ROOT), "hostSource": host_module.__file__, "pythonExecutable": sys.executable}), encoding="utf-8")
    with (OUT / "runner.log").open("w", encoding="utf-8") as log:
        child_env = dict(os.environ, KFPS_TEST_APP_ROOT=str(ROOT), KFPS_TEST_PYTHON=sys.executable)
        if installed:
            child_env["NODE_PATH"] = str(WORKSPACE / "dependencies/node_modules")
        options = json.loads(child_env.get("KFPS_TEST_OPTIONS", "{}"))
        options["browserHost"] = True
        child_env["KFPS_TEST_OPTIONS"] = json.dumps(options)
        child = subprocess.Popen([str(WORKSPACE / "dependencies/node.exe") if installed else shutil.which("node"), str(Path(__file__).with_name("run-native-page.cjs")),
            port, str(OUT), *map(str, SCRIPTS)], cwd=OUT, env=child_env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        while child.poll() is None:
            if installed:
                observe_installed(installed)
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError("Chrome workflow exceeded its deadline")
            time.sleep(.005)
        result = child.returncode or (1 if unexpected_dialogs else 0)
    if result == 0:
        allowance = host.page.sync("Runtime.evaluate", {"expression": "window.__KfpsBrowserCloseAllowed === true", "returnByValue": True})
        if allowance.get("result", {}).get("value") is not False:
            raise RuntimeError("Test navigation allowance survived a reload")
        host.close()
        close_deadline = time.monotonic() + 20
        while not host._allow_close and not unexpected_dialogs and time.monotonic() < close_deadline:
            if installed:
                observe_installed(installed)
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
    try:
        host.shutdown()
        host.hide()
    finally:
        if installed:
            browser_page.OwnedBrowserProcess = original_process
            finish_installed(installed, SCRIPTS)
print((OUT / "runner.log").read_text(encoding="utf-8"))
sys.exit(result)
