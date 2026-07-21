from __future__ import annotations

import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))

from kfps_ui.theme_catalog import (  # noqa: E402
    NIGHT_CITY_2077_THEME,
    PUBLIC_THEME_NAMES,
    THEME_PRESETS,
)


PALETTE_DIR = UI / "qml" / "Kfps" / "Theme"
PALETTE = PALETTE_DIR / "PaletteNightCity2077.qml"
ASSET_DIR = UI / "assets" / "themes" / "night-city-2077"
FONT_DIR = UI / "assets" / "fonts" / "night-city-2077"
STRING_PROPERTY_RE = re.compile(
    r'^\s*readonly property string\s+(\w+):\s*"([^"]*)"', re.MULTILINE
)
BOOL_PROPERTY_RE = re.compile(
    r"^\s*readonly property bool\s+(\w+):\s*(true|false)", re.MULTILINE
)
COLOR_PROPERTY_RE = re.compile(
    r'^\s*readonly property color\s+(\w+):\s*"([^"]*)"', re.MULTILINE
)
REAL_PROPERTY_RE = re.compile(
    r"^\s*readonly property real\s+(\w+):\s*([0-9.]+)", re.MULTILINE
)


class NightCity2077ThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PALETTE.read_text(encoding="utf-8")
        cls.string_properties = dict(STRING_PROPERTY_RE.findall(cls.source))
        cls.bool_properties = {
            name: value == "true" for name, value in BOOL_PROPERTY_RE.findall(cls.source)
        }
        cls.color_properties = dict(COLOR_PROPERTY_RE.findall(cls.source))
        cls.real_properties = {
            name: float(value) for name, value in REAL_PROPERTY_RE.findall(cls.source)
        }

    def test_registry_marks_theme_as_public(self):
        presets = {preset.name: preset for preset in THEME_PRESETS}
        self.assertIn(NIGHT_CITY_2077_THEME, presets)
        self.assertFalse(presets[NIGHT_CITY_2077_THEME].supporter_only)
        self.assertIn(NIGHT_CITY_2077_THEME, PUBLIC_THEME_NAMES)
        self.assertFalse(self.bool_properties["supporterOnly"])
        self.assertFalse(self.bool_properties["supporterSignatureVisible"])
        self.assertEqual(self.string_properties["supporterSignatureText"], "")

    def test_palette_uses_documented_high_contrast_signal_colors(self):
        self.assertEqual(self.color_properties["backgroundA"], "#0e0e17")
        self.assertEqual(self.color_properties["signalPrimary"], "#f75049")
        self.assertEqual(self.color_properties["signalSecondary"], "#5ef6ff")
        self.assertEqual(self.color_properties["text"], "#ffffff")
        self.assertEqual(self.color_properties["muted"], "#d6d0d0")

    def test_angular_and_glitch_capabilities_are_explicit(self):
        for name in (
            "ambientScanEnabled",
            "controlSignalEnabled",
            "navSignalEnabled",
            "headerSignalEnabled",
            "angularControlsEnabled",
            "glitchInteractionsEnabled",
            "diagnosticEasterEggsEnabled",
            "technicalTypographyEnabled",
            "floatingPanelsEnabled",
            "glyphRailsEnabled",
            "customFrameExclusive",
        ):
            self.assertTrue(self.bool_properties[name], name)
        self.assertFalse(self.bool_properties["equipmentAccentsEnabled"])
        self.assertFalse(self.bool_properties["panelLocatorEnabled"])
        self.assertGreaterEqual(self.real_properties["angularCutSize"], 8.0)
        self.assertGreater(self.real_properties["glitchIntensity"], 0.0)
        self.assertEqual(self.real_properties["customFrameRadius"], 0.0)

    def test_custom_components_resolve_and_honor_motion_controls(self):
        shell = UI / "qml" / "shell"
        for token in (
            "backdropComponentFile",
            "foregroundComponentFile",
            "pageTransitionComponentFile",
        ):
            path = (shell / self.string_properties[token]).resolve()
            self.assertTrue(path.is_file(), token)
            source = path.read_text(encoding="utf-8")
            self.assertIn("Theme.reducedMotion", source, path.name)
            self.assertIn("screenshotMode", source, path.name)

        for token in ("backdropComponentFile", "foregroundComponentFile"):
            source = (shell / self.string_properties[token]).resolve().read_text(encoding="utf-8")
            self.assertIn("Theme.ambientMotion", source, token)

        backdrop = (shell / self.string_properties["backdropComponentFile"]).resolve().read_text(encoding="utf-8")
        self.assertIn("Theme.glassEffects", backdrop)
        self.assertIn("Theme.glitchInteractionsEnabled", backdrop)

    def test_background_scan_is_slow_and_low_intensity(self):
        backdrop = (
            UI / "qml" / "shell" / self.string_properties["backdropComponentFile"]
        ).resolve().read_text(encoding="utf-8")
        self.assertIn("opacity: 0.075", backdrop)
        self.assertIn("shadowOpacity: 0.20", backdrop)
        self.assertIn("duration: 7600", backdrop)
        self.assertIn("PauseAnimation { duration: 18400 }", backdrop)
        self.assertNotIn("duration: 2800", backdrop)

    def test_core_interactive_controls_use_the_angular_frame_contract(self):
        names = (
            "PrimaryButton.qml",
            "GhostButton.qml",
            "NavButton.qml",
            "KfpsTextField.qml",
            "KfpsTextArea.qml",
            "KfpsComboBox.qml",
            "KfpsCheckBox.qml",
            "KfpsSwitch.qml",
            "KfpsSlider.qml",
            "KfpsScrollBar.qml",
            "KfpsToolTip.qml",
        )
        for name in names:
            source = (UI / "qml" / "components" / name).read_text(encoding="utf-8")
            self.assertIn("AngularControlFrame", source, name)
            self.assertIn("Theme.angularControlsEnabled", source, name)

    def test_panel_hierarchy_avoids_duplicate_open_frame_ornaments(self):
        frame = (UI / "qml" / "components" / "AngularControlFrame.qml").read_text(
            encoding="utf-8"
        )
        panel = (UI / "qml" / "components" / "GlassPanel.qml").read_text(
            encoding="utf-8"
        )
        ticker = (UI / "qml" / "shell" / "AnnouncementTicker.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("property bool decorationVisible: true", frame)
        self.assertIn("property bool enclosedFrame", panel)
        self.assertIn("property bool technicalFrameVisible", panel)
        self.assertIn("enclosedFrame: Theme.angularControlsEnabled", ticker)
        self.assertNotIn("openPanel && !enclosedPanel\n                x: root.width", frame)

    def test_motion_capture_forces_live_status_without_persisting_it(self):
        app = (UI / "app.py").read_text(encoding="utf-8")
        motion_block = app.split(
            "if args.motion_capture_dir or args.motion_preview:", 1
        )[1].split("\n\n", 1)[0]
        self.assertIn('settings._data["liveStatusVisible"] = True', motion_block)
        self.assertNotIn("settings.liveStatusVisible = True", motion_block)

    def test_font_files_and_license_are_packaged(self):
        expected = {
            "uiFontFile": "Rajdhani-Medium.ttf",
            "displayFontFile": "Rajdhani-Bold.ttf",
            "monoFontFile": "Rajdhani-Regular.ttf",
        }
        for token, filename in expected.items():
            path = UI / "assets" / self.string_properties[token]
            self.assertEqual(path.name, filename)
            self.assertTrue(path.is_file(), token)
            self.assertEqual(path.read_bytes()[:4], b"\x00\x01\x00\x00", token)

        self.assertIn(
            "SIL OPEN FONT LICENSE Version 1.1",
            (FONT_DIR / "OFL.txt").read_text(encoding="utf-8"),
        )
        notice = (FONT_DIR / "FONT-NOTICE.txt").read_text(encoding="utf-8")
        self.assertIn("Rajdhani", notice)
        self.assertIn("https://github.com/google/fonts", notice)

    def test_theme_assets_are_local_scalable_and_original(self):
        references = {
            value
            for value in self.string_properties.values()
            if value.startswith("themes/night-city-2077/")
        }
        self.assertGreaterEqual(len(references), 4)
        for relative in references:
            self.assertNotIn("://", relative)
            self.assertTrue((UI / "assets" / relative).is_file(), relative)

        svg_paths = sorted(ASSET_DIR.glob("*.svg"))
        self.assertGreaterEqual(len(svg_paths), 5)
        for path in svg_paths:
            root = ET.parse(path).getroot()
            source = path.read_text(encoding="utf-8").lower()
            self.assertTrue(root.tag.endswith("svg"), path.name)
            self.assertNotIn("<text", source, path.name)
            self.assertNotRegex(source, r"(?:href|src)\s*=\s*[\"']https?://", path.name)
            self.assertNotIn("cd projekt", source, path.name)

        backdrop = ET.parse(ASSET_DIR / "night-city-backdrop.svg").getroot()
        view_box = [float(value) for value in backdrop.attrib["viewBox"].split()]
        self.assertGreaterEqual(view_box[2], 2560)
        self.assertGreaterEqual(view_box[3], 1440)

    def test_theme_payload_stays_small(self):
        payload = sum(path.stat().st_size for path in ASSET_DIR.iterdir() if path.is_file())
        payload += sum(path.stat().st_size for path in FONT_DIR.iterdir() if path.is_file())
        self.assertLess(payload, 2_000_000)

    def test_foreground_is_noninteractive(self):
        foreground = (
            UI / "qml" / "shell" / self.string_properties["foregroundComponentFile"]
        ).resolve()
        source = foreground.read_text(encoding="utf-8")
        for handler in (
            "MouseArea",
            "TapHandler",
            "HoverHandler",
            "DragHandler",
            "WheelHandler",
        ):
            self.assertNotIn(handler, source)


if __name__ == "__main__":
    unittest.main()
