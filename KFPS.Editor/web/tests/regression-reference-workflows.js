async page => {
  const results = await page.evaluate(async () => {
    const results = [];
    const red = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"><rect width="64" height="32" fill="#e02040"/></svg>');
    const blue = red.replace('%23e02040', '%232040e0');
    const check = (condition, message) => { if (!condition) throw Error(message); };
    const setup = async () => {
      await loadPayload({ shapes: Array.from({ length: 300 }, (_, index) => ({
        type: 1048677, data: [index ? 100 + index : 0, 0, .1, .1, 0, 0, 0], color: [20, 80, 140, 255],
      })) }, { projectName: null });
      await editorReference.loadOverlayImageFromUrl(red, "reference-workflow.svg", { layeredState: null });
      selectObjects([vinylObjects()[0]], "reference workflow");
      await flushPendingAutosave();
    };
    const run = async (name, test) => {
      try { await setup(); await test(); results.push({ name, passed: true }); }
      catch (error) { results.push({ name, passed: false, error: String(error.message) }); }
      document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    };
    await run("opacity preserves restored transform", async () => {
      const state = editorReference.sourceOverlayProjectState();
      Object.assign(state.transform, { left: 45, top: -35, scaleX: 3, scaleY: 2, angle: 25, skewX: 9 });
      await editorReference.loadOverlayImageFromUrl(red, "transformed.svg", { layeredState: null, projectState: state });
      const before = editorReference.sourceOverlayProjectState().transform;
      $("overlayOpacity").value = "45";
      $("overlayOpacity").dispatchEvent(new Event("input", { bubbles: true }));
      const after = editorReference.sourceOverlayProjectState().transform;
      check(after.opacity === .45, "Opacity control was not applied");
      delete before.opacity; delete after.opacity;
      check(JSON.stringify(before) === JSON.stringify(after), "Changing opacity resized or moved the reference");
    });
    await run("project restores reference order", async () => {
      setOverlayLayerMode("below");
      const project = editableProjectPayload("Reference order");
      project.editor_source_overlay.controls.layer_mode = "above";
      await loadProjectPayload(project, "Reference order");
      check(overlayLayerMode === "above", "Saved above/below reference order was ignored");
      check(canvas.getObjects().indexOf(editorReference.image) > canvas.getObjects().indexOf(vinylObjects()[0]), "Reference order differs from its control");
    });
    await run("reference installation survives display failure", async () => {
      markCurrentHistorySaved("Reference fault");
      const revision = editorRecovery.revision;
      const refresh = updateHud;
      let injected = false;
      updateHud = (...args) => {
        if (!injected && editorReference.source?.dataUrl === blue) { injected = true; throw Error("Injected reference display failure"); }
        return refresh(...args);
      };
      try { await editorReference.loadOverlayImageFromUrl(blue, "replacement.svg", { layeredState: null }); }
      catch (_) {} finally { updateHud = refresh; }
      check(injected, "Display failure was not injected");
      check(editorReference.source?.dataUrl === blue && editorReference.image.getElement().naturalWidth === 64, "Installed reference was cleared after its display failed");
      check(editorRecovery.revision > revision && isDocumentDirty(), "Installed reference escaped dirty/recovery state");
      await flushPendingAutosave();
      const saved = await readAutosavePayload();
      check(saved.editor_source_overlay?.data_url === blue, "Installed reference did not reach recovery");
    });
    await run("sample color survives display failure", async () => {
      const before = JSON.stringify(snapshotShapes()), index = editorHistory.index;
      const refresh = updateSelectionPanel;
      let injected = false;
      updateSelectionPanel = (...args) => {
        if (!injected && JSON.stringify(snapshotShapes()) !== before) { injected = true; throw Error("Injected sample display failure"); }
        return refresh(...args);
      };
      try { sampleOverlayColorForSelected(); } catch (_) {} finally { updateSelectionPanel = refresh; }
      check(injected, "Sample display failure was not injected");
      check(editorHistory.index === index + 1, "Sampled color escaped undo history");
      check(JSON.stringify(snapshotShapes()) === JSON.stringify(currentHistoryState().shapes), "Sampled color differs from committed history");
      await flushPendingAutosave(); await undo();
      check(JSON.stringify(snapshotShapes()) === before, "Sampled color could not be undone exactly");
    });
    await run("sampling updates remembered color and automatic mode has undo", async () => {
      const before = JSON.stringify(snapshotShapes()), index = editorHistory.index;
      $("autoOverlayColor").checked = true;
      $("autoOverlayColor").dispatchEvent(new Event("change", { bubbles: true }));
      $("autoOverlayColor").checked = false;
      check(editorHistory.index === index + 1, "Enabling automatic sampling escaped history");
      check(rememberedColor.slice(0, 3).join() === "224,32,64", "Sampled color was not remembered");
      await undo();
      check(JSON.stringify(snapshotShapes()) === before, "Automatic sample could not be undone");
    });
    await run("layered reference refresh preserves transform and recovery", async () => {
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"><g id="color_1"><rect width="64" height="32" fill="#e02040"/></g><g id="color_2"><rect width="64" height="32" fill="#2040e0"/></g></svg>';
      const state = editorReference.parseLayeredSvg(svg, "layered.svg");
      await editorReference.loadOverlayImageFromUrl(editorReference.layeredSvgDataUrl(state), "layered.svg", { layeredState: state });
      editorReference.image.set({ left: 25, top: -45, scaleX: 3, scaleY: 2, angle: 27, skewX: 4 });
      const transform = JSON.stringify(editorReference.sourceOverlayProjectState().transform);
      await editorReference.setLayeredOverlayViewMode("selected");
      await editorReference.setLayeredOverlayLayer(0);
      check(JSON.stringify(editorReference.sourceOverlayProjectState().transform) === transform, "SVG layer switching resized the reference");
      check(Array.from(editorReference.readOverlayPixel(16, 16)).join() === "224,32,64,255", "Selected SVG layer pixels were not rendered");
      await flushPendingAutosave();
      const recovery = await readAutosavePayload();
      check(recovery.editor_source_overlay.layered_svg.selected_index === 0 && recovery.editor_source_overlay.layered_svg.view_mode === "selected", "SVG selection did not reach recovery");
      const originalImage = window.Image;
      window.Image = function () {
        const image = new originalImage();
        Object.defineProperty(image, "src", { set() { queueMicrotask(() => image.onerror?.()); } });
        return image;
      };
      try { check(await editorReference.setLayeredOverlayLayer(1) === false, "Failed SVG refresh reported success"); }
      finally { window.Image = originalImage; }
      check(editorReference.layered.selectedIndex === 0 && Array.from(editorReference.readOverlayPixel(16, 16)).join() === "224,32,64,255", "Failed SVG refresh changed saved selection or pixels");
    });
    await run("remove cancels an image decode immediately", async () => {
      const originalImage = window.Image;
      let delivered;
      const ready = new Promise(resolve => { delivered = resolve; });
      window.Image = function (...args) {
        const image = new originalImage(...args);
        image.addEventListener("load", event => { event.stopImmediatePropagation(); delivered(); });
        return image;
      };
      try {
        const pending = editorReference.loadOverlayImageFromUrl(blue, "cancelled.svg", { layeredState: null });
        await ready;
        editorReference.removeOverlay();
        const result = await Promise.race([pending, new Promise(resolve => setTimeout(() => resolve("timeout"), 1000))]);
        check(result === null && !editorReference.image && !editorReference.source, "Removed reference kept a pending decode or restored itself");
      } finally { window.Image = originalImage; }
    });
    await run("invalid replacement retains existing source", async () => {
      const before = editorReference.image, state = JSON.stringify(editorReference.sourceOverlayProjectState());
      let rejected = false;
      try { await editorReference.loadOverlayImageFromUrl("data:image/png;base64,broken", "broken.png", { layeredState: null }); }
      catch (_) { rejected = true; }
      check(rejected && editorReference.image === before && JSON.stringify(editorReference.sourceOverlayProjectState()) === state, "Invalid replacement damaged the existing source");
    });
    await flushPendingAutosave();
    return results;
  });
  fs.writeFileSync(path.join(output, "reference-workflows.json"), JSON.stringify(results, null, 2));
  if (results.some(result => !result.passed)) throw Error("Reference workflows failed: " + JSON.stringify(results));
  return results;
}
