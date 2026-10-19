import { invertMatrix, mapPoint, placementMatrix, sectionToPaint } from './layout-model.mjs';

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

export function sampleMask(pages, uv, slot) {
  if (!Array.isArray(uv) || uv.length !== 2 || !uv.every(Number.isFinite) || uv.some(v => v < 0 || v > 1)) return 0;
  if (!Number.isInteger(slot) || slot < 0 || slot >= 11) return 0;
  const page = pages[Math.floor(slot / 4)];
  if (!page?.data || !page.width || !page.height) return 0;
  const x = uv[0] * page.width - .5, y = uv[1] * page.height - .5;
  const left = Math.floor(x), top = Math.floor(y), fx = x - left, fy = y - top;
  const get = (px, py) => page.data[(clamp(py, 0, page.height - 1) * page.width + clamp(px, 0, page.width - 1)) * 4 + slot % 4] / 255;
  return get(left, top) * (1 - fx) * (1 - fy) + get(left + 1, top) * fx * (1 - fy)
    + get(left, top + 1) * (1 - fx) * fy + get(left + 1, top + 1) * fx * fy;
}

export function chooseSurfaceSection({ uv3, normal, kind, allowed, sections, pages, enabled, uvScale = [.5, 1] }) {
  if (!uv3?.every(Number.isFinite) || !normal?.every(Number.isFinite)) return null;
  if (!Array.isArray(uvScale) || uvScale.length !== 2 || !uvScale.every(value => Number.isFinite(value) && value > 0)) return null;
  const uv = [uv3[0] * uvScale[0], uv3[1] * uvScale[1]];
  let best = null;
  // Match the native-UV material's ordering and strict >0.5 coverage threshold.
  for (const section of sections) {
    const slot = section.slot_index;
    if (section.kind !== kind || !(allowed & (1 << slot)) || (enabled && enabled[slot] < .5)) continue;
    const facing = section.facing.reduce((sum, value, index) => sum + value * normal[index], 0);
    if (!(facing > 0)) continue;
    const coverage = sampleMask(pages, uv, slot);
    if (coverage > .5 && (!best || coverage > best.coverage)) best = { section, coverage, uv };
  }
  return best;
}

export function atlasToSectionPoint(section, uv, paintSize) {
  const [sl, st, sr, sb] = section.source_region;
  if (!(sr > sl && sb > st)) throw Error('Invalid section region.');
  const [pl, pt, pr, pb] = section.paint_region;
  const u = pl + clamp((uv[0] - sl) / (sr - sl), 0, 1) * (pr - pl);
  const v = pt + clamp((uv[1] - st) / (sb - st), 0, 1) * (pb - pt);
  return mapPoint(invertMatrix(sectionToPaint(section, paintSize)), u * paintSize[0], v * paintSize[1]);
}

export function selectionFrame(section, paintSize, placement, bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4 || !bounds.every(Number.isFinite)
      || bounds[2] <= bounds[0] || bounds[3] <= bounds[1]) return null;
  const paintInverse = invertMatrix(sectionToPaint(section, paintSize));
  const placementInverse = invertMatrix(placementMatrix(placement));
  const local = (u, v) => mapPoint(placementInverse, ...mapPoint(paintInverse, u * paintSize[0], v * paintSize[1]));
  const origin = local(0, 0), x = local(1, 0), y = local(0, 1);
  return { slot: section.slot_index,
    x: [x[0] - origin[0], y[0] - origin[0], origin[0]],
    y: [x[1] - origin[1], y[1] - origin[1], origin[1]],
    bounds: [bounds[0] - 1024, bounds[1] - 512, bounds[2] - 1024, bounds[3] - 512] };
}

export function gestureTransform(placement, mode, start, current, options = {}) {
  if (![...start.point, ...current.point, ...start.screen, ...current.screen].every(Number.isFinite)) throw Error('Invalid surface gesture.');
  const dx = current.point[0] - start.point[0], dy = start.point[1] - current.point[1];
  const screenX = current.screen[0] - start.screen[0], screenY = current.screen[1] - start.screen[1];
  const snap = (value, step) => options.snap ? Math.round(value / step) * step : value;
  if (mode === 'move') return { x: clamp(snap(placement.x + dx, 10), -4096, 4096), y: clamp(snap(placement.y + dy, 10), -4096, 4096) };
  if (mode === 'scale') {
    const horizontal = Math.exp(clamp(screenX / 180, -8, 8));
    if (options.aspectLocked || options.snap) {
      const factor = clamp(horizontal, Math.max(.01 / placement.scaleX, .01 / placement.scaleY), Math.min(8 / placement.scaleX, 8 / placement.scaleY));
      return { scaleX: placement.scaleX * factor, scaleY: placement.scaleY * factor };
    }
    return { scaleX: clamp(placement.scaleX * horizontal, .01, 8), scaleY: clamp(placement.scaleY * Math.exp(clamp(-screenY / 180, -8, 8)), .01, 8) };
  }
  if (mode === 'rotate') {
    const center = [1024 + placement.x, 512 - placement.y];
    const first = [start.point[0] - center[0], center[1] - start.point[1]];
    const second = [current.point[0] - center[0], center[1] - current.point[1]];
    let degrees = screenX * .5;
    if (Math.hypot(...first) > 30 && Math.hypot(...second) > 30) {
      let delta = Math.atan2(second[1], second[0]) - Math.atan2(first[1], first[0]);
      delta = Math.atan2(Math.sin(delta), Math.cos(delta));
      degrees = delta * 180 / Math.PI;
    }
    return { rotation: clamp(snap(placement.rotation + degrees, 15), -3600, 3600) };
  }
  if (mode === 'skew') return { skew: clamp(snap((placement.skew || 0) + screenX / 180, .1), -4, 4) };
  throw Error('Unknown surface editing mode.');
}
