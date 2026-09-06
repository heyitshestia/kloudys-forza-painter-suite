import {SCHEMA, FEATURES, normalizeReport} from '/protocol.mjs';

const $ = id => document.getElementById(id);
const KEY = 'kfps-support-draft-v1';
const fresh = () => ({schema: SCHEMA, id: crypto.randomUUID(), created_at: new Date().toISOString(), source: 'discord-form', feature: 'Other', title: '', description: '', expected: '', technical: {}});
let draft = fresh(), submitted = null, account = null, config = null, sending = false;
function message(text, error = false) { $('notice').textContent = text; $('notice').classList.toggle('error', error); }
function store() { try { sessionStorage.setItem(KEY, JSON.stringify({draft, submitted})); } catch { message('This browser cannot preserve the draft across sign-in. Keep your saved KFPS report and add it again after signing in.', true); } }
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
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, credentials: 'same-origin', signal: AbortSignal.timeout(70000)});
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
  if (!account?.authenticated) { readDraft(); location.assign('/auth/start'); return; }
  try {
    if (!submitted) { readDraft(); submitted = normalizeReport(draft); store(); }
    sending = true; $('send').disabled = true; $('retry').disabled = true;
    message('Sending reviewed report...');
    message('');
    receipt(await api('/api/reports', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': account.csrf}, body: JSON.stringify(submitted)}));
  } catch (error) {
    message(error.message, true);
    if (submitted) receipt({status: 'unknown', message: 'Submission is not confirmed. Check status before retrying the same report.'});
  } finally { sending = false; $('send').disabled = !config?.enabled; }
}

// Clear the private handoff fragment immediately, before any requests or third-party navigation.
const fragment = location.hash;
const authParams = new URLSearchParams(location.search);
const authResult = authParams.get('auth');
const authDetail = authParams.get('detail') || '';
history.replaceState(null, '', '/');
if (authResult) message((authResult === 'cancelled' ? 'Discord sign-in was cancelled or expired. Your draft is still here.' : authResult === 'unavailable' ? 'Discord sign-in is temporarily unavailable. Your draft is still here.' : 'Discord sign-in could not be completed. Try signing in again; your draft is still here.') + (/^(?:token-request|token-response|token-scope|identity-request|identity-response|session)-[0-9]{1,3}$/.test(authDetail) ? ` Support code: ${authDetail}.` : ''), true);
try {
  const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
  if (saved?.draft) draft = validateDraft(saved.draft);
  if (saved?.submitted) submitted = normalizeReport(saved.submitted);
  if (fragment.startsWith('#draft=')) {
    if (fragment.length > 100000) throw new Error('Report is too large.');
    const bytes = Uint8Array.from(atob(fragment.slice(7).replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
    draft = validateDraft(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes))); submitted = null;
    store();
  }
} catch { message('The saved report could not be read. You can still describe the problem below or add a valid KFPS support report.', true); }
populate();
$('report-form').addEventListener('input', () => { if (!submitted) { readDraft(); refreshTechnical(); } });
$('report-form').addEventListener('submit', event => { event.preventDefault(); send(); });
$('login').onclick = () => { if (!submitted) readDraft(); location.assign('/auth/start'); };
$('logout').onclick = async () => { try { await api('/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': account.csrf}}); location.reload(); } catch (e) { message(e.message, true); } };
$('check').onclick = checkStatus;
$('retry').onclick = send;
$('new-report').onclick = () => { draft = fresh(); submitted = null; store(); location.reload(); };
$('report-file').onchange = async () => {
  try {
    const file = $('report-file').files[0]; if (!file) return;
    if (file.size > 49152) throw new Error('Choose a KFPS support report smaller than 48 KB.');
    const value = JSON.parse(await file.text());
    if (value.schema !== SCHEMA) throw new Error('This is not a KFPS support report. Artwork and save files are not accepted.');
    draft = validateDraft(value); submitted = null; populate(); store(); message('Saved report added. Review the details before sending.');
  } catch (error) { message(error.message, true); }
  finally { $('report-file').value = ''; }
};
try {
  config = await api('/api/config'); account = await api('/api/session');
  $('discord').href = config.join_url;
  $('support-invite').href = config.join_url;
  $('identity').textContent = account.authenticated ? `Signed in as ${account.name}` : 'Not signed in';
  $('login').hidden = !!account.authenticated; $('logout').hidden = !account.authenticated;
  $('login').disabled = !config.enabled;
  $('send').disabled = !config.enabled;
  $('send').textContent = account.authenticated ? 'Send report' : 'Sign in to send';
  if (!config.enabled) message('Reporting is temporarily unavailable. Your draft remains local; nothing has been submitted.', true);
  else if (!$('notice').classList.contains('error')) message('Review your report before sending.');
  if (submitted) { receipt({status: 'unknown'}); await checkStatus(); }
} catch (error) { message(error.message, true); }
