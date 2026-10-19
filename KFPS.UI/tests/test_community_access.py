from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.community_access import (
    artwork_access, claim_request, claim_results, contribution_status, policy_mode,
    upload_access, verified_capability,
)
from kfps_ui.community_client import CommunityApiClient, CommunityApiError

SCHEMA = UI.parent / "tools/community_worker/contracts/verified-access-contract.schema.json"


def policy(mode="verified_v1"):
    return {"version": 1, "mode": mode, "required_own_vinyls": 10,
            "required_account_age_days": 14,
            "count_basis": "lifetime_own_handmade_vinyls", "own_claims_enabled": mode == "verified_v1"}


def capability(count=0, reason=None):
    active = (count >= 10 and reason is None) or reason == "grandfathered_supporter"
    unknown = reason in {"unsupported_identity", "connection_date_unavailable"}
    return {"policy_version": 1, "active": active, "eligible_vinyl_count": count,
            "required_account_age_days": 14, "connected_at": None if unknown else "2026-09-01T00:00:00.000Z",
            "eligible_after": None if unknown else "2026-09-15T00:00:00.000Z",
            "grandfathered_at": "2026-10-19T00:00:00.000Z" if reason == "grandfathered_supporter" else None,
            "required_count": 10, "reason": reason or ("eligible" if active else "contributions_required")}


def contribution(state="not_claimed", can_claim=True):
    return {"state": state, "can_claim": can_claim, "eligible_at": None, "credited_at": None}


class AccessContractTests(unittest.TestCase):
    def test_canonical_schema_is_the_accepted_artifact(self):
        self.assertEqual(hashlib.sha256(SCHEMA.read_bytes()).hexdigest(),
                         "0264de524a9273131ad71222214cb8b36dda680cb8bc808a04d06c847da5d7ee")
        definitions = json.loads(SCHEMA.read_text())["$defs"]
        self.assertEqual(set(policy()), set(definitions["AccessPolicy"]["required"]))
        self.assertEqual(set(capability()), set(definitions["VerifiedCapability"]["required"]))
        self.assertEqual(set(contribution()), set(definitions["ContributionStatus"]["required"]))
        for mode in definitions["AccessPolicy"]["properties"]["mode"]["enum"]:
            self.assertEqual(policy_mode({"access_policy": policy(mode)}), mode)

    def test_legacy_absence_is_not_verified(self):
        self.assertEqual(policy_mode({}), "legacy_supporter")
        self.assertEqual(verified_capability({}, "legacy_supporter"), {})
        self.assertEqual(upload_access("legacy_supporter", True, True, "vinyl", "own"), {"supporter_only": True})

    def test_unknown_malformed_and_partial_policy_fail_closed(self):
        for value in (None, [], {}, {**policy(), "version": 2}, {**policy(), "version": True},
                      {**policy(), "mode": "next"}, {**policy(), "mode": {}},
                      {**policy(), "own_claims_enabled": False}, {**policy(), "extra": 1}):
            with self.subTest(value=value):
                self.assertEqual(policy_mode({"access_policy": value}), "unsupported")

    def test_count_and_reason_are_server_capability_not_a_local_unlock(self):
        for count in (0, 9, 10, 11):
            parsed = verified_capability({"capabilities": {"verified": capability(count)}}, "verified_v1")
            self.assertEqual(parsed["active"], count >= 10)
        for reason in ("account_suspended", "unsupported_identity", "waiting_period", "connection_date_unavailable"):
            parsed = verified_capability({"capabilities": {"verified": capability(11, reason)}}, "verified_v1")
            self.assertFalse(parsed["active"])
        for bad in ({**capability(10), "active": False}, {**capability(9), "active": True},
                    {**capability(), "eligible_vinyl_count": True}, {**capability(), "reason": []}):
            with self.subTest(bad=bad):
                self.assertEqual(verified_capability({"capabilities": {"verified": bad}}, "verified_v1"), {})
        self.assertEqual(verified_capability({"capabilities": {"verified": capability(10)}}, "legacy_supporter"), {})

    def test_connection_dates_are_server_evidence_not_local_clock_unlock(self):
        waiting = capability(10, "waiting_period")
        with patch("time.time", return_value=10**12):
            self.assertFalse(verified_capability({"capabilities": {"verified": waiting}}, "verified_v1")["active"])
        for bad in ({**capability(10), "connected_at": None}, {**capability(10), "eligible_after": "bad"},
                    {**capability(10), "eligible_after": "2026-09-02T00:00:00Z"},
                    {**capability(10), "connected_at": "2026-09-01"}, {**capability(10), "required_account_age_days": 0}):
            self.assertEqual(verified_capability({"capabilities": {"verified": bad}}, "verified_v1"), {})

    def test_grandfather_grant_bypasses_count_and_age_but_not_suspension(self):
        granted = {**capability(0, "grandfathered_supporter"), "connected_at": None, "eligible_after": None}
        self.assertTrue(verified_capability({"capabilities": {"verified": granted}}, "verified_v1")["active"])
        suspended = {**granted, "active": False, "reason": "account_suspended"}
        self.assertFalse(verified_capability({"capabilities": {"verified": suspended}}, "verified_v1")["active"])
        for bad in ({**granted, "grandfathered_at": None}, {**granted, "grandfathered_at": "local-key-present"},
                    {**capability(10), "grandfathered_at": granted["grandfathered_at"]}):
            self.assertEqual(verified_capability({"capabilities": {"verified": bad}}, "verified_v1"), {})

    def test_access_flags_remain_independent(self):
        row = {"supporter_only": True, "access": {"audience": "verified", "can_view_media": True,
               "can_download": False, "can_interact": True, "restriction_reason": "unavailable"}}
        access = artwork_access(row, "verified_v1", True, True)
        self.assertTrue(access["can_view_media"])
        self.assertFalse(access["can_download"])
        self.assertTrue(access["can_interact"])
        for mode, auth, restricted in (("unsupported", True, True), ("verified_v1", True, False), ("verified_v1", False, False)):
            denied = artwork_access(row, mode, auth, restricted)
            self.assertFalse(any(denied[key] for key in ("can_view_media", "can_download", "can_interact")))
        self.assertFalse(artwork_access({}, "verified_v1", True, True)["can_download"])
        self.assertFalse(artwork_access({**row, "access": {**row["access"], "audience": "supporter"}}, "verified_v1", True, True)["can_view_media"])

    def test_verified_uploads_require_explicit_authorship_but_liveries_do_not_claim_credit(self):
        for authorship in ("own", "permission"):
            self.assertEqual(upload_access("verified_v1", False, False, "vinyl", authorship),
                             {"supporter_only": False, "audience": "public", "authorship": authorship})
        self.assertEqual(upload_access("verified_v1", True, True, "livery", "own"),
                         {"supporter_only": True, "audience": "verified"})
        for mode, allowed, restricted, authorship in (("unsupported", True, False, "own"),
                ("verified_v1", False, True, "own"), ("verified_v1", True, False, "")):
            with self.assertRaises(CommunityApiError):
                upload_access(mode, allowed, restricted, "vinyl", authorship)

    def test_claim_bounds_unique_ids_and_revision_evidence(self):
        item = {"artwork_id": "one", "revision": 1, "content_sha256": "a" * 64}
        self.assertEqual(claim_request([item])["assertion"], "own_original_vinyl_v1")
        self.assertEqual(len(claim_request([{**item, "artwork_id": str(i)} for i in range(10)])["claims"]), 10)
        for selection in ([], [item] * 2, [item, {**item, "revision": 2}],
                          [{**item, "artwork_id": str(i)} for i in range(11)],
                          [{**item, "revision": True}], [{**item, "content_sha256": "private/path.json"}]):
            with self.assertRaises(CommunityApiError): claim_request(selection)

    def test_claim_results_correlate_by_id_and_never_invent_credit(self):
        selections = [{"artwork_id": name, "revision": 1, "content_sha256": "a" * 64} for name in ("first", "second")]
        results = [{"artwork_id": "second", "outcome": "rejected", "error": "claim_revision_changed", "contribution": None},
                   {"artwork_id": "first", "outcome": "accepted", "error": None, "contribution": contribution("scheduled", False)}]
        payload = {"results": results, "access_policy": policy(), "capabilities": {"verified": capability(9)}}
        parsed = claim_results(payload, selections)
        self.assertEqual([row["artwork_id"] for row in parsed], ["first", "second"])
        self.assertEqual(parsed[0]["contribution"]["state"], "scheduled")
        for malformed in (results[:1], [results[0], results[0]], [{**results[0], "artwork_id": "other"}, results[1]],
                          [{**results[0], "error": None}, results[1]]):
            with self.assertRaises(CommunityApiError): claim_results({**payload, "results": malformed}, selections)


class TransportTests(unittest.TestCase):
    def test_contract_header_on_json_binary_and_multipart_only_community(self):
        client = CommunityApiClient("http://127.0.0.1:8790/v1", "synthetic")
        with patch.object(client, "_open", return_value=(b"{}", {})) as opened:
            client.json("config")
            client.binary("asset")
            client.multipart("liveries", {}, {"package": ("x.kfpslivery", b"x", "application/octet-stream")})
        for call in opened.call_args_list:
            self.assertEqual(call.args[0].get_header("X-community-access-contract"), "1")
        source = (UI / "src/kfps_ui/community_service.py").read_text(encoding="utf-8")
        github = source.split("def _github_post_json", 1)[1].split("def community_file_part", 1)[0]
        self.assertNotIn("X-Community-Access-Contract", github)

    def test_observes_success_and_http_error_policy_headers(self):
        headers = Message()
        headers["x-community-access-policy"] = "verified_v1"
        response = BytesIO(b"{}")
        response.headers = headers
        observed = []
        client = CommunityApiClient("http://127.0.0.1:8790/v1", policy_observer=observed.append)
        with patch("kfps_ui.community_client._OPENER.open", return_value=response):
            client.json("config")
        error = HTTPError(client.url("session"), 403, "Forbidden", headers, BytesIO(b'{"error":"verified_required"}'))
        with patch("kfps_ui.community_client._OPENER.open", side_effect=error), self.assertRaises(CommunityApiError):
            client.json("session")
        self.assertEqual(observed, ["verified_v1", "verified_v1"])


if __name__ == "__main__":
    unittest.main()
