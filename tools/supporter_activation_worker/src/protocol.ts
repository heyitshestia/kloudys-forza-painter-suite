export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export interface SignedEnvelope {
  type: string;
  version: 1;
  kid: string;
  payload: string;
  signature: string;
}

const privateKeyCache = new Map<string, Promise<CryptoKey>>();

export function canonicalJson(value: JsonValue): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const parts = Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`);
  return `{${parts.join(",")}}`;
}

export function bytesToBase64Url(data: Uint8Array): string {
  let binary = "";
  for (const byte of data) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function base64UrlToBytes(value: string): Uint8Array {
  if (!value || !/^[A-Za-z0-9_-]+$/.test(value)) throw new Error("invalid base64url");
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export function bytesToHex(data: Uint8Array): string {
  return Array.from(data, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function toArrayBuffer(data: Uint8Array): ArrayBuffer {
  return data.slice().buffer as ArrayBuffer;
}

export async function sha256Hex(data: Uint8Array): Promise<string> {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256", toArrayBuffer(data))));
}

function pemToDer(pem: string): Uint8Array {
  const body = pem.replace(/-----BEGIN PRIVATE KEY-----/g, "")
    .replace(/-----END PRIVATE KEY-----/g, "")
    .replace(/\s+/g, "");
  if (!body) throw new Error("activation private key is empty or not PKCS#8 PEM");
  return Uint8Array.from(atob(body), (char) => char.charCodeAt(0));
}

function importPrivateKey(pem: string): Promise<CryptoKey> {
  let promise = privateKeyCache.get(pem);
  if (!promise) {
    promise = crypto.subtle.importKey(
      "pkcs8",
      toArrayBuffer(pemToDer(pem)),
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["sign"],
    );
    privateKeyCache.set(pem, promise);
  }
  return promise;
}

export async function signEnvelope(
  privateKeyPem: string,
  kid: string,
  type: string,
  payload: Record<string, JsonValue>,
): Promise<SignedEnvelope> {
  const payloadBytes = new TextEncoder().encode(canonicalJson(payload));
  const key = await importPrivateKey(privateKeyPem);
  const signature = new Uint8Array(await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, toArrayBuffer(payloadBytes)));
  return {
    type,
    version: 1,
    kid,
    payload: bytesToBase64Url(payloadBytes),
    signature: bytesToBase64Url(signature),
  };
}

export async function signReceipt(
  privateKeyPem: string,
  kid: string,
  keyId: string,
  deviceId: string,
  activatedAt: string,
): Promise<SignedEnvelope> {
  return signEnvelope(privateKeyPem, kid, "kfps.supporter.activation", {
    activated_at: activatedAt,
    device_id: deviceId,
    key_id: keyId,
    schema: "kfps.activation.v1",
  });
}

export async function signDecision(
  privateKeyPem: string,
  kid: string,
  status: string,
  keyId: string,
  deviceId: string,
  nonce: string,
  decidedAt: string,
): Promise<SignedEnvelope> {
  return signEnvelope(privateKeyPem, kid, "kfps.supporter.activation-decision", {
    decided_at: decidedAt,
    device_id: deviceId,
    key_id: keyId,
    nonce,
    schema: "kfps.activation.decision.v1",
    status,
  });
}

export function constantTimeEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}
