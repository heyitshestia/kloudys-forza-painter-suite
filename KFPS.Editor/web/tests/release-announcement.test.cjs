'use strict';
const assert = require('node:assert/strict');
const {safeStatus} = require('../release-announcement.js');
const expected = ['releaseId','publishedAt','expiresAt','locale','acknowledged','eligible'];
assert.deepEqual(Object.keys(safeStatus(null)), expected);
const status = safeStatus({releaseId:'notice-1',publishedAt:'2026-01-01T00:00:00Z',
  expiresAt:'2026-01-08T00:00:00Z',locale:'ja',acknowledged:true,eligible:false,
  token:'do-not-collect',client:'private-client',content:{title:'private text'},path:'private-path'});
assert.deepEqual(Object.keys(status), expected);
assert.equal(status.locale,'ja');
assert.equal(status.acknowledged,true);
assert(!JSON.stringify(status).includes('private'));
console.log('Release announcement diagnostic boundary: passed');
