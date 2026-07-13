import { env, SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { createAdminSignatureForTesting } from "../src/admin_auth";
import { bytesToBase64Url, sha256Hex } from "../src/protocol";

const ADMIN_SECRET = "test-admin-secret-that-is-longer-than-thirty-two-characters";

function randomBytes(length: number): Uint8Array {
  const value = new Uint8Array(length);
  crypto.getRandomValues(value);
  return value;
}

async function makeLicense(): Promise<{ keyId: string; proof: string; proofHash: string }> {
  const keyId = Array.from(randomBytes(32), (byte) => byte.toString(16).padStart(2, "0")).join("");
  const proofBytes = randomBytes(384);
  return { keyId, proof: bytesToBase64Url(proofBytes), proofHash: await sha256Hex(proofBytes) };
}

function deviceId(fill: string): string {
  return fill.repeat(64).slice(0, 64);
}

async function activate(keyId: string, proof: string, device: string): Promise<Response> {
  return SELF.fetch("https://activation.test/v1/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      protocol: 1,
      key_id: keyId,
      key_proof: proof,
      device_id: device,
      nonce: bytesToBase64Url(randomBytes(32)),
    }),
  });
}

async function deactivate(keyId: string, proof: string, device: string): Promise<Response> {
  return SELF.fetch("https://activation.test/v1/deactivate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      protocol: 1,
      key_id: keyId,
      key_proof: proof,
      device_id: device,
      nonce: bytesToBase64Url(randomBytes(32)),
    }),
  });
}

async function adminFetch(path: string, method = "GET", body = ""): Promise<Response> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const requestId = crypto.randomUUID();
  const signature = await createAdminSignatureForTesting(method, path, timestamp, requestId, body, ADMIN_SECRET);
  return SELF.fetch(`https://activation.test${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-KFPS-Admin-Timestamp": timestamp,
      "X-KFPS-Admin-Request-Id": requestId,
      "X-KFPS-Admin-Signature": signature,
    },
    body: method === "GET" ? undefined : body,
  });
}

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM admin_events"),
    env.DB.prepare("DELETE FROM licenses"),
    env.DB.prepare("DELETE FROM kofi_inbox"),
  ]);
});

describe("activation worker", () => {
  it("reports health without exposing configuration", async () => {
    const response = await SELF.fetch("https://activation.test/v1/health");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ service: "kfps-supporter-activation", protocol: 1, status: "ok" });
  });

  it("claims once, repairs idempotently, and records a duplicate", async () => {
    const license = await makeLicense();
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO licenses(key_id, signature_sha256, created_at, updated_at) VALUES (?1, ?2, ?3, ?3)",
    ).bind(license.keyId, license.proofHash, now).run();

    const first = await activate(license.keyId, license.proof, deviceId("a"));
    expect(first.status).toBe(200);
    expect((await first.json() as { status: string }).status).toBe("active");

    const repair = await activate(license.keyId, license.proof, deviceId("a"));
    expect(repair.status).toBe(200);

    const duplicate = await activate(license.keyId, license.proof, deviceId("b"));
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { status: string }).status).toBe("already_activated");

    const row = await env.DB.prepare("SELECT device_id, conflict_count FROM licenses WHERE key_id = ?1")
      .bind(license.keyId).first<{ device_id: string; conflict_count: number }>();
    expect(row?.device_id).toBe(deviceId("a"));
    expect(row?.conflict_count).toBe(1);
  });

  it("allows exactly one winner for simultaneous different-device claims", async () => {
    const license = await makeLicense();
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO licenses(key_id, signature_sha256, created_at, updated_at) VALUES (?1, ?2, ?3, ?3)",
    ).bind(license.keyId, license.proofHash, now).run();
    const responses = await Promise.all([
      activate(license.keyId, license.proof, deviceId("c")),
      activate(license.keyId, license.proof, deviceId("d")),
    ]);
    expect(responses.map((response) => response.status).sort()).toEqual([200, 409]);
  });

  it("does not count an invalid proof as a duplicate", async () => {
    const license = await makeLicense();
    const wrong = await makeLicense();
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO licenses(key_id, signature_sha256, device_id, activated_at, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?4, ?4)",
    ).bind(license.keyId, license.proofHash, deviceId("e"), now).run();
    const response = await activate(license.keyId, wrong.proof, deviceId("f"));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "not_eligible" });
    const row = await env.DB.prepare("SELECT conflict_count FROM licenses WHERE key_id = ?1")
      .bind(license.keyId).first<{ conflict_count: number }>();
    expect(row?.conflict_count).toBe(0);
  });

  it("does not sign a deactivation denial for an invalid proof", async () => {
    const license = await makeLicense();
    const wrong = await makeLicense();
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO licenses(key_id, signature_sha256, device_id, activated_at, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?4, ?4)",
    ).bind(license.keyId, license.proofHash, deviceId("e"), now).run();

    const response = await deactivate(license.keyId, wrong.proof, deviceId("e"));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "not_eligible" });
  });

  it("signs a denial only for a known revoked proof", async () => {
    const license = await makeLicense();
    const now = new Date().toISOString();
    await env.DB.prepare(
      "INSERT INTO licenses(key_id, signature_sha256, status, created_at, updated_at) VALUES (?1, ?2, 'revoked', ?3, ?3)",
    ).bind(license.keyId, license.proofHash, now).run();
    const response = await activate(license.keyId, license.proof, deviceId("9"));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual(expect.objectContaining({
      status: "not_eligible",
      decision: expect.objectContaining({ type: "kfps.supporter.activation-decision" }),
    }));
  });

  it("requires authenticated admin requests and supports import, list, and reset", async () => {
    const unauthorized = await SELF.fetch("https://activation.test/v1/admin/licenses");
    expect(unauthorized.status).toBe(401);

    const license = await makeLicense();
    const importBody = JSON.stringify({ licenses: [{ key_id: license.keyId, signature_sha256: license.proofHash }] });
    const imported = await adminFetch("/v1/admin/licenses/import", "POST", importBody);
    expect(imported.status).toBe(200);

    expect((await activate(license.keyId, license.proof, deviceId("1"))).status).toBe(200);
    const listed = await adminFetch("/v1/admin/licenses?limit=10");
    expect(listed.status).toBe(200);
    const listPayload = await listed.json() as { licenses: Array<{ key_id: string; registered: boolean }> };
    expect(listPayload.licenses).toEqual(expect.arrayContaining([
      expect.objectContaining({ key_id: license.keyId, registered: true }),
    ]));

    const resetBody = JSON.stringify({ action: "reset", key_id: license.keyId });
    const reset = await adminFetch("/v1/admin/licenses/mutate", "POST", resetBody);
    expect(reset.status).toBe(200);
    expect((await activate(license.keyId, license.proof, deviceId("2"))).status).toBe(200);
  });

  it("accepts authenticated Ko-fi webhooks and stores only encrypted customer fields", async () => {
    const payment = {
      verification_token: "test-kofi-verification-token-2026",
      message_id: "kofi-message-0001",
      timestamp: "2026-07-13T20:00:00Z",
      type: "Donation",
      from_name: "Private Supporter",
      email: "private@example.test",
      amount: "5.00",
      currency: "EUR",
      kofi_transaction_id: "txn-private-0001",
      message: "Thank you",
    };
    const body = new URLSearchParams({ data: JSON.stringify(payment) }).toString();
    const response = await SELF.fetch("https://activation.test/v1/kofi/webhook", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    expect(response.status).toBe(200);
    const duplicate = await SELF.fetch("https://activation.test/v1/kofi/webhook", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    expect(duplicate.status).toBe(200);

    const stored = await env.DB.prepare("SELECT payload_encrypted FROM kofi_inbox").first<{ payload_encrypted: string }>();
    expect(stored?.payload_encrypted).not.toContain(payment.from_name);
    expect(stored?.payload_encrypted).not.toContain(payment.email);
    expect(stored?.payload_encrypted).not.toContain(payment.kofi_transaction_id);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM kofi_inbox").first<{ count: number }>()).toEqual({ count: 1 });

    const listed = await adminFetch("/v1/admin/kofi/events?limit=100&after=");
    expect(listed.status).toBe(200);
    const listPayload = await listed.json() as { events: Array<{ event_id: string; payload: { chunks: Record<string, string> } }> };
    expect(listPayload.events).toHaveLength(1);
    expect(Object.keys(listPayload.events[0].payload.chunks).sort()).toEqual(["buyer", "event", "purchase"]);

    const ackBody = JSON.stringify({ event_ids: [listPayload.events[0].event_id] });
    const acknowledged = await adminFetch("/v1/admin/kofi/ack", "POST", ackBody);
    expect(acknowledged.status).toBe(200);
    expect(await acknowledged.json()).toEqual({ acknowledged: 1, requested: 1 });
    const empty = await adminFetch("/v1/admin/kofi/events?limit=100&after=");
    expect((await empty.json() as { events: unknown[] }).events).toEqual([]);
  });

  it("rejects a Ko-fi webhook with the wrong verification token", async () => {
    const body = new URLSearchParams({
      data: JSON.stringify({ verification_token: "wrong-token-value", message_id: "kofi-message-0002" }),
    }).toString();
    const response = await SELF.fetch("https://activation.test/v1/kofi/webhook", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    expect(response.status).toBe(403);
    expect(await env.DB.prepare("SELECT COUNT(*) AS count FROM kofi_inbox").first<{ count: number }>()).toEqual({ count: 0 });
  });

  it("bounds and encrypts unusually long Ko-fi customer fields", async () => {
    const noisy = `\"\\${String.fromCharCode(1)}`.repeat(180);
    const payment = {
      verification_token: "test-kofi-verification-token-2026",
      message_id: "kofi-message-long-fields-0001",
      kofi_transaction_id: "transaction-long-fields-0001",
      timestamp: noisy,
      type: noisy,
      from_name: noisy,
      email: `${noisy}@example.test`,
      amount: noisy,
      currency: noisy,
      message: noisy,
      shop_items: [{ item_name: noisy }],
    };
    const body = new URLSearchParams({ data: JSON.stringify(payment) }).toString();
    const response = await SELF.fetch("https://activation.test/v1/kofi/webhook", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    expect(response.status).toBe(200);
    const stored = await env.DB.prepare("SELECT payload_encrypted FROM kofi_inbox").first<{ payload_encrypted: string }>();
    expect(stored?.payload_encrypted).not.toContain(noisy.slice(0, 12));
  });
});
