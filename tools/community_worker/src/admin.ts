import {
  adminAuthorized,
  base64ToBytes,
  HttpError,
  jsonResponse,
  plainText,
  readJsonObject,
  sha256Hex,
} from "./security";
import type { Env } from "./types";
import { MAX_PREVIEW_BYTES, MAX_THUMBNAIL_BYTES, validatePng } from "./validation";
import { FEATURED_ARTWORK_LIMIT } from "./catalog";
import {
  getVersionPolicy,
  publicVersionPolicy,
  setManualVersionPolicy,
  syncVersionPolicy,
} from "./version_policy";

function requireAdmin(request: Request, env: Env): void {
  if (!adminAuthorized(request, env)) throw new HttpError(401, "admin_auth_required");
}

function parseManifest(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

export async function handleAdminQueue(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const url = new URL(request.url);
  const status = url.searchParams.get("status") || "pending";
  const classification = url.searchParams.get("classification") || "all";
  const audience = url.searchParams.get("audience") || "all";
  const search = (url.searchParams.get("search") || "").trim().slice(0, 100).toLocaleLowerCase("en-US");
  const requestedSort = url.searchParams.get("sort") || (status === "pending" ? "oldest" : "latest");
  const requestedPage = Math.max(1, Math.min(10000, Number.parseInt(url.searchParams.get("page") || "1", 10) || 1));
  const limit = Math.max(1, Math.min(100, Number.parseInt(url.searchParams.get("limit") || "48", 10) || 48));
  const statuses = new Set(["pending", "published", "rejected", "removed", "featured", "all"]);
  const classifications = new Set(["all", "handmade", "toolmade"]);
  const audiences = new Set(["all", "everyone", "supporters"]);
  const orderBy: Record<string, string> = {
    latest: "COALESCE(a.published_at, a.created_at) DESC, a.updated_at DESC, a.id DESC",
    oldest: "COALESCE(a.published_at, a.created_at) ASC, a.updated_at ASC, a.id ASC",
    updated: "a.updated_at DESC, a.id DESC",
    downloads: "a.download_count DESC, a.favorite_count DESC, COALESCE(a.published_at, a.created_at) DESC",
    favorites: "a.favorite_count DESC, a.download_count DESC, COALESCE(a.published_at, a.created_at) DESC",
    reports: "a.report_count DESC, a.updated_at DESC, a.id DESC",
    shapes: "a.shape_count DESC, a.updated_at DESC, a.id DESC",
    name: "lower(a.title) ASC, a.id ASC",
  };
  if (!statuses.has(status)) throw new HttpError(400, "invalid_status");
  if (!classifications.has(classification)) throw new HttpError(400, "invalid_classification");
  if (!audiences.has(audience)) throw new HttpError(400, "invalid_audience");
  if (!(requestedSort in orderBy)) throw new HttpError(400, "invalid_sort");

  const parameters: unknown[] = [];
  const bind = (value: unknown): string => {
    parameters.push(value);
    return `?${parameters.length}`;
  };
  const conditions: string[] = [];
  if (status === "featured") {
    conditions.push("a.status = 'published'");
    conditions.push("a.featured = 1");
  } else if (status !== "all") {
    const token = bind(status);
    conditions.push(`(a.status = ${token} OR EXISTS(
      SELECT 1 FROM artwork_revisions r WHERE r.artwork_id = a.id AND r.status = ${token}
    ))`);
  }
  if (classification !== "all") conditions.push(`a.classification = ${bind(classification)}`);
  if (audience === "everyone") conditions.push("a.supporter_only = 0");
  if (audience === "supporters") conditions.push("a.supporter_only = 1");
  if (search) {
    const pattern = `%${search.replace(/[\\%_]/g, "\\$&")}%`;
    const token = bind(pattern);
    conditions.push(`(
      lower(a.title) LIKE ${token} ESCAPE '\\'
      OR lower(a.description) LIKE ${token} ESCAPE '\\'
      OR lower(a.tags_json) LIKE ${token} ESCAPE '\\'
      OR lower(u.username) LIKE ${token} ESCAPE '\\'
    )`);
  }
  const where = conditions.length ? `WHERE ${conditions.join(" AND ")}` : "";
  const count = await env.DB.prepare(
    `SELECT COUNT(*) AS total
       FROM artworks a JOIN users u ON u.id = a.creator_id
       ${where}`,
  ).bind(...parameters).first<{ total: number }>();
  const total = Number(count?.total || 0);
  const featuredCount = Number((await env.DB.prepare(
    "SELECT COUNT(*) AS total FROM artworks WHERE status = 'published' AND featured = 1",
  ).first<{ total: number }>())?.total || 0);
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const page = Math.min(requestedPage, pageCount);
  const queryParameters = [...parameters, limit, (page - 1) * limit];
  const rows = await env.DB.prepare(
    `SELECT a.id, a.title, a.description, a.category, a.classification, a.supporter_only, a.tags_json, a.games_json, a.shape_count, a.uses_masks,
            a.group_count, a.source_schema, a.schema_known, a.status, a.rejection_reason,
            a.featured, a.current_revision,
            a.content_hash, a.preview_hash, a.download_count, a.favorite_count,
            a.report_count, a.created_at, a.updated_at, a.published_at,
            u.username, u.provider_login,
            (SELECT MAX(revision) FROM artwork_revisions WHERE artwork_id = a.id) AS latest_revision,
            (SELECT status FROM artwork_revisions WHERE artwork_id = a.id ORDER BY revision DESC LIMIT 1) AS latest_revision_status
       FROM artworks a JOIN users u ON u.id = a.creator_id
       ${where}
      ORDER BY ${orderBy[requestedSort]}
      LIMIT ?${parameters.length + 1} OFFSET ?${parameters.length + 2}`,
  ).bind(...queryParameters).all<Record<string, unknown>>();
  return jsonResponse({
    items: rows.results || [],
    status,
    classification,
    audience,
    search,
    sort: requestedSort,
    page,
    page_size: limit,
    total,
    page_count: pageCount,
    featured_count: featuredCount,
    featured_limit: FEATURED_ARTWORK_LIMIT,
  });
}

export async function handleAdminReports(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const rows = await env.DB.prepare(
    `SELECT r.id, r.artwork_id, r.reason, r.details, r.status, r.created_at,
             reporter.username AS reporter, a.title, a.category, a.classification, a.supporter_only, a.shape_count,
            a.source_schema, a.schema_known, a.status AS artwork_status,
            a.report_count, a.current_revision,
            creator.username AS creator
       FROM reports r
       JOIN users reporter ON reporter.id = r.reporter_id
       JOIN artworks a ON a.id = r.artwork_id
       JOIN users creator ON creator.id = a.creator_id
      WHERE r.status = 'open' ORDER BY r.created_at ASC LIMIT 250`,
  ).all<Record<string, unknown>>();
  return jsonResponse({ items: rows.results || [] });
}

export async function handleAdminAsset(request: Request, env: Env, id: string): Promise<Response> {
  requireAdmin(request, env);
  const row = await env.DB.prepare(
    `SELECT r.preview_key FROM artwork_revisions r
      WHERE r.artwork_id = ?1 ORDER BY r.revision DESC LIMIT 1`,
  ).bind(id).first<{ preview_key: string }>();
  if (!row) throw new HttpError(404, "asset_not_found");
  const object = await env.ASSETS.get(row.preview_key);
  if (!object) throw new HttpError(404, "asset_not_found");
  const headers = new Headers({ "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" });
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  return new Response(object.body, { headers });
}

export async function handleAdminRerenderQueue(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const status = new URL(request.url).searchParams.get("status") || "published";
  if (!["published", "pending", "rejected", "removed", "all"].includes(status)) {
    throw new HttpError(400, "invalid_status");
  }
  const selection = `SELECT a.id, a.title, a.status, a.current_revision, a.content_hash,
                            a.preview_hash, a.thumbnail_hash, a.uses_masks,
                            r.design_bytes, r.preview_bytes, r.thumbnail_bytes
                       FROM artworks a
                       JOIN artwork_revisions r
                         ON r.artwork_id = a.id AND r.revision = a.current_revision`;
  const statement = status === "all"
    ? env.DB.prepare(`${selection} ORDER BY a.created_at ASC LIMIT 500`)
    : env.DB.prepare(`${selection} WHERE a.status = ?1 ORDER BY a.created_at ASC LIMIT 500`).bind(status);
  const rows = await statement.all<Record<string, unknown>>();
  return jsonResponse({ items: rows.results || [], status });
}

export async function handleAdminDesign(request: Request, env: Env, id: string): Promise<Response> {
  requireAdmin(request, env);
  const row = await env.DB.prepare(
    `SELECT a.current_revision, a.content_hash, r.design_key
       FROM artworks a JOIN artwork_revisions r
         ON r.artwork_id = a.id AND r.revision = a.current_revision
      WHERE a.id = ?1 LIMIT 1`,
  ).bind(id).first<{ current_revision: number; content_hash: string; design_key: string }>();
  if (!row) throw new HttpError(404, "artwork_not_found");
  const object = await env.ASSETS.get(row.design_key);
  if (!object) throw new HttpError(404, "asset_not_found");
  return new Response(object.body, {
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Artwork-Revision": String(row.current_revision),
      "X-Content-Sha256": row.content_hash,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function handleAdminReplaceRenderedAssets(
  request: Request,
  env: Env,
  _ctx: ExecutionContext,
  id: string,
): Promise<Response> {
  requireAdmin(request, env);
  const value = await readJsonObject(request, 4 * 1024 * 1024);
  const expectedRevision = Number(value.expected_revision);
  if (!Number.isInteger(expectedRevision) || expectedRevision < 1) {
    throw new HttpError(400, "invalid_revision");
  }
  const expectedContentHash = plainText(value.expected_content_sha256, "expected_content_sha256", 64, true).toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(expectedContentHash)) throw new HttpError(400, "invalid_content_hash");
  const rendererVersion = plainText(value.renderer_version, "renderer_version", 32, true);
  if (value.uses_masks != null && typeof value.uses_masks !== "boolean") {
    throw new HttpError(400, "invalid_mask_metadata");
  }
  const previewBytes = base64ToBytes(value.preview_base64, MAX_PREVIEW_BYTES);
  const thumbnailBytes = base64ToBytes(value.thumbnail_base64, MAX_THUMBNAIL_BYTES);
  validatePng(previewBytes);
  validatePng(thumbnailBytes, 640);
  const [previewHash, thumbnailHash] = await Promise.all([
    sha256Hex(previewBytes),
    sha256Hex(thumbnailBytes),
  ]);

  const current = await env.DB.prepare(
    `SELECT a.current_revision, a.content_hash, a.preview_hash, a.thumbnail_hash, a.uses_masks,
            r.preview_key, r.thumbnail_key, r.uses_masks AS revision_uses_masks
       FROM artworks a JOIN artwork_revisions r
         ON r.artwork_id = a.id AND r.revision = a.current_revision
      WHERE a.id = ?1 LIMIT 1`,
  ).bind(id).first<{
    current_revision: number;
    content_hash: string;
    preview_hash: string;
    thumbnail_hash: string;
    uses_masks: number;
    preview_key: string;
    thumbnail_key: string;
    revision_uses_masks: number;
  }>();
  if (!current) throw new HttpError(404, "artwork_not_found");
  if (Number(current.current_revision) !== expectedRevision || current.content_hash !== expectedContentHash) {
    throw new HttpError(409, "stale_artwork", "The artwork changed before its rendered assets could be replaced.");
  }
  const usesMasks = value.uses_masks == null ? Boolean(current.uses_masks) : value.uses_masks;
  const maskMetadataMatches = Boolean(current.uses_masks) === usesMasks
    && Boolean(current.revision_uses_masks) === usesMasks;
  if (current.preview_hash === previewHash && current.thumbnail_hash === thumbnailHash) {
    if (!maskMetadataMatches) {
      const now = new Date().toISOString();
      await env.DB.batch([
        env.DB.prepare(
          `UPDATE artwork_revisions SET uses_masks = ?4
            WHERE artwork_id = ?1 AND revision = ?2 AND content_hash = ?3`,
        ).bind(id, expectedRevision, expectedContentHash, usesMasks ? 1 : 0),
        env.DB.prepare(
          `UPDATE artworks SET uses_masks = ?4
            WHERE id = ?1 AND current_revision = ?2 AND content_hash = ?3`,
        ).bind(id, expectedRevision, expectedContentHash, usesMasks ? 1 : 0),
        env.DB.prepare(
          `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
           VALUES (?1, ?2, 'admin', 'refresh_mask_metadata', ?3, ?4)`,
        ).bind(crypto.randomUUID(), id, JSON.stringify({ uses_masks: usesMasks }), now),
      ]);
    }
    return jsonResponse({
      artwork_id: id,
      revision: expectedRevision,
      unchanged: true,
      metadata_updated: !maskMetadataMatches,
      uses_masks: usesMasks,
      preview_sha256: previewHash,
      thumbnail_sha256: thumbnailHash,
    });
  }
  const collision = await env.DB.prepare(
    `SELECT artwork_id FROM artwork_revisions
      WHERE preview_hash = ?1 AND NOT (artwork_id = ?2 AND revision = ?3) LIMIT 1`,
  ).bind(previewHash, id, expectedRevision).first<{ artwork_id: string }>();
  if (collision) throw new HttpError(409, "duplicate_rendered_preview", "The regenerated preview matches another artwork.");

  const assetVersion = crypto.randomUUID();
  const previewKey = `artworks/${id}/r${expectedRevision}/${assetVersion}/preview.png`;
  const thumbnailKey = `artworks/${id}/r${expectedRevision}/${assetVersion}/thumbnail.png`;
  try {
    await env.ASSETS.put(previewKey, previewBytes, {
      httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
      customMetadata: { sha256: previewHash, artworkId: id, revision: String(expectedRevision), rendererVersion },
    });
    await env.ASSETS.put(thumbnailKey, thumbnailBytes, {
      httpMetadata: { contentType: "image/png", cacheControl: "public, max-age=86400" },
      customMetadata: { sha256: thumbnailHash, artworkId: id, revision: String(expectedRevision), rendererVersion },
    });
    const eventId = crypto.randomUUID();
    const note = JSON.stringify({
      renderer_version: rendererVersion,
      previous_preview_sha256: current.preview_hash,
      previous_preview_key: current.preview_key,
      previous_thumbnail_key: current.thumbnail_key,
      previous_uses_masks: Boolean(current.uses_masks),
      preview_sha256: previewHash,
      thumbnail_sha256: thumbnailHash,
      uses_masks: usesMasks,
    }).slice(0, 500);
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE artwork_revisions
            SET preview_hash = ?4, thumbnail_hash = ?5,
                preview_key = ?6, thumbnail_key = ?7,
                preview_bytes = ?8, thumbnail_bytes = ?9, uses_masks = ?11
          WHERE artwork_id = ?1 AND revision = ?2 AND content_hash = ?3 AND preview_key = ?10`,
      ).bind(
        id, expectedRevision, expectedContentHash, previewHash, thumbnailHash,
        previewKey, thumbnailKey, previewBytes.length, thumbnailBytes.length, current.preview_key,
        usesMasks ? 1 : 0,
      ),
      env.DB.prepare(
        `UPDATE artworks SET preview_hash = ?4, thumbnail_hash = ?5, uses_masks = ?6
          WHERE id = ?1 AND current_revision = ?2 AND content_hash = ?3`,
      ).bind(id, expectedRevision, expectedContentHash, previewHash, thumbnailHash, usesMasks ? 1 : 0),
      env.DB.prepare(
        `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
         VALUES (?1, ?2,
           CASE WHEN EXISTS(
             SELECT 1 FROM artworks a JOIN artwork_revisions r
               ON r.artwork_id = a.id AND r.revision = a.current_revision
             WHERE a.id = ?2 AND a.current_revision = ?3 AND a.preview_hash = ?4
               AND a.thumbnail_hash = ?5 AND a.uses_masks = ?10
               AND r.preview_key = ?6 AND r.thumbnail_key = ?7 AND r.uses_masks = ?10
           ) THEN 'admin' ELSE NULL END,
           'rerender_assets', ?8, ?9)`,
      ).bind(
        eventId, id, expectedRevision, previewHash, thumbnailHash,
        previewKey, thumbnailKey, note, new Date().toISOString(), usesMasks ? 1 : 0,
      ),
    ]);
  } catch (error) {
    await Promise.all([
      env.ASSETS.delete(previewKey).catch(() => undefined),
      env.ASSETS.delete(thumbnailKey).catch(() => undefined),
    ]);
    throw error;
  }

  return jsonResponse({
    artwork_id: id,
    revision: expectedRevision,
    unchanged: false,
    preview_sha256: previewHash,
    thumbnail_sha256: thumbnailHash,
    uses_masks: usesMasks,
    rollback_assets_retained: true,
  });
}

export async function handleAdminModerate(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const value = await readJsonObject(request, 16 * 1024);
  const artworkId = plainText(value.artwork_id, "artwork_id", 64, true);
  const action = plainText(value.action, "action", 24, true);
  const note = plainText(value.note, "note", 500, false);
  const requestedRevision = Number(value.revision || 0);
  if (!["approve", "reject", "remove", "feature", "unfeature", "classify_handmade", "classify_toolmade"].includes(action)) {
    throw new HttpError(400, "invalid_action");
  }
  const artwork = await env.DB.prepare(
    "SELECT id, creator_id, status, current_revision, classification, featured FROM artworks WHERE id = ?1 LIMIT 1",
  ).bind(artworkId).first<{
    id: string;
    creator_id: string;
    status: string;
    current_revision: number;
    classification: string;
    featured: number;
  }>();
  if (!artwork) throw new HttpError(404, "artwork_not_found");
  const now = new Date().toISOString();

  if (action === "feature" || action === "unfeature") {
    if (artwork.status !== "published") throw new HttpError(409, "artwork_not_published");
    if (action === "feature" && !Boolean(artwork.featured)) {
      const featured = await env.DB.prepare(
        `UPDATE artworks SET featured = 1, updated_at = ?2
          WHERE id = ?1 AND status = 'published' AND featured = 0
            AND (SELECT COUNT(*) FROM artworks WHERE status = 'published' AND featured = 1) < ?3
          RETURNING id`,
      ).bind(artworkId, now, FEATURED_ARTWORK_LIMIT).first<{ id: string }>();
      if (!featured) {
        throw new HttpError(
          409,
          "featured_slots_full",
          `All ${FEATURED_ARTWORK_LIMIT} featured slots are occupied. Unfeature one artwork before adding another.`,
        );
      }
    } else if (action === "unfeature") {
      await env.DB.prepare("UPDATE artworks SET featured = 0, updated_at = ?2 WHERE id = ?1")
        .bind(artworkId, now).run();
    }
  } else if (action === "classify_handmade" || action === "classify_toolmade") {
    const classification = action === "classify_handmade" ? "handmade" : "toolmade";
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE artworks SET classification = ?2, updated_at = ?3 WHERE id = ?1",
      ).bind(artworkId, classification, now),
      env.DB.prepare(
        "UPDATE artwork_revisions SET manifest_json = json_set(manifest_json, '$.classification', ?2) WHERE artwork_id = ?1",
      ).bind(artworkId, classification),
    ]);
  } else if (action === "remove") {
    await env.DB.batch([
      env.DB.prepare("UPDATE artworks SET status = 'removed', featured = 0, updated_at = ?2 WHERE id = ?1").bind(artworkId, now),
      env.DB.prepare("UPDATE artwork_revisions SET status = 'removed' WHERE artwork_id = ?1").bind(artworkId),
      env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(artworkId),
    ]);
  } else {
    const revision = Number.isInteger(requestedRevision) && requestedRevision > 0
      ? requestedRevision
      : Number((await env.DB.prepare(
        "SELECT MAX(revision) AS revision FROM artwork_revisions WHERE artwork_id = ?1 AND status = 'pending'",
      ).bind(artworkId).first<{ revision: number }>())?.revision || 0);
    if (!revision) throw new HttpError(409, "pending_revision_not_found");
    const row = await env.DB.prepare(
      `SELECT revision, content_hash, preview_hash, thumbnail_hash, shape_count, uses_masks, manifest_json, status
         FROM artwork_revisions WHERE artwork_id = ?1 AND revision = ?2 LIMIT 1`,
    ).bind(artworkId, revision).first<Record<string, unknown>>();
    if (!row || row.status !== "pending") throw new HttpError(409, "pending_revision_not_found");
    if (artwork.status === "published" && revision <= Number(artwork.current_revision || 0)) {
      throw new HttpError(409, "stale_revision", "A newer revision is already published.");
    }
    if (action === "reject") {
      const reason = note || "The submission did not meet the community publishing requirements.";
      const statements = [
        env.DB.prepare(
          "UPDATE artwork_revisions SET status = 'rejected', rejection_reason = ?3 WHERE artwork_id = ?1 AND revision = ?2",
        ).bind(artworkId, revision, reason),
      ];
      if (artwork.status === "pending" && revision === 1) {
        statements.push(env.DB.prepare(
          "UPDATE artworks SET status = 'rejected', rejection_reason = ?2, updated_at = ?3 WHERE id = ?1",
        ).bind(artworkId, reason, now));
      }
      await env.DB.batch(statements);
    } else {
      const manifest = parseManifest(String(row.manifest_json || "{}"));
      const classification = manifest.classification === "handmade" || manifest.classification === "toolmade"
        ? String(manifest.classification)
        : artwork.classification === "handmade" ? "handmade" : "toolmade";
      await env.DB.batch([
        env.DB.prepare(
          `UPDATE artwork_revisions
              SET status = 'rejected', rejection_reason = 'Superseded by a newer approved revision.'
            WHERE artwork_id = ?1 AND status = 'pending' AND revision < ?2`,
        ).bind(artworkId, revision),
        env.DB.prepare(
          `UPDATE artwork_revisions SET status = 'published', rejection_reason = ''
            WHERE artwork_id = ?1 AND revision = ?2`,
        ).bind(artworkId, revision),
        env.DB.prepare(
          `UPDATE artworks SET status = 'published', rejection_reason = '', current_revision = ?2,
            title = ?3, description = ?4, category = ?5, classification = ?6,
            tags_json = ?7, games_json = ?8,
            source_schema = ?9, schema_known = ?10, license = ?11, shape_count = ?12,
            group_count = ?13, content_hash = ?14, preview_hash = ?15, thumbnail_hash = ?16,
            updated_at = ?17, published_at = COALESCE(published_at, ?17), uses_masks = ?18
           WHERE id = ?1`,
        ).bind(
          artworkId, revision, String(manifest.title || "Untitled"), String(manifest.description || ""),
          String(manifest.category || "Other"), classification,
          JSON.stringify(manifest.tags || []), JSON.stringify(manifest.games || []),
          String(manifest.source_schema || "legacy-kfps"), manifest.schema_known === false ? 0 : 1,
          String(manifest.license || "kfps-community-share-v1"), Number(manifest.shape_count || row.shape_count || 0),
          Number(manifest.group_count || 0), String(row.content_hash), String(row.preview_hash),
          String(row.thumbnail_hash || row.preview_hash), now,
          manifest.uses_masks === true || Boolean(row.uses_masks) ? 1 : 0,
        ),
        env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(artworkId),
        env.DB.prepare(
          `INSERT INTO artwork_search(artwork_id, title, description, creator, tags)
           SELECT ?1, ?2, ?3, username, ?4 FROM users WHERE id = ?5`,
        ).bind(artworkId, String(manifest.title || "Untitled"), String(manifest.description || ""),
          Array.isArray(manifest.tags) ? manifest.tags.join(" ") : "", artwork.creator_id),
      ]);
    }
  }

  await env.DB.prepare(
    "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, ?2, 'admin', ?3, ?4, ?5)",
  ).bind(crypto.randomUUID(), artworkId, action, note, now).run();
  const featuredCount = Number((await env.DB.prepare(
    "SELECT COUNT(*) AS total FROM artworks WHERE status = 'published' AND featured = 1",
  ).first<{ total: number }>())?.total || 0);
  return jsonResponse({
    artwork_id: artworkId,
    action,
    ok: true,
    featured_count: featuredCount,
    featured_limit: FEATURED_ARTWORK_LIMIT,
  });
}

export async function handleAdminResolveReport(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const value = await readJsonObject(request, 8192);
  const reportId = plainText(value.report_id, "report_id", 64, true);
  const resolution = plainText(value.resolution, "resolution", 16, true);
  if (!["resolved", "dismissed"].includes(resolution)) throw new HttpError(400, "invalid_resolution");
  const result = await env.DB.prepare(
    `UPDATE reports SET status = ?2, resolved_at = ?3 WHERE id = ?1 AND status = 'open' RETURNING artwork_id`,
  ).bind(reportId, resolution, new Date().toISOString()).first<{ artwork_id: string }>();
  if (!result) throw new HttpError(404, "report_not_found");
  await env.DB.prepare(
    "UPDATE artworks SET report_count = (SELECT COUNT(*) FROM reports WHERE artwork_id = ?1 AND status = 'open') WHERE id = ?1",
  ).bind(result.artwork_id).run();
  return jsonResponse({ report_id: reportId, status: resolution });
}

export async function handleAdminUserAction(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const value = await readJsonObject(request, 8192);
  const username = plainText(value.username, "username", 24, true).toLocaleLowerCase("en-US");
  const action = plainText(value.action, "action", 16, true);
  if (!["suspend", "restore"].includes(action)) throw new HttpError(400, "invalid_action");
  const now = new Date().toISOString();
  const user = await env.DB.prepare(
    "SELECT id FROM users WHERE username_norm = ?1 LIMIT 1",
  ).bind(username).first<{ id: string }>();
  if (!user) throw new HttpError(404, "creator_not_found");
  const statements = [
    env.DB.prepare("UPDATE users SET suspended_at = ?2, updated_at = ?3 WHERE id = ?1")
      .bind(user.id, action === "suspend" ? now : null, now),
    env.DB.prepare(
      "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, NULL, 'admin', ?2, ?3, ?4)",
    ).bind(crypto.randomUUID(), `user_${action}`, username, now),
  ];
  if (action === "suspend") {
    statements.push(env.DB.prepare("DELETE FROM sessions WHERE user_id = ?1").bind(user.id));
  }
  await env.DB.batch(statements);
  return jsonResponse({ username, action, ok: true });
}

export async function handleAdminVersionStatus(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  return jsonResponse({ version: publicVersionPolicy(await getVersionPolicy(env)) });
}

export async function handleAdminVersionAction(request: Request, env: Env): Promise<Response> {
  requireAdmin(request, env);
  const value = await readJsonObject(request, 8192);
  const action = plainText(value.action, "action", 16, true);
  let policy;
  if (action === "sync") {
    policy = await syncVersionPolicy(env, { force: true, reason: "admin" });
  } else if (action === "set") {
    policy = await setManualVersionPolicy(env, value.minimum_version as string, value.automatic === true);
  } else if (action === "pause") {
    const current = await getVersionPolicy(env);
    policy = await setManualVersionPolicy(env, current.minimumVersion, false);
  } else {
    throw new HttpError(400, "invalid_action");
  }
  const publicPolicy = publicVersionPolicy(policy);
  await env.DB.prepare(
    "INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at) VALUES (?1, NULL, 'admin', ?2, ?3, ?4)",
  ).bind(
    crypto.randomUUID(), `version_${action}`, JSON.stringify(publicPolicy), new Date().toISOString(),
  ).run();
  return jsonResponse({ version: publicPolicy });
}

export const ADMIN_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>KFPS Community Moderation</title><style>
:root{font-family:Segoe UI,Arial,sans-serif;color:#f8eaf3;background:#100b11}*{box-sizing:border-box}
body{margin:0;background:#100b11}header{position:sticky;top:0;z-index:2;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:14px 18px;background:#171118;border-bottom:1px solid #583249}
h1{font-size:18px;margin:0;margin-right:auto;color:#ff82bb}button,input,select{border:1px solid #74405e;background:#241820;color:#fff;padding:9px 11px;border-radius:6px}
button{cursor:pointer}button:hover{border-color:#ff71b3}button:disabled{cursor:default;opacity:.42}.primary{background:#9c285f}.danger{background:#6b2432}.wrap{padding:18px;max-width:1680px;margin:auto}
.tabs,.segments,.pager{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.tabs{margin-bottom:12px}.tabs button.active,.segments button.active{border-color:#ff82bb;background:#7c234f;box-shadow:inset 0 -2px #ff82bb}
.tabs button.slots-full{border-color:#d49a40;color:#ffd089}
.queue-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:12px;margin-bottom:8px;border:1px solid #4f3345;background:#171118;border-radius:8px}.queue-controls input{min-width:240px;flex:1}.queue-controls label{font-size:12px;color:#bca0b1;display:flex;gap:6px;align-items:center}
.results-line{min-height:24px;color:#bca0b1;font-size:12px;padding:2px 3px 10px}.pager{justify-content:center;padding:18px 0 4px}.hidden{display:none!important}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.card{border:1px solid #4f3345;background:#1a1319;border-radius:8px;overflow:hidden}.card.reported{border-color:#db4966;box-shadow:inset 4px 0 #db4966}.card img{display:block;width:100%;height:220px;object-fit:contain;background:#0b080b}
.body{padding:12px}.meta{font-size:12px;color:#bca0b1}.flag{display:inline-block;margin:0 5px 8px 0;padding:4px 7px;border:1px solid #db4966;border-radius:4px;color:#ff9caf;background:#39151f;font-size:11px;font-weight:700}.flag.schema{border-color:#d49a40;color:#ffd089;background:#3b2a12}.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.empty{padding:40px;text-align:center;color:#bca0b1}
.flag.supporter{border-color:#ff71b3;color:#ffd3e8;background:#4b1832}.flag.handmade{border-color:#ff9dc9;color:#ffd5e8;background:#482034}.flag.toolmade{border-color:#78cfff;color:#bfeaff;background:#173344}.flag.masks{border-color:#e5c550;color:#ffe88a;background:#40350f}.version{max-width:760px;border:1px solid #74405e;background:#1a1319;border-radius:8px;padding:18px}.version h2{margin:0 0 8px;color:#ff82bb}.version dl{display:grid;grid-template-columns:180px 1fr;gap:8px;margin:16px 0}.version dt{color:#bca0b1}.version dd{margin:0;overflow-wrap:anywhere}.version .field{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:14px}.version .field input{min-width:180px}
@media(max-width:720px){.wrap{padding:12px}.queue-controls>*{width:100%}.queue-controls label{justify-content:space-between}.segments button{flex:1}.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>KFPS Community Moderation</h1><input id="creator" placeholder="Creator username"><button onclick="userAction('suspend')">Suspend</button><button onclick="userAction('restore')">Restore</button><input id="token" type="password" placeholder="Admin token"><button class="primary" onclick="reloadCurrent()">Connect</button></header>
<main class="wrap">
<nav class="tabs" id="view-tabs">
  <button data-mode="pending" onclick="setQueueMode('pending')">Pending</button>
  <button data-mode="featured" id="featured-tab" onclick="setQueueMode('featured')">Featured -/8</button>
  <button data-mode="published" onclick="setQueueMode('published')">Published</button>
  <button data-mode="rejected" onclick="setQueueMode('rejected')">Rejected</button>
  <button data-mode="removed" onclick="setQueueMode('removed')">Removed</button>
  <button data-mode="all" onclick="setQueueMode('all')">All artwork</button>
  <button data-view="reports" onclick="loadReports()">Reports</button>
  <button data-view="version" onclick="loadVersion()">Version policy</button>
</nav>
<section class="queue-controls" id="queue-controls">
  <input id="queue-search" type="search" placeholder="Search title, description, tags, or creator" oninput="scheduleSearch()">
  <div class="segments" id="classification-tabs">
    <button data-classification="all" onclick="setClassification('all')">All</button>
    <button data-classification="handmade" onclick="setClassification('handmade')">Handmade</button>
    <button data-classification="toolmade" onclick="setClassification('toolmade')">Toolmade</button>
  </div>
  <label>Audience
    <select id="queue-audience" onchange="queueSettingChanged()">
      <option value="all">Everyone + supporters</option>
      <option value="everyone">Everyone</option>
      <option value="supporters">Supporters only</option>
    </select>
  </label>
  <label>Sort
    <select id="queue-sort" onchange="sortChanged()">
      <option value="latest">Latest</option>
      <option value="oldest" selected>Oldest</option>
      <option value="updated">Recently updated</option>
      <option value="downloads">Most downloads</option>
      <option value="favorites">Most favorites</option>
      <option value="reports">Most reports</option>
      <option value="shapes">Most shapes</option>
      <option value="name">Name A-Z</option>
    </select>
  </label>
  <label>Per page
    <select id="queue-limit" onchange="queueSettingChanged()">
      <option value="24">24</option>
      <option value="48" selected>48</option>
      <option value="96">96</option>
    </select>
  </label>
</section>
<div class="results-line" id="queue-summary"></div>
<div id="content" class="grid"></div>
<nav class="pager hidden" id="pager">
  <button id="page-first" onclick="setPage(1)">First</button>
  <button id="page-previous" onclick="setPage(page-1)">Previous</button>
  <span id="page-label"></span>
  <button id="page-next" onclick="setPage(page+1)">Next</button>
  <button id="page-last" onclick="setPage(pageCount)">Last</button>
</nav>
</main>
<script>
let mode='pending';
let currentView='queue';
let classification='all';
let page=1;
let pageCount=1;
let sortTouched=false;
let searchTimer=0;
let loadGeneration=0;
const content=document.getElementById('content');
const token=document.getElementById('token');
const creator=document.getElementById('creator');
const controls=document.getElementById('queue-controls');
const summary=document.getElementById('queue-summary');
const pager=document.getElementById('pager');
const sortSelect=document.getElementById('queue-sort');
const audienceSelect=document.getElementById('queue-audience');
const limitSelect=document.getElementById('queue-limit');
const searchInput=document.getElementById('queue-search');
const featuredTab=document.getElementById('featured-tab');
token.value=sessionStorage.getItem('kfps-admin-token')||'';
const headers=()=>({'Content-Type':'application/json','X-Community-Admin-Token':token.value});
async function api(path,options={}){sessionStorage.setItem('kfps-admin-token',token.value);const r=await fetch(path,{...options,headers:{...headers(),...(options.headers||{})}});if(!r.ok){let message=r.statusText;try{message=(await r.json()).message||message}catch{}throw new Error(message)}return r.json()}
async function image(id,img){const r=await fetch('/v1/admin/artworks/'+id+'/preview',{headers:headers()});if(r.ok)img.src=URL.createObjectURL(await r.blob())}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const schemaLabels={'legacy-kfps':'Legacy KFPS-compatible JSON','kfps-community':'KFPS Community JSON','kfps-primitives':'KFPS primitive geometry','forza-typecode-export':'Forza live type-code export','forza-save-library':'KFPS save-library export','forza-file-export':'KFPS decoded file export','kfps-cgroup-flat':'KFPS flat C_group JSON','fd6-converted':'Forza Designer 6 conversion','fh6-typecode':'FH6 type-code geometry','forza-typecode':'Forza type-code geometry','unrecognized':'Unrecognized compatible JSON'};
function schemaName(item){return schemaLabels[item.source_schema]||item.source_schema||'KFPS-compatible JSON'}
function schemaFlag(item){return Number(item.schema_known)?'':'<div class="flag schema">COMPATIBILITY UNVERIFIED</div>'}
function supporterFlag(item){return Number(item.supporter_only)?'<div class="flag supporter">SUPPORTERS ONLY</div>':''}
function classificationFlag(item){const value=item.classification==='handmade'?'handmade':'toolmade';return '<div class="flag '+value+'">'+value.toUpperCase()+'</div>'}
function masksFlag(item){return Number(item.uses_masks)?'<div class="flag masks">MASKS</div>':''}
function actionButton(parent,label,style,handler,disabled=false,title=''){const button=document.createElement('button');button.textContent=label;if(style)button.className=style;button.onclick=handler;button.disabled=disabled;if(title)button.title=title;parent.append(button)}
function markActive(){document.querySelectorAll('#view-tabs button').forEach(button=>{const active=currentView==='queue'?button.dataset.mode===mode:button.dataset.view===currentView;button.classList.toggle('active',active)});document.querySelectorAll('#classification-tabs button').forEach(button=>button.classList.toggle('active',button.dataset.classification===classification))}
function showQueueChrome(visible){controls.classList.toggle('hidden',!visible);summary.classList.toggle('hidden',!visible);if(!visible)pager.classList.add('hidden')}
function setQueueMode(next){currentView='queue';mode=next;page=1;if(!sortTouched)sortSelect.value=next==='pending'?'oldest':'latest';loadQueue()}
function setClassification(next){classification=next;page=1;loadQueue()}
function sortChanged(){sortTouched=true;page=1;loadQueue()}
function queueSettingChanged(){page=1;loadQueue()}
function scheduleSearch(){clearTimeout(searchTimer);searchTimer=setTimeout(()=>{page=1;loadQueue()},250)}
function setPage(next){const target=Math.max(1,Math.min(pageCount,Number(next)||1));if(target===page)return;page=target;loadQueue();window.scrollTo({top:0,behavior:'smooth'})}
function updatePager(){document.getElementById('page-label').textContent='Page '+page+' of '+pageCount;document.getElementById('page-first').disabled=page<=1;document.getElementById('page-previous').disabled=page<=1;document.getElementById('page-next').disabled=page>=pageCount;document.getElementById('page-last').disabled=page>=pageCount}
function reloadCurrent(){if(currentView==='reports')return loadReports();if(currentView==='version')return loadVersion();return loadQueue()}
async function loadQueue(){
  currentView='queue';showQueueChrome(true);markActive();
  const generation=++loadGeneration;
  content.className='grid';content.innerHTML='<div class="empty">Loading artwork...</div>';
  summary.textContent='Loading...';pager.classList.add('hidden');
  const params=new URLSearchParams({status:mode,classification,audience:audienceSelect.value,sort:sortSelect.value,page:String(page),limit:limitSelect.value});
  if(searchInput.value.trim())params.set('search',searchInput.value.trim());
  try{
    const data=await api('/v1/admin/queue?'+params.toString());
    if(generation!==loadGeneration)return;
    const featuredCount=Number(data.featured_count||0);
    const featuredLimit=Number(data.featured_limit||8);
    featuredTab.textContent='Featured '+featuredCount+'/'+featuredLimit;
    featuredTab.title=featuredCount>=featuredLimit?'All featured slots are occupied. Unfeature one artwork to add another.':(featuredLimit-featuredCount)+' featured slot'+(featuredLimit-featuredCount===1?'':'s')+' available.';
    featuredTab.classList.toggle('slots-full',featuredCount>=featuredLimit);
    page=Number(data.page||1);pageCount=Number(data.page_count||1);
    const start=Number(data.total)?(page-1)*Number(data.page_size)+1:0;
    const end=Math.min(Number(data.total||0),page*Number(data.page_size||0));
    summary.textContent=(mode==='featured'?featuredCount+' of '+featuredLimit+' featured slots filled | ':'')+Number(data.total||0)+' artwork'+(Number(data.total)===1?'':'s')+' matched'+(start?' | showing '+start+'-'+end:'');
    content.innerHTML='';
    for(const item of data.items){
      const reports=Number(item.report_count||0);
      const card=document.createElement('article');
      card.className='card'+(reports?' reported':'');
      card.innerHTML='<img alt=""><div class="body">'+
        (reports?'<div class="flag">'+esc(reports)+' OPEN REPORT'+(reports===1?'':'S')+'</div>':'')+
        classificationFlag(item)+supporterFlag(item)+masksFlag(item)+schemaFlag(item)+
        '<br><strong>'+esc(item.title)+'</strong>'+
        '<div class="meta">@'+esc(item.username)+' | '+esc(item.category)+' | '+esc(item.shape_count)+' shapes | '+esc(schemaName(item))+'</div>'+
        '<div class="meta">'+esc(item.status)+' | revision '+esc(item.latest_revision)+' | '+esc(item.download_count||0)+' downloads | '+esc(item.favorite_count||0)+' favorites</div>'+
        '<p>'+esc(item.description)+'</p><div class="actions"></div></div>';
      image(item.id,card.querySelector('img'));
      const actions=card.querySelector('.actions');
      if(item.latest_revision_status==='pending'){actionButton(actions,'Approve','primary',()=>moderate(item,'approve'));actionButton(actions,'Reject','',()=>moderate(item,'reject'))}
      if(item.status==='published')actionButton(actions,item.featured?'Unfeature':'Feature','',()=>moderate(item,item.featured?'unfeature':'feature'),!item.featured&&featuredCount>=featuredLimit,!item.featured&&featuredCount>=featuredLimit?'All '+featuredLimit+' featured slots are occupied.':'');
      actionButton(actions,item.classification==='handmade'?'Set Toolmade':'Set Handmade','',()=>moderate(item,item.classification==='handmade'?'classify_toolmade':'classify_handmade'));
      if(reports)actionButton(actions,'Review reports','danger',()=>loadReports());
      if(item.status!=='removed')actionButton(actions,'Remove','danger',()=>moderate(item,'remove'));
      actionButton(actions,'Suspend creator','danger',()=>userAction('suspend',item.username));
      content.append(card);
    }
    if(!data.items.length)content.innerHTML='<div class="empty">No artwork matches these filters.</div>';
    updatePager();pager.classList.toggle('hidden',pageCount<=1);
  }catch(e){if(generation!==loadGeneration)return;summary.textContent='';content.innerHTML='<div class="empty">'+esc(e.message)+'</div>'}
}
async function moderate(item,action){let note='';if(action==='reject'||action==='remove'){const response=prompt('Moderation note:');if(response===null)return;note=response}try{await api('/v1/admin/moderate',{method:'POST',body:JSON.stringify({artwork_id:item.id,revision:item.latest_revision,action,note})});loadQueue()}catch(e){alert(e.message)}}
async function loadReports(){currentView='reports';++loadGeneration;showQueueChrome(false);markActive();content.className='grid';content.innerHTML='<div class="empty">Loading...</div>';try{const data=await api('/v1/admin/reports');content.innerHTML='';for(const item of data.items){const reports=Number(item.report_count||1);const card=document.createElement('article');card.className='card reported';card.innerHTML='<img alt=""><div class="body"><div class="flag">OPEN REPORT | '+esc(reports)+' ON ARTWORK</div>'+classificationFlag(item)+supporterFlag(item)+schemaFlag(item)+'<br><strong>'+esc(item.title)+'</strong><div class="meta">'+esc(item.reason)+' | reported by @'+esc(item.reporter)+' | creator @'+esc(item.creator)+'</div><div class="meta">'+esc(item.category)+' | '+esc(item.shape_count)+' shapes | '+esc(schemaName(item))+' | artwork '+esc(item.artwork_status)+'</div><p>'+esc(item.details||'No additional details supplied.')+'</p><div class="actions"></div></div>';image(item.artwork_id,card.querySelector('img'));const actions=card.querySelector('.actions');actionButton(actions,'Resolve','primary',()=>resolveReport(item.id,'resolved'));actionButton(actions,'Dismiss','',()=>resolveReport(item.id,'dismissed'));if(item.artwork_status==='published')actionButton(actions,'Remove artwork','danger',()=>removeReported(item));actionButton(actions,'Suspend creator','danger',()=>userAction('suspend',item.creator));content.append(card)}if(!data.items.length)content.innerHTML='<div class="empty">No open reports.</div>'}catch(e){content.innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
async function resolveReport(id,resolution){await api('/v1/admin/reports/resolve',{method:'POST',body:JSON.stringify({report_id:id,resolution})});loadReports()}
async function removeReported(item){const note=prompt('Why is this artwork being removed?');if(note===null)return;await api('/v1/admin/moderate',{method:'POST',body:JSON.stringify({artwork_id:item.artwork_id,revision:item.current_revision,action:'remove',note})});loadReports()}
async function loadVersion(){currentView='version';++loadGeneration;showQueueChrome(false);markActive();content.className='';content.innerHTML='<div class="empty">Loading version policy...</div>';try{const data=await api('/v1/admin/version');renderVersion(data.version)}catch(e){content.innerHTML='<div class="empty">'+esc(e.message)+'</div>'}}
function renderVersion(v){content.innerHTML='<section class="version"><h2>Accepted KFPS version</h2><div class="meta">The official repository VERSION is checked automatically. Automatic checks may raise this floor but never lower it.</div><dl><dt>Minimum upload version</dt><dd><strong>'+esc(v.minimum_upload_version)+'</strong></dd><dt>Automatic sync</dt><dd>'+esc(v.automatic?'Running':'Paused')+'</dd><dt>Official source</dt><dd>'+esc(v.repository)+' @ '+esc(v.branch)+'</dd><dt>Verified commit</dt><dd>'+esc(v.source_commit||'Not synced yet')+'</dd><dt>Last successful sync</dt><dd>'+esc(v.synced_at||'Not synced yet')+'</dd><dt>Last attempt</dt><dd>'+esc(v.last_attempt_at||'Not attempted yet')+'</dd><dt>Status</dt><dd>'+esc(v.last_status||'Unknown')+(v.last_error?'<br>'+esc(v.last_error):'')+'</dd></dl><div class="actions" id="version-actions"></div><div class="field"><label for="version-floor">Manual minimum</label><input id="version-floor" value="'+esc(v.minimum_upload_version)+'" inputmode="numeric"><button id="version-set">Set and pause</button></div></section>';const actions=document.getElementById('version-actions');actionButton(actions,'Sync official VERSION','primary',()=>versionAction({action:'sync'}));actionButton(actions,v.automatic?'Pause automatic sync':'Resume automatic sync','',()=>versionAction(v.automatic?{action:'pause'}:{action:'set',minimum_version:v.minimum_upload_version,automatic:true}));document.getElementById('version-set').onclick=()=>{const minimum=document.getElementById('version-floor').value.trim();if(!confirm('Set the minimum upload version to '+minimum+' and pause automatic synchronization?'))return;versionAction({action:'set',minimum_version:minimum,automatic:false})}}
async function versionAction(payload){try{const data=await api('/v1/admin/version',{method:'POST',body:JSON.stringify(payload)});renderVersion(data.version)}catch(e){alert(e.message)}}
async function userAction(action,name=''){const username=name||creator.value.trim();if(!username)return;const verb=action==='suspend'?'Suspend':'Restore';if(!confirm(verb+' @'+username+'?'))return;try{await api('/v1/admin/users/action',{method:'POST',body:JSON.stringify({username,action})});creator.value=username;await reloadCurrent()}catch(e){alert(e.message)}}
markActive();
</script></body></html>`;
