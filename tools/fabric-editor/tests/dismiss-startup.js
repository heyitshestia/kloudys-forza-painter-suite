async (page) => {
  await page.evaluate(() => {
    localStorage.setItem("kloudyFabricStartupHelpConfirmed", "true");
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  });
}
