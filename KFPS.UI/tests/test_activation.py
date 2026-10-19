from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtNetwork import QNetworkRequest

from kfps_ui import activation_crypto
from kfps_ui.activation_client import ActivationClient
from kfps_ui.activation_crypto import (
    RsaPublicKey,
    SupporterKey,
    b64url_encode,
    canonical_payload,
    derive_activation_key_id,
    verify_activation_decision,
    verify_activation_receipt,
    verify_activation_status,
    verify_community_entitlement,
)
from kfps_ui.activation_storage import (
    ActivationStorageError,
    ActivationStore,
    DpapiProtector,
    PlaintextTestProtector,
    derive_device_id,
    encode_receipt,
)
from kfps_ui.supporter_service import SupporterService


APP = QCoreApplication.instance() or QCoreApplication([])
TEST_N = int(
    "bba79163a4fb96b7b52c3d3105ff49c81d5ba1405c08ba2d5176e78cb3b22b14"
    "b42187249b0c877ae2cd40006bee3adbf15cdf3afcb906e58d392485e7df056c1a45"
    "31c4d99181898591d378cf59b5d629ca9a1291d1320b0a504a73f7c65bcf99f55"
    "44101a0b4c80cd283ec564c60407a5f0b7cff85c2bfc8b72d7f715728ff",
    16,
)
TEST_D = int(
    "5db26e8ad56ef5b36697df39e227b4dc61a445e08fd39fba4f09d2d5d347abf11"
    "b7bfe318de574a42c2895c36020c46cdb9826b21a4bfca093a22b955cd063b0da8"
    "30eca87041c4f7cd0d2df29f16760879962fd5e40a6566dca0f3f984150350a156"
    "9e4ee35f6d163a982849f0174f33684a87347f489cc8b9c75ab52ba70f9",
    16,
)
TEST_PUBLIC_KEY = RsaPublicKey(f"{TEST_N:x}", 65537)


def sign_test_envelope(envelope_type: str, payload: dict) -> dict:
    message = canonical_payload(payload)
    digest_info = activation_crypto.SHA256_DIGESTINFO_PREFIX + hashlib.sha256(message).digest()
    key_size = (TEST_N.bit_length() + 7) // 8
    encoded = b"\x00\x01" + b"\xff" * (key_size - len(digest_info) - 3) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), TEST_D, TEST_N).to_bytes(key_size, "big")
    return {
        "type": envelope_type,
        "version": 1,
        "kid": activation_crypto.ACTIVATION_KEY_ID,
        "payload": b64url_encode(message),
        "signature": b64url_encode(signature),
    }


class FakeClient(QObject):
    completed = Signal(object)

    def __init__(self):
        super().__init__()
        self.configured = True
        self.requests = []

    def activate(self, **payload):
        self.requests.append(("activate", payload))

    def deactivate(self, **payload):
        self.requests.append(("deactivate", payload))

    def status(self, **payload):
        self.requests.append(("status", payload))

    def community_entitlement(self, **payload):
        self.requests.append(("community-entitlement", payload))


class PendingReply(QObject):
    finished = Signal()


class RecordingNetworkManager:
    def __init__(self):
        self.request = None

    def post(self, request, _payload):
        self.request = request
        return PendingReply()


def fake_key(path: Path) -> SupporterKey:
    payload = {"supporter_name": "Test", "entitlements": ["supporter_theme"]}
    payload_bytes = canonical_payload(payload)
    signature = bytes(range(256)) + bytes(range(128))
    return SupporterKey(
        path=path,
        payload=payload,
        payload_bytes=payload_bytes,
        signature=signature,
        key_id=derive_activation_key_id(payload_bytes, signature),
        signature_sha256=hashlib.sha256(signature).hexdigest(),
        key_proof=b64url_encode(signature),
    )


def wait_for_request(client: FakeClient, count: int = 1):
    deadline = time.monotonic() + 2
    while len(client.requests) < count and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(0.005)
    return len(client.requests) >= count


class ActivationTests(unittest.TestCase):
    def make_service(self, root: Path, *, clock=lambda: 1000.0):
        key = fake_key(root / "Test.kfpskey")
        client = FakeClient()
        store = ActivationStore(root / "private-state", PlaintextTestProtector())
        service = SupporterService(
            root,
            store=store,
            client=client,
            endpoint="http://127.0.0.1:8787",
            enforce_activation=True,
            clock=clock,
        )
        self.addCleanup(service.close)
        service._payload = key.payload
        service._key = key
        service._evaluate_local_activation()
        return key, client, store, service

    def test_key_id_is_stable_for_the_same_signed_material(self):
        payload = b'{"schema":"kfps.supporter.v1"}'
        signature = b"signed" * 64
        self.assertEqual(
            derive_activation_key_id(payload, signature),
            derive_activation_key_id(payload, signature),
        )
        self.assertNotEqual(
            derive_activation_key_id(payload, signature),
            derive_activation_key_id(payload + b" ", signature),
        )

    def test_activation_client_accepts_only_an_exact_secure_or_local_origin(self):
        for endpoint in (
            "https://activation.example.test",
            "https://activation.example.test:443/",
            "http://127.0.0.1:8787",
            "http://localhost:8787/",
        ):
            self.assertTrue(ActivationClient(endpoint).configured, endpoint)
        for endpoint in (
            "http://activation.example.test",
            "https://user:pass@activation.example.test",
            "https://activation.example.test/v1",
            "https://activation.example.test?target=other",
            "https://activation.example.test#fragment",
        ):
            self.assertFalse(ActivationClient(endpoint).configured, endpoint)

    def test_activation_client_never_follows_redirects(self):
        client = ActivationClient("https://activation.example.test")
        manager = RecordingNetworkManager()
        client._manager = manager
        client.activate(key_id="a" * 64, key_proof="proof", device_id="b" * 64, nonce="nonce")
        self.assertEqual(
            manager.request.attribute(QNetworkRequest.RedirectPolicyAttribute),
            QNetworkRequest.ManualRedirectPolicy,
        )

    def test_dpapi_payload_model_keeps_identity_and_receipts_separate(self):
        with tempfile.TemporaryDirectory() as td:
            try:
                protector = DpapiProtector()
            except ActivationStorageError as exc:
                self.skipTest(str(exc))
            root = Path(td) / "H\u00e9stia \u6e2c\u8a66" / "activation state"
            store = ActivationStore(root, protector)
            secret, device_id = store.load_or_create_identity()
            self.assertEqual(device_id, derive_device_id(secret))
            store.save_key_state("a" * 64, {"receipt": "opaque", "grace_started_at": 1})
            self.assertEqual(store.key_state("a" * 64)["receipt"], "opaque")
            self.assertNotIn(b"opaque", (root / "activation.dat").read_bytes())
            self.assertEqual(store.load_or_create_identity()[1], device_id)

    def test_damaged_identity_does_not_silently_create_a_new_device(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = ActivationStore(root, PlaintextTestProtector())
            store.load_or_create_identity()
            (root / "identity.dat").write_bytes(b"damaged")
            with self.assertRaises(ActivationStorageError):
                store.load_or_create_identity()

    def test_receipt_decision_and_status_are_bound_to_request_values(self):
        key_id = "1" * 64
        device_id = "2" * 64
        nonce = b64url_encode(b"n" * 32)
        receipt = sign_test_envelope("kfps.supporter.activation", {
            "activated_at": "2026-07-13T12:00:00.000Z",
            "device_id": device_id,
            "key_id": key_id,
            "schema": "kfps.activation.v1",
        })
        decision = sign_test_envelope("kfps.supporter.activation-decision", {
            "decided_at": "2026-07-13T12:00:01.000Z",
            "device_id": device_id,
            "key_id": key_id,
            "nonce": nonce,
            "schema": "kfps.activation.decision.v1",
            "status": "already_activated",
        })
        status = sign_test_envelope("kfps.supporter.activation-status", {
            "checked_at": "2026-07-13T12:00:02.000Z",
            "device_id": device_id,
            "key_id": key_id,
            "nonce": nonce,
            "schema": "kfps.activation.status.v1",
            "status": "revoked",
        })
        with patch.object(activation_crypto, "ACTIVATION_PUBLIC_KEY", TEST_PUBLIC_KEY):
            self.assertIsNotNone(verify_activation_receipt(receipt, key_id=key_id, device_id=device_id)[0])
            self.assertIsNone(verify_activation_receipt(receipt, key_id="3" * 64, device_id=device_id)[0])
            self.assertIsNotNone(verify_activation_decision(decision, key_id=key_id, device_id=device_id, nonce=nonce)[0])
            self.assertIsNone(verify_activation_decision(decision, key_id=key_id, device_id=device_id, nonce="wrong")[0])
            self.assertIsNotNone(verify_activation_status(status, key_id=key_id, device_id=device_id, nonce=nonce)[0])
            self.assertIsNone(verify_activation_status(status, key_id=key_id, device_id=device_id, nonce="wrong")[0])

    def test_community_entitlement_is_signed_short_lived_and_request_bound(self):
        subject = "11111111-1111-4111-8111-111111111111"
        nonce = b64url_encode(b"n" * 32)
        issued = datetime.fromtimestamp(1000, timezone.utc).isoformat().replace("+00:00", "Z")
        expires = datetime.fromtimestamp(1900, timezone.utc).isoformat().replace("+00:00", "Z")
        envelope = sign_test_envelope("kfps.supporter.community-entitlement", {
            "audience": "kfps-community-v1",
            "entitlement_id": "22222222-2222-4222-8222-222222222222",
            "expires_at": expires,
            "issued_at": issued,
            "nonce": nonce,
            "schema": "kfps.community.supporter.v1",
            "subject": subject,
        })
        with patch.object(activation_crypto, "ACTIVATION_PUBLIC_KEY", TEST_PUBLIC_KEY):
            verified, error = verify_community_entitlement(
                envelope, subject=subject, nonce=nonce, now=1000,
            )
            self.assertEqual(error, "")
            self.assertEqual(verified["subject"], subject)
            self.assertIsNone(verify_community_entitlement(
                envelope, subject="33333333-3333-4333-8333-333333333333", nonce=nonce, now=1000,
            )[0])
            self.assertIsNone(verify_community_entitlement(
                envelope, subject=subject, nonce=nonce, now=1901,
            )[0])

    def test_active_service_requests_only_a_signed_community_entitlement(self):
        with tempfile.TemporaryDirectory() as td:
            key, client, _store, service = self.make_service(Path(td), clock=lambda: 1000.0)
            service._activation_state = "active"
            service._access_allowed = True
            subject = "11111111-1111-4111-8111-111111111111"
            received = []
            service.communityEntitlementReady.connect(received.append)
            service.requestCommunityEntitlement(subject)
            self.assertTrue(wait_for_request(client))
            operation, request = client.requests[-1]
            self.assertEqual(operation, "community-entitlement")
            self.assertEqual(request["community_subject"], subject)
            self.assertEqual(request["key_id"], key.key_id)
            entitlement = sign_test_envelope("kfps.supporter.community-entitlement", {
                "audience": "kfps-community-v1",
                "entitlement_id": "22222222-2222-4222-8222-222222222222",
                "expires_at": datetime.fromtimestamp(1900, timezone.utc).isoformat().replace("+00:00", "Z"),
                "issued_at": datetime.fromtimestamp(1000, timezone.utc).isoformat().replace("+00:00", "Z"),
                "nonce": request["nonce"],
                "schema": "kfps.community.supporter.v1",
                "subject": subject,
            })
            with patch.object(activation_crypto, "ACTIVATION_PUBLIC_KEY", TEST_PUBLIC_KEY):
                client.completed.emit({
                    "operation": operation,
                    "nonce": request["nonce"],
                    "http_status": 200,
                    "network_error": "",
                    "parse_error": "",
                    "body": {"status": "active", "entitlement": entitlement},
                })
            self.assertTrue(received)
            self.assertTrue(received[-1]["ok"])
            self.assertEqual(received[-1]["subject"], subject)
            payload = json.loads(activation_crypto.b64url_decode(entitlement["payload"]).decode("utf-8"))
            self.assertNotIn("key_id", payload)
            self.assertNotIn("device_id", payload)

    def test_missing_community_entitlement_route_has_a_clear_message(self):
        with tempfile.TemporaryDirectory() as td:
            _key, client, _store, service = self.make_service(Path(td), clock=lambda: 1000.0)
            service._activation_state = "active"
            service._access_allowed = True
            subject = "11111111-1111-4111-8111-111111111111"
            received = []
            service.communityEntitlementReady.connect(received.append)
            service.requestCommunityEntitlement(subject)
            self.assertTrue(wait_for_request(client))
            operation, request = client.requests[-1]
            client.completed.emit({
                "operation": operation,
                "nonce": request["nonce"],
                "http_status": 404,
                "network_error": "",
                "parse_error": "",
                "body": {"error": "not_found"},
            })
            self.assertTrue(received)
            self.assertFalse(received[-1]["ok"])
            self.assertEqual(received[-1]["code"], "not_found")
            self.assertIn("migration service needs an update", received[-1]["message"])
            self.assertNotIn("Signed activation response", received[-1]["message"])


if __name__ == "__main__":
    unittest.main()
