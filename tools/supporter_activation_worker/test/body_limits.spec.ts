import { env, SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import worker, { type Env } from "../src/index";
import { createAdminSignatureForTesting } from "../src/admin_auth";
import { base64UrlToBytes, bytesToBase64Url, sha256Hex, toArrayBuffer, type SignedEnvelope } from "../src/protocol";

const encoder = new TextEncoder();
const workerEnv = env as Env;
const keyId = "a".repeat(64);
const proofBytes = new Uint8Array(384).fill(17);
const publicRoutes = ["activate", "deactivate", "status", "community-entitlement"];
const routes = [
  ...publicRoutes.map((name) => ({ path: `/v1/${name}`, maximum: 8192 })),
  { path: "/v1/admin/licenses/import", maximum: 256 * 1024 },
  { path: "/v1/kofi/webhook", maximum: 64 * 1024 },
];

function trackedStream(chunks: Uint8Array[], cancellation: "normal" | "reject" | "pending" = "normal") {
  const state = { delivered: 0, pulls: 0, cancellations: 0 };
  let index = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      state.pulls += 1;
      if (index === chunks.length) return controller.close();
      const chunk = chunks[index++];
      state.delivered += chunk.byteLength;
      controller.enqueue(chunk);
    },
    cancel() {
      state.cancellations += 1;
      if (cancellation === "reject") return Promise.reject(new Error("source cancellation failed"));
      if (cancellation === "pending") return new Promise<void>(() => {});
    },
  }, { highWaterMark: 0 });
  return { body, state };
}

function chunksOf(bytes: Uint8Array, size: number): Uint8Array[] {
  const chunks: Uint8Array[] = [];
  for (let offset = 0; offset < bytes.length; offset += size) chunks.push(bytes.slice(offset, offset + size));
  return chunks;
}

function request(path: string, body: ReadableStream<Uint8Array> | null, headers: Record<string, string> = {}) {
  return new Request(`https://activation.test${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body,
    duplex: "half",
  } as RequestInit & { duplex: string });
}

async function adminHeaders(path: string, rawBody: string): Promise<Record<string, string>> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const requestId = crypto.randomUUID();
  return {
    "X-KFPS-Admin-Timestamp": timestamp,
    "X-KFPS-Admin-Request-Id": requestId,
    "X-KFPS-Admin-Signature": await createAdminSignatureForTesting(
      "POST", path, timestamp, requestId, rawBody, workerEnv.ADMIN_HMAC_SECRET,
    ),
  };
}

function validBody(path: string): string {
  if (path.includes("/admin/")) {
    return JSON.stringify({ licenses: [{ key_id: "b".repeat(64), signature_sha256: "c".repeat(64) }] });
  }
  if (path.includes("/kofi/")) {
    return JSON.stringify({
      verification_token: workerEnv.KOFI_VERIFICATION_TOKEN,
      message_id: "r9-synthetic-payment",
      from_name: "Synthetic \u00e9\u20ac\ud83d\ude80",
      email: "r9@example.test",
    });
  }
  const fields = {
    protocol: 1,
    key_id: keyId,
    key_proof: bytesToBase64Url(proofBytes),
    nonce: bytesToBase64Url(new Uint8Array(32).fill(23)),
  };
  return JSON.stringify(path.endsWith("community-entitlement")
    ? { ...fields, community_subject: "11111111-1111-4111-8111-111111111111" }
    : { ...fields, device_id: "d".repeat(64) });
}

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM admin_events"),
    env.DB.prepare("DELETE FROM licenses"),
    env.DB.prepare("DELETE FROM kofi_inbox"),
  ]);
  const now = new Date().toISOString();
  await env.DB.prepare(
    "INSERT INTO licenses(key_id, signature_sha256, created_at, updated_at) VALUES (?1, ?2, ?3, ?3)",
  ).bind(keyId, await sha256Hex(proofBytes), now).run();
});

describe("streamed request body limits through the exported fetch handler", () => {
  for (const { path, maximum } of routes) {
    describe(path, () => {
      it.each([undefined, "1"])("cancels an overflowing stream with declared length %s", async (declared) => {
        const stream = trackedStream(Array.from({ length: maximum / 4096 + 8 }, () => new Uint8Array(4096).fill(32)));
        const response = await worker.fetch(request(path, stream.body, declared ? { "Content-Length": declared } : {}), workerEnv);
        expect(stream.state.cancellations).toBe(1);
        expect(stream.state.delivered).toBe(maximum + 4096);
        expect(stream.body.locked).toBe(false);
        expect(response.status).toBe(413);
        expect(await response.json()).toEqual({ error: "request_too_large" });
      });

      it("rejects an oversized declared length before pulling and cancels the source", async () => {
        const stream = trackedStream([encoder.encode(validBody(path))]);
        const response = await worker.fetch(request(path, stream.body, { "Content-Length": String(maximum + 1) }), workerEnv);
        expect(stream.state).toEqual({ delivered: 0, pulls: 0, cancellations: 1 });
        expect(stream.body.locked).toBe(false);
        expect(response.status).toBe(413);
      });

      it.each([undefined, String(maximum)])("accepts exactly the byte limit with declared length %s", async (declared) => {
        const raw = validBody(path);
        const padded = raw + " ".repeat(maximum - encoder.encode(raw).length);
        const headers = path.includes("/admin/") ? await adminHeaders(path, padded) : {};
        if (declared) headers["Content-Length"] = declared;
        const stream = trackedStream(chunksOf(encoder.encode(padded), 997));
        const response = await worker.fetch(request(path, stream.body, headers), workerEnv);
        expect(response.status).toBe(200);
        expect(stream.state.delivered).toBe(maximum);
        expect(stream.state.cancellations).toBe(0);
        expect(stream.body.locked).toBe(false);
        if (publicRoutes.some((name) => path === `/v1/${name}`)) {
          const result = await response.json() as Record<string, SignedEnvelope>;
          const envelope = result.receipt || result.decision || result.entitlement;
          const pemBody = workerEnv.KOFI_INBOX_PUBLIC_KEY_PEM.replace(/-----[^-]+-----|\s/g, "");
          const publicKey = await crypto.subtle.importKey(
            "spki", Uint8Array.from(atob(pemBody), (value) => value.charCodeAt(0)),
            { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
          );
          expect(await crypto.subtle.verify(
            "RSASSA-PKCS1-v1_5", publicKey, toArrayBuffer(base64UrlToBytes(envelope.signature)),
            toArrayBuffer(base64UrlToBytes(envelope.payload)),
          )).toBe(true);
        }
      });

      it("rejects exactly one excess byte, without consuming the next chunk", async () => {
        const raw = validBody(path);
        const padded = raw + " ".repeat(maximum - encoder.encode(raw).length);
        const stream = trackedStream([encoder.encode(padded), encoder.encode(" "), encoder.encode("unread")]);
        const headers = path.includes("/admin/") ? await adminHeaders(path, padded + " ") : {};
        headers["Content-Length"] = String(maximum);
        const response = await worker.fetch(request(path, stream.body, headers), workerEnv);
        expect(stream.state.delivered).toBe(maximum + 1);
        expect(stream.state.cancellations).toBe(1);
        expect(response.status).toBe(413);
      });
    });
  }

  it.each(["reject", "pending"] as const)("returns 413 even when source cancellation is %s", async (cancellation) => {
    const stream = trackedStream([new Uint8Array(8193), new Uint8Array(100)], cancellation);
    const response = await worker.fetch(request("/v1/activate", stream.body), workerEnv);
    expect(response.status).toBe(413);
    expect(stream.state.cancellations).toBe(1);
    expect(stream.state.delivered).toBe(8193);
    expect(stream.body.locked).toBe(false);
  });

  it("preserves exact signed admin text across one-byte UTF-8 chunks", async () => {
    const path = "/v1/admin/not-a-route?probe=exact";
    const raw = ' { "text" : "\u00e9\u20ac\ud83d\ude80", "escape": "\\u0061" }\r\n';
    const headers = await adminHeaders(path, raw);
    const response = await worker.fetch(request(path, trackedStream(chunksOf(encoder.encode(raw), 1)).body, headers), workerEnv);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not_found" });
    const tampered = await worker.fetch(request(path, trackedStream([encoder.encode(raw + " ")]).body, headers), workerEnv);
    expect(tampered.status).toBe(401);
    expect(await tampered.json()).toEqual({ error: "admin_auth_failed" });
  });

  it("accepts a signed admin mutation with preserved whitespace and JSON escapes", async () => {
    const path = "/v1/admin/licenses/mutate";
    const raw = `\r\n{ "key_id" : "${keyId}", "\\u0061ction" : "restore" } \t`;
    const response = await worker.fetch(request(path, trackedStream(chunksOf(encoder.encode(raw), 1)).body, await adminHeaders(path, raw)), workerEnv);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ license: { key_id: keyId, status: "active" } });
  });

  it.each(["application/json", "application/x-www-form-urlencoded"])("accepts chunked Ko-fi %s without a length", async (contentType) => {
    const raw = validBody("/v1/kofi/webhook");
    const encoded = contentType === "application/json" ? raw : new URLSearchParams({ data: raw }).toString();
    const stream = trackedStream(chunksOf(encoder.encode(encoded), 1));
    const response = await worker.fetch(request("/v1/kofi/webhook", stream.body, { "Content-Type": contentType }), workerEnv);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "accepted" });
  });

  it.each([[0xc3, 0x28], [0xed, 0xa0, 0x80], [0xf0, 0x9f]])("rejects invalid or incomplete UTF-8 %j without replacement", async (...badBytes) => {
    const prefix = encoder.encode(`{"verification_token":"${workerEnv.KOFI_VERIFICATION_TOKEN}","message_id":"r9-invalid","from_name":"`);
    const bytes = badBytes.length === 2 && badBytes[0] === 0xf0
      ? [...prefix, ...badBytes]
      : [...prefix, ...badBytes, ...encoder.encode('"}')];
    const response = await worker.fetch(request("/v1/kofi/webhook", trackedStream(chunksOf(new Uint8Array(bytes), 1)).body), workerEnv);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_webhook" });
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM kofi_inbox").first()).toEqual({ count: 0 });
  });

  it("releases an errored stream and accepts a subsequent valid request", async () => {
    const body = new ReadableStream<Uint8Array>({ pull() { throw new Error("interrupted upload"); } }, { highWaterMark: 0 });
    const failed = await worker.fetch(request("/v1/activate", body), workerEnv);
    expect(failed.status).toBe(400);
    expect(body.locked).toBe(false);
    const recovered = await worker.fetch(request("/v1/activate", trackedStream([encoder.encode(validBody("/v1/activate"))]).body), workerEnv);
    expect(recovered.status).toBe(200);
  });

  it("handles an absent body without a service error", async () => {
    const response = await worker.fetch(request("/v1/activate", null), workerEnv);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid_request" });
  });

  it("also rejects an oversized upload through the local Worker service binding", async () => {
    const response = await SELF.fetch(request("/v1/activate", trackedStream([new Uint8Array(8193)]).body));
    expect(response.status).toBe(413);
    expect(await response.json()).toEqual({ error: "request_too_large" });
  });
});
