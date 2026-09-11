/* Local timings only: no artwork, filenames, input values or per-frame readbacks. */
(function (root) {
  "use strict";
  const ACTIONS = new Set("idle pointer move scale skew rotate pan zoom guide select reference numeric nudge undo redo add duplicate delete copy paste color mask order group layout save load new export asset text pixel settings edit".split(" "));
  const COMMANDS = {
    undoBtn: "undo", historyUndo: "undo", redoBtn: "redo", historyRedo: "redo",
    saveProject: "save", saveProjectAs: "save", exportJson: "export", newCanvas: "new",
    loadProject: "load", openJsonBrowser: "load", selectProjectEntry: "load", selectJsonBrowserEntry: "load",
    duplicateLayer: "duplicate", quickDuplicateLayer: "duplicate", deleteLayer: "delete", quickDeleteLayer: "delete",
    copyLayer: "copy", pasteLayer: "paste", applyFields: "numeric", colorSwatchButton: "color", quickColorSwatch: "color",
    colorEyedropper: "color", sampleOverlayColor: "color", applyColorToSelection: "color", equalizeAlpha: "color",
    maskSelectedTool: "mask", bringFront: "order", bringForward: "order", sendBackward: "order", sendBack: "order",
    groupSelected: "group", quickGroupSelected: "group", ungroupSelected: "group", flipHorizontal: "scale", flipVertical: "scale",
    rotateLeft: "rotate", rotateRight: "rotate", generateTextVinyl: "text", generatePixelArt: "pixel",
    fitView: "zoom", fitSelected: "zoom", quickFitSelected: "zoom", resetView: "zoom", toggleOverlay: "reference", removeOverlay: "reference",
  };
  function sourceName(value) {
    try {
      const path = new URL(value, root.location?.href).pathname;
      return /\/tools\/fabric-editor\/(?:vendor\/|locales\/)?[a-zA-Z0-9.-]+\.(js|html)$/.test(path)
        ? path.split("/tools/fabric-editor/")[1] : "unknown";
    } catch (_) { return "unknown"; }
  }
  function errorClass(value) {
    const name = value?.name;
    return /^(Error|TypeError|RangeError|ReferenceError|SyntaxError|SecurityError|AbortError|QuotaExceededError)$/.test(name) ? name : "unknown";
  }
  function create(env) {
    const doc = env.document, clock = () => env.performance.now();
    const page = Array.from(env.crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, "0")).join("");
    const frames = new Float32Array(600), events = [], timeline = [{ at: 0, action: "idle" }];
    const totals = { totalTasks: 0, totalGaps100: 0, totalGaps500: 0, totalDraws: 0 };
    let period = {}, lastSample = {}, cursor = 0, count = 0, lastFrame = 0, seq = 0, pending = null, frameId = 0;
    let provider = () => ({}), headers = null, enabled = true, current = "idle", startAt = 0, clientDrops = 0;
    let logging = {}, transportOk = false, renderStart = 0, observer = null, lastRequestAt = -Infinity, pulseTimer = 0;
    try {
      const token = new URLSearchParams((env.location.hash || "").replace(/^#/, "")).get("session") || env.sessionStorage.getItem("kfpsFabricEditorSession");
      if (token) headers = { "X-KFPS-Editor-Session": token };
    } catch (_) { /* The native host still records startup failures if storage is unavailable. */ }
    const recovery = { pendingRevision: 0, browserRevision: 0, serverRevision: 0, browserAt: 0, serverAt: 0 };
    const ids = new WeakMap(); let nextId = 0;
    function record(kind, fields = {}) {
      if (!enabled) return;
      if (events.length >= 48) { events.shift(); clientDrops++; }
      events.push({ kind, action: current, at: clock(), ...fields });
    }
    function resetPeriod() {
      period = { frames: 0, frameMax: 0, gaps50: 0, gaps100: 0, gaps250: 0, gaps500: 0, tasks: 0, taskMax: 0, renderMax: 0, renderCount: 0 };
    }
    resetPeriod();
    function attribute(from, to) {
      for (let index = timeline.length - 1; index >= 0; index--) {
        if (timeline[index].action !== "idle" && timeline[index].at <= to && (timeline[index + 1]?.at ?? Infinity) >= from) return timeline[index].action;
      }
      return "idle";
    }
    function transition(name) {
      timeline.push({ at: clock(), action: name });
      if (timeline.length > 64) timeline.shift();
    }
    function frame(now) {
      if (!enabled) return;
      if (doc.visibilityState === "visible" && lastFrame) {
        const delta = now - lastFrame;
        frames[cursor] = delta; cursor = (cursor + 1) % frames.length; count = Math.min(frames.length, count + 1);
        period.frames++; period.frameMax = Math.max(period.frameMax, delta);
        if (delta >= 50) period.gaps50++;
        if (delta >= 100) { period.gaps100++; totals.totalGaps100++; record("frame-stall", { duration: delta, action: attribute(lastFrame, now) }); }
        if (delta >= 250) period.gaps250++;
        if (delta >= 500) { period.gaps500++; totals.totalGaps500++; }
      }
      lastFrame = doc.visibilityState === "visible" ? now : 0;
      frameId = env.requestAnimationFrame(frame);
    }
    function longTasks(list) {
      if (!enabled || doc.visibilityState !== "visible") return;
      for (const entry of list.getEntries()) {
        period.tasks++; totals.totalTasks++; period.taskMax = Math.max(period.taskMax, entry.duration);
        record("long-task", { at: entry.startTime, duration: entry.duration, action: attribute(entry.startTime, entry.startTime + entry.duration) });
      }
    }
    function snapshot(activeSample = false) {
      const sorted = Array.from(frames.subarray(0, count)).sort((a, b) => a - b);
      let state = {};
      try { state = provider() || {}; } catch (_) { state = { ready: false }; }
      return { schema: 1, page, seq, metrics: { ...(activeSample || !lastSample.frames ? period : lastSample), ...totals, clientDrops,
        frameP50: sorted[Math.floor(sorted.length * .5)] || 0,
        frameP95: sorted[Math.floor(sorted.length * .95)] || 0,
        frameP99: sorted[Math.floor(sorted.length * .99)] || 0,
        ...(Number.isFinite(env.performance.memory?.usedJSHeapSize) ? {heapBytes: env.performance.memory.usedJSHeapSize} : {}) },
        state: { ...state, action: current, visible: doc.visibilityState === "visible", focused: doc.hasFocus() },
        recovery: { ...recovery }, events: events.slice(), logging: { ...logging }, transportOk };
    }
    async function flush() {
      if (!enabled || !headers || pending) return pending || false;
      if (clock() - lastRequestAt < 250) return false;
      lastRequestAt = clock();
      const data = snapshot(true), batch = events.splice(0);
      data.seq = ++seq; data.events = batch;
      delete data.logging; delete data.transportOk;
      const controller = new env.AbortController();
      const timeout = env.setTimeout(() => controller.abort(), 3000);
      lastSample = { ...period }; resetPeriod();
      pending = (async () => {
        try {
          const response = await env.fetch("/api/fabric-editor/diagnostics", { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(data), signal: controller.signal });
          if (!response.ok) throw new Error("diagnostics unavailable");
          const result = await response.json();
          logging = result.logging || {}; transportOk = true;
          return true;
        } catch (_) {
          transportOk = false;
          events.unshift(...batch);
          if (events.length > 48) { clientDrops += events.length - 48; events.splice(0, events.length - 48); }
          return false;
        } finally { env.clearTimeout(timeout); pending = null; }
      })();
      return pending;
    }
    function action(name, target) {
      if (!enabled || !ACTIONS.has(name) || current === name) return;
      current = name; startAt = clock();
      transition(name);
      const fields = {};
      if (target && typeof target === "object") {
        if (!ids.has(target)) ids.set(target, ++nextId);
        fields.selectedId = ids.get(target);
        fields.shapeType = Number(target.kloudy?.type) || 0;
      }
      record("action-start", fields);
    }
    function finish() {
      if (current !== "idle") record("action-end", { duration: clock() - startAt });
      if (current !== "idle") transition("idle");
      current = "idle";
    }
    function setEnabled(value) {
      enabled = Boolean(value); lastFrame = 0;
      env.cancelAnimationFrame(frameId);
      if (enabled) frameId = env.requestAnimationFrame(frame);
    }
    function pulse(name, target) {
      if (!enabled) return;
      action(name, target);
      env.clearTimeout(pulseTimer);
      const started = startAt;
      pulseTimer = env.setTimeout(() => { if (current === name && startAt === started) finish(); }, 180);
    }
    const timer = env.setInterval(() => { if (enabled) void flush(); }, 2000);
    if (env.PerformanceObserver?.supportedEntryTypes?.includes("longtask")) {
      observer = new env.PerformanceObserver(longTasks); observer.observe({ entryTypes: ["longtask"] });
    }
    doc.addEventListener("visibilitychange", () => { lastFrame = 0; finish(); void flush(); });
    env.addEventListener("blur", finish);
    env.addEventListener("error", event => record(event.error ? "js-error" : "resource-error", {
      error: errorClass(event.error), source: sourceName(event.filename || event.target?.src || ""), line: Number(event.lineno) || 0,
    }), true);
    env.addEventListener("unhandledrejection", event => record("rejection", { error: errorClass(event.reason) }));
    doc.addEventListener("pointerdown", event => {
      if (event.target?.tagName === "CANVAS") { finish(); action("pointer"); record("command", { buttons: event.buttons, modifiers: (event.ctrlKey ? 1 : 0) | (event.shiftKey ? 2 : 0) | (event.altKey ? 4 : 0) }); void flush(); }
    }, true);
    doc.addEventListener("pointerup", finish, true);
    doc.addEventListener("pointercancel", finish, true);
    doc.addEventListener("click", event => {
      const id = event.target?.closest?.("button")?.id;
      if (COMMANDS[id]) { action(COMMANDS[id]); record("command"); void flush(); env.setTimeout(finish, 0); }
    }, true);
    doc.addEventListener("keydown", event => {
      if (event.isComposing || event.repeat || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target?.tagName)) return;
      if (/^Arrow(Left|Right|Up|Down)$/.test(event.key)) record("command", { action: "nudge" });
    }, true);
    record("page-start"); frameId = env.requestAnimationFrame(frame); void flush();
    return {
      record, action, pulse, finish, snapshot, flush, setEnabled,
      configure(options) { headers = options.headers; provider = options.state || provider; void flush(); },
      recovery(revision, browserOk, serverOk) {
        if (browserOk && revision >= recovery.browserRevision) { recovery.browserRevision = revision; recovery.browserAt = Date.now(); }
        if (serverOk && revision >= recovery.serverRevision) { recovery.serverRevision = revision; recovery.serverAt = Date.now(); }
        record("recovery-result", { revision, browserOk: Boolean(browserOk), serverOk: Boolean(serverOk) });
      },
      queued(revision) { recovery.pendingRevision = revision; },
      bindCanvas(canvas) {
        for (const [event, name] of Object.entries({ "object:moving": "move", "object:scaling": "scale", "object:skewing": "skew", "object:rotating": "rotate" })) canvas.on(event, info => action(name, info.target));
        canvas.on("object:modified", () => { record("edit"); finish(); });
        canvas.on("before:render", () => { renderStart = clock(); });
        canvas.on("after:render", () => { if (enabled) { period.renderCount++; totals.totalDraws++; period.renderMax = Math.max(period.renderMax, clock() - renderStart); } });
        for (const element of [canvas.lowerCanvasEl, canvas.upperCanvasEl]) {
          element.addEventListener("contextlost", () => record("canvas-lost"));
          element.addEventListener("contextrestored", () => record("canvas-restored"));
        }
      },
      dispose() { setEnabled(false); env.clearTimeout(pulseTimer); env.clearInterval(timer); observer?.disconnect(); },
    };
  }
  if (typeof module === "object" && module.exports) module.exports = { create, errorClass, sourceName };
  else root.KfpsEditorDiagnostics = create(root);
})(typeof window === "object" ? window : globalThis);
