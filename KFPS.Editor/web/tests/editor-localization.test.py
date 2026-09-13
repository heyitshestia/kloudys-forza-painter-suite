"""Qt-independent tests for the desktop localization helper."""
from __future__ import annotations
import importlib.util
import json
import tempfile
import unittest
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.editor_manifest import MANIFEST, load_manifest, native_source
SPEC = importlib.util.spec_from_file_location(
    "editor_localization", native_source("localization", ROOT)
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EditorTranslator = MODULE.EditorTranslator
CATALOG_SPEC = importlib.util.spec_from_file_location("locale_manager", ROOT / load_manifest()["web_root"] / "locales/manage.py")
MANAGER = importlib.util.module_from_spec(CATALOG_SPEC)
CATALOG_SPEC.loader.exec_module(MANAGER)


class DesktopLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def translator(self, system="ko_KR", saved=None):
        pref = self.runtime / "preferences.json"
        if saved is None:
            pref.unlink(missing_ok=True)
        else:
            pref.write_text(json.dumps({"settings": {"kloudyFabricLanguage": saved}}), encoding="utf-8")
        return EditorTranslator(ROOT, self.runtime, system)

    def test_locale_selection(self):
        self.assertEqual(self.translator().language, "ko")
        self.assertEqual(self.translator("en_US").language, "en")
        self.assertEqual(self.translator("ko_KR", "en").language, "en")
        self.assertEqual(self.translator("en_US", "ko").language, "ko")

    def test_owned_dialogs(self):
        t = self.translator()
        for text in ["KFPS Vinyl Editor", "Reopen Editor", "Save before closing?", "This project has unsaved changes.", "Save", "Discard", "Cancel", "Close", "OK"]:
            self.assertNotEqual(t.tr(text), text, text)
        self.assertEqual(self.translator("en_US").tr("Save"), "Save")

    def test_opaque_names_and_unknown_diagnostics(self):
        t = self.translator()
        name = 'Save {1} 한국어 <&>'
        result = t.tr("Renamed layer to {0}.", name)
        self.assertIn(name, result)
        source = f'A project named "{name}" already exists. Choose a different name or open it before using Save.'
        self.assertIn(name, t.message(source))
        self.assertNotIn("already exists", t.message(source))
        self.assertEqual(t.message("New diagnostic: function_name() line 17"), "New diagnostic: function_name() line 17")

    def test_missing_catalog_and_corrupt_preferences(self):
        (self.runtime / "preferences.json").write_text("broken", encoding="utf-8")
        t = EditorTranslator(ROOT, self.runtime, "ko_KR")
        self.assertEqual(t.language, "ko")
        t = EditorTranslator(self.runtime / "missing", self.runtime, "ko_KR")
        self.assertEqual(t.tr("Save"), "Save")

    def test_english_catalog_values_and_missing_korean_fallback(self):
        manifest = load_manifest()
        manifest_path = self.runtime / MANIFEST.relative_to(ROOT)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        locale_root = self.runtime / manifest["web_root"] / "locales"
        locale_root.mkdir(parents=True)
        (locale_root / "en.json").write_text(json.dumps({"messages": {"Save": "Save project"}}), encoding="utf-8")
        (locale_root / "ko.json").write_text(json.dumps({"messages": {"Save": ""}}), encoding="utf-8")
        self.assertEqual(EditorTranslator(self.runtime, self.runtime, "ko").tr("Save"), "Save project")
        self.assertEqual(EditorTranslator(self.runtime, self.runtime, "en").tr("Save"), "Save project")


class CatalogMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.catalogs = {code: MANAGER.read_catalog(code) for code in ("en", "ko")}

    def test_current_catalogs_and_source_keys(self):
        self.assertEqual(MANAGER.validate(self.catalogs), [])

    def test_missing_translation_fails_but_draft_can_fall_back(self):
        self.catalogs["ko"]["messages"]["Save"] = ""
        self.assertTrue(MANAGER.validate(self.catalogs))
        self.assertEqual(MANAGER.validate(self.catalogs, allow_missing=True), [])

    def test_lost_placeholder_or_modified_html_contract_fails(self):
        bad = copy.deepcopy(self.catalogs)
        bad["ko"]["messages"]["Renamed layer to {0}."] = "No name"
        self.assertTrue(any("placeholder mismatch" in error for error in MANAGER.validate(bad)))
        key = next(iter(self.catalogs["ko"]["html"]))
        self.catalogs["ko"]["html"][key] += '<a href="https://example.invalid">external</a>'
        self.assertTrue(any("HTML structure" in error for error in MANAGER.validate(self.catalogs)))


if __name__ == "__main__":
    unittest.main()
