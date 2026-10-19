# Studio Component Converter Provenance

The development authority is the sibling livery component's
`src/chassis-converter` directory. The reviewed distribution copy is materialized
under `tools/livery-studio/src/chassis-converter` in KFPS; it is not a second
independently edited implementation. Neither layout is a separate repository.

## Sources And License

- KFPS baseline: `33de8f5589519c6e9320617eb3c148fb602ab5ff`.
- `Program.cs` and `GlbWriter.cs` are owned copies of the baseline
  `tools/livery/chassis-converter` files. Original SHA-256 respectively:
  `6e4ce01167332a37246976b51187d75cf241e5d309ffd6e2260a7a1e5da4e84c`,
  `d0a3098bcef536e123bb7918566237507fb658fb1a4061262205d0a74d9f53cc`.
- `ModelImporter.cs` is an owned, narrowly modified copy of the baseline's
  vendored importer. Other parser `.cs` files are linked read-only, not copied
  or built through baseline project references.
- Vendored upstream: D3FEKT/ForzaTechStudio commit
  `4f373c5fb192551ce5249e320dd79b1399b693ca`, MIT. The baseline provenance names
  that upstream revision; `LICENSE.ForzaTechStudio` preserves its notice.
- The build uses the existing `Syroot.BinaryData` 5.2.2 dependency from NuGet.
  The qualified self-contained executable includes its .NET runtime and package
  dependencies. Distribution must retain `LICENSE.ForzaTechStudio` and the
  applicable runtime/dependency notices under `../../licenses`.
  Game assets and extracted textures are not distribution inputs.

## Narrow Changes

The converter enumerates all declared options and shared memberships, preserves
empty options and raw parent metadata, rejects ambiguous path substitution,
reports blocked alternatives, and emits mesh/UV/transform coverage. The importer
keeps native UV components without flip/unflip loss and rejects unsupported
geometry formats, missing buffers, invalid strides, and unverifiable packed
offsets. It is not a new general model decoder or a game-rendering implementation.

Phase-4 corrections resolve the declared index-buffer ID, reject invalid index
ranges, resolve forward bone parents without recursion, select one raw native
LOD bit across the scene, preserve opposite-winding faces, and apply spatial
reflection parity. Independently encoded normals are no longer distorted by
position compression bounds. Named attachment misses cannot alias unrelated
numeric bones. Scene skeletons and material/bucket flags are exposed as evidence;
unverified bind/snap, skinning, paintable-glass and wheel-material semantics are
not claimed to be implemented. The pinned upstream revision is recorded above;
the KFPS baseline's `tools/livery/chassis-converter/vendor/ForzaTechStudio/PROVENANCE.md`
records the vendored source identity. Private research records are not required
to build or run the distributed converter.

The native-proof continuation restricts painting to UV3 plus each car's valid
native mask resources, preserves original mask attributes/hashes and disables
generic projection. Exact material binding replaces substring borrowing.
Material blob hashes, original resource references/parser parameter values,
unapplied override hashes and static-versus-blur/shadow purpose are additive
evidence, not a recreation of game shaders. Scene wheel presence is derived from
native WheelStyle membership, never filenames. Independent Python wire-reader
tests now compare native UV bytes through the source affine to GLB float32
streams; this is stronger than the earlier importer self-hash, but is not a
game-render or attachment/fitment equivalence claim.

## Build And Transfer

Run `../../scripts/build-converter.ps1` from this source directory, or invoke the
script by its full path. Shared `resolve-baseline.ps1` uses the sibling `repo`
for a development component named `livery`; in the packaged
`tools/livery-studio` layout it uses the containing KFPS installation.
Custom layouts require an explicit baseline. `-BaselineRoot` and `-Dotnet`
override read-only dependencies explicitly.

The qualified executable location, relative to this source directory, is
`../../runs/component-converter/converter/publish/Kfps.LiveryLab.Converter.exe`.
Its receipt is `../../runs/component-converter/converter/build-manifest.json`.
The v2 receipt records relative source/prerequisite paths, their hashes and the
executable hash, without depending on a developer's absolute workspace.
All files in this converter source directory, including this document, are
fingerprinted: a documentation change also requires reviewed receipt and
distribution-inventory refresh before qualification. Do not relabel an old
receipt as a new build. Tests use a separate `tests` build subdirectory.
`-Tests` builds the dependency-free regression executable.

All restore/build/cache/temp outputs are redirected beneath a named directory
inside the component's `runs` tree. No baseline vendor project is restored or
built. Development mode requires the qualified baseline commit and clean
converter prerequisites; packaged pinned mode verifies the exact prerequisite
inventory without requiring an installed Git checkout. Both modes reject
unexpected prerequisite bytes and redirected source/output paths.
Only the exact qualified converter executable and receipt are shipping inputs
from `runs`; test builds, caches, sessions and extracted assets are excluded.

The executable is self-contained and single-file. Its CLI remains
`--request request.json`; no GUI, game process, live-save access or installation
is performed. UV/source hashes verify byte-copy/build provenance only, not native
parser correctness, fitment, or game acceptance. The limitations below remain
part of the public contract; private experiment/audit files are not packaged.
### Direct textures and wheel completeness, 2026-10-18

`material_textures.py` is an independent bounded wire reader/extractor based on
the documented FTS PC texture-header structure, using the workspace's existing
Pillow decoder. No FTS texture decoder implementation was copied. Source paths
and hash evidence remain local; game-derived PNGs are run artifacts only.
`Program.cs` adds explicit incomplete-wheel/tire/fitment metadata after a real
render disproved completeness. It does not guess deformation or change geometry.

`NativeMorphs.cs` is an independently written, bounded non-damage MBuf reader
and supplied-coefficient evaluator. Its buffer layout and application order were
checked against the locally shipped FH6 tire vertex shader and raw native rim /
tire buffers. It is not wired into production position conversion: car-specific
coefficients and tire selection remain unverified. No GPL extraction-tool code
was copied; the separate Doliman100 research reference is a documented lead for
database field names, not the provenance of this implementation.

Mesh extras expose original per-channel native UV transform arrays and the
actual isolated pipeline identifier `native-unflipped-then-native-scale-offset-v1`.
The owned importer has never used the upstream FTS V flip; do not apply the
FTS-flipped preview correction to these outputs. This is additive metadata only:
UV accessor bytes, geometry and source affine application are unchanged.
Missing transforms remain null, and non-finite source channels are null rather
than guessed identities. Renderer qualification must reject missing evidence.

`PreviewWheelFit.cs` is an independently written, bounded artist-preview
deformation helper. Explicit dimensions control axial scale and radial rim/tire
mapping; normals use the inverse differential. It does not solve native morph
coefficients, infer stock dimensions, choose assets or touch UVs. Only the test
executable's `--wheel-preview` proof calls it; the production converter does not.
Those isolated outputs carry preview/non-export/non-parity flags and are not
fitment-qualified vehicle assets. Three source rims and two explicitly chosen
tire families are visual/test evidence, not a verified car-to-tire association.

