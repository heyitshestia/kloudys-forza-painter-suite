"""Loopback preview preferences keep the existing request and storage boundaries."""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))

from kfps_livery_lab.prepare import LAB_ROOT, load_baseline
from kfps_livery_lab.server import LiveryLabServer, WEB_FILES
from kfps_livery_lab.model import NativeVinylRenderer
import test_studio_preview_quality_model as render_fixtures
from test_studio_preview_quality_model import png_image, shape


RUN = LAB_ROOT / "runs/test-preview-quality/routes"


class PreviewQualityRouteTests(unittest.TestCase):
    def setUp(self):
        RUN.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=RUN)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        diagnostics = patch("kfps_livery_lab.diagnostics.DEFAULT_ROOT", self.root / "diagnostics")
        diagnostics.start()
        self.addCleanup(diagnostics.stop)
        self.web = self.root / "web"
        self.host = self.root / "host"
        self.settings = self.root / "session/settings"
        for name in (*WEB_FILES, "preview-quality.mjs", "private.mjs"):
            path = self.web / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// fixture", encoding="utf-8")
        for name in ("mesh.glb", "paint.png", "m0.png", "m1.png", "m2.png"):
            (self.root / name).write_bytes(b"asset")
        self.prepared = {
            "files": {"mesh": "mesh.glb", "paint": "paint.png", "masks": ["m0.png", "m1.png", "m2.png"]},
            "manifest": {"inspection_runtime": {"local_mesh": True}},
            "editor_config": {"paint_size": [2048, 1024], "sections": [], "vehicle": {"car_id": 1}}}
        self.renderer = NativeVinylRenderer.__new__(NativeVinylRenderer)
        self.renderer._resource = Mock(return_value=("Primitives", 1))
        self.renderer.baseline = Mock()
        self.renderer.baseline.render_typecode_layers_canvas.side_effect = render_fixtures.PreviewQualityModelTests.canvas
        self.start()
        self.addCleanup(lambda: self.server.close())

    def start(self):
        self.server = LiveryLabServer(self.prepared, self.root, self.host, web_root=self.web,
                                     renderer=self.renderer, session_data_root=self.root / "session")
        self.server.start()
        self.prefix = f"/{self.server.token}/"

    def request(self, method, route="api/preview-quality", body=None, headers=None, *, raw_path=False):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.httpd.server_port, timeout=3)
        try:
            connection.request(method, route if raw_path else self.prefix + route, body, headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def post(self, value, route="api/preview-quality", **headers):
        return self.request("POST", route, json.dumps(value).encode(), {"Content-Type": "application/json", **headers})

    def test_default_persistence_restart_and_settings_root(self):
        status, headers, body = self.request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"version": 1, "quality": "balanced"})
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.server.preview_quality.root, self.server.language.root)
        self.assertEqual(self.server.preview_quality.root, self.server.confirmations.root)
        self.assertEqual(self.server.preview_quality.root, self.settings)
        for quality in ("fast", "balanced", "sharp"):
            self.assertEqual(json.loads(self.post({"quality": quality})[2]), {"version": 1, "quality": quality})
        old_token = self.server.token
        self.server.close()
        self.start()
        self.assertNotEqual(self.server.token, old_token)
        self.assertEqual(json.loads(self.request("GET")[2]), {"version": 1, "quality": "sharp"})
        self.assertEqual(self.request("GET", f"/{old_token}/api/preview-quality", raw_path=True)[0], 404)

    def test_strict_json_enum_and_size_guards_preserve_saved_choice(self):
        self.assertEqual(self.post({"quality": "fast"})[0], 200)
        path = self.settings / "preview-quality.json"
        before = path.read_bytes()
        for value in ({}, [], None, {"quality": "FAST"}, {"quality": None}, {"quality": 1},
                      {"quality": []}, {"quality": "sharp", "version": 1}):
            self.assertEqual(self.post(value)[0], 422)
        for raw in (b"bad", b'\xff', b'{"quality":NaN}', b'{"quality":"fast","quality":"sharp"}'):
            self.assertEqual(self.request("POST", body=raw, headers={"Content-Type": "application/json"})[0], 422)
        self.assertEqual(self.request("POST", body=b"{}")[0], 415)
        self.assertEqual(self.request("POST", body=b"", headers={"Content-Length": "1025"})[0], 413)
        exact = b'{"quality":"balanced"}'.ljust(1024, b" ")
        self.assertEqual(self.request("POST", body=exact, headers={"Content-Type": "application/json; charset=utf-8"})[0], 200)
        self.assertEqual(self.post({"quality": "fast"})[0], 200)
        for header in ("Content-Encoding", "Transfer-Encoding"):
            self.assertEqual(self.request("POST", body=b"", headers={header: "gzip"})[0], 400)
        self.assertEqual(path.read_bytes(), before)

    def test_host_origin_token_and_exact_route_guards(self):
        for headers in ({"Host": "evil.test"}, {"Origin": "http://evil.test"}, {"Origin": "null"},
                        {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.request("GET", headers=headers)[0], 403)
            self.assertEqual(self.post({"quality": "sharp"}, **headers)[0], 403)
        self.assertEqual(self.request("GET", headers={"Origin": self.server.origin})[0], 200)
        for route, expected in (("api/preview-quality?x=1", 400), ("api/preview-quality#x", 400),
                                ("api/%70review-quality", 400), ("api/preview-quality/extra", 404)):
            self.assertEqual(self.request("GET", route)[0], expected)
            self.assertEqual(self.post({"quality": "fast"}, route)[0], expected)
        self.assertEqual(self.request("GET", "/api/preview-quality", raw_path=True)[0], 404)
        self.assertEqual(self.request("OPTIONS")[0], 405)
        self.assertFalse(self.settings.exists())

    def test_missing_invalid_and_duplicate_headers_never_write(self):
        cases = [([], 411), ([("Content-Length", "-1")], 411), ([("Content-Length", "1x")], 411),
                 ([("Content-Length", "0"), ("Content-Length", "0")], 411),
                 ([("Content-Length", "0"), ("Origin", self.server.origin), ("Origin", self.server.origin)], 403),
                 ([("Content-Length", "0"), ("Host", self.server.origin[7:])], 403)]
        for headers, expected in cases:
            connection = http.client.HTTPConnection("127.0.0.1", self.server.httpd.server_port, timeout=3)
            try:
                connection.putrequest("POST", self.prefix + "api/preview-quality")
                connection.putheader("Content-Type", "application/json")
                for name, value in headers:
                    connection.putheader(name, value)
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
            finally:
                connection.close()
        self.assertFalse(self.settings.exists())

    def test_truncated_body_never_writes(self):
        with socket.create_connection(("127.0.0.1", self.server.httpd.server_port), timeout=3) as connection:
            request = (f"POST {self.prefix}api/preview-quality HTTP/1.0\r\nHost: {self.server.origin[7:]}\r\n"
                       "Content-Type: application/json\r\nContent-Length: 30\r\n\r\n{}").encode()
            connection.sendall(request)
            connection.shutdown(socket.SHUT_WR)
            response = http.client.HTTPResponse(connection)
            response.begin()
            self.assertEqual(response.status, 400)
            response.read()
        self.assertFalse(self.settings.exists())

    def test_token_rotation_during_post_does_not_write(self):
        from kfps_livery_lab import server as backend
        original = backend.decode_json
        def rotate(raw):
            self.server.token = "rotated-session"
            return original(raw)
        with patch.object(backend, "decode_json", rotate):
            self.assertEqual(self.post({"quality": "sharp"})[0], 404)
        self.assertFalse(self.settings.exists())

    def test_corrupt_preference_preserved_and_config_is_independent(self):
        self.settings.mkdir(parents=True)
        path = self.settings / "preview-quality.json"
        path.write_bytes(b"corrupt-future-file")
        for response in (self.request("GET"), self.post({"quality": "sharp"})):
            self.assertEqual(response[0], 409)
            self.assertEqual(set(json.loads(response[2])), {"error"})
            self.assertNotIn(str(self.root).encode(), response[2])
        self.assertEqual(path.read_bytes(), b"corrupt-future-file")
        status, _, body = self.request("GET", "api/editor-config")
        self.assertEqual(status, 200)
        self.assertNotIn("preview_quality", json.loads(body))

    def test_atomic_failure_returns_safe_error_and_preserves_other_settings(self):
        self.settings.mkdir(parents=True)
        siblings = {"studio-language.json": b'{"version":1,"language":"ja"}',
                    "action-confirmations.json": b'{"version":1,"skipped":[]}'}
        for name, content in siblings.items():
            (self.settings / name).write_bytes(content)
        self.assertEqual(self.post({"quality": "fast"})[0], 200)
        with patch("kfps_livery_lab.file_io.os.replace", side_effect=PermissionError("private path")):
            response = self.post({"quality": "sharp"})
        self.assertEqual(response[0], 503)
        self.assertNotIn(b"private path", response[2])
        self.assertEqual(json.loads(self.request("GET")[2])["quality"], "fast")
        for name, content in siblings.items():
            self.assertEqual((self.settings / name).read_bytes(), content)
        self.assertEqual(list(self.settings.glob("*.tmp")), [])

    def test_optional_module_is_allowlisted_without_serving_settings(self):
        status, headers, body = self.request("GET", "preview-quality.mjs")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/javascript")
        self.assertEqual(body, b"// fixture")
        for name in ("private.mjs", "settings/preview-quality.json", "preview-quality.lock"):
            self.assertEqual(self.request("GET", name)[0], 404)

    def test_render_quality_is_request_only_not_a_shape_or_export_setting(self):
        self.assertEqual(self.post({"quality": "sharp"})[0], 200)
        canonical = json.loads(self.post({"shapes": [shape()]}, "api/render-vinyl")[2])
        self.assertEqual((canonical["width"], canonical["height"]), (2048, 1024))
        for quality, size in (("fast", (1024, 512)), ("balanced", (2048, 1024)), ("sharp", (4096, 2048))):
            status, _, body = self.post({"shapes": [shape()], "preview_quality": quality}, "api/render-vinyl")
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertEqual(result["bounds"], canonical["bounds"])
            self.assertEqual(result["shapes"], canonical["shapes"])
            with png_image(result) as image:
                self.assertEqual(image.size, size)
        self.assertEqual(self.post({"shapes": [shape()], "preview_quality": "ultra"}, "api/render-vinyl")[0], 422)
        with patch("kfps_livery_lab.save_codec.compile_section_vinyl") as compile_section:
            self.assertEqual(self.post({"project": {}, "section": "Top", "preview_quality": "fast"},
                                       "api/export-section")[0], 422)
            compile_section.assert_not_called()

    @unittest.skipUnless(os.environ.get("KFPS_LAB_TEST_BASELINE"), "Explicit KFPS baseline not selected")
    def test_native_render_quality_through_real_loopback_api(self):
        load_baseline(Path(os.environ["KFPS_LAB_TEST_BASELINE"]))
        self.server.renderer = NativeVinylRenderer()
        shapes = [shape(data=[.125, -.75, -1.25, .5, 31, .3, 0]),
                  shape(data=[0, 0, .25, .25, 0, 0, 1], mask=True)]
        canonical = self.server.renderer({"shapes": shapes})
        for quality, size in render_fixtures.SIZES.items():
            status, _, body = self.post({"shapes": shapes, "preview_quality": quality}, "api/render-vinyl")
            self.assertEqual(status, 200)
            result = json.loads(body)
            self.assertEqual(result["bounds"], canonical["bounds"])
            self.assertEqual(result["shapes"], canonical["shapes"])
            self.assertEqual((result["width"], result["height"]), size)
            with png_image(result) as image:
                self.assertEqual(image.size, size)
                self.assertIsNotNone(image.getchannel("A").getbbox())
        self.assertFalse(self.settings.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
