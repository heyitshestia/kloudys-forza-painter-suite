from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))

from kfps_ui.settings_service import SettingsService  # noqa: E402
from kfps_ui.theme_catalog import (  # noqa: E402
    PUBLIC_THEME_NAMES,
    SUPPORTER_THEME_NAMES,
    WINDOWS_94_THEME,
    available_theme_names,
)


PALETTE_DIR = UI / "qml" / "Kfps" / "Theme"
PALETTE = PALETTE_DIR / "PaletteWindows94.qml"


class Windows94ThemeTests(unittest.TestCase):
    def test_windows94_is_supporter_only_and_persistent(self):
        self.assertNotIn(WINDOWS_94_THEME, PUBLIC_THEME_NAMES)
        self.assertIn(WINDOWS_94_THEME, SUPPORTER_THEME_NAMES)
        self.assertNotIn(WINDOWS_94_THEME, available_theme_names(False))
        self.assertIn(WINDOWS_94_THEME, available_theme_names(True))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsService(path)
            settings.reducedMotion = True
            settings.theme = WINDOWS_94_THEME
            reloaded = SettingsService(path)
            self.assertEqual(reloaded.theme, WINDOWS_94_THEME)
            self.assertFalse(reloaded.reducedMotion)
            self.assertFalse(reloaded.ambientMotion)
            self.assertFalse(reloaded.glassEffects)

            reloaded.ambientMotion = True
            reloaded.glassEffects = True
            persisted = SettingsService(path)
            self.assertTrue(persisted.ambientMotion)
            self.assertTrue(persisted.glassEffects)

    def test_palette_matches_the_classic_reference_contract(self):
        source = PALETTE.read_text(encoding="utf-8")
        expected = (
            'readonly property string name: "Windows 94"',
            "readonly property bool supporterOnly: true",
            "readonly property bool terminalMode: false",
            "readonly property bool classicMode: true",
            'property color face: "#c0c0c0"',
            'property color highlight: "#ffffff"',
            'property color bevelShadow: "#808080"',
            'property color navy: "#000080"',
            'property color desktop: "#008080"',
            'readonly property string iconFolder: "icons-windows94"',
            'readonly property string backdropComponentFile: "../themes/windows94/Windows94Backdrop.qml"',
            'readonly property string pageTransitionComponentFile: "../themes/windows94/Windows94PageTransition.qml"',
        )
        for declaration in expected:
            self.assertIn(declaration, source)

        for path in PALETTE_DIR.glob("Palette*.qml"):
            if path != PALETTE:
                self.assertIn(
                    "readonly property bool classicMode: false",
                    path.read_text(encoding="utf-8"),
                    path.name,
                )

    def test_font_and_original_recolored_icons_are_packaged(self):
        font_dir = UI / "assets" / "fonts" / "windows94"
        self.assertGreater((font_dir / "W95FA.otf").stat().st_size, 20_000)
        self.assertIn("SIL OPEN FONT LICENSE", (font_dir / "OFL.txt").read_text(encoding="utf-8"))
        self.assertTrue((font_dir / "FONT-NOTICE.txt").is_file())

        icon_dir = UI / "assets" / "icons-windows94"
        icons = sorted(icon_dir.glob("*.svg"))
        self.assertGreaterEqual(len(icons), 25)
        self.assertFalse(list(icon_dir.glob("*.png")))
        for path in icons:
            self.assertIn('stroke="#000000"', path.read_text(encoding="utf-8"), path.name)

    def test_shared_controls_use_classic_depth_and_focus_primitives(self):
        theme = (PALETTE_DIR / "Theme.qml").read_text(encoding="utf-8")
        main = (UI / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("readonly property bool classicMode: palette.classicMode", theme)
        self.assertIn("property string classicFontFamily", theme)
        self.assertIn("terminalMode || classicMode", theme)
        self.assertIn("W95FA.otf", main)

        bevel = (UI / "qml" / "components" / "ClassicBevel.qml").read_text(encoding="utf-8")
        focus = (UI / "qml" / "components" / "ClassicFocusRect.qml").read_text(encoding="utf-8")
        self.assertIn("sunken || pressed", bevel)
        self.assertIn("Theme.innerHighlight", bevel)
        self.assertIn("Theme.borderStrong", bevel)
        self.assertIn("visible: Theme.classicMode && active", focus)

        for relative in (
            "components/PrimaryButton.qml",
            "components/GhostButton.qml",
            "components/NavButton.qml",
            "components/KfpsTextField.qml",
            "components/KfpsComboBox.qml",
            "components/KfpsCheckBox.qml",
            "components/KfpsSlider.qml",
            "components/KfpsScrollBar.qml",
            "components/GlassPanel.qml",
            "shell/AppTitleBar.qml",
        ):
            source = (UI / "qml" / relative).read_text(encoding="utf-8")
            self.assertIn("ClassicBevel", source, relative)

    def test_theme_specific_motion_is_short_and_reduced_motion_safe(self):
        transition = (UI / "qml" / "themes" / "windows94" / "Windows94PageTransition.qml").read_text(
            encoding="utf-8"
        )
        palette = PALETTE.read_text(encoding="utf-8")
        self.assertIn("if (Theme.reducedMotion)", transition)
        self.assertIn("Theme.pageTransitionDuration", transition)
        self.assertIn("readonly property real pageTransitionDuration: 180", palette)


if __name__ == "__main__":
    unittest.main()
