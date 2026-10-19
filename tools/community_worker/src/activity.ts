import { adminAuthorized, HttpError, jsonResponse, readJsonObject, sha256Hex } from './security';
import type { Env } from './types';

export type ActivityEnv = Env & { ACTIVITY_COUNTER_ENABLED?: string; ACTIVITY_PING_LIMITER?: RateLimit };
export const ACTIVITY_MAX_BYTES = 768;
export const ACTIVITY_MINUTE_LIMIT = 120;
export const ACTIVITY_DAY_LIMIT = 2_000;
export const ACTIVITY_CLEANUP_DAY_LIMIT = 10_000;
export const ACTIVITY_CLEANUP_BATCH_SIZE = 250;
export const ACTIVITY_RETENTION_SECONDS = 48 * 3600;
const DAY = 86_400_000;
const KINDS = ['day', 'week', 'month'] as const;
type Kind = typeof KINDS[number];
type Period = { kind: Kind; start: string; end: string };
const date = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export function activityPeriods(now = Date.now()): Period[] {
  const d = new Date(now);
  const day = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  const week = day - ((d.getUTCDay() + 6) % 7) * DAY;
  return [
    {kind: 'day', start: date(day), end: date(day + DAY)},
    {kind: 'week', start: date(week), end: date(week + 7 * DAY)},
    {kind: 'month', start: date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)),
      end: date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))},
  ];
}

function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).sort().join('|') !== [...keys].sort().join('|')) {
    throw new HttpError(400, 'invalid_activity_payload');
  }
  return value as Record<string, unknown>;
}

async function admit(env: ActivityEnv, now: number): Promise<void> {
  // Global budgets use no IP, account or persistent client identifier.
  const windows = [
    ['day', Math.floor(now / DAY) * 86400, ACTIVITY_DAY_LIMIT],
    ['minute', Math.floor(now / 60000) * 60, ACTIVITY_MINUTE_LIMIT],
  ] as const;
  for (const [kind, start, limit] of windows) {
    const row = await env.DB.prepare(`INSERT INTO activity_budgets(kind,window_start,requests)
      VALUES(?1,?2,1) ON CONFLICT(kind,window_start) DO UPDATE SET
      requests=requests+1 WHERE requests<?3 RETURNING requests`).bind(kind, start, limit)
      .first<{requests: number}>();
    if (!row || row.requests > limit) throw new HttpError(429, 'activity_budget_exhausted');
  }
}

function activityLimiter(env: ActivityEnv): RateLimit | undefined {
  const limiter = env.ACTIVITY_PING_LIMITER;
  return limiter && typeof limiter.limit === 'function' ? limiter : undefined;
}

export async function handleActivityPing(request: Request, env: ActivityEnv): Promise<Response> {
  if (env.ACTIVITY_COUNTER_ENABLED !== '1') throw new HttpError(503, 'activity_disabled');
  const limiter = activityLimiter(env);
  if (!limiter) throw new HttpError(503, 'activity_unavailable');
  let admission: unknown;
  try {
    admission = await limiter.limit({key: 'kfps-activity-ping-v1'});
  } catch {
    throw new HttpError(503, 'activity_unavailable');
  }
  if (!admission || typeof admission !== 'object' || Array.isArray(admission)
      || !('success' in admission) || typeof admission.success !== 'boolean') {
    throw new HttpError(503, 'activity_unavailable');
  }
  if (!admission.success) throw new HttpError(429, 'activity_budget_exhausted');
  const url = new URL(request.url);
  if (url.search || request.headers.has('authorization') || request.headers.has('cookie')
      || request.headers.has('x-community-admin-token') || request.headers.has('x-community-test-token')
      || (request.headers.has('origin') && request.headers.get('origin') !== url.origin)) {
    throw new HttpError(400, 'activity_credentials_or_metadata_not_allowed');
  }
  const body = object(await readJsonObject(request, ACTIVITY_MAX_BYTES), ['v', 'periods']);
  if (body.v !== 1) throw new HttpError(400, 'activity_version_unsupported');
  const supplied = object(body.periods, [...KINDS]);
  const now = Date.now();
  const periods = activityPeriods(now);
  let wrongPeriod = false;
  for (const period of periods) {
    const item = object(supplied[period.kind], ['start', 'token']);
    if (typeof item.token !== 'string' || !/^[a-f0-9]{64}$/.test(item.token)
        || typeof item.start !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(item.start)) {
      throw new HttpError(400, 'invalid_activity_payload');
    }
    wrongPeriod ||= item.start !== period.start;
  }
  if (wrongPeriod) return jsonResponse({error: 'activity_period_changed', day: periods[0]!.start,
    utc: new Date(now).toISOString()}, 409);
  await admit(env, now);
  const statements: D1PreparedStatement[] = [];
  for (const period of periods) {
    const token = (supplied[period.kind] as Record<string, string>).token!;
    const hash = await sha256Hex(`kfps-activity-v1|${period.kind}|${period.start}|${token}`);
    statements.push(env.DB.prepare(`INSERT OR IGNORE INTO activity_tokens
      (kind,period_start,period_end,token_hash,expires_at) VALUES(?1,?2,?3,?4,?5)`)
      .bind(period.kind, period.start, period.end, hash,
        Date.parse(`${period.end}T00:00:00Z`) / 1000 + ACTIVITY_RETENTION_SECONDS));
  }
  statements.push(env.DB.prepare(`INSERT OR IGNORE INTO activity_metadata(key,value)
    VALUES('collection_started_day',?1)`).bind(periods[0]!.start));
  await env.DB.batch(statements);
  // No token, deduplication oracle, IP or request echo in the response.
  return jsonResponse({ok: true, day: periods[0]!.start});
}

export async function handleActivitySummary(request: Request, env: ActivityEnv): Promise<Response> {
  if (!adminAuthorized(request, env)) throw new HttpError(403, 'admin_required');
  if (new URL(request.url).search) throw new HttpError(400, 'activity_query_not_allowed');
  const now = Date.now();
  const periods = activityPeriods(now);
  const statements = periods.map(period => env.DB.prepare(`SELECT installations FROM activity_totals
    WHERE kind=?1 AND period_start=?2`).bind(period.kind, period.start));
  statements.push(env.DB.prepare("SELECT value FROM activity_metadata WHERE key='collection_started_day'"));
  statements.push(env.DB.prepare(`SELECT kind,requests FROM activity_budgets WHERE
    (kind='day' AND window_start=?1) OR (kind='minute' AND window_start=?2)`)
    .bind(Math.floor(now / DAY) * 86400, Math.floor(now / 60000) * 60));
  const rows = await env.DB.batch<Record<string, unknown>>(statements);
  return jsonResponse({
    schema: 1, metric: 'active_installations', timezone: 'UTC',
    enabled: env.ACTIVITY_COUNTER_ENABLED === '1' && Boolean(activityLimiter(env)), as_of: new Date(now).toISOString(),
    collection_started_day: rows[3]!.results[0]?.value ?? null,
    periods: periods.map((period, i) => ({...period,
      count: Number(rows[i]!.results[0]?.installations ?? 0)})),
    saturated: rows[4]!.results.some(row => Number(row.requests) >=
      (row.kind === 'day' ? ACTIVITY_DAY_LIMIT : ACTIVITY_MINUTE_LIMIT)),
  });
}

async function cleanupBatch(env: ActivityEnv, now: number,
    table: 'activity_tokens' | 'activity_budgets', columns: string, condition: string,
    values: (string | number)[]): Promise<number> {
  const selection = `SELECT ${columns} FROM ${table} WHERE ${condition} LIMIT ?${values.length + 1}`;
  const row = await env.DB.prepare(`SELECT COUNT(*) AS n FROM (${selection})`)
    .bind(...values, ACTIVITY_CLEANUP_BATCH_SIZE).first<{n: number}>();
  const count = Number(row?.n ?? 0);
  if (!count) return 0;
  // Reserve deletion slots atomically, including budget-row cleanup. A failed
  // deletion keeps its reservation; retries cannot overspend the daily quota.
  const reserved = await env.DB.prepare(`INSERT INTO activity_budgets(kind,window_start,requests)
    VALUES('cleanup',?1,?2) ON CONFLICT(kind,window_start) DO UPDATE SET
    requests=requests+?2 WHERE requests+?2<=?3 RETURNING requests`)
    .bind(Math.floor(now / DAY) * 86400, count, ACTIVITY_CLEANUP_DAY_LIMIT)
    .first<{requests: number}>();
  if (!reserved) return -1;
  const result = await env.DB.prepare(`DELETE FROM ${table} WHERE (${columns}) IN (${selection})`)
    .bind(...values, count).run();
  return Number(result.meta.changes ?? 0);
}

export async function cleanupActivity(env: ActivityEnv, now = Date.now()): Promise<void> {
  try {
    const seconds = Math.floor(now / 1000);
    // Indexed, bounded batches also cap month-boundary and missed-cron backlogs.
    for (const kind of ['minute', 'day', 'cleanup']) {
      if (await cleanupBatch(env, now, 'activity_budgets', 'kind,window_start',
        'kind=?1 AND window_start<?2 ORDER BY window_start',
        [kind, seconds - ACTIVITY_RETENTION_SECONDS]) < 0) return;
    }
    for (let batch = 0; batch < 4; batch++) {
      const removed = await cleanupBatch(env, now, 'activity_tokens', 'kind,period_start,token_hash',
        'expires_at<=?1 ORDER BY expires_at', [seconds]);
      if (removed < ACTIVITY_CLEANUP_BATCH_SIZE) break;
    }
  } catch {
    // A rejected scheduled promise can be logged by the platform with SQL bindings.
    console.warn('KFPS activity cleanup unavailable');
  }
}

export async function routeActivity(request: Request, env: ActivityEnv): Promise<Response | null> {
  const path = new URL(request.url).pathname.replace(/\/+$/, '');
  if (path !== '/v1/activity/ping' && path !== '/v1/admin/activity') return null;
  try {
    if (path === '/v1/activity/ping' && request.method === 'POST') return await handleActivityPing(request, env);
    if (path === '/v1/admin/activity' && request.method === 'GET') return await handleActivitySummary(request, env);
    return jsonResponse({error: 'method_not_allowed'}, 405, {Allow: path.endsWith('/ping') ? 'POST' : 'GET'});
  } catch (error) {
    // Do not pass D1 exceptions to the generic worker logger: SQL bindings may be in them.
    if (error instanceof HttpError) return jsonResponse({error: error.code}, error.status,
      error.status === 429 ? {'Retry-After': '1800'} : {});
    return jsonResponse({error: 'activity_unavailable'}, 503);
  }
}
