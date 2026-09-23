from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(UI / "tests"), str(ROOT)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kfps_ui.community_preview_service import CommunityPreviewService, inspect_file

APP = QApplication.instance() or QApplication([])


class PreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.input = self.root / "vinyl.json"
        self.input.write_text(json.dumps({"shapes": [{"type":16, "data":[512,512,220,120,30], "color":[10,190,210,255]}]}))

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def inspect(self, path):
        self.service.inspectPath(str(path))
        deadline = time.monotonic() + 20
        while self.service.busy and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.01)
        self.assertFalse(self.service.busy)
        self.assertFalse(self.service.hasError, self.service.status)

    def test_supporter_discovery_for_visitors_members_and_supporters(self):
        artwork = inspect_file(self.input, self.root)
        for supporter in (False, True):
            self.service.store.add(dict(title='Discovery fixture', kind='vinyl', supporter=supporter),
                                   artwork['payload'], artwork['preview'], 'Supporter', seed=True)
        for account in ('Visitor', 'Member', 'Supporter'):
            with self.subTest(account=account):
                self.service.setAccount(account)
                self.service.filter('scope', 'Supporters')
                self.assertTrue(self.service.rows)
                self.assertTrue(all(row['supporter'] for row in self.service.rows))
                self.assertTrue(all(row['previewUrl'] for row in self.service.rows))
                self.assertEqual(self.service.selected['locked'], account != 'Supporter')
                self.service.filterSupporters(False)
                self.assertEqual(self.service.scope, 'Browse')
                self.assertTrue(any(not row['supporter'] for row in self.service.rows))
        self.service.filter('scope', 'Supporters')
        self.service.filter('scope', 'Browse')
        self.assertFalse(self.service.filters['supporters'])

    def fields(self, **kw):
        return dict(title="Local upload", description="A test", tags="racing, 테스트", category="Patterns",
                    classification="handmade", rights=True, compatibility=True, **kw)

    def test_real_json_validation_publish_download_without_network(self):
        original = self.input.read_bytes()
        with patch.object(socket.socket,"connect",side_effect=AssertionError("Network forbidden")):
            self.inspect(self.input)
            self.assertEqual(self.service.upload["shapes"],1)
            self.service.publish(self.fields())
            self.assertFalse(self.service.hasError,self.service.status)
            self.assertEqual(self.service.scope,"My uploads")
            self.assertEqual(self.service.selected["tags"],["racing", "테스트"])
            self.service.download()
            files = list((self.service.store.root / "downloads").glob("*/*.json"))
            self.assertEqual(len(files),1)
            self.assertEqual(json.loads(files[0].read_bytes()),json.loads(original))
            self.assertEqual(self.input.read_bytes(),original)
            self.assertEqual(list((self.service.store.root / "staging").iterdir()),[])

    def test_validated_livery_roundtrip(self):
        from test_full_livery_package import build_package
        from PySide6.QtGui import QImage
        path=self.root / "test.kfpslivery"
        cover = QImage(670, 376, QImage.Format_RGB32)
        cover.fill('blue')
        cover_path = self.root / 'cover.webp'
        cover.save(str(cover_path), 'WEBP')
        build_package(path, thumbnail=cover_path.read_bytes())
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        self.inspect(path)
        self.assertEqual(self.service.upload["kind"],"livery")
        self.service.inspectPhotos([str(ROOT / "KFPS.UI/assets/mini-kloudy.png")])
        while self.service.busy:
            APP.processEvents()
            time.sleep(0.01)
        self.service.publish(self.fields())
        self.assertFalse(self.service.hasError,self.service.status)
        self.service.download()
        target=next((self.service.store.root / "downloads").glob("*/*.kfpslivery"))
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),before)

    def test_invalid_and_preview_only_packages_rejected(self):
        for suffix in (".json", ".kfpslivery", ".kfpspreview"):
            path=self.root / ("bad"+suffix)
            path.write_bytes(b"not an artwork")
            with self.assertRaises(Exception): inspect_file(path,self.root / "state")

    def test_publication_requires_rights_and_compatible_ack(self):
        self.inspect(self.input)
        data=self.fields()
        data["rights"]=False
        self.service.publish(data)
        self.assertTrue(self.service.hasError)
        self.assertIsNotNone(self.service.pending)
        self.service.setAccount("Visitor")
        self.service.publish(self.fields())
        self.assertTrue(self.service.hasError)

    def test_member_cannot_publish_supporter_content(self):
        self.inspect(self.input)
        self.service.setAccount("Member")
        self.service.publish(self.fields(supporter=True))
        self.assertTrue(self.service.hasError)

    def test_clock_refreshes_future_artwork_for_nonowner(self):
        self.inspect(self.input)
        now=self.service.now()
        ident=self.service.store.add(dict(self.service.upload, category="Patterns",tags=[],classification="handmade",supporter=False),
                                     self.service.pending["payload"], self.service.pending["preview"],"Moderator", starts=now+3,ends=now+8,now=now)
        self.service.setAccount("Member")
        self.service.filter("scope","Browse")
        self.assertFalse(self.service.rows)
        self.service.offset=4
        self.service._tick()
        self.assertEqual(self.service.rows[0]["id"],ident)
        self.service.offset=9
        self.service._tick()
        self.assertFalse(self.service.rows)
        self.assertIsNone(self.service.store.db.execute("SELECT payload FROM artwork WHERE id=?",(ident,)).fetchone()[0])

    def test_upload_schedule_timezone_and_end_validation(self):
        self.inspect(self.input)
        self.service.publish(self.fields(timed=True,starts="2026-09-19T13:00",ends="2026-09-19T14:00"))
        self.assertTrue(self.service.hasError)
        self.service.publish(self.fields(timed=True,starts="2099-02-19T13:00+09:00",ends="2099-02-19T16:00+09:00"))
        self.assertFalse(self.service.hasError,self.service.status)
        self.assertEqual(self.service.selected["state"],"scheduled")
        self.assertEqual(self.service.selected["ends"]-self.service.selected["starts"],10800)

    def test_no_ignored_creator_dead_end(self):
        self.inspect(self.input)
        self.service.publish(self.fields())
        self.service.setAccount("Member")
        self.service.filter("scope","Browse")
        self.service.toggle("ignored")
        self.assertFalse(self.service.rows)
        self.assertEqual(self.service.ignoredCreators,["Kloudy"])
        self.service.unignore("Kloudy")
        self.assertEqual(len(self.service.rows),1)

    def test_creator_profiles_browse_exact_creator_and_keep_gates(self):
        self.inspect(self.input)
        self.service.publish(self.fields())
        ident = self.service.selected["id"]
        self.service.saveProfile("Handmade vinyls", "https://example.com")
        self.service.viewCreator("Kloudy")
        self.assertTrue(self.service.creatorProfile["own"])
        self.assertFalse(self.service.moderator)
        self.service.setAccount("Member")
        self.service.followCreator()
        self.assertEqual(self.service.creatorProfile["followers"], 1)
        self.assertTrue(self.service.creatorProfile["followed"])
        self.assertEqual(self.service.creatorProfile["bio"], "Handmade vinyls")
        self.service.filter("search", "not a match")
        self.service.filter("kind", "livery")
        self.service.browseCreator(ident)
        self.assertEqual(self.service.selected["id"], ident)
        self.assertEqual(self.service.filters["creator"], "Kloudy")
        self.assertTrue(all(r["creator"] == "Kloudy" for r in self.service.rows))
        self.service.setAccount("Visitor")
        self.assertFalse(self.service.creatorProfile["followed"])
        self.service.followCreator()
        self.assertTrue(self.service.hasError)
        self.service.viewCreator("Nobody")
        self.assertEqual(self.service.creatorProfile["artworks"], [])

    def test_public_profile_never_lists_unreleased_or_removed_artwork(self):
        self.inspect(self.input)
        self.service.publish(self.fields(timed=True, starts="2099-02-19T13:00+09:00", ends="2099-02-19T16:00+09:00"))
        self.service.viewCreator("Kloudy")
        self.assertEqual(self.service.creatorProfile["artworks"], [])
        self.service.setAccount("Moderator")
        self.assertEqual(self.service.creatorProfile["artworks"], [])

    def test_profile_and_votes_survive_service_restart(self):
        self.inspect(self.input)
        self.service.publish(self.fields())
        ident = self.service.selected["id"]
        self.service.saveProfile("Persisted bio", "")
        self.service.vote(1)
        self.service.close()
        self.service = CommunityPreviewService(ROOT, self.root / "state")
        self.service.filter("scope", "Browse")
        self.service.select(ident)
        self.assertEqual(self.service.selected["vote"], 1)
        self.service.viewCreator("Kloudy")
        self.assertEqual(self.service.creatorProfile["bio"], "Persisted bio")
        self.service.vote(1)
        self.assertEqual(self.service.selected["vote"], 0)


if __name__ == "__main__": unittest.main()
