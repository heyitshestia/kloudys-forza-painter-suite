# KFPS theme system

Themes are presentation data. Workflow logic and page structure must not depend on a
concrete theme name.

## Ownership

- `qml/Kfps/Theme/Palette*.qml` owns colors, visual-effect values, artwork paths,
  icon treatment, and supporter metadata.
- `qml/Kfps/Theme/Theme.qml` selects an allowed palette and exposes the stable
  semantic `Theme.*` API consumed by the rest of QML.
- `src/kfps_ui/theme_catalog.py` owns persistence validation, Settings ordering,
  supporter-gated visibility, and optional preferences applied when entering a theme.
- Reusable components and pages consume semantic tokens. They must not inspect
  `Theme.themeName` or add `Theme.activeSomePreset` branches.

## Palette contract

Every palette implements the same typed property contract. The contract test compares
all palette property names and types, so a missing or misspelled token fails validation.

The required metadata includes:

- `name` - exact user-facing name, matching the Python registry.
- `supporterOnly` - whether QML may activate it without supporter access.
- `iconFolder`, `iconColorize`, and `iconTint` - generic icon treatment.
- `terminalMode` and `iconGlyphsVisible` - opt into the flat command-surface
  treatment and suppress graphical icon slots without checking a concrete theme name.
- `backdropComponentFile`, `foregroundComponentFile`, and
  `pageTransitionComponentFile` - optional custom presentation components loaded
  through stable shell hosts. Foregrounds are non-interactive and reserved for
  perimeter hardware detail that must remain above translucent content glass.
- Capability booleans such as `controlSignalEnabled` and `panelLocatorEnabled` -
  opt-in behavior consumed without concrete-theme checks.
- `customFrameExclusive` and `customFrameRadius` - let a theme make its nine-slice
  frame the sole structural outline instead of stacking it over legacy borders.

Optional visual features remain represented by the shared contract. Disable one with
an empty asset path, `false`, or zero opacity instead of branching in a component.

## Adding a theme

1. Copy an existing `Palette*.qml` file and change values without removing tokens.
2. Give it unique `name` metadata and set `supporterOnly` deliberately.
3. Register the QML type in `qml/Kfps/Theme/qmldir`.
4. Instantiate it and add it to `palettes` in `Theme.qml`.
5. Add one matching `ThemePreset` entry in `theme_catalog.py`, including deliberate
   supporter access and any theme-entry preference values.
6. Put any original assets under a dedicated `KFPS.UI/assets/themes/<theme>/` folder.
7. Run the automated checks below.
8. Capture every major page in the new theme at the standard desktop and compact sizes.

The Python and QML supporter flags intentionally exist on both sides: Python controls
what Settings offers, while QML protects runtime activation and falls back to the
default palette. Tests enforce that the two values agree.

## Validation

From the project root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python KFPS.UI\tools\audit_theme_literals.py
python KFPS.UI\tests\test_theme_catalog.py
python KFPS.UI\tests\test_qml_refinement.py
python KFPS.UI\tools\capture_pages.py --theme "Night Blossom" --theme "Command Prompt" --theme "Windows 94" --theme "Patron's Atelier" --theme "Carbon Dark" --theme "Overdrive 200X"
python KFPS.UI\tools\audit_layout_matrix.py --theme "Night Blossom" --size 1360x820
```

`capture_pages.py` accepts repeatable `--theme`, `--page`, and `--size` options. Explicit
theme captures are stored in separate slugged folders and do not change saved settings.
Run the layout audit once for each registered theme before release.

The literal audit excludes `SourceDownloadBlocker.qml` because that full-window red
warning is intentionally independent from selectable themes.

## Token naming

Name tokens by purpose rather than appearance:

- `previewSurface`, not `darkPreview`
- `rowHover`, not `pinkHover`
- `primaryButtonTop`, not `goldButtonTop`
- `navActiveTop`, not `carbonNavTop`

When a new design needs behavior the contract cannot express, add a generic capability
token to every palette and consume that token in the shared component.

## Overdrive 200X

Overdrive 200X is the first theme to opt into custom backdrop and transition components.
Its shared-component effects remain controlled by generic capability and signal tokens;
no reusable control checks the Overdrive name. The research and motion decisions live in
`OVERDRIVE_THEME_STORYBOARD.md`, and asset provenance is recorded beside the assets.

Overdrive also enables `customFrameExclusive` with an empty `panelEdgeFile`. Structural
panels and header status modules therefore use clean, rounded, borderless glass without
the standard outline, inner outline, nine-slice edge, or tiled trim rail. Command
controls use the shallow button-lens treatment inside hard clipping bounds. Semantic
circles and tracks such as status lamps, checkboxes, switches, and sliders retain their
familiar control geometry.

The custom button lens is painted after generic backdrop blur and glass shading so its
authored edge and embedded marks stay legible. A non-interactive foreground component
adds sparse chassis-seam telemetry, while shared controls expose panel and focus-state
micro LEDs through generic equipment capability tokens.

## Command Prompt

Command Prompt is a public theme. It deliberately uses no decorative raster or vector
assets: the shell is pure black, all active QML radii resolve to zero through
`Theme.corner()`, structural glass panels become one continuous borderless surface,
and command controls use square outlines with inverted hover selection. The navigation
and title shell use prompt-oriented text while the application workflow remains shared.

The Settings-only `terminalGreenText` preference switches the monochrome terminal ink
between white and phosphor green. The preference may stay enabled while another theme
is active, but only `PaletteCommandPrompt` consumes it. `iconGlyphsVisible` is false for
this palette so shared icon components collapse their layout slots instead of loading
or leaving gaps for graphical symbols.

## Windows 94

Windows 94 is a supporter theme built from the fixed Windows 9x face, light, highlight,
shadow, dark, navy, blue, and desktop colors. Shared controls use a generic
`classicMode` capability to switch to square geometry, four-color raised and recessed
bevels, dotted keyboard focus, direct black icons, and short classic page transitions.
The packaged W95FA font is licensed under the SIL Open Font License; the icon set is a
mechanical monochrome treatment of KFPS's existing original SVG geometry.

On entry, its `ThemePreset` sets reduced motion, ambient background motion, and glass
effects to off in one saved update. Users may change those options afterward; their
choices remain persisted until they explicitly enter Windows 94 again.
