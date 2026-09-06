// Shared by the browser review and the server; only allowlisted context survives.
export const SCHEMA = 'kfps-support-report/1';
export const FEATURES = ['Generator', 'Editor', 'Import and export', 'Liveries', 'Community', 'Updater', 'Other'];
export const MAX_BYTES = 64 * 1024;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export class InputError extends Error {}

export function redact(value, max = 1600) {
  return String(value ?? '').slice(0, 60000)
    .replace(/^.*\b(?:authorization|cookie|password|secret|bearer|api[ _-]?key|activation[ _-]?key|access[ _-]?token|refresh[ _-]?token|receipt)\b.*$/gim, '[sensitive line removed]')
    .replace(/https?:\/\/[^\s<>"']+/gi, '[url removed]')
    .replace(/\b[a-z]:[\\/][^\r\n"'<>|]*/gi, '[local path removed]')
    .replace(/\\\\[^\r\n"'<>|]+/g, '[network path removed]')
    .replace(/\/(?:home|Users)\/[^\s"'<>]+/g, '[local path removed]')
    .replace(/\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b/g, '[credential removed]')
    .replace(/(?<![\w.+-])[\w.+-]{1,128}@[\w.-]{1,253}\.[A-Za-z]{2,24}/g, '[email removed]')
    .replace(/\b(?:\d{15,20}|[a-f0-9]{32,})\b/gi, '[identifier removed]')
    .split('\n').map(line => /(?<![^\s"'<>:/\\])[^\s"'<>:/\\]{1,240}\.(?:json|png|jpe?g|webp|bmp|svg|kfpslivery|zip|7z)\b/i.test(line) ? '[file reference removed]' : line).join('\n')
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '').slice(0, max);
}

function record(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function pick(value, keys, max = 700) {
  const source = record(value), output = {};
  for (const key of keys) {
    const item = source[key];
    if (typeof item === 'string') output[key] = redact(item, max);
    else if (typeof item === 'boolean') output[key] = item;
    else if (typeof item === 'number' && Number.isFinite(item) && Math.abs(item) <= 1e15) output[key] = item;
  }
  return output;
}

export function normalizeTechnical(value) {
  const v = record(value), result = {};
  result.app = pick(v.app, ['version', 'theme', 'page', 'uptime_seconds'], 100);
  result.hardware = pick(v.hardware, ['platform', 'architecture', 'processor', 'logical_cpu_count', 'memory_bytes'], 200);
  result.hardware.gpus = (Array.isArray(v.hardware?.gpus) ? v.hardware.gpus : []).slice(0, 8).map(g => pick(g, ['name', 'driver_version'], 160));
  result.running_games = (Array.isArray(v.running_games) ? v.running_games : []).slice(0, 4).map(g => ({
    game: ['FH4','FH5','FH6','FM8'].includes(g?.game) ? g.game : 'unknown',
    store: ['steam','microsoft_xbox'].includes(g?.store) ? g.store : 'unknown',
  }));
  result.dependencies = pick(v.dependencies, ['PySide6','numpy','Pillow','opencv-python','opencv-python-headless','psutil'], 100);
  Object.assign(result, pick(v, ['python','python_bits','collection_warning'], 200));
  result.states = {};
  for (const key of ['transfer','generator','editor','liveries','offline','outputs','community','updater','runtime']) {
    result.states[key] = pick(v.states?.[key], ['status','running','lastError','activeGame','selectedLayers','selectedShapes','candidateCount','exportedCount','skippedCount','viewerReady','packageAddError','dependenciesText','pythonText','runtimeText','selectedPresetIndex']);
  }
  result.locator = pick(v.locator, ['engine_version','created_utc','store_variant'], 100);
  result.locator.request = pick(v.locator?.request, ['game','purpose','layer_count']);
  result.locator.outcome = pick(v.locator?.outcome, ['status','reason','authoritative','failure_reason','refusal_reason']);
  result.logs = (Array.isArray(v.logs) ? v.logs : []).slice(0, 5).map(log => ({source: redact(log?.source, 30), text: redact(log?.text, 6500)}));
  result.browser = pick(v.browser, ['userAgent','language','screen','deviceMemory','hardwareConcurrency'], 300);
  return result;
}

export function normalizeReport(input) {
  const v = record(input);
  if (v.schema !== SCHEMA || !UUID.test(v.id || '')) throw new InputError('Invalid report format. Prepare a new report in KFPS.');
  if (!FEATURES.includes(v.feature)) throw new InputError('Choose the affected feature.');
  const description = redact(v.description, 3000).trim();
  if (description.length < 5) throw new InputError('Please briefly describe what went wrong.');
  const result = {
    schema: SCHEMA, id: v.id.toLowerCase(), source: v.source === 'kfps' ? 'kfps' : 'discord-form',
    created_at: typeof v.created_at === 'string' && Number.isFinite(Date.parse(v.created_at)) ? v.created_at.slice(0, 40) : new Date().toISOString(),
    feature: v.feature, title: redact(v.title || description.split('\n')[0], 90).trim() || `${v.feature} issue`,
    description, expected: redact(v.expected, 1500).trim(),
    technical: v.include_technical === false ? {} : normalizeTechnical(v.technical),
    include_technical: v.include_technical !== false,
  };
  if (new TextEncoder().encode(JSON.stringify(result)).length > MAX_BYTES) throw new InputError('Report is too large. Remove some log text.');
  return result;
}

export function discordText(value, max = 1400) {
  return redact(value, max).replace(/@/g, '@\u200b').replace(/[\\`*_~>|]/g, '\\$&');
}

export function publicSummary(report, user) {
  const text = [
    `**${discordText(report.feature)} report**`,
    `Reporter: ${discordText(user.name, 70)} | KFPS ${discordText(report.technical?.app?.version || 'not supplied', 50)}`,
    '', discordText(report.description, 1050),
    ...(report.expected ? ['', '**Expected:**', discordText(report.expected, 350)] : []),
    '', `Report ID: \`${report.id}\``,
    report.include_technical ? 'Technical details are delivered privately to staff.' : 'Technical details were not included.',
  ].join('\n');
  return text.slice(0, 1990);
}

export function validWebhook(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && u.hostname === 'discord.com' && !u.port && !u.search && !u.hash && !u.username && !u.password
      && /^\/api\/webhooks\/\d{17,20}\/[A-Za-z0-9_-]{30,}$/.test(u.pathname);
  } catch { return false; }
}

export async function readJsonLimited(request) {
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) throw new InputError('Expected a JSON report.');
  if (Number(request.headers.get('content-length') || 0) > MAX_BYTES) throw new InputError('Report is too large.');
  const reader = request.body?.getReader();
  if (!reader) throw new InputError('Missing report.');
  const chunks = []; let length = 0;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    length += value.length;
    if (length > MAX_BYTES) { await reader.cancel(); throw new InputError('Report is too large.'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  try { return JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)); }
  catch { throw new InputError('Invalid JSON report.'); }
}
