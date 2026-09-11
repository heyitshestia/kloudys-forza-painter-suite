from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
ASSETS = UI / "assets" / "themes" / "rx93-psycho-frame"
QML = UI / "qml" / "themes" / "rx93"
PALETTE = UI / "qml" / "Kfps" / "Theme" / "PaletteRx93PsychoFrame.qml"
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import PUBLIC_THEME_NAMES, RX93_PSYCHO_FRAME_THEME


def contrast(first, second):
    def luminance(value):
        channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


class Rx93ThemeTests(unittest.TestCase):
    def test_theme_is_selectable_and_persists(self):
        self.assertIn(RX93_PSYCHO_FRAME_THEME, PUBLIC_THEME_NAMES)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsService(path)
            settings.theme = RX93_PSYCHO_FRAME_THEME
            self.assertEqual(SettingsService(path).theme, RX93_PSYCHO_FRAME_THEME)

    def test_palette_assets_and_components_exist(self):
        source = PALETTE.read_text(encoding="utf-8")
        for relative in re.findall(r'property string \w+File: "([^"]+)"', source):
            path = (UI / "qml" / "shell" / relative) if relative.endswith(".qml") else UI / "assets" / relative
            self.assertTrue(path.is_file(), relative)

    def test_theme_owned_art_and_materials_are_distinct(self):
        names = ("parts/chassis.png", "parts/navy-key.png", "parts/ceramic-key.png", "parts/inset-panel.png")
        digests = {hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() for name in names}
        self.assertEqual(len(digests), 4)
        for source in QML.glob("*.qml"):
            text = source.read_text(encoding="utf-8")
            for relative in re.findall(r'/themes/([^/]+)/', text):
                self.assertEqual(relative, "rx93-psycho-frame", source.name)
            self.assertNotIn("Canvas {", text)
            self.assertNotIn("MultiEffect {", text)

    def test_licensed_files_match_provenance(self):
        manifest = json.loads((ASSETS / "external-assets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), 35)
        for record in manifest["files"]:
            self.assertEqual(hashlib.sha256((ASSETS / record["file"]).read_bytes()).hexdigest(), record["sha256"])
            self.assertIn("raw.githubusercontent.com/", record["source"])
        for path in (ASSETS / "icons").glob("*.svg"):
            self.assertEqual(ET.parse(path).getroot().get("stroke"), "#ffffff")
        ET.parse(ASSETS / "rx93-mark.svg")

    def test_asset_payload_under_ten_mib(self):
        self.assertLess(sum(p.stat().st_size for p in ASSETS.rglob("*") if p.is_file()), 10 * 1024 * 1024)

    def test_ambient_motion_obeys_accessibility_and_window_state(self):
        for name in ("Rx93Foreground.qml", "Rx93SidebarHeader.qml"):
            source = (QML / name).read_text(encoding="utf-8")
            for guard in ("Theme.ambientMotion", "!Theme.reducedMotion", "!screenshotMode", "Window.window.active", "Window.Minimized", "running: root.motionAllowed"):
                self.assertIn(guard, source, name)
            self.assertIn("interval: 50", source)
        self.assertNotIn("Animation {", (QML / "Rx93Backdrop.qml").read_text(encoding="utf-8"))
        self.assertIn("enabled: false", (QML / "Rx93Foreground.qml").read_text(encoding="utf-8"))

    def test_small_text_and_control_boundaries_have_contrast(self):
        palette = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', PALETTE.read_text(encoding="utf-8")))
        for token in ("text", "muted", "subtle"):
            self.assertGreaterEqual(contrast(palette[token], "#283234"), 4.5, token)
        self.assertGreaterEqual(contrast(palette["primaryButtonText"], "#8d9f92"), 4.5)
        self.assertGreaterEqual(contrast(palette["borderSoft"], "#152023"), 3)
        self.assertGreaterEqual(contrast(palette["focusColor"], "#283234"), 3)
        for token in ("comboHighlight", "helpCategorySelected", "helpTopicSelected", "helpBadgeSelected", "checkboxCheckedSurface"):
            self.assertGreaterEqual(contrast(palette["primaryText"], palette[token]), 4.5, token)

    def test_old_palettes_leave_new_hooks_empty(self):
        for path in PALETTE.parent.glob("Palette*.qml"):
            if path == PALETTE:
                continue
            source = path.read_text(encoding="utf-8")
            for hook in ("controlSurfaceComponentFile", "panelSurfaceComponentFile", "sidebarSurfaceComponentFile", "sidebarHeaderComponentFile", "titleBarContentComponentFile"):
                self.assertIn(f'property string {hook}: ""', source, path.name)
            self.assertIn('property var chromeMetrics: ({})', source)

    def test_custom_buttons_do_not_construct_legacy_decoration(self):
        for name in ("PrimaryButton.qml", "GhostButton.qml", "NavButton.qml"):
            source = (UI / "qml/components" / name).read_text(encoding="utf-8")
            self.assertIn("id: legacySurface", source)
            self.assertIn("sourceComponent: Component", source)
            self.assertIn("active: Theme.controlSurfaceComponentFile.length === 0 || customSurface.status === Loader.Error", source)
            self.assertIn("ThemeSurface {", source)

    def test_window_controls_stay_in_upper_armor_strip(self):
        palette = PALETTE.read_text(encoding="utf-8")
        for setting in ("windowButtonsTopInset: 3", "compactWindowButtonsTopInset: 0", "windowButtonsHeight: 30", "compactWindowButtonsIconLift: 8"):
            self.assertIn(setting, palette)
        source = (UI / "qml/shell/AppTitleBar.qml").read_text(encoding="utf-8")
        self.assertIn('Theme.chromeMetric("windowButtonsHeight"', source)
        self.assertIn('"compactWindowButtonsTopInset", Theme.classicMode ? 3 : 0', source)
        self.assertIn("anchors.top: parent.top", source)
        self.assertIn('"compactWindowButtonsIconLift", 0', source)

    def test_no_photographic_backdrop_or_rejected_parts(self):
        for source in QML.glob("*.qml"):
            self.assertNotIn("drydock.png", source.read_text(encoding="utf-8"))
        self.assertFalse((ASSETS / "drydock.png").exists())

    def test_modular_surface_and_brand_assets(self):
        source = (UI / "qml/components/ThemeSurface.qml").read_text(encoding="utf-8")
        self.assertIn("property string componentFile", source)
        self.assertIn("property var surfaceOwner", source)
        self.assertNotIn("rx93", source.lower())
        ET.parse(ASSETS / "kfps-armored-wordmark.svg")

    def test_all_literal_native_glyph_names_are_present(self):
        names = set()
        for path in (UI / "qml").rglob("*.qml"):
            names.update(re.findall(r'(?:iconName|name): "([a-z][a-z0-9-]*)"', path.read_text(encoding="utf-8")))
        for name in names:
            self.assertTrue((ASSETS / "icons" / (name + ".svg")).is_file(), name)


if __name__ == "__main__":
    unittest.main()
