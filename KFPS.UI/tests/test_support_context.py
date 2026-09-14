import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "KFPS.UI/src"), str(ROOT)]
from kfps_ui.support_context import collect_context
from kfps_ui.support_log_bundle import collect_retained_log_bundle
from kfps_ui.support_logs import read_known_file, updater_location
from kfps_ui.support_report import build_support_report, save_handoff


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "app"
        self.root.mkdir()
        self.env = patch.dict(os.environ, {"LOCALAPPDATA": str(Path(self.temp.name) / "local")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if isinstance(data, dict) else data, encoding="utf-8")
        return path

    def archive(self):
        metadata, blob = collect_retained_log_bundle(self.root)
        return metadata, json.loads(gzip.decompress(blob))

    def test_state_and_stale_owner_without_private_identity_or_any_mutation(self):
        marker = self.write("runtime/fabric-editor/desktop.json", {"service":"kfps-editor-desktop",
            "pid":4294967294, "root":"PRIVATE_ROOT", "instance":"PRIVATE_INSTANCE", "state":"starting",
            "started_at":1, "updated_at":2, "error":"Access denied", "unknown":"PRIVATE_OTHER"})
        lock = self.write("runtime/fabric-editor/desktop.lock", "4294967294\nPRIVATE_EXE\nPRIVATE_HOST\n")
        error = self.write("runtime/fabric-editor/desktop-startup-error.json", {"pid":4294967294,"error":"startup failed"})
        before = [path.read_bytes() for path in (marker, lock, error)]
        context = collect_context(self.root)
        self.assertEqual(context["editor_state"]["fields"]["state"], "starting")
        self.assertEqual(context["editor_lock"]["process"]["status"], "not_running")
        self.assertIn("startup failed", json.dumps(context))
        self.assertNotIn("PRIVATE", json.dumps(context))
        self.assertEqual(before, [path.read_bytes() for path in (marker, lock, error)])

    def test_live_pid_is_observation_not_assumed_editor_owner(self):
        self.write("runtime/fabric-editor/desktop.json", {"pid":os.getpid(), "started_at":1})
        context = collect_context(self.root)["editor_state"]
        self.assertTrue(context["process_started_after_marker"])
        self.assertFalse(context["process"]["executable_in_installation"])
        self.assertNotIn("exe", context["process"])

    def test_bad_states_are_distinguished_from_missing_and_links_never_read(self):
        self.write("runtime/fabric-editor/desktop.json", "{broken")
        target = self.write("runtime/fabric-editor/desktop.lock", "PRIVATE_CONTENT")
        os.link(target, self.root / "elsewhere")
        context = collect_context(self.root)
        self.assertEqual(context["editor_state"]["status"], "invalid")
        self.assertEqual(context["editor_lock"]["status"], "unsafe_file")
        self.assertEqual(context["editor_startup_error"]["status"], "missing")
        self.assertNotIn("PRIVATE", json.dumps(context))
        self.write("runtime/fabric-editor/diagnostics.json", {"schema":"kfps-editor-diagnostics/1", "updated":1})
        os.link(self.root / "runtime/fabric-editor/diagnostics.json", self.root / "private-diagnostics")
        self.assertEqual(collect_context(self.root)["editor_diagnostics"], {"unavailable":"snapshot_unreadable"})

    def test_every_category_includes_previous_editor_and_locator_evidence(self):
        self.write("runtime/fabric-editor/diagnostics.json", {"schema":"kfps-editor-diagnostics/1", "updated":1,
            "native":{"kind":"renderer-stopped", "code":9}, "identity":{"version":"3.1.82"}})
        self.write("runtime/live-memory/reports/latest.json", {"created_utc":"2026-01-01T00:00:00Z",
            "outcome":{"status":"no_match"}, "request":{"game":"fh6","layer_count":3000}, "shapes":["PRIVATE"]})
        for page in ("create", "outputs", "editor", "community", "update", "other"):
            report = build_support_report(self.root, {"page":page}, since=time.time(), collect=lambda:{})
            self.assertEqual(report["technical"]["editor"]["native"]["kind"], "renderer-stopped")
            self.assertEqual(report["technical"]["locator"]["outcome"]["status"], "no_match")
            self.assertNotIn("PRIVATE", json.dumps(report))

    def test_updater_history_is_only_for_this_installation_and_never_copies_paths(self):
        anchor, state = updater_location(self.root)
        for folder in ("logs", "reports"):
            (state / folder).mkdir(parents=True)
        (state / "logs/update-20260914-120000-aabb.log").write_text("Rollback failed\ntoken=PRIVATE_KEY\n")
        (state / "reports/update-20260914-120000-aabb.json").write_text(json.dumps({
            "schema":"kfps-update-report/1", "status":"failed", "rollback":True,
            "error":"Access denied", "app_root":"PRIVATE_ROOT", "changes":["PRIVATE_CHANGES"]}))
        other = state.parent / "another-installation/logs"
        other.mkdir(parents=True)
        (other / "update-20260914-120000-aabb.log").write_text("PRIVATE_OTHER_INSTALL")
        _, archive = self.archive()
        text = json.dumps(archive)
        self.assertIn("Rollback failed", text)
        self.assertIn("Access denied", text)
        self.assertNotIn("PRIVATE", text)
        self.assertTrue(any(file["name"].startswith("updater-worker") for file in archive["files"]))

    def test_locked_file_is_visible_in_checklist_and_does_not_drop_other_logs(self):
        target = self.write("runtime/fabric-editor/desktop.log", "startup")
        self.write("runtime/support-reports/report-window.log", "login pending")
        original = Path.open
        def denied(path, *args, **kwargs):
            if path == target:
                raise PermissionError(13, "PRIVATE_ERROR")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", denied):
            metadata, archive = self.archive()
        self.assertTrue(metadata["warnings"])
        index = next(file for file in archive["files"] if file["name"].startswith("collection-index"))
        row = next(row for row in json.loads(index["text"])["files"] if row["file"] == "desktop.log")
        self.assertEqual(row["status"], "unreadable")
        self.assertEqual(row["errno"], 13)
        self.assertIn("login pending", json.dumps(archive))
        self.assertNotIn("PRIVATE", json.dumps(archive))

    def test_transient_sharing_race_retries_without_changing_file(self):
        path = self.write("runtime/fabric-editor/desktop.log", "startup")
        original = Path.open
        calls = []
        def sharing(target, *args, **kwargs):
            if target == path:
                calls.append(1)
                if len(calls) < 3:
                    error = PermissionError("temporary")
                    error.winerror = 32
                    raise error
            return original(target, *args, **kwargs)
        with patch.object(Path, "open", sharing):
            raw, _ = read_known_file(self.root, path, 100)
        self.assertEqual(raw, b"startup")
        self.assertEqual(len(calls), 3)

    def test_python_package_passes_actual_form_and_submission_parser(self):
        import shutil
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required for the cross-language contract")
        for relative in ("runtime/fabric-editor/desktop.log", "runtime/support-reports/report-window.log",
                         "runtime/app-logs/app-42.log", "runtime/qml-transfer-logs/transfer-20260914-120000.log"):
            self.write(relative, "Synthetic event\n" * 3000 + "token=PRIVATE\n")
        self.write("runtime/fabric-editor/desktop.lock", "4294967294\nPRIVATE_HOST\n")
        report = build_support_report(self.root, {"page":"editor", "version":"test"}, since=time.time(), collect=lambda:{})
        attachment = collect_retained_log_bundle(self.root, snapshot=report["technical"],
            session_logs={"app":"Pending event\npassword=PRIVATE\n", "transfer":"Latest transfer event"})
        report["private_logs"] = attachment[0]
        path, _ = save_handoff(self.root, report, log_attachment=attachment)
        result = subprocess.run([node, str(ROOT / "tools/support_worker/test/validate-collection.mjs"),
                                 str(path.parent / "report.kfps-report.json.gz")], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"privateBytesPreserved":true', result.stdout)

    def test_recorded_baseline_comparison_and_local_update_report_fallback(self):
        import hashlib
        raw = "print('synthetic source')\n"
        path = self.write("KFPS.Editor/src/kfps_editor/host.py", raw)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.write("KFPS.Editor/baseline.json", {"schema":"kfps-editor-baseline/1",
            "engine":{"chromium":"140.0.0","private":"PRIVATE"},
            "files":[{"path":"KFPS.Editor/src/kfps_editor/host.py","sha256":digest}]})
        self.write("runtime/update-reports/update-20260914-120000-aabb.json", {"status":"failed","phase":"apply","error":"denied"})
        context = collect_context(self.root)
        self.assertTrue(context["installation"]["editor-host"]["matches_recorded_baseline"])
        self.assertEqual(context["updater_history"]["runs"][0]["fields"]["phase"], "apply")
        self.assertNotIn("PRIVATE", json.dumps(context))
        self.write("KFPS.Editor/src/kfps_editor/host.py", "changed\n")
        self.assertFalse(collect_context(self.root)["installation"]["editor-host"]["matches_recorded_baseline"])

    def test_file_limit_keeps_other_components_when_app_history_is_large(self):
        from kfps_ui.support_logs import discover_worker_logs
        for index in range(270):
            self.write(f"runtime/app-logs/app-{index}.log", "app event\n")
        self.write("runtime/qml-transfer-logs/transfer-20260914-120000.log", "transfer event\n")
        self.write("runtime/support-reports/report-window.log", "login event\n")
        files, warnings = discover_worker_logs(self.root, now=time.time(), retained=True)
        self.assertEqual(len(files), 256)
        self.assertTrue({"app-runtime", "transfer-worker", "report-window"} <= {source for source, _ in files})
        self.assertTrue(any("limit" in value for value in warnings))

    def test_serialized_capacity_keeps_checklist_and_reports_omissions(self):
        from kfps_ui import support_log_bundle as bundle
        for index in range(3):
            self.write(f"runtime/qml-transfer-logs/transfer-20260914-12000{index}.log", 'event "quoted"\n' * 5000)
        with patch.object(bundle, "MAX_RAW_BYTES", 450000):
            metadata, data = self.archive()
        self.assertLessEqual(metadata["raw_size"], 450000)
        self.assertTrue(metadata["warnings"])
        self.assertTrue(any(file["name"].startswith("transfer-worker") for file in data["files"]))
        self.assertTrue(any(file["name"].startswith("collection-index") for file in data["files"]))


if __name__ == "__main__":
    unittest.main()
