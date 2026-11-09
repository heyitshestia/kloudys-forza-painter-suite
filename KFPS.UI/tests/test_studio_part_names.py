"""Synthetic naming contracts plus opt-in, read-only Fairlady qualification.

Real run: set KFPS_PART_NAMES_REAL=1, KFPS_PART_NAMES_GAME_ROOT to the game
content directory and KFPS_PART_NAMES_GLB to an existing Fairlady GLB. Optional
KFPS_PART_NAMES_REPORT writes the qualification result in the caller's run dir.
KFPS_PART_NAMES_BUILD_FIXTURES may override runtime/garage-builds-20261102/
body-fixtures.json for the opt-in shared-resolver check against captured IDs.
KFPS_PART_NAMES_SECOND_GLB may override the existing grouped-sections c4 Subaru
GLB for CPU-only labels without a model-declared body option.
No game data, strings, or FLS catalogue are fixtures in this test module.
The local reference config pins Forza-Mod-Tool c3e4f684, database 661353983,
SHA256 ea500fc3ad2ab7a760e884260b591b14e514739667337aefecb498bddb8f83c6.
Installed-cache metadata now takes precedence. KFPS_PART_NAMES_EXPECT_CURRENT=1
requires that path during qualification; the reference remains a separate fallback.
Neither mode constitutes in-game validation.
"""

from __future__ import annotations

import copy
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import struct
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
from unittest.mock import patch
import warnings
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab import part_names as subject

FAMILIES = {
    "CarBody": ("List_UpgradeCarBody", 38, "Body Kit", "Widebody Kit"),
    "ChassisStiffness": ("List_UpgradeCarBodyChassisStiffness", 54,
                         "Chassis Reinforcement / Roll Cage", "Street Chassis Reinforcement / Roll Cage"),
    "FrontBumper": ("List_UpgradeCarBodyFrontBumper", 24, "Front Bumper", "Street Front Bumper"),
    "Hood": ("List_UpgradeCarBodyHood", 28, "Hood", "Street Hood"),
    "RearBumper": ("List_UpgradeCarBodyRearBumper", 26, "Rear Bumper", "Street Rear Bumper"),
    "RearWing": ("List_UpgradeRearWing", 25, "Rear Wing", "Street Rear Wing"),
    "SideSkirts": ("List_UpgradeCarBodySideSkirt", 27, "Side Skirts", "Street Side Skirts"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loc_hash(value):
    bits = 0xffffffff
    for char in value:
        bits ^= ord(char)
        bits = int(f"{bits:032b}"[7:] + f"{bits:032b}"[:7], 2)
    return bits


def token(table, key):
    return "_&" + str((loc_hash(table) << 32) | loc_hash(key))


def str_file(name, values):
    def section(entries):
        data, symbols = bytearray(), bytearray()
        for key, text in entries:
            symbols.extend(struct.pack("<II", loc_hash(key), len(data)))
            data.extend(text.encode("utf-8") + b"\0")
        return struct.pack("<iii", len(symbols) + len(data), len(data), len(entries)) + symbols + data

    content = section(list(values.items()))
    names = section([(key, key) for key in values])
    return struct.pack("<H126shhii", 0x800, name.encode("ascii"), 0, 2, 140,
                       140 + len(content)) + content + names


class PartNamesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kfps-part-names-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in [('CATALOGUE_CACHE_ROOT', self.root / 'cache'),
                            ('CATALOGUE_READER_CONFIG', self.root / 'absent-reader.json')]:
            setting = patch.object(subject, name, value, create=True)
            setting.start()
            self.addCleanup(setting.stop)
        self.game = self.root / "game"
        self.archive = self.game / "media/stripped/StringTables/EN.zip"
        self.archive.parent.mkdir(parents=True)
        self.database = self.root / "reference.sqlite"
        self.vehicle = {"car_id": 344, "model_code": "NIS_FairladyZ_03"}
        self.options = []
        self.strings = {"List_PartManufacturer": {"IDS_PartManufacturer_661": "Rocket Bunny"},
                        "UpgradeTypes": {}, "Upgrades": {}}
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript("""
                CREATE TABLE VersionInfo (database_version INTEGER);
                INSERT INTO VersionInfo VALUES (661353983);
                CREATE TABLE Data_Car (Id INTEGER, MediaName TEXT);
                INSERT INTO Data_Car VALUES (344, 'NIS_FairladyZ_03');
                CREATE TABLE Data_CarBody (Id INTEGER);
                INSERT INTO Data_CarBody VALUES (344000), (344001);
                CREATE TABLE List_PartManufacturer (Id INTEGER, PartManufacturer TEXT);
                CREATE TABLE UpgradeTypes (Id INTEGER, PartName TEXT, IsException INTEGER, Name TEXT);
                CREATE TABLE Upgrades (Id INTEGER, TypeId TEXT, Level INTEGER, IsException INTEGER, Name TEXT);
                CREATE TABLE Data_UpgradePart (Id INTEGER, TableName TEXT, CategoryName TEXT,
                                              PartName TEXT, HasRequiresGraphics INTEGER);
                INSERT INTO Data_UpgradePart VALUES
                    (41, 'List_UpgradeCarBodyChassisStiffness', 'CarBody', 'ChassisStiffness', 1);
            """)
            db.execute("INSERT INTO List_PartManufacturer VALUES (?,?)",
                       (661, token("List_PartManufacturer", "IDS_PartManufacturer_661")))
            for family, (table, type_id, category, product) in FAMILIES.items():
                db.execute(f"CREATE TABLE {table} (Id INTEGER, Ordinal INTEGER, CarBodyID INTEGER, "
                           "Level INTEGER, IsStock INTEGER, ManufacturerID INTEGER, PartsStringID INTEGER, "
                           "RequiresGraphics INTEGER)")
                db.execute(f"INSERT INTO {table} VALUES (344100,344,344001,1,0,661,0,1)")
                key = "IDS_Name_" + str(type_id)
                product_key = "IDS_Name_" + str(type_id + 100)
                self.strings["UpgradeTypes"][key] = category
                self.strings["Upgrades"][product_key] = product
                db.execute("INSERT INTO UpgradeTypes VALUES (?,?,0,?)",
                           (type_id, family, token("UpgradeTypes", key)))
                db.execute("INSERT INTO Upgrades VALUES (?,?,1,0,?)",
                           (type_id + 100, str(type_id), token("Upgrades", product_key)))
                parent = -1 if family in ("CarBody", "RearWing") else 344001
                self.options.append({"part_type": family, "id": 344100, "level": 1,
                    "stock": False, "parent_upgrade_id": parent, "car_body_id": parent,
                    "parent_is_stock": False})
            db.execute("INSERT INTO List_UpgradeCarBody VALUES (344000,344,344000,0,1,0,0,1)")
            db.execute("INSERT INTO Upgrades VALUES (143,38,0,0,?)",
                       (token("Upgrades", "IDS_Name_143"),))
            self.strings["Upgrades"]["IDS_Name_143"] = "Stock Body"
            self.options.append({"part_type": "CarBody", "id": 344000, "level": 0,
                                 "stock": True, "parent_upgrade_id": -1})
        self.config = {"format": "kfps-part-names-reference-v1", "sqlite_path": str(self.database),
                       "sha256": digest(self.database), "database_version": 661353983, "language": "EN"}
        self.write_strings()

    def write_strings(self):
        with zipfile.ZipFile(self.archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for table, values in self.strings.items():
                bundle.writestr(table + ".str", str_file(table, values))

    def change_db(self, statement, parameters=()):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(statement, parameters)
        self.config["sha256"] = digest(self.database)

    def load(self, options=None, vehicle=None, config=None):
        return subject.load_part_names(self.game, self.vehicle if vehicle is None else vehicle,
            self.options if options is None else options,
            reference_config=self.config if config is None else config)

    def name(self, family, result=None, ident=344100):
        return next(row for row in (result or self.load())["names"]
                    if row["part_type"] == family and row["id"] == ident)

    def add_non_visual(self):
        self.change_db("INSERT INTO List_UpgradeCarBodyChassisStiffness VALUES (344101,344,344001,2,0,661,0,0)")
        self.change_db("INSERT INTO Upgrades VALUES (155,'54',2,0,?)",
                       (token("Upgrades", "IDS_Name_155"),))
        self.strings["Upgrades"]["IDS_Name_155"] = "Sport Chassis Reinforcement / Roll Cage"
        self.write_strings()

    def test_fixed_stock_body_uses_exact_current_car_rows_not_saved_id_guessing(self):
        self.change_db('DELETE FROM List_UpgradeCarBody WHERE Id=344100')
        for family, (table, *_) in FAMILIES.items():
            if family != 'CarBody':
                self.change_db(f'UPDATE {table} SET CarBodyID=344000, IsStock=1')
        options = [row for row in self.options if row['part_type'] == 'RearWing']
        options[0] = {**options[0], 'stock': True}
        cached = {'database': self.database.read_bytes(), 'provenance': {'current': True}}
        with patch.object(subject, 'load_installed_catalogue', return_value=cached):
            names = subject.load_part_names(self.game, self.vehicle, options, fixed_body=True)
            fixed = {(row['part_type'], row['id']) for row in names['fixed_stock_options']}
            self.assertIn(('CarBody', 344000), fixed)
            self.assertIn(('Hood', 344100), fixed)
            self.assertNotIn(('RearWing', 344100), fixed)
            self.assertTrue(all(row['stock'] and row['empty'] for row in names['fixed_stock_options']))
            self.assertEqual([], subject.load_part_names(self.game, self.vehicle, options)['fixed_stock_options'])
            cached['provenance']['current'] = False
            self.assertEqual([], subject.load_part_names(self.game, self.vehicle, options, fixed_body=True)['fixed_stock_options'])

    def test_fixed_stock_rejects_multiple_body_options_and_nonstock_parts(self):
        cached = {'database': self.database.read_bytes(), 'provenance': {'current': True}}
        with patch.object(subject, 'load_installed_catalogue', return_value=cached):
            names = subject.load_part_names(self.game, self.vehicle, [], fixed_body=True)
            self.assertEqual([], names['fixed_stock_options'])
        self.change_db('DELETE FROM List_UpgradeCarBody WHERE Id=344100')
        cached['database'] = self.database.read_bytes()
        with patch.object(subject, 'load_installed_catalogue', return_value=cached):
            names = subject.load_part_names(self.game, self.vehicle, [], fixed_body=True)
            self.assertEqual(['CarBody'], [r['part_type'] for r in names['fixed_stock_options']])

    def test_all_seven_exact_names_and_body_namespace(self):
        result = self.load()
        self.assertEqual(set(FAMILIES), {row["part_type"] for row in result["names"]})
        self.assertTrue(all(row["status"] == "resolved" for row in result["names"]))
        self.assertEqual("Rocket Bunny", self.name("CarBody", result)["manufacturer"])
        self.assertEqual("Widebody Kit", self.name("CarBody", result)["product"])
        self.assertEqual(344001, self.name("CarBody", result)["data_car_body_id"])
        self.assertEqual([{"parent_upgrade_id": 344000, "body_option_id": 344000},
                          {"parent_upgrade_id": 344001, "body_option_id": 344100}],
                         result["body_compatibility"]["parent_map"])
        self.assertTrue(result["reference_only"])
        self.assertFalse(result["same_build_verified"])
        self.assertFalse(result["body_compatibility"]["same_build_verified"])

    def test_failed_installed_source_cannot_authorize_reference_geometry_without_cache(self):
        self.add_non_visual()
        installed = self.game / "media/stripped/gamedbRC.slt"
        installed.write_bytes(b"unsupported installed catalogue")
        result = self.load()
        self.assertTrue(result["names"])
        self.assertFalse(result["same_build_verified"])
        self.assertIsNone(result["body_compatibility"])
        self.assertEqual([], result["non_visual_options"])
        self.assertIn("installed-catalogue-unavailable", result["warnings"])

    def test_malformed_body_parent_is_never_an_absent_parent(self):
        self.add_non_visual()
        for parent in ("not-a-body-id", True, 0, -2, 1.5, {}, []):
            with self.subTest(parent=parent):
                options = copy.deepcopy(self.options)
                body = next(o for o in options if o["part_type"] == "CarBody" and o["id"] == 344100)
                body["parent_upgrade_id"] = body["car_body_id"] = parent
                result = self.load(options=options)
                self.assertEqual("unresolved", self.name("CarBody", result)["status"])
                self.assertEqual([], result["non_visual_options"])
                self.assertNotIn(344100, [p["body_option_id"] for p in result["body_compatibility"]["parent_map"]])

    def test_deterministic_detached_json_and_unchanged_inputs(self):
        original = copy.deepcopy((self.options, self.vehicle, self.config))
        before = [(digest(path), path.stat().st_mtime_ns) for path in (self.database, self.archive)]
        first = self.load()
        self.assertEqual(first, json.loads(json.dumps(self.load())))
        self.assertNotIn(str(self.root), json.dumps(first))
        self.assertEqual(original, (self.options, self.vehicle, self.config))
        self.assertEqual(before, [(digest(path), path.stat().st_mtime_ns)
                                  for path in (self.database, self.archive)])
        first["names"][0]["manufacturer"] = "caller mutation"
        self.assertNotEqual(first, self.load())

    def test_absent_optional_sources_return_empty_without_raising(self):
        with patch.object(subject, "STUDIO_ROOT", self.root / "absent-studio"):
            self.assertEqual([], subject.load_part_names(self.game, self.vehicle, self.options)["names"])
        self.assertEqual([], self.load(config=self.root / "missing.json")["names"])
        self.archive.unlink()
        self.assertEqual([], self.load()["names"])

    def test_non_sqlite_install_without_local_reference_has_no_shipped_catalogue(self):
        installed = self.game / "media/stripped/gamedbRC.slt"
        installed.write_bytes(b"not a readable SQLite database")
        with patch.object(subject, "STUDIO_ROOT", self.root / "ordinary-studio"):
            result = subject.load_part_names(self.game, self.vehicle, self.options)
        self.assertEqual("Part names unavailable", result["source"])
        self.assertEqual([], result["names"])
        self.assertEqual([], result["non_visual_options"])
        self.assertIsNone(result["body_compatibility"])
        self.assertEqual({}, result["provenance"])
        self.assertIn("installed-catalogue-unavailable", result["warnings"])
        self.assertIn("reader-unavailable", result["warnings"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_relative_default_config_and_media_root(self):
        settings = self.root / "settings"
        settings.mkdir()
        config = dict(self.config, sqlite_path="../reference.sqlite")
        (settings / "part-names-reference.json").write_text(json.dumps(config), encoding="utf-8")
        with patch.object(subject, "STUDIO_ROOT", self.root):
            result = subject.load_part_names(self.game / "media", self.vehicle, self.options)
        self.assertEqual(8, len(result["names"]))

    def test_bad_reference_hash_version_and_format_fail_closed(self):
        for change in ({"sha256": "0" * 64}, {"database_version": 7}, {"format": "wrong"},
                       {"sqlite_path": "relative.sqlite"}, {"language": "../EN"}):
            with self.subTest(change=change):
                result = self.load(config=dict(self.config, **change))
                self.assertEqual([], result["names"])
                self.assertEqual([], result["non_visual_options"])
                self.assertIsNone(result["body_compatibility"])
                self.assertTrue(result["warnings"])

    def test_readable_installed_database_preferred(self):
        installed = self.game / "media/stripped/gamedbRC.slt"
        installed.write_bytes(self.database.read_bytes())
        before = digest(installed)
        result = self.load(config=dict(self.config, sha256="0" * 64))
        self.assertEqual(8, len(result["names"]))
        self.assertFalse(result["reference_only"])
        self.assertFalse(result["body_compatibility"]["reference_only"])
        self.assertEqual(before, digest(installed))
        self.assertEqual(result, self.load(config={"format": "invalid"}))

    def test_automatic_catalogue_is_current_and_deterministic_after_first_read(self):
        self.add_non_visual()
        installed = self.game / 'media/stripped/gamedbRC.slt'
        installed.write_bytes(self.database.read_bytes())
        first = self.load(config={'format': 'invalid'})
        self.assertTrue(first['same_build_verified'])
        self.assertFalse(first['reference_only'])
        self.assertTrue(first['body_compatibility']['same_build_verified'])
        self.assertEqual(digest(installed), first['provenance']['source_sha256'])
        self.assertEqual(first, self.load(config={'format': 'invalid'}))
        self.assertNotIn('refreshed', json.dumps(first))
        self.assertNotIn(str(self.root), json.dumps(first))

    def test_failed_refresh_keeps_names_but_not_old_fitment_or_virtual_options(self):
        self.add_non_visual()
        installed = self.game / 'media/stripped/gamedbRC.slt'
        installed.write_bytes(self.database.read_bytes())
        good = self.load()
        self.assertTrue(good['non_visual_options'])
        installed.write_bytes(b'unsupported replacement')
        stale = self.load()
        self.assertTrue(stale['names'])
        self.assertTrue(stale['reference_only'])
        self.assertFalse(stale['same_build_verified'])
        self.assertIn('Previous installed', stale['source'])
        self.assertIn('installed-catalogue-stale', stale['warnings'])
        self.assertEqual([], stale['non_visual_options'])
        self.assertIsNone(stale['body_compatibility'])

    def test_cancellation_is_not_hidden_as_optional_names_failure(self):
        with patch.object(subject, 'load_installed_catalogue', create=True,
                          side_effect=InterruptedError('cancelled')):
            with self.assertRaises(InterruptedError):
                self.load()

    def test_cancellation_after_localization_does_not_return_body_metadata(self):
        event = threading.Event()
        localize = subject._localization

        def interrupted(*args):
            result = localize(*args)
            event.set()
            return result

        with patch.object(subject, '_localization', side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                subject.load_part_names(self.game, self.vehicle, self.options,
                    reference_config=self.config, cancel_event=event)

    def test_cancellation_during_resolution_is_not_an_optional_failure(self):
        event = threading.Event()
        rows = subject._rows

        def interrupted(*args, **kwargs):
            result = rows(*args, **kwargs)
            if args[1] == 'Data_Car':
                event.set()
            return result

        with patch.object(subject, '_rows', side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                subject.load_part_names(self.game, self.vehicle, self.options,
                    reference_config=self.config, cancel_event=event)

    def assert_identity_rejected(self, result, warning="car-identity-mismatch"):
        self.assertEqual([], result["names"])
        self.assertEqual([], result["non_visual_options"])
        self.assertIsNone(result["body_compatibility"])
        self.assertIn(warning, result["warnings"])

    def test_ascii_case_only_model_codes_resolve_for_reference_and_installed_sources(self):
        self.add_non_visual()
        code = self.vehicle["model_code"]
        variants = (code, code.lower(), code.upper(), code.swapcase())
        installed = self.game / "media/stripped/gamedbRC.slt"
        for source in ("reference", "installed"):
            for media_name in variants:
                self.change_db("UPDATE Data_Car SET MediaName=?", (media_name,))
                if source == "installed":
                    installed.write_bytes(self.database.read_bytes())
                expected = self.load(vehicle=dict(self.vehicle, model_code=media_name))
                self.assertEqual(9, len(expected["names"]))
                self.assertTrue(all(row["status"] == "resolved" for row in expected["names"]))
                self.assertEqual([344101], [row["id"] for row in expected["non_visual_options"]])
                self.assertEqual(source == "reference", expected["reference_only"])
                for model_code in variants:
                    with self.subTest(source=source, media_name=media_name, model_code=model_code):
                        vehicle = dict(self.vehicle, model_code=model_code)
                        before = copy.deepcopy((vehicle, self.options, self.config))
                        self.assertEqual(expected, self.load(vehicle=vehicle))
                        self.assertEqual(before, (vehicle, self.options, self.config))

    def test_wrong_car_or_different_complete_model_code_does_not_resolve(self):
        for vehicle in ({"car_id": 999, "model_code": "NIS_FairladyZ_03"},
                        {"car_id": 345, "model_code": "nis_fairladyz_03"},
                        {"car_id": 344, "model_code": "nis_fairladyz_04"},
                        {"car_id": 344, "model_code": "nis_fairladyz"},
                        {"car_id": 344, "model_code": "nis_fairladyz_03_extra"},
                        {"car_id": 344, "model_code": "other_fairladyz_03"},
                        {"car_id": 344, "model_code": "nis-fairladyz-03"}):
            with self.subTest(vehicle=vehicle):
                self.assert_identity_rejected(self.load(vehicle=vehicle))

    def test_matching_model_on_another_car_id_is_not_guessed(self):
        self.change_db("UPDATE Data_Car SET Id=999, MediaName='nis_fairladyz_03'")
        self.assert_identity_rejected(self.load())

    def test_car_id_must_be_an_exact_positive_integer(self):
        for car_id in (None, True, False, "344", 344.0, 0, -344, 2**31):
            with self.subTest(car_id=car_id):
                result = self.load(vehicle=dict(self.vehicle, car_id=car_id))
                self.assert_identity_rejected(result, "exact-car-identity-unavailable")

    def test_malformed_database_car_ids_are_not_coerced(self):
        self.change_db("DROP TABLE Data_Car")
        self.change_db("CREATE TABLE Data_Car (Id, MediaName TEXT)")
        for car_id in (None, "344", 344.0, b"344"):
            with self.subTest(car_id=car_id):
                self.change_db("DELETE FROM Data_Car")
                self.change_db("INSERT INTO Data_Car VALUES (?,?)", (car_id, self.vehicle["model_code"]))
                self.assert_identity_rejected(self.load())

    def test_duplicate_car_identity_is_not_selected_by_model_case(self):
        self.change_db("INSERT INTO Data_Car VALUES (344, 'nis_fairladyz_03')")
        self.assert_identity_rejected(self.load())

    def test_model_paths_and_malformed_values_are_rejected_on_either_side(self):
        code = self.vehicle["model_code"]
        invalid = (None, "", 344, True, 344.0, b"NIS_FairladyZ_03",
                   "../" + code, "media/cars/" + code, "C:\\cars\\" + code,
                   "\\\\server\\cars\\" + code, code + ".zip", code + ".", ".", "..",
                   " " + code, code + " ", "NIS FairladyZ 03", code + "\n", code + "\0",
                   "_" + code, "A" * 201, "NIS_Fairlad\u00fdZ_03")
        for value in invalid:
            for side in ("vehicle", "database", "both"):
                with self.subTest(value=value, side=side):
                    media_name = code if side == "vehicle" else value
                    model_code = code if side == "database" else value
                    self.change_db("UPDATE Data_Car SET MediaName=?", (media_name,))
                    result = self.load(vehicle=dict(self.vehicle, model_code=model_code))
                    warning = ("exact-car-identity-unavailable"
                               if not isinstance(model_code, str) or not model_code
                               else "car-identity-mismatch")
                    self.assert_identity_rejected(result, warning)
        for value in ([], {}):
            with self.subTest(value=value):
                result = self.load(vehicle=dict(self.vehicle, model_code=value))
                self.assert_identity_rejected(result, "exact-car-identity-unavailable")

    def test_unicode_case_equivalents_are_not_ascii_model_matches(self):
        pairs = (("NI\u017f_FairladyZ_03", "NIS_FairladyZ_03"),
                 ("NIS_Fairlady\u212a_03", "NIS_FairladyK_03"),
                 ("NIS_Stra\u00dfe_03", "NIS_STRASSE_03"))
        for left, right in pairs:
            for media_name, model_code in ((left, right), (right, left)):
                with self.subTest(media_name=media_name, model_code=model_code):
                    self.change_db("UPDATE Data_Car SET MediaName=?", (media_name,))
                    self.assert_identity_rejected(self.load(vehicle=dict(self.vehicle, model_code=model_code)))

    def test_child_names_require_exact_native_parent_not_declared_body(self):
        options = copy.deepcopy(self.options)
        hood = next(row for row in options if row["part_type"] == "Hood")
        hood["parent_upgrade_id"] = hood["car_body_id"] = 344000
        self.assertEqual("unresolved", self.name("Hood", self.load(options))["status"])
        options = [row for row in self.options if row["part_type"] != "CarBody"]
        result = self.load(options)
        self.assertEqual("resolved", self.name("Hood", result)["status"])
        self.assertEqual("resolved", self.name("RearWing", result)["status"])
        self.assertEqual([], result["body_compatibility"]["parent_map"])
        self.assertEqual([], result["non_visual_options"])

    def test_conflicting_body_declaration_cannot_anchor_geometry_but_native_labels_survive(self):
        options = copy.deepcopy(self.options)
        next(row for row in options if row["part_type"] == "CarBody" and row["id"] == 344100)["level"] = 8
        result = self.load(options)
        self.assertEqual("unresolved", self.name("CarBody", result)["status"])
        self.assertEqual("resolved", self.name("Hood", result)["status"])
        self.assertEqual(1, len(result["body_compatibility"]["parent_map"]))

    def test_undeclared_body_labels_still_reject_foreign_car_parent_and_level_conflicts(self):
        options = [copy.deepcopy(row) for row in self.options if row["part_type"] != "CarBody"]
        hood = next(row for row in options if row["part_type"] == "Hood")
        hood["level"] = 2
        self.assertEqual("unresolved", self.name("Hood", self.load(options))["status"])
        hood["level"] = 1
        self.change_db("UPDATE List_UpgradeCarBody SET Ordinal=999 WHERE Id=344100")
        result = self.load(options)
        self.assertEqual("unresolved", self.name("Hood", result)["status"])
        self.assertEqual(["body-parent-unavailable"], self.name("Hood", result)["issues"])
        self.assertEqual([], result["body_compatibility"]["parent_map"])
        self.assertEqual([], result["non_visual_options"])

    def test_root_option_from_another_car_stays_unresolved(self):
        self.change_db("UPDATE List_UpgradeRearWing SET Ordinal=999")
        self.assertEqual("unresolved", self.name("RearWing")["status"])

    def test_no_parent_id_alias_and_only_explicit_nonvisual_options_emitted(self):
        self.change_db("INSERT INTO List_UpgradeCarBodyChassisStiffness VALUES (344101,344,344001,2,0,661,0,0)")
        result = self.load()
        self.assertEqual([344101], [row["id"] for row in result["non_visual_options"]])
        self.assertEqual("partial", self.name("ChassisStiffness", result, 344101)["status"])
        options = copy.deepcopy(self.options)
        next(row for row in options if row["part_type"] == "CarBody" and row["id"] == 344100)["id"] = 344001
        self.assertEqual("unresolved", self.name("CarBody", self.load(options), 344001)["status"])

    def test_non_visual_option_exact_shape_names_and_no_input_mutation(self):
        self.add_non_visual()
        before = copy.deepcopy(self.options)
        result = self.load()
        self.assertEqual([{"part_type": "ChassisStiffness", "part_type_value": 41, "id": 344101,
            "level": 2, "stock": False, "baseline": False, "car_body_id": 344001,
            "parent_upgrade_id": 344001, "parent_is_stock": False, "fitment_verified": False,
            "supported": True, "empty": True, "declared_instance_count": 0,
            "requires_graphics": False, "source_kind": "database-nonvisual",
            "reference_only": True, "issues": []}], result["non_visual_options"])
        name = self.name("ChassisStiffness", result, 344101)
        self.assertEqual("resolved", name["status"])
        self.assertEqual("Sport Chassis Reinforcement / Roll Cage", name["product"])
        self.assertEqual("Rocket Bunny", name["manufacturer"])
        self.assertEqual("database-nonvisual", name["source_kind"])
        self.assertTrue(name["reference_only"])
        self.assertEqual(before, self.options)
        self.assertEqual(result, json.loads(json.dumps(self.load())))

    def test_non_visual_requires_exact_capability_not_inferred_from_family(self):
        self.add_non_visual()
        changes = (("HasRequiresGraphics", 0), ("HasRequiresGraphics", None),
                   ("HasRequiresGraphics", "unknown"), ("TableName", "OtherTable"),
                   ("CategoryName", "OtherCategory"), ("PartName", "OtherPart"), ("Id", 99))
        defaults = {"HasRequiresGraphics": 1, "TableName": FAMILIES["ChassisStiffness"][0],
                    "CategoryName": "CarBody", "PartName": "ChassisStiffness", "Id": 41}
        for column, value in changes:
            with self.subTest(column=column, value=value):
                self.change_db(f"UPDATE Data_UpgradePart SET {column}=?", (value,))
                result = self.load()
                self.assertEqual([], result["non_visual_options"])
                self.assertEqual(8, len(result["names"]))
                self.change_db(f"UPDATE Data_UpgradePart SET {column}=?", (defaults[column],))
        self.change_db("INSERT INTO Data_UpgradePart SELECT * FROM Data_UpgradePart")
        self.assertEqual([], self.load()["non_visual_options"])
        self.change_db("DROP TABLE Data_UpgradePart")
        result = self.load()
        self.assertEqual([], result["non_visual_options"])
        self.assertEqual(8, len(result["names"]))

    def test_non_visual_requires_explicit_zero_graphics_flag(self):
        self.add_non_visual()
        for flag in (1, None, -1, "unknown"):
            with self.subTest(flag=flag):
                self.change_db("UPDATE List_UpgradeCarBodyChassisStiffness SET RequiresGraphics=? WHERE Id=344101",
                               (flag,))
                self.assertEqual([], self.load()["non_visual_options"])
        self.change_db("UPDATE List_UpgradeCarBodyChassisStiffness SET RequiresGraphics=0 WHERE Id=344101")
        self.assertEqual(1, len(self.load()["non_visual_options"]))

    def test_non_visual_requires_declared_family_and_exact_declared_body(self):
        self.add_non_visual()
        for family, ident in (("CarBody", 344100), ("ChassisStiffness", 344100)):
            with self.subTest(family=family):
                options = [o for o in self.options if (o["part_type"], o["id"]) != (family, ident)]
                self.assertEqual([], self.load(options)["non_visual_options"])
        options = copy.deepcopy(self.options)
        next(o for o in options if o["part_type"] == "CarBody" and o["id"] == 344100)["level"] = 9
        self.assertEqual([], self.load(options)["non_visual_options"])
        self.change_db("UPDATE List_UpgradeCarBodyChassisStiffness SET CarBodyID=999 WHERE Id=344101")
        self.assertEqual([], self.load()["non_visual_options"])

    def test_non_visual_does_not_replace_existing_even_conflicting_declarations(self):
        self.add_non_visual()
        declared = {"part_type": "ChassisStiffness", "id": 344101,
                    "parent_upgrade_id": 344000, "level": 3}
        result = self.load(self.options + [declared, dict(declared)])
        self.assertEqual([], result["non_visual_options"])
        self.assertEqual("unresolved", self.name("ChassisStiffness", result, 344101)["status"])

    def test_non_visual_duplicate_id_in_another_body_is_not_qualified(self):
        self.add_non_visual()
        self.change_db("INSERT INTO List_UpgradeCarBodyChassisStiffness VALUES (344101,999,999000,2,0,661,0,0)")
        result = self.load()
        self.assertEqual([], result["non_visual_options"])
        self.assertEqual(8, len(result["names"]))

    def test_non_visual_invalid_rows_or_count_are_nonfatal(self):
        self.add_non_visual()
        for field, value, original in (("IsStock", 2, 0), ("Level", 256, 2),
                                       ("Id", -1, 344101), ("Ordinal", 999, 344)):
            with self.subTest(field=field):
                self.change_db(f"UPDATE List_UpgradeCarBodyChassisStiffness SET {field}=? WHERE Level=2", (value,))
                self.assertEqual([], self.load()["non_visual_options"])
                self.change_db(f"UPDATE List_UpgradeCarBodyChassisStiffness SET {field}=? WHERE {field}=?",
                               (original, value))
        with patch.object(subject, "MAX_OPTIONS", len(self.options)):
            result = self.load()
            self.assertEqual([], result["non_visual_options"])
            self.assertEqual(8, len(result["names"]))

    def test_non_visual_never_generalizes_to_other_part_families(self):
        self.change_db("INSERT INTO List_UpgradeCarBodyHood VALUES (344101,344,344001,2,0,661,0,0)")
        self.assertEqual([], self.load()["non_visual_options"])
        self.assertFalse(any(o["id"] == 344101 for o in self.load()["names"]))

    def test_non_visual_preserves_installed_source_identity(self):
        self.add_non_visual()
        installed = self.game / "media/stripped/gamedbRC.slt"
        installed.write_bytes(self.database.read_bytes())
        result = self.load()
        self.assertFalse(result["non_visual_options"][0]["reference_only"])
        self.assertFalse(self.name("ChassisStiffness", result, 344101)["reference_only"])

    def test_duplicate_or_negative_declarations_do_not_block_optional_metadata(self):
        options = copy.deepcopy(self.options)
        options.extend([dict(options[1]), {"part_type": "CarBody", "id": -1}, None,
                        {"part_type": "Hood", "id": True}])
        result = self.load(options)
        self.assertEqual("duplicate-option-id", self.name("ChassisStiffness", result)["issues"][0])
        self.assertEqual("unresolved", self.name("CarBody", result, -1)["status"])
        self.assertEqual("resolved", self.name("RearWing", result)["status"])
        self.assertTrue(result["warnings"])

    def test_invalid_callers_and_empty_options_do_not_raise_or_read_files(self):
        with patch.object(subject, "_read", side_effect=AssertionError("unexpected I/O")):
            for vehicle, options in (({}, self.options), (self.vehicle, []),
                                     (self.vehicle, None), (self.vehicle, [{"id": None}])):
                self.assertEqual([], subject.load_part_names(self.game, vehicle, options)["names"])

    def test_ambiguous_body_reference_is_not_guessed(self):
        self.change_db("INSERT INTO List_UpgradeCarBody VALUES (344200,344,344001,1,0,661,0,1)")
        result = self.load()
        self.assertEqual([], result["names"])
        self.assertIn("body-parent-ambiguous", result["warnings"])

    def test_missing_product_or_manufacturer_is_partial(self):
        self.change_db("DELETE FROM Upgrades WHERE TypeId='28'")
        hood = self.name("Hood")
        self.assertEqual("partial", hood["status"])
        self.assertIsNone(hood["product"])
        self.assertEqual("Rocket Bunny", hood["manufacturer"])
        self.change_db("UPDATE List_UpgradeRearWing SET ManufacturerID=777")
        self.assertEqual("partial", self.name("RearWing")["status"])

    def test_ambiguous_product_and_exception_type_do_not_choose_first(self):
        self.change_db("INSERT INTO Upgrades SELECT * FROM Upgrades WHERE TypeId='28'")
        self.assertIsNone(self.name("Hood")["product"])
        self.change_db("INSERT INTO UpgradeTypes VALUES (999,'RearWing',1,'exception')")
        self.assertEqual("resolved", self.name("RearWing")["status"])
        self.change_db("INSERT INTO UpgradeTypes VALUES (998,'RearWing',0,'ambiguous')")
        self.assertEqual("partial", self.name("RearWing")["status"])

    def test_manufacturer_zero_is_not_guessed_and_stock_does_not_change_level(self):
        self.change_db("UPDATE List_UpgradeCarBodyChassisStiffness SET IsStock=1,ManufacturerID=0")
        options = copy.deepcopy(self.options)
        next(row for row in options if row["part_type"] == "ChassisStiffness")["stock"] = True
        row = self.name("ChassisStiffness", self.load(options))
        self.assertIsNone(row["manufacturer"])
        self.assertTrue(row["is_stock"])
        self.assertEqual("Street Chassis Reinforcement / Roll Cage", row["product"])

    def test_missing_localization_table_is_partial_not_raw_token(self):
        del self.strings["List_PartManufacturer"]
        self.write_strings()
        result = self.load()
        row = self.name("Hood", result)
        self.assertEqual("partial", row["status"])
        self.assertIsNone(row["manufacturer"])
        self.assertNotIn("_&", json.dumps(result["names"]))

    def test_hash_and_utf8_string_parser_known_token(self):
        self.assertEqual("_&14848208903670025758",
                         token("List_PartManufacturer", "IDS_PartManufacturer_661"))
        values = subject._parse_strings(str_file("List_PartManufacturer",
                    {"IDS_PartManufacturer_661": "Rocket Bunny"}), "List_PartManufacturer")
        self.assertEqual("Rocket Bunny", values[14848208903670025758])

    def test_truncated_bad_offsets_duplicate_symbols_and_unsupported_version(self):
        valid = str_file("Upgrades", {"a": "one", "b": "two"})
        bad_offset = bytearray(valid)
        struct.pack_into("<i", bad_offset, 132, len(valid) + 1)
        duplicate = bytearray(valid)
        duplicate[160:164] = duplicate[152:156]
        bad_version = bytearray(valid)
        struct.pack_into("<H", bad_version, 0, 0x400)
        for value in (valid[:135], bytes(bad_offset), bytes(duplicate), bytes(bad_version)):
            with self.subTest(length=len(value)):
                with self.assertRaises(ValueError):
                    subject._parse_strings(value, "Upgrades")

    def test_duplicate_archive_member_is_rejected_without_extraction(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "a") as bundle:
                bundle.writestr("Upgrades.str", str_file("Upgrades", {}))
        self.assertEqual([], self.load()["names"])
        self.assertFalse((self.root / "Upgrades.str").exists())

    def test_size_and_option_limits_are_nonfatal(self):
        for constant, limit in (("MAX_DATABASE_BYTES", 16), ("MAX_ARCHIVE_BYTES", 16),
                                ("MAX_OPTIONS", 1)):
            with self.subTest(constant=constant), patch.object(subject, constant, limit):
                self.assertEqual([], self.load()["names"])

    def test_replaced_same_size_source_is_revalidated_without_cache(self):
        data = bytearray(self.database.read_bytes())
        data[-1] ^= 1
        self.database.write_bytes(data)
        result = self.load()
        self.assertEqual([], result["names"])
        self.assertIn("reference-fingerprint-mismatch", result["warnings"])


def process_memory():
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("peak", "current", "peak_paged", "paged",
                "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        return {}
    return {"peak_working_set_bytes": counters.peak, "working_set_bytes": counters.current}


@unittest.skipUnless(os.environ.get("KFPS_PART_NAMES_REAL") == "1", "opt-in local qualification")
class PartNamesRealTests(unittest.TestCase):
    def test_fairlady_all_seven_strings_and_bounded_call_cost(self):
        game = Path(os.environ["KFPS_PART_NAMES_GAME_ROOT"])
        path = Path(os.environ["KFPS_PART_NAMES_GLB"])
        with path.open("rb") as stream:
            magic, version, total, size, chunk = struct.unpack("<4sIIII", stream.read(20))
            self.assertEqual((b"glTF", 2, 0x4e4f534a), (magic, version, chunk))
            self.assertLess(size, 16 * 1024 * 1024)
            document = json.loads(stream.read(size))
        options = document["scenes"][document.get("scene", 0)]["extras"]["kfps_part_options"]
        before = copy.deepcopy(options)
        vehicle = {"car_id": 344, "model_code": "NIS_FairladyZ_03"}
        memory_before = process_memory()
        times, results = [], []
        for _ in range(8):
            start = time.perf_counter()
            result = subject.load_part_names(game, vehicle, options)
            times.append((time.perf_counter() - start) * 1000)
            results.append(result)
        self.assertTrue(all(result == results[0] for result in results))
        result = results[0]
        self.assertEqual([], result["warnings"])
        self.assertEqual(set(FAMILIES), {row["part_type"] for row in result["names"]})
        virtual = result["non_visual_options"]
        self.assertEqual([344001, 344101], [row["id"] for row in virtual])
        self.assertEqual([344000, 344001], [row["parent_upgrade_id"] for row in virtual])
        self.assertEqual({(row["part_type"], row["id"]) for row in options + virtual},
                         {(row["part_type"], row["id"]) for row in result["names"]})
        self.assertTrue(all(row["status"] == "resolved" for row in result["names"]))
        by_key = {(row["part_type"], row["id"]): row for row in result["names"]}
        self.assertEqual("Rocket Bunny", by_key[("CarBody", 344100)]["manufacturer"])
        self.assertEqual("Widebody Kit", by_key[("CarBody", 344100)]["product"])
        self.assertEqual("Nissan", by_key[("ChassisStiffness", 344102)]["manufacturer"])
        self.assertEqual("Race Chassis Reinforcement / Roll Cage",
                         by_key[("ChassisStiffness", 344102)]["product"])
        for option in virtual:
            self.assertNotIn(option["id"], [row["id"] for row in options
                                           if row["part_type"] == "ChassisStiffness"])
            self.assertEqual("ChassisStiffness", option["part_type"])
            self.assertIs(option["requires_graphics"], False)
            self.assertIs(option["baseline"], False)
            self.assertIs(option["empty"], True)
            self.assertIs(option["reference_only"], result["reference_only"])
            self.assertEqual(0, option["declared_instance_count"])
            self.assertEqual("Nissan", by_key[("ChassisStiffness", option["id"])]["manufacturer"])
            self.assertEqual("Sport Chassis Reinforcement / Roll Cage",
                             by_key[("ChassisStiffness", option["id"])]["product"])
            for mesh in document.get("meshes", []):
                extras = mesh.get("extras", {})
                if extras.get("kfps_part_type") == "ChassisStiffness":
                    self.assertNotIn(option["id"], extras.get("kfps_part_option_ids", []))
        self.assertEqual(661353983, result["provenance"]["database_version"])
        self.assertIs(result["reference_only"], not result["same_build_verified"])
        if os.environ.get("KFPS_PART_NAMES_EXPECT_CURRENT") == "1":
            self.assertTrue(result["same_build_verified"])
            self.assertTrue(result["provenance"]["current"])
            self.assertIn("Installed cached", result["source"])
        self.assertIn({"parent_upgrade_id": 344001, "body_option_id": 344100},
                      result["body_compatibility"]["parent_map"])
        self.assertEqual(before, options)
        self.assertEqual(result, json.loads(json.dumps(result)))
        self.assertNotIn(str(ROOT), json.dumps(result))
        tracemalloc.start()
        subject.load_part_names(game, vehicle, options)
        _, python_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_after = process_memory()
        archive = game / "media/cars/NIS_FairladyZ_03.zip"
        with zipfile.ZipFile(archive) as bundle:
            member = bundle.getinfo("Manifest.xml")
            self.assertLess(member.file_size, 2 * 1024 * 1024)
            manifest = bundle.read(member)
        manifest_hash = hashlib.sha256(manifest).hexdigest()
        model_parts = {int(part.attrib["PartId"]): part.findall("Model")
                       for part in ET.fromstring(manifest).iter("UpgradeablePart")
                       if part.get("PartEnum") == "ChassisStiffness"}
        self.assertEqual({344000, 344002, 344100, 344102}, set(model_parts))
        self.assertEqual([], model_parts[344000])
        self.assertEqual([], model_parts[344100])
        self.assertTrue(model_parts[344002])
        self.assertTrue(model_parts[344102])

        from kfps_livery_lab.garage_build import effective_options, resolve_build
        fixtures_path = Path(os.environ.get("KFPS_PART_NAMES_BUILD_FIXTURES",
            str(ROOT / "runtime/garage-builds-20261102/body-fixtures.json")))
        fixtures = json.loads(fixtures_path.read_text(encoding="utf-8-sig"))
        captured = [row for row in fixtures["records"] if row["vehicle"] == vehicle
                    and row["garage_build"]["parts"]["ChassisStiffness"] == 344101]
        self.assertTrue(captured)
        merged = effective_options(options, result)
        for row in captured:
            build = row["garage_build"]
            with self.assertRaisesRegex(ValueError, "ChassisStiffness"):
                resolve_build(build, options, result["body_compatibility"])
            self.assertEqual(build["parts"], resolve_build(build, merged, result["body_compatibility"]))
        self.assertEqual(before, options)
        with tempfile.TemporaryDirectory(prefix="kfps-part-names-") as temporary:
            start = time.perf_counter()
            ordinary = subject.load_part_names(game, vehicle, options,
                reference_config=Path(temporary) / "absent-reference.json",
                cache_root=Path(temporary) / "empty-cache",
                reader_config=Path(temporary) / "absent-reader.json")
            ordinary_ms = (time.perf_counter() - start) * 1000
        self.assertEqual([], ordinary["names"])
        self.assertEqual([], ordinary["non_visual_options"])
        self.assertIsNone(ordinary["body_compatibility"])

        second_path = Path(os.environ.get("KFPS_PART_NAMES_SECOND_GLB",
            str(ROOT / "tools/livery-studio/runs/grouped-sections-20261021/cars/c4/prepared/mesh/vehicle.glb")))
        with second_path.open("rb") as stream:
            magic, version, total, size, chunk = struct.unpack("<4sIIII", stream.read(20))
            self.assertEqual((b"glTF", 2, 0x4e4f534a), (magic, version, chunk))
            self.assertLess(size, 16 * 1024 * 1024)
            second_document = json.loads(stream.read(size))
        second_options = second_document["scenes"][second_document.get("scene", 0)]["extras"]["kfps_part_options"]
        second_before = copy.deepcopy(second_options)
        second_vehicle = {"car_id": 4252, "model_code": "SUB_Impreza22BTG_98"}
        start = time.perf_counter()
        second = subject.load_part_names(game, second_vehicle, second_options)
        second_ms = (time.perf_counter() - start) * 1000
        self.assertEqual(second, subject.load_part_names(game, second_vehicle, second_options))
        self.assertEqual(11, len(second["names"]))
        self.assertEqual(second_before, second_options)
        self.assertEqual({(row["part_type"], row["id"]) for row in second_options},
                         {(row["part_type"], row["id"]) for row in second["names"]})
        self.assertEqual([], second["non_visual_options"])
        self.assertEqual([], second["body_compatibility"]["parent_map"])
        self.assertFalse(any(row["part_type"] == "CarBody" for row in second_options))
        for name in second["names"]:
            self.assertEqual("resolved", name["status"])
            self.assertEqual([], name["issues"])
            self.assertIsNotNone(name["product"])
            self.assertIsNotNone(name["category"])
        report = {"source": result["source"], "provenance": result["provenance"],
            "groups": sorted(FAMILIES), "resolved_options": len(result["names"]),
            "declared_options": len(options), "non_visual_options": virtual,
            "manifest_sha256": manifest_hash, "captured_builds_resolved": len(captured),
            "body_compatibility": result["body_compatibility"], "call_ms": times,
            "first_call_ms": times[0], "warm_median_ms": statistics.median(times[1:]),
            "two_call_warm_estimate_ms": statistics.median(times[1:]) * 2,
            "python_peak_bytes": python_peak, "process_before": memory_before,
            "process_after": memory_after, "same_build_verified": result["same_build_verified"],
            "ordinary_install_without_reader_or_reference": {"source": ordinary["source"],
                "name_count": len(ordinary["names"]), "non_visual_count": len(ordinary["non_visual_options"]),
                "call_ms": ordinary_ms},
            "second_car_cpu_only": {"vehicle": second_vehicle, "call_ms": second_ms,
                "declared_options": len(second_options), "names": second["names"],
                "non_visual_options": second["non_visual_options"],
                "reference_only": second["reference_only"], "warnings": second["warnings"]},
            "benchmark_scope": "First call and repeated calls in one process; filesystem cache uncontrolled; no persistent module cache"}
        output = os.environ.get("KFPS_PART_NAMES_REPORT")
        if output:
            Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("PART_NAMES_QUALIFICATION " + json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
