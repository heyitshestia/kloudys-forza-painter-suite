"""GET-only loopback display server; no Studio authoring server or stores."""
from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
import secrets
import struct
import threading
from urllib.parse import urlsplit

from .prepare import LAB_ROOT, file_hash
from .readonly_preview import descriptor_assets, ordinary_path, read_descriptor, verified_bytes
from .file_io import io_path

WEB_FILES = ('readonly.html', 'readonly.mjs', 'readonly.css', 'viewer.css', 'livery-scene.js',
             'surface-math.mjs', 'native-material.mjs', 'native-texture-binding.mjs', 'preview-quality.mjs',
             'wheel-model.mjs', 'inspection-tools.mjs', 'component-model.mjs', 'layout-model.mjs', 'mirror-links.mjs',
             'icons.js', 'LICENSE.lucide', 'theme-adapter.mjs', 'i18n.mjs',
             'locales/en.mjs', 'locales/ko.mjs', 'locales/ja.mjs')
VENDOR_FILES = ('three/build/three.module.min.js', 'three/build/three.core.min.js',
                'three/examples/jsm/loaders/GLTFLoader.js', 'three/examples/jsm/controls/OrbitControls.js',
                'three/examples/jsm/utils/BufferGeometryUtils.js', 'three/examples/jsm/utils/SkeletonUtils.js',
                'three/LICENSE')
IMPORT_MAP = '{"imports":{"three":"./vendor/three/build/three.module.min.js","three/addons/":"./vendor/three/examples/jsm/"}}'
IMPORT_HASH = base64.b64encode(hashlib.sha256(IMPORT_MAP.encode('utf-8')).digest()).decode('ascii')


class _BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
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


class ReadonlyPreviewServer:
    def __init__(self, descriptor, kfps_root, *, expected_package_id=None, expected_descriptor_sha256=None):
        self.lease = None
        root = Path(descriptor).absolute().parent
        try:
            if io_path(root / 'viewer.lock').exists():
                from .readonly_cache import cache_lease
                self.lease = cache_lease(root)
                self.lease.__enter__()
            self._initialize(descriptor, kfps_root, expected_package_id, expected_descriptor_sha256)
        except BaseException:
            if self.lease is not None:
                self.lease.__exit__(None, None, None)
                self.lease = None
            raise

    def _initialize(self, descriptor, kfps_root, expected_package_id, expected_descriptor_sha256):
        self.path = Path(descriptor).absolute()
        self.root = self.path.parent
        self.prepared = read_descriptor(self.path)
        if expected_package_id is not None and self.prepared['manifest'].get('package_id') != expected_package_id:
            raise ValueError('Prepared viewer belongs to another livery package.')
        if expected_descriptor_sha256 is not None and file_hash(self.path) != expected_descriptor_sha256:
            raise ValueError('Prepared viewer identity changed before startup.')
        self.assets = descriptor_assets(self.prepared, self.root)
        self.token = secrets.token_urlsafe(32)
        self.thread = None
        self.closed = False
        self.kfps_root = Path(kfps_root).absolute()
        self.raw_masks = {}
        self.mask_lock = threading.Lock()
        self.static = {}
        web = LAB_ROOT / 'src/web'
        vendor = Path(kfps_root).absolute() / 'tools/livery-inspector/vendor'
        for prefix, base, names in (('', web, WEB_FILES), ('vendor/', vendor, VENDOR_FILES)):
            for name in names:
                path = ordinary_path(base / name, base)
                body = io_path(path).read_bytes()
                self.static[prefix + name] = (path, base, hashlib.sha256(body).hexdigest())
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.0'

            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def do_GET(self):
                owner.handle(self)

            def do_POST(self):
                owner.reply(self, 405, {'error': 'This viewer is read-only.'})

            do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_POST

            def log_message(self, *_args):
                pass

        self.httpd = _BoundedServer(('127.0.0.1', 0), Handler)

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.httpd.server_port}'

    def start(self):
        if self.closed:
            raise ValueError('The viewer session has closed.')
        if self.thread is None:
            self.thread = threading.Thread(target=self.httpd.serve_forever,
                                           kwargs={'poll_interval': .05}, daemon=True)
            self.thread.start()
        return f'{self.origin}/{self.token}/'

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.thread:
            self.httpd.shutdown()
            self.thread.join(timeout=3)
            self.thread = None
        self.httpd.server_close()
        self.raw_masks.clear()
        if self.lease is not None:
            self.lease.__exit__(None, None, None)
            self.lease = None

    def handle(self, request):
        if (request.headers.get_all('Host') != [self.origin.removeprefix('http://')]
                or request.headers.get('Origin', self.origin) != self.origin
                or request.headers.get('Sec-Fetch-Site', 'none') not in ('none', 'same-origin')):
            return self.reply(request, 403, {'error': 'Only this local viewer origin is allowed.'})
        target = urlsplit(request.path)
        prefix = f'/{self.token}/'
        if (target.scheme or target.netloc or target.fragment or not target.path.startswith(prefix)
                or '%' in target.path or '\\' in target.path or '..' in target.path.split('/')):
            return self.reply(request, 404, {'error': 'Unknown preview resource.'})
        relative = target.path[len(prefix):]
        if target.query and relative:
            return self.reply(request, 404, {'error': 'Unknown preview resource.'})
        try:
            if relative == 'api/manifest':
                return self.reply(request, 200, self.prepared['manifest'])
            if relative.startswith('api/ui-font/'):
                from .theme_context import validate_theme, _regular, FONT_TYPES, MAX_FONT_BYTES
                encoded = relative.removeprefix('api/ui-font/')
                if not 2 <= len(encoded) <= 360:
                    raise ValueError('Invalid font identifier.')
                asset = bytes.fromhex(encoded).decode('ascii')
                validate_theme({'name': 'Viewer font', 'variables': {'--panel': '#000000'},
                                'fontFamily': 'sans-serif', 'fontAssets': [{'family': 'Viewer', 'asset': asset}]})
                path = self.kfps_root / 'KFPS.UI/assets' / asset
                body = _regular(path, self.kfps_root, MAX_FONT_BYTES)
                signature, mime, _ = FONT_TYPES[path.suffix.lower()]
                if body[:4] != signature:
                    raise ValueError('Invalid font format.')
                return self.reply(request, 200, body, mime)
            if relative.startswith('api/local-render/mask-raw/'):
                index = relative.removeprefix('api/local-render/mask-raw/')
                if index not in ('0', '1', '2'):
                    return self.reply(request, 404, {'error': 'Unknown mask.'})
                route = 'api/local-render/mask/' + index
                with self.mask_lock:
                    body = self.asset_bytes(route)
                    if index not in self.raw_masks:
                        from PIL import Image
                        size = self.prepared['manifest']['inspection_runtime']['render_contract']['mask_size']
                        if (not isinstance(size, list) or len(size) != 2
                                or any(type(n) is not int or not 0 < n <= 8192 for n in size)
                                or size[0] * size[1] > 16 * 1024**2):
                            raise ValueError('Invalid native mask dimensions.')
                        with Image.open(io.BytesIO(body)) as image:
                            if image.format != 'PNG' or image.mode != 'RGBA' or image.size != tuple(size):
                                raise ValueError('Native mask dimensions changed.')
                            self.raw_masks[index] = struct.pack('<II', *size) + image.tobytes()
                    result = self.raw_masks[index]
                return self.reply(request, 200, result, 'application/octet-stream')
            if relative in self.assets:
                return self.reply(request, 200, self.asset_bytes(relative), self.assets[relative][1])
            name = relative or 'readonly.html'
            if name in self.static:
                path, root, digest = self.static[name]
                mime = ('text/javascript' if path.suffix in ('.js', '.mjs') else
                        mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
                return self.reply(request, 200, verified_bytes(path, digest, root, 8 * 1024**2), mime)
        except (OSError, ValueError, KeyError, TypeError):
            return self.reply(request, 409, {'error': 'Preview assets changed or are unavailable. Reopen this livery.'})
        return self.reply(request, 404, {'error': 'Unknown preview resource.'})

    def asset_bytes(self, route):
        path, _ = self.assets[route]
        return verified_bytes(path, self.prepared['file_sha256'][path.relative_to(self.root).as_posix()], self.root)

    @staticmethod
    def reply(request, status, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=True, allow_nan=False).encode('utf-8') if isinstance(data, dict) else data
        request.send_response(status)
        for name, value in {'Content-Type': content_type, 'Content-Length': str(len(body)),
                            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                            'Referrer-Policy': 'no-referrer', 'Cross-Origin-Resource-Policy': 'same-origin',
                            'Content-Security-Policy': "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'sha256-" + IMPORT_HASH + "'; connect-src 'self'; font-src 'self'; worker-src 'self' blob:"}.items():
            request.send_header(name, value)
        request.end_headers()
        try:
            request.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass
