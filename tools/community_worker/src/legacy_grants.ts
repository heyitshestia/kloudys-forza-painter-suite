import { HttpError } from './security';
import type { Env, SessionUser } from './types';

export function canonicalTimestamp(value: unknown): number|null {
  if (typeof value !== 'string' || value.startsWith('0000-') || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) return null;
  const ms=Date.parse(value);
  return Number.isFinite(ms) && new Date(ms).toISOString() === value ? ms : null;
}
export function legacyCutoff(env:Env, now=Date.now()):string|null {
  const value=env.COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF;
  const ms=canonicalTimestamp(value);
  return ms !== null && ms<=now ? value! : null;
}
export interface LegacyGrantProof {
  entitlementId:string; licenseCreatedAt:string; cutoff:string; proofHash:string; issuedAt:string;
}
export function grantStatement(env:Env,user:SessionUser,proof:LegacyGrantProof):D1PreparedStatement {
  return env.DB.prepare(`INSERT INTO verified_legacy_grants(user_id,github_provider_id,entitlement_id,granted_at,
    license_created_at,eligibility_cutoff,source,proof_sha256,verified_at)
    SELECT id,provider_id,?3,?4,?5,?6,'signed_legacy_proof',?7,?8 FROM users
    WHERE id=?1 AND provider='github' AND provider_id=?2 AND suspended_at IS NULL
      AND supporter_entitlement_id=?3
      AND NOT EXISTS(SELECT 1 FROM verified_legacy_grants WHERE user_id=?1 AND entitlement_id=?3)
    ON CONFLICT(user_id) DO NOTHING`).bind(user.id,user.providerId,proof.entitlementId,new Date().toISOString(),
      proof.licenseCreatedAt,proof.cutoff,proof.proofHash,proof.issuedAt);
}
export async function grandfatheredAt(env:Env,user:SessionUser|null):Promise<string|null> {
  if (user?.provider !== 'github') return null;
  const row=await env.DB.prepare(`SELECT granted_at FROM verified_legacy_grants
    WHERE user_id=?1 AND github_provider_id=?2`).bind(user.id,user.providerId).first<{granted_at:string}>();
  return row && canonicalTimestamp(row.granted_at)!==null ? row.granted_at : null;
}

// Explicit operator task, never a public endpoint. Uses trusted pre-cutoff rows;
// retries cannot enroll post-cutoff proofs or erase/replace a prior grant.
export async function backfillLegacyGrants(env:Env):Promise<number> {
  const cutoff=legacyCutoff(env);
  if (!cutoff) throw new HttpError(503,'legacy_grant_configuration_error');
  const now=new Date().toISOString();
  const result=await env.DB.prepare(`INSERT OR IGNORE INTO verified_legacy_grants(user_id,github_provider_id,
    entitlement_id,granted_at,eligibility_cutoff,source,verified_at)
    SELECT id,provider_id,supporter_entitlement_id,?2,?1,'active_entitlement_snapshot',supporter_verified_at
    FROM users WHERE provider='github' AND supporter_entitlement_id IS NOT NULL
      AND supporter_verified_at <= ?1 AND supporter_verified_until > ?1
      AND strftime('%Y-%m-%dT%H:%M:%fZ',supporter_verified_at)=supporter_verified_at
      AND strftime('%Y-%m-%dT%H:%M:%fZ',supporter_verified_until)=supporter_verified_until
      AND NOT EXISTS(SELECT 1 FROM verified_legacy_grants g WHERE g.user_id=users.id)
    RETURNING user_id`)
    .bind(cutoff,now).all<{user_id:string}>();
  return result.results.length;
}
