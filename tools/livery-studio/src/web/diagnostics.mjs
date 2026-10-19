// Support telemetry only. Never accept project objects, labels, paths or errors.
export const ENUMS = {
  event:['host','readiness','render','counts','action','error','request','closed'],
  host:['backend','native','chrome','unknown'],
  gpu_policy:['auto','opengl','d3d11','browser-default','unknown'],
  action:['launch','import','edit','undo','redo','save','reopen','source_edit','source_return','cancel','car_switch','export','checkpoint','theme','language','component','reset','render','library','recovery','selection'],
  outcome:['start','ok','error','cancelled','stale','busy','requested'],
  error_code:['http_4xx','http_5xx','network','aborted','javascript','preview','context_lost','shader','operation','timeout','unknown'],
};
export const NUMBERS = {
  duration_ms:600000,frame_ms:600000,frame_mean_ms:600000,frame_max_ms:600000,compose_ms:600000,load_ms:600000,
  canvas_width:32768,canvas_height:32768,pixel_ratio:8,source_count:4096,placement_count:65536,section_count:64,
  shape_count:1000000,geometries:1000000,textures:1000000,programs:100000,draw_calls:1000000,
  triangles:1000000000,resource_bytes:16*1024**3,frame_count:2**31-1,http_status:599,
};
const booleans = new Set(['ready','webgl','visible']);
export function sanitizeEvent(value) {
  try {
    if(!value||Object.getPrototypeOf(value)!==Object.prototype)return null;
    const keys=Object.keys(value);if(!keys.includes('event')||keys.length>40)return null;
    const clean={};
    for(const key of keys){
      let item=value[key];
      if(Object.hasOwn(ENUMS,key)){if(typeof item!=='string'||!ENUMS[key].includes(item))return null;}
      else if(Object.hasOwn(NUMBERS,key)){
        if(typeof item!=='number'||!Number.isFinite(item)||item<0||item>NUMBERS[key])return null;
        if(!key.endsWith('_ms')&&key!=='pixel_ratio'&&!Number.isSafeInteger(item))return null;
        item=Math.round(item*100)/100;
      }else if(booleans.has(key)){if(typeof item!=='boolean')return null;}
      else if(key==='app_version'){if(typeof item!=='string'||!/^\d{1,4}(?:\.\d{1,4}){1,3}(?![\s\S])/.test(item))return null;}
      else return null;
      clean[key]=item;
    }
    return JSON.stringify(clean).length<=864?clean:null;
  }catch{return null;}
}

export function projectCounts(project, sectionCount=0) {
  // Read lengths only; do not clone, stringify or traverse individual shapes.
  try {
    const vinyls=Array.isArray(project?.vinyls)?project.vinyls:[];
    return {source_count:vinyls.length,placement_count:project?.placements?.length||0,
      section_count:sectionCount,shape_count:vinyls.reduce((sum,source)=>sum+(source.shapes?.length||0),0)};
  } catch { return {}; }
}

export function createDiagnostics({win=globalThis.window,doc=globalThis.document,fetcher=globalThis.fetch,
  now=()=>performance.now(),setIntervalFn=globalThis.setInterval,clearIntervalFn=globalThis.clearInterval,
  setTimeoutFn=globalThis.setTimeout,clearTimeoutFn=globalThis.clearTimeout}={}) {
  const queue=[];let disposed=false,inflight=false,sampler=null,retryAt=0,tokens=16,refill=now(),lastSample=-Infinity,bootFailure=false;
  const host=win?.__kfpsStudioNativeDownloads===true?'native':'chrome';
  const gpuPolicy=host==='native'&&['auto','opengl','d3d11'].includes(win?.__kfpsStudioDiagnosticPolicy)?win.__kfpsStudioDiagnosticPolicy:host==='native'?'unknown':'browser-default';
  function emit(event,fields={}) {
    try{
      if(disposed)return false;
      const time=now();tokens=Math.min(16,tokens+Math.max(0,time-refill)/1000);refill=time;
      if(tokens<1||queue.length>=32)return false;
      const clean=sanitizeEvent({event,host,...fields});if(!clean)return false;
      tokens--;queue.push(clean);return true;
    }catch{return false;}
  }
  async function flush(keepalive=false) {
    if(inflight||!queue.length||now()<retryAt)return false;
    inflight=true;const batch=[];let bytes=13,timer;
    while(queue.length&&batch.length<16){
      const size=JSON.stringify(queue[0]).length+(batch.length?1:0);
      if(bytes+size>8192)break;
      bytes+=size;batch.push(queue.shift());
    }
    try{
      const controller=new AbortController();timer=setTimeoutFn(()=>controller.abort(),1500);
      const response=await fetcher('./api/diagnostics',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({events:batch}),signal:controller.signal,keepalive,redirect:'error',credentials:'same-origin'});
      if(!response.ok)throw Error();
      return true;
    }catch{retryAt=now()+30000;return false;}
    finally{clearTimeoutFn(timer);inflight=false;}
  }
  function sample(force=false) {
    try{
      if(disposed||!sampler||doc?.visibilityState==='hidden'||!force&&now()-lastSample<15000)return;
      lastSample=now();const value=sampler();if(value)emit('render',value);
    }catch{emit('error',{error_code:'unknown'});}
  }
  function scene(event,fields) {
    if(event==='ready')emit('readiness',{...fields,ready:true});
    else if(event==='error'||event==='context-lost')emit('error',{error_code:event==='context-lost'?'context_lost':'preview',ready:false});
    else if(event==='component-selection')emit('action',{action:'component',outcome:'ok'});
  }
  const tick=setIntervalFn(()=>{
    try{if(!bootFailure&&win?.__liveryLabBootError)bootFailure=emit('readiness',{ready:false,error_code:'javascript'});}catch{}
    sample();void flush();
  },2000);
  const onError=()=>emit('error',{error_code:'javascript'});
  const onHide=()=>{emit('closed');void flush(true);dispose();};
  win?.addEventListener('error',onError);win?.addEventListener('unhandledrejection',onError);win?.addEventListener('pagehide',onHide);
  function dispose(){if(disposed)return;disposed=true;clearIntervalFn(tick);queue.length=0;
    win?.removeEventListener('error',onError);win?.removeEventListener('unhandledrejection',onError);win?.removeEventListener('pagehide',onHide);}
  emit('host',{gpu_policy:gpuPolicy,ready:false});
  return {emit,flush,sample,scene,dispose,setSampler(value){sampler=typeof value==='function'?value:null;},pending:()=>queue.length};
}

const noop={emit:()=>false,flush:async()=>false,sample(){},scene(){},dispose(){},setSampler(){}};
function initialize(){try{return typeof window==='undefined'?noop:createDiagnostics();}catch{return noop;}}
export const studioDiagnostics=initialize();
if(typeof window!=='undefined')window.__kfpsStudioDiagnostics=studioDiagnostics;
