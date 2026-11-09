"""Package startup ordering without a game, converter, browser or native window."""
from contextlib import ExitStack, nullcontext
import copy
from email.message import Message
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab import host_bridge as bridge

launcher = bridge.launcher
registered = launcher._registered
read_json = launcher._read_json
VEHICLE = {"car_id": 3307, "model_code": "PACKAGE_CAR"}


class PackageLaunchTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.config = {"kfpsRoot": str(self.root / "kfps"), "gameRoot": str(self.root / "game"),
                       "pythonExe": str(self.root / "python.exe"), "archive": "DEFAULT.zip"}
        for path in (self.root / "kfps", self.root / "game/media/Cars", self.root / "runs"):
            path.mkdir(parents=True, exist_ok=True)
        for path in (self.root / "python.exe", self.root / "kfps/json_preview_renderer.py",
                     self.root / "game/media/Cars/DEFAULT.zip", self.root / "game/media/Cars/PACKAGE_CAR.zip"):
            path.touch()
        self.patch(launcher, "LAB_ROOT", self.root)
        self.patch(launcher, "CONTROL", self.root / "runs/control")
        self.patch(launcher, "WORKSPACE", self.root / "runs/workspace")
        self.patch(launcher, "load_config", return_value=self.config)
        self.patch(launcher, "_launch_lock", return_value=nullcontext())
        self.patch(launcher, "_registered", return_value=None)
        self.patch(launcher, "_read_json", side_effect=FileNotFoundError)
        self.records = self.patch(launcher, "_atomic_json")
        self.spawn = self.patch(launcher, "_spawn", return_value=Mock(pid=123, poll=Mock(return_value=None)))
        self.patch(launcher.psutil, "Process", return_value=SimpleNamespace(create_time=lambda: 1, is_running=lambda: True))
        self.ready = {"pid": 123, "url": "http://127.0.0.1:1234/" + "a" * 43 + "/", "reused": True,
                      "vehicle": VEHICLE.copy()}
        self.patch(launcher, "_ready_record", return_value=self.ready.copy())

    def patch(self, target, name, *args, **kwargs):
        return self.stack.enter_context(patch.object(target, name, *args, **kwargs))

    def catalogue(self, rows=None):
        from kfps_livery_lab import car_workspace, prepare
        self.patch(prepare, "load_baseline", return_value=self.root)
        return self.patch(car_workspace, "catalogue", return_value=rows if rows is not None else {
            "exact": {**VEHICLE, "archive": "PACKAGE_CAR.zip"},
            "wrong-id": {**VEHICLE, "car_id": 99, "archive": "DEFAULT.zip"}})

    def test_cold_package_prepares_exact_car_once_without_changing_default_or_template(self):
        template = self.root / "default-template.zip"
        template.touch()
        self.config["template"] = str(template)
        before = copy.deepcopy(self.config)
        self.catalogue()
        result = launcher.ensure_ready(initial_vehicle=VEHICLE, discover=False)
        self.assertFalse(result["reused"])
        self.spawn.assert_called_once_with({key: value for key, value in
            dict(self.config, archive="PACKAGE_CAR.zip").items() if key != "template"})
        self.assertEqual(self.config, before)
        self.assertTrue(all(call.args[0] == launcher.CONTROL / "instance.json" for call in self.records.call_args_list))
        self.assertEqual(self.records.call_args.args[1]["launch_config"]["archive"], "PACKAGE_CAR.zip")

    def test_missing_or_ambiguous_identity_never_spawns(self):
        for rows in ({}, {"a": {**VEHICLE, "archive": "PACKAGE_CAR.zip"},
                         "b": {**VEHICLE, "archive": "PACKAGE_CAR.zip"}}):
            self.catalogue(rows)
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(ValueError, "exact|ambiguous"):
                    launcher.ensure_ready(initial_vehicle=VEHICLE, discover=False)
        self.spawn.assert_not_called()
        self.records.assert_not_called()

    def test_actual_catalogue_selects_by_clip_id_and_model_code(self):
        from kfps_livery_lab import prepare
        from tools.livery import vehicle_assets
        self.patch(prepare, "load_baseline", return_value=self.root)
        for name, car_id in (("DEFAULT.zip", 99), ("PACKAGE_CAR.zip", 3307), ("OTHER.zip", 3307)):
            with zipfile.ZipFile(self.root / "game/media/Cars" / name, "w") as archive:
                archive.writestr(f"fixture/carclips_{car_id}.clipd", b"synthetic fixture")
        with patch.object(vehicle_assets, "_car_clip_in_archive", wraps=vehicle_assets._car_clip_in_archive) as inspect:
            launcher.ensure_ready(initial_vehicle=VEHICLE, discover=False)
            inspect.assert_called_once_with(self.root / "game/media/Cars/PACKAGE_CAR.zip")
        self.assertEqual(self.spawn.call_args.args[0]["archive"], "PACKAGE_CAR.zip")
        self.spawn.assert_called_once()

    def test_filtered_catalogue_missing_model_reads_no_archives_and_keeps_bounds(self):
        from kfps_livery_lab import car_workspace
        from tools.livery import vehicle_assets
        with patch.object(vehicle_assets, "_car_clip_in_archive") as inspect:
            self.assertEqual(car_workspace.catalogue(self.config["gameRoot"], model_code="MISSING"), {})
            inspect.assert_not_called()
            with patch.object(car_workspace, "MAX_DIRECTORY_ENTRIES", 1), self.assertRaises(car_workspace.CarError):
                car_workspace.catalogue(self.config["gameRoot"], model_code="MISSING")

    def test_default_catalogue_still_reads_all_valid_archives(self):
        from kfps_livery_lab import car_workspace
        from tools.livery import vehicle_assets
        for name in ("DEFAULT.zip", "PACKAGE_CAR.zip"):
            with zipfile.ZipFile(self.root / "game/media/Cars" / name, "w") as archive:
                archive.writestr("carclips_3307.clipd", b"fixture")
        with patch.object(vehicle_assets, "_car_clip_in_archive", wraps=vehicle_assets._car_clip_in_archive) as inspect:
            self.assertEqual(len(car_workspace.catalogue(self.config["gameRoot"])), 2)
            self.assertEqual(inspect.call_count, 2)

    def test_filtered_catalogue_preserves_redirect_and_size_checks(self):
        from kfps_livery_lab import car_workspace
        from tools.livery import vehicle_assets
        with patch.object(vehicle_assets, "_car_clip_in_archive") as inspect:
            self.assertEqual(car_workspace.catalogue(self.config["gameRoot"], model_code="PACKAGE_CAR"), {})
            inspect.assert_not_called()
            with patch.object(Path, "is_symlink", return_value=True):
                self.assertEqual(car_workspace.catalogue(self.config["gameRoot"], model_code="PACKAGE_CAR"), {})
            inspect.assert_not_called()

    def test_reused_backend_is_not_reprepared_for_package(self):
        self.patch(launcher, "_registered", return_value=self.ready)
        catalogue = self.catalogue()
        self.assertIs(launcher.ensure_ready(initial_vehicle=VEHICLE, discover=False), self.ready)
        catalogue.assert_not_called()
        self.spawn.assert_not_called()

    def test_workspace_claim_precedes_post_startup_cancellation(self):
        cancelled = threading.Event()
        callback = Mock(side_effect=lambda _result: cancelled.set())
        self.patch(launcher, 'ensure_ready', return_value=self.ready)
        with self.assertRaises(launcher.LaunchCancelled):
            bridge.launch_from_host(self.root, cancelled=cancelled, backend_ready=callback)
        callback.assert_called_once_with(self.ready)

    def test_cancel_during_resolution_does_not_spawn(self):
        cancelled = threading.Event()
        catalogue = self.catalogue()
        catalogue.side_effect = lambda _, **_kwargs: (cancelled.set() or {"exact": {**VEHICLE, "archive": "PACKAGE_CAR.zip"}})
        with self.assertRaises(launcher.LaunchCancelled):
            launcher.ensure_ready(initial_vehicle=VEHICLE, cancelled=cancelled, discover=False)
        self.spawn.assert_not_called()

    def test_invalid_target_is_rejected_before_spawn(self):
        for value in ({}, {**VEHICLE, "car_id": True}, {**VEHICLE, "model_code": "../escape"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                launcher.ensure_ready(initial_vehicle=value, discover=False)
        self.spawn.assert_not_called()

    def test_effective_record_configuration_stays_in_same_installation(self):
        effective = dict(self.config, archive="PACKAGE_CAR.zip")
        self.assertEqual(launcher._record_config(self.config, {"launch_config": effective}), effective)
        other = dict(effective, kfpsRoot=str(self.root))
        with self.assertRaises(ValueError):
            launcher._record_config(self.config, {"launch_config": other})

    def test_pending_package_launch_is_not_overwritten_by_default_launch(self):
        effective = dict(self.config, archive="PACKAGE_CAR.zip")
        self.patch(launcher, "_read_json", return_value={"status": "starting", "pid": 123,
            "created": 1, "workspace": str(launcher.WORKSPACE), "launch_config": effective})
        inspect = self.patch(launcher, "inspect_process", return_value=object())
        with self.assertRaisesRegex(RuntimeError, "still preparing"):
            launcher.ensure_ready(discover=False)
        self.assertEqual(inspect.call_args.args[1], effective)
        self.spawn.assert_not_called()

    def test_registered_package_backend_reuses_effective_archive(self):
        effective = dict(self.config, archive="PACKAGE_CAR.zip")
        self.patch(launcher, "_read_json", return_value={"managed": True, "pid": 123, "created": 1,
            "workspace": str(launcher.WORKSPACE), "launch_config": effective})
        ready = self.patch(launcher, "_ready_record", return_value=self.ready)
        self.assertIs(registered(self.config), self.ready)
        self.assertEqual(ready.call_args.args[1], effective)
        self.assertTrue(ready.call_args.kwargs["managed"])

    def test_dead_missing_and_recycled_registration_skip_obsolete_config(self):
        invalid = {"archive": "removed.zip", "template": str(self.root / "removed.zip")}
        for pid, created in ((None, 1), (456, 1), (789, 1)):
            with self.subTest(pid=pid):
                self.patch(launcher, "_read_json", return_value={"pid": pid, "created": created,
                    "workspace": str(launcher.WORKSPACE), "launch_config": invalid})
                def process(identifier):
                    if identifier == 456:
                        raise launcher.psutil.NoSuchProcess(identifier)
                    return SimpleNamespace(create_time=lambda: 2, is_running=lambda: True)
                self.patch(launcher.psutil, "Process", side_effect=process)
                restricted = self.patch(launcher, "_record_config", side_effect=AssertionError("Dead config was validated"))
                self.assertIsNone(registered(self.config))
                restricted.assert_not_called()

    def test_dead_registration_does_not_prevent_restart_after_paths_change(self):
        def process(pid):
            if pid == 456:
                raise launcher.psutil.NoSuchProcess(pid)
            return SimpleNamespace(create_time=lambda: 2 if pid == 789 else 1, is_running=lambda: True)
        self.patch(launcher.psutil, "Process", side_effect=process)
        self.patch(launcher, "_record_config", side_effect=AssertionError("Dead config was validated"))
        for pid in (None, 456, 789):
            with self.subTest(pid=pid):
                stale = {"pid": pid, "created": 1, "status": "starting", "workspace": str(launcher.WORKSPACE),
                         "launch_config": dict(self.config, archive="removed.zip", template=str(self.root / "removed.zip"),
                                               kfpsRoot=str(self.root / "removed-root"))}
                def read(path, *_):
                    if path == launcher.CONTROL / "instance.json":
                        return stale
                    raise FileNotFoundError()
                self.patch(launcher, "_read_json", side_effect=read)
                self.spawn.reset_mock()
                self.assertFalse(launcher.ensure_ready(discover=False)["reused"])
                self.spawn.assert_called_once_with(self.config)

    def test_matching_live_nonresponsive_session_is_not_replaced(self):
        self.patch(launcher, "_read_json", return_value={"pid": 123, "created": 1,
            "workspace": str(launcher.WORKSPACE), "launch_config": self.config})
        self.patch(launcher, "inspect_process", return_value=object())
        with self.assertRaisesRegex(RuntimeError, "not responding"):
            launcher.ensure_ready(discover=False)
        self.spawn.assert_not_called()

    def test_malformed_record_root_is_ignored_before_liveness(self):
        launcher.CONTROL.mkdir(parents=True)
        (launcher.CONTROL / "instance.json").write_text("[]", encoding="utf-8")
        self.patch(launcher, "_read_json", read_json)
        alive = self.patch(launcher, "_registration_alive", side_effect=AssertionError("Malformed record reached liveness"))
        self.assertIsNone(registered(self.config))
        self.assertFalse(launcher.ensure_ready(discover=False)["reused"])
        alive.assert_not_called()
        self.spawn.assert_called_once()

    def test_invalid_registered_configuration_fails_closed_before_spawn(self):
        self.patch(launcher, "_read_json", return_value={"status": "starting", "pid": 123,
            "workspace": str(launcher.WORKSPACE), "launch_config": dict(self.config, archive="../outside.zip")})
        with self.assertRaises(launcher.IncompatibleStudio):
            launcher.ensure_ready(discover=False)
        self.spawn.assert_not_called()

    def test_cancel_after_spawn_terminates_only_effective_owned_launch(self):
        self.catalogue()
        cancelled = threading.Event()
        self.spawn.side_effect = lambda _: (cancelled.set() or Mock(pid=123, poll=Mock(return_value=None)))
        terminate = self.patch(launcher, "_terminate_owned")
        with self.assertRaises(launcher.LaunchCancelled):
            launcher.ensure_ready(initial_vehicle=VEHICLE, cancelled=cancelled, discover=False)
        self.assertEqual(terminate.call_args.args[2]["archive"], "PACKAGE_CAR.zip")
        self.assertEqual(self.config["archive"], "DEFAULT.zip")

    def test_cold_wrong_car_receipt_is_never_published_or_opened(self):
        self.catalogue()
        self.patch(launcher, "_ready_record", return_value=dict(self.ready, vehicle={"car_id": 99, "model_code": "OTHER"}))
        terminate = self.patch(launcher, "_terminate_owned")
        with self.assertRaisesRegex(ValueError, "exact car"):
            launcher.ensure_ready(initial_vehicle=VEHICLE, discover=False)
        terminate.assert_called_once()
        self.assertEqual(self.records.call_count, 1)

    def test_old_backend_without_bootstrap_assets_requires_restart(self):
        capabilities = {key: True for key in ("native_mask_pixels", "host_vinyl_handoff", "host_theme_handoff",
            "ui_theme_persistence", "source_editor_roundtrip")}
        capabilities.update({key: {"enabled": True, "version": 1} for key in ("recovery", "project_storage", "vinyl_library")})
        capabilities["vehicle"] = {"archive_name": "DEFAULT.zip"}
        capabilities["chrome_exposed"] = False
        for version in (None, True, 1):
            with self.subTest(version=version):
                response = io.BytesIO(json.dumps(dict(capabilities, package_startup=version)).encode())
                self.patch(launcher, "build_opener", return_value=SimpleNamespace(open=lambda *_args, **_kwargs: response))
                if type(version) is int:
                    self.assertEqual(launcher._probe(self.ready["url"], "DEFAULT.zip")["package_startup"], 1)
                else:
                    with self.assertRaises(launcher.IncompatibleStudio):
                        launcher._probe(self.ready["url"], "DEFAULT.zip")

    def test_bridge_forwards_target_including_theme_retry(self):
        from urllib.error import HTTPError
        request = {"name": "Package", "layout": {"vehicle": VEHICLE}, "ui_theme": {}}
        ready = dict(self.ready, host_layout_handoff=True, reused=False)
        self.patch(bridge, "validate_request", side_effect=lambda value: value)
        ensure = self.patch(launcher, "ensure_ready", return_value=ready)
        self.patch(bridge, "_check_package_target")
        self.patch(bridge, "_native_admission", return_value=nullcontext())
        self.patch(bridge, "_publish_theme", side_effect=[HTTPError("old", 404, "rotated", {}, None), None])
        self.patch(bridge, "stage_handoff", return_value="b" * 32)
        bridge.launch_from_host(ROOT, request)
        self.assertEqual(ensure.call_count, 2)
        for call in ensure.call_args_list:
            self.assertEqual(call.kwargs["initial_vehicle"], VEHICLE)

    def test_pre_scene_permission_requires_owned_native_session(self):
        request = {"layout": {"vehicle": VEHICLE}}
        ready = dict(self.ready, host_layout_handoff=True, vehicle=VEHICLE, chrome_exposed=False)
        owner = object()
        for chrome, owns, allowed in ((False, True, True), (False, False, False), (True, True, False)):
            self.patch(launcher, "_window_module", return_value=SimpleNamespace(
                use_chrome=lambda _: chrome, owns_native_url=lambda *_: owns))
            self.assertIs(bridge._check_package_target(ROOT, ready, request, owner), allowed)

    def test_native_lease_does_not_authorize_chrome_exposed_or_unknown_backend(self):
        request = {"layout": {"vehicle": VEHICLE}}
        owner = object()
        self.patch(launcher, "_window_module", return_value=SimpleNamespace(
            use_chrome=lambda _: False, owns_native_url=lambda *_: True))
        for shared in (True, None):
            ready = dict(self.ready, host_layout_handoff=True, chrome_exposed=shared)
            self.assertFalse(bridge._check_package_target(ROOT, ready, request, owner))
            ready["vehicle"] = {"car_id": 99, "model_code": "OTHER"}
            with self.assertRaisesRegex(ValueError, "another open page"):
                bridge._check_package_target(ROOT, ready, request, owner)

    def test_chrome_open_marks_shared_under_admission_before_process_launch(self):
        calls = []
        from contextlib import contextmanager
        @contextmanager
        def admission(url):
            calls.append("admit")
            try:
                yield
            finally:
                calls.append("release")
        self.patch(launcher, "window_preflight", return_value=self.config)
        self.patch(launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: True, native_admission=admission))
        self.patch(launcher, "_mark_chrome_exposed", side_effect=lambda _: calls.append("mark"), create=True)
        self.patch(launcher, "_open_chrome_window", side_effect=lambda _: calls.append("open") or True)
        with patch.dict(launcher.os.environ, {"KFPS_LIVERY_NO_OPEN": "0"}):
            self.assertTrue(launcher.open_studio_window(self.ready["url"]))
        self.assertEqual(calls, ["admit", "mark", "open", "release"])

    def test_chrome_admission_failure_never_marks_or_opens(self):
        self.patch(launcher, "window_preflight", return_value=self.config)
        self.patch(launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: True,
            native_admission=Mock(side_effect=RuntimeError("Native owner is active"))))
        mark = self.patch(launcher, "_mark_chrome_exposed", create=True)
        opened = self.patch(launcher, "_open_chrome_window")
        with patch.dict(launcher.os.environ, {"KFPS_LIVERY_NO_OPEN": "0"}), self.assertRaisesRegex(RuntimeError, "Native owner"):
            launcher.open_studio_window(self.ready["url"])
        mark.assert_not_called()
        opened.assert_not_called()

    def test_chrome_marker_requires_positive_receipt_before_opening(self):
        url = self.ready["url"]
        for receipt, succeeds in (({"chrome_exposed": True}, True), ({"chrome_exposed": False}, False),
                                  ({"chrome_exposed": 1}, False)):
            with self.subTest(receipt=receipt):
                opener = Mock()
                opener.open.return_value = io.BytesIO(json.dumps(receipt).encode())
                self.patch(launcher, "build_opener", return_value=opener)
                if succeeds:
                    launcher._mark_chrome_exposed(url)
                else:
                    with self.assertRaisesRegex(ValueError, "No Chrome window"):
                        launcher._mark_chrome_exposed(url)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, url + "api/chrome-session")
                self.assertEqual(request.get_method(), "POST")
                self.assertEqual(request.data, b"")

    def test_static_allowlist_includes_startup_and_parent_panel_modules(self):
        from kfps_livery_lab import server
        for name in ("studio-bootstrap.mjs", "workspace-panels.mjs"):
            self.assertIn(name, server.WEB_FILES + server.OPTIONAL_WEB_FILES)


class ChromeSessionBoundaryTests(unittest.TestCase):
    def setUp(self):
        from kfps_livery_lab import server
        self.module = server
        self.server = server.LiveryLabServer.__new__(server.LiveryLabServer)
        self.server.state_lock = threading.RLock()
        self.server.token = "a" * 43
        self.server.chrome_exposed = False
        self.server.reply = Mock(side_effect=lambda _request, status, value: (status, value))
        self.server.httpd = SimpleNamespace(server_port=1234)
        self.server.session_workspace = Path("unused-session")
        self.server.source_editor = Mock()

    def request(self, *, method="POST", token=None, suffix="", length="0"):
        token = self.server.token if token is None else token
        headers = Message()
        headers["Content-Length"] = length
        request = SimpleNamespace(command=method, headers=headers)
        target = urlsplit(f"/{token}/api/chrome-session" + suffix)
        return self.server._chrome_session_request(request, target, token)

    def test_marker_is_monotonic_and_survives_real_token_activation(self):
        self.assertEqual(self.request(), (200, {"chrome_exposed": True}))
        previous = self.server.token
        with patch.object(self.module, "atomic_json"):
            self.server._activate_car({"editor_config": {"vehicle": VEHICLE}}, Path("unused-car"), {}, previous)
        self.assertNotEqual(self.server.token, previous)
        self.assertTrue(self.server.chrome_exposed)
        self.assertEqual(self.request(token=previous)[0], 404)
        self.assertEqual(self.request(), (200, {"chrome_exposed": True}))

    def test_invalid_marker_requests_do_not_change_session(self):
        for options, status in (({"method": "GET"}, 405), ({"length": "1"}, 400),
                                ({"suffix": "?clear=1"}, 400), ({"token": "b" * 43}, 404)):
            with self.subTest(options=options):
                self.assertEqual(self.request(**options)[0], status)
                self.assertFalse(self.server.chrome_exposed)


if __name__ == "__main__":
    unittest.main()
