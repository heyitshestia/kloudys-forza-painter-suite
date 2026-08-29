# API Contract

The current protocol is `/v1`. Error responses use:

```json
{"error":"stable_machine_code","message":"Short user-facing explanation."}
```

## Public

- `GET /v1/health`
- `GET /v1/config`
- `GET /v1/artworks`
- `GET /v1/artworks/{id}`
- `GET /v1/artworks/{id}/preview`
- `GET /v1/artworks/{id}/thumbnail`
- `GET /v1/creators/{username}`

Catalog parameters include `search`, `category`, `game`, `classification`, `sort`, `scope`, `creator`,
`page`, and `limit`. Public responses are paginated and never enumerate R2 keys.
`classification` accepts `handmade` or `toolmade`; omitting it returns both. Search,
tags, category, game, creator, sorting, and pagination are evaluated inside that
classification filter. Anonymous and ordinary `scope=browse` responses exclude
supporter-only metadata. `scope=supporters` requires both a Community session and
a current supporter verification.

## Authentication And Profiles

- `POST /v1/auth/github`
- `POST /v1/auth/test` when explicitly enabled locally
- `GET /v1/session`
- `DELETE /v1/session`
- `POST /v1/profile/username`
- `PATCH /v1/profile`
- `GET /v1/profile/ignored`
- `POST /v1/supporter/verify`

Authenticated requests use `Authorization: Bearer <community-session>`. GitHub
access tokens are verified once and are not stored. Community session tokens are
stored as SHA-256 hashes. Usernames are immutable after the first successful claim.
Signing out deletes the active server session as well as the DPAPI-protected local copy.
Username claims must send matching `username` and `confirm_username` values, including
capitalization. Missing or unequal confirmation returns `username_confirmation_required`
without claiming the name.

`POST /v1/supporter/verify` accepts only a short-lived RSA-signed entitlement from
the separate activation Worker. Its audience, Community user ID, nonce, issue time,
expiry, canonical encoding, key ID, and signature are verified. It contains an
opaque entitlement ID but no supporter key, receipt, purchaser identity, or device
identity. One activation license binds to one Community account until the operator
uses **Reset Community Link** in the private Operations Console.

## Community Actions

- `GET /v1/artworks/{id}/download`
- `POST /v1/artworks`
- `POST /v1/artworks/{id}/revisions`
- `PATCH /v1/artworks/{id}`
- `DELETE /v1/artworks/{id}`
- `POST /v1/artworks/{id}/favorite`
- `POST /v1/artworks/{id}/report`
- `POST /v1/creators/{username}/follow`
- `POST /v1/creators/{username}/ignore`

Every Community Action requires a valid Community bearer session. Catalog browsing,
public artwork metadata, creator profiles, previews, and thumbnails remain public. An
anonymous download request returns `authentication_required` without reading the
stored JSON object or incrementing its download count.

Ignoring is an account-private catalog preference. Authenticated catalog requests
exclude artwork from ignored creators across Featured, Browse, classification,
Supporters, Favorites, Following, and creator-filtered views. It does not delete
artwork, alter follow relationships, affect anonymous or other users, or block the
creator profile needed to reverse the choice. `GET /v1/profile/ignored` is
authenticated and returns only the requesting account's ignored-creator list.

Supporter-only metadata, detail, previews, thumbnails, and downloads require a
currently verified supporter session. Restricted assets return `private, no-store`
and unauthorized lookups return `artwork_not_found` rather than revealing that an
entry exists. Already-downloaded JSON files cannot be recalled remotely.

Uploads are canonicalized. The service retains supported shape geometry and
format metadata only; local paths and arbitrary metadata never enter stored JSON.
The service derives `source_schema`, `schema_known`, and `games` from the submitted
design instead of trusting uploader-supplied game labels. Known inputs include KFPS
primitive and Community JSON, Forza live type-code exports, KFPS save-library and
decoded-file exports, flat C_group JSON, and KFPS-converted FD6 JSON. A structurally
valid shape list with an unrecognized explicit format requires
`"confirm_compatibility": true`; otherwise the API returns
`unknown_schema_confirmation_required`. JSON without a usable shape list is rejected.
Full inspection previews and compact catalog thumbnails are separately validated,
hashed, and stored. Older uploads without a dedicated thumbnail fall back to the
full preview. When `AUTO_PUBLISH_VALIDATED_UPLOADS` is enabled, successful upload
and revision responses have `status: "published"` and `moderation_required: false`;
validation failures are rejected before catalog publication.

Every upload and revision must include `client_version` as a three-part KFPS
version and `classification` as exactly `handmade` or `toolmade`. New uploads may
also set `supporter_only: true`, but the server accepts that value only for a
currently verified supporter. Audience and classification are independent and
both are immutable to creators on active revisions. Classification remains
immutable on owner restores, while the creator may choose a new audience when
restoring their own removed listing. Restoring as supporter-only still requires
current supporter verification. A missing,
malformed, or older client version returns `client_update_required` with HTTP 426.
The effective minimum is exposed by `GET /v1/config` as
`minimum_upload_version`. During the compatibility bridge it comes from
`COMPATIBILITY_MINIMUM_UPLOAD_VERSION`; after strict rollout it comes from the
D1-backed active policy. `MINIMUM_UPLOAD_VERSION` is that policy's deployment fallback. The
scheduled Worker synchronizes against the official repository's commit-pinned
`VERSION` file, may raise but never automatically lower the floor, and retains the
last verified value on failure. Classification is immutable to creators and must match
the existing listing on revisions and owner restores. `PATCH /v1/artworks/{id}` is
owner-only, accepts exactly `{"tags":[...]}`, and does not alter the JSON, hashes,
revision number, or classification.

`REQUIRE_MODERN_UPLOAD_CLIENT=0` is a temporary deployment bridge for the release
that introduces these fields. In that mode only, a payload missing both new fields
is recorded as a legacy client and classified Toolmade, while declared clients use
the compatibility minimum. Set it to `1` only after the updated KFPS build is
broadly available and staged; strict mode uses the synchronized policy floor.

Artwork responses expose `source_schema`, `schema_label`, `schema_known`, and
`schema_warning`. `games` contains only detected game origins. Creator deletion is
a soft removal from active catalog access. A later `POST /v1/artworks` of the same
validated design by the same creator restores that artwork ID, may choose a new
audience, and replaces only its derived preview assets. Cross-account duplicates
and administrator-removed artwork remain blocked. Revision, hash, moderation, and
duplicate history remain available to the service operator.

## Administration

- `GET /v1/admin/queue`
- `GET /v1/admin/reports`
- `GET /v1/admin/artworks/{id}/preview`
- `POST /v1/admin/moderate`
- `POST /v1/admin/reports/resolve`
- `POST /v1/admin/users/action`
- `GET /v1/admin/version`
- `POST /v1/admin/version`

Open reports include the artwork state, preview lookup ID, shape count, and total
open-report count so the private console can highlight affected listings. Unknown
schemas carry a separate compatibility flag. Admin
requests require `X-Community-Admin-Token`. Production automation should
replace this human console token with signed short-lived administration sessions
before delegating moderation to multiple people.

The admin version route supports `sync`, `pause`, and an explicit `set` action.
Manual `set` may roll back the floor and pauses synchronization unless
`automatic: true` is supplied. Every action records moderation history. Queue and
report responses include `supporter_only` so restricted listings are labeled in
the moderation console.

`POST /v1/admin/moderate` also accepts `classify_handmade` and
`classify_toolmade`. These are the only post-upload classification changes; they
update the listing and revision manifests and create a moderation event.

`GET /v1/admin/queue` is a paginated artwork browser rather than a fixed
moderation slice. It accepts:

- `status`: `pending`, `published`, `rejected`, `removed`, or `all`;
- `classification`: `all`, `handmade`, or `toolmade`;
- `audience`: `all`, `everyone`, or `supporters`;
- `sort`: `latest`, `oldest`, `updated`, `downloads`, `favorites`, `reports`,
  `shapes`, or `name`;
- `search`, `page`, and `limit` (`limit` is capped at 100).

Responses include `total`, `page`, `page_size`, and `page_count`. Filtering,
searching, sorting, and pagination happen in D1 so the browser can reach every
artwork without loading every preview at once.
