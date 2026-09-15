from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from fh6_import_typecode_json import load_shapes
from kfps_shapes.resources import resolve_vinyl_resource
from test_fm8_shape_mapping import LIBRARY_TABS, library_shapes
from tools.cgroup.cgroup_codec import build_flat_payload, layer_from_shape
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.shape_identity import (
    canonical_shape_identity, canonicalize_shape, resource_shape_word,
    target_game_shape_word,
)


class CrossGameShapeContractTests(unittest.TestCase):
    def test_catalog_words_match_all_frozen_native_slots(self):
        words = json.loads((ROOT / "KFPS.Editor/web/shape-words.json").read_text())["families"]
        for family, base in LIBRARY_TABS:
            self.assertEqual({str(i): base + i - 1 for i in range(1, 41)}, words[family], family)

    def test_lowercase_and_symbol_resources_are_not_special_cased_out(self):
        for family, base in LIBRARY_TABS:
            for slot in range(1, 41):
                self.assertEqual(base + slot - 1, resource_shape_word(family, slot))
        for slot in (0, 41, "not a slot", True):
            self.assertIsNone(resource_shape_word("Lower_Letters_1", slot))

    def test_known_numeric_identity_wins_over_stale_labels(self):
        for family, base in LIBRARY_TABS:
            for slot in range(1, 41):
                word = base + slot - 1
                shape = {"type": 0x100000 + word, "type_word": word,
                         "resource_family": "Upper_Letters_6", "resource_index": 13}
                before = copy.deepcopy(shape)
                identity = canonical_shape_identity(shape)
                self.assertEqual(word, identity.word, (family, slot))
                for game in ("fh4", "fh5", "fh6", "fm8"):
                    self.assertEqual(word, target_game_shape_word(shape, identity.word, game))
                normalized, _ = canonicalize_shape(shape)
                self.assertEqual((family, slot), (normalized["resource_family"], normalized["resource_index"]))
                self.assertEqual(before, shape)

    def test_invalid_metadata_does_not_break_valid_numeric_shapes(self):
        for index in ("invalid", {}, [], True, 0, 41):
            shape = {"type": 0x100000 + 3513, "resource_family": "Lower_Letters_1", "resource_index": index}
            self.assertEqual(3513, canonical_shape_identity(shape).word)

    def test_unknown_explicit_words_are_preserved_not_relabelled(self):
        shape = {"type": 0x100000 + 65000, "type_word": 65000,
                 "resource_family": "Primitives", "resource_index": 1}
        self.assertEqual(65000, canonical_shape_identity(shape).word)
        for game in ("fh4", "fh5", "fh6", "fm8"):
            self.assertEqual(65000, target_game_shape_word(shape, 65000, game))
        self.assertEqual(2001, canonical_shape_identity(
            {"resourceFamily": "Lower_Letters_1", "resourceIndex": "1"}).word)

    def test_full_native_type_wins_over_stale_numeric_aliases_like_the_editor(self):
        shapes = []
        expected = []
        for family, base in LIBRARY_TABS:
            for slot in range(1, 41):
                word = base + slot - 1
                item = {"type": 0x100000 + word, "type_word": 121, "shape_word": 122,
                        "resource_family": "Primitives", "resource_index": 21,
                        "data": [0, 0, 1, 1, 0, 0, 0], "color": [1, 2, 3, 255]}
                self.assertEqual(word, canonical_shape_identity(item).word)
                self.assertEqual((family, slot), resolve_vinyl_resource(item["type"], item))
                shapes.append(item)
                expected.append(word)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "conflicting.json"
            path.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
            for game in ("fh4", "fh5", "fh6", "fm8"):
                live, skipped = load_shapes(path, allow_unknown_low_byte=True, target_game=game)
                self.assertEqual([], skipped)
                self.assertEqual(expected, [s["shape_word"] for s in live])
                self.assertEqual(expected, [layer_from_shape(s, i, game).shape_id for i, s in enumerate(shapes)])

    def test_complete_library_decode_then_prepare_every_game(self):
        shapes = library_shapes(metadata=True)
        shapes[-1]["mask"] = True
        shapes[-1]["data"][6] = 1
        expected = [s["type_word"] for s in shapes]
        resources = [(family, slot) for family, _ in LIBRARY_TABS for slot in range(1, 41)]
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "data"
            source = Path(temp) / "decoded.json"
            for source_game in ("fh4", "fh5", "fh6", "fm8"):
                raw.write_bytes(build_flat_payload(
                    layer_from_shape(s, i, target_game=source_game) for i, s in enumerate(shapes)))
                decoded = decode_forza_source(raw, game=source_game)
                self.assertEqual(expected, [s["type_word"] for s in decoded.layers])
                self.assertEqual(resources, [(s.get("resource_family"), s.get("resource_index"))
                                             for s in decoded.layers], source_game)
                self.assertEqual([s["mask"] for s in shapes], [s["mask"] for s in decoded.layers])
                self.assertEqual([], decoded.report["warnings"])
                source.write_text(json.dumps({"shapes": decoded.layers}), encoding="utf-8")
                for target_game in ("fh4", "fh5", "fh6", "fm8"):
                    with self.subTest(source=source_game, target=target_game):
                        live, skipped = load_shapes(source, allow_unknown_low_byte=True, target_game=target_game)
                        self.assertEqual([], skipped)
                        self.assertEqual(expected, [s["shape_word"] for s in live])
                        offline = [layer_from_shape(s, i, target_game=target_game)
                                   for i, s in enumerate(decoded.layers)]
                        self.assertEqual(expected, [s.shape_id for s in offline])
                        for original, prepared, encoded, resource in zip(shapes, live, offline, resources):
                            self.assertEqual(resource, resolve_vinyl_resource(original["type"], original))
                            self.assertEqual(original["data"][:6], [prepared[k] for k in ("x", "y", "sx", "sy", "rotation", "skew")])
                            self.assertEqual(original["color"], prepared["color"])
                            self.assertEqual(original["mask"], encoded.mask)


if __name__ == "__main__":
    unittest.main()
