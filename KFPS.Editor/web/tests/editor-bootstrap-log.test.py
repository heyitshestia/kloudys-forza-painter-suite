"""Bounded prelaunch retention, Windows inherited handles and denied storage."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor import bootstrap_log as logs


@unittest.skipUnless(os.name == "nt", "Windows inherited file handles")
class BootstrapLogTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / "runtime/test-runs/editor-modernization-2026-09-12/runs/log-fixtures"
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(dir=folder)
        self.root = Path(self.folder.name)
        self.path = self.root / "desktop.log"

    def tearDown(self):
        self.folder.cleanup()

    def test_huge_previous_logs_keep_only_bounded_newest_tails(self):
        self.path.write_bytes(b"old" * logs.MAX_BYTES + b"newest")
        (self.root / "desktop.log.1").write_bytes(b"prior" * logs.MAX_BYTES)
        self.assertEqual("rotated", logs.prepare_desktop_log(self.root))
        self.assertEqual(0, self.path.stat().st_size)
        self.assertEqual(logs.MAX_BYTES, (self.root / "desktop.log.1").stat().st_size)
        self.assertEqual(logs.MAX_BYTES, (self.root / "desktop.log.2").stat().st_size)
        self.assertTrue((self.root / "desktop.log.1").read_bytes().endswith(b"newest"))
        with logs.open_desktop_log(self.root) as stream:
            stream.write("fresh startup\n")
        self.assertEqual("fresh startup\n", self.path.read_text())

    def test_inherited_writer_is_not_rotated_or_truncated(self):
        self.path.write_bytes(b"x" * (logs.MAX_BYTES + 1))
        marker = self.root / "child-ready"
        code = "import pathlib,sys,time; print('child', flush=True); pathlib.Path(sys.argv[1]).touch(); time.sleep(30)"
        with self.path.open("a", encoding="utf-8") as stream:
            child = subprocess.Popen([sys.executable, "-c", code, str(marker)], stdout=stream,
                stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            import time
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            before = self.path.read_bytes()
            self.assertEqual("in-use", logs.prepare_desktop_log(self.root))
            self.assertEqual(before, self.path.read_bytes())
            with logs.open_desktop_log(self.root) as stream:
                stream.write("concurrent startup\n")
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertEqual("rotated", logs.prepare_desktop_log(self.root))
        self.assertIn(b"concurrent startup", (self.root / "desktop.log.1").read_bytes())

    def test_rotation_denial_preserves_original_and_appending_still_works(self):
        self.path.write_bytes(b"x" * (logs.MAX_BYTES + 1))
        before = self.path.read_bytes()
        with patch.object(logs, "_replace_tail", side_effect=PermissionError("denied")):
            self.assertEqual("unavailable", logs.prepare_desktop_log(self.root))
            self.assertEqual(before, self.path.read_bytes())
            with logs.open_desktop_log(self.root) as stream:
                stream.write("startup still allowed")
        self.assertTrue(self.path.read_bytes().endswith(b"startup still allowed"))

    def test_hardlink_or_unwritable_sink_does_not_break_launch(self):
        victim = self.root / "victim"
        victim.write_text("untouched")
        os.link(victim, self.path)
        self.assertEqual("unsafe-path", logs.prepare_desktop_log(self.root))
        with logs.open_desktop_log(self.root) as stream:
            stream.write("must not alter victim")
        self.assertEqual("untouched", victim.read_text())
        other = self.root / "denied"
        other.mkdir()
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            with logs.open_desktop_log(other) as stream:
                stream.write("discarded diagnostic, not a failed startup")


if __name__ == "__main__":
    unittest.main()
