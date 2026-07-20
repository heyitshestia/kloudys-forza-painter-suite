# Overdrive 200X theme storyboard

Status: implemented in DIRTY staging

## Creative thesis

Overdrive 200X imagines KFPS as a premium detachable head unit and vinyl plotting
controller designed in 2003, then rebuilt as modern military-science-fiction field
equipment. It is tactile, colorful, and mechanical without copying a particular
stereo, dashboard, game, or manufacturer.

The theme must feel like a working instrument. Light indicates state, motion explains
navigation, and material treatments establish depth. Decoration never obscures artwork,
logs, file names, or repeated controls.

## Reference synthesis

The visual language is informed by, but does not reproduce, these sources:

- Detachable head units used dense physical controls, dark display windows, silver
  faceplates, blue dot-matrix displays, and occasionally motorized mechanisms. The
  [Kenwood KDC-V7022 archive](https://www.crutchfield.com/p_113KDCV702/Kenwood-KDC-V7022.html)
  is a useful period example.
- Translucent plastics made internal structure part of an object's identity. The
  [Cooper Hewitt plastics history](https://www.cooperhewitt.org/2019/09/26/hero-to-zero-a-history-of-plastics/)
  and [Aalto Nokia Design Archive overview](https://www.aalto.fi/en/news/what-windows-does-the-nokia-design-archive-open)
  provide broader industrial-design context.
- Automotive head units are integrated control surfaces rather than decorative screens.
  The [Texas Instruments head-unit overview](https://www.ti.com/solution/automotive-head-unit)
  reinforces the modular hardware vocabulary.
- Early digital clusters used high-contrast luminous information and restrained warning
  colors. The [FIC cluster overview](https://www.fic.com.tw/the-evolution-and-trends-of-digital-cluster/)
  provides contemporary comparison material.

No reference image, logo, labeled control, texture, or interface layout will ship in
KFPS. All production assets are original and brand-neutral.

The second polish pass responds to the requested Halo: Reach mood through broad design
traits only: armored graphite equipment, cold tactical illumination, amber readiness
signals, exposed diagnostic lamps, and asymmetric instrumentation. It does not copy
Halo symbols, type, labels, interface geometry, artwork, or screen layouts.

## Design pillars

### 1. Hardware, not a flat skin

- Smoked display glass sits above a graphite chassis.
- Satin alloy rails and translucent polycarbonate reveal controlled internal detail.
- Buttons have a short physical travel and a defined lower lip.
- Fine seams, fasteners, and registration ticks establish scale.

### 2. Information emits light

- Cyan identifies primary interaction and navigation.
- Amber identifies system state, indexing, and neutral activity.
- Coral is reserved for destructive, failed, or urgent states.
- Lime is reserved for successful completion and healthy status.
- White text remains the dominant reading color.

### 3. Motion has a mechanism

- Page transitions behave like a motorized faceplate or scanning carriage.
- Hover sweeps resemble light moving through molded plastic.
- Progress behaves like an indexed display, not a decorative spinner.
- Ambient motion is infrequent and slow enough to disappear during concentrated work.

### 4. Dense but disciplined

- The existing KFPS information density and geometry remain intact.
- Decorative labels are abstract marks, not fake instructions or feature descriptions.
- Fine detail is strongest around the frame and controls, leaving content areas quiet.
- Micro LEDs sit on exposed chassis seams and the top rim of selected equipment panels,
  never beneath reading glass or across text.

## Palette

| Role | Color | Purpose |
| --- | --- | --- |
| Chassis black | `#05080a` | Window and deepest background |
| Display smoke | `#09151a` | Preview wells and console surfaces |
| Graphite | `#151d21` | Main panel body |
| Satin alloy | `#c9d4d8` | Fine physical highlights |
| Display white | `#f4fbfc` | Primary text |
| Cyan | `#62efff` | Primary actions and selected navigation |
| Deep aqua | `#087f91` | Pressed controls and depth |
| Amber | `#ffc45a` | Indexing and equipment state |
| Coral | `#ff6074` | Failure, destructive action, urgent update |
| Signal lime | `#aeea72` | Success and ready state |

Large surfaces remain neutral. Cyan, amber, coral, and lime never become full-screen
washes.

## Typography and iconography

- Keep Segoe UI Variable for readability.
- Use uppercase only for tiny equipment labels and status fragments.
- Preserve normal letter spacing for application text.
- Use the Carbon line-icon geometry as a starting family, recolored through theme tokens.
- Add no copied automotive symbols or manufacturer marks.
- The KFPS mark remains recognizable inside an original segmented dial treatment.

## Spatial composition

### Full-window backdrop

The custom background is a wide, low-light product render of an original vinyl plotting
console. It contains:

- A graphite chassis with satin silver perimeter rails.
- A dark cyan display window concentrated near the upper center.
- Translucent aqua polycarbonate near the far left and right edges.
- A shallow row of abstract soft keys along the bottom edge.
- A few amber and coral status lamps at the perimeter.
- Low detail and low contrast behind KFPS content columns.
- No text, logos, cars, people, brands, or recognizable commercial products.

The background is separated conceptually into chassis, display light, and foreground
trim so QML can add independent movement without shifting the full image.

### Sidebar

- Reads as the removable control faceplate.
- Logo sits in a segmented circular dial with an amber index mark.
- Active navigation gains a cyan display bar and three animated meter segments.
- The bottom supporter panel resembles a labeled cartridge bay.

### Workspace

- Panels resemble smoked display modules nested into the chassis.
- Panels use clean rounded glass and one restrained cyan locator tick.
- Standard outlines, inner borders, nine-slice edges, and tiled rails are suppressed
  so corners never expose competing geometries.
- Preview wells are deeper and less reflective than command panels.
- Inputs resemble recessed soft keys rather than glossy browser fields.

### Header

- Announcement ticker becomes a narrow dot-matrix information window.
- Version pill becomes an equipment serial/status display.
- Supporter pill becomes a removable holographic authentication tab.

## Motion storyboard

### Scene A: settled idle

Duration: continuous, with events separated by long rests.

- Display illumination changes by less than four percent over 12 seconds.
- A thin cyan scan line crosses the upper display once every 18 to 26 seconds.
- Three tiny equalizer segments near the upper-right edge perform one calm sequence,
  then remain still for at least 14 seconds.
- No object rotates, bounces, or follows a short obvious loop.

### Scene B: page navigation

Total duration: 360 ms.

1. `0-70 ms`: current content dims to 72 percent and shifts two pixels backward.
2. `45-230 ms`: a narrow translucent faceplate band travels left to right.
3. `90-280 ms`: new content resolves behind the band with a six-pixel horizontal settle.
4. `230-360 ms`: cyan and amber trailing ticks collapse into the right edge.

The transition does not delay navigation or block interaction beyond the existing page
load. Reduced motion uses a 110 ms crossfade.

### Scene C: primary button hover

Total duration: 210 ms, one shot.

- Button rises one pixel using the existing physical motion.
- A narrow cyan-white refraction travels across the acrylic cap.
- Three lower meter marks illuminate in sequence.
- The effect does not repeat while the pointer remains stationary.

### Scene D: primary button press

Total duration: 95 ms down, 130 ms release.

- Cap travel increases slightly while the lower lip darkens toward deep aqua.
- Meter marks collapse simultaneously.
- Release produces no elastic overshoot.

### Scene E: navigation selection

Total duration: 260 ms.

- Cyan fill enters from the leading edge.
- The icon resolves from silver to display white.
- Three signal segments illuminate from left to right.
- The previously active item fades directly without playing the full entrance backward.

### Scene F: panel focus

Total duration: 300 ms, one shot.

- The top locator tick slides 18 pixels and settles.
- A very low-opacity scan reflection crosses only the focused or hovered panel.
- Static panels do not animate continuously.

### Scene G: supporter authentication tab

Ambient cycle: 9 seconds with a 12-second rest.

- A thin spectral highlight crosses the tab at a shallow angle.
- Tiny cyan, amber, and coral edge fragments shift by no more than two pixels.
- Cursor hover produces a restrained two-axis tilt capped at 1.5 degrees.
- Reduced motion shows the centered highlight with no tilt.

### Scene H: status and progress

- Ready state uses one steady lime indicator.
- Checking state advances four amber segments at 420 ms per step.
- Success fills all segments lime, holds for 700 ms, then returns to steady state.
- Failure flashes coral twice over 900 ms, then remains solid. No infinite fast blink.

### Scene I: chassis telemetry

- A cyan data pulse crosses the sidebar seam, outside rail, and lower bus in one calm
  sequence, followed by a long rest.
- The upper status triad performs a brief double pulse every several seconds.
- Panel and input micro LEDs respond to hover, focus, or selection and then settle.
- All telemetry is drawn above translucent content surfaces but remains outside reading
  regions and never accepts pointer input.

## Original asset manifest

| Asset | Intended size | Format | Notes |
| --- | ---: | --- | --- |
| `overdrive-backdrop.png` | 1672 x 941 | PNG | Original wide hardware environment |
| `overdrive-panel-texture.png` | 1254 x 1254 | PNG | Smoked molded-polycarbonate microtexture |
| `overdrive-button-lens.svg` | 512 x 128 viewbox | SVG | Shallow control-safe acrylic reflections |
| `overdrive-edge-frame.svg` | 256 x 256 viewbox | SVG | Retained source study; intentionally not rendered |
| `overdrive-trim-strip.svg` | 1024 x 16 viewbox | SVG | Retained source study; intentionally not rendered |
| `overdrive-logo-dial.svg` | 512 x 512 viewbox | SVG | Original dial surround; KFPS mark stays separate |
| `overdrive-glint.svg` | 512 x 128 viewbox | SVG | Restrained panel glint texture |

Generated assets must contain no text, logos, watermarks, recognizable products, or
interface controls copied from references. Asset contrast is evaluated beneath real KFPS
panels rather than in isolation.

## Theme-system integration

The implementation remains capability-driven:

- `backdropComponentFile` selects a custom backdrop through a generic loader.
- `pageTransitionComponentFile` selects a custom transition overlay.
- Generic animation tokens control sweep visibility, speed, width, and color.
- Generic signal-segment tokens control panel, button, and navigation accents.
- Existing themes provide empty component paths and disabled capability values.
- No page or shared component checks for the string `Overdrive 200X`.

Custom components implement stable contracts:

```text
Backdrop: fills its parent and observes ambientMotion, reducedMotion, screenshotMode
Transition: exposes play() and remains non-interactive
Accent: observes active, hovered, pressed, reducedMotion, screenshotMode
```

## Performance budget

- Maintain 60 FPS at 1760 x 1040 on the current development machine.
- Maintain usable interaction at 1360 x 820 with software rendering.
- No continuously animated full-window blur.
- No more than three moving full-width translucent elements at once.
- Pause ambient loops when the application is inactive, minimized, or in screenshot mode.
- Use transforms and opacity for motion; avoid changing complex layout geometry per frame.
- Keep decoded theme textures below approximately 80 MB combined.
- Reuse textures through QML image caching.

## Reduced motion and capture behavior

- Reduced motion disables parallax, scan travel, tilt, and sequential meter animation.
- It preserves clear static active, hover, pressed, success, warning, and failure states.
- Screenshot mode freezes every ambient element at a deliberately composed frame.
- Automated captures must be deterministic between runs.

## Validation matrix

Visual captures:

- Create, Outputs, Community, Editor, Help, Settings, Update, and Credits.
- 1360 x 820, 1760 x 1040, 1920 x 1080, and 2560 x 1440.
- Normal motion, reduced motion, glass disabled, and compact sidebar.
- Empty, loading, success, warning, error, hover, focus, and pressed states where practical.

Acceptance criteria:

- No text loses contrast against a custom asset.
- No animation shifts layout or delays a command.
- No animation runs rapidly forever.
- No theme-specific branch appears outside the theme facade or generic component loader.
- Every palette still passes the exact typed contract test.
- All existing UI tests and layout audits pass.
- Asset paths resolve in bundled and unbundled launches.

## Staging verification

The completed DIRTY implementation and military-science-fiction polish pass were checked
on 2026-07-20:

- 134 Python/QML service tests passed; one opt-in local Worker integration test was
  skipped as designed.
- The literal-color and exact typed-palette contract audits passed.
- Overdrive passed 66 page/size layout cases across 100 and 135 percent UI scale with no
  clipped, zero-sized, or undersized visible control.
- The interaction audit exercised 320 visible controls across all 11 pages. No hover
  artwork escaped a control boundary, and every audited control retained hover and press
  feedback.
- All 11 Overdrive pages were captured and visually reviewed at 1360 x 820. Create,
  Help, and Settings were additionally reviewed at 135 percent UI scale.
- Carbon Dark, Night Blossom, and Patron's Atelier Create-page regression captures were
  visually unchanged after the shared control hooks were added.
- An eight-frame live-motion capture verified the perimeter data sweep, display scan,
  status pulse, and deterministic screenshot composition.
- A controlled 18.9-second warm motion profile used 5.8 percent of one CPU core and
  167.9 MB with Qt's software renderer. Panel and button telemetry remains event-driven;
  only the sparse backdrop and perimeter phases run while idle.
