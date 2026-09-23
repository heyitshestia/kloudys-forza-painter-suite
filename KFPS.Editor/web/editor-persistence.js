(function installPersistence(global) {
  "use strict";

  class EditorPersistence {
    constructor(config, hooks = {}) {
      this.config = config;
      this.hooks = hooks;
      this.worker = null;
      this.pending = new Map();
      this.nextId = 0;
      this.lastReference = undefined;
      this.disposed = false;
    }

    record(id, pending, state, error = null) {
      try {
        this.hooks.event?.({ ...pending.cause, jobId: id, job: pending.operation, documentGeneration: pending.generation,
          requestId: pending.requestId, state, duration: Math.max(0, Date.now() - pending.started),
          queueDepth: this.pending.size, workerDuration: pending.workerDuration,
          ...(error ? { error: error.name || "unknown", errorCode: error.code || "" } : {}) });
      } catch (_) { /* Diagnostic observers cannot reject a storage operation. */ }
    }

    reset(error) {
      if (this.worker) {
        this.worker.onmessage = this.worker.onerror = this.worker.onmessageerror = null;
        this.worker.terminate();
      }
      this.worker = null;
      this.lastReference = undefined;
      for (const [id, request] of this.pending) {
        clearTimeout(request.timer);
        this.record(id, request, this.disposed ? "cancelled" : "failed", error);
        request.reject(error);
      }
      this.pending.clear();
    }

    dispose() {
      if (this.disposed) return;
      this.disposed = true;
      this.reset(Object.assign(new Error("Background storage has closed."), { code: "storage_closed" }));
    }

    start() {
      if (this.worker) return;
      const worker = new Worker("/tools/fabric-editor/editor-persistence-worker.js?v=1");
      this.worker = worker;
      worker.onmessage = event => {
        if (this.worker !== worker || this.disposed) return;
        const message = event.data;
        const pending = this.pending.get(message.id);
        if (!pending) return;
        clearTimeout(pending.timer);
        this.pending.delete(message.id);
        if (Number.isFinite(message.workerDuration)) pending.workerDuration = Math.max(0, message.workerDuration);
        if (message.error) {
          const error = Object.assign(new Error(message.error), { code: message.code });
          this.record(message.id, pending, "failed", error); pending.reject(error);
        } else { this.record(message.id, pending, "finished"); pending.resolve(message.value); }
      };
      worker.onerror = event => {
        if (this.worker !== worker || this.disposed) return;
        event.preventDefault();
        this.reset(Object.assign(new Error("The background save worker stopped. Recovery will retry."), { code: "worker_failed" }));
      };
      worker.onmessageerror = () => {
        if (this.worker === worker && !this.disposed) this.reset(new Error("The background save worker returned an unreadable response."));
      };
    }

    request(operation, data = {}) {
      if (this.disposed) return Promise.reject(Object.assign(new Error("Background storage has closed."), { code: "storage_closed" }));
      const maxBytes = this.config.maxBytes || 150 * 1024 * 1024;
      let inputBytes = 0;
      if (operation === "parseFile") inputBytes = data.file?.size || 0;
      if (operation === "parseText") {
        if (String(data.text).length > maxBytes) inputBytes = maxBytes + 1;
        else inputBytes = new Blob([String(data.text)]).size;
      }
      if (operation === "fetchJSON" && (/^\/api\/fabric-editor\/(?:json-file|project-file)(?:\?|$)/.test(data.url || "")
        || /^\/api\/fabric-editor\/autosave\?checkpoint=/.test(data.url || ""))) inputBytes = maxBytes;
      if (inputBytes > maxBytes) return Promise.reject(Object.assign(new Error("File exceeds the editor input limit. Choose a smaller file."), { code: "input_too_large" }));
      const protection = ["recovery", "browserRecovery", "recoveryHead"].includes(operation);
      const outstanding = [...this.pending.values()];
      // Reserve two request slots for checkpoint protection; admit at most two
      // project-sized read inputs, independently of the small-request count.
      if (this.pending.size >= 8 || !protection && (outstanding.filter(item => !item.protection).length >= 6
        || outstanding.reduce((total, item) => total + item.inputBytes, inputBytes) > maxBytes * 2)) {
        return Promise.reject(Object.assign(new Error("Background storage is busy. Try again in a moment."), { code: "storage_busy" }));
      }
      try { this.start(); }
      catch (error) { return Promise.reject(error); }
      const message = { ...data, operation, id: ++this.nextId, config: this.config };
      if (data.payload) {
        message.payload = { ...data.payload };
        const overlay = data.payload.editor_source_overlay;
        const reference = overlay ? { data_url: overlay.data_url || null, svg_text: overlay.svg_text || null } : null;
        if (this.lastReference === undefined || reference?.data_url !== this.lastReference?.data_url
          || reference?.svg_text !== this.lastReference?.svg_text) {
          message.reference = reference;
        }
        // Equal text can still be a newly parsed string after reopening. Retain
        // the current source, not an additional old copy of a large reference.
        this.lastReference = reference;
        if (overlay) message.payload.editor_source_overlay = { ...overlay, data_url: null, svg_text: null };
      }
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => this.reset(Object.assign(new Error("Background storage timed out. Recovery will retry."), { code: "worker_timeout" })), 45000);
        let generation = 0;
        try { generation = this.hooks.generation?.() || 0; } catch (_) {}
        const pending = { resolve, reject, timer, started: Date.now(), operation, generation, requestId: data.request_id, inputBytes, protection };
        try { pending.cause = data.payload?.editor_recovery_cause || this.hooks.cause?.() || null; } catch (_) {}
        if (data.payload?.recovery_revision) pending.cause = { ...pending.cause, revision: data.payload.recovery_revision };
        this.pending.set(message.id, pending);
        this.record(message.id, pending, "pending");
        try { this.worker.postMessage(message); }
        catch (error) { this.reset(error); }
      });
    }
  }

  global.KfpsEditorPersistence = { create: (config, hooks) => new EditorPersistence(config, hooks) };
})(window);
