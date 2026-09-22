# Community Search Input

## Ownership and Behavior

The Community page owns the editable search draft. The gallery service owns the
last submitted search and result generation. Network responses, thumbnail loads,
selection changes and account status updates must never rewrite a draft.

`CommunityPreview.qml` observes the scalar applied query, not a direct binding
from textbox `text` to the broadly notified filters map. A real query change
still synchronizes the field. User edits submit after 300 ms without another edit;
Enter submits immediately, and unchanged queries do not generate another request.
Input-method composition suspends submission until committed text is available.

Both live and preview services expose `searchReset(str)` for intentional resets.
It also clears an unsubmitted draft when the applied query is already empty,
which a query-value change notification alone cannot express. Upload completion
uses this signal; preview creator navigation retains its previous reset behavior.
The existing live catalog generation check rejects out-of-order result pages.

## Verification

Run `python -B KFPS.UI/tests/test_community_search_native.py -v` with the pinned
application dependencies. Tests load the actual Community QML page offscreen,
send native Qt keyboard/input-method events, and exercise both service adapters.
The live adapter uses an isolated in-memory HTTP substitute, never production
accounts, keys or artwork. One test delays an older response until after a newer
query to verify result ordering as well as draft ownership.

Coverage includes fast/slow/paused typing, background notifications, middle edits,
backspace, selection replacement, undo, paste, Enter, empty searches, Korean
preedit/commit/cancel, explicit resets, page recreation, focus changes and all nine
themes. Korean composition is exercised through Qt input-method events, not a
claim of manual validation with every Windows IME implementation.

Optional `KFPS_SEARCH_EVIDENCE` saves theme screenshots beneath a caller-selected
test-run directory. Do not commit screenshots, runtime state or private logs.

## Checkpoint and Lookback

2026-09-22: the regression test failed against the original page because a generic
service notification replaced a typed `c` with the old empty query. The local-draft
fix passes that reproduction. The problem is UI state ownership, not Cloudflare
search matching; increasing the old delay alone would not fix it. No Worker,
authentication, artwork format or editor changes are required. Keep the existing
service boundary and scope the release to this fix, its tests and documentation.

DIRTY verification: 94 Community tests passed, including the subprocess running
23 native input cases through both adapters and full-size captures in all nine
themes. The native harness owns its own QApplication to avoid unrelated suites'
QCoreApplication instances. Explicit capture dimensions prevent a one-pixel
offscreen view from being mistaken for visual coverage.

Evidence: `runtime/test-runs/community-search-20260922/dirty/` (ignored).
CLEAN verification: all 1,098 application tests passed, including the isolated
native search suite. Evidence is under the corresponding `clean/` test-run folder.
Only seven scoped source, test, documentation and version files are promoted.

Version 3.1.93 uses the existing main-branch quality workflow and signed stable
updater publication. No Worker deployment or new bundled release is required.
Publication is complete only after that workflow passes and the public channel
identifies 3.1.93; the existing bundled release remains unchanged.
