"""Verify document-scoped package export without servers, windows or games."""
from contextlib import ExitStack, nullcontext
import copy
from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI/src"), str(ROOT / "tools/livery-studio/src")]

from kfps_ui.app_paths import AppPaths
from kfps_ui.editor_service import EditorService
from kfps_ui.experimental.full_livery.paths import FullLiveryPaths
from kfps_ui.log_service import LogService
from kfps_livery_lab import host_bridge as bridge, server
from kfps_livery_lab.export_service import ExportService
from kfps_livery_lab.save_codec import NAMES
from test_garage_launch import build
from test_studio_package_handoff import make_package

VEHICLE = {"car_id": 3307, "model_code": "TEST_CAR"}


class StudioTemplateLaunchContractTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="template-launch-")))
        for target, name, value in (
                (bridge, "LAB_ROOT", self.root), (bridge, "HANDOFF_ROOT", self.root / "runs/inbox"),
                (bridge.launcher, "LAB_ROOT", self.root),
                (bridge.launcher, "CONTROL", self.root / "runs/control")):
            self.stack.enter_context(patch.object(target, name, value))
        ui = ROOT / "KFPS.UI"
        self.paths = AppPaths(self.root, ui, ui / "qml", ui / "assets", self.root / "runtime", Path(sys.executable))
        self.package = FullLiveryPaths.for_app(self.paths).package_root / "fixture.kfpslivery"
        self.package.parent.mkdir(parents=True)
        self.stack.enter_context(patch.object(bridge, "PACKAGE_LIBRARY", self.package.parent))
        make_package(self.package)
        self.before = self.package.read_bytes()
        self.request = bridge.request_for_package(self.package)
        # Exercise the production route handler without binding a socket.
        self.server = server.LiveryLabServer.__new__(server.LiveryLabServer)
        self.server.state_lock = threading.RLock()
        self.server.render_lock = threading.Lock()
        self.server.token = "a" * 43
        self.server.httpd = SimpleNamespace(server_port=1234)
        self.server.prepared = {"editor_config": {"vehicle": VEHICLE,
                               "sections": [{"section": name} for name in NAMES]}}
        self.server.workspace = self.root
        self.server.session_workspace = self.root
        self.server.assets = {}
        self.server.mask_pixels_cache = {}
        self.server.export_service = None
        self.server.renderer = SimpleNamespace(_resource=lambda _: True)
        self.server.language = SimpleNamespace(configuration=lambda: {})
        self.server.theme_context = SimpleNamespace(effective=lambda: {}, get=lambda: {})
        self.server.car_workspace = None
        self.server.chrome_exposed = False
        self.server.launch_archive = "TEST_CAR.zip"
        self.server.source_editor = Mock()
        self.server.reply = Mock()

    def route(self, path, body=None, binding=None):
        headers = Message()
        headers["Host"] = "127.0.0.1:1234"
        if binding is not None:
            headers["X-KFPS-Package-Handoff"] = binding
        raw = json.dumps(body).encode() if body is not None else b""
        if body is not None:
            headers["Content-Length"] = str(len(raw))
            headers["Content-Type"] = "application/json"
        request = SimpleNamespace(command="POST" if body is not None else "GET", headers=headers,
                                  path=f"/{self.server.token}/api/{path}", rfile=io.BytesIO(raw))
        self.server.reply.reset_mock()
        self.server.handle(request)
        self.server.reply.assert_called_once()
        return self.server.reply.call_args.args[1:3]

    def test_garage_package_worker_transfers_artwork_and_body_with_opaque_reference(self):
        log = LogService()
        self.addCleanup(log.close)
        with patch.object(EditorService, "refresh"):
            editor = EditorService(self.paths, Mock(), Mock(), log)
        self.addCleanup(editor.close)
        with patch.object(editor, "_start_thread") as queue:
            editor.launchGarageArtworkInLiveryStudio(VEHICLE, build(), str(self.package), "package")
        queue.assert_called_once()
        with patch.object(editor, "_resolve_studio_vehicle"), \
                patch.object(editor, "_garage_studio_bridge", return_value=bridge), \
                patch.object(editor, "_launch_studio_worker") as launch:
            queue.call_args.kwargs["target"](*queue.call_args.kwargs["args"])
        launch.assert_called_once()
        request = launch.call_args.args[0]
        self.assertEqual({"name", "layout", "package_ref"}, set(request))
        self.assertEqual(VEHICLE, request["layout"]["vehicle"])
        self.assertEqual(build(), request["layout"]["garage_build"])
        self.assertTrue(request["layout"]["vinyls"])
        self.assertNotIn(str(self.package), json.dumps(request))
        self.assertEqual(self.before, self.package.read_bytes())

    def test_package_export_is_page_scoped_and_can_encode_unrelated_new_artwork(self):
        identifier = bridge.stage_handoff(self.request)
        status, page = self.route("host-layout/" + identifier)
        self.assertEqual(200, status)
        self.assertTrue(page["package_template"])
        self.assertNotIn("package_ref", page)
        status, config = self.route("editor-config")
        self.assertEqual(200, status)
        self.assertEqual({"enabled": False, "reason": "No same-car export template was supplied.",
                          "template_layout_available": False}, config["experimental_export"])
        status, error = self.route("export-experiment", self.request["layout"])
        self.assertEqual(409, status)
        self.assertIn("same-car save export template", error["error"])
        project = copy.deepcopy(page["layout"])
        project["vinyls"][0]["shapes"] = [{"type":1048677,"data":[6,2,1,1,30,0,0],"color":[150,25,18,255]}]
        status, body = self.route("export-experiment", project, identifier)
        self.assertEqual(200, status, body if status != 200 else "")
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(project,json.loads(archive.read("layout.kfps-layout.json")))
        self.assertIsNone(self.server.export_service)
        self.assertEqual(self.before, self.package.read_bytes())

    def test_named_package_round_trip_with_new_art_and_unchanged_template(self):
        from tools.livery.fh6_save_installer import parse_fh6_header
        from tools.livery.package import validate_full_livery_package
        handle = bridge.stage_handoff(self.request)
        project = copy.deepcopy(self.request["layout"])
        project["vinyls"][0]["shapes"] = [{"type":1048677,"data":[6,2,1,1,30,0,0],"color":[150,25,18,255]}]
        identities = set()
        for title in ("Test design", "\u30c6\u30b9\u30c8"):
            status, data = self.route("export-package", {"project": project, "title": title}, handle)
            self.assertEqual(200, status, data if status != 200 else "")
            package = self.root / "new.kfpslivery"
            package.write_bytes(data)
            manifest = validate_full_livery_package(package, verify_previews=True)
            self.assertEqual(manifest["livery"]["title"], title)
            self.assertEqual(manifest["vehicle"]["car_id"], VEHICLE["car_id"])
            self.assertTrue(manifest["sharing"]["exportable"])
            with zipfile.ZipFile(package) as archive:
                header = parse_fh6_header(archive.read("source/fh6/header"))
                self.assertEqual(header.title, title)
                self.assertEqual(header.type_value, manifest["livery"]["logical_placement_count"])
                self.assertFalse({"experiment.json","layout.kfps-layout.json"}.intersection(archive.namelist()))
                identities.add(header.asset_guid)
            self.assertTrue(bridge.request_for_package(package)["layout"]["placements"])
        self.assertEqual(len(identities), 2)
        self.assertEqual(self.before, self.package.read_bytes())

    def test_package_endpoint_fails_closed(self):
        project = self.request["layout"]
        body = {"project": project, "title": "Test"}
        handle = bridge.stage_handoff(self.request)
        self.assertEqual(409, self.route("export-package", body)[0])
        self.assertNotEqual(200, self.route("export-package", body, "0"*32)[0])
        self.assertEqual(422, self.route("export-package", {**body, "path": "ignored"}, handle)[0])
        for bad in ("", " ", "x"*65, "\0oops", "\ud800", "\U0001f600"*33, None):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(422, self.route("export-package", {**body, "title": bad}, handle)[0])
        for changes in ({"vehicle_parts":{"RearWing":7}}, {"vehicle":{**VEHICLE, "car_id":1}}):
            self.assertEqual(422, self.route("export-package", {**body,"project":{**project,**changes}}, handle)[0])
        self.assertEqual(self.before, self.package.read_bytes())

    def test_stale_and_wrong_car_bound_exports_never_fall_back_to_global_exporter(self):
        identifier = bridge.stage_handoff(self.request)
        self.server.export_service = ExportService(self.package, VEHICLE, NAMES)
        project = self.request["layout"]
        self.assertEqual(400, self.route("export-experiment",project,"../outside")[0])
        self.assertNotEqual(200, self.route("export-experiment",project,"0"*32)[0])
        with patch.object(bridge.time, "time", return_value=__import__("time").time()+bridge.HANDOFF_LIFETIME+1):
            self.assertEqual(410, self.route("export-experiment",project,identifier)[0])
        with patch.dict(self.server.prepared["editor_config"], vehicle={**VEHICLE,"model_code":"MISMATCH"}):
            self.assertEqual(409, self.route("export-experiment",project,identifier)[0])
        self.package.write_bytes(self.before+b"changed")
        self.assertEqual(409,self.route("export-experiment",project,identifier)[0])
        self.package.unlink()
        self.assertEqual(409,self.route("export-experiment",project,identifier)[0])

    def test_external_package_remains_artwork_only(self):
        external = self.root/"external.kfpslivery"
        external.write_bytes(self.before)
        request = bridge.request_for_package(external)
        self.assertNotIn("package_ref",request)
        identifier = bridge.stage_handoff(request)
        self.assertNotIn("package_template",self.route("host-layout/"+identifier)[1])
        self.assertEqual(409,self.route("export-experiment",request["layout"],identifier)[0])

    def test_explicit_template_distinguishes_fitted_block_from_valid_artwork(self):
        exporter = ExportService(self.package, VEHICLE, NAMES)
        self.server.export_service = exporter
        fitted = copy.deepcopy(self.request["layout"])
        fitted["vehicle_parts"] = {"RearWing": 7}
        status, error = self.route("export-experiment", fitted)
        self.assertEqual(422, status)
        self.assertIn("Configured body/parts", error["error"])
        self.assertIs(exporter, self.server.export_service)
        self.assertTrue(self.route("editor-config")[1]["experimental_export"]["enabled"])
        status, body = self.route("export-experiment", self.request["layout"])
        self.assertEqual(200, status)
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("candidate/C_livery", archive.namelist())
            self.assertFalse(json.loads(archive.read("experiment.json"))["installed"])
        self.assertEqual(self.before, self.package.read_bytes())

    def test_wrong_car_project_cannot_use_an_existing_template(self):
        exporter = ExportService(self.package, VEHICLE, NAMES)
        self.server.export_service = exporter
        project = copy.deepcopy(self.request["layout"])
        project["vehicle"]["car_id"] += 1
        status, error = self.route("export-experiment", project)
        self.assertEqual(422, status)
        self.assertIn("different car", error["error"])
        self.assertIs(exporter, self.server.export_service)

    def test_host_launch_only_passes_vehicle_to_backend_readiness(self):
        ready = {"url": "http://127.0.0.1:1234/" + "a" * 43 + "/", "reused": True}
        with patch.object(bridge.launcher, "ensure_ready", return_value=ready) as ensure, \
                patch.object(bridge, "_check_package_target", return_value=False), \
                patch.object(bridge, "_native_admission", return_value=nullcontext()):
            result = bridge.launch_from_host(self.root, self.request)
        ensure.assert_called_once_with(expected_kfps_root=self.root, cancelled=None, initial_vehicle=VEHICLE)
        self.assertTrue(result["transferred"])

    def test_car_activation_invalidates_previous_template(self):
        self.server.export_service = ExportService(self.package, VEHICLE, NAMES)
        prepared = {"editor_config": {"vehicle": {"car_id": 999, "model_code": "OTHER"}}}
        with patch.object(server, "atomic_json"):
            self.server._activate_car(prepared, self.root, {}, self.server.token)
        self.assertIsNone(self.server.export_service)

    def test_template_path_cannot_be_smuggled_into_artwork_request(self):
        for key in ("template", "template_path", "export_template"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bridge.validate_request({**self.request, key: str(self.package)})


if __name__ == "__main__":
    unittest.main()
