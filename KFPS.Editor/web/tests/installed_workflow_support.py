"""Private installed-root mode shared by the two existing workflow drivers."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

REFERENCE = Path(__file__).resolve().parents[3]
WORKSPACE = REFERENCE.parent
RUN_ROOTS = (WORKSPACE / "livery/runs", REFERENCE / "runtime/test-runs")
MARKER = "installed-workflow-owner.json"


def ordinary(path):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Linked workflow path: {part}")
    return path.resolve()


def private_path(path):
    path = ordinary(path)
    if not any(path != root and path.is_relative_to(root) for root in RUN_ROOTS):
        raise ValueError("Installed workflow data must remain in named isolated E-drive runs")
    return path


def resolve_paths(installed_root, output, *, profile=None):
    app, out = ordinary(installed_root), private_path(output)
    if not app.is_dir() or app.is_relative_to(out) or out.is_relative_to(app):
        raise ValueError("Installed application and private evidence must be separate")
    if out.exists():
        raise ValueError("Preserve evidence: choose a fresh output directory")
    if os.environ.get("KFPS_EDITOR_BASELINE_DIR"):
        raise ValueError("Installed qualification cannot substitute executable web assets")
    profile = private_path(profile) if profile else out / "profile"
    if profile.is_relative_to(app) or app.is_relative_to(profile) or profile == out:
        raise ValueError("Installed profile must be private and separate from the application")
    owner = {"schema": 1, "appRoot": str(app), "syntheticOnly": True}
    if profile.exists() and any(profile.iterdir()):
        marker = ordinary(profile / MARKER)
        if not marker.is_file() or marker.stat().st_size > 4096 or json.loads(marker.read_bytes()) != owner:
            raise ValueError("Refusing an existing profile not owned by this installed workflow")
    return {"app": app, "out": out, "profile": profile, "exports": out / "exports", "owner": owner}


def validate_private_windows_profile(browser_profile):
    # Query in the future child's environment, not a cached parent Shell context.
    query = '''import ctypes,json
from ctypes import wintypes
s=ctypes.WinDLL("shell32")
s.SHGetFolderPathW.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR]
s.SHGetFolderPathW.restype=ctypes.c_long
rows=[]
for csidl in (0x1c,0x1a):
 b=ctypes.create_unicode_buffer(260)
 hr=s.SHGetFolderPathW(None,csidl,None,0,b)
 rows.append({"hr":hr,"path":b.value})
print(json.dumps(rows))'''
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", query], env=dict(os.environ),
        cwd=os.environ["USERPROFILE"], capture_output=True, text=True, check=True,
        timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(completed.stdout)
    result = {}
    for row, (key, label) in zip(rows, (("LOCALAPPDATA", "localAppData"), ("APPDATA", "roamingAppData")), strict=True):
        if row["hr"] < 0 or Path(row["path"]).resolve() != Path(os.environ[key]).resolve():
            raise ValueError(f"Private Windows {key} lookup failed or mismatched: 0x{row['hr'] & 0xffffffff:08X}")
        result[label] = row["path"]
    default = Path(result["localAppData"]) / "Google/Chrome/User Data"
    if Path(browser_profile).resolve().is_relative_to(default.resolve()):
        raise ValueError("Private Chrome profile must be separate from the default data directory")
    return {**result, "browserProfile": str(browser_profile), "defaultChromeProfile": str(default),
            "distinctFromDefaultChrome": True}


def initialize_private_run(paths):
    out, profile = paths["out"], paths["profile"]
    out.mkdir(parents=True, exist_ok=False)
    profile.mkdir(parents=True, exist_ok=True)
    marker = profile / MARKER
    if not marker.exists():
        marker.write_text(json.dumps(paths["owner"]), encoding="utf-8")
    for key in list(os.environ):
        if key.upper().startswith(("PYTHON", "QT_", "QTWEBENGINE", "QML", "PYSIDE", "SHIBOKEN")):
            os.environ.pop(key)
    for key in ("TEMP", "TMP", "TMPDIR", "USERPROFILE", "XDG_CACHE_HOME"):
        location = out / ("env-" + key.lower())
        location.mkdir()
        os.environ[key] = str(location)
    for key, suffix in (("LOCALAPPDATA", "AppData/Local"), ("APPDATA", "AppData/Roaming")):
        location = Path(os.environ["USERPROFILE"]) / suffix
        location.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(location)
    os.environ["HOME"] = os.environ["USERPROFILE"]
    os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(os.environ["USERPROFILE"])
    check = validate_private_windows_profile(profile / "browser-profile")
    (out / "private-environment.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    os.environ["KFPS_APP_ROOT"] = str(paths["app"])
    os.environ["KFPS_TEST_APP_ROOT"] = str(paths["app"])
    os.environ["KFPS_TEST_REFERENCE_ROOT"] = str(REFERENCE)
    os.environ["KFPS_TEST_PYTHON"] = sys.executable
    os.environ["QT_QPA_PLATFORM"] = "windows"
    fixture = out / "launch-fixture/runtime"
    fixture.mkdir(parents=True)
    (fixture / "qml-shell-settings.json").write_text(json.dumps({"editorGraphics": "opengl", "editorUseChrome": False}))
    paths["launch_fixture"] = fixture.parent
    paths["observed"] = {}
    paths["window_checks"] = 0
    paths["window_errors"] = []


def verify_installed(paths):
    app = paths["app"]
    if (Path(sys.executable).resolve().parent != app / "python" or not sys.flags.isolated or
            not sys.dont_write_bytecode or not sys.pycache_prefix):
        raise RuntimeError("Installed workflows require selected-install/python/python.exe -I -B -X pycache_prefix=<private E run>")
    prefix = private_path(sys.pycache_prefix)
    if prefix.is_relative_to(app):
        raise RuntimeError("Bytecode prefix must not use the installation")
    for name, module in list(sys.modules.items()):
        if name == "kfps_editor" or name.startswith("kfps_editor."):
            filename = getattr(module, "__file__", None)
            if filename and not Path(filename).resolve().is_relative_to(app / "KFPS.Editor/src"):
                raise RuntimeError(f"Wrong installed host module: {name}")
    if not ordinary(app / "KFPS.Editor/baseline.json").is_file():
        raise RuntimeError("Genuine installed baseline is required; it will not be generated")
    from kfps_editor.baseline import verify
    identity = verify(app)
    if identity.get("status") != "verified":
        raise RuntimeError("Installed host baseline was not verified")
    paths["identity"] = identity
    from kfps_editor import graphics
    selection = graphics.select_policy(paths["launch_fixture"])
    graphics.configure_environment(os.environ, selection)
    graphics.configure_qt(selection)
    return identity


def observe_installed(paths):
    if time.monotonic() - paths.get("last_observation", 0) < .1:
        return
    paths["last_observation"] = time.monotonic()
    import psutil
    current = psutil.Process()
    pids = {current.pid}
    for process in current.children(recursive=True):
        try:
            paths["observed"][(process.pid, process.create_time())] = process
            pids.add(process.pid)
        except psutil.NoSuchProcess:
            pass
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    violations = []
    @callback
    def visit(hwnd, unused):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user.IsWindowVisible(hwnd):
            violations.append({"pid": pid.value, "kind": "visible"})
        return True
    user.EnumWindows(visit, 0)
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    if pid.value in pids:
        violations.append({"pid": pid.value, "kind": "foreground"})
    paths["window_checks"] += 1
    paths["window_errors"].extend(violations)
    if violations:
        raise RuntimeError("Installed workflow opened or activated an owned window")


def finish_installed(paths, scripts):
    if paths.get("finished"):
        return
    paths["finished"] = True
    import psutil
    report = {"passed": False, "installedRoot": str(paths["app"]), "profile": str(paths["profile"]),
              "exports": str(paths["exports"]), "windowChecks": paths["window_checks"],
              "windowViolations": paths["window_errors"], "compiledLauncherTest": False}
    errors = []
    try:
        from kfps_editor.baseline import verify
        after = verify(paths["app"])
        if after.get("status") != "verified" or after.get("baseline") != paths["identity"].get("baseline"):
            raise RuntimeError("Installed source/baseline changed during workflow")
        report["baselineBefore"] = paths["identity"]
        report["baselineAfter"] = after
        report["sourceUnchanged"] = True
        result = json.loads((paths["out"] / "results.json").read_bytes())
        rows = result["results"]
        if ([row["script"] for row in rows] != [Path(script).name for script in scripts] or
                not all(row.get("passed") is True for row in rows) or not result["pageErrors"]["passed"]):
            raise RuntimeError("Not all requested real page suites passed")
        assets = json.loads((paths["out"] / "asset-readback.json").read_bytes())
        if not assets or not all(row.get("matched") is True for row in assets):
            raise RuntimeError("Installed renderer asset readback did not match")
        if paths["window_errors"] or not paths["window_checks"]:
            raise RuntimeError("No-focus qualification failed or had no observations")
    except Exception as exc:
        errors.append(str(exc))
    finally:
        owned = dict(paths["observed"])
        for process in psutil.Process().children(recursive=True):
            try:
                owned[(process.pid, process.create_time())] = process
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                errors.append(f"Owned process cleanup failed: {exc}")
        live = []
        for (pid, created), process in owned.items():
            try:
                if process.is_running() and process.create_time() == created:
                    process.terminate()
                    live.append(process)
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                errors.append(f"Owned process termination failed: {exc}")
                live.append(process)
        _, alive = psutil.wait_procs(live, timeout=5)
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                errors.append(f"Owned process kill failed: {exc}")
        _, alive = psutil.wait_procs(alive, timeout=5)
        report["ownedSurvivors"] = [process.pid for process in alive]
        if alive:
            errors.append("Owned child processes survived cleanup")
        report["errors"] = errors
        report["passed"] = not errors
        (paths["out"] / "installed-workflow.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if errors:
        raise RuntimeError("; ".join(errors))
