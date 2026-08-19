# KFPS Local Chassis Converter

This helper converts the complete locally authored FH6 car scene from a user's
own car archive into a neutral GLB cache used by the KFPS full-livery viewer. It
preserves scene transforms, triangle geometry, normals, and texture-coordinate
channels 0 through 3 for the car's stock/default configuration. It does not extract
paints, textures, material finishes, or other game assets into shareable livery
packages.

The published Windows x64 executable is self-contained. End users do not need
.NET, Blender, Python, or a separate extraction-tool checkout to prepare a local
chassis.

## Build

```powershell
dotnet publish .\tools\livery\chassis-converter\Kfps.ChassisConverter.csproj `
  -c Release -r win-x64 --self-contained true
```

The KFPS build copies the single-file executable into
`tools/livery/chassis-converter/bin/win-x64/`.

## Input Contract

The executable accepts `--request <json-path>`. The request contains the local
car ZIP path, its scene entry, and a local GLB output path. KFPS creates this
request in a temporary folder and terminates the converter when a newer
selection supersedes it.

The conversion contract keeps only the highest-detail model level, removes
degenerate and duplicate faces, applies each mesh's FH6 UV scale and offset,
normalizes coordinate handedness and triangle winding, and labels neutral paint,
glass, trim, dark, and hidden geometry for KFPS's Three.js renderer. It follows
the scene's explicit stock flags and selects one deterministic baseline for each
upgradable part. Loading every mutually exclusive body-kit variant into one scene
is intentionally prohibited because some car archives expand to unsafe memory
sizes. Missing required baseline geometry fails the conversion.

Livery meshes preserve FH6's exact `TEXCOORD_3` coordinates whenever present.
A verified paint or glass surface without UV3 is accepted only with a nonzero,
role-appropriate projection-side bitset; unclassified geometry is rejected.
Each accepted livery mesh carries separate final-render and projection-fitting
bitsets: ordinary body paint accepts the five body
projections, spoilers accept only the spoiler projection, trunk panels accept
back and top, and verified exterior windows accept only glass projections.
Interior window shells and lamp glass are excluded from livery routing. The
Python boundary validates every GLB buffer, accessor, index range, livery UV
channel, material role, selectable-part reference, and allowed-section
declaration before accepting the cache file.

## Provenance

The modelbin bundle parser and model importer under `vendor/ForzaTechStudio`
come from D3FEKT/ForzaTechStudio commit
`4f373c5fb192551ce5249e320dd79b1399b693ca`, licensed under MIT. The original
license is preserved at `vendor/ForzaTechStudio/LICENSE`. The GLB writer,
process boundary, role classification, validation, and KFPS integration are
KFPS-specific code.

Redistribution notices for the parser dependencies and self-contained .NET
runtime are indexed in `THIRD_PARTY.md`.
