import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from kfps_ui.generation_service import GenerationService


class GenerationControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.paths = SimpleNamespace(app_root=root, runtime_root=root/'runtime', ui_root=root,
                                     python_executable='not-run.exe')
        with patch.object(GenerationService, '_load_presets', return_value=['Test']):
            self.service = GenerationService(self.paths, Mock())
        self.addCleanup(self.service.close)

    def test_stop_queue_keeps_current_checkpoint_finish_and_removes_pending(self):
        s = self.service
        s._running = True
        s._queue = [('next',)]
        s._queue_total = 2
        with patch.object(s, 'gracefulStop') as stop:
            s.cancelQueue()
        self.assertEqual([], s._queue)
        self.assertTrue(s._running)
        stop.assert_called_once()

    def test_retry_only_failed_jobs_and_not_completed_ones(self):
        s = self.service
        s._failed_jobs = [('failed-a',), ('failed-b',)]
        with patch.object(s, '_start_single') as start:
            s.retryFailed()
        start.assert_called_once_with('failed-a')
        self.assertEqual([('failed-b',)], s._queue)
        self.assertEqual([], s._failed_jobs)

    def test_running_retry_is_rejected(self):
        s = self.service
        s._running = True
        s._failed_jobs = [('failed',)]
        with patch.object(s, '_start_single') as start:
            s.retryFailed()
        start.assert_not_called()

    def test_mixed_queue_does_not_report_complete_after_earlier_failure(self):
        s = self.service
        s._running = True
        s._failed_jobs = [('failed',)]
        s._active_job = ('success',)
        with patch.object(s, 'refreshPreview'):
            s._finished(0, None)
        self.assertEqual('Finished with 1 failed image(s)', s.status)
        self.assertTrue(s.canRetryFailed)

    def test_failed_stop_request_keeps_pending_queue(self):
        s = self.service
        s._running = True
        s._run_dir = str(self.paths.app_root)
        s._queue = [('next',)]
        s._queue_total = 2
        with patch.object(Path, 'write_text', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(RuntimeError, 'queue was kept'):
                s.cancelQueue()
        self.assertFalse(s._queue_cancelled)
        self.assertEqual([('next',)], s._queue)
        self.assertEqual(2, s._queue_total)

    def test_failure_after_accepted_stop_remains_retryable(self):
        s = self.service
        s._running = True
        s._run_dir = str(self.paths.app_root)
        s._active_job = ('failed-finalization',)
        s.cancelQueue()
        with patch.object(s, 'refreshPreview'):
            s._finished(7, None)
        self.assertEqual('Finished with 1 failed image(s)', s.status)
        self.assertTrue(s.canRetryFailed)


if __name__ == '__main__':
    unittest.main()
