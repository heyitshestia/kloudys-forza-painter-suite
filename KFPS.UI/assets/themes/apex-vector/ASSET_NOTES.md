# Apex Vector assets

The four legacy SVG files directly in this folder were authored for KFPS on 2026-07-20. They use original geometric construction and contain no extracted WipEout artwork, logos, ships, icons, screenshots, type, or textures.

The visual research informed general principles only: strict information rails, negative space, high-contrast flat color fields, technical progress cells, and restrained ambient motion.

- `apex-vector-backdrop.svg`: scalable cool-white engineering field.
- `apex-vector-panel-frame.svg`: notched nine-slice structural frame.
- `apex-vector-button-lens.svg`: clipped control edge and signal treatment.
- `apex-vector-logo-reticle.svg`: original KFPS logo instrument surround.

IBM Plex font files are stored separately under `assets/fonts/apex-vector` with their OFL license.

## Native menu revision

The updated native theme uses original QML pennants and folded planar fins in
`qml/themes/apex`, existing bundled interface icons, and the same IBM Plex fonts.
No game assets, audio, proprietary typefaces or external runtime dependencies
were added. The older SVG frames are retained for compatibility but no longer
draw over the new flat panels and controls.
The `icons` subdirectory contains only monochrome derivatives of the five
existing KFPS `assets/icons-carbon` SVGs with matching names. Geometry is
unchanged; explicit foreground colours remove effect-layer allocation and
preserve menu icons in Qt's software renderer. Display-size rasterization
avoids magnifying a cached 24-pixel image.

Visual references (research only, not packaged imagery):
- https://www.playstation.com/en-us/games/wipeout-omega-collection/
- https://blog.playstation.com/2016/12/03/wipeout-omega-collection-revealed-for-ps4/
- https://www.fluidstudio.co.uk/work/wipeout-omega-collection
