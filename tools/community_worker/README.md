# KFPS Community Library

Independently deployable community catalog service for sharing import-ready Forza
vinyl JSONs. Its source lives in the KFPS repository so the application and its
real service contract can be validated together.

## Boundaries

- The Worker does not modify or deploy the KFPS application.
- It has its own versioning, database, object storage, tests, and deployment.
- KFPS is an ordinary HTTPS client of the versioned `/v1` API.
- Supporter keys and activation receipts are never accepted as community credentials.
- Source images, generator reports, settings, local paths, and personal files are not uploaded.

## Included Features

- Anonymous browsing, search, categories, game filters, previews, and pagination
- A dedicated eight-slot Featured gallery, with an admin-enforced slot cap
- Trending, newest, download, favorite, and alphabetical sorting for the main catalog
- GitHub identity exchange plus local test authentication
- Unique, case-insensitive, one-time community usernames with exact double confirmation
- Creator profiles, follows, favorites, account-private creator ignoring, and personal upload views
- Browse-all, Handmade, Toolmade, and server-enforced Supporters catalog views with search constrained to the active view
- Sanitized JSON uploads, immutable revisions, full inspection previews, compact
  catalog thumbnails, and downloads
- Mandatory uploader classification and repository-synchronized minimum-KFPS-version enforcement for uploads
- Scheduled, D1-backed VERSION synchronization with commit provenance, admin sync/pause/rollback, and no automatic downgrade
- Short-lived supporter verification bound to one Community account without sending supporter keys, receipts, purchaser identity, or device identity to this service
- Authenticated JSON downloads with per-account daily popularity counting
- Server-side source-schema and game-origin detection; uploaders do not choose compatibility labels
- Explicit compatibility acknowledgement for structurally valid but unrecognized JSON formats
- Exact semantic-design and preview duplicate detection
- Validated immediate publication, private reports, owner removal, suspensions, and audit events
- D1-backed abuse throttles and strict request, field, JSON, shape, and PNG limits
- R2 asset hashes, generated object keys, MIME hardening, and atomic database publication
- Browser-based moderation, Featured-slot tracking, and VERSION-policy console at `/admin`
- Owner tag editing plus administrator-only Handmade/Toolmade reclassification

## Disposable End-to-End Test

Requirements: Node.js 20 or newer and Python 3.12 with the locked KFPS
dependencies installed. From the KFPS repository root, run:

```powershell
py -3.12 tools\community_worker\tools\run_kfps_e2e.py
```

Windows users can also open `Run_Community_E2E.bat` in this directory. The runner
creates a new local D1 database, R2 bucket state, ports, accounts, catalog fixtures,
and supporter signing key for each run. It starts the Worker without opening a
window, runs the real KFPS Community client workflows, stops the Worker, and
deletes successful state. It retains only local failure evidence under
`runtime/community-e2e`; CI uploads only sanitized Worker, fixture, and KFPS test
logs, never generated environment or key files.

The runner cannot address production storage because it uses
`wrangler.e2e.jsonc`, which contains separate binding names and a non-production
database identifier. It does not require a real Community account, supporter key,
GitHub login, Cloudflare login, or production secret. See
[`docs/E2E.md`](docs/E2E.md) for the scenario and cleanup contract.

Test packages include `Run_Community_Validation.bat` at the KFPS application root.
It uses bundled Python when present, checks Node.js/npm, prints the relevant KFPS,
Windows, CPU, GPU, RAM, runtime, public endpoint, and file-hash details, performs
three clean runs, and creates a sanitized ZIP under `Community-Test-Reports`.

For manual Worker development only, copy `.dev.vars.example` to the ignored
`.dev.vars`, then run `npm ci`, `npm run migrate:local`, and `npm run dev` from
this directory. Manual state is separate from the disposable E2E runner.

## Verification

```powershell
npm run typecheck
npm test
py -3.12 tools\community_worker\tools\run_kfps_e2e.py
```

The Worker tests run against local D1 and R2 implementations. They cover identity,
immutable usernames, upload sanitization, concurrent duplicate rejection,
same-origin browser access, browsing, favorites, creator follows, downloads,
reports, owner removal, moderation, VERSION synchronization, supporter entitlement
tampering/expiry/account binding, and supporter-only catalog and asset isolation.

Updated clients explicitly declare `handmade` or `toolmade` and include a current
KFPS client version. During rollout, the exact older request shape that lacks both
fields remains accepted as Toolmade. Creators may change search tags later from **My uploads**, but
cannot change classification. The operator can correct classification from `/admin`;
the action is written to moderation history.

Featured supporter artwork exposes only its compact catalog thumbnail to visitors so
the curated gallery can be previewed. Its full preview, artwork detail route, and JSON
download remain restricted to a signed-in account with verified supporter access.
Featured artwork is removed from ordinary discovery lists while remaining available
in owner and favorite management views.

## Preview Maintenance

The authenticated maintenance API can replace preview and thumbnail derivatives
without changing an artwork's JSON, owner, revision, user-authored metadata, or
publication date. It also derives the read-only `uses_masks` catalog flag from the
validated design so clients can identify masked artwork without trusting a tag.
Run the catalog tool with the Python runtime from the KFPS version whose
renderer should become authoritative:

```powershell
& "..\KFPS CLEAN\python\python.exe" .\tools\rerender_catalog_previews.py --dry-run
& "..\KFPS CLEAN\python\python.exe" .\tools\rerender_catalog_previews.py
```

The tool reads the ignored production `ADMIN_TOKEN` from `.deploy.secrets`, checks
every stored design hash and revision, renders through KFPS upload validation, and
uploads only changed assets, or updates only mask metadata when the images already
match. Use `--artwork-id ID` for a targeted run or
`--status all` to include non-published records. The Worker validates PNG structure
and dimensions, rejects stale or duplicate replacements, swaps both R2 keys and D1
hashes together, retains the previous R2 derivatives for rollback, and records their
keys in a moderation event. Never distribute the token or the
maintenance script with populated secrets.

Signed-in users report somebody else's listing from its artwork details. Creators
remove their own listing from **My uploads**. Re-uploading the same validated design
from the same account restores an owner-removed listing with regenerated preview
assets; other accounts remain blocked. The operator reviews reports or removes any
published listing at `/admin`; moderation removal remains blocked from resubmission
while retaining its audit and duplicate history.

## Production Setup Summary

1. Create a D1 database named `kfps-community`.
2. Replace the placeholder D1 database ID in `wrangler.jsonc`.
3. Create an R2 bucket named `kfps-community-assets`.
4. Create an ignored `.deploy.secrets` containing a random `ADMIN_TOKEN` for the first deployment.
5. Keep test authentication disabled and set `AUTO_PUBLISH_VALIDATED_UPLOADS` to the intended production policy.
6. Set `MINIMUM_UPLOAD_VERSION` to the oldest KFPS version permitted to upload.
7. Keep `COMPATIBILITY_MINIMUM_UPLOAD_VERSION` at `3.0.81` during the rollout bridge.
8. Confirm `VERSION_REPOSITORY`, `VERSION_BRANCH`, and the scheduled trigger point to the official KFPS repository.
9. Match the supporter entitlement key ID and public modulus to the activation Worker.
10. Set `REQUIRE_MODERN_UPLOAD_CLIENT` to `1` only after that KFPS version is broadly available.
11. Register a GitHub OAuth application with Device Flow enabled and set its public client ID.
12. Deploy the activation Worker migration/code first, then apply this Worker's remote migrations and deploy it.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md), [docs/API.md](docs/API.md),
[docs/STAGING.md](docs/STAGING.md), and [docs/CONTENT_POLICY.md](docs/CONTENT_POLICY.md) before deployment. GitHub account
setup and local Device Flow testing are covered in [docs/GITHUB_LOGIN.md](docs/GITHUB_LOGIN.md). The complete
trust boundaries and production checklist are in [docs/SECURITY.md](docs/SECURITY.md).
Approved future work is tracked in [docs/BACKLOG.md](docs/BACKLOG.md).

## Licenses

Service code is MIT licensed. Uploaded artwork remains governed by the license the
creator selects and by the community publishing terms. This code repository does
not grant rights to third-party artwork, brands, characters, or game assets.
