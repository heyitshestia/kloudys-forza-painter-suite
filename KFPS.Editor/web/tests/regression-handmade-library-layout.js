async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = await h.setupDerived(page, output, { ...options, layers: 2400 });
  await h.saveAs(page, "Library layout checkpoint");
  const original = await h.snapshot(page), checks = [];
  for (const language of ["en", "ko"]) {
    if (await page.evaluate(() => KfpsI18n.language) !== language) {
      await page.locator("#editorLanguageSelect").selectOption(language);
      await page.locator("#messageDialog").waitFor({ state: "visible" });
      await page.locator("#messageDialogClose").click();
      await page.reload();
      await page.waitForFunction(language => KfpsI18n.language === language && vinylObjects().length === 2400 && !recoveryRestoreDepth, language);
    }
    for (const size of [{ width: 1000, height: 720 }, { width: 1600, height: 1000 }]) {
      await page.setViewportSize(size);
      await page.locator('[data-tool-mode="shapeLibrary"]').click();
      await page.locator("#shapeSearch").fill("1");
      await page.waitForFunction(() => document.getElementById("shapeGrid").getAttribute("aria-busy") === "false");
      const tile = page.locator("#shapeGrid .shapeTile").last();
      await tile.focus();
      await page.keyboard.press("Tab");
      h.check(await tile.locator(".favButton").evaluate(button => button === document.activeElement), "Keyboard could not reach the offscreen favorite");
      await page.keyboard.press("Shift+Tab");
      h.check(await tile.evaluate(tile => tile === document.activeElement), "Keyboard could not return to the shape tile");
      await page.waitForFunction(() => {
        const image = document.querySelector("#shapeGrid .shapeTile:last-child img");
        return image?.complete && image.naturalWidth > 0;
      });
      const geometry = await tile.evaluate(tile => {
        const box = tile.getBoundingClientRect(), image = tile.querySelector("img").getBoundingClientRect();
        return { height: box.height, width: box.width, visible: box.top >= 0 && box.bottom <= innerHeight,
          image: { width: image.width, height: image.height },
          labelsFit: [...tile.querySelectorAll("span")].every(span => {
            const rect = span.getBoundingClientRect(); return rect.left >= box.left && rect.right <= box.right && rect.bottom <= box.bottom;
          }) };
      });
      h.check(geometry.height === 136 && geometry.visible && geometry.labelsFit && geometry.image.width === 48 && geometry.image.height === 48, "Shape tile content is clipped or invisible after keyboard scroll");
      checks.push({ language, viewport: size, geometry });
      await page.screenshot({ path: path.join(output, `library-layout-${language}-${size.width}.png`) });
      h.check(await h.snapshot(page) === original, "Library layout or keyboard navigation changed artwork");
    }
  }
  return { initial, checks, exactArtwork: true, viewportsAreEmulatedNotPhysicalDpi: true };
}
