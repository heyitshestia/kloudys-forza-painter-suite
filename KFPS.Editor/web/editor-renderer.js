(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorRenderer = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ scene, reference, view, catalog, geometry, colors, schedule, diagnostics, maxLayers, KfpsI18n }) {
    const HYBRID_RENDER_MIN_LAYERS = 300;
    const HYBRID_RENDER_MIN_REFERENCE_PIXELS = 4 * 1024 * 1024;
    const HYBRID_RENDER_PREWARM_CHUNK = 64;
    const HYBRID_RENDER_SETTLE_MS = 260;
    let hybridRenderer = null;
    let hybridRenderActive = false;
    let hybridRenderFrame = null;
    let hybridRenderSettleTimer = null;
    let documentWarmup = null;
    let hybridLowerVisibility = "";
    let hybridDisabledReason = "";
    const hybridMeshCache = new Map();
    const contextCleanup = [];
    let disposed = false;
    let generation = 0;
    function record(kind, fields) {
      try { diagnostics?.record(kind, fields); } catch (_) { /* Reporting cannot own rendering. */ }
    }
    function present(callback) {
      try { callback(); }
      catch (error) { record("js-error", { source: "editor-renderer.js", error: error?.name || "unknown" }); }
    }
    function releaseRendererResources(renderer) {
      if (!renderer) return;
      const gl = renderer.gl;
      gl.useProgram(null);
      gl.bindBuffer(gl.ARRAY_BUFFER, null);
      gl.bindTexture(gl.TEXTURE_2D, null);
      for (const mesh of hybridMeshCache.values()) gl.deleteBuffer(mesh.buffer);
      hybridMeshCache.clear();
      for (const object of [renderer, renderer.overlay, renderer.instanced]) {
        if (!object) continue;
        if (object.program) gl.deleteProgram(object.program);
        if (object.buffer) gl.deleteBuffer(object.buffer);
        if (object.texture) gl.deleteTexture(object.texture);
        object.program = object.buffer = object.texture = object.source = null;
      }
    }
    function reset(reason = "") {
      generation++;
      hybridDisabledReason = reason;
      endHybridRenderNow();
      const retired = hybridRenderer;
      hybridRenderer = null;
      if (retired) retired.element.hidden = true;
      releaseRendererResources(retired);
    }
    function requireResource(value) {
      if (!value) throw new Error(KfpsI18n.t("WebGL unavailable"));
      return value;
    }
    function compileHybridShader(gl, type, source) {
      const shader = gl.createShader(type);
      try {
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
          throw new Error(KfpsI18n.error(gl.getShaderInfoLog(shader) || KfpsI18n.t("unknown shader error")));
        }
        return shader;
      } catch (error) {
        gl.deleteShader(shader);
        throw error;
      }
    }

    function createShaderProgram(gl, sources) {
      let vertex = null, fragment = null, program = null;
      try {
        vertex = compileHybridShader(gl, gl.VERTEX_SHADER, sources.vertex);
        fragment = compileHybridShader(gl, gl.FRAGMENT_SHADER, sources.fragment);
        program = gl.createProgram();
        gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
          throw new Error(KfpsI18n.error(gl.getProgramInfoLog(program) || sources.error));
        }
        const attributes = Object.fromEntries(sources.attributes.map(name => [name, gl.getAttribLocation(program, `a_${name}`)]));
        return { program, attributes, attributeLocations: Object.values(attributes),
          uniforms: Object.fromEntries(sources.uniforms.map(name => [name, gl.getUniformLocation(program, `u_${name}`)])),
        };
      } catch (error) {
        if (program) gl.deleteProgram(program);
        throw error;
      } finally {
        if (vertex) gl.deleteShader(vertex);
        if (fragment) gl.deleteShader(fragment);
      }
    }

    function createHybridProgram(gl) {
      return createShaderProgram(gl, { vertex: `
        attribute vec2 a_position;
        attribute float a_alpha;
        uniform mat3 u_world;
        uniform mat3 u_view;
        uniform vec2 u_resolution;
        varying float v_alpha;
        void main() {
          vec3 world = u_world * vec3(a_position, 1.0);
          vec3 screen = u_view * world;
          vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
          gl_Position = vec4(clip, 0.0, 1.0);
          v_alpha = a_alpha;
        }
      `, fragment: `
        precision mediump float;
        uniform vec4 u_color;
        varying float v_alpha;
        void main() {
          gl_FragColor = vec4(u_color.rgb, u_color.a * v_alpha);
        }
      `, error: KfpsI18n.t("unknown program error"), attributes: ["position", "alpha"],
        uniforms: ["world", "view", "resolution", "color"] });
    }

    function createHybridTextureProgram(gl) {
      return createShaderProgram(gl, { vertex: `
        attribute vec2 a_position;
        attribute vec2 a_texcoord;
        uniform mat3 u_world;
        uniform mat3 u_view;
        uniform vec2 u_resolution;
        uniform vec2 u_size;
        varying vec2 v_texcoord;
        void main() {
          vec2 local = a_position * u_size;
          vec3 world = u_world * vec3(local, 1.0);
          vec3 screen = u_view * world;
          vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
          gl_Position = vec4(clip, 0.0, 1.0);
          v_texcoord = a_texcoord;
        }
      `, fragment: `
        precision mediump float;
        uniform sampler2D u_texture;
        uniform float u_opacity;
        varying vec2 v_texcoord;
        void main() {
          vec4 sampled = texture2D(u_texture, v_texcoord);
          gl_FragColor = vec4(sampled.rgb, sampled.a * u_opacity);
        }
      `, error: KfpsI18n.t("unknown texture shader error"), attributes: ["position", "texcoord"],
        uniforms: ["world", "view", "resolution", "size", "texture", "opacity"] });
    }

    function createHybridInstancedProgram(gl) {
      return createShaderProgram(gl, { vertex: `
        attribute vec2 a_position;
        attribute float a_alpha;
        attribute vec3 a_world0;
        attribute vec3 a_world1;
        attribute vec3 a_world2;
        attribute vec4 a_color;
        uniform mat3 u_view;
        uniform vec2 u_resolution;
        varying float v_alpha;
        varying vec4 v_color;
        void main() {
          mat3 world_matrix = mat3(a_world0, a_world1, a_world2);
          vec3 world = world_matrix * vec3(a_position, 1.0);
          vec3 screen = u_view * world;
          vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
          gl_Position = vec4(clip, 0.0, 1.0);
          v_alpha = a_alpha;
          v_color = a_color;
        }
      `, fragment: `
        precision mediump float;
        varying float v_alpha;
        varying vec4 v_color;
        void main() {
          gl_FragColor = vec4(v_color.rgb, v_color.a * v_alpha);
        }
      `, error: KfpsI18n.t("unknown instanced shader error"), attributes: ["position", "alpha", "world0", "world1", "world2", "color"],
        uniforms: ["view", "resolution"] });
    }

    function initHybridRenderer() {
      if (disposed) return null;
      if (hybridRenderer || hybridDisabledReason) return hybridRenderer;
      const element = view.element("hybridRenderCanvas");
      if (!element) {
        hybridDisabledReason = KfpsI18n.t("missing canvas");
        return null;
      }
      if (!contextCleanup.length) {
        const lost = event => {
          record("webgl-lost");
          event.preventDefault();
          reset("WebGL context lost");
          element.hidden = true;
          present(() => scene.canvas()?.requestRenderAll?.());
        };
        const restored = () => {
          record("webgl-restored");
          hybridDisabledReason = "";
          initHybridRenderer();
          present(() => scene.canvas()?.requestRenderAll?.());
        };
        for (const [name, handler] of [["webglcontextlost", lost], ["webglcontextrestored", restored]]) {
          element.addEventListener(name, handler);
          contextCleanup.push(() => element.removeEventListener(name, handler));
        }
      }
      const gl = element.getContext("webgl", {
        alpha: true,
        antialias: true,
        depth: false,
        stencil: false,
        preserveDrawingBuffer: true,
      });
      if (!gl) {
        record("preview-fallback", { code: 0 });
        hybridDisabledReason = KfpsI18n.t("WebGL unavailable");
        return null;
      }
      const resources = { element, gl };
      try {
        Object.assign(resources, createHybridProgram(gl));
        resources.overlay = createHybridTextureProgram(gl);
        const instancedExtension = gl.getExtension("ANGLE_instanced_arrays");
        // A replaced program must not inherit enabled attributes pointing into
        // retired buffers. Query this hardware limit only during initialization.
        const attributeLimit = gl.getParameter(gl.MAX_VERTEX_ATTRIBS);
        for (let location = 0; location < attributeLimit; location++) {
          gl.disableVertexAttribArray(location);
          instancedExtension?.vertexAttribDivisorANGLE(location, 0);
        }
        resources.enabledAttributes = new Set();
        resources.instanced = instancedExtension ? { ...createHybridInstancedProgram(gl), extension: instancedExtension } : null;
        const overlayBuffer = resources.overlay.buffer = requireResource(gl.createBuffer());
        gl.bindBuffer(gl.ARRAY_BUFFER, overlayBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
          -0.5, -0.5, 0, 0,
           0.5, -0.5, 1, 0,
          -0.5,  0.5, 0, 1,
          -0.5,  0.5, 0, 1,
           0.5, -0.5, 1, 0,
           0.5,  0.5, 1, 1,
        ]), gl.STATIC_DRAW);
        resources.overlay.texture = requireResource(gl.createTexture());
        resources.overlay.source = null;
        if (resources.instanced) {
          resources.instanced.buffer = requireResource(gl.createBuffer());
          resources.instanced.data = new Float32Array(maxLayers * 13);
        }
        gl.useProgram(resources.program);
        gl.enable(gl.BLEND);
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        gl.disable(gl.DEPTH_TEST);
        gl.disable(gl.CULL_FACE);
        resources.viewMatrix = new Float32Array(9);
        resources.pipelineWarmed = false;
        hybridRenderer = resources;
      } catch (err) {
        releaseRendererResources(resources);
        hybridDisabledReason = err?.message || String(err);
        record("preview-fallback", { code: 1 });
        console.warn(KfpsI18n.t("Hybrid renderer disabled."), err);
        hybridRenderer = null;
      }
      return hybridRenderer;
    }

    function resizeHybridRenderer() {
      const renderer = initHybridRenderer();
      if (!renderer || !scene.canvas() || renderer.gl.isContextLost()) return false;
      const width = Math.max(1, Number(scene.canvas().width) || 1);
      const height = Math.max(1, Number(scene.canvas().height) || 1);
      if (renderer.element.width !== width || renderer.element.height !== height) {
        renderer.element.width = width;
        renderer.element.height = height;
      }
      renderer.gl.viewport(0, 0, width, height);
      return true;
    }

    function hybridResourceKeyFromObject(object) {
      const meta = object?.kloudy;
      if (!meta?.resource_family || !meta?.resource_index) return null;
      return `${meta.resource_family}:${Number(meta.resource_index)}:${Number(meta.type) || ""}`;
    }

    function hybridResolvedFromObject(object) {
      const meta = object?.kloudy;
      if (!meta?.resource_family || !meta?.resource_index) return null;
      return {
        family: String(meta.resource_family),
        index: Number(meta.resource_index),
        typeCode: Number(meta.type),
        shapeWord: Number(meta.type_word ?? (Number(meta.type) & 0xffff)),
      };
    }

    function hybridMeshForObject(object) {
      const renderer = initHybridRenderer();
      const key = hybridResourceKeyFromObject(object);
      if (!renderer || !key) return null;
      if (hybridMeshCache.has(key)) return hybridMeshCache.get(key);
      const resolved = hybridResolvedFromObject(object);
      const payload = resolved ? catalog.payloads.get(catalog.key(resolved)) : null;
      const vertices = payload?.Vertices || payload?.vertices || [];
      const rawIndices = payload?.Indices || payload?.indices || payload?.triangles || [];
      if (!vertices.length || !rawIndices.length) return null;
      // Some opaque resources contain vertex-alpha bytes that the normal Fabric
      // path renderer intentionally ignores. Honor them only for resources that
      // use the editor's gradient/alpha-mesh rendering path.
      const usesVertexAlpha = catalog.isGradient(object);
      const decodedAlphas = usesVertexAlpha ? catalog.alphas(payload, vertices.length) : null;
      const indices = geometry.indices(rawIndices);
      const packed = [];
      for (const rawIndex of indices) {
        const index = Number(rawIndex);
        const point = geometry.vertex(vertices[index]);
        if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
        const decoded = decodedAlphas?.[index];
        const alpha = usesVertexAlpha
          ? (decoded === undefined ? point.alpha : Math.max(0, Math.min(1, decoded / 255)))
          : 1;
        packed.push(point.x, point.y, alpha);
      }
      if (packed.length < 9) return null;
      const gl = renderer.gl;
      const buffer = requireResource(gl.createBuffer());
      try {
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(packed), gl.STATIC_DRAW);
      } catch (error) { gl.deleteBuffer(buffer); throw error; }
      const mesh = { buffer, count: packed.length / 3, usesVertexAlpha };
      hybridMeshCache.set(key, mesh);
      return mesh;
    }

    function hybridMat3FromFabric(matrix, target = new Float32Array(9)) {
      const m = matrix || [1, 0, 0, 1, 0, 0];
      target[0] = Number(m[0]) || 0;
      target[1] = Number(m[1]) || 0;
      target[2] = 0;
      target[3] = Number(m[2]) || 0;
      target[4] = Number(m[3]) || 0;
      target[5] = 0;
      target[6] = Number(m[4]) || 0;
      target[7] = Number(m[5]) || 0;
      target[8] = 1;
      return target;
    }

    function hybridObjectColor(object, target = new Float32Array(4)) {
      const source = object.kloudy?.mask && Array.isArray(object.kloudy.maskOriginalColor)
        ? colors.normalize(object.kloudy.maskOriginalColor)
        : colors.parse(object.fill || "#ffffff", (object.opacity ?? 1) * 255);
      target[0] = Math.max(0, Math.min(1, source[0] / 255));
      target[1] = Math.max(0, Math.min(1, source[1] / 255));
      target[2] = Math.max(0, Math.min(1, source[2] / 255));
      target[3] = Math.max(0, Math.min(1, source[3] / 255));
      return target;
    }

    function hybridLayerEligible(object) {
      const meta = object?.kloudy;
      return Boolean(
        object
        && meta
        && !object.kloudyGuide
        && !object.kloudyMaskOutline
        && !object.kloudyMaskCutout
        && meta.resource_family
        && scene.visible(object)
        && (meta.mask ? (meta.maskOriginalColor?.[3] ?? 255) > 0 : (object.opacity ?? 1) > 0)
      );
    }


    function hybridShouldUse(objects = scene.objects()) {
      if (hybridDisabledReason) return false;
      const image = reference.image;
      const pixels = Number(image?.width) * Number(image?.height);
      // A large reference can dominate Canvas2D zoom cost even with no vinyls.
      const largeReference = image?.visible !== false && (image?.opacity ?? 0) > 0
        && Number.isFinite(pixels) && pixels >= HYBRID_RENDER_MIN_REFERENCE_PIXELS;
      if (!objects || (objects.length < HYBRID_RENDER_MIN_LAYERS && !largeReference)) return false;
      return Boolean(initHybridRenderer());
    }

    async function prewarmHybridMeshesForObjects(objects = scene.objects()) {
      try {
      if (!hybridShouldUse(objects)) return;
      const epoch = generation, documentEpoch = scene.generation();
      const targets = [];
      const seen = new Set();
      for (const object of objects) {
        if (!hybridLayerEligible(object)) continue;
        const key = hybridResourceKeyFromObject(object);
        if (!key || seen.has(key) || hybridMeshCache.has(key)) continue;
        seen.add(key);
        targets.push(object);
      }
      for (let index = 0; index < targets.length; index += 1) {
        if (disposed || epoch !== generation || documentEpoch !== scene.generation()) return;
        hybridMeshForObject(targets[index]);
        if ((index + 1) % HYBRID_RENDER_PREWARM_CHUNK === 0) {
          await schedule.nextFrame();
        }
      }
      if (disposed || epoch !== generation || documentEpoch !== scene.generation()) return;
      if (hybridRenderNow()) {
        // Draw every newly loaded resource set once while load progress is still
        // visible. Drivers can defer buffer specialization as well as shader work.
        if (!hybridRenderer.pipelineWarmed) hybridRenderer.gl.finish();
        hybridRenderer.pipelineWarmed = true;
      }
      } catch (error) {
        disablePreviewAfterFailure(error, 3);
      }
    }

    function disablePreviewAfterFailure(error, code) {
      reset(error?.message || String(error));
      present(() => scene.canvas()?.requestRenderAll?.());
      record("preview-fallback", { code });
      console.error("Editor GPU preview disabled; using Fabric:", hybridDisabledReason);
    }

    function hybridSetFabricLowerVisible(visible) {
      if (!scene.canvas()?.lowerCanvasEl) return;
      if (visible) {
        scene.canvas().lowerCanvasEl.style.visibility = hybridLowerVisibility;
        hybridLowerVisibility = "";
        return;
      }
      if (scene.canvas().lowerCanvasEl.style.visibility !== "hidden") hybridLowerVisibility = scene.canvas().lowerCanvasEl.style.visibility || "";
      scene.canvas().lowerCanvasEl.style.visibility = "hidden";
    }



    function hybridRenderStateForObject(object) {
      const state = object.__kloudyHybridRenderState || {
        world: new Float32Array(9),
        color: new Float32Array(4),
        fill: null,
        opacity: null,
        mask: null,
        maskColor: null,
      };
      hybridMat3FromFabric(object.calcTransformMatrix(), state.world);
      // Alpha-mesh images compensate for raster upsampling in their Fabric scale.
      // GPU vertices are already in resource units; remove that factor from the
      // linear transform only, preserving world translation and group transforms.
      if (object.kloudy?.alpha_mesh_image) {
        const renderScale = Math.max(0.000001, Number(object.kloudy.render_scale) || 1);
        state.world[0] /= renderScale;
        state.world[1] /= renderScale;
        state.world[3] /= renderScale;
        state.world[4] /= renderScale;
      }
      const maskColor = object.kloudy?.maskOriginalColor;
      const colorChanged = state.fill !== object.fill
        || state.opacity !== object.opacity
        || state.mask !== Boolean(object.kloudy?.mask)
        || state.maskColor !== maskColor
        || (Array.isArray(maskColor) && (
          state.maskR !== maskColor[0]
          || state.maskG !== maskColor[1]
          || state.maskB !== maskColor[2]
          || state.maskA !== maskColor[3]
        ));
      if (colorChanged) {
        hybridObjectColor(object, state.color);
        state.fill = object.fill;
        state.opacity = object.opacity;
        state.mask = Boolean(object.kloudy?.mask);
        state.maskColor = maskColor;
        [state.maskR, state.maskG, state.maskB, state.maskA] = Array.isArray(maskColor) ? maskColor : [null, null, null, null];
      }
      object.__kloudyHybridRenderState = state;
      return state;
    }

    function useProgramAttributes(renderer, program) {
      const next = program.attributeLocations, enabled = renderer.enabledAttributes, gl = renderer.gl;
      for (const location of enabled) if (!next.includes(location)) gl.disableVertexAttribArray(location);
      for (const location of next) if (!enabled.has(location)) gl.enableVertexAttribArray(location);
      enabled.clear();
      for (const location of next) enabled.add(location);
    }

    function prepareHybridShapeProgram(renderer, viewMatrix, maskPass) {
      const gl = renderer.gl;
      gl.useProgram(renderer.program);
      gl.uniform2f(renderer.uniforms.resolution, renderer.element.width, renderer.element.height);
      gl.uniformMatrix3fv(renderer.uniforms.view, false, viewMatrix);
      useProgramAttributes(renderer, renderer);
      if (maskPass) {
        gl.blendFuncSeparate(gl.ZERO, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE_MINUS_SRC_ALPHA);
      } else {
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      }
    }

    function drawHybridShapePassFallback(renderer, objects, viewMatrix, maskPass) {
      const gl = renderer.gl;
      prepareHybridShapeProgram(renderer, viewMatrix, maskPass);
      let boundBuffer = null;
      for (const object of objects) {
        if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
        const mesh = hybridMeshForObject(object);
        if (!mesh) continue;
        if (mesh.buffer !== boundBuffer) {
          boundBuffer = mesh.buffer;
          gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buffer);
          gl.vertexAttribPointer(renderer.attributes.position, 2, gl.FLOAT, false, 12, 0);
          gl.vertexAttribPointer(renderer.attributes.alpha, 1, gl.FLOAT, false, 12, 8);
        }
        const state = hybridRenderStateForObject(object);
        gl.uniformMatrix3fv(renderer.uniforms.world, false, state.world);
        gl.uniform4fv(renderer.uniforms.color, state.color);
        gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
      }
    }

    function prepareHybridInstancedProgram(renderer, viewMatrix, maskPass) {
      const gl = renderer.gl;
      const instanced = renderer.instanced;
      gl.useProgram(instanced.program);
      gl.uniform2f(instanced.uniforms.resolution, renderer.element.width, renderer.element.height);
      gl.uniformMatrix3fv(instanced.uniforms.view, false, viewMatrix);
      useProgramAttributes(renderer, instanced);
      if (maskPass) {
        gl.blendFuncSeparate(gl.ZERO, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE_MINUS_SRC_ALPHA);
      } else {
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      }
    }

    function drawHybridInstancedRun(renderer, mesh, states) {
      if (!mesh || !states.length) return;
      const gl = renderer.gl;
      const instanced = renderer.instanced;
      const extension = instanced.extension;
      const stride = 13;
      states.forEach((state, index) => {
        const offset = index * stride;
        instanced.data.set(state.world, offset);
        instanced.data.set(state.color, offset + 9);
      });
      gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buffer);
      gl.vertexAttribPointer(instanced.attributes.position, 2, gl.FLOAT, false, 12, 0);
      gl.vertexAttribPointer(instanced.attributes.alpha, 1, gl.FLOAT, false, 12, 8);
      extension.vertexAttribDivisorANGLE(instanced.attributes.position, 0);
      extension.vertexAttribDivisorANGLE(instanced.attributes.alpha, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, instanced.buffer);
      gl.bufferData(gl.ARRAY_BUFFER, instanced.data.subarray(0, states.length * stride), gl.DYNAMIC_DRAW);
      const byteStride = stride * 4;
      gl.vertexAttribPointer(instanced.attributes.world0, 3, gl.FLOAT, false, byteStride, 0);
      gl.vertexAttribPointer(instanced.attributes.world1, 3, gl.FLOAT, false, byteStride, 12);
      gl.vertexAttribPointer(instanced.attributes.world2, 3, gl.FLOAT, false, byteStride, 24);
      gl.vertexAttribPointer(instanced.attributes.color, 4, gl.FLOAT, false, byteStride, 36);
      extension.vertexAttribDivisorANGLE(instanced.attributes.world0, 1);
      extension.vertexAttribDivisorANGLE(instanced.attributes.world1, 1);
      extension.vertexAttribDivisorANGLE(instanced.attributes.world2, 1);
      extension.vertexAttribDivisorANGLE(instanced.attributes.color, 1);
      extension.drawArraysInstancedANGLE(gl.TRIANGLES, 0, mesh.count, states.length);
    }

    function resetHybridInstancedDivisors(renderer) {
      const instanced = renderer.instanced;
      if (!instanced) return;
      const extension = instanced.extension;
      Object.values(instanced.attributes).forEach((location) => extension.vertexAttribDivisorANGLE(location, 0));
    }

    function hybridInstancingEffective(objects, maskPass) {
      let eligible = 0;
      let runs = 0;
      let previousMesh = null;
      for (const object of objects) {
        if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
        const mesh = hybridMeshForObject(object);
        if (!mesh) continue;
        eligible += 1;
        if (mesh !== previousMesh) {
          runs += 1;
          previousMesh = mesh;
        }
      }
      return eligible >= 4 && runs <= eligible * 0.65;
    }

    function drawHybridShapePass(renderer, objects, viewMatrix, maskPass) {
      if (!renderer.instanced || !hybridInstancingEffective(objects, maskPass)) {
        drawHybridShapePassFallback(renderer, objects, viewMatrix, maskPass);
        return;
      }
      prepareHybridInstancedProgram(renderer, viewMatrix, maskPass);
      let activeMesh = null;
      let states = [];
      const flush = () => {
        if (activeMesh && states.length) drawHybridInstancedRun(renderer, activeMesh, states);
        states = [];
      };
      for (const object of objects) {
        if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
        const mesh = hybridMeshForObject(object);
        if (!mesh) continue;
        if (activeMesh && mesh !== activeMesh) flush();
        activeMesh = mesh;
        states.push(hybridRenderStateForObject(object));
      }
      flush();
      resetHybridInstancedDivisors(renderer);
    }

    function releaseHybridOverlay() {
      const renderer = hybridRenderer;
      if (!renderer?.overlay) return;
      if (renderer.overlay.texture) renderer.gl.deleteTexture(renderer.overlay.texture);
      renderer.overlay.texture = null;
      renderer.overlay.source = null;
    }

    function drawHybridOverlay(renderer, viewMatrix) {
      if (!reference.image || reference.image.visible === false || (reference.image.opacity ?? 1) <= 0) return false;
      const source = reference.image.getElement?.() || reference.image._element;
      if (!source) return false;
      const gl = renderer.gl;
      const overlay = renderer.overlay;
      if (!overlay.texture) overlay.texture = requireResource(gl.createTexture());
      gl.useProgram(overlay.program);
      gl.bindBuffer(gl.ARRAY_BUFFER, overlay.buffer);
      useProgramAttributes(renderer, overlay);
      gl.vertexAttribPointer(overlay.attributes.position, 2, gl.FLOAT, false, 16, 0);
      gl.vertexAttribPointer(overlay.attributes.texcoord, 2, gl.FLOAT, false, 16, 8);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, overlay.texture);
      if (overlay.source !== source) {
        let uploadCanvas = null;
        try {
          const width = source.naturalWidth || source.width;
          const height = source.naturalHeight || source.height;
          const limit = gl.getParameter(gl.MAX_TEXTURE_SIZE);
          let uploadSource = source;
          // Only the GPU preview is resized; sampling and project data keep the original.
          if (Math.max(width, height) > limit) {
            const scale = limit / Math.max(width, height);
            uploadCanvas = document.createElement("canvas");
            uploadCanvas.width = Math.max(1, Math.floor(width * scale));
            uploadCanvas.height = Math.max(1, Math.floor(height * scale));
            uploadCanvas.getContext("2d").drawImage(source, 0, 0, uploadCanvas.width, uploadCanvas.height);
            uploadSource = uploadCanvas;
          }
          gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, uploadSource);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
          // Allocation failures set a WebGL error rather than throwing. Check only
          // after uploads, never on every pointer frame (which can stall the GPU).
          const uploadError = gl.getError();
          if (uploadError !== gl.NO_ERROR) throw new Error(`Reference texture upload failed (WebGL ${uploadError}).`);
          overlay.source = source;
        } finally {
          if (uploadCanvas) uploadCanvas.width = uploadCanvas.height = 1;
        }
      }
      hybridMat3FromFabric(reference.image.calcTransformMatrix(), overlay.world || (overlay.world = new Float32Array(9)));
      gl.uniformMatrix3fv(overlay.uniforms.world, false, overlay.world);
      gl.uniformMatrix3fv(overlay.uniforms.view, false, viewMatrix);
      gl.uniform2f(overlay.uniforms.resolution, renderer.element.width, renderer.element.height);
      gl.uniform2f(overlay.uniforms.size, Math.max(1, Number(reference.image.width) || 1), Math.max(1, Number(reference.image.height) || 1));
      gl.uniform1i(overlay.uniforms.texture, 0);
      gl.uniform1f(overlay.uniforms.opacity, Math.max(0, Math.min(1, Number(reference.image.opacity) || 0)));
      gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      return true;
    }

    function hybridCanvasBackgroundColor(renderer) {
      const raw = String(scene.canvas().backgroundColor || view.cssColor("--fabric-canvas-bg", "#ffffff")).trim();
      if (renderer.backgroundRaw === raw && renderer.backgroundColor) return renderer.backgroundColor;
      let color = [255, 255, 255, 255];
      if (/^#[0-9a-f]{6}$/i.test(raw)) {
        color = colors.parse(raw, 255);
      } else {
        const match = raw.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
        if (match) color = colors.normalize([Number(match[1]), Number(match[2]), Number(match[3]), 255]);
      }
      renderer.backgroundRaw = raw;
      renderer.backgroundColor = color;
      return color;
    }

    function hybridRenderNow() {
      try {
        if (!resizeHybridRenderer() || !hybridShouldUse()) {
          endHybridRenderNow();
          return false;
        }
        const objects = scene.objects();
        const renderer = hybridRenderer;
        const gl = renderer.gl;
        gl.viewport(0, 0, renderer.element.width, renderer.element.height);
        const background = hybridCanvasBackgroundColor(renderer);
        gl.clearColor(background[0] / 255, background[1] / 255, background[2] / 255, 1);
        gl.clear(gl.COLOR_BUFFER_BIT);
        const viewMatrix = hybridMat3FromFabric(scene.canvas().viewportTransform, renderer.viewMatrix);
        const drawReference = () => {
          const required = reference.image?.visible !== false && (reference.image?.opacity ?? 0) > 0;
          if (!drawHybridOverlay(renderer, viewMatrix) && required) throw new Error("Reference preview unavailable.");
        };
        if (reference.layerMode() === "below") drawReference();
        drawHybridShapePass(renderer, objects, viewMatrix, false);
        if (reference.layerMode() === "above") drawReference();
        drawHybridShapePass(renderer, objects, viewMatrix, true);
        gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
        return true;
      } catch (error) {
        disablePreviewAfterFailure(error, 2);
        return false;
      }
    }

    function requestHybridRender() {
      if (disposed || hybridRenderFrame) return;
      hybridRenderFrame = requestAnimationFrame(() => {
        hybridRenderFrame = null;
        if (!hybridRenderActive) return;
        if (hybridRenderNow()) {
          // Keep the last complete Fabric frame visible until the preview succeeds.
          hybridSetFabricLowerVisible(false);
          hybridRenderer.element.hidden = false;
          scene.canvas()?.renderTop?.();
        }
      });
    }

    function beginHybridRender(reason = "interaction") {
      cancelDocumentWarmup();
      if (disposed || scene.toolMode() === "guides") return false;
      const objects = scene.objects();
      if (!hybridShouldUse(objects)) return false;
      clearTimeout(hybridRenderSettleTimer);
      hybridRenderSettleTimer = null;
      hybridRenderActive = true;
      requestHybridRender();
      present(() => view.text("hudMode", KfpsI18n.t("{0} / GPU preview", view.mode(scene.selected().length))));
      return true;
    }

    function endHybridRenderNow() {
      cancelDocumentWarmup();
      clearTimeout(hybridRenderSettleTimer);
      hybridRenderSettleTimer = null;
      if (hybridRenderFrame) cancelAnimationFrame(hybridRenderFrame);
      hybridRenderFrame = null;
      if (!hybridRenderActive) return;
      hybridRenderActive = false;
      try { diagnostics?.awaitPaint?.("settled-paint"); } catch (_) {}
      hybridSetFabricLowerVisible(true);
      if (hybridRenderer?.element) hybridRenderer.element.hidden = true;
      present(() => scene.canvas()?.requestRenderAll?.());
      present(() => view.hud());
    }

    function settleHybridRender(delay = HYBRID_RENDER_SETTLE_MS) {
      if (!hybridRenderActive) return;
      clearTimeout(hybridRenderSettleTimer);
      hybridRenderSettleTimer = setTimeout(() => endHybridRenderNow(), delay);
    }

    function cancelDocumentWarmup(state = "cancelled") {
      const job = documentWarmup;
      if (!job) return;
      documentWarmup = null;
      if (job.frame) cancelAnimationFrame(job.frame);
      record("phase", { phase: "document-cache", state, duration: performance.now() - job.started,
        documentId: job.identity, layers: job.warmed });
    }

    function warmDocumentCaches() {
      const canvas = scene.canvas();
      if (!canvas || disposed) return false;
      // Publish a complete GPU frame before the queued Fabric pass can build all
      // cold caches at once. Ordinary drawing remains the fallback and final view.
      canvas.cancelRequestedRender();
      if (!beginHybridRender("document load")) {
        canvas.requestRenderAll();
        return false;
      }
      canvas.requestRenderAll();
      const job = { canvas, identity: scene.documentIdentity(), objects: scene.objects().slice(),
        index: 0, warmed: 0, frame: 0, started: performance.now() };
      documentWarmup = job;
      const step = () => {
        if (documentWarmup !== job) return;
        job.frame = 0;
        if (disposed || !hybridRenderActive || scene.canvas() !== canvas
          || scene.documentIdentity() !== job.identity) {
          endHybridRenderNow();
          return;
        }
        const started = performance.now();
        try {
          while (job.index < job.objects.length) {
            const object = job.objects[job.index++];
            if (object.canvas === canvas && object.visible && object.opacity !== 0
              && (!canvas.skipOffscreen || object.group || object.isOnScreen()) && object.shouldCache()) {
              object.renderCache();
              job.warmed++;
            }
            if (performance.now() - started >= 4) break;
          }
        } catch (error) {
          cancelDocumentWarmup("failed");
          record("js-error", { source: "editor-renderer.js", error: error?.name || "unknown" });
          endHybridRenderNow();
          return;
        }
        if (job.index === job.objects.length) {
          cancelDocumentWarmup("finished");
          try { diagnostics?.awaitPaint?.("document-paint"); } catch (_) {}
          endHybridRenderNow();
        } else job.frame = requestAnimationFrame(step);
      };
      job.frame = requestAnimationFrame(step);
      return true;
    }
    return {
      reset,
      dispose() {
        if (disposed) return;
        disposed = true; reset();
        contextCleanup.splice(0).forEach(remove => remove());
      },
      initHybridRenderer,
      resizeHybridRenderer,
      hybridMeshForObject,
      hybridShouldUse,
      prewarmHybridMeshesForObjects,
      releaseHybridOverlay,
      hybridCanvasBackgroundColor,
      hybridRenderNow,
      requestHybridRender,
      beginHybridRender,
      endHybridRenderNow,
      settleHybridRender,
      warmDocumentCaches,
      get warmingDocument() { return Boolean(documentWarmup); },
      get renderer() { return hybridRenderer; },
      get meshCount() { return hybridMeshCache.size; },
      get active() { return hybridRenderActive; },
      get disabledReason() { return hybridDisabledReason; },
      get minimumLayers() { return HYBRID_RENDER_MIN_LAYERS; },
    };
  }
  return { create };
});
