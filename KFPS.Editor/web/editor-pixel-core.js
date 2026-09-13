(function installPixelCore(global) {
"use strict";

function colorDistance(a, b) {
  return Math.max(
    Math.abs(Number(a?.[0] || 0) - Number(b?.[0] || 0)),
    Math.abs(Number(a?.[1] || 0) - Number(b?.[1] || 0)),
    Math.abs(Number(a?.[2] || 0) - Number(b?.[2] || 0)),
    Math.abs(Number(a?.[3] ?? 255) - Number(b?.[3] ?? 255)),
  );
}

function pixelArtColorAt(pixelData, x, y) {
  const offset = ((y * pixelData.width) + x) * 4;
  return [
    pixelData.data[offset],
    pixelData.data[offset + 1],
    pixelData.data[offset + 2],
    pixelData.data[offset + 3],
  ];
}

function pixelArtVisible(color, alphaCutoff) {
  return Number(color?.[3] || 0) > alphaCutoff;
}

function pixelArtEdgeBetween(a, b, alphaCutoff, tolerance) {
  const aVisible = pixelArtVisible(a, alphaCutoff);
  const bVisible = pixelArtVisible(b, alphaCutoff);
  if (aVisible !== bVisible) return true;
  return aVisible && bVisible && colorDistance(a, b) > tolerance;
}

function collectPixelArtEdges(pixelData, axis, alphaCutoff, tolerance) {
  const edges = [];
  if (axis === "x") {
    const rowStep = Math.max(1, Math.floor(pixelData.height / 160));
    for (let y = 0; y < pixelData.height; y += rowStep) {
      for (let x = 1; x < pixelData.width; x++) {
        if (pixelArtEdgeBetween(
          pixelArtColorAt(pixelData, x - 1, y),
          pixelArtColorAt(pixelData, x, y),
          alphaCutoff,
          tolerance,
        )) {
          edges.push(x);
        }
      }
    }
  } else {
    const colStep = Math.max(1, Math.floor(pixelData.width / 160));
    for (let x = 0; x < pixelData.width; x += colStep) {
      for (let y = 1; y < pixelData.height; y++) {
        if (pixelArtEdgeBetween(
          pixelArtColorAt(pixelData, x, y - 1),
          pixelArtColorAt(pixelData, x, y),
          alphaCutoff,
          tolerance,
        )) {
          edges.push(y);
        }
      }
    }
  }
  return [...new Set(edges)].sort((a, b) => a - b);
}

function dominantPixelArtStep(edges, dimension) {
  if (!edges.length) return Math.max(1, Math.ceil(dimension / 256));
  const counts = new Map();
  for (let index = 1; index < edges.length; index++) {
    const diff = edges[index] - edges[index - 1];
    if (diff < 2 || diff > 96) continue;
    counts.set(diff, (counts.get(diff) || 0) + 1);
  }
  let bestStep = 1;
  let bestCount = 0;
  counts.forEach((count, step) => {
    if (count > bestCount || (count === bestCount && step > bestStep)) {
      bestStep = step;
      bestCount = count;
    }
  });
  if (bestCount < 4) return Math.max(1, Math.ceil(dimension / 256));
  return Math.max(1, bestStep);
}

function dominantPixelArtOffset(edges, step) {
  if (step <= 1 || !edges.length) return 0;
  const counts = new Map();
  edges.forEach((edge) => {
    const offset = ((edge % step) + step) % step;
    counts.set(offset, (counts.get(offset) || 0) + 1);
  });
  let bestOffset = 0;
  let bestCount = 0;
  counts.forEach((count, offset) => {
    if (count > bestCount || (count === bestCount && offset < bestOffset)) {
      bestOffset = offset;
      bestCount = count;
    }
  });
  return bestOffset;
}

function pixelArtIntervals(dimension, step, offset) {
  const effectiveStep = Math.max(1, step);
  const boundaries = new Set([0, dimension]);
  for (let position = offset; position < dimension; position += effectiveStep) {
    if (position > 0) boundaries.add(position);
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  const intervals = [];
  for (let index = 1; index < sorted.length; index++) {
    const start = sorted[index - 1];
    const end = sorted[index];
    if (end > start) intervals.push({ start, end, size: end - start });
  }
  return intervals;
}

function dominantPixelArtCell(pixelData, xInterval, yInterval, alphaCutoff, tolerance) {
  let visible = 0;
  const area = Math.max(1, xInterval.size * yInterval.size);
  const exact = new Map();
  for (let y = yInterval.start; y < yInterval.end; y++) {
    for (let x = xInterval.start; x < xInterval.end; x++) {
      const color = pixelArtColorAt(pixelData, x, y);
      if (!pixelArtVisible(color, alphaCutoff)) continue;
      visible++;
      const exactKey = `${color[0]}:${color[1]}:${color[2]}`;
      exact.set(exactKey, (exact.get(exactKey) || 0) + 1);
    }
  }
  if (!visible || visible / area < 0.55) return null;
  let bestColor = null;
  let bestCount = 0;
  exact.forEach((count, exactKey) => {
    const color = exactKey.split(":").map((value) => Number(value));
    if (count > bestCount) {
      bestCount = count;
      bestColor = color;
    }
  });
  if (!bestColor) return null;
  return [bestColor[0], bestColor[1], bestColor[2], 255];
}

function detectPixelArtGrid(pixelData, alphaCutoff, tolerance) {
  const xEdges = collectPixelArtEdges(pixelData, "x", alphaCutoff, tolerance);
  const yEdges = collectPixelArtEdges(pixelData, "y", alphaCutoff, tolerance);
  let stepX = dominantPixelArtStep(xEdges, pixelData.width);
  let stepY = dominantPixelArtStep(yEdges, pixelData.height);
  if (stepX > 1 && stepY > 1 && Math.max(stepX, stepY) / Math.min(stepX, stepY) <= 1.35) {
    const sharedStep = Math.min(stepX, stepY);
    stepX = sharedStep;
    stepY = sharedStep;
  }
  const offsetX = dominantPixelArtOffset(xEdges, stepX);
  const offsetY = dominantPixelArtOffset(yEdges, stepY);
  const xIntervals = pixelArtIntervals(pixelData.width, stepX, offsetX);
  const yIntervals = pixelArtIntervals(pixelData.height, stepY, offsetY);
  return { gridW: xIntervals.length, gridH: yIntervals.length, stepX, stepY, offsetX, offsetY, xIntervals, yIntervals };
}

function* pixelArtRows(pixelData, grid, alphaCutoff, tolerance) {
  for (const yInterval of grid.yIntervals) {
    yield grid.xIntervals.map(xInterval => dominantPixelArtCell(pixelData, xInterval, yInterval, alphaCutoff, tolerance));
  }
}

function sampleDetectedPixelArtGrid(pixelData, alphaCutoff, tolerance) {
  const grid = detectPixelArtGrid(pixelData, alphaCutoff, tolerance);
  const { xIntervals, yIntervals, ...metadata } = grid;
  return { ...metadata, rows: Array.from(pixelArtRows(pixelData, grid, alphaCutoff, tolerance)) };
}

function pixelArtExactColorKey(color) {
  return `${Number(color?.[0] || 0)}:${Number(color?.[1] || 0)}:${Number(color?.[2] || 0)}:${Number(color?.[3] ?? 255)}`;
}

function buildPixelArtRuns(rows, maxRuns = Infinity) {
  const merged = [];
  let active = new Map();
  let y = 0;
  for (const row of rows) {
    const nextActive = new Map();
    let x = 0;
    while (x < row.length) {
      const color = row[x];
      if (!color) { x++; continue; }
      const start = x;
      const key = pixelArtExactColorKey(color);
      x++;
      while (x < row.length && row[x] && pixelArtExactColorKey(row[x]) === key) x++;
      const width = x - start;
      const mergeKey = `${start}:${width}:${key}`;
      const previous = active.get(mergeKey);
      if (previous && previous.y + previous.height === y) {
        previous.height++;
        nextActive.set(mergeKey, previous);
      } else {
        const run = { x: start, y, width, height: 1, key, color: [...color] };
        merged.push(run);
        // Finalized rectangles never combine with one another in this algorithm.
        if (merged.length > maxRuns) return null;
        nextActive.set(mergeKey, run);
      }
    }
    active = nextActive;
    y++;
  }
  return merged;
}

function analyzePixelArt(pixelData, alphaCutoff, tolerance, maxRuns) {
  const grid = detectPixelArtGrid(pixelData, alphaCutoff, tolerance);
  const { xIntervals, yIntervals, ...metadata } = grid;
  const runs = buildPixelArtRuns(pixelArtRows(pixelData, grid, alphaCutoff, tolerance), maxRuns);
  return { ...metadata, runs, overflow: runs === null };
}

const api = { colorDistance, pixelArtColorAt, pixelArtVisible, pixelArtEdgeBetween, collectPixelArtEdges, dominantPixelArtStep, dominantPixelArtOffset, pixelArtIntervals, dominantPixelArtCell, sampleDetectedPixelArtGrid, pixelArtExactColorKey, buildPixelArtRuns, analyzePixelArt };
if (typeof module !== "undefined" && module.exports) module.exports = api;
global.KfpsPixelCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
