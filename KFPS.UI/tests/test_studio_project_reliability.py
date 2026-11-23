"""Studio save/recovery failure and restart qualification with isolated fixtures."""
from contextlib import closing
import hashlib
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/tests"), str(ROOT / "KFPS.UI/src"),
               str(ROOT / "tools/livery-studio/src")]
from kfps_livery_lab import recovery as r
from kfps_livery_lab.project_storage import ProjectStore
from kfps_livery_lab.managed_recovery import CarRecoveryStore
from kfps_livery_lab.storage_paths import StorageError
from test_garage_studio_workflow import project, VEHICLE


class ProjectReliabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kfps-project-reliability-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = ProjectStore(self.root / "projects")
        self.legacy = self.root / "legacy"
        isolated = patch.object(r, "LAB_ROOT", self.root)
        isolated.start()
        self.addCleanup(isolated.stop)
        self.recovery = CarRecoveryStore(self.store, self.legacy)

    def save(self, value=None, prior=None, name="Fixture"):
        payload = {"name": name, "project": project() if value is None else value}
        if prior:
            payload.update(id=prior["id"], expected_revision=prior["revision"])
        return self.store.save(VEHICLE, payload)["entry"]

    def checkpoint(self, value=None, kind="checkpoint"):
        return self.recovery.save(VEHICLE, {"document_id": "a" * 32, "kind": kind,
            "name": "Fixture", "project": project() if value is None else value})["entry"]

    def test_save_replace_restart_retains_complete_project(self):
        first = self.save()
        changed = project()
        changed["vehicle_parts"]["RearWing"] = 12
        changed["vinyls"][0]["shapes"][0].update(mask=True, data=[10, 20, 1, -1, 33, .2, 1])
        second = self.save(changed, first)
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["revision"], second["revision"])
        reopened = ProjectStore(self.store.root).open(VEHICLE, second["id"])
        self.assertEqual(reopened["project"], changed)
        self.assertEqual(len(list(self.store.root.rglob("*.json"))), 1)
        with self.assertRaises(StorageError) as caught:
            self.save(project(), first)
        self.assertEqual(caught.exception.code, "project_changed")
        self.assertEqual(ProjectStore(self.store.root).open(VEHICLE, first["id"])["project"], changed)

    def test_interrupted_publish_before_and_after_rename_preserves_prior_revision(self):
        first = self.save()
        for after in (False, True):
            with self.subTest(after_rename=after):
                changed = project()
                changed["placements"][0]["x"] = 900
                publish = self.store._publish

                def interrupted(*args):
                    if after:
                        publish(*args)
                    raise OSError("private test fault")

                with patch.object(self.store, "_publish", interrupted), self.assertRaises(StorageError) as caught:
                    self.save(changed, first)
                self.assertNotIn("private test fault", str(caught.exception))
                self.store = ProjectStore(self.store.root)
                self.assertEqual(self.store.open(VEHICLE, first["id"])["project"], project())
        changed = project()
        changed["placements"][0]["x"] = 900
        final = self.save(changed, first)
        self.assertEqual(ProjectStore(self.store.root).open(VEHICLE, final["id"])["project"], changed)
        self.assertEqual(len(list(self.store.root.rglob("*.json"))), 1)

    def test_locked_obsolete_revision_does_not_block_new_durable_save(self):
        first = self.save()
        old_file = next(self.store.root.rglob(first["file_name"]))
        original = Path.unlink

        def locked(path, *args, **kwargs):
            if path == old_file:
                raise PermissionError("obsolete revision temporarily in use")
            return original(path, *args, **kwargs)

        changed = project()
        with patch.object(Path, "unlink", locked):
            changed["placements"][0]["x"] = 10
            second = self.save(changed, first)
            changed["placements"][0]["x"] = 20
            third = self.save(changed, second)
        self.assertTrue(old_file.exists())
        self.assertEqual(ProjectStore(self.store.root).open(VEHICLE, third["id"])["project"], changed)
        self.save(changed, third)
        self.assertFalse(old_file.exists())

    def test_unmanaged_generated_looking_file_is_never_cleaned(self):
        first = self.save()
        directory = next(self.store.root.rglob(first["file_name"])).parent
        foreign = directory / ("b" * 32 + "-" + "c" * 16 + ".json")
        foreign.write_bytes(b"user-owned unrelated data")
        changed = project()
        changed["placements"][0]["x"] = 40
        self.save(changed, first)
        self.assertEqual(foreign.read_bytes(), b"user-owned unrelated data")

    def test_recovery_restart_restore_retains_current_and_never_marks_file_saved(self):
        first = self.checkpoint()
        current = project()
        current["placements"][0]["x"] = 500
        restarted = CarRecoveryStore(ProjectStore(self.store.root), self.legacy)
        restored = restarted.prepare_restore(VEHICLE, first["id"],
            {"document_id": "b" * 32, "current_project": current})
        self.assertEqual(restored["project"], project())
        retained = restarted.prepare_restore(VEHICLE, restored["retained"]["id"],
            {"document_id": "c" * 32, "current_project": project()})
        self.assertEqual(retained["project"], current)
        self.assertEqual(self.store.list(VEHICLE)["entries"], [])

    def test_corrupt_recovery_target_never_replaces_or_retains_current(self):
        first = self.checkpoint()
        path = next(self.store.root.rglob("recovery.sqlite3"))
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE entries SET project=? WHERE id=?", (b"{}", first["id"]))
        before = self.recovery.list(VEHICLE)["entries"]
        with self.assertRaises(r.RecoveryError) as caught:
            self.recovery.prepare_restore(VEHICLE, first["id"],
                {"document_id": "b" * 32, "current_project": project()})
        self.assertEqual(caught.exception.status, 409)
        self.assertEqual(self.recovery.list(VEHICLE)["entries"], before)

    def test_failed_retention_rolls_back_pruning_and_preserves_checkpoints(self):
        first = self.checkpoint()
        automatic = self.checkpoint(kind="auto")
        before = self.recovery.list(VEHICLE)["entries"]
        with patch.object(r, "MAX_TOTAL_BYTES", 1), self.assertRaises(r.RecoveryError) as caught:
            self.recovery.prepare_restore(VEHICLE, first["id"],
                {"document_id": "b" * 32, "current_project": project()})
        self.assertEqual(caught.exception.status, 507)
        self.assertEqual(self.recovery.list(VEHICLE)["entries"], before)
        self.assertIn(automatic["id"], {entry["id"] for entry in before})

    def test_legacy_restore_is_readonly_and_retains_current_in_managed_store(self):
        legacy = r.RecoveryStore(self.legacy)
        first = legacy.save(VEHICLE, {"document_id": "a" * 32, "kind": "checkpoint",
                                      "name": "Legacy", "project": project()})["entry"]
        before = hashlib.sha256(legacy.path.read_bytes()).hexdigest()
        changed = project()
        changed["placements"][0]["x"] = 9
        result = self.recovery.prepare_restore(VEHICLE, first["id"],
            {"document_id": "b" * 32, "current_project": changed})
        self.assertEqual(result["entry"]["source"], "legacy")
        self.assertEqual(hashlib.sha256(legacy.path.read_bytes()).hexdigest(), before)
        self.assertEqual(len(self.recovery.list(VEHICLE)["entries"]), 2)

    def test_auto_dedup_rotation_protected_entries_and_wrong_car(self):
        checkpoint = self.checkpoint()
        first = self.checkpoint(kind="auto")
        self.assertEqual(first["id"], self.checkpoint(kind="auto")["id"])
        for index in range(8):
            changed = project()
            changed["placements"][0]["x"] = index
            self.checkpoint(changed, kind="auto")
        entries = self.recovery.list(VEHICLE)["entries"]
        self.assertEqual(sum(row["kind"] == "auto" for row in entries), r.AUTO_PER_DOCUMENT)
        self.assertIn(checkpoint["id"], {row["id"] for row in entries})
        other = {"car_id": 99, "model_code": "OTHER"}
        self.assertEqual(self.recovery.list(other)["entries"], [])

    def test_large_project_roundtrip_and_oversize_fail_without_mutation(self):
        value = project()
        base = value["vinyls"][0]
        base["shapes"][0]["shape_name"] = "x" * 400
        value["vinyls"] = [{"id": f"source-{index}", "name": f"Source {index}",
                            "shapes": base["shapes"] * 3000} for index in range(16)]
        value["placements"] = []
        value.pop("authoring")
        raw = r._project(value, VEHICLE)
        self.assertLess(len(raw), r.MAX_PROJECT_BYTES)
        first = self.save(value)
        self.assertEqual(ProjectStore(self.store.root).open(VEHICLE, first["id"])["project"], value)
        checkpoint = self.checkpoint(value)
        restored = self.recovery.prepare_restore(VEHICLE, checkpoint["id"],
            {"document_id": "b" * 32, "current_project": project()})
        self.assertEqual(restored["project"], value)
        value["vinyls"][0]["shapes"][0]["shape_name"] = "x" * 800
        with self.assertRaises(r.RecoveryError) as caught:
            self.save(value, first)
        self.assertEqual(caught.exception.status, 413)
        reopened = self.store.open(VEHICLE, first["id"])["project"]
        self.assertEqual(reopened["vinyls"][0]["shapes"][0]["shape_name"], "x" * 400)


class ProjectReliabilityRouteTests(unittest.TestCase):
    def setUp(self):
        from test_studio_preview_quality_routes import PreviewQualityRouteTests
        self.fixture = PreviewQualityRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepared["editor_config"]["vehicle"] = dict(VEHICLE)

    def request(self, method, route, value=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.fixture.server.httpd.server_port, timeout=20)
        try:
            body = None if value is None else json.dumps(value).encode()
            connection.request(method, self.fixture.prefix + "api/" + route, body,
                               {"Content-Type": "application/json", **(headers or {})})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_real_routes_save_recovery_restart_and_restore(self):
        status, saved = self.request("POST", "projects", {"name": "Fixture", "project": project()})
        self.assertEqual(status, 200)
        status, checkpoint = self.request("POST", "recovery", {"document_id": "a" * 32,
            "kind": "checkpoint", "name": "Fixture", "project": project()})
        self.assertEqual(status, 200)
        self.fixture.server.close()
        self.fixture.start()
        self.assertEqual(self.request("GET", "projects/" + saved["entry"]["id"])[1]["project"], project())
        self.assertEqual(len(self.request("GET", "recovery")[1]["entries"]), 1)
        changed = project()
        changed["placements"][0]["x"] = 55
        status, restored = self.request("POST", "recovery/" + checkpoint["entry"]["id"] + "/restore",
            {"document_id": "b" * 32, "current_project": changed})
        self.assertEqual(status, 200)
        self.assertEqual(restored["project"], project())
        self.assertEqual(restored["retained"]["kind"], "before-restore")
        self.assertEqual(len(self.request("GET", "recovery")[1]["entries"]), 2)

    def test_write_failure_and_invalid_data_leave_previous_project_openable(self):
        status, saved = self.request("POST", "projects", {"name": "Fixture", "project": project()})
        self.assertEqual(status, 200)
        changed = project()
        changed["placements"][0]["x"] = 80
        payload = {"name": "Fixture", "project": changed, "id": saved["entry"]["id"],
                   "expected_revision": saved["entry"]["revision"]}
        with patch("kfps_livery_lab.project_storage.os.fsync", side_effect=OSError("private location")):
            status, result = self.request("POST", "projects", payload)
        self.assertEqual(status, 503)
        self.assertNotIn("private location", json.dumps(result))
        changed["placements"][0]["x"] = float("nan")
        self.assertEqual(self.request("POST", "projects", payload)[0], 422)
        self.assertEqual(self.request("GET", "projects/" + saved["entry"]["id"])[1]["project"], project())

    def test_large_project_above_vinyl_limit_roundtrips_through_real_http(self):
        value = project()
        shape = value["vinyls"][0]["shapes"][0]
        shape["shape_name"] = "x" * 400
        value["vinyls"] = [{"id": f"s{index}", "name": "Large fixture", "shapes": [shape] * 3000}
                            for index in range(8)]
        value["placements"] = []
        value.pop("authoring")
        self.assertGreater(len(json.dumps(value).encode()), 8 * 1024 * 1024)
        status, saved = self.request("POST", "projects", {"name": "Large fixture", "project": value})
        self.assertEqual(status, 200)
        status, result = self.request("GET", "projects/" + saved["entry"]["id"])
        self.assertEqual(status, 200)
        self.assertEqual(result["project"], value)

    def test_cross_origin_and_incomplete_requests_do_not_create_projects(self):
        for route in ("projects", "recovery"):
            self.assertEqual(self.request("POST", route, {}, {"Origin": "http://evil.test"})[0], 403)
        import socket
        with socket.create_connection(("127.0.0.1", self.fixture.server.httpd.server_port), timeout=3) as sock:
            body = (f"POST {self.fixture.prefix}api/projects HTTP/1.0\r\n"
                    f"Host: {self.fixture.server.origin[7:]}\r\nContent-Type: application/json\r\n"
                    "Content-Length: 100\r\n\r\n{}").encode()
            sock.sendall(body)
            sock.shutdown(socket.SHUT_WR)
            response = http.client.HTTPResponse(sock)
            response.begin()
            self.assertEqual(response.status, 400)
            response.read()
        self.assertEqual(self.request("GET", "projects")[1]["entries"], [])


if __name__ == "__main__":
    if "--serve" in sys.argv:
        fixture = ProjectReliabilityRouteTests()
        fixture.setUp()
        try:
            web = ROOT / "tools/livery-studio/src/web"
            for name in ("project-storage-ui.mjs", "recovery-ui.mjs", "layout-model.mjs", "mirror-links.mjs",
                         "i18n.mjs", "locales/en.mjs", "locales/ja.mjs", "locales/ko.mjs"):
                target = fixture.fixture.web / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((web / name).read_bytes())
            (fixture.fixture.web / "index.html").write_text(
                '<!doctype html><html><head><meta charset="utf-8"><title>Project reliability fixture</title>'
                '<style>body{font:16px sans-serif}dialog{width:540px}button,input,select{margin:8px;padding:8px}'
                'label{display:block}.error{color:#b00}</style></head><body><div id="recoveryHost"></div></body></html>',
                encoding="utf-8")
            fixture.fixture.server.close()
            fixture.fixture.start()
            print(json.dumps({"url": fixture.fixture.server.origin + fixture.fixture.prefix}), flush=True)
            sys.stdin.readline()
        finally:
            fixture.doCleanups()
    else:
        unittest.main()
