# KFPS Supporter Compatibility And Recognition Worker

## Current Policy

The locally tested theme-only implementation retires PC registration and duplicate
enforcement. Existing signed keys unlock themes locally; the new client does not
poll activation/status or require an activation grace period. Local tools remain
free. New key creation, automatic fulfillment and email delivery are retired from
the private Operations Console.

This Worker retains old-client signed responses, registered-key Community
recognition, authenticated administrative operations and encrypted historical
Ko-fi intake. Retaining an API is not a promise to sell, create or deliver keys.
This document describes source behavior, not a completed deployment.
[Theme-only policy and tests](docs/THEME-ONLY-KEYS.md) are the detailed route contract.

## Public Compatibility Routes

```text
GET  /v1/health
POST /v1/activate
POST /v1/status
POST /v1/deactivate
POST /v1/community-entitlement
```

The three legacy activation routes keep protocol-1 request/response shapes so old
clients can verify signatures. The device field is format-checked and echoed as
required by those formats, but is not stored, compared or used for eligibility.
Registered active proofs receive their compatible signed responses; revoked,
unknown or wrong proofs remain denied as defined in the route contract. These
routes perform no registration, counter, timestamp or revocation writes and
produce no duplicate decision. Deactivation acknowledges an old client's local
receipt removal; it does not release a Community account binding.

Historical device IDs, activation timestamps and counters remain in D1 unchanged.
They are retained records, not current public enforcement inputs. Key proof
authentication, exact schemas, request limits and RSA response signatures remain.

## Community Recognition

`POST /v1/community-entitlement` accepts the exact device-free request or the
legacy request with a valid device field that is then discarded. The issuer
checks the registered license, active status, matching key-signature proof and
Community subject format. Neither a stored device nor `activated_at` is required.

An atomic parameterized claim binds one license to one exact Community subject
hash and one opaque entitlement ID. Same-subject retries reuse that ID; another
subject receives a conflict even from another machine or with a fresh nonce.
Invalid proof, unknown license and revoked status cannot claim an account.

A successful response contains the unchanged 15-minute signed v1 `entitlement`.
A separately signed `legacy_verified_grant` is included only when trusted stored
registration time satisfies an explicitly reviewed cutoff. Both envelopes have
exactly paired subject, entitlement ID, nonce, issue time and expiry. They contain
no key ID, device identity or purchaser identity.

The issuer does not authenticate the GitHub login. The Community service must
authenticate the account and verify both signatures, paired fields, lifetime and
the same configured cutoff before storing a permanent grant. A v1 entitlement,
local key presence or a newly minted proof date alone cannot create Verified.
[Legacy Verified grant](LEGACY-VERIFIED-GRANT.md) and the
[Community contract](../community_worker/contracts/README.md) define this boundary.

Existing durable grants survive ordinary proof expiry, sign-out and local key
removal; suspension and ownership protections still apply. Default Community
policy and cutoff selection remain coordinated rollout decisions.

## Encrypted Ko-fi Inbox

`POST /v1/kofi/webhook` remains a compatibility intake route. It validates the
verification token and bounded fields, then encrypts chunks with a dedicated
3072-bit RSA-OAEP-SHA256 public key. D1 retains hashed event IDs, encrypted payloads
and received/imported timestamps. Duplicate delivery is idempotent; acknowledgement
does not delete historical encrypted records.

The Worker sees plaintext transiently during validation/encryption but does not
log request bodies or store readable customer fields. The separate private
operations environment retains the decryption key. The retired console does not
automatically import, fulfill or email a new key from these events. Review the
external product listing and webhook disposition explicitly before launch; do not
reintroduce the archived fulfillment/deployment utilities.

## Admin API And Secrets

Retained routes:

```text
GET  /v1/admin/licenses
POST /v1/admin/licenses/import
POST /v1/admin/licenses/mutate
GET  /v1/admin/kofi/events
POST /v1/admin/kofi/ack
```

Every admin request uses timestamped HMAC-SHA256 over method, exact path/query,
timestamp, unique request ID and body hash. Mutation replay protection remains.
The `reset_community` operation releases only the opaque account binding; it does
not restore a revoked license or clear unrelated historical fields. Administrative
maintenance is not a newly exposed public or console key-creation workflow.

Required binding/secret names remain `DB`, `ACTIVATION_KEY_ID`,
`ADMIN_HMAC_SECRET`, `ACTIVATION_PRIVATE_KEY_PEM`, `KOFI_VERIFICATION_TOKEN` and
`KOFI_INBOX_PUBLIC_KEY_PEM`. The inbox public key is stored as a Worker secret to
keep multiline PEM out of configuration/output. The supporter-key issuing private
key and inbox decryption private key never belong in this Worker source or a bundle.
Never publish real values, request bodies, key proofs, customer records or raw logs.

## Local Validation

Use the existing isolated runner described in
[the theme-only test instructions](docs/THEME-ONLY-KEYS.md). It generates synthetic
signing keys, uses local emulated D1, disables remote bindings and isolates caches
and logs. The focused theme-only/security checkpoint passed 110 tests and type
checking; this is not production validation.

Do not obtain local test secrets from the retired console workflow or use real
customer records. `npm run typecheck`, `npm test` and the existing local test
configuration remain source validation tools; deployment is a separate action.

## Current Deployment And Rollback Gates

1. Freeze the reviewed issuer/client/Community contract and preserve the previous
   deployed version, D1 schema/data, bindings and recoverable secret configuration.
   Document any backup/export limitation before approval. Protect backups from
   public source and artifacts.
2. Use the existing authorized Worker and D1 bindings. Do not recreate production
   D1, reset licenses, import new keys or rotate secrets merely to deploy this
   compatibility change. It requires no issuer schema migration or record rewrite.
3. Keep the cutoff unset until an explicit historical-cohort review approves one
   canonical value for both issuer and Community. An absent cutoff intentionally
   omits the optional permanent-grant proof; it does not break the v1 response.
4. The release owner uses the existing reviewed Worker deployment tooling
   (`npm run deploy` invokes Wrangler). Do not run an archived console helper,
   use Fulfillment Settings or enable a key-delivery job. Publish the compatible
   issuer before distributing the device-free recognition client.
5. Coordinate Community additive migrations, indexing/backfill, policy activation
   and rollback separately through [ROLLOUT.md](../community_worker/contracts/ROLLOUT.md).
   Preserve account identity, uploads, license/account bindings and permanent grants.
6. Verify deployed health and old/new-client response/signature compatibility
   without real purchases, customer mutations or fabricated public artwork.
   Public client routes must remain reachable without an interactive Cloudflare
   Access login; admin routes still require their existing HMAC authentication.
7. Record exact deployed identities and rollback steps. Restoring older issuer
   code can reintroduce its device precondition for new clients; coordinate any
   rollback instead of restoring the whole live database or deleting newer records.
8. Retire or revise the former key-sale/delivery promise on the external storefront
   as part of launch. Optional donations do not promise new keys or Verified access.

Server revocation still denies recognition and affects compatible old-client
online status checks. It does not remotely remove the new client's locally
validated theme entitlement or erase an existing permanent Community grant.
No live service, storefront, credentials or customer data is changed by this guide.
