import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT)]
from PySide6.QtCore import QCoreApplication, QTimer
from kfps_ui.app_log import AppLogWriter
from kfps_ui.log_service import LogService
from kfps_ui.support_log_bundle import collect_retained_log_bundle
APP = QCoreApplication.instance() or QCoreApplication([])


class AppLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_pending_messages_are_snapshotted_and_retained_after_restart(self):
        log = LogService(runtime_root=self.root / "runtime")
        self.addCleanup(log.close)
        log.append("Before report click", update_status=False)
        log.append("password=PRIVATE", update_status=False)
        text, _ = log.diagnostic_snapshot()
        self.assertIn("Before report click", text)
        self.assertEqual(log.plainText, "")  # not flushed to the UI yet
        log.close()
        self.assertFalse(log._writer.thread.is_alive())
        again = LogService(runtime_root=self.root / "runtime")
        self.addCleanup(again.close)
        again.append("After restart", update_status=False)
        again.close()
        _, blob = collect_retained_log_bundle(self.root)
        data = json.loads(gzip.decompress(blob))
        text = "\n".join(file["text"] for file in data["files"] if file["name"].startswith("app-runtime"))
        self.assertIn("Before report click", text)
        self.assertIn("After restart", text)
        self.assertNotIn("PRIVATE", text)

    def test_ui_does_not_wait_for_disk_and_queue_pressure_is_visible(self):
        from logging.handlers import RotatingFileHandler
        gate, entered = threading.Event(), threading.Event()
        original = RotatingFileHandler.emit
        writer = None
        def slow(handler, record):
            entered.set()
            gate.wait(3)
            return original(handler, record)
        try:
            with patch.object(RotatingFileHandler, "emit", slow):
                writer = AppLogWriter(self.root / "runtime")
                writer.append("first")
                self.assertTrue(entered.wait(2))
                start = time.monotonic()
                for index in range(4000):
                    writer.append(f"queued {index}")
                elapsed = time.monotonic() - start
                self.assertLess(elapsed, 1)
                self.assertGreater(writer.status()["dropped"], 0)
                self.assertLessEqual(writer.queue.qsize(), 1024)
                gate.set()
                writer.close()
            self.assertFalse(writer.thread.is_alive())
        finally:
            gate.set()
            if writer:
                writer.close()

    def test_linked_output_is_never_written_and_failure_reaches_snapshot(self):
        path = self.root / f"runtime/app-logs/app-{os.getpid()}.log"
        path.parent.mkdir(parents=True)
        private = self.root / "private.txt"
        private.write_text("PRIVATE")
        os.link(private, path)
        log = LogService(runtime_root=self.root / "runtime")
        self.addCleanup(log.close)
        log.append("must not write", update_status=False)
        log.close()
        self.assertTrue(log.diagnostic_snapshot()[1]["failed"])
        self.assertEqual(private.read_text(), "PRIVATE")

    def test_history_and_oversized_messages_are_bounded(self):
        log = LogService()
        self.addCleanup(log.close)
        for index in range(3000):
            log.append(str(index) + " x"*1000, update_status=False)
        text, _ = log.diagnostic_snapshot()
        self.assertLess(len(text), 1024 * 1024 + 2500)
        self.assertIn("2999", text)
        log.append("PRIVATE" * 20000, update_status=False)
        text, _ = log.diagnostic_snapshot()
        self.assertTrue(text.endswith("[oversized log line removed]"))
        self.assertNotIn("PRIVATE", text)

    def test_rotation_retains_current_and_two_previous_files(self):
        from logging.handlers import RotatingFileHandler
        def small(path, **kwargs):
            return RotatingFileHandler(path, maxBytes=1000, backupCount=2, encoding="utf-8")
        with patch("kfps_ui.app_log.RotatingFileHandler", side_effect=small):
            writer = AppLogWriter(self.root / "runtime")
            for index in range(100):
                writer.append(f"event {index:04} " + "a "*50)
            writer.close()
        self.assertFalse(writer.status()["failed"])
        files = list((self.root / "runtime/app-logs").glob("app-*.log*"))
        self.assertEqual(len(files), 3)
        self.assertTrue(all(path.stat().st_size < 1200 for path in files))
        self.assertIn("event 0099", (self.root / f"runtime/app-logs/app-{os.getpid()}.log").read_text())


if __name__ == "__main__":
    unittest.main()
