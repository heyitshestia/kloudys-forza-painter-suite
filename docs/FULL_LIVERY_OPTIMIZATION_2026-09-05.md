# Full Livery Renderer Optimization

## Scope and starting point

- DIRTY and CLEAN start clean at `73700b68288aa0bb62bd09df1e8939fa591515f7` (3.1.59).
- Implementation and tests stay in DIRTY. Native Local, game saves, live memory,
  import/export rules, ownership policy and portable package format stay unchanged.
- Initial implementation scope excluded promotion and publication. Subsequent
  approval covers promotion to CLEAN/main and version 3.1.60, without a new release.
- Run evidence: `runtime/audits/livery-optimization-2026-09-05/` (ignored, local only).

## Milestones

1. Lifecycle: first rendered frame, bounded startup, context/crash reporting,
   resource estimates and device-aware memory guards. Validate cancellation,
   stale events, shutdown, timeouts and simulated memory pressure.
2. Loading and display: reuse unchanged validated derived assets, share materials,
   avoid idle work, correct output color and glass opacity, bounded anisotropy.
   Compare identical inputs and record resource counts and warm/cold timings.
3. Local texture quality: rerender vectors at higher resolution separately from
   portable packages, with explicit budgets and cache identity. Verify masks,
   orientation, alpha and cache corruption/restart behavior.
4. Integration: actual worker and browser paths, desktop/mobile screenshots,
   repeated loading/rotation/filtering/disposal, focused and broader regressions.

## Decisions and stop conditions

- Retain one disposable WebEngine viewer per selection. A persistent scene could
  reduce model startup, but increases the unverified driver-lifetime surface.
- Never retain two live 3D scenes for a visual transition. A loading cover is
  preferred to keeping an old GPU scene alive or adding a blocking screenshot.
- Do not raise texture resolution blindly. Native package sections stay 2048x1024;
  local quality must improve real detail, not upscale those images.
- Missing, changed or corrupt derived cache files must be rebuilt. Untrusted
  packages still require full validation.
- Stop an individual render on a budget breach or missing asset; record why.
- Local automated tests are not AMD/Intel/NVIDIA driver qualification. The
  experimental release gate stays in place.

## Initial lookback

The existing disposable viewer, worker protocol, cache catalog, source rasterizer
and projection contract already solve much of the problem. Reuse them. The main
gaps are readiness/lifetime observability, repeated validation work, shader output
handling and low local texture density, not the working game import/export path.
No new renderer framework, package dialect or repository is needed.

## Status

- Implemented and locally validated in DIRTY; approved for CLEAN/main as 3.1.60.
- Publication includes the follow-up Saved packages Add compatibility fix, with
  612 combined regression tests passing. No public release or bundle is requested.
- The subsystem remains experimental. This is not multi-vendor GPU qualification.

## What changed

- A preview becomes ready only after its first complete rendered frame. A short
  loading-cover fade avoids displaying an old car while the next one loads.
- The Qt browser URL changes only for a genuinely new session. Shared service
  progress notifications can no longer reload the same page repeatedly.
- Duplicate selections are ignored while that selection is loading or visible.
  Failed selections can be retried. Stale results cannot replace a new selection
  or reopen a viewer after leaving the tab. Closing the tab clears queued jobs.
- Server startup, browser loading, renderer crashes, shader errors, missing
  textures and graphics-context loss produce explicit failures and diagnostics.
- Cancelling repeatedly cannot extend the worker or server termination deadline.
- GR86 tracked materials fell from 488 to 17 by sharing equivalent materials.
  Geometry, mesh visibility rules, section routing and draw-call counts were not
  changed by that optimization. Direct-UV mask samples are reused within shaders.
- Shader output uses the renderer's color-management and tone-mapping path.
  Opaque vinyl coverage on glass is no longer artificially limited to 82% alpha.
- Animation is limited to 60 Hz; idle and hidden views stop drawing. Reset clears
  residual orbit momentum. Narrow layouts wrap their header without overlapping
  controls, and an untouched/reset camera reframes when the viewport changes.
- Textures use bounded anisotropic filtering. Closed/failed loads abort their
  requests, close image bitmaps, dispose tracked GPU objects and release context.
- High quality rerenders native vectors directly into cropped section tiles at
  twice the linear pixel density. It does not upscale the package's PNGs.
  Standard uses the original package sections. This preference is saved locally.
- Referenced artwork that cannot be resolved locally uses the original section
  image, unchanged. Mixed resolution is reported in the UI and diagnostics rather
  than silently omitting content. In the supplied GR86, this applies to both body
  sides; its other populated sections use higher density.
- Derived mesh validation receipts and atlas content hashes avoid repeated parsing
  of unchanged assets. Missing/corrupt files and malformed cache indexes rebuild.
- Only disposable meshes, atlases and private previews are eligible for the
  2 GiB soft disk quota. Active files, recent work, packages, game saves, links and
  junctions are protected. Protected/recent files can temporarily exceed the quota.

## Limits and compatibility

- Preview preparation budgets follow physical/available RAM, within 768 MiB to
  6 GiB. Existing non-preview worker operations retain their previous 6 GiB limit.
- Renderer-process memory and shared graphics-process growth are monitored. Viewer
  budgets range from 384 MiB to 2 GiB, with a system-memory reserve check.
- JavaScript estimates geometry, texture/mipmap and framebuffer allocation and
  uses a 192-512 MiB graphics budget. Drawing resolution adapts to the remaining
  budget; device texture-size limits are checked before upload.
- These are conservative estimates and sampled process statistics, not exact VRAM
  accounting or a guarantee against a driver-level allocation failure. The shared
  graphics process is never killed by the livery guard.
- High preparation uses Standard when less than 2 GiB RAM is available and reports
  the downgrade. Oversized texture contracts fail with a Standard-quality hint.
- Local render-contract revision is 11. Portable package/compiler revision remains
  unchanged at 11; these are separate contracts. Existing packages need no rewrite.
- The section-rendering helper accepts optional local canvas bounds. Its existing
  package-export callers retain the same 2048x1024 defaults. Import/export routes,
  ownership rules, save discovery, save files and live-memory logic were not changed.

## Measurements

The comparison used the same supplied GR86 package, game assets, Python 3.12.10,
and pre-existing mesh, with separate texture caches. Unchanged CLEAN supplied the
baseline worker code; all generated evidence stayed in DIRTY. Values are local
samples, not claims for every PC. The measurement wrapper itself adds startup time.

| Preparation | CLEAN Standard | DIRTY Standard | DIRTY High |
| --- | ---: | ---: | ---: |
| First texture build, worker seconds | 1.750 | 1.453 | 3.625 |
| Median warm worker seconds, 3 repeats | 0.141 | 0.078 | 0.078 |
| Median warm wrapper wall seconds | 0.663 | 0.606 | 0.613 |

High is deliberately slower on first preparation. It adds real detail rather than
claiming a free resolution increase. Earlier single-run timings were exploratory;
the repeated same-interpreter comparison above supersedes them.

The actual Qt page, service, worker and local server were exercised through 36
load/close cycles across four cars, both quality settings, private local previews
and the supplied portable package. The largest source had 10,368 placements.
Warm selections in this run reached the complete preview in about 1.6-2.2 seconds.
Two cycles included rapid supersession. Every close left zero viewer subprocesses.

| Twelve-cycle batch | Host after-close range, MiB | Peak total process-tree MiB |
| --- | ---: | ---: |
| 1 | 459.5-584.4 | 935.0 |
| 2 | 494.8-575.7 | 963.6 |
| 3 | 507.0-569.6 | 928.4 |

This shows a plateau in the tested scenario, not proof of no leak on other drivers.
The final mixed-resolution path was separately retested in native Qt, including
the bundled Python runtime. Interruption before readiness left no pending worker,
running worker, viewer URL or inspector process. No QML warnings were recorded.

## Verification

- 604 UI/service regression tests pass, including 21 focused optimization tests.
  The broad suite also emits a shutdown ResourceWarning about 171 uncollectable
  objects. Its origin was not established here; passing tests are not treated as
  a clean whole-project leak audit. The focused optimization run has no such warning.
- Actual browser interaction: drag, zoom, reset, automatic rotation, 48 section
  toggles, idle settling, resize, disposal and recovery. Resource counts remain
  constant during rotation/filtering and tracked resources reach zero on disposal.
- Screenshots and nonblank/pixel-change checks at 1440x900, 390x844 and 3840x2160.
  A simulated 2 GiB browser memory hint at 4K used a 0.561 drawing ratio and an
  estimated 181 MiB allocation within a 192 MiB budget. This is a policy test on
  the same NVIDIA GPU, not physical low-memory hardware qualification.
- Missing texture and deliberate context-loss tests stop safely; reload recovers.
- All 11 native orientation mappings are tested independently. Nine populated
  GR86 sections were also compared with their Standard crops. Original-resolution
  fallbacks are pixel-identical; higher-resolution crops preserve placement and
  artwork with expected raster-edge differences. Thin window logos have lower
  binary alpha overlap, so visual inspection and premultiplied-color error were
  used alongside coverage, rather than treating a single threshold as ground truth.
- A damaged paint file and a valid-JSON-but-invalid `null` index were deliberately
  introduced only in an isolated test cache. Both rebuild and reopen successfully.
- The supplied package SHA-256 remains unchanged after all tests. No game writes
  or live-memory actions were performed.

## Diagnostics and local evidence

The existing **Diagnostics** action includes the added viewer logs. Session folders
are under `runtime/experiments/full-livery/sessions/` in an ordinary installation:

- `viewer-<timestamp>-<id>/viewer-events.jsonl`: phases, ready/failure, GPU identity,
  texture quality, timings, estimated resource counts and memory budget.
- `viewer-latest.json`: latest frame/health sample, refreshed about every five seconds.
- Worker `request.json`, `result.json`, `progress.json`, stdout/stderr and recovery
  records continue to use the existing isolated-session format.
- `diagnostics/viewer-memory-guard.json`: most recent memory/time-limit stop.

Local evidence index, relative to `runtime/audits/livery-optimization-2026-09-05/`:

- `benchmark-result.json`: final repeated CLEAN/DIRTY preparation comparison.
- `qt-stress-result.json`: 36-cycle memory/readiness/process evidence.
- `qt-result.json`, `qt-bundled-final-console.log`: final bundled-runtime native check.
- `qt-interrupt-result.json`: rapid selection followed by immediate tab closure.
- `browser-checks-final.log`, `browser-small-device.log`: interaction/failure/budget checks.
- `cache-pixel-result.json`: corruption recovery, section comparisons, package hash check.
- `diagnostic-export-test.log`: actual diagnostic ZIP includes viewer events and
  latest samples, without mesh, image or livery package contents.
- `suite-final.log`: broad regression results.
- `output/playwright/`: before/after, narrow, large and Qt screenshots.

These files are private ignored test evidence, not release or commit content.

## Milestone lookback

The cropped-vector approach retains the existing projection mappings without an
8K canvas per panel or a new package format. Disposable workers remain appropriate;
a persistent-viewer rewrite is not justified by the measured warm-load savings.

The initial offscreen Qt attempts were not a valid hardware test. A non-activating,
off-desktop native Qt window exposed the equal-URL reload loop; fixing the shared
notification binding resolved it. No user window focus was taken for these tests.

The pixel comparison exposed the difference between thin-edge coverage and missing
content. It also prompted preserving original images when local referenced artwork
cannot be resolved. Quality was not increased by discarding those references.
Two benchmark harness attempts hit existing path-containment checks; the harness
was corrected to keep all outputs in DIRTY while reading baseline code from CLEAN.
No production containment rules were relaxed.

Scope review retained the old import/export worker limits and added cancellation
of queued preview jobs when the tab closes. No additional renderer framework,
shared-model cache or experimental import path was introduced.

## Remaining gaps and next test

- NVIDIA RTX 4090/ANGLE D3D11 was the available real graphics device. AMD, Intel,
  hybrid-GPU switching, remote desktop, physical low-RAM machines and long-duration
  full-application sessions remain unqualified.
- This pass does not certify every car assembly or fix missing external artwork.
  The tested Alfa prototype still shows an anomalous front component placement in
  both quality modes. It uses the unchanged local mesh/assembly path and should be
  compared with its reference assembly separately; no car-specific offset was added.
- Higher texture density cannot recover detail absent from a raster logo or improve
  the game's native projection masks. Those masks retain their original dimensions.
- In DIRTY, open Liveries, compare Standard and High, switch between several cars,
  rotate/zoom, leave and reopen the tab, then use Diagnostics if a preview stops.
  Multi-vendor testing remains outstanding; promotion was subsequently approved.
