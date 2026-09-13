# Editor Validation

See [Interaction Qualification Register](INTERACTIONS.md) for workflow families,
test entry points, input levels and remaining gaps.

Run tests against an isolated profile. Never point destructive/fault fixtures at a
personal installation or a user's project folder. Native tests default to background
windows without minimizing; foreground checks require an explicit reason.

## Fast Checks

From the repository root:

```powershell
py -3.12 tools/editor_manifest.py
node KFPS.Editor/web/tests/run-unit.cjs
py -3.12 KFPS.Editor/web/locales/manage.py check
py -3.12 KFPS.Editor/web/tests/editor-localization.test.py
py -3.12 KFPS.Editor/web/tests/editor-close-lifecycle.test.py
py -3.12 KFPS.Editor/web/tests/editor-bootstrap-log.test.py
py -3.12 -m unittest discover -s KFPS.UI/tests -p "test_editor*.py"
go -C tools/bootstrap_updater test ./cmd/kfps-update-tool ./internal/bootstrap
```

The page harness needs the existing Playwright/Node dependencies. Keep native
QApplication suites separate from tests that create QCoreApplication. Do not call
an offscreen graphics run equivalent to real-window pixel/performance validation.

## Update Awareness Checks

`test_update_status.py` exercises the shared main/editor Qt checker against a local
HTTP server, including versions, malformed/oversized responses, offline behavior,
request coalescing, timeouts and shutdown. `editor-updates.node.js` covers reminder
state, acknowledgement, later versions, failed settings writes and disposal.

`regression-update-indicator.js` runs in the native page harness. Its default phase
checks English/Korean layouts, reduced motion, the authenticated host snapshot,
real preference writes, and exact recovery with 2,401 shapes. Use `--abrupt-exit`
for this intentionally unsaved phase. Reuse its isolated profile with test options
`indicatorPhase: "restart"` and `previousOutput` pointing to the first output;
that phase verifies recovery and acknowledgement, saves, then supports
`--normal-close`. Offered future versions are intercepted test fixtures, never
changes to the public channel. These checks do not replace dense gesture testing.

## Dense Input

`dense-human-fixture.cjs` imports a synthetic mixed scene through the real file
input and records loaded, visible and selected counts. Dense fixtures use
2,400-2,950 shapes with insertion headroom; handle/contact matrices use3,000.
Shapes must actually be visible. Two-shape faults and offscreen padding are not
dense-use evidence. Reference opacity and order are recorded; latency comparisons
must use matching values. Real mouse/keyboard input drives operations, while
state reads verify exact undo, unrelated layers and persisted content.

`regression-dense-commands`, `regression-dense-gestures`,
`regression-dense-documents`, `regression-dense-resources` and
`regression-numeric-preview` provide separate operation timings, including the
delayed settled redraw. Frames are event-loop intervals, not guaranteed physical
display scanout. Do not hide tail stalls behind an average or aggregate initial
image decoding with steady gesture latency.

Dense gestures accept a bounded `minimumSeconds` and write minute checkpoints
without forced garbage collection. External native process-tree samples include
the host, renderer and GPU processes; JavaScript heap alone is not total memory.
Low-count report reproduction remains separate from realistic dense editing.
`primeHistory: true` first commits85 real keypresses and requires80 retained history
entries throughout endurance. Samples identify the Node test driver separately;
exclude it when describing product-only native allocation. `hit-cache-lifetime`
checks cache/dirty-state preservation through actual picking, pointer drags and
a throwing render. Allocation-count improvement is not automatically an FPS gain.

`regression-document-warmup` checks2900-layer project opens, optional exact baseline
PNG bytes, real wheel/drag interruption, exact drag undo, an injected cache-build failure and final
recovery. Cold document caches are prepared in short slices behind the existing
GPU preview, then normal Fabric drawing resumes. The slice budget is cooperative,
not a hard execution deadline for an individual shape. Diagnostic phase
`document-cache` distinguishes finished, cancelled and failed preparation;
`document-paint` is armed for the final normal drawing pass, not a hidden skip.
Any interaction or replacement can cancel preparation without changing artwork.
The input test waits for the project browser to close and records capture-phase
events that actually reach the canvas during preparation. Merely sending input
behind a loading dialog or observing a later zoom is not an interruption test.

Dense project readiness includes restored reference dimensions/order/opacity and
the expected clean state, not only the accepted layer count. Standalone dense
multiselection can create a2950-layer/48-member fixture with an explicit reference;
its historical3000-layer/50-member benchmark fixture remains supported. Report
the actual fixture rather than assuming a test filename establishes its size.

## Isolated Installation

`tools/stage.py` copies only manifest-declared editor program/shared files, verifies
their hashes, and excludes main KFPS UI, the generator and personal profiles. It
only creates new destinations inside `runtime/test-runs/`; it is not a publisher,
release bundle builder or updater.

```powershell
py -3.12 KFPS.Editor/tools/stage.py runtime/test-runs/my-editor-check/installation
```

Use `web/tests/run-native-page.py --app-root <stage>` for actual Qt/page workflows.
It verifies the sources parsed by the renderer against the selected installation,
not just whatever files happen to be in the development checkout.
Unexpected page errors fail the native harness. Deliberately injected errors must
match the exact workflow, message and count declared in `workflow-contracts.json`;
missing expected errors fail too. The final `pageErrors` record distinguishes these
injections from actual application failures. Older evidence without that record
requires inspecting its retained `errors` array before interpreting a green exit.
New runs retain the evaluated test source, its SHA-256 and options in `test-inputs`.
The capacity test checks the reference fixture's manifest dimensions before it
interprets a restart pixel-count assertion. Explicit forced-GC retention probes
are labelled and must not be treated as natural-session memory measurements.

Compile a test launcher using `tools/native_launcher/build_launcher.ps1 -Editor
-Output <stage>/KFPS Editor.exe`. Then use `web/tests/run-native-exe.py <stage>
<new-output> <regression-script>` to exercise the real EXE, CLI, native window,
page workflow and normal close handshake. `--profile` qualifies process restart;
`--kfps-bridge` qualifies a cold launch through the actual KFPS bridge.

`qualify-package.py`, `qualify-launcher.ps1` and `qualify-update-guard.py` cover
declared dependencies, layout discovery, partial-install rejection, Windows lock
exclusivity and process-stop protection. The process-stop test supplies mocked
process inventory and forbids calling the real Stop-Process command.

## Interpretation

For multi-monitor reproduction, the native page harness accepts `--screen-index`
and `--maximize` (fill that monitor's available area without raising the window).
It records actual Qt monitor geometry and scaling. Do not equate a browser's
`screen` metadata or an emulated viewport with verified native window placement.
`regression-reference-quarter-report.js` accepts an explicit local `reference` in
`KFPS_TEST_OPTIONS`; do not commit that image or use a personal project profile.
It assigns the local file through CDP to the real file input, avoiding test-tool
base64 construction stalls. Initial load, cold sampling, first zoom, continued
gestures and settling are separate measurements.

Keep raw failures and corrected reruns. A stale test path or wrong mock owner is
a fixture failure, not a passed regression. Deferred storage/network tests must
verify the actual saved revision and reopened data, not only Promise completion.

Compare performance against frozen source/fixture bytes under matching runtime,
viewport, scale, cache and reference state. Separate initial decode/GPU upload,
steady editing, explicit save, recovery, intentional validation and garbage
collection. Report tails and memory trends, not only average FPS.

The modernization's isolated runs include 3,000-shape/24 MP interaction tests,
a 21-minute gesture/recovery run, near-limit project storage, all 1,400 catalog
identities, eleven fonts, EN/KO workflows, injected renderer/storage faults and
editor-only launches/restarts. Those tests do not prove every driver, machine,
third-party input file or possible input combination safe. The original black-
canvas symptom has not been reproduced on the qualification workstation. Very
large first reference uploads and some all-layer operations remain slower.
