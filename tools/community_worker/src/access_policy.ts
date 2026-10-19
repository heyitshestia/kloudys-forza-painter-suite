import { eligibleVinylCount, requireFingerprintReadiness } from './contributions';
import { HttpError } from './security';
import { hasActiveSupporter, requireActiveSupporter } from './supporter';
import type { Env, SessionUser } from './types';
import { canonicalTimestamp,grandfatheredAt } from './legacy_grants';

export const REQUIRED_ACCOUNT_AGE_DAYS = 14;
export const REQUIRED_OWN_VINYLS = 10;
const WAIT_MS = REQUIRED_ACCOUNT_AGE_DAYS * 24 * 60 * 60 * 1000;
export function getAccessPolicy(env: Env) {
  const configured = env.COMMUNITY_ACCESS_POLICY;
  if (configured !== undefined && configured !== 'legacy' && configured !== 'verified-v1') {
    throw new HttpError(503, 'access_policy_configuration_error', 'Community access configuration is unavailable.');
  }
  const mode = configured === 'verified-v1' ? 'verified_v1' : 'legacy_supporter';
  return {version:1 as const, mode, required_own_vinyls:REQUIRED_OWN_VINYLS,
    required_account_age_days:REQUIRED_ACCOUNT_AGE_DAYS, count_basis:'lifetime_own_handmade_vinyls' as const,
    own_claims_enabled:mode === 'verified_v1'};
}
export function requestAccessContract(request: Request): boolean {
  return request.headers.get('X-Community-Access-Contract') === '1';
}
export function requireAccessContract(request: Request): void {
  if (!requestAccessContract(request)) throw new HttpError(426, 'client_update_required', 'Update KFPS to use this Community operation.');
}

// Only accept the UTC shape written by the worker, with exact calendar validation.
export function connectionWindow(user: SessionUser|null, now = Date.now()) {
  const raw = user?.provider === 'github' ? user.communityConnectedAt : undefined;
  const normalized = typeof raw === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(raw)
    ? raw.includes('.') ? raw : raw.replace('Z','.000Z') : '';
  const ms=canonicalTimestamp(normalized);
  if (!Number.isFinite(now) || ms===null || ms > now || !Number.isFinite(ms + WAIT_MS)) {
    return {connected_at:null, eligible_after:null, mature:false};
  }
  return {connected_at:normalized, eligible_after:new Date(ms + WAIT_MS).toISOString(), mature:now >= ms + WAIT_MS};
}

export type VerifiedReason = 'eligible'|'contributions_required'|'policy_legacy'|'account_suspended'|
  'unsupported_identity'|'waiting_period'|'connection_date_unavailable'|'grandfathered_supporter';
export function verifiedCapability(policy: ReturnType<typeof getAccessPolicy>, user: SessionUser|null,
  count: number, now = Date.now(), grandfatheredAt: string|null = null) {
  const window = connectionWindow(user,now);
  let reason:VerifiedReason;
  if (policy.mode !== 'verified_v1') reason='policy_legacy';
  else if (user?.suspended) reason='account_suspended';
  else if (user?.provider !== 'github') reason='unsupported_identity';
  else if (grandfatheredAt) reason='grandfathered_supporter';
  else if (!window.connected_at) reason='connection_date_unavailable';
  else if (!window.mature) reason='waiting_period';
  else if (count < REQUIRED_OWN_VINYLS) reason='contributions_required';
  else reason='eligible';
  return {policy_version:1 as const, active:reason === 'eligible' || reason === 'grandfathered_supporter', eligible_vinyl_count:count,
    required_count:REQUIRED_OWN_VINYLS, required_account_age_days:REQUIRED_ACCOUNT_AGE_DAYS,
    connected_at:window.connected_at, eligible_after:window.eligible_after, grandfathered_at:grandfatheredAt, reason};
}

export async function getViewerAccess(env: Env, request: Request, user: SessionUser|null) {
  const policy=getAccessPolicy(env);
  let ready=false, count=0;
  if (policy.mode === 'verified_v1') {
    try { await requireFingerprintReadiness(env); ready=true; }
    catch(error) { if (!(error instanceof HttpError) || error.code !== 'verified_index_not_ready') throw error; }
    // Index uncertainty disables credit/access, never otherwise-valid public uploads.
    if (ready && user?.provider === 'github') count=await eligibleVinylCount(env,user.id);
  }
  return {policy,user,contract:requestAccessContract(request),ready,
    verified:verifiedCapability(policy,user,count,Date.now(),await grandfatheredAt(env,user))};
}
export type ViewerAccess = Awaited<ReturnType<typeof getViewerAccess>>;
export function requireRestrictedAccess(context: ViewerAccess): void {
  if (context.policy.mode === 'legacy_supporter') { requireActiveSupporter(context.user); return; }
  if (!context.user) throw new HttpError(401,'authentication_required');
  if (context.user.suspended) throw new HttpError(403,'account_suspended');
  if (!context.contract) throw new HttpError(426,'client_update_required','Update KFPS to use this Community operation.');
  if (!context.ready && !context.verified.grandfathered_at) throw new HttpError(503,'verified_index_not_ready');
  if (!context.verified.active) throw new HttpError(403,'verified_required','Verified requires 14 days since your first Community GitHub connection and 10 eligible own Handmade vinyls, or a permanent existing-key grant.');
}
export function validateAudience(value: Record<string,unknown>, context: ViewerAccess, kind:'vinyl'|'livery') {
  if (context.policy.mode === 'legacy_supporter') {
    if (value.supporter_only === true) requireRestrictedAccess(context);
    return {value,authorship:'unknown' as const};
  }
  if (!context.contract) throw new HttpError(426,'client_update_required');
  if (typeof value.audience!=='string' || !['public','verified'].includes(value.audience)) throw new HttpError(400,'invalid_audience');
  if (kind === 'vinyl' && (typeof value.authorship!=='string' || !['own','permission'].includes(value.authorship))) throw new HttpError(400,'invalid_authorship');
  if (kind === 'livery' && 'authorship' in value) throw new HttpError(400,'invalid_authorship');
  const restricted=value.audience === 'verified';
  if ('supporter_only' in value && value.supporter_only !== restricted) throw new HttpError(400,'audience_conflict');
  if (restricted) requireRestrictedAccess(context);
  return {value:{...value,supporter_only:restricted},authorship:kind === 'vinyl' ? value.authorship as 'own'|'permission' : 'unknown' as const};
}

export function artworkAccess(row: Record<string,unknown>, context: ViewerAccess) {
  const {user,policy}=context, restricted=Boolean(row.supporter_only);
  const unavailable=Boolean(row.purged_at) || row.status === 'removed' ||
    Boolean(row.ends_at && String(row.ends_at)<=new Date().toISOString());
  const audience=restricted ? policy.mode === 'verified_v1' ? 'verified' : 'supporter' : 'public';
  let reason:string|null=null;
  if (unavailable) reason='unavailable';
  else if (!user) reason='authentication_required';
  else if (user.suspended) reason='account_suspended';
  else if (restricted && policy.mode === 'verified_v1' && !context.contract) reason='client_update_required';
  else if (restricted && !(policy.mode === 'verified_v1' ? context.verified.active : hasActiveSupporter(user))) {
    reason=policy.mode === 'verified_v1' ? 'verified_required' : 'supporter_required';
  }
  const canDownload=reason === null;
  return {audience,can_view_media:!unavailable && (!restricted || canDownload),
    can_download:canDownload,can_interact:canDownload,restriction_reason:reason};
}
