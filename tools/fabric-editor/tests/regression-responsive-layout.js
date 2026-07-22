async (page) => {
  page.setDefaultTimeout(180000);
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [60 + index % 180, 130, 220, 255],
      data: [-850 + (index % 60) * 28, 620 - Math.floor(index / 60) * 25, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
  });

  const results = [];
  for (const theme of ["pastel", "dark"]) {
    await page.evaluate((nextTheme) => applyEditorTheme(nextTheme, { persist: false }), theme);
    for (const viewport of [
      { width: 1280, height: 720 },
      { width: 1600, height: 900 },
      { width: 1920, height: 1080 },
    ]) {
      await page.setViewportSize(viewport);
      const result = await page.evaluate(() => {
        const tolerance = 1;
        const groups = [...document.querySelectorAll(".menuGroup")];
        const menuRect = document.querySelector(".appMenus").getBoundingClientRect();
        const controlsContained = groups.every((group) => {
          const parent = group.getBoundingClientRect();
          return [...group.children].filter((child) => child.getClientRects().length).every((child) => {
            const rect = child.getBoundingClientRect();
            return rect.left >= parent.left - tolerance && rect.right <= parent.right + tolerance;
          });
        });
        const groupRects = groups.map((group) => group.getBoundingClientRect());
        const groupsSeparated = groupRects.every((rect, index) => (
          index === 0 || rect.left >= groupRects[index - 1].right - tolerance
        ));
        return {
          theme: document.documentElement.dataset.editorTheme,
          viewport: { width: innerWidth, height: innerHeight },
          documentFits: document.documentElement.scrollWidth <= innerWidth,
          controlsContained,
          groupsSeparated,
          groupsStartInsideMenu: !groupRects.length || groupRects[0].left >= menuRect.left - tolerance,
          mountedLayerRows: document.querySelectorAll("#layers > li").length,
          layerCount: vinylObjects().length,
        };
      });
      if (!result.documentFits || !result.controlsContained || !result.groupsSeparated || !result.groupsStartInsideMenu) {
        throw new Error(`Responsive layout overlap at ${theme} ${viewport.width}x${viewport.height}.`);
      }
      if (result.layerCount !== 3000 || result.mountedLayerRows > 30) {
        throw new Error("Responsive layout test lost layer virtualization.");
      }
      results.push(result);
    }
  }
  return results;
}
