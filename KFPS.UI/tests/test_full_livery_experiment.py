from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kfps_ui.experimental.full_livery.catalog import FullLiveryCatalog
from kfps_ui.experimental.full_livery.diagnostics import (
    DiagnosticSession,
    recover_abandoned_sessions,
    scrub_text,
)
from kfps_ui.experimental.full_livery.feature_gate import FullLiveryFeatureGate
from kfps_ui.experimental.full_livery.paths import CACHE_REVISION, FullLiveryPaths
from kfps_ui.experimental.full_livery.qualification import qualification_template
from kfps_ui.experimental.full_livery import jobs as full_livery_jobs
from kfps_ui.experimental.full_livery.protocol import OPERATIONS as PROTOCOL_OPERATIONS
from kfps_ui.experimental.full_livery.protocol import PROTOCOL_VERSION
from kfps_ui.experimental.full_livery.supervisor import (
    _inspector_command,
    _worker_command,
)


class FullLiveryExperimentContractTests(unittest.TestCase):
    def test_worker_protocol_exposes_every_implemented_operation(self):
        self.assertEqual(set(full_livery_jobs.OPERATIONS), set(PROTOCOL_OPERATIONS))

    def test_qualification_cli_launches_outside_the_repository(self):
        script = ROOT / "tools" / "livery" / "full_livery_qualification.py"
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(script), "--help"],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("full-livery release qualification", completed.stdout)

    def test_process_commands_preserve_python_and_frozen_portability(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ui_root = root / "KFPS.UI"
            ui_root.mkdir()
            bundled_python = root / "python" / "python.exe"
            bundled_python.parent.mkdir()
            bundled_python.touch()
            paths = SimpleNamespace(
                python_executable=str(bundled_python),
                ui_root=ui_root,
            )
            request = root / "request.json"
            result = root / "result.json"
            program, arguments = _worker_command(paths, request, result)
            self.assertEqual(str(bundled_python), program)
            self.assertEqual(str(ui_root / "full_livery_process.py"), arguments[0])
            self.assertEqual("worker", arguments[1])
            program, arguments = _inspector_command(
                paths,
                root / "config.json",
                root / "ready.json",
                root / "stop",
            )
            self.assertEqual(str(bundled_python), program)
            self.assertEqual("inspector", arguments[1])

            paths.python_executable = str(root / "KFPS.exe")
            program, arguments = _worker_command(paths, request, result)
            self.assertEqual(sys.executable, program)
            self.assertIn("--full-livery-worker", arguments)
            program, arguments = _inspector_command(
                paths,
                root / "config.json",
                root / "ready.json",
                root / "stop",
            )
            self.assertEqual(sys.executable, program)
            self.assertIn("--full-livery-inspector", arguments)

    def test_missing_configured_root_never_falls_back_to_another_drive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fallback = root / "XboxGames" / "GameSave"
            fallback.mkdir(parents=True)
            partition = SimpleNamespace(mountpoint=str(root))
            with patch.object(full_livery_jobs.psutil, "disk_partitions", return_value=[partition]):
                self.assertEqual([], full_livery_jobs._scan_roots(str(root / "missing")))

    def test_incomplete_root_scan_keeps_the_last_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_root = root / "app"
            inspector_root = app_root / "tools" / "livery-inspector"
            inspector_root.mkdir(parents=True)
            app_paths = SimpleNamespace(
                runtime_root=app_root / "runtime",
                exported_root=app_root / "imgs" / "exported",
            )
            experiment = FullLiveryPaths.for_app(app_paths)
            experiment.ensure()
            values = experiment.as_worker_payload()
            values.update({
                "app_root": str(app_root.resolve()),
                "inspector_root": str(inspector_root.resolve()),
            })
            paths = full_livery_jobs.JobPaths.from_request({"paths": values})
            save_root = root / "saves"
            source = save_root / "cached" / "C_livery"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"partial scan fixture")
            stat = source.stat()
            catalog = FullLiveryCatalog(experiment.catalog_file, experiment.quarantine)
            catalog.upsert_source(
                source,
                root=save_root,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                content_hash="cached-content",
                parser_revision=1,
                seen_token="complete-scan",
                row={
                    "_visible": True,
                    "_contentHash": "cached-content",
                    "_mtimeNs": stat.st_mtime_ns,
                    "title": "Cached livery",
                    "path": str(source.resolve()),
                    "carId": 1,
                    "modelCode": "cached_car",
                    "placementCount": 10,
                    "modified": "",
                    "detail": "Cached",
                    "hasHeader": False,
                    "exportable": True,
                    "privacyDetail": "",
                },
            )

            def interrupted_rglob(_path, _pattern):
                yield source
                raise OSError("simulated disconnected save drive")

            with patch.object(full_livery_jobs, "_scan_roots", return_value=[save_root.resolve()]):
                with patch.object(Path, "rglob", interrupted_rglob):
                    result = full_livery_jobs.scan_saves(paths, {}, threading.Event())

            self.assertTrue(result["stale_index"])
            self.assertEqual("Cached livery", result["rows"][0]["title"])
            self.assertEqual(1, len(catalog.source_rows()))

    def test_paths_are_isolated_and_legacy_settings_are_copied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_paths = SimpleNamespace(
                runtime_root=root / "runtime",
                exported_root=root / "imgs" / "exported",
            )
            legacy = app_paths.runtime_root / "full-livery"
            legacy.mkdir(parents=True)
            (legacy / "settings.json").write_text(
                json.dumps({"fh6_game_folder": "C:/FH6"}), encoding="utf-8"
            )

            paths = FullLiveryPaths.for_app(app_paths)
            settings = paths.load_settings()

            self.assertEqual("C:/FH6", settings["fh6_game_folder"])
            self.assertTrue(paths.settings_file.is_file())
            self.assertTrue((legacy / "settings.json").is_file())
            self.assertEqual(
                app_paths.runtime_root / "experiments" / "full-livery",
                paths.root,
            )
            self.assertEqual(f"v{CACHE_REVISION}", paths.cache.name)

    def test_source_index_survives_restart_and_removes_only_unseen_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog_path = root / "state" / "catalog.sqlite3"
            source_root = root / "saves"
            first = source_root / "one" / "C_livery"
            second = source_root / "two" / "C_livery"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            catalog = FullLiveryCatalog(catalog_path, root / "quarantine")
            for path, token in ((first, "scan-1"), (second, "scan-1")):
                stat = path.stat()
                catalog.upsert_source(
                    path,
                    root=source_root,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    content_hash=path.read_bytes().hex(),
                    parser_revision=3,
                    seen_token=token,
                    row={"path": str(path.resolve()), "title": path.parent.name},
                )

            reopened = FullLiveryCatalog(catalog_path, root / "quarantine")
            stat = first.stat()
            cached = reopened.cached_source(
                first, size=stat.st_size, mtime_ns=stat.st_mtime_ns, parser_revision=3
            )
            self.assertEqual("one", cached["title"])
            reopened.mark_source_seen(first, "scan-2")
            self.assertEqual(1, reopened.finish_source_scan([source_root], "scan-2"))
            self.assertEqual(["one"], [row["title"] for row in reopened.source_rows()])

    def test_package_index_uses_file_identity_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "saved" / "sample.kfpslivery"
            package.parent.mkdir(parents=True)
            package.write_bytes(b"package")
            stat = package.stat()
            catalog = FullLiveryCatalog(root / "catalog.sqlite3")
            catalog.upsert_package(
                package,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                compiler_revision=8,
                seen_token="one",
                row={"path": str(package.resolve()), "title": "Sample"},
            )
            reopened = FullLiveryCatalog(root / "catalog.sqlite3")
            self.assertEqual(
                "Sample",
                reopened.cached_package(
                    package,
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    compiler_revision=8,
                )["title"],
            )

    def test_batch_source_index_commits_one_complete_scan(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "saves"
            source_root.mkdir()
            catalog = FullLiveryCatalog(root / "catalog.sqlite3")
            records = []
            for index in range(500):
                path = source_root / str(index) / "C_livery"
                path.parent.mkdir()
                path.write_bytes(str(index).encode("ascii"))
                stat = path.stat()
                records.append({
                    "path": path,
                    "root": source_root,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "content_hash": f"hash-{index}",
                    "parser_revision": 7,
                    "row": {"path": str(path.resolve()), "title": str(index)},
                })
            self.assertEqual(0, catalog.apply_source_scan([source_root], "one", records))
            self.assertEqual(500, len(catalog.source_snapshot([source_root])))
            self.assertEqual(250, catalog.apply_source_scan([source_root], "two", records[:250]))
            self.assertEqual(250, len(catalog.source_rows()))

    def test_corrupt_database_is_quarantined_and_rebuilt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "state" / "catalog.sqlite3"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"not sqlite")
            catalog = FullLiveryCatalog(path, root / "quarantine")
            self.assertEqual({"sources": 0, "packages": 0, "cache_entries": 0}, catalog.stats())
            self.assertEqual(1, len(list((root / "quarantine").glob("*.corrupt"))))
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual("ok", connection.execute("PRAGMA quick_check").fetchone()[0])

    def test_feature_gate_keeps_preview_export_and_install_distinct(self):
        with patch.dict(os.environ, {"KFPS_FULL_LIVERY_STAGE": "preview"}):
            preview = FullLiveryFeatureGate.resolve()
        self.assertTrue(preview.can_preview)
        self.assertTrue(preview.can_export)
        self.assertFalse(preview.can_install)
        with patch.dict(os.environ, {"KFPS_FULL_LIVERY_STAGE": "candidate"}):
            candidate = FullLiveryFeatureGate.resolve()
        self.assertTrue(candidate.can_install)
        self.assertFalse(candidate.is_stable)

    def test_stable_stage_requires_current_complete_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "qualification.json"
            with patch.dict(os.environ, {"KFPS_FULL_LIVERY_STAGE": "stable"}):
                blocked = FullLiveryFeatureGate.resolve(
                    qualification_file=evidence,
                    app_version="3.1.test",
                )
            self.assertEqual("candidate", blocked.stage)
            self.assertEqual("qualification-blocked", blocked.source)

            value = qualification_template("3.1.test")
            for record in value["checks"].values():
                record["passed"] = True
                record["evidence"] = ["verified report"]
            evidence.write_text(json.dumps(value), encoding="utf-8")
            with patch.dict(os.environ, {"KFPS_FULL_LIVERY_STAGE": "stable"}):
                stable = FullLiveryFeatureGate.resolve(
                    qualification_file=evidence,
                    app_version="3.1.test",
                )
            self.assertTrue(stable.is_stable)
            self.assertEqual("qualification", stable.source)

    def test_isolated_worker_process_writes_a_durable_result_and_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_root = root / "app"
            app_root.mkdir()
            (app_root / "tools" / "livery-inspector").mkdir(parents=True)
            app_paths = SimpleNamespace(
                runtime_root=app_root / "runtime",
                exported_root=app_root / "imgs" / "exported",
            )
            paths = FullLiveryPaths.for_app(app_paths)
            paths.ensure()
            session = paths.sessions / "worker-contract"
            session.mkdir()
            request_file = session / "request.json"
            result_file = session / "result.json"
            request_paths = paths.as_worker_payload()
            request_paths.update({
                "app_root": str(app_root.resolve()),
                "inspector_root": str((app_root / "tools" / "livery-inspector").resolve()),
            })
            request_file.write_text(json.dumps({
                "protocol": PROTOCOL_VERSION,
                "request_id": "worker-contract",
                "operation": "refresh-packages",
                "kind": "refresh-packages",
                "metadata": {},
                "paths": request_paths,
                "payload": {},
                "session_dir": str(session.resolve()),
                "cancel_file": str((session / "cancel").resolve()),
            }), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "full_livery_process.py"),
                    "worker",
                    "--request",
                    str(request_file),
                    "--result",
                    str(result_file),
                    "--parent-pid",
                    str(os.getpid()),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            failure_detail = completed.stderr
            if result_file.is_file():
                failure_detail += result_file.read_text(encoding="utf-8", errors="replace")
            self.assertEqual(0, completed.returncode, failure_detail)
            result = json.loads(result_file.read_text(encoding="utf-8"))
            self.assertTrue(result["ok"])
            self.assertEqual([], result["value"]["rows"])
            marker = json.loads((session / "active.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", marker["state"])

    def test_abandoned_session_is_recorded_for_next_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = DiagnosticSession(root / "sessions" / "request", "scan-saves", "request")
            session.event("progress", count=12)
            recovered = recover_abandoned_sessions(root / "sessions", root / "recovery")
            self.assertEqual(["request"], recovered)
            record = json.loads((root / "recovery" / "request.json").read_text(encoding="utf-8"))
            self.assertEqual("abandoned", record["state"])

    def test_diagnostic_scrubbing_removes_windows_account_name(self):
        self.assertEqual(
            r"C:\Users\<user>\Desktop\KFPS",
            scrub_text(r"C:\Users\ExampleUser\Desktop\KFPS"),
        )


if __name__ == "__main__":
    unittest.main()
