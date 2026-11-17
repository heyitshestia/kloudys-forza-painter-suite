"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor.js"), "utf8");
const functions = ["showAutosaveRecovery", "maybeShowAutosaveRecovery"].map(name => {
  const match = source.match(new RegExp(`^async function ${name}\\([^]*?^\\}`, "m"));
  assert.ok(match, name);
  return match[0];
}).join("\n");

function harness(options = {}) {
  const calls = { recover: 0, verify: 0, prompts: 0, writes: 0 };
  const frames = [];
  const nodes = Object.fromEntries(["autosaveRecoveryTitle", "autosaveRecoveryHeading", "autosaveRecoverySummary",
    "autosaveRecoveryDescription", "autosaveRecoveryError", "recoverAutosave", "autosaveRecoveryDialog"]
    .map(id => [id, { textContent: "", hidden: false }]));
  Object.assign(nodes.autosaveRecoveryDialog, { open: false,
    showModal() { this.open = true; calls.prompts++; }, close() { this.open = false; } });
  const payload = options.payload === undefined ? { shapes: [{}], editor_session: {
    project_name: "Saved project", saved: true, receipt: { target_id: "project.json" },
  } } : options.payload;
  const context = vm.createContext({
    window: options.window || {}, documentGeneration: 0, contentCommitId: 0, nudgeHistoryPending: false, recoveryAutosavePayload: null,
    recoveryReadWarning: "", isTextVinylHarnessRun: () => false,
    readAutosavePayload: async () => payload,
    recoverAutosavePayload: async (_payload, { onFailure }) => {
      calls.recover++;
      if (options.failure) { onFailure(options.failure); return false; }
      return !options.cancelled;
    },
    editorProjects: { verify: async () => { calls.verify++; return options.verified !== false; } },
    $: id => nodes[id], setText: (id, value) => { nodes[id].textContent = value; },
    KfpsI18n: { t: (key, ...args) => key.replace(/\{(\d+)\}/g, (_, i) => args[Number(i)]) },
    autosaveSummary: () => "Opaque <name>", showCornerNotice: () => {},
    requestAnimationFrame: fn => frames.push(fn), setTimeout: fn => frames.push(fn),
    clearAutosave: () => { calls.writes++; }, writeAutosavePayload: () => { calls.writes++; },
  });
  vm.runInContext(functions, context);
  return { context, nodes, calls, payload, flush: () => { while (frames.length) frames.shift()(); } };
}

(async () => {
  const results = [];
  const chrome = { KfpsDesktopBridge: { completed() {}, progress() {} } };
  const qt = { qt: { webChannelTransport: {} } };
  for (const [name, window] of [["Chrome", chrome], ["Qt", qt]]) {
    for (const saved of [true, false]) {
      const h = harness({ window, payload: { shapes: [{}], editor_session: { saved } } });
      await h.context.maybeShowAutosaveRecovery(); h.flush();
      assert.equal(h.calls.recover, 1); assert.equal(h.calls.prompts, 0);
      assert.equal(h.calls.verify, 0, "Avoid redundant fingerprint read on successful auto restore");
      results.push(`${name}: ${saved ? "saved" : "unsaved"} auto restore`);
    }
    const h = harness({ window, failure: "Synthetic <load failure>" });
    await h.context.maybeShowAutosaveRecovery(); h.flush();
    assert.equal(h.calls.prompts, 1);
    assert.equal(h.nodes.autosaveRecoveryTitle.textContent, "Resume Saved Session?");
    assert.equal(h.nodes.autosaveRecoveryError.hidden, false);
    assert.match(h.nodes.autosaveRecoveryError.textContent, /Synthetic <load failure>/);
    assert.equal(h.calls.writes, 0);
    results.push(`${name}: failed restore retains verified checkpoint and literal error`);
    const cancelled = harness({ window, cancelled: true });
    await cancelled.context.maybeShowAutosaveRecovery(); cancelled.flush();
    assert.equal(cancelled.calls.prompts, 0);
    results.push(`${name}: superseded restore does not prompt`);
  }
  for (const test of [
    { name: "verified saved", title: "Resume Saved Session?" },
    { name: "missing or modified project", verified: false, title: "Resume Previous Session?" },
    { name: "unsaved", payload: { shapes: [{}], editor_session: { saved: false } }, title: "Recover Unsaved Editor Work?" },
    { name: "legacy", payload: { shapes: [{}] }, title: "Resume Previous Session?" },
    { name: "no named project", payload: { shapes: [{}], editor_session: { saved: true } }, title: "Resume Previous Session?" },
    { name: "incomplete desktop bridge", window: { KfpsDesktopBridge: {} }, title: "Resume Saved Session?" },
  ]) {
    const h = harness(test);
    await h.context.maybeShowAutosaveRecovery(); h.flush();
    assert.equal(h.calls.recover, 0);
    assert.equal(h.calls.prompts, 1);
    assert.equal(h.nodes.autosaveRecoveryTitle.textContent, test.title, test.name);
    assert.equal(h.nodes.autosaveRecoveryError.hidden, true);
    assert.equal(h.calls.writes, 0);
    results.push(`manual prompt: ${test.name}`);
  }
  for (const payload of [null, { shapes: [] }]) {
    const h = harness({ payload });
    assert.equal(await h.context.maybeShowAutosaveRecovery(), false); h.flush();
    assert.equal(h.calls.prompts, 0);
    results.push(payload ? "empty recovery ignored" : "no recovery ignored");
  }
  for (const phase of ["read", "verify", "paint", "payload replaced", "edit while reading", "edit while verifying", "save while verifying", "pending nudge"]) {
    const h = harness();
    if (phase === "read") h.context.readAutosavePayload = async () => { h.context.documentGeneration++; return h.payload; };
    if (phase === "verify") h.context.editorProjects.verify = async () => { h.context.documentGeneration++; return true; };
    if (phase === "edit while reading") h.context.readAutosavePayload = async () => { h.context.contentCommitId++; return h.payload; };
    if (phase === "edit while verifying") h.context.editorProjects.verify = async () => { h.context.contentCommitId++; return true; };
    if (phase === "save while verifying") h.context.editorProjects.verify = async () => { h.context.editorProjects.association = {}; return true; };
    if (phase === "pending nudge") h.context.nudgeHistoryPending = true;
    await h.context.maybeShowAutosaveRecovery();
    if (phase === "paint") h.context.documentGeneration++;
    if (phase === "payload replaced") h.context.recoveryAutosavePayload = null;
    h.flush();
    assert.equal(h.calls.prompts, 0, phase);
    results.push(`stale prompt suppressed during ${phase}`);
  }
  for (const phase of ["already closed", "verification", "paint"]) {
    const h = harness();
    h.context.recoveryAutosavePayload = h.payload;
    h.nodes.autosaveRecoveryDialog.open = phase !== "already closed";
    if (phase === "verification") h.context.editorProjects.verify = async () => {
      h.nodes.autosaveRecoveryDialog.close(); return true;
    };
    await h.context.showAutosaveRecovery(h.payload, "Retry failed", { requireOpen: true });
    if (phase === "paint") h.nodes.autosaveRecoveryDialog.close();
    h.flush();
    assert.equal(h.calls.prompts, 0);
    results.push(`dismissed retry stays closed: ${phase}`);
  }
  console.log(JSON.stringify({ passed: true, cases: results.length, results }));
})().catch(error => { console.error(error); process.exitCode = 1; });
