import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock

from test_fabric_editor_server import RunningEditorServer, fabric_server, post_json


class EditorPrivateReadTests(unittest.TestCase):
    def test_cancelled_preview_does_not_log_a_server_failure(self):
        handler = object.__new__(fabric_server.Handler)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        for error in (BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()):
            handler.wfile.write.side_effect = error
            handler._send_png(b"preview")
        handler.wfile.write.side_effect = OSError("unexpected disk failure")
        with self.assertRaises(OSError):
            handler._send_png(b"preview")

    def test_private_reads_require_session_and_same_origin_before_dispatch(self):
        routes = (
            "startup-help-confirmed", "preferences", "themes", "autosave",
            "recovery-reference?sha256=missing", "json-browser", "json-file?id=missing",
            "json-preview?id=missing", "project-browser", "project-file?id=missing",
            "project-receipt?id=missing", "assets", "asset-preview?id=missing",
            "studio-source-context", "diagnostics", "update-status",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = fabric_server.ServerPaths.for_runtime(root, root / "runtime")
            with RunningEditorServer(paths=paths) as server:
                token = server.httpd.editor_session_token
                for route in routes:
                    for headers in ({}, {fabric_server.EDITOR_MUTATION_HEADER: "wrong"},
                                    {fabric_server.EDITOR_MUTATION_HEADER: "\u00ff"},
                                    {fabric_server.EDITOR_MUTATION_HEADER: token, "Host": "foreign.invalid"},
                                    {fabric_server.EDITOR_MUTATION_HEADER: token, "Origin": "http://foreign.invalid"},
                                    {fabric_server.EDITOR_MUTATION_HEADER: token, "Sec-Fetch-Site": "cross-site"}):
                        with self.subTest(route=route, headers=list(headers)):
                            request = urllib.request.Request(f"{server}/api/fabric-editor/{route}", headers=headers)
                            with self.assertRaises(urllib.error.HTTPError) as denied:
                                urllib.request.urlopen(request, timeout=3)
                            self.assertEqual(403, denied.exception.code)
                for route in ("health",):
                    with urllib.request.urlopen(f"{server}/api/fabric-editor/{route}", timeout=3) as response:
                        self.assertEqual(200, response.status)
                with urllib.request.urlopen(f"{server}/tools/fabric-editor/index.html", timeout=3) as response:
                    self.assertEqual(200, response.status)

    def test_authenticated_project_and_recovery_reads_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = fabric_server.ServerPaths.for_runtime(root, root / "runtime")
            with RunningEditorServer(paths=paths) as server:
                _, saved = post_json(server, fabric_server.PROJECT_SAVE_API,
                                     {"name": "Private", "payload": {"shapes": []}})
                headers = {fabric_server.EDITOR_MUTATION_HEADER: server.httpd.editor_session_token}
                for route in ("project-browser", "project-file?id=" + saved["id"], "autosave?head=1",
                              "preferences", "assets", "themes"):
                    request = urllib.request.Request(f"{server}/api/fabric-editor/{route}", headers=headers)
                    with urllib.request.urlopen(request, timeout=3) as response:
                        self.assertIsInstance(json.loads(response.read()), dict)


if __name__ == "__main__":
    unittest.main()
