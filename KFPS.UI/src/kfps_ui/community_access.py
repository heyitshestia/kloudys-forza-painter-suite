"""Consumer checks for the versioned Community access contract.

The wire authority is tools/community_worker/contracts/verified-access-contract.schema.json.
These checks deliberately deny access for unknown versions or malformed additions.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re

from .community_client import CommunityApiError

POLICY_MODES = {"legacy_supporter", "verified_v1"}
CONTRIBUTION_STATES = {
    "not_claimed", "permission_only", "pending_publication", "scheduled", "credited",
    "revoked", "duplicate", "review_required", "not_eligible",
}
CLAIM_ERRORS = {
    "artwork_not_found", "claim_revision_changed", "credit_revoked",
    "duplicate_contribution", "claim_evidence_required", "vinyl_required",
    "handmade_required",
}


def policy_mode(payload: dict) -> str:
    if not isinstance(payload, dict):
        return "unsupported"
    if "access_policy" not in payload:
        return "legacy_supporter"
    value = payload["access_policy"]
    if not isinstance(value, dict) or set(value) != {
        "version", "mode", "required_own_vinyls", "required_account_age_days", "count_basis", "own_claims_enabled",
    }:
        return "unsupported"
    mode = value.get("mode")
    if (type(value.get("version")) is not int or value["version"] != 1
            or not isinstance(mode, str) or mode not in POLICY_MODES or type(value.get("required_own_vinyls")) is not int
            or value["required_own_vinyls"] != 10 or value.get("count_basis") != "lifetime_own_handmade_vinyls"
            or type(value.get("required_account_age_days")) is not int or value["required_account_age_days"] != 14
            or type(value.get("own_claims_enabled")) is not bool
            or value["own_claims_enabled"] != (mode == "verified_v1")):
        return "unsupported"
    return mode


def verified_capability(payload: dict, mode: str) -> dict:
    capabilities = payload.get("capabilities")
    value = capabilities.get("verified") if isinstance(capabilities, dict) else None
    if not isinstance(value, dict) or set(value) != {
        "policy_version", "active", "eligible_vinyl_count", "required_count", "required_account_age_days",
        "connected_at", "eligible_after", "grandfathered_at", "reason",
    }:
        return {}
    reason = value.get("reason")
    if (type(value.get("policy_version")) is not int or value["policy_version"] != 1
            or type(value.get("active")) is not bool
            or type(value.get("eligible_vinyl_count")) is not int or value["eligible_vinyl_count"] < 0
            or type(value.get("required_count")) is not int or value["required_count"] != 10
            or type(value.get("required_account_age_days")) is not int or value["required_account_age_days"] != 14
            or not isinstance(reason, str) or reason not in {"eligible", "grandfathered_supporter", "contributions_required", "policy_legacy", "account_suspended", "unsupported_identity", "waiting_period", "connection_date_unavailable"}
            or value["active"] != (reason in {"eligible", "grandfathered_supporter"})
            or (value["active"] and mode != "verified_v1")
            or (reason == "eligible" and value["eligible_vinyl_count"] < 10)
            or (mode == "verified_v1" and reason == "policy_legacy")):
        return {}
    connected, eligible = utc_timestamp(value["connected_at"]), utc_timestamp(value["eligible_after"])
    grandfathered = utc_timestamp(value["grandfathered_at"])
    if ((value["connected_at"] is not None and connected is None)
            or (value["grandfathered_at"] is not None and grandfathered is None)
            or (reason == "grandfathered_supporter" and grandfathered is None)
            or (reason == "eligible" and value["grandfathered_at"] is not None)
            or (value["eligible_after"] is not None and eligible is None)
            or (connected is None) != (eligible is None)
            or (connected is not None and eligible - connected != timedelta(days=14))
            or (reason in {"eligible", "waiting_period", "contributions_required"} and connected is None)
            or (reason in {"unsupported_identity", "connection_date_unavailable"} and connected is not None)):
        return {}
    return dict(value)


def utc_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def artwork_access(item: dict, mode: str, authenticated: bool, restricted_access: bool) -> dict:
    restricted = bool(item.get("supporter_only"))
    audience = "verified" if restricted and mode == "verified_v1" else ("supporter" if restricted else "public")
    denied = {"audience": audience, "can_view_media": False, "can_download": False,
              "can_interact": False, "restriction_reason": "client_update_required"}
    if mode not in POLICY_MODES:
        return denied
    value = item.get("access")
    if value is None and mode == "legacy_supporter":
        allowed = not restricted or restricted_access
        return {"audience": audience, "can_view_media": allowed,
                "can_download": authenticated and allowed, "can_interact": authenticated and allowed,
                "restriction_reason": ("authentication_required" if not authenticated else
                                       "supporter_required" if not allowed else None)}
    if not isinstance(value, dict) or set(value) != set(denied):
        return denied
    if (value.get("audience") != audience
            or any(type(value.get(key)) is not bool for key in ("can_view_media", "can_download", "can_interact"))
            or value.get("restriction_reason") not in (
                None, "authentication_required", "supporter_required", "verified_required",
                "client_update_required", "account_suspended", "unavailable",
            )):
        return denied
    result = dict(value)
    # A stale row cannot grant access after sign-out, revocation or a policy switch.
    if restricted and not restricted_access:
        result.update(can_view_media=False, can_download=False, can_interact=False)
    if not authenticated:
        result.update(can_download=False, can_interact=False)
    return result


def contribution_status(value) -> dict:
    if not isinstance(value, dict) or set(value) != {"state", "can_claim", "eligible_at", "credited_at"}:
        return {}
    if not isinstance(value.get("state"), str) or value["state"] not in CONTRIBUTION_STATES or type(value.get("can_claim")) is not bool:
        return {}
    for key in ("eligible_at", "credited_at"):
        stamp = value[key]
        if stamp is not None:
            if utc_timestamp(stamp) is None:
                return {}
    return dict(value)


def upload_access(mode: str, restricted_access: bool, restricted: bool, kind: str, authorship: str) -> dict:
    if mode not in POLICY_MODES:
        raise CommunityApiError(426, "client_update_required", "Community access could not be verified. Refresh your account or update KFPS.")
    if restricted and not restricted_access:
        raise CommunityApiError(403, "verified_required" if mode == "verified_v1" else "supporter_required",
                                "Your account cannot publish restricted artwork under the current server policy.")
    fields = {"supporter_only": bool(restricted)}
    if mode == "verified_v1":
        fields["audience"] = "verified" if restricted else "public"
        if kind == "vinyl":
            if authorship not in {"own", "permission"}:
                raise CommunityApiError(400, "authorship_required", "Choose whether this is your original vinyl or shared with permission.")
            fields["authorship"] = authorship
    return fields


def claim_selection(item: dict) -> dict:
    artwork_id, revision, digest = item.get("id"), item.get("current_revision"), item.get("content_sha256")
    if (not isinstance(artwork_id, str) or not 1 <= len(artwork_id) <= 64
            or type(revision) is not int or revision < 1
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
        raise CommunityApiError(409, "claim_evidence_required", "Refresh this upload before claiming original authorship.")
    return {"artwork_id": artwork_id, "revision": revision, "content_sha256": digest}


def claim_request(selections: list[dict]) -> dict:
    if not 1 <= len(selections) <= 10 or len({item.get("artwork_id") for item in selections}) != len(selections):
        raise CommunityApiError(400, "invalid_claims", "Select between one and ten different original vinyls.")
    checked = [claim_selection({"id": item.get("artwork_id"), "current_revision": item.get("revision"),
                               "content_sha256": item.get("content_sha256")}) for item in selections]
    payload = {"assertion": "own_original_vinyl_v1", "claims": checked}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 16 * 1024:
        raise CommunityApiError(413, "request_too_large", "The claim selection is too large.")
    return payload


def claim_results(payload: dict, selections: list[dict]) -> list[dict]:
    invalid = CommunityApiError(502, "invalid_claim_response", "The claim results could not be verified. Refresh your uploads before trying again.")
    if (not isinstance(payload, dict) or set(payload) != {"results", "access_policy", "capabilities"}
            or not isinstance(payload.get("capabilities"), dict) or set(payload["capabilities"]) != {"verified"}
            or policy_mode(payload) != "verified_v1"
            or not verified_capability(payload, "verified_v1")):
        raise invalid
    results = payload.get("results")
    requested = {item["artwork_id"] for item in selections}
    if not isinstance(results, list) or len(results) != len(requested):
        raise invalid
    by_id = {}
    for item in results:
        if not isinstance(item, dict) or set(item) != {"artwork_id", "outcome", "error", "contribution"}:
            raise invalid
        artwork_id, outcome, error = item["artwork_id"], item["outcome"], item["error"]
        if not isinstance(artwork_id, str) or artwork_id not in requested or artwork_id in by_id:
            raise invalid
        contribution = contribution_status(item["contribution"])
        if outcome == "rejected":
            if not isinstance(error, str) or error not in CLAIM_ERRORS or (item["contribution"] is not None and not contribution):
                raise invalid
        elif outcome not in ("accepted", "unchanged") or error is not None or not contribution:
            raise invalid
        by_id[artwork_id] = dict(item)
    return [by_id[item["artwork_id"]] for item in selections]
