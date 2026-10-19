import { createExecutionContext, env, waitOnExecutionContext } from 'cloudflare:test';
import { beforeEach, expect, it, vi, afterEach } from 'vitest';
import { zlibSync,zipSync,strToU8 } from 'fflate';
import worker from '../src/index';
import { createSession,sha256Hex } from '../src/security';
import type { Env } from '../src/types';
import { indexHistoricalVinyls,finalizeVerifiedIndex } from '../src/verified_index';
import { purgeExpiredArtwork } from '../src/availability';
import issuerFixture from './fixtures/legacy-issuer.json';

const runtime={...env,COMMUNITY_ACCESS_POLICY:'verified-v1',VERSION_SYNC_ENABLED:'0'};
const native=()=>({type:1048677,data:[0,0,1,1,0,0,0],color:[200,50,70,255]});

function png(seed:number):string {
  function chunk(name:string,data:Uint8Array) {
    const out=new Uint8Array(12+data.length),view=new DataView(out.buffer);
    view.setUint32(0,data.length);out.set(new TextEncoder().encode(name),4);out.set(data,8);
    let crc=0xffffffff;
    for (const byte of out.subarray(4,-4)) {crc^=byte;for(let i=0;i<8;i++) crc=(crc>>>1)^((crc&1)?0xedb88320:0);}
    view.setUint32(out.length-4,(crc^0xffffffff)>>>0);return out;
  }
  const header=new Uint8Array(13),view=new DataView(header.buffer);
  view.setUint32(0,64);view.setUint32(4,64);header[8]=8;header[9]=6;
  const pixels=new Uint8Array(64*(64*4+1));
  for(let y=0;y<64;y++) for(let x=0;x<64;x++) {
    const i=y*257+1+x*4;pixels.set([seed%256,(seed*7+x)%256,y*3,255],i);
  }
  const pieces=[new Uint8Array([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',zlibSync(pixels)),chunk('IEND',new Uint8Array())];
  return btoa(pieces.map(p=>String.fromCharCode(...p)).join(''));
}
function upload(seed:number,extra:Record<string,unknown>={}) {
  const shape=native();shape.data[0]=seed;
  return {title:`Synthetic ${seed}`,description:'Local regression fixture',category:'Original Artwork',
    classification:'handmade',authorship:'own',audience:'public',confirm_rights:true,
    tags:['test'],games:['FH6'],license:'kfps-community-share-v1',client_version:'3.0.81',
    design:{format:'fh6_typecode_json_export_v1',shapes:[shape]},
    preview_base64:png(seed),thumbnail_base64:png(seed+100),...extra};
}
async function call(path:string,method='GET',body?:unknown,token='',bindings:Env=runtime,admin=false) {
  const ctx=createExecutionContext();
  const response=await worker.fetch(new Request(`https://community.test${path}`,{method,
    headers:{'Content-Type':'application/json','X-Community-Access-Contract':'1',
      ...(token?{Authorization:`Bearer ${token}`} : {}),...(admin?{'X-Community-Admin-Token':env.ADMIN_TOKEN}:{})},
    body:body===undefined?undefined:JSON.stringify(body)}),bindings,ctx);
  await waitOnExecutionContext(ctx);return response;
}
async function account(id='owner') {
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,username,username_norm,created_at,updated_at)
    VALUES(?1,'github',?1,?1,?1,?1,'2020-01-01T00:00:00.000Z','2020-01-01T00:00:00.000Z')`).bind(id).run();
  return createSession(env,id);
}
async function count(token:string) {
  const result=await call('/v1/session','GET',undefined,token);
  expect(result.status).toBe(200);return (await result.json() as any).capabilities.verified;
}
beforeEach(async()=>{
  await env.DB.batch(['moderation_events','verified_legacy_grants','reports','artwork_search','artworks',
    'vinyl_fingerprints','sessions','users','rate_limits','service_settings'].map(t=>env.DB.prepare(`DELETE FROM ${t}`)));
  const stored=await env.ASSETS.list();if(stored.objects.length) await env.ASSETS.delete(stored.objects.map(x=>x.key));
  await env.DB.prepare("INSERT INTO service_settings(key,value,updated_at) VALUES('verified_fingerprints_v1','ready','2020-01-01')").run();
});
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});

it('actual ten own Handmade uploads grant access; Toolmade and permission do not',async()=>{
  const token=await account();
  for(let i=0;i<10;i++) {
    const response=await call('/v1/artworks','POST',upload(i),token);
    expect(response.status,await response.clone().text()).toBe(201);
    expect(await count(token)).toMatchObject({eligible_vinyl_count:i+1,active:i===9});
  }
  for(const extra of [{classification:'toolmade'},{authorship:'permission'}]) {
    const response=await call('/v1/artworks','POST',upload(extra.classification?20:21,extra),token);
    expect(response.status,await response.clone().text()).toBe(201);
  }
  expect(await count(token)).toMatchObject({eligible_vinyl_count:10,active:true,reason:'eligible'});
});

it.each(['padding','mask_rgb','rectangle_rotation'])('actual %s variations cannot turn one artwork into ten credits',async(kind)=>{
  const token=await account();
  for(let i=0;i<10;i++) {
    const shapes=kind==='padding'?[native(),{...native(),data:[i,0,1,1,0,0,0],color:[0,0,0,0]}]
      :kind==='mask_rgb'?[native(),{...native(),mask:true,data:[0,0,.5,.5,0,0,1],color:[i,80,40,255]}]
      :[{type:1,data:[0,0,10,10,i],color:[200,50,70,255]}];
    const response=await call('/v1/artworks','POST',upload(i,{design:{shapes}}),token);
    expect(response.status,await response.clone().text()).toBe(201);
    expect(await count(token)).toMatchObject({eligible_vinyl_count:1,active:false});
  }
});

it('ambiguous masks still upload normally without earning automatic credit',async()=>{
  const token=await account();
  const masks=[{...native(),mask:false,data:[0,0,1,1,0,0,1]},
    {...native(),mask:false,data:[0,0,1,1,0,0,.5]},
    {...native(),mask:true,data:[0,0,1,1,0,0,1],color:[10,80,40,0]}];
  for(let i=0;i<masks.length;i++) {
    const response=await call('/v1/artworks','POST',upload(i,{design:{shapes:[native(),masks[i]]}}),token);
    expect(response.status,await response.clone().text()).toBe(201);
    expect((await response.json() as any).artwork.contribution.state).toBe('review_required');
  }
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0,active:false});
});

it.each(['1','0'])('an inflight revision cannot overwrite an admin Toolmade correction (auto-publish %s)',async(publish)=>{
  const token=await account();
  const created=await call('/v1/artworks','POST',upload(1),token);
  expect(created.status,await created.clone().text()).toBe(201);
  const id=(await created.json() as any).artwork.id;
  const before=(await env.ASSETS.list()).objects.map(x=>x.key).sort();
  let corrected=false;
  const bucket=new Proxy(env.ASSETS,{get(target,key){
    if(key==='put') return async(...args:Parameters<R2Bucket['put']>)=>{
      if(!corrected) {
        corrected=true;
        const response=await call('/v1/admin/moderate','POST',{
          artwork_id:id,action:'classify_toolmade',note:'Synthetic staff correction'},'',runtime,true);
        expect(response.status,await response.clone().text()).toBe(200);
      }
      return (target.put as any)(...args);
    };
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }});
  const response=await call(`/v1/artworks/${id}/revisions`,'POST',upload(2,{change_note:'Synthetic revision'}),token,
    {...runtime,ASSETS:bucket,AUTO_PUBLISH_VALIDATED_UPLOADS:publish,AUTO_APPROVE_TEST_UPLOADS:'0'});
  expect(corrected).toBe(true);
  expect(response.status,await response.clone().text()).toBe(409);
  expect(await response.json()).toMatchObject({error:'classification_immutable'});
  expect(await env.DB.prepare('SELECT classification,current_revision FROM artworks WHERE id=?1').bind(id).first())
    .toEqual({classification:'toolmade',current_revision:1});
  const revisions=await env.DB.prepare('SELECT revision,manifest_json FROM artwork_revisions WHERE artwork_id=?1').bind(id).all<any>();
  expect(revisions.results).toHaveLength(1);
  expect(JSON.parse(revisions.results[0].manifest_json).classification).toBe('toolmade');
  expect((await env.ASSETS.list()).objects.map(x=>x.key).sort()).toEqual(before);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0,active:false});
});

it('owner claims are bounded, identity/revision checked, idempotent and moderated without unlocking Toolmade',async()=>{
  const token=await account(),other=await account('other');
  const response=await call('/v1/artworks','POST',upload(1,{authorship:'permission'}),token);
  expect(response.status,await response.clone().text()).toBe(201);
  const art=(await response.json() as any).artwork;
  const row=await env.DB.prepare('SELECT current_revision,content_hash FROM artworks WHERE id=?1').bind(art.id).first<any>();
  const item={artwork_id:art.id,revision:row.current_revision,content_sha256:row.content_hash};
  const body={assertion:'own_original_vinyl_v1',claims:[item]};
  expect((await (await call('/v1/profile/vinyl-claims','POST',body,other)).json() as any).results[0])
    .toMatchObject({outcome:'rejected',error:'artwork_not_found',contribution:null});
  const stale=await call('/v1/profile/vinyl-claims','POST',{...body,claims:[{...item,revision:2}]},token);
  expect((await stale.json() as any).results[0].error).toBe('claim_revision_changed');
  expect((await call('/v1/profile/vinyl-claims','POST',{...body,claims:[item,item]},token)).status).toBe(400);
  const claimResponse=await call('/v1/profile/vinyl-claims','POST',body,token);
  expect(claimResponse.status,await claimResponse.clone().text()).toBe(200);
  expect((await claimResponse.json() as any).results[0]).toMatchObject({outcome:'accepted',error:null,contribution:{state:'credited'}});
  expect((await (await call('/v1/profile/vinyl-claims','POST',body,token)).json() as any).results[0].outcome).toBe('unchanged');
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  expect((await call('/v1/admin/moderate','POST',{...item,action:'credit_revoke',note:'Synthetic review'},'',runtime,true)).status).toBe(200);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0});
  expect((await (await call('/v1/profile/vinyl-claims','POST',body,token)).json() as any).results[0].error).toBe('credit_revoked');
  expect((await call('/v1/admin/moderate','POST',{...item,action:'credit_approve',note:'Cannot override revoke'},'',runtime,true)).status).toBe(409);
  expect((await call('/v1/admin/moderate','POST',{...item,action:'credit_restore',note:'Audited restoration'},'',runtime,true)).status).toBe(200);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  await call('/v1/admin/moderate','POST',{artwork_id:art.id,action:'classify_toolmade',note:'Staff correction'},'',runtime,true);
  expect((await (await call('/v1/profile/vinyl-claims','POST',body,token)).json() as any).results[0].error).toBe('handmade_required');
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0});
});

it('credits persist on owner deletion/revision/restore, without another grant',async()=>{
  const token=await account();
  const created=await call('/v1/artworks','POST',upload(1),token);
  const id=(await created.json() as any).artwork.id;
  const revised=await call(`/v1/artworks/${id}/revisions`,'POST',upload(2,{authorship:'permission',change_note:'New revision'}),token);
  expect(revised.status,await revised.clone().text()).toBe(201);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  expect((await call(`/v1/artworks/${id}`,'DELETE',undefined,token)).status).toBe(200);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  const restored=await call('/v1/artworks','POST',upload(2),token);
  expect(restored.status,await restored.clone().text()).toBe(201);
  expect((await restored.json() as any)).toMatchObject({restored:true,artwork:{id}});
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
});

it('historical index resumes, detects collisions, preserves files and permission, and cannot finalize incomplete evidence',async()=>{
  const token=await account();
  for(let i=0;i<3;i++) {
    const shapes=i<2?[native(),{...native(),data:[i,0,1,1,0,0,0],color:[0,0,0,0]}]:[native()];
    const result=await call('/v1/artworks','POST',upload(i,{design:{shapes},authorship:'permission'}),token);
    expect(result.status,await result.clone().text()).toBe(201);
  }
  const objects=(await env.ASSETS.list()).objects.map(x=>[x.key,x.etag]);
  await env.DB.batch([
    env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint=NULL,credit_fingerprint_status='unknown',credit_authorship='unknown'"),
    env.DB.prepare('DELETE FROM vinyl_fingerprints'),env.DB.prepare('DELETE FROM service_settings'),
  ]);
  await expect(finalizeVerifiedIndex(runtime)).rejects.toMatchObject({code:'verified_index_incomplete'});
  expect(await indexHistoricalVinyls(runtime,1)).toMatchObject({indexed:1,unknown:2,ready:false});
  expect(await indexHistoricalVinyls(runtime,4)).toMatchObject({indexed:2,unknown:0,ready:false});
  expect(await finalizeVerifiedIndex(runtime)).toMatchObject({unknown:0,ready:true});
  expect(await indexHistoricalVinyls(runtime,4)).toMatchObject({indexed:0,ready:true});
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM vinyl_contributions').first<any>()).n).toBe(0);
  expect(await env.DB.prepare('SELECT historical_collision FROM vinyl_fingerprints').first()).toEqual({historical_collision:1});
  const claims=await call('/v1/artworks?view=gallery&scope=mine&contribution_view=claims','GET',undefined,token);
  expect(claims.status).toBe(200);
  expect((await claims.json() as any).items.every((x:any)=>x.contribution.state==='duplicate')).toBe(true);
  expect((await env.ASSETS.list()).objects.map(x=>[x.key,x.etag])).toEqual(objects);
});

it('storage outage leaves historical indexing retryable; missing or corrupt bytes never become qualified',async()=>{
  const token=await account();
  const result=await call('/v1/artworks','POST',upload(1,{authorship:'permission'}),token);
  expect(result.status).toBe(201);
  const row=await env.DB.prepare('SELECT design_key FROM artwork_revisions').first<any>();
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown',credit_fingerprint=NULL").run();
  await expect(indexHistoricalVinyls({...runtime,ASSETS:new Proxy(env.ASSETS,{get(target,key){
    if(key==='get') return ()=>Promise.reject(new Error('synthetic offline'));
    const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
  }})})).rejects.toMatchObject({code:'verified_index_storage_unavailable'});
  expect((await env.DB.prepare('SELECT credit_fingerprint_status s FROM artwork_revisions').first<any>()).s).toBe('unknown');
  await env.ASSETS.put(row.design_key,'not the original bytes');
  expect(await indexHistoricalVinyls(runtime)).toMatchObject({indexed:1,review_required:1});
  expect((await env.DB.prepare('SELECT credit_fingerprint_status s FROM artwork_revisions').first<any>()).s).toBe('review_required');
});

it('Verified discovery/profile totals agree while full media and social routes enforce capability/header',async()=>{
  const token=await account(),other=await account('other');
  for(let i=0;i<10;i++) expect((await call('/v1/artworks','POST',upload(i),token)).status).toBe(201);
  const result=await call('/v1/artworks','POST',upload(30,{audience:'verified'}),token);
  expect(result.status,await result.clone().text()).toBe(201);
  const id=(await result.json() as any).artwork.id;
  const cfg=await call('/v1/config');expect((await cfg.json() as any).scopes).toContain('verified');
  for(const scope of ['verified','supporters']) {
    const listing=await call(`/v1/artworks?view=gallery&scope=${scope}`);
    expect(listing.status).toBe(200);expect((await listing.json() as any).items.map((x:any)=>x.id)).toEqual([id]);
  }
  for(const viewer of ['',other,token]) {
    const profile=await call('/v1/creators/owner','GET',undefined,viewer);
    expect((await profile.json() as any).creator.artwork_count).toBe(11);
    expect((await call(`/v1/artworks/${id}/thumbnail`,'GET',undefined,viewer)).status).toBe(200);
  }
  for(const asset of ['preview','download']) {
    expect((await call(`/v1/artworks/${id}/${asset}`)).status).toBe(401);
    expect((await call(`/v1/artworks/${id}/${asset}`,'GET',undefined,other)).status).toBe(403);
    expect((await call(`/v1/artworks/${id}/${asset}`,'GET',undefined,token)).status).toBe(200);
    const old=await worker.fetch(new Request(`https://community.test/v1/artworks/${id}/${asset}`,{headers:{Authorization:`Bearer ${token}`}}),runtime,createExecutionContext());
    expect(old.status).toBe(426);
  }
  for(const [route,body] of [['favorite',{favorite:true}],['vote',{vote:1}],['report',{reason:'other',details:'Synthetic'}]] as const) {
    expect((await call(`/v1/artworks/${id}/${route}`,'POST',body,other)).status).toBe(403);
    const allowed=await call(`/v1/artworks/${id}/${route}`,'POST',body,token);
    expect([200,201],await allowed.clone().text()).toContain(allowed.status);
  }
  expect((await call(`/v1/artworks/${id}/download`,'GET',undefined,token,{...runtime,COMMUNITY_ACCESS_POLICY:'legacy'})).status).toBe(404);
  expect(await count(token)).toMatchObject({active:true,eligible_vinyl_count:11});
});

it('the real client no-view Verified catalogue discovers metadata without a paid key and keeps downloads gated',async()=>{
  const creator=await account(),viewer=await account('viewer');
  for(let i=0;i<10;i++) expect((await call('/v1/artworks','POST',upload(i),creator)).status).toBe(201);
  const created=await call('/v1/artworks','POST',upload(30,{audience:'verified'}),creator);
  expect(created.status,await created.clone().text()).toBe(201);
  const id=(await created.json() as any).artwork.id;
  const path='/v1/artworks?category=All&game=All&sort=trending&scope=verified&page=1&limit=24';
  async function listing(token:string,canDownload:boolean) {
    const response=await call(path,'GET',undefined,token);
    expect(response.status,await response.clone().text()).toBe(200);
    const body=await response.json() as any;
    expect(body).toMatchObject({scope:'verified',sort:'trending',total:1,page:1,page_size:24});
    expect(body.items.map((item:any)=>item.id)).toEqual([id]);
    expect(body.items[0].access).toMatchObject({audience:'verified',can_download:canDownload});
    expect((await call(`/v1/artworks/${id}/thumbnail`,'GET',undefined,token)).status).toBe(200);
  }
  await listing('',false);
  await listing(viewer,false);
  expect(await count(viewer)).toMatchObject({active:false,eligible_vinyl_count:0});
  const blocked=await call(`/v1/artworks/${id}/download`,'GET',undefined,viewer);
  expect(blocked.status).toBe(403);
  expect(await blocked.json()).toMatchObject({error:'verified_required'});

  for(let i=100;i<110;i++) expect((await call('/v1/artworks','POST',upload(i),viewer)).status).toBe(201);
  const session=await call('/v1/session','GET',undefined,viewer);
  expect(await session.json()).toMatchObject({supporter:{active:false},
    capabilities:{verified:{active:true,eligible_vinyl_count:10}}});
  await listing(viewer,true);
  expect((await call(`/v1/artworks/${id}/download`,'GET',undefined,viewer)).status).toBe(200);
  expect((await call(path,'GET',undefined,viewer,{...runtime,COMMUNITY_ACCESS_POLICY:'legacy'})).status).toBe(409);
});

it('scheduled publication earns only after start; terminal expiry settles once and never reveals deleted media',async()=>{
  const token=await account();
  const start=new Date(Date.now()+3600000).toISOString(),end=new Date(Date.now()+7200000).toISOString();
  const future=await call('/v1/artworks','POST',upload(1,{starts_at:start,ends_at:end}),token);
  expect(future.status).toBe(201);
  const id=(await future.json() as any).artwork.id;
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0});
  expect((await call(`/v1/artworks/${id}/thumbnail`)).status).toBe(404);
  expect((await call(`/v1/artworks/${id}`,'DELETE',undefined,token)).status).toBe(200);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0});
  const due=await call('/v1/artworks','POST',upload(2,{starts_at:start,ends_at:end}),token);
  const dueId=(await due.json() as any).artwork.id;
  // Fixture advances the recorded committed interval, not the client clock.
  await env.DB.prepare(`UPDATE vinyl_publications SET committed_at='2020-01-01T00:00:00.000Z',
    starts_at='2020-01-01T01:00:00.000Z',ends_at='2020-01-01T02:00:00.000Z' WHERE artwork_id=?1`).bind(dueId).run();
  await env.DB.prepare("UPDATE artworks SET ends_at='2020-01-01T02:00:00.000Z' WHERE id=?1").bind(dueId).run();
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  expect(await purgeExpiredArtwork(runtime)).toMatchObject({purged:1,failed:0});
  expect(await purgeExpiredArtwork(runtime)).toMatchObject({purged:0,failed:0});
  expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  expect((await call(`/v1/artworks/${dueId}/thumbnail`,'GET',undefined,token)).status).toBe(404);
  const own=await call('/v1/artworks?view=gallery&scope=mine&contribution_view=claims','GET',undefined,token);
  const item=(await own.json() as any).items.find((x:any)=>x.id===dueId);
  expect(item.contribution.state).toBe('credited');expect(item.access.can_download).toBe(false);
  expect(item.preview_url).toBe('');expect(item.thumbnail_url).toBe('');
  expect((await env.DB.prepare("SELECT COUNT(*) n FROM moderation_events WHERE artwork_id=?1 AND action='credit_issued'").bind(dueId).first<any>()).n).toBe(1);
});

it('restricted livery photo/package routes require Verified, but its game thumbnail is public and no livery earns credit',async()=>{
  const token=await account(),other=await account('other');
  for(let i=0;i<10;i++) expect((await call('/v1/artworks','POST',upload(i),token)).status).toBe(201);
  const files={'source/fh6/C_livery':strToU8('synthetic'),'livery/layers.json':strToU8('{}'),
    'mesh/vehicle.json':strToU8('{}'),'projection/index.json':strToU8('{}')};
  const manifest={format:'kfps_full_livery_package_v1',format_version:1,compiler_revision:11,
    source:{game:'fh6',owned:true},sharing:{exportable:true,contains_foreign_vinyl_groups:false},
    livery:{target_car_id:100,decoded_layer_count:42},
    files:await Promise.all(Object.entries(files).map(async([path,data])=>({path,size:data.length,sha256:await sha256Hex(data)})))};
  const archive=zipSync({...files,'manifest.json':strToU8(JSON.stringify(manifest))},{mtime:new Date('2026-01-01')});
  const metadata=upload(50,{audience:'verified'}) as any;delete metadata.authorship;
  const form=new FormData();form.set('metadata',JSON.stringify({...metadata,photo_count:1}));
  form.set('package',new File([archive],'synthetic.kfpslivery'));
  const image=Uint8Array.from(atob(png(50)),c=>c.charCodeAt(0));
  for(const name of ['photo0','preview','thumbnail']) form.set(name,new File([image],name+'.png'));
  const result=await worker.fetch(new Request('https://community.test/v1/liveries',{method:'POST',
    headers:{Authorization:`Bearer ${token}`,'X-Community-Access-Contract':'1'},body:form}),runtime,createExecutionContext());
  expect(result.status,await result.clone().text()).toBe(201);
  const id=(await result.json() as any).artwork.id;
  expect(await count(token)).toMatchObject({eligible_vinyl_count:10});
  expect((await call(`/v1/artworks/${id}/thumbnail`)).status).toBe(200);
  for(const part of ['preview','photos/0','download']) {
    expect((await call(`/v1/artworks/${id}/${part}`,'GET',undefined,other)).status).toBe(403);
    expect((await call(`/v1/artworks/${id}/${part}`,'GET',undefined,token)).status).toBe(200);
  }
  const row=await env.DB.prepare('SELECT current_revision,content_hash FROM artworks WHERE id=?1').bind(id).first<any>();
  const resultClaim=await call('/v1/profile/vinyl-claims','POST',{assertion:'own_original_vinyl_v1',
    claims:[{artwork_id:id,revision:row.current_revision,content_sha256:row.content_hash}]},token);
  expect((await resultClaim.json() as any).results[0].error).toBe('vinyl_required');
});

it('records actual synthetic worker exchanges for the Python client contract gate',async()=>{
  const entries:any[]=[];
  async function record(name:string,path:string,method='GET',body?:unknown,token='',bindings:Env=runtime) {
    const response=await call(path,method,body,token,bindings);
    const text=await response.clone().text();let json:unknown;
    try{json=JSON.parse(text);}catch{throw new Error('Fixture recorder expects JSON responses');}
    entries.push({name,request:{method,path,headers:{'Content-Type':'application/json','X-Community-Access-Contract':'1'},
      authenticated:Boolean(token),...(body===undefined?{}:{json:body})},response:{status:response.status,
      headers:Object.fromEntries([...response.headers].filter(([key])=>['content-type','cache-control','x-community-access-policy'].includes(key))),json}});
    return {status:response.status,json:json as any};
  }
  const token=await account(),other=await account('other');
  await record('config','/v1/config');
  await record('session_zero','/v1/session','GET',undefined,token);
  const handmade=await record('upload_handmade','/v1/artworks','POST',upload(1),token);
  expect(handmade.status).toBe(201);const id=handmade.json.artwork.id;
  await record('upload_toolmade','/v1/artworks','POST',upload(2,{classification:'toolmade'}),token);
  const permission=await record('upload_permission','/v1/artworks','POST',upload(3,{authorship:'permission'}),token);
  const item=permission.json.artwork;
  await record('owner_claim_list','/v1/artworks?view=gallery&scope=mine&contribution_view=claims','GET',undefined,token);
  const row=await env.DB.prepare('SELECT current_revision,content_hash FROM artworks WHERE id=?1').bind(item.id).first<any>();
  await record('claim_own','/v1/profile/vinyl-claims','POST',{assertion:'own_original_vinyl_v1',
    claims:[{artwork_id:item.id,revision:row.current_revision,content_sha256:row.content_hash}]},token);
  for(let i=10;i<18;i++) expect((await call('/v1/artworks','POST',upload(i),token)).status).toBe(201);
  await env.DB.prepare('UPDATE users SET created_at=?1 WHERE id=?2').bind(new Date().toISOString(),'owner').run();
  const waiting=await record('session_waiting_14_days','/v1/session','GET',undefined,token);
  expect(waiting.json.capabilities.verified).toMatchObject({eligible_vinyl_count:10,active:false,reason:'waiting_period'});
  await env.DB.prepare("UPDATE users SET created_at='2020-01-01T00:00:00.000Z' WHERE id='owner'").run();
  await record('session_eligible','/v1/session','GET',undefined,token);
  const protectedArt=await record('upload_verified','/v1/artworks','POST',upload(40,{audience:'verified'}),token);
  const protectedId=protectedArt.json.artwork.id;
  const locked=await record('download_locked',`/v1/artworks/${protectedId}/download`,'GET',undefined,other);
  expect(locked.status).toBe(403);
  const allowed=await record('download_verified',`/v1/artworks/${protectedId}/download`,'GET',undefined,token);
  expect(allowed.status).toBe(200);
  await record('revision_permission',`/v1/artworks/${id}/revisions`,'POST',upload(50,{authorship:'permission',change_note:'Synthetic'}),token);
  await env.DB.prepare("UPDATE artworks SET ends_at='2020-01-01T00:00:00.000Z' WHERE id=?1").bind(protectedId).run();
  expect((await record('download_expired',`/v1/artworks/${protectedId}/download`,'GET',undefined,token)).status).toBe(404);
  await record('session_legacy','/v1/session','GET',undefined,token,{...runtime,COMMUNITY_ACCESS_POLICY:'legacy'});
  const fixture=issuerFixture;
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(fixture.now*1000);
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,username,username_norm,created_at,updated_at)
    VALUES(?1,'github','synthetic-issuer','holder','FixtureHolder','fixtureholder',?2,?2)`)
    .bind(fixture.subject,new Date().toISOString()).run();
  const holder=await createSession(env,fixture.subject);
  const n=Uint8Array.from(atob(fixture.publicKey.n.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
  const proof=JSON.parse(atob(fixture.legacy_verified_grant.payload.replace(/-/g,'+').replace(/_/g,'/')));
  const settings={...runtime,SUPPORTER_ENTITLEMENT_KEY_ID:fixture.entitlement.kid,
    SUPPORTER_ENTITLEMENT_MODULUS_HEX:Array.from(n,x=>x.toString(16).padStart(2,'0')).join(''),
    COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF:proof.eligibility_cutoff};
  const grant=await record('grandfather_verified','/v1/supporter/verify','POST',{
    entitlement:fixture.entitlement,legacy_verified_grant:fixture.legacy_verified_grant},holder,settings);
  expect(grant.status).toBe(200);expect(grant.json.capabilities.verified.reason).toBe('grandfathered_supporter');
  await record('grandfather_after_clear','/v1/supporter/verify','DELETE',undefined,holder,settings);
  const session=await record('session_grandfathered','/v1/session','GET',undefined,holder,settings);
  expect(session.json).toMatchObject({supporter:{active:false},capabilities:{verified:{active:true,eligible_vinyl_count:0}}});
  console.log('KFPS_CLIENT_FIXTURE '+JSON.stringify({format:'kfps.community.actual-worker-exchanges.v1',
    contract_sha256:'0264de524a9273131ad71222214cb8b36dda680cb8bc808a04d06c847da5d7ee',
    producer:'test/verified_routes.spec.ts actual worker.fetch with synthetic local D1/R2',
    limitations:'Recorded transport replay is not simultaneous Python-to-worker process integration. Tokens and private keys excluded.',entries}));
});

it('concurrent tenth uploads count unique contributions exactly once and proof readiness cannot be bypassed',async()=>{
  const token=await account();
  for(let i=0;i<9;i++) expect((await call('/v1/artworks','POST',upload(i),token)).status).toBe(201);
  const responses=await Promise.all([call('/v1/artworks','POST',upload(20),token),call('/v1/artworks','POST',upload(21),token)]);
  expect(responses.map(r=>r.status)).toEqual([201,201]);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:11,active:true});
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown' WHERE artwork_id=(SELECT id FROM artworks ORDER BY id LIMIT 1)").run();
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0,active:false});
  const blocked=await call('/v1/artworks','POST',upload(25,{audience:'verified'}),token);
  expect(blocked.status).toBe(503);
  expect((await call('/v1/artworks','POST',upload(26),token)).status).toBe(201);
});

it('a historical collision invalidates materialized credit rather than letting first indexing win',async()=>{
  const token=await account();
  const first=await call('/v1/artworks','POST',upload(1,{design:{shapes:[native()]}}),token);
  expect(first.status).toBe(201);
  const second=await call('/v1/artworks','POST',upload(2,{design:{shapes:[native(),{...native(),color:[0,0,0,0]}]}}),token);
  expect(second.status).toBe(201);expect(await count(token)).toMatchObject({eligible_vinyl_count:1});
  const id=(await second.json() as any).artwork.id;
  await env.DB.prepare("UPDATE artwork_revisions SET credit_fingerprint_status='unknown',credit_fingerprint=NULL WHERE artwork_id=?1").bind(id).run();
  await indexHistoricalVinyls(runtime);await finalizeVerifiedIndex(runtime);
  expect(await count(token)).toMatchObject({eligible_vinyl_count:0,active:false});
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM vinyl_contributions WHERE credited_at IS NOT NULL').first<any>()).n).toBe(1);
});

it.each([{audience:['verified']},{audience:['public']},{authorship:['own']},{authorship:['permission']}])
  ('rejects non-string contract fields before upload or asset writes: %j',async extra=>{
    const token=await account();
    const response=await call('/v1/artworks','POST',upload(1,extra),token);
    expect(response.status).toBe(400);
    expect((await env.ASSETS.list()).objects).toHaveLength(0);
    expect((await env.DB.prepare('SELECT COUNT(*) n FROM artworks').first<any>()).n).toBe(0);
  });
