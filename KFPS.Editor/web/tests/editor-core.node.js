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
  const stack = Array.from({ length: 3000 }, (_, index) => ({ index }));
  const reversed = stack.slice().reverse();
  assert.deepEqual(KfpsEditorCore.orderByStack(reversed, stack), stack);
  assert.equal(reversed[0], stack.at(-1), "Ordering must not mutate the caller's selection");
  const detached = {};
  assert.deepEqual(KfpsEditorCore.orderByStack([stack[2], detached, stack[0]], stack), [detached, stack[0], stack[2]]);
  assert.deepEqual(KfpsEditorCore.orderByStack([], stack), []);
  assert.deepEqual(KfpsEditorCore.orderByStack([detached], stack), [detached]);
  const parse = globalThis.KfpsEditorCore.parseNumericExpression;
  for (const [expression, expected] of [["12 + 3 * 4", 24], ["(12 + 3) * 4", 60], ["-2.5 / .5", -5], ["50%", .5], ["1e2 + -4", 96], ["-(2+3)", -5]]) assert.equal(parse(expression), expected);
  for (const expression of ["", "1/0", "NaN", "Infinity", "2**3", "alert(1)", "2foo", "1e20", "()", "1+", "(".repeat(20) + "1" + ")".repeat(20), "1+".repeat(200) + "1"]) assert.throws(() => parse(expression));
  const source = [{ vinyl: true }, { vinyl: false }, { vinyl: true }];
  const registry = new OrderedObjectRegistry((item) => item.vinyl);
  assert.deepEqual(registry.read(source), [source[0], source[2]]);
  assert.equal(registry.indexOf(source[2], source), 1);
  source.reverse();
  assert.deepEqual(registry.read(source), [source[2], source[0]], "registry should remain cached until invalidated");
  registry.invalidate();
  assert.deepEqual(registry.read(source), [source[0], source[2]]);

  let predicates = 0;
  const copiedRegistry = new OrderedObjectRegistry(item => { predicates++; return item.vinyl; });
  const first = copiedRegistry.read(source.slice());
  for (let i = 0; i < 10; i++) assert.equal(copiedRegistry.read(source.slice()), first);
  assert.equal(predicates, source.length, "Public copied snapshots should reuse the registry");
  const reordered = source.slice().reverse();
  assert.deepEqual(copiedRegistry.read(reordered), [source[2], source[0]]);
  const replacement = { vinyl: true };
  assert.deepEqual(copiedRegistry.read([replacement, source[1], source[0]]), [replacement, source[0]], "Same-size replacement must invalidate cached membership");
  replacement.vinyl = false;
  copiedRegistry.invalidate();
  assert.deepEqual(copiedRegistry.read([replacement, source[1], source[0]]), [source[0]]);
  assert.deepEqual(copiedRegistry.read([]), []);

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

  let yields = 0;
  assert.deepEqual(await mapWithConcurrency([1, 2, 3, 4], 2, value => value * 2, {
    yieldAfterMs: 0,
    yield: async () => { yields++; await new Promise(resolve => setTimeout(resolve, 0)); },
  }), [2, 4, 6, 8]);
  assert.ok(yields > 0 && yields <= 4, "Optional build slicing must yield without changing order");
  await assert.rejects(mapWithConcurrency([1, 2], 2, value => value, {
    yieldAfterMs: 0, yield: async () => { throw new Error("expected yield failure"); },
  }), /expected yield failure/);

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
