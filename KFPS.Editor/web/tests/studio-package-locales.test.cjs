const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

const root = path.join(__dirname, '../../../tools/livery-studio/src/web/locales');
const messages = JSON.parse(fs.readFileSync(path.join(root, 'messages.json'), 'utf8'));
const keys = [
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
