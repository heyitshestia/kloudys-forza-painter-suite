"use strict";
const assert = require("node:assert/strict");
const { create, ACK_KEY } = require("../editor-updates.js");
const offer = version => ({ available: true, checked: true, latestVersion: version, localVersion: "3.1.77" });

function fixture(stored = new Map()) {
  const classes = new Set(), listeners = new Map(), timers = new Map();
  let id = 0, response = offer("3.1.78"), calls = 0, fail = false;
  const button = { hidden: true, disabled: false, title: "", textContent: "",
    classList: { toggle: (key, on) => on ? classes.add(key) : classes.delete(key), remove: key => classes.delete(key) },
    setAttribute() {}, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) };
  const preferences = { getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value), flush: async () => true };
  const owner = create({ button, preferences, headers: { "X-KFPS-Editor-Session": "test-token" },
    i18n: { t: (s, v) => s.replace("{0}", v) },
    schedule: (fn, delay) => { timers.set(++id, { fn, delay }); return id; }, cancel: key => timers.delete(key),
    fetcher: async (url, options) => {
      calls++;
      assert.equal(url, "/api/fabric-editor/update-status");
      assert.equal(options.headers["X-KFPS-Editor-Session"], "test-token");
      if (fail) throw Error("offline");
      if (typeof response === "function") return response(options);
      return { ok: true, json: async () => response };
    } });
  owner.start();
  return { owner, button, classes, listeners, timers, preferences, stored,
    get calls() { return calls; }, reply: value => { response = value; }, offline: value => { fail = value; },
    click: () => listeners.get("click")() };
}

(async () => {
  let scenarios = 0;
  const t = fixture();
  assert(t.button.hidden);
  assert.deepEqual([...t.timers.values()].map(x => x.delay), [1000]);
  t.owner.start(); assert.equal(t.timers.size, 1);
  t.reply({ checked: true, available: false, latestVersion: "3.1.77" });
  await t.owner.check(); assert(t.button.hidden); scenarios++;
  t.reply(offer("3.1.78"));
  await t.owner.check(); assert(!t.button.hidden); assert(t.classes.has("isBlinking"));
  assert(t.button.title.includes("3.1.78")); scenarios++;
  await t.click(); assert(!t.classes.has("isBlinking")); assert(!t.button.hidden);
  assert.equal(t.stored.get(ACK_KEY), "3.1.78"); scenarios++;
  t.offline(true); await t.owner.check(); assert(!t.button.hidden); assert(!t.classes.has("isBlinking"));
  t.offline(false); t.reply(offer("3.1.79")); await t.owner.check(); assert(t.classes.has("isBlinking")); scenarios++;
  t.reply({ checked: true, available: false, latestVersion: "3.1.76" });
  await t.owner.check(); assert(t.button.hidden); assert(!t.classes.has("isBlinking")); scenarios++;
  t.reply(offer("<invalid>")); await t.owner.check(); assert(t.button.hidden);
  t.reply({ checking: true }); await t.owner.check(); assert.deepEqual([...t.timers.values()].map(x => x.delay), [1500]); scenarios++;
  t.owner.dispose(); assert.equal(t.timers.size, 0); assert.equal(t.listeners.size, 0);
  const calls = t.calls; await t.owner.check(); assert.equal(t.calls, calls); scenarios++;

  const restart = fixture(t.stored);
  await restart.owner.check(); assert(!restart.classes.has("isBlinking")); restart.owner.dispose(); scenarios++;
  const failed = fixture();
  failed.preferences.flush = async () => false;
  await failed.owner.check(); await failed.click();
  assert(!failed.classes.has("isBlinking")); assert(failed.button.title.includes("could not be saved"));
  failed.preferences.setItem = () => { throw Error("storage denied"); };
  failed.reply(offer("3.1.80")); await failed.owner.check(); await failed.click();
  assert(!failed.classes.has("isBlinking")); failed.owner.dispose(); scenarios++;

  const race = fixture(); let finishSave;
  race.preferences.flush = () => new Promise(resolve => { finishSave = resolve; });
  await race.owner.check(); const ack = race.click();
  race.reply(offer("3.1.79")); await race.owner.check(); assert(race.classes.has("isBlinking"));
  finishSave(true); await ack; assert(race.classes.has("isBlinking")); assert(!race.button.disabled);
  race.owner.dispose(); scenarios++;

  const close = fixture(); let signal;
  close.reply(options => new Promise((resolve, reject) => {
    signal = options.signal;
    signal.addEventListener("abort", () => reject(Error("aborted")), { once: true });
  }));
  const pending = close.owner.check(); assert.equal(close.owner.check(), pending);
  await Promise.resolve(); assert.equal(close.calls, 1);
  close.owner.dispose(); assert(signal.aborted); await pending;
  assert.equal(close.timers.size, 0); scenarios++;

  const timeout = fixture(); let timedOut = false;
  timeout.reply(options => new Promise((resolve, reject) => options.signal.addEventListener("abort", () => {
    timedOut = true; reject(Error("timeout"));
  })));
  const wait = timeout.owner.check(); await Promise.resolve();
  [...timeout.timers.values()].find(x => x.delay === 5000).fn(); await wait;
  assert(timedOut); assert.deepEqual([...timeout.timers.values()].map(x => x.delay), [60000]);
  timeout.reply(offer("3.1.78")); await timeout.owner.check(); assert(timeout.classes.has("isBlinking"));
  timeout.owner.dispose(); scenarios++;
  console.log(JSON.stringify({ suite: "editor-update-indicator", scenarios, passed: true }));
})().catch(error => { console.error(error); process.exitCode = 1; });
