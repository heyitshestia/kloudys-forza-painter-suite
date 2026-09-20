# Community Local Preview

## Open the mockup

Open DIRTY's normal `KFPS.exe`, then choose Community. The local marker
`runtime/community-preview/enabled.local` enables the new page in this checkout.
Restart any already-open DIRTY window after source changes. Alternatively,
`KFPS.UI/tools/Launch_Community_Preview.bat` launches the same full KFPS application
directly on Community. There is no separate Community window or duplicate sidebar.
The title bar, theme, fonts and controls come from the normal KFPS shell. Change
themes in Settings as usual. At 1280x800 the gallery fits three posts per row.
The local catalog does not require GitHub sign-in, a key or Cloudflare credentials.

All catalog changes stay in `runtime/community-preview/review/catalog.sqlite3`.
Downloads stay in `runtime/community-preview/review/downloads`. Closing and
reopening preserves votes, favorites, profiles, uploads and moderation state.

Use **Back** at the bottom left or the normal sidebar to change pages in the same
window. Returning to Community retains the current selection and local state.
To restore the old live Community page, rename/remove `enabled.local` and restart
KFPS without `--community-preview`. The local test catalog is not deleted.

## Try the workflows

1. Browse the Gallery + Inspector layout. Search, filter artwork type/game/category,
   switch Featured/Timed Releases/Favorites/Following, and enlarge a preview by clicking it.
2. Use **Test account** to switch Visitor, Member, Supporter and Creator. These
   are explicitly simulated identities/entitlements; no real keys are used.
3. Try an upvote, downvote and clicking the same vote again to remove it. Favorites
   are separate. Follow or ignore a creator; undo ignoring from Profile.
4. Open Upload artwork. Choose a real vinyl JSON or `.kfpslivery` package, add
   metadata/tags, confirm sharing rights, and publish to the local catalog.
   Do not use `.fabric-project.json` as a game-ready export or `.kfpspreview` as
   a shareable livery. Both remain distinct formats.
   New livery uploads require one to three uploader-selected PNG/JPEG/WebP photos.
   Each source image can be up to 20 MiB and 64 megapixels; the local catalog keeps
   metadata-free copies with a maximum 1920-pixel edge. The first is the cover.
   Replace the selection or remove individual photos before publication.
   Existing entries without photos remain readable.
5. Enable Scheduled release and choose the start/end dates and local times.
   Stored times are UTC. The footer's **+1h** advances only the test clock, so
   release/expiry can be tried without waiting. Expiry deletes the stored payload
   and preview, not your original selected file or downloaded copies.
   Active timed releases appear in Browse and the dedicated Timed Releases tab.
   Future releases remain private until their start time. Expiry also deletes
   their uploaded photos and closes an open local 3D preview.
6. Click any @username to open their profile, follow them or browse their artworks.
   Your own profile has Edit profile, including the existing unignore controls.
   Report an artwork from its detail panel. Moderation is intentionally absent
   from Community; the local store retains administration helpers for tests only.
   Removing an upload is available only for your own artwork.
   For a livery, click a photo to enlarge it, then choose **3D render**. The large
   modal uses the existing livery viewer: drag to orbit, right-drag to pan and
   scroll to zoom. Close with **X** or Escape. Rendering is explicit, never started
   by browsing posts or opening a photo, and requires the matching local FH6 assets.
   If assets are unavailable, the photos still work and the viewer offers the game
   folder picker. Sign-in/supporter/availability checks also apply to 3D access.
7. Try Korean with the page's language switch and KFPS themes through Settings. Some reused controls,
   test-account names and diagnostic messages remain English in this prototype.

The supplied character images and livery screenshot are clearly labelled visual
samples and cannot be downloaded as artwork. Six-shape synthetic vinyl fixtures
are real downloadable JSONs. You can import your own files without changing them.

## Isolation

- The main entry point and page router have a source-only, local opt-in. The old
  production Community page is retained unchanged by this integration.
- No Worker source/configuration, cloud database or live storage is changed.
- Community preview actions use only SQLite/local files. The normal Community
  service is in demo mode while the prototype is enabled, so it does not call its Worker.
- The rest of KFPS retains its normal settings and services, including ordinary
  update/supporter checks. Those are separate from the simulated catalog accounts.
- The local database and fixture assets are not publication-ready or a migration.
- No private sharing, inbox, comments or new paid benefits are implemented.

## Working vs simulated

Working locally: per-account votes, favorites, follows/ignore, clickable creator
profiles, exact-creator browsing, profile editing,
search/filters, upload validation/rendering, local publication, exact livery-file
round-trip, uploader photo galleries, supervised interactive livery 3D previews,
downloads, supporter/visitor gates, schedules/expiry, report queue,
own-upload removal, persistent state and the responsive native gallery.

Simulated: GitHub identity and key entitlement. Creator is Kloudy without admin
privileges; Moderator remains a backend test fixture only. These identities are not
security credentials. This is a single-computer test harness, not a network server.

Not yet integrated: real Cloudflare contracts/storage migration, online expiry
scheduler, all existing production account and
revision-management dialogs, complete localization of reused controls, production
limits and multi-client concurrency. The ordinary Community page remains available
with the opt-in disabled.
Expiry runs while the preview is open, with catch-up when it next opens. Production
expiry needs a hosted scheduler; this mockup does not claim otherwise.

## Repeatable checks

From DIRTY:

```powershell
.\python\python.exe -m unittest discover -s KFPS.UI/tests -p 'test_community_preview_*.py' -v
.\python\python.exe KFPS.UI/tools/community_preview.py --test --state my-check
.\python\python.exe KFPS.UI/tools/community_preview.py --native-test --state native-check
.\python\python.exe KFPS.UI/tools/community_preview.py --theme-test --state theme-check
```

Use a fresh state name for a clean UI test catalog. `--native-test` runs the same
checks in a non-activating background Windows window instead of offscreen.
Results, screenshots and logs are saved under that named local preview directory.
No test uploads reach the public catalog.
Workflow checks use Qt's basic render loop because QTest's nested event waits can
stall the threaded renderer on a hot theme change. The separate asynchronous theme
check exercises the normal renderer without nested waits. User launch/rendering
policy is unchanged. Test shell settings and runtime logs have separate directories.

## Layout And Readability

The Community page stays inside KFPS, using its real title bar, sidebar and theme.
Its shell status band is 40 pixels; other pages restore their normal shell layout.
The gallery and dropdowns share integer-width tracks and a dedicated scrollbar
gutter. At 1760x1040 there are five columns; at 1280x800 there are three, with two
filter rows. The main gallery starts at y=203 / y=245 respectively (RX-93 adds its
existing custom frame spacing).

Buttons and dropdowns are 36 pixels tall. Body and creator text is 14 pixels,
artwork titles 15, and controls 12-13. Community opts into Qt CurveRendering for
grayscale edges, removes text scaling/press translations, and does not shrink
button labels automatically. Existing theme materials and colors remain intact.
Shared controls default to their previous rendering and animation behavior.

Native rendering plus QFont NoSubpixelAntialias did not remove colored fringes
in measured screenshots, so that unsuccessful font-factory approach was removed.
See [Qt's supported text rendering modes](https://doc.qt.io/qt-6.8/qml-qtquick-text.html#renderType-prop).
The terminal gallery sample had 1079 colored-edge pixels with native text and
zero with the selected curve renderer. This is local graphics evidence, not a
claim of verification on every GPU or forced software-rendering configuration.

## Startup Size

The existing normal KFPS preference is 1760x1040. DIRTY's saved window geometry
also uses that size. Normal launches retain the last saved geometry and fit
smaller displays automatically. The preview launcher does not force test sizes.
The live window capture helper failed on this machine, so only the saved size,
not a direct measurement of the user's currently open window, was verified.

## Current Verification

### Theme-Preserving Readability And Creator Gallery, 2026-09-20

The selected theme still owns fontFamily, displayFamily and monoFamily. The
shared control changes do not install a replacement font: button, input and
navigation labels use integer sizes and curve-rendered live text, and avoid
label shrinking and fractional press/hover transforms. This is a shared-control
readability baseline, not a claim that every legacy page-specific caption has
been redesigned. Decorative theme assets remain in use.

Apex Vector and Night City reserve safe content gutters for their chrome.
Download and Favorite are equal-width, full-row text actions. Only locked
supporter artwork changes Download to Ko-Fi; ordinary downloads keep their
existing sign-in requirement. Gallery double-click opens the full image viewer.

Creator profiles show username/bio and a three- or four-column virtualized gallery.
Metadata arrives in keyset pages of at most 48 entries. Images are decoded only
for instantiated/prefetched tiles, without an eager catalog-wide image read.
The local Python image provider is synchronous because asynchronous provider
requests stalled the native Qt/Python interaction test. The bounded local path
passed; production HTTP media loading must reuse the existing client/cache path.
Account changes, expiry, ignores and visibility rules are covered by tests.

Verified evidence:
- `runtime/community-preview/typography-20260920-native-check/`: 15 native workflow
  groups and 223 unit/regression tests (80 Community, 90 full-livery, 47 livery,
  six geometry). Actual clicks verify double-click enlargement, Escape, vote
  changes, equal action widths and Ko-Fi routing with browser launch intercepted.
- A 600-artwork native creator catalog reached its final thumbnail with at most
  29 live tile delegates. Initial display took 0.409 seconds including a deliberate
  0.200-second test wait. The slowest page jump took 0.225 seconds including a
  0.045-second wait. These are local measurements, not a smooth-frame-rate claim.
- 5,000 metadata entries traversed in 105 pages in approximately 0.15 seconds.
  SQLite authorization explicitly rejected image/payload reads during that test.
- `runtime/community-preview/typography-20260920-theme-final/`: 27 passing cases
  across all nine themes and three sizes, with 63 screenshots including Create
  and Settings. Font inheritance, minimum shared-control text size, equal/full
  action width, alignment and terminal colored-fringe pixels were checked.

No new Community QML errors were recorded. Existing theme-switch/scrollbar and
teardown warnings are retained in the logs. The 90-second traceback in the theme
run is its periodic diagnostic timer, not a failed or stalled run. The older real
Audi render evidence below remains the 3D qualification; this typography pass did
not repeat the real-car browser interaction suite. No production deployment,
version change, CLEAN transfer or push was performed.

Production integration must replace the old page inside KFPS and reuse the current
CommunityService, GitHub login, supporter entitlement, Worker, D1 and private R2.
These already exist. The local mock account selector and SQLite store are not
production replacements. Live votes, livery/media contracts and scheduled deletion
still need to be connected/extended in that existing stack before publication.

### Review Qualification, 2026-09-20

Fresh DIRTY-only qualification passed 215 unit/regression tests: 72 Community,
90 full-livery, 47 livery and six window-geometry tests. New cases cover upload
transaction rollback on a photo-write failure, failed download replacement,
expiry/photo deletion on restart, older catalogs without the photo table,
oversized image headers, failed-validation cleanup, repeated file selection,
and closing while file inspection finishes.

The first native run caught a real Windows file-sharing race: replacing the
optional progress snapshot failed while a reader held it, aborting 3D rendering.
Progress snapshot failures now leave a diagnostic event and do not abort the
operation. Required output/result writes still fail normally. A real Windows
reader-lock regression reproduces the old failure and verifies recovery.

Post-fix evidence:
- `runtime/community-preview/review-20260920-unit/`: regression logs, including
  failing pre-fix progress tests and passing post-fix full-livery tests.
- `runtime/community-preview/review-20260920-native-fixed/`: 14 passing native
  workflow groups, actual Audi rendering, orbit/pan/zoom, wheel toggling without
  reload, X-close and temporary-directory cleanup. Source package unchanged.
- `runtime/community-preview/review-20260920-themes/`: 27 passing theme/size
  cases, 45 screenshots and no Community QML errors. Default-size Windows 94,
  compact Korean and default-size real-car screenshots were visually reviewed.

These tests verify the local mockup, not live GitHub authentication, supporter
verification, private cloud storage or server-side scheduling. The existing
older-package consistency mismatch below remains unresolved. Previously recorded
shared scrollbar/theme-switch and QML teardown warnings remain in test logs;
they are not classified as new Community failures. No deployment was performed.

### Earlier Layout Qualification

Native workflow evidence: `runtime/community-preview/profile-readability-06/native-checks.json`.
Twelve groups cover real pointer clicks, creator profiles, own-profile editing,
voting/change/removal, downloads, uploads/schedules, gates, scrolling, filtering,
Korean layouts, theme changes and same-window navigation. Unit checks cover
27 preview, 21 existing Community and six window-placement tests.

The final theme sweep is `runtime/community-preview/profile-themes-04/`: all nine
themes at 1760x1040 English, 1280x800 English and 1000x660 Korean, with full-size
gallery/profile screenshots and medium upload dialogs. Checks include track
alignment, visible controls, profile close labels, text rendering mode and actual
terminal-text pixel colors. All 27 cases passed, producing 45 screenshots with
no preview QML errors. The nine default-resolution galleries were also visually
reviewed. See `theme-checks.json` for the recorded results.

Intermediate failed experiments remain in the ignored runtime tree and are
explained in `runtime/community-preview/WORK_PLAN.md`; they are not final evidence.
The threaded sweep deliberately avoids nested QTest mouse-move waits. Background
test windows never activate the user's window. Existing shared theme-switch and
FastScrollView warnings are retained in logs; no whole-app qualification is claimed.

## Timed Release And Livery Media Verification

`runtime/community-preview/timed-livery-native-06/` records 14 passing workflow
groups, including an actual Audi Sport Quattro package through upload, photo
selection and the complete local 3D pipeline. Playwright verified orbit, pan,
zoom, preference changes without navigation, nonblank canvas pixels at 1600x900
and 460x700, and no browser errors. The native close button was clicked and the
disposable render directory verified removed. The source package hash remained
unchanged. Default-size photo and 3D screenshots are included.
`runtime/community-preview/timed-livery-themes-01/` adds 27 passing checks across
all nine themes at 1760x1040, 1280x800 and 1000x660, with 45 screenshots and no
preview QML errors. The default-size terminal text sample still has zero colored
edge pixels. Existing shared theme-switch/scrollbar warnings remain in the logs.

33 Community preview tests, 87 full-livery tests and 47 livery regression tests
passed. The additive photo table preserves existing catalogs. Renderer settings,
packages, caches and worker sessions are isolated under the local preview state;
normal Livery-page selection, saves, settings and the live service are untouched.
The embedded URL uses the same stable-string guard as LiveryPage, avoiding
status-triggered reloads. Closing, account changes, selection changes and expiry
release the viewer. Startup errors retain a visible close control.

The older real-car input failed the current source/derived-layer consistency
check, including its normal migration attempt. Test preparation rebuilt a copy
from the package's preserved C_livery/header with the current compiler. Provenance
and hashes are under `runtime/community-preview/timed-livery-fixture/`. This does
not claim that the pre-existing older-package mismatch is repaired; the validator
was not weakened and no personal package was modified.
