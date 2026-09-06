import {InputError, UUID, normalizeReport, publicSummary, readJsonLimited, validWebhook} from '../public/protocol.mjs';

const encoder = new TextEncoder();
const API = 'https://discord.com/api/v10';
const DAY = 86400000;
const securityHeaders = {
  'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};
export function json(value, status = 200, headers = {}) {
  return new Response(JSON.stringify(value), {status, headers: {...securityHeaders, 'Content-Type': 'application/json; charset=utf-8', ...headers}});
}
function b64(bytes) { return btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, ''); }
function un64(text) { return Uint8Array.from(atob(text.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0)); }
async function key(secret) {
  if (typeof secret !== 'string' || secret.length < 32) throw new Error('configuration');
  return crypto.subtle.importKey('raw', encoder.encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign', 'verify']);
}
export async function sign(value, secret) {
  const body = b64(encoder.encode(JSON.stringify(value)));
  return `${body}.${b64(new Uint8Array(await crypto.subtle.sign('HMAC', await key(secret), encoder.encode(body))))}`;
}
export async function verify(token, secret, now = Date.now()) {
  try {
    if (typeof token !== 'string' || token.length > 3000) return null;
    const [body, signature, extra] = token.split('.');
    if (!body || !signature || extra || !await crypto.subtle.verify('HMAC', await key(secret), un64(signature), encoder.encode(body))) return null;
    const value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(un64(body)));
    return Number.isFinite(value.exp) && value.exp > now ? value : null;
  } catch { return null; }
}
function cookie(request, name) {
  return (request.headers.get('cookie') || '').split(';').map(s => s.trim()).find(s => s.startsWith(`${name}=`))?.slice(name.length + 1) || '';
}
function setCookie(name, value, age, env) {
  return `${name}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${age}${env.PUBLIC_ORIGIN.startsWith('https:') ? '; Secure' : ''}`;
}
function redirect(path, env, cookies = []) {
  const headers = new Headers({...securityHeaders, Location: new URL(path, env.PUBLIC_ORIGIN).href});
  for (const c of cookies) headers.append('Set-Cookie', c);
  return new Response(null, {status: 303, headers});
}
export async function session(request, env) {
  const value = await verify(cookie(request, 'kfps_support'), env.SESSION_SECRET);
  return value?.kind === 'session' && /^\d{17,20}$/.test(value.id) && typeof value.csrf === 'string' ? value : null;
}
function enabled(env) {
  return env.DELIVERY_ENABLED === '1' && /^\d{17,20}$/.test(env.DISCORD_CLIENT_ID || '')
    && !!env.DISCORD_CLIENT_SECRET && env.SESSION_SECRET?.length >= 32
    && validWebhook(env.PUBLIC_WEBHOOK_URL) && validWebhook(env.PRIVATE_WEBHOOK_URL);
}
async function discordFetch(url, options = {}) {
  // workerd supports manual/follow, not redirect:error. Callers reject non-2xx.
  return fetch(url, {...options, redirect: 'manual', signal: AbortSignal.timeout(15000)});
}
async function callback(request, env) {
  const url = new URL(request.url), state = url.searchParams.get('state');
  const saved = await verify(cookie(request, 'kfps_oauth'), env.SESSION_SECRET);
  const clear = setCookie('kfps_oauth', '', 0, env);
  if (!saved || saved.kind !== 'oauth' || !state || saved.nonce !== state || !url.searchParams.get('code') || url.searchParams.has('error')) {
    return redirect('/?auth=cancelled', env, [clear]);
  }
  let phase = 'token-request', status = 0;
  try {
    const response = await discordFetch(`${API}/oauth2/token`, {method: 'POST', headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams({
      client_id: env.DISCORD_CLIENT_ID, client_secret: env.DISCORD_CLIENT_SECRET, grant_type: 'authorization_code',
      code: url.searchParams.get('code'), redirect_uri: `${env.PUBLIC_ORIGIN}/auth/callback`,
    })});
    status = response.status;
    if (!response.ok) throw new Error('oauth');
    phase = 'token-response';
    const token = await response.json();
    phase = 'token-scope';
    if (!token.access_token || token.token_type?.toLowerCase() !== 'bearer' || token.scope !== 'identify') throw new Error('scope');
    phase = 'identity-request'; status = 0;
    const identity = await discordFetch(`${API}/users/@me`, {headers: {Authorization: `Bearer ${token.access_token}`}});
    status = identity.status;
    if (!identity.ok) throw new Error('identity');
    phase = 'identity-response';
    const user = await identity.json();
    if (!/^\d{17,20}$/.test(user.id) || typeof user.username !== 'string') throw new Error('identity');
    phase = 'session'; status = 0;
    const value = {kind: 'session', id: user.id, name: (user.global_name || user.username).slice(0, 80), csrf: crypto.randomUUID(), exp: Date.now() + 8 * 3600000};
    // OAuth tokens are used only here and are never stored in cookies or report records.
    return redirect('/', env, [clear, setCookie('kfps_support', await sign(value, env.SESSION_SECRET), 8 * 3600, env)]);
  } catch {
    // Fixed phase names and HTTP status only: never reflect OAuth bodies or tokens.
    return redirect(`/?auth=failed&detail=${phase}-${status}`, env, [clear]);
  }
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      if (url.origin !== env.PUBLIC_ORIGIN) return json({error: 'Unsupported address.'}, 400);
      const path = url.pathname;
      if (path === '/api/config' && request.method === 'GET') return json({enabled: enabled(env), join_url: env.DISCORD_JOIN_URL, environment: 'DIRTY testing', schema: 'kfps-support-report/1'});
      if (path === '/api/session' && request.method === 'GET') {
        const user = await session(request, env);
        return json(user ? {authenticated: true, name: user.name, csrf: user.csrf} : {authenticated: false});
      }
      if (path === '/auth/start' && request.method === 'GET') {
        if (!enabled(env)) return redirect('/?auth=unavailable', env);
        const nonce = crypto.randomUUID();
        const signed = await sign({kind: 'oauth', nonce, exp: Date.now() + 600000}, env.SESSION_SECRET);
        const target = new URL('https://discord.com/oauth2/authorize');
        target.search = new URLSearchParams({client_id: env.DISCORD_CLIENT_ID, redirect_uri: `${env.PUBLIC_ORIGIN}/auth/callback`, response_type: 'code', scope: 'identify', state: nonce}).toString();
        return redirect(target.href, env, [setCookie('kfps_oauth', signed, 600, env)]);
      }
      if (path === '/auth/callback' && request.method === 'GET') return callback(request, env);
      if (path === '/api/reports' || path === '/auth/logout' || /^\/api\/reports\//.test(path)) {
        const user = await session(request, env);
        if (!user) return json({error: 'Sign in with Discord again. Your draft is still here.'}, 401);
        if (request.method === 'POST') {
          if (request.headers.get('origin') !== env.PUBLIC_ORIGIN || request.headers.get('x-csrf-token') !== user.csrf) return json({error: 'Session check failed. Reload the form.'}, 403);
          if (path === '/auth/logout') return json({ok: true}, 200, {'Set-Cookie': setCookie('kfps_support', '', 0, env)});
          if (path !== '/api/reports') return json({error: 'Not found.'}, 404);
          if (!enabled(env)) return json({error: 'Report delivery is temporarily unavailable. Keep your saved report and try later.'}, 503);
          const report = normalizeReport(await readJsonLimited(request));
          const object = env.REPORTS.get(env.REPORTS.idFromName(user.id));
          return object.fetch(new Request('https://report.internal/send', {method: 'POST', body: JSON.stringify({report, user: {id: user.id, name: user.name}})}));
        }
        const id = path.slice('/api/reports/'.length);
        if (request.method === 'GET' && UUID.test(id)) return env.REPORTS.get(env.REPORTS.idFromName(user.id)).fetch(new Request(`https://report.internal/status/${id}`));
        return json({error: 'Method not allowed.'}, 405);
      }
      if (path.startsWith('/api/') || path.startsWith('/auth/')) return json({error: 'Not found.'}, 404);
      if (request.method !== 'GET' && request.method !== 'HEAD') return json({error: 'Method not allowed.'}, 405);
      const response = await env.ASSETS.fetch(request);
      const headers = new Headers(response.headers);
      for (const [name, value] of Object.entries(securityHeaders)) headers.set(name, value);
      return new Response(response.body, {status: response.status, headers});
    } catch (error) {
      return json({error: error instanceof InputError ? error.message : 'The reporting service could not complete this request. Your local report is safe.'}, error instanceof InputError ? 400 : 503);
    }
  },
};

async function digest(value) {
  return b64(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(JSON.stringify(value)))));
}
function result(record, env) {
  const delivered = record.private?.state === 'sent' && record.public?.state === 'sent';
  const uncertain = [record.private, record.public].some(v => ['sending', 'uncertain'].includes(v?.state));
  const blocked = [record.private, record.public].some(v => v?.state === 'blocked');
  return {id: record.id, status: delivered ? 'delivered' : uncertain ? 'uncertain' : blocked ? 'blocked' : 'retryable',
    retry_after: Math.max(0, Math.ceil(((record.retryAt || 0) - Date.now()) / 1000)),
    public_url: record.public?.thread ? `https://discord.com/channels/${env.DISCORD_GUILD_ID}/${record.public.thread}` : null,
    message: delivered ? 'Report sent. Staff have the technical details and your support post is ready.'
      : uncertain ? 'Discord may have received part of this report. Do not submit a new copy. Give staff this report ID so they can check.'
      : blocked ? 'Delivery is blocked by the reporting configuration. Keep this report ID and contact support.'
      : 'Delivery is incomplete. Retry this same report after the wait shown; already delivered parts will not be posted again.'};
}

export class ReportStore {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; this.queue = Promise.resolve(); this.pending = 0; }
  async fetch(request) {
    if (this.pending >= 4) return json({error: 'A report is already being processed. Wait a moment before retrying.'}, 429);
    this.pending++;
    const task = this.queue.then(() => this.handle(request));
    this.queue = task.catch(() => {});
    try { return await task; }
    catch { return json({error: 'Delivery state could not be confirmed. Keep the report ID and check its status before retrying.'}, 503); }
    finally { this.pending--; }
  }
  async handle(request) {
    const path = new URL(request.url).pathname;
    if (request.method === 'GET' && path.startsWith('/status/')) {
      const record = await this.ctx.storage.get(`report:${path.slice(8)}`);
      return record ? json(result(record, this.env)) : json({error: 'No submission recorded for this account and report ID.'}, 404);
    }
    if (request.method !== 'POST' || path !== '/send') return json({error: 'Not found.'}, 404);
    const {report, user} = await request.json(), storage = this.ctx.storage;
    const recordKey = `report:${report.id}`, hash = await digest(report);
    let record = await storage.get(recordKey);
    if (record && record.hash !== hash) return json({error: 'This report has already been submitted with different contents. Restore the original draft or contact staff with its ID.'}, 409);
    if (record && result(record, this.env).status !== 'retryable') return json(result(record, this.env));
    if (record?.retryAt > Date.now()) return json(result(record, this.env), 429);
    if (!record) {
      const now = Date.now(), times = (await storage.get('submissions') || []).filter(t => t > now - DAY);
      if (times.length >= 20 || times.filter(t => t > now - 600000).length >= 3) return json({error: 'Report limit reached. Please wait before sending another report.', retry_after: 600}, 429);
      times.push(now);
      record = {id: report.id, hash, created: now, private: {state: 'pending'}, public: {state: 'pending'}, attempts: 0};
      await storage.put({submissions: times, [recordKey]: record});
      if (await storage.getAlarm() === null) await storage.setAlarm(now + 30 * DAY);
    }
    if (record.attempts >= 5) { record.private.state === 'pending' ? record.private.state = 'blocked' : record.public.state = 'blocked'; await storage.put(recordKey, record); return json(result(record, this.env)); }
    record.attempts++;
    // Validate destinations before posting. A misplaced webhook must not leak diagnostics.
    for (const [kind, url, channel] of [['private', this.env.PRIVATE_WEBHOOK_URL, this.env.PRIVATE_CHANNEL_ID], ['public', this.env.PUBLIC_WEBHOOK_URL, this.env.SUPPORT_CHANNEL_ID]]) {
      if (record[kind].state === 'sent') continue;
      if (!validWebhook(url)) { record[kind].state = 'blocked'; break; }
      try {
        const check = await discordFetch(url);
        if (!check.ok) {
          record.retryAt = Date.now() + 60000;
          if ([401,403,404].includes(check.status)) record[kind].state = 'blocked';
          await storage.put(recordKey, record); return json(result(record, this.env));
        }
        const metadata = await check.json();
        if (metadata.channel_id !== channel || metadata.guild_id !== this.env.DISCORD_GUILD_ID || metadata.type !== 1) { record[kind].state = 'blocked'; break; }
      } catch { record.retryAt = Date.now() + 60000; await storage.put(recordKey, record); return json(result(record, this.env)); }
    }
    if (result(record, this.env).status === 'blocked') { await storage.put(recordKey, record); return json(result(record, this.env)); }
    for (const kind of ['private', 'public']) {
      if (record[kind].state === 'sent') continue;
      const url = new URL(kind === 'private' ? this.env.PRIVATE_WEBHOOK_URL : this.env.PUBLIC_WEBHOOK_URL);
      url.searchParams.set('wait', 'true');
      const payload = {allowed_mentions: {parse: []}, username: 'KFPS Support', content: kind === 'public' ? publicSummary(report, user) : `Private diagnostic report ${report.id}`};
      let body, headers;
      if (kind === 'public') {
        payload.thread_name = `[${report.feature}] ${report.title}`.replace(/[@\r\n]/g, ' ').slice(0, 100);
        body = JSON.stringify(payload); headers = {'Content-Type': 'application/json'};
      } else {
        payload.attachments = [{id: 0, filename: `kfps-report-${report.id}.json`, description: 'Reviewed KFPS technical context'}];
        body = new FormData(); body.set('payload_json', JSON.stringify(payload));
        body.set('files[0]', new Blob([JSON.stringify({received_at: new Date(record.created).toISOString(), reporter: user, ...report}, null, 2)], {type: 'application/json'}), `kfps-report-${report.id}.json`);
      }
      record[kind] = {state: 'sending'};
      await storage.put(recordKey, record);
      try {
        const response = await discordFetch(url.href, {method: 'POST', body, headers});
        if (!response.ok) {
          record[kind].state = response.status === 429 ? 'pending' : response.status >= 500 ? 'uncertain' : 'blocked';
          record.retryAt = Date.now() + 60000;
        } else {
          const message = await response.json();
          if (!/^\d{17,20}$/.test(message.id) || !/^\d{17,20}$/.test(message.channel_id) || (kind === 'private' && message.channel_id !== this.env.PRIVATE_CHANNEL_ID)) throw new Error('unexpected acknowledgment');
          record[kind] = {state: 'sent', message: message.id, ...(kind === 'public' ? {thread: message.channel_id} : {})};
        }
      } catch { record[kind].state = 'uncertain'; }
      await storage.put(recordKey, record);
      if (record[kind].state !== 'sent') break;
    }
    return json(result(record, this.env));
  }
  async alarm() {
    const records = await this.ctx.storage.list({prefix: 'report:'});
    const expired = [...records].filter(([, r]) => r.created <= Date.now() - 30 * DAY).map(([k]) => k);
    if (expired.length) await this.ctx.storage.delete(expired);
    const remaining = [...records].filter(([key]) => !expired.includes(key));
    if (remaining.length) await this.ctx.storage.setAlarm(Math.max(Date.now() + 1000, Math.min(...remaining.map(([,r]) => r.created + 30 * DAY))));
    else await this.ctx.storage.delete('submissions');
  }
}
