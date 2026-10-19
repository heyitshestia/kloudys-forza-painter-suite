async page => {
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const steps = [];
  page.setDefaultTimeout(15000);
  const menuCommand = async (menu, id) => {
    if (!await page.locator(`#${id}`).isVisible()) await page.locator(`#workspace${menu}Menu`).click();
    await page.locator(`#${id}`).click();
  };
  const tipKeys = ["kloudyFabricProjectSharingAcknowledged", "kloudyFabricLanguageNoticeAcknowledged", "kloudyFabricEditorUpdateAcknowledged"];
  const noExtraTips = async () => check(await page.evaluate(() =>
    ["projectSharingDialog", "languageNoticeDialog", "editorUpdateDialog"].every(id => !document.getElementById(id)?.open)), "An obsolete first-time notice opened");
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  check(await page.locator("#startupHelpDialog").isVisible(), "Fresh profile must retain the initial help/shortcuts popup");
  check(await page.locator("#startupHelpDialog [data-shortcut-label]").count() > 10, "Initial shortcut reference is missing");
  await noExtraTips();
  await page.locator("#startupHelpDontShow").check();
  await page.locator("#startupHelpConfirm").click();
  await page.waitForFunction(() => startupRecoveryHandled && !document.querySelector("dialog[open]"), null, { timeout: 15000 });
  await noExtraTips();
  check(await page.evaluate(() => readStartupHelpConfirmed()), "Initial help acknowledgment was not persisted");
  check((await page.evaluate(keys => keys.map(key => editorSettings.getItem(key)), tipKeys)).every(value => value === null), "Removed tips must not require or manufacture acknowledgment flags");
  steps.push("fresh profile has only the retained initial help; no extra acknowledgment writes");

  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready && startupRecoveryHandled);
  check(await page.locator("#startupHelpDialog").isHidden(), "Acknowledged help returned on reload");
  await noExtraTips();
  steps.push("persisted acknowledgment skips all first-time popups on reload");

  for (const value of ["1", "old-version", null]) {
    await page.evaluate(async ({ keys, value }) => {
      for (const key of keys) value === null ? editorSettings.removeItem(key) : editorSettings.setItem(key, value);
      await KfpsEditorPreferences.flush();
      startupRecoveryHandled = false;
      await continueEditorStartup();
    }, { keys: tipKeys, value });
    await noExtraTips();
  }
  steps.push("old, stale and absent legacy tip flags cannot re-enable startup notices");

  await menuCommand("Help", "helpBtn");
  await page.locator("#helpDialog").waitFor({ state: "visible" });
  await page.locator("#closeHelp").click();
  await menuCommand("Help", "shortcutsBtn");
  await page.locator("#shortcutsDialog").waitFor({ state: "visible" });
  await page.locator("#closeShortcuts").click();
  steps.push("explicit Help and shortcut menus still open");

  await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: 1048677, color: [24, 145, 190, 128], data: [15, 20, .5, .7, 14, .2, 0] }] });
    vinylObjects()[0].left += 12;
    pushHistory("startup-tip confirmation fixture");
  });
  const before = await page.evaluate(() => JSON.stringify(vinylObjects().map(o => objectToShape(o, { includeEditorMeta: true }))));
  await menuCommand("File", "newCanvas");
  await page.locator("#confirmationDialog").waitFor({ state: "visible" });
  check(await page.evaluate(() => documentDirty), "Confirmation fixture must have unsaved work");
  await page.locator("#confirmationDialogCancel").click();
  check(await page.evaluate(() => JSON.stringify(vinylObjects().map(o => objectToShape(o, { includeEditorMeta: true })))) === before, "Cancelling New lost unsaved work");
  await menuCommand("File", "newCanvas");
  await page.locator("#confirmationDialog").waitFor({ state: "visible" });
  await page.locator("#confirmationDialogConfirm").click();
  await page.waitForFunction(() => vinylObjects().length === 0 && !editorCommands.busy);
  await page.evaluate(async () => { await clearAutosave(); await flushPendingAutosave(); });
  await noExtraTips();
  steps.push("unsaved New confirmation retains cancel and explicit destructive acceptance");
  check(!await page.evaluate(() => isDocumentDirty()), "Test must leave a clean document for host close");
  return { passed: true, steps, extraTipsRemoved: 3, ordinaryConfirmationPreserved: true };
}
