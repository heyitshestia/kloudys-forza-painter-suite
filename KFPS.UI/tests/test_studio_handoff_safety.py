"""Preparation and HTTP handoff boundaries; synthetic assets, no game writes."""
import hashlib
import io
import json
import threading
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import test_livery_preparation_reuse as fixtures
from kfps_livery_lab import car_workspace as cars, server
from kfps_livery_lab.garage_build import BODY_PARTS


def build(wing=106):
    value = {"version": 1, "parts": {part: 101 + i for i, part in enumerate(BODY_PARTS)}}
    value["parts"]["RearWing"] = wing
    value["fingerprint"] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


class GarageSwitchPreparationTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.StudioSessionReuseTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.manager = self.case.manager
        self.document = {"scenes": [{"extras": {"kfps_part_options": [
            {"part_type": part, "id": 101 + i, "supported": True} for i, part in enumerate(BODY_PARTS)]}}]}
        from tools.livery import portable_mesh_converter
        self.enterContext(patch.object(portable_mesh_converter, "_glb_payloads", return_value=(self.document, b"")))
        self.prepared = {"manifest": {"inspection_runtime": {"fidelity": {}}}}
        self.assets = {"api/local-mesh": (self.case.base / "fixture.glb", "model/gltf-binary")}
        self.case.worker.side_effect = lambda _: (self.prepared, self.assets)
        self.case.validate.side_effect = lambda *_: (self.prepared, self.assets)

    def start(self, value):
        job = self.manager.start(f"{1:032x}", "INITIAL.zip", garage_build=value)
        self.manager.records[job["id"]]["thread"].join(3)
        return job["id"]

    def test_invalid_target_build_fails_before_ready_and_keeps_active_car(self):
        job = self.start(build(9999))
        self.assertEqual("failed", self.manager.poll(job)["status"])
        self.assertEqual("garage-build-unavailable", self.manager.poll(job)["error_code"])
        self.assertIsNone(self.manager.active_root)
        with self.assertRaises(cars.CarError):
            self.manager.commit(job, lambda *_: self.fail("invalid build activated"))

    def test_valid_build_commits_and_input_mutation_cannot_change_it(self):
        original = build()
        job = self.start(original)
        original["parts"]["RearWing"] = 9999
        self.assertEqual("ready", self.manager.poll(job)["status"])
        self.manager.commit(job, lambda *_: "new-session")
        self.assertEqual("committed", self.manager.poll(job)["status"])

    def test_commit_rechecks_target_parts_before_token_rotation(self):
        job = self.start(build())
        self.document["scenes"][0]["extras"]["kfps_part_options"].pop()
        with self.assertRaises(ValueError):
            self.manager.commit(job, lambda *_: self.fail("changed build activated"))
        self.assertIsNone(self.manager.active_root)

    def test_bad_snapshot_never_allocates_worker(self):
        with self.assertRaises(ValueError):
            self.start({**build(), "fingerprint": "0" * 64})
        self.case.worker.assert_not_called()
        self.assertEqual({}, self.manager.records)

    def test_worker_start_failure_can_retry_and_shutdown(self):
        with patch.object(cars.threading.Thread, "start", side_effect=RuntimeError("PRIVATE")):
            failed = self.manager.start(f"{1:032x}", "INITIAL.zip")
        self.assertEqual("failed", failed["status"])
        self.assertNotIn("PRIVATE", str(failed))
        job = self.start(build())
        self.assertEqual("ready", self.manager.poll(job)["status"])


class HandoffCarBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.host = server.LiveryLabServer.__new__(server.LiveryLabServer)
        self.host.state_lock = threading.RLock()
        self.host.token = "a" * 43
        self.host.httpd = SimpleNamespace(server_port=1234)
        self.host.chrome_exposed = False
        self.host.reply = Mock(side_effect=lambda _, status, value: (status, value))
        self.manager = self.host.car_workspace = Mock()
        self.manager.lock = threading.RLock()
        self.car_id, self.layout_id, self.job_id = "b" * 32, "c" * 32, "d" * 32
        self.vehicle = {"car_id": 344, "model_code": "NIS_FairladyZ_03"}
        self.manager.cars = {self.car_id: self.vehicle}
        self.manager.records = {self.job_id: {"automatic_handoff": True}}
        self.value = {"name": "fixture", "layout": {"vehicle": self.vehicle, "garage_build": build()},
                      "startup_session": self.host.url}
        self.read = self.enterContext(patch.object(server, "read_layout_handoff", return_value=self.value))

    def request(self, value, suffix=""):
        body = json.dumps(value).encode()
        headers = Message()
        headers["Content-Length"], headers["Content-Type"] = str(len(body)), "application/json"
        request = SimpleNamespace(command="POST", headers=headers, rfile=io.BytesIO(body))
        relative = "api/car-switch" + suffix
        target = urlsplit(f"/{self.host.token}/{relative}")
        return self.host._car_request(request, relative, target, self.host.token, "OLD.zip")

    def test_exact_granted_handoff_passes_frozen_build_to_preparation(self):
        self.assertEqual(202, self.request({"carId": self.car_id, "layoutId": self.layout_id})[0])
        self.manager.start.assert_called_once_with(self.car_id, "OLD.zip", garage_build=build(), automatic_handoff=True)

    def test_shared_stale_and_wrong_car_handoffs_never_prepare(self):
        for change in ("shared", "ungranted", "wrong-car"):
            with self.subTest(change=change):
                self.host.chrome_exposed = change == "shared"
                self.value["startup_session"] = "other" if change == "ungranted" else self.host.url
                self.value["layout"]["vehicle"] = {} if change == "wrong-car" else self.vehicle
                with self.assertRaises(cars.CarError):
                    self.request({"carId": self.car_id, "layoutId": self.layout_id})
        self.manager.start.assert_not_called()

    def test_opening_chrome_during_preparation_prevents_automatic_commit(self):
        self.host.chrome_exposed = True
        with self.assertRaises(cars.CarError):
            self.request({}, f"/{self.job_id}/commit")
        self.manager.commit.assert_not_called()

    def test_manual_car_selection_remains_available(self):
        self.host.chrome_exposed = True
        self.request({"carId": self.car_id})
        self.manager.start.assert_called_once_with(self.car_id, "OLD.zip")


if __name__ == "__main__":
    unittest.main()
