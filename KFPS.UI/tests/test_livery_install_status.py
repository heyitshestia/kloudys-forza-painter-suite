from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]

from PySide6.QtCore import QCoreApplication, QObject, Signal
from kfps_ui.app_paths import AppPaths
from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.log_service import LogService
from kfps_ui.workspace_tasks import TaskJournal


def confirmation_result(root, user=123, version=1):
    # Controlled worker fixture; real directory binding is tested separately.
    account = Path(root) / f"u_{user}_16D460"
    containers = account / str(version) / "ContainersRoot"
    expected = {"schema": "kfps-fh6-destination-v1", "directory": str(account),
                "containers": str(containers), "user_id": str(user), "manifest_sha256": "a" * 64,
                "directory_id": [1, 2], "version_id": [1, 3], "containers_id": [1, 4]}
    return {"account": str(account), "user_id": str(user), "containers": str(containers),
            "expected_destination": expected}


class ControlledTasks(QObject):
    completed = Signal(object)
    stateChanged = Signal()
    progress = Signal(object)

    def __init__(self, *args):
        super().__init__()
        self.running = False
        self.current_operation = ""
        self.requests = []
        self.reject = set()

    def start(self, operation, payload, *, kind=None, metadata=None, **kwargs):
        if operation in self.reject:
            return False
        self.requests.append({"kind": kind or operation, "input": payload, **(metadata or {})})
        self.current_operation = operation
        self.running = True
        self.stateChanged.emit()
        return True

    def finish(self, payload=None, **result):
        request = self.requests[-1]
        self.running = False
        self.current_operation = ""
        self.stateChanged.emit()
        self.completed.emit({**request, "ok": True, "value": payload or {}, **result})

    def cancel(self, *args, **kwargs):
        pass

    def close(self):
        self.running = False


class LiveryInstallStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="install-status-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        paths = AppPaths(self.root, UI, UI / "qml", UI / "assets",
                         self.root / "runtime", Path(sys.executable))
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
                patch("kfps_ui.full_livery_service.FullLiveryTaskSupervisor", ControlledTasks):
            self.service = FullLiveryService(paths, LogService(), demo=True)
        self.addCleanup(self.service.close)
        self.tasks = self.service._tasks
        self.service._gate = FullLiveryFeatureGate("candidate", "test")
        self.service._active = True
        self.service._game_folder = str(self.root / "synthetic-game")
        self.package = self.root / "installed.kfpslivery"
        self.package.write_bytes(b"synthetic: worker operations must not execute")
        self.service._selected_package = str(self.package)
        self.service._current_manifest = {
            "package_id": "installed", "sharing": {"exportable": True},
            "files": [{"path": "source/fh6/header"}],
            "livery": {"title": "Status fixture", "target_car_id": 344},
        }
        compatibility = patch("kfps_ui.full_livery_service.compatibility_decision",
                              return_value={"installable": True})
        compatibility.start()
        self.addCleanup(compatibility.stop)
        self.service.prepareInstallSelectedPackage()
        self.tasks.finish(confirmation_result(self.root))
        self.assertTrue(self.service.installConfirmationCurrent)
        self.tasks.requests.clear()
        self.states = []
        self.service.changed.connect(lambda: self.states.append(
            (self.service.status, self.service.summary, self.service.running)))

    def install(self):
        self.service.installSelectedPackage()
        self.assertEqual("install", self.tasks.requests[-1]["kind"])
        self.tasks.finish({"title": "Status fixture", "installed_folder": "synthetic-entry",
                           "backup_path": "synthetic-receipt"})

    def finish_scan(self, **payload):
        self.assertEqual("scan", self.tasks.requests[-1]["kind"])
        self.tasks.finish({"rows": [{"path": str(self.root / "C_livery"),
                                     "title": "Status fixture", "carId": 344}],
                           "game_assets_ready": True, "inspected": 1, **payload})

    def finish_index(self):
        self.assertEqual("refresh-packages", self.tasks.requests[-1]["kind"])
        self.tasks.finish({"rows": [{"path": str(self.package), "title": "Status fixture",
                                     "carId": 344}], "cache_hits": 1})

    def assert_install_summary(self, summary):
        self.assertEqual(summary, self.service._summary)
        self.assertEqual(summary + "\nDestination: FH6 account 123, current save 1.", self.service.summary)

    def journal(self):
        journal = TaskJournal()
        self.addCleanup(journal.close)
        journal.watch("liveries", self.service, label="Livery processing", page="liveries", detail="summary")
        return journal

    def test_local_task_history_retains_destination_during_install_and_after_refresh(self):
        journal = self.journal()
        self.service.installSelectedPackage()
        label = "Destination: FH6 account 123, current save 1."
        active = journal.rows[0]
        self.assertTrue(active["running"])
        self.assertIn(label, active["detail"])
        self.assertNotIn(label, str(self.tasks.requests[-1]["install_notice"]))
        self.tasks.finish({"title": "Status fixture", "installed_folder": "synthetic-entry"})
        self.finish_scan()
        self.finish_index()
        self.app.processEvents()
        installed = next(row for row in journal.rows if row["id"] == active["id"])
        self.assertFalse(installed["running"])
        self.assertEqual("FH6 livery installed", installed["status"])
        self.assertIn(label, installed["detail"])
        self.service.scanSaves()
        self.assertNotIn("Destination:", self.service.summary)
        self.assertNotIn("Destination:", journal.rows[0]["detail"])
        self.assertIn(label, next(row for row in journal.rows if row["id"] == active["id"])["detail"])

    def test_local_task_failure_history_retains_destination_without_changing_error(self):
        journal = self.journal()
        self.service.installSelectedPackage()
        self.tasks.finish(ok=False, error="Confirmed destination changed")
        self.app.processEvents()
        row = journal.rows[0]
        self.assertFalse(row["running"])
        self.assertEqual("Full-livery task failed", row["status"])
        self.assert_install_summary("Confirmed destination changed")
        self.assertEqual(self.service.summary, row["detail"])
        self.assertNotIn("Destination:", self.service.log.plainText)

    def test_success_survives_scan_and_index_with_models_and_selection_intact(self):
        self.install()
        self.assertEqual("FH6 livery installed", self.service.status)
        summary = self.service.summary
        self.assertIn("Status fixture", summary)
        self.assertTrue(self.service.running)
        self.finish_scan()
        self.assertEqual("FH6 livery installed", self.service.status)
        self.assertEqual(summary, self.service.summary)
        self.assertTrue(self.service.running)
        self.assertEqual(1, self.service.sourceCount)
        self.finish_index()
        self.assertEqual(("FH6 livery installed", summary, False), self.states[-1])
        self.assertEqual(1, self.service.packageCount)
        self.assertEqual(str(self.package), self.service.selectedPackage)
        self.assertTrue(self.service.selectedPackageInstallable)
        completed = next(i for i, state in enumerate(self.states) if state[0] == "FH6 livery installed")
        self.assertTrue(all(state[:2] == ("FH6 livery installed", summary)
                            for state in self.states[completed:]))

    def test_install_failure_does_not_scan_or_report_success(self):
        self.service.installSelectedPackage()
        self.tasks.finish(ok=False, error="Installation verification failed")
        self.assertEqual(1, len(self.tasks.requests))
        self.assertEqual("Full-livery task failed", self.service.status)
        self.assert_install_summary("Installation verification failed")
        self.assertFalse(self.service.running)

    def test_install_cancel_does_not_scan_or_report_success(self):
        self.service.installSelectedPackage()
        self.tasks.finish(ok=False, cancelled=True, error="Stopped before commit")
        self.assertEqual(1, len(self.tasks.requests))
        self.assertEqual("Full-livery task cancelled", self.service.status)
        self.assert_install_summary("Stopped before commit")
        self.assertFalse(self.service.running)

    def test_scan_failure_replaces_success_and_stops_refresh_chain(self):
        self.install()
        self.tasks.finish(ok=False, error="Save index unavailable")
        self.assertEqual(2, len(self.tasks.requests))
        self.assertEqual("Full-livery task failed", self.service.status)
        self.assert_install_summary("Save index unavailable")
        self.assertFalse(self.service.running)

    def test_package_index_failure_replaces_success(self):
        self.install()
        self.finish_scan()
        self.tasks.finish(ok=False, error="Package index unavailable")
        self.assertEqual("Full-livery task failed", self.service.status)
        self.assert_install_summary("Package index unavailable")
        self.assertFalse(self.service.running)

    def test_scan_cancel_is_visible(self):
        self.install()
        self.tasks.finish(ok=False, cancelled=True, error="Refresh cancelled")
        self.assertEqual("Full-livery task cancelled", self.service.status)
        self.assert_install_summary("Refresh cancelled")
        self.assertFalse(self.service.running)
        self.assertEqual(2, len(self.tasks.requests))

    def test_package_index_cancel_is_visible(self):
        self.install()
        self.finish_scan()
        self.tasks.finish(ok=False, cancelled=True, error="Index cancelled")
        self.assertEqual("Full-livery task cancelled", self.service.status)
        self.assert_install_summary("Index cancelled")
        self.assertFalse(self.service.running)

    def test_stale_save_warning_survives_package_indexing(self):
        self.install()
        self.finish_scan(stale_index=True, warning="Configured save folder unavailable")
        self.assertEqual("Showing last complete livery index", self.service.status)
        self.assert_install_summary("Configured save folder unavailable")
        self.finish_index()
        self.assertEqual("Showing last complete livery index", self.service.status)
        self.assert_install_summary("Configured save folder unavailable")

    def test_missing_game_assets_warning_survives_package_indexing(self):
        self.install()
        self.finish_scan(game_assets_ready=False, game_asset_error="Synthetic missing assets")
        self.assertEqual("FH6 folder required", self.service.status)
        self.assertIn("Synthetic missing assets", self.service.summary)
        summary = self.service.summary
        self.finish_index()
        self.assertEqual("FH6 folder required", self.service.status)
        self.assertEqual(summary, self.service.summary)

    def test_empty_scan_warning_survives_package_indexing(self):
        self.install()
        self.finish_scan(rows=[], warning="Save discovery unavailable")
        self.assert_install_summary("Save discovery unavailable")
        self.finish_index()
        self.assert_install_summary("Save discovery unavailable")

    def test_second_install_is_blocked_while_either_refresh_is_running(self):
        self.install()
        self.service.installSelectedPackage()
        self.assertEqual(2, len(self.tasks.requests))
        self.finish_scan()
        self.service.installSelectedPackage()
        self.assertEqual(3, len(self.tasks.requests))
        self.finish_index()
        self.assertFalse(self.service.running)

    def test_manual_scan_after_completion_has_ordinary_status(self):
        self.install()
        self.finish_scan()
        self.finish_index()
        self.service.scanSaves()
        self.assertEqual("Scanning FH6 liveries", self.service.status)
        self.finish_scan()
        self.assertEqual("Indexing saved livery packages", self.service.status)
        self.finish_index()
        self.assertEqual("Full-livery index ready", self.service.status)
        self.assertIn("Indexed 1 saved packages", self.service.summary)

    def test_manual_package_refresh_does_not_reuse_install_notice(self):
        self.install()
        self.finish_scan()
        self.finish_index()
        self.service.refreshPackages()
        self.assertEqual("Indexing saved livery packages", self.service.status)
        self.finish_index()
        self.assertEqual("Full-livery index ready", self.service.status)

    def test_late_scan_cannot_replace_new_selection_or_clear_its_running_state(self):
        self.install()
        old_scan = self.tasks.requests[-1]
        other = self.root / "other.kfpslivery"
        other.write_bytes(b"synthetic")
        self.assertTrue(self.service.selectPackage(str(other)))
        state = (self.service.status, self.service.summary, self.service.running)
        self.tasks.completed.emit({**old_scan, "ok": True, "value": {"rows": []}})
        self.assertEqual(state, (self.service.status, self.service.summary, self.service.running))
        self.assertEqual(str(other), self.service.selectedPackage)
        self.assertTrue(self.service.running)
        self.assertEqual("open-package", self.tasks.requests[-1]["kind"])

    def test_late_index_cannot_restore_success_after_returning_to_grid(self):
        self.install()
        self.finish_scan()
        self.service.showSourceGrid()
        self.finish_index()
        self.assertEqual("Livery browser", self.service.status)
        self.assertEqual("Local FH6 liveries", self.service.summary)
        self.assertEqual("", self.service.selectedPackage)
        self.assertFalse(self.service.selectedPackageInstallable)
        self.assertFalse(self.service.running)

    def test_page_close_before_install_result_preserves_paused_state(self):
        self.service.installSelectedPackage()
        self.service.deactivate()
        self.tasks.finish({"title": "Status fixture"})
        self.assertEqual("Experimental workspace paused", self.service.status)
        self.assertFalse(self.service.running)
        self.assertEqual(1, len(self.tasks.requests))

    def test_page_close_during_scan_preserves_paused_state(self):
        self.install()
        self.service.deactivate()
        self.finish_scan()
        self.assertEqual("Experimental workspace paused", self.service.status)
        self.assertFalse(self.service.running)
        self.assertEqual(2, len(self.tasks.requests))

    def test_newer_viewer_failure_is_not_hidden_by_successful_scan(self):
        self.install()
        self.service._inspector_failed("Synthetic viewer error")
        self.finish_scan()
        self.assertEqual("3D viewer failed", self.service.status)
        self.assertEqual("Synthetic viewer error", self.service.summary)
        self.assertEqual(2, len(self.tasks.requests))

    def test_refresh_failure_is_not_suppressed_by_newer_status_on_same_selection(self):
        self.install()
        self.service._inspector_failed("Synthetic viewer error")
        self.tasks.finish(ok=False, error="Scan also failed")
        self.assertEqual("Full-livery task failed", self.service.status)
        self.assert_install_summary("Scan also failed")

    def test_rejected_scan_start_reports_busy_without_stuck_running(self):
        self.tasks.reject.add("scan-saves")
        self.install()
        self.assertEqual("Livery worker busy", self.service.status)
        self.assertFalse(self.service.running)
        self.assertEqual(1, len(self.tasks.requests))

    def test_rejected_index_start_reports_busy_without_stuck_running(self):
        self.install()
        self.tasks.reject.add("refresh-packages")
        self.finish_scan()
        self.assertEqual("Package index busy", self.service.status)
        self.assertFalse(self.service.running)
        self.assertEqual(2, len(self.tasks.requests))

    def test_changed_destination_does_not_restore_old_install_notice(self):
        self.install()
        self.service._save_root = str(self.root / "different-save-root")
        self.service._status = "Different save destination"
        self.service._summary = "New destination selected"
        self.finish_scan()
        self.assertEqual("Different save destination", self.service.status)
        self.assertEqual("New destination selected", self.service.summary)
        self.assertEqual(2, len(self.tasks.requests))


if __name__ == "__main__":
    unittest.main()
