from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiClient, CommunityApiError
from kfps_ui.community_credentials import CommunityCredentialStore
from kfps_ui.community_service import CommunityService, configured_community_api_url
from kfps_ui.community_validation import detect_payload_schema, inspect_upload, validate_download


APP = QCoreApplication.instance() or QCoreApplication([])


def wait_for(predicate, timeout=12.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    APP.processEvents()
    return bool(predicate())


def write_design(path: Path, accent=100):
    payload = {
        "metadata": {"display_name": path.stem, "private_path": "must-not-survive", "target_game": "fh6"},
        "shapes": [
            {
                "type": 16,
                "color": [255, (accent >> 8) & 255, accent & 255, 255],
                "data": [512, 512, 300, 120, (accent % 360_000) / 1000],
            },
            {"type": 16, "color": [20, 220, 180, 255], "data": [420, 440, 80, 160, 340]},
            {"type": 16, "color": [255, 255, 255, 255], "data": [600, 600, 120, 60, 30]},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class DummyDesktop:
    def __init__(self, selected: Path):
        self.selected = str(selected)
        self.opened = []
        self.choose_calls = 0

    def chooseJson(self):
        self.choose_calls += 1
        return self.selected

    def openFolder(self, value):
        self.opened.append(str(value))


class DummyLog:
    def __init__(self):
        self.messages = []

    def append(self, message, level="info"):
        self.messages.append((str(message), str(level)))


class CommunityBoundaryTests(unittest.TestCase):
    def test_service_urls_are_pinned_and_require_secure_remote_transport(self):
        client = CommunityApiClient("http://127.0.0.1:8790/v1")
        self.assertEqual(client.url("health"), "http://127.0.0.1:8790/v1/health")
        self.assertEqual(client.url("/v1/artworks/a/preview"), "http://127.0.0.1:8790/v1/artworks/a/preview")
        with self.assertRaises(CommunityApiError):
            client.url("https://example.com/v1/artworks/a/preview")
        with self.assertRaises(CommunityApiError):
            client.url("http://user:password@127.0.0.1:8790/v1/artworks/a/preview")
        with self.assertRaises(CommunityApiError):
            client.url("/v1/artworks/a/preview#unexpected")
        with self.assertRaises(CommunityApiError):
            CommunityApiClient("http://example.com/v1")

        with self.assertRaises(CommunityApiError) as error:
            client.binary("artworks/a/download", authenticated=True)
        self.assertEqual(error.exception.code, "authentication_required")

    def test_packaged_endpoint_is_isolated_and_environment_can_override_it(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            app_root = Path(folder)
            endpoint = app_root / "data" / "community_api_url.txt"
            endpoint.parent.mkdir(parents=True)
            endpoint.write_text("https://community.example.workers.dev/v1\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("KFPS_COMMUNITY_API_URL", None)
                self.assertEqual(configured_community_api_url(app_root), "https://community.example.workers.dev/v1")
            with patch.dict(os.environ, {"KFPS_COMMUNITY_API_URL": "http://127.0.0.1:8790/v1/"}):
                self.assertEqual(configured_community_api_url(app_root), "http://127.0.0.1:8790/v1")

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_community_session_uses_dpapi_and_stays_separate(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            store = CommunityCredentialStore(Path(folder))
            token = "kfc_" + "a" * 43
            self.assertTrue(store.save_token(token))
            self.assertEqual(store.load_token(), token)
            self.assertIn("community", str(store.session_file))
            self.assertNotIn("supporter", str(store.session_file).lower())
            self.assertNotEqual(store.session_file.read_bytes(), token.encode("utf-8"))
            store.clear_token()
            self.assertFalse(store.session_file.exists())

    def test_community_sessions_are_isolated_by_service_endpoint(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            local = CommunityCredentialStore(Path(folder), "http://127.0.0.1:8790/v1")
            production = CommunityCredentialStore(Path(folder), "https://community.example.workers.dev/v1")
            self.assertNotEqual(local.session_file, production.session_file)
            self.assertEqual(local.installation_file, production.installation_file)
            self.assertEqual(local.session_file.parent.name, "sessions")

    def test_upload_validation_renders_and_download_validation_rejects_tampering(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "validation.json"
            write_design(source)
            inspected = inspect_upload(source, folder)
            self.assertEqual(inspected.shape_count, 3)
            self.assertEqual(inspected.schema_id, "kfps-primitives")
            self.assertEqual(inspected.schema_label, "KFPS primitive geometry")
            self.assertTrue(inspected.schema_known)
            self.assertEqual(inspected.detected_games, ("FH6",))
            self.assertEqual(inspected.schema_warning, "")
            self.assertTrue(inspected.preview_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
            preview_size = (
                int.from_bytes(inspected.preview_bytes[16:20], "big"),
                int.from_bytes(inspected.preview_bytes[20:24], "big"),
            )
            thumbnail_size = (
                int.from_bytes(inspected.thumbnail_bytes[16:20], "big"),
                int.from_bytes(inspected.thumbnail_bytes[20:24], "big"),
            )
            self.assertGreaterEqual(max(preview_size), 900)
            self.assertLessEqual(max(preview_size), 1400)
            self.assertGreaterEqual(min(thumbnail_size), 64)
            self.assertLessEqual(max(thumbnail_size), 480)
            self.assertLess(max(thumbnail_size), max(preview_size))
            canonical = json.dumps({
                "format": "kfps.community.v1",
                "metadata": {"shape_count": 1},
                "shapes": [{"type": 16, "color": [1, 2, 3, 255], "data": [1, 2, 3, 4, 5]}],
            }, separators=(",", ":")).encode("utf-8")
            import hashlib
            digest = hashlib.sha256(canonical).hexdigest()
            self.assertEqual(validate_download(canonical, digest)["format"], "kfps.community.v1")
            with self.assertRaises(ValueError):
                validate_download(canonical + b" ", digest)

    def test_upload_thumbnails_pad_extreme_aspect_ratios_to_a_transparent_square(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            for name, width, height in (("wide", 10_000, 500), ("tall", 500, 10_000)):
                with self.subTest(name=name):
                    source = folder / f"{name}.json"
                    source.write_text(json.dumps({
                        "metadata": {"target_game": "fh6"},
                        "shapes": [
                            {"type": 1, "color": [0, 0, 0, 0], "data": [0, 0, 1, 1, 0]},
                            {"type": 1, "color": [255, 30, 100, 255], "data": [0, 0, width, height, 0]},
                        ],
                    }), encoding="utf-8")
                    inspected = inspect_upload(source, folder)
                    preview_size = (
                        int.from_bytes(inspected.preview_bytes[16:20], "big"),
                        int.from_bytes(inspected.preview_bytes[20:24], "big"),
                    )
                    thumbnail = QImage.fromData(inspected.thumbnail_bytes, "PNG")
                    self.assertGreaterEqual(min(preview_size), 64)
                    self.assertEqual((thumbnail.width(), thumbnail.height()), (480, 480))
                    self.assertEqual(thumbnail.pixelColor(0, 0).alpha(), 0)
                    self.assertGreater(thumbnail.pixelColor(240, 240).alpha(), 0)

    def test_known_community_json_schemas_and_game_origins_are_detected(self):
        primitive = {"type": 16, "color": [1, 2, 3, 255], "data": [1, 2, 3, 4, 5]}
        type_code = {
            "type": 1048678,
            "type_word": 102,
            "color": [1, 2, 3, 255],
            "data": [1, 2, 3, 4, 5, 0, 0],
            "source_format": "fh6_typecode",
        }
        cases = [
            ({"format": "kfps.community.v1", "metadata": {"detected_games": ["FH5"]}, "shapes": [primitive]}, "kfps-community", ("FH5",)),
            ({"format": "fh6_typecode_json_export_v1", "source": {"game": "fm8"}, "shapes": [type_code]}, "forza-typecode-export", ("FM8",)),
            ({"format": "kfps_forza_save_library_json_v1", "target_game": "fh5", "shapes": [type_code]}, "forza-save-library", ("FH5",)),
            ({"format": "kfps_forza_file_export_json_v1", "target_game": "fm8", "shapes": [type_code]}, "forza-file-export", ("FM8",)),
            ({"format": "kfps_cgroup_flat_json_v1", "shapes": [type_code]}, "kfps-cgroup-flat", ()),
            ({"format": "kfps.fd6.converted.v1", "shapes": [type_code]}, "fd6-converted", ("FH6",)),
            ({"metadata": {"target_game": "fh6"}, "shapes": [primitive]}, "kfps-primitives", ("FH6",)),
            ({"shapes": [type_code]}, "fh6-typecode", ("FH6",)),
        ]
        for payload, expected_schema, expected_games in cases:
            with self.subTest(expected_schema=expected_schema, expected_games=expected_games):
                detected = detect_payload_schema(payload)
                self.assertTrue(detected.known)
                self.assertEqual(detected.schema_id, expected_schema)
                self.assertEqual(detected.games, expected_games)

    def test_unknown_explicit_schema_is_warned_but_remains_uploadable(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "unknown-project.json"
            write_design(source)
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload["format"] = "another-project.v9"
            source.write_text(json.dumps(payload), encoding="utf-8")
            inspected = inspect_upload(source, folder)
            self.assertFalse(inspected.schema_known)
            self.assertEqual(inspected.schema_id, "unrecognized")
            self.assertIn("another-project.v9", inspected.schema_label)
            self.assertIn("compatibility may vary", inspected.schema_warning)
            self.assertTrue(inspected.preview_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_fd6_upload_is_converted_in_runtime_without_changing_the_original(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "FD6 Community Sample.json"
            source.write_text(json.dumps({
                "format": "fd6.shapes",
                "version": 1,
                "image_size": [200, 100],
                "shapes": [
                    {"type": "rotated_ellipse", "x": 120, "y": 70, "rx": 63, "ry": 31.5, "angle": 90, "color": [1, 2, 3, 255]},
                    {"type": "triangle", "x1": 0, "y1": 0, "x2": 10, "y2": 0, "x3": 0, "y3": 10, "color": [255, 255, 255, 255]},
                ],
            }), encoding="utf-8")
            original = source.read_bytes()
            inspected = inspect_upload(source, folder)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(inspected.payload["format"], "kfps.fd6.converted.v1")
            self.assertEqual(inspected.shape_count, 1)
            self.assertEqual(inspected.schema_id, "fd6-converted")
            self.assertTrue(inspected.schema_known)
            self.assertEqual(inspected.detected_games, ("FH6",))
            self.assertIn("original file was not changed", inspected.normalization_note)
            normalized = list((folder / "community" / "upload-normalized").glob("*.fd6-converted.json"))
            self.assertEqual(len(normalized), 1)
            self.assertEqual(json.loads(normalized[0].read_text(encoding="utf-8"))["format"], "kfps.fd6.converted.v1")
            self.assertTrue(inspected.preview_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_github_device_flow_uses_public_identity_and_can_be_cancelled(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            app_root = folder / "app"
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CommunityService(paths, DummyDesktop(folder / "unused.json"), DummyLog(), demo=True)
            device_events = []
            service._githubDeviceReady.connect(device_events.append)
            calls = []

            def github_post(url, values, maximum=64 * 1024):
                calls.append((url, dict(values), maximum))
                if url.endswith("/device/code"):
                    return {
                        "device_code": "d" * 40,
                        "user_code": "ABCD-EFGH",
                        "verification_uri": "https://github.com/login/device",
                        "expires_in": 900,
                        "interval": 5,
                    }
                return {"access_token": "gho_temporary_test_token"}

            class NeverCancel:
                @staticmethod
                def wait(_seconds):
                    return False

                @staticmethod
                def set():
                    return None

                @staticmethod
                def clear():
                    return None

            class FakeClient:
                def __init__(self, _base_url, token=""):
                    self.token = token

                def json(self, path, method="GET", payload=None, authenticated=False):
                    if path == "auth/github":
                        self.assert_exchange = payload
                        if payload != {"access_token": "gho_temporary_test_token"}:
                            raise AssertionError(payload)
                        return {"token": "community_session_token", "provider": "github"}
                    if path == "session":
                        return {"user": {"provider": "github", "provider_login": "FixtureUser"}, "stats": {}}
                    raise AssertionError(path)

            service._github_cancel = NeverCancel()
            try:
                with patch("kfps_ui.community_service._github_post_json", side_effect=github_post), \
                     patch("kfps_ui.community_service.CommunityApiClient", FakeClient), \
                     patch("kfps_ui.community_service.webbrowser.open"):
                    result = service._github_auth_flow("Ov23liFixtureClientId")
                self.assertEqual(result["token"], "community_session_token")
                self.assertEqual(calls[0][1], {"client_id": "Ov23liFixtureClientId"})
                self.assertNotIn("scope", calls[0][1])
                self.assertEqual(device_events[0]["user_code"], "ABCD-EFGH")

                class CancelImmediately:
                    @staticmethod
                    def wait(_seconds):
                        return True

                    @staticmethod
                    def set():
                        return None

                    @staticmethod
                    def clear():
                        return None

                service._github_cancel = CancelImmediately()
                calls.clear()
                with patch("kfps_ui.community_service._github_post_json", side_effect=github_post), \
                     patch("kfps_ui.community_service.webbrowser.open"):
                    with self.assertRaises(CommunityApiError) as cancelled:
                        service._github_auth_flow("Ov23liFixtureClientId")
                self.assertEqual(cancelled.exception.code, "github_auth_cancelled")
            finally:
                service.close()

    def test_private_owner_preview_is_authenticated_cached_and_hash_checked(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "preview.json"
            write_design(source, 1234)
            preview = inspect_upload(source, folder).preview_bytes
            import hashlib
            digest = hashlib.sha256(preview).hexdigest()
            app_root = folder / "app"
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CommunityService(paths, DummyDesktop(source), DummyLog(), demo=True)
            target = app_root / "runtime" / "community" / "private-previews" / f"{digest}.png"
            try:
                with patch.object(CommunityApiClient, "binary", return_value=(preview, {"Content-Type": "image/png"})) as binary:
                    result = service._fetch_private_preview("artwork-1", digest, "/v1/artworks/artwork-1/preview", "session", target)
                self.assertEqual(Path(result["path"]), target)
                self.assertEqual(target.read_bytes(), preview)
                self.assertTrue(binary.call_args.kwargs["authenticated"])
                with patch.object(CommunityApiClient, "binary", return_value=(preview, {})):
                    with self.assertRaises(CommunityApiError) as mismatch:
                        service._fetch_private_preview("artwork-1", "0" * 64, "/v1/artworks/artwork-1/preview", "session", target)
                self.assertEqual(mismatch.exception.code, "preview_checksum_mismatch")
            finally:
                service.close()

    def test_download_requires_a_community_account_before_network_access(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            app_root = folder / "app"
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CommunityService(paths, DummyDesktop(folder / "unused.json"), DummyLog(), demo=True)
            service._token = ""
            service._session_user = {}
            service._selected = {"id": "anonymous-download", "downloadUrl": "/v1/artworks/anonymous-download/download"}
            try:
                with patch.object(CommunityApiClient, "binary") as binary:
                    service.downloadSelected()
                binary.assert_not_called()
                self.assertEqual(service.errorMessage, "Sign in before downloading community artwork.")
            finally:
                service.close()

    def test_upload_browser_path_uses_the_same_validator_without_opening_file_explorer(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "Browser Selection.json"
            write_design(source, 2468)
            app_root = folder / "app"
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            desktop = DummyDesktop(folder / "manual-choice.json")
            service = CommunityService(paths, desktop, DummyLog(), app_version="3.0.81", demo=True)
            try:
                service.selectUploadJson(str(source))
                self.assertTrue(wait_for(lambda: not service.busy and bool(service.uploadPath)), service.errorMessage)
                self.assertEqual(Path(service.uploadPath), source.resolve())
                self.assertEqual(service.uploadName, "Browser Selection")
                self.assertEqual(service.uploadShapeCount, 3)
                self.assertEqual(desktop.choose_calls, 0)
                payload = service._upload_payload(
                    "Fixture", "", "Original Artwork", "test", "handmade",
                    "kfps-community-share-v1", False, True, False,
                )
                self.assertEqual(payload["client_version"], "3.0.81")
                self.assertEqual(payload["classification"], "handmade")

                service._scope = "handmade"
                self.assertIn("scope=browse", service._catalog_path())
                self.assertIn("classification=handmade", service._catalog_path())
                service._scope = "toolmade"
                self.assertIn("classification=toolmade", service._catalog_path())

                service.selectUploadJson(str(folder / "missing.json"))
                self.assertEqual(service.uploadPath, "")
                self.assertIn("existing JSON file", service.errorMessage)
            finally:
                service.close()

    def test_supporter_handoff_is_account_bound_and_restricted_assets_stay_memory_only(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "supporter-preview.json"
            write_design(source, 4321)
            preview = inspect_upload(source, folder).thumbnail_bytes
            import hashlib
            digest = hashlib.sha256(preview).hexdigest()
            app_root = folder / "app"
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            service = CommunityService(paths, DummyDesktop(source), DummyLog(), demo=True)
            subject = "11111111-1111-4111-8111-111111111111"
            requested = []
            service.supporterEntitlementRequested.connect(requested.append)
            try:
                service.demo = False
                service._token = "session"
                service._client.token = "session"
                service._session_user = {"id": subject, "username": "SupporterTester"}
                service._supporter = {"active": False, "verified_until": ""}
                service._supporter_request_after = 0
                service.ensureSupporterEntitlement()
                self.assertEqual(requested, [subject])
                self.assertTrue(service._supporter_entitlement_pending)

                service.applySupporterEntitlement({
                    "ok": False, "subject": subject, "message": "No active supporter registration.",
                })
                self.assertFalse(service._supporter_entitlement_pending)
                self.assertIn("No active", service.supporterStatus)

                expires = datetime.fromtimestamp(time.time() + 900, timezone.utc).isoformat().replace("+00:00", "Z")
                service._apply_result("supporter_verify", {
                    "ok": True, "value": {"supporter": {"active": True, "verified_until": expires}},
                })
                self.assertTrue(service.supporterAccess)
                with patch.object(service, "_submit") as submit:
                    service._scope = "supporters"
                    service.setLocalSupporterState("revoked")
                self.assertFalse(service.supporterAccess)
                self.assertEqual(service.selectedScopeIndex, 3)
                self.assertEqual(service.artworkModel.rowCount(), 0)
                self.assertEqual(submit.call_args.args[0], "supporter_clear")
                self.assertTrue(service._supporter_clear_required)
                service.setLocalSupporterState("active")
                service._supporter = {"active": True, "verified_until": expires}

                item = {
                    "id": "supporter-artwork",
                    "title": "Restricted fixture",
                    "supporter_only": True,
                    "preview_url": "/v1/artworks/supporter-artwork/preview",
                    "thumbnail_url": "/v1/artworks/supporter-artwork/thumbnail",
                    "download_url": "/v1/artworks/supporter-artwork/download",
                    "preview_sha256": digest,
                    "thumbnail_sha256": digest,
                    "creator": {"username": "Artist"},
                }
                row = service._normalize_artwork(item)
                self.assertTrue(row["supporterOnly"])
                self.assertEqual(row["previewUrl"], "")
                self.assertEqual(row["thumbnailUrl"], "")
                with patch.object(CommunityApiClient, "binary", return_value=(preview, {"Content-Type": "image/png"})) as binary:
                    asset = service._fetch_supporter_asset(
                        row["id"], digest, row["_thumbnailAssetUrl"], "session", "thumbnail",
                    )
                self.assertTrue(asset["data_url"].startswith("data:image/png;base64,"))
                self.assertTrue(binary.call_args.kwargs["authenticated"])
                self.assertFalse(any(paths.runtime_root.rglob("*.png")))

                service._scope = "supporters"
                service._write_cache({"items": [item], "page": 1, "page_count": 1, "total": 1})
                self.assertFalse(service._cache_file.exists())
            finally:
                service.close()

    def test_community_qml_exposes_login_inspector_and_risk_policy(self):
        page = (UI / "qml" / "pages" / "CommunityPage.qml").read_text(encoding="utf-8")
        card = (UI / "qml" / "components" / "CommunityArtworkCard.qml").read_text(encoding="utf-8")
        self.assertIn('communityService.connectAccountWith("github")', page)
        self.assertIn("id: artworkInspector", page)
        self.assertIn("onDoubleClicked: root.openArtworkInspector(index)", page)
        self.assertIn("signal doubleClicked()", card)
        self.assertIn("use it at your own risk", page)
        self.assertIn("uploadCompatibilityConfirmationRequired", page)
        self.assertIn("Detected format:", page)
        self.assertIn('text: communityService.authenticated ? "Download to Library" : "Connect to Download"', page)
        self.assertNotIn("Browsing and downloads work without an account", page)
        self.assertIn("id: usernameConfirmDialog", page)
        self.assertIn('text: "Review Username"', page)
        self.assertIn('text: "Confirm Permanently"', page)
        self.assertIn("communityService.chooseUsername(confirmed, confirmed)", page)
        self.assertIn("id: uploadFiles", page)
        self.assertIn("model: jsonService.fileModel", page)
        self.assertIn("communityService.selectUploadJson(String(path))", page)
        self.assertIn('text: "Import JSON File"', page)
        self.assertIn('Label { text: "Output folder" }', page)
        self.assertIn("CommunityUploadTile", page)
        self.assertIn('SCOPE_LABELS = ["Browse", "Handmade", "Toolmade", "Supporters", "Favorites", "Following", "My uploads"]',
                      (UI / "src" / "kfps_ui" / "community_service.py").read_text(encoding="utf-8"))
        self.assertIn('text: "Handmade"', page)
        self.assertIn('text: "Toolmade"', page)
        self.assertIn('"Get access to supporter vinyl sharing"', page)
        self.assertIn('desktop.openUrl("https://ko-fi.com/s/2d1507698d")', page)
        self.assertIn("enabled: index < 4 || communityService.authenticated", page)
        self.assertIn('text: "Supporters"', page)
        self.assertIn("root.uploadSupporterOnly", page)
        self.assertIn("cardSupporterOnly", card)
        app = (UI / "app.py").read_text(encoding="utf-8")
        self.assertIn("community.supporterEntitlementRequested.connect", app)
        self.assertIn("supporter.communityEntitlementReady.connect", app)
        self.assertIn("root.uploadClassification.length > 0", page)
        self.assertIn("id: editTagsDialog", page)
        self.assertIn("communityService.selectedMetadataEditable", page)
        self.assertIn("communityService.updateSelectedTags(editTagsField.text)", page)
        self.assertNotIn("updateSelectedClassification", page)
        self.assertNotIn("Compatible games", page)
        self.assertNotIn("selectedGames", page)
        self.assertIn("text: \"Report\"", page)
        self.assertIn("text: \"Remove\"", page)
        self.assertNotIn("safe for work", page.lower())
        self.assertNotIn("mature_content", page)


@unittest.skipUnless(os.environ.get("KFPS_COMMUNITY_E2E") == "1", "local Worker integration test is opt-in")
class CommunityWorkerIntegrationTests(unittest.TestCase):
    def test_complete_qt_client_workflow(self):
        api = os.environ.get("KFPS_COMMUNITY_API_URL", "http://127.0.0.1:8790/v1")
        self.assertEqual(CommunityApiClient(api).json("health")["status"], "ok")

        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as folder:
            folder = Path(folder)
            source = folder / "CommunityWorkflow.json"
            variant = int(uuid.uuid4().hex[:8], 16)
            write_design(source, variant)
            app_root = folder / "app"
            (app_root / "imgs" / "library").mkdir(parents=True)
            paths = AppPaths(
                app_root=app_root,
                ui_root=UI,
                qml_root=UI / "qml",
                asset_root=UI / "assets",
                runtime_root=app_root / "runtime",
                bundled_python=app_root / "python" / "python.exe",
            )
            desktop = DummyDesktop(source)
            log = DummyLog()
            service = CommunityService(paths, desktop, log, app_version="3.0.81")
            try:
                self.assertTrue(wait_for(lambda: service.connected and not service.busy), service.errorMessage)
                self.assertGreaterEqual(service.totalCount, 1)

                service.connectAccountWith("local-test")
                self.assertTrue(wait_for(lambda: service.authenticated and not service.busy), service.errorMessage)
                self.assertTrue(service.usernameRequired)
                username = "QtFlow_" + uuid.uuid4().hex[:10]
                service.chooseUsername(username, username)
                self.assertTrue(wait_for(lambda: service.username == username and not service.busy), service.errorMessage)

                service.updateProfile("Automated integration profile", "https://example.com/kfps")
                self.assertTrue(wait_for(
                    lambda: service.sessionUser.get("bio") == "Automated integration profile" and not service.busy
                ), service.errorMessage)

                service.chooseUploadJson()
                self.assertTrue(wait_for(lambda: service.uploadReady and not service.busy), service.errorMessage)
                title = "Qt Workflow " + uuid.uuid4().hex[:8]
                service.submitUpload(
                    title, "End-to-end client test.", "Original Artwork", "automated, integration",
                    "toolmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: service.selectedOwned and service.selectedArtwork.get("title") == title and not service.busy
                ), service.errorMessage)
                self.assertIn("/thumbnail", service.selectedArtwork.get("thumbnailUrl", ""))
                self.assertEqual(service.selectedArtwork.get("gamesText"), "FH6")
                self.assertEqual(service.selectedArtwork.get("schemaId"), "kfps-primitives")
                self.assertTrue(service.selectedArtwork.get("schemaKnown"))
                self.assertEqual(service.selectedArtwork.get("classification"), "toolmade")
                self.assertTrue(service.selectedMetadataEditable)
                artwork_id = service.selectedArtwork["id"]

                service.updateSelectedTags("automated, integration, retagged")
                self.assertTrue(wait_for(
                    lambda: "retagged" in service.selectedArtwork.get("tagsText", "") and not service.busy
                ), service.errorMessage)
                self.assertEqual(service.selectedArtwork.get("classification"), "toolmade")

                service.submitUpload(
                    title + " Duplicate", "Duplicate test.", "Original Artwork", "automated",
                    "toolmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(lambda: "already" in service.errorMessage.lower() and not service.busy), service.errorMessage)
                service.clearError()

                service.favoriteSelected()
                self.assertTrue(wait_for(lambda: service.selectedArtwork.get("favorited") is True and not service.busy), service.errorMessage)
                service.downloadSelected()
                self.assertTrue(wait_for(lambda: bool(service.downloadedPath) and not service.busy), service.errorMessage)
                downloaded = Path(service.downloadedPath)
                self.assertTrue(downloaded.is_file())
                canonical = json.loads(downloaded.read_text(encoding="utf-8"))
                self.assertEqual(canonical["format"], "kfps.community.v1")
                self.assertNotIn("private_path", json.dumps(canonical))
                manifest_path = downloaded.with_suffix(".community.manifest.json")
                self.assertTrue(manifest_path.is_file())
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["source_schema"], "kfps-primitives")
                self.assertTrue(manifest["schema_known"])
                self.assertTrue(downloaded.with_suffix(".png").is_file())

                write_design(source, variant + 1)
                service.chooseUploadJson()
                self.assertTrue(wait_for(
                    lambda: service.uploadReady and service._upload_inspection.source_sha256
                    != service._rows[service.selectedIndex].get("contentSha256", "") and not service.busy
                ))
                service.submitRevision(
                    title, "Revised end-to-end client test.", "Original Artwork", "automated, revision",
                    "toolmade", "kfps-community-share-v1", False, True, False, "Adjusted one accent color.",
                )
                self.assertTrue(wait_for(lambda: service.uploadStatus.startswith("Revision 2") and not service.busy), service.errorMessage)

                service.setSearchQuery(title)
                service.setScopeIndex(2)
                self.assertTrue(wait_for(
                    lambda: any(row.get("id") == artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.setScopeIndex(1)
                self.assertTrue(wait_for(
                    lambda: all(row.get("id") != artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.setSearchQuery("")
                service.setScopeIndex(0)
                self.assertTrue(wait_for(
                    lambda: service.totalCount > 1 and any(row.get("creatorName") != username for row in service._rows)
                    and not service.busy
                ), service.errorMessage)
                other_index = next(i for i, row in enumerate(service._rows) if row.get("creatorName") != username)
                service.selectArtwork(other_index)
                other_creator = service.selectedArtwork["creatorName"]
                service.loadCreator(other_creator)
                self.assertTrue(wait_for(lambda: service.creatorProfile.get("username") == other_creator and not service.busy), service.errorMessage)
                service.followSelectedCreator()
                self.assertTrue(wait_for(lambda: service.selectedArtwork.get("creatorFollowed") is True and not service.busy), service.errorMessage)
                service.reportSelected("other", "Automated local moderation queue test.")
                self.assertTrue(wait_for(
                    lambda: service.statusMessage == "Report submitted privately and highlighted for moderation."
                    and not service.busy
                ), service.errorMessage)

                service.setScopeIndex(6)
                self.assertTrue(wait_for(
                    lambda: any(row.get("id") == artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.selectArtwork(next(i for i, row in enumerate(service._rows) if row.get("id") == artwork_id))
                service.removeSelectedUpload()
                self.assertTrue(wait_for(
                    lambda: all(row.get("id") != artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)

                write_design(source, variant + 2)
                unknown_payload = json.loads(source.read_text(encoding="utf-8"))
                unknown_payload["format"] = "integration-unknown.v1"
                source.write_text(json.dumps(unknown_payload), encoding="utf-8")
                service.chooseUploadJson()
                self.assertTrue(wait_for(
                    lambda: service.uploadReady and service.uploadCompatibilityConfirmationRequired and not service.busy
                ), service.errorMessage)
                unknown_title = "Qt Unknown " + uuid.uuid4().hex[:8]
                service.submitUpload(
                    unknown_title, "Unknown-schema acknowledgement test.", "Original Artwork", "automated",
                    "handmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: "unrecognized format" in service.errorMessage.lower() and not service.busy
                ), service.errorMessage)
                service.clearError()
                service.submitUpload(
                    unknown_title, "Unknown-schema acknowledgement test.", "Original Artwork", "automated",
                    "handmade", "kfps-community-share-v1", False, True, True,
                )
                self.assertTrue(wait_for(
                    lambda: service.selectedOwned and service.selectedArtwork.get("title") == unknown_title
                    and not service.busy
                ), service.errorMessage)
                self.assertEqual(service.selectedArtwork.get("schemaId"), "unrecognized")
                self.assertFalse(service.selectedArtwork.get("schemaKnown"))
                self.assertTrue(service.selectedArtwork.get("schemaWarning"))
                service.removeSelectedUpload()
                self.assertTrue(wait_for(
                    lambda: all(row.get("title") != unknown_title for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.signOut()
                self.assertFalse(service.authenticated)
                self.assertFalse(service._credentials.session_file.exists())
            finally:
                service.close()
                APP.processEvents()


if __name__ == "__main__":
    unittest.main()
