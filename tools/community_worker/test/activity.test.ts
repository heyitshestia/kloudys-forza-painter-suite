import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import worker from '../src/index';
import { ACTIVITY_DAY_LIMIT, ACTIVITY_MINUTE_LIMIT, ACTIVITY_CLEANUP_DAY_LIMIT,
  ACTIVITY_CLEANUP_BATCH_SIZE, activityPeriods, cleanupActivity,
  type ActivityEnv } from '../src/activity';

const NOW = Date.parse('2026-10-19T12:00:00.000Z');
// D1-focused tests admit at the native guard; dedicated cases below exercise the real binding.
const runtime: ActivityEnv = {...env, ACTIVITY_COUNTER_ENABLED: '1', VERSION_SYNC_ENABLED: '0',
  ACTIVITY_PING_LIMITER: {limit: async () => ({success: true})}};
const native = env as unknown as {
  ACTIVITY_PING_LIMITER: RateLimit; ACTIVITY_TEST_WINDOW_LIMITER: RateLimit;
};
const tables = ['activity_tokens', 'activity_totals', 'activity_budgets', 'activity_metadata'];

async function payload(seed = 'installation-1', now = Date.now()) {
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(seed),
    {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  return {v: 1, periods: Object.fromEntries(await Promise.all(activityPeriods(now).map(async period => {
    const bytes = await crypto.subtle.sign('HMAC', key,
      new TextEncoder().encode(`kfps-activity-v1|${period.kind}|${period.start}`));
    const token = [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
    return [period.kind, {start: period.start, token}];
  })))};
}

async function call(path: string, method = 'GET', body?: unknown,
    headers: Record<string, string> = {}, bindings = runtime) {
  const request = new Request('https://community.test' + path, {method,
    headers: {'Content-Type': 'application/json', ...headers},
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body)});
  const context = createExecutionContext();
  const response = await worker.fetch(request, bindings, context);
  await waitOnExecutionContext(context);
  return response;
}
async function scheduled(bindings = runtime) {
  const context = createExecutionContext();
  await worker.scheduled({scheduledTime: Date.now(), cron: '*/10 * * * *', noRetry() {}} as ScheduledController,
    bindings, context);
  await waitOnExecutionContext(context);
}
const ping = (body: unknown) => call('/v1/activity/ping', 'POST', body);
const summary = () => call('/v1/admin/activity', 'GET', undefined, {'X-Community-Admin-Token': env.ADMIN_TOKEN});
const counts = async () => ((await (await summary()).json()) as any).periods.map((x: any) => x.count);

async function seedBudgets(day: number, minute: number) {
  await env.DB.prepare(`INSERT INTO activity_budgets(kind,window_start,requests)
    VALUES('day',?1,?2),('minute',?3,?4)`)
    .bind(Math.floor(NOW / 86400000) * 86400, day, Math.floor(NOW / 60000) * 60, minute).run();
}
const budgets = async () => (await env.DB.prepare(`SELECT kind,window_start,requests
  FROM activity_budgets ORDER BY kind,window_start`).all<{
    kind: string; window_start: number; requests: number;
  }>()).results;

async function budgetUpdatesDuring(action: () => Promise<void>, includeCleanup = false) {
  await env.DB.prepare('CREATE TABLE activity_test_budget_updates(kind TEXT PRIMARY KEY, updates INTEGER)').run();
  try {
    await env.DB.prepare("INSERT INTO activity_test_budget_updates VALUES('day',0),('minute',0)").run();
    if (includeCleanup) await env.DB.prepare("INSERT INTO activity_test_budget_updates VALUES('cleanup',0)").run();
    // An UPDATE trigger fires even when the old query writes the same capped value.
    await env.DB.prepare(`CREATE TRIGGER activity_test_budget_update AFTER UPDATE ON activity_budgets
      BEGIN UPDATE activity_test_budget_updates SET updates=updates+1 WHERE kind=NEW.kind; END`).run();
    await action();
    return (await env.DB.prepare('SELECT kind,updates FROM activity_test_budget_updates ORDER BY kind')
      .all<{kind: string; updates: number}>()).results;
  } finally {
    await env.DB.prepare('DROP TRIGGER IF EXISTS activity_test_budget_update').run();
    await env.DB.prepare('DROP TABLE activity_test_budget_updates').run();
  }
}

beforeEach(async () => {
  await env.DB.batch(tables.map(table => env.DB.prepare(`DELETE FROM ${table}`)));
  vi.spyOn(Date, 'now').mockReturnValue(NOW);
});
afterEach(() => vi.restoreAllMocks());

it('counts separate day/week/month installation sets; never sums daily uniques', async () => {
  expect((await ping(await payload())).status).toBe(200);
  vi.spyOn(Date, 'now').mockReturnValue(NOW + 86400000);
  expect((await ping(await payload())).status).toBe(200);
  expect(await counts()).toEqual([1, 1, 1]);
  expect((await ping(await payload('installation-2'))).status).toBe(200);
  expect(await counts()).toEqual([2, 2, 2]);
  const response = await (await summary()).json() as any;
  expect(response.metric).toBe('active_installations');
  expect(response.periods[1]).toMatchObject({start: '2026-10-19', end: '2026-10-26'});
  expect(response.collection_started_day).toBe('2026-10-19');
  expect(response).not.toHaveProperty('tokens');
});

it('parallel duplicate requests and replay only increment once', async () => {
  const body = await payload();
  const requests = Array.from({length: 30}, () => ping(body));
  expect((await Promise.all(requests)).every(x => x.status === 200)).toBe(true);
  expect(await counts()).toEqual([1, 1, 1]);
  expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n).toBe(3);
});

it('week and month boundaries have distinct counts and ISO year crossing is Monday-based', async () => {
  expect(activityPeriods(Date.parse('2027-01-01T00:00:00Z'))[1]).toEqual(
    {kind: 'week', start: '2026-12-28', end: '2027-01-04'});
  expect(activityPeriods(Date.parse('2028-02-29T23:59:59Z'))[2]).toEqual(
    {kind: 'month', start: '2028-02-01', end: '2028-03-01'});
  await ping(await payload());
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-26T12:00:00Z'));
  await ping(await payload());
  expect(await counts()).toEqual([1, 1, 1]);
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-11-01T12:00:00Z'));
  await ping(await payload());
  expect(await counts()).toEqual([1, 1, 1]);
});

it('wrong clock returns current server period without writes; never backdates events', async () => {
  const response = await ping(await payload('clock', Date.parse('2025-01-01T00:00:00Z')));
  expect(response.status).toBe(409);
  expect(await response.json()).toEqual({error: 'activity_period_changed', day: '2026-10-19',
    utc: '2026-10-19T12:00:00.000Z'});
  expect(await counts()).toEqual([0, 0, 0]);
});

it.each([
  {name: 'path', value: 'C:/private/file.png'}, {name: 'github', value: 'someone'},
  {name: 'key', value: 'secret'}, {name: 'ip', value: '127.0.0.1'},
  {name: 'hardware_id', value: 'no'}, {name: '__proto__', value: 'no'},
])('rejects extra $name metadata without storing any part', async ({name, value}) => {
  const body = await payload();
  expect((await ping({...body, [name]: value})).status).toBe(400);
  expect(await counts()).toEqual([0, 0, 0]);
});

it('rejects nested metadata, invalid tokens, types, UTF8 and excessive bodies', async () => {
  const body: any = await payload();
  body.periods.day.account = 'private';
  expect((await ping(body)).status).toBe(400);
  delete body.periods.day.account;
  for (const token of [null, '', 'a'.repeat(65), 'A'.repeat(64), ['a'.repeat(64)], 12, '../file']) {
    body.periods.day.token = token;
    expect((await ping(body)).status).toBe(400);
  }
  expect((await ping('x'.repeat(769))).status).toBe(413);
  expect((await ping('[]')).status).toBe(400);
  expect((await ping('null')).status).toBe(400);
  expect((await ping('not json')).status).toBe(400);
  const context = createExecutionContext();
  const invalid = await worker.fetch(new Request('https://community.test/v1/activity/ping', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: new Uint8Array([255, 254])}), runtime, context);
  await waitOnExecutionContext(context);
  expect(invalid.status).toBe(400);
  expect(await counts()).toEqual([0, 0, 0]);
});

it('does not accept account credentials, cookies, foreign origins or query metadata', async () => {
  for (const headers of [{Authorization: 'Bearer private'}, {Cookie: 'session=private'},
    {'X-Community-Admin-Token': env.ADMIN_TOKEN}, {Origin: 'https://attacker.test'},
    {'X-Community-Test-Token': 'private'}]) {
    expect((await call('/v1/activity/ping', 'POST', await payload(), headers as any)).status).toBe(400);
  }
  expect((await call('/v1/activity/ping?user=private', 'POST', await payload())).status).toBe(400);
  expect((await call('/v1/activity/ping', 'POST', await payload(), {'Content-Type': 'text/plain'})).status).toBe(415);
});

it('only the existing admin credential can see aggregates, and methods are strict', async () => {
  await ping(await payload());
  expect((await call('/v1/admin/activity')).status).toBe(403);
  expect((await call('/v1/admin/activity', 'GET', undefined, {Authorization: 'Bearer community-session'})).status).toBe(403);
  expect((await call('/v1/admin/activity', 'POST', {})).status).toBe(405);
  expect((await call('/v1/activity/ping')).status).toBe(405);
  const response = await summary();
  expect(response.status).toBe(200);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
});

it('absent/invalid/disabled flag stops collection; old routes keep working', async () => {
  for (const flag of [undefined, '0', 'true', 'typo']) {
    expect((await call('/v1/activity/ping', 'POST', await payload(), {},
      {...runtime, ACTIVITY_COUNTER_ENABLED: flag})).status).toBe(503);
  }
  expect((await call('/v1/health')).status).toBe(200);
  expect((await call('/v1/session')).status).toBe(401);
  expect((await call('/v1/artworks?scope=browse')).status).toBe(200);
  expect(await counts()).toEqual([0, 0, 0]);
});

it('the native guard receives only a fixed route key and rejects before reading the body or D1', async () => {
  const limit = vi.fn(async () => ({success: false}));
  const prepare = vi.spyOn(env.DB, 'prepare');
  const batch = vi.spyOn(env.DB, 'batch');
  const request = new Request('https://community.test/v1/activity/ping', {method: 'POST',
    headers: {'Content-Type': 'application/json', 'CF-Connecting-IP': '192.0.2.1'}, body: 'not-json'});
  const context = createExecutionContext();
  const bindings: ActivityEnv = {...runtime, ACTIVITY_PING_LIMITER: {limit}};
  const response = await worker.fetch(request, bindings, context);
  await waitOnExecutionContext(context);
  expect(response.status).toBe(429);
  expect(response.headers.get('Retry-After')).toBe('1800');
  expect(await response.json()).toEqual({error: 'activity_budget_exhausted'});
  expect(limit).toHaveBeenCalledExactlyOnceWith({key: 'kfps-activity-ping-v1'});
  expect(request.bodyUsed).toBe(false);
  expect(prepare).not.toHaveBeenCalled();
  expect(batch).not.toHaveBeenCalled();
});

it.each([
  {name: 'missing binding', binding: undefined},
  {name: 'null binding', binding: null},
  {name: 'missing method', binding: {}},
  {name: 'invalid method', binding: {limit: 1}},
  {name: 'exception', binding: {limit: async () => { throw new Error('PRIVATE exception details'); }}},
  ...[undefined, null, {}, [], true, {success: 1}, {success: 'true'}].map((result, i) => (
    {name: 'malformed result ' + i, binding: {limit: async () => result}})),
])('native guard fails closed on $name with zero body reads, D1 calls or exception logs', async ({binding}) => {
  const prepare = vi.spyOn(env.DB, 'prepare');
  const batch = vi.spyOn(env.DB, 'batch');
  const logs = ['error', 'warn', 'log', 'info', 'debug'].map(method =>
    vi.spyOn(console, method as 'error').mockImplementation(() => {}));
  const request = new Request('https://community.test/v1/activity/ping', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: 'not-json'});
  const context = createExecutionContext();
  const bindings: ActivityEnv = {...runtime, ACTIVITY_PING_LIMITER: binding as unknown as RateLimit};
  const response = await worker.fetch(request, bindings, context);
  await waitOnExecutionContext(context);
  expect(response.status).toBe(503);
  expect(await response.json()).toEqual({error: 'activity_unavailable'});
  expect(request.bodyUsed).toBe(false);
  expect(prepare).not.toHaveBeenCalled();
  expect(batch).not.toHaveBeenCalled();
  expect(logs.every(log => log.mock.calls.length === 0)).toBe(true);
});

it('missing native binding reports collection disabled without changing the aggregate schema', async () => {
  await ping(await payload());
  const response = await call('/v1/admin/activity', 'GET', undefined,
    {'X-Community-Admin-Token': env.ADMIN_TOKEN}, {...runtime, ACTIVITY_PING_LIMITER: undefined});
  expect(response.status).toBe(200);
  const value = await response.json() as any;
  expect(value.enabled).toBe(false);
  expect(value.periods.map((row: any) => row.count)).toEqual([1, 1, 1]);
  expect(Object.keys(value).sort()).toEqual([
    'as_of', 'collection_started_day', 'enabled', 'metric', 'periods', 'saturated', 'schema', 'timezone',
  ]);
});

it('disabled collection, admin reads and other routes do not call the native limiter', async () => {
  const limit = vi.fn(async () => { throw new Error('Must not be called'); });
  const bindings = {...runtime, ACTIVITY_PING_LIMITER: {limit}, ACTIVITY_COUNTER_ENABLED: '0'};
  expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(503);
  expect((await call('/v1/admin/activity', 'GET', undefined,
    {'X-Community-Admin-Token': env.ADMIN_TOKEN}, bindings)).status).toBe(200);
  expect((await call('/v1/health', 'GET', undefined, {}, bindings)).status).toBe(200);
  expect((await call('/v1/session', 'GET', undefined, {}, bindings)).status).toBe(401);
  expect(limit).not.toHaveBeenCalled();
});

it('real workerd native 60/minute limiter rejects concurrent overflow without body reads or D1', async () => {
  const bindings = {...runtime, ACTIVITY_PING_LIMITER: native.ACTIVITY_PING_LIMITER};
  expect((await call('/v1/activity/ping', 'POST', await payload(), {}, bindings)).status).toBe(200);
  for (let attempt = 1; attempt < 60; attempt++) {
    expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(400);
  }
  expect(await counts()).toEqual([1, 1, 1]);
  const prepare = vi.spyOn(env.DB, 'prepare');
  const batch = vi.spyOn(env.DB, 'batch');
  const requests = Array.from({length: 32}, () => new Request('https://community.test/v1/activity/ping', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: 'not-json'}));
  const responses = await Promise.all(requests.map(async request => {
    const context = createExecutionContext();
    const response = await worker.fetch(request, bindings, context);
    await waitOnExecutionContext(context);
    return response;
  }));
  expect(responses.every(response => response.status === 429 && response.headers.get('Retry-After') === '1800')).toBe(true);
  expect(requests.every(request => !request.bodyUsed)).toBe(true);
  expect(prepare).not.toHaveBeenCalled();
  expect(batch).not.toHaveBeenCalled();
});

it('real workerd native limiter allows traffic again after its local test window', async () => {
  const bindings = {...runtime, ACTIVITY_PING_LIMITER: native.ACTIVITY_TEST_WINDOW_LIMITER};
  const prepare = vi.spyOn(env.DB, 'prepare');
  const batch = vi.spyOn(env.DB, 'batch');
  expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(400);
  expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(400);
  expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(429);
  await new Promise(resolve => setTimeout(resolve, 11000));
  expect((await call('/v1/activity/ping', 'POST', 'not-json', {}, bindings)).status).toBe(400);
  expect(prepare).not.toHaveBeenCalled();
  expect(batch).not.toHaveBeenCalled();
}, 20000);

it('global flood budgets bound accepted requests without IP rows', async () => {
  await env.DB.prepare("INSERT INTO activity_budgets VALUES('minute',?1,?2)")
    .bind(Math.floor(NOW / 60000) * 60, ACTIVITY_MINUTE_LIMIT - 1).run();
  expect((await ping(await payload())).status).toBe(200);
  const response = await ping(await payload('flood'));
  expect(response.status).toBe(429);
  expect(response.headers.get('Retry-After')).toBe('1800');
  expect(await counts()).toEqual([1, 1, 1]);
  vi.spyOn(Date, 'now').mockReturnValue(NOW + 60000);
  await env.DB.prepare("UPDATE activity_budgets SET requests=?1 WHERE kind='day'").bind(ACTIVITY_DAY_LIMIT).run();
  expect((await ping(await payload('flood2'))).status).toBe(429);
  expect((await env.DB.prepare('SELECT * FROM activity_budgets').all()).results.every(
    row => Object.keys(row).sort().join(',') === 'kind,requests,window_start')).toBe(true);
  expect((await (await summary()).json() as any).saturated).toBe(true);
});

it.each(['day', 'minute'] as const)('%s budget admits its last slot and then stays at the exact cap', async kind => {
  const day = kind === 'day' ? ACTIVITY_DAY_LIMIT - 1 : 10;
  const minute = kind === 'minute' ? ACTIVITY_MINUTE_LIMIT - 1 : 20;
  await seedBudgets(day, minute);
  expect((await ping(await payload())).status).toBe(200);
  const denied = await ping(await payload('after-cap'));
  expect(denied.status).toBe(429);
  expect(denied.headers.get('Retry-After')).toBe('1800');
  expect(await denied.json()).toEqual({error: 'activity_budget_exhausted'});
  expect((await budgets()).map(row => row.requests)).toEqual([
    kind === 'day' ? ACTIVITY_DAY_LIMIT : day + 2,
    kind === 'minute' ? ACTIVITY_MINUTE_LIMIT : minute + 1,
  ]);
  expect(await counts()).toEqual([1, 1, 1]);
});

it.each(['day', 'minute'] as const)('%s budget admits exactly its remaining slots under concurrency', async kind => {
  const remaining = 5;
  const attempts = 32;
  const day = kind === 'day' ? ACTIVITY_DAY_LIMIT - remaining : 10;
  const minute = kind === 'minute' ? ACTIVITY_MINUTE_LIMIT - remaining : 20;
  await seedBudgets(day, minute);
  const body = await payload();
  const responses = await Promise.all(Array.from({length: attempts}, () => ping(body)));
  expect(responses.filter(response => response.status === 200)).toHaveLength(remaining);
  expect(responses.filter(response => response.status === 429)).toHaveLength(attempts - remaining);
  expect((await budgets()).map(row => row.requests)).toEqual([
    kind === 'day' ? ACTIVITY_DAY_LIMIT : day + attempts,
    kind === 'minute' ? ACTIVITY_MINUTE_LIMIT : minute + remaining,
  ]);
  expect(await counts()).toEqual([1, 1, 1]);
});

it('a full day budget causes zero SQL updates for repeated sequential and concurrent denials', async () => {
  await seedBudgets(ACTIVITY_DAY_LIMIT, 20);
  const before = await budgets();
  const body = await payload();
  const updates = await budgetUpdatesDuring(async () => {
    for (let attempt = 0; attempt < 64; attempt++) {
      expect((await ping(body)).status).toBe(429);
    }
    const responses = await Promise.all(Array.from({length: 96}, () => ping(body)));
    expect(responses.every(response => response.status === 429)).toBe(true);
    vi.spyOn(Date, 'now').mockReturnValue(NOW + 60000);
    expect((await ping(body)).status).toBe(429);
  });
  expect(updates).toEqual([{kind: 'day', updates: 0}, {kind: 'minute', updates: 0}]);
  expect(await budgets()).toEqual(before);
  expect(await counts()).toEqual([0, 0, 0]);
  expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n).toBe(0);
});

it('a full minute budget does not update itself while preserving the day-first admission policy', async () => {
  await seedBudgets(10, ACTIVITY_MINUTE_LIMIT);
  const body = await payload();
  const updates = await budgetUpdatesDuring(async () => {
    const responses = await Promise.all(Array.from({length: 32}, () => ping(body)));
    expect(responses.every(response => response.status === 429)).toBe(true);
  });
  expect(updates).toEqual([{kind: 'day', updates: 32}, {kind: 'minute', updates: 0}]);
  expect((await budgets()).map(row => row.requests)).toEqual([42, ACTIVITY_MINUTE_LIMIT]);
  expect(await counts()).toEqual([0, 0, 0]);
});

it('new minute and UTC day windows recover without changing the previous capped rows', async () => {
  await seedBudgets(10, ACTIVITY_MINUTE_LIMIT);
  expect((await ping(await payload())).status).toBe(429);
  vi.spyOn(Date, 'now').mockReturnValue(NOW + 60000);
  expect((await ping(await payload())).status).toBe(200);
  await env.DB.prepare("UPDATE activity_budgets SET requests=?1 WHERE kind='day'")
    .bind(ACTIVITY_DAY_LIMIT).run();
  expect((await ping(await payload())).status).toBe(429);
  const before = await budgets();
  vi.spyOn(Date, 'now').mockReturnValue(NOW + 86400000);
  expect((await ping(await payload())).status).toBe(200);
  const after = await budgets();
  for (const row of before) expect(after).toContainEqual(row);
  expect(after.filter(row => !before.some(old => old.kind === row.kind && old.window_start === row.window_start))
    .map(row => row.requests)).toEqual([1, 1]);
  expect(await counts()).toEqual([1, 1, 1]);
});

it('real scheduled handler removes expired tokens even while collection is disabled; aggregates survive', async () => {
  const body: any = await payload();
  await ping(body);
  const rows = await env.DB.prepare('SELECT * FROM activity_tokens').all();
  expect(JSON.stringify(rows.results)).not.toContain(body.periods.day.token);
  const whole = await env.DB.prepare('SELECT * FROM activity_totals').all();
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-22T00:00:00Z'));
  await scheduled({...runtime, ACTIVITY_COUNTER_ENABLED: '0'});
  expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM activity_tokens WHERE kind='day'").first<any>()).n).toBe(0);
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-11-03T00:00:00Z'));
  await scheduled({...runtime, ACTIVITY_COUNTER_ENABLED: '0'});
  expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n).toBe(0);
  expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM activity_budgets WHERE kind!='cleanup'")
    .first<any>()).n).toBe(0);
  expect((await env.DB.prepare('SELECT * FROM activity_totals').all()).results).toEqual(whole.results);
});

async function expiredTokens(count: number, expires = Math.floor(NOW / 1000) - 1) {
  await env.DB.prepare(`WITH RECURSIVE ids(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM ids WHERE n<?1)
    INSERT INTO activity_tokens(kind,period_start,period_end,token_hash,expires_at)
    SELECT CASE n%3 WHEN 0 THEN 'month' WHEN 1 THEN 'day' ELSE 'week' END,
      '2026-09-01','2026-10-01',printf('%064x',n),?2 FROM ids`).bind(count, expires).run();
}

it('empty cleanup schedules spend no write budget and indexed expiry probes avoid full scans', async () => {
  for (let run = 0; run < 4; run++) await cleanupActivity(runtime, NOW);
  expect(await budgets()).toEqual([]);
  const tokens = await env.DB.prepare(`EXPLAIN QUERY PLAN SELECT kind,period_start,token_hash
    FROM activity_tokens WHERE expires_at<=?1 ORDER BY expires_at LIMIT 250`).bind(NOW / 1000).all();
  expect(JSON.stringify(tokens.results)).toContain('activity_tokens_expiry');
  const budgetPlan = await env.DB.prepare(`EXPLAIN QUERY PLAN SELECT kind,window_start
    FROM activity_budgets WHERE kind='minute' AND window_start<?1 ORDER BY window_start LIMIT 250`)
    .bind(NOW / 1000).all();
  expect(JSON.stringify(budgetPlan.results)).toContain('PRIMARY KEY');
});

it('cleanup counts actual small batches instead of wasting a full reservation per schedule', async () => {
  await expiredTokens(3);
  await cleanupActivity(runtime, NOW);
  expect((await budgets()).filter(row => row.kind === 'cleanup').map(row => row.requests)).toEqual([3]);
  await cleanupActivity(runtime, NOW);
  expect((await budgets()).filter(row => row.kind === 'cleanup').map(row => row.requests)).toEqual([3]);
});

it('month/week/day expiry and stale admission rows share one hard daily deletion budget', async () => {
  await expiredTokens(ACTIVITY_CLEANUP_DAY_LIMIT + 1000);
  await env.DB.prepare("INSERT INTO activity_budgets VALUES('minute',?1,1),('day',?1,1)")
    .bind(Math.floor(NOW / 1000) - ACTIVITY_RETENTION_TEST).run();
  const before = await env.DB.prepare('SELECT * FROM activity_totals ORDER BY kind').all();
  for (let run = 0; run < 15; run++) await cleanupActivity(runtime, NOW);
  const reserved = (await budgets()).find(row => row.kind === 'cleanup')!;
  expect(reserved.requests).toBeLessThanOrEqual(ACTIVITY_CLEANUP_DAY_LIMIT);
  expect(reserved.requests).toBeGreaterThan(ACTIVITY_CLEANUP_DAY_LIMIT - ACTIVITY_CLEANUP_BATCH_SIZE);
  const remaining = Number((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n);
  expect(remaining).toBe(ACTIVITY_CLEANUP_DAY_LIMIT + 1000 - reserved.requests + 2);
  const updates = await budgetUpdatesDuring(async () => {
    for (let run = 0; run < 8; run++) await cleanupActivity(runtime, NOW);
  }, true);
  expect(updates.every(row => row.updates === 0)).toBe(true);
  expect(await budgets()).toEqual([reserved]);
  await cleanupActivity(runtime, NOW + 86400000);
  expect(Number((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n))
    .toBe(remaining - 4 * ACTIVITY_CLEANUP_BATCH_SIZE);
  expect((await env.DB.prepare('SELECT * FROM activity_totals ORDER BY kind').all()).results).toEqual(before.results);
});

const ACTIVITY_RETENTION_TEST = 48 * 3600 + 1;

it('concurrent scheduled cleanups cannot exceed remaining daily deletion slots', async () => {
  await expiredTokens(1000);
  await env.DB.prepare("INSERT INTO activity_budgets VALUES('cleanup',?1,?2)")
    .bind(Math.floor(NOW / 86400000) * 86400, ACTIVITY_CLEANUP_DAY_LIMIT - 500).run();
  await Promise.all(Array.from({length: 8}, () => cleanupActivity(runtime, NOW)));
  expect((await budgets()).find(row => row.kind === 'cleanup')!.requests).toBe(ACTIVITY_CLEANUP_DAY_LIMIT);
  expect(Number((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n)).toBe(500);
});

it('failed deletion retains its reservation and logs no payload; next day recovers', async () => {
  await expiredTokens(3);
  await env.DB.prepare(`CREATE TRIGGER activity_test_delete_fail BEFORE DELETE ON activity_tokens
    BEGIN SELECT RAISE(ABORT,'private deletion failure'); END`).run();
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {});
  try {
    await cleanupActivity(runtime, NOW);
    expect((await budgets()).find(row => row.kind === 'cleanup')!.requests).toBe(3);
    expect(warning).toHaveBeenCalledExactlyOnceWith('KFPS activity cleanup unavailable');
    expect(Number((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n)).toBe(3);
  } finally { await env.DB.prepare('DROP TRIGGER activity_test_delete_fail').run(); }
  await cleanupActivity(runtime, NOW + 86400000);
  expect((await budgets()).filter(row => row.kind === 'cleanup').map(row => row.requests)).toEqual([3, 3]);
  expect(Number((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n)).toBe(0);
});

it('database failures never leak tokens, SQL, paths or exception messages', async () => {
  const logs = ['error', 'warn', 'log', 'info', 'debug'].map(method =>
    vi.spyOn(console, method as 'error').mockImplementation(() => {}));
  const body: any = await payload();
  const bindings = {...runtime, DB: {prepare: () => {
    throw new Error('SECRET SQL TOKEN ' + body.periods.day.token);
  }} as any};
  for (const path of ['/v1/activity/ping', '/v1/admin/activity']) {
    const response = path.endsWith('ping')
      ? await call(path, 'POST', body, {}, bindings)
      : await call(path, 'GET', undefined, {'X-Community-Admin-Token': env.ADMIN_TOKEN}, bindings);
    expect(response.status).toBe(503);
    expect(await response.text()).toBe('{"error":"activity_unavailable"}');
  }
  expect(logs.every(log => log.mock.calls.length === 0)).toBe(true);
});

it('real scheduled cleanup database errors log only a fixed warning without SQL or tokens', async () => {
  const logs = ['error', 'warn', 'log', 'info', 'debug'].map(method =>
    vi.spyOn(console, method as 'error').mockImplementation(() => {}));
  const body: any = await payload();
  const originalPrepare = runtime.DB.prepare.bind(runtime.DB);
  vi.spyOn(runtime.DB, 'prepare').mockImplementation(sql => {
    if (sql.includes('activity_')) throw new Error('SECRET SQL ' + body.periods.day.token);
    return originalPrepare(sql);
  });
  await scheduled({...runtime, ACTIVITY_COUNTER_ENABLED: '0'});
  expect(logs.flatMap(log => log.mock.calls)).toEqual([['KFPS activity cleanup unavailable']]);
});

it('one failing insert rolls the whole three-period transaction back', async () => {
  await env.DB.prepare(`CREATE TRIGGER activity_test_fail BEFORE INSERT ON activity_tokens
    WHEN NEW.kind='month' BEGIN SELECT RAISE(ABORT,'synthetic rejection'); END`).run();
  try {
    expect((await ping(await payload())).status).toBe(503);
    expect(await counts()).toEqual([0, 0, 0]);
    expect((await env.DB.prepare('SELECT COUNT(*) AS n FROM activity_tokens').first<any>()).n).toBe(0);
  } finally { await env.DB.prepare('DROP TRIGGER activity_test_fail').run(); }
});
