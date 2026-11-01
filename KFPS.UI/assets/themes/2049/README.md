# Original optical materials

All PNGs in this folder are original, deterministically generated KFPS artwork. No film frame, photograph, downloaded material texture, logo or third-party code is embedded in them.

Rebuild with the bundled Python and `KFPS.UI/tools/build_2049_textures.py` (NumPy and Pillow are existing dependencies). Seed: 2049.

- `optical-glass.png`: 768x768 near-transparent emulsion, sparse dust and fine scratches. No low-frequency cloudy exposure.
- `phosphor-raster.png`: 192x96 restrained horizontal raster tile; no crossing noise grid.
- `optical-backing.png`: 1920x1080 quiet black glass surface, narrow curved luminous rim, chromatic edge registration, corner-only lattice and perimeter wear.
- `optical-rim.png`: 1920x1080 edge-only CRT lens treatment; centre is transparent.
- `analog-wear.png`: 1024x512 sparse horizontal dropouts and fine wear, generated with a separate seed of 20492049.
- `analog-sweep.png`: 1024x80 low-alpha rolling scan band with uneven registration and broken line segments; animated only behind content.

The screen and animation references are credited in `qml/themes/2049/README.md`. Those references are not shipped.
