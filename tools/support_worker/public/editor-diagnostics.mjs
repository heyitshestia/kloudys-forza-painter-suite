// Matches the local diagnostic schema. No message, stack, path or artwork fields.
export const NUMBERS = new Set(`at duration line code shapeType selected frames frameP50 frameP95 frameP99 frameMax gaps50 gaps100 gaps250 gaps500 tasks taskMax totalTasks totalGaps100 totalGaps500 renderMax renderCount layers objects helpers zoom width height referenceWidth referenceHeight referenceChars referenceOpacity history heapBytes revision browserRevision serverRevision browserAt serverAt pendingRevision uiLag dropped seq rendererPid rssBytes childRssBytes draws totalDraws selectedId buttons modifiers clientDrops editorRevision`.split(' '));
export const BOOLS = new Set('visible focused referenceAbove referenceVisible browserOk serverOk ready minimized'.split(' '));
export const ASSETS = ['index.html', 'editor.js', 'editor-core.js', 'editor-fabric-adapter.js', 'editor-diagnostics.js', 'editor-preferences.js', 'editor-persistence.js', 'editor-persistence-worker.js', 'editor-pixel-core.js', 'editor-pixel-worker.js', 'editor-assets.js', 'editor-i18n.js', 'vendor/fabric.min.js', 'locales/en.js', 'locales/ko.js'];
export const ENUMS = {
  kind: 'page-start action-start action-end command edit long-task frame-stall js-error rejection resource-error console-warning console-error webgl-lost webgl-restored canvas-lost canvas-restored preview-fallback recovery-result native-start native-ready native-failed native-reload native-close renderer-stopped close-timeout heartbeat-stale'.split(' '),
  action: 'idle pointer move scale skew rotate pan zoom guide select reference numeric nudge undo redo add duplicate delete copy paste color mask order group layout save load new export asset text pixel settings edit'.split(' '),
  renderer: ['fabric', 'gpu-preview', 'fallback', 'starting'],
  state: ['pending', 'saved', 'failed', 'idle', 'starting', 'ready', 'closed'],
  error: ['Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError', 'SecurityError', 'AbortError', 'QuotaExceededError', 'unknown'],
  source: [...ASSETS, 'native', 'unknown'],
};
const record = v => v && typeof v === 'object' && !Array.isArray(v) ? v : {};
const number = v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= Number.MAX_SAFE_INTEGER;
function fields(value) {
  return Object.fromEntries(Object.entries(record(value)).filter(([key, v]) =>
    NUMBERS.has(key) && number(v) || BOOLS.has(key) && typeof v === 'boolean' || Object.hasOwn(ENUMS, key) && ENUMS[key].includes(v)));
}
export function normalizeEditor(value) {
  const v = record(value);
  if (['snapshot_unreadable', 'snapshot_too_large'].includes(v.unavailable)) return {unavailable: v.unavailable};
  if (v.schema !== 'kfps-editor-diagnostics/1') return {};
  const result = {schema: v.schema, native: fields(v.native), page: {}, recent: [], installed_assets: {}, logging: {}};
  for (const key of ['age_seconds', 'page_age_seconds']) if (number(v[key]) && v[key] >= 0) result[key] = v[key];
  if (typeof v.version === 'string' && /^[0-9.\-a-zA-Z]{1,40}$/.test(v.version)) result.version = v.version;
  const p = record(v.page);
  // The page ID is an ephemeral diagnostic correlation ID, never an auth token.
  if (typeof p.page === 'string' && /^[a-f0-9]{32}$/.test(p.page) && Number.isSafeInteger(p.seq) && p.seq >= 0) {
    result.page = {page: p.page, seq: p.seq, metrics: fields(p.metrics), state: fields(p.state), recovery: fields(p.recovery),
      events: (Array.isArray(p.events) ? p.events : []).slice(-48).map(fields).filter(e => e.kind)};
  }
  result.recent = (Array.isArray(v.recent) ? v.recent : []).slice(-16).map(fields).filter(e => e.kind);
  for (const key of ASSETS) {
    const hash = v.installed_assets?.[key];
    if (typeof hash === 'string' && (hash === 'missing' || /^[a-f0-9]{64}$/.test(hash))) result.installed_assets[key] = hash;
  }
  for (const key of ['accepted', 'written', 'dropped', 'last_write']) if (number(v.logging?.[key])) result.logging[key] = v.logging[key];
  if (typeof v.logging?.failed === 'boolean') result.logging.failed = v.logging.failed;
  return result;
}
