import gc
import unittest
import weakref
from PySide6.QtCore import QObject, Signal, QCoreApplication
from kfps_ui.workspace_tasks import TaskJournal


class Source(QObject):
    changed = Signal()
    running = False
    status = "Ready"


class TaskJournalTests(unittest.TestCase):
    def setUp(self):
        self.source = Source()
        self.journal = TaskJournal(limit=3)
        self.cancelled = []
        self.journal.watch("scan", self.source, label="Scan", page="outputs",
                           cancel=lambda: self.cancelled.append(True))

    def tearDown(self):
        self.journal.close()

    def change(self, running, status):
        self.source.running, self.source.status = running, status
        self.source.changed.emit()

    def test_idle_registration_is_not_a_completed_task(self):
        self.assertEqual([], self.journal.rows)

    def test_stage_and_attempt_identity(self):
        self.change(True, "Reading")
        first = self.journal.rows[0]["id"]
        self.change(True, "Verifying")
        self.assertEqual(first, self.journal.rows[0]["id"])
        self.change(False, "Failed: input missing")
        self.assertEqual("Failed: input missing", self.journal.rows[0]["status"])
        self.assertFalse(self.journal.rows[0]["running"])
        self.change(True, "Reading again")
        self.assertNotEqual(first, self.journal.rows[0]["id"])
        self.assertFalse(self.journal.act(first, "cancel"))

    def test_capabilities_rechecked(self):
        self.change(True, "Reading")
        token = self.journal.rows[0]["id"]
        self.assertTrue(self.journal.act(token, "cancel"))
        self.assertEqual([True], self.cancelled)
        self.change(False, "Cancelled")
        self.assertFalse(self.journal.act(token, "cancel"))
        self.assertFalse(self.journal.act(token, "retry"))

    def test_history_bounded_without_evicting_active(self):
        for i in range(8):
            self.change(True, str(i))
            self.change(False, "Done")
        self.assertEqual(3, len(self.journal.rows))

    def test_cancel_callback_failure_does_not_claim_cancelled(self):
        def fail():
            raise OSError("Cannot stop")
        self.journal._sources["scan"]["cancel"] = fail
        self.change(True, "Working")
        self.assertFalse(self.journal.act(self.journal.rows[0]["id"], "cancel"))
        self.assertTrue(self.journal.rows[0]["running"])
        self.assertEqual("Working", self.journal.rows[0]["status"])

    def test_unknown_actions_cannot_dispatch(self):
        self.change(True, "Working")
        self.assertFalse(self.journal.act(self.journal.rows[0]["id"], "close"))

    def test_terminal_status_after_busy_signal_is_retained_then_frozen(self):
        self.change(True, "Reading")
        self.change(False, "Reading")
        self.change(False, "Failed: result could not be read")
        QCoreApplication.processEvents()
        self.assertEqual('Failed: result could not be read', self.journal.rows[0]['status'])
        self.change(False, 'Ready for another file')
        self.assertEqual('Failed: result could not be read', self.journal.rows[0]['status'])

    def test_close_disconnects_live_source_and_releases_journal(self):
        journal = TaskJournal()
        journal.watch('other', self.source, label='Other', page='outputs')
        reference = weakref.ref(journal)
        journal.close()
        del journal
        gc.collect()
        self.assertIsNone(reference(), 'A live source must not retain a closed journal')
        self.source.changed.emit()

    def test_multiple_sources_settle_without_postponing_pending_flush(self):
        other = Source()
        self.journal.watch('other', other, label='Other', page='outputs')
        self.change(True, 'Scanning')
        other.running = True
        other.changed.emit()
        self.change(False, 'Scanning')
        timer_id = self.journal._settle_timer.timerId()
        other.running = False
        other.changed.emit()
        self.assertEqual(timer_id, self.journal._settle_timer.timerId())
        self.source.status = 'Scan failed'
        other.status = 'Other finished'
        QCoreApplication.processEvents()
        self.assertEqual({row['source']: row['status'] for row in self.journal.rows},
                         {'scan': 'Scan failed', 'other': 'Other finished'})
        self.assertFalse(self.journal._settle_timer.isActive())

    def test_retry_before_flush_does_not_change_previous_attempt(self):
        self.change(True, 'First')
        self.change(False, 'First failed')
        previous = self.journal.rows[0]['id']
        self.change(True, 'Retrying')
        QCoreApplication.processEvents()
        old = next(row for row in self.journal.rows if row['id'] == previous)
        self.assertEqual(old['status'], 'First failed')
        self.assertEqual(self.journal.rows[0]['status'], 'Retrying')

    def test_close_before_flush_does_not_deliver_settled_status(self):
        self.change(True, 'Reading')
        self.change(False, 'Reading')
        self.journal.close()
        self.source.status = 'Late completion'
        self.source.changed.emit()
        QCoreApplication.processEvents()
        self.assertEqual(self.journal.rows[0]['status'], 'Reading')
        self.assertFalse(self.journal._settle_timer.isActive())

    def test_completion_during_flush_is_not_lost(self):
        other = Source()
        self.journal.watch('other', other, label='Other', page='outputs')
        self.change(True, 'First')
        other.running = True
        other.changed.emit()
        self.change(False, 'First done')
        fired = []

        def complete_other():
            if not fired:
                fired.append(True)
                other.running = False
                other.status = 'Second done'
                other.changed.emit()

        self.journal.changed.connect(complete_other)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertEqual({row['source']: row['status'] for row in self.journal.rows},
                         {'scan': 'First done', 'other': 'Second done'})
        self.assertTrue(all(config['settling'] is None for config in self.journal._sources.values()))


if __name__ == "__main__":
    unittest.main()
