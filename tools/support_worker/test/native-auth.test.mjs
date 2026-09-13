import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {ReportStore, sign, verify} from '../src/worker.mjs';
import {nativeAuthStore} from '../src/native-auth.mjs';
import {nativeSignIn} from '../public/native-signin.mjs';

class Storage {
  data = new Map();
  async get(key) { return structuredClone(this.data.get(key)); }
  async put(key, value) { this.data.set(key, structuredClone(value)); }
  async setAlarm(value) { this.alarm = value; }
  async delete(key) { this.data.delete(key); }
  async list({prefix}) { return new Map([...this.data].filter(([key]) => key.startsWith(prefix))); }
}
function fixture() {
  const stores = new Map();
  const env = {PUBLIC_ORIGIN: 'https://support.example', SESSION_SECRET: 'synthetic-secret-longer-than-thirty-two', DISCORD_CLIENT_ID: '111111111111111111', DISCORD_CLIENT_SECRET: 'synthetic', DELIVERY_ENABLED: '1', PUBLIC_WEBHOOK_URL: 'https://discord.com/api/webhooks/222222222222222222/' + 'a'.repeat(40), PRIVATE_WEBHOOK_URL: 'https://discord.com/api/webhooks/333333333333333333/' + 'b'.repeat(40), ASSETS: {fetch: async () => new Response('<html>approval fixture</html>')}};
  env.REPORTS = {idFromName: id => id, get: id => {
    if (!stores.has(id)) { const storage = new Storage(); stores.set(id, {storage, object: new ReportStore({storage}, env)}); }
    return stores.get(id).object;
  }};
  const request = (path, {cookie = '', body = {}, method = 'POST', origin = env.PUBLIC_ORIGIN, csrf = '', raw} = {}) => worker.fetch(new Request(env.PUBLIC_ORIGIN + path, {method, headers: {Origin: origin, Cookie: cookie, 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'CF-Connecting-IP': '192.0.2.1'}, ...(method === 'POST' ? {body: raw ?? JSON.stringify(body)} : {})}), env);
  const browser = async (id = '444444444444444444') => 'kfps_support=' + await sign({kind: 'session', id, name: 'Fixture User', csrf: 'browser-only', exp: Date.now() + 3600000}, env.SESSION_SECRET);
  const start = async () => { const response = await request('/api/native-auth/start'); assert.equal(response.status, 200); return {value: await response.json(), cookie: response.headers.get('set-cookie').split(';')[0]}; };
  return {env, stores, request, browser, start};
}

test('separate browser approval creates a fresh native session; private cookie, no report/token in links', async () => {
  const f = fixture(), first = await f.start(), browser = await f.browser();
  assert(first.value.expires_in_ms > 0 && first.value.expires_in_ms <= 300000);
  assert.equal(first.value.url, f.env.PUBLIC_ORIGIN + '/auth/native?ticket=' + first.value.id);
  assert.equal(JSON.stringify(first.value).includes('secret'), false);
  assert.equal((await f.request('/api/native-auth/poll', {cookie: first.cookie})).status, 200);
  const info = await (await f.request('/api/native-auth/approval?ticket=' + first.value.id, {method: 'GET', cookie: browser})).json();
  assert.equal(info.code, first.value.code);
  const approval = await f.request('/api/native-auth/approve', {cookie: browser, csrf: 'browser-only', body: {ticket: first.value.id, code: info.code, confirm: true}});
  assert.deepEqual(await approval.json(), {status: 'ready'});
  const ready = await f.request('/api/native-auth/poll', {cookie: first.cookie});
  assert.deepEqual(await ready.clone().json(), {status: 'ready'});
  const token = ready.headers.get('set-cookie').split(';')[0].slice('kfps_support='.length);
  const session = await verify(token, f.env.SESSION_SECRET);
  assert.equal(session.id, '444444444444444444'); assert.notEqual(session.csrf, 'browser-only');
  assert.match(ready.headers.get('set-cookie'), /HttpOnly; SameSite=Lax/);
  assert.match(ready.headers.get('set-cookie'), /Secure/);
  const retry = await f.request('/api/native-auth/poll', {cookie: first.cookie});
  assert.equal(retry.headers.get('set-cookie'), ready.headers.get('set-cookie'), 'lost-response retry is idempotent');
  assert.equal([...f.stores.keys()].some(key => /^\d+$/.test(key)), false, 'no report delivery actor was touched');
});

test('approval needs browser identity, origin, CSRF and matching explicit confirmation', async () => {
  const f = fixture(), first = await f.start(), browser = await f.browser();
  const path = '/api/native-auth/approve', valid = {ticket: first.value.id, code: first.value.code, confirm: true};
  for (const [options, status] of [[{body: valid}, 401], [{body: valid, cookie: browser}, 403], [{body: valid, cookie: browser, csrf: 'browser-only', origin: 'https://evil.example'}, 403], [{body: {...valid, confirm: false}, cookie: browser, csrf: 'browser-only'}, 400], [{body: {...valid, code: 'WRONG'}, cookie: browser, csrf: 'browser-only'}, 400]]) {
    assert.equal((await f.request(path, options)).status, status);
  }
  assert.deepEqual(await (await f.request('/api/native-auth/poll', {cookie: first.cookie})).json(), {status: 'pending'});
  assert.equal((await f.request('/api/native-auth/poll', {cookie: browser})).status, 410, 'browser cookie cannot consume native authorization');
});

test('tickets cannot switch accounts after approval; cancel, deny, expiry and alarm cleanup work', async () => {
  const f = fixture(), first = await f.start(), browser = await f.browser();
  const approve = cookie => f.request('/api/native-auth/approve', {cookie, csrf: 'browser-only', body: {ticket: first.value.id, code: first.value.code, confirm: true}});
  assert.equal((await approve(browser)).status, 200);
  assert.equal((await approve(await f.browser('555555555555555555'))).status, 409);
  assert.deepEqual(await (await f.request('/api/native-auth/cancel', {cookie: first.cookie})).json(), {status: 'cancelled'});
  assert.deepEqual(await (await f.request('/api/native-auth/poll', {cookie: first.cookie})).json(), {status: 'cancelled'});
  const second = await f.start();
  await f.request('/api/native-auth/deny', {cookie: browser, csrf: 'browser-only', body: {ticket: second.value.id, code: second.value.code, confirm: true}});
  assert.deepEqual(await (await f.request('/api/native-auth/poll', {cookie: second.cookie})).json(), {status: 'denied'});
  const {storage, object} = f.stores.get('native-auth:' + second.value.id);
  const record = await storage.get('native-auth'); record.exp = Date.now() - 1; await storage.put('native-auth', record);
  assert.equal((await f.request('/api/native-auth/poll', {cookie: second.cookie})).status, 410);
  await object.alarm(); assert.equal(await storage.get('native-auth'), undefined);
});

test('wrong consumer key, malformed/oversized bodies, disabled delivery and anonymous flood fail closed', async () => {
  const f = fixture(), first = await f.start();
  const forged = 'kfps_native_auth=' + await sign({kind: 'native-auth', id: first.value.id, secret: 'wrong', exp: Date.now() + 60000}, f.env.SESSION_SECRET);
  assert.equal((await f.request('/api/native-auth/poll', {cookie: forged})).status, 403);
  for (const raw of ['null', '[]', '{', JSON.stringify({x: 'a'.repeat(1025)})]) assert.equal((await f.request('/api/native-auth/start', {raw})).status, 400);
  assert.equal((await f.request('/api/native-auth/start', {origin: 'https://evil.example'})).status, 403);
  for (let i = 0; i < 7; i++) await f.start();
  assert.equal((await f.request('/api/native-auth/start')).status, 429);
  f.env.DELIVERY_ENABLED = '0'; assert.equal((await f.request('/api/native-auth/start')).status, 503);
});

test('default-browser route reuses its support session or redirects to existing identity-only OAuth', async () => {
  const f = fixture(), first = await f.start();
  const redirect = await f.request('/auth/native?ticket=' + first.value.id, {method: 'GET'});
  assert.equal(redirect.headers.get('location'), f.env.PUBLIC_ORIGIN + '/auth/start?native=' + first.value.id);
  const oauth = await f.request('/auth/start?native=' + first.value.id, {method: 'GET'});
  const target = new URL(oauth.headers.get('location'));
  assert.equal(target.origin, 'https://discord.com'); assert.equal(target.searchParams.get('scope'), 'identify');
  const signed = oauth.headers.get('set-cookie').split(';')[0].slice('kfps_oauth='.length);
  assert.equal((await verify(signed, f.env.SESSION_SECRET)).native, first.value.id);
  const page = await f.request('/auth/native?ticket=' + first.value.id, {method: 'GET', cookie: await f.browser()});
  assert.equal(page.status, 200); assert.match(page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  const cancelled = await f.request('/auth/native?ticket=' + first.value.id + '&auth=cancelled', {method: 'GET'});
  assert.equal(cancelled.status, 200, 'cancellation must not auto-open OAuth again');
});

test('auth storage never returns a session without its consumer proof', async () => {
  const f = fixture(), first = await f.start(), browser = await f.browser();
  await f.request('/api/native-auth/approve', {cookie: browser, csrf: 'browser-only', body: {ticket: first.value.id, code: first.value.code, confirm: true}});
  const value = await (await f.request('/api/native-auth/approval?ticket=' + first.value.id, {method: 'GET', cookie: browser})).json();
  assert.equal(value.session, undefined);
  const storage = f.stores.get('native-auth:' + first.value.id).storage;
  const response = await nativeAuthStore(storage, 'poll', {hash: 'wrong'}, (value, status) => Response.json(value, {status}));
  assert.equal(response.status, 403);
});

test('client launches only the expected default-browser URL and never auto-submits after approval', async () => {
  const id = crypto.randomUUID(), tasks = [], calls = [], changes = [], accounts = [];
  const flow = nativeSignIn({origin: 'https://support.example', now: () => 1000,
    schedule: fn => { tasks.push(fn); return tasks.length; }, unschedule: () => {},
    changed: value => changes.push(value), authenticated: account => accounts.push(account),
    api: async path => { calls.push(path); return path.endsWith('/start') ? {id, code: '1234-5678', expires_at: 301000, url: 'https://support.example/auth/native?ticket=' + id} : path.endsWith('/poll') ? {status: 'ready'} : {authenticated: true, name: 'Fixture'}; }});
  await flow.start(); await flow.start(); assert.equal(calls.length, 1);
  assert.equal(flow.request().id, id); flow.opened(id, true); assert.equal(flow.request(), null);
  await tasks.shift()(); assert.equal(accounts.length, 1); assert.equal(flow.request(), null);
  assert.deepEqual(calls, ['/api/native-auth/start', '/api/native-auth/poll', '/api/session']);
});

test('client cancellation ignores a late authorization response and untrusted launch URL', async () => {
  const id = crypto.randomUUID(), errors = [], accounts = [], tasks = [];
  let resolve;
  const response = new Promise(r => { resolve = r; });
  const flow = nativeSignIn({origin: 'https://support.example', changed: v => errors.push(v), authenticated: v => accounts.push(v),
    api: path => path.endsWith('/start') ? response : Promise.resolve({status: 'cancelled'}), schedule: fn => tasks.push(fn)});
  const started = flow.start(); await flow.cancel(); resolve({id, url: 'https://evil.example/', code: '1234-5678', expires_at: Date.now() + 10000}); await started;
  assert.equal(flow.request(), null); assert.equal(tasks.length, 0); assert.equal(accounts.length, 0);
  const bad = nativeSignIn({origin: 'https://support.example', changed: v => errors.push(v), authenticated: v => accounts.push(v), api: () => Promise.resolve({id, url: 'https://evil.example/', code: '1234-5678', expires_at: Date.now() + 10000})});
  await bad.start(); assert.equal(bad.request(), null); assert.equal(errors.at(-1).error, 'invalid-response');
});

test('manual browser link survives failed or absent host launch without another auth request', async () => {
  const id = crypto.randomUUID(), tasks = [], changes = [], calls = [];
  let now = 1000;
  const flow = nativeSignIn({origin: 'https://support.example', now: () => now,
    schedule: fn => {tasks.push(fn); return tasks.length;}, unschedule: () => {},
    changed: value => changes.push(value), authenticated: () => assert.fail('No approval happened'),
    api: async path => {calls.push(path); return {id, code: '1234-5678', expires_at: 301000, url: 'https://support.example/auth/native?ticket=' + id};}});
  await flow.start();
  const url = flow.request().url;
  flow.opened(id, false);
  assert.equal(changes.at(-1).error, 'browser');
  assert.equal(changes.at(-1).url, url);
  assert.equal(flow.manual(), true);
  assert.equal(flow.request(), null);
  assert.equal(changes.at(-1).error, '');
  flow.reopen();
  assert.equal(flow.request().url, url);
  assert.equal(flow.manual(), true, 'user click works before the host acknowledges');
  flow.opened(id, false);
  assert.equal(changes.at(-1).error, '', 'late automatic reply cannot overwrite the manual fallback');
  assert.deepEqual(calls, ['/api/native-auth/start']);
  now = 301000;
  assert.equal(flow.manual(), false, 'expired URL is never launched by a late click');
  assert.equal(changes.at(-1).error, 'expired');
  assert.equal(flow.request(), null);
  assert.equal(changes.at(-1).url, undefined);
});

test('client refuses credentials, fragments and extra query parameters in approval URLs', async () => {
  const id = crypto.randomUUID(), changes = [];
  for (const url of [`https://user:pass@support.example/auth/native?ticket=${id}`,
    `https://support.example/auth/native?ticket=${id}#fragment`,
    `https://support.example/auth/native?ticket=${id}&extra=true`]) {
    const flow = nativeSignIn({origin: 'https://support.example', changed: value => changes.push(value),
      authenticated: () => assert.fail('No approval happened'), api: async () => ({id, url, code: '1234-5678', expires_at: Date.now() + 10000})});
    await flow.start(); assert.equal(flow.request(), null); assert.equal(flow.manual(), false);
    assert.equal(changes.at(-1).error, 'invalid-response');
  }
});
