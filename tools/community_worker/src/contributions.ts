import { HttpError } from './security';
import type { Env } from './types';
import type { VinylFingerprint } from './vinyl_fingerprint';

export const READINESS_KEY = 'verified_fingerprints_v1';
export async function requireFingerprintReadiness(env: Env): Promise<void> {
  const row = await env.DB.prepare('SELECT value FROM service_settings WHERE key=?1').bind(READINESS_KEY).first<{value:string}>();
  const missing = await env.DB.prepare(`SELECT 1 AS missing FROM artwork_revisions r JOIN artworks a ON a.id=r.artwork_id
    WHERE a.kind='vinyl' AND r.credit_fingerprint_status='unknown' LIMIT 1`).first();
  if (row?.value !== 'ready' || missing) throw new HttpError(503, 'verified_index_not_ready', 'Verified access is not ready. Please try later.');
}

export function settleStatement(env: Env, artworkId: string | null = null): D1PreparedStatement {
  return env.DB.prepare(`UPDATE vinyl_contributions SET
    eligible_at=(SELECT e.eligible_at FROM vinyl_eligible_contributions e WHERE e.artwork_id=vinyl_contributions.artwork_id),
    credited_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE credited_at IS NULL AND revoked_at IS NULL AND (?1 IS NULL OR artwork_id=?1)
      AND EXISTS(SELECT 1 FROM service_settings WHERE key=?2 AND value='ready')
      AND EXISTS(SELECT 1 FROM vinyl_eligible_contributions e WHERE e.artwork_id=vinyl_contributions.artwork_id)`)
    .bind(artworkId, READINESS_KEY);
}

export async function settleContributions(env: Env, artworkId: string | null = null): Promise<void> {
  await settleStatement(env, artworkId).run();
}

export async function eligibleVinylCount(env: Env, creatorId: string): Promise<number> {
  const row = await env.DB.prepare(`SELECT COUNT(*) AS total FROM vinyl_contributions c
    JOIN artworks a ON a.id=c.artwork_id AND a.kind='vinyl' AND a.classification='handmade'
    JOIN vinyl_fingerprints f ON f.version=1 AND f.fingerprint=c.fingerprint
      AND f.artwork_id=c.artwork_id AND f.historical_collision=0
    WHERE c.creator_id=?1 AND revoked_at IS NULL AND (credited_at IS NOT NULL OR EXISTS(
      SELECT 1 FROM vinyl_eligible_contributions e WHERE e.artwork_id=c.artwork_id))`)
    .bind(creatorId).first<{total:number}>();
  return Number(row?.total || 0);
}

export interface RevisionCredit {
  artworkId: string; creatorId: string; revision: number; contentHash: string;
  fingerprint: VinylFingerprint; authorship: 'unknown' | 'own' | 'permission';
  assertionSource?: 'upload' | 'owner_claim' | 'admin';
  expectedPreviewKey?: string;
}

export function revisionContributionStatements(env: Env, input: RevisionCredit): D1PreparedStatement[] {
  const {artworkId:id, creatorId, revision, contentHash, fingerprint:fp, authorship} = input;
  const now = new Date().toISOString();
  const statements = [
    settleStatement(env, id),
    env.DB.prepare(`UPDATE artwork_revisions SET credit_fingerprint=?5,
      credit_fingerprint_status=?6, credit_authorship=?7
      WHERE artwork_id=?1 AND revision=?2 AND content_hash=?3 AND EXISTS(
        SELECT 1 FROM artworks a WHERE a.id=?1 AND a.creator_id=?4 AND a.kind='vinyl')
        AND (?8 IS NULL OR preview_key=?8)`)
      .bind(id, revision, contentHash, creatorId, fp.fingerprint, fp.status, authorship, input.expectedPreviewKey || null),
    env.DB.prepare(`INSERT OR IGNORE INTO vinyl_fingerprints(version,fingerprint,artwork_id,reserved_at)
      SELECT 1,r.credit_fingerprint,r.artwork_id,?5 FROM artwork_revisions r JOIN artworks a ON a.id=r.artwork_id
      WHERE a.id=?1 AND a.creator_id=?4 AND a.kind='vinyl' AND r.revision=?2 AND r.content_hash=?3
        AND r.credit_fingerprint_status='qualified' AND r.credit_fingerprint IS NOT NULL
        AND (?6 IS NULL OR r.preview_key=?6)`)
      .bind(id, revision, contentHash, creatorId, now, input.expectedPreviewKey || null),
  ];
  if (authorship === 'own') {
    statements.push(env.DB.prepare(`INSERT INTO vinyl_contributions(artwork_id,creator_id,
      assertion_revision,assertion_content_hash,assertion_source,asserted_at,fingerprint)
      SELECT a.id,a.creator_id,r.revision,r.content_hash,?5,?6,r.credit_fingerprint
      FROM artworks a JOIN artwork_revisions r ON r.artwork_id=a.id
      WHERE a.id=?1 AND a.creator_id=?4 AND a.kind='vinyl' AND r.revision=?2 AND r.content_hash=?3
        AND (?7 IS NULL OR r.preview_key=?7)
      ON CONFLICT(artwork_id) DO UPDATE SET assertion_revision=excluded.assertion_revision,
        assertion_content_hash=excluded.assertion_content_hash,assertion_source=excluded.assertion_source,
        asserted_at=excluded.asserted_at,fingerprint=excluded.fingerprint
      WHERE vinyl_contributions.credited_at IS NULL AND vinyl_contributions.revoked_at IS NULL
        AND NOT EXISTS(SELECT 1 FROM vinyl_eligible_contributions e WHERE e.artwork_id=excluded.artwork_id)`)
      .bind(id, revision, contentHash, creatorId, input.assertionSource || 'upload', now, input.expectedPreviewKey || null));
  }
  statements.push(settleStatement(env, id));
  return statements;
}

export interface ContributionStatus {
  state: 'not_claimed'|'permission_only'|'pending_publication'|'scheduled'|'credited'|'revoked'|'duplicate'|'review_required'|'not_eligible';
  can_claim: boolean; eligible_at: string|null; credited_at: string|null;
}

export async function contributionStatuses(env: Env, ids: string[]): Promise<Map<string, ContributionStatus>> {
  if (!ids.length) return new Map();
  if (ids.length > 100) throw new Error('Contribution batch exceeds limit');
  const rows = await env.DB.prepare(`SELECT a.id,a.kind,a.classification,a.status,a.starts_at,a.current_revision,a.content_hash,
    r.credit_fingerprint,r.credit_fingerprint_status,r.credit_authorship,
    c.artwork_id AS claimed,c.assertion_revision,c.assertion_content_hash,c.revoked_at,c.credited_at,c.eligible_at,e.eligible_at AS due_at,
    f.artwork_id AS reserved_for,f.historical_collision,cf.historical_collision AS credit_collision,
    cf.artwork_id AS credit_reserved_for,
    EXISTS(SELECT 1 FROM vinyl_publications p WHERE p.artwork_id=a.id AND p.revision=a.current_revision
      AND p.content_hash=a.content_hash
      AND MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) <= strftime('%Y-%m-%dT%H:%M:%fZ','now')
      AND (p.ends_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) < p.ends_at)
      AND (p.closed_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) < p.closed_at)) AS has_window
    FROM artworks a JOIN artwork_revisions r ON r.artwork_id=a.id AND r.revision=a.current_revision
    LEFT JOIN vinyl_contributions c ON c.artwork_id=a.id
    LEFT JOIN vinyl_eligible_contributions e ON e.artwork_id=a.id
    LEFT JOIN vinyl_fingerprints f ON f.version=1 AND f.fingerprint=r.credit_fingerprint
    LEFT JOIN vinyl_fingerprints cf ON cf.version=1 AND cf.fingerprint=c.fingerprint
    WHERE a.id IN (${ids.map((_,i)=>`?${i+1}`).join(',')})`).bind(...ids).all<Record<string,unknown>>();
  return new Map((rows.results || []).map(row => {
    let state: ContributionStatus['state'];
    if (row.kind !== 'vinyl' || row.classification !== 'handmade') state='not_eligible';
    else if (row.revoked_at) state='revoked';
    else if (row.credited_at && (row.credit_collision || row.credit_reserved_for!==row.id)) state='duplicate';
    else if (row.credited_at || row.due_at) state='credited';
    else if (row.credit_fingerprint_status !== 'qualified' || !row.has_window && ['removed','rejected'].includes(String(row.status))) state='review_required';
    else if (row.historical_collision || row.reserved_for !== row.id) state='duplicate';
    else if (!row.claimed || row.assertion_revision!==row.current_revision || row.assertion_content_hash!==row.content_hash) {
      state=row.credit_authorship === 'permission' ? 'permission_only' : 'not_claimed';
    }
    else if (row.status !== 'published') state='pending_publication';
    else if (row.starts_at && String(row.starts_at)>new Date().toISOString()) state='scheduled';
    else state='review_required';
    return [String(row.id), {state, can_claim:['not_claimed','permission_only'].includes(state),
      eligible_at: (row.eligible_at || row.due_at || null) as string|null,
      credited_at: (row.credited_at || null) as string|null}];
  }));
}
