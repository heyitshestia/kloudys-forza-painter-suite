# Signed Legacy Grant Contract

Current local implementation, 2026-10-19; service rollout remains a separate gate.
The issuer signs the paired evidence, the Python client verifies and forwards it,
and the Community service authenticates the account, verifies the proof again and
stores the permanent grant. This document does not claim deployment or authorize
live account/data operations.

Activation response keeps entitlement byte/schema-compatible and optionally adds
legacy_verified_grant as a JSON object envelope. Updated clients pass that object
unchanged beside entitlement in POST /v1/supporter/verify. Absence is valid and
does not itself grant Verified. No local key-presence decision is trusted.

Envelope exact keys: type, version, kid, payload, signature.
Type: kfps.community.legacy-verified-grant. Version: 1. kid: same as v1 entitlement.
Payload/signature use the existing canonical JSON, base64url and RSA-SHA256 scheme.
Payload exact keys:

- schema: kfps.community.legacy-verified.v1
- audience: kfps-community-verified-v1
- subject, entitlement_id, nonce, issued_at, expires_at: exact strings from v1
- license_created_at: issuer's persisted server license registration timestamp
- eligibility_cutoff: explicitly configured reviewed cutoff

Both services use COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF, with no default. Cutoff
must be exact canonical UTC ISO with milliseconds (YYYY-MM-DDTHH:mm:ss.sssZ),
not later than server now. The issuer requires a registered active license with
the matching key-signature proof, an atomic claim for the same Community subject,
and a trusted registration date <= cutoff. Stored device identity and activated_at
are not eligibility conditions. Device-free requests and exact legacy requests
are accepted; any legacy device field is format-checked and discarded.
Community verifies BOTH signatures,
the exact paired fields and key ID, the authenticated GitHub identity, the short
proof lifetime, and exact cutoff equality to its own configuration. The issuer
does not authenticate the GitHub session itself; only the Community service can
bind redemption to the authenticated account. A different subject cannot reuse
the claimed license, even with a fresh nonce or another machine.

Community grants are unique by stable GitHub identity and entitlement, idempotent,
audited and separate from expiring theme entitlements. Clearing a key, expiry or
relogin does not remove a grant. Account suspension still overrides active access.

Existing trusted Community verification rows can be backfilled only with proven
pre-cutoff active verification. They are not inferred from raw keys or a current
post-cutoff proof. Existing keys never registered in issuer storage require an
audited decision; registration time is not signed key issuance time.
