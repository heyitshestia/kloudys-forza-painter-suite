import {validateProject, serializeProject, MAX_PROJECT_BYTES} from './layout-model.mjs';
import {validateGarageBuild} from './garage-build.mjs';

const opaque = /^[a-f0-9]{32}$/;
const packageHash = /^#(?:layout|project)=([a-f0-9]{32})$/;
const sections = ['Front','Back','Top','Left','Right','Spoiler','FrontWindshield','BackWindshield','TopWindow','LeftWindow','RightWindow'];
const sharedMessage = 'Save your work and choose this package\'s car in the existing Studio before opening it. This running Studio may have another open page, so automatic car switching was blocked. Existing documents have not been changed.';
let startupHandoff = null;

export function clearPackageStartupHandoff() {
  if(!startupHandoff)return;
  const {window,clear,timer} = startupHandoff;
  startupHandoff = null;
  clearTimeout(timer);
  window.removeEventListener('hashchange',clear);
  window.removeEventListener('pagehide',clear);
}

function rememberHandoff(value,window,base,hash) {
  clearPackageStartupHandoff();
  const clear = () => clearPackageStartupHandoff();
  const timer = setTimeout(clear,30000);
  timer.unref?.();
  startupHandoff = {value,window,base,hash,clear,timer};
  window.addEventListener('hashchange',clear);
  window.addEventListener('pagehide',clear);
}

export function takePackageStartupHandoff(id,window = globalThis.window,kind='layout') {
  const cached = startupHandoff;
  clearPackageStartupHandoff();
  if(!cached || cached.window !== window || cached.hash !== '#' + kind + '=' + id || window.location.hash !== cached.hash)return null;
  const url = new URL(window.location.href);
  url.hash = '';
  return url.href === cached.base ? cached.value : null;
}

async function requestJSON(base, route, body, timeoutMs) {
  const controller = new AbortController();
  const timeoutError = () => Error('Studio startup request timed out. Reopen Studio from KFPS.');
  let timer;
  const deadline = new Promise((_,reject) => {timer = setTimeout(() => {
    controller.abort();reject(timeoutError());
  },timeoutMs);});
  const read = async () => {
    const response = await fetch(new URL('api/' + route, base), {
      method:body === undefined ? 'GET' : 'POST', cache:'no-store', redirect:'error', signal:controller.signal,
      headers:body === undefined ? {} : {'Content-Type':'application/json'},
      body:body === undefined ? undefined : JSON.stringify(body), keepalive:body !== undefined,
    });
    if(controller.signal.aborted){void response.body?.cancel().catch(() => {});throw timeoutError();}
    const maximum = /^host-(?:layout|project)\//.test(route) ? MAX_PROJECT_BYTES : 1024 * 1024;
    if(response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
      await response.body?.cancel();
      throw Error('The incoming vinyl response is not JSON.');
    }
    const reader = response.body.getReader(), chunks = [];
    let size = 0;
    try {
      while(true) {
        const {done,value} = await reader.read();
        if(controller.signal.aborted)throw timeoutError();
        if(done)break;
        size += value.byteLength;
        if(size > maximum)throw Error('Studio returned oversized readiness metadata.');
        chunks.push(value);
      }
    } finally {
      await reader.cancel();
      reader.releaseLock();
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset += chunk.byteLength;}
    const value = JSON.parse(new TextDecoder().decode(bytes));
    if(!response.ok)throw Error(typeof value?.error === 'string' ? value.error : 'The package car could not be prepared. The current layout is retained.');
    return value;
  };
  try {return await Promise.race([read(),deadline]);}
  catch(error){if(controller.signal.aborted)throw timeoutError();throw error;}
  finally {clearTimeout(timer);}
}

function jobValue(value, expectedId) {
  if(!value || !opaque.test(value.id) || expectedId && value.id !== expectedId
    || !['preparing','ready','cancelling','cancelled','failed','committed'].includes(value.status)) {
    throw Error('The car preparation returned an invalid status. Your layout is retained.');
  }
  return value;
}

function exactCar(value, target) {
  if(!value || !Array.isArray(value.cars) || value.cars.length > 4096)throw Error('The car catalogue contains invalid entries.');
  const ids = new Set();
  for(const car of value.cars) {
    if(!car || !opaque.test(car.id) || ids.has(car.id) || typeof car.model_code !== 'string'
      || !(car.car_id === null || Number.isSafeInteger(car.car_id) && car.car_id >= 0))throw Error('The car catalogue contains invalid entries.');
    ids.add(car.id);
  }
  const matches = value.cars.filter(car => car.car_id === target.car_id && car.model_code === target.model_code);
  if(matches.length !== 1)throw Error(matches.length ? 'The package car is ambiguous in the configured catalogue.' : 'The exact package car is not installed. Nothing was opened.');
  if(matches[0].id === value.current)throw Error('The current car is missing from the catalogue.');
  return matches[0];
}

// This runs only before the editor (and its scene module) has been imported.
// Existing documents continue through the editor's Save/Discard/Cancel path.
export async function preparePackageStartup({window = globalThis.window, request,
  wait = () => new Promise(resolve => setTimeout(resolve,500)), onStatus = () => {}, requestTimeoutMs = 15000} = {}) {
  clearPackageStartupHandoff();
  if(!/^#(?:layout|project)/.test(window.location.hash))return true;
  const base = new URL(window.location.href);
  base.hash = '';
  if(base.protocol !== 'http:' || base.hostname !== '127.0.0.1' || !base.port || base.username || base.password || base.search
    || !/^\/[A-Za-z0-9_-]{43}\/$/.test(base.pathname))throw Error('Invalid local Studio window URL.');
  request ??= (route,body) => requestJSON(base,route,body,requestTimeoutMs);
  let closed = false, job = null, cancellation = null, cancellationRead = false, committing = false;
  const cancel = () => {
    if(!cancellation && job && !committing) {
      onStatus('Cancelling obsolete car preparation...');
      cancellation = request(`car-switch/${job.id}/cancel`,{}).then(value => jobValue(value,job.id));
    }
    return cancellation;
  };
  const pagehide = () => {closed = true;void cancel()?.catch(() => {});};
  window.addEventListener('pagehide',pagehide);
  try {
    while(!closed) {
      const hash = window.location.hash;
      if(!/^#(?:layout|project)/.test(hash))return true;
      const match = packageHash.exec(hash);
      if(!match)throw Error('The incoming artwork link is invalid.');
      const kind=hash.startsWith('#project=')?'project':'layout';
      const current = () => !closed && window.location.hash === hash;
      onStatus(kind==='project'?'Opening Studio project...':'Opening package artwork...');
      const config = await request('editor-config');
      if(!current())continue;
      if(config[`host_${kind}_handoff`] !== true)throw Error('This session cannot receive this artwork. Save your work, then restart Studio.');
      const value = await request('host-' + kind + '/' + match[1]);
      if(!current())continue;
      const incoming=value?.[kind],car=incoming?.vehicle;
      if(!car || !Number.isSafeInteger(car.car_id) || car.car_id <= 0 || typeof car.model_code !== 'string'
        || !car.model_code.trim() || car.model_code.length > 160 || /[\x00-\x1f]/.test(car.model_code))throw Error('The package has no exact car identity.');
      validateProject(incoming,car,sections);
      if(incoming.garage_build!==undefined) {
        validateGarageBuild(incoming.garage_build);
        if(config.host_garage_build!==true)throw Error('This Studio needs a restart before opening Garage builds. Save your work, then restart Studio.');
      }
      serializeProject(incoming);
      if(car.car_id === config.vehicle?.car_id && car.model_code === config.vehicle?.model_code) {
        rememberHandoff(value,window,base.href,hash);
        return true;
      }
      if(window.__kfpsStudioNativeDownloads !== true)throw Error("In Chrome, save your work and choose this package's car in Studio before opening it. Automatic car switching could interrupt another Studio window.");
      if(config.chrome_exposed !== false)throw Error(sharedMessage);
      if(value.startup_session !== base.href)throw Error(sharedMessage);
      if(config.car_switch !== true)throw Error('This session cannot open the package car. Save your work, then restart Studio.');
      if(config.handoff_car_validation !== true)throw Error('Save your work, then restart Studio before opening another car.');
      const catalogue = await request('cars');
      if(!current())continue;
      const selected = exactCar(catalogue,car);
      onStatus('Preparing the package car...');
      cancellation = null;
      cancellationRead = false;
      job = jobValue(await request('car-switch',{carId:selected.id,[kind==='project'?'projectId':'layoutId']:match[1]}));
      while(job) {
        if(!current() && !cancellation)cancel();
        if(cancellation && !cancellationRead){job = await cancellation;cancellationRead = true;}
        if(job.status === 'cancelled'){job = null;break;}
        if(job.status === 'failed')throw Error(job.error || 'The package car could not be prepared. The current layout is retained.');
        if(job.status === 'ready') {
          if(cancellation)throw Error('Cancellation was not confirmed. Retry status or cancel again.');
          committing = true;
          let receipt;
          try {receipt = await request(`car-switch/${job.id}/commit`,{});}
          catch {throw Error('The car switch result could not be confirmed. Reopen Studio from KFPS before retrying.');}
          const result = jobValue(receipt,job.id);
          // A committed receipt rotates the token even if a newer handoff arrived.
          const url = new URL(result.url,base);
          if(result.status !== 'committed' || typeof result.url !== 'string' || url.origin !== base.origin
            || url.username || url.password || url.search || url.hash || !/^\/[A-Za-z0-9_-]{43}\/$/.test(url.pathname)
            || url.pathname === base.pathname)throw Error('The car switch returned an invalid destination. Save your retained layout before reopening the Studio.');
          job = null;
          if(closed)return false;
          if(/^#(?:vinyl|layout|project)=[a-f0-9]{32}$/.test(window.location.hash))url.hash = window.location.hash;
          window.location.assign(url.href);
          return false;
        }
        if(job.status === 'committed')throw Error('This car session has already switched. Save your retained layout, then reopen the Studio from KFPS.');
        if(closed){await cancel();return false;}
        await wait();
        if(!current() && !cancellation)continue;
        job = jobValue(await request(`car-switch/${job.id}`),job.id);
      }
    }
    return false;
  } finally {
    window.removeEventListener('pagehide',pagehide);
    if(job && !committing)await cancel()?.catch(() => {});
  }
}
