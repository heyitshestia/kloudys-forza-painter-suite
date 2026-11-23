"""Run the distributable BAT with Windows PowerShell, using private fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name('Collect_KFPS_Diagnostics.bat')
EVIDENCE = ROOT / 'runtime/diagnostics-collector-20261112'


@unittest.skipUnless(os.name == 'nt', 'Windows BAT integration test')
class CollectorTests(unittest.TestCase):
    def setUp(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='fixture-', dir=EVIDENCE)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.local = self.root / 'Local AppData'
        self.temp = self.root / 'Temp'
        self.temp.mkdir()
        self.env = {**os.environ, 'LOCALAPPDATA': str(self.local), 'TEMP': str(self.temp),
                    'TMP': str(self.temp)}

    def put(self, root, name, data):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def layout(self, nested=False, inner=False, odd=False):
        base = self.root / ("KFPS & 100% ! [test] O'Brien \u65e5\u672c" if odd else 'KFPS Test')
        app = base / 'KloudysFH6Painter' if nested else base
        self.put(base, 'KFPS.exe', b'fixture outer launcher; never execute')
        if nested:
            self.put(app, 'KFPS.exe', b'fixture inner launcher; never execute')
        self.put(app, 'VERSION', '3.2.3\n')
        self.put(app, 'KFPS.UI/app.py', '# fixture, never execute\n')
        launch = app if inner else base
        bat = launch / SOURCE.name
        shutil.copy2(SOURCE, bat)
        return base, app, bat

    def updater(self, root, text='Updater completed', age=0):
        identity = hashlib.sha256(str(root.resolve()).replace('\\', '/').lower().encode()).hexdigest()
        state = self.local / 'KloudysFH6Painter/updater/installations' / identity
        log = self.put(state, 'logs/update-20261112-100000-42.log', text)
        self.put(state, 'reports/update-20261112-100000-42.json', '{"status":"ok"}')
        self.put(state, 'state.json', 'SECRET_STATE_DO_NOT_INCLUDE')
        self.put(state, 'cache/private.zip', b'SECRET_CACHE_DO_NOT_INCLUDE')
        if age:
            os.utime(log, (age, age))
        return state

    def run_bat(self, bat, success=True):
        command = f'"{os.environ["SystemRoot"]}\\System32\\cmd.exe" /d /s /c ""{bat}" --no-pause"'
        result = subprocess.run(command, env=self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=40, cwd=self.temp)
        output = result.stdout.decode('utf-8', 'replace')
        self.assertEqual(result.returncode, 0 if success else 1, output)
        if not success:
            self.assertNotIn('SUCCESS:', output)
            return output
        self.assertIn('SUCCESS:', output)
        zips = list(bat.parent.glob('KFPS-Diagnostics-*.zip')) + list(self.temp.glob('KFPS-Diagnostics/*.zip'))
        self.assertEqual(len(zips), 1, output)
        with zipfile.ZipFile(zips[0]) as archive:
            self.assertIsNone(archive.testzip())
            entries = {name: archive.read(name) for name in archive.namelist()}
        diagnostics = json.loads(entries['diagnostics.json'])
        return diagnostics, entries, output

    def test_direct_layout_logs_privacy_and_no_mutation(self):
        base, app, bat = self.layout()
        log = self.put(app, 'runtime/app-logs/app-42.log', 'Error file: test.cjs\nAuthorization: Bearer SUPER_SECRET\n')
        self.put(app, 'runtime/fabric-editor/desktop-startup-error.json', '{"error":"broken"}')
        self.put(app, 'settings/user.json', 'PRIVATE_SETTINGS')
        self.put(app, 'imgs/generated/private.log', 'PRIVATE_ARTWORK')
        self.put(app, 'runtime/app-logs/credentials.json', 'PRIVATE_CREDENTIALS')
        self.updater(base)
        before = log.read_bytes()
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertEqual(diagnostics['application_root'], str(app))
        self.assertGreaterEqual(len(diagnostics['collected']), 4)
        self.assertIn('Error file: test.cjs', entries['application/app-logs/app-42.log'].decode())
        payload = b'\n'.join(entries.values())
        for secret in (b'SUPER_SECRET', b'PRIVATE_SETTINGS', b'PRIVATE_ARTWORK', b'PRIVATE_CREDENTIALS',
                       b'SECRET_STATE_DO_NOT_INCLUDE', b'SECRET_CACHE_DO_NOT_INCLUDE'):
            self.assertNotIn(secret, payload)
        self.assertEqual(log.read_bytes(), before)

    def test_outer_and_inner_official_layout(self):
        for inner in (False, True):
            with self.subTest(inner=inner):
                base, app, bat = self.layout(nested=True, inner=inner)
                self.updater(base)
                diagnostics, entries, _ = self.run_bat(bat)
                self.assertEqual(diagnostics['application_root'], str(app))
                self.assertEqual(diagnostics['install_root'], str(base))
                self.assertTrue(diagnostics['updater_locations'][0]['match'])
                self.assertEqual(entries['application/VERSION.txt'], b'3.2.3\n')
                for path in bat.parent.glob('KFPS-Diagnostics-*.zip'):
                    path.unlink()

    def test_special_characters_unicode_and_missing_logs(self):
        _, app, bat = self.layout(odd=True)
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertEqual(diagnostics['application_root'], str(app))
        self.assertEqual(len(diagnostics['collected']), 1)
        self.assertEqual(entries['application/VERSION.txt'], b'3.2.3\n')

    def test_latest_logs_and_other_installation_context(self):
        base, _, bat = self.layout()
        state = self.updater(base, age=1000)
        for index in range(4):
            file = self.put(state, f'logs/update-20261112-10000{index}-43.log', f'log {index}')
            os.utime(file, (2000 + index, 2000 + index))
        for index in range(4):
            self.updater(self.root / f'Other {index}')
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertEqual(len(diagnostics['updater_locations']), 3)
        self.assertTrue(diagnostics['updater_locations'][0]['match'])
        names = [name for name in entries if state.name in name and '/logs/' in name]
        self.assertEqual(len(names), 2)
        self.assertTrue(any('100003' in name for name in names))
        self.assertTrue(any('100002' in name for name in names))

    def test_large_log_is_bounded_and_source_unchanged(self):
        _, app, bat = self.layout()
        value = b'X' * (3 * 1024 * 1024) + b'FINAL_ERROR'
        path = self.put(app, 'runtime/app-logs/app-99.log', value)
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertTrue(entries['application/app-logs/app-99.log.tail.txt'].endswith(b'FINAL_ERROR'))
        row = next(row for row in diagnostics['collected'] if row['source'] == str(path))
        self.assertEqual(row['collected_bytes'], 2 * 1024 * 1024)
        self.assertTrue(row['truncated'])
        self.assertEqual(path.read_bytes(), value)

    def test_wrong_folder_does_not_collect_or_create_zip(self):
        folder = self.root / 'Downloads'
        folder.mkdir()
        bat = folder / SOURCE.name
        shutil.copy2(SOURCE, bat)
        output = self.run_bat(bat, success=False)
        self.assertIn('beside KFPS.exe', output)
        self.assertFalse(list(self.root.rglob('*.zip')))

    def test_utf16_empty_log_and_missing_appdata(self):
        _, app, bat = self.layout()
        self.env.pop('LOCALAPPDATA')
        self.put(app, 'runtime/app-logs/app-10.log', 'Repair required: example.cjs'.encode('utf-16'))
        self.put(app, 'runtime/app-logs/app-11.log', b'')
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertEqual(entries['application/app-logs/app-10.log'], b'Repair required: example.cjs')
        self.assertEqual(entries['application/app-logs/app-11.log'], b'')
        self.assertTrue(any('LOCALAPPDATA' in issue for issue in diagnostics['issues']))

    def test_locked_log_is_reported_without_blocking_archive(self):
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                      ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        _, app, bat = self.layout()
        path = self.put(app, 'runtime/app-logs/app-42.log', 'locked log')
        handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            diagnostics, entries, _ = self.run_bat(bat)
        finally:
            kernel.CloseHandle(handle)
        self.assertNotIn('application/app-logs/app-42.log', entries)
        self.assertTrue(any('app-42.log' in issue for issue in diagnostics['issues']))
        self.assertIn('application/VERSION.txt', entries)

    def test_zip_output_failure_falls_back_to_temp(self):
        base = self.root / ('x' * max(1, 215 - len(str(self.root)) - 1))
        self.put(base, 'KFPS.exe', b'fixture launcher; never execute')
        self.put(base, 'VERSION', '3.2.3')
        bat = base / SOURCE.name
        shutil.copy2(SOURCE, bat)
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertIn('application/VERSION.txt', entries)
        # Windows PowerShell's .NET framework normally rejects the longer ZIP
        # path. Long-path-enabled hosts may legitimately use the primary folder.
        if list(self.temp.glob('KFPS-Diagnostics/*.zip')):
            self.assertTrue(any('temporary diagnostics folder' in issue for issue in diagnostics['issues']))

    def test_linked_log_folder_is_not_followed(self):
        _, app, bat = self.layout()
        secret = self.root / 'Private'
        self.put(secret, 'app-42.log', 'DO_NOT_READ_LINK_TARGET')
        link = app / 'runtime/app-logs'
        link.parent.mkdir()
        env = {**self.env, 'TEST_JUNCTION': str(link), 'TEST_TARGET': str(secret)}
        result = subprocess.run([os.environ['SystemRoot'] + r'\System32\WindowsPowerShell\v1.0\powershell.exe',
                                 '-NoProfile', '-Command',
                                 "New-Item -ItemType Junction -Path $env:TEST_JUNCTION -Target $env:TEST_TARGET | Out-Null"],
                                env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            diagnostics, entries, _ = self.run_bat(bat)
            self.assertNotIn(b'DO_NOT_READ_LINK_TARGET', b'\n'.join(entries.values()))
            self.assertTrue(any('Linked path skipped' in issue for issue in diagnostics['issues']))
        finally:
            os.rmdir(link)

    def test_total_budget_prioritizes_current_installation(self):
        base, app, bat = self.layout()
        for root in (base, self.root / 'Other A', self.root / 'Other B'):
            state = self.updater(root)
            for index in range(2):
                self.put(state, f'logs/update-big-{index}.log', b'X' * (2 * 1024 * 1024))
                self.put(state, f'reports/update-big-{index}.json', b'Y' * (2 * 1024 * 1024))
        self.put(app, 'runtime/app-logs/app-42.log', 'CURRENT_STARTUP_FAILURE')
        diagnostics, entries, _ = self.run_bat(bat)
        self.assertIn('application/VERSION.txt', entries)
        self.assertEqual(entries['application/app-logs/app-42.log'], b'CURRENT_STARTUP_FAILURE')
        self.assertLessEqual(sum(row['collected_bytes'] for row in diagnostics['collected']), 16 * 1024 * 1024)
        self.assertTrue(any('size limit' in issue for issue in diagnostics['issues']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
