import test from 'node:test';
import assert from 'node:assert/strict';
import {describeScreenshot,validateScreenshotMetadata,screenshotInfo,MAX_SCREENSHOT_BYTES} from '../public/screenshots.mjs';
import {normalizeReport,publicSummary} from '../public/protocol.mjs';
import {readSubmission,submissionBody} from '../src/submission.mjs';

const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aipkAAAAASUVORK5CYII=','base64');
const image=()=>new Blob([png],{type:'image/png'});
const draft=()=>({schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Editor',description:'Screenshot transport test',technical:{logs:[{source:'editor',text:'PRIVATE-TEST-LOG'}]}});
async function report() {return normalizeReport({...draft(),screenshots:[await describeScreenshot(image())],screenshots_public:true});}
const request=body=>new Request('https://example.test',{method:'POST',body});

test('PNG content and dimensions are validated independently of filenames',async()=>{
  const metadata=await describeScreenshot(image());assert.equal(metadata.width,1);assert.equal(metadata.height,1);assert.equal(metadata.type,'image/png');assert.match(metadata.sha256,/^[a-f0-9]{64}$/);
  await assert.rejects(describeScreenshot(new Blob([png],{type:'image/jpeg'})));
  for(const text of ['<svg></svg>','<html>not an image</html>','broken'])await assert.rejects(describeScreenshot(new Blob([text],{type:'image/png'})));
  await assert.rejects(describeScreenshot(new Blob([],{type:'image/png'})));
  await assert.rejects(describeScreenshot(new Blob([new Uint8Array(MAX_SCREENSHOT_BYTES+1)],{type:'image/png'})));
  const huge=Buffer.from(png);huge.writeUInt32BE(16385,16);assert.throws(()=>screenshotInfo(huge));
  huge.writeUInt32BE(10000,16);huge.writeUInt32BE(10000,20);assert.throws(()=>screenshotInfo(huge));
});
test('screenshot metadata requires explicit public consent and bounded quantities',async()=>{
  const m=await describeScreenshot(image());
  for(const consent of [false,undefined,'true',1])assert.throws(()=>validateScreenshotMetadata([m],consent));
  assert.throws(()=>validateScreenshotMetadata(Array(4).fill(m),true));
  assert.throws(()=>validateScreenshotMetadata(Array(3).fill({...m,size:MAX_SCREENSHOT_BYTES}),true));
  for(const change of [{size:NaN},{width:-1},{sha256:'x'},{type:'image/svg+xml'}])assert.throws(()=>validateScreenshotMetadata([{...m,...change}],true));
  assert.deepEqual(validateScreenshotMetadata([{...m,filename:'PRIVATE-NAME',path:'PRIVATE'}],true),validateScreenshotMetadata([m],true));
});
test('image-free legacy reports retain byte-stable normalization',()=>{
  const old=normalizeReport(draft());assert.equal('screenshots' in old,false);
  assert.equal(JSON.stringify(normalizeReport({...old,screenshots:[],screenshots_public:false})),JSON.stringify(old));
});
test('multipart screenshot report round trips without retaining original filenames',async()=>{
  const r=await report(),form=submissionBody(r,[image()]);
  const accepted=await readSubmission(request(form));assert.deepEqual(accepted.report,r);
  assert.deepEqual(Buffer.from(await accepted.files[0].arrayBuffer()),png);
  assert.equal(accepted.files[0].name,'screenshot-1.png');
  assert.match(publicSummary(r,{name:'Tester'}),/shared publicly/);
  assert(!publicSummary(r,{name:'Tester'}).includes('PRIVATE-TEST-LOG'));
  assert.deepEqual(normalizeReport({...r,include_technical:false}).technical,{});
  assert.equal(normalizeReport({...r,include_technical:false}).screenshots.length,1);
});
test('omitted, duplicate, extra and changed image uploads fail closed',async()=>{
  const r=await report();
  await assert.rejects(readSubmission(new Request('https://example.test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(r)})));
  for(const mutate of [f=>f.delete('screenshot[0]'),f=>f.append('report','{}'),f=>f.set('unexpected','extra'),f=>f.set('screenshot[0]',new Blob(['bad'],{type:'image/png'}),'x.png')]) {
    const form=submissionBody(r,[image()]);mutate(form);await assert.rejects(readSubmission(request(form)));
  }
  const changed=structuredClone(r);changed.screenshots[0].sha256='a'.repeat(64);
  await assert.rejects(readSubmission(request(submissionBody(changed,[image()]))),/changed/);
});
test('oversized multipart stream is rejected before parsing',async()=>{
  await assert.rejects(readSubmission(new Request('https://example.test',{method:'POST',headers:{'Content-Type':'multipart/form-data; boundary=x','Content-Length':'50000000'},body:'x'})),/too large/);
});
