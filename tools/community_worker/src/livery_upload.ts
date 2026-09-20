import { Unzip, UnzipInflate } from 'fflate';
import { enforceRateLimit, HttpError, jsonResponse, plainText, requireUser, sha256Hex } from './security';
import { validatePng, validateUploadMetadata } from './validation';
import { effectiveMinimumUploadVersion, getVersionPolicy } from './version_policy';
import { requireActiveSupporter } from './supporter';
import type { Env } from './types';

export const MAX_LIVERY_BYTES = 16 * 1024 * 1024;
const MAX_EXPANDED_BYTES = 32 * 1024 * 1024;
const MAX_MEMBER_BYTES = 8 * 1024 * 1024;
const MAX_BODY_BYTES = 26 * 1024 * 1024;

function invalid(message = 'The livery package is invalid.'): never {
  throw new HttpError(400, 'invalid_livery', message);
}

// fflate is MIT licensed. Bound actual decompressor output, not only ZIP headers.
// This is a server integrity/format check; the desktop additionally decodes the
// native source and verifies derived geometry before upload, download or render.
export async function validateLivery(bytes: Uint8Array): Promise<{ car: string; shapes: number }> {
  if (!bytes.length || bytes.length > MAX_LIVERY_BYTES) throw new HttpError(413, 'livery_too_large');
  const members = new Map<string, Uint8Array>();
  const names = new Set<string>();
  let total = 0, finished = 0;
  const unzip = new Unzip(file => {
    const name = file.name;
    if (names.size >= 256 || !name || name.startsWith('/') || /[\\:\x00-\x1f]/.test(name)
        || name.split('/').some(part => !part || part === '.' || part === '..')
        || names.has(name.toLowerCase())) invalid('Unsafe or duplicate package path.');
    if (!(name === 'manifest.json' || /^(source\/fh6\/(C_livery|header|bigThumb\.webp)|(?:livery|mesh|projection|preview)\/[A-Za-z0-9_./-]+\.(json|png|webp|glb))$/.test(name))) {
      invalid('The package contains an unsupported file.');
    }
    names.add(name.toLowerCase());
    if ((file.originalSize || 0) > MAX_MEMBER_BYTES) invalid('A package member exceeds 8 MiB.');
    let size = 0;
    const chunks: Uint8Array[] = [];
    file.ondata = (error, data, final) => {
      if (error) invalid();
      size += data.length; total += data.length;
      if (size > MAX_MEMBER_BYTES || total > MAX_EXPANDED_BYTES) invalid('The expanded package exceeds its size limit.');
      chunks.push(data);
      if (final) {
        const content = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) { content.set(chunk, offset); offset += chunk.length; }
        chunks.length = 0;
        members.set(name, content); finished++;
      }
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  try {
    for (let offset = 0; offset < bytes.length; offset += 32768) {
      unzip.push(bytes.subarray(offset, offset + 32768), offset + 32768 >= bytes.length);
    }
  } catch (error) {
    if (error instanceof HttpError) throw error;
    invalid();
  }
  if (!names.size || finished !== names.size) invalid('Incomplete ZIP archive.');
  const raw = members.get('manifest.json');
  if (!raw || raw.length > 2 * 1024 * 1024) invalid('Missing or oversized manifest.');
  let manifest: Record<string, any>;
  try { manifest = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(raw)); }
  catch { invalid('Invalid manifest JSON.'); }
  if (!manifest || manifest.format !== 'kfps_full_livery_package_v1' || manifest.format_version !== 1
      || manifest.compiler_revision !== 11 || manifest.source?.game !== 'fh6'
      || manifest.source?.owned !== true || manifest.sharing?.exportable !== true
      || manifest.sharing?.contains_foreign_vinyl_groups !== false) invalid('Only shareable, current FH6 livery packages are accepted.');
  if (!Array.isArray(manifest.files) || manifest.files.length !== members.size - 1) invalid('The manifest does not cover the archive.');
  const seen = new Set<string>();
  for (const record of manifest.files) {
    const data = members.get(record?.path);
    if (!data || record.path === 'manifest.json' || seen.has(record.path) || record.size !== data.length
        || record.sha256 !== await sha256Hex(data)) invalid('Package integrity check failed.');
    seen.add(record.path);
  }
  for (const name of ['source/fh6/C_livery', 'livery/layers.json', 'mesh/vehicle.json', 'projection/index.json']) {
    if (!seen.has(name)) invalid('Required livery data is missing.');
  }
  const shapes = manifest.livery?.decoded_layer_count;
  if (!Number.isInteger(shapes) || shapes < 0 || shapes > 15000) invalid('Invalid livery layer count.');
  const car = plainText(String(manifest.vehicle?.model_code || manifest.livery?.target_car_id || ''), 'car', 120, true);
  return { car, shapes };
}

async function limitedForm(request: Request): Promise<FormData> {
  if (!request.headers.get('content-type')?.startsWith('multipart/form-data;') || !request.body) {
    throw new HttpError(415, 'multipart_required');
  }
  if (Number(request.headers.get('content-length')) > MAX_BODY_BYTES) throw new HttpError(413, 'request_too_large');
  let length = 0;
  const stream = request.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      length += chunk.byteLength;
      if (length > MAX_BODY_BYTES) throw new HttpError(413, 'request_too_large');
      controller.enqueue(chunk);
    },
  }));
  try { return await new Response(stream, { headers: { 'Content-Type': request.headers.get('content-type')! } }).formData(); }
  catch (error) { if (length > MAX_BODY_BYTES) throw new HttpError(413, 'request_too_large'); throw new HttpError(400, 'invalid_multipart'); }
}

async function imagePart(form: FormData, name: string, limit: number, dimension: number): Promise<Uint8Array> {
  const part = form.get(name);
  if (!(part instanceof File) || part.size > limit) throw new HttpError(400, 'invalid_preview');
  const bytes = new Uint8Array(await part.arrayBuffer());
  validatePng(bytes, dimension);
  return bytes;
}

export async function handleLiveryUpload(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, 'livery_upload', 12, 1800);
  const form = await limitedForm(request);
  const meta = form.get('metadata');
  if (typeof meta !== 'string' || meta.length > 16384) throw new HttpError(400, 'invalid_metadata');
  let body: Record<string, unknown>;
  try { body = JSON.parse(meta); } catch { throw new HttpError(400, 'invalid_json'); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw new HttpError(400, 'invalid_metadata');
  const policy = await getVersionPolicy(env);
  const upload = validateUploadMetadata(body, effectiveMinimumUploadVersion(env, policy));
  if (upload.supporterOnly) requireActiveSupporter(user);
  const source = form.get('package');
  if (!(source instanceof File) || source.size > MAX_LIVERY_BYTES) throw new HttpError(413, 'livery_too_large');
  const bytes = new Uint8Array(await source.arrayBuffer());
  const livery = await validateLivery(bytes);
  const photoCount = body.photo_count;
  if (!Number.isInteger(photoCount) || Number(photoCount) < 0 || Number(photoCount) > 3) throw new HttpError(400, 'invalid_photo_count');
  for (const key of form.keys()) {
    if (key.startsWith('photo') && !Array.from({ length: Number(photoCount) }, (_, index) => `photo${index}`).includes(key)) {
      throw new HttpError(400, 'invalid_photo_count');
    }
  }
  const photos: Uint8Array[] = [];
  for (let index = 0; index < Number(photoCount); index++) photos.push(await imagePart(form, `photo${index}`, 2 * 1024 * 1024, 2048));
  const thumbnail = await imagePart(form, 'thumbnail', 512 * 1024, 640);
  // New clients send the package's in-game cover separately from optional photos.
  // Preserve uploads from older clients that used their first photo as the cover.
  const preview = form.has('preview') ? await imagePart(form, 'preview', 2 * 1024 * 1024, 2048) : photos[0] || thumbnail;
  const hash = await sha256Hex(bytes);
  const published = env.AUTO_PUBLISH_VALIDATED_UPLOADS === '1'
    || (env.ALLOW_TEST_AUTH === '1' && env.AUTO_APPROVE_TEST_UPLOADS === '1' && user.provider === 'local-test');
  const status = published ? 'published' : 'pending';
  const duplicate = await env.DB.prepare(`SELECT id, creator_id, status, purged_at, starts_at, ends_at, supporter_only,
    (SELECT action FROM moderation_events WHERE artwork_id = artworks.id ORDER BY created_at DESC, rowid DESC LIMIT 1) AS last_action
    FROM artworks WHERE content_hash = ?1 LIMIT 1`).bind(hash).first<Record<string, unknown>>();
  if (duplicate) {
    if (duplicate.creator_id !== user.id || duplicate.status !== 'removed' || duplicate.purged_at
        || duplicate.last_action !== 'owner_removed' || duplicate.ends_at) throw new HttpError(409, 'duplicate_artwork');
    const now = new Date().toISOString();
    if (duplicate.supporter_only) requireActiveSupporter(user);
    const restored = await env.DB.batch([
      env.DB.prepare(`UPDATE artworks SET status = ?3, updated_at = ?2 WHERE id = ?1 AND status = 'removed'
        AND creator_id = ?4 AND (SELECT action FROM moderation_events WHERE artwork_id = ?1 ORDER BY created_at DESC, rowid DESC LIMIT 1) = 'owner_removed'`)
        .bind(duplicate.id, now, status, user.id),
      env.DB.prepare(`UPDATE artwork_revisions SET status = ?2 WHERE artwork_id = ?1 AND revision = 1
        AND EXISTS(SELECT 1 FROM artworks WHERE id = ?1 AND status = ?2 AND updated_at = ?3)`).bind(duplicate.id, status, now),
      env.DB.prepare('DELETE FROM artwork_search WHERE artwork_id = ?1').bind(duplicate.id),
      env.DB.prepare(`INSERT INTO artwork_search(artwork_id, title, description, creator, tags)
        SELECT id, title, description, ?2, tags_json FROM artworks WHERE id = ?1 AND status = 'published'`).bind(duplicate.id, user.username),
      env.DB.prepare(`INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
        SELECT ?1, ?2, ?3, 'owner_restored', 'Restored original livery files and metadata.', ?4
        WHERE EXISTS(SELECT 1 FROM artworks WHERE id = ?2 AND status = ?5 AND updated_at = ?4)`)
        .bind(crypto.randomUUID(), duplicate.id, user.username, now, status),
    ]);
    if (restored[0]?.meta.changes !== 1) throw new HttpError(409, 'restore_conflict');
    return jsonResponse({ artwork: { id: duplicate.id, kind: 'livery' }, restored: true, original_details_retained: true }, 201);
  }
  const id = crypto.randomUUID(), now = new Date().toISOString();
  const prefix = `artworks/${id}/r1/`;
  const keys = [prefix + 'design.kfpslivery', prefix + 'preview.png', prefix + 'thumbnail.png'];
  const photoHashes = await Promise.all(photos.map(photo => sha256Hex(photo)));
  const previewHash = await sha256Hex(preview);
  const thumbHash = await sha256Hex(thumbnail);
  if (await env.DB.prepare('SELECT artwork_id FROM artwork_revisions WHERE preview_hash = ?1 LIMIT 1').bind(previewHash).first()) {
    throw new HttpError(409, 'duplicate_preview', 'This livery cover is already used by another upload. Check your existing uploads.');
  }
  try {
    for (const [key, data, type] of [[keys[0]!, bytes, 'application/octet-stream'], [keys[1]!, preview, 'image/png'], [keys[2]!, thumbnail, 'image/png']] as const) {
      await env.ASSETS.put(key, data, { httpMetadata: { contentType: type, cacheControl: 'private, no-store' } });
    }
    const statements = [env.DB.prepare(`INSERT INTO artworks(id, creator_id, title, description, category, classification,
      supporter_only, tags_json, games_json, license, source_schema, schema_known, kind, car, shape_count, group_count,
      status, content_hash, preview_hash, thumbnail_hash, created_at, updated_at, published_at, starts_at, ends_at, photo_count)
      VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, '["FH6"]', ?9, 'kfps-full-livery', 1, 'livery', ?10, ?11, 0,
      ?12, ?13, ?14, ?15, ?16, ?16, ?17, ?18, ?19, ?20)`)
      .bind(id, user.id, upload.title, upload.description, upload.category, upload.classification,
        Number(upload.supporterOnly), JSON.stringify(upload.tags), upload.license, livery.car, livery.shapes,
        status, hash, previewHash, thumbHash, now, published ? now : null, upload.startsAt, upload.endsAt, photos.length),
      env.DB.prepare(`INSERT INTO artwork_revisions(artwork_id, revision, content_hash, preview_hash, thumbnail_hash,
        design_key, preview_key, thumbnail_key, design_bytes, preview_bytes, thumbnail_bytes, shape_count, manifest_json, status, created_at)
        VALUES (?1, 1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)`)
        .bind(id, hash, previewHash, thumbHash, keys[0], keys[1], keys[2], bytes.length, preview.length,
          thumbnail.length, livery.shapes, JSON.stringify({ kind: 'livery', ...upload, ...livery }), status, now),
      env.DB.prepare(`INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
        VALUES (?1, ?2, ?3, ?4, 'Livery package integrity and images validated.', ?5)`)
        .bind(crypto.randomUUID(), id, user.username, published ? 'validated_auto_publish' : 'submitted', now),
    ];
    for (let index = 0; index < photos.length; index++) {
      const key = prefix + `photo${index}.png`; keys.push(key);
      await env.ASSETS.put(key, photos[index]!, { httpMetadata: { contentType: 'image/png', cacheControl: 'private, no-store' } });
      statements.push(env.DB.prepare('INSERT INTO artwork_photos(artwork_id, position, object_key, sha256) VALUES (?1, ?2, ?3, ?4)')
        .bind(id, index, key, photoHashes[index]));
    }
    if (published) statements.push(env.DB.prepare('INSERT INTO artwork_search(artwork_id, title, description, creator, tags) VALUES (?1, ?2, ?3, ?4, ?5)')
      .bind(id, upload.title, upload.description, user.username, upload.tags.join(' ')));
    await env.DB.batch(statements);
  } catch (error) {
    await env.ASSETS.delete(keys);
    throw error;
  }
  return jsonResponse({ artwork: { id, kind: 'livery', title: upload.title }, moderation_required: !published }, 201);
}
