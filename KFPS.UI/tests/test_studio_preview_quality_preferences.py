"""Private preview preferences fail closed and survive independent writers."""
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))

from kfps_livery_lab import preview_preferences as p


RUN = p.LAB_ROOT / "runs/test-preview-quality/preferences"
QUALITIES = ("fast", "balanced", "sharp")


class PreviewQualityPreferencesTests(unittest.TestCase):
    def setUp(self):
        RUN.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=RUN)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "settings"
        self.store = p.PreviewPreferences(self.root)

    def test_default_is_read_only_and_choices_survive_reopen(self):
        self.assertEqual(self.store.get(), {"version": 1, "quality": "balanced"})
        self.assertFalse(self.root.exists())
        for quality in QUALITIES:
            expected = {"version": 1, "quality": quality}
            self.assertEqual(self.store.update({"quality": quality}), expected)
            self.assertEqual(p.PreviewPreferences(self.root).get(), expected)
            self.assertEqual(json.loads(self.store.path.read_bytes()), expected)
        self.assertEqual(self.store.path.name, "preview-quality.json")
        self.assertEqual(self.store.lock_path.name, "preview-quality.lock")
        self.assertEqual({f.name for f in self.root.iterdir()}, {"preview-quality.json", "preview-quality.lock"})

    def test_invalid_updates_do_not_create_storage(self):
        for value in (None, [], {}, {"quality": "sharp", "version": 1},
                      *({"quality": q} for q in (None, [], {}, True, 1, "FAST", "fast ", "ultra"))):
            with self.subTest(value=value), self.assertRaises(p.PreviewError) as caught:
                self.store.update(value)
            self.assertEqual(caught.exception.status, 422)
            self.assertFalse(self.root.exists())

    def test_corrupt_future_duplicate_and_oversized_files_are_preserved(self):
        self.root.mkdir()
        bodies = (b"bad", b"\xff", b"[]", b"{}", b'{"version":2,"quality":"fast"}',
                  b'{"version":true,"quality":"fast"}', b'{"version":1.0,"quality":"fast"}',
                  b'{"version":1,"quality":"FAST"}', b'{"version":1,"quality":null}',
                  b'{"version":1,"quality":"fast","quality":"sharp"}',
                  b'{"version":1,"quality":"fast","extra":0}',
                  b'{"version":NaN,"quality":"fast"}', b"x" * (p.MAX_FILE_BYTES + 1))
        for body in bodies:
            self.store.path.write_bytes(body)
            for action in (self.store.get, lambda: self.store.update({"quality": "sharp"})):
                with self.subTest(body=body[:60]), self.assertRaises(p.PreviewError) as caught:
                    action()
                self.assertEqual(caught.exception.status, 409)
                self.assertEqual(self.store.path.read_bytes(), body)

    def test_storage_boundary_hardlinks_and_non_files_are_rejected(self):
        for root in (p.LAB_ROOT, p.LAB_ROOT.parent / "outside", p.LAB_ROOT / "runs/../settings"):
            with self.subTest(root=root), self.assertRaises(p.PreviewError):
                p.PreviewPreferences(root)
        self.root.mkdir()
        original = Path(self.temp.name) / "original.json"
        body = b'{"version":1,"quality":"fast"}'
        original.write_bytes(body)
        for target in (self.store.path, self.store.lock_path):
            os.link(original, target)
            for action in (self.store.get, lambda: self.store.update({"quality": "sharp"})):
                with self.assertRaises(p.PreviewError):
                    action()
            target.unlink()
            target.mkdir()
            with self.assertRaises(p.PreviewError):
                self.store.update({"quality": "sharp"})
            target.rmdir()
        self.assertEqual(original.read_bytes(), body)

    def test_redirected_ancestors_and_files_are_rejected(self):
        original = Path.lstat
        for target, mode in ((self.root, stat.S_IFDIR), (self.store.path, stat.S_IFREG),
                             (self.store.lock_path, stat.S_IFREG)):
            def redirected(path, *args, **kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=mode, st_nlink=1, st_file_attributes=0x400)
                return original(path, *args, **kwargs)
            with patch.object(Path, "lstat", redirected):
                for action in (self.store.get, lambda: self.store.update({"quality": "sharp"})):
                    with self.assertRaises(p.PreviewError) as caught:
                        action()
                    self.assertEqual(caught.exception.status, 500)
        self.assertFalse(self.root.exists())

    def test_atomic_failure_busy_lock_and_recovery_preserve_previous_file(self):
        self.store.update({"quality": "fast"})
        before = self.store.path.read_bytes()
        with patch("kfps_livery_lab.file_io.os.replace", side_effect=PermissionError("private path")):
            with self.assertRaises(p.PreviewError) as caught:
                self.store.update({"quality": "sharp"})
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn("private path", str(caught.exception))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        with patch.object(p, "LOCK_TIMEOUT_SECONDS", .05), patch.object(
                p, "_try_lock", side_effect=BlockingIOError(errno.EAGAIN, "busy")):
            start = time.monotonic()
            with self.assertRaises(p.PreviewError) as caught:
                self.store.update({"quality": "sharp"})
            self.assertEqual(caught.exception.status, 503)
            self.assertLess(time.monotonic() - start, .5)
            self.assertEqual(self.store.get()["quality"], "fast")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.store.update({"quality": "sharp"})
        self.assertEqual(p.PreviewPreferences(self.root).get()["quality"], "sharp")

    def test_invalid_lock_and_unavailable_storage_are_not_overwritten(self):
        self.root.mkdir()
        self.store.lock_path.write_bytes(b"not a lock")
        with self.assertRaises(p.PreviewError) as caught:
            self.store.update({"quality": "fast"})
        self.assertEqual(caught.exception.status, 500)
        self.assertEqual(self.store.lock_path.read_bytes(), b"not a lock")
        self.assertFalse(self.store.path.exists())
        with patch.object(Path, "mkdir", side_effect=PermissionError("private path")):
            with self.assertRaises(p.PreviewError) as caught:
                self.store.update({"quality": "fast"})
        self.assertEqual(caught.exception.status, 503)
        self.assertNotIn("private path", str(caught.exception))

    def test_exact_file_limit_and_growth_after_stat_are_bounded(self):
        self.root.mkdir()
        body = b'{"version":1,"quality":"sharp"}'.ljust(p.MAX_FILE_BYTES, b" ")
        self.store.path.write_bytes(body)
        self.assertEqual(self.store.get(), {"version": 1, "quality": "sharp"})
        small_stat = self.store.path.stat()
        grown = body + b" " * p.MAX_FILE_BYTES
        self.store.path.write_bytes(grown)
        with patch.object(p.os, "fstat", return_value=small_stat), patch.object(p, "decode_json") as decode:
            with self.assertRaises(p.PreviewError) as caught:
                self.store.get()
            decode.assert_not_called()
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.store.path.read_bytes(), grown)

    def test_killed_writer_preserves_published_value_and_releases_lock(self):
        self.store.update({"quality": "fast"})
        before = self.store.path.read_bytes()
        ready = Path(self.temp.name) / "replacement-ready"
        script = """import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from kfps_livery_lab.preview_preferences import PreviewPreferences
from kfps_livery_lab import file_io
def paused_replace(source, destination):
    Path(sys.argv[3]).write_text('ready')
    time.sleep(60)
file_io.os.replace = paused_replace
PreviewPreferences(sys.argv[2]).update({'quality': 'sharp'})
"""
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", script, str(p.LAB_ROOT / "src"), str(self.root), str(ready)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(ready.exists(), "Writer did not reach the pre-replacement checkpoint.")
            self.assertEqual(self.store.get()["quality"], "fast")
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(p.PreviewPreferences(self.root).get()["quality"], "fast")
        self.store.update({"quality": "balanced"})
        self.assertEqual(p.PreviewPreferences(self.root).get()["quality"], "balanced")

    def test_cold_concurrent_readers_and_writers_observe_whole_values(self):
        def change(index):
            store = p.PreviewPreferences(self.root)
            for offset in range(10):
                quality = QUALITIES[(index + offset) % 3]
                self.assertEqual(store.update({"quality": quality}), {"version": 1, "quality": quality})
                self.assertIn(store.get()["quality"], QUALITIES)
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(change, range(5)))
        self.assertIn(p.PreviewPreferences(self.root).get()["quality"], QUALITIES)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_independent_process_writers_share_stable_lock(self):
        script = """import sys
sys.path.insert(0, sys.argv[1])
from kfps_livery_lab.preview_preferences import PreviewPreferences
store = PreviewPreferences(sys.argv[2])
for _ in range(10):
    store.update({'quality': sys.argv[3]})
    assert store.get()['quality'] in ('fast', 'balanced', 'sharp')
"""
        children = []
        try:
            for quality in QUALITIES:
                children.append(subprocess.Popen(
                    [sys.executable, "-B", "-c", script, str(p.LAB_ROOT / "src"), str(self.root), quality],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
            for child in children:
                output, error = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, output + error)
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)
        self.assertIn(self.store.get()["quality"], QUALITIES)
        self.assertEqual(list(self.root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
