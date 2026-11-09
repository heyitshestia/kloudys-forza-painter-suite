const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const root = path.join(__dirname, '../../../tools/livery-studio/src/web/locales');
const messages = JSON.parse(fs.readFileSync(path.join(root, 'messages.json'), 'utf8'));
const keys = [
  'Preview quality was reduced for this layout to fit available memory. Saved quality preference and exports are unchanged.',
  'Vinyl source actions', 'Delete vinyl source', 'Delete vinyl source?',
  'Delete "{0}" and its {1} placement(s) across this car?',
  'This only changes the current layout. Original files are kept. Undo restores the source and its placements.',
  'Vinyl source deleted.', 'Vinyl source is no longer available.', 'Highlight section', 'Highlighted: {0}', 'Delete',
  "Invalid local Studio window URL.",
  "This Studio does not support package artwork. Save your work, then restart Studio.",
  "Preparing the package car...",
  "Cancelling obsolete car preparation...",
  "Studio startup request timed out. Reopen Studio from KFPS.",
  "Studio returned oversized readiness metadata.",
  "The package car is ambiguous in the configured catalogue.",
  "The car switch result could not be confirmed. Reopen Studio from KFPS before retrying.",
  "Save your work and choose this package's car in the existing Studio before opening it. This running Studio may have another open page, so automatic car switching was blocked. Existing documents have not been changed.",
  "Inspector",
  "Placement",
  "Design",
  "Car",
  "View",
  "Preview",
  "Fast",
  "Balanced",
  "Sharp",
  "In Chrome, save your work and choose this package's car in Studio before opening it. Automatic car switching could interrupt another Studio window.",
  'Save this layout before opening package artwork?',
  'Only editable artwork is imported. Body paint and materials are not imported. The source package is unchanged.',
  'Discard and open',
  'Save and open',
  'The package has no exact car identity.',
  'This session cannot open the package car. Save your work, then restart Studio.',
  'Package opening cancelled. The current layout is unchanged.',
  'The exact package car is not installed. Nothing was opened.',
  'The package car could not be prepared. The current layout is retained.',
  'The incoming artwork link is invalid.',
  'This session cannot receive this artwork. Save your work, then restart Studio.',
  'Opening package artwork...',
  'The incoming artwork exceeds its size limit.',
  'The incoming artwork data is invalid.',
  'Package artwork opened. Body paint and materials were not imported. The source package is unchanged.',
];

for (const [language, index] of [['en', -1], ['ko', 0], ['ja', 1]]) {
  test(`package prompts and feedback are present in ${language}`, async () => {
    const {default: pack} = await import(pathToFileURL(path.join(root, `${language}.mjs`)).href);
    assert.deepEqual(Object.keys(pack), Object.keys(messages));
    for (const key of keys) {
      assert.ok(Array.isArray(messages[key]) && messages[key].length === 2, key);
      assert.equal(pack[key], index < 0 ? key : messages[key][index]);
      assert.ok(pack[key].trim(), key);
      if (index >= 0) assert.notEqual(pack[key], key);
    }
  });
}
