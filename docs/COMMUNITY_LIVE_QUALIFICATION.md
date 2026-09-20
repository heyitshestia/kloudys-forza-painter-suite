# Community Live Qualification

## Scope and Stop Condition

2026-09-20: exercise CLEAN's integrated gallery against the existing production
Worker with the existing protected GitHub session. Use synthetic artwork only;
do not change personal artwork, profile, supporter entitlement, or Native Updated
Local. Keep test windows nonactivating. The subsequent user instruction authorizes
publication from CLEAN to public main with a version bump after qualification.
No new public release or downloadable bundle is requested.

Done means uploads/downloads and native interaction checks pass, real-model 3D
rendering and cleanup are checked, timed access and scheduled deletion are
verified, access/failure regressions pass, and all live test posts are removed.

## Milestones

1. Build 3,000-shape vinyls and a synthetic 1,200-shape livery for a real Audi.
2. Run native CLEAN uploads, photos, voting, favorite, discovery, revision, media,
   download, session continuity and real 3D tests. Record every created ID.
3. Verify real timed expiry and scheduled private-storage removal. Cover other
   account roles, invalid uploads and interruptions against the isolated Worker.
4. Clean up only recorded synthetic IDs, rerun regressions, record limitations.

Evidence and recovery ledger: `runtime/community-preview/live-qualification-20260920/`.
Production uploads use the title prefix `KFPS SYNTHETIC QA` and the run suffix.
Owner removal is soft deletion; physical object cleanup must be verified separately.

## Initial Lookback

The existing local and read-only checks do not prove production mutations. Reuse
the real service and native UI, with isolated download destinations, rather than
building another mock application. Do not revoke the real user's access to test
non-supporter behavior; exercise that matrix on the identical isolated Worker.

## Verified Results

- CLEAN's existing GitHub session and ordinary supporter entitlement were reused.
  No new login, credential replacement, entitlement revocation or profile edit.
- Production: 3,000-shape vinyl form upload, owner tag edit, revision, exact-hash
  download, upvote/downvote/clear, persisted favorites, profile thumbnail catalog,
  supporter-only upload/download and anonymous download denial passed.
- Production: scheduled artwork stayed out of normal discovery before opening,
  appeared in Browse and Timed Releases during its window, and lost download
  access immediately at its deadline. The native list refreshed at expiry.
- Production: a synthetic 1,200-shape package compiled for the real Audi Sport
  Quattro model passed native validation, three-photo upload and exact-byte
  download. PNG, JPEG and WebP preparation, photo removal/replacement and rejection
  of zero/four photos were exercised. No personal livery was uploaded.
- The actual 274,259-triangle model rendered with the synthetic artwork. Playwright
  checked orbit, pan, zoom, wheel visibility and nonblank canvases at 1600x900 and
  460x700, with no JavaScript errors. This is not a claim of in-game import testing
  or exhaustive vehicle/body-kit accuracy.
- X close, three additional complete open/close cycles and closing during download
  left no session/scratch directory or child worker. The closed viewer HTTP server
  was also unreachable. App RSS after the final cycles: 2119.7, 2106.4, 2097.5 MiB.
  These are whole-app stress-session measurements, not the viewer's isolated cost.
- 54 isolated real-Worker tests passed, covering second-account authorization,
  supporter gates, invalid package paths/hashes/policies, schedule boundaries,
  failed-storage purge retries, duplicates/races, restoration and session handling.
- 210 focused desktop tests passed: 84 Community, 90 livery and 36 QML contracts.
  The 5,000-item creator paging fixture completed 105 bounded pages in 0.405 s.
- Native live evidence: CLEAN `runtime/community-preview/live-qualification-20260920/141911/`.
  The earlier `141327/` contains the initial vinyl/revision/profile captures.
  Screenshots, credentials, generated artwork and runtime logs stay uncommitted.

## Lookback and Test Corrections

The first preflight checked entitlement too early while normal verification was
still running; waiting for it confirmed the existing key without changing access.
An initial upcoming-release assertion also incorrectly denied the uploader access
to their own file. The existing contract intentionally permits owner preview before
publication. Public discovery/access and access after expiry were tested separately;
no production authorization was weakened to make a test pass.

Reusing the real service and normal QML exposed these test assumptions without
requiring another implementation. No product defect has been found in the live
flow so far. Five synthetic production IDs are recorded in the cleanup ledger.
Owner removal hides posts but preserves revision files; only those verified QA
tombstones with no existing schedule are assigned a cleanup deadline. Actual timed
uploads keep their original deadlines so the live cron path remains a real test.

## Final Gate Results

- All five synthetic posts reached `removed` with `purged_at` set by the real
  scheduled worker. All 21 inventoried R2 objects independently returned missing;
  each authenticated download returned 404. Audit tombstones are retained.
- Post-cleanup health: original eight featured entries, 674 gallery entries, zero
  timed releases, test authentication disabled, original GitHub session accepted.
- Full desktop regression: 1,068 tests passed in 139.699 s using a stable temporary
  directory, matching the CI configuration. An earlier run exposed an obsolete
  theme assertion and one transient activation-fixture storage error. The theme
  assertion now permits only the explicit Apex/Night City frame insets; custom
  surface hooks remain empty. Activation passed alone and in the full repeat;
  no activation production code was changed.
- Worker typechecking and the existing QML lint gate passed. QML reports the usual
  unqualified context-property warnings. Python also reports existing shutdown
  resource warnings; these are not counted as clean diagnostics.
- Personal keys, receipts, cached sessions and all test payloads remain outside
  staged source and updater inputs. No key is needed in the publication checkout.

Fresh interactive
GitHub authorization is unchanged and was not repeated; account exchange and
expiry failures are covered by the isolated Worker tests. Detailed server errors
can remain English even when native labels are Korean.
