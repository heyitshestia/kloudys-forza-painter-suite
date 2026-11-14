"use strict";
const assert = require("node:assert/strict");
const { create } = require("../editor-private-previews.js");
const settle = () => new Promise(resolve => setImmediate(resolve));

async function main() {
  const calls = [], revoked = [], created = [], pending = [];
  const env = { location: new URL("http://127.0.0.1:1234/tools/fabric-editor/index.html"),
    URL: class extends URL {}, Event, addEventListener() {}, removeEventListener() {} };
  env.URL.createObjectURL = blob => { const url = `blob:test/${created.length}`; created.push(blob); return url; };
  env.URL.revokeObjectURL = url => revoked.push(url);
  const image = () => Object.assign(new EventTarget(), { src: "", contains(item) { return item === this; }, removeAttribute() { this.src = ""; } });
  const owner = create({ env, headers: { "X-KFPS-Editor-Session": "private" }, fetcher: (url, options) => {
    calls.push({ url, options });
    return new Promise(resolve => pending.push(resolve));
  } });
  const images = Array.from({ length: 10 }, image);
  for (let i = 0; i < images.length; i++) owner.set(images[i], `/api/fabric-editor/json-preview?id=${i}`);
  assert.equal(calls.length, 4, "preview concurrency is bounded");
  owner.clear(images[0]);
  pending[0](new Response("old"));
  await settle();
  assert.equal(images[0].src, "", "cleared request cannot republish stale preview");
  assert.equal(calls.length, 5);
  pending[1](new Response("preview"));
  await settle();
  assert.match(images[1].src, /^blob:/);
  assert.equal(calls[1].options.headers["X-KFPS-Editor-Session"], "private");
  assert.equal(calls[1].options.redirect, "error");
  let errors = 0;
  images[1].addEventListener("error", () => errors++);
  owner.set(images[1], "https://foreign.invalid/api/fabric-editor/json-preview");
  assert.equal(errors, 1);
  assert.equal(revoked.length, 1);
  const count = calls.length;
  owner.set(images[1], "/api/fabric-editor/project-file?id=private");
  assert.equal(calls.length, count, "headers never sent to non-preview routes");
  owner.dispose();
  assert.ok(calls.every(call => call.options.signal.aborted));
  for (const resolve of pending) resolve(new Response("late"));
  await settle();
  assert.ok(images.every(item => !item.src));
  assert.equal(created.length, 1);
  const failedCalls = [];
  const failures = create({ env, headers: {}, fetcher: async (url, options) => {
    failedCalls.push(options);
    return new Response("preview", { status: url.includes("http-error") ? 503 : 200 });
  } });
  const startCreated = created.length, startRevoked = revoked.length;
  for (let i = 0; i < 6; i++) {
    const broken = image();
    let attached = true;
    const container = { contains: item => attached && item === broken };
    // The asset library removes failed images before owner/container cleanup.
    broken.addEventListener("error", () => { attached = false; });
    failures.set(broken, `/api/fabric-editor/asset-preview?id=${i % 2 ? "http-error" : "decode-error"}`);
    await settle();
    if (attached) broken.dispatchEvent(new Event("error"));
    assert.equal(attached, false);
    failures.clear(container);
    assert.ok(failedCalls.at(-1).signal.aborted, "detached failed preview must release its owner entry");
    assert.equal(broken.src, "");
  }
  assert.equal(created.length - startCreated, revoked.length - startRevoked, "decode failures must revoke every blob");
  const afterFailure = revoked.length;
  failures.dispose();
  assert.equal(revoked.length, afterFailure, "no failed entries retained until page disposal");
  console.log("Private previews: authenticated, bounded, stale-safe and disposed.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
