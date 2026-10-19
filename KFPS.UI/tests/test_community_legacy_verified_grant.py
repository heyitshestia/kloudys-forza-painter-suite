from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import test_activation as fixtures
from kfps_ui import activation_crypto as crypto

SUBJECT = "11111111-1111-4111-8111-111111111111"
ENTITLEMENT = "22222222-2222-4222-8222-222222222222"
GRANT_TYPE = "kfps.community.legacy-verified-grant"
NONCE = crypto.b64url_encode(b"n" * 32)


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def signed_pair(nonce=NONCE):
    payload = dict(schema="kfps.community.supporter.v1", audience="kfps-community-v1", subject=SUBJECT,
                   entitlement_id=ENTITLEMENT, nonce=nonce, issued_at=iso(1000), expires_at=iso(1900))
    entitlement = fixtures.sign_test_envelope("kfps.supporter.community-entitlement", payload)
    payload.update(schema="kfps.community.legacy-verified.v1", audience="kfps-community-verified-v1",
                   license_created_at=iso(100), eligibility_cutoff=iso(500))
    return entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload)


def decoded(envelope):
    return json.loads(crypto.b64url_decode(envelope["payload"]))


class LegacyGrantCryptoTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.object(crypto, "ACTIVATION_PUBLIC_KEY", fixtures.TEST_PUBLIC_KEY)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def verify(self, entitlement, grant, **kwargs):
        return crypto.verify_community_legacy_verified_grant(
            grant, entitlement=entitlement, subject=SUBJECT, nonce=NONCE, now=kwargs.get("now", 1000))

    def test_exact_signed_pair_and_inclusive_cutoff(self):
        entitlement, grant = signed_pair()
        self.assertEqual(self.verify(entitlement, grant), (decoded(grant), ""))
        payload = decoded(grant)
        payload["license_created_at"] = payload["eligibility_cutoff"] = payload["issued_at"]
        self.assertIsNotNone(self.verify(entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload))[0])

    def test_each_binding_must_match_the_accompanying_signed_entitlement(self):
        entitlement, grant = signed_pair()
        mutations = {"subject": "33333333-3333-4333-8333-333333333333",
                     "entitlement_id": "44444444-4444-4444-8444-444444444444", "nonce": "other-request",
                     "issued_at": iso(999), "expires_at": iso(1899)}
        for field, value in mutations.items():
            with self.subTest(field=field):
                payload = decoded(grant)
                payload[field] = value
                self.assertIsNone(self.verify(entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload))[0])

    def test_payload_shape_schema_audience_and_order_are_strict(self):
        entitlement, grant = signed_pair()
        for field, value in (("schema", "kfps.community.supporter.v1"), ("audience", "other"),
                             ("extra", "value"), ("license_created_at", None), ("eligibility_cutoff", True),
                             ("license_created_at", iso(501)), ("eligibility_cutoff", iso(1001))):
            with self.subTest(field=field, value=value):
                payload = decoded(grant)
                payload[field] = value
                self.assertIsNone(self.verify(entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload))[0])
        for field in decoded(grant):
            with self.subTest(missing=field):
                payload = decoded(grant)
                del payload[field]
                self.assertIsNone(self.verify(entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload))[0])

    def test_timestamp_form_and_real_calendar_are_strict(self):
        entitlement, grant = signed_pair()
        for value in ("1970-01-01", "1970-01-01T00:01:40Z", "1970-01-01T00:01:40.000+00:00",
                      "1970-01-01T00:01:40.0000Z", "1970-01-01T00:01:40.000z", "1970-02-30T00:00:00.000Z",
                      "1970-01-01T24:00:00.000Z", "0000-01-01T00:00:00.000Z", " 1970-01-01T00:01:40.000Z"):
            for field in ("license_created_at", "eligibility_cutoff"):
                with self.subTest(field=field, value=value):
                    payload = decoded(grant)
                    payload[field] = value
                    self.assertIsNone(self.verify(entitlement, fixtures.sign_test_envelope(GRANT_TYPE, payload))[0])

    def test_bad_envelopes_signatures_and_uncanonical_encodings_fail(self):
        entitlement, grant = signed_pair()
        for bad in (None, [], "grant", {}, {**grant, "extra": 1}, {**grant, "version": True},
                    {**grant, "kid": "other"}, {**grant, "type": "other"}, {**grant, "signature": "AA"},
                    {**grant, "payload": grant["payload"] + "="}, {**grant, "payload": "A" * 10000}):
            with self.subTest(bad=repr(bad)[:100]):
                self.assertIsNone(self.verify(entitlement, bad)[0])
        forged = copy.deepcopy(grant)
        payload = decoded(grant)
        payload["license_created_at"] = iso(10)
        forged["payload"] = crypto.b64url_encode(crypto.canonical_payload(payload))
        self.assertIsNone(self.verify(entitlement, forged)[0])

    def test_base_entitlement_must_itself_verify_and_be_fresh(self):
        entitlement, grant = signed_pair()
        for base in (None, {**entitlement, "signature": "AA"}, grant):
            self.assertIsNone(self.verify(base, grant)[0])
        for now in (879, 1900, 9999):
            self.assertIsNone(self.verify(entitlement, grant, now=now)[0])
        self.assertIsNone(crypto.verify_community_legacy_verified_grant(
            grant, entitlement=entitlement, subject=SUBJECT, nonce="fresh-request", now=1000)[0])

    def test_matching_but_non_schema_nonce_is_rejected(self):
        for nonce in ("short", "a" * 87, "=" * 43, True, ["not-a-string"]):
            with self.subTest(nonce=nonce):
                entitlement, grant = signed_pair(nonce)
                self.assertIsNone(crypto.verify_community_legacy_verified_grant(
                    grant, entitlement=entitlement, subject=SUBJECT, nonce=nonce, now=1000)[0])


class LegacyGrantServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key, self.client, self.store, self.service = fixtures.ActivationTests.make_service(self, Path(self.temp.name))
        self.service._activation_state = "active"
        self.service._access_allowed = True
        self.received = []
        self.service.communityEntitlementReady.connect(self.received.append)
        self.key_patch = patch.object(crypto, "ACTIVATION_PUBLIC_KEY", fixtures.TEST_PUBLIC_KEY)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def request(self):
        count = len(self.client.requests) + 1
        self.service.requestCommunityEntitlement(SUBJECT)
        self.assertTrue(fixtures.wait_for_request(self.client, count))
        operation, request = self.client.requests[-1]
        entitlement, grant = signed_pair(request["nonce"])
        return {"operation": operation, "nonce": request["nonce"], "http_status": 200,
                "network_error": "", "parse_error": "", "body": {
                    "status": "active", "entitlement": entitlement, "legacy_verified_grant": grant}}

    def test_success_forwards_original_envelopes_and_does_not_persist_or_unlock(self):
        result = self.request()
        before = self.store.key_state(self.key.key_id).copy()
        self.client.completed.emit(result)
        self.assertEqual(self.received, [{"ok": True, "subject": SUBJECT, **{
            key: result["body"][key] for key in ("entitlement", "legacy_verified_grant")}}])
        self.assertEqual(self.store.key_state(self.key.key_id), before)
        self.assertEqual(self.service._activation_state, "active")
        self.assertTrue(self.service._access_allowed)

    def test_old_response_without_grant_stays_successful(self):
        result = self.request()
        del result["body"]["legacy_verified_grant"]
        self.client.completed.emit(result)
        self.assertTrue(self.received[-1]["ok"])
        self.assertNotIn("legacy_verified_grant", self.received[-1])

    def test_present_invalid_or_mismatched_grant_fails_without_affecting_theme_activation(self):
        for kind in ("null", "forged", "different_nonce", "different_id"):
            with self.subTest(kind=kind):
                result = self.request()
                grant = result["body"]["legacy_verified_grant"]
                if kind == "null": grant = None
                elif kind == "forged": grant["signature"] = "AA"
                else:
                    payload = decoded(grant)
                    payload["nonce" if kind == "different_nonce" else "entitlement_id"] = (
                        "other" if kind == "different_nonce" else "33333333-3333-4333-8333-333333333333")
                    grant = fixtures.sign_test_envelope(GRANT_TYPE, payload)
                result["body"]["legacy_verified_grant"] = grant
                self.client.completed.emit(result)
                self.assertFalse(self.received[-1]["ok"])
                self.assertNotIn("legacy_verified_grant", self.received[-1])
                self.assertEqual(self.service._activation_state, "active")
                self.assertTrue(self.service._access_allowed)

    def test_replayed_old_result_does_not_consume_new_inflight_request(self):
        old = self.request()
        self.client.completed.emit(old)
        current = self.request()
        self.client.completed.emit(old)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.service._inflight_operation, "community-entitlement")
        self.client.completed.emit(current)
        self.assertEqual(len(self.received), 2)
        self.assertTrue(self.received[-1]["ok"])
        self.client.completed.emit(current)
        self.assertEqual(len(self.received), 2)

    def test_current_metadata_does_not_authorize_an_old_signed_pair(self):
        old = self.request()
        self.client.completed.emit(old)
        current = self.request()
        current["body"] = old["body"]
        self.client.completed.emit(current)
        self.assertFalse(self.received[-1]["ok"])


if __name__ == "__main__":
    unittest.main()
