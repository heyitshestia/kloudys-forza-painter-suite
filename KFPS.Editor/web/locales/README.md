# Editor Localization Maintenance

`en.json` and `ko.json` are the authoritative English and Korean catalogs. Edit
their values, not their keys. The original English keys are stable identifiers;
changing an English caption does not require renaming the key in code or Korean.
`en.js` and `ko.js` are generated offline browser packs. The native Python window
reads the same JSON catalogs. No translation service, font download or new runtime
dependency is required. Missing Korean text falls back to English, then the key.

## Catalog structure

`messages`: stable English source key to display text. Positional placeholders
`{0}`, `{1}`, etc. must retain their meaning, although Korean may reorder them.
Only documented English plural-suffix slots in `ko.json`'s `pluralOmissions` may
be omitted. Identical technical captions (Ctrl, X, file extensions) are intentional.

`html`: complete trusted inline-help fragments, translated as a unit for natural sentence order. Preserve markup semantics and never insert user input here.

`families`: original resource-family identifier → Korean caption. Option values and shape resource identifiers must remain unchanged.

`shapeLabels`: original shape/glyph description → Korean display label. Keep `shapeDisplayName()` and serialization English/identifier-safe; use `localizedShapeDisplayName()` only for presentation.

## Editing rules

Use `KfpsI18n.t("English sentence {0}.", value)` for normal UI messages. Values are opaque: do not translate names, recursively format them, or remove existing HTML escaping. For controlled enum labels at a display boundary, use `KfpsI18n.term(label)`. For known backend diagnostics, `KfpsI18n.error()` translates the first message line while retaining technical stack details. Unknown errors retain their original text. `KfpsI18n.history()` is only for generated history reasons, never user content.

Static HTML is translated once after authoritative preferences load. There is no mutation observer and no translation of scene objects, edited text, or export payloads. Do not call `applyStatic()` over already-edited dynamic/user content. Do not translate `data-tool`, input/option values, protocol names, filesystem paths, or JSON keys.

## Updating Either Language

From the repository root:

```sh
python KFPS.Editor/web/locales/manage.py sync
```

This adds new explicit `KfpsI18n.t("...")` / `tr("...")` keys, native translated
messages, static text and attributes to both catalogs without deleting old keys.
New English defaults to the source key; new Korean entries are empty and need
translation. Use double-quoted literal keys in JavaScript. Computed keys,
controlled enums, new whole-HTML help blocks and shape/family captions must be
added manually to both catalogs. Do not translate arbitrary runtime strings.
The persistence worker/facade's literal `failure("...")` and `new Error("...")`
diagnostics are also collected; the main editor translates these with
`KfpsI18n.error()` without localizing protocol fields or saved artwork.

Edit the values in `en.json` and `ko.json`, then run:

```sh
python KFPS.Editor/web/locales/manage.py build
python KFPS.Editor/web/locales/manage.py check
node KFPS.Editor/web/tests/editor-i18n.node.js
python KFPS.Editor/web/tests/editor-localization.test.py
python KFPS.Editor/web/tests/editor-localization-native.py
node KFPS.Editor/web/tests/editor-core.node.js
node KFPS.Editor/web/tests/editor-preferences.node.js
node KFPS.Editor/web/tests/editor-shell.node.js
```

`check` is read-only and runs in the existing quality workflow. It rejects missing
translations, catalog/source key drift, changed placeholders, modified HTML
controls/links/IDs and stale generated packs. Commit the two JSON catalogs and
their generated JS packs together when the review is approved. `build
--allow-missing` is for local drafts only; CI always requires complete translations.
The old `tests/build-locale.py [--check]` command delegates to the same tool.

## Language Selection And Notice

The compact dropdown is at the lower left. On first use, Windows display language
(not regional number/date formatting) selects Korean or English; a saved choice
takes priority. Browser-only use falls back to `navigator.language`. Changing the
dropdown saves a preference but never reloads or alters unsaved artwork. Save the
project and reopen the editor to apply it. `?lang=en|ko` is a temporary QA override.

The arrow notice follows the existing introduction/project-sharing dialogs and
precedes recovery. It requires a checkbox and confirmation. Escape cannot dismiss
it; failed storage writes leave it visible and retryable. Its permanent marker is
`kloudyFabricLanguageNoticeAcknowledged: "1"` in the existing app-folder
`runtime/fabric-editor/preferences.json`. It is independent of the language
selection, favorites, projects, exports and asset library. Only explicitly
clearing that setting/profile causes the notice to appear again.

## Native Regression Coverage

The modernization update notice follows the language notice and precedes recovery.
Its English/Korean text lives in these same catalogs, with no network translation.
Checkbox plus OK persists `kloudyFabricEditorUpdateAcknowledged: "modernization-1"`
in the app-folder preferences. Keep this edition identifier stable across routine
updates and translations; it is not tied to the app version or selected language.
Viewing the notice or visiting Ko-fi does not acknowledge it. Failed writes keep
it visible and retryable. Its ordinary link uses the native host's existing
external-navigation policy and must not use `target="_blank"`, which the host
intentionally disallows. Recovery and saved projects are separate from this marker.

Use the existing live native-page regression runner with a disposable profile:
`regression-language-switch.js` covers both languages, four themes, failed writes,
acknowledgment and Save As using Enter. It leaves Korean selected.
`regression-korean-localization.js` covers assets, shape IDs/names, bilingual
search, numeric validation, IME shortcuts, recovery status, help and tours.
Restart the native process with the same profile and run
`regression-language-restart.js` to verify persisted language and acknowledgment.
These tests write real projects and assets; never use a personal profile.

The supplied mocked browser harness is not part of the source integration.
Technical checks cannot judge idiomatic Korean; native-speaker review is still
useful. Native font/glyph artwork, shape resources, internal shape names, IDs,
project/export schemas and user-supplied names are not localized or converted.
