"use strict";

const assert = require("node:assert/strict");
require("../editor-core.js");

const {
  alignmentDelta,
  distributionDeltas,
  OrderedObjectRegistry,
  buildVirtualLayout,
  mapWithConcurrency,
  virtualRange,
} = globalThis.KfpsEditorCore;

async function run() {
  const source = [{ vinyl: true }, { vinyl: false }, { vinyl: true }];
  const registry = new OrderedObjectRegistry((item) => item.vinyl);
  assert.deepEqual(registry.read(source), [source[0], source[2]]);
  assert.equal(registry.indexOf(source[2], source), 1);
  source.reverse();
  assert.deepEqual(registry.read(source), [source[2], source[0]], "registry should remain cached until invalidated");
  registry.invalidate();
  assert.deepEqual(registry.read(source), [source[0], source[2]]);

  let active = 0;
  let maximumActive = 0;
  const ordered = await mapWithConcurrency([5, 4, 3, 2, 1], 2, async (value) => {
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    await new Promise((resolve) => setTimeout(resolve, value));
    active -= 1;
    return value * 2;
  });
  assert.deepEqual(ordered, [10, 8, 6, 4, 2]);
  assert.equal(maximumActive, 2);

  active = 0;
  await assert.rejects(
    mapWithConcurrency([0, 1, 2, 3, 4], 3, async (value) => {
      active += 1;
      await new Promise((resolve) => setTimeout(resolve, value === 1 ? 1 : 5));
      active -= 1;
      if (value === 1) throw new Error("expected worker failure");
      return value;
    }),
    /expected worker failure/,
  );
  assert.equal(active, 0, "mapWithConcurrency must settle in-flight workers before rejecting");

  const layout = buildVirtualLayout([
    { id: "a", height: 20 },
    { id: "b", height: 30 },
    { id: "c", height: 40 },
  ]);
  assert.equal(layout.totalHeight, 90);
  assert.deepEqual(
    virtualRange(layout, 24, 20, 0),
    { start: 1, end: 2, padTop: 20, padBottom: 40, totalHeight: 90 },
  );

  const bounds = { left: 20, top: 30, right: 60, bottom: 90, centerX: 40, centerY: 60 };
  const canvas = { left: -1000, top: -1000, right: 1000, bottom: 1000, centerX: 0, centerY: 0 };
  assert.deepEqual(alignmentDelta(bounds, canvas, "left"), { x: -1020, y: 0 });
  assert.deepEqual(alignmentDelta(bounds, canvas, "centerX"), { x: -40, y: 0 });
  assert.deepEqual(alignmentDelta(bounds, canvas, "bottom"), { x: 0, y: 910 });
  assert.deepEqual(distributionDeltas([0, 15, 90, 100]), [0, 100 / 3 - 15, 200 / 3 - 90, 0]);
  assert.deepEqual(distributionDeltas([10, 30]), [0, 0]);
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
