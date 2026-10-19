# Theme-Only Keys And Legacy Worker Compatibility

Local implementation, not a deployment or cutoff decision. This document
supersedes historical PC-registration behavior. The current worker README and
`../LEGACY-VERIFIED-GRANT.md` describe the same device-free recognition boundary;
the cryptographic grandfather-proof contract remains unchanged.

## Ownership And Scope

The new application unlocks supporter themes by validating the existing signed
local key. It does not call activate, status, or deactivate. Its only recognition
request here is `/v1/community-entitlement`, without a device ID.

Console key creation, automatic fulfillment and email delivery are retired. The
worker compatibility change does not weaken admin authentication, change retained
admin operations, set a
cutoff, alter Community moderation, or modify permanent Community Verified grants.

## Legacy Public Routes

All three routes retain their exact protocol-1 request:

```text
protocol, key_id, key_proof, device_id, nonce
```

`protocol` is the number 1. IDs are 64 lowercase hexadecimal characters. The
base64url proof decodes to 384 bytes; the nonce decodes to 16 through 64 bytes.
Unknown/missing fields, malformed values, non-JSON content types, and bodies over
8192 bytes remain rejected. A device is format-checked and echoed only for old
client signature verification, never stored or compared with a database device.

| Route | Registered active proof | Registered revoked proof | Unknown ID or wrong proof |
| --- | --- | --- | --- |
| `/v1/activate` | 200, `active`, signed receipt | 403, signed `not_eligible` decision | 403, unsigned `not_eligible` error |
| `/v1/status` | 200, signed `active` status | 200, signed `revoked` status | 403, unsigned `not_eligible` error |
| `/v1/deactivate` | 200, signed `deactivated` decision | 403, signed `not_eligible` decision | 403, unsigned `not_eligible` error |

These operations are now read-only. Multiple machines may use the same eligible
registered proof. No duplicate decisions, duplicate counts, reset counts, device
assignments, automatic revocations, or timestamp updates are produced.
Deactivation acknowledges an old client's local receipt removal; it does not
change server eligibility or release the Community binding.

Receipt schema/type/field sets are unchanged, including the absence of a receipt
nonce in the old format. The receipt uses the historical activation timestamp
when present, otherwise the response time without saving it. Signed decisions
and statuses keep the request device and nonce. All signing helpers are unchanged.

## Community Recognition

The endpoint accepts exactly either:

```text
protocol, key_id, key_proof, nonce, community_subject
protocol, key_id, key_proof, device_id, nonce, community_subject
```

If present, `device_id` must still be a valid 64-character lowercase hex string;
null, empty, or malformed values are not equivalent to omission. After parsing it
is discarded. Neither stored device identity nor `activated_at` is an eligibility
condition. Proof hash, registered license, active status, and UUID subject checks
remain required.

The existing parameterized atomic D1 update still binds one license to one exact
Community subject hash and one opaque entitlement ID. Same-subject retries and
refreshes reuse that ID, including after signing failure or module restart.
Another subject receives 409 even when a request nonce or key proof is replayed
from another machine. Invalid proof/revoked/unknown requests receive 403 and
cannot claim an account. Only the existing authenticated admin reset operation
can explicitly release the account binding.

The successful response remains `status: active` plus the unchanged signed v1
`entitlement`, with optional `legacy_verified_grant`. Proofs contain no key or
device identity. The nonce, subject, entitlement ID, issue time, and 15-minute
expiry are paired exactly across both signed envelopes.

### Verified Eligibility Is Not Broadened

The optional grant still requires canonical trusted dates:

```text
stored licenses.created_at <= configured COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF
configured COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF <= server issuance time
```

Missing, malformed, or future configuration, or malformed/newer registration
dates, omit the optional grant. Client-supplied cutoff/creation fields are rejected.
No date is inferred from the key, activation history, local file, or current date.

For compatibility, an active registered newer key can still receive a v1
entitlement, **not** a grandfather Verified grant. Community must require its
trusted paired-grant validation and authenticated subject binding before creating
a permanent grandfather record; it must not treat key possession or the v1 token
alone as Verified. This issuer does not authenticate the Community login itself.
Existing permanent trusted grants remain Community-owned and untouched, including
their identity binding, idempotent redemption, and moderation rules.

Revoked rows are not silently restored. The schema has no revocation-reason field;
this slice cannot infer whether a historical revocation should be reconsidered.

## Data And Security Review

- No migration or record rewrite is needed. Historical devices, counters, status,
  creation dates, account hashes, and entitlement IDs are retained.
- Only Community binding fields and its existing `updated_at` update are written
  by public recognition. Public compatibility routes perform no writes.
- Legacy admin reset/clear-history operations remain authenticated and unchanged;
  historical counters have no public eligibility/enforcement role.
- RSA signing, registered signature-hash proof authentication, exact field sets,
  nonce bounds, cache-control, response privacy, and generic failures are retained.
- SQL values are bound parameters. Account claiming and eligibility are checked
  in the same update, retaining the one-account race guarantee.
- Admin HMAC checks continue to cover method, exact path/query, timestamp,
  request ID, and body hash. Mutation replay rejection remains intact.
- No rate limiter or rate-limit binding exists in the inspected worker baseline.
  No abuse control was removed. External edge limits were neither accessed nor
  verified; no claim of locally tested rate limiting is made.
- No dependency, credential, live service, or deployment changes were made.

No new security regression was found in this bounded source/route review. This is
local emulated validation, not production validation or a full dependency audit.

## Test Evidence

The focused suites exercise the theme-only compatibility and holder-recognition
contract through actual local fetch routes, signing and emulated D1.

| Guarantee | Tests | Evidence |
| --- | --- | --- |
| Old signed response formats; multiple machines; no historical-column writes | `theme_only_keys.spec.ts`, `worker.spec.ts` | Real fetch routes, RSA verification, exact fields, D1 audit triggers |
| Old/new exact Community requests; registered active proof required | `theme_only_keys.spec.ts` | Missing device accepted, malformed device rejected, bad proof/status denied |
| One-account binding, nonce pairing, races, retries, restart | `theme_only_keys.spec.ts` | Same ID retained, another subject denied, recovery after signing failure |
| Trusted cutoff and all grandfather failure cases | `legacy_verified.spec.ts` in both request modes | Original signing/cutoff cases retained and expanded |
| Admin authentication/replay and existing Ko-fi behavior | `theme_only_keys.spec.ts`, `worker.spec.ts` | HMAC tampering/time/replay checks, encrypted inbox tests |

Baseline: **37 passed**. Valid RED: **48 failed, 54 passed**, with a clean
typecheck. First GREEN: **102 passed**. Final expanded security/regression suite:
**110 passed**, with a clean typecheck. No skipped tests.

Run from this worker directory using its already installed dependencies:

```powershell
./test/run-local.ps1 -RunDirectory '<absolute-isolated-test-directory>' -Phase final-green
./test/run-local.ps1 -RunDirectory '<absolute-isolated-test-directory>' -Phase final-typecheck -Typecheck
```

The runner uses synthetic signing keys and local emulated D1, disables remote
bindings, and does not load production Wrangler configuration or dotenv secrets.
Temporary state, cache, and Wrangler logs are routed under the run directory.
Replace the placeholder with a dedicated disposable test directory, never an
installation, user profile or customer-data location. Test logs are local evidence
and must not be included in public source or release bundles.

Coverage percentage was not measured: the installed dependencies lack
`@vitest/coverage-istanbul`, and native V8 coverage is unsupported by this worker
test pool. No packages were downloaded for this task. Full desktop-client and
Community permanent-grant redemption tests remain with their respective owners.
