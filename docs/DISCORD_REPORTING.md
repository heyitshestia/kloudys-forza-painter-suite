# KFPS support reporting

Introduced in KFPS 3.1.61. Reporting is isolated from Community artwork uploads,
activation, game locators and save processing. Node.js is not required by users.

## User workflow

1. Click **Report a problem** below **Credits** on any page.
2. KFPS saves a bounded, sanitized report locally and opens its dedicated report
   window using the managed browser runtime. The report and retained logs load
   automatically, including packages above the old browser-handoff size threshold.
3. Review the context, edit the title, describe the problem and expected result,
   and choose whether to include private technical details.
4. Sign in with Discord in the Windows default browser. Check the matching code
   and authorize the KFPS report window, which signs in automatically without
   navigating away from your report. Existing browser logins can be reused;
   Discord can still require authentication if that browser session has expired.
   KFPS does not choose Edge or copy browser cookies. Optionally add or paste PNG/JPG screenshots, review their previews,
   and confirm that the images will be public. Then explicitly send the report.
   Sign-in, opening the form and selecting screenshots never submit automatically.
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
expected result, KFPS version when included, report ID, and screenshots explicitly
selected and confirmed for public sharing. The form and result identify the
dedicated KFPS Support server, separate from the community server.

Private: additional technical context explicitly included by the reporter, sent
to the configured private diagnostics channel for Kloudy and authorized staff.
The form previews it and permits excluding it entirely.

Collection runs only when requested. It includes allowlisted app/service state,
bounded recent log excerpts, dependency versions, OS/CPU/RAM/GPU/driver information,
and supported game process names/store hints. It does not scan live game memory.
Only a relevant recent locator outcome may be included; pointer graphs, ownership
structures, shapes and arbitrary earlier archives are excluded.

Artwork, save files, screenshots, credentials and unrelated files are never
collected automatically. Only screenshots deliberately selected in the form can
be attached; these go to the public post, not the private diagnostic attachment.
Both client and server sanitize input. Automatic cleanup cannot recognize every
personal detail in free text, so the user must review the report before sending.

Local files are under `runtime/support-reports/<report-id>/`:

- `report.json`: sanitized original report.
- `report.kfps-report.json.gz`: the report plus complete privacy-filtered retained
  editor and worker logs, when available. Choose this file to restore a missing log attachment.
- `open-report.html`: compatibility/recovery handoff for older browser workflows.
- `runtime/support-reports/latest.json`: most recent local report reference.
- `runtime/support-reports/browser/`: isolated report-window profile and cache;
  not collected as logs or packaged in a release.
- `runtime/support-reports/report-window.log` and `.1`/`.2`: bounded report-window
  lifecycle and failure logs, included privately in later reports.

The managed report window reads only a canonical report-ID folder, rejects linked
files/folders, and transfers at most 9 MiB in checked chunks to the exact trusted
form origin. Neither report bytes nor credentials appear in launch arguments or
authorization links. No local HTTP listener, general filesystem bridge, browser
file permission, or file picker is needed in the normal workflow. Failures retain
the local package and show Retry rather than silently dropping the logs.
The native window preserves one edited draft locally for up to 24 hours, checked
when the form next opens. Normal external-browser recovery keeps its historical
session-storage behavior; closing that browser can lose edited text. The original
local report remains in either case. Old fragment handoffs still work, and their
fragment is removed immediately.
Screenshot pixels stay only in tab memory, not session storage or receipts. Sign
in before adding them. After a reload or sign-in expiration, reattach the original
images in the original order to retry an incomplete submission. A content hash
binds each image to the report, so retries cannot silently drop or change images.
Successful delivery releases preview URLs and image references.
Complete private logs use one bounded IndexedDB entry, separate from screenshot
memory and editable session storage, so Discord sign-in and page refresh do not
discard them. Delivery, sign-out and New report delete that entry. Copies older
than 24 hours are discarded when the form opens; there is no background cleanup
while the browser is closed. The form explains this retention and offers a
download of the complete sanitized logs plus a short on-screen preview.
The manual file picker remains a recovery option, not the normal report button.
It explicitly confirms that the report loaded even after resetting its hidden
file input so the same file can be selected again.

Native sign-in requests expire after five minutes. The public approval link
contains only an unguessable request ID; a separate signed HttpOnly pending cookie
binds completion to the requesting report window. Approval requires the browser's
authenticated session, same-origin CSRF check, matching displayed code, and an
explicit confirmation. It creates a distinct report session, not a copy of the
browser's cookie or Discord access token. Lost completion responses can retry
idempotently with the same private cookie. Cancellation, denial, and expiry cannot
submit a report. Temporary approval state is isolated in the existing Durable
Object binding and expires; per-address start limits bound anonymous creation.

## Editor Diagnostics

Reports opened from KFPS's Editor page include the most recently written editor
snapshot: frame stalls, memory and cache use, reference dimensions, layer count,
recent action/command/commit identifiers, save and recovery outcomes, actual
browser-engine versions, and installed editor-file fingerprints. Snapshot age and
logging failures are included so stale or incomplete evidence is distinguishable.

The collector also reads recent, sanitized excerpts from known editor, transfer,
generator, upscaling, background-removal and livery-worker logs when available.
It looks back up to seven days, labels previous-session logs, and includes up to
16 log entries. The summary stays capped at 48 KiB; excerpts may be shortened.

The report preparation task also copies retained editor log files, from their
beginning rather than just their tails: `performance.jsonl`, `performance.1.jsonl`,
`performance.2.jsonl`, `desktop.log`, `desktop.log.1` and `desktop.log.2`. This separate compressed attachment
goes only to the verified private diagnostics channel. The existing diagnostic
snapshot remains in report.json. The same private archive includes retained
generator, transfer, upscaler, background-removal, livery and livery-viewer worker
logs from their known log locations. Unlike the summary excerpts, these are not
limited to the last seven days or the latest run. Original run and artwork names
are replaced with numbered source labels. No project, recovery, image, arbitrary
file or directory traversal is accepted as a log attachment.

Structured performance records retain their chronological session, sequence,
action, command, commit, checkpoint and timing fields through the existing
allowlist. Free-form startup and worker logs are redacted line by line. Unsupported or
partially written records, unreadable files, linked files and oversized files
are visibly reported as omissions, never silently presented as a complete copy.
Capture includes the bytes present when each file was opened; later events are
not part of that report. Retention limits and dropped events at the original
producer cannot be recovered by packaging a report.

Limits are 4 MiB per source file, 24 MiB expanded sanitized archive, 8 MiB compressed
private attachment, and 9 MiB saved support package. Up to six editor files and
256 worker files can be included. Discovery is also time- and entry-bounded;
any file count, size, discovery or access omission is reported, so an incomplete
archive is not labelled complete. Oversized source files are omitted with a warning,
not silently shortened. These budgets accommodate the normal editor rotations
plus worker logs; they are not unlimited retention. Bounded streaming
decompression, strict file/record schemas and matching content hashes run in the
browser and server. Missing or changed archives block submission/retry unless the
reporter explicitly disables technical details. Screenshots cannot be substituted
for private logs or sent to the private-log destination.

New archives use `kfps-private-app-logs/2` and `kfps-app-logs-<id>.json.gz`.
The form and Worker continue accepting `kfps-private-editor-logs/1` archives from
older clients without changing their normalized metadata or retry hashes.

The editor keeps a bounded event backlog separate from its 48-record, 24 KiB
transport batches. Bursts schedule a paced background drain; retries preserve the
same sequence and bytes until accepted. A full native queue returns backpressure
instead of acknowledging and discarding the packet. Normal close attempts a final
drain. Prolonged outages, forced termination and disk errors can still cause loss;
explicit queue, drop and write counters distinguish those cases.

Only the compatibility HTML handoff retains the old 750 KiB automatic-fragment
threshold; larger packages there need manual recovery. The managed KFPS report
window automatically loads the complete supported package instead. Preparing logs
does not upload them. No report bytes or archive are stored in Cloudflare receipts.

Both the hosted review form and the Worker import the same editor filter.
Updating only application files cannot update that hosted filter. When changing
diagnostic fields or the editor source inventory:

1. Run `py -3.12 tools/editor_manifest.py sync` and the support Worker tests.
2. Deploy only `tools/support_worker` from the reviewed CLEAN checkout, preserving
   existing secrets, bindings and receipts.
3. Run `npm run verify-deployment` in that folder. This read-only gate compares
   every served form asset with the checkout and checks configuration and the
   anonymous access boundary. It never submits a report.
4. Reload already-open reporting forms before testing. Preserve the current
   deployment ID as the rollback target and keep deployment evidence private.

Do not add empty new fields to older normalized reports: receipt hashes must stay
stable when an existing report is reviewed or retried. The regression suite covers
legacy context, expanded context and private/public delivery in actual workerd
with mocked Discord. Deployment readback is not a live Discord delivery test.

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

Limits: 48 KiB local report, 64 KiB report JSON. Optional screenshots: 3 PNG/JPG
images, 5 MiB each, 10 MiB combined, 40 megapixels and 16,384 pixels per side.
The browser decodes and re-encodes image pixels to discard embedded metadata;
uploaded filenames become screenshot-1.png/jpg, etc. Visible personal information
is not automatically blurred. The server checks content signatures, dimensions,
sizes, hashes and explicit public consent before any delivery. Images use bounded
multipart upload, never a larger JSON allowance or a new storage service.
Public images remain public when private technical details are disabled.

Rate limits: 3 new reports per 10 minutes and 20 per
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
- `KFPS.UI/src/kfps_ui/support_logs.py`: bounded allowlisted worker discovery and
  short summary excerpts.
- `KFPS.UI/src/kfps_ui/support_log_bundle.py`: complete retained application-log
  collection, record allowlisting, compression and local support packages.
- `KFPS.UI/src/kfps_ui/support_browser.py`: Windows HTTPS-default resolution and
  explicit-argument browser launch; no hard-coded browser or registry changes.
- `KFPS.UI/src/kfps_ui/report_service.py`: Qt state, worker ownership and existing
  local Markdown report compatibility.
- `KFPS.UI/qml/shell/SupportReportButton.qml` and `Sidebar.qml`: global entry point.
- `KFPS.UI/app.py`: context binding and shutdown ownership.
- `tools/support_worker/public`: form and shared validation protocol.
- `tools/support_worker/src/worker.mjs`: OAuth, routing, delivery and receipts.
- `tools/support_worker/src/submission.mjs`: bounded JSON/multipart input and image
  integrity checks; legacy image-free reports keep their original receipt hashes.
- `tools/support_worker/public/screenshots.mjs`: shared image limits and metadata.
- `tools/support_worker/public/screenshot-picker.mjs`: image previews, consent and
  retry reattachment. No automatic screenshot capture or separate upload endpoint.
- `tools/support_worker/public/private-logs.mjs`: shared bounded gzip, log schema
  and attachment integrity checks; not a general archive or arbitrary file upload.
- `tools/support_worker/public/private-log-picker.mjs`: private-log review,
  temporary browser-local persistence, opt-out and exact retry reattachment.
- `tools/support_worker/wrangler.jsonc`: deployment identifiers and non-secret config.

Required Worker secrets: `DISCORD_CLIENT_SECRET`, `SESSION_SECRET`,
`PUBLIC_WEBHOOK_URL`, `PRIVATE_WEBHOOK_URL`. Never store values in the repository,
app bundles, reports or logs. OAuth callback is the configured public origin plus
`/auth/callback`. Deploy only this Worker, not the Community or activation Workers.

## Verification

The screenshot suite covers the actual multipart route, private/public separation,
authentication, consent, format/size checks, missing and changed image rejection,
retry integrity, duplicate suppression, and real workerd/SQLite delivery with
mocked Discord. `test/screenshots.browser.cjs` exercises actual PNG/JPG selection,
decoding, previews, removal, consent, mobile/desktop layouts, receipt reload and
reattachment through the real multipart parser with mocked identity/delivery.
`test/log-review.browser.cjs` retains the original image-free workflow coverage.
Browser scripts take an output directory and require the existing Playwright
development dependency; never target a user's signed-in profile for mocked tests.
`test/private-logs.browser.cjs` covers private bundle handoff, sign-in/refresh,
missing-file rejection, retry integrity, deletion after delivery and opt-out.
Python tests verify complete retained rotations, privacy, live append, omissions,
link/size checks and legacy handoffs. Live qualification must additionally use a
real native editor session, the actual QML report button, and compare the received
private attachment with the locally prepared archive. Synthetic transport tests
alone do not verify editor logging or native collection.

Discord's [webhook attachment contract](https://docs.discord.com/developers/resources/webhook#execute-webhook)
is used: public screenshots are files on the same forum starter message, with
`wait=true`, unique attachment indexes and mentions disabled. No dependency or
third-party code was added for image processing.

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

## One-time startup notice (2026-09-07)

After the DIRTY checks below and visual approval, Hestia authorized promotion
to CLEAN/main with the native upscaler in the 3.1.62 bundled release. The
no-publication statements below describe the earlier implementation checkpoint.

The shell shows a welcome notice after its first visible startup following this
change. It displays Hestia's support-channel message, highlights the existing
Report a problem button below Credits with a curved arrow, and announces the
native 2x/4x upscaler. Got it dismisses the notice; Try the upscaler dismisses it
and opens that page. Escape also dismisses. Outside/spotlight clicks cannot submit
a report, launch a browser, or dismiss the notice accidentally.

`supportUpscalerNoticeAcknowledged` is stored in the existing
`runtime/qml-shell-settings.json`. Old settings without the key show the notice.
Dismissal survives restarts, ordinary updates and preference resets. Deleting
the settings file or using a fresh installation naturally shows it again.
If settings cannot be written, the notice still closes for the current session
and the persistence error is logged. No server/account state is involved.

Implementation: `shell/FeatureWelcomeOverlay.qml`, the target exposed by
`Sidebar.qml`, the startup timer in `Main.qml`, and `SettingsService` persistence.
The arrow follows live button geometry. Geometry checks run only while open and
do not repaint a stationary arrow; the artwork is unloaded on close. The message
uses a solid theme-colored surface, a spotlight cutout and theme-aware corners.
Screenshot-only app runs suppress the automatic notice.

Validation entry points:

```text
python -m unittest discover -s KFPS.UI/tests -p test_feature_welcome.py -v
python KFPS.UI/tools/test_feature_welcome_workflow.py
```

The workflow uses isolated settings, actual QML clicks, eight themes, two window
sizes, each dismissal path and fresh application processes for restart checks.
It runs offscreen, disables unsupported software-renderer glass effects, and
never sends reports or opens a real browser. Artifacts and subprocess logs belong
under ignored `runtime/welcome-testing/`.

Final evidence: `runtime/welcome-testing/workflow-20260907-065339/`.
All 16 theme/size cases passed, including text clipping and arrow target checks;
Got it, Try the upscaler and Escape each passed a separate process restart check.
Five focused persistence tests and all 658 application regression tests passed.
Full-suite log: `runtime/welcome-testing/full-regression.log` (52.000 seconds).
The existing suite shutdown ResourceWarning remains; this notice work does not
claim to resolve unrelated QObject lifetime warnings. No promotion, version bump,
release build, browser launch or server change was performed for this notice.

Lookback:

1. Scope stayed limited to the requested support/upscaler announcement in DIRTY.
2. Reused the existing settings, modal controls, theme helpers and report button.
3. Initial missing glass-layer screenshots were a software-test-renderer issue;
   Windows 94 text clipping was a layout issue and was corrected separately.
4. Added painted-text/viewport checks alongside screenshots and real restart tests.
5. One notice flag and one reusable shell component are sufficient; no new service.
6. No alternate WIP implementations or new announcement backend were introduced.
7. Passing geometry assertions alone did not prove that every word was visible.
8. A static screenshot/arrow would be simpler but would drift as the sidebar resizes.
9. Stop feature work after the final checks; leave promotion and publishing to Hestia.
