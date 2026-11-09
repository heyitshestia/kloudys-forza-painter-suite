from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kfps_ui.garage_index import (GarageError, GarageStore, compare_builds,
                                available_livery_models, clean_diagnostics, match_livery, normalize_garage, profile_identity)


def car(ident=1, model=123, **extra):
    return dict(Id=ident, CarId=model, CarBody=2, RearWing=3, FrontBumper=4,
                RearBumper=5, Hood=6, SideSkirts=7, WheelStyle=-1,
                LiveryFileName="Livery_0123_test", TuneFileName="", **extra)


class GarageIndexTests(unittest.TestCase):
    def test_diagnostics_are_only_bounded_counts_and_booleans(self):
        value = {"loaded": True, "busy": False, "carCount": 344, "comparisonCount": 2,
                 "historyAvailable": False, "lastScanReused": True, "lastScanMs": 300,
                 "source": "private", "cars": [car()], "scope": "private", "projectPath": "private"}
        clean = clean_diagnostics(value)
        self.assertEqual(7, len(clean))
        self.assertEqual(344, clean['carCount'])
        self.assertEqual({}, clean_diagnostics({'carCount': True, 'lastScanMs': -1, 'busy': 'yes'}))

    def test_duplicate_models_keep_separate_owned_identity(self):
        rows = normalize_garage([car(1), car(2)])
        self.assertEqual(["1", "2"], [r["instanceId"] for r in rows])
        self.assertEqual(rows[0]["buildSignature"], rows[1]["buildSignature"])
        self.assertEqual(-1, rows[0]["parts"]["WheelStyle"])

    def test_reject_bad_contract(self):
        cases = [None, {}, [car(), car()], [{**car(), "CarId": True}],
                 [{**car(), "CarBody": "2"}], [{**car(), "LiveryFileName": "../x"}],
                 [{**car(), "Id": -1}], [{**car(), "Hood": None}]]
        for data in cases:
            with self.subTest(data=type(data).__name__), self.assertRaises(GarageError):
                normalize_garage(data)

    def test_optional_unknown_fields_do_not_leak(self):
        row = normalize_garage([{**car(), "AccountName": "private", "TireBrand": None}])[0]
        self.assertNotIn("AccountName", row)
        self.assertIsNone(row["parts"]["TireBrand"])
        self.assertEqual([], normalize_garage([]))

    def test_comparison_preserves_unknowns_and_identifies_model(self):
        before, after = normalize_garage([car(1), {**car(2), "RearWing": 42}])
        self.assertEqual([{"field": "RearWing", "before": "3", "after": "42"}],
                         compare_builds(before, after))
        after["carId"] = 999
        self.assertEqual("Car model", compare_builds(before, after)[0]["field"])

    def test_exact_livery_match_requires_model_and_profile_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "one" / "Profile" / "C_ProfileData"
            good = dict(path=str(root / "one" / "Livery_0123_test" / "C_livery"), carId=123)
            wrong = dict(path=str(root / "two" / "Livery_0123_test" / "C_livery"), carId=123)
            row = normalize_garage([car()])[0]
            self.assertEqual(good["path"], match_livery(row, [wrong, good], profile)["path"])
            self.assertEqual("unavailable", match_livery(row, [wrong], profile)["status"])
            self.assertEqual("ambiguous", match_livery(row, [good, good], profile)["status"])
            self.assertEqual("unavailable", match_livery(row, [{**good, "carId": 4}], profile)["status"])

    def test_available_livery_skips_repeated_models_after_first_same_account_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / 'one/Profile/garage.json'
            good = dict(path=str(root / 'one/Livery_saved/C_livery'), carId=123, available=True)
            original = Path.resolve
            with patch.object(Path, 'resolve', autospec=True, side_effect=original) as resolve:
                self.assertEqual({123}, available_livery_models([good] * 5000, [], profile))
                self.assertEqual(2, resolve.call_count)
            wrong = {**good, 'path': str(root / 'two/Livery_saved/C_livery')}
            self.assertEqual({123}, available_livery_models([wrong, good], [], profile))
            self.assertEqual(set(), available_livery_models([wrong], [], profile))
            self.assertEqual({123}, available_livery_models([wrong], [], ''))

    def test_available_livery_ignores_invalid_or_missing_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = dict(path=str(Path(tmp) / 'package.kfpslivery'), carId=123, available=True)
            for field, value in [('carId', True), ('carId', 0), ('carId', '123'),
                                 ('carId', 2**31), ('path', ''), ('path', 'relative'),
                                 ('path', 'invalid\0'), ('available', False), ('available', 'yes')]:
                with self.subTest(field=field, value=value):
                    self.assertEqual(set(), available_livery_models([], [{**good, field: value}], ''))
            self.assertEqual({123}, available_livery_models([], [good], ''))

    def test_store_history_is_opt_in_bounded_and_profile_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GarageStore(Path(tmp))
            a, b = profile_identity(Path(tmp) / "a"), profile_identity(Path(tmp) / "b")
            rows = normalize_garage([car()])
            first = store.publish(a, "a" * 64, rows, history=False)
            self.assertEqual([], first["history"])
            for n in range(25):
                changed = normalize_garage([{**car(), "RearWing": 10 + n}])
                state = store.publish(a, f"{n:064x}", changed, history=True, scope="c" * 64)
            self.assertLessEqual(len(state["history"]), 20)
            self.assertEqual("RearWing", state["history"][-1]["changes"][0]["fields"][0])
            self.assertIsNone(store.load(b))
            state = store.publish(a, "e" * 64, rows, history=False)
            self.assertEqual([], state["history"])
            self.assertEqual(rows, store.load(a)["cars"])

    def test_unscoped_or_replaced_profile_has_no_inherited_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GarageStore(Path(tmp))
            rows = normalize_garage([car()])
            changed = normalize_garage([{**car(), "RearWing": 99}])
            store.publish("a" * 64, "b" * 64, rows, history=True)
            state = store.publish("a" * 64, "c" * 64, changed, history=True)
            self.assertEqual([], state["history"])
            store.publish("a" * 64, "d" * 64, rows, history=True, scope="e" * 64)
            state = store.publish("a" * 64, "f" * 64, changed, history=True, scope="f" * 64)
            self.assertEqual([], state["history"])

    def test_corrupt_cache_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = GarageStore(Path(tmp))
            ident = "a" * 64
            store.publish(ident, "b" * 64, normalize_garage([car()]), history=False)
            (Path(tmp) / (ident + ".json")).write_text("{}")
            self.assertIsNone(store.load(ident))
            with self.assertRaises(GarageError):
                store.load("../outside")


if __name__ == "__main__":
    unittest.main()
