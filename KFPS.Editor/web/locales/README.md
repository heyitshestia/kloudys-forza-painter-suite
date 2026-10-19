# Editor Localization Maintenance

`en.json`, `ko.json` and `ja.json` are the authoritative English, Korean and Japanese catalogs. Edit
their values, not their keys. The original English keys are stable identifiers;
changing an English caption does not require renaming the key in code or other catalogs.
`en.js`, `ko.js` and `ja.js` are generated offline browser packs. The native Python window
reads the same JSON catalogs. No translation service, font download or new runtime
dependency is required. Missing localized text falls back to English, then the key.

## Catalog structure

`messages`: stable English source key to display text. Positional placeholders
`{0}`, `{1}`, etc. must retain their meaning, although translations may reorder them.
Only documented English plural-suffix slots in `ko.json` or `ja.json`'s `pluralOmissions` may
be omitted. Identical technical captions (Ctrl, X, file extensions) are intentional.

`html`: complete trusted inline-help fragments, translated as a unit for natural sentence order. Preserve markup semantics and never insert user input here.

`families`: original resource-family identifier → localized caption. Option values and shape resource identifiers must remain unchanged.

`shapeLabels`: original shape/glyph description → localized display label. Keep `shapeDisplayName()` and serialization English/identifier-safe; use `localizedShapeDisplayName()` only for presentation.

## Editing rules

Use `KfpsI18n.t("English sentence {0}.", value)` for normal UI messages. Values are opaque: do not translate names, recursively format them, or remove existing HTML escaping. For controlled enum labels at a display boundary, use `KfpsI18n.term(label)`. For known backend diagnostics, `KfpsI18n.error()` translates the first message line while retaining technical stack details. Unknown errors retain their original text. `KfpsI18n.history()` is only for generated history reasons, never user content.

Static HTML is translated once after authoritative preferences load. There is no mutation observer and no translation of scene objects, edited text, or export payloads. Do not call `applyStatic()` over already-edited dynamic/user content. Do not translate `data-tool`, input/option values, protocol names, filesystem paths, or JSON keys.

## Updating Any Language

From the repository root:

```sh
python KFPS.Editor/web/locales/manage.py sync
```

This adds new explicit `KfpsI18n.t("...")` / `tr("...")` keys, native translated
messages, static text and attributes to all catalogs without deleting old keys.
New English defaults to the source key; new Korean/Japanese entries are empty and need
translation. Use double-quoted literal keys in JavaScript. Computed keys,
controlled enums, new whole-HTML help blocks and shape/family captions must be
added manually to all catalogs. Do not translate arbitrary runtime strings.
The persistence worker/facade's literal `failure("...")` and `new Error("...")`
diagnostics are also collected; the main editor translates these with
`KfpsI18n.error()` without localizing protocol fields or saved artwork.

Edit the values in `en.json`, `ko.json` and `ja.json`, then run:

```sh
python KFPS.Editor/web/locales/manage.py build
python KFPS.Editor/web/locales/manage.py check
node KFPS.Editor/web/tests/editor-i18n.node.js
python KFPS.Editor/web/tests/editor-localization.test.py
python KFPS.Editor/web/tests/editor-japanese-catalog.test.py
node KFPS.Editor/web/tests/editor-japanese-catalog.node.js
python KFPS.Editor/web/tests/editor-localization-native.py
node KFPS.Editor/web/tests/editor-core.node.js
node KFPS.Editor/web/tests/editor-preferences.node.js
node KFPS.Editor/web/tests/editor-shell.node.js
```

`check` is read-only and runs in the existing quality workflow. It rejects missing
translations, catalog/source key drift, changed placeholders, modified HTML
controls/links/IDs and stale generated packs. Commit the three JSON catalogs and
their generated JS packs together when the review is approved. `build
--allow-missing` is for local drafts only; CI always requires complete translations.
The old `tests/build-locale.py [--check]` command delegates to the same tool.
`build --language ja` validates all catalogs but writes only `ja.js`, useful when
catalog owners are working concurrently. It does not waive source coverage.

## Japanese Catalog Review

Japanese uses the same schema and stable keys, with `locale: "ja"` and
`name: "日本語"`. The catalog covers messages, whole HTML help fragments, all
35 resource families and all 764 native shape/glyph labels. Native glyph names
identify the original Latin glyphs; localization does not add Japanese glyph
geometry or alter artwork, resource IDs, or saved user names.

Terminology: レイヤー (layer), 参照画像 (reference image), シアー (skew),
ネイティブ図形 (native shape), 書き出し (export), 読み込み (import).
The focused Japanese test checks exact EN key parity, nonempty Japanese prose,
placeholder multiplicity, documented plural omissions, protected HTML attributes,
font/glyph identifiers and generated-pack parity. Unchanged shortcuts, units,
file extensions and product names are intentional, explicitly allowlisted cases.
These checks do not certify native-speaker phrasing, font coverage or visual fit.
Catalog checks are separate from actual native/browser qualification; they cannot
establish selector behavior, rendering or persistence alone. The accepted installed
workflow evidence is summarized below without extending it to physical IME/DPI.
The redesign uses a local `t(...)` alias and dynamic button/menu label arrays.
Those are outside the general double-quoted-call extractor; the focused Japanese
catalog test also inventories the current workspace/docking literals and reviewed
dynamic menu labels in all three languages. Add newly introduced dynamic labels
explicitly. A green extractor check is not proof that arbitrary runtime text is
localized.

## Language Selection And Startup

The compact dropdown is at the lower left. On first use, Windows display language
(not regional number/date formatting) selects Japanese, Korean or English; a saved choice
takes priority. Browser-only use falls back to `navigator.language`. Changing the
dropdown saves a preference but never reloads or alters unsaved artwork. Save the
project and reopen the editor to apply it. `?lang=en|ko|ja` is a temporary QA override.

The initial shortcut guide is the retained automatic first-use tutorial. A
separate release announcement may appear once across KFPS, the editor and Studio
only within seven days of its fixed publication timestamp. It uses Windows
display language (Korean/Japanese, otherwise English), independently of the saved
editor language, and is inert for unpublished or expired content. In `editor.js`, startup
calls `maybeShowStartupHelp()` and then `continueEditorStartup()` after the guide
closes (or immediately when already confirmed). Continuation handles recovery,
New Canvas or JSON browsing without calling the former sharing, language-arrow
or modernization-update notice helpers. Explicit project/tutorial modes keep
their own startup behavior; ordinary safety/recovery prompts are not removed.

The following legacy keys remain in the preference allowlist, but are inert for
automatic startup: `kloudyFabricProjectSharingAcknowledged`,
`kloudyFabricLanguageNoticeAcknowledged` and
`kloudyFabricEditorUpdateAcknowledged`. Existing values are not deleted or
manufactured; missing/stale values do not reopen the retired notices. Their old
dialog markup, helpers and translations remain for compatibility, not as active
first-run requirements. Do not change or clear these keys to reset the tutorial;
use KFPS's Reset Editor Tutorial control for the retained shortcut guide.

## Native Regression Coverage

Coverage below describes the current test source, not a new run performed for
this documentation update. Use the existing real-host regression runners with
disposable profiles; these checks write projects/preferences/assets, so never
point them at a personal profile.

- `../tests/editor-startup-tips.node.js` checks six continuation branches without
  calling the retired notices, and verifies that initial-help sequencing remains.
- `../tests/regression-startup-tips.js` checks the real page's initial guide,
  acknowledgement/reload, absent/stale legacy flags, explicit Help/Shortcuts and
  ordinary unsaved New cancellation/acceptance. It requires a fresh profile.
- `../tests/regression-language-switch.js` defaults to EN/KO/JA, four themes and
  two viewport sizes. It checks that the retired notice stays closed, failed
  language writes roll back, successful changes preserve unsaved artwork, and
  Save As works with Enter. It deliberately leaves Korean saved for restart.
- `../tests/regression-language-restart.js` verifies a full-process restart uses
  that Korean preference while the old notice key remains absent and its dialog
  closed. It no longer tests acknowledging the retired language notice.
- `../tests/regression-korean-localization.js` covers Korean assets, shape IDs/
  names, bilingual search, numeric validation, injected IME guards, recovery,
  help and tours; it is not a Japanese-specific UI test.
- `../tests/editor-japanese-catalog.test.py` and
  `../tests/editor-japanese-catalog.node.js` cover all catalog sections,
  placeholders/opaque values, source-key inventory and generated-pack parity.
  The older `editor-localization-native.py` dialog unit loop covers EN/KO only;
  do not cite it alone as three-language native qualification.

The accepted 2026-10-19 installed gate separately includes native/Chrome
3,000-shape compatibility, Japanese/custom-theme/shortcut consumption and
restart/recovery. Real Studio source-return checks used five native and five fresh
Chrome 2D hosts with Japanese/custom settings, exact apply/undo/reopen and unchanged
canonical settings. Detailed installed/source-return and Chrome recovery records
are retained in private release qualification evidence; they are not public
source dependencies or required packaged assets. The portable synthetic tests
listed above describe the reproducible source coverage. Earlier
failed runs remain preserved. Injected composition checks and emulated viewport
sizes do not certify physical Windows IME input, monitor DPI or every installed
font. No universal smoothness or game-export acceptance follows from them.

The supplied mocked browser harness is not part of the source integration.
Technical checks cannot judge idiomatic Korean or Japanese; native-speaker review is still
useful. Native font/glyph artwork, shape resources, internal shape names, IDs,
project/export schemas and user-supplied names are not localized or converted.
