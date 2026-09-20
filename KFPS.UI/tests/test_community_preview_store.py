from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui.community_preview_store import PreviewStore, PreviewError


class PreviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = PreviewStore(self.root)
        self.raw = b'{"shapes":[]}'
        self.meta = {"title": "Test", "kind": "vinyl", "tags": [], "supporter": False}
        self.ident = self.store.add(self.meta, self.raw, b"image", "Moderator", now=100)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_guest_download_is_denied(self):
        with self.assertRaises(PreviewError): self.store.download(self.ident, "Visitor", now=100)

    def test_download_exact_and_repeat_safe(self):
        first = self.store.download(self.ident, "Member", now=100)
        second = self.store.download(self.ident, "Member", now=110)
        self.assertEqual(first, second)
        self.assertEqual(first.read_bytes(), self.raw)
        self.assertEqual(self.store.catalog("Member", 110)[0]["downloads"], 1)

    def test_supporter_gated_for_member_and_guest(self):
        ident = self.store.add(dict(self.meta, supporter=True), b"supporter", b"image", "Moderator", now=100)
        for account in ("Member", "Visitor"):
            with self.assertRaises(PreviewError): self.store.download(ident, account, now=100)
        self.assertEqual(self.store.download(ident, "Supporter", now=100).read_bytes(), b"supporter")

    def test_vote_change_remove_and_distinct_accounts(self):
        self.store.vote(self.ident, 1, "Member", 100)
        self.store.vote(self.ident, 1, "Member", 100)
        self.assertEqual(self.store.catalog("Member", 100)[0]["score"], 1)
        self.store.vote(self.ident, -1, "Member", 100)
        self.store.vote(self.ident, 1, "Supporter", 100)
        self.assertEqual(self.store.catalog("Member", 100)[0]["score"], 0)
        self.store.vote(self.ident, 0, "Member", 100)
        self.assertEqual(self.store.catalog("Member", 100)[0]["score"], 1)
        with self.assertRaises(PreviewError): self.store.vote(self.ident, 1, "Visitor", 100)

    def test_favorites_follow_and_ignore_separate_per_account(self):
        for table, value in (("favorites", self.ident), ("follows", "Kloudy"), ("ignored", "Kloudy")):
            self.store.toggle(table, value, "Member")
        row = self.store.catalog("Member", 100)[0]
        self.assertTrue(row["favorite"] and row["followed"] and row["ignored"])
        row = self.store.catalog("Supporter", 100)[0]
        self.assertFalse(row["favorite"] or row["followed"] or row["ignored"])
        self.store.toggle("favorites", self.ident, "Member")
        self.assertFalse(self.store.catalog("Member", 100)[0]["favorite"])

    def test_expiry_inclusive_and_download_copy_survives(self):
        ident = self.store.add(self.meta, b"timed", b"image", "Moderator", starts=200, ends=300, now=100)
        with self.assertRaises(PreviewError): self.store.download(ident, "Member", now=199.99)
        copy = self.store.download(ident, "Member", now=200)
        self.assertEqual(copy.read_bytes(), b"timed")
        self.store.download(ident, "Member", now=299.99)
        with self.assertRaises(PreviewError): self.store.download(ident, "Member", now=300)
        row = self.store.db.execute("SELECT payload,preview,state FROM artwork WHERE id=?", (ident,)).fetchone()
        self.assertEqual(tuple(row), (None, None, "expired"))
        self.assertEqual(copy.read_bytes(), b"timed")
        with self.assertRaises(PreviewError): self.store.moderate(ident, "restore", "Moderator", now=301)

    def test_restart_persistence_and_expiry_catchup(self):
        ident = self.store.add(self.meta, b"scheduled", b"image", "Moderator", starts=200, ends=300, now=100)
        self.store.vote(self.ident, 1, "Member", 100)
        self.store.close()
        self.store = PreviewStore(self.root)
        self.assertEqual(self.store.catalog("Member", 101)[0]["score"], 1)
        self.store.catalog("Moderator", 400)
        row = self.store.db.execute("SELECT payload FROM artwork WHERE id=?", (ident,)).fetchone()
        self.assertIsNone(row[0])

    def test_bad_schedule_rejected(self):
        for starts, ends in ((200,None),(None,300),(200,200),(300,200),(20,50)):
            with self.assertRaises(PreviewError): self.store.add(self.meta,b"x",b"", "Member",starts=starts,ends=ends,now=100)

    def test_removed_release_still_has_a_cleanup_deadline(self):
        ident = self.store.add(self.meta, b"timed removal", b"image", "Moderator", starts=200, ends=300, now=100)
        self.store.moderate(ident, "remove", "Moderator", 100)
        self.assertEqual(self.store.next_boundary(100), 300)
        self.store.expire(300)
        self.assertIsNone(self.store.db.execute("SELECT payload FROM artwork WHERE id=?", (ident,)).fetchone()[0])

    def test_duplicate_payload_rejected(self):
        with self.assertRaises(PreviewError): self.store.add(self.meta,self.raw,b"", "Member",now=100)

    def test_mod_permissions_and_reporting(self):
        self.store.report(self.ident,"Test problem", "Member",100)
        self.assertEqual(self.store.catalog("Moderator",100)[0]["reports"],1)
        for action in ("remove","restore","feature","resolve"):
            with self.assertRaises(PreviewError): self.store.moderate(self.ident, action,"Member",100)
        self.store.moderate(self.ident,"resolve","Moderator",100)
        self.assertEqual(self.store.catalog("Moderator",100)[0]["reports"],0)
        self.store.moderate(self.ident,"remove","Moderator",100)
        with self.assertRaises(PreviewError): self.store.download(self.ident,"Member",100)
        self.store.moderate(self.ident,"restore","Moderator",100)
        self.assertEqual(self.store.download(self.ident,"Member",100).read_bytes(),self.raw)

    def test_owner_can_remove_but_not_feature(self):
        ident=self.store.add(self.meta,b"own",b"", "Member",now=100)
        with self.assertRaises(PreviewError): self.store.moderate(ident,"feature","Member",100)
        self.store.moderate(ident,"remove","Member",100)
        with self.assertRaises(PreviewError): self.store.download(ident,"Member",100)

    def test_livery_bytes_are_preserved(self):
        ident=self.store.add(dict(self.meta,kind="livery"),b"package",b"", "Moderator",now=100)
        path=self.store.download(ident,"Member",100)
        self.assertEqual(path.suffix,".kfpslivery")
        self.assertEqual(path.read_bytes(),b"package")

    def test_preview_only_not_downloadable(self):
        ident=self.store.add(self.meta,None,b"picture", "Moderator",now=100)
        with self.assertRaises(PreviewError): self.store.download(ident,"Member",100)

    def test_tampered_payload_rejected(self):
        with self.store.db: self.store.db.execute("UPDATE artwork SET payload=? WHERE id=?",(b"changed",self.ident))
        with self.assertRaises(PreviewError): self.store.download(self.ident,"Member",100)

    def test_profile_and_bad_website(self):
        self.store.save_profile("Member","Hello","https://example.test")
        self.assertEqual(self.store.profile("Member")["bio"],"Hello")
        with self.assertRaises(PreviewError): self.store.save_profile("Member","x","javascript:foo")


if __name__ == "__main__": unittest.main()
