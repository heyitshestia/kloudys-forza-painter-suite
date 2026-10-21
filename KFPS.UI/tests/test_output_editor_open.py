import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from test_editor_service import EditorService, DummyPreview, DummyDesktop, DummyLog, make_paths, wait_for
from kfps_ui.editor_launch import launch_editor, validate_request


class OutputEditorOpenTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.paths = make_paths(Path(temporary.name))
        for entry in ("KFPS.UI/editor.py", "KFPS.Editor/editor.py", "python/python.exe"):
            target = self.paths.app_root / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        self.service = EditorService(self.paths, DummyPreview(), DummyDesktop(), DummyLog())
        self.addCleanup(self.service.close)
        self.assertTrue(wait_for(lambda: not self.service._scan_running))

    def test_all_output_sources_forward_exact_json_without_writing_it(self):
        for source in ("generated", "editor", "exported", "library"):
            with self.subTest(source=source):
                target = self.paths.app_root / "imgs" / source / "Sub folder" / "Vinyl # & \u65e5\ud55c.JSON"
                target.parent.mkdir(parents=True)
                data = b'{"shapes":[{"type":1048677}]}'
                target.write_bytes(data)
                with patch("kfps_ui.editor_service.launch_editor", return_value="Opened") as launch:
                    self.service.launchJson(str(target))
                    self.assertTrue(wait_for(lambda: not self.service.launching))
                launch.assert_called_once_with(self.paths, "", "activate", self.service._cancel_event,
                                               json_id=target.relative_to(self.paths.app_root).as_posix())
                self.assertEqual(data, target.read_bytes())
                self.assertEqual("", self.service.lastError)

    def test_invalid_paths_do_not_spawn_or_fall_back_to_blank_editor(self):
        outside = self.paths.app_root / "outside.json"
        outside.write_text("{}")
        self.paths.exported_root.mkdir(parents=True)
        wrong_type = self.paths.exported_root / "image.png"
        wrong_type.touch()
        with patch("kfps_ui.editor_service.launch_editor") as launch:
            for target in ("", str(outside), str(wrong_type), str(self.paths.exported_root),
                           str(self.paths.exported_root / "missing.json")):
                with self.subTest(target=target):
                    self.service.launchJson(target)
                    self.assertFalse(self.service.launching)
                    self.assertTrue(self.service.lastError)
            launch.assert_not_called()

    def test_duplicate_click_while_starting_is_not_queued(self):
        target = self.paths.exported_root / "one.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}")
        with patch.object(self.service, "_start_thread") as start:
            self.service.launchJson(str(target))
            self.service.launchJson(str(target))
            self.assertEqual(1, start.call_count)

    def test_protocol_rejects_arbitrary_paths_and_conflicting_intents(self):
        for value in (None, 1, [], "../x.json", "/imgs/editor/x.json", "imgs/editor/../secret.json",
                      "imgs/editor//x.json", "imgs/editor/./x.json", "imgs/editor/x\x00.json",
                      "imgs/editor/x.json:stream", "imgs\\editor\\x.json", "runtime/x.json",
                      "imgs/library/x.png", "@exports/../x.json", "x" * 2049):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_request({"json": value})
        for conflict in ({"mode": "new"}, {"mode": "json"}, {"project": "x.fabric-project.json"}):
            with self.assertRaises(ValueError):
                validate_request({"json": "imgs/editor/x.json", **conflict})
        request = {"json": "imgs/library/Community/Name # \u65e5.json", "mode": "activate", "project": ""}
        self.assertEqual(request, validate_request(request))

    def test_existing_instance_receives_one_request_without_new_window(self):
        with patch("kfps_ui.editor_launch.forward_request", return_value=True) as forward, \
                patch("kfps_ui.editor_launch.wait_until_ready", return_value="Ready"), \
                patch("kfps_ui.editor_launch.subprocess.Popen") as spawn:
            launch_editor(self.paths, json_id="imgs/exported/My Vinyl.json", background=True)
        self.assertEqual({"project": "", "mode": "activate", "json": "imgs/exported/My Vinyl.json", "background": True},
                         forward.call_args.args[1])
        spawn.assert_not_called()

    def test_cold_launch_passes_json_once_and_no_extra_open_request(self):
        with patch("kfps_ui.editor_launch.forward_request", return_value=False) as forward, \
                patch("kfps_ui.editor_launch.wait_until_ready", return_value="Ready"), \
                patch("kfps_ui.editor_launch.subprocess.Popen") as spawn:
            launch_editor(self.paths, json_id="imgs/exported/My Vinyl.json", background=True)
        args = spawn.call_args.args[0]
        self.assertEqual("imgs/exported/My Vinyl.json", args[args.index("--json-id") + 1])
        self.assertEqual(1, args.count("--json-id"))
        self.assertEqual(1, forward.call_count)
        self.assertNotIn("--project-id", args)

    def test_launch_failure_is_exposed_for_outputs_status(self):
        target = self.paths.exported_root / "one.json"
        target.parent.mkdir(parents=True)
        target.write_text("{}")
        with patch("kfps_ui.editor_service.launch_editor", side_effect=RuntimeError("Editor busy")):
            self.service.launchJson(str(target))
            self.assertTrue(wait_for(lambda: not self.service.launching))
        self.assertEqual("Editor busy", self.service.lastError)

    def test_authenticated_json_reader_accepts_all_output_roots_only(self):
        from test_fabric_editor_server import RunningEditorServer, fabric_server as server
        from test_editor_server_paths import get
        paths = server.ServerPaths.for_runtime(self.paths.app_root, self.paths.runtime_root / "fabric-editor")
        payload = {"shapes": [{"type": 1048677, "data": [0, 0, 1, 1, 0, 0, 0], "color": [1, 2, 3, 255]}]}
        with patch.object(server, "ROOT", self.paths.app_root), \
                patch.object(server, "GENERATED_ROOT", self.paths.generated_root), \
                patch.object(server, "EXPORTED_JSON_ROOT", self.paths.exported_root), \
                RunningEditorServer(paths=paths) as instance:
            for source in ("generated", "editor", "exported", "library"):
                relative = f"imgs/{source}/Sub folder/Name # & \u65e5.JSON"
                target = self.paths.app_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(payload, get(instance, server.JSON_FILE_API, id=relative)["payload"])
            for relative in ("runtime/private.json", "imgs/library/../exported/x.json", "imgs/library/missing.json"):
                with self.assertRaises(urllib.error.HTTPError):
                    get(instance, server.JSON_FILE_API, id=relative)


if __name__ == "__main__":
    unittest.main()
