"""Independent, loopback-only Studio launcher. Importing never starts a process."""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import psutil

LAB_ROOT = Path(__file__).resolve().parents[2]
CONTROL = LAB_ROOT / "runs/studio-launch"
WORKSPACE = LAB_ROOT / "runs/studio-session-theme-v2"
CONFIG = LAB_ROOT / "settings/local-launch.json"
MAX_JSON = 1024 * 1024


class LaunchCancelled(RuntimeError):
    pass


class IncompatibleStudio(ValueError):
    """A verified live session must be saved and restarted, not replaced."""


def _check_cancel(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise LaunchCancelled("Livery Studio launch was cancelled.")


def _inside(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("Studio writable path is outside its isolated workspace.")
    return path


def _read_json(path, maximum=MAX_JSON):
    with Path(path).open("rb") as source:
        body = source.read(maximum + 1)
    if len(body) > maximum:
        raise ValueError("Studio metadata is too large.")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("Studio metadata must be an object.")
    return value


def _atomic_json(path, value):
    path = _inside(path, LAB_ROOT / "runs")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(value, target, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_url(value):
    if not isinstance(value, str) or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}/[A-Za-z0-9_-]{43}/", value):
        raise ValueError("Studio returned an invalid local session URL.")
    port = urlsplit(value).port
    if not port or not 0 < port <= 65535:
        raise ValueError("Studio returned an invalid local port.")
    return value


def validate_config(config, expected_kfps_root=None):
    if not isinstance(config, dict):
        raise ValueError("Studio configuration must be an object.")
    result = {}
    for key in ("kfpsRoot", "gameRoot", "pythonExe"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Studio configuration is missing {key}.")
        path = Path(value).resolve(strict=True)
        if not (path.is_file() if key == "pythonExe" else path.is_dir()):
            raise ValueError(f"Studio configuration has an invalid {key}.")
        result[key] = str(path)
    if expected_kfps_root is not None and Path(result["kfpsRoot"]) != Path(expected_kfps_root).resolve():
        raise ValueError("Livery Studio is configured for a different KFPS installation.")
    archive = config.get("archive")
    if not isinstance(archive, str) or not re.fullmatch(r"[A-Za-z0-9_ -]+\.zip", archive):
        raise ValueError("Select one car ZIP filename in the Studio configuration.")
    if not (Path(result["gameRoot"]) / "media/Cars" / archive).is_file():
        raise ValueError("The configured car ZIP was not found in the game folder.")
    if not (Path(result["kfpsRoot"]) / "json_preview_renderer.py").is_file():
        raise ValueError("The configured KFPS root is missing its vinyl renderer.")
    result["archive"] = archive
    if config.get("template"):
        result["template"] = str(Path(config["template"]).resolve(strict=True))
        if not Path(result["template"]).is_file():
            raise ValueError("Studio export template must be a file.")
    return result


def load_config(expected_kfps_root=None):
    try:
        try:
            config = _read_json(CONFIG, 65536)
        except FileNotFoundError:
            path = Path(__file__).with_name("install_config.py")
            spec = importlib.util.spec_from_file_location("_kfps_studio_install_config", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            config = module.automatic_config(LAB_ROOT, expected_kfps_root)
        if "kfpsRoot" not in config:
            spec = importlib.util.spec_from_file_location("_studio_package_paths", Path(__file__).with_name("package_paths.py"))
            paths = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(paths)
            config["kfpsRoot"] = str(paths.default_baseline(LAB_ROOT))
        if "pythonExe" not in config and isinstance(config.get("kfpsRoot"), str):
            config["pythonExe"] = str(Path(config["kfpsRoot"]) / "python/python.exe")
        return validate_config(config, expected_kfps_root)
    except FileNotFoundError as exc:
        raise ValueError("Livery Studio setup is missing. Check its settings/local-launch.json.") from exc


@contextmanager
def _launch_lock(timeout, cancelled=None):
    root = _inside(CONTROL, LAB_ROOT / "runs")
    root.mkdir(parents=True, exist_ok=True)
    path = _inside(root / "launch.lock", root)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            _check_cancel(cancelled)
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Another Studio launch is still preparing. Please try again shortly.")
                time.sleep(.1)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def inspect_process(pid, config, workspace, created=None):
    """Never trust a PID/URL alone: require exact executable, script and inputs."""
    try:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            return None
        workspace = _inside(workspace, LAB_ROOT / "runs")
        process = psutil.Process(pid)
        birth = process.create_time()
        if created is not None and abs(birth - float(created)) > .01:
            return None
        if Path(process.exe()).resolve() != Path(config["pythonExe"]):
            return None
        arguments = process.cmdline()
        script = str((LAB_ROOT / "src/run_livery.py").resolve()).casefold()
        if not any(str(Path(arg).resolve()).casefold() == script for arg in arguments[1:3] if not arg.startswith("-")):
            return None
        required = {"--kfps-root": config["kfpsRoot"], "--game-root": config["gameRoot"], "--workspace": str(workspace)}
        for flag, expected in required.items():
            if arguments.count(flag) != 1 or Path(arguments[arguments.index(flag) + 1]).resolve() != Path(expected):
                return None
        if arguments.count("--archive") != 1 or arguments[arguments.index("--archive") + 1] != config["archive"]:
            return None
        if "--prepare-only" in arguments:
            return None
        if config.get("template"):
            if arguments.count("--template") != 1 or Path(arguments[arguments.index("--template") + 1]).resolve() != Path(config["template"]):
                return None
        elif "--template" in arguments:
            return None
        return process
    except (psutil.Error, OSError, ValueError, IndexError, TypeError):
        return None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Studio readiness cannot redirect to another address.")


def _probe(url, archive):
    validate_url(url)
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(url + "api/editor-config", timeout=2) as response:
        body = response.read(MAX_JSON + 1)
    if len(body) > MAX_JSON:
        raise ValueError("Studio returned oversized readiness metadata.")
    config = json.loads(body)
    if not isinstance(config, dict) or config.get("native_mask_pixels") is not True:
        raise ValueError("This Studio predates native mask picking. Start a compatible isolated session.")
    if config.get("host_vinyl_handoff") is not True:
        raise ValueError("This Studio predates editor vinyl transfer. Start a compatible isolated session.")
    if config.get("host_theme_handoff") is not True:
        raise ValueError("This Studio predates host theme transfer. Start a compatible isolated session.")
    if config.get("ui_theme_persistence") is not True:
        raise ValueError("This Studio predates durable theme selection. Start a compatible isolated session.")
    if config.get("source_editor_roundtrip") is not True:
        raise ValueError("This Studio predates source editing. Save your work, then stop and restart Studio.")
    if (type(config.get("package_startup")) is not int or config["package_startup"] != 1
            or type(config.get("chrome_exposed")) is not bool):
        raise IncompatibleStudio("This Studio predates package startup. Save your work, then stop and restart Studio. It has not been stopped automatically.")
    recovery = config.get("recovery")
    if (not isinstance(recovery, dict) or recovery.get("enabled") is not True
            or type(recovery.get("version")) is not int or recovery["version"] != 1):
        raise ValueError("This Studio predates layout recovery. Save your work, then stop and restart Studio.")
    for name in ("project_storage", "vinyl_library"):
        capability = config.get(name)
        if (not isinstance(capability, dict) or capability.get("enabled") is not True
                or type(capability.get("version")) is not int or capability["version"] != 1):
            raise IncompatibleStudio("This Studio predates managed projects or the vinyl library. Save your work, then stop and restart Studio. It has not been stopped automatically.")
    if (not isinstance(config, dict) or not isinstance(config.get("vehicle"), dict)
            or (config["vehicle"].get("archive_name") != archive
                and not (config.get("car_switch") is True and config.get("launch_archive") == archive))):
        raise ValueError("Studio is serving a different car.")
    return config


def _ready_record(info_path, config, *, managed=False, created=None):
    try:
        info_path = _inside(info_path, LAB_ROOT / "runs")
        info = _read_json(info_path, 65536)
        process = inspect_process(info.get("pid"), config, info_path.parent, created)
        if info.get("status") != "running" or process is None:
            return None
        port = urlsplit(validate_url(info.get("url"))).port
        listeners = process.net_connections(kind="tcp")
        if not any(connection.status == psutil.CONN_LISTEN and connection.laddr.ip == "127.0.0.1"
                   and connection.laddr.port == port for connection in listeners):
            return None
        capabilities = _probe(info.get("url"), config["archive"])
        vehicle = capabilities.get("vehicle")
        return {"url": info["url"], "pid": process.pid, "created": process.create_time(),
                "workspace": str(info_path.parent), "managed": managed, "reused": True,
                "chrome_exposed": capabilities.get("chrome_exposed") is not False,
                "vehicle": {key: vehicle.get(key) for key in ("car_id", "model_code")} if isinstance(vehicle, dict) else None,
                "host_vinyl_handoff": capabilities.get("host_vinyl_handoff") is True,
                "host_layout_handoff": capabilities.get("host_layout_handoff") is True,
                "host_project_handoff": capabilities.get("host_project_handoff") is True,
                "host_garage_build": capabilities.get("host_garage_build") is True,
                "host_theme_handoff": capabilities.get("host_theme_handoff") is True,
                "ui_theme_persistence": capabilities.get("ui_theme_persistence") is True}
    except IncompatibleStudio:
        raise
    except (OSError, ValueError, TypeError, psutil.Error):
        return None


def _record_config(config, record):
    """A session may have an ephemeral car, but never a different installation."""
    if not record.get("launch_config"):
        return config
    try:
        saved = validate_config(record["launch_config"], config["kfpsRoot"])
    except (OSError, ValueError, TypeError):
        raise IncompatibleStudio("The registered Studio configuration is no longer valid. It has not been replaced.") from None
    if any(saved[key] != config[key] for key in ("kfpsRoot", "gameRoot", "pythonExe")):
        raise IncompatibleStudio("The registered Studio belongs to a different configuration. It has not been replaced.")
    if saved.get("template") != config.get("template") and not (
            saved["archive"] != config["archive"] and "template" not in saved):
        raise IncompatibleStudio("The registered Studio uses a different export template. It has not been replaced.")
    return saved


def _initial_config(config, vehicle, cancelled):
    if vehicle is None:
        return config
    if (not isinstance(vehicle, dict) or set(vehicle) != {"car_id", "model_code"}
            or type(vehicle["car_id"]) is not int or not 0 < vehicle["car_id"] <= 0xffffffff
            or not isinstance(vehicle["model_code"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_ -]{0,150}", vehicle["model_code"])):
        raise ValueError("The package has no exact car identity.")
    source = str(Path(__file__).resolve().parents[1])
    if source not in sys.path:
        sys.path.insert(0, source)
    from kfps_livery_lab.car_workspace import catalogue
    from kfps_livery_lab.prepare import load_baseline
    load_baseline(Path(config["kfpsRoot"]))
    _check_cancel(cancelled)
    matches = [row for row in catalogue(config["gameRoot"], model_code=vehicle["model_code"]).values()
               if row["car_id"] == vehicle["car_id"] and row["model_code"] == vehicle["model_code"]]
    _check_cancel(cancelled)
    if len(matches) != 1:
        raise ValueError("The package car is ambiguous in the configured catalogue." if matches else
                         "The package's exact car was not found in the configured catalogue.")
    selected = dict(config, archive=matches[0]["archive"])
    if selected["archive"] != config["archive"]:
        selected.pop("template", None)
    return validate_config(selected, config["kfpsRoot"])


def _registration_alive(record):
    pid, created = record.get("pid"), record.get("created")
    if type(pid) is not int or pid <= 0:
        return False
    if created is not None and (type(created) not in (int, float) or not math.isfinite(created)):
        return False
    try:
        process = psutil.Process(pid)
        if not process.is_running():
            return False
        return created is None or abs(process.create_time() - created) <= .01
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except psutil.AccessDenied:
        raise IncompatibleStudio("The registered Studio process could not be verified. It has not been replaced.") from None


def _registered(config):
    try:
        record = _read_json(CONTROL / "instance.json", 65536)
        if not _registration_alive(record):
            return None
        workspace = _inside(record["workspace"], LAB_ROOT / "runs")
        return _ready_record(workspace / "server-info.json", _record_config(config, record),
                             managed=record.get("managed") is True and workspace == WORKSPACE.resolve(),
                             created=record.get("created"))
    except IncompatibleStudio:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _spawn(config):
    workspace = _inside(WORKSPACE, LAB_ROOT / "runs")
    temporary = _inside(workspace / "tmp", workspace)
    cache = _inside(workspace / "cache", workspace)
    temporary.mkdir(parents=True, exist_ok=True)
    cache.mkdir(exist_ok=True)
    args = [config["pythonExe"], "-B", str(LAB_ROOT / "src/run_livery.py"),
            "--kfps-root", config["kfpsRoot"], "--game-root", config["gameRoot"],
            "--archive", config["archive"], "--workspace", str(workspace), "--port", "0"]
    if config.get("template"):
        args.extend(["--template", config["template"]])
    env = dict(os.environ, TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary),
               PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(cache / "pycache"))
    for key in ("XDG_CACHE_HOME", "MPLCONFIGDIR", "NUMBA_CACHE_DIR", "DOTNET_BUNDLE_EXTRACT_BASE_DIR", "DOTNET_CLI_HOME"):
        env[key] = str(cache)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with (CONTROL / "backend.stdout.log").open("ab") as stdout, (CONTROL / "backend.stderr.log").open("ab") as stderr:
        return subprocess.Popen(args, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                stdout=stdout, stderr=stderr, close_fds=True, **options)


def _terminate_owned(pid, created, config, workspace, *, include_children=True):
    process = inspect_process(pid, config, workspace, created)
    if process is None:
        return False
    # Converter descendants belong to this verified startup only, not other KFPS jobs.
    try:
        children = process.children(recursive=True) if include_children else []
    except psutil.NoSuchProcess:
        return True
    except psutil.AccessDenied:
        return False
    for child in reversed(children):
        try:
            child.terminate()
        except psutil.Error:
            pass
    try:
        process.terminate()
        _, alive = psutil.wait_procs([*children, process], timeout=3)
        for item in alive:
            try:
                item.kill()
            except psutil.Error:
                pass
        psutil.wait_procs(alive, timeout=2)
    except psutil.Error:
        pass
    return not any(item.is_running() for item in [*children, process])


def ensure_ready(*, expected_kfps_root=None, cancelled=None, timeout=120, discover=True, initial_vehicle=None):
    _check_cancel(cancelled)
    config = load_config(expected_kfps_root)
    with _launch_lock(timeout, cancelled):
        _check_cancel(cancelled)
        record = _registered(config)
        if record is not None:
            return record
        existing_config = config
        try:
            pending = _read_json(CONTROL / "instance.json", 65536)
            if _registration_alive(pending):
                existing_config = _record_config(config, pending)
                if (Path(pending.get("workspace", "")).resolve() == WORKSPACE.resolve()
                        and inspect_process(pending.get("pid"), existing_config, WORKSPACE, pending.get("created")) is not None):
                    if pending.get("status") == "starting":
                        raise RuntimeError("Studio is still preparing in the background. Try again shortly; no second server was started.")
                    raise RuntimeError("The existing Studio is not responding. It has not been replaced or stopped automatically.")
        except IncompatibleStudio:
            raise
        except (OSError, ValueError):
            pass
        if discover:
            # One directory level only; never traverse caches, user saves or installations.
            for directory in sorted((LAB_ROOT / "runs").iterdir())[:512]:
                if directory.is_dir():
                    record = _ready_record(directory / "server-info.json", config)
                    if record is not None:
                        _atomic_json(CONTROL / "instance.json", record)
                        return record
        # Do not start over an unresponsive canonical process, or kill it automatically.
        try:
            info = _read_json(WORKSPACE / "server-info.json", 65536)
            if inspect_process(info.get("pid"), existing_config, WORKSPACE) is not None:
                raise RuntimeError("The existing Studio is older or not responding. Save your work, then use the Studio stop command and restart it. It has not been stopped automatically.")
        except (OSError, ValueError):
            pass
        _check_cancel(cancelled)
        config = _initial_config(config, initial_vehicle, cancelled)
        _check_cancel(cancelled)
        child = _spawn(config)
        try:
            created = psutil.Process(child.pid).create_time()
        except psutil.Error:
            child.wait(timeout=3)
            raise RuntimeError("Studio stopped during startup. See runs/studio-launch/backend.stderr.log.")
        deadline = time.monotonic() + timeout
        try:
            _atomic_json(CONTROL / "instance.json", {"status": "starting", "pid": child.pid,
                         "created": created, "workspace": str(WORKSPACE.resolve()), "managed": True,
                         "launch_config": config})
            while time.monotonic() < deadline:
                _check_cancel(cancelled)
                if child.poll() is not None:
                    raise RuntimeError("Studio could not start. See livery/runs/studio-launch/backend.stderr.log.")
                record = _ready_record(WORKSPACE / "server-info.json", config, managed=True, created=created)
                if record is not None and record["pid"] == child.pid:
                    vehicle = record.get("vehicle")
                    if initial_vehicle is not None and (not isinstance(vehicle, dict)
                            or type(vehicle.get("car_id")) is not int or vehicle != initial_vehicle):
                        raise ValueError("The prepared Studio does not match the package's exact car. Nothing was opened.")
                    record["reused"] = False
                    _atomic_json(CONTROL / "instance.json", dict(record, launch_config=config))
                    return record
                time.sleep(.15)
            raise TimeoutError("Studio preparation timed out. See livery/runs/studio-launch/backend.stderr.log.")
        except BaseException:
            _terminate_owned(child.pid, created, config, WORKSPACE)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            raise


def stop_owned():
    with _launch_lock(10):
        try:
            record = _read_json(CONTROL / "instance.json", 65536)
            if record.get("managed") is not True:
                return False
            if Path(record.get("workspace", "")).resolve() != WORKSPACE.resolve():
                return False
            config = record.get("launch_config") or load_config()
            stopped = _terminate_owned(record["pid"], record["created"], config, record["workspace"])
            if stopped:
                _atomic_json(CONTROL / "instance.json", {"status": "stopped"})
            return stopped
        except (OSError, ValueError, KeyError, TypeError):
            return False


def stop_workspace_backend(expected, *, expected_kfps_root):
    """Release an admitted backend after its documents close, never another host."""
    if (not isinstance(expected, dict) or expected.get('managed') is not True
            or type(expected.get('pid')) is not int or expected['pid'] <= 0
            or type(expected.get('created')) not in (int, float)
            or not math.isfinite(expected['created']) or expected['created'] <= 0
            or not isinstance(expected.get('workspace'), str)):
        return 'not-owned'
    try:
        if Path(expected['workspace']).resolve() != WORKSPACE.resolve():
            return 'not-owned'
        with _launch_lock(5):
            try:
                saved = _read_json(CONTROL / 'instance.json', 65536)
            except FileNotFoundError:
                return 'gone'
            if (saved.get('managed') is not True or type(saved.get('pid')) is not int
                    or saved['pid'] != expected['pid'] or saved.get('created') != expected['created']
                    or Path(saved.get('workspace', '')).resolve() != WORKSPACE.resolve()):
                return 'not-owned'
            if not _registration_alive(saved):
                return 'gone'
            # The game setting may have changed since launch. Verify the actual
            # registered inputs, not the configuration of a hypothetical new server.
            config = validate_config(saved.get('launch_config'), expected_kfps_root)
            def ready():
                return _ready_record(WORKSPACE / 'server-info.json', config,
                                     managed=True, created=expected['created'])
            current = ready()
            if current is None:
                return 'unavailable'
            if current.get('chrome_exposed') is not False:
                return 'shared'
            window = _window_module()
            try:
                with window.native_admission(current['url']):
                    # Chrome admission uses this same lease; recheck after taking
                    # it so a just-opened Chrome window cannot be terminated.
                    current = ready()
                    if current is None:
                        return 'unavailable'
                    if current.get('chrome_exposed') is not False:
                        return 'shared'
                    if current.get('pid') != expected['pid'] or current.get('created') != expected['created']:
                        return 'not-owned'
                    if not _terminate_owned(expected['pid'], expected['created'], config, saved['workspace'], include_children=False):
                        return 'failed'
                    _atomic_json(CONTROL / 'instance.json', {'status': 'stopped'})
                    return 'stopped'
            except RuntimeError:
                return 'in-use'
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, psutil.Error):
        return 'unavailable'


def chrome_path():
    from_root = [Path(os.environ.get(key, "C:/missing")) / "Google/Chrome/Application/chrome.exe"
                 for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for candidate in from_root:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("Chrome is selected for Livery Studio but was not found. Install Chrome from KFPS Settings, or turn off the Studio Chrome toggle to use the native window.")


def _window_module():
    path = Path(__file__).with_name("studio_window.py")
    spec = importlib.util.spec_from_file_location("_kfps_studio_window", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def window_preflight(expected_kfps_root=None):
    config = load_config(expected_kfps_root)
    window = _window_module()
    if window.use_chrome(config["kfpsRoot"]):
        chrome_path()
    else:
        window.native_preflight(config)
    return config


def open_studio_window(url, *, cancelled=None):
    base, separator, fragment = url.partition("#")
    validate_url(base)
    if separator and not re.fullmatch(r"(?:vinyl|layout|project)=[a-f0-9]{32}", fragment):
        raise ValueError("Invalid Studio vinyl handoff.")
    if os.environ.get("KFPS_LIVERY_NO_OPEN") == "1":
        return False
    _check_cancel(cancelled)
    config = window_preflight()
    window = _window_module()
    if not window.use_chrome(config["kfpsRoot"]):
        window.open_native(url, config, cancelled=cancelled)
        return True
    editor_source = str(Path(config["kfpsRoot"]) / "KFPS.Editor/src")
    if editor_source not in sys.path:
        sys.path.insert(0, editor_source)
    # Do not introduce a browser into a backend while a native document owns it.
    with window.native_admission(url):
        _check_cancel(cancelled)
        _mark_chrome_exposed(base)
        _check_cancel(cancelled)
        return _open_chrome_window(url)


def _mark_chrome_exposed(url):
    request = Request(validate_url(url) + "api/chrome-session", data=b"", method="POST")
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            body = response.read(1025)
        value = json.loads(body)
        if (len(body) > 1024 or not isinstance(value, dict) or set(value) != {"chrome_exposed"}
                or value["chrome_exposed"] is not True):
            raise ValueError("Invalid shared-host receipt.")
    except (OSError, ValueError):
        raise ValueError("Studio could not confirm shared-host protection. Save your work, then restart Studio. No Chrome window was opened.") from None


def _open_chrome_window(url):
    chrome = chrome_path()
    profile = _inside(LAB_ROOT / "runs/studio-browser", LAB_ROOT / "runs")
    # Leave initialized profiles' placement to Chrome, including already-running windows.
    initial_size = [] if (profile / "Local State").exists() or (profile / "Default").exists() else ["--window-size=1760,1040"]
    profile.mkdir(parents=True, exist_ok=True)
    temporary = _inside(profile / "tmp", profile)
    temporary.mkdir(exist_ok=True)
    environment = _window_module().isolated_environment(profile)
    environment.update(TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([str(chrome), f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                      "--disable-sync", "--disable-background-mode", *initial_size, f"--app={url}"],
                     cwd=profile, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, **options)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Explicit user action: open Studio in the host selected in KFPS Settings.")
    parser.add_argument("--stop", action="store_true", help="Stop only a server created by this supervisor.")
    args = parser.parse_args()
    try:
        if args.stop:
            print(json.dumps({"stopped": stop_owned()}))
        else:
            if args.open and os.environ.get("KFPS_LIVERY_NO_OPEN") != "1":
                window_preflight()
            result = ensure_ready()
            if args.open:
                result["opened"] = open_studio_window(result["url"])
            print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
