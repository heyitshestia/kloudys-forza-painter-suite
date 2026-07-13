import { base64UrlToBytes, bytesToBase64Url, constantTimeEqual, sha256Hex, toArrayBuffer } from "./protocol";

export interface AdminAuthResult {
  ok: boolean;
  requestId: string;
  error?: string;
}

const MAX_CLOCK_SKEW_SECONDS = 300;

function validRequestId(value: string): boolean {
  return /^[A-Za-z0-9._:-]{16,128}$/.test(value);
}

export async function authenticateAdmin(
  request: Request,
  rawBody: string,
  secret: string,
): Promise<AdminAuthResult> {
  const timestampText = request.headers.get("X-KFPS-Admin-Timestamp") || "";
  const requestId = request.headers.get("X-KFPS-Admin-Request-Id") || "";
  const signatureText = request.headers.get("X-KFPS-Admin-Signature") || "";
  const timestamp = Number(timestampText);
  if (!Number.isInteger(timestamp) || Math.abs(Math.floor(Date.now() / 1000) - timestamp) > MAX_CLOCK_SKEW_SECONDS) {
    return { ok: false, requestId, error: "expired or invalid admin timestamp" };
  }
  if (!validRequestId(requestId)) return { ok: false, requestId, error: "invalid admin request id" };
  if (secret.length < 32) return { ok: false, requestId, error: "admin authentication is not configured" };

  let supplied: Uint8Array;
  try {
    supplied = base64UrlToBytes(signatureText);
  } catch {
    return { ok: false, requestId, error: "invalid admin signature" };
  }

  const url = new URL(request.url);
  const bodyHash = await sha256Hex(new TextEncoder().encode(rawBody));
  const message = [request.method.toUpperCase(), `${url.pathname}${url.search}`, timestampText, requestId, bodyHash].join("\n");
  const key = await crypto.subtle.importKey(
    "raw",
    toArrayBuffer(new TextEncoder().encode(secret)),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = new Uint8Array(await crypto.subtle.sign("HMAC", key, toArrayBuffer(new TextEncoder().encode(message))));
  return constantTimeEqual(supplied, expected)
    ? { ok: true, requestId }
    : { ok: false, requestId, error: "invalid admin signature" };
}

export async function createAdminSignatureForTesting(
  method: string,
  pathAndQuery: string,
  timestamp: string,
  requestId: string,
  rawBody: string,
  secret: string,
): Promise<string> {
  const bodyHash = await sha256Hex(new TextEncoder().encode(rawBody));
  const message = [method.toUpperCase(), pathAndQuery, timestamp, requestId, bodyHash].join("\n");
  const key = await crypto.subtle.importKey(
    "raw",
    toArrayBuffer(new TextEncoder().encode(secret)),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return bytesToBase64Url(new Uint8Array(await crypto.subtle.sign("HMAC", key, toArrayBuffer(new TextEncoder().encode(message)))));
}
