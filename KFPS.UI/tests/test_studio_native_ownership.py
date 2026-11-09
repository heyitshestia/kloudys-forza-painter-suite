"""Native Studio leases use OS ownership, including across crashes and token changes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools/livery-studio/src"), str(ROOT / "KFPS.Editor/src")]
from kfps_livery_lab import studio_window


class NativeOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="studio-ownership-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.patcher = patch.object(studio_window, "LAB", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.url = "http://127.0.0.1:32190/" + "a" * 43 + "/"

    def test_token_and_fragment_do_not_create_a_second_owner(self):
        first = studio_window.acquire_native_owner(self.url)
        self.addCleanup(first.unlock)
        for url in (self.url, self.url.replace("a" * 43, "b" * 43), self.url + "#layout=" + "c" * 32):
            with self.subTest(url=url), self.assertRaises(studio_window.NativeOwnerError):
                studio_window.acquire_native_owner(url)
        self.assertTrue(first.isLocked())
        first.unlock()
        second = studio_window.acquire_native_owner(self.url)
        self.addCleanup(second.unlock)
        self.assertTrue(second.isLocked())

    def test_other_backend_has_independent_owner(self):
        first = studio_window.acquire_native_owner(self.url)
        self.addCleanup(first.unlock)
        second = studio_window.acquire_native_owner(self.url.replace(":32190/", ":32191/"))
        self.addCleanup(second.unlock)
        self.assertTrue(first.isLocked() and second.isLocked())

    def test_borrowed_owner_allows_retained_car_switch_and_is_not_released(self):
        from kfps_livery_lab import host_bridge
        lock = studio_window.acquire_native_owner(self.url)
        self.addCleanup(lock.unlock)
        ready = {"url": self.url, "reused": True, "host_layout_handoff": True,
                 "vehicle": {"car_id": 1, "model_code": "FIRST"}, "chrome_exposed": False}
        request = {"layout": {"vehicle": {"car_id": 2, "model_code": "SECOND"}}}
        with patch.object(host_bridge.launcher, "_window_module", return_value=studio_window), \
                patch.object(studio_window, "use_chrome", return_value=False):
            with self.assertRaisesRegex(ValueError, "another open page"):
                host_bridge._check_package_target(ROOT, ready, request)
            host_bridge._check_package_target(ROOT, ready, request, lock)
            with studio_window.native_admission(self.url, lock):
                self.assertTrue(lock.isLocked())
            self.assertTrue(lock.isLocked())
            with self.assertRaises(studio_window.NativeOwnerError):
                with studio_window.native_admission(self.url.replace(":32190/", ":32191/"), lock):
                    self.fail("Wrong backend was admitted")
            with patch.object(studio_window, "use_chrome", return_value=True):
                with self.assertRaisesRegex(ValueError, "In Chrome"):
                    host_bridge._check_package_target(ROOT, ready, request, lock)

    def test_provisional_admission_releases_on_failure(self):
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with studio_window.native_admission(self.url):
                with self.assertRaises(studio_window.NativeOwnerError):
                    studio_window.acquire_native_owner(self.url)
                raise RuntimeError("injected")
        lock = studio_window.acquire_native_owner(self.url)
        self.addCleanup(lock.unlock)

    def test_redirected_storage_is_rejected_without_writes(self):
        target = self.root / "runs/native-owners"
        for method in ("is_symlink", "is_junction"):
            with self.subTest(method=method), patch.object(Path, method, autospec=True,
                    side_effect=lambda path: path == target):
                with self.assertRaisesRegex(studio_window.NativeOwnerError, "redirected"):
                    studio_window.acquire_native_owner(self.url)
        self.assertFalse((self.root / "runs").exists())

    def test_process_crash_releases_os_lease_despite_stale_marker(self):
        script = """
import os, sys
from pathlib import Path
root, lab, url = sys.argv[1:]
sys.path[:0] = [str(Path(root)/'tools/livery-studio/src'), str(Path(root)/'KFPS.Editor/src')]
from kfps_livery_lab import studio_window
studio_window.LAB = Path(lab)
lock = studio_window.acquire_native_owner(url)
print('held', flush=True)
sys.stdin.readline()
os._exit(17)
"""
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", script, str(ROOT), str(self.root), self.url],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self.assertEqual(child.stdout.readline().strip(), "held")
            with self.assertRaises(studio_window.NativeOwnerError):
                studio_window.acquire_native_owner(self.url)
        finally:
            child.communicate("crash\n", timeout=10)
        self.assertEqual(child.returncode, 17)
        self.assertTrue((studio_window.native_owner_directory(self.url) / "desktop.lock").is_file())
        lock = studio_window.acquire_native_owner(self.url)
        self.addCleanup(lock.unlock)
        self.assertTrue(lock.isLocked())


if __name__ == "__main__":
    unittest.main()
