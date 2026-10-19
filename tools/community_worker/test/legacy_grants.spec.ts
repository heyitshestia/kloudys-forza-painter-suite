import { createExecutionContext,env } from 'cloudflare:test';
import { beforeEach,expect,it } from 'vitest';
import worker from '../src/index';
import { createSession } from '../src/security';
import { backfillLegacyGrants } from '../src/legacy_grants';
import { verifySupporterEnvelope,verifyLegacyGrantEnvelope } from '../src/supporter';

const cutoff='2026-10-01T00:00:00.000Z';
const settings={...env,COMMUNITY_ACCESS_POLICY:'verified-v1',COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF:cutoff};
const grantType='kfps.community.legacy-verified-grant';
let token:string;
function canonical(value:any):string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value==='object') return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`;
  return JSON.stringify(value);
}
function b64(bytes:Uint8Array) {return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/g,'');}
async function sign(type:string,payload:any) {
  const der=Uint8Array.from(atob(env.TEST_SUPPORTER_PRIVATE_KEY_PEM.replace(/-----(BEGIN|END) PRIVATE KEY-----|\s/g,'')),c=>c.charCodeAt(0));
  const key=await crypto.subtle.importKey('pkcs8',der,{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['sign']);
  const bytes=new TextEncoder().encode(canonical(payload));
  return {type,version:1,kid:env.SUPPORTER_ENTITLEMENT_KEY_ID,payload:b64(bytes),
    signature:b64(new Uint8Array(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',key,bytes)))};
}
async function proofs(overrides:Record<string,unknown>={},subject='holder') {
  const now=Date.now();
  const paired={subject,entitlement_id:crypto.randomUUID(),nonce:b64(crypto.getRandomValues(new Uint8Array(32))),
    issued_at:new Date(now).toISOString(),expires_at:new Date(now+15*60*1000).toISOString()};
  const entitlement=await sign('kfps.supporter.community-entitlement',{
    ...paired,schema:'kfps.community.supporter.v1',audience:'kfps-community-v1'});
  const legacy_verified_grant=await sign(grantType,{...paired,schema:'kfps.community.legacy-verified.v1',
    audience:'kfps-community-verified-v1',license_created_at:'2026-09-01T00:00:00.000Z',eligibility_cutoff:cutoff,...overrides});
  return {entitlement,legacy_verified_grant};
}
async function call(path:string,method='GET',body?:unknown,selectedToken=token,selectedEnv=settings) {
  return worker.fetch(new Request(`https://community.test${path}`,{method,
    headers:{Authorization:`Bearer ${selectedToken}`,'Content-Type':'application/json','X-Community-Access-Contract':'1'},
    body:body===undefined?undefined:JSON.stringify(body)}),selectedEnv,createExecutionContext());
}
beforeEach(async()=>{
  await env.DB.batch(['moderation_events','verified_legacy_grants','reports','artwork_search','artworks','vinyl_fingerprints',
    'sessions','users','rate_limits','service_settings'].map(t=>env.DB.prepare(`DELETE FROM ${t}`)));
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,username,created_at,updated_at)
    VALUES('holder','github','123','holder','Holder',?1,?1)`).bind(new Date().toISOString()).run();
  token=await createSession(env,'holder');
});

it('real paired signatures grant permanently once, survive expiry/unlink/relogin, without faking paid state',async()=>{
  const body=await proofs();
  const response=await call('/v1/supporter/verify','POST',body);
  expect(response.status).toBe(200);
  const data=await response.json() as any;
  expect(data.capabilities.verified).toMatchObject({active:true,reason:'grandfathered_supporter',eligible_vinyl_count:0});
  const granted=data.capabilities.verified.grandfathered_at;
  expect(granted).toMatch(/Z$/);
  expect((await call('/v1/supporter/verify','POST',body)).status).toBe(200);
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM verified_legacy_grants').first<any>()).n).toBe(1);
  expect((await env.DB.prepare("SELECT COUNT(*) n FROM moderation_events WHERE action='verified_legacy_granted'").first<any>()).n).toBe(1);
  await env.DB.prepare("UPDATE users SET supporter_verified_until='2026-01-01T00:00:00.000Z'").run();
  const cleared=await call('/v1/supporter/verify','DELETE');
  expect((await cleared.json() as any)).toMatchObject({supporter:{active:false},capabilities:{verified:{active:true,grandfathered_at:granted}}});
  token=await createSession(env,'holder');
  const session=await call('/v1/session');
  expect((await session.json() as any)).toMatchObject({supporter:{active:false},capabilities:{verified:{active:true,grandfathered_at:granted}}});
});

it.each([
  {subject:'other'}, {entitlement_id:'00000000-0000-4000-8000-000000000001'}, {nonce:'A'.repeat(32)},
  {issued_at:'2026-01-01T00:00:00.000Z'}, {expires_at:'2026-01-01T00:00:00.000Z'},
  {license_created_at:'2026-10-02T00:00:00.000Z'}, {license_created_at:'2026-02-30T00:00:00.000Z'},
  {license_created_at:'0000-01-01T00:00:00.000Z'},
  {eligibility_cutoff:'2026-09-30T00:00:00.000Z'}, {audience:'wrong'}, {unexpected:true},
])('rejects correctly signed but mismatched/ineligible optional proof %j before any write',async override=>{
  const response=await call('/v1/supporter/verify','POST',await proofs(override));
  expect(response.status).toBe(400);
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM verified_legacy_grants').first<any>()).n).toBe(0);
  expect((await env.DB.prepare("SELECT supporter_entitlement_id FROM users WHERE id='holder'").first<any>()).supporter_entitlement_id).toBeNull();
});

it('rejects a signed cutoff after proof issuance even when redemption is later than both',async()=>{
  const now=Date.now(),cut=new Date(now-30000).toISOString();
  const paired={subject:'holder',entitlement_id:crypto.randomUUID(),nonce:b64(new Uint8Array(32).fill(1)),
    issued_at:new Date(now-60000).toISOString(),expires_at:new Date(now+60000).toISOString()};
  const entitlement=await sign('kfps.supporter.community-entitlement',{
    ...paired,schema:'kfps.community.supporter.v1',audience:'kfps-community-v1'});
  const proof=await sign(grantType,{...paired,schema:'kfps.community.legacy-verified.v1',
    audience:'kfps-community-verified-v1',license_created_at:'2020-01-01T00:00:00.000Z',eligibility_cutoff:cut});
  const verified=await verifySupporterEnvelope(settings,entitlement,'holder',now);
  await expect(verifyLegacyGrantEnvelope({...settings,COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF:cut},proof,'holder',verified,now))
    .rejects.toMatchObject({code:'invalid_legacy_verified_grant'});
});

it('v1 proof alone remains accepted but cannot award permanent access',async()=>{
  const {entitlement}=await proofs();
  expect((await call('/v1/supporter/verify','POST',{entitlement})).status).toBe(200);
  expect((await (await call('/v1/session')).json() as any)).toMatchObject({supporter:{active:true},
    capabilities:{verified:{active:false,grandfathered_at:null}}});
});
it('forged signature, absent/future cutoff and local identity fail closed',async()=>{
  const body=await proofs();
  const bad=structuredClone(body);bad.legacy_verified_grant.signature='A'.repeat(512);
  expect((await call('/v1/supporter/verify','POST',bad)).status).toBe(400);
  for (const value of [undefined,'bad','2999-01-01T00:00:00.000Z']) {
    expect((await call('/v1/supporter/verify','POST',body,token,{...settings,COMMUNITY_VERIFIED_LEGACY_KEY_CUTOFF:value} as any)).status).toBe(503);
  }
  await env.DB.prepare("UPDATE users SET provider='local-test' WHERE id='holder'").run();
  expect((await call('/v1/supporter/verify','POST',body)).status).toBe(403);
});
it('rollback disables effective Verified but preserves grant; suspension cannot bypass it',async()=>{
  expect((await call('/v1/supporter/verify','POST',await proofs())).status).toBe(200);
  const legacy=await call('/v1/session','GET',undefined,token,{...settings,COMMUNITY_ACCESS_POLICY:'legacy'});
  const cap=(await legacy.json() as any).capabilities.verified;
  expect(cap).toMatchObject({active:false,reason:'policy_legacy'});expect(cap.grandfathered_at).toMatch(/Z$/);
  await env.DB.prepare("UPDATE users SET suspended_at='2026-01-01' WHERE id='holder'").run();
  expect((await call('/v1/supporter/verify','POST',await proofs())).status).toBe(403);
});
it('backfills only proven active-at-cutoff GitHub rows idempotently, not post-cutoff/new purchases',async()=>{
  await env.DB.prepare(`UPDATE users SET supporter_entitlement_id=?1,supporter_verified_at='2026-09-30T23:55:00.000Z',
    supporter_verified_until='2026-10-01T00:10:00.000Z' WHERE id='holder'`).bind(crypto.randomUUID()).run();
  expect(await backfillLegacyGrants(settings)).toBe(1);
  expect(await backfillLegacyGrants(settings)).toBe(0);
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,created_at,updated_at,
    supporter_entitlement_id,supporter_verified_at,supporter_verified_until)
    VALUES('new','github','456','new','2026-01-01','2026-01-01',?1,'2026-10-01T00:01:00.000Z','2026-10-01T00:16:00.000Z')`).bind(crypto.randomUUID()).run();
  expect(await backfillLegacyGrants(settings)).toBe(0);
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM verified_legacy_grants').first<any>()).n).toBe(1);
});
