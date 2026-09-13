async page => {
  const checks = await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [60, 140, 220, 255], mask: i % 4 === 0,
      data: [i % 60 * 25 - 750, Math.floor(i / 60) * 25 - 625, .1, .1, 0, 0, i % 4 === 0 ? 1 : 0],
    })) });
    const expected = exportValidation();
    window.validationExpected = JSON.stringify(expected);
    scheduleExportValidation();
    if (!exportValidationTimer) throw new Error("Validation was not scheduled off the edit path");
    return { masks: expected.masks, warnings: expected.warnings.length };
  });
  await page.waitForFunction(() => exportValidationTimer === null);
  await page.evaluate(() => {
    const expected = JSON.parse(validationExpected);
    if ($("exportMaskCount").textContent !== String(expected.masks)) throw new Error("Background count differs from authoritative validation");
    if (JSON.stringify([...$("exportIssueList").children].map(row => row.textContent)) !== JSON.stringify(expected.issues.map(issue => issue.message))) throw new Error("Background issues differ from authoritative validation");
    scheduleExportValidation();
    vinylObjects()[0].left = NaN;
    vinylObjects()[0].setCoords();
    const result = refreshExportValidation();
    if (!result.errors.length || !$("exportJson").disabled || exportValidationTimer !== null) throw new Error("Authoritative export did not cancel stale validation or block invalid transforms");
    vinylObjects()[0].left = 0;
    vinylObjects()[0].setCoords();
    scheduleExportValidation();
    scheduleExportValidation([vinylObjects()[0]]);
  });
  await page.waitForFunction(() => exportValidationTimer === null);
  const result = await page.evaluate(async () => {
    if ($("exportMaskCount").textContent !== "1") throw new Error("Superseded validation painted stale counts");
    await clearAutosave(); documentDirty = false;
    return { exactIssues: true, authoritativeExport: true, latestRequestWins: true };
  });
  return { ...checks, ...result };
}
