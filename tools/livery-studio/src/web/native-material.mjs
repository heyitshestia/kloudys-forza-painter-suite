/*
 * Parameter-name/hash facts reference ForzaTechStudio 4f373c5 (MIT).
 * Copyright (c) 2023 Nenkai
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

const MAX_PARAMETERS = 512, MAX_RESOURCES = 32, MAX_TEXTURES = 32;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const boundedText = (value, limit = 1024) => typeof value === 'string' && value.length <= limit ? value : null;
const finite = value => typeof value === 'number' && Number.isFinite(value);
const vector = (value, length) => Array.isArray(value) && value.length === length && value.every(finite);
const hash = value => typeof value === 'string' && /^(?:0x)?[\da-f]{8}$/i.test(value) ? value.replace(/^0x/i, '').toUpperCase() : null;
const clamp = (value, maximum = 1) => Math.max(0, Math.min(maximum, value));

const BASE_COLORS = {
  EA718FBE: 'UniqueBaseColorColorParam', '53A946B6': 'BaseColor_Tint',
  '63040D89': 'DiffuseColorColorParam', F51639BE: 'DiffuseColorGroupColorParam',
  '57C321A6': 'ColorColorParam', '73A9E2DF': 'ColorGroupColorParam',
  '1F3EB7A9': 'DiffTintColorParam', D0F0433A: 'DiffuseColor0',
  A76D0485: 'DiffuseTintColor', D9826618: 'DiffuseTintColor0',
  '00FC00E4': 'Tint', '1F0BBA20': 'BaseColor', '36976C2B': 'CustomColor',
  C0CB2820: 'PaintColorColorParam', '0014A502': 'PaintColorGroupColorParam',
};
const GLASS_COLORS = { '1F30F777': 'GlassColor0ColorParam', '1925D9BF': 'GlassColor', '36CA5A12': 'CH1GlassColor' };
const EMISSIVE_COLORS = { '21EC1E4D': 'EmissiveColor', EFBBC518: 'EmissiveTint' };
const EMISSIVE_INTENSITY = { '074CCD8C': 'Emissive_Intensity', '9421C781': 'EmissiveIntensity',
  D78943E8: 'EmissiveMultiplier', '4C6E94DA': 'EmissiveStrength', '22F9702D': 'EmissiveBrightness' };
const TEXTURES = {
  '85E937A9': ['baseColor', 'BaseColorAlpha'], F9E8078D: ['normal', 'Normal'],
  '8D9C56EF': ['roughMetalAo', 'RoughMetalAO'], '698CA64F': ['alpha', 'Alpha'],
  '57D9D49E': ['alpha', 'AlphaTexture'], '66E53F62': ['alpha', 'CH1AlphaTextureTexture'],
  '2FDCDBF0': ['alpha', 'AlphaTexture_1'], '4E0D5E89': ['emissive', 'CH1EmissiveMap'],
  '6161E552': ['emissive', 'EmissiveCH1'], '020B22EB': ['emissive', 'EmissiveMap'],
  '212B4B48': ['emissive', 'EmissiveTexture'], '3CB4DFCB': ['emissive', 'InteriorEmissiveTexture'],
  '490FB859': ['lightingMask', 'radTexture'],
};
const OTHER_NAMES = {
  '6B242133': 'BaseColor_TintMultiplier', '18A539DD': 'ClearCoatRoughness',
  '5ABC4AE8': 'ClearFinishAmount', '80D4CB8B': 'GlassRoughnessFloat',
  '402B8ED0': 'UVChoice_OnCh1_OffCh2', '19A7D8F1': 'U_Tiling', '4A3D8375': 'V_Tiling',
  B01AEE8E: 'U_Tiling', '3E95E96D': 'V_Tiling', '38B56360': 'FlakeColor',
  '4E282123': 'Roughness_Shift', CD6B029B: 'Normal_Intensity', '604BA06B': 'FlakeCoverage',
  '4E547D2C': 'FlakeRoughness', '6926A074': 'RoughnessScale',
};
const NAMES = Object.freeze({ ...BASE_COLORS, ...GLASS_COLORS, ...EMISSIVE_COLORS,
  ...EMISSIVE_INTENSITY, ...Object.fromEntries(Object.entries(TEXTURES).map(([key, value]) => [key, value[1]])), ...OTHER_NAMES });

function gamePath(value) {
  if (!boundedText(value) || /[\x00-\x1f\x7f%?#]/.test(value)) return null;
  const normalized = value.replaceAll('\\', '/');
  if (!/^game:\/media\//i.test(normalized)) return null;
  if (normalized.slice(5).includes(':') || normalized.split('/').slice(1).some(part => !part || part === '..' || part === '.')) return null;
  return normalized;
}

function normalizeParameter(value) {
  if (!record(value)) return { invalid: true };
  const nameHash = hash(value.name_hash), type = boundedText(value.type, 32);
  const p = { nameHash, type, value: null, invalid: !nameHash || nameHash === 'DEADBEEF' || value.parser_placeholder === true };
  if (['Color', 'Vector4'].includes(type) && vector(value.value, 4)) p.value = [...value.value];
  else if (type === 'Vector2' && vector(value.value, 2)) p.value = [...value.value];
  else if (type === 'Float' && finite(value.value)) p.value = value.value;
  else if (type === 'Int' && Number.isSafeInteger(value.value)) p.value = value.value;
  else if (type === 'Bool' && typeof value.value === 'boolean') p.value = value.value;
  else if (type === 'Texture2D' && record(value.value) && gamePath(value.value.path)) {
    p.value = { path: gamePath(value.value.path), pathHash: hash(value.value.path_hash) };
  } else p.invalid = true;
  return p;
}

function checkedColor(value, label) {
  if (!vector(value, 3) || value.some(item => item < 0 || item > 1)) throw new TypeError(`Invalid ${label} color; expected three finite values in [0,1].`);
  return [...value];
}

export function srgbToLinear(rgb) {
  return checkedColor(rgb, 'sRGB').map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
}

function normalize(extras, settings) {
  const data = record(extras) ? extras : {}, native = record(data.kfps_native_material) ? data.kfps_native_material : {};
  if (!record(settings)) throw new TypeError('Invalid material settings.');
  const encoding = settings.parameterColorEncoding ?? 'linear';
  if (!['linear', 'srgb', 'unknown'].includes(encoding)) throw new TypeError('Unknown parameter color encoding.');
  const parameters = Array.isArray(native.parameters) ? native.parameters : [];
  const resources = Array.isArray(native.nested_resources) ? native.nested_resources : [];
  const category = boundedText(settings.category, 32) || boundedText(data.kfps_role, 32) || 'unknown';
  return {
    category, encoding, encodingExplicit: settings.parameterColorEncoding !== undefined,
    paintColor: settings.paintColorLinear === undefined ? null : checkedColor(settings.paintColorLinear, 'linear paint'),
    channels: Array.isArray(settings.availableUvChannels) ? [...new Set(settings.availableUvChannels.slice(0, 32)
      .filter(item => Number.isInteger(item) && item >= 0 && item <= 7))].sort() : [],
    parameterCount: parameters.length,
    parameters: parameters.length <= MAX_PARAMETERS ? parameters.map(normalizeParameter) : [],
    resources: resources.length <= MAX_RESOURCES ? resources.map(gamePath).filter(Boolean) : [],
    resourceLimit: resources.length > MAX_RESOURCES,
    resource: gamePath(native.resource_path), name: boundedText(native.name, 256),
    sourceHash: typeof native.source_blob_sha256 === 'string' && /^[a-f\d]{64}$/i.test(native.source_blob_sha256)
      ? native.source_blob_sha256.toLowerCase() : null,
    transparent: data.kfps_native_render_bucket?.transparent === true,
    alphaToCoverage: data.kfps_native_render_bucket?.alpha_to_coverage === true,
    overrides: Array.isArray(data.kfps_material_instance_overrides) && data.kfps_material_instance_overrides.length > 0,
  };
}

function resourceFamily(reference) {
  const path = reference.toLowerCase(), prefix = 'game:/media/cars/_library/materials/_fmnext/';
  if (!path.startsWith(prefix)) return null;
  const template = path.slice(prefix.length);
  if (/^metal\/(steel|aluminum|chrome|gunmetal|titanium|copper|anodizedmetal)(_ch[12])?\.materialbin$/.test(template)) return 'metal';
  if (/^rubber\/rubber(_ch[12])?\.materialbin$/.test(template)) return 'rubber';
  if (/^(paint\/(paintedmetal|metalpowder)(_ch[12])?|wheel\/wheelpaint|carpaint_default\/carpaint)\.materialbin$/.test(template)) return 'paint';
  if (/^glass\/(glass|glass_detailed|glass_windshield|glass_window_side|glass_limotint)(_ch[12])?\.materialbin$/.test(template)) return 'glass';
  if (/^(fabric\/(carpet|felt|nylon|cloth)|leather\/leather)\.materialbin$/.test(template)) return 'fabric';
  if (/^plastic\/(plastic|fluid_container)(_ch[12])?\.materialbin$/.test(template)) return 'plastic';
  if (/^carbonfiber\/carbonfiber\.materialbin$/.test(template)) return 'carbon';
  if (/^specialcase\/(blackframe|blackhole)\.materialbin$/.test(template)) return 'dark';
  return null;
}

function physicalDefaults(family) {
  const base = { color: [.32, .32, .32], emissive: [0, 0, 0], roughness: .65, metalness: 0,
    opacity: 1, transparent: false, depthWrite: true, clearcoat: 0, clearcoatRoughness: .1,
    emissiveIntensity: 0, transmission: 0 };
  const styles = {
    paint: { color: [.45, .45, .45], roughness: .3, clearcoat: .65, clearcoatRoughness: .08 },
    metal: { color: [.55, .55, .55], metalness: 1, roughness: .32 },
    glass: { color: [.18, .24, .28], roughness: .14, opacity: .32, transparent: true, depthWrite: false, clearcoat: .6 },
    rubber: { color: [.018, .018, .018], roughness: .86 },
    plastic: { color: [.06, .06, .06], roughness: .58 },
    fabric: { color: [.055, .055, .055], roughness: .95 },
    carbon: { color: [.035, .035, .035], roughness: .4, clearcoat: .3 },
    dark: { color: [.012, .012, .012], roughness: .85 },
    trim: { color: [.08, .08, .08] },
  };
  return { ...base, ...(styles[family] || {}) };
}

function resolve(input) {
  const warnings = new Set(), rejected = new Set(), used = new Set(), referenced = new Set(), conflicting = new Set(), byHash = new Map();
  input.parameters.forEach((p, index) => {
    if (p.invalid) { rejected.add(index); return; }
    if (conflicting.has(p.nameHash)) { rejected.add(index); return; }
    const previous = byHash.get(p.nameHash);
    if (previous && JSON.stringify([previous.type, previous.value]) !== JSON.stringify([p.type, p.value])) {
      warnings.add(`conflicting-parameter-${p.nameHash}`); conflicting.add(p.nameHash);
      byHash.delete(p.nameHash); rejected.add(index); return;
    }
    byHash.set(p.nameHash, p);
  });
  input.parameters.forEach((p, index) => { if (conflicting.has(p.nameHash)) rejected.add(index); });
  if (input.parameterCount > MAX_PARAMETERS) warnings.add('parameter-limit-exceeded');
  if (input.resourceLimit) warnings.add('resource-limit-exceeded');
  if (input.overrides) warnings.add('native-instance-overrides-not-applied');
  if (input.alphaToCoverage) warnings.add('native-alpha-to-coverage-not-reproduced');
  const families = new Set([...input.resources, ...(input.resource ? [input.resource] : [])].map(resourceFamily).filter(Boolean));
  const family = families.size === 1 ? [...families][0] : 'neutral';
  if (families.size > 1) warnings.add('conflicting-material-families');
  const isPaint = ['paint', 'body'].includes(input.category), isGlass = input.category === 'glass' || family === 'glass';
  const style = isGlass ? 'glass' : family !== 'neutral' ? family : isPaint ? 'paint' : ['trim', 'dark'].includes(input.category) ? input.category : 'neutral';
  const options = physicalDefaults(style), defaults = new Set(Object.keys(options)), applied = [];
  const chosen = (table, predicate) => Object.keys(table).map(key => byHash.get(key)).find(p => p && predicate(p));
  const colorParam = p => ['Color', 'Vector4'].includes(p.type) && vector(p.value, 4);
  const scalarParam = p => p.type === 'Float' && finite(p.value);
  const apply = (p, target, value, interpretation = 'direct-clamped-preview') => {
    used.add(p.nameHash); options[target] = value; defaults.delete(target);
    applied.push({ nameHash: p.nameHash, name: NAMES[p.nameHash], target, interpretation });
  };
  const colorValue = p => {
    const rgb = p.value.slice(0, 3).map(value => clamp(value));
    if (rgb.some((value, index) => value !== p.value[index])) warnings.add('clamped-color');
    return input.encoding === 'srgb' ? srgbToLinear(rgb) : rgb;
  };
  const limited = (p, target, maximum = 1) => {
    const value = clamp(p.value, maximum);
    if (value !== p.value) warnings.add(`clamped-${target}`);
    return value;
  };
  const base = (isGlass && chosen(GLASS_COLORS, colorParam)) || chosen(BASE_COLORS, colorParam);
  if (input.encoding !== 'unknown' && base && !(isPaint && input.paintColor)) {
    apply(base, 'color', colorValue(base), 'native-rgb-preview');
    const multiplier = byHash.get('6B242133');
    if (multiplier && colorParam(multiplier)) {
      apply(multiplier, 'color', options.color.map((value, index) => clamp(value * multiplier.value[index])), 'linear-multiplier-preview');
    }
  }
  if (isPaint && input.paintColor) {
    options.color = [...input.paintColor]; defaults.delete('color');
    warnings.add('explicit-user-paint-color');
  }
  const opacity = byHash.get('698CA64F');
  if (input.transparent || isGlass) {
    options.transparent = true; options.depthWrite = false;
    if (input.transparent) { defaults.delete('transparent'); defaults.delete('depthWrite'); }
    if (opacity && scalarParam(opacity)) apply(opacity, 'opacity', limited(opacity, 'opacity'));
  }
  for (const [key, target, eligible] of [
    ['18A539DD', 'clearcoatRoughness', isPaint || family === 'paint'],
    ['5ABC4AE8', 'clearcoat', isPaint || family === 'paint'],
    ['80D4CB8B', 'roughness', isGlass],
  ]) {
    const p = byHash.get(key);
    if (eligible && p && scalarParam(p)) apply(p, target, limited(p, target));
  }
  const emissive = chosen(EMISSIVE_COLORS, colorParam);
  if (emissive && input.encoding !== 'unknown') {
    apply(emissive, 'emissive', colorValue(emissive), 'native-rgb-preview');
    options.emissiveIntensity = 1;
    const intensity = chosen(EMISSIVE_INTENSITY, scalarParam);
    if (intensity) apply(intensity, 'emissiveIntensity', limited(intensity, 'emissiveIntensity', 8));
  }
  const choice = byHash.get('402B8ED0');
  const nativeUvLabel = choice?.type === 'Bool' ? choice.value ? 'CH1' : 'CH2' : null;
  const uvParams = [chosen({ '19A7D8F1': 1, B01AEE8E: 1 }, scalarParam), chosen({ '4A3D8375': 1, '3E95E96D': 1 }, scalarParam)];
  const repeat = uvParams.map(p => {
    if (!p) return 1;
    if (Math.abs(p.value) >= 1e-6 && Math.abs(p.value) <= 1024) return p.value;
    warnings.add('invalid-texture-tiling'); return 1;
  });
  const textureRequests = [];
  for (const p of byHash.values()) {
    if (p.type !== 'Texture2D' || !Object.hasOwn(TEXTURES, p.nameHash)) continue;
    if (textureRequests.length === MAX_TEXTURES) { warnings.add('texture-limit-exceeded'); break; }
    referenced.add(p.nameHash);
    if (nativeUvLabel) referenced.add(choice.nameHash);
    for (const uv of uvParams) if (uv) referenced.add(uv.nameHash);
    textureRequests.push({ nameHash: p.nameHash, kind: TEXTURES[p.nameHash][0], sourcePath: p.value.path,
      sourcePathHash: p.value.pathHash, uvChannel: null, nativeUvLabel, availableUvChannels: [...input.channels], repeat: [...repeat],
      sourceColorSpace: 'unknown', channelMapping: null, status: 'unresolved',
      reasons: ['texture-not-decoded', 'native-uv-index-unverified', 'sampler-state-unverified'] });
  }
  const valid = [...byHash.values()];
  return {
    options, colorSpace: 'linear-srgb', textureRequests,
    evidence: {
      sourceHash: input.sourceHash, sourceName: input.name, resources: [...input.resources], family,
      renderBucket: { transparent: input.transparent, alphaToCoverage: input.alphaToCoverage },
      userOverrides: isPaint && input.paintColor ? ['color'] : [],
      colorInput: input.encoding === 'linear' && !input.encodingExplicit ? 'linear-assumed' : input.encoding,
      decodedParametersVerified: false, gameEquivalent: false, applied, defaults: [...defaults], warnings: [...warnings],
      counters: { parametersSeen: input.parameterCount, appliedParameters: used.size,
        rejectedParameters: rejected.size + (input.parameterCount > MAX_PARAMETERS ? input.parameterCount : 0),
        unknownParameters: valid.filter(p => !Object.hasOwn(NAMES, p.nameHash)).length,
        recognizedUnusedParameters: valid.filter(p => Object.hasOwn(NAMES, p.nameHash) && !used.has(p.nameHash) && !referenced.has(p.nameHash)).length,
        referencedParameters: referenced.size, textureRequests: textureRequests.length, texturesLoaded: 0 },
    },
  };
}

export function resolveNativeMaterial(extras, settings = {}) {
  return resolve(normalize(extras, settings));
}

export function createNativeMaterialResolver({ maxEntries = 128, maxBytes = 2 * 1024 * 1024 } = {}) {
  if (!Number.isSafeInteger(maxEntries) || maxEntries < 1 || maxEntries > 512
    || !Number.isSafeInteger(maxBytes) || maxBytes < 1024 || maxBytes > 8 * 1024 * 1024) throw new RangeError('Invalid material cache limit.');
  const entries = new Map();
  let bytes = 0, hits = 0, misses = 0, evictions = 0;
  return {
    resolve(extras, settings = {}) {
      const input = normalize(extras, settings), key = JSON.stringify(input), cached = entries.get(key);
      if (cached) {
        hits++; entries.delete(key); entries.set(key, cached);
        return structuredClone(cached.result);
      }
      misses++;
      const result = resolve(input), size = 2 * (key.length + JSON.stringify(result).length);
      if (size <= maxBytes) {
        while (entries.size >= maxEntries || bytes + size > maxBytes) {
          const oldest = entries.keys().next().value;
          bytes -= entries.get(oldest).size; entries.delete(oldest); evictions++;
        }
        entries.set(key, { result, size }); bytes += size;
      }
      return structuredClone(result);
    },
    clear() { entries.clear(); bytes = 0; },
    stats() { return { entries: entries.size, bytes, hits, misses, evictions, maxEntries, maxBytes }; },
  };
}
