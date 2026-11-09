from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]
from PySide6.QtCore import QCoreApplication, QModelIndex
from kfps_ui.app_paths import AppPaths
from kfps_ui.garage_index import GarageError, GarageStore, normalize_garage, profile_identity
from kfps_ui.garage_reader import scan
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from kfps_ui.models import DictListModel
from test_garage_index import car


class GarageReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "garage.json"
        self.source.write_text(json.dumps([car()]))
        self.store = GarageStore(self.root / "index")
        self.cancel = threading.Event()

    def test_scan_reopens_index_reuses_and_never_changes_source(self):
        original = self.source.read_bytes()
        first = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertFalse(first["reused"])
        with patch("kfps_ui.garage_reader.reader_records", side_effect=AssertionError("repeat work")):
            second = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertTrue(second["reused"])
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(first["state"]["cars"], self.store.load(profile_identity(self.source))["cars"])

    def test_unchanged_scan_has_no_writes_and_still_checks_source_twice(self):
        from kfps_ui import garage_reader
        first = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        index = self.store.path(profile_identity(self.source))
        before = index.stat().st_mtime_ns
        with patch.object(self.store, "publish", side_effect=AssertionError("unnecessary write")), \
                patch.object(garage_reader, "snapshot", wraps=garage_reader.snapshot) as snapshot:
            second = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertEqual(2, snapshot.call_count)
        self.assertEqual(first["state"], second["state"])
        self.assertEqual(before, index.stat().st_mtime_ns)

    def test_small_source_read_is_sized_to_file_not_limit(self):
        from kfps_ui.garage_reader import snapshot
        with self.source.open("rb") as stream:
            tracked = MagicMock(wraps=stream)
            tracked.__enter__.return_value = tracked
            with patch.object(Path, "open", return_value=tracked):
                snapshot(self.source, self.cancel)
            tracked.read.assert_called_once_with(self.source.stat().st_size + 1)

    def test_reused_scan_rejects_change_or_cancel_between_reads(self):
        from kfps_ui import garage_reader
        first = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        original = self.source.read_bytes()
        snapshot = garage_reader.snapshot
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                self.source.write_bytes(original)
                self.cancel.clear()
                calls = []
                def changing(path, event):
                    calls.append(True)
                    if len(calls) == 2:
                        if cancel:
                            event.set()
                        else:
                            self.source.write_text(json.dumps([car(5)]))
                    return snapshot(path, event)
                with patch.object(garage_reader, "snapshot", side_effect=changing), \
                        self.assertRaises(InterruptedError if cancel else GarageError):
                    scan(self.source, self.store, self.root / "reader.json", self.cancel)
                self.assertEqual(first["state"], self.store.load(profile_identity(self.source)))

    def test_reused_scan_can_still_clear_history(self):
        self.source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "a" * 64,
                                           "cars": [car()]}))
        scan(self.source, self.store, self.root / "reader.json", self.cancel, history=True)
        self.source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "a" * 64,
                                           "cars": [{**car(), "RearWing": 99}]}))
        changed = scan(self.source, self.store, self.root / "reader.json", self.cancel, history=True)
        self.assertEqual(1, len(changed["state"]["history"]))
        unchanged = scan(self.source, self.store, self.root / "reader.json", self.cancel, history=True)
        self.assertEqual(changed["state"], unchanged["state"])
        cleared = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertTrue(cleared["reused"])
        self.assertEqual([], cleared["state"]["history"])
        self.assertEqual(cleared["state"], self.store.load(profile_identity(self.source)))

    def test_cancel_and_changing_source_preserve_previous_state(self):
        first = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.cancel.set()
        with self.assertRaises(InterruptedError):
            scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.cancel.clear()
        self.source.write_text(json.dumps([car(2)]))
        def changing(*args):
            self.source.write_text(json.dumps([car(3)]))
            return [car(2)]
        with patch("kfps_ui.garage_reader.reader_records", side_effect=changing), self.assertRaises(GarageError):
            scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertEqual(first["state"], self.store.load(profile_identity(self.source)))

    def test_missing_reader_and_invalid_json_leave_no_index(self):
        self.source.write_text("[NaN]")
        with self.assertRaises(GarageError):
            scan(self.source, self.store, self.root / "reader.json", self.cancel)
        other = self.root / "C_ProfileData"
        other.write_bytes(b"sample")
        with patch("kfps_ui.garage_reader._reader_command", side_effect=GarageError("Garage support files need repair")), self.assertRaisesRegex(GarageError, "repair"):
            scan(other, self.store, self.root / "reader.json", self.cancel)
        self.assertFalse(self.store.root.exists())

    def test_duplicate_json_fields_rejected(self):
        self.source.write_text(json.dumps([car()]).replace('"CarId": 123', '"CarId": 999, "CarId": 123'))
        with self.assertRaisesRegex(GarageError, "repeated"):
            scan(self.source, self.store, self.root / "reader.json", self.cancel)

    def test_cancel_at_commit_preserves_prior_index(self):
        first = scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.source.write_text(json.dumps([{**car(), "RearWing": 99}]))
        from kfps_ui import garage_index
        write = garage_index.atomic_json
        def cancelling(path, value, **kwargs):
            self.cancel.set()
            return write(path, value, **kwargs)
        with patch.object(garage_index, "atomic_json", side_effect=cancelling), self.assertRaises(InterruptedError):
            scan(self.source, self.store, self.root / "reader.json", self.cancel)
        self.assertEqual(first["state"], self.store.load(profile_identity(self.source)))
        self.assertEqual([], list(self.store.root.glob('.garage-*')))

    def test_native_reader_uses_crash_safe_handles(self):
        script = self.root / "reader.py"
        script.write_text("import sys\nassert sys.argv[1] == '--stdin'\nassert sys.stdin.buffer.read() == b'sample'\nprint(" + repr(json.dumps([car()])) + ")\n")
        config = self.root / "reader.json"
        config.write_text(json.dumps({"python": sys.executable, "script": str(script)}))
        source = self.root / "C_ProfileData"
        source.write_bytes(b"sample")
        with patch("kfps_ui.garage_reader._reader_command", return_value=[sys.executable, "-I", "-B", str(script), "--stdin"]):
            result = scan(source, self.store, config, self.cancel)
        self.assertEqual(1, len(result["state"]["cars"]))
        self.assertFalse(list(self.root.glob('.garage-read-*')))

    def test_native_reader_cancel_reaps_child_and_cleans_handles(self):
        from kfps_ui import garage_reader
        script = self.root / 'reader.py'
        script.write_text('import sys,time\nsys.stdin.buffer.read()\ntime.sleep(30)\n')
        config = self.root / 'reader.json'
        config.write_text(json.dumps({'python': sys.executable, 'script': str(script)}))
        source = self.root / 'C_ProfileData'
        source.write_bytes(b'sample')
        original = garage_reader.subprocess.Popen
        processes = []
        def child(*args, **kwargs):
            result = original(*args, **kwargs)
            processes.append(result)
            self.cancel.set()
            return result
        with patch("kfps_ui.garage_reader._reader_command", return_value=[sys.executable, "-I", "-B", str(script), "--stdin"]), patch.object(garage_reader.subprocess, 'Popen', side_effect=child), self.assertRaises(InterruptedError):
            scan(source, self.store, config, self.cancel)
        self.assertTrue(processes)
        self.assertIsNotNone(processes[0].poll())
        self.assertFalse(self.store.root.exists())
        self.assertEqual({'reader.py', 'reader.json', 'C_ProfileData', 'garage.json'}, {p.name for p in self.root.iterdir()})

    def test_native_reader_rejects_oversized_output_and_cleans_handles(self):
        script = self.root / 'reader.py'
        script.write_text("import sys\nsys.stdin.buffer.read()\nsys.stdout.buffer.write(b'x' * (17 * 1024 * 1024))\n")
        config = self.root / 'reader.json'
        config.write_text(json.dumps({'python': sys.executable, 'script': str(script)}))
        source = self.root / 'C_ProfileData'
        source.write_bytes(b'sample')
        with patch("kfps_ui.garage_reader._reader_command", return_value=[sys.executable, "-I", "-B", str(script), "--stdin"]), self.assertRaises(GarageError):
            scan(source, self.store, config, self.cancel)
        self.assertFalse(self.store.root.exists())
        self.assertEqual({'reader.py', 'reader.json', 'C_ProfileData', 'garage.json'}, {p.name for p in self.root.iterdir()} )


class GarageServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = AppPaths(self.root, UI, UI / "qml", UI / "assets", self.root / "runtime", Path(sys.executable))
        self.log = LogService()
        self.addCleanup(self.log.close)
        self.sources = DictListModel(["path", "carId", "modelCode", "title", "available"])
        self.liveries = SimpleNamespace(sourceModel=self.sources)
        self.service = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(self.service.close)
        self.source = self.root / "saves" / "Profile" / "garage.json"
        self.source.parent.mkdir(parents=True)
        self.source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "a" * 64,
                                          "cars": [car(1), car(2), car(3, 456)]}))

    def wait_scan(self):
        deadline = time.monotonic() + 8
        while self.service.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertFalse(self.service.busy, self.service.status)

    def test_construct_does_not_read_files_or_launch_work(self):
        with patch.object(Path, "open", side_effect=AssertionError("startup read")):
            service = GarageService(self.paths, self.log, self.liveries)
            self.assertIsNone(service._thread)
            self.assertEqual(0, service.total)
            service.close()

    def test_scan_filter_comparison_history_and_restart(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        self.assertEqual(3, s.total)
        s.setFilter("duplicates")
        self.assertEqual(2, s.cars.rowCount())
        s.select("1")
        s.pinComparison()
        s.select("3")
        self.assertEqual("Car model", s.differences[0]["field"])
        s.setHistoryEnabled(True)
        self.source.write_text(json.dumps({"format": "kfps-garage-snapshot-v1", "profileToken": "a" * 64,
                                          "cars": [{**car(1), "RearWing": 99}, car(2), car(3, 456)]}))
        s.refresh()
        self.wait_scan()
        self.assertEqual(1, len(s.history))
        restored = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(restored.close)
        restored.activate()
        self.assertEqual(3, restored.total)
        self.assertIsNone(restored._thread)
        s.setHistoryEnabled(False)
        self.assertEqual([], s.history)
        s.setSearch("123")
        self.assertEqual(2, s.cars.rowCount())

    def test_livery_handoff_requires_current_exact_reference(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        target = self.root / "saves" / "Livery_0123_test" / "C_livery"
        self.sources.replace([dict(path=str(target), carId=123, title="Art", modelCode="CAR_TEST")])
        s.activate()
        s.select("1")
        received = []
        s.liveryRequested.connect(received.append)
        self.assertTrue(s.details["matched"])
        s.openLivery()
        self.assertEqual([str(target)], received)
        self.sources.replace([])
        s.openLivery()
        self.assertEqual(1, len(received))

    def test_source_model_change_notifies_garage(self):
        changed = []
        self.service.changed.connect(lambda: changed.append(True))
        self.sources.replace([])
        self.assertTrue(changed)

    def test_details_cache_invalidates_for_changed_inserted_and_removed_sources(self):
        from kfps_ui import garage_service
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        target = self.root / "saves/Livery_0123_test/C_livery"
        source = dict(path=str(target), carId=123, title="First", modelCode="CAR_TEST")
        self.sources.replace([source])
        with patch.object(garage_service, "match_livery", wraps=garage_service.match_livery) as matcher:
            for _ in range(10):
                self.assertEqual("First", s.details["livery"])
            self.assertEqual(1, matcher.call_count)
            self.sources.set_row_value(0, "title", "Renamed")
            self.assertEqual("Renamed", s.details["livery"])
            self.sources.append_many([source])
            self.assertFalse(s.details["matched"])
            self.sources.replace([source])
            self.assertTrue(s.details["matched"])
            self.sources.set_row_value(0, "path", str(self.root / "other/Livery_0123_test/C_livery"))
            self.assertFalse(s.details["matched"])

    def test_open_rechecks_match_even_when_details_are_cached(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        self.sources.replace([dict(path=str(self.root / "saves/Livery_0123_test/C_livery"),
                                  carId=123, title="Art", modelCode="CAR_TEST")])
        self.assertTrue(s.details["matched"])
        received = []
        s.liveryRequested.connect(received.append)
        with patch("kfps_ui.garage_service.match_livery", return_value={"status": "unavailable"}) as matcher:
            s.openLivery()
        matcher.assert_called_once()
        self.assertEqual([], received)

    def test_source_removal_layout_and_empty_role_signals_invalidate(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        good = dict(path=str(self.root / "saves/Livery_0123_test/C_livery"), carId=123,
                    title="Art", modelCode="FIRST")
        other = dict(path=str(self.root / "elsewhere/Livery_0123_test/C_livery"), carId=123,
                     title="Elsewhere", modelCode="SECOND")
        self.sources.replace([good])
        self.assertTrue(s.details["matched"])
        self.sources.append_many([other], max_rows=1)
        self.assertFalse(s.details["matched"])
        self.sources.replace([good, other])
        self.assertEqual({"SECOND"}, {r["title"] for r in s.cars.rows if r["carId"] == 123})
        self.sources.layoutAboutToBeChanged.emit()
        self.sources._rows.reverse()
        self.sources.layoutChanged.emit()
        self.assertEqual({"FIRST"}, {r["title"] for r in s.cars.rows if r["carId"] == 123})
        self.assertTrue(s.details["matched"])
        self.sources._rows[1]["title"] = "All roles changed"
        self.sources.dataChanged.emit(self.sources.index(1), self.sources.index(1), [])
        self.assertEqual("All roles changed", s.details["livery"])
        self.sources.replace([good, good])
        self.assertFalse(s.details["matched"])
        self.sources.beginRemoveRows(QModelIndex(), 1, 1)
        del self.sources._rows[1]
        self.sources.endRemoveRows()
        self.assertTrue(s.details["matched"])

    def test_profile_switch_releases_obsolete_rows_and_cached_match(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        old_rows = s._state["cars"]
        self.assertTrue(s.details["parts"])
        self.assertIs(old_rows, s._indexed_rows)
        other = self.root / "other/Profile/garage.json"
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps([{**car(1), "RearWing": 999}]))
        s.scanSource(str(other))
        self.wait_scan()
        self.assertEqual("", s.selectedId)
        self.assertIsNone(s._indexed_rows)
        self.assertEqual({}, s._rows_by_id)
        self.assertIsNot(old_rows, s._ordered_rows_source)
        self.assertIsNone(s._match_cache)
        s.select("1")
        self.assertEqual("999", next(p["value"] for p in s.details["parts"] if p["name"] == "RearWing"))

    def test_closed_service_ignores_source_and_filter_notifications(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        s.details
        self.sources.replace([dict(path="none", carId=123, title="Art", modelCode="CAR_TEST")])
        self.assertTrue(s.close())
        notifications = []
        s.changed.connect(lambda: notifications.append(True))
        self.sources.set_row_value(0, "title", "New")
        self.sources.set_row_value(0, "modelCode", "OTHER")
        self.sources.replace([])
        s.setSearch("x")
        s.setFilter("duplicates")
        s.select("2")
        s.pinComparison()
        s.clearComparison()
        self.assertEqual([], notifications)
        self.assertEqual({}, s._rows_by_id)
        self.assertIsNone(s._indexed_rows)

    def test_storage_creation_failure_is_reported_without_losing_loaded_rows(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select('1')
        rows = s._state['cars']
        with patch.object(Path, 'mkdir', side_effect=PermissionError('PRIVATE_LOCATION')):
            s.refresh()
        self.assertFalse(s.busy)
        self.assertIs(rows, s._state['cars'])
        self.assertEqual('1', s.selectedId)
        self.assertIn('storage', s.status.lower())
        self.assertNotIn('PRIVATE_LOCATION', s.status)
        s.refresh()
        self.wait_scan()
        self.assertEqual(3, s.total)

    def test_scan_worker_start_failure_recovers_and_can_retry(self):
        s = self.service
        with patch('kfps_ui.garage_service.threading.Thread.start', side_effect=RuntimeError('PRIVATE_FAILURE')):
            s.scanSource(str(self.source))
        self.assertFalse(s.busy)
        self.assertIsNone(s._thread)
        self.assertNotIn('PRIVATE_FAILURE', s.status)
        s.scanSource(str(self.source))
        self.wait_scan()
        self.assertEqual(3, s.total)

    def test_project_worker_start_failure_does_not_lose_comparison(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select('1')
        s.saveComparison('Saved comparison')
        ident = s.savedComparisonId
        with patch('kfps_ui.garage_service.threading.Thread.start', side_effect=RuntimeError('PRIVATE_FAILURE')):
            s.linkProject(str(self.root / 'project.json'))
        self.assertFalse(s.busy)
        self.assertIsNone(s._thread)
        self.assertEqual(ident, s.savedComparisonId)
        self.assertFalse(s.projectLinked)
        self.assertIn('start', s.projectStatus.lower())
        self.assertNotIn('PRIVATE_FAILURE', s.projectStatus)

    def test_repeat_refresh_and_tab_return_do_not_reset_model_or_write_settings(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        resets = []
        s.cars.modelReset.connect(lambda: resets.append(True))
        s.select("2")
        with patch("kfps_ui.garage_service.atomic_json", side_effect=AssertionError("settings rewrite")):
            s.activate()
            s.setSearch("")
            s.setFilter("all")
            s.refresh()
            self.wait_scan()
        self.assertEqual([], resets)
        self.assertEqual("2", s.selectedId)
        self.assertEqual(3, s.visibleCount)

    def test_catalogue_is_read_only_after_change_and_search_updates(self):
        from kfps_ui import garage_service
        index = self.root / "vehicles.json"
        def write_name(name):
            index.write_text(json.dumps({"format": "kfps_fh6_vehicle_asset_index_v1",
                                         "vehicles": {"123": {"model_code": name}}}))
        write_name("ORIGINAL")
        self.liveries._experiment_paths = SimpleNamespace(vehicle_index=index)
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        with patch.object(garage_service, "read_json", wraps=garage_service.read_json) as reader:
            s.activate()
            reader.assert_not_called()
            write_name("REVISED_MODEL")
            s.activate()
            reader.assert_called_once_with(index)
        s.setSearch("REVISED")
        self.assertEqual(2, s.visibleCount)

    def test_source_notifications_before_first_visit_do_not_copy_library(self):
        with patch.object(self.service, "_sources", side_effect=AssertionError("idle library read")):
            self.sources.replace([dict(path="none", carId=123, title="Art", modelCode="CAR_TEST")])
        self.assertIsNone(self.service._thread)
        self.assertEqual(0, self.service.cars.rowCount())

    def test_thumbnail_notifications_do_not_do_garage_work(self):
        sources = DictListModel(["path", "carId", "modelCode", "title", "thumbnailUrl"])
        s = GarageService(self.paths, self.log, SimpleNamespace(sourceModel=sources))
        self.addCleanup(s.close)
        s.scanSource(str(self.source))
        deadline = time.monotonic() + 8
        while s.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertFalse(s.busy)
        sources.replace([dict(path="none", carId=123, title="Art", modelCode="CAR_TEST")])
        notifications = []
        s.changed.connect(lambda: notifications.append(True))
        with patch.object(s, "_sources", side_effect=AssertionError("thumbnail caused a library copy")):
            sources.set_row_value(0, "thumbnailUrl", "file:///new.png")
        self.assertEqual([], notifications)

    def test_completed_scan_is_accepted_after_late_cancel(self):
        result = scan(self.source, self.service.store, self.root / 'reader.json', threading.Event())
        self.service.cancel()
        self.service._apply(result)
        self.assertEqual(3, self.service.total)
        self.assertNotIn('cancelled', self.service.status)

    def test_unscoped_refresh_does_not_inherit_comparison_or_history(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select("1")
        s.pinComparison()
        s.setHistoryEnabled(True)
        self.source.write_text(json.dumps([car(1)]))
        s.refresh()
        self.wait_scan()
        self.assertEqual("", s.compareLabel)
        self.assertFalse(s.historyAvailable)
        self.assertEqual([], s.history)

    def test_saved_comparison_and_project_link_restart_and_changed_file(self):
        from test_garage_notes import project
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.select('1')
        s.saveComparison('Before wing change')
        ident = s.savedComparisonId
        self.assertTrue(ident)
        target = self.root / 'layout.json'
        target.write_text(json.dumps(project()))
        with patch('kfps_ui.garage_service.inspect_project', wraps=lambda path, car, root, **kw: __import__('kfps_ui.garage_notes', fromlist=['inspect_project']).inspect_project(path, car, UI.parent, **kw)):
            s.linkProject(str(target))
            self.wait_scan()
        self.assertTrue(s.projectLinked)
        self.assertIn('linked', s.projectStatus.lower())
        restored = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(restored.close)
        restored.activate()
        self.assertEqual('', restored.savedComparisonId)
        restored.chooseComparison(ident)
        self.assertTrue(restored.projectLinked)
        target.write_text(json.dumps({**project(), 'vehicle_parts': {'RearWing': 77}}))
        with patch('kfps_ui.garage_service.resolve_project', wraps=lambda info, root, **kw: __import__('kfps_ui.garage_notes', fromlist=['resolve_project']).resolve_project(info, UI.parent, **kw)):
            restored.checkProject()
            deadline = time.monotonic() + 8
            while restored.busy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
        self.assertFalse(restored.busy)
        self.assertIn('changed', restored.projectStatus.lower())
        before = target.read_bytes()
        restored.removeComparison()
        self.assertEqual([], restored.savedComparisons)
        self.assertEqual(before, target.read_bytes())

    def test_failed_scan_keeps_display_and_redacts_log(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.scanSource(str(self.root / "sensitive-account-name"))
        self.wait_scan()
        self.assertEqual(3, s.total)
        text = "\n".join(self.log._diagnostic_lines)
        self.assertNotIn("sensitive-account-name", text)
        self.assertNotIn(str(self.source), text)


if __name__ == "__main__":
    unittest.main()
