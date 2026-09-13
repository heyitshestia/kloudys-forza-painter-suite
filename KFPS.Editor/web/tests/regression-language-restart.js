async page => {
  const state = await page.evaluate(async () => ({
    language: KfpsI18n.language,
    systemLanguage: window.KfpsEditorSystemLanguage,
    acknowledged: editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY),
    wouldShow: maybeShowLanguageNotice(),
    serverSettings: (await (await fetch(EDITOR_PREFS_API)).json()).settings,
  }));
  if (state.language !== "ko" || state.acknowledged !== "1" || state.wouldShow || state.serverSettings.kloudyFabricLanguage !== "ko") {
    throw new Error(`Language/acknowledgment did not survive native process restart: ${JSON.stringify(state)}`);
  }
  return {fullProcessRestart:true, ...state};
}
