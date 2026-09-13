"use strict";
const assert = require("node:assert/strict");
const { create } = require("../editor-desktop-protocol.js");

async function run() {
  const timers = new Map(), replies = [], phases = [];
  let next = 0, waiting = false, resolve, calls = 0;
  const clock = { setInterval(fn) { timers.set(++next, fn); return next; }, clearInterval(id) { timers.delete(id); } };
  const bridge = { completed(id, raw) { replies.push([id, JSON.parse(raw)]); }, progress(id, phase) { phases.push([id, phase]); } };
  const api = create({ clock, bridge: () => bridge, userWaiting: () => waiting,
    execute: () => { calls++; return new Promise(done => { resolve = done; }); }, onError() {} });
  const pending = api.execute("one", "open", {});
  await api.execute("one", "open", {});
  assert.equal(calls, 1);
  assert.deepEqual(api.outcome("one"), { state: "working" });
  waiting = true; [...timers.values()].forEach(fn => fn());
  assert.deepEqual(api.outcome("one"), { state: "user-wait" });
  assert.equal(phases.at(-1)[1], "user-wait");
  resolve({ ok: true }); await pending;
  assert.equal(timers.size, 0);
  assert.deepEqual(api.outcome("one"), { state: "complete", result: { ok: true, value: { ok: true } } });
  await api.execute("one", "open", {});
  assert.equal(calls, 1); assert.equal(replies.length, 2);

  const failed = create({ clock, bridge: () => ({ completed() { throw Error("lost"); } }),
    userWaiting: () => false, execute: async () => { throw Error("failure"); }, onError() { throw Error("UI failed"); } });
  await failed.execute("bad", "close", {});
  assert.equal(failed.outcome("bad").result.error, "failure");
  assert.equal(timers.size, 0);
  for (let i=0; i<20; i++) await failed.execute(`r${i}`, "state", {});
  assert.equal(failed.outcome("bad").state, "unknown");
  assert.equal(failed.outcome("r3").state, "unknown");
  assert.equal(failed.outcome("r4").state, "complete");

  waiting = false;
  const abandoned = api.execute("abandoned", "close", {});
  const count = replies.length;
  api.dispose();
  resolve({ok:true}); await abandoned;
  assert.equal(replies.length, count); assert.equal(timers.size, 0);
  assert.equal(api.outcome("abandoned").state, "unknown");
  await failed.execute("bad id", "open", {});
  assert.equal(failed.outcome("bad id").state, "unknown");
  console.log("desktop protocol: deduplication, outcome recovery, bounded retention, user wait, errors and disposal passed");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
