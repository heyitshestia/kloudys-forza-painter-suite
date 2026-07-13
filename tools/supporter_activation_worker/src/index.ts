import { authenticateAdmin } from "./admin_auth";
import { encryptKofiEvent, parseKofiPayload, validKofiToken } from "./kofi_inbox";
import { base64UrlToBytes, sha256Hex, signDecision, signReceipt, signStatus } from "./protocol";

export interface Env {
  DB: D1Database;
  ACTIVATION_PRIVATE_KEY_PEM: string;
  ADMIN_HMAC_SECRET: string;
  ACTIVATION_KEY_ID: string;
  KOFI_VERIFICATION_TOKEN: string;
  KOFI_INBOX_PUBLIC_KEY_PEM: string;
}

interface ActivationRequest {
  protocol: 1;
  key_id: string;
  key_proof: string;
  device_id: string;
  nonce: string;
}

interface LicenseRow {
  key_id: string;
  signature_sha256: string;
  status: "active" | "revoked";
  device_id: string | null;
  activated_at: string | null;
  conflict_count: number;
  first_conflict_at: string | null;
  last_conflict_at: string | null;
  reset_count: number;
  last_reset_at: string | null;
  created_at: string;
  updated_at: string;
}

type AdminLicenseAction = "reset" | "revoke" | "restore" | "clear_conflicts";

const JSON_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json; charset=utf-8",
  "X-Content-Type-Options": "nosniff",
};
const MAX_PUBLIC_BODY = 8192;
const MAX_ADMIN_BODY = 256 * 1024;
const MAX_KOFI_BODY = 64 * 1024;
const HEX_64 = /^[0-9a-f]{64}$/;

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function errorResponse(status: number, code: string): Response {
  return jsonResponse({ error: code }, status);
}

function hasExactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

async function readBody(request: Request, maximum: number): Promise<string> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > maximum) throw new Error("request body too large");
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.length > maximum) throw new Error("request body too large");
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function parseActivationRequest(raw: string): ActivationRequest {
  const value = JSON.parse(raw) as Record<string, unknown>;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid request");
  if (!hasExactKeys(value, ["protocol", "key_id", "key_proof", "device_id", "nonce"])) throw new Error("invalid fields");
  if (value.protocol !== 1 || typeof value.key_id !== "string" || !HEX_64.test(value.key_id)) throw new Error("invalid key id");
  if (typeof value.device_id !== "string" || !HEX_64.test(value.device_id)) throw new Error("invalid device id");
  if (typeof value.key_proof !== "string" || typeof value.nonce !== "string") throw new Error("invalid proof or nonce");
  const proof = base64UrlToBytes(value.key_proof);
  const nonce = base64UrlToBytes(value.nonce);
  if (proof.length !== 384 || nonce.length < 16 || nonce.length > 64) throw new Error("invalid proof or nonce length");
  return value as unknown as ActivationRequest;
}

async function signedDecision(
  env: Env,
  request: ActivationRequest,
  status: string,
  decidedAt: string,
  httpStatus: number,
): Promise<Response> {
  const decision = await signDecision(
    env.ACTIVATION_PRIVATE_KEY_PEM,
    env.ACTIVATION_KEY_ID,
    status,
    request.key_id,
    request.device_id,
    request.nonce,
    decidedAt,
  );
  return jsonResponse({ status, decision }, httpStatus);
}

async function handleActivate(request: Request, env: Env): Promise<Response> {
  if ((request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    return errorResponse(415, "content_type_required");
  }
  let activation: ActivationRequest;
  try {
    activation = parseActivationRequest(await readBody(request, MAX_PUBLIC_BODY));
  } catch {
    return errorResponse(400, "invalid_request");
  }

  const now = new Date().toISOString();
  const proofHash = await sha256Hex(base64UrlToBytes(activation.key_proof));
  const claimed = await env.DB.prepare(
    `UPDATE licenses
       SET device_id = CASE WHEN device_id IS NULL THEN ?2 ELSE device_id END,
           activated_at = COALESCE(activated_at, ?3),
           updated_at = ?3
     WHERE key_id = ?1
       AND signature_sha256 = ?4
       AND status = 'active'
       AND (device_id IS NULL OR device_id = ?2)
     RETURNING key_id, device_id, activated_at`,
  ).bind(activation.key_id, activation.device_id, now, proofHash).first<Pick<LicenseRow, "key_id" | "device_id" | "activated_at">>();

  if (claimed?.device_id && claimed.activated_at) {
    const receipt = await signReceipt(
      env.ACTIVATION_PRIVATE_KEY_PEM,
      env.ACTIVATION_KEY_ID,
      activation.key_id,
      activation.device_id,
      claimed.activated_at,
    );
    return jsonResponse({ status: "active", receipt });
  }

  const row = await env.DB.prepare(
    "SELECT status, device_id, signature_sha256 FROM licenses WHERE key_id = ?1 LIMIT 1",
  ).bind(activation.key_id).first<Pick<LicenseRow, "status" | "device_id" | "signature_sha256">>();

  if (row && row.status === "active" && row.signature_sha256 === proofHash && row.device_id && row.device_id !== activation.device_id) {
    await env.DB.prepare(
      `UPDATE licenses
          SET conflict_count = conflict_count + 1,
              first_conflict_at = COALESCE(first_conflict_at, ?2),
              last_conflict_at = ?2,
              updated_at = ?2
        WHERE key_id = ?1`,
    ).bind(activation.key_id, now).run();
    return signedDecision(env, activation, "already_activated", now, 409);
  }

  if (row && row.status === "revoked" && row.signature_sha256 === proofHash) {
    return signedDecision(env, activation, "not_eligible", now, 403);
  }
  return errorResponse(403, "not_eligible");
}

async function handleDeactivate(request: Request, env: Env): Promise<Response> {
  if ((request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    return errorResponse(415, "content_type_required");
  }
  let activation: ActivationRequest;
  try {
    activation = parseActivationRequest(await readBody(request, MAX_PUBLIC_BODY));
  } catch {
    return errorResponse(400, "invalid_request");
  }
  const now = new Date().toISOString();
  const proofHash = await sha256Hex(base64UrlToBytes(activation.key_proof));
  const result = await env.DB.prepare(
    `UPDATE licenses
        SET device_id = NULL,
            activated_at = NULL,
            reset_count = reset_count + 1,
            last_reset_at = ?4,
            updated_at = ?4
      WHERE key_id = ?1
        AND signature_sha256 = ?2
        AND status = 'active'
        AND device_id = ?3`,
  ).bind(activation.key_id, proofHash, activation.device_id, now).run();
  if ((result.meta.changes || 0) === 1) return signedDecision(env, activation, "deactivated", now, 200);
  const row = await env.DB.prepare(
    "SELECT signature_sha256 FROM licenses WHERE key_id = ?1 LIMIT 1",
  ).bind(activation.key_id).first<Pick<LicenseRow, "signature_sha256">>();
  if (row?.signature_sha256 === proofHash) {
    return signedDecision(env, activation, "not_eligible", now, 403);
  }
  return errorResponse(403, "not_eligible");
}

async function handleStatus(request: Request, env: Env): Promise<Response> {
  if ((request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    return errorResponse(415, "content_type_required");
  }
  let activation: ActivationRequest;
  try {
    activation = parseActivationRequest(await readBody(request, MAX_PUBLIC_BODY));
  } catch {
    return errorResponse(400, "invalid_request");
  }

  const proofHash = await sha256Hex(base64UrlToBytes(activation.key_proof));
  const row = await env.DB.prepare(
    "SELECT status, signature_sha256 FROM licenses WHERE key_id = ?1 LIMIT 1",
  ).bind(activation.key_id).first<Pick<LicenseRow, "status" | "signature_sha256">>();
  if (!row || row.signature_sha256 !== proofHash) return errorResponse(403, "not_eligible");

  const checkedAt = new Date().toISOString();
  const status = row.status === "revoked" ? "revoked" : "active";
  const decision = await signStatus(
    env.ACTIVATION_PRIVATE_KEY_PEM,
    env.ACTIVATION_KEY_ID,
    status,
    activation.key_id,
    activation.device_id,
    activation.nonce,
    checkedAt,
  );
  return jsonResponse({ status, decision });
}

async function handleKofiWebhook(request: Request, env: Env): Promise<Response> {
  const contentType = (request.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("application/x-www-form-urlencoded") && !contentType.includes("application/json")) {
    return errorResponse(415, "content_type_required");
  }
  let rawBody: string;
  let payload: Record<string, unknown>;
  try {
    rawBody = await readBody(request, MAX_KOFI_BODY);
    payload = parseKofiPayload(rawBody, contentType);
  } catch {
    return errorResponse(400, "invalid_webhook");
  }
  if (!validKofiToken(payload, env.KOFI_VERIFICATION_TOKEN || "")) {
    return errorResponse(403, "invalid_webhook");
  }
  const encrypted = await encryptKofiEvent(payload, env.KOFI_INBOX_PUBLIC_KEY_PEM || "");
  const now = new Date().toISOString();
  await env.DB.prepare(
    "INSERT OR IGNORE INTO kofi_inbox(event_id, payload_encrypted, received_at) VALUES (?1, ?2, ?3)",
  ).bind(encrypted.eventId, JSON.stringify(encrypted.payload), now).run();
  return jsonResponse({ status: "accepted" });
}

async function recordAdminMutation(env: Env, requestId: string, action: string, keyId = ""): Promise<boolean> {
  const result = await env.DB.prepare(
    "INSERT OR IGNORE INTO admin_events(request_id, action, key_id, created_at) VALUES (?1, ?2, ?3, ?4)",
  ).bind(requestId, action, keyId, new Date().toISOString()).run();
  return (result.meta.changes || 0) === 1;
}

async function authenticateAdminRequest(request: Request, env: Env, rawBody: string): Promise<string | Response> {
  const auth = await authenticateAdmin(request, rawBody, env.ADMIN_HMAC_SECRET || "");
  if (!auth.ok) return errorResponse(401, "admin_auth_failed");
  return auth.requestId;
}

function publicLicense(row: LicenseRow): Record<string, unknown> {
  return {
    key_id: row.key_id,
    signature_sha256: row.signature_sha256,
    status: row.status,
    registered: Boolean(row.device_id),
    device_id_prefix: row.device_id ? row.device_id.slice(0, 12) : "",
    activated_at: row.activated_at,
    conflict_count: row.conflict_count,
    first_conflict_at: row.first_conflict_at,
    last_conflict_at: row.last_conflict_at,
    reset_count: row.reset_count,
    last_reset_at: row.last_reset_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function handleAdminList(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const after = url.searchParams.get("after") || "";
  const requestedLimit = Number(url.searchParams.get("limit") || "250");
  const limit = Number.isInteger(requestedLimit) ? Math.max(1, Math.min(500, requestedLimit)) : 250;
  if (after && !HEX_64.test(after)) return errorResponse(400, "invalid_cursor");
  const result = await env.DB.prepare(
    `SELECT * FROM licenses
      WHERE key_id > ?1
      ORDER BY key_id
      LIMIT ?2`,
  ).bind(after, limit + 1).all<LicenseRow>();
  const rows = result.results || [];
  const hasMore = rows.length > limit;
  const visible = rows.slice(0, limit);
  return jsonResponse({
    licenses: visible.map(publicLicense),
    next_after: hasMore && visible.length ? visible[visible.length - 1].key_id : "",
  });
}

async function handleAdminKofiList(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const after = url.searchParams.get("after") || "";
  const requestedLimit = Number(url.searchParams.get("limit") || "100");
  const limit = Number.isInteger(requestedLimit) ? Math.max(1, Math.min(100, requestedLimit)) : 100;
  if (after && !HEX_64.test(after)) return errorResponse(400, "invalid_cursor");
  const result = await env.DB.prepare(
    `SELECT event_id, payload_encrypted, received_at
       FROM kofi_inbox
      WHERE imported_at IS NULL AND event_id > ?1
      ORDER BY event_id
      LIMIT ?2`,
  ).bind(after, limit + 1).all<{ event_id: string; payload_encrypted: string; received_at: string }>();
  const rows = result.results || [];
  const hasMore = rows.length > limit;
  const visible = rows.slice(0, limit);
  return jsonResponse({
    events: visible.map((row) => ({
      event_id: row.event_id,
      payload: JSON.parse(row.payload_encrypted),
      received_at: row.received_at,
    })),
    next_after: hasMore && visible.length ? visible[visible.length - 1].event_id : "",
  });
}

async function handleAdminKofiAck(env: Env, rawBody: string, requestId: string): Promise<Response> {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return errorResponse(400, "invalid_request");
  }
  if (!payload || !hasExactKeys(payload, ["event_ids"]) || !Array.isArray(payload.event_ids) || payload.event_ids.length < 1 || payload.event_ids.length > 100) {
    return errorResponse(400, "invalid_request");
  }
  const eventIds = [...new Set(payload.event_ids)];
  if (eventIds.length !== payload.event_ids.length || !eventIds.every((value) => typeof value === "string" && HEX_64.test(value))) {
    return errorResponse(400, "invalid_request");
  }
  if (!(await recordAdminMutation(env, requestId, "kofi_ack"))) return errorResponse(409, "admin_request_replayed");
  const now = new Date().toISOString();
  const results = await env.DB.batch(eventIds.map((eventId) => env.DB.prepare(
    "UPDATE kofi_inbox SET imported_at = ?2 WHERE event_id = ?1 AND imported_at IS NULL",
  ).bind(eventId, now)));
  const acknowledged = results.reduce((total, result) => total + Number(result.meta.changes || 0), 0);
  return jsonResponse({ acknowledged, requested: eventIds.length });
}

async function handleAdminImport(request: Request, env: Env, rawBody: string, requestId: string): Promise<Response> {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return errorResponse(400, "invalid_request");
  }
  if (!payload || !hasExactKeys(payload, ["licenses"]) || !Array.isArray(payload.licenses) || payload.licenses.length < 1 || payload.licenses.length > 100) {
    return errorResponse(400, "invalid_request");
  }
  const entries: Array<{ key_id: string; signature_sha256: string }> = [];
  for (const item of payload.licenses) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return errorResponse(400, "invalid_request");
    const row = item as Record<string, unknown>;
    if (!hasExactKeys(row, ["key_id", "signature_sha256"]) || typeof row.key_id !== "string" || typeof row.signature_sha256 !== "string" || !HEX_64.test(row.key_id) || !HEX_64.test(row.signature_sha256)) {
      return errorResponse(400, "invalid_request");
    }
    entries.push({ key_id: row.key_id, signature_sha256: row.signature_sha256 });
  }
  if (!(await recordAdminMutation(env, requestId, "import"))) return errorResponse(409, "admin_request_replayed");

  const now = new Date().toISOString();
  await env.DB.batch(entries.map((entry) => env.DB.prepare(
    `INSERT OR IGNORE INTO licenses
       (key_id, signature_sha256, status, created_at, updated_at)
     VALUES (?1, ?2, 'active', ?3, ?3)`,
  ).bind(entry.key_id, entry.signature_sha256, now)));

  const checks = await env.DB.batch(entries.map((entry) => env.DB.prepare(
    "SELECT key_id, signature_sha256 FROM licenses WHERE key_id = ?1",
  ).bind(entry.key_id)));
  let registered = 0;
  let conflicts = 0;
  checks.forEach((check, index) => {
    const found = (check.results?.[0] || {}) as Record<string, unknown>;
    if (found.key_id === entries[index].key_id && found.signature_sha256 === entries[index].signature_sha256) registered += 1;
    else conflicts += 1;
  });
  return jsonResponse({ registered, conflicts, total: entries.length });
}

async function handleAdminMutation(
  env: Env,
  keyId: string,
  action: AdminLicenseAction,
  requestId: string,
): Promise<Response> {
  if (!(await recordAdminMutation(env, requestId, action, keyId))) return errorResponse(409, "admin_request_replayed");
  const now = new Date().toISOString();
  let statement: D1PreparedStatement;
  if (action === "reset") {
    statement = env.DB.prepare(
      `UPDATE licenses
          SET device_id = NULL,
              activated_at = NULL,
              reset_count = reset_count + 1,
              last_reset_at = ?2,
              updated_at = ?2
        WHERE key_id = ?1`,
    ).bind(keyId, now);
  } else if (action === "clear_conflicts") {
    statement = env.DB.prepare(
      `UPDATE licenses
          SET conflict_count = 0,
              first_conflict_at = NULL,
              last_conflict_at = NULL,
              updated_at = ?2
        WHERE key_id = ?1`,
    ).bind(keyId, now);
  } else {
    statement = env.DB.prepare(
      "UPDATE licenses SET status = ?2, updated_at = ?3 WHERE key_id = ?1",
    ).bind(keyId, action === "revoke" ? "revoked" : "active", now);
  }
  const result = await statement.run();
  if ((result.meta.changes || 0) !== 1) return errorResponse(404, "license_not_found");
  const row = await env.DB.prepare("SELECT * FROM licenses WHERE key_id = ?1").bind(keyId).first<LicenseRow>();
  return jsonResponse({ license: row ? publicLicense(row) : null });
}

async function handleAdminMutationRequest(env: Env, rawBody: string, requestId: string): Promise<Response> {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(rawBody) as Record<string, unknown>;
  } catch {
    return errorResponse(400, "invalid_request");
  }
  if (
    !payload
    || !hasExactKeys(payload, ["action", "key_id"])
    || typeof payload.key_id !== "string"
    || !HEX_64.test(payload.key_id)
    || !["reset", "revoke", "restore", "clear_conflicts"].includes(String(payload.action))
  ) {
    return errorResponse(400, "invalid_request");
  }
  return handleAdminMutation(
    env,
    payload.key_id,
    payload.action as AdminLicenseAction,
    requestId,
  );
}

async function handleAdmin(request: Request, env: Env, path: string): Promise<Response> {
  let rawBody = "";
  if (request.method !== "GET") {
    try {
      rawBody = await readBody(request, MAX_ADMIN_BODY);
    } catch {
      return errorResponse(413, "request_too_large");
    }
  }
  const auth = await authenticateAdminRequest(request, env, rawBody);
  if (auth instanceof Response) return auth;
  if (request.method === "GET" && path === "/v1/admin/licenses") return handleAdminList(request, env);
  if (request.method === "GET" && path === "/v1/admin/kofi/events") return handleAdminKofiList(request, env);
  if (request.method === "POST" && path === "/v1/admin/licenses/import") return handleAdminImport(request, env, rawBody, auth);
  if (request.method === "POST" && path === "/v1/admin/kofi/ack") return handleAdminKofiAck(env, rawBody, auth);
  if (request.method === "POST" && path === "/v1/admin/licenses/mutate") {
    return handleAdminMutationRequest(env, rawBody, auth);
  }
  return errorResponse(404, "not_found");
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/v1/health") {
      return jsonResponse({ service: "kfps-supporter-activation", protocol: 1, status: "ok" });
    }
    try {
      if (request.method === "POST" && url.pathname === "/v1/activate") return await handleActivate(request, env);
      if (request.method === "POST" && url.pathname === "/v1/status") return await handleStatus(request, env);
      if (request.method === "POST" && url.pathname === "/v1/deactivate") return await handleDeactivate(request, env);
      if (request.method === "POST" && url.pathname === "/v1/kofi/webhook") return await handleKofiWebhook(request, env);
      if (url.pathname.startsWith("/v1/admin/")) return await handleAdmin(request, env, url.pathname);
      return errorResponse(404, "not_found");
    } catch {
      return errorResponse(500, "service_error");
    }
  },
} satisfies ExportedHandler<Env>;
