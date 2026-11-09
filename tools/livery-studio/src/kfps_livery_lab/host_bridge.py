"""Small transferable boundary shared by the native app and both editor hosts."""
from __future__ import annotations

from contextlib import nullcontext
import importlib.util
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request

LAB_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_ROOT = LAB_ROOT / "runs/host-handoffs"
MAX_BYTES = 8 * 1024 * 1024
MAX_LAYOUT_BYTES = 32 * 1024 * 1024
MAX_HANDOFFS = 64
HANDOFF_LIFETIME = 24 * 60 * 60
HANDOFF_ID = re.compile(r"[a-f0-9]{32}")
CHROME_PACKAGE_CAR_MESSAGE = (
    "In Chrome, save your work and choose this package's car in Studio before opening it. "
    "Automatic car switching could interrupt another Studio window.")
SHARED_PACKAGE_CAR_MESSAGE = (
    "Save your work and choose this package's car in the existing Studio before opening it. "
    "This running Studio may have another open page, so automatic car switching was blocked. "
    "Existing documents have not been changed.")


class HandoffError(ValueError):
    """Bounded public error; never carry filesystem exception text to HTTP."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _local_module(name):
    spec = importlib.util.spec_from_file_location("_kfps_studio_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = _local_module("launcher")
model = _local_module("model")
themes = _local_module("theme_context")


def _package_handoff():
    # Native EditorService loads this bridge directly by filename. Add only the
    # fixed adjacent package location; never a caller-supplied import path.
    source = str(Path(__file__).resolve().parents[1])
    if source not in sys.path:
        sys.path.insert(0, source)
    from kfps_livery_lab import package_handoff
    return package_handoff


def request_for_package(path, expected=""):
    return validate_request(_package_handoff().request_for_package(path, _handoff_root(), expected=expected))


def _project_handoff():
    _package_handoff()
    from kfps_livery_lab import project_handoff
    return project_handoff


def request_for_stock(identity):
    return validate_request(_project_handoff().request_for_stock(identity))


def request_for_garage_artwork(identity, snapshot, path, kind, expected=""):
    package = _package_handoff()
    from kfps_livery_lab.garage_build import validate_build
    snapshot = validate_build(snapshot)
    identity = _project_handoff().request_for_stock(identity)['project']['vehicle']
    if kind == 'package':
        request = request_for_package(path, expected=expected)
    elif kind == 'save':
        request = package.request_for_save(path, identity, expected=expected)
    else:
        raise ValueError('Choose package or save artwork from the Garage catalogue.')
    if request['layout']['vehicle'] != identity:
        raise ValueError('The selected artwork belongs to a different car model.')
    request['layout']['garage_build'] = snapshot
    return validate_request(request)


def _handoff_root():
    path = launcher._inside(HANDOFF_ROOT, LAB_ROOT / "runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_request(value):
    if not isinstance(value, dict) or set(value) - {"name", "vinyl", "layout", "project", "ui_theme"}:
        raise ValueError("Studio launch accepts artwork, a display name and a resolved theme only.")
    name = value.get("name", "Editor vinyl")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(char) < 32 for char in name):
        raise ValueError("Vinyl name must contain 1 to 120 printable characters.")
    vinyl = value.get("vinyl")
    context = {"ui_theme": themes.validate_theme(value["ui_theme"])} if "ui_theme" in value else {}
    if len(set(value) & {'vinyl', 'layout', 'project'}) > 1:
        raise ValueError('Send one vinyl, package artwork or full Studio project, not a mixture.')
    if "project" in value:
        _project_handoff()._no_paths(name)
        return {"name": name.strip(), "project": _project_handoff().validate_project(value["project"]), **context}
    if "layout" in value:
        if "vinyl" in value:
            raise ValueError("Send either a vinyl or package artwork, not both.")
        return {"name": name.strip(), "layout": _package_handoff().validate_layout(value["layout"]), **context}
    if vinyl is None:
        return {"name": name.strip(), "vinyl": None, **context}
    # Resource loading happens in the exact native renderer at import time. Here
    # the shared validator strips metadata and rejects malformed transforms.
    shapes = model.validate_shapes(vinyl, lambda kind: True)
    return {"name": name.strip(), "vinyl": {"shapes": shapes}, **context}


def stage_handoff(request, *, startup_session=None):
    request = validate_request(request)
    if startup_session is not None:
        if not ({"layout", "project"} & set(request)):
            raise ValueError("Only package artwork can carry startup switch permission.")
        launcher.validate_url(startup_session)
    if request.get("vinyl") is None and not ({"layout", "project"} & set(request)):
        return None
    with launcher._launch_lock(5):
        return _stage_validated_handoff(request, startup_session=startup_session)


def _stage_validated_handoff(request, *, startup_session=None):
    root = _handoff_root()
    active = 0
    for file in root.glob("*.json"):
        if not re.fullmatch(r"[a-f0-9]{32}\.json", file.name):
            continue
        path = launcher._inside(file, root)
        if time.time() - path.stat().st_mtime > HANDOFF_LIFETIME:
            path.unlink(missing_ok=True)
        else:
            active += 1
    if active >= MAX_HANDOFFS:
        raise ValueError("Studio has too many pending artwork transfers. Retry after older transfers expire.")
    identifier = secrets.token_hex(16)
    kind = 'project' if 'project' in request else 'layout' if 'layout' in request else 'vinyl'
    layout = kind != 'vinyl'
    envelope = {"format": f"kfps-studio-host-{kind}-v1",
                "created": time.time(), "name": request["name"],
                **({kind: request[kind]} if layout else {"shapes": request["vinyl"]["shapes"]})}
    if startup_session is not None:
        envelope["startup_session"] = startup_session
    body = json.dumps(envelope, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(body) > (MAX_LAYOUT_BYTES if layout else MAX_BYTES):
        raise ValueError("Artwork transfer exceeds its size limit.")
    path = launcher._inside(root / (identifier + ".json"), root)
    with path.open("xb") as output:
        output.write(body)
    return identifier


def read_handoff(identifier, *, resolve_resource=None):
    return _read_handoff(identifier, resolve_resource=resolve_resource)


def read_layout_handoff(identifier, *, resolve_resource=None):
    return _read_handoff(identifier, layout=True, resolve_resource=resolve_resource)


def read_project_handoff(identifier, *, resolve_resource=None):
    return _read_handoff(identifier, layout=True, project=True, resolve_resource=resolve_resource)


def _read_handoff(identifier, *, layout=False, project=False, resolve_resource=None):
    maximum = MAX_LAYOUT_BYTES if layout else MAX_BYTES
    label = "Studio project" if project else "Package artwork" if layout else "Vinyl"
    resend = "Open it from Liveries again." if layout else "Send it from the editor again."
    if not isinstance(identifier, str) or not HANDOFF_ID.fullmatch(identifier):
        raise HandoffError(400, f"Invalid {label.lower()} transfer identifier.")
    try:
        # GET must neither create an inbox nor follow redirected files out of it.
        root = launcher._inside(HANDOFF_ROOT, LAB_ROOT / "runs")
        candidate = root / (identifier + ".json")
        for path in (HANDOFF_ROOT, candidate):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Redirected inbox entry.")
        path = launcher._inside(candidate, root)
        with path.open("rb") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Not a private regular inbox file.")
            if metadata.st_size > maximum:
                raise HandoffError(413, f"{label} transfer exceeds {maximum // (1024 * 1024)} MiB.")
            body = source.read(maximum + 1)
        if len(body) > maximum:
            raise HandoffError(413, f"{label} transfer exceeds {maximum // (1024 * 1024)} MiB.")
        envelope = model.decode_json(body)
        key = "project" if project else "layout" if layout else "shapes"
        format_name = "kfps-studio-host-project-v1" if project else "kfps-studio-host-layout-v1" if layout else "kfps-studio-host-vinyl-v1"
        expected_keys = {"format", "created", "name", key}
        if layout and isinstance(envelope, dict) and "startup_session" in envelope:
            expected_keys.add("startup_session")
            launcher.validate_url(envelope["startup_session"])
        if (not isinstance(envelope, dict) or set(envelope) != expected_keys
                or envelope["format"] != format_name):
            raise ValueError("Invalid envelope.")
        created = envelope["created"]
        if type(created) not in (int, float) or not math.isfinite(created):
            raise ValueError("Invalid creation time.")
        age = time.time() - created
        if age < 0:
            raise ValueError("Future creation time.")
        if age > HANDOFF_LIFETIME:
            raise HandoffError(410, f"{label} transfer has expired. {resend}")
        if layout:
            request = validate_request({"name": envelope["name"], key: envelope[key]})
            if resolve_resource is not None:
                validator = _project_handoff().validate_project if project else _package_handoff().validate_layout
                request[key] = validator(request[key], lru_cache(maxsize=model.MAX_SHAPES)(resolve_resource))
            if "startup_session" in envelope:
                request["startup_session"] = envelope["startup_session"]
            return request
        request = validate_request({"name": envelope["name"], "vinyl": {"shapes": envelope["shapes"]}})
        shapes = request["vinyl"]["shapes"]
        if resolve_resource is not None:
            shapes = model.validate_shapes({"shapes": shapes}, lru_cache(maxsize=model.MAX_SHAPES)(resolve_resource))
        return {"name": request["name"], "shapes": shapes}
    except HandoffError:
        raise
    except FileNotFoundError:
        raise HandoffError(404, f"{label} transfer was not found. {resend}") from None
    except (OSError, ValueError, OverflowError, RecursionError):
        raise HandoffError(422, f"{label} transfer is invalid or unavailable. {resend}") from None


def _check_package_target(kfps_root, result, request, native_owner=None):
    kind = 'project' if 'project' in request else 'layout'
    if kind not in request:
        return
    if not result.get(f"host_{kind}_handoff"):
        label = 'Studio projects' if kind == 'project' else 'package artwork'
        raise ValueError(f"This Studio does not support {label}. Save your work, then restart Studio.")
    if "garage_build" in request[kind] and result.get("host_garage_build") is not True:
        raise ValueError("This Studio needs a restart before opening Garage builds. Save your work, then restart Studio.")
    window = launcher._window_module()
    chrome = window.use_chrome(kfps_root)
    owned = native_owner is not None and window.owns_native_url(native_owner, result["url"])
    shared = result.get("chrome_exposed") is not False
    if chrome or shared or (result.get("reused") is not False and not owned):
        # Readiness describes the server's car, not exclusive ownership of its pages.
        vehicle = result.get("vehicle")
        expected = request[kind]["vehicle"]
        if (not isinstance(vehicle, dict) or type(vehicle.get("car_id")) is not int
                or vehicle.get("car_id") != expected["car_id"]
                or vehicle.get("model_code") != expected["model_code"]):
            raise ValueError(CHROME_PACKAGE_CAR_MESSAGE if chrome else SHARED_PACKAGE_CAR_MESSAGE)
    return bool(owned and not chrome and not shared)


def _native_admission(kfps_root, result, native_owner):
    window = launcher._window_module()
    return (nullcontext() if window.use_chrome(kfps_root)
            else window.native_admission(result["url"], native_owner))


def launch_from_host(kfps_root, request=None, *, open_window=False, cancelled=None, native_owner=None, backend_ready=None):
    request = validate_request({} if request is None else request)
    # A missing selected host must not leave an expensive prepared backend behind.
    if open_window and launcher.os.environ.get("KFPS_LIVERY_NO_OPEN") != "1":
        launcher.window_preflight(kfps_root)
    kind = 'project' if 'project' in request else 'layout'
    initial = {"initial_vehicle": request[kind]["vehicle"]} if kind in request else {}
    result = launcher.ensure_ready(expected_kfps_root=kfps_root, cancelled=cancelled, **initial)
    if backend_ready is not None:
        backend_ready(result)
    launcher._check_cancel(cancelled)
    _check_package_target(kfps_root, result, request, native_owner)
    if "ui_theme" in request:
        # A car commit may rotate the token between readiness and this request.
        for attempt in range(2):
            try:
                with _native_admission(kfps_root, result, native_owner):
                    _publish_theme(result, request["ui_theme"])
                break
            except HTTPError as exc:
                if exc.code != 404 or attempt:
                    raise ValueError("Studio could not apply the host theme. Launch it again.") from None
                launcher._check_cancel(cancelled)
                result = launcher.ensure_ready(expected_kfps_root=kfps_root, cancelled=cancelled, **initial)
                if backend_ready is not None:
                    backend_ready(result)
                _check_package_target(kfps_root, result, request, native_owner)
    result = dict(result, transferred=False, opened=False)
    if kind in request:
        owned = _check_package_target(kfps_root, result, request, native_owner)
        with _native_admission(kfps_root, result, native_owner):
            identifier = (stage_handoff(request, startup_session=result["url"])
                          if owned else stage_handoff(request))
        result["url"] += "#" + kind + "=" + identifier
        result["transferred"] = True
    elif request["vinyl"] is not None and result.get("host_vinyl_handoff"):
        with _native_admission(kfps_root, result, native_owner):
            identifier = stage_handoff(request)
        result["url"] += "#vinyl=" + identifier
        result["transferred"] = True
    if open_window:
        launcher._check_cancel(cancelled)
        result["opened"] = launcher.open_studio_window(result["url"], cancelled=cancelled)
    result["message"] = ("Livery Studio is ready. Your vinyl was sent to the Studio."
                         if result["transferred"] else "Livery Studio is ready.")
    if 'project' in request:
        result['message'] = 'Studio project sent. The saved source is unchanged.'
    elif "layout" in request:
        result["message"] = ("Garage artwork and body sent to Studio. Original files and game saves are unchanged."
                             if request['layout'].get('garage_build') and request['layout']['vinyls'] else
                             "Package artwork sent to Studio. Body paint and materials are not imported; the source package is unchanged.")
    elif request["vinyl"] is not None and not result["transferred"]:
        result["message"] += " Use Add vinyl to import an exported JSON; this running Studio does not support direct transfer yet."
    return result


def _publish_theme(result, value):
    url = launcher.validate_url(result["url"])
    if not result.get("host_theme_handoff"):
        raise ValueError("This Studio does not support host theme transfer.")
    body = json.dumps(value, allow_nan=False).encode("utf-8")
    request = Request(url + "api/host-theme", data=body, headers={"Content-Type": "application/json"})
    opener = launcher.build_opener(launcher.ProxyHandler({}), launcher._NoRedirect())
    with opener.open(request, timeout=5) as response:
        content = response.read(themes.MAX_BYTES + 1)
    if len(content) > themes.MAX_BYTES or not isinstance(json.loads(content), dict):
        raise ValueError("Studio returned invalid theme metadata.")
