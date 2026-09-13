async (page, options = {}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const count=Number(options.layers || 2);
  page.setDefaultTimeout(15000);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const prompt = page.locator("#textPromptDialog");
  const input = page.locator("#textPromptInput");
  const writes = [];
  const capture = request => {
    if (request.method() === "POST" && request.url().includes("/api/fabric-editor/save-project")) writes.push(request.url());
  };
  page.on("request", capture);
  const idle = () => page.waitForFunction(() => !projectSaveInProgress && !exportSaveInProgress);
  const enterName = async (button, name, key = "Enter") => {
    await page.locator(button).click();
    await h.type(page,'#textPromptInput',name);
    await input.press(key);
    await prompt.waitFor({ state: "hidden" });
    await idle();
  };
  const project = name => page.evaluate(async name => {
    const listing = await (await fetch(PROJECT_BROWSER_API)).json();
    const entry = listing.entries.find(item => item.title === name);
    if (!entry) return null;
    return (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
  }, name);
  await page.evaluate(async () => {
    KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
    await KfpsEditorPreferences.flush();
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
  });
  const initial=count>=2000 ? await h.setup(page,output,options) : null;
  if(!initial)await page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1].map(index => ({
      type: 1048677, color: [40, 150, 210, 255], data: [index * 100, 20, 0.5, 0.5, 0, 0, 0],
    })) });
  });

  await page.locator("#saveProjectAs").click();
  await input.fill("Enter Save As");
  await input.press("Enter");
  await prompt.waitFor({ state: "hidden" });
  await page.waitForFunction(() => !projectSaveInProgress);
  const state = await page.evaluate(() => ({ name: currentProjectName, dirty: documentDirty, status: document.getElementById("status").textContent }));
  check(state.name === "Enter Save As" && !state.dirty, `Save As + Enter did not save: ${JSON.stringify(state)}`);
  const saved = await page.evaluate(async () => {
    const listing = await (await fetch(PROJECT_BROWSER_API)).json();
    const entry = listing.entries.find(item => item.title === "Enter Save As");
    if (!entry) throw new Error("Saved project is absent from the real project folder");
    return (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
  });
  check(saved.shapes.length === count, "Saved project must contain every layer");

  await page.locator("#newCanvas").click();
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.locator("#loadProject").click();
  await page.locator(".projectBrowserEntry").filter({ has: page.getByText("Enter Save As", { exact: true }) }).click();
  await page.locator("#selectProjectEntry").click();
  await page.locator("#projectBrowserDialog").waitFor({ state: "hidden" });
  check(await page.evaluate(count => currentProjectName === "Enter Save As" && vinylObjects().length === count && !documentDirty,count), "Enter-saved project must reopen through Open Project");

  if(initial)await h.select(page,'Human target');
  else await page.evaluate(() => { canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); });
  const layerName = "\ud14c\uc2a4\ud2b8 Layer";
  await enterName("#renameSelectedLayer", layerName);
  check(await page.evaluate(name => selectedVinylObjects()[0].kloudy.name === name, layerName), "Layer rename must apply Enter and preserve Unicode");
  await page.locator('#selectAllLayers').click();
  await page.locator("#groupSelected").click();
  await enterName("#renameSelectedGroup", "Enter Group");
  check(await page.evaluate(() => vinylObjects().every(object => object.kloudy.group_name === "Enter Group")), "Group rename must apply Enter to every member");
  await page.locator("#saveProject").click();
  await idle();
  const grouped = await project("Enter Save As");
  check(grouped.shapes.every(shape => shape.editor_group_name === "Enter Group"), "Normal Save must persist Enter-renamed groups");
  check(grouped.shapes.some(shape => shape.shape_name === layerName), "Normal Save must persist Enter-renamed layer names");

  await enterName("#saveProjectAs", "Numpad Copy", "NumpadEnter");
  check(Boolean(await project("Numpad Copy")), "Numpad Enter must save too");
  await enterName("#saveProjectAs", "Enter Save As");
  await page.locator("#messageDialog").waitFor({ state: "visible" });
  check((await page.locator("#messageDialogTitle").innerText()).includes("already used"), "An existing name must remain protected");
  check(JSON.stringify(await project("Enter Save As")) === JSON.stringify(grouped), "Duplicate names must not overwrite the first project");
  await page.locator("#messageDialogClose").click();

  await page.route("**/api/fabric-editor/save-project", route => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Simulated disk failure" }) }));
  await enterName("#saveProjectAs", "Retried Project");
  await page.locator("#messageDialog").waitFor({ state: "visible" });
  check(await project("Retried Project") === null, "Failed save must not produce a phantom project");
  check(await page.evaluate(() => currentProjectName === "Numpad Copy"), "Failed Save As must preserve the current project identity");
  await page.locator("#messageDialogClose").click();
  await page.unroute("**/api/fabric-editor/save-project");
  await enterName("#saveProjectAs", "Retried Project");
  check(Boolean(await project("Retried Project")), "Retry with Enter must save successfully");

  for (const action of ["escape", "click", "focused-enter"]) {
    const before = writes.length;
    await page.locator("#saveProjectAs").click();
    await input.fill(`Cancelled ${action}`);
    if (action === "escape") await input.press("Escape");
    else if (action === "click") await page.locator("#textPromptCancel").click();
    else { await page.locator("#textPromptCancel").focus(); await page.keyboard.press("Enter"); }
    await prompt.waitFor({ state: "hidden" });
    check(writes.length === before && await project(`Cancelled ${action}`) === null, `${action} must cancel without any save request`);
  }
  await page.locator("#saveProjectAs").click();
  await input.fill("Clicked Continue");
  await page.locator("#textPromptConfirm").click();
  await prompt.waitFor({ state: "hidden" });
  await idle();
  check(Boolean(await project("Clicked Continue")), "Continue click must still save");
  await page.locator("#saveProjectAs").click();
  await input.fill("Implicit Submit");
  await page.evaluate(() => document.querySelector("#textPromptDialog form").requestSubmit());
  await prompt.waitFor({ state: "hidden" });
  await idle();
  check(Boolean(await project("Implicit Submit")), "Form submission without a submitter must confirm");

  await page.evaluate(() => {
    window.promptResults = [];
    requestTextInput("Old", "Name").then(value => promptResults.push(["old", value]));
    requestTextInput("Replacement", "Name").then(value => promptResults.push(["replacement", value]));
  });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  check(await page.evaluate(() => JSON.stringify(promptResults) === JSON.stringify([["old", null]])), "A delayed close event must not cancel a newly opened prompt");
  await input.fill("Replacement accepted");
  await input.press("Enter");
  check(await page.evaluate(() => promptResults[1]?.[1] === "Replacement accepted"), "Replacement prompt must accept its own Enter");

  await page.locator("#newCanvas").click();
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.evaluate(async shapes => { await loadPayload({ shapes }); }, grouped.shapes);
  await enterName("#exportJson", "Enter Export");
  const exported = await page.evaluate(async () => {
    await refreshJsonBrowser();
    const entry = selectedJsonBrowserEntry();
    return (await (await fetch(`${JSON_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
  });
  check(exported.shapes.length === count && exported.shapes.every(shape => Object.keys(shape).every(key => !key.startsWith("editor_"))), "Enter-exported JSON must contain every flat layer without editor metadata");
  await enterName("#saveProject", "Enter First Save");
  check(Boolean(await project("Enter First Save")), "The first Save must accept Enter just like Save As");

  let release;
  const held = new Promise(resolve => { release = resolve; });
  await page.route("**/api/fabric-editor/save-project", async route => { await held; await route.continue(); });
  const beforeHeld = writes.length;
  await page.locator("#saveProjectAs").click();
  await input.fill("Single Submission");
  await input.press("Enter");
  await page.waitForFunction(() => projectSaveInProgress);
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  release();
  await idle();
  await page.unroute("**/api/fabric-editor/save-project");
  check(writes.length === beforeHeld + 1 && Boolean(await project("Single Submission")), "Repeated Enter during a write must not save twice");

  await page.locator("#adjustTheme").click();
  await page.locator("#themeAdjustName").fill("Enter Theme");
  await page.evaluate(() => document.getElementById("themeAdjustName").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true })));
  check(await page.locator("#themeAdjustDialog").isVisible(), "IME composition Enter must not prematurely save the theme");
  await page.locator("#themeAdjustName").press("Enter");
  await page.locator("#themeAdjustDialog").waitFor({ state: "hidden" });
  check(await page.evaluate(async () => (await (await fetch(EDITOR_THEMES_API)).json()).themes.some(theme => theme.name === "Enter Theme")), "Theme-name Enter must write a real theme file");
  await page.locator('[data-tool-mode="text"]').click();
  await page.locator("#textVinylInput").fill("First line");
  await page.locator("#textVinylInput").press("End");
  await page.locator("#textVinylInput").press("Enter");
  await page.locator("#textVinylInput").pressSequentially("Second line");
  check(await page.locator("#textVinylInput").inputValue() === "First line\nSecond line", "Enter must remain a newline in multiline text");
  page.off("request", capture);
  await page.screenshot({ path: path.join(output,"enter-workflow.png") });
  return { initial, saveAsEnter: true, reopenedThroughUi: true, savedLayers: count, layerAndGroupRename: true, unicode: true, numpadEnter: true, duplicateProtected: true, failedSaveRetry: true, cancellation: ["Escape", "Cancel click", "Enter on Cancel"], explicitContinue: true, implicitSubmit: true, promptReplacement: true, flatExport: true, firstSaveEnter: true, singleSubmission: true, themeEnter: true, multilineUnchanged: true };
}
