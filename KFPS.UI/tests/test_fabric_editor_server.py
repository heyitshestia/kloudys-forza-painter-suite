import json
import http.client
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = ROOT / "KFPS.Editor" / "web"
for entry in (str(ROOT), str(ROOT / "tools/fabric-editor")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import start_fabric_editor as fabric_server


class RunningEditorServer:
    def __init__(self, *, paths=None):
        self.httpd = fabric_server.EditorServer(
            ("127.0.0.1", 0),
            fabric_server.Handler,
            paths=paths,
        )
        self.thread = threading.Thread(
            target=self.httpd.serve_forever,
            daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        return self

    def __str__(self):
        return self.url

    def __exit__(self, exc_type, exc, traceback):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        return False


def post_json(base_url: str, path: str, payload: dict, token=True):
    headers = {"Content-Type": "application/json"}
    if token:
        headers[fabric_server.EDITOR_MUTATION_HEADER] = str(
            getattr(getattr(base_url, "httpd", None), "editor_session_token", token)
        )
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class FabricEditorServerTests(unittest.TestCase):
    def test_update_status_is_authenticated_and_read_only(self):
        with RunningEditorServer() as server:
            endpoint = f"{server}/api/fabric-editor/update-status"
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(endpoint, timeout=3)
            self.assertEqual(denied.exception.code, 403)
            request = urllib.request.Request(endpoint, headers={
                fabric_server.EDITOR_MUTATION_HEADER: server.httpd.editor_session_token,
            })
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertFalse(json.loads(response.read())["available"])
            offered = {"localVersion": "3.1.77", "latestVersion": "3.1.78", "available": True,
                       "checking": False, "checked": True}
            server.httpd.update_status = offered
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(json.loads(response.read()), offered)
                self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertIs(server.httpd.update_status, offered)

    def test_json_response_ignores_disconnection_but_not_other_failures(self):
        handler = object.__new__(fabric_server.Handler)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        for error in (BrokenPipeError(), ConnectionResetError(), ConnectionAbortedError()):
            with self.subTest(error=type(error).__name__):
                handler.wfile.write.side_effect = error
                self.assertFalse(handler._send_json({"ok": True}))
        handler.wfile.write.side_effect = OSError("unrelated failure")
        with self.assertRaises(OSError):
            handler._send_json({"ok": True})
        handler.wfile.write.side_effect = None
        self.assertTrue(handler._send_json({"ok": True}))
        with self.assertRaises(TypeError):
            handler._send_json({"invalid": object()})

    def test_saved_files_and_private_commit_trace_survive_lost_reply(self):
        for job, endpoint in (("saveProject", fabric_server.PROJECT_SAVE_API),
                              ("saveExport", fabric_server.EDITOR_EXPORT_API)):
            with self.subTest(job=job), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                request_id = "358cd0bc-4e38-4bcc-8400-d3fe4e8b6b72"
                response_finished = threading.Event()
                original = fabric_server.Handler._send_json

                def lose_reply(handler, payload, status=200):
                    if payload.get("receipt", {}).get("request_id") != request_id:
                        return original(handler, payload, status)
                    handler.connection.shutdown(socket.SHUT_RDWR)
                    try:
                        return original(handler, payload, status)
                    finally:
                        response_finished.set()

                with (
                    patch.object(fabric_server, "EDITOR_PROJECT_ROOT", root / "projects"),
                    patch.object(fabric_server, "EDITOR_JSON_ROOT", root / "exports"),
                    patch.object(fabric_server, "EDITOR_SERVER_MARKER", root / "server.json"),
                    patch.object(fabric_server, "EDITOR_PROJECT_CHANGE_MARKER", root / "project-change.json"),
                    patch.object(fabric_server, "EDITOR_OUTPUT_CHANGE_MARKER", root / "output-change.json"),
                    patch.object(fabric_server, "_safe_relpath", side_effect=lambda path: Path(path).name),
                    patch.object(fabric_server.Handler, "_send_json", lose_reply),
                    RunningEditorServer() as server,
                ):
                    diagnostic = server.httpd.diagnostics()
                    server.httpd.handle_error = Mock()
                    with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError)):
                        post_json(server, endpoint, {"name": "PRIVATE ARTWORK", "request_id": request_id,
                                                   "payload": {"shapes": [{"type": 1, "private": "PRIVATE"}]}})
                    self.assertTrue(response_finished.wait(3))
                    store = server.httpd.project_store() if job == "saveProject" else server.httpd.export_store()
                    outcome = store.outcome(request_id)
                    self.assertTrue(outcome["current"])
                    target = store.root / outcome["receipt"]["target_id"]
                    self.assertEqual([{"type": 1, "private": "PRIVATE"}], json.loads(target.read_text())["shapes"])
                    self.assertEqual(1, len(list(store.root.rglob("*.json"))))
                    server.httpd.handle_error.assert_not_called()
                records = [json.loads(line) for line in (root / "performance.jsonl").read_text().splitlines()]
                commits = [record for record in records if record.get("requestId") == request_id]
                self.assertEqual(1, len(commits))
                self.assertEqual(("job", job, "committed", "native"),
                                 tuple(commits[0][key] for key in ("kind", "job", "state", "source")))
                self.assertGreaterEqual(commits[0]["duration"], 0)
                self.assertNotIn("PRIVATE", json.dumps(records))

    def test_executable_editor_assets_are_not_http_cached(self):
        with RunningEditorServer() as server:
            for filename in ("index.html", "editor.js", "editor-fabric-adapter.js", "style.css"):
                with self.subTest(filename=filename):
                    with urllib.request.urlopen(f"{server}/tools/fabric-editor/{filename}", timeout=3) as response:
                        self.assertEqual("no-store", response.headers.get("Cache-Control"))
                        self.assertEqual((EDITOR_ROOT / filename).read_bytes(), response.read())

    def test_rejected_posts_reliably_return_403_without_creating_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            projects = Path(temporary) / "projects"
            with patch.object(fabric_server, "EDITOR_PROJECT_ROOT", projects), RunningEditorServer() as server:
                for _ in range(30):
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        post_json(server, fabric_server.PROJECT_SAVE_API, {"name": "rejected", "payload": {"shapes": [{"type": 1}]}}, token=False)
                    self.assertEqual(403, error.exception.code)
                self.assertFalse(projects.exists())

    def test_recovery_revisions_survive_clear_restart_and_reordered_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "autosave.json"
            with patch.object(fabric_server, "EDITOR_AUTOSAVE_MARKER", marker):
                with RunningEditorServer() as server:
                    def store(revision, **changes):
                        return post_json(server, fabric_server.EDITOR_AUTOSAVE_API,
                                         {"shapes": [{"x": revision}], "recovery_revision": revision, **changes})[1]

                    self.assertTrue(store(20)["applied"])
                    self.assertTrue(store(20)["duplicate"])
                    self.assertFalse(store(20, shapes=[{"x": 999}])["applied"])
                    self.assertFalse(store(10)["applied"])
                    self.assertFalse(store(19, action="clear")["applied"])
                    self.assertEqual(20, json.loads(marker.read_text())["recovery_revision"])
                    self.assertTrue(store(21, action="clear")["cleared"])
                    self.assertTrue(store(21, action="clear")["duplicate"])
                    self.assertFalse(store(20)["applied"])
                with RunningEditorServer() as server:
                    self.assertFalse(store(20)["applied"])
                    with urllib.request.urlopen(f"{server}{fabric_server.EDITOR_AUTOSAVE_API}") as response:
                        self.assertFalse(json.load(response)["exists"])
                    self.assertTrue(store(22)["applied"])
                    self.assertEqual(22, json.loads(marker.read_text())["recovery_revision"])

    def test_recovery_legacy_payload_and_clear_remain_compatible(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "autosave.json"
            with patch.object(fabric_server, "EDITOR_AUTOSAVE_MARKER", marker), RunningEditorServer() as server:
                payload = {"shapes": [{"type": 1}], "saved_at": "2026-09-09T00:00:00Z"}
                self.assertTrue(post_json(server, fabric_server.EDITOR_AUTOSAVE_API, payload)[1]["applied"])
                self.assertEqual(payload, json.loads(marker.read_text()))
                self.assertTrue(post_json(server, fabric_server.EDITOR_AUTOSAVE_API, {"action": "clear"})[1]["cleared"])
                self.assertFalse(marker.exists())

    def test_recovery_failed_write_does_not_advance_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "autosave.json"
            with patch.object(fabric_server, "EDITOR_AUTOSAVE_MARKER", marker), RunningEditorServer() as server:
                payload = {"shapes": [], "recovery_revision": 10}
                with patch.object(fabric_server, "_write_json_atomic", side_effect=OSError("disk unavailable")):
                    with self.assertRaises(urllib.error.HTTPError):
                        post_json(server, fabric_server.EDITOR_AUTOSAVE_API, payload)
                self.assertTrue(post_json(server, fabric_server.EDITOR_AUTOSAVE_API, payload)[1]["applied"])

    def test_atomic_json_write_replaces_complete_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "nested" / "project.json"
            fabric_server._write_json_atomic(target, {"shapes": [1, 2]})
            fabric_server._write_json_atomic(target, {"shapes": [3]})

            self.assertEqual(
                {"shapes": [3]},
                json.loads(target.read_text(encoding="utf-8")),
            )
            self.assertEqual([], list(target.parent.glob("*.tmp")))

    def test_static_server_exposes_editor_assets_but_not_app_files(self):
        self.assertTrue(
            fabric_server._is_allowed_static_path(
                "/tools/fabric-editor/index.html"
            )
        )
        self.assertTrue(
            fabric_server._is_allowed_static_path(
                "/tools/fabric-editor/Resources/Vinyls/Primitives/1.png"
            )
        )
        self.assertTrue(
            fabric_server._is_allowed_static_path("/assets/kfps-logo.ico")
        )
        self.assertFalse(
            fabric_server._is_allowed_static_path("/hestia.kfpskey")
        )
        self.assertFalse(
            fabric_server._is_allowed_static_path(
                "/tools/fabric-editor/%2e%2e/%2e%2e/hestia.kfpskey"
            )
        )

        with RunningEditorServer() as base_url:
            with urllib.request.urlopen(
                f"{base_url}/tools/fabric-editor/index.html",
                timeout=3,
            ) as response:
                self.assertEqual(200, response.status)
            with self.assertRaises(urllib.error.HTTPError) as blocked:
                urllib.request.urlopen(
                    f"{base_url}/hestia.kfpskey",
                    timeout=3,
                )
            self.assertEqual(404, blocked.exception.code)

    def test_static_get_and_head_share_the_declared_mount(self):
        with RunningEditorServer() as server:
            for method in ("GET", "HEAD"):
                for filename in ("index.html", "editor.js", "Resources/Vinyls/Primitives/1", "Resources/Vinyls/Primitives/1.png"):
                    with self.subTest(method=method, filename=filename):
                        request = urllib.request.Request(f"{server}/tools/fabric-editor/{filename}", method=method)
                        with urllib.request.urlopen(request, timeout=3) as response:
                            self.assertEqual(200, response.status)
                            self.assertEqual((EDITOR_ROOT / filename).stat().st_size, int(response.headers["Content-Length"]))
                            self.assertEqual("no-store", response.headers["Cache-Control"])
                            self.assertEqual(b"" if method == "HEAD" else (EDITOR_ROOT / filename).read_bytes(), response.read())
                for target in ("/VERSION", "/tools/fabric-editor/start_fabric_editor.py", "/tools/fabric-editor/tests/run-native-page.py",
                               "/tools/fabric-editor/", "/tools/fabric-editor/Resources/Vinyls/",
                               "/tools/fabric-editor/%2e%2e/%2e%2e/VERSION", "/tools/fabric-editor/Resources/%5c..%5cVERSION"):
                    with self.subTest(method=method, target=target):
                        with self.assertRaises(urllib.error.HTTPError) as blocked:
                            urllib.request.urlopen(urllib.request.Request(f"{server}{target}", method=method), timeout=3)
                        self.assertEqual(404, blocked.exception.code)

    def test_mutations_require_editor_header_and_save_as_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary) / "projects"
            project_marker = Path(temporary) / "project-change.json"
            with (
                patch.object(
                    fabric_server,
                    "EDITOR_PROJECT_ROOT",
                    project_root,
                ),
                patch.object(
                    fabric_server,
                    "EDITOR_PROJECT_CHANGE_MARKER",
                    project_marker,
                ),
                RunningEditorServer() as base_url,
            ):
                payload = {
                    "name": "Protected Project",
                    "payload": {"shapes": [{"type": 1}]},
                    "overwrite": False,
                }
                with self.assertRaises(urllib.error.HTTPError) as unauthorized:
                    post_json(
                        base_url,
                        fabric_server.PROJECT_SAVE_API,
                        payload,
                        token=False,
                    )
                self.assertEqual(403, unauthorized.exception.code)

                with self.assertRaises(urllib.error.HTTPError) as foreign_origin:
                    request = urllib.request.Request(
                        f"{base_url}{fabric_server.PROJECT_SAVE_API}",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Origin": "https://untrusted.example",
                            fabric_server.EDITOR_MUTATION_HEADER: base_url.httpd.editor_session_token,
                        },
                        method="POST",
                    )
                    urllib.request.urlopen(request, timeout=3)
                self.assertEqual(403, foreign_origin.exception.code)

                status, saved = post_json(
                    base_url,
                    fabric_server.PROJECT_SAVE_API,
                    payload,
                )
                self.assertEqual(200, status)
                self.assertEqual("Protected Project", saved["title"])

                with self.assertRaises(urllib.error.HTTPError) as collision:
                    post_json(
                        base_url,
                        fabric_server.PROJECT_SAVE_API,
                        payload,
                    )
                self.assertEqual(409, collision.exception.code)
                error = json.loads(
                    collision.exception.read().decode("utf-8")
                )
                self.assertEqual("project_exists", error["code"])

                payload["overwrite"] = True
                payload["payload"]["shapes"].append({"type": 2})
                status, _saved = post_json(
                    base_url,
                    fabric_server.PROJECT_SAVE_API,
                    payload,
                )
                self.assertEqual(200, status)
                target = (
                    project_root
                    / "Protected Project.fabric-project.json"
                )
                self.assertEqual(
                    2,
                    len(
                        json.loads(
                            target.read_text(encoding="utf-8")
                        )["shapes"]
                    ),
                )
                self.assertEqual(
                    2,
                    json.loads(
                        target.read_text(encoding="utf-8")
                    )["layer_count"],
                )
                marker = json.loads(project_marker.read_text(encoding="utf-8"))
                self.assertEqual(str(target.resolve()), marker["path"])

    def test_editor_export_records_a_desktop_output_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            editor_root = Path(temporary) / "editor"
            output_marker = Path(temporary) / "editor-output-change.json"
            with (
                patch.object(fabric_server, "EDITOR_JSON_ROOT", editor_root),
                patch.object(fabric_server, "EDITOR_SERVER_MARKER", Path(temporary) / "server.json"),
                patch.object(fabric_server, "EDITOR_OUTPUT_CHANGE_MARKER", output_marker),
                patch.object(fabric_server, "_safe_relpath", side_effect=lambda path: Path(path).name),
                RunningEditorServer() as base_url,
            ):
                status, saved = post_json(
                    base_url,
                    fabric_server.EDITOR_EXPORT_API,
                    {"name": "Fresh Export", "payload": {"shapes": [{"type": 1}]}},
                )
                target = Path(saved["path"])
                marker = json.loads(output_marker.read_text(encoding="utf-8"))
                self.assertEqual(200, status)
                self.assertTrue(target.is_file())
                self.assertEqual(str(target.resolve()), marker["path"])


if __name__ == "__main__":
    unittest.main()
