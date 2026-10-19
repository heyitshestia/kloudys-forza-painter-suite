// Independent bounded preview adapter. FTS 4f373c5, MIT, Copyright (c) 2023 Nenkai.
// References and qualification limits: docs/NATIVE-TEXTURE-BINDING.md.
import { resolveNativeMaterial } from './native-material.mjs';

export const NATIVE_TEXTURE_UV_PIPELINE = 'fts-importer-v-flipped-then-native-scale-offset-v1';
export const NATIVE_TEXTURE_NATIVE_UV_PIPELINE = 'native-unflipped-then-native-scale-offset-v1';
export const NATIVE_TEXTURE_PROFILE = 'fts-brake-basecolor-preview-v1';
export const NATIVE_TEXTURE_DECLARATION_SHA256 = 'c48809e086530ad194c00fd7c8c608fd5889e2c2f64eb1d02714fa89f2c2d6a5';
const TEMPLATE = 'game:/media/cars/_library/materials/_fmnext/brake/brakerotor_ch1.materialbin';
const PARAMETER_TYPES = Object.freeze({
  '85E937A9': 'Texture2D', 'F9E8078D': 'Texture2D', '8D9C56EF': 'Texture2D',
  'CD6B029B': 'Float', '4E282123': 'Float', '9A83BC93': 'Bool',
  '19A7D8F1': 'Float', '4A3D8375': 'Float',
});
const UNRESOLVED = Object.freeze(['exact-game-shader', 'normal-map-convention', 'packed-rmao-channels', 'shader-sampler-state']);
const SHA = /^[a-f0-9]{64}$/;
const hash = value => typeof value === 'string' ? value.replace(/^0x/i, '').toUpperCase() : '';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const sha256 = value => typeof value === 'string' && SHA.test(value);

/** @typedef {{availableUvChannels:number[], sourceUvTransforms:number[][],
 * uvPipeline:string, declarationSha256:string}} NativeTextureBindingContext
 * @typedef {{source_path:string, cache_key:string, metadata:object}} StagedNativeTexture
 */

function sourcePath(value) {
  if (typeof value !== 'string' || value.length > 1024 || /[\x00-\x1f\x7f%?#]/.test(value)) return null;
  const path = value.replaceAll('\\', '/').toLowerCase();
  if (!path.startsWith('game:/media/') || path.slice(6).includes(':') || path.split('/').some(p => ['', '.', '..'].includes(p))) return null;
  return path;
}

function result(reasons, fields = {}) {
  return { status: reasons.length ? 'unresolved' : 'planned', profile: NATIVE_TEXTURE_PROFILE,
    request: null, texture: null, ...fields, reasons: [...new Set(reasons)], unresolved: [...UNRESOLVED],
    evidence: { qualification: 'fts-preview-convention', gameEquivalent: false,
      ftsCommit: '4f373c5fb192551ce5249e320dd79b1399b693ca',
      declarationSha256: NATIVE_TEXTURE_DECLARATION_SHA256,
      uvBasis: 'FTS ViewportPage.Rendering channel 0; not a recovered game shader input',
      samplerBasis: 'native texture domain plus linear preview filtering; shader sampler unresolved' } };
}

/** @param {object} extras @param {NativeTextureBindingContext} settings */
export function planNativeTextureBinding(extras, settings = {}) {
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) return result(['invalid-binding-context']);
  const material = extras?.kfps_native_material;
  if (!material || !Array.isArray(material.parameters) || material.parameters.length > 512) return result(['invalid-native-material']);
  const refs = [material.resource_path, ...(Array.isArray(material.nested_resources) ? material.nested_resources : [])].filter(v => v != null);
  if (!refs.length || refs.length > 32 || refs.some(ref => sourcePath(ref) !== TEMPLATE)) return result(['unsupported-material-template']);
  if (settings.declarationSha256 !== NATIVE_TEXTURE_DECLARATION_SHA256) return result(['unverified-material-declaration']);
  const bucket = extras.kfps_native_render_bucket;
  if (bucket?.opaque !== true || bucket.transparent || bucket.alpha_to_coverage || bucket.decal) return result(['unsupported-alpha-or-decal-state']);
  if (extras.kfps_material_instance_overrides != null
    && (!Array.isArray(extras.kfps_material_instance_overrides) || extras.kfps_material_instance_overrides.length)) return result(['unresolved-instance-overrides']);
  for (const p of material.parameters) {
    const name = hash(p?.name_hash);
    if (!p || p.parser_placeholder || PARAMETER_TYPES[name] !== p.type) return result(['unsupported-or-invalid-parameter']);
    if (p.type === 'Float' && (typeof p.value !== 'number' || !Number.isFinite(p.value))) return result(['invalid-scalar']);
    if (p.type === 'Bool' && p.value !== false) return result(['unsupported-damage-switch']);
  }
  const resolved = resolveNativeMaterial(extras, { availableUvChannels: settings.availableUvChannels });
  if (resolved.evidence.counters.rejectedParameters) return result(['ambiguous-or-rejected-parameter']);
  const requests = resolved.textureRequests.filter(t => t.nameHash === '85E937A9');
  if (requests.length !== 1) return result(['missing-unique-basecolor-texture']);
  const request = { nameHash: '85E937A9', kind: 'baseColor', sourcePath: requests[0].sourcePath,
    sourcePathHash: requests[0].sourcePathHash };
  const reasons = [];
  if (!Array.isArray(settings.availableUvChannels) || !settings.availableUvChannels.includes(0)) reasons.push('missing-native-uv0');
  if (![NATIVE_TEXTURE_UV_PIPELINE, NATIVE_TEXTURE_NATIVE_UV_PIPELINE].includes(settings.uvPipeline)) reasons.push('unverified-uv-pipeline');
  const transform = settings.sourceUvTransforms?.[0];
  if (!Array.isArray(settings.sourceUvTransforms) || settings.sourceUvTransforms.length > 8
    || !Array.isArray(transform) || transform.length !== 4 || transform.some(v => typeof v !== 'number' || !Number.isFinite(v) || Math.abs(v) >= 1e6)
    || Math.abs(transform[1]) < 1e-8 || Math.abs(transform[3]) < 1e-8) reasons.push('invalid-source-uv-transform');
  if (resolved.evidence.warnings.some(w => /tiling/.test(w))) reasons.push('invalid-material-tiling');
  if (reasons.length) return result(reasons, {request});
  const [tileU, tileV] = requests[0].repeat;
  // Isolated converter preserves native V, so only material tiling remains.
  // The explicit legacy flipped contract needs scaleV + 2*offsetV - gV.
  const matrix = settings.uvPipeline === NATIVE_TEXTURE_NATIVE_UV_PIPELINE
    ? [tileU, 0, 0, 0, tileV, 0, 0, 0, 1]
    : [tileU, 0, 0, 0, -tileV, (transform[3] + 2 * transform[2]) * tileV, 0, 0, 1];
  return result([], {request, texture: {channel: 0, matrix, matrixAutoUpdate: false, flipY: false},
    material: {slot: 'map', color: [1, 1, 1], transparent: false, opacity: 1,
      alphaTest: 0, transmission: 0, depthWrite: true, alphaPolicy: 'ignore-texture-alpha-opaque-bucket'} });
}

/** @param {object} plan @param {StagedNativeTexture} asset */
export function qualifyNativeTextureAsset(plan, asset) {
  if (plan?.status !== 'planned' || plan.profile !== NATIVE_TEXTURE_PROFILE || !plan.request || !plan.texture) return result(['binding-not-planned']);
  const m = asset?.metadata;
  const reasons = [];
  if (!sourcePath(asset?.source_path) || sourcePath(asset.source_path) !== sourcePath(plan.request.sourcePath)) reasons.push('asset-source-mismatch');
  if (!SHA.test(asset?.cache_key ?? '') || !SHA.test(m?.source_sha256 ?? '') || !SHA.test(m?.png_sha256 ?? '')) reasons.push('invalid-asset-identity');
  if (!m || m.pipeline !== 'pc-swatch-straight-v1' || m.decoded_mode !== 'RGBA'
    || m.flip_y !== false || m.premultiplied_alpha !== false) reasons.push('unverified-pixel-pipeline');
  if (!['srgb', 'linear-srgb'].includes(m?.color_space)) reasons.push('unsupported-color-space');
  if (!['repeat', 'clamp', 'mirror'].includes(m?.domain)) reasons.push('unsupported-native-domain');
  if (!Number.isInteger(m?.width) || !Number.isInteger(m?.height) || m.width < 1 || m.height < 1 || m.width > 4096 || m.height > 4096) reasons.push('invalid-image-dimensions');
  if (!Array.isArray(m?.alpha_range) || m.alpha_range.length !== 2 || m.alpha_range.some(v => !Number.isInteger(v) || v < 0 || v > 255)
    || m.alpha_range[0] > m.alpha_range[1]) reasons.push('unverified-alpha-range');
  if (reasons.length) return result(reasons, {request: structuredClone(plan.request)});
  return { ...structuredClone(plan), status: 'ready', assetKey: asset.cache_key,
    texture: { ...structuredClone(plan.texture), colorSpace: m.color_space,
      wrapS: m.domain, wrapT: m.domain, minFilter: 'linear-mipmap-linear', magFilter: 'linear', generateMipmaps: true },
    material: { ...plan.material, color: [...plan.material.color] },
    evidence: {...plan.evidence, textureSourceSha256:m.source_sha256, texturePngSha256:m.png_sha256,
      ignoredAlphaRange: [...m.alpha_range]} };
}

/** Resolve public staged metadata without fetching or changing any input.
 * Equivalent declaration spellings may agree; conflicting hashes or duplicate
 * asset matches fail closed. The returned asset is the original read-only row.
 * @param {object} extras
 * @param {Omit<NativeTextureBindingContext, 'declarationSha256'>} settings
 * @param {{declarations:Record<string,string>, assets:StagedNativeTexture[]}} nativeAssets
 * @returns {{binding:object, asset:StagedNativeTexture}|null}
 */
export function resolveStagedNativeTexture(extras, settings, nativeAssets) {
  if (!record(extras) || !record(settings) || !record(nativeAssets)
    || !record(nativeAssets.declarations) || !Array.isArray(nativeAssets.assets)
    || !nativeAssets.assets.length || nativeAssets.assets.length > 128) return null;
  const material = extras.kfps_native_material;
  if (!record(material) || (material.nested_resources != null && !Array.isArray(material.nested_resources))
    || (material.nested_resources?.length ?? 0) > 32) return null;
  const refs = [material.resource_path, ...(material.nested_resources ?? [])].filter(v => v != null);
  if (!refs.length || refs.length > 32) return null;
  const normalizedRefs = refs.map(sourcePath);
  if (normalizedRefs.some(path => !path)) return null;
  const entries = Object.entries(nativeAssets.declarations);
  if (!entries.length || entries.length > 128) return null;
  const declarations = new Map();
  for (const [key, value] of entries) {
    const path = sourcePath(key);
    if (!path || !sha256(value) || (declarations.has(path) && declarations.get(path) !== value)) return null;
    declarations.set(path, value);
  }
  const hashes = normalizedRefs.map(path => declarations.get(path));
  if (hashes.some(value => !value) || new Set(hashes).size !== 1) return null;
  // Only hashes of staged declaration bytes qualify; a caller's hash is ignored.
  const plan = planNativeTextureBinding(extras, {...settings, declarationSha256: hashes[0]});
  if (plan.status !== 'planned') return null;
  const requested = sourcePath(plan.request.sourcePath);
  if (!requested) return null;
  let asset = null;
  for (const candidate of nativeAssets.assets) {
    if (!record(candidate) || !sourcePath(candidate.source_path)) return null;
    if (sourcePath(candidate.source_path) !== requested) continue;
    if (asset) return null;
    asset = candidate;
  }
  if (!asset || !record(asset.metadata) || !sha256(asset.cache_key)
    || !sha256(asset.metadata.source_sha256) || !sha256(asset.metadata.png_sha256)) return null;
  const binding = qualifyNativeTextureAsset(plan, asset);
  return binding.status === 'ready' ? {binding, asset} : null;
}
