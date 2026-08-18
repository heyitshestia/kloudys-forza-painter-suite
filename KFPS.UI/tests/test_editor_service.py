import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = UI_ROOT.parent
sys.path.insert(0, str(UI_ROOT / "src"))

from PySide6.QtCore import QCoreApplication

from kfps_ui.app_paths import AppPaths
from kfps_ui.editor_service import EditorService


APP = QCoreApplication.instance() or QCoreApplication([])


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    APP.processEvents()
    return bool(predicate())


class DummyPreview:
    def __init__(self):
        self.requests = []

    def preview_for_json(self, path, source=""):
        self.requests.append((str(path), str(source)))
        return "file:///editor-project-preview.png"


class SlowPreview:
    def __init__(self):
        self.requests = []
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()

    def preview_for_json(self, path, source=""):
        with self.lock:
            self.requests.append(str(path))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1
        return f"file:///{Path(path).name}.png"


class DummyDesktop:
    def __init__(self):
        self.opened = []

    def openFolder(self, path):
        self.opened.append(str(path))


class DummyLog:
    def __init__(self):
        self.messages = []

    def append(self, message, level="info"):
        self.messages.append((str(message), str(level)))


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.payload


def make_paths(root: Path) -> AppPaths:
    return AppPaths(
        app_root=root,
        ui_root=UI_ROOT,
        qml_root=UI_ROOT / "qml",
        asset_root=UI_ROOT / "assets",
        runtime_root=root / "runtime",
        bundled_python=root / "python" / "python.exe",
    )


class EditorProjectManagerTests(unittest.TestCase):
    def test_discovers_filters_selects_and_opens_projects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = make_paths(root)
            paths.project_root.mkdir(parents=True)
            alpha = paths.project_root / "Alpha.fabric-project.json"
            beta = paths.project_root / "Beta.fabric-project.json"
            broken = paths.project_root / "Broken.fabric-project.json"
            alpha.write_text(
                json.dumps({"shapes": [{"type": 1}, {"type": 2}, {"type": 3}]}),
                encoding="utf-8",
            )
            beta.write_text(
                json.dumps(
                    {
                        "layer_count": 2,
                        "layers": [{"type": 1}, {"type": 2}],
                        "editor_source_overlay": {
                            "data_url": "data:image/png;base64," + ("A" * 70000)
                        },
                    }
                ),
                encoding="utf-8",
            )
            broken.write_text("{not-json", encoding="utf-8")

            preview = DummyPreview()
            desktop = DummyDesktop()
            service = EditorService(paths, preview, desktop, DummyLog())
            self.addCleanup(service.close)

            self.assertEqual(3, service.projectCount)
            by_name = {row["name"]: row for row in service.projectModel.rows}
            self.assertEqual(3, by_name["Alpha"]["shapeCount"])
            self.assertEqual("3 shapes", by_name["Alpha"]["shapeLabel"])
            self.assertEqual(2, by_name["Beta"]["shapeCount"])
            self.assertEqual(-1, by_name["Broken"]["shapeCount"])

            service.searchText = "3 shapes"
            self.assertEqual(["Alpha"], [row["name"] for row in service.projectModel.rows])
            service.select(0)
            self.assertTrue(
                wait_for(lambda: not service.previewLoading)
            )
            self.assertEqual(str(alpha), service.selectedPath)
            self.assertEqual("Alpha", service.selectedName)
            self.assertEqual("3", service.selectedShapes)
            self.assertEqual("file:///editor-project-preview.png", service.previewUrl)
            self.assertEqual([(str(alpha), "")], preview.requests)

            service.openProjects()
            self.assertEqual([str(paths.project_root)], desktop.opened)

    def test_reset_tutorial_removes_the_runtime_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            marker = (
                paths.runtime_root
                / "fabric-editor"
                / "startup-help-confirmed.json"
            )
            marker.parent.mkdir(parents=True)
            marker.write_text('{"confirmed": true}', encoding="utf-8")
            service = EditorService(
                paths,
                DummyPreview(),
                DummyDesktop(),
                DummyLog(),
            )
            self.addCleanup(service.close)

            service.resetTutorial()

            self.assertFalse(marker.exists())
            self.assertIn("next editor launch", service.status)
            self.assertEqual("", service.lastError)

    def test_preview_rendering_is_serialized_and_keeps_the_latest_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            preview = SlowPreview()
            service = EditorService(
                paths,
                preview,
                DummyDesktop(),
                DummyLog(),
            )
            self.addCleanup(service.close)
            first = str(paths.project_root / "First.fabric-project.json")
            second = str(paths.project_root / "Second.fabric-project.json")
            service._selected = first
            first_thread = threading.Thread(
                target=service._preview_worker,
                args=(first,),
            )
            first_thread.start()
            self.assertTrue(wait_for(lambda: preview.active == 1))
            service._selected = second
            second_thread = threading.Thread(
                target=service._preview_worker,
                args=(second,),
            )
            second_thread.start()
            first_thread.join()
            second_thread.join()
            self.assertTrue(wait_for(lambda: service.previewUrl.endswith("Second.fabric-project.json.png")))

            self.assertEqual(1, preview.max_active)
            self.assertEqual([first, second], preview.requests)


class EditorServerReuseTests(unittest.TestCase):
    def _write_marker(self, paths: AppPaths, root: Path, port: int = 48123):
        marker = paths.runtime_root / "fabric-editor" / "server.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "service": "kfps-fabric-editor",
                    "pid": 1234,
                    "port": port,
                    "root": str(root),
                    "session_token": "test_editor_session_token_1234567890",
                }
            ),
            encoding="utf-8",
        )

    def test_active_server_requires_matching_root_and_health_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = make_paths(root)
            self._write_marker(paths, root)
            service = EditorService(
                paths,
                DummyPreview(),
                DummyDesktop(),
                DummyLog(),
            )
            self.addCleanup(service.close)
            health = FakeResponse({"ok": True, "root": str(root)})

            with patch(
                "kfps_ui.editor_service.urllib.request.urlopen",
                return_value=health,
            ) as request:
                url = service._active_server_url()

            self.assertEqual(
                "http://127.0.0.1:48123/tools/fabric-editor/index.html#session=test_editor_session_token_1234567890",
                url,
            )
            request.assert_called_once_with(
                "http://127.0.0.1:48123/api/fabric-editor/health",
                timeout=0.65,
            )

            self._write_marker(paths, root / "another-install")
            with patch(
                "kfps_ui.editor_service.urllib.request.urlopen"
            ) as foreign_request:
                self.assertEqual("", service._active_server_url())
            foreign_request.assert_not_called()

    def test_launch_worker_reuses_server_and_encodes_project_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = make_paths(root)
            service = EditorService(
                paths,
                DummyPreview(),
                DummyDesktop(),
                DummyLog(),
            )
            self.addCleanup(service.close)
            completed = []
            service.launchCompleted.connect(
                lambda ok, url, message: completed.append((ok, url, message))
            )

            with (
                patch.object(
                    service,
                    "_active_server_url",
                    return_value=(
                        "http://127.0.0.1:48123/"
                        "tools/fabric-editor/index.html"
                        "#session=test_editor_session_token_1234567890"
                    ),
                ),
                patch("kfps_ui.editor_service.subprocess.Popen") as popen,
                patch(
                    "kfps_ui.editor_service.QDesktopServices.openUrl",
                    return_value=True,
                ),
            ):
                service._launch_worker(
                    root / "tools" / "fabric-editor" / "start_fabric_editor.py",
                    "Folder/My Project.fabric-project.json",
                    "",
                )

            popen.assert_not_called()
            self.assertEqual(1, len(completed))
            self.assertTrue(completed[0][0])
            self.assertEqual(
                completed[0][1],
                "http://127.0.0.1:48123/tools/fabric-editor/index.html"
                "?project=Folder%2FMy%20Project.fabric-project.json"
                "#session=test_editor_session_token_1234567890",
            )
            self.assertEqual("Editor opened in your browser.", service.status)
            self.assertTrue(service.running)


if __name__ == "__main__":
    unittest.main()
