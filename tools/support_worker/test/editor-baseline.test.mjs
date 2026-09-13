import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeEditor} from '../public/editor-diagnostics.mjs';

test('native runtime identity survives support normalization without paths or arbitrary text', () => {
  const runtime = {status:'verified', python:'3.12.10', bits:64, pyside:'6.11.1',
    qt:'6.11.1', webengine:'6.11.1', chromium:'140.0.7339.225', baseline:'a'.repeat(64),
    files:9000, bytes:940000000, verification_ms:1200};
  const result = normalizeEditor({schema:'kfps-editor-diagnostics/1', editor_runtime:{...runtime,
    path:'C:/private', message:'private report', token:'secret'}});
  assert.deepEqual(result.editor_runtime,runtime);
  assert.deepEqual(normalizeEditor({schema:'kfps-editor-diagnostics/1', editor_runtime:{
    python:'C:/private', status:'anything', baseline:'secret', files:Infinity, bits:-1}}).editor_runtime,undefined);
});
