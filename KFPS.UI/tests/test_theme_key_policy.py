from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import test_activation as fixtures
from kfps_ui import activation_crypto as crypto
from kfps_ui.supporter_service import SupporterService


class ThemeKeyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.client = fixtures.FakeClient()
        self.store = Mock()
        self.store.load_or_create_identity.side_effect = AssertionError("must not read device identity")
        self.store.key_state.side_effect = AssertionError("must not read old activation state")
        self.patch = patch.object(crypto, "SUPPORTER_PUBLIC_KEY", fixtures.TEST_PUBLIC_KEY)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def key_file(self, name="existing.kfpskey", **fields):
        payload = {"schema": "kfps.supporter.v1", "supporter_name": "Synthetic",
                   "entitlements": ["supporter_theme", "all_features"], **fields}
        envelope = fixtures.sign_test_envelope("kfps.supporter.unlock", payload)
        path = self.root / name
        path.write_text(json.dumps(envelope), encoding="utf-8")
        return path

    def service(self):
        result = SupporterService(self.root, store=self.store, client=self.client,
                                  endpoint="http://127.0.0.1:8787", enforce_activation=True)
        self.addCleanup(result.close)
        return result

    def test_valid_key_needs_no_pc_identity_or_network_even_when_old_enforcement_is_true(self):
        self.key_file()
        service = self.service()
        service.startActivation()
        service.repairActivation()
        service.deactivateDevice()
        fixtures.APP.processEvents()
        self.assertTrue(service.unlocked)
        self.assertFalse(service.canDeactivate)
        self.assertFalse(service.canRepair)
        self.assertEqual([], self.client.requests)
        self.assertEqual([], self.store.mock_calls)
        self.assertFalse(service.problemVisible)

    def test_key_only_grants_the_theme_entitlement(self):
        self.key_file()
        service = self.service()
        self.assertEqual(["supporter_theme"], service.entitlements)
        self.assertTrue(service.hasEntitlement("supporter_theme"))
        for value in ("all_features", "supporter", "community", "bulk_import", "", "verified"):
            self.assertFalse(service.hasEntitlement(value), value)

    def test_old_device_and_duplicate_state_is_preserved_and_irrelevant_across_restart(self):
        self.key_file()
        old = self.root / "private-state"
        old.mkdir()
        data = b"old encrypted identity and revoked/duplicate receipt; intentionally unreadable"
        (old / "activation.dat").write_bytes(data)
        for _ in range(2):
            service = self.service()
            self.assertTrue(service.unlocked)
            service.close()
        self.assertEqual(data, (old / "activation.dat").read_bytes())
        self.assertEqual([], self.store.mock_calls)

    def test_tampered_key_does_not_unlock_themes(self):
        path = self.key_file()
        envelope = json.loads(path.read_text())
        envelope["signature"] = "AAAA"
        path.write_text(json.dumps(envelope))
        self.assertFalse(self.service().unlocked)
        self.assertEqual([], self.store.mock_calls)

    def test_no_key_or_unrelated_entitlement_does_not_unlock(self):
        self.assertFalse(self.service().unlocked)
        self.key_file(entitlements=["all_features"])
        self.assertFalse(self.service().unlocked)

    def test_remove_affects_themes_only_and_never_sends_deactivation(self):
        self.key_file()
        service = self.service()
        service.removeKey()
        self.assertFalse(service.unlocked)
        self.assertEqual([], self.client.requests)
        self.assertEqual([], self.store.mock_calls)

    def test_legacy_file_is_read_in_place_without_migration_or_deletion(self):
        path = self.key_file()
        legacy = self.root / "runtime" / "supporter" / "supporter.kfpskey"
        legacy.parent.mkdir(parents=True)
        path.rename(legacy)
        before = legacy.read_bytes()
        self.assertTrue(self.service().unlocked)
        self.assertTrue(legacy.exists())
        self.assertEqual(before, legacy.read_bytes())
        self.assertFalse(list(self.root.glob("*.kfpskey")))

    def test_failed_legacy_removal_reports_failure_and_retains_actual_access(self):
        path = self.key_file()
        legacy = self.root / "runtime" / "supporter" / "supporter.kfpskey"
        legacy.parent.mkdir(parents=True)
        path.rename(legacy)
        service = self.service()
        unlink = Path.unlink
        def locked(candidate, *args, **kwargs):
            if candidate == legacy:
                raise PermissionError("synthetic file is locked")
            return unlink(candidate, *args, **kwargs)
        with patch.object(Path, "unlink", locked):
            service.removeKey()
        self.assertTrue(service.unlocked)
        self.assertTrue(service.problemVisible)
        self.assertIn("Could not remove", service.status)
        self.assertEqual("active", service.activationState)
        service.reload()
        self.assertTrue(service.unlocked)
        self.assertTrue(legacy.exists())
        self.assertEqual([], self.client.requests)

    def test_partial_removal_rechecks_the_key_remaining_on_disk(self):
        removable = self.key_file("removable.kfpskey")
        invalid = self.root / "invalid.kfpskey"
        invalid.write_text("{}")
        service = self.service()
        unlink = Path.unlink
        def locked(candidate, *args, **kwargs):
            if candidate == invalid:
                raise PermissionError("synthetic file is locked")
            return unlink(candidate, *args, **kwargs)
        with patch.object(Path, "unlink", locked):
            service.removeKey()
        self.assertFalse(removable.exists())
        self.assertTrue(invalid.exists())
        self.assertFalse(service.unlocked)
        self.assertTrue(service.problemVisible)
        self.assertIn("Could not remove", service.status)

    @unittest.skipUnless(__import__("os").name == "nt", "Windows file sharing test")
    def test_real_windows_locked_legacy_key_and_retry(self):
        import ctypes
        from ctypes import wintypes
        path = self.key_file()
        legacy = self.root / "runtime" / "supporter" / "supporter.kfpskey"
        legacy.parent.mkdir(parents=True)
        path.rename(legacy)
        service = self.service()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.CreateFileW(str(legacy), 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            service.removeKey()
            self.assertTrue(service.unlocked)
            self.assertTrue(service.problemVisible)
            self.assertIn("Could not remove", service.status)
            self.assertTrue(legacy.exists())
        finally:
            kernel.CloseHandle(handle)
        service.removeKey()
        self.assertFalse(service.unlocked)
        self.assertFalse(service.problemVisible)
        self.assertFalse(legacy.exists())
        self.assertEqual([], self.client.requests)

    def test_grandfather_request_has_no_device_identifier_and_cannot_revoke_theme_access(self):
        self.key_file()
        service = self.service()
        service.requestCommunityEntitlement("sha256:" + "a" * 64)
        operation, payload = self.client.requests[-1]
        self.assertEqual("community-entitlement", operation)
        self.assertNotIn("device_id", payload)
        self.client.completed.emit({"operation": operation, "nonce": payload["nonce"],
                                    "http_status": 403, "body": {"error": "not_eligible"}})
        self.assertTrue(service.unlocked)
        self.assertEqual([], self.store.mock_calls)

    def test_failed_import_does_not_revoke_existing_valid_theme_key(self):
        self.key_file()
        service = self.service()
        bad = self.root / "bad.json"
        bad.write_text("{}")
        with patch("kfps_ui.supporter_service.QFileDialog.getOpenFileName", return_value=(str(bad), "")):
            self.assertFalse(service.importKey())
        self.assertTrue(service.unlocked)

    def test_retired_activation_results_cannot_change_local_theme_access(self):
        self.key_file()
        service = self.service()
        for operation in ("activate", "deactivate", "status"):
            self.client.completed.emit({"operation": operation, "http_status": 200,
                                        "body": {"status": "revoked"}})
            self.assertTrue(service.unlocked)

    def test_actual_request_transport_omits_device_and_rejects_redirects(self):
        from kfps_ui.activation_client import ActivationClient
        from PySide6.QtNetwork import QNetworkRequest
        client = ActivationClient("http://127.0.0.1:8787")
        sent = []
        class Manager:
            def post(self, request, payload):
                sent.append((request, json.loads(bytes(payload))))
                return fixtures.PendingReply()
        client._manager = Manager()
        client.community_entitlement(key_id="a" * 64, key_proof="proof", nonce="nonce", community_subject="subject")
        request, payload = sent[0]
        self.assertNotIn("device_id", payload)
        self.assertEqual(set(payload), {"protocol", "key_id", "key_proof", "nonce", "community_subject"})
        self.assertEqual(request.attribute(QNetworkRequest.RedirectPolicyAttribute), QNetworkRequest.ManualRedirectPolicy)
        client._contexts.clear()
        client.close()

    def test_key_change_rejects_late_community_reply_without_locking_the_new_key(self):
        self.key_file()
        service = self.service()
        received = []
        service.communityEntitlementReady.connect(received.append)
        service.requestCommunityEntitlement("subject")
        operation, payload = self.client.requests[-1]
        self.key_file(supporter_name="Another synthetic holder")
        service.reload()
        self.client.completed.emit({"operation": operation, "nonce": payload["nonce"],
                                    "http_status": 200, "body": {}})
        self.assertEqual("key_changed", received[-1]["code"])
        self.assertTrue(service.unlocked)

    def test_removing_key_during_grant_request_does_not_accept_late_reply(self):
        self.key_file()
        service = self.service()
        received = []
        service.communityEntitlementReady.connect(received.append)
        service.requestCommunityEntitlement("subject")
        operation, payload = self.client.requests[-1]
        service.removeKey()
        self.client.completed.emit({"operation": operation, "nonce": payload["nonce"],
                                    "http_status": 200, "body": {}})
        self.assertEqual("key_changed", received[-1]["code"])
        self.assertFalse(service.unlocked)

    def test_closed_service_cannot_start_grant_request(self):
        self.key_file()
        service = self.service()
        service.close()
        service.requestCommunityEntitlement("subject")
        self.assertEqual([], self.client.requests)

    def test_import_revalidates_staged_bytes_before_replacing_existing_key(self):
        destination = self.key_file()
        before = destination.read_bytes()
        service = self.service()
        source = self.root / "external" / destination.name
        source.parent.mkdir()
        source.write_text("{}")
        self.assertFalse(service._install_key(source, {"entitlements": ["supporter_theme"]}, "valid"))
        self.assertEqual(before, destination.read_bytes())
        self.assertTrue(service.unlocked)
        self.assertFalse(list(self.root.glob("supporter-*.tmp")))


if __name__ == "__main__":
    unittest.main()
