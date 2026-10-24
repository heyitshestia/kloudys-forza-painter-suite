async (page) => {
  // Exercise the real native page theme picker and modal lifecycle.
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#editorThemeSelect').selectOption({label:'Original Xbox'});
  await page.keyboard.press('Escape');
  await page.evaluate(()=>KfpsEditorPreferences.flush());
  const data=await page.evaluate(()=>({base:document.documentElement.dataset.editorThemeBase,
    accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(),ready:window.KfpsDesktop.ready}));
  check(data.accent==='#a1e52c' && data.ready,'Native Qt editor did not apply Xbox theme');
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#adjustTheme').click();
  await page.locator('#themeAdjustDialog').waitFor({state:'visible'});
  const enteredAt=Date.now(), samples=[];
  for(let attempt=0;attempt<12;attempt++) {
    await page.waitForTimeout(100);
    samples.push(await page.locator('#themeAdjustDialog').evaluate(n=>({ms:performance.now(),opacity:getComputedStyle(n).opacity,
      animations:n.getAnimations().map(a=>({time:a.currentTime,state:a.playState}))})));
    if(samples.at(-1).opacity==='1')break;
  }
  const motion=await page.evaluate(()=>({state:document.documentElement.dataset.xboxMotion,
    dialogOpacity:getComputedStyle(document.getElementById('themeAdjustDialog')).opacity}));
  motion.samples=samples;motion.elapsed=Date.now()-enteredAt;
  check(motion.dialogOpacity==='1','Native theme dialog must remain readable after entry: '+JSON.stringify(motion));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  check(await page.locator('#themeAdjustDialog').evaluate(n=>!n.open),'Theme dialog did not cancel');
  return {passed:true,nativeTheme:data,themeDialogCancel:true,motion};
}
