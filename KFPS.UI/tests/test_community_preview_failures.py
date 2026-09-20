from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zlib

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from kfps_ui.community_preview_photos import read_photos
from kfps_ui.community_preview_service import CommunityPreviewService, inspect_file
from kfps_ui.community_preview_store import PreviewError, PreviewStore

APP = QApplication.instance() or QApplication([])


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.store = self.service.store
        self.meta = dict(title="Failure test", kind="livery")

    def tearDown(self):
        if self.service is not None:
            self.service.close()
        self.temp.cleanup()

    def add(self, **kwargs):
        return self.store.add(self.meta, b"exact package bytes", b"cover", "Creator", **kwargs)

    def test_photo_write_failure_rolls_back_entire_upload(self):
        self.store.db.execute("""CREATE TRIGGER fail_photo BEFORE INSERT ON photos
            WHEN NEW.position=1 BEGIN SELECT RAISE(ABORT, 'simulated full disk'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.add(photos=[b"first", b"second", b"third"])
        for table in ("artwork", "photos", "events"):
            self.assertEqual(self.store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.store.db.execute("DROP TRIGGER fail_photo")
        ident = self.add(photos=[b"first", b"second", b"third"])
        self.assertEqual(self.store.photos(ident, "Member"), [b"first", b"second", b"third"])

    def test_failed_download_keeps_previous_copy_and_count(self):
        ident = self.add()
        target = self.store.download(ident, "Member", now=100)
        before = target.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("simulated locked destination")):
            self.service.filter("scope", "Browse")
            self.service.select(ident)
            self.service.download()
        self.assertTrue(self.service.hasError)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM downloads").fetchone()[0], 1)
        self.service.download()
        self.assertFalse(self.service.hasError, self.service.status)
        self.assertFalse(target.with_suffix(".tmp").exists())

    def test_livery_photos_and_download_expire_on_restart(self):
        now = time.time()
        ident = self.add(photos=[b"one", b"two"], starts=now-10, ends=now+5)
        target = self.store.download(ident, "Member", now=now)
        self.service.close()
        with patch("time.time", return_value=now+10):
            self.service = CommunityPreviewService(ROOT, self.root / "state")
            self.store = self.service.store
            self.service.filter("scope", "Browse")
            self.assertEqual(self.service.rows, [])
            self.assertEqual(self.store.photos(ident, "Creator"), [])
            with self.assertRaises(PreviewError):
                self.store.render_payload(ident, "Creator")
        row = self.store.db.execute("SELECT payload,preview,state FROM artwork WHERE id=?", (ident,)).fetchone()
        self.assertEqual(tuple(row), (None, None, "expired"))
        self.assertEqual(target.read_bytes(), b"exact package bytes")

    def test_additive_photo_table_keeps_old_catalog(self):
        ident = self.add()
        self.store.vote(ident, 1, "Member")
        self.store.db.execute("DROP TABLE photos")
        self.store.db.commit()
        self.service.close()
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.store = self.service.store
        self.service.setAccount("Member")
        self.service.filter("scope", "Browse")
        self.assertEqual(self.service.selected["vote"], 1)
        self.assertEqual(self.service.selected["photoUrls"], [])
        self.assertEqual(self.store.download(ident, "Member").read_bytes(), b"exact package bytes")

    def test_validation_failure_cleans_staging_and_recovers(self):
        path = self.root / "invalid.json"
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(Exception):
            inspect_file(path, self.store.root)
        self.assertEqual(list((self.store.root / "staging").iterdir()), [])
        payload = {"shapes": [{"type": 16, "data": [0, 0, 20, 30, 0], "color": [255, 0, 0, 255]}]}
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(inspect_file(path, self.store.root)["shapes"], 1)
        self.assertEqual(list((self.store.root / "staging").iterdir()), [])

    def test_png_dimension_limit_before_pixel_allocation(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind+data))
        raw = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8001, 8000, 8, 2, 0, 0, 0))
        raw += chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")
        path = self.root / "large-header.png"
        path.write_bytes(raw)
        with self.assertRaisesRegex(PreviewError, "64 megapixels"):
            read_photos([str(path)])

    def test_rapid_inspection_uses_one_immutable_result(self):
        entered, release = threading.Event(), threading.Event()
        pending = dict(kind="vinyl", title="First", shapes=1, payload=b"vinyl", preview=b"", warning="")
        def slow(*args):
            entered.set()
            release.wait(5)
            return pending
        with patch("kfps_ui.community_preview_service.inspect_file", side_effect=slow) as inspect:
            try:
                self.service.inspectPath("first.json")
                self.assertTrue(entered.wait(2))
                self.service.inspectPath("second.json")
                self.service.publish(dict(title="Too early", rights=True))
                self.assertTrue(self.service.hasError)
                self.assertEqual(self.store.catalog("Creator"), [])
            finally:
                release.set()
            deadline = time.monotonic() + 5
            while self.service.busy and time.monotonic() < deadline:
                APP.processEvents()
                time.sleep(.01)
            self.assertFalse(self.service.busy)
            self.assertEqual(inspect.call_count, 1)
        self.assertEqual(self.service.upload["title"], "First")
        self.service.publish(dict(title="Ready", rights=True))
        self.assertFalse(self.service.hasError, self.service.status)
        self.assertEqual(len(self.store.catalog("Creator")), 1)

    def test_close_while_inspection_finishes_never_publishes(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            release.wait(5)
            return dict(kind="vinyl", title="Pending", payload=b"x", preview=b"")
        with patch("kfps_ui.community_preview_service.inspect_file", side_effect=slow):
            self.service.inspectPath("pending.json")
            self.assertTrue(entered.wait(2))
            timer = threading.Timer(.05, release.set)
            timer.start()
            self.service.close()
            timer.join()
        self.service = None
        APP.processEvents()
        reopened = PreviewStore(self.root / "state")
        try:
            self.assertEqual(reopened.catalog("Creator"), [])
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
