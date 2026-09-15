from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from test_fm8_shape_mapping import LIBRARY_TABS
from fh6_import_typecode_json import load_font_registry, load_shapes, resolve_font_from_name, resolve_font_shape


class FontImportContractTests(unittest.TestCase):
    def test_every_named_font_slot_uses_verified_numeric_identity(self):
        payload = json.loads((ROOT / "data/fh6_font_registry.json").read_text(encoding="utf-8"))
        bases = dict(LIBRARY_TABS)
        self.assertEqual(877, len(payload["glyphs"]))
        self.assertEqual(3, len(payload["unnamed_slots"]))
        registry = load_font_registry()
        for row in payload["glyphs"]:
            expected = bases[row["resource_family"]] + row["resource_index"] - 1
            self.assertEqual(expected, row["fh6_shape_word"])
            self.assertEqual(expected, resolve_font_from_name(row["shape_name"], registry)["shape_word"], row)
            selected = resolve_font_shape({"font": row["font"], "glyph": row["glyph"], "block": row["block"]}, registry)
            self.assertEqual(expected, selected["shape_word"], row)

    def test_named_font_imports_reach_every_live_target_without_numeric_fields(self):
        rows = json.loads((ROOT / "data/fh6_font_registry.json").read_text(encoding="utf-8"))["glyphs"]
        shapes = [{"font_shape": row["shape_name"], "data": [i, -i, 0.5, 0.7, 30, 0.2, 0],
                   "color": [30, 60, 90, 255]} for i, row in enumerate(rows)]
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fonts.json"
            source.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
            for game in ("fh4", "fh5", "fh6", "fm8"):
                actual, skipped = load_shapes(source, target_game=game)
                self.assertEqual([], skipped)
                self.assertEqual([r["fh6_shape_word"] for r in rows], [s["shape_word"] for s in actual])

    def test_legacy_human_names_and_symbol_characters_are_distinct(self):
        registry = load_font_registry()
        expected = {"Dollar Sign": 2027, "Pound Sign": 2028, "Exclamation Mark": 1937,
                    "Question Mark": 1938, "Ampersand": 1940, "AE": 2031,
                    "Lower At Symbol": 2034, "Upper At Symbol": 1939}
        for name, word in expected.items():
            self.assertEqual(word, resolve_font_from_name("Forza Font 1 " + name, registry)["shape_word"], name)
        for char, word in (("$", 2027), ("%", 2037), (";", 2038), (":", 2039), ("@", 1939), ("\u00e6", 2031), ("\u00c6", 2031)):
            self.assertEqual(word, resolve_font_shape({"font": 1, "glyph": char}, registry)["shape_word"])
        self.assertIsNone(resolve_font_shape({"font": 6, "glyph": "@"}, registry))
        self.assertIsNone(resolve_font_shape({"font": 11, "glyph": "/"}, registry))


if __name__ == "__main__":
    unittest.main()
