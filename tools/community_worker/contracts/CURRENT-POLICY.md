# Current Policy Overrides

2026-10-19. Current source policy, superseding the earlier preflight contract.
This document does not assert that the live service has enabled Verified:

1. Ordinary Verified requires 14 * 24 hours from first validated GitHub Community
   connection AND ten eligible lifetime own HANDMADE vinyl contributions.
2. Toolmade uploads remain supported, including explicit own/permission authorship
   and public audience. They never count. Liveries never count. Revisions do not
   create another contribution. No automated classifier is introduced.
3. Qualifying existing key holders can receive a permanent, identity-bound
   grandfather grant after trusted server verification of historical eligibility.
   This bypasses BOTH ordinary conditions; local key possession alone is insufficient.
   Temporary supporter state remains truthful and independent of Verified.
4. Grant persistence survives proof expiry, unlink/local key deletion and reconnect.
   Suspension overrides access. A newer registered key or a v1 entitlement alone
   must not create a permanent grant. New console key creation/delivery is retired.

## Wire

- AccessPolicy.count_basis is lifetime_own_handmade_vinyls. Existing threshold/count
  field names remain unchanged. required_account_age_days remains 14.
- VerifiedCapability.grandfathered_at is a required nullable UTC timestamp.
  It remains present for a durable grant while legacy mode or suspension disables
  effective Verified. No grant means null, never a local key-derived timestamp.
- Active grant holders use reason grandfathered_supporter. Active ordinary users
  use eligible. Active grant holders may have fewer than ten credits or null
  connection dates. Active ordinary users must satisfy both requirements.
- Reason precedence: policy_legacy, account_suspended, unsupported_identity,
  grandfathered_supporter, connection_date_unavailable, waiting_period,
  contributions_required, eligible.
- Toolmade/livery contribution rows use state not_eligible and can_claim=false.
  A submitted Toolmade claim is rejected with handmade_required; a livery claim
  is rejected with vinyl_required. Neither blocks normal uploads.
- POST /v1/supporter/verify accepts an optional legacy_verified_grant alongside
  the unchanged entitlement. POST and DELETE responses add access_policy and
  capabilities; clients refresh session rather than alter counts/grants locally.
  The paired issuer proof is defined in LEGACY-GRANT-PROOF.md. The v1 entitlement
  has no trusted historical registration/cutoff evidence and cannot by itself
  qualify a newly connected historical holder.
- Local themes require a valid signed key but no PC binding or online activation.
  Community recognition is separate: the issuer checks the registered active
  key proof and atomically binds one license to one stable Community subject.
  No stored device or activation timestamp is required. The Community service
  authenticates the GitHub account and verifies the signed pair and its cutoff
  before recording a permanent grant. See ../../supporter_activation_worker/docs/THEME-ONLY-KEYS.md.

## Classification And Lifetime Evidence

Classification is an existing creator declaration with admin correction. It is
not proof of original authorship. Qualification and counts require Handmade;
an admin correction to Toolmade removes that contribution from the effective count
without deleting the ledger/audit. Reclassification back to Handmade reevaluates
the same original contribution, never creates a second one. Explicit revocation
remains sticky. Removal/expiry retains credit for honestly qualified Handmade work.

Legacy remains the default. No schema update is a deployment or a live policy
change. No raw key, personal data or live customer record is used in local tests.
