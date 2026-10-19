function summarize(values) {
  if (!values.length || values.some(value => !Number.isFinite(value) || value < 0)) {
    throw Error('Frame measurements must be nonempty, finite, and nonnegative');
  }
  const sorted = [...values].sort((a, b) => a - b);
  return { samples: values.length, minMs: sorted[0], medianMs: sorted[Math.ceil(sorted.length / 2) - 1],
    p95Ms: sorted[Math.ceil(sorted.length * .95) - 1], maxMs: sorted.at(-1),
    smallSampleWarning: values.length < 100 };
}

// Kept self-contained because Playwright serializes this into the actual page.
function inspectPixels(data) {
  if (!data.length || data.length % 4) throw Error('Expected nonempty RGBA pixels');
  const histogram = new Map();
  let opaque = 0;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3]) opaque++;
    const key = `${data[i]},${data[i + 1]},${data[i + 2]},${data[i + 3]}`;
    histogram.set(key, (histogram.get(key) || 0) + 1);
  }
  let dominant = 0;
  for (const count of histogram.values()) dominant = Math.max(dominant, count);
  return { pixels: data.length / 4, opaque, colors: histogram.size,
    nonDominant: data.length / 4 - dominant,
    nonblank: opaque > 100 && histogram.size > 8 && data.length / 4 - dominant > 100 };
}

module.exports = { summarize, inspectPixels };
