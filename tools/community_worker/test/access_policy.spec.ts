import { createExecutionContext, env } from 'cloudflare:test';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { connectionWindow, getAccessPolicy, verifiedCapability } from '../src/access_policy';
import { createSession } from '../src/security';
import type { SessionUser } from '../src/types';
import worker from '../src/index';

const NOW=Date.parse('2026-10-19T12:00:00.000Z'), WAIT=14*24*60*60*1000;
const user:SessionUser={id:'synthetic',provider:'github',providerId:'123',providerLogin:'example',username:'Example',
  bio:'',websiteUrl:'',avatarUrl:'',suspended:false,supporterEntitlementId:'',supporterVerifiedUntil:'',
  communityConnectedAt:new Date(NOW-WAIT).toISOString()};
const verifiedEnv={...env,COMMUNITY_ACCESS_POLICY:'verified-v1',VERSION_SYNC_ENABLED:'0'};
const policy=getAccessPolicy(verifiedEnv);
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();});
beforeEach(async()=>{
  await env.DB.batch(['moderation_events','verified_legacy_grants','reports','artwork_search','artworks','vinyl_fingerprints',
    'sessions','users','rate_limits','service_settings'].map(t=>env.DB.prepare(`DELETE FROM ${t}`)));
  await env.DB.prepare("INSERT INTO service_settings(key,value,updated_at) VALUES('verified_fingerprints_v1','ready','2026-01-01')").run();
});
function request(path:string,method='GET',body?:unknown,token='') {
  return new Request(`https://community.test${path}`,{method,headers:{'Content-Type':'application/json',
    'X-Community-Access-Contract':'1',...(token?{Authorization:`Bearer ${token}`}:{})},
    body:body===undefined?undefined:JSON.stringify(body)});
}
async function call(path:string,method='GET',body?:unknown,token='') {
  return worker.fetch(request(path,method,body,token),verifiedEnv,createExecutionContext());
}

it.each([0,9,10,11])('requires BOTH exact server age and count (%i)',count=>{
  expect(verifiedCapability(policy,user,count,NOW-1)).toMatchObject({active:false,reason:'waiting_period',eligible_vinyl_count:count});
  expect(verifiedCapability(policy,user,count,NOW).active).toBe(count>=10);
  expect(verifiedCapability(policy,user,count,NOW+1).active).toBe(count>=10);
});
it.each(['','invalid','0000-01-01T00:00:00.000Z','0000-01-01T00:00:00Z','2026-02-30T00:00:00.000Z','2026-10-20T00:00:00.000Z','2026-10-01T00:00:00+00:00'])('fails closed for unproven date %s',date=>{
  const account={...user,communityConnectedAt:date};
  expect(connectionWindow(account,NOW)).toEqual({connected_at:null,eligible_after:null,mature:false});
  expect(verifiedCapability(policy,account,10,NOW)).toMatchObject({active:false,reason:'connection_date_unavailable'});
});
it('keeps legacy truthful, excludes local identities, and gives permanent grants priority without bypassing suspension',()=>{
  expect(verifiedCapability(getAccessPolicy(env),user,20,NOW)).toMatchObject({active:false,reason:'policy_legacy'});
  expect(verifiedCapability(policy,{...user,provider:'local-test'},20,NOW)).toMatchObject({active:false,reason:'unsupported_identity'});
  const grant='2026-10-18T00:00:00.000Z';
  expect(verifiedCapability(policy,{...user,communityConnectedAt:''},0,NOW,grant)).toMatchObject({active:true,reason:'grandfathered_supporter',grandfathered_at:grant});
  expect(verifiedCapability(policy,{...user,suspended:true},0,NOW,grant)).toMatchObject({active:false,reason:'account_suspended',grandfathered_at:grant});
});
it('actual config advertises exact policy, no-store and error negotiation',async()=>{
  const response=await call('/v1/config');
  expect(response.status).toBe(200);
  expect(response.headers.get('X-Community-Access-Policy')).toBe('verified_v1');
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect((await response.json() as any).access_policy).toEqual(policy);
  const missing=await call('/missing');
  expect(missing.status).toBe(404);
  expect(missing.headers.get('X-Community-Access-Policy')).toBe('verified_v1');
  const bad=await worker.fetch(request('/v1/config'),{...env,COMMUNITY_ACCESS_POLICY:'typo'},createExecutionContext());
  expect(bad.status).toBe(503);
  expect(bad.headers.has('X-Community-Access-Policy')).toBe(false);
});
it('first validated GitHub connection creates age; relogin/profile/username preserve it, failed verification creates none',async()=>{
  vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(NOW);
  const remote=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({id:321,login:'FirstName'})));
  const first=await call('/v1/auth/github','POST',{access_token:'synthetic-only'});
  expect(first.status).toBe(200);
  const token=(await first.json() as any).token;
  const row=await env.DB.prepare("SELECT id,created_at FROM users WHERE provider_id='321'").first<any>();
  expect(row.created_at).toBe(new Date(NOW).toISOString());
  expect((await call('/v1/profile/username','POST',{username:'AgeTester',confirm_username:'AgeTester'},token)).status).toBe(200);
  expect((await call('/v1/profile','PATCH',{bio:'synthetic',website_url:''},token)).status).toBe(200);
  vi.setSystemTime(NOW+WAIT);
  remote.mockResolvedValue(new Response(JSON.stringify({id:321,login:'Renamed'})));
  const again=await call('/v1/auth/github','POST',{access_token:'synthetic-only'});
  expect(again.status).toBe(200);
  expect(await env.DB.prepare("SELECT id,created_at FROM users WHERE provider_id='321'").first()).toEqual(row);
  const session=await call('/v1/session','GET',undefined,(await again.json() as any).token);
  expect((await session.json() as any).capabilities.verified).toMatchObject({connected_at:row.created_at,
    eligible_after:new Date(NOW+WAIT).toISOString(),active:false,reason:'contributions_required'});
  remote.mockResolvedValue(new Response('{}',{status:401}));
  expect((await call('/v1/auth/github','POST',{access_token:'bad-synthetic'})).status).toBe(401);
  expect((await env.DB.prepare('SELECT COUNT(*) n FROM users').first<any>()).n).toBe(1);
});
it('honors old stored GitHub age in actual session without rewriting it',async()=>{
  await env.DB.prepare(`INSERT INTO users(id,provider,provider_id,provider_login,username,created_at,updated_at)
    VALUES('old','github','123','old','OldUser','2026-01-01T00:00:00.000Z','2026-10-01')`).run();
  const token=await createSession(env,'old');
  const response=await call('/v1/session','GET',undefined,token);
  expect(response.status).toBe(200);
  expect((await response.json() as any).capabilities.verified).toMatchObject({connected_at:'2026-01-01T00:00:00.000Z',
    eligible_after:'2026-01-15T00:00:00.000Z',reason:'contributions_required'});
  expect((await env.DB.prepare("SELECT created_at FROM users WHERE id='old'").first<any>()).created_at).toBe('2026-01-01T00:00:00.000Z');
});
