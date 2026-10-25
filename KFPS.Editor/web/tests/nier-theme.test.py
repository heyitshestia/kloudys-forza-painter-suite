"""Actual editor HTTP saves and Studio durable theme validation, private profiles only."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'KFPS.Editor/src'), str(ROOT / 'tools/livery-studio/src'), str(ROOT)]
from kfps_editor.server import EditorServer, Handler, ServerPaths, EDITOR_MUTATION_HEADER, _theme_id_from_name
from kfps_livery_lab.theme_context import ThemeContext, COLOR_KEYS, validate_studio_theme


class NIERThemeTests(unittest.TestCase):
    def test_editor_http_roundtrip_and_preference_preservation(self):
        directory = ROOT / 'KFPS.Editor/runtime/nier-theme-tests'
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            paths = ServerPaths.for_runtime(ROOT, Path(temp), exports=Path(temp) / 'exports')
            existing = {'settings': {'kloudyFabricShortcuts': '{"duplicate":"Ctrl+Alt+D"}',
                                    'futureSetting': {'kept': True}}, 'unrelated': [1, 2]}
            existing['theme'] = 'nier'
            legacy = {'format': 'kfps_fabric_editor_theme_v1', 'id': 'nier', 'name': 'NIER',
                      'base': 'dark', 'values': {key: '#123456' for key in COLOR_KEYS}}
            paths.themes.mkdir()
            legacy_file = paths.themes / 'nier.json'
            legacy_file.write_text(json.dumps(legacy), encoding='utf-8')
            legacy_bytes = legacy_file.read_bytes()
            paths.preferences.write_text(json.dumps(existing), encoding='utf-8')
            with EditorServer(('127.0.0.1', 0), Handler, paths=paths) as server:
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                origin = f'http://127.0.0.1:{server.server_address[1]}'

                def request(route, body=None):
                    req = Request(origin + '/api/fabric-editor/' + route,
                                  data=None if body is None else json.dumps(body).encode(),
                                  headers={'Content-Type': 'application/json', 'Origin': origin,
                                           EDITOR_MUTATION_HEADER: server.editor_session_token})
                    with urlopen(req, timeout=5) as response:
                        return json.load(response)
                try:
                    self.assertIn('builtin:nier', [entry['id'] for entry in request('themes')['themes']])
                    self.assertEqual(request('preferences')['theme'], 'nier')
                    old_entry = next(entry for entry in request('themes')['themes'] if entry['id'] == 'nier')
                    self.assertFalse(old_entry['builtin'])
                    self.assertEqual(old_entry['base'], 'dark')
                    self.assertEqual(old_entry['values'], legacy['values'])
                    request('preferences', {'theme': 'builtin:nier'})
                    self.assertEqual(request('preferences')['theme'], 'builtin:nier')
                    saved = request('themes', {'name': 'NIER', 'base': 'builtin:nier',
                                              'values': {key: '#123456' for key in COLOR_KEYS}})['theme']
                    self.assertEqual(saved['id'], 'nier-2')
                    self.assertEqual(saved['base'], 'builtin:nier')
                    self.assertEqual(saved['format'], 'kfps_fabric_editor_theme_v1')
                    self.assertEqual(len(saved['values']), 33)
                    catalog = {entry['id']: entry for entry in request('themes')['themes']}
                    self.assertEqual(catalog[saved['id']]['base'], 'builtin:nier')
                    self.assertEqual(json.loads((paths.themes / 'nier-2.json').read_text()), saved)
                    for theme in ['pastel', 'dark', 'blackout', 'whiteout', 'builtin:nier', saved['id'], 'nier']:
                        request('preferences', {'theme': theme})
                        self.assertEqual(request('preferences')['theme'], theme)
                    with self.assertRaises(HTTPError):
                        request('preferences', {'theme': 'missing-theme'})
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
                persisted = json.loads(paths.preferences.read_text())
                for key, value in existing['settings'].items():
                    self.assertEqual(persisted['settings'][key], value)
                self.assertEqual(persisted['unrelated'], existing['unrelated'])
                self.assertEqual(_theme_id_from_name('NIER'), 'nier')
                self.assertEqual(legacy_file.read_bytes(), legacy_bytes)
                self.assertEqual(persisted['theme'], 'nier')

    def test_studio_restart_cancel_to_host_and_invalid_save(self):
        directory = ROOT / 'tools/livery-studio/runs'
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='nier-test-', dir=directory) as temp:
            theme = {'format': 'kfps_fabric_editor_theme_v1', 'id': 'builtin:nier', 'name': 'NieR Automata',
                     'base': 'builtin:nier', 'values': {key: '#47473e' for key in COLOR_KEYS},
                     'fontFamily': 'sans-serif', 'colorScheme': 'light'}
            context = ThemeContext(temp, ROOT)
            context.select(theme)
            self.assertEqual(ThemeContext(temp, ROOT).effective()['base'], 'builtin:nier')
            before = context.studio_path.read_bytes()
            for invalid in [dict(theme, base='unknown'), dict(theme, values={'--accent': '#fff'}),
                            dict(theme, values=dict(theme['values'], **{'--accent': 'url(bad)'}))]:
                with self.assertRaises(ValueError):
                    context.select(invalid)
                self.assertEqual(context.studio_path.read_bytes(), before)
            custom = dict(theme, id='custom', name='Edited NIER', values=dict(theme['values'], **{'--accent': '#ffcc55'}))
            context.select(custom)
            self.assertEqual(ThemeContext(temp, ROOT).effective()['values']['--accent'], '#ffcc55')
            for base in ('pastel', 'dark', 'blackout', 'whiteout', 'builtin:nier'):
                self.assertEqual(validate_studio_theme(dict(theme, base=base))['base'], base)
            context.select(None)
            self.assertIsNone(ThemeContext(temp, ROOT).effective())


if __name__ == '__main__':
    unittest.main()
