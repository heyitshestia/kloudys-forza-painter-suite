# KFPS theme system

The app should treat theme as presentation data, not workflow logic.

## Ownership boundary

- QML palettes define colors, artwork file names, opacity values, and component-surface tokens.
- QML components consume only semantic `Theme.*` properties and functions.
- Python validates and persists theme names, and exposes available choices to Settings.
- Pages should not branch on a theme name. If a page needs a color, add a semantic token.

## QML structure

`KFPS.UI/qml/Kfps/Theme/Theme.qml` remains the public singleton used by pages and components.
It delegates concrete palette values to files such as:

- `PaletteNightBlossom.qml`
- `PaletteKofiCherry.qml`

This keeps imports stable:

```qml
import Kfps.Theme 1.0

Rectangle {
    color: Theme.previewSurface
    border.color: Theme.borderStrong
}
```

## Python structure

`KFPS.UI/src/kfps_ui/theme_catalog.py` is the Python registry used by settings and supporter unlocks.
Add theme names there when a palette becomes selectable.

```python
THEME_PRESETS = (
    ThemePreset("Night Blossom"),
    ThemePreset("New Public Theme"),
    ThemePreset("New Supporter Theme", supporter_only=True),
)
```

## New-theme checklist

1. Add `PaletteName.qml` beside the existing palettes.
2. Add it to `qmldir`.
3. Instantiate it in `Theme.qml`.
4. Route `activeThemeName` to the palette.
5. Add the name to `theme_catalog.py`.
6. Add any assets to `KFPS.UI/assets/`.
7. Run `python KFPS.UI/tools/audit_theme_literals.py`.
8. Run layout/screenshot audits at the existing validation sizes.

## Token guidance

Use tokens named for purpose, not color:

- `previewSurface`, not `darkRedPreview`
- `rowHover`, not `pinkHover`
- `primaryButtonTop`, not `buttonPinkTop`
- `navActiveTop`, not `goldNavTop`

A component should never check `Theme.themeName` directly. Only `Theme.qml` should select a palette.


## Codex integration handoff

The root `CODEX_HANDOFF.md` file is written for Codex or another local coding agent. It includes the recommended prompt, integration order, validation commands, manual smoke checks, and success criteria. Keep this document as the long-term theme-system reference after integration.
