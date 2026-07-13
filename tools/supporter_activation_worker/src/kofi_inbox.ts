import { bytesToBase64Url, constantTimeEqual, sha256Hex, toArrayBuffer } from "./protocol";

export const KOFI_INBOX_KEY_ID = "kofi-inbox-rsa-2026-01";

const publicKeyCache = new Map<string, Promise<CryptoKey>>();
const encoder = new TextEncoder();

function pemToDer(pem: string): Uint8Array {
  const body = pem.replace(/-----BEGIN PUBLIC KEY-----/g, "")
    .replace(/-----END PUBLIC KEY-----/g, "")
    .replace(/\s+/g, "");
  if (!body) throw new Error("Ko-fi inbox public key is empty");
  return Uint8Array.from(atob(body), (character) => character.charCodeAt(0));
}

function importPublicKey(pem: string): Promise<CryptoKey> {
  let promise = publicKeyCache.get(pem);
  if (!promise) {
    promise = crypto.subtle.importKey(
      "spki",
      toArrayBuffer(pemToDer(pem)),
      { name: "RSA-OAEP", hash: "SHA-256" },
      false,
      ["encrypt"],
    );
    publicKeyCache.set(pem, promise);
  }
  return promise;
}

function text(value: unknown, maximumBytes: number): string {
  const source = (typeof value === "string" || typeof value === "number" || typeof value === "boolean"
    ? String(value).trim()
    : "").replace(/[\u0000-\u001f\u007f]/g, " ");
  if (encoder.encode(source).length <= maximumBytes) return source;
  let result = "";
  for (const character of source) {
    if (encoder.encode(result + character).length > maximumBytes) break;
    result += character;
  }
  return result;
}

function fitEncryptedChunk(value: Record<string, string>, shrinkOrder: string[]): Record<string, string> {
  const fitted = { ...value };
  const size = () => encoder.encode(JSON.stringify(fitted)).length;
  for (const key of shrinkOrder) {
    if (size() <= 300) return fitted;
    const characters = Array.from(fitted[key] || "");
    let lower = 0;
    let upper = characters.length;
    while (lower < upper) {
      const middle = Math.ceil((lower + upper) / 2);
      fitted[key] = characters.slice(0, middle).join("").trimEnd();
      if (size() <= 300) lower = middle;
      else upper = middle - 1;
    }
    fitted[key] = characters.slice(0, lower).join("").trimEnd();
  }
  if (size() > 300) throw new Error("Ko-fi encrypted chunk exceeds RSA-OAEP capacity");
  return fitted;
}

function productName(payload: Record<string, unknown>): string {
  const direct = text(payload.product || payload.item || payload.tier_name, 64);
  if (direct) return direct;
  if (!Array.isArray(payload.shop_items)) return "";
  const names = payload.shop_items.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return "";
    const item = value as Record<string, unknown>;
    return text(item.item_name || item.name || item.product_name, 64);
  }).filter(Boolean);
  return text(names.join(", "), 64);
}

export function parseKofiPayload(rawBody: string, contentType: string): Record<string, unknown> {
  let source: unknown;
  if (contentType.toLowerCase().includes("application/x-www-form-urlencoded")) {
    const encoded = new URLSearchParams(rawBody).get("data");
    if (!encoded) throw new Error("Ko-fi data form field is missing");
    source = JSON.parse(encoded);
  } else {
    const parsed = JSON.parse(rawBody) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && typeof (parsed as Record<string, unknown>).data === "string") {
      source = JSON.parse(String((parsed as Record<string, unknown>).data));
    } else {
      source = parsed;
    }
  }
  if (!source || typeof source !== "object" || Array.isArray(source)) throw new Error("Ko-fi payload is invalid");
  return source as Record<string, unknown>;
}

export function validKofiToken(payload: Record<string, unknown>, expectedToken: string): boolean {
  const supplied = encoder.encode(text(payload.verification_token, 512));
  const expected = encoder.encode(expectedToken.trim());
  return expected.length >= 16 && constantTimeEqual(supplied, expected);
}

async function encryptChunk(
  publicKeyPem: string,
  value: Record<string, string>,
  shrinkOrder: string[],
): Promise<string> {
  const plaintext = encoder.encode(JSON.stringify(fitEncryptedChunk(value, shrinkOrder)));
  const key = await importPublicKey(publicKeyPem);
  const encrypted = new Uint8Array(await crypto.subtle.encrypt({ name: "RSA-OAEP" }, key, toArrayBuffer(plaintext)));
  return bytesToBase64Url(encrypted);
}

export interface EncryptedKofiEvent {
  eventId: string;
  payload: {
    version: 1;
    kid: string;
    algorithm: "RSA-OAEP-SHA256";
    chunks: Record<string, string>;
  };
}

export async function encryptKofiEvent(
  payload: Record<string, unknown>,
  publicKeyPem: string,
): Promise<EncryptedKofiEvent> {
  const messageId = text(payload.message_id, 96);
  if (!messageId) throw new Error("Ko-fi message_id is missing");
  if (!/^[A-Za-z0-9._:-]+$/.test(messageId)) throw new Error("Ko-fi message_id has an invalid format");
  const event = {
    message_id: messageId,
    kofi_transaction_id: text(payload.kofi_transaction_id || payload.transaction_id, 96),
  };
  const buyer = {
    from_name: text(payload.from_name, 80),
    email: text(payload.email, 128),
  };
  const purchase = {
    timestamp: text(payload.timestamp, 40),
    type: text(payload.type, 24),
    amount: text(payload.amount, 24),
    currency: text(payload.currency, 8),
    product: productName(payload),
    message: text(payload.message, 48),
  };
  const chunks = {
    event: await encryptChunk(publicKeyPem, event, ["kofi_transaction_id"]),
    buyer: await encryptChunk(publicKeyPem, buyer, ["from_name", "email"]),
    purchase: await encryptChunk(publicKeyPem, purchase, ["message", "product", "timestamp", "type", "amount", "currency"]),
  };
  return {
    eventId: await sha256Hex(encoder.encode(messageId)),
    payload: {
      version: 1,
      kid: KOFI_INBOX_KEY_ID,
      algorithm: "RSA-OAEP-SHA256",
      chunks,
    },
  };
}
