import { createExecutionContext, env, SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it, vi } from "vitest";
import worker from "../src/index";
import {
  FEATURED_ARTWORK_LIMIT,
  NEW_ARTWORK_UPLOAD_LIMIT,
  NEW_ARTWORK_UPLOAD_WINDOW_SECONDS,
} from "../src/catalog";
import { validateUpload } from "../src/validation";

const ADMIN_TOKEN = "local-test-admin-token-that-is-at-least-32-characters";
const PREVIEW = "iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAABY0lEQVR42u3bu3HCQBQFUNhRSCjqIXcVDinJIVWQUw9FyJFDm2GMdi9658Z8du7x20Vg7efDvOxkWJoKAAAQAAAEAAABAEAAAJB+mZ59wv30pbUHOd7OJsAWJAAACAAAAgCAAAAgAAAIAAACAIAASMn0diu+fDx+zOcVQPfSf3t8OMa0qeL/eo1QiLbp8td8vU0DrFVWIEIrU34oQitVfiBCK1d+GEIrWX4QQitbfsj7+yqi9ASkHIYD12ECHMIAam8/g9djAmxBAAQAAAEAQAAA6Je0H8kHrccE2IIAlBv7pHWYgPJb0OgpGPz+rfQWELAF5mxBvcsIOX+yzoBepQRdg+QdwmuXE3YBmPkpaK2SAv9FPfdj6KvLCr0/IPsGjZ/S/vODuTtkXvzX6x6x4hduZc6AIgEAAIAAACAAAAgAAAIAgAAAIAAACIDtZz8f5kUNJgCAAAAgAAAIAAACAID0yTeWyzlJHL1/wAAAAABJRU5ErkJggg==";
const PREVIEW_TWO = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAABqklEQVR42u2bMRLCMAwE7wM01HTU/JsH8C4qCjoYmIEBQ8CWTokluXBLsgtkoniD9Wp9Kdd2s6Wsb58tWZbng8zwHwKywb8JyAj/FJAV/i4gMzxNgFd4igDP8GoBLQfaHfbNa44vA5bwEmipDOkvDxbwTPAaEZq/HpjwluBTIrTXHniEfyzGxRda+CXAmSLgHV4j4caGCPASCQ8+RIFvkfDKCC8XPJaAkhNLwJ+Pp8llKeEbK+aC/wVtIaN21sAcd3gSeK2E2kELlvAacIaImikTVoMNE14qoeYeB17grSQMAWwBlvASCWoBvcGzJQwBQwBJwJzwrRKGgCFgCJgc+dMKmAwkyikqooCfhUg5QkYT8DeRKUfISPcBokYoigBxIxRBgLoR8jwNUhohz88DKFtj6QX0IsFil8hMQC9Phal9gNd9gcUF9LAzREtkPO8N0hoh79vj6kYopYBohchohLSNkPdKTNUIee8E1Y1QDxJYVTosEvheo0h1I9R6sJ6yWEojpDnYUi0wrRHq/c0P6fkgM3x1IRIVnibA86t3yAyvFhDhpUtkhr+tK+AZTRUFBwckAAAAAElFTkSuQmCC";

type TestJson = null | boolean | number | string | TestJson[] | { [key: string]: TestJson };

function canonicalJson(value: TestJson): string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key]!)}`).join(",")}}`;
}

function testBase64Url(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function privateKeyDer(pem: string): ArrayBuffer {
  const raw = pem.replace(/-----BEGIN PRIVATE KEY-----/g, "")
    .replace(/-----END PRIVATE KEY-----/g, "")
    .replace(/\s+/g, "");
  return Uint8Array.from(atob(raw), (character) => character.charCodeAt(0)).buffer;
}

async function supporterEntitlement(
  subject: string,
  entitlementId: string = crypto.randomUUID(),
  issued: number = Date.now(),
): Promise<Record<string, unknown>> {
  const payload = {
    audience: "kfps-community-v1",
    entitlement_id: entitlementId,
    expires_at: new Date(issued + 15 * 60 * 1000).toISOString(),
    issued_at: new Date(issued).toISOString(),
    nonce: testBase64Url(crypto.getRandomValues(new Uint8Array(32))),
    schema: "kfps.community.supporter.v1",
    subject,
  };
  const payloadBytes = new TextEncoder().encode(canonicalJson(payload));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    privateKeyDer(env.TEST_SUPPORTER_PRIVATE_KEY_PEM),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = new Uint8Array(await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", key, payloadBytes.slice().buffer as ArrayBuffer,
  ));
  return {
    type: "kfps.supporter.community-entitlement",
    version: 1,
    kid: env.SUPPORTER_ENTITLEMENT_KEY_ID,
    payload: testBase64Url(payloadBytes),
    signature: testBase64Url(signature),
  };
}

function design(offset = 0): Record<string, unknown> {
  return {
    format: "kfps.primitive.v1",
    metadata: { source_path: "C:\\Users\\Private\\secret.png", shape_count: 2, target_game: "FH6" },
    shapes: [
      { type: 1, data: [0, 0, 100, 100], color: [0, 0, 0, 0] },
      { type: 2, data: [offset, 4, 30, 18, 12], color: [255, 80, 170, 255], score: 0.4 },
    ],
  };
}

function uploadBody(offset = 0): Record<string, unknown> {
  return {
    title: `Test Artwork ${offset}`,
    description: "A community integration fixture.",
    category: "Original Artwork",
    classification: "toolmade",
    tags: ["test", "geometric"],
    games: ["FH6", "FM8"],
    license: "kfps-community-share-v1",
    confirm_rights: true,
    client_version: "3.0.81",
    design: design(offset),
    preview_base64: PREVIEW,
    thumbnail_base64: PREVIEW_TWO,
  };
}

async function jsonFetch(path: string, method = "GET", body?: unknown, token = "", admin = false): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  if (admin) headers["X-Community-Admin-Token"] = ADMIN_TOKEN;
  return SELF.fetch(`https://community.test${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function directJsonFetch(path: string, method = "GET", body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  return worker.fetch(new Request(`https://community.test${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  }), env, createExecutionContext());
}

async function account(seed: string, username: string): Promise<string> {
  const auth = await jsonFetch("/v1/auth/test", "POST", {
    installation_id: seed.repeat(64).slice(0, 64),
    display_name: `${username} local test`,
  });
  expect(auth.status).toBe(200);
  const token = String((await auth.json() as { token: string }).token);
  const chosen = await jsonFetch("/v1/profile/username", "POST", { username, confirm_username: username }, token);
  expect(chosen.status).toBe(200);
  return token;
}

async function verifySupporter(token: string, entitlementId: string = crypto.randomUUID()): Promise<string> {
  const session = await (await jsonFetch("/v1/session", "GET", undefined, token)).json() as {
    user: { id: string };
  };
  const response = await jsonFetch("/v1/supporter/verify", "POST", {
    entitlement: await supporterEntitlement(session.user.id, entitlementId),
  }, token);
  expect(response.status).toBe(200);
  expect(await response.json()).toMatchObject({ supporter: { active: true } });
  return entitlementId;
}

async function clearR2(): Promise<void> {
  let cursor: string | undefined;
  do {
    const listed = await env.ASSETS.list({ cursor });
    if (listed.objects.length) await env.ASSETS.delete(listed.objects.map((item: R2Object) => item.key));
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);
}

beforeEach(async () => {
  await env.DB.batch([
    env.DB.prepare("DELETE FROM moderation_events"),
    env.DB.prepare("DELETE FROM reports"),
    env.DB.prepare("DELETE FROM follows"),
    env.DB.prepare("DELETE FROM favorites"),
    env.DB.prepare("DELETE FROM artwork_search"),
    env.DB.prepare("DELETE FROM artwork_revisions"),
    env.DB.prepare("DELETE FROM artworks"),
    env.DB.prepare("DELETE FROM sessions"),
    env.DB.prepare("DELETE FROM rate_limits"),
    env.DB.prepare("DELETE FROM service_settings"),
    env.DB.prepare("DELETE FROM users"),
  ]);
  await clearR2();
});

describe("community worker", () => {
  it("allows a generous initial upload submission rate", () => {
    expect(NEW_ARTWORK_UPLOAD_LIMIT).toBe(50);
    expect(NEW_ARTWORK_UPLOAD_WINDOW_SECONDS).toBe(30 * 60);
  });

  it("reports public configuration without exposing secrets", async () => {
    const health = await jsonFetch("/v1/health");
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual({ service: "kfps-community-library", protocol: 1, status: "ok" });
    const config = await (await jsonFetch("/v1/config")).json() as Record<string, unknown>;
    expect(config.categories).toContain("Original Artwork");
    expect(config.scopes).toContain("featured");
    expect(config.featured_artwork_limit).toBe(FEATURED_ARTWORK_LIMIT);
    expect(config.deployment_environment).toBe("local-unit-test");
    expect(JSON.stringify(config)).not.toContain(ADMIN_TOKEN);
  });

  it("protects staging test authentication when a separate token is configured", async () => {
    const protectedEnv = { ...env, TEST_AUTH_TOKEN: "s".repeat(48) };
    const body = JSON.stringify({
      installation_id: "protected-staging-installation-id-0000000001",
      display_name: "Protected staging tester",
    });
    const request = (token = "") => new Request("https://community.test/v1/auth/test", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "X-Community-Test-Token": token } : {}),
      },
      body,
    });
    const denied = await worker.fetch(request(), protectedEnv, createExecutionContext());
    expect(denied.status).toBe(401);
    expect(await denied.json()).toMatchObject({ error: "test_authentication_required" });
    const accepted = await worker.fetch(request("s".repeat(48)), protectedEnv, createExecutionContext());
    expect(accepted.status).toBe(200);
  });

  it("preserves and reports mask usage from explicit and data flags", async () => {
    const token = await account("m", "MaskArtist");
    const maskedDesign = design(12);
    (maskedDesign.shapes as Array<Record<string, unknown>>)[1]!.mask = true;
    const uploaded = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(12),
      design: maskedDesign,
    }, token);
    expect(uploaded.status).toBe(201);
    const artwork = (await uploaded.json() as { artwork: { id: string; uses_masks: boolean } }).artwork;
    expect(artwork.uses_masks).toBe(true);

    const downloaded = await jsonFetch(`/v1/artworks/${artwork.id}/download`, "GET", undefined, token);
    expect(downloaded.status).toBe(200);
    const payload = await downloaded.json() as { shapes: Array<Record<string, unknown>> };
    expect(payload.shapes[1]?.mask).toBe(true);
    const stored = await env.DB.prepare(
      `SELECT a.uses_masks, r.uses_masks AS revision_uses_masks
         FROM artworks a JOIN artwork_revisions r
           ON r.artwork_id = a.id AND r.revision = a.current_revision WHERE a.id = ?1`,
    ).bind(artwork.id).first<{ uses_masks: number; revision_uses_masks: number }>();
    expect(stored).toMatchObject({ uses_masks: 1, revision_uses_masks: 1 });

    const dataMaskedDesign = design(14);
    ((dataMaskedDesign.shapes as Array<Record<string, unknown>>)[1]!.data as number[]).push(0, 1);
    const inspected = await validateUpload({ ...uploadBody(14), design: dataMaskedDesign }, "3.0.81", true);
    expect(inspected.usesMasks).toBe(true);
    (dataMaskedDesign.shapes as Array<Record<string, unknown>>)[1]!.mask = false;
    expect((await validateUpload({ ...uploadBody(14), design: dataMaskedDesign }, "3.0.81", true)).usesMasks).toBe(false);
    expect((await validateUpload(uploadBody(15), "3.0.81", true)).usesMasks).toBe(false);
  });

  it("atomically replaces current preview derivatives through the admin maintenance API", async () => {
    const token = await account("r", "RenderAdminFixture");
    const uploadedResponse = await jsonFetch("/v1/artworks", "POST", uploadBody(13), token);
    expect(uploadedResponse.status).toBe(201);
    const artwork = (await uploadedResponse.json() as {
      artwork: { id: string; current_revision: number; content_sha256: string };
    }).artwork;
    const before = await env.DB.prepare(
      "SELECT design_key, preview_key, thumbnail_key FROM artwork_revisions WHERE artwork_id = ?1 AND revision = 1",
    ).bind(artwork.id).first<{ design_key: string; preview_key: string; thumbnail_key: string }>();

    expect((await jsonFetch("/v1/admin/rerender")).status).toBe(401);
    const queue = await jsonFetch("/v1/admin/rerender?status=published", "GET", undefined, "", true);
    expect(queue.status).toBe(200);
    expect(await queue.json()).toMatchObject({
      items: [{ id: artwork.id, current_revision: 1, content_hash: artwork.content_sha256, uses_masks: 0 }],
    });
    expect((await jsonFetch(`/v1/admin/artworks/${artwork.id}/design`)).status).toBe(401);
    const designResponse = await jsonFetch(`/v1/admin/artworks/${artwork.id}/design`, "GET", undefined, "", true);
    expect(designResponse.status).toBe(200);
    const designBytes = new Uint8Array(await designResponse.arrayBuffer());
    expect(designResponse.headers.get("X-Content-Sha256")).toBe(artwork.content_sha256);
    expect(designResponse.headers.get("X-Artwork-Revision")).toBe("1");

    const replacement = {
      expected_revision: 1,
      expected_content_sha256: artwork.content_sha256,
      renderer_version: "3.0.95",
      uses_masks: false,
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    };
    expect((await jsonFetch(
      `/v1/admin/artworks/${artwork.id}/rendered-assets`, "POST", replacement,
    )).status).toBe(401);
    const replaced = await jsonFetch(
      `/v1/admin/artworks/${artwork.id}/rendered-assets`, "POST", replacement, "", true,
    );
    expect(replaced.status).toBe(200);
    expect(await replaced.json()).toMatchObject({ artwork_id: artwork.id, revision: 1, unchanged: false });

    const preview = new Uint8Array(await (await jsonFetch(`/v1/artworks/${artwork.id}/preview`)).arrayBuffer());
    const thumbnail = new Uint8Array(await (await jsonFetch(`/v1/artworks/${artwork.id}/thumbnail`)).arrayBuffer());
    expect(preview).toEqual(Uint8Array.from(atob(PREVIEW_TWO), (character) => character.charCodeAt(0)));
    expect(thumbnail).toEqual(Uint8Array.from(atob(PREVIEW), (character) => character.charCodeAt(0)));
    const designAfter = new Uint8Array(await (await jsonFetch(
      `/v1/admin/artworks/${artwork.id}/design`, "GET", undefined, "", true,
    )).arrayBuffer());
    expect(designAfter).toEqual(designBytes);
    const after = await env.DB.prepare(
      `SELECT a.current_revision, a.content_hash, r.design_key, r.preview_key, r.thumbnail_key
         FROM artworks a JOIN artwork_revisions r
           ON r.artwork_id = a.id AND r.revision = a.current_revision WHERE a.id = ?1`,
    ).bind(artwork.id).first<Record<string, unknown>>();
    expect(after).toMatchObject({ current_revision: 1, content_hash: artwork.content_sha256, design_key: before?.design_key });
    expect(after?.preview_key).not.toBe(before?.preview_key);
    expect(after?.thumbnail_key).not.toBe(before?.thumbnail_key);
    expect((await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM moderation_events WHERE artwork_id = ?1 AND action = 'rerender_assets'",
    ).bind(artwork.id).first<{ count: number }>())?.count).toBe(1);
    expect((await jsonFetch(
      `/v1/admin/artworks/${artwork.id}/rendered-assets`, "POST",
      { ...replacement, expected_revision: 2 }, "", true,
    )).status).toBe(409);
  });

  it("backfills mask metadata without rotating matching rendered assets", async () => {
    const token = await account("k", "MaskBackfillFixture");
    const maskedDesign = design(16);
    (maskedDesign.shapes as Array<Record<string, unknown>>)[1]!.mask = true;
    const uploaded = await (await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(16),
      design: maskedDesign,
    }, token)).json() as {
      artwork: { id: string; current_revision: number; content_sha256: string };
    };
    const before = await env.DB.prepare(
      "SELECT preview_key, thumbnail_key FROM artwork_revisions WHERE artwork_id = ?1 AND revision = 1",
    ).bind(uploaded.artwork.id).first<{ preview_key: string; thumbnail_key: string }>();
    await env.DB.batch([
      env.DB.prepare("UPDATE artworks SET uses_masks = 0 WHERE id = ?1").bind(uploaded.artwork.id),
      env.DB.prepare("UPDATE artwork_revisions SET uses_masks = 0 WHERE artwork_id = ?1").bind(uploaded.artwork.id),
    ]);

    const response = await jsonFetch(
      `/v1/admin/artworks/${uploaded.artwork.id}/rendered-assets`,
      "POST",
      {
        expected_revision: 1,
        expected_content_sha256: uploaded.artwork.content_sha256,
        renderer_version: "3.0.96",
        uses_masks: true,
        preview_base64: PREVIEW,
        thumbnail_base64: PREVIEW_TWO,
      },
      "",
      true,
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      artwork_id: uploaded.artwork.id,
      unchanged: true,
      metadata_updated: true,
      uses_masks: true,
    });
    const after = await env.DB.prepare(
      `SELECT a.uses_masks, r.uses_masks AS revision_uses_masks, r.preview_key, r.thumbnail_key
         FROM artworks a JOIN artwork_revisions r
           ON r.artwork_id = a.id AND r.revision = a.current_revision WHERE a.id = ?1`,
    ).bind(uploaded.artwork.id).first<Record<string, unknown>>();
    expect(after).toMatchObject({
      uses_masks: 1,
      revision_uses_masks: 1,
      preview_key: before?.preview_key,
      thumbnail_key: before?.thumbnail_key,
    });
    expect((await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM moderation_events WHERE artwork_id = ?1 AND action = 'refresh_mask_metadata'",
    ).bind(uploaded.artwork.id).first<{ count: number }>())?.count).toBe(1);
  });

  it("keeps VERSION policy administrative, inspectable, and explicitly reversible", async () => {
    expect((await jsonFetch("/v1/admin/version")).status).toBe(401);
    const initial = await jsonFetch("/v1/admin/version", "GET", undefined, "", true);
    expect(initial.status).toBe(200);
    expect(await initial.json()).toMatchObject({
      version: { minimum_upload_version: "3.0.81", automatic: true },
    });

    const manual = await jsonFetch("/v1/admin/version", "POST", {
      action: "set", minimum_version: "3.0.80", automatic: false,
    }, "", true);
    expect(manual.status).toBe(200);
    expect(await manual.json()).toMatchObject({
      version: { minimum_upload_version: "3.0.80", automatic: false, last_status: "manual_override" },
    });
    expect(await (await jsonFetch("/v1/config")).json()).toMatchObject({
      minimum_upload_version: "3.0.80",
    });

    const resumed = await jsonFetch("/v1/admin/version", "POST", {
      action: "set", minimum_version: "3.0.80", automatic: true,
    }, "", true);
    expect(await resumed.json()).toMatchObject({ version: { automatic: true } });
    const paused = await jsonFetch("/v1/admin/version", "POST", { action: "pause" }, "", true);
    expect(await paused.json()).toMatchObject({ version: { automatic: false } });
    expect((await jsonFetch("/v1/admin/version", "POST", {
      action: "set", minimum_version: "main", automatic: false,
    }, "", true)).status).toBe(400);

    const panel = await (await jsonFetch("/admin")).text();
    expect(panel).toContain("Version policy");
    expect(panel).toContain("SUPPORTERS ONLY");
  });

  it("allows only same-origin browser requests", async () => {
    const sameOrigin = await SELF.fetch("https://community.test/v1/config", {
      method: "OPTIONS",
      headers: { Origin: "https://community.test" },
    });
    expect(sameOrigin.status).toBe(204);
    expect(sameOrigin.headers.get("Access-Control-Allow-Origin")).toBe("https://community.test");

    const crossOrigin = await SELF.fetch("https://community.test/v1/config", {
      method: "OPTIONS",
      headers: { Origin: "https://untrusted.example" },
    });
    expect(crossOrigin.status).toBe(403);
    expect(crossOrigin.headers.get("Access-Control-Allow-Origin")).toBeNull();

    const desktopClient = await jsonFetch("/v1/config");
    expect(desktopClient.status).toBe(200);
    expect(desktopClient.headers.get("Access-Control-Allow-Origin")).toBeNull();
  });

  it("makes usernames unique and immutable", async () => {
    const first = await account("a", "Creator_Test");
    const locked = await jsonFetch("/v1/profile/username", "POST", { username: "Different" }, first);
    expect(locked.status).toBe(409);
    expect((await locked.json() as { error: string }).error).toBe("username_locked");

    const auth = await jsonFetch("/v1/auth/test", "POST", {
      installation_id: "b".repeat(64), display_name: "Second",
    });
    const second = String((await auth.json() as { token: string }).token);
    const unconfirmed = await jsonFetch("/v1/profile/username", "POST", {
      username: "creator_test", confirm_username: "Creator_Test",
    }, second);
    expect(unconfirmed.status).toBe(400);
    expect((await unconfirmed.json() as { error: string }).error).toBe("username_confirmation_required");
    const duplicate = await jsonFetch("/v1/profile/username", "POST", {
      username: "creator_test", confirm_username: "creator_test",
    }, second);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("username_unavailable");
  });

  it("exchanges a GitHub identity without retaining the GitHub token", async () => {
    const github = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({
      id: 314159,
      login: "PublicGitHubUser",
      avatar_url: "https://avatars.githubusercontent.com/u/314159?v=4",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    try {
      const first = await directJsonFetch("/v1/auth/github", "POST", { access_token: "gho_temporary_fixture_token" });
      expect(first.status).toBe(200);
      const firstPayload = await first.json() as { token: string; provider: string };
      expect(firstPayload.provider).toBe("github");
      expect(firstPayload.token).not.toContain("temporary_fixture");

      expect((await jsonFetch("/v1/profile/username", "POST", {
        username: "GitHubCreator", confirm_username: "GitHubCreator",
      }, firstPayload.token)).status).toBe(200);
      const uploaded = await jsonFetch("/v1/artworks", "POST", uploadBody(314), firstPayload.token);
      expect(uploaded.status).toBe(201);
      expect(await uploaded.json()).toMatchObject({
        artwork: { status: "published" },
        moderation_required: false,
      });
      const event = await env.DB.prepare(
        "SELECT action FROM moderation_events ORDER BY created_at DESC LIMIT 1",
      ).first<{ action: string }>();
      expect(event?.action).toBe("validated_auto_publish");

      const request = github.mock.calls[0]?.[1] as RequestInit;
      expect(new Headers(request.headers).get("Authorization")).toBe("Bearer gho_temporary_fixture_token");
      expect(new Headers(request.headers).get("X-GitHub-Api-Version")).toBe("2026-03-10");

      const second = await directJsonFetch("/v1/auth/github", "POST", { access_token: "gho_temporary_fixture_token" });
      expect(second.status).toBe(200);
      const users = await env.DB.prepare("SELECT provider, provider_login FROM users").all<Record<string, string>>();
      expect(users.results).toEqual([{ provider: "github", provider_login: "PublicGitHubUser" }]);
      const stored = JSON.stringify(await env.DB.prepare("SELECT * FROM sessions").all());
      expect(stored).not.toContain("gho_temporary_fixture_token");
    } finally {
      github.mockRestore();
    }
  });

  it("requires distribution rights but does not classify artwork as SFW", async () => {
    const token = await account("m", "PolicyCreator");
    const denied = await jsonFetch("/v1/artworks", "POST", { ...uploadBody(95), confirm_rights: false }, token);
    expect(denied.status).toBe(400);
    expect((await denied.json() as { error: string }).error).toBe("rights_confirmation_required");
    const accepted = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(96), mature_content: true, title: "Unclassified Community Artwork",
    }, token);
    expect(accepted.status).toBe(201);
  });

  it("requires a current client and an explicit Handmade or Toolmade classification", async () => {
    const token = await account("q", "ClassificationDefault");
    const accepted = await jsonFetch("/v1/artworks", "POST", uploadBody(600), token);
    expect(accepted.status).toBe(201);
    expect(await accepted.json()).toMatchObject({ artwork: { classification: "toolmade" } });

    const noVersion = uploadBody(601);
    delete noVersion.client_version;
    const missingVersion = await jsonFetch("/v1/artworks", "POST", noVersion, token);
    expect(missingVersion.status).toBe(426);
    expect((await missingVersion.json() as { error: string }).error).toBe("client_update_required");

    const outdated = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(602), client_version: "3.0.79",
    }, token);
    expect(outdated.status).toBe(426);
    expect((await outdated.json() as { error: string }).error).toBe("client_update_required");

    const noClassification = uploadBody(603);
    delete noClassification.classification;
    const missingClassification = await jsonFetch("/v1/artworks", "POST", noClassification, token);
    expect(missingClassification.status).toBe(400);
    expect((await missingClassification.json() as { error: string }).error).toBe("invalid_classification");

    const invalid = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(604),
      classification: "both",
    }, token);
    expect(invalid.status).toBe(400);
    expect((await invalid.json() as { error: string }).error).toBe("invalid_classification");
    expect((await jsonFetch("/v1/artworks?classification=both")).status).toBe(400);
  });

  it("keeps the production rollout bridge explicit and defaults only legacy uploads", async () => {
    const legacyBody = uploadBody(605);
    delete legacyBody.client_version;
    delete legacyBody.classification;
    const legacy = await validateUpload(legacyBody, "3.0.81", false);
    expect(legacy.clientVersion).toBe("legacy");
    expect(legacy.classification).toBe("toolmade");
    await expect(validateUpload(legacyBody, "3.0.81", true)).rejects.toMatchObject({
      status: 426, code: "client_update_required",
    });
  });

  it("accepts the exact pre-classification upload through the rollout route", async () => {
    const token = await account("l", "LegacyRoute");
    const legacyBody = uploadBody(606);
    delete legacyBody.client_version;
    delete legacyBody.classification;
    const response = await worker.fetch(new Request("https://community.test/v1/artworks", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(legacyBody),
    }), { ...env, REQUIRE_MODERN_UPLOAD_CLIENT: "0" }, createExecutionContext());
    expect(response.status).toBe(201);
    expect(await response.json()).toMatchObject({ artwork: { classification: "toolmade", supporter_only: false } });
  });

  it("filters and searches independently inside Handmade and Toolmade", async () => {
    const token = await account("v", "ClassificationFilter");
    const handmade = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(610),
      title: "Handmade Needle",
      tags: ["sharedneedle", "hand-drawn"],
      classification: "handmade",
    }, token);
    expect(handmade.status).toBe(201);
    const toolmade = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(611),
      title: "Toolmade Needle",
      tags: ["sharedneedle", "generated"],
      classification: "toolmade",
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    }, token);
    expect(toolmade.status).toBe(201);

    const browse = await (await jsonFetch("/v1/artworks?search=sharedneedle")).json() as {
      total: number; items: Array<{ classification: string }>;
    };
    expect(browse.total).toBe(2);
    const handmadeOnly = await (await jsonFetch(
      "/v1/artworks?classification=handmade&search=sharedneedle",
    )).json() as { total: number; items: Array<{ classification: string; title: string }> };
    expect(handmadeOnly.total).toBe(1);
    expect(handmadeOnly.items[0]).toMatchObject({ classification: "handmade", title: "Handmade Needle" });
    const toolmadeOnly = await (await jsonFetch(
      "/v1/artworks?classification=toolmade&search=sharedneedle",
    )).json() as { total: number; items: Array<{ classification: string; title: string }> };
    expect(toolmadeOnly.total).toBe(1);
    expect(toolmadeOnly.items[0]).toMatchObject({ classification: "toolmade", title: "Toolmade Needle" });
  });

  it("isolates supporter-only artwork and enforces signed account-bound access", async () => {
    const supporter = await account("s", "SupporterCreator");
    const regular = await account("r", "RegularViewer");
    const supporterId = await verifySupporter(supporter);

    const uploaded = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(615),
      title: "Supporter Gallery Fixture",
      supporter_only: true,
    }, supporter);
    expect(uploaded.status).toBe(201);
    const artwork = (await uploaded.json() as { artwork: { id: string; supporter_only: boolean } }).artwork;
    expect(artwork.supporter_only).toBe(true);
    const moderation = await (await jsonFetch(
      "/v1/admin/queue?status=published", "GET", undefined, "", true,
    )).json() as { items: Array<{ id: string; supporter_only: number }> };
    expect(moderation.items).toContainEqual(expect.objectContaining({ id: artwork.id, supporter_only: 1 }));

    expect((await (await jsonFetch("/v1/artworks")).json() as { total: number }).total).toBe(0);
    expect((await jsonFetch("/v1/artworks?scope=supporters")).status).toBe(401);
    expect((await jsonFetch("/v1/artworks?scope=supporters", "GET", undefined, regular)).status).toBe(403);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}`, "GET", undefined, regular)).status).toBe(404);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/thumbnail`, "GET", undefined, regular)).status).toBe(404);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/download`, "GET", undefined, regular)).status).toBe(404);

    const supporters = await jsonFetch("/v1/artworks?scope=supporters&search=Gallery", "GET", undefined, supporter);
    expect(supporters.status).toBe(200);
    expect(await supporters.json()).toMatchObject({
      total: 1,
      items: [{ id: artwork.id, supporter_only: true }],
    });
    const thumbnail = await jsonFetch(`/v1/artworks/${artwork.id}/thumbnail`, "GET", undefined, supporter);
    expect(thumbnail.status).toBe(200);
    expect(thumbnail.headers.get("Cache-Control")).toBe("private, no-store");
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/download`, "GET", undefined, supporter)).status).toBe(200);

    const publicRevision = await jsonFetch(`/v1/artworks/${artwork.id}/revisions`, "POST", {
      ...uploadBody(617),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
      supporter_only: false,
      change_note: "Attempted visibility change.",
    }, supporter);
    expect(publicRevision.status).toBe(409);
    expect((await publicRevision.json() as { error: string }).error).toBe("supporter_visibility_immutable");

    const regularUpload = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(616),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
      supporter_only: true,
    }, regular);
    expect(regularUpload.status).toBe(403);
    expect((await regularUpload.json() as { error: string }).error).toBe("supporter_required");

    const regularSession = await (await jsonFetch("/v1/session", "GET", undefined, regular)).json() as {
      user: { id: string };
    };
    const reused = await jsonFetch("/v1/supporter/verify", "POST", {
      entitlement: await supporterEntitlement(regularSession.user.id, supporterId),
    }, regular);
    expect(reused.status).toBe(409);
    expect((await reused.json() as { error: string }).error).toBe("supporter_entitlement_already_bound");

    const cleared = await jsonFetch("/v1/supporter/verify", "DELETE", undefined, supporter);
    expect(cleared.status).toBe(200);
    expect(await cleared.json()).toEqual({ supporter: { active: false, verified_until: "" } });
    const retainedBinding = await env.DB.prepare(
      "SELECT supporter_entitlement_id, supporter_verified_until FROM users WHERE username = ?1",
    ).bind("SupporterCreator").first<Record<string, unknown>>();
    expect(retainedBinding?.supporter_entitlement_id).toBe(supporterId);
    expect(retainedBinding?.supporter_verified_until).toBeNull();
    expect((await jsonFetch("/v1/artworks?scope=supporters", "GET", undefined, supporter)).status).toBe(403);

    await verifySupporter(supporter, supporterId);

    await env.DB.prepare(
      "UPDATE users SET supporter_verified_until = ?2 WHERE username = ?1",
    ).bind("SupporterCreator", new Date(Date.now() - 1000).toISOString()).run();
    expect((await jsonFetch("/v1/artworks?scope=supporters", "GET", undefined, supporter)).status).toBe(403);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}`, "GET", undefined, supporter)).status).toBe(404);
  });

  it("shows featured supporter thumbnails publicly while enforcing eight curated slots", async () => {
    const supporter = await account("featured-supporter", "FeaturedSupporter");
    const regular = await account("featured-regular", "FeaturedRegular");
    await verifySupporter(supporter);

    const uploaded = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(715),
      title: "Featured Supporter Fixture",
      supporter_only: true,
    }, supporter);
    expect(uploaded.status).toBe(201);
    const artwork = (await uploaded.json() as { artwork: { id: string } }).artwork;

    const featured = await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: artwork.id,
      revision: 1,
      action: "feature",
      note: "",
    }, "", true);
    expect(featured.status).toBe(200);
    expect(await featured.json()).toMatchObject({
      featured_count: 1,
      featured_limit: FEATURED_ARTWORK_LIMIT,
    });

    const catalog = await jsonFetch("/v1/artworks?scope=featured");
    expect(catalog.status).toBe(200);
    expect(await catalog.json()).toMatchObject({
      total: 1,
      page_size: FEATURED_ARTWORK_LIMIT,
      items: [{ id: artwork.id, featured: true, supporter_only: true }],
    });
    expect((await (await jsonFetch("/v1/artworks?scope=browse")).json() as { total: number }).total).toBe(0);

    const thumbnail = await jsonFetch(`/v1/artworks/${artwork.id}/thumbnail`);
    expect(thumbnail.status).toBe(200);
    expect(thumbnail.headers.get("Cache-Control")).toContain("public");
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/preview`)).status).toBe(404);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/download`, "GET", undefined, regular)).status).toBe(404);
    expect((await jsonFetch(`/v1/artworks/${artwork.id}/download`, "GET", undefined, supporter)).status).toBe(200);

    const clone = (id: string, title: string, contentHash: string, isFeatured: number) => env.DB.prepare(
      `INSERT INTO artworks(
        id, creator_id, title, description, category, tags_json, games_json, license,
        schema_version, shape_count, group_count, status, rejection_reason, featured,
        current_revision, content_hash, preview_hash, download_count, favorite_count,
        report_count, created_at, updated_at, published_at, thumbnail_hash,
        source_schema, schema_known, classification, supporter_only, uses_masks
      )
      SELECT ?1, creator_id, ?2, description, category, tags_json, games_json, license,
        schema_version, shape_count, group_count, status, rejection_reason, ?4,
        current_revision, ?3, preview_hash, download_count, favorite_count,
        report_count, created_at, updated_at, published_at, thumbnail_hash,
        source_schema, schema_known, classification, supporter_only, uses_masks
      FROM artworks WHERE id = ?5`,
    ).bind(id, title, contentHash, isFeatured, artwork.id).run();
    for (let index = 0; index < FEATURED_ARTWORK_LIMIT - 1; index += 1) {
      await clone(`featured-clone-${index}`, `Featured Clone ${index}`, `featured-content-${index}`, 1);
    }
    await clone("featured-candidate", "Featured Candidate", "featured-content-candidate", 0);

    const fullQueue = await jsonFetch("/v1/admin/queue?status=featured", "GET", undefined, "", true);
    expect(fullQueue.status).toBe(200);
    expect(await fullQueue.json()).toMatchObject({
      total: FEATURED_ARTWORK_LIMIT,
      featured_count: FEATURED_ARTWORK_LIMIT,
      featured_limit: FEATURED_ARTWORK_LIMIT,
    });

    const ninth = await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: "featured-candidate",
      revision: 1,
      action: "feature",
      note: "",
    }, "", true);
    expect(ninth.status).toBe(409);
    expect(await ninth.json()).toMatchObject({ error: "featured_slots_full" });

    expect((await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: "featured-clone-0",
      revision: 1,
      action: "unfeature",
      note: "",
    }, "", true)).status).toBe(200);
    expect((await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: "featured-candidate",
      revision: 1,
      action: "feature",
      note: "",
    }, "", true)).status).toBe(200);
  });

  it("rejects expired, tampered, mismatched, and malformed supporter entitlements", async () => {
    const token = await account("t", "EntitlementGuard");
    const session = await (await jsonFetch("/v1/session", "GET", undefined, token)).json() as {
      user: { id: string };
    };
    const expired = await jsonFetch("/v1/supporter/verify", "POST", {
      entitlement: await supporterEntitlement(session.user.id, crypto.randomUUID(), Date.now() - 31 * 60 * 1000),
    }, token);
    expect(expired.status).toBe(400);

    const mismatched = await jsonFetch("/v1/supporter/verify", "POST", {
      entitlement: await supporterEntitlement("11111111-1111-4111-8111-111111111111"),
    }, token);
    expect(mismatched.status).toBe(400);

    const tampered = await supporterEntitlement(session.user.id);
    tampered.signature = String(tampered.signature).slice(0, -1) + (String(tampered.signature).endsWith("A") ? "B" : "A");
    expect((await jsonFetch("/v1/supporter/verify", "POST", { entitlement: tampered }, token)).status).toBe(400);
    expect((await jsonFetch("/v1/supporter/verify", "POST", { active: true }, token)).status).toBe(400);
  });

  it("lets only the owner edit tags without changing the design or classification", async () => {
    const owner = await account("u", "MetadataOwner");
    const other = await account("n", "MetadataOther");
    const uploaded = await (await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(620),
      tags: ["beforetag"],
      classification: "toolmade",
    }, owner)).json() as { artwork: { id: string; content_sha256: string; current_revision: number } };
    const id = uploaded.artwork.id;

    const denied = await jsonFetch(`/v1/artworks/${id}`, "PATCH", { tags: ["hijacked"] }, other);
    expect(denied.status).toBe(403);

    const changed = await jsonFetch(`/v1/artworks/${id}`, "PATCH", {
      tags: ["aftertag", "portrait"],
    }, owner);
    expect(changed.status).toBe(200);
    expect(await changed.json()).toMatchObject({
      artwork: {
        id,
        tags: ["aftertag", "portrait"],
        classification: "toolmade",
        content_sha256: uploaded.artwork.content_sha256,
        current_revision: uploaded.artwork.current_revision,
      },
    });
    expect((await (await jsonFetch("/v1/artworks?classification=toolmade&search=aftertag")).json() as { total: number }).total).toBe(1);
    expect((await (await jsonFetch("/v1/artworks?classification=handmade&search=aftertag")).json() as { total: number }).total).toBe(0);
    expect((await (await jsonFetch("/v1/artworks?search=beforetag")).json() as { total: number }).total).toBe(0);

    const unsupported = await jsonFetch(`/v1/artworks/${id}`, "PATCH", {
      tags: ["aftertag"], classification: "handmade",
    }, owner);
    expect(unsupported.status).toBe(400);
    expect((await unsupported.json() as { error: string }).error).toBe("invalid_metadata");

    const reclassified = await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: id, action: "classify_handmade", note: "Corrected during fixture review.",
    }, "", true);
    expect(reclassified.status).toBe(200);
    const detail = await (await jsonFetch(`/v1/artworks/${id}`, "GET", undefined, owner)).json() as {
      artwork: { classification: string };
    };
    expect(detail.artwork.classification).toBe("handmade");
    const storedRevision = await env.DB.prepare(
      "SELECT manifest_json FROM artwork_revisions WHERE artwork_id = ?1 AND revision = 1",
    ).bind(id).first<{ manifest_json: string }>();
    expect(JSON.parse(storedRevision?.manifest_json || "{}").classification).toBe("handmade");
  });

  it("detects game origins from the design instead of trusting upload labels", async () => {
    const token = await account("o", "OriginDetector");
    const uploaded = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(97),
      games: ["FM8"],
    }, token);
    expect(uploaded.status).toBe(201);
    const body = await uploaded.json() as { artwork: Record<string, unknown> };
    expect(body.artwork).toMatchObject({
      games: ["FH6"],
      source_schema: "kfps-primitives",
      schema_label: "KFPS primitive geometry",
      schema_known: true,
      schema_warning: "",
    });

    const wrongGame = await (await jsonFetch("/v1/artworks?game=FM8")).json() as { total: number };
    const detectedGame = await (await jsonFetch("/v1/artworks?game=FH6")).json() as { total: number };
    expect(wrongGame.total).toBe(0);
    expect(detectedGame.total).toBe(1);
  });

  it("recognizes live Forza type-code exports and their actual source game", async () => {
    const token = await account("t", "TypeCodeOrigin");
    const uploaded = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(99),
      games: ["FH5"],
      design: {
        format: "fh6_typecode_json_export_v1",
        source: { game: "fm8" },
        shapes: [{
          type: 1048678,
          type_word: 102,
          data: [0, 0, 1, 1, 0, 0, 0],
          color: [255, 255, 255, 255],
          source_format: "fh6_typecode",
        }],
      },
    }, token);
    expect(uploaded.status).toBe(201);
    expect((await uploaded.json() as { artwork: Record<string, unknown> }).artwork).toMatchObject({
      games: ["FM8"],
      source_schema: "forza-typecode-export",
      schema_label: "Forza live type-code export",
      schema_known: true,
    });
  });

  it("requires explicit acknowledgement for structurally valid unknown schemas", async () => {
    const token = await account("u", "UnknownSchema");
    const unknownDesign = {
      ...design(98),
      format: "other-project.v9",
      metadata: { shape_count: 2 },
    };
    const payload = { ...uploadBody(98), design: unknownDesign };
    const blocked = await jsonFetch("/v1/artworks", "POST", payload, token);
    expect(blocked.status).toBe(400);
    expect(await blocked.json()).toMatchObject({ error: "unknown_schema_confirmation_required" });

    const accepted = await jsonFetch("/v1/artworks", "POST", {
      ...payload,
      confirm_compatibility: true,
    }, token);
    expect(accepted.status).toBe(201);
    const acceptedBody = await accepted.json() as { artwork: Record<string, unknown> };
    expect(acceptedBody.artwork).toMatchObject({
      games: [],
      source_schema: "unrecognized",
      schema_known: false,
    });
    expect(String(acceptedBody.artwork.schema_warning)).toContain("compatibility may vary");

    const downloaded = await jsonFetch(`/v1/artworks/${acceptedBody.artwork.id}/download`, "GET", undefined, token);
    const canonical = await downloaded.json() as { metadata: Record<string, unknown> };
    expect(canonical.metadata).toMatchObject({
      source_schema: "unrecognized",
      schema_known: false,
      detected_games: [],
    });
  });

  it("uploads, sanitizes, browses, favorites, downloads, and reports artwork", async () => {
    const token = await account("c", "CreatorOne");
    const uploaded = await jsonFetch("/v1/artworks", "POST", uploadBody(17), token);
    expect(uploaded.status).toBe(201);
    const uploadJson = await uploaded.json() as { artwork: { id: string; status: string } };
    expect(uploadJson.artwork.status).toBe("published");
    const id = uploadJson.artwork.id;

    const browse = await jsonFetch("/v1/artworks?search=creatorone&game=FH6&sort=trending", "GET", undefined, token);
    expect(browse.status).toBe(200);
    const catalog = await browse.json() as { total: number; items: Array<{ id: string }> };
    expect(catalog.total).toBe(1);
    expect(catalog.items[0]?.id).toBe(id);

    const favorite = await jsonFetch(`/v1/artworks/${id}/favorite`, "POST", { favorite: true }, token);
    expect(await favorite.json()).toEqual({ favorited: true, favorites: 1 });

    const download = await jsonFetch(`/v1/artworks/${id}/download`, "GET", undefined, token);
    expect(download.status).toBe(200);
    const downloaded = await download.json() as { format: string; metadata: Record<string, unknown>; shapes: unknown[] };
    expect(downloaded.format).toBe("kfps.community.v1");
    expect(downloaded.metadata.source_path).toBeUndefined();
    expect(downloaded.shapes).toHaveLength(2);

    const report = await jsonFetch(`/v1/artworks/${id}/report`, "POST", { reason: "other", details: "Test report" }, token);
    expect(report.status).toBe(201);
    const reports = await jsonFetch("/v1/admin/reports", "GET", undefined, "", true);
    const reportItems = (await reports.json() as { items: Array<Record<string, unknown>> }).items;
    expect(reportItems).toHaveLength(1);
    expect(reportItems[0]).toMatchObject({
      artwork_id: id,
      artwork_status: "published",
      report_count: 1,
      shape_count: 2,
    });
    const published = await jsonFetch("/v1/admin/queue?status=published", "GET", undefined, "", true);
    const publishedItems = (await published.json() as { items: Array<Record<string, unknown>> }).items;
    expect(publishedItems[0]).toMatchObject({ id, report_count: 1 });
  });

  it("blocks semantic duplicates before writing another object", async () => {
    const token = await account("d", "DuplicateTest");
    expect((await jsonFetch("/v1/artworks", "POST", uploadBody(22), token)).status).toBe(201);
    const duplicate = await jsonFetch("/v1/artworks", "POST", { ...uploadBody(22), title: "Renamed copy" }, token);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("duplicate_artwork");
    const stored = await env.ASSETS.list();
    expect(stored.objects).toHaveLength(3);
  });

  it("enforces preview uniqueness when uploads race", async () => {
    const token = await account("r", "ConcurrentDuplicate");
    const responses = await Promise.all([
      jsonFetch("/v1/artworks", "POST", uploadBody(101), token),
      jsonFetch("/v1/artworks", "POST", uploadBody(102), token),
    ]);
    expect(responses.map((response) => response.status).sort()).toEqual([201, 409]);
    const rejected = responses.find((response) => response.status === 409);
    expect((await rejected?.json() as { error: string }).error).toBe("duplicate_preview");
    expect((await env.DB.prepare("SELECT COUNT(*) AS count FROM artwork_revisions").first<{ count: number }>())?.count).toBe(1);
    expect((await env.ASSETS.list()).objects).toHaveLength(3);
  });

  it("ignores score metadata and lets the same owner restore an owner-removed design", async () => {
    const token = await account("h", "HistoryDuplicate");
    const first = await (await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(62), classification: "handmade",
    }, token)).json() as { artwork: { id: string } };
    const changedScore = uploadBody(62);
    ((changedScore.design as { shapes: Array<Record<string, unknown>> }).shapes[1]!).score = 9999;
    const duplicate = await jsonFetch("/v1/artworks", "POST", { ...changedScore, title: "Score-only copy" }, token);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("duplicate_artwork");
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "DELETE", undefined, token)).status).toBe(200);
    const restoredResponse = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(62),
      title: "Restored copy",
      classification: "handmade",
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    }, token);
    expect(restoredResponse.status).toBe(201);
    const restored = await restoredResponse.json() as {
      restored: boolean; artwork: { id: string; status: string; title: string; classification: string };
    };
    expect(restored.restored).toBe(true);
    expect(restored.artwork).toMatchObject({
      id: first.artwork.id, status: "published", title: "Restored copy", classification: "handmade",
    });
    expect((await env.DB.prepare("SELECT COUNT(*) AS count FROM artworks").first<{ count: number }>())?.count).toBe(1);
    expect((await env.DB.prepare("SELECT COUNT(*) AS count FROM artwork_revisions").first<{ count: number }>())?.count).toBe(1);
    expect((await env.DB.prepare(
      "SELECT action FROM moderation_events WHERE artwork_id = ?1 ORDER BY created_at DESC, rowid DESC LIMIT 1",
    ).bind(first.artwork.id).first<{ action: string }>())?.action).toBe("owner_restored");
    expect((await env.ASSETS.list()).objects).toHaveLength(3);
  });

  it("lets an owner choose a new audience only when restoring an owner-removed design", async () => {
    const supporter = await account("audience-supporter", "AudienceSupporter");
    await verifySupporter(supporter);
    const first = await (await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(6201), supporter_only: true,
    }, supporter)).json() as { artwork: { id: string; supporter_only: boolean } };
    expect(first.artwork.supporter_only).toBe(true);
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "DELETE", undefined, supporter)).status).toBe(200);

    const publicRestoreResponse = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(6201), title: "Public restored copy", supporter_only: false,
      preview_base64: PREVIEW_TWO, thumbnail_base64: PREVIEW,
    }, supporter);
    expect(publicRestoreResponse.status).toBe(201);
    expect(await publicRestoreResponse.json()).toMatchObject({
      restored: true,
      artwork: { id: first.artwork.id, supporter_only: false, status: "published" },
    });
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`)).status).toBe(200);
    const publicStored = await env.DB.prepare(
      `SELECT a.supporter_only, r.manifest_json
         FROM artworks a JOIN artwork_revisions r
           ON r.artwork_id = a.id AND r.revision = a.current_revision
        WHERE a.id = ?1`,
    ).bind(first.artwork.id).first<{ supporter_only: number; manifest_json: string }>();
    expect(publicStored?.supporter_only).toBe(0);
    expect(JSON.parse(publicStored?.manifest_json || "{}").supporter_only).toBe(false);

    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "DELETE", undefined, supporter)).status).toBe(200);
    const supporterRestoreResponse = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(6201), title: "Supporter restored copy", supporter_only: true,
    }, supporter);
    expect(supporterRestoreResponse.status).toBe(201);
    expect(await supporterRestoreResponse.json()).toMatchObject({
      restored: true,
      artwork: { id: first.artwork.id, supporter_only: true, status: "published" },
    });
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`)).status).toBe(404);
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "GET", undefined, supporter)).status).toBe(200);

    const regular = await account("audience-regular", "AudienceRegular");
    const regularUpload = {
      ...uploadBody(6199), preview_base64: PREVIEW_TWO, thumbnail_base64: PREVIEW,
    };
    const regularCreate = await jsonFetch("/v1/artworks", "POST", regularUpload, regular);
    expect(regularCreate.status).toBe(201);
    const regularFirst = await regularCreate.json() as {
      artwork: { id: string };
    };
    expect((await jsonFetch(`/v1/artworks/${regularFirst.artwork.id}`, "DELETE", undefined, regular)).status).toBe(200);
    const denied = await jsonFetch("/v1/artworks", "POST", {
      ...regularUpload, supporter_only: true,
    }, regular);
    expect(denied.status).toBe(403);
    expect((await denied.json() as { error: string }).error).toBe("supporter_required");
    expect(await env.DB.prepare(
      "SELECT status, supporter_only FROM artworks WHERE id = ?1",
    ).bind(regularFirst.artwork.id).first()).toMatchObject({ status: "removed", supporter_only: 0 });
  });

  it("keeps owner-removed designs reserved against other accounts", async () => {
    const owner = await account("x", "RemovalOwner");
    const other = await account("y", "RemovalOther");
    const first = await (await jsonFetch("/v1/artworks", "POST", uploadBody(63), owner)).json() as { artwork: { id: string } };
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "DELETE", undefined, owner)).status).toBe(200);
    const duplicate = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(63),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    }, other);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("duplicate_artwork");
  });

  it("does not let an owner resubmit an admin-removed design", async () => {
    const owner = await account("z", "ModeratedOwner");
    const first = await (await jsonFetch("/v1/artworks", "POST", uploadBody(64), owner)).json() as {
      artwork: { id: string; current_revision: number };
    };
    const removed = await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: first.artwork.id,
      revision: first.artwork.current_revision,
      action: "remove",
      note: "Moderation removal fixture.",
    }, "", true);
    expect(removed.status).toBe(200);
    const duplicate = await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(64),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    }, owner);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("duplicate_artwork");
  });

  it("allows only one concurrent owner restore and cleans losing preview assets", async () => {
    const owner = await account("w", "RestoreRace");
    const first = await (await jsonFetch("/v1/artworks", "POST", uploadBody(65), owner)).json() as { artwork: { id: string } };
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}`, "DELETE", undefined, owner)).status).toBe(200);
    const restoreBody = {
      ...uploadBody(65),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
    };
    const responses = await Promise.all([
      jsonFetch("/v1/artworks", "POST", restoreBody, owner),
      jsonFetch("/v1/artworks", "POST", restoreBody, owner),
    ]);
    expect(responses.map((response) => response.status).sort()).toEqual([201, 409]);
    expect((await env.ASSETS.list()).objects).toHaveLength(3);
  });

  it("publishes revisions atomically and refreshes full-text search", async () => {
    const token = await account("i", "RevisionCreator");
    const first = await (await jsonFetch("/v1/artworks", "POST", uploadBody(70), token)).json() as { artwork: { id: string } };
    const revision = {
      ...uploadBody(71),
      title: "Distinct Revision Searchword",
      preview_base64: PREVIEW_TWO,
      change_note: "Changed geometry and title.",
    };
    const revised = await jsonFetch(`/v1/artworks/${first.artwork.id}/revisions`, "POST", revision, token);
    expect(revised.status).toBe(201);
    expect(await revised.json()).toMatchObject({ artwork_id: first.artwork.id, revision: 2, status: "published" });
    const search = await (await jsonFetch("/v1/artworks?search=Searchword")).json() as { total: number; items: Array<{ current_revision: number }> };
    expect(search.total).toBe(1);
    expect(search.items[0]?.current_revision).toBe(2);
    const duplicate = await jsonFetch(`/v1/artworks/${first.artwork.id}/revisions`, "POST", revision, token);
    expect(duplicate.status).toBe(409);
    expect((await duplicate.json() as { error: string }).error).toBe("duplicate_revision");
  });

  it("does not let a creator change classification in a revision", async () => {
    const token = await account("b", "LegacyRevision");
    const first = await (await jsonFetch("/v1/artworks", "POST", {
      ...uploadBody(72), classification: "handmade",
    }, token)).json() as { artwork: { id: string } };
    const revision = {
      ...uploadBody(73),
      preview_base64: PREVIEW_TWO,
      thumbnail_base64: PREVIEW,
      change_note: "Attempted classification change.",
    };
    const denied = await jsonFetch(`/v1/artworks/${first.artwork.id}/revisions`, "POST", revision, token);
    expect(denied.status).toBe(409);
    expect((await denied.json() as { error: string }).error).toBe("classification_immutable");
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}/revisions`, "POST", {
      ...revision, classification: "handmade",
    }, token)).status).toBe(201);
    const detail = await (await jsonFetch(`/v1/artworks/${first.artwork.id}`, "GET", undefined, token)).json() as {
      artwork: { classification: string };
    };
    expect(detail.artwork.classification).toBe("handmade");
  });

  it("counts at most one download per identity and artwork each day", async () => {
    const token = await account("j", "DownloadCounter");
    const first = await (await jsonFetch("/v1/artworks", "POST", uploadBody(80), token)).json() as { artwork: { id: string } };
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}/thumbnail`)).status).toBe(200);
    const anonymous = await jsonFetch(`/v1/artworks/${first.artwork.id}/download`);
    expect(anonymous.status).toBe(401);
    expect((await anonymous.json() as { error: string }).error).toBe("authentication_required");
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}/download`, "GET", undefined, token)).status).toBe(200);
    expect((await jsonFetch(`/v1/artworks/${first.artwork.id}/download`, "GET", undefined, token)).status).toBe(200);
    const row = await env.DB.prepare("SELECT download_count FROM artworks WHERE id = ?1").bind(first.artwork.id)
      .first<{ download_count: number }>();
    expect(row?.download_count).toBe(1);
  });

  it("rejects corrupt PNG structure instead of storing it", async () => {
    const token = await account("k", "PreviewGuard");
    const corrupt = PREVIEW.slice(0, -8) + "AAAAAAAA";
    const response = await jsonFetch("/v1/artworks", "POST", { ...uploadBody(90), preview_base64: corrupt }, token);
    expect(response.status).toBe(400);
    expect((await response.json() as { error: string }).error).toBe("invalid_preview");
    expect((await env.ASSETS.list()).objects).toHaveLength(0);
  });

  it("revokes sessions on sign-out and creator suspension", async () => {
    const token = await account("l", "SessionGuard");
    expect((await jsonFetch("/v1/session", "DELETE", undefined, token)).status).toBe(200);
    expect((await jsonFetch("/v1/session", "GET", undefined, token)).status).toBe(401);

    const active = await jsonFetch("/v1/auth/test", "POST", {
      installation_id: "l".repeat(64), display_name: "SessionGuard again",
    });
    const activeToken = String((await active.json() as { token: string }).token);
    const suspended = await jsonFetch("/v1/admin/users/action", "POST", {
      username: "SessionGuard", action: "suspend",
    }, "", true);
    expect(suspended.status).toBe(200);
    expect((await jsonFetch("/v1/session", "GET", undefined, activeToken)).status).toBe(401);

    const afterSuspend = await jsonFetch("/v1/auth/test", "POST", {
      installation_id: "l".repeat(64), display_name: "SessionGuard suspended",
    });
    const suspendedToken = String((await afterSuspend.json() as { token: string }).token);
    expect((await jsonFetch("/v1/artworks", "POST", uploadBody(91), suspendedToken)).status).toBe(403);
    expect((await jsonFetch("/v1/admin/users/action", "POST", {
      username: "SessionGuard", action: "restore",
    }, "", true)).status).toBe(200);
    expect((await jsonFetch("/v1/artworks", "POST", uploadBody(91), suspendedToken)).status).toBe(201);
  });

  it("supports creator profiles, follows, owner queues, and owner removal", async () => {
    const creatorToken = await account("e", "ProfileCreator");
    const upload = await (await jsonFetch("/v1/artworks", "POST", uploadBody(31), creatorToken)).json() as { artwork: { id: string } };
    const viewerToken = await account("f", "ProfileViewer");

    const follow = await jsonFetch("/v1/creators/ProfileCreator/follow", "POST", { follow: true }, viewerToken);
    expect(await follow.json()).toEqual({ followed: true, followers: 1 });
    const profile = await (await jsonFetch("/v1/creators/ProfileCreator", "GET", undefined, viewerToken)).json() as { creator: { followers: number; followed: boolean } };
    expect(profile.creator).toMatchObject({ followers: 1, followed: true });

    const mine = await (await jsonFetch("/v1/artworks?scope=mine", "GET", undefined, creatorToken)).json() as { total: number };
    expect(mine.total).toBe(1);
    expect((await jsonFetch(`/v1/artworks/${upload.artwork.id}`, "DELETE", undefined, creatorToken)).status).toBe(200);
    expect((await (await jsonFetch("/v1/artworks")).json() as { total: number }).total).toBe(0);
  });

  it("hides ignored creators from every catalog scope until they are unignored", async () => {
    const creatorToken = await account("ignored-creator", "IgnoredCreator");
    const upload = await (await jsonFetch("/v1/artworks", "POST", uploadBody(311), creatorToken)).json() as {
      artwork: { id: string };
    };
    const viewerToken = await account("ignored-viewer", "IgnoredViewer");
    expect((await jsonFetch("/v1/profile/ignored", "GET")).status).toBe(401);
    expect((await jsonFetch("/v1/creators/IgnoredViewer/ignore", "POST", { ignored: true }, viewerToken)).status).toBe(400);

    expect((await jsonFetch("/v1/creators/IgnoredCreator/follow", "POST", { follow: true }, viewerToken)).status).toBe(200);
    expect((await jsonFetch(`/v1/artworks/${upload.artwork.id}/favorite`, "POST", { favorite: true }, viewerToken)).status).toBe(200);
    const ignoredResponse = await jsonFetch(
      "/v1/creators/IgnoredCreator/ignore", "POST", { ignored: true }, viewerToken,
    );
    expect(ignoredResponse.status).toBe(200);
    expect(await ignoredResponse.json()).toMatchObject({
      ignored: true, ignored_count: 1, creator: { username: "IgnoredCreator" },
    });

    const profile = await (await jsonFetch(
      "/v1/creators/IgnoredCreator", "GET", undefined, viewerToken,
    )).json() as { creator: { ignored: boolean; followed: boolean } };
    expect(profile.creator).toMatchObject({ ignored: true, followed: true });
    const ignored = await (await jsonFetch("/v1/profile/ignored", "GET", undefined, viewerToken)).json() as {
      items: Array<{ username: string }>;
    };
    expect(ignored.items).toEqual([expect.objectContaining({ username: "IgnoredCreator" })]);
    const session = await (await jsonFetch("/v1/session", "GET", undefined, viewerToken)).json() as {
      stats: { ignored_count: number };
    };
    expect(session.stats.ignored_count).toBe(1);

    for (const scope of ["browse", "favorites", "following"]) {
      const catalog = await (await jsonFetch(`/v1/artworks?scope=${scope}`, "GET", undefined, viewerToken)).json() as {
        total: number;
      };
      expect(catalog.total).toBe(0);
    }
    await env.DB.prepare("UPDATE artworks SET featured = 1 WHERE id = ?1").bind(upload.artwork.id).run();
    expect((await (await jsonFetch(
      "/v1/artworks?scope=featured", "GET", undefined, viewerToken,
    )).json() as { total: number }).total).toBe(0);
    expect((await (await jsonFetch("/v1/artworks?scope=featured")).json() as { total: number }).total).toBe(1);

    const restoredResponse = await jsonFetch(
      "/v1/creators/IgnoredCreator/ignore", "POST", { ignored: false }, viewerToken,
    );
    expect(restoredResponse.status).toBe(200);
    expect(await restoredResponse.json()).toMatchObject({ ignored: false, ignored_count: 0 });
    expect((await (await jsonFetch("/v1/profile/ignored", "GET", undefined, viewerToken)).json() as {
      items: unknown[];
    }).items).toEqual([]);
    expect((await (await jsonFetch(
      "/v1/artworks?scope=featured", "GET", undefined, viewerToken,
    )).json() as { total: number }).total).toBe(1);
  });

  it("requires admin authentication and records moderation decisions", async () => {
    const token = await account("g", "ModeratedCreator");
    const uploaded = await (await jsonFetch("/v1/artworks", "POST", uploadBody(47), token)).json() as { artwork: { id: string } };
    const id = uploaded.artwork.id;
    await env.DB.batch([
      env.DB.prepare("UPDATE artworks SET status = 'pending', published_at = NULL WHERE id = ?1").bind(id),
      env.DB.prepare("UPDATE artwork_revisions SET status = 'pending' WHERE artwork_id = ?1").bind(id),
      env.DB.prepare("DELETE FROM artwork_search WHERE artwork_id = ?1").bind(id),
    ]);

    expect((await jsonFetch("/v1/admin/queue")).status).toBe(401);
    const queue = await (await jsonFetch("/v1/admin/queue", "GET", undefined, "", true)).json() as { items: Array<{ id: string }> };
    expect(queue.items[0]?.id).toBe(id);
    const approved = await jsonFetch("/v1/admin/moderate", "POST", {
      artwork_id: id, revision: 1, action: "approve", note: "Fixture approved",
    }, "", true);
    expect(approved.status).toBe(200);
    expect((await (await jsonFetch("/v1/artworks")).json() as { total: number }).total).toBe(1);
    const event = await env.DB.prepare(
      "SELECT action, note FROM moderation_events WHERE artwork_id = ?1 ORDER BY created_at DESC LIMIT 1",
    ).bind(id).first<{ action: string; note: string }>();
    expect(event).toMatchObject({ action: "approve", note: "Fixture approved" });
  });

  it("filters, sorts, searches, and paginates every admin artwork status", async () => {
    const token = await account("m", "AdminBrowserCreator");
    const lowBody = {
      ...uploadBody(61),
      title: "Handmade Low",
      classification: "handmade",
    };
    const highBody = {
      ...uploadBody(62),
      title: "Handmade High",
      classification: "handmade",
    };
    const toolBody = {
      ...uploadBody(63),
      title: "Toolmade Removed",
      classification: "toolmade",
    };
    const low = await (await jsonFetch("/v1/artworks", "POST", lowBody, token)).json() as { artwork: { id: string } };
    await env.DB.prepare(
      "UPDATE artwork_revisions SET preview_hash = 'admin-browser-low' WHERE artwork_id = ?1",
    ).bind(low.artwork.id).run();
    const high = await (await jsonFetch("/v1/artworks", "POST", highBody, token)).json() as { artwork: { id: string } };
    await env.DB.prepare(
      "UPDATE artwork_revisions SET preview_hash = 'admin-browser-high' WHERE artwork_id = ?1",
    ).bind(high.artwork.id).run();
    const tool = await (await jsonFetch("/v1/artworks", "POST", toolBody, token)).json() as { artwork: { id: string } };
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE artworks SET download_count = 2, favorite_count = 7, published_at = '2026-01-01T00:00:00Z' WHERE id = ?1",
      ).bind(low.artwork.id),
      env.DB.prepare(
        "UPDATE artworks SET download_count = 30, favorite_count = 3, published_at = '2026-02-01T00:00:00Z' WHERE id = ?1",
      ).bind(high.artwork.id),
      env.DB.prepare(
        "UPDATE artworks SET status = 'removed', download_count = 100 WHERE id = ?1",
      ).bind(tool.artwork.id),
      env.DB.prepare(
        "UPDATE artwork_revisions SET status = 'removed' WHERE artwork_id = ?1",
      ).bind(tool.artwork.id),
    ]);

    const first = await (await jsonFetch(
      "/v1/admin/queue?status=published&classification=handmade&sort=downloads&page=1&limit=1",
      "GET", undefined, "", true,
    )).json() as {
      items: Array<{ id: string; download_count: number }>;
      total: number;
      page: number;
      page_count: number;
    };
    expect(first).toMatchObject({ total: 2, page: 1, page_count: 2 });
    expect(first.items[0]).toMatchObject({ id: high.artwork.id, download_count: 30 });

    const second = await (await jsonFetch(
      "/v1/admin/queue?status=published&classification=handmade&sort=downloads&page=2&limit=1",
      "GET", undefined, "", true,
    )).json() as { items: Array<{ id: string }>; page: number };
    expect(second.page).toBe(2);
    expect(second.items[0]?.id).toBe(low.artwork.id);

    const removed = await (await jsonFetch(
      "/v1/admin/queue?status=all&classification=toolmade&search=removed&sort=latest",
      "GET", undefined, "", true,
    )).json() as { items: Array<{ id: string; status: string }>; total: number };
    expect(removed.total).toBe(1);
    expect(removed.items[0]).toMatchObject({ id: tool.artwork.id, status: "removed" });

    expect((await jsonFetch(
      "/v1/admin/queue?classification=unknown",
      "GET", undefined, "", true,
    )).status).toBe(400);
    expect((await jsonFetch(
      "/v1/admin/queue?sort=untrusted",
      "GET", undefined, "", true,
    )).status).toBe(400);
  });
});
