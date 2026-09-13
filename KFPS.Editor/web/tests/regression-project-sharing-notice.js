async (page, screenshotDirectory) => {
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const key = "kloudyFabricProjectSharingAcknowledged";
  const dialog = page.locator("#projectSharingDialog");
  const checkbox = page.locator("#projectSharingAcknowledge");
  const button = page.locator("#projectSharingContinue");
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  check(await page.locator("#startupHelpDialog").isVisible(), "Fresh installation must show the introduction first");
  check(!await dialog.isVisible(), "Sharing notice must not cover the introduction");
  await page.locator("#startupHelpDontShow").check();
  await page.locator("#startupHelpConfirm").click();
  await dialog.waitFor({ state: "visible" });
  check(!await checkbox.isChecked(), "Acknowledgment must start unchecked");
  check(await button.isDisabled(), "Continue must require acknowledgment");
  await page.evaluate(() => confirmProjectSharingNotice());
  check(await page.evaluate(key => KfpsEditorPreferences.getItem(key), key) === null, "Unchecked confirmation must not persist");
  await page.keyboard.press("Escape");
  check(await dialog.isVisible(), "Escape must not dismiss the notice");
  await checkbox.check();
  check(await button.isEnabled(), "Acknowledgment must enable Continue");
  await checkbox.uncheck();
  check(await button.isDisabled(), "Removing acknowledgment must disable Continue");

  const sizes = [await page.evaluate(() => ({ width: innerWidth, height: innerHeight })), { width: 900, height: 640 }, { width: 360, height: 640 }];
  for (const size of sizes) {
    await page.setViewportSize(size);
    await button.scrollIntoViewIfNeeded();
    const fits = await page.evaluate(() => {
      const dialog = document.getElementById("projectSharingDialog");
      const button = document.getElementById("projectSharingContinue").getBoundingClientRect();
      const bounds = dialog.getBoundingClientRect();
      return bounds.left >= 0 && bounds.right <= innerWidth && bounds.top >= 0
        && bounds.bottom <= innerHeight && dialog.scrollWidth <= dialog.clientWidth
        && button.top >= bounds.top && button.bottom <= bounds.bottom;
    });
    check(fits, `Notice or Continue overflows ${size.width}x${size.height}`);
    const prefix = typeof screenshotDirectory === "string" ? `${screenshotDirectory}/` : "";
    await page.screenshot({ path: `${prefix}popup-${size.width}x${size.height}.png` });
  }
  await page.setViewportSize(sizes[0]);

  await page.route("**/api/fabric-editor/preferences", route => route.request().method() === "POST" ? route.abort("failed") : route.continue());
  await checkbox.check();
  await button.click();
  await page.locator("#projectSharingError").waitFor({ state: "visible" });
  check(await dialog.isVisible(), "Failed save must leave the notice open");
  check(await button.isEnabled(), "Failed save must permit retry");
  const failed = await page.evaluate(key => ({ memory: KfpsEditorPreferences.getItem(key), browser: localStorage.getItem(key) }), key);
  check(failed.memory === null && failed.browser === null, "Failed acknowledgment must not survive in browser storage");
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await dialog.waitFor({ state: "visible" });
  check(!await page.locator("#startupHelpDialog").isVisible(), "Previously acknowledged introduction must stay dismissed");
  check(await button.isDisabled(), "Failed-save restart must request a new acknowledgment");
  await page.unroute("**/api/fabric-editor/preferences");
  await checkbox.check();
  await button.click();
  await dialog.waitFor({ state: "hidden" });
  const stored = await page.evaluate(async () => (await (await fetch("/api/fabric-editor/preferences")).json()).settings);
  check(stored[key] === "1", "Acknowledgment must reach the real settings API");
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  check(!await dialog.isVisible(), "Saved acknowledgment must survive a page reload");
  return { introductionOrder: true, requiredCheckbox: true, escapeBlocked: true, responsiveSizes: sizes, failedWriteRollback: true, retry: true, reload: true };
}
