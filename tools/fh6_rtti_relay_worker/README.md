# KFPS FH6 RTTI Relay Worker

This isolated Cloudflare Worker accepts privacy-safe FH6 locator profiles from enrolled calibrator helpers and serves the canonical `RTTI.dat` registry to KFPS clients.

It does not share a database, secret, route, or runtime dependency with supporter activation or the Community Library.

## Security model

- The normal helper package contains a random, expiring, reusable auto-enrollment campaign code with a fixed device limit.
- Every new Windows installation silently registers as its own named helper and receives a unique random device credential once.
- The calibrator protects that credential with Windows DPAPI.
- The administrator can revoke or rename each registered PC independently. Revoking or rotating the campaign stops its file from registering additional PCs without disabling devices that are already enrolled.
- A named, expiring, single-use enrollment remains available for targeted recovery and device resets.
- Only complete, high-confidence six-step profiles are accepted.
- The Worker recomputes the profile ID, strips unrecognized fields, rate-limits writes, and records accepted and rejected submissions.
- Revoking a helper blocks future submissions immediately. Resetting enrollment invalidates the old device credential.
- Public clients can only read the normalized `RTTI.dat` registry.
- New normalized registry content is placed in a durable D1 outbox and dispatches
  the GitHub fallback-sync workflow. Exact duplicate profiles do not dispatch,
  and a backlog of profile updates is coalesced into one full-registry sync.
- GitHub delivery failures never reject an otherwise valid RTTI profile. They
  remain visible through the authenticated `/v1/admin/github-sync` endpoint and
  are retried on a later publication; GitHub also performs one daily safety sync.

The reusable campaign code is an invitation embedded in the portable helper folder, not an administrator credential. Anyone who obtains that folder can claim one of its remaining device slots until the campaign expires, is revoked, or its code is rotated. Keep the campaign bounded and send the folder only to intended helpers.

## Local checks

```powershell
npm ci
npm run migrate:local
npm test
npm run typecheck
npm run dev
```

## Production deployment

The D1 database is `kfps-fh6-rtti`. Set a unique `ADMIN_HMAC_SECRET` of at least 32 characters. Create a fine-grained GitHub token restricted to `heyitshestia/kloudys-forza-painter-suite` with only `Contents: read and write`, then store it as the `GITHUB_RTTI_SYNC_TOKEN` Worker secret. Apply all remote migrations before deploying the Worker, then bootstrap the checked-in `RTTI.dat` through the authenticated admin endpoint. Create and rotate bounded auto-enrollment campaigns from the Operations Console rather than placing the administrator secret in a helper package.

Deployment order:

```powershell
npx wrangler d1 migrations apply kfps-fh6-rtti --remote
npx wrangler secret put GITHUB_RTTI_SYNC_TOKEN
npx wrangler deploy
```

The GitHub credential is used only to create the
`fh6-rtti-registry-updated` repository dispatch event. GitHub performs the
validated `RTTI.dat` commit with its own short-lived workflow token.

Do not reuse the supporter activation or Community Library secrets.
