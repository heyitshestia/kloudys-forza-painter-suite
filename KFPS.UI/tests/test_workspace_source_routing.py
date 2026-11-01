"""Source routing hints never replace descriptor or named-pipe admission."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from _test_evidence import evidence_directory

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/livery-studio/src"), str(ROOT / "KFPS.Editor/src"), str(ROOT / "KFPS.UI/src")]

from kfps_editor.activation import process_running
from kfps_editor.ipc import EditorConnectionError, instance_name
from kfps_livery_lab import source_editor


class WorkspaceSourceRoutingTests(unittest.TestCase):
    def setUp(self):
        original_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        evidence = evidence_directory("workspace-source-routing")
        evidence.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="workspace-source-routing-", dir=evidence)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "root"
        self.lab = self.root / "tools/livery-studio"
        self.job = "b" * 32
        self.runtime = self.lab / "runs/session/source-editor" / self.job / "editor"
        self.runtime.mkdir(parents=True)
        self.marker = self.root / "runtime/workspace/studio-session.json"
        self.marker.parent.mkdir(parents=True)
        self.url = "http://127.0.0.1:32100/" + "a" * 43 + "/"
        self.descriptor = {
            "format": "kfps-studio-source-edit-v1", "jobId": self.job,
            "projectId": source_editor.PROJECT_ID, "name": "Fixture",
            "returnUrl": self.url + "api/source-editor/" + self.job + "/return",
            "secret": "c" * 43, "expiresAt": time.time() + 60,
        }
        self.write_descriptor()
        self.hint = {"format": "kfps-workspace-studio/1", "pid": os.getpid(),
                     "session": hashlib.sha256(self.url.encode("utf-8")).hexdigest()}
        self.write_hint()
        self.patches = self.enterContext(ExitStack())
        self.patches.enter_context(patch.object(source_editor, "LAB", self.lab))
        self.chrome = self.patches.enter_context(patch("kfps_editor.launch_preferences.use_chrome", return_value=False))
        self.live = self.patches.enter_context(patch("kfps_editor.activation.process_running", return_value=True))
        self.forward = self.patches.enter_context(patch("kfps_editor.ipc.forward_before_qt", return_value=True))
        self.wait_ready = self.patches.enter_context(patch("kfps_editor.ipc.wait_until_ready"))
        baseline = SimpleNamespace(launch_command=Mock(return_value=(
            [str(self.root / "python/python.exe"), "-I", "-B", "-X", "pycache_prefix=old",
             str(self.root / "KFPS.Editor/editor.py")], {})))
        standalone = SimpleNamespace(isolated_environment=Mock(return_value={"ROUTING_TEST": "1"}))
        self.modules = self.patches.enter_context(patch.object(source_editor, "_module",
            side_effect=lambda name, *_: {"baseline": baseline, "studio_window": standalone}[name]))
        self.spawn = self.patches.enter_context(patch.object(source_editor.subprocess, "Popen",
            return_value=SimpleNamespace(pid=12345, poll=lambda: None)))
        (self.runtime / "desktop.json").write_text(json.dumps({"pid": 12345, "state": "ready"}), encoding="utf-8")

    def write_hint(self, value=None):
        self.marker.write_text(json.dumps(self.hint if value is None else value), encoding="utf-8")

    def write_descriptor(self):
        (self.runtime / source_editor.DESCRIPTOR).write_text(json.dumps(self.descriptor), encoding="utf-8")

    def launch(self, cancelled=None):
        source_editor._launch_editor(self.root, self.runtime, cancelled or threading.Event())

    def assert_standalone(self):
        self.launch()
        self.forward.assert_not_called()
        self.wait_ready.assert_not_called()
        self.spawn.assert_called_once()
        command = self.spawn.call_args.args[0]
        self.assertIn("-I", command)
        self.assertIn("-B", command)
        self.assertIn("pycache_prefix=" + str(self.runtime / "bytecode"), command)
        self.assertEqual(self.spawn.call_args.kwargs["cwd"], self.root)
        self.assertEqual(self.spawn.call_args.kwargs["env"], {"ROUTING_TEST": "1"})

    def test_matching_live_native_owner_forwards_in_background(self):
        self.launch()
        self.forward.assert_called_once_with(instance_name(self.root, self.root / "runtime/workspace"),
            {"mode": "activate", "project": (self.runtime / "projects" / source_editor.PROJECT_ID).relative_to(self.root).as_posix(),
             "background": True}, timeout=8000)
        self.wait_ready.assert_called_once()
        self.assertTrue(self.wait_ready.call_args.kwargs["background"])
        self.spawn.assert_not_called()
        self.modules.assert_not_called()

    def test_missing_marker_keeps_unowned_studio_standalone(self):
        self.marker.unlink()
        self.assert_standalone()

    def test_other_studio_session_keeps_standalone(self):
        self.hint["session"] = hashlib.sha256(self.url.replace(":32100/", ":32101/").encode()).hexdigest()
        self.write_hint()
        self.assert_standalone()

    def test_other_token_keeps_standalone_even_on_same_port(self):
        self.hint["session"] = hashlib.sha256(self.url.replace("a" * 43, "d" * 43).encode()).hexdigest()
        self.write_hint()
        self.assert_standalone()

    def test_dead_owner_keeps_standalone(self):
        self.live.return_value = False
        self.assert_standalone()

    def test_unknown_process_state_is_not_ownership(self):
        self.live.return_value = None
        self.assert_standalone()

    def test_pid_probe_failure_keeps_standalone(self):
        self.live.side_effect = OSError("probe unavailable")
        self.assert_standalone()

    def test_editor_chrome_preference_does_not_consult_hint(self):
        self.chrome.return_value = True
        with patch.object(source_editor, "_customization_json", side_effect=AssertionError("Unexpected hint read")):
            self.assert_standalone()

    def test_live_pid_check_uses_existing_windows_probe(self):
        self.live.side_effect = process_running
        self.assertTrue(source_editor._workspace_owns_source(self.root, self.runtime))
        self.live.assert_called_once_with(os.getpid())

    def test_no_fallback_after_rejected_or_uncertain_ack(self):
        for message in ("Rejected ACK", "Timeout after request was written"):
            with self.subTest(message=message):
                self.forward.side_effect = EditorConnectionError(message)
                with self.assertRaisesRegex(EditorConnectionError, message):
                    self.launch()
                self.spawn.assert_not_called()
                self.modules.assert_not_called()
                self.wait_ready.assert_not_called()

    def test_no_fallback_after_ack_when_readiness_fails(self):
        self.wait_ready.side_effect = RuntimeError("Editor did not become ready")
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            self.launch()
        self.spawn.assert_not_called()
        self.modules.assert_not_called()

    def test_pipe_absent_before_delivery_uses_existing_standalone_path(self):
        self.forward.return_value = False
        self.launch()
        self.forward.assert_called_once()
        self.wait_ready.assert_not_called()
        self.spawn.assert_called_once()

    def test_cancelled_launch_does_not_route_or_spawn(self):
        cancelled = threading.Event()
        cancelled.set()
        self.launch(cancelled)
        self.forward.assert_not_called()
        self.spawn.assert_not_called()
        self.live.assert_not_called()

    def test_marker_schema_and_value_types_are_strict(self):
        invalid = [None, [], {}, dict(self.hint, format="other"), dict(self.hint, extra="unexpected"),
                   dict(self.hint, pid=True), dict(self.hint, pid=0), dict(self.hint, pid=-1),
                   dict(self.hint, pid=0xFFFFFFFF), dict(self.hint, pid="123"), dict(self.hint, pid=1.5),
                   dict(self.hint, session=None), dict(self.hint, session="a" * 63),
                   dict(self.hint, session="g" * 64), dict(self.hint, session="a" * 65)]
        for value in invalid:
            with self.subTest(value=value):
                self.marker.write_text(json.dumps(value), encoding="utf-8")
                self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))
        self.live.assert_not_called()

    def test_marker_json_is_bounded_and_rejects_duplicates_and_nonfinite(self):
        body = json.dumps(self.hint).encode()
        for invalid in (b"", b"{", b"\xff", b"[" * 1500 + b"]" * 1500,
                        b'{"pid":1,"pid":2}', b'{"pid":NaN}', body + b" " * 4096):
            with self.subTest(size=len(invalid)):
                self.marker.write_bytes(invalid)
                self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))
        self.marker.write_bytes(body + b" " * (4096 - len(body)))
        self.assertTrue(source_editor._workspace_owns_source(self.root, self.runtime))
        self.marker.write_bytes(body + b" " * (4097 - len(body)))
        self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))

    def test_marker_read_failure_keeps_standalone(self):
        with patch.object(source_editor, "_customization_json", side_effect=PermissionError("denied")):
            self.assert_standalone()

    def test_marker_directory_is_not_a_file(self):
        self.marker.unlink()
        self.marker.mkdir()
        self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))

    def test_hardlinked_marker_is_not_trusted(self):
        alias = self.marker.with_name("alias.json")
        os.link(self.marker, alias)
        self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))

    def test_redirected_marker_or_parent_is_not_trusted(self):
        real_symlink = Path.is_symlink
        for redirect in (self.marker, self.marker.parent):
            with self.subTest(path=redirect), patch.object(Path, "is_symlink",
                    lambda path: path == redirect or real_symlink(path)):
                self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))
        with patch.object(Path, "is_junction", lambda path: path == self.marker.parent):
            self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))

    def test_descriptor_must_exist_and_pass_existing_validation(self):
        for change in ({"expiresAt": 1}, {"returnUrl": self.descriptor["returnUrl"] + "?query=1"},
                       {"returnUrl": self.descriptor["returnUrl"].replace("127.0.0.1", "localhost")},
                       {"jobId": "e" * 32}):
            with self.subTest(change=change):
                original = dict(self.descriptor)
                self.descriptor.update(change)
                self.write_descriptor()
                self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))
                self.descriptor = original
        (self.runtime / source_editor.DESCRIPTOR).unlink()
        self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))
        self.live.assert_not_called()

    def test_hint_contains_only_digest_and_is_never_modified_by_reader(self):
        before = self.marker.read_bytes()
        self.assertNotIn(self.url.encode(), before)
        self.assertNotIn(self.descriptor["secret"].encode(), before)
        self.assertTrue(source_editor._workspace_owns_source(self.root, self.runtime))
        self.assertEqual(self.marker.read_bytes(), before)

    def test_parent_writer_digest_and_ownership_cleanup_match_reader(self):
        from PySide6.QtCore import QObject, QUrl
        from shiboken6 import delete
        from kfps_ui.workspace_controller import WorkspaceController
        controller, shell = QObject(), QObject()
        self.addCleanup(delete, controller)
        self.addCleanup(delete, shell)
        controller.shell, controller.closed = shell, False
        controller._studio_marker, controller._studio_session = self.marker, None
        controller.paths = SimpleNamespace(app_root=self.root)
        controller._marker_directory_valid = lambda: WorkspaceController._marker_directory_valid(controller)
        host = SimpleNamespace(page=SimpleNamespace(url=lambda: QUrl(self.url + "?ignored=1#vinyl=" + "d" * 32)))
        shell.owners = {"Studio": host}
        WorkspaceController._write_studio_owner(controller, host)
        self.assertEqual(json.loads(self.marker.read_text(encoding="utf-8")), self.hint)
        self.assertTrue(source_editor._workspace_owns_source(self.root, self.runtime))
        old_host = SimpleNamespace()
        WorkspaceController._clear_studio_owner(controller, old_host)
        self.assertTrue(self.marker.exists())
        self.write_hint(dict(self.hint, pid=os.getpid() + 1))
        WorkspaceController._clear_studio_owner(controller, host)
        self.assertTrue(self.marker.exists())
        WorkspaceController._write_studio_owner(controller, host)
        WorkspaceController._clear_studio_owner(controller, host)
        self.assertFalse(self.marker.exists())
        self.assertFalse(source_editor._workspace_owns_source(self.root, self.runtime))


if __name__ == "__main__":
    unittest.main()
