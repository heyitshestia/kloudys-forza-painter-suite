import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui import editor_launch as launch
from kfps_editor import ipc


class EditorLaunchHardeningTests(unittest.TestCase):
    def socket(self, reply=b"ok\n"):
        socket = Mock()
        socket.waitForConnected.return_value = True
        socket.bytesAvailable.return_value = len(reply)
        socket.readAll.return_value = reply
        socket.waitForReadyRead.return_value = False
        socket.socketDescriptor.return_value = -1
        return socket

    def test_live_rejected_or_bad_ack_never_starts_second_process(self):
        for reply in (b"error\n", b"busy\n", b"bad\n", b"x" * 65):
            with self.subTest(reply=reply), patch.object(ipc, "_local_socket", return_value=self.socket(reply)), patch.object(launch.subprocess, "Popen") as spawn:
                with self.assertRaises(launch.EditorConnectionError):
                    launch.launch_editor(Mock(app_root=Path("A"), runtime_root=Path("R")))
                spawn.assert_not_called()

    def test_lost_ack_never_reports_absent_instance(self):
        with patch.object(ipc, "_local_socket", return_value=self.socket(b"")), patch.object(ipc.time, "monotonic", side_effect=[0, 0, 0, 2]):
            with self.assertRaisesRegex(launch.EditorConnectionError, "not responded"):
                launch.forward_request("test", {"mode": "new"})

    def test_absent_instance_can_start(self):
        socket = self.socket()
        socket.waitForConnected.return_value = False
        with patch.object(ipc, "_local_socket", return_value=socket):
            self.assertFalse(launch.forward_request("test", {}))

    def test_actual_ready_waits_past_ipc_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            with patch.object(ipc, "read_desktop_state", side_effect=[{"state": "starting"}, {"state": "ready"}]), patch.object(ipc.time, "sleep") as sleep:
                self.assertIn("opened", launch.wait_until_ready(runtime, "test"))
                sleep.assert_called_once()

    def test_native_startup_failure_is_explained(self):
        with patch.object(ipc, "read_desktop_state", return_value={"state": "failed", "error": "Missing runtime"}):
            with self.assertRaisesRegex(RuntimeError, "Missing runtime"):
                launch.wait_until_ready(Path("runtime"), "test")

    def test_bootstrap_error_must_match_child_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            for pid in (12, 13):
                (runtime / "desktop-startup-error.json").write_text(json.dumps({"pid": pid, "error": "Qt import failed"}))
                process = Mock(pid=12)
                process.poll.return_value = 1
                with self.assertRaises(RuntimeError) as error:
                    launch.wait_until_ready(runtime, "test", process=process)
                self.assertEqual(pid == 12, "Qt import failed" in str(error.exception))

    def test_cancel_leaves_independent_child_alone(self):
        event = threading.Event()
        event.set()
        process = Mock()
        self.assertIn("independently", launch.wait_until_ready(Path("runtime"), "test", event, process))
        process.terminate.assert_not_called()
        process.kill.assert_not_called()

    def test_wrong_instance_marker_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            (runtime / "desktop.json").write_text(json.dumps({"instance": "other", "state": "ready"}))
            self.assertEqual({}, launch.read_desktop_state(runtime, "test"))

    def test_cold_start_passes_project_once_and_hides_child_console(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "KFPS.Editor").mkdir()
            (root / "KFPS.Editor" / "editor.py").touch()
            (root / "python").mkdir()
            (root / "python/python.exe").touch()
            paths = Mock(app_root=root, runtime_root=root / "runtime", python_executable=sys.executable)
            with patch.object(launch, "forward_request", return_value=False), patch.object(launch, "wait_until_ready", return_value="ready") as wait, patch.object(launch.subprocess, "Popen") as spawn:
                self.assertEqual("ready", launch.launch_editor(paths, "My Project.fabric-project.json"))
                args = spawn.call_args.args[0]
                self.assertEqual(str(root / "python/python.exe"), args[0])
                self.assertEqual(["-I", "-B", "-X"], args[1:4])
                self.assertIn(str(root / "KFPS.Editor/editor.py"), args)
                self.assertNotEqual(sys.executable, args[0])
                self.assertEqual(1, args.count("My Project.fabric-project.json"))
                self.assertIn("--from-kfps", args)
                self.assertFalse(wait.call_args.kwargs["connected"])


if __name__ == "__main__":
    unittest.main()
