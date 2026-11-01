from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QCoreApplication, QSortFilterProxyModel
from PySide6.QtTest import QSignalSpy

from kfps_ui.livery_library import LiveryLibraryFilter, source_details
from kfps_ui.models import DictListModel


ROLES = (
    "title", "path", "carId", "modelCode", "placementCount", "modified",
    "exportable", "searchText",
)
SORTS = ("modified", "title", "car", "placements")


def livery(path, **changes):
    return {
        "title": "Blue [Track]", "path": path, "carId": 1296,
        "modelCode": "TEST_CAR", "placementCount": 52,
        "modified": "2026-09-09 12:30", "exportable": True,
        "searchText": "", **changes,
    }


class LiveryLibraryFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.source = DictListModel(ROLES)
        self.proxy = LiveryLibraryFilter()
        self.proxy.setSourceModel(self.source)
        self.addCleanup(self.proxy.setSourceModel, None)

    def paths(self):
        return [self.source.row(self.proxy.mapToSource(self.proxy.index(i, 0)).row())["path"]
                for i in range(self.proxy.rowCount())]

    def test_defaults_and_configuration_before_source_attachment(self):
        proxy = LiveryLibraryFilter()
        self.assertIsInstance(proxy, QSortFilterProxyModel)
        self.assertEqual((proxy.search, proxy.car_id, proxy.availability, proxy.sort_order),
                         ("", 0, "all", "modified"))
        self.assertEqual(proxy.rowCount(), 0)
        proxy.setSearch("blue")
        proxy.setCarId(1296)
        proxy.setAvailability("exportable")
        proxy.setSortOrder("placements")
        self.source.replace([livery("a"), livery("b", carId=11296)])
        proxy.setSourceModel(self.source)
        self.assertEqual(proxy.rowCount(), 1)
        proxy.setSourceModel(None)
        self.assertEqual(proxy.rowCount(), 0)
        self.assertEqual(proxy.search, "blue")

    def test_broad_filter_changes_do_not_resort_unchanged_results(self):
        self.source.replace([livery(str(i), title=f"Livery {i}") for i in range(500)])
        self.assertEqual(500, self.proxy.rowCount())
        comparisons = []
        compare = LiveryLibraryFilter.lessThan

        def measured(proxy, left, right):
            comparisons.append(1)
            return compare(proxy, left, right)

        with patch.object(LiveryLibraryFilter, "lessThan", measured):
            for query in ("l", "li", "liv", "livery"):
                self.proxy.setSearch(query)
                self.assertEqual(500, self.proxy.rowCount())
            self.proxy.setCarId(1296)
            self.proxy.setAvailability("exportable")
            self.assertEqual(500, self.proxy.rowCount())
        self.assertEqual([], comparisons, "Filtering must not repeat an unchanged full sort")

    def test_search_is_literal_including_regex_metacharacters_and_spaces(self):
        for token in (".*", "[", "]", "[Track]", "(a|b)", "a+b?", "^$", "{2}",
                      "\\d", "two  spaces", " leading "):
            with self.subTest(token=token):
                self.source.replace([
                    livery("hit", title="PREFIX " + token + " SUFFIX"),
                    livery("miss", title="prefix ordinary text suffix"),
                ])
                self.proxy.setSearch(token.swapcase())
                self.assertEqual(self.paths(), ["hit"])
        self.proxy.setSearch("")
        self.assertEqual(self.proxy.rowCount(), 2)

    def test_unicode_casefold_search_and_title_sort(self):
        self.source.replace([
            livery("street", title="Stra\u00dfe"),
            livery("greek", title="\u03a3\u039f\u03a3"),
            livery("japanese", title="\u6771\u4eac \u30ec\u30fc\u30b9"),
            livery("accent", title="\u00c9T\u00c9"),
        ])
        for query, expected in (("STRASSE", "street"), ("\u03c3\u03bf\u03c2", "greek"),
                                ("\u6771\u4eac", "japanese"), ("\u00e9t\u00e9", "accent")):
            with self.subTest(query=query):
                self.proxy.setSearch(query)
                self.assertEqual(self.paths(), [expected])
        self.proxy.setSearch("")
        self.proxy.setSortOrder("title")
        self.assertEqual(self.paths(), ["street", "accent", "greek", "japanese"])

    def test_search_uses_indexed_text_and_visible_fields(self):
        self.source.replace([livery("C:/saved/livery", searchText="custom tag")])
        for query in ("custom TAG", "blue", "[track]", "test_car", "1296", "C:/SAVED"):
            with self.subTest(query=query):
                self.proxy.setSearch(query)
                self.assertEqual(self.proxy.rowCount(), 1)
        self.proxy.setSearch("absent")
        self.assertEqual(self.proxy.rowCount(), 0)

    def test_filters_intersect_and_car_id_is_exact(self):
        self.source.replace([
            livery("owned"), livery("preview", exportable=False),
            livery("other-car", carId=11296), livery("other-title", title="Red"),
            livery("text-id", carId="1296"),
        ])
        self.proxy.setSearch("blue")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("exportable")
        self.assertEqual(self.paths(), ["owned", "text-id"])
        self.proxy.setAvailability("preview")
        self.assertEqual(self.paths(), ["preview"])
        self.proxy.setAvailability("all")
        self.assertEqual(self.paths(), ["owned", "preview", "text-id"])
        self.proxy.setCarId(0)
        self.assertEqual(self.paths(), ["other-car", "owned", "preview", "text-id"])
        self.proxy.setSearch("")
        self.assertEqual(self.proxy.rowCount(), 5)

    def test_availability_does_not_treat_false_strings_as_permission(self):
        values = [True, False, None, "false", "true", [], {}, 1, 0]
        self.source.replace([livery(str(i), exportable=value) for i, value in enumerate(values)])
        self.proxy.setAvailability("exportable")
        self.assertEqual(self.paths(), ["0", "7"])
        self.proxy.setAvailability("preview")
        self.assertEqual(self.paths(), ["1", "2", "3", "4", "5", "6", "8"])

    def test_all_sort_orders_have_requested_directions(self):
        self.source.replace([
            livery("z", title="alpha", carId=10, placementCount=9, modified="2025-01-01 12:00"),
            livery("b", title="Zulu", carId=2, placementCount="100", modified="2026-10-01 12:00"),
            livery("a", title="ALPHA", carId="2", placementCount=10, modified="2026-02-01 12:00"),
        ])
        for mode, expected in (("modified", ["b", "a", "z"]),
                               ("title", ["a", "z", "b"]),
                               ("car", ["a", "b", "z"]),
                               ("placements", ["b", "a", "z"])):
            with self.subTest(mode=mode):
                self.proxy.setSortOrder(mode)
                self.assertEqual(self.paths(), expected)

    def test_path_ties_are_deterministic_after_source_reordering(self):
        rows = [livery(path) for path in ("z", "a", "B", "b", "A")]
        for mode in SORTS:
            with self.subTest(mode=mode):
                self.proxy.setSortOrder(mode)
                for ordering in (rows, list(reversed(rows))):
                    self.source.replace(ordering)
                    self.assertEqual(self.paths(), ["A", "a", "B", "b", "z"])

    def test_invalid_options_raise_without_changing_state(self):
        self.source.replace([livery("a")])
        self.proxy.setSearch("Blue")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("exportable")
        self.proxy.setSortOrder("title")
        cases = (
            (self.proxy.setAvailability, ("", "ALL", "owned", "preview ", None, [], 1)),
            (self.proxy.setSortOrder, ("", "TITLE", "date", "title ", None, {}, 1)),
            (self.proxy.setCarId, (-1, True, 1.5, "1296", None, [], 2 ** 31)),
            (self.proxy.setSearch, (None, 1, [], {})),
        )
        for setter, values in cases:
            for value in values:
                with self.subTest(setter=setter.__name__, value=value):
                    with self.assertRaises(ValueError):
                        setter(value)
                    self.assertEqual((self.proxy.search, self.proxy.car_id,
                                      self.proxy.availability, self.proxy.sort_order),
                                     ("Blue", 1296, "exportable", "title"))
                    self.assertEqual(self.paths(), ["a"])

    def test_qt_properties_notify_only_when_changed(self):
        cases = (
            ("search", "needle", self.proxy.setSearch, self.proxy.searchChanged),
            ("car_id", 1296, self.proxy.setCarId, self.proxy.carIdChanged),
            ("availability", "preview", self.proxy.setAvailability, self.proxy.availabilityChanged),
            ("sort_order", "title", self.proxy.setSortOrder, self.proxy.sortOrderChanged),
        )
        for name, value, setter, signal in cases:
            with self.subTest(name=name):
                spy = QSignalSpy(signal)
                setter(value)
                setter(value)
                self.assertEqual(self.proxy.property(name), value)
                self.assertEqual(spy.count(), 1)

    def test_source_replace_and_empty_rescan_preserve_filters(self):
        self.source.replace([livery("old")])
        self.proxy.setSearch("blue")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("preview")
        self.proxy.setSortOrder("placements")
        self.assertEqual(self.paths(), [])
        self.source.replace([
            livery("small", exportable=False, placementCount=10),
            livery("large", exportable=False, placementCount=100),
            livery("wrong-car", exportable=False, carId=1),
        ])
        self.assertEqual(self.paths(), ["large", "small"])
        self.source.replace([])
        self.assertEqual(self.paths(), [])
        self.source.replace([livery("new", exportable=False)])
        self.assertEqual(self.paths(), ["new"])
        self.assertEqual((self.proxy.search, self.proxy.car_id,
                          self.proxy.availability, self.proxy.sort_order),
                         ("blue", 1296, "preview", "placements"))

    def test_role_names_resolve_on_source_model_replacement(self):
        old = self.source
        old.replace([livery("old")])
        self.proxy.setSearch("blue")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("exportable")
        self.proxy.setSortOrder("placements")
        self.source = DictListModel(tuple(reversed(ROLES)))
        self.source.replace([livery("low", placementCount=1), livery("high", placementCount=100)])
        self.proxy.setSourceModel(self.source)
        self.proxy.setSourceModel(self.source)
        self.assertEqual(self.paths(), ["high", "low"])
        old.replace([livery("unrelated")])
        old.set_row_value(0, "title", "changed")
        self.assertEqual(self.paths(), ["high", "low"])
        self.proxy.setSourceModel(None)
        self.assertEqual(self.proxy.rowCount(), 0)
        self.proxy.setSourceModel(self.source)
        self.assertEqual(self.paths(), ["high", "low"])

    def test_append_remove_and_data_changes_update_proxy(self):
        self.source.replace([livery("a", exportable=False), livery("b", placementCount=1)])
        self.proxy.setSearch("blue")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("exportable")
        self.proxy.setSortOrder("placements")
        self.assertEqual(self.paths(), ["b"])
        self.source.set_row_value(0, "exportable", True)
        self.assertEqual(self.paths(), ["a", "b"])
        self.source.set_row_value(1, "placementCount", 100)
        self.assertEqual(self.paths(), ["b", "a"])
        self.source.set_row_value(1, "carId", 1)
        self.assertEqual(self.paths(), ["a"])
        self.source.set_row_value(0, "title", "Red")
        self.assertEqual(self.paths(), [])
        self.source.set_row_value(0, "searchText", "BLUE")
        self.assertEqual(self.paths(), ["a"])
        self.source.append_many([livery("c", placementCount=200)])
        self.assertEqual(self.paths(), ["c", "a"])
        self.source.append_many([livery("d", placementCount=300)], max_rows=1)
        self.assertEqual(self.paths(), ["d"])

    def test_changes_to_every_sort_role_and_path_tie_update_order(self):
        for mode, role, value in (("title", "title", "AAA"),
                                  ("car", "carId", 1),
                                  ("modified", "modified", "2026-12-01 00:00"),
                                  ("placements", "placementCount", 100)):
            with self.subTest(mode=mode):
                self.source.replace([livery("a"), livery("b")])
                self.proxy.setSortOrder(mode)
                self.assertEqual(self.paths(), ["a", "b"])
                self.source.set_row_value(1, role, value)
                self.assertEqual(self.paths(), ["b", "a"])
                self.source.set_row_value(0, role, value)
                self.source.set_row_value(1, "path", "0")
                self.assertEqual(self.paths(), ["0", "a"])

    def test_filters_and_sorting_never_mutate_or_signal_source_changes(self):
        rows = [livery("b"), livery("a", exportable=False)]
        original = copy.deepcopy(rows)
        self.source.replace(rows)
        spies = [QSignalSpy(signal) for signal in (
            self.source.dataChanged, self.source.modelReset, self.source.layoutChanged,
            self.source.rowsInserted, self.source.rowsRemoved, self.source.countChanged,
        )]
        for mode in SORTS:
            self.proxy.setSortOrder(mode)
            for availability in ("all", "exportable", "preview"):
                self.proxy.setAvailability(availability)
                self.proxy.setSearch("blue")
                self.proxy.setCarId(1296)
                self.paths()
                self.proxy.setSearch("")
                self.proxy.setCarId(0)
        self.assertEqual(self.source.rows, original)
        self.assertEqual(rows, original)
        self.assertTrue(all(spy.count() == 0 for spy in spies))

    def test_missing_roles_use_safe_defaults_and_title_search_fallback(self):
        self.source = DictListModel(("path", "title"))
        self.source.replace([{"path": "b", "title": "Blue"}, {"path": "a", "title": "Red"}])
        self.proxy.setSourceModel(self.source)
        for mode in ("modified", "car", "placements"):
            self.proxy.setSortOrder(mode)
            self.assertEqual(self.paths(), ["a", "b"])
        self.proxy.setSearch("BLUE")
        self.assertEqual(self.paths(), ["b"])
        self.proxy.setAvailability("exportable")
        self.assertEqual(self.paths(), [])
        self.proxy.setAvailability("preview")
        self.assertEqual(self.paths(), ["b"])
        self.proxy.setCarId(1296)
        self.assertEqual(self.paths(), [])
        self.source = DictListModel(())
        self.source.replace([{}, {}])
        self.proxy.setSourceModel(self.source)
        self.proxy.setSearch("")
        self.proxy.setCarId(0)
        for mode in SORTS:
            self.proxy.setSortOrder(mode)
            self.assertEqual(self.proxy.rowCount(), 2)

    def test_malformed_values_do_not_crash_filtering_or_sorting(self):
        self.source.replace([
            livery("a", title=None, carId={}, placementCount="bad", modified=[], searchText=[]),
            livery("b", title=[], carId=-1, placementCount=float("nan"), modified=None),
            livery("c", carId=1.5, placementCount=float("inf"), modified={}),
            livery("d", carId=True, placementCount=-2, modified=object()),
        ])
        for mode in SORTS:
            self.proxy.setSortOrder(mode)
            self.assertEqual(self.proxy.rowCount(), 4)
            self.paths()
        self.proxy.setCarId(1)
        self.assertEqual(self.paths(), [])

    def test_5000_rows_match_independent_filter_and_sort_oracle(self):
        rows = [livery(
            f"C:/Saves/Livery {i:05d}/C_livery", title=f"Track [{i % 37:02d}] #{i:05d}",
            carId=(2, 10, 1296, 11296)[i % 4], modelCode=f"MODEL_{i % 19:02d}",
            placementCount=(i * 73) % 12001,
            modified=f"2026-{i % 12 + 1:02d}-{i % 28 + 1:02d} {i % 24:02d}:{i % 60:02d}",
            exportable=i % 3 != 0, searchText="Stra\u00dfe .*" if i % 17 == 0 else "",
        ) for i in range(5000)]
        random.Random(1729).shuffle(rows)
        original = copy.deepcopy(rows)
        self.source.replace(rows)
        scenarios = (("", 0, "all"), (".*", 0, "all"), ("STRASSE", 1296, "exportable"),
                     ("track", 10, "preview"), ("[07]", 0, "exportable"), ("missing", 0, "all"))
        for query, car, availability in scenarios:
            self.proxy.setSearch(query)
            self.proxy.setCarId(car)
            self.proxy.setAvailability(availability)
            matches = [row for row in rows
                       if (not car or row["carId"] == car)
                       and (availability == "all" or row["exportable"] == (availability == "exportable"))
                       and any(query.casefold() in str(row[key]).casefold()
                               for key in ("title", "path", "carId", "modelCode", "searchText"))]
            for mode, field in (("modified", "modified"), ("title", "title"),
                                ("car", "carId"), ("placements", "placementCount")):
                with self.subTest(query=query, car=car, availability=availability, mode=mode):
                    expected = sorted(matches, key=lambda row: (row["path"].casefold(), row["path"]))
                    expected.sort(key=lambda row: row[field].casefold() if mode == "title" else row[field],
                                  reverse=mode in ("modified", "placements"))
                    self.proxy.setSortOrder(mode)
                    self.assertEqual(self.paths(), [row["path"] for row in expected])
        self.proxy.setSearch(".*")
        self.proxy.setCarId(1296)
        self.proxy.setAvailability("preview")
        expected = self.paths()
        self.assertTrue(expected)
        self.source.replace(reversed(rows))
        self.assertEqual(self.paths(), expected)
        self.assertEqual(self.source.rows, list(reversed(original)))
        self.assertEqual(rows, original)

    def test_proxy_and_details_do_not_access_filesystem(self):
        row = livery("C:/nonexistent/C_livery", thumbnailUrl="file:///already-indexed.webp")
        with patch("builtins.open", side_effect=AssertionError("file read")), \
                patch.object(io, "open", side_effect=AssertionError("file read")), \
                patch.object(os, "stat", side_effect=AssertionError("file stat")), \
                patch.object(os, "scandir", side_effect=AssertionError("directory scan")):
            self.source.replace([row])
            self.proxy.setSearch("blue")
            self.proxy.setCarId(1296)
            self.proxy.setAvailability("exportable")
            for mode in SORTS:
                self.proxy.setSortOrder(mode)
                self.assertEqual(self.paths(), [row["path"]])
            self.assertEqual(source_details(row)["thumbnailUrl"], row["thumbnailUrl"])


class SourceDetailsTests(unittest.TestCase):
    def test_returns_only_json_safe_display_fields_without_mutation(self):
        row = livery("C:/saved/C_livery", hasHeader=True, privacyDetail="Owned",
                     thumbnailUrl="file:///C:/saved/bigThumb.webp?v=123", privateValue=object())
        original = dict(row)
        expected = {key: row[key] for key in (
            "title", "modelCode", "carId", "placementCount", "modified", "hasHeader",
            "exportable", "privacyDetail", "thumbnailUrl",
        )}
        result = source_details(row)
        self.assertEqual(result, expected)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(row, original)

    def test_manifest_fills_absent_fields_without_overriding_row(self):
        manifest = {"title": "Manifest title", "modelCode": "CAR", "carId": "1296",
                    "placementCount": "123", "hasHeader": True, "exportable": True,
                    "thumbnailUrl": "file:///manifest.webp"}
        original = copy.deepcopy(manifest)
        result = source_details({"title": "Row title", "exportable": False, "thumbnailUrl": ""}, manifest)
        self.assertEqual(result, {
            "title": "Row title", "modelCode": "CAR", "carId": 1296,
            "placementCount": 123, "modified": "", "hasHeader": True,
            "exportable": False, "privacyDetail": "", "thumbnailUrl": "",
        })
        self.assertEqual(manifest, original)
        self.assertEqual(source_details({"carId": None}, manifest)["carId"], 0)

    def test_missing_and_malformed_metadata_have_safe_defaults(self):
        empty = {"title": "", "modelCode": "", "carId": 0, "placementCount": 0,
                 "modified": "", "hasHeader": False, "exportable": False,
                 "privacyDetail": "", "thumbnailUrl": ""}
        for value in (None, [], "bad", 1):
            with self.subTest(value=value):
                self.assertEqual(source_details(value, value), empty)
        result = source_details({"title": [], "modelCode": {}, "carId": True,
                                 "placementCount": float("nan"), "modified": float("inf"),
                                 "hasHeader": "false", "exportable": "true",
                                 "privacyDetail": object(), "thumbnailUrl": []})
        self.assertEqual(result, empty)
        for value in (-1, 1.5, 2 ** 80, "1.5", "bad", float("inf")):
            with self.subTest(value=value):
                self.assertEqual(source_details({"carId": value, "placementCount": value})["carId"], 0)
                self.assertEqual(source_details({"placementCount": value})["placementCount"], 0)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
