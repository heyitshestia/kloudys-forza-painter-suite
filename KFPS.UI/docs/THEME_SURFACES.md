# Optional Native Theme Surfaces

The shared shell keeps ownership of navigation, labels, focus and click actions.
A theme can replace decoration without forking those workflows. RX-93 is the
first consumer of these optional hooks; the other palettes leave them empty.

## Surface Hooks

`ThemeSurface.qml` loads a theme-owned QML component from a palette's relative
component path. Keep this component visual only so it does not intercept input.

| Palette property | Component receives |
| --- | --- |
| `controlSurfaceComponentFile` | `control` and `controlKind` (`primary`, `ghost`, `nav`) |
| `panelSurfaceComponentFile` | `panel` |
| `sidebarSurfaceComponentFile` | `sidebar` |
| `sidebarHeaderComponentFile` | `sidebar` |
| `titleBarContentComponentFile` | Available geometry and attached window |

The control owner supplies normal Qt state such as enabled, pressed, hovered and
focus. Keep labels and event handlers in the shared controls. Primary, ghost and
navigation buttons instantiate their legacy decoration only when the optional
hook is empty or fails to load. This avoids constructing unused effect trees.

## Layout Metrics

`chromeMetrics` is an optional palette object. `Theme.chromeMetric(name, fallback)`
accepts finite nonnegative numbers and otherwise uses the shared default.

- Frame: `frameScale`, `compactFrameScale`.
- Title bar: `titleHeight`, `compactTitleHeight`.
- Insets: `leftInset`, `rightInset`, `bottomInset` and their `compact` variants.
- Sidebar header: `sidebarHeaderHeight`, `compactSidebarHeaderHeight`.
- Window controls: `windowButtonsTopInset`, `compactWindowButtonsTopInset`,
  `windowButtonsHeight`, `windowButtonsIconLift`, `compactWindowButtonsIconLift`.

RX-93 uses 30-pixel window controls, starting 3 pixels below the top edge at
desktop size and at the top edge in compact mode. Compact symbols receive an
additional 8-pixel upward offset without reducing their click targets. These values keep the glyphs
above the chassis's white armor stripe. Empty metrics preserve other themes'
original title-bar layout. Do not add concrete theme-name branches to the shell.

`Theme.px()` rounds to whole pixels. Do not use it directly on fractional image
scales; round a dimension or apply the scale after converting a whole dimension.

## Assets And Motion

Store runtime artwork under `KFPS.UI/assets/themes/<theme>/`, with theme-owned
QML under `KFPS.UI/qml/themes/<theme>/`. Use local nine-slice material parts for
resizable controls, not a picture of an entire interface with text baked in.
Keep reference artwork and validation captures in documentation, out of runtime.

Static decoration does not need a continuously running animation. RX-93's small
ambient details update at most 20 times per second, with guards for reduced
motion, the ambient toggle, inactive/minimized windows and screenshot mode.
Pointer feedback retains short native animations independently of ambient motion.

## Verification

Run `py -3.12 -m unittest discover -s KFPS.UI/tests -p '*theme*.py'`.
`tools/preview_rx93.py` launches the real native shell with disposable settings;
it does not modify the installed application's data. Use `KFPS_RX93_PUBLIC=1`
to verify the theme without supporter-preview entitlement. Captures must wait for
the current page loader and theme images to become ready. Keep visual inspection,
input checks and performance measurements distinct from static contract tests.
