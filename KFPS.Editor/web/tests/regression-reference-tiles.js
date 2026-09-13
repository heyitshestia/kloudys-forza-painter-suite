async page => page.evaluate(async () => {
  const source = document.createElement("canvas");
  source.width = 4099; source.height = 2053;
  const ctx = source.getContext("2d", { willReadFrequently: true });
  const gradient = ctx.createLinearGradient(0, 0, source.width, source.height);
  gradient.addColorStop(0, "#12345680"); gradient.addColorStop(1, "#abcdef");
  ctx.fillStyle = gradient; ctx.fillRect(0, 0, source.width, source.height);
  ctx.fillStyle = "#ff0000"; ctx.fillRect(255, 256, 1, 1);
  await editorReference.loadOverlayImageFromUrl(source.toDataURL(), "tile-accuracy.png");
  if (editorReference.sampler.tiles.size || editorReference.sampler.canvas) throw new Error("Sampler eagerly decoded pixels");
  let samples = 0;
  const coordinates = [[255, 256], [4098, 2052], [0, 0], [256, 255]];
  for (let y = 0; y < source.height; y += 128) for (let x = 0; x < source.width; x += 127) coordinates.push([x, y]);
  for (const [x, y] of coordinates) {
    const actual = editorReference.readOverlayPixel(x, y);
    const expected = ctx.getImageData(x, y, 1, 1).data;
    if (actual.some((value, index) => value !== expected[index])) throw new Error(`Tile pixel mismatch at ${x},${y}: ${actual} / ${expected}`);
    if (editorReference.sampler.tiles.size > 32) throw new Error("Tile cache exceeded memory bound");
    samples++;
  }
  if (String(editorReference.readOverlayPixel(255, 256)) !== "255,0,0,255") throw new Error("Evicted tile did not recreate exact one-pixel marker");
  const tileBytes = [...editorReference.sampler.tiles.values()].reduce((sum, tile) => sum + tile.data.byteLength, 0);
  const surface = editorReference.sampler.canvas;
  editorReference.removeOverlay();
  if (editorReference.sampler || surface.width !== 1 || surface.height !== 1) throw new Error("Sampler backing storage not released");
  source.width = source.height = 1;
  await clearAutosave(); documentDirty = false;
  return { exactSamples: samples, tileBytes, maxBytes: 8 * 1024 * 1024, eviction: true, released: true };
})
