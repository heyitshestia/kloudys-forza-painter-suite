# Editor workflow improvements (3.1.103, 2026-10-17)

## Publication qualification

The user authorized promotion to CLEAN and main with a version bump and no new
public release or bundle. The earlier DIRTY-only scope and results below are
historical checkpoints. The promoted production changes are limited to the
editor UI/group owner and English/Korean catalogs; the nine focused tests and
shared test harness accompany them. Personal installations, runtime settings,
keys, artwork and unrelated DIRTY experiments are excluded.

CLEAN publication evidence is stored locally under
`runtime/test-runs/20261017-editor-workflow-publication/`.
The four core editor files in the frozen pre-change baseline matched CLEAN
3.1.102 exactly before promotion. This confirms the selected changes do not
carry unrelated DIRTY work. Revalidate both editor hosts and local quality
checks, then require all GitHub quality gates before signed updater publication.

Local CLEAN qualification:
- `native/results.json` and `chrome/results.json`: all five workflow suites
  pass, with no page errors or unexpected dialogs. Normal shutdown passes.
- `native-restart/results.json`: a fresh editor process retains the custom
  shortcut, saved colours, Korean locale and group hierarchy; shutdown passes.
- All 55 JavaScript syntax checks/unit suites and eight localization tests pass;
  catalog and editor manifest checks pass.
- `app-tests.log`: 1,167 app regression tests run, one skipped, no failures.
- The reviewed commit contains only the 21 explicitly selected source, test,
  translation, changelog and version/documentation files. No runtime artifacts,
  personal settings, credentials or artwork are included.

Lookback: CLEAN reproduces the tested DIRTY behavior without importing unrelated
work. Both existing editor hosts remain the authoritative integration paths;
no new save mechanism, service deployment or release-bundle work is needed.

## Scope and baseline

Six requested editor workflows only. No changes to CLEAN, Native Updated Local,
game saves, releases, version numbers or online services. Use background native
test windows and isolated test profiles; do not activate the user's windows.

Baseline source checkpoint and test logs:
`runtime/test-runs/20261017-editor-workflow/baseline/`.
Baseline: all 53 JavaScript syntax checks and unit suites pass.

## Contracts

- Saved colours: slots 1-8 use 1-8, slots 9-16 use Ctrl+1-8. Bindings are
  configurable through existing shortcut settings. Empty slots do not recolour
  artwork. Typing, IME composition and modal dialogs suppress global shortcuts.
- Space toggles reference visibility without changing opacity, placement or size
  lock. Guide-tool Space panning retains priority when its pointer is active.
- Double-click an individual canvas shape to reveal, select and scroll to its
  layer, opening ancestor groups and clearing a conflicting layer search. This
  does not change canvas zoom, geometry or history. Reference/guide tools and
  selection lock are respected. Group-list double clicks still do not centre.
- Copy a shape independently without its partial ancestor groups. Complete
  selected groups retain their internal hierarchy with new identities on paste.
- Group with one complete group plus loose shapes extends the existing group.
  New Group explicitly creates a parent. Add to Group selects an existing target.
- Drop in the middle of a group header to add membership. Header edges keep
  depth reordering. Membership changes leave shape transforms and depth intact.
  Cycles, missing objects, excessive nesting and filtered-list dragging fail
  without changing the document. Undo/redo remains one operation per edit.

## Milestones and validation

1. Extend existing shortcuts, reference owner and virtual list navigation.
   Verify keyboard events, locked layers, empty palettes and 3,000-layer lists.
2. Extend existing group metadata owner. Verify partial/full group copying,
   nesting, cycle rejection, membership, depth and transforms.
3. Exercise real native editor actions in background, persistence and undo/redo.
   Run existing regression and localization checks. Reopen saved test artifacts.

Stop at a tested DIRTY build and report remaining gaps. No publishing authorized.

## Lookback: implementation design

Existing shortcut configuration, reference visibility, flat Fabric scene and
virtualized list already solve most infrastructure requirements. Reuse them.
The grouping issue is metadata/selection semantics, not rendering or Forza data.
Separate explicit nesting from adding members; avoid introducing a second scene
model. Native tests must verify behaviour rather than relying on helper tests.
No tuning loop or expensive job is required. Continue with bounded regressions.

## Lookback: native drag test

Two centre-drop assertions failed despite correct membership helper tests. The
captured pointer evidence showed the target row moving after auto-scroll; the
test kept aiming at its old position, now in the reorder edge. The test must
track the live row centre before judging membership. Auto-scroll now stops while
an actual group-centre target is active, and refreshes feedback after scrolling.
This is an interaction/test geometry issue, not a reason to replace grouping.

## Lookback: compact layouts and shutdown

Chrome's smaller default window exposed a real layout regression: two extra
standalone grouping buttons could squeeze the layer viewport to zero height.
Add to Group and New Group now live in a compact group-actions menu next to
Group. The layer viewport keeps at least one row available; the toolbar scrolls
when constrained. No separate editor shell or duplicated layout was introduced.

The first final native shutdown check left the synthetic document unsaved. Its
page tests passed, but shutdown correctly remained pending instead of discarding
work. The edge suite now saves through Save As before requesting a clean close.
The next native runs verified the actual shutdown handshake successfully.

## Verified results

All paths below are relative to `runtime/test-runs/20261017-editor-workflow/`.

- `native-complete/results.json`: all seven UI regression suites pass together
  in the real bundled Qt editor. `native-close.json` confirms normal shutdown.
- `chrome-complete/results.json`: the same seven suites pass together through
  the installed Chrome editor host. `normal-close.json` confirms normal shutdown
  and that the controlled test reload allowance was cleared.
- Both complete runs have no page errors or unexpected native dialogs.
- `native-restart/results.json`: a fresh editor process retains Korean language,
  the custom colour binding, saved palette and project grouping. Transient layer
  highlighting does not persist. Normal shutdown passes.
- JavaScript runner: 54 syntax checks/unit suites, zero failures (baseline 53).
- English/Korean catalog validation and all eight localization tests pass.
- Group unit tests exhaust all 1,275 nonempty selection/target combinations in
  the representative eight-shape, five-group tree, including atomic rejection,
  unchanged native values and valid serialized hierarchy.

Coverage includes all 16 colour bindings, empty/locked slots, repeat suppression,
typing/contenteditable/IME, rebinding and persistence, reference visibility and
guide panning, individual/full/one-member group copying, extending and explicitly
nesting groups, real pointer membership drops, cancellation, cycle/depth/stale
input guards, exact undo/redo, full-capacity paste rejection, project save and
reopen, and virtual navigation through 3,000 shapes. Membership-only operations
were compared against native exported shape values: geometry and stack order
remain unchanged. Adding 2,000 shapes to a 1,000-shape group was also exercised.

The bulk membership operation measured 28.2 ms in Qt and 36.1 ms in Chrome in
the final complete runs. These are local operation timings, not end-to-end rendering or
performance guarantees for other PCs.

Each editor mode passed 24 layout combinations: English/Korean, pastel/dark/
blackout/whiteout, and 1760x1040/1280x800/900x640. Checks cover the group menu,
dialog padding, text escaping and all 16 colour labels. Existing reference
controls also pass their 12-layout regression. Screenshots are alongside results.
Repeated-use tests include 12 membership/undo cycles, 30 reference toggles,
legacy shortcut conflicts, stale dialogs and reopening hidden/collapsed docks.
All new test data is synthetic. Tests used background/no-activation windows and
isolated profiles. No user project was loaded or changed.

## How to try it

- Reopen the editor from DIRTY using either the normal or Chrome editor setting.
- Saved colours use 1-8 and Ctrl+1-8; change bindings in the existing Keys panel.
- Space toggles the reference image; guide-mode Space panning keeps its priority.
- Double-click an individual canvas shape to reveal its layer. Double-click a
  layer still centres that shape on the canvas.
- Copy/paste individual shapes without inherited partial groups. A complete
  selected group retains its hierarchy with independent identities on paste.
- Select a complete group plus loose shapes and press Group to extend it.
  The `...` menu beside Group provides Add to Group and explicit New Group.
- Drop a layer in the centre of a group header to add it. Header edges retain
  depth reordering; a centre drop does not change native stack order.

## Final lookback and scope audit

The requested six workflows are implemented using the existing editor owners.
The observed product failures were compact layout sizing and a layer highlight
lost during virtual-row redraw; both were corrected and retested. Test ordering,
pointer-coordinate and close-handshake assumptions were also corrected in the
harnesses without relaxing production safeguards. No unresolved product failure was
found in the exercised workflows; physical keyboard layouts and other users'
hardware remain unverified. No GPU/driver compatibility claim is made.

Changes are limited to the editor web UI/group owner, English/Korean catalogs,
seven focused test files, the shared test runner's Chrome navigation handling,
this document and the local integrity baseline. Test
artifacts remain under the established runtime/test-runs directory. Existing
unrelated modifications are preserved; no new workspace or repository was made.
No changes were promoted to CLEAN, pushed, version-bumped or bundled.

## Continued qualification

Scope remains the same six features in DIRTY. Additional milestones: verify all
1,275 selection/target combinations on a representative nested group tree;
exercise repeated and stale UI operations; inspect the new controls in both
languages and all four built-in themes; then verify persisted state after a
fresh editor process. No broader editor redesign or release work is in scope.

The group matrix passed. The first repeated-use test exposed a test-fixture
mistake: changing a lock directly bypassed history, so undo could not restore
that unstored test state. The fixture now loads the locked layer normally.
The next test found a product issue: a hidden dock's scheduled redraw removed
the canvas-to-layer highlight. The highlight is now tracked independently of
temporary row elements, retained on redraw, and cleared when its shape is no
longer selected or the document changes. This uses the existing virtual list,
not a second list implementation.
The corrected repeat test passes in both complete editor qualification runs.

Combined runs also exposed test ordering assumptions: Save on an already named
project does not request a name, and the responsive side panel overlays the
canvas centre at narrow widths. Tests now use Save As when naming an artifact,
aim only at a verified unobstructed canvas point, and clear their own search
filters. No production behavior was changed to accommodate those assumptions.
Visual review additionally found missing dialog padding; Add to Group now reuses
the editor's compact dialog header/body and a specific translated target label.

Lookback after the combined test runs: no new grouping/data-contract problem
appeared. The remaining failures came from retained test viewport/project/search
state and a cancellation assertion made before the browser's asynchronous close
event. Keep the product implementation; strengthen the test preconditions and
wait for observable completion. Avoid adding timers or special cases to the
production editor to satisfy test timing.

The longer Chrome run exposed one further harness issue: raw Playwright reloads
were interpreted by the browser host as close requests. Controlled test reloads
now require a saved, idle document and use a navigation-only allowance that
expires with the old document. The final host close separately verifies that
the allowance is absent and the normal close handshake completes. Unexpected
native dialogs are recorded and fail the harness rather than only printing a
callback exception. Production browser/save/close code is unchanged.

## Completion audit

The final combined native and Chrome runs, plus the fresh-process native restart,
all passed. Test hosts and their browser processes exited. The implementation
continues to reuse existing shortcut, group, persistence and virtual-list owners;
no additional architecture is needed. Scope remains the six requested workflows.
Earlier failed experiments are retained as diagnostic evidence, not presented as
passing runs. The authoritative results are the three directories indexed above.
Existing unrelated working-tree changes remain untouched. No promotion, version
bump, GitHub push, release or bundle was performed.

## Additional durability qualification

Requested follow-up, same DIRTY-only/background scope. Milestones: exercise
mixed old/new group copying repeatedly with exact undo/redo; inject clipboard
quota and project-write failures without touching personal data; use grouping
and colour shortcuts during a real delayed save acknowledgment; abruptly exit
only the isolated test editor after a durable unsaved checkpoint and reopen it.
Success requires unchanged saved revisions, no loss of newer edits, independent
paste identities, successful retry, and exact recovery through the autosave picker.
Reuse existing native/Chrome and recovery harnesses. New evidence belongs under
the same dated test-run root; stop after recording results and remaining gaps.

Results:

- `chrome-durability-01/results.json`: new durability suite and existing save
  revision/recovery migration suite pass; normal close passes with no dialogs.
- `native-durability-01/results.json`: the same tests plus a 3,000-shape dual
  recovery-store check pass. The test host then exits without its shutdown
  handshake, recorded in `native-abrupt-exit.json`; its renderer also exits.
- `native-durability-recovered-01/results.json`: a fresh native process uses the
  original isolated profile. Loading through Recent Autosaves restores exactly
  the unsaved checkpoint, including group membership, identities and colours.
  Save after recovery and normal shutdown both pass.
- Clipboard tests cover old flat-group metadata, mixed complete/partial groups,
  15 repeated pastes with distinct identities, 15 exact undos/redos, and an
  injected clipboard-storage quota failure that leaves in-memory copying usable.
- A real project save is committed while its acknowledgment is delayed. Group
  membership and colour edits made during that delay remain dirty and recoverable;
  the saved file retains its captured revision. An injected pre-commit failure
  leaves both that file and newer edits intact. Retrying and reopening is exact.
- Existing native close lifecycle tests: 36 pass. Recovery-store tests: 19 pass,
  including corrupt-checkpoint fallback and failed atomic replacement. The
  JavaScript runner again passes all 54 syntax checks/unit suites.

Lookback: no new product defect appeared. Test faults were bounded to isolated
profiles and restored before normal shutdown; no production safety policy was
relaxed. Save/recovery integration now has direct workflow evidence, rather than
only unit-level coverage. No further implementation changes are justified by
these results. Remaining external gaps include other hardware/drivers, physical
IME/keyboard layouts and user-specific accessibility/display configurations.

## Shortcut validation hardening

Authorized follow-up: DIRTY only, no focus activation, promotion or release.
Reuse the existing shortcut owner rather than adding a second command router.
Milestones: one reservation policy for assignment and saved-binding loading;
visible English/Korean validation; default/legacy/duplicate/malformed settings
matrix; real native and Chrome rebinding, persistence and workflow regressions.
Success means all 17 new actions remain configurable with supported combinations,
protected controls cannot be reassigned, and valid older bindings retain priority.

The rejected alternative was to validate only the Keys UI: persisted profiles
would still bypass it. Host-specific maps were also rejected because a setting
must remain usable when switching between normal and managed Chrome modes.
Retain the established app-mode Ctrl+D and Ctrl+1-8 defaults; reserve other known
Chrome accelerators, Windows keys and fixed navigation controls. Space retains
its existing reference/guide context, and plain Backspace/Delete may only be
assigned to Delete. AltGr/IME events cannot capture or invoke editor shortcuts.

Primary references for the conservative reservation policy (no external code):
- https://support.google.com/chrome/answer/157179?hl=en
- https://support.microsoft.com/en-US/Windows/Hardware/Input-Devices/windows-keyboard-tips-and-tricks

Limits: global shortcuts installed by third-party programs cannot be enumerated
or guaranteed by KFPS. Reserved accelerators are tested by DOM dispatch into the
real capture handler, not by invoking destructive/window-changing OS shortcuts.

Qualification results:
- `native-shortcuts-01` and `chrome-shortcuts-02`: all five suites pass together
  (shortcut validation, original workflows, repeated use, durability and layout).
  Normal shutdown passes, with no unexpected dialogs or page errors.
- Both modes rebind and exercise all 17 new actions through the actual Keys UI,
  persist them across reload, reject 17 representative protected/conflicting
  events, preserve Tab/Escape focus handling, suppress AltGr and repair injected
  invalid/duplicate saved settings. Korean feedback and Reset Defaults pass.
- The rejection stays in the sticky dialog header while lower entries scroll.
  Verified at 1760x1040, 1280x800 and 900x640 in four themes; the narrow Korean
  screenshot was visually inspected. The existing 24-case layout suite passes.
- `native-shortcuts-restart`: a fresh process retains Korean, the custom saved
  colour binding, palette and saved grouping; normal shutdown passes.
- `editor-shortcuts.node.js`: 2,065 protected action/combination cases pass,
  plus all defaults, all new actions, malformed settings, duplicate/disabled
  persistence, modifier normalization, plus-key parsing and IME/AltGr cases.
- All 55 JavaScript syntax checks/unit suites and eight localization tests pass;
  English/Korean catalog validation passes.

Lookback: UI-only validation was indeed insufficient for saved profiles. The
shared policy closes that gap without changing normal key dispatch or the data
model. Visual review caught a scrolled-away rejection message; moving it into
the existing sticky header fixed it without adding another modal. No workflow
regression appeared. The remaining global-hotkey and physical-layout limits are
explicit, so no claim of universal OS-level conflict detection is made.

Changes remain in DIRTY: shortcut handling, its dialog/status styling,
English/Korean catalogs and generated packs, two focused tests, this record and
the local integrity baseline. No CLEAN/personal instance edits, publication,
version bump or release work occurred. All test hosts were closed.
