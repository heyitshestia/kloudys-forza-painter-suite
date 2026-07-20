# Apex Vector theme storyboard

Status: implemented in DIRTY staging

## Creative thesis

Apex Vector treats KFPS as a precision race-control and graphics-compilation
workstation. It is bright, exact, fast, and information-first. The interface keeps the
existing KFPS layout and density, then adds an original technical field, decisive state
changes, compact typography, and restrained motion around that layout.

The theme is not a replica of a game interface. WipEout Omega Collection menu footage,
developer studies, fan analyses, and other futuristic UI references informed broad
principles only: strict rails, negative space, compact technical type, geometric
progress language, asymmetric composition, and motion that communicates direction.
No screenshot, logo, type treatment, menu panel, icon, texture, ship, or extracted game
asset is included in KFPS.

## Design pillars

### 1. Artwork remains the subject

- Content columns and control locations do not move.
- Large surfaces stay cool white and low contrast.
- The source and preview wells use neutral gray so white and black vinyls remain visible.
- Decorative geometry sits behind content and avoids dense reading regions.

### 2. State is unambiguous

- Coral means execute, selected content, or urgent attention.
- Black marks the current navigation location.
- Cyan identifies secondary telemetry, focus, and transfer direction.
- Green is reserved for ready, healthy, and completed states.
- Handmade pink and Toolmade blue keep their application-wide meanings.

### 3. Motion explains direction

- Page changes use one fast lateral transfer, not a decorative loop.
- Hover signals illuminate once and settle.
- Ambient telemetry performs short, infrequent sequences with long rests.
- Large geometry moves through transforms and opacity only.
- Reduced motion preserves every state while removing travel and sequencing.

### 4. Precision without visual noise

- IBM Plex Sans handles normal reading.
- IBM Plex Sans Condensed SemiBold handles compact headings.
- IBM Plex Mono handles measurements and status fragments.
- Letter spacing remains zero and headings stay proportional to their containers.
- Fine rails and microcells stay at the perimeter rather than crossing text.

## Spatial storyboard

### Window field

The full window is a cool-white engineering surface with a fine grid, sparse datum
marks, and diagonal transfer rails. A large original layer-array instrument occupies
the right half. It resembles nested vinyl geometry under analysis without depicting a
specific vehicle, logo, or game object.

The layer array has three depth groups. In the idle state they drift by a few pixels and
less than two degrees over long periods. The central registration target remains quiet
enough to sit behind preview, help, settings, and community content.

### Sidebar

The sidebar is an instrument rail rather than a floating card. The KFPS logo sits in a
thin registration reticle. Inactive destinations use dark semantic icons and text.
The active destination becomes a near-black control with white text, a vivid red edge, and
a short three-cell state indicator. This contrast remains readable on the bright field.

### Header

The announcement ticker, supporter state, version, and page title stay on their shared
horizontal levels. Small saturated cyan and red buses reinforce those anchors without enclosing
them in additional cards. The update state continues to use the shared red version-pill
blink instead of adding a theme-specific warning.

### Workspace

Structural sections remain unframed. Repeated items, actual tools, and inputs use the
original notched frame language. The custom frame is exclusive, so legacy outlines and
rounded shells do not stack beneath it. Primary controls use a flat saturated red field
with hard clipping, printed registration marks, and no hover bleed. Panels use opaque
white or light-gray fills; the theme deliberately disables glass blur, refraction, sheen,
and depth gradients.

### Community and outputs

Tile grids keep their current dimensions and interactions. Thumbnail wells remain
neutral gray across light and dark artwork. Selection, classification, supporter state,
download state, and destructive actions retain separate semantic colors.

## Motion specification

### Idle layer array

- Primary drift: 18 to 24 seconds.
- Secondary counter-drift: 22 to 30 seconds.
- Maximum translation: 8 logical pixels.
- Maximum rotation: 1.6 degrees.
- Motion pauses while the window is inactive and freezes in screenshot mode.

### Perimeter telemetry

- A short bus sequence resolves in roughly 1.15 seconds.
- The sequence rests for at least 6.6 seconds before another event.
- No rapid blink loops continuously.
- Telemetry never accepts input and never enters a reading surface.

### Page transfer

Total duration: 320 ms.

1. A white veil stabilizes the outgoing content.
2. A narrow black sweep establishes direction.
3. Coral and cyan rails pass through as transfer markers.
4. Trailing microcells collapse at the destination edge.

Reduced motion replaces travel with a short static state change.

### Control interaction

- Hover response: 105 to 190 ms, one shot.
- Press travel: 70 to 95 ms.
- Release: 110 to 140 ms with no elastic overshoot.
- Selected navigation resolves directly and does not pulse forever.

## Original asset manifest

| Asset | Format | Purpose |
| --- | --- | --- |
| `apex-vector-backdrop.svg` | SVG, 2560 x 1440 viewbox | Full-window engineering field |
| `apex-vector-panel-frame.svg` | SVG | Original notched equipment outline |
| `apex-vector-button-lens.svg` | SVG | Clipped action-control lens and state cells |
| `apex-vector-logo-reticle.svg` | SVG | Original KFPS instrument surround |

Every SVG is text-free, scalable, locally referenced, and authored for KFPS. Asset
provenance is recorded in `assets/themes/apex-vector/ASSET_NOTES.md`.

## Fonts and licensing

The theme packages unmodified IBM Plex Sans Regular, IBM Plex Sans Condensed SemiBold,
and IBM Plex Mono Regular files. IBM Plex is distributed under the SIL Open Font
License 1.1. The complete license and font notice live in
`assets/fonts/apex-vector/`.

The theme contract treats font files as optional. Existing themes keep empty font paths
and retain their previous system-font behavior. A missing custom font falls back to the
existing KFPS font stack without blocking startup.

## Performance budget

- No continuously repainted full-window Canvas.
- Canvas geometry repaints only when its containing size changes.
- Ambient movement uses scene-graph transforms and opacity.
- No continuously animated full-window blur.
- Motion pauses while the application is inactive.
- All theme SVGs and font files stay below a 2 MB packaged payload.
- Software rendering at 1360 x 820 remains part of the capture gate.

## Accessibility and preference behavior

- Text and controls are checked against the bright field at every supported size.
- Selected navigation uses dark fill and white text for strong contrast.
- Focus remains cyan and does not rely on motion alone.
- Reduced motion, ambient motion, glass effects, manual generator overrides, and live
  status remain global persisted preferences.
- Screenshot mode chooses deterministic static animation states.
- Public-theme access is declared consistently in the Python registry and QML palette;
  supporter and non-supporter footer messaging stays dynamic.

## Validation matrix

The staging gate includes:

- Every KFPS page at 1360 x 820, 1760 x 1040, 1920 x 1080, 2560 x 1440, and 3440 x 1440.
- Compact and wide sidebars.
- Empty, populated, selected, hover, focus, pressed, and update states where available.
- Normal motion, reduced motion, and deterministic screenshot states.
- Theme contract, SVG parsing, asset path, font license, payload, QML refinement, and
  layout audit tests.
- Regression captures for Night Blossom, Command Prompt, Windows 94, Patron's Atelier,
  Carbon Dark, and Overdrive 200X after shared-control changes.

## Acceptance criteria

- No content or workflow changes when the theme is selected.
- No theme-name branch in a shared component.
- No copied reference material ships with KFPS.
- No text overlaps, clips, or becomes unreadable at a supported viewport.
- White and dark artwork remain visible in output and community previews.
- Hover artwork remains clipped to its control.
- Ambient animation does not create a persistent interaction cost.
- Existing public and supporter themes retain their intended behavior.
