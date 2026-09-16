from __future__ import annotations

import concurrent.futures
import json
import os
import struct
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.cgroup_library_service import CGroupLibraryService
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, write_cgroup_file
from tools.cgroup.fh6_identity import (
    CreatorIdentity, FH6DestinationChoiceRequired, FH6IdentityError, SaveAccount,
    account_from_selection, build_vinyl_header, parse_vinyl_header, read_account,
    resolve_creator, select_account,
)
from tools.cgroup.forza_source_decoder import decode_forza_source


def junction(source: Path, destination: Path):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(source), str(destination))
    else:
        destination.symlink_to(source, target_is_directory=True)


def make_account(root: Path, user_id=1234567890, *, creator="Local Painter", version="7"):
    directory = root / "pgs" / f"u_{user_id}_16D460"
    containers = directory / version / "ContainersRoot"
    containers.mkdir(parents=True)
    (containers / f"User_{user_id:X}").mkdir()
    (directory / f"{version}.json").write_text(json.dumps({
        "Manifest": {"UserId": str(user_id), "GameId": "16D460", "Version": int(version)},
    }))
    junction(containers.parent, directory / "current")
    if creator:
        group = containers / "LayerGroup_0000_fixture"
        group.mkdir()
        (group / "header").write_bytes(build_vinyl_header("Original", user_id, creator, 1,
                                                       now=datetime(2026, 1, 2, 3, 4, 5)))
        write_cgroup_file(group / "C_group", build_flat_payload([
            CGroupLayer(102, 0, 0, 1, 1, 0, 0, (255, 255, 255, 255)),
        ]))
        (group / "thumb.webp").write_bytes(b"old thumbnail")
    return read_account(directory)


def pointer(local: Path, account: SaveAccount, *, windows=False, profile_id=None):
    base = (local / "Packages" / "Microsoft.ForteBaseGame_8wekyb3d8bbwe" / "LocalCache" / "Local"
            if windows else local / "ForzaHorizon6")
    path = base / f"SaveFolderMetadata_{profile_id or account.user_id:X}" / "LastSaveFolderLocation"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(account.directory / "current" / "ContainersRoot"), encoding="utf-8")
    return path


def snapshot(root: Path):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class HeaderTests(unittest.TestCase):
    def test_fresh_header_fields_and_unicode(self):
        raw = build_vinyl_header("\ud55c\uae00 \U0001f600" * 30, 123, "\ud14c\uc2a4\ud2b8 \U0001f600", 59)
        header = parse_vinyl_header(raw)
        self.assertLessEqual(len(header.title.encode("utf-16le")), 128)
        self.assertEqual(header.creator, "\ud14c\uc2a4\ud2b8 \U0001f600")
        self.assertEqual(header.creator_id, 123)
        self.assertEqual(header.layer_count, 59)
        self.assertEqual(header.tail[:37], bytes(28) + b"\x01\x02" + bytes(7))
        self.assertEqual(len(header.tail), 57)
        self.assertNotEqual(header.asset_id, parse_vinyl_header(build_vinyl_header("a", 123, "b", 59)).asset_id)
        self.assertEqual(header.created.date(), datetime.now().date())

    def test_reject_bad_creation_input(self):
        for user_id, name, count in [(0, "Owner", 1), (1, "", 1), (1, "KFPS", 1),
                                     (1, "Owner", 0), (1, "Owner", 3001), (1, "a\x00b", 1)]:
            with self.subTest(user_id=user_id, name=name, count=count), self.assertRaises(FH6IdentityError):
                build_vinyl_header("test", user_id, name, count)
        for guid in [bytes(16), b"short"]:
            with self.assertRaises(FH6IdentityError):
                build_vinyl_header("test", 1, "Owner", 1, asset_id=guid)

    def test_malformed_header(self):
        valid = build_vinyl_header("a", 1, "b", 1)
        cases = [b"", valid[:50], b"\x08" + valid[1:], valid[:4] + b"\xff" * 4 + valid[8:]]
        bad_date = bytearray(valid)
        struct.pack_into("<H", bad_date, 16, 13)  # Month after title and empty description.
        cases.append(bytes(bad_date))
        for value in cases:
            with self.subTest(length=len(value)), self.assertRaises(FH6IdentityError):
                parse_vinyl_header(value)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "local"
        self.account = make_account(self.root)

    def select(self, **kwargs):
        return select_account([self.root, self.root / "pgs"], local_app_data=self.local, **kwargs)

    def test_current_account_and_all_supported_explicit_selections(self):
        self.assertEqual(self.select(), self.account)
        for path in [self.account.directory, self.account.directory / "current",
                     self.account.containers.parent, self.account.containers]:
            self.assertEqual(account_from_selection(path), self.account)
        (self.account.containers / f"User_{self.account.user_id:X}_Backup").mkdir()
        self.assertEqual(read_account(self.account.directory), self.account)

    def test_both_store_pointers_choose_same_account(self):
        make_account(self.root, 456, creator=None)
        pointer(self.local, self.account)
        pointer(self.local, self.account, windows=True)
        self.assertEqual(self.select(), self.account)

    def test_multiple_accounts_require_choice_without_pointers(self):
        second = make_account(self.root, 456)
        with self.assertRaises(FH6DestinationChoiceRequired):
            self.select()
        self.assertEqual(self.select(destination=second.containers), second)

    def test_conflicting_pointers_require_choice(self):
        second = make_account(self.root, 456)
        pointer(self.local, self.account)
        pointer(self.local, second, windows=True)
        with self.assertRaises(FH6DestinationChoiceRequired):
            self.select()

    def test_pointer_selected_account_does_not_fall_back_to_other_creator(self):
        second = make_account(self.root, 456, creator=None)
        pointer(self.local, second)
        selected = self.select()
        self.assertEqual(selected, second)
        with self.assertRaisesRegex(FH6IdentityError, "Save one small vinyl"):
            resolve_creator(selected)

    def test_stale_and_wrong_profile_pointers(self):
        p = pointer(self.local, self.account, profile_id=999)
        with self.assertRaises(FH6DestinationChoiceRequired):
            self.select()
        p.write_text(str(self.root / "missing"))
        with self.assertRaises(FH6DestinationChoiceRequired):
            self.select()

    def test_manifest_user_game_and_profile_must_agree(self):
        manifest = self.account.directory / "7.json"
        for content in [{"UserId": "999", "GameId": "16D460", "Version": 7},
                        {"UserId": str(self.account.user_id), "GameId": "OTHER", "Version": 7},
                        {"UserId": str(self.account.user_id), "GameId": "16D460", "Version": 8}]:
            manifest.write_text(json.dumps({"Manifest": content}))
            with self.assertRaises(FH6IdentityError):
                read_account(self.account.directory)
        manifest.write_bytes(self.account.manifest)
        (self.account.containers / "User_FFF").mkdir()
        with self.assertRaises(FH6IdentityError):
            read_account(self.account.directory)

    def test_inactive_version_and_vinyl_selection_rejected(self):
        old = self.account.directory / "6" / "ContainersRoot"
        old.mkdir(parents=True)
        for path in [old, self.account.containers / "LayerGroup_0000_fixture"]:
            with self.assertRaises(FH6IdentityError):
                account_from_selection(path)

    def test_current_version_switch_detected(self):
        new = self.account.directory / "8" / "ContainersRoot"
        new.mkdir(parents=True)
        (new / f"User_{self.account.user_id:X}").mkdir()
        data = json.loads(self.account.manifest)
        data["Manifest"]["Version"] = 8
        (self.account.directory / "8.json").write_text(json.dumps(data))
        current = self.account.directory / "current"
        if os.name == "nt":
            current.rmdir()
        else:
            current.unlink()
        junction(new.parent, current)
        with self.assertRaisesRegex(FH6IdentityError, "changed the active save"):
            self.account.revalidate()

    def test_foreign_newer_artwork_does_not_supply_creator(self):
        foreign = self.account.containers / "LayerGroup_foreign"
        foreign.mkdir()
        (foreign / "header").write_bytes(build_vinyl_header("Foreign", 999, "Not Owner", 1))
        self.assertEqual(resolve_creator(self.account).name, "Local Painter")

    def test_latest_internal_date_supports_renamed_gamertag(self):
        identity = resolve_creator(self.account)
        updated = self.account.containers / "LayerGroup_updated"
        updated.mkdir()
        (updated / "header").write_bytes(build_vinyl_header("New", self.account.user_id, "New Name", 1))
        os.utime(identity.evidence, (time.time() + 100000, time.time() + 100000))
        self.assertEqual(resolve_creator(self.account).name, "New Name")
        with self.assertRaises(FH6IdentityError):
            changed = CreatorIdentity(self.account, identity.name, identity.evidence, b"not the header")
            changed.revalidate()

    def test_conflicting_same_date_and_invalid_default_names(self):
        identity = resolve_creator(self.account)
        second = self.account.containers / "LayerGroup_conflict"
        second.mkdir()
        (second / "header").write_bytes(build_vinyl_header("Other", self.account.user_id, "Different",
                                                           1, now=datetime(2026, 1, 2, 3, 4, 5)))
        with self.assertRaisesRegex(FH6IdentityError, "Conflicting"):
            resolve_creator(self.account)
        identity.evidence.write_bytes(CGroupLibraryService._build_draft_header("Old fallback"))
        (second / "header").unlink()
        with self.assertRaisesRegex(FH6IdentityError, "No verified"):
            resolve_creator(self.account)


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.account = make_account(self.root)
        self.local = self.root / "local"
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)})
        self.env.start()
        self.addCleanup(self.env.stop)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        self.service = CGroupLibraryService(paths, None, None, SimpleNamespace(append=Mock()))
        self.addCleanup(self.service.close)
        self.processes = patch.object(self.service, "_game_process_running", return_value=False)
        self.processes.start()
        self.addCleanup(self.processes.stop)
        self.roots = patch.object(self.service, "_default_save_roots", return_value=[self.root])
        self.roots.start()
        self.addCleanup(self.roots.stop)
        self.thumb = patch.object(self.service, "_write_save_thumb", return_value=False)
        self.thumb.start()
        self.addCleanup(self.thumb.stop)
        self.source = self.write_json(59)

    def write_json(self, count):
        path = self.root / "input.json"
        path.write_text(json.dumps({"name": "Imported", "shapes": [
            {"type": 8, "data": [i, 0, 100, 100, 0], "color": [255, 0, 100, 255]}
            for i in range(count)
        ]}))
        return path

    def groups(self):
        return sorted(self.account.containers.glob("LayerGroup_*"))

    def assert_no_stage(self):
        self.assertEqual([], list(self.account.containers.glob(".kfps-*")))

    def test_real_worker_creates_fresh_verified_entries_not_header_copies(self):
        original = self.groups()[0]
        before = snapshot(original)
        ids = {parse_vinyl_header(before["header"]).asset_id}
        for count in [43, 59, 3000]:
            self.write_json(count)
            existing = set(self.groups())
            result = self.service._create_folder_install_work(self.source, "fh6")
            created, = set(self.groups()) - existing
            header = parse_vinyl_header((created / "header").read_bytes())
            self.assertEqual((count, self.account.user_id, "Local Painter"),
                             (header.layer_count, header.creator_id, header.creator))
            self.assertEqual(count, len(decode_forza_source(created / "C_group", game="fh6").layers))
            self.assertNotIn(header.asset_id, ids)
            ids.add(header.asset_id)
            self.assertEqual(57, len(header.tail))
            self.assertFalse((created / "thumb.webp").exists())
            self.assertIn("without a thumbnail", result["message"])
        self.assertEqual(before, snapshot(original))
        self.assert_no_stage()

    def test_missing_identity_and_invalid_count_never_commit(self):
        original = self.groups()[0]
        for count in [0, 3001]:
            self.write_json(count)
            with self.assertRaises(ValueError):
                self.service._create_folder_install_work(self.source, "fh6")
            self.assertEqual([original], self.groups())
            self.assert_no_stage()
        (original / "header").unlink()
        self.write_json(1)
        with self.assertRaisesRegex(FH6IdentityError, "Save one small vinyl"):
            self.service._create_folder_install_work(self.source, "fh6")
        self.assert_no_stage()

    def test_old_shared_header_count_guid_and_padding_are_not_copied(self):
        original = self.groups()[0] / "header"
        raw = build_vinyl_header("Unrelated", self.account.user_id, "Local Painter", 183)
        old = parse_vinyl_header(raw)
        tail = bytearray(old.tail)
        struct.pack_into("<I", tail, 0, 1)
        tail[12:28] = old.asset_id
        tail[28:30] = b"\x00\x02"
        original.write_bytes(raw[:-57] + tail + bytes(842))
        before = set(self.groups())
        self.service._create_folder_install_work(self.source, "fh6")
        created, = set(self.groups()) - before
        header = parse_vinyl_header((created / "header").read_bytes())
        self.assertEqual(59, header.layer_count)
        self.assertNotEqual(old.asset_id, header.asset_id)
        self.assertEqual(bytes(28), header.tail[:28])
        self.assertEqual(57, len(header.tail))

    def test_conflicting_target_created_during_staging_is_not_overwritten(self):
        prepare = self.service._prepare_fh6_import
        fixed = datetime(2026, 9, 16, 1, 2, 3)
        target = self.account.containers / "LayerGroup_0000_20260916010203"
        def collide(*args, **kwargs):
            result = prepare(*args, **kwargs)
            target.mkdir()
            (target / "sentinel").write_bytes(b"another importer")
            return result
        with patch("kfps_ui.cgroup_library_service.datetime") as clock:
            clock.now.return_value = fixed
            with patch.object(self.service, "_prepare_fh6_import", side_effect=collide), self.assertRaises(OSError):
                self.service._create_folder_install_work(self.source, "fh6")
        self.assertEqual({"sentinel": b"another importer"}, snapshot(target))
        self.assert_no_stage()

    def test_same_count_payload_corruption_is_detected(self):
        identity = resolve_creator(self.account)
        folder = self.root / "staged"
        folder.mkdir()
        count, thumb, header, digest = self.service._prepare_fh6_import(self.source, folder, identity)
        changed = build_flat_payload([
            CGroupLayer(102, 0, 0, 1, 1, 0, 0, (0, 0, 0, 255)) for _ in range(count)
        ])
        write_cgroup_file(folder / "C_group", changed)
        with self.assertRaisesRegex(ValueError, "verification failed"):
            self.service._verify_fh6_import(folder, count, header, digest)

    def test_write_cancel_identity_change_and_commit_failure_leave_no_entry(self):
        original = self.groups()[0]
        for target, error in [
            ("_atomic_write_bytes", OSError("disk full")),
            ("_check_fh6_import_ready", concurrent.futures.CancelledError()),
        ]:
            with patch.object(self.service, target, side_effect=error), self.assertRaises(type(error)):
                self.service._create_folder_install_work(self.source, "fh6")
            self.assertEqual([original], self.groups())
            self.assert_no_stage()
        with patch.object(CreatorIdentity, "revalidate", side_effect=FH6IdentityError("changed")), self.assertRaises(FH6IdentityError):
            self.service._create_folder_install_work(self.source, "fh6")
        with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=OSError("locked")), self.assertRaises(OSError):
            self.service._create_folder_install_work(self.source, "fh6")
        with patch.object(self.service, "_verify_fh6_import", side_effect=[None, ValueError("bad commit")]), self.assertRaises(ValueError):
            self.service._create_folder_install_work(self.source, "fh6")
        self.assertEqual([original], self.groups())
        self.assert_no_stage()

    def test_cancellation_after_thumbnail_does_not_commit(self):
        original = self.groups()[0]
        def cancel(*_args):
            self.service._cancel_event.set()
            return False
        with patch.object(self.service, "_write_save_thumb", side_effect=cancel), self.assertRaises(concurrent.futures.CancelledError):
            self.service._create_folder_install_work(self.source, "fh6")
        self.assertEqual([original], self.groups())
        self.assert_no_stage()

    def test_last_used_account_switch_during_staging_does_not_commit(self):
        second = make_account(self.root, 456)
        p = pointer(self.local, self.account)
        def switch(*args):
            p.unlink()
            pointer(self.local, second)
            return False
        with patch.object(self.service, "_write_save_thumb", side_effect=switch), self.assertRaisesRegex(ValueError, "account changed"):
            self.service._create_folder_install_work(self.source, "fh6")
        self.assertEqual(1, len(self.groups()))
        self.assert_no_stage()

    def test_additive_import_allows_both_running_game_executables(self):
        for executable in ("ForzaHorizon6.exe", "ForzaHorizon6-Win64-Shipping.exe"):
            with self.subTest(executable=executable):
                before = set(self.groups())
                with patch.object(self.service, "_game_process_running", side_effect=lambda name: name == executable):
                    result = self.service._create_folder_install_work(self.source, "fh6")
                self.assertTrue(result["ok"])
                created, = set(self.groups()) - before
                self.assertEqual(59, parse_vinyl_header((created / "header").read_bytes()).layer_count)
                self.assert_no_stage()

    def test_additive_import_game_start_during_staging_is_not_a_failure(self):
        before = set(self.groups())
        running = False
        def start_game(*args):
            nonlocal running
            running = True
            return False
        with patch.object(self.service, "_game_process_running", side_effect=lambda _: running), patch.object(
            self.service, "_write_save_thumb", side_effect=start_game
        ):
            result = self.service._create_folder_install_work(self.source, "fh6")
        self.assertTrue(running)
        self.assertTrue(result["ok"])
        self.assertEqual(1, len(set(self.groups()) - before))
        self.assert_no_stage()

    def test_additive_import_still_rejects_save_changes_with_game_running(self):
        before = snapshot(self.account.containers)
        manifest = self.account.directory / "7.json"
        def change_save(*args):
            data = json.loads(manifest.read_text())
            data["Manifest"]["LastWrite"] = "changed during import"
            manifest.write_text(json.dumps(data))
            return False
        with patch.object(self.service, "_game_process_running", return_value=True), patch.object(
            self.service, "_write_save_thumb", side_effect=change_save
        ), self.assertRaisesRegex(FH6IdentityError, "changed the active save"):
            self.service._create_folder_install_work(self.source, "fh6")
        self.assertEqual(before, snapshot(self.account.containers))
        self.assert_no_stage()

    def test_replacement_running_game_or_game_starting_during_staging_blocks_commit(self):
        original = self.groups()[0]
        before = snapshot(original)
        for results in [[True], [False, False, True]]:
            with patch.object(self.service, "_game_process_running", side_effect=results), self.assertRaisesRegex(ValueError, "replacing an existing vinyl"):
                self.service._install_work(self.source, original)
            self.assertEqual([original], self.groups())
            self.assertEqual(before, snapshot(original))
            self.assert_no_stage()

    def test_replacement_preserves_id_and_backups_but_updates_count(self):
        target = self.groups()[0]
        before = snapshot(target)
        result = self.service._install_work(self.source, target)
        after = parse_vinyl_header((target / "header").read_bytes())
        self.assertEqual(after.asset_id, parse_vinyl_header(before["header"]).asset_id)
        self.assertEqual(after.layer_count, 59)
        self.assertFalse((target / "thumb.webp").exists())
        backups = list((self.root / "runtime" / "cgroup-folder-import-backups").iterdir())
        self.assertEqual(1, len(backups))
        self.assertEqual(before, snapshot(backups[0]))
        self.assertTrue(result["ok"])
        self.assert_no_stage()

    def test_replacement_verification_failure_restores_all_original_files(self):
        target = self.groups()[0]
        before = snapshot(target)
        with patch.object(self.service, "_verify_fh6_import", side_effect=[None, ValueError("bad")]), self.assertRaises(ValueError):
            self.service._install_work(self.source, target)
        self.assertEqual(before, snapshot(target))
        self.assert_no_stage()

    def test_replacement_commit_failure_restores_original(self):
        target = self.groups()[0]
        before = snapshot(target)
        rename = os.rename
        calls = 0
        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("locked")
            return rename(*args)
        with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=fail_second), self.assertRaises(OSError):
            self.service._install_work(self.source, target)
        self.assertEqual(before, snapshot(target))
        self.assert_no_stage()

    def test_failed_rollback_preserves_backup_and_reports_its_location(self):
        target = self.groups()[0]
        before = snapshot(target)
        rename = os.rename
        def fail_install_and_restore(source, destination):
            if Path(destination) == target:
                raise OSError("locked")
            return rename(source, destination)
        with patch("kfps_ui.cgroup_library_service.os.rename", side_effect=fail_install_and_restore), self.assertRaisesRegex(RuntimeError, "original vinyl backup"):
            self.service._install_work(self.source, target)
        backup, = (self.root / "runtime" / "cgroup-folder-import-backups").iterdir()
        self.assertEqual(before, snapshot(backup))
        rollback, = self.account.containers.glob(".kfps-*.rollback")
        self.assertEqual(before, snapshot(rollback))

    def test_foreign_replacement_rejected(self):
        target = self.groups()[0]
        (target / "header").write_bytes(build_vinyl_header("Foreign", 999, "Other", 1))
        before = snapshot(target)
        with self.assertRaises(FH6IdentityError):
            self.service._install_work(self.source, target)
        self.assertEqual(before, snapshot(target))

    def wait_for_service(self):
        deadline = time.monotonic() + 10
        while self.service.running and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertFalse(self.service.running, self.service.summary)

    def test_public_slot_ambiguity_picker_then_worker_completion(self):
        make_account(self.root, 456)
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=str(self.account.containers)) as dialog:
            self.service.createFH6LayerGroupFromSelectedJson(str(self.source))
            self.wait_for_service()
        dialog.assert_called_once()
        self.assertEqual("Complete", self.service.status)
        self.assertEqual(2, len(self.groups()))
        self.assertIsNone(self.service._pending_fh6_json)

    def test_public_slot_picker_cancel_writes_nothing(self):
        make_account(self.root, 456)
        before = snapshot(self.account.containers)
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=""):
            self.service.createFH6LayerGroupFromSelectedJson(str(self.source))
            self.wait_for_service()
        self.assertIn("cancelled", self.service.summary)
        self.assertEqual(before, snapshot(self.account.containers))
        self.assertIsNone(self.service._pending_fh6_json)

    def test_public_slot_invalid_destination_fails_without_repeated_prompt(self):
        make_account(self.root, 456)
        with patch("kfps_ui.cgroup_library_service.QFileDialog.getExistingDirectory", return_value=str(self.root)) as dialog:
            self.service.createFH6LayerGroupFromSelectedJson(str(self.source))
            self.wait_for_service()
        dialog.assert_called_once()
        self.assertEqual("Failed", self.service.status)
        self.assertEqual(1, len(self.groups()))
        self.assertIsNone(self.service._pending_fh6_json)


if __name__ == "__main__":
    unittest.main()
