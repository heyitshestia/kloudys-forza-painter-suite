# Livery Viewer Vinyl Resolution

The read-only 3D viewers in Liveries and Community offer the same two levels:

| Level | Vector sampling | Compared with the previous viewer |
| --- | --- | --- |
| Standard | 2x native section coordinates | Previous High |
| High | 4x native section coordinates | Twice the width and height of previous High |

This changes preview detail only. Native game data, package contents, shape
counts, placement, UV mapping, masks, and export behavior do not change.
Studio's independent authoring preview modes are unchanged.

## Using It

Open a livery's 3D preview and select Standard or High in its header. Changing
resolution replaces the preview session and rebuilds or reuses its derived paint
textures. It does not save or modify the livery. Standard is the default.

The Liveries preference persists across restarts. Community's isolated previews
inherit that preference when opened; a selection made in the Community dialog
applies to that temporary preview. Neither viewer scans saves on behalf of a
Community preview.

The new `viewer_vinyl_quality` preference uses `standard` / `high`. Legacy
`viewer_quality` is preserved for rollback, but never interpreted as a request
for the new 4x mode. Existing High users therefore stay at the same sampling
level as before. No manual file conversion or settings cleanup is needed.

## Rendering And Limits

- Supported vector layers are rerendered, not enlarged from the saved PNG.
- Rectangular and square native-mask layouts use the same car-specific affine
  placement. Mask images and UV coordinates keep their original dimensions.
- Packed atlas dimensions include fixed gutters, so the overall atlas height
  need not double exactly. Each rerendered section's dimensions do double.
- Sources that are not available or permitted to rerender retain their original
  section images. The viewer reports original or mixed resolution; it does not
  fabricate detail or bypass ownership restrictions.
- High falls back to Standard below 8 GiB available RAM. Below 2 GiB, saved
  original resolution is used. Diagnostics report the actual rendered level.
- Atlas size, worker memory, graphics memory and maximum GPU texture dimensions
  remain bounded. An unsupported High preview can be retried at Standard.
- Quality-specific cache identities prevent reuse of the wrong resolution.

## Validation

DIRTY validation on 2026-10-26:

- 277 regression tests passed, including unchanged Studio quality modes and
  upload compatibility, plus new resolution, preference and lifecycle coverage.
- Real Qt controls exercised offscreen in both panels at 1280x800 and 800x600
  across Night Blossom, Carbon Dark, Original Xbox, Original PS2 and NieR Automata.
- A real 14,125-layer, nine-section package was prepared at both levels and
  reopened through the shared read-only server in headless Chrome/SwiftShader.
- Actual section dimensions doubled; source regions, UVs and masks matched.
  Four screenshots passed nonblank pixel checks. The source package was unchanged.
- Square-mask behavior has synthetic real-vector pixel coverage, not a newly
  rendered real square-mask vehicle. Tests do not qualify every car, GPU, display
  scale, or hardware-accelerated Qt WebEngine driver.

Private logs, source-package checks and screenshots are under the ignored
`runtime/test-runs/viewer-resolution-20261026/` directory. No publication or live
Community upload was performed during these checks.
