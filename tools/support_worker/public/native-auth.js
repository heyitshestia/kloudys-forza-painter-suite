import {UUID} from '/protocol.mjs';
import {language,applyLanguage,onLanguageChange,localizedError} from '/report-locale.mjs';
const $ = id => document.getElementById(id);
const ko = language()==='ko';
const t = (en, kr) => ko ? kr : en;
const id = new URLSearchParams(location.search).get('ticket');
let account;
applyLanguage();
// Approval state lives on the server; changing language never approves or sends.
onLanguageChange(()=>location.reload());
$('auth-info').textContent=t('Checking your sign-in request...', '로그인 요청을 확인하는 중입니다...');
document.documentElement.lang = ko ? 'ko' : 'en';
for (const [key, en, kr] of [
  ['auth-title', 'Sign in to KFPS', 'KFPS 로그인'],
  ['approval-warning', 'Only continue if you started sign-in in KFPS and the code below matches the code in your KFPS report window. Never approve a code sent to you by someone else.', 'KFPS에서 직접 로그인을 시작했고 아래 코드가 KFPS 신고 창에 표시된 코드와 일치할 때만 계속해 주세요. 다른 사람이 보내 준 코드는 승인하지 마세요.'],
  ['approval-privacy', 'This signs in your KFPS report window. It does not send a report or share your Discord password, messages, or email address.', 'KFPS 신고 창에 로그인합니다. 보고서는 전송되지 않으며 Discord 비밀번호, 메시지, 이메일 주소는 공유되지 않습니다.'],
  ['match-label', 'I started this request and the code matches my KFPS window.', '제가 직접 요청했으며 코드가 KFPS 창의 코드와 일치합니다.'],
  ['approve', 'Authorize KFPS', 'KFPS 로그인 승인'], ['deny', 'Cancel', '취소'], ['auth-login', 'Sign in with Discord', 'Discord로 로그인'],
]) $(key).textContent = t(en, kr);
async function request(path, options = {}) {
  const response = await fetch(path, {...options, credentials: 'same-origin', signal: AbortSignal.timeout(15000)});
  const value = await response.json();
  if (response.status === 401) { $('auth-login').hidden = false; throw Error(t('Sign in with Discord, then confirm your KFPS window below.', 'Discord로 로그인한 다음 KFPS 창을 확인해 주세요.')); }
  if (!response.ok) throw Error(t('This request could not be completed. Return to KFPS and start sign-in again.', '요청을 완료하지 못했습니다. KFPS로 돌아가 로그인을 다시 시작해 주세요.'));
  return value;
}
function complete(status) {
  $('notice').textContent = '';
  $('approval').hidden = true; $('auth-login').hidden = true;
  $('auth-info').textContent = status === 'ready'
    ? t('Authorized. Return to your KFPS report window; it will sign in automatically. You can close this tab.', '승인되었습니다. KFPS 신고 창으로 돌아가면 자동으로 로그인됩니다. 이 탭은 닫아도 됩니다.')
    : t('Sign-in cancelled. Your report has not been sent.', '로그인이 취소되었습니다. 보고서는 전송되지 않았습니다.');
}
async function decide(action) {
  $('notice').textContent = '';
  $('approve').disabled = true; $('deny').disabled = true;
  try {
    const value = await request('/api/native-auth/' + action, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': account.csrf}, body: JSON.stringify({ticket: id, confirm: true, code: account.code})});
    complete(value.status);
  } catch (error) { $('notice').textContent = localizedError(error.message); $('deny').disabled = false; $('approve').disabled = !$('match-code').checked; }
}
$('match-code').onchange = () => { $('approve').disabled = !$('match-code').checked; };
$('approve').onclick = () => { if ($('match-code').checked) decide('approve'); };
$('deny').onclick = () => decide('deny');
try {
  if (!UUID.test(id || '')) throw Error(t('Invalid sign-in link. Start again in KFPS.', '올바르지 않은 로그인 링크입니다. KFPS에서 다시 시작해 주세요.'));
  $('auth-login').href = '/auth/start?native=' + id;
  account = await request('/api/native-auth/approval?ticket=' + id);
  if (account.status !== 'pending') complete(account.status);
  else {
    $('auth-info').textContent = t('Confirm the request from your KFPS report window.', 'KFPS 신고 창에서 보낸 요청을 확인해 주세요.');
    $('approval-name').textContent = t('Discord account: ', 'Discord 계정: ') + account.name;
    $('approval-code').textContent = account.code;
    $('approval').hidden = false;
  }
} catch (error) { $('auth-info').textContent = localizedError(error.message); }
