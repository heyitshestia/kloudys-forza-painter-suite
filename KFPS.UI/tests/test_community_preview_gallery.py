from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from kfps_ui.community_preview_service import CommunityPreviewService, image_bytes

APP = QApplication.instance() or QApplication([])


class CreatorGalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = CommunityPreviewService(ROOT, Path(self.temp.name))
        self.store = self.service.store
        self.now = time.time()
        self.picture = image_bytes((UI / "assets/mini-kloudy.png").read_bytes())

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def add(self, **fields):
        return self.store.add({"title": "Gallery test", "kind": "vinyl", "creator": "GalleryArtist", **fields},
                              b"{}", self.picture, "Moderator", seed=True)

    def bulk(self, count=5000):
        ids = [f"{i+1:032x}" for i in range(count)]
        with self.store.db:
            self.store.db.executemany("INSERT INTO artwork VALUES (?,?,?,?,?,?,?,?,?)", (
                (ident, json.dumps({"title": f"Artwork {i:04d}", "kind": "vinyl", "creator": "GalleryArtist", "game": "FH6"}),
                 None, None, "", self.now - i // 3, None, None, "published") for i, ident in enumerate(ids)
            ))
        return ids

    def test_5000_items_keyset_pagination_without_loading_images_or_payloads(self):
        expected = set(self.bulk())
        def authorize(action, table, column, *unused):
            if action == sqlite3.SQLITE_READ and table == "artwork" and column in ("preview", "payload"):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.store.db.set_authorizer(authorize)
        cursor, seen = None, []
        started = time.perf_counter()
        while True:
            page = self.store.creator_page("GalleryArtist", "Member", after=cursor)
            self.assertEqual(page["total"], 5000)
            self.assertLessEqual(len(page["items"]), 48)
            seen.extend(row["id"] for row in page["items"])
            cursor = page["next"]
            if cursor is None: break
        elapsed = time.perf_counter() - started
        self.assertEqual(len(seen), 5000)
        self.assertEqual(set(seen), expected)
        print(f"Creator catalog: 5000 items / 105 bounded pages in {elapsed:.3f}s", flush=True)

    def test_new_upload_does_not_shift_the_next_page_or_duplicate_existing_items(self):
        expected = set(self.bulk(120))
        first = self.store.creator_page("GalleryArtist", "Member")
        new = self.add()
        remaining = []
        cursor = first["next"]
        while cursor:
            page = self.store.creator_page("GalleryArtist", "Member", after=cursor)
            remaining += page["items"]
            cursor = page["next"]
        ids = [row["id"] for row in first["items"] + remaining]
        self.assertEqual(set(ids), expected)
        self.assertEqual(len(ids), 120)
        self.assertNotIn(new, ids)

    def test_profile_filters_unavailable_and_ignored_artwork(self):
        available = self.add()
        future, expired, removed = self.add(), self.add(), self.add()
        with self.store.db:
            self.store.db.execute("UPDATE artwork SET starts=? WHERE id=?", (self.now+1000, future))
            self.store.db.execute("UPDATE artwork SET ends=? WHERE id=?", (self.now-1, expired))
            self.store.db.execute("UPDATE artwork SET state='removed' WHERE id=?", (removed,))
        page = self.store.creator_page("GalleryArtist", "Member")
        self.assertEqual([row["id"] for row in page["items"]], [available])
        self.store.toggle("ignored", "GalleryArtist", "Member")
        self.assertEqual(self.store.creator_page("GalleryArtist", "Member")["total"], 0)

    def test_service_fetches_bounded_metadata_and_resets_for_account_changes(self):
        self.bulk(120)
        with patch.object(self.store, "preview", side_effect=AssertionError("Eager image read")):
            self.service.viewCreator("GalleryArtist")
            self.assertEqual(self.service.creator_model.rowCount(), 48)
            self.service.loadMoreCreator()
            self.assertEqual(self.service.creator_model.rowCount(), 96)
            self.service.loadMoreCreator()
            self.assertEqual(self.service.creator_model.rowCount(), 120)
            self.assertFalse(self.service.creatorHasMore)
        self.service.setAccount("Member")
        self.assertEqual(self.service.creator_model.rowCount(), 48)

    def test_profile_selection_reads_only_requested_metadata(self):
        ident = self.add()
        self.service.viewCreator("GalleryArtist")
        with patch.object(self.store, "catalog", wraps=self.store.catalog) as catalog:
            self.assertTrue(self.service.inspectCreatorArtwork(ident))
            self.assertEqual(catalog.call_args.kwargs, {"ident": ident})
        self.assertEqual(self.service.selected["id"], ident)
        self.assertFalse(self.service.inspectCreatorArtwork("nonexistent"))
        self.store.toggle("ignored", "GalleryArtist", "Creator")
        self.assertFalse(self.service.inspectCreatorArtwork(ident))
        self.service.refresh()
        self.assertEqual(self.service.creator_model.rowCount(), 0)

    def test_follow_preserves_loaded_pages(self):
        self.bulk(120)
        self.service.viewCreator("GalleryArtist")
        self.service.loadMoreCreator()
        self.service.followCreator()
        self.assertEqual(self.service.creator_model.rowCount(), 96)
        self.assertTrue(self.service.creatorProfile["followed"])

    def test_thumbnail_is_bounded_and_database_connection_is_closed(self):
        ident = self.add()
        closed = []
        class Connection(sqlite3.Connection):
            def close(self):
                closed.append(True)
                super().close()
        connect = sqlite3.connect
        with patch("kfps_ui.community_preview_images.sqlite3.connect", side_effect=lambda *a, **k: connect(*a, **k, factory=Connection)):
            size = QSize()
            result = self.service.images.requestImage("0/" + ident, size, QSize(400, 260))
        self.assertFalse(result.isNull())
        self.assertLessEqual(result.width(), 400)
        self.assertLessEqual(result.height(), 260)
        self.assertEqual(size, result.size())
        self.assertEqual(closed, [True])

    def test_thumbnail_rejects_stale_generation_invalid_id_and_hidden_artwork(self):
        ident = self.add()
        provider = self.service.images
        provider.set_access("Alex", 0, 7)
        for request in ("0/"+ident, "7/../catalog.sqlite3", "7/"+"f"*32):
            self.assertTrue(provider.requestImage(request, QSize(), QSize()).isNull())
        self.assertFalse(provider.requestImage("7/"+ident, QSize(), QSize()).isNull())
        self.store.toggle("ignored", "GalleryArtist", "Member")
        self.assertTrue(provider.requestImage("7/"+ident, QSize(), QSize()).isNull())
        self.store.toggle("ignored", "GalleryArtist", "Member")
        with self.store.db:
            self.store.db.execute("UPDATE artwork SET ends=? WHERE id=?", (self.now-1, ident))
        self.assertTrue(provider.requestImage("7/"+ident, QSize(), QSize()).isNull())


if __name__ == "__main__":
    unittest.main()
