from __future__ import annotations

import json
import math
import mimetypes
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .package import FullLiveryPackageError, read_package_member, validate_livery_inspection_artifact
from .render_contract import MASK_PAGE_COUNT, RENDER_CONTRACT_FORMAT


class LiveryInspectorServer:
    """Token-scoped localhost server for the embedded livery inspector."""

    def __init__(self, static_root: Path | str):
        self.static_root = Path(static_root).resolve()
        self._package: Path | None = None
        self._local_mesh: Path | None = None
        self._local_render: dict = {}
        self._manifest: dict = {}
        self._token = secrets.token_urlsafe(18)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            return ""
        return f"http://127.0.0.1:{self._server.server_port}/{self._token}/"

    @property
    def package_path(self) -> Path | None:
        return self._package

    def set_package(self, package: Path | str) -> dict:
        path = Path(package).resolve()
        manifest = validate_livery_inspection_artifact(path)
        self._package = path
        self._manifest = manifest
        self._local_mesh = None
        self._local_render = {}
        return manifest

    def set_local_mesh(self, mesh: Path | str | None) -> None:
        if mesh is None:
            self._local_mesh = None
            return
        path = Path(mesh).resolve()
        if not path.is_file() or path.suffix.casefold() != ".glb":
            raise FullLiveryPackageError("The local inspection mesh is not a readable GLB file.")
        self._local_mesh = path

    def set_local_render_contract(self, root: Path | str, contract: dict) -> None:
        base = Path(root).resolve()
        if str(contract.get("format") or "") != RENDER_CONTRACT_FORMAT:
            raise FullLiveryPackageError("The local FH6 livery render contract is unsupported.")
        files = contract.get("files") or {}

        def local_png(name: object) -> Path:
            path = (base / str(name or "")).resolve()
            try:
                path.relative_to(base)
            except ValueError as exc:
                raise FullLiveryPackageError("The local livery render path is unsafe.") from exc
            if not path.is_file() or path.suffix.casefold() != ".png":
                raise FullLiveryPackageError("A local FH6 livery render texture is missing.")
            return path

        paint = local_png(files.get("paint"))
        masks = [local_png(name) for name in (files.get("masks") or [])]
        if len(masks) != MASK_PAGE_COUNT:
            raise FullLiveryPackageError("The local FH6 livery mask set is incomplete.")
        sections = contract.get("sections") or []
        slots: set[int] = set()
        for section in sections:
            if not isinstance(section, dict):
                raise FullLiveryPackageError("The local FH6 livery section metadata is invalid.")
            slot = int(section.get("slot_index", -1))
            if slot < 0 or slot >= 11 or slot in slots:
                raise FullLiveryPackageError("The local FH6 livery section slots are invalid.")
            slots.add(slot)
            for key in ("source_region", "paint_region"):
                values = section.get(key)
                if not isinstance(values, list) or len(values) != 4:
                    raise FullLiveryPackageError("The local FH6 livery texture regions are invalid.")
                try:
                    normalized = [float(value) for value in values]
                except (TypeError, ValueError) as exc:
                    raise FullLiveryPackageError("The local FH6 livery texture regions are invalid.") from exc
                if (
                    any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in normalized)
                    or normalized[0] >= normalized[2]
                    or normalized[1] >= normalized[3]
                ):
                    raise FullLiveryPackageError("The local FH6 livery texture regions are outside the atlas.")
        metadata = {
            key: contract[key]
            for key in (
                "format",
                "uv_contract",
                "assembly",
                "paint_size",
                "mask_size",
                "filters",
                "sections",
                "quality_scale",
                "quality_source",
            )
            if key in contract
        }
        self._local_render = {
            "paint": paint,
            "masks": masks,
            "metadata": metadata,
        }

    def start(self) -> str:
        if self._server is not None:
            return self.url
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib request-handler API
                owner._handle(self)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        server = self._server
        self._thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05),
            name="kfps-livery-inspector",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def close(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _handle(self, request: BaseHTTPRequestHandler) -> None:
        path = unquote(urlsplit(request.path).path)
        prefix = f"/{self._token}/"
        if not path.startswith(prefix):
            self._error(request, HTTPStatus.NOT_FOUND, "Unknown inspector session.")
            return
        relative = path[len(prefix) :]
        if relative == "api/manifest":
            runtime_manifest = dict(self._manifest)
            runtime_manifest["inspection_runtime"] = {
                "local_mesh": self._local_mesh is not None,
                "direct_uv3": self._local_mesh is not None and bool(self._local_render),
                "world_projection_fallback": False,
                "render_contract": self._local_render.get("metadata") or {},
            }
            self._send(request, json.dumps(runtime_manifest).encode("utf-8"), "application/json")
            return
        if relative == "api/local-mesh":
            if self._local_mesh is None:
                self._error(request, HTTPStatus.NOT_FOUND, "No matching local inspection mesh is ready.")
                return
            self._send(request, self._local_mesh.read_bytes(), "model/gltf-binary")
            return
        if relative == "api/local-render/paint":
            paint = self._local_render.get("paint")
            if paint is None:
                self._error(request, HTTPStatus.NOT_FOUND, "The local livery paint texture is unavailable.")
                return
            self._send(request, paint.read_bytes(), "image/png")
            return
        if relative.startswith("api/local-render/mask/"):
            parts = relative.split("/")
            if len(parts) != 4 or not parts[-1].isdigit():
                self._error(request, HTTPStatus.NOT_FOUND, "Unknown local livery mask texture.")
                return
            index = int(parts[-1])
            masks = self._local_render.get("masks") or []
            if index < 0 or index >= len(masks):
                self._error(request, HTTPStatus.NOT_FOUND, "The requested local livery mask is unavailable.")
                return
            self._send(request, masks[index].read_bytes(), "image/png")
            return
        if relative.startswith("api/member/"):
            if self._package is None:
                self._error(request, HTTPStatus.CONFLICT, "No livery package is open.")
                return
            member = relative[len("api/member/") :]
            try:
                data = read_package_member(self._package, member, allow_private_preview=True)
            except FullLiveryPackageError as exc:
                self._error(request, HTTPStatus.NOT_FOUND, str(exc))
                return
            mime = mimetypes.guess_type(member)[0] or "application/octet-stream"
            self._send(request, data, mime)
            return

        static_name = relative or "index.html"
        target = (self.static_root / static_name).resolve()
        try:
            target.relative_to(self.static_root)
        except ValueError:
            self._error(request, HTTPStatus.BAD_REQUEST, "Unsafe static path.")
            return
        if not target.is_file():
            self._error(request, HTTPStatus.NOT_FOUND, "Inspector file not found.")
            return
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(request, target.read_bytes(), mime)

    @staticmethod
    def _send(request: BaseHTTPRequestHandler, data: bytes, content_type: str) -> None:
        request.send_response(HTTPStatus.OK)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(data)))
        request.send_header("Cache-Control", "no-store")
        request.send_header("X-Content-Type-Options", "nosniff")
        request.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self'; worker-src 'self' blob:")
        request.end_headers()
        try:
            request.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    @staticmethod
    def _error(request: BaseHTTPRequestHandler, status: HTTPStatus, message: str) -> None:
        data = message.encode("utf-8", errors="replace")
        request.send_response(status)
        request.send_header("Content-Type", "text/plain; charset=utf-8")
        request.send_header("Content-Length", str(len(data)))
        request.send_header("Cache-Control", "no-store")
        request.end_headers()
        try:
            request.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
