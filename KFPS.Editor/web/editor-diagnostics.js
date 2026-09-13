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
  const ERRORS = new Set("js-error rejection resource-error console-error webgl-lost canvas-lost renderer-stopped native-failed close-timeout".split(" "));
  const MAX_BACKLOG = 1024, MAX_BATCH = 48, MAX_PACKET_BYTES = 24 * 1024, MIN_SEND_MS = 250;
  function priority(event) {
    if (ERRORS.has(event.kind) || event.state === "failed" || event.kind === "recovery-result" && !event.browserOk && !event.serverOk) return 3;
    if (["edit", "commit", "checkpoint", "recovery-result"].includes(event.kind) || ["committed", "finished", "cancelled"].includes(event.state)) return 2;
    return 1;
  }
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
    let provider = () => ({}), headers = null, enabled = true, current = "idle", startAt = 0, clientDrops = 0, criticalDrops = 0;
    let logging = {}, transportOk = false, renderStart = null, observer = null, lastRequestAt = -Infinity, pulseTimer = 0;
    let disposed = false, commandTimer = 0, transportTimer = 0, controller = null, boundCanvas = null;
    let drainTimer = 0, retryAt = 0, batch = null;
    const cleanup = [], canvasCleanup = [];
    const pendingPaint = new Map();
    function listen(target, event, handler, capture = false, owners = cleanup) {
      target.addEventListener(event, handler, capture);
      owners.push(() => target.removeEventListener(event, handler, capture));
    }
    try {
      const token = new URLSearchParams((env.location.hash || "").replace(/^#/, "")).get("session") || env.sessionStorage.getItem("kfpsFabricEditorSession");
      if (token) headers = { "X-KFPS-Editor-Session": token };
    } catch (_) { /* The native host still records startup failures if storage is unavailable. */ }
    const recovery = { pendingRevision: 0, browserRevision: 0, serverRevision: 0, browserAt: 0, serverAt: 0 };
    const ids = new WeakMap(); let nextId = 0;
    let gestures = new WeakMap(), nextInputId = 0, inputId = 0;
    function enqueue(item) {
      if (events.length >= MAX_BACKLOG) {
        let index = 0;
        for (let i = 1; i < events.length; i++) if (priority(events[i]) < priority(events[index])) index = i;
        const discard = priority(item) < priority(events[index]) ? item : events.splice(index, 1)[0];
        clientDrops++;
        if (priority(discard) > 1) criticalDrops++;
        if (discard === item) return;
      }
      events.push(item);
    }
    function scheduleFlush(delay = 50) {
      if (disposed || !enabled || !headers || pending || drainTimer) return;
      drainTimer = env.setTimeout(() => { drainTimer = 0; void flush(); },
        Math.max(delay, retryAt - clock(), MIN_SEND_MS - (clock() - lastRequestAt)));
    }
    function record(kind, fields = {}) {
      if (!enabled || disposed) return;
      const item = { kind, action: current, at: clock(), ...fields };
      enqueue(item);
      if (events.length >= 24 || priority(item) > 1) scheduleFlush();
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
      return { schema: 1, page, seq, metrics: { ...(activeSample || !lastSample.frames ? period : lastSample), ...totals, clientDrops, criticalDrops, queueDepth: events.length + (batch?.count || 0),
        frameP50: sorted[Math.floor(sorted.length * .5)] || 0,
        frameP95: sorted[Math.floor(sorted.length * .95)] || 0,
        frameP99: sorted[Math.floor(sorted.length * .99)] || 0,
        ...(Number.isFinite(env.performance.memory?.usedJSHeapSize) ? {heapBytes: env.performance.memory.usedJSHeapSize} : {}) },
        state: { ...state, action: current, visible: doc.visibilityState === "visible", focused: doc.hasFocus() },
        recovery: { ...recovery }, events: events.slice(0, MAX_BATCH), logging: { ...logging }, transportOk };
    }
    function prepareBatch() {
      const data = snapshot(true), encoder = new TextEncoder();
      data.seq = seq + 1; data.events = [];
      delete data.logging; delete data.transportOk;
      const base = encoder.encode(JSON.stringify(data)).byteLength;
      if (base > MAX_PACKET_BYTES) throw new Error("diagnostic state too large");
      let bytes = base;
      while (events.length && data.events.length < MAX_BATCH) {
        const item = events[0]; let size;
        try { size = encoder.encode(JSON.stringify(item)).byteLength; }
        catch (_) { size = MAX_PACKET_BYTES; }
        if (base + size > MAX_PACKET_BYTES) {
          events.shift(); clientDrops++; if (priority(item) > 1) criticalDrops++;
          continue;
        }
        if (bytes + size + (data.events.length ? 1 : 0) > MAX_PACKET_BYTES) break;
        bytes += size + (data.events.length ? 1 : 0);
        data.events.push(events.shift());
      }
      // Retries keep these exact bytes/sequence until the native queue accepts them.
      batch = { body: JSON.stringify(data), count: data.events.length };
      seq = data.seq; lastSample = { ...period }; resetPeriod();
    }
    async function flush(closing = false) {
      if (!enabled || disposed || !headers || pending) return pending || false;
      if (!closing && (clock() - lastRequestAt < MIN_SEND_MS || clock() < retryAt)) { scheduleFlush(); return false; }
      env.clearTimeout(drainTimer); drainTimer = 0;
      lastRequestAt = clock();
      try { if (!batch) prepareBatch(); }
      catch (_) { transportOk = false; retryAt = clock() + 2000; scheduleFlush(); return false; }
      controller = new env.AbortController();
      const requestController = controller;
      transportTimer = env.setTimeout(() => requestController.abort(), 3000);
      pending = Promise.resolve().then(async () => {
        try {
          if (disposed) return false;
          const response = await env.fetch("/api/fabric-editor/diagnostics", { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: batch.body, signal: requestController.signal });
          if (!response.ok) throw new Error("diagnostics unavailable");
          const result = await response.json();
          if (disposed) return false;
          logging = result.logging || {}; transportOk = true; batch = null; retryAt = 0;
          return true;
        } catch (_) {
          transportOk = false;
          retryAt = clock() + 2000;
          return false;
        } finally {
          env.clearTimeout(transportTimer); controller = null; pending = null;
          if (batch || events.length) scheduleFlush();
        }
      });
      return pending;
    }
    async function drain() {
      const deadline = clock() + 2000;
      const timeout = env.setTimeout(() => controller?.abort(), 2000);
      try {
        for (let count = 0; count < 24; count++) {
          if (!await flush(true)) return false;
          if (!batch && !events.length) return true;
          if (clock() >= deadline) break;
        }
        return false;
      } finally { env.clearTimeout(timeout); }
    }
    function action(name, target) {
      if (!enabled || !ACTIONS.has(name) || current === name) return;
      current = name; startAt = clock();
      inputId = ++nextInputId;
      transition(name);
      const fields = { inputId };
      if (target && typeof target === "object") {
        if (!ids.has(target)) ids.set(target, ++nextId);
        fields.selectedId = ids.get(target);
        fields.shapeType = Number(target.kloudy?.type) || 0;
      }
      record("action-start", fields);
    }
    function finish() {
      if (current !== "idle") record("action-end", { inputId, duration: clock() - startAt });
      if (current !== "idle") transition("idle");
      current = "idle";
    }
    function setEnabled(value) {
      enabled = !disposed && Boolean(value); lastFrame = 0; renderStart = null;
      pendingPaint.clear();
      gestures = new WeakMap();
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
    listen(doc, "visibilitychange", () => { lastFrame = 0; finish(); void flush(); });
    listen(env, "blur", finish);
    listen(env, "error", event => record(event.error ? "js-error" : "resource-error", {
      error: errorClass(event.error), source: sourceName(event.filename || event.target?.src || ""), line: Number(event.lineno) || 0,
    }), true);
    listen(env, "unhandledrejection", event => record("rejection", { error: errorClass(event.reason) }));
    listen(doc, "pointerdown", event => {
      if (event.target?.tagName === "CANVAS") { gestures = new WeakMap(); finish(); action("pointer"); record("command", { buttons: event.buttons, modifiers: (event.ctrlKey ? 1 : 0) | (event.shiftKey ? 2 : 0) | (event.altKey ? 4 : 0) }); void flush(); }
    }, true);
    listen(doc, "pointerup", finish, true);
    listen(doc, "pointercancel", () => { gestures = new WeakMap(); finish(); }, true);
    listen(doc, "click", event => {
      const id = event.target?.closest?.("button")?.id;
      if (COMMANDS[id]) { action(COMMANDS[id]); record("command"); void flush(); env.clearTimeout(commandTimer); commandTimer = env.setTimeout(finish, 0); }
    }, true);
    listen(doc, "keydown", event => {
      if (event.key === "Escape") gestures = new WeakMap();
      if (event.isComposing || event.repeat || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target?.tagName)) return;
      if (/^Arrow(Left|Right|Up|Down)$/.test(event.key)) record("command", { action: "nudge" });
    }, true);
    record("page-start"); frameId = env.requestAnimationFrame(frame); void flush();
    return {
      record, action, pulse, finish, snapshot, flush, drain, setEnabled,
      pageId: page,
      awaitPaint(phase, cause) {
        if (!enabled || disposed || !["document-paint", "settled-paint"].includes(phase)) return;
        pendingPaint.set(phase, { cause, started: clock() });
      },
      configure(options) { headers = options.headers; provider = options.state || provider; void flush(); },
      recovery(revision, browserOk, serverOk, cause = null, errorCode = "") {
        if (browserOk && revision >= recovery.browserRevision) { recovery.browserRevision = revision; recovery.browserAt = Date.now(); }
        if (serverOk && revision >= recovery.serverRevision) { recovery.serverRevision = revision; recovery.serverAt = Date.now(); }
        record("recovery-result", { ...cause, revision, browserOk: Boolean(browserOk), serverOk: Boolean(serverOk), errorCode });
      },
      queued(revision) { recovery.pendingRevision = revision; },
      bindCanvas(canvas) {
        if (disposed || boundCanvas === canvas) return;
        canvasCleanup.splice(0).forEach(remove => remove());
        boundCanvas = canvas; renderStart = null; pendingPaint.clear();
        const bind = (event, handler) => { canvas.on(event, handler); canvasCleanup.push(() => canvas.off(event, handler)); };
        for (const [event, name] of Object.entries({ "object:moving": "move", "object:scaling": "scale", "object:skewing": "skew", "object:rotating": "rotate" })) bind(event, info => {
          action(name, info.target);
          if (enabled && info.target) gestures.set(info.target, inputId);
        });
        bind("object:modified", info => {
          const gesture = info?.target ? gestures.get(info.target) || 0 : 0;
          if (info?.target) gestures.delete(info.target);
          if (info) info.kfpsDiagnosticInputId = gesture;
          record("edit", { inputId: gesture }); finish();
        });
        bind("before:render", info => { renderStart = enabled && info?.ctx === canvas.contextContainer ? clock() : null; });
        bind("after:render", info => {
          // Fabric renderTop emits after:render without a paired full-canvas draw.
          if (!enabled || renderStart === null || info?.ctx !== canvas.contextContainer) return;
          const duration = clock() - renderStart; renderStart = null;
          period.renderCount++; totals.totalDraws++; period.renderMax = Math.max(period.renderMax, duration);
          for (const [phase, pending] of pendingPaint) {
            record("phase", { ...pending.cause, phase, duration: clock() - pending.started, renderDuration: duration, state: "finished" });
          }
          pendingPaint.clear();
        });
        for (const element of [canvas.lowerCanvasEl, canvas.upperCanvasEl]) {
          listen(element, "contextlost", () => record("canvas-lost"), false, canvasCleanup);
          listen(element, "contextrestored", () => record("canvas-restored"), false, canvasCleanup);
        }
      },
      dispose() {
        if (disposed) return;
        disposed = true; setEnabled(false); controller?.abort();
        env.clearTimeout(pulseTimer); env.clearTimeout(commandTimer); env.clearTimeout(transportTimer);
        env.clearTimeout(drainTimer); drainTimer = 0; batch = null; events.length = 0;
        env.clearInterval(timer); observer?.disconnect();
        cleanup.splice(0).forEach(remove => remove()); canvasCleanup.splice(0).forEach(remove => remove());
        boundCanvas = null; provider = () => ({});
      },
    };
  }
  if (typeof module === "object" && module.exports) module.exports = { create, errorClass, sourceName };
  else root.KfpsEditorDiagnostics = create(root);
})(typeof window === "object" ? window : globalThis);
