from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.garage_index import GarageError
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from kfps_ui.models import DictListModel
from test_garage_index import car


class GarageAccountServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        self.log = LogService()
        self.addCleanup(self.log.close)
        self.liveries = SimpleNamespace(sourceModel=DictListModel(["path", "carId", "modelCode", "title"]))
        self.first = self.account("a", 123)
        self.second = self.account("b", 456)
        self.rows = [self.first, self.second]
        self.discovery = self.enter_patch("discover_accounts", side_effect=lambda *a, **kw: list(self.rows))
        self.resolve = self.enter_patch("resolve_account", side_effect=self.resolve_directory)
        self.enter_patch("account_for_source", return_value=None)
        self.service = self.make_service()

    def enter_patch(self, name, **kwargs):
        p = patch("kfps_ui.garage_service." + name, **kwargs)
        result = p.start()
        self.addCleanup(p.stop)
        return result

    def account(self, ident, model):
        directory = self.root / ident
        source = directory / "1" / "Profile" / "garage.json"
        source.parent.mkdir(parents=True)
        source.write_text(json.dumps([car(1, model), car(2, model)]))
        return {"id": ident, "label": "FH6 account " + ident, "directory": str(directory),
                "source": str(source), "available": True}

    def resolve_directory(self, directory):
        return Path(next(r["source"] for r in self.rows if r["directory"] == str(directory)))

    def make_service(self):
        service = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(service.close)
        return service

    def wait(self, service=None):
        service = service or self.service
        deadline = time.monotonic() + 5
        while service.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.003)
        self.assertFalse(service.busy, service.status)

    def choose_first(self):
        self.service.enter()
        self.wait()
        self.service.selectAccount("a")
        self.wait()
        self.assertEqual("a", self.service.selectedAccountId)

    def test_first_visit_requires_choice_even_with_one_account_and_no_startup_discovery(self):
        self.rows = [self.first]
        self.discovery.assert_not_called()
        self.service.activate()
        self.discovery.assert_not_called()
        self.service.enter()
        self.wait()
        self.assertEqual(1, len(self.service.accountOptions))
        self.assertFalse(self.service.hasSource)
        self.assertEqual("", self.service.selectedAccountId)
        self.assertTrue(self.service.accountsDiscovered)
        self.assertFalse((self.service.root / "settings.json").exists())
        self.service.enter()
        self.discovery.assert_called_once()

    def test_selection_switch_restart_and_summary(self):
        self.choose_first()
        s = self.service
        self.assertEqual(2, s.total)
        self.assertEqual(1, s.summary["models"])
        self.assertEqual(2, s.summary["duplicates"])
        s.select("1")
        s.pinComparison()
        s.selectAccount("b")
        self.wait()
        self.assertEqual("b", s.selectedAccountId)
        self.assertEqual(456, s.cars.get(0)["carId"])
        self.assertEqual("", s.selectedId)
        self.assertEqual("", s.compareLabel)
        restored = self.make_service()
        restored.enter()
        self.wait(restored)
        self.assertEqual("b", restored.selectedAccountId)
        self.assertEqual(456, restored.cars.get(0)["carId"])

    def test_failed_switch_and_unknown_id_keep_previous_selection(self):
        self.choose_first()
        before = (self.service.root / "settings.json").read_bytes()
        self.service.selectAccount("not-discovered")
        self.assertEqual("a", self.service.selectedAccountId)
        Path(self.second["source"]).write_text("broken")
        self.service.selectAccount("b")
        self.wait()
        self.assertEqual("a", self.service.selectedAccountId)
        self.assertEqual(2, self.service.total)
        self.assertEqual(before, (self.service.root / "settings.json").read_bytes())

    def test_refresh_follows_current_version_not_saved_numbered_folder(self):
        self.choose_first()
        current = Path(self.first["directory"]) / "2" / "Profile" / "garage.json"
        current.parent.mkdir(parents=True)
        current.write_text(json.dumps([car(4, 999)]))
        self.first["source"] = str(current)
        self.service.refresh()
        self.wait()
        self.assertEqual("a", self.service.selectedAccountId)
        self.assertEqual(999, self.service.cars.get(0)["carId"])
        self.assertEqual(str(current), self.service._source)

    def test_rotation_during_scan_keeps_snapshot_and_settings(self):
        self.choose_first()
        before = (self.service.root / "settings.json").read_bytes()
        initial = Path(self.first["source"])
        self.resolve.side_effect = [initial, initial.parent / "changed.json"]
        self.service.refresh()
        self.wait()
        self.assertEqual(2, self.service.total)
        self.assertIn("changed", self.service.status)
        self.assertEqual(before, (self.service.root / "settings.json").read_bytes())

    def test_unavailable_remembered_account_keeps_cache_and_does_not_choose_another(self):
        self.choose_first()
        self.rows = [self.second]
        self.service.rescanAccounts()
        self.wait()
        self.assertEqual("a", self.service.selectedAccountId)
        self.assertEqual(2, self.service.total)
        missing = next(r for r in self.service.accountOptions if r["id"] == "a")
        self.assertFalse(missing["available"])

    def test_cancel_discovery_and_failure_are_retryable(self):
        def cancel(event, **kwargs):
            event.set()
            raise InterruptedError()
        self.discovery.side_effect = cancel
        self.service.enter()
        self.wait()
        self.assertEqual([], self.service.accountOptions)
        self.discovery.side_effect = OSError("private-account-path")
        self.service.rescanAccounts()
        self.wait()
        self.assertNotIn("private-account-path", self.service.accountStatus)
        self.discovery.side_effect = lambda *a, **kw: self.rows
        self.service.rescanAccounts()
        self.wait()
        self.assertEqual(2, len(self.service.accountOptions))

    def test_manual_selection_remains_available_with_discovery_and_restart(self):
        self.service.scanSource(self.first["source"])
        self.wait()
        manual = self.service.selectedAccountId
        self.assertTrue(manual.startswith("manual:"))
        self.service.enter()
        self.wait()
        self.assertEqual(manual, self.service.selectedAccountId)
        self.assertTrue(any(r["id"] == manual for r in self.service.accountOptions))
        restored = self.make_service()
        restored.activate()
        self.assertEqual(manual, restored.selectedAccountId)
        self.assertEqual(2, restored.total)

    def test_diagnostics_never_contain_accounts_or_source_paths(self):
        self.choose_first()
        text = json.dumps(self.service.diagnosticSummary)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn(self.first["label"], text)
        self.assertEqual(2, self.service.diagnosticSummary["accountCount"])

    def test_worker_start_failure_can_retry_and_does_not_touch_cached_garage(self):
        self.choose_first()
        with patch("kfps_ui.garage_service.threading.Thread.start", side_effect=RuntimeError("PRIVATE")):
            self.service.rescanAccounts()
        self.assertFalse(self.service.busy)
        self.assertEqual(2, self.service.total)
        self.assertIn("retry", self.service.accountStatus)
        self.assertNotIn("PRIVATE", self.service.accountStatus)
        self.service.rescanAccounts()
        self.wait()
        self.assertEqual(2, len(self.service.accountOptions))

    def test_cancelled_switch_does_not_change_selected_account_or_index(self):
        self.choose_first()
        before = (self.service.root / "settings.json").read_bytes()
        def cancel_source(source, event):
            event.set()
            raise InterruptedError()
        with patch("kfps_ui.garage_reader.snapshot", side_effect=cancel_source):
            self.service.selectAccount("b")
            self.wait()
        self.assertEqual("a", self.service.selectedAccountId)
        self.assertEqual(before, (self.service.root / "settings.json").read_bytes())
        self.assertEqual(2, self.service.total)

    def test_corrupt_account_settings_fall_back_to_existing_manual_source(self):
        self.choose_first()
        settings = self.service.root / "settings.json"
        data = json.loads(settings.read_text())
        data["account"] = {"directory": "relative", "id": "bad", "label": "invalid"}
        settings.write_text(json.dumps(data))
        restored = self.make_service()
        restored.activate()
        self.assertTrue(restored.selectedAccountId.startswith("manual:"))
        self.assertEqual(2, restored.total)

    def test_save_failure_keeps_current_session_and_reports_not_remembered(self):
        self.service.enter()
        self.wait()
        with patch("kfps_ui.garage_service.atomic_json", side_effect=OSError("PRIVATE")):
            self.service.selectAccount("a")
            self.wait()
        self.assertEqual("a", self.service.selectedAccountId)
        self.assertIn("could not be remembered", self.service.status)
        self.assertFalse((self.service.root / "settings.json").exists())

    def test_idle_enter_does_not_start_another_worker_or_reset_rows(self):
        self.choose_first()
        resets = []
        self.service.cars.modelReset.connect(lambda: resets.append(True))
        with patch("kfps_ui.garage_service.threading.Thread", side_effect=AssertionError("idle worker")):
            for _ in range(10):
                self.service.enter()
                self.app.processEvents()
        self.discovery.assert_called_once()
        self.assertEqual([], resets)

    def test_closed_service_ignores_late_discovery_and_selection(self):
        self.service.close()
        self.service._apply_accounts({"accounts": self.rows})
        self.service.enter()
        self.service.selectAccount("a")
        self.discovery.assert_not_called()
        self.assertEqual([], self.service.accountOptions)

    def test_real_discovery_current_alias_worker_rotation_and_restart(self):
        from kfps_ui import garage_accounts
        from test_garage_accounts import make_account, make_version, junction, unlink_junction
        directory = make_account(self.root / "actual-layout")
        source = directory / "7" / "ContainersRoot" / "Profile" / "C_ProfileData"
        source.write_text(json.dumps([car(1, 123)]))
        self.service.root.mkdir(parents=True)
        reader = self.service.root / "synthetic_reader.py"
        reader.write_text("import json,sys\nprint(json.dumps(json.load(sys.stdin)))\n")
        (self.service.root / "reader.json").write_text(json.dumps({"python": sys.executable, "script": str(reader)}))
        self.enterContext(patch("kfps_ui.garage_reader._reader_command",
                                return_value=[sys.executable, "-I", "-B", str(reader), "--stdin"]))
        self.discovery.side_effect = lambda event, **kwargs: garage_accounts.discover_accounts(
            event, roots=[directory], local_app_data="")
        self.resolve.side_effect = garage_accounts.resolve_account
        with patch("kfps_ui.garage_service.account_for_source", wraps=garage_accounts.account_for_source):
            self.service.enter()
            self.wait()
            self.assertFalse(self.service.hasSource)
            # The manual current alias must migrate to the same stable account.
            self.service.scanSource(str(directory / "current/ContainersRoot/Profile/C_ProfileData"))
            self.wait()
            ident = self.service.selectedAccountId
            self.assertFalse(ident.startswith("manual:"))
            self.assertEqual(str(source), self.service._source)
            self.assertEqual(1, self.service.total)
            newer = make_version(directory, 1234567890, "8")
            (newer / "Profile/C_ProfileData").write_text(json.dumps([car(2, 456)]))
            unlink_junction(directory / "current")
            junction(newer.parent, directory / "current")
            self.service.refresh()
            self.wait()
            self.assertEqual(ident, self.service.selectedAccountId)
            self.assertEqual(456, self.service.cars.get(0)["carId"])
            # Simulate a save rollover while KFPS is not running, before restore.
            newest = make_version(directory, 1234567890, "9")
            (newest / "Profile/C_ProfileData").write_text(json.dumps([car(3, 789)]))
            unlink_junction(directory / "current")
            junction(newest.parent, directory / "current")
            restored = self.make_service()
            restored.enter()
            self.wait(restored)
            self.assertEqual(ident, restored.selectedAccountId)
            self.assertEqual(789, restored.cars.get(0)["carId"])
            self.assertFalse(restored.historyAvailable)

    def test_current_save_change_at_index_commit_does_not_publish(self):
        self.choose_first()
        from kfps_ui.garage_index import profile_identity
        index = self.service.store.path(profile_identity(self.first["source"]))
        before = index.read_bytes()
        Path(self.first["source"]).write_text(json.dumps([car(4, 999)]))
        initial = Path(self.first["source"])
        self.resolve.side_effect = [initial, initial, initial.parent / "changed.json"]
        self.service.refresh()
        self.wait()
        self.assertIn("changed", self.service.status)
        self.assertEqual(before, index.read_bytes())
        self.assertEqual(123, self.service.cars.get(0)["carId"])
        self.assertFalse(list(index.parent.glob(".garage-*")))

    def test_cancel_in_final_validator_preserves_reused_and_new_snapshot(self):
        self.choose_first()
        from kfps_ui.garage_index import profile_identity
        index = self.service.store.path(profile_identity(self.first["source"]))
        before = index.read_bytes()
        initial = Path(self.first["source"])
        original = initial.read_bytes()
        for changed in (False, True):
            with self.subTest(changed=changed):
                initial.write_bytes(json.dumps([car(4, 999)]).encode() if changed else original)
                calls = []
                def cancelling(directory):
                    calls.append(True)
                    if len(calls) == (3 if changed else 2):
                        self.service.cancel()
                    return initial
                self.resolve.side_effect = cancelling
                self.service.refresh()
                self.wait()
                self.assertIn("cancelled", self.service.status)
                self.assertEqual("a", self.service.selectedAccountId)
                self.assertEqual(before, index.read_bytes())
                self.assertEqual(123, self.service.cars.get(0)["carId"])

    def test_named_comparison_and_project_survive_switch_and_restart(self):
        self.choose_first()
        from kfps_ui.garage_notes import inspect_project
        from test_garage_notes import project
        s = self.service
        s.select("1")
        s.saveComparison("Stock build")
        ident = s.savedComparisonId
        target = self.root / "project.json"
        target.write_text(json.dumps(project()))
        before = target.read_bytes()
        s.notes.link(ident, inspect_project(target, 123, UI.parent))
        s._notes = s.notes.load()
        s.selectAccount("b")
        self.wait()
        self.assertEqual("", s.savedComparisonId)
        self.assertEqual(1, len(s.savedComparisons))
        restored = self.make_service()
        restored.enter()
        self.wait(restored)
        self.assertEqual("", restored.savedComparisonId)
        restored.chooseComparison(ident)
        self.assertTrue(restored.projectLinked)
        self.assertEqual("Stock build", restored.compareLabel)
        self.assertEqual(before, target.read_bytes())


if __name__ == "__main__":
    unittest.main()
