# FH6 Full-Livery Portability Validation

## Record-Aware Ownership Follow-up (3.1.96)

The 3.1.95 fix below missed short-marker transforms. Privacy inspection now
collects candidate protected wrappers independently, then uses the existing
artwork walker's selected record boundaries to exclude numeric interiors. This
covers short, repeated and extended markers, inline and markerless transforms,
optional scale fields, and shape/raster payloads. Actual trailer/header bytes
remain eligible for protection checks. Incomplete or unrecognized sections and
parser failures do not clear suspicious candidates. A complete decode alone is
not an ownership verdict. No scale-specific or source-specific exceptions exist.

Source-index revision 4 and source-preview revision 5 rebuild stale verdicts.
The package format and artwork-decoding decisions are unchanged.

Qualification used 80 distinct real payloads, including both reported cases and
local owned/unowned sources with up to 12,504 decoded placements. All decoded
artwork hashes and warnings matched the frozen 3.1.95 baseline. The production
worker completed 95 operations: eight eligible sources exported and reopened,
59 unowned sources and one genuinely protected source stayed blocked, and one
pre-existing incomplete owned source remained rejected. Eleven empty sources
stayed hidden. All 52 exported section renders were pixel-identical to baseline;
226 original input files were hash-verified unchanged. Old scan/preview caches
were replaced and subsequent requests reused the corrected caches.

The final livery regression run passed 174 tests, with another 53 shared-decoder
and cross-game tests passing. One five-second UI-worker timeout occurred during
concurrent qualification; its isolated and full-suite reruns passed without a
product change. The pre-existing Qt shutdown ResourceWarning remains.

Seven-repeat median privacy-check times were 89/114 ms for the reported sources
and 287 ms for a 10,368-placement protected source. Candidate-free examples were
faster than baseline. This is a bounded scan/export-time correctness cost, not a
render-loop change or a claim that every game save format is now understood.
Qualification did not launch FH6, install packages, or change live saves.

## Ownership Boundary Regression (3.1.95)

Privacy inspection must not reinterpret numeric fields inside a validated
extended livery transform as protected-group trailers. Those fields are skipped,
but the following trailer and group are still inspected. Genuine compact, wide,
mirrored and nested protected wrappers retain their existing restrictions.

Regression coverage includes scale-byte collisions, protected groups after normal
records, unowned sources, truncated input and stale scan/preview cache refresh.
Source-index revision 3 and source-preview revision 4 invalidate earlier cached
verdicts. The package format and placement decoder are unchanged.

A private 3,188-placement reference passed the scan, local-preview, export and
fresh-process package-reopen workflow. All nine populated section renders matched
the baseline pixels, and the packaged source/header bytes were unchanged. Original
save files and private fixture data are not part of the repository. These checks
validate the export workflow, not a new in-game import or visual game comparison.

## Scope

This milestone makes the existing FH6 full-livery viewer distributable without
Blender, a local development checkout, or per-car meshes bundled with KFPS.
Shared `.kfpslivery` files contain the source livery, canonical placements, and
2D section renders. The recipient's own FH6 installation supplies the matching
neutral chassis geometry and livery UV maps.

Base-paint colors, paint materials, finishes, tint, paint-only records,
cross-car application, and cross-game recompilation are outside this milestone.

## Reference validation

The first portability proof compared two user-verified cars against the
established development renderer. That established vertex transforms, winding,
UV channel handling, and section projection. The product converter now follows
the complete car scene description instead of extracting one model in isolation,
so it also assembles stock panels, glass, wings, and other positioned chassis
parts.

The two frozen assembly regression contracts are:

| Car | Meshes | Paint meshes | Glass meshes | Triangles | Local GLB |
| --- | ---: | ---: | ---: | ---: | ---: |
| ALF_00_SE048SP_90 | 683 | 14 | 22 | 698,940 | 34.42 MiB |
| nis_gtrlm_95 | 746 | 46 | 51 | 432,488 | 20.58 MiB |

The complete renderer was then exercised on 14 additional cars spanning coupes,
sedans, hatchbacks, a pickup, a classic sports car, wide-body cars, large wings,
split panels, body artwork, and window artwork. Every chassis converted without
an unresolved scene instance. All 14 revision-5 section contracts rebuilt, and
each default/opposite-side pair rendered coherently with normally readable text.
The tested liveries range from 4,562 to 12,504 placements and use 4 to 10 populated
projection sections.

## Package validation

- Package IDs are canonical UUIDs and never become filesystem paths.
- Every canonical placement is independently decoded from the preserved
  `C_livery` and compared exactly.
- Every populated section must have one readable 2048x1024 render.
- Section previews can be independently regenerated and compared pixel-for-pixel,
  independent of PNG encoder compression differences.
- Current packages reject embedded chassis meshes and resolve them locally.
- Older revisions rebuild atomically from their embedded source when opened.
- Foreign artwork remains preview-only and cannot enter an export package.

## Same-car save installation validation

- Installation requires the package car ID and model code to match the local
  FH6 asset index exactly.
- The original installer borrowed metadata from the exact-car source header.
  As of the 2026-09-20 DIRTY fix, that header is only a car/count consistency
  check. The destination gets a newly generated type-3 saved header, verified
  recipient identity, and fresh GUID, without copied online/base metadata.
- The source and rewritten payloads decode to identical artwork and warnings.
- The destination is hash-inventoried before staging. A concurrent change aborts
  the transaction before commit.
- The installer creates a unique new folder and has no overwrite path.
- A post-commit reopen verifies the header, placement count, ownership policy,
  decoded artwork, source bytes, and thumbnail. Failure removes the new folder.
- A realistic proof copied a 645-file, 42.3 MiB FH6 `ContainersRoot`, installed a
  real 10-placement package, preserved all 645 existing file hashes, added only
  `C_livery`, `header`, and `bigThumb.webp`, and left the live save's complete
  hash inventory unchanged.
- The 2026-09-20 isolated-worker check installed a real 2,559-placement package
  twice into a 714-file save copy, plus an 8,793-placement synthetic package
  into a vinyl-only account. Existing and live file hashes remained unchanged.
  The account and header regressions are in
  `KFPS.UI/tests/test_fh6_livery_identity.py`. This is save-file validation;
  the affected user's package still needs an in-game retry.

## Chassis validation

- The helper is a self-contained Windows x64 executable.
- Only the highest-detail model level is retained.
- Per-mesh position, bone, UV scale/offset, V orientation, handedness, and winding
  transforms match the reference path.
- Degenerate and duplicate faces are removed deterministically.
- Paint and glass livery surfaces require `TEXCOORD_3`.
- The portable GLB conversion reflects the game's X axis. Body-side and
  side-window artwork therefore use the matching portable mask slot and the
  reflected mesh-facing direction as one contract. This keeps both kinds of
  artwork on the intended physical side without mirroring readable text.
- GLB headers, chunks, buffers, views, accessors, bounds, roles, vertex counts,
  index ranges, and triangle lists are validated before a cache file is used.
- Obsolete conversion processes are terminated when selection changes.
- Invalid cached chassis files are deleted and rebuilt from the local game.

The side-routing correction was checked in a 14-car, 28-view offscreen batch.
Every default/opposite pair retained its body artwork; cars with populated side
windows retained their window artwork. An asymmetric Nissan comparison was also
rendered with both candidate transforms: native destination transforms kept its
side labels readable, while the rejected preserved-source transform visibly
mirrored them. Render-contract revision 5 invalidates older cached atlases so the
corrected body and window routing is rebuilt automatically.

## Comparison mode

The local DIRTY validation instance can expose additional records as private
comparison previews through a runtime-only marker. These previews omit the save
record and canonical layer data, use a preview-only package format, and fail the
share-package validator. Normal installations do not enable this mode.

## Remaining validation

The current evidence supports a broad working prototype, not a claim of complete
catalog accuracy. The maintainer still needs to compare the indexed screenshots against
the same liveries in FH6. Cars with unusual removable body kits, active aero,
extreme split glass, or all eleven populated projection sections remain priority
edge cases. Base paint, paint material, tint, and paint-only records remain
separate milestones. Same-car installation still requires an in-game load test
before release; the automated proof intentionally used only a copied save.
