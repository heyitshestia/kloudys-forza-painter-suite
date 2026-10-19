import { getViewerAccess, getAccessPolicy, requestAccessContract } from './access_policy';
import { contributionStatuses, requireFingerprintReadiness, settleStatement } from './contributions';
import { enforceRateLimit, HttpError, jsonResponse, readJsonObject, requireUser, adminAuthorized } from './security';
import type { Env } from './types';

interface Selection {artwork_id:string;revision:number;content_sha256:string}
function exact(value:Record<string,unknown>,keys:string[]) {
  return Object.keys(value).length===keys.length && keys.every(key=>Object.hasOwn(value,key));
}
function selection(value:unknown):Selection {
  if(!value || typeof value!=='object' || Array.isArray(value)) throw new HttpError(400,'invalid_claim');
  const v=value as Record<string,unknown>;
  if(!exact(v,['artwork_id','revision','content_sha256']) || typeof v.artwork_id!=='string'
    || !v.artwork_id.length || v.artwork_id.length>64 || typeof v.revision!=='number'
    || !Number.isSafeInteger(v.revision) || v.revision<1 || typeof v.content_sha256!=='string'
    || !/^[a-f0-9]{64}$/.test(v.content_sha256)) throw new HttpError(400,'invalid_claim');
  return v as unknown as Selection;
}

async function readClaim(env:Env,item:Selection,creatorId:string) {
  return env.DB.prepare(`SELECT a.id,a.kind,a.classification,a.status,a.current_revision,a.content_hash,
    c.artwork_id AS claimed,c.assertion_revision,c.assertion_content_hash,c.revoked_at,c.credited_at
    FROM artworks a LEFT JOIN vinyl_contributions c ON c.artwork_id=a.id
    WHERE a.id=?1 AND a.creator_id=?2`).bind(item.artwork_id,creatorId).first<Record<string,unknown>>();
}
async function checkClaim(env:Env,item:Selection,creatorId:string) {
  const row=await readClaim(env,item,creatorId);
  const contribution=row?(await contributionStatuses(env,[item.artwork_id])).get(item.artwork_id)??null:null;
  const error=!row?'artwork_not_found':row.kind!=='vinyl'?'vinyl_required'
    :row.current_revision!==item.revision || row.content_hash!==item.content_sha256?'claim_revision_changed'
    :row.classification!=='handmade'?'handmade_required':row.revoked_at?'credit_revoked'
    :contribution?.state==='duplicate'?'duplicate_contribution'
    :!contribution || ['review_required','not_eligible'].includes(contribution.state)?'claim_evidence_required':null;
  return {row,contribution,error};
}

async function claim(env:Env,item:Selection,creatorId:string,source:'owner_claim'|'admin',note='') {
  const before=await checkClaim(env,item,creatorId);
  const result=(outcome:'accepted'|'unchanged'|'rejected',error:string|null,contribution=before.contribution)=>
    ({artwork_id:item.artwork_id,outcome,error,contribution});
  if(before.error) return result('rejected',before.error);
  if(before.row?.claimed && (before.row.credited_at || before.row.assertion_revision===item.revision
      && before.row.assertion_content_hash===item.content_sha256)) return result('unchanged',null);
  const now=new Date().toISOString();
  // Every mutating statement repeats the current identity/revision/classification
  // predicates: a preflight lookup cannot authorize a later, different revision.
  const eligible=`SELECT a.id FROM artworks a JOIN artwork_revisions r
    ON r.artwork_id=a.id AND r.revision=a.current_revision
    JOIN vinyl_fingerprints f ON f.version=1 AND f.fingerprint=r.credit_fingerprint
      AND f.artwork_id=a.id AND f.historical_collision=0
    WHERE a.id=?1 AND a.creator_id=?2 AND a.current_revision=?3 AND a.content_hash=?4
      AND r.content_hash=?4 AND a.kind='vinyl' AND a.classification='handmade'
      AND r.credit_fingerprint_status='qualified'
      AND NOT EXISTS(SELECT 1 FROM vinyl_contributions c WHERE c.artwork_id=a.id AND c.revoked_at IS NOT NULL)
      AND (a.status IN ('published','pending') OR EXISTS(SELECT 1 FROM vinyl_publications p
        WHERE p.artwork_id=a.id AND p.revision=?3 AND p.content_hash=?4
        AND MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at))<=strftime('%Y-%m-%dT%H:%M:%fZ','now')
        AND (p.ends_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at))<p.ends_at)
        AND (p.closed_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at))<p.closed_at)))`;
  const args=[item.artwork_id,creatorId,item.revision,item.content_sha256];
  const results=await env.DB.batch([
    env.DB.prepare(`UPDATE artwork_revisions SET credit_authorship='own'
      WHERE artwork_id IN (${eligible}) AND revision=?3 AND content_hash=?4 RETURNING artwork_id`).bind(...args),
    env.DB.prepare(`INSERT INTO vinyl_contributions(artwork_id,creator_id,assertion_revision,assertion_content_hash,
      assertion_source,asserted_at,fingerprint)
      SELECT artwork_id,?2,revision,content_hash,?5,?6,credit_fingerprint FROM artwork_revisions
      WHERE artwork_id IN (${eligible}) AND revision=?3 AND content_hash=?4
      ON CONFLICT(artwork_id) DO UPDATE SET assertion_revision=excluded.assertion_revision,
        assertion_content_hash=excluded.assertion_content_hash,assertion_source=excluded.assertion_source,
        asserted_at=excluded.asserted_at,fingerprint=excluded.fingerprint
      WHERE vinyl_contributions.credited_at IS NULL AND vinyl_contributions.revoked_at IS NULL
        AND (vinyl_contributions.assertion_revision<>excluded.assertion_revision
          OR vinyl_contributions.assertion_content_hash<>excluded.assertion_content_hash)
        AND NOT EXISTS(SELECT 1 FROM vinyl_eligible_contributions e WHERE e.artwork_id=excluded.artwork_id)`)
      .bind(...args,source,now),
    env.DB.prepare(`INSERT INTO moderation_events(id,artwork_id,actor,action,note,created_at)
      SELECT ?1,?2,?3,?4,?5,?6 WHERE changes()>0`)
      .bind(crypto.randomUUID(),item.artwork_id,source==='admin'?'admin':creatorId,
        source==='admin'?'credit_approve':'own_vinyl_claim',note,now),
    settleStatement(env,item.artwork_id),
  ]);
  const after=await checkClaim(env,item,creatorId);
  if(!(results[0]?.results.length)) return result('rejected',after.error || 'claim_revision_changed',after.contribution);
  return result('accepted',null,after.contribution);
}

export async function handleVinylClaims(request:Request,env:Env):Promise<Response> {
  const user=await requireUser(request,env);
  if(getAccessPolicy(env).mode!=='verified_v1') throw new HttpError(409,'verified_policy_disabled');
  if(!requestAccessContract(request)) throw new HttpError(426,'client_update_required');
  if(user.provider!=='github' || !user.providerId) throw new HttpError(403,'github_required');
  await requireFingerprintReadiness(env);
  const value=await readJsonObject(request,16*1024);
  if(!exact(value,['assertion','claims']) || value.assertion!=='own_original_vinyl_v1'
    || !Array.isArray(value.claims) || value.claims.length<1 || value.claims.length>10) throw new HttpError(400,'invalid_claim_batch');
  const items=value.claims.map(selection);
  if(new Set(items.map(item=>item.artwork_id)).size!==items.length) throw new HttpError(400,'invalid_claim_batch');
  await enforceRateLimit(env,user.id,'vinyl_claims',10,3600);
  const results=[];
  for(const item of items) results.push(await claim(env,item,user.id,'owner_claim'));
  const context=await getViewerAccess(env,request,user);
  return jsonResponse({results,access_policy:context.policy,capabilities:{verified:context.verified}});
}

export async function handleCreditModeration(request:Request,env:Env,value:Record<string,unknown>):Promise<Response> {
  if(!adminAuthorized(request,env)) throw new HttpError(401,'admin_auth_required');
  if(!exact(value,['artwork_id','action','revision','content_sha256','note'])
    || typeof value.note!=='string' || !value.note.trim() || value.note.length>500) throw new HttpError(400,'invalid_credit_action');
  const item=selection({artwork_id:value.artwork_id,revision:value.revision,content_sha256:value.content_sha256});
  await requireFingerprintReadiness(env);
  const art=await env.DB.prepare('SELECT creator_id,current_revision,content_hash FROM artworks WHERE id=?1')
    .bind(item.artwork_id).first<{creator_id:string;current_revision:number;content_hash:string}>();
  if(!art) throw new HttpError(404,'artwork_not_found');
  if(art.current_revision!==item.revision || art.content_hash!==item.content_sha256) throw new HttpError(409,'claim_revision_changed');
  if(value.action==='credit_approve') {
    const result=await claim(env,item,art.creator_id,'admin',value.note.trim());
    if(result.error) throw new HttpError(409,result.error);
  } else {
    const revoke=value.action==='credit_revoke';
    if(!revoke && value.action!=='credit_restore') throw new HttpError(400,'invalid_credit_action');
    const qualification=revoke?'':` AND revoked_at IS NOT NULL AND EXISTS(SELECT 1 FROM artworks a
      JOIN vinyl_fingerprints f ON f.version=1 AND f.fingerprint=vinyl_contributions.fingerprint
        AND f.artwork_id=a.id AND f.historical_collision=0
      WHERE a.id=?1 AND a.kind='vinyl' AND a.classification='handmade')`;
    const results=await env.DB.batch([
      settleStatement(env,item.artwork_id),
      env.DB.prepare(`UPDATE vinyl_contributions SET revoked_at=?4,revocation_note=?5
        WHERE artwork_id=?1 AND EXISTS(SELECT 1 FROM artworks a WHERE a.id=?1 AND a.current_revision=?2 AND a.content_hash=?3)
        ${qualification} RETURNING artwork_id`).bind(item.artwork_id,item.revision,item.content_sha256,
          revoke?new Date().toISOString():null,value.note.trim()),
      settleStatement(env,item.artwork_id),
    ]);
    if(!results[1]?.results.length) throw new HttpError(409,'claim_evidence_required');
  }
  return jsonResponse({artwork_id:item.artwork_id,action:value.action,ok:true,
    contribution:(await contributionStatuses(env,[item.artwork_id])).get(item.artwork_id)});
}
