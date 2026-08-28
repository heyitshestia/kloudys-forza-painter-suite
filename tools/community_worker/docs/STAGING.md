# Isolated Community Staging

Staging uses a different Worker name, D1 database, R2 bucket, admin token, test
authentication token, and supporter test key from production. The checked-in
example contains no usable Cloudflare resource identifier. No staging command is
run by KFPS, its updater, CI, or the local end-to-end runner.

## Prepare

The normal path creates dedicated resources and a sanitized recovery report:

```powershell
py -3.12 tools\provision_staging_with_report.py
```

The equivalent manual Cloudflare commands are:

```powershell
npx wrangler d1 create kfps-community-staging
npx wrangler r2 bucket create kfps-community-assets-staging
```

Pass the returned D1 UUID to the preparation tool:

```powershell
py -3.12 tools\prepare_staging.py --database-id STAGING-D1-UUID
```

The tool refuses production identifiers, requires `staging` in every resource
name, generates separate ignored secrets, and writes ignored
`wrangler.staging.jsonc` plus `.staging/`. It does not contact Cloudflare.
Staging reuses only the production public GitHub OAuth application ID so the
normal device-login path can be tested; no production private token or signing
key is copied.

## Deploy And Validate

Review the generated files, then apply migrations and deploy explicitly:

```powershell
npx wrangler d1 migrations apply DB --remote --config wrangler.staging.jsonc
npx wrangler deploy --config wrangler.staging.jsonc --secrets-file .staging\deploy.secrets
py -3.12 tools\run_kfps_staging_e2e.py --api-url https://STAGING-WORKER.workers.dev/v1 --repetitions 3
```

For the normal deployment path, use the reporting wrapper after preparation. It
applies migrations, deploys, runs three remote repetitions, redacts generated
secrets, verifies the report contains none of those values, and always writes a
diagnostic ZIP under `Community-Deployment-Reports`. The report includes source,
platform, tool-version, migration, deployment, public-state, and per-run evidence:
The wrapper waits up to 90 seconds for workers.dev propagation and records every
health/config readiness attempt before starting destructive test workflows.

```powershell
py -3.12 tools\deploy_staging_with_report.py --api-url https://STAGING-WORKER.workers.dev/v1
```

Validate the public GitHub device application plus a real Worker session using
the deployment machine's secure GitHub CLI login. The report stores no account
identifier or credential:

```powershell
py -3.12 tools\validate_github_auth.py --api-url https://STAGING-WORKER.workers.dev/v1 --expected-environment staging
```

Force one exact repository version lookup and restore staging's paused policy:

```powershell
py -3.12 tools\validate_version_sync.py --api-url https://STAGING-WORKER.workers.dev/v1 --expected-environment staging
```

The validator refuses non-HTTPS URLs, Workers that do not identify themselves as
`staging`, mismatched KFPS versions, strict modern-only upload policy, disabled
test authentication, and staging configurations that overlap production. Its
test-auth token is sent only to the staging `/v1/auth/test` request. Production
keeps that route disabled and does not define the staging secret.

Staging is disposable. Delete its Worker, D1 database, and R2 bucket after the
validation window. Never change the production endpoint file in a test package;
the staging validator uses an explicit command-line URL and process environment.

## Rollout Compatibility

Production starts with `REQUIRE_MODERN_UPLOAD_CLIENT=0`. Existing KFPS clients
that predate upload classifications send neither `client_version` nor
`classification`; the Worker accepts only that exact legacy combination and
stores it as Toolmade. Updated clients still send and validate both fields. Browse,
preview, authenticated download, and existing sessions remain on `/v1`.
Declared clients at or above `COMPATIBILITY_MINIMUM_UPLOAD_VERSION=3.0.81` remain
accepted during this bridge even when repository synchronization has recorded a
newer future floor.

After the compatible KFPS build is broadly available and old upload support is no
longer needed, change only `REQUIRE_MODERN_UPLOAD_CLIENT` to `1`, rerun all tests,
stage the change, and deploy. That later switch affects uploads only.

## Production Promotion

After every staging, GitHub-authentication, and version-sync gate passes, use the
guarded production command. It exports D1 to the private ignored backup folder,
records the current Worker version, verifies secret retention by name, deploys,
waits for health/config/catalog compatibility, and automatically rolls the Worker
back if those gates fail:

```powershell
py -3.12 tools\deploy_production_with_report.py `
  --api-url https://kfps-community-library.hestia-cummings.workers.dev/v1 `
  --confirm-production kfps-community-library
```
