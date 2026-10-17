# Editor and report reviewer coexistence

## Scope

KFPS 3.1.104 fixes two application issues reported against 3.1.103:

- Opening the report reviewer could prevent the editor from starting, and vice versa.
- The layer toolbar could shrink to 32 pixels while its wrapped buttons required over 100 pixels, clipping controls inside a tiny scrollbar.

No graphics backend, project format, save mechanism, Cloudflare service, supporter key, or updater binary is changed.

## Ownership and updates

Application windows take read-only, read-shared handles to the existing updater lock. The updater retains its existing exclusive read/write handle, so an update cannot start while either application window holds its lease. The final close releases updater exclusion. Windows also releases handles after process termination.

The editor's separate instance lock and report reviewer's separate instance lock still prevent duplicate hosts. The editor attempts pre-Qt request forwarding after obtaining its shared lease; an acknowledged delivery or forwarding error releases that lease without replaying the request. Older exclusive readers continue to block new readers until the older window closes.

The lock file is opened without truncation, write sharing or delete sharing. Reparse points, directories and hard links remain rejected. Installation identity and updater paths are unchanged.

Report startup failures close resources before displaying an error. Cleanup continues if another resource fails to close. English/Korean messages distinguish installation verification failures from contention and generic startup errors. Only verification failures suggest installation repair. Diagnostics record exception type and Windows error number, not report content.

## Layer panel

The wrapped toolbar and other fixed panel controls no longer flex-shrink. The virtualized layer list retains its own scroll area and minimum height. A short panel can scroll as a whole instead of clipping toolbar rows. Collapsed panels retain their previous behavior.

## Regression coverage

- `editor-update-guard.test.py`: simultaneous readers, exclusive updater in both directions, file identity/content preservation, crash release, hard-link rejection and pre-Qt forwarding cleanup.
- `test_support_window_startup.py`: both launch/close orders through report startup, updater contention, failed listener, cleanup failure, existing-report forwarding and damaged baseline.
- `test_support_window.py --editor-mode native|chrome [--report-first]`: actual editor and report windows, isolated local authorization fixture, large report, sign-in retry/fallback, reviewer refresh/restart and final updater release. No live report submission.
- `regression-layer-toolbar.js`: English/Korean, four built-in editor themes, five viewports from 900x640 to 3840x2160, simulated UI scaling from 100% to 200%, toolbar geometry, button hit areas and group menu interaction.
- Existing startup, instance ownership, IPC, close lifecycle, baseline, layer dragging, double-click navigation, responsive layout and dense editor workflow suites remain required.

The quality workflow runs shared-lease unit tests and both native editor/reviewer launch orders on Windows for subsequent changes. Layout screenshots and private run logs stay under `runtime/test-runs/20261017-editor-report-fixes`, not in Git.

## Validation limits

Local qualification passed: 1,194 DIRTY application tests (one existing skip),
55 JavaScript suites, 75 editor lifecycle/guard/baseline unit tests, the unchanged
Go updater bootstrap tests, four real editor/reviewer coexistence runs, 160
toolbar cases per host, and the dense editing/navigation workflow suites.
The corrected minimum-height sweep additionally passed 160 Chrome cases at
270px/135px panel heights. CLEAN passed 1,175 application tests (one existing
skip), the same 55 JavaScript suites and 75 editor Python tests, and real
editor/reviewer coexistence and Chrome toolbar qualification.
An activation-storage case failed once in the default temporary directory;
its isolated recheck and the complete suite with an isolated temporary directory
passed. No activation code was changed.

UI tests run offscreen or in an isolated headless Chrome profile to avoid taking desktop focus. Simulated UI scaling is not a physical mixed-DPI monitor test. Offscreen Qt emits GPU-context diagnostics on the local test machine; this does not establish graphics-driver compatibility. The reporter's specific Windows preview build has not been reproduced locally.

Do not reuse a dirty document between suites that require a saved-page reload. Save through the UI or start a fresh host/profile. Saved projects and recovery data must never be cleared to make a test pass.
