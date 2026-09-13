async (page,options={}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const initial=options.layers ? await h.setup(page,output,options) : null;
  page.setDefaultTimeout(25000);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const ready = () => page.waitForFunction(() => window.KfpsDesktop?.ready);
  const closeDialogs = () => page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(d => d.close()));
  let reloadNumber=0;
  const reloadSaved=async()=> {
    if(await page.evaluate(()=>documentDirty)) {
      await closeDialogs();
      await page.locator('#saveProject').click();
      if(await page.locator('#textPromptDialog').isVisible()) {
        await h.type(page,'#textPromptInput',`Language reload checkpoint ${++reloadNumber}`);
        await page.locator('#textPromptInput').press('Enter');
      }
      await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    }
    await page.reload();await ready();
  };
  const results = [];
  for (const language of ["en", "ko"]) {
    await page.evaluate(async language => {
      editorSettings.setItem(KfpsI18n.KEY, language);
      editorSettings.setItem(PROJECT_SHARING_ACK_KEY, "1");
      editorSettings.removeItem(LANGUAGE_NOTICE_ACK_KEY);
      await KfpsEditorPreferences.flush();
    }, language);
    await reloadSaved();
    await page.locator("#languageNoticeDialog").waitFor({state: "visible"});
    check(await page.evaluate(() => KfpsI18n.language) === language, "Persisted language not applied");
    check(await page.locator("h1").innerText() === (language === "ko" ? "K-FPS" : "KFPS Vinyl Editor"), "Localized editor heading is incorrect");
    check(await page.locator("#languageNoticeContinue").isDisabled(), "Acknowledgment must be required");
    await page.keyboard.press("Escape");
    check(await page.locator("#languageNoticeDialog").isVisible(), "Escape dismissed the notice permanently");
    check(await page.evaluate(() => editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY)) === null, "Showing notice acknowledged it");
    const layout = [];
    for (const theme of ["pastel", "dark", "blackout", "whiteout"]) {
      await page.evaluate(theme => editorTheme.applyEditorTheme(theme, {persist: false}), theme);
      for (const size of [{width: 1440, height: 900}, {width: 900, height: 640}]) {
        await page.setViewportSize(size);
        const result = await page.evaluate(() => {
          const select = document.getElementById("editorLanguageSelect").getBoundingClientRect();
          const notice = document.getElementById("languageNoticeDialog").getBoundingClientRect();
          const button = document.getElementById("languageNoticeContinue");
          const arrow = document.querySelector(".languageNoticeArrow").getBoundingClientRect();
          const menus = [...document.querySelectorAll(".menuGroup")];
          return {
            lowerLeft: select.x < 200 && select.bottom <= innerHeight && select.y > innerHeight - 40,
            noticeFits: notice.x >= 0 && notice.right <= innerWidth && notice.y >= 0 && notice.bottom < select.top,
            arrowPoints: arrow.left + arrow.width / 2 >= select.left && arrow.left + arrow.width / 2 <= select.right && Math.abs(arrow.bottom - select.top) < 12,
            buttonFits: button.scrollWidth <= button.clientWidth + 1,
            menusFit: menus.every(menu => [...menu.children].filter(child => child.getClientRects().length).every(child => {
              const a = child.getBoundingClientRect(), b = menu.getBoundingClientRect();
              return a.right <= b.right + 1 && a.left >= b.left - 1;
            })),
            documentFits: document.documentElement.scrollWidth <= innerWidth,
            contextTextFits: [...document.querySelectorAll(".contextItem b")].every(item => item.scrollHeight <= item.clientHeight + 1),
          };
        });
        await page.screenshot({path: `${language}-${theme}-${size.width}-notice.png`});
        check(Object.values(result).every(Boolean), `Localization layout ${language} ${theme} ${size.width}: ${JSON.stringify(result)}`);
        layout.push({theme, ...size, ...result});
      }
    }
    await page.setViewportSize({width: 1440, height: 900});
    await page.evaluate(() => editorTheme.applyEditorTheme("blackout", {persist: false}));
    // Exercise the actual preference API failure boundary, not a replacement editor.
    await page.route("**/api/fabric-editor/preferences", route => route.request().method() === "POST"
      ? route.fulfill({status: 503, contentType: "application/json", body: '{"ok":false,"error":"test: disk unavailable"}'}) : route.continue());
    await page.locator("#languageNoticeAcknowledge").check();
    await page.locator("#languageNoticeContinue").click();
    await page.locator("#languageNoticeError").waitFor({state: "visible"});
    check(await page.evaluate(() => editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY)) === null, "Failed acknowledgment saved in memory");
    await page.unroute("**/api/fabric-editor/preferences");
    await page.locator("#languageNoticeContinue").click();
    await page.locator("#languageNoticeDialog").waitFor({state: "hidden"});
    check(await page.evaluate(async () => (await (await fetch(EDITOR_PREFS_API)).json()).settings[LANGUAGE_NOTICE_ACK_KEY]) === "1", "Acknowledgment not written to real server");
    await reloadSaved();
    check(await page.locator("#languageNoticeDialog").isHidden(), "Acknowledged notice reappeared after reload");
    await closeDialogs();
    if(initial) {
      await h.select(page,'Human target');
    } else await page.evaluate(async () => {
      await loadPayload({shapes: [{type:1048677, color:[40,180,150,255], data:[0,0,1,1,0,0,0], shape_name:"Save {0} 한국어", editor_group_id:"g", editor_group_name:"Group {1}"}]});
      canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    });
    const original = await page.evaluate(() => JSON.stringify(snapshotShapes()));
    const next = language === "en" ? "ko" : "en";
    await page.route("**/api/fabric-editor/preferences", route => route.request().method() === "POST"
      ? route.fulfill({status: 503, contentType:"application/json", body:'{"ok":false}'}) : route.continue());
    await page.locator("#editorLanguageSelect").selectOption(next);
    await page.waitForFunction(() => !document.getElementById("editorLanguageSelect").disabled);
    check(await page.locator("#editorLanguageSelect").inputValue() === language, "Failed language save did not restore selection");
    await page.unroute("**/api/fabric-editor/preferences");
    await closeDialogs();
    await page.locator("#editorLanguageSelect").selectOption(next);
    await page.waitForFunction(() => !document.getElementById("editorLanguageSelect").disabled);
    check(await page.evaluate(() => KfpsI18n.language) === language, "Language change reloaded unsaved workspace");
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === original, "Language change altered artwork or names");
    await closeDialogs();
    await page.locator("#saveProjectAs").click();
    await page.locator("#textPromptInput").fill(`Localization ${language} 한국어`);
    await page.locator("#textPromptInput").press("Enter");
    await page.waitForFunction(() => !documentDirty && currentProjectName);
    const saved = await page.evaluate(async () => {
      const response = await fetch(`${PROJECT_BROWSER_API}?name=${encodeURIComponent(currentProjectName)}`);
      return {name: currentProjectName, shapes: snapshotShapes(), status: response.status};
    });
    check(saved.status === 200, "Project save was not available through server");
    results.push({initial,language, layout, requiredConfirmation:true, failedWritesRetry:true, persistedAcknowledgment:true, savedProject:saved.name, safeLanguageSwitch:true});
  }
  await page.evaluate(async () => {
    editorSettings.setItem(KfpsI18n.KEY, "ko");
    await KfpsEditorPreferences.flush();
    documentDirty = false;
  });
  return results;
}
