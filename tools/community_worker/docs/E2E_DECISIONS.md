# Community E2E Decision Record

## 2026-08-28: Recover The Worker And Automate The Real Client Boundary

### Goal Check

The active goal is automatic validation of the complete KFPS Community workflow
against a disposable real Worker. The implementation remains limited to the
Community Worker boundary, KFPS Community tests, and CI orchestration.

### Evidence Found

- The authoritative Worker source survived in the 2026-08-23 project archive.
- Its 39 Worker tests and TypeScript check passed before import.
- The KFPS Community suite passed 20 tests and skipped one opt-in live workflow.
- The skipped workflow assumed pre-seeded external state, hardcoded KFPS 3.0.81,
  and used catalog scope indexes that no longer matched the application.

### Alternatives Considered

1. Keep the Worker in an untracked standalone Desktop repository. This preserves
   physical separation but cannot provide reproducible fresh-clone or pull-request
   validation because that repository had no commits or remote.
2. Replace the Worker with a fake HTTP server. This is smaller but cannot test D1,
   R2, Wrangler bindings, migrations, Worker validation, or cleanup behavior.
3. Import the independently deployable Worker under `tools/community_worker` and
   run it locally from KFPS CI. This keeps runtime/deployment boundaries while
   making the contract reproducible. This option was selected.

### Assumptions Corrected

- The Worker source was archived, not missing.
- Invalid uploads are rejected before persistent storage rather than retained as
  downloadable quarantine objects. Worker tests directly verify empty R2 state.
- Featured, Browse, Handmade, Toolmade, Supporters, Favorites, Following, and My
  Uploads have distinct current indexes; the old test had drifted.
- Clearing supporter verification does not release the account's entitlement ID.
  Re-verification must use the same entitlement until an explicit administrative reset.

### Complexity And Value

The added infrastructure is one imported Worker project, one local runner, one
isolated E2E module, and one CI job. It replaces manual servers, permanent fixture
state, and an opt-in skipped test. The verified value is direct: fresh migrations,
real KFPS requests, D1/R2 behavior, version gating, supporter access, and teardown
now execute together.

### Continue Or Stop

Continue through repeatability, concurrent isolation, complete project tests, and
fresh-clone CI validation. Do not change production Community behavior or deploy
until those gates pass and the user explicitly requests promotion.

## 2026-08-28: Final Validation Lookback

### Result

- Three consecutive fresh-state runs passed.
- Two disposable runners passed concurrently without sharing ports or state.
- A clean-source clone passed dependency installation, Worker checks, migrations,
  fixture seeding, KFPS client workflows, teardown, and cleanup.
- All 39 Worker tests and all 544 KFPS tests passed. One unrelated Windows
  loopback test failed once, then passed alone and in the complete rerun.
- The Community Worker's test toolchain was updated to versions with zero known
  npm audit findings; the Worker still has no production runtime dependencies.

### Lifecycle Defects Found

- KFPS could request supporter verification before a newly authenticated account
  had chosen its required Community username.
- A rejected supporter verification could remain pending indefinitely.
- A stale supporter-clear request could race a rapid local reactivation.

All three cases now have focused regression coverage and pass through the real
client-to-Worker path. Complexity remains proportional to verified value, so the
current architecture should stop here until production promotion is explicitly
requested.
