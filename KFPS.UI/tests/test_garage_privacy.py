import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'KFPS.UI/src'), str(ROOT)]
from kfps_ui.support_report import build_support_report
from kfps_ui.support_log_bundle import collect_retained_log_bundle


class GaragePrivacyTests(unittest.TestCase):
    def test_account_diagnostics_include_counts_not_identifiers(self):
        from kfps_ui.garage_index import clean_diagnostics
        result = clean_diagnostics({"accountsDiscovered": True, "accountSelected": True,
                                       "accountCount": 2, "accounts": ["PRIVATE"],
                                       "selectedAccountId": "PRIVATE", "accountStatus": "PRIVATE"})
        self.assertEqual({"accountsDiscovered": True, "accountSelected": True, "accountCount": 2}, result)

    def test_catalogue_diagnostics_exclude_images_names_and_preferences(self):
        from kfps_ui.garage_index import clean_diagnostics
        self.assertEqual({"catalogueBusy": False, "catalogueCount": 682, "stockThumbnailCount": 680},
            clean_diagnostics({"catalogueBusy": False, "catalogueCount": 682, "stockThumbnailCount": 680,
                               "thumbnailUrl": "PRIVATE", "gamertag": "PRIVATE", "sort": "owned"}))
        self.assertEqual({}, clean_diagnostics({"catalogueCount": 4097, "stockThumbnailCount": -1}))

    def test_report_and_attachment_exclude_garage_files_and_private_fields(self):
        marker = 'PRIVATE-GARAGE-RECORD-SHOULD-NOT-APPEAR'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            garage = root / 'runtime/garage'
            garage.mkdir(parents=True)
            for name in ('reader.json', 'settings.json', 'comparisons.json', 'private.log'):
                (garage / name).write_text(marker)
            report = build_support_report(root, {'garage': {'loaded': True, 'carCount': 344,
                'source': marker, 'cars': [marker], 'projectPath': marker}, 'page': 'liveries'},
                since=0, collect=lambda: {})
            self.assertEqual({'loaded': True, 'carCount': 344}, report['technical']['garage'])
            attachment = collect_retained_log_bundle(root, snapshot=report['technical'])
            self.assertIsNotNone(attachment)
            self.assertNotIn(marker, gzip.decompress(attachment[1]).decode())
            self.assertNotIn(marker, json.dumps(report))

    def test_discovery_cannot_make_garage_data_into_a_log(self):
        from kfps_ui.support_logs import collect_worker_logs, read_known_file
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private = root / 'runtime/garage/comparisons.json'
            private.parent.mkdir(parents=True)
            private.write_text('PRIVATE-COMPARISON-NAME')
            with self.assertRaises(ValueError): read_known_file(root, private, 4096)
            found = ([('app-runtime', private)], [])
            with patch('kfps_ui.support_logs.discover_worker_logs', return_value=found):
                self.assertEqual([], collect_worker_logs(root, since=0, now=0, redact=str)[0])
            with patch('kfps_ui.support_log_bundle.discover_worker_logs', return_value=found):
                attachment = collect_retained_log_bundle(root)
            self.assertNotIn('PRIVATE-COMPARISON-NAME', gzip.decompress(attachment[1]).decode())


if __name__ == '__main__': unittest.main()
