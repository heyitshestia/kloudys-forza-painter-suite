(function installKfpsFabricAdapter(global) {
  "use strict";

  const runtime = global.fabric;
  if (!runtime) throw new Error("Fabric.js did not load.");

  const version = String(runtime.version || "unknown");
  const major = Number.parseInt(version.split(".")[0], 10);
  if (!Number.isFinite(major) || major < 5 || major > 7) {
    throw new Error(`Unsupported Fabric.js runtime: ${version}`);
  }

  function scenePoint(canvas, event) {
    if (typeof canvas?.getScenePoint === "function") return canvas.getScenePoint(event);
    if (typeof canvas?.getPointer === "function") return canvas.getPointer(event);
    throw new Error("Fabric canvas does not expose a scene-coordinate pointer API.");
  }

  function moveObjectTo(canvas, object, index) {
    if (!canvas || !object) return false;
    if (typeof canvas.moveObjectTo === "function") return canvas.moveObjectTo(object, index);
    if (typeof object.moveTo === "function") {
      object.moveTo(index);
      return true;
    }
    return false;
  }

  function sendObjectToBack(canvas, object) {
    if (!canvas || !object) return false;
    if (typeof canvas.sendObjectToBack === "function") return canvas.sendObjectToBack(object);
    if (typeof object.sendToBack === "function") {
      object.sendToBack();
      return true;
    }
    return false;
  }

  function bringObjectToFront(canvas, object) {
    if (!canvas || !object) return false;
    if (typeof canvas.bringObjectToFront === "function") return canvas.bringObjectToFront(object);
    if (typeof object.bringToFront === "function") {
      object.bringToFront();
      return true;
    }
    return false;
  }

  function replaceObjectStack(canvas, objects) {
    if (!canvas || !Array.isArray(objects)) return false;
    const current = canvas.getObjects();
    if (current.length === objects.length && objects.every((object, index) => current[index] === object)) {
      return false;
    }
    if (objects.some((object) => !object) || new Set(objects).size !== objects.length) {
      throw new Error("Refusing to replace the Fabric stack with missing or duplicate objects.");
    }
    canvas._objects = objects.slice();
    objects.forEach((object) => {
      object.canvas = canvas;
    });
    canvas.requestRenderAll();
    return true;
  }

  function cancelObjectTransform(canvas) {
    const transform = canvas?._currentTransform;
    if (!transform) return null;
    // Do not finalize: that would emit object:modified and record the partial
    // drag while history is restoring an earlier state.
    canvas._currentTransform = null;
    canvas._groupSelector = null;
    if (transform.target) {
      transform.target.isMoving = false;
      transform.target._scaling = false;
      transform.target.__corner = 0;
    }
    return transform;
  }

  function installSceneRenderGate(canvas, shouldSkip) {
    const renderObjects = canvas._renderObjects;
    if (typeof renderObjects !== "function") return false;
    // Keep Fabric's render lifecycle and hit-testing intact. Only the hidden
    // on-screen scene is redundant; exports and other contexts still render.
    canvas._renderObjects = function (context, objects) {
      if (context === this.contextContainer && shouldSkip()) return;
      return renderObjects.call(this, context, objects);
    };
    return true;
  }

  // KFPS never imports or serializes SVG through Fabric. Keep that boundary
  // explicit while the supported Fabric migration remains performance-gated.
  function unsupportedSvgOperation() {
    throw new Error("Fabric SVG import and serialization are disabled in the KFPS editor.");
  }
  ["loadSVGFromString", "loadSVGFromURL"].forEach((name) => {
    if (typeof runtime[name] === "function") runtime[name] = unsupportedSvgOperation;
  });
  [runtime.Canvas?.prototype, runtime.StaticCanvas?.prototype].forEach((prototype) => {
    if (prototype && typeof prototype.toSVG === "function") prototype.toSVG = unsupportedSvgOperation;
  });

  let hitSurface = null;
  const nearestControlCanvases = new WeakSet();
  let nearestControlPickingInstalled = false;

  function installNearestControlPicking(canvas) {
    const prototype = runtime.Object?.prototype;
    if (typeof prototype?._findTargetCorner !== "function") return false;
    nearestControlCanvases.add(canvas);
    if (nearestControlPickingInstalled) return true;
    const original = prototype._findTargetCorner;
    prototype._findTargetCorner = function (pointer, forTouch) {
      const hit = original.call(this, pointer, forTouch);
      if (!hit || !nearestControlCanvases.has(this.canvas)) return hit;
      // Generous hit areas overlap on narrow shapes. Enumeration order must
      // not turn a side-handle click into a corner resize or skew.
      let nearest = hit;
      let distance = (pointer.x - this.oCoords[hit].x) ** 2 + (pointer.y - this.oCoords[hit].y) ** 2;
      for (const name of Object.keys(this.oCoords)) {
        if (name === hit || !this.isControlVisible(name)) continue;
        const point = this.oCoords[name];
        const nextDistance = (pointer.x - point.x) ** 2 + (pointer.y - point.y) ** 2;
        if (nextDistance >= distance) continue;
        const corners = forTouch ? point.touchCorner : point.corner;
        if (!corners) continue;
        const crossings = this._findCrossPoints(pointer, this._getImageLines(corners));
        if (crossings !== 0 && crossings % 2 === 1) {
          nearest = name;
          distance = nextDistance;
        }
      }
      this.__corner = nearest;
      return nearest;
    };
    nearestControlPickingInstalled = true;
    return true;
  }

  function installCpuPixelPicking(canvas) {
    const original = canvas.isTargetTransparent;
    if (typeof original !== "function" || !canvas.cacheCanvasEl || !canvas.contextCache) return false;
    const surface = document.createElement("canvas");
    surface.width = canvas.cacheCanvasEl.width;
    surface.height = canvas.cacheCanvasEl.height;
    const context = surface.getContext("2d", { willReadFrequently: true });
    if (!context) return false;
    canvas.cacheCanvasEl.width = canvas.cacheCanvasEl.height = 1;
    canvas.cacheCanvasEl = surface;
    canvas.contextCache = context;
    // Preserve Fabric's full-path rasterization and tolerance. Tiny clipped
    // surfaces change antialiasing for some native triangle meshes. CPU storage
    // removes GPU readback stalls without retaining a second viewport surface.
    canvas.isTargetTransparent = function (object, x, y) {
      if (!object?.kloudy || object.kloudyGuide) return original.call(this, object, x, y);
      const caching = object.objectCaching;
      const background = object.selectionBackgroundColor;
      try {
        // Inactive objects otherwise read back their GPU-backed render cache.
        object.objectCaching = false;
        return original.call(this, object, x, y);
      } catch (error) {
        // A failing Fabric render can leave its saved transform on the context.
        const width = this.cacheCanvasEl.width;
        this.cacheCanvasEl.width = width;
        throw error;
      } finally {
        object.objectCaching = caching;
        object.selectionBackgroundColor = background;
      }
    };
    return true;
  }

  function sceneBounds(object) {
    if (!object.group) return object.getBoundingRect(true, true);
    // Fabric 5's absolute coordinates still live in the parent's coordinate space.
    const transform = object.group.calcTransformMatrix();
    const points = object.getCoords(true, true).map(point => runtime.util.transformPoint(point, transform));
    const left = Math.min(...points.map(point => point.x));
    const top = Math.min(...points.map(point => point.y));
    return { left, top, width: Math.max(...points.map(point => point.x)) - left, height: Math.max(...points.map(point => point.y)) - top };
  }

  function visiblePixelAt(canvas, object, point) {
    const bounds = object.getBoundingRect(true, true);
    if (point.x < bounds.left || point.y < bounds.top || point.x > bounds.left + bounds.width || point.y > bounds.top + bounds.height) return false;
    if (!hitSurface) { hitSurface = document.createElement("canvas"); hitSurface.width = hitSurface.height = 3; }
    const context = hitSurface.getContext("2d", { willReadFrequently: true });
    const screen = runtime.util.transformPoint(point, canvas.viewportTransform);
    const previous = { objectCaching: object.objectCaching, globalCompositeOperation: object.globalCompositeOperation, opacity: object.opacity, selectionBackgroundColor: object.selectionBackgroundColor, shadow: object.shadow };
    const groupTransformDone = object.group?._transformDone;
    context.clearRect(0, 0, 3, 3);
    context.save();
    try {
      context.translate(1 - screen.x, 1 - screen.y);
      context.transform(...canvas.viewportTransform);
      object.objectCaching = false;
      object.globalCompositeOperation = "source-over";
      object.selectionBackgroundColor = "";
      object.shadow = null;
      if (object.kloudy?.mask) object.opacity = 1;
      // Render the actual path/image alpha, not its selection box or mask proxy.
      if (object.group) object.group._transformDone = false;
      object.render(context);
      return context.getImageData(1, 1, 1, 1).data[3] > 0;
    } finally {
      Object.assign(object, previous);
      if (object.group) object.group._transformDone = groupTransformDone;
      context.restore();
    }
  }

  global.KfpsFabricAdapter = Object.freeze({
    installNearestControlPicking,
    installCpuPixelPicking,
    installSceneRenderGate,
    visiblePixelAt,
    bringObjectToFront,
    cancelObjectTransform,
    major,
    moveObjectTo,
    replaceObjectStack,
    scenePoint,
    sceneBounds,
    sendObjectToBack,
    version,
  });
})(window);
