import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui.editor_launch import instance_name, launch_editor, validate_request
from kfps_ui.editor_update_guard import acquire_update_guard, updater_state_root


class EditorDesktopContractTests(unittest.TestCase):
    def test_request_preserves_relative_unicode_project_names(self):
        request = {"project": "Folder/My Project.fabric-project.json", "mode": "activate"}
        self.assertEqual(request, validate_request(request))

    def test_request_rejects_non_project_paths_and_unknown_operations(self):
        for payload in ([], {"mode": []}, {"mode": "delete"}, {"extra": True}, {"project": "../x.fabric-project.json"}, {"project": "C:/x.fabric-project.json"}, {"project": "/x.fabric-project.json"}, {"project": "x.json"}, {"project": "a\\x.fabric-project.json"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_request(payload)

    def test_singleton_is_scoped_to_installation_and_storage(self):
        root = Path(tempfile.gettempdir())
        first = instance_name(root / "A", root / "runtime")
        self.assertEqual(first, instance_name(root / "A", root / "runtime"))
        self.assertNotEqual(first, instance_name(root / "B", root / "runtime"))
        self.assertNotEqual(first, instance_name(root / "A", root / "other"))

    def test_existing_editor_is_reused_without_child_process(self):
        paths = Mock(app_root=Path("installation"), runtime_root=Path("runtime"))
        with (patch("kfps_ui.editor_launch.forward_request", return_value=True) as forward,
              patch("kfps_ui.editor_launch.wait_until_ready", return_value="Editor opened in its own window.") as ready,
              patch("kfps_ui.editor_launch.subprocess.Popen") as spawn):
            launch_editor(paths, "test.fabric-project.json", "activate")
            spawn.assert_not_called()
            self.assertEqual("test.fabric-project.json", forward.call_args.args[1]["project"])
            ready.assert_called_once_with(paths.runtime_root / "fabric-editor",
                                          instance_name(paths.app_root, paths.runtime_root / "fabric-editor"),
                                          None, background=False)

    def test_update_does_not_launch_or_quit_main_while_editor_open(self):
        from kfps_ui.update_service import UpdateService
        log = Mock()
        service = UpdateService(Mock(), log)
        with patch("kfps_ui.update_service.editor_is_open", return_value=True), patch("kfps_ui.update_service.subprocess.Popen") as spawn, patch("kfps_ui.update_service.QCoreApplication.quit") as quit_app:
            service.startUpdate()
            spawn.assert_not_called()
            quit_app.assert_not_called()
            self.assertIn("Close the KFPS Editor", log.append.call_args.args[0])

    @unittest.skipUnless(os.name == "nt", "Windows updater lock contract")
    def test_guard_excludes_updater_and_releases_without_deleting_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            first = acquire_update_guard(state)
            try:
                with self.assertRaisesRegex(RuntimeError, "updating"):
                    acquire_update_guard(state)
            finally:
                first.Close()
            second = acquire_update_guard(state)
            second.Close()
            self.assertTrue((state / "updater.lock").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows updater identity")
    def test_guard_identity_matches_bootstrap_normalization(self):
        root = Path(tempfile.gettempdir()).resolve()
        expected = hashlib.sha256(root.as_posix().lower().encode()).hexdigest()
        self.assertEqual(expected, updater_state_root(root / "KloudysFH6Painter").name)
