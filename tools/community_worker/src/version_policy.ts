import { HttpError } from "./security";
import type { Env } from "./types";

const VERSION_PATTERN = /^(\d+)\.(\d+)\.(\d+)$/;
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const BRANCH_PATTERN = /^[A-Za-z0-9._/-]{1,120}$/;
const COMMIT_PATTERN = /^[0-9a-f]{40}$/;
const MAX_GITHUB_RESPONSE = 128 * 1024;
const MAX_GIT_REFS_RESPONSE = 512 * 1024;
const DEFAULT_VERSION = "3.0.81";
const DEFAULT_REPOSITORY = "heyitshestia/kloudys-forza-painter-suite";
const DEFAULT_BRANCH = "main";

export interface VersionPolicy {
  minimumVersion: string;
  automatic: boolean;
  repository: string;
  branch: string;
  sourceCommit: string;
  sourceTransport: string;
  sourceNote: string;
  syncedAt: string;
  lastAttemptAt: string;
  lastStatus: string;
  lastError: string;
}

export interface VersionSyncResult extends VersionPolicy {
  remoteVersion: string;
  changed: boolean;
}

function versionParts(value: string): [number, number, number] | null {
  const match = VERSION_PATTERN.exec(value);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

export function validateKfpsVersion(value: unknown): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!versionParts(text) || text.length > 32) {
    throw new HttpError(400, "invalid_version", "Use a complete KFPS version such as 3.0.81.");
  }
  return text;
}

export function compareKfpsVersions(left: string, right: string): number {
  const a = versionParts(left);
  const b = versionParts(right);
  if (!a || !b) throw new Error("invalid KFPS version comparison");
  for (let index = 0; index < 3; index += 1) {
    if (a[index]! !== b[index]!) return a[index]! > b[index]! ? 1 : -1;
  }
  return 0;
}

export function effectiveMinimumUploadVersion(env: Env, policy: VersionPolicy): string {
  if (env.REQUIRE_MODERN_UPLOAD_CLIENT !== "0") return policy.minimumVersion;
  return validateKfpsVersion(env.COMPATIBILITY_MINIMUM_UPLOAD_VERSION || DEFAULT_VERSION);
}

function configuredRepository(env: Env): string {
  const value = (env.VERSION_REPOSITORY || DEFAULT_REPOSITORY).trim();
  if (!REPOSITORY_PATTERN.test(value)) throw new Error("version repository is invalid");
  return value;
}

function configuredBranch(env: Env): string {
  const value = (env.VERSION_BRANCH || DEFAULT_BRANCH).trim();
  if (!BRANCH_PATTERN.test(value) || value.includes("..") || value.startsWith("/") || value.endsWith("/")) {
    throw new Error("version branch is invalid");
  }
  return value;
}

async function settings(env: Env): Promise<Map<string, string>> {
  const rows = await env.DB.prepare(
    "SELECT key, value FROM service_settings WHERE key LIKE 'version_%'",
  ).all<{ key: string; value: string }>();
  return new Map((rows.results || []).map((row) => [row.key, row.value]));
}

export async function getVersionPolicy(env: Env): Promise<VersionPolicy> {
  const stored = await settings(env);
  const fallback = validateKfpsVersion(env.MINIMUM_UPLOAD_VERSION || DEFAULT_VERSION);
  const candidate = stored.get("version_minimum") || fallback;
  const minimumVersion = versionParts(candidate) ? candidate : fallback;
  return {
    minimumVersion,
    automatic: (stored.get("version_automatic") || env.VERSION_SYNC_ENABLED || "1") !== "0",
    repository: configuredRepository(env),
    branch: configuredBranch(env),
    sourceCommit: stored.get("version_source_commit") || "",
    sourceTransport: stored.get("version_source_transport") || "",
    sourceNote: stored.get("version_source_note") || "",
    syncedAt: stored.get("version_synced_at") || "",
    lastAttemptAt: stored.get("version_last_attempt_at") || "",
    lastStatus: stored.get("version_last_status") || "not_synced",
    lastError: stored.get("version_last_error") || "",
  };
}

async function putSettings(env: Env, values: Record<string, string>, now = new Date().toISOString()): Promise<void> {
  await env.DB.batch(Object.entries(values).map(([key, value]) => env.DB.prepare(
    `INSERT INTO service_settings(key, value, updated_at) VALUES (?1, ?2, ?3)
     ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
  ).bind(key, value, now)));
}

async function boundedJson(response: Response): Promise<Record<string, unknown>> {
  if (!response.ok) throw new Error(`GitHub returned HTTP ${response.status}`);
  const declared = Number(response.headers.get("content-length") || "0");
  if (declared > MAX_GITHUB_RESPONSE) throw new Error("GitHub response was too large");
  const text = await response.text();
  if (text.length > MAX_GITHUB_RESPONSE) throw new Error("GitHub response was too large");
  const value = JSON.parse(text) as unknown;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("GitHub response was invalid");
  return value as Record<string, unknown>;
}

function decodeGitHubContent(value: unknown): string {
  if (typeof value !== "string" || value.length > 1024) throw new Error("GitHub VERSION content was invalid");
  const compact = value.replace(/\s+/g, "");
  try {
    return atob(compact).trim();
  } catch {
    throw new Error("GitHub VERSION content was not base64");
  }
}

async function boundedText(response: Response, maximum: number, label: string): Promise<string> {
  if (!response.ok) throw new Error(`${label} returned HTTP ${response.status}`);
  const declared = Number(response.headers.get("content-length") || "0");
  if (declared > maximum) throw new Error(`${label} response was too large`);
  const body = await response.arrayBuffer();
  if (body.byteLength > maximum) throw new Error(`${label} response was too large`);
  return new TextDecoder("utf-8", { fatal: true }).decode(body);
}

function errorMessage(error: unknown): string {
  return String(error instanceof Error ? error.message : error).slice(0, 160);
}

async function fetchVersionWithGitHubApi(
  repository: string,
  branch: string,
  fetcher: typeof fetch,
): Promise<{ version: string; commit: string }> {
  const headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "KFPS-Community-Version-Sync",
    "X-GitHub-Api-Version": "2026-03-10",
  };
  const commitResponse = await fetcher(
    `https://api.github.com/repos/${repository}/commits/${encodeURIComponent(branch)}`,
    { headers, redirect: "manual" },
  );
  const commitPayload = await boundedJson(commitResponse);
  const commit = String(commitPayload.sha || "").toLowerCase();
  if (!COMMIT_PATTERN.test(commit)) throw new Error("GitHub commit identity was invalid");

  const contentResponse = await fetcher(
    `https://api.github.com/repos/${repository}/contents/VERSION?ref=${commit}`,
    { headers, redirect: "manual" },
  );
  const contentPayload = await boundedJson(contentResponse);
  if (contentPayload.encoding !== "base64" || contentPayload.type !== "file") {
    throw new Error("GitHub VERSION response was invalid");
  }
  return { version: validateKfpsVersion(decodeGitHubContent(contentPayload.content)), commit };
}

function commitFromGitAdvertisement(advertisement: string, branch: string): string {
  const suffix = ` refs/heads/${branch}`;
  for (const line of advertisement.split("\n")) {
    const marker = line.indexOf(suffix);
    if (marker < 0) continue;
    const remainder = line.slice(marker + suffix.length);
    if (remainder && !remainder.startsWith("\0")) continue;
    const match = /([0-9a-f]{40})$/.exec(line.slice(0, marker));
    if (match && COMMIT_PATTERN.test(match[1]!)) return match[1]!;
  }
  throw new Error("Git transport did not advertise the configured branch");
}

async function fetchVersionWithGitTransport(
  repository: string,
  branch: string,
  fetcher: typeof fetch,
): Promise<{ version: string; commit: string }> {
  const refResponse = await fetcher(
    `https://github.com/${repository}.git/info/refs?service=git-upload-pack`,
    {
      headers: {
        "Accept": "application/x-git-upload-pack-advertisement",
        "User-Agent": "KFPS-Community-Version-Sync",
      },
      redirect: "manual",
    },
  );
  const advertisement = await boundedText(refResponse, MAX_GIT_REFS_RESPONSE, "Git transport");
  const commit = commitFromGitAdvertisement(advertisement, branch);
  const versionResponse = await fetcher(
    `https://raw.githubusercontent.com/${repository}/${commit}/VERSION`,
    {
      headers: { "Accept": "text/plain", "User-Agent": "KFPS-Community-Version-Sync" },
      redirect: "manual",
    },
  );
  const version = validateKfpsVersion(
    (await boundedText(versionResponse, 1024, "Raw VERSION")).trim(),
  );
  return { version, commit };
}

export async function fetchOfficialVersion(
  env: Env,
  fetcher: typeof fetch = fetch,
): Promise<{ version: string; commit: string; transport: string; sourceNote: string }> {
  const repository = configuredRepository(env);
  const branch = configuredBranch(env);
  try {
    const resolved = await fetchVersionWithGitHubApi(repository, branch, fetcher);
    return { ...resolved, transport: "github_api", sourceNote: "" };
  } catch (apiError) {
    try {
      const resolved = await fetchVersionWithGitTransport(repository, branch, fetcher);
      return {
        ...resolved,
        transport: "git_smart_http",
        sourceNote: `github_api_fallback: ${errorMessage(apiError)}`,
      };
    } catch (gitError) {
      throw new Error(
        `GitHub API failed (${errorMessage(apiError)}); Git transport failed (${errorMessage(gitError)})`,
      );
    }
  }
}

export async function syncVersionPolicy(
  env: Env,
  options: { force?: boolean; fetcher?: typeof fetch; reason?: string } = {},
): Promise<VersionSyncResult> {
  const before = await getVersionPolicy(env);
  if (!before.automatic && !options.force) {
    return { ...before, remoteVersion: "", changed: false };
  }
  const attemptedAt = new Date().toISOString();
  await putSettings(env, {
    version_last_attempt_at: attemptedAt,
    version_last_status: "checking",
    version_last_error: "",
  }, attemptedAt);
  try {
    const official = await fetchOfficialVersion(env, options.fetcher || fetch);
    const comparison = compareKfpsVersions(official.version, before.minimumVersion);
    const minimumVersion = comparison >= 0 ? official.version : before.minimumVersion;
    const status = comparison > 0 ? "updated" : comparison === 0 ? "current" : "ignored_older";
    const syncedAt = new Date().toISOString();
    await putSettings(env, {
      version_minimum: minimumVersion,
      version_automatic: "1",
      version_source_commit: official.commit,
      version_source_transport: official.transport,
      version_source_note: official.sourceNote,
      version_synced_at: syncedAt,
      version_last_attempt_at: attemptedAt,
      version_last_status: status,
      version_last_error: "",
      version_last_reason: String(options.reason || "scheduled").slice(0, 40),
    }, syncedAt);
    return {
      ...(await getVersionPolicy(env)),
      remoteVersion: official.version,
      changed: minimumVersion !== before.minimumVersion,
    };
  } catch (error) {
    const message = String(error instanceof Error ? error.message : error).slice(0, 240);
    await putSettings(env, {
      version_last_attempt_at: attemptedAt,
      version_last_status: "failed",
      version_last_error: message,
    }, new Date().toISOString());
    throw error;
  }
}

export async function maybeSyncVersionPolicy(env: Env, minimumIntervalSeconds = 300): Promise<void> {
  const policy = await getVersionPolicy(env);
  if (!policy.automatic) return;
  const lastAttempt = Date.parse(policy.lastAttemptAt);
  if (Number.isFinite(lastAttempt) && Date.now() - lastAttempt < minimumIntervalSeconds * 1000) return;
  await syncVersionPolicy(env, { reason: "upload_observed" });
}

export async function setManualVersionPolicy(
  env: Env,
  minimumVersion: string,
  automatic = false,
): Promise<VersionPolicy> {
  const version = validateKfpsVersion(minimumVersion);
  const now = new Date().toISOString();
  await putSettings(env, {
    version_minimum: version,
    version_automatic: automatic ? "1" : "0",
    version_last_status: automatic ? "manual_then_automatic" : "manual_override",
    version_last_error: "",
  }, now);
  return getVersionPolicy(env);
}

export function publicVersionPolicy(policy: VersionPolicy): Record<string, unknown> {
  return {
    minimum_upload_version: policy.minimumVersion,
    automatic: policy.automatic,
    repository: policy.repository,
    branch: policy.branch,
    source_commit: policy.sourceCommit,
    source_transport: policy.sourceTransport,
    source_note: policy.sourceNote,
    synced_at: policy.syncedAt,
    last_attempt_at: policy.lastAttemptAt,
    last_status: policy.lastStatus,
    last_error: policy.lastError,
  };
}
