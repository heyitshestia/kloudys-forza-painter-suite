# Local Verified Rollout And Repair

Implementation is authorized locally; deployment, a production cutoff, remote
migrations and live customer-data operations are NOT authorized. This document
is an operator runbook, not evidence that production has changed. See the test
handoff for the current qualification state.

The 2026-10-19 client checks existing theme keys locally and no longer sends a
PC identifier to the legacy grant issuer. Deploy the staged compatible issuer
before distributing that client; see
`../../supporter_activation_worker/docs/THEME-ONLY-KEYS.md`. This adds no migration
or cutoff default. Retire the old public key-product/delivery promise before
launching the console change: it no longer creates or emails keys. Existing
records, permanent grants and private artwork must remain intact.

## Contract

The one schema is `verified-access-contract.schema.json`. Existing Community v1
payloads keep their original fields. `CURRENT-POLICY.md`, `ACCOUNT-AGE.md` and
`LEGACY-GRANT-PROOF.md` describe the accepted current rules. Historical preflight
notes outside this directory are not a second contract.

- Request header: `X-Community-Access-Contract: 1`.
- Response header: `X-Community-Access-Policy: legacy_supporter|verified_v1`.
- `COMMUNITY_ACCESS_POLICY` absent or `legacy` preserves paid legacy behavior;
  only exact `verified-v1` enables earned/permanent Verified. Invalid config fails
  closed. Do not publish a default Verified environment as part of these changes.
- Existing `supporter_only` storage is preserved. It maps to `verified` only
  under the enabled policy; it never makes restricted assets public.
- `GET /v1/config` advertises `access_policy`; session and supporter verification
  responses add `capabilities.verified`. Paid-theme/supporter state stays truthful.
- `GET /v1/artworks?view=gallery&scope=verified` discovers restricted metadata.
  `scope=supporters` remains a read alias. Compact published thumbnails stay
  discoverable. Full previews, photos, downloads and restricted interactions
  require the effective capability and contract header. Ordinary public downloads
  keep the existing sign-in/username requirements.
- Vinyl uploads/revisions in enabled mode require `audience` and `authorship`;
  liveries require audience but reject authorship. Rights-to-share confirmation
  stays distinct from original authorship. Toolmade uploads remain valid but
  cannot earn a credit. Unsupported fingerprint semantics do not block uploads.
- Owner selection uses `GET /v1/artworks?view=gallery&scope=mine&contribution_view=claims`.
  The claim POST is `/v1/profile/vinyl-claims`, exact schema, at most ten unique
  artwork IDs, 16 KiB, ten batches/hour. Identity comes from the session. One
  result per selection distinguishes stale revisions, nonownership, Toolmade,
  duplicate, revoked and missing-evidence claims. Unavailable rows expose no media.
- Existing `/v1/admin/moderate` accepts `credit_approve`, `credit_revoke` and
  `credit_restore` with exact revision/hash and a required review note. Approval
  cannot bypass uniqueness/publication evidence or a sticky revocation. Only
  explicit restore clears revocation. The existing admin console exposes these
  bounded operations; existing review actions remain unchanged.

## Additive Migration

1. Apply 0012 through 0014 to a backed-up isolated database first. Sessions, users,
   original files/hashes and `supporter_only` are not replaced. The contribution
   and permanent-grant ledgers are additive. Test default legacy before enabling.
   Migration 0014 adds the covering fingerprint-status/artwork index used by
   every readiness check; it changes no records or authorization rules. Preserve
   it on policy rollback. Removing this index would only restore a full-scan
   performance cost, not undo the ledgers or disable the readiness check.
2. Use existing admin authentication with `POST /v1/admin/verified-index` and an
   exact body `{ "action": "status" }`. No caller supplies paths, URLs, identities,
   counts, readiness flags or fingerprints.
3. Repeated `index_batch` actions read at most four unknown canonical revisions
   from their registered private R2 keys, with a 24 MiB limit and exact stored
   content-hash verification. File bytes are not changed. Per-row state is the
   resumable watermark. Transient storage failure leaves the row retryable.
   Missing/corrupt/unsupported records become review-required, not invented credit.
4. Global reservations cover permission/unknown-authorship designs too. A
   collision between historical artworks blocks automatic credit for both;
   indexing never awards authorship or chooses an original artist by arrival order.
5. `finalize` is accepted only with zero unknown rows. Unknown rows added later
   disable automatic credit until repaired. New uploads use the same normalizer
   in the existing publication transaction. Indexing completion is not a claim
   that every old missing file or historical publication can be reconstructed.
6. Publication windows record committed server transitions, including scheduled
   starts, close times and terminal changes. Migration snapshots current published
   rows at migration time; it does not fabricate a past interval from published_at.
   Own claims can use a retained proven interval. Missing historical evidence
   stays review-required. Expiry/removal after a genuine interval retains credit;
   deletion before a scheduled start does not create one.
7. Configure an explicitly reviewed `COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF` in
   both issuers only at a later approved rollout. It must be canonical millisecond
   UTC, no later than proof issuance. The default is unset. `backfill_legacy_grants`
   is an idempotent admin maintenance action for trustworthy GitHub-linked
   entitlements active at that cutoff; future/ambiguous evidence cannot qualify.
   Newly linked old keys use the optional paired signed proof, not a local flag.
8. Verify old/new client compatibility, full restricted asset paths, claims,
   ten Handmade contributions plus age, permanent grants and theme separation
   in the isolated environment. Only a subsequent reviewed rollout may set
   `COMMUNITY_ACCESS_POLICY=verified-v1` remotely.

## Rollback And Repair

Rollback means set policy to `legacy`, not restore the whole database or delete
ledger tables. Preserve uploads, files, sessions, reservations, authored claims,
permanent grants and moderation audit. Legacy uploads continue fingerprinting
but do not infer authorship. Re-enable after the same readiness check.

For evidence corruption, set the readiness service setting away from `ready`
before repairing the isolated database. Compare the registered R2 object against
its original hash; never rewrite files or hashes to make a check pass. An audited
operator may reset only affected per-revision index statuses to `unknown`, then
run bounded indexing and finalize. Keep reservations: do not free a disputed
fingerprint for another account. A historical collision removes its automatic
count even if a credit had already been materialized. Reassignment across owners
requires a separately reviewed, atomic audited repair, not `credit_restore`.

The cutoff is an immutable rollout choice. Changing it is a policy/migration
decision, not a routine fix for a rejected key. Grants survive clearing temporary
supporter state, proof expiry and relogin; account suspension still blocks access.

## Limits

Handmade and own-authorship are declarations subject to moderation. This is not
an AI classifier, identity certificate or perceptual originality detector. Exact
normalization handles supported semantic equivalents; tiny edits, recolouring
and other near-duplicate farming remain moderation concerns. Nonopaque masks,
contradictory mask flags, transparent legacy bounds and unknown shape semantics
are conservatively review-required for automatic credit.
