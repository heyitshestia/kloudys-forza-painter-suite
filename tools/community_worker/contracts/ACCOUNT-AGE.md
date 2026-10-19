# Community Connection Age

User-authorized change, 2026-10-19. Supersedes the earlier ten-credit-only
eligibility formula. Default legacy mode and deployment restrictions are unchanged.

Ordinary Verified requires BOTH ten lifetime eligible own Handmade vinyl contributions AND at least
14 * 24 hours since the first successful GitHub identity connection to Community.
Only worker time is authoritative. Contributions earned during the wait count.
GitHub account age, device clocks, username changes, paid keys and reconnects are
not eligibility inputs.

## Exact Additive Wire Fields

- AccessPolicy.required_account_age_days: 14.
- VerifiedCapability.required_account_age_days: 14.
- VerifiedCapability.connected_at: first Community GitHub connection UTC, or null.
- VerifiedCapability.eligible_after: connected_at + 1,209,600,000 ms UTC, or null.
- VerifiedCapability.reason additionally permits waiting_period and
  connection_date_unavailable. No client-side remaining-time gate is provided.

Permanent existing-key grants bypass the ordinary requirements; see CURRENT-POLICY.md.
Reason precedence: policy_legacy, account_suspended, unsupported_identity, grandfathered_supporter,
connection_date_unavailable, waiting_period, contributions_required, eligible.
The count remains visible while waiting. Capability active is server-owned.
Dates are both null for unsupported identities or missing/invalid/future stored
timestamps. A future timestamp is invalid evidence, not a new waiting period.
Unknown dates require evidence-based operator repair, never a reset to today or
an assumed old date. Date output normalizes valid UTC timestamps to milliseconds.

## Historical Evidence

Local repository history starts auth.ts at commit
0cc62a8390f0a6c763be3228d0f5ed9f77e584f8. handleGitHubAuth validates the GitHub /user
response before calling upsertProviderUser. The new-user INSERT uses worker now
for users.created_at. Existing users are found by UNIQUE(provider, provider_id)
and reconnect only changes provider_login, avatar_url and updated_at.
The later auth change (9e136bf) only adds ignored_count to session statistics.
No inspected production source/migration mutates users.created_at or converts a
local-test account into a GitHub account. Profile/username changes also preserve it.

Therefore users.created_at for provider=github is the existing authoritative
first validated Community connection timestamp. No new date column, rewrite or
legacy age backfill is needed. A later session creation failure does not undo the
already successful identity connection. This is source/history evidence, not a
claim that the live database was queried; it was not.

## Required Checks

First connection, reconnect with renamed GitHub login, profile/username changes,
existing old account, just before/exactly/after 14 days, 9/10 credits, contributions
earned during the waiting period, suspension, unsupported identity, malformed/
missing/future dates, unchanged legacy supporter behavior. Use synthetic identities
and local worker/D1 only; do not contact GitHub in tests.
