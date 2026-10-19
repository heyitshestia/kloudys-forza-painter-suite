"""Japanese catalog contracts, without launching a browser or native window."""
from collections import Counter
import copy
import ast
from contextlib import redirect_stdout, redirect_stderr
import io
import importlib.util
import re
from pathlib import Path
import unittest
from unittest.mock import patch

LOCALES = Path(__file__).resolve().parents[1] / "locales"
SPEC = importlib.util.spec_from_file_location("locale_manager_ja", LOCALES / "manage.py")
MANAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MANAGER)
TECHNICAL_CAPTIONS = {
    "- Kloudy", "{0} ms", "{0} MiB", "Control", "Delete / Backspace", "HTTP {0}",
    "OK", "Shift+L", "shape-names HTTP {0}", "shape-words HTTP {0}", "#FFFFFF",
    "#ffffff", ".fabric-project.json", "Ctrl", "Ctrl+D", "Ctrl+Z / Ctrl+Y", "F",
    "G", "I", "M", "O", "P", "R", "S", "Shift", "Shift+F", "T", "V", "X",
    "Y", "x 0, y 0", "Livery Studio",
}


class JapaneseCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogs = {code: MANAGER.read_catalog(code) for code in ("en", "ko", "ja")}

    def test_language_registered_and_metadata(self):
        self.assertIn("ja", MANAGER.LANGUAGES)
        self.assertEqual(self.catalogs["ja"]["locale"], "ja")
        self.assertEqual(self.catalogs["ja"]["name"], "日本語")

    def test_all_sections_have_exact_keys_and_nonempty_translations(self):
        for section in MANAGER.SECTIONS:
            self.assertEqual(set(self.catalogs["ja"][section]), set(self.catalogs["en"][section]))
            for key, value in self.catalogs["ja"][section].items():
                self.assertIsInstance(value, str, key)
                self.assertTrue(value.strip(), key)
                self.assertNotIn("\ufffd", value, key)

    def test_structural_validation_with_source_inventory_checked_separately(self):
        # Source wiring is independently gated by manage.py check; this isolates catalog defects.
        with patch.object(MANAGER, "source_messages", return_value=set()):
            self.assertEqual(MANAGER.validate(self.catalogs), [])

    def test_current_redesign_labels_in_all_three_languages(self):
        # The existing extractor does not understand the redesign's local t alias.
        # Review dynamic button/menu labels explicitly; never treat IDs as UI text.
        labels = {"Reset workspace", "File", "Edit", "View", "Help", "Float panel",
                  "Dock left", "Dock right", "Close panel"}
        for filename in ("editor-workspace.js", "editor-docking.js"):
            source = (LOCALES.parent / filename).read_text(encoding="utf-8")
            for match in re.finditer(r"\b(?:t|control)\(\s*('(?:\\.|[^'\\])*')", source):
                labels.add(ast.literal_eval(match[1]))
        self.assertGreaterEqual(len(labels), 25)
        for code, catalog in self.catalogs.items():
            for key in labels:
                self.assertTrue(catalog["messages"].get(key), f"{code}: {key}")

    def test_current_source_inventory(self):
        self.assertEqual(MANAGER.source_messages() - set(self.catalogs["en"]["messages"]), set())

    def test_placeholder_multiplicity_and_documented_plural_omissions(self):
        ja = self.catalogs["ja"]
        for section in MANAGER.SECTIONS:
            for key, value in ja[section].items():
                before = Counter(re.findall(r"\{(\d+)\}", key))
                after = Counter(re.findall(r"\{(\d+)\}", value))
                for slot in ja["pluralOmissions"].get(key, []):
                    self.assertRegex(key, rf"(?:layer|guide|project|JSON|problem)\{{{slot}\}}")
                    before.pop(str(slot))
                self.assertEqual(before, after, f"{section}: {key}")

    def test_no_untranslated_english_prose_or_catalog_fallbacks(self):
        for section in MANAGER.SECTIONS:
            for key, value in self.catalogs["ja"][section].items():
                if section == "messages" and key in TECHNICAL_CAPTIONS:
                    self.assertEqual(value, self.catalogs["en"][section][key])
                else:
                    self.assertRegex(value, r"[\u3040-\u30ff\u3400-\u9fff]", key)
                    self.assertNotEqual(value, self.catalogs["en"][section][key], key)

    def test_pack_is_reproducible_and_matches_json(self):
        self.assertEqual((LOCALES / "ja.js").read_text(encoding="utf-8"),
                         MANAGER.pack("ja", self.catalogs["ja"]))

    def test_family_and_font_identifiers_are_not_translated_in_keys(self):
        ja = self.catalogs["ja"]
        self.assertEqual(len(ja["families"]), 35)
        self.assertEqual(len(ja["shapeLabels"]), 764)
        self.assertEqual(ja["families"]["Upper_Letters_11"], "大文字 11")
        for number in range(1, 12):
            for case, caption in (("Upper", "大文字"), ("Lower", "小文字")):
                for glyph in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    key = f"Forza Font {number} {case} {glyph}"
                    self.assertEqual(ja["shapeLabels"][key], f"Forza フォント {number} {caption} {glyph}")

    def test_missing_japanese_translation_fails(self):
        catalogs = copy.deepcopy(self.catalogs)
        catalogs["ja"]["messages"]["Save"] = ""
        with patch.object(MANAGER, "source_messages", return_value=set()):
            self.assertTrue(any("missing translation" in error for error in MANAGER.validate(catalogs)))

    def test_lost_user_value_placeholder_fails(self):
        catalogs = copy.deepcopy(self.catalogs)
        catalogs["ja"]["messages"]["Renamed layer to {0}."] = "レイヤー名を変更しました。"
        with patch.object(MANAGER, "source_messages", return_value=set()):
            self.assertTrue(any("placeholder mismatch" in error for error in MANAGER.validate(catalogs)))

    def test_modified_shortcut_markup_fails(self):
        catalogs = copy.deepcopy(self.catalogs)
        key = next(key for key in catalogs["ja"]["html"] if 'data-shortcut-label="makeMask"' in key)
        catalogs["ja"]["html"][key] = catalogs["ja"]["html"][key].replace('"makeMask"', '"delete"')
        with patch.object(MANAGER, "source_messages", return_value=set()):
            self.assertTrue(any("HTML structure" in error for error in MANAGER.validate(catalogs)))

    def test_sync_adds_both_locales_without_replacing_existing_translations(self):
        catalogs = copy.deepcopy(self.catalogs)
        writes = {}
        with patch.object(MANAGER, "read_catalog", side_effect=lambda code: catalogs[code]), \
                patch.object(MANAGER, "write_catalog", side_effect=lambda code, data: writes.update({code: data})), \
                patch.object(MANAGER, "source_messages", return_value={"Synthetic new UI message"}), \
                patch.object(MANAGER.sys, "argv", ["manage.py", "sync"]), redirect_stdout(io.StringIO()):
            self.assertEqual(MANAGER.main(), 0)
        self.assertEqual(writes["en"]["messages"]["Synthetic new UI message"], "Synthetic new UI message")
        for code in ("ko", "ja"):
            self.assertEqual(writes[code]["messages"]["Synthetic new UI message"], "")
            self.assertEqual(writes[code]["messages"]["Save"], self.catalogs[code]["messages"]["Save"])

    def test_language_build_only_writes_selected_pack(self):
        with patch.object(MANAGER, "read_catalog", side_effect=lambda code: self.catalogs[code]), \
                patch.object(MANAGER.sys, "argv", ["manage.py", "build", "--language", "ja"]), \
                patch.object(Path, "write_text", autospec=True) as write, redirect_stdout(io.StringIO()):
            self.assertEqual(MANAGER.main(), 0)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(write.call_args.args[0], LOCALES / "ja.js")
        self.assertEqual(write.call_args.args[1], MANAGER.pack("ja", self.catalogs["ja"]))

    def test_check_cannot_skip_other_languages(self):
        with patch.object(MANAGER.sys, "argv", ["manage.py", "check", "--language", "ja"]), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            MANAGER.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
