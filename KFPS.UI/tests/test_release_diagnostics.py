"""Release diagnostics stay useful without copying custom work or identities."""
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'KFPS.UI/src'), str(ROOT)]
from kfps_ui.support_context import collect_context, collect_preferences
from kfps_ui.support_log_bundle import collect_retained_log_bundle
from tools.fabric_editor_diagnostics import clean_fields


class ReleaseDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'app'
        self.root.mkdir()
        environment = patch.dict(os.environ, {'LOCALAPPDATA': str(Path(self.temp.name) / 'local')})
        environment.start()
        self.addCleanup(environment.stop)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_customizations_are_summarized_not_copied_and_do_not_change(self):
        app = self.write('runtime/qml-shell-settings.json', {'theme': 'PRIVATE custom theme',
            'editorUseChrome': True, 'liveryUseChrome': False, 'editorGraphics': 'd3d11',
            'backupFolder': 'PRIVATE folder', 'key': 'PRIVATE key',
            'windowGeometry': {'x': 1234, 'y': 5678, 'width': 1760, 'height': 1040, 'maximized': False}})
        editor = self.write('runtime/fabric-editor/preferences.json', {'theme': 'PRIVATE custom',
            'settings': {'kloudyFabricLanguage': 'ja', 'kloudyFabricShortcuts': json.dumps({'PRIVATE action': 'PRIVATE binding'}),
                'kloudyFabricDockState': json.dumps({'panels': {'locked': True, 'items': {
                    'PRIVATE panel': {'place': 'floating', 'rect': {'x': 1234}}}}}),
                'PRIVATE setting': 'PRIVATE value'}})
        before = [p.read_bytes() for p in (app, editor)]
        value = collect_preferences(self.root)
        self.assertEqual(value['app']['options']['editorGraphics'], 'd3d11')
        self.assertTrue(value['app']['options']['editorUseChrome'])
        self.assertEqual(value['editor']['options']['custom_shortcut_count'], 1)
        self.assertEqual(value['editor']['options']['panel_places']['floating'], 1)
        self.assertEqual(value['editor']['options']['language'], 'ja')
        self.assertNotIn('PRIVATE', json.dumps(value))
        self.assertNotIn('1234', json.dumps(value))
        self.assertEqual(before, [p.read_bytes() for p in (app, editor)])

    def test_malformed_oversized_linked_and_unknown_preferences_are_bounded(self):
        for bad in ([], None, 4, 'bad', {'theme': [], 'editorGraphics': {}, 'windowGeometry': {'width': math.inf}},
                    {'settings': {'kloudyFabricShortcuts': '{bad', 'kloudyFabricDockState': '[]'}}):
            self.write('runtime/qml-shell-settings.json', bad)
            self.write('runtime/fabric-editor/preferences.json', bad)
            value = collect_preferences(self.root)
            json.dumps(value, allow_nan=False)
            self.assertLess(len(json.dumps(value)), 4000)
        target = self.write('runtime/qml-shell-settings.json', {'secret': 'PRIVATE'})
        os.link(target, self.root / 'linked')
        self.assertEqual(collect_preferences(self.root)['app']['status'], 'unsafe_file')
        large = self.root / 'runtime/fabric-editor/preferences.json'
        large.write_bytes(b' ' * (2 * 1024 * 1024 + 1))
        self.assertEqual(collect_preferences(self.root)['editor']['status'], 'oversized_file')

    def test_storage_is_not_opened_and_component_fingerprints_survive_bundle(self):
        database = self.root / 'imgs/livery-projects/storage.sqlite3'
        database.parent.mkdir(parents=True)
        database.write_bytes(b'PRIVATE artwork project database')
        self.write('tools/livery-studio/src/kfps_livery_lab/server.py', {'synthetic': True})
        opened = []
        original = Path.open
        def track(path, *args, **kwargs):
            opened.append(path)
            if path == database:
                raise AssertionError('Project database must not be opened')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', track):
            metadata, blob = collect_retained_log_bundle(self.root)
        archive = json.loads(gzip.decompress(blob))
        text = json.dumps(archive)
        self.assertNotIn('PRIVATE', text)
        self.assertIn('studio-server', text)
        self.assertIn('sha256_groups', text)
        self.assertIn('custom_shortcut_count', text)
        self.assertLess(metadata['size'], 8 * 1024 * 1024)
        self.assertNotIn(database, opened)

    def test_workspace_fields_are_allowlisted_not_free_form(self):
        value = clean_fields({'floatingPanels': 4, 'viewportWidth': 1760, 'devicePixelRatio': 1.5,
            'panelsLocked': True, 'panelDrag': False, 'focusCanvas': True, 'title': 'PRIVATE',
            'leftPanels': 'PRIVATE', 'hiddenPanels': math.inf, 'source': 'locales/ja.js'})
        self.assertEqual(value['floatingPanels'], 4)
        self.assertEqual(value['devicePixelRatio'], 1.5)
        self.assertTrue(value['panelsLocked'])
        self.assertEqual(value['source'], 'locales/ja.js')
        self.assertNotIn('leftPanels', value)
        self.assertNotIn('hiddenPanels', value)
        self.assertNotIn('PRIVATE', json.dumps(value))

    def test_report_data_cannot_supply_studio_collector_code(self):
        path = self.root / 'tools/livery-studio/src/kfps_livery_lab/diagnostics.py'
        path.parent.mkdir(parents=True)
        path.write_text("raise AssertionError('PRIVATE injected module ran')", encoding='utf-8')
        value = collect_context(self.root)
        self.assertIn('studio_diagnostics', value)
        self.assertNotIn('PRIVATE', json.dumps(value))

    def test_anonymous_activity_state_is_not_an_attachment_or_identity(self):
        path = self.write('runtime/activity-private/state.json', {'schema': 1, 'enabled': False,
            'seed': 'PRIVATE seed', 'last_status': 'never_sent'})
        lock = path.with_name('state.lock')
        lock.touch()
        before = path.read_bytes()
        value = collect_context(self.root)
        status = value['anonymous_activity']
        self.assertFalse(status['enabled'])
        self.assertEqual(status['status'], 'disabled')
        _, blob = collect_retained_log_bundle(self.root)
        archive = json.loads(gzip.decompress(blob))
        self.assertNotIn('PRIVATE', json.dumps(archive))
        self.assertNotIn('activity-private', json.dumps(archive))
        self.assertEqual(path.read_bytes(), before)

    def test_installed_studio_logs_are_structured_and_invalid_rows_are_omitted(self):
        from kfps_ui import support_studio
        support_studio._contract.cache_clear()
        contract = support_studio._contract()
        if contract is None:
            self.skipTest('Studio must be materialized for the installed contract gate')
        folder = self.root / support_studio.RELATIVE_ROOT
        folder.mkdir(parents=True)
        good = {'schema_version': 1, 'utc': '2026-10-19T12:00:00Z',
            'session': 'a' * 16, 'sequence': 1, 'event': 'render', 'frame_ms': 20,
            'shape_count': 3000, 'canvas_width': 1760, 'canvas_height': 1040}
        bad = {**good, 'path': 'PRIVATE project', 'key': 'PRIVATE secret'}
        (folder / 'studio.jsonl').write_text(json.dumps(good) + '\n' + json.dumps(bad) + '\n' +
            '{"broken":"PRIVATE"\n', encoding='utf-8')
        _, blob = collect_retained_log_bundle(self.root)
        archive = json.loads(gzip.decompress(blob))
        record = next(item for item in archive['files'] if item['name'] == 'studio-performance-0000.log')
        self.assertEqual(record['omitted_lines'], 2)
        self.assertEqual(json.loads(record['text'])['shape_count'], 3000)
        self.assertNotIn('PRIVATE', json.dumps(archive))
        before = (folder / 'studio.jsonl').read_bytes()
        collect_context(self.root)
        self.assertEqual((folder / 'studio.jsonl').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
