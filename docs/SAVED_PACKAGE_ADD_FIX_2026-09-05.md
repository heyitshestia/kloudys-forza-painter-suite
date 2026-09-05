# Saved packages Add: recipient preview compatibility

## State and scope

Implemented and tested in DIRTY on 2026-09-05. Subsequently approved for promotion
with the preceding renderer optimization to CLEAN/main as 3.1.60, without a new
release or bundle. Native Local, the running user instance, and game saves remain
outside the change scope.

## Confirmed cause

The Add worker validated a received package with `verify_previews=True` whenever
a local FH6 installation was linked. This regenerated all stored panel previews
and required every RGBA pixel to match the sender's preview exactly. Therefore,
linking local game assets could prevent an otherwise valid package from being
added at all.

The reported 225-layer package passed member hashes, canonical source decoding,
ownership policy, section counts, and car identity. It failed the extra Front
pixel comparison in both unchanged CLEAN and DIRTY. Front differed at 286 of
2,097,152 pixels (0.0136%); all seven populated sections retained identical image
bounds, and one section matched exactly. Both local Pillow 11.3.0 and the bundled
12.3.0 reproduced the rejection. The sender's renderer/dependency provenance is
not present in the package, so the exact origin of those pixel differences has
not been established. This was not introduced by the current viewer optimization.

## Implementation

- Add uses portable validation without local preview regeneration. All existing
  hashes, archive limits, image readability/dimensions, complete section inventory,
  source-derived canonical layer equality, ownership, and identity checks remain.
- Current-revision migration/copy has the same recipient behavior. Older revisions
  still follow the existing migration/rebuild route.
- Creating/exporting a new package still performs strict local preview rerender
  validation. No pixel-tolerance heuristic or per-package exception was added.
- Received packages are copied atomically and remain byte-identical. Existing
  collision handling, cancellation, indexing, and lazy preview preparation remain.
- Add failures have a dedicated inline message beneath Saved packages. Unrelated
  preview/index status changes cannot erase it; a new Add attempt clears it.
- The file picker and path-based entry point now use the same Add validation path.

The source container is the authoritative livery. Packaged preview pixels are
derived display data, not proof that two machines have identical rasterizers or
local game assets. Existing installation policy is unchanged.

## Validation

Evidence: `runtime/audits/livery-package-add-2026-09-05/` (ignored local artifacts).

- `unittest.log`: 612 tests pass, including eight new Add regression tests.
- Regression cases: renderer drift, repeat Add, already-in-folder Add, cached
  reindex, current-revision copy, damaged/rehashed unreadable PNG, rehashed layer
  alteration, foreign-owned source, cancellation, picker cancellation, missing
  file, and error persistence/retry.
- `add-first-pass-result.json`: actual QML Add button, supplied picker result,
  isolated worker copy, model refresh, automatic selection and High viewer load.
  Repeated Add produced one package, not a duplicate. Initial cold Add to ready
  was 11.109 seconds; repeated Add was 0.828 seconds on this machine.
- `reopen-result.json`: new process loaded the saved catalog and rendered the car.
- `reopen-visible.png`: visual inspection plus a central viewport pixel check
  (24,155 distinct colors) confirmed a nonblank textured car and visible list row.
- `rejection-visible.png`: corrupt-file rejection is visible beside Saved packages.
- Original package hash unchanged. No remaining helper child processes or QML
  warnings after integration tests. No live-memory or game-save operations used.
- `git diff --check` passed; CLEAN has no working-tree changes.

The native file picker was supplied its result by the test harness, avoiding focus
changes; the actual QML button, service, subprocess jobs, catalog and WebEngine
viewer ran normally. Early harness-only checks required replacing an invalid
absolute QML import with the existing relative import pattern, and waiting for
compositor presentation before taking screenshots. Final evidence includes those
corrections, not just a renderer-ready flag.

## Lookback and remaining limits

The work still addresses missing received packages, not renderer fidelity or
installation changes. Existing portable validation and atomic copying were the
correct foundation. The failure was a validation-contract error, not missing
files or a broken button. A pixel tolerance was rejected because it would be an
arbitrary substitute for source validation. Separating portability from local
compiler reproducibility is smaller and preserves the verified data contract.
No new package format or migration infrastructure was needed.

The prior assumption that equal compiler revisions imply identical preview pixels
is false. The best alternative, rebuilding every received package, would add
latency and unnecessarily change received artifacts. Keep the current focused fix.
The broad suite still emits its existing shutdown garbage-collection warning
(172 uncollectable objects in this run versus 171 in the preceding audit); this
is not a clean whole-application lifecycle qualification. GPU coverage remains
this machine's NVIDIA device. Restart DIRTY before retesting the Add UI.
