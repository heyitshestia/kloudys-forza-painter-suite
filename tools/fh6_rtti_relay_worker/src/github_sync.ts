import { sha256Hex } from "./protocol";

const DEFAULT_REPOSITORY = "heyitshestia/kloudys-forza-painter-suite";
const EVENT_TYPE = "fh6-rtti-registry-updated";
const API_VERSION = "2022-11-28";
const MAX_DISPATCH_ATTEMPTS = 8;

export interface GithubSyncEnv {
  DB: D1Database;
  GITHUB_RTTI_SYNC_TOKEN?: string;
}

interface OutboxRow {
  event_id: string;
  registry_fingerprint: string;
  profile_id: string;
  updated_at: string;
  attempt_count: number;
}

export interface GithubSyncResult {
  configured: boolean;
  delivered: number;
  failed: number;
  pending: number;
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export async function prepareGithubSyncOutbox(
  env: GithubSyncEnv,
  profile: unknown,
  profileId: string,
  updatedAt: string,
): Promise<{ fingerprint: string; statement: D1PreparedStatement }> {
  const canonical = JSON.stringify(profile);
  const fingerprint = await sha256Hex(new TextEncoder().encode(canonical));
  return {
    fingerprint,
    statement: env.DB.prepare(
      `INSERT OR IGNORE INTO github_sync_outbox(
         event_id, registry_fingerprint, profile_id, updated_at, status, created_at
       ) VALUES (?1, ?2, ?3, ?4, 'pending', ?4)`,
    ).bind(crypto.randomUUID(), fingerprint, profileId, updatedAt),
  };
}

async function pendingCount(env: GithubSyncEnv): Promise<number> {
  const row = await env.DB.prepare(
    "SELECT COUNT(*) AS count FROM github_sync_outbox WHERE status != 'delivered'",
  ).first<{ count: number }>();
  return Number(row?.count || 0);
}

export async function dispatchPendingGithubSync(
  env: GithubSyncEnv,
  fetcher: Fetcher = fetch,
): Promise<GithubSyncResult> {
  const token = (env.GITHUB_RTTI_SYNC_TOKEN || "").trim();
  if (!token) {
    return { configured: false, delivered: 0, failed: 0, pending: await pendingCount(env) };
  }

  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE github_sync_outbox
       SET status = 'failed', last_error = 'dispatch lease expired'
       WHERE status = 'dispatching'
         AND datetime(last_attempt_at) < datetime(?1, '-10 minutes')`,
    ).bind(now),
    env.DB.prepare(
      `DELETE FROM github_sync_outbox
       WHERE status = 'delivered'
         AND datetime(delivered_at) < datetime(?1, '-90 days')`,
    ).bind(now),
  ]);

  const row = await env.DB.prepare(
    `SELECT event_id, registry_fingerprint, profile_id, updated_at, attempt_count
     FROM github_sync_outbox
     WHERE status IN ('pending', 'failed') AND attempt_count < ?1
     ORDER BY created_at DESC LIMIT 1`,
  ).bind(MAX_DISPATCH_ATTEMPTS).first<OutboxRow>();
  if (!row) return { configured: true, delivered: 0, failed: 0, pending: await pendingCount(env) };

  const attemptAt = new Date().toISOString();
  const claimed = await env.DB.prepare(
    `UPDATE github_sync_outbox
     SET status = 'dispatching', attempt_count = attempt_count + 1,
         last_attempt_at = ?1, last_error = ''
     WHERE event_id = ?2 AND status IN ('pending', 'failed')`,
  ).bind(attemptAt, row.event_id).run();
  if (claimed.meta.changes !== 1) {
    return { configured: true, delivered: 0, failed: 0, pending: await pendingCount(env) };
  }

  try {
    const response = await fetcher(`https://api.github.com/repos/${DEFAULT_REPOSITORY}/dispatches`, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "User-Agent": "KFPS-FH6-RTTI-Relay/1",
        "X-GitHub-Api-Version": API_VERSION,
      },
      body: JSON.stringify({
        event_type: EVENT_TYPE,
        client_payload: {
          profile_id: row.profile_id,
          registry_fingerprint: row.registry_fingerprint,
          updated_utc: row.updated_at,
        },
      }),
    });
    if (response.status !== 204) throw new Error(`GitHub dispatch returned HTTP ${response.status}`);
    const deliveredAt = new Date().toISOString();
    const completed = await env.DB.prepare(
      `UPDATE github_sync_outbox
       SET status = 'delivered', delivered_at = ?1, last_error = ''
       WHERE datetime(created_at) <= datetime(?2)
         AND status IN ('pending', 'failed', 'dispatching')`,
    ).bind(deliveredAt, row.updated_at).run();
    return {
      configured: true,
      delivered: Number(completed.meta.changes || 0),
      failed: 0,
      pending: await pendingCount(env),
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "GitHub dispatch failed";
    await env.DB.prepare(
      "UPDATE github_sync_outbox SET status = 'failed', last_error = ?1 WHERE event_id = ?2",
    ).bind(message.slice(0, 200), row.event_id).run();
    console.error(JSON.stringify({ event: "github_rtti_sync_failed", event_id: row.event_id, error: message }));
    return { configured: true, delivered: 0, failed: 1, pending: await pendingCount(env) };
  }
}
