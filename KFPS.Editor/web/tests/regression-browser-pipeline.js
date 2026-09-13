async page => {
  const check = (v, message) => { if (!v) throw new Error(message); };
  const group = name => ({ key: name, title: name, source: name, count: 1, max_layers: 1, mtime: 1,
    entries: [{ id: name + ".json", name: name + ".json", layers: 1, mtime: 1 }] });
  await page.route("**/api/fabric-editor/json-browser?*", async route => {
    const source = await page.evaluate(url => new URL(url).searchParams.get("source"), route.request().url());
    if (source === "generated") await new Promise(resolve => setTimeout(resolve, 250));
    await route.fulfill({ json: { groups: [group(source), group(source + "2")], total_entries: 2 } }).catch(() => {});
  });
  const latest = await page.evaluate(async () => {
    setJsonBrowserSource("generated");
    const old = refreshJsonBrowser();
    await new Promise(resolve => setTimeout(resolve, 30));
    setJsonBrowserSource("editor");
    await refreshJsonBrowser();
    await old;
    return { source: jsonBrowserState.source, group: selectedJsonBrowserGroup()?.key, loading: jsonBrowserState.loading };
  });
  check(latest.source === "editor" && latest.group === "editor" && !latest.loading, "Rapid source switch retained stale results or dropped the new request");
  await page.evaluate(() => {
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    $("jsonBrowserDialog").showModal();
    window.browserFirstThumb = $("jsonBrowserGroups").querySelector("img");
  });
  await page.locator(".jsonBrowserCard").nth(1).click();
  check(await page.evaluate(() => Boolean(window.browserFirstThumb) && window.browserFirstThumb === $("jsonBrowserGroups").querySelector("img")), "Selecting a group recreated its thumbnails");
  await page.unroute("**/api/fabric-editor/json-browser?*");
  await page.route("**/api/fabric-editor/json-browser?*", route => route.fulfill({ status: 503, json: { error: "test: storage unavailable" } }));
  const failed = await page.evaluate(async () => {
    await refreshJsonBrowser();
    return !jsonBrowserState.loading && !jsonBrowserState.request && !selectedJsonBrowserEntry();
  });
  check(failed, "Failed scan kept a stale import target or left the browser busy");
  await page.unroute("**/api/fabric-editor/json-browser?*");
  await page.evaluate(() => $("jsonBrowserDialog").close());
  return { latestSourceWins: true, thumbnailElementsRetained: true, failedScanClearsState: true };
}
