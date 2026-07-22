import sys
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from tools.cgroup.shape_identity import resource_shape_word


class ShapeIdentityTests(unittest.TestCase):
    def test_upper_letter_symbol_slots_have_stable_shape_words(self):
        base_word = 1051477 & 0xFFFF
        self.assertEqual(base_word + 26, resource_shape_word("Upper_Letters_7", 27))
        self.assertEqual(base_word + 39, resource_shape_word("Upper_Letters_7", 40))
        self.assertIsNone(resource_shape_word("Upper_Letters_7", 41))


if __name__ == "__main__":
    unittest.main()
