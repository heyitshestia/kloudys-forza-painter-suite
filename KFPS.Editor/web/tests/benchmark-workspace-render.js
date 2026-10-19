async page => {
  const rows = [];
  for (const count of [240, 2400]) {
    const result = await page.evaluate(async count => {
      const start = performance.now();
      await loadPayload({ shapes: Array.from({ length: count }, (_, index) => ({
        type: [1048677, 1048678, 1048706, 1048712, 1048715][index % 5],
        color: [40 + index % 150, 90 + index % 120, 170, index % 9 ? 255 : 160],
        data: [-690 + index % 60 * 23, 440 - Math.floor(index / 60) * 23, .12, .16, index % 4 * 15, 0, 0],
      })) });
      canvas.setViewportTransform([.6, 0, 0, .6, canvas.width / 2, canvas.height / 2]);
      const loaded = performance.now(), frames = [];
      for (let index = 0; index < 2; index++) {
        const frame = performance.now(); canvas.renderAll(); frames.push(performance.now() - frame);
      }
      return { count, loadedMs: loaded - start, renderMs: frames, renderer: editorRenderer.active ? 'WebGL' : 'CPU',
        canvas: [canvas.width, canvas.height], browserDpr: devicePixelRatio };
    }, count);
    rows.push(result); console.log(JSON.stringify(result));
  }
  fs.writeFileSync(path.join(output, 'render-comparison.json'), JSON.stringify(rows, null, 2));
  return { rows, qualification: 'Same synthetic mixed geometry and software-render path; not a physical GPU frame-rate test.' };
}
