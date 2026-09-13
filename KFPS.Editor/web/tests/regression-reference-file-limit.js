async (page, options) => {
  page.setDefaultTimeout(180000);
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const dense=await h.setup(page,output,{layers:2900});
  const trace=await h.monitor(page,output);
  const cdp = await page.context().newCDPSession(page);
  const setFile = async name => {
    const { root } = await cdp.send('DOM.getDocument');
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#overlayInput' });
    await cdp.send('DOM.setFileInputFiles', { nodeId, files: [`${options.fixtures}/${name}`] });
  };
  try {
    await page.evaluate(async () => {
      currentProjectName = 'Real reference boundary';
    });
    await setFile('reference-99.png');
    await page.waitForFunction(() => editorReference.source?.fileName === 'reference-99.png');
    await page.locator('#fitView').click();
    await h.select(page,'Human target');
    await trace.run('near-reference-limit-dense-pointer',async()=> {
      const before=await h.snapshot(page),g=await h.geometry(page);
      await h.drag(page,g.grab,{x:g.grab.x+18,y:g.grab.y+12});
      if(await h.snapshot(page)===before)throw Error('Near-limit pointer movement did nothing');
      await h.undo(page,before);
      await page.mouse.move(g.center.x,g.center.y);
      for(const delta of [-160,160,-160,160])await page.mouse.wheel(0,delta);
    });
    const accepted = await page.evaluate(async () => {
      const bytes = new Blob([editorReference.source.dataUrl]).size;
      if (bytes <= 98 * 1024 * 1024 || bytes >= EDITOR_REFERENCE_MAX_BYTES) throw new Error('Fixture does not exercise the new near-limit reference');
      if (editorReference.sampler.width * editorReference.sampler.height !== 48000000) throw new Error('Decoded reference lost resolution');
      if (JSON.stringify([...editorReference.readOverlayPixel(17, 23)].slice(0, 3)) !== '[18,52,86]') throw new Error('Original marker pixel changed');
      await saveProject();
      if (documentDirty) throw new Error('Accepted reference could not be saved');
      await flushPendingAutosave();
      if (!editorRecovery.status.serverOk || !editorRecovery.status.browserOk) throw new Error('Accepted reference lacks both recovery copies');
      const file = await readEditorDocument(`${PROJECT_FILE_API}?id=Real%20reference%20boundary.fabric-project.json`);
      if (file.payload.editor_source_overlay.data_url !== editorReference.source.dataUrl) throw new Error('Project reference bytes changed');
      await loadProjectPayload(file.payload, 'Real reference boundary');
      window.referenceLimitExpected = { image: editorReference.image, url: editorReference.source.dataUrl, state: JSON.stringify(snapshotShapes()) };
      return { bytes, pixels: editorReference.sampler.width * editorReference.sampler.height };
    });
    await setFile('reference-101.png');
    await page.waitForFunction(() => $('status').textContent.includes(KfpsI18n.t('Reference exceeds the {0} MiB storage budget. Use a smaller image.', EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024))));
    const rejected = await page.evaluate(async () => {
      if (editorReference.image !== referenceLimitExpected.image || editorReference.source.dataUrl !== referenceLimitExpected.url
        || JSON.stringify(snapshotShapes()) !== referenceLimitExpected.state) throw new Error('Rejected file altered existing artwork/reference');
      const saved = await readEditorDocument(`${PROJECT_FILE_API}?id=Real%20reference%20boundary.fabric-project.json`);
      if (saved.payload.editor_source_overlay.data_url !== referenceLimitExpected.url) throw new Error('Rejected reference overwrote project');
      delete window.referenceLimitExpected;
      return { previousImagePreserved: true, previousProjectPreserved: true };
    });
    await page.screenshot({ path: path.join(output,'reference-limit-preserved.png') });
    await page.evaluate(async () => { editorReference.removeOverlay(); clearVinylObjects(); resetHistory(); refreshLayers(); await clearAutosave(); documentDirty = false; });
    return { dense, accepted, rejected, rows:trace.rows,nativeFileInput: true };
  } finally { await trace.close(); await cdp.detach(); }
}
