# KFPS Supporter Activation Worker

Isolated Cloudflare Worker and D1 service for two private KFPS operations:

1. Anonymous supporter-key activation and registration recovery.
2. Encrypted Ko-fi payment-event intake for the local operations console.

This folder is deliberately separate from editor, generator, import/export, and release application code.

## Activation Data

Activation requests and D1 rows contain only:

- deterministic 64-character key ID;
- SHA-256 of the existing supporter-key signature;
- random client device ID;
- status and timestamps;
- duplicate-attempt and reset counters.

They do not contain supporter name, email, purchase ID, Windows account, computer name, hardware serial, artwork, or file path. The existing `.kfpskey` format is unchanged. The Worker uses a separate activation-only RSA key and never receives the supporter-key issuing private key.

Public activation routes:

```text
GET  /v1/health
POST /v1/activate
POST /v1/status
POST /v1/deactivate
```

Requests are schema checked and size bounded. A valid first device receives a signed receipt. At startup, a matching key proof receives a signed active or revoked status bound to its device ID and fresh nonce. A valid second device receives a signed duplicate decision. Unknown IDs and wrong proofs receive a generic unsigned denial and do not increase duplicate counters.

## Encrypted Ko-fi Inbox

Ko-fi posts payment data to:

```text
POST /v1/kofi/webhook
```

The Worker validates Ko-fi's verification token, bounds every field, splits the event into small records, and encrypts each record with a dedicated 3072-bit RSA-OAEP-SHA256 public key. D1 stores:

- SHA-256 of Ko-fi's `message_id` as the event primary key;
- encrypted payload chunks;
- received and imported timestamps.

The Worker sees webhook plaintext transiently while validating and encrypting it. It never logs the request body. D1 does not store readable name, email, purchase ID, message, amount, or product fields. Only the separate Desktop operations console has the matching private decryption key.

Repeated deliveries with the same `message_id` are idempotent. Imported rows are marked acknowledged rather than deleted, preserving encrypted audit/recovery state.

## Admin API

```text
GET  /v1/admin/licenses
POST /v1/admin/licenses/import
POST /v1/admin/licenses/mutate
GET  /v1/admin/kofi/events
POST /v1/admin/kofi/ack
```

Every admin request uses a timestamped HMAC-SHA256 signature over method, exact path/query, timestamp, unique request ID, and body hash. Mutation request IDs are stored to reject replay. License key IDs and Ko-fi event IDs stay in signed JSON bodies for mutations rather than routine request paths.

Use only the separate `KFPS Operations Console`. Do not expose admin routes through an unauthenticated proxy or public dashboard.

## Required Bindings And Secrets

`wrangler.jsonc` declares:

```text
DB                            D1 binding
ACTIVATION_KEY_ID             non-secret protocol key ID
ADMIN_HMAC_SECRET             Worker secret
ACTIVATION_PRIVATE_KEY_PEM    Worker secret
KOFI_VERIFICATION_TOKEN       Worker secret
KOFI_INBOX_PUBLIC_KEY_PEM     uploaded as a Worker secret
```

The inbox public key is not confidential, but uploading it as a secret keeps multiline PEM out of config and deployment output. Neither private key belongs in this Worker folder.

## Local Development

```powershell
cd "C:\Users\Hestia\Desktop\KFPS DIRTY\tools\supporter_activation_worker"
npm ci
npm run migrate:local
npm run dev
```

Local values belong in ignored `.dev.vars`. The console writes that file through `Settings > Write Local Test Secrets`.

Validation:

```powershell
npm run typecheck
npm test
npx wrangler deploy --dry-run
```

Tests cover atomic activation claims, same-device repair, simultaneous claims, signed startup status and duplicate/revoked decisions, invalid-proof privacy, admin authentication, import/list/reset/conflict clearing, Ko-fi token rejection, encrypted-at-rest storage, duplicate webhooks, list/ack flow, and long-field encryption bounds.

## Production

Current production base URL:

```text
https://kfps-supporter-activation.hestia-cummings.workers.dev
```

Keep the Worker URL enabled and set to **Public**. Do not enable Cloudflare Access for this hostname: KFPS and Ko-fi do not perform an Access login, and the admin routes already require timestamped HMAC authentication. Version preview URLs are disabled in `wrangler.jsonc`.

Before deploying:

1. Log in to the intended Cloudflare account.
2. Create D1 `kfps-activation` once.
3. Replace the placeholder D1 UUID in `wrangler.jsonc`.
4. Put the real Ko-fi verification token into the console's Fulfillment Settings.
5. Run the guarded deployment helper from `KFPS Activation Admin`.
6. Configure Ko-fi with `/v1/kofi/webhook` on the deployed HTTPS base URL.
7. Test Ko-fi intake and activation before enabling the KFPS client endpoint.

Complete instructions are in:

```text
C:\Users\Hestia\Desktop\KFPS Activation Admin\DEPLOYMENT.md
```

## Operational Rules

- Never log request bodies, key proofs, customer fields, full headers, IP addresses, or user agents.
- Never add readable customer identity to D1.
- Never classify network/server failures as duplicate activation.
- Never delete an activation allowlist row during reset; clear its device assignment.
- Clear duplicate counters independently from registration, revocation, and restore actions.
- Back up D1 and both private RSA keys separately in encrypted storage.
- Keep this service isolated from unrelated KFPS application updates.

Revocation removes a protected receipt the next time that KFPS starts and verifies a signed revoked status. A computer kept offline cannot receive that status. Registration reset remains separate and does not revoke an existing receipt.
