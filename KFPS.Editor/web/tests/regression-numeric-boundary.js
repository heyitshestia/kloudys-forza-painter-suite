async (page, options = {}) => {
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 300 }, (_, i) => ({ type: 1048677,
      data: [i % 20 * 25, Math.floor(i / 20) * 25, .1, .12, 0, 0, 0], color: [80, 120, 220, 255] })) });
    selectObjects([vinylObjects()[0]], 'numeric boundary'); activateDockPanel('propertiesPane');
  });
  const label = page.locator('[data-numeric-for="rotInput"]');
  await label.scrollIntoViewIfNeeded();
  const rect = await label.boundingBox(), x = rect.x + rect.width / 2, y = rect.y + rect.height / 2;
  const before = await page.evaluate(() => ({ shape: objectToShape(vinylObjects()[0]), index: editorHistory.index }));
  await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.move(x + 30, y, { steps: 6 });
  const previewed = await page.evaluate(before => JSON.stringify(objectToShape(vinylObjects()[0])) !== JSON.stringify(before.shape), before);
  // An external open can begin while a captured pointer has not yet been released.
  await page.evaluate(() => beginDocumentLoad());
  await page.mouse.up();
  const result = await page.evaluate(({ before, previewed }) => ({ previewed,
    restored: JSON.stringify(objectToShape(vinylObjects()[0])) === JSON.stringify(before.shape),
    noStaleCommit: editorHistory.index === before.index,
  }), { before, previewed });
  if (!options.characterize && Object.values(result).some(value => value !== true)) throw Error(JSON.stringify(result));
  return result;
}
