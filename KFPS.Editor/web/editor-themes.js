(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorThemes = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ scene, view, settings, endpoints, headers, cleanName, escapeHtml, KfpsI18n,
    fetcher = (...args) => fetch(...args) }) {
    const requests = new Set();
    let disposed = false, choiceRevision = 0, catalogRevision = 0;

    function present(action) {
      if (disposed) return;
      try { action(); }
      catch (error) {
        try { view.error(KfpsI18n.t("The edit was kept, but the display could not refresh."), error); }
        catch (_) { /* Presentation is not the theme's durable state. */ }
      }
    }

    async function requestJson(url, options = {}, timeoutMs = 5000) {
      if (disposed) throw new DOMException("The operation was aborted.", "AbortError");
      const controller = new AbortController();
      requests.add(controller);
      let timer, onAbort;
      const aborted = new Promise((_, reject) => {
        onAbort = () => reject(controller.signal.reason);
        controller.signal.addEventListener("abort", onAbort, { once: true });
        timer = setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), timeoutMs);
      });
      try {
        return await Promise.race([aborted, (async () => {
          const response = await fetcher(url, { cache: "no-store", ...options, signal: controller.signal });
          try {
            controller.signal.throwIfAborted();
            const data = await response.json().catch(() => ({}));
            controller.signal.throwIfAborted();
            if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
            return data;
          } finally { if (!response.bodyUsed) response.body?.cancel().catch(() => {}); }
        })()]);
      } finally {
        clearTimeout(timer); controller.signal.removeEventListener("abort", onAbort); requests.delete(controller);
      }
    }

    function dispose() {
      if (disposed) return;
      disposed = true;
      for (const controller of requests) controller.abort();
    }
    const BUILTIN_EDITOR_THEMES = [
      { id: "pastel", name: "Signature Pink", builtin: true, values: {} },
      { id: "dark", name: "Dark", builtin: true, values: {} },
      { id: "blackout", name: "Blackout", builtin: true, values: {} },
      { id: "whiteout", name: "Whiteout", builtin: true, values: {} },
    ];

    const THEME_MAIN_FIELDS = ["--shell", "--panel", "--text", "--accent", "--fabric-canvas-bg", "--line"];

    const THEME_FIELDS = [
      ["--bg", KfpsI18n.t("App background")],
      ["--shell", KfpsI18n.t("Outer shell")],
      ["--panel", KfpsI18n.t("Main panels")],
      ["--panel2", KfpsI18n.t("Raised panels")],
      ["--panel3", KfpsI18n.t("Inset panels")],
      ["--text", KfpsI18n.t("Main text")],
      ["--muted", KfpsI18n.t("Muted text")],
      ["--soft", KfpsI18n.t("Soft labels")],
      ["--line", KfpsI18n.t("Thin borders")],
      ["--line2", KfpsI18n.t("Strong borders")],
      ["--accent", KfpsI18n.t("Primary accent")],
      ["--accent2", KfpsI18n.t("Secondary accent")],
      ["--good", KfpsI18n.t("Success color")],
      ["--warn", KfpsI18n.t("Warning color")],
      ["--danger", KfpsI18n.t("Danger color")],
      ["--canvas-bg", KfpsI18n.t("Canvas surround")],
      ["--fabric-canvas-bg", KfpsI18n.t("Canvas color")],
      ["--editor-grid-line", KfpsI18n.t("Grid lines")],
      ["--editor-grid-axis", KfpsI18n.t("Grid axis")],
      ["--editor-guide-line", KfpsI18n.t("Guide lines")],
      ["--editor-guide-selected", KfpsI18n.t("Selected guide")],
      ["--editor-guide-draft", KfpsI18n.t("Guide draft")],
      ["--editor-notch-line", KfpsI18n.t("Rotation notch")],
      ["--editor-notch-muted", KfpsI18n.t("Muted notch")],
      ["--editor-notch-active", KfpsI18n.t("Active notch")],
      ["--editor-selection-border", KfpsI18n.t("Selection border")],
      ["--editor-shape-outline", KfpsI18n.t("Shape outline")],
      ["--editor-selection-corner", KfpsI18n.t("Transform handles")],
      ["--editor-selection-corner-stroke", KfpsI18n.t("Handle stroke")],
      ["--editor-skew-corner", KfpsI18n.t("Skew handle")],
      ["--shape-tile-bg", KfpsI18n.t("Shape tile background")],
      ["--dialog-bg", KfpsI18n.t("Dialog background")],
      ["--dialog-header", KfpsI18n.t("Dialog header")],
    ];

    let editorThemes = new Map(BUILTIN_EDITOR_THEMES.map((theme) => [theme.id, theme]));

    let themeAdjustRestoreTheme = null;

    let themeAdjustSaving = false;

    function normalizeTheme(theme) {
      const key = String(theme || "");
      if (editorThemes.has(key)) return key;
      return key === "dark" ? "dark" : "pastel";
    }

    function themeById(theme) {
      return editorThemes.get(normalizeTheme(theme)) || editorThemes.get("pastel") || BUILTIN_EDITOR_THEMES[0];
    }

    function themeFieldCurrentValues() {
      const styles = getComputedStyle(document.documentElement);
      const values = {};
      THEME_FIELDS.forEach(([key]) => {
        values[key] = styles.getPropertyValue(key).trim();
      });
      return values;
    }

    function clearCustomThemeProperties() {
      THEME_FIELDS.forEach(([key]) => document.documentElement.style.removeProperty(key));
      ["--surface-rgb", "--panel-rgb", "--accent-rgb", "--accent2-rgb", "--good-rgb", "--warn-rgb", "--danger-rgb"].forEach((key) => {
        document.documentElement.style.removeProperty(key);
      });
    }

    function hexToRgbString(hex) {
      const match = String(hex || "").trim().match(/^#([0-9a-f]{6})$/i);
      if (!match) return null;
      const raw = match[1];
      return `${parseInt(raw.slice(0, 2), 16)}, ${parseInt(raw.slice(2, 4), 16)}, ${parseInt(raw.slice(4, 6), 16)}`;
    }

    function syncDerivedThemeRgb(values = {}) {
      const pairs = [
        ["--shell", "--surface-rgb"],
        ["--panel", "--panel-rgb"],
        ["--accent", "--accent-rgb"],
        ["--accent2", "--accent2-rgb"],
        ["--good", "--good-rgb"],
        ["--warn", "--warn-rgb"],
        ["--danger", "--danger-rgb"],
      ];
      pairs.forEach(([source, target]) => {
        const rgb = hexToRgbString(values[source]);
        if (rgb) document.documentElement.style.setProperty(target, rgb);
      });
    }

    function applyCustomThemeValues(values = {}) {
      clearCustomThemeProperties();
      THEME_FIELDS.forEach(([key]) => {
        if (values[key]) document.documentElement.style.setProperty(key, String(values[key]));
      });
      syncDerivedThemeRgb(values);
    }

    function populateEditorThemeSelect(selectedTheme = null) {
      const select = view.element("editorThemeSelect");
      if (!select) return;
      const current = selectedTheme || select.value || "pastel";
      select.innerHTML = "";
      [...editorThemes.values()].forEach((theme) => {
        const option = document.createElement("option");
        option.value = theme.id;
        option.textContent = theme.builtin ? KfpsI18n.t(theme.name) : KfpsI18n.t("{0} (Custom)", theme.name);
        select.appendChild(option);
      });
      select.value = normalizeTheme(current);
    }

    function saveEditorThemePreference(theme) {
      if (disposed) return;
      settings.setItem("kloudyFabricTheme", normalizeTheme(theme));
      if (window.KfpsEditorPreferences) return;
      requestJson(endpoints.preferences, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ theme: normalizeTheme(theme) }),
      }).catch(() => {
        // Direct-file launches or blocked local server writes still keep localStorage.
      });
    }

    function applyEditorTheme(theme, options = {}) {
      if (disposed) return;
      if (options.preview || options.persist !== false) choiceRevision += 1;
      const safeTheme = normalizeTheme(theme);
      const entry = themeById(safeTheme);
      document.documentElement.dataset.editorThemeBase = entry.builtin ? safeTheme : (entry.base || "pastel");
      if (entry.builtin) {
        clearCustomThemeProperties();
        document.documentElement.dataset.editorTheme = safeTheme;
      } else {
        document.documentElement.dataset.editorTheme = "custom";
        applyCustomThemeValues(entry.values || {});
      }
      if (!options.preview && options.persist !== false) {
        present(() => saveEditorThemePreference(safeTheme));
      }
      present(() => populateEditorThemeSelect(safeTheme));
      present(applyEditorThemePreviewRefresh);
    }

    function normalizeEntry(theme) {
      if (!theme?.id || typeof theme !== "object" || !theme.values || typeof theme.values !== "object" || Array.isArray(theme.values)) return null;
      const builtin = BUILTIN_EDITOR_THEMES.find(entry => entry.id === String(theme.id));
      if (builtin) return builtin;
      return { id: String(theme.id), name: String(theme.name || theme.id), builtin: false,
        base: BUILTIN_EDITOR_THEMES.some(entry => entry.id === theme.base) ? theme.base : "pastel", values: theme.values };
    }

    async function loadEditorThemes() {
      const revision = ++catalogRevision;
      try {
        const data = await requestJson(endpoints.themes);
        if (disposed || revision !== catalogRevision || !Array.isArray(data.themes)) return;
        const entries = new Map(BUILTIN_EDITOR_THEMES.map(theme => [theme.id, theme]));
        for (const theme of data.themes) {
          const entry = normalizeEntry(theme);
          if (entry) entries.set(entry.id, entry);
        }
        editorThemes = entries;
      } catch (_err) {
        // Failed refresh preserves the last complete list; first startup has built-ins.
      }
      present(() => populateEditorThemeSelect(view.element("editorThemeSelect")?.value || settings.getItem("kloudyFabricTheme") || "pastel"));
    }

    async function loadEditorThemePreference(expectedChoice = choiceRevision) {
      try {
        const data = await requestJson(endpoints.preferences);
        if (disposed || expectedChoice !== choiceRevision) return null;
        if (data.theme) {
          applyEditorTheme(data.theme, { persist: false });
          return data.theme;
        }
      } catch (_err) {
        // Direct-file/browser fallback.
      }
      return null;
    }

    async function initialize(initialTheme) {
      const revision = choiceRevision;
      await loadEditorThemes();
      if (disposed || revision !== choiceRevision) return;
      const serverTheme = await loadEditorThemePreference(revision);
      if (disposed || revision !== choiceRevision) return;
      if (!serverTheme) {
        applyEditorTheme(initialTheme, { persist: false });
        present(() => saveEditorThemePreference(normalizeTheme(initialTheme)));
      }
    }

    function themeFieldInputRow(key, label, value) {
      const safeValue = String(value || "");
      const isHex = /^#[0-9a-f]{6}$/i.test(safeValue);
      return KfpsI18n.t("\n    <div class=\"themeAdjustRow\">\n      <label for=\"theme-{0}\">{1}</label>\n      {2}\n      <input id=\"theme-{3}\" class=\"themeValueInput\" data-theme-var=\"{4}\" value=\"{5}\" spellcheck=\"false\" aria-label=\"{6} value\">\n    </div>\n  ", escapeHtml(key.slice(2)), escapeHtml(label), isHex ? KfpsI18n.t("<input class=\"themeColorInput\" type=\"color\" aria-label=\"{0} color\" value=\"{1}\" data-theme-color-for=\"{2}\">", escapeHtml(label), escapeHtml(safeValue), escapeHtml(key)) : '<span></span>', escapeHtml(key.slice(2)), escapeHtml(key), escapeHtml(safeValue), escapeHtml(label));
    }

    function themeFieldInput(fields, key) {
      return [...(fields?.querySelectorAll(".themeValueInput") || [])].find((input) => input.dataset.themeVar === key) || null;
    }

    function themeColorInput(fields, key) {
      return [...(fields?.querySelectorAll(".themeColorInput") || [])].find((input) => input.dataset.themeColorFor === key) || null;
    }

    function renderThemeAdjustFields(values) {
      const fields = view.element("themeAdjustFields");
      if (fields) {
        const basicLabels = { "--shell": KfpsI18n.t("Window"), "--panel": KfpsI18n.t("Panels"), "--text": KfpsI18n.t("Text"), "--accent": KfpsI18n.t("Accent"), "--fabric-canvas-bg": KfpsI18n.t("Canvas"), "--line": KfpsI18n.t("Borders") };
        const rows = keys => THEME_FIELDS.filter(([key]) => keys.includes(key))
          .map(([key, label]) => themeFieldInputRow(key, basicLabels[key] || label, values[key])).join("");
        fields.innerHTML = KfpsI18n.t("<div class=\"themeColorGrid\">{0}</div>\n      <details class=\"themeAdvanced\"><summary>More colors</summary><div class=\"themeColorGrid\">{1}</div></details>", rows(THEME_MAIN_FIELDS), rows(THEME_FIELDS.map(([key]) => key).filter(key => !THEME_MAIN_FIELDS.includes(key))));
        fields.querySelectorAll(".themeValueInput").forEach((input) => {
          input.addEventListener("input", () => {
            const key = input.dataset.themeVar;
            const valid = CSS.supports("color", input.value);
            input.setAttribute("aria-invalid", String(!valid));
            if (key && valid) document.documentElement.style.setProperty(key, input.value);
            const color = themeColorInput(fields, key);
            if (color && /^#[0-9a-f]{6}$/i.test(input.value)) color.value = input.value;
            syncDerivedThemeRgb(themeFieldCurrentValues());
            applyEditorThemePreviewRefresh();
            updateThemeContrastStatus();
          });
        });
        fields.querySelectorAll(".themeColorInput").forEach((input) => {
          input.addEventListener("input", () => {
            const key = input.dataset.themeColorFor;
            const text = themeFieldInput(fields, key);
            if (text) {
              text.value = input.value;
              text.dispatchEvent(new Event("input", { bubbles: true }));
            }
          });
        });
      }
      updateThemeContrastStatus();
    }

    function updateThemeContrastStatus() {
      const invalid = Boolean(view.element("themeAdjustFields")?.querySelector('[aria-invalid="true"]'));
      const values = themeFieldCurrentValues();
      const luminance = hex => {
        const rgb = hexToRgbString(hex);
        if (!rgb) return null;
        const linear = rgb.split(",").map(value => Number(value) / 255).map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
        return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
      };
      const ratios = ["--text", "--muted"].flatMap(text => ["--shell", "--panel", "--panel2", "--panel3", "--dialog-bg", "--dialog-header"].map(surface => {
        const a = luminance(values[text]), b = luminance(values[surface]);
        return a === null || b === null ? null : (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      }));
      const minimum = ratios.every(value => value !== null) ? Math.min(...ratios) : null;
      const status = view.element("themeAdjustStatus");
      if (status) {
        status.textContent = invalid ? KfpsI18n.t("Invalid color value") : minimum === null ? KfpsI18n.t("Text contrast: unavailable for these colors") : `${minimum < 4.5 ? KfpsI18n.t("Low text contrast") : KfpsI18n.t("Text contrast")}: ${minimum.toFixed(1)}:1`;
        status.dataset.warning = String(invalid || (minimum !== null && minimum < 4.5));
      }
      if (view.element("saveThemeAdjust")) view.element("saveThemeAdjust").disabled = themeAdjustSaving || invalid;
    }

    function previewThemeAdjustBase() {
      applyEditorTheme(view.element("themeAdjustBase").value, { persist: false, preview: true });
      renderThemeAdjustFields(themeFieldCurrentValues());
    }

    function openThemeAdjustDialog() {
      const dialog = view.element("themeAdjustDialog");
      if (!dialog || themeAdjustSaving || disposed) return;
      choiceRevision += 1;
      themeAdjustRestoreTheme = normalizeTheme(view.element("editorThemeSelect")?.value || settings.getItem("kloudyFabricTheme") || "pastel");
      const current = themeById(themeAdjustRestoreTheme);
      view.element("themeAdjustName").value = current.builtin ? KfpsI18n.t("{0} Custom", current.name) : current.name;
      view.element("themeAdjustBase").replaceChildren(...[...editorThemes.values()].map(theme => {
        const option = document.createElement("option");
        option.value = theme.id;
        option.textContent = theme.builtin ? KfpsI18n.t(theme.name) : theme.name;
        return option;
      }));
      view.element("themeAdjustBase").value = themeAdjustRestoreTheme;
      renderThemeAdjustFields(themeFieldCurrentValues());
      try {
        if (!dialog.open) dialog.showModal();
      } catch (_err) {
        dialog.setAttribute("open", "");
      }
    }

    function applyEditorThemePreviewRefresh() {
      if (!scene.canvas() || disposed) return;
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--fabric-canvas-bg").trim() || "#fffefe";
      scene.canvas().set("backgroundColor", bg);
      scene.styleControls();
      scene.grid();
      scene.canvas().requestRenderAll();
    }

    async function saveAdjustedTheme() {
      if (disposed || themeAdjustSaving || view.element("themeAdjustFields")?.querySelector('[aria-invalid="true"]')) return;
      const name = cleanName(view.element("themeAdjustName")?.value || "Custom Theme", "Custom Theme");
      const values = {};
      document.querySelectorAll(".themeValueInput[data-theme-var]").forEach((input) => {
        values[input.dataset.themeVar] = input.value;
      });
      themeAdjustSaving = true;
      const controls = view.element("themeAdjustDialog").querySelectorAll("input, select, button");
      controls.forEach(control => { control.disabled = true; });
      try {
        const data = await requestJson(endpoints.themes, {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify({ name, values, base: document.documentElement.dataset.editorThemeBase || "pastel" }),
        }, 30000);
        if (disposed) return;
        const theme = normalizeEntry(data.theme);
        if (!theme || theme.builtin) throw new Error(KfpsI18n.error("invalid editor theme"));
        catalogRevision += 1;
        editorThemes.set(theme.id, theme);
        themeAdjustRestoreTheme = null;
        applyEditorTheme(theme.id);
        present(() => view.element("themeAdjustDialog")?.close());
        present(() => view.status(KfpsI18n.t("Saved custom editor theme: {0}.", theme.name)));
      } catch (err) {
        present(() => view.error(KfpsI18n.t("Theme save failed"), err));
        present(() => view.status(KfpsI18n.t("Theme save failed: {0}", KfpsI18n.error(err.message || err))));
      } finally {
        themeAdjustSaving = false;
        if (!disposed) controls.forEach(control => { control.disabled = false; });
        present(updateThemeContrastStatus);
      }
    }

    function closeThemeAdjustDialog({ restore = true } = {}) {
      if (disposed || themeAdjustSaving) return;
      if (restore && themeAdjustRestoreTheme) applyEditorTheme(themeAdjustRestoreTheme, { persist: false });
      themeAdjustRestoreTheme = null;
      view.element("themeAdjustDialog")?.close();
    }
    return {
      initialize, dispose, applyEditorTheme, loadEditorThemes, loadEditorThemePreference,
      themeFieldCurrentValues, previewThemeAdjustBase, openThemeAdjustDialog, saveAdjustedTheme, closeThemeAdjustDialog,
      entries: Object.freeze({ has: id => editorThemes.has(id), keys: () => editorThemes.keys() }),
    };
  }
  return { create };
});
