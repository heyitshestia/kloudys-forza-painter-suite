"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor.js"), "utf8");
const context = vm.createContext({
  KfpsI18n: { t: (s, ...args) => s.replace(/\{(\d+)\}/g, (_, i) => args[i]) },
  setText() {}, setStatus() {}, renderShortcutEditor() {}, updateShortcutLabels() {},
});
vm.runInContext(source.slice(source.indexOf("const DEFAULT_SHORTCUTS ="), source.indexOf("const SHORTCUT_LABELS =")) + `
  const SHORTCUT_LABELS = DEFAULT_SHORTCUTS, SHORTCUTS_KEY = 'shortcuts';
  let saved = '{}', shortcutLoadWarnings = [], shortcutStatusMessage = '', shortcuts;
  const editorSettings = { getItem: () => saved, setItem: (_, value) => { saved = value; } };
` + source.slice(source.indexOf("function normalizeShortcutKey("), source.indexOf("function updateShortcutLabels(")), context);
const run = expression => vm.runInContext(expression, context);
const load = value => { context.fixture = value; return run("saved=fixture; shortcuts=loadShortcuts(); JSON.stringify(shortcuts)"); };
load('{}');
const defaults = JSON.parse(run("JSON.stringify(DEFAULT_SHORTCUTS)"));
for (const [action, combo] of Object.entries(defaults)) {
  context.action = action; context.combo = combo;
  assert.equal(run("shortcutBindingIssue(action, normalizeShortcutCombo(combo))"), "", `Default rejected: ${action}`);
}
const protectedCombos = ['ArrowLeft', 'Ctrl+ArrowRight', 'Shift+ArrowUp', 'Alt+ArrowDown', 'Home', 'End',
  'Ctrl+PageDown', 'Tab', 'Shift+Tab', 'Enter', 'Escape', 'Backspace', 'Ctrl+Backspace', 'Shift+Delete',
  'Ctrl+Alt+Delete', 'Space', 'Ctrl+Space', 'Alt+Space', 'Shift+Insert', 'Win+R', 'Meta+L', 'Alt+F4',
  'CapsLock', 'PrintScreen', 'F1', 'F3', 'F4', 'F5', 'Shift+F5', 'F6', 'F7', 'F10', 'F11', 'F12',
  'Ctrl+L', 'Ctrl+R', 'Ctrl+S', 'Ctrl+O', 'Ctrl+N', 'Ctrl+W', 'Ctrl+T', 'Ctrl+Shift+T', 'Ctrl+Shift+W',
  'Ctrl+Shift+C', 'Ctrl+Shift+I', 'Ctrl+Shift+J', 'Ctrl+0', 'Ctrl+9', 'Ctrl++', 'Ctrl+Shift++', 'Ctrl+-', 'Alt+D', 'Alt+F'];
let rejected = 0;
for (const action of Object.keys(defaults)) for (const combo of protectedCombos) {
  if ((action === 'toggleReference' && combo === 'Space') || (action === 'delete' && combo === 'Backspace')) continue;
  load('{}'); context.action = action; context.combo = combo;
  assert.equal(run("setShortcut(action, combo)"), false, `${action} accepted ${combo}`);
  assert.equal(run("JSON.stringify(shortcuts)"), JSON.stringify(defaults));
  assert.equal(run("saved"), '{}', 'Rejected shortcut wrote settings');
  rejected++;
}
for (const value of ['Ctrl', 'Control+Shift', 'Ctrl+', 'A+B', 'Ctrl+A+B', 'Ctrl++A', 'UnknownKey', 42, {}]) {
  load('{}'); context.combo = value;
  assert.equal(run("setShortcut('colorSlot1', combo)"), false, `Malformed shortcut accepted: ${JSON.stringify(value)}`);
}
assert.equal(run("normalizeShortcutCombo('ctrl++')"), 'Ctrl+Plus');
assert.equal(run("normalizeShortcutCombo('shift+control+f8')"), 'Ctrl+Shift+F8');
for (const action of Object.keys(defaults).filter(action => action.startsWith('colorSlot') || action === 'toggleReference')) {
  load('{}'); context.action = action;
  assert.equal(run("setShortcut(action, 'Ctrl+Shift+2')"), true);
  run("shortcuts=loadShortcuts()");
  assert.equal(run("shortcutFor(action)"), 'Ctrl+Shift+2');
}
let loaded = JSON.parse(load(JSON.stringify({ duplicate: '1', colorSlot2: 'F5', colorSlot3: 'Meta+R', colorSlot4: 'F8',
  colorSlot5: 'F8', colorSlot6: '', toggleReference: 'ArrowLeft' })));
assert.equal(loaded.duplicate, '1'); assert.equal(loaded.colorSlot1, '');
assert.equal(loaded.colorSlot2, '2'); assert.equal(loaded.colorSlot3, '3');
assert.equal(loaded.colorSlot4, 'F8'); assert.equal(loaded.colorSlot5, '');
assert.equal(loaded.colorSlot6, ''); assert.equal(loaded.toggleReference, 'Space');
assert.equal(new Set(Object.values(loaded).filter(Boolean)).size, Object.values(loaded).filter(Boolean).length);
assert.ok(run("shortcutLoadWarnings.length >= 4"));
run("saveShortcuts(); shortcuts=loadShortcuts()");
assert.equal(run("shortcutFor('colorSlot6')"), '', 'Disabled binding revived after restart');
for (const malformed of ['null', '[]', '17', '"string"', '{broken']) {
  assert.equal(load(malformed), JSON.stringify(defaults));
  assert.ok(run("shortcutLoadWarnings.length"));
}
load('{}');
for (const event of [{ key: 'Process' }, { key: 'Dead' }, { key: 'AltGraph' }, { key: '1', isComposing: true },
  { key: '1', keyCode: 229 }, { key: '1', ctrlKey: true, altKey: true, getModifierState: key => key === 'AltGraph' }]) {
  context.event = event;
  assert.equal(run("eventToShortcutCombo(event)"), '');
}
context.event = { key: '+', ctrlKey: true };
assert.equal(run("eventToShortcutCombo(event)"), 'Ctrl+Plus');
context.event = { key: '9', ctrlKey: true, altKey: true, getModifierState: () => false };
assert.equal(run("eventToShortcutCombo(event)"), 'Ctrl+Alt+9', 'Genuine Ctrl+Alt binding was lost');
console.log(`Shortcuts: ${rejected} protected binding cases, all defaults/17 new actions, migration, duplicate/disabled settings, malformed input and IME/AltGr passed`);
