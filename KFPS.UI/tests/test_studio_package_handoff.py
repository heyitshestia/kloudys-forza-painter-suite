"""Read-only package artwork transfer, isolated from real saves and UI launches."""
import copy
from contextlib import nullcontext
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab import host_bridge as bridge
from kfps_livery_lab.studio_window import validate_window_url
from tools.cgroup import forza_source_decoder as decoder
from tools.livery.fh6_save_installer import build_destination_header
from tools.livery.package import _decode_livery_contract, validate_full_livery_package
from test_full_livery_package import build_package, json_bytes, sha
from test_livery_group_exports import saved_payload, shape
from PIL import Image


def make_package(path, *, protected=False, raster=False, version=2):
    first = shape(10, ("outer", "inner"))
    if raster:
        first["type"] = 0x108009
    payload = saved_payload({"Front": [first, shape(20, ("outer", "inner")),
                                        shape(30, ("outer",)), shape(40)], "Spoiler": [shape(-13)]})
    # The fixture builder includes a final inter-section transform; real v2
    # envelopes stop after the last section's terminal state.
    _, _, meta = decoder.extract_livery_payload(payload)
    end = meta["body_end"]
    payload = bytearray(payload[:end - 17] + payload[end:])
    struct.pack_into("<I", payload, 47, end - 17 - 51)
    struct.pack_into("<I", payload, 4, version)
    if protected:
        struct.pack_into("<I", payload, 8, 1)
    payload = bytes(payload)
    build_package(path, payload_override=payload)
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    layers, report, counts, _ = _decode_livery_contract(payload)
    entries["livery/layers.json"] = json_bytes(layers)
    entries["source/fh6/header"] = build_destination_header(title="Nested artwork", car_id=3307,
        creator_tag=b"TEST0001", creator_name="Fixture", placement_count=sum(counts), now=datetime.now(timezone.utc))
    projection = json.loads(entries["projection/index.json"])
    projection["rendered_sections"] = []
    for name, count in zip(decoder.LIVERY_SECTION_NAMES, counts):
        if not count:
            continue
        image = io.BytesIO()
        Image.new("RGBA", (2048, 1024)).save(image, format="PNG")
        member = f"projection/rendered/{name}.png"
        entries[member] = image.getvalue()
        projection["rendered_sections"].append({"section": name, "path": member, "width": 2048, "height": 1024})
    entries["projection/index.json"] = json_bytes(projection)
    manifest = json.loads(entries["manifest.json"])
    manifest["livery"]["decoded_layer_count"] = report["decoded_layers"]
    manifest["files"] = [{"path": name, "role": "fixture", "size": len(data), "sha256": sha(data)}
                         for name, data in sorted(entries.items()) if name != "manifest.json"]
    entries["manifest.json"] = json_bytes(manifest)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return payload


class PackageHandoffTests(unittest.TestCase):
    def setUp(self):
        admission = patch.object(bridge, "_native_admission", return_value=nullcontext())
        admission.start()
        self.addCleanup(admission.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target, value in (("LAB_ROOT", self.root), ("CONTROL", self.root / "runs/control"),
                              ("WORKSPACE", self.root / "runs/workspace")):
            isolated = patch.object(bridge.launcher, target, value)
            isolated.start()
            self.addCleanup(isolated.stop)
        self.package = self.root / "fixture.kfpslivery"
        self.payload = make_package(self.package)
        for target, value in (("LAB_ROOT", self.root), ("HANDOFF_ROOT", self.root / "runs/inbox")):
            mocked = patch.object(bridge, target, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        host_mode = patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: False))
        host_mode.start()
        self.addCleanup(host_mode.stop)

    def test_real_decoder_preserves_all_groups_coordinates_and_source(self):
        validate_full_livery_package(self.package)
        before = self.package.read_bytes()
        request = bridge.request_for_package(self.package)
        self.assertEqual(set(request), {"name", "layout"})
        layout = request["layout"]
        self.assertEqual(layout["vehicle"], {"car_id": 3307, "model_code": "TEST_CAR"})
        grouped, report = decoder.clivery_to_layers(self.payload, preserve_groups=True)
        self.assertEqual(report["warnings"], [])
        for source, placement in zip(layout["vinyls"], layout["placements"]):
            expected, warnings = decoder.layers_to_kfps_json_layers(
                [item for item in grouped if item["section"] == placement["section"]], game="fh6")
            self.assertEqual(warnings, [])
            self.assertEqual(source["shapes"], expected)
        self.assertEqual([len(s.get("editor_group_path", [])) for s in layout["vinyls"][0]["shapes"]], [2, 2, 1, 0])
        self.assertEqual(before, self.package.read_bytes())
        self.assertNotIn(str(self.package), json.dumps(request))

    def test_staged_snapshot_is_detached_repeatable_and_bounded(self):
        request = bridge.request_for_package(self.package)
        expected = copy.deepcopy(request)
        identifier = bridge.stage_handoff(request)
        request["layout"]["vinyls"][0]["shapes"].clear()
        self.package.unlink()
        for _ in range(2):
            self.assertEqual(bridge.read_layout_handoff(identifier, resolve_resource=lambda _: True), expected)
        with patch.object(bridge, "MAX_HANDOFFS", 1), self.assertRaises(ValueError):
            bridge.stage_handoff(expected)

    def test_invalid_protected_missing_and_oversized_packages_fail_closed(self):
        with self.assertRaises(ValueError):
            bridge.request_for_package(self.root / "missing.kfpslivery")
        protected = self.root / "protected.kfpslivery"
        make_package(protected, protected=True)
        with self.assertRaises(ValueError):
            bridge.request_for_package(protected)
        self.package.write_bytes(b"not a package")
        with self.assertRaises(ValueError):
            bridge.request_for_package(self.package)
        from kfps_livery_lab import package_handoff
        with patch.object(package_handoff, "MAX_PACKAGE_BYTES", 1), self.assertRaises(ValueError):
            bridge.request_for_package(self.package)

    def test_startup_permission_roundtrip_is_optional_and_session_bound(self):
        request = bridge.request_for_package(self.package)
        url = "http://127.0.0.1:1234/" + "a" * 43 + "/"
        identifier = bridge.stage_handoff(request, startup_session=url)
        self.assertEqual(bridge.read_layout_handoff(identifier), dict(request, startup_session=url))
        self.assertNotIn("startup_session", request)
        with self.assertRaises(ValueError):
            bridge.stage_handoff(request, startup_session="https://example.com/")

    def test_layout_validator_retains_masks_metadata_and_rejects_lossy_inputs(self):
        value = bridge.request_for_package(self.package)
        masked = value["layout"]["vinyls"][0]["shapes"][0]
        masked["mask"] = True
        masked["data"][6] = 1
        self.assertEqual(bridge.validate_request(value), value)
        for modify in (lambda v: v.update(vinyl={"shapes": [masked]}),
                       lambda v: v["layout"]["vehicle"].update(car_id=True),
                       lambda v: v["layout"].update(vehicle_parts={"Body": 123}),
                       lambda v: v["layout"]["placements"][0].update(x=1),
                       lambda v: v["layout"]["vinyls"][0]["shapes"][0].update(is_raster_logo=True),
                       lambda v: v["layout"]["vinyls"][0].update(shapes=[masked] * 3001)):
            changed = copy.deepcopy(value)
            modify(changed)
            with self.subTest(changed=str(changed)[:120]), self.assertRaises(ValueError):
                bridge.validate_request(changed)

    def test_layout_and_vinyl_read_routes_cannot_cross_and_expiry_is_explicit(self):
        request = bridge.request_for_package(self.package)
        identifier = bridge.stage_handoff(request)
        with self.assertRaises(bridge.HandoffError):
            bridge.read_handoff(identifier)
        with self.assertRaises(bridge.HandoffError):
            bridge.read_layout_handoff("../" + identifier)
        with patch.object(bridge.time, "time", return_value=bridge.time.time() + bridge.HANDOFF_LIFETIME + 10):
            with self.assertRaises(bridge.HandoffError) as caught:
                bridge.read_layout_handoff(identifier)
            self.assertEqual(caught.exception.status, 410)

    def test_package_launch_requires_capability_and_native_url_is_allowlisted(self):
        request = bridge.request_for_package(self.package)
        ready = {"url": "http://127.0.0.1:1234/" + "a" * 43 + "/", "host_layout_handoff": True,
                 "reused": False, "chrome_exposed": False}
        with patch.object(bridge.launcher, "ensure_ready", return_value=ready):
            result = bridge.launch_from_host(ROOT, request)
        self.assertTrue(result["transferred"])
        self.assertIn("#layout=", result["url"])
        self.assertEqual(validate_window_url(result["url"]), result["url"])
        with patch.object(bridge.launcher, "ensure_ready", return_value={"url": ready["url"]}):
            with self.assertRaisesRegex(ValueError, "package"):
                bridge.launch_from_host(ROOT, request)
        with self.assertRaises(ValueError):
            validate_window_url(ready["url"] + "#layout=../../private")

    def test_ready_record_exposes_package_capability_for_new_and_reused_servers(self):
        launcher = bridge.launcher
        url = "http://127.0.0.1:1234/" + "a" * 43 + "/"
        process = SimpleNamespace(pid=123, create_time=lambda: 1,
            net_connections=lambda **_: [SimpleNamespace(status=launcher.psutil.CONN_LISTEN,
                laddr=SimpleNamespace(ip="127.0.0.1", port=1234))])
        with patch.object(launcher, "_inside", side_effect=lambda path, root: Path(path)), \
                patch.object(launcher, "_read_json", return_value={"status": "running", "pid": 123, "url": url}), \
                patch.object(launcher, "inspect_process", return_value=process):
            for capability in (True, False, None):
                for managed in (True, False):
                    with self.subTest(capability=capability, managed=managed), \
                            patch.object(launcher, "_probe", return_value={"host_layout_handoff": capability,
                                "vehicle": {"car_id": 3307, "model_code": "TEST_CAR", "archive_name": "test.zip"}}):
                        value = launcher._ready_record(self.root / "server-info.json", {"archive": "test.zip"}, managed=managed)
                        self.assertIs(value["host_layout_handoff"], capability is True)
                        self.assertEqual(value["vehicle"], {"car_id": 3307, "model_code": "TEST_CAR"})

    def test_chrome_package_rejects_other_or_unknown_car_before_any_mutation(self):
        request = bridge.request_for_package(self.package)
        request["ui_theme"] = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        for vehicle in (None, {}, {"car_id": 99, "model_code": "TEST_CAR"},
                        {"car_id": 3307, "model_code": "OTHER"}, {"car_id": "3307", "model_code": "TEST_CAR"}):
            for reused in (True, False):
                ready = {"url": "unused", "host_layout_handoff": True, "vehicle": vehicle, "reused": reused}
                with self.subTest(vehicle=vehicle, reused=reused), \
                        patch.object(bridge.launcher, "ensure_ready", return_value=ready), \
                        patch.object(bridge.launcher, "window_preflight"), \
                        patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: True)), \
                        patch.object(bridge.launcher, "open_studio_window") as opened, \
                        patch.object(bridge, "_publish_theme") as published, \
                        patch.object(bridge, "stage_handoff") as staged:
                    with self.assertRaisesRegex(ValueError, "In Chrome, save your work and choose this package's car"):
                        bridge.launch_from_host(ROOT, request, open_window=True)
                    published.assert_not_called()
                    staged.assert_not_called()
                    opened.assert_not_called()

    def test_same_car_chrome_and_fresh_backend_native_keep_existing_route(self):
        request = bridge.request_for_package(self.package)
        for chrome, vehicle in ((True, request["layout"]["vehicle"]), (False, {"car_id": 99, "model_code": "OTHER"})):
            ready = {"url": "http://127.0.0.1:1234/" + "a" * 43 + "/", "host_layout_handoff": True,
                     "vehicle": vehicle, "reused": False, "chrome_exposed": False}
            with self.subTest(chrome=chrome), patch.object(bridge.launcher, "ensure_ready", return_value=ready), \
                    patch.object(bridge.launcher, "window_preflight"), \
                    patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: chrome)), \
                    patch.object(bridge.launcher, "open_studio_window", return_value=True) as opened:
                result = bridge.launch_from_host(ROOT, request, open_window=True)
                self.assertTrue(result["transferred"])
                self.assertTrue(result["opened"])
                opened.assert_called_once_with(result["url"], cancelled=None)

    def test_native_shared_or_unknown_backend_blocks_other_car_before_mutation(self):
        request = bridge.request_for_package(self.package)
        request["ui_theme"] = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        for reused in (True, None, 0):
            for vehicle in (None, {}, {"car_id": 99, "model_code": "OTHER"}):
                ready = {"url": "unused", "host_layout_handoff": True, "vehicle": vehicle, "reused": reused}
                with self.subTest(reused=reused, vehicle=vehicle), \
                        patch.object(bridge.launcher, "ensure_ready", return_value=ready), \
                        patch.object(bridge.launcher, "window_preflight"), \
                        patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: False)), \
                        patch.object(bridge.launcher, "open_studio_window") as opened, \
                        patch.object(bridge, "_publish_theme") as published, \
                        patch.object(bridge, "stage_handoff") as staged:
                    with self.assertRaisesRegex(ValueError, "another open page"):
                        bridge.launch_from_host(ROOT, request, open_window=True)
                    published.assert_not_called()
                    staged.assert_not_called()
                    opened.assert_not_called()

    def test_shared_native_matching_car_still_transfers_without_switch(self):
        request = bridge.request_for_package(self.package)
        ready = {"url": "http://127.0.0.1:1234/" + "a" * 43 + "/", "host_layout_handoff": True,
                 "vehicle": request["layout"]["vehicle"], "reused": True}
        with patch.object(bridge.launcher, "ensure_ready", return_value=ready), \
                patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: False)):
            self.assertTrue(bridge.launch_from_host(ROOT, request)["transferred"])

    def test_native_rechecks_shared_car_after_theme_readiness_refresh(self):
        from urllib.error import HTTPError
        request = bridge.request_for_package(self.package)
        request["ui_theme"] = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        ready = {"url": "old", "host_layout_handoff": True, "vehicle": request["layout"]["vehicle"], "reused": False}
        changed = dict(ready, url="new", vehicle={"car_id": 99, "model_code": "OTHER"}, reused=True)
        with patch.object(bridge.launcher, "ensure_ready", side_effect=[ready, changed]), \
                patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: False)), \
                patch.object(bridge, "_publish_theme", side_effect=HTTPError("old", 404, "rotated", {}, None)), \
                patch.object(bridge, "stage_handoff") as staged:
            with self.assertRaisesRegex(ValueError, "another open page"):
                bridge.launch_from_host(ROOT, request)
            staged.assert_not_called()

    def test_chrome_rechecks_car_after_readiness_refresh_before_retrying_theme(self):
        from urllib.error import HTTPError
        request = bridge.request_for_package(self.package)
        request["ui_theme"] = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        ready = {"url": "old", "host_layout_handoff": True, "vehicle": request["layout"]["vehicle"]}
        changed = dict(ready, url="new", vehicle={"car_id": 99, "model_code": "OTHER"})
        with patch.object(bridge.launcher, "ensure_ready", side_effect=[ready, changed]), \
                patch.object(bridge.launcher, "window_preflight"), \
                patch.object(bridge.launcher, "_window_module", return_value=SimpleNamespace(use_chrome=lambda _: True)), \
                patch.object(bridge.launcher, "open_studio_window") as opened, \
                patch.object(bridge, "_publish_theme", side_effect=HTTPError("old", 404, "rotated", {}, None)) as published, \
                patch.object(bridge, "stage_handoff") as staged:
            with self.assertRaisesRegex(ValueError, "Automatic car switching could interrupt another Studio window"):
                bridge.launch_from_host(ROOT, request, open_window=True)
            published.assert_called_once()
            staged.assert_not_called()
            opened.assert_not_called()

    def test_stale_backend_never_stages_or_opens_window(self):
        request = bridge.request_for_package(self.package)
        request["ui_theme"] = {"name": "Test", "variables": {"--accent": "#ee4477"}, "fontFamily": "Arial"}
        with patch.object(bridge.launcher, "ensure_ready", return_value={"url": "old", "host_vinyl_handoff": True}), \
                patch.object(bridge.launcher, "window_preflight"), \
                patch.object(bridge.launcher, "open_studio_window") as opened, \
                patch.object(bridge, "_publish_theme") as published, \
                patch.object(bridge, "stage_handoff") as staged:
            with self.assertRaisesRegex(ValueError, "restart Studio"):
                bridge.launch_from_host(ROOT, request, open_window=True)
            staged.assert_not_called()
            opened.assert_not_called()
            published.assert_not_called()

    def test_chrome_and_native_launch_accept_only_opaque_package_fragment(self):
        launcher = bridge.launcher
        base = "http://127.0.0.1:1234/" + "a" * 43 + "/"
        with patch.dict(os.environ, {"KFPS_LIVERY_NO_OPEN": "1"}):
            self.assertFalse(launcher.open_studio_window(base + "#layout=" + "b" * 32))
            for fragment in ("layout=private.kfpslivery", "layout=" + "b" * 32 + "&path=save", "file=C:/save"):
                with self.assertRaises(ValueError):
                    launcher.open_studio_window(base + "#" + fragment)

    def test_layout_size_and_missing_shape_resource_are_rejected(self):
        request = bridge.request_for_package(self.package)
        from kfps_livery_lab import package_handoff
        with patch.object(package_handoff, "MAX_LAYOUT_BYTES", 1024), self.assertRaises(ValueError):
            bridge.validate_request(request)
        identifier = bridge.stage_handoff(request)
        with self.assertRaises(bridge.HandoffError) as caught:
            bridge.read_layout_handoff(identifier, resolve_resource=lambda _: None)
        self.assertEqual(caught.exception.status, 422)

    def test_linked_package_is_rejected(self):
        link = self.root / "linked.kfpslivery"
        os.link(self.package, link)
        with self.assertRaises(ValueError):
            bridge.request_for_package(link)

    def test_header_car_mismatch_and_missing_header_are_explicit(self):
        with zipfile.ZipFile(self.package) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        for header in (None, build_destination_header(title="Wrong car", car_id=99, creator_tag=b"TEST0001",
                         creator_name="Fixture", placement_count=5, now=datetime.now(timezone.utc))):
            changed = dict(entries)
            if header is None:
                changed.pop("source/fh6/header")
            else:
                changed["source/fh6/header"] = header
            manifest = json.loads(changed["manifest.json"])
            manifest["files"] = [{"path": name, "role": "fixture", "size": len(data), "sha256": sha(data)}
                                 for name, data in sorted(changed.items()) if name != "manifest.json"]
            changed["manifest.json"] = json_bytes(manifest)
            with zipfile.ZipFile(self.package, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in changed.items():
                    archive.writestr(name, data)
            with self.subTest(missing=header is None), self.assertRaises(ValueError):
                bridge.request_for_package(self.package)

    def test_valid_but_noneditable_raster_and_unsupported_envelope_fail_explicitly(self):
        for options, reason in (({"raster": True}, "raster"), ({"version": 1}, "version-2")):
            with self.subTest(options=options):
                make_package(self.package, **options)
                validate_full_livery_package(self.package)
                with self.assertRaisesRegex(ValueError, reason):
                    bridge.request_for_package(self.package)

    def test_nested_source_compression_is_bounded_before_package_validation(self):
        from kfps_livery_lab.save_codec import MAX_PAYLOAD
        for raw in (struct.pack("<II", 1, MAX_PAYLOAD + 1) + b"x",
                    struct.pack("<II", len(zlib.compress(b"x" * 4096)), 1) + zlib.compress(b"x" * 4096)):
            with zipfile.ZipFile(self.package, "w") as archive:
                archive.writestr("source/fh6/C_livery", raw)
            with patch("tools.livery.package.validate_full_livery_package", side_effect=AssertionError("Unbounded decoder reached")) as validate:
                with self.assertRaises(ValueError):
                    bridge.request_for_package(self.package)
                validate.assert_not_called()


class PackageHandoffRouteTests(unittest.TestCase):
    def setUp(self):
        import test_studio_preview_quality_routes as routes
        self.fixture = routes.PreviewQualityRouteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.package = self.root / "fixture.kfpslivery"
        make_package(self.package)
        for target, value in (("LAB_ROOT", self.root), ("HANDOFF_ROOT", self.root / "runs/inbox")):
            mocked = patch.object(bridge, target, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.value = bridge.request_for_package(self.package)
        self.identifier = bridge.stage_handoff(self.value)

    def test_actual_http_boundary_and_rotated_token_keep_same_artwork(self):
        route = "api/host-layout/" + self.identifier
        request = self.fixture.request
        status, headers, body = request("GET", route)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(body), self.value)
        config = json.loads(request("GET", "api/editor-config")[2])
        self.assertTrue(config["host_layout_handoff"])
        old_prefix = self.fixture.prefix
        self.fixture.server.token = "b" * 43
        self.fixture.prefix = "/" + self.fixture.server.token + "/"
        self.assertEqual(request("GET", old_prefix + route, raw_path=True)[0], 404)
        self.assertEqual(json.loads(request("GET", route)[2]), self.value)
        for method, address, headers, expected in (
                ("POST", route, {}, 405), ("GET", route + "?path=C:/save", {}, 400),
                ("GET", route, {"Origin": "http://evil.test"}, 403),
                ("GET", "api/host-layout/../private", {}, 400),
                ("GET", "api/host-layout/" + "f" * 32, {}, 404)):
            with self.subTest(method=method, address=address):
                self.assertEqual(request(method, address, headers=headers)[0], expected)


if __name__ == "__main__":
    unittest.main()
