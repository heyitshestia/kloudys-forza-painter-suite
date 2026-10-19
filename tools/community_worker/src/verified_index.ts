import { adminAuthorized, HttpError, jsonResponse, readJsonObject, sha256Hex } from './security';
import { canonicalizeDesign } from './validation';
import { vinylFingerprint, type VinylFingerprint } from './vinyl_fingerprint';
import { READINESS_KEY } from './contributions';
import { backfillLegacyGrants } from './legacy_grants';
import type { Env } from './types';

const MAX_BYTES=24*1024*1024;
async function boundedBytes(object:R2ObjectBody):Promise<Uint8Array> {
  if(object.size<1 || object.size>MAX_BYTES) {await object.body.cancel();throw new Error('invalid_size');}
  const reader=object.body.getReader(),chunks:Uint8Array[]=[];let total=0;
  try {
    for(;;) {
      const {done,value}=await reader.read();if(done) break;
      total+=value.length;if(total>object.size || total>MAX_BYTES) throw new Error('invalid_size');chunks.push(value);
    }
    if(total!==object.size) throw new Error('invalid_size');
  } finally {await reader.cancel().catch(()=>undefined);reader.releaseLock();}
  const bytes=new Uint8Array(total);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  return bytes;
}
export async function verifiedIndexStatus(env:Env) {
  const row=await env.DB.prepare(`SELECT COUNT(*) AS total,
    COALESCE(SUM(r.credit_fingerprint_status='unknown'),0) AS unknown,
    COALESCE(SUM(r.credit_fingerprint_status='review_required'),0) AS review_required
    FROM artwork_revisions r JOIN artworks a ON a.id=r.artwork_id WHERE a.kind='vinyl'`).first<any>();
  const state=await env.DB.prepare('SELECT value FROM service_settings WHERE key=?1').bind(READINESS_KEY).first<any>();
  return {...row,ready:state?.value==='ready' && row.unknown===0};
}
export async function indexHistoricalVinyls(env:Env,limit=4) {
  if(!Number.isInteger(limit) || limit<1 || limit>4) throw new HttpError(400,'invalid_index_limit');
  const rows=await env.DB.prepare(`SELECT r.artwork_id,r.revision,r.content_hash,r.design_key
    FROM artwork_revisions r JOIN artworks a ON a.id=r.artwork_id
    WHERE a.kind='vinyl' AND r.credit_fingerprint_status='unknown'
    ORDER BY a.created_at,a.id,r.revision LIMIT ?1`).bind(limit).all<any>();
  let indexed=0,review=0;
  for(const row of rows.results) {
    let fp:VinylFingerprint={version:1,status:'review_required',fingerprint:null,reason:'unavailable_evidence'};
    let storageRead=false;
    try {
      const prefix=`artworks/${row.artwork_id}/r${row.revision}/`;
      if(typeof row.design_key!=='string' || !row.design_key.startsWith(prefix)
        || !/^[A-Za-z0-9_/-]+\.json$/.test(row.design_key) || row.design_key.includes('..')) throw new Error('invalid_key');
      storageRead=true;
      const object=await env.ASSETS.get(row.design_key);
      storageRead=false;
      if(!object) throw new Error('missing_blob');
      storageRead=true;
      let bytes:Uint8Array;
      try {bytes=await boundedBytes(object);}
      catch(error) {if(error instanceof Error && error.message==='invalid_size') storageRead=false;throw error;}
      storageRead=false;
      if(await sha256Hex(bytes)!==row.content_hash) throw new Error('hash_mismatch');
      const stored=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      const design=canonicalizeDesign(stored,{id:'historical-canonical',label:'Historical canonical',
        known:stored.format==='kfps.community.v1' && stored.metadata?.schema_known===true,games:[]});
      fp=await vinylFingerprint(design);
    } catch {
      if(storageRead) throw new HttpError(503,'verified_index_storage_unavailable');
      // Unavailable/uncertain old files are review-required, never guessed.
    }
    const now=new Date().toISOString();
    const results=await env.DB.batch([
      env.DB.prepare(`UPDATE artwork_revisions SET credit_fingerprint=?5,credit_fingerprint_status=?6
        WHERE artwork_id=?1 AND revision=?2 AND content_hash=?3 AND design_key=?4 AND credit_fingerprint_status='unknown'
        RETURNING artwork_id`).bind(row.artwork_id,row.revision,row.content_hash,row.design_key,fp.fingerprint,fp.status),
      env.DB.prepare(`INSERT INTO vinyl_fingerprints(version,fingerprint,artwork_id,reserved_at)
        SELECT 1,credit_fingerprint,artwork_id,?5 FROM artwork_revisions
        WHERE artwork_id=?1 AND revision=?2 AND content_hash=?3 AND design_key=?4
          AND credit_fingerprint_status='qualified' AND credit_fingerprint=?6
        ON CONFLICT(version,fingerprint) DO UPDATE SET historical_collision=CASE
          WHEN vinyl_fingerprints.artwork_id<>excluded.artwork_id THEN 1 ELSE vinyl_fingerprints.historical_collision END`)
        .bind(row.artwork_id,row.revision,row.content_hash,row.design_key,now,fp.fingerprint),
    ]);
    if(results[0]?.results.length) {indexed++;if(fp.status==='review_required') review++;}
  }
  return {indexed,batch_review_required:review,...await verifiedIndexStatus(env)};
}
export async function finalizeVerifiedIndex(env:Env) {
  const results=await env.DB.batch([
    env.DB.prepare(`INSERT INTO service_settings(key,value,updated_at)
      SELECT ?1,'ready',?2 WHERE NOT EXISTS(SELECT 1 FROM artwork_revisions r JOIN artworks a ON a.id=r.artwork_id
        WHERE a.kind='vinyl' AND r.credit_fingerprint_status='unknown')
      ON CONFLICT(key) DO UPDATE SET value='ready',updated_at=excluded.updated_at RETURNING key`)
      .bind(READINESS_KEY,new Date().toISOString()),
  ]);
  if(!results[0]?.results.length) throw new HttpError(409,'verified_index_incomplete');
  return verifiedIndexStatus(env);
}
export async function handleVerifiedMaintenance(request:Request,env:Env) {
  if(!adminAuthorized(request,env)) throw new HttpError(401,'admin_auth_required');
  const value=await readJsonObject(request,1024);
  if(Object.keys(value).length!==1 || typeof value.action!=='string') throw new HttpError(400,'invalid_index_action');
  let result;
  switch(value.action) {
    case 'status':return jsonResponse(await verifiedIndexStatus(env));
    case 'index_batch':result=await indexHistoricalVinyls(env);break;
    case 'finalize':result=await finalizeVerifiedIndex(env);break;
    case 'backfill_legacy_grants':result={granted:await backfillLegacyGrants(env)};break;
    default:throw new HttpError(400,'invalid_index_action');
  }
  await env.DB.prepare(`INSERT INTO moderation_events(id,artwork_id,actor,action,note,created_at)
    VALUES(?1,NULL,'admin','verified_maintenance',?2,?3)`)
    .bind(crypto.randomUUID(),JSON.stringify({action:value.action,...result}),new Date().toISOString()).run();
  return jsonResponse(result);
}
