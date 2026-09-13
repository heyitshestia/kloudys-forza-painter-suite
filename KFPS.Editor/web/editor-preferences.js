"use strict";

window.KfpsEditorPreferences = (() => {
  const tr = (source, ...args) => window.KfpsI18n ? window.KfpsI18n.t(source, ...args) : source.replace(/\{(\d+)\}/g, (match, i) => i < args.length ? String(args[i]) : match);
  const localOnly = location.protocol === "file:";
  const keys = new Set([
    "kloudyFabricTheme", "kloudyFabricFavorites", "kloudyFabricFavoriteColors",
    "kloudyFabricLastColor", "kloudyFabricShortcuts", "kloudyFabricDockState",
    "kloudyFabricOverlayLayerMode", "kloudyFabricReuseLastFontSize",
    "kloudyFabricLastFontShapeTransform", "kloudyFabricTextVinylFont",
    "kloudyFabricTextVinylCustomFont", "kloudyFabricProjectSharingAcknowledged",
    "kloudyFabricOverlapCycle", "kloudyFabricLanguage", "kloudyFabricLanguageNoticeAcknowledged",
    "kloudyFabricEditorUpdateAcknowledged",
    "kloudyFabricUpdateBlinkAcknowledged",
  ]);
  const values = new Map();
  let pending = {};
  let writing = null;
  let timer = null;
  let retryDelay = 2000;
  let error = "";

  function browserGet(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }

  function token() {
    try {
      return new URLSearchParams(location.hash.slice(1)).get("session")
        || sessionStorage.getItem("kfpsFabricEditorSession") || "";
    } catch (_) { return ""; }
  }

  function report(message) {
    error = message;
    window.dispatchEvent(new CustomEvent("kfps-preferences-status", { detail: { error } }));
  }

  function schedule(delay = 200) {
    clearTimeout(timer);
    timer = setTimeout(flush, delay);
  }

  function flush() {
    clearTimeout(timer);
    timer = null;
    if (localOnly) { pending = {}; return Promise.resolve(true); }
    if (writing) return writing;
    writing = (async () => {
      while (Object.keys(pending).length) {
        const batch = pending;
        pending = {};
        try {
          const response = await fetch("/api/fabric-editor/preferences", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-KFPS-Editor-Session": token() },
            body: JSON.stringify({ settings: batch }),
            signal: AbortSignal.timeout(5000),
          });
          const result = await response.json();
          if (!response.ok || result.ok !== true) throw new Error(result.error || tr("HTTP {0}", response.status));
          retryDelay = 2000;
          report("");
        } catch (err) {
          pending = { ...batch, ...pending };
          report(tr("Editor settings could not be saved: {0}", err.message || err));
          schedule(retryDelay);
          retryDelay = Math.min(30000, retryDelay * 2);
          return false;
        }
      }
      return true;
    })().finally(() => { writing = null; });
    return writing;
  }

  async function load() {
    keys.forEach((key) => {
      const value = browserGet(key);
      if (value !== null) values.set(key, value);
    });
    if (localOnly) return;
    try {
      const response = await fetch("/api/fabric-editor/preferences", { cache: "no-store", signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error(tr("HTTP {0}", response.status));
      const result = await response.json();
      const stored = result.settings || {};
      if (typeof result.theme === "string" && !("kloudyFabricTheme" in stored)) {
        values.set("kloudyFabricTheme", result.theme);
      }
      Object.entries(stored).forEach(([key, value]) => {
        if (keys.has(key) && typeof value === "string") {
          values.set(key, value);
          try { localStorage.setItem(key, value); } catch (_) { /* App-folder settings remain authoritative. */ }
        }
      });
      // Migrate settings still available in this browser origin, never its artwork.
      values.forEach((value, key) => { if (!(key in stored)) pending[key] = value; });
      if (Object.keys(pending).length) schedule();
      report("");
    } catch (err) {
      report(tr("Editor settings could not be loaded: {0}", err.message || err));
      throw err;
    }
  }
  const ready = load();

  window.addEventListener("pagehide", flush);
  return {
    ready, flush,
    get error() { return error; },
    getItem(key) { return keys.has(key) ? values.get(key) ?? null : browserGet(key); },
    setItem(key, value) {
      if (!keys.has(key)) throw new Error(tr("Unsupported editor preference: {0}", key));
      const text = String(value);
      if (values.get(key) === text) return;
      values.set(key, text);
      try { localStorage.setItem(key, text); } catch (_) { /* The server copy is still writable. */ }
      pending[key] = text;
      schedule();
    },
    removeItem(key) {
      if (!keys.has(key)) throw new Error(tr("Unsupported editor preference: {0}", key));
      values.delete(key);
      try { localStorage.removeItem(key); } catch (_) { /* The server copy is still writable. */ }
      pending[key] = null;
      schedule();
    },
    async loadEditor(source) {
      try { await ready; }
      catch (_) {
        const dialog = document.createElement("dialog");
        const message = document.createElement("p");
        message.textContent = tr("Your editor settings could not be loaded. Retry to continue without replacing them with defaults.");
        const retry = document.createElement("button");
        retry.textContent = tr("Retry");
        dialog.append(message, retry);
        document.body.appendChild(dialog);
        dialog.showModal();
        await new Promise((resolve) => {
          retry.onclick = async () => {
            retry.disabled = true;
            try { await load(); dialog.close(); dialog.remove(); resolve(); }
            catch (_) { message.textContent = error; }
            finally { retry.disabled = false; }
          };
          dialog.addEventListener("cancel", (event) => event.preventDefault());
        });
      }
      window.KfpsI18n?.init(window.KfpsEditorPreferences);
      window.KfpsI18n?.applyStatic(document);
      const script = document.createElement("script");
      script.src = source;
      script.onerror = () => { document.body.textContent = tr("The editor could not load. Restart the editor or repair the KFPS installation."); };
      document.body.appendChild(script);
    },
  };
})();
