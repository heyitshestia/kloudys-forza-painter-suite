# C_group Import/Export Integration Plan

This plan is for a clean-room KFPS integration inspired by public behavior and
format observations from ForzaLiveryStudio. Do not copy AGPL source code or
assets into KFPS unless the project intentionally accepts the licensing impact.

## Goal

Make shape identity and import/export behavior deterministic by using the
Forza `C_group` vinyl payload as the file-format ground truth.

The current live path writes and reads memory layer records. That is still
useful, but it is fragile because live shape resources, editor templates, RTTI
locator state, and preview mappings can disagree. A direct `C_group` path gives
us stable fixtures and, eventually, a safer file-export option from the editor.

## Current KFPS Paths

- UI transfer bridge:
  - `KFPS.UI/bridges/transfer_bridge.py`
  - Calls `fh6_import_typecode_json.py`, `fh6_export_typecode_json.py`,
    `fh6_probe.py`, and `fh6_trim_group_count.py`.
- Live export schema:
  - `fh6_export_typecode_json.py` emits `{"shapes": [...]}`.
  - Each layer stores `type`, `type_word`, `data`, `color`, and `mask`.
  - `data` is `[x, y, sx, sy, rotation, skew, maskFlag]`.
- Live import schema:
  - `fh6_import_typecode_json.py` expects the same shape data.
  - It writes memory offsets for transform, color, mask, and shape word.
- Editor schema:
  - `tools/fabric-editor/editor.js` keeps both visual resource identity
    (`resource_family`, `resource_index`) and game identity (`type_word`).
  - The visual mesh and the game word must be resolved through one canonical
    identity layer before export.
- Preview schema:
  - `json_preview_renderer.py` resolves resources for thumbnail rendering.
  - This must not become the canonical truth for the in-game shape ID.

## Important Identity Rule

There are two different concepts that must not be mixed:

- Visual resource: the editor mesh/thumbnail path, such as
  `Community_Vinyls_2/19`.
- Game shape ID: the 16-bit shape word written into game memory or the
  `C_group` payload, such as `2223`.

For finished behavior, the canonical direction should be:

```text
resource_family + resource_index
        -> canonical game shape word
        -> JSON type/type_word
        -> live memory write or C_group export
```

When JSON only contains `type_word`, the renderer can infer a visual resource.
When JSON contains both, conflicts must be reported instead of silently choosing
whichever mapping happens to render.

## C_group Flat Payload Model

The prototype implements only the flat path first.

Container:

```text
u32 compressed_length
u32 decompressed_length
zlib-compressed payload
```

Payload:

```text
"gyvl"
u32 version = 1
u32 unknown = 0
root transform marker and identity transform
root group marker
root direct child count
root child bitmap/control bytes
flat shape records
terminator
```

Flat shape record:

```text
u8 marker flag
u8 shape marker = 0x02
u16 shape_id
f32 rotation
f32 x
f32 y
f32 scale_x
f32 scale_y
f32 skew
u8 blue
u8 green
u8 red
u8 alpha
```

KFPS JSON stores colors as RGBA, so the prototype writes BGRA into `C_group`.

## Implementation Phases

### Phase 1: Isolated Prototype

Status: implemented in this clone under `tools/cgroup`.

- Add `shape_identity.py`.
- Add `cgroup_codec.py`.
- Add `export_kfps_json_to_cgroup.py`.
- Add `audit_shape_identity.py`.
- Do not modify default UI, live importer, live exporter, or updater.

### Phase 1B: Export-Only Real File Prototype

Status: implemented in this clone under `tools/cgroup`.

- Add `forza_source_decoder.py`.
- Add `export_forza_source_to_kfps_json.py`.
- Add `find_forza_sources.py`.
- Accept a direct `C_group`/`C_livery` file or a folder containing one.
- Inflate the Forza zlib container.
- Decode standalone `C_group` into flattened KFPS JSON.
- Decode `C_livery` section scaffolding and empty/non-empty section counts.
- Keep a privacy guard enabled by default for known locked payload markers.
- Write a decode report next to the exported JSON.

Validation performed:

- Synthetic flat `C_group` exported from `assets/app/KFPS Logo.json` decodes
  back to 319 layers with zero shape-word mismatches.
- Windows bundled Python can run the exporter.
- Windows save-root scan finds real `C_group`/`C_livery` artifacts under
  `C:\XboxGames\GameSave`.
- A real 65-layer `C_group` calibration artifact exported successfully to KFPS
  JSON. Its community-shape words differ from the old assumed contiguous table,
  which confirms why game/save-file truth is needed.
- Two tested `C_livery` files decoded as valid but empty, with all section
  counts at zero.

Current limits:

- The file path is still a command-line prototype only.
- It does not write back into the game.
- It does not replace the current live memory importer/exporter.
- Populated `C_livery` decoding still needs validation against a known non-empty
  livery.
- Nested/grouped `C_group` files need more comparison fixtures before UI
  integration.

Validation:

- Export `assets/app/KFPS Logo.json` to a flat `C_group`.
- Read the generated `C_group` back and verify layer count and shape IDs.
- Run identity audit and list any resource/type-word conflicts.

### Phase 2: Canonical Shape Fixtures

Create fixture JSONs from known, manually verified shape sets:

- 40 primitives in order.
- 40 gradients in order.
- 40 entries for each non-letter tab.
- All 520 non-letter shapes.
- Community gradient tabs.
- Negative scale, skew, rotation, alpha, and mask samples.

For each fixture:

1. Render KFPS JSON preview.
2. Export flat `C_group`.
3. Parse the `C_group` back.
4. Confirm shape IDs match the canonical table.
5. Load/import in game if available.
6. Export live memory JSON.
7. Compare live JSON against the original fixture.

### Phase 3: Live Export Hardening

Use `C_group` fixtures as ground truth for live export.

- Run a known fixture in game.
- Export with KFPS live exporter.
- Compare `type_word`, transform, color, alpha, mask, and ordering.
- If preview differs from game but `C_group` and live export agree, fix the
  preview renderer.
- If live export differs from `C_group`, fix memory offsets or group flattening.
- If imported game state differs after save/reload, fix live import write logic.

### Phase 4: Editor File Export

Add an optional editor export mode:

```text
Editor JSON -> canonical shape IDs -> flat C_group export folder
```

This should be separate from the current JSON export until validated.

Benefits:

- No 3000-circle template dependency for this file path.
- No live resource-cache issue for editor-created vinyls.
- Better debug artifacts because the exported file contains the actual game
  shape IDs.

### Phase 5: Nested Groups

Add nested export only after flat export is proven.

Rules to preserve:

- Internal editor groups can remain editor-only for JSON.
- If exporting real game groups, group transforms must be converted into child
  local transforms or proper nested `C_group` nodes.
- Mask behavior must be revalidated before public release.

### Phase 6: UI Integration

Expose only after tests pass:

- "Export Forza C_group Folder" in the editor.
- "Audit JSON Shape IDs" in development/debug tools.
- Keep the live importer/exporter as-is until the C_group path has passed game
  validation.

Prototype update, 2026-07-07:

- Added a local-only "Forza save library" card to the Outputs page.
- One click scans known Forza save folders only, not Downloads/Desktop.
- Valid unguarded `LayerGroup_*/C_group` artifacts are decoded into
  `imgs/exported/cgroup-library/<entry>/`.
- Each entry writes a KFPS JSON, decode report, manifest, and `.preview.png`.
- The existing Exported JSON browser is refreshed after export so the library
  entries are immediately selectable for preview/import testing.
- The raw game save artifact is not copied into the app folder; the library is
  JSON/report/preview only for now.
- `BaseLivery_*` and `C_livery` containers are intentionally ignored by the
  library scanner because they are not individual layer-group exports.
- The scanner reads the sibling `header` file for display metadata when present,
  so the browser can show the vinyl/group title and shape count instead of a
  long save-folder/hash string.
- Save-root discovery now checks cached roots first, then looks for
  `XboxGames/GameSave` on every mounted drive and near the top of each drive.
  The roots that actually contain `LayerGroup_*/C_group` files are saved to
  game-specific cache files such as `runtime/cgroup-library-roots-fh6.json` for
  faster later scans.

Prototype update, 2026-07-07B:

- The save-library scan is now bound to the Outputs target game dropdown.
- FH6, FH5, and FM8 library entries are written into separate folders under
  `imgs/exported/cgroup-library/<game>/`.
- Manual CGroup export and finder commands now accept `--game fh6|fh5|fm|fm8`.
- FM8 file exports run through an exact FM8-to-FH6 shape-word normalization
  table before writing KFPS JSON, while preserving the raw FM8 type word in
  `source_raw_type_word`.
- FH6/FH5 decoding remains unchanged and still uses the normal shape-word
  lookup.

Prototype update, 2026-07-07C:

- Added an FH6-only folder-install prototype.
- The installer does not write live memory.
- Replacement mode requires the user to choose an existing disposable
  `ContainersRoot/LayerGroup_*/` folder that already contains `C_group`.
- New-folder mode creates `LayerGroup_0000_<timestamp>/` inside the newest FH6
  `ContainersRoot` discovered from existing saves.
- Before writing, the selected folder is copied to
  `runtime/cgroup-folder-import-backups/`.
- The selected KFPS JSON is encoded into a flat `C_group`, the existing `header`
  is renamed or rebuilt as a draft header, and `thumb.webp` is refreshed when
  preview rendering succeeds.
- Folder-import thumbnails are rendered with transparent preview backgrounds
  and saved as RGBA WebP. FH6 may still flatten alpha when displaying the
  thumbnail; this requires in-game confirmation.
- Users should leave the in-game editor or close/reopen FH6 before checking the
  result. Writing into a LayerGroup that FH6 currently has open is not a safe
  public workflow.
- This path is intentionally separate from normal live-memory import until the
  game reload behavior is validated with small, 520-shape, and generated
  fixtures.

## Risks

- AGPL reference repo cannot be copied directly.
- `C_group` file placement/import workflow still needs game validation.
- Color byte order must be verified in game.
- Mask trailing-flag behavior needs dedicated tests.
- Nested groups should not be attempted until flat shape identity is stable.

## Success Criteria

- KFPS JSON exported to flat `C_group` parses back with the same count.
- Shape IDs are exact for primitives, gradients, community tabs, and the 520
  shape fixture.
- Editor preview, JSON, generated `C_group`, live export, and saved/reloaded
  game state all agree for the same fixture.
- The old live memory path remains unchanged until the new path is proven.
