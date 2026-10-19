"""Explicit, revision-bound Studio source edits through the existing 2D editor."""
from __future__ import annotations

import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

LAB = Path(__file__).resolve().parents[2]
MAX_BYTES = 8 * 1024 * 1024
LIFETIME = 8 * 60 * 60
MAX_JOBS = 32
MAX_ACTIVE = 4
JOB_ID = re.compile(r"[a-f0-9]{32}")
IDENTITY = re.compile(r"[A-Za-z0-9_.-]{1,96}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
PROJECT_ID = "Studio-source.fabric-project.json"
DESCRIPTOR = "studio-source-edit.json"
# Parity-tested against the editor server's public customization contract.
CUSTOMIZATION_KEYS = frozenset({
    "kloudyFabricTheme", "kloudyFabricFavorites", "kloudyFabricFavoriteColors",
    "kloudyFabricLastColor", "kloudyFabricShortcuts", "kloudyFabricDockState",
    "kloudyFabricOverlayLayerMode", "kloudyFabricReuseLastFontSize",
    "kloudyFabricLastFontShapeTransform", "kloudyFabricTextVinylFont",
    "kloudyFabricTextVinylCustomFont", "kloudyFabricProjectSharingAcknowledged",
    "kloudyFabricOverlapCycle", "kloudyFabricLanguage", "kloudyFabricLanguageNoticeAcknowledged",
    "kloudyFabricEditorUpdateAcknowledged", "kloudyFabricUpdateBlinkAcknowledged",
    "kloudyFabricCenteredResize",
})
MAX_CUSTOMIZATION_FILE = 256 * 1024
MAX_PERSISTED_THEME_BYTES = 4 * MAX_CUSTOMIZATION_FILE + 4096
MAX_CUSTOM_THEMES = 256
MAX_CUSTOM_THEME_BYTES = 16 * 1024 * 1024


def _module(name, path=None):
    spec = importlib.util.spec_from_file_location("_studio_source_" + name, path or Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


model = _module("model")


class SourceEditError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


def _inside(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.resolve().is_relative_to(root):
        raise SourceEditError(422, "Source-edit storage is unavailable.")
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise SourceEditError(422, "Source-edit storage is redirected.")
        if part == root:
            break
    return path.resolve()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _customization_json(path, root, maximum=MAX_CUSTOMIZATION_FILE):
    path = _inside(path, root)
    try:
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
                raise ValueError("Not a bounded regular customization file.")
            body = stream.read(maximum + 1)
    except FileNotFoundError:
        return None, 0
    if len(body) > maximum:
        raise ValueError("Customization file exceeded its limit.")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate customization field.")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("Non-finite customization value.")

    value = json.loads(body, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError("Customization must be a JSON object.")
    return value, len(body)


def _inherit_customizations(kfps_root, runtime):
    """Snapshot only editor preferences/themes; later writes stay job-local."""
    root = Path(kfps_root).resolve()
    canonical = _inside(root / "runtime/fabric-editor", root)
    documents = []
    try:
        preferences, _ = _customization_json(canonical / "preferences.json", root)
        selected = set()
        if preferences is not None:
            if not isinstance(preferences, dict) or not isinstance(preferences.get("settings", {}), dict):
                raise ValueError("Invalid preferences object.")
            settings = {key: value for key, value in preferences.get("settings", {}).items() if key in CUSTOMIZATION_KEYS}
            if any(value is not None and (not isinstance(value, str) or len(value.encode("utf-8")) > 32768)
                   for value in settings.values()) or len(json.dumps(settings).encode("utf-8")) > 128 * 1024:
                raise ValueError("Invalid editor setting value.")
            payload = {"settings": settings}
            if "theme" in preferences:
                if not isinstance(preferences["theme"], str):
                    raise ValueError("Invalid selected theme.")
                payload["theme"] = preferences["theme"]
                selected.add(preferences["theme"])
            if settings.get("kloudyFabricTheme"):
                selected.add(settings["kloudyFabricTheme"])
            documents.append(("preferences.json", payload))

        theme_root = _inside(canonical / "themes", root)
        known = {"", "pastel", "dark", "blackout", "whiteout"}
        identifiers = set(known)
        selected_custom = selected - known
        total, count, skipped = 0, 0, 0
        if theme_root.exists():
            with os.scandir(theme_root) as entries:
                for entry in entries:
                    if not entry.name.lower().endswith(".json"):
                        continue
                    count += 1
                    if count > MAX_CUSTOM_THEMES:
                        raise ValueError("Too many custom themes.")
                    identifier = Path(entry.name).stem
                    try:
                        theme, size = _customization_json(theme_root / entry.name, root, MAX_PERSISTED_THEME_BYTES)
                        if not isinstance(theme, dict):
                            raise ValueError("Custom theme is unavailable.")
                        identifier = theme.get("id") or identifier
                        values = theme.get("values")
                        if (not isinstance(identifier, str) or not identifier or len(identifier) > 180
                                or any(character in identifier for character in '/\\\x00') or identifier in (".", "..")
                                or identifier in identifiers or theme.get("format", "kfps_fabric_editor_theme_v1") != "kfps_fabric_editor_theme_v1"
                                or not isinstance(values, dict) or any(not isinstance(value, str) for value in values.values())):
                            raise ValueError("Invalid custom theme definition.")
                    except (OSError, ValueError, RecursionError, UnicodeError):
                        if Path(entry.name).stem in selected_custom or isinstance(identifier, str) and identifier in selected_custom:
                            raise
                        skipped += 1
                        continue
                    total += size
                    if total > MAX_CUSTOM_THEME_BYTES:
                        raise ValueError("Custom theme collection is too large.")
                    identifiers.add(identifier)
                    if (identifier + ".json").casefold() == entry.name.casefold():
                        known.add(identifier)
                    documents.append(("themes/" + entry.name, theme))
        if selected - known:
            raise ValueError("Selected custom theme is missing.")
        marker, _ = _customization_json(canonical / "startup-help-confirmed.json", root, 4096)
        if marker is not None:
            if not isinstance(marker, dict) or marker.get("confirmed") is not True:
                raise ValueError("Invalid shortcuts guide acknowledgement.")
            documents.append(("startup-help-confirmed.json", {"confirmed": True}))

        # Validate the entire snapshot before writing any of it. Never touch the source.
        for relative, document in documents:
            destination = _inside(Path(runtime) / relative, runtime)
            if destination.exists():
                raise ValueError("Private editor customization already exists.")
        for relative, document in documents:
            _atomic(_inside(Path(runtime) / relative, runtime), document)
        return skipped
    except (OSError, ValueError, RecursionError, UnicodeError):
        raise SourceEditError(503, "Your editor customization could not be inherited. Check the normal editor's saved preferences and themes, then try again. No original settings were changed.") from None


def _binding(value):
    if not isinstance(value, dict) or set(value) != {"documentId", "sourceId", "sourceRevision"}:
        raise SourceEditError(422, "Expected document, source and revision identities.")
    if any(not isinstance(value[key], str) or not IDENTITY.fullmatch(value[key]) for key in ("documentId", "sourceId")):
        raise SourceEditError(422, "Invalid source-edit identity.")
    if type(value["sourceRevision"]) is not int or not 0 <= value["sourceRevision"] <= 9007199254740991:
        raise SourceEditError(422, "Invalid source revision.")
    return dict(value)


def _source(value, resolve_resource):
    if not isinstance(value, dict) or set(value) != {"name", "shapes"}:
        raise SourceEditError(422, "Expected a native source name and shapes.")
    name = value["name"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or not name.isprintable():
        raise SourceEditError(422, "Source name must contain 1 to 120 printable characters.")
    try:
        shapes = model.validate_shapes({"shapes": value["shapes"]}, resolve_resource)
    except model.ValidationError as exc:
        raise SourceEditError(422, str(exc)) from None
    result = {"name": name.strip(), "shapes": shapes}
    if len(_json(result)) > MAX_BYTES:
        raise SourceEditError(413, "Source edit exceeds 8 MiB.")
    return result


def _launch_editor(root, runtime, cancelled):
    """No alternate editor implementation: normal CLI, preference and baseline checks."""
    if cancelled.is_set():
        return
    baseline = _module("baseline", root / "KFPS.Editor/src/kfps_editor/baseline.py")
    args = ["--from-kfps", "--runtime-root", str(runtime), "--project-id", PROJECT_ID]
    command, environment = baseline.launch_command(root, root / "KFPS.Editor/editor.py", args,
                                                    fallback=root / "python/python.exe")
    environment = _module("studio_window").isolated_environment(runtime)
    for index, argument in enumerate(command):
        if argument.startswith("pycache_prefix="):
            command[index] = "pycache_prefix=" + str(runtime / "bytecode")
    if "-B" not in command:
        command[1:1] = ["-I", "-B"]
    with (runtime / "source-launch.log").open("ab") as stream:
        process = subprocess.Popen(command, cwd=root, env=environment, stdout=stream, stderr=stream,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # Never activate an existing user editor; each job owns a separate runtime.
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline and not cancelled.wait(.12):
        if process.poll() is not None:
            raise SourceEditError(503, "The 2D editor could not start. Check its selected host and installation.")
        try:
            marker = runtime / "desktop.json"
            if marker.stat().st_size > 16384:
                raise ValueError("Invalid readiness marker.")
            state = json.loads(marker.read_bytes())
            if state.get("pid") != process.pid:
                continue
            if state.get("state") == "ready":
                return
            if state.get("state") == "failed":
                raise SourceEditError(503, "The 2D editor could not load this source. Its local copy is retained.")
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    if not cancelled.is_set():
        raise SourceEditError(504, "The 2D editor is taking too long. Its local source copy remains available.")
    # Cancellation invalidates the return, not the independently editable document.


class SourceEditor:
    def __init__(self, session_root, kfps_root, *, launch=None, clock=time.time):
        self.root = _inside(Path(session_root) / "source-editor", LAB / "runs")
        self.kfps_root = Path(kfps_root).resolve()
        self.launch = launch or _launch_editor
        self.clock = clock
        self.lock = threading.RLock()
        self.jobs = {}
        self.closed = False

    def _record(self, identifier, token):
        if not isinstance(identifier, str) or not JOB_ID.fullmatch(identifier):
            raise SourceEditError(400, "Invalid source-edit identifier.")
        job = self.jobs.get(identifier)
        if job is None or not hmac.compare_digest(job["session"], token):
            raise SourceEditError(404, "Source edit is unavailable in this session.")
        if self.clock() >= job["expiresAt"] and job["status"] not in ("cancelled", "stale", "expired"):
            job["status"] = "expired"
            job["cancel"].set()
        return job

    def _usable(self, job):
        if job["status"] == "expired":
            raise SourceEditError(410, "Source edit expired. Start a new edit from the Studio.")
        if self.closed or job["status"] in ("cancelled", "stale", "failed"):
            raise SourceEditError(409, "Source edit is no longer active. The Studio layout was not changed.")

    def _view(self, job):
        return {"id": job["id"], "status": job["status"], **job["binding"], "name": job["source"]["name"],
                "shapeCount": len((job.get("result") or job["source"])["shapes"]), "expiresAt": job["expiresAt"],
                **({"error": job["error"]} if "error" in job else {}),
                **({"customizationWarnings": job["customizationWarnings"]} if job.get("customizationWarnings") else {})}

    def start(self, value, token, url, resolve_resource):
        if not isinstance(value, dict) or set(value) != {"documentId", "sourceId", "sourceRevision", "source"}:
            raise SourceEditError(422, "Expected source and document revision identities.")
        binding = _binding({key: value[key] for key in ("documentId", "sourceId", "sourceRevision")})
        source = _source(value["source"], resolve_resource)
        with self.lock:
            if self.closed:
                raise SourceEditError(409, "The source editor session is closed.")
            active = []
            for identifier, existing in self.jobs.items():
                self._record(identifier, existing["session"])
                if existing["status"] in ("launching", "editing", "ready"):
                    active.append(existing)
            if len(self.jobs) >= MAX_JOBS:
                for identifier, existing in list(self.jobs.items()):
                    if existing["status"] not in ("launching", "editing", "ready") and not existing["thread"].is_alive():
                        del self.jobs[identifier]
                        break
            if len(self.jobs) >= MAX_JOBS or len(active) >= MAX_ACTIVE:
                raise SourceEditError(429, "Too many source edits are pending. Finish or cancel an existing edit.")
            if any(job["session"] == token and job["binding"]["documentId"] == binding["documentId"]
                   and job["binding"]["sourceId"] == binding["sourceId"] for job in active):
                raise SourceEditError(409, "This source already has a pending edit.")
            identifier = secrets.token_hex(16)
            runtime = _inside(self.root / identifier / "editor", self.root)
            secret = secrets.token_urlsafe(32)
            expires = self.clock() + LIFETIME
            descriptor = {"format": "kfps-studio-source-edit-v1", "jobId": identifier, "projectId": PROJECT_ID,
                          "returnUrl": url + "api/source-editor/" + identifier + "/return", "secret": secret,
                          "name": source["name"], "expiresAt": expires}
            _validate_descriptor(descriptor, runtime)
            customization_warnings = _inherit_customizations(self.kfps_root, runtime)
            _atomic(runtime / "projects" / PROJECT_ID, {"format": "kloudy_fabric_editor_project_v1",
                    "name": "Studio-source", "layer_count": len(source["shapes"]), "shapes": source["shapes"]})
            _atomic(runtime / DESCRIPTOR, descriptor)
            job = {"id": identifier, "session": token, "binding": binding, "source": source, "secret": secret,
                   "expiresAt": expires, "status": "launching", "runtime": runtime, "cancel": threading.Event(),
                   "customizationWarnings": customization_warnings}
            self.jobs[identifier] = job
            def run():
                try:
                    self.launch(self.kfps_root, runtime, job["cancel"])
                    with self.lock:
                        if job["status"] == "launching":
                            job["status"] = "editing"
                except Exception:
                    with self.lock:
                        if job["status"] == "launching":
                            job["status"] = "failed"
                            job["error"] = "The 2D editor could not become ready. Its local source copy is retained."
            job["thread"] = threading.Thread(target=run, daemon=True, name="studio-source-editor")
            job["thread"].start()
            return self._view(job)

    def poll(self, identifier, token):
        with self.lock:
            return self._view(self._record(identifier, token))

    def submit(self, identifier, token, secret, value, resolve_resource):
        with self.lock:
            job = self._record(identifier, token)
            if not isinstance(secret, str) or not hmac.compare_digest(job["secret"], secret):
                raise SourceEditError(403, "Source return authorization failed.")
            self._usable(job)
            source = _source({"name": job["source"]["name"], "shapes": value.get("shapes") if isinstance(value, dict) else None}, resolve_resource)
            if not isinstance(value, dict) or set(value) != {"shapes"}:
                raise SourceEditError(422, "Expected only native shapes.")
            if "result" in job:
                if job["result"] != source:
                    raise SourceEditError(409, "This edit was already returned. Start another edit for further changes.")
                return self._view(job)
            try:
                _atomic(job["runtime"].parent / "returned.json", source)
            except OSError:
                raise SourceEditError(503, "The returned source could not be stored. Keep the editor open and retry.") from None
            job["result"] = source
            job["status"] = "ready"
            return self._view(job)

    def take(self, identifier, token, value):
        binding = _binding(value)
        with self.lock:
            job = self._record(identifier, token)
            self._usable(job)
            if binding != job["binding"]:
                raise SourceEditError(409, "The Studio document or source revision changed. Returned artwork was not applied.")
            if job["status"] not in ("ready", "taken"):
                raise SourceEditError(409, "The source has not been returned from the editor yet.")
            job["status"] = "taken"
            return {**self._view(job), "source": job["result"]}

    def cancel(self, identifier, token):
        with self.lock:
            job = self._record(identifier, token)
            if job["status"] not in ("expired", "stale"):
                job["status"] = "cancelled"
            job["cancel"].set()
            return self._view(job)

    def invalidate(self, token):
        with self.lock:
            for job in self.jobs.values():
                if job["session"] == token:
                    job["status"] = "stale"
                    job["cancel"].set()

    def close(self):
        with self.lock:
            self.closed = True
            jobs = list(self.jobs.values())
            for job in jobs:
                job["cancel"].set()
        deadline = time.monotonic() + 2
        for job in jobs:
            job["thread"].join(timeout=max(0, deadline - time.monotonic()))


def _validate_descriptor(value, runtime):
    if not isinstance(value, dict) or set(value) != {"format", "jobId", "projectId", "returnUrl", "secret", "name", "expiresAt"}:
        raise SourceEditError(422, "Invalid source edit context.")
    if (value["format"] != "kfps-studio-source-edit-v1" or value["projectId"] != PROJECT_ID
            or not isinstance(value["jobId"], str) or not JOB_ID.fullmatch(value["jobId"])
            or not isinstance(value["secret"], str) or not TOKEN.fullmatch(value["secret"])
            or type(value["expiresAt"]) not in (int, float)
            or not time.time() - LIFETIME <= value["expiresAt"] <= time.time() + LIFETIME + 60):
        raise SourceEditError(422, "Invalid source edit context.")
    runtime = _inside(runtime, LAB / "runs")
    if runtime.name != "editor" or runtime.parent.name != value["jobId"] or runtime.parent.parent.name != "source-editor":
        raise SourceEditError(422, "Source edit context is outside its private runtime.")
    if not isinstance(value["name"], str) or not 1 <= len(value["name"]) <= 120 or not value["name"].isprintable():
        raise SourceEditError(422, "Invalid source edit name.")
    if not isinstance(value["returnUrl"], str):
        raise SourceEditError(422, "Source return address is invalid.")
    try:
        url = urlsplit(value["returnUrl"])
        port = url.port
    except ValueError:
        raise SourceEditError(422, "Source return address is invalid.") from None
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not port or url.username or url.password
            or url.query or url.fragment or not re.fullmatch(r"/[A-Za-z0-9_-]{43}/api/source-editor/" + value["jobId"] + r"/return", url.path)
            or url.netloc != "127.0.0.1:" + str(url.port)):
        raise SourceEditError(422, "Source return address is invalid.")
    return value


def editor_context(runtime, *, private=False):
    path = Path(runtime) / DESCRIPTOR
    if not path.exists():
        return None
    path = _inside(path, LAB / "runs")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 16384:
            raise SourceEditError(422, "Invalid source edit context file.")
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise SourceEditError(422, "Invalid source edit context file.")
    value = _validate_descriptor(model.decode_json(raw), Path(runtime))
    if value["expiresAt"] <= time.time():
        raise SourceEditError(410, "Source edit expired. Open it again from Studio.")
    return value if private else {key: value[key] for key in ("jobId", "projectId", "name", "expiresAt")}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def editor_return(runtime, value):
    context = editor_context(runtime, private=True)
    if context is None:
        raise SourceEditError(404, "This editor was not opened from a Studio source.")
    if (not isinstance(value, dict) or set(value) != {"jobId", "projectId", "shapes"}
            or value["jobId"] != context["jobId"] or value["projectId"] != context["projectId"]):
        raise SourceEditError(409, "The editor source identity changed.")
    body = _json({"shapes": value["shapes"]})
    if len(body) > MAX_BYTES:
        raise SourceEditError(413, "Source edit exceeds 8 MiB.")
    request = Request(context["returnUrl"], data=body, headers={"Content-Type": "application/json",
                      "X-KFPS-Source-Return": context["secret"]})
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=10) as response:
            raw = response.read(16385)
    except HTTPError as exc:
        status = exc.code if exc.code in (403, 404, 409, 410, 413, 422, 503) else 502
        raise SourceEditError(status, "Studio could not accept this return. Keep the editor copy and check the pending edit in Studio.") from None
    except OSError:
        raise SourceEditError(503, "Studio is unavailable. Your editor copy remains unchanged.") from None
    if len(raw) > 16384:
        raise SourceEditError(502, "Studio returned invalid edit status.")
    result = model.decode_json(raw)
    if not isinstance(result, dict) or result.get("id") != context["jobId"] or result.get("status") not in ("ready", "taken"):
        raise SourceEditError(502, "Studio returned invalid edit status.")
    return {"status": "returned", "message": "Returned to Studio. Choose which instances to update there."}
