# Interaction Qualification Register

This is a maintenance map, not a claim that every possible gesture, file or device
has been tested. Test scripts are in `../web/tests/`. The source/function inventory
and native control capture supplement this map; counting functions or finding a
selector in a test is not behavioral coverage.

## Shape and Canvas Input

| Family | Normal and boundary cases | Regression entry points | Qualification |
| --- | --- | --- | --- |
| Pick a shape | Filled interior, transparent area, small/rotated shapes, controls, dense scene | `bounded-picking`, `small-control-picking`, `dense-rotation-overlay` | Real pointer cases plus geometry assertions; ring-pixel assertion remains unqualified |
| Layer selection | Row selection, selected/unselected layers, same shape/color, inverse, clear, all | `tool-workflows`, `dense-multiselection`, `layer-drag` | Buttons and pointer workflows; dense setup is synthetic |
| Move | Drag selected shape, rotate then immediately drag, wheel zoom then drag, large reference above/below | `pan-zoom`, `dense-rotation-overlay`, native performance/soak harnesses | Paired dense input and 21-minute run; not all GPU drivers |
| Rotate | Handle, left/right buttons, numeric angle and label drag, cancel, undo/redo | `tool-workflows`, `dense-numeric`, `numeric-boundary` | Actual input; the optional ring visibility test is NOT a pass |
| Scale | Corner/side controls, signed numeric scale, arithmetic, zero/invalid values, undo/redo | `transform-handle-matrix`, `dense-rotation-overlay`, `dense-numeric`, `operation-boundaries` | New dense matrix:384 real-handle cases, eight handles x four modifier states x four guide states x three types;3,000 visible shapes and24 MP reference. Exact undo and unrelated artwork preserved. Earlier256-case run was only an offscreen-background correctness fixture |
| Skew | Shift-modified control action, numeric skew, restored transform, document replacement during preview | `transform-handle-matrix`, `dense-numeric`, `numeric-boundary`, `input-commit-lifetimes` | All four corner handles actually skew with Shift; side controls retain their existing scaling behavior |
| Numeric input | Enter, repeated Enter, arrows, Shift/Alt steps, label drag, Escape, IME, stale focus and lost capture | `dense-numeric`, `numeric-boundary`; `editor-transform-inputs.node.js` | Real input plus owner fault tests; 3,000 layers and 24 MP reference |
| Nudge | Held keys, modifier steps, coalesced history, presentation failure after mutation | `input-commit-lifetimes`, `incremental-build` | Real keys and injected presentation failure |
| Flip | Horizontal/vertical, twice to original, undo/redo | `tool-workflows`, `history-operations` | Button and state round trips |
| Alignment | Left/center/right, top/middle/bottom, selection/canvas, distribution minimum count | `tool-workflows`, `operation-boundaries` | All six buttons and both distributions; helpers cover boundary preconditions |
| Guides | Click-click, drag, wheel during draft, right/middle/Space pan, Escape, tool switch, touch | `guide-navigation` | Actual native input with reference; 312 angle/constraint/grid geometry cases separately |
| Guide constraints | Free/horizontal/vertical, Shift at 45 degrees, grid start/end snapping, zero/huge grid sizes | `guide-navigation`, `guides-colors-shortcuts` | Pointer and controls plus geometry matrix |
| Shape snapping | Control-gated guide/grid contact; edge/center contact, anchored resize/skew | `guide-contact-matrix`, `transform-handle-matrix`, guide tests above | 96 real side/axis/angle/modifier cases and 24 masked cases on 3,000 visible-grid shapes; includes continued drag, escape/return, exact undo/recovery; 18 direct contact classifications |
| View | Wheel in/out, fit vinyl/full canvas/selection, panning, reference movement, tool switch | `pan-zoom`, `guide-navigation`, `reference-workflows`, `tool-workflows` | Actual input and state invariants |
| Group | Create/rename/ungroup, nested metadata, collapse/expand, hide/lock, selection propagation | `text-prompts`, `project-export-roundtrip`, `edit-commit-families`, `incremental-build` | Buttons and helper faults; editor-only metadata must survive project save |
| Reorder | Forward/back/front/back, layer-row drag and multi-selection order | `layer-drag`, `history-operations`, `edit-commit-families` | Pointer/button cases and commit-fault tests |
| Duplicate/copy/delete | Capacity, locked/hidden/grouped/masked layers, partial failure, stale completion, undo/recovery | `duplicate-commit`, `workflow-atomicity`, `layer-limit`, `incremental-build` | Actual buttons plus isolated fault injection; no silent partial commit |
| Replace shape | Single/matching replacements, placement mode, resource failure and history | `operation-boundaries`, `edit-commit-families`, `shape-identity` | Characterization and exact data assertions; not every replacement pair |
| Color/alpha | Palette slots, save/clear, zero alpha, multi-selection, locked layer, sampling, live sampling | `guides-colors-shortcuts`, `reference-workflows`, `input-commit-lifetimes`, `hybrid-alpha` | Color input events/buttons, pixels, undo and fault cases; not OS color-picker automation |
| Mask | Toggle, nested/order behavior, ineffective masks, renderer/export consistency | `tool-workflows`, `hybrid-alpha`, `project-export-roundtrip` | Real toggle and data/pixel tests |

## Documents, Resources and Settings

| Family | Cases | Regression entry points | Qualification |
| --- | --- | --- | --- |
| New/open | Dirty confirmation, cancel, queued/late load, interrupted resource preparation, recovery floor | `async-document-boundaries`, `operation-boundaries`, `startup-hardening`, `recovery-startup-floor` | Native workflows and fault injection |
| Save/Save As | Enter/Numpad Enter, duplicate name, byte cap, conflict, lost reply, explicit failure, reopened file | `text-prompts`, `project-receipts`, `explicit-save-timeout`, `storage-capacity` | Actual native file paths and durable receipt checks |
| Recovery | Idle submission, current/previous, independent disk/browser, retry, stale revision, graceful drain, crash/restart | `background-recovery`, `recovery-revisions`, `recovery-restart`, `shutdown-drain`, native close tests | Exact reopened state and injected failures; abrupt OS power loss is not guaranteed |
| Export | Flat JSON, exact transforms/order/colors/types, groups/reference excluded, overwritten output receipt | `project-export-roundtrip`, `export-receipts`, `shape-identity` | 1,400 catalog identities and exact flat/project round trips; no live game installation used in this pass |
| JSON/project browsers | List/open, stale responses, missing/invalid entries, cancellation, naming, saved associations | `browser-pipeline`, `project-receipts`, `text-prompts`, `tool-workflows` | Native page workflows; opening Explorer is not automated |
| Shape catalog | All tabs, search, favorites by mouse/keyboard, restart, shared loads, deadline/disposal | `shape-identity`, `catalog-loading`, `resource-lifetimes`, `tool-process-restart` | All 1,400 shapes; seven reported tile IDs, single-flight and late-reply faults |
| Fonts/text | Eleven font resources, digits, text creation, invalid/empty/count limits | `native-text-digits`, `generation`, `operation-boundaries` | Resource and page workflows; every string/font/spacing combination not qualified |
| Pixel conversion | Source/dimensions, capacity, progress/cancel, stale generation | `generation`, `async-document-boundaries`, `layer-limit` | Conversion/control boundaries; this is not a generator quality benchmark |
| Assets | Save/insert/rename/delete, independent storage, groups, layout, restart | `assets-controls`, `assets-persistence`, `assets-process-restart`, `assets-layout` | Real independent files and new-process round trip |
| Reference | Replace/hide/remove, opacity/transform/order, raster/layered SVG, sampling, tile eviction, large image | `reference-workflows`, `reference-tiles`, `large-reference`, `reference-budget`, `reference-file-limit` | Exact pixels/state, cancellation and faults; first large GPU upload remains costly |
| Reference / quarter-circle report | Fresh canvas, 5888x2816 reference, opacity, Save As, eyedropper/palette, zoom, quarter-circle rotation/move/resize | `reference-quarter-report`, `large-reference-preview`, parameterized `hybrid-failures` | Actual native input and saved/recovery reopen; matched first-zoom comparison and low-layer pixel/failure checks. Synthetic reference, not the reporter's file; does not prove the reported AMD crash fixed |
| Themes | Built-in/custom, preview/reset/cancel/save, failed POST/GET, late preferences, contrast, narrow window | `themes`, `theme-lifetimes`, `theme-no-persist`, `theme-restart` | Six basic and 33 advanced colors; native visual/contrast checks |
| Language | English/Korean, persistent switch, confirmation notice, IME, opaque names/IDs | `korean-localization`, `language-switch`, `language-restart`, native localization tests | Native/page and catalog validation; translations not externally re-reviewed |
| Help/tour/shortcuts | Help dialog, 12 tour steps, shortcut capture/collision/Escape/IME/reset, typing exclusions | `language-switch`, `modal-shortcuts`, `guides-colors-shortcuts`, `guide-help-layout` | Actual controls/key actions and layout checks |

## Native and Background Work

| Family | Evidence to rerun |
| --- | --- |
| Standalone/KFPS launch | Actual compiled EXE and KFPS bridge; direct/wrapped/legacy/partial layouts; occupied port and singleton activation |
| Native close | Save/discard/cancel, both machine deadlines, long user prompt, malformed/duplicate/late reply, renderer exit, storage failure |
| Background test policy | No-activation and stays-on-bottom flags; foreground PID assertion in compiled-EXE harness; never minimize frame tests |
| Rendering lifetime | Failed program/buffer/texture allocation, stale attributes, context loss/restore, fallback, final disposal; exact alpha/reference pixels |
| Logging | Bounded queues/rotation, semantic correlation, dropped-critical count, reload/disposal, inherited writer, unwritable/unsafe sink |
| Update | Signed upgrade/repair fixture, exact retired program files, partial replacement rollback, preserved projects/recovery/settings/profile, exclusive editor lease |

The executable script names above omit the common `regression-` prefix and `.js`
suffix. Fault injection intentionally uses internal owners where a physical device
cannot deterministically cause the failure. Such tests are not labeled human input.

## Dense Workflow Extensions

`dense-commands` covers selection, all alignment/distribution commands, groups,
flips, rotation buttons, masks, duplication/deletion, names and document reopen
with2,400 visible layers. `dense-documents` separates Save As, existing Save,
flat export, New, open, Fit and recovery timings with2,900 visible layers.
`dense-resources` covers tool modes,48-layer reusable assets, asset cancellation,
three text fonts, pixel conversion, favorites and saved reload with2,400 layers.
`dense-gestures` repeats rotation -> immediate move -> wheel -> immediate move ->
scale/Shift-skew on five primitive types with2,950 layers and a large reference
above/below. Undo and all shapes are checked, not only the active object.

Text prompts, modal shortcuts, themes, language and guide/color controls also
accept dense fixtures. Small resource/worker/storage fault matrices are retained
as fault tests. These categories must remain distinct in reports.

## Remaining Qualification Work

The practical modernization gates are separate from the broader aspiration to test
every possible interaction. The finite handle/modifier and guide-side matrices above
do not cover every arbitrary shape, guide angle, zoom or combination of guides.
Remaining work includes long-session tests on the reporting user's GPU/driver; strict rotation-ring visual
qualification; OS file/color dialogs, unusual accessibility/input devices and real
power-loss/storage hardware. Do not quietly turn these into passes based on the
control inventory, synthetic shape count or a favorable average frame rate.
