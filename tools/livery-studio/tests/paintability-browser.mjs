import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root = path.resolve(process.env.KFPS_TEST_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..'));
const [workspaceArg, label = 'baseline', archive = 'POR_3_917LHFE_70.zip'] = process.argv.slice(2);
assert(workspaceArg, 'Pass an isolated run workspace.');
const workspace = path.resolve(workspaceArg);
assert(workspace.startsWith(path.join(root, 'tools/livery-studio/runs') + path.sep));
fs.mkdirSync(workspace, {recursive: true});
const output = path.join(workspace, label);
fs.mkdirSync(output, {recursive: true});
const require = createRequire(process.env.KFPS_PLAYWRIGHT_PACKAGE ||
  path.join(process.env.USERPROFILE, '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium} = require('playwright');
const infoPath = path.join(workspace, 'server-info.json');
const log = fs.openSync(path.join(output, 'server.log'), 'w');
const child = spawn(path.join(root, 'python/python.exe'), ['-B',
  path.join(path.dirname(fileURLToPath(import.meta.url)), 'isolated_server.py'), '--kfps-root', root,
  '--game-root', process.env.KFPS_TEST_GAME_ROOT || 'C:/XboxGames/Forza Horizon 6/Content',
  '--archive', archive, '--workspace', workspace], {
  cwd: root, windowsHide: true, stdio: ['ignore', log, log],
  env: {...process.env, PYTHONDONTWRITEBYTECODE: '1', TEMP: output, TMP: output},
});
let browser, page;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  let info;
  for (let attempt = 0; attempt < 180; attempt++) {
    try { info = JSON.parse(fs.readFileSync(infoPath, 'utf8')); } catch {}
    if (info?.pid === child.pid && info.status === 'running') break;
    assert(child.exitCode === null, 'Studio server stopped: see server.log.');
    await sleep(500);
  }
  assert(info?.pid === child.pid && info.status === 'running', 'Studio server did not start.');
  browser = await chromium.launch({headless: true,
    executablePath: process.env.KFPS_TEST_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-vsync'],
    env: {...process.env, TEMP: output, TMP: output},
  });
  page = await browser.newPage({viewport: {width: 1440, height: 900}});
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== new URL(info.url).origin) return route.abort();
    if (url.pathname.endsWith('/livery-editor.mjs')) {
      const response = await route.fetch();
      return route.fulfill({response, body: await response.text() +
        '\nwindow.__paintDocument = () => JSON.parse(serializeProject(project));'});
    }
    if (!url.pathname.endsWith('/livery-scene.js')) return route.continue();
    const response = await route.fetch();
    await route.fulfill({response, body: await response.text() + `
      window.__paintTest = {
        ready: isSceneReady,
        setup() {
          controls.enableDamping = false; controls.autoRotate = false;
          setSectionFilter('right'); setInspectionMode('paintability');
          frameModel(modelBounds, new THREE.Vector3(-1, .06, 0));
          requestRender();
        },
        ablate() {
          for (const {mesh} of componentMeshes) if (meshCategory(mesh) === 'paint') {
            mesh.userData.kfps_allowed_sides = 63;
            mesh.material.uniforms.meshAllowedSlots.value = allowedSlotArray(63);
          }
          requestRender();
        },
        stats() {
          const right = renderContract.sections.filter(s => s.slot_index === 4);
          const rows = [];
          for (const {mesh} of componentMeshes) {
            if (meshCategory(mesh) !== 'paint' || !effectivelyVisible(mesh)) continue;
            const uv = mesh.geometry.getAttribute('uv3'), pos = mesh.geometry.getAttribute('position');
            const normals = mesh.geometry.getAttribute('normal'), indices = mesh.geometry.index;
            if (!uv || !normals || !indices) continue;
            const normalMatrix = new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld);
            let eligible = 0, accepted = 0;
            for (let i = 0; i < indices.count; i += 3) {
              const ids = [0,1,2].map(k => indices.getX(i+k));
              const uv3 = [0,0], n = new THREE.Vector3();
              for (const id of ids) {
                uv3[0] += uv.getX(id)/3; uv3[1] += uv.getY(id)/3;
                n.add(new THREE.Vector3().fromBufferAttribute(normals,id));
              }
              n.applyMatrix3(normalMatrix).normalize();
              const args = {uv3, normal:n.toArray(), kind:'body', sections:right,
                pages:surfaceMaskPages, allowed:63};
              if (!chooseSurfaceSection(args)) continue;
              eligible++;
              if (chooseSurfaceSection({...args,allowed:meshAllowedSides(mesh,'paint')})) accepted++;
            }
            if (eligible) rows.push({name:mesh.userData.kfps_source_mesh_name,
              material:mesh.userData.kfps_material_name,allowed:meshAllowedSides(mesh,'paint'),eligible,accepted});
          }
          const box=canvas.getBoundingClientRect(), hits=[];
          for(let y=80;y<box.height-60;y+=12) for(let x=40;x<box.width-40;x+=12) {
            const hit=surfaceAtClient(box.left+x,box.top+y);
            if(hit) hits.push({x,y,section:hit.section});
          }
          return {rows,hits,scene:sceneState()};
        },
        paint() {
          const source=document.createElement('canvas');
          source.width=renderContract.paint_size[0]; source.height=renderContract.paint_size[1];
          const ctx=source.getContext('2d'); ctx.fillStyle='#ff00e5';ctx.fillRect(0,0,source.width,source.height);
          updatePaintCanvas(source,'balanced',source.width*source.height*4);
          setInspectionMode('off'); requestRender();
        },
        plain() {setInspectionMode('off');requestRender();},
      };
    `});
  });
  await page.goto(info.url, {waitUntil: 'domcontentloaded'});
  await page.waitForFunction(() => window.__paintTest?.ready(), null, {timeout: 120000});
  await page.waitForFunction(() => window.__paintDocument && !document.querySelector('#importVinyl').disabled);
  await page.evaluate(() => window.__paintTest.setup());
  await sleep(800);
  const baseline = await page.evaluate(() => window.__paintTest.stats());
  await page.locator('#canvas').screenshot({path: path.join(output, 'right-original.png')});
  if (label.startsWith('fixed')) {
    assert(baseline.rows.length > 0, 'No mask-covered body surfaces.');
    assert(baseline.rows.every(row => row.accepted === row.eligible), 'Native mask coverage is blocked.');
    await page.selectOption('#section', 'Right');
    const shapes = [{type:1048677,data:[0,0,20,10,0,0,0],color:[255,0,229,255],mask:false}];
    await page.setInputFiles('#vinylFile', {name:'right-paint-test.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(shapes))});
    await page.waitForFunction(() => window.__paintDocument().placements.length === 1);
    await page.evaluate(() => window.__paintTest.plain());
    await sleep(800);
    await page.locator('#canvas').screenshot({path:path.join(output,'right-imported-vinyl.png')});
    const project = await page.evaluate(() => window.__paintDocument());
    assert.equal(project.placements[0].section, 'Right');
    const savedPath = path.join(output,'right-paint-test.kfps-layout.json');
    fs.writeFileSync(savedPath,JSON.stringify(project,null,2));
    await page.click('#saveProject');
    await page.fill('#layoutProjectName',`${label}-right`);
    await page.click('#saveLayoutProject [data-storage="save"]');
    await page.waitForFunction(() => !document.querySelector('#saveLayoutProject').open);
    await page.click('#undo');
    await page.waitForFunction(() => window.__paintDocument().placements.length === 0);
    await page.click('#redo');
    await page.waitForFunction(() => window.__paintDocument().placements.length === 1);
    await page.click('#openProject');
    await page.selectOption('#openLayoutProject select', {label:`${label}-right`});
    await page.click('#openLayoutProject [data-storage="open"]');
    await page.waitForFunction(() => !document.querySelector('#openLayoutProject').open);
    assert.deepEqual(await page.evaluate(() => window.__paintDocument()),project);
    await page.evaluate(() => window.__paintTest.setup());
  }
  await page.evaluate(() => window.__paintTest.ablate());
  await sleep(500);
  const unrestricted = await page.evaluate(() => window.__paintTest.stats());
  if (label.startsWith('fixed')) assert.deepEqual(baseline.hits,unrestricted.hits, 'Ablation should not unlock any further surface.');
  await page.locator('#canvas').screenshot({path: path.join(output, 'right-native-masks.png')});
  await page.evaluate(() => window.__paintTest.paint());
  await sleep(500);
  await page.locator('#canvas').screenshot({path: path.join(output, 'right-paint.png')});
  const prepared=JSON.parse(fs.readFileSync(path.join(workspace,'prepared.json'),'utf8'));
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify({archive,label,signature:prepared.signature,baseline,unrestricted,errors},null,2));
  console.log(JSON.stringify({archive,label,rows:baseline.rows,
    hitsBefore:baseline.hits.length,hitsAfter:unrestricted.hits.length,errors},null,2));
  assert.deepEqual(errors, []);
} catch (error) {
  if (page) {
    await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});
    const diagnostic=await page.evaluate(()=>({text:document.body.innerText,document:window.__paintDocument?.()})).catch(()=>null);
    fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify(diagnostic,null,2));
    console.error(diagnostic?.text);
  }
  throw error;
} finally {
  await browser?.close();
  if (child.exitCode === null) {
    child.kill();
    await new Promise(resolve => child.once('exit',resolve));
  }
  fs.closeSync(log);
}
