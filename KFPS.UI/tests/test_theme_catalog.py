from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))

from kfps_ui.theme_catalog import (  # noqa: E402
    APEX_VECTOR_THEME,
    COMMAND_PROMPT_THEME,
    DEFAULT_THEME,
    OVERDRIVE_200X_THEME,
    PUBLIC_THEME_NAMES,
    SUPPORTER_THEME_NAMES,
    THEME_PRESETS,
    WINDOWS_94_THEME,
    available_theme_names,
    is_supporter_theme,
    normalize_theme,
)


PALETTE_DIR = UI / "qml" / "Kfps" / "Theme"
PROPERTY_RE = re.compile(r"^\s*readonly property\s+(\w+)\s+(\w+)\s*:", re.MULTILINE)
NAME_RE = re.compile(r'^\s*readonly property string name:\s*"([^"]+)"', re.MULTILINE)
SUPPORTER_RE = re.compile(r"^\s*readonly property bool supporterOnly:\s*(true|false)", re.MULTILINE)


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

    def test_recent_theme_entitlements_are_explicit(self):
        self.assertIn(DEFAULT_THEME, PUBLIC_THEME_NAMES)
        self.assertIn(COMMAND_PROMPT_THEME, PUBLIC_THEME_NAMES)
        self.assertIn(APEX_VECTOR_THEME, PUBLIC_THEME_NAMES)
        self.assertIn(WINDOWS_94_THEME, SUPPORTER_THEME_NAMES)
        self.assertIn(OVERDRIVE_200X_THEME, SUPPORTER_THEME_NAMES)

    def test_palette_metadata_matches_python_registry(self):
        qmldir = (PALETTE_DIR / "qmldir").read_text(encoding="utf-8")
        theme = (PALETTE_DIR / "Theme.qml").read_text(encoding="utf-8")

        self.assertEqual(len({preset.name for preset in THEME_PRESETS}), len(THEME_PRESETS))
        self.assertEqual(len({preset.qml_component for preset in THEME_PRESETS}), len(THEME_PRESETS))

        for preset in THEME_PRESETS:
            path = PALETTE_DIR / f"{preset.qml_component}.qml"
            self.assertTrue(path.is_file(), f"Missing palette file for {preset.name}: {path.name}")
            source = path.read_text(encoding="utf-8")
            name_match = NAME_RE.search(source)
            supporter_match = SUPPORTER_RE.search(source)
            self.assertIsNotNone(name_match, f"{path.name} has no literal name metadata")
            self.assertIsNotNone(supporter_match, f"{path.name} has no supporterOnly metadata")
            self.assertEqual(name_match.group(1), preset.name)
            self.assertEqual(supporter_match.group(1) == "true", preset.supporter_only)
            self.assertIn(f"{preset.qml_component} 1.0 {preset.qml_component}.qml", qmldir)
            self.assertIn(preset.qml_component, theme)

    def test_every_palette_implements_the_same_typed_contract(self):
        contracts: dict[str, dict[str, str]] = {}
        for preset in THEME_PRESETS:
            path = PALETTE_DIR / f"{preset.qml_component}.qml"
            properties = PROPERTY_RE.findall(path.read_text(encoding="utf-8"))
            contract = {name: property_type for property_type, name in properties}
            self.assertEqual(len(contract), len(properties), f"Duplicate palette token in {path.name}")
            contracts[preset.name] = contract

        baseline_name = THEME_PRESETS[0].name
        baseline = contracts[baseline_name]
        self.assertGreaterEqual(len(baseline), 180)
        for required in ("name", "supporterOnly", "iconFolder", "iconColorize", "iconTint"):
            self.assertIn(required, baseline)
        for name, contract in contracts.items():
            self.assertEqual(contract, baseline, f"{name} does not match the {baseline_name} token contract")

    def test_components_do_not_branch_on_concrete_theme_names(self):
        qml_root = UI / "qml"
        offenders: list[str] = []
        for path in qml_root.rglob("*.qml"):
            if path.parent == PALETTE_DIR:
                continue
            source = path.read_text(encoding="utf-8")
            concrete_branch_source = source.replace("Theme.activeThemeName", "")
            if "Theme.themeName" in source or re.search(r"Theme\.active[A-Z]\w+", concrete_branch_source):
                offenders.append(str(path.relative_to(qml_root)))
        self.assertEqual(offenders, [], f"Theme-specific component branches found: {offenders}")


if __name__ == "__main__":
    unittest.main()
