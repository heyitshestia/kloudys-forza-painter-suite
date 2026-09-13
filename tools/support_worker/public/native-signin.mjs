import {UUID} from './protocol.mjs';

// The host sees only the approval URL. All session cookies stay HttpOnly.
export function nativeSignIn({api, origin, changed, authenticated, now = () => performance.now(), schedule = setTimeout, unschedule = clearTimeout}) {
  let attempt = null, timer = null, generation = 0, starting = false;
  let deadline = 0, startedAt = now(), attemptNumber = 0, sequence = 0;
  const events = [];
  const lastStages = new Map();
  function record(stage, result, status = 0) {
    const previous = lastStages.get(stage);
    const http_status = Number.isInteger(status) && status >= 100 && status <= 599 ? status : 0;
    if (previous?.attempt === attemptNumber && previous.stage === stage && previous.result === result && previous.http_status === http_status) return;
    events.push({sequence: ++sequence, attempt: attemptNumber, stage, result, http_status,
      elapsed_ms: Math.max(0, Math.min(600000, Math.floor(now() - startedAt)))});
    lastStages.set(stage, events.at(-1));
    if (events.length > 64) events.shift();
  }
  const reason = error => error?.supportCode === 'invalid-response' ? 'invalid-response'
    : ['TimeoutError', 'AbortError'].includes(error?.name) ? 'timeout'
    : error?.status === 429 ? 'rate-limited' : error?.status === 503 ? 'service-unavailable'
    : error?.status >= 500 ? 'server-error' : error?.status >= 400 ? 'request-rejected' : 'network';
  const invalid = () => Object.assign(new Error('Invalid authorization response.'), {supportCode: 'invalid-response'});
  const publish = error => changed(attempt ? {...attempt, error: error || ''} : null);
  const post = path => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(15000)});
  const clear = () => { if (timer !== null) unschedule(timer); timer = null; };
  function end(result) {
    clear(); attempt = null; record('terminal', result); publish(); changed({error: result});
  }
  const active = () => {
    if (attempt && now() >= deadline) end('expired');
    return !!attempt;
  };
  async function poll(epoch) {
    if (!attempt || epoch !== generation) return;
    if (now() >= deadline) { end('expired'); return; }
    let stage = 'poll';
    try {
      const result = await post('/api/native-auth/poll');
      if (!attempt || epoch !== generation) return;
      if (!result || typeof result !== 'object') throw invalid();
      if (result.status === 'ready') {
        record('poll', 'ready');
        stage = 'session';
        const account = await api('/api/session');
        if (epoch !== generation) return;
        if (!account?.authenticated) { record('session', 'session-missing'); publish('session-missing'); }
        else {
          record('session', 'authenticated');
          attempt = null; publish(); authenticated(account); return;
        }
      } else if (['denied', 'cancelled', 'expired'].includes(result.status)) {
        end(result.status); return;
      } else if (result.status === 'pending') {
        record('poll', 'pending');
      } else {
        throw invalid();
      }
    } catch (error) {
      if (!attempt || epoch !== generation) return;
      const code = reason(error); record(stage, code, error?.status); publish(code);
    }
    timer = schedule(() => poll(epoch), 2000);
  }
  record('init', 'ready');
  return Object.freeze({
    async start() {
      if (starting || attempt) return;
      starting = true; const epoch = ++generation;
      ++attemptNumber; startedAt = now(); record('start', 'requested'); changed({starting: true});
      try {
        const result = await post('/api/native-auth/start');
        if (epoch !== generation) return;
        let target;
        try { target = new URL(result?.url); } catch { throw invalid(); }
        // Absolute server time is not comparable with the user's PC clock.
        // Older services omit the duration; their ticket still expires server-side.
        const remaining = result.expires_in_ms === undefined ? 300000 : result.expires_in_ms;
        if (!UUID.test(result.id || '') || target.origin !== origin || target.pathname !== '/auth/native' || target.username || target.password || target.hash
          || target.search !== '?ticket=' + result.id || !/^[A-F0-9]{4}-[A-F0-9]{4}$/.test(result.code)
          || !Number.isSafeInteger(result.expires_at) || result.expires_at <= 0
          || !Number.isInteger(remaining) || remaining <= 0 || remaining > 300000) throw invalid();
        deadline = startedAt + remaining;
        if (now() >= deadline) { end('expired'); return; }
        attempt = {id: result.id, url: result.url, code: result.code, expires_at: result.expires_at, launch: true};
        record('start', 'ready'); publish();
        timer = schedule(() => poll(epoch), 2000);
      } catch (error) { if (epoch === generation) {
        const code = reason(error); record('start', code, error?.status); changed({error: code});
      } }
      finally { if (epoch === generation) starting = false; }
    },
    request() { return active() && attempt.launch ? {id: attempt.id, url: attempt.url} : null; },
    opened(id, success) { if (active() && attempt.id === id && attempt.launch) {
      attempt.launch = false; record('browser', success ? 'accepted' : 'failed'); publish(success ? '' : 'browser');
    } },
    reopen() { if (active()) { attempt.launch = true; record('browser', 'reopen'); publish(); } },
    manual() {
      if (!active()) return false;
      // A real target=_blank click also works when the native polling bridge is
      // unavailable. Suppress a duplicate automatic launch and any late reply.
      attempt.launch = false; record('browser', 'manual'); publish(); return true;
    },
    async cancel() {
      ++generation; clear(); attempt = null; starting = true; publish();
      record('cancel', 'requested');
      try { await post('/api/native-auth/cancel'); record('cancel', 'cancelled'); }
      catch (error) { record('cancel', reason(error), error?.status); }
      finally { starting = false; changed({error: 'cancelled'}); }
    },
    diagnostics(after = 0) { return events.filter(event => event.sequence > after).map(event => ({...event})); },
  });
}

export function signInErrorText(value) {
  const messages = {
    expired: 'This sign-in request expired. Click Sign in with Discord to start again. Your report is still here.',
    denied: 'Sign-in was declined in the browser. Click Sign in with Discord to try again. Your report is still here.',
    cancelled: 'Sign-in was cancelled. You can start again when ready. Your report is still here.',
    'rate-limited': 'Too many sign-in attempts. Please wait a few minutes before trying again. Your report is still here.',
    'service-unavailable': 'Discord sign-in is temporarily unavailable. Please try again shortly. Your report is still here.',
    'invalid-response': 'The sign-in service returned an unexpected response. Please retry. Your report is still here.',
    'request-rejected': 'The sign-in service rejected this request. Please retry sign-in. Your report is still here.',
    'server-error': 'The sign-in service encountered an error. Please try again shortly. Your report is still here.',
    'session-missing': 'Browser approval was received, but KFPS could not establish the signed-in session. It will retry automatically. Your report is still here.',
  };
  if (messages[value?.error]) return messages[value.error];
  if (value?.id) return 'Sign-in has not completed. Open in default browser, or copy the sign-in link into your browser. Your report is still here.';
  return value?.error === 'timeout'
    ? 'The sign-in request timed out. Check your connection and try again. Your report is still here.'
    : 'Could not reach the sign-in service. Check your connection and try again. Your report is still here.';
}
