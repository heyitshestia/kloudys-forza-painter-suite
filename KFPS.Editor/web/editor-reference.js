(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorReference = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ scene, session, view, persistence, changed, maxReferenceBytes, fabric, KfpsI18n, round }) {
    let overlayLoadGeneration = 0;
    let overlayRefreshGeneration = 0;
    let overlayImage = null;
    let overlaySampler = null;
    let layeredOverlayState = null;
    let overlaySourceState = null;
    let unavailableSourceOverlayState = null;
    let disposed = false;
    let pendingImageCancel = null;
    let pendingRefreshCancel = null;
    let pendingReader = null;

    function cancelLoads() {
      overlayLoadGeneration++;
      overlayRefreshGeneration++;
      if (pendingReader) {
        const reader = pendingReader;
        pendingReader = null;
        reader.onload = reader.onerror = reader.onloadend = null;
        if (reader.readyState === 1) reader.abort();
      }
      pendingImageCancel?.();
      pendingRefreshCancel?.();
    }

    function displayFailed(error) {
      try { view.failed(error); } catch (_) {}
    }

    function rebuildOverlaySampler(img) {
      const width = img.naturalWidth || img.width || 1;
      const height = img.naturalHeight || img.height || 1;
      releaseOverlaySampler();
      overlaySampler = { width, height, source: img, tiles: new Map(), canvas: null };
    }

    function releaseOverlaySampler() {
      if (overlaySampler?.canvas) overlaySampler.canvas.width = overlaySampler.canvas.height = 1;
      overlaySampler?.tiles.clear();
      overlaySampler = null;
    }

    function readOverlayPixel(x, y) {
      const sampler = overlaySampler;
      if (!sampler || x < 0 || y < 0 || x >= sampler.width || y >= sampler.height) return null;
      const tileSize = 256;
      const left = Math.floor(x / tileSize) * tileSize;
      const top = Math.floor(y / tileSize) * tileSize;
      const key = `${left}:${top}`;
      let tile = sampler.tiles.get(key);
      if (tile) sampler.tiles.delete(key);
      else {
        // Exact source pixels, allocated only when sampled. Keep at most 8 MiB of
        // decoded tiles instead of a second full-resolution RGBA reference image.
        const surface = sampler.canvas || (sampler.canvas = document.createElement("canvas"));
        const width = Math.min(tileSize, sampler.width - left);
        const height = Math.min(tileSize, sampler.height - top);
        surface.width = width; surface.height = height;
        const context = surface.getContext("2d", { willReadFrequently: true });
        context.drawImage(sampler.source, left, top, width, height, 0, 0, width, height);
        tile = { width, data: context.getImageData(0, 0, width, height).data };
      }
      sampler.tiles.set(key, tile);
      if (sampler.tiles.size > 32) sampler.tiles.delete(sampler.tiles.keys().next().value);
      const offset = ((y - top) * tile.width + x - left) * 4;
      return tile.data.subarray(offset, offset + 4);
    }

    function sourceOverlayProjectState() {
      if (!overlayImage || !overlaySourceState) return unavailableSourceOverlayState;
      const source = {
        version: 1,
        kind: overlaySourceState.kind || "image",
        file_name: overlaySourceState.fileName || "source-overlay",
        mime_type: overlaySourceState.mimeType || null,
        data_url: overlaySourceState.dataUrl || null,
        svg_text: overlaySourceState.svgText || null,
        intrinsic_width: overlaySampler?.width || overlayImage.width || null,
        intrinsic_height: overlaySampler?.height || overlayImage.height || null,
        object_width: overlayImage.width || null,
        object_height: overlayImage.height || null,
        rendered_width: overlayImage.getScaledWidth?.() || null,
        rendered_height: overlayImage.getScaledHeight?.() || null,
        transform: {
          left: round(overlayImage.left || 0),
          top: round(overlayImage.top || 0),
          scaleX: Number(overlayImage.scaleX) || 1,
          scaleY: Number(overlayImage.scaleY) || 1,
          angle: Number(overlayImage.angle) || 0,
          skewX: Number(overlayImage.skewX) || 0,
          skewY: Number(overlayImage.skewY) || 0,
          flipX: Boolean(overlayImage.flipX),
          flipY: Boolean(overlayImage.flipY),
          opacity: Number(overlayImage.opacity ?? 1),
          visible: overlayImage.visible !== false,
        },
        controls: {
          scale_percent: Number(view.element("overlayScalePercent")?.value || view.element("overlayScale")?.value || 100),
          opacity_percent: Number(view.element("overlayOpacity")?.value || Math.round((overlayImage.opacity ?? 1) * 100)),
          layer_mode: session.layerMode(),
        },
      };
      if (layeredOverlayState) {
        source.layered_svg = {
          selected_index: Number(layeredOverlayState.selectedIndex) || 0,
          view_mode: String(layeredOverlayState.viewMode || "original"),
          width: Number(layeredOverlayState.width) || null,
          height: Number(layeredOverlayState.height) || null,
          layers: Array.isArray(layeredOverlayState.layers) ? layeredOverlayState.layers.map((layer) => ({ ...layer })) : [],
        };
      }
      return source;
    }

    function clearSourceOverlayState(options = {}) {
      cancelLoads();
      const retired = overlayImage;
      unavailableSourceOverlayState = null;
      overlayImage = null;
      releaseOverlaySampler();
      overlaySourceState = null;
      clearLayeredOverlayState({ refresh: false });
      for (const retire of [() => scene.releasePreview(), () => { if (retired) scene.discard(retired); }]) {
        try { retire(); } catch (error) { displayFailed(error); }
      }
      if (options.refresh !== false) {
        try { clearLayeredOverlayState(); view.interactivity(); } catch (error) { displayFailed(error); }
      }
    }

    async function restoreSourceOverlayFromProject(state) {
      if (!state) {
        clearSourceOverlayState();
        return true;
      }
      const fileName = String(state.file_name || "source-overlay");
      if (state.kind === "layered_svg" && state.svg_text) {
        const layeredState = parseLayeredSvg(String(state.svg_text), fileName);
        const layered = state.layered_svg || {};
        layeredState.selectedIndex = Math.max(0, Math.min(
          Number(layered.selected_index) || 0,
          Math.max(0, layeredState.layers.length - 1)
        ));
        layeredState.viewMode = String(layered.view_mode || "original");
        const url = layeredSvgDataUrl(layeredState);
        if (!url) throw new Error(KfpsI18n.t("The saved layered SVG reference could not be rendered."));
        return Boolean(await loadOverlayImageFromUrl(url, fileName, { mimeType: state.mime_type || "image/svg+xml", projectState: state, layeredState }));
      }
      if (!state.data_url) {
        clearSourceOverlayState();
        return true;
      }
      return Boolean(await loadOverlayImageFromUrl(String(state.data_url), fileName, { mimeType: state.mime_type || null, projectState: state, layeredState: null }));
    }

    function applyOverlayProjectTransform(state, image = overlayImage) {
      if (!image || !state?.transform) return;
      const transform = state.transform;
      image.set({
        left: Number(transform.left) || 0,
        top: Number(transform.top) || 0,
        scaleX: Number(transform.scaleX) || 1,
        scaleY: Number(transform.scaleY) || 1,
        angle: Number(transform.angle) || 0,
        skewX: Number(transform.skewX) || 0,
        skewY: Number(transform.skewY) || 0,
        flipX: Boolean(transform.flipX),
        flipY: Boolean(transform.flipY),
        opacity: Number.isFinite(Number(transform.opacity)) ? Number(transform.opacity) : 1,
        visible: transform.visible !== false,
      });
      image.setCoords();
    }

    function clearLayeredOverlayState(options = {}) {
      layeredOverlayState = null;
      if (options.refresh === false) return;
      view.hidden("layeredOverlayControls", true);
      const select = view.element("overlaySvgLayerSelect");
      if (select) select.innerHTML = "";
      view.text("overlaySvgLayerInfo", KfpsI18n.t("Load a layered SVG to flip through its reference, guide, and color layers."));
    }

    function svgLayerLabel(group) {
      return (
        group.getAttribute("inkscape:label") ||
        group.getAttributeNS?.("http://www.inkscape.org/namespaces/inkscape", "label") ||
        group.getAttribute("label") ||
        group.id ||
        "Layer"
      );
    }

    function styleHasDisplayNone(style) {
      return /(^|;)\s*display\s*:\s*none\s*(;|$)/i.test(String(style || ""));
    }

    function setSvgElementVisible(element, visible) {
      let style = element.getAttribute("style") || "";
      style = style.replace(/(^|;)\s*display\s*:\s*none\s*;?/ig, ";").replace(/^;+|;+$/g, "").trim();
      if (!visible) style = `${style ? `${style};` : ""}display:none`;
      if (style) element.setAttribute("style", style);
      else element.removeAttribute("style");
      if (visible) element.removeAttribute("display");
      else element.setAttribute("display", "none");
    }

    function parseLayeredSvg(text, fileName = "overlay.svg") {
      const parser = new DOMParser();
      const doc = parser.parseFromString(text, "image/svg+xml");
      if (doc.querySelector("parsererror")) throw new Error(KfpsI18n.t("SVG parser rejected the file."));
      const svg = doc.documentElement;
      const groups = Array.from(svg.querySelectorAll("g")).filter((group) => {
        const label = svgLayerLabel(group);
        return group.id || label;
      });
      const layers = groups.map((group, index) => {
        const label = svgLayerLabel(group);
        const id = group.id || `svg_layer_${index}`;
        const labelLower = label.toLowerCase();
        const idLower = id.toLowerCase();
        const hidden = group.getAttribute("display") === "none" || styleHasDisplayNone(group.getAttribute("style"));
        const kind = idLower.includes("reference") || labelLower.includes("reference")
          ? "reference"
          : idLower.includes("grid") || labelLower.includes("grid")
            ? "grid"
            : idLower.includes("line") || labelLower.includes("line_art") || labelLower.includes("edge")
              ? "edge"
              : idLower.includes("canvas") || labelLower.includes("canvas")
                ? "canvas"
                : labelLower.includes("_color_") || idLower.includes("_color_") || /^l\d+_color_/.test(idLower)
                  ? "color"
                  : idLower.includes("glow") || labelLower.startsWith("fx_") || idLower.includes("fx")
                    ? "guide"
                    : "other";
        return { id, label, index, hidden, kind };
      });
      return {
        fileName,
        sourceText: text,
        width: Number(svg.getAttribute("width")?.replace(/[^\d.]/g, "")) || Number(svg.viewBox?.baseVal?.width) || 1920,
        height: Number(svg.getAttribute("height")?.replace(/[^\d.]/g, "")) || Number(svg.viewBox?.baseVal?.height) || 1080,
        layers,
        selectedIndex: Math.max(0, layers.findIndex((layer) => layer.kind === "color")),
        viewMode: "original",
      };
    }

    function selectedLayeredOverlayLayer(state = layeredOverlayState) {
      if (!state?.layers?.length) return null;
      return state.layers[Math.max(0, Math.min(state.selectedIndex, state.layers.length - 1))];
    }

    function shouldShowSvgLayer(layer, mode, selectedLayer) {
      if (mode === "original") return !layer.hidden;
      if (mode === "color_layers") return layer.kind === "color";
      if (mode === "selected") return layer.id === selectedLayer?.id;
      if (mode === "selected_reference") return layer.id === selectedLayer?.id || layer.kind === "reference";
      if (mode === "selected_edge") return layer.id === selectedLayer?.id || layer.kind === "edge";
      return !layer.hidden;
    }

    function layeredSvgDataUrl(state = layeredOverlayState) {
      if (!state) return null;
      const parser = new DOMParser();
      const doc = parser.parseFromString(state.sourceText, "image/svg+xml");
      if (doc.querySelector("parsererror")) return null;
      const selectedLayer = selectedLayeredOverlayLayer(state);
      doc.querySelectorAll("g").forEach((group) => {
        const id = group.id || "";
        const layer = state.layers.find((item) => item.id === id || item.label === svgLayerLabel(group));
        if (!layer) return;
        setSvgElementVisible(group, shouldShowSvgLayer(layer, state.viewMode, selectedLayer));
      });
      const serializer = new XMLSerializer();
      const text = serializer.serializeToString(doc);
      return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
    }

    function populateLayeredOverlayControls() {
      const controls = view.element("layeredOverlayControls");
      const select = view.element("overlaySvgLayerSelect");
      const modeSelect = view.element("overlaySvgViewMode");
      if (!controls || !select || !modeSelect || !layeredOverlayState) return;
      controls.hidden = false;
      select.innerHTML = "";
      layeredOverlayState.layers.forEach((layer, index) => {
        const option = document.createElement("option");
        option.value = String(index);
        const suffix = layer.kind !== "color" ? ` (${layer.kind})` : "";
        option.textContent = `${String(index + 1).padStart(2, "0")} ${layer.label}${suffix}`;
        select.appendChild(option);
      });
      select.value = String(layeredOverlayState.selectedIndex);
      modeSelect.value = layeredOverlayState.viewMode;
      updateLayeredOverlayInfo();
    }

    function updateLayeredOverlayInfo() {
      if (!layeredOverlayState) return;
      const layer = selectedLayeredOverlayLayer();
      const colorCount = layeredOverlayState.layers.filter((item) => item.kind === "color").length;
      view.text(
        "overlaySvgLayerInfo",
        KfpsI18n.t("{0}: {1} layer(s), {2} color layer(s). Showing {3}.", layeredOverlayState.fileName, layeredOverlayState.layers.length, colorCount, layer?.label || KfpsI18n.t("original visibility"))
      );
    }

    function setLayeredOverlayLayer(index) {
      if (!layeredOverlayState?.layers?.length) return;
      const count = layeredOverlayState.layers.length;
      return refreshLayeredOverlayImage({ ...layeredOverlayState, selectedIndex: ((Number(index) % count) + count) % count });
    }

    function setLayeredOverlayViewMode(mode) {
      if (!layeredOverlayState) return;
      return refreshLayeredOverlayImage({ ...layeredOverlayState, viewMode: String(mode || "original") });
    }

    function refreshLayeredOverlayImage(nextState = layeredOverlayState) {
      if (disposed || !layeredOverlayState || !overlayImage) return Promise.resolve(false);
      pendingRefreshCancel?.();
      const target = overlayImage;
      const state = layeredOverlayState;
      const generation = ++overlayRefreshGeneration;
      const isCurrent = () => !disposed && target === overlayImage && state === layeredOverlayState && generation === overlayRefreshGeneration;
      const url = layeredSvgDataUrl(nextState);
      if (!url) {
        view.status(KfpsI18n.t("Layered SVG reference refresh failed."));
        return Promise.resolve(false);
      }
      return new Promise(resolve => {
        const img = new Image();
        let settled = false;
        const cleanup = () => {
          clearTimeout(timer);
          img.onload = img.onerror = null;
          if (pendingRefreshCancel === cancel) pendingRefreshCancel = null;
        };
        const cancel = () => { if (settled) return; settled = true; cleanup(); img.src = ""; resolve(false); };
        const fail = () => {
          const current = isCurrent();
          cancel();
          if (current) {
            try { populateLayeredOverlayControls(); view.status(KfpsI18n.t("Layered SVG reference refresh failed.")); }
            catch (error) { displayFailed(error); }
          }
        };
        const timer = setTimeout(fail, 30000);
        pendingRefreshCancel = cancel;
        img.onload = () => {
          if (settled) return;
          if (!isCurrent()) { cancel(); return; }
          cleanup();
          let installed = false;
          try {
            scene.releasePreview();
            target.setElement(img);
            target.set({ width: img.width || nextState.width, height: img.height || nextState.height });
            rebuildOverlaySampler(img);
            layeredOverlayState = nextState;
            installed = true;
            target.setCoords();
            changed("reference image adjusted");
            populateLayeredOverlayControls();
            scene.canvas().requestRenderAll();
            settled = true; resolve(true);
          } catch (error) {
            displayFailed(error);
            if (!installed) img.src = "";
            settled = true; resolve(installed);
          }
        };
        img.onerror = fail;
        img.src = url;
      });
    }

    function canvasPointToOverlayPixel(x, y, inverse = null) {
      if (!overlayImage || !overlaySampler) return null;
      inverse ||= fabric.util.invertTransform(overlayImage.calcTransformMatrix());
      const local = fabric.util.transformPoint(new fabric.Point(x, y), inverse);
      const px = Math.round(local.x + (overlayImage.width || overlaySampler.width) / 2);
      const py = Math.round(local.y + (overlayImage.height || overlaySampler.height) / 2);
      if (px < 0 || py < 0 || px >= overlaySampler.width || py >= overlaySampler.height) return null;
      return { x: px, y: py };
    }

    function overlayColorAtCanvasPoint(x, y) {
      const pixel = canvasPointToOverlayPixel(x, y);
      if (!pixel || !overlaySampler) return null;
      const data = readOverlayPixel(pixel.x, pixel.y);
      const alpha = data[3];
      if (alpha < 24) return null;
      return [
        data[0],
        data[1],
        data[2],
        255,
      ];
    }

    function dominantOverlayColorForObject(obj) {
      if (!obj || !overlaySampler) return null;
      obj.setCoords();
      const rect = obj.getBoundingRect(true, true);
      const stepsX = Math.max(7, Math.min(44, Math.ceil(rect.width / 42)));
      const stepsY = Math.max(7, Math.min(44, Math.ceil(rect.height / 42)));
      const bins = new Map();
      const average = { count: 0, r: 0, g: 0, b: 0, a: 0 };
      const inverse = fabric.util.invertTransform(overlayImage.calcTransformMatrix());
      for (let iy = 0; iy < stepsY; iy++) {
        const y = rect.top + rect.height * ((iy + 0.5) / stepsY);
        for (let ix = 0; ix < stepsX; ix++) {
          const x = rect.left + rect.width * ((ix + 0.5) / stepsX);
          const pixel = canvasPointToOverlayPixel(x, y, inverse);
          if (!pixel) continue;
          const [r, g, b, a] = readOverlayPixel(pixel.x, pixel.y);
          if (a < 24) continue;
          average.count++;
          average.r += r;
          average.g += g;
          average.b += b;
          average.a += a;
          const key = `${r >> 4},${g >> 4},${b >> 4}`;
          const bin = bins.get(key) || { count: 0, r: 0, g: 0, b: 0, a: 0 };
          bin.count++;
          bin.r += r;
          bin.g += g;
          bin.b += b;
          bin.a += a;
          bins.set(key, bin);
        }
      }
      if (view.element("overlaySampleMode")?.value === "average" && average.count) {
        return [
          Math.round(average.r / average.count),
          Math.round(average.g / average.count),
          Math.round(average.b / average.count),
          255,
        ];
      }
      let best = null;
      for (const bin of bins.values()) {
        if (!best || bin.count > best.count || (bin.count === best.count && bin.a > best.a)) best = bin;
      }
      if (!best) return null;
      return [
        Math.round(best.r / best.count),
        Math.round(best.g / best.count),
        Math.round(best.b / best.count),
        255,
      ];
    }

    async function loadOverlayImageFromUrl(url, fileName, options = {}) {
      if (disposed) return null;
      if (options.generation === undefined) cancelLoads();
      const generation = options.generation ?? ++overlayLoadGeneration;
      const documentToken = options.documentGeneration ?? session.generation();
      const layeredState = options.layeredState === undefined ? layeredOverlayState : options.layeredState;
      const isCurrent = () => !disposed && generation === overlayLoadGeneration && documentToken === session.generation();
      if (!isCurrent()) return null;
      let objectUrl = null;
      if (String(url).startsWith("data:image/")) {
        try {
          const blob = await persistence.request("referenceImage", {
            payload: { editor_source_overlay: { data_url: layeredState ? null : url, svg_text: layeredState?.sourceText || null } },
            imageUrl: layeredState ? url : null,
            maxReferenceBytes: maxReferenceBytes,
          });
          if (!isCurrent()) return null;
          objectUrl = URL.createObjectURL(blob);
        } catch (error) {
          if (!isCurrent()) return null;
          if (error.code === "reference_too_large") error.message = KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", maxReferenceBytes / (1024 * 1024));
          view.status(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(error.message)));
          throw error;
        }
      }
      return new Promise((resolve, reject) => {
        const img = new Image();
        let installed = false;
        let settled = false;
        const cleanup = () => {
          clearTimeout(timer);
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          img.onload = img.onerror = null;
          if (pendingImageCancel === cancel) pendingImageCancel = null;
        };
        const cancel = () => { if (settled) return; settled = true; cleanup(); if (!installed) img.src = ""; resolve(null); };
        const fail = (error) => {
          if (settled) return;
          settled = true;
          cleanup();
          if (!installed) img.src = "";
          if (isCurrent()) {
            try { view.status(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(error.message))); }
            finally { reject(error); }
          } else resolve(null);
        };
        const timer = setTimeout(() => fail(new Error(KfpsI18n.t("{0} is not a usable image.", fileName))), 30000);
        pendingImageCancel = cancel;
        img.onload = () => {
          if (settled) return;
          cleanup();
          if (!isCurrent()) { cancel(); return; }
          let replacement = null;
          try {
            if (!objectUrl && new Blob([String(layeredState?.sourceText || url)]).size > maxReferenceBytes) {
              throw new Error(KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", maxReferenceBytes / (1024 * 1024)));
            }
            replacement = new fabric.Image(img, {
              originX: "center",
              originY: "center",
              left: 0,
              top: 0,
              opacity: Number(view.element("overlayOpacity").value) / 100,
              selectable: false,
              evented: false,
              excludeFromExport: true,
            });
            replacement.kloudyOverlay = true;
            if (options.projectState) {
              applyOverlayProjectTransform(options.projectState, replacement);
            } else {
              const fit = 1800 / Math.max(img.width, img.height);
              const factor = view.scaleControls(view.element("overlayScalePercent")?.value || view.element("overlayScale")?.value || 100) / 100;
              replacement.set({ scaleX: fit * factor, scaleY: fit * factor });
            }
            scene.canvas().add(replacement);
            scene.releasePreview();
            if (overlayImage) scene.discard(overlayImage);
            overlayImage = replacement;
            rebuildOverlaySampler(img);
            clearLayeredOverlayState({ refresh: false });
            layeredOverlayState = layeredState;
            overlayRefreshGeneration++;
            overlaySourceState = {
              kind: layeredState ? "layered_svg" : "image",
              fileName,
              mimeType: options.mimeType || null,
              dataUrl: layeredState ? null : url,
              svgText: layeredState?.sourceText || null,
            };
            unavailableSourceOverlayState = null;
            installed = true;
            if (options.projectState?.controls) {
              view.scaleControls(options.projectState.controls.scale_percent || 100);
              if (view.element("overlayOpacity")) view.element("overlayOpacity").value = Math.round((overlayImage.opacity ?? 1) * 100);
              if (options.projectState.controls.layer_mode) session.setLayerMode(options.projectState.controls.layer_mode, { persist: false, refresh: false });
            }
            changed("reference image loaded");
            // Prepare the reference texture during explicit image loading, so its
            // first upload is not deferred to the user's next drag or keypress.
            scene.prewarm();
            if (layeredOverlayState) populateLayeredOverlayControls();
            else clearLayeredOverlayState();
            if (session.toolMode() === "source") view.interactivity();
            else scene.order();
            scene.canvas().requestRenderAll();
            view.status(layeredOverlayState ? KfpsI18n.t("Layered SVG reference loaded: {0}", fileName) : KfpsI18n.t("Reference image loaded: {0}", fileName));
            view.hud();
            settled = true; resolve(overlayImage);
          } catch (error) {
            if (installed) { displayFailed(error); settled = true; resolve(overlayImage); return; }
            if (replacement && replacement !== overlayImage) scene.discard(replacement);
            fail(error);
          }
        };
        img.onerror = () => {
          fail(new Error(KfpsI18n.t("{0} is not a usable image.", fileName)));
        };
        img.src = objectUrl || url;
      });
    }

    function addOverlayFile(file) {
      if (disposed) return;
      if (file.size > maxReferenceBytes) {
        view.status(KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", maxReferenceBytes / (1024 * 1024)));
        return;
      }
      cancelLoads();
      const isSvg = file.type === "image/svg+xml" || /\.svg$/i.test(file.name || "");
      const generation = ++overlayLoadGeneration;
      const documentToken = session.generation();
      const isCurrent = () => !disposed && generation === overlayLoadGeneration && documentToken === session.generation();
      const reader = new FileReader();
      pendingReader = reader;
      reader.onloadend = () => {
        if (pendingReader === reader) pendingReader = null;
        reader.onload = reader.onerror = reader.onloadend = null;
      };
      reader.onerror = () => { if (isCurrent()) view.status(KfpsI18n.t("Reference load failed: could not read {0}.", file.name)); };
      if (isSvg) {
        reader.onload = () => {
          if (!isCurrent()) return;
          let layeredState;
          try {
            layeredState = parseLayeredSvg(String(reader.result || ""), file.name);
          } catch (err) {
            view.status(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(err.message || KfpsI18n.t("SVG could not be parsed."))));
            return;
          }
          const url = layeredSvgDataUrl(layeredState);
          if (!url) {
            view.status(KfpsI18n.t("Reference load failed: {0} could not be rendered.", file.name));
            return;
          }
          loadOverlayImageFromUrl(url, file.name, { mimeType: file.type || "image/svg+xml", layeredState, generation, documentGeneration: documentToken }).catch(() => {});
        };
        reader.readAsText(file);
        return;
      }
      reader.onload = () => {
        if (isCurrent()) loadOverlayImageFromUrl(reader.result, file.name, { mimeType: file.type || null, layeredState: null, generation, documentGeneration: documentToken }).catch(() => {});
      };
      reader.readAsDataURL(file);
    }

    function updateOverlay(options = {}) {
      if (!overlayImage) return;
      overlayImage.set({ opacity: Number(view.element("overlayOpacity").value) / 100 });
      if (options.rescale !== false) {
        const percent = view.scaleControls(view.element("overlayScalePercent")?.value || view.element("overlayScale")?.value || 100);
        const scale = 1800 / Math.max(overlayImage.width || 1, overlayImage.height || 1) * percent / 100;
        overlayImage.set({ scaleX: scale, scaleY: scale });
        overlayImage.setCoords();
      }
      changed("reference image adjusted");
      scene.order();
      scene.canvas().requestRenderAll();
    }

    function toggleOverlay() {
      if (!overlayImage) {
        view.status(KfpsI18n.t("No reference image is loaded. Add one first."));
        return;
      }
      overlayImage.visible = !overlayImage.visible;
      changed(overlayImage.visible ? "reference image shown" : "reference image hidden");
      scene.canvas().requestRenderAll();
    }

    function removeOverlay() {
      cancelLoads();
      if (!overlayImage && !unavailableSourceOverlayState) {
        view.status(KfpsI18n.t("No reference image is loaded to remove."));
        return;
      }
      clearSourceOverlayState({ refresh: false });
      changed("reference image removed");
      clearLayeredOverlayState();
      view.interactivity();
      scene.canvas().requestRenderAll();
      view.hud();
    }

    return {
      readOverlayPixel,
      sourceOverlayProjectState,
      clearSourceOverlayState,
      restoreSourceOverlayFromProject,
      parseLayeredSvg,
      layeredSvgDataUrl,
      setLayeredOverlayLayer,
      setLayeredOverlayViewMode,
      refreshLayeredOverlayImage,
      overlayColorAtCanvasPoint,
      dominantOverlayColorForObject,
      loadOverlayImageFromUrl,
      addOverlayFile,
      updateOverlay,
      toggleOverlay,
      removeOverlay,
      get image() { return overlayImage; }, get sampler() { return overlaySampler; },
      get source() { return overlaySourceState; }, get layered() { return layeredOverlayState; },
      get unavailable() { return unavailableSourceOverlayState; },
      preserveUnavailable(state) { unavailableSourceOverlayState = state; },
      dispose() { if (!disposed) { disposed = true; clearSourceOverlayState({ refresh: false }); } },
    };
  }
  return { create };
});
