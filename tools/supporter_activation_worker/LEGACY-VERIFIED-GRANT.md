# Optional Legacy Verified Grant (Local Draft)

The later [theme-only policy](docs/THEME-ONLY-KEYS.md) removes the device
precondition and accepts both old and device-free request bodies. The paired
proof, trusted cutoff, exact account binding and permanent-grant rules in this
document remain unchanged. Both changes are local and undeployed.

This additive issuer/client change is local and undeployed. No production cutoff
is selected or configured here. The supporter key format and signed v1 Community
proof remain unchanged. Current request compatibility and historical-state
preservation follow the theme-only policy linked above.

## Cohort Configuration

`COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF` is an optional, explicitly reviewed UTC
cutover in exact `YYYY-MM-DDTHH:mm:ss.sssZ` format. Whitespace, offsets, missing
milliseconds, invalid calendar dates, year zero, and future cutoffs are rejected
for grant issuance. There is no default, current-date fallback, or inferred cohort.

Only a registered active license with the matching key-signature proof and a
successful atomic claim for the same Community subject can receive the optional
grant. Neither a stored device nor an activation timestamp is required. The same
atomic D1 claim returns its stored `licenses.created_at`. The issuer requires:

```text
valid license.created_at <= configured cutoff <= server issuance time
```

The authoritative date is the activation license row's creation date, not the
short-lived proof's issuance time, local file timestamp, purchase text, or a date
submitted by the client. Newer theme-only keys cannot qualify through this path.
An older key first registered after the cutoff also does not qualify automatically.

Missing, malformed, or future cutoff configuration, and malformed/newer license
creation dates, **omit only the optional grant**. The v1 entitlement and unrelated
activation operations still work. This fail-closed cohort behavior avoids an
activation outage caused by a rollout configuration mistake. The issuer performs
no database migration, writes no permanent Verified record, and logs no proof/key.

## Wire Contract

`POST /v1/community-entitlement` accepts the device-free request and the exact
legacy request with a format-checked device field that is then discarded. A successful
response remains `{status: "active", entitlement}` and may additionally contain
`legacy_verified_grant`. The existing `entitlement` payload/signature are unchanged.

The optional object is a canonical-JSON RSA PKCS#1 v1.5 SHA-256 signed envelope:

```text
type       kfps.community.legacy-verified-grant
version    1
kid        same activation key ID as the accompanying v1 entitlement
payload    unpadded canonical base64url JSON
signature  unpadded base64url RSA signature
```

The payload has exactly these fields:

| Field | Value |
| --- | --- |
| schema | `kfps.community.legacy-verified.v1` |
| audience | `kfps-community-verified-v1` |
| subject | Exact v1 Community subject |
| entitlement_id | Exact v1 entitlement UUID |
| nonce | Exact v1 request nonce |
| issued_at | Exact v1 issue timestamp |
| expires_at | Exact v1 expiry timestamp |
| license_created_at | Validated D1 creation date, canonical UTC milliseconds |
| eligibility_cutoff | Exact validated configured cutoff, canonical UTC milliseconds |

The five shared values are byte-for-byte equal to the accompanying proof. Both
expire after 15 minutes. This short-lived envelope is evidence for redeeming a
permanent Community grant, not permanent access encoded in a reusable token.

Canonical definitions are maintained by the Community component in
`../community_worker/contracts/verified-access-contract.schema.json` under
`LegacyVerifiedGrantEnvelope` and `LegacyVerifiedGrantPayload`. The Community
verifier must verify the paired signatures, its configured cutoff, authenticated
identity, expiry and bindings before making its own permanent/idempotent record.

## Python Boundary And Compatibility

`activation_crypto.verify_community_legacy_verified_grant` verifies the signed v1
entitlement itself, the optional signature/key/type/version/canonical encodings,
exact fields/types, audience, five paired values, date order, and fresh lifetime.
`SupporterService` additionally binds completion to the locally retained request
nonce. A delayed old completion is ignored without consuming the current request;
an old signed pair returned with current response metadata fails verification.

Only after both proofs validate does `communityEntitlementReady` emit:

```text
{ok: true, subject, entitlement, legacy_verified_grant}
```

The signed optional object is forwarded unchanged. An absent field preserves old
responses. A present invalid field (including null) yields `ok: false` for this
Community operation; it does not revoke/change theme activation or persist any
grant locally. Old clients still consume their unchanged v1 entitlement and ignore
the extra field. The Community client/worker, not this module, controls forwarding,
redemption, permanent identity binding, unlink/relogin behavior, and access policy.

## Validation And Rollout Boundary

Focused tests use generated/synthetic signing keys, local emulated D1 licenses,
and isolated Qt service stores. They exercise eligible and boundary dates, absent/
invalid/future configuration, newer/malformed licenses, inactive/revoked/wrong
proof/account claims, malformed optional legacy device fields, signature forgery,
all five pairing mismatches, expired proofs, old responses, stale-result replay,
and unchanged valid local theme access.
Existing activation, Ko-fi/admin and isolation tests remain part of qualification.

Do not deploy this draft or set a cutoff as part of testing. A later reviewed
rollout must choose one explicit cohort cutoff and configure the same value in
both services. Missing issuer configuration intentionally grants nobody through
this optional path. No assertion of live customer eligibility is made here.
