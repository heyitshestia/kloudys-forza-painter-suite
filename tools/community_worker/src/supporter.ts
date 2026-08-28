import {
  enforceRateLimit,
  HttpError,
  jsonResponse,
  readJsonObject,
  requireUser,
} from "./security";
import type { Env, SessionUser } from "./types";

const ENVELOPE_KEYS = ["kid", "payload", "signature", "type", "version"];
const PAYLOAD_KEYS = [
  "audience", "entitlement_id", "expires_at", "issued_at", "nonce", "schema", "subject",
];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const BASE64URL = /^[A-Za-z0-9_-]+$/;
const HEX = /^[0-9a-f]+$/i;
const publicKeyCache = new Map<string, Promise<CryptoKey>>();

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function canonicalJson(value: JsonValue): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key]!)}`).join(",")}}`;
}

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, index) => key === wanted[index]);
}

function base64UrlToBytes(value: unknown, maximum: number): Uint8Array {
  if (typeof value !== "string" || !value || value.length > maximum * 2 || !BASE64URL.test(value)) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - value.length % 4) % 4);
    const bytes = Uint8Array.from(atob(normalized), (character) => character.charCodeAt(0));
    if (bytes.length > maximum) throw new HttpError(400, "invalid_supporter_entitlement");
    return bytes;
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
}

function bytesToBase64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function toArrayBuffer(value: Uint8Array): ArrayBuffer {
  return value.slice().buffer as ArrayBuffer;
}

function hexToBytes(value: string): Uint8Array {
  if (!HEX.test(value) || value.length % 2 !== 0) throw new Error("supporter public key modulus is invalid");
  return Uint8Array.from(value.match(/../g) || [], (pair) => Number.parseInt(pair, 16));
}

function supporterPublicKey(env: Env): Promise<CryptoKey> {
  const kid = (env.SUPPORTER_ENTITLEMENT_KEY_ID || "").trim();
  const modulus = (env.SUPPORTER_ENTITLEMENT_MODULUS_HEX || "").trim();
  const cacheKey = `${kid}:${modulus}`;
  let promise = publicKeyCache.get(cacheKey);
  if (!promise) {
    if (!kid || modulus.length < 512) throw new HttpError(503, "supporter_verification_unavailable");
    promise = crypto.subtle.importKey(
      "jwk",
      {
        kty: "RSA",
        n: bytesToBase64Url(hexToBytes(modulus)),
        e: "AQAB",
        alg: "RS256",
        ext: true,
      },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    publicKeyCache.set(cacheKey, promise);
  }
  return promise;
}

export function hasActiveSupporter(user: SessionUser | null, now = Date.now()): boolean {
  if (!user?.supporterEntitlementId || !user.supporterVerifiedUntil) return false;
  const expires = Date.parse(user.supporterVerifiedUntil);
  return Number.isFinite(expires) && expires > now;
}

export function publicSupporterState(user: SessionUser | null): Record<string, unknown> {
  return {
    active: hasActiveSupporter(user),
    verified_until: user?.supporterVerifiedUntil || "",
  };
}

export function requireActiveSupporter(user: SessionUser | null): void {
  if (!hasActiveSupporter(user)) {
    throw new HttpError(403, "supporter_required", "A currently verified KFPS supporter account is required.");
  }
}

export async function verifySupporterEnvelope(
  env: Env,
  envelope: unknown,
  expectedSubject: string,
  now = Date.now(),
): Promise<{ entitlementId: string; issuedAt: string; expiresAt: string }> {
  if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  const signed = envelope as Record<string, unknown>;
  if (!exactKeys(signed, ENVELOPE_KEYS)
      || signed.type !== "kfps.supporter.community-entitlement"
      || signed.version !== 1
      || signed.kid !== env.SUPPORTER_ENTITLEMENT_KEY_ID) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  const payloadBytes = base64UrlToBytes(signed.payload, 4096);
  const signature = base64UrlToBytes(signed.signature, 512);
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(payloadBytes)) as Record<string, unknown>;
  } catch {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
      || !exactKeys(payload, PAYLOAD_KEYS)
      || payload.schema !== "kfps.community.supporter.v1"
      || payload.audience !== "kfps-community-v1"
      || payload.subject !== expectedSubject
      || typeof payload.nonce !== "string"
      || !BASE64URL.test(payload.nonce)
      || payload.nonce.length < 22
      || payload.nonce.length > 86) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  const entitlementId = String(payload.entitlement_id || "");
  const issuedAt = String(payload.issued_at || "");
  const expiresAt = String(payload.expires_at || "");
  const issued = Date.parse(issuedAt);
  const expires = Date.parse(expiresAt);
  if (!UUID.test(entitlementId)
      || !Number.isFinite(issued)
      || !Number.isFinite(expires)
      || issued > now + 2 * 60 * 1000
      || issued < now - 30 * 60 * 1000
      || expires <= now
      || expires - issued > 16 * 60 * 1000
      || expires <= issued) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  const canonical = new TextEncoder().encode(canonicalJson(payload as JsonValue));
  if (canonical.length !== payloadBytes.length
      || !canonical.every((byte, index) => byte === payloadBytes[index])) {
    throw new HttpError(400, "invalid_supporter_entitlement");
  }
  const verified = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    await supporterPublicKey(env),
    toArrayBuffer(signature),
    toArrayBuffer(payloadBytes),
  );
  if (!verified) throw new HttpError(400, "invalid_supporter_entitlement");
  return { entitlementId, issuedAt, expiresAt };
}

export async function handleVerifySupporter(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "supporter_verify", 20, 3600);
  const value = await readJsonObject(request, 16 * 1024);
  if (!exactKeys(value, ["entitlement"])) throw new HttpError(400, "invalid_supporter_entitlement");
  const verified = await verifySupporterEnvelope(env, value.entitlement, user.id);
  if (user.supporterEntitlementId && user.supporterEntitlementId !== verified.entitlementId) {
    throw new HttpError(409, "supporter_account_already_bound", "This Community account is already bound to another supporter entitlement.");
  }
  const existing = await env.DB.prepare(
    "SELECT id FROM users WHERE supporter_entitlement_id = ?1 AND id <> ?2 LIMIT 1",
  ).bind(verified.entitlementId, user.id).first();
  if (existing) {
    throw new HttpError(409, "supporter_entitlement_already_bound", "This supporter entitlement is already bound to another Community account.");
  }
  try {
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE users
            SET supporter_entitlement_id = ?2,
                supporter_verified_at = ?3,
                supporter_verified_until = ?4,
                updated_at = ?3
          WHERE id = ?1`,
      ).bind(user.id, verified.entitlementId, verified.issuedAt, verified.expiresAt),
      env.DB.prepare(
        `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
         VALUES (?1, NULL, ?2, 'supporter_verified', ?3, ?4)`,
      ).bind(crypto.randomUUID(), user.username, verified.expiresAt, verified.issuedAt),
    ]);
  } catch {
    throw new HttpError(409, "supporter_entitlement_already_bound");
  }
  return jsonResponse({ supporter: { active: true, verified_until: verified.expiresAt } });
}

export async function handleClearSupporter(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "supporter_clear", 20, 3600);
  const now = new Date().toISOString();
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE users
          SET supporter_verified_at = NULL,
              supporter_verified_until = NULL,
              updated_at = ?2
        WHERE id = ?1`,
    ).bind(user.id, now),
    env.DB.prepare(
      `INSERT INTO moderation_events(id, artwork_id, actor, action, note, created_at)
       VALUES (?1, NULL, ?2, 'supporter_cleared', '', ?3)`,
    ).bind(crypto.randomUUID(), user.username, now),
  ]);
  return jsonResponse({ supporter: { active: false, verified_until: "" } });
}
