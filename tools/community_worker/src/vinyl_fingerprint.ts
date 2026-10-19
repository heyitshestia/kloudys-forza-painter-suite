import { sha256Hex } from './security';
import type { CanonicalDesign, CanonicalShape } from './types';

// Same stable bases/order as kfps_shapes/identity.py; no game/custom map lookup.
export const RESOURCE_BASES: Record<string, number> = {
  Primitives: 1048677, Community_Vinyls_1: 1050677, Community_Vinyls_2: 1050777,
  Community_Vinyls_3: 1050877, Community_Vinyls_4: 1050977,
  Gradient_Shapes: 1048777, Stripes: 1048877, Tears: 1048977, Racing_Icons: 1049077,
  Flames: 1049177, Paint_Splats: 1049277, Tribal: 1049377, Nature: 1049477,
  Upper_Letters_1: 1050477, Lower_Letters_1: 1050577,
  Upper_Letters_2: 1049877, Lower_Letters_2: 1049977,
  Upper_Letters_3: 1050077, Lower_Letters_3: 1050177,
  Upper_Letters_4: 1050277, Lower_Letters_4: 1050377,
  Upper_Letters_5: 1051077, Lower_Letters_5: 1051177,
  Upper_Letters_6: 1051277, Lower_Letters_6: 1051377,
  Upper_Letters_7: 1051477, Lower_Letters_7: 1051577,
  Upper_Letters_8: 1051677, Lower_Letters_8: 1051777,
  Upper_Letters_9: 1051877, Lower_Letters_9: 1051977,
  Upper_Letters_10: 1052077, Lower_Letters_10: 1052177,
  Upper_Letters_11: 1052277, Lower_Letters_11: 1052377,
};

export interface VinylFingerprint {
  version: 1;
  status: 'qualified' | 'review_required';
  fingerprint: string | null;
  reason: string;
}

function resource(shape: CanonicalShape): [string, number] | null {
  for (const [family, base] of Object.entries(RESOURCE_BASES)) {
    if (shape.type >= base && shape.type < base + 40) return [family, shape.type - base + 1];
  }
  if (shape.resource_family != null || shape.resource_index != null) {
    return shape.resource_family && Object.hasOwn(RESOURCE_BASES, shape.resource_family)
      && Number.isInteger(shape.resource_index) && shape.resource_index! >= 1 && shape.resource_index! <= 40
      ? [shape.resource_family, shape.resource_index!] : null;
  }
  const word = shape.type_word ?? (shape.type & 65535);
  for (const [family, base] of Object.entries(RESOURCE_BASES)) {
    const index = ((word - (base & 65535)) & 65535) + 1;
    if (index <= 40) return [family, index];
  }
  return null;
}

export function fingerprintShape(shape: CanonicalShape): unknown[] | null {
  const primitive = [1, 2, 8, 16].includes(shape.type) && shape.type_word == null
    && shape.resource_family == null && shape.resource_index == null && shape.source_format !== 'fh6_typecode';
  if (!shape.data.every(Number.isFinite) || shape.data.length < 4
      || shape.data.length > (primitive ? 5 : 7)
      || !shape.color.every(value => Number.isInteger(value) && value >= 0 && value <= 255)
      || ![3, 4].includes(shape.color.length)) return null;
  if (shape.source_format && !['fh6_typecode', 'kfps.primitive.v1'].includes(shape.source_format)) return null;
  const identity = primitive ? ['primitive', shape.type] : resource(shape);
  if (!identity) return null;
  const color = shape.color.length === 3 ? [...shape.color, 255] : [...shape.color];
  if (color.every(value => value <= 1)) for (let i = 0; i < 4; i++) color[i] = color[i]! * 255;
  const geometry = [...shape.data.slice(0, 4), shape.data[4] ?? 0];
  if (primitive && shape.type===1) geometry[4]=0;
  if (!primitive) geometry.push(shape.data[5] ?? 0);
  if (shape.data.length>6 && ![0,1].includes(shape.data[6]!)) return null;
  if (shape.mask != null && shape.data.length>6 && shape.mask !== Boolean(shape.data[6])) return null;
  const mask = shape.mask ?? Boolean(shape.data[6]);
  // Solid masks ignore alpha, while gradient resources may use it. Without
  // resource-specific coverage evidence, nonopaque masks require review.
  if (mask && color[3]!==255) return null;
  if (mask) color.splice(0,3,0,0,0);
  return [primitive ? 'primitive' : 'native', identity, geometry, color, mask];
}

export async function vinylFingerprint(design: CanonicalDesign): Promise<VinylFingerprint> {
  const unsupported = (reason: string): VinylFingerprint => ({ version: 1, status: 'review_required', fingerprint: null, reason });
  if (!design.metadata.schema_known || design.shapes.length < 1 || design.shapes.length > 3001) return unsupported('unsupported_schema');
  const shapes = design.shapes.map(fingerprintShape);
  if (shapes.some(shape => shape === null)) return unsupported('unsupported_shape_semantics');
  // Native zero-alpha nonmask layers do not draw. Legacy bounds influence
  // editor recentering, so uncertainty there is not silently normalized away.
  if (shapes.some(shape=>shape![0]==='primitive' && (shape![3] as number[])[3]===0)) return unsupported('legacy_transparent_bounds');
  const visible=shapes.filter(shape=>(shape![3] as number[])[3]!==0);
  if (!visible.some(shape=>shape![4]===false)) return unsupported('no_visible_artwork');
  return { version: 1, status: 'qualified', fingerprint: await sha256Hex(JSON.stringify(['kfps-vinyl-render-v1', visible])), reason: '' };
}
