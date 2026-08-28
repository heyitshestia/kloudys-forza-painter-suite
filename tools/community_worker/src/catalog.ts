import {
  enforceRateLimit,
  HttpError,
  jsonResponse,
  optionalUser,
  plainText,
  readJsonObject,
  requireUser,
  sha256Hex,
} from "./security";
import type { ArtworkClassification, Env, SessionUser, ValidatedUpload } from "./types";
import { CATEGORIES, GAMES, validateClassification, validateTags, validateUpload } from "./validation";
import { compareKfpsVersions, effectiveMinimumUploadVersion, getVersionPolicy, maybeSyncVersionPolicy } from "./version_policy";
import { hasActiveSupporter, requireActiveSupporter } from "./supporter";

const MAX_UPLOAD_BODY = 34 * 1024 * 1024;
export const NEW_ARTWORK_UPLOAD_LIMIT = 50;
export const NEW_ARTWORK_UPLOAD_WINDOW_SECONDS = 30 * 60;
export const FEATURED_ARTWORK_LIMIT = 8;
const SORTS = new Set(["featured", "trending", "new", "downloads", "favorites", "name"]);
const SCOPES = new Set(["featured", "browse", "supporters", "mine", "favorites", "following"]);
const SCHEMA_LABELS: Record<string, string> = {
  "legacy-kfps": "Legacy KFPS-compatible JSON",
  "kfps-community": "KFPS Community JSON",
  "kfps-primitives": "KFPS primitive geometry",
  "forza-typecode-export": "Forza live type-code export",
  "forza-save-library": "KFPS Forza save-library export",
  "forza-file-export": "KFPS decoded Forza file export",
  "kfps-cgroup-flat": "KFPS flat C_group JSON",
  "fd6-converted": "Forza Designer 6 conversion",
  "fh6-typecode": "FH6 type-code geometry",
  "forza-typecode": "Forza type-code geometry",
  "unrecognized": "Unrecognized compatible JSON",
};

function parseList(value: unknown): string[] {
  if (typeof value !== "string") return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function integerValue(value: unknown): number {
  const number = Number(value || 0);
  return Number.isFinite(number) ? Math.trunc(number) : 0;
}

function shouldPublishValidatedUpload(env: Env, user: SessionUser): boolean {
  if (env.AUTO_PUBLISH_VALIDATED_UPLOADS === "1") return true;
  return env.ALLOW_TEST_AUTH === "1"
    && env.AUTO_APPROVE_TEST_UPLOADS === "1"
    && user.provider === "local-test";
}

function fullTextQuery(value: string): string {
  const tokens = value.match(/[\p{L}\p{N}_-]+/gu)?.slice(0, 8) || [];
  return tokens.map((token) => `"${token.replace(/"/g, '""')}"*`).join(" AND ");
}

function artworkJson(row: Record<string, unknown>, user: SessionUser | null = null): Record<string, unknown> {
  const id = String(row.id);
  const sourceSchema = String(row.source_schema || "legacy-kfps");
  const schemaKnown = Boolean(row.schema_known);
  return {
    id,
    title: String(row.title || "Untitled"),
    description: String(row.description || ""),
    category: String(row.category || "Other"),
    classification: String(row.classification || "toolmade"),
    supporter_only: Boolean(row.supporter_only),
    tags: parseList(row.tags_json),
    games: parseList(row.games_json),
    license: String(row.license || "kfps-community-share-v1"),
    schema_version: integerValue(row.schema_version),
    shape_count: integerValue(row.shape_count),
    group_count: integerValue(row.group_count),
    uses_masks: Boolean(row.uses_masks),
    source_schema: sourceSchema,
    schema_label: SCHEMA_LABELS[sourceSchema] || "KFPS-compatible JSON",
    schema_known: schemaKnown,
    schema_warning: schemaKnown
      ? ""
      : "This upload uses an unrecognized source schema. It passed structural checks, but import compatibility may vary.",
    status: String(row.status || "published"),
    rejection_reason: user && user.id === String(row.creator_id) ? String(row.rejection_reason || "") : "",
    featured: Boolean(row.featured),
    current_revision: integerValue(row.current_revision),
    content_sha256: String(row.content_hash || ""),
    preview_sha256: String(row.preview_hash || ""),
    thumbnail_sha256: String(row.thumbnail_hash || row.preview_hash || ""),
    downloads: integerValue(row.download_count),
    favorites: integerValue(row.favorite_count),
    favorited: Boolean(row.is_favorite),
    created_at: String(row.created_at || ""),
    updated_at: String(row.updated_at || ""),
    published_at: String(row.published_at || ""),
    preview_url: `/v1/artworks/${encodeURIComponent(id)}/preview`,
    thumbnail_url: `/v1/artworks/${encodeURIComponent(id)}/thumbnail`,
    download_url: `/v1/artworks/${encodeURIComponent(id)}/download`,
    creator: {
      username: String(row.username || "Unknown"),
      avatar_url: String(row.avatar_url || ""),
      bio: String(row.creator_bio || ""),
      follower_count: integerValue(row.creator_followers),
      followed: Boolean(row.is_followed),
    },
  };
}

const ARTWORK_COLUMNS = `
  a.id, a.creator_id, a.title, a.description, a.category, a.classification, a.supporter_only, a.tags_json, a.games_json,
  a.license, a.schema_version, a.shape_count, a.group_count, a.uses_masks, a.source_schema, a.schema_known,
  a.status, a.rejection_reason,
  a.featured, a.current_revision, a.content_hash, a.preview_hash, a.thumbnail_hash,
  a.download_count, a.favorite_count, a.created_at,
  a.updated_at, a.published_at, u.username, u.avatar_url, u.bio AS creator_bio,
  (SELECT COUNT(*) FROM follows ff WHERE ff.creator_id = u.id) AS creator_followers`;

async function visibleArtwork(
  env: Env,
  id: string,
  user: SessionUser | null,
  allowFeaturedSupporterThumbnail = false,
): Promise<Record<string, unknown>> {
  const row = await env.DB.prepare(
    `SELECT ${ARTWORK_COLUMNS},
       EXISTS(SELECT 1 FROM favorites f WHERE f.artwork_id = a.id AND f.user_id = ?2) AS is_favorite,
       EXISTS(SELECT 1 FROM follows fw WHERE fw.creator_id = u.id AND fw.follower_id = ?2) AS is_followed
     FROM artworks a JOIN users u ON u.id = a.creator_id
     WHERE a.id = ?1 AND (a.status = 'published' OR a.creator_id = ?2) LIMIT 1`,
  ).bind(id, user?.id || "").first<Record<string, unknown>>();
  if (!row) throw new HttpError(404, "artwork_not_found");
  const publicFeaturedThumbnail = allowFeaturedSupporterThumbnail
    && Boolean(row.featured)
    && String(row.status) === "published";
  if (Boolean(row.supporter_only) && !hasActiveSupporter(user) && !publicFeaturedThumbnail) {
    throw new HttpError(404, "artwork_not_found");
  }
  return row;
}

export async function handleListArtworks(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const user = await optionalUser(request, env);
  const search = (url.searchParams.get("search") || "").trim().slice(0, 100).toLocaleLowerCase("en-US");
  const category = url.searchParams.get("category") || "All";
  const game = url.searchParams.get("game") || "All";
  const creator = (url.searchParams.get("creator") || "").trim().toLocaleLowerCase("en-US");
  const classificationValue = url.searchParams.get("classification");
  const classification = classificationValue == null || classificationValue === ""
    ? ""
    : validateClassification(classificationValue);
  const requestedSort = SORTS.has(url.searchParams.get("sort") || "") ? String(url.searchParams.get("sort")) : "featured";
  const scope = SCOPES.has(url.searchParams.get("scope") || "") ? String(url.searchParams.get("scope")) : "browse";
  const sort = scope === "featured" ? "featured" : requestedSort;
  const page = scope === "featured"
    ? 1
    : Math.max(1, Math.min(10000, Number.parseInt(url.searchParams.get("page") || "1", 10) || 1));
  const requestedLimit = Math.max(1, Math.min(60, Number.parseInt(url.searchParams.get("limit") || "24", 10) || 24));
  const limit = scope === "featured" ? FEATURED_ARTWORK_LIMIT : requestedLimit;
  if ((scope === "supporters" || scope === "mine" || scope === "favorites" || scope === "following") && !user) {
    throw new HttpError(401, "authentication_required");
  }
  const supporterActive = hasActiveSupporter(user);
  if (scope === "supporters") requireActiveSupporter(user);

  const conditions: string[] = [];
  const parameters: unknown[] = [];
  const bind = (value: unknown): string => {
    parameters.push(value);
    return `?${parameters.length}`;
  };

  if (scope === "mine") {
    conditions.push(`a.creator_id = ${bind(user?.id || "")}`);
    conditions.push("a.status <> 'removed'");
  } else {
    conditions.push("a.status = 'published'");
  }
  if (scope === "featured") {
    conditions.push("a.featured = 1");
  } else if (scope === "browse" || scope === "supporters" || scope === "following") {
    conditions.push("a.featured = 0");
  }
  if (scope === "favorites") {
    conditions.push(`EXISTS(SELECT 1 FROM favorites sf WHERE sf.artwork_id = a.id AND sf.user_id = ${bind(user?.id || "")})`);
  }
  if (scope === "following") {
    conditions.push(`EXISTS(SELECT 1 FROM follows sw WHERE sw.creator_id = a.creator_id AND sw.follower_id = ${bind(user?.id || "")})`);
  }
  if (scope === "featured") {
    // Curated metadata and compact thumbnails are visible to everyone. Full
    // supporter previews and JSON downloads remain protected by asset routes.
  } else if (scope === "supporters") {
    conditions.push("a.supporter_only = 1");
  } else if (scope === "browse" || !supporterActive) {
    conditions.push("a.supporter_only = 0");
  }
  if (search && scope !== "featured") {
    const fts = scope === "mine" ? "" : fullTextQuery(search);
    if (fts) {
      conditions.push(`a.id IN (SELECT artwork_id FROM artwork_search WHERE artwork_search MATCH ${bind(fts)})`);
    } else {
      const pattern = `%${search.replace(/[\\%_]/g, "\\$&")}%`;
      const token = bind(pattern);
      conditions.push(`(lower(a.title) LIKE ${token} ESCAPE '\\' OR lower(a.description) LIKE ${token} ESCAPE '\\' OR lower(a.tags_json) LIKE ${token} ESCAPE '\\' OR lower(u.username) LIKE ${token} ESCAPE '\\')`);
    }
  }
  if (category !== "All" && scope !== "featured") {
    if (!(CATEGORIES as readonly string[]).includes(category)) throw new HttpError(400, "invalid_category");
    conditions.push(`a.category = ${bind(category)}`);
  }
  if (game !== "All" && scope !== "featured") {
    if (!(GAMES as readonly string[]).includes(game)) throw new HttpError(400, "invalid_game");
    conditions.push(`EXISTS(SELECT 1 FROM json_each(a.games_json) WHERE value = ${bind(game)})`);
  }
  if (classification && scope !== "featured") conditions.push(`a.classification = ${bind(classification)}`);
  if (creator && scope !== "featured") conditions.push(`u.username_norm = ${bind(creator)}`);

  const orderBy: Record<string, string> = {
    featured: "a.featured DESC, a.published_at DESC, a.id DESC",
    trending: "((a.download_count + a.favorite_count * 4.0 + a.featured * 20.0) / MAX(2.0, julianday('now') - julianday(a.published_at) + 2.0)) DESC, a.published_at DESC",
    new: "a.published_at DESC, a.id DESC",
    downloads: "a.download_count DESC, a.favorite_count DESC, a.published_at DESC",
    favorites: "a.favorite_count DESC, a.download_count DESC, a.published_at DESC",
    name: "lower(a.title) ASC, a.id ASC",
  };
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const userToken = bind(user?.id || "");
  const limitToken = bind(limit);
  const offsetToken = bind((page - 1) * limit);
  const query = `
    SELECT ${ARTWORK_COLUMNS},
      EXISTS(SELECT 1 FROM favorites f WHERE f.artwork_id = a.id AND f.user_id = ${userToken}) AS is_favorite,
      EXISTS(SELECT 1 FROM follows fw WHERE fw.creator_id = u.id AND fw.follower_id = ${userToken}) AS is_followed
    FROM artworks a JOIN users u ON u.id = a.creator_id
    ${where}
    ORDER BY ${orderBy[sort]}
    LIMIT ${limitToken} OFFSET ${offsetToken}`;
  const result = await env.DB.prepare(query).bind(...parameters).all<Record<string, unknown>>();

  const countParameters = parameters.slice(0, parameters.length - 3);
  const count = await env.DB.prepare(
    `SELECT COUNT(*) AS total FROM artworks a JOIN users u ON u.id = a.creator_id ${where}`,
  ).bind(...countParameters).first<{ total: number }>();
  const total = integerValue(count?.total);
  return jsonResponse({
    items: (result.results || []).map((row) => artworkJson(row, user)),
    page,
    page_size: limit,
    total,
    page_count: Math.max(1, Math.ceil(total / limit)),
    sort,
    scope,
    classification: scope === "featured" ? "all" : classification || "all",
  }, 200, { "Cache-Control": user ? "private, no-store" : "public, max-age=30" });
}

export async function handleArtworkDetail(request: Request, env: Env, id: string): Promise<Response> {
  const user = await optionalUser(request, env);
  const row = await visibleArtwork(env, id, user);
  const revisions = await env.DB.prepare(
    `SELECT revision, shape_count, change_note, created_at, status
       FROM artwork_revisions
      WHERE artwork_id = ?1
        AND (status = 'published' OR ?2 = (SELECT creator_id FROM artworks WHERE id = ?1))
      ORDER BY revision DESC`,
  ).bind(id, user?.id || "").all<Record<string, unknown>>().catch(() => ({ results: [] as Record<string, unknown>[] }));
  return jsonResponse({ artwork: artworkJson(row, user), revisions: revisions.results || [] });
}

export async function handleUpdateArtworkMetadata(request: Request, env: Env, id: string): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "artwork_metadata", 30, 3600);
  const current = await env.DB.prepare(
    `SELECT a.creator_id, a.status, a.current_revision, a.title, a.description,
            r.manifest_json
       FROM artworks a
       JOIN artwork_revisions r
         ON r.artwork_id = a.id AND r.revision = a.current_revision
      WHERE a.id = ?1 AND a.status <> 'removed' LIMIT 1`,
  ).bind(id).first<Record<string, unknown>>();
  if (!current) throw new HttpError(404, "artwork_not_found");
  if (String(current.creator_id) !== user.id) throw new HttpError(403, "not_artwork_owner");

  const value = await readJsonObject(request, 8192);
  const allowed = new Set(["tags"]);
  if (Object.keys(value).some((key) => !allowed.has(key))
      || !Object.prototype.hasOwnProperty.call(value, "tags")) {
    throw new HttpError(400, "invalid_metadata", "Only tags can be changed here.");
  }
  const selectedTags = validateTags(value.tags);
  const manifest = parseManifest(current.manifest_json);
  manifest.tags = selectedTags;
  const now = new Date().toISOString();

  await env.DB.batch([
    env.DB.prepare(
      `UPDATE artworks SET tags_json = ?3, updated_at = ?4
        WHERE id = ?1 AND creator_id = ?2 AND status <> 'removed'`,
    ).bind(id, user.id, JSON.stringify(selectedTags), now),
    env.DB.prepare(
      `UPDATE artwork_revisions SET manifest_json = ?3
        WHERE artwork_id = ?1 AND revision = ?2
          AND EXISTS(SELECT 1 FROM artworks a
                      WHERE a.id = ?1 AND a.creator_id = ?4 AND a.status <> 'removed')`,
    ).bind(id, integerValue(current.current_revision), JSON.stringify(manifest), user.id),
    env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(id),
    env.DB.prepare(
      `INSERT INTO artwork_search(artwork_id, title, description, creator, tags)
       SELECT a.id, a.title, a.description, u.username, ?3
         FROM artworks a JOIN users u ON u.id = a.creator_id
        WHERE a.id = ?1 AND a.creator_id = ?2 AND a.status = 'published'`,
    ).bind(id, user.id, selectedTags.join(" ")),
    env.DB.prepare(
      `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
       VALUES (?1, ?2, ?3, 'owner_metadata_updated', ?4, ?5)`,
    ).bind(crypto.randomUUID(), id, user.username, JSON.stringify({ tags: selectedTags }), now),
  ]);

  const row = await visibleArtwork(env, id, user);
  return jsonResponse({ artwork: artworkJson(row, user) });
}

async function duplicateCheck(
  env: Env,
  upload: ValidatedUpload,
  excludeArtwork = "",
  ignoreArtwork = "",
): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT a.id, r.content_hash, r.preview_hash
       FROM artwork_revisions r JOIN artworks a ON a.id = r.artwork_id
      WHERE (r.content_hash = ?1 OR r.preview_hash = ?2)
        AND (?3 = '' OR a.id <> ?3)
      ORDER BY r.created_at DESC LIMIT 1`,
  ).bind(upload.contentHash, upload.previewHash, ignoreArtwork).first<Record<string, unknown>>();
  if (!row) return;
  if (excludeArtwork && row.id === excludeArtwork) {
    throw new HttpError(409, "duplicate_revision", "This revision is identical to the current artwork.");
  }
  const code = row.content_hash === upload.contentHash ? "duplicate_artwork" : "duplicate_preview";
  throw new HttpError(409, code, code === "duplicate_artwork"
    ? "This exact design is already in the community library."
    : "This preview is already attached to another community upload.");
}

interface OwnerRemovedArtwork {
  id: string;
  current_revision: number;
  classification: ArtworkClassification;
  supporter_only: number;
  preview_key: string;
  thumbnail_key: string;
}

async function ownerRemovedArtwork(
  env: Env,
  creatorId: string,
  contentHash: string,
): Promise<OwnerRemovedArtwork | null> {
  return env.DB.prepare(
    `SELECT a.id, a.current_revision, a.classification, a.supporter_only, r.preview_key, r.thumbnail_key
       FROM artworks a
       JOIN artwork_revisions r
         ON r.artwork_id = a.id AND r.revision = a.current_revision
      WHERE a.creator_id = ?1
        AND a.status = 'removed'
        AND a.content_hash = ?2
        AND r.content_hash = ?2
        AND (SELECT me.action FROM moderation_events me
              WHERE me.artwork_id = a.id
              ORDER BY me.created_at DESC, me.rowid DESC LIMIT 1) = 'owner_removed'
      ORDER BY a.updated_at DESC LIMIT 1`,
  ).bind(creatorId, contentHash).first<OwnerRemovedArtwork>();
}

function revisionManifest(
  upload: ValidatedUpload,
  classification: ArtworkClassification = upload.classification,
  supporterOnly: boolean = upload.supporterOnly,
): string {
  return JSON.stringify({
    client_version: upload.clientVersion,
    title: upload.title,
    description: upload.description,
    category: upload.category,
    classification,
    supporter_only: supporterOnly,
    tags: upload.tags,
    games: upload.games,
    source_schema: upload.sourceSchema,
    schema_label: upload.schemaLabel,
    schema_known: upload.schemaKnown,
    license: upload.license,
    shape_count: upload.shapeCount,
    group_count: upload.groupCount,
    uses_masks: upload.usesMasks,
  });
}

function parseManifest(value: unknown): Record<string, unknown> {
  try {
    const parsed = JSON.parse(String(value || "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

async function writeRevisionAssets(
  env: Env,
  id: string,
  revision: number,
  upload: ValidatedUpload,
): Promise<{ designKey: string; previewKey: string; thumbnailKey: string }> {
  const assetVersion = crypto.randomUUID();
  const designKey = `artworks/${id}/r${revision}/${assetVersion}/design.json`;
  const previewKey = `artworks/${id}/r${revision}/${assetVersion}/preview.png`;
  const thumbnailKey = `artworks/${id}/r${revision}/${assetVersion}/thumbnail.png`;
  await env.ASSETS.put(designKey, upload.designBytes, {
    httpMetadata: { contentType: "application/json; charset=utf-8", cacheControl: "private, no-store" },
    customMetadata: { sha256: upload.contentHash, artworkId: id, revision: String(revision) },
  });
  try {
    await env.ASSETS.put(previewKey, upload.previewBytes, {
      httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
      customMetadata: { sha256: upload.previewHash, artworkId: id, revision: String(revision) },
    });
    await env.ASSETS.put(thumbnailKey, upload.thumbnailBytes, {
      httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
      customMetadata: { sha256: upload.thumbnailHash, artworkId: id, revision: String(revision) },
    });
  } catch (error) {
    await Promise.all([env.ASSETS.delete(designKey), env.ASSETS.delete(previewKey), env.ASSETS.delete(thumbnailKey)]);
    throw error;
  }
  return { designKey, previewKey, thumbnailKey };
}

async function writeRestoredPreviewAssets(
  env: Env,
  id: string,
  revision: number,
  upload: ValidatedUpload,
): Promise<{ previewKey: string; thumbnailKey: string }> {
  const assetVersion = crypto.randomUUID();
  const previewKey = `artworks/${id}/r${revision}/${assetVersion}/preview.png`;
  const thumbnailKey = `artworks/${id}/r${revision}/${assetVersion}/thumbnail.png`;
  await env.ASSETS.put(previewKey, upload.previewBytes, {
    httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
    customMetadata: { sha256: upload.previewHash, artworkId: id, revision: String(revision) },
  });
  try {
    await env.ASSETS.put(thumbnailKey, upload.thumbnailBytes, {
      httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
      customMetadata: { sha256: upload.thumbnailHash, artworkId: id, revision: String(revision) },
    });
  } catch (error) {
    await Promise.all([env.ASSETS.delete(previewKey), env.ASSETS.delete(thumbnailKey)]);
    throw error;
  }
  return { previewKey, thumbnailKey };
}

async function restoreOwnerRemovedArtwork(
  env: Env,
  user: SessionUser,
  upload: ValidatedUpload,
  removed: OwnerRemovedArtwork,
  autoPublish: boolean,
): Promise<Response> {
  await duplicateCheck(env, upload, "", removed.id);
  const id = removed.id;
  const revision = integerValue(removed.current_revision);
  const now = new Date().toISOString();
  const status = autoPublish ? "published" : "pending";
  if (upload.classification !== removed.classification) {
    throw new HttpError(409, "classification_immutable", "This upload was already classified and can only be reclassified by an administrator.");
  }
  const supporterOnly = upload.supporterOnly;
  if (supporterOnly) requireActiveSupporter(user);
  const classification = removed.classification;
  const assets = await writeRestoredPreviewAssets(env, id, revision, upload);
  try {
    const statements = [
      env.DB.prepare(
        `UPDATE artwork_revisions
            SET preview_hash = ?3, thumbnail_hash = ?4,
                preview_key = ?5, thumbnail_key = ?6,
                preview_bytes = ?7, thumbnail_bytes = ?8,
                manifest_json = ?9, uses_masks = ?14, status = ?10, rejection_reason = '',
                change_note = 'Restored by the owner with regenerated preview assets.'
          WHERE artwork_id = ?1 AND revision = ?2
            AND status = 'removed' AND preview_key = ?11 AND content_hash = ?12
            AND EXISTS(
              SELECT 1 FROM artworks a
               WHERE a.id = ?1 AND a.creator_id = ?13 AND a.status = 'removed'
                 AND (SELECT me.action FROM moderation_events me
                       WHERE me.artwork_id = a.id
                       ORDER BY me.created_at DESC, me.rowid DESC LIMIT 1) = 'owner_removed'
            )`,
      ).bind(
        id, revision, upload.previewHash, upload.thumbnailHash,
        assets.previewKey, assets.thumbnailKey, upload.previewBytes.length, upload.thumbnailBytes.length,
        revisionManifest(upload, classification, supporterOnly), status, removed.preview_key, upload.contentHash, user.id,
        upload.usesMasks ? 1 : 0,
      ),
      env.DB.prepare(
        `UPDATE artworks
            SET status = ?6, rejection_reason = '', featured = 0, current_revision = ?4,
                title = ?7, description = ?8, category = ?9,
                tags_json = ?10, games_json = ?11, source_schema = ?12, schema_known = ?13,
                license = ?14, shape_count = ?15, group_count = ?16, uses_masks = ?21,
                 content_hash = ?3, preview_hash = ?17, thumbnail_hash = ?18,
                updated_at = ?19, classification = ?20, supporter_only = ?22,
                published_at = CASE WHEN ?6 = 'published' THEN COALESCE(published_at, ?19) ELSE published_at END
          WHERE id = ?1 AND creator_id = ?2 AND status = 'removed' AND content_hash = ?3
            AND EXISTS(
              SELECT 1 FROM artwork_revisions r
               WHERE r.artwork_id = ?1 AND r.revision = ?4 AND r.preview_key = ?5 AND r.status = ?6
            )
            AND (SELECT me.action FROM moderation_events me
                  WHERE me.artwork_id = ?1
                  ORDER BY me.created_at DESC, me.rowid DESC LIMIT 1) = 'owner_removed'`,
      ).bind(
        id, user.id, upload.contentHash, revision, assets.previewKey, status,
        upload.title, upload.description, upload.category, JSON.stringify(upload.tags),
        JSON.stringify(upload.games), upload.sourceSchema, upload.schemaKnown ? 1 : 0,
        upload.license, upload.shapeCount, upload.groupCount,
         upload.previewHash, upload.thumbnailHash, now,
        classification, upload.usesMasks ? 1 : 0, supporterOnly ? 1 : 0,
       ),
    ];
    if (autoPublish) {
      statements.push(
        env.DB.prepare(
          `DELETE FROM artwork_search WHERE artwork_id = ?1
            AND EXISTS(SELECT 1 FROM artwork_revisions r
                        WHERE r.artwork_id = ?1 AND r.revision = ?2 AND r.preview_key = ?3)`,
        ).bind(id, revision, assets.previewKey),
        env.DB.prepare(
          `INSERT INTO artwork_search(artwork_id, title, description, creator, tags)
           SELECT ?1, ?2, ?3, u.username, ?4
             FROM artworks a JOIN users u ON u.id = a.creator_id
            WHERE a.id = ?1 AND a.status = 'published'
              AND EXISTS(SELECT 1 FROM artwork_revisions r
                          WHERE r.artwork_id = ?1 AND r.revision = ?5 AND r.preview_key = ?6)`,
        ).bind(id, upload.title, upload.description, upload.tags.join(" "), revision, assets.previewKey),
      );
    }
    statements.push(env.DB.prepare(
      `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
       SELECT ?1, ?2, ?3, 'owner_restored', 'Revalidated with regenerated preview assets and owner-selected audience.', ?4
        WHERE EXISTS(SELECT 1 FROM artwork_revisions r
                      WHERE r.artwork_id = ?2 AND r.revision = ?5 AND r.preview_key = ?6)`,
    ).bind(crypto.randomUUID(), id, user.username, now, revision, assets.previewKey));
    const results = await env.DB.batch(statements);
    if ((results[0]?.meta.changes || 0) !== 1 || (results[1]?.meta.changes || 0) !== 1) {
      throw new HttpError(409, "restore_conflict", "This artwork was already restored. Refresh the library and try again.");
    }
  } catch (error) {
    await Promise.all([env.ASSETS.delete(assets.previewKey), env.ASSETS.delete(assets.thumbnailKey)]);
    await duplicateCheck(env, upload, "", id);
    throw error;
  }
  await Promise.all([
    env.ASSETS.delete(removed.preview_key).catch(() => undefined),
    env.ASSETS.delete(removed.thumbnail_key).catch(() => undefined),
  ]);
  const row = await visibleArtwork(env, id, user);
  return jsonResponse({ artwork: artworkJson(row, user), moderation_required: !autoPublish, restored: true }, 201);
}

export async function handleCreateArtwork(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(
    env,
    user.id,
    "upload",
    NEW_ARTWORK_UPLOAD_LIMIT,
    NEW_ARTWORK_UPLOAD_WINDOW_SECONDS,
  );
  const versionPolicy = await getVersionPolicy(env);
  const upload = await validateUpload(
    await readJsonObject(request, MAX_UPLOAD_BODY),
    effectiveMinimumUploadVersion(env, versionPolicy),
    env.REQUIRE_MODERN_UPLOAD_CLIENT !== "0",
  );
  if (upload.clientVersion !== "legacy"
      && compareKfpsVersions(upload.clientVersion, versionPolicy.minimumVersion) > 0) {
    ctx.waitUntil(maybeSyncVersionPolicy(env).catch((error) => {
      console.error("Upload-triggered KFPS VERSION synchronization failed", error);
    }));
  }
  if (upload.supporterOnly) requireActiveSupporter(user);
  const autoPublish = shouldPublishValidatedUpload(env, user);
  const removed = await ownerRemovedArtwork(env, user.id, upload.contentHash);
  if (removed) return restoreOwnerRemovedArtwork(env, user, upload, removed, autoPublish);
  await duplicateCheck(env, upload);
  const id = crypto.randomUUID();
  const revision = 1;
  const now = new Date().toISOString();
  const status = autoPublish ? "published" : "pending";
  const assets = await writeRevisionAssets(env, id, revision, upload);
  try {
    const statements = [
      env.DB.prepare(
        `INSERT INTO artworks(
          id, creator_id, title, description, category, classification, supporter_only, tags_json, games_json,
          source_schema, schema_known, license, shape_count, group_count, status,
          content_hash, preview_hash, thumbnail_hash,
          created_at, updated_at, published_at, uses_masks
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?19, ?20, ?21)`,
      ).bind(
        id, user.id, upload.title, upload.description, upload.category, upload.classification,
        upload.supporterOnly ? 1 : 0, JSON.stringify(upload.tags),
        JSON.stringify(upload.games), upload.sourceSchema, upload.schemaKnown ? 1 : 0,
        upload.license, upload.shapeCount, upload.groupCount, status,
        upload.contentHash, upload.previewHash, upload.thumbnailHash, now, autoPublish ? now : null,
        upload.usesMasks ? 1 : 0,
      ),
      env.DB.prepare(
        `INSERT INTO artwork_revisions(
          artwork_id, revision, content_hash, preview_hash, thumbnail_hash,
          design_key, preview_key, thumbnail_key, design_bytes, preview_bytes, thumbnail_bytes,
          shape_count, manifest_json, status, created_at, uses_masks
        ) VALUES (?1, 1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)`,
      ).bind(id, upload.contentHash, upload.previewHash, upload.thumbnailHash,
        assets.designKey, assets.previewKey, assets.thumbnailKey,
        upload.designBytes.length, upload.previewBytes.length, upload.thumbnailBytes.length,
        upload.shapeCount, revisionManifest(upload), status, now, upload.usesMasks ? 1 : 0),
      env.DB.prepare(
        "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
      ).bind(crypto.randomUUID(), id, user.username, autoPublish ? "validated_auto_publish" : "submitted", "", now),
    ];
    if (autoPublish) {
      statements.push(env.DB.prepare(
        "INSERT INTO artwork_search(artwork_id, title, description, creator, tags) VALUES (?1, ?2, ?3, ?4, ?5)",
      ).bind(id, upload.title, upload.description, user.username, upload.tags.join(" ")));
    }
    await env.DB.batch(statements);
  } catch (error) {
    await Promise.all([
      env.ASSETS.delete(assets.designKey), env.ASSETS.delete(assets.previewKey), env.ASSETS.delete(assets.thumbnailKey),
    ]);
    await duplicateCheck(env, upload);
    throw error;
  }
  const row = await visibleArtwork(env, id, user);
  return jsonResponse({ artwork: artworkJson(row, user), moderation_required: !autoPublish }, 201);
}

export async function handleCreateRevision(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  id: string,
): Promise<Response> {
  const user = await requireUser(request, env);
  const current = await env.DB.prepare(
    "SELECT creator_id, current_revision, status, classification, supporter_only FROM artworks WHERE id = ?1 AND status <> 'removed' LIMIT 1",
  ).bind(id).first<{
    creator_id: string;
    current_revision: number;
    status: string;
    classification: ArtworkClassification;
    supporter_only: number;
  }>();
  if (!current) throw new HttpError(404, "artwork_not_found");
  if (current.creator_id !== user.id) throw new HttpError(403, "not_artwork_owner");
  await enforceRateLimit(env, user.id, "revision", 8, 3600);
  const value = await readJsonObject(request, MAX_UPLOAD_BODY);
  const changeNote = plainText(value.change_note, "change_note", 240, true);
  const versionPolicy = await getVersionPolicy(env);
  const upload = await validateUpload(
    value,
    effectiveMinimumUploadVersion(env, versionPolicy),
    env.REQUIRE_MODERN_UPLOAD_CLIENT !== "0",
  );
  if (upload.clientVersion !== "legacy"
      && compareKfpsVersions(upload.clientVersion, versionPolicy.minimumVersion) > 0) {
    ctx.waitUntil(maybeSyncVersionPolicy(env).catch((error) => {
      console.error("Revision-triggered KFPS VERSION synchronization failed", error);
    }));
  }
  if (upload.classification !== current.classification) {
    throw new HttpError(409, "classification_immutable", "Classification cannot be changed in a revision.");
  }
  const supporterOnly = Boolean(current.supporter_only);
  if (upload.supporterOnly !== supporterOnly) {
    throw new HttpError(409, "supporter_visibility_immutable", "Supporter-only visibility cannot be changed in a revision.");
  }
  if (supporterOnly) requireActiveSupporter(user);
  const classification = current.classification;
  await duplicateCheck(env, upload, id);
  const latest = await env.DB.prepare(
    "SELECT MAX(revision) AS revision FROM artwork_revisions WHERE artwork_id = ?1",
  ).bind(id).first<{ revision: number }>();
  const revision = integerValue(latest?.revision) + 1;
  const now = new Date().toISOString();
  const autoPublish = shouldPublishValidatedUpload(env, user);
  const status = autoPublish ? "published" : "pending";
  const assets = await writeRevisionAssets(env, id, revision, upload);
  try {
    const statements = [
      env.DB.prepare(
        `UPDATE artwork_revisions
            SET status = 'rejected', rejection_reason = 'Superseded by a newer submitted revision.'
          WHERE artwork_id = ?1 AND status = 'pending'`,
      ).bind(id),
      env.DB.prepare(
        `INSERT INTO artwork_revisions(
          artwork_id, revision, content_hash, preview_hash, thumbnail_hash,
          design_key, preview_key, thumbnail_key, design_bytes, preview_bytes, thumbnail_bytes,
          shape_count, manifest_json, status, change_note, created_at, uses_masks
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)`,
      ).bind(id, revision, upload.contentHash, upload.previewHash, upload.thumbnailHash,
        assets.designKey, assets.previewKey, assets.thumbnailKey,
        upload.designBytes.length, upload.previewBytes.length, upload.thumbnailBytes.length,
        upload.shapeCount, revisionManifest(upload, classification, supporterOnly), status, changeNote, now,
        upload.usesMasks ? 1 : 0),
      env.DB.prepare(
        "UPDATE artworks SET updated_at = ?2 WHERE id = ?1",
      ).bind(id, now),
      env.DB.prepare(
        "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
      ).bind(crypto.randomUUID(), id, user.username, autoPublish ? "validated_auto_publish_revision" : "submitted_revision", changeNote, now),
    ];
    if (autoPublish) {
      statements.push(env.DB.prepare(
        `UPDATE artworks SET status = 'published', rejection_reason = '', current_revision = ?2,
          title = ?3, description = ?4, category = ?5, classification = ?6,
          tags_json = ?7, games_json = ?8, source_schema = ?9, schema_known = ?10,
          license = ?11, shape_count = ?12, group_count = ?13, uses_masks = ?18,
          content_hash = ?14, preview_hash = ?15, thumbnail_hash = ?16, updated_at = ?17,
          published_at = COALESCE(published_at, ?17) WHERE id = ?1`,
      ).bind(id, revision, upload.title, upload.description, upload.category, classification, JSON.stringify(upload.tags),
        JSON.stringify(upload.games), upload.sourceSchema, upload.schemaKnown ? 1 : 0,
        upload.license, upload.shapeCount, upload.groupCount,
        upload.contentHash, upload.previewHash, upload.thumbnailHash, now, upload.usesMasks ? 1 : 0));
      statements.push(
        env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(id),
        env.DB.prepare(
          "INSERT INTO artwork_search(artwork_id, title, description, creator, tags) VALUES (?1, ?2, ?3, ?4, ?5)",
        ).bind(id, upload.title, upload.description, user.username, upload.tags.join(" ")),
      );
    }
    await env.DB.batch(statements);
  } catch (error) {
    await Promise.all([
      env.ASSETS.delete(assets.designKey), env.ASSETS.delete(assets.previewKey), env.ASSETS.delete(assets.thumbnailKey),
    ]);
    await duplicateCheck(env, upload, id);
    const newest = await env.DB.prepare(
      "SELECT MAX(revision) AS revision FROM artwork_revisions WHERE artwork_id = ?1",
    ).bind(id).first<{ revision: number }>();
    if (integerValue(newest?.revision) >= revision) {
      throw new HttpError(409, "revision_conflict", "Another revision was submitted first. Refresh and try again.");
    }
    throw error;
  }
  return jsonResponse({ artwork_id: id, revision, status }, 201);
}

async function recordDownload(env: Env, id: string, user: SessionUser): Promise<void> {
  const subjectHash = await sha256Hex(`user:${user.id}`);
  const dayBucket = Math.floor(Date.now() / 86_400_000);
  const inserted = await env.DB.prepare(
    `INSERT OR IGNORE INTO download_events(artwork_id, subject_hash, day_bucket, created_at)
     VALUES (?1, ?2, ?3, ?4)`,
  ).bind(id, subjectHash, dayBucket, new Date().toISOString()).run();
  if ((inserted.meta.changes || 0) > 0) {
    await env.DB.prepare(
      "UPDATE artworks SET download_count = download_count + 1 WHERE id = ?1 AND status = 'published'",
    ).bind(id).run();
  }
}

export async function handleArtworkAsset(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  id: string,
  kind: "preview" | "thumbnail" | "download",
): Promise<Response> {
  const user = kind === "download"
    ? await requireUser(request, env)
    : await optionalUser(request, env);
  const row = await visibleArtwork(env, id, user, kind === "thumbnail");
  const revision = integerValue(row.current_revision);
  const stored = await env.DB.prepare(
    "SELECT design_key, preview_key, thumbnail_key FROM artwork_revisions WHERE artwork_id = ?1 AND revision = ?2 LIMIT 1",
  ).bind(id, revision).first<{ design_key: string; preview_key: string; thumbnail_key: string }>();
  if (!stored) throw new HttpError(404, "asset_not_found");
  const objectKey = kind === "download"
    ? stored.design_key
    : kind === "thumbnail" && stored.thumbnail_key ? stored.thumbnail_key : stored.preview_key;
  const object = await env.ASSETS.get(objectKey);
  if (!object) throw new HttpError(404, "asset_not_found");
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("X-Content-Type-Options", "nosniff");
  if (kind !== "download") {
    headers.set(
      "Cache-Control",
      row.status === "published" && (!Boolean(row.supporter_only) || (kind === "thumbnail" && Boolean(row.featured)))
        ? "public, max-age=3600, stale-while-revalidate=86400"
        : "private, no-store",
    );
  } else {
    if (!user) throw new HttpError(401, "authentication_required");
    const safeTitle = String(row.title || "community-artwork").replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 80) || "community-artwork";
    headers.set("Content-Disposition", `attachment; filename="${safeTitle}.json"`);
    headers.set("Cache-Control", "private, no-store");
    if (row.status === "published") {
      ctx.waitUntil(recordDownload(env, id, user));
    }
  }
  return new Response(object.body, { headers });
}

export async function handleFavorite(request: Request, env: Env, id: string): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "favorite", 120, 3600);
  await visibleArtwork(env, id, user);
  const value = await readJsonObject(request, 2048);
  if (typeof value.favorite !== "boolean") throw new HttpError(400, "invalid_favorite");
  const now = new Date().toISOString();
  if (value.favorite) {
    await env.DB.prepare(
      "INSERT OR IGNORE INTO favorites(user_id, artwork_id, created_at) VALUES (?1, ?2, ?3)",
    ).bind(user.id, id, now).run();
  } else {
    await env.DB.prepare("DELETE FROM favorites WHERE user_id = ?1 AND artwork_id = ?2").bind(user.id, id).run();
  }
  await env.DB.prepare(
    "UPDATE artworks SET favorite_count = (SELECT COUNT(*) FROM favorites WHERE artwork_id = ?1) WHERE id = ?1",
  ).bind(id).run();
  const count = await env.DB.prepare("SELECT favorite_count FROM artworks WHERE id = ?1").bind(id).first<{ favorite_count: number }>();
  return jsonResponse({ favorited: value.favorite, favorites: integerValue(count?.favorite_count) });
}

export async function handleFollow(request: Request, env: Env, username: string): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "follow", 120, 3600);
  const creator = await env.DB.prepare(
    "SELECT id FROM users WHERE username_norm = ?1 AND suspended_at IS NULL LIMIT 1",
  ).bind(username.toLocaleLowerCase("en-US")).first<{ id: string }>();
  if (!creator) throw new HttpError(404, "creator_not_found");
  if (creator.id === user.id) throw new HttpError(400, "cannot_follow_self");
  const value = await readJsonObject(request, 2048);
  if (typeof value.follow !== "boolean") throw new HttpError(400, "invalid_follow");
  if (value.follow) {
    await env.DB.prepare(
      "INSERT OR IGNORE INTO follows(follower_id, creator_id, created_at) VALUES (?1, ?2, ?3)",
    ).bind(user.id, creator.id, new Date().toISOString()).run();
  } else {
    await env.DB.prepare("DELETE FROM follows WHERE follower_id = ?1 AND creator_id = ?2").bind(user.id, creator.id).run();
  }
  const count = await env.DB.prepare("SELECT COUNT(*) AS total FROM follows WHERE creator_id = ?1").bind(creator.id).first<{ total: number }>();
  return jsonResponse({ followed: value.follow, followers: integerValue(count?.total) });
}

export async function handleCreator(request: Request, env: Env, username: string): Promise<Response> {
  const viewer = await optionalUser(request, env);
  const supporterActive = hasActiveSupporter(viewer) ? 1 : 0;
  const normalized = username.toLocaleLowerCase("en-US");
  const row = await env.DB.prepare(
    `SELECT u.id, u.username, u.bio, u.website_url, u.avatar_url, u.created_at,
      (SELECT COUNT(*) FROM artworks WHERE creator_id = u.id AND status = 'published'
         AND (supporter_only = 0 OR ?3 = 1)) AS artwork_count,
      (SELECT COALESCE(SUM(download_count), 0) FROM artworks WHERE creator_id = u.id AND status = 'published'
         AND (supporter_only = 0 OR ?3 = 1)) AS downloads,
      (SELECT COUNT(*) FROM follows WHERE creator_id = u.id) AS followers,
      EXISTS(SELECT 1 FROM follows WHERE creator_id = u.id AND follower_id = ?2) AS followed
     FROM users u WHERE u.username_norm = ?1 AND u.suspended_at IS NULL LIMIT 1`,
  ).bind(normalized, viewer?.id || "", supporterActive).first<Record<string, unknown>>();
  if (!row) throw new HttpError(404, "creator_not_found");
  return jsonResponse({
    creator: {
      username: String(row.username), bio: String(row.bio || ""), website_url: String(row.website_url || ""),
      avatar_url: String(row.avatar_url || ""), joined_at: String(row.created_at || ""),
      artwork_count: integerValue(row.artwork_count), downloads: integerValue(row.downloads),
      followers: integerValue(row.followers), followed: Boolean(row.followed),
      is_me: viewer?.id === String(row.id),
    },
  });
}

export async function handleReport(request: Request, env: Env, id: string): Promise<Response> {
  const user = await requireUser(request, env);
  await visibleArtwork(env, id, user);
  await enforceRateLimit(env, user.id, "report", 10, 86400);
  const value = await readJsonObject(request, 8192);
  const reason = plainText(value.reason, "reason", 40, true);
  if (!["copyright", "misleading", "abuse", "unsafe", "duplicate", "other"].includes(reason)) throw new HttpError(400, "invalid_reason");
  const details = plainText(value.details, "details", 800, false);
  const reportId = crypto.randomUUID();
  try {
    await env.DB.prepare(
      "INSERT INTO reports(id, reporter_id, artwork_id, reason, details, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
    ).bind(reportId, user.id, id, reason, details, new Date().toISOString()).run();
  } catch {
    throw new HttpError(409, "already_reported");
  }
  await env.DB.prepare("UPDATE artworks SET report_count = report_count + 1 WHERE id = ?1").bind(id).run();
  return jsonResponse({ report_id: reportId, status: "open" }, 201);
}

export async function handleRemoveArtwork(request: Request, env: Env, id: string): Promise<Response> {
  const user = await requireUser(request, env);
  const result = await env.DB.prepare(
    `UPDATE artworks SET status = 'removed', featured = 0, updated_at = ?3
      WHERE id = ?1 AND creator_id = ?2 AND status <> 'removed' RETURNING id`,
  ).bind(id, user.id, new Date().toISOString()).first();
  if (!result) throw new HttpError(404, "artwork_not_found");
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare("UPDATE artwork_revisions SET status = 'removed' WHERE artwork_id = ?1").bind(id),
    env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(id),
    env.DB.prepare(
      "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, ?2, ?3, 'owner_removed', '', ?4)",
    ).bind(crypto.randomUUID(), id, user.username, now),
  ]);
  return jsonResponse({ removed: true });
}
