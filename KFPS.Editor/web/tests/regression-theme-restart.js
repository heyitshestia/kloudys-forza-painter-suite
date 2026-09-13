async page => {
  await page.waitForFunction(() => document.documentElement.dataset.editorTheme === "custom");
  const state = await page.evaluate(() => ({
    id: editorSettings.getItem("kloudyFabricTheme"),
    base: document.documentElement.dataset.editorThemeBase,
    accent: editorTheme.themeFieldCurrentValues()["--accent"],
    matte: getComputedStyle(document.body).backgroundImage === "none",
  }));
  if (state.id !== "matte-restart-proof" || state.base !== "blackout" || state.accent !== "#a9c4ba" || !state.matte) throw new Error(`Custom theme lost on restart: ${JSON.stringify(state)}`);
  return { ...state, fullProcessRestart: true };
}
