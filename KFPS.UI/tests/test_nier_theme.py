import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / 'src'))
from kfps_ui.settings_service import SettingsService
from kfps_ui.theme_catalog import NIER_AUTOMATA_THEME, PUBLIC_THEME_NAMES
from test_rx93_theme import contrast


class NierThemeTests(unittest.TestCase):
    def test_public_theme_restart_preserves_graphics_and_settings(self):
        self.assertIn(NIER_AUTOMATA_THEME, PUBLIC_THEME_NAMES)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text(json.dumps({'theme': 'Original PS2', 'editorGraphics': 'd3d11', 'ps2StartupMuted': True}))
            settings = SettingsService(path)
            settings.theme = NIER_AUTOMATA_THEME
            reloaded = SettingsService(path)
            self.assertEqual(reloaded.theme, NIER_AUTOMATA_THEME)
            self.assertEqual(reloaded.editorGraphics, 'd3d11')
            self.assertTrue(reloaded.ps2StartupMuted)

    def test_complete_palette_and_accessible_contrast(self):
        folder = UI / 'qml/Kfps/Theme'
        source = (folder / 'PaletteNierAutomata.qml').read_text()
        baseline = (folder / 'PaletteOriginalPs2.qml').read_text()
        names = lambda text: set(re.findall(r'property \w+ (\w+):', text))
        self.assertEqual(names(source), names(baseline))
        for relative in re.findall(r'property string \w+File: "([^"]+)"', source):
            path = UI / 'qml/shell' / relative if relative.endswith('.qml') else UI / 'assets' / relative
            self.assertTrue(path.is_file(), relative)
        colors = dict(re.findall(r'property color (\w+): "(#[0-9a-f]+)"', source))
        for fg in ('text', 'muted', 'subtle', 'primary', 'primaryBright', 'primaryHot', 'success', 'warning', 'danger'):
            for bg in ('surface', 'surfaceStrong', 'surfaceRaised', 'ghostHoverSurface'):
                self.assertGreaterEqual(contrast(colors[fg], colors[bg]), 4.5, (fg, bg))
        for bg in ('primaryButtonTop', 'primaryButtonBottom', 'navActiveBottom', 'comboHighlight'):
            self.assertGreaterEqual(contrast(colors['primaryText'], colors[bg]), 4.5, bg)
        for bg in ('titleBarSurface', 'titleBarButtonHover', 'titleBarCloseHover'):
            self.assertGreaterEqual(contrast(colors['text'], colors[bg]), 4.5, bg)

    def test_theme_owns_only_bounded_motion_and_no_input_overlay(self):
        folder = UI / 'qml/themes/nier'
        for file in folder.glob('*.qml'):
            source = file.read_text()
            self.assertNotRegex(source, r'#[0-9a-fA-F]{3,8}', file.name)
            for forbidden in ('ShaderEffect {', 'MultiEffect {', 'loops: Animation.Infinite', 'Timer {', 'Overlay.overlay', 'Popup {'):
                self.assertNotIn(forbidden, source, file.name)
        reveal = (folder / 'NierReveal.qml').read_text()
        for required in ('enabled: false', '!Theme.reducedMotion', 'function finish()', 'duration: 620', 'onVisibleChanged', 'onActiveChanged'):
            self.assertIn(required, reveal)
        dashboard = (folder / 'NierDashboard.qml').read_text()
        self.assertIn('parent: navigation ? navigation.parent : null', dashboard)
        self.assertIn('previousFocusItem', dashboard)


if __name__ == '__main__':
    unittest.main()
