"use strict";
// Real editor page and Studio theme UI/API. Studio's game-renderer module is
// deliberately excluded: this fixture has no licensed car or game installation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const readline = require('node:readline');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../../..');
const run = process.env.KFPS_XBOX_RUN || 'xbox-headless-current';
assert.match(run, /^xbox-headless-[a-z0-9-]+$/);
const output = path.join(root, 'KFPS.Editor/runtime', run);
fs.mkdirSync(output, {recursive: true});
process.env.TEMP = process.env.TMP = path.join(output, 'temp');
fs.mkdirSync(process.env.TEMP, {recursive: true});
const report = {run, checks: [], limitations: ['Studio game renderer excluded; no native WebView2 qualification.']};
let host, browser;
const log = fs.createWriteStream(path.join(output, 'server.log'), {flags: 'a'});
async function startHost() {
  const child = cp.spawn(process.env.KFPS_TEST_PYTHON, ['-B', path.join(__dirname, 'xbox-theme-server.py'), output],
    {cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
  child.stderr.pipe(log, {end: false});
  const exit = new Promise(resolve => child.once('exit', resolve));
  const info = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => {child.kill(); reject(Error('Theme host startup timed out'));}, 20000);
    const lines = readline.createInterface({input: child.stdout});
    lines.once('line', line => {clearTimeout(timer); try {resolve(JSON.parse(line));} catch (e) {reject(e);}});
    child.once('exit', code => {clearTimeout(timer); reject(Error(`Theme host exited: ${code}`));});
    child.once('error', reject);
  });
  return {...info, stop: async () => {child.stdin.end('\n'); assert.equal(await exit, 0);}};
}
async function openEditor(context) {
  const page = await context.newPage();
  page.on('pageerror', error => report.checks.push(`Editor page error: ${error.message}`));
  await page.addInitScript(() => localStorage.setItem('kloudyFabricStartupHelpConfirmed', 'true'));
  await page.goto(host.editor);
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(async () => {
    await KfpsEditorPreferences.ready;
    await editorTheme.loadEditorThemes();
    await editorTheme.loadEditorThemePreference();
    document.querySelectorAll('dialog[open]').forEach(d => d.close());
  });
  return page;
}
async function editorSelect(page, id) {
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#editorThemeSelect').selectOption(id);
  await page.keyboard.press('Escape');
  await page.evaluate(() => KfpsEditorPreferences.flush());
}
async function editorAdjust(page) {
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#adjustTheme').click();
  await page.locator('#themeAdjustDialog').waitFor({state: 'visible'});
  await settleChromeEntrance(page);
}
async function settleChromeEntrance(page) {
  await page.evaluate(() => Promise.all(document.getAnimations().filter(a => a.animationName === 'xboxChromeEnter')
    .map(a => a.finished.catch(() => {}))));
}
async function state(page, studio = false) {
  return page.evaluate(studio => {
    const css = getComputedStyle(document.documentElement);
    const header = document.querySelector(studio ? '#commands' : '.appBar');
    return {id: document.documentElement.dataset.editorTheme, base: document.documentElement.dataset.editorThemeBase,
      accent: css.getPropertyValue('--accent').trim(), header: getComputedStyle(header).backgroundImage,
      text: css.getPropertyValue('--text').trim()};
  }, studio);
}
async function openStudio(context) {
  const page = await context.newPage();
  const source = fs.readFileSync(path.join(root, 'tools/livery-studio/src/web/livery-editor.mjs'), 'utf8');
  const icons = source.slice(source.indexOf('function icon(button)'), source.indexOf('async function responseError'));
  await page.route('**/livery-editor.mjs', route => route.fulfill({contentType: 'text/javascript', body: icons}));
  await page.goto(host.studio);
  await page.waitForFunction(() => !document.querySelector('#showTheme').disabled);
  return page;
}
async function studioSelect(page, id, save = true) {
  await page.locator('#showTheme').click();
  await page.locator('#themeChoice').selectOption(id);
  if (save) {
    await page.locator('#applyTheme').click();
    await page.locator('#themeDialog').waitFor({state: 'hidden'});
  }
}
async function geometry(page, selector) {
  return page.locator(selector).evaluateAll(nodes => nodes.map(node => {
    const r = node.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};
  }));
}
async function fits(page, selector) {
  await settleChromeEntrance(page);
  return page.locator(selector).evaluate(node => {
    const r = node.getBoundingClientRect();
    return r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && node.scrollWidth <= node.clientWidth + 1;
  });
}

async function protectedArtworkStyles(page) {
  await page.locator('#quickColorSwatch').click();
  await page.locator('.favoriteColorSwatch').nth(0).click();
  await page.locator('#dialogColorPicker').evaluate(input => {
    input.value = '#e74768'; input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  });
  await page.locator('#saveFavoriteColor').click();
  await page.locator('.favoriteColorSwatch').nth(1).click();
  await page.locator('#dialogColorPicker').evaluate(input => {
    input.value = '#16a675'; input.dispatchEvent(new Event('input', {bubbles:true}));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  });
  await page.locator('#saveFavoriteColor').click();
  await page.locator('.favoriteColorSwatch').nth(2).click();
  await page.locator('#closeColorDialog').click();
  await page.locator('.dockTab[data-panel="shapeLibraryPane"]').click();
  await page.locator('.shapeTile').first().waitFor({state:'visible'});
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    const specimen = document.createElement('button');
    specimen.id = 'referenceSwatchProbe';
    specimen.style.cssText = '--swatch:rgba(239,103,32,.4);background:rgba(239,103,32,.4);box-shadow:inset 0 0 0 999px var(--swatch)';
    document.getElementById('overlayPane').append(specimen);
    const selectors = ['#quickColorSwatch','#colorSwatchButton','#colorPanelSwatch','#activeColorLarge',
      '.favoriteColorSwatch:not(.empty):not(.active):not(.selected)', '.favoriteColorSwatch.active',
      '.favoriteColorSwatch.empty', '.shapeTile', '.shapeTile .favButton', '#referenceSwatchProbe'];
    const capture = () => Object.fromEntries(selectors.map(selector => {
      const node = document.querySelector(selector); if(!node) throw Error(`Missing swatch fixture ${selector}`);
      const css = getComputedStyle(node);
      return [selector, {background:css.backgroundImage, color:css.backgroundColor, shadow:css.boxShadow, size:css.backgroundSize}];
    }));
    const styled = capture(), base = root.dataset.editorThemeBase;
    root.dataset.editorThemeBase = 'skin-disabled';
    const unstyled = capture(); root.dataset.editorThemeBase = base;
    specimen.remove();
    return {styled, unstyled};
  });
  assert.deepEqual(result.styled, result.unstyled, 'Xbox chrome must not replace artwork-bearing fills/shadows');
  await page.locator('.dockTab[data-panel="propertiesPane"]').click();
  return Object.keys(result.styled);
}

async function customPaletteContrast(page, studio = false) {
  const {pathToFileURL} = require('node:url');
  const {PALETTES} = await import(pathToFileURL(path.join(root, 'tools/livery-studio/src/web/theme-adapter.mjs')));
  return page.evaluate(({palettes, studio}) => {
    const root = document.documentElement, keys = Object.keys(palettes.light);
    const previous = keys.map(key => [key,root.style.getPropertyValue(key),root.style.getPropertyPriority(key)]);
    const computed = () => keys.map(key => getComputedStyle(root).getPropertyValue(key));
    const before = computed();
    const rgb = color => color.startsWith('#') ? color.slice(1).match(/../g).map(v=>parseInt(v,16))
      : color.match(/[\d.]+/g).slice(0,3).map(Number);
    const luma = color => rgb(color).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
      .reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const measurements = [];
    try {
      for (const [name, colors] of Object.entries(palettes)) {
        for (const [key, value] of Object.entries(colors)) root.style.setProperty(key, value);
        const selectors = studio ? ['#themeCancel','#themeName'] : ['#saveProject','.toolButton.active','.fieldGrid input'];
        for (const selector of selectors) {
          const css = getComputedStyle(document.querySelector(selector));
          const a = luma(css.color), b = luma(colors['--panel3']);
          const ratio = (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
          if(ratio<4.5) throw Error(`Custom ${name} ${selector}: ${ratio}`);
          measurements.push({name,selector,color:css.color,contrast:ratio});
        }
      }
    } finally {
      for (const [key,value,priority] of previous) {
        if (value) root.style.setProperty(key,value,priority); else root.style.removeProperty(key);
      }
      if (JSON.stringify(computed()) !== JSON.stringify(before)) throw Error('Palette contrast probe did not restore computed colors');
    }
    return measurements;
  }, {palettes:{light:PALETTES.whiteout,dark:PALETTES.blackout},studio});
}

async function chromeMotion(page, studio = false) {
  const label = studio ? 'studio' : 'editor', header = studio ? '#commands' : '.appBar';
  const popup = studio ? '#themeDialog' : '.workspaceMenu:popover-open';
  const trigger = studio ? '#showTheme' : '#workspaceViewMenu';
  const snapshot = () => page.evaluate(header => {
    const css = getComputedStyle(document.querySelector(header), '::before');
    const animation = document.getAnimations().find(a => a.animationName === 'xboxHeaderDrift');
    return {gate:document.documentElement.dataset.xboxMotion, name:css.animationName,
      playState:css.animationPlayState, transform:css.transform, time:animation?.currentTime,
      hidden:document.hidden, focused:document.hasFocus()};
  }, header);
  const close = async () => {
    if (studio) await page.locator('#themeCancel').click();
    else await page.keyboard.press('Escape');
  };
  await page.emulateMedia({reducedMotion:'no-preference'});
  const first = await snapshot();
  assert.equal(first.gate, 'running', `${label}: active page motion`);
  assert.equal(first.name, 'xboxHeaderDrift');
  await page.waitForTimeout(180);
  const moving = await snapshot();
  assert.ok(moving.time > first.time && moving.transform !== first.transform, `${label}: actual ambient clock/transform advance`);
  const headerA = await page.locator(header).screenshot({path:path.join(output, `${label}-motion-header-a.png`)});
  await page.waitForTimeout(500);
  const headerB = await page.locator(header).screenshot({path:path.join(output, `${label}-motion-header-b.png`)});
  assert.ok(!headerA.equals(headerB), `${label}: rendered header pixels must change`);
  // Capture a reproducible interpolated entrance, rather than racing a 160ms frame.
  const entrance = await page.evaluate(({trigger,popup}) => {
    document.querySelector(trigger).click();
    const node = document.querySelector(popup);
    getComputedStyle(node).opacity;
    const animation = node.getAnimations().find(a => a.animationName === 'xboxChromeEnter');
    if (!animation) throw Error('Missing popup entrance');
    animation.pause(); animation.currentTime = 45;
    const css = getComputedStyle(node);
    return {opacity:css.opacity, transform:css.transform, duration:animation.effect.getTiming().duration,
      properties:Object.keys(animation.effect.getKeyframes()[0]).sort()};
  }, {trigger,popup});
  assert.ok(Number(entrance.opacity) > 0 && Number(entrance.opacity) < 1);
  assert.notEqual(entrance.transform, 'none');
  assert.equal(entrance.duration, 160);
  assert.deepEqual(entrance.properties, ['composite','computedOffset','easing','offset','opacity','transform']);
  await page.screenshot({path:path.join(output, `${label}-xbox-popup-motion.png`)});
  const interrupted = await page.evaluate(popup => {
    Object.defineProperty(document, 'hasFocus', {configurable:true,value:()=>false});
    window.dispatchEvent(new Event('blur'));
    const css = getComputedStyle(document.querySelector(popup));
    return {opacity:css.opacity,transform:css.transform,animation:css.animationName};
  }, popup);
  assert.deepEqual(interrupted, {opacity:'1',transform:'none',animation:'none'}, 'Inactive entrance must settle, not freeze transparent');
  await close();
  // Headless virtual windows do not reliably expose OS background visibility.
  // Exercise the real event handlers and CSS clocks with explicit DOM state probes.
  const inactive = [];
  for (const hidden of [false,true]) {
    await page.evaluate(hidden => {
      Object.defineProperty(document, 'hasFocus', {configurable:true,value:()=>false});
      Object.defineProperty(document, 'hidden', {configurable:true,get:()=>hidden});
      Object.defineProperty(document, 'visibilityState', {configurable:true,get:()=>hidden?'hidden':'visible'});
      if (hidden) document.dispatchEvent(new Event('visibilitychange'));
      else window.dispatchEvent(new Event('blur'));
    }, hidden);
    await page.waitForTimeout(50);
    const paused = await snapshot();
    await page.waitForTimeout(120);
    const after = await snapshot();
    assert.equal(paused.gate, 'paused'); assert.equal(paused.playState, 'paused');
    assert.equal(after.time, paused.time); assert.equal(after.transform, paused.transform);
    const readable = await page.evaluate(studio => {
      const read = selector => {
        const node = document.querySelector(selector), css = getComputedStyle(node);
        return {opacity:css.opacity,transform:css.transform,animation:css.animationName,
          readable:css.visibility==='visible' && css.display!=='none' && node.getBoundingClientRect().height>0};
      };
      let menu;
      if (!studio) {document.querySelector('#workspaceViewMenu').click();menu=read('.workspaceMenu:popover-open');}
      document.querySelector(studio?'#showTheme':'#adjustTheme').click();
      return {menu,dialog:read(studio?'#themeDialog':'#themeAdjustDialog')};
    }, studio);
    const visible = {opacity:'1',transform:'none',animation:'none',readable:true};
    assert.deepEqual(readable.dialog, visible, `${label}: dialog opened while inactive/hidden must be readable`);
    if (!studio) assert.deepEqual(readable.menu, visible);
    if (hidden) await page.screenshot({path:path.join(output, `${label}-xbox-hidden-dialog.png`)});
    await page.locator(studio?'#themeCancel':'#closeThemeAdjust').click();
    await page.locator(studio?'#themeDialog':'#themeAdjustDialog').waitFor({state:'hidden'});
    inactive.push({hidden,time:paused.time,unchanged:true,...readable});
  }
  await page.evaluate(() => {
    delete document.hasFocus; delete document.hidden; delete document.visibilityState;
    document.dispatchEvent(new Event('visibilitychange')); window.dispatchEvent(new Event('focus'));
  });
  assert.equal((await snapshot()).gate, 'running');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal((await snapshot()).name, 'none');
  await page.locator(trigger).click();
  const reduced = await page.locator(popup).evaluate(node => {
    const css = getComputedStyle(node);return {animation:css.animationName,transform:css.transform,opacity:css.opacity};
  });
  assert.deepEqual(reduced, {animation:'none',transform:'none',opacity:'1'});
  await page.screenshot({path:path.join(output, `${label}-xbox-reduced-motion.png`)});
  await close();
  await page.emulateMedia({reducedMotion:'no-preference'});
  assert.equal((await snapshot()).name, 'xboxHeaderDrift');
  const targets = await page.evaluate(() => document.getAnimations().filter(a => a.animationName?.startsWith('xbox'))
    .map(a => a.effect.target.id || a.effect.target.className));
  assert.deepEqual(targets, [studio?'commands':'appBar']);
  return {ambientAdvances:true,headerPixelsChange:true,entrance,interrupted,inactive,reduced,
    inactivityMethod:'DOM visibility/focus probes in real Chrome; not OS window minimization'};
}

async function disposedMotionListeners(page, studio = false) {
  const cdp = await page.context().newCDPSession(page);
  const listeners = async () => {
    const found = [];
    for (const expression of ['window','document']) {
      const {result} = await cdp.send('Runtime.evaluate', {expression,objectGroup:'xbox-listeners'});
      const {listeners} = await cdp.send('DOMDebugger.getEventListeners', {objectId:result.objectId});
      for (const listener of listeners) {
        if ((listener.originalHandler?.description || listener.handler?.description || '').includes('function syncChromeMotion')) {
          found.push(`${expression}:${listener.type}`);
        }
      }
    }
    return found.sort();
  };
  try {
    const before = await listeners();
    assert.deepEqual(before, ['document:visibilitychange','window:blur','window:focus','window:pageshow']);
    await page.evaluate(studio => {
      if (studio) window.dispatchEvent(new PageTransitionEvent('pagehide'));
      else editorTheme.dispose();
    }, studio);
    const after = await listeners();
    assert.deepEqual(after, [], 'Disposal must remove all four motion listeners');
    const gate = await page.evaluate(() => {
      for (const event of ['focus','blur','pageshow']) window.dispatchEvent(new Event(event));
      document.dispatchEvent(new Event('visibilitychange'));
      return document.documentElement.dataset.xboxMotion;
    });
    assert.equal(gate, undefined, 'Disposed motion must not reactivate');
    return {before,after,reactivated:false};
  } finally {
    await cdp.send('Runtime.releaseObjectGroup', {objectGroup:'xbox-listeners'});
    await cdp.detach();
  }
}

async function noChromeMotion(page, studio = false) {
  const result = await page.evaluate(studio => ({gate:document.documentElement.dataset.xboxMotion,
    content:getComputedStyle(document.querySelector(studio?'#commands':'.appBar'),'::before').content,
    animations:document.getAnimations().filter(a => a.animationName?.startsWith('xbox')).length}), studio);
  assert.deepEqual(result, {gate:undefined,content:'none',animations:0}, 'Theme exit must remove all Xbox effects');
}

(async () => {
  host = await startHost();
  browser = await chromium.launch({headless: true, channel: 'chrome', args: ['--disable-background-networking']});
  let context = await browser.newContext({viewport: {width: 1600, height: 1000}});
  // All tested application traffic must remain on loopback, including optional telemetry.
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/])/, route => route.abort());
  let editor = await openEditor(context);
  await editor.locator('#workspaceDockWidth').press('ArrowLeft');
  await editor.evaluate(() => KfpsEditorPreferences.flush());
  const dockWidth = await editor.locator('#workspaceDockWidth').getAttribute('aria-valuenow');
  const artwork = await editor.evaluate(async () => {
    await loadPayload({shapes: Array.from({length: 24}, (_, i) => ({type: 1048677 + i % 8,
      color: [80 + i * 5, 110, 160, 255], data: [(i % 6) * 120 - 300, Math.floor(i / 6) * 120 - 180, .7, .7, i * 9, 0, 0]}))});
    return JSON.stringify(vinylObjects().map(o => o.toObject()));
  });
  const layout = await geometry(editor, '.workspace,.canvasStage,.rightDock,.toolRail');
  for (const id of ['pastel', 'dark', 'blackout', 'whiteout']) {
    await editorSelect(editor, id);
    const before = await state(editor);
    await editorSelect(editor, 'builtin:xbox');
    assert.equal((await state(editor)).base, 'builtin:xbox');
    assert.deepEqual(await geometry(editor, '.workspace,.canvasStage,.rightDock,.toolRail'), layout);
    await editorSelect(editor, id);
    assert.deepEqual(await state(editor), before);
    await noChromeMotion(editor);
  }
  await editorSelect(editor, 'builtin:xbox');
  report.editorMotion = await chromeMotion(editor);
  assert.equal(await editor.evaluate(() => JSON.stringify(vinylObjects().map(o => o.toObject()))), artwork);
  report.protectedArtworkControls = await protectedArtworkStyles(editor);
  report.customPaletteContrast = await customPaletteContrast(editor);
  const colors = await editor.evaluate(() => {
    const node = canvas.lowerCanvasEl, data = node.getContext('2d').getImageData(0,0,node.width,node.height).data;
    const colors = new Set(); for(let i=0;i<data.length;i+=400) colors.add(`${data[i]},${data[i+1]},${data[i+2]}`);
    return colors.size;
  });
  assert.ok(colors > 24, 'Editor canvas should contain rendered artwork, not a blank surface');
  report.canvasSampleColors = colors;
  report.checks.push('Editor: all four original themes restored exactly; canvas objects and docking geometry unchanged');
  await editor.screenshot({path: path.join(output, 'editor-xbox-1600.png')});
  await editorAdjust(editor);
  await editor.locator('[data-theme-var="--accent"]').fill('invalid-color');
  assert.equal(await editor.locator('#saveThemeAdjust').isDisabled(), true);
  await editor.locator('#resetThemeAdjust').click();
  await editor.locator('[data-theme-var="--accent"]').fill('#ffcc55');
  await editor.locator('#closeThemeAdjust').click();
  assert.equal((await state(editor)).accent, '#a1e52c');
  await editorAdjust(editor);
  await editor.locator('#themeAdjustName').fill('Xbox headless custom');
  await editor.locator('[data-theme-var="--accent"]').fill('#ffcc55');
  await editor.locator('#saveThemeAdjust').click();
  await editor.locator('#themeAdjustDialog').waitFor({state: 'hidden'});
  await editor.evaluate(() => KfpsEditorPreferences.flush());
  const editorCustom = await state(editor);
  assert.equal(editorCustom.base, 'builtin:xbox'); assert.equal(editorCustom.accent, '#ffcc55');
  await editor.reload();
  await editor.waitForFunction(() => document.documentElement.dataset.editorTheme === 'custom');
  assert.deepEqual(await state(editor), editorCustom);
  assert.equal(await editor.locator('.appBar').evaluate(node => getComputedStyle(node,'::before').animationName), 'xboxHeaderDrift');
  assert.match(await editor.locator('.appBar').evaluate(node => getComputedStyle(node,'::before').backgroundImage), /rgb\(255, 204, 85\)/);
  report.checks.push('Editor: invalid-color guard, reset, preview cancel, custom save and reload');
  await editor.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
  for (const size of [{width:1600,height:1000},{width:900,height:700}]) {
    await editor.setViewportSize(size);
    await editorAdjust(editor);
    assert.ok(await fits(editor, '#themeAdjustDialog'), `Editor dialog overflow: ${size.width}`);
    await editor.screenshot({path: path.join(output, `editor-custom-dialog-${size.width}.png`)});
    await editor.locator('#closeThemeAdjust').click();
  }
  let studio = await openStudio(context);
  for (const id of ['pastel','dark','blackout','whiteout']) {
    await studioSelect(studio, id); const before = await state(studio, true);
    const bounds = await geometry(studio, '#workspace,#viewport,#library,#authoring');
    await studioSelect(studio, 'builtin:xbox');
    assert.deepEqual(await geometry(studio, '#workspace,#viewport,#library,#authoring'), bounds);
    await studioSelect(studio, id); assert.deepEqual(await state(studio, true), before);
    await noChromeMotion(studio, true);
  }
  await studioSelect(studio, 'builtin:xbox');
  report.studioMotion = await chromeMotion(studio, true);
  const studioBuiltin = await state(studio, true);
  assert.equal(studioBuiltin.accent, '#a1e52c');
  await studio.locator('#showTheme').click();
  report.studioCustomPaletteContrast = await customPaletteContrast(studio, true);
  await settleChromeEntrance(studio);
  await studio.screenshot({path: path.join(output, 'studio-xbox-appearance-1600.png')});
  await studio.locator('[data-theme-var="--accent"]').fill('invalid-color');
  assert.ok(await studio.locator('#applyTheme').isDisabled());
  await studio.locator('#themeCancel').click();
  assert.deepEqual(await state(studio, true), studioBuiltin);
  await studio.locator('#showTheme').click();
  await studio.locator('#themeName').fill('Studio edited Xbox');
  await studio.locator('[data-theme-var="--accent"]').fill('#ffcc55');
  const downloadPromise = studio.waitForEvent('download');
  await studio.locator('#downloadTheme').click();
  const download = await downloadPromise;
  const exported = path.join(output, 'studio-edited-xbox.json');
  await download.saveAs(exported);
  assert.equal(JSON.parse(fs.readFileSync(exported, 'utf8')).base, 'builtin:xbox');
  await studio.locator('#applyTheme').click();
  await studio.locator('#themeDialog').waitFor({state: 'hidden'});
  const studioCustom = await state(studio, true);
  assert.equal(studioCustom.accent, '#ffcc55');
  await studio.reload();
  await studio.waitForFunction(() => !document.querySelector('#showTheme').disabled);
  assert.deepEqual(await state(studio, true), studioCustom);
  assert.equal(await studio.locator('#commands').evaluate(node => getComputedStyle(node,'::before').animationName), 'xboxHeaderDrift');
  assert.match(await studio.locator('#commands').evaluate(node => getComputedStyle(node,'::before').backgroundImage), /rgb\(255, 204, 85\)/);
  await studioSelect(studio, 'whiteout', false);
  await studio.locator('#themeFile').setInputFiles(exported);
  await studio.locator('#applyTheme').click();
  await studio.locator('#themeDialog').waitFor({state:'hidden'});
  assert.deepEqual(await state(studio, true), studioCustom);
  for (const size of [{width:1600,height:1000},{width:900,height:700},{width:390,height:844}]) {
    await studio.setViewportSize(size); await studio.locator('#showTheme').click();
    assert.ok(await fits(studio, '#themeDialog'), `Studio dialog overflow: ${size.width}`);
    await studio.screenshot({path:path.join(output, `studio-custom-dialog-${size.width}.png`)});
    await studio.locator('#themeCancel').click();
  }
  report.checks.push('Studio: all original themes, geometry, invalid color, cancel, custom edit, export/import and reload');
  report.editorMotionDisposal = await disposedMotionListeners(editor);
  report.studioMotionDisposal = await disposedMotionListeners(studio, true);
  await context.close(); await host.stop(); host = null;
  host = await startHost();
  context = await browser.newContext({viewport:{width:1600,height:1000}});
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/])/, route => route.abort());
  editor = await openEditor(context); studio = await openStudio(context);
  assert.deepEqual(await state(editor), editorCustom);
  assert.deepEqual(await state(studio, true), studioCustom);
  assert.equal(await editor.locator('#workspaceDockWidth').getAttribute('aria-valuenow'), dockWidth);
  await editorSelect(editor, 'builtin:xbox'); await studioSelect(studio, 'builtin:xbox');
  await context.close(); await host.stop(); host = null;
  host = await startHost();
  context = await browser.newContext({viewport:{width:1600,height:1000}});
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/])/, route => route.abort());
  editor = await openEditor(context); studio = await openStudio(context);
  assert.equal((await state(editor)).id, 'builtin:xbox'); assert.equal((await state(studio, true)).id, 'builtin:xbox');
  await studioSelect(studio, 'host'); assert.equal((await state(studio, true)).base, 'dark');
  await editorSelect(editor, 'pastel'); assert.equal((await state(editor)).base, 'pastel');
  await noChromeMotion(studio, true); await noChromeMotion(editor);
  report.checks.push('Both: fresh processes and empty browser storage restore built-in and custom Xbox; saved dock width preserved; revert to default/host');
  report.passed = true;
})().catch(error => {report.passed = false; report.error = error.stack; process.exitCode = 1; console.error(error);})
  .finally(async () => {
    if (!report.passed && browser) {
      for (const [i, page] of browser.contexts().flatMap(context => context.pages()).entries()) {
        await page.screenshot({path: path.join(output, `failure-${i}.png`)}).catch(() => {});
      }
    }
    if (browser) await browser.close();
    if (host) await host.stop();
    log.end();
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  });
