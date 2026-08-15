# KFPS Full-Livery Packages

This directory contains the isolated FH6 full-car livery package system. It
does not reuse the individual vinyl-group writer. Its only write path adds a
verified package to an FH6 save for the package's exact car; FH4, FH5, FM8,
cross-car application, and existing livery replacement remain unavailable.

The current product scope is intentionally narrow: render the correct neutral
car chassis and every vinyl placement. Base-paint colors, paint materials,
finishes, tint, upgrade-state reconstruction, and paint-only liveries are a
separate later milestone.

## User workflow

1. Open the public `Liveries` tab.
2. Choose the FH6 `Content` folder if KFPS did not find it automatically.
3. Scan local FH6 saves. KFPS deduplicates identical slot/current records.
4. Select an owned local livery. KFPS can preview it even when it contains vinyls
   by another player, but export remains unavailable until those vinyls are
   removed in FH6.
5. Export an eligible livery as a `.kfpslivery` package.
6. Add or select a received package to inspect its car, artwork, and target
   policy. KFPS resolves the matching inspection mesh from that PC's own FH6
   installation.
7. Select `Install in FH6 Save` and confirm. KFPS verifies the exact car against
   the local game installation, creates a recovery record, and adds a new livery
   folder without replacing an existing entry. FH6 may need to reload its save
   before the new livery appears.

The scan is read-only; only the explicit install action writes. Liveries owned by another player are excluded. Owned
liveries containing another player's vinyl groups remain available for private
visual inspection, but every package creation and validation path rejects them.
The UI explains that the foreign vinyls must be removed in FH6 before export.

Private source previews contain rendered inspection material only. They omit the
original livery record, its header, and canonical layer data, and cannot be added
to the saved share-package library.

## Package contract

`.kfpslivery` is a ZIP container with a versioned `manifest.json`. Version 1
contains:

| Path | Purpose |
| --- | --- |
| `source/fh6/C_livery` | Exact compressed FH6 livery record for lossless provenance and future same-game installation. |
| `source/fh6/header` | Exact-car FH6 title/header template. Required for installation. |
| `source/fh6/bigThumb.webp` | Original FH6 thumbnail when available. Older packages receive a deterministic fallback during installation. |
| `livery/layers.json` | Canonical section-aware KFPS layer representation for future reprojection and cross-game recompilation. |
| `mesh/vehicle.json` | Car ID, model/archive identity, archive hash, proxy entry, and projection inventory. It contains no game mesh bytes. |
| `projection/vehicle-map.json` | Derived section planes, axes, bounds, scales, and rotations. |
| `projection/rendered/*.png` | Livery-owned section renders used by the inspector. |
| `projection/index.json` | Projection/render inventory and format identity. |

Every member is size- and SHA-256-addressed by the manifest. Validation rejects
unsafe paths, duplicate names, untracked files, missing records, unsupported
versions, oversized expansion, hash mismatches, and disagreement between the
manifest, canonical layers, vehicle metadata, and the preserved `C_livery` car
identity. KFPS independently decodes the preserved source again and requires
exact canonical layers, section counts, render inventory, and decoded section
preview pixels.
Changing derived data and replacing its package hashes does not bypass this
semantic verification.

Older compiler revisions are listed without blocking startup. Opening one
rebuilds it from its embedded source on the background livery worker, verifies
the rebuilt package, and replaces the old local copy atomically.

The exact source record is opaque and may contain original save identity. The
installer preserves artwork bytes but rewrites destination-owned identity
metadata and creates a fresh local header identity before committing anything.

## Same-car FH6 installation

Installation is deliberately fail-closed:

- It accepts only a current, verified, exportable `.kfpslivery` package.
- Package car ID and model code must match the recipient's local FH6 car archive.
- FH6 may remain open. If its save changes while KFPS stages the new entry, KFPS
  aborts before commit rather than writing over a concurrent change.
- A single destination account identity must be unambiguous. The user can select
  the exact `ContainersRoot` when more than one account exists.
- Source artwork is decoded before and after destination identity rewriting and
  must remain identical.
- KFPS hashes the destination save before staging and aborts if any pre-existing
  file changes before commit.
- The commit creates one new `Livery_*` folder. It never overwrites an existing
  folder or livery.
- The committed header, source record, ownership policy, placement count,
  decoded artwork, and thumbnail are reopened and verified. A failed check
  removes the newly created folder automatically.
- A transaction recovery record is stored under
  `runtime/full-livery/install-backups`.

## Target decisions

KFPS exposes explicit `KEEP`, `CHANGE`, and `DISCARD` rows for each destination.

- **FH6, same car:** preserve the exact livery and canonical layers; rewrite
  destination save identity/header GUID/creator metadata; discard inspector
  mesh, projection previews, and package previews from the game save.
- **FH6, different car:** blocked. Cross-car application is outside the current
  product contract.
- **FH5/FH4:** retain canonical artwork only. Shape identity, section projection,
  target car, and header dialect need a verified encoder. Installation is not
  implemented.
- **FM8:** retained canonical artwork is not installable until a full-livery
  dialect encoder exists.

The policy is intentionally conservative. Preserved data is not presented as a
working cross-game conversion.

## 3D inspection

The embedded inspector is local-only:

- Three.js runtime files are vendored under `tools/livery-inspector` with their
  MIT license and provenance record.
- The renderer is KFPS's own Three.js/WebGL inspector. No external project's UI
  or renderer is used.
- A random token scopes every localhost server session.
- Static paths and package member paths are constrained and packages are fully
  revalidated before serving.
- The package identifies the car. KFPS resolves and privately caches the full
  authored car scene from that PC's FH6 installation. Scene transforms are
  retained, explicit stock parts are shown by default, and complete locally
  available upgrade choices can be selected in the inspector. Incomplete
  optional variants are omitted rather than leaving partial geometry visible.
- Paint and glass use FH6's dedicated `TEXCOORD_3` livery coordinates. Top,
  left, right, front, back, and glass masks remain independent because their UV
  rectangles overlap. A surface-facing test chooses the applicable section,
  then remaps that section's exact `Masks.xml` rectangle into its independently
  packed paint tile. This avoids both ordinary-material-UV errors and cross-side
  texture bleed.
- Wheel and brake model entries are authored in local corner space and cannot be
  placed at the model origin. The prototype excludes those unplaced entries and
  draws neutral inspection wheels at the exact four positions in the local
  archive's `Locators.xml`. Their dimensions are wheelbase-relative stand-ins,
  not copied game tuning data.
- No extracted game mesh or raw projection asset is included by the normal KFPS
  export workflow.
- `Kfps.ChassisConverter.exe` is a self-contained Windows x64 helper. It reads
  the local scene and referenced model entries from the recipient's own FH6 car
  archive, preserves the highest-detail chassis geometry and exact livery UV
  channels, and writes a private local GLB cache. End users do not need Blender,
  .NET, or a separate extraction-tool installation.
- Livery-bearing paint and glass without exact `TEXCOORD_3` coordinates are
  rejected. KFPS does not substitute a visually approximate world-space
  projection, because the approximation breaks scale and alignment on curved,
  asymmetric, and window geometry.
- A new package selection cancels an obsolete conversion. Corrupt cached GLBs
  are rejected and rebuilt from the local game archive.

## Known prototype limits

- This milestone exports, receives, validates, catalogs, inspects, and installs
  packages for the exact same FH6 car only.
- The section-aware contract has been visually validated on the user-verified
  803-placement `ALF_00_SE048SP_90` and 10,368-placement `nis_gtrlm_95`
  liveries. The same untuned mapping handles body sides, top, front windshield,
  rear windshield, and a selectable Nissan wing without cross-section bleed.
- A structural conversion audit covered all 660 car archives in the tested FH6
  installation. All 652 livery-capable archives produced validated exact-UV
  scenes; eight traffic-only archives had no usable livery-bearing paint and are
  intentionally unsupported. This proves catalog-wide structural compatibility,
  not pixel-perfect visual validation of every car. More user-verified cars with
  unusual wings, mirrors, windows, and all-eleven-section coverage remain useful.
- The neutral wheels make the current inspector coherent but are not a faithful
  reconstruction of each car's installed wheel, tire, brake, or suspension
  configuration. Selectable scene-authored body options are supported, but the
  recipient's exact installed tuning configuration is not reconstructed.
- Base-paint color and material state are not decoded yet. Empty placement
  records remain hidden because this milestone cannot distinguish an unused
  record from a paint-only design reliably.
- Package hashes prove internal consistency, not author identity or trust.

## Development commands

```powershell
.\python\python.exe -m tools.livery.export_full_livery_package `
  "C:\path\to\Livery_folder" `
  "runtime\full-livery\runs\test.kfpslivery" `
  --game-folder "C:\XboxGames\Forza Horizon 6\Content"

.\python\python.exe -m tools.livery.serve_inspector `
  "runtime\full-livery\runs\test.kfpslivery"
```
