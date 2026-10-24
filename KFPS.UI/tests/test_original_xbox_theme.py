from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import ORIGINAL_XBOX_THEME, PUBLIC_THEME_NAMES
from test_rx93_theme import contrast

PALETTE = UI / "qml/Kfps/Theme/PaletteOriginalXbox.qml"
COMPONENTS = UI / "qml/themes/xbox"


class OriginalXboxTests(unittest.TestCase):
    def test_public_theme_and_settings_restart(self):
        self.assertIn(ORIGINAL_XBOX_THEME, PUBLIC_THEME_NAMES)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            settings = SettingsService(path)
            settings.theme = ORIGINAL_XBOX_THEME
            self.assertEqual(SettingsService(path).theme, ORIGINAL_XBOX_THEME)
            settings.theme = "Night Blossom"
            self.assertEqual(SettingsService(path).theme, "Night Blossom")

    def test_asset_and_component_paths(self):
        for relative in re.findall(r'property string \w+File: "([^"]+)"', PALETTE.read_text()):
            path = UI / "qml/shell" / relative if relative.endswith(".qml") else UI / "assets" / relative
            self.assertTrue(path.is_file(), relative)

    def test_controls_and_text_contrast(self):
        palette = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', PALETTE.read_text()))
        for foreground in ("text", "muted", "subtle"):
            for background in ("surface", "surfaceStrong", "surfaceRaised", "ghostHoverSurface"):
                self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 4.5, (foreground, background))
        for background in ("primaryButtonTop", "primaryButtonMiddle", "primaryButtonBottom", "navActiveBottom", "comboHighlight"):
            self.assertGreaterEqual(contrast(palette["primaryText"], palette[background]), 4.5, background)
        self.assertGreaterEqual(contrast(palette["focusColor"], palette["surfaceRaised"]), 3)

    def test_surfaces_use_theme_tokens_and_bounded_motion(self):
        for file in COMPONENTS.glob("*.qml"):
            source = file.read_text()
            self.assertNotRegex(source, r'#[0-9a-fA-F]{3,8}', file.name)
            for heavyweight in ("ShaderEffect {", "MultiEffect {", "loops: Animation.Infinite"):
                self.assertNotIn(heavyweight, source, file.name)
            if file.name != "XboxMotionClock.qml":
                self.assertNotIn("Timer {", source, file.name)
        self.assertIn("!Theme.reducedMotion", (COMPONENTS / "XboxControlSurface.qml").read_text())
        clock = (COMPONENTS / "XboxMotionClock.qml").read_text()
        for gate in ("Theme.ambientMotion", "!Theme.reducedMotion", "!screenshotMode", "applicationActive", "windowVisible", "requested && visible"):
            self.assertIn(gate, clock)
        self.assertIn("Math.min(960, root.width)", (COMPONENTS / "XboxBackdrop.qml").read_text())
        self.assertIn("Math.min(384, root.width)", (COMPONENTS / "XboxReactor.qml").read_text())

    def test_medallion_is_transparent_and_small_enough(self):
        from PIL import Image
        for name in ("medallion.png", "core.png"):
            path = UI / "assets/themes/original-xbox" / name
            with Image.open(path) as image:
                self.assertEqual(image.mode, "RGBA")
                self.assertLessEqual(image.getpixel((0, 0))[3], 1)  # Allow one alpha quantization step.
            self.assertLess(path.stat().st_size, 5 * 1024 * 1024)

    def test_depth_and_primary_navigation_are_theme_scoped(self):
        palette = PALETTE.read_text()
        self.assertIn("dashboardNavigation: 1", palette)
        sidebar = (UI / "qml/shell/Sidebar.qml").read_text()
        self.assertIn('Theme.chromeMetric("dashboardNavigation", 0)', sidebar)
        self.assertIn("visible: !root.dashboardNavigation", sidebar)
        dashboard = (COMPONENTS / "XboxDashboard.qml").read_text()
        self.assertIn("FocusScope {", dashboard)
        self.assertNotIn("Overlay.overlay", dashboard)
        self.assertNotIn("Popup {", dashboard)
        self.assertIn("parent: navigation ? navigation.parent : null", dashboard)
        self.assertIn("if (hasEnteredWorkspace) close()", dashboard)
        self.assertNotIn("FORZA PAINTER SUITE", dashboard)
        self.assertIn('root.choose("credits")', dashboard)
        reactor = (COMPONENTS / "XboxReactor.qml").read_text()
        self.assertIn('original-xbox/core.png', reactor)
        self.assertIn('clock.seconds, false', reactor)
        self.assertIn('clock.seconds, true', reactor)


if __name__ == "__main__":
    unittest.main()
