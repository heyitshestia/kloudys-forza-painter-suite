# Night City 2077 Theme

## Intent

Night City 2077 is an original KFPS theme built from a documented study of
high-resolution science-fiction game UI references. It recreates the visual
grammar with KFPS-owned geometry and assets rather than shipping captured
screens, logos, characters, icons, or proprietary fonts.

The theme is public. Supporter and non-supporter footer messaging continues to
come from the shared Sidebar logic.

## Visual System

- Darkest-blue work field: `#0e0e17`.
- Red structural rails and command states: `#f75049`.
- Cyan focus, selection, and connection signals: `#5ef6ff`.
- White and neutral-grey information text.
- Rajdhani Bold for display text and Rajdhani Medium/Regular for interface and
  diagnostic text under SIL OFL 1.1.
- Asymmetric nine-point command silhouettes with interrupted edges.
- Structural groups float directly over the workspace and use open corner
  guides instead of filled cards. Only true dialogs, fields, commands, and
  repeated content tiles retain enclosed surfaces.
- Red and cyan typography is mixed by role: red for route and warning labels,
  cyan for data, inactive navigation, and acquisition state.
- Flat, high-contrast surfaces. No rounded glass islands or soft pill buttons.

## Depth And Telemetry

The backdrop is made from independent low-contrast depth planes, perspective
wire geometry, route traces, and a restrained scan field. The planes drift at
different speeds so the workspace has depth without moving its controls. Two
vertical glyph rails scroll independently at the viewport edges and replace
the generic rows of repeated indicator lights used by other themes.

The top-to-bottom acquisition field takes several seconds to cross the window
and then remains idle for a longer interval. Its bloom stays below foreground
frame intensity so it cannot wash through text or editable values.

Structural frames use a soft outer bloom around a sharp one-pixel red or cyan
core. Bloom is clipped to its owning control, so hover and focus never spill
across neighboring content. True popups use `KfpsPopupSurface` for an enclosed,
readable signal frame while page-level groups remain open.

The visual hierarchy has three explicit levels. Major floating page groups use
one restrained upper-left route rail, without a mirrored lower-right ornament.
Minor and repeated panels stay undecorated so lists do not become a wall of
duplicate brackets. The live-status channel, previews, dialogs, editable fields,
and confirmation readouts are fully enclosed because their bounds carry useful
interaction or content meaning.

## Interaction Storyboard

Idle controls use a translucent dark plate with sparse red status marks and a
soft multi-pass edge light. Hover performs a 70-250 ms acquisition pass: the
border energizes, a cyan scanner crosses the control, a registration echo
briefly offsets from the red plate, and the acquisition rail resolves. Pressing
a command changes the plate to solid red, moves it down by one pixel, and swaps
the label to dark ink. Focus is always cyan and does not depend on hover.

Page navigation runs a 420 ms horizontal signal teardown and rebuild. Ambient
scan passes and diagnostic faults are deliberately infrequent. Text and hit
targets never move during a glitch.

## Motion Controls

- Reduce motion removes displacement, transition sweeps, and animated state
  settling.
- Ambient motion disables idle scans, heartbeat sequences, and rare faults.
- Glass and effects disables chromatic registration echoes and glitch slices.
- Screenshot mode freezes every decorative sequence at a deterministic frame.

## Easter Eggs

The foreground diagnostic bus rotates a few low-contrast KFPS messages. They
are visual telemetry only and never intercept input. The messages are disabled
with ambient motion and remain nonessential to operation.

## Maintenance Contract

Shared components branch only on semantic tokens such as
`Theme.angularControlsEnabled`; they never compare concrete theme names. Every
palette implements the same typed token contract. New controls should use
`AngularControlFrame` where a rectangular fallback would otherwise leak into
this theme. Structural containers should set panel intent explicitly: floating
page groups use the open-panel path, while dialogs and menus request an enclosed
panel. `Theme.glyphRailsEnabled` suppresses generic equipment ticks in favor of
the theme-owned scrolling telemetry.

Editable text uses a slightly larger semibold face when technical typography
is active. This is intentionally scoped to the capability token so other theme
metrics and font weights remain unchanged.
