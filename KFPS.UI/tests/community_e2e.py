from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from test_community import (
    APP,
    ROOT,
    UI,
    AppPaths,
    CommunityApiClient,
    CommunityService,
    DummyDesktop,
    DummyLog,
    wait_for,
    write_design,
)
from kfps_ui.community_service import SCOPE_VALUES


API = os.environ.get("KFPS_COMMUNITY_API_URL", "http://127.0.0.1:8790/v1")
APP_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
EXPECTED_MINIMUM_VERSION = os.environ.get("KFPS_COMMUNITY_EXPECTED_MINIMUM_UPLOAD_VERSION", APP_VERSION)


def set_scope(service: CommunityService, scope: str) -> None:
    service.setScopeIndex(SCOPE_VALUES.index(scope))


def create_service(folder: Path, source: Path, app_version: str = APP_VERSION) -> CommunityService:
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
    return CommunityService(paths, DummyDesktop(source), DummyLog(), app_version=app_version)


def connect_test_account(service: CommunityService, prefix: str) -> str:
    if not wait_for(lambda: service.connected and not service.busy):
        raise AssertionError(service.errorMessage)
    service.connectAccountWith("local-test")
    if not wait_for(lambda: service.authenticated and not service.busy):
        raise AssertionError(service.errorMessage)
    if service.usernameRequired:
        username = f"{prefix}_{uuid.uuid4().hex[:10]}"
        service.chooseUsername(username, username)
        if not wait_for(lambda: service.username == username and not service.busy):
            raise AssertionError(service.errorMessage)
    return service.username


def issue_supporter_entitlement(subject: str) -> dict:
    issuer = os.environ.get("KFPS_COMMUNITY_SUPPORTER_ISSUER", "")
    key_path = os.environ.get("KFPS_COMMUNITY_TEST_SUPPORTER_KEY", "")
    if not issuer or not key_path:
        raise AssertionError("The disposable supporter issuer was not configured by the E2E runner.")
    issue_command = "issue-unique" if os.environ.get("KFPS_COMMUNITY_UNIQUE_SUPPORTER_ENTITLEMENTS") == "1" else "issue"
    result = subprocess.run(
        ["node", issuer, issue_command, key_path, subject],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(result.stdout)


class CommunityWorkerEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        client = CommunityApiClient(API)
        if client.json("health")["status"] != "ok":
            raise AssertionError("The disposable Community Worker is not healthy.")
        config = client.json("config")
        if config["minimum_upload_version"] != EXPECTED_MINIMUM_VERSION:
            raise AssertionError(
                f"Worker minimum version {config['minimum_upload_version']} does not match "
                f"the expected rollout floor {EXPECTED_MINIMUM_VERSION}."
            )
        if not config["test_auth"]:
            raise AssertionError("Disposable Community Worker test authentication is disabled.")
        if config.get("modern_upload_client_required"):
            raise AssertionError("The compatibility bridge is disabled in the disposable rollout test.")
        expected_environment = os.environ.get("KFPS_COMMUNITY_EXPECTED_ENVIRONMENT", "local-e2e")
        if config.get("deployment_environment") != expected_environment:
            raise AssertionError(
                f"Expected {expected_environment!r}, received {config.get('deployment_environment')!r}."
            )

    def test_complete_qt_client_workflow(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            folder = Path(temporary)
            source = folder / "CommunityWorkflow.json"
            variant = int(uuid.uuid4().hex[:8], 16)
            write_design(source, variant)
            service = create_service(folder, source)
            try:
                username = connect_test_account(service, "QtFlow")
                set_scope(service, "browse")
                self.assertTrue(wait_for(lambda: service.totalCount >= 16 and not service.busy), service.errorMessage)

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
                artwork_id = service.selectedArtwork["id"]
                self.assertIn("/thumbnail", service.selectedArtwork.get("thumbnailUrl", ""))
                self.assertEqual(service.selectedArtwork.get("gamesText"), "FH6")
                self.assertEqual(service.selectedArtwork.get("schemaId"), "kfps-primitives")
                self.assertTrue(service.selectedArtwork.get("schemaKnown"))
                self.assertEqual(service.selectedArtwork.get("classification"), "toolmade")
                self.assertTrue(service.selectedMetadataEditable)

                service.updateSelectedTags("automated, integration, retagged")
                self.assertTrue(wait_for(
                    lambda: "retagged" in service.selectedArtwork.get("tagsText", "") and not service.busy
                ), service.errorMessage)

                service.submitUpload(
                    title + " Duplicate", "Duplicate test.", "Original Artwork", "automated",
                    "toolmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: "already" in service.errorMessage.lower() and not service.busy
                ), service.errorMessage)
                service.clearError()

                service.favoriteSelected()
                self.assertTrue(wait_for(
                    lambda: service.selectedArtwork.get("favorited") is True and not service.busy
                ), service.errorMessage)
                service.downloadSelected()
                self.assertTrue(wait_for(lambda: bool(service.downloadedPath) and not service.busy), service.errorMessage)
                downloaded = Path(service.downloadedPath)
                canonical = json.loads(downloaded.read_text(encoding="utf-8"))
                self.assertEqual(canonical["format"], "kfps.community.v1")
                self.assertNotIn("private_path", json.dumps(canonical))
                manifest = json.loads(downloaded.with_suffix(".community.manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["source_schema"], "kfps-primitives")
                self.assertTrue(manifest["schema_known"])
                self.assertTrue(downloaded.with_suffix(".png").is_file())

                write_design(source, variant + 1)
                service.chooseUploadJson()
                self.assertTrue(wait_for(
                    lambda: service.uploadReady and service._upload_inspection.source_sha256
                    != service._rows[service.selectedIndex].get("contentSha256", "") and not service.busy
                ), service.errorMessage)
                service.submitRevision(
                    title, "Revised end-to-end client test.", "Original Artwork", "automated, revision",
                    "toolmade", "kfps-community-share-v1", False, True, False, "Adjusted one accent color.",
                )
                self.assertTrue(wait_for(
                    lambda: service.uploadStatus.startswith("Revision 2") and not service.busy
                ), service.errorMessage)

                service.setSearchQuery(title)
                set_scope(service, "toolmade")
                self.assertTrue(wait_for(
                    lambda: any(row.get("id") == artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                set_scope(service, "handmade")
                self.assertTrue(wait_for(
                    lambda: all(row.get("id") != artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.setSearchQuery("")
                set_scope(service, "browse")
                self.assertTrue(wait_for(
                    lambda: service.totalCount > 1 and any(row.get("creatorName") != username for row in service._rows)
                    and not service.busy
                ), service.errorMessage)
                other_index = next(i for i, row in enumerate(service._rows) if row.get("creatorName") != username)
                service.selectArtwork(other_index)
                other_creator = service.selectedArtwork["creatorName"]
                service.loadCreator(other_creator)
                self.assertTrue(wait_for(
                    lambda: service.creatorProfile.get("username") == other_creator and not service.busy
                ), service.errorMessage)
                service.followSelectedCreator()
                self.assertTrue(wait_for(
                    lambda: service.selectedArtwork.get("creatorFollowed") is True and not service.busy
                ), service.errorMessage)
                service.reportSelected("other", "Automated local moderation queue test.")
                self.assertTrue(wait_for(
                    lambda: service.statusMessage == "Report submitted privately and highlighted for moderation."
                    and not service.busy
                ), service.errorMessage)

                set_scope(service, "mine")
                self.assertTrue(wait_for(
                    lambda: any(row.get("id") == artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.selectArtwork(next(i for i, row in enumerate(service._rows) if row.get("id") == artwork_id))
                service.removeSelectedUpload()
                self.assertTrue(wait_for(
                    lambda: all(row.get("id") != artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)

                service.chooseUploadJson()
                self.assertTrue(wait_for(lambda: service.uploadReady and not service.busy), service.errorMessage)
                restored_title = title + " Restored"
                service.submitUpload(
                    restored_title, "Owner resubmission test.", "Original Artwork", "automated, restored",
                    "toolmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: service.selectedArtwork.get("id") == artwork_id
                    and service.selectedArtwork.get("title") == restored_title and not service.busy
                ), service.errorMessage)
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

    def test_supporter_access_uses_a_disposable_signed_entitlement(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            folder = Path(temporary)
            source = folder / "SupporterWorkflow.json"
            write_design(source, int(uuid.uuid4().hex[:8], 16))
            service = create_service(folder, source)
            try:
                account_entitlement: dict | None = None

                def deliver_entitlement(requested_subject: str) -> None:
                    nonlocal account_entitlement
                    if account_entitlement is None:
                        account_entitlement = issue_supporter_entitlement(requested_subject)
                    service.applySupporterEntitlement({
                        "ok": True,
                        "subject": requested_subject,
                        "entitlement": account_entitlement,
                    })

                service.supporterEntitlementRequested.connect(deliver_entitlement)
                service.setLocalSupporterState("active", True)
                connect_test_account(service, "SupporterFlow")
                subject = str(service.sessionUser.get("id") or "")
                self.assertTrue(subject)
                self.assertTrue(wait_for(lambda: service.supporterAccess and not service.busy), service.supporterStatus)

                service.chooseUploadJson()
                self.assertTrue(wait_for(lambda: service.uploadReady and not service.busy), service.errorMessage)
                title = "Supporter Workflow " + uuid.uuid4().hex[:8]
                service.submitUpload(
                    title, "Supporter access E2E test.", "Original Artwork", "supporter, automated",
                    "handmade", "kfps-community-share-v1", True, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: service.selectedArtwork.get("title") == title
                    and service.selectedArtwork.get("supporterOnly") is True and not service.busy
                ), service.errorMessage)
                artwork_id = service.selectedArtwork["id"]

                service.setLocalSupporterState("no_key", False)
                self.assertFalse(service.supporterAccess)
                service.downloadSelected()
                self.assertIn("supporter", service.errorMessage.lower())

                service.setLocalSupporterState("active", True)
                self.assertTrue(wait_for(lambda: service.supporterAccess and not service.busy), service.supporterStatus)
                set_scope(service, "mine")
                self.assertTrue(wait_for(
                    lambda: any(row.get("id") == artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
                service.selectArtwork(next(i for i, row in enumerate(service._rows) if row.get("id") == artwork_id))
                service.removeSelectedUpload()
                self.assertTrue(wait_for(
                    lambda: all(row.get("id") != artwork_id for row in service._rows) and not service.busy
                ), service.errorMessage)
            finally:
                service.close()
                APP.processEvents()

    def test_stale_client_and_invalid_files_are_rejected_without_publication(self):
        client = CommunityApiClient(API)
        before = int(client.json("artworks?limit=1").get("total") or 0)
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            folder = Path(temporary)
            source = folder / "RejectedWorkflow.json"
            write_design(source, int(uuid.uuid4().hex[:8], 16))
            service = create_service(folder, source, app_version="0.0.1")
            try:
                connect_test_account(service, "RejectedFlow")
                service.chooseUploadJson()
                self.assertTrue(wait_for(lambda: service.uploadReady and not service.busy), service.errorMessage)
                service.submitUpload(
                    "Stale Workflow " + uuid.uuid4().hex[:8], "Must be rejected.", "Original Artwork", "stale",
                    "toolmade", "kfps-community-share-v1", False, True, False,
                )
                self.assertTrue(wait_for(
                    lambda: EXPECTED_MINIMUM_VERSION in service.errorMessage and "or newer" in service.errorMessage.lower()
                    and not service.busy
                ), service.errorMessage)
                service.clearError()

                source.write_text("{not valid json", encoding="utf-8")
                service.chooseUploadJson()
                self.assertTrue(wait_for(
                    lambda: bool(service.errorMessage) and not service.busy
                ), "Invalid JSON was not rejected by KFPS.")
                self.assertFalse(service.uploadReady)
            finally:
                service.close()
                APP.processEvents()
        after = int(client.json("artworks?limit=1").get("total") or 0)
        self.assertEqual(after, before)

    def test_pre_classification_client_can_upload_during_rollout_bridge(self):
        test_root = ROOT / "runtime" / "community-tests"
        test_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=test_root) as temporary:
            folder = Path(temporary)
            source = folder / "LegacyCommunityWorkflow.json"
            write_design(source, int(uuid.uuid4().hex[:8], 16))
            service = create_service(folder, source)
            try:
                connect_test_account(service, "LegacyFlow")
                service.chooseUploadJson()
                self.assertTrue(wait_for(lambda: service.uploadReady and not service.busy), service.errorMessage)
                payload = service._upload_payload(
                    "Legacy Workflow " + uuid.uuid4().hex[:8],
                    "Pre-classification KFPS compatibility test.",
                    "Original Artwork",
                    "legacy, automated",
                    "toolmade",
                    "kfps-community-share-v1",
                    False,
                    True,
                    False,
                )
                for field in ("client_version", "classification", "supporter_only"):
                    payload.pop(field, None)
                client = CommunityApiClient(API, service._token)
                result = client.json("artworks", "POST", payload, authenticated=True)
                artwork = dict(result.get("artwork") or {})
                self.assertEqual(artwork.get("classification"), "toolmade")
                self.assertFalse(artwork.get("supporter_only", False))
                self.assertTrue(artwork.get("id"))
                client.json(f"artworks/{artwork['id']}", "DELETE", authenticated=True)

                payload["client_version"] = "3.1.42"
                payload["classification"] = "toolmade"
                result = client.json("artworks", "POST", payload, authenticated=True)
                restored = dict(result.get("artwork") or {})
                self.assertEqual(restored.get("id"), artwork.get("id"))
                self.assertEqual(restored.get("classification"), "toolmade")
                client.json(f"artworks/{restored['id']}", "DELETE", authenticated=True)
            finally:
                service.close()
                APP.processEvents()


if __name__ == "__main__":
    unittest.main()
