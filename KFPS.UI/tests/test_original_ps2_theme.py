from __future__ import annotations

import re
import json
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / 'src'))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import ORIGINAL_PS2_THEME, PUBLIC_THEME_NAMES
from test_rx93_theme import contrast

PALETTE = UI / 'qml/Kfps/Theme/PaletteOriginalPs2.qml'
COMPONENTS = UI / 'qml/themes/ps2'


class OriginalPs2Tests(unittest.TestCase):
    def test_intro_mute_default_and_round_trip_preserve_existing_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            path.write_text(json.dumps({'theme': 'Original Xbox', 'editorGraphics': 'd3d11'}))
            settings = SettingsService(path)
            self.assertFalse(settings.ps2StartupMuted)
            settings.ps2StartupMuted = True
            reloaded = SettingsService(path)
            self.assertTrue(reloaded.ps2StartupMuted)
            self.assertEqual(reloaded.theme, 'Original Xbox')
            self.assertEqual(reloaded.editorGraphics, 'd3d11')
            reloaded.theme = ORIGINAL_PS2_THEME
            self.assertTrue(SettingsService(path).ps2StartupMuted)
            reloaded.ps2StartupMuted = False
            self.assertFalse(SettingsService(path).ps2StartupMuted)

    def test_intro_mute_rejects_malformed_saved_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            for value in ('false', 'true', 1, [], None):
                path.write_text(json.dumps({'ps2StartupMuted': value}))
                self.assertFalse(SettingsService(path).ps2StartupMuted)

    def test_cinematic_and_menu_have_no_footer_controls(self):
        startup = (COMPONENTS / 'Ps2Startup.qml').read_text()
        dashboard = (COMPONENTS / 'Ps2Dashboard.qml').read_text()
        for name in ('Ps2StartupMute', 'Ps2StartupSkip'):
            self.assertNotIn(name, startup)
        for name in ('Ps2DashboardEnter', 'Ps2DashboardBack', 'Ps2DashboardCredits'):
            self.assertNotIn(name, dashboard)
        shared = (UI / 'qml/components/ThemeStartup.qml').read_text()
        self.assertIn('Keys.onEscapePressed', shared)
        self.assertIn('Keys.onEscapePressed', dashboard)
        settings_page = (UI / 'qml/pages/SettingsPage.qml').read_text()
        self.assertNotIn('Ps2TestIntro', settings_page)
        self.assertNotIn('requestReplay', startup)

    def test_public_and_restart_preserves_other_settings(self):
        self.assertIn(ORIGINAL_PS2_THEME, PUBLIC_THEME_NAMES)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'settings.json'
            settings = SettingsService(path)
            settings.reducedMotion = True
            settings.theme = ORIGINAL_PS2_THEME
            reloaded = SettingsService(path)
            self.assertEqual(reloaded.theme, ORIGINAL_PS2_THEME)
            self.assertTrue(reloaded.reducedMotion)
            reloaded.theme = 'Original Xbox'
            self.assertEqual(SettingsService(path).theme, 'Original Xbox')

    def test_assets_and_semantic_colors(self):
        source = PALETTE.read_text()
        for relative in re.findall(r'property string \w+File: "([^"]+)"', source):
            path = UI / 'qml/shell' / relative if relative.endswith('.qml') else UI / 'assets' / relative
            self.assertTrue(path.is_file(), relative)
        colors = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', source))
        for foreground in ('text', 'muted', 'subtle', 'primary'):
            for background in ('surface', 'surfaceStrong', 'surfaceRaised', 'ghostHoverSurface'):
                self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5, (foreground, background))
        for background in ('primaryButtonTop', 'primaryButtonMiddle', 'primaryButtonBottom', 'navActiveBottom', 'comboHighlight'):
            self.assertGreaterEqual(contrast(colors['primaryText'], colors[background]), 4.5, background)

    def test_scope_motion_and_native_window_ownership(self):
        for path in COMPONENTS.glob('*.qml'):
            source = path.read_text()
            self.assertNotRegex(source, r'#[0-9a-fA-F]{3,8}', path.name)
            for heavy in ('ShaderEffect {', 'MultiEffect {', 'loops: Animation.Infinite'):
                self.assertNotIn(heavy, source)
            if path.name not in ('Ps2MotionClock.qml', 'Ps2Startup.qml'):
                self.assertNotIn('Timer {', source)
            if path.name == 'Ps2Startup.qml':
                shared = (UI / 'qml/components/ThemeStartup.qml').read_text()
                self.assertIn('ThemeStartup {', source)
                self.assertEqual(shared.count('Timer {'), 1)
                self.assertIn('interval: 250', shared)
                self.assertIn('running: root.visible && !root.waiting && !root.suspended', shared)
                self.assertIn('root.stalledTicks >= 20', shared)
                self.assertIn('if (Theme.reducedMotion) return false', shared)
                self.assertNotIn('Overlay.overlay', source)
                self.assertNotIn('Popup {', source)
        clock = (COMPONENTS / 'Ps2MotionClock.qml').read_text()
        for gate in ('requested && visible', 'applicationActive', 'windowVisible', 'Theme.ambientMotion', '!Theme.reducedMotion', '!screenshotMode'):
            self.assertIn(gate, clock)
        sprites = (COMPONENTS / 'Ps2Clock.qml').read_text()
        self.assertIn('Math.min(384, root.width)', sprites)
        dashboard = (COMPONENTS / 'Ps2Dashboard.qml').read_text()
        self.assertIn('parent: navigation ? navigation.parent : null', dashboard)
        self.assertNotIn('Overlay.overlay', dashboard)
        self.assertNotIn('Popup {', dashboard)
        self.assertIn('enabled: visible', dashboard)
        self.assertIn('previousFocusItem', dashboard)


if __name__ == '__main__':
    unittest.main()
