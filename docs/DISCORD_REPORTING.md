# KFPS support reporting

Introduced in KFPS 3.1.61. Reporting is isolated from Community artwork uploads,
activation, game locators and save processing. Node.js is not required by users.

## User workflow

1. Click **Report a problem** below **Credits** on any page.
2. KFPS saves a bounded, sanitized report locally and opens a review form in the
   system default web browser. The HTML-file association is not used to choose it.
3. Review the context, edit the title, describe the problem and expected result,
   and choose whether to include private technical details.
4. Sign in with Discord, then explicitly send the report. Sign-in and opening the
   form never submit it automatically.
5. Keep the report ID. Follow the public support post or check delivery status.

The form explains that reports go to the dedicated KFPS Support Discord server.
It includes the permanent invitation: https://discord.gg/XT8dG8bDKy.
Post title is expanded by default; collapsing it does not discard its value.

The stable form address is:
https://kfps-support-staging.hestia-cummings.workers.dev

The historical Worker name is retained intentionally. Renaming or moving it is
not necessary for promotion and would require coordinating OAuth redirects and
installed clients. The public form and Discord application have no testing label.

## Data boundaries

Public: Discord display name, post title, affected area, issue description,
expected result, KFPS version when included, and report ID.

Private: additional technical context explicitly included by the reporter, sent
to the configured private diagnostics channel for Kloudy and authorized staff.
The form previews it and permits excluding it entirely.

Collection runs only when requested. It includes allowlisted app/service state,
bounded recent log excerpts, dependency versions, OS/CPU/RAM/GPU/driver information,
and supported game process names/store hints. It does not scan live game memory.
Only a relevant recent locator outcome may be included; pointer graphs, ownership
structures, shapes and arbitrary earlier archives are excluded.

Artwork, save files, screenshots, credentials and unrelated files are not attached.
Both client and server sanitize input. Automatic cleanup cannot recognize every
personal detail in free text, so the user must review the report before sending.

Local files are under `runtime/support-reports/<report-id>/`:

- `report.json`: sanitized original report.
- `open-report.html`: local browser handoff.
- `runtime/support-reports/latest.json`: most recent local report reference.

The handoff uses a URL fragment, not a query string; the form removes it immediately.
The editable draft is held in browser session storage across sign-in and refresh.
Closing the browser can lose edited text; the original local report remains.
If Windows cannot resolve a launchable browser executable, the HTTPS form opens
through the default handler and KFPS explains how to add the saved report manually.

## Delivery and recovery

- Discord OAuth uses only `identify`, with expiring state and signed HttpOnly,
  Secure, SameSite cookies. There is no bot or access to members' messages.
- Submission enforces authentication, origin and CSRF checks, strict schema and
  size limits. Channel-specific webhooks remain server secrets.
- Webhook guild/channel identities are verified before sending. Mentions are
  disabled and public text is escaped.
- A per-account SQLite Durable Object serializes delivery. Private context is
  sent first, followed by the public forum post. Completed parts are not reposted.
- An uncertain acknowledgment is not automatically retried. Staff must check both
  channels by report ID before requesting a new report.
- Only receipt metadata, delivery state and a content hash are retained by the
  Worker, not the raw report body. Receipts expire after 30 days.
- Discord posts and attachments remain until staff delete them. Removing a report
  requires locating and removing both destinations; receipt expiry does not do it.

Limits: 48 KiB local report, 64 KiB request, 3 new reports per 10 minutes and 20 per
day per authenticated account, 5 delivery attempts per report. Sessions last
8 hours; OAuth state lasts 10 minutes. Local collection uses one background task,
suppresses repeated clicks and suppresses browser launches after app shutdown.

Emergency stop: set `DELIVERY_ENABLED=0` in the dedicated Worker and deploy it.
The form will report temporary unavailability, preserving the draft. This does
not disable the existing Community service or local report creation. Do not rotate
credentials to diagnose ordinary delivery errors. Rotate only affected credentials
when necessary; rotating `SESSION_SECRET` invalidates all active form sessions.

## Implementation

- `KFPS.UI/src/kfps_ui/support_report.py`: collection, sanitation, atomic saves.
- `KFPS.UI/src/kfps_ui/support_browser.py`: Windows HTTPS-default resolution and
  explicit-argument browser launch; no hard-coded browser or registry changes.
- `KFPS.UI/src/kfps_ui/report_service.py`: Qt state, worker ownership and existing
  local Markdown report compatibility.
- `KFPS.UI/qml/shell/SupportReportButton.qml` and `Sidebar.qml`: global entry point.
- `KFPS.UI/app.py`: context binding and shutdown ownership.
- `tools/support_worker/public`: form and shared validation protocol.
- `tools/support_worker/src/worker.mjs`: OAuth, routing, delivery and receipts.
- `tools/support_worker/wrangler.jsonc`: deployment identifiers and non-secret config.

Required Worker secrets: `DISCORD_CLIENT_SECRET`, `SESSION_SECRET`,
`PUBLIC_WEBHOOK_URL`, `PRIVATE_WEBHOOK_URL`. Never store values in the repository,
app bundles, reports or logs. OAuth callback is the configured public origin plus
`/auth/callback`. Deploy only this Worker, not the Community or activation Workers.

## Verification

Pre-promotion checks on 2026-09-06:

- 626 Python/application tests passed, including 14 support collection, privacy,
  browser routing, shutdown, file-lock retry and compatibility tests.
- 18 support Worker tests passed. One exercises the actual workerd runtime and
  SQLite storage across reloads; outbound Discord traffic is mocked in these tests.
- 27 browser checks passed against deployed form assets, using mocked identity
  and delivery. Checks cover drafts, double submission, private exclusion, title
  editing, invitations, public/private notices and desktop/mobile layouts.
- 144 actual QML shell checks passed: 8 themes, 2 sizes, 9 pages. Collection and
  saving are real; external browser launching is mocked to avoid taking focus.
- A separate live owner-account test completed OAuth, sent one public post and
  one private attachment, and preserved the receipt on reload without duplication.
- The reporter performed additional manual checks and authorized promotion.

Known validation gaps remain: ordinary non-staff account end-to-end access checks,
other machines/browser defaults, and an updated packaged installation smoke test.
Owner-account success and mocked tests do not replace those checks.

Run from the repository root with Python 3.12 and the existing development tools:

```text
python -m unittest discover -s KFPS.UI/tests -p "test_*.py" -v
python KFPS.UI/tools/test_support_workflow.py
node --test tools/support_worker/test/*.test.mjs
```

The runtime test reuses locked Miniflare/esbuild dependencies from
`tools/community_worker/node_modules`. Run `npm ci` there first on a fresh developer
checkout. Reporting tests run in the existing Community Worker CI job, without
new scheduled jobs or another dependency installation. The normal Windows test
discovery includes the reporting tests automatically.

`tools/support_worker/test/browser-workflow.js` is an isolated Playwright CLI
scenario. It mocks identity and submission; never run it in a logged-in user
browser or describe it as a live Discord delivery test.

Local evidence belongs under ignored `runtime/support-testing`, not in commits or
bundles. The original integration notes are preserved there for local auditing.

## Server maintenance

Keep the pinned support guide, start-here message and private diagnostics notice
aligned with the form. They must explain public/private visibility, explicit Send,
report IDs, uncertain delivery and manual fallback. The permanent invite and
stable form address should work independently of installed KFPS versions.

Before future changes, preserve the identity-only OAuth scope, non-public technical
delivery, existing local Markdown report API and separation from other Workers.
