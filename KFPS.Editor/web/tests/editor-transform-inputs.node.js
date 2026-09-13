const assert = require('node:assert/strict');
require('node:events').setMaxListeners(0);
const { create } = require('../editor-transform-inputs.js');
function fixture() {
  const element = () => Object.assign(new EventTarget(), { value: '0', dataset: { step: '1' }, setAttribute() {} });
  const fields = Object.fromEntries(['xInput', 'yInput', 'sxInput', 'syInput', 'rotInput', 'skewInput'].map(id => [id, element()]));
  const label = Object.assign(element(), { dataset: { numericFor: 'rotInput' }, captured: null,
    setPointerCapture(id) { this.captured = id; }, hasPointerCapture(id) { return this.captured === id; }, releasePointerCapture() { this.captured = null; } });
  const win = new EventTarget(), state = { generation: 1, object: { angle: 0 }, commits: 0, applied: 0, errors: 0, failView: false };
  const owner = create({ scene: { selected: () => state.object, contains: object => state.object === object,
    generation: () => state.generation, snapshot: object => ({ ...object }), restore: (object, shape) => Object.assign(object, shape) },
    edits: { flushNudge() {}, apply(options) { state.object.angle = Number(fields.rotInput.value); state.applied++; if (!options?.preview) state.commits++; return true; }, commit() { state.commits++; } },
    view: { element: id => fields[id], refresh() { fields.rotInput.value = String(state.object.angle); if (state.failView) throw Error('display'); },
      syncMasks() {}, render() {}, invalid() {}, error() { state.errors++; } }, parse: Number, round: value => value,
    document: { querySelectorAll: () => [label], activeElement: null }, window: win });
  const fire = (target, type, values = {}) => target.dispatchEvent(Object.assign(new Event(type, { cancelable: true }), values));
  const down = () => fire(label, 'pointerdown', { button: 0, pointerId: 7, clientX: 0 });
  const move = () => fire(label, 'pointermove', { pointerId: 7, clientX: 30 });
  return { owner, fields, label, win, state, fire, down, move };
}
{
  const f = fixture(); f.down(); f.move(); f.state.failView = true;
  f.owner.cancel(); assert.equal(f.state.object.angle, 0); assert.equal(f.state.commits, 0);
  assert.equal(f.label.captured, null); assert.equal(f.owner.active, false); assert.equal(f.state.errors, 1); f.owner.dispose();
}
{
  const f = fixture(); f.down(); f.move(); f.state.generation++;
  f.state.object = { angle: 12 }; f.fire(f.label, 'pointerup', { pointerId: 7 });
  assert.equal(f.state.object.angle, 12); assert.equal(f.state.commits, 0); assert.equal(f.label.captured, null); f.owner.dispose();
}
{
  const f = fixture(); const field = f.fields.rotInput; f.fire(field, 'focus'); field.value = '45';
  f.fire(field, 'keydown', { key: 'Enter', repeat: true }); f.fire(field, 'keydown', { key: 'Enter', isComposing: true });
  assert.equal(f.state.commits, 0); f.fire(field, 'keydown', { key: 'Enter' }); f.fire(field, 'blur');
  assert.equal(f.state.commits, 1); f.state.generation++; field.value = '90'; f.fire(field, 'blur');
  assert.equal(f.state.object.angle, 45); f.owner.dispose();
}
{
  const f = fixture(); f.down(); f.move(); f.fire(f.label, 'pointerup', { pointerId: 8 });
  assert.equal(f.owner.active, true); f.fire(f.label, 'pointerup', { pointerId: 7 });
  assert.equal(f.state.commits, 1); assert.equal(f.label.captured, null); f.owner.dispose();
}
{
  const f = fixture(); f.down(); f.move(); f.owner.dispose(); f.owner.dispose();
  assert.equal(f.state.object.angle, 0); assert.equal(f.label.captured, null);
  f.down(); f.move(); assert.equal(f.owner.active, false); assert.equal(f.state.commits, 0);
}
console.log('Transform input owner: 5 lifetime, capture and commit cases passed');
