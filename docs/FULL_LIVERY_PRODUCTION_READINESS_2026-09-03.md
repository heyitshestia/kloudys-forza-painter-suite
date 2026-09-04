# FH6 Full-Livery Production Readiness Record

Date: 2026-09-03

Workspace: `KFPS DIRTY` only

Status: production candidate, still behind the existing experimental release
gate

## Scope

This pass targets exact-car FH6 livery inspection, package export, package
validation, and same-car save installation. It does not enable cross-car or
cross-game application, expose unowned liveries in the product, decode base
paint or tuning state, or change the live-memory vinyl-group pipeline.

The implementation was compared against fresh, read-only reference checkouts:

- Forza Livery Studio commit
  `70429375159a1c2f052bc91c29c9e1c4eb1d27fd` for livery parsing and 2D section
  rendering behavior;
- ForzaTechStudio commit
  `4f373c5fb192551ce5249e320dd79b1399b693ca` for the already-vendored model
  decoder lineage.

No reference source or assets were copied into KFPS. The temporary comparison
build and all game-derived validation output remain ignored and are not shipped.

## Changes

### Livery decoder

- Handles generation-1, generation-2, and current FH record markers explicitly.
- Handles markerless roots and child groups, wide and compact group headers,
  mirrored transform trailers, group masks, and nested transform propagation.
- Keeps generation-2 framing flags separate from current trailing-mask flags.
- Canonicalizes the two known FH wire aliases, `0x07D0` to `0x07D1` and
  `0x0BB8` to `0x0BB9`, before shape validation.
- Deduplicates repeated ambiguous shape-identity warnings without hiding which
  resource candidates were found.

### Chassis and projection

- Reads exact world-space position, normal, and index data for the small number
  of validated paint/glass meshes that lack `TEXCOORD_3`.
- Fits each projected section against the exact local `Masks.xml` coverage with
  facing-side filtering, bounded scale/offset search, and wheel/bumper anchors.
- Accepts a fitted projection only when its boundary cost improves by at least
  0.05. Otherwise it keeps the deterministic unadjusted projection.
- Stores final projection bounds in render-contract revision 9. The browser does
  not perform fitting or scan mesh bounds every animation frame.

### Browser renderer

- Requires mask coverage above 50 percent before applying a section.
- Uses strongest coverage for direct UV and best facing direction for projected
  geometry, preventing cross-side and overlapping-window bleed.
- Frames the complete stable chassis for the current aspect ratio on desktop
  and mobile. Resize preserves a user-modified camera.
- Retains explicit disposal of geometry, materials, textures, skeletons,
  animation callbacks, and the WebGL context.

### Package and diagnostics

- Package compiler revision 11 forces old derived section data to be rebuilt
  from the exact preserved source before use.
- Source-index revision 2 decodes every visible owned source before presenting
  it as exportable. Foreign-group ownership failures and incomplete source data
  are counted and explained separately; neither can be mislabeled as ready.
- The catalog validator records decoded count, completeness, and per-section
  count mismatches in addition to conversion/render failures.
- The differential runner is resumable, fingerprints its inputs, isolates every
  record failure, records the failed phase and tool output, and exits nonzero
  when any record fails or is intrinsically incomplete.

## Automated and corpus evidence

| Gate | Result |
| --- | --- |
| Saved files inventoried | 77 |
| Duplicate files removed from comparison | 1 |
| Empty records excluded | 17 |
| Unique nonempty records | 59 |
| Distinct exact-car chassis | 47 |
| Chassis conversions | 47 passed, 0 failed |
| Private render contracts | 58 passed, 1 unsupported custom record |
| Owned sharing candidates | 5 passed privacy, 4 complete exports, 1 incomplete source rejected |
| Full KFPS automated suite | 582 passed, 0 failed, 0 skipped |
| Recoverable logical leaves | 333,071 |
| Populated 2D sections compared | 359 |
| Semantic differences | 0 |
| Wrong side/orientation selections | 0 |
| Mean checker-space pixel error | 0.501 / 255 |
| Mean alpha intersection-over-union | 94.57 percent |

Low alpha-overlap outliers are sections containing only a few nearly invisible
edge pixels. The complete semantic comparison and visual difference sheets show
the same artwork, side, order, masks, transforms, and colors. The largest pixel
deltas are antialiasing differences around very dense edges, not missing or
reordered shapes.

Two save records are incomplete at source level:

- `Kiss Shot Integra` declares 8,029 placements; both current parsers recover
  6,130. KFPS may render the recoverable private preview but refuses a shareable
  export.
- The 39-placement GR86 custom-mesh experiment recovers no standard FH6 shapes
after the modified archive is removed. It is rejected and is not treated as a
normal livery regression.

The real product source index was also run cold and warm against all 77 files.
Both runs exposed six owned records: four exportable, one blocked by a foreign
group, and one blocked as incomplete. The warm run reused all 77 indexed file
identities while producing the same decisions.

The real package path was also exercised against an isolated copy of a save:

- an owned 10-placement package was created and fully validated;
- installation added one new exact-car folder without modifying existing files;
- reopening produced identical artwork, placement count, and payload size;
- the installed record passed the ownership check;
- an unowned source was rejected for sharing;
- its local comparison preview contained no source record or canonical layers.

## Browser lifecycle evidence

The actual Three.js viewer was run headlessly at 1440x900 and 390x844. The car
remained fully framed and controls did not overlap it. A 500-filter-switch burst,
more than 1,000 auto-rotate frames, and eight complete reloads left the tracked
resource inventory unchanged. Explicit disposal reduced tracked geometry,
materials, textures, and skeletons to zero and released the WebGL context.

## Remaining release gate

This pass is a production candidate, not universal hardware proof. Before the
experimental stage can be marked stable, community validation still needs:

- both Microsoft Store/Xbox and Steam FH6 installations;
- repeated switching on AMD, NVIDIA, and Intel graphics;
- varied install and save locations;
- unusual body kits, active aero, split glass, and all-section liveries;
- real in-game load of an installed package after restart;
- interrupted conversion, forced viewer termination, and recovery diagnostics
  from machines other than the development system.

Any failure should include the Full Livery Diagnostics ZIP and the selected
record title/car ID. The per-operation session identifies whether failure was in
save decoding, ownership, vehicle indexing, chassis conversion, section render,
browser startup, package validation, or save commit.

## Engineering lookback

1. The work remains scoped to accurate exact-car FH6 viewing, export, and
   same-car installation; live-memory vinyl groups and cross-car conversion are
   unchanged.
2. The current reference implementations, prior KFPS experiments, saved corpus,
   package tests, and existing lifecycle isolation were all used before adding
   new behavior.
3. The two remaining corpus failures are source-representation limits, not
   tuning, chassis conversion, projection, or browser lifecycle failures.
4. Improvements are measured on complete leaf semantics, every populated
   section, visual differences, package round trips, cache behavior, and resource
   disposal rather than only successful command exits.
5. Added complexity is bounded to a versioned projection fitter, explicit parser
   dialects, and versioned package/render/index contracts. No car-specific fixes
   or silent compatibility exceptions were added.
6. This does not repeat the retired custom-mesh path. The product continues to
   use native FH6 shapes and exact local chassis assets.
7. The assumptions that every paint surface has direct UV3 data and that declared
   counts alone prove exportability are now known to be false and are enforced in
   code and tests.
8. Embedding game-derived chassis assets or accepting partial share packages was
   rejected because either option weakens portability, licensing, or data
   integrity.
9. The implementation should continue as a production candidate behind the
   existing release gate until the external hardware, store, and restart matrix
   above is completed.
