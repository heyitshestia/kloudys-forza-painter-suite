async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [120, 160 + index % 80, 220, 255],
      data: [(index % 60) * 22, -Math.floor(index / 60) * 22, 0.18, 0.18, 0, 0, 0],
      editor_group_id: index >= 1200 && index < 1250 ? "virtual-group" : null,
      editor_group_name: index >= 1200 && index < 1250 ? "Virtual Group" : null,
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();
    await loadPayload({ shapes });
    activateDockPanel("layersPane");
    const viewport = document.getElementById("layersViewport");
    const list = document.getElementById("layers");
    const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
    const scrollStart = performance.now();
    for (let index = 0; index <= 120; index += 1) {
      viewport.scrollTop = (viewport.scrollHeight - viewport.clientHeight) * (index / 120);
      viewport.dispatchEvent(new Event("scroll"));
      await frame();
    }
    const scrollMs = performance.now() - scrollStart;
    const rowsAtBottom = list.querySelectorAll(":scope > li").length;
    const bottomText = list.textContent;
    const search = document.getElementById("layerSearch");
    search.value = "1500.";
    refreshLayers();
    const filteredEntries = layerListEntries.length;
    const filteredRows = list.querySelectorAll(":scope > li").length;
    const filteredText = list.textContent;
    search.value = "";
    refreshLayers();
    const groupEntry = layerListRows.get("group:virtual-group");
    setCollapsedGroup("virtual-group", true);
    const collapsedEntries = layerListEntries.length;
    setCollapsedGroup("virtual-group", false);
    const expandedEntries = layerListEntries.length;
    return {
      layers: vinylObjects().length,
      scrollMs,
      averageScrollFrameMs: scrollMs / 121,
      rowsAtBottom,
      bottomReached: bottomText.includes("1. "),
      filteredEntries,
      filteredRows,
      filteredMatch: filteredText.includes("1500."),
      groupMembers: groupEntry?.objects.length || 0,
      collapsedEntryDelta: expandedEntries - collapsedEntries,
      maxMountedDescendants: list.querySelectorAll("*").length,
    };
  });
}
