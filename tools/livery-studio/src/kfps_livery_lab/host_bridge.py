"""Small transferable boundary shared by the native app and both editor hosts."""
from __future__ import annotations

import importlib.util
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
from urllib.error import HTTPError
from urllib.request import Request

LAB_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_ROOT = LAB_ROOT / "runs/host-handoffs"
MAX_BYTES = 8 * 1024 * 1024
MAX_HANDOFFS = 64
HANDOFF_LIFETIME = 24 * 60 * 60
HANDOFF_ID = re.compile(r"[a-f0-9]{32}")


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


def _handoff_root():
    path = launcher._inside(HANDOFF_ROOT, LAB_ROOT / "runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_request(value):
    if not isinstance(value, dict) or set(value) - {"name", "vinyl", "ui_theme"}:
        raise ValueError("Studio launch accepts a vinyl, display name and resolved theme only.")
    name = value.get("name", "Editor vinyl")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(char) < 32 for char in name):
        raise ValueError("Vinyl name must contain 1 to 120 printable characters.")
    vinyl = value.get("vinyl")
    context = {"ui_theme": themes.validate_theme(value["ui_theme"])} if "ui_theme" in value else {}
    if vinyl is None:
        return {"name": name.strip(), "vinyl": None, **context}
    # Resource loading happens in the exact native renderer at import time. Here
    # the shared validator strips metadata and rejects malformed transforms.
    shapes = model.validate_shapes(vinyl, lambda kind: True)
    return {"name": name.strip(), "vinyl": {"shapes": shapes}, **context}


def stage_handoff(request):
    request = validate_request(request)
    if request["vinyl"] is None:
        return None
    with launcher._launch_lock(5):
        return _stage_validated_handoff(request)


def _stage_validated_handoff(request):
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
        raise ValueError("Studio has too many pending vinyl transfers. Import the saved JSON directly for now.")
    identifier = secrets.token_hex(16)
    envelope = {"format": "kfps-studio-host-vinyl-v1", "created": time.time(),
                "name": request["name"], "shapes": request["vinyl"]["shapes"]}
    body = json.dumps(envelope, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_BYTES:
        raise ValueError("Vinyl transfer exceeds 8 MiB.")
    path = launcher._inside(root / (identifier + ".json"), root)
    with path.open("xb") as output:
        output.write(body)
    return identifier


def read_handoff(identifier, *, resolve_resource=None):
    if not isinstance(identifier, str) or not HANDOFF_ID.fullmatch(identifier):
        raise HandoffError(400, "Invalid vinyl transfer identifier.")
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
            if metadata.st_size > MAX_BYTES:
                raise HandoffError(413, "Vinyl transfer exceeds 8 MiB.")
            body = source.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise HandoffError(413, "Vinyl transfer exceeds 8 MiB.")
        envelope = model.decode_json(body)
        if (not isinstance(envelope, dict) or set(envelope) != {"format", "created", "name", "shapes"}
                or envelope["format"] != "kfps-studio-host-vinyl-v1"):
            raise ValueError("Invalid envelope.")
        created = envelope["created"]
        if type(created) not in (int, float) or not math.isfinite(created):
            raise ValueError("Invalid creation time.")
        age = time.time() - created
        if age < 0:
            raise ValueError("Future creation time.")
        if age > HANDOFF_LIFETIME:
            raise HandoffError(410, "Vinyl transfer has expired. Send it from the editor again.")
        request = validate_request({"name": envelope["name"], "vinyl": {"shapes": envelope["shapes"]}})
        shapes = request["vinyl"]["shapes"]
        if resolve_resource is not None:
            shapes = model.validate_shapes({"shapes": shapes}, lru_cache(maxsize=model.MAX_SHAPES)(resolve_resource))
        return {"name": request["name"], "shapes": shapes}
    except HandoffError:
        raise
    except FileNotFoundError:
        raise HandoffError(404, "Vinyl transfer was not found. Send it from the editor again.") from None
    except (OSError, ValueError, OverflowError, RecursionError):
        raise HandoffError(422, "Vinyl transfer is invalid or unavailable. Send it from the editor again.") from None


def launch_from_host(kfps_root, request=None, *, open_window=False, cancelled=None):
    request = validate_request({} if request is None else request)
    # A missing selected host must not leave an expensive prepared backend behind.
    if open_window and launcher.os.environ.get("KFPS_LIVERY_NO_OPEN") != "1":
        launcher.window_preflight(kfps_root)
    result = launcher.ensure_ready(expected_kfps_root=kfps_root, cancelled=cancelled)
    launcher._check_cancel(cancelled)
    if "ui_theme" in request:
        # A car commit may rotate the token between readiness and this request.
        for attempt in range(2):
            try:
                _publish_theme(result, request["ui_theme"])
                break
            except HTTPError as exc:
                if exc.code != 404 or attempt:
                    raise ValueError("Studio could not apply the host theme. Launch it again.") from None
                launcher._check_cancel(cancelled)
                result = launcher.ensure_ready(expected_kfps_root=kfps_root, cancelled=cancelled)
    result = dict(result, transferred=False, opened=False)
    if request["vinyl"] is not None and result.get("host_vinyl_handoff"):
        identifier = stage_handoff(request)
        result["url"] += "#vinyl=" + identifier
        result["transferred"] = True
    if open_window:
        launcher._check_cancel(cancelled)
        result["opened"] = launcher.open_studio_window(result["url"], cancelled=cancelled)
    result["message"] = ("Livery Studio is ready. Your vinyl was sent to the Studio."
                         if result["transferred"] else "Livery Studio is ready.")
    if request["vinyl"] is not None and not result["transferred"]:
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
