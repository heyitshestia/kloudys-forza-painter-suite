from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'KFPS.UI/src')]
from kfps_ui.activity_service import ActivityService
from tools.kfps_activity import PRIVACY_TEXT
from tools.kfps_activity_host import ActivityHost


class Counter:
    def __init__(self):
        self.value = True
        self.started = self.stopped = 0
        self.writable = True

    def enabled(self):
        return self.value

    def set_enabled(self, value):
        if not self.writable:
            return False
        self.value = value
        return True

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class ActivityHostTests(unittest.TestCase):
    def test_counter_construction_failure_does_not_block_host(self):
        with patch('tools.kfps_activity_host.ActivityCounter', side_effect=RuntimeError('unavailable')):
            host = ActivityHost(ROOT)
            service = ActivityService(ROOT)
        self.assertFalse(host.start())
        self.assertFalse(host.enabled())
        self.assertFalse(host.set_enabled(False))
        host.stop()
        service.start()
        service.close()

    def test_optional_counter_method_failures_never_escape(self):
        counter = Mock()
        for name in ('start', 'stop', 'enabled', 'set_enabled'):
            getattr(counter, name).side_effect = RecursionError('malformed optional state')
        service = ActivityService(ROOT, counter=counter)
        self.assertFalse(service.enabled)
        service.refresh()
        self.assertFalse(service.setEnabled(False))
        service.start()
        service.close()
        self.assertEqual(counter.stop.call_count, 1)

    def test_construct_and_read_settings_do_not_start_worker(self):
        counter = Counter()
        service = ActivityService(ROOT, counter=counter)
        self.assertTrue(service.enabled)
        self.assertEqual(service.privacyText, PRIVACY_TEXT)
        service.refresh()
        self.assertEqual(counter.started, 0)
        self.assertEqual(counter.stopped, 0)

    def test_ready_once_close_once_and_no_restart(self):
        counter = Counter()
        service = ActivityService(ROOT, counter=counter)
        service.start()
        service.start()
        self.assertEqual(counter.started, 1)
        service.close()
        service.close()
        service.start()
        self.assertEqual(counter.started, 1)
        self.assertEqual(counter.stopped, 1)

    def test_shared_preference_refresh_and_write_failure(self):
        counter = Counter()
        service = ActivityService(ROOT, counter=counter)
        self.assertTrue(service.setEnabled(False))
        self.assertFalse(service.enabled)
        counter.value = True
        service.refresh()
        self.assertTrue(service.enabled)
        counter.writable = False
        self.assertFalse(service.setEnabled(False))
        self.assertTrue(service.enabled)
        self.assertIn('not saved', service.status)
        self.assertEqual(counter.started, 0)

    def test_readiness_hook_waits_for_actual_frame_without_focus_calls(self):
        qml = (ROOT / 'KFPS.UI/qml/components/ActivityStartup.qml').read_text(encoding='utf-8')
        self.assertIn('onFrameSwapped', qml)
        self.assertIn('root.ready', qml)
        for forbidden in ('activate', 'raise', 'forceActiveFocus', 'Component.onCompleted'):
            self.assertNotIn(forbidden, qml)
        main = (ROOT / 'KFPS.UI/qml/Main.qml').read_text(encoding='utf-8')
        self.assertIn('ActivityStartup {', main)
        self.assertIn('!screenshotMode', main.split('ActivityStartup {', 1)[1].split('}', 1)[0])


if __name__ == '__main__':
    unittest.main()
