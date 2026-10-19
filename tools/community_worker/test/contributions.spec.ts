import { env } from 'cloudflare:test';
import { beforeEach, expect, it } from 'vitest';
import { contributionStatuses, eligibleVinylCount, requireFingerprintReadiness, revisionContributionStatements,
  settleContributions } from '../src/contributions';

beforeEach(async () => {
  await env.DB.batch(['moderation_events','verified_legacy_grants','reports','artwork_search','artworks','vinyl_fingerprints',
    'sessions','users','service_settings'].map(t=>env.DB.prepare(`DELETE FROM ${t}`)));
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,created_at,updated_at)
    VALUES('owner','github','1','synthetic','2026-01-01','2026-01-01')`).run();
  await env.DB.prepare("INSERT INTO service_settings(key,value,updated_at) VALUES('verified_fingerprints_v1','ready','2026-01-01')").run();
});

async function seed(id:string, options:{status?:string; start?:string; end?:string; fingerprint?:string; authorship?:'own'|'permission'|'unknown'}={}) {
  const status=options.status||'published', hash=id.padEnd(64,'0');
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO artworks(id,creator_id,title,category,classification,tags_json,games_json,license,shape_count,status,
      content_hash,preview_hash,created_at,updated_at,starts_at,ends_at)
      VALUES(?1,'owner',?1,'Original Artwork','handmade','[]','[]','kfps-community-share-v1',1,?2,?3,?3,
      '2026-01-01','2026-01-01',?4,?5)`).bind(id,status,hash,options.start||null,options.end||null),
    env.DB.prepare(`INSERT INTO artwork_revisions(artwork_id,revision,content_hash,preview_hash,design_key,preview_key,
      design_bytes,preview_bytes,shape_count,manifest_json,status,created_at)
      VALUES(?1,1,?2,?2,?1,?1,1,1,1,'{}',?3,'2026-01-01')`).bind(id,hash,status),
    ...revisionContributionStatements(env,{artworkId:id,creatorId:'owner',revision:1,contentHash:hash,
      authorship:options.authorship||'own',fingerprint:{version:1,status:'qualified',fingerprint:options.fingerprint||hash,reason:'test'}}),
  ]);
}

it('earns once, keeps lifetime credit after removal, with transactional audit',async()=>{
  await seed('one');
  expect(await eligibleVinylCount(env,'owner')).toBe(1);
  await env.DB.prepare("UPDATE artworks SET status='removed' WHERE id='one'").run();
  await settleContributions(env);
  expect(await eligibleVinylCount(env,'owner')).toBe(1);
  expect((await contributionStatuses(env,['one'])).get('one')?.state).toBe('credited');
  expect((await env.DB.prepare("SELECT COUNT(*) AS n FROM moderation_events WHERE action='credit_issued'").first<any>()).n).toBe(1);
});

it('does not credit permission, pending, future, or duplicate originals',async()=>{
  await seed('permission',{authorship:'permission'});
  await seed('pending',{status:'pending'});
  await seed('future',{start:'2999-01-01T00:00:00.000Z'});
  await seed('duplicate',{fingerprint:'permission'.padEnd(64,'0')});
  expect(await eligibleVinylCount(env,'owner')).toBe(0);
  const states=await contributionStatuses(env,['permission','pending','future','duplicate']);
  expect([...states.values()].map(s=>s.state).sort()).toEqual(['duplicate','pending_publication','permission_only','scheduled']);
});

it('settles expired windows but not removal-before-start or approval-after-end',async()=>{
  await seed('expired',{start:'2998-01-01T00:00:00.000Z',end:'2999-01-01T00:00:00.000Z'});
  // Simulate a clock-independent historical committed window, without re-opening it.
  await env.DB.prepare(`UPDATE vinyl_publications SET committed_at='2026-01-01T00:00:00.000Z',
    starts_at='2026-01-02T00:00:00.000Z',ends_at='2026-01-03T00:00:00.000Z' WHERE artwork_id='expired'`).run();
  await seed('early',{start:'2999-01-01T00:00:00.000Z'});
  await env.DB.prepare("UPDATE artworks SET status='removed' WHERE id='early'").run();
  await seed('late',{end:'2026-01-01T00:00:00.000Z'});
  await settleContributions(env);
  expect(await eligibleVinylCount(env,'owner')).toBe(1);
});

it('revocation is sticky and audit survives ordinary reassertion',async()=>{
  await seed('one');
  await env.DB.prepare("UPDATE vinyl_contributions SET revoked_at='2026-01-01',revocation_note='test' WHERE artwork_id='one'").run();
  await env.DB.batch(revisionContributionStatements(env,{artworkId:'one',creatorId:'owner',revision:1,
    contentHash:'one'.padEnd(64,'0'),authorship:'own',fingerprint:{version:1,status:'qualified',fingerprint:'one'.padEnd(64,'0'),reason:'test'}}));
  expect(await eligibleVinylCount(env,'owner')).toBe(0);
  expect((await contributionStatuses(env,['one'])).get('one')?.state).toBe('revoked');
});

it('index readiness fails closed and stale operation guards cannot claim',async()=>{
  await seed('one',{authorship:'unknown'});
  await requireFingerprintReadiness(env);
  await env.DB.batch(revisionContributionStatements(env,{artworkId:'one',creatorId:'owner',revision:1,
    contentHash:'one'.padEnd(64,'0'),authorship:'own',expectedPreviewKey:'wrong-operation',
    fingerprint:{version:1,status:'qualified',fingerprint:'one'.padEnd(64,'0'),reason:'test'}}));
  expect(await eligibleVinylCount(env,'owner')).toBe(0);
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown'").run();
  await expect(requireFingerprintReadiness(env)).rejects.toMatchObject({status:503});
});

it('readiness searches the covering status index and still rejects an unknown revision',async()=>{
  await seed('catalogue');
  await env.DB.prepare(`WITH RECURSIVE revisions(n) AS (
    SELECT 2 UNION ALL SELECT n+1 FROM revisions WHERE n<4096
  ) INSERT INTO artwork_revisions(artwork_id,revision,content_hash,preview_hash,design_key,preview_key,
    design_bytes,preview_bytes,shape_count,manifest_json,status,created_at,credit_fingerprint_status)
    SELECT r.artwork_id,n,printf('%064x',n),printf('%064x',n),r.design_key,r.preview_key,r.design_bytes,
      r.preview_bytes,r.shape_count,r.manifest_json,r.status,r.created_at,'qualified'
    FROM revisions JOIN artwork_revisions r ON r.artwork_id='catalogue' AND r.revision=1`).run();
  expect(await env.DB.prepare('SELECT COUNT(*) n FROM artwork_revisions').first('n')).toBe(4096);

  // Capture the production query so this plan assertion cannot drift to a test-only query.
  const queries:string[]=[];
  const db=new Proxy(env.DB,{get(target,key){
    if(key==='prepare') return (sql:string)=>{queries.push(sql);return target.prepare(sql);};
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }});
  await requireFingerprintReadiness({...env,DB:db});
  const query=queries.find(sql=>sql.includes('credit_fingerprint_status'));
  expect(query).toBeDefined();
  const plan=await env.DB.prepare(`EXPLAIN QUERY PLAN ${query!}`).all<{detail:string}>();
  const read=await env.DB.prepare(query!).all();
  console.log('READINESS_QUERY_PLAN '+JSON.stringify({revisions:4096,unknown:0,
    details:plan.results.map(row=>row.detail),rows_read:read.meta.rows_read}));
  expect(plan.results.map(row=>row.detail).join('\n')).toMatch(
    /SEARCH r USING COVERING INDEX idx_artwork_revisions_credit_status_artwork \(credit_fingerprint_status=\?\)/);

  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown' WHERE revision=4096").run();
  await expect(requireFingerprintReadiness(env)).rejects.toMatchObject({status:503,code:'verified_index_not_ready'});
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='review_required' WHERE revision=4096").run();
  await requireFingerprintReadiness(env);
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown' WHERE revision=4096").run();
  await env.DB.prepare("UPDATE artworks SET kind='livery' WHERE id='catalogue'").run();
  await requireFingerprintReadiness(env);
  await env.DB.prepare("DELETE FROM service_settings WHERE key='verified_fingerprints_v1'").run();
  await expect(requireFingerprintReadiness(env)).rejects.toMatchObject({status:503,code:'verified_index_not_ready'});
});

it('Toolmade never counts and audited classification correction changes the effective count without another credit',async()=>{
  await seed('one');
  await env.DB.prepare("UPDATE artworks SET classification='toolmade' WHERE id='one'").run();
  expect(await eligibleVinylCount(env,'owner')).toBe(0);
  expect((await contributionStatuses(env,['one'])).get('one')).toMatchObject({state:'not_eligible',can_claim:false});
  await env.DB.prepare("UPDATE artworks SET classification='handmade' WHERE id='one'").run();
  expect(await eligibleVinylCount(env,'owner')).toBe(1);
  expect((await env.DB.prepare("SELECT COUNT(*) n FROM vinyl_contributions").first<any>()).n).toBe(1);
});
