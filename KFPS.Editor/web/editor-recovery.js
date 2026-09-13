(function installRecovery(root) {
  "use strict";
  function create({ transport, eligible = () => true, onQueued = () => {}, onResult = () => {},
    onClear = () => {}, onError = () => {}, clock = Date.now, now = () => performance.now(),
    setTimer = setTimeout, clearTimer = clearTimeout, idleMs = 500, maxWaitMs = 2000 }) {
    let revision = 0, pending = null, queued = null, pendingSince = null;
    let writeTimer = null, retryTimer = null, retryDelay = 2000;
    let writePromise = null, backupPromise = null, backupQueued = null, disposed = false, closing = false, shutdownPromise = null;
    let status = Object.freeze({ state: "idle", revision: 0 });
    const notify = (callback, ...args) => {
      try { callback(...args); } catch (error) { try { onError(error); } catch (_ignored) {} }
    };
    function next() {
      const value = Math.max(revision + 1, clock() * 1000);
      if (!Number.isSafeInteger(value)) throw Error("Recovery revision exceeds its safe range.");
      revision = value;
      return revision;
    }
    function stopRetry() { clearTimer(retryTimer); retryTimer = null; retryDelay = 2000; }
    function report(operation, browserOk, serverOk, error = "", code = "") {
      if (operation.recovery_revision === revision) {
        status = Object.freeze({ state: browserOk || serverOk ? operation.action === "clear" ? "cleared" : "saved" : "failed",
          revision, browserOk, serverOk, error, code });
      }
      notify(onResult, operation, browserOk, serverOk, error, code);
    }
    function backup(operation) {
      backupQueued = operation;
      if (backupPromise) return backupPromise;
      backupPromise = (async () => {
        while (backupQueued && !disposed) {
          const payload = backupQueued;
          backupQueued = null;
          try {
            const result = await transport.request("browserRecovery", { payload });
            if (disposed) return;
            if (payload.recovery_revision === revision && result.browserOk) {
              report(payload, true, status.serverOk === true, status.error || "", status.code || "");
            }
          } catch (_error) { /* The ordered app writer reports failure and retries. */ }
        }
      })().finally(() => { backupPromise = null; });
      return backupPromise;
    }
    function drain() {
      if (writePromise) return writePromise;
      writePromise = (async () => {
        while (queued && !disposed) {
          const operation = queued;
          queued = null;
          if (operation.recovery_revision !== revision) continue;
          let result;
          try { result = await transport.request("recovery", { payload: operation }); }
          catch (error) {
            result = { browserOk: false, serverOk: false, retryable: error.code !== "recovery_too_large",
              error: String(error.message || error), code: error.code || "" };
            notify(onError, error);
          }
          if (disposed) return;
          report(operation, Boolean(result.browserOk), Boolean(result.serverOk), result.error || "", result.code || "");
          if (result.serverOk) retryDelay = 2000;
          else if (result.retryable !== false && operation.recovery_revision === revision && !disposed && !closing) {
            clearTimer(retryTimer);
            retryTimer = setTimer(() => {
              retryTimer = null;
              if (operation.recovery_revision !== revision || disposed || closing) return;
              queued = operation;
              void drain();
            }, retryDelay);
            retryDelay = Math.min(30000, retryDelay * 2);
          }
        }
      })().finally(() => {
        writePromise = null;
        if (queued && !disposed) return drain();
      });
      return writePromise;
    }
    function flush() {
      clearTimer(writeTimer); writeTimer = null; pendingSince = null;
      if (pending) { queued = pending; pending = null; }
      if (writePromise && queued) void backup(queued);
      return drain();
    }
    function dispose() {
      disposed = true; clearTimer(writeTimer); clearTimer(retryTimer);
      pending = queued = backupQueued = null;
    }
    return {
      observe(value) { if (Number.isSafeInteger(value) && value > 0) revision = Math.max(revision, value); },
      write(payload) {
        if (disposed || closing || !eligible() || !payload || !Array.isArray(payload.shapes)) return false;
        try { pending = { ...payload, recovery_revision: next() }; }
        catch (error) { notify(onError, error); return false; }
        status = Object.freeze({ state: "pending", revision });
        notify(onQueued, revision);
        stopRetry();
        if (pendingSince === null) pendingSince = now();
        clearTimer(writeTimer);
        writeTimer = setTimer(flush, Math.min(idleMs, Math.max(0, maxWaitMs - (now() - pendingSince))));
        return true;
      },
      clear() {
        if (disposed || closing) return Promise.resolve();
        const value = next();
        pending = null; pendingSince = null;
        stopRetry(); clearTimer(writeTimer); writeTimer = null;
        notify(onClear, value);
        status = Object.freeze({ state: "cleared", revision });
        queued = { action: "clear", shapes: [], recovery_revision: revision };
        if (writePromise) void backup(queued);
        return drain();
      },
      flush,
      shutdown() {
        if (shutdownPromise) return shutdownPromise;
        closing = true; stopRetry();
        const disk = flush();
        shutdownPromise = Promise.allSettled([disk, backupPromise]).finally(dispose);
        return shutdownPromise;
      },
      dispose,
      get revision() { return revision; },
      get status() { return status; },
      get writePromise() { return writePromise; },
      get backupPromise() { return backupPromise; },
      get retryScheduled() { return retryTimer !== null; },
    };
  }
  const api = { create };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.KfpsEditorRecovery = api;
})(typeof globalThis === "object" ? globalThis : this);
