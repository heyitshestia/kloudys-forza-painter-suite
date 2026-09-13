import {UUID, InputError, readBytesLimited} from '../public/protocol.mjs';

const TTL = 5 * 60 * 1000;
const PENDING = 'kfps_native_auth';
const hash = async text => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), x => x.toString(16).padStart(2, '0')).join('');
const call = (env, id, action, body = {}) => env.REPORTS.get(env.REPORTS.idFromName(`native-auth:${id}`)).fetch(
  new Request(`https://report.internal/native/${action}`, {method: 'POST', body: JSON.stringify(body)}));

// The public link identifies an approval request, never its private consumer key.
export async function nativeAuth(request, env, helpers) {
  const {json, session, sign, verify, cookie, setCookie, enabled} = helpers;
  const url = new URL(request.url), path = url.pathname;
  if (!path.startsWith('/api/native-auth/')) return null;
  if (!enabled(env)) return json({error: 'Sign-in is temporarily unavailable.'}, 503);
  if (path === '/api/native-auth/approval' && request.method === 'GET') {
    const id = url.searchParams.get('ticket');
    if (!UUID.test(id || '')) return json({error: 'Invalid sign-in link.'}, 400);
    const user = await session(request, env);
    if (!user) return json({error: 'Sign in with Discord to continue.'}, 401);
    const response = await call(env, id, 'info');
    const value = await response.json();
    return json({...value, ...(response.ok ? {name: user.name, csrf: user.csrf} : {})}, response.status);
  }
  if (request.method !== 'POST') return json({error: 'Method not allowed.'}, 405);
  if (request.headers.get('origin') !== env.PUBLIC_ORIGIN) return json({error: 'Sign-in origin check failed.'}, 403);
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) throw new InputError('Expected a sign-in request.');
  let body;
  try { body = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(await readBytesLimited(request, 1024))); }
  catch { throw new InputError('Invalid sign-in request.'); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new InputError('Invalid sign-in request.');
  if (path === '/api/native-auth/start') {
    const ip = request.headers.get('cf-connecting-ip') || 'unknown';
    const limit = await call(env, `rate:${await hash(ip)}`, 'limit');
    if (!limit.ok) return limit;
    const id = crypto.randomUUID(), secret = crypto.randomUUID() + crypto.randomUUID();
    const exp = Date.now() + TTL;
    const response = await call(env, id, 'create', {hash: await hash(secret), exp});
    if (!response.ok) return response;
    const {code} = await response.json();
    const pending = await sign({kind: 'native-auth', id, secret, exp}, env.SESSION_SECRET);
    return json({id, code, expires_at: exp, expires_in_ms: Math.max(0, exp - Date.now()), url: `${env.PUBLIC_ORIGIN}/auth/native?ticket=${id}`}, 200,
      {'Set-Cookie': setCookie(PENDING, pending, TTL / 1000, env)});
  }
  if (path === '/api/native-auth/approve' || path === '/api/native-auth/deny') {
    const user = await session(request, env);
    if (!user) return json({error: 'Sign in with Discord to continue.'}, 401);
    if (request.headers.get('x-csrf-token') !== user.csrf) return json({error: 'Session check failed.'}, 403);
    if (!UUID.test(body.ticket || '') || body.confirm !== true) return json({error: 'Confirm this sign-in request.'}, 400);
    return call(env, body.ticket, path.endsWith('/deny') ? 'deny' : 'approve',
      {user: {id: user.id, name: user.name}, code: body.code});
  }
  const pending = await verify(cookie(request, PENDING), env.SESSION_SECRET);
  if (pending?.kind !== 'native-auth' || !UUID.test(pending.id || '') || typeof pending.secret !== 'string') {
    return json({error: 'This sign-in request expired. Start again in KFPS.', status: 'expired'}, 410);
  }
  if (path === '/api/native-auth/poll' || path === '/api/native-auth/cancel') {
    const cancel = path.endsWith('/cancel');
    const response = await call(env, pending.id, cancel ? 'cancel' : 'poll', {hash: await hash(pending.secret)});
    const value = await response.json();
    if (value.status !== 'ready') return json(value, response.status,
      cancel ? {'Set-Cookie': setCookie(PENDING, '', 0, env)} : {});
    // A response lost in transit can be retried with the same private pending cookie.
    // The browser session and Discord access token never cross into the native window.
    const signed = await sign(value.session, env.SESSION_SECRET);
    return json({status: 'ready'}, 200, {'Set-Cookie': setCookie('kfps_support', signed, 8 * 3600, env)});
  }
  return json({error: 'Not found.'}, 404);
}

export async function nativeAuthStore(storage, action, body, json, now = Date.now()) {
  const expired = () => json({status: 'expired', error: 'Sign-in expired. Start again in KFPS.'}, 410);
  if (action === 'limit') {
    const times = (await storage.get('native-rate') || []).filter(t => t > now - 86400000);
    if (times.length >= 40 || times.filter(t => t > now - 600000).length >= 8) return json({error: 'Too many sign-in attempts. Please wait before trying again.'}, 429);
    times.push(now);
    await storage.put('native-rate', times);
    await storage.setAlarm(now + 86400000);
    return json({ok: true});
  }
  let record = await storage.get('native-auth');
  if (action === 'create') {
    if (record) return json({error: 'Sign-in request already exists.'}, 409);
    if (!/^[a-f0-9]{64}$/.test(body.hash) || !Number.isFinite(body.exp) || body.exp <= now || body.exp > now + TTL + 1000) return expired();
    const random = crypto.randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase();
    record = {hash: body.hash, exp: body.exp, code: random.slice(0, 4) + '-' + random.slice(4), status: 'pending'};
    await storage.put('native-auth', record);
    await storage.setAlarm(record.exp);
    return json({code: record.code});
  }
  if (!record || record.exp <= now) return expired();
  if (action === 'info') return json({status: record.status, code: record.code, expires_at: record.exp});
  if (action === 'approve' || action === 'deny') {
    if (record.status !== 'pending') return json({error: 'This request is no longer waiting for approval.'}, 409);
    if (body.code !== record.code || !/^\d{17,20}$/.test(body.user?.id || '') || typeof body.user?.name !== 'string') return json({error: 'Sign-in confirmation did not match.'}, 400);
    record.status = action === 'approve' ? 'ready' : 'denied';
    if (action === 'approve') record.session = {kind: 'session', id: body.user.id, name: body.user.name.slice(0, 80), csrf: crypto.randomUUID(), exp: now + 8 * 3600000};
    await storage.put('native-auth', record);
    return json({status: record.status});
  }
  if (body.hash !== record.hash) return json({error: 'Sign-in request does not belong to this window.'}, 403);
  if (action === 'cancel') {
    record.status = 'cancelled';
    delete record.session;
    await storage.put('native-auth', record);
    return json({status: 'cancelled'});
  }
  if (action === 'poll') return json({status: record.status, ...(record.status === 'ready' ? {session: record.session} : {})});
  return json({error: 'Not found.'}, 404);
}
