# Deployment

## Cloudflare Resources

Create one D1 database and one private R2 bucket dedicated to this service. Do not
reuse the supporter activation database, Worker, bucket, secrets, or routes.

The Supporters scope does depend on the activation Worker's public
`/v1/community-entitlement` contract. Deploy activation migration `0003` and its
Worker code before deploying the Community migration/code in this folder. The two
services still retain separate databases, secrets, and responsibilities.

```powershell
npx wrangler d1 create kfps-community
npx wrangler r2 bucket create kfps-community-assets
npm run migrate:remote
npx wrangler deploy --secrets-file .deploy.secrets
```

Copy the D1 ID returned by Cloudflare into `wrangler.jsonc`. The checked-in
production policy disables local test authentication and publishes uploads only
after server validation succeeds:

```json
"ALLOW_TEST_AUTH": "0",
"AUTO_APPROVE_TEST_UPLOADS": "0",
"AUTO_PUBLISH_VALIDATED_UPLOADS": "1",
"MINIMUM_UPLOAD_VERSION": "3.0.81",
"COMPATIBILITY_MINIMUM_UPLOAD_VERSION": "3.0.81",
"REQUIRE_MODERN_UPLOAD_CLIENT": "0",
"VERSION_SYNC_ENABLED": "1",
"VERSION_REPOSITORY": "heyitshestia/kloudys-forza-painter-suite",
"VERSION_BRANCH": "main"
```

Set `AUTO_PUBLISH_VALIDATED_UPLOADS` to `0` to restore manual quarantine for new
uploads and revisions without changing code. Existing published artwork is not
altered by that switch.

`MINIMUM_UPLOAD_VERSION` is the fallback used before D1 contains a version policy.
It must be a numeric three-part version. The scheduled trigger resolves the official
repository branch to a commit, reads `VERSION` at that commit, and stores a newer
floor in D1. It never automatically lowers the floor. Modern clients below it
receive HTTP 426; browsing and downloads are unaffected. A versionless upload is
accepted only by the explicit legacy bridge described below.
Use `/admin > Version policy` to inspect provenance, sync immediately, pause, or
perform an explicit rollback.

Keep `REQUIRE_MODERN_UPLOAD_CLIENT` at `0` throughout the compatibility rollout.
This bridge accepts only the exact older request shape where both
`client_version` and `classification` are absent, and records it as a legacy
Toolmade listing. Modern clients at or above
`COMPATIBILITY_MINIMUM_UPLOAD_VERSION` also remain able to upload even if the
synchronized future floor has advanced. A partial or invalid modern declaration
is still rejected.
After the updated KFPS release is broadly available, set it to `1` in a separate
staged deployment so both fields become mandatory server-side.

Before the first deployment, create `.deploy.secrets` beside `wrangler.jsonc` with
one random admin token of at least 32 characters. This file is ignored by Git:

```text
ADMIN_TOKEN=replace-with-a-long-random-production-token
```

Wrangler requires the secrets file for the first deployment because the Worker
does not exist yet. After that first deployment, rotate the token with
`npx wrangler secret put ADMIN_TOKEN` and use `npm run deploy` for later releases.

## Supporter Entitlement Trust

`SUPPORTER_ENTITLEMENT_KEY_ID` and `SUPPORTER_ENTITLEMENT_MODULUS_HEX` are public
verification values, not secrets. They must match the activation signing key used by
the separately deployed activation Worker. Never place the activation private key in
this project or in the Community Worker.

Production rollout order:

1. Back up both D1 databases.
2. Apply activation Worker migration `0003_community_entitlements.sql` remotely.
3. Deploy the activation Worker and verify `/v1/health` plus a staging entitlement.
4. Apply Community migrations `0007_version_policy.sql` and
   `0008_supporter_catalog.sql` remotely.
5. Deploy this Worker, open `/admin`, and run **Sync official VERSION**.
6. Verify ordinary Browse cannot see a supporter fixture and a verified staging
   account can browse, preview, and download it.
7. Release the KFPS client only after both Workers pass those checks.

Rollback the KFPS client first if needed. Existing public behavior remains available
without supporter verification. A JSON already downloaded to a user's computer
cannot be remotely recalled.

## GitHub Identity

Register a dedicated GitHub OAuth application and enable Device Flow. The desktop
application uses the public client ID to obtain a GitHub user token. It exchanges
that token once with `/v1/auth/github`; the Worker verifies it with GitHub and then
discards it. Only the hashed community session remains in D1.

Set the OAuth application's public client ID in `GITHUB_CLIENT_ID` under `vars` in
`wrangler.jsonc`. A client secret is not used by Device Flow and must never be
included in KFPS, this Worker, or repository settings. Follow
[GITHUB_LOGIN.md](GITHUB_LOGIN.md) for registration and local testing.

## Connect The Desktop Client

After the production Worker is deployed and its health endpoint responds, put its
versioned API URL in `KFPS DIRTY/data/community_api_url.txt` for the app test:

```text
https://your-community-worker.workers.dev/v1
```

The packaged text file is the only production endpoint setting in KFPS. The
`KFPS_COMMUNITY_API_URL` environment variable takes priority for local or staging
tests. Keep the text file on the local `127.0.0.1` URL until production resources,
moderation access, GitHub sign-in, and backups have all been tested.

Use [STAGING.md](STAGING.md) before any production migration or deployment. Its
configuration and validator refuse production binding reuse and do not change the
packaged KFPS endpoint.

## Public Repository

The service can be published in its own public GitHub repository. Keep deployment
manual until test and production Cloudflare resources are distinct. Repository
Actions must have access only to this community Worker and never to the KFPS repo.

## Backup And Recovery

- Export D1 metadata on a schedule.
- Enable R2 object retention appropriate to moderation and deletion policy.
- Keep object keys immutable by artwork ID and revision.
- Test restoring D1 into a staging database before opening public uploads.
