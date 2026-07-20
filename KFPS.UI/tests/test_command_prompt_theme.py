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
    COMMAND_PROMPT_THEME,
    PUBLIC_THEME_NAMES,
    SUPPORTER_THEME_NAMES,
    available_theme_names,
)


PALETTE = UI / "qml" / "Kfps" / "Theme" / "PaletteCommandPrompt.qml"


class CommandPromptThemeTests(unittest.TestCase):
    def test_command_prompt_is_public(self):
        self.assertIn(COMMAND_PROMPT_THEME, PUBLIC_THEME_NAMES)
        self.assertNotIn(COMMAND_PROMPT_THEME, SUPPORTER_THEME_NAMES)
        self.assertIn(COMMAND_PROMPT_THEME, available_theme_names(False))

    def test_palette_declares_terminal_capabilities(self):
        source = PALETTE.read_text(encoding="utf-8")
        self.assertIn('readonly property string name: "Command Prompt"', source)
        self.assertIn("readonly property bool supporterOnly: false", source)
        self.assertIn("readonly property bool terminalMode: true", source)
        self.assertIn("readonly property bool iconGlyphsVisible: false", source)
        self.assertIn('readonly property color backgroundA: "#000000"', source)
        self.assertIn('readonly property color classificationHandmade: "#ff9fce"', source)
        self.assertIn('readonly property color classificationToolmade: "#8fd8ff"', source)
        self.assertIn('readonly property string backdropComponentFile: "../themes/terminal/TerminalBackdrop.qml"', source)

    def test_green_text_setting_defaults_and_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsService(path)
            self.assertFalse(settings.terminalGreenText)
            self.assertEqual(settings.uiScale, 1.05)
            self.assertIn("property bool greenText: false", PALETTE.read_text(encoding="utf-8"))
            settings.terminalGreenText = True
            self.assertTrue(settings.terminalGreenText)
            settings.theme = "Night Blossom"
            settings.theme = COMMAND_PROMPT_THEME
            reloaded = SettingsService(path)
            self.assertEqual(reloaded.theme, COMMAND_PROMPT_THEME)
            self.assertTrue(reloaded.terminalGreenText)

    def test_green_text_control_is_terminal_only(self):
        settings_page = (UI / "qml" / "pages" / "SettingsPage.qml").read_text(encoding="utf-8")
        theme = (UI / "qml" / "Kfps" / "Theme" / "Theme.qml").read_text(encoding="utf-8")
        main = (UI / "qml" / "Main.qml").read_text(encoding="utf-8")
        self.assertIn("visible: Theme.terminalMode", settings_page)
        self.assertIn("settings.terminalGreenText = checked", settings_page)
        self.assertIn("greenText: root.terminalGreenText", theme)
        self.assertIn('property: "terminalGreenText"; value: settings.terminalGreenText', main)
        for path in (UI / "qml" / "Kfps" / "Theme").glob("Palette*.qml"):
            if path != PALETTE:
                self.assertNotIn("property bool greenText", path.read_text(encoding="utf-8"), path.name)

    def test_terminal_controls_are_square_and_command_driven(self):
        theme = (UI / "qml" / "Kfps" / "Theme" / "Theme.qml").read_text(encoding="utf-8")
        primary = (UI / "qml" / "components" / "PrimaryButton.qml").read_text(encoding="utf-8")
        ghost = (UI / "qml" / "components" / "GhostButton.qml").read_text(encoding="utf-8")
        panel = (UI / "qml" / "components" / "GlassPanel.qml").read_text(encoding="utf-8")
        sidebar = (UI / "qml" / "shell" / "Sidebar.qml").read_text(encoding="utf-8")
        self.assertIn("function corner(defaultRadius)", theme)
        self.assertIn("return terminalMode ? 0 : defaultRadius", theme)
        self.assertIn('text: Theme.terminalMode ? "> " + root.text : root.text', primary)
        self.assertIn("terminalInverted", primary)
        self.assertIn("effectiveLabelColor", ghost)
        self.assertIn("Theme.terminalMode && (checkedState || down)", ghost)
        self.assertIn("border.width: Theme.terminalMode ? 0", panel)
        self.assertIn('supporterService.unlocked', sidebar)
        self.assertIn('"Thank you for supporting the project"', sidebar)
        self.assertIn('"Consider supporting the project"', sidebar)

        for directory in ("components", "pages", "shell"):
            for path in (UI / "qml" / directory).glob("*.qml"):
                for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if line.strip().startswith("radius:"):
                        self.assertRegex(
                            line,
                            r"Theme\.(corner|framedRadius)\(",
                            f"{path.name}:{line_number} bypasses square terminal corners",
                        )

    def test_empty_terminal_asset_paths_are_not_loaded(self):
        panel = (UI / "qml" / "components" / "GlassPanel.qml").read_text(encoding="utf-8")
        blossom = (UI / "qml" / "shell" / "BlossomBackdrop.qml").read_text(encoding="utf-8")
        self.assertIn("visible: Theme.panelNoiseFile.length > 0", panel)
        self.assertIn('source: visible ? assetRoot + "/" + Theme.panelNoiseFile : ""', panel)
        self.assertIn("visible: Theme.backdropBaseFile.length > 0", blossom)


if __name__ == "__main__":
    unittest.main()
