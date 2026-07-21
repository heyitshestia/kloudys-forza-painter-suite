from __future__ import annotations

import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))

from kfps_ui.theme_catalog import (  # noqa: E402
    OVERDRIVE_200X_THEME,
    SUPPORTER_THEME_NAMES,
    THEME_PRESETS,
)


PALETTE_DIR = UI / "qml" / "Kfps" / "Theme"
OVERDRIVE_PALETTE = PALETTE_DIR / "PaletteOverdrive200X.qml"
ASSET_DIR = UI / "assets" / "themes" / "overdrive-200x"
STRING_PROPERTY_RE = re.compile(
    r'^\s*readonly property string\s+(\w+):\s*"([^"]*)"', re.MULTILINE
)
BOOL_PROPERTY_RE = re.compile(
    r"^\s*readonly property bool\s+(\w+):\s*(true|false)", re.MULTILINE
)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


class OverdriveThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = OVERDRIVE_PALETTE.read_text(encoding="utf-8")
        cls.string_properties = dict(STRING_PROPERTY_RE.findall(cls.source))
        cls.bool_properties = {
            name: value == "true" for name, value in BOOL_PROPERTY_RE.findall(cls.source)
        }

    def test_registry_marks_overdrive_as_a_supporter_theme(self):
        presets = {preset.name: preset for preset in THEME_PRESETS}
        self.assertIn(OVERDRIVE_200X_THEME, presets)
        self.assertTrue(presets[OVERDRIVE_200X_THEME].supporter_only)
        self.assertIn(OVERDRIVE_200X_THEME, SUPPORTER_THEME_NAMES)

    def test_motion_capabilities_are_explicitly_enabled(self):
        for name in (
            "equipmentAccentsEnabled",
            "ambientScanEnabled",
            "controlSignalEnabled",
            "navSignalEnabled",
            "panelLocatorEnabled",
            "headerSignalEnabled",
            "logoColorize",
            "customFrameExclusive",
        ):
            self.assertTrue(self.bool_properties[name], name)

        for path in PALETTE_DIR.glob("Palette*.qml"):
            if path in (
                OVERDRIVE_PALETTE,
                PALETTE_DIR / "PaletteApexVector.qml",
                PALETTE_DIR / "PaletteNightCity2077.qml",
            ):
                continue
            values = dict(BOOL_PROPERTY_RE.findall(path.read_text(encoding="utf-8")))
            for name in (
                "equipmentAccentsEnabled",
                "ambientScanEnabled",
                "controlSignalEnabled",
                "navSignalEnabled",
                "panelLocatorEnabled",
                "headerSignalEnabled",
            ):
                self.assertEqual(values[name], "false", f"{path.name}: {name}")

    def test_custom_component_paths_resolve_from_shell_loader(self):
        shell = UI / "qml" / "shell"
        for token in (
            "backdropComponentFile",
            "foregroundComponentFile",
            "pageTransitionComponentFile",
        ):
            relative = self.string_properties[token]
            self.assertTrue(relative)
            self.assertTrue((shell / relative).resolve().is_file(), token)

    def test_button_lens_is_painted_above_generic_glass_and_clipped(self):
        glass = (UI / "qml" / "components" / "ButtonGlassBackdrop.qml").read_text(encoding="utf-8")
        lens = (UI / "qml" / "components" / "ButtonLensOverlay.qml").read_text(encoding="utf-8")
        self.assertNotIn("primaryButtonLensOverlayFile", glass)
        self.assertIn("primaryButtonLensOverlayFile", lens)
        self.assertIn("clip: true", lens)

        for name in ("PrimaryButton.qml", "GhostButton.qml", "NavButton.qml"):
            source = (UI / "qml" / "components" / name).read_text(encoding="utf-8")
            self.assertGreater(source.index("ButtonLensOverlay"), source.index("ButtonGlassBackdrop"), name)

    def test_structural_surfaces_are_borderless_and_rounded(self):
        self.assertTrue(self.bool_properties["customFrameExclusive"])
        self.assertEqual(self.string_properties["panelEdgeFile"], "")
        self.assertEqual(self.string_properties["goldTrimFile"], "")

        theme_source = (PALETTE_DIR / "Theme.qml").read_text(encoding="utf-8")
        self.assertIn("function framedRadius", theme_source)

        for relative in (
            "qml/components/GlassPanel.qml",
            "qml/components/PrimaryButton.qml",
            "qml/components/GhostButton.qml",
            "qml/components/NavButton.qml",
        ):
            source = (UI / relative).read_text(encoding="utf-8")
            self.assertIn("Theme.customFrameExclusive", source, relative)

    def test_all_overdrive_asset_references_are_local_and_present(self):
        references = {
            value
            for value in self.string_properties.values()
            if value.startswith("themes/overdrive-200x/")
        }
        self.assertGreaterEqual(len(references), 5)
        for relative in references:
            self.assertNotIn("://", relative)
            self.assertTrue((UI / "assets" / relative).is_file(), relative)

    def test_raster_assets_meet_resolution_and_size_budget(self):
        backdrop = ASSET_DIR / "overdrive-backdrop.png"
        texture = ASSET_DIR / "overdrive-panel-texture.png"
        backdrop_width, backdrop_height = png_size(backdrop)
        texture_width, texture_height = png_size(texture)
        self.assertGreaterEqual(backdrop_width, 1600)
        self.assertGreaterEqual(backdrop_height, 900)
        self.assertGreaterEqual(texture_width, 512)
        self.assertEqual(texture_width, texture_height)
        self.assertLess(sum(path.stat().st_size for path in ASSET_DIR.iterdir()), 8_000_000)

    def test_svg_assets_are_well_formed_and_brand_neutral(self):
        for path in ASSET_DIR.glob("*.svg"):
            ET.parse(path)
            source = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("<text", source, path.name)
            self.assertNotIn("http://www.w3.org/1999/xlink", source, path.name)

    def test_custom_motion_respects_capture_and_reduced_motion(self):
        for relative in (
            "qml/themes/overdrive/OverdriveBackdrop.qml",
            "qml/themes/overdrive/OverdriveForeground.qml",
            "qml/themes/overdrive/OverdrivePageTransition.qml",
            "qml/shell/SupporterPill.qml",
        ):
            source = (UI / relative).read_text(encoding="utf-8")
            self.assertIn("Theme.reducedMotion", source, relative)
            self.assertIn("screenshotMode", source, relative)


if __name__ == "__main__":
    unittest.main()
