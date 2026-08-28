import {
  createSession,
  enforceRateLimit,
  HttpError,
  httpsUrl,
  jsonResponse,
  optionalUser,
  plainText,
  readJsonObject,
  requireUser,
  secureTokenEqual,
  sha256Hex,
} from "./security";
import type { Env, SessionUser } from "./types";
import { publicSupporterState } from "./supporter";

const USERNAME_PATTERN = /^[A-Za-z0-9_]{3,24}$/;
const INSTALLATION_PATTERN = /^[A-Za-z0-9_-]{24,128}$/;

interface GitHubUser {
  id?: number;
  login?: string;
  avatar_url?: string;
}

export function publicUser(user: SessionUser): Record<string, unknown> {
  return {
    id: user.id,
    provider: user.provider,
    provider_login: user.providerLogin,
    username: user.username,
    bio: user.bio,
    website_url: user.websiteUrl,
    avatar_url: user.avatarUrl,
    suspended: user.suspended,
  };
}

async function upsertProviderUser(
  env: Env,
  provider: "github" | "local-test",
  providerId: string,
  login: string,
  avatarUrl: string,
): Promise<string> {
  const now = new Date().toISOString();
  const existing = await env.DB.prepare(
    "SELECT id FROM users WHERE provider = ?1 AND provider_id = ?2 LIMIT 1",
  ).bind(provider, providerId).first<{ id: string }>();
  if (existing) {
    await env.DB.prepare(
      "UPDATE users SET provider_login = ?2, avatar_url = ?3, updated_at = ?4 WHERE id = ?1",
    ).bind(existing.id, login, avatarUrl, now).run();
    return existing.id;
  }
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO users(id, provider, provider_id, provider_login, avatar_url, created_at, updated_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?6)`,
  ).bind(id, provider, providerId, login, avatarUrl, now).run();
  return id;
}

export async function handleTestAuth(request: Request, env: Env): Promise<Response> {
  if (env.ALLOW_TEST_AUTH !== "1") throw new HttpError(404, "not_found");
  const expectedToken = env.TEST_AUTH_TOKEN || "";
  if (expectedToken && !secureTokenEqual(request.headers.get("x-community-test-token") || "", expectedToken)) {
    throw new HttpError(401, "test_authentication_required");
  }
  const value = await readJsonObject(request, 4096);
  const installationId = plainText(value.installation_id, "installation_id", 128, true);
  if (!INSTALLATION_PATTERN.test(installationId)) throw new HttpError(400, "invalid_installation_id");
  const displayName = plainText(value.display_name, "display_name", 60, false) || "Local KFPS Tester";
  await enforceRateLimit(env, installationId, "test_auth", 8, 60);
  const providerId = await sha256Hex(`kfps-community-local:${installationId}`);
  const userId = await upsertProviderUser(env, "local-test", providerId, displayName, "");
  const token = await createSession(env, userId);
  const user = await env.DB.prepare(
    "SELECT COALESCE(username, '') AS username FROM users WHERE id = ?1",
  ).bind(userId).first<{ username: string }>();
  return jsonResponse({ token, username_required: !user?.username, provider: "local-test" });
}

export async function handleGitHubAuth(request: Request, env: Env): Promise<Response> {
  const value = await readJsonObject(request, 4096);
  const accessToken = plainText(value.access_token, "access_token", 512, true);
  await enforceRateLimit(env, request.headers.get("cf-connecting-ip") || "unknown", "github_auth", 12, 60);
  const response = await fetch("https://api.github.com/user", {
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${accessToken}`,
      "User-Agent": "KFPS-Community-Library",
      "X-GitHub-Api-Version": "2026-03-10",
    },
  });
  if (!response.ok) throw new HttpError(401, "github_auth_failed", "GitHub did not accept this sign-in.");
  const profileText = await response.text();
  if (profileText.length > 64 * 1024) throw new HttpError(502, "invalid_github_response");
  let profile: GitHubUser;
  try {
    profile = JSON.parse(profileText) as GitHubUser;
  } catch {
    throw new HttpError(502, "invalid_github_response");
  }
  if (!Number.isInteger(profile.id) || !profile.login) throw new HttpError(401, "github_auth_failed");
  const userId = await upsertProviderUser(
    env,
    "github",
    String(profile.id),
    plainText(profile.login, "github_login", 80, true),
    profile.avatar_url ? httpsUrl(profile.avatar_url, "avatar_url") : "",
  );
  const token = await createSession(env, userId);
  const user = await env.DB.prepare(
    "SELECT COALESCE(username, '') AS username FROM users WHERE id = ?1",
  ).bind(userId).first<{ username: string }>();
  return jsonResponse({ token, username_required: !user?.username, provider: "github" });
}

export async function handleSession(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env, false);
  const stats = await env.DB.prepare(
    `SELECT
       (SELECT COUNT(*) FROM artworks WHERE creator_id = ?1 AND status = 'published') AS artwork_count,
       (SELECT COUNT(*) FROM favorites WHERE user_id = ?1) AS favorite_count,
       (SELECT COUNT(*) FROM follows WHERE follower_id = ?1) AS following_count,
       (SELECT COUNT(*) FROM follows WHERE creator_id = ?1) AS follower_count`,
  ).bind(user.id).first<Record<string, number>>();
  return jsonResponse({ user: publicUser(user), stats: stats || {}, supporter: publicSupporterState(user) });
}

export async function handleSignOut(request: Request, env: Env): Promise<Response> {
  await requireUser(request, env, false);
  const token = (request.headers.get("authorization") || "").split(" ", 2)[1] || "";
  await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?1").bind(await sha256Hex(token)).run();
  return jsonResponse({ signed_out: true });
}

export async function handleChooseUsername(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env, false);
  if (user.username) throw new HttpError(409, "username_locked", "Community usernames can only be chosen once.");
  const value = await readJsonObject(request, 4096);
  const username = plainText(value.username, "username", 24, true);
  if (!USERNAME_PATTERN.test(username)) {
    throw new HttpError(400, "invalid_username", "Use 3-24 letters, numbers, or underscores.");
  }
  const confirmation = plainText(value.confirm_username, "confirm_username", 24, false);
  if (confirmation !== username) {
    throw new HttpError(
      400,
      "username_confirmation_required",
      "Confirm the exact username, including capitalization, before choosing it permanently.",
    );
  }
  const normalized = username.toLocaleLowerCase("en-US");
  const reserved = await env.DB.prepare(
    "SELECT 1 AS found FROM reserved_usernames WHERE username_norm = ?1 LIMIT 1",
  ).bind(normalized).first();
  if (reserved) throw new HttpError(409, "username_unavailable", "That username is reserved.");
  await enforceRateLimit(env, user.id, "choose_username", 5, 3600);
  try {
    const result = await env.DB.prepare(
      `UPDATE users SET username = ?2, username_norm = ?3, updated_at = ?4
       WHERE id = ?1 AND username IS NULL RETURNING id`,
    ).bind(user.id, username, normalized, new Date().toISOString()).first();
    if (!result) throw new HttpError(409, "username_locked");
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(409, "username_unavailable", "That username is already in use.");
  }
  const updated = await optionalUser(request, env);
  return jsonResponse({ user: updated ? publicUser({ ...updated, username }) : { username } });
}

export async function handleUpdateProfile(request: Request, env: Env): Promise<Response> {
  const user = await requireUser(request, env);
  await enforceRateLimit(env, user.id, "update_profile", 30, 3600);
  const value = await readJsonObject(request, 8192);
  const bio = plainText(value.bio, "bio", 280, false);
  const website = httpsUrl(value.website_url, "website_url");
  const now = new Date().toISOString();
  await env.DB.prepare(
    "UPDATE users SET bio = ?2, website_url = ?3, updated_at = ?4 WHERE id = ?1",
  ).bind(user.id, bio, website, now).run();
  return jsonResponse({ user: publicUser({ ...user, bio, websiteUrl: website }) });
}
