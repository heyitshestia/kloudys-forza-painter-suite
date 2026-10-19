const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const renderer = require('../editor-renderer.js');

test('native bitmap sampling remains owned by Fabric', () => {
  // GPU clipping changed stable color readbacks by 1-2 levels. The real-host
  // pixel suite verifies the default cache draw, including masks and effects.
  assert.equal(renderer.drawNativePathCache, undefined);
  const source = fs.readFileSync(path.join(__dirname, '../editor.js'), 'utf8');
  assert.doesNotMatch(source, /\.drawCacheOnCanvas\s*=/);
});
