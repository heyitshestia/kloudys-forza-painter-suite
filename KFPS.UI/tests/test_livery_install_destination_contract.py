"""Destination confirmation and Garage independence, with no real save access."""
import copy
import gzip
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/src")]

from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.experimental.full_livery import jobs
from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
from kfps_ui.full_livery_service import FullLiveryService
from kfps_ui.garage_reader import scan
from kfps_ui.garage_service import GarageService
from kfps_ui.log_service import LogService
from tools.cgroup import fh6_identity
from tools.livery import fh6_save_installer as installer
from test_garage_index import car
from test_livery_install_status import ControlledTasks, confirmation_result


class InstallDestinationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="install-destination-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        ui = ROOT / "KFPS.UI"
        paths = AppPaths(self.root, ui, ui / "qml", ui / "assets", self.root / "runtime", Path(sys.executable))
        log = LogService()
        self.addCleanup(log.close)
        with patch("kfps_ui.full_livery_service.discover_fh6_game_folder", return_value=None), \
                patch("kfps_ui.full_livery_service.FullLiveryTaskSupervisor", ControlledTasks):
            self.liveries = FullLiveryService(paths, log, demo=True)
        self.addCleanup(self.liveries.close)
        self.liveries._gate = FullLiveryFeatureGate("candidate", "test")
        self.liveries._active = True
        self.liveries._game_folder = str(self.root / "synthetic-game")
        package = self.root / "fixture.kfpslivery"
        package.write_bytes(b"fixture: installer is mocked")
        self.liveries._selected_package = str(package)
        self.manifest = {"sharing": {"exportable": True}, "files": [{"path": "source/fh6/header"}],
                         "livery": {"target_car_id": 344}, "vehicle": {"model_code": "TEST_CAR"}}
        self.liveries._current_manifest = self.manifest
        compatibility = patch("kfps_ui.full_livery_service.compatibility_decision", return_value={"installable": True})
        compatibility.start()
        self.addCleanup(compatibility.stop)
        self.tasks = self.liveries._tasks
        self.resolved = confirmation_result(self.root, user=456)
        self.ready = []
        self.liveries.installConfirmationReady.connect(lambda: self.ready.append(True))
        self.garage = GarageService(paths, log, self.liveries)
        self.addCleanup(self.garage.close)
        self.source = self.root / "synthetic-garage.json"
        self.source.write_text(json.dumps([car()]), encoding="utf-8")
        self.account = {"id": "garage-account", "label": "Garage fixture",
                        "directory": str(self.root / "garage-account"), "available": True}
        self.garage._accounts = [self.account]

    def select_garage_account(self):
        def read_selected(_source, *, account):
            result = scan(self.source, self.garage.store, self.root / "unused-reader.json", threading.Event())
            result["account"] = {key: account[key] for key in ("id", "label", "directory")}
            self.garage._apply(result)
        with patch.object(self.garage, "_scan_source", side_effect=read_selected):
            self.garage.selectAccount(self.account["id"])
        self.assertEqual(self.account["id"], self.garage.selectedAccountId)

    def prepare(self):
        self.liveries.prepareInstallSelectedPackage()
        self.assertEqual("install-destination", self.tasks.requests[-1]["kind"])
        self.tasks.finish(self.resolved)
        self.assertTrue(self.liveries.installConfirmationCurrent)

    def worker_destination(self):
        self.prepare()
        self.liveries.installSelectedPackage()
        self.assertEqual("install", self.tasks.requests[-1]["kind"])
        payload = self.tasks.requests[-1]["input"]
        result = SimpleNamespace(installed_folder=self.root / "not-written", backup_path=self.root / "not-written",
                                 title="Fixture", car_id=344, model_code="TEST_CAR", placement_count=1)
        paths = SimpleNamespace(vehicle_index=self.root / "unused-index", recovery=self.root / "unused-recovery")
        with patch.object(jobs, "validate_full_livery_package", return_value=self.manifest), \
                patch.object(jobs, "load_or_build_vehicle_asset_index", return_value={344: SimpleNamespace(model_code="TEST_CAR")}), \
                patch.object(jobs, "_scan_roots", return_value=[]) as roots, \
                patch.object(jobs, "install_full_livery_package", return_value=result) as install:
            jobs.install_package(paths, payload, threading.Event())
        roots.assert_called_once_with(payload["save_root"])
        self.assertEqual(self.resolved["expected_destination"], install.call_args.kwargs["expected_destination"])
        return payload, install.call_args.kwargs["destination"]

    def test_selected_garage_account_does_not_replace_explicit_livery_destination(self):
        destination = str(self.root / "explicit-install-account")
        self.liveries._save_root = destination
        self.select_garage_account()
        payload, target = self.worker_destination()
        self.assertEqual(destination, self.tasks.requests[0]["input"]["save_root"])
        self.assertEqual(self.resolved["containers"], payload["save_root"])
        self.assertEqual(self.resolved["containers"], target)
        self.assertEqual(destination, self.liveries._save_root)
        self.assertNotEqual(self.account["directory"], target)

    def test_selected_garage_account_does_not_supply_unconfigured_destination(self):
        self.select_garage_account()
        payload, target = self.worker_destination()
        self.assertEqual("", self.tasks.requests[0]["input"]["save_root"])
        self.assertEqual(self.resolved["containers"], target)
        self.assertEqual("", self.liveries._save_root)

    def test_confirmation_discloses_automatic_mode_account_folder_and_garage_independence(self):
        self.prepare()
        description = self.liveries.installDestinationDescription
        for text in ("Automatically selected", "verified last-save", "only verified account",
                     "u_456_16D460", "ID 456", self.resolved["containers"],
                     "My Cars does not select this destination", "Cancel and choose FH6 Save Folder"):
            self.assertIn(text, description)
        self.assertEqual([True], self.ready)

    def test_confirmation_discloses_explicit_selection_mode(self):
        self.liveries._save_root = str(self.root / "chosen-root")
        self.prepare()
        self.assertIn("Resolved from your selected FH6 Save Folder", self.liveries.installDestinationDescription)
        self.assertNotIn("Automatically selected", self.liveries.installDestinationDescription)

    def test_direct_install_without_confirmation_cannot_dispatch(self):
        self.liveries.installSelectedPackage()
        self.assertEqual([], self.tasks.requests)
        self.assertIn("confirmation required", self.liveries.status)

    def test_cancelled_confirmation_cannot_dispatch(self):
        self.prepare()
        self.liveries.cancelInstallConfirmation()
        self.assertEqual("Installation cancelled", self.liveries.status)
        self.assertEqual("No installation was started.", self.liveries.summary)
        self.assertEqual("", self.liveries.installDestinationDescription)
        self.liveries.installSelectedPackage()
        self.assertEqual(1, len(self.tasks.requests))
        self.assertFalse(self.liveries.installConfirmationCurrent)
        self.assertEqual("Install confirmation required", self.liveries.status)
        self.assertEqual("Check the package and FH6 save destination again before installing.", self.liveries.summary)

    def test_cancel_preserves_newer_status_summary_and_busy_state(self):
        for status, summary, running, worker_running in (
                ("Full-livery task failed", "New worker failure", False, False),
                ("Confirm FH6 install destination", "Newer diagnostic detail", False, False),
                ("Confirm FH6 install destination",
                 "Review the verified account and current save folder before installing.", True, True),
                ("Confirm FH6 install destination",
                 "Review the verified account and current save folder before installing.", False, True)):
            with self.subTest(status=status, summary=summary, running=running, worker_running=worker_running):
                self.prepare()
                self.liveries._status, self.liveries._summary = status, summary
                self.liveries._running = running
                self.tasks.running = worker_running
                self.liveries.cancelInstallConfirmation()
                self.assertEqual((status, summary, running),
                                 (self.liveries.status, self.liveries.summary, self.liveries.running))
                self.assertIsNone(self.liveries._install_confirmation)
                self.liveries._running = self.tasks.running = False

    def test_cancel_preserves_status_when_confirmation_no_longer_owns_selection(self):
        self.prepare()
        self.liveries._selection_serial += 1
        before = self.liveries.status, self.liveries.summary
        self.liveries.cancelInstallConfirmation()
        self.assertEqual(before, (self.liveries.status, self.liveries.summary))
        self.assertIsNone(self.liveries._install_confirmation)

    def test_repeated_cancel_does_not_overwrite_later_failure(self):
        self.prepare()
        self.liveries.cancelInstallConfirmation()
        self.liveries._status, self.liveries._summary = "Full-livery task failed", "Later failure"
        self.liveries.cancelInstallConfirmation()
        self.assertEqual(("Full-livery task failed", "Later failure"),
                         (self.liveries.status, self.liveries.summary))

    def test_changed_confirmation_context_cannot_dispatch(self):
        for field, value in (("_save_root", "different"), ("_game_folder", "different"),
                             ("_selected_package", "different"), ("_selection_serial", 99),
                             ("_source_preview_serial", 99), ("_active", False)):
            with self.subTest(field=field):
                self.prepare()
                previous = getattr(self.liveries, field)
                setattr(self.liveries, field, value)
                count = len(self.tasks.requests)
                self.liveries.installSelectedPackage()
                self.assertEqual(count, len(self.tasks.requests))
                self.assertFalse(self.liveries.installConfirmationCurrent)
                self.assertEqual("Install confirmation required", self.liveries.status)
                setattr(self.liveries, field, previous)

    def test_destination_failure_and_cancellation_never_open_confirmation(self):
        for result in ({"ok": False, "error": "Destination is ambiguous"},
                       {"ok": False, "cancelled": True, "error": "Cancelled"}):
            self.liveries.prepareInstallSelectedPackage()
            self.tasks.finish(**result)
            self.assertEqual([], self.ready)
            self.assertFalse(self.liveries.installConfirmationCurrent)
            self.assertFalse(self.liveries.running)
            self.assertEqual(result["error"], self.liveries.summary)

    def test_late_preflight_cannot_open_over_a_new_selection_or_status(self):
        self.liveries.prepareInstallSelectedPackage()
        old = self.tasks.requests[-1]
        self.liveries._selection_serial += 1
        self.liveries._status = "New selection"
        self.tasks.finish(self.resolved)
        self.assertEqual([], self.ready)
        self.assertEqual("New selection", self.liveries.status)
        self.assertFalse(self.liveries.running)
        self.liveries.prepareInstallSelectedPackage()
        self.liveries._inspector_failed("New viewer failure")
        self.tasks.finish(self.resolved)
        self.assertEqual([], self.ready)
        self.assertEqual("New viewer failure", self.liveries.summary)
        self.tasks.completed.emit({**old, "ok": True, "value": self.resolved})
        self.assertEqual([], self.ready)

    def test_page_exit_cannot_open_confirmation(self):
        self.liveries.prepareInstallSelectedPackage()
        self.liveries.deactivate()
        self.tasks.finish(self.resolved)
        self.assertEqual([], self.ready)
        self.assertEqual("Experimental workspace paused", self.liveries.status)

    def test_malformed_preflight_is_not_confirmable(self):
        self.liveries.prepareInstallSelectedPackage()
        self.tasks.finish({"containers": "incomplete"})
        self.assertEqual([], self.ready)
        self.assertFalse(self.liveries.installConfirmationCurrent)
        self.assertEqual("Install destination check failed", self.liveries.status)

    def test_malformed_or_mismatched_snapshot_cannot_open_confirmation(self):
        cases = [None, {}, {**self.resolved["expected_destination"], "schema": "future"}]
        for expected in cases:
            with self.subTest(expected=expected):
                self.liveries.prepareInstallSelectedPackage()
                self.tasks.finish({**self.resolved, "expected_destination": expected})
                self.assertFalse(self.liveries.installConfirmationCurrent)
                self.assertEqual("Install destination check failed", self.liveries.status)
        for field in ("account", "containers", "user_id"):
            with self.subTest(field=field):
                self.liveries.prepareInstallSelectedPackage()
                self.tasks.finish({**self.resolved, field: "mismatched-description"})
                self.assertFalse(self.liveries.installConfirmationCurrent)
                self.assertEqual("Install destination check failed", self.liveries.status)
        self.assertEqual([], self.ready)

    def test_preflight_copies_snapshot_and_keeps_128_bit_ids_in_python_worker_payload(self):
        self.resolved["expected_destination"]["containers_id"][1] = 2**127 + 17
        self.prepare()
        original = copy.deepcopy(self.resolved["expected_destination"])
        self.resolved["expected_destination"]["containers_id"][1] = 99
        self.liveries.installSelectedPackage()
        payload = self.tasks.requests[-1]["input"]
        self.assertEqual(original, json.loads(json.dumps(payload))["expected_destination"])
        self.assertIsInstance(self.liveries.installDestinationDescription, str)
        self.assertIsInstance(self.liveries.installConfirmationCurrent, bool)

    def test_worker_rejects_missing_or_malformed_snapshot_before_package_access(self):
        for supplied in (None, {}, [], {**self.resolved["expected_destination"], "schema": "future"}):
            with self.subTest(supplied=supplied), patch.object(jobs, "validate_full_livery_package") as validate, \
                    patch.object(jobs, "install_full_livery_package") as install:
                with self.assertRaises(installer.FullLiveryInstallError):
                    jobs.install_package(None, {"expected_destination": supplied}, threading.Event())
                validate.assert_not_called()
                install.assert_not_called()

    def test_worker_rejects_root_that_differs_from_confirmed_snapshot(self):
        payload = {"save_root": str(self.root / "other"), "expected_destination": self.resolved["expected_destination"]}
        with patch.object(jobs, "validate_full_livery_package") as validate, \
                patch.object(jobs, "install_full_livery_package") as install:
            with self.assertRaises(installer.FullLiveryInstallError):
                jobs.install_package(None, payload, threading.Event())
            validate.assert_not_called()
            install.assert_not_called()

    def test_local_destination_label_is_absent_from_support_report_and_private_logs(self):
        from kfps_ui.report_service import ReportService
        from kfps_ui.support_report import build_support_report
        from kfps_ui.support_log_bundle import collect_retained_log_bundle

        self.prepare()
        self.liveries.installSelectedPackage()
        label = "Destination: FH6 account 456, current save 1."
        self.assertIn(label, self.liveries.summary)
        reporter = ReportService(self.liveries.paths, self.liveries.log, SimpleNamespace(localVersion="test"))
        self.addCleanup(reporter.close)
        reporter.bind_support_context({"liveries": self.liveries})
        context = reporter._snapshot_support("liveries")
        self.assertNotIn("summary", context["services"]["liveries"])
        report = build_support_report(self.root, context, since=0, collect=lambda: {})
        attachment = collect_retained_log_bundle(self.root, snapshot=report["technical"],
                                                 session_logs={"app": context["retained_app_log"]})
        self.assertIsNotNone(attachment)
        reopened = gzip.decompress(attachment[1]).decode("utf-8")
        for output in (json.dumps(context), json.dumps(report), reopened):
            for private in (label, "u_456_16D460", self.resolved["containers"], "expected_destination", "manifest_sha256"):
                self.assertNotIn(private, output)

    def test_destination_ipc_export_keeps_outcomes_not_account_identity(self):
        from kfps_ui.experimental.full_livery.diagnostics import export_diagnostic_bundle

        sessions = self.root / "sessions"
        for operation in ("resolve-install-destination", "install-package"):
            folder = sessions / operation
            folder.mkdir(parents=True)
            common = {"protocol": 1, "request_id": "fixture", "operation": operation, "kind": "install"}
            request = {**common, "payload": {"save_root": self.resolved["containers"],
                                             "expected_destination": self.resolved["expected_destination"]}}
            result = {**common, "ok": True, "value": self.resolved,
                      "metadata": {"private": self.resolved}, "error": self.resolved["containers"]}
            for name, value in (("request.json", request), ("result.json", result)):
                (folder / name).write_text(json.dumps(value), encoding="utf-8")
        target = export_diagnostic_bundle(self.root / "diagnostics.zip", sessions_root=sessions,
                                         recovery_root=self.root / "recovery", catalog_stats={}, release_state={})
        with zipfile.ZipFile(target) as archive:
            self.assertEqual(5, len(archive.namelist()))
            for name in archive.namelist():
                text = archive.read(name).decode("utf-8")
                for private in ("u_456_16D460", "ContainersRoot", "expected_destination", "manifest_sha256", "user_id"):
                    self.assertNotIn(private, text)
                if name.endswith("result.json"):
                    self.assertTrue(json.loads(text)["ok"])
                if name != "summary.json":
                    self.assertIn(json.loads(text)["operation"], ("resolve-install-destination", "install-package"))

    def test_rejected_preflight_start_has_no_stuck_running(self):
        self.tasks.reject.add("resolve-install-destination")
        self.liveries.prepareInstallSelectedPackage()
        self.assertFalse(self.liveries.running)
        self.assertFalse(self.liveries.installConfirmationCurrent)
        self.assertEqual("Install destination check unavailable", self.liveries.status)

    def test_rejected_install_start_consumes_confirmation_and_has_no_stuck_running(self):
        self.prepare()
        self.tasks.reject.add("install-package")
        self.liveries.installSelectedPackage()
        self.assertFalse(self.liveries.running)
        self.assertFalse(self.liveries.installConfirmationCurrent)
        self.assertEqual("Installation not started", self.liveries.status)

    def test_confirmation_is_single_use_and_running_blocks_reentry(self):
        self.prepare()
        self.liveries.installSelectedPackage()
        self.liveries.installSelectedPackage()
        self.liveries.prepareInstallSelectedPackage()
        self.assertEqual(2, len(self.tasks.requests))
        self.tasks.finish(ok=False, cancelled=True)
        self.liveries.installSelectedPackage()
        self.assertEqual(2, len(self.tasks.requests))
        self.assertFalse(self.liveries.installConfirmationCurrent)

    def make_account(self, user=123, version=1):
        import _winapi
        account = self.root / "saves" / f"u_{user}_16D460"
        containers = account / str(version) / "ContainersRoot"
        (containers / f"User_{user:x}").mkdir(parents=True)
        (account / f"{version}.json").write_text(json.dumps({"Manifest": {
            "UserId": str(user), "GameId": "16D460", "Version": version}}), encoding="utf-8")
        current = account / "current"
        if current.exists():
            os.rmdir(current)
        _winapi.CreateJunction(str(containers.parent), str(current))
        return account, containers

    def test_real_preflight_resolver_reads_only_disposable_account_and_preserves_files(self):
        account, containers = self.make_account()
        before = (account / "1.json").read_bytes()
        result = jobs.resolve_install_destination(None, {"save_root": str(account)}, threading.Event())
        self.assertEqual({"account": str(account), "containers": str(containers), "user_id": "123"},
                         {key: result[key] for key in ("account", "containers", "user_id")})
        self.assertEqual(installer.destination_snapshot(fh6_identity.read_account(account)), result["expected_destination"])
        self.assertEqual(before, (account / "1.json").read_bytes())
        self.assertEqual(["User_7b"], [p.name for p in containers.iterdir()])

    def test_synthetic_accepted_install_uses_real_preflight_worker_job_and_reopened_files(self):
        from test_studio_package_handoff import make_package
        from tools.cgroup.forza_source_decoder import clivery_to_layers, unwrap_forza_container

        package = Path(self.liveries.selectedPackage)
        make_package(package)
        account, containers = self.make_account()
        evidence = containers / "LayerGroup_fixture"
        evidence.mkdir()
        (evidence / "header").write_bytes(fh6_identity.build_vinyl_header("Fixture", 123, "Fixture Owner", 1))
        self.liveries._save_root = str(account)
        self.liveries._current_manifest = jobs.validate_full_livery_package(package)
        self.liveries.prepareInstallSelectedPackage()
        confirmed = jobs.resolve_install_destination(None, self.tasks.requests[-1]["input"], threading.Event())
        self.tasks.finish(confirmed)
        self.assertTrue(self.liveries.installConfirmationCurrent)
        self.liveries.installSelectedPackage()
        payload = json.loads(json.dumps(self.tasks.requests[-1]["input"]))
        self.assertEqual(confirmed["expected_destination"], payload["expected_destination"])
        paths = SimpleNamespace(vehicle_index=self.root / "synthetic-index", recovery=self.root / "recovery")
        # Only the local game-car inventory is synthetic. Package validation,
        # destination checks, identity rewrite, install and reopen are real.
        with patch.object(jobs, "load_or_build_vehicle_asset_index",
                          return_value={3307: SimpleNamespace(model_code="TEST_CAR")}):
            result = jobs.install_package(paths, payload, threading.Event())
        self.tasks.finish(result)
        installed = Path(result["installed_folder"])
        self.assertEqual(containers, installed.parent)
        header = installer.parse_fh6_header((installed / "header").read_bytes())
        layers, report = clivery_to_layers(unwrap_forza_container(installed / "C_livery"))
        self.assertEqual((3307, 123, 5), (header.car_id, int.from_bytes(header.creator_tag, "little"), len(layers)))
        self.assertFalse(report["warnings"])
        receipt = json.loads((Path(result["backup_path"]) / "install.json").read_bytes())
        self.assertEqual(str(containers), receipt["containers_root"])
        self.assertEqual("FH6 livery installed", self.liveries.status)
        summary = self.liveries.summary
        self.assertIn("Destination: FH6 account 123, current save 1.", summary)
        self.tasks.finish({"rows": [{"path": str(installed / "C_livery"), "carId": 3307}],
                           "game_assets_ready": True, "inspected": 1})
        self.tasks.finish({"rows": [{"path": str(package), "carId": 3307}], "cache_hits": 1})
        self.assertFalse(self.liveries.running)
        self.assertEqual("FH6 livery installed", self.liveries.status)
        self.assertEqual(summary, self.liveries.summary)
        self.assertEqual(confirmed["expected_destination"], installer.destination_snapshot(fh6_identity.read_account(account)))

    def test_real_preflight_ambiguity_does_not_choose_a_different_account(self):
        self.make_account(123)
        self.make_account(456)
        with self.assertRaises(installer.FullLiveryInstallError):
            jobs.resolve_install_destination(None, {"save_root": str(self.root / "saves")}, threading.Event())

    def test_pinned_current_folder_rejects_version_change_and_never_follows_new_pointer(self):
        account, containers = self.make_account(123)
        other, _ = self.make_account(456)
        resolved = jobs.resolve_install_destination(None, {"save_root": str(account)}, threading.Event())
        with patch.object(fh6_identity, "_pointer_accounts", side_effect=AssertionError("must remain pinned")):
            selected = installer._select_destination_account([], destination=resolved["containers"])
        self.assertEqual(account, selected.directory)
        self.assertNotEqual(other, selected.directory)
        self.make_account(123, version=2)
        with self.assertRaisesRegex(installer.FullLiveryInstallError, "current"):
            installer._select_destination_account([], destination=containers)

    def test_cancelled_preflight_does_not_resolve_anything(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch.object(installer, "_select_destination_account", side_effect=AssertionError("no read")):
            with self.assertRaises(InterruptedError):
                jobs.resolve_install_destination(None, {}, cancelled)

    def test_read_only_destination_operation_runs_through_hidden_worker_protocol(self):
        from kfps_ui.experimental.full_livery.protocol import PROTOCOL_VERSION, new_request_id, write_json_atomic
        account, containers = self.make_account()
        session = self.root / "worker-check"
        request, result = session / "request.json", session / "result.json"
        paths = self.liveries._experiment_paths.as_worker_payload()
        paths.update(app_root=str(self.root), inspector_root=str(self.root / "tools/livery-inspector"))
        write_json_atomic(request, {"protocol": PROTOCOL_VERSION, "request_id": new_request_id(),
                          "operation": "resolve-install-destination", "paths": paths,
                          "payload": {"save_root": str(account)}, "session_dir": str(session),
                          "cancel_file": str(session / "cancel")})
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "KFPS.UI/full_livery_process.py"), "worker",
             "--request", str(request), "--result", str(result), "--parent-pid", str(os.getpid())],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        reopened = json.loads(result.read_bytes())
        self.assertTrue(reopened["ok"], reopened)
        self.assertEqual(str(containers), reopened["value"]["containers"])
        self.assertEqual("123", reopened["value"]["user_id"])
        self.assertEqual(installer.destination_snapshot(fh6_identity.read_account(account)),
                         reopened["value"]["expected_destination"])
        self.assertEqual(["User_7b"], [path.name for path in containers.iterdir()])

    def test_explicit_account_resolution_never_consults_system_pointer(self):
        destination = self.root / "u_123_16D460" / "current" / "ContainersRoot"
        destination.mkdir(parents=True)
        expected = object()
        with patch.object(fh6_identity, "account_from_selection", return_value=expected) as selected, \
                patch.object(fh6_identity, "_pointer_accounts", side_effect=AssertionError("unexpected fallback")):
            self.assertIs(expected, installer._select_destination_account([], destination=destination))
        selected.assert_called_once_with(destination.resolve())

    def test_automatic_resolution_can_use_pointer_independent_of_garage_selection(self):
        self.select_garage_account()
        pointer_account = object()
        with patch.object(fh6_identity, "_pointer_accounts", return_value=({"pointer-account": pointer_account}, False)):
            resolved = installer._select_destination_account([], local_app_data=self.root / "synthetic-local")
        self.assertIs(pointer_account, resolved)
        self.assertEqual(self.account["id"], self.garage.selectedAccountId)

    def test_ambiguous_automatic_pointer_remains_fail_closed(self):
        with patch.object(fh6_identity, "_pointer_accounts", return_value=({"one": object(), "two": object()}, False)):
            with self.assertRaisesRegex(installer.FullLiveryInstallError, "ambiguous"):
                installer._select_destination_account([], local_app_data=self.root / "synthetic-local")


if __name__ == "__main__":
    unittest.main()
