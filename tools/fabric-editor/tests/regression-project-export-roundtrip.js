async (page) => {
  page.setDefaultTimeout(300000);
  return page.evaluate(async () => {
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();

    const shapes = Array.from({ length: 128 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [40 + index % 180, 80 + index % 140, 120 + index % 120, 120 + index % 136],
      data: [
        -700 + (index % 16) * 90,
        420 - Math.floor(index / 16) * 120,
        (index % 7 === 0 ? -1 : 1) * (0.18 + (index % 5) * 0.03),
        (index % 11 === 0 ? -1 : 1) * (0.2 + (index % 4) * 0.04),
        (index * 17) % 360,
        ((index % 9) - 4) * 0.025,
        index === 63 ? 1 : 0,
      ],
      mask: index === 63,
      score: index / 1000,
      source_format: "fh6_typecode",
      shape_name: `Compatibility ${index + 1}`,
      editor_id: `compat-${String(index + 1).padStart(3, "0")}`,
      editor_hidden: index === 5,
      editor_locked: index === 6,
      editor_group_id: index < 12 ? "compat-group" : null,
      editor_group_name: index < 12 ? "Compatibility Group" : null,
    }));
    const guideStateFixture = {
      version: 1,
      gridEnabled: true,
      gridSize: 37,
      gridOpacity: 31,
      guidesVisible: true,
      snapGuides: true,
      snapGrid: false,
      snapCtrlOnly: true,
      snapThreshold: 14,
      guideConstraint: "free",
      snapGuideAnchor: false,
      snapGuideEnd: true,
      guides: [{
        id: "compat-guide",
        x1: -500,
        y1: -250,
        x2: 500,
        y2: 250,
        constraint: "free",
      }],
    };
    const project = {
      format: "kloudy_fabric_editor_project_v1",
      name: "Compatibility Roundtrip",
      shapes,
      editor_guides: guideStateFixture,
      editor_collapsed_groups: ["compat-group"],
    };

    const projectFile = new File(
      [JSON.stringify(project)],
      "Compatibility Roundtrip.fabric-project.json",
      { type: "application/json" },
    );
    await loadProjectFile(projectFile);

    const loaded = vinylObjects();
    const loadedProjectShapes = loaded.map((object) => objectToShape(object, { includeEditorMeta: true }));
    const savedProject = JSON.parse(JSON.stringify({
      format: "kloudy_fabric_editor_project_v1",
      name: currentProjectName,
      shapes: loadedProjectShapes,
      editor_guides: savedGuideState(),
      editor_collapsed_groups: collapsedLayerGroupIds(),
    }));
    await loadProjectPayload(savedProject, "Compatibility Roundtrip");

    const reloaded = vinylObjects();
    const exported = JSON.parse(JSON.stringify({
      shapes: reloaded.map((object) => objectToShape(object, { includeEditorMeta: false })),
    }));
    const forbiddenEditorKeys = exported.shapes.flatMap((shape) => (
      Object.keys(shape).filter((key) => key.startsWith("editor_"))
    ));
    const exportedBeforeReload = JSON.stringify(exported.shapes);
    await loadPayload(exported);
    const exportedAfterReload = JSON.stringify(
      vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: false })),
    );

    const result = {
      projectFormat: savedProject.format,
      projectLayers: loadedProjectShapes.length,
      stableEditorIds: loadedProjectShapes.every((shape, index) => shape.editor_id === shapes[index].editor_id),
      hiddenLayers: loadedProjectShapes.filter((shape) => shape.editor_hidden).length,
      lockedLayers: loadedProjectShapes.filter((shape) => shape.editor_locked).length,
      groupedLayers: loadedProjectShapes.filter((shape) => shape.editor_group_id === "compat-group").length,
      collapsedGroups: savedProject.editor_collapsed_groups,
      guides: savedProject.editor_guides.guides.length,
      gridSize: savedProject.editor_guides.gridSize,
      masks: exported.shapes.filter((shape) => shape.mask || Number(shape.data?.[6]) !== 0).length,
      exportLayers: exported.shapes.length,
      forbiddenEditorKeys,
      exportRoundtripExact: exportedBeforeReload === exportedAfterReload,
    };

    if (result.projectFormat !== "kloudy_fabric_editor_project_v1" || result.projectLayers !== 128) {
      throw new Error("Project file format or layer count changed during serialization.");
    }
    if (!result.stableEditorIds || result.hiddenLayers !== 1 || result.lockedLayers !== 1 || result.groupedLayers !== 12) {
      throw new Error("Project-only layer metadata did not survive file reload.");
    }
    if (result.collapsedGroups.length !== 1 || result.collapsedGroups[0] !== "compat-group") {
      throw new Error("Collapsed project groups did not survive file reload.");
    }
    if (result.guides !== 1 || result.gridSize !== 37) throw new Error("Project guide settings did not survive file reload.");
    if (result.masks !== 1 || result.exportLayers !== 128) throw new Error("FH6 export lost a mask or vinyl layer.");
    if (result.forbiddenEditorKeys.length) throw new Error("FH6 export leaked project-only editor metadata.");
    if (!result.exportRoundtripExact) throw new Error("FH6 export changed after an export-import-export roundtrip.");
    return result;
  });
}
