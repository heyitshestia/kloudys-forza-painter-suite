"""Shutdown must follow exact backend identity and live document ownership."""
from contextlib import ExitStack, nullcontext
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/livery-studio/src'))
from kfps_livery_lab import launcher


class StudioBackendShutdownTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.workspace = self.root / 'runs/workspace'
        self.config = {'kfpsRoot': str(self.root), 'gameRoot': 'OLD_GAME',
                       'pythonExe': 'python.exe', 'archive': 'OLD.zip'}
        self.expected = {'pid': 123, 'created': 12.0, 'workspace': str(self.workspace),
                         'managed': True, 'url': 'http://127.0.0.1:1234/' + 'a'*43 + '/'}
        self.record = {**self.expected, 'launch_config': self.config}
        self.ready = {**self.expected, 'chrome_exposed': False}
        self.window = SimpleNamespace(native_admission=Mock(return_value=nullcontext()))
        for name, value in [('LAB_ROOT', self.root), ('CONTROL', self.root/'runs/control'),
                            ('WORKSPACE', self.workspace)]:
            self.stack.enter_context(patch.object(launcher, name, value))
        self.patch('_launch_lock', return_value=nullcontext())
        self.patch('_read_json', side_effect=lambda *_: copy.deepcopy(self.record))
        self.patch('_registration_alive', return_value=True)
        self.patch('validate_config', side_effect=lambda value, *_: value)
        self.patch('_ready_record', side_effect=lambda *_args, **_kwargs: copy.deepcopy(self.ready))
        self.patch('_window_module', return_value=self.window)
        self.stop = self.patch('_terminate_owned', return_value=True)
        self.write = self.patch('_atomic_json')

    def patch(self, name, **kwargs):
        return self.stack.enter_context(patch.object(launcher, name, **kwargs))

    def run_stop(self):
        return launcher.stop_workspace_backend(self.expected, expected_kfps_root=self.root)

    def test_exact_backend_stops_using_registered_not_current_game_configuration(self):
        with patch.object(launcher, 'load_config', side_effect=AssertionError('Do not load newly selected game')):
            self.assertEqual('stopped', self.run_stop())
        self.stop.assert_called_once_with(123, 12.0, self.config, str(self.workspace), include_children=False)
        self.write.assert_called_once()
        self.window.native_admission.assert_called_once_with(self.ready['url'])

    def test_rotation_uses_current_token_and_never_a_stale_handoff_fragment(self):
        self.expected['url'] += '#layout=' + '0'*32
        self.ready['url'] = 'http://127.0.0.1:1234/' + 'b'*43 + '/'
        self.assertEqual('stopped', self.run_stop())
        self.window.native_admission.assert_called_once_with(self.ready['url'])

    def test_other_registration_or_unmanaged_backend_is_not_stopped(self):
        for change in ({'pid': 124}, {'created': 13.0}, {'workspace': str(self.root/'runs/other')}, {'managed': False}):
            with self.subTest(change=change):
                self.record = {**self.expected, 'launch_config': self.config, **change}
                self.assertEqual('not-owned', self.run_stop())
        self.stop.assert_not_called()

    def test_chrome_shared_or_unknown_readiness_is_retained(self):
        for flag in (True, None):
            self.ready['chrome_exposed'] = flag
            with self.subTest(flag=flag):
                self.assertEqual('shared', self.run_stop())
        self.patch('_ready_record', return_value=None)
        self.assertEqual('unavailable', self.run_stop())
        self.stop.assert_not_called()

    def test_existing_native_owner_blocks_shutdown(self):
        self.window.native_admission.side_effect = RuntimeError('Another document owns this backend')
        self.assertEqual('in-use', self.run_stop())
        self.stop.assert_not_called()

    def test_chrome_opened_between_probe_and_lease_is_preserved(self):
        self.patch('_ready_record', side_effect=[self.ready, {**self.ready, 'chrome_exposed': True}])
        self.assertEqual('shared', self.run_stop())
        self.stop.assert_not_called()

    def test_missing_registered_game_is_not_misreported_as_exited(self):
        self.patch('validate_config', side_effect=FileNotFoundError)
        self.assertEqual('unavailable', self.run_stop())
        self.stop.assert_not_called()

    def test_stop_failure_does_not_clear_registration(self):
        self.stop.return_value = False
        self.assertEqual('failed', self.run_stop())
        self.write.assert_not_called()

    def test_already_exited_and_invalid_identity_never_stop_other_processes(self):
        self.patch('_registration_alive', return_value=False)
        self.assertEqual('gone', self.run_stop())
        for change in ({'created': None}, {'created': float('nan')}, {'pid': True}, {'workspace': '../outside'}):
            self.expected.update(change)
            self.assertEqual('not-owned', self.run_stop())
        self.stop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
