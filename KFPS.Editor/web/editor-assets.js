(function (global) {
  "use strict";
  const API = "/api/fabric-editor/assets";
  const FORMAT = "kfps_editor_asset_v1";
  const MAX_BYTES = 8 * 1024 * 1024;

  function install(options) {
    const byId = id => document.getElementById(id);
    let entries = [], limit = 40, generation = 0, busy = false;
    let pending = Promise.resolve();
    async function request(query = "", body = null) {
      const response = await fetch(API + query, {
        method: body ? "POST" : "GET", cache: "no-store", signal: AbortSignal.timeout(15000),
        ...(body ? { headers: { ...options.headers, "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(KfpsI18n.error(result.error || KfpsI18n.t("The asset library is unavailable.")));
      return result;
    }
    function status(message, error = false) {
      byId("assetStatus").textContent = message;
      byId("assetStatus").classList.toggle("assetError", error);
    }
    function run(task) {
      if (busy) return pending;
      busy = true;
      render();
      pending = Promise.resolve().then(task).catch(error => {
        status(error.message || String(error), true);
        options.notify(error.message || String(error));
      }).finally(() => { busy = false; render(); });
      return pending;
    }
    function button(label, action, className = "") {
      const node = document.createElement("button");
      node.type = "button";
      node.textContent = label;
      node.title = label;
      node.className = className;
      node.disabled = busy;
      node.addEventListener("click", () => run(action));
      return node;
    }
    async function get(entry) { return (await request(`?id=${encodeURIComponent(entry.id)}`)).payload; }
    async function refresh() {
      const current = ++generation;
      status(KfpsI18n.t("Loading assets..."));
      const result = await request();
      if (current !== generation) return;
      entries = result.entries || [];
      const unavailable = result.unavailable?.length || 0;
      status(unavailable ? KfpsI18n.t("{0} asset file(s) could not be read. They have not been removed.", unavailable) : KfpsI18n.t("{0} asset(s)", entries.length) , Boolean(unavailable));
      render();
    }
    function render() {
      const list = byId("assetGrid");
      const query = byId("assetSearch").value.trim().toLocaleLowerCase();
      const filtered = entries.filter(entry => entry.name.toLocaleLowerCase().includes(query));
      list.replaceChildren();
      for (const entry of filtered.slice(0, limit)) {
        const card = document.createElement("article");
        card.className = "editorAsset";
        card.dataset.assetId = entry.id;
        const preview = button("", async () => options.insert((await get(entry)).shapes));
        preview.className = "assetPreview";
        preview.title = KfpsI18n.t("Insert {0}", entry.name);
        preview.setAttribute("aria-label", KfpsI18n.t("Insert {0}", entry.name));
        const image = document.createElement("img");
        image.src = entry.preview_url;
        image.alt = entry.name;
        image.loading = "lazy";
        image.decoding = "async";
        image.addEventListener("error", () => { preview.textContent = KfpsI18n.t("Preview unavailable"); });
        preview.append(image);
        const name = document.createElement("strong");
        name.textContent = entry.name;
        name.title = entry.name;
        const count = document.createElement("span");
        count.className = "assetLayerCount";
        count.textContent = KfpsI18n.t("{0} layers", entry.layer_count);
        const actions = document.createElement("div");
        actions.className = "assetActions";
        actions.append(button(KfpsI18n.t("Insert"), async () => options.insert((await get(entry)).shapes)));
        const menu = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "\u22ef";
        summary.title = KfpsI18n.t("Actions for {0}", entry.name);
        summary.setAttribute("aria-label", summary.title);
        menu.append(summary);
        const menuBody = document.createElement("div");
        menuBody.className = "assetMenu";
        menuBody.append(button(KfpsI18n.t("Rename"), async () => {
          menu.open = false;
          const name = await options.prompt(KfpsI18n.t("Rename Asset"), KfpsI18n.t("Name"), entry.name);
          if (name === null) return;
          await request("", { action: "rename", id: entry.id, revision: entry.revision, name });
          await refresh();
        }));
        menuBody.append(button(KfpsI18n.t("Export Asset"), async () => {
          menu.open = false;
          const payload = await get(entry);
          const name = entry.name.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[ .]+$/, "") || "asset";
          options.download(`${name}.kfps-asset.json`, JSON.stringify({ format: FORMAT, name: payload.name, shapes: payload.shapes }, null, 2));
        }));
        menuBody.append(button(KfpsI18n.t("Delete"), async () => {
          menu.open = false;
          if (!await options.confirm(KfpsI18n.t("Delete Asset"), KfpsI18n.t("Delete \"{0}\" from the library? Copies already inserted in projects will remain.", entry.name), KfpsI18n.t("Delete"))) return;
          await request("", { action: "delete", id: entry.id, revision: entry.revision });
          await refresh();
        }));
        menu.append(menuBody);
        actions.append(menu);
        card.append(preview, name, count, actions);
        list.append(card);
      }
      byId("assetMore").hidden = filtered.length <= limit;
      for (const id of ["assetRefresh", "assetImport", "assetSaveSelection", "assetMore"]) byId(id).disabled = busy;
      byId("assetSaveSelection").disabled = busy || !options.hasSelection();
    }
    byId("assetSaveSelection").addEventListener("click", () => run(async () => {
      const shapes = options.selection();
      if (!shapes.length) throw new Error(KfpsI18n.t("Select layers before saving an asset."));
      const name = await options.prompt(KfpsI18n.t("Save Selection As Asset"), KfpsI18n.t("Name"), KfpsI18n.t("Untitled asset"));
      if (name === null) return;
      await request("", { action: "save", payload: { format: FORMAT, name, shapes } });
      await refresh();
      options.notify(KfpsI18n.t("Saved asset: {0}", name));
    }));
    byId("assetRefresh").addEventListener("click", () => run(refresh));
    byId("assetSearch").addEventListener("input", () => { limit = 40; render(); });
    byId("assetMore").addEventListener("click", () => { limit += 40; render(); });
    byId("assetImport").addEventListener("click", () => byId("assetInput").click());
    document.addEventListener("pointerdown", event => {
      byId("assetGrid").querySelectorAll("details[open]").forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
    });
    byId("assetGrid").addEventListener("keydown", event => {
      if (event.key !== "Escape") return;
      const menu = event.target.closest("details[open]");
      if (menu) { event.preventDefault(); event.stopPropagation(); menu.open = false; menu.querySelector("summary").focus(); }
    });
    byId("assetInput").addEventListener("change", event => {
      const file = event.target.files[0];
      event.target.value = "";
      if (!file) return;
      run(async () => {
        if (file.size > MAX_BYTES) throw new Error(KfpsI18n.t("Asset files must be smaller than 8 MB."));
        const payload = JSON.parse(await file.text());
        if (payload?.format !== FORMAT) throw new Error(KfpsI18n.t("Choose a KFPS editor asset file."));
        await request("", { action: "save", payload });
        await refresh();
        options.notify(KfpsI18n.t("Imported asset: {0}", payload.name));
      });
    });
    return {
      refresh: () => run(refresh),
      selectionChanged: () => { byId("assetSaveSelection").disabled = busy || !options.hasSelection(); },
      get busy() { return busy; },
      waitForIdle: () => pending,
    };
  }
  global.KfpsEditorAssets = Object.freeze({ install });
})(window);
