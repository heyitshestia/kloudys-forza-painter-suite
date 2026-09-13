async (page) => {
  await page.evaluate(async () => {
    localStorage.setItem("kloudyFabricStartupHelpConfirmed", "true");
    KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
    KfpsEditorPreferences.setItem("kloudyFabricLanguageNoticeAcknowledged", "1");
    KfpsEditorPreferences.setItem(EDITOR_UPDATE_ACK_KEY, EDITOR_UPDATE_NOTICE_VERSION);
    await KfpsEditorPreferences.flush();
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  });
}
