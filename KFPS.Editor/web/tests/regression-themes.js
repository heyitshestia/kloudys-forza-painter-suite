async (page,options={}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  page.setDefaultTimeout(20000);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const measures = [];
  await page.evaluate(async () => {
    KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
    await KfpsEditorPreferences.flush();
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
  });
  const initial=options.layers ? await h.setup(page,output,options) : null;
  if(!initial)await page.evaluate(async()=> {
    await loadPayload({ shapes: Array.from({ length: 24 }, (_, i) => ({ type: 1048677 + i % 8, color: [80 + i * 5, 110, 160, 255], data: [(i % 6) * 120 - 300, Math.floor(i / 6) * 120 - 180, .7, .7, i * 9, 0, 0] })) });
  });
  for (const theme of ["blackout", "whiteout"]) {
    await page.locator("#editorThemeSelect").selectOption(theme);
    const contrast = await page.evaluate(() => {
      const values = editorTheme.themeFieldCurrentValues();
      const luminance = color => {
        const channels = color.slice(1).match(/../g).map(value => parseInt(value, 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
        return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
      };
      const ratio = (a, b) => { a = luminance(values[a]); b = luminance(values[b]); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); };
      const surfaces = ["--shell", "--panel", "--panel2", "--panel3", "--dialog-bg", "--dialog-header"];
      return {
        text: Math.min(...["--text", "--muted", "--soft", "--accent", "--good", "--warn", "--danger"].flatMap(foreground => surfaces.map(background => ratio(foreground, background)))),
        controls: Math.min(...surfaces.map(background => ratio("--line", background))),
        matte: getComputedStyle(document.body).backgroundImage === "none",
      };
    });
    check(contrast.text >= 4.5 && contrast.controls >= 3 && contrast.matte, `${theme} contrast or matte surfaces failed: ${JSON.stringify(contrast)}`);
    measures.push({ theme, ...contrast });
    await page.screenshot({ path: `${theme}-editor.png` });
    await page.locator("#adjustTheme").click();
    check(await page.locator(".themeValueInput:visible").count() === 6, "Default theme editor must expose only six main colors");
    await page.screenshot({ path: `${theme}-adjust.png` });
    const original = await page.locator('[data-theme-var="--text"]').inputValue();
    await page.locator('[data-theme-var="--text"]').fill("invalid-color");
    check(await page.locator("#saveThemeAdjust").isDisabled(), "Invalid colors must not save");
    await page.locator('[data-theme-var="--text"]').fill(theme === "blackout" ? "#191919" : "#fafafa");
    check((await page.locator("#themeAdjustStatus").innerText()).startsWith("Low text contrast"), "Low contrast must be visible before saving");
    await page.locator("#resetThemeAdjust").click();
    check(await page.locator('[data-theme-var="--text"]').inputValue() === original, "Reset must restore starting colors");
    await page.locator(".themeAdvanced summary").click();
    check(await page.locator(".themeValueInput:visible").count() === 33, "Advanced colors must remain available");
    await page.locator("#themeAdjustBase").selectOption(theme === "blackout" ? "whiteout" : "blackout");
    check(await page.evaluate(theme => editorSettings.getItem("kloudyFabricTheme") === theme, theme), "Preview changed persisted theme selection");
    await page.locator("#themeAdjustName").press("Escape");
    check(await page.evaluate(theme => document.documentElement.dataset.editorTheme === theme, theme), "Cancel did not restore original theme");
  }
  await page.locator("#adjustTheme").click();
  await page.locator("#themeAdjustBase").selectOption("blackout");
  await page.locator("#themeAdjustName").fill("Matte restart proof");
  await page.locator('[data-theme-var="--accent"]').fill("#a9c4ba");
  await page.locator("#themeAdjustName").press("Enter");
  await page.locator("#themeAdjustDialog").waitFor({ state: "hidden" });
  await page.locator('#saveProjectAs').click();await h.type(page,'#textPromptInput','Theme dense persistence');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready && document.documentElement.dataset.editorTheme === "custom");
  const restored = await page.evaluate(() => ({ base: document.documentElement.dataset.editorThemeBase, accent: editorTheme.themeFieldCurrentValues()["--accent"], matte: getComputedStyle(document.body).backgroundImage === "none" }));
  check(restored.base === "blackout" && restored.accent === "#a9c4ba" && restored.matte, "Custom theme did not retain its base and colors on reload");
  for (const size of [{ width: 1440, height: 900 }, { width: 900, height: 640 }, { width: 360, height: 640 }]) {
    await page.setViewportSize(size);
    await page.locator("#adjustTheme").click();
    const fits = await page.evaluate(() => {
      const dialog = document.getElementById("themeAdjustDialog"), rect = dialog.getBoundingClientRect();
      return rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight && dialog.scrollWidth <= dialog.clientWidth + 1;
    });
    check(fits, `Theme editor overflows ${size.width}x${size.height}`);
    await page.screenshot({ path: `theme-adjust-${size.width}.png` });
    await page.locator("#closeThemeAdjust").click();
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  if(initial)check(await page.evaluate(()=>vinylObjects().length)===initial.layers,'Theme reload lost dense artwork');
  return { initial,contrast: measures, basicColors: 6, advancedColors: 33, previewCancel: true, validation: true, reset: true, customReload: restored, responsiveWidths: [1440, 900, 360] };
}
