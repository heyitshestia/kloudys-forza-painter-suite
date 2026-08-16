import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const SECTION_COUNT = 11;
const RENDER_CONTRACT_FORMAT = 'kfps_fh6_section_render_contract_v3';
const ALL_BODY_SIDES = 0x1f;
const ALL_GLASS_SIDES = 0x7c0;
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
  const texture = trackTexture(await new THREE.TextureLoader().loadAsync(url));
  texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  texture.flipY = false;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  return texture;
}

function sectionArrays(contract, kind) {
  const sourceRegions = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  const paintRegions = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector4());
  const facings = Array.from({ length: SECTION_COUNT }, () => new THREE.Vector3());
  const present = new Float32Array(SECTION_COUNT);
  for (const section of contract.sections || []) {
    const slot = Number(section.slot_index);
    if (!Number.isInteger(slot) || slot < 0 || slot >= SECTION_COUNT) continue;
    const source = section.source_region || [];
    const paint = section.paint_region || [];
    const facing = section.facing || [];
    sourceRegions[slot].set(...source.map(Number));
    paintRegions[slot].set(...paint.map(Number));
    facings[slot].set(...facing.map(Number));
    if (section.kind === kind) present[slot] = 1;
  }
  return { sourceRegions, paintRegions, facings, present };
}

function sectionAwareMaterial(
  paintTexture,
  maskTextures,
  baseColor,
  kind,
  allowedSides,
  transparent = false
) {
  const arrays = sectionArrays(renderContract, kind);
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
      baseColor: { value: new THREE.Color(baseColor) },
      keyDirection: { value: new THREE.Vector3(0.45, 0.9, 0.55).normalize() },
    },
    vertexShader: `
      attribute vec2 uv3;
      varying vec2 atlasUv;
      varying vec3 worldNormalValue;
      varying vec3 worldPositionValue;
      void main() {
        atlasUv = vec2(uv3.x * 0.5, uv3.y);
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

      void main() {
        vec3 normalValue = normalize(worldNormalValue);
        float bestCoverage = 0.0;
        int bestSlot = -1;
        vec2 bestAtlasUv = atlasUv;
        for (int slot = 0; slot < ${SECTION_COUNT}; ++slot) {
          if (
            enabledSlots[slot] < 0.5
            || meshAllowedSlots[slot] < 0.5
            || dot(sideFacing[slot], normalValue) <= 0.0
          ) continue;
          vec2 candidateUv = atlasUv;
          if (
            candidateUv.x < 0.0 || candidateUv.x > 1.0
            || candidateUv.y < 0.0 || candidateUv.y > 1.0
          ) continue;
          vec4 page0 = texture2D(maskMap0, candidateUv);
          vec4 page1 = texture2D(maskMap1, candidateUv);
          vec4 page2 = texture2D(maskMap2, candidateUv);
          float candidate = slotCoverage(slot, page0, page1, page2);
          if (candidate > bestCoverage) {
            bestCoverage = candidate;
            bestSlot = slot;
            bestAtlasUv = candidateUv;
          }
        }

        vec4 decal = vec4(0.0);
        if (bestSlot >= 0 && bestCoverage > 0.0) {
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
        gl_FragColor = vec4(lit, ${transparent ? '0.82' : '1.0'});
      }
    `,
    transparent,
    depthWrite: !transparent,
    side: THREE.DoubleSide,
  }));
  return material;
}

function frameModel(bounds) {
  const size = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z);
  controls.target.copy(center);
  camera.position.copy(center).add(new THREE.Vector3(radius * 1.08, radius * 0.58, radius * 1.32));
  camera.near = Math.max(0.01, radius / 250);
  camera.far = Math.max(100, radius * 50);
  camera.updateProjectionMatrix();
  controls.minDistance = radius * 0.45;
  controls.maxDistance = radius * 6;
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
    const response = await fetch('./api/manifest', { cache: 'no-store' });
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

    setStatus('Loading the exact local car mesh, paint regions, and section masks...');
    const loadResults = await Promise.allSettled([
      loadTexture('./api/local-render/paint', true),
      loadTexture('./api/local-render/mask/0'),
      loadTexture('./api/local-render/mask/1'),
      loadTexture('./api/local-render/mask/2'),
      new GLTFLoader().loadAsync('./api/local-mesh').then(item => {
        trackObjectResources(item.scene);
        return item;
      }),
    ]);
    const failedLoad = loadResults.find(result => result.status === 'rejected');
    if (failedLoad) throw failedLoad.reason;
    if (viewerDisposed) return;
    const [paintTexture, mask0, mask1, mask2, gltf] = loadResults.map(result => result.value);
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
    const materialCache = new Map();
    const liveryMaterial = (kind, allowedSides) => {
      const key = `${kind}:${allowedSides}`;
      if (!materialCache.has(key)) {
        const material = sectionAwareMaterial(
          paintTexture,
          [mask0, mask1, mask2],
          kind === 'glass' ? 0x202a31 : 0xc7cbd0,
          kind,
          allowedSides,
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
    model.traverse(child => {
      if (!child.isMesh) return;
      meshCount += 1;
      const category = meshCategory(child);
      if (category === 'paint') {
        if (!child.geometry.getAttribute('uv3')) {
          throw new Error('The local car mesh does not contain exact FH6 livery coordinates.');
        }
        child.material = liveryMaterial(
          'body',
          meshAllowedSides(child, category)
        );
        paintCount += 1;
      } else if (category === 'glass') {
        if (!child.geometry.getAttribute('uv3')) {
          throw new Error('The local car glass does not contain exact FH6 livery coordinates.');
        }
        child.material = liveryMaterial(
          'glass',
          meshAllowedSides(child, category)
        );
        child.renderOrder = 2;
        glassCount += 1;
      } else if (category === 'hidden') {
        child.visible = false;
      } else {
        child.material = trackMaterial(new THREE.MeshStandardMaterial({
          color: category === 'dark' ? 0x11161b : 0x4b555d,
          roughness: 0.68,
          metalness: 0.15,
        }));
      }
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
    const bounds = new THREE.Box3().setFromObject(model);
    floor.position.y = bounds.min.y - 0.018;
    frameModel(bounds);
    setSectionFilter('all');
    setStatus('');
    console.info(
      `KFPS section-aware inspector: ${paintCount} paint, ${glassCount} glass, `
      + `${meshCount} local meshes, ${wheelCount} neutral inspection wheels, `
      + `${(renderContract.sections || []).length} livery sections.`
    );
    requestRender();
  } catch (error) {
    console.error(error);
    setStatus(error?.message || String(error), true);
    disposeViewer();
  }
}

function resetView() {
  camera.position.copy(homeCamera);
  controls.target.copy(homeTarget);
  controls.update();
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
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  if (width === renderWidth && height === renderHeight && pixelRatio === renderPixelRatio) return;
  renderWidth = width;
  renderHeight = height;
  renderPixelRatio = pixelRatio;
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function renderFrame() {
  animationFrameId = 0;
  if (viewerDisposed || document.hidden) return;
  resize();
  controls.update();
  renderer.render(scene, camera);
  renderedFrames += 1;
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
    },
  };
}

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
