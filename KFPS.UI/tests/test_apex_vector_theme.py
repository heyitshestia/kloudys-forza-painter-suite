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
    APEX_VECTOR_THEME,
    PUBLIC_THEME_NAMES,
    THEME_PRESETS,
)


PALETTE_DIR = UI / "qml" / "Kfps" / "Theme"
PALETTE = PALETTE_DIR / "PaletteApexVector.qml"
ASSET_DIR = UI / "assets" / "themes" / "apex-vector"
FONT_DIR = UI / "assets" / "fonts" / "apex-vector"
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


class ApexVectorThemeTests(unittest.TestCase):
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

    def test_registry_marks_apex_vector_as_public(self):
        presets = {preset.name: preset for preset in THEME_PRESETS}
        self.assertIn(APEX_VECTOR_THEME, presets)
        self.assertFalse(presets[APEX_VECTOR_THEME].supporter_only)
        self.assertIn(APEX_VECTOR_THEME, PUBLIC_THEME_NAMES)
        self.assertFalse(self.bool_properties["supporterOnly"])
        self.assertFalse(self.bool_properties["supporterSignatureVisible"])
        self.assertEqual(self.string_properties["supporterSignatureText"], "")

    def test_custom_components_resolve_and_observe_motion_contract(self):
        shell = UI / "qml" / "shell"
        for token in (
            "backdropComponentFile",
            "foregroundComponentFile",
            "pageTransitionComponentFile",
        ):
            relative = self.string_properties[token]
            path = (shell / relative).resolve()
            self.assertTrue(path.is_file(), token)
            source = path.read_text(encoding="utf-8")
            self.assertIn("Theme.reducedMotion", source, path.name)
            self.assertIn("screenshotMode", source, path.name)

        for token in ("backdropComponentFile", "foregroundComponentFile"):
            source = (shell / self.string_properties[token]).resolve().read_text(encoding="utf-8")
            self.assertIn("Theme.ambientMotion", source, token)

    def test_flat_surfaces_replace_old_instrument_decorations(self):
        for name in (
            "equipmentAccentsEnabled",
            "ambientScanEnabled",
            "controlSignalEnabled",
            "navSignalEnabled",
            "panelLocatorEnabled",
            "headerSignalEnabled",
        ):
            self.assertFalse(self.bool_properties[name], name)
        self.assertTrue(self.bool_properties["customFrameExclusive"])
        self.assertLessEqual(self.real_properties["customFrameRadius"], 3.0)
        for token in ("titleBarContentComponentFile", "controlSurfaceComponentFile",
                      "panelSurfaceComponentFile", "sidebarSurfaceComponentFile",
                      "sidebarHeaderComponentFile"):
            self.assertTrue((UI / "qml/components" / self.string_properties[token]).resolve().is_file(), token)
        self.assertIn("dashboardNavigation: 1", self.source)

    def test_visual_contract_is_flat_and_high_chroma(self):
        self.assertFalse(self.bool_properties["glassBackdropEnabled"])
        for name in (
            "panelNoiseSoftOpacity",
            "panelNoiseOpacity",
            "panelNoiseStrongOpacity",
            "panelHighlightSoftOpacity",
            "panelHighlightOpacity",
            "panelHighlightStrongOpacity",
            "panelOverlaySoftOpacity",
            "panelOverlayOpacity",
            "panelRefractionOpacity",
            "buttonGlassBackdropOpacity",
            "buttonGlassLensOpacity",
        ):
            self.assertEqual(self.real_properties[name], 0.0, name)

        self.assertEqual(self.real_properties["customFrameRadius"], 0.0)
        self.assertEqual(self.color_properties["signalPrimary"], "#d80c26")
        self.assertEqual(self.color_properties["signalSecondary"], "#00c8e5")
        self.assertEqual(
            {
                self.color_properties["primaryButtonTop"],
                self.color_properties["primaryButtonMiddle"],
                self.color_properties["primaryButtonBottom"],
            },
            {"#d80c26"},
        )
        self.assertEqual(
            {
                self.color_properties["navActiveTop"],
                self.color_properties["navActiveMiddle"],
                self.color_properties["navActiveBottom"],
            },
            {"#080b0c"},
        )

    def test_font_files_and_license_are_packaged(self):
        expected = {
            "uiFontFile": "IBMPlexSans-Regular.ttf",
            "displayFontFile": "IBMPlexSansCondensed-SemiBold.ttf",
            "monoFontFile": "IBMPlexMono-Regular.ttf",
        }
        for token, filename in expected.items():
            relative = self.string_properties[token]
            path = UI / "assets" / relative
            self.assertEqual(path.name, filename)
            self.assertTrue(path.is_file(), token)
            self.assertEqual(path.read_bytes()[:4], b"\x00\x01\x00\x00", token)

        license_text = (FONT_DIR / "OFL.txt").read_text(encoding="utf-8")
        notice_text = (FONT_DIR / "FONT-NOTICE.txt").read_text(encoding="utf-8")
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", license_text)
        self.assertIn("IBM Plex", notice_text)
        self.assertIn("https://github.com/IBM/plex", notice_text)

    def test_theme_font_loader_contract_is_wired(self):
        theme = (PALETTE_DIR / "Theme.qml").read_text(encoding="utf-8")
        main = (UI / "qml" / "Main.qml").read_text(encoding="utf-8")
        for token in ("uiFontFile", "displayFontFile", "monoFontFile"):
            self.assertIn(f"readonly property string {token}: palette.{token}", theme)
        for loader in ("themeUiFont", "themeDisplayFont", "themeMonoFont"):
            self.assertIn(f"id: {loader}", main)
        for runtime_name in (
            "loadedUiFontFamily",
            "loadedDisplayFontFamily",
            "loadedMonoFontFamily",
        ):
            self.assertIn(runtime_name, theme)
            self.assertIn(runtime_name, main)

    def test_all_theme_asset_references_are_local_and_present(self):
        references = {
            value
            for value in self.string_properties.values()
            if value.startswith("themes/apex-vector/")
        }
        self.assertGreaterEqual(len(references), 4)
        for relative in references:
            self.assertNotIn("://", relative)
            self.assertTrue((UI / "assets" / relative).is_file(), relative)

    def test_svg_assets_are_scalable_well_formed_and_original(self):
        svg_paths = sorted(ASSET_DIR.glob("*.svg"))
        self.assertGreaterEqual(len(svg_paths), 4)
        for path in svg_paths:
            root = ET.parse(path).getroot()
            source = path.read_text(encoding="utf-8").lower()
            self.assertTrue(root.tag.endswith("svg"), path.name)
            self.assertNotIn("<text", source, path.name)
            self.assertNotRegex(source, r"(?:href|src)\s*=\s*[\"']https?://", path.name)
            self.assertNotIn("wipeout", source, path.name)
            self.assertNotIn("omega", source, path.name)

        backdrop = ET.parse(ASSET_DIR / "apex-vector-backdrop.svg").getroot()
        view_box = [float(value) for value in backdrop.attrib["viewBox"].split()]
        self.assertGreaterEqual(view_box[2], 2560)
        self.assertGreaterEqual(view_box[3], 1440)

    def test_asset_and_font_payload_stays_small(self):
        payload = sum(path.stat().st_size for path in ASSET_DIR.rglob("*") if path.is_file())
        payload += sum(path.stat().st_size for path in FONT_DIR.iterdir() if path.is_file())
        self.assertLess(payload, 2_000_000)

    def test_menu_icons_preserve_existing_geometry_without_effect_layers(self):
        for name in ("generate", "json", "settings", "home", "chevron-right"):
            original = ET.parse(UI / "assets/icons-carbon" / (name + ".svg")).getroot()
            for variant, color in (("dark", "#11161b"), ("light", "#ffffff")):
                icon = ET.parse(ASSET_DIR / "icons" / (name + "-" + variant + ".svg")).getroot()
                self.assertEqual(icon.attrib["stroke"], color)
                icon.set("stroke", original.attrib["stroke"])
                self.assertEqual(ET.tostring(icon), ET.tostring(original))
        source = (UI / "qml/themes/apex/ApexIcon.qml").read_text(encoding="utf-8")
        self.assertIn("sourceSize.width", source)
        self.assertNotIn("layer.enabled", source)

    def test_primary_text_contrast(self):
        def luminance(value):
            channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= 0.04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
        for background, text in (("primary", "primaryText"), ("backgroundA", "text"),
                                 ("backgroundA", "subtle"), ("ghostHoverSurface", "text")):
            a, b = sorted((luminance(self.color_properties[background]), luminance(self.color_properties[text])))
            self.assertGreaterEqual((b + .05) / (a + .05), 4.5, (background, text))

    def test_backdrop_stops_outside_active_menu(self):
        source = (UI / "qml/themes/apex/ApexVectorBackdrop.qml").read_text(encoding="utf-8")
        for token in ("Window.Minimized", "Window.window.active", "menuVisible", "visible &&", "running: root.motionAllowed"):
            self.assertIn(token, source)
        for expensive in ("Canvas", "Timer {", "ShaderEffectSource", "MultiEffect"):
            self.assertNotIn(expensive, source)

    def test_dashboard_preserves_body_and_lifecycle_contract(self):
        source = (UI / "qml/themes/apex/ApexDashboard.qml").read_text(encoding="utf-8")
        for token in ("navigation.parent", "navigation.route(page)", "dashboardWorkspaceEntered",
                      "previousFocusItem", "Qt.Key_Escape", "onMotionAllowedChanged",
                      "root.categories.length"):
            self.assertIn(token, source)
        self.assertNotIn("Popup {", source)

    def test_navigation_uses_live_semantic_gradient_and_icon_tint(self):
        source = (UI / "qml" / "components" / "NavButton.qml").read_text(encoding="utf-8")
        self.assertNotIn("gradient: root.active ? activeGradient", source)
        for token in ("Theme.navActiveTop", "Theme.navActiveMiddle", "Theme.navActiveBottom"):
            self.assertIn(token, source)
        self.assertEqual(source.count("Theme.iconColorize || Theme.classicMode || root.active"), 2)
        self.assertEqual(source.count("Theme.iconTint"), 2)
        self.assertGreaterEqual(
            source.count("Theme.angularControlsEnabled ? Theme.primaryText : Theme.primaryButtonText"),
            4,
        )

    def test_foreground_telemetry_remains_noninteractive(self):
        host = (UI / "qml" / "shell" / "ThemedForeground.qml").read_text(encoding="utf-8")
        self.assertNotIn("enabled: false", host)
        for path in (UI / "qml" / "themes").glob("*/*Foreground.qml"):
            source = path.read_text(encoding="utf-8")
            for handler in (
                "MouseArea",
                "TapHandler",
                "HoverHandler",
                "DragHandler",
                "WheelHandler",
            ):
                self.assertNotIn(handler, source, f"{path.name}: {handler}")


if __name__ == "__main__":
    unittest.main()
