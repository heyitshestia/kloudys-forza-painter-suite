(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorUpdates = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const ACK_KEY = "kloudyFabricUpdateBlinkAcknowledged";

  function create({ button, preferences, i18n: KfpsI18n, headers,
    fetcher = (...args) => fetch(...args),
    schedule = setTimeout, cancel = clearTimeout }) {
    let latest = "", sessionAck = "", unsavedAck = "";
    let timer = null, request = null, pending = null;
    let disposed = false, started = false, saving = false;

    function render() {
      if (disposed) return;
      let stored = "";
      try { stored = preferences.getItem(ACK_KEY) || ""; } catch (_) { /* Session acknowledgement still works. */ }
      const acknowledged = latest === sessionAck || latest === stored;
      button.hidden = !latest;
      button.disabled = saving;
      button.classList.toggle("isBlinking", Boolean(latest && !acknowledged));
      button.textContent = KfpsI18n.t("UPDATE");
      button.title = !acknowledged
        ? KfpsI18n.t("KFPS {0} is available. Click to stop blinking. Save your work and update from KFPS when ready.", latest)
        : unsavedAck === latest
          ? KfpsI18n.t("KFPS {0} is available. Blinking paused, but your acknowledgement could not be saved yet.", latest)
          : KfpsI18n.t("KFPS {0} is available. Blinking paused. Save your work and update from KFPS when ready.", latest);
      button.setAttribute("aria-label", button.title);
    }

    async function acknowledge() {
      if (disposed || !latest || saving) return;
      const version = latest;
      sessionAck = version;
      saving = true;
      render();
      try {
        preferences.setItem(ACK_KEY, version);
        if (typeof preferences.flush === "function" && !await preferences.flush()) throw new Error("Preference write pending");
        unsavedAck = "";
      } catch (_) {
        // Existing preference retries may complete later; never keep flashing at someone who clicked.
        unsavedAck = version;
      } finally {
        saving = false;
        render();
      }
    }

    function queue(delay) {
      if (disposed || !started) return;
      cancel(timer);
      timer = schedule(() => { timer = null; void check(); }, delay);
    }

    function check() {
      if (disposed) return Promise.resolve();
      if (pending) return pending;
      cancel(timer); timer = null;
      const controller = new AbortController();
      request = controller;
      const deadline = schedule(() => controller.abort(), 5000);
      let next = 60000;
      pending = Promise.resolve().then(async () => {
        try {
          const response = await fetcher("/api/fabric-editor/update-status", {
            headers, cache: "no-store", signal: controller.signal,
          });
          if (!response.ok) return;
          const status = await response.json();
          if (disposed || controller.signal.aborted) return;
          if (status.checking === true) next = 1500;
          if (status.available === true && typeof status.latestVersion === "string"
              && /^\d+(?:\.\d+){1,3}$/.test(status.latestVersion) && status.latestVersion.length <= 32) {
            latest = status.latestVersion;
          } else if (status.checked === true && status.available === false) {
            latest = "";
          }
          render();
        } catch (_) { /* Offline or closing: preserve a previously confirmed offer and retry quietly. */ }
        finally {
          cancel(deadline);
          request = null;
          pending = null;
          queue(next);
        }
      });
      return pending;
    }

    function start() {
      if (started || disposed) return;
      started = true;
      button.addEventListener("click", acknowledge);
      render();
      queue(1000);
    }

    function dispose() {
      if (disposed) return;
      disposed = true;
      cancel(timer); timer = null;
      request?.abort();
      button.removeEventListener("click", acknowledge);
      button.classList.remove("isBlinking");
    }

    return { start, check, dispose };
  }
  return { create, ACK_KEY };
});
