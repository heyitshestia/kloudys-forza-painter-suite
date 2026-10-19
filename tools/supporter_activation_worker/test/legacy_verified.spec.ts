import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import worker, { type Env } from "../src/index";
import { base64UrlToBytes, bytesToBase64Url, eligibleForLegacyVerifiedGrant, sha256Hex, signCommunityEntitlement } from "../src/protocol";

const SUBJECT = "11111111-1111-4111-8111-111111111111";
const OTHER_SUBJECT = "22222222-2222-4222-8222-222222222222";
const DEVICE = "a".repeat(64);
// Synthetic historical dates only, not a proposed production cutover.
const CREATED = "2020-01-01T00:00:00.000Z";
const CUTOFF = "2020-02-01T00:00:00.000Z";
type Envelope = { type: string; version: number; kid: string; payload: string; signature: string };
type Body = { status: string; entitlement: Envelope; legacy_verified_grant?: Envelope };

function payload(envelope: Envelope): Record<string, string> {
  return JSON.parse(new TextDecoder().decode(base64UrlToBytes(envelope.payload)));
}

async function seedLicense(created = CREATED, includeDevice = true) {
  const keyId = "b".repeat(64);
  const proof = bytesToBase64Url(new Uint8Array(384).fill(7));
  const proofHash = await sha256Hex(base64UrlToBytes(proof));
  await env.DB.prepare(
    "INSERT INTO licenses(key_id,signature_sha256,device_id,activated_at,created_at,updated_at) VALUES (?1,?2,?3,?4,?4,?4)",
  ).bind(keyId, proofHash, DEVICE, created).run();
  return { protocol: 1, key_id: keyId, key_proof: proof, ...(includeDevice ? { device_id: DEVICE } : {}),
    nonce: bytesToBase64Url(crypto.getRandomValues(new Uint8Array(32))), community_subject: SUBJECT };
}

async function issue(request: object, cutoff: string | undefined = CUTOFF, route = "community-entitlement") {
  const bindings = { ...env, COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF: cutoff } as unknown as Env;
  return worker.fetch(new Request(`https://activation.test/v1/${route}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
  }), bindings);
}

async function validSignature(envelope: Envelope) {
  const pem = (env as unknown as { KOFI_INBOX_PUBLIC_KEY_PEM: string }).KOFI_INBOX_PUBLIC_KEY_PEM;
  const der = Uint8Array.from(atob(pem.replace(/-----[^-]+-----|\s/g, "")), (char) => char.charCodeAt(0));
  const key = await crypto.subtle.importKey("spki", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key,
    base64UrlToBytes(envelope.signature) as BufferSource, base64UrlToBytes(envelope.payload) as BufferSource);
}

beforeEach(async () => { await env.DB.prepare("DELETE FROM licenses").run(); });

describe.each([true, false])("optional legacy Verified grant (device field: %s)", (includeDevice) => {
  const seed = (created = CREATED) => seedLicense(created, includeDevice);
  it("enforces the exact server-time boundary and rejects non-string configuration", () => {
    const now = Date.parse(CUTOFF);
    expect(eligibleForLegacyVerifiedGrant(CREATED, CUTOFF, now)).toBe(true);
    expect(eligibleForLegacyVerifiedGrant(CREATED, CUTOFF, now - 1)).toBe(false);
    expect(eligibleForLegacyVerifiedGrant(CUTOFF, CUTOFF, now)).toBe(true);
    for (const bad of [null, true, now, {}, [], ""])
      expect(eligibleForLegacyVerifiedGrant(CREATED, bad, now)).toBe(false);
    expect(eligibleForLegacyVerifiedGrant(CREATED, CUTOFF, NaN)).toBe(false);
  });
  it("signs exactly paired claims without changing the v1 entitlement or exposing key/device identity", async () => {
    const request = await seed();
    const response = await issue(request);
    expect(response.status).toBe(200);
    const body = await response.json() as Body;
    const grant = body.legacy_verified_grant!;
    expect(Object.keys(body).sort()).toEqual(["entitlement", "legacy_verified_grant", "status"]);
    expect(grant).toMatchObject({ type: "kfps.community.legacy-verified-grant", version: 1, kid: body.entitlement.kid });
    const entitlement = payload(body.entitlement);
    expect(payload(grant)).toEqual({
      schema: "kfps.community.legacy-verified.v1", audience: "kfps-community-verified-v1",
      subject: SUBJECT, nonce: request.nonce, entitlement_id: entitlement.entitlement_id,
      issued_at: entitlement.issued_at, expires_at: entitlement.expires_at,
      license_created_at: CREATED, eligibility_cutoff: CUTOFF,
    });
    expect(await validSignature(grant)).toBe(true);
    expect(await validSignature(body.entitlement)).toBe(true);
    expect(body.entitlement).toEqual(await signCommunityEntitlement(env.ACTIVATION_PRIVATE_KEY_PEM,
      env.ACTIVATION_KEY_ID, SUBJECT, entitlement.entitlement_id, request.nonce, entitlement.issued_at, entitlement.expires_at));
    expect(JSON.stringify(payload(grant))).not.toContain(DEVICE);
    expect(JSON.stringify(payload(grant))).not.toContain(request.key_id);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it.each([undefined, "", "bad", "2020-02-01", "2020-02-01T00:00:00Z", "2020-02-01T00:00:00.000+00:00",
    "2020-02-30T00:00:00.000Z", " 2020-02-01T00:00:00.000Z", "0000-02-01T00:00:00.000Z", "9999-01-01T00:00:00.000Z"])(
    "omits only the optional grant for missing/invalid/future cutoff %s", async (cutoff) => {
      const request = await seed();
      // Explicit undefined must not take issue()'s test default.
      const bindings = { ...env, COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF: cutoff } as unknown as Env;
      const response = await worker.fetch(new Request("https://activation.test/v1/community-entitlement", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
      }), bindings);
      expect(response.status).toBe(200);
      const body = await response.json() as Body;
      expect(Object.keys(body).sort()).toEqual(["entitlement", "status"]);
      expect(await validSignature(body.entitlement)).toBe(true);
      const { community_subject: _subject, ...activation } = request;
      expect((await issue({ ...activation, device_id: DEVICE }, cutoff, "activate")).status).toBe(200);
    });

  it.each(["2020-02-01T00:00:00.001Z", "9999-01-01T00:00:00.000Z", "bad", "2020-01-01T00:00:00Z",
    "2020-02-30T00:00:00.000Z", "0000-01-01T00:00:00.000Z"])("does not grandfather an ineligible creation date %s", async (created) => {
    const response = await issue(await seed(created));
    expect(response.status).toBe(200);
    expect(await response.json()).not.toHaveProperty("legacy_verified_grant");
  });

  it("includes the exact creation cutoff boundary", async () => {
    expect(await (await issue(await seed(CUTOFF))).json()).toHaveProperty("legacy_verified_grant");
  });

  it.each(["revoked", "wrong-proof", "wrong-account"])("never mints for %s", async (kind) => {
    const request = await seed();
    if (kind === "revoked") await env.DB.prepare("UPDATE licenses SET status='revoked'").run();
    if (kind === "wrong-proof") request.key_proof = bytesToBase64Url(new Uint8Array(384).fill(8));
    if (kind === "wrong-account") { await issue(request); request.community_subject = OTHER_SUBJECT; }
    const response = await issue(request);
    expect(response.status).toBe(kind === "wrong-account" ? 409 : 403);
    expect(await response.json()).not.toHaveProperty("legacy_verified_grant");
  });

  it("keeps the same entitlement identity but binds each refresh to its own nonce", async () => {
    const request = await seed();
    const first = await (await issue(request)).json() as Body;
    request.nonce = bytesToBase64Url(crypto.getRandomValues(new Uint8Array(32)));
    const second = await (await issue(request)).json() as Body;
    expect(payload(second.legacy_verified_grant!).entitlement_id).toBe(payload(first.entitlement).entitlement_id);
    expect(payload(second.legacy_verified_grant!).nonce).toBe(request.nonce);
    expect(payload(second.legacy_verified_grant!).nonce).not.toBe(payload(first.legacy_verified_grant!).nonce);
  });
});
