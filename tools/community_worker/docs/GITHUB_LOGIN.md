# GitHub Community Sign-In

KFPS uses GitHub OAuth Device Flow only to establish a stable public identity.
It requests no OAuth scopes, cannot access repositories, and never receives a
GitHub password. The temporary GitHub token is sent once to the Community Worker,
used to request `/user`, and discarded. KFPS stores only its separate Community
session, encrypted for the current Windows user with DPAPI.

## Register The OAuth App

1. Open GitHub **Settings > Developer settings > OAuth Apps > New OAuth App**.
2. Use `KFPS Community Library` as the application name.
3. Use the standalone Community repository or deployed Worker URL as the homepage.
4. GitHub requires a callback URL even though Device Flow does not use it. Use the
   deployed Worker's root URL.
5. Create the app, open its settings, and enable **Device Flow**.
6. Copy the public client ID. Do not generate, copy, or distribute a client secret.

Put the client ID in `wrangler.jsonc`:

```json
"GITHUB_CLIENT_ID": "Ov23liYourPublicClientId"
```

Deploy the Worker again. `/v1/config` will expose only this public ID so desktop
clients can start Device Flow.

## Test Locally

Either set the same value as `GITHUB_CLIENT_ID` in the ignored `.dev.vars`, or
override only the desktop client for one launch:

```powershell
$env:KFPS_COMMUNITY_GITHUB_CLIENT_ID = "Ov23liYourPublicClientId"
$env:KFPS_COMMUNITY_API_URL = "http://127.0.0.1:8790/v1"
& "..\KFPS DIRTY\KFPS.exe"
```

The local service may expose both **Continue with GitHub** and **Use Local Test
Account**. Production must keep `ALLOW_TEST_AUTH` at `0`, so only GitHub appears.

## Account Behavior

- The GitHub account ID, not its changeable login spelling, anchors the Community account.
- The chosen Community username is separate and can be claimed only once. KFPS shows
  it on a second confirmation screen, and the service requires an exact matching
  confirmation before accepting the claim.
- Signing out deletes the local DPAPI session and invalidates that Community session.
- Signing out does not revoke the OAuth app grant in GitHub. A user can review or
  revoke it under GitHub **Settings > Applications > Authorized OAuth Apps**.
- A suspended Community account cannot use authenticated actions, regardless of a
  valid GitHub identity.
