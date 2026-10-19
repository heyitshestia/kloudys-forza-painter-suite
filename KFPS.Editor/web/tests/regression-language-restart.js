async page => {
  await page.waitForFunction(()=>window.KfpsDesktop?.ready&&startupRecoveryHandled);
  const state=await page.evaluate(async()=>({language:KfpsI18n.language,
    systemLanguage:window.KfpsEditorSystemLanguage,acknowledged:editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY),
    noticeOpen:document.querySelector('#languageNoticeDialog').open,
    serverSettings:(await(await fetch(EDITOR_PREFS_API)).json()).settings}));
  if (state.language!=='ko'||state.acknowledged!==null||state.noticeOpen||state.serverSettings.kloudyFabricLanguage!=='ko') {
    throw Error('Language preference or removed-tip contract changed after native restart: '+JSON.stringify(state));
  }
  return {passed:true,fullProcessRestart:true,...state};
}
