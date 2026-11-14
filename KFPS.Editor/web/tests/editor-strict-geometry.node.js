'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../editor.js'), 'utf8');
const body = source.slice(source.indexOf('function validateStrictInputShapes('), source.indexOf('\nfunction normalizeInputShape('));
const legacyTypes = source.slice(source.indexOf('const LEGACY_RECTANGLE_TYPES ='), source.indexOf('\n', source.indexOf('const ELLIPSE_DIVISOR =')));
const rounding = source.slice(source.indexOf('function round(value)'), source.indexOf('\nfunction requestCanvasRender('));
const validate = vm.runInNewContext(`${legacyTypes}\n${rounding}\n${body}; validateStrictInputShapes`, {
  KfpsI18n: { t: text => text },
});

test('strict scale admission survives native serialization after legacy conversion', () => {
  for (const [type, divisor] of [[1048677, 1], [1, 127], [2, 127], [8, 63], [16, 63]]) {
    for (const axis of [2, 3]) for (const sign of [-1, 1]) {
      for (const scale of [1e-7, 4.9e-7]) {
        const data = shape.data.slice();
        data[axis] = sign * scale * divisor;
        assert.throws(() => validate([shape, {...shape, type, data}]), /saved layers are invalid/);
      }
      for (const scale of [1e-6, 2e-6]) {
        const data = shape.data.slice();
        data[axis] = sign * scale * divisor;
        validate([{...shape, type, data}]);
      }
    }
  }
});
const shape = {type: 1048677, data: [10, 20, 1, -.5, 370, .25, 0], color: [12, 34, 56, 78]};
test('strict geometry rejects coercions, sparse arrays and out-of-range fields without mutation', () => {
  for (const data of [null, [], [0, 0, 1], [0, 0, 0, 1], [0, 0, 1, 0],
    [null, 0, 1, 1], [true, 0, 1, 1], ['0', 0, 1, 1], [NaN, 0, 1, 1],
    [0, Infinity, 1, 1], [0, 0, 1e13, 1], [0, 0, 1, 1, 0, 0, 2], Array(7)]) {
    assert.throws(() => validate([{...shape, data}]), /saved layers are invalid/);
  }
  for (const color of [null, [], [0, 1], [0, 0, 256], [0, -1, 0, 255], [0, 0, NaN], ['0', 0, 0], Array(4)]) {
    assert.throws(() => validate([{...shape, color}]), /saved layers are invalid/);
  }
  for (const patch of [{type: '1048677'}, {type: 1048677.5}, {type: 2 ** 32},
    {type_word: -1}, {type_word: 65536}, {mask: 'false'}, {mask: 3}]) {
    assert.throws(() => validate([{...shape, ...patch}]), /saved layers are invalid/);
  }
  const frozen = Object.freeze({...shape, data: Object.freeze(shape.data.slice()), color: Object.freeze(shape.color.slice())});
  const before = JSON.stringify(frozen);
  assert.throws(() => validate([frozen, null]), /saved layers are invalid/);
  assert.equal(JSON.stringify(frozen), before);
});
test('strict geometry supports legacy/native optional fields, mirrors, RGB and numeric tails', () => {
  validate([]);
  for (const type of [1, 2, 8, 16, 1048677]) for (const length of [4, 5, 6, 7, 8]) {
    validate([{type, data: [10, 20, -1, .5, -720, -.25, 1, 123.456].slice(0, length), color: [1, 2, 3]}]);
  }
  validate([{...shape, color: undefined, mask: 1, type_word: 101}]);
  validate([{...shape, type: 1, color: [1, 2, 3, 0]}]);
});
