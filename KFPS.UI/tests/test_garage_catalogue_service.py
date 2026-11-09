from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

import test_garage_service as fixtures
from kfps_ui.garage_service import GarageService


CATALOGUE = [
    {"carId": 123, "title": "Zeta Coupe", "modelCode": "ZET_Coupe", "thumbnailUrl": ""},
    {"carId": 456, "title": "Beta Saloon", "modelCode": "BET_Saloon", "thumbnailUrl": ""},
    {"carId": 789, "title": "Alpha Roadster", "modelCode": "ALP_Roadster", "thumbnailUrl": ""},
]


class GarageCatalogueServiceTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.GarageServiceTests.setUpClass.__func__)
    setUp = fixtures.GarageServiceTests.setUp
    wait_scan = fixtures.GarageServiceTests.wait_scan

    def catalogue(self):
        self.service._apply_catalogue({"game": "", "cars": CATALOGUE, "status": "Stock thumbnails unavailable"})

    def wait_catalogue(self):
        deadline = time.monotonic() + 5
        while self.service.catalogueBusy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertFalse(self.service.catalogueBusy)

    def test_manufacturer_order_ignores_year_prefix_and_keeps_priority_sorts(self):
        s = self.service
        s.activate()
        rows = [
            {**CATALOGUE[0], 'title': '1969 Toyota 2000GT', 'manufacturer': 'Toyota', 'modelName': '2000GT', 'year': 1969},
            {**CATALOGUE[1], 'title': '2016 Honda S660 Alpha', 'manufacturer': 'Honda', 'modelName': 'S660 Alpha', 'year': 2016},
            {**CATALOGUE[2], 'title': '1995 Nissan NISMO GT-R LM', 'manufacturer': 'Nissan', 'modelName': 'NISMO GT-R LM', 'year': 1995},
        ]
        s._apply_catalogue({'game': '', 'cars': rows, 'status': 'ready'})
        self.assertEqual([456, 789, 123], [r['carId'] for r in s.cars.rows])
        s.setSort('owned')
        self.assertEqual([456, 789, 123], [r['carId'] for r in s.cars.rows])

    def test_entry_checks_changes_without_reloading_unchanged_or_idle_polling(self):
        s = self.service
        self.liveries.gameFolder = 'fixture-game'
        with patch('kfps_ui.garage_service.catalogue_signature', return_value='first') as stamp, \
                patch('kfps_ui.garage_service.load_catalogue', return_value={'cars': CATALOGUE, 'status': 'ready'}) as load, \
                patch('kfps_ui.garage_service.discover_accounts', return_value=[]):
            s.enter()
            self.wait_scan()
            self.wait_catalogue()
            s.enter()
            self.wait_catalogue()
            load.assert_called_once()
            stamp.return_value = 'updated'
            s.enter()
            self.wait_catalogue()
            self.assertEqual(2, load.call_count)
            calls = stamp.call_count
            for _ in range(5):
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(calls, stamp.call_count)
            s.refresh()
            self.wait_catalogue()
            self.assertEqual(3, load.call_count)

    def test_changed_during_load_and_empty_failure_keep_last_good_catalogue(self):
        s = self.service
        s.activate()
        self.catalogue()
        self.liveries.gameFolder = 'fixture-game'
        with patch('kfps_ui.garage_service.catalogue_signature', side_effect=['before', 'after']), \
                patch('kfps_ui.garage_service.load_catalogue', return_value={'cars': CATALOGUE[:1], 'status': 'ready'}):
            s._load_catalogue()
            self.wait_catalogue()
        self.assertEqual(3, s.browseTotal)
        self.assertIn('changed', s.catalogueStatus)
        s._apply_catalogue({'game': 'fixture-game', 'cars': [], 'status': 'unavailable'})
        self.assertEqual(3, s.browseTotal)

    def test_catalogue_without_account_does_not_claim_ownership(self):
        s = self.service
        s.activate()
        self.catalogue()
        self.assertEqual(3, s.browseTotal)
        self.assertEqual(0, s.total)
        self.assertFalse(s.ownershipKnown)
        self.assertEqual("Alpha Roadster", s.cars.rows[0]["title"])
        self.assertTrue(all(not row["owned"] for row in s.cars.rows))
        s.select("catalogue:789")
        self.assertFalse(s.details["owned"])
        self.assertEqual("Ownership unknown", s.details["ownership"])
        self.assertIsNone(s._row())

    def test_merge_retains_owned_copies_and_no_fake_stock_build(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        self.catalogue()
        self.assertEqual(4, s.browseTotal)
        self.assertEqual({"1", "2", "3", "catalogue:789"}, {r["instanceId"] for r in s.cars.rows})
        s.select("catalogue:789")
        with patch.object(s, "_start_worker") as worker:
            s.openPreview()
            s.openStudio()
            s.pinComparison()
            self.assertIsNone(s._compare)
            worker.assert_not_called()
        self.assertEqual("Not owned", s.details["ownership"])
        s.select("2")
        self.assertTrue(s.details["owned"])
        self.assertEqual("2", s._row()["instanceId"])

    def test_filters_and_sort_remembered_without_account(self):
        s = self.service
        s.activate()
        self.catalogue()
        s.setSort("owned")
        s.setFilter("owned")
        self.assertEqual(0, s.visibleCount)
        saved = json.loads((s.root / "settings.json").read_text())
        self.assertEqual("owned", saved["sort"])
        restored = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(restored.close)
        restored.activate()
        self.assertEqual(s.sortIndex, restored.sortIndex)
        self.assertEqual(s.filterIndex, restored.filterIndex)

    def test_owned_and_livery_priority_and_filter(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        for row in s._state["cars"]:
            row["liveryRef"] = ""
        s._state["cars"][0]["liveryRef"] = "missing-applied-livery"
        self.sources.replace([{'carId': 456, 'path': str(self.source.parent.parent / 'Livery_spare/C_livery'),
                               'available': True, 'title': 'Spare design', 'modelCode': 'BET_Saloon'}])
        self.catalogue()
        s.setSort("owned")
        self.assertEqual("catalogue:789", s.cars.rows[-1]["instanceId"])
        s.setSort("livery")
        self.assertEqual("3", s.cars.rows[0]["instanceId"])
        s.setFilter("owned")
        self.assertEqual(3, s.visibleCount)
        s.setFilter("livery")
        self.assertEqual(["3"], [r["instanceId"] for r in s.cars.rows])
        s.setFilter("duplicates")
        self.assertEqual(2, s.visibleCount)
        s.setFilter("all")
        s.setSort("name")
        self.assertEqual("Alpha Roadster", s.cars.rows[0]["title"])

    def test_saved_liveries_match_model_even_when_not_applied_or_car_not_owned(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        self.catalogue()
        same_root = self.source.parent.parent
        self.sources.replace([
            {'carId': 123, 'path': str(same_root / 'Livery_spare/C_livery'), 'available': True},
            {'carId': 789, 'path': str(same_root / 'Livery_not_owned/C_livery'), 'available': True},
            {'carId': 456, 'path': str(self.root / 'other/Livery_foreign/C_livery'), 'available': True},
        ])
        s.setFilter('livery')
        self.assertEqual({'1', '2', 'catalogue:789'}, {r['instanceId'] for r in s.cars.rows})
        self.assertTrue(all(r['hasLivery'] for r in s.cars.rows))
        s.select('1')
        self.assertFalse(s.details['matched'])
        self.assertEqual(3, s.summary['liveries'])
        self.sources.set_row_value(0, 'path', str(self.root / 'other/Livery_spare/C_livery'))
        self.assertEqual(['catalogue:789'], [r['instanceId'] for r in s.cars.rows])
        self.sources.replace([])
        self.assertEqual(0, s.visibleCount)

    def test_unavailable_and_other_account_liveries_do_not_match(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        self.catalogue()
        self.sources.replace([{'carId': 123, 'path': str(self.source.parent.parent / 'Livery_missing/C_livery'),
                               'available': False}])
        s.setFilter('livery')
        self.assertEqual(0, s.visibleCount)
        self.sources.replace([{'carId': 456, 'path': str(self.root / 'other/Livery_other/C_livery'),
                               'available': True}])
        self.assertEqual(0, s.visibleCount)
        other = self.root / 'other/Profile/garage.json'
        other.parent.mkdir(parents=True)
        other.write_text(self.source.read_text())
        s.scanSource(str(other))
        self.wait_scan()
        self.assertEqual(['3'], [r['instanceId'] for r in s.cars.rows])

    def test_local_packages_count_and_model_changes_refresh_filter(self):
        from kfps_ui.models import DictListModel
        self.liveries.packageModel = DictListModel(['path', 'carId', 'available'])
        s = GarageService(self.paths, self.log, self.liveries)
        self.addCleanup(s.close)
        s.activate()
        s._apply_catalogue({'game': '', 'cars': CATALOGUE, 'status': 'ready'})
        self.liveries.packageModel.replace([{'path': str(self.root / 'design.kfpslivery'),
                                            'carId': 789, 'available': True}])
        s.setFilter('livery')
        self.assertEqual(['catalogue:789'], [r['instanceId'] for r in s.cars.rows])
        self.liveries.packageModel.set_row_value(0, 'available', False)
        self.assertEqual(0, s.visibleCount)

    def test_source_availability_changes_rebuild_without_applied_reference(self):
        s = self.service
        s.activate()
        self.catalogue()
        self.sources.replace([{'carId': 789, 'path': str(self.root / 'Livery_spare/C_livery'),
                               'available': False}])
        s.setFilter('livery')
        self.assertEqual(0, s.visibleCount)
        self.sources.set_row_value(0, 'available', True)
        self.assertEqual(['catalogue:789'], [r['instanceId'] for r in s.cars.rows])
        self.sources.set_row_value(0, 'available', False)
        self.assertEqual(0, s.visibleCount)

    def test_refresh_uses_existing_library_scan_and_respects_lifecycle(self):
        s = self.service
        self.liveries.scanSaves = Mock()
        s.refresh()
        self.liveries.scanSaves.assert_called_once_with()
        self.liveries.scanSaves.reset_mock()
        s._source = str(self.source)
        with patch.object(s, '_scan_source') as scan:
            s.refresh()
            scan.assert_called_once_with(str(self.source), account=None)
        self.liveries.scanSaves.assert_called_once_with()
        self.liveries.scanSaves.reset_mock()
        with patch.object(s, '_busy', True):
            s.refresh()
        s.close()
        s.refresh()
        self.liveries.scanSaves.assert_not_called()

    def test_bad_preferences_and_write_failure_are_safe(self):
        s = self.service
        s.root.mkdir(parents=True)
        (s.root / "settings.json").write_text(json.dumps({"source": "", "sort": ["bad"], "filter": {"bad": 1}}))
        s.activate()
        self.assertEqual(0, s.sortIndex)
        self.assertEqual(0, s.filterIndex)
        s.setSort("nonsense")
        with patch("kfps_ui.garage_service.atomic_json", side_effect=OSError):
            s.setSort("owned")
        self.assertEqual(1, s.sortIndex)
        self.assertIn("could not be remembered", s.status)

    def test_view_save_preserves_history_source_and_account(self):
        s = self.service
        s.scanSource(str(self.source))
        self.wait_scan()
        s.setHistoryEnabled(True)
        s._settings['account'] = {'id': 'a' * 64, 'label': 'Fixture account', 'directory': str(self.root)}
        s.setSort('livery')
        s.setFilter('owned')
        saved = json.loads((s.root / 'settings.json').read_text())
        self.assertTrue(saved['history'])
        self.assertEqual(str(self.source), saved['source'])
        self.assertEqual('a' * 64, saved['account']['id'])
        self.assertEqual('livery', saved['sort'])

    def test_catalogue_error_preserves_previous_rows_and_is_retryable(self):
        s = self.service
        s.activate()
        self.catalogue()
        s._apply_catalogue({'game': '', 'error': True, 'status': 'Unavailable; rescan to retry'})
        self.assertEqual(3, s.browseTotal)
        self.assertFalse(s.catalogueBusy)
        self.assertIn('retry', s.catalogueStatus)
        self.liveries.gameFolder = 'fixture-game'
        with patch('kfps_ui.garage_service.load_catalogue', return_value={'cars': CATALOGUE, 'status': 'ready'}), \
                patch('kfps_ui.garage_service.discover_accounts', return_value=[]):
            s.rescanAccounts()
            self.wait_scan()
            deadline = time.monotonic() + 3
            while s.catalogueBusy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
        self.assertEqual('ready', s.catalogueStatus)

    def test_catalogue_start_failure_has_no_stuck_busy_flag(self):
        s = self.service
        self.liveries.gameFolder = 'fixture-game'
        with patch('kfps_ui.garage_service.threading.Thread.start', side_effect=RuntimeError):
            s._load_catalogue()
        self.assertFalse(s.catalogueBusy)
        self.assertIsNone(s._catalogue_game)
        self.assertIn('could not start', s.catalogueStatus)

    def test_transient_settings_read_failure_does_not_erase_account(self):
        s = self.service
        s.root.mkdir(parents=True)
        previous = {'source': str(self.source), 'history': True,
                    'account': {'id': 'a' * 64, 'label': 'Fixture', 'directory': str(self.root)}}
        settings = s.root / 'settings.json'
        settings.write_text(json.dumps(previous))
        with patch('kfps_ui.garage_service.read_json', side_effect=PermissionError):
            s.activate()
            s.setSort('owned')
        self.assertEqual(previous, json.loads(settings.read_text()))
        self.assertIn('could not be remembered', s.status)
        s.setSort('livery')
        self.assertEqual({**previous, 'sort': 'livery'}, json.loads(settings.read_text()))

    def test_cancel_after_game_change_never_starts_replacement_job(self):
        s = self.service
        self.liveries.gameFolder = 'new-game'
        s.cancel()
        with patch.object(s, '_load_catalogue') as start:
            s._apply_catalogue({'game': 'old-game', 'cars': CATALOGUE, 'status': 'ready'})
        start.assert_not_called()
        self.assertFalse(s.catalogueBusy)
        self.assertEqual('Car catalogue cancelled', s.catalogueStatus)

    def test_stale_or_cancelled_catalogue_keeps_previous_list(self):
        s = self.service
        s.activate()
        self.catalogue()
        s._apply_catalogue({"game": "old-game", "cars": [], "status": ""})
        self.assertEqual(3, s.browseTotal)
        s._catalogue_cancel.set()
        s._apply_catalogue({"game": "", "cars": [], "status": "cancelled"})
        self.assertEqual(3, s.browseTotal)
        s.close()
        self.catalogue()
        self.assertEqual(0, s.browseTotal)

    def test_catalogue_load_background_once_and_no_idle_work(self):
        s = self.service
        self.liveries.gameFolder = "fixture-game"
        release = threading.Event()
        self.addCleanup(release.set)
        def load(*args):
            release.wait(2)
            return {"cars": CATALOGUE, "status": "ready"}
        with patch("kfps_ui.garage_service.load_catalogue", side_effect=load) as loader, \
                patch('kfps_ui.garage_service.catalogue_signature', return_value='fixture'), \
                patch("kfps_ui.garage_service.discover_accounts", return_value=[]):
            s.enter()
            self.wait_scan()
            self.assertTrue(s.catalogueBusy)
            release.set()
            deadline = time.monotonic() + 3
            while s.catalogueBusy and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.005)
            self.assertFalse(s.catalogueBusy)
            self.assertEqual(3, s.browseTotal)
            s.enter()
            s.enter()
            self.wait_catalogue()
            loader.assert_called_once()


if __name__ == "__main__":
    unittest.main()
