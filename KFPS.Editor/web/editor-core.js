(function installKfpsEditorCore(global) {
  "use strict";

  class OrderedObjectRegistry {
    constructor(predicate) {
      this.predicate = typeof predicate === "function" ? predicate : () => true;
      this.dirty = true;
      this.source = null;
      this.sourceLength = -1;
      this.objects = [];
      this.indexes = new Map();
    }

    invalidate() {
      this.dirty = true;
    }

    read(source) {
      const nextSource = Array.isArray(source) ? source : [];
      if (!this.dirty && this.sourceLength === nextSource.length) {
        // Fabric's public getObjects() returns a fresh array. Compare its order
        // before rebuilding the filtered list and index map on every lookup.
        let unchanged = this.source === nextSource;
        if (!unchanged && this.source) {
          unchanged = true;
          for (let index = 0; index < nextSource.length; index++) {
            if (this.source[index] !== nextSource[index]) { unchanged = false; break; }
          }
        }
        if (unchanged) return this.objects;
      }
      this.source = nextSource;
      this.sourceLength = nextSource.length;
      this.objects = nextSource.filter(this.predicate);
      this.indexes = new Map(this.objects.map((object, index) => [object, index]));
      this.dirty = false;
      return this.objects;
    }

    indexOf(object, source) {
      this.read(source);
      return this.indexes.get(object) ?? -1;
    }
  }

  async function mapWithConcurrency(items, concurrency, worker, options = {}) {
    const source = Array.from(items || []);
    if (!source.length) return [];
    const results = new Array(source.length);
    const workerCount = Math.max(1, Math.min(source.length, Math.floor(Number(concurrency)) || 1));
    let cursor = 0;
    let firstError = null;
    const now = () => global.performance?.now?.() ?? Date.now();
    let sliceStarted = now();
    let yielding = null;
    const runners = Array.from({ length: workerCount }, async () => {
      while (cursor < source.length && !firstError) {
        const index = cursor;
        cursor += 1;
        try {
          results[index] = await worker(source[index], index, source);
          if (options.yield && now() - sliceStarted >= (options.yieldAfterMs ?? 8)) {
            yielding ||= Promise.resolve().then(options.yield).finally(() => { sliceStarted = now(); yielding = null; });
            await yielding;
          }
        } catch (error) {
          firstError ||= error;
        }
      }
    });
    await Promise.all(runners);
    if (firstError) throw firstError;
    return results;
  }

  function buildVirtualLayout(entries, defaultHeight = 56) {
    let offset = 0;
    const normalized = Array.from(entries || []);
    normalized.forEach((entry, index) => {
      const height = Math.max(1, Number(entry?.height) || defaultHeight);
      entry.virtualIndex = index;
      entry.virtualTop = offset;
      entry.virtualHeight = height;
      offset += height;
    });
    return { entries: normalized, totalHeight: offset };
  }

  function firstEntryEndingAfter(entries, target) {
    let low = 0;
    let high = entries.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      const entry = entries[middle];
      if ((entry.virtualTop + entry.virtualHeight) <= target) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  function virtualRange(layout, scrollTop, viewportHeight, overscan = 240) {
    const entries = layout?.entries || [];
    const totalHeight = Math.max(0, Number(layout?.totalHeight) || 0);
    if (!entries.length) {
      return { start: 0, end: 0, padTop: 0, padBottom: 0, totalHeight };
    }
    const startPixel = Math.max(0, (Number(scrollTop) || 0) - Math.max(0, Number(overscan) || 0));
    const endPixel = Math.min(
      totalHeight,
      (Number(scrollTop) || 0) + Math.max(0, Number(viewportHeight) || 0) + Math.max(0, Number(overscan) || 0),
    );
    const start = Math.min(entries.length, firstEntryEndingAfter(entries, startPixel));
    let end = start;
    while (end < entries.length && entries[end].virtualTop < endPixel) end += 1;
    const padTop = start < entries.length ? entries[start].virtualTop : totalHeight;
    const renderedBottom = end > start
      ? entries[end - 1].virtualTop + entries[end - 1].virtualHeight
      : padTop;
    return {
      start,
      end,
      padTop,
      padBottom: Math.max(0, totalHeight - renderedBottom),
      totalHeight,
    };
  }

  function alignmentDelta(bounds, target, mode) {
    const source = bounds || {};
    const destination = target || {};
    const sourceCenterX = Number.isFinite(source.centerX)
      ? source.centerX
      : (Number(source.left) + Number(source.right)) / 2;
    const sourceCenterY = Number.isFinite(source.centerY)
      ? source.centerY
      : (Number(source.top) + Number(source.bottom)) / 2;
    const targetCenterX = Number.isFinite(destination.centerX)
      ? destination.centerX
      : (Number(destination.left) + Number(destination.right)) / 2;
    const targetCenterY = Number.isFinite(destination.centerY)
      ? destination.centerY
      : (Number(destination.top) + Number(destination.bottom)) / 2;
    if (mode === "left") return { x: Number(destination.left) - Number(source.left), y: 0 };
    if (mode === "centerX") return { x: targetCenterX - sourceCenterX, y: 0 };
    if (mode === "right") return { x: Number(destination.right) - Number(source.right), y: 0 };
    if (mode === "top") return { x: 0, y: Number(destination.top) - Number(source.top) };
    if (mode === "centerY") return { x: 0, y: targetCenterY - sourceCenterY };
    if (mode === "bottom") return { x: 0, y: Number(destination.bottom) - Number(source.bottom) };
    return { x: 0, y: 0 };
  }

  function distributionDeltas(values) {
    const centers = Array.from(values || [], Number);
    if (centers.length < 3 || centers.some((value) => !Number.isFinite(value))) {
      return centers.map(() => 0);
    }
    const step = (centers[centers.length - 1] - centers[0]) / (centers.length - 1);
    return centers.map((value, index) => (
      index === 0 || index === centers.length - 1
        ? 0
        : centers[0] + step * index - value
    ));
  }

  function parseNumericExpression(value) {
    const text = String(value ?? "").trim();
    if (!text || text.length > 256) throw new Error("Enter a number or arithmetic expression.");
    let at = 0, tokens = 0;
    const space = () => { while (/\s/.test(text[at] || "") && at < text.length) at++; };
    const finite = number => {
      if (!Number.isFinite(number) || Math.abs(number) > 1e9) throw new Error("The result must be finite and between -1,000,000,000 and 1,000,000,000.");
      return number;
    };
    function primary(depth) {
      space();
      if (++tokens > 128 || depth > 16) throw new Error("The expression is too complex.");
      let number;
      if (text[at] === "+" || text[at] === "-") {
        const negative = text[at++] === "-";
        return finite((negative ? -1 : 1) * primary(depth + 1));
      }
      if (text[at] === "(") {
        at++;
        number = sum(depth + 1);
        space();
        if (text[at++] !== ")") throw new Error("Close the parentheses.");
      } else {
        const match = /^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?/i.exec(text.slice(at));
        if (!match) throw new Error("Use numbers, parentheses and + - * / operators.");
        at += match[0].length;
        number = finite(Number(match[0]));
      }
      space();
      if (text[at] === "%") { at++; number /= 100; }
      return finite(number);
    }
    function product(depth) {
      let number = primary(depth);
      space();
      while (text[at] === "*" || text[at] === "/") {
        const operator = text[at++];
        const right = primary(depth);
        if (operator === "/" && right === 0) throw new Error("Division by zero is not allowed.");
        number = finite(operator === "*" ? number * right : number / right);
        space();
      }
      return number;
    }
    function sum(depth) {
      let number = product(depth);
      space();
      while (text[at] === "+" || text[at] === "-") {
        const operator = text[at++];
        const right = product(depth);
        number = finite(operator === "+" ? number + right : number - right);
        space();
      }
      return number;
    }
    const result = sum(0);
    space();
    if (at !== text.length) throw new Error("The expression contains an unsupported value.");
    return result;
  }

  function orderByStack(objects, stack) {
    if (objects.length < 2) return objects.slice();
    const positions = new Map(stack.map((object, index) => [object, index]));
    return objects.slice().sort((left, right) => (positions.get(left) ?? -1) - (positions.get(right) ?? -1));
  }

  global.KfpsEditorCore = Object.freeze({
    orderByStack,
    parseNumericExpression,
    alignmentDelta,
    distributionDeltas,
    OrderedObjectRegistry,
    buildVirtualLayout,
    mapWithConcurrency,
    virtualRange,
  });
}(globalThis));
