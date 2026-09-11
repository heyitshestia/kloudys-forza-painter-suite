# KFPS Vinyl Editor

The KFPS Vinyl Editor is the bundled independent desktop workspace for creating,
tracing, repairing, and organizing FH-compatible vinyl JSON. It uses native
Forza shape resources and enforces the 3,000-layer game budget.

The editor runs entirely on the local machine. The small local server exists so
the embedded browser engine can load bundled shape assets and save projects back into the KFPS
folder. It does not upload artwork. The server exposes only editor assets and
rejects mutation requests that did not originate from the editor page.

## Open The Editor

English and Korean are available from the lower-left language dropdown. A saved
choice takes precedence over the Windows display language and applies when the
editor is reopened. The first-run arrow notice stays until explicitly acknowledged.
See [localization maintenance](locales/README.md) for the shared catalog workflow.

Open `KFPS Editor.exe` beside `KFPS.exe`, or use the `Editor` page in KFPS:

- `New Canvas` opens a blank editor.
- `Import JSON` opens the editor's JSON browser.
- Select a saved project and choose `Open Project` to continue it.
- `Tutorial` resets the first-run guide for the next editor launch action.
- `Folder` opens the internal project folder.

Both routes reuse one editor window per installation. The editor owns its local
server and remains open when KFPS closes. KFPS still lists and previews the same
projects and receives project/export change notifications. Fabric, the editor
tools, and project/game JSON formats have not been replaced.

Close the editor before updating KFPS. The editor holds the installation's
updater lock so an update cannot replace files underneath unsaved work.

## Save, Recovery, And Export

These are three separate operations:

| Operation | Purpose | Location |
| --- | --- | --- |
| `Save` | Updates the current editable project. | `runtime/fabric-editor/projects/` |
| `Save As` | Creates another editable project. | `runtime/fabric-editor/projects/` |
| Recovery copy | Protects recent unsaved work after an interruption. | `runtime/fabric-editor/autosave.json` and browser storage |
| `Export JSON` | Validates and creates an import-ready flat vinyl JSON. | `imgs/editor/` |

Projects preserve editor-only organization such as guides, internal groups,
hidden and locked state, and the reference image. Exported JSON contains only
the flat vinyl layers needed by KFPS import workflows.

In naming prompts, Enter (including numpad Enter) confirms the entered name:
first Save, Save As, unnamed JSON export, layer rename, and group rename.
Cancel and Escape discard the prompt. Enter in the theme-name field saves the
new theme; Enter in the multiline text builder still inserts a newline.

The project title shows `Saved` or `Unsaved`. Closing the desktop window offers
Save, Discard, or Cancel for unsaved edits. It flushes pending recovery and settings
before closing; write failures keep the window open unless you explicitly choose
to close anyway. Discard leaves the last recovery copy available. Opening another
document, including from KFPS, also asks before replacing unsaved work. Recovery
is a safety net, not a replacement for `Save`.

## Reusable Groups

The `Assets` tab stores independent copies of selected artwork. `Save Selection`
keeps shape identities, colors, transforms, masks, visibility, names and group
metadata. Search the thumbnail grid and choose `Insert` to add a separate copy
at the current view center. New layers and groups receive fresh IDs; copies are
unlocked, matching Paste. The 3,000-layer limit is checked before insertion.

Saved assets live only in `runtime/fabric-editor/assets/*.asset.json`, not in
`imgs/editor`, generated outputs or the game/library JSON folders. They do not
link back to source files. Deleting an export or source project cannot remove a
saved asset, and editing/deleting a saved asset cannot change inserted copies.

The asset menu provides Rename, Export Asset and Delete. Portable
`.kfps-asset.json` files preserve reusable groups and can be added with Import
Asset. These are editor asset files, not flat game-import JSONs. Existing project
files remain the format for sharing a whole editable project.

Asset writes are atomic and use revision checks; unreadable files are reported
and retained. Each asset is limited to 8 MB and 3,000 layers. Thumbnails preserve
native gradient alpha and masks, exclude hidden layers, and use a 32-entry
rebuildable memory cache. A missing preview does not delete or prevent insertion
of the saved artwork. The grid initially mounts 40 assets, with Show More for
additional entries.

## Selection And Numbers

`Cycle overlapping layers` is off by default and persists with editor settings.
When enabled, repeated clicks cycle through the visible shapes under the pointer.
A stationary right click opens the overlap menu; right-drag still pans. Picking
uses shape/image alpha instead of bounding boxes, ignores locked/hidden layers,
and respects selection lock and tool modes. The menu supports arrow keys,
Home/End, Enter and Escape.

Transform fields accept bounded arithmetic using `+ - * /`, parentheses,
decimals and percentages (`50%` is `0.5`). Enter or leaving the field commits a
valid value; Escape restores the current value. Invalid expressions and zero
scale do not alter the artwork. Drag a numeric label to adjust its field, with
Shift for larger steps and Alt for finer steps. A complete drag makes one undo
step; Escape or losing window focus cancels it. Arrow keys still step values.

## Favorites And Settings

Favorite shapes, favorite colors, theme, shortcuts, dock layout, and text-tool
preferences are stored in `runtime/fabric-editor/preferences.json`. They are
loaded before the editor initializes and survive closing/reopening the editor,
KFPS restarts, and a change of local server port. Rapid changes are coalesced and
pending writes are completed on normal window close. Failed writes are retried
and reported; unreadable settings are not silently replaced with defaults.

Existing projects, recovery, exports, and custom themes stay in their established
folders. Settings that existed only in a previous external browser's storage are
not automatically accessible to the new desktop profile. They are migrated only
when available in the current browser origin; no browser profile is scanned.

The original `start_fabric_editor.py` browser path remains available for diagnosis.
Do not edit the same project in browser and desktop sessions simultaneously.

See `docs/EDITOR_DESKTOP.md` for development, validation, and release requirements.

## Themes

Signature Pink and Dark remain available alongside neutral, matte Blackout and
Whiteout. Adjust shows six main color controls, a starting-theme selector and
Reset colors. More colors contains the remaining detailed controls. Text contrast
status warns about low-contrast edits; invalid color values cannot be saved.
Cancel restores the original theme. Saved custom themes retain their base styling
and colors across restarts. Long theme names do not resize the header controls.

Project reloads retain custom layer names. Open dialogs protect the canvas from
keyboard shortcuts. A stalled explicit save times out after 30 seconds, retaining
unsaved work and restoring the save controls for retry.

## Workspace Layout

### Header

- `File`: New, Open JSON, Open Project, Save, and Save As.
- `Edit`: Undo, Redo, Copy, Paste, Duplicate, and Delete.
- `View`: Fit Vinyl, Full Canvas, Selection, and Panels.
- `Finish`: Export JSON, Tour, Help, and configurable Keys.

The options bar below the header keeps the active tool, selection, placement
mode, active color, common actions, and export readiness visible.

### Tool Rail

- `Select`: select, box-select, move, resize, skew, and rotate.
- `Shapes`: search and place bundled native shapes.
- `Text`: build editable text from native Forza letter shapes.
- `Pixel`: convert deliberate pixel art into merged rectangle layers.
- `Dropper`: sample a vinyl or reference-image color.
- `Guides`: draw guides and configure snapping.
  Draw by dragging, or click a start point and then an endpoint. Zoom with the
  wheel and pan with middle/right drag without losing the start point. In Guides,
  Space temporarily pans unless assigned to a custom shortcut. Escape cancels a
  draft. Shift constrains free lines to 45-degree increments; explicit horizontal
  or vertical mode takes precedence, followed by angle lock, then endpoint-grid
  snapping. Drafts do not enter history or exports until committed.
- `Reference`: load, show, scale, and sample a tracing image.
- `Move Ref`: move the reference without touching vinyl layers.
- `Mask`: toggle the selected layers as mask/cutout layers.

Choosing a tool opens the matching inspector. The Layers panel stays available
above it so layer order and selection are never hidden behind another tool.

### Layers And Inspector

The upper right panel is the persistent layer stack. It supports:

- search and virtualized browsing for large designs
- visibility and lock controls
- internal groups and group collapse
- layer and group naming
- one-step and edge layer ordering
- shape replacement
- selection locking

Drag the divider to give Layers or the inspector more room. Collapse Layers or
hide the complete dock when canvas space matters. The layout is remembered.

The lower inspector contains:

- `Properties`: color, opacity, exact transforms, flips, rotation, alignment,
  distribution, and selection tools
- `Shapes`: searchable native library and favorites
- `Text`: native-letter text construction
- `Pixel`: pixel-art detection and merged rectangle construction
- `Guides`: grid, guides, snap options, and nudge size
- `Reference`: image and layered-SVG tracing controls
- `History`: visible undo/redo timeline and saved-source markers
- `Export`: errors and warnings found before export

## Selection And Placement

- Click a visible shape or its layer row to select it.
- Shift-click or Ctrl-click layer rows to build a multi-selection.
- Drag empty canvas to box-select.
- Hold the Select shortcut while starting a drag over a shape to force a box
  selection.
- Use `Visible only`, `Invert`, `Same Shape`, and `Same Color` for dense work.
- Use align and distribute controls for precise multi-layer layout.
- Locked layers are skipped by destructive and transform actions.

The `Place` selector controls new shapes and duplicates:

- `At top`: add above the complete design.
- `Above selection`: insert immediately above the selected range.
- `Below selection`: insert immediately below the selected range.
- `Replace once`: replace the selected shape type, then return to `At top`.

## Transform And Canvas Controls

- Mouse wheel: zoom.
- Middle- or right-drag: pan.
- Side handles: change width or height along the shape's own axes. Skewed edge
  directions stay unchanged and the opposite edge stays anchored.
- Corner handles: uniform scale.
- Shift with a corner handle: skew.
- Corner gestures start from the point grabbed, without resetting existing skew.
  Pressing or releasing Shift during a drag switches mode without jumping.
- Arrow keys: nudge by the configured amount.
- Shift+Arrow: nudge ten times farther.
- Hold X or Y during a drag: constrain movement to that axis.
- Hold Ctrl near a visible grid or guide: snap the active edge.
- Rotation uses a temporary 45-degree notch ring.

The `Properties` inspector also provides exact X, Y, width, height, angle, and
skew input plus flip, quarter-turn, align, and distribute commands.

## Shapes, Text, Pixel Art, And References

The shape library reads names and type codes from the bundled FH resources.
Search accepts a family, display name, index, or type code. Favorites and the
last active color persist locally.

The Text tool converts entered characters into editable native Forza letter
layers. The Pixel tool is intended for deliberate low-resolution pixel art and
merges adjacent same-color cells where possible.

Pixel decoding/grid analysis runs in a short-lived worker separate from recovery
storage. Rectangle merging streams rows and stops when the available layer budget
is exceeded, without allocating the entire generated grid. SVG sources unsupported
by worker decoding use the existing DOM rasterizer before transferring pixels for
background analysis. New cancels pending analysis. Pixel/text replacement builds
the new layers before removing previous output; resource failures or intervening
document edits keep the existing work. Large object builds yield between batches.
Native Forza font generation no longer rasterizes an unused text mask.

Reference images are tracing helpers. They can be moved, scaled, faded, sampled,
and saved with an editable project, but never become exported vinyl layers.
References have no editor-imposed megapixel cap. Original pixels are retained
for color sampling and project storage; only the GPU display texture is resized
when it exceeds the device's texture dimension limit. Large images need more RAM
and loading time, and remain subject to the browser's image/canvas capabilities.
The stored-source budget is 100 MiB; project save and recovery requests are limited
to 150 MiB. These measure serialized/embedded data, not the source file on disk.
Base64 raster embedding adds roughly one third, so a source file near 75 MiB can
fill the 100 MiB reference allowance. Other project metadata consumes additional
space; a reference below its allowance does not bypass the total project limit.
Large projects require more memory and can pause longer during save/recovery.
Browser-only recovery remains subject to its own storage quota; check that recovery
was saved in KFPS, especially with large embedded references.
References rejected by these storage checks leave the current reference in place.
Projects above the previous limits require an editor version supporting the
higher budgets to save or recover normally. Indented project files on disk can
be slightly larger than the serialized request limit.

## History And Recovery

Asynchronous Open/New, shape insertion, replacement, duplication and paste use
document ownership checks. Superseded work cannot reappear in a new document;
failed strict project/history rebuilds keep the existing artwork. Capacity is
checked again at insertion, including when more than one build finishes together.
Guide/grid/snap setting changes participate in project dirty state, history and
recovery. Fully transparent editable layers survive project and recovery reloads.

History records meaningful editing states, shows the active state, and marks the
last explicit save. Click a history entry to jump to it. The loaded source is a
protected boundary so an accidental Undo cannot erase the entire imported
design.

Undo while dragging cancels that unfinished move/resize and returns to the last
committed state. Releasing the mouse afterward does not reapply the cancelled
gesture. A subsequent Undo steps back through committed history normally.

Selection outlines and mask previews are temporary canvas helpers, not vinyl
layers. They are removed with their owners and when switching projects; old orphan
selection outlines are also cleaned up when selection is synchronized.

Recovery is queued after committed edits and reference changes: after 500 ms of
inactivity, or at most two seconds of continuous changes before starting a write.
Pending work is also flushed when the editor loses focus or goes into the
background. A blocked browser, full disk or interrupted process can still delay
or prevent persistence; recovery is not a substitute for saving important work.
Undo, Redo and history jumps update recovery to the restored state. Holding an
arrow key checkpoints the nudge at bounded intervals instead of waiting forever
for key release; pending nudges are immediately shown as unsaved.

Writes are serialized and coalesced to the newest revision. Temporary app-folder
failures retry after two seconds, backing off to at most 30 seconds. Status reports
whether recovery reached the app folder, browser storage only, or neither.
An identical committed write can be retried safely if its acknowledgement was
lost. Recovery reads fall back to the browser copy after a five-second server
timeout; writes time out after ten seconds and retry as described above.
A stalled app-folder write does not delay the newer browser recovery copy.
On reopening, the newer available recovery is selected. Legacy recovery files
remain readable, and revisioned clear markers prevent delayed writes from
resurrecting discarded work, including after a server restart.

Save acknowledges only the revision it actually stored. Edits made while Save
is running remain unsaved and retain recovery. Recovery is cleared only when
the current document still matches the saved revision.

Native triangle commands are shared read-only across matching shapes; Fabric
continues to own each shape's transforms, selection and rendering caches. Removed
objects release their instance resources without destroying shared source images.
If the GPU preview loses its context, editing falls back to Fabric while GPU
resources are recreated after restoration.

## Export Check

`Export Check` runs continuously and again before export.

Blocking errors include:

- no vinyl layers
- more than 3,000 layers
- invalid transform numbers
- zero-sized scales

Warnings include:

- hidden layers that will still export
- layers completely outside the FH canvas
- unresolved shape resources
- ineffective mask layers
- exact duplicate geometry

Warnings do not silently change artwork. Review and fix them intentionally, then
choose `Export JSON`. The resulting file appears under Editor exports in KFPS
Outputs.

## Default Shortcuts

| Shortcut | Action |
| --- | --- |
| `V`, `S`, `T`, `P` | Select, Shapes, Text, Pixel |
| `I`, `G`, `O`, `R` | Dropper, Guides, Reference, Move Reference |
| `M` | Toggle selected mask layers |
| `Ctrl+C`, `Ctrl+V` | Copy and paste selected layers |
| `Ctrl+D` | Duplicate selected layers |
| `Delete` | Delete selected layers or the selected guide |
| `Ctrl+Z`, `Ctrl+Y` | Undo and redo |
| `[` and `]` | Move selected layers backward or forward |
| `F`, `Shift+F` | Flip vertically or horizontally |
| `X`, `Y` | Constrain an active drag |
| `Shift+L` | Lock or unlock the current selection |

Open `Keys` to review or change these bindings.
New assignments that conflict with another action are rejected. Space can be
captured, and IME composition/dead-key events do not overwrite bindings. Existing
stored preferences are not silently reset; use Reset Defaults to repair older
conflicting custom bindings. Temporary theme previews do not change the saved
theme, and keyboard activation of a shape favorite does not insert a shape.

## Large Designs

For dense projects, the editor:

- indexes vinyl layers separately from guides and helpers
- constructs shape assets with bounded concurrency while preserving order
- virtualizes the layer list
- shares unchanged history state and restores changed objects in place
- serializes only known changed layers for transform commits, with full capture
  for structural/unknown edits and pending nudges
- avoids duplicate immediate export validation after a mouse transform; explicit
  export still performs a complete fresh validation
- defers recovery serialization during edit bursts
- uses a transient accelerated interaction preview from 300 layers upward
- resumes the exact Fabric render when interaction ends

The hard limit for import, duplication, text, pixel-art conversion, and export is
3,000 editable vinyl layers.

## Troubleshooting

The one-time **Sharing Projects And Groups** notice follows the introduction.
It requires **I acknowledge** before continuing and cannot be dismissed with
Escape. Share `.fabric-project.json` files to preserve editable groups; exported
game JSONs must contain flat vinyl layers. The acknowledgment is saved with the
app-folder editor preferences and survives editor restarts. A failed settings
write leaves the notice open for retry. Resetting the tutorial does not reset
this separate acknowledgment.

- If the editor does not open, read the status on the KFPS Editor page.
- Check `runtime/fabric-editor/desktop.log` for native startup and JavaScript errors.
- The native launcher waits for page readiness, not just an open process. If the
  page cannot start within a minute, Reopen Editor retries with a fresh document
  and no selected-project query. Existing saved projects, settings and recovery
  files are preserved; a recovery prompt can still be offered.
- Open Editor on the generator page activates the current editor without creating
  a new canvas. The Editor page's New Canvas keeps its explicit replacement prompt.
- A busy/unresponsive existing window is not replaced with a duplicate process.
  Finish its open/save/close dialog and retry. Early bootstrap failures are also
  recorded in `desktop-startup-error.json` with the failing process ID.
- Use Settings > `Reset Editor Tutorial` to show the first-run guide again.
- If the panels are hidden, use `View > Panels`.
- If a project is missing, choose `Folder` and confirm it ends in
  `.fabric-project.json`, then refresh the native Editor page.
- If export is blocked, open `Export Check`; it lists the exact layers involved.
- Reopening the native editor automatically resumes the last complete recovery
  checkpoint, including saved projects, references, groups and guides. Explicit
  New/Open requests take precedence. Browser-only use still offers recovery for
  confirmation. An unreadable newest copy falls back to an earlier complete copy.

## Interaction Performance Boundaries

The Fabric adapter suppresses only the hidden on-screen scene pass while the
hybrid GPU preview is active. Fabric's render lifecycle, selection/hit testing,
separate export contexts, and CPU fallback remain active. GPU requests share one
animation-frame queue. Ending an interaction still restores the authoritative
Fabric scene; large scenes can remain CPU-bound on slower machines.

Mask helpers reuse one stack snapshot and update coordinates only when their
transform, interaction state, or viewport changes. Geometry-only commits refresh
visible layer rows without rebuilding the entire layer index; a queued structural
refresh always takes precedence. Nudge history tracks all changed leaves and
retains the conservative full-capture fallback for structural/unknown changes.
Recovery cadence and portable project/export formats are unchanged. During edits,
export validation runs in small cooperative batches; explicit export still performs
the authoritative full check before writing game JSON.

## Background Recovery

Recovery is queued after 500 ms of idle time, with a 2-second maximum wait during
continued edits. One worker serializes and writes checkpoints to both the app folder
and IndexedDB. This avoids synchronous full-document localStorage writes. Unchanged
reference source bytes are stored once per content identity instead of being sent
again for each edit. Portable project files still embed their original reference;
internal recovery sidecars are not a replacement for sharing project files.

The app folder retains current and previous atomic checkpoints, a revision/clear
marker, and bounded SHA-256 reference sidecars under `recovery-references`. Browser
storage retains two checkpoint generations and their references. Native close waits
for the latest app-folder checkpoint and settings acknowledgement. Disk/quota/worker
failures are reported and retried; an older or failed response cannot replace a
newer revision. If the app-folder writer stalls, a separate coalescing path can
still save the newest browser copy. Startup clears only this store's abandoned
temporary files. Original project files are never deleted as recovery cleanup.

Recovery is not protection against every failure: killing the process before a
checkpoint is acknowledged can lose the newest uncommitted edits; unavailable disk
and browser storage cannot be called saved. Large initial image decoding/GPU upload,
project restoration and constrained-device rendering can still pause. The native
close warning lets the user keep the editor open when the latest checkpoint fails.

Project/JSON parsing and project encoding also run in the worker. Reference color
sampling uses exact original pixels through a bounded 8 MiB tile cache, not a second
full-image RGBA allocation. The 100 MiB embedded-reference and 150 MiB total
project/recovery budgets remain. Reference-only and guide-only preparatory work can
be saved and resumed before any vinyl layer is added.

JSON-browser requests are latest-wins and time-bounded. Selecting an existing
browser row retains thumbnail elements. Local preview responses use private HTTP
revalidation keyed by source/preview file metadata and server lifetime; unchanged
images avoid rendering again even after the bounded server image cache evicts
them. Cold directory scans and first-time previews still do real filesystem and
rendering work; aborting a browser request does not cancel that server-side work.

`tests/benchmark-performance-pipeline.js` measures real native-page interactions
at 1,400/3,000 layers, dense masks, large selections and synthetic CPU throttling.
`regression-performance-pipeline.js` and `regression-browser-pipeline.js` cover
the correctness boundaries above. `soak-performance-pipeline.js` keeps one
3,000-layer document open for 21 minutes with repeated edits, undo/redo, reference
replacement, recovery readback and saved-project verification. Use an isolated
profile and disposable artwork. Do not interpret throttling as measured hardware
performance or a short benchmark as proof that all stalls/leaks are eliminated.

The repository changelog records the 3.1.75 capacity, recovery and performance
changes. Local audit profiles, synthetic images and detailed run logs are not
distributed with the application.

## Developer Checks

`python tools/fabric-editor/tests/editor-launch-native.py <fresh-output-directory>`
exercises real Qt startup, occupied-port fallback, busy IPC rejection, a missing
JavaScript startup deadline, external retry, and renderer-crash retry. It uses an
isolated runtime and only terminates its own renderer. This is a Windows test and
runs in CI with `QT_QPA_PLATFORM=offscreen`. `regression-startup-hardening.js` adds
3,000-layer cold project opening in Korean, failed-read preservation/retry,
reference callback failure, and denied browser-storage coverage to the native
page regression harness.

The dependency-free geometry and ordering tests live in
`tools/fabric-editor/tests`:

```powershell
node tools/fabric-editor/tests/editor-core.node.js
node tools/fabric-editor/tests/editor-pixel-core.node.js
node tools/fabric-editor/tests/editor-persistence.node.js
node tools/fabric-editor/tests/editor-persistence-worker.node.js
node tools/fabric-editor/tests/editor-shell.node.js
```

`tests/editor-transforms.browser.js` runs through Playwright CLI's `run-code
--filename` against an already opened editor. Use an isolated local editor server
and disposable project/autosave directories: the test saves a synthetic project.
It covers real side/corner-handle drags, continuous Shift-mode changes, skew/flip
matrix invariants, drag cancellation
with Undo, selection and mask helper cleanup, late outline loading, a 3,000-layer
document, and a saved-project reload. It does not interact with a running game.

The KFPS Python suite also covers editor project discovery and local server
reuse:

```powershell
.\python\python.exe -m unittest discover -s KFPS.UI\tests
```

The editor relies on the bundled Fabric.js and bundled native shape resources.
Arbitrary SVG path import is intentionally not treated as a valid game layer.

## Local Diagnostics

The Performance tab shows recent frame intervals, long tasks, layer/reference
counts, approximate JavaScript memory, recovery acknowledgments and local log
health. Hidden-window time is not counted as a visible frame stall. A missing
heartbeat or an unconfirmed write is a warning, not proof of a renderer crash.

Native logs live in `runtime/fabric-editor`: `desktop.log` contains launch and
process output, `diagnostics.json` is the current bounded snapshot, and
`performance.jsonl` plus two rotated files retain local diagnostic events.
Performance events exclude artwork, typed text and filenames. Disk writes run
on a bounded background queue, not the rendering thread.

Use KFPS's **Report a problem** button to prepare a reviewable report with this
snapshot and recent editor/worker log excerpts. Technical context can be
excluded, and nothing is uploaded until Send is pressed. Automatic redaction is
not perfect: review the excerpt for personal details. Do not share the entire
runtime folder; it also contains your projects, references and recovery copies.

Developer validation: `tests/editor-diagnostics.node.js`,
`KFPS.UI/tests/test_editor_diagnostics.py`, `test_support_logs.py`, and
`tools/support_worker/test` cover collection, bounds, failures and private
delivery. The support worker's browser/server protocol must be deployed along
with any newly supported report fields; desktop-only changes are insufficient.
