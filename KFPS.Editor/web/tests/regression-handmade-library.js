async (page, options = {}) => {
  page.setDefaultTimeout(30000);
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = await h.setupDerived(page, output, { ...options, layers: options.layers || 2400 });
  const original = await h.snapshot(page), checks = [];
  const trace = await h.monitor(page, output);
  const ready = () => page.waitForFunction(() => document.getElementById("shapeGrid").getAttribute("aria-busy") === "false");
  const exactResults = async () => {
    await ready();
    const result = await page.evaluate(() => {
      const query = document.getElementById("shapeSearch").value.trim().toLowerCase();
      const families = query || showFavoritesOnly ? FAMILY_ORDER : [document.getElementById("shapeFamily").value];
      const expected = [];
      for (const family of families) for (let index = 1; index <= editorCatalog.shapeCountForFamily(family); index++) {
        const key = `${family}:${index}`;
        if (showFavoritesOnly && !favorites.has(key)) continue;
        if (query && !shapeSearchText(family, index, editorCatalog.resourceToTypeCode(family, index)).includes(query)) continue;
        expected.push(key);
      }
      return { expected, actual: [...document.querySelectorAll("#shapeGrid .shapeTile")].map(tile => tile.dataset.resourceKey) };
    });
    h.check(JSON.stringify(result.actual) === JSON.stringify(result.expected), "Library contains missing, duplicate or stale results");
    return result.actual.length;
  };
  try {
    await page.locator('[data-tool-mode="shapeLibrary"]').click();
    await page.locator("#shapeFamily").selectOption("Primitives");
    await trace.run("typed-full-type", async () => { await h.type(page, "#shapeSearch", "1048677"); await ready(); });
    h.check(await exactResults() === 1, "Exact type search was not unique");
    await trace.run("broad-prefix", async () => { await h.type(page, "#shapeSearch", "1"); await ready(); });
    const broadCount = await exactResults();
    h.check(broadCount > 400, "Broad query did not exercise a substantial catalog");
    const tile = page.locator("#shapeGrid .shapeTile").first();
    await page.waitForFunction(() => { const img = document.querySelector("#shapeGrid .shapeTile img"); return img?.complete && img.naturalWidth > 0; });
    h.check(await page.locator("#shapeGrid img").evaluateAll(images => images.every(img => img.loading === "lazy" && img.decoding === "async")), "Thumbnails did not use deferred decoding");
    checks.push({ name: "complete-broad-catalog-and-visible-thumbnail", count: broadCount });
    await trace.run("cancel-replace-query-and-family", async () => {
      for (const query of ["Primitives", "1", "1048", "Crescent", "1", ""]) await page.locator("#shapeSearch").fill(query);
      await page.locator("#shapeFamily").selectOption("Gradient_Shapes");
      await ready();
    });
    await exactResults();
    await h.type(page, "#shapeSearch", "1048677"); await exactResults();
    const key = await tile.getAttribute("data-resource-key");
    const beforeFavorite = await page.evaluate(key => favorites.has(key), key);
    await tile.locator(".favButton").focus();
    for (let count = 1; count <= 4; count++) {
      await page.keyboard.press("Space"); await ready();
      h.check(await page.evaluate(({ key, expected }) => favorites.has(key) === expected
        && document.activeElement?.classList.contains("favButton")
        && document.activeElement.closest(".shapeTile").dataset.resourceKey === key,
      { key, expected: count % 2 ? !beforeFavorite : beforeFavorite }), "Favorite refresh lost keyboard focus or changed the wrong item");
    }
    h.check(await h.snapshot(page) === original, "Favorite keyboard presses inserted artwork");
    checks.push({ name: "four-favorite-toggles-without-refocusing" });
    await page.locator("#shapeSearch").fill("");
    await ready();
    await page.evaluate(() => {
      const original = createShapeLibraryTile;
      createShapeLibraryTile = (...args) => { createShapeLibraryTile = original; throw new Error("Injected shape-grid failure"); };
    });
    await page.locator("#shapeFamily").selectOption("Primitives");
    await page.locator("#messageDialog").waitFor({ state: "visible" });
    h.check(await page.locator("#messageDialogTitle").textContent() === "Shape library refresh failed", "Library failure lacked the expected visible message");
    await ready();
    await page.locator("#messageDialogClose").click();
    await page.locator("#shapeFamily").selectOption("Gradient_Shapes");
    await exactResults();
    checks.push({ name: "injected-render-failure-and-real-control-retry", injected: true });
    h.check(await h.snapshot(page) === original, "Library workflows changed existing artwork");
    await page.screenshot({ path: path.join(output, "library-final.png") });
    return { initial, checks, rows: trace.rows, exactArtwork: true };
  } finally { await trace.close(); }
}
