# Community Worker Import Manifest

The Community Worker was recovered from the standalone project snapshot archived
on 2026-08-23 and imported into KFPS for reproducible application-to-service
validation. The Worker remains independently deployable and has its own package,
migrations, tests, configuration, and license.

## Included

- `src/`: Worker implementation
- `migrations/`: complete D1 migration chain
- `test/`: D1/R2 Worker integration tests
- `tools/`: fixture, maintenance, and disposable E2E tools
- `docs/`: API, deployment, security, and content-policy documentation
- `package.json` and `package-lock.json`: locked Node.js dependencies
- `tsconfig.json`, `vitest.config.ts`, and Wrangler configurations
- `.dev.vars.example`, `README.md`, and `LICENSE`

## Explicitly Excluded

- `.dev.vars` and `.deploy.secrets`
- `.wrangler`, `local-data`, and all local D1/R2 state
- `node_modules`
- Worker and runtime logs
- generated previews or catalog content
- the standalone snapshot's `.git` directory
- launchers whose paths referenced the former Desktop layout

The disposable E2E runner generates its own signing key, Worker variables,
database, object storage, ports, accounts, and artwork fixtures for every run.
It has no production credentials and uses `wrangler.e2e.jsonc`, whose bindings
cannot address the production D1 database or R2 bucket.
