import { env } from "cloudflare:test";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  effectiveMinimumUploadVersion,
  fetchOfficialVersion,
  getVersionPolicy,
  maybeSyncVersionPolicy,
  setManualVersionPolicy,
  syncVersionPolicy,
} from "../src/version_policy";

function githubFetcher(version: string, commit = "a".repeat(40)): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.redirect).toBe("manual");
    const url = String(input);
    if (url.endsWith("/commits/main")) {
      return new Response(JSON.stringify({ sha: commit }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.endsWith(`/contents/VERSION?ref=${commit}`)) {
      return new Response(JSON.stringify({
        type: "file",
        encoding: "base64",
        content: btoa(`${version}\n`),
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response("not found", { status: 404 });
  }) as unknown as typeof fetch;
}

function gitFallbackFetcher(version: string, commit = "b".repeat(40)): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.redirect).toBe("manual");
    const url = String(input);
    if (url.startsWith("https://api.github.com/")) {
      return new Response("rate limited", { status: 403 });
    }
    if (url.endsWith(".git/info/refs?service=git-upload-pack")) {
      return new Response(
        `001e# service=git-upload-pack\n0000${commit} refs/heads/main\n0000`,
        { status: 200, headers: { "Content-Type": "application/x-git-upload-pack-advertisement" } },
      );
    }
    if (url.endsWith(`/${commit}/VERSION`)) {
      return new Response(`${version}\n`, { status: 200, headers: { "Content-Type": "text/plain" } });
    }
    return new Response("not found", { status: 404 });
  }) as unknown as typeof fetch;
}

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM service_settings").run();
});

describe("repository-authoritative version policy", () => {
  it("keeps the compatibility floor stable until strict rollout is enabled", async () => {
    await setManualVersionPolicy(env, "3.1.43", true);
    const policy = await getVersionPolicy(env);
    expect(effectiveMinimumUploadVersion({
      ...env,
      REQUIRE_MODERN_UPLOAD_CLIENT: "0",
      COMPATIBILITY_MINIMUM_UPLOAD_VERSION: "3.0.81",
    }, policy)).toBe("3.0.81");
    expect(effectiveMinimumUploadVersion({
      ...env,
      REQUIRE_MODERN_UPLOAD_CLIENT: "1",
      COMPATIBILITY_MINIMUM_UPLOAD_VERSION: "3.0.81",
    }, policy)).toBe("3.1.43");
  });

  it("pins VERSION to the resolved main commit and raises the upload floor", async () => {
    const fetcher = githubFetcher("3.0.82");
    const official = await fetchOfficialVersion(env, fetcher);
    expect(official).toEqual({
      version: "3.0.82", commit: "a".repeat(40), transport: "github_api", sourceNote: "",
    });

    const result = await syncVersionPolicy(env, { fetcher, force: true, reason: "test" });
    expect(result).toMatchObject({
      minimumVersion: "3.0.82",
      remoteVersion: "3.0.82",
      sourceCommit: "a".repeat(40),
      sourceTransport: "github_api",
      lastStatus: "updated",
      changed: true,
    });
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(String((fetcher as ReturnType<typeof vi.fn>).mock.calls[3]?.[0])).toContain(`ref=${"a".repeat(40)}`);
  });

  it("falls back to exact Git refs and immutable raw VERSION when REST is unavailable", async () => {
    const fetcher = gitFallbackFetcher("3.1.43");
    const official = await fetchOfficialVersion(env, fetcher);
    expect(official).toMatchObject({
      version: "3.1.43",
      commit: "b".repeat(40),
      transport: "git_smart_http",
    });
    expect(official.sourceNote).toContain("HTTP 403");
    expect(fetcher).toHaveBeenCalledTimes(3);

    const result = await syncVersionPolicy(env, { fetcher, force: true, reason: "fallback_test" });
    expect(result).toMatchObject({
      sourceCommit: "b".repeat(40),
      sourceTransport: "git_smart_http",
      lastStatus: "updated",
    });
  });

  it("never lowers a newer floor during automatic synchronization", async () => {
    await setManualVersionPolicy(env, "3.1.0", true);
    const result = await syncVersionPolicy(env, { fetcher: githubFetcher("3.0.99"), reason: "test" });
    expect(result).toMatchObject({
      minimumVersion: "3.1.0",
      remoteVersion: "3.0.99",
      lastStatus: "ignored_older",
      changed: false,
    });
  });

  it("retains the last verified floor when GitHub fails", async () => {
    await setManualVersionPolicy(env, "3.0.85", true);
    const failing = vi.fn(async () => new Response("unavailable", { status: 503 })) as unknown as typeof fetch;
    await expect(syncVersionPolicy(env, { fetcher: failing })).rejects.toThrow("HTTP 503");
    expect(await getVersionPolicy(env)).toMatchObject({
      minimumVersion: "3.0.85",
      lastStatus: "failed",
    });
  });

  it("keeps an explicit rollback paused until an administrator syncs again", async () => {
    await setManualVersionPolicy(env, "3.0.80", false);
    const fetcher = githubFetcher("3.0.90");
    await maybeSyncVersionPolicy(env, 0);
    expect(fetcher).not.toHaveBeenCalled();
    expect(await getVersionPolicy(env)).toMatchObject({ minimumVersion: "3.0.80", automatic: false });
  });
});
