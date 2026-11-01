# 2049

An original KFPS theme inspired by the optical instruments and mechanical archive interfaces in Blade Runner 2049.

## Design

- One continuous black-glass instrument surface, narrow cyan/green perimeter, lime phosphor text, amber status and red warning accents.
- Etched calibration rails, corner-only lattice, edge wear and a restrained horizontal raster. No cloudy exposure or stacked high-contrast grain.
- IBM Plex Sans for readable controls; IBM Plex Mono for instrument headings and identifiers.
- New full-width workspace and lower navigation bank replace the sidebar and floating header controls only in this theme. Native title-bar controls and existing route/service behaviour are retained.
- Create uses separate source/output viewing bays and a lower instrument bank for source analysis, generation profile, shape budget and execution. Other pages use unframed surfaces inside the same console.
- Viewing-bay registration marks, open field baselines and navigation ticks share the display surface instead of enclosing each control in a filled plate. Keyboard focus, hover and selected states remain distinct.
- Create's form state and actions are shared with its ordinary presentation; changing theme does not reset the budget, checkpoints or manual options. The workbench scrolls at minimum window size.
- Actual content plates travel 48 pixels and settle into registration over 510 ms. The four-pixel edge reader remains optional. No filters over artwork.
- Ambient mode adds a 16-second rolling scan with a short pause, occasional subpixel raster drift, sparse horizontal dropouts and fine scratches. These are behind the controls and artwork, not a full-window distortion filter.
- Reduced-motion and ambient-motion preferences are respected. Inactive and minimized windows stop ambient movement.

## Provenance

Primary visual and motion references: [Territory Studio](https://territorystudio.com/project/blade-runner-2049/) and [Cantina Creative](https://www.cantinacreative.com/film/blade-runner-2049).

All theme geometry and animation are implemented locally in QML. The bitmap materials under `assets/themes/2049/` are original deterministic artwork made with `tools/build_2049_textures.py`. No film screenshots, film logos, soundtrack, video, or external source code are included. Existing KFPS icons and IBM Plex fonts under `assets/fonts/apex-vector/` are reused without duplication; the fonts retain their existing SIL Open Font License.

This is a KFPS shell theme. It does not replace independently selected Vinyl Editor or Livery Studio themes.

All measurements and status labels come from existing services. The interface does not invent progress graphs or sample output. Normal generation validation, queueing, safe stop and force-stop confirmation remain authoritative.
