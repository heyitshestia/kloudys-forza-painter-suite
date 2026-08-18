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

  global.KfpsFabricAdapter = Object.freeze({
    bringObjectToFront,
    major,
    moveObjectTo,
    replaceObjectStack,
    scenePoint,
    sendObjectToBack,
    version,
  });
})(window);
