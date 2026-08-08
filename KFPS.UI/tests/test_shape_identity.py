import sys
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from tools.cgroup.shape_identity import (
    canonical_resource_for_word,
    normalize_game_key,
    resource_shape_word,
    target_game_shape_word,
)


class ShapeIdentityTests(unittest.TestCase):
    def test_upper_letter_symbol_slots_have_stable_shape_words(self):
        base_word = 1051477 & 0xFFFF
        self.assertEqual(base_word + 26, resource_shape_word("Upper_Letters_7", 27))
        self.assertEqual(base_word + 39, resource_shape_word("Upper_Letters_7", 40))
        self.assertIsNone(resource_shape_word("Upper_Letters_7", 41))

    def test_fh4_is_an_explicit_horizon_target(self):
        self.assertEqual("fh4", normalize_game_key("Forza Horizon 4"))

    def test_canonical_resource_identity_can_remap_for_motorsport(self):
        self.assertEqual(("Primitives", 23), canonical_resource_for_word(123))
        shape = {
            "type": 0x100000 + 2101,
            "type_word": 2101,
            "resource_family": "Community_Vinyls_1",
            "resource_index": 1,
        }
        self.assertEqual(2103, target_game_shape_word(shape, 2101, "fm"))

    def test_fh4_raw_word_is_preserved_only_when_targeting_fh4(self):
        shape = {
            "type": 0x100000 + 117,
            "type_word": 117,
            "resource_family": "Primitives",
            "resource_index": 5,
            "source_game": "fh4",
        }
        self.assertEqual(117, target_game_shape_word(shape, 105, "fh4"))
        self.assertEqual(105, target_game_shape_word(shape, 105, "fh5"))
        self.assertEqual(105, target_game_shape_word(shape, 105, "fh6"))


if __name__ == "__main__":
    unittest.main()
