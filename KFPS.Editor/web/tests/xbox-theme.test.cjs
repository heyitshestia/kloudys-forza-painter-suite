"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const root = path.resolve(__dirname, '../../..');

(async () => {
  const {PALETTES, COLOR_KEYS, normalizeTheme, FORMAT} = await import(pathToFileURL(
    path.join(root, 'tools/livery-studio/src/web/theme-adapter.mjs')));
  const css = fs.readFileSync(path.join(root, 'KFPS.Editor/web/style.css'), 'utf8');
  const blocks = {pastel: css.match(/:root\s*\{([^}]+)\}/)[1]};
  for (const name of Object.keys(PALETTES).filter(name => name !== 'pastel')) {
    blocks[name] = css.match(new RegExp(`:root\\[data-editor-theme-base="${name}"\\]\\s*\\{([^}]+)\\}`))[1];
  }
  assert.equal(COLOR_KEYS.length, 33);
  for (const [name, palette] of Object.entries(PALETTES)) {
    const values = Object.fromEntries([...blocks[name].matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(m => [m[1], m[2].trim()]));
    assert.deepEqual(Object.keys(palette).sort(), [...COLOR_KEYS].sort());
    for (const key of COLOR_KEYS) assert.equal(values[key], palette[key], `${name} ${key} parity`);
    assert.equal(normalizeTheme({id: name}).base, name);
  }
  const theme = normalizeTheme({id: 'builtin:xbox'});
  assert.equal(theme.name, 'Original Xbox');
  assert.equal(theme.format, FORMAT);
  assert.equal(theme.colorScheme, 'dark');
  const custom = normalizeTheme({...theme, id: 'custom-xbox', values: {...theme.values, '--accent': '#ffcc55'}});
  assert.equal(custom.base, 'builtin:xbox');
  assert.equal(custom.values['--accent'], '#ffcc55');
  assert.deepEqual(normalizeTheme(JSON.parse(JSON.stringify(custom))), custom);
  assert.throws(() => normalizeTheme({...theme, values: {'--accent': 'url(https://invalid)'}}));
  const luminance = color => color.slice(1).match(/../g).map(c => parseInt(c, 16) / 255)
    .map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4)
    .reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
  const contrast = (a, b) => (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  let minimum = Infinity;
  for (const foreground of ['--text','--muted','--soft','--accent','--warn','--danger']) {
    for (const background of ['--shell','--panel','--panel2','--panel3','--dialog-header']) {
      const ratio = contrast(luminance(theme.values[foreground]), luminance(theme.values[background]));
      assert.ok(ratio >= 4.5, `${foreground}/${background}: ${ratio.toFixed(2)}`);
      minimum = Math.min(minimum, ratio);
    }
  }
  console.log(JSON.stringify({palettes: Object.keys(PALETTES), keys: 33, minimumTextContrast: minimum,
    customRoundtrip: true, unsafeColorRejected: true}));
})().catch(error => {console.error(error); process.exitCode = 1;});
