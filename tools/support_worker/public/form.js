import {SCHEMA, FEATURES, normalizeReport} from '/protocol.mjs';
import {normalizeDraft} from '/draft.mjs';
import {ScreenshotPicker} from '/screenshot-picker.mjs';
import {PrivateLogPicker} from '/private-log-picker.mjs';
import {MAX_PACKAGE_BYTES} from '/private-logs.mjs';
import {nativeHandoff} from '/native-handoff.mjs';
import {nativeSignIn,signInErrorText} from '/native-signin.mjs';
import {applyReportCopy,reportText} from '/report-copy.mjs';
import {t,language,applyLanguage,onLanguageChange,localizedError} from '/report-locale.mjs';

const $ = id => document.getElementById(id);
const KEY = 'kfps-support-draft-v1';
const fresh = () => ({schema: SCHEMA, id: crypto.randomUUID(), created_at: new Date().toISOString(), source: 'discord-form', feature: 'Other', title: '', description: '', expected: '', technical: {}});
let draft = fresh(), submitted = null, account = null, config = null, sending = false;
let savedDraft=false,incoming=null,importing=false,checking=false;
let storageValue=null,storageConflict=false,draftStorageWarning=false;
const storageNotice='This browser cannot preserve the draft across sign-in. Keep your saved KFPS report and add it again after signing in.';
const conflictNotice='Another report window changed the saved draft. Keep this window open and copy your edits before reloading.';
let lastNotice={text:'Checking reporting service...',error:false,args:[]},lastReceipt=null,signInState=null;
const native = window.KFPSNativeReport === true;
const tr = en => t(en);
applyLanguage();
applyReportCopy();
$('report-privacy').lang = language();
$('saved-report-recovery').hidden = native;
function showAccount() {
  $('identity').textContent = account?.authenticated ? t('Signed in as {0}',account.name) : t('Not signed in');
  $('login').hidden = !!account?.authenticated; $('logout').hidden = !account?.authenticated;
  $('send').textContent = t(account?.authenticated ? 'Send report' : 'Sign in to send');
  screenshots.refresh();
}
const nativeLogin = nativeSignIn({api, origin: location.origin, authenticated: value => {
  account = value; showAccount(); message(tr('Signed in. Review your report before sending.', '로그인되었습니다. 전송 전에 보고서를 확인해 주세요.'));
}, changed: value => {signInState=value;renderSignIn(value);}});
function renderSignIn(value) {
  $('native-signin').hidden = !value?.id;
  $('login').disabled = !!value?.id || !!value?.starting || !config?.enabled;
  $('native-reopen').textContent = tr('Open in default browser', '기본 브라우저에서 열기');
  $('native-cancel').textContent = tr('Cancel', '취소');
  $('native-link-label').textContent = tr("Browser didn't open? Copy this link into your browser.", '브라우저가 열리지 않으면 아래 링크를 복사해 브라우저 주소창에 붙여 넣어 주세요.');
  $('native-link').value = value?.id ? value.url : '';
  if (value?.id) {
    $('native-reopen').href = value.url;
    $('native-signin-code').textContent = value.code;
    $('native-signin-text').textContent = tr('Authorize in your default browser, then return here. Check that the codes match. Your report stays open and is not sent.', '기본 브라우저에서 코드가 일치하는지 확인하고 승인한 뒤 돌아와 주세요. 보고서 창은 그대로 유지되며 보고서는 전송되지 않습니다.');
  } else {
    $('native-reopen').removeAttribute('href');
    $('native-signin-code').textContent = '';
  }
  if (value?.error) message(signInErrorText(value), true);
  else if (value?.starting) message('Starting Discord sign-in...');
  else if (value?.id) message('Authorize in your browser, then return to KFPS. Your report has not been sent.');
}
Object.defineProperty(window, 'KFPSReportSignIn', {value: Object.freeze({request: nativeLogin.request, opened: nativeLogin.opened, diagnostics: nativeLogin.diagnostics})});
function signIn() {
  if(storageConflict)return;
  if (!submitted&&!readDraft())return;
  if(storageConflict)return;
  if (native) nativeLogin.start();
  else location.assign('/auth/start');
}
const privateLogs=new PrivateLogPicker({onError:text=>message(text,true)});
const screenshots=new ScreenshotPicker({getAccount:()=>account,getSubmitted:()=>submitted,getSending:()=>sending,
  onChange:()=>updateSendButton(),onError:text=>message(text,true),
  onReady:()=>message('Screenshots ready. Review the previews and public-sharing confirmation before sending.')});
function updateSendButton() {
  const value = submitted || draft;
  const included = submitted ? submitted.include_technical !== false : $('include').checked;
  $('send').disabled = storageConflict || sending || importing || !!incoming || !!submitted || screenshots.busy || privateLogs.busy || !config?.enabled
    || (included && !privateLogs.ready(value));
  $('private-log-state').classList.toggle('error', included && !privateLogs.ready(value));
}
function message(text, error = false,...args) {
  lastNotice={text,error,args};renderNotice();
}
function renderNotice() {
  const {text,error,args}=lastNotice,rendered=t(text,...args);
  $('notice').textContent = error&&rendered?localizedError(rendered):rendered;
  $('notice').classList.toggle('error',error);
}
renderNotice();
function storageMatches() {
  if(storageConflict)throw Error(conflictNotice);
  const actual=(native?localStorage:sessionStorage).getItem(KEY);
  if(actual!==storageValue){storageConflict=true;updateSendButton();throw Error(conflictNotice);}
}
function store(state={draft,submitted,delivered_id:lastReceipt?.status==='delivered'?submitted?.id:null}) { try {
  storageMatches();
  const value=JSON.stringify({...state,saved_at:Date.now()});
  (native?localStorage:sessionStorage).setItem(KEY,value);
  storageValue=value;draftStorageWarning=false;
  // The native shared copy is authoritative. A tab-local mirror is best effort.
  if(native)try{sessionStorage.setItem(KEY,value);}catch{}
  return true;
} catch {draftStorageWarning=true;message(storageConflict?conflictNotice:storageNotice,true);return false;} }
addEventListener('storage',event=>{
  if(native&&event.key===KEY&&event.newValue!==storageValue){storageConflict=true;message(conflictNotice,true);updateSendButton();renderIncoming();}
});
function browserDetails() { return {userAgent: navigator.userAgent, language: language(), screen: `${screen.width} x ${screen.height}`, hardwareConcurrency: navigator.hardwareConcurrency}; }
function technical() {
  const data = structuredClone(draft.technical || {});
  data.browser = browserDetails();
  data.app = {...data.app, version: $('version').value.trim()};
  data.running_games = $('game').value ? [{game: $('game').value, store: $('store').value}] : [];
  return data;
}
function refreshTechnical() {
  const data = technical(), games = data.running_games || [];
  const values = [['KFPS', data.app?.version || 'Not supplied'], ['Game', games.map(g => `${g.game} (${g.store === 'microsoft_xbox' ? 'Xbox / Microsoft Store' : g.store})`).join(', ') || 'Not detected'], ['System', data.hardware?.platform || 'Not supplied'], ['GPU', (data.hardware?.gpus || []).map(g => `${g.name}${g.driver_version ? ' / ' + g.driver_version : ''}`).join(', ') || 'Not supplied'], ['Memory', data.hardware?.memory_bytes ? `${(data.hardware.memory_bytes / 1073741824).toFixed(1)} GB` : 'Not supplied']];
  $('facts').replaceChildren(...values.flatMap(([label, value]) => { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = t(label); dd.textContent = ['Not supplied','Not detected'].includes(value)?t(value):value; return [dt, dd]; }));
  $('technical').textContent = JSON.stringify($('include').checked ? data : {technical_details: 'Not included'}, null, 2);
  privateLogs.refresh(draft,$('include').checked);
  updateSendButton();
}
function populate() {
  $('feature').value = FEATURES.includes(draft.feature) ? draft.feature : 'Other';
  for (const name of ['description','expected','title']) $(name).value = draft[name] || '';
  $('include').checked = draft.include_technical !== false;
  $('version').value = draft.technical?.app?.version || '';
  $('game').value = draft.technical?.running_games?.[0]?.game || '';
  $('store').value = draft.technical?.running_games?.[0]?.store || 'unknown';
  refreshLabels();
  refreshTechnical();
}
function readDraft() {
  if(importing)return false;
  draft = {...draft, feature: $('feature').value, description: $('description').value, expected: $('expected').value, title: $('title').value, technical: technical(), include_technical: $('include').checked};
  savedDraft=true;
  return store();
}
function receipt(value) {
  const details={...value};
  delete details.public_url;
  try {
    const url=new URL(value.public_url);
    if(url.origin==='https://discord.com'&&!url.username&&!url.password&&!url.search&&!url.hash
      &&/^\/channels\/\d{17,20}\/\d{17,20}$/.test(url.pathname))details.public_url=url.href;
  }catch{}
  value=lastReceipt?.status==='delivered'
    ? details.status==='delivered'?{...lastReceipt,...details}:lastReceipt
    : details;
  lastReceipt=value;
  store();
  $('receipt').dataset.status=value.status;
  if(value.status==='delivered'&&!draftStorageWarning)message('');
  $('report-form').hidden = true; $('receipt').hidden = false;
  renderReceipt();
  $('post-link').hidden = !value.public_url;
  if (value.public_url) $('post-link').href = value.public_url;
  $('retry').hidden = value.status !== 'retryable';
  $('retry').disabled = (value.retry_after || 0) > 0;
  if (value.retry_after) message('Wait {0} seconds, then check status again.', true,value.retry_after);
  $('new-report').hidden = value.status !== 'delivered';
  $('send').disabled = true;
  if(value.status==='delivered'){screenshots.clear();privateLogs.clear();}
  $('retry-screenshots').hidden=!submitted.screenshots?.length || value.status==='delivered';
  if(!$('retry-screenshots').hidden)$('retry-screenshots').append($('screenshots-section'));
  $('retry-private-logs').hidden=!submitted.private_logs||value.status==='delivered';
  if(!$('retry-private-logs').hidden){$('retry-private-logs').append($('private-logs-section'));privateLogs.refresh(submitted);}
  screenshots.refresh();
  renderIncoming();
}
function refreshLabels() {
  $('source').textContent=t(draft.source==='kfps'?'Prepared by KFPS':'Browser report');
  $('report-id').textContent=t('Report ID: {0}',draft.id);
}
function renderReceipt() {
  if(!lastReceipt||!submitted)return;
  $('result-title').textContent=t(lastReceipt.status==='delivered'?'Report sent':'Report delivery');
  $('result-text').textContent=t(lastReceipt.message||'Delivery status has not been confirmed. Check status before retrying.');
  $('receipt-id').textContent=t('Report ID: {0}',submitted.id);
}
onLanguageChange(()=>{
  applyReportCopy();$('report-privacy').lang=language();
  const notice=lastNotice;renderSignIn(signInState);lastNotice=notice;renderNotice();
  showAccount();refreshLabels();refreshTechnical();renderReceipt();
  if(submitted&&lastReceipt?.status!=='delivered')privateLogs.refresh(submitted,submitted.include_technical!==false);
  const key=$('report-file-status').dataset.copyKey;if(key)$('report-file-status').textContent=reportText(key);
});
async function api(path, options = {}) {
  const response = await fetch(path, {...options, credentials: 'same-origin', signal: options.signal || AbortSignal.timeout(70000)});
  let result;
  try { result = await response.json(); } catch { throw Object.assign(new Error('The service returned an unreadable response. Your draft is still saved.'),{status:response.status,supportCode:'invalid-response'}); }
  if (response.status === 401) {
    account = {authenticated: false};
    $('identity').textContent = t('Sign-in expired'); $('login').hidden = false; $('logout').hidden = true;
    $('send').textContent = t('Sign in to send');
  }
  if (!response.ok && !result?.status) throw Object.assign(new Error(result?.error || `Request failed (${response.status}).`),{status:response.status});
  return result;
}
async function checkStatus() {
  if (!submitted || !account?.authenticated || sending || checking || importing) return;
  const id=submitted.id;
  checking=true;$('check').disabled = true;
  try { receipt(await api(`/api/reports/${submitted.id}`)); }
  catch (error) {
    if(submitted?.id!==id)return;
    message(`${error.message} You can retry the same saved submission; do not create another copy.`, true);
    $('retry').hidden = lastReceipt?.status==='delivered';$('retry').disabled = false;
  }
  finally { checking=false;$('check').disabled = false;renderIncoming(); }
}
async function send() {
  if (storageConflict || sending || checking || importing || incoming || submitted && lastReceipt?.status==='delivered') return;
  try{storageMatches();}catch{if(storageConflict){message(conflictNotice,true);return;}}
  if (!account?.authenticated) { signIn(); return; }
  try {
    if(screenshots.busy||privateLogs.busy)throw Error('Wait for attachments to finish loading.');
    if (!submitted) {
      if(!readDraft())return;
      const images=screenshots.metadata();
      const candidate = normalizeReport({...draft,...(images.length?{screenshots:images,screenshots_public:true}:{})});
      // Validate attachments before recording an attempted delivery. A missing
      // local archive must not turn an unsent draft into an unknown receipt.
      privateLogs.attach(candidate,screenshots.body(candidate));
      submitted = candidate;
      if(!store()){submitted=null;return;}
    }
    const upload=privateLogs.attach(submitted,screenshots.body(submitted));
    sending = true; $('send').disabled = true; $('retry').disabled = true;
    screenshots.refresh();
    message('Sending reviewed report...');
    receipt(await api('/api/reports', {method: 'POST', ...upload, headers: {...upload.headers, 'X-CSRF-Token': account.csrf}}));
  } catch (error) {
    message(error.message, true);
    if (submitted && sending) receipt({status: 'unknown', message: 'Submission is not confirmed. Check status before retrying the same report.'});
  } finally { sending = false; updateSendButton();screenshots.refresh(); }
}

// Clear the private handoff fragment immediately, before any requests or third-party navigation.
const fragment = location.hash;
const authParams = new URLSearchParams(location.search);
const authResult = authParams.get('auth');
const authDetail = authParams.get('detail') || '';
history.replaceState(null, '', '/');
if (authResult) message((authResult === 'cancelled' ? 'Discord sign-in was cancelled or expired. Your draft is still here.' : authResult === 'unavailable' ? 'Discord sign-in is temporarily unavailable. Your draft is still here.' : 'Discord sign-in could not be completed. Try signing in again; your draft is still here.') + (/^(?:token-request|token-response|token-scope|identity-request|identity-response|session)-[0-9]{1,3}$/.test(authDetail) ? ` Support code: ${authDetail}.` : ''), true);
try {
  storageValue=(native?localStorage:sessionStorage).getItem(KEY);
  let saved = JSON.parse(storageValue || 'null');
  if (native && saved && (!Number.isFinite(saved.saved_at) || saved.saved_at < Date.now() - 86400000)) {
    saved = null; localStorage.removeItem(KEY);storageValue=null;sessionStorage.removeItem(KEY);
  }
  if (saved?.draft) {draft = normalizeDraft(saved.draft);savedDraft=true;}
  if (saved?.submitted) submitted = normalizeReport(saved.submitted);
  if(submitted&&saved?.delivered_id===submitted.id)lastReceipt={status:'delivered',message:'Report sent'};
} catch { message('The saved report could not be read. You can still describe the problem below or add a valid KFPS support report.', true); }
await privateLogs.restore(submitted||draft);
try {
  if (fragment.startsWith('#draft=')) {
    if (fragment.length > 100000) throw new Error('Report is too large.');
    const bytes = Uint8Array.from(atob(fragment.slice(7).replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
    await acceptSavedReport(new Blob([bytes]));
  } else if(fragment.startsWith('#bundle=')) {
    if(fragment.length>1050000)throw Error('Report handoff is too large. Add the saved report bundle instead.');
    const bytes=Uint8Array.from(atob(fragment.slice(8).replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
    await acceptSavedReport(new Blob([bytes]));
  }
} catch { message('The saved report could not be read. You can still describe the problem below or add a valid KFPS support report.', true); }
populate();
if(submitted)receipt(lastReceipt||{status:'unknown'});
$('report-form').addEventListener('input', () => { if (!submitted) { readDraft(); refreshTechnical(); } });
$('report-form').addEventListener('submit', event => { event.preventDefault(); send(); });
$('login').onclick = signIn;
$('native-reopen').onclick = event => { if (!nativeLogin.manual()) event.preventDefault(); };
$('native-link').onclick = () => $('native-link').select();
$('native-cancel').onclick = nativeLogin.cancel;
$('logout').onclick = async () => {
  $('logout').disabled=true;
  try {
    await api('/auth/logout', {method:'POST',headers:{'X-CSRF-Token':account.csrf}});
    await privateLogs.clear();
    const saved=submitted?store():readDraft();
    if(saved){location.reload();return;}
    account={authenticated:false};screenshots.clear();showAccount();refreshTechnical();
    message('Signed out. Your edits could not be saved. Keep this window open and preserve your text before reloading.',true);
  } catch(error){message(error.message,true);}
  finally{$('logout').disabled=false;}
};
$('check').onclick = checkStatus;
$('retry').onclick = send;
$('new-report').onclick = async () => {
  if(incoming||checking||sending||importing||storageConflict)return;
  importing=true;updateSendButton();
  try {await useIncoming({value:fresh(),logs:null,automatic:false});}
  catch(error){message(error.message,true);}
  finally{importing=false;renderIncoming();refreshTechnical();}
};
function renderIncoming() {
  $('incoming-report').hidden=!incoming;
  const locked=!!submitted&&lastReceipt?.status!=='delivered';
  $('incoming-locked').hidden=!locked;
  $('replace-report').disabled=locked||importing||checking||storageConflict;
  $('resume-report').disabled=importing;
}
async function useIncoming(item) {
  const protectedDraft=savedDraft||!!submitted||!!privateLogs.item;
  let canPersist=true;
  try{storageMatches();}catch(error){if(protectedDraft||storageConflict)throw error;canPersist=false;}
  let staged=false;
  if(item.logs&&canPersist)try{await privateLogs.stage(item.logs);staged=true;}
  catch(error){if(protectedDraft)throw error;}
  const persisted=store({draft:item.value,submitted:null,delivered_id:null});
  if(!persisted){
    if(staged)await privateLogs.discard(item.logs);
    if(protectedDraft)return false;
  }
  if(item.logs)await privateLogs.commit(item.logs,{staged:staged&&persisted,persist:persisted});
  else if(persisted)await privateLogs.clear();
  draft=item.value;submitted=null;lastReceipt=null;savedDraft=true;
  $('receipt').hidden=true;$('report-form').hidden=false;
  // Attachment controls may have moved into a receipt during a retry.
  $('report-form').insertBefore($('screenshots-section'),$('report-form').querySelector('footer'));
  document.querySelector('#report-form aside').insertBefore($('private-logs-section'),$('version').closest('details'));
  screenshots.clear();screenshots.refresh();populate();
  showImportStatus(item);
  return true;
}
function showImportStatus(item) {
  const ready=privateLogs.ready(item.value);
  $('report-file-status').dataset.copyKey=ready?(item.automatic?'automaticReady':'savedReady'):'summaryReady';
  $('report-file-status').textContent=reportText($('report-file-status').dataset.copyKey);
  if(draftStorageWarning)message(storageConflict?conflictNotice:storageNotice,true);
  else if(privateLogs.storageWarning)message(reportText('cacheWarning'),true);
  else message(reportText($('report-file-status').dataset.copyKey),!ready);
}
$('resume-report').onclick=()=>{incoming=null;renderIncoming();updateSendButton();};
$('replace-report').onclick=async()=>{
  if(!incoming||importing||checking||storageConflict||submitted&&lastReceipt?.status!=='delivered')return;
  importing=true;renderIncoming();updateSendButton();
  try {if(await useIncoming(incoming))incoming=null;}
  catch(error){message(error.message,true);}
  finally {importing=false;renderIncoming();refreshTechnical();}
};
async function acceptSavedReport(file,{expectedId=null,automatic=false}={}) {
  if(incoming&&expectedId===incoming.value.id)return;
  if(storageConflict)throw Error(conflictNotice);
  if(sending||checking||importing||incoming||screenshots.busy)throw Error('Finish the current report action before opening another report.');
  importing=true;updateSendButton();
  try {
    if (file.size > MAX_PACKAGE_BYTES) throw new Error('Choose a KFPS support report bundle no larger than 9 MB.');
    const header=new Uint8Array(await file.slice(0,2).arrayBuffer());
    const packaged=header[0]===31&&header[1]===139;
    if(!packaged&&file.size>49152)throw new Error('Choose a KFPS support report smaller than 48 KB, or its compressed log bundle.');
    const current=submitted||draft;
    const validate=value=>{
      if (value.schema !== SCHEMA) throw new Error('This is not a KFPS support report. Artwork and save files are not accepted.');
      if(expectedId&&value.id!==expectedId)throw Error('The prepared report ID does not match.');
      if(value.id===current.id&&current.private_logs&&JSON.stringify(value.private_logs)!==JSON.stringify(current.private_logs))throw Error('Choose the original bundle for this submitted report.');
      return normalizeDraft(value);
    };
    // Validate in memory first. Do not replace the single cached archive while
    // the user is still deciding whether to resume the existing report.
    const logs=packaged?await privateLogs.prepare(file,{validate}):null;
    const value=logs?logs.report:validate(JSON.parse(await file.text()));
    const item={value,logs,automatic};
    if(value.id===current.id) {
      let persist=true;
      try{storageMatches();}catch(error){if(storageConflict)throw error;persist=false;}
      if(logs&&(!submitted||submitted.private_logs))await privateLogs.commit(logs,{persist});
      if(submitted){privateLogs.refresh(submitted,submitted.include_technical!==false);message('Original private logs restored. Retry the same report without changing its contents.');}
      else {populate();store();showImportStatus(item);}
      return;
    }
    if(savedDraft||submitted){incoming=item;renderIncoming();return;}
    await useIncoming(item);
  } finally {importing=false;renderIncoming();updateSendButton();}
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
  updateSendButton();
  $('send').textContent = t(account.authenticated ? 'Send report' : 'Sign in to send');
  screenshots.refresh();
  if (!config.enabled) message('Reporting is temporarily unavailable. Your draft remains local; nothing has been submitted.', true);
  else if (!$('notice').classList.contains('error')) message('Review your report before sending.');
  if (submitted) await checkStatus();
} catch (error) { message(error.message, true); }
Object.defineProperty(window,'KFPSReportTransfer',{value:nativeHandoff({accept:acceptSavedReport,waitingUser:id=>incoming?.value.id===id,current:id=>{
  const value=submitted||draft;
  if(value.id!==id)return false;
  if(submitted&&lastReceipt?.status==='delivered')return true;
  return !value.private_logs||(privateLogs.item?.id===id&&privateLogs.item.metadata.sha256===value.private_logs.sha256);
}})});
