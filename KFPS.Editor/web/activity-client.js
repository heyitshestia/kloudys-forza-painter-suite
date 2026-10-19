"use strict";

(function (root) {
  function create({ document, ready, request, window = root }) {
    let stopped = false, busy = false, timer = null, attempts = 0;
    const stop = () => { stopped = true; window.clearTimeout(timer); };
    const schedule = delay => { if (!stopped) timer = window.setTimeout(tick, delay); };
    async function tick() {
      if (stopped || busy) return;
      if (document.visibilityState !== "visible" || !ready()) { schedule(500); return; }
      busy = true;
      try {
        await new Promise(resolve => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)));
        if (stopped) return;
        if (document.visibilityState !== "visible" || !ready()) { schedule(500); return; }
        await request();
        stop();
      } catch (_) {
        if (++attempts < 3) schedule(1500);
        else stop();
      } finally { busy = false; }
    }
    window.addEventListener("pagehide", stop, { once: true });
    return { start: () => schedule(500), stop };
  }

  if (typeof module === "object" && module.exports) module.exports = { create };
  else {
    const host = document.currentScript?.dataset.activityHost;
    if (!["editor", "studio"].includes(host) || location.protocol === "file:") return;
    const request = async () => {
      const headers = { "Content-Type": "application/json" };
      if (host === "editor") headers["X-KFPS-Editor-Session"] = new URLSearchParams(location.hash.slice(1)).get("session")
        || sessionStorage.getItem("kfpsFabricEditorSession") || "";
      const endpoint = host === "studio" ? "./api/activity-ready" : "/api/fabric-editor/activity-ready";
      const controller = new AbortController();
      const deadline = root.setTimeout(() => controller.abort(), 4000);
      try {
        const response = await fetch(endpoint, { method: "POST", headers, body: "{}", cache: "no-store",
          credentials: "same-origin", signal: controller.signal });
        const result = await response.json();
        if (!response.ok || result?.ok !== true) throw new Error("Activity host unavailable.");
      } finally {
        root.clearTimeout(deadline);
      }
    };
    create({ document, request,
      ready: () => host === "studio" ? Boolean(root.__liveryLab?.ready) : Boolean(root.KfpsDesktop?.ready) }).start();
  }
})(typeof window === "object" ? window : globalThis);
