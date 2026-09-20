# Community Integration

## Scope and Delivery

Replace the Community page inside KFPS with the reviewed gallery. Develop and
test in DIRTY, transfer only verified changes to CLEAN, then deploy the existing
Community Worker. No new service, personal-installation changes, version bump,
GitHub push, release, or bundle. Existing artwork and account data must survive.

Evidence: `runtime/community-preview/integration-20260920/` (ignored runtime).
The local preview remains an explicit test harness, never the production backend.

## Decisions

- Reuse CommunityService for GitHub device authorization, protected credentials,
  supporter entitlements and authenticated HTTP. Add a view adapter, not another
  authentication system or SQLite-backed production catalog.
- Extend the current Worker/D1/private R2 additively. Preserve legacy API behavior
  for old clients; new gallery opts into the expanded catalog contract.
- Restrict all file downloads and livery photos to authenticated requests. Apply
  supporter and availability checks on every asset request, not only in the UI.
- Availability is UTC with inclusive start and exclusive end. Deny expired files
  immediately; cron removes all stored revisions and media, retrying failures.
- New upload limits must respect the Worker's 128 MiB memory ceiling. Do not send
  a 256 MiB base64 body just because the local prototype allowed that file size.
- Keep the nine theme font families and native app shell. No moderation UI,
  private messages, comments, new supporter perks or separate Community app.

## Milestones and Gates

1. Backend: additive migration, votes, expanded discovery, bounded livery/media
   validation, availability and retryable deletion. Gate: worker regressions,
   authorization matrix, malformed uploads, exact time boundaries, failed purge
   retry, existing artwork/revision compatibility.
2. Native integration: real account flow, creator catalog, upload/download/media,
   supporter actions, voting and schedules. Gate: actual QML actions against a
   local instance of the real Worker, EN/KO, restart and sign-out cache isolation.
3. CLEAN transfer: review against its newer base, transfer scoped files only.
   Gate: CLEAN regression and native launch, no unrelated or private artifacts.
4. Deployment: capture current deployment and database recovery point, apply the
   additive migration, deploy the existing Worker and read back health/config.
   Gate: private-file access denied anonymously, legacy endpoints healthy and new
   contract advertised. Record what was and was not verified live.

Stop before deployment on failed compatibility/security tests. Do not publish
partial UI wiring as a finished replacement. Production user content is not a
test fixture; use isolated synthetic records and remove them after verification.

## Alternatives and Lookback

A second backend was rejected: it duplicates credentials, administration and
storage. Extending the old monolithic QML page was also rejected: the reviewed
modular gallery already has native interaction and layout evidence. A thin live
adapter preserves both the existing account service and reviewed components.

At each milestone recheck scope, earlier implementations, failures versus test
errors, complexity, regressions and whether to continue or simplify. The old
mock tests certify layout only, not real GitHub/R2 integration.

## References

- Cloudflare Worker limits: https://developers.cloudflare.com/workers/platform/limits/
- Streaming guidance: https://developers.cloudflare.com/workers/best-practices/workers-best-practices/

## State

Current state, 2026-09-20: implemented in DIRTY, selectively transferred to CLEAN,
and deployed to the existing production Community Worker. No GitHub push, version
bump, release or bundle. Personal Native Updated Local was not changed.

The following dated checkpoints describe the sequence, not outstanding work.

2026-09-20: integration started. DIRTY and CLEAN Worker sources match; CLEAN is
clean at a2d72d0 (3.1.89), while DIRTY has pre-existing unrelated changes on an
older base. Whole-worktree copying is prohibited. No deployment yet.

### Backend and Native Checkpoint

Implemented additive migration 0011, opt-in `view=gallery` discovery, votes,
scheduled access gates and retryable R2 prefix deletion. Legacy lists exclude
liveries so older JSON-only clients cannot accidentally treat ZIP data as JSON.
Livery uploads use bounded multipart requests: 16 MiB package, 32 MiB expanded,
8 MiB per member, 256 files, three photos of at most 2 MiB after preparation.
The native validator still performs full source/geometry validation. The Worker
checks bounded decompression, member allowlist, manifest hashes and sharing
declarations; it does not independently decode Forza binary geometry.

fflate 0.8.3 is an exact, MIT-licensed dependency (Arjun Barrett, 2023), selected
for streamed decompression with actual-output limits. License remains in its npm
package; no copied upstream implementation. Primary source:
https://github.com/101arrowz/fflate . The initial 0.8.2 selection had advisory
GHSA-px8p-9vwx-vf98 in unzipSync (not our streaming API); upgraded specifically
to patched 0.8.3. npm audit then reports zero vulnerabilities.

Worker checkpoint: 54 tests passed. Native real-Worker integration checkpoint:
`integration-20260920-native-08/gallery-checks.json`, thirteen groups passed including
native account/session creation, vinyl upload, actual vote/favorite clicks,
authenticated hashed download, creator tiles, actual Audi package/photo upload
and validated download, language changes, ordinary vinyl revisions, protected
credential reload through a fresh service, timed expiry and logout. Uses a local test account,
not a claim of live GitHub OAuth verification. The first native run failed due
to test lookup of a Popup as an Item, corrected in the test lookup.

Lookback: still replacing the existing page/service, not creating a parallel
platform. Network testing exposed missing production labels and a creator-title
field mismatch, both corrected. Existing tags and vinyl revisions were initially
absent from the adapter and have been restored before transfer. Timed uploads and
full liveries do not accept in-place revisions; original ordinary vinyl revision
behavior remains. No CLEAN changes or deployment yet.

### Transfer Gate

210 desktop regressions pass, covering Community, package validation, renderer
lifecycle, QML controls, theme catalog and window/settings behavior. One previous
source-contract test expected shrinking text; its contract now checks the requested
fixed-size curve text, symmetric slots and overflow elision. The native integration
test needed settled layout frames before simulated mouse clicks and unique visual
fixtures to respect duplicate-preview protection; these were test problems, not
service bypasses. All final native checks have no QML errors.

Lookback: the same account service, endpoints, D1 and private R2 remain authoritative.
No new identity or hosting system has been introduced. The renderer now invalidates
pending opens when closed, preventing a late download from reopening it after page
navigation. A restored ordinary vinyl can have a new schedule; an expired/purged
upload cannot be restored. Additive schema and opt-in catalog behavior preserve
old clients. Continue with selective transfer, not whole-worktree synchronization.

Production baseline Worker: 0300d8aa-5794-465c-a41f-0fb689c38d8a. Remote migration
inspection confirms only 0011 is pending. A D1 Time Travel bookmark is recorded
privately in the ignored run directory before migration; no production records
are exported into source control. Rollback is the previous Worker version with
the additive schema retained; database restoration is an emergency operation,
not an automatic rollback (it could discard newer user writes).

### Deployment and Final Verification

- CLEAN desktop suite: 210 passed. CLEAN Worker suite: 54 passed; typecheck passed;
  npm audit found no known vulnerabilities in the installed dependency tree.
- CLEAN native local-Worker qualification: 15 groups passed, no QML errors,
  including actual authenticated package transfer, saved-session reload, revisions,
  votes, favorites, creator catalog, EN/KO, 1280/1000-width layouts, expiry and
  renderer open/close cleanup. Evidence:
  `runtime/community-preview/integration-20260920-clean-native-02/`.
- The first CLEAN pass caught an omitted FullLiveryService dependency. Added only
  the reviewed preview-only entry point and path override, then reran the suite.
- The medium-window pass exposed unnecessary recreation of translated tab models
  on generic service updates. A value-cached language property stops that churn.
- A restore test was intermittently creating different ZIP bytes across a DOS
  timestamp boundary. Fixed the fixture timestamp; restoration now tests identical
  archive bytes deliberately, without relaxing production hash checks.
- Migration 0011 applied successfully (12 statements); no migrations remain.
- Production Worker version: `73c78ad1-80db-4a9d-8ddf-b012004ebce2`.
  Existing D1/R2 names, GitHub client, supporter verification and ten-minute cron
  are unchanged. No test-auth capability is enabled in production.
- Live read-only checks passed: healthy service, gallery v1 configuration,
  unchanged eight featured legacy records, 674 gallery entries, anonymous file
  download denied, authenticated thumbnail hash validated, existing session accepted.
- Normal CLEAN startup against production loaded the new QML page and real
  featured images under the existing Kloudy account. No new sign-in was required.
  `integration-20260920/clean-live-native.json` and `clean-live.png` record this.
  Background captures explicitly advance QML incubation/render frames; an initial
  fixed-delay capture did not finish loading while the window was obscured.
- The isolated local Worker and test application instances have been stopped.
  Transfer hashes, recovery bookmark and live checks are under the ignored
  `runtime/community-preview/integration-20260920/` directory in CLEAN.

### Limits and Remaining Validation

- Existing sessions remain valid until their ordinary expiry/revocation, or if
  Windows can no longer decrypt their local credentials. This migration does not
  rotate secrets, delete sessions or replace credential files. The live cached
  GitHub session was checked before and after deployment; fresh GitHub browser
  authorization was not repeated during this pass because that flow is unchanged.
- Full-livery sharing currently accepts the existing FH6 package format/compiler
  revision. Other games' full-livery packages are not newly supported. Limits are
  16 MiB compressed, 32 MiB expanded, 8 MiB/member, and 1-3 prepared photos.
- Expiry denies new access at the deadline. Physical object deletion runs on the
  existing ten-minute cron in bounded batches and retries failures. Production
  originally had no timed releases at verification. The subsequent synthetic
  production qualification is documented in COMMUNITY_LIVE_QUALIFICATION.md.
- The initial deployment verification was read-only. Subsequent production
  qualification exercised synthetic vinyl/livery uploads, votes, revisions,
  downloads, real-Audi 3D motion and repeated cleanup. This does not cover every
  vehicle or GPU; see COMMUNITY_LIVE_QUALIFICATION.md for the precise scope.
- Native interface labels support EN/KO, but some detailed server validation
  errors remain English. Both supported window sizes and prior nine-theme evidence
  are retained; this is not a claim of testing every display scale or device.
- Shared tests emit existing Pillow deprecation and Qt/Python shutdown resource
  warnings. They do not fail, but no claim of eliminating every process-level
  allocation or warning is made.
