from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(UI / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from game_adapters import get_adapter_or_default
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup.fm8_identity import FM8IdentityError, build_vinyl_header, parse_vinyl_header
from tools.cgroup.forza_source_decoder import DecodeError, decode_forza_source
from test_fm8_offline_transfer import fm8_header, write_group


class FM8HeaderIdentityTests(unittest.TestCase):
    def setUp(self):
        self.source_id = uuid.uuid4()
        self.new_id = uuid.uuid4()
        self.source = fm8_header(asset_id=self.source_id, layer_count=40)

    def build(self, **changes):
        args = dict(source=self.source, source_folder_id=self.source_id, title="New vinyl",
                    layer_count=1400, asset_id=self.new_id,
                    now=datetime(2026, 9, 18, 13, 45, 10, 123000, tzinfo=timezone.utc))
        args.update(changes)
        return build_vinyl_header(**args)

    def test_fresh_ids_count_date_and_preserved_creator(self):
        raw = self.build()
        result = parse_vinyl_header(raw, folder_id=self.new_id)
        donor = parse_vinyl_header(self.source, folder_id=self.source_id)
        self.assertEqual(2, raw.count(self.new_id.bytes_le))
        self.assertNotIn(self.source_id.bytes_le, raw)
        self.assertEqual(("New vinyl", "", "LocalUser"),
                         (result.metadata.title, result.metadata.description, result.metadata.creator))
        self.assertEqual(donor.creator_id, result.creator_id)
        self.assertEqual(1400, result.layer_count)
        self.assertEqual(datetime(2026, 9, 18, 13, 45, 10, 123000, tzinfo=timezone.utc), result.created_utc)

    def test_old_title_only_copy_reproduces_mismatched_ids_and_count(self):
        old = CGroupLibraryService._rename_header(self.source, "New vinyl")
        self.assertEqual(40, parse_vinyl_header(old).layer_count)
        with self.assertRaisesRegex(FM8IdentityError, "identifiers"):
            parse_vinyl_header(old, folder_id=self.new_id)

    def test_unicode_counts_utf16_units_without_splitting_surrogate(self):
        title = "\ud55c\uae00 \U0001f60a " * 30
        result = parse_vinyl_header(self.build(title=title))
        encoded = result.metadata.title.encode("utf-16le")
        self.assertLessEqual(len(encoded), 128)
        self.assertNotIn("\ufffd", result.metadata.title)
        self.assertTrue(result.metadata.title.startswith("\ud55c\uae00 \U0001f60a"))

    def test_empty_and_control_whitespace_title(self):
        self.assertEqual("KFPS Import", parse_vinyl_header(self.build(title=" \x00\t\n")).metadata.title)
        self.assertEqual("a b", parse_vinyl_header(self.build(title="a\n\tb")).metadata.title)

    def test_count_boundaries_and_reused_identity(self):
        for count in (1, 3000):
            with self.subTest(count=count):
                self.assertEqual(count, parse_vinyl_header(self.build(layer_count=count)).layer_count)
        for count in (0, 3001):
            with self.subTest(count=count), self.assertRaises(FM8IdentityError):
                self.build(layer_count=count)
        for asset in (uuid.UUID(int=0), self.source_id):
            with self.subTest(asset=asset), self.assertRaises(FM8IdentityError):
                self.build(asset_id=asset)

    def test_rejects_unsupported_truncated_or_foreign_header(self):
        cases = [self.source[:n] for n in (0, 3, 7, 20, len(self.source)-1)]
        cases.extend((struct.pack("<I",7)+self.source[4:], self.source+b"\0",
                      fm8_header(asset_id=self.source_id,catalog_state=1),
                      self.source[:-16]+uuid.uuid4().bytes_le))
        for raw in cases:
            with self.subTest(length=len(raw)), self.assertRaises(FM8IdentityError):
                self.build(source=raw)

    def test_rejects_donor_folder_mismatch(self):
        with self.assertRaisesRegex(FM8IdentityError, "identifiers"):
            self.build(source_folder_id=uuid.uuid4())


class FM8OfflineInstallIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name)
        self.groups = self.app / "saves" / "LayerGroups"
        self.groups.mkdir(parents=True)
        self.source = write_group(self.groups, str(uuid.uuid4()))
        (self.source / "thumbnail").write_bytes(b"unrelated donor image")
        self.before = {p.name:p.read_bytes() for p in self.source.iterdir()}
        self.input = self.app / "New design.json"
        self.input.write_text(json.dumps({"shapes":[
            {"type":1048678,"data":[0,0,1,1,0,0,0],"color":[30,130,220,255]},
            {"type":1052077,"data":[50,10,2,3,45,.1,0],"color":[100,20,50,128]},
        ]}),encoding="utf-8")
        paths = AppPaths(self.app, UI, UI / "qml", UI / "assets", self.app / "runtime", Path(sys.executable))
        self.service = CGroupLibraryService(paths, None, None, None)
        self.addCleanup(self.service.close)
        self.patches = [patch.object(self.service,"_default_save_roots",return_value=[self.groups]),
                        patch.object(self.service,"_game_process_running",return_value=False),
                        patch.object(self.service,"_write_save_thumb",return_value=False)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def install(self):
        return self.service._create_fm8_layer_group_install_work(self.input)

    def new_groups(self):
        return [p for p in self.groups.iterdir() if p != self.source]

    def assert_source_untouched(self):
        self.assertEqual(self.before, {p.name:p.read_bytes() for p in self.source.iterdir()})

    def test_real_work_path_fresh_metadata_payload_and_no_donor_thumbnail(self):
        result = self.install()
        self.assertTrue(result["ok"])
        created, = self.new_groups()
        meta = parse_vinyl_header((created / "header").read_bytes(),folder_id=uuid.UUID(created.name))
        self.assertEqual(2,meta.layer_count)
        self.assertEqual("New design",meta.metadata.title)
        self.assertFalse((created / "thumbnail").exists())
        self.assertEqual(2,len(decode_forza_source(created / "data",game="fm8").layers))
        self.assertIn("cannot confirm", result["message"])
        self.assert_source_untouched()

    def test_two_imports_do_not_share_identity(self):
        self.install()
        self.install()
        created = self.new_groups()
        self.assertEqual(2,len(created))
        ids = {parse_vinyl_header((p / "header").read_bytes(),folder_id=uuid.UUID(p.name)).asset_id for p in created}
        self.assertEqual(2,len(ids))
        self.assert_source_untouched()

    def test_fm8_thumbnail_is_native_png(self):
        from PIL import Image
        self.patches[2].stop()
        self.install()
        created, = self.new_groups()
        with Image.open(created / "thumbnail") as image:
            image.load()
            self.assertEqual("PNG",image.format)
            self.assertEqual((256,256),image.size)
            self.assertTrue(image.convert("RGBA").getchannel("A").getbbox())
        self.assert_source_untouched()

    def test_game_running_all_store_process_names_allows_new_entries(self):
        for executable in get_adapter_or_default("fm8").process_names:
            with self.subTest(executable=executable), patch.object(self.service,"_game_process_running",side_effect=lambda n:n==executable) as process_check:
                before = len(self.new_groups())
                self.assertTrue(self.install()["ok"])
                self.assertEqual(before+1,len(self.new_groups()))
                process_check.assert_not_called()
        self.assert_source_untouched()

    def test_game_starts_during_prepare_does_not_block_new_entry(self):
        running = False
        def thumb(*args):
            nonlocal running
            running = True
            return False
        with patch.object(self.service,"_write_save_thumb",side_effect=thumb), patch.object(self.service,"_game_process_running",side_effect=lambda n:running):
            self.assertTrue(self.install()["ok"])
        self.assertEqual(1,len(self.new_groups()))
        self.assert_source_untouched()

    def test_cancellation_before_and_during_prepare(self):
        self.service._cancel_event.set()
        with self.assertRaises(concurrent.futures.CancelledError):
            self.install()
        self.service._cancel_event.clear()
        def thumb(*args):
            self.service._cancel_event.set()
            return False
        with patch.object(self.service,"_write_save_thumb",side_effect=thumb), self.assertRaises(concurrent.futures.CancelledError):
            self.install()
        self.assertEqual([],self.new_groups())
        self.assert_source_untouched()

    def test_missing_or_unsupported_donor_never_uses_draft_header(self):
        for raw in (b"invalid",struct.pack("<I",7)+self.before["header"][4:]):
            (self.source / "header").write_bytes(raw)
            with self.assertRaisesRegex(ValueError,"No supported locally owned"):
                self.install()
            self.assertEqual([],self.new_groups())

    def test_latest_template_ignores_newer_mismatched_identity(self):
        invalid = write_group(self.groups,str(uuid.uuid4()))
        (invalid / "header").write_bytes(self.before["header"])
        os.utime(self.source / "data",(100,100))
        os.utime(invalid / "data",(200,200))
        self.assertEqual(self.source,self.service._latest_fm8_layer_group())

    def test_source_header_changed_before_commit(self):
        def thumb(*args):
            (self.source / "header").write_bytes(b"changed externally")
            return False
        with patch.object(self.service,"_write_save_thumb",side_effect=thumb), self.assertRaisesRegex(ValueError,"source FM8 vinyl changed"):
            self.install()
        self.assertEqual([],self.new_groups())
        self.assertEqual(b"changed externally",(self.source / "header").read_bytes())

    def test_failed_payload_reopen_rolls_back_new_entry_only(self):
        with patch("tools.cgroup.forza_source_decoder.decode_forza_source",side_effect=DecodeError("test rejection")), self.assertRaisesRegex(ValueError,"reopened safely"):
            self.install()
        self.assertEqual([],self.new_groups())
        self.assert_source_untouched()

    def test_changed_staging_data_is_not_committed(self):
        def thumb(json_path,thumb_path,image_format):
            (thumb_path.parent / "data").write_bytes(b"changed")
            return False
        with patch.object(self.service,"_write_save_thumb",side_effect=thumb), self.assertRaisesRegex(ValueError,"staged FM8 vinyl changed"):
            self.install()
        self.assertEqual([],self.new_groups())
        self.assert_source_untouched()

    def test_destination_collision_does_not_overwrite_or_remove_existing_file(self):
        rename = os.rename
        def collision(source,destination):
            destination.mkdir()
            (destination / "keep").write_bytes(b"other entry")
            rename(source,destination)
        with patch("kfps_ui.cgroup_library_service.os.rename",side_effect=collision), self.assertRaises(OSError):
            self.install()
        existing, = self.new_groups()
        self.assertEqual(b"other entry",(existing / "keep").read_bytes())
        self.assert_source_untouched()


if __name__ == "__main__":
    unittest.main()
