# Fabric FH6 Editor

Bundled local-browser editor for creating and cleaning FH6 JSON files.

## Goal

Provide a simpler FH6 JSON editor focused on manual cleanup:

- Full FH6 shape library from `Resources/Vinyls`.
- Generated legacy JSON import is automatically converted to FH6 square/circle type-code layers.
- Handmade/exported FH6 JSON keeps its original type codes.
- Export always writes FH6 type-code JSON.
- Canvas uses FH6-style centered coordinates.

## Current Controls

- Import JSON: load generated or handmade/exported JSON.
- Export FH6 JSON: save the current layer stack.
- Save Project / Load Project: save or reopen the current editable state.
- Load Overlay: add a trace/reference image.
- Overlay opacity/size: adjust the reference image.
- Live auto color from overlay: updates selected/new shape color from the pixels under the shape.
- Mouse wheel: zoom.
- Middle/right mouse drag: pan.
- `V` / `S` / `I` / `G` / `O`: Select, Shapes, Dropper, Guides, Overlay. Ignored while typing in fields.
- Click visible pixels: select the top visible layer under the cursor.
- Drag box: select multiple layers.
- Hold `V` while dragging: force box-select even when the drag starts on a shape.
- Invert box select: select layers outside the dragged box.
- Drag selected layer/box: move.
- Side handles: resize one axis.
- Corner handles: skew by default; hold Shift for uniform/global scale.
- Delete/Backspace: delete selected layer(s).
- Ctrl+D: duplicate selected layer(s).
- Duplicate follows Place mode, so copies can be inserted above/below the selected layer or range.
- Ctrl+Z / Ctrl+Y: undo / redo.
- Arrow keys: nudge selected layer(s).
- Shift+Arrow keys: larger nudge.
- `[` / `]`: move selected layer(s) backward/forward in layer order.
- Click a shape tile: place that shape in the current viewport center.
- Place mode: add at top, insert above/below selection, or replace selected layer shape type.
- Reuse last font size: keep repeated font characters consistent.
- Click the star corner on a shape tile: add/remove favorite.
- Search: filter shapes by name, family, index, or type code.
- Gradient Shapes render with their bundled fade masks in the editor preview.
- Multi-select color edit: apply color/alpha to all selected unlocked layers.
- Enter in transform fields: apply typed values.
- Tool options bar: keeps shape placement mode, active color, duplicate/delete/group/fit, and export readiness visible above the canvas.
- Selected-shape halo/frame: editor-only visibility helper for same-color neighboring shapes.

## 3,000-Layer Architecture

- Vinyl layers are indexed independently from guides and editor-only helpers.
- Resource fetches and Fabric object construction use bounded concurrency while preserving stack order.
- The layer browser keeps the complete searchable model but mounts only the visible rows.
- Undo/redo structurally shares unchanged shapes and restores changed objects in place.
- Autosave is deferred and serializes only the newest state after bursts of edits.
- Designs with at least 300 layers use a transient WebGL interaction preview for pan, zoom, and transforms. Fabric resumes after the interaction for the exact final render.
- FH6's 3,000 editable-layer maximum is enforced for imports, duplication, and built-in generators.

Developer checks live in `tools/fabric-editor/tests`. Run the dependency-free core test with:

```powershell
node tools/fabric-editor/tests/editor-core.node.js
```

## Known Limits

- This does not yet have a polished FH6-specific transform gizmo.
- Arbitrary SVG import is intentionally not supported.
- The editor relies on bundled Fabric.js.
- Autosave keeps a temporary recovery copy in browser storage and, when launched through KFPS, in `runtime/fabric-editor/autosave.json`. It remains separate from explicit project saves.
