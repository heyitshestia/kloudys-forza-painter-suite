"""Verify failed CLI launches release real locks BEFORE displaying their error."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from PySide6.QtWidgets import QApplication
from shiboken6 import delete
from kfps_editor import cli
from kfps_editor.host import EditorDesktop
from kfps_editor.instance_lock import EditorInstanceLock
from kfps_editor.update_guard import acquire_update_guard

APP = QApplication.instance() or QApplication([])


@unittest.skipUnless(os.name == "nt", "Windows startup ownership")
class StartupErrorTests(unittest.TestCase):
    def test_partial_start_releases_before_error_dialog_or_main_app_return(self):
        run = ROOT / "runtime/test-runs/2026-09-14-editor-startup/startup-errors"
        run.mkdir(parents=True, exist_ok=True)
        for from_kfps, denied_log in ((False, False), (True, False), (True, True)):
            with self.subTest(from_kfps=from_kfps, denied_log=denied_log), tempfile.TemporaryDirectory(dir=run) as directory:
                runtime = Path(directory)
                state = runtime / "update-state"
                guard = acquire_update_guard(state)
                hosts, dialogs = [], []

                def fail_start(host, request):
                    hosts.append(host)
                    self.assertTrue(host.lock.tryLock(0))
                    raise OSError("Injected partial startup failure")

                def verify_released(*args):
                    other = EditorInstanceLock(runtime)
                    self.assertTrue(other.tryLock(0))
                    other.unlock()
                    lease = acquire_update_guard(state)
                    lease.Close()
                    dialogs.append(True)

                args = ["editor.py", "--runtime-root", str(runtime)] + (["--from-kfps"] if from_kfps else [])
                try:
                    with (patch.object(sys, "argv", args),
                          patch("kfps_editor.bootstrap_log.open_desktop_log", side_effect=PermissionError("Injected locked log")) if denied_log else nullcontext(),
                          patch("kfps_editor.baseline.CONTRACT", "missing-test-baseline.json"),
                          patch("kfps_editor.baseline.development_root", return_value=True),
                          patch("kfps_editor.baseline.verify", return_value={}),
                          patch("kfps_editor.startup.acquire_or_forward", return_value=guard),
                          patch("kfps_editor.ipc.forward_request", return_value=False),
                          patch("tools.source_download_guard.evaluate_source_download_guard", return_value=SimpleNamespace(blocked=False)),
                          patch("PySide6.QtWidgets.QApplication", return_value=APP),
                          patch("PySide6.QtWidgets.QMessageBox.critical", side_effect=verify_released),
                          patch.object(EditorDesktop, "start", fail_start)):
                        self.assertEqual(cli.main(), 1)
                    self.assertEqual(len(dialogs), 0 if from_kfps else 1)
                    verify_released()
                    self.assertIn("Injected partial startup failure", (runtime / "desktop-startup-error.json").read_text())
                finally:
                    for host in hosts:
                        host.shutdown()
                        delete(host)
                    guard.Close()


if __name__ == "__main__":
    unittest.main()
