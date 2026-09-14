"""Actual Windows ownership, stale Qt markers and crash/race regression tests."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor.instance_lock import EditorInstanceLock
from kfps_editor import ipc, startup
from kfps_editor.activation import process_running

OUT = ROOT / "runtime/test-runs/2026-09-14-editor-startup/unit"
OUT.mkdir(parents=True, exist_ok=True)
CHILD = '''
import os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from kfps_editor.instance_lock import EditorInstanceLock
lock=EditorInstanceLock(Path(sys.argv[2]))
if not lock.tryLock(): sys.exit(3)
print(os.getpid(),flush=True)
if sys.argv[3]=='crash': os._exit(0)
time.sleep(3)
lock.unlock()
'''


@unittest.skipUnless(os.name == "nt", "Windows file sharing contract")
class InstanceLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OUT)
        self.runtime = Path(self.temp.name)
        self.lock = EditorInstanceLock(self.runtime)

    def tearDown(self):
        self.lock.unlock()
        self.temp.cleanup()

    def child(self, mode="hold"):
        return subprocess.Popen([sys.executable, "-I", "-B", "-c", CHILD,
                                 str(ROOT / "KFPS.Editor/src"), str(self.runtime), mode],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)

    def test_legacy_foreign_and_malformed_markers_recover_without_deletion(self):
        from PySide6.QtCore import QLockFile
        protected = {}
        for relative in ("preferences.json", "autosave.json", "projects/saved.fabric-project.json", "assets/saved.json"):
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{"test":"preserve exactly"}')
            protected[path] = (path.read_bytes(), path.stat().st_mtime_ns)
        for payload in (b"", b"partial", b"123456789\npython\nOTHER-PC\n\n\n",
                        f"{os.getpid()}\npython\nOTHER-PC\n\n\n".encode()):
            with self.subTest(payload=payload):
                self.lock.path.write_bytes(payload)
                original_identity = self.lock.path.stat().st_ino
                old = QLockFile(str(self.lock.path))
                old.setStaleLockTime(0)
                self.assertFalse(old.tryLock(0), "Baseline fixture must reproduce a Qt stale-marker refusal")
                self.assertTrue(self.lock.tryLock())
                self.assertEqual(self.lock.path.stat().st_ino, original_identity)
                self.assertEqual(int(self.lock.path.read_text().splitlines()[0]), os.getpid())
                self.lock.unlock()
                for path, before in protected.items():
                    self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_live_old_and_new_locks_exclude_each_other(self):
        from PySide6.QtCore import QLockFile
        old = QLockFile(str(self.lock.path))
        old.setStaleLockTime(0)
        self.assertTrue(old.tryLock(0))
        before = self.lock.path.read_bytes()
        try:
            self.assertFalse(self.lock.tryLock())
            self.assertEqual(before, self.lock.path.read_bytes())
        finally:
            old.unlock()
        self.assertTrue(self.lock.tryLock())
        self.assertFalse(old.tryLock(0))
        self.assertFalse(old.removeStaleLockFile(), "A legacy editor must not remove our live lock")

    def test_cross_process_owner_and_crash_release(self):
        child = self.child()
        try:
            self.assertEqual(int(child.stdout.readline()), child.pid)
            self.assertFalse(self.lock.tryLock())
            child.kill()
            child.wait(timeout=10)
            self.assertFalse(process_running(child.pid))
            self.assertTrue(self.lock.tryLock())
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)

    def test_transient_reader_lock_retries_without_removing_marker(self):
        from kfps_editor.windows_lock import acquire_file_lease
        owner = acquire_file_lease(self.lock.path, share=1)
        release = threading.Timer(.15, owner.Close)
        release.start()
        start = time.monotonic()
        try:
            self.assertTrue(self.lock.tryLock(1000))
            self.assertGreaterEqual(time.monotonic() - start, .10)
            self.assertLess(time.monotonic() - start, 1)
        finally:
            release.join()
            owner.Close()

    def test_simultaneous_launchers_only_one_owner(self):
        children = [self.child() for _ in range(5)]
        try:
            results = [child.communicate(timeout=15) for child in children]
            self.assertEqual(sum(child.returncode == 0 for child in children), 1, results)
            self.assertEqual(sum(child.returncode == 3 for child in children), 4, results)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill(); child.wait(timeout=10)

    def test_write_denial_is_not_reported_as_running(self):
        self.lock.path.write_text("untouched")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong]
        self.assertTrue(kernel.SetFileAttributesW(str(self.lock.path), 1))
        try:
            with self.assertRaisesRegex(RuntimeError, "cannot write"):
                self.lock.tryLock()
            self.assertEqual(self.lock.last_error, 5)
            self.assertEqual(self.lock.path.read_text(), "untouched")
        finally:
            kernel.SetFileAttributesW(str(self.lock.path), 128)

    def test_hardlink_cannot_overwrite_saved_work(self):
        victim = self.runtime / "project-sentinel.json"
        victim.write_text("saved-work")
        os.link(victim, self.lock.path)
        with self.assertRaisesRegex(RuntimeError, "single-link"):
            self.lock.tryLock()
        self.assertEqual(victim.read_text(), "saved-work")

    def test_failed_metadata_write_releases_handle(self):
        from kfps_editor.windows_lock import FileLease
        with patch.object(FileLease, "write", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.lock.tryLock()
        self.assertTrue(self.lock.tryLock())

    def test_dead_ready_marker_is_not_current_readiness(self):
        child = self.child("crash")
        child.communicate(timeout=10)
        (self.runtime / "desktop.json").write_text(json.dumps({"pid": child.pid,
            "instance": "test", "state": "ready"}))
        self.assertEqual(ipc.read_desktop_state(self.runtime, "test"), {})

    def test_missing_ready_marker_does_not_report_success(self):
        with patch.object(ipc, "STARTUP_TIMEOUT", .01), patch.object(ipc.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "too long"):
                ipc.wait_until_ready(self.runtime, "test")

    def test_guard_retry_stops_after_one_ack(self):
        busy = RuntimeError("busy"); busy.winerror = 32
        with patch.object(startup, "acquire_update_guard", side_effect=busy), \
             patch.object(startup, "forward_before_qt", side_effect=[False, True]) as forward, \
             patch.object(startup.time, "sleep"):
            self.assertIsNone(startup.acquire_or_forward(ROOT, self.runtime, {"mode": "new"}))
            self.assertEqual(forward.call_count, 2)

    def test_guard_timeout_and_permission_are_distinct(self):
        for code in (32, 5):
            error = RuntimeError("original"); error.winerror = code
            with patch.object(startup, "acquire_update_guard", side_effect=error), \
                 patch.object(startup, "forward_before_qt", return_value=False) as forward, \
                 patch.object(startup, "GUARD_WAIT_SECONDS", 0):
                with self.assertRaisesRegex(RuntimeError, "not responding" if code == 32 else "original"):
                    startup.acquire_or_forward(ROOT, self.runtime, {})
                self.assertEqual(forward.call_count, int(code == 32))

    def test_lost_ack_is_never_replayed(self):
        error = RuntimeError("busy"); error.winerror = 32
        with patch.object(startup, "acquire_update_guard", side_effect=error), \
             patch.object(startup, "forward_before_qt", side_effect=ipc.EditorConnectionError("lost ACK")) as forward:
            with self.assertRaises(ipc.EditorConnectionError):
                startup.acquire_or_forward(ROOT, self.runtime, {})
            forward.assert_called_once()


if __name__ == "__main__":
    unittest.main()
