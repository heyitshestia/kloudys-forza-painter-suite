'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { fontGlyphSlots } = require('../KFPS.Editor/web/editor-catalog.js');

const file = path.join(__dirname, '../KFPS.Editor/web/shape-names.json');
const current = fs.readFileSync(file, 'utf8');
const names = JSON.parse(current);
const words = JSON.parse(fs.readFileSync(path.join(__dirname, '../KFPS.Editor/web/shape-words.json'), 'utf8')).families;
const glyphs = [], unnamed = [];
for (let font = 1; font <= 11; font++) for (const lower of [false, true]) {
  const block = lower ? 'Lower' : 'Upper';
  names.families[`${block}_Letters_${font}`] = Object.fromEntries(
    fontGlyphSlots(font, lower).map((char, index) => [String(index + 1),
      `Forza Font ${font} ${block} ${char === null ? `slot ${index + 1}` : char}`]));
  const family = `${block}_Letters_${font}`;
  fontGlyphSlots(font, lower).forEach((char, index) => {
    const resource = { resource_family: family, resource_index: index + 1 };
    if (char === null) { unnamed.push(resource); return; }
    const word = words[family][String(index + 1)];
    glyphs.push({ font, block: index < 26 ? block.toLowerCase()
      : !lower && index < 36 ? 'number' : `${block.toLowerCase()}_symbol`,
      glyph: char, display_glyph: char, shape_name: names.families[family][String(index + 1)],
      ...resource, fh6_shape_word: word, fh6_shape_word_hex: `0x${word.toString(16).padStart(4, '0')}` });
  });
}
const registry = { format: 'fh6_font_registry_v1', source: 'kfps_native_slots_v1',
  glyph_count: glyphs.length, unnamed_slots: unnamed, glyphs };
const registryFile = path.join(__dirname, '../data/fh6_font_registry.json');
if (process.argv.includes('--check')) {
  if (JSON.stringify(JSON.parse(current)) !== JSON.stringify(names)
      || JSON.stringify(JSON.parse(fs.readFileSync(registryFile, 'utf8'))) !== JSON.stringify(registry)) {
    process.stderr.write('Font names or compatibility registry are out of date. Run tools/sync_font_names.cjs.\n');
    process.exitCode = 1;
  }
} else {
  fs.writeFileSync(file, JSON.stringify(names, null, 2) + '\n');
  fs.writeFileSync(registryFile, JSON.stringify(registry, null, 2) + '\n');
}
