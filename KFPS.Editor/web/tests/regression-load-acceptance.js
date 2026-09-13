async page => {
  return page.evaluate(async () => {
    const failures = [], checks = [];
    const check = (name, ok) => { checks.push({ name, passed: Boolean(ok) }); if (!ok) failures.push(name); };
    const shapes = Array.from({ length: 2400 }, (_, index) => ({ type: 1048677,
      color: [40, 150, 210, 255], data: [(index % 60) * 8, Math.floor(index / 60) * 8, .05, .05, 0, 0, 0] }));
    await loadPayload({ shapes }, { name: "Acceptance A", projectName: "Acceptance A" });
    await saveProject();
    const receipt = editorProjects.association, state = currentHistoryState();
    try { await loadProjectPayload({ invalid: true }, "Invalid B"); } catch (_) {}
    check("failed open retains A scene/history", currentHistoryState() === state && vinylObjects().length === 2400);
    check("failed open retains A receipt", editorProjects.expected("Acceptance A")?.fingerprint === receipt?.fingerprint);
    vinylObjects()[0].left += 5; pushHistory("edit after failed open");
    await saveProject();
    check("normal Save after failed open", !documentDirty && editorProjects.association?.fingerprint !== receipt?.fingerprint);
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    for (const [site, get, set] of [
      ["refreshLayers", () => refreshLayers, value => { refreshLayers = value; }],
      ["renderHistoryList", () => renderHistoryList, value => { renderHistoryList = value; }],
      ["fitDesignView", () => fitDesignView, value => { fitDesignView = value; }],
    ]) {
      const original = get();
      set(() => { throw Error(`Injected ${site} presentation failure`); });
      let accepted = false;
      try { accepted = await loadProjectPayload({ shapes, name: `Acceptance ${site}` }, site); }
      catch (_) {}
      finally { set(original); }
      check(`${site} coherent accepted baseline`, accepted && currentHistoryState()?.shapes.length === 2400
        && currentProjectName === `Acceptance ${site}`);
      document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    }
    const generated = await makeFabricObject({ ...shapes[0], editor_pixel_art_generated: true });
    check("generated provenance restored", generated.kloudy.pixel_art_generated === true);
    generated.kloudy.pixel_art_generated = true;
    check("generated provenance serialized", objectToShape(generated).editor_pixel_art_generated === true);
    check("flat export excludes provenance", !("editor_pixel_art_generated" in objectToShape(generated, { includeEditorMeta: false })));
    discardFabricObject(generated);
    await clearAutosave(); documentDirty = false;
    return { passed: failures.length === 0, failures, checks };
  });
}
