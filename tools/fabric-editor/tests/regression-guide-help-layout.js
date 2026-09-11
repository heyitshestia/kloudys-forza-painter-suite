async page => {
  const results=[];
  for(const language of ["en","ko"]){
    await page.evaluate(async language=>{
      editorSettings.setItem(KfpsI18n.KEY,language);
      editorSettings.setItem(PROJECT_SHARING_ACK_KEY,"1");
      editorSettings.setItem(LANGUAGE_NOTICE_ACK_KEY,"1");
      await KfpsEditorPreferences.flush();
    },language);
    await page.reload();await page.waitForFunction(()=>window.KfpsDesktop?.ready);
    await page.evaluate(()=>document.querySelectorAll("dialog[open]").forEach(d=>d.close()));
    await page.evaluate(()=>applyEditorTheme("blackout",{persist:false}));
    for(const size of [{width:1600,height:1000},{width:900,height:640}]){
      await page.setViewportSize(size);
      await page.locator("#helpBtn").click();
      const layout=await page.evaluate(()=>{
        const dialog=$("helpDialog");
        const section=[...dialog.querySelectorAll("section")].find(s=>s.querySelector("h3")?.textContent===KfpsI18n.t("Guides, Grid, And Snapping"));
        if(!section)throw new Error("Guide Help section missing");
        section.scrollIntoView({block:"start"});
        const rect=dialog.getBoundingClientRect();
        return {fits:rect.left>=0&&rect.right<=innerWidth&&rect.top>=0&&rect.bottom<=innerHeight,
          textFits:[...section.querySelectorAll("li")].every(li=>li.scrollWidth<=li.clientWidth+1),
          angleHelp:section.textContent.includes("45"),language:KfpsI18n.language};
      });
      if(!layout.fits||!layout.textFits||!layout.angleHelp||layout.language!==language)throw new Error(JSON.stringify(layout));
      await page.screenshot({path:path.join(output,`guide-help-${language}-${size.width}.png`)});
      await page.locator("#closeHelp").click();
      results.push({...size,...layout});
    }
  }
  return results;
}
