// Matches the local diagnostic schema. No message, stack, path or artwork fields.
export const NUMBERS = new Set(`at duration line code shapeType selected frames frameP50 frameP95 frameP99 frameMax gaps50 gaps100 gaps250 gaps500 tasks taskMax totalTasks totalGaps100 totalGaps500 renderMax renderCount layers objects helpers zoom width height referenceWidth referenceHeight referenceChars referenceOpacity history heapBytes revision browserRevision serverRevision browserAt serverAt pendingRevision uiLag dropped seq rendererPid rssBytes childRssBytes draws totalDraws selectedId buttons modifiers clientDrops criticalDrops editorRevision operationId jobId documentGeneration queueDepth documentId commitId firstCommitId commandId inputId historyId workerDuration renderDuration meshCount cachePixels cacheCount`.split(' '));
export const BOOLS = new Set('visible focused referenceAbove referenceVisible browserOk serverOk ready minimized'.split(' '));
export const ASSETS = ["index.html", "editor.js", "editor-core.js", "editor-fabric-adapter.js", "editor-commands.js", "editor-transform-inputs.js", "editor-history.js", "editor-layer-groups.js", "editor-desktop-protocol.js", "editor-diagnostics.js", "editor-preferences.js", "editor-updates.js", "editor-persistence.js", "editor-projects.js", "editor-recovery.js", "editor-reference.js", "editor-renderer.js", "editor-catalog.js", "editor-themes.js", "editor-persistence-worker.js", "editor-pixel-core.js", "editor-pixel-worker.js", "editor-assets.js", "editor-i18n.js", "vendor/fabric.min.js", "locales/en.js", "locales/ko.js"];
export const ENUMS = {
  kind: 'page-start action-start action-end command edit commit checkpoint phase job long-task frame-stall js-error rejection resource-error console-warning console-error webgl-lost webgl-restored canvas-lost canvas-restored preview-fallback recovery-result native-start native-ready native-failed native-reload native-close native-sample renderer-stopped close-timeout heartbeat-stale'.split(' '),
  job: 'recovery browserRecovery readRecovery recoveryHead parseFile parseText fetchJSON referenceImage saveProject saveExport'.split(' '),
  action: 'idle pointer move scale skew rotate pan zoom guide select reference numeric nudge undo redo add duplicate delete copy paste color mask order group layout save load new export asset text pixel settings edit'.split(' '),
  renderer: ['fabric', 'gpu-preview', 'fallback', 'starting'],
  state: ['pending', 'committed', 'finished', 'cancelled', 'saved', 'failed', 'idle', 'starting', 'ready', 'closed'],
  error: ['Error', 'TypeError', 'RangeError', 'ReferenceError', 'SyntaxError', 'SecurityError', 'AbortError', 'QuotaExceededError', 'unknown'],
  errorCode: 'input_too_large recovery_too_large reference_too_large project_too_large export_too_large storage_busy storage_closed storage_failed worker_failed worker_timeout http_error invalid_response stale_revision recovery_head_unavailable project_exists project_conflict save_request_used'.split(' '),
  phase: 'document-build document-prewarm document-install document-retire document-present document-paint document-cache settled-paint'.split(' '),
  source: [...ASSETS, 'native', 'unknown'],
};
const record = v => v && typeof v === 'object' && !Array.isArray(v) ? v : {};
const number = v => typeof v === 'number' && Number.isFinite(v) && Math.abs(v) <= Number.MAX_SAFE_INTEGER;
export function fields(value) {
  return Object.fromEntries(Object.entries(record(value)).filter(([key, v]) =>
    NUMBERS.has(key) && number(v) || BOOLS.has(key) && typeof v === 'boolean' || Object.hasOwn(ENUMS, key) && ENUMS[key].includes(v)
    || key === 'requestId' && typeof v === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(v)
    || key === 'pageId' && typeof v === 'string' && /^[a-f0-9]{32}$/.test(v)));
}
export function normalizeEditor(value) {
  const v = record(value);
  if (['snapshot_unreadable', 'snapshot_too_large'].includes(v.unavailable)) return {unavailable: v.unavailable};
  if (v.schema !== 'kfps-editor-diagnostics/1') return {};
  const result = {schema: v.schema, native: fields(v.native), page: {}, recent: [], installed_assets: {}, logging: {}};
  for (const key of ['age_seconds', 'page_age_seconds']) if (number(v[key]) && v[key] >= 0) result[key] = v[key];
  if (typeof v.version === 'string' && /^[0-9.\-a-zA-Z]{1,40}$/.test(v.version)) result.version = v.version;
  const runtime = record(v.editor_runtime);
  result.editor_runtime = {};
  for (const key of ['python', 'pyside', 'qt', 'webengine', 'chromium']) {
    if (typeof runtime[key] === 'string' && /^[0-9.a-zA-Z+-]{1,48}$/.test(runtime[key])) result.editor_runtime[key] = runtime[key];
  }
  if (['verified', 'development'].includes(runtime.status)) result.editor_runtime.status = runtime.status;
  if (runtime.test_debugging === true) result.editor_runtime.test_debugging = true;
  if (typeof runtime.baseline === 'string' && /^[a-f0-9]{64}$/.test(runtime.baseline)) result.editor_runtime.baseline = runtime.baseline;
  for (const key of ['bits', 'files', 'bytes', 'verification_ms']) {
    if (number(runtime[key]) && runtime[key] >= 0 && runtime[key] <= 1e12) result.editor_runtime[key] = runtime[key];
  }
  // Legacy report retries must retain the same normalized contents and receipt hash.
  if (!Object.keys(result.editor_runtime).length) delete result.editor_runtime;
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
