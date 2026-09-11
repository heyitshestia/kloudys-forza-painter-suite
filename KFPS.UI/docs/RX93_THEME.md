# RX-93 Psycho-Frame

A public native KFPS theme available in Settings without a supporter key.
This is a fan-made mechanical interpretation inspired by the RX-93 Nu Gundam,
not an official or endorsed Bandai product.

## Presentation

The theme uses reusable navy armor, ceramic keycaps, recessed metal panels,
yellow piping and restrained green lighting. Labels, focus and click behavior
remain native controls, not text embedded in a background picture. Compact
layouts retain the same workflows, with the frame scaled to preserve usable space.
Window controls sit above the white armor stripe, with full-size click targets.

Ambient details stop when the window is inactive or minimized, when ambient
motion is disabled, or when reduced motion is enabled. Their timers are limited
to 20 updates per second; this is not a whole-window frame-rate cap. Other shared
shell animation can still render at the display refresh rate.

## Ownership

- Palette and registry: `qml/Kfps/Theme/PaletteRx93PsychoFrame.qml` and
  `src/kfps_ui/theme_catalog.py`.
- Theme-owned components: `qml/themes/rx93/`.
- Runtime assets and provenance: `assets/themes/rx93-psycho-frame/`.
- Modular hooks: [Theme surfaces](THEME_SURFACES.md).

Only the selected runtime material parts are shipped. Reference mockups,
discarded concepts and private validation images are not product assets.
Fonts use the SIL Open Font License; Lucide icons use the ISC license.
See the asset directory's license files and provenance manifests.

## Testing

The theme contract suite covers public access, persistence, asset presence,
licensed-file hashes, basic contrast, motion guards and legacy-theme defaults.
`tools/preview_rx93.py` runs the actual native shell with disposable settings.
`tools/audit_rx93_native.py` exercises navigation, theme selection, window
controls and accessibility toggles. These checks do not validate game transfers
or generator performance.
