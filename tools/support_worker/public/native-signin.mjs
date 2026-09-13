import {UUID} from './protocol.mjs';

// The host sees only the approval URL. All session cookies stay HttpOnly.
export function nativeSignIn({api, origin, changed, authenticated, now = () => Date.now(), schedule = setTimeout, unschedule = clearTimeout}) {
  let attempt = null, timer = null, generation = 0, starting = false;
  const publish = error => changed(attempt ? {...attempt, error: error || ''} : null);
  const post = path => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}', signal: AbortSignal.timeout(15000)});
  const clear = () => { if (timer !== null) unschedule(timer); timer = null; };
  async function poll(epoch) {
    if (!attempt || epoch !== generation) return;
    if (now() >= attempt.expires_at) { attempt = null; publish(); changed({error: 'expired'}); return; }
    try {
      const result = await post('/api/native-auth/poll');
      if (!attempt || epoch !== generation) return;
      if (result.status === 'ready') {
        const account = await api('/api/session');
        if (epoch !== generation) return;
        if (!account.authenticated) throw Error('Session was not established.');
        attempt = null; publish(); authenticated(account); return;
      }
      if (['denied', 'cancelled', 'expired'].includes(result.status)) { attempt = null; publish(); changed({error: result.status}); return; }
    } catch {
      if (!attempt || epoch !== generation) return;
      publish('connection');
    }
    timer = schedule(() => poll(epoch), 2000);
  }
  return Object.freeze({
    async start() {
      if (starting || attempt) return;
      starting = true; const epoch = ++generation;
      try {
        const result = await post('/api/native-auth/start');
        if (epoch !== generation) return;
        const target = new URL(result.url);
        if (!UUID.test(result.id || '') || target.origin !== origin || target.pathname !== '/auth/native'
          || target.search !== '?ticket=' + result.id || !/^[A-F0-9]{4}-[A-F0-9]{4}$/.test(result.code)
          || !Number.isFinite(result.expires_at) || result.expires_at <= now() || result.expires_at > now() + 301000) throw Error('Invalid authorization response.');
        attempt = {...result, launch: true}; publish();
        timer = schedule(() => poll(epoch), 2000);
      } catch { if (epoch === generation) changed({error: 'start'}); }
      finally { starting = false; }
    },
    request() { return attempt?.launch ? {id: attempt.id, url: attempt.url} : null; },
    opened(id, success) { if (attempt?.id === id) { attempt.launch = false; publish(success ? '' : 'browser'); } },
    reopen() { if (attempt) { attempt.launch = true; publish(); } },
    async cancel() {
      ++generation; clear(); attempt = null; starting = true; publish();
      try { await post('/api/native-auth/cancel'); } catch { /* Expiry still closes an unreachable request. */ }
      finally { starting = false; }
    },
  });
}
