import {SCHEMA, FEATURES, normalizeReport} from '/protocol.mjs';
import {ScreenshotPicker} from '/screenshot-picker.mjs';
import {PrivateLogPicker} from '/private-log-picker.mjs';
import {MAX_PACKAGE_BYTES} from '/private-logs.mjs';
import {nativeHandoff} from '/native-handoff.mjs';
import {nativeSignIn} from '/native-signin.mjs';

const $ = id => document.getElementById(id);
const KEY = 'kfps-support-draft-v1';
const fresh = () => ({schema: SCHEMA, id: crypto.randomUUID(), created_at: new Date().toISOString(), source: 'discord-form', feature: 'Other', title: '', description: '', expected: '', technical: {}});
let draft = fresh(), submitted = null, account = null, config = null, sending = false;
const native = window.KFPSNativeReport === true;
const ko = navigator.language.toLowerCase().startsWith('ko');
const tr = (en, kr) => ko ? kr : en;
function showAccount() {
  $('identity').textContent = account?.authenticated ? `Signed in as ${account.name}` : 'Not signed in';
  $('login').hidden = !!account?.authenticated; $('logout').hidden = !account?.authenticated;
  $('send').textContent = account?.authenticated ? 'Send report' : 'Sign in to send';
  screenshots.refresh();
}
const nativeLogin = nativeSignIn({api, origin: location.origin, authenticated: value => {
  account = value; showAccount(); message(tr('Signed in. Review your report before sending.', '로그인되었습니다. 전송 전에 보고서를 확인해 주세요.'));
}, changed: value => {
  $('native-signin').hidden = !value?.id;
  $('login').disabled = !!value?.id || !config?.enabled;
  if (value?.id) {
    $('native-signin-code').textContent = value.code;
    $('native-signin-text').textContent = tr('Authorize in your default browser, then return here. Check that the codes match. Your report stays open and is not sent.', '기본 브라우저에서 코드가 일치하는지 확인하고 승인한 뒤 돌아와 주세요. 보고서 창은 그대로 유지되며 보고서는 전송되지 않습니다.');
  }
  if (value?.error) message(tr('Sign-in has not completed. Use Open browser again, or cancel and retry. Your report is still here.', '로그인이 완료되지 않았습니다. 브라우저를 다시 열거나 취소 후 다시 시도해 주세요. 보고서는 그대로 유지됩니다.'), true);
}});
Object.defineProperty(window, 'KFPSReportSignIn', {value: Object.freeze({request: nativeLogin.request, opened: nativeLogin.opened})});
function signIn() {
  if (!submitted) readDraft();
  if (native) nativeLogin.start();
  else location.assign('/auth/start');
}
const privateLogs=new PrivateLogPicker({onError:text=>message(text,true)});
const screenshots=new ScreenshotPicker({getAccount:()=>account,getSubmitted:()=>submitted,getSending:()=>sending,
  onChange:()=>{$('send').disabled=sending||screenshots.busy||!config?.enabled;},onError:text=>message(text,true),
  onReady:()=>message('Screenshots ready. Review the previews and public-sharing confirmation before sending.')});
function message(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
function store() { try {
  const value = JSON.stringify({draft, submitted, saved_at: Date.now()});
  sessionStorage.setItem(KEY, value);
  if (native) localStorage.setItem(KEY, value);
} catch { message('This browser cannot preserve the draft across sign-in. Keep your saved KFPS report and add it again after signing in.', true); } }
function validateDraft(value) {
  // The same allowlist used by the server also runs before any local report is displayed.
  const normalized = normalizeReport({...value, description: value.description || 'Describe the problem here.'});
  if (!value.description) normalized.description = '';
  if (!value.title) normalized.title = '';
  return normalized;
}
function browserDetails() { return {userAgent: navigator.userAgent, language: navigator.language, screen: `${screen.width} x ${screen.height}`, hardwareConcurrency: navigator.hardwareConcurrency}; }
function technical() {
  const data = structuredClone(draft.technical || {});
  data.browser = browserDetails();
  data.app = {...data.app, version: $('version').value.trim() || data.app?.version || ''};
  if ($('game').value) data.running_games = [{game: $('game').value, store: $('store').value}];
  return data;
}
function refreshTechnical() {
  const data = technical(), games = data.running_games || [];
  const values = [['KFPS', data.app?.version || 'Not supplied'], ['Game', games.map(g => `${g.game} (${g.store === 'microsoft_xbox' ? 'Xbox / Microsoft Store' : g.store})`).join(', ') || 'Not detected'], ['System', data.hardware?.platform || 'Not supplied'], ['GPU', (data.hardware?.gpus || []).map(g => `${g.name}${g.driver_version ? ' / ' + g.driver_version : ''}`).join(', ') || 'Not supplied'], ['Memory', data.hardware?.memory_bytes ? `${(data.hardware.memory_bytes / 1073741824).toFixed(1)} GB` : 'Not supplied']];
  $('facts').replaceChildren(...values.flatMap(([label, value]) => { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = label; dd.textContent = value; return [dt, dd]; }));
  $('technical').textContent = JSON.stringify($('include').checked ? data : {technical_details: 'Not included'}, null, 2);
  privateLogs.refresh(draft,$('include').checked);
}
function populate() {
  $('feature').value = FEATURES.includes(draft.feature) ? draft.feature : 'Other';
  for (const name of ['description','expected','title']) $(name).value = draft[name] || '';
  $('include').checked = draft.include_technical !== false;
  $('version').value = draft.technical?.app?.version || '';
  $('game').value = draft.technical?.running_games?.[0]?.game || '';
  $('store').value = draft.technical?.running_games?.[0]?.store || 'unknown';
  $('source').textContent = draft.source === 'kfps' ? 'Prepared by KFPS' : 'Browser report';
  $('report-id').textContent = `Report ID: ${draft.id}`;
  refreshTechnical();
}
function readDraft() {
  draft = {...draft, feature: $('feature').value, description: $('description').value, expected: $('expected').value, title: $('title').value, technical: technical(), include_technical: $('include').checked};
  store();
}
function receipt(value) {
  if(value.status==='delivered')message('');
  $('report-form').hidden = true; $('receipt').hidden = false;
  $('result-title').textContent = value.status === 'delivered' ? 'Report sent' : 'Report delivery';
  $('result-text').textContent = value.message || 'Delivery status has not been confirmed. Check status before retrying.';
  $('receipt-id').textContent = `Report ID: ${submitted.id}`;
  $('post-link').hidden = !value.public_url;
  if (value.public_url) $('post-link').href = value.public_url;
  $('retry').hidden = value.status !== 'retryable';
  $('retry').disabled = (value.retry_after || 0) > 0;
  if (value.retry_after) message(`Wait ${value.retry_after} seconds, then check status again.`, true);
  $('new-report').hidden = value.status !== 'delivered';
  $('send').disabled = true;
  if(value.status==='delivered'){screenshots.clear();privateLogs.clear();}
  $('retry-screenshots').hidden=!submitted.screenshots?.length || value.status==='delivered';
  if(!$('retry-screenshots').hidden)$('retry-screenshots').append($('screenshots-section'));
  $('retry-private-logs').hidden=!submitted.private_logs||value.status==='delivered';
  if(!$('retry-private-logs').hidden){$('retry-private-logs').append($('private-logs-section'));privateLogs.refresh(submitted);}
  screenshots.refresh();
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, credentials: 'same-origin', signal: options.signal || AbortSignal.timeout(70000)});
  let result;
  try { result = await response.json(); } catch { throw new Error('The service returned an unreadable response. Your draft is still saved.'); }
  if (response.status === 401) {
    account = {authenticated: false};
    $('identity').textContent = 'Sign-in expired'; $('login').hidden = false; $('logout').hidden = true;
    $('send').textContent = 'Sign in to send';
  }
  if (!response.ok && !result.status) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}
async function checkStatus() {
  if (!submitted || !account?.authenticated) return;
  $('check').disabled = true;
  try { receipt(await api(`/api/reports/${submitted.id}`)); }
  catch (error) { message(`${error.message} You can retry the same saved submission; do not create another copy.`, true); $('retry').hidden = false; $('retry').disabled = false; }
  finally { $('check').disabled = false; }
}
async function send() {
  if (sending) return;
  if (!account?.authenticated) { signIn(); return; }
  try {
    if(screenshots.busy||privateLogs.busy)throw Error('Wait for attachments to finish loading.');
    if (!submitted) {
      readDraft();
      const images=screenshots.metadata();
      submitted = normalizeReport({...draft,...(images.length?{screenshots:images,screenshots_public:true}:{})}); store();
    }
    const upload=privateLogs.attach(submitted,screenshots.body(submitted));
    sending = true; $('send').disabled = true; $('retry').disabled = true;
    screenshots.refresh();
    message('Sending reviewed report...');
    receipt(await api('/api/reports', {method: 'POST', ...upload, headers: {...upload.headers, 'X-CSRF-Token': account.csrf}}));
  } catch (error) {
    message(error.message, true);
    if (submitted) receipt({status: 'unknown', message: 'Submission is not confirmed. Check status before retrying the same report.'});
  } finally { sending = false; $('send').disabled = !!submitted || !config?.enabled;screenshots.refresh(); }
}

// Clear the private handoff fragment immediately, before any requests or third-party navigation.
const fragment = location.hash;
const authParams = new URLSearchParams(location.search);
const authResult = authParams.get('auth');
const authDetail = authParams.get('detail') || '';
history.replaceState(null, '', '/');
if (authResult) message((authResult === 'cancelled' ? 'Discord sign-in was cancelled or expired. Your draft is still here.' : authResult === 'unavailable' ? 'Discord sign-in is temporarily unavailable. Your draft is still here.' : 'Discord sign-in could not be completed. Try signing in again; your draft is still here.') + (/^(?:token-request|token-response|token-scope|identity-request|identity-response|session)-[0-9]{1,3}$/.test(authDetail) ? ` Support code: ${authDetail}.` : ''), true);
try {
  let saved = JSON.parse(sessionStorage.getItem(KEY) || (native ? localStorage.getItem(KEY) : '') || 'null');
  if (native && (!Number.isFinite(saved?.saved_at) || saved.saved_at < Date.now() - 86400000)) {
    saved = null; localStorage.removeItem(KEY); sessionStorage.removeItem(KEY);
  }
  if (saved?.draft) draft = validateDraft(saved.draft);
  if (saved?.submitted) submitted = normalizeReport(saved.submitted);
  if (fragment.startsWith('#draft=')) {
    if (fragment.length > 100000) throw new Error('Report is too large.');
    const bytes = Uint8Array.from(atob(fragment.slice(7).replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
    draft = validateDraft(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes))); submitted = null;
    store();
  } else if(fragment.startsWith('#bundle=')) {
    if(fragment.length>1050000)throw Error('Report handoff is too large. Add the saved report bundle instead.');
    const bytes=Uint8Array.from(atob(fragment.slice(8).replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
    draft=validateDraft(await privateLogs.accept(new Blob([bytes])));submitted=null;store();
  }
} catch { message('The saved report could not be read. You can still describe the problem below or add a valid KFPS support report.', true); }
if(!privateLogs.item)await privateLogs.restore(submitted||draft);
populate();
$('report-form').addEventListener('input', () => { if (!submitted) { readDraft(); refreshTechnical(); } });
$('report-form').addEventListener('submit', event => { event.preventDefault(); send(); });
$('login').onclick = signIn;
$('native-reopen').onclick = nativeLogin.reopen;
$('native-cancel').onclick = nativeLogin.cancel;
$('logout').onclick = async () => { try { await api('/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': account.csrf}}); await privateLogs.clear();location.reload(); } catch (e) { message(e.message, true); } };
$('check').onclick = checkStatus;
$('retry').onclick = send;
$('new-report').onclick = async () => { await privateLogs.clear();draft = fresh(); submitted = null; store(); location.reload(); };
async function acceptSavedReport(file,{expectedId=null,automatic=false}={}) {
    if (file.size > MAX_PACKAGE_BYTES) throw new Error('Choose a KFPS support report bundle no larger than 9 MB.');
    const header=new Uint8Array(await file.slice(0,2).arrayBuffer());
    const packaged=header[0]===31&&header[1]===139;
    if(!packaged&&file.size>49152)throw new Error('Choose a KFPS support report smaller than 48 KB, or its compressed log bundle.');
    const restoringSubmitted=submitted&&(!automatic||submitted.id===expectedId);
    const validate=value=>{
      if (value.schema !== SCHEMA) throw new Error('This is not a KFPS support report. Artwork and save files are not accepted.');
      if(expectedId&&value.id!==expectedId)throw Error('The prepared report ID does not match.');
      if(restoringSubmitted&&(!packaged||value.id!==submitted.id||JSON.stringify(value.private_logs)!==JSON.stringify(submitted.private_logs)))throw Error('Choose the original bundle for this submitted report.');
      return validateDraft(value);
    };
    const value = packaged?await privateLogs.accept(file,{validate}):validate(JSON.parse(await file.text()));
    if(automatic&&!restoringSubmitted){submitted=null;$('receipt').hidden=true;$('report-form').hidden=false;}
    $('report-file-status').textContent=automatic
      ? 'Report and logs loaded automatically. / 보고서와 로그가 자동으로 준비되었습니다.'
      : 'Saved report loaded. You do not need to select it again. / 보고서를 불러왔습니다. 다시 선택하지 않아도 됩니다.';
    if(submitted) {
      privateLogs.refresh(submitted);message('Original private logs restored. Retry the same report without changing its contents.');return;
    }
    if(!automatic||draft.id!==value.id){draft=value;screenshots.clear();}
    screenshots.refresh();populate();store();message(automatic?'Report and logs are ready. Review before sending.':'Saved report added. Review the details before sending.');
}
$('choose-report').onclick=()=>{$('report-file').value='';$('report-file').click();};
$('report-file').onchange = async () => {
  try {
    const file=$('report-file').files[0];if(file)await acceptSavedReport(file);
  } catch (error) { message(error.message, true); }
  finally { $('report-file').value = ''; }
};
try {
  config = await api('/api/config'); account = await api('/api/session');
  $('discord').href = config.join_url;
  $('support-invite').href = config.join_url;
  showAccount();
  $('login').disabled = !config.enabled;
  $('send').disabled = !config.enabled;
  $('send').textContent = account.authenticated ? 'Send report' : 'Sign in to send';
  screenshots.refresh();
  if (!config.enabled) message('Reporting is temporarily unavailable. Your draft remains local; nothing has been submitted.', true);
  else if (!$('notice').classList.contains('error')) message('Review your report before sending.');
  if (submitted) { receipt({status: 'unknown'}); await checkStatus(); }
} catch (error) { message(error.message, true); }
Object.defineProperty(window,'KFPSReportTransfer',{value:nativeHandoff({accept:acceptSavedReport,current:id=>{
  const value=submitted||draft;
  if(value.id!==id)return false;
  if(submitted&&$('result-title').textContent==='Report sent')return true;
  return !value.private_logs||(privateLogs.item?.id===id&&privateLogs.item.metadata.sha256===value.private_logs.sha256);
}})});
