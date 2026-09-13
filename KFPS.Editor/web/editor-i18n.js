/* KFPS editor localization: display text only; no artwork/data translation. */
(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.KfpsI18n = api;
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";
  const KEY = "kloudyFabricLanguage";
  let language = "en";
  let patterns = null;
  let knownMessages = null;
  const catalog = (code = language) => root.KfpsEditorLocales?.[code] || {};
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  function lookup(section, key, fallback = key) {
    const translated = catalog()[section]?.[key];
    const english = catalog("en")[section]?.[key];
    return typeof translated === "string" && translated.length ? translated
      : typeof english === "string" && english.length ? english : fallback;
  }
  const messageKeys = () => knownMessages ||= { ...catalog("en").messages, ...catalog().messages };
  const normalize = text => String(text).replace(/\s+/g, " ").trim();
  const escapeRegExp = text => String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // Replacement values are opaque. Do not translate or recursively format user names.
  function format(text, values) {
    return String(text).replace(/\{(\d+)\}/g, (match, index) => Number(index) < values.length ? String(values[Number(index)]) : match);
  }
  function t(source, ...values) {
    return format(lookup("messages", source), values);
  }
  function init(preferences) {
    let selected = null;
    try { selected = new URLSearchParams(root.location?.search || "").get("lang"); } catch (_) { /* Optional QA override. */ }
    if (!["en", "ko"].includes(selected)) {
      try { selected = (preferences || root.localStorage)?.getItem(KEY); } catch (_) { /* Browser storage can be disabled. */ }
    }
    if (!["en", "ko"].includes(selected)) selected = /^ko(?:-|_|$)/i.test(root.KfpsEditorSystemLanguage || root.navigator?.language || "") ? "ko" : "en";
    language = selected;
    patterns = null;
    knownMessages = null;
    if (root.document) root.document.documentElement.lang = language;
    return language;
  }
  function templatePatterns() {
    if (patterns) return patterns;
    patterns = Object.keys(messageKeys()).filter(key => /\{\d+\}/.test(key) && !/<[a-z]/i.test(key)).map(key => {
      let last = 0;
      const indexes = [];
      let expression = "^";
      for (const match of key.matchAll(/\{(\d+)\}/g)) {
        expression += escapeRegExp(key.slice(last, match.index)) + "([\\s\\S]*?)";
        indexes.push(Number(match[1]));
        last = match.index + match[0].length;
      }
      expression += escapeRegExp(key.slice(last)) + "$";
      return { key, indexes, regex: new RegExp(expression) };
    }).sort((a, b) => b.key.replace(/\{\d+\}/g, "").length - a.key.replace(/\{\d+\}/g, "").length);
    return patterns;
  }
  // For trusted backend diagnostic messages and generated history reasons only.
  // Never use this on arbitrary project, asset, layer, or theme names.
  function message(source, translateTerms = false) {
    const text = String(source ?? "");
    if (own(messageKeys(), text)) return t(text);
    for (const entry of templatePatterns()) {
      const match = entry.regex.exec(text);
      if (!match) continue;
      const values = [];
      entry.indexes.forEach((index, i) => { values[index] = translateTerms ? t(match[i + 1]) : match[i + 1]; });
      return t(entry.key, ...values);
    }
    return text; // Keep unknown technical diagnostics useful to developers.
  }
  function error(source) {
    const text = String(source ?? "");
    const lines = text.split("\n");
    const prefix = /^(\w*Error: )/.exec(lines[0]);
    lines[0] = prefix ? prefix[1] + message(lines[0].slice(prefix[1].length)) : message(lines[0]);
    return lines.join("\n");
  }
  function familyLabel(family) {
    return lookup("families", family, String(family).replaceAll("_", " "));
  }
  function shapeLabel(name) {
    return lookup("shapeLabels", name);
  }
  function applyStatic(document) {
    document.documentElement.lang = language;
    if (document.documentElement.dataset.kfpsLocalized) return;
    const messages = messageKeys();
    // Preserve an option's implicit value before translating its visible caption.
    document.querySelectorAll("option:not([value])").forEach(option => { option.value = option.textContent; });
    // Translate complete help paragraphs first so Korean sentence order is natural.
    document.querySelectorAll("p, li, h1, h2, h3, h4, label, summary").forEach(element => {
      if (element.closest("script, style, textarea")) return;
      const key = normalize(element.innerHTML);
      const translated = lookup("html", key);
      if (translated !== key) element.innerHTML = translated;
    });
    const walk = document.createTreeWalker(document.documentElement, 4);
    const nodes = [];
    while (walk.nextNode()) nodes.push(walk.currentNode);
    nodes.forEach(node => {
      if (node.parentElement?.closest("script, style, textarea, kbd, [data-shortcut-label], [data-language-name]")) return;
      const source = node.nodeValue;
      const key = normalize(source);
      if (own(messages, key)) node.nodeValue = source.match(/^\s*/)[0] + t(key) + source.match(/\s*$/)[0];
    });
    document.querySelectorAll("[title], [aria-label], [placeholder], [data-tool]").forEach(element => {
      ["title", "aria-label", "placeholder"].forEach(attribute => {
        const source = element.getAttribute(attribute);
        if (source !== null && own(messages, source)) element.setAttribute(attribute, t(source));
      });
      // data-tool is an internal mode identifier, not a caption: never change it.
    });
    document.documentElement.dataset.kfpsLocalized = language;
  }
  function recoveryPattern() {
    const keys = ["Recovery pending", "Recovery saved in KFPS", "Recovery saved in this browser only", "Recovery failed; save the project"];
    return new RegExp([...new Set(keys.flatMap(key => [key, t(key)]))].map(escapeRegExp).join("|"));
  }
  const api = Object.freeze({
    KEY, init, t, term: t, message, history: source => message(source, true), error, familyLabel, shapeLabel, applyStatic, recoveryPattern,
    get language() { return language; },
    get locale() { return language === "ko" ? "ko-KR" : "en-US"; },
  });
  init();
  return api;
});
