import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { chooseSurfaceSection, atlasToSectionPoint, selectionFrame } from './surface-math.mjs';
import { createNativeMaterialResolver } from './native-material.mjs';
import { resolveStagedNativeTexture } from './native-texture-binding.mjs';
import { placeholderWheelSpecs, placeholderFloorY } from './wheel-model.mjs';
import { uv3SeamSegments } from './inspection-tools.mjs';
import {t,errorText} from './i18n.mjs';
import { componentCatalog, initialComponentSelection, selectComponent, componentMeshVisible,
  inspectUv3, inspectNativeUvChannels, summarizeComponents, fidelityMessages, validateVehicleParts } from './component-model.mjs';

// Isolated authoring adaptation of the baseline KFPS inspector. Geometry,
// section masks remain shared with the baseline. Source/game parity is unverified;
// missing UV3 stays neutral instead of receiving a guessed world projection.
let editorPaintTexture = null;
export function updatePaintCanvas(source) {
  if (viewerDisposed || !modelReady) throw Error('The car preview is unavailable.');
  if (source.width !== renderContract.paint_size[0] || source.height !== renderContract.paint_size[1]) throw Error('Paint canvas size does not match this car.');
  if (!editorPaintTexture) {
    editorPaintTexture = trackTexture(new THREE.CanvasTexture(source));
    editorPaintTexture.colorSpace = THREE.SRGBColorSpace;
    editorPaintTexture.flipY = false;
    editorPaintTexture.anisotropy = graphicsDevice.anisotropy;
    const old = new Set();
    for (const material of [...paintMaterials, ...glassMaterials]) {
      old.add(material.uniforms.paintMap.value);
      material.uniforms.paintMap.value = editorPaintTexture;
    }
    for (const texture of old) {
      trackedTextures.delete(texture); texture.dispose(); texture.image?.close?.();
    }
  } else if (editorPaintTexture.image !== source) throw Error('Paint canvas identity changed.');
  editorPaintTexture.needsUpdate = true;
  requestRender();
}

export function isSceneReady() { return modelReady && !viewerDisposed; }
export function currentVehicleParts() { return partOverrides(); }
export function sceneState() { return { ...viewerDiagnostics(), ready: isSceneReady() }; }

function partOverrides(selection = selectedPartOptions) {
  const defaults=initialComponentSelection(partCatalog);
  return Object.fromEntries([...selection].filter(([partType,id])=>defaults.get(partType)!==id));
}

export function validatePartConfiguration(value) {
  return partOverrides(validateVehicleParts(value,partCatalog));
}

export function setVehicleParts(value) {
  if(viewerDisposed||!modelReady)throw Error('The car preview is unavailable.');
  selectedPartOptions=validateVehicleParts(value,partCatalog);
  applyPartSelection();
  return partOverrides();
}

let surfaceConfig = null;
let surfaceMaskPages = [];
const surfaceRaycaster = new THREE.Raycaster();
export function configureSurfaceEditing(config) {
  if (!config?.sections?.length || config.sections.some(section => !section.atlasToLocal)) throw Error('Native section mapping is unavailable.');
  surfaceConfig = config;
}
export function surfaceCameraEnabled(enabled) {
  if (viewerDisposed) return;
  controls.enabled = Boolean(enabled);
  if (!enabled) {
    controls.autoRotate = false;
    rotateButton.setAttribute('aria-pressed', 'false');
    const damping = controls.enableDamping;
    controls.enableDamping = false; controls.update(); controls.enableDamping = damping;
  }
  requestRender();
}
export function setSurfaceSelection(placement, bounds) {
  if (viewerDisposed) return;
  const section = placement && surfaceConfig?.sections.find(item => item.section === placement.section);
  const frame = section && selectionFrame(section, surfaceConfig.paint_size, placement, bounds);
  for (const material of [...paintMaterials, ...glassMaterials]) {
    const uniforms = material.uniforms;
    uniforms.selectedSlot.value = frame ? frame.slot : -1;
    if (frame) {
      uniforms.selectionX.value.fromArray(frame.x); uniforms.selectionY.value.fromArray(frame.y);
      uniforms.selectionBounds.value.fromArray(frame.bounds);
      uniforms.selectionColor.value.copy(selectionAccent);
    }
  }
  requestRender();
}
export function surfaceAtClient(clientX, clientY) {
  if (!isSceneReady() || !surfaceConfig || !surfaceMaskPages.length) return null;
  const box = canvas.getBoundingClientRect();
  if (!box.width || !box.height || clientX < box.left || clientY < box.top || clientX > box.right || clientY > box.bottom) return null;
  surfaceRaycaster.setFromCamera(new THREE.Vector2((clientX - box.left) / box.width * 2 - 1, 1 - (clientY - box.top) / box.height * 2), camera);
  const meshes = componentMeshes.filter(({mesh}) => effectivelyVisible(mesh)).map(({mesh}) => mesh);
  const intersections = surfaceRaycaster.intersectObjects(meshes, false);
  if (!intersections.length) return null;
  const nearest = intersections[0].distance;
  for (const hit of intersections) {
    // Never select paint through a nearer opaque/unsupported surface.
    if (hit.distance > nearest + 1e-4) break;
    const mesh = hit.object, category = meshCategory(mesh), uv = mesh.geometry.getAttribute('uv3');
    if (!['paint', 'glass'].includes(category) || !uv || !hit.face) continue;
    const local = mesh.worldToLocal(hit.point.clone()), vertices = mesh.geometry.getAttribute('position');
    const a = new THREE.Vector3().fromBufferAttribute(vertices, hit.face.a);
    const b = new THREE.Vector3().fromBufferAttribute(vertices, hit.face.b);
    const c = new THREE.Vector3().fromBufferAttribute(vertices, hit.face.c);
    const weights = THREE.Triangle.getBarycoord(local, a, b, c, new THREE.Vector3());
    if (!weights) continue;
    const indices = [hit.face.a, hit.face.b, hit.face.c], values = weights.toArray();
    const uv3 = [0, 0], normal = new THREE.Vector3(), normals = mesh.geometry.getAttribute('normal');
    for (let index = 0; index < 3; index++) {
      uv3[0] += uv.getX(indices[index]) * values[index]; uv3[1] += uv.getY(indices[index]) * values[index];
      if (normals) normal.addScaledVector(new THREE.Vector3().fromBufferAttribute(normals, indices[index]), values[index]);
    }
    if (!normals) normal.copy(hit.face.normal);
    normal.applyMatrix3(new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld)).normalize();
    const choice = chooseSurfaceSection({ uv3, normal: normal.toArray(), kind: category === 'glass' ? 'glass' : 'body',
      allowed: meshAllowedSides(mesh, category), sections: surfaceConfig.sections, pages: surfaceMaskPages,
      uvScale: surfaceConfig.uv_scale || [.5, 1],
      enabled: mesh.material?.uniforms?.enabledSlots?.value });
    if (!choice) continue;
    const point = atlasToSectionPoint(choice.section, choice.uv, surfaceConfig.paint_size);
    return { section: choice.section.section, point, atlasUv: choice.uv, world: hit.point.toArray(), normal: normal.toArray(),
      mesh: mesh.name, category, coverage: choice.coverage, screen: [clientX, clientY] };
  }
  return null;
}

const SECTION_COUNT = 11;
const RENDER_CONTRACT_FORMAT = 'kfps_fh6_section_render_contract_v3';
const ALL_BODY_SIDES = 0x1f;
const ALL_GLASS_SIDES = 0x7c0;
const canvas = document.querySelector('#canvas');
const viewport = document.querySelector('#viewport');
function displayColor(value) {
  // Resolve supported CSS4 theme colors once on theme changes, not during drags.
  const sample = document.createElement('canvas'); sample.width = sample.height = 1;
  const context = sample.getContext('2d', {willReadFrequently: true});
  context.fillStyle = value; context.fillRect(0, 0, 1, 1);
  const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
  return new THREE.Color().setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace);
}
let selectionAccent = displayColor(getComputedStyle(viewport).getPropertyValue('--editor-selection-border').trim());
const inspectionUniforms = {
  inspectionMode: {value: 0},
  inspectionPaint: {value: new THREE.Color()},
  inspectionGlass: {value: new THREE.Color()},
  inspectionUnsupported: {value: new THREE.Color()},
  inspectionNeutral: {value: new THREE.Color()},
};
const inspectionDeclarations = `
  uniform float inspectionMode;
  uniform vec3 inspectionPaint;
  uniform vec3 inspectionGlass;
  uniform vec3 inspectionUnsupported;
  uniform vec3 inspectionNeutral;
`;
function inspectionTheme() {
  const css=getComputedStyle(viewport),color=(name,fallback)=>displayColor(css.getPropertyValue(name).trim()||css.getPropertyValue(fallback).trim());
  inspectionUniforms.inspectionPaint.value.copy(color('--accent','--text'));
  inspectionUniforms.inspectionGlass.value.copy(color('--warn','--accent'));
  inspectionUniforms.inspectionUnsupported.value.copy(color('--danger','--text'));
  inspectionUniforms.inspectionNeutral.value.copy(color('--muted','--text'));
}
inspectionTheme();
const status = document.querySelector('#status');
const title = document.querySelector('#title');
const vehicle = document.querySelector('#vehicle');
const resetButton = document.querySelector('#reset');
const rotateButton = document.querySelector('#rotate');
const wheelsCheckbox = document.querySelector('#wheels');
let wheelsVisible = new URLSearchParams(window.location.search).get('wheels') !== '0';
let inspectionWheels = null;
wheelsCheckbox.checked = wheelsVisible;
const partControls = document.querySelector('#parts');
const componentStatus = document.querySelector('#componentStatus');
const fidelityStatus = document.querySelector('#fidelityStatus');
const fidelityDetails = document.querySelector('#fidelityDetails');
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
scene.background = displayColor(getComputedStyle(viewport).backgroundColor);
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
const nativeTextureSources = new Map();
const nativeDecodedBudgetBytes = Math.min(128 * 1024 * 1024, gpuBudgetBytes / 2);
let nativeDecodedBytes = 0;

function viewerEvent(event, message = '', details = {}) {
  try { window.__kfpsStudioDiagnostics?.scene(event, sceneDiagnosticMetrics()); } catch {}
  console.info('KFPS_VIEWER:' + JSON.stringify({event, message, ...details, diagnostics: viewerStatusDiagnostics()}));
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
  window.dispatchEvent(new CustomEvent('kfps-viewer-error', {detail: {message}}));
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

scene.add(new THREE.HemisphereLight(0xffffff, 0x343434, 2.0));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
keyLight.position.set(4.5, 8, 6);
scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0xffffff, 1.4);
rimLight.position.set(-6, 3, -5);
scene.add(rimLight);

const floor = trackObjectResources(new THREE.Mesh(
  new THREE.CircleGeometry(7, 96),
  new THREE.MeshStandardMaterial({ color: 0x242424, roughness: 0.86, metalness: 0.05 })
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
let partCatalog = componentCatalog([]);
let componentMeshes = [];
let componentCoverage = null;
let runtimeFidelity = null;
const nativeMaterials = createNativeMaterialResolver({maxEntries: 512});
let materialEvidence = {meshes: 0, nativeValuesApplied: 0, unresolvedTextures: 0, warnings: {}};
const partNotes = new Map();
let inspectionMode = 'off';
const inspectionLines = [];
let seamUnavailable = 0;

function clearInspectionLines() {
  for (const line of inspectionLines) {
    line.removeFromParent();
    line.geometry.dispose();
    line.material.dispose();
  }
  inspectionLines.length=0;
  seamUnavailable=0;
}

function buildInspectionLines() {
  clearInspectionLines();
  const color=displayColor(getComputedStyle(viewport).getPropertyValue('--accent').trim());
  for(const {mesh,evidence} of componentMeshes){
    if(!effectivelyVisible(mesh)||!['paint','glass'].includes(evidence.category))continue;
    if(evidence.uv3!=='present'){seamUnavailable++;continue;}
    const edges=uv3SeamSegments(mesh.geometry);
    if(!edges.available){seamUnavailable++;continue;}
    if(!edges.positions.length)continue;
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.BufferAttribute(edges.positions,3));
    const material=new THREE.LineBasicMaterial({color,depthTest:true,depthWrite:false,toneMapped:false});
    material.onBeforeCompile=shader=>{shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>','#include <project_vertex>\ngl_Position.z -= 0.00002 * gl_Position.w;');};
    const lines=new THREE.LineSegments(geometry,material);
    lines.name='KFPS UV3 inspection';lines.raycast=()=>{};lines.renderOrder=3;
    lines.userData.inspectionEdges={boundaries:edges.boundaries,discontinuities:edges.discontinuities};
    mesh.add(lines);inspectionLines.push(lines);
  }
}

export function inspectionState({resources=false}={}) {
  return {mode:inspectionMode,ready:isSceneReady(),disposed:viewerDisposed,
    sections:(renderContract?.sections||[]).map(section=>section.section),
    unsupportedMeshes:(componentCoverage?.uv3.visible_unmapped||0)+(componentCoverage?.unmapped_visual_surfaces?.filter(item=>item.visible).length||0),
    lineSegments:inspectionLines.reduce((sum,line)=>sum+line.geometry.getAttribute('position').count/2,0),
    ownedGeometries:inspectionLines.length,seamUnavailable,
    ...(resources?{
      materialIdentity:componentMeshes.map(({mesh})=>(Array.isArray(mesh.material)?mesh.material:[mesh.material]).map(item=>item.uuid).join(',')).join('|'),
      geometryIdentity:componentMeshes.map(({mesh})=>mesh.geometry.uuid).join('|'),
    }:{})};
}

export function setInspectionMode(mode) {
  if(!['off','paintability','uv-seams'].includes(mode))throw Error('Unknown inspection mode.');
  if(!isSceneReady())return false;
  if(mode===inspectionMode)return true;
  clearInspectionLines();
  inspectionMode=mode;inspectionUniforms.inspectionMode.value=mode==='paintability'?1:mode==='uv-seams'?2:0;
  if(mode==='uv-seams')buildInspectionLines();
  requestRender();window.dispatchEvent(new Event('kfps-inspection-change'));
  return true;
}

// Reuse the normal bounds fitter; native masks choose the close-up, not car-specific guesses.
export function focusInspectionSection(name) {
  if(!isSceneReady()||!surfaceMaskPages.length)return false;
  const section=renderContract.sections.find(item=>item.section===name);
  if(!section)return false;
  const bounds=new THREE.Box3(),normal=new THREE.Vector3(),vertices=[new THREE.Vector3(),new THREE.Vector3(),new THREE.Vector3()];
  const enabled=new Float32Array(SECTION_COUNT);enabled[section.slot_index]=1;
  for(const {mesh,evidence} of componentMeshes){
    const kind=evidence.category==='glass'?'glass':evidence.category==='paint'?'body':null;
    if(kind!==section.kind||evidence.uv3!=='present'||!effectivelyVisible(mesh))continue;
    const position=mesh.geometry.getAttribute('position'),uv=mesh.geometry.getAttribute('uv3'),index=mesh.geometry.index;
    const count=index?.count??position.count,normalMatrix=new THREE.Matrix3().getNormalMatrix(mesh.matrixWorld);
    for(let i=0;i<count;i+=3){
      const ids=[0,1,2].map(j=>index?index.getX(i+j):i+j),atlas=[0,0];
      ids.forEach((id,j)=>{vertices[j].fromBufferAttribute(position,id);atlas[0]+=uv.getX(id)/3;atlas[1]+=uv.getY(id)/3;});
      THREE.Triangle.getNormal(...vertices,normal);normal.applyMatrix3(normalMatrix).normalize();
      const choice=chooseSurfaceSection({uv3:atlas,normal:normal.toArray(),kind,allowed:meshAllowedSides(mesh,evidence.category),
        sections:renderContract.sections,pages:surfaceMaskPages,uvScale:surfaceConfig?.uv_scale||[renderContract.uv_contract?.u_scale??.5,renderContract.uv_contract?.v_scale??1],enabled});
      if(choice?.section.section===name)for(const vertex of vertices)bounds.expandByPoint(vertex.clone().applyMatrix4(mesh.matrixWorld));
    }
  }
  if(bounds.isEmpty())return false;
  const savedCamera=homeCamera.clone(),savedTarget=homeTarget.clone(),damping=controls.enableDamping;
  controls.autoRotate=false;rotateButton.setAttribute('aria-pressed','false');
  controls.enableDamping=false;controls.update();
  const direction=new THREE.Vector3().fromArray(section.facing);
  if(Math.abs(direction.y)>.99)direction.z=.001;
  frameModel(bounds,direction);
  homeCamera.copy(savedCamera);homeTarget.copy(savedTarget);controls.enableDamping=damping;
  requestRender();return true;
}

function inspectUnsupportedMaterial(material, unsupported) {
  // Keep the exact original material, maps and geometry; Off is a uniform-only no-op.
  material.onBeforeCompile=shader=>{
    Object.assign(shader.uniforms,inspectionUniforms);
    shader.fragmentShader=shader.fragmentShader.replace('#include <common>','#include <common>\n'+inspectionDeclarations)
      .replace('#include <opaque_fragment>',`${unsupported ? `if(inspectionMode>0.5){
        float stripe=step(0.5,fract((gl_FragCoord.x+gl_FragCoord.y)/12.0));
        outgoingLight=mix(inspectionNeutral,inspectionUnsupported,stripe);diffuseColor.a=1.0;
      }` : 'if(inspectionMode>0.5 && inspectionMode<1.5){outgoingLight=inspectionNeutral*0.45;diffuseColor.a=1.0;}'}\n#include <opaque_fragment>`);
  };
  material.customProgramCacheKey=()=>`kfps-inspection-neutral-v1:${unsupported}`;
  return material;
}

function setStatus(message, error = false) {
  status.textContent = errorText(message);
  status.classList.toggle('hidden', !message);
  status.classList.toggle('error', error);
}

function meshIdentity(mesh) {
  return `${mesh.name || ''} ${mesh.material?.name || ''}`.toLowerCase();
}

function meshCategory(mesh) {
  if (['shadow-only', 'wheel-motion-blur'].includes(mesh.userData?.kfps_static_render_purpose)) return 'hidden';
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
  if (Number.isInteger(declared) && declared >= 0 && declared < (1 << SECTION_COUNT)) {
    return declared;
  }
  return category === 'glass' ? ALL_GLASS_SIDES : ALL_BODY_SIDES;
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
  return Array.isArray(values) ? values.filter(Number.isSafeInteger) : [];
}

function meshPartVisible(mesh) {
  return componentMeshVisible(mesh.userData, selectedPartOptions);
}

function partTypeLabel(value) {
  return t(String(value || 'Car part')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' '));
}
function componentDisplayLabel(option){
  const kind=option.stock?t('Stock'):option.level!==null?t`Level ${option.level}`:t('Option');
  return `${kind} (ID ${option.id})${option.empty===true?t(' - empty'):''}${option.available===false?t(' - unavailable'):''}`;
}

function preparePartControls(options) {
  partCatalog = componentCatalog(options, runtimeFidelity?.body_compatibility);
  selectedPartOptions = initialComponentSelection(partCatalog);
  partNotes.clear();
  partControls.replaceChildren();
  for (const [partType, optionsForPart] of partCatalog.groups) {
    const row = document.createElement('div');
    row.className = 'component-row';
    const label = document.createElement('label');
    const select = document.createElement('select');
    const controlId = `component-${partNotes.size}`;
    label.htmlFor = controlId;
    label.textContent = partTypeLabel(partType);
    select.id = controlId;
    select.dataset.partType = partType;
    select.title = t('Choose a declared component. Choices are saved in the layout, not installed in the game. Only explicit source body relationships constrain this list.');
    {
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = t('No component selected');
      placeholder.disabled = true;
      select.append(placeholder);
    }
    for (const option of optionsForPart) {
      const element = document.createElement('option');
      element.value = String(option.id);
      element.textContent = componentDisplayLabel(option);
      element.disabled = option.available === false;
      element.title = errorText(option.reason);
      select.append(element);
    }
    select.value = selectedPartOptions.get(partType) === null ? '' : String(selectedPartOptions.get(partType));
    const note = document.createElement('small');
    note.id = `${controlId}-status`;
    select.setAttribute('aria-describedby', note.id);
    row.append(label, select, note);
    partNotes.set(partType, note);
    partControls.append(row);
  }
  partControls.classList.toggle('hidden', partControls.childElementCount === 0);
}

function effectivelyVisible(mesh) {
  for (let current = mesh; current; current = current.parent) if (!current.visible) return false;
  return true;
}

function nativeWheelState() {
  const meshes = componentMeshes.filter(({mesh, evidence}) => evidence.base_visible && meshPartVisible(mesh)
    && mesh.userData?.kfps_part_type === 'WheelStyle'
    && mesh.userData?.kfps_static_render_purpose === 'surface');
  const instances = new Set(meshes.map(({mesh}) => mesh.userData.kfps_instance_identity).filter(Boolean));
  const source = model?.userData?.kfps_conversion_coverage?.native_wheel_geometry;
  const complete = instances.size >= 4 && source?.assembly_complete === true
    && source.runtime_fitment_applied === true && source.tire_geometry_present === true;
  return {meshes: meshes.length, instances: instances.size,
    visibleMeshes: meshes.filter(({mesh}) => effectivelyVisible(mesh)).length, complete};
}

function applyWheelVisibility() {
  const standIns = inspectionWheels?.visible && inspectionWheels.children.length === 4;
  for (const {mesh, evidence} of componentMeshes) {
    if (mesh.userData?.kfps_part_type === 'WheelStyle') {
      mesh.visible = evidence.base_visible && meshPartVisible(mesh) && !standIns;
    }
  }
}

function refreshComponentCoverage() {
  const meshes = componentMeshes.map(record => ({...record.evidence,
    selected: meshPartVisible(record.mesh), visible: effectivelyVisible(record.mesh)}));
  componentCoverage = summarizeComponents(partCatalog, selectedPartOptions, meshes);
  const partDetails = [];
  for (const group of componentCoverage.groups) {
    const note = partNotes.get(group.part_type), selected = group.options.find(option => option.id === group.selected);
    const select = note.previousElementSibling;
    select.value=group.selected===null?'':String(group.selected);
    for (const element of select.options) {
      if(element.value==='')continue;
      const option=group.options.find(candidate=>candidate.id===Number(element.value));
      element.disabled=option.available===false||option.compatible===false;
      element.textContent=componentDisplayLabel(option)+(option.compatible===false?t(' - other body'):'');
    }
    if (!selected) { note.textContent = t('No compatible component selected. This part is hidden.'); continue; }
    const empty = t(selected.empty === true ? 'Declared empty option' : 'Empty or missing: not confirmed');
    const parent = selected.parent;
    const parentText = parent.id === null ? t('Parent not supplied.') : t`Parent upgrade ${parent.id}; stock parent: ${parent.parent_is_stock===null?t('unknown'):t(String(parent.parent_is_stock))} (${parent.mapped_body_option===null?t('relationship unresolved'):t`mapped to body ${parent.mapped_body_option}; game fitment unverified`}).`;
    const unavailable=group.options.filter(option=>option.available===false).map(option=>`ID ${option.id}: ${errorText(option.reason||'Geometry unavailable')}`).join(' ');
    partDetails.push(t`${partTypeLabel(group.part_type)}: ${selected.mesh_count ? t`${selected.mesh_count} tagged meshes` : empty}; ${selected.shared_unconditional_mesh_count} unconditional shared. ${selected.missing_uv3} without usable UV3. ${parentText}${unavailable ? t` Unavailable: ${unavailable}` : ''}`);
    const notes = [];
    if (!selected.mesh_count) notes.push(t(selected.empty ? 'No part fitted.' : 'Geometry unavailable.'));
    if (selected.missing_uv3) notes.push(t`${selected.missing_uv3} surfaces cannot be painted.`);
    if (parent.id !== null) notes.push(t(parent.mapped_body_option === null ? 'Body fitment unverified.' : 'Body-linked option.'));
    if (group.options.some(option => option.available === false)) notes.push(t('Some options unavailable.'));
    note.textContent = notes.join(' ') || t('Available.');
  }
  componentStatus.textContent = partCatalog.groups.size
    ? t`${componentCoverage.visible_mesh_count}/${componentCoverage.mesh_count} source mesh nodes visible. ${Object.keys(partOverrides()).length} configuration overrides saved with the layout.`
    : t('No component options declared in this asset. Source completeness is unverified.');
  const wheelState = {count: inspectionWheels?.children.length || 0, visible: inspectionWheels?.visible ?? false, native: nativeWheelState()};
  const messages = fidelityMessages(componentCoverage, runtimeFidelity, wheelState, materialEvidence);
  const fitment = renderContract?.assembly?.wheel_fitment;
  if (fitment) {
    messages.push(fitment.reason);
    const sizes = placeholderWheelSpecs(renderContract.assembly);
    for (const axle of ['front', 'rear']) {
      const size = sizes.find(wheel => wheel.corner === `${axle}_left`)?.nominalSize;
      if (size) messages.push(t`${t(axle === 'front' ? 'Front' : 'Rear')} reference size: ${size.width_mm}/${size.aspect_percent} R${size.rim_diameter_in}. Nominal unloaded dimensions; runtime suspension and body-kit fitment are unverified.`);
    }
  }
  const lodPolicy=model?.userData?.kfps_conversion_coverage?.lod_policy;
  if(typeof lodPolicy==='string')messages.push(t`LOD policy: ${errorText(lodPolicy)}`);
  document.querySelector('#fitmentStatus').textContent=partCatalog.bodyParents.size
    ? t`Source mapping covers ${partCatalog.bodyParents.size} parent upgrades. Other relationships remain unresolved; game fitment is unverified.`
    : t('Manual configuration: body-kit fitment relationships are unresolved. Combining parts can overlap or leave gaps; IDs are not treated as compatibility proof.');
  const unmapped = componentCoverage.uv3.visible_unmapped;
  fidelityStatus.textContent = `${t('Game rendering unverified.')} ${unmapped ? t`${unmapped} visible surfaces cannot be painted. ` : ''}${wheelState.visible ? t('Placeholder wheels.') : ''}`.trim();
  fidelityDetails.replaceChildren();
  for (const message of [...messages, ...partDetails]) {
    const item = document.createElement('li'); item.textContent = errorText(message); fidelityDetails.append(item);
  }
}

function changePartSelection(event) {
  const select = event.target.closest('select[data-part-type]');
  if (viewerDisposed || !modelReady || !select || select.disabled) return;
  const partType = select.dataset.partType;
  if (!selectComponent(partCatalog, selectedPartOptions, partType, select.value === '' ? null : Number(select.value))) {
    select.value = selectedPartOptions.get(partType) === null ? '' : String(selectedPartOptions.get(partType));
    return;
  }
  applyPartSelection();
  window.dispatchEvent(new Event('kfps-component-selection'));
  viewerEvent('component-selection', 'Preview selection changed; game configuration unverified.', {partType, optionId: selectedPartOptions.get(partType)});
}

function applyPartSelection() {
  clearInspectionLines();
  for (const {mesh,evidence} of componentMeshes)mesh.visible=evidence.base_visible&&meshPartVisible(mesh);
  applyWheelVisibility();
  model.updateMatrixWorld(true);
  modelBounds=stableInspectionBounds(model);
  refreshComponentCoverage();
  if(inspectionMode==='uv-seams')buildInspectionLines();
  window.dispatchEvent(new Event('kfps-inspection-change'));
  requestRender();
}

async function loadBitmap(url) {
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
  return bitmap;
}

async function loadTexture(url, color = false) {
  const texture = trackTexture(new THREE.Texture(await loadBitmap(url)));
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

async function qualifiedNativeTexture(mesh, nativeAssets, cache, uvChannels) {
  const resolved = resolveStagedNativeTexture(mesh.userData, {
    availableUvChannels: uvChannels,
    sourceUvTransforms: mesh.userData?.kfps_native_texcoord_transforms,
    uvPipeline: mesh.userData?.kfps_native_uv_pipeline,
  }, nativeAssets);
  if (!resolved) return null;
  const {binding, asset} = resolved;
  const key = JSON.stringify([binding.assetKey, binding.texture, binding.material]);
  if (!cache.has(key)) {
    const {width, height} = asset.metadata;
    const decodedBytes = width * height * 4;
    const newSource = !nativeTextureSources.has(binding.assetKey);
    // Bound allocations before decoding. Distinct material transforms share the
    // decoded bitmap, while each GPU texture is conservatively budgeted in full.
    if (Math.max(width, height) > renderer.capabilities.maxTextureSize
      || resourceBytes().estimatedGpu + Math.ceil(decodedBytes * 4 / 3) > gpuBudgetBytes
      || (newSource && nativeDecodedBytes + decodedBytes > nativeDecodedBudgetBytes)) {
      const warning = 'native-texture-memory-budget';
      materialEvidence.warnings[warning] = (materialEvidence.warnings[warning] || 0) + 1;
      return null;
    }
    let bitmap = nativeTextureSources.get(binding.assetKey);
    if (!bitmap) {
      bitmap = await loadBitmap(`./api/native-texture/${binding.assetKey}`);
      if (viewerDisposed) { bitmap.close(); throw Error('Viewer closed.'); }
      if (bitmap.width !== width || bitmap.height !== height) {
        bitmap.close();
        throw Error('A native material texture has unexpected dimensions. Prepare the car again.');
      }
      nativeTextureSources.set(binding.assetKey, bitmap);
      nativeDecodedBytes += decodedBytes;
    }
    const texture = trackTexture(new THREE.Texture(bitmap));
    const wrap = {repeat: THREE.RepeatWrapping, clamp: THREE.ClampToEdgeWrapping, mirror: THREE.MirroredRepeatWrapping};
    texture.channel = binding.texture.channel;
    texture.colorSpace = binding.texture.colorSpace === 'srgb' ? THREE.SRGBColorSpace : THREE.LinearSRGBColorSpace;
    texture.flipY = binding.texture.flipY;
    texture.matrixAutoUpdate = false;
    texture.matrix.set(...binding.texture.matrix);
    texture.wrapS = wrap[binding.texture.wrapS];
    texture.wrapT = wrap[binding.texture.wrapT];
    texture.needsUpdate = true;
    const {slot, alphaPolicy, ...material} = binding.material;
    cache.set(key, {key, texture, options: {...material, [slot]: texture}, evidence: binding.evidence});
  }
  return cache.get(key);
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
    const projectionAxis = section.projection_axis || [0, 0, 0, 0];
    const projectionMask = section.projection_mask_region || [0, 0, 0, 0];
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
  transparent = false,
  nativeOptions = null
) {
  const arrays = sectionArrays(renderContract, kind, projectionBounds);
  transparent = transparent || nativeOptions?.transparent === true;
  const material = new THREE.MeshPhysicalMaterial({
    color: baseColor,
    roughness: transparent ? 0.16 : 0.32,
    metalness: transparent ? 0 : 0.22,
    clearcoat: transparent ? 0 : 0.8,
    clearcoatRoughness: 0.18,
    opacity: transparent ? 0.82 : 1,
    transparent,
    depthWrite: !transparent,
    side: THREE.DoubleSide,
    ...physicalOptions(nativeOptions),
  });
  material.uniforms = {
      ...inspectionUniforms,
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
      nativeUvScale: { value: new THREE.Vector2(renderContract.uv_contract?.u_scale ?? .5, renderContract.uv_contract?.v_scale ?? 1) },
      baseColor: { value: new THREE.Color(baseColor) },
      selectedSlot: { value: -1 },
      selectionX: { value: new THREE.Vector3() },
      selectionY: { value: new THREE.Vector3() },
      selectionBounds: { value: new THREE.Vector4() },
      selectionColor: { value: selectionAccent.clone() },
    };
  const vertexDeclarations = `
      ${directUv ? '#ifndef USE_UV3\nattribute vec2 uv3;\n#endif' : ''}
      uniform vec2 nativeUvScale;
      varying vec2 atlasUv;
      varying vec3 worldNormalValue;
      varying vec3 worldPositionValue;
  `;
  const vertexMapping = `
        atlasUv = ${directUv ? 'uv3 * nativeUvScale' : 'vec2(0.0)'};
        vec4 nativeWorldPosition = modelMatrix * vec4(position, 1.0);
        worldPositionValue = nativeWorldPosition.xyz;
        worldNormalValue = inverseTransformDirection(transformedNormal, viewMatrix);
  `;
  const fragmentDeclarations = `
      ${inspectionDeclarations}
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
      uniform int selectedSlot;
      uniform vec3 selectionX;
      uniform vec3 selectionY;
      uniform vec4 selectionBounds;
      uniform vec3 selectionColor;
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

  `;
  const decalMapping = `
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
        float selectionLine = 0.0;
        if (bestSlot >= 0 && bestCoverage > 0.5) {
          vec4 source = sourceRegions[bestSlot];
          vec2 sourceSize = source.zw - source.xy;
          if (sourceSize.x > 0.000001 && sourceSize.y > 0.000001) {
            vec2 sectionUv = clamp((bestAtlasUv - source.xy) / sourceSize, 0.0, 1.0);
            vec4 paint = paintRegions[bestSlot];
            vec2 paintUv = mix(paint.xy, paint.zw, sectionUv);
            decal = texture2D(paintMap, paintUv);
            decal.a *= bestCoverage;
            if (bestSlot == selectedSlot) {
              vec3 coordinate = vec3(paintUv, 1.0);
              vec2 local = vec2(dot(selectionX, coordinate), dot(selectionY, coordinate));
              vec2 distanceToEdge = min(local - selectionBounds.xy, selectionBounds.zw - local);
              vec2 width = max(fwidth(local) * 1.5, vec2(0.001));
              if (all(greaterThanEqual(distanceToEdge, -width))) {
                selectionLine = 1.0 - smoothstep(0.0, 1.0, min(abs(distanceToEdge.x) / width.x, abs(distanceToEdge.y) / width.y));
              }
            }
          }
        }

        diffuseColor.rgb = mix(diffuseColor.rgb, decal.rgb, decal.a);
        diffuseColor.rgb = mix(diffuseColor.rgb, selectionColor, selectionLine);
        diffuseColor.a = ${transparent ? 'mix(opacity, 1.0, decal.a)' : '1.0'};
  `;
  // Keep Three's lighting/material pipeline; only native decal sampling is custom.
  material.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, material.uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\n' + vertexDeclarations)
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n' + vertexMapping);
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\n' + fragmentDeclarations)
      .replace('#include <color_fragment>', '#include <color_fragment>\n' + decalMapping)
      .replace('#include <emissivemap_fragment>', '#include <emissivemap_fragment>\ntotalEmissiveRadiance = mix(totalEmissiveRadiance, selectionColor, selectionLine);');
    shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>',`
      if(inspectionMode>0.5 && (inspectionMode<1.5 || useDirectUv<0.5)){
        float stripe=step(0.5,fract((gl_FragCoord.x+gl_FragCoord.y)/12.0));
        vec3 eligibleColor=${transparent ? 'mix(inspectionGlass,inspectionNeutral,step(0.72,fract(gl_FragCoord.x/7.0))*step(0.72,fract(gl_FragCoord.y/7.0)))' : 'inspectionPaint'};
        outgoingLight=useDirectUv<0.5?mix(inspectionNeutral,inspectionUnsupported,stripe):bestSlot>=0?eligibleColor:inspectionNeutral*0.45;
        diffuseColor.a=1.0;
      }
      #include <opaque_fragment>`);
  };
  material.customProgramCacheKey = () => `kfps-native-uv-pbr-inspection-v1:${directUv}:${transparent}`;
  return trackMaterial(material);
}

function physicalOptions(options) {
  if (!options) return {};
  return {...options, color: new THREE.Color().setRGB(...options.color, THREE.LinearSRGBColorSpace),
    emissive: new THREE.Color().setRGB(...options.emissive, THREE.LinearSRGBColorSpace)};
}

function stableInspectionBounds(model) {
  const bounds = new THREE.Box3();
  let found = false;
  for (const {mesh} of componentMeshes) {
    if (!effectivelyVisible(mesh)) continue;
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    if (!mesh.geometry.boundingBox) continue;
    bounds.union(mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrixWorld));
    found = true;
  }
  return found ? bounds : modelBounds?.clone() || new THREE.Box3().setFromObject(model);
}

function inspectionFloorY(assembly, fallback) {
  return placeholderFloorY(assembly, fallback);
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
  const specs = placeholderWheelSpecs(assembly);
  if (!specs.length) return 0;

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
  [tireMaterial, rimMaterial, hubMaterial].forEach(trackMaterial);
  const geometryCache = new Map();
  const wheelGroup = new THREE.Group();
  wheelGroup.name = 'KFPS placeholder wheels';
  wheelGroup.visible = wheelsVisible;
  for (const spec of specs) {
    const {corner: name, center: position, radius: tireRadius, width: tireWidth, rimRadius} = spec;
    const geometryKey = JSON.stringify([tireRadius, tireWidth, rimRadius]);
    if (!geometryCache.has(geometryKey)) {
      const tubeRadius = (tireRadius - rimRadius) * 0.5;
      const tire = new THREE.TorusGeometry(rimRadius + tubeRadius, tubeRadius, 16, 48);
      tire.scale(1, 1, tireWidth / (tubeRadius * 2));
      const rim = new THREE.CylinderGeometry(rimRadius, rimRadius, tireWidth * .9, 40, 1, false);
      const hub = new THREE.CylinderGeometry(rimRadius * .24, rimRadius * .24, tireWidth * .92, 24);
      [tire, rim, hub].forEach(geometry => trackedGeometries.add(geometry));
      geometryCache.set(geometryKey, {tire, rim, hub});
    }
    const geometries = geometryCache.get(geometryKey);
    const wheel = new THREE.Group();
    wheel.name = `KFPS inspection wheel ${name}`;
    wheel.position.set(...position);

    const tire = new THREE.Mesh(geometries.tire, tireMaterial);
    tire.rotation.y = Math.PI / 2;
    tire.name = `${wheel.name} tire`;
    wheel.add(tire);

    const rim = new THREE.Mesh(geometries.rim, rimMaterial);
    rim.rotation.z = Math.PI / 2;
    rim.name = `${wheel.name} rim`;
    wheel.add(rim);

    const hub = new THREE.Mesh(geometries.hub, hubMaterial);
    hub.rotation.z = Math.PI / 2;
    hub.name = `${wheel.name} hub`;
    wheel.add(hub);
    wheelGroup.add(wheel);
  }
  model.add(wheelGroup);
  model.updateMatrixWorld(true);
  for (const wheel of wheelGroup.children) {
    const bounds = new THREE.Box3().setFromObject(wheel);
    wheel.userData.measuredSize = bounds.getSize(new THREE.Vector3()).toArray();
  }
  inspectionWheels = wheelGroup;
  applyWheelVisibility();
  return specs.length;
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
    title.textContent = manifest.livery?.title || t('Untitled full livery');
    vehicle.textContent = t`${manifest.vehicle?.model_code || t('Unresolved car')} · Car ID ${manifest.livery?.target_car_id || '?'} · ${manifest.livery?.logical_placement_count || 0} placements`;
    const runtime = manifest.inspection_runtime || {};
    runtimeFidelity = runtime.fidelity || null;
    renderContract = runtime.render_contract || {};
    if (
      !runtime.local_mesh
      || renderContract.format !== RENDER_CONTRACT_FORMAT
    ) {
      throw new Error(
        'KFPS has not prepared this car\'s local FH6 inspection mesh and section masks yet. '
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
    // RGBA stores four independent masks. A 2D canvas would premultiply the RGB
    // masks by the fourth mask and destroy valid RGB samples where alpha is zero.
    surfaceMaskPages = await Promise.all([0, 1, 2].map(async index => {
      const response = await fetch(`./api/local-render/mask-raw/${index}`, { signal: loadAbort.signal });
      if (!response.ok) throw Error('Native mask pixels are unavailable. Restart Livery Studio to use the updated backend.');
      const [width, height] = renderContract.mask_size, expected = 8 + width * height * 4;
      if (Number(response.headers.get('Content-Length')) !== expected) throw Error('Native mask pixel length does not match the car.');
      const buffer = await response.arrayBuffer(), header = new DataView(buffer);
      if (buffer.byteLength !== expected || header.getUint32(0, true) !== width || header.getUint32(4, true) !== height) throw Error('Native mask dimensions do not match the car.');
      return { width, height, data: new Uint8Array(buffer, 8) };
    }));
    if (viewerDisposed) return;
    model = gltf.scene;
    preparePartControls(model.userData?.kfps_part_options);
    const uvCache = new Map(), nativeUvCache = new Map();
    componentMeshes = [];
    model.traverse(child => {
      if (!child.isMesh) return;
      const category = meshCategory(child);
      if (!uvCache.has(child.geometry)) uvCache.set(child.geometry, {
        uv3: inspectUv3(child.geometry),
      });
      componentMeshes.push({mesh: child, evidence: {
        id: componentMeshes.length, name: child.name, part_type: String(child.userData?.kfps_part_type || ''),
        option_ids: meshPartOptionIds(child), category, ...uvCache.get(child.geometry),
        native_uv: inspectNativeUvChannels(child.geometry, {
          ...child.userData?.kfps_imported_uv_sha256, ...child.userData?.kfps_uv_sha256}, nativeUvCache),
        unpaintable_surface_role: child.userData?.kfps_unpaintable_surface_role || null,
        uv_sha256: child.userData?.kfps_uv_sha256 || null,
        source_visible: effectivelyVisible(child), base_visible: child.visible !== false && category !== 'hidden',
      }});
    });
    for (const {mesh, evidence} of componentMeshes) mesh.visible = evidence.base_visible && meshPartVisible(mesh);
    model.updateMatrixWorld(true);
    paintMaterials = [];
    glassMaterials = [];
    // Fidelity inspection never invents UVs. Legacy projection shader uniforms
    // remain zeroed; both missing and invalid UV3 render the neutral base material.
    const projectionBounds = [];
    const materialCache = new Map();
    const liveryMaterial = (kind, allowedSides, projectionSides, directUv, nativeOptions) => {
      const key = `${kind}:${allowedSides}:${projectionSides}:${directUv ? 1 : 0}:${JSON.stringify(nativeOptions)}`;
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
          kind === 'glass',
          nativeOptions
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
    const nativeTextures = new Map();
    const oldMaterials = new Set();
    materialEvidence = {meshes: 0, nativeValuesApplied: 0, unresolvedTextures: 0, textureBindings: 0, textureAssets: 0, warnings: {}};
    for (const {mesh: child, evidence} of componentMeshes) {
      meshCount += 1;
      const category = evidence.category;
      const validUvChannels = evidence.native_uv.available.filter(channel => !evidence.native_uv.invalid.includes(channel));
      let resolved;
      if (category !== 'hidden') {
        const materialCategory = category === 'trim' && ['paint','glass'].includes(evidence.unpaintable_surface_role)
          ? evidence.unpaintable_surface_role : category;
        resolved = nativeMaterials.resolve(child.userData, {category:materialCategory,
          availableUvChannels: validUvChannels});
        materialEvidence.meshes++;
        materialEvidence.nativeValuesApplied += resolved.evidence.counters.appliedParameters;
        materialEvidence.unresolvedTextures += resolved.textureRequests.length;
        for (const warning of resolved.evidence.warnings) materialEvidence.warnings[warning] = (materialEvidence.warnings[warning] || 0) + 1;
      }
      if (category !== 'hidden') {
        for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
          if (material) oldMaterials.add(material);
        }
      }
      if (category === 'paint') {
        const directUv = evidence.uv3 === 'present';
        child.material = liveryMaterial(
          'body',
          meshAllowedSides(child, category),
          0,
          directUv,
          resolved.options
        );
        paintCount += 1;
      } else if (category === 'glass') {
        const directUv = evidence.uv3 === 'present';
        child.material = liveryMaterial(
          'glass',
          meshAllowedSides(child, category),
          0,
          directUv,
          resolved.options
        );
        child.renderOrder = 2;
        glassCount += 1;
      } else if (category === 'hidden') {
        child.visible = false;
      } else {
        const binding = await qualifiedNativeTexture(child, runtime.native_textures, nativeTextures, validUvChannels);
        if (viewerDisposed) return;
        if (binding) {
          materialEvidence.textureBindings++;
          materialEvidence.unresolvedTextures = Math.max(0, materialEvidence.unresolvedTextures - 1);
        }
        const unsupported=['paint','glass'].includes(evidence.unpaintable_surface_role);
        const key = JSON.stringify([resolved.options, binding?.key || null, unsupported]);
        if (!neutralMaterials.has(key)) {
          neutralMaterials.set(key, trackMaterial(inspectUnsupportedMaterial(new THREE.MeshPhysicalMaterial(physicalOptions({...resolved.options, ...binding?.options})),unsupported)));
        }
        child.material = neutralMaterials.get(key);
      }
    }
    materialEvidence.textureAssets = nativeTextureSources.size;
    const completeBytes = resourceBytes();
    modelResourceBytes = completeBytes.geometry + completeBytes.textures;
    if (completeBytes.estimatedGpu > gpuBudgetBytes) throw new Error('The car and its textures exceed the preview graphics memory budget.');
    const retainedMaterials = new Set();
    model.traverse(child => {
      for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
        if (material) retainedMaterials.add(material);
      }
    });
    oldMaterials.forEach(material => {
      if (!retainedMaterials.has(material)) { material.dispose(); trackedMaterials.delete(material); }
    });
    if (!meshCount || !paintCount) {
      throw new Error('The local car conversion did not preserve FH6 livery-bearing paint geometry.');
    }
    const nativeWheels = nativeWheelState();
    if (!new URLSearchParams(window.location.search).has('wheels') && nativeWheels.complete) wheelsVisible = false;
    wheelsCheckbox.checked = wheelsVisible;
    const wheelCount = addInspectionWheels(renderContract.assembly);
    wheelsCheckbox.disabled = wheelCount === 0;
    if (!wheelCount) { wheelsVisible = false; wheelsCheckbox.checked = false; }
    wheelsCheckbox.title = t(wheelCount ? 'Show simple placeholder wheels; fitment evidence is listed below' : 'Placeholder wheel locations or dimensions are unavailable');
    scene.add(model);
    model.updateMatrixWorld(true);
    modelBounds = stableInspectionBounds(model);
    floor.position.y = inspectionFloorY(renderContract.assembly, modelBounds.min.y) - 0.018;
    frameModel(modelBounds);
    setSectionFilter('all');
    phase('scene', 'Rendering first frame');
    modelReady = true;
    refreshComponentCoverage();
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
  if (modelBounds) frameModel(modelBounds, homeCamera.clone().sub(homeTarget));
  else { camera.position.copy(homeCamera); controls.target.copy(homeTarget); }
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

function toggleWheels() {
  if (viewerDisposed) return;
  wheelsVisible = wheelsCheckbox.checked;
  if (inspectionWheels) inspectionWheels.visible = wheelsVisible;
  applyWheelVisibility();
  if (modelReady) refreshComponentCoverage();
  requestRender();
  viewerEvent('wheels', '', {visible: wheelsVisible});
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
wheelsCheckbox.addEventListener('change', toggleWheels);
partControls.addEventListener('change', changePartSelection);
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

function handleThemeChange() {
  if (viewerDisposed) return;
  scene.background.copy(displayColor(getComputedStyle(viewport).backgroundColor));
  const accent = getComputedStyle(viewport).getPropertyValue('--editor-selection-border').trim();
  selectionAccent = displayColor(accent);
  inspectionTheme();
  const seamColor=displayColor(getComputedStyle(viewport).getPropertyValue('--accent').trim());
  for(const line of inspectionLines)line.material.color.copy(seamColor);
  for (const material of [...paintMaterials, ...glassMaterials]) material.uniforms.selectionColor.value.copy(selectionAccent);
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
    clearInspectionLines();
    inspectionMode='off';inspectionUniforms.inspectionMode.value=0;
    window.clearTimeout(loadTimeout);
    loadAbort.abort();
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    animationFrameId = 0;
    controls.removeEventListener('change', requestRender);
    controls.dispose();
    resetButton.removeEventListener('click', resetView);
    rotateButton.removeEventListener('click', toggleAutoRotate);
    wheelsCheckbox.removeEventListener('change', toggleWheels);
    partControls.removeEventListener('change', changePartSelection);
    sectionButtons.forEach(button => button.removeEventListener('click', selectSection));
    canvas.removeEventListener('dblclick', resetFromDoubleClick);
    window.removeEventListener('resize', handleResize);
    window.removeEventListener('kfps-theme-applied', handleThemeChange);
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    canvas.removeEventListener('webglcontextlost', handleContextLost);
    partControls.replaceChildren();
    selectedPartOptions.clear();
    partCatalog.groups.clear();
    partNotes.clear();
    componentMeshes = [];
    trackedSkeletons.forEach(skeleton => skeleton.dispose());
    trackedGeometries.forEach(geometry => geometry.dispose());
    trackedMaterials.forEach(material => material.dispose());
    const images = new Set(nativeTextureSources.values());
    trackedTextures.forEach(texture => {
      texture.dispose();
      if (texture.image) images.add(texture.image);
    });
    images.forEach(image => image.close?.());
    nativeTextureSources.clear();
    nativeDecodedBytes = 0;
    trackedSkeletons.clear();
    trackedGeometries.clear();
    trackedMaterials.clear();
    trackedTextures.clear();
    scene.clear();
    model = null;
    inspectionWheels = null;
    modelBounds = null;
    paintMaterials = [];
    glassMaterials = [];
    surfaceMaskPages = [];
    surfaceConfig = null;
    nativeMaterials.clear();
    window.dispatchEvent(new Event('kfps-inspection-change'));
  }
  if (releaseContext) releaseRendererContext();
  return viewerDiagnostics();
}

export function sceneDiagnosticMetrics() {
  return {ready:isSceneReady(),webgl:!rendererContextReleased,visible:document.visibilityState!=='hidden',
    canvas_width:canvas.width,canvas_height:canvas.height,pixel_ratio:renderPixelRatio,
    frame_count:renderedFrames,frame_ms:frameTime,frame_mean_ms:renderedFrames?frameTimeTotal/renderedFrames:0,
    frame_max_ms:frameTimePeak,load_ms:timings.firstFrame||0,
    geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,programs:renderer.info.programs?.length||0,
    draw_calls:renderer.info.render.calls,triangles:renderer.info.render.triangles,
    resource_bytes:Math.ceil(modelResourceBytes+(viewerDisposed?0:renderWidth*renderHeight*renderPixelRatio**2*40))};
}

function viewerDiagnostics() {
  return {
    disposed: viewerDisposed,
    contextReleased: rendererContextReleased,
    animationActive: Boolean(animationFrameId),
    ready: firstFrameReady,
    camera: {position: camera.position.toArray(), target: controls.target.toArray(), near: camera.near, far: camera.far},
    background: scene.background?.getHexString() || null,
    selectionAccent: selectionAccent.getHexString(),
    wheels: {visible: Boolean(inspectionWheels?.visible), count: inspectionWheels?.children.length || 0, native: nativeWheelState(),
      fitment: renderContract?.assembly?.wheel_fitment || null,
      specifications: placeholderWheelSpecs(renderContract?.assembly),
      measuredSizes: inspectionWheels?.children.map(wheel => wheel.userData.measuredSize) || []},
    components: componentCoverage,
    conversionCoverage: model?.userData?.kfps_conversion_coverage || null,
    vehicle_parts: partOverrides(),
    fidelity: {world_projection_fallback: false, game_equivalence_verified: false,
      materials: 'native-parameter-preview', materialEvidence: structuredClone(materialEvidence),
      wheels: inspectionWheels?.visible ? 'inspection-stand-ins' : nativeWheelState().complete ? 'native-source-meshes' : 'incomplete-native-source', manifest: runtimeFidelity,
      game_export_configuration_supported: false,
      projected_material_count: [...paintMaterials,...glassMaterials].filter(material=>material.uniforms.meshProjectionSlots.value.some(value=>value!==0)).length,
      nonstock_selected: componentCoverage?.groups.some(group => group.selected !== null && !group.options.find(option => option.id === group.selected)?.stock) ?? false},
    timings: {...timings},
    bytes: resourceBytes(),
    nativeTextureMemory: {decodedBytes: nativeDecodedBytes, decodedBudgetBytes: nativeDecodedBudgetBytes,
      sources: nativeTextureSources.size},
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

function viewerStatusDiagnostics() {
  // The native host bounds status messages to 64 KiB. Per-part inspection
  // evidence can be much larger; keep it available through viewerDiagnostics.
  const full = viewerDiagnostics();
  const status = {};
  for (const key of ['disposed', 'contextReleased', 'animationActive', 'ready',
    'camera', 'background', 'selectionAccent', 'timings', 'bytes',
    'nativeTextureMemory', 'device', 'quality', 'tracked', 'renderer', 'rendering']) {
    status[key] = full[key];
  }
  status.wheels = {visible: full.wheels.visible, count: full.wheels.count, native: full.wheels.native};
  return status;
}

function handleContextLost(event) {
  event.preventDefault();
  if (viewerDisposed) return;
  const message = 'The graphics device lost the 3D preview. Save your layout, then reopen Livery Studio to retry.';
  setStatus(message, true);
  viewerEvent('context-lost', message);
  window.dispatchEvent(new CustomEvent('kfps-viewer-error', {detail: {message}}));
  disposeViewer(false);
}

renderer.debug.onShaderError = () => { throw new Error('The graphics device could not compile the livery shader.'); };
canvas.addEventListener('webglcontextlost', handleContextLost);

canvas.addEventListener('dblclick', resetFromDoubleClick);
window.addEventListener('resize', handleResize);
window.addEventListener('kfps-theme-applied', handleThemeChange);
document.addEventListener('visibilitychange', handleVisibilityChange);
window.addEventListener('pagehide', disposeViewer);
window.__kfpsDisposeViewer = disposeViewer;
window.__kfpsViewerDiagnostics = viewerDiagnostics;
window.__kfpsViewerStatusDiagnostics = viewerStatusDiagnostics;
window.__kfpsViewerBooted = true;
window.clearTimeout(window.__kfpsViewerBootTimer);
export const sceneReady = loadPackage();
resize();
requestRender();
