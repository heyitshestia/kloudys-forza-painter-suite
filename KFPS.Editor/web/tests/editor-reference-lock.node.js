"use strict";
const assert = require("node:assert/strict");
const { create } = require("../editor-reference.js");

const controls = new Map();
for (const [id, value] of Object.entries({ overlayScale: "120", overlayScalePercent: "120", overlayOpacity: "45", overlaySizeLock: "" })) {
  controls.set(id, { value, disabled: false, attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } });
}
const events = [];
let failImage = false;
global.Image = class {
  width = 100; height = 50;
  set src(value) { if (value) queueMicrotask(() => failImage ? this.onerror?.() : this.onload?.()); }
};
class FabricImage {
  constructor(image, options) { Object.assign(this, { width: image.width, height: image.height }, options); }
  set(values) { Object.assign(this, values); }
  setCoords() {}
  getScaledWidth() { return this.width * this.scaleX; }
  getScaledHeight() { return this.height * this.scaleY; }
}
const api = create({
  scene: { canvas: () => ({ add() {}, requestRenderAll() {} }), releasePreview() {}, discard() {}, prewarm() {}, order() {} },
  session: { generation: () => 1, toolMode: () => "select", layerMode: () => "below", setLayerMode() {} },
  view: { element: id => controls.get(id), hidden() {}, text() {}, status() {}, hud() {}, interactivity() {}, failed(error) { throw error; },
    scaleControls(value) { const n = Math.max(10, Math.min(400, Number(value) || 100));
      controls.get("overlayScale").value = controls.get("overlayScalePercent").value = String(n); return n; } },
  persistence: {}, changed: reason => events.push(reason), maxReferenceBytes: 1024,
  fabric: { Image: FabricImage }, KfpsI18n: { t: value => value, error: value => value }, round: value => value,
});

(async () => {
  api.setSizeLocked(true);
  assert.equal(api.sizeLocked, false);
  assert.equal(controls.get("overlaySizeLock").disabled, true);
  await api.loadOverlayImageFromUrl("blob:fixture", "test.png", { layeredState: null });
  const original = { ...api.sourceOverlayProjectState().transform };
  api.setSizeLocked(true);
  assert.equal(api.sizeLocked, true);
  assert.equal(controls.get("overlaySizeLock").attributes["aria-pressed"], "true");
  assert.equal(controls.get("overlayScale").disabled, true);
  assert.equal(controls.get("overlayScalePercent").disabled, true);
  const count = events.length;
  api.setSizeLocked(true);
  assert.equal(events.length, count, "Repeated lock should not dirty the document");
  controls.get("overlayScalePercent").value = "400";
  api.updateOverlay();
  assert.equal(controls.get("overlayScalePercent").value, "120");
  assert.equal(events.length, count, "Blocked resize should not mark an edit");
  assert.deepEqual(api.sourceOverlayProjectState().transform, original);
  for (const value of [0, 1, 45, 99, 100]) {
    controls.get("overlayOpacity").value = String(value);
    api.updateOverlay({ rescale: false });
    assert.equal(api.image.opacity, value / 100);
    assert.equal(api.image.scaleX, original.scaleX);
    assert.equal(api.image.scaleY, original.scaleY);
  }
  const saved = api.sourceOverlayProjectState();
  assert.equal(saved.controls.size_locked, true);
  api.clearSourceOverlayState();
  assert.equal(api.sizeLocked, false);
  await api.restoreSourceOverlayFromProject(saved);
  assert.equal(api.sizeLocked, true);
  assert.deepEqual(api.sourceOverlayProjectState(), saved);
  failImage = true;
  await assert.rejects(api.loadOverlayImageFromUrl("blob:broken", "bad.png"));
  failImage = false;
  assert.equal(api.sizeLocked, true, "Failed replacement must retain lock");
  assert.deepEqual(api.sourceOverlayProjectState(), saved);
  api.setSizeLocked(false);
  controls.get("overlayScalePercent").value = "250";
  api.updateOverlay();
  assert.equal(api.image.scaleX, 45);
  for (const value of [undefined, false, "true", "false", 1, null]) {
    const old = structuredClone(saved);
    if (value === undefined) delete old.controls.size_locked;
    else old.controls.size_locked = value;
    await api.restoreSourceOverlayFromProject(old);
    assert.equal(api.sizeLocked, false, "Only explicit true may restore a lock");
  }
  await api.restoreSourceOverlayFromProject(saved);
  await api.loadOverlayImageFromUrl("blob:new", "replacement.png", { layeredState: null });
  assert.equal(api.sizeLocked, false, "New reference should start unlocked");
  api.setSizeLocked(true);
  api.removeOverlay();
  assert.equal(api.sizeLocked, false);
  assert.equal(controls.get("overlaySizeLock").disabled, true);
  assert.equal(controls.get("overlayScale").disabled, false);
  api.dispose();
  console.log("Reference size lock: guard, controls, opacity, persistence, old files, replacement and removal passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
