import {
  ADMIN_HTML,
  handleAdminAsset,
  handleAdminDesign,
  handleAdminModerate,
  handleAdminQueue,
  handleAdminReplaceRenderedAssets,
  handleAdminRerenderQueue,
  handleAdminReports,
  handleAdminResolveReport,
  handleAdminUserAction,
  handleAdminVersionAction,
  handleAdminVersionStatus,
} from "./admin";
import {
  handleChooseUsername,
  handleGitHubAuth,
  handleSession,
  handleSignOut,
  handleTestAuth,
  handleUpdateProfile,
} from "./auth";
import {
  FEATURED_ARTWORK_LIMIT,
  handleArtworkAsset,
  handleArtworkDetail,
  handleCreateArtwork,
  handleCreateRevision,
  handleCreator,
  handleFavorite,
  handleFollow,
  handleIgnore,
  handleIgnoredCreators,
  handleListArtworks,
  handleRemoveArtwork,
  handleReport,
  handleUpdateArtworkMetadata,
} from "./catalog";
import { errorResponse, HttpError, jsonResponse } from "./security";
import type { Env } from "./types";
import { CATEGORIES, CLASSIFICATIONS, GAMES, LICENSES } from "./validation";
import { effectiveMinimumUploadVersion, getVersionPolicy, publicVersionPolicy, syncVersionPolicy } from "./version_policy";
import { handleClearSupporter, handleVerifySupporter } from "./supporter";

const HTML_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy": "default-src 'none'; img-src 'self' blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "Content-Type": "text/html; charset=utf-8",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
} as const;

function pathMatch(path: string, pattern: RegExp): string[] | null {
  const match = pattern.exec(path);
  return match ? match.slice(1).map((value) => decodeURIComponent(value)) : null;
}

async function route(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/+$/, "") || "/";
  const method = request.method.toUpperCase();

  if (method === "OPTIONS") {
    const origin = request.headers.get("Origin");
    if (origin && origin !== url.origin) {
      throw new HttpError(403, "origin_not_allowed");
    }
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Community-Admin-Token, X-Community-Test-Token",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
        ...(origin ? { "Access-Control-Allow-Origin": origin } : {}),
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
      },
    });
  }
  if (path === "/" && method === "GET") {
    return jsonResponse({ service: "kfps-community-library", protocol: 1, status: "ok" });
  }
  if (path === "/admin" && method === "GET") return new Response(ADMIN_HTML, { headers: HTML_HEADERS });
  if (path === "/v1/health" && method === "GET") {
    return jsonResponse({ service: "kfps-community-library", protocol: 1, status: "ok" });
  }
  if (path === "/v1/config" && method === "GET") {
    const versionPolicy = await getVersionPolicy(env);
    return jsonResponse({
      protocol: 1,
      categories: CATEGORIES,
      games: GAMES,
      licenses: LICENSES,
      classifications: CLASSIFICATIONS,
      sorts: ["featured", "trending", "new", "downloads", "favorites", "name"],
      scopes: ["featured", "browse", "supporters", "favorites", "following", "mine"],
      featured_artwork_limit: FEATURED_ARTWORK_LIMIT,
      minimum_upload_version: effectiveMinimumUploadVersion(env, versionPolicy),
      modern_upload_client_required: env.REQUIRE_MODERN_UPLOAD_CLIENT !== "0",
      version_sync: publicVersionPolicy(versionPolicy),
      page_size: 24,
      github_client_id: env.GITHUB_CLIENT_ID || "",
      test_auth: env.ALLOW_TEST_AUTH === "1",
      deployment_environment: env.DEPLOYMENT_ENVIRONMENT || "production",
      username: { minimum: 3, maximum: 24, immutable: true, pattern: "letters, numbers, underscores" },
      upload: {
        maximum_shapes: 3001,
        maximum_json_bytes: 24 * 1024 * 1024,
        maximum_preview_bytes: 2 * 1024 * 1024,
        maximum_thumbnail_bytes: 512 * 1024,
      },
    }, 200, { "Cache-Control": "public, max-age=300" });
  }

  if (path === "/v1/auth/test" && method === "POST") return handleTestAuth(request, env);
  if (path === "/v1/auth/github" && method === "POST") return handleGitHubAuth(request, env);
  if (path === "/v1/session" && method === "GET") return handleSession(request, env);
  if (path === "/v1/session" && method === "DELETE") return handleSignOut(request, env);
  if (path === "/v1/profile/username" && method === "POST") return handleChooseUsername(request, env);
  if (path === "/v1/profile" && method === "PATCH") return handleUpdateProfile(request, env);
  if (path === "/v1/profile/ignored" && method === "GET") return handleIgnoredCreators(request, env);
  if (path === "/v1/supporter/verify" && method === "POST") return handleVerifySupporter(request, env);
  if (path === "/v1/supporter/verify" && method === "DELETE") return handleClearSupporter(request, env);

  if (path === "/v1/artworks" && method === "GET") return handleListArtworks(request, env);
  if (path === "/v1/artworks" && method === "POST") return handleCreateArtwork(request, env, ctx);

  let match = pathMatch(path, /^\/v1\/artworks\/([^/]+)$/);
  if (match && method === "GET") return handleArtworkDetail(request, env, match[0]!);
  if (match && method === "PATCH") return handleUpdateArtworkMetadata(request, env, match[0]!);
  if (match && method === "DELETE") return handleRemoveArtwork(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/preview$/);
  if (match && method === "GET") return handleArtworkAsset(request, env, ctx, match[0]!, "preview");
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/thumbnail$/);
  if (match && method === "GET") return handleArtworkAsset(request, env, ctx, match[0]!, "thumbnail");
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/download$/);
  if (match && method === "GET") return handleArtworkAsset(request, env, ctx, match[0]!, "download");
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/favorite$/);
  if (match && method === "POST") return handleFavorite(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/report$/);
  if (match && method === "POST") return handleReport(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/artworks\/([^/]+)\/revisions$/);
  if (match && method === "POST") return handleCreateRevision(request, env, ctx, match[0]!);

  match = pathMatch(path, /^\/v1\/creators\/([^/]+)$/);
  if (match && method === "GET") return handleCreator(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/creators\/([^/]+)\/follow$/);
  if (match && method === "POST") return handleFollow(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/creators\/([^/]+)\/ignore$/);
  if (match && method === "POST") return handleIgnore(request, env, match[0]!);

  if (path === "/v1/admin/queue" && method === "GET") return handleAdminQueue(request, env);
  if (path === "/v1/admin/reports" && method === "GET") return handleAdminReports(request, env);
  if (path === "/v1/admin/reports/resolve" && method === "POST") return handleAdminResolveReport(request, env);
  if (path === "/v1/admin/moderate" && method === "POST") return handleAdminModerate(request, env);
  if (path === "/v1/admin/users/action" && method === "POST") return handleAdminUserAction(request, env);
  if (path === "/v1/admin/version" && method === "GET") return handleAdminVersionStatus(request, env);
  if (path === "/v1/admin/version" && method === "POST") return handleAdminVersionAction(request, env);
  if (path === "/v1/admin/rerender" && method === "GET") return handleAdminRerenderQueue(request, env);
  match = pathMatch(path, /^\/v1\/admin\/artworks\/([^/]+)\/preview$/);
  if (match && method === "GET") return handleAdminAsset(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/admin\/artworks\/([^/]+)\/design$/);
  if (match && method === "GET") return handleAdminDesign(request, env, match[0]!);
  match = pathMatch(path, /^\/v1\/admin\/artworks\/([^/]+)\/rendered-assets$/);
  if (match && method === "POST") return handleAdminReplaceRenderedAssets(request, env, ctx, match[0]!);

  throw new HttpError(404, "not_found");
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      const response = await route(request, env, ctx);
      const headers = new Headers(response.headers);
      const requestOrigin = request.headers.get("Origin");
      if (requestOrigin === new URL(request.url).origin) {
        headers.set("Access-Control-Allow-Origin", requestOrigin);
        const vary = headers.get("Vary") || "";
        if (!vary.split(",").some((value) => value.trim().toLowerCase() === "origin")) {
          headers.set("Vary", vary ? `${vary}, Origin` : "Origin");
        }
      }
      headers.set("X-Community-Protocol", env.API_PROTOCOL || "1");
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
    } catch (error) {
      return errorResponse(error);
    }
  },

  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = new Date().toISOString();
    const oldWindow = Math.floor(Date.now() / 1000) - 48 * 60 * 60;
    ctx.waitUntil(env.DB.batch([
      env.DB.prepare("DELETE FROM sessions WHERE expires_at <= ?1").bind(now),
      env.DB.prepare("DELETE FROM rate_limits WHERE window_start < ?1").bind(oldWindow),
      env.DB.prepare("DELETE FROM download_events WHERE day_bucket < ?1").bind(Math.floor(Date.now() / 86_400_000) - 45),
    ]).then(() => undefined));
    ctx.waitUntil(syncVersionPolicy(env, { reason: "scheduled" }).then(() => undefined).catch((error) => {
      console.error("KFPS VERSION synchronization failed", error);
    }));
  },
};
