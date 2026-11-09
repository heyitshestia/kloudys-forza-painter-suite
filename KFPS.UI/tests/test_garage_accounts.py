from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "KFPS.UI" / "src"))

from kfps_ui import garage_accounts as accounts
from kfps_ui.garage_index import GarageError


def junction(source, destination):
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(source), str(destination))
    else:
        destination.symlink_to(source, target_is_directory=True)


def unlink_junction(path):
    if os.name == "nt":
        path.rmdir()
    else:
        path.unlink()


def make_version(directory, user_id, version="7", *, profile=True, layout="Profile"):
    containers = directory / version / "ContainersRoot"
    containers.mkdir(parents=True)
    (containers / f"User_{user_id:X}").mkdir()
    (directory / f"{version}.json").write_text(json.dumps({
        "Manifest": {"UserId": str(user_id), "GameId": "16D460", "Version": int(version)},
    }), encoding="utf-8")
    if profile:
        folder = containers / (f"User_{user_id:X}" if layout == "User" else "Profile")
        folder.mkdir(exist_ok=True)
        (folder / "C_ProfileData").write_bytes(b"synthetic profile")
    return containers


def make_account(root, user_id=1234567890, *, profile=True, layout="Profile"):
    directory = root / "pgs" / f"u_{user_id}_16D460"
    containers = make_version(directory, user_id, profile=profile, layout=layout)
    junction(containers.parent, directory / "current")
    return directory


def make_pointer(local, directory, *, windows=False, user_id=1234567890):
    base = (local / "Packages" / "Microsoft.ForteBaseGame_8wekyb3d8bbwe" / "LocalCache" / "Local"
            if windows else local / "ForzaHorizon6")
    pointer = base / f"SaveFolderMetadata_{user_id:X}" / "LastSaveFolderLocation"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(directory / "current" / "ContainersRoot"), encoding="utf-8")
    return pointer


class GarageAccountTests(unittest.TestCase):
    LAYOUT = "Profile"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="garage-accounts-test-", dir=ROOT / "runtime")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.local = self.root / "local"
        self.saves = self.root / "saves"
        self.cancel = threading.Event()
        self.directory = make_account(self.saves, layout=self.LAYOUT)
        folder = f"User_{1234567890:X}" if self.LAYOUT == "User" else "Profile"
        self.primary = self.directory / "7" / "ContainersRoot" / folder / "C_ProfileData"

    def discover(self, roots=None):
        return accounts.discover_accounts(self.cancel, roots=[self.saves] if roots is None else roots,
                                          local_app_data=self.local)

    def rotate(self):
        containers = make_version(self.directory, 1234567890, "8", layout=self.LAYOUT)
        unlink_junction(self.directory / "current")
        junction(containers.parent, self.directory / "current")
        return containers / self.primary.parent.name / "C_ProfileData"

    def assert_unavailable(self, directory=None):
        with self.assertRaises(GarageError) as caught:
            accounts.resolve_account(directory or self.directory)
        self.assertEqual(accounts.UNAVAILABLE, str(caught.exception))
        self.assertNotIn(str(self.root), str(caught.exception))
        self.assertNotIn("1234567890", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_contract_primary_and_no_logging(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            row, = self.discover()
        self.assertEqual("", output.getvalue())
        self.assertEqual({"id", "label", "directory", "source", "available"}, set(row))
        self.assertRegex(row["id"], r"^[0-9a-f]{64}$")
        self.assertIn("FH6 account 567890", row["label"])
        self.assertNotIn("1234567890", row["label"])
        self.assertNotIn(str(self.root), row["label"])
        self.assertEqual(str(self.directory), row["directory"])
        self.assertEqual(str(self.primary), row["source"])
        self.assertIs(True, row["available"])
        self.assertEqual(self.primary, accounts.resolve_account(str(self.directory)))

    def test_both_provider_pointers_deduplicate_without_fallback(self):
        first = make_pointer(self.local, self.directory)
        first.write_text("\ufeff" + str(self.directory / "current") + "\x00", encoding="utf-8")
        make_pointer(self.local, self.directory, windows=True)
        with patch.object(accounts, "read_account", wraps=accounts.read_account) as verify:
            row, = self.discover([])
        self.assertEqual(str(self.directory), row["directory"])
        self.assertEqual(1, verify.call_count)

    def test_all_verified_accounts_from_pointers_and_roots_are_listed(self):
        second = make_account(self.root / "other-drive", 9999567890)
        third = make_account(self.saves, 5555)
        make_pointer(self.local, self.directory)
        make_pointer(self.local, second, windows=True, user_id=9999567890)
        rows = self.discover()
        self.assertEqual({str(p) for p in (self.directory, second, third)}, {r["directory"] for r in rows})
        self.assertEqual(3, len({r["id"] for r in rows}))
        self.assertEqual(3, len({r["label"] for r in rows}))
        self.assertEqual(rows, self.discover([self.saves / "pgs", self.saves]))

    def test_same_user_in_two_locations_has_distinct_stable_labels(self):
        second = make_account(self.root / "second-drive")
        roots = [self.directory, second]
        rows = self.discover(roots)
        self.assertEqual(2, len({r["label"] for r in rows}))
        self.assertEqual(2, len({r["id"] for r in rows}))
        self.assertEqual(rows, self.discover(list(reversed(roots))))
        for row in rows:
            self.assertEqual(row, accounts.account_for_source(row["source"]))

    def test_default_roots_only_use_xboxgames_on_drives_and_localappdata(self):
        drive = self.root / "drive"
        directory = make_account(drive / "XboxGames" / "GameSave", 42)
        make_pointer(self.local, self.directory)
        with patch.object(accounts.os, "listdrives", return_value=[str(drive)], create=True), \
                patch.object(accounts, "_drive_type", return_value=3), \
                patch.dict(os.environ, {"LOCALAPPDATA": str(self.local)}):
            rows = accounts.discover_accounts(self.cancel)
        self.assertEqual({str(directory), str(self.directory)}, {r["directory"] for r in rows})
        row, = accounts.discover_accounts(self.cancel, roots=[drive / "XboxGames"], local_app_data="")
        self.assertEqual(str(directory), row["directory"])

    def test_stale_mismatched_relative_and_oversized_pointers_do_not_adopt(self):
        pointer = make_pointer(self.local, self.directory, user_id=999)
        self.assertEqual([], self.discover([]))
        pointer.unlink()
        pointer = make_pointer(self.local, self.directory)
        for value in (str(self.root / "missing"), "relative/current", "x" * 4097,
                      str(self.directory / "6" / "ContainersRoot"), str(self.primary), ""):
            with self.subTest(value_length=len(value)):
                pointer.write_text(value, encoding="utf-8")
                self.assertEqual([], self.discover([]))
                self.assertEqual(1, len(self.discover()))

    def test_old_pointer_is_rejected_even_when_old_version_is_valid(self):
        pointer = make_pointer(self.local, self.directory)
        pointer.write_text(str(self.primary.parents[1]), encoding="utf-8")
        new = self.rotate()
        self.assertEqual([], self.discover([]))
        row, = self.discover()
        self.assertEqual(str(new), row["source"])

    def test_wrong_game_user_version_and_malformed_manifests_are_rejected(self):
        manifest = self.directory / "7.json"
        cases = [{"Manifest": {"UserId": "1234567890", "GameId": "OTHER", "Version": 7}},
                 {"Manifest": {"UserId": "999", "GameId": "16D460", "Version": 7}},
                 {"Manifest": {"UserId": "1234567890", "GameId": "16D460", "Version": 8}},
                 {"Manifest": []}, {}, []]
        for value in cases:
            manifest.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual([], self.discover())
            self.assert_unavailable()
        manifest.write_bytes(b"invalid json")
        self.assertEqual([], self.discover())
        self.assert_unavailable()

    def test_extra_or_wrong_profile_user_is_not_a_verified_account(self):
        containers = self.primary.parents[1]
        (containers / "User_FFF").mkdir()
        self.assertEqual([], self.discover())
        self.assert_unavailable()
        self.primary.unlink()
        (containers / f"User_{1234567890:X}").rmdir()
        self.assertEqual([], self.discover())

    def test_backup_only_account_is_visible_but_unavailable(self):
        self.primary.rename(self.primary.with_name("C_ProfileBackup"))
        row, = self.discover()
        self.assertIs(False, row["available"])
        self.assertEqual("", row["source"])
        self.assert_unavailable()
        self.assertIsNone(accounts.account_for_source(self.primary.with_name("C_ProfileBackup")))

    def test_missing_profile_does_not_inherit_another_account_primary(self):
        self.primary.unlink()
        make_account(self.saves, 456)
        rows = self.discover()
        self.assertEqual(2, len(rows))
        self.assertEqual(1, sum(r["available"] for r in rows))
        self.assert_unavailable()

    def test_empty_oversized_and_directory_profiles_are_unavailable(self):
        for size in (0, accounts.MAX_PROFILE_BYTES + 1):
            with self.primary.open("wb") as stream:
                stream.truncate(size)
            self.assertFalse(self.discover()[0]["available"])
            self.assert_unavailable()
        self.primary.unlink()
        self.primary.mkdir()
        self.assertFalse(self.discover()[0]["available"])
        self.assert_unavailable()

    def test_hardlinked_primary_is_accepted_without_reading_shared_contents(self):
        shared = self.root / "shared-profile"
        self.primary.rename(shared)
        self.primary.hardlink_to(shared)
        self.assertGreater(self.primary.stat().st_nlink, 1)
        self.assertEqual(self.primary, accounts.resolve_account(self.directory))
        self.assertTrue(self.discover()[0]["available"])

    def test_current_cannot_escape_account(self):
        external = self.root / "external"
        external.mkdir()
        unlink_junction(self.directory / "current")
        junction(external, self.directory / "current")
        self.assertEqual([], self.discover())
        self.assert_unavailable()

    def test_containers_cannot_escape_version(self):
        containers = self.primary.parents[1]
        moved = self.root / "external-containers"
        containers.rename(moved)
        junction(moved, containers)
        self.assertEqual([], self.discover())
        self.assert_unavailable()

    def test_profile_folder_cannot_redirect_even_within_account(self):
        folder = self.primary.parent
        other = folder.with_name("OtherProfile")
        folder.rename(other)
        junction(other, folder)
        self.assertFalse(self.discover()[0]["available"])
        self.assert_unavailable()
        self.assertIsNone(accounts.account_for_source(self.primary))

    def test_profile_folder_cannot_escape_account(self):
        folder = self.primary.parent
        other = self.root / "external-profile"
        folder.rename(other)
        junction(other, folder)
        rows = self.discover()
        if self.LAYOUT == "User":
            self.assertEqual([], rows)
        else:
            self.assertFalse(rows[0]["available"])
        self.assert_unavailable()

    def test_account_junction_outside_fallback_root_is_not_adopted(self):
        root = self.root / "aliases"
        root.mkdir()
        alias = root / self.directory.name
        junction(self.directory, alias)
        self.assertEqual([], self.discover([root]))
        self.assert_unavailable(alias)
        self.assertIsNone(accounts.account_for_source(
            alias / "current" / "ContainersRoot" / self.primary.parent.name / "C_ProfileData"))

    def test_redirected_pointer_metadata_is_not_followed(self):
        pointer = make_pointer(self.local, self.directory)
        original = pointer.parent
        moved = self.root / "external-pointer"
        original.rename(moved)
        junction(moved, original)
        self.assertEqual([], self.discover([]))

    def test_file_symlink_to_backup_or_outside_is_not_a_primary(self):
        backup = self.primary.with_name("C_ProfileBackup")
        self.primary.rename(backup)
        try:
            self.primary.symlink_to(backup)
        except OSError as error:
            if os.name == "nt" and error.winerror == 1314:
                self.skipTest("File symlink privilege is unavailable.")
            raise
        self.assertFalse(self.discover()[0]["available"])
        self.assert_unavailable()
        self.primary.unlink()
        outside = self.root / "outside-profile"
        outside.write_bytes(b"synthetic")
        self.primary.symlink_to(outside)
        self.assert_unavailable()

    def test_manifest_symlink_outside_account_is_rejected(self):
        manifest = self.directory / "7.json"
        outside = self.root / "outside-manifest.json"
        manifest.rename(outside)
        try:
            manifest.symlink_to(outside)
        except OSError as error:
            if os.name == "nt" and error.winerror == 1314:
                self.skipTest("File symlink privilege is unavailable.")
            raise
        self.assertEqual([], self.discover())
        self.assert_unavailable()

    def test_exact_current_alias_and_numbered_primary_are_recognized(self):
        alias = self.directory / "current" / "ContainersRoot" / self.primary.parent.name / "C_ProfileData"
        row, = self.discover()
        self.assertEqual(row, accounts.account_for_source(alias))
        self.assertEqual(row, accounts.account_for_source(str(self.primary)))

    def test_unrelated_selections_are_not_adopted(self):
        unrelated = self.root / "Profile" / "C_ProfileData"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b"synthetic")
        wrong_layout = self.primary.parents[1] / "Other" / "C_ProfileData"
        wrong_layout.parent.mkdir()
        wrong_layout.write_bytes(b"synthetic")
        for path in (None, "", "relative/Profile/C_ProfileData", unrelated, wrong_layout,
                     self.directory, self.primary.parent, self.primary.with_name("garage.json"),
                     self.primary.with_name("C_ProfileBackup"),
                     self.primary.parent / ".." / "Profile" / "C_ProfileData"):
            self.assertIsNone(accounts.account_for_source(path))

    def test_current_rotation_keeps_id_but_refreshes_source(self):
        before, = self.discover()
        new = self.rotate()
        after, = self.discover()
        self.assertEqual(before["id"], after["id"])
        self.assertEqual(before["label"], after["label"])
        self.assertEqual(str(new), after["source"])
        self.assertEqual(new, accounts.resolve_account(before["directory"]))
        self.assertIsNone(accounts.account_for_source(before["source"]))
        self.assertEqual([], self.discover([self.primary.parents[2]]))

    def test_rotation_during_verification_fails_closed(self):
        real = accounts.read_account
        def rotating(path):
            result = real(path)
            self.rotate()
            return result
        with patch.object(accounts, "read_account", side_effect=rotating):
            self.assert_unavailable()

    def test_rotation_during_primary_access_fails_closed(self):
        real = Path.open
        def opening(path, *args, **kwargs):
            stream = real(path, *args, **kwargs)
            if path == self.primary:
                self.rotate()
            return stream
        with patch.object(Path, "open", opening):
            self.assert_unavailable()

    def test_permission_denied_root_does_not_hide_other_accounts(self):
        other = self.root / "denied"
        other.mkdir()
        real = accounts.os.scandir
        def scanning(path):
            if Path(path) == other:
                raise PermissionError("private path must not escape")
            return real(path)
        with patch.object(accounts.os, "scandir", side_effect=scanning):
            self.assertEqual(1, len(self.discover([other, self.saves])))

    def test_manifest_and_primary_permission_failures_are_generic(self):
        real = Path.open
        for denied in (self.directory / "7.json", self.primary):
            def opening(path, *args, **kwargs):
                if path == denied:
                    raise PermissionError("private path and 1234567890")
                return real(path, *args, **kwargs)
            with patch.object(Path, "open", opening):
                self.assert_unavailable()
                rows = self.discover()
            if denied == self.primary:
                self.assertEqual(1, len(rows))
                self.assertFalse(rows[0]["available"])
            else:
                self.assertEqual([], rows)

    def test_cancel_before_start_performs_no_filesystem_work(self):
        self.cancel.set()
        with patch.object(accounts.os, "scandir") as scan, patch.object(accounts, "read_account") as verify:
            with self.assertRaises(InterruptedError):
                accounts.discover_accounts(self.cancel)
        scan.assert_not_called()
        verify.assert_not_called()

    def test_cancellation_during_fallback_is_not_swallowed_as_oserror(self):
        real = accounts._children
        def children(path, limit, cancel):
            for child in real(path, limit, cancel):
                if Path(path) == self.saves / "pgs":
                    self.cancel.set()
                yield child
        with patch.object(accounts, "_children", side_effect=children), self.assertRaises(InterruptedError):
            self.discover()

    def test_cancellation_inside_shared_verifier_iteration(self):
        real = accounts._children
        def children(path, limit, cancel):
            for child in real(path, limit, cancel):
                yield child
                if Path(path).name == "ContainersRoot":
                    self.cancel.set()
        with patch.object(accounts, "_children", side_effect=children), self.assertRaises(InterruptedError):
            self.discover([self.directory])

    def test_cancellation_after_pointer_read(self):
        pointer = make_pointer(self.local, self.directory)
        real = Path.open
        def opening(path, *args, **kwargs):
            stream = real(path, *args, **kwargs)
            if path == pointer:
                self.cancel.set()
            return stream
        with patch.object(Path, "open", opening), self.assertRaises(InterruptedError):
            self.discover([])

    def test_late_cancel_never_returns_partial_rows(self):
        real = accounts._row
        def row(*args):
            result = real(*args)
            self.cancel.set()
            return result
        with patch.object(accounts, "_row", side_effect=row), self.assertRaises(InterruptedError):
            self.discover([self.directory])

    def test_shared_verifier_has_a_real_iteration_limit(self):
        (self.primary.parents[1] / "Other").mkdir()
        with patch.object(accounts, "MAX_CONTAINER_ENTRIES", 1):
            self.assertEqual([], self.discover())
            self.assert_unavailable()

    def test_root_candidate_and_pointer_limits(self):
        second = make_account(self.saves, 456)
        with patch.object(accounts, "MAX_CANDIDATES", 1):
            self.assertEqual(1, len(self.discover()))
        with patch.object(accounts, "MAX_ACCOUNTS", 1):
            self.assertEqual(1, len(self.discover()))
        with patch.object(accounts, "MAX_ROOT_ENTRIES", 1):
            self.assertEqual(1, len(self.discover([self.saves / "pgs"])))
        with patch.object(accounts, "MAX_ROOTS", 1):
            self.assertEqual(1, len(self.discover([self.directory, second])))
        make_pointer(self.local, self.directory)
        make_pointer(self.local, second, user_id=456)
        with patch.object(accounts, "MAX_POINTER_ENTRIES", 1):
            self.assertEqual(1, len(self.discover([])))

    def test_no_old_snapshot_traversal_or_profile_private_content_reads(self):
        old = make_version(self.directory, 1234567890, "6")
        (self.primary.parent / "reader.json").write_text("private test fixture", encoding="utf-8")
        (self.primary.parents[1] / "header").write_bytes(b"not identity evidence")
        read_paths = []
        scanned = []
        real_open, real_children = Path.open, accounts._children

        class GuardedFile:
            def __init__(self, path, stream):
                self.path, self.stream = path, stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def fileno(self):
                return self.stream.fileno()
            def read(self, size=-1):
                read_paths.append(self.path)
                if self.path != self_manifest or size <= 0:
                    raise AssertionError("Unexpected file contents read")
                return self.stream.read(size)

        self_manifest = self.directory / "7.json"
        def opening(path, *args, **kwargs):
            return GuardedFile(Path(path), real_open(path, *args, **kwargs))
        def children(path, limit, cancel):
            scanned.append(Path(path))
            yield from real_children(path, limit, cancel)
        with patch.object(Path, "open", opening), patch.object(accounts, "_children", side_effect=children):
            self.assertTrue(self.discover()[0]["available"])
        self.assertEqual([self_manifest], read_paths)
        self.assertNotIn(old, scanned)
        self.assertEqual({self.saves, self.saves / "pgs", self.primary.parents[1]}, set(scanned))

    def test_dual_primary_layouts_are_ambiguous_even_when_hardlinked(self):
        other_name = "Profile" if self.LAYOUT == "User" else f"User_{1234567890:X}"
        other = self.primary.parents[1] / other_name / "C_ProfileData"
        other.parent.mkdir(exist_ok=True)
        for hardlinked in (False, True):
            with self.subTest(hardlinked=hardlinked):
                if hardlinked:
                    other.hardlink_to(self.primary)
                else:
                    other.write_bytes(b"another synthetic primary")
                row, = self.discover()
                self.assertFalse(row["available"])
                self.assertEqual("", row["source"])
                self.assert_unavailable()
                for source in (self.primary, other):
                    self.assertIsNone(accounts.account_for_source(source))
                    alias = self.directory / "current" / "ContainersRoot" / source.parent.name / source.name
                    self.assertIsNone(accounts.account_for_source(alias))
                other.unlink()

    def test_other_layout_backup_does_not_replace_or_conflict_with_primary(self):
        other_name = "Profile" if self.LAYOUT == "User" else f"User_{1234567890:X}"
        other = self.primary.parents[1] / other_name / "C_ProfileBackup"
        other.parent.mkdir(exist_ok=True)
        other.write_bytes(b"synthetic backup")
        self.assertEqual(self.primary, accounts.resolve_account(self.directory))
        self.assertEqual(str(self.primary), self.discover()[0]["source"])
        self.assertIsNone(accounts.account_for_source(other))

    def test_other_user_primary_is_never_adopted_or_read(self):
        other = self.primary.parents[1] / "User_FFF" / "C_ProfileData"
        other.parent.mkdir()
        other.write_bytes(b"synthetic other user")
        opened = []
        real_open = Path.open
        def opening(path, *args, **kwargs):
            opened.append(Path(path))
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", opening):
            self.assertEqual([], self.discover())
            self.assert_unavailable()
            self.assertIsNone(accounts.account_for_source(other))
            alias = self.directory / "current" / "ContainersRoot" / other.parent.name / other.name
            self.assertIsNone(accounts.account_for_source(alias))
        self.assertNotIn(other, opened)

    def test_default_roots_exclude_remote_unknown_and_optical_drives_before_probing(self):
        drives = {"C:/": 3, "D:/": 2, "X:/": 4, "Y:/": 0, "Z:/": 1, "R:/": 5, "S:/": 6}
        with patch.object(accounts.os, "listdrives", return_value=list(drives), create=True), \
                patch.object(accounts, "_drive_type", side_effect=drives.__getitem__), \
                patch.object(accounts, "_root_candidates", return_value=()) as probe:
            self.assertEqual([], accounts.discover_accounts(self.cancel, local_app_data=""))
        self.assertEqual([Path("C:/XboxGames/GameSave"), Path("D:/XboxGames/GameSave")],
                         [call.args[0] for call in probe.call_args_list])

    def test_drive_type_failure_does_not_probe_that_drive(self):
        with patch.object(accounts.os, "listdrives", return_value=["X:/"], create=True), \
                patch.object(accounts, "_drive_type", side_effect=OSError("unavailable")), \
                patch.object(accounts, "_root_candidates") as probe:
            self.assertEqual([], accounts.discover_accounts(self.cancel, local_app_data=""))
        probe.assert_not_called()


class GarageUserAccountTests(GarageAccountTests):
    LAYOUT = "User"

    def test_zero_padded_lowercase_user_container_matches_verified_numeric_identity(self):
        renamed = self.primary.parent.with_name(f"User_{1234567890:016x}")
        self.primary.parent.rename(renamed)
        self.primary = renamed / "C_ProfileData"
        row, = self.discover()
        self.assertTrue(row["available"])
        self.assertEqual(str(self.primary), row["source"])
        self.assertEqual(row, accounts.account_for_source(self.primary))
        alias = self.directory / "current" / "ContainersRoot" / renamed.name / "C_ProfileData"
        self.assertEqual(row, accounts.account_for_source(alias))

    def test_duplicate_matching_user_containers_with_primaries_are_ambiguous(self):
        duplicate = self.primary.parent.with_name(f"User_{1234567890:016x}")
        duplicate.mkdir()
        other = duplicate / "C_ProfileData"
        other.write_bytes(b"synthetic duplicate")
        row, = self.discover()
        self.assertFalse(row["available"])
        self.assert_unavailable()
        self.assertIsNone(accounts.account_for_source(self.primary))
        self.assertIsNone(accounts.account_for_source(other))


if __name__ == "__main__":
    unittest.main()
