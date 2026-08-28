# Community Library Backlog

This file records approved future work only. Items here are not implemented or
enabled in production until they have their own design, tests, and rollout.

## Automatic KFPS Version Synchronization

**Status:** Implemented in WIP; not deployed

Keep the Community upload-version floor synchronized with the official KFPS
repository instead of manually editing and redeploying the Worker after every
KFPS version bump.

Requirements:

- Treat the tracked `VERSION` file on the official KFPS `main` branch as the
  only automatic authority.
- Never derive or raise the minimum version from an uploader-provided
  `client_version`; that value is untrusted and can be spoofed.
- Validate the fetched value as a strict KFPS version before storing it.
- Retain the last verified value when GitHub is unavailable or returns invalid
  data. A failed refresh must not clear or lower the active floor.
- Prevent automatic downgrades. Any rollback must be an explicit admin action.
- Store the last verified version, source commit, and synchronization time so
  they are visible in the admin console and moderation history.
- Add a manual **Sync version now** admin action and a scheduled Cloudflare
  refresh so normal version bumps require no Worker deployment.
- Test newer, equal, older, malformed, unavailable, cached, and explicit
  rollback cases before production rollout.

## Supporter Community Tab

**Status:** Implemented in WIP; not deployed

Add a dedicated **Supporters** scope to the Community tab for vinyls published
by verified KFPS supporters. Access and publishing eligibility must be enforced
by the server, not by hiding controls in QML.

Requirements:

- Only a currently verified supporter may publish into the Supporters scope.
- Only a currently verified supporter may list, search, inspect, preview, or
  download Supporters-scope artwork. Administrators retain moderation access.
- Handmade/Toolmade remains a separate mandatory classification. Supporter
  visibility must not replace or alter that classification.
- Determine supporter attribution from a verified entitlement, never from an
  uploader checkbox or a client-provided boolean.
- Keep supporter keys and offline activation receipts out of the Community
  service. Use a short-lived, audience-bound signed entitlement or similarly
  isolated proof that reveals no key, receipt, purchaser name, email, device
  identity, or local path.
- Bind the entitlement to the active Community account/session so it cannot be
  copied to another GitHub account.
- Do not expose supporter-only metadata through public catalog, search, cache,
  preview, or download endpoints.
- Preserve normal reports, duplicate checks, revisions, owner removal, and
  administrator moderation for supporter artwork.
- Define the status-change policy before implementation: existing uploads may
  remain archived in the supporter catalog, but expired or revoked accounts
  must lose new uploads and supporter-only access immediately after a trusted
  status refresh.
- Clearly document that a JSON already downloaded to a user's computer cannot
  be remotely recalled.
- Add API authorization, cache-isolation, entitlement-expiry, tampering,
  account-binding, and UI regression tests before rollout.
