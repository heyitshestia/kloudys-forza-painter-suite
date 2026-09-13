async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = await h.setup(page, output, options);
  await h.saveAs(page, "Recovery choice checkpoint");
  const original = await h.snapshot(page), checks = [];
  await page.evaluate(async () => {
    await writeAutosavePayload(autosavePayloadFromState(snapshotEditorState()));
  });
  const showFailedAutoRestore = async () => {
    await page.evaluate(async () => {
      const recover = recoverAutosavePayload, harness = isTextVinylHarnessRun;
      try {
        recoverAutosavePayload = async () => false;
        isTextVinylHarnessRun = () => false;
        await maybeShowAutosaveRecovery();
      } finally { recoverAutosavePayload = recover; isTextVinylHarnessRun = harness; }
    });
    await page.locator("#autosaveRecoveryDialog").waitFor({ state: "visible" });
  };
  await showFailedAutoRestore();
  await page.locator("#dismissAutosave").click();
  await page.locator("#autosaveRecoveryDialog").waitFor({ state: "hidden" });
  h.check(await page.evaluate(async () => (await readAutosavePayload())?.shapes?.length === 1748), "Keep Recovery removed the checkpoint");
  h.check(await h.snapshot(page) === original, "Keep Recovery changed the live document");
  checks.push({ name: "keep-recovery-and-live-document" });
  await showFailedAutoRestore();
  await page.locator("#recoverAutosave").click();
  await page.waitForFunction(() => !recoveryRestoreDepth && vinylObjects().length === 1748);
  h.check(await h.snapshot(page) === original, "Manual fallback recovery changed the project");
  checks.push({ name: "manual-recover-button-exact" });
  await showFailedAutoRestore();
  await page.locator("#discardAutosave").click();
  await page.waitForFunction(async () => await readAutosavePayload() === null);
  h.check(await h.snapshot(page) === original, "Discarding the recovery copy changed the live document");
  checks.push({ name: "discard-only-recovery-copy" });
  await page.locator("#saveProject").click();
  await page.waitForFunction(() => !documentDirty);
  return { initial, checks, exactArtwork: true, controlledFault: "Only automatic restore is made to return false, exposing its real fallback dialog; actual buttons and persistence are exercised. No performance conclusion from this fault test." };
}
