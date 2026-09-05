import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const SECTION_COUNT = 11;
const RENDER_CONTRACT_FORMAT = 'kfps_fh6_section_render_contract_v3';
const ALL_BODY_SIDES = 0x1f;
const ALL_GLASS_SIDES = 0x7c0;
const SLOT_GEOMETRY_SIDES = [0, 1, 2, 4, 3, 5, 6, 7, 8, 10, 9];
const canvas = document.querySelector('#canvas');
const viewport = document.querySelector('#viewport');
const status = document.querySelector('#status');
const title = document.querySelector('#title');
const vehicle = document.querySelector('#vehicle');
const resetButton = document.querySelector('#reset');
const rotateButton = document.querySelector('#rotate');
const partControls = document.querySelector('#parts');
const sectionButtons = [...document.querySelectorAll('[data-section]')];

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
const gl = renderer.getContext();
const debugRenderer = gl.getExtension('WEBGL_debug_renderer_info');
const graphicsDevice = {
  renderer: gl.getParameter(debugRenderer ? debugRenderer.UNMASKED_RENDERER_WEBGL : gl.RENDERER),
  vendor: gl.getParameter(debugRenderer ? debugRenderer.UNMASKED_VENDOR_WEBGL : gl.VENDOR),
  maxTextureSize: renderer.capabilities.maxTextureSize,
  anisotropy: Math.min(4, renderer.capabilities.getMaxAnisotropy()),
};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x090b0e);
const camera = new THREE.PerspectiveCamera(36, 1, 0.01, 1000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.075;
controls.autoRotateSpeed = 0.65;

const trackedGeometries = new Set();
const trackedMaterials = new Set();
const trackedTextures = new Set();
const trackedSkeletons = new Set();
let animationFrameId = 0;
let viewerDisposed = false;
let rendererContextReleased = false;
let renderWidth = 0;
let renderHeight = 0;
let renderPixelRatio = 0;
let renderRequests = 0;
let renderedFrames = 0;
let modelBounds = null;
const startedAt = performance.now();
const loadAbort = new AbortController();
const loadTimeout = window.setTimeout(() => failViewer('Loading the car exceeded 60 seconds.'), 60000);
const timings = {};
let modelReady = false;
let firstFrameReady = false;
let frameTime = 0;
let lastFrameAt = 0;
let frameTimeTotal = 0;
let frameTimePeak = 0;
const gpuBudgetBytes = Math.min(512, Math.max(192, (navigator.deviceMemory || 4) * 64)) * 1024 * 1024;
let modelResourceBytes = 0;

function viewerEvent(event, message = '') {
  console.info('KFPS_VIEWER:' + JSON.stringify({event, message, diagnostics: viewerDiagnostics()}));
}

function phase(name, message) {
  timings[name] = Math.round(performance.now() - startedAt);
  setStatus(message);
  viewerEvent('phase', message);
}

function failViewer(message) {
  if (viewerDisposed) return;
  setStatus(message, true);
  viewerEvent('error', message);
  disposeViewer();
}

function resourceBytes() {
  const buffers = new Set();
  for (const geometry of trackedGeometries) {
    for (const attribute of [...Object.values(geometry.attributes), geometry.index]) {
      const buffer = (attribute?.array || attribute?.data?.array)?.buffer;
      if (buffer) buffers.add(buffer);
    }
  }
  let geometryBytes = 0;
  buffers.forEach(buffer => { geometryBytes += buffer.byteLength; });
  let textureBytes = 0;
  trackedTextures.forEach(texture => {
    const image = texture.image;
    textureBytes += (image?.width || 0) * (image?.height || 0) * 4 * (texture.generateMipmaps ? 4 / 3 : 1);
  });
  const framebuffers = viewerDisposed ? 0 : Math.ceil(renderWidth * renderHeight * renderPixelRatio ** 2 * 40);
  return {geometry: geometryBytes, textures: Math.ceil(textureBytes), framebuffers,
    estimatedGpu: Math.ceil(geometryBytes + textureBytes + framebuffers), budget: gpuBudgetBytes};
}

function trackTexture(texture) {
  if (!texture?.isTexture) return texture;
  if (viewerDisposed) {
    texture.dispose();
    if (typeof texture.image?.close === 'function') texture.image.close();
  } else {
    trackedTextures.add(texture);
  }
  return texture;
}

function trackMaterial(material) {
  for (const item of Array.isArray(material) ? material : [material]) {
    if (!item?.isMaterial) continue;
    for (const value of Object.values(item)) trackTexture(value);
    for (const uniform of Object.values(item.uniforms || {})) {
      const value = uniform?.value;
      if (Array.isArray(value)) value.forEach(trackTexture);
      else trackTexture(value);
    }
    if (viewerDisposed) item.dispose();
    else trackedMaterials.add(item);
  }
  return material;
}

function trackObjectResources(root) {
  root?.traverse(child => {
    if (child.geometry?.isBufferGeometry) {
      if (viewerDisposed) child.geometry.dispose();
      else trackedGeometries.add(child.geometry);
    }
    trackMaterial(child.material);
    if (child.skeleton?.dispose) {
      if (viewerDisposed) child.skeleton.dispose();
      else trackedSkeletons.add(child.skeleton);
    }
  });
  return root;
}

scene.add(new THREE.HemisphereLight(0xe9f7ff, 0x14191e, 2.35));
const keyLight = new THREE.DirectionalLight(0xffffff, 3.1);
keyLight.position.set(4.5, 8, 6);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x7cdfee, 2.0);
rimLight.position.set(-6, 3, -5);
scene.add(rimLight);

const floor = trackObjectResources(new THREE.Mesh(
  new THREE.CircleGeometry(7, 96),
  new THREE.MeshStandardMaterial({ color: 0x11161a, roughness: 0.86, metalness: 0.05 })
));
floor.rotation.x = -Math.PI / 2;
scene.add(floor);

let model = null;
let homeCamera = camera.position.clone();
let homeTarget = controls.target.clone();
let paintMaterials = [];
let glassMaterials = [];
let renderContract = null;
let selectedPartOptions = new Map();
let selectablePartGroups = new Map();

function setStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle('hidden', !message);
  status.classList.toggle('error', error);
}

function meshIdentity(mesh) {
  return `${mesh.name || ''} ${mesh.material?.name || ''}`.toLowerCase();
}

function meshCategory(mesh) {
  const declared = String(mesh.userData?.kfps_role || '').toLowerCase();
  if (['paint', 'glass', 'hidden', 'dark', 'trim'].includes(declared)) return declared;
  const identity = meshIdentity(mesh);
  const hasUv3 = Boolean(mesh.geometry?.getAttribute('uv3'));
  if (
    identity.includes('gls_window')
    || identity.includes('gls_windshield')
    || identity.includes('glassflivery')
    || identity.includes('glass_livery')
    || identity.includes('windshield')
    || identity.includes('windsheild')
  ) return 'glass';
  if (hasUv3 && identity.includes('glass') && !identity.includes('blackglass') && !identity.includes('gls_clear')) {
    return 'glass';
  }
  if (identity.includes('carpaint') || identity.includes('car_paint')) return 'paint';
  if (identity.includes('shadow')) return 'hidden';
  if (
    identity.includes('blackglass')
    || identity.includes('gls_clear')
    || identity.includes('undercarriage')
    || identity.includes('tire')
  ) return 'dark';
  return 'trim';
}

function meshAllowedSides(mesh, category) {
  const declared = Number(mesh.userData?.kfps_allowed_sides);
  if (Number.isInteger(declared) && declared > 0 && declared < (1 << SECTION_COUNT)) {
    return declared;
  }
  return category === 'glass' ? ALL_GLASS_SIDES : ALL_BODY_SIDES;
}

function meshProjectionSides(mesh) {
  const declared = Number(mesh.userData?.kfps_projection_sides);
  return Number.isInteger(declared) && declared >= 0 && declared < (1 << SECTION_COUNT)
    ? declared
    : 0;
}

function allowedSlotArray(mask) {
  const allowed = new Float32Array(SECTION_COUNT);
  for (let slot = 0; slot < SECTION_COUNT; slot += 1) {
    allowed[slot] = (mask & (1 << slot)) !== 0 ? 1 : 0;
  }
  return allowed;
}

function meshPartOptionIds(mesh) {
  const values = mesh.userData?.kfps_part_option_ids;
  return Array.isArray(values) ? values.map(Number).filter(Number.isInteger) : [];
}

function meshPartVisible(mesh) {
  const optionIds = meshPartOptionIds(mesh);
  if (!optionIds.length) return true;
  const partType = String(mesh.userData?.kfps_part_type || '');
  const selected = selectedPartOptions.get(partType);
  if (Number.isInteger(selected)) return optionIds.includes(selected);
  return mesh.userData?.kfps_stock_part === true;
}

function partTypeLabel(value) {
  return String(value || 'Car part')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ');
}

function preparePartControls(options) {
  selectedPartOptions = new Map();
  selectablePartGroups = new Map();
  partControls.replaceChildren();
  for (const option of Array.isArray(options) ? options : []) {
    const partType = String(option?.part_type || '');
    const id = Number(option?.id);
    if (!partType || !Number.isInteger(id)) continue;
    if (!selectablePartGroups.has(partType)) selectablePartGroups.set(partType, []);
    selectablePartGroups.get(partType).push({
      id,
      level: Number(option?.level) || 0,
      stock: option?.stock === true,
    });
  }
  for (const [partType, optionsForPart] of selectablePartGroups) {
    optionsForPart.sort((a, b) => Number(b.stock) - Number(a.stock) || a.level - b.level || a.id - b.id);
    const alternatives = optionsForPart.filter(option => !option.stock);
    selectedPartOptions.set(partType, null);
    if (!alternatives.length) continue;
    const label = document.createElement('label');
    const select = document.createElement('select');
    const controlId = `part-${partType.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;
    label.htmlFor = controlId;
    label.textContent = partTypeLabel(partType);
    select.id = controlId;
    select.dataset.partType = partType;
    const stockOption = document.createElement('option');
    stockOption.value = '';
    stockOption.textContent = 'Stock';
    stockOption.selected = true;
    select.append(stockOption);
    for (const option of alternatives) {
      const element = document.createElement('option');
      element.value = String(option.id);
      element.textContent = `Option ${option.level || option.id}`;
      select.append(element);
    }
    partControls.append(label, select);
  }
  partControls.classList.toggle('hidden', partControls.childElementCount === 0);
}

async function loadTexture(url, color = false) {
  const response = await fetch(url, {signal: loadAbort.signal});
  if (!response.ok) throw new Error(`Texture load failed (${response.status}).`);
  const bitmap = await createImageBitmap(await response.blob(), {
    premultiplyAlpha: 'none', colorSpaceConversion: 'none',
  });
  if (viewerDisposed) { bitmap.close(); throw new Error('Viewer closed.'); }
  if (Math.max(bitmap.width, bitmap.height) > renderer.capabilities.maxTextureSize) {
    bitmap.close();
    throw new Error('This graphics device cannot load the selected texture resolution.');
  }
  const texture = trackTexture(new THREE.Texture(bitmap));
  texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.flipY = false;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.anisotropy = color ? Math.min(4, renderer.capabilities.getMaxAnisotropy()) : 1;
  texture.needsUpdate = true;
  return texture;
}

function sectionArrays(contract, kind, projectionBounds) {
  const sourceRegions = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  const paintRegions = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  const facings = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector3());
  const present = new Float32Array(SECTION_COUNT);
  const projectionAxes = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  const projectionMinimum = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector2(-1, -1));
  const projectionMaximum = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector2(1, 1));
  const projectionMaskRegions = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  for (const section of contract.sections || []) {
    const slot = Number(section.slot_index);
    if (!Number.isInteger(slot) || slot < 0 || slot >= SECTION_COUNT) continue;
    const source = section.source_region || [];
    const paint = section.paint_region || [];
    const facing = section.facing || [];
    const projectionAxis = section.projection_axis || [];
    const projectionMask = section.projection_mask_region || [];
    sourceRegions[slot].set(...source.map(Number));
    paintRegions[slot].set(...paint.map(Number));
    facings[slot].set(...facing.map(Number));
    projectionAxes[slot].set(...projectionAxis.map(Number));
    projectionMaskRegions[slot].set(...projectionMask.map(Number));
    const bounds = projectionBounds?.[slot];
    if (bounds?.valid) {
      projectionMinimum[slot].copy(bounds.minimum);
      projectionMaximum[slot].copy(bounds.maximum);
    }
    if (section.kind === kind) present[slot] = 1;
  }
  return {
    sourceRegions,
    paintRegions,
    facings,
    present,
    projectionAxes,
    projectionMinimum,
    projectionMaximum,
    projectionMaskRegions,
  };
}

function sectionAwareMaterial(
  paintTexture,
  maskTextures,
  baseColor,
  kind,
  allowedSides,
  projectionSides,
  projectionBounds,
  directUv,
  transparent = false
) {
  const arrays = sectionArrays(renderContract, kind, projectionBounds);
  const material = trackMaterial(new THREE.ShaderMaterial({
    uniforms: {
      paintMap: { value: paintTexture },
      maskMap0: { value: maskTextures[0] },
      maskMap1: { value: maskTextures[1] },
      maskMap2: { value: maskTextures[2] },
      sourceRegions: { value: arrays.sourceRegions },
      paintRegions: { value: arrays.paintRegions },
      sideFacing: { value: arrays.facings },
      enabledSlots: { value: arrays.present },
      meshAllowedSlots: { value: allowedSlotArray(allowedSides) },
      meshProjectionSlots: { value: allowedSlotArray(projectionSides) },
      projectionAxis: { value: arrays.projectionAxes },
      projectionMinimum: { value: arrays.projectionMinimum },
      projectionMaximum: { value: arrays.projectionMaximum },
      projectionMaskRegion: { value: arrays.projectionMaskRegions },
      useDirectUv: { value: directUv ? 1.0 : 0.0 },
      baseColor: { value: new THREE.Color(baseColor) },
      keyDirection: { value: new THREE.Vector3(0.45, 0.9, 0.55).normalize() },
    },
    vertexShader: `
      ${directUv ? 'attribute vec2 uv3;' : ''}
      varying vec2 atlasUv;
      varying vec3 worldNormalValue;
      varying vec3 worldPositionValue;
      void main() {
        atlasUv = ${directUv ? 'vec2(uv3.x * 0.5, uv3.y)' : 'vec2(0.0)'};
        vec4 worldPosition = modelMatrix * vec4(position, 1.0);
        worldPositionValue = worldPosition.xyz;
        worldNormalValue = normalize(mat3(modelMatrix) * normal);
        gl_Position = projectionMatrix * viewMatrix * worldPosition;
      }
    `,
    fragmentShader: `
      uniform sampler2D paintMap;
      uniform sampler2D maskMap0;
      uniform sampler2D maskMap1;
      uniform sampler2D maskMap2;
      uniform vec4 sourceRegions[${SECTION_COUNT}];
      uniform vec4 paintRegions[${SECTION_COUNT}];
      uniform vec3 sideFacing[${SECTION_COUNT}];
      uniform float enabledSlots[${SECTION_COUNT}];
      uniform float meshAllowedSlots[${SECTION_COUNT}];
      uniform float meshProjectionSlots[${SECTION_COUNT}];
      uniform vec4 projectionAxis[${SECTION_COUNT}];
      uniform vec2 projectionMinimum[${SECTION_COUNT}];
      uniform vec2 projectionMaximum[${SECTION_COUNT}];
      uniform vec4 projectionMaskRegion[${SECTION_COUNT}];
      uniform float useDirectUv;
      uniform vec3 baseColor;
      uniform vec3 keyDirection;
      varying vec2 atlasUv;
      varying vec3 worldNormalValue;
      varying vec3 worldPositionValue;

      float slotCoverage(int slot, vec4 page0, vec4 page1, vec4 page2) {
        if (slot == 0) return page0.r;
        if (slot == 1) return page0.g;
        if (slot == 2) return page0.b;
        if (slot == 3) return page0.a;
        if (slot == 4) return page1.r;
        if (slot == 5) return page1.g;
        if (slot == 6) return page1.b;
        if (slot == 7) return page1.a;
        if (slot == 8) return page2.r;
        if (slot == 9) return page2.g;
        return page2.b;
      }

      float axisComponent(vec3 value, float axis) {
        if (axis < 0.5) return value.x;
        if (axis < 1.5) return value.y;
        return value.z;
      }

      void main() {
        vec3 normalValue = normalize(worldNormalValue);
        float bestCoverage = 0.0;
        float bestFacing = -1.0;
        int bestSlot = -1;
        vec2 bestAtlasUv = atlasUv;
        ${directUv ? `vec4 directPage0 = texture2D(maskMap0, atlasUv);
        vec4 directPage1 = texture2D(maskMap1, atlasUv);
        vec4 directPage2 = texture2D(maskMap2, atlasUv);` : ''}
        for (int slot = 0; slot < ${SECTION_COUNT}; ++slot) {
          if (
            enabledSlots[slot] < 0.5
            || meshAllowedSlots[slot] < 0.5
            || dot(sideFacing[slot], normalValue) <= 0.0
          ) continue;
          vec2 candidateUv = atlasUv;
          if (useDirectUv < 0.5) {
            if (meshProjectionSlots[slot] < 0.5) continue;
            vec4 axis = projectionAxis[slot];
            vec2 minimum = projectionMinimum[slot];
            vec2 range = projectionMaximum[slot] - minimum;
            if (range.x <= 0.000001 || range.y <= 0.000001) continue;
            vec2 axisValue = vec2(
              axisComponent(worldPositionValue, axis.x) * axis.z,
              axisComponent(worldPositionValue, axis.y) * axis.w
            );
            vec2 normalized = (axisValue - minimum) / range;
            vec4 maskRegion = projectionMaskRegion[slot];
            candidateUv = vec2(
              mix(maskRegion.x, maskRegion.y, normalized.x),
              mix(maskRegion.z, maskRegion.w, normalized.y)
            );
          }
          if (
            candidateUv.x < 0.0 || candidateUv.x > 1.0
            || candidateUv.y < 0.0 || candidateUv.y > 1.0
          ) continue;
          vec4 page0 = ${directUv ? 'directPage0' : 'texture2D(maskMap0, candidateUv)'};
          vec4 page1 = ${directUv ? 'directPage1' : 'texture2D(maskMap1, candidateUv)'};
          vec4 page2 = ${directUv ? 'directPage2' : 'texture2D(maskMap2, candidateUv)'};
          float candidate = slotCoverage(slot, page0, page1, page2);
          if (candidate <= 0.5) continue;
          float facing = dot(sideFacing[slot], normalValue);
          bool better = useDirectUv >= 0.5
            ? candidate > bestCoverage
            : facing >= bestFacing;
          if (better) {
            bestCoverage = candidate;
            bestFacing = facing;
            bestSlot = slot;
            bestAtlasUv = candidateUv;
          }
        }

        vec4 decal = vec4(0.0);
        if (bestSlot >= 0 && bestCoverage > 0.5) {
          vec4 source = sourceRegions[bestSlot];
          vec2 sourceSize = source.zw - source.xy;
          if (sourceSize.x > 0.000001 && sourceSize.y > 0.000001) {
            vec2 sectionUv = clamp((bestAtlasUv - source.xy) / sourceSize, 0.0, 1.0);
            vec4 paint = paintRegions[bestSlot];
            vec2 paintUv = mix(paint.xy, paint.zw, sectionUv);
            decal = texture2D(paintMap, paintUv);
            decal.a *= bestCoverage;
          }
        }

        vec3 colorValue = mix(baseColor, decal.rgb, decal.a);
        float diffuse = 0.42 + 0.58 * max(dot(normalValue, keyDirection), 0.0);
        float edge = pow(
          1.0 - max(dot(normalValue, normalize(cameraPosition - worldPositionValue)), 0.0),
          3.0
        );
        vec3 lit = colorValue * diffuse + vec3(0.06, 0.11, 0.14) * edge;
        gl_FragColor = vec4(lit, ${transparent ? 'mix(0.82, 1.0, decal.a)' : '1.0'});
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
    transparent,
    depthWrite: !transparent,
    side: THREE.DoubleSide,
  }));
  return material;
}

function calculateProjectionBounds(model, contract) {
  const sections = contract?.sections || [];
  const sectionBySlot = new Map(
    sections.map(section => [Number(section.slot_index), section])
  );
  const bounds = Array.from({ length: SECTION_COUNT }, () => ({
    valid: false,
    minimum: new THREE.Vector2(Infinity, Infinity),
    maximum: new THREE.Vector2(-Infinity, -Infinity),
  }));
  for (const section of sections) {
    const slot = Number(section.slot_index);
    const minimum = section.projection_minimum || [];
    const maximum = section.projection_maximum || [];
    if (
      !Number.isInteger(slot)
      || slot < 0
      || slot >= SECTION_COUNT
      || minimum.length !== 2
      || maximum.length !== 2
      || ![...minimum, ...maximum].map(Number).every(Number.isFinite)
    ) continue;
    bounds[slot].minimum.set(Number(minimum[0]), Number(minimum[1]));
    bounds[slot].maximum.set(Number(maximum[0]), Number(maximum[1]));
    bounds[slot].valid = bounds[slot].maximum.x > bounds[slot].minimum.x
      && bounds[slot].maximum.y > bounds[slot].minimum.y;
  }
  model.updateMatrixWorld(true);
  model.traverse(mesh => {
    if (!mesh.isMesh || mesh.geometry?.getAttribute('uv3')) return;
    const projectionSides = meshProjectionSides(mesh);
    if (!projectionSides) return;
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    if (!mesh.geometry.boundingBox) return;
    const worldBounds = mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld);
    for (let slot = 0; slot < SECTION_COUNT; slot += 1) {
      const geometrySide = SLOT_GEOMETRY_SIDES[slot];
      if ((projectionSides & (1 << geometrySide)) === 0) continue;
      const axis = sectionBySlot.get(slot)?.projection_axis || [];
      if (axis.length !== 4) continue;
      const target = bounds[slot];
      if (target.valid) continue;
      const axisX = Number(axis[0]);
      const axisY = Number(axis[1]);
      const scaleX = Number(axis[2]);
      const scaleY = Number(axis[3]);
      if (![axisX, axisY, scaleX, scaleY].every(Number.isFinite)) continue;
      const axisMinimumX = axisX === 0 ? worldBounds.min.x : axisX === 1 ? worldBounds.min.y : worldBounds.min.z;
      const axisMaximumX = axisX === 0 ? worldBounds.max.x : axisX === 1 ? worldBounds.max.y : worldBounds.max.z;
      const axisMinimumY = axisY === 0 ? worldBounds.min.x : axisY === 1 ? worldBounds.min.y : worldBounds.min.z;
      const axisMaximumY = axisY === 0 ? worldBounds.max.x : axisY === 1 ? worldBounds.max.y : worldBounds.max.z;
      const x0 = axisMinimumX * scaleX;
      const x1 = axisMaximumX * scaleX;
      const y0 = axisMinimumY * scaleY;
      const y1 = axisMaximumY * scaleY;
      target.minimum.x = Math.min(target.minimum.x, x0, x1);
      target.minimum.y = Math.min(target.minimum.y, y0, y1);
      target.maximum.x = Math.max(target.maximum.x, x0, x1);
      target.maximum.y = Math.max(target.maximum.y, y0, y1);
      target.valid = target.maximum.x > target.minimum.x && target.maximum.y > target.minimum.y;
    }
  });

  const locators = contract?.assembly?.locators || {};
  const front = locators.bumper_front;
  const rear = locators.bumper_rear;
  if (Array.isArray(front) && Array.isArray(rear)) {
    for (const slot of [2, 3, 4]) {
      const axis = sectionBySlot.get(slot)?.projection_axis || [];
      if (
        Number(axis[0]) !== 2
        || !bounds[slot].valid
        || sectionBySlot.get(slot)?.projection_minimum
      ) continue;
      const first = Number(front[2]) * Number(axis[2]);
      const second = Number(rear[2]) * Number(axis[2]);
      if (Number.isFinite(first) && Number.isFinite(second) && Math.abs(first - second) >= 0.5) {
        bounds[slot].minimum.x = Math.min(first, second);
        bounds[slot].maximum.x = Math.max(first, second);
      }
    }
  }
  return bounds;
}

function stableInspectionBounds(model) {
  const bounds = new THREE.Box3();
  let found = false;
  model.traverse(mesh => {
    if (!mesh.isMesh || mesh.visible === false || mesh.userData?.kfps_stock_part === false) return;
    const category = meshCategory(mesh);
    if (category !== 'paint' && category !== 'glass') return;
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    if (!mesh.geometry.boundingBox) return;
    bounds.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));
    found = true;
  });
  return found ? bounds : new THREE.Box3().setFromObject(model);
}

function inspectionFloorY(assembly, fallback) {
  const centers = Object.values(assembly?.wheel_centers || {});
  const radius = Number(assembly?.tire_radius);
  const yValues = centers
    .filter(value => Array.isArray(value) && value.length === 3)
    .map(value => Number(value[1]))
    .filter(Number.isFinite);
  return yValues.length === 4 && Number.isFinite(radius) && radius > 0
    ? Math.min(...yValues) - radius
    : fallback;
}

function frameModel(bounds, preferredDirection = null) {
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const extent = Math.max(size.x, size.y, size.z);
  const direction = preferredDirection?.clone() || new THREE.Vector3(1.08, 0.58, 1.32);
  if (direction.lengthSq() < 1e-8) direction.set(1.08, 0.58, 1.32);
  direction.normalize();
  controls.target.copy(center);
  camera.near = Math.max(0.01, extent / 250);
  camera.far = Math.max(100, extent * 50);
  camera.updateProjectionMatrix();

  const corners = [];
  for (const x of [bounds.min.x, bounds.max.x]) {
    for (const y of [bounds.min.y, bounds.max.y]) {
      for (const z of [bounds.min.z, bounds.max.z]) corners.push(new THREE.Vector3(x, y, z));
    }
  }
  const fits = distance => {
    camera.position.copy(center).addScaledVector(direction, distance);
    camera.lookAt(center);
    camera.updateMatrixWorld(true);
    let maxX = 0;
    let maxY = 0;
    for (const corner of corners) {
      const projected = corner.clone().project(camera);
      maxX = Math.max(maxX, Math.abs(projected.x));
      maxY = Math.max(maxY, Math.abs(projected.y));
    }
    return maxX <= 0.9 && maxY <= 0.78;
  };
  let lower = extent * 0.5;
  let upper = extent * 20;
  for (let iteration = 0; iteration < 28; iteration += 1) {
    const middle = (lower + upper) * 0.5;
    if (fits(middle)) upper = middle;
    else lower = middle;
  }
  camera.position.copy(center).addScaledVector(direction, upper * 1.03);
  controls.minDistance = extent * 0.45;
  controls.maxDistance = extent * 20;
  controls.update();
  homeCamera = camera.position.clone();
  homeTarget = controls.target.clone();
}

function addInspectionWheels(assembly) {
  const centers = assembly?.wheel_centers || {};
  const tireRadius = Number(assembly?.tire_radius);
  const tireWidth = Number(assembly?.tire_width);
  const rimRadius = Number(assembly?.rim_radius);
  const required = ['front_left', 'front_right', 'rear_left', 'rear_right'];
  if (
    assembly?.format !== 'kfps_fh6_local_vehicle_assembly_v1'
    || !required.every(name => Array.isArray(centers[name]) && centers[name].length === 3)
    || ![tireRadius, tireWidth, rimRadius].every(Number.isFinite)
    || tireRadius <= 0
    || tireWidth <= 0
    || rimRadius <= 0
    || rimRadius >= tireRadius
  ) {
    return 0;
  }

  const tireMaterial = new THREE.MeshStandardMaterial({
    color: 0x111419,
    roughness: 0.82,
    metalness: 0.02,
  });
  const rimMaterial = new THREE.MeshStandardMaterial({
    color: 0x929ba3,
    roughness: 0.36,
    metalness: 0.72,
  });
  const hubMaterial = new THREE.MeshStandardMaterial({
    color: 0x343b41,
    roughness: 0.46,
    metalness: 0.56,
  });
  const tubeRadius = (tireRadius - rimRadius) * 0.5;
  const torusRadius = rimRadius + tubeRadius;
  const tireGeometry = new THREE.TorusGeometry(torusRadius, tubeRadius, 14, 48);
  tireGeometry.scale(1, 1, tireWidth / (tubeRadius * 2));
  const rimGeometry = new THREE.CylinderGeometry(
    rimRadius,
    rimRadius,
    tireWidth * 1.03,
    40,
    1,
    false
  );
  const hubGeometry = new THREE.CylinderGeometry(
    rimRadius * 0.24,
    rimRadius * 0.24,
    tireWidth * 1.07,
    24
  );
  [tireMaterial, rimMaterial, hubMaterial].forEach(trackMaterial);
  [tireGeometry, rimGeometry, hubGeometry].forEach(geometry => trackedGeometries.add(geometry));
  const wheelGroup = new THREE.Group();
  wheelGroup.name = 'KFPS neutral locator-based inspection wheels';
  for (const name of required) {
    const position = centers[name].map(Number);
    if (!position.every(Number.isFinite)) return 0;
    const wheel = new THREE.Group();
    wheel.name = `KFPS inspection wheel ${name}`;
    wheel.position.set(...position);

    const tire = new THREE.Mesh(tireGeometry, tireMaterial);
    tire.rotation.y = Math.PI / 2;
    tire.name = `${wheel.name} tire`;
    wheel.add(tire);

    const rim = new THREE.Mesh(rimGeometry, rimMaterial);
    rim.rotation.z = Math.PI / 2;
    rim.name = `${wheel.name} rim`;
    wheel.add(rim);

    const hub = new THREE.Mesh(hubGeometry, hubMaterial);
    hub.rotation.z = Math.PI / 2;
    hub.name = `${wheel.name} hub`;
    wheel.add(hub);
    wheelGroup.add(wheel);
  }
  model.add(wheelGroup);
  return required.length;
}

function enabledForFilter(kind, filterName) {
  const enabled = new Float32Array(SECTION_COUNT);
  for (const section of renderContract.sections || []) {
    if (section.kind !== kind) continue;
    if (filterName === 'all' || section.filter === filterName) {
      enabled[Number(section.slot_index)] = 1;
    }
  }
  return enabled;
}

function setSectionFilter(filterName) {
  const bodyFilter = enabledForFilter('body', filterName);
  const glassFilter = enabledForFilter('glass', filterName);
  paintMaterials.forEach(material => {
    material.uniforms.enabledSlots.value = bodyFilter;
  });
  glassMaterials.forEach(material => {
    material.uniforms.enabledSlots.value = glassFilter;
  });
  sectionButtons.forEach(button => {
    button.classList.toggle('active', button.dataset.section === filterName);
  });
  requestRender();
}

async function loadPackage() {
  try {
    phase('manifest', 'Opening livery preview');
    const response = await fetch('./api/manifest', { cache: 'no-store', signal: loadAbort.signal });
    if (!response.ok) throw new Error(await response.text());
    const manifest = await response.json();
    title.textContent = manifest.livery?.title || 'Untitled full livery';
    vehicle.textContent = `${manifest.vehicle?.model_code || 'Unresolved car'} · Car ID ${manifest.livery?.target_car_id || '?'} · ${manifest.livery?.logical_placement_count || 0} placements`;
    const runtime = manifest.inspection_runtime || {};
    renderContract = runtime.render_contract || {};
    if (
      !runtime.local_mesh
      || renderContract.format !== RENDER_CONTRACT_FORMAT
    ) {
      throw new Error(
        'KFPS has not prepared this car\'s exact local FH6 livery mesh and section masks yet. '
        + 'Choose the FH6 Content folder and reopen the package.'
      );
    }
    const availableFilters = new Set(renderContract.filters || []);
    sectionButtons.forEach(button => {
      button.disabled = !availableFilters.has(button.dataset.section);
    });

    phase('assets', 'Loading car and livery textures');
    const loadResults = await Promise.all([
      loadTexture('./api/local-render/paint', true),
      loadTexture('./api/local-render/mask/0'),
      loadTexture('./api/local-render/mask/1'),
      loadTexture('./api/local-render/mask/2'),
      fetch('./api/local-mesh', {signal: loadAbort.signal}).then(response => {
        if (!response.ok) throw new Error(`Car mesh load failed (${response.status}).`);
        return response.arrayBuffer();
      }).then(buffer => {
        if (viewerDisposed) throw new Error('Viewer closed.');
        return new GLTFLoader().parseAsync(buffer, '');
      }).then(item => {
        trackObjectResources(item.scene);
        return item;
      }),
    ]);
    if (viewerDisposed) return;
    const assetBytes = resourceBytes();
    modelResourceBytes = assetBytes.geometry + assetBytes.textures;
    resize();
    if (resourceBytes().estimatedGpu > gpuBudgetBytes) throw new Error('The car exceeds the preview graphics memory budget.');
    phase('materials', 'Preparing car surfaces');
    const [paintTexture, mask0, mask1, mask2, gltf] = loadResults;
    model = gltf.scene;
    preparePartControls(model.userData?.kfps_part_options);
    model.traverse(child => {
      if (!child.isMesh) return;
      const category = meshCategory(child);
      child.userData.kfps_base_visible = category !== 'hidden';
      child.visible = child.userData.kfps_base_visible && meshPartVisible(child);
    });
    model.updateMatrixWorld(true);
    paintMaterials = [];
    glassMaterials = [];
    const projectionBounds = calculateProjectionBounds(model, renderContract);
    const materialCache = new Map();
    const liveryMaterial = (kind, allowedSides, projectionSides, directUv) => {
      const key = `${kind}:${allowedSides}:${projectionSides}:${directUv ? 1 : 0}`;
      if (!materialCache.has(key)) {
        const material = sectionAwareMaterial(
          paintTexture,
          [mask0, mask1, mask2],
          kind === 'glass' ? 0x202a31 : 0xc7cbd0,
          kind,
          allowedSides,
          projectionSides,
          projectionBounds,
          directUv,
          kind === 'glass'
        );
        materialCache.set(key, material);
        (kind === 'glass' ? glassMaterials : paintMaterials).push(material);
      }
      return materialCache.get(key);
    };
    let paintCount = 0;
    let glassCount = 0;
    let meshCount = 0;
    const neutralMaterials = new Map();
    const oldMaterials = new Set();
    model.traverse(child => {
      if (!child.isMesh) return;
      meshCount += 1;
      const category = meshCategory(child);
      if (category !== 'hidden') {
        for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
          if (material) oldMaterials.add(material);
        }
      }
      if (category === 'paint') {
        const directUv = Boolean(child.geometry.getAttribute('uv3'));
        child.material = liveryMaterial(
          'body',
          meshAllowedSides(child, category),
          meshProjectionSides(child),
          directUv
        );
        paintCount += 1;
      } else if (category === 'glass') {
        const directUv = Boolean(child.geometry.getAttribute('uv3'));
        child.material = liveryMaterial(
          'glass',
          meshAllowedSides(child, category),
          meshProjectionSides(child),
          directUv
        );
        child.renderOrder = 2;
        glassCount += 1;
      } else if (category === 'hidden') {
        child.visible = false;
      } else {
        if (!neutralMaterials.has(category)) {
          neutralMaterials.set(category, trackMaterial(new THREE.MeshStandardMaterial({
            color: category === 'dark' ? 0x11161b : 0x4b555d,
            roughness: 0.68, metalness: 0.15,
          })));
        }
        child.material = neutralMaterials.get(category);
      }
    });
    const retainedMaterials = new Set();
    model.traverse(child => {
      for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
        if (material) retainedMaterials.add(material);
      }
    });
    oldMaterials.forEach(material => {
      if (!retainedMaterials.has(material)) { material.dispose(); trackedMaterials.delete(material); }
    });
    const refreshPartSelection = () => {
      model.traverse(child => {
        if (!child.isMesh) return;
        child.visible = child.userData.kfps_base_visible !== false && meshPartVisible(child);
      });
      model.updateMatrixWorld(true);
      requestRender();
    };
    partControls.querySelectorAll('select').forEach(select => {
      select.addEventListener('change', () => {
        const selected = select.value === '' ? null : Number(select.value);
        selectedPartOptions.set(select.dataset.partType, selected);
        refreshPartSelection();
      });
    });
    if (!meshCount || !paintCount) {
      throw new Error('The local car conversion did not preserve FH6 livery-bearing paint geometry.');
    }
    const wheelCount = addInspectionWheels(renderContract.assembly);
    scene.add(model);
    model.updateMatrixWorld(true);
    modelBounds = stableInspectionBounds(model);
    floor.position.y = inspectionFloorY(renderContract.assembly, modelBounds.min.y) - 0.018;
    frameModel(modelBounds);
    setSectionFilter('all');
    phase('scene', 'Rendering first frame');
    modelReady = true;
    console.info(
      `KFPS section-aware inspector: ${paintCount} paint, ${glassCount} glass, `
      + `${meshCount} local meshes, ${wheelCount} neutral inspection wheels, `
      + `${(renderContract.sections || []).length} livery sections.`
    );
    requestRender();
  } catch (error) {
    failViewer(error?.message || String(error));
  }
}

function resetView() {
  const damping = controls.enableDamping;
  const rotating = controls.autoRotate;
  // Flush residual motion before restoring the saved camera pose.
  controls.enableDamping = false;
  controls.autoRotate = false;
  controls.update();
  camera.position.copy(homeCamera);
  controls.target.copy(homeTarget);
  controls.update();
  controls.enableDamping = damping;
  controls.autoRotate = rotating;
  requestRender();
}

function toggleAutoRotate() {
  controls.autoRotate = !controls.autoRotate;
  rotateButton.setAttribute('aria-pressed', String(controls.autoRotate));
  requestRender();
}

function selectSection(event) {
  const button = event.currentTarget;
  if (!button.disabled) setSectionFilter(button.dataset.section);
}

function resetFromDoubleClick() {
  resetView();
}

resetButton.addEventListener('click', resetView);
rotateButton.addEventListener('click', toggleAutoRotate);
sectionButtons.forEach(button => button.addEventListener('click', selectSection));
controls.addEventListener('change', requestRender);

function resize() {
  const width = Math.max(1, viewport.clientWidth);
  const height = Math.max(1, viewport.clientHeight);
  const pixelBudget = Math.min(
    (navigator.deviceMemory || 4) >= 8 ? 8388608 : 4194304,
    Math.max(1, (gpuBudgetBytes - modelResourceBytes) * .9 / 40),
  );
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(pixelBudget / (width * height)));
  if (width === renderWidth && height === renderHeight && pixelRatio === renderPixelRatio) return;
  const cameraWasHome = modelBounds !== null
    && camera.position.distanceToSquared(homeCamera) < 1e-8
    && controls.target.distanceToSquared(homeTarget) < 1e-8;
  const homeDirection = homeCamera.clone().sub(homeTarget);
  renderWidth = width;
  renderHeight = height;
  renderPixelRatio = pixelRatio;
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  if (cameraWasHome) frameModel(modelBounds, homeDirection);
}

function renderFrame(timestamp) {
  animationFrameId = 0;
  if (viewerDisposed || document.hidden) return;
  // Limit continuous animation to 60 Hz, including on high-refresh displays.
  if (lastFrameAt && timestamp - lastFrameAt < 15) { requestRender(); return; }
  const delta = lastFrameAt ? Math.min((timestamp - lastFrameAt) / 1000, .1) : 1 / 60;
  lastFrameAt = timestamp;
  const frameStart = performance.now();
  resize();
  controls.update(delta);
  try {
    renderer.render(scene, camera);
  } catch (error) {
    failViewer(error?.message || String(error));
    return;
  }
  renderedFrames += 1;
  frameTime = performance.now() - frameStart;
  frameTimeTotal += frameTime;
  frameTimePeak = Math.max(frameTimePeak, frameTime);
  if (modelReady && !firstFrameReady) {
    firstFrameReady = true;
    timings.firstFrame = Math.round(performance.now() - startedAt);
    window.clearTimeout(loadTimeout);
    setStatus('');
    viewerEvent('ready');
  }
  if (controls.autoRotate) requestRender();
}

function requestRender() {
  if (!viewerDisposed && !document.hidden && !animationFrameId) {
    renderRequests += 1;
    animationFrameId = requestAnimationFrame(renderFrame);
  }
}

function handleResize() {
  resize();
  requestRender();
}

function handleVisibilityChange() {
  lastFrameAt = 0;
  if (document.hidden && animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
  } else {
    resize();
    requestRender();
  }
}

function releaseRendererContext() {
  if (rendererContextReleased) return;
  rendererContextReleased = true;
  renderer.renderLists.dispose();
  renderer.dispose();
  renderer.forceContextLoss();
}

function disposeViewer(releaseContext = true) {
  if (!viewerDisposed) {
    viewerDisposed = true;
    window.clearTimeout(loadTimeout);
    loadAbort.abort();
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
    controls.removeEventListener('change', requestRender);
    controls.dispose();
    resetButton.removeEventListener('click', resetView);
    rotateButton.removeEventListener('click', toggleAutoRotate);
    sectionButtons.forEach(button => button.removeEventListener('click', selectSection));
    window.removeEventListener('dblclick', resetFromDoubleClick);
    window.removeEventListener('resize', handleResize);
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    canvas.removeEventListener('webglcontextlost', handleContextLost);
    partControls.replaceChildren();
    selectedPartOptions.clear();
    selectablePartGroups.clear();
    trackedSkeletons.forEach(skeleton => skeleton.dispose());
    trackedGeometries.forEach(geometry => geometry.dispose());
    trackedMaterials.forEach(material => material.dispose());
    trackedTextures.forEach(texture => {
      texture.dispose();
      if (typeof texture.image?.close === 'function') texture.image.close();
    });
    trackedSkeletons.clear();
    trackedGeometries.clear();
    trackedMaterials.clear();
    trackedTextures.clear();
    scene.clear();
    model = null;
    modelBounds = null;
    paintMaterials = [];
    glassMaterials = [];
  }
  if (releaseContext) releaseRendererContext();
  return viewerDiagnostics();
}

function viewerDiagnostics() {
  return {
    disposed: viewerDisposed,
    contextReleased: rendererContextReleased,
    animationActive: Boolean(animationFrameId),
    ready: firstFrameReady,
    timings: {...timings},
    bytes: resourceBytes(),
    device: {
      ...graphicsDevice,
      pixelRatio: renderPixelRatio,
    },
    quality: {scale: renderContract?.quality_scale || 1, source: renderContract?.quality_source || '',
      paintSize: renderContract?.paint_size || []},
    tracked: {
      geometries: trackedGeometries.size,
      materials: trackedMaterials.size,
      textures: trackedTextures.size,
      skeletons: trackedSkeletons.size,
    },
    renderer: {
      geometries: renderer.info.memory.geometries,
      textures: renderer.info.memory.textures,
      programs: renderer.info.programs?.length || 0,
    },
    rendering: {
      requests: renderRequests,
      frames: renderedFrames,
      cpuFrameMs: frameTime,
      meanCpuFrameMs: renderedFrames ? frameTimeTotal / renderedFrames : 0,
      peakCpuFrameMs: frameTimePeak,
      calls: renderer.info.render.calls,
      triangles: renderer.info.render.triangles,
    },
  };
}

function handleContextLost(event) {
  event.preventDefault();
  if (viewerDisposed) return;
  viewerEvent('context-lost', 'The graphics device lost the 3D preview. Reopen this livery to retry.');
  disposeViewer(false);
}

renderer.debug.onShaderError = () => { throw new Error('The graphics device could not compile the livery shader.'); };
canvas.addEventListener('webglcontextlost', handleContextLost);

window.addEventListener('dblclick', resetFromDoubleClick);
window.addEventListener('resize', handleResize);
document.addEventListener('visibilitychange', handleVisibilityChange);
window.addEventListener('pagehide', disposeViewer);
window.addEventListener('beforeunload', disposeViewer);
window.__kfpsDisposeViewer = disposeViewer;
window.__kfpsViewerDiagnostics = viewerDiagnostics;
window.__kfpsViewerBooted = true;
window.clearTimeout(window.__kfpsViewerBootTimer);
loadPackage();
resize();
requestRender();
