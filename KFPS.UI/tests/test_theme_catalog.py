from __future__ import annotations

import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))

from kfps_ui.theme_catalog import (  # noqa: E402
    DEFAULT_THEME,
    SUPPORTER_THEME_NAMES,
    available_theme_names,
    is_supporter_theme,
    normalize_theme,
)


class ThemeCatalogTests(unittest.TestCase):
    def test_unknown_theme_falls_back(self):
        self.assertEqual(normalize_theme("not real"), DEFAULT_THEME)

    def test_supporter_themes_are_hidden_until_unlocked(self):
        locked = available_theme_names(False)
        unlocked = available_theme_names(True)
        for name in SUPPORTER_THEME_NAMES:
            self.assertNotIn(name, locked)
            self.assertIn(name, unlocked)
            self.assertTrue(is_supporter_theme(name))
        self.assertFalse(is_supporter_theme("Unused Theme"))


if __name__ == "__main__":
    unittest.main()
