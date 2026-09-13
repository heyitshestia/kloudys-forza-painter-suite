"use strict";
const assert = require("node:assert/strict");
const { create } = require("../editor-recovery.js");
(async () => {
  let time = 0, serial = 0, release = null, mode = "ok", clears = 0;
  const timers = new Map(), calls = [], reports = [];
  const options = {
    clock: () => 1000, now: () => time,
    setTimer: (callback, delay) => { const id = ++serial; timers.set(id, { callback, at: time + delay }); return id; },
    clearTimer: id => timers.delete(id),
    onClear: () => clears++, onResult: (...args) => { reports.push(args); throw Error("Display fault"); },
    onError: () => {},
    transport: { request: async (operation, { payload }) => {
      calls.push({ operation, payload });
      if (operation === "browserRecovery") return { browserOk: true };
      if (mode === "hold") { mode = "ok"; await new Promise(resolve => { release = resolve; }); }
      if (mode === "fail") return { browserOk: true, serverOk: false, retryable: true, error: "disk fault" };
      return { browserOk: true, serverOk: true };
    } },
  };
  const owner = create(options);
  owner.observe(2000000);
  owner.write({ shapes: [1] });
  assert.equal(owner.revision, 2000001);
  for (time = 100; time <= 1900; time += 100) owner.write({ shapes: [time] });
  assert.equal([...timers.values()][0].at, 2000, "continuous editing must retain the max wait deadline");
  await owner.flush();
  assert.equal(calls.length, 1);
  assert.equal(owner.status.serverOk, true, "display observer must not invalidate the acknowledgment");
  mode = "hold";
  owner.write({ shapes: [2] });
  const first = owner.flush();
  assert.ok(release);
  owner.write({ shapes: [3] });
  const second = owner.flush();
  await owner.backupPromise;
  assert.equal(owner.status.browserOk, true);
  assert.notEqual(owner.status.serverOk, true);
  release(); await first; await second;
  assert.equal(calls.filter(call => call.operation === "recovery").length, 3);
  assert.deepEqual(calls.at(-1).payload.shapes, [3]);
  assert.equal(owner.status.serverOk, true);
  mode = "fail";
  owner.write({ shapes: [4] }); await owner.flush();
  assert.equal(owner.retryScheduled, true);
  mode = "ok";
  await owner.clear();
  assert.equal(owner.retryScheduled, false);
  assert.equal(clears, 1);
  assert.equal(owner.status.state, "cleared");
  assert.equal(calls.at(-1).payload.action, "clear");
  mode = "hold";
  owner.write({ shapes: [5] });
  const late = owner.flush();
  const before = reports.length;
  owner.dispose(); release(); await late;
  assert.equal(reports.length, before, "disposed owner must ignore late delivery");
  assert.equal(timers.size, 0);
  assert.equal(owner.write({ shapes: [] }), false);
  const graceful = create(options);
  mode = "hold"; graceful.write({ shapes: [6] }); const active = graceful.flush();
  graceful.write({ shapes: [7] }); const closing = graceful.shutdown();
  assert.equal(graceful.shutdown(), closing);
  assert.equal(graceful.write({ shapes: [8] }), false, "no new edits accepted during shutdown");
  release(); await active; await closing;
  assert.deepEqual(calls.filter(call => call.operation === "recovery").at(-1).payload.shapes, [7]);
  assert.equal(graceful.status.serverOk, true); assert.equal(timers.size, 0);
  console.log("Recovery ownership: continuous deadline, coalescing, independent backup, ACK/display separation, retry, clear and disposal passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
