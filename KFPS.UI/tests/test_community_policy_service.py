"""Real client/service integration with an isolated, contract-shaped loopback peer."""
from __future__ import annotations

import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.community_client import CommunityApiError
from kfps_ui.community_gallery_service import CommunityGalleryService
from kfps_ui.community_service import CommunityService
from test_community_access import capability, contribution, policy

APP = QCoreApplication.instance() or QCoreApplication([])
RUN_ROOT = UI.parent / "runtime/community-tests/free-access-client-20261019"


def settle(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        APP.processEvents()
        if predicate():
            return True
        time.sleep(.005)
    APP.processEvents()
    return bool(predicate())


class WirePeer:
    def __init__(self):
        self.mode = "verified_v1"
        self.header = "verified_v1"
        self.count = 9
        self.reason = None
        self.paid = False
        self.grandfathered_at = None
        self.requests = []
        self.claim_outcomes = {}
        self.bad_claim_response = False
        self.redemption_error = ""
        self.image = b""
        self.block_session = threading.Event()
        self.release_session = threading.Event()
        self.delay_session = False
        self.raw = json.dumps({"format": "kfps.community.v1", "metadata": {"shape_count": 1},
            "shapes": [{"type": 16, "color": [1, 2, 3, 255], "data": [1, 2, 3, 4, 5]}]}, separators=(",", ":")).encode()
        self.records = [self.record("one"), self.record("two"), self.record("restricted", restricted=True)]
        peer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self): self.respond()
            def do_POST(self): self.respond()
            def do_DELETE(self): self.respond()

            def respond(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b""
                peer.requests.append((self.command, self.path, dict(self.headers), body))
                path = urlsplit(self.path).path.removeprefix("/v1/")
                token = self.headers.get("Authorization", "")
                username = "Second" if token.endswith("account-b") else "Owner"
                status, payload = 200, {}
                if path == "config":
                    payload = {} if peer.mode == "old" else {"access_policy": policy(peer.mode)}
                elif path == "session":
                    payload = peer.session(username)
                    if peer.delay_session:
                        peer.delay_session = False
                        peer.block_session.set()
                        peer.release_session.wait(5)
                elif path == "profile/ignored":
                    payload = {"items": []}
                elif path == "profile/vinyl-claims":
                    request = json.loads(body)
                    results = []
                    for item in reversed(request["claims"]):
                        error = peer.claim_outcomes.get(item["artwork_id"])
                        results.append({"artwork_id": item["artwork_id"], "outcome": "rejected" if error else "accepted",
                                        "error": error, "contribution": None if error else contribution("scheduled", False)})
                    if peer.bad_claim_response:
                        results = results[:1]
                    payload = {"results": results, "access_policy": policy(), "capabilities": {"verified": peer.verified()}}
                elif path == "artworks" and self.command == "GET":
                    query = parse_qs(urlsplit(self.path).query)
                    rows = copy.deepcopy(peer.records)
                    if query.get("sort") == ["featured"]:
                        rows = []
                    for row in rows:
                        if row["status"] != "published":
                            continue
                        allowed = not row["supporter_only"] or peer.verified()["active"]
                        row["access"].update(can_view_media=allowed, can_download=allowed, can_interact=allowed,
                                             restriction_reason=None if allowed else "verified_required")
                    payload = {"items": rows, "page": 1, "page_count": 1, "total": len(rows)}
                elif path.endswith("/download"):
                    payload = peer.raw
                elif path.endswith(("/thumbnail", "/preview")):
                    payload = peer.image
                elif path == "artworks" and self.command == "POST":
                    payload = {"artwork": peer.record("uploaded")}
                elif path == "supporter/verify":
                    payload = {"supporter": {"active": False}, "access_policy": policy(peer.mode),
                               "capabilities": {"verified": peer.verified()}}
                    if self.command == "POST" and peer.redemption_error:
                        status, payload = 409, {"error": peer.redemption_error, "message": "Synthetic redemption conflict"}
                raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                self.send_response(status)
                if peer.header is not None:
                    self.send_header("X-Community-Access-Policy", peer.header)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def verified(self):
        reason = "policy_legacy" if self.mode in {"legacy_supporter", "old"} else self.reason
        if reason is None and self.grandfathered_at:
            reason = "grandfathered_supporter"
        result = capability(self.count, reason)
        result["grandfathered_at"] = self.grandfathered_at
        return result

    def session(self, username="Owner"):
        result = {"user": {"id": username, "username": username, "provider": "github"}, "stats": {},
                  "supporter": {"active": self.paid, "verified_until": "2099-01-01T00:00:00Z" if self.paid else ""}}
        if self.mode != "old":
            result.update(access_policy=policy(self.mode), capabilities={"verified": self.verified()})
        return result

    def record(self, ident, restricted=False):
        return {"id": ident, "title": "<b>\ud55c\uae00 \u65e5\u672c\u8a9e " + ident + ".json</b>", "kind": "vinyl",
                "creator": {"username": "Owner"}, "classification": "handmade", "status": "published",
                "supporter_only": restricted, "preview_url": "", "thumbnail_url": "", "photo_urls": [],
                "download_url": f"artworks/{ident}/download", "current_revision": 1, "content_sha256": hashlib.sha256(self.raw).hexdigest(),
                "contribution": contribution(), "access": {"audience": "verified" if restricted else "public",
                "can_view_media": not restricted, "can_download": not restricted, "can_interact": not restricted,
                "restriction_reason": "verified_required" if restricted else None}}

    def close(self):
        self.release_session.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


class PolicyServiceTests(unittest.TestCase):
    def setUp(self):
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=RUN_ROOT)
        root = Path(self.temp.name)
        self.peer = WirePeer()
        self.endpoint = patch.dict(os.environ, {"KFPS_COMMUNITY_API_URL": self.peer.url})
        self.endpoint.start()
        paths = AppPaths(app_root=root, ui_root=UI, qml_root=UI / "qml", asset_root=UI / "assets",
                         runtime_root=root / "runtime", bundled_python=UI.parent / "python/python.exe")
        self.service = CommunityService(paths, SimpleNamespace(openFolder=lambda _: None), SimpleNamespace(append=lambda *args: None))
        self.service._activation_timer.stop()
        self.service._supporter_timer.stop()
        self.service._token = "account-a"
        self.service._client.token = "account-a"
        self.service._local_supporter_state = "no_key"
        self.service.activate()
        self.assertTrue(settle(lambda: self.service.connected and not self.service.busy), self.service.errorMessage)
        self.gallery = None

    def tearDown(self):
        self.peer.release_session.set()
        if self.gallery:
            self.gallery.close()
        self.service.close()
        self.peer.close()
        self.endpoint.stop()
        self.temp.cleanup()

    def refresh(self):
        self.service.refreshAccount()
        self.assertTrue(settle(lambda: not self.service.busy and not self.service._policy_timer.isActive()), self.service.errorMessage)

    def make_gallery(self):
        self.gallery = CommunityGalleryService(UI.parent, self.service, SimpleNamespace(communityLanguage="en"))
        self.gallery.timer.stop()
        self.gallery.filter("scope", "My uploads")
        self.assertTrue(settle(lambda: not self.gallery.busy))
        return self.gallery

    def test_both_requirements_server_clock_and_revocation(self):
        self.assertFalse(self.service.verifiedAccess)
        for count, reason, expected in ((10, "waiting_period", False), (9, None, False),
                                        (10, None, True), (11, "account_suspended", False)):
            self.peer.count, self.peer.reason = count, reason
            self.refresh()
            self.assertEqual(self.service.verifiedAccess, expected)
            self.assertEqual(self.service.verifiedCount, count)
            self.assertFalse(self.service.supporterAccess)
        self.assertEqual(self.service.connectedAt, capability()["connected_at"])

    def test_all_real_transport_requests_negotiate_without_token_to_public_config(self):
        self.refresh()
        for method, path, headers, body in self.peer.requests:
            self.assertEqual(headers.get("X-Community-Access-Contract"), "1", path)
            if path.endswith("/config") or path.endswith("/health"):
                self.assertNotIn("Authorization", headers)

    def test_legacy_revocation_invalidates_inflight_access_snapshot(self):
        self.peer.mode = self.peer.header = "legacy_supporter"
        self.peer.paid = True
        self.service._local_supporter_state = "active"
        self.refresh()
        self.assertTrue(self.service.restrictedAccess)
        snapshot = self.service.accessSnapshot()
        self.peer.paid = False
        self.refresh()
        self.assertFalse(self.service.restrictedAccess)
        with self.assertRaises(CommunityApiError):
            self.service.assertAccessSnapshot(snapshot)

    def test_retained_public_images_negotiate_and_locked_thumbnail_remains_visible(self):
        from test_community_gallery import solid_png
        self.peer.image = solid_png("#3cbfb0")
        digest = hashlib.sha256(self.peer.image).hexdigest()
        records = [self.peer.record("restricted", True), self.peer.record("public")]
        for item in records:
            item.update(thumbnail_url=f"artworks/{item['id']}/thumbnail", thumbnail_sha256=digest,
                        preview_url=f"artworks/{item['id']}/preview", preview_sha256=digest)
        self.service._scope = "browse"
        self.service._apply_catalog({"items": records})
        self.assertFalse(self.service._rows[1]["thumbnailUrl"].startswith("http"))
        self.service._schedule_private_previews()
        self.assertTrue(settle(lambda: all(row["thumbnailUrl"].startswith("data:image/png;") for row in self.service._rows)))
        self.assertFalse(self.service._rows[0]["canDownload"])
        self.assertFalse(any("restricted/preview" in path for _, path, _, _ in self.peer.requests))
        self.service.selectArtwork(1)
        self.assertTrue(settle(lambda: any("public/preview" in path for _, path, _, _ in self.peer.requests)))
        self.assertTrue(settle(lambda: not self.service._private_preview_inflight))
        self.assertTrue(self.service.selectedArtwork["previewUrl"].startswith("data:image/png;"))
        for _, path, headers, _ in self.peer.requests:
            if "/thumbnail" in path or "/preview" in path:
                self.assertEqual(headers.get("X-Community-Access-Contract"), "1")
                self.assertNotIn("Authorization", headers)
        self.assertFalse(any(self.service.paths.runtime_root.rglob("*.png")))

    def test_unknown_header_revokes_before_download_and_refreshes_closed(self):
        self.peer.count = 10
        self.refresh()
        client = self.service.sessionClient()
        self.peer.header, self.peer.mode = "future_v9", "future_v9"
        with self.assertRaises(CommunityApiError):
            client.binary("artworks/restricted/download", authenticated=True)
        self.assertFalse(self.service.verifiedAccess)
        self.assertTrue(settle(lambda: self.service.policyMode == "unsupported" and not self.service.busy))
        self.assertFalse(self.service.policyReady)
        self.assertFalse(any(self.service.paths.library_root.rglob("*.json")))

    def test_missing_header_alone_cannot_downgrade_known_verified(self):
        self.peer.count = 10
        self.refresh()
        self.peer.header = None
        client = self.service.sessionClient()
        client.json("health")
        self.assertEqual(self.service.policyMode, "verified_v1")
        self.refresh()
        self.assertTrue(self.service.verifiedAccess)
        self.peer.mode = "old"
        self.refresh()
        self.assertEqual(self.service.policyMode, "legacy_supporter")
        self.assertFalse(self.service.verifiedAccess)

    def test_old_account_response_and_old_client_cannot_restore_access(self):
        client = self.service.sessionClient()
        self.peer.delay_session = True
        self.service.refreshAccount()
        self.assertTrue(self.peer.block_session.wait(2))
        self.service.signOut()
        self.peer.release_session.set()
        self.assertTrue(settle(lambda: not self.service.busy))
        self.assertFalse(self.service.authenticated)
        self.assertFalse(self.service.verifiedAccess)
        with self.assertRaises(CommunityApiError):
            client.json("session", authenticated=True)

    def test_claim_batch_is_explicit_bounded_and_results_are_id_correlated(self):
        gallery = self.make_gallery()
        gallery.setClaimsView(True)
        self.assertTrue(settle(lambda: not gallery.busy))
        for ident in ("one", "two"):
            gallery.toggleClaim(ident)
        self.assertEqual(self.service.claimSelection, ["one", "two"])
        self.peer.claim_outcomes["two"] = "claim_revision_changed"
        self.service.submitClaims(False)
        self.assertFalse(any(path.endswith("vinyl-claims") for _, path, _, _ in self.peer.requests))
        self.service.submitClaims(True)
        self.assertTrue(settle(lambda: len(self.service.claimResults) == 2 and not self.service.busy))
        self.assertEqual([row["artwork_id"] for row in self.service.claimResults], ["one", "two"])
        self.assertEqual(self.service.claimResults[0]["contribution"]["state"], "scheduled")
        self.assertEqual(self.service.claimResults[1]["error"], "claim_revision_changed")
        self.assertEqual(self.service.verifiedCount, 9)
        self.assertFalse(self.service.verifiedAccess)
        self.assertEqual(self.service.claimSelection, [])
        claims_request = next(json.loads(body) for method, path, _, body in self.peer.requests if path.endswith("vinyl-claims"))
        self.assertEqual(set(claims_request["claims"][0]), {"artwork_id", "revision", "content_sha256"})
        self.assertTrue(any("contribution_view=claims" in path and "scope=mine" in path for _, path, _, _ in self.peer.requests))

    def test_progress_only_refresh_keeps_upload_draft_but_account_change_drops_it(self):
        gallery = self.make_gallery()
        pending = {"title": "opaque \ud55c\uae00.json", "kind": "vinyl", "payload": b"source"}
        gallery._pending = pending
        self.peer.count = 8
        self.refresh()
        self.assertIs(gallery._pending, pending)
        self.peer.count = 10
        self.refresh()
        self.assertIs(gallery._pending, pending)
        self.service.signOut()
        self.assertIsNone(gallery._pending)

    def test_historical_claim_metadata_never_fetches_empty_or_private_media(self):
        row = self.peer.records[0]
        row.update(status="removed", download_url="", preview_url="", thumbnail_url="", photo_urls=[])
        row["access"].update(can_view_media=False, can_download=False, can_interact=False, restriction_reason="unavailable")
        gallery = self.make_gallery()
        gallery.select("one")
        self.assertEqual(gallery.selected["previewUrl"], "")
        self.assertEqual(gallery.selected["photoUrls"], [])
        self.assertEqual(gallery.selected["title"], row["title"])
        self.assertFalse(gallery.selected["downloadable"])
        self.assertFalse(gallery.selected["canInteract"])

    def test_toolmade_upload_remains_allowed_without_claims(self):
        gallery = self.make_gallery()
        row = self.peer.records[0]
        row["classification"] = "toolmade"
        # Even a stale can_claim flag cannot let the client select a known Toolmade row.
        gallery.refresh()
        self.assertTrue(settle(lambda: not gallery.busy))
        gallery.toggleClaim("one")
        self.assertEqual(self.service.claimSelection, [])
        self.assertFalse(next(item for item in gallery.rows if item["id"] == "one")["canClaim"])
        from test_community_gallery import solid_png
        gallery._pending = {"kind": "vinyl", "payload": self.peer.raw, "preview": solid_png("blue")}
        gallery.publish({"title": "Toolmade \u65e5\u672c\u8a9e.json", "rights": True, "classification": "toolmade",
                         "authorship": "own", "supporter": False})
        self.assertTrue(settle(lambda: not gallery.busy and gallery._pending is None), gallery.status)
        payload = next(json.loads(body) for method, path, _, body in self.peer.requests if method == "POST" and path.endswith("/artworks"))
        self.assertEqual(payload["classification"], "toolmade")
        self.assertEqual(payload["authorship"], "own")
        self.assertEqual(payload["audience"], "public")
        self.assertEqual(self.service.verifiedCount, 9)

    def test_optional_grant_forwarded_unchanged_only_to_understood_new_worker(self):
        entitlement = {"fixture": "unchanged-v1"}
        signed_grant = {"type": "kfps.community.legacy-verified-grant", "version": 1,
                        "payload": "opaque-fixture", "signature": "opaque-signature", "kid": "test"}
        self.service._local_supporter_state = "active"
        self.service._local_supporter_key_available = True
        self.service._supporter_request_after = time.time() + 600
        self.service.applySupporterEntitlement({"ok": True, "subject": "Owner", "entitlement": entitlement,
                                               "legacy_verified_grant": signed_grant})
        self.assertTrue(settle(lambda: not self.service.busy))
        payload = next(json.loads(body) for method, path, _, body in self.peer.requests if method == "POST" and path.endswith("supporter/verify"))
        self.assertEqual(payload, {"entitlement": entitlement, "legacy_verified_grant": signed_grant})
        self.assertFalse(self.service.verifiedAccess)
        self.peer.mode, self.peer.header = "old", None
        self.refresh()
        self.peer.requests.clear()
        self.service.applySupporterEntitlement({"ok": True, "subject": "Owner", "entitlement": entitlement,
                                               "legacy_verified_grant": signed_grant})
        self.assertTrue(settle(lambda: not self.service.busy))
        payload = next(json.loads(body) for method, path, _, body in self.peer.requests if method == "POST" and path.endswith("supporter/verify"))
        self.assertEqual(payload, {"entitlement": entitlement})

    def test_permanent_grant_survives_local_key_removal_expiry_and_reconnect(self):
        self.peer.count = 0
        self.peer.grandfathered_at = "2026-10-19T00:00:00.000Z"
        self.refresh()
        self.assertTrue(self.service.grandfatheredVerified)
        self.assertTrue(self.service.verifiedAccess)
        self.assertFalse(self.service.supporterAccess)
        connected = self.service.connectedAt
        self.service.setLocalSupporterState("no_key", False)
        self.refresh()
        self.assertTrue(self.service.grandfatheredVerified)
        self.service.signOut()
        self.assertTrue(settle(lambda: not self.service.busy))
        self.assertFalse(self.service.verifiedAccess)
        self.service._token = "account-a"
        self.service._client.token = "account-a"
        self.refresh()
        self.assertTrue(self.service.grandfatheredVerified)
        self.assertEqual(self.service.connectedAt, connected)
        self.peer.reason = "account_suspended"
        self.refresh()
        self.assertFalse(self.service.verifiedAccess)
        self.assertEqual(self.service._verified["grandfathered_at"], self.peer.grandfathered_at)

    def test_terminal_migration_outcome_does_not_repeat_on_refresh_or_restart(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.assertEqual(requests, ["Owner"])
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "not_eligible",
                                               "message": "This synthetic key is not eligible for migration."})
        self.assertEqual(self.service.statusMessage, "This synthetic key is not eligible for migration.")
        for timestamp in (time.time() + 600, time.time() + 1200):
            with patch("kfps_ui.community_service.time.time", return_value=timestamp):
                self.refresh()
        self.assertEqual(requests, ["Owner"])
        self.assertFalse(self.service.verifiedAccess)
        old = self.service
        old.close()
        self.service = CommunityService(old.paths, old.desktop, old.log)
        self.service._activation_timer.stop()
        self.service._supporter_timer.stop()
        self.service._token = self.service._client.token = "account-a"
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.refresh()
        self.assertEqual(requests, ["Owner"])
        self.service.verifyExistingSupporter()
        self.assertEqual(requests, ["Owner", "Owner"])

    def test_new_key_or_account_can_try_without_unlocking_from_previous_outcome(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "community_account_already_bound"})
        self.service.setLocalSupporterState("active", True, "b" * 64)
        self.assertEqual(requests, ["Owner", "Owner"])
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "not_eligible"})
        self.service._token = self.service._client.token = "account-b"
        self.refresh()
        self.assertEqual(requests, ["Owner", "Owner", "Second"])
        self.assertFalse(self.service.verifiedAccess)

    def test_old_proof_without_grant_stops_auto_retries_in_verified_mode(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.peer.count = 10
        self.refresh()
        self.assertTrue(self.service.verifiedAccess)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.applySupporterEntitlement({"ok": True, "subject": "Owner", "entitlement": {"fixture": "v1"}})
        self.assertIn("no permanent Verified grant", self.service.statusMessage)
        with patch("kfps_ui.community_service.time.time", return_value=time.time() + 600):
            self.refresh()
        self.assertEqual(requests, ["Owner"])
        self.assertTrue(self.service.verifiedAccess)
        self.assertFalse(self.service.grandfatheredVerified)
        self.assertFalse(any(method == "POST" and path.endswith("supporter/verify") for method, path, _, _ in self.peer.requests))

    def test_transient_migration_failure_can_retry_after_backoff(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "supporter_entitlement_failed"})
        self.service.ensureSupporterEntitlement()
        self.assertEqual(requests, ["Owner"])
        with patch("kfps_ui.community_service.time.time", return_value=time.time() + 600):
            self.service.ensureSupporterEntitlement()
        self.assertEqual(requests, ["Owner", "Owner"])

    def test_late_failure_for_replaced_key_does_not_mark_new_key_complete(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.setLocalSupporterState("active", True, "b" * 64)
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "key_changed"})
        self.assertEqual(requests, ["Owner", "Owner"])
        self.assertEqual(self.service._migration_completed, [])

    def test_migration_retry_cache_is_bounded_private_and_not_an_access_grant(self):
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "not_eligible"})
        cache = self.service._migration_outcome_file
        text = cache.read_text(encoding="utf-8")
        self.assertNotIn("Owner", text)
        self.assertNotIn("a" * 64, text)
        self.assertNotIn("account-a", text)
        self.assertFalse(self.service.verifiedAccess)
        for invalid in ({"version": 2, "completed": []}, {"version": 1, "completed": "invalid"},
                        {"version": 1, "completed": ["f" * 64] * 65}, ["invalid"]):
            cache.write_text(json.dumps(invalid))
            self.assertEqual(self.service._load_migration_outcomes(), [])
        cache.write_text("x" * 8193)
        self.assertEqual(self.service._load_migration_outcomes(), [])
        cache.write_text("{")
        self.assertEqual(self.service._load_migration_outcomes(), [])

    def test_retry_cache_write_failure_does_not_lose_session_suppression_or_manual_retry(self):
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        with patch.object(self.service, "_atomic_write", side_effect=PermissionError("synthetic")):
            self.service.applySupporterEntitlement({"ok": False, "subject": "Owner", "code": "not_eligible"})
            with patch("kfps_ui.community_service.time.time", return_value=time.time() + 600):
                self.service.ensureSupporterEntitlement()
            self.assertEqual(requests, ["Owner"])
            self.service.verifyExistingSupporter()
            self.assertEqual(requests, ["Owner", "Owner"])

    def test_stale_redemption_cannot_consume_new_request_or_leave_current_request_busy(self):
        self.service.setLocalSupporterState("active", True, "a" * 64)
        marker = self.service._supporter_request_marker
        snapshot = self.service.accessSnapshot()
        self.service._apply_result("supporter_verify", {"ok": True, "snapshot": snapshot,
            "migration_marker": "old-request", "value": {"supporter": {"active": True}}})
        self.assertTrue(self.service._supporter_entitlement_pending)
        self.assertEqual(self.service._supporter_request_marker, marker)
        self.assertFalse(self.service.supporterAccess)
        self.service._access_epoch += 1
        self.service._apply_result("supporter_verify", {"ok": True, "snapshot": snapshot,
            "migration_marker": marker, "value": {"supporter": {"active": True}}})
        self.assertFalse(self.service._supporter_entitlement_pending)
        self.assertFalse(self.service.supporterAccess)
        self.assertEqual(self.service._migration_completed, [])
        self.service._policy_timer.stop()

    def test_account_binding_redemption_conflict_stops_backoff_and_restart_retries(self):
        self.peer.redemption_error = "supporter_account_already_bound"
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        proof = {"ok": True, "subject": "Owner", "entitlement": {"synthetic": "v1"},
                 "legacy_verified_grant": {"synthetic": "paired-grant"}}
        self.service.applySupporterEntitlement(proof)
        self.assertTrue(settle(lambda: not self.service.busy and not self.service._policy_timer.isActive()))
        self.assertEqual(len(self.service._migration_completed), 1)
        with patch("kfps_ui.community_service.time.time", return_value=time.time() + 600):
            self.refresh()
        self.assertEqual(requests, ["Owner"])
        old = self.service
        old.close()
        self.service = CommunityService(old.paths, old.desktop, old.log)
        self.service._activation_timer.stop()
        self.service._supporter_timer.stop()
        self.service._token = self.service._client.token = "account-a"
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.refresh()
        self.assertEqual(requests, ["Owner"])
        self.service.verifyExistingSupporter()
        self.assertEqual(requests, ["Owner", "Owner"])
        self.service.applySupporterEntitlement(proof)
        self.assertTrue(settle(lambda: not self.service.busy and not self.service._policy_timer.isActive()))
        self.assertFalse(self.service.verifiedAccess)
        self.assertEqual(sum(method == "POST" and path.endswith("supporter/verify")
                             for method, path, _, _ in self.peer.requests), 2)

    def test_other_redemption_conflicts_are_not_persisted_as_terminal(self):
        self.peer.redemption_error = "access_changed"
        requests = []
        self.service.supporterEntitlementRequested.connect(requests.append)
        self.service.setLocalSupporterState("active", True, "a" * 64)
        self.service.applySupporterEntitlement({"ok": True, "subject": "Owner",
            "entitlement": {"synthetic": "v1"}, "legacy_verified_grant": {"synthetic": "paired-grant"}})
        self.assertTrue(settle(lambda: not self.service.busy and not self.service._policy_timer.isActive()))
        self.assertEqual(self.service._migration_completed, [])
        with patch("kfps_ui.community_service.time.time", return_value=time.time() + 600):
            self.service.ensureSupporterEntitlement()
        self.assertEqual(requests, ["Owner", "Owner"])

    def test_claim_selection_limit_and_incomplete_response_never_updates_progress(self):
        self.peer.records = [self.peer.record(str(i)) for i in range(12)]
        gallery = self.make_gallery()
        for i in range(12):
            gallery.toggleClaim(str(i))
        self.assertEqual(len(self.service.claimSelection), 10)
        self.peer.bad_claim_response = True
        self.service.submitClaims(True)
        self.assertTrue(settle(lambda: not self.service.busy and not self.service.claimsBusy))
        self.assertEqual(self.service.claimResults, [])
        self.assertEqual(self.service.verifiedCount, 9)
        self.assertFalse(self.service.verifiedAccess)
        self.assertIn("could not be verified", self.service.errorMessage)


if __name__ == "__main__":
    unittest.main()
