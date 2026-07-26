# KFPS Vinyl Editor

The KFPS Vinyl Editor is the bundled local browser workspace for creating,
tracing, repairing, and organizing FH-compatible vinyl JSON. It uses native
Forza shape resources and enforces the 3,000-layer game budget.

The editor runs entirely on the local machine. The small local server exists so
the browser can load bundled shape assets and save projects back into the KFPS
folder. It does not upload artwork. The server exposes only editor assets and
rejects mutation requests that did not originate from the editor page.

## Open The Editor

Use the `Editor` page in KFPS:

- `New Canvas` opens a blank editor.
- `Import JSON` opens the editor's JSON browser.
- Select a saved project and choose `Open Project` to continue it.
- `Tutorial` resets the first-run guide and opens the editor.
- `Folder` opens the internal project folder.

KFPS reuses one editor server while the app is running instead of starting a
new server for every click. Launch errors and the server log are available from
the native Editor page and Settings.

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

The project title shows `Saved` or `Unsaved`. Closing a tab with unsaved edits
triggers the browser's normal leave-page warning. Opening another document from
inside the editor also asks before replacing unsaved work. Recovery is a safety
net, not a replacement for `Save`.

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
- Side handles: resize one axis.
- Corner handles: skew.
- Shift with a corner handle: uniform scale.
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

Reference images are tracing helpers. They can be moved, scaled, faded, sampled,
and saved with an editable project, but never become exported vinyl layers.

## History And Recovery

History records meaningful editing states, shows the active state, and marks the
last explicit save. Click a history entry to jump to it. The loaded source is a
protected boundary so an accidental Undo cannot erase the entire imported
design.

The recovery copy updates after edits and reference changes. On the next start,
the editor offers to restore it when appropriate. Saving a project clears the
temporary recovery copy.

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

## Large Designs

For dense projects, the editor:

- indexes vinyl layers separately from guides and helpers
- constructs shape assets with bounded concurrency while preserving order
- virtualizes the layer list
- shares unchanged history state and restores changed objects in place
- defers recovery serialization during edit bursts
- uses a transient accelerated interaction preview from 300 layers upward
- resumes the exact Fabric render when interaction ends

The hard limit for import, duplication, text, pixel-art conversion, and export is
3,000 editable vinyl layers.

## Troubleshooting

- If the editor does not open, read the status on the KFPS Editor page.
- Check `runtime/fabric-editor/server.log` for server startup errors.
- Use Settings > `Reset Editor Tutorial` to show the first-run guide again.
- If the panels are hidden, use `View > Panels`.
- If a project is missing, choose `Folder` and confirm it ends in
  `.fabric-project.json`, then refresh the native Editor page.
- If export is blocked, open `Export Check`; it lists the exact layers involved.
- If the browser closed unexpectedly, reopen the editor and restore the offered
  recovery copy.

## Developer Checks

The dependency-free geometry and ordering tests live in
`tools/fabric-editor/tests`:

```powershell
node tools/fabric-editor/tests/editor-core.node.js
node tools/fabric-editor/tests/editor-shell.node.js
```

The KFPS Python suite also covers editor project discovery and local server
reuse:

```powershell
.\python\python.exe -m unittest discover -s KFPS.UI\tests
```

The editor relies on the bundled Fabric.js and bundled native shape resources.
Arbitrary SVG path import is intentionally not treated as a valid game layer.
