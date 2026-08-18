import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = ROOT / "tools" / "fabric-editor"
for entry in (str(ROOT), str(EDITOR_ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import start_fabric_editor as fabric_server


class RunningEditorServer:
    def __init__(self):
        self.httpd = fabric_server.EditorServer(
            ("127.0.0.1", 0),
            fabric_server.Handler,
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
                "/tools/fabric-editor/Resources/Vinyls/Primitives/1.svg"
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
