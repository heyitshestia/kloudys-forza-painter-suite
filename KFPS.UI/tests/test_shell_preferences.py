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
    WINDOWS_94_THEME,
)


class ShellPreferenceTests(unittest.TestCase):
    def test_global_preferences_survive_themes_and_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = SettingsService(path)

            self.assertFalse(settings.manualOverrides)
            self.assertFalse(settings.reducedMotion)
            self.assertTrue(settings.ambientMotion)
            self.assertTrue(settings.glassEffects)
            self.assertTrue(settings.liveStatusVisible)

            settings.manualOverrides = True
            settings.reducedMotion = True
            settings.ambientMotion = False
            settings.glassEffects = False
            settings.liveStatusVisible = False
            settings.theme = WINDOWS_94_THEME
            settings.theme = COMMAND_PROMPT_THEME

            reloaded = SettingsService(path)
            self.assertEqual(reloaded.theme, COMMAND_PROMPT_THEME)
            self.assertTrue(reloaded.manualOverrides)
            self.assertTrue(reloaded.reducedMotion)
            self.assertFalse(reloaded.ambientMotion)
            self.assertFalse(reloaded.glassEffects)
            self.assertFalse(reloaded.liveStatusVisible)

    def test_live_status_alignment_and_visibility_are_shell_owned(self):
        main = (UI / "qml" / "Main.qml").read_text(encoding="utf-8")
        community = (UI / "qml" / "pages" / "CommunityPage.qml").read_text(encoding="utf-8")
        settings_page = (UI / "qml" / "pages" / "SettingsPage.qml").read_text(encoding="utf-8")

        self.assertEqual(main.count("AnnouncementTicker {"), 1)
        self.assertIn("visible: settings.liveStatusVisible", main)
        self.assertIn("readonly property real headerReferenceWidth", main)
        self.assertIn("pageLoader.width - Theme.px(40)", main)
        self.assertIn("Page and subtab layouts cannot resize the ticker", main)
        self.assertIn("readonly property bool headerAlignmentAvailable: root.wide", community)
        self.assertNotIn("headerAlignmentAvailable: root.activeTab", community)
        self.assertIn('text: "Show live status ticker"', settings_page)
        self.assertIn("settings.liveStatusVisible = checked", settings_page)

    def test_version_pill_uses_the_global_update_blink_for_its_surface(self):
        pill = (UI / "qml" / "shell" / "VersionPill.qml").read_text(encoding="utf-8")
        theme = (UI / "qml" / "Kfps" / "Theme" / "Theme.qml").read_text(encoding="utf-8")

        self.assertIn("versionService.updateAvailable", pill)
        self.assertIn("versionService.blinkOn", pill)
        self.assertIn("color: Theme.updateAlertSurface", pill)
        self.assertIn("root.updateAlertPhase ? 0.94 : 0.0", pill)
        self.assertIn("updateAlertSurface: palette.updateAlertSurface", theme)
        self.assertIn("updateAlertText: palette.updateAlertText", theme)


if __name__ == "__main__":
    unittest.main()
