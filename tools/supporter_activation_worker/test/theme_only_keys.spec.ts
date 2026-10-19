import { env, SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";
import { createAdminSignatureForTesting } from "../src/admin_auth";
import { base64UrlToBytes, bytesToBase64Url, canonicalJson, sha256Hex, type SignedEnvelope } from "../src/protocol";

const KEY_ID = "b".repeat(64);
const PROOF = bytesToBase64Url(new Uint8Array(384).fill(7));
const DEVICE = "a".repeat(64);
const OTHER_DEVICE = "c".repeat(64);
const SUBJECT = "11111111-1111-4111-8111-111111111111";
const OTHER_SUBJECT = "22222222-2222-4222-8222-222222222222";
// Synthetic historical dates; these are not production cutoff decisions.
const CREATED = "2020-01-01T00:00:00.000Z";
const CUTOFF = "2020-02-01T00:00:00.000Z";
const ROUTES = ["activate", "status", "deactivate"] as const;
type Route = typeof ROUTES[number];
type CommunityBody = { status: string; entitlement: SignedEnvelope; legacy_verified_grant?: SignedEnvelope };

function nonce(length = 32) {
  return bytesToBase64Url(crypto.getRandomValues(new Uint8Array(length)));
}

function requestBody(device: string | undefined = DEVICE): Record<string, unknown> {
  return { protocol: 1, key_id: KEY_ID, key_proof: PROOF, nonce: nonce(),
    ...(device === undefined ? {} : { device_id: device }) };
}

function communityBody(device?: string): Record<string, unknown> {
  const body = requestBody();
  if (device === undefined) delete body.device_id;
  else body.device_id = device;
  return { ...body, community_subject: SUBJECT };
}

function post(route: string, body: unknown) {
  return SELF.fetch(`https://activation.test/v1/${route}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}

function issue(body: unknown, overrides: Partial<Env> = {}) {
  return worker.fetch(new Request("https://activation.test/v1/community-entitlement", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }), { ...env, COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF: CUTOFF, ...overrides } as unknown as Env);
}

async function row() {
  return env.DB.prepare("SELECT * FROM licenses WHERE key_id = ?1").bind(KEY_ID).first<Record<string, unknown>>();
}

async function seed(device: string | null = DEVICE, activated: string | null = CREATED, status = "active") {
  await env.DB.prepare(
    `INSERT INTO licenses(key_id, signature_sha256, status, device_id, activated_at,
       conflict_count, first_conflict_at, last_conflict_at, reset_count, last_reset_at, created_at, updated_at)
     VALUES (?1, ?2, ?3, ?4, ?5, 17, ?6, ?6, 3, ?6, ?6, ?6)`,
  ).bind(KEY_ID, await sha256Hex(base64UrlToBytes(PROOF)), status, device, activated, CREATED).run();
}

async function verifiedPayload(envelope: SignedEnvelope, type: string) {
  expect(Object.keys(envelope).sort()).toEqual(["kid", "payload", "signature", "type", "version"]);
  expect(envelope).toMatchObject({ type, version: 1, kid: env.ACTIVATION_KEY_ID });
  const pem = (env as unknown as { KOFI_INBOX_PUBLIC_KEY_PEM: string }).KOFI_INBOX_PUBLIC_KEY_PEM;
  const der = Uint8Array.from(atob(pem.replace(/-----[^-]+-----|\s/g, "")), (char) => char.charCodeAt(0));
  const key = await crypto.subtle.importKey("spki", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  expect(await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key,
    base64UrlToBytes(envelope.signature) as BufferSource, base64UrlToBytes(envelope.payload) as BufferSource)).toBe(true);
  const text = new TextDecoder().decode(base64UrlToBytes(envelope.payload));
  const payload = JSON.parse(text) as Record<string, string>;
  expect(text).toBe(canonicalJson(payload));
  return payload;
}

async function expectNoHistoryWrites() {
  expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM test_license_writes WHERE kind = 'history'").first()).toEqual({ count: 0 });
}

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM licenses").run();
  await env.DB.batch([
    env.DB.prepare("CREATE TABLE IF NOT EXISTS test_license_writes (kind TEXT NOT NULL)"),
    env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS test_any_license_update AFTER UPDATE ON licenses
      BEGIN INSERT INTO test_license_writes VALUES ('any'); END`),
    env.DB.prepare(`CREATE TRIGGER IF NOT EXISTS test_history_update AFTER UPDATE OF device_id, activated_at,
      conflict_count, first_conflict_at, last_conflict_at, reset_count, last_reset_at, status, created_at ON licenses
      BEGIN INSERT INTO test_license_writes VALUES ('history'); END`),
    env.DB.prepare("DELETE FROM test_license_writes"),
  ]);
});

describe("theme-only legacy compatibility", () => {
  it.each([true, false])("keeps exact signed v1 formats across machines with historical registration %s", async (historical) => {
    await seed(historical ? DEVICE : null, historical ? CREATED : null);
    const before = await row();
    for (const device of [DEVICE, OTHER_DEVICE, "d".repeat(64)]) {
      for (const route of ROUTES) {
        const request = requestBody(device);
        const response = await post(route, request);
        expect(response.status).toBe(200);
        expect(response.headers.get("cache-control")).toBe("no-store");
        const body = await response.json() as { status: string; receipt?: SignedEnvelope; decision?: SignedEnvelope };
        expect(Object.keys(body).sort()).toEqual([route === "activate" ? "receipt" : "decision", "status"]);
        expect(body.status).toBe(route === "deactivate" ? "deactivated" : "active");
        const type = route === "activate" ? "activation" : route === "status" ? "activation-status" : "activation-decision";
        const payload = await verifiedPayload((body.receipt ?? body.decision)!, `kfps.supporter.${type}`);
        const timeField = route === "activate" ? "activated_at" : route === "status" ? "checked_at" : "decided_at";
        const expected = route === "activate" ? [timeField, "device_id", "key_id", "schema"]
          : [timeField, "device_id", "key_id", "nonce", "schema", "status"];
        expect(Object.keys(payload).sort()).toEqual(expected.sort());
        expect(payload).toMatchObject({ key_id: KEY_ID, device_id: device,
          schema: route === "activate" ? "kfps.activation.v1" : `kfps.activation.${route === "status" ? "status" : "decision"}.v1` });
        expect(Number.isFinite(Date.parse(payload[timeField]))).toBe(true);
        if (route !== "activate") expect(payload).toMatchObject({ nonce: request.nonce, status: body.status });
      }
    }
    expect(await row()).toEqual(before);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM test_license_writes").first()).toEqual({ count: 0 });
  });

  it.each(ROUTES)("%s never signs for unknown IDs or bad registered proofs", async (route) => {
    await seed();
    const before = await row();
    for (const request of [
      { ...requestBody(), key_id: "f".repeat(64) },
      { ...requestBody(), key_proof: bytesToBase64Url(new Uint8Array(384).fill(8)) },
    ]) {
      const response = await post(route, request);
      expect(response.status).toBe(403);
      expect(await response.json()).toEqual({ error: "not_eligible" });
    }
    expect(await row()).toEqual(before);
    await expectNoHistoryWrites();
  });

  it.each(ROUTES)("%s retains revoked eligibility and authenticated signed denial/status", async (route: Route) => {
    await seed(DEVICE, CREATED, "revoked");
    const before = await row();
    const request = requestBody(OTHER_DEVICE);
    const response = await post(route, request);
    expect(response.status).toBe(route === "status" ? 200 : 403);
    const body = await response.json() as { status: string; decision: SignedEnvelope };
    const expectedStatus = route === "status" ? "revoked" : "not_eligible";
    expect(body.status).toBe(expectedStatus);
    const payload = await verifiedPayload(body.decision,
      `kfps.supporter.activation-${route === "status" ? "status" : "decision"}`);
    expect(payload).toMatchObject({ status: expectedStatus, key_id: KEY_ID, device_id: OTHER_DEVICE, nonce: request.nonce });
    expect(await row()).toEqual(before);
    await expectNoHistoryWrites();
  });

  it("does not change the row during simultaneous different-machine compatibility requests", async () => {
    await seed();
    const before = await row();
    const responses = await Promise.all(ROUTES.flatMap((route) =>
      [DEVICE, OTHER_DEVICE].map((device) => post(route, requestBody(device)))));
    expect(responses.map((response) => response.status)).toEqual([200, 200, 200, 200, 200, 200]);
    expect(await row()).toEqual(before);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM test_license_writes").first()).toEqual({ count: 0 });
  });
});

describe.each([undefined, DEVICE, OTHER_DEVICE])("Community device-independent recognition (device %s)", (device) => {
  it.each(["none", "device-only", "timestamp-only", "both"])("recognizes eligible existing holders with historical fields: %s", async (history) => {
    await seed(history === "device-only" || history === "both" ? DEVICE : null,
      history === "timestamp-only" || history === "both" ? CREATED : null);
    const before = await row();
    const request = communityBody(device);
    const response = await issue(request);
    expect(response.status).toBe(200);
    const body = await response.json() as CommunityBody;
    const entitlement = await verifiedPayload(body.entitlement, "kfps.supporter.community-entitlement");
    const grant = await verifiedPayload(body.legacy_verified_grant!, "kfps.community.legacy-verified-grant");
    expect(entitlement).toMatchObject({ subject: SUBJECT, nonce: request.nonce, audience: "kfps-community-v1" });
    expect(grant).toEqual({ ...entitlement, schema: "kfps.community.legacy-verified.v1",
      audience: "kfps-community-verified-v1", license_created_at: CREATED, eligibility_cutoff: CUTOFF });
    expect(entitlement).not.toHaveProperty("device_id");
    expect(entitlement).not.toHaveProperty("key_id");
    expect(Date.parse(entitlement.expires_at) - Date.parse(entitlement.issued_at)).toBe(15 * 60 * 1000);
    const after = await row();
    for (const name of Object.keys(before!)) {
      if (!["community_subject_hash", "community_entitlement_id", "community_bound_at", "updated_at"].includes(name)) {
        expect(after![name]).toEqual(before![name]);
      }
    }
    await expectNoHistoryWrites();
  });

  it.each(["unknown-key", "wrong-proof", "revoked"])("does not bind or grant for %s", async (kind) => {
    await seed(DEVICE, CREATED, kind === "revoked" ? "revoked" : "active");
    const before = await row();
    const request = communityBody(device);
    if (kind === "unknown-key") request.key_id = "f".repeat(64);
    if (kind === "wrong-proof") request.key_proof = bytesToBase64Url(new Uint8Array(384).fill(8));
    const response = await issue(request);
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "not_eligible" });
    expect(await row()).toEqual(before);
    await expectNoHistoryWrites();
  });
});

describe("Community binding and bounded protocol", () => {
  it("retries the same subject idempotently across old/new clients without transferring its identity", async () => {
    await seed(null, null);
    const request = communityBody();
    const firstResponse = await issue(request);
    expect(firstResponse.status).toBe(200);
    const first = await firstResponse.json() as CommunityBody;
    const firstPayload = await verifiedPayload(first.entitlement, "kfps.supporter.community-entitlement");
    const replay = await issue(request);
    expect(replay.status).toBe(200);
    const replayPayload = await verifiedPayload((await replay.json() as CommunityBody).entitlement, "kfps.supporter.community-entitlement");
    expect(replayPayload).toMatchObject({ entitlement_id: firstPayload.entitlement_id, subject: SUBJECT, nonce: request.nonce });
    const bound = await row();
    for (const device of [undefined, OTHER_DEVICE]) {
      const response = await issue({ ...request, ...(device ? { device_id: device } : {}), community_subject: OTHER_SUBJECT });
      expect(response.status).toBe(409);
      expect(await response.json()).toEqual({ error: "community_account_already_bound" });
      expect(await row()).toEqual(bound);
    }
    const refresh = { ...request, device_id: OTHER_DEVICE, nonce: nonce() };
    const refreshed = await issue(refresh);
    expect(refreshed.status).toBe(200);
    const body = await refreshed.json() as CommunityBody;
    const refreshedPayload = await verifiedPayload(body.legacy_verified_grant!, "kfps.community.legacy-verified-grant");
    expect(refreshedPayload).toMatchObject({ entitlement_id: firstPayload.entitlement_id, subject: SUBJECT, nonce: refresh.nonce });
    expect(refreshedPayload.nonce).not.toBe(firstPayload.nonce);
    expect((await row())!.community_bound_at).toBe(bound!.community_bound_at);
    await expectNoHistoryWrites();
  });

  it.each([true, false])("keeps the account claim atomic for simultaneous requests (same subject %s)", async (sameSubject) => {
    await seed(null, null);
    const requests = [communityBody(), { ...communityBody(OTHER_DEVICE), community_subject: sameSubject ? SUBJECT : OTHER_SUBJECT }];
    const responses = await Promise.all(requests.map((request) => issue(request)));
    expect(responses.map((response) => response.status).sort()).toEqual(sameSubject ? [200, 200] : [200, 409]);
    const accepted = [];
    for (let index = 0; index < responses.length; index += 1) {
      const response = responses[index];
      if (response.status === 200) {
        const body = await response.json() as CommunityBody;
        const payload = await verifiedPayload(body.entitlement, "kfps.supporter.community-entitlement");
        expect(payload.subject).toBe(requests[index].community_subject);
        accepted.push(payload.entitlement_id);
      } else expect(await response.json()).toEqual({ error: "community_account_already_bound" });
    }
    expect(new Set(accepted).size).toBe(1);
    await expectNoHistoryWrites();
  });

  it.each([true, false])("rejects malformed and extra Community fields (old format %s)", async (oldFormat) => {
    await seed();
    const before = await row();
    const valid = communityBody(oldFormat ? DEVICE : undefined);
    const variants: unknown[] = [null, [], "request", {},
      ...[0, 2, "1", null].map((protocol) => ({ ...valid, protocol })),
      ...[null, "", "g".repeat(64), "a".repeat(63), 123].map((device_id) => ({ ...valid, device_id })),
      ...[null, "", "not-a-uuid", `${SUBJECT} `].map((community_subject) => ({ ...valid, community_subject })),
      ...[null, "bad=", nonce(15), nonce(65)].map((value) => ({ ...valid, nonce: value })),
      ...[null, "bad=", bytesToBase64Url(new Uint8Array(383)), bytesToBase64Url(new Uint8Array(385))]
        .map((key_proof) => ({ ...valid, key_proof })),
      { ...valid, license_created_at: CREATED }, { ...valid, eligibility_cutoff: CUTOFF },
      { ...valid, key_id: "g".repeat(64) }, { ...valid, extra: true },
    ];
    for (const field of ["protocol", "key_id", "key_proof", "nonce", "community_subject"]) {
      const missing = { ...valid };
      delete missing[field];
      variants.push(missing);
    }
    for (const body of variants) {
      const response = await issue(body);
      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: "invalid_request" });
    }
    expect(await row()).toEqual(before);
  });

  it.each(ROUTES)("retains required legacy device and bounded proof/nonce validation on %s", async (route) => {
    await seed();
    const body = requestBody();
    const { device_id: _device, ...withoutDevice } = body;
    for (const invalid of [withoutDevice, { ...body, device_id: null }, { ...body, extra: true },
      { ...body, protocol: 2 }, { ...body, nonce: nonce(15) }, { ...body, nonce: nonce(65) },
      { ...body, key_proof: bytesToBase64Url(new Uint8Array(383)) }]) {
      expect((await post(route, invalid)).status).toBe(400);
    }
    for (const length of [16, 64]) expect((await post(route, { ...body, nonce: nonce(length) })).status).toBe(200);
  });

  it.each([16, 64])("accepts nonce boundary %s in both Community shapes", async (length) => {
    await seed(null, null);
    for (const device of [undefined, OTHER_DEVICE]) {
      expect((await issue({ ...communityBody(device), nonce: nonce(length) })).status).toBe(200);
    }
  });

  it("does not grandfather a newly registered key even without device history", async () => {
    await seed(null, null);
    await env.DB.prepare("UPDATE licenses SET created_at = ?1").bind(new Date().toISOString()).run();
    await env.DB.prepare("DELETE FROM test_license_writes").run();
    for (const device of [undefined, OTHER_DEVICE]) {
      const response = await issue(communityBody(device));
      expect(response.status).toBe(200);
      const body = await response.json() as CommunityBody;
      expect(body).not.toHaveProperty("legacy_verified_grant");
      expect(await verifiedPayload(body.entitlement, "kfps.supporter.community-entitlement")).toMatchObject({ subject: SUBJECT });
    }
    await expectNoHistoryWrites();
  });

  it("preserves the stored account and entitlement across signing failure, retry, and module restart", async () => {
    await seed(null, null);
    const request = communityBody();
    const failed = await issue(request, { ACTIVATION_PRIVATE_KEY_PEM: "invalid-test-key" });
    expect(failed.status).toBe(500);
    expect(await failed.json()).toEqual({ error: "service_error" });
    const claimed = await row();
    expect(claimed!.community_entitlement_id).toEqual(expect.any(String));
    expect((await issue({ ...request, community_subject: OTHER_SUBJECT })).status).toBe(409);
    vi.resetModules();
    const restarted = (await import("../src/index")).default;
    const retry = { ...request, nonce: nonce() };
    const recovered = await restarted.fetch(new Request("https://activation.test/v1/community-entitlement", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(retry),
    }), { ...env, COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF: CUTOFF } as unknown as Env);
    expect(recovered.status).toBe(200);
    const body = await recovered.json() as CommunityBody;
    const grant = await verifiedPayload(body.legacy_verified_grant!, "kfps.community.legacy-verified-grant");
    expect(grant).toMatchObject({ subject: SUBJECT, nonce: retry.nonce, entitlement_id: claimed!.community_entitlement_id });
    expect((await row())!.community_bound_at).toBe(claimed!.community_bound_at);
    await expectNoHistoryWrites();
  });

  it.each([...ROUTES, "community-entitlement"])("retains body bounds and media-type checks on %s", async (route) => {
    await seed();
    const before = await row();
    const body = route === "community-entitlement" ? communityBody() : requestBody();
    const headerCases: Record<string, string>[] = [{ "Content-Type": "text/plain" }, { "Content-Type": "application/json", "Content-Length": "8193" }];
    for (const headers of headerCases) {
      const response = await SELF.fetch(`https://activation.test/v1/${route}`, { method: "POST", headers, body: JSON.stringify(body) });
      expect(response.status).toBe(headers["Content-Type"] === "text/plain" ? 415 : 400);
    }
    const oversized = `${JSON.stringify(body)}${" ".repeat(8193)}`;
    const response = await SELF.fetch(`https://activation.test/v1/${route}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: oversized,
    });
    expect(response.status).toBe(400);
    expect(await row()).toEqual(before);
  });
});

describe("admin security boundary remains separate from key compatibility", () => {
  it.each([
    ["GET", "/v1/admin/licenses"], ["GET", "/v1/admin/kofi/events"],
    ["POST", "/v1/admin/licenses/import"], ["POST", "/v1/admin/licenses/mutate"], ["POST", "/v1/admin/kofi/ack"],
  ])("requires admin authentication for %s %s even with a valid key proof", async (method, path) => {
    await seed();
    const before = await row();
    const response = await SELF.fetch(`https://activation.test${path}`, {
      method, headers: { "Content-Type": "application/json", Authorization: `Bearer ${PROOF}` },
      body: method === "GET" ? undefined : JSON.stringify(requestBody()),
    });
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "admin_auth_failed" });
    expect(await row()).toEqual(before);
  });

  it("retains HMAC body/path/time authentication and mutation replay protection", async () => {
    // Audit inserts affect D1's change count; admin mutations intentionally write.
    await env.DB.batch([
      env.DB.prepare("DROP TRIGGER test_any_license_update"),
      env.DB.prepare("DROP TRIGGER test_history_update"),
    ]);
    await seed();
    const path = "/v1/admin/licenses/mutate";
    const body = JSON.stringify({ action: "reset_community", key_id: KEY_ID });
    const requestId = crypto.randomUUID();
    const timestamp = String(Math.floor(Date.now() / 1000));
    const secret = "test-admin-secret-that-is-longer-than-thirty-two-characters";
    const signature = await createAdminSignatureForTesting("POST", path, timestamp, requestId, body, secret);
    const headers = { "Content-Type": "application/json", "X-KFPS-Admin-Timestamp": timestamp,
      "X-KFPS-Admin-Request-Id": requestId, "X-KFPS-Admin-Signature": signature };
    const before = await row();
    for (const [url, rawBody] of [[`${path}?tampered=1`, body], [path, body.replace("reset_community", "revoke")]]) {
      expect((await SELF.fetch(`https://activation.test${url}`, { method: "POST", headers, body: rawBody })).status).toBe(401);
    }
    const oldTimestamp = String(Number(timestamp) - 301);
    const expired = await createAdminSignatureForTesting("POST", path, oldTimestamp, requestId, body, secret);
    expect((await SELF.fetch(`https://activation.test${path}`, { method: "POST", body,
      headers: { ...headers, "X-KFPS-Admin-Timestamp": oldTimestamp, "X-KFPS-Admin-Signature": expired } })).status).toBe(401);
    expect(await row()).toEqual(before);
    const accepted = await SELF.fetch(`https://activation.test${path}`, { method: "POST", headers, body });
    expect(accepted.status).toBe(200);
    const after = await row();
    const replay = await SELF.fetch(`https://activation.test${path}`, { method: "POST", headers, body });
    expect(replay.status).toBe(409);
    expect(await replay.json()).toEqual({ error: "admin_request_replayed" });
    expect(await row()).toEqual(after);
  });
});
