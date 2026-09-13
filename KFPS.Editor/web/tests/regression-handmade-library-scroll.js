async (page, options = {}) => {
  page.setDefaultTimeout(30000);
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = await h.setupDerived(page, output, { ...options, layers: options.layers || 2400 });
  const original = await h.snapshot(page);
  const ready = () => page.waitForFunction(() => document.getElementById("shapeGrid").getAttribute("aria-busy") === "false");
  const scrollState = () => page.evaluate(() => {
    const grid = document.getElementById("shapeGrid");
    let viewport = grid.parentElement;
    while (viewport && !(viewport.scrollHeight > viewport.clientHeight + 10
      && /auto|scroll/.test(getComputedStyle(viewport).overflowY))) viewport = viewport.parentElement;
    if (!viewport) throw Error("Scrollable shape library not found");
    const rect = viewport.getBoundingClientRect(), last = grid.lastElementChild, tile = last.getBoundingClientRect();
    return { top: viewport.scrollTop, height: viewport.clientHeight, total: viewport.scrollHeight,
      x: rect.left + rect.width / 2, y: rect.top + rect.height * .7,
      lastVisible: tile.top >= rect.top && tile.bottom <= rect.bottom,
      key: last.dataset.resourceKey };
  });
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await h.type(page, "#shapeSearch", "1"); await ready();
  let before = await scrollState();
  for (let step = 0; step < 40 && !before.lastVisible; step++) {
    await page.mouse.move(before.x, before.y); await page.mouse.wheel(0, 4000);
    await page.waitForTimeout(50); before = await scrollState();
  }
  h.check(before.lastVisible && before.top > 1000, "Did not reach a deeply scrolled library item using wheel input");
  const key = before.key, rows = [];
  if (options.sweeps) {
    const trace = await h.monitor(page, output);
    try {
      for (let sweep = 0; sweep < options.sweeps; sweep++) {
        for (const direction of [-1, 1]) {
          await trace.run(`library-sweep-${sweep}-${direction}`, async () => {
            for (let step = 0; step < 40; step++) {
              const current = await scrollState();
              if (direction < 0 ? current.top <= 1 : current.lastVisible) break;
              await page.mouse.move(current.x, current.y);
              await page.mouse.wheel(0, 4000 * direction);
              await page.waitForTimeout([150, 80, 35, 10][sweep % 4]);
            }
            const current = await scrollState();
            h.check(direction < 0 ? current.top <= 1 : current.lastVisible, "Repeated wheel sweep did not reach its endpoint");
          });
        }
      }
      fs.writeFileSync(path.join(output, "library-sweep-timings.json"), JSON.stringify(trace.rows, null, 2));
    } finally { await trace.close(); }
    before = await scrollState();
  }
  await page.waitForFunction(key => {
    const tile = [...document.querySelectorAll("#shapeGrid .shapeTile")].find(tile => tile.dataset.resourceKey === key);
    const image = tile?.querySelector("img");
    return image?.complete && image.naturalWidth > 0;
  }, key);
  const tileGeometry = await page.locator(`#shapeGrid [data-resource-key="${key}"]`).evaluate(tile => {
    const box = tile.getBoundingClientRect();
    return { height: box.height, labelsFit: [...tile.querySelectorAll("span")].every(span => {
      const rect = span.getBoundingClientRect(); return rect.left >= box.left && rect.right <= box.right && rect.bottom <= box.bottom;
    }) };
  });
  h.check(tileGeometry.height === 136 && tileGeometry.labelsFit, "Library tile labels escape their stable bounds");
  await page.screenshot({ path: path.join(output, "library-deep-results.png") });
  const button = () => page.locator(`#shapeGrid [data-resource-key="${key}"] .favButton`);
  for (let turn = 0; turn < 2; turn++) {
    await button().click(); await ready(); await page.waitForTimeout(100);
    const after = await scrollState();
    rows.push({ turn, before, after, stayed: Math.abs(after.top - before.top) <= 1 });
    fs.writeFileSync(path.join(output, "library-scroll.json"), JSON.stringify({ initial, rows }, null, 2));
    h.check(rows.at(-1).stayed, "Favoriting a lower library item reset its scroll position");
    before = after;
  }
  await button().click(); await ready();
  await page.locator("#showFavorites").click(); await ready();
  h.check(await button().count() === 1, "Favorite missing from favorites-only view");
  await button().click(); await ready();
  h.check(await button().count() === 0, "Removed favorite remained in favorites-only view");
  await page.locator("#showAllShapes").click(); await ready();
  h.check(await h.snapshot(page) === original, "Library scrolling or favorites changed artwork");
  await page.screenshot({ path: path.join(output, "library-scroll-final.png") });
  return { initial, rows, tileGeometry, sweeps: options.sweeps || 0, favoritesOnlyRemoval: true, exactArtwork: true };
}
