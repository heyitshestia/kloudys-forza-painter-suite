"""Exercise the installed worker entry point, protocol and dispatch in a child process."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(ROOT)]
from kfps_ui.experimental.full_livery.paths import FullLiveryPaths
from kfps_ui.garage_index import BODY_PARTS, digest


class GarageWorkerProcessTests(unittest.TestCase):
    def run_invalid_build(self, snapshot, expected_error):
        evidence = os.environ.get("KFPS_GARAGE_WORKER_EVIDENCE")
        evidence_root = Path(evidence).resolve() if evidence else None
        if evidence_root:
            evidence_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="garage-worker-", dir=evidence_root) as folder:
            root = Path(folder)
            app = root / "app"
            paths = FullLiveryPaths.for_app(SimpleNamespace(runtime_root=app / "runtime", exported_root=app / "exports"))
            session = root / "session"
            session.mkdir()
            request, result = session / "request.json", session / "result.json"
            path_values = paths.as_worker_payload()
            path_values.update(app_root=str(app), inspector_root=str(app / "tools/livery-inspector"))
            game = root / "must-not-read-game"
            game.mkdir()
            sentinel = game / "sentinel.txt"
            sentinel.write_bytes(b"No game assets or saves are needed for this regression.")
            before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
            value = {"protocol": 1, "request_id": "native-garage-protocol-test", "operation": "prepare-garage",
                     "kind": "garage-mesh", "paths": path_values, "session_dir": str(session),
                     "cancel_file": str(session / "cancel"), "payload": {
                         "game_folder": str(game), "identity": {"car_id": 344, "model_code": "NIS_FairladyZ_03"},
                         "garage_build": snapshot}}
            request.write_text(json.dumps(value), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("KFPS_") and k != "PYTHONPATH"}
            env.update(KFPS_APP_ROOT=str(app), KFPS_ACTIVITY_DISABLED="1", PYTHONDONTWRITEBYTECODE="1")
            for key in ("TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME"):
                location = root / "profile" / key.lower()
                location.mkdir(parents=True, exist_ok=True)
                env[key] = str(location)
            command = [sys.executable, "-I", "-B", str(UI / "full_livery_process.py"), "worker",
                       "--request", str(request), "--result", str(result), "--parent-pid", str(os.getpid())]
            with subprocess.Popen(command, cwd=UI, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
                try:
                    stdout, stderr = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate(timeout=5)
                    self.fail("Garage protocol worker did not exit within 15 seconds: " + stderr)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            (session / "stdout.log").write_text(stdout, encoding="utf-8")
            (session / "stderr.log").write_text(stderr, encoding="utf-8")
            try:
                self.assertEqual(2, process.returncode, stdout + stderr)
                self.assertTrue(result.is_file(), "Worker failed before writing its structured result: " + stderr)
                response = json.loads(result.read_text(encoding="utf-8"))
                self.assertEqual("prepare-garage", response["operation"])
                self.assertEqual("native-garage-protocol-test", response["request_id"])
                self.assertEqual(1, response["protocol"])
                self.assertFalse(response["ok"])
                self.assertFalse(response["cancelled"])
                self.assertEqual("GarageError", response["error_type"])
                self.assertIn(expected_error, response["error"])
                self.assertNotIn("Unsupported full-livery worker operation", response["error"] + stderr)
                trace = (session / "traceback.txt").read_text(encoding="utf-8")
                self.assertIn("validate_body_snapshot", trace)
                self.assertIn("prepare_garage", trace)
                events = [json.loads(line) for line in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertIn("operation_started", [event["event"] for event in events])
                self.assertEqual("session_completed", events[-1]["event"])
                self.assertFalse(events[-1]["ok"])
                self.assertEqual("failed", json.loads((session / "active.json").read_text())["state"])
                self.assertFalse(paths.vehicle_index.exists(), "Malformed build must fail before game indexing")
                self.assertEqual(before, hashlib.sha256(sentinel.read_bytes()).hexdigest())
                self.assertEqual([sentinel], list(game.rglob("*")))
                self.assertEqual([], list(paths.mesh_cache.rglob("*")))
                self.assertEqual([], list(paths.package_root.rglob("*")))
                self.assertNotIn("PRIVATE_TEST_VALUE", result.read_text(encoding="utf-8"))
                self.assertIsNotNone(process.poll())
            finally:
                if evidence_root:
                    target = evidence_root / self._testMethodName
                    target.mkdir(exist_ok=True)
                    for file in session.iterdir():
                        if file.is_file():
                            shutil.copy2(file, target / file.name)

    def test_missing_snapshot_returns_structured_failure_through_real_protocol(self):
        self.run_invalid_build(None, "snapshot is invalid")

    def test_unexpected_fields_are_rejected_without_echoing_values(self):
        parts = {name: 0 for name in BODY_PARTS}
        snapshot = {"version": 1, "parts": parts, "fingerprint": digest({"version": 1, "parts": parts}),
                    "private": "PRIVATE_TEST_VALUE"}
        self.run_invalid_build(snapshot, "snapshot is invalid")

    def test_changed_fingerprint_reaches_operation_validation_not_unknown_dispatch(self):
        snapshot = {"version": 1, "parts": {name: 0 for name in BODY_PARTS}, "fingerprint": "a" * 64}
        self.run_invalid_build(snapshot, "snapshot has changed")

    @unittest.skipUnless(os.environ.get("KFPS_GARAGE_REAL_GAME"), "Opt-in local car-asset integration")
    def test_real_body_fixture_prepares_through_native_worker(self):
        self._real_body_fixture(stock=False)

    @unittest.skipUnless(os.environ.get("KFPS_GARAGE_REAL_GAME"), "Opt-in local car-asset integration")
    def test_real_stock_prepares_through_native_worker(self):
        self._real_body_fixture(stock=True)

    def _real_body_fixture(self, *, stock):
        import psutil

        fixture_file = Path(os.environ["KFPS_GARAGE_REAL_FIXTURE"])
        source_index = Path(os.environ["KFPS_GARAGE_REAL_INDEX"])
        evidence = Path(os.environ["KFPS_GARAGE_WORKER_EVIDENCE"]).resolve()
        evidence.relative_to(ROOT.resolve())
        evidence.mkdir(parents=True, exist_ok=True)
        fixture_bytes = fixture_file.read_bytes()
        record = json.loads(fixture_bytes)["records"][0]
        identity, build = record["vehicle"], record["garage_build"]
        self.assertEqual(set(BODY_PARTS), set(build["parts"]))
        self.assertTrue(all(type(value) is int for value in build["parts"].values()))
        with tempfile.TemporaryDirectory(prefix="garage-real-worker-", dir=evidence) as folder:
            root = Path(folder)
            paths = FullLiveryPaths.for_app(SimpleNamespace(runtime_root=root / "runtime", exported_root=root / "exports"))
            paths.vehicle_index.parent.mkdir(parents=True)
            shutil.copy2(source_index, paths.vehicle_index)
            session = root / "session"
            session.mkdir()
            request, result, cancel = (session / name for name in ("request.json", "result.json", "cancel"))
            path_values = paths.as_worker_payload()
            path_values.update(app_root=str(ROOT), inspector_root=str(ROOT / "tools/livery-inspector"))
            request.write_text(json.dumps({"protocol": 1, "request_id": "native-garage-real-test",
                "operation": "prepare-garage", "kind": "garage-mesh", "paths": path_values,
                "session_dir": str(session), "cancel_file": str(cancel), "payload": {
                    "game_folder": os.environ["KFPS_GARAGE_REAL_GAME"], "identity": identity,
                    **({"stock": True} if stock else {"garage_build": build})}}), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("KFPS_") and k != "PYTHONPATH"}
            env.update(KFPS_APP_ROOT=str(ROOT), KFPS_ACTIVITY_DISABLED="1", KFPS_LIVERY_NO_OPEN="1",
                       PYTHONDONTWRITEBYTECODE="1")
            command = [sys.executable, "-I", "-B", str(UI / "full_livery_process.py"), "worker",
                       "--request", str(request), "--result", str(result), "--parent-pid", str(os.getpid())]
            children, peak_rss, timed_out, forced_cleanup = {}, 0, False, []
            started = time.monotonic()
            try:
                with subprocess.Popen(command, cwd=UI, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
                    worker = psutil.Process(process.pid)
                    try:
                        while True:
                            try:
                                descendants = worker.children(recursive=True)
                                for child in descendants:
                                    children[(child.pid, child.create_time())] = child
                                peak_rss = max(peak_rss, worker.memory_info().rss + sum(
                                    child.memory_info().rss for child in descendants if child.is_running()))
                            except psutil.NoSuchProcess:
                                pass
                            try:
                                stdout, stderr = process.communicate(timeout=.25)
                                break
                            except subprocess.TimeoutExpired:
                                if time.monotonic() - started > 120:
                                    timed_out = True
                                    cancel.touch()
                                    stdout, stderr = process.communicate(timeout=10)
                                    break
                    finally:
                        for child in children.values():
                            if child.is_running():
                                try:
                                    forced_cleanup.append("child")
                                    child.kill()
                                    child.wait(timeout=5)
                                except psutil.NoSuchProcess:
                                    pass
                        if process.poll() is None:
                            forced_cleanup.append("worker")
                            process.kill()
                            process.wait(timeout=5)
                (session / "stdout.log").write_text(stdout, encoding="utf-8")
                (session / "stderr.log").write_text(stderr, encoding="utf-8")
                self.assertFalse(timed_out, "Real preparation exceeded the bounded local test window")
                self.assertEqual([], forced_cleanup, "Preparation left processes requiring forced cleanup")
                self.assertEqual(0, process.returncode, stdout + stderr)
                response = json.loads(result.read_text(encoding="utf-8"))
                self.assertTrue(response["ok"], response.get("error"))
                self.assertEqual("prepare-garage", response["operation"])
                self.assertEqual("native-garage-real-test", response["request_id"])
                value = response["value"]
                self.assertEqual(identity, value["identity"])
                fingerprint = "stock" if stock else build["fingerprint"]
                self.assertEqual(fingerprint, value["garage_fingerprint"])
                descriptor = Path(value["readonly_descriptor"])
                self.assertEqual(hashlib.sha256(descriptor.read_bytes()).hexdigest(), value["readonly_descriptor_sha256"])
                sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
                from kfps_livery_lab.readonly_preview import read_descriptor
                checked = read_descriptor(descriptor)
                manifest = checked["manifest"]
                self.assertEqual(identity, {key: manifest["vehicle"][key] for key in identity})
                if stock:
                    self.assertNotIn("garage_build", manifest["inspection_runtime"])
                else:
                    self.assertEqual(build, manifest["inspection_runtime"]["garage_build"])
                self.assertEqual(manifest["package_id"], value["preview_id"])
                self.assertEqual(f"garage-body-{identity['car_id']}-{fingerprint}", value["preview_id"])
                self.assertIsInstance(value["preview_evidence"], dict)
                self.assertEqual("Stock body" if stock else "Garage body build", manifest["livery"]["title"])
                self.assertEqual([], list(paths.package_root.rglob("*")))
                self.assertEqual(fixture_bytes, fixture_file.read_bytes())
                self.assertFalse(any(child.is_running() for child in children.values()))
                events = [json.loads(line) for line in (session / "events.jsonl").read_text().splitlines()]
                self.assertEqual("session_completed", events[-1]["event"])
                self.assertTrue(events[-1]["ok"])
                summary = {"success": True, "stock": stock, "body_slot_count": 0 if stock else len(build["parts"]),
                           "mesh_cache_hit": value["mesh_cache_hit"], "descriptor_and_assets_reopened": True,
                           "preview_identity_matched": True, "worker_reaped": process.poll() is not None,
                           "descendants_remaining": 0, "forced_cleanup_count": len(forced_cleanup),
                           "elapsed_seconds": round(response["elapsed_seconds"], 3),
                           "peak_worker_tree_rss_bytes": peak_rss, "fixture_unchanged": True}
                (session / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            finally:
                target = evidence / self._testMethodName
                target.mkdir(exist_ok=True)
                for file in session.iterdir():
                    if file.is_file():
                        shutil.copy2(file, target / file.name)


if __name__ == "__main__":
    unittest.main()
