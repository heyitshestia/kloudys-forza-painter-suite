"use strict";

importScripts("editor-pixel-core.js?v=1");

self.onmessage = async event => {
  const { file, pixels, alphaCutoff, tolerance, maxRuns } = event.data;
  let bitmap = null;
  let surface = null;
  try {
    let pixelData = pixels;
    if (!pixelData) {
      try { bitmap = await createImageBitmap(file); }
      catch (error) {
        // Chromium cannot decode every SVG directly to an ImageBitmap. Keep the
        // existing SVG rasterization path without moving analysis onto the UI.
        if (file?.type === "image/svg+xml" || /\.svg$/i.test(file?.name || "")) {
          self.postMessage({ rasterizeSvg: true });
          return;
        }
        throw new Error("Could not decode the pixel-art source image.");
      }
      surface = new OffscreenCanvas(bitmap.width, bitmap.height);
      const context = surface.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("Could not prepare the pixel-art source image.");
      context.drawImage(bitmap, 0, 0);
      pixelData = { width: bitmap.width, height: bitmap.height,
        data: context.getImageData(0, 0, bitmap.width, bitmap.height).data };
      bitmap.close(); bitmap = null;
      surface.width = surface.height = 1;
    }
    self.postMessage({ value: KfpsPixelCore.analyzePixelArt(pixelData, alphaCutoff, tolerance, maxRuns) });
  } catch (error) {
    self.postMessage({ error: error.message || String(error) });
  } finally {
    bitmap?.close();
    if (surface) surface.width = surface.height = 1;
  }
};
