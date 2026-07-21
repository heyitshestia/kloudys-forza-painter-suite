import { env, SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { createAdminSignatureForTesting } from "../src/admin_auth";

const ADMIN_SECRET = "test-rtti-admin-secret-that-is-longer-than-thirty-two-characters";

function validProfile(): Record<string, unknown> {
  return {
    game: "fh6",
    module_size: 187904000,
    descriptor_offset: 173585832,
    vtable_offsets: [116506584],
    update_code: "82282983460368",
    base_class_count: 4,
    game_build: "3.398.92.0",
    created_utc: "2026-07-15T12:33:37Z",
    calibrator_version: "3.0.0",
    evidence: {
      workflow: "six_step_template_calibration",
      confidence: "high",
      scan_count: 6,
      distinct_counts: [3000, 2997, 2994, 2991, 2988, 2985],
    },
  };
}

async function adminFetch(path: string, method = "GET", body = ""): Promise<Response> {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const requestId = crypto.randomUUID();
  const signature = await createAdminSignatureForTesting(method, path, timestamp, requestId, body, ADMIN_SECRET);
  return SELF.fetch(`https://rtti.test${path}`, {
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

async function createAndEnroll(name = "Trusted Helper") {
  const createdResponse = await adminFetch("/v1/admin/helpers/create", "POST", JSON.stringify({ name }));
  expect(createdResponse.status).toBe(201);
  const created = await createdResponse.json() as { helper_id: string; enrollment_code: string };
  const deviceId = "a".repeat(64);
  const enrolledResponse = await SELF.fetch("https://rtti.test/v1/enroll", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ protocol: 1, enrollment_code: created.enrollment_code, device_id: deviceId }),
  });
  expect(enrolledResponse.status).toBe(200);
  const enrolled = await enrolledResponse.json() as { credential: string };
  return { ...created, deviceId, credential: enrolled.credential };
}

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM submissions"),
    env.DB.prepare("DELETE FROM profiles"),
    env.DB.prepare("DELETE FROM helpers"),
    env.DB.prepare("DELETE FROM auto_enrollment_campaigns"),
    env.DB.prepare("DELETE FROM registry_state"),
    env.DB.prepare("DELETE FROM admin_events"),
  ]);
});

describe("FH6 RTTI relay", () => {
  it("exposes health and an empty privacy-safe registry", async () => {
    expect(await (await SELF.fetch("https://rtti.test/v1/health")).json()).toEqual({
      service: "kfps-fh6-rtti-registry", protocol: 1, status: "ok",
    });
    const response = await SELF.fetch("https://rtti.test/v1/RTTI.dat");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ format: "kfps_fh6_rtti_registry_v1", updated_utc: "", profiles: [] });
  });

  it("enrolls a helper once and publishes a complete calibrated profile", async () => {
    const helper = await createAndEnroll();
    const reused = await SELF.fetch("https://rtti.test/v1/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ protocol: 1, enrollment_code: helper.enrollment_code, device_id: helper.deviceId }),
    });
    expect(reused.status).toBe(403);

    const profile = { ...validProfile(), pid: 12345, path: "C:\\private\\forzahorizon6.exe" };
    const submitted = await SELF.fetch("https://rtti.test/v1/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${helper.credential}` },
      body: JSON.stringify({ protocol: 1, device_id: helper.deviceId, profile }),
    });
    expect(submitted.status).toBe(200);
    expect(await submitted.json()).toEqual(expect.objectContaining({ accepted: true, profile_id: "fh6-4cc182a67116f120ea47" }));

    const registry = await (await SELF.fetch("https://rtti.test/v1/RTTI.dat")).json() as { profiles: Array<Record<string, unknown>> };
    expect(registry.profiles).toHaveLength(1);
    expect(registry.profiles[0]).not.toHaveProperty("pid");
    expect(registry.profiles[0]).not.toHaveProperty("path");
  });

  it("allows only one winner when the same one-time enrollment is raced", async () => {
    const createdResponse = await adminFetch("/v1/admin/helpers/create", "POST", JSON.stringify({ name: "Race Helper" }));
    const created = await createdResponse.json() as { enrollment_code: string };
    const payload = JSON.stringify({ protocol: 1, enrollment_code: created.enrollment_code, device_id: "f".repeat(64) });
    const responses = await Promise.all([
      SELF.fetch("https://rtti.test/v1/enroll", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload }),
      SELF.fetch("https://rtti.test/v1/enroll", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload }),
    ]);
    const statuses = responses.map((response) => response.status).sort();
    expect(statuses[0]).toBe(200);
    expect([403, 409]).toContain(statuses[1]);
  });

  it("auto-enrolls new devices from a bounded reusable campaign without administrator approval", async () => {
    const createBody = JSON.stringify({ name: "Trusted automatic helpers", expires_days: 30, max_devices: 2 });
    const createdResponse = await adminFetch("/v1/admin/campaigns/create", "POST", createBody);
    expect(createdResponse.status).toBe(201);
    const campaign = await createdResponse.json() as { campaign_id: string; auto_enrollment_code: string };

    const enrollDevice = (fill: string) => SELF.fetch("https://rtti.test/v1/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ protocol: 1, auto_enrollment_code: campaign.auto_enrollment_code, device_id: fill.repeat(64) }),
    });
    const first = await enrollDevice("1");
    const second = await enrollDevice("2");
    const full = await enrollDevice("3");
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(full.status).toBe(403);

    const firstBody = await first.json() as { helper_id: string; credential: string; auto_enrolled: boolean };
    expect(firstBody.auto_enrolled).toBe(true);
    const submitted = await SELF.fetch("https://rtti.test/v1/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${firstBody.credential}` },
      body: JSON.stringify({ protocol: 1, device_id: "1".repeat(64), profile: validProfile() }),
    });
    expect(submitted.status).toBe(200);

    const campaigns = await adminFetch("/v1/admin/campaigns");
    expect(await campaigns.json()).toEqual({ campaigns: [expect.objectContaining({
      campaign_id: campaign.campaign_id, enrolled_count: 2, max_devices: 2, status: "active",
    })] });
    const helpers = await adminFetch("/v1/admin/helpers");
    expect(await helpers.json()).toEqual({ helpers: expect.arrayContaining([
      expect.objectContaining({ helper_id: firstBody.helper_id, campaign_name: "Trusted automatic helpers" }),
    ]) });
  });

  it("serializes campaign capacity races and lets the owner close or rotate registration", async () => {
    const createBody = JSON.stringify({ name: "Single seat campaign", expires_days: 30, max_devices: 1 });
    const created = await (await adminFetch("/v1/admin/campaigns/create", "POST", createBody)).json() as {
      campaign_id: string; auto_enrollment_code: string;
    };
    const enroll = (code: string, fill: string) => SELF.fetch("https://rtti.test/v1/enroll", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ protocol: 1, auto_enrollment_code: code, device_id: fill.repeat(64) }),
    });
    const raced = await Promise.all([
      enroll(created.auto_enrollment_code, "4"),
      enroll(created.auto_enrollment_code, "5"),
    ]);
    expect(raced.map((response) => response.status).sort()).toEqual([200, 403]);

    const revokeBody = JSON.stringify({ campaign_id: created.campaign_id, action: "revoke" });
    expect((await adminFetch("/v1/admin/campaigns/mutate", "POST", revokeBody)).status).toBe(200);
    expect((await enroll(created.auto_enrollment_code, "6")).status).toBe(403);

    const rotateBody = JSON.stringify({ campaign_id: created.campaign_id, action: "rotate" });
    const rotated = await (await adminFetch("/v1/admin/campaigns/mutate", "POST", rotateBody)).json() as {
      auto_enrollment_code: string;
    };
    expect(rotated.auto_enrollment_code).not.toBe(created.auto_enrollment_code);
    expect((await enroll(created.auto_enrollment_code, "7")).status).toBe(403);
    // Rotation changes the invite, but the original one-device capacity remains full.
    expect((await enroll(rotated.auto_enrollment_code, "7")).status).toBe(403);
  });

  it("limits an enrolled helper to twenty submissions per rolling thirty minutes", async () => {
    const helper = await createAndEnroll("Rate Helper");
    const publish = () => SELF.fetch("https://rtti.test/v1/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${helper.credential}` },
      body: JSON.stringify({ protocol: 1, device_id: helper.deviceId, profile: validProfile() }),
    });
    for (let index = 0; index < 20; index += 1) expect((await publish()).status).toBe(200);
    expect((await publish()).status).toBe(429);
  });

  it("rejects incomplete evidence and audits it without changing the registry", async () => {
    const helper = await createAndEnroll();
    const profile = validProfile();
    (profile.evidence as Record<string, unknown>).distinct_counts = [3000, 2997];
    const response = await SELF.fetch("https://rtti.test/v1/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${helper.credential}` },
      body: JSON.stringify({ protocol: 1, device_id: helper.deviceId, profile }),
    });
    expect(response.status).toBe(400);
    const registry = await (await SELF.fetch("https://rtti.test/v1/RTTI.dat")).json() as { profiles: unknown[] };
    expect(registry.profiles).toHaveLength(0);
    const rows = await env.DB.prepare("SELECT accepted FROM submissions").all<{ accepted: number }>();
    expect(rows.results).toEqual([{ accepted: 0 }]);
  });

  it("revokes helper publication immediately and can issue a new one-time enrollment", async () => {
    const helper = await createAndEnroll();
    expect((await adminFetch("/v1/admin/helpers/mutate", "POST", JSON.stringify({
      helper_id: helper.helper_id, action: "revoke",
    }))).status).toBe(200);
    const denied = await SELF.fetch("https://rtti.test/v1/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${helper.credential}` },
      body: JSON.stringify({ protocol: 1, device_id: helper.deviceId, profile: validProfile() }),
    });
    expect(denied.status).toBe(403);

    const reset = await adminFetch("/v1/admin/helpers/mutate", "POST", JSON.stringify({
      helper_id: helper.helper_id, action: "reset_enrollment",
    }));
    expect(reset.status).toBe(200);
    expect(await reset.json()).toEqual(expect.objectContaining({ enrollment_code: expect.any(String), status: "active" }));
  });

  it("bootstraps existing profiles only through authenticated admin access", async () => {
    const unauthorized = await SELF.fetch("https://rtti.test/v1/admin/registry/bootstrap", {
      method: "POST", body: JSON.stringify({ registry: {} }),
    });
    expect(unauthorized.status).toBe(401);
    const registry = { format: "kfps_fh6_rtti_registry_v1", updated_utc: "2026-07-15T00:00:00Z", profiles: [validProfile()] };
    const response = await adminFetch("/v1/admin/registry/bootstrap", "POST", JSON.stringify({ registry }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(expect.objectContaining({ imported: 1 }));
  });
});
