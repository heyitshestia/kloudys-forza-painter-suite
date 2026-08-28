import type { Env, SessionUser } from "./types";

const encoder = new TextEncoder();
const TOKEN_PATTERN = /^kfc_[A-Za-z0-9_-]{43}$/;

export class HttpError extends Error {
  constructor(public status: number, public code: string, message = code) {
    super(message);
  }
}

export const JSON_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Type": "application/json; charset=utf-8",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
} as const;

export function jsonResponse(data: unknown, status = 200, extraHeaders: HeadersInit = {}): Response {
  return new Response(JSON.stringify(data), { status, headers: { ...JSON_HEADERS, ...extraHeaders } });
}

export function errorResponse(error: unknown): Response {
  if (error instanceof HttpError) {
    return jsonResponse({ error: error.code, message: error.message }, error.status);
  }
  console.error(error);
  return jsonResponse({ error: "internal_error", message: "The community service could not complete the request." }, 500);
}

export async function readJsonObject(request: Request, maximumBytes: number): Promise<Record<string, unknown>> {
  const contentType = (request.headers.get("content-type") || "").split(";", 1)[0]?.trim().toLowerCase();
  if (contentType !== "application/json") throw new HttpError(415, "content_type_required");
  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > maximumBytes) throw new HttpError(413, "request_too_large");
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.length > maximumBytes) throw new HttpError(413, "request_too_large");
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new HttpError(400, "invalid_json");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new HttpError(400, "object_required");
  return value as Record<string, unknown>;
}

export function plainText(value: unknown, field: string, maximum: number, required = false): string {
  if (typeof value !== "string") {
    if (!required && value == null) return "";
    throw new HttpError(400, `invalid_${field}`, `${field} must be text.`);
  }
  const text = value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "").trim();
  if (required && !text) throw new HttpError(400, `invalid_${field}`, `${field} is required.`);
  if (text.length > maximum) throw new HttpError(400, `invalid_${field}`, `${field} is too long.`);
  return text;
}

export function httpsUrl(value: unknown, field: string): string {
  const text = plainText(value, field, 300, false);
  if (!text) return "";
  let url: URL;
  try {
    url = new URL(text);
  } catch {
    throw new HttpError(400, `invalid_${field}`, `${field} must be a valid URL.`);
  }
  if (url.protocol !== "https:") throw new HttpError(400, `invalid_${field}`, `${field} must use HTTPS.`);
  url.username = "";
  url.password = "";
  return url.toString();
}

export function bytesToBase64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function base64ToBytes(value: unknown, maximumBytes: number): Uint8Array {
  if (typeof value !== "string" || value.length > Math.ceil(maximumBytes * 4 / 3) + 8) {
    throw new HttpError(400, "invalid_base64");
  }
  try {
    const raw = value.replace(/-/g, "+").replace(/_/g, "/");
    const normalized = raw + "=".repeat((4 - raw.length % 4) % 4);
    const binary = atob(normalized);
    const out = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    if (out.length > maximumBytes) throw new HttpError(413, "asset_too_large");
    return out;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, "invalid_base64");
  }
}

export async function sha256Hex(value: Uint8Array | string): Promise<string> {
  const bytes = typeof value === "string" ? encoder.encode(value) : value;
  const input = new Uint8Array(bytes).buffer;
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", input));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return `kfc_${bytesToBase64Url(bytes)}`;
}

export async function createSession(env: Env, userId: string): Promise<string> {
  const token = randomToken();
  const now = new Date();
  const expires = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);
  await env.DB.prepare(
    "INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?1, ?2, ?3, ?4, ?3)",
  ).bind(await sha256Hex(token), userId, now.toISOString(), expires.toISOString()).run();
  await env.DB.prepare(
    `DELETE FROM sessions WHERE user_id = ?1 AND token_hash NOT IN (
       SELECT token_hash FROM sessions WHERE user_id = ?1 ORDER BY created_at DESC LIMIT 8
     )`,
  ).bind(userId).run();
  return token;
}

export async function optionalUser(request: Request, env: Env): Promise<SessionUser | null> {
  const header = request.headers.get("authorization") || "";
  if (!header) return null;
  const [scheme, token] = header.split(" ", 2);
  if (scheme?.toLowerCase() !== "bearer" || !token || !TOKEN_PATTERN.test(token)) {
    throw new HttpError(401, "invalid_session");
  }
  const row = await env.DB.prepare(
    `SELECT u.id, u.provider, u.provider_id, u.provider_login, COALESCE(u.username, '') AS username,
            u.bio, u.website_url, u.avatar_url, u.suspended_at,
            u.supporter_entitlement_id, u.supporter_verified_until
       FROM sessions s JOIN users u ON u.id = s.user_id
      WHERE s.token_hash = ?1 AND s.expires_at > ?2 LIMIT 1`,
  ).bind(await sha256Hex(token), new Date().toISOString()).first<Record<string, unknown>>();
  if (!row) throw new HttpError(401, "session_expired");
  return {
    id: String(row.id),
    provider: row.provider as "github" | "local-test",
    providerId: String(row.provider_id),
    providerLogin: String(row.provider_login),
    username: String(row.username || ""),
    bio: String(row.bio || ""),
    websiteUrl: String(row.website_url || ""),
    avatarUrl: String(row.avatar_url || ""),
    suspended: Boolean(row.suspended_at),
    supporterEntitlementId: String(row.supporter_entitlement_id || ""),
    supporterVerifiedUntil: String(row.supporter_verified_until || ""),
  };
}

export async function requireUser(request: Request, env: Env, requireUsername = true): Promise<SessionUser> {
  const user = await optionalUser(request, env);
  if (!user) throw new HttpError(401, "authentication_required");
  if (user.suspended) throw new HttpError(403, "account_suspended");
  if (requireUsername && !user.username) throw new HttpError(409, "username_required");
  return user;
}

export async function enforceRateLimit(env: Env, subject: string, action: string, limit: number, seconds: number): Promise<void> {
  const windowStart = Math.floor(Date.now() / 1000 / seconds) * seconds;
  const subjectHash = await sha256Hex(subject);
  const row = await env.DB.prepare(
    `INSERT INTO rate_limits(subject_hash, action, window_start, event_count)
     VALUES (?1, ?2, ?3, 1)
     ON CONFLICT(subject_hash, action, window_start)
     DO UPDATE SET event_count = event_count + 1
     RETURNING event_count`,
  ).bind(subjectHash, action, windowStart).first<{ event_count: number }>();
  if ((row?.event_count || 0) > limit) throw new HttpError(429, "rate_limited", "Please wait before trying that again.");
}

export function adminAuthorized(request: Request, env: Env): boolean {
  const supplied = request.headers.get("x-community-admin-token") || "";
  const expected = env.ADMIN_TOKEN || "";
  return secureTokenEqual(supplied, expected);
}

export function secureTokenEqual(supplied: string, expected: string): boolean {
  if (supplied.length < 32 || supplied.length !== expected.length) return false;
  let difference = 0;
  for (let index = 0; index < supplied.length; index += 1) {
    difference |= supplied.charCodeAt(index) ^ expected.charCodeAt(index);
  }
  return difference === 0;
}
