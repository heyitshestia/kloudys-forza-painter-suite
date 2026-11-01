from pathlib import Path
import json
import re
import sys
import tempfile
import unittest

UI = Path(__file__).resolve().parents[1]
QML = UI / "qml/themes/redline"
PALETTE = UI / "qml/Kfps/Theme/PaletteRedline.qml"
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import PUBLIC_THEME_NAMES, is_supporter_theme
from test_rx93_theme import contrast


class RedlineThemeTests(unittest.TestCase):
    def test_selectable_and_preferences_survive_restart(self):
        self.assertIn("Redline", PUBLIC_THEME_NAMES)
        self.assertFalse(is_supporter_theme("Redline"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"settings.json"
            settings = SettingsService(path)
            settings.reducedMotion = True
            settings.ambientMotion = False
            settings.theme = "Redline"
            loaded = SettingsService(path)
            self.assertEqual(loaded.theme, "Redline")
            self.assertTrue(loaded.reducedMotion)
            self.assertFalse(loaded.ambientMotion)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["theme"], "Redline")

    def test_asset_and_component_paths_exist(self):
        for name, relative in re.findall(r'property string (\w+File): "([^"]+)"', PALETTE.read_text(encoding="utf-8")):
            base = UI/"qml" if name == "workspaceConsoleComponentFile" else UI/"qml/shell" if relative.endswith(".qml") else UI/"assets"
            self.assertTrue((base/relative).is_file(), relative)
        self.assertIn("SIL OPEN FONT LICENSE", (UI/"assets/fonts/redline/OFL.txt").read_text(encoding="utf-8"))
        self.assertIn("Source:", (UI/"assets/fonts/redline/FONT-NOTICE.txt").read_text(encoding="utf-8"))

    def test_revision_has_its_own_layout_and_motion(self):
        backdrop=(QML/"RedlineBackdrop.qml").read_text(encoding="utf-8")
        transition=(QML/"RedlinePageTransition.qml").read_text(encoding="utf-8")
        console=(QML/"RedlineConsole.qml").read_text(encoding="utf-8")
        self.assertNotIn("fabrication-bay", backdrop)
        self.assertNotIn("Image {", backdrop)
        self.assertIn("property real disruption", backdrop)
        self.assertIn("contentOffsetX: 0", transition)
        self.assertIn("contentOffsetY: 0", transition)
        self.assertIn("RedlineGroup:", console)
        self.assertIn("groupFor(appController.currentPage)", console)
        settings=(UI/"qml/pages/SettingsPage.qml").read_text(encoding="utf-8")
        self.assertIn('Theme.chromeMetric("redlineInterface", 0)', settings)
        for section in range(3):
            self.assertIn("visible: !root.redlineInterface || root.selectedSection === "+str(section), settings)

    def test_contrast_for_text_fields_and_selections(self):
        values = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', PALETTE.read_text(encoding="utf-8")))
        for bg in ("surface", "surfaceSoft", "ghostHoverSurface", "fieldFocusSurface", "comboHighlight"):
            for fg in ("text", "muted", "subtle"):
                self.assertGreaterEqual(contrast(values[fg], values[bg]), 4.5, (fg, bg))
        for bg in ("primary", "primaryHot", "primaryDeep", "helpCategorySelected", "navActiveMiddle"):
            self.assertGreaterEqual(contrast(values["primaryText"], values[bg]), 4.5, bg)

    def test_typed_hooks_preserve_2049_defaults(self):
        theme=(UI/"qml/Kfps/Theme/Palette2049.qml").read_text(encoding="utf-8")
        self.assertIn(': "themes/2049/ArchiveConsole.qml"', theme)
        self.assertIn(': "../themes/2049/ArchiveWorkbench.qml"', theme)
        main=(UI/"qml/Main.qml").read_text(encoding="utf-8")
        self.assertEqual(main.count("CachedPageHost {"),1)
        self.assertIn('Theme.chromeMetric("workspaceTopInset", window.shortWindow ? 70 : 86)', main)

    def test_workbench_uses_authoritative_state_and_actions(self):
        source=(QML/"RedlineWorkbench.qml").read_text(encoding="utf-8")
        self.assertIn("root.session.beginGeneration()",source)
        self.assertIn("root.session.requestForceStop()",source)
        self.assertIn("generationService.gracefulStop()",source)
        self.assertIn("sourceService.choose()",source)
        self.assertNotIn("startQueue(",source)
        self.assertNotIn("ShaderEffectSource",source)
        for key in ("templateLayers","checkpointValues","detailEnabled","lumaEnabled","repairEnabled","boostEnabled","seedValue"):
            self.assertIn(key,source)

    def test_animation_gates_and_nonintercepting_decoration(self):
        for name in ("RedlineBackdrop","RedlinePageTransition","RedlineControlSurface"):
            source=(QML/(name+".qml")).read_text(encoding="utf-8")
            for gate in ("Window.window.active","Window.Minimized","!Theme.reducedMotion","!screenshotMode"):
                self.assertIn(gate,source)
            self.assertIn("enabled: false",source)
        self.assertIn("Theme.ambientMotion",(QML/"RedlineBackdrop.qml").read_text(encoding="utf-8"))
        for path in QML.glob("*.qml"):
            source=path.read_text(encoding="utf-8")
            for forbidden in ("MultiEffect", "ShaderEffect", "Canvas {", "Timer {", "MouseArea", "VideoOutput", "MediaPlayer"):
                self.assertNotIn(forbidden,source,path.name)

    def test_library_layout_and_category_actions_are_opt_in(self):
        source=(UI/"qml/pages/JsonPage.qml").read_text(encoding="utf-8")
        self.assertIn('Theme.chromeMetric("redlineInterface", 0)',source)
        self.assertIn('root.redlineInterface ? Qt.RightToLeft : Qt.LeftToRight',source)
        self.assertIn('jsonService.setSource(index)',source)
        self.assertIn('objectName: "OutputCategoryTab:" + index',source)
        self.assertEqual(source.count('objectName: "OutputCategoryTabs"'), 1)
        self.assertNotIn('RedlineOutputCategory:', source)
        surface=(QML/"RedlineControlSurface.qml").read_text(encoding="utf-8")
        self.assertIn('controlKind === "primary" || (controlKind === "nav" && selected)',surface)

    def test_icon_commands_have_accessible_names_and_focus(self):
        source=(QML/"RedlineButton.qml").read_text(encoding="utf-8")
        self.assertIn("Accessible.name: hint || text",source)
        self.assertIn("focusPolicy: Qt.StrongFocus",source)
        self.assertIn("KfpsToolTip {",source)
        self.assertIn("text: root.hint",source)
        self.assertIn("menuEntry ? 80",source)

    def test_nav_spacing_is_opt_in_with_original_defaults(self):
        source=(UI/"qml/components/NavButton.qml").read_text(encoding="utf-8")
        for key, default in (("navContentInset", 17), ("navContentGap", 8), ("navArrowWidth", 20), ("navArrowInset", 10)):
            self.assertIn('Theme.chromeMetric("'+key+'", '+str(default)+')',source)
        for palette in (UI/"qml/Kfps/Theme").glob("Palette*.qml"):
            if palette != PALETTE:
                self.assertNotIn("navContentInset", palette.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
