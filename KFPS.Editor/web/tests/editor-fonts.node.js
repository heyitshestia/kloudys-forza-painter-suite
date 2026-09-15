'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { fontGlyphSlots, forzaGlyphResource, decodeVertexAlphas } = require('../editor-catalog.js');

// Independently transcribed native resource sheets. Nulls are unnamed artwork,
// not guessed character aliases. Duplicate @ glyphs may resolve to either slot.
const tails = [
  ['$','\u00a3','\u00a5','\u20ac','\u00e6','^','\u00df','@','#','+','%',';',':','/'],
  ['$','\u00a3','\u00a5','\u20ac','(',')','^','*','#','+','%',';',':','/'],
  ['$','\u00a3','\u00a5','\u20ac','\u00e6','^','\u00df','@','#','+','%',';',':','/'],
  ['$','\u00a3','\u00a5','\u20ac','\u00e6','^','\u00df','@','#','+','%',';',':',null],
  ['$','\u00a3','\u00a5','\u20ac','(',')',null,'{','}','`','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','(',')','\u00bb','*','[',']','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','[',']','\u2021','*','#','\u00a4','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','(',')','\u00a7','*','\u00d8','\u00a2','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','(',')','<','*','#','+','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','(',')','\u2021','*','\u00a7','\u00a2','%',';',':',','],
  ['$','\u00a3','\u00a5','\u20ac','(',')','\u00a2','*','#','+','%',';',':',','],
];

test('every identified glyph resolves to the expected resource, in all eleven fonts', () => {
  let slots = 0, named = 0;
  for (let font = 1; font <= 11; font++) {
    const upper = [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890!?', font === 6 ? null : '@', '&'];
    const lower = [...'abcdefghijklmnopqrstuvwxyz', ...tails[font - 1]];
    assert.deepEqual(fontGlyphSlots(font, false), upper);
    assert.deepEqual(fontGlyphSlots(font, true), lower);
    for (const [block, expected] of [['Upper', upper], ['Lower', lower]]) expected.forEach((char, index) => {
      slots++;
      if (char === null) return;
      named++;
      const result = forzaGlyphResource(char, font);
      assert.ok(result, `${font}/${block}/${index + 1}: ${char}`);
      assert.equal(result.family.split('_').at(-1), String(font));
      assert.equal((result.family.startsWith('Upper') ? upper : lower)[result.index - 1], char);
    });
  }
  assert.equal(slots, 880); assert.equal(named, 877);
});

test('unsupported symbols and invalid inputs never silently become A or another glyph', () => {
  for (const char of ['', null, undefined, 1, 'AB', '\n', '\uac00', '\u0000']) assert.equal(forzaGlyphResource(char, 1), null);
  assert.equal(forzaGlyphResource('@', 6), null);
  assert.equal(forzaGlyphResource('/', 11), null);
  assert.deepEqual(forzaGlyphResource('\u00c6', 1), { family: 'Lower_Letters_1', index: 31 });
  assert.deepEqual(forzaGlyphResource('A', 1.5), { family: 'Upper_Letters_1', index: 1 });
  assert.deepEqual(forzaGlyphResource('0', 99), { family: 'Upper_Letters_11', index: 36 });
});

test('alpha decoding keeps binary, partial and legacy representations consistent', () => {
  assert.deepEqual([...decodeVertexAlphas({}, 3)], [255,255,255]);
  assert.deepEqual([...decodeVertexAlphas({ VerticesAlpha: 'AID/' }, 3)], [0,128,255]);
  assert.deepEqual([...decodeVertexAlphas({ VerticesAlpha: [0, { A: 128 }, [1,2,3,255]] }, 3)], [0,128,255]);
  assert.deepEqual([...decodeVertexAlphas({ VerticesAlpha: 'invalid!' }, 3)], [255,255,255]);
});
