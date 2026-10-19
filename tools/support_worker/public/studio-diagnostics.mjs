// Same bounded, no-free-text records as the installed Studio collector.
export const ENUMS = {
  event: 'host readiness render counts action error request closed'.split(' '),
  host: ['backend', 'native', 'chrome', 'unknown'],
  gpu_policy: ['auto', 'opengl', 'd3d11', 'browser-default', 'unknown'],
  action: 'launch import edit undo redo save reopen source_edit source_return cancel car_switch export checkpoint theme language component reset render library recovery selection'.split(' '),
  outcome: ['start', 'ok', 'error', 'cancelled', 'stale', 'busy', 'requested'],
  error_code: 'http_4xx http_5xx network aborted javascript preview context_lost shader operation timeout unknown'.split(' '),
};
export const NUMBERS = {
  ...Object.fromEntries('duration_ms frame_ms frame_mean_ms frame_max_ms compose_ms load_ms'.split(' ').map(k => [k, 600000])),
  canvas_width: 32768, canvas_height: 32768, pixel_ratio: 8,
  source_count: 4096, placement_count: 65536, section_count: 64, shape_count: 1000000,
  geometries: 1000000, textures: 1000000, programs: 100000, draw_calls: 1000000,
  triangles: 1000000000, resource_bytes: 16 * 1024 ** 3, frame_count: 2 ** 31 - 1, http_status: 599,
};
export const BOOLEANS = ['ready', 'webgl', 'visible'];
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const metadata = ['schema_version', 'utc', 'session', 'sequence'];
export function validStudioRecord(value) {
  if (!object(value) || Object.keys(value).length > 44 || value.schema_version !== 1
      || !Number.isSafeInteger(value.sequence) || value.sequence < 1
      || typeof value.session !== 'string' || !/^[a-f0-9]{16}$/.test(value.session)
      || typeof value.utc !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(value.utc)
      || !ENUMS.event.includes(value.event)) return false;
  const fields = Object.entries(value).filter(([key]) => !metadata.includes(key));
  if (fields.length > 40) return false;
  for (const [key, item] of fields) {
    if (Object.hasOwn(ENUMS, key)) { if (!ENUMS[key].includes(item)) return false; }
    else if (Object.hasOwn(NUMBERS, key)) {
      if (typeof item !== 'number' || !Number.isFinite(item) || item < 0 || item > NUMBERS[key]
          || !key.endsWith('_ms') && key !== 'pixel_ratio' && !Number.isSafeInteger(item)) return false;
    } else if (BOOLEANS.includes(key)) { if (typeof item !== 'boolean') return false; }
    else if (key === 'app_version') { if (typeof item !== 'string' || !/^[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}$/.test(item)) return false; }
    else return false;
  }
  return new TextEncoder().encode(JSON.stringify(value)).length <= 1024;
}
