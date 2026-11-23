"""Managed Studio exits when actual owners disappear, not when a tab goes idle."""
from contextlib import ExitStack
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/livery-studio/src'), str(ROOT / 'KFPS.Editor/src')]
from kfps_livery_lab import launcher, studio_window


class ManagedLaunchTests(unittest.TestCase):
    def test_old_backend_is_not_silently_reused(self):
        capabilities = {key: True for key in ('native_mask_pixels', 'host_vinyl_handoff', 'host_theme_handoff',
                                              'ui_theme_persistence', 'source_editor_roundtrip')}
        capabilities.update(package_startup=1, chrome_exposed=False)
        for value in (None, True, 0, 2):
            with self.subTest(value=value):
                response = io.BytesIO(json.dumps(dict(capabilities, backend_lifetime=value)).encode())
                with patch.object(launcher, 'build_opener', return_value=SimpleNamespace(open=lambda *_a, **_k: response)):
                    with self.assertRaisesRegex(launcher.IncompatibleStudio, 'automatic backend shutdown'):
                        launcher._probe('http://127.0.0.1:1234/' + 'a' * 43 + '/', 'test.zip')

    def test_spawn_enables_managed_lifetime(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            control = root / 'runs/control'
            control.mkdir(parents=True)
            for name, value in (('LAB_ROOT', root), ('CONTROL', control), ('WORKSPACE', root / 'runs/workspace')):
                stack.enter_context(patch.object(launcher, name, value))
            spawn = stack.enter_context(patch.object(launcher.subprocess, 'Popen'))
            launcher._spawn(dict(pythonExe=sys.executable, kfpsRoot=str(root), gameRoot=str(root), archive='test.zip'))
            self.assertIn('--managed-lifetime', spawn.call_args.args[0])


class LifetimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('kfps_livery_lab.backend_lifetime')
        self.now = 0
        self.policy = self.module.LifetimePolicy(clock=lambda: self.now, startup_grace=60, disconnect_grace=5)

    def test_never_opened_backend_expires(self):
        self.now = 59
        self.assertIsNone(self.policy.observe('none'))
        self.now = 60
        self.assertEqual('unclaimed', self.policy.observe('none'))

    def test_active_native_or_chrome_owner_never_expires(self):
        for state in ('native', 'chrome'):
            for moment in (1, 1000, 100000):
                self.now = moment
                self.assertIsNone(self.policy.observe(state))

    def test_last_owner_close_waits_for_reload_grace(self):
        self.now = 70
        self.assertIsNone(self.policy.observe('native'))
        self.now = 74
        self.assertIsNone(self.policy.observe('none'))
        self.now = 75
        self.assertEqual('owner_closed', self.policy.observe('none'))

    def test_reload_and_handoff_renew_ownership(self):
        self.now = 70
        self.policy.observe('native')
        self.now = 74
        self.policy.observe('none')
        self.policy.observe('chrome')
        self.now = 78
        self.assertIsNone(self.policy.observe('none'))
        self.now = 79
        self.assertEqual('owner_closed', self.policy.observe('none'))

    def test_transient_admission_does_not_shorten_startup_allowance(self):
        self.policy.observe('native')
        self.now = 59
        self.assertIsNone(self.policy.observe('none'))
        self.now = 60
        self.assertEqual('owner_closed', self.policy.observe('none'))

    def test_unknown_ownership_is_not_permission_to_close(self):
        self.now = 600
        self.assertIsNone(self.policy.observe('unknown'))
        self.now = 604
        self.assertIsNone(self.policy.observe('none'))
        self.now = 605
        self.assertEqual('unclaimed', self.policy.observe('none'))


class ChromeOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('kfps_livery_lab.backend_lifetime')
        self.profile = Path(tempfile.gettempdir()) / 'studio-browser'
        self.chrome = Path(tempfile.gettempdir()) / 'chrome.exe'

    def process(self, args, *, pid=123, created=42):
        process = Mock()
        process.info = {'name': 'chrome.exe'}
        process.pid = pid
        process.cmdline.return_value = [str(self.chrome), *args]
        process.exe.return_value = str(self.chrome)
        process.create_time.return_value = created
        process.is_running.return_value = True
        return process

    def probe(self, processes):
        return self.module.ChromeOwnership(self.profile, self.chrome, processes=lambda: iter(processes))

    def test_exact_profile_only_and_children_do_not_own_backend(self):
        wrong = self.process([f'--user-data-dir={self.profile}-other'])
        renderer = self.process([f'--user-data-dir={self.profile}', '--type=renderer'])
        correct = self.process([f'--user-data-dir={self.profile}', '--app=http://127.0.0.1:1/'])
        self.assertFalse(self.probe([wrong, renderer]).alive())
        self.assertTrue(self.probe([wrong, renderer, correct]).alive())

    def test_executable_and_duplicate_profile_flags_must_match(self):
        wrong = self.process([f'--user-data-dir={self.profile}'])
        wrong.exe.return_value = str(self.chrome.parent / 'other.exe')
        duplicate = self.process([f'--user-data-dir={self.profile}', f'--user-data-dir={self.profile}'])
        self.assertFalse(self.probe([wrong, duplicate]).alive())

    def test_cached_identity_is_cheap_and_reused_pid_is_rechecked(self):
        first = self.process([f'--user-data-dir={self.profile}'])
        probe = self.probe([first])
        self.assertTrue(probe.alive())
        self.assertTrue(probe.alive())
        self.assertEqual(1, first.cmdline.call_count)
        first.create_time.return_value = 43
        first.cmdline.return_value = [str(self.chrome), '--user-data-dir=other']
        self.assertFalse(probe.alive())

    def test_another_live_browser_owner_survives_first_process_exit(self):
        first = self.process([f'--user-data-dir={self.profile}'])
        second = self.process([f'--user-data-dir={self.profile}'], pid=124)
        probe = self.probe([first, second])
        self.assertTrue(probe.alive())
        first.is_running.return_value = False
        first.cmdline.side_effect = psutil.NoSuchProcess(first.pid)
        self.assertTrue(probe.alive())
        second.is_running.return_value = False
        second.cmdline.side_effect = psutil.NoSuchProcess(second.pid)
        self.assertIsNone(probe.alive())

    def test_access_denied_is_unknown_not_closed(self):
        process = self.process([])
        process.cmdline.side_effect = psutil.AccessDenied(process.pid)
        self.assertIsNone(self.probe([process]).alive())

    def test_missing_process_name_is_unknown_not_closed(self):
        for info in ({}, {'name': None}, {'name': ''}):
            with self.subTest(info=info):
                process = self.process([f'--user-data-dir={self.profile}'])
                process.info = info
                self.assertIsNone(self.probe([process]).alive())

    def test_stale_non_chrome_identity_cannot_authorize_shutdown(self):
        stale = self.process([])
        stale.info = {'name': 'unrelated.exe'}
        stale.is_running.return_value = False
        self.assertIsNone(self.probe([stale]).alive())
        replacement = self.process([f'--user-data-dir={self.profile}'])
        with patch.object(psutil, 'process_iter') as iterate:
            iterate.return_value = iter([replacement])
            probe = self.module.ChromeOwnership(self.profile, self.chrome)
            self.assertTrue(probe.alive())
            iterate.cache_clear.assert_called_once()


@unittest.skipUnless(os.name == 'nt', 'Windows OS lease contract')
class NativeOwnershipTests(unittest.TestCase):
    def test_stale_browser_scan_cannot_authorize_shutdown(self):
        module = importlib.import_module('kfps_livery_lab.backend_lifetime')
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio_window, 'LAB', Path(temporary)):
            url = 'http://127.0.0.1:32190/' + 'a' * 43 + '/'
            probe = module.BackendOwnership(ROOT, Path(temporary))
            with patch.object(probe, '_chrome_alive', return_value=False), patch.object(module.time, 'monotonic', side_effect=[10, 12]):
                with probe.observe(url, chrome_exposed=True) as state:
                    self.assertEqual('unknown', state)
            with patch.object(probe, '_chrome_alive', return_value=True):
                with probe.observe(url, chrome_exposed=True) as state:
                    self.assertEqual('chrome', state)

    def test_slow_browser_scan_does_not_block_native_admission(self):
        module = importlib.import_module('kfps_livery_lab.backend_lifetime')
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio_window, 'LAB', Path(temporary)):
            url = 'http://127.0.0.1:32190/' + 'a' * 43 + '/'
            probe = module.BackendOwnership(ROOT, Path(temporary))
            entered, release = threading.Event(), threading.Event()
            observed = []
            def slow():
                entered.set()
                release.wait(3)
                return False
            def observe():
                with probe.observe(url, chrome_exposed=True) as state:
                    observed.append(state)
            with patch.object(probe, '_chrome_alive', side_effect=slow):
                thread = threading.Thread(target=observe)
                thread.start()
                owner = None
                try:
                    self.assertTrue(entered.wait(2))
                    owner = studio_window.acquire_native_owner(url)
                    time.sleep(.15)
                    release.set()
                    thread.join(3)
                    self.assertEqual(['native'], observed)
                finally:
                    release.set()
                    thread.join(3)
                    if owner:
                        owner.unlock()

    def test_live_lease_and_crash_are_detected_without_poll_log_spam(self):
        module = importlib.import_module('kfps_livery_lab.backend_lifetime')
        with tempfile.TemporaryDirectory() as temporary, patch.object(studio_window, 'LAB', Path(temporary)):
            url = 'http://127.0.0.1:32190/' + 'a' * 43 + '/'
            probe = module.BackendOwnership(ROOT, Path(temporary))
            owner = studio_window.acquire_native_owner(url)
            try:
                with probe.observe(url, chrome_exposed=False) as state:
                    self.assertEqual('native', state)
            finally:
                owner.unlock()
            with probe.observe(url, chrome_exposed=False) as state:
                self.assertEqual('none', state)
                with self.assertRaises(studio_window.NativeOwnerError):
                    studio_window.acquire_native_owner(url)
            replacement = studio_window.acquire_native_owner(url)
            replacement.unlock()


class RequestDrainTests(unittest.TestCase):
    def test_worker_start_failure_releases_admission(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from kfps_livery_lab.server import _BoundedHTTPServer
        server = _BoundedHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        try:
            with patch.object(ThreadingHTTPServer, 'process_request', side_effect=RuntimeError('cannot start worker')):
                with self.assertRaises(RuntimeError):
                    server.process_request(Mock(), ('127.0.0.1', 1))
            self.assertEqual(0, server.active_requests)
            self.assertTrue(server.stop_if_idle())
            for _ in range(8):
                self.assertTrue(server.slots.acquire(blocking=False))
        finally:
            server.server_close()

    def test_shutdown_cannot_cut_off_an_inflight_request(self):
        from http.server import BaseHTTPRequestHandler
        from http.client import HTTPConnection
        from kfps_livery_lab.server import _BoundedHTTPServer
        entered, release = threading.Event(), threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                entered.set()
                release.wait(5)
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')
            def log_message(self, *_args):
                pass
        server = _BoundedHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        try:
            connection.request('GET', '/')
            self.assertTrue(entered.wait(3))
            self.assertFalse(server.stop_if_idle())
            release.set()
            self.assertEqual(b'ok', connection.getresponse().read())
            self.assertFalse(server.stop_if_idle(min_idle=10))
            deadline = time.monotonic() + 3
            while not server.stop_if_idle() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(server.stop_if_idle())
        finally:
            release.set()
            connection.close()
            server.shutdown()
            thread.join(5)
            server.server_close()


class LifetimeDiagnosticsTests(unittest.TestCase):
    def test_lifecycle_diagnostics_remain_allowlisted(self):
        from kfps_livery_lab.diagnostics import sanitize_event
        value = dict(event='lifetime', host='backend', owner_state='none', shutdown_reason='owner_closed')
        self.assertEqual(value, sanitize_event(value))
        self.assertIsNone(sanitize_event(dict(value, url='http://127.0.0.1/private')))
        self.assertIsNone(sanitize_event(dict(value, owner_state='arbitrary text')))


if __name__ == '__main__':
    unittest.main()
