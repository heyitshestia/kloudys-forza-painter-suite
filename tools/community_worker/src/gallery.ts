import { enforceRateLimit, HttpError, jsonResponse, readJsonObject, requireUser } from './security';
import { visibleArtwork } from './catalog';
import { assertAvailable } from './availability';
import type { Env } from './types';

export async function handleVote(request: Request, env: Env, id: string): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, 'vote', 180, 3600);
  await visibleArtwork(env, id, user);
  const body = await readJsonObject(request, 1024);
  if (typeof body.vote !== 'number' || ![-1, 0, 1].includes(body.vote)) throw new HttpError(400, 'invalid_vote');
  const statement = body.vote === 0
    ? env.DB.prepare('DELETE FROM artwork_votes WHERE artwork_id = ?1 AND user_id = ?2').bind(id, user.id)
    : env.DB.prepare(`INSERT INTO artwork_votes(artwork_id, user_id, value, updated_at) VALUES (?1, ?2, ?3, ?4)
        ON CONFLICT(artwork_id, user_id) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`)
      .bind(id, user.id, body.vote, new Date().toISOString());
  await env.DB.batch([statement, env.DB.prepare(`UPDATE artworks SET vote_score =
    COALESCE((SELECT SUM(value) FROM artwork_votes WHERE artwork_id = ?1), 0) WHERE id = ?1`).bind(id)]);
  const row = await env.DB.prepare('SELECT vote_score FROM artworks WHERE id = ?1').bind(id).first<{ vote_score: number }>();
  return jsonResponse({ vote: body.vote, vote_score: row?.vote_score || 0 });
}

export async function handlePhoto(request: Request, env: Env, id: string, position: number): Promise<Response> {
  const user = await requireUser(request, env);
  const artwork = await visibleArtwork(env, id, user);
  assertAvailable(artwork, user, true);
  if (!Number.isInteger(position) || position < 0 || position > 2) throw new HttpError(404, 'asset_not_found');
  const record = await env.DB.prepare('SELECT object_key FROM artwork_photos WHERE artwork_id = ?1 AND position = ?2')
    .bind(id, position).first<{ object_key: string }>();
  const object = record ? await env.ASSETS.get(record.object_key) : null;
  if (!object) throw new HttpError(404, 'asset_not_found');
  return new Response(object.body, { headers: {
    'Content-Type': 'image/png', 'Cache-Control': 'private, no-store',
    'X-Content-Type-Options': 'nosniff', 'ETag': object.httpEtag,
  } });
}
