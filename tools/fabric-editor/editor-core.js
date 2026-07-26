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
      if (!this.dirty && this.source === nextSource && this.sourceLength === nextSource.length) {
        return this.objects;
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

  async function mapWithConcurrency(items, concurrency, worker) {
    const source = Array.from(items || []);
    if (!source.length) return [];
    const results = new Array(source.length);
    const workerCount = Math.max(1, Math.min(source.length, Math.floor(Number(concurrency)) || 1));
    let cursor = 0;
    let firstError = null;
    const runners = Array.from({ length: workerCount }, async () => {
      while (cursor < source.length && !firstError) {
        const index = cursor;
        cursor += 1;
        try {
          results[index] = await worker(source[index], index, source);
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

  global.KfpsEditorCore = Object.freeze({
    alignmentDelta,
    distributionDeltas,
    OrderedObjectRegistry,
    buildVirtualLayout,
    mapWithConcurrency,
    virtualRange,
  });
}(globalThis));
