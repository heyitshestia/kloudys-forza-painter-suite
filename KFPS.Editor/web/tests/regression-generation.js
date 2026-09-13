async page => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const blank = async () => { document.querySelectorAll('dialog[open]').forEach(d => d.close()); documentDirty = false; await startBlankCanvas(); };
    const makeFile = async (mime, width = 48, height = 32) => {
      const element = document.createElement('canvas'); element.width = width; element.height = height;
      const ctx = element.getContext('2d');
      ctx.fillStyle = '#20a0c0'; ctx.fillRect(0, 0, width, height);
      if (width < 100) {
        ctx.clearRect(0, 0, 4, 4);
        ctx.fillStyle = 'rgba(240,30,60,0.7)'; ctx.fillRect(8, 4, 16, 20);
        ctx.fillStyle = '#f0c030'; ctx.fillRect(32, 8, 8, 16);
      }
      const blob = await new Promise(resolve => element.toBlob(resolve, mime));
      element.width = element.height = 1;
      return new File([blob], 'Pixel.' + mime.split('/')[1], { type: blob.type });
    };
    const files = [];
    for (const mime of ['image/png', 'image/jpeg', 'image/webp']) files.push(await makeFile(mime));
    files.push(new File(['<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32"><rect width="48" height="32" fill="#20a0c0"/><rect x="8" y="8" width="16" height="16" fill="#f0c030"/></svg>'], 'Pixel.svg', { type: 'image/svg+xml' }));
    const formats = [];
    for (const file of files) {
      const image = await loadImageFromFile(file);
      const grid = sampleDetectedPixelArtGrid(image, 128, 24);
      const expected = buildPixelArtRuns(grid.rows);
      const actual = await analyzePixelArtFile(file, { alphaCutoff: 128, tolerance: 24, maxRuns: 3000 });
      check(JSON.stringify(actual.runs) === JSON.stringify(expected), `${file.type}: worker changed decoded colors or rectangles`);
      check(actual.gridW === grid.gridW && actual.gridH === grid.gridH, `${file.type}: detected grid changed`);
      formats.push({ format: file.type, rectangles: actual.runs.length });
    }
    await blank();
    pixelArtSourceFile = files[0];
    document.getElementById('pixelArtClearPrevious').checked = true;
    await generatePixelArtRectangles();
    check(vinylObjects().length > 0, 'Successful pixel generation must add real editable layers');
    const pixelBefore = JSON.stringify(snapshotShapes());
    const pixelCount = vinylObjects().length;
    await generatePixelArtRectangles();
    check(vinylObjects().length === pixelCount, 'Replace previous pixel generation must not append');
    await undo();
    check(JSON.stringify(snapshotShapes()) === pixelBefore, 'Pixel replacement undo must preserve exact source layers');
    await redo();
    const originalMake = makeFabricObject;
    const beforeFailure = JSON.stringify(snapshotShapes());
    makeFabricObject = async () => { throw new Error('Injected pixel build failure'); };
    try { await generatePixelArtRectangles(); } finally { makeFabricObject = originalMake; }
    check(JSON.stringify(snapshotShapes()) === beforeFailure, 'Failed pixel rebuild must preserve previous layers');
    await blank();

    const largeFile = await makeFile('image/png', 6000, 4000);
    await loadPayload({ shapes: [{ type: 1048677, data: [0,0,1,1,0,0,0], color: [40,150,210,255] }] });
    canvas.setActiveObject(vinylObjects()[0]);
    pixelArtSourceFile = largeFile;
    let completed = false;
    const generation = generatePixelArtRectangles().finally(() => { completed = true; });
    let edits = 0, savedWhileRunning = false;
    const started = performance.now();
    const gaps = [];
    let last = performance.now();
    while (!completed && edits < 12) {
      await nextFrame();
      gaps.push(performance.now() - last); last = performance.now();
      nudgeSelected(1, 0); flushPendingNudgeHistory(); edits++;
      await flushPendingAutosave();
      savedWhileRunning ||= !completed && editorRecovery.status.serverOk === true;
    }
    await generation;
    check(edits > 0 && savedWhileRunning, 'Recovery and canvas edits must progress during real 24 MP analysis');
    check(vinylObjects().length === 1 && objectToShape(vinylObjects()[0]).data[0] === edits, 'Concurrent edits must survive generation');
    check(!pixelArtGenerationRunning && !pixelArtAnalysisCancel, 'Pixel worker must release its task and controls');
    const concurrent = { edits, savedWhileRunning, milliseconds: performance.now() - started, maxObservedGapMs: Math.max(...gaps) };
    const pending = generatePixelArtRectangles();
    documentDirty = false; await startBlankCanvas(); await pending;
    check(!vinylObjects().length && !pixelArtGenerationRunning && !pixelArtAnalysisCancel, 'New must cancel pending pixel analysis without resurrecting layers');
    const beforeBad = JSON.stringify(snapshotShapes());
    pixelArtSourceFile = new File(['broken'], 'bad.png', { type: 'image/png' });
    await generatePixelArtRectangles();
    check(JSON.stringify(snapshotShapes()) === beforeBad && !pixelArtGenerationRunning, 'Bad image must leave the workspace usable');

    await blank();
    document.getElementById('textVinylInput').value = 'ABC';
    document.getElementById('textVinylClearPrevious').checked = true;
    await generateTextVinylShapes();
    const textBefore = JSON.stringify(snapshotShapes());
    makeFabricObject = async () => { throw new Error('Injected text build failure'); };
    try { await generateTextVinylShapes(); } finally { makeFabricObject = originalMake; }
    check(JSON.stringify(snapshotShapes()) === textBefore && !historyLocked, 'Failed text rebuild must preserve previous layers');
    return { formats, pixelReplacementUndo: true, pixelFailureAtomic: true, concurrent, cancellation: true, corruptImage: true, textFailureAtomic: true };
  });
}
