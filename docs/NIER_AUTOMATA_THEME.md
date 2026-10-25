# NieR Automata Theme

An Automata-inspired optional theme for KFPS, Vinyl Editor and Livery Studio.
It uses warm neutral surfaces, charcoal controls, staff-line ornament and
restrained diagonal/triangle entrances. Artwork and car render colours remain
unfiltered.

Introduced in 3.1.119 through the normal updater; no new bundled release.

## Controls

Select **NieR Automata** in KFPS Settings, the Vinyl Editor theme selector or
Studio Appearance. The native main menu groups existing routes into Workspace,
Library and System. Left/Right changes category, Up/Down selects an entry, and
Enter opens it. The menu control returns to the hub; Credits is under System.

The main content reveal lasts 620 ms and never captures input. Native title-bar
controls remain available. Reduced Motion settles the animation immediately.
The web editors use short, bounded theme-only dialog transitions.

## Compatibility

- Native and Chrome editor modes share the same web theme.
- Existing palette meanings and the 33-key web theme format are preserved.
- The web base ID is `builtin:nier`, leaving legacy custom IDs untouched.
- Custom theme editing, preview/cancel, saving/loading and persistence remain.
- No changes to graphics backends, document formats, shortcuts, grouping,
  game integration or import/export behaviour are part of this theme.
- Switching to another theme restores that theme's existing appearance.

The theme is available without a supporter key. No game audio, extracted artwork,
game fonts or game code are bundled. Visuals are original procedural components
using KFPS's existing font and icon resources.

## Reference And Validation

Primary design reference: Hisayoshi Kijima,
[UI Design in NieR:Automata](https://www.platinumgames.com/official-blog/article/9624).

Local validation covers offscreen native navigation/scaling, native and Chrome
editor workflows, custom-theme persistence, compositor colour swatches and a
real-car Studio render/orbit test. Software/offscreen checks do not substitute
for hardware-GPU, desktop-compositing or physical multi-monitor testing.
