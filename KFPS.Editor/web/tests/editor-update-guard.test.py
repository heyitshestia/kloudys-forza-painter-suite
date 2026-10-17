"""Windows reader leases must coexist while the unchanged updater stays exclusive."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor.update_guard import acquire_update_guard
from kfps_editor.windows_lock import acquire_file_lease
from kfps_editor import startup

OUT = ROOT / "runtime/test-runs/20261017-editor-report-fixes/unit"
OUT.mkdir(parents=True, exist_ok=True)


@unittest.skipUnless(os.name == "nt", "Windows sharing contract")
class UpdateGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OUT)
        self.root = Path(self.temp.name)
        self.leases = []

    def tearDown(self):
        for lease in reversed(self.leases):
            lease.Close()
        self.temp.cleanup()

    def reader(self):
        lease = acquire_update_guard(self.root)
        self.leases.append(lease)
        return lease

    def writer(self):
        # The existing Go updater uses these same access/share/disposition flags.
        lease = acquire_file_lease(self.root / "updater.lock")
        self.leases.append(lease)
        return lease

    def test_multiple_readers_block_updater_until_last_reader_closes(self):
        readers = [self.reader() for _ in range(8)]
        for reader in readers:
            with self.assertRaises(OSError) as error:
                self.writer()
            self.assertEqual(error.exception.winerror, 32)
            reader.Close()
        self.writer()

    def test_updater_blocks_all_readers_and_retry_succeeds(self):
        writer = self.writer()
        with self.assertRaises(RuntimeError) as error:
            self.reader()
        self.assertEqual(error.exception.winerror, 32)
        writer.Close()
        self.reader()

    def test_existing_lock_is_not_truncated_or_replaced(self):
        path = self.root / "updater.lock"
        path.write_bytes(b"existing-updater-metadata")
        before = (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
        self.reader()
        self.reader()
        self.assertEqual((path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns), before)
        with self.assertRaises(OSError):
            path.unlink()

    def test_cross_process_readers_and_crash_release(self):
        code = """
import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from kfps_editor.update_guard import acquire_update_guard
lease=acquire_update_guard(Path(sys.argv[2]))
print('ready',flush=True)
time.sleep(60)
"""
        parent = self.reader()
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", code,
            str(ROOT / "KFPS.Editor/src"), str(self.root)], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            parent.Close()
            with self.assertRaises(OSError):
                self.writer()
            child.kill()
            child.communicate(timeout=10)
            self.writer()
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)

    def test_hardlink_rejected_without_touching_target(self):
        target = self.root / "saved-project"
        target.write_bytes(b"preserve")
        os.link(target, self.root / "updater.lock")
        with self.assertRaisesRegex(RuntimeError, "single-link"):
            self.reader()
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_forwarding_releases_reader_before_loading_qt(self):
        for failure in (False, True):
            with self.subTest(failure=failure), \
                 patch.object(startup, "updater_state_root", return_value=self.root), \
                 patch.object(startup, "forward_before_qt", side_effect=RuntimeError("lost ACK") if failure else None,
                              return_value=True) as forward:
                if failure:
                    with self.assertRaisesRegex(RuntimeError, "lost ACK"):
                        startup.acquire_or_forward(self.root, self.root / "runtime", {"mode": "activate"})
                else:
                    self.assertIsNone(startup.acquire_or_forward(self.root, self.root / "runtime", {"mode": "activate"}))
                forward.assert_called_once()
                self.writer().Close()


if __name__ == "__main__":
    unittest.main()
