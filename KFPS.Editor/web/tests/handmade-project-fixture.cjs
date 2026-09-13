"use strict";
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const dense = require("./dense-human-fixture.cjs");

const hash = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const check = (condition, message) => { if (!condition) throw Error(message); };

function input(options = {}) {
  const filename = options.project || process.env.KFPS_EDITOR_PROJECT_FIXTURE;
  check(filename && path.isAbsolute(filename), "Supply an absolute private project fixture path");
  const bytes = fs.readFileSync(filename);
  const sha256 = hash(bytes);
  if (options.projectSha256) check(sha256 === options.projectSha256, "Private fixture fingerprint changed");
  const project = JSON.parse(bytes);
  check(project.format === "kloudy_fabric_editor_project_v1" && Array.isArray(project.shapes), "Expected an editor project");
  check(project.shapes.length > 1000 && project.shapes.length <= 3000, "Handmade qualification requires a substantial project");
  return { filename, bytes, sha256, project };
}

function profile(output) {
  const record = JSON.parse(fs.readFileSync(path.join(output, "process.json"), "utf8"));
  const root = path.resolve(__dirname, "../../..");
  const allowed = path.join(root, "runtime/test-runs") + path.sep;
  const target = path.resolve(record.profile);
  check(target.startsWith(allowed), "Handmade fixtures only belong in an isolated native test profile");
  return target;
}

async function openStored(page, name, count) {
  await page.locator("#loadProject").click();
  const entry = page.locator(".projectBrowserEntry").filter({ has: page.getByText(name, { exact: true }) });
  await entry.click();
  await page.locator("#selectProjectEntry").click();
  await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth && !documentDirty, count);
  await page.locator("#projectBrowserDialog").waitFor({ state: "hidden" });
}

async function referenceState(page) {
  return page.evaluate(() => {
    const saved = editorReference.sourceOverlayProjectState();
    return { ...saved, data_url: saved?.data_url ? { length: saved.data_url.length } : null, svg_text: saved?.svg_text ? { length: saved.svg_text.length } : null };
  });
}

async function setup(page, output, options = {}) {
  if(options.inputTrace)await page.evaluate(()=>{
    if(window.handmadePointerTrace)return;
    window.handmadePointerTrace=[];
    for(const type of ['pointerdown','pointermove','pointerup','pointercancel'])document.addEventListener(type,event=>{
      if(type==='pointermove'&&!event.buttons)return;
      handmadePointerTrace.push({type,at:performance.now(),x:event.clientX,y:event.clientY,
        screenX:event.screenX,screenY:event.screenY,buttons:event.buttons,button:event.button,
        trusted:event.isTrusted,pointerType:event.pointerType});
      if(handmadePointerTrace.length>256)handmadePointerTrace.shift();
    },{capture:true,passive:true});
  });
  const source = input(options);
  const name = path.basename(source.filename).replace(/\.fabric-project\.json$/i, "");
  const destination = path.join(profile(output), "projects", path.basename(source.filename));
  check(path.resolve(source.filename) !== path.resolve(destination), "Do not test the original project in place");
  fs.mkdirSync(path.dirname(destination), { recursive: true });
  if (fs.existsSync(destination)) check(hash(fs.readFileSync(destination)) === source.sha256, "Existing private project copy differs");
  else fs.copyFileSync(source.filename, destination);
  const started = Date.now();
  await openStored(page, name, source.project.shapes.length);
  const reference = source.project.editor_source_overlay;
  if (reference) await page.waitForFunction(({ width, height, opacity, order }) =>
    editorReference.image?.width === width && editorReference.image?.height === height
    && Number(document.getElementById("overlayOpacity").value) === opacity && overlayLayerMode === order,
  { width: reference.intrinsic_width, height: reference.intrinsic_height,
    opacity: reference.controls.opacity_percent, order: reference.controls.layer_mode });
  await page.locator("#fitView").click();
  await page.waitForTimeout(500);
  const shapes = JSON.parse(await dense.snapshot(page));
  check(shapes.length === source.project.shapes.length, "Project layer count differs");
  const drift = [];
  for (let i = 0; i < shapes.length; i++) {
    const actual = shapes[i], expected = source.project.shapes[i];
    check(actual.editor_id === expected.editor_id, `Layer order/ID changed at ${i}`);
    check(actual.type === expected.type && JSON.stringify(actual.color) === JSON.stringify(expected.color), `Shape/color changed at ${i}`);
    for (let j = 0; j < expected.data.length; j++) {
      const difference = Math.abs(actual.data[j] - expected.data[j]);
      if (difference > 1e-9) drift.push({ index: i, field: j, expected: expected.data[j], actual: actual.data[j], difference });
    }
  }
  check(!drift.length, `Opening changed project geometry: ${JSON.stringify(drift.slice(0, 5))}`);
  const result = { setup: "Unmodified private project copied to isolated store and opened using actual project-browser controls",
    sha256: source.sha256, bytes: source.bytes.length, loadMs: Date.now() - started,
    ...await dense.scene(page), referenceState: await referenceState(page), geometryDrift: drift };
  fs.writeFileSync(path.join(output, "handmade-input.json"), JSON.stringify(result, null, 2));
  return result;
}

async function saveAs(page, name) {
  await page.locator("#saveProjectAs").click();
  await dense.type(page, "#textPromptInput", name);
  await page.locator("#textPromptInput").press("Enter");
  await page.locator("#textPromptDialog").waitFor({ state: "hidden" });
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
}

async function setupDerived(page, output, options = {}) {
  const source = input(options);
  const count = Number(options.layers || 2400);
  check(Number.isInteger(count) && count >= source.project.shapes.length + 50 && count <= 2950,
    "Derived control fixture must retain every handmade layer and leave insertion headroom");
  const project = structuredClone(source.project);
  const originalCount = project.shapes.length;
  const added = [];
  while (project.shapes.length < count - 50) {
    const index = project.shapes.length - originalCount;
    const parent = source.project.shapes[index % originalCount];
    const copy = { ...structuredClone(parent), editor_id: `handmade-extra-${index}`,
      shape_name: `Qualification copy ${index}`, editor_group_id: null, editor_group_name: null };
    project.shapes.push(copy);
    added.push({ id: copy.editor_id, sourceId: parent.editor_id, purpose: "Near-capacity copy at original position" });
  }
  for (let index = 0; index < 48; index++) {
    project.shapes.push({ type: index % 2 ? 1048678 : 1048677, color: [210, 80, 130, 255],
      data: [-190 + index % 12 * 34, 100 - Math.floor(index / 12) * 35, .22, .22, 0, 0, 0],
      editor_id: `dense-batch-${index}`, shape_name: `Batch member ${index}`,
      editor_group_id: "dense-batch", editor_group_name: "Dense batch" });
    added.push({ id: `dense-batch-${index}`, purpose: "Controlled 48-member group for command assertions" });
  }
  project.shapes.push({ type: 1048706, color: [245, 180, 60, 255], data: [-180, -190, 1.5, 1.5, 0, 0, 0],
    editor_id: "dense-target", shape_name: "Human target" });
  project.shapes.push({ type: 1048678, color: [90, 205, 195, 255], data: [210, -190, 1.4, 1.4, 0, 0, 0],
    editor_id: "dense-other", shape_name: "Human alternate" });
  added.push({ id: "dense-target", purpose: "Controlled command probe" }, { id: "dense-other", purpose: "Controlled alternate probe" });
  project.layer_count = count;
  project.name = "Handmade control derivative";
  const filename = path.join(output, "Handmade control derivative.fabric-project.json");
  fs.writeFileSync(filename, JSON.stringify(project));
  fs.writeFileSync(path.join(output, "handmade-derivation.json"), JSON.stringify({ sourceSha256: source.sha256,
    originalCount, derivedCount: count, originalShapesUnchanged: true, originalReferenceUnchanged: true,
    added, limitation: "Appended controlled probes and overlapping copies are not the original hand-built design" }, null, 2));
  const result = await setup(page, output, { ...options, project: filename, projectSha256: hash(fs.readFileSync(filename)) });
  return { ...result, handmadeSourceSha256: source.sha256, originalLayers: originalCount, derived: true };
}

async function selectId(page, id, modifiers = []) {
  const { index, name } = await page.evaluate(id => {
    const index = vinylObjects().findIndex(object => object.kloudy.editor_id === id);
    return { index, name: vinylObjects()[index]?.kloudy.name };
  }, id);
  check(index >= 0, "Requested handmade layer no longer exists");
  await dense.type(page, "#layerSearch", `${index + 1}. ${name || ""}`);
  const label = page.locator(".layerMain b").filter({ hasText: new RegExp(`^${index + 1}\\. `) });
  for (let attempt = 0; attempt < 30 && !await label.count(); attempt++) {
    const viewport = await page.evaluate(() => {
      const rect = layerScrollPane().getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    });
    await page.mouse.move(viewport.x, viewport.y);
    await page.mouse.wheel(0, 180);
    await page.waitForTimeout(50);
  }
  check(await label.count() === 1, "Exact handmade layer was not reachable through filtered list scrolling");
  await page.locator(".layerRow").filter({ has: label }).locator(".layerMain").click({ modifiers });
  await page.waitForFunction(id => selectedVinylObjects().some(object => object.kloudy.editor_id === id), id);
}

const speeds = {
  slow: { steps: 24, delay: 20 },
  ordinary: { steps: 12, delay: 8 },
  fast: { steps: 4, delay: 0 },
  burst: { steps: 1, delay: 0 },
};

async function motion(page, from, to, speed = "ordinary", modifiers = [], button = "left") {
  check(!fs.existsSync(path.join(process.cwd(), "stop-test.json")), "External memory monitor requested a safe stop");
  const timing = speeds[speed];
  check(timing, "Unknown input speed");
  for (const modifier of modifiers) await page.keyboard.down(modifier);
  const started = Date.now();
  try {
    await page.mouse.move(from.x, from.y);
    await page.mouse.down({ button });
    for (let index = 1; index <= timing.steps; index++) {
      await page.mouse.move(from.x + (to.x - from.x) * index / timing.steps,
        from.y + (to.y - from.y) * index / timing.steps);
      if (timing.delay) await page.waitForTimeout(timing.delay);
    }
    await page.mouse.up({ button });
  } finally {
    await page.mouse.up({ button });
    for (const modifier of modifiers.toReversed()) await page.keyboard.up(modifier);
  }
  const record={ speed, ...timing, ms: Date.now() - started, modifiers, button, from, to, utc:Date.now() };
  fs.appendFileSync(path.join(process.cwd(),'injected-motions.jsonl'),JSON.stringify(record)+'\n');
  return record;
}

async function frameSelection(page) {
  await page.locator("#fitSelected").click();
  let zoomOuts = 0;
  for (; zoomOuts < 10; zoomOuts++) {
    const geometry = await dense.geometry(page);
    const box = await page.locator(".upper-canvas").boundingBox();
    if (Object.values(geometry.handles).every(p => p.x > box.x + 35 && p.x < box.x + box.width - 35
      && p.y > box.y + 35 && p.y < box.y + box.height - 35)) return { ...geometry, zoomOuts };
    await page.mouse.move(geometry.center.x, geometry.center.y);
    await page.mouse.wheel(0, 150);
    await page.waitForTimeout(60);
  }
  throw Error("Actual zoom could not frame all transform controls");
}

async function expectTranslation(page,before,after,x,y) {
  const actual={x:(after.left-before.left)*before.zoom,y:(after.top-before.top)*before.zoom};
  const error=Math.hypot(actual.x-x,actual.y-y);
  if(error<=1)return;
  const pointerTrace=await page.evaluate(()=>window.handmadePointerTrace||null);
  const failure={expected:{x,y},actual,error,before,after,pointerTrace};
  fs.writeFileSync(path.join(process.cwd(),'motion-delta-failure.json'),JSON.stringify(failure,null,2));
  throw Error(`Drag moved by the wrong distance (${error.toFixed(2)} screen pixels of error)`);
}

module.exports = { ...dense, input, profile, setup, openStored, referenceState, saveAs, hash, check,
  selectId, speeds, motion, frameSelection, setupDerived, expectTranslation };
