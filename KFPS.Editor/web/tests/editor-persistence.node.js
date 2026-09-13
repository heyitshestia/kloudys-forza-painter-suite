"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const workers = [];
class FakeWorker {
  constructor() { this.messages = []; workers.push(this); }
  postMessage(message) {
    this.messages.push(structuredClone(message));
    if (!this.hold) queueMicrotask(() => this.onmessage?.({ data: { id: message.id, value: { ok: true } } }));
  }
  terminate() { this.terminated = true; }
}
const scope = { Worker: FakeWorker, Blob, setTimeout, clearTimeout, window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../editor-persistence.js"), "utf8"), scope);

async function run() {
  const events = [];
  const persistence = scope.window.KfpsEditorPersistence.create({}, { generation: () => 7,
    cause: () => ({documentId:2,commitId:3,firstCommitId:1,pageId:'a'.repeat(32)}), event: item => events.push(item) });
  const payload = data => ({ shapes: [], editor_source_overlay: { data_url: data, svg_text: null, transform: { left: 1 } } });
  await persistence.request("recovery", { payload: payload("same reference") });
  const oldCachedObject = persistence.lastReference;
  await persistence.request("recovery", { payload: payload(["same", "reference"].join(" ")) });
  assert.notEqual(persistence.lastReference, oldCachedObject, "Reopening identical reference text must release the previous cache object");
  assert.equal(persistence.lastReference.data_url, "same reference");
  assert.equal(Object.hasOwn(workers[0].messages[1], "reference"), false, "Rebinding must not resend unchanged reference bytes");
  assert.equal(workers[0].messages[1].payload.editor_source_overlay.data_url, null);
  assert.equal(workers[0].messages[1].payload.editor_source_overlay.transform.left, 1);
  await persistence.request("recovery", { payload: payload("changed reference") });
  assert.equal(workers[0].messages[2].reference.data_url, "changed reference");
  workers[0].hold = true;
  const staleError = workers[0].onerror;
  const pending = Array.from({ length: 8 }, () => persistence.request("recovery", { payload: payload("changed reference") }));
  await assert.rejects(persistence.request("recovery"), /Background storage is busy/);
  const settled = Promise.allSettled(pending);
  persistence.reset(new Error("Injected worker interruption"));
  assert.ok((await settled).every(result => result.status === "rejected"));
  assert.equal(persistence.pending.size, 0);
  assert.equal(persistence.lastReference, undefined);
  assert.equal(workers[0].terminated, true);
  await persistence.request("recovery", { payload: payload("changed reference") });
  assert.equal(workers[1].messages[0].reference.data_url, "changed reference", "A restarted worker must receive the reference again");
  staleError({ preventDefault() {} });
  assert.equal(persistence.worker, workers[1], "An old worker error reset the new worker");
  persistence.hooks.event = () => { throw Error("observer failure"); };
  await persistence.request("readRecovery");
  persistence.hooks.event = item => events.push(item);
  workers[1].hold = true;
  const pendingClose = persistence.request("saveProject", { request_id: "da5c3040-6a47-4e3f-a103-6399c729a81b", payload: payload("PRIVATE artwork") });
  const closed = assert.rejects(pendingClose, /closed/);
  persistence.dispose(); await closed;
  await assert.rejects(persistence.request("recovery"), /closed/);
  assert.equal(workers.length, 2, "Disposed owner created another worker");
  assert.equal(persistence.pending.size, 0);
  assert.equal(workers[1].onmessage, null); assert.equal(workers[1].onerror, null);
  assert.ok(events.some(item => item.state === "cancelled" && item.requestId === "da5c3040-6a47-4e3f-a103-6399c729a81b"));
  assert.ok(events.every(item => item.documentGeneration === 7 && item.queueDepth <= 8));
  assert.ok(events.every(item => item.documentId === 2 && item.commitId === 3 && item.firstCommitId === 1));
  assert.equal(JSON.stringify(events).includes("PRIVATE"), false);
  const started = events.filter(item => item.state === "pending");
  for (const entry of started) assert.equal(events.filter(item => item.jobId === entry.jobId && item.state !== "pending").length, 1);
  const admission = scope.window.KfpsEditorPersistence.create({ maxBytes: 1024 });
  const beforeWorkers = workers.length;
  await assert.rejects(admission.request("parseFile", { file: new Blob(["x".repeat(1025)]) }), error => error.code === "input_too_large");
  assert.equal(workers.length, beforeWorkers, "Oversized input started a worker");
  admission.start(); workers.at(-1).hold = true;
  const file = new Blob(["x".repeat(1024)]);
  const admitted = [admission.request("parseFile", { file }), admission.request("parseFile", { file })];
  await assert.rejects(admission.request("parseFile", { file }), error => error.code === "storage_busy");
  for (let index = 0; index < 4; index++) admitted.push(admission.request("fetchJSON", { url: "/metadata" }));
  await assert.rejects(admission.request("fetchJSON", { url: "/metadata" }), error => error.code === "storage_busy");
  admitted.push(admission.request("recovery", { payload: { shapes: [] } }), admission.request("browserRecovery", { payload: { shapes: [] } }));
  const settledAdmission = Promise.allSettled(admitted);
  admission.reset(Error("test complete"));
  assert.equal((await settledAdmission).length, 8, "Protection slots were not reserved");
  admission.dispose();
  console.log("Persistence: reference identity, bounds, worker epochs, correlated outcomes, observer isolation and disposal passed.");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
