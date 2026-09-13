import test from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {describePrivateLogs,readPackage,LOG_SCHEMA,APP_LOG_SCHEMA,PACKAGE_SCHEMA,inflate,MAX_LOG_BYTES} from '../public/private-logs.mjs';
import {normalizeReport,redact,publicSummary} from '../public/protocol.mjs';
import {submissionBody,readSubmission} from '../src/submission.mjs';

const event=()=>({schema:'kfps-editor-diagnostics/1',session:'a'.repeat(32),utc:new Date().toISOString(),serial:1,kind:'commit',action:'move',commitId:5,inputId:4});
const make=()=>({schema:LOG_SCHEMA,created_at:new Date().toISOString(),files:[{name:'performance.jsonl',modified_utc:new Date().toISOString(),source_bytes:500,omitted_lines:0,text:JSON.stringify(event())+'\n'}],warnings:[]});
const file=value=>new Blob([gzipSync(JSON.stringify(value))],{type:'application/gzip'});
const request=body=>new Request('https://support.example',{method:'POST',body});
async function fixture(){const value=make(),logs=file(value),{metadata}=await describePrivateLogs(logs,{redact});return {value,logs,report:normalizeReport({schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Editor',description:'Real pipeline test fixture',private_logs:metadata})};}

test('full log attachment round trips separately from public content',async()=>{
  const {logs,report}=await fixture();
  const accepted=await readSubmission(request(submissionBody(report,[],logs)));
  assert.deepEqual(accepted.report,report);assert.deepEqual(Buffer.from(await accepted.privateLogs.arrayBuffer()),Buffer.from(await logs.arrayBuffer()));
  const publicText=publicSummary(report,{name:'Tester'});
  for(const field of ['commitId','private_logs',report.private_logs.sha256,'performance.jsonl'])assert(!publicText.includes(field));
});
test('private consent off removes metadata and rejects attached files',async()=>{
  const {logs,report}=await fixture();const excluded=normalizeReport({...report,include_technical:false});
  assert(!excluded.private_logs);await assert.rejects(readSubmission(request(submissionBody(excluded,[],logs))),/Unexpected/);
  assert(!normalizeReport({schema:report.schema,id:crypto.randomUUID(),feature:'Editor',description:'Legacy report'}).private_logs);
});
test('missing, changed, duplicate or unexpected archives are refused',async()=>{
  const {logs,report}=await fixture();
  await assert.rejects(readSubmission(new Request('https://support.example',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(report)})),/Reattach/);
  for(const mutate of [f=>f.delete('private_logs'),f=>f.append('private_logs',logs),f=>f.set('private_logs',file({...make(),warnings:['bad']})),f=>f.set('extra','bad')]) {
    const f=submissionBody(report,[],logs);mutate(f);await assert.rejects(readSubmission(request(f)));
  }
  await assert.rejects(readSubmission(request(submissionBody({...report,private_logs:{...report.private_logs,sha256:'0'.repeat(64)}},[],logs))),/changed/);
});
test('schema checks exclude artwork, arbitrary files and unsafe text',async()=>{
  for(const mutate of [b=>b.files[0].name='../autosave.json',b=>b.files.push(b.files[0]),b=>b.files[0].text=JSON.stringify({...event(),shapes:[1]}),b=>b.files[0].text=JSON.stringify({...event(),message:'private'}),b=>{b.files[0].name='desktop.log';b.files[0].text='password=PRIVATE';},b=>b.extra='secret']) {
    const value=make();mutate(value);await assert.rejects(describePrivateLogs(file(value),{redact}));
  }
  await assert.rejects(describePrivateLogs(new Blob(['{}']),{redact}));
  await assert.rejects(describePrivateLogs(new Blob([new Uint8Array(MAX_LOG_BYTES+1)]),{redact}));
  await assert.rejects(inflate(new Blob([gzipSync('a'.repeat(10000))]),100),/safety limit/);
});
test('saved package binds exact original logs and report',async()=>{
  const {logs,report}=await fixture();
  const packageValue={schema:PACKAGE_SCHEMA,report,logs_base64:Buffer.from(await logs.arrayBuffer()).toString('base64')};
  const accepted=await readPackage(file(packageValue),{redact});assert.deepEqual(accepted.report,report);
  packageValue.report.private_logs.sha256='b'.repeat(64);await assert.rejects(readPackage(file(packageValue),{redact}),/match/);
});
test('full history stays intact well beyond the old 16-event report window',async()=>{
  const value=make();value.files[0].text=Array.from({length:6000},(_,i)=>JSON.stringify({...event(),serial:i+1,commitId:i+1})).join('\n')+'\n';
  value.files[0].source_bytes=Buffer.byteLength(value.files[0].text);
  const result=await describePrivateLogs(file(value),{redact});assert.equal(result.bundle.files[0].text.split('\n').filter(Boolean).length,6000);
});

test('application archives preserve all worker sources without changing legacy editor metadata',async()=>{
  const value=make();value.schema=APP_LOG_SCHEMA;
  const sources=['transfer-worker','generator-bridge','generator-worker','upscale-worker','background-worker','livery-worker','livery-worker-stderr','livery-viewer'];
  for(const source of sources)value.files.push({name:source+'-0001.log',modified_utc:new Date().toISOString(),source_bytes:40000,omitted_lines:0,text:'Worker record\n'.repeat(3000)});
  value.warnings=['Log discovery limit reached; some logs were not checked.'];
  const logs=file(value),{metadata,bundle}=await describePrivateLogs(logs,{redact});
  assert.equal(metadata.files,9);assert.deepEqual(bundle,value);
  const report=normalizeReport({schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Other',description:'All retained workers',private_logs:metadata});
  const accepted=await readSubmission(request(submissionBody(report,[],logs)));
  assert.deepEqual(accepted.report.private_logs,metadata);
  assert.equal((await describePrivateLogs(file(make()),{redact})).metadata.schema,LOG_SCHEMA);
  value.files[1].name='project-0001.log';await assert.rejects(describePrivateLogs(file(value),{redact}));
});
