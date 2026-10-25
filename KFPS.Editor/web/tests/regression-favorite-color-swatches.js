async (page, testOptions = {}) => {
  const fs = require('node:fs');
  const path = require('node:path');
  const check = (value, message) => { if (!value) throw Error(message); };
  const appRoot = path.resolve(__dirname, '../../..');
  const privateRoot = path.join(appRoot, 'runtime/test-runs/color-palette-20261021');
  const within = (root, candidate) => {
    const relative = path.relative(root, path.resolve(candidate));
    return relative !== '' && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
  };
  check(within(privateRoot, output), 'Use a fresh output directory inside runtime/test-runs/color-palette-20261021');
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  check(processInfo.profile && within(privateRoot, processInfo.profile), 'Refusing a non-private palette profile');
  check(path.resolve(processInfo.appRoot) === appRoot, 'This regression must run against this DIRTY checkout');
  check(processInfo.exportRoot && within(privateRoot, processInfo.exportRoot), 'Pass a private --export-root inside the palette run directory');
  page.setDefaultTimeout(15000);

  const colors = ['#e74768', '#16a675', '#397cde'];
  const neutral = '#d6b82a';
  const swatch = index => page.locator('#favoriteColorGrid .favoriteColorSwatch').nth(index);
  const report = { host: testOptions.browserHost ? 'chrome' : 'native', colors, captures: [], reload: false };
  const record = () => fs.writeFileSync(path.join(output, 'favorite-color-swatches.json'), JSON.stringify(report, null, 2));
  const ready = () => page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsWorkspace
    && document.documentElement.classList.contains('workspaceRedesign'));
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  async function openPalette() {
    await page.locator('#quickColorSwatch').click();
    await page.locator('#colorDialog').waitFor({ state: 'visible' });
  }
  async function closePalette() {
    await page.locator('#closeColorDialog').click();
    await page.locator('#colorDialog').waitFor({ state: 'hidden' });
  }
  async function chooseColor(hex) {
    // Exercise the actual color input handlers without opening an OS color chooser.
    await page.locator('#dialogColorPicker').evaluate((input, value) => {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, hex);
    await page.waitForFunction(value => document.querySelector('#dialogColorPicker').value === value
      && colorToHex(currentPanelColor()) === value, hex);
  }
  async function openView() {
    await page.locator('#workspaceViewMenu').click();
    await page.locator('#workspaceViewCommands').waitFor({ state: 'visible' });
  }
  async function selectTheme(theme) {
    await openView();
    await page.locator('#editorThemeSelect').selectOption(theme);
    await page.keyboard.press('Escape');
    await page.waitForFunction(id => document.documentElement.dataset.editorTheme === id, theme);
  }
  async function assertPalette(label) {
    const actual = await page.evaluate(() => ({
      colors: favoriteColors.map(color => color && colorToHex(color)),
      persisted: JSON.parse(editorSettings.getItem('kloudyFabricFavoriteColors')),
      count: document.querySelectorAll('#favoriteColorGrid .favoriteColorSwatch').length,
    }));
    check(actual.count === 16 && actual.colors.length === 16, `${label}: expected all 16 palette slots`);
    check(colors.every((color, i) => actual.colors[i] === color), `${label}: saved colors changed`);
    check(actual.colors.slice(colors.length).every(color => color === null), `${label}: empty slots changed`);
    check(actual.persisted?.length === 16 && colors.every((color, i) => actual.persisted[i]
      && color === '#' + actual.persisted[i].slice(0, 3).map(n => n.toString(16).padStart(2, '0')).join('')),
    `${label}: persisted favorites differ from the UI`);
  }
  async function capture(label, states) {
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#colorDialog')).opacity === '1');
    // Include delayed hover/focus hints in the occlusion map before sampling pixels.
    const hint = Object.entries(states).find(([, state]) => state.hover || state.focus);
    if (hint) await page.waitForFunction(index => {
      const slot = document.querySelectorAll('#favoriteColorGrid .favoriteColorSwatch')[index];
      return slot.getAttribute('aria-describedby')?.includes('workspaceTooltip')
        && document.querySelector('#workspaceTooltip').matches(':popover-open');
    }, Number(hint[0]));
    await settle();
    const geometry = await page.evaluate(() => {
      const rect = node => {
        const r = node.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom };
      };
      return {
        width: innerWidth, height: innerHeight, dpr: devicePixelRatio,
        theme: document.documentElement.dataset.editorTheme,
        dialog: rect(document.querySelector('#colorDialog')),
        occlusions: [...document.querySelectorAll('[role="tooltip"]')]
          .filter(node => node.getClientRects().length && !node.hidden).map(rect),
        slots: [...document.querySelectorAll('#favoriteColorGrid .favoriteColorSwatch')].map(node => {
          const shortcut = node.querySelector('.favoriteColorShortcut');
          const style = getComputedStyle(node), text = getComputedStyle(shortcut);
          return { rect: rect(node), label: rect(shortcut), text: shortcut.textContent,
            classes: [...node.classList], hover: node.matches(':hover'), focus: node.matches(':focus-visible'),
            shadow: style.boxShadow, background: style.backgroundImage, opacity: style.opacity,
            outlineStyle: style.outlineStyle, outlineWidth: parseFloat(style.outlineWidth),
            foreground: text.color, labelBackground: text.backgroundColor };
        }),
      };
    });
    const png = await page.screenshot({ path: path.join(output, label + '.png'), type: 'png', fullPage: false });
    // Decode the real compositor screenshot, not a synthetic rendering of computed CSS.
    const pixels = await page.evaluate(async ({ encoded, geometry, colors }) => {
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(Error('Screenshot PNG could not be decoded'));
        image.src = 'data:image/png;base64,' + encoded;
      });
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth; canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(image, 0, 0);
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const sx = canvas.width / geometry.width, sy = canvas.height / geometry.height;
      const rgb = css => css.match(/[\d.]+/g).slice(0, 3).map(Number);
      const luminance = channels => channels.map(n => n / 255).map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4)
        .reduce((sum, n, i) => sum + n * [.2126, .7152, .0722][i], 0);
      return geometry.slots.map((slot, index) => {
        const samples = [], r = slot.rect, text = slot.label;
        // Stay clear of rounded borders, focus rings, and the complete shortcut badge.
        for (let y = r.y + 7; y < r.bottom - 7; y += 1) {
          for (let x = r.x + 7; x < r.right - 7; x += 1) {
            if (x >= text.x - 2 && x <= text.right + 2 && y >= text.y - 2 && y <= text.bottom + 2) continue;
            if (geometry.occlusions.some(box => x >= box.x - 2 && x <= box.right + 2
              && y >= box.y - 2 && y <= box.bottom + 2)) continue;
            const px = Math.floor(x * sx), py = Math.floor(y * sy);
            if (px < 0 || py < 0 || px >= canvas.width || py >= canvas.height) continue;
            const offset = (py * canvas.width + px) * 4;
            samples.push([data[offset], data[offset + 1], data[offset + 2]]);
          }
        }
        const expected = colors[index]?.slice(1).match(/../g).map(n => parseInt(n, 16));
        const matching = expected ? samples.filter(sample => sample.every((n, i) => Math.abs(n - expected[i]) <= 12)).length : 0;
        const brightness = samples.map(sample => (sample[0] + sample[1] + sample[2]) / 3);
        const low = Math.min(...brightness), high = Math.max(...brightness), range = high - low;
        const a = luminance(rgb(slot.foreground)), b = luminance(rgb(slot.labelBackground));
        return { index, samples: samples.length, fillFraction: matching / samples.length,
          checkerRange: range,
          darkFraction: brightness.filter(n => n < low + range * .3).length / samples.length,
          lightFraction: brightness.filter(n => n > high - range * .3).length / samples.length,
          // This checks declared label colors, not opacity-composited contrast.
          labelStyleContrast: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
      });
    }, { encoded: png.toString('base64'), geometry, colors });
    report.captures.push({ label, geometry, pixels });
    record();
    const d = geometry.dialog;
    check(d.x >= 0 && d.y >= 0 && d.right <= geometry.width + 1 && d.bottom <= geometry.height + 1,
      `${label}: palette is clipped`);
    for (const [index, expected] of Object.entries(states)) {
      const actual = geometry.slots[index];
      for (const [state, value] of Object.entries(expected)) {
        const observed = ['hover', 'focus'].includes(state) ? actual[state] : actual.classes.includes(state);
        check(observed === value, `${label}: slot ${Number(index) + 1} ${state} expected ${value}, got ${observed}`);
      }
    }
    for (const sample of pixels) {
      const slot = geometry.slots[sample.index], r = slot.rect, text = slot.label;
      check(sample.samples >= 40, `${label}: slot ${sample.index + 1} has insufficient unobscured pixels`);
      check(text.x >= r.x && text.right <= r.right + 1 && text.y >= r.y && text.bottom <= r.bottom + 1
        && slot.text.trim() && sample.labelStyleContrast >= 4.5,
      `${label}: slot ${sample.index + 1} shortcut label layout or declared contrast changed`);
      if (slot.focus) check(slot.outlineStyle !== 'none' && slot.outlineWidth >= 1,
        `${label}: slot ${sample.index + 1} lost its keyboard focus indicator`);
      if (sample.index < colors.length) {
        check(!slot.classes.includes('empty') && sample.fillFraction >= .94,
          `${label}: saved slot ${sample.index + 1} lost its color fill (${Math.round(sample.fillFraction * 100)}% matching; box-shadow=${slot.shadow})`);
      } else {
        check(slot.classes.includes('empty') && sample.checkerRange >= 30 && sample.darkFraction >= .2 && sample.lightFraction >= .2,
          `${label}: empty slot ${sample.index + 1} lost its checkerboard`);
      }
    }
  }

  try {
    await ready();
    check(await page.evaluate(() => !isDocumentDirty() && !projectSaveInProgress && !editorCommands.busy
      && vinylObjects().length === 0 && favoriteColors.every(color => color === null)),
    'Use a fresh private profile with an empty, idle document and palette; do not reuse user settings');
    await page.setViewportSize({ width: 1760, height: 1040 });
    await selectTheme('dark');
    await openPalette();
    for (let index = 0; index < colors.length; index++) {
      check((await swatch(index).getAttribute('class')).split(' ').includes('empty'), `Slot ${index + 1} must start empty`);
      await swatch(index).click();
      await chooseColor(colors[index]);
      await page.locator('#saveFavoriteColor').click();
    }
    await closePalette();
    await openPalette();
    await assertPalette('close/reopen');
    await page.locator('#colorDialog h2').hover();
    await capture('dark-1760-reopened', { 0: { active: false, selected: false }, 2: { active: true, selected: true } });
    await closePalette();

    for (const theme of ['dark', 'whiteout', 'blackout', 'pastel', 'builtin:ps2', 'custom']) {
      if (theme === 'custom') {
        await openView();
        await page.locator('#adjustTheme').click();
        await page.locator('#themeAdjustDialog').waitFor({ state: 'visible' });
        await page.locator('#themeAdjustBase').selectOption('whiteout');
        await page.locator('#themeAdjustName').fill('Palette regression 20261021');
        await page.locator('[data-theme-var="--accent"]').fill('#146b57');
        await page.locator('#saveThemeAdjust').click();
        await page.locator('#themeAdjustDialog').waitFor({ state: 'hidden' });
        if (await page.locator('.workspaceMenu:popover-open').count()) await page.keyboard.press('Escape');
        await page.waitForFunction(() => document.documentElement.dataset.editorTheme === 'custom');
      } else await selectTheme(theme);
      for (const size of [{ width: 1760, height: 1040 }, { width: 1280, height: 800 }]) {
        await page.setViewportSize(size);
        await openPalette();
        const label = `${theme}-${size.width}x${size.height}`;
        await swatch(2).click();
        await page.locator('#colorDialog h2').hover();
        await capture(label + '-inactive', { 0: { selected: false, active: false, hover: false, focus: false },
          2: { active: true, selected: true } });
        await swatch(0).click();
        await chooseColor(neutral);
        await page.locator('#colorDialog h2').hover();
        await capture(label + '-selected', { 0: { selected: true, active: false } });
        await swatch(1).click();
        await swatch(15).click();
        await swatch(0).hover();
        await capture(label + '-hover', { 0: { selected: false, active: false, hover: true },
          1: { active: true, selected: false }, 15: { empty: true, selected: true } });
        await page.locator('#colorDialog h2').hover();
        await page.locator('#dialogColorPicker').focus();
        await page.keyboard.press('Tab');
        await capture(label + '-focus', { 0: { selected: false, active: false, hover: false, focus: true } });
        await assertPalette(label);
        await closePalette();
      }
    }
    await page.evaluate(async () => {
      await KfpsEditorPreferences.flush();
      if (isDocumentDirty() || projectSaveInProgress || editorCommands.busy) throw Error('Unsafe palette persistence reload');
    });
    await page.reload();
    await ready();
    await page.waitForFunction(() => document.documentElement.dataset.editorTheme === 'custom');
    await openPalette();
    await assertPalette('reload');
    await swatch(15).click();
    await chooseColor(neutral);
    await page.locator('#colorDialog h2').hover();
    await capture('custom-1280x800-reloaded', { 0: { active: false, selected: false },
      1: { active: false, selected: false }, 2: { active: false, selected: false }, 15: { selected: true, empty: true } });
    await closePalette();
    report.reload = true;
    report.passed = true;
    return { passed: true, host: report.host, captures: report.captures.length, reload: true,
      themes: ['dark', 'whiteout', 'blackout', 'pastel', 'builtin:ps2', 'custom'], sizes: ['1760x1040', '1280x800'],
      evidence: path.join(output, 'favorite-color-swatches.json') };
  } catch (error) {
    report.passed = false;
    report.error = String(error.stack || error);
    throw error;
  } finally {
    record();
  }
}
