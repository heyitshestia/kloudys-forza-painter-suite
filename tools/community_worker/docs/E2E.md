# Disposable Community End-to-End Validation

## Purpose

This test runs the real KFPS Community Python client against the real Community
Worker in an isolated local Cloudflare runtime. It catches contract and lifecycle
regressions that either project's unit tests cannot detect alone.

The runner is temporary. It is not a server that remains online, and it never
connects KFPS to the production Community catalog.

## One-Command Run

From the KFPS repository root:

```powershell
py -3.12 tools\community_worker\tools\run_kfps_e2e.py
```

`Run_Community_E2E.bat` provides the same operation for Windows.
The repository-root `Run_Community_Validation.bat` prefers bundled Python, prints
sanitized system and toolchain details, performs three fresh runs, and writes a
shareable diagnostic ZIP under `Community-Test-Reports`.

Useful diagnostic options:

```powershell
py -3.12 tools\community_worker\tools\run_kfps_e2e.py --repetitions 3
py -3.12 tools\community_worker\tools\run_kfps_e2e.py --keep-success
py -3.12 tools\community_worker\tools\run_kfps_e2e.py --skip-worker-checks --skip-install
```

## Lifecycle

For every repetition the runner:

1. Creates a uniquely named directory under `runtime/community-e2e`.
2. Generates a temporary RSA supporter key pair.
3. Applies all migrations to a new local D1 database.
4. Starts Wrangler on unused localhost HTTP and inspector ports.
5. Uses a dedicated local R2 state directory.
6. Seeds 16 deterministic public fixtures owned by two test creators.
7. Runs the real KFPS Community service against the local `/v1` API.
8. Terminates the complete Wrangler process tree.
9. Removes all successful test state after Windows releases SQLite handles.

Failed runs retain their directory and Worker, fixture, and KFPS test logs for
diagnosis. Generated environment files and supporter keys are local test material
and are never uploaded by CI.

## Covered Workflows

- Empty-database migration and Worker startup
- Health, configuration, and current KFPS version agreement
- Local test authentication, permanent username selection, profile update, and sign-out
- Handmade and Toolmade catalog filtering
- Upload, metadata edit, semantic duplicate rejection, download, and checksum validation
- Revision publication
- Favorites, creator follows, and private reports
- Owner removal and same-owner resubmission
- Unknown-schema acknowledgement
- Exact pre-classification KFPS upload compatibility during the rollout bridge
- Generated, account-bound supporter verification
- Supporter-only upload and denial after local entitlement removal
- Deliberately stale KFPS upload rejection
- Invalid local JSON rejection without catalog publication

Worker-level tests additionally inspect D1 and R2 directly. They verify that
corrupt previews are rejected before object storage, concurrent upload losers are
cleaned, moderation state is preserved, supporter tokens cannot be reused across
accounts, and version synchronization never lowers the accepted version silently.

## Safety Boundary

- `wrangler.e2e.jsonc` contains no production database or bucket identifiers.
- Wrangler is always invoked with `--local` and a unique `--persist-to` directory.
- The runner generates all tokens and signing material for that run.
- Local test authentication is protected by a generated per-run token.
- GitHub authentication is not contacted; identity is local-test only.
- The production Worker URL is never read by the runner.
- CI artifacts include only `*.log` process output, never generated environment or key files.

Any change that introduces `--remote`, a production binding identifier, or a
production service URL into this runner should fail review.

Remote validation is a separate explicit workflow described in
[`STAGING.md`](STAGING.md). It cannot be selected accidentally from this runner.
