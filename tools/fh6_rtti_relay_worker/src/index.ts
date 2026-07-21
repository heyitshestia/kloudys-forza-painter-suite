import { authenticateAdmin } from "./admin_auth";
import { randomToken, sha256Hex } from "./protocol";
import { MAX_PROFILES, normalizeProfile, normalizeRegistry, REGISTRY_FORMAT, type NormalizedProfile } from "./registry";

interface Env {
  DB: D1Database;
  ADMIN_HMAC_SECRET: string;
}

interface HelperRow {
  helper_id: string;
  name: string;
  status: "active" | "revoked";
  enrollment_expires_at: string | null;
  enrollment_used_at: string | null;
  device_id: string | null;
  submit_count: number;
  reject_count: number;
  last_submit_at: string | null;
  created_at: string;
  updated_at: string;
  campaign_id: string | null;
  campaign_name: string | null;
}

interface CampaignRow {
  campaign_id: string;
  name: string;
  status: "active" | "revoked";
  expires_at: string;
  max_devices: number;
  enrolled_count: number;
  created_at: string;
  updated_at: string;
}

const MAX_BODY_BYTES = 64 * 1024;
const SUBMISSION_WINDOW_MINUTES = 30;
const SUBMISSION_LIMIT = 20;

function json(value: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...headers,
    },
  });
}

async function bodyText(request: Request): Promise<string> {
  const declared = Number(request.headers.get("Content-Length") || 0);
  if (declared > MAX_BODY_BYTES) throw new Error("request body is too large");
  const body = await request.text();
  if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) throw new Error("request body is too large");
  return body;
}

function parseObject(rawBody: string): Record<string, unknown> {
  const value = JSON.parse(rawBody) as unknown;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("request body must be an object");
  return value as Record<string, unknown>;
}

function validDeviceId(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

async function tokenHash(value: string): Promise<string> {
  return sha256Hex(new TextEncoder().encode(value));
}

async function registryResponse(env: Env, request: Request): Promise<Response> {
  const result = await env.DB.prepare(
    "SELECT profile_json FROM profiles ORDER BY updated_at DESC, profile_id ASC LIMIT ?1",
  ).bind(MAX_PROFILES).all<{ profile_json: string }>();
  const state = await env.DB.prepare("SELECT updated_at FROM registry_state WHERE singleton = 1").first<{ updated_at: string }>();
  const profiles = result.results.map((row) => JSON.parse(row.profile_json) as NormalizedProfile);
  const registry = { format: REGISTRY_FORMAT, updated_utc: state?.updated_at || "", profiles };
  const payload = `${JSON.stringify(registry, null, 2)}\n`;
  const etag = `\"${await tokenHash(payload)}\"`;
  if (request.headers.get("If-None-Match") === etag) return new Response(null, { status: 304, headers: { ETag: etag } });
  return new Response(payload, {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=60, stale-if-error=86400",
      "ETag": etag,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function enroll(env: Env, request: Request): Promise<Response> {
  let body: Record<string, unknown>;
  try {
    body = parseObject(await bodyText(request));
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "invalid request" }, 400);
  }
  if (body.protocol !== 1 || !validDeviceId(body.device_id)) {
    return json({ error: "invalid enrollment request" }, 400);
  }
  const oneTimeCode = typeof body.enrollment_code === "string" ? body.enrollment_code : "";
  const autoCode = typeof body.auto_enrollment_code === "string" ? body.auto_enrollment_code : "";
  if (Boolean(oneTimeCode) === Boolean(autoCode)) return json({ error: "invalid enrollment request" }, 400);
  const enrollmentCode = oneTimeCode || autoCode;
  if (!/^[A-Za-z0-9_-]{40,128}$/.test(enrollmentCode)) return json({ error: "invalid enrollment request" }, 400);
  const enrollmentHash = await tokenHash(enrollmentCode);
  if (autoCode) return autoEnroll(env, enrollmentHash, body.device_id);

  const helper = await env.DB.prepare(
    "SELECT helper_id, status, enrollment_expires_at, enrollment_used_at FROM helpers WHERE enrollment_hash = ?1",
  ).bind(enrollmentHash).first<{ helper_id: string; status: string; enrollment_expires_at: string | null; enrollment_used_at: string | null }>();
  const now = new Date().toISOString();
  if (!helper || helper.status !== "active" || helper.enrollment_used_at || !helper.enrollment_expires_at || helper.enrollment_expires_at <= now) {
    return json({ error: "enrollment code is invalid, expired, or already used" }, 403);
  }
  const credential = randomToken(48);
  const credentialHash = await tokenHash(credential);
  const updated = await env.DB.prepare(
    `UPDATE helpers SET device_id = ?1, credential_hash = ?2, enrollment_used_at = ?3, updated_at = ?3
     WHERE helper_id = ?4 AND status = 'active' AND enrollment_used_at IS NULL AND enrollment_hash = ?5`,
  ).bind(body.device_id, credentialHash, now, helper.helper_id, enrollmentHash).run();
  if (updated.meta.changes !== 1) return json({ error: "enrollment code was already used" }, 409);
  return json({ protocol: 1, helper_id: helper.helper_id, credential });
}

async function autoEnroll(env: Env, codeHash: string, deviceId: string): Promise<Response> {
  const campaign = await env.DB.prepare(
    `SELECT campaign_id, name, status, expires_at, max_devices, enrolled_count, created_at, updated_at
       FROM auto_enrollment_campaigns WHERE code_hash = ?1`,
  ).bind(codeHash).first<CampaignRow>();
  const now = new Date().toISOString();
  if (!campaign || campaign.status !== "active" || campaign.expires_at <= now || campaign.enrolled_count >= campaign.max_devices) {
    return json({ error: "automatic enrollment is unavailable, expired, or full" }, 403);
  }
  const existing = await env.DB.prepare(
    "SELECT helper_id FROM helpers WHERE campaign_id = ?1 AND device_id = ?2",
  ).bind(campaign.campaign_id, deviceId).first<{ helper_id: string }>();
  if (existing) return json({ error: "this device already enrolled; restore or reset it from the administrator console" }, 409);

  const helperId = crypto.randomUUID();
  const credential = randomToken(48);
  const credentialHash = await tokenHash(credential);
  const name = `Auto helper ${deviceId.slice(0, 8)}`;
  const results = await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO helpers(
         helper_id, name, status, enrollment_used_at, device_id, credential_hash,
         campaign_id, created_at, updated_at
       )
       SELECT ?1, ?2, 'active', ?3, ?4, ?5, campaign_id, ?3, ?3
       FROM auto_enrollment_campaigns
       WHERE campaign_id = ?6 AND code_hash = ?7 AND status = 'active'
         AND expires_at > ?3 AND enrolled_count < max_devices`,
    ).bind(helperId, name, now, deviceId, credentialHash, campaign.campaign_id, codeHash),
    env.DB.prepare(
      `UPDATE auto_enrollment_campaigns
       SET enrolled_count = (SELECT COUNT(*) FROM helpers WHERE campaign_id = ?1), updated_at = ?2
       WHERE campaign_id = ?1`,
    ).bind(campaign.campaign_id, now),
  ]);
  if (results[0].meta.changes !== 1) return json({ error: "automatic enrollment is unavailable, expired, or full" }, 403);
  return json({ protocol: 1, helper_id: helperId, credential, auto_enrolled: true });
}

async function authenticatedHelper(env: Env, request: Request, deviceId: unknown): Promise<HelperRow | null> {
  const authorization = request.headers.get("Authorization") || "";
  const match = /^Bearer ([A-Za-z0-9_-]{60,128})$/.exec(authorization);
  if (!match || !validDeviceId(deviceId)) return null;
  const hash = await tokenHash(match[1]);
  return env.DB.prepare(
    `SELECT helpers.helper_id, helpers.name, helpers.status, helpers.enrollment_expires_at,
            helpers.enrollment_used_at, helpers.device_id, helpers.submit_count, helpers.reject_count,
            helpers.last_submit_at, helpers.created_at, helpers.updated_at, helpers.campaign_id,
            auto_enrollment_campaigns.name AS campaign_name
       FROM helpers
       LEFT JOIN auto_enrollment_campaigns ON auto_enrollment_campaigns.campaign_id = helpers.campaign_id
       WHERE helpers.credential_hash = ?1 AND helpers.device_id = ?2`,
  ).bind(hash, deviceId).first<HelperRow>();
}

async function recordRejection(env: Env, helper: HelperRow, reason: string): Promise<void> {
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO submissions(submission_id, helper_id, accepted, reason, created_at) VALUES (?1, ?2, 0, ?3, ?4)",
    ).bind(crypto.randomUUID(), helper.helper_id, reason.slice(0, 160), now),
    env.DB.prepare("UPDATE helpers SET reject_count = reject_count + 1, updated_at = ?1 WHERE helper_id = ?2").bind(now, helper.helper_id),
  ]);
}

async function submitProfile(env: Env, request: Request): Promise<Response> {
  let body: Record<string, unknown>;
  try {
    body = parseObject(await bodyText(request));
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "invalid request" }, 400);
  }
  const helper = await authenticatedHelper(env, request, body.device_id);
  if (!helper) return json({ error: "invalid helper credential" }, 401);
  if (helper.status !== "active") return json({ error: "helper access is revoked" }, 403);
  if (body.protocol !== 1) {
    await recordRejection(env, helper, "unsupported protocol");
    return json({ error: "unsupported protocol" }, 400);
  }
  const recent = await env.DB.prepare(
    `SELECT COUNT(*) AS count FROM submissions
     WHERE helper_id = ?1 AND datetime(created_at) >= datetime('now', '-${SUBMISSION_WINDOW_MINUTES} minutes')`,
  ).bind(helper.helper_id).first<{ count: number }>();
  if (Number(recent?.count || 0) >= SUBMISSION_LIMIT) return json({ error: "please wait before submitting again" }, 429);

  let profile: NormalizedProfile;
  try {
    profile = await normalizeProfile(body.profile, true);
  } catch (error) {
    const reason = error instanceof Error ? error.message : "invalid profile";
    await recordRejection(env, helper, reason);
    return json({ error: reason }, 400);
  }
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO profiles(profile_id, profile_json, helper_id, created_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?4)
       ON CONFLICT(profile_id) DO UPDATE SET profile_json = excluded.profile_json,
         helper_id = excluded.helper_id, updated_at = excluded.updated_at`,
    ).bind(profile.profile_id, JSON.stringify(profile), helper.helper_id, now),
    env.DB.prepare(
      "INSERT INTO submissions(submission_id, helper_id, profile_id, accepted, reason, created_at) VALUES (?1, ?2, ?3, 1, 'accepted', ?4)",
    ).bind(crypto.randomUUID(), helper.helper_id, profile.profile_id, now),
    env.DB.prepare(
      "UPDATE helpers SET submit_count = submit_count + 1, last_submit_at = ?1, updated_at = ?1 WHERE helper_id = ?2",
    ).bind(now, helper.helper_id),
    env.DB.prepare(
      `INSERT INTO registry_state(singleton, updated_at) VALUES (1, ?1)
       ON CONFLICT(singleton) DO UPDATE SET updated_at = excluded.updated_at`,
    ).bind(now),
  ]);
  return json({ accepted: true, profile_id: profile.profile_id, updated_utc: now });
}

async function authenticateAdminRequest(env: Env, request: Request, rawBody: string): Promise<{ requestId: string } | Response> {
  const auth = await authenticateAdmin(request, rawBody, env.ADMIN_HMAC_SECRET || "");
  if (!auth.ok) return json({ error: auth.error || "unauthorized" }, 401);
  const inserted = await env.DB.prepare(
    "INSERT OR IGNORE INTO admin_events(request_id, action, created_at) VALUES (?1, ?2, ?3)",
  ).bind(auth.requestId, new URL(request.url).pathname, new Date().toISOString()).run();
  if (inserted.meta.changes !== 1) return json({ error: "admin request was already used" }, 409);
  return { requestId: auth.requestId };
}

async function adminRoute(env: Env, request: Request, path: string): Promise<Response> {
  let rawBody = "";
  try {
    rawBody = request.method === "GET" ? "" : await bodyText(request);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "invalid request" }, 400);
  }
  const auth = await authenticateAdminRequest(env, request, rawBody);
  if (auth instanceof Response) return auth;

  if (request.method === "GET" && path === "/v1/admin/helpers") {
    const result = await env.DB.prepare(
      `SELECT helpers.helper_id, helpers.name, helpers.status, helpers.enrollment_expires_at,
              helpers.enrollment_used_at, helpers.device_id, helpers.submit_count, helpers.reject_count,
              helpers.last_submit_at, helpers.created_at, helpers.updated_at, helpers.campaign_id,
              auto_enrollment_campaigns.name AS campaign_name
       FROM helpers
       LEFT JOIN auto_enrollment_campaigns ON auto_enrollment_campaigns.campaign_id = helpers.campaign_id
       ORDER BY helpers.created_at DESC LIMIT 500`,
    ).all<HelperRow>();
    return json({ helpers: result.results });
  }
  if (request.method === "GET" && path === "/v1/admin/campaigns") {
    const result = await env.DB.prepare(
      `SELECT campaign_id, name, status, expires_at, max_devices, enrolled_count, created_at, updated_at
       FROM auto_enrollment_campaigns ORDER BY created_at DESC LIMIT 100`,
    ).all<CampaignRow>();
    return json({ campaigns: result.results });
  }
  if (request.method === "GET" && path === "/v1/admin/submissions") {
    const limit = Math.min(500, Math.max(1, Number(new URL(request.url).searchParams.get("limit") || 100)));
    const result = await env.DB.prepare(
      `SELECT submissions.submission_id, submissions.helper_id, helpers.name AS helper_name,
              submissions.profile_id, submissions.accepted, submissions.reason, submissions.created_at
       FROM submissions JOIN helpers ON helpers.helper_id = submissions.helper_id
       ORDER BY submissions.created_at DESC LIMIT ?1`,
    ).bind(limit).all();
    return json({ submissions: result.results });
  }

  let body: Record<string, unknown>;
  try {
    body = parseObject(rawBody);
  } catch (error) {
    return json({ error: error instanceof Error ? error.message : "invalid request" }, 400);
  }
  if (request.method === "POST" && path === "/v1/admin/helpers/create") {
    const name = String(body.name ?? "").trim();
    const expiresDays = Number(body.expires_days ?? 7);
    if (!name || name.length > 80 || !Number.isInteger(expiresDays) || expiresDays < 1 || expiresDays > 30) {
      return json({ error: "helper name or enrollment lifetime is invalid" }, 400);
    }
    const helperId = crypto.randomUUID();
    const enrollmentCode = randomToken(32);
    const enrollmentHash = await tokenHash(enrollmentCode);
    const now = new Date();
    const expires = new Date(now.getTime() + expiresDays * 86400000).toISOString();
    await env.DB.prepare(
      `INSERT INTO helpers(helper_id, name, enrollment_hash, enrollment_expires_at, created_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?5)`,
    ).bind(helperId, name, enrollmentHash, expires, now.toISOString()).run();
    return json({ helper_id: helperId, name, enrollment_code: enrollmentCode, enrollment_expires_at: expires }, 201);
  }
  if (request.method === "POST" && path === "/v1/admin/helpers/mutate") {
    const helperId = String(body.helper_id ?? "");
    const action = String(body.action ?? "");
    if (!/^[0-9a-f-]{36}$/.test(helperId)) return json({ error: "invalid helper id" }, 400);
    const now = new Date().toISOString();
    if (action === "rename") {
      const name = String(body.name ?? "").trim();
      if (!name || name.length > 80) return json({ error: "helper name is invalid" }, 400);
      const result = await env.DB.prepare("UPDATE helpers SET name = ?1, updated_at = ?2 WHERE helper_id = ?3")
        .bind(name, now, helperId).run();
      if (result.meta.changes !== 1) return json({ error: "helper not found" }, 404);
      return json({ helper_id: helperId, name });
    }
    if (action === "revoke" || action === "restore") {
      const status = action === "revoke" ? "revoked" : "active";
      const result = await env.DB.prepare("UPDATE helpers SET status = ?1, updated_at = ?2 WHERE helper_id = ?3")
        .bind(status, now, helperId).run();
      if (result.meta.changes !== 1) return json({ error: "helper not found" }, 404);
      return json({ helper_id: helperId, status });
    }
    if (action === "reset_enrollment") {
      const enrollmentCode = randomToken(32);
      const hash = await tokenHash(enrollmentCode);
      const expires = new Date(Date.now() + 7 * 86400000).toISOString();
      const result = await env.DB.prepare(
        `UPDATE helpers SET status = 'active', enrollment_hash = ?1, enrollment_expires_at = ?2,
         enrollment_used_at = NULL, device_id = NULL, credential_hash = NULL, updated_at = ?3 WHERE helper_id = ?4`,
      ).bind(hash, expires, now, helperId).run();
      if (result.meta.changes !== 1) return json({ error: "helper not found" }, 404);
      return json({ helper_id: helperId, status: "active", enrollment_code: enrollmentCode, enrollment_expires_at: expires });
    }
    return json({ error: "unsupported helper action" }, 400);
  }
  if (request.method === "POST" && path === "/v1/admin/campaigns/create") {
    const name = String(body.name ?? "").trim();
    const expiresDays = Number(body.expires_days ?? 180);
    const maxDevices = Number(body.max_devices ?? 10);
    if (!name || name.length > 80 || !Number.isInteger(expiresDays) || expiresDays < 1 || expiresDays > 3650
        || !Number.isInteger(maxDevices) || maxDevices < 1 || maxDevices > 500) {
      return json({ error: "campaign name, expiry, or device limit is invalid" }, 400);
    }
    const campaignId = crypto.randomUUID();
    const autoEnrollmentCode = randomToken(48);
    const codeHash = await tokenHash(autoEnrollmentCode);
    const now = new Date();
    const expires = new Date(now.getTime() + expiresDays * 86400000).toISOString();
    await env.DB.prepare(
      `INSERT INTO auto_enrollment_campaigns(
         campaign_id, name, code_hash, expires_at, max_devices, created_at, updated_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?6)`,
    ).bind(campaignId, name, codeHash, expires, maxDevices, now.toISOString()).run();
    return json({
      campaign_id: campaignId, name, status: "active", auto_enrollment_code: autoEnrollmentCode,
      expires_at: expires, max_devices: maxDevices, enrolled_count: 0,
    }, 201);
  }
  if (request.method === "POST" && path === "/v1/admin/campaigns/mutate") {
    const campaignId = String(body.campaign_id ?? "");
    const action = String(body.action ?? "");
    if (!/^[0-9a-f-]{36}$/.test(campaignId)) return json({ error: "invalid campaign id" }, 400);
    const now = new Date().toISOString();
    if (action === "revoke" || action === "restore") {
      const status = action === "revoke" ? "revoked" : "active";
      const result = await env.DB.prepare(
        "UPDATE auto_enrollment_campaigns SET status = ?1, updated_at = ?2 WHERE campaign_id = ?3",
      ).bind(status, now, campaignId).run();
      if (result.meta.changes !== 1) return json({ error: "campaign not found" }, 404);
      return json({ campaign_id: campaignId, status });
    }
    if (action === "rotate") {
      const autoEnrollmentCode = randomToken(48);
      const hash = await tokenHash(autoEnrollmentCode);
      const result = await env.DB.prepare(
        "UPDATE auto_enrollment_campaigns SET code_hash = ?1, status = 'active', updated_at = ?2 WHERE campaign_id = ?3",
      ).bind(hash, now, campaignId).run();
      if (result.meta.changes !== 1) return json({ error: "campaign not found" }, 404);
      return json({ campaign_id: campaignId, status: "active", auto_enrollment_code: autoEnrollmentCode });
    }
    return json({ error: "unsupported campaign action" }, 400);
  }
  if (request.method === "POST" && path === "/v1/admin/registry/bootstrap") {
    let registry;
    try {
      registry = await normalizeRegistry(body.registry);
    } catch (error) {
      return json({ error: error instanceof Error ? error.message : "invalid registry" }, 400);
    }
    const now = new Date().toISOString();
    const statements = registry.profiles.map((profile) => env.DB.prepare(
      `INSERT INTO profiles(profile_id, profile_json, helper_id, created_at, updated_at)
       VALUES (?1, ?2, NULL, ?3, ?3)
       ON CONFLICT(profile_id) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at`,
    ).bind(profile.profile_id, JSON.stringify(profile), now));
    statements.push(env.DB.prepare(
      `INSERT INTO registry_state(singleton, updated_at) VALUES (1, ?1)
       ON CONFLICT(singleton) DO UPDATE SET updated_at = excluded.updated_at`,
    ).bind(now));
    await env.DB.batch(statements);
    return json({ imported: registry.profiles.length, updated_utc: now });
  }
  return json({ error: "not found" }, 404);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    try {
      if (request.method === "GET" && path === "/v1/health") {
        return json({ service: "kfps-fh6-rtti-registry", protocol: 1, status: "ok" });
      }
      if (request.method === "GET" && (path === "/v1/RTTI.dat" || path === "/RTTI.dat")) {
        return registryResponse(env, request);
      }
      if (request.method === "POST" && path === "/v1/enroll") return enroll(env, request);
      if (request.method === "POST" && path === "/v1/submit") return submitProfile(env, request);
      if (path.startsWith("/v1/admin/")) return adminRoute(env, request, path);
      return json({ error: "not found" }, 404);
    } catch (error) {
      return json({ error: "service error" }, 500);
    }
  },
};
