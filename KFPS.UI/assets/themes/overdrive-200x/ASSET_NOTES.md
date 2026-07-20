# Overdrive 200X asset notes

All files in this directory were created specifically for KFPS. No reference-site
images, commercial product photography, logos, labels, or manufacturer artwork are
included.

- `overdrive-backdrop.png` is an original generated console environment. It contains
  no text or branding and is used only as the full-window hardware chassis.
- `overdrive-panel-texture.png` is an original generated smoked-polycarbonate material
  sample used at low opacity.
- The SVG frame, trim, lens, dial, and glint assets were authored for this theme from
  simple geometric primitives and gradients.
- The edge frame and standalone trim strip remain source material but are intentionally
  not layered over panels or controls. Overdrive uses rounded borderless panels and the
  shallow button lens instead.
- The button lens is drawn above generic glass shading but inside each control's hard
  clipping boundary. This preserves its authored shell without allowing hover artwork
  to escape the button.
- The existing transparent KFPS logo remains the source mark. `ThemedLogo.qml`
  colorizes it at runtime so its original alpha and geometry are preserved.

An experimental generated logo recolor was rejected because it rendered a checkerboard
instead of real transparency. It is not present in the project or referenced by KFPS.
