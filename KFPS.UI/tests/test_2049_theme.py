from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
PALETTE = UI / "qml/Kfps/Theme/Palette2049.qml"
QML = UI / "qml/themes/2049"
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import ARCHIVE_2049_THEME, PUBLIC_THEME_NAMES, is_supporter_theme
from test_rx93_theme import contrast


class Archive2049ThemeTests(unittest.TestCase):
    def test_selectable_without_key_and_persists_other_preferences(self):
        self.assertIn(ARCHIVE_2049_THEME, PUBLIC_THEME_NAMES)
        self.assertFalse(is_supporter_theme(ARCHIVE_2049_THEME))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsService(path)
            settings.theme = "Night Blossom"
            settings.reducedMotion = True
            settings.ambientMotion = False
            settings.theme = ARCHIVE_2049_THEME
            loaded = SettingsService(path)
            self.assertEqual(loaded.theme, ARCHIVE_2049_THEME)
            self.assertTrue(loaded.reducedMotion)
            self.assertFalse(loaded.ambientMotion)
            self.assertEqual(json.loads(path.read_text())["theme"], "2049")

    def test_asset_and_component_paths_exist(self):
        for name, relative in re.findall(r'property string (\w+File): "([^"]+)"', PALETTE.read_text(encoding="utf-8")):
            base = UI / "qml" if name == "workspaceConsoleComponentFile" else UI / "qml/shell" if relative.endswith(".qml") else UI / "assets"
            path = base / relative
            self.assertTrue(path.is_file(), relative)
        for name in ("optical-glass.png", "optical-backing.png", "optical-rim.png", "phosphor-raster.png", "analog-wear.png", "analog-sweep.png"):
            self.assertTrue((UI / "assets/themes/2049" / name).is_file())

    def test_semantic_text_and_selections_have_contrast(self):
        values = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', PALETTE.read_text()))
        for bg in ("surface", "surfaceSoft", "surfaceStrong", "ghostHoverSurface", "fieldFocusSurface", "comboHighlight"):
            for fg in ("text", "muted", "subtle"):
                self.assertGreaterEqual(contrast(values[fg], values[bg]), 4.5, (fg, bg))
        for bg in ("primary", "primaryHot", "primaryDeep", "navActiveMiddle", "helpCategorySelected", "helpTopicSelected", "helpBadgeSelected"):
            self.assertGreaterEqual(contrast(values["primaryText"], values[bg]), 4.5, bg)
        self.assertGreaterEqual(contrast(values["border"], values["surface"]), 3)
        self.assertGreaterEqual(contrast(values["focusColor"], values["surfaceSoft"]), 3)

    def test_decorations_never_take_input_or_use_expensive_effects(self):
        for name in ("ArchiveFrame", "ArchiveBackdrop", "ArchiveForeground", "ArchivePageTransition"):
            self.assertIn("enabled: false", (QML / (name + ".qml")).read_text())
        for path in QML.glob("*.qml"):
            source = path.read_text()
            for forbidden in ("MultiEffect", "ShaderEffect", "VideoOutput", "MediaPlayer", "Canvas {", "requestPaint", "Timer {", "MouseArea", "Popup {"):
                self.assertNotIn(forbidden, source, path.name)
            self.assertNotRegex(source, r"font\.letterSpacing:\s*[^0\s]")

    def test_motion_gates_and_edge_only_transitions(self):
        for name in ("ArchiveBackdrop", "ArchiveForeground", "ArchivePageTransition", "ArchiveControlSurface"):
            source = (QML / (name + ".qml")).read_text()
            for gate in ("Window.window.active", "Window.Minimized", "!Theme.reducedMotion", "!screenshotMode"):
                self.assertIn(gate, source)
        self.assertIn("Theme.ambientMotion", (QML / "ArchiveForeground.qml").read_text())
        self.assertIn("Theme.ambientMotion", (QML / "ArchiveBackdrop.qml").read_text())
        transition = (QML / "ArchivePageTransition.qml").read_text()
        self.assertIn("progress = 1", transition)
        self.assertIn("function play()", transition)
        self.assertNotIn("loops: Animation.Infinite", transition)

    def test_plate_motion_contract_defaults_to_zero_for_other_themes(self):
        source = (UI / "qml/shell/ThemedPageTransition.qml").read_text()
        self.assertRegex(source, r"contentOffsetX: .*contentOffsetX : 0")
        self.assertRegex(source, r"contentOffsetY: .*contentOffsetY : 0")
        main = (UI / "qml/Main.qml").read_text()
        self.assertIn("x: pageTransition.contentOffsetX", main)
        self.assertIn("y: pageTransition.contentOffsetY", main)
        self.assertIn("pageTransition.replayOnContentReady", main)

    def test_optical_surface_does_not_filter_artwork(self):
        source = (QML / "ArchiveBackdrop.qml").read_text()
        self.assertIn("optical-glass.png", source)
        self.assertIn("phosphor-raster.png", source)
        for forbidden in ("ShaderEffectSource", "sourceItem", "layer.effect", "MultiEffect"):
            self.assertNotIn(forbidden, source)
        from PIL import Image
        with Image.open(UI / "assets/themes/2049/optical-rim.png") as image:
            self.assertEqual(image.getchannel("A").crop((96, 96, image.width - 96, image.height - 96)).getextrema(), (0, 0))

    def test_instrument_interface_reuses_the_single_create_state(self):
        main = (UI / "qml/Main.qml").read_text()
        create = (UI / "qml/pages/CreatePage.qml").read_text(encoding="utf-8")
        self.assertIn('Theme.chromeMetric("instrumentInterface", 0)', main)
        self.assertIn('visible: !dashboardVisible && !window.instrumentInterface', main)
        self.assertIn('anchors.left: window.instrumentInterface ? parent.left : sidebar.right', main)
        self.assertEqual(main.count('CachedPageHost {'), 1)
        self.assertIn('property alias templateLayers: layers.text', create)
        self.assertIn('onClicked: root.beginGeneration()', create)
        self.assertIn('root.session.beginGeneration()', (QML / 'ArchiveWorkbench.qml').read_text())
        self.assertNotIn('startQueue', (QML / 'ArchiveWorkbench.qml').read_text())

    def test_working_surface_keeps_grain_and_exposure_at_the_edges(self):
        from PIL import Image, ImageStat
        assets = UI / "assets/themes/2049"
        with Image.open(assets / "optical-backing.png") as image:
            centre = image.convert("RGB").crop((480, 270, 1440, 810))
            stats = ImageStat.Stat(centre)
            self.assertLess(max(stats.stddev), 1.0)
            self.assertLess(max(stats.mean), 16)
        with Image.open(assets / "optical-glass.png") as image:
            self.assertLess(ImageStat.Stat(image.getchannel("A")).mean[0], 2)
        with Image.open(assets / "phosphor-raster.png") as image:
            self.assertLessEqual(image.getchannel("A").getextrema()[1], 12)

    def test_open_field_surface_is_local_and_non_intercepting(self):
        field = (QML / "ArchiveFieldSurface.qml").read_text()
        self.assertIn("enabled: false", field)
        self.assertIn("control.activeFocus", field)
        self.assertIn("control.hovered", field)
        workbench = (QML / "ArchiveWorkbench.qml").read_text()
        self.assertEqual(workbench.count("background: ArchiveFieldSurface {}"), 4)
        for component in ("KfpsTextField.qml", "KfpsComboBox.qml"):
            self.assertNotIn("ArchiveFieldSurface", (UI / "qml/components" / component).read_text())

    def test_analog_motion_is_bounded_and_behind_the_content(self):
        from PIL import Image, ImageStat
        assets = UI / "assets/themes/2049"
        with Image.open(assets / "analog-sweep.png") as image:
            self.assertEqual(image.size, (1024, 80))
            self.assertLessEqual(image.getchannel("A").getextrema()[1], 40)
        with Image.open(assets / "analog-wear.png") as image:
            self.assertLess(ImageStat.Stat(image.getchannel("A")).mean[0], 0.2)
        backdrop = (QML / "ArchiveBackdrop.qml").read_text()
        foreground = (QML / "ArchiveForeground.qml").read_text()
        self.assertIn('visible: root.motionAllowed', backdrop)
        self.assertIn('sweepDuration: 16000', backdrop)
        self.assertIn('trackingOffset = 0', backdrop)
        self.assertNotIn('analog-sweep.png', foreground)

    def test_selected_help_metadata_uses_selection_foreground(self):
        source = (UI / "qml/pages/HelpPage.qml").read_text()
        match_label = source.split("text: topicButton.match", 1)[1].split("font.family", 1)[0]
        self.assertIn("topicButton.index === topicList.currentIndex", match_label)
        self.assertIn("!Theme.floatingPanelsEnabled", match_label)
        self.assertIn("? Theme.primaryText : Theme.subtle", match_label)


if __name__ == "__main__":
    unittest.main()
