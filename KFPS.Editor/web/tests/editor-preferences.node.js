"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor-preferences.js"), "utf8");

function fixture(settings = {}, browser = {}, protocol = "http:") {
  const storage = new Map(Object.entries(browser));
  const calls = [];
  const timers = new Map();
  let id = 0, failWrite = false, failRead = false, hold = null;
  const context = {
    window: { addEventListener() {}, dispatchEvent() {} },
    location: { protocol, hash: "#session=test" }, URLSearchParams, AbortSignal,
    sessionStorage: { getItem() { return null; } },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) },
    CustomEvent: class { constructor(type, data) { this.type=type; this.detail=data; } },
    setTimeout: fn => { timers.set(++id, fn); return id; }, clearTimeout: id => timers.delete(id),
    fetch: async (_, options = {}) => {
      if (!options.method) {
        if (failRead) throw new Error("read unavailable");
        return { ok: true, json: async () => ({ settings }) };
      }
      const body = JSON.parse(options.body); calls.push(body);
      if (hold) await hold;
      if (failWrite) throw new Error("disk unavailable");
      Object.assign(settings, body.settings);
      return { ok: true, json: async () => ({ ok: true }) };
    },
  };
  vm.runInNewContext(source, context);
  return { api: context.window.KfpsEditorPreferences, calls, storage, setFail: v => { failWrite=v; }, setHold: v => { hold=v; } };
}

(async () => {
  const key = "kloudyFabricFavorites";
  const a = fixture({ [key]: "[9]" }, { [key]: "[1]", kloudyFabricLastColor: "#123456", artwork: "private" });
  await a.api.ready;
  assert.equal(a.api.getItem(key), "[9]");
  await a.api.flush();
  assert.deepEqual(a.calls, [{ settings: { kloudyFabricLastColor: "#123456" } }]);
  a.api.setItem(key, "[2]"); a.api.setItem(key, "[3]");
  a.setFail(true);
  assert.equal(await a.api.flush(), false);
  assert.match(a.api.error, /could not be saved/);
  a.api.setItem(key, "[4]"); a.setFail(false);
  assert.equal(await a.api.flush(), true);
  assert.equal(a.calls.at(-1).settings[key], "[4]");
  assert.equal(a.api.error, "");
  a.api.removeItem(key); await a.api.flush();
  assert.equal(a.calls.at(-1).settings[key], null);
  assert.throws(() => a.api.setItem("artwork", "private"));

  let release;
  const b = fixture(); await b.api.ready;
  b.setHold(new Promise(r => { release = r; }));
  b.api.setItem(key, "[5]");
  const flushing = b.api.flush();
  b.api.setItem(key, "[6]"); release();
  assert.equal(await flushing, true);
  assert.deepEqual(b.calls.map(c => c.settings[key]), ["[5]", "[6]"]);

  const local = fixture({}, { [key]: "[7]" }, "file:");
  await local.api.ready; local.api.setItem(key, "[8]");
  assert.equal(await local.api.flush(), true);
  assert.equal(local.storage.get(key), "[8]");
  assert.equal(local.calls.length, 0);
  const noticeKey = "kloudyFabricEditorUpdateAcknowledged";
  const noticeSettings = { [noticeKey]: "modernization-1", kloudyFabricLanguage: "ko" };
  const notice = fixture(noticeSettings, { [noticeKey]: "old-edition" });
  await notice.api.ready;
  assert.equal(notice.api.getItem(noticeKey), "modernization-1");
  notice.api.setItem("kloudyFabricLanguage", "en");
  await notice.api.flush();
  assert.equal(noticeSettings[noticeKey], "modernization-1");
  const centerKey = "kloudyFabricCenteredResize";
  const centeredSettings = { [centerKey]: "1", [key]: "[9]" };
  const centered = fixture(centeredSettings, { [centerKey]: "0" });
  await centered.api.ready;
  assert.equal(centered.api.getItem(centerKey), "1");
  centered.api.setItem(centerKey, "0"); centered.setFail(true);
  assert.equal(await centered.api.flush(), false);
  centered.setFail(false);
  assert.equal(await centered.api.flush(), true);
  assert.equal(centeredSettings[centerKey], "0");
  assert.equal(centeredSettings[key], "[9]");
  console.log("editor-preferences.node.js: hydration, scoped migration, coalescing, retry, concurrent edits, deletion, and direct-file fallback passed");
})().catch(error => { console.error(error); process.exitCode=1; });
