"use strict";

const assert = require("node:assert/strict");
const pixel = require("../editor-pixel-core.js");
const red = [240, 30, 20, 255], blue = [20, 30, 240, 255];
const rows = [[red, red, null, blue], [red, red, null, blue], [null, red, red, blue]];
assert.deepEqual(pixel.buildPixelArtRuns(rows), [
  { x: 0, y: 0, width: 2, height: 2, key: "240:30:20:255", color: red },
  { x: 3, y: 0, width: 1, height: 3, key: "20:30:240:255", color: blue },
  { x: 1, y: 2, width: 2, height: 1, key: "240:30:20:255", color: red },
]);
assert.equal(pixel.buildPixelArtRuns(rows, 2), null);
assert.deepEqual(pixel.buildPixelArtRuns([[null, null]], 0), []);
assert.deepEqual(pixel.buildPixelArtRuns([], 0), []);
let visited = 0;
function* tooManyRows() {
  for (let y = 0; y < 100000; y++) { visited++; yield y % 2 ? [blue, red] : [red, blue]; }
}
assert.equal(pixel.buildPixelArtRuns(tooManyRows(), 3000), null);
assert.equal(visited, 1501, "Reject before enumerating a huge over-budget grid");
const flat = { width: 64, height: 32, data: new Uint8ClampedArray(64 * 32 * 4) };
for (let offset = 0; offset < flat.data.length; offset += 4) flat.data.set(red, offset);
const result = pixel.analyzePixelArt(flat, 128, 24, 1);
assert.equal(result.overflow, false);
assert.equal(result.runs.length, 1);
assert.deepEqual(result.runs[0].color, red);
assert.equal(pixel.analyzePixelArt(flat, 128, 24, 0).overflow, true);
assert.deepEqual(pixel.analyzePixelArt(flat, 255, 24, 0).runs, []);
assert.equal(pixel.pixelArtVisible([1, 2, 3, 128], 128), false);
assert.equal(pixel.pixelArtVisible([1, 2, 3, 129], 128), true);
console.log("Pixel core: exact merge, transparency, empty, budget boundaries and early termination passed.");
