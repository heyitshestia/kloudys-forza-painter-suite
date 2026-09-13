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

from PySide6.QtCore import QCoreApplication, QTimer

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
    def test_editor_change_markers_refresh_projects_and_emit_output_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = make_paths(root)
            service = EditorService(paths, DummyPreview(), DummyDesktop(), DummyLog())
            self.addCleanup(service.close)
            self.assertTrue(wait_for(lambda: not service._scan_running))
            output_events = []
            service.editorOutputsChanged.connect(lambda: output_events.append(True))

            project = paths.project_root / "Marker Project.fabric-project.json"
            project.parent.mkdir(parents=True, exist_ok=True)
            project.write_text(json.dumps({"layer_count": 1, "shapes": [{"type": 1}]}), encoding="utf-8")
            service._project_change_marker.write_text("{}", encoding="utf-8")
            service._output_change_marker.write_text("{}", encoding="utf-8")
            service._poll_editor_changes()

            self.assertEqual([True], output_events)
            self.assertTrue(wait_for(lambda: service.projectCount == 1 and not service._scan_running))
            self.assertEqual("Marker Project", service.projectModel.row(0)["name"])

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
            self.assertTrue(wait_for(lambda: not service._scan_running))

            self.assertTrue(wait_for(lambda: service.projectCount == 3 and not service._scan_running))
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
            self.assertTrue(wait_for(lambda: not service._scan_running))

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
            self.assertTrue(wait_for(lambda: not service._scan_running))
            first = str(paths.project_root / "First.fabric-project.json")
            second = str(paths.project_root / "Second.fabric-project.json")
            self.assertTrue(wait_for(lambda: not service._scan_running))
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

    def test_scan_is_background_coalesced_cached_and_owner_thread_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            paths.project_root.mkdir(parents=True)
            for index in range(200):
                (paths.project_root / f"Project {index}.fabric-project.json").write_text(
                    json.dumps({"shapes": [{}] * (index % 10)}), encoding="utf-8")
            entered, release = threading.Event(), threading.Event()
            calls, scans, updates, beats = [], [], [], []
            original_count, original_scan = EditorService._project_shape_count, EditorService._scan_projects
            owner = threading.get_ident()
            def count(service, path):
                calls.append(threading.get_ident())
                if len(calls) == 1:
                    entered.set()
                    release.wait(3)
                return original_count(service, path)
            def scan(service):
                scans.append(threading.get_ident())
                return original_scan(service)
            with patch.object(EditorService, "_project_shape_count", count), patch.object(EditorService, "_scan_projects", scan):
                service = EditorService(paths, DummyPreview(), DummyDesktop(), DummyLog())
                timer = QTimer(); timer.setInterval(5); timer.timeout.connect(lambda: beats.append(True)); timer.start()
                service.changed.connect(lambda: updates.append(threading.get_ident()))
                try:
                    self.assertTrue(entered.wait(1))
                    for _ in range(60):
                        service.refresh()
                    service.searchText = "Project 19"
                    self.assertTrue(wait_for(lambda: len(beats) >= 5))
                    self.assertEqual(1, len(scans), "Repeated requests spawned simultaneous scans")
                    release.set()
                    self.assertTrue(wait_for(lambda: not service._scan_running and service.projectCount == 200, timeout=10),
                                    (len(scans), len(calls), service._scan_generation, service._scan_running, service.projectCount, service.log.messages))
                    self.assertEqual(2, len(scans), "Newest refresh was not coalesced into one follow-up scan")
                    self.assertEqual(200, len(calls), "Unchanged projects were reparsed on the second scan")
                    self.assertTrue(all(thread != owner for thread in calls))
                    self.assertTrue(all(thread == owner for thread in updates))
                    self.assertEqual(11, len(service.projectModel.rows))
                    project = paths.project_root / "Project 19.fabric-project.json"
                    project.write_text(json.dumps({"shapes": [{}] * 12}), encoding="utf-8")
                    service.refresh()
                    self.assertTrue(wait_for(lambda: not service._scan_running))
                    self.assertEqual(201, len(calls))
                    self.assertEqual(12, next(row["shapeCount"] for row in service.projectModel.rows if row["name"] == "Project 19"))
                finally:
                    release.set(); timer.stop(); service.close()

    def test_scan_start_failure_can_retry_and_close_ignores_late_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            service = EditorService(paths, DummyPreview(), DummyDesktop(), DummyLog())
            try:
                self.assertTrue(wait_for(lambda: not service._scan_running))
                with patch.object(service, "_start_thread", side_effect=RuntimeError("No worker")):
                    service.refresh()
                self.assertFalse(service._scan_running)
                service.refresh()
                self.assertTrue(wait_for(lambda: not service._scan_running))
                service.close()
                service._finish_scan(service._scan_generation, [{"invalid": "late"}], "")
                self.assertEqual(0, service.projectCount)
            finally:
                service.close()


class EditorWindowLaunchTests(unittest.TestCase):
    def test_failed_worker_start_is_retryable_and_activate_preserves_canvas(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            entry = paths.app_root / "KFPS.UI" / "editor.py"
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.touch()
            service = EditorService(paths, DummyPreview(), DummyDesktop(), DummyLog())
            self.addCleanup(service.close)
            self.assertTrue(wait_for(lambda: not service._scan_running))
            with patch.object(service, "_start_thread", side_effect=RuntimeError("No worker available")):
                service.activate()
            self.assertFalse(service.launching)
            self.assertIn("No worker", service.lastError)
            with patch.object(service, "_start_thread") as start:
                service.activate()
                self.assertTrue(service.launching)
                self.assertEqual("", service.lastError)
                self.assertEqual("activate", start.call_args.kwargs["args"][2])

    def test_launch_worker_preserves_project_and_reports_window_status(self):
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
            self.assertTrue(wait_for(lambda: not service._scan_running))
            completed = []
            service.launchCompleted.connect(
                lambda ok, url, message: completed.append((ok, url, message))
            )

            with patch("kfps_ui.editor_service.launch_editor", return_value="Existing window activated") as launch:
                service._launch_worker(
                    root / "KFPS.UI" / "editor.py",
                    "Folder/My Project.fabric-project.json",
                    "",
                )

            launch.assert_called_once_with(paths, "Folder/My Project.fabric-project.json", "activate", service._cancel_event)
            self.assertEqual(1, len(completed))
            self.assertTrue(completed[0][0])
            self.assertEqual("", completed[0][1])
            self.assertEqual("Editor opened in its own window.", service.status)
            self.assertTrue(service.running)

    def test_all_launch_actions_and_close_keep_editor_ownership_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = make_paths(Path(temporary))
            service = EditorService(paths, DummyPreview(), DummyDesktop(), DummyLog())
            self.addCleanup(service.close)
            self.assertTrue(wait_for(lambda: not service._scan_running))
            service._selected = "chosen-project"
            with patch.object(service, "_launch") as launch:
                service.launch()
                service.launchJsonBrowser()
                service.launchSelected()
                self.assertEqual([("", "new"), ("", "json"), ("chosen-project", "")], [call.args for call in launch.call_args_list])
            with patch("kfps_ui.editor_service.launch_editor") as launch:
                service.close()
                service._launch_worker(Path("editor.py"), "", "new")
                launch.assert_not_called()
            self.assertTrue(service._cancel_event.is_set())


if __name__ == "__main__":
    unittest.main()
