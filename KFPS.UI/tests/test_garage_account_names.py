"""Display-only account identity enrichment, using synthetic save metadata."""
from __future__ import annotations

import contextlib
from datetime import datetime
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/src")]

from kfps_ui import garage_accounts as accounts
from tools.cgroup import fh6_identity as identity
from test_garage_accounts import junction, make_account, make_version, unlink_junction


USER_ID = 1234567890
OLD = datetime(2026, 1, 2, 3, 4, 5)
NEW = datetime(2026, 11, 3, 3, 4, 5)


def header_bytes(name, user_id=USER_ID, created=OLD):
    placeholder = "fixture-placeholder"
    raw = identity.build_vinyl_header("Synthetic", user_id, placeholder, 1, now=created)
    before = placeholder.encode("utf-16le")
    after = name.encode("utf-16le")
    return raw.replace(struct.pack("<I", len(before) // 2) + before,
                       struct.pack("<I", len(after) // 2) + after, 1)


class GarageAccountNameTests(unittest.TestCase):
    def setUp(self):
        run = ROOT / "runtime/garage-account-names-20261103"
        run.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=run)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.directory = make_account(self.root / "saves")
        self.containers = self.directory / "7/ContainersRoot"
        self.primary = self.containers / "Profile/C_ProfileData"
        self.cancel = threading.Event()

    def add_header(self, name="Local Painter", *, key="one", user_id=USER_ID,
                   created=OLD, containers=None):
        path = (containers or self.containers) / f"LayerGroup_{key}" / "header"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(header_bytes(name, user_id, created))
        return path

    def discover(self, roots=None):
        return accounts.discover_accounts(self.cancel, roots=roots or [self.directory],
                                          local_app_data="")

    def row(self):
        row, = self.discover()
        return row

    def assert_named(self, row, name="Local Painter"):
        self.assertEqual(f"{name} - 567890 ({row['id'][:8]})", row["label"])
        self.assertTrue(row["available"])
        self.assertNotIn(str(USER_ID), row["label"])

    def assert_fallback(self, row=None):
        row = self.row() if row is None else row
        self.assertEqual(f"FH6 account 567890 ({row['id'][:8]})", row["label"])
        self.assertTrue(row["available"])

    def test_verified_name_and_manual_recognition_share_label(self):
        self.add_header()
        row = self.row()
        self.assert_named(row)
        self.assertEqual(row, accounts.account_for_source(self.primary))
        alias = self.directory / "current/ContainersRoot/Profile/C_ProfileData"
        self.assertEqual(row, accounts.account_for_source(alias))

    def test_newest_internal_date_wins_over_file_mtime(self):
        old = self.add_header("Old Painter")
        self.add_header("Renamed Painter", key="two", created=NEW)
        os.utime(old, (2000000000, 2000000000))
        self.assert_named(self.row(), "Renamed Painter")

    def test_tied_conflicting_names_fall_back(self):
        self.add_header()
        self.add_header("Different Painter", key="two")
        self.assert_fallback()

    def test_tied_identical_names_are_usable(self):
        self.add_header()
        self.add_header(key="two")
        self.assert_named(self.row())

    def test_foreign_newer_creator_is_ignored(self):
        self.add_header()
        self.add_header("Foreign Painter", key="foreign", user_id=999, created=NEW)
        self.assert_named(self.row())

    def test_foreign_creator_alone_falls_back(self):
        self.add_header("Foreign Painter", user_id=999)
        self.assert_fallback()

    def test_no_headers_fall_back(self):
        self.assert_fallback()

    def test_fake_kfps_and_blank_names_fall_back(self):
        for name in ("KFPS", " kFpS ", "", "   "):
            with self.subTest(name=name):
                self.add_header(name)
                self.assert_fallback()

    def test_fake_newer_name_does_not_replace_verified_name(self):
        self.add_header()
        self.add_header("KFPS", key="fake", created=NEW)
        self.assert_named(self.row())

    def test_malformed_or_unreadable_header_never_leaves_partial_guess(self):
        self.add_header()
        other = self.add_header("New Painter", key="two", created=NEW)
        for raw in (b"", b"not a header", b"x" * 65537):
            with self.subTest(size=len(raw)):
                other.write_bytes(raw)
                self.assert_fallback()
        other.write_bytes(header_bytes("New Painter", created=NEW))
        real_open = Path.open
        def opening(path, *args, **kwargs):
            if path == other:
                raise PermissionError("private metadata detail")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", opening):
            self.assert_fallback()

    def test_missing_header_in_layer_group_is_incomplete(self):
        self.add_header()
        (self.containers / "LayerGroup_missing").mkdir()
        self.assert_fallback()

    def test_nonregular_header_falls_back(self):
        path = self.add_header()
        path.unlink()
        path.mkdir()
        self.assert_fallback()

    def test_control_bidi_zero_width_and_invisible_names_are_rejected(self):
        for char in ("\x00", "\n", "\t", "\x7f", "\x85", "\u2028", "\u2029",
                     "\u202e", "\u2066", "\u200b", "\u200c", "\u200d", "\ufeff",
                     "\u034f", "\ufe0f", "\u3164", "\u2800"):
            with self.subTest(codepoint=ord(char)):
                self.add_header(f"Local{char}Painter")
                self.assert_fallback()

    def test_length_boundary_and_outer_spaces(self):
        self.add_header("  Local Painter  ")
        self.assert_named(self.row())
        self.add_header("a" * 128)
        self.assert_named(self.row(), "a" * 128)
        self.add_header("a" * 129)
        self.assert_fallback()

    def test_unicode_name_remains_literal_plaintext(self):
        name = '\ud14c\uc2a4\ud2b8 "Painter"'
        self.add_header(name)
        self.assert_named(self.row(), name)
        qml = (ROOT / "KFPS.UI/qml/components/GarageBrowser.qml").read_text(encoding="utf-8")
        self.assertIn("labelTextFormat: Text.PlainText", qml)

    def test_malicious_markup_falls_back_even_in_auto_text_tooltips(self):
        for name in ('<b>Painter</b>', '<img src="https://invalid.test/private">',
                     '<img src="file:///private">', '&lt;b&gt;Painter&lt;/b&gt;'):
            with self.subTest(name=name):
                self.add_header(name)
                self.assert_fallback()

    def test_unsafe_newest_name_does_not_choose_an_older_name(self):
        self.add_header()
        self.add_header("New\u202ePainter", key="two", created=NEW)
        self.assert_fallback()

    def test_row_id_directory_source_and_availability_unchanged_by_names(self):
        before = self.row()
        self.add_header()
        after = self.row()
        self.assert_named(after)
        self.assertEqual({k: v for k, v in before.items() if k != "label"},
                         {k: v for k, v in after.items() if k != "label"})

    def test_same_user_in_two_directories_has_deterministic_distinct_labels(self):
        self.add_header()
        second = make_account(self.root / "second")
        self.add_header(containers=second / "7/ContainersRoot")
        rows = self.discover([self.directory, second])
        for row in rows:
            self.assert_named(row)
        self.assertEqual(2, len({row["label"] for row in rows}))
        self.assertEqual(2, len({row["id"] for row in rows}))
        self.assertEqual(rows, self.discover([second, self.directory]))

    def test_version_rotation_keeps_id_and_discovers_current_name_only(self):
        self.add_header("Old Painter")
        before = self.row()
        new = make_version(self.directory, USER_ID, "8")
        self.add_header("New Painter", containers=new, created=NEW)
        unlink_junction(self.directory / "current")
        junction(new.parent, self.directory / "current")
        after = self.row()
        self.assert_named(after, "New Painter")
        self.assertEqual(before["id"], after["id"])
        self.assertEqual(before["directory"], after["directory"])

    def test_entry_budget_boundary_and_overflow_fall_back(self):
        self.add_header()
        self.assertIn(accounts.MAX_NAME_ENTRIES, (512, 1024))
        with patch.object(accounts, "MAX_NAME_ENTRIES", 3):
            self.assert_named(self.row())  # User, Profile, LayerGroup.
            self.add_header("New Painter", key="two", created=NEW)
            self.assert_fallback()

    def test_limit_counts_non_header_entries_too(self):
        self.add_header()
        (self.containers / "Unrelated").mkdir()
        with patch.object(accounts, "MAX_NAME_ENTRIES", 3):
            self.assert_fallback()

    def test_cancel_during_header_read_propagates_for_discovery_and_manual(self):
        header = self.add_header()
        real_open = Path.open
        def opening(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            if path == header:
                self.cancel.set()
            return stream
        for action in (self.discover, lambda: accounts.account_for_source(self.primary, cancel=self.cancel)):
            self.cancel.clear()
            with patch.object(Path, "open", opening), self.assertRaises(InterruptedError):
                action()

    def test_cancel_during_invalid_header_is_not_swallowed(self):
        header = self.add_header()
        real_open = Path.open
        def opening(path, *args, **kwargs):
            if path == header:
                self.cancel.set()
                raise PermissionError("private metadata detail")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", opening), self.assertRaises(InterruptedError):
            self.discover()

    def test_cancel_during_bounded_enumeration_propagates(self):
        self.add_header()
        real_children = accounts._children
        def children(path, limit, cancel):
            for child in real_children(path, limit, cancel):
                if limit == accounts.MAX_NAME_ENTRIES:
                    self.cancel.set()
                yield child
        with patch.object(accounts, "_children", side_effect=children), self.assertRaises(InterruptedError):
            self.discover()

    def test_manual_precancel_does_no_work(self):
        self.cancel.set()
        with patch.object(accounts, "read_account") as verify, self.assertRaises(InterruptedError):
            accounts.account_for_source(self.primary, cancel=self.cancel)
        verify.assert_not_called()

    def test_manual_cancel_during_final_current_check_propagates(self):
        self.add_header()
        resolved = False
        real_creator, real_current = accounts.resolve_creator, accounts._same_current
        def creator(*args, **kwargs):
            nonlocal resolved
            result = real_creator(*args, **kwargs)
            resolved = True
            return result
        def current(account):
            real_current(account)
            if resolved:
                self.cancel.set()
        with patch.object(accounts, "resolve_creator", side_effect=creator), \
                patch.object(accounts, "_same_current", side_effect=current), \
                self.assertRaises(InterruptedError):
            accounts.account_for_source(self.primary, cancel=self.cancel)

    def test_resolution_does_not_read_names(self):
        self.add_header()
        with patch.object(identity, "parse_vinyl_header", side_effect=AssertionError("name work")):
            self.assertEqual(self.primary, accounts.resolve_account(self.directory))

    def test_reads_only_bounded_headers_never_payloads_or_unrelated_headers(self):
        header = self.add_header()
        payload = header.with_name("C_group")
        payload.write_bytes(b"private payload")
        unrelated = self.containers / "Livery_one/header"
        unrelated.parent.mkdir()
        unrelated.write_bytes(b"not vinyl metadata")
        reads = []
        real_open = Path.open
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
                if self.path == header:
                    if not 0 < size <= 65537:
                        raise AssertionError("Unbounded header read")
                    reads.append(size)
                elif self.path != self_manifest:
                    raise AssertionError("Unexpected contents read")
                return self.stream.read(size)
        self_manifest = self.directory / "7.json"
        def opening(path, *args, **kwargs):
            if path in (payload, unrelated):
                raise AssertionError("Non-metadata opened")
            return GuardedFile(path, real_open(path, *args, **kwargs))
        with patch.object(Path, "open", opening):
            self.assert_named(self.row())
        self.assertEqual([65537], reads)

    def test_redirected_group_falls_back_without_opening_target(self):
        self.add_header()
        for local in (True, False):
            with self.subTest(local=local):
                target = self.containers / "Other" if local else self.root / "outside"
                target.mkdir()
                (target / "header").write_bytes(header_bytes("New Painter", created=NEW))
                redirected = self.containers / "LayerGroup_redirect"
                junction(target, redirected)
                self.addCleanup(lambda p=redirected: unlink_junction(p) if p.exists() else None)
                real_open = Path.open
                def opening(path, *args, **kwargs):
                    if path.parent in (target, redirected):
                        raise AssertionError("Redirect target opened")
                    return real_open(path, *args, **kwargs)
                with patch.object(Path, "open", opening):
                    self.assert_fallback()
                unlink_junction(redirected)

    def test_redirected_header_falls_back_without_opening_target(self):
        header = self.add_header()
        target = header.with_name("other")
        header.rename(target)
        try:
            header.symlink_to(target)
        except OSError as error:
            if os.name == "nt" and error.winerror == 1314:
                self.skipTest("File symlink privilege is unavailable")
            raise
        real_open = Path.open
        def opening(path, *args, **kwargs):
            if path in (header, target):
                raise AssertionError("Redirected header opened")
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", opening):
            self.assert_fallback()

    def test_rotation_during_name_read_does_not_return_stale_row(self):
        header = self.add_header()
        new = make_version(self.directory, USER_ID, "8")
        real_open = Path.open
        def opening(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            if path == header:
                unlink_junction(self.directory / "current")
                junction(new.parent, self.directory / "current")
            return stream
        with patch.object(Path, "open", opening):
            self.assertEqual([], self.discover())

    def test_no_private_diagnostics_or_game_writes(self):
        self.add_header()
        before = {p: p.read_bytes() for p in self.containers.rglob("*") if p.is_file()}
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            self.assert_named(self.row())
        self.assertEqual("", output.getvalue())
        self.assertEqual(before, {p: p.read_bytes() for p in self.containers.rglob("*") if p.is_file()})

    def test_shared_default_resolver_still_ignores_malformed_headers(self):
        self.add_header()
        self.add_header(key="bad").write_bytes(b"invalid")
        self.assertEqual("Local Painter", identity.resolve_creator(identity.read_account(self.directory)).name)

    def test_supplied_resolver_paths_fail_closed_and_propagate_cancellation(self):
        good = self.add_header()
        bad = self.add_header(key="bad")
        bad.write_bytes(b"invalid")
        account = identity.read_account(self.directory)
        with self.assertRaises(identity.FH6IdentityError):
            identity.resolve_creator(account, header_paths=iter((good, bad)))
        def cancelled():
            yield good
            raise InterruptedError("cancelled")
        with self.assertRaises(InterruptedError):
            identity.resolve_creator(account, header_paths=cancelled())

    def test_changed_header_during_read_falls_back(self):
        header = self.add_header()
        real_open = Path.open
        class ChangingFile:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def read(self, size=-1):
                raw = self.stream.read(size)
                with real_open(header, "wb") as target:
                    target.write(header_bytes("Changed Painter", created=NEW))
                return raw
        def opening(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            return ChangingFile(stream) if path == header else stream
        with patch.object(Path, "open", opening):
            self.assert_fallback()

    def test_header_directory_permission_failure_discards_partial_result(self):
        self.add_header()
        real_children = accounts._children
        def children(path, limit, cancel):
            yield from real_children(path, limit, cancel)
            if limit == accounts.MAX_NAME_ENTRIES:
                raise PermissionError("private metadata detail")
        with patch.object(accounts, "_children", side_effect=children):
            self.assert_fallback()


if __name__ == "__main__":
    unittest.main()
