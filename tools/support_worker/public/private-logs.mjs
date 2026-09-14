import {fields} from './editor-diagnostics.mjs';

export const LOG_SCHEMA='kfps-private-editor-logs/1';
export const APP_LOG_SCHEMA='kfps-private-app-logs/2';
export const PACKAGE_SCHEMA='kfps-support-package/1';
export const MAX_LOG_BYTES=8*1024*1024;
export const MAX_LOG_RAW_BYTES=24*1024*1024;
export const MAX_PACKAGE_BYTES=9*1024*1024;
const encoder=new TextEncoder();
const names=new Set(['performance.jsonl','performance.1.jsonl','performance.2.jsonl','desktop.log','desktop.log.1','desktop.log.2']);
const workerName=/^(?:app-status|app-session|app-runtime|diagnostic-context|collection-index|updater-worker|updater-legacy|editor-server|report-window|transfer-worker|generator-bridge|generator-worker|upscale-worker|background-worker|livery-worker(?:-stderr)?|livery-viewer(?:-stderr)?)-\d{4}\.log$/;
const discoveryWarnings=new Set(['Log discovery limit reached; some logs were not checked.',
  'Some log entries could not be read or were linked.','Some log folders could not be read or were linked.',
  'Retained log file limit reached; some logs were not included.','Updater diagnostic location unavailable.']);
const validSchema=value=>value===LOG_SCHEMA||value===APP_LOG_SCHEMA;
const validName=(name,schema)=>names.has(name)||schema===APP_LOG_SCHEMA&&workerName.test(name);
const timestamp=v=>typeof v==='string'&&/^\d{4}-\d\d-\d\dT[0-9:.+Z-]{8,30}$/.test(v);
const integer=(v,max)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
const object=v=>v&&typeof v==='object'&&!Array.isArray(v);
const check=(ok,message='Invalid private application log attachment.')=>{if(!ok)throw Error(message);};
const warning=(v,schema)=>{
  if(typeof v!=='string')return false;
  if(schema===APP_LOG_SCHEMA&&discoveryWarnings.has(v))return true;
  const match=v.match(/^([^:]+): (?:could not copy the complete retained log\.|incomplete or unsupported lines omitted \(\d{1,8}\)\.)$/);
  return !!match&&validName(match[1],schema);
};

export function validatePrivateMetadata(value) {
  check(object(value)&&validSchema(value.schema));
  check(typeof value.sha256==='string'&&/^[a-f0-9]{64}$/.test(value.sha256));
  check(integer(value.size,MAX_LOG_BYTES)&&value.size>0&&integer(value.raw_size,MAX_LOG_RAW_BYTES)&&value.raw_size>0);
  const count=value.schema===APP_LOG_SCHEMA?310:6;
  check(integer(value.files,count)&&Array.isArray(value.warnings)&&value.warnings.length<=count+4&&value.warnings.every(v=>warning(v,value.schema)));
  return {schema:value.schema,sha256:value.sha256,size:value.size,raw_size:value.raw_size,files:value.files,warnings:value.warnings};
}

export async function inflate(file,limit=MAX_LOG_RAW_BYTES) {
  let reader;
  try {
    reader=file.stream().pipeThrough(new DecompressionStream('gzip')).getReader();
    const chunks=[];let length=0;
    while(true) {
      const {value,done}=await reader.read();if(done)break;
      length+=value.length;check(length<=limit,'Expanded private logs exceed the safety limit.');chunks.push(value);
    }
    const result=new Uint8Array(length);let offset=0;
    for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length;}
    return result;
  } finally {if(reader)await reader.cancel().catch(()=>{});}
}

function event(value) {
  check(object(value)&&value.schema==='kfps-editor-diagnostics/1');
  check(typeof value.session==='string'&&/^[a-f0-9]{32}$/.test(value.session)&&timestamp(value.utc)&&integer(value.serial,Number.MAX_SAFE_INTEGER));
  const remainder={...value};for(const key of ['schema','session','utc','serial'])delete remainder[key];
  if(value.kind==='sample') {
    check(Object.keys(remainder).every(k=>['kind','page','seq','metrics','state','recovery','events'].includes(k)));
    check(typeof value.page==='string'&&/^[a-f0-9]{32}$/.test(value.page)&&integer(value.seq,Number.MAX_SAFE_INTEGER));
    check(Array.isArray(value.events)&&value.events.length<=48);
    for(const item of [value.metrics,value.state,value.recovery,...value.events]) {
      check(object(item)&&Object.keys(item).length===Object.keys(fields(item)).length);
    }
  } else check(!!fields(remainder).kind&&Object.keys(remainder).length===Object.keys(fields(remainder)).length);
}

export async function describePrivateLogs(file,{redact}={}) {
  check(file&&typeof file.arrayBuffer==='function'&&file.size>0&&file.size<=MAX_LOG_BYTES);
  const bytes=new Uint8Array(await file.arrayBuffer());
  check(bytes[0]===31&&bytes[1]===139,'Choose the compressed KFPS log attachment.');
  const raw=await inflate(new Blob([bytes]));
  const bundle=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
  check(object(bundle)&&Object.keys(bundle).every(k=>['schema','created_at','files','warnings'].includes(k))&&validSchema(bundle.schema)&&timestamp(bundle.created_at));
  const count=bundle.schema===APP_LOG_SCHEMA?310:6;
  check(Array.isArray(bundle.files)&&bundle.files.length<=count&&new Set(bundle.files.map(f=>f.name)).size===bundle.files.length);
  check(Array.isArray(bundle.warnings)&&bundle.warnings.length<=count+4&&bundle.warnings.every(v=>warning(v,bundle.schema)));
  for(const file of bundle.files) {
    check(object(file)&&Object.keys(file).every(k=>['name','modified_utc','source_bytes','omitted_lines','text'].includes(k)));
    check(validName(file.name,bundle.schema)&&timestamp(file.modified_utc)&&integer(file.source_bytes,4*1024*1024)&&integer(file.omitted_lines,10000000)&&typeof file.text==='string');
    for(const line of file.text.split('\n')) {
      if(!line)continue;
      if(file.name.startsWith('performance'))event(JSON.parse(line));
      else check(typeof redact==='function'&&line.length<=60000&&redact(line,60000)===line,'Private logs contain text that has not passed privacy cleanup.');
    }
  }
  const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  return {metadata:validatePrivateMetadata({schema:bundle.schema,sha256,size:bytes.length,raw_size:raw.length,files:bundle.files.length,warnings:bundle.warnings}),bundle};
}

export async function readPackage(file,options) {
  check(file.size>0&&file.size<=MAX_PACKAGE_BYTES,'Choose a KFPS support bundle no larger than 9 MB.');
  const raw=await inflate(file,Math.ceil(MAX_LOG_BYTES*4/3)+100000);
  const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
  check(object(value)&&value.schema===PACKAGE_SCHEMA&&typeof value.logs_base64==='string');
  check(value.logs_base64.length<=Math.ceil(MAX_LOG_BYTES/3)*4&&/^[A-Za-z0-9+/]*={0,2}$/.test(value.logs_base64));
  const bytes=Uint8Array.from(atob(value.logs_base64),c=>c.charCodeAt(0));
  const logs=new Blob([bytes],{type:'application/gzip'});
  const {metadata,bundle}=await describePrivateLogs(logs,options);
  check(JSON.stringify(metadata)===JSON.stringify(validatePrivateMetadata(value.report?.private_logs)),'Private logs do not match this report.');
  return {report:value.report,logs,metadata,bundle};
}

export const logFilename=(id,schema=LOG_SCHEMA)=>`kfps-${schema===APP_LOG_SCHEMA?'app':'editor'}-logs-${id}.json.gz`;
