(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorCatalog = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ VINYL_TYPE_BASES, VINYL_RESOURCE_BASES, format, KfpsI18n,
    fetcher = (...args) => fetch(...args), requestTimeoutMs = 30000 }) {
    const resourceCache = new Map();
    const resourcePathPromiseCache = new Map();
    const resourceOutlineCache = new Map();
    const resourcePayloadCache = new Map();
    const resourcePayloadPromiseCache = new Map();
    const requests = new Set();
    const payloads = Object.freeze({
      get: key => resourcePayloadCache.get(key), has: key => resourcePayloadCache.has(key),
    });
    let shapeNames = { families: {} };
    let shapeWords = { families: {} };
    let resolvedResourceBase = null;
    let metadataPending = null;
    let disposed = false;

    function ensureOpen() {
      if (disposed) throw new DOMException("The operation was aborted.", "AbortError");
    }

    async function request(url, consume, timeoutMs = requestTimeoutMs, group = null) {
      ensureOpen();
      const controller = new AbortController();
      requests.add(controller);
      group?.add(controller);
      let timer, onAbort;
      const aborted = new Promise((_, reject) => {
        onAbort = () => reject(controller.signal.reason);
        controller.signal.addEventListener("abort", onAbort, { once: true });
        timer = setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), timeoutMs);
      });
      try {
        return await Promise.race([aborted, (async () => {
          const response = await fetcher(url, { cache: "force-cache", signal: controller.signal });
          try {
            controller.signal.throwIfAborted();
            const result = await consume(response);
            controller.signal.throwIfAborted();
            ensureOpen();
            return result;
          } finally {
            if (!response.bodyUsed) response.body?.cancel().catch(() => {});
          }
        })()]);
      } finally {
        clearTimeout(timer);
        controller.signal.removeEventListener("abort", onAbort);
        requests.delete(controller);
        group?.delete(controller);
      }
    }

    async function loadMetadata() {
      ensureOpen();
      if (metadataPending) return metadataPending;
      const pending = (async () => {
        const group = new Set();
        const read = stem => request(`/tools/fabric-editor/${stem}.json`, response => {
          if (!response.ok) throw new Error(stem === "shape-names"
            ? KfpsI18n.t("shape-names HTTP {0}", response.status)
            : KfpsI18n.t("shape-words HTTP {0}", response.status));
          return response.json();
        }, requestTimeoutMs, group);
        let names, words;
        try { [names, words] = await Promise.all([read("shape-names"), read("shape-words")]); }
        finally { for (const controller of group) controller.abort(); }
        for (const data of [names, words]) {
          if (!data || typeof data.families !== "object" || !data.families || Array.isArray(data.families)
              || Object.values(data.families).some(family => !family || typeof family !== "object" || Array.isArray(family))) {
            throw new Error(KfpsI18n.t("Shape metadata unavailable."));
          }
        }
        ensureOpen();
        shapeNames = names;
        shapeWords = words;
      })();
      metadataPending = pending;
      try { await pending; }
      finally { if (metadataPending === pending) metadataPending = null; }
    }

    function dispose() {
      if (disposed) return;
      disposed = true;
      for (const controller of requests) controller.abort();
      for (const cache of [resourceCache, resourcePathPromiseCache, resourceOutlineCache, resourcePayloadCache, resourcePayloadPromiseCache]) cache.clear();
    }
    function resourceCountForFamilyDefinition(family) {
      return 40;
    }

    function resolvedResourceFromFullTypeCode(typeCode) {
      const fullCode = Number(typeCode);
      if (!Number.isFinite(fullCode) || fullCode <= 1000000) return null;
      for (const [family, base] of Object.entries(VINYL_TYPE_BASES)) {
        const delta = fullCode - Number(base);
        if (delta >= 0 && delta < resourceCountForFamilyDefinition(family)) {
          const shapeWord = fullCode & 0xffff;
          return { family, index: delta + 1, typeCode: fullCode, shapeWord };
        }
      }
      return null;
    }

    function resolvedResourceFromShapeWord(wordValue) {
      const word = Number(wordValue) & 0xffff;
      for (const [family, base] of Object.entries(VINYL_TYPE_BASES)) {
        const baseWord = Number(base) & 0xffff;
        const delta = word - baseWord;
        if (delta >= 0 && delta < resourceCountForFamilyDefinition(family)) {
          return { family, index: delta + 1, typeCode: 0x100000 + word, shapeWord: word };
        }
      }
      return null;
    }

    function typeCodeToResource(typeCode) {
      const fullResource = resolvedResourceFromFullTypeCode(typeCode);
      if (fullResource) return fullResource;
      const word = Number(typeCode) & 0xffff;
      const compactResource = resolvedResourceFromShapeWord(word);
      if (compactResource) return compactResource;
      const explicit = shapeWords?.families || {};
      for (const [family, values] of Object.entries(explicit)) {
        for (const [index, shapeWord] of Object.entries(values || {})) {
          if ((Number(shapeWord) & 0xffff) === word) {
            return { family, index: Number(index), typeCode: 0x100000 + word, shapeWord: word };
          }
        }
      }
      return null;
    }

    function resourceToTypeCode(family, index) {
      return 0x100000 + resourceToShapeWord(family, index);
    }

    function resourceToShapeWord(family, index) {
      if (family === "Primitives") return (100 + Number(index)) & 0xffff;
      const base = VINYL_TYPE_BASES[family];
      if (!base) throw new Error(KfpsI18n.t("Unknown shape family: {0}", family));
      if (family.includes("Letters")) return (base + Number(index) - 1) & 0xffff;
      return ((base & 0xffff) + Number(index) - 1) & 0xffff;
    }

    async function loadResourcePath(typeCode) {
      const resolved = typeCodeToResource(typeCode);
      if (!resolved) throw new Error(KfpsI18n.t("Unsupported FH6 type code: {0}", typeCode));
      return loadResourcePathForResolved(resolved);
    }

    async function loadResourcePathForResolved(resolved) {
      ensureOpen();
      const cacheKey = resourceCacheKey(resolved);
      if (resourceCache.has(cacheKey)) return resourceCache.get(cacheKey);
      if (resourcePathPromiseCache.has(cacheKey)) return resourcePathPromiseCache.get(cacheKey);
      const pending = (async () => {
        const payload = await loadResourcePayloadForResolved(resolved);
        ensureOpen();
        const vertices = payload.Vertices || [];
        const indices = payload.Indices || [];
        const chunks = [];
        for (let i = 0; i + 2 < indices.length; i += 3) {
          const p0 = vertices[indices[i]];
          const p1 = vertices[indices[i + 1]];
          const p2 = vertices[indices[i + 2]];
          if (!p0 || !p1 || !p2) continue;
          chunks.push(`M ${format(p0.X)} ${format(p0.Y)} L ${format(p1.X)} ${format(p1.Y)} L ${format(p2.X)} ${format(p2.Y)} Z`);
        }
        const d = chunks.join(" ");
        resourceCache.set(cacheKey, d);
        return d;
      })();
      resourcePathPromiseCache.set(cacheKey, pending);
      try {
        return await pending;
      } finally {
        resourcePathPromiseCache.delete(cacheKey);
      }
    }

    function resourceCacheKey(resolved) {
      return `${resolved.family}:${resolved.index}:${resolved.typeCode || ""}`;
    }

    async function loadResourcePayloadForResolved(resolved) {
      ensureOpen();
      const cacheKey = resourceCacheKey(resolved);
      if (resourcePayloadCache.has(cacheKey)) return resourcePayloadCache.get(cacheKey);
      if (resourcePayloadPromiseCache.has(cacheKey)) return resourcePayloadPromiseCache.get(cacheKey);
      const pending = (async () => {
        const { payload } = await fetchResource(resolved.family, resolved.index, "", true);
        ensureOpen();
        resourcePayloadCache.set(cacheKey, payload);
        return payload;
      })();
      resourcePayloadPromiseCache.set(cacheKey, pending);
      try {
        return await pending;
      } finally {
        resourcePayloadPromiseCache.delete(cacheKey);
      }
    }

    function edgeKey(a, b) {
      return a < b ? `${a}:${b}` : `${b}:${a}`;
    }

    async function loadResourceOutlinePathForResolved(resolved) {
      ensureOpen();
      const cacheKey = resourceCacheKey(resolved);
      if (resourceOutlineCache.has(cacheKey)) return resourceOutlineCache.get(cacheKey);
      const payload = await loadResourcePayloadForResolved(resolved);
      ensureOpen();
      const vertices = payload.Vertices || [];
      const indices = payload.Indices || [];
      const edges = new Map();
      for (let i = 0; i + 2 < indices.length; i += 3) {
        const tri = [indices[i], indices[i + 1], indices[i + 2]];
        for (const [a, b] of [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]]) {
          if (!vertices[a] || !vertices[b]) continue;
          const key = edgeKey(a, b);
          const current = edges.get(key);
          if (current) current.count += 1;
          else edges.set(key, { a, b, count: 1 });
        }
      }
      const chunks = [];
      edges.forEach((edge) => {
        if (edge.count !== 1) return;
        const p0 = vertices[edge.a];
        const p1 = vertices[edge.b];
        chunks.push(`M ${format(p0.X)} ${format(p0.Y)} L ${format(p1.X)} ${format(p1.Y)}`);
      });
      const d = chunks.join(" ");
      resourceOutlineCache.set(cacheKey, d);
      return d;
    }

    async function fetchResource(family, index, suffix, json) {
      ensureOpen();
      const orderedBases = resolvedResourceBase
        ? [resolvedResourceBase, ...VINYL_RESOURCE_BASES.filter((base) => base !== resolvedResourceBase)]
        : VINYL_RESOURCE_BASES;
      let lastUrl = "";
      for (const base of orderedBases) {
        const url = `${base}/${family}/${index}${suffix}`;
        lastUrl = url;
        try {
          const result = await request(url, async response => ({
            ok: response.ok, payload: response.ok && json ? await response.json() : undefined,
          }), json ? requestTimeoutMs : Math.min(15000, requestTimeoutMs));
          if (result.ok) {
            ensureOpen();
            resolvedResourceBase = base;
            return { url, payload: result.payload };
          }
        } catch (error) {
          ensureOpen();
          if (error instanceof SyntaxError) throw error;
          // A failed location may have an installed fallback; disposal may not.
        }
      }
      if (json) throw new Error(KfpsI18n.t("Missing shape resource: {0}", lastUrl));
      return { url: lastUrl };
    }

    async function resolveVinylResourceUrl(family, index, suffix = "") {
      return (await fetchResource(family, index, suffix, false)).url;
    }

    function vinylResourceUrl(family, index, suffix = "") {
      const base = resolvedResourceBase || VINYL_RESOURCE_BASES[0];
      return `${base}/${family}/${index}${suffix}`;
    }

    function shapeDisplayName(family, index) {
      const familyLabel = family.replaceAll("_", " ");
      let word;
      try {
        word = resourceToShapeWord(family, index);
      } catch (_err) {
        word = shapeWords?.families?.[family]?.[String(index)];
      }
      const suffix = word !== undefined ? ` / word ${word}` : "";
      if (family === "Primitives" || family.includes("Letters")) {
        return shapeNames?.families?.[family]?.[String(index)] || `${familyLabel} slot ${index}${suffix}`;
      }
      return `${familyLabel} slot ${index}${suffix}`;
    }

    function shapeCountForFamily(family) {
      const named = shapeNames?.families?.[family];
      if (named && Object.keys(named).length) {
        return Math.max(
          resourceCountForFamilyDefinition(family),
          ...Object.keys(named).map((key) => Number(key) || 0),
        );
      }
      return resourceCountForFamilyDefinition(family);
    }
    return {
      loadMetadata,
      dispose,
      typeCodeToResource,
      resourceToTypeCode,
      resourceToShapeWord,
      loadResourcePath,
      loadResourcePathForResolved,
      resourceCacheKey,
      loadResourcePayloadForResolved,
      loadResourceOutlinePathForResolved,
      resolveVinylResourceUrl,
      vinylResourceUrl,
      shapeDisplayName,
      shapeCountForFamily,
      get names() { return shapeNames; },
      get words() { return shapeWords; },
      payloads,
    };
  }
  return { create };
});
