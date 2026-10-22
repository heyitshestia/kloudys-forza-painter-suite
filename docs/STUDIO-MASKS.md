# Studio Masks

Implemented in 3.1.114.

## Using Masks

Import a vinyl containing native mask shapes and place it on the car as usual.
A mask cuts through artwork drawn earlier on that same section, including other
vinyl placements, and reveals the car paint. Shapes drawn later can cover that
area again. Moving or reordering a masked vinyl changes which earlier artwork it
cuts through. Other sections and hidden placements are unaffected.

Section export preserves the mask flags and keeps each placed vinyl together.
No overlap restriction, raster baking or replacement geometry is applied.
Mask-only vinyls remain selectable. Fast, Balanced and Sharp preview settings
retain their existing resolutions; saved shape coordinates do not change.

Masked placements currently require 100% placement opacity for export. The
separate restrictions on clipped source geometry, unsupported raster decals and
complete-car component overrides remain in place.

## Implementation

Ordinary sources retain the existing single-image drawing path. A masked source
caches its colour image and a coverage image. Each placement erases by coverage,
then adds premultiplied colour: `C + (1 - coverage) * previous section`. This
preserves ordered cutouts, gradient coverage and paint following a mask without
rerendering the source vectors during dragging.

Coverage bounds keep mask-only sources selectable. The additional images count
toward steady and staged memory limits and are released on failed loading,
replacement, quality changes and disposal. The project format, theme format and
OpenGL/Direct3D policy are unchanged.

Experimental complete-car candidates use counted placement groups with native
mask subgroups on masked sections. Unmasked sections retain the prior writer
path. These candidate files remain explicitly marked as experimental and are
never installed automatically.

## Validation And Limits

The focused suite covers all eleven sections, mask-only and terminal masks,
consecutive masks, native bitmap boundaries through 3,000 shapes, eighty seeded
affine cases, strict byte traversal, HTTP export, ZIP/header reopening and source
preservation. Standalone vinyl codecs are checked for FH4, FH5, FH6 and FM8;
codec success is not a claim of new in-game acceptance for those games.

The installed Chrome workflow passed exact pixel comparisons, real car-atlas
checks, all preview qualities, masked movement, undo/redo and managed project
save/reopen. The native Direct3D 11 host passed the core pixel/atlas, quality,
section-export and dense-edit checks. An extended native save/reopen repeat was
stopped by the system GPU-load guard and is not counted as a pass.

Complete-car mask output still requires an in-game load/save/restart/reopen
round trip. Previously verified section-vinyl alignment and ungrouping do not
certify that separate full-design format. Exact per-car surface permissions and
layer limits are also not established by these tests.
