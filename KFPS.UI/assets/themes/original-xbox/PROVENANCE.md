# Original Xbox Theme Assets

`medallion.png` is an original generated bitmap made on 2026-10-24 with the
built-in OpenAI image-generation tool for this KFPS interface. It is not extracted
from Microsoft software. No Microsoft logo, sound or font is bundled.

The theme reuses KFPS's existing icons and licensed Barlow fonts from the RX-93
asset directory; their licence files remain there unchanged.

The chamfered KFPS wordmark in `qml/themes/xbox/XboxWordmark.qml` was drawn as
original geometric letter paths on 2026-10-25. It uses theme colors and the
existing Qt Canvas renderer, with no downloaded font or traced Microsoft logo.

The curved background grid, green currents, linked menu shapes and transitions
are original procedural theme code in `qml/themes/xbox/`. They use existing KFPS
theme colors and Qt rendering, not extracted dashboard textures, shaders, models,
audio or third-party source code. Historical dashboard material was consulted as
a visual reference only; source links and decisions are in the isolated workspace's
`docs/DESIGN.md`.

## Depth Revision: Core

`core.png` is a second original bitmap generated with the built-in OpenAI image
tool on 2026-10-24 after the user's reference review. It replaces the metal-framed
medallion in the active dashboard and sidebar. The earlier medallion is retained
as the first-pass asset, not used by the revised reactor. Both have genuine alpha.
The moving front/rear ribbons are procedural QML/Canvas layers, not baked animation.

Source output: `exec-cf20c38a-1521-4489-a895-bf72582efeec.png`.

Prompt: Use case: stylized-concept. Asset type: production bitmap core for a faithful
original-2001-console-dashboard-inspired KFPS interface, not a full mockup. A single
luminous, translucent green glass/plasma spherical core, straight on, nearly circular
organic silhouette, yellow-lime energy concentrated in its center fading to deep
emerald transparent glass at its perimeter. Restrained early-2000s realtime-rendered
aesthetic, simple smooth flowing glass membranes inside, asymmetric glossy highlights
upper left, subtle uneven folded glass edges, genuine volume and translucency. NO
metal, NO chrome, NO bezel, NO circular machinery, NO rigid ring, NO surrounding orbit
bands (those will be animated by software), NO sparks or particles, NO text or symbols,
NO Xbox logo, NO letters. Square composition, subject fills central 70 percent leaving
generous fully transparent margin on all sides. Alpha transparent background. This is
an original visual asset; the software will overlay KFPS type and procedural animated
orbit bands. Keep surface simple enough to animate over it, do not produce a busy
marbled stone texture.

## Prompt

Use case: stylized-concept. Asset type: a square bitmap material emblem for an optional original 2001 Xbox-inspired KFPS desktop software skin. Create a centered circular futuristic machined graphite/chrome medallion, with dark translucent green glass center, fine concentric mechanical grooves and a thin phosphor lime-green lit inner ring. Straight on orthographic view, perfect circular silhouette, restrained clean early-2000s console dashboard pre-rendered 3D style. Center glass has abstract subtle fluid green marbling and NO symbol or lettering; KFPS lettering will be rendered by software over it. Outer ring metallic silver/graphite and physically tangible, no screws, no clutter. Object occupies 85% of square. Real alpha transparent background all around outside the circular edge. No text, no Xbox logos, no symbols, no menu, no scene, no particles, no detached lights, no bloom bleeding beyond the silhouette. Crisp usable production UI asset; readable at 128 pixels.
