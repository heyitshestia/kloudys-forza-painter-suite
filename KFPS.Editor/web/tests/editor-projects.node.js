"use strict";
const assert = require("node:assert/strict");
const { create } = require("../editor-projects.js");
(async () => {
  let generation = 1;
  const receipt = { target_id: "Example.fabric-project.json", fingerprint: "a".repeat(64), bytes: 100,
    request_id: "1".repeat(32), write_stage: "committed" };
  const calls = [];
  let mode = "saved";
  const persistence = { request: async (operation, data) => {
    calls.push({ operation, data });
    if (operation === "saveProject") {
      if (mode === "saved") return { receipt };
      if (mode === "conflict") throw Object.assign(Error("conflict"), { code: "project_conflict" });
      throw Object.assign(Error("lost response"), { code: "worker_timeout" });
    }
    if (data.url.includes("request_id")) return mode === "reconcile" ? { status: "committed", receipt } : { status: "unknown" };
    return { current: mode !== "changed" };
  } };
  const owner = create({ persistence, generation: () => generation, requestId: () => receipt.request_id });
  assert.equal((await owner.save("Example", { shapes: [] })).id, receipt.target_id);
  owner.associate(receipt, "Example");
  assert.equal(owner.expected("Different"), null);
  assert.equal(owner.expected("Example").fingerprint, receipt.fingerprint);
  generation++;
  assert.equal(owner.association, null);
  assert.equal(owner.expected("Example"), null);
  mode = "reconcile";
  calls.length = 0;
  assert.equal((await owner.save("Example", { shapes: [] })).receipt.fingerprint, receipt.fingerprint);
  assert.deepEqual(calls.map(call => call.operation), ["saveProject", "fetchJSON"]);
  mode = "unknown";
  await assert.rejects(owner.save("Example", {}), { code: "save_unknown" });
  mode = "conflict";
  calls.length = 0;
  await assert.rejects(owner.save("Example", {}), { code: "project_conflict" });
  assert.equal(calls.length, 1);
  assert.equal(await owner.verify(receipt), true);
  mode = "changed";
  assert.equal(await owner.verify(receipt), false);
  assert.equal(await owner.verify({}), false);
  console.log("Project ownership, lost receipts, no replay, conflicts and stale association passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });
