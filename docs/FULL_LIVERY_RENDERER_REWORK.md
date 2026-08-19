# FH6 Full-Livery Renderer Rework

## Goal and boundary

Render every nonempty FH6 livery available in the local save against its exact
car with correct body sides, glass sections, masks, assembly transforms, and
grounding. The isolated validation factory may render owned and unowned records
for private comparison, but the production Livery tab enumerates only locally
owned saves. Export, package sharing, and save installation remain fail-closed
for unowned sources and foreign vinyl groups.

The implementation is maintained in the main KFPS source tree. Reference
checkouts, validation outputs, and local game data remain ignored and are never
shipped. Forza Livery Studio 1.2.0 at commit
`09cf1137ac441fd38af8751a6ff64cc31308bd1b` is an AGPL-3.0 behavioral reference
under the ignored `runtime/livery-reference/` tree. No FLS source was copied
into KFPS.

## Independent renderer contract

- The C# converter assembles the complete stock car scene from the recipient's
  local FH6 archive and preserves transforms, normals, UV channels, draw groups,
  material bindings, part identity, and wheel/bumper locators.
- Exact `TEXCOORD_3` remains the preferred livery mapping. Verified paint or
  glass surfaces without UV3 may use a side-constrained world-projection path;
  unclassified geometry is never guessed into the livery route.
- Final visibility and projection fitting use separate side bitsets. Final body
  rendering is broad enough for curved multi-side panels, while projection
  bounds stay constrained by bumper, hood, skirt, wing, trunk, and window
  identity.
- The converter recognizes body paint by material semantics, window glass by
  binding and exterior identity, and direct-UV livery canvas geometry by FLS's
  panel and car-paint bindings. Interior glass, labels, lamps, tires, and
  unrelated trim remain excluded.
- The renderer grounds the scene from all four wheel locators and tire radius,
  and frames it from stable body/glass bounds rather than arbitrary optional
  geometry.
- The 11 livery sections retain independent masks, paint rectangles, facing
  vectors, projection axes, and left/right identity after the scene's X mirror.
- Mask layers subtract alpha from artwork below them. A zero-alpha native
  gradient is accepted as a no-op rather than drawn as a colored shape.

## Local corpus proof

`tools/livery/validate_local_catalog.py` inventories, deduplicates, converts,
renders, packages, reopens, and validates the complete local save corpus. Its
outputs are ignored local evidence and must not be distributed.

The 2026-08-18 corpus contains:

- 144 `C_livery` files;
- 56 byte-identical duplicates;
- 32 unique empty records, which remain hidden;
- 56 unique nonempty liveries across 46 distinct cars;
- 4 locally owned and 52 unowned records;
- 2 owned records containing foreign groups.

The v10 run at
`runtime/full-livery/validation/2026-08-18-private-preview-v10/` converted 46 of
46 cars and produced 56 of 56 private previews with zero conversion or preview
errors. The v8, v9, and v10 runs are retained as frozen comparisons.

The material audit recovered 87 direct-UV livery canvas meshes on 11 cars that
the previous name-only classifier discarded as trim. This includes doors,
fenders, hoods, trunks, bumpers, wings, mirrors, and side skirts. The cache
revision is 10 so older GLBs cannot conceal the corrected classification.

## FLS differential rendering oracle

The successful v10 corpus run proves that KFPS can decode every locally
available record, prepare every required chassis, and finish every preview. It
does not prove that the 2D livery composition exactly matches FLS. Layer order,
nested mask inheritance, native gradient alpha, raster decals, and skipped
binary records can all produce a complete but visually wrong preview.

Forza Livery Studio 1.2.0 is therefore used as a private behavioral oracle. A
diagnostic-only target in the ignored FLS checkout renders each imported
`C_livery` section through FLS's own nested scene renderer at 2048 by 1024. The
helper preserves FLS child order, mask blend mode, native per-vertex alpha, and
raster decal textures. It is not part of KFPS and is never shipped.

`tools/livery/compare_fls_renders.py` runs the same local source through that
oracle and the real KFPS decoder/section renderer. It records logical placement
counts, missing outputs, alpha intersection-over-union, orientation checks,
alpha error, visible-pixel color error, and three-panel comparison images.
Results belong under ignored `runtime/full-livery/differential/` directories.

The first owned 10,224-placement sample accounted for all placements in both
renderers. Its six populated sections selected the identity orientation over
horizontal flip, vertical flip, and 180-degree rotation. Alpha coverage IoU was
95.7 to 99.0 percent. This is a useful control, not proof of parity: the full
counterexample set below supplies the mask-heavy, partial-alpha-heavy,
raster-heavy, window-heavy, asymmetric, and physically incomplete coverage
needed before changing the production renderer.

The completed semantic-contract run is retained at
`runtime/full-livery/differential/2026-08-19-full-semantic-contract-v3/`. It
independently rebuilt all KFPS and FLS renders for 56 unique nonempty liveries,
353 populated sections, 46 cars, and 331,804 logical leaves. KFPS matched FLS
exactly on all 331,804 leaves with zero record-count or semantic mismatches. The
contract compares source order, section, native shape identity, raster identity,
mask state, BGRA color, and complete world transform; all sections also selected
the identity orientation. This is the source-of-truth gate for missing pieces,
side assignment, layer order, nested masks, fades, and group transforms.

The remaining PNG differences are raster-edge and antialiasing differences
between the two independent rasterizers. Across all 353 sections, mean checker
space error is 0.496 on a 0-255 scale. Visual inspection of the largest deltas
shows the same artwork and coverage with thin edge differences, including the
dense black-on-silver stress case. Very small or nearly transparent sections can
produce weak alpha-IoU ratios despite differing by only a few edge pixels, so
they are not used to override the exact semantic result.

The parser correction was representation-level, not car-specific: artwork
group transforms now follow FLS's strict scene grammar, while ownership/privacy
recognition remains a separate fail-closed scanner. No car IDs, livery names, or
per-car transform exceptions were introduced. Package compiler revision 9
invalidates and rebuilds cached section images made with the older grammar. The
local FLS diagnostic helper also receives its Qt plugin path from the harness,
preventing the standalone oracle's platform-plugin startup warning without
adding a Qt dependency to KFPS.

Visual browser checks compare the renderer with the save's own `bigThumb.webp`
for representative cases. The retained screenshots are under
`runtime/full-livery/validation/2026-08-18-visual-qa/`:

- `CARDBOARD TOY`: recovered missing door, fender, hood, trunk, wing, and bumper
  artwork;
- `Symboli Rudolf`, `YIXUAN`, and `Burnice ZZZ - Itasha`: overlapping livery
  panel shells render without duplicate geometry or z-fighting;
- `Annie Integra type R`: 797 mask operations subtract cleanly without colored
  mask geometry;
- `Chick Hicks`: front, side, and rear window artwork remains routed to glass;
- `InGameLogoTest` and `Sword Art Online`: left/right and rear-window routing
  remain distinct;
- all 46 converted cars contain four wheel locators and are grounded from wheel
  bottoms rather than arbitrary mesh bounds.

## Private preview and ownership safety

- The production Livery tab hides unowned records and its preview worker rejects
  an unowned source even if invoked directly.
- The ignored validation factory may create source-free private artifacts for
  corpus comparison. They contain rendered section images and metadata, not the
  source `C_livery` or canonical layers, and are never distributed.
- Shareable package creation independently rejects unowned sources, foreign
  groups, logical/physical count mismatches, incomplete raster references, and
  incomplete section decoding.
- Four unowned records have logical section counts that exceed recoverable
  physical placements. Private preview records those mismatches and renders the
  recoverable placements; export remains blocked.
- Three referenced raster IDs are absent from the local FH6 decal archive. They
  are omitted with explicit private-preview warnings and remain a hard failure
  for shareable packages.

## Remaining limits

- Base paint colors, paint materials, installed wheel/tire/brake choices, and
  exact tuning state are not part of this vinyl-render milestone. Neutral gray
  body regions and inspection wheels are expected where no vinyl covers them.
- Empty placement records stay hidden because paint-only liveries cannot yet be
  distinguished reliably from unused records.
- Validation-only private previews may show recoverable physical placements from
  malformed or partially understood unowned records. They are evidence, not
  production-visible or exportable packages.
- The local corpus proves all liveries available on this machine, not every FH6
  car and option combination in existence. New unusual glass or body-kit cases
  should be added as regression fixtures when they are observed.

## Regression requirements

Any later renderer change must preserve the frozen comparison runs, rebuild the
mesh cache under a new revision when semantics change, pass the package,
converter, decoder, and service suites, rerun the complete local corpus, and
visually recheck at least one body-panel, asymmetric-side, mask-heavy,
window-heavy, and high-suspension livery.
