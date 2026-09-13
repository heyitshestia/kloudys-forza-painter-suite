(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsDesktopProtocol = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function create({ execute, bridge, userWaiting, onError, clock = globalThis }) {
    const pending = new Map();
    const completed = new Map();
    const maxCompleted = 16;
    let disposed = false;
    function notify(id, result) {
      try { bridge()?.completed(id, JSON.stringify(result)); } catch (_) { /* Host can read the retained outcome. */ }
    }
    function phase(record) {
      const next = userWaiting() ? "user-wait" : "working";
      if (next !== record.phase || next === "user-wait") {
        try { bridge()?.progress?.(record.id, next); } catch (_) { /* A lost progress reply never repeats work. */ }
      }
      record.phase = next;
    }
    const api = {
      ready: false,
      async execute(id, operation, payload) {
        if (disposed || typeof id !== "string" || !/^[a-zA-Z0-9_-]{1,64}$/.test(id)) return;
        if (completed.has(id)) { notify(id, completed.get(id)); return; }
        if (pending.has(id)) return;
        // Native requests are serialized by the host; bound misuse too.
        if (pending.size >= 8) { notify(id, { ok: false, error: "Editor is busy" }); return; }
        const record = { id, phase: "working", timer: null };
        pending.set(id, record);
        if (operation === "open" || operation === "close") {
          phase(record);
          record.timer = clock.setInterval(() => phase(record), 500);
        }
        let result;
        try { result = { ok: true, value: await execute(operation, payload) }; }
        catch (error) {
          result = { ok: false, error: String(error?.message || error).slice(0, 2000) };
          try { onError(error); } catch (_) { /* Error UI cannot strand the terminal outcome. */ }
        } finally {
          if (record.timer !== null) clock.clearInterval(record.timer);
          pending.delete(id);
        }
        if (disposed) return;
        completed.set(id, result);
        while (completed.size > maxCompleted) completed.delete(completed.keys().next().value);
        notify(id, result);
      },
      outcome(id) {
        if (completed.has(id)) return { state: "complete", result: completed.get(id) };
        const record = pending.get(id);
        return { state: record ? record.phase : "unknown" };
      },
      dispose() {
        disposed = true;
        api.ready = false;
        for (const record of pending.values()) if (record.timer !== null) clock.clearInterval(record.timer);
        pending.clear();
        completed.clear();
      },
    };
    return api;
  }
  return { create };
});
