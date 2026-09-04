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
shipped. The current Forza Livery Studio checkout at commit
`70429375159a1c2f052bc91c29c9e1c4eb1d27fd` is an AGPL-3.0 behavioral reference
used only from a temporary build. No FLS source was copied into KFPS. The latest
evidence and remaining release gate are recorded in
[`FULL_LIVERY_PRODUCTION_READINESS_2026-09-03.md`](FULL_LIVERY_PRODUCTION_READINESS_2026-09-03.md).

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

The 2026-09-03 corpus contains 77 files, one byte-identical duplicate, 17 empty
records, and 59 unique nonempty records across 47 exact-car chassis. Six records
are locally owned, 53 are unowned, and seven contain foreign groups. Five pass
the privacy prefilter; four pass complete package export, while one unsupported
custom-shape experiment is rejected for incomplete source data. All 47 chassis
converted successfully. Fifty-eight
records built usable private render contracts; the remaining 39-placement GR86
record came from the retired custom-mesh experiment and contains no standard
shapes after the modified game archive is removed.

## Differential rendering oracle

A diagnostic-only helper built against the current reference checkout renders
each `C_livery` section through its native nested scene renderer at 2048 by 1024.
It preserves child order, mask blend mode, native per-vertex alpha, raster decal
textures, and complete world transforms. The helper is not part of KFPS and is
never shipped.

`tools/livery/compare_fls_renders.py` runs the same source through that helper
and the real KFPS decoder/section renderer. It records input hashes, logical
placement counts, exact leaf semantics, missing outputs, alpha overlap,
orientation checks, color/alpha error, and three-panel comparison images. A
timeout or failure is isolated to its record and does not discard a long run.

The current run covers 59 records, 333,071 recoverable leaves, and 359 populated
sections. KFPS has zero count or semantic differences and every section selects
the identity orientation. Mean checker-space error is 0.501 on a 0-255 scale.
Visual inspection of the largest deltas shows matching artwork with raster-edge
and antialiasing differences. Very small, nearly transparent sections can have
low alpha-overlap ratios while differing by only a few faint edge pixels, so
that metric never overrides exact semantic evidence.

The parser corrections are representation-level, not car-specific. No car IDs,
livery names, or per-car transform exceptions were introduced. Package compiler
revision 11 invalidates and rebuilds derived sections made with the old grammar.

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
- Two records have logical section counts that exceed recoverable standard
  placements. Private preview records those mismatches and renders recoverable
  placements where any exist; export remains blocked.
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
