"""Token-scoped loopback API with car-managed projects and session-local host themes."""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import threading
import time
from urllib.parse import parse_qsl, unquote, urlsplit

from .host_bridge import HANDOFF_ID, HandoffError, read_handoff
from .car_workspace import CarError, CarWorkspace, ID as CAR_JOB_ID, prepared_assets
from .model import MAX_BODY_BYTES, NativeVinylRenderer, ValidationError, decode_json
from .prepare import LAB_ROOT, atomic_json, prepare_car, within, workspace_lock, load_baseline
from .theme_context import ThemeContext, MAX_BYTES as MAX_THEME_BYTES
from .source_editor import SourceEditor, SourceEditError, MAX_BYTES as MAX_SOURCE_EDIT_BYTES
from .recovery import RecoveryStore, RecoveryError, MAX_REQUEST_BYTES as MAX_RECOVERY_BYTES, ID as RECOVERY_ID
from .project_storage import ProjectStore, VinylLibrary, ID as PROJECT_ID
from .managed_recovery import CarRecoveryStore
from .storage_paths import StorageError
from .confirmation_preferences import ConfirmationPreferences, ConfirmationError, MAX_REQUEST_BYTES as MAX_CONFIRMATION_BYTES
from .language_preferences import LanguagePreferences, LanguageError, MAX_REQUEST_BYTES as MAX_LANGUAGE_BYTES
from .preview_preferences import PreviewPreferences, PreviewError, MAX_REQUEST_BYTES as MAX_PREVIEW_PREFERENCE_BYTES
from .save_codec import section_limit_policy
from .diagnostics import DiagnosticLog, application_version, request_action, MAX_BODY_BYTES as MAX_DIAGNOSTIC_BYTES

WEB_FILES = ("index.html", "editor.css", "viewer.css", "livery-scene.js", "livery-editor.mjs",
             "layout-model.mjs", "component-model.mjs", "surface-math.mjs", "surface-edit.mjs", "native-material.mjs",
             "native-texture-binding.mjs", "wheel-model.mjs", "theme-adapter.mjs", "icons.js", "LICENSE.lucide")
VENDOR_FILES = ("three/build/three.module.min.js", "three/build/three.core.min.js",
                "three/examples/jsm/loaders/GLTFLoader.js", "three/examples/jsm/controls/OrbitControls.js",
                "three/examples/jsm/utils/BufferGeometryUtils.js", "three/examples/jsm/utils/SkeletonUtils.js",
                "three/LICENSE")
OPTIONAL_WEB_FILES = ("authoring-model.mjs", "studio-tools.mjs", "mirror-links.mjs",
                      "recovery-ui.mjs", "inspection-tools.mjs", "action-confirmations.mjs", "confirmation-policy.mjs",
                      "i18n.mjs", "locales/en.mjs", "locales/ko.mjs", "locales/ja.mjs", "project-storage-ui.mjs", "diagnostics.mjs",
                      "preview-quality.mjs")
MAX_PROJECT_BYTES = 32 * 1024 * 1024
MAX_NATIVE_TEXTURE_BYTES = 80 * 1024 * 1024
# The qualified Studio client consumes validated #vinyl handoffs on startup/hashchange.
HOST_VINYL_HANDOFF_READY = True


def _read_native_texture(path, expected_hash):
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise ValueError("Invalid native texture hash.")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_NATIVE_TEXTURE_BYTES:
            raise ValueError("Invalid native texture size.")
        # Bound the actual read too: registration/stat may precede a file mutation.
        body = stream.read(info.st_size + 1)
    if len(body) != info.st_size or hashlib.sha256(body).hexdigest() != expected_hash:
        raise ValueError("Native texture integrity changed.")
    return body


class _BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    # Module imports arrive in bursts before the accept loop can dispatch workers.
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class LiveryLabServer:
    def __init__(self, prepared: dict, workspace: Path, kfps_root: Path, *, port: int = 0,
                 web_root: Path | None = None, renderer=None, export_service=None, game_root=None,
                 session_data_root=None, project_root=None, library_root=None, legacy_recovery_root=None,
                 release_announcement=None, activity_counter=None):
        self.prepared = prepared
        self.workspace = Path(workspace).resolve()
        self.token = secrets.token_urlsafe(32)
        self.renderer = renderer if renderer is not None else NativeVinylRenderer()
        self.export_service = export_service
        self.render_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.mask_pixels_lock = threading.Lock()
        self.mask_pixels_cache = {}
        self.session_workspace = self.workspace
        identity = hashlib.sha256(os.path.normcase(str(self.session_workspace)).encode("utf-8")).hexdigest()
        self.session_data_root = Path(session_data_root or LAB_ROOT / "runs/studio-session-data" / identity).resolve()
        if not self.session_data_root.is_relative_to((LAB_ROOT / "runs").resolve()):
            raise ValueError("Studio session data must stay under livery/runs.")
        self.source_editor = SourceEditor(self.session_data_root, kfps_root)
        storage_base = self.session_data_root if session_data_root is not None else Path(kfps_root)
        self.projects = ProjectStore(project_root or storage_base / "imgs" / "livery-projects")
        self.vinyl_library = VinylLibrary(library_root or storage_base / "imgs")
        recovery_root = legacy_recovery_root or (self.session_data_root / "recovery" if session_data_root is not None else LAB_ROOT / "recovery")
        self.recovery = CarRecoveryStore(self.projects, recovery_root)
        settings_root = self.session_data_root / "settings" if session_data_root is not None else LAB_ROOT / "settings"
        self.confirmations = ConfirmationPreferences(settings_root)
        self.language = LanguagePreferences(settings_root, kfps_root)
        self.preview_quality = PreviewPreferences(settings_root)
        self.theme_context = ThemeContext(self.session_workspace, kfps_root)
        self.release_announcement = release_announcement
        if self.release_announcement is None and (Path(kfps_root) / "tools/kfps_release_announcement.py").is_file():
            load_baseline(kfps_root)
            from tools.kfps_release_announcement import ReleaseAnnouncement
            self.release_announcement = ReleaseAnnouncement(kfps_root)
        self.activity_counter = activity_counter
        if (Path(kfps_root) / "tools/kfps_activity_host.py").is_file():
            load_baseline(kfps_root)
            from tools.kfps_activity_host import ActivityHost
            self.activity_counter = ActivityHost(kfps_root, counter=activity_counter)
        self.launch_archive = prepared.get("editor_config", {}).get("vehicle", {}).get("archive_name")
        self.car_workspace = CarWorkspace(workspace, kfps_root, game_root) if game_root is not None else None
        self.static = {}
        web = (web_root or LAB_ROOT / "src" / "web").resolve()
        vendor = (Path(kfps_root) / "tools" / "livery-inspector" / "vendor").resolve()
        for name in WEB_FILES:
            self.static[name] = (within(web / name, web), web)
        for name in OPTIONAL_WEB_FILES:
            if (web / name).is_file():
                self.static[name] = (within(web / name, web), web)
        for name in VENDOR_FILES:
            self.static["vendor/" + name] = (within(vendor / name, vendor), vendor)
        announcement_web = Path(kfps_root) / "KFPS.Editor/web"
        for name in ("release-announcement.js", "release-announcement.css", "activity-client.js"):
            if (announcement_web / name).is_file():
                self.static[name] = (within(announcement_web / name, announcement_web), announcement_web)
        self.assets = prepared_assets(prepared, self.workspace)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def do_GET(self):
                owner.handle(self)

            def do_POST(self):
                owner.handle(self)

            def do_OPTIONS(self):
                owner.reply(self, 405, {"error": "Method not allowed."})

            def log_message(self, *_args):
                pass

        self.httpd = _BoundedHTTPServer(("127.0.0.1", port), Handler)
        self.thread = None
        self.diagnostics = DiagnosticLog()
        self.diagnostic_version = application_version(kfps_root)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.httpd.server_port}"

    @property
    def url(self):
        return f"{self.origin}/{self.token}/"

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
            self.thread.start()
            version = {"app_version": self.diagnostic_version} if self.diagnostic_version else {}
            self.diagnostics.record("host", host="backend", ready=True, **version)
        return self.url

    def close(self):
        if self.activity_counter is not None:
            self.activity_counter.stop()
        try:
            try:
                self.source_editor.close()
            finally:
                if self.car_workspace is not None:
                    self.car_workspace.close()
        finally:
            try:
                if self.thread is not None:
                    self.httpd.shutdown()
                    self.thread.join(timeout=3)
            finally:
                self.thread = None
                self.httpd.server_close()
                if self.release_announcement is not None:
                    self.release_announcement.close()
                self.diagnostics.record("closed", host="backend")
                self.diagnostics.close()

    def _activity_ready_request(self, request, target, token):
        if target.query or target.fragment or target.path != f"/{token}/api/activity-ready":
            return self.reply(request, 404, {"error": "Unknown activity route."})
        if request.command != "POST":
            return self.reply(request, 405, {"error": "Method not allowed."})
        if (request.headers.get_all("Content-Length", []) != ["2"]
                or request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding")
                or request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"):
            return self.reply(request, 400, {"error": "Invalid activity readiness request."})
        request.connection.settimeout(3)
        raw = request.rfile.read(2)
        request.body_consumed = True
        if raw != b"{}":
            return self.reply(request, 400, {"error": "Invalid activity readiness request."})
        with self.state_lock:
            if token != self.token:
                return self.reply(request, 404, {"error": "Unknown session."})
            if self.activity_counter is not None:
                self.activity_counter.start()
        return self.reply(request, 200, {"ok": True})

    def _release_announcement_request(self, request, target, token):
        if target.query or target.fragment or target.path != f"/{token}/api/release-announcement":
            return self.reply(request, 404, {"error": "Unknown release notice route."})
        if request.command != "POST":
            return self.reply(request, 405, {"error": "Method not allowed."})
        lengths = request.headers.get_all("Content-Length", [])
        if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 4
                or not 0 < int(lengths[0]) <= 1024 or request.headers.get("Transfer-Encoding")
                or request.headers.get("Content-Encoding")
                or request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"):
            return self.reply(request, 400, {"error": "Invalid release notice request."})
        request.connection.settimeout(3)
        raw = request.rfile.read(int(lengths[0]))
        request.body_consumed = True
        if len(raw) != int(lengths[0]):
            return self.reply(request, 400, {"error": "Truncated release notice request."})
        try:
            body = decode_json(raw)
            with self.state_lock:
                if token != self.token:
                    return self.reply(request, 404, {"error": "Unknown session."})
                result = (self.release_announcement.dispatch(body) if self.release_announcement is not None
                          else {"eligible": False})
            return self.reply(request, 200, result)
        except ValueError:
            return self.reply(request, 400, {"error": "Invalid release notice request."})

    def _diagnostic_request(self, request, target, token):
        if target.query or target.fragment or target.path != f"/{token}/api/diagnostics":
            return self.reply(request, 404, {"error": "Unknown diagnostic route."})
        if request.command == "GET":
            return self.reply(request, 200, self.diagnostics.report())
        if request.command != "POST":
            return self.reply(request, 405, {"error": "Method not allowed."})
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            return self.reply(request, 400, {"error": "Encoded diagnostics are not supported."})
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 8:
            return self.reply(request, 411, {"error": "One bounded Content-Length is required."})
        length = int(lengths[0])
        if length > MAX_DIAGNOSTIC_BYTES:
            return self.reply(request, 413, {"error": "Diagnostic request exceeds 8 KiB."})
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.reply(request, 415, {"error": "Content-Type must be application/json."})
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            return self.reply(request, 400, {"error": "Truncated diagnostic request."})
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                return self.reply(request, 404, {"error": "Unknown session."})
            accepted = self.diagnostics.accept(value)
        return self.reply(request, 200, {"accepted": accepted})

    def _activate_car(self, prepared, workspace, assets, expected_token):
        with self.state_lock:
            if self.token != expected_token:
                raise CarError(409, "The car session changed. Reload the Studio.")
            token = secrets.token_urlsafe(32)
            url = f"{self.origin}/{token}/"
            # Persist readiness before publishing; failed writes leave the old state usable.
            atomic_json(self.session_workspace / "server-info.json", {
                "status": "running", "url": url, "pid": os.getpid(),
                "vehicle": prepared["editor_config"]["vehicle"]})
            self.prepared, self.workspace, self.assets = prepared, workspace, assets
            self.mask_pixels_cache = {}
            self.export_service = None
            self.source_editor.invalidate(self.token)
            self.token = token
            return url

    def _source_editor_request(self, request, relative, target, token):
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise SourceEditError(400, "Invalid source-edit URL.")
        parts = relative.split("/")
        if len(parts) not in (2, 3, 4) or parts[:2] != ["api", "source-editor"]:
            raise SourceEditError(404, "Unknown source-edit API.")
        if request.command == "GET" and len(parts) == 3:
            with self.state_lock:
                if token != self.token:
                    raise SourceEditError(404, "Unknown session.")
                result = self.source_editor.poll(parts[2], token)
            return self.reply(request, 200, result)
        if request.command != "POST" or len(parts) == 3:
            raise SourceEditError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise SourceEditError(400, "Encoded source-edit bodies are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise SourceEditError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_SOURCE_EDIT_BYTES:
            raise SourceEditError(413, "Source edit exceeds 8 MiB.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise SourceEditError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise SourceEditError(400, "Truncated source-edit body.")
        value = decode_json(body)
        if not self.render_lock.acquire(blocking=False):
            raise SourceEditError(503, "A vinyl is rendering. Retry the source edit when it completes.")
        try:
            with self.state_lock:
                if token != self.token:
                    raise SourceEditError(404, "Unknown session.")
                if len(parts) == 2:
                    status, result = 202, self.source_editor.start(value, token, self.url, self.renderer._resource)
                elif parts[3] == "return":
                    secrets = request.headers.get_all("X-KFPS-Source-Return", [])
                    if len(secrets) != 1:
                        raise SourceEditError(403, "Source return authorization failed.")
                    status, result = 200, self.source_editor.submit(parts[2], token, secrets[0], value, self.renderer._resource)
                elif parts[3] == "take":
                    status, result = 200, self.source_editor.take(parts[2], token, value)
                elif parts[3] == "cancel" and isinstance(value, dict) and not value:
                    status, result = 200, self.source_editor.cancel(parts[2], token)
                else:
                    raise SourceEditError(422, "Invalid source-edit action.")
        finally:
            self.render_lock.release()
        return self.reply(request, status, result)

    def _confirmation_request(self, request, relative, target, token):
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise ConfirmationError(400, "Invalid confirmation URL.")
        if relative != "api/confirmations":
            raise ConfirmationError(404, "Unknown confirmation API.")
        if request.command == "GET":
            with self.state_lock:
                if token != self.token:
                    raise ConfirmationError(404, "Unknown session.")
                result = self.confirmations.get()
            return self.reply(request, 200, result)
        if request.command != "POST":
            raise ConfirmationError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise ConfirmationError(400, "Encoded confirmation requests are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise ConfirmationError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_CONFIRMATION_BYTES:
            raise ConfirmationError(413, "Confirmation request exceeds 1 KiB.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ConfirmationError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise ConfirmationError(400, "Truncated confirmation body.")
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                raise ConfirmationError(404, "Unknown session.")
            result = self.confirmations.update(value)
        return self.reply(request, 200, result)

    def _language_request(self, request, relative, target, token):
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise LanguageError(400, "Invalid language URL.")
        if relative != "api/language":
            raise LanguageError(404, "Unknown language API.")
        if request.command == "GET":
            with self.state_lock:
                if token != self.token:
                    raise LanguageError(404, "Unknown session.")
                result = self.language.get()
            return self.reply(request, 200, result)
        if request.command != "POST":
            raise LanguageError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise LanguageError(400, "Encoded language requests are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise LanguageError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_LANGUAGE_BYTES:
            raise LanguageError(413, "Language request exceeds 1 KiB.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise LanguageError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise LanguageError(400, "Truncated language body.")
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                raise LanguageError(404, "Unknown session.")
            result = self.language.update(value)
        return self.reply(request, 200, result)

    def _preview_quality_request(self, request, relative, target, token):
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise PreviewError(400, "Invalid preview-quality URL.")
        if relative != "api/preview-quality":
            raise PreviewError(404, "Unknown preview-quality API.")
        if request.command == "GET":
            with self.state_lock:
                if token != self.token:
                    raise PreviewError(404, "Unknown session.")
                result = self.preview_quality.get()
            return self.reply(request, 200, result)
        if request.command != "POST":
            raise PreviewError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise PreviewError(400, "Encoded preview-quality requests are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise PreviewError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_PREVIEW_PREFERENCE_BYTES:
            raise PreviewError(413, "Preview-quality request exceeds 1 KiB.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise PreviewError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise PreviewError(400, "Truncated preview-quality body.")
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                raise PreviewError(404, "Unknown session.")
            result = self.preview_quality.update(value)
        return self.reply(request, 200, result)

    def _recovery_request(self, request, relative, target, token):
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise RecoveryError(400, "Invalid recovery URL.")
        parts = relative.split("/")
        root = relative == "api/recovery"
        restore = (len(parts) == 4 and parts[:2] == ["api", "recovery"]
                   and RECOVERY_ID.fullmatch(parts[2]) and parts[3] == "restore")
        if not root and not restore:
            raise RecoveryError(404, "Unknown recovery API.")
        if request.command == "GET" and root:
            with self.state_lock:
                if token != self.token:
                    raise RecoveryError(404, "Unknown session.")
                result = self.recovery.list(self.prepared["editor_config"].get("vehicle"))
            return self.reply(request, 200, result)
        if request.command != "POST":
            raise RecoveryError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise RecoveryError(400, "Encoded recovery requests are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise RecoveryError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_RECOVERY_BYTES:
            raise RecoveryError(413, "Recovery request exceeds the layout size limit.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise RecoveryError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise RecoveryError(400, "Truncated recovery body.")
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                raise RecoveryError(404, "Unknown session.")
            vehicle = self.prepared["editor_config"].get("vehicle")
            result = (self.recovery.save(vehicle, value) if root else
                      self.recovery.prepare_restore(vehicle, parts[2], value))
        return self.reply(request, 200, result)

    @staticmethod
    def _storage_query(target, allowed):
        if target.fragment or len(target.query) > 4096:
            raise StorageError(400, "Invalid storage query.")
        try:
            pairs = parse_qsl(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=4, errors="strict")
        except (ValueError, UnicodeError) as exc:
            raise StorageError(400, "Invalid storage query.") from exc
        result = {}
        for key, value in pairs:
            if key not in allowed or key in result:
                raise StorageError(400, "Unknown or repeated storage parameter.")
            result[key] = value
        if "offset" in result:
            if not re.fullmatch(r"0|[1-9][0-9]{0,5}", result["offset"]):
                raise StorageError(422, "Invalid page offset.")
            result["offset"] = int(result["offset"])
        return result

    def _project_request(self, request, relative, target, token):
        if relative != target.path[len(token) + 2:]:
            raise StorageError(400, "Invalid project URL.")
        parts = relative.split("/")
        root = relative == "api/projects"
        item = len(parts) == 3 and parts[:2] == ["api", "projects"] and PROJECT_ID.fullmatch(parts[2])
        if not root and not item:
            raise StorageError(404, "Unknown project API.")
        query = self._storage_query(target, {"offset"} if root and request.command == "GET" else set())
        if request.command == "GET":
            with self.state_lock:
                if token != self.token:
                    raise StorageError(404, "Unknown session.")
                vehicle = self.prepared["editor_config"].get("vehicle")
                result = self.projects.list(vehicle, query.get("offset", 0)) if root else self.projects.open(vehicle, parts[2])
            return self.reply(request, 200, result)
        if request.command != "POST" or not root:
            raise StorageError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise StorageError(400, "Encoded project requests are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,10}", lengths[0]):
            raise StorageError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > MAX_RECOVERY_BYTES:
            raise StorageError(413, "Project request exceeds the layout size limit.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise StorageError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise StorageError(400, "Truncated project request.")
        value = decode_json(body)
        with self.state_lock:
            if token != self.token:
                raise StorageError(404, "Unknown session.")
            result = self.projects.save(self.prepared["editor_config"].get("vehicle"), value)
        return self.reply(request, 200, result)

    def _library_request(self, request, relative, target, token):
        if request.command != "GET":
            raise StorageError(405, "Method not allowed.")
        if relative != target.path[len(token) + 2:]:
            raise StorageError(400, "Invalid library URL.")
        if relative not in ("api/vinyl-library", "api/vinyl-library/file"):
            raise StorageError(404, "Unknown vinyl library API.")
        is_file = relative.endswith("/file")
        query = self._storage_query(target, {"path"} if is_file else {"path", "offset"})
        with self.state_lock:
            if token != self.token:
                raise StorageError(404, "Unknown session.")
            result = (self.vinyl_library.read(query.get("path")) if is_file else
                      self.vinyl_library.list(query.get("path", ""), query.get("offset", 0)))
        return self.reply(request, 200, result)

    def _car_request(self, request, relative, target, token, current_archive):
        manager = self.car_workspace
        if manager is None:
            return self.reply(request, 404, {"error": "Car selection is unavailable in this session."})
        if target.query or target.fragment or relative != target.path[len(token) + 2:]:
            raise CarError(400, "Invalid car selection URL.")
        parts = relative.split("/")
        if relative == "api/cars" and request.command == "GET":
            return self.reply(request, 200, manager.list(current_archive))
        if len(parts) not in (2, 3, 4) or parts[:2] != ["api", "car-switch"]:
            raise CarError(404, "Unknown car selection API.")
        if len(parts) > 2 and not CAR_JOB_ID.fullmatch(parts[2]):
            raise CarError(400, "Invalid car preparation identifier.")
        if request.command == "GET" and len(parts) == 3:
            return self.reply(request, 200, manager.poll(parts[2]))
        if request.command != "POST":
            raise CarError(405, "Method not allowed.")
        if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
            raise CarError(400, "Encoded request bodies are not supported.")
        lengths = request.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise CarError(411, "One Content-Length is required.")
        length = int(lengths[0])
        if length > 1024:
            raise CarError(413, "Car selection request is too large.")
        if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise CarError(415, "Content-Type must be application/json.")
        body = request.rfile.read(length)
        request.body_consumed = True
        if len(body) != length:
            raise CarError(400, "Truncated request body.")
        value = decode_json(body)
        # Serialize mutation with commit, then recheck a body delayed across rotation.
        # Keep manager -> state lock order identical to the activation callback.
        with manager.lock:
            with self.state_lock:
                if token != self.token:
                    raise CarError(404, "Unknown session.")
            if len(parts) == 2:
                if not isinstance(value, dict) or set(value) != {"carId"}:
                    raise CarError(422, "Choose one catalogue car ID.")
                return self.reply(request, 202, manager.start(value["carId"], current_archive))
            if len(parts) != 4 or value != {} or not isinstance(value, dict):
                raise CarError(422, "Expected an empty car action request.")
            if parts[3] == "cancel":
                return self.reply(request, 200, manager.cancel(parts[2]))
            if parts[3] == "commit":
                result = manager.commit(parts[2], lambda prepared, root, assets:
                                        self._activate_car(prepared, root, assets, token))
                return self.reply(request, 200, result)
            raise CarError(404, "Unknown car selection API.")

    def reply(self, request, status, data, mime="application/json; charset=utf-8"):
        action = getattr(request, "diagnostic_action", None)
        if action:
            fields = {"host": "backend", "action": action, "http_status": status,
                      "outcome": "ok" if status < 400 else "error",
                      "duration_ms": min(600000, max(0, (time.monotonic() - request.diagnostic_started) * 1000))}
            if status >= 400:
                fields["error_code"] = "http_5xx" if status >= 500 else "http_4xx"
            self.diagnostics.record("request", **fields)
        if not isinstance(data, bytes):
            data = json.dumps(data, allow_nan=False).encode("utf-8")
        request.send_response(status)
        for key, value in {"Content-Type": mime, "Content-Length": str(len(data)), "Cache-Control": "no-store",
                           "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Connection": "close",
                           "Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; font-src 'self'; style-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"}.items():
            request.send_header(key, value)
        request.end_headers()
        request.close_connection = True
        try:
            request.wfile.write(data)
            request.wfile.flush()
            # Windows can reset a connection with unread POST bytes, hiding the error response.
            # Send the response first, then drain only a bounded, declared body briefly.
            if request.command == "POST" and not getattr(request, "body_consumed", False):
                lengths = request.headers.get_all("Content-Length", [])
                if len(lengths) == 1 and lengths[0].isdigit() and 0 < int(lengths[0]) <= MAX_PROJECT_BYTES:
                    request.connection.shutdown(socket.SHUT_WR)
                    request.connection.settimeout(.2)
                    request.rfile.read(int(lengths[0]))
        except OSError:
            pass

    def handle(self, request):
        try:
            # Each request sees one immutable car binding even if commit rotates the session.
            with self.state_lock:
                token, prepared, workspace, assets, exporter = (self.token, self.prepared, self.workspace,
                                                               self.assets, self.export_service)
                mask_pixels_cache = self.mask_pixels_cache
            if request.headers.get_all("Host") != [self.origin.removeprefix("http://")]:
                return self.reply(request, 403, {"error": "Invalid Host."})
            origins = request.headers.get_all("Origin", [])
            if (origins and origins != [self.origin]) or request.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.reply(request, 403, {"error": "Invalid Origin."})
            target = urlsplit(request.path)
            if target.scheme or target.netloc or not target.path.startswith(f"/{token}/"):
                return self.reply(request, 404, {"error": "Unknown session."})
            relative = unquote(target.path[len(token) + 2:])
            request.diagnostic_started = time.monotonic()
            request.diagnostic_action = request_action(request.command, relative)
            if relative == "api/activity-ready":
                return self._activity_ready_request(request, target, token)
            if relative == "api/release-announcement":
                return self._release_announcement_request(request, target, token)
            if relative == "api/diagnostics":
                return self._diagnostic_request(request, target, token)
            if relative == "api/source-editor" or relative.startswith("api/source-editor/"):
                return self._source_editor_request(request, relative, target, token)
            if relative == "api/recovery" or relative.startswith("api/recovery/"):
                return self._recovery_request(request, relative, target, token)
            if relative == "api/projects" or relative.startswith("api/projects/"):
                return self._project_request(request, relative, target, token)
            if relative == "api/vinyl-library" or relative.startswith("api/vinyl-library/"):
                return self._library_request(request, relative, target, token)
            if relative == "api/confirmations" or relative.startswith("api/confirmations/"):
                return self._confirmation_request(request, relative, target, token)
            if relative == "api/language" or relative.startswith("api/language/"):
                return self._language_request(request, relative, target, token)
            if relative == "api/preview-quality" or relative.startswith("api/preview-quality/"):
                return self._preview_quality_request(request, relative, target, token)
            if relative in ("api/ui-theme", "api/host-theme") or relative.startswith("api/ui-font/"):
                if target.query or target.fragment or relative != target.path[len(token) + 2:]:
                    return self.reply(request, 404, {"error": "Theme resource is unavailable."})
                if relative == "api/ui-theme" and request.command == "GET":
                    return self.reply(request, 200, self.theme_context.effective())
                if relative.startswith("api/ui-font/") and request.command == "GET":
                    font = self.theme_context.font(relative[len("api/ui-font/"):])
                    if font is None:
                        return self.reply(request, 404, {"error": "Theme font is unavailable."})
                    return self.reply(request, 200, *font)
                if relative not in ("api/host-theme", "api/ui-theme") or request.command != "POST":
                    return self.reply(request, 405, {"error": "Method not allowed."})
                if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
                    return self.reply(request, 400, {"error": "Encoded request bodies are not supported."})
                lengths = request.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                    return self.reply(request, 411, {"error": "One Content-Length is required."})
                length = int(lengths[0])
                if length > MAX_THEME_BYTES:
                    return self.reply(request, 413, {"error": "Theme request exceeds 32 KiB."})
                if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    return self.reply(request, 415, {"error": "Content-Type must be application/json."})
                body = request.rfile.read(length)
                request.body_consumed = True
                if len(body) != length:
                    return self.reply(request, 400, {"error": "Truncated request body."})
                value = decode_json(body)
                with self.state_lock:
                    if token != self.token:
                        return self.reply(request, 404, {"error": "Unknown session."})
                    try:
                        if relative == "api/ui-theme":
                            if not isinstance(value, dict) or set(value) != {"theme"}:
                                raise ValueError("Expected one Studio theme selection.")
                            result = self.theme_context.select(value["theme"])
                            result["ui_theme_persistence"] = True
                        else:
                            result = self.theme_context.update(value)
                    except (OSError, ValueError):
                        return self.reply(request, 422, {"error": "Invalid theme or unavailable bundled font."})
                return self.reply(request, 200, result)
            if relative.startswith("api/native-texture/"):
                if request.command != "GET":
                    return self.reply(request, 405, {"error": "Method not allowed."})
                key = relative[len("api/native-texture/"):]
                if (not re.fullmatch(r"[a-f0-9]{64}", key) or target.query or target.fragment
                        or relative != target.path[len(token) + 2:] or relative not in assets):
                    return self.reply(request, 404, {"error": "Native texture is not available."})
                path, mime = assets[relative]
                name = prepared["files"]["native_textures"][key]
                expected_hash = prepared["file_sha256"].get(name)
                body = _read_native_texture(within(path, workspace), expected_hash)
                return self.reply(request, 200, body, mime)
            if relative.startswith("api/local-render/mask-raw/"):
                index = relative[len("api/local-render/mask-raw/"):]
                if request.command != "GET":
                    return self.reply(request, 405, {"error": "Method not allowed."})
                if (index not in ("0", "1", "2") or target.query or target.fragment
                        or relative != target.path[len(token) + 2:]):
                    return self.reply(request, 404, {"error": "Native mask is not available."})
                from .mask_pixels import read_mask_pixels
                with self.mask_pixels_lock:
                    if index not in mask_pixels_cache:
                        path, _mime = assets["api/local-render/mask/" + index]
                        size = prepared["manifest"]["inspection_runtime"]["render_contract"]["mask_size"]
                        mask_pixels_cache[index] = read_mask_pixels(within(path, workspace), size)
                    pixels = mask_pixels_cache[index]
                return self.reply(request, 200, pixels, "application/octet-stream")
            if relative == "api/cars" or relative == "api/car-switch" or relative.startswith("api/car-switch/"):
                current_archive = prepared.get("editor_config", {}).get("vehicle", {}).get("archive_name")
                return self._car_request(request, relative, target, token, current_archive)
            if relative.startswith("api/host-vinyl/"):
                if request.command != "GET":
                    return self.reply(request, 405, {"error": "Method not allowed."})
                identifier = relative[len("api/host-vinyl/"):]
                if (not HANDOFF_ID.fullmatch(identifier) or target.query or target.fragment
                        or relative != target.path[len(token) + 2:]):
                    return self.reply(request, 400, {"error": "Invalid vinyl transfer identifier."})
                if not self.render_lock.acquire(blocking=False):
                    return self.reply(request, 503, {"error": "A vinyl is already rendering. Retry after it completes."})
                try:
                    result = read_handoff(identifier, resolve_resource=self.renderer._resource)
                    status = 200
                except HandoffError as exc:
                    status, result = exc.status, {"error": str(exc)}
                finally:
                    self.render_lock.release()
                return self.reply(request, status, result)
            if request.command == "POST":
                if relative not in ("api/render-vinyl", "api/export-experiment", "api/export-section"):
                    return self.reply(request, 404, {"error": "Unknown API."})
                if request.headers.get("Transfer-Encoding") or request.headers.get("Content-Encoding"):
                    return self.reply(request, 400, {"error": "Encoded request bodies are not supported."})
                lengths = request.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                    return self.reply(request, 411, {"error": "One Content-Length is required."})
                length = int(lengths[0])
                maximum = MAX_PROJECT_BYTES if relative in ("api/export-experiment", "api/export-section") else MAX_BODY_BYTES
                if length > maximum:
                    return self.reply(request, 413, {"error": "Request exceeds the API size limit."})
                if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    return self.reply(request, 415, {"error": "Content-Type must be application/json."})
                if not self.render_lock.acquire(blocking=False):
                    return self.reply(request, 503, {"error": "A vinyl is already rendering. Retry after it completes."})
                try:
                    body = request.rfile.read(length)
                    request.body_consumed = True
                    if len(body) != length:
                        return self.reply(request, 400, {"error": "Truncated request body."})
                    value = decode_json(body)
                    if relative == "api/export-section":
                        if not isinstance(value, dict) or set(value) != {"project", "section"}:
                            raise ValidationError("Expected a project and one section.")
                        from .save_codec import compile_section_vinyl
                        config = prepared["editor_config"]
                        result = compile_section_vinyl(value["project"], config["vehicle"]["car_id"],
                                                       [row["section"] for row in config["sections"]], value["section"])
                        return self.reply(request, 200, result)
                    if relative == "api/export-experiment":
                        if exporter is None:
                            return self.reply(request, 409, {"error": "Launch with an owned, same-car save export template first."})
                        result = exporter.export(value)
                        return self.reply(request, 200, result, "application/zip")
                    result = self.renderer(value)
                    return self.reply(request, 200, result)
                finally:
                    self.render_lock.release()
            if relative == "api/manifest":
                return self.reply(request, 200, prepared["manifest"])
            if relative == "api/editor-config":
                capability = exporter.capabilities() if exporter else {
                    "enabled": False, "reason": "No same-car export template was supplied.", "template_layout_available": False}
                return self.reply(request, 200, {**prepared["editor_config"], "experimental_export": capability,
                                                 "livery_section_policy": section_limit_policy(),
                                                 **self.language.configuration(),
                                                 "host_vinyl_handoff": HOST_VINYL_HANDOFF_READY,
                                                 "host_theme_handoff": True, "ui_theme_persistence": True,
                                                 "ui_theme": self.theme_context.effective(),
                                                 "host_ui_theme": self.theme_context.get(),
                                                 "section_vinyl_export": True, "car_switch": self.car_workspace is not None,
                                                 "source_editor_roundtrip": True,
                                                 "action_confirmations": {"version": 1, "enabled": True},
                                                 "project_storage": {"enabled": True, "version": 1},
                                                 "vinyl_library": {"enabled": True, "version": 1},
                                                 "recovery": {"enabled": True, "version": 1, "debounce_ms": 1500},
                                                 "launch_archive": self.launch_archive, "native_mask_pixels": True})
            if relative == "api/template-layout":
                if exporter is None:
                    return self.reply(request, 409, {"error": "No save export template was supplied."})
                return self.reply(request, 200, exporter.template_layout())
            if relative in assets:
                path, mime = assets[relative]
                return self.reply(request, 200, within(path, workspace).read_bytes(), mime)
            name = relative or "index.html"
            if name in self.static:
                path, root = self.static[name]
                path = within(path, root)
                if path.is_file():
                    mime = "text/javascript" if path.suffix in (".js", ".mjs") else mimetypes.guess_type(name)[0] or "text/plain"
                    return self.reply(request, 200, path.read_bytes(), mime)
            self.reply(request, 404, {"error": "File not available."})
        except StorageError as exc:
            self.reply(request, exc.status, exc.response())
        except (CarError, SourceEditError, RecoveryError, ConfirmationError, LanguageError, PreviewError) as exc:
            self.reply(request, exc.status, {"error": str(exc)})
        except ValidationError as exc:
            self.reply(request, 422, {"error": str(exc)})
        except (socket.timeout, TimeoutError):
            self.reply(request, 408, {"error": "Request timed out."})
        except (OSError, ValueError, RecursionError):
            self.reply(request, 400, {"error": "Request or local asset is invalid."})
        except Exception:
            logging.exception("Livery request failed")
            self.reply(request, 500, {"error": "Local rendering failed. See the backend log."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kfps-root", type=Path, required=True)
    parser.add_argument("--game-root", type=Path, required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--template", type=Path, help="Read-only same-car C_livery export or .kfpslivery template")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be in 0..65535.")
    with workspace_lock(args.workspace):
        run(args)


def run(args):
    prepared = prepare_car(args.kfps_root, args.game_root, args.archive, args.workspace)
    info_path = within(args.workspace / "server-info.json", args.workspace)
    if args.prepare_only:
        atomic_json(info_path, {"status": "prepared", "url": None, "pid": os.getpid(), "vehicle": prepared["editor_config"]["vehicle"]})
        print(json.dumps({"status": "prepared", "workspace": str(args.workspace.resolve())}), flush=True)
        return
    exporter = None
    if args.template:
        from .export_service import ExportService
        exporter = ExportService(args.template, prepared["editor_config"]["vehicle"],
                                 [section["section"] for section in prepared["editor_config"]["sections"]])
    server = LiveryLabServer(prepared, args.workspace, args.kfps_root, port=args.port, export_service=exporter,
                            game_root=args.game_root)
    stop = threading.Event()
    def stopping(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        url = server.start()
        atomic_json(info_path, {"status": "running", "url": url, "pid": os.getpid(), "vehicle": prepared["editor_config"]["vehicle"]})
        print(json.dumps({"status": "running", "url": url}), flush=True)
        stop.wait()
    finally:
        server.close()
        atomic_json(info_path, {"status": "stopped", "url": None, "pid": os.getpid()})


if __name__ == "__main__":
    main()
