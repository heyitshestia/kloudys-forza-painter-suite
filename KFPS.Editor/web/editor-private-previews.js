(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorPrivatePreviews = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ headers, fetcher = (...args) => fetch(...args), env = window }) {
    const entries = new Map(), queue = [];
    let active = 0;
    const observer = env.IntersectionObserver ? new env.IntersectionObserver(items => {
      for (const item of items) if (item.isIntersecting) enqueue(entries.get(item.target));
    }, { rootMargin: "300px" }) : null;
    function forget(image) {
      const entry = entries.get(image);
      if (!entry) return;
      entries.delete(image);
      image.removeEventListener("error", entry.onError);
      observer?.unobserve(image);
      const queued = queue.indexOf(entry);
      if (queued >= 0) queue.splice(queued, 1);
      entry.controller.abort();
      if (entry.objectUrl) env.URL.revokeObjectURL(entry.objectUrl);
      image.removeAttribute("src");
    }
    function clear(container) {
      for (const image of entries.keys()) if (!container || image === container || container.contains(image)) forget(image);
    }
    function enqueue(entry) {
      if (!entry || entry.queued || entry.controller.signal.aborted) return;
      entry.queued = true;
      observer?.unobserve(entry.image);
      queue.push(entry);
      pump();
    }
    function pump() {
      while (active < 4 && queue.length) {
        const entry = queue.shift();
        if (entry.controller.signal.aborted) continue;
        active++;
        void load(entry).finally(() => { active--; pump(); });
      }
    }
    async function load(entry) {
      const timer = setTimeout(() => entry.controller.abort(), 15000);
      try {
        const response = await fetcher(entry.url, { headers, signal: entry.controller.signal, redirect: "error" });
        if (!response.ok) throw new Error("Preview unavailable");
        const blob = await response.blob();
        if (entries.get(entry.image) !== entry || entry.controller.signal.aborted) return;
        entry.objectUrl = env.URL.createObjectURL(blob);
        entry.image.src = entry.objectUrl;
      } catch (_) {
        if (entries.get(entry.image) === entry) entry.image.dispatchEvent(new env.Event("error"));
      } finally { clearTimeout(timer); }
    }
    function set(image, path) {
      forget(image);
      if (!path) return;
      let url;
      try { url = new env.URL(path, env.location.href); }
      catch (_) { image.dispatchEvent(new env.Event("error")); return; }
      if (url.origin !== env.location.origin || !["/api/fabric-editor/json-preview", "/api/fabric-editor/asset-preview"].includes(url.pathname)) {
        image.dispatchEvent(new env.Event("error"));
        return;
      }
      const entry = { image, url: url.href, controller: new AbortController(), queued: false, objectUrl: "" };
      entry.onError = () => { if (entries.get(image) === entry) forget(image); };
      entries.set(image, entry);
      image.addEventListener("error", entry.onError, { once: true });
      if (image.loading === "lazy" && observer) observer.observe(image);
      else enqueue(entry);
    }
    const pagehide = event => { if (!event.persisted) clear(); };
    env.addEventListener("pagehide", pagehide);
    return { set, clear, dispose() { clear(); observer?.disconnect(); env.removeEventListener("pagehide", pagehide); } };
  }
  return Object.freeze({ create });
});
