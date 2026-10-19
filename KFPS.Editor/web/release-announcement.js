"use strict";

(function (root) {
  const STATUS_KEYS = ["releaseId", "publishedAt", "expiresAt", "locale", "acknowledged", "eligible"];
  function safeStatus(value) {
    return Object.fromEntries(STATUS_KEYS.map(key => [key, value?.[key] ?? null]));
  }

  function create({ document, request, ready, window = root }) {
    const client = Array.from(window.crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, "0")).join("");
    let timer = null, expiryTimer = null, done = false, busy = false, token = "", acknowledged = false;
    let dialog = null, previousFocus = null, status = safeStatus(null), retryCount = 0;
    const schedule = (delay = 350) => { window.clearTimeout(timer); if (!done) timer = window.setTimeout(tick, delay); };
    const paint = () => new Promise(resolve => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)));
    const unavailable = () => document.visibilityState !== "visible" || !ready() || Boolean(document.querySelector("dialog[open]"));

    function close() {
      done = true;
      window.clearTimeout(timer);
      window.clearTimeout(expiryTimer);
      if (dialog?.open) dialog.close();
      dialog?.remove();
      if (token && !acknowledged) request({ action: "release", token }, true).catch(() => {});
      token = "";
      if (previousFocus?.isConnected && !document.querySelector("dialog[open]")) previousFocus.focus({ preventScroll: true });
    }

    async function present(row) {
      if (unavailable()) {
        await request({ action: "release", token: row.token });
        schedule();
        return;
      }
      token = row.token;
      previousFocus = document.activeElement;
      dialog = document.createElement("dialog");
      dialog.id = "kfpsReleaseAnnouncement";
      dialog.lang = row.locale;
      dialog.setAttribute("aria-labelledby", "kfpsReleaseAnnouncementTitle");
      const body = document.createElement("div");
      body.className = "release-announcement-body";
      body.tabIndex = 0;
      const title = document.createElement("h2");
      title.id = "kfpsReleaseAnnouncementTitle";
      title.textContent = row.content.title;
      body.append(title);
      for (const block of row.content.blocks) {
        if (block.heading) {
          const heading = document.createElement("h3");
          heading.textContent = block.heading;
          body.append(heading);
        }
        const paragraph = document.createElement("p");
        paragraph.textContent = block.text;
        body.append(paragraph);
      }
      const closing = document.createElement("p");
      closing.className = "release-announcement-closing";
      closing.textContent = row.content.closing;
      body.append(closing);
      const actions = document.createElement("div");
      actions.className = "release-announcement-actions";
      const support = document.createElement("button");
      support.type = "button";
      support.textContent = row.content.supportLabel;
      support.disabled = true;
      support.addEventListener("click", async () => {
        if (!acknowledged || support.disabled) return;
        support.disabled = true;
        try { await request({ action: "support", token }); } catch (_) { /* Closing is always available. */ }
        finally { support.disabled = false; }
      });
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "primary";
      dismiss.textContent = row.content.closeLabel;
      dismiss.addEventListener("click", close);
      actions.append(support, dismiss);
      dialog.append(body, actions);
      dialog.addEventListener("cancel", event => { event.preventDefault(); close(); });
      dialog.addEventListener("close", close, { once: true });
      dialog.addEventListener("keydown", event => {
        event.stopPropagation();
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() !== "c") event.preventDefault();
      });
      document.body.append(dialog);
      dialog.showModal();
      body.focus({ preventScroll: true });
      expiryTimer = window.setTimeout(close, Math.max(0, Math.min(row.remainingMs, Date.parse(row.expiresAt) - Date.now())));
      await paint();
      if (done || !dialog.open || document.visibilityState !== "visible" || !dialog.getBoundingClientRect().width) {
        close();
        return;
      }
      for (let attempt = 0; attempt < 3 && !done; attempt++) {
        try {
          const result = await request({ action: "presented", token });
          status = safeStatus(result);
          acknowledged = result.acknowledged === true;
          if (!acknowledged) { close(); return; }
          support.disabled = false;
          return;
        } catch (_) { /* A lost acknowledgment response is safe to retry. */ }
      }
      close();
    }

    async function tick() {
      if (done || busy) return;
      if (unavailable()) { schedule(500); return; }
      busy = true;
      try {
        const row = await request({ action: "claim", client });
        status = safeStatus(row);
        if (row.token) await present(row);
        else if (row.retryAfterMs && row.eligible) schedule(Math.min(30500, row.retryAfterMs));
        else done = true;
      } catch (_) {
        if (++retryCount < 3) schedule(1500);
        else close();
      } finally { busy = false; }
    }
    window.addEventListener("pagehide", close, { once: true });
    return { start: () => schedule(), close, readStatus: () => ({ ...status }) };
  }

  const api = { create, safeStatus };
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    const host = document.currentScript?.dataset.releaseHost;
    if (!host || !["editor", "studio"].includes(host) || location.protocol === "file:") return;
    const endpoint = host === "studio" ? "./api/release-announcement" : "/api/fabric-editor/release-announcement";
    const request = async (body, keepalive = false) => {
      const headers = { "Content-Type": "application/json" };
      if (host === "editor") {
        headers["X-KFPS-Editor-Session"] = new URLSearchParams(location.hash.slice(1)).get("session")
          || sessionStorage.getItem("kfpsFabricEditorSession") || "";
      }
      const response = await fetch(endpoint, { method: "POST", headers, body: JSON.stringify(body),
        cache: "no-store", credentials: "same-origin", keepalive,
        signal: keepalive ? undefined : AbortSignal.timeout(4000) });
      if (!response.ok) throw new Error("Release notice unavailable.");
      return response.json();
    };
    const notice = create({ document, request,
      ready: () => host === "studio" ? Boolean(root.__liveryLab?.ready) : Boolean(root.KfpsDesktop?.ready) });
    root.KfpsReleaseAnnouncement = { readStatus: notice.readStatus };
    notice.start();
  }
})(typeof window === "object" ? window : globalThis);
