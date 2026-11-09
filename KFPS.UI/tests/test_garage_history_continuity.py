"""Synthetic proof of the native-history gate, not native decoder qualification."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
EVIDENCE = ROOT / "runtime/garage-workflow-20261104/history"
sys.path[:0] = [str(UI / "src"), str(ROOT)]

from PySide6.QtCore import QCoreApplication
from kfps_ui import garage_accounts as accounts, garage_reader as reader
from kfps_ui.app_paths import AppPaths
from kfps_ui.garage_index import GarageError, GarageStore, digest, normalize_garage, profile_identity
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from kfps_ui.models import DictListModel
from test_garage_accounts import junction, make_account, make_version, unlink_junction
from test_garage_index import car


class _HistoryFixture(unittest.TestCase):
    def setUp(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-", dir=EVIDENCE)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = make_account(self.root / "saves", 10101, layout="User")
        self.source = accounts.resolve_account(self.directory)
        self.write_rows(self.source)
        self.cancel = threading.Event()
        self.store = GarageStore(self.root / "index")
        self.config = self.root / "reader.json"
        script = self.root / "synthetic_reader.py"
        # Exercise the real stdin/process boundary without accessing a game save
        # or pretending to qualify its external binary decoder.
        script.write_text("import json,sys\nassert sys.argv[1:] == ['--stdin']\n"
                          "print(json.dumps(json.load(sys.stdin)))\n", encoding="utf-8")
        self.config.write_text(json.dumps({"python": sys.executable, "script": str(script)}),
                               encoding="utf-8")
        self.enterContext(patch("kfps_ui.garage_reader._reader_command",
                                return_value=[sys.executable, "-I", "-B", str(script), "--stdin"]))

    def write_rows(self, source, *, wing=3, model=123):
        source.write_text(json.dumps([{**car(model=model), "RearWing": wing}]), encoding="utf-8")

    def rotate(self, version="8", *, wing=99):
        containers = make_version(self.directory, 10101, version, layout="User")
        source = containers / "User_2775/C_ProfileData"
        self.write_rows(source, wing=wing)
        unlink_junction(self.directory / "current")
        junction(containers.parent, self.directory / "current")
        return source

    def discover(self):
        return accounts.discover_accounts(self.cancel, roots=[self.root / "saves"], local_app_data="")

    def validator(self, directory, source):
        def validate():
            if accounts.resolve_account(directory) != source:
                raise GarageError("The active save changed during the scan.")
        return validate

    def scan(self, source=None, *, directory=None, validate_source=None, history=True):
        source = source or self.source
        if validate_source is None:
            validate_source = self.validator(directory or self.directory, source)
        return reader.scan(source, self.store, self.config, self.cancel,
                           history=history, validate_source=validate_source)

    def assert_gated(self, state):
        self.assertEqual("", state["scope"])
        self.assertEqual([], state["history"])
        self.assertEqual(state, self.store.load(state["profile"]))


class GarageHistoryContinuityProofTests(_HistoryFixture):
    def test_coherent_metadata_cannot_distinguish_identical_primary_bytes(self):
        other_directory = make_account(self.root / "saves", 20202, layout="User")
        other = accounts.resolve_account(other_directory)
        other.write_bytes(self.source.read_bytes())
        rows = self.discover()
        self.assertEqual(2, len(rows))
        self.assertEqual(2, len({row["id"] for row in rows}))
        self.assertTrue(all(row["available"] for row in rows))
        for row in rows:
            self.assertEqual(row, accounts.account_for_source(row["source"]))
        first = self.scan()["state"]
        second = self.scan(other, directory=other_directory)["state"]
        self.assertEqual(first["sourceHash"], second["sourceHash"])
        self.assertEqual(first["cars"], second["cars"])
        self.assertNotEqual(first["profile"], second["profile"])
        self.assert_gated(first)
        self.assert_gated(second)

    def test_matching_car_ids_and_claimed_owner_fields_do_not_supply_scope(self):
        raw = [{**car(), "UserId": 10101, "AccountId": 10101, "ProfileId": "claimed"}]
        self.source.write_text(json.dumps(raw), encoding="utf-8")
        first = self.scan()["state"]
        row, = self.discover()
        self.source.write_text(json.dumps([{**raw[0], "UserId": 20202, "RearWing": 77}]), encoding="utf-8")
        self.assertEqual(row, self.discover()[0])
        second = self.scan()["state"]
        self.assertEqual(first["cars"][0]["instanceId"], second["cars"][0]["instanceId"])
        self.assertEqual(77, second["cars"][0]["parts"]["RearWing"])
        self.assertNotIn("UserId", second["cars"][0])
        self.assert_gated(second)

    def test_empty_garage_cannot_establish_owner_by_record_overlap(self):
        self.source.write_text("[]", encoding="utf-8")
        self.assert_gated(self.scan()["state"])
        self.write_rows(self.source)
        self.assert_gated(self.scan()["state"])

    def test_inconsistent_manifest_is_rejected_before_it_can_supply_identity(self):
        manifest = self.directory / "7.json"
        original = json.loads(manifest.read_text(encoding="utf-8"))
        for field, value in (("UserId", "20202"), ("GameId", "OTHER"), ("Version", 8)):
            with self.subTest(field=field):
                manifest.write_text(json.dumps({"Manifest": {**original["Manifest"], field: value}}),
                                    encoding="utf-8")
                self.assertEqual([], self.discover())
                self.assertIsNone(accounts.account_for_source(self.source))
                with self.assertRaises(GarageError):
                    accounts.resolve_account(self.directory)
        self.assertFalse(self.store.root.exists())

    def test_rotation_preserves_locator_but_does_not_join_unproved_profiles(self):
        before_row, = self.discover()
        first = self.scan()["state"]
        old_index = self.store.path(first["profile"]).read_bytes()
        newer = self.rotate()
        after_row, = self.discover()
        self.assertEqual(before_row["id"], after_row["id"])
        self.assertNotEqual(before_row["source"], after_row["source"])
        self.assertIsNone(accounts.account_for_source(self.source))
        second = self.scan(newer)["state"]
        self.assertNotEqual(first["profile"], second["profile"])
        self.assertEqual(old_index, self.store.path(first["profile"]).read_bytes())
        self.assert_gated(second)

    def test_manual_backup_and_copy_remain_unscoped_even_with_identical_bytes(self):
        self.scan()
        for source in (self.source.with_name("C_ProfileBackup"), self.root / "garage.json"):
            with self.subTest(kind=source.suffix or "backup"):
                source.write_bytes(self.source.read_bytes())
                self.assertIsNone(accounts.account_for_source(source))
                self.assert_gated(self.scan(source, validate_source=lambda: None)["state"])
                self.write_rows(source, wing=88)
                self.assert_gated(self.scan(source, validate_source=lambda: None)["state"])

    def test_rotation_at_atomic_commit_preserves_previous_index(self):
        first = self.scan()["state"]
        index = self.store.path(first["profile"])
        before = index.read_bytes()
        self.write_rows(self.source, wing=77)
        validate = self.validator(self.directory, self.source)
        calls = []
        def rotating():
            calls.append(True)
            if len(calls) == 2:
                self.rotate()
            validate()
        with self.assertRaisesRegex(GarageError, "changed"):
            self.scan(validate_source=rotating)
        self.assertEqual(2, len(calls))
        self.assertEqual(before, index.read_bytes())
        self.assertEqual([], list(self.store.root.glob(".garage-*")))

    def test_metadata_change_at_atomic_commit_preserves_previous_index(self):
        first = self.scan()["state"]
        index = self.store.path(first["profile"])
        before = index.read_bytes()
        self.write_rows(self.source, wing=77)
        validate = self.validator(self.directory, self.source)
        calls = []
        def changing():
            calls.append(True)
            if len(calls) == 2:
                (self.directory / "7.json").write_text("{}", encoding="utf-8")
            validate()
        with self.assertRaises(GarageError):
            self.scan(validate_source=changing)
        self.assertEqual(before, index.read_bytes())
        self.assertEqual([], list(self.store.root.glob(".garage-*")))

    def test_changes_during_decode_and_reused_read_do_not_publish(self):
        first = self.scan()["state"]
        before = self.store.path(first["profile"]).read_bytes()
        original = self.source.read_bytes()
        self.write_rows(self.source, wing=22)
        decode = reader.reader_records
        def changing(*args):
            result = decode(*args)
            self.write_rows(self.source, wing=33)
            return result
        with patch.object(reader, "reader_records", side_effect=changing), self.assertRaises(GarageError):
            self.scan()
        self.source.write_bytes(original)
        snapshot = reader.snapshot
        calls = []
        def changing_reuse(path, event):
            calls.append(True)
            if len(calls) == 2:
                self.write_rows(self.source, wing=44)
            return snapshot(path, event)
        with patch.object(reader, "snapshot", side_effect=changing_reuse), self.assertRaises(GarageError):
            self.scan()
        self.assertEqual(before, self.store.path(first["profile"]).read_bytes())

    def test_cancellation_after_validator_preserves_new_and_reused_indexes(self):
        first = self.scan()["state"]
        index = self.store.path(first["profile"])
        before = index.read_bytes()
        original = self.source.read_bytes()
        for changed in (False, True):
            with self.subTest(changed=changed):
                self.cancel.clear()
                self.source.write_bytes(original)
                if changed:
                    self.write_rows(self.source, wing=44)
                calls = []
                def cancelling():
                    self.validator(self.directory, self.source)()
                    calls.append(True)
                    if len(calls) == (2 if changed else 1):
                        self.cancel.set()
                with self.assertRaises(InterruptedError):
                    self.scan(validate_source=cancelling)
                self.assertEqual(before, index.read_bytes())
                self.assertEqual([], list(self.store.root.glob(".garage-*")))

    def test_cancelled_native_child_is_reaped_without_publishing(self):
        processes = []
        start = reader.subprocess.Popen
        def cancelling(*args, **kwargs):
            process = start(*args, **kwargs)
            processes.append(process)
            self.cancel.set()
            return process
        with patch.object(reader.subprocess, "Popen", side_effect=cancelling), self.assertRaises(InterruptedError):
            self.scan()
        self.assertEqual(1, len(processes))
        self.assertIsNotNone(processes[0].poll())
        self.assertFalse(self.store.root.exists())

    def test_old_indexes_are_reread_and_never_promoted_from_discovery(self):
        first = self.scan()["state"]
        index = self.store.path(first["profile"])
        for legacy_format in (True, False):
            with self.subTest(legacy_format=legacy_format):
                legacy = json.loads(json.dumps(first))
                if legacy_format:
                    legacy["format"] = 1
                else:
                    row = legacy["cars"][0]
                    del row["parts"]["ChassisStiffness"]
                    row["buildSignature"] = digest([row["carId"], row["parts"]])
                legacy["checksum"] = digest({key: value for key, value in legacy.items() if key != "checksum"})
                index.write_text(json.dumps(legacy), encoding="utf-8")
                self.assertIsNone(self.store.load(first["profile"]))
                with patch.object(reader, "reader_records", wraps=reader.reader_records) as decode:
                    result = self.scan()
                decode.assert_called_once()
                self.assertFalse(result["reused"])
                self.assert_gated(result["state"])

    def test_restart_reuses_unscoped_index_without_decoder_or_write(self):
        first = self.scan()["state"]
        self.store = GarageStore(self.store.root)
        before = self.store.path(first["profile"]).read_bytes()
        with patch.object(reader, "reader_records", side_effect=AssertionError("unexpected decoder")), \
                patch.object(self.store, "publish", side_effect=AssertionError("unexpected write")):
            result = self.scan()
        self.assertTrue(result["reused"])
        self.assert_gated(result["state"])
        self.assertEqual(before, self.store.path(first["profile"]).read_bytes())

    def test_explicit_scoped_store_contract_stays_bounded_and_opt_in(self):
        ident, scope = "a" * 64, "b" * 64
        for revision in range(23):
            rows = normalize_garage([{**car(ident=n), "RearWing": revision} for n in range(205)])
            state = self.store.publish(ident, digest(revision), rows, history=True, scope=scope)
        self.assertEqual(20, len(state["history"]))
        for event in state["history"]:
            self.assertEqual(205, event["count"])
            self.assertEqual(200, len(event["changes"]))
        self.assertEqual(state, GarageStore(self.store.root).load(ident))
        switched = self.store.publish(ident, digest("switch"), rows, history=True, scope="c" * 64)
        self.assertEqual([], switched["history"])
        disabled = self.store.publish(ident, digest("disabled"), rows, history=False, scope=scope)
        self.assertEqual([], disabled["history"])


class GarageHistoryContinuityServiceTests(_HistoryFixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        super().setUp()
        self.paths = AppPaths(ROOT, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        self.log = LogService()
        self.addCleanup(self.log.close)
        self.liveries = SimpleNamespace(sourceModel=DictListModel(["path", "carId", "modelCode", "title"]))
        self.service = self.make_service()
        self.service.root.mkdir(parents=True)
        (self.service.root / "reader.json").write_bytes(self.config.read_bytes())
        discovery = patch("kfps_ui.garage_service.discover_accounts", side_effect=lambda event:
                          accounts.discover_accounts(event, roots=[self.root / "saves"], local_app_data=""))
        self.discovery = discovery.start()
        self.addCleanup(discovery.stop)

    def make_service(self):
        service = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(lambda: self.assertTrue(service.close(), "test worker did not stop"))
        return service

    def wait(self, service=None):
        service = service or self.service
        deadline = time.monotonic() + 8
        while service.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.003)
        self.assertFalse(service.busy, service.status)

    def choose(self):
        self.service.enter()
        self.wait()
        self.assertFalse(self.service.hasSource)
        self.service.selectAccount(self.service.accountOptions[0]["id"])
        self.wait()
        self.assertEqual(1, self.service.total)

    def test_validated_native_history_request_is_rejected_without_setting_write(self):
        self.choose()
        settings = self.service.root / "settings.json"
        before = settings.read_bytes()
        source_before = self.source.read_bytes()
        self.service.setHistoryEnabled(True)
        self.assertFalse(self.service.historyAvailable)
        self.assertFalse(self.service.historyEnabled)
        self.assertIn("unavailable", self.service.status)
        self.assertEqual(before, settings.read_bytes())
        self.assertEqual(source_before, self.source.read_bytes())
        self.assertEqual([], self.service.history)

    def test_rotation_switch_backup_and_restart_preserve_native_history_gate(self):
        self.choose()
        selected = self.service.selectedAccountId
        self.service.select("1")
        self.service.pinComparison()
        newer = self.rotate()
        self.service.refresh()
        self.wait()
        self.assertEqual(selected, self.service.selectedAccountId)
        self.assertEqual(str(newer), self.service._source)
        self.assertEqual("", self.service.compareLabel)
        self.assertFalse(self.service.historyAvailable)
        other_directory = make_account(self.root / "saves", 20202, layout="User")
        other = accounts.resolve_account(other_directory)
        self.write_rows(other, model=456)
        self.service.rescanAccounts()
        self.wait()
        other_id = next(row["id"] for row in self.service.accountOptions if row["id"] != selected)
        self.service.selectAccount(other_id)
        self.wait()
        self.assertEqual(456, self.service.cars.get(0)["carId"])
        self.assertEqual("", self.service.selectedId)
        self.assertFalse(self.service.historyAvailable)
        restored = self.make_service()
        restored.enter()
        self.wait(restored)
        self.assertEqual(other_id, restored.selectedAccountId)
        self.assertTrue(restored.diagnosticSummary["lastScanReused"])
        self.assertFalse(restored.historyAvailable)
        backup = other.with_name("C_ProfileBackup")
        backup.write_bytes(other.read_bytes())
        restored.scanSource(str(backup))
        self.wait(restored)
        self.assertTrue(restored.selectedAccountId.startswith("manual:"))
        self.assertFalse(restored.historyAvailable)
        self.assertEqual([], restored.history)

    def test_failed_account_switch_keeps_settings_index_and_previous_rows(self):
        self.choose()
        before_settings = (self.service.root / "settings.json").read_bytes()
        old_state = self.service._state
        before_index = self.service.store.path(old_state["profile"]).read_bytes()
        other_directory = make_account(self.root / "saves", 20202, layout="User")
        other = accounts.resolve_account(other_directory)
        other.write_text("not a valid reader payload", encoding="utf-8")
        self.service.rescanAccounts()
        self.wait()
        other_id = next(row["id"] for row in self.service.accountOptions if row["id"] != self.service.selectedAccountId)
        self.service.selectAccount(other_id)
        self.wait()
        self.assertEqual(old_state, self.service._state)
        self.assertEqual(before_settings, (self.service.root / "settings.json").read_bytes())
        self.assertEqual(before_index, self.service.store.path(old_state["profile"]).read_bytes())
        self.assertIsNone(self.service.store.load(profile_identity(other)))
        self.assertFalse(self.service.historyAvailable)
        diagnostics = "\n".join(self.log._diagnostic_lines)
        self.assertNotIn(str(self.root), diagnostics)
        self.assertNotIn(str(other_directory), diagnostics)

    def test_startup_and_idle_do_not_discover_decode_or_write_history(self):
        self.discovery.assert_not_called()
        self.assertIsNone(self.service._thread)
        self.choose()
        with patch("kfps_ui.garage_service.threading.Thread", side_effect=AssertionError("idle worker")), \
                patch.object(reader, "reader_records", side_effect=AssertionError("idle decoder")), \
                patch.object(self.service.store, "publish", side_effect=AssertionError("idle history write")), \
                patch("kfps_ui.garage_service.atomic_json", side_effect=AssertionError("idle settings write")):
            for _ in range(20):
                self.service.enter()
                self.app.processEvents()
        self.discovery.assert_called_once()
        self.assertFalse(self.service.historyAvailable)


if __name__ == "__main__":
    unittest.main()
