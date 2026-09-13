async page => {
  const result = await page.evaluate(async () => {
    const families = ["Primitives", "Gradient_Shapes", ...ALPHA_MESH_IMAGE_FAMILIES];
    const shapes = families.flatMap((family, f) => Array.from({ length: 80 }, (_, i) => {
      const slot = i % 40 + 1, index = f * 80 + i;
      return { type: editorCatalog.resourceToTypeCode(family, slot),
        resource_family: family, resource_index: slot,
        color: [220, 30, 80, i < 40 ? 255 : 96],
        data: [(index % 20) * 120 - 1140, Math.floor(index / 20) * 120 - (families.length * 4 - 1) * 60, .48, .48, 0, 0, 0] };
    }));
    await loadPayload({ shapes });
    editorRenderer.endHybridRenderNow();
    canvas.discardActiveObject();
    canvas.backgroundColor = "#dddddd";
    const zoom = Math.min(canvas.width / 2440, canvas.height / (families.length * 480 + 80));
    canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
    canvas.renderAll();
    const w = canvas.width, h = canvas.height;
    const before = canvas.contextContainer.getImageData(0, 0, w, h).data;
    const baseline = canvas.lowerCanvasEl.toDataURL();
    if (!editorRenderer.hybridRenderNow()) throw Error("Preview unavailable: " + editorRenderer.disabledReason);
    const renderer = editorRenderer.renderer, gl = renderer.gl;
    const raw = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, raw);
    const after = new Uint8ClampedArray(raw.length);
    for (let y = 0; y < h; y++) after.set(raw.subarray((h-y-1)*w*4, (h-y)*w*4), y*w*4);
    const image = document.createElement("canvas"); image.width=w; image.height=h;
    image.getContext("2d").putImageData(new ImageData(after,w,h),0,0);
    const comparisons = vinylObjects().map((object, index) => {
      const p = fabric.util.transformPoint(object.getCenterPoint(), canvas.viewportTransform);
      const radius = 56 * zoom;
      let error=0, count=0, stillInk=0, movingInk=0, stillSignal=0, movingSignal=0;
      for(let y=Math.max(0,Math.floor(p.y-radius));y<Math.min(h,p.y+radius);y++) {
        for(let x=Math.max(0,Math.floor(p.x-radius));x<Math.min(w,p.x+radius);x++) {
          const i=(y*w+x)*4;
          for(let c=0;c<3;c++) error+=Math.abs(before[i+c]-after[i+c]);
          if(before[i]-before[i+1]>25) stillInk++;
          if(after[i]-after[i+1]>25) movingInk++;
          stillSignal+=Math.max(0,before[i]-before[i+1]);
          movingSignal+=Math.max(0,after[i]-after[i+1]);
          count++;
        }
      }
      return {family:object.kloudy.resource_family,slot:object.kloudy.resource_index,
        opacity:object.opacity,alphaMesh:object.kloudy.alpha_mesh_image,renderScale:object.kloudy.render_scale,
        gradient:isGradientObject(object),mae:error/(count*3),stillInk,movingInk,stillSignal,movingSignal,
        mesh:!!editorRenderer.hybridMeshForObject(object),index};
    });
    return {baseline, preview:image.toDataURL(),comparisons};
  });
  for(const key of ["baseline","preview"]) {
    fs.writeFileSync(path.join(output,`motion-alpha-${key}.png`),Buffer.from(result[key].split(",")[1],"base64"));
    delete result[key];
  }
  fs.writeFileSync(path.join(output,"motion-alpha-comparison.json"),JSON.stringify(result,null,2));
  // Integrated contrast tolerates subpixel edge antialiasing without accepting
  // the ~98% area loss caused by applying image raster scale to resource meshes.
  const missing = result.comparisons.filter(row => row.alphaMesh && row.stillSignal >= 100 && row.movingSignal < row.stillSignal * .65);
  if (missing.length) throw Error("Translucent shapes lost coverage: " + JSON.stringify(missing));
  return result;
}
