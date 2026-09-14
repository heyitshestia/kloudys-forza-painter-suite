const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');
const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const output = config.output;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const state = () => JSON.parse(fs.readFileSync(path.join(output, 'state.json'), 'utf8'));
async function until(fn) {
  for (let i = 0; i < 600; i++) {
    if (await fn()) return;
    await pause(50);
  }
  throw Error('Timed out waiting for native state');
}
(async () => {
  let browser, page;
  const errors = [], checks = [];
  try {
    await until(async () => {try {return (await fetch(`http://127.0.0.1:${config.port}/json/version`)).ok;} catch {return false;}});
    browser = await chromium.connectOverCDP(`http://127.0.0.1:${config.port}`, {noDefaults: true});
    async function attach() {
      await until(() => browser.contexts().some(c => c.pages().some(p => p.url() === state().url)));
      page = browser.contexts().flatMap(c => c.pages()).find(p => p.url() === state().url);
      page.on('pageerror', e => errors.push(String(e)));
      await page.waitForFunction(() => window.__kfpsViewerDiagnostics?.().ready, null, {timeout: 30000});
      await until(() => state().ready);
    }
    await attach();
    const diag = () => page.evaluate(() => window.__kfpsViewerDiagnostics());
    assert.equal(await page.locator('#wheels').isChecked(), !config.expectHidden);
    assert.equal((await diag()).wheels.visible, !config.expectHidden);
    assert.equal((await diag()).wheels.count, 4);
    checks.push(config.expectHidden ? 'Hidden choice restored in fresh native process' : 'First-run wheels on');
    await page.locator('#wheels').check();
    await until(() => state().visible);
    await pause(200);
    const initial = await diag(), originalUrl = page.url();
    await page.locator('#canvas').screenshot({path: path.join(output, 'wheels-on.png')});
    await page.locator('#wheels').uncheck();
    await until(() => !state().visible);
    await pause(200);
    await page.locator('#canvas').screenshot({path: path.join(output, 'wheels-off.png')});
    const hidden = await diag();
    assert.equal(hidden.wheels.visible, false);
    assert.ok(hidden.rendering.triangles < initial.rendering.triangles);
    assert.deepEqual(hidden.tracked, initial.tracked);
    assert.equal(page.url(), originalUrl);
    checks.push('Current wheels hidden without reload or resource reallocation');
    const part = page.locator('#parts select').first();
    if (await part.count()) {
      const value = await part.locator('option').last().getAttribute('value');
      await part.selectOption(value);
    }
    if (await page.locator('[data-section="left"]').isEnabled()) await page.locator('[data-section="left"]').click();
    await page.locator('#reset').click();
    await page.locator('#rotate').click();
    const frame = (await diag()).rendering.frames;
    await pause(450);
    assert.ok((await diag()).rendering.frames > frame);
    assert.equal((await diag()).wheels.visible, false);
    await page.locator('#rotate').click();
    checks.push('Parts, sections, reset and moving camera preserve hidden wheels');
    for (let i = 0; i < 30; i++) await page.locator('#wheels').click();
    await until(() => !state().visible);
    assert.deepEqual((await diag()).tracked, initial.tracked);
    checks.push('Thirty toggles retain stable resource counts');
    await page.locator('#reset').click();
    await pause(200);
    await page.setViewportSize({width: 380, height: 650});
    const box = await page.locator('.hud-right').boundingBox();
    assert.ok(box && box.x >= 0 && box.x + box.width <= 380);
    await page.screenshot({path: path.join(output, 'viewer-narrow.png')});
    await page.setViewportSize({width: 1000, height: 740});
    await page.screenshot({path: path.join(output, 'viewer-desktop.png')});
    checks.push('Narrow/desktop control layout');
    let sequence = state().sequence;
    for (let car = 2; car <= (config.realCases.length || 4); car++) {
      const previousUrl = page.url();
      sequence++;
      fs.writeFileSync(path.join(output, 'command.json'), JSON.stringify({operation: 'next', sequence}));
      await until(() => state().sequence === sequence && state().url !== previousUrl);
      await attach();
      assert.equal(await page.locator('#wheels').isChecked(), false);
      assert.equal((await diag()).wheels.visible, false);
      assert.equal((await diag()).wheels.count, !config.realCases.length && car === 3 ? 0 : 4);
      if (config.realCases.length) {
        await pause(200);
        const hiddenTriangles = (await diag()).rendering.triangles;
        await page.locator('#canvas').screenshot({path: path.join(output, `car-${car}-off.png`)});
        await page.locator('#wheels').check();
        await until(() => state().visible);
        await pause(200);
        assert.ok((await diag()).rendering.triangles > hiddenTriangles);
        await page.locator('#canvas').screenshot({path: path.join(output, `car-${car}-on.png`)});
        await page.locator('#wheels').uncheck();
        await until(() => !state().visible);
      }
      checks.push(`New car ${car} starts hidden${!config.realCases.length && car === 3 ? ' without assembly metadata' : ''}`);
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({passed: true, checks, errors, initial, hidden}, null, 2));
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({path: path.join(output, 'failure.png')}).catch(() => {});
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({passed: false, checks, errors, error: String(error.stack)}, null, 2));
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
})();
