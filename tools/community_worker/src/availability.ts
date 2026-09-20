import { HttpError } from './security';
import type { Env, SessionUser } from './types';

export function validateSchedule(value: Record<string, unknown>): { startsAt: string | null; endsAt: string | null } {
  if (value.starts_at == null && value.ends_at == null) return { startsAt: null, endsAt: null };
  const parse = (raw: unknown): number => typeof raw === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(raw) ? Date.parse(raw) : NaN;
  const start = parse(value.starts_at);
  const end = parse(value.ends_at);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end <= Date.now()) {
    throw new HttpError(400, 'invalid_schedule', 'Choose a start and a later end time, with the end in the future.');
  }
  return { startsAt: new Date(start).toISOString(), endsAt: new Date(end).toISOString() };
}

export function assertAvailable(row: Record<string, unknown>, user: SessionUser | null, ownerUpcoming = false): void {
  const now = Date.now();
  if (row.purged_at || (row.ends_at && Date.parse(String(row.ends_at)) <= now)
      || (row.starts_at && Date.parse(String(row.starts_at)) > now
          && !(ownerUpcoming && user?.id === row.creator_id))) {
    throw new HttpError(404, 'artwork_not_found');
  }
}

export const AVAILABLE_SQL = `(a.purged_at IS NULL AND
  (a.starts_at IS NULL OR a.starts_at <= strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) AND
  (a.ends_at IS NULL OR a.ends_at > strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))`;

// Access checks enforce the deadline independently of this retryable cleanup.
// Keep metadata/tombstones for staff; never mark purged until every R2 delete succeeds.
export async function purgeExpiredArtwork(env: Env): Promise<{ purged: number; failed: number }> {
  const now = new Date().toISOString();
  const rows = await env.DB.prepare(`SELECT id FROM artworks
    WHERE ends_at <= ?1 AND purged_at IS NULL ORDER BY ends_at LIMIT 20`).bind(now).all<{ id: string }>();
  let purged = 0, failed = 0;
  for (const row of rows.results || []) {
    try {
      let cursor: string | undefined;
      do {
        const page = await env.ASSETS.list({ prefix: `artworks/${row.id}/`, limit: 1000, cursor });
        if (page.objects.length) await env.ASSETS.delete(page.objects.map(item => item.key));
        cursor = page.truncated ? page.cursor : undefined;
      } while (cursor);
      await env.DB.batch([
        env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(row.id),
        env.DB.prepare("UPDATE artwork_revisions SET status = 'removed' WHERE artwork_id = ?1").bind(row.id),
        env.DB.prepare("DELETE FROM artwork_photos WHERE artwork_id = ?1").bind(row.id),
        env.DB.prepare("UPDATE artworks SET status = 'removed', featured = 0, purged_at = ?2 WHERE id = ?1 AND ends_at <= ?2").bind(row.id, now),
        env.DB.prepare(`INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
          VALUES (?1, ?2, 'system', 'expired_purged', 'Scheduled files and media deleted.', ?3)`)
          .bind(crypto.randomUUID(), row.id, now),
      ]);
      purged++;
    } catch (error) {
      failed++;
      console.error('Scheduled artwork cleanup will retry', row.id, error);
    }
  }
  return { purged, failed };
}
