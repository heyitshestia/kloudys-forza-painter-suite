/* global fabric */
"use strict";

const FH6_BOUNDS = { left: -1000, top: -1000, width: 2000, height: 2000 };
const LEGACY_RECTANGLE_TYPES = new Set([1, 2]);
const LEGACY_ELLIPSE_TYPES = new Set([8, 16]);
const RECTANGLE_DIVISOR = 127.0;
const ELLIPSE_DIVISOR = 63.0;
const VINYL_RESOURCE_BASES = [
  "/tools/fabric-editor/Resources/Vinyls",
];
const STARTUP_HELP_CONFIRMED_KEY = "kloudyFabricStartupHelpConfirmed";
const STARTUP_HELP_CONFIRMED_API = "/api/fabric-editor/startup-help-confirmed";
const EDITOR_PREFS_API = "/api/fabric-editor/preferences";
const EDITOR_THEMES_API = "/api/fabric-editor/themes";
const EDITOR_AUTOSAVE_API = "/api/fabric-editor/autosave";
const JSON_BROWSER_API = "/api/fabric-editor/json-browser";
const JSON_FILE_API = "/api/fabric-editor/json-file";
const EDITOR_EXPORT_API = "/api/fabric-editor/save-editor-json";
const PROJECT_BROWSER_API = "/api/fabric-editor/project-browser";
const PROJECT_FILE_API = "/api/fabric-editor/project-file";
const PROJECT_SAVE_API = "/api/fabric-editor/save-project";
const PROJECT_OPEN_FOLDER_API = "/api/fabric-editor/open-project-folder";
const SHORTCUTS_KEY = "kloudyFabricShortcuts";
const OVERLAY_LAYER_MODE_KEY = "kloudyFabricOverlayLayerMode";
const AUTOSAVE_KEY = "kloudyFabricAutosave";
const TEXT_VINYL_FONT_KEY = "kloudyFabricTextVinylFont";
const TEXT_VINYL_CUSTOM_FONT_KEY = "kloudyFabricTextVinylCustomFont";
const VINYL_HIT_TOLERANCE = 0;
const PIXEL_ART_SQUARE_SIZE = 128.498032;

function isTextVinylHarnessRun() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    return params.has("harness") || params.has("textVinylHarness");
  } catch (_err) {
    return false;
  }
}

function startupProjectId() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    const project = (params.get("project") || "").trim();
    return project || "";
  } catch (_err) {
    return "";
  }
}

const DEFAULT_SHORTCUTS = {
  selectTool: "V",
  shapeLibrary: "S",
  dropper: "I",
  guides: "G",
  overlay: "O",
  sourceTool: "R",
  delete: "Delete",
  duplicate: "Ctrl+D",
  undo: "Ctrl+Z",
  redo: "Ctrl+Y",
  layerForward: "]",
  layerBackward: "[",
  flipVertical: "F",
  flipHorizontal: "Shift+F",
  makeMask: "M",
  axisLockX: "X",
  axisLockY: "Y",
  selectionLock: "Shift+L",
};

const BUILTIN_EDITOR_THEMES = [
  { id: "pastel", name: "Signature Pink", builtin: true, values: {} },
  { id: "dark", name: "Dark", builtin: true, values: {} },
];

const THEME_FIELDS = [
  ["--bg", "App background"],
  ["--shell", "Outer shell"],
  ["--panel", "Main panels"],
  ["--panel2", "Raised panels"],
  ["--panel3", "Inset panels"],
  ["--text", "Main text"],
  ["--muted", "Muted text"],
  ["--soft", "Soft labels"],
  ["--line", "Thin borders"],
  ["--line2", "Strong borders"],
  ["--accent", "Primary accent"],
  ["--accent2", "Secondary accent"],
  ["--good", "Success color"],
  ["--warn", "Warning color"],
  ["--danger", "Danger color"],
  ["--canvas-bg", "Canvas surround"],
  ["--fabric-canvas-bg", "Canvas color"],
  ["--editor-grid-line", "Grid lines"],
  ["--editor-grid-axis", "Grid axis"],
  ["--editor-guide-line", "Guide lines"],
  ["--editor-guide-selected", "Selected guide"],
  ["--editor-guide-draft", "Guide draft"],
  ["--editor-notch-line", "Rotation notch"],
  ["--editor-notch-muted", "Muted notch"],
  ["--editor-notch-active", "Active notch"],
  ["--editor-selection-border", "Selection border"],
  ["--editor-shape-outline", "Shape outline"],
  ["--editor-selection-corner", "Transform handles"],
  ["--editor-selection-corner-stroke", "Handle stroke"],
  ["--editor-skew-corner", "Skew handle"],
  ["--shape-tile-bg", "Shape tile background"],
  ["--dialog-bg", "Dialog background"],
  ["--dialog-header", "Dialog header"],
];

const SHORTCUT_LABELS = {
  selectTool: "Select / Move",
  shapeLibrary: "Shape Library",
  dropper: "Eyedropper",
  guides: "Guides / Snap",
  overlay: "Overlay / Reference",
  sourceTool: "Source Move",
  delete: "Delete selected",
  duplicate: "Duplicate selected",
  undo: "Undo",
  redo: "Redo",
  layerForward: "Layer forward",
  layerBackward: "Layer backward",
  flipVertical: "Flip vertical",
  flipHorizontal: "Flip horizontal",
  makeMask: "Toggle mask layer",
  axisLockX: "Drag lock X axis",
  axisLockY: "Drag lock Y axis",
  selectionLock: "Lock current selection",
};

const VINYL_TYPE_BASES = {
  Primitives: 1048677,
  Community_Vinyls_1: 1050677,
  Community_Vinyls_2: 1050777,
  Community_Vinyls_3: 1050877,
  Community_Vinyls_4: 1050977,
  Gradient_Shapes: 1048777,
  Stripes: 1048877,
  Tears: 1048977,
  Racing_Icons: 1049077,
  Flames: 1049177,
  Paint_Splats: 1049277,
  Tribal: 1049377,
  Nature: 1049477,
  Upper_Letters_1: 1050477,
  Lower_Letters_1: 1050577,
  Upper_Letters_2: 1049877,
  Lower_Letters_2: 1049977,
  Upper_Letters_3: 1050077,
  Lower_Letters_3: 1050177,
  Upper_Letters_4: 1050277,
  Lower_Letters_4: 1050377,
  Upper_Letters_5: 1051077,
  Lower_Letters_5: 1051177,
  Upper_Letters_6: 1051277,
  Lower_Letters_6: 1051377,
  Upper_Letters_7: 1051477,
  Lower_Letters_7: 1051577,
  Upper_Letters_8: 1051677,
  Lower_Letters_8: 1051777,
  Upper_Letters_9: 1051877,
  Lower_Letters_9: 1051977,
  Upper_Letters_10: 1052077,
  Lower_Letters_10: 1052177,
  Upper_Letters_11: 1052277,
  Lower_Letters_11: 1052377,
};
const GRADIENT_RESOURCE_SLOTS = {
  Gradient_Shapes: Array.from({ length: 40 }, (_value, index) => index + 1),
  Community_Vinyls_1: [8, 20, 40],
  Community_Vinyls_2: [1, 2, 3, 4, 9, 11, 12, 13, 14, 19, 21, 22, 23, 24, 31, 32, 33, 34, 40],
  Community_Vinyls_4: [1, 2, 3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 25, 26, 27, 31, 32, 33, 34, 35, 36, 37, 40],
  Stripes: [23],
};
const GRADIENT_SHAPE_WORDS = new Set(
  Object.entries(GRADIENT_RESOURCE_SLOTS).flatMap(([family, slots]) => (
    slots.map((index) => resourceToShapeWord(family, index))
  ))
);

const FAMILY_ORDER = Object.keys(VINYL_TYPE_BASES);
const FAVORITE_COLOR_SLOTS = 16;
const resourceCache = new Map();
const resourceOutlineCache = new Map();
const textVinylMeshCache = new Map();
let canvas;
let isPanning = false;
let lastPan = null;
let loadedName = "untitled";
let currentProjectName = null;
let overlayImage = null;
let history = [];
let historyIndex = -1;
let historyLocked = false;
let protectedHistoryIndex = -1;
let showFavoritesOnly = false;
let favorites = loadFavoriteShapes();
let shapeNames = { families: {} };
let shapeWords = { families: {} };
let rememberedColor = [255, 255, 255, 255];
let favoriteColors = loadFavoriteColors();
let selectedFavoriteColorSlot = 0;
let editorThemes = new Map(BUILTIN_EDITOR_THEMES.map((theme) => [theme.id, theme]));
let themeAdjustRestoreTheme = null;
let shapeEyedropperActive = false;
let activeToolMode = "select";
let overlaySampler = null;
let layeredOverlayState = null;
let overlaySourceState = null;
let liveOverlayColorFrame = null;
let resolvedResourceBase = localStorage.getItem("kloudyFabricResourceBase") || null;
let collapsedLayerGroups = new Set();
let dropperPreservedActiveObject = null;
let guideState = defaultGuideState();
let guideDraft = null;
let selectedGuideId = null;
let guideRenderQueued = false;
let lastSnapMessageAt = 0;
let snapOverlayObjects = [];
let transformAnchorSnapshot = null;
let reuseLastFontSize = localStorage.getItem("kloudyFabricReuseLastFontSize") === "true";
let lastFontShapeTransform = loadLastFontShapeTransform();
let selectedShapeOutlineObjects = new Set();
let selectedShapeOutlineHelpers = new Map();
let selectionInvertLocked = false;
let dragAxisLock = null;
let dragAxisSnapshot = null;
let selectionLockActive = false;
let selectionLockObjects = [];
let selectionLockRestoring = false;
let pendingDialogColor = null;
let dialogColorFrame = null;
let vBoxSelectActive = false;
let shortcuts = loadShortcuts();
let overlayLayerMode = normalizeOverlayLayerMode(localStorage.getItem(OVERLAY_LAYER_MODE_KEY));
let maskPreviewOutlines = new Map();
let maskPreviewCutouts = new Map();
let layerListRows = new Map();
let lastLayerListKey = null;
let layerDragState = null;
let layerDragGhost = null;
let suppressLayerClick = false;
let nextLayerListObjectId = 1;
let layerRefreshFrame = null;
let canvasRenderFrame = null;
let canvasGeometryFrame = null;
let visualGridFrame = null;
let hudUpdateFrame = null;
let pendingHudPointer = null;
let pendingHudTarget = null;
let pendingHudText = null;
let layerStatsCache = null;
let autosaveWriteTimer = null;
let pendingAutosavePayload = null;
let recoveryAutosavePayload = null;
let canvasResizeObserver = null;
let lastCanvasSize = { width: 0, height: 0 };
let jsonBrowserState = {
  source: "generated",
  groups: [],
  selectedGroupIndex: -1,
  selectedEntryIndex: -1,
  loading: false,
};
let projectBrowserState = {
  entries: [],
  selectedIndex: -1,
  loading: false,
};
let pendingGlobalShapeReplacement = null;
let exportSaveInProgress = false;
let projectSaveInProgress = false;
let toastTimer = null;
let pixelArtSourceFile = null;
let editorTourState = null;
const TEXT_VINYL_SOURCE_FLAG = "kfps_text_vinyl";

try {
  const savedColor = JSON.parse(localStorage.getItem("kloudyFabricLastColor") || "null");
  if (Array.isArray(savedColor) && savedColor.length >= 3) rememberedColor = savedColor;
} catch (_err) {
  rememberedColor = [255, 255, 255, 255];
}

function $(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function setHidden(id, hidden) {
  const el = $(id);
  if (el) el.hidden = hidden;
}

function normalizeShortcutKey(key) {
  const raw = String(key || "").trim();
  if (!raw) return "";
  const lower = raw.toLowerCase();
  const aliases = {
    " ": "Space",
    spacebar: "Space",
    esc: "Escape",
    del: "Delete",
    return: "Enter",
    arrowleft: "ArrowLeft",
    arrowright: "ArrowRight",
    arrowup: "ArrowUp",
    arrowdown: "ArrowDown",
    backspace: "Backspace",
    delete: "Delete",
    tab: "Tab",
    enter: "Enter",
    escape: "Escape",
  };
  if (aliases[lower]) return aliases[lower];
  if (raw.length === 1) return raw.toUpperCase();
  return raw[0].toUpperCase() + raw.slice(1);
}

function normalizeShortcutCombo(value) {
  const parts = String(value || "").split("+").map((part) => part.trim()).filter(Boolean);
  const modifiers = new Set();
  let key = "";
  parts.forEach((part) => {
    const lower = part.toLowerCase();
    if (lower === "ctrl" || lower === "control") modifiers.add("Ctrl");
    else if (lower === "shift") modifiers.add("Shift");
    else if (lower === "alt" || lower === "option") modifiers.add("Alt");
    else if (lower === "meta" || lower === "cmd" || lower === "command") modifiers.add("Meta");
    else key = normalizeShortcutKey(part);
  });
  if (!key) return "";
  return [...["Ctrl", "Shift", "Alt", "Meta"].filter((mod) => modifiers.has(mod)), key].join("+");
}

function eventToShortcutCombo(event) {
  const key = normalizeShortcutKey(event.key);
  if (!key || ["Control", "Shift", "Alt", "Meta"].includes(key)) return "";
  const parts = [];
  if (event.ctrlKey) parts.push("Ctrl");
  if (event.shiftKey) parts.push("Shift");
  if (event.altKey) parts.push("Alt");
  if (event.metaKey) parts.push("Meta");
  parts.push(key);
  return parts.join("+");
}

function loadShortcuts() {
  try {
    const saved = JSON.parse(localStorage.getItem(SHORTCUTS_KEY) || "{}");
    const merged = { ...DEFAULT_SHORTCUTS };
    Object.keys(DEFAULT_SHORTCUTS).forEach((action) => {
      const combo = normalizeShortcutCombo(saved[action]);
      if (combo) merged[action] = combo;
    });
    return merged;
  } catch (_err) {
    return { ...DEFAULT_SHORTCUTS };
  }
}

function saveShortcuts() {
  localStorage.setItem(SHORTCUTS_KEY, JSON.stringify(shortcuts));
}

function shortcutFor(action) {
  return normalizeShortcutCombo(shortcuts[action] || DEFAULT_SHORTCUTS[action]);
}

function shortcutMatches(event, action) {
  return eventToShortcutCombo(event) === shortcutFor(action);
}

function shortcutPrimaryKey(action) {
  const combo = shortcutFor(action);
  return combo.split("+").pop() || "";
}

function resetShortcuts() {
  shortcuts = { ...DEFAULT_SHORTCUTS };
  saveShortcuts();
  renderShortcutEditor();
  updateShortcutLabels();
  setStatus("Editor shortcuts reset to defaults.");
}

function setShortcut(action, combo) {
  const normalized = normalizeShortcutCombo(combo);
  if (!normalized || !DEFAULT_SHORTCUTS[action]) return;
  shortcuts[action] = normalized;
  saveShortcuts();
  renderShortcutEditor();
  updateShortcutLabels();
  setStatus(`${SHORTCUT_LABELS[action] || action} shortcut set to ${normalized}.`);
}

function updateShortcutLabels() {
  document.querySelectorAll("[data-shortcut-label]").forEach((el) => {
    const action = el.dataset.shortcutLabel;
    if (action) el.textContent = shortcutFor(action);
  });
  const toolMap = {
    selectTool: "v",
    shapeLibrary: "s",
    dropper: "i",
    guides: "g",
    overlay: "o",
  };
  Object.entries(toolMap).forEach(([action, toolKey]) => {
    const button = document.querySelector(`.toolButton[data-tool-key="${toolKey}"]`);
    if (button?.firstChild) button.firstChild.nodeValue = shortcutFor(action);
  });
  const maskButton = $("maskSelectedTool");
  if (maskButton?.firstChild) maskButton.firstChild.nodeValue = shortcutFor("makeMask");
}

function renderShortcutEditor() {
  const list = $("shortcutEditorList");
  if (!list) return;
  list.innerHTML = "";
  Object.keys(DEFAULT_SHORTCUTS).forEach((action) => {
    const row = document.createElement("label");
    row.className = "shortcutEditRow";
    row.innerHTML = `
      <span>${escapeHtml(SHORTCUT_LABELS[action] || action)}</span>
      <input class="shortcutCapture" data-shortcut-action="${escapeHtml(action)}" readonly value="${escapeHtml(shortcutFor(action))}" title="Click, then press a new shortcut.">
    `;
    const input = row.querySelector("input");
    input.addEventListener("focus", () => {
      input.classList.add("capturing");
      input.value = "Press keys...";
    });
    input.addEventListener("blur", () => {
      input.classList.remove("capturing");
      input.value = shortcutFor(action);
    });
    input.addEventListener("keydown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.key === "Escape") {
        input.blur();
        return;
      }
      const combo = eventToShortcutCombo(event);
      if (!combo) return;
      setShortcut(action, combo);
      input.blur();
    });
    list.appendChild(row);
  });
}

function normalizeOverlayLayerMode(value) {
  return value === "above" ? "above" : "below";
}

function clampOverlayScalePercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 100;
  return Math.max(10, Math.min(400, Math.round(number)));
}

function syncOverlayScaleControls(value) {
  const percent = clampOverlayScalePercent(value);
  if ($("overlayScale")) $("overlayScale").value = String(percent);
  if ($("overlayScalePercent")) $("overlayScalePercent").value = String(percent);
  return percent;
}

function defaultGuideState() {
  return {
    gridEnabled: false,
    gridSize: 50,
    gridOpacity: 20,
    guidesVisible: true,
    snapGuides: true,
    snapGrid: true,
    snapCtrlOnly: true,
    snapThreshold: 12,
    guideConstraint: "free",
    snapGuideAnchor: false,
    snapGuideEnd: false,
    guides: [],
  };
}

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
  const select = $("editorThemeSelect");
  if (!select) return;
  const current = selectedTheme || select.value || "pastel";
  select.innerHTML = "";
  [...editorThemes.values()].forEach((theme) => {
    const option = document.createElement("option");
    option.value = theme.id;
    option.textContent = theme.builtin ? theme.name : `${theme.name} (Custom)`;
    select.appendChild(option);
  });
  select.value = normalizeTheme(current);
}

function saveEditorThemePreference(theme) {
  fetch(EDITOR_PREFS_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ theme: normalizeTheme(theme) }),
  }).catch(() => {
    // Direct-file launches or blocked local server writes still keep localStorage.
  });
}

function applyEditorTheme(theme, options = {}) {
  const safeTheme = normalizeTheme(theme);
  const entry = themeById(safeTheme);
  if (entry.builtin) {
    clearCustomThemeProperties();
    document.documentElement.dataset.editorTheme = safeTheme;
  } else {
    document.documentElement.dataset.editorTheme = "custom";
    applyCustomThemeValues(entry.values || {});
  }
  localStorage.setItem("kloudyFabricTheme", safeTheme);
  if (options.persist !== false) saveEditorThemePreference(safeTheme);
  populateEditorThemeSelect(safeTheme);
  if (canvas) {
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--fabric-canvas-bg").trim() || "#fffefe";
    canvas.set("backgroundColor", bg);
    styleAllTransformControls();
    updateVisualGridLayer();
    canvas.requestRenderAll();
  }
}

async function loadEditorThemes() {
  editorThemes = new Map(BUILTIN_EDITOR_THEMES.map((theme) => [theme.id, theme]));
  try {
    const response = await fetch(EDITOR_THEMES_API, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      (Array.isArray(data.themes) ? data.themes : []).forEach((theme) => {
        if (!theme?.id) return;
        editorThemes.set(String(theme.id), {
          id: String(theme.id),
          name: String(theme.name || theme.id),
          builtin: Boolean(theme.builtin),
          values: theme.values && typeof theme.values === "object" ? theme.values : {},
        });
      });
    }
  } catch (_err) {
    // Direct-file/browser fallback keeps built-in themes only.
  }
  populateEditorThemeSelect(localStorage.getItem("kloudyFabricTheme") || "pastel");
}

async function loadEditorThemePreference() {
  try {
    const response = await fetch(EDITOR_PREFS_API, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      if (data.theme) {
        applyEditorTheme(data.theme, { persist: false });
        return data.theme;
      }
    }
  } catch (_err) {
    // Direct-file/browser fallback.
  }
  return null;
}

function themeFieldInputRow(key, label, value) {
  const safeValue = String(value || "");
  const isHex = /^#[0-9a-f]{6}$/i.test(safeValue);
  return `
    <label class="themeAdjustRow">
      <span>${escapeHtml(label)}</span>
      <input class="themeValueInput" data-theme-var="${escapeHtml(key)}" value="${escapeHtml(safeValue)}" spellcheck="false">
      ${isHex ? `<input class="themeColorInput" type="color" value="${escapeHtml(safeValue)}" data-theme-color-for="${escapeHtml(key)}">` : ""}
    </label>
  `;
}

function themeFieldInput(fields, key) {
  return [...(fields?.querySelectorAll(".themeValueInput") || [])].find((input) => input.dataset.themeVar === key) || null;
}

function themeColorInput(fields, key) {
  return [...(fields?.querySelectorAll(".themeColorInput") || [])].find((input) => input.dataset.themeColorFor === key) || null;
}

function openThemeAdjustDialog() {
  const dialog = $("themeAdjustDialog");
  if (!dialog) return;
  themeAdjustRestoreTheme = normalizeTheme($("editorThemeSelect")?.value || localStorage.getItem("kloudyFabricTheme") || "pastel");
  const current = themeById(themeAdjustRestoreTheme);
  const values = themeFieldCurrentValues();
  const nameInput = $("themeAdjustName");
  if (nameInput) nameInput.value = current.builtin ? `${current.name} Custom` : current.name;
  const fields = $("themeAdjustFields");
  if (fields) {
    fields.innerHTML = THEME_FIELDS
      .map(([key, label]) => themeFieldInputRow(key, label, values[key]))
      .join("");
    fields.querySelectorAll(".themeValueInput").forEach((input) => {
      input.addEventListener("input", () => {
        const key = input.dataset.themeVar;
        if (key) document.documentElement.style.setProperty(key, input.value);
        const color = themeColorInput(fields, key);
        if (color && /^#[0-9a-f]{6}$/i.test(input.value)) color.value = input.value;
        syncDerivedThemeRgb(themeFieldCurrentValues());
        applyEditorThemePreviewRefresh();
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
  try {
    if (!dialog.open) dialog.showModal();
  } catch (_err) {
    dialog.setAttribute("open", "");
  }
}

function applyEditorThemePreviewRefresh() {
  if (!canvas) return;
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--fabric-canvas-bg").trim() || "#fffefe";
  canvas.set("backgroundColor", bg);
  styleAllTransformControls();
  updateVisualGridLayer();
  canvas.requestRenderAll();
}

async function saveAdjustedTheme() {
  const name = cleanProjectBaseName($("themeAdjustName")?.value || "Custom Theme", "Custom Theme");
  const values = {};
  document.querySelectorAll(".themeValueInput[data-theme-var]").forEach((input) => {
    values[input.dataset.themeVar] = input.value;
  });
  const saveButton = $("saveThemeAdjust");
  if (saveButton) saveButton.disabled = true;
  try {
    const response = await fetch(EDITOR_THEMES_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, values }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    await loadEditorThemes();
    const themeId = data.theme?.id;
    if (themeId) applyEditorTheme(themeId);
    themeAdjustRestoreTheme = null;
    $("themeAdjustDialog")?.close();
    setStatus(`Saved custom editor theme: ${data.theme?.name || name}.`);
  } catch (err) {
    showError("Theme save failed", err);
    setStatus(`Theme save failed: ${err.message || err}`);
  } finally {
    if (saveButton) saveButton.disabled = false;
  }
}

function closeThemeAdjustDialog({ restore = true } = {}) {
  if (restore && themeAdjustRestoreTheme) applyEditorTheme(themeAdjustRestoreTheme, { persist: false });
  themeAdjustRestoreTheme = null;
  $("themeAdjustDialog")?.close();
}

function cssColorVar(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function positiveModulo(value, divisor) {
  if (!Number.isFinite(divisor) || divisor <= 0) return 0;
  return ((value % divisor) + divisor) % divisor;
}

function colorWithAlpha(color, alpha) {
  const safeAlpha = Math.max(0, Math.min(1, Number(alpha)));
  const rgba = String(color || "").match(/^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)$/i);
  if (rgba) {
    return `rgba(${Number(rgba[1])}, ${Number(rgba[2])}, ${Number(rgba[3])}, ${safeAlpha})`;
  }
  const hex = String(color || "").trim().match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const raw = hex[1];
    return `rgba(${parseInt(raw.slice(0, 2), 16)}, ${parseInt(raw.slice(2, 4), 16)}, ${parseInt(raw.slice(4, 6), 16)}, ${safeAlpha})`;
  }
  return color || `rgba(0, 0, 0, ${safeAlpha})`;
}

function isGradientResource(resource) {
  if (!resource?.family || !resource?.index) return false;
  const explicitWord = Number(resource.shapeWord);
  const shapeWord = Number.isFinite(explicitWord)
    ? (explicitWord & 0xffff)
    : resourceToShapeWord(resource.family, resource.index);
  if (GRADIENT_SHAPE_WORDS.has(shapeWord)) return true;
  const name = shapeNames?.families?.[resource.family]?.[String(resource.index)] || "";
  return /\b(gradient|shadow|faded)\b/i.test(String(name));
}

function isGradientObject(object) {
  const meta = object?.kloudy;
  if (!meta?.resource_family || !meta?.resource_index) return false;
  return isGradientResource({
    family: meta.resource_family,
    index: Number(meta.resource_index),
    shapeWord: Number(meta.type_word),
  });
}

function applyObjectColor(object, color) {
  if (!object) return;
  const normalized = normalizeColor(color);
  const hex = colorToHex(normalized);
  if (object.kloudy?.mask) {
    object.kloudy.maskOriginalColor = normalized.slice();
    object.set({ fill: hex, opacity: normalized[3] / 255 });
    applyMaskVisual(object);
    return;
  }
  object.set({ fill: hex, opacity: normalized[3] / 255 });
  if (isGradientObject(object) && fabric?.Image?.filters?.BlendColor) {
    object.filters = [new fabric.Image.filters.BlendColor({
      color: hex,
      mode: "tint",
      alpha: 1,
    })];
    object.applyFilters();
  }
}

function editorTransformColors() {
  return {
    border: cssColorVar("--editor-selection-border", "#2b1622"),
    corner: cssColorVar("--editor-selection-corner", "#ffffff"),
    cornerStroke: cssColorVar("--editor-selection-corner-stroke", "#2b1622"),
    skewCorner: cssColorVar("--editor-skew-corner", "#ec6fa4"),
  };
}

function editorVisualScaleForZoom(zoom = canvas?.getZoom?.() || 1) {
  const z = Math.max(0.001, Number(zoom) || 1);
  if (z <= 1.25) return 1;
  return Math.max(0.5, 1 / (1 + (z - 1.25) * 0.22));
}

function editorVisualScaleForObject(object) {
  return editorVisualScaleForZoom(object?.canvas?.getZoom?.() || canvas?.getZoom?.() || 1);
}

function editorBorderWidthForZoom(zoom = canvas?.getZoom?.() || 1) {
  const visualScale = editorVisualScaleForZoom(zoom);
  return Math.max(1.15, 1.15 + 0.85 * visualScale);
}

function styleObjectTransformControls(object) {
  if (!object) return;
  const colors = editorTransformColors();
  const visualScale = editorVisualScaleForObject(object);
  const borderWidth = editorBorderWidthForZoom(object?.canvas?.getZoom?.() || canvas?.getZoom?.() || 1);
  const singleShapeGap = 2.0;
  const isMultiSelection = object.type === "activeSelection" || object.type === "activeselection";
  object.set({
    borderColor: isMultiSelection ? colors.border : "rgba(0,0,0,0)",
    cornerColor: colors.corner,
    cornerStrokeColor: colors.cornerStroke,
    cornerStyle: "rect",
    transparentCorners: false,
    cornerSize: Math.max(9, 16 * visualScale),
    touchCornerSize: 56,
    borderScaleFactor: isMultiSelection ? borderWidth : 1,
    padding: isMultiSelection ? Math.max(7, 12 * visualScale) : borderWidth / 2 + singleShapeGap * visualScale,
  });
}

function figmaControlSmallFactor(object) {
  const zoom = Math.max(0.001, object?.canvas?.getZoom?.() || canvas?.getZoom?.() || 1);
  const screenWidth = Math.abs((object?.getScaledWidth?.() || 0) * zoom);
  const screenHeight = Math.abs((object?.getScaledHeight?.() || 0) * zoom);
  const smallX = Math.max(0, Math.min(1, (96 - screenWidth) / 96));
  const smallY = Math.max(0, Math.min(1, (96 - screenHeight) / 96));
  return Math.max(smallX, smallY);
}

function figmaControlPushDistance(name, object) {
  const small = figmaControlSmallFactor(object);
  const visualScale = editorVisualScaleForObject(object);
  switch (name) {
    case "tl":
    case "tr":
    case "bl":
    case "br":
      return (11 + 21 * small) * visualScale;
    case "ml":
    case "mr":
    case "mt":
    case "mb":
      return (9 + 22 * small) * visualScale;
    case "mtr":
      return (46 + 24 * small) * visualScale;
    default:
      return 0;
  }
}

function fallbackControlVector(name, fabricObject) {
  const angle = fabric.util.degreesToRadians(Number(fabricObject?.angle) || 0);
  const axisX = { x: Math.cos(angle), y: Math.sin(angle) };
  const axisY = { x: -Math.sin(angle), y: Math.cos(angle) };
  switch (name) {
    case "tl":
      return { x: -axisX.x - axisY.x, y: -axisX.y - axisY.y };
    case "tr":
      return { x: axisX.x - axisY.x, y: axisX.y - axisY.y };
    case "bl":
      return { x: -axisX.x + axisY.x, y: -axisX.y + axisY.y };
    case "br":
      return { x: axisX.x + axisY.x, y: axisX.y + axisY.y };
    case "ml":
      return { x: -axisX.x, y: -axisX.y };
    case "mr":
      return axisX;
    case "mt":
    case "mtr":
      return { x: -axisY.x, y: -axisY.y };
    case "mb":
      return axisY;
    default:
      return { x: 0, y: -1 };
  }
}

function normalizedControlVector(name, point, center, fabricObject) {
  let dx = point.x - center.x;
  let dy = point.y - center.y;
  let length = Math.hypot(dx, dy);
  if (length < 0.01) {
    const fallback = fallbackControlVector(name, fabricObject);
    dx = fallback.x;
    dy = fallback.y;
    length = Math.hypot(dx, dy) || 1;
  }
  return { x: dx / length, y: dy / length };
}

function figmaControlPositionHandler(name) {
  return function positionHandler(dim, finalMatrix, fabricObject, control) {
    const activeControl = control || this || {};
    const point = fabric.util.transformPoint(
      new fabric.Point((activeControl.x || 0) * dim.x, (activeControl.y || 0) * dim.y),
      finalMatrix
    );
    const center = fabric.util.transformPoint(new fabric.Point(0, 0), finalMatrix);
    const vector = normalizedControlVector(name, point, center, fabricObject);
    const push = figmaControlPushDistance(name, fabricObject);
    return new fabric.Point(point.x + vector.x * push, point.y + vector.y * push);
  };
}

function figmaRotatePositionHandler(dim, finalMatrix, fabricObject) {
  const halfX = dim.x * 0.5;
  const halfY = dim.y * 0.5;
  const points = [
    new fabric.Point(-halfX, -halfY),
    new fabric.Point(halfX, -halfY),
    new fabric.Point(halfX, halfY),
    new fabric.Point(-halfX, halfY),
  ].map((point) => fabric.util.transformPoint(point, finalMatrix));
  const minY = Math.min(...points.map((point) => point.y));
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const topPoints = points.filter((point) => Math.abs(point.y - minY) < 2.5);
  const x = topPoints.length
    ? topPoints.reduce((sum, point) => sum + point.x, 0) / topPoints.length
    : (minX + maxX) / 2;
  return new fabric.Point(x, minY - figmaControlPushDistance("mtr", fabricObject));
}

function rgbFromCssColor(color) {
  const value = String(color || "").trim();
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hex) {
    const raw = hex[1].length === 3
      ? hex[1].split("").map((ch) => ch + ch).join("")
      : hex[1];
    return [
      parseInt(raw.slice(0, 2), 16),
      parseInt(raw.slice(2, 4), 16),
      parseInt(raw.slice(4, 6), 16),
    ];
  }
  const rgba = value.match(/^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)/i);
  if (rgba) return [Number(rgba[1]), Number(rgba[2]), Number(rgba[3])].map((v) => Math.max(0, Math.min(255, Math.round(v || 0))));
  return null;
}

function colorLuminance(rgb) {
  if (!rgb) return 1;
  const [r, g, b] = rgb.map((v) => {
    const c = Math.max(0, Math.min(255, Number(v) || 0)) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function selectedShapeHalo(object) {
  const rgb = rgbFromCssColor(object?.fill);
  const luminance = colorLuminance(rgb);
  const opacity = Number(object?.opacity ?? 1);
  const darkShape = luminance < 0.36 || opacity < 0.35;
  return {
    color: darkShape ? "rgba(255, 255, 255, 0.98)" : "rgba(18, 12, 18, 0.92)",
    blur: darkShape ? 13 : 10,
  };
}

function restoreSelectionOutline(object) {
  const original = object?.__kloudySelectionOutline;
  if (!object || !original) return;
  object.set({
    shadow: original.shadow || null,
  });
  delete object.__kloudySelectionOutline;
  object.dirty = true;
}

function storeSelectionOutlineOriginal(object) {
  if (!object || object.__kloudySelectionOutline) return;
  object.__kloudySelectionOutline = {
    shadow: object.shadow || null,
  };
}

function makeSelectionOutlineHelper(object) {
  const helper = object?.kloudy?.outline_path
    ? new fabric.Path(object.kloudy.outline_path, { originX: "center", originY: "center" })
    : new fabric.Rect({
      originX: "center",
      originY: "center",
      width: Math.max(1, Number(object?.width) || 1),
      height: Math.max(1, Number(object?.height) || 1),
    });
  const clipPath = object?.kloudy?.mesh_path
    ? new fabric.Path(object.kloudy.mesh_path, { originX: "center", originY: "center" })
    : new fabric.Rect({
      originX: "center",
      originY: "center",
      width: Math.max(1, Number(object?.width) || 1),
      height: Math.max(1, Number(object?.height) || 1),
    });
  clipPath.set({
    fill: "#000",
    stroke: null,
    strokeWidth: 0,
    selectable: false,
    evented: false,
    objectCaching: false,
  });
  helper.set({
    fill: "rgba(0,0,0,0)",
    opacity: 1,
    stroke: selectedShapeHalo(object).color,
    strokeWidth: 3,
    strokeLineJoin: "round",
    strokeLineCap: "round",
    strokeUniform: true,
    selectable: false,
    evented: false,
    excludeFromExport: true,
    objectCaching: false,
    globalCompositeOperation: "source-over",
    clipPath,
  });
  helper.kloudySelectionOutlineHelper = true;
  helper.kloudySelectionOutlineOwner = object;
  return helper;
}

function selectionOutlineScaledValue(objectScale) {
  const scale = Number(objectScale) || 1;
  const sign = scale < 0 ? -1 : 1;
  const absoluteScale = Math.max(0.000001, Math.abs(scale));
  // The selected rim is clipped by the shape itself, so it must not be expanded.
  return sign * absoluteScale;
}

function syncSelectionOutlineHelper(object, helper) {
  if (!object || !helper) return;
  const zoom = Math.max(0.001, canvas?.getZoom?.() || 1);
  const strokeWidth = Math.max(1.25, 1.25 + 1.25 * editorVisualScaleForZoom(zoom));
  helper.set({
    left: object.left,
    top: object.top,
    scaleX: selectionOutlineScaledValue(object.scaleX),
    scaleY: selectionOutlineScaledValue(object.scaleY),
    angle: object.angle,
    skewX: object.skewX,
    skewY: object.skewY,
    flipX: object.flipX,
    flipY: object.flipY,
    visible: object.visible !== false,
    stroke: selectedShapeHalo(object).color,
    strokeWidth,
  });
  helper.setCoords();
}

function syncSelectionOutlineHelpers(selectedSet) {
  if (!canvas) return;
  selectedShapeOutlineHelpers.forEach((helper, object) => {
    if (!selectedSet.has(object) || !canvas.getObjects().includes(object)) {
      canvas.remove(helper);
      selectedShapeOutlineHelpers.delete(object);
    }
  });
  selectedSet.forEach((object) => {
    let helper = selectedShapeOutlineHelpers.get(object);
    if (!helper) {
      helper = makeSelectionOutlineHelper(object);
      selectedShapeOutlineHelpers.set(object, helper);
      canvas.add(helper);
    }
    syncSelectionOutlineHelper(object, helper);
    const objectIndex = canvas.getObjects().indexOf(object);
    if (objectIndex >= 0) helper.moveTo(objectIndex + 1);
  });
}

function syncSelectedShapeOutlines(selected = selectedVinylObjects(), options = {}) {
  if (!canvas) return;
  const selectable = selected.filter((obj) => obj?.kloudy && !obj.kloudyGuide);
  // Fabric moves ActiveSelection wrappers before committing child coordinates.
  // Per-shape helper outlines drift during that phase, so only use them for a
  // single selected shape and let Fabric's selection box represent multi-selects.
  const next = new Set(selectable.length === 1 ? selectable : []);
  selectedShapeOutlineObjects.forEach((obj) => {
    if (!next.has(obj)) restoreSelectionOutline(obj);
  });
  next.forEach((obj) => {
    storeSelectionOutlineOriginal(obj);
    // Fabric shadows are extremely expensive on complex vinyl paths while
    // panning or dragging. Keep selection indication on the transform box.
    obj.set({
      shadow: null,
    });
    obj.dirty = true;
  });
  selectedShapeOutlineObjects = next;
  syncSelectionOutlineHelpers(next);
  if (options.relayer !== false) bringGuidesToBack();
  requestCanvasRender();
}

function styledActiveSelection(objects) {
  const selection = new fabric.ActiveSelection(objects, { canvas });
  styleObjectTransformControls(selection);
  return selection;
}

function styleAllTransformControls() {
  if (!canvas) return;
  canvas.getObjects().forEach(styleObjectTransformControls);
  const active = canvas.getActiveObject();
  if (active) styleObjectTransformControls(active);
}

function styleActiveTransformControls() {
  if (!canvas) return;
  const active = canvas.getActiveObject();
  if (active) styleObjectTransformControls(active);
}

function editorCornerTransformHandler(eventData, transform, x, y) {
  if (!eventData?.shiftKey && fabric?.controlsUtils?.scalingEqually) {
    return fabric.controlsUtils.scalingEqually(eventData, transform, x, y);
  }
  if (!fabric?.controlsUtils?.skewHandlerX) return false;
  return fabric.controlsUtils.skewHandlerX(eventData, transform, x, y);
}

function editorCornerTransformActionName(eventData) {
  return eventData?.shiftKey ? "skewX" : "scale";
}

function editorCornerTransformCursorStyleHandler(eventData, control) {
  if (!eventData?.shiftKey) return "nwse-resize";
  return control?.x === control?.y ? "nesw-resize" : "nwse-resize";
}

function editorSideScaleCursorStyleHandler(_eventData, control) {
  return control?.x ? "ew-resize" : "ns-resize";
}

function roundedRectPath(ctx, x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, Math.abs(width) / 2, Math.abs(height) / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function shapeLockedControlRenderTransform(ctx, left, top, fabricObject) {
  ctx.translate(left, top);
  const angle = Number(fabricObject?.angle) || 0;
  if (angle) ctx.rotate(fabric.util.degreesToRadians(angle));
}

function renderFigmaCornerControl(ctx, left, top, styleOverride, fabricObject) {
  const colors = editorTransformColors();
  const size = Math.max(14, styleOverride.cornerSize || fabricObject.cornerSize || 16);
  ctx.save();
  shapeLockedControlRenderTransform(ctx, left, top, fabricObject);
  ctx.fillStyle = colors.corner;
  ctx.strokeStyle = colors.cornerStroke;
  ctx.lineWidth = 2;
  roundedRectPath(ctx, -size / 2, -size / 2, size, size, 3);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function renderFigmaSideControl(name) {
  return function renderSide(ctx, left, top, styleOverride, fabricObject) {
    const colors = editorTransformColors();
    const base = Math.max(15, styleOverride.cornerSize || fabricObject.cornerSize || 16);
    const vertical = name === "ml" || name === "mr";
    const width = vertical ? Math.max(9, base * 0.62) : Math.max(21, base * 1.45);
    const height = vertical ? Math.max(21, base * 1.45) : Math.max(9, base * 0.62);
    ctx.save();
    shapeLockedControlRenderTransform(ctx, left, top, fabricObject);
    ctx.fillStyle = colors.corner;
    ctx.strokeStyle = colors.cornerStroke;
    ctx.lineWidth = 2;
    roundedRectPath(ctx, -width / 2, -height / 2, width, height, Math.min(width, height) / 2);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  };
}

function renderFigmaRotateControl(ctx, left, top, styleOverride, fabricObject) {
  const colors = editorTransformColors();
  const size = Math.max(17, styleOverride.cornerSize || fabricObject.cornerSize || 16);
  ctx.save();
  shapeLockedControlRenderTransform(ctx, left, top, fabricObject);
  ctx.fillStyle = colors.corner;
  ctx.strokeStyle = colors.cornerStroke;
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  ctx.arc(0, 0, size / 2, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.strokeStyle = colors.skewCorner;
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.arc(0, 0, size * 0.25, -0.7, Math.PI * 1.25);
  ctx.stroke();
  ctx.restore();
}

function configureEditorTransformControls() {
  if (!fabric?.Control || !fabric?.Object?.prototype?.controls || !fabric.controlsUtils) return;
  const controls = fabric.Object.prototype.controls;
  const generousHitArea = {
    sizeX: 34,
    sizeY: 34,
    touchSizeX: 64,
    touchSizeY: 64,
  };
  controls.ml = new fabric.Control({
    x: -0.5,
    y: 0,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("ml"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: fabric.controlsUtils.scalingX,
    actionName: "scaleX",
    render: renderFigmaSideControl("ml"),
  });
  controls.mr = new fabric.Control({
    x: 0.5,
    y: 0,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mr"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: fabric.controlsUtils.scalingX,
    actionName: "scaleX",
    render: renderFigmaSideControl("mr"),
  });
  controls.mt = new fabric.Control({
    x: 0,
    y: -0.5,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mt"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: fabric.controlsUtils.scalingY,
    actionName: "scaleY",
    render: renderFigmaSideControl("mt"),
  });
  controls.mb = new fabric.Control({
    x: 0,
    y: 0.5,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mb"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: fabric.controlsUtils.scalingY,
    actionName: "scaleY",
    render: renderFigmaSideControl("mb"),
  });
  for (const [name, x, y] of [["tl", -0.5, -0.5], ["tr", 0.5, -0.5], ["bl", -0.5, 0.5], ["br", 0.5, 0.5]]) {
    controls[name] = new fabric.Control({
      x,
      y,
      ...generousHitArea,
      positionHandler: figmaControlPositionHandler(name),
      cursorStyleHandler: editorCornerTransformCursorStyleHandler,
      actionHandler: editorCornerTransformHandler,
      getActionName: editorCornerTransformActionName,
      render: renderFigmaCornerControl,
    });
  }
  if (fabric.controlsUtils.rotationWithSnapping) {
    controls.mtr = new fabric.Control({
      x: 0,
      y: -0.5,
      ...generousHitArea,
      positionHandler: figmaRotatePositionHandler,
      cursorStyleHandler: fabric.controlsUtils.rotationStyleHandler,
      actionHandler: fabric.controlsUtils.rotationWithSnapping,
      actionName: "rotate",
      withConnection: false,
      render: renderFigmaRotateControl,
    });
  }
}

function setStatus(message) {
  setText("status", message);
}

function showCornerNotice(title, message = "") {
  const notice = $("cornerNotice");
  if (!notice) return;
  const titleEl = $("cornerNoticeTitle");
  const bodyEl = $("cornerNoticeBody");
  if (titleEl) titleEl.textContent = title;
  if (bodyEl) bodyEl.textContent = message;
  notice.hidden = false;
  notice.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    notice.classList.remove("show");
    setTimeout(() => {
      if (!notice.classList.contains("show")) notice.hidden = true;
    }, 180);
  }, 4200);
}

function invalidateLayerStats() {
  layerStatsCache = null;
}

function getLayerStats(force = false) {
  if (!force && layerStatsCache) return layerStatsCache;
  const objects = vinylObjects();
  const visible = objects.filter((obj) => obj.visible !== false && (obj.opacity ?? 1) > 0).length;
  layerStatsCache = { objects, count: objects.length, visible };
  return layerStatsCache;
}

function updateHud(pointer = null, options = {}) {
  if (!canvas) return;
  if (!options.pointerOnly) {
    const selected = selectedVinylObjects().length;
    const stats = getLayerStats(Boolean(options.forceStats));
    const zoom = `${Math.round((canvas.getZoom() || 1) * 100)}%`;
    const layerText = `${stats.count} layer${stats.count === 1 ? "" : "s"}`;
    const selectionText = selected ? `${selected} selected` : "No layer selected";
    setText("selectedCount", String(selected));
    setText("visibleCount", String(stats.visible));
    setText("zoomValue", zoom);
    setText("hudLayers", layerText);
    setText("hudMode", currentHudMode(selected));
    setText("bottomZoom", zoom);
    setText("bottomLayers", layerText);
    setText("contextSelection", selectionText);
    setText("exportLayerCount", String(stats.count));
    setText("layerLimitMeter", `${stats.count} / template`);
    setHidden("emptyCanvasHint", stats.count > 0 || Boolean(overlayImage));
  }
  if (pointer) {
    const coords = `x ${round(pointer.x)}, y ${round(-pointer.y)}`;
    setText("hudCoords", coords);
    setText("bottomCoords", coords);
  }
}

function currentHudMode(selectedCount = 0) {
  if (shapeEyedropperActive || activeToolMode === "dropper") return "Eyedropper";
  if (activeToolMode === "guides") return selectedGuideId ? "Guide selected" : "Draw guides";
  if (activeToolMode === "source") return overlayImage ? "Move source overlay" : "Source tool - no overlay";
  if (activeToolMode === "shapeLibrary") return "Place from library";
  if (activeToolMode === "overlay") return "Overlay controls";
  return selectedCount ? "Edit selected" : "Select / box-select";
}

function setHoverHud(target) {
  if (!$("hudHover")) return;
  if (target?.kloudy) {
    $("hudHover").textContent = `over ${target.kloudy.name || typeLabel(target.kloudy.type)}`;
  } else {
    $("hudHover").textContent = "over nothing";
  }
}

function schedulePointerHud(pointer = null, target = null, hoverText = null) {
  pendingHudPointer = pointer;
  pendingHudTarget = target;
  pendingHudText = hoverText;
  if (hudUpdateFrame) return;
  hudUpdateFrame = requestAnimationFrame(() => {
    hudUpdateFrame = null;
    updateHud(pendingHudPointer, { pointerOnly: true });
    if (pendingHudText) setText("hudHover", pendingHudText);
    else setHoverHud(pendingHudTarget);
    pendingHudPointer = null;
    pendingHudTarget = null;
    pendingHudText = null;
  });
}

function setBusy(message) {
  $("busyText").textContent = message;
  $("busyBanner").hidden = false;
  setStatus(message);
}

function clearBusy(message = null) {
  $("busyBanner").hidden = true;
  if (message) setStatus(message);
}

function showError(prefix, err) {
  const message = err && err.stack ? err.stack : (err && err.message ? err.message : String(err));
  console.error(prefix, err);
  clearBusy(`${prefix}: ${message.split("\n")[0]}`);
  alert(`${prefix}\n\n${message}`);
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

function colorToHex(color) {
  const c = normalizeColor(color);
  return `#${c[0].toString(16).padStart(2, "0")}${c[1].toString(16).padStart(2, "0")}${c[2].toString(16).padStart(2, "0")}`;
}

function normalizeColor(color) {
  const out = Array.isArray(color) ? color.slice(0, 4) : [255, 255, 255, 255];
  while (out.length < 4) out.push(255);
  return out.map((v) => Math.max(0, Math.min(255, Math.round(Number(v) || 0))));
}

function hexToRgb(hex, alpha) {
  const clean = hex.replace("#", "");
  const parsedAlpha = Number(alpha);
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
    Math.max(0, Math.min(255, Math.round(Number.isFinite(parsedAlpha) ? parsedAlpha : 255))),
  ];
}

function loadFavoriteColors() {
  try {
    const saved = JSON.parse(localStorage.getItem("kloudyFabricFavoriteColors") || "[]");
    if (!Array.isArray(saved)) return [];
    return saved.map((color) => color ? normalizeColor(color) : null).slice(0, FAVORITE_COLOR_SLOTS);
  } catch (_err) {
    return [];
  }
}

function loadFavoriteShapes() {
  try {
    const saved = JSON.parse(localStorage.getItem("kloudyFabricFavorites") || "[]");
    return new Set(Array.isArray(saved) ? saved.map(String) : []);
  } catch (_err) {
    return new Set();
  }
}

function loadLastFontShapeTransform() {
  try {
    const saved = JSON.parse(localStorage.getItem("kloudyFabricLastFontShapeTransform") || "null");
    if (!saved || typeof saved !== "object") return null;
    return {
      scaleX: Number(saved.scaleX) || 1,
      scaleY: Number(saved.scaleY) || 1,
      angle: Number(saved.angle) || 0,
      skewX: Number(saved.skewX) || 0,
    };
  } catch (_err) {
    return null;
  }
}

function isFontFamily(family) {
  return String(family || "").includes("Letters");
}

function rememberFontShapeTransform(object) {
  if (!object?.kloudy || !isFontFamily(object.kloudy.resource_family)) return;
  lastFontShapeTransform = {
    scaleX: Number(object.scaleX) || 1,
    scaleY: Number(object.scaleY) || 1,
    angle: Number(object.angle) || 0,
    skewX: Number(object.skewX) || 0,
  };
  localStorage.setItem("kloudyFabricLastFontShapeTransform", JSON.stringify(lastFontShapeTransform));
}

function saveFavoriteColors() {
  localStorage.setItem("kloudyFabricFavoriteColors", JSON.stringify(favoriteColors));
}

function activateDockPanel(panelId) {
  const button = document.querySelector(`.dockTab[data-panel="${panelId}"]`);
  if (!button) return;
  const group = button.closest(".dockGroup");
  if (!group) return;
  group.querySelectorAll(".dockTab").forEach((tab) => tab.classList.toggle("active", tab === button));
  group.querySelectorAll(".dockPane").forEach((pane) => {
    const active = pane.id === panelId;
    pane.classList.toggle("active", active);
    pane.hidden = !active;
  });
}

function setToolRailMode(mode, label = null) {
  activeToolMode = mode || "select";
  document.querySelectorAll(".toolButton").forEach((tool) => tool.classList.toggle("active", tool.dataset.toolMode === activeToolMode));
  const activeButton = document.querySelector(`.toolButton[data-tool-mode="${activeToolMode}"]`);
  label = label || activeButton?.dataset.tool || "Select / Move";
  setText("activeToolLabel", label);
  setText("hudMode", currentHudMode(selectedVinylObjects().length));
  updateGuideInteractivity();
  updateSourceInteractivity();
}

function setActiveTool(button) {
  if (!button) return;
  const mode = button.dataset.toolMode || "select";
  const label = button.dataset.tool || button.textContent.trim();
  setToolRailMode(mode, label);
  if (mode === "dropper") {
    setShapeEyedropper(true, { keepTool: true });
  } else {
    setShapeEyedropper(false, { keepTool: true, silent: true });
  }
  if (mode === "guides") {
    canvas?.discardActiveObject();
  } else if (mode === "source") {
    selectedGuideId = null;
    renderGuideObjects();
    updateSourceInteractivity();
  } else if (selectedGuideId) {
    selectedGuideId = null;
    renderGuideObjects();
  }
  if (button.dataset.focusPanel) activateDockPanel(button.dataset.focusPanel);
  if (mode === "select") setStatus("Select mode. Drag empty canvas to box-select; mouse wheel zooms; middle/right drag pans.");
  if (mode === "shapeLibrary") setStatus("Shape Library open. Click a shape tile to place it in the current viewport.");
  if (mode === "guides") setStatus("Guides mode. Drag on the canvas to create editor-only guide lines. Hold Control while moving vinyl layers to snap.");
  if (mode === "overlay") setStatus("Overlay controls open. Overlay images are reference-only and never exported.");
  if (mode === "source") setStatus(overlayImage ? "Source Move mode. Drag the source overlay only; vinyl layers and guides are ignored. Hold Control to snap it to grid/guides." : "Source Move mode needs an overlay first. Add a source image in Overlay controls.");
}

function activateToolShortcut(key) {
  const normalized = String(key || "").toLowerCase();
  const button = document.querySelector(`.toolButton[data-tool-key="${normalized}"]`);
  if (!button) return false;
  setActiveTool(button);
  return true;
}

function setVBoxSelectActive(active) {
  vBoxSelectActive = Boolean(active);
  document.body.classList.toggle("forceBoxSelectMode", vBoxSelectActive);
  if (canvas && !shapeEyedropperActive && activeToolMode !== "guides" && activeToolMode !== "source") {
    canvas.selection = true;
    canvas.skipTargetFind = vBoxSelectActive;
    canvas.defaultCursor = vBoxSelectActive ? "crosshair" : "default";
    canvas.hoverCursor = vBoxSelectActive ? "crosshair" : "default";
    canvas.requestRenderAll();
  }
  if (vBoxSelectActive) setText("hudMode", "V box select");
  else setText("hudMode", currentHudMode(selectedVinylObjects().length));
}

function leaveGuideModeForLayerEdit() {
  if (activeToolMode !== "guides") return;
  guideDraft = null;
  selectedGuideId = null;
  setToolRailMode("select", "Select / Move");
  renderGuideObjects();
  setStatus("Guide drawing disengaged. Select mode is active while editing shapes.");
}

function resourceCountForFamilyDefinition(family) {
  if (String(family).startsWith("Upper_Letters_")) return 26;
  return 40;
}

function resolvedResourceFromFullTypeCode(typeCode) {
  const fullCode = Number(typeCode);
  if (!Number.isFinite(fullCode) || fullCode <= 1000000) return null;
  for (const [family, base] of Object.entries(VINYL_TYPE_BASES)) {
    const delta = fullCode - Number(base);
    if (delta >= 0 && delta < resourceCountForFamilyDefinition(family)) {
      const shapeWord = fullCode & 0xffff;
      return { family, index: delta + 1, typeCode: fullCode, shapeWord };
    }
  }
  return null;
}

function resolvedResourceFromShapeWord(wordValue) {
  const word = Number(wordValue) & 0xffff;
  for (const [family, base] of Object.entries(VINYL_TYPE_BASES)) {
    const baseWord = Number(base) & 0xffff;
    const delta = word - baseWord;
    if (delta >= 0 && delta < resourceCountForFamilyDefinition(family)) {
      return { family, index: delta + 1, typeCode: 0x100000 + word, shapeWord: word };
    }
  }
  return null;
}

function typeCodeToResource(typeCode) {
  const fullResource = resolvedResourceFromFullTypeCode(typeCode);
  if (fullResource) return fullResource;
  const word = Number(typeCode) & 0xffff;
  const compactResource = resolvedResourceFromShapeWord(word);
  if (compactResource) return compactResource;
  const explicit = shapeWords?.families || {};
  for (const [family, values] of Object.entries(explicit)) {
    for (const [index, shapeWord] of Object.entries(values || {})) {
      if ((Number(shapeWord) & 0xffff) === word) {
        return { family, index: Number(index), typeCode: 0x100000 + word, shapeWord: word };
      }
    }
  }
  return null;
}

function resourceToTypeCode(family, index) {
  return 0x100000 + resourceToShapeWord(family, index);
}

function resourceToShapeWord(family, index) {
  if (family === "Primitives") return (100 + Number(index)) & 0xffff;
  const base = VINYL_TYPE_BASES[family];
  if (!base) throw new Error(`Unknown shape family: ${family}`);
  if (family.includes("Letters")) return (base + Number(index) - 1) & 0xffff;
  return ((base & 0xffff) + Number(index) - 1) & 0xffff;
}

async function loadResourcePath(typeCode) {
  const resolved = typeCodeToResource(typeCode);
  if (!resolved) throw new Error(`Unsupported FH6 type code: ${typeCode}`);
  return loadResourcePathForResolved(resolved);
}

async function loadResourcePathForResolved(resolved) {
  const cacheKey = `${resolved.family}:${resolved.index}:${resolved.typeCode || ""}`;
  if (resourceCache.has(cacheKey)) return resourceCache.get(cacheKey);
  const url = await resolveVinylResourceUrl(resolved.family, resolved.index, "");
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Missing shape resource: ${url}`);
  const payload = await response.json();
  const vertices = payload.Vertices || [];
  const indices = payload.Indices || [];
  const chunks = [];
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const p0 = vertices[indices[i]];
    const p1 = vertices[indices[i + 1]];
    const p2 = vertices[indices[i + 2]];
    if (!p0 || !p1 || !p2) continue;
    chunks.push(`M ${fmt(p0.X)} ${fmt(p0.Y)} L ${fmt(p1.X)} ${fmt(p1.Y)} L ${fmt(p2.X)} ${fmt(p2.Y)} Z`);
  }
  const d = chunks.join(" ");
  resourceCache.set(cacheKey, d);
  return d;
}

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

async function loadResourceOutlinePathForResolved(resolved) {
  const cacheKey = `${resolved.family}:${resolved.index}:${resolved.typeCode || ""}`;
  if (resourceOutlineCache.has(cacheKey)) return resourceOutlineCache.get(cacheKey);
  const url = await resolveVinylResourceUrl(resolved.family, resolved.index, "");
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Missing shape resource: ${url}`);
  const payload = await response.json();
  const vertices = payload.Vertices || [];
  const indices = payload.Indices || [];
  const edges = new Map();
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const tri = [indices[i], indices[i + 1], indices[i + 2]];
    for (const [a, b] of [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]]) {
      if (!vertices[a] || !vertices[b]) continue;
      const key = edgeKey(a, b);
      const current = edges.get(key);
      if (current) current.count += 1;
      else edges.set(key, { a, b, count: 1 });
    }
  }
  const chunks = [];
  edges.forEach((edge) => {
    if (edge.count !== 1) return;
    const p0 = vertices[edge.a];
    const p1 = vertices[edge.b];
    chunks.push(`M ${fmt(p0.X)} ${fmt(p0.Y)} L ${fmt(p1.X)} ${fmt(p1.Y)}`);
  });
  const d = chunks.join(" ");
  resourceOutlineCache.set(cacheKey, d);
  return d;
}

function loadFabricImage(url) {
  return new Promise((resolve, reject) => {
    fabric.Image.fromURL(url, (image) => {
      if (!image) reject(new Error(`Failed to load image resource: ${url}`));
      else resolve(image);
    }, { crossOrigin: "anonymous" });
  });
}

async function resolveVinylResourceUrl(family, index, suffix = "") {
  const orderedBases = resolvedResourceBase
    ? [resolvedResourceBase, ...VINYL_RESOURCE_BASES.filter((base) => base !== resolvedResourceBase)]
    : VINYL_RESOURCE_BASES;
  let lastUrl = "";
  for (const base of orderedBases) {
    const url = `${base}/${family}/${index}${suffix}`;
    lastUrl = url;
    try {
      const response = await fetch(url, { cache: "force-cache" });
      if (response.ok) {
        resolvedResourceBase = base;
        localStorage.setItem("kloudyFabricResourceBase", base);
        return url;
      }
    } catch (_err) {
      // Try the next bundled resource location.
    }
  }
  return lastUrl;
}

function vinylResourceUrl(family, index, suffix = "") {
  const base = resolvedResourceBase || VINYL_RESOURCE_BASES[0];
  return `${base}/${family}/${index}${suffix}`;
}

function fmt(value) {
  return String(Math.round(Number(value) * 1000000) / 1000000);
}

function legacyBoundsForShape(shape) {
  const data = Array.isArray(shape.data) ? shape.data : [];
  if (data.length < 4) return null;
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const w = Math.abs(Number(data[2]) || 1);
  const h = Math.abs(Number(data[3]) || 1);
  return { minX: x - w / 2, maxX: x + w / 2, minY: y - h / 2, maxY: y + h / 2 };
}

function computeLegacyOffset(shapes) {
  let bounds = null;
  for (const shape of shapes) {
    const type = Number(shape.type);
    if (!LEGACY_RECTANGLE_TYPES.has(type) && !LEGACY_ELLIPSE_TYPES.has(type)) continue;
    const b = legacyBoundsForShape(shape);
    if (!b) continue;
    bounds = bounds ? {
      minX: Math.min(bounds.minX, b.minX),
      maxX: Math.max(bounds.maxX, b.maxX),
      minY: Math.min(bounds.minY, b.minY),
      maxY: Math.max(bounds.maxY, b.maxY),
    } : b;
  }
  if (!bounds) return { x: 0, y: 0 };
  return { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 };
}

function legacyToFh6Shape(shape, legacyOffset = { x: 0, y: 0 }) {
  const type = Number(shape.type);
  const data = Array.isArray(shape.data) ? shape.data : [];
  if (data.length < 4) throw new Error("Legacy shape requires at least x,y,w,h data.");
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const w = Number(data[2]) || 1;
  const h = Number(data[3]) || 1;
  const rot = Number(data[4]) || 0;
  const isRect = LEGACY_RECTANGLE_TYPES.has(type);
  const divisor = isRect ? RECTANGLE_DIVISOR : ELLIPSE_DIVISOR;
  const fullCode = isRect ? 1048677 : 1048678;
  return {
    type: fullCode,
    type_word: fullCode & 0xffff,
    data: [
      x - legacyOffset.x,
      -(y - legacyOffset.y),
      w / divisor,
      h / divisor,
      isRect && type === 1 ? 0 : (360 - rot) % 360,
      Number(data[5]) || 0,
      shape.mask ? 1 : 0,
    ],
    color: normalizeColor(shape.color),
    mask: Boolean(shape.mask),
    score: Number(shape.score) || 0,
    source_format: "legacy_geometry",
    legacy_type: type,
    legacy_divisor: divisor,
    legacy_offset: [legacyOffset.x, legacyOffset.y],
  };
}

function normalizeInputShape(shape, index, legacyOffset = { x: 0, y: 0 }) {
  const color = normalizeColor(shape.color);
  if (index === 0 && Number(shape.type) === 1 && color[3] <= 0) return null;
  if (color[3] <= 0) return null;
  const type = Number(shape.type);
  if (LEGACY_RECTANGLE_TYPES.has(type) || LEGACY_ELLIPSE_TYPES.has(type)) {
    return legacyToFh6Shape(shape, legacyOffset);
  }
  if (type > 1000000) {
    const data = Array.isArray(shape.data) ? shape.data.slice() : [];
    while (data.length < 7) data.push(0);
    return {
      ...shape,
      type,
      type_word: Number(shape.type_word ?? (type & 0xffff)),
      data,
      color,
      mask: Boolean(shape.mask || data[6]),
      score: Number(shape.score) || 0,
    };
  }
  return null;
}

async function makeFabricObject(shape, name = null) {
  const typeCode = Number(shape.type);
  const typeResolved = typeCodeToResource(typeCode);
  const explicitResource = shape.resource_family && shape.resource_index
    ? {
      family: String(shape.resource_family),
      index: Number(shape.resource_index),
      typeCode,
      shapeWord: Number(shape.type_word ?? (typeCode & 0xffff)),
    }
    : null;
  const resolved = typeResolved || explicitResource;
  const d = resolved ? await loadResourcePathForResolved(resolved) : await loadResourcePath(typeCode);
  const color = normalizeColor(shape.color);
  const data = shape.data || [0, 0, 1, 1, 0, 0, 0];
  const outlinePath = resolved ? await loadResourceOutlinePathForResolved(resolved).catch(() => "") : "";
  const gradientResource = isGradientResource(resolved);
  const shapePathForBounds = gradientResource ? new fabric.Path(d, { originX: "center", originY: "center" }) : null;
  const object = gradientResource
    ? await loadFabricImage(await resolveVinylResourceUrl(resolved.family, resolved.index, ".png"))
    : new fabric.Path(d);
  const useBitmapCache = gradientResource;
  object.set({
    originX: "center",
    originY: "center",
    ...fabricPropsFromFh6Data(data),
    stroke: null,
    strokeWidth: 0,
    objectCaching: useBitmapCache,
    noScaleCache: useBitmapCache,
    perPixelTargetFind: true,
    targetFindTolerance: VINYL_HIT_TOLERANCE,
    hoverCursor: "pointer",
    moveCursor: "move",
    lockScalingFlip: false,
    centeredScaling: false,
  });
  if (shapePathForBounds) {
    object.set({
      width: Math.max(1, Number(shapePathForBounds.width) || Number(object.width) || 1),
      height: Math.max(1, Number(shapePathForBounds.height) || Number(object.height) || 1),
    });
  }
  const resolvedShapeWord = Number(resolved?.shapeWord ?? shape.type_word ?? (typeCode & 0xffff));
  object.kloudy = {
    name: name || (resolved ? shapeDisplayName(resolved.family, resolved.index) : (shape.shape_name || typeLabel(typeCode))),
    type: typeCode,
    type_word: Number.isFinite(resolvedShapeWord) ? resolvedShapeWord : (typeCode & 0xffff),
    resource_family: resolved?.family || null,
    resource_index: resolved?.index || null,
    source_format: shape.source_format || "fh6_typecode",
    legacy_type: shape.legacy_type ?? null,
    legacy_divisor: shape.legacy_divisor ?? null,
    legacy_offset: Array.isArray(shape.legacy_offset) ? shape.legacy_offset.slice(0, 2) : null,
    score: Number(shape.score) || 0,
    extra: data.slice(5),
    mask: Boolean(shape.mask || data[6]),
    maskOriginalColor: Boolean(shape.mask || data[6]) ? color.slice() : null,
    locked: Boolean(shape.editor_locked),
    group_id: shape.editor_group_id ? String(shape.editor_group_id) : null,
    group_name: shape.editor_group_name ? String(shape.editor_group_name) : null,
    mesh_path: d || null,
    outline_path: outlinePath || null,
    scaleSigns: {
      x: (Number(data[2]) || 1) < 0 ? -1 : 1,
      y: (Number(data[3]) || 1) < 0 ? -1 : 1,
    },
  };
  applyObjectColor(object, color);
  applyMaskVisual(object);
  if (shape.editor_hidden) object.visible = false;
  if (object.kloudy.locked) setObjectLocked(object, true);
  styleObjectTransformControls(object);
  return object;
}

function radiansToDegrees(value) {
  return value * 180 / Math.PI;
}

function degreesToTan(value) {
  return Math.tan(value * Math.PI / 180);
}

function typeLabel(typeCode) {
  const resolved = typeCodeToResource(typeCode);
  if (!resolved) return `Unknown ${typeCode}`;
  return shapeDisplayName(resolved.family, resolved.index);
}

function shapeDisplayName(family, index) {
  const familyLabel = family.replaceAll("_", " ");
  let word;
  try {
    word = resourceToShapeWord(family, index);
  } catch (_err) {
    word = shapeWords?.families?.[family]?.[String(index)];
  }
  const suffix = word !== undefined ? ` / word ${word}` : "";
  if (family === "Primitives" || family.includes("Letters")) {
    return shapeNames?.families?.[family]?.[String(index)] || `${familyLabel} slot ${index}${suffix}`;
  }
  return `${familyLabel} slot ${index}${suffix}`;
}

function shapeSearchText(family, index, typeCode) {
  return [
    family,
    family.replaceAll("_", " "),
    index,
    typeCode,
    `#${index}`,
    shapeDisplayName(family, index),
  ].join(" ").toLowerCase();
}

function shapeCountForFamily(family) {
  const named = shapeNames?.families?.[family];
  if (named && Object.keys(named).length) {
    return Math.max(...Object.keys(named).map((key) => Number(key) || 0));
  }
  if (family.startsWith("Upper_Letters_")) return 26;
  if (family.startsWith("Lower_Letters_")) return 39;
  return 40;
}

async function loadShapeNames() {
  try {
    const [namesResponse, wordsResponse] = await Promise.all([
      fetch("/tools/fabric-editor/shape-names.json"),
      fetch("/tools/fabric-editor/shape-words.json"),
    ]);
    if (!namesResponse.ok) throw new Error(`shape-names HTTP ${namesResponse.status}`);
    if (!wordsResponse.ok) throw new Error(`shape-words HTTP ${wordsResponse.status}`);
    shapeNames = await namesResponse.json();
    shapeWords = await wordsResponse.json();
    renderShapeGrid();
  } catch (err) {
    console.warn("Shape metadata unavailable.", err);
  }
}

function rememberColor(color) {
  rememberedColor = normalizeColor(color);
  localStorage.setItem("kloudyFabricLastColor", JSON.stringify(rememberedColor));
  refreshColorUi();
}

function currentPanelColor() {
  const selected = selectedVinylObjects();
  if (selected.length === 1) {
    if (selected[0].kloudy?.mask && Array.isArray(selected[0].kloudy.maskOriginalColor)) {
      return normalizeColor(selected[0].kloudy.maskOriginalColor);
    }
    return hexToRgb(selected[0].fill || "#ffffff", (selected[0].opacity ?? 1) * 255);
  }
  return rememberedColor;
}

function refreshColorUi() {
  const active = normalizeColor(currentPanelColor());
  const activeHex = colorToHex(active);
  const swatch = $("colorSwatchButton");
  if (swatch) swatch.style.setProperty("--swatch", activeHex);
  if ($("colorPanelSwatch")) $("colorPanelSwatch").style.setProperty("--swatch", activeHex);
  if ($("quickColorSwatch")) $("quickColorSwatch").style.setProperty("--swatch", activeHex);
  if ($("colorPanelLabel")) $("colorPanelLabel").textContent = `${activeHex.toUpperCase()} / A ${active[3]}`;
  if ($("activeColorLarge")) $("activeColorLarge").style.setProperty("--swatch", activeHex);
  if ($("activeColorLabel")) $("activeColorLabel").textContent = `${activeHex.toUpperCase()} / A ${active[3]}`;
  if ($("dialogColorPicker")) $("dialogColorPicker").value = activeHex;
  if ($("colorPicker") && selectedVinylObjects().length !== 1) $("colorPicker").value = colorToHex(rememberedColor);
  renderFavoriteColors();
}

function refreshColorUiFast(color) {
  const active = normalizeColor(color);
  const activeHex = colorToHex(active);
  const swatch = $("colorSwatchButton");
  if (swatch) swatch.style.setProperty("--swatch", activeHex);
  if ($("colorPanelSwatch")) $("colorPanelSwatch").style.setProperty("--swatch", activeHex);
  if ($("quickColorSwatch")) $("quickColorSwatch").style.setProperty("--swatch", activeHex);
  if ($("colorPanelLabel")) $("colorPanelLabel").textContent = `${activeHex.toUpperCase()} / A ${active[3]}`;
  if ($("activeColorLarge")) $("activeColorLarge").style.setProperty("--swatch", activeHex);
  if ($("activeColorLabel")) $("activeColorLabel").textContent = `${activeHex.toUpperCase()} / A ${active[3]}`;
  if ($("colorPicker")) $("colorPicker").value = activeHex;
  if ($("opacitySlider")) $("opacitySlider").value = active[3];
}

function renderFavoriteColors() {
  const grid = $("favoriteColorGrid");
  if (!grid) return;
  const activeHex = colorToHex(currentPanelColor());
  grid.innerHTML = "";
  for (let index = 0; index < FAVORITE_COLOR_SLOTS; index++) {
    const color = favoriteColors[index] || null;
    const button = document.createElement("button");
    button.type = "button";
    const selected = index === selectedFavoriteColorSlot;
    button.className = `favoriteColorSwatch${color ? "" : " empty"}${selected ? " selected" : ""}${color && colorToHex(color) === activeHex ? " active" : ""}`;
    button.title = color
      ? `Slot ${index + 1}: use ${colorToHex(color).toUpperCase()} / A ${color[3]}`
      : `Slot ${index + 1}: empty. Click to select, then Save Color.`;
    if (color) button.style.setProperty("--swatch", colorToHex(color));
    button.addEventListener("click", () => {
      selectedFavoriteColorSlot = index;
      if (color) applyEditorColor(color, "saved color");
      else {
        renderFavoriteColors();
        setStatus(`Selected empty color slot ${index + 1}. Choose a color, then Save Color.`);
      }
    });
    grid.appendChild(button);
  }
}

function previewEditorColor(color) {
  const normalized = normalizeColor(color);
  rememberedColor = normalized;
  const selected = selectedVinylObjects();
  const editable = unlockedObjects(selected);
  editable.forEach((obj) => {
    applyObjectColor(obj, normalized);
    obj.setCoords();
  });
  refreshColorUiFast(normalized);
  syncSelectedShapeOutlines(selected);
  if (canvas && editable.length) canvas.requestRenderAll();
}

function scheduleDialogColorPreview(color) {
  pendingDialogColor = normalizeColor(color);
  if (dialogColorFrame) return;
  dialogColorFrame = requestAnimationFrame(() => {
    dialogColorFrame = null;
    if (!pendingDialogColor) return;
    previewEditorColor(pendingDialogColor);
  });
}

function commitDialogColor(color) {
  pendingDialogColor = null;
  applyEditorColor(color, "dialog color");
}

function commitPendingDialogColor() {
  if (pendingDialogColor) commitDialogColor(pendingDialogColor);
}

function applyEditorColor(color, reason = "color") {
  const normalized = normalizeColor(color);
  const selected = selectedVinylObjects();
  if (selected.length === 1) {
    if (selected[0].kloudy?.locked) {
      updateSelectionPanel();
      setStatus("Selected layer is locked. Unlock it before changing color.");
      return;
    }
    rememberColor(normalized);
    applyObjectColor(selected[0], normalized);
    selected[0].setCoords();
    syncSelectedShapeOutlines(selected);
    canvas.requestRenderAll();
    updateSelectionPanel();
    pushHistory(reason);
    return;
  }
  if (selected.length > 1) {
    const editable = unlockedObjects(selected);
    if (!editable.length) {
      rememberColor(normalized);
      updateSelectionPanel();
      setStatus("Selected layers are locked. Unlock them before changing color.");
      return;
    }
    rememberColor(normalized);
    editable.forEach((obj) => {
      applyObjectColor(obj, normalized);
      obj.setCoords();
    });
    syncSelectedShapeOutlines(selected);
    canvas.requestRenderAll();
    updateSelectionPanel();
    pushHistory("batch color edit");
    setStatus(`Applied ${colorToHex(normalized).toUpperCase()} / A ${normalized[3]} to ${editable.length} selected layer(s).${editable.length !== selected.length ? ` Skipped ${selected.length - editable.length} locked layer(s).` : ""}`);
    return;
  }
  rememberColor(normalized);
  if ($("colorPicker")) $("colorPicker").value = colorToHex(normalized);
  if ($("opacitySlider")) $("opacitySlider").value = normalized[3];
  updateSelectionPanel();
  setStatus(`Active color set to ${colorToHex(normalized).toUpperCase()}.`);
}

function alphaForObject(object) {
  if (object?.kloudy?.mask && Array.isArray(object.kloudy.maskOriginalColor)) {
    return normalizeColor(object.kloudy.maskOriginalColor)[3];
  }
  return Math.round((object?.opacity ?? 1) * 255);
}

function sharedSelectedAlpha(selected = selectedVinylObjects()) {
  if (!selected.length) return null;
  const first = alphaForObject(selected[0]);
  return selected.every((object) => alphaForObject(object) === first) ? first : null;
}

function openColorDialog() {
  refreshColorUi();
  $("colorDialog").showModal();
}

function saveCurrentFavoriteColor() {
  const color = normalizeColor(currentPanelColor());
  const hex = colorToHex(color);
  if (selectedFavoriteColorSlot < 0 || selectedFavoriteColorSlot >= FAVORITE_COLOR_SLOTS) {
    selectedFavoriteColorSlot = Math.max(0, favoriteColors.findIndex((item) => !item));
  }
  if (selectedFavoriteColorSlot < 0) selectedFavoriteColorSlot = 0;
  while (favoriteColors.length < FAVORITE_COLOR_SLOTS) favoriteColors.push(null);
  favoriteColors[selectedFavoriteColorSlot] = color;
  favoriteColors = favoriteColors.slice(0, FAVORITE_COLOR_SLOTS);
  saveFavoriteColors();
  renderFavoriteColors();
  setStatus(`Saved ${hex.toUpperCase()} to color slot ${selectedFavoriteColorSlot + 1}.`);
}

function removeCurrentFavoriteColor() {
  const slot = Math.max(0, Math.min(FAVORITE_COLOR_SLOTS - 1, selectedFavoriteColorSlot));
  const hadColor = Boolean(favoriteColors[slot]);
  while (favoriteColors.length < FAVORITE_COLOR_SLOTS) favoriteColors.push(null);
  favoriteColors[slot] = null;
  saveFavoriteColors();
  renderFavoriteColors();
  setStatus(hadColor ? `Cleared color slot ${slot + 1}.` : `Color slot ${slot + 1} is already empty.`);
}

function clearFavoriteColors() {
  favoriteColors = Array(FAVORITE_COLOR_SLOTS).fill(null);
  saveFavoriteColors();
  renderFavoriteColors();
  setStatus("Cleared saved colors.");
}

function setShapeEyedropper(active, options = {}) {
  shapeEyedropperActive = active;
  if (active && !dropperPreservedActiveObject) {
    dropperPreservedActiveObject = canvas?.getActiveObject() || null;
  }
  if (!active) {
    dropperPreservedActiveObject = null;
  }
  $("colorEyedropper")?.classList.toggle("active", active);
  document.body.classList.toggle("eyedropperMode", active);
  if (canvas) {
    canvas.skipTargetFind = false;
    canvas.selection = !active;
  }
  if (!options.keepTool) {
    setToolRailMode(active ? "dropper" : "select");
  }
  if (!options.silent) {
    setStatus(active
      ? "Eyedropper active. Click a vinyl layer to copy its color, or click empty/source overlay space to sample the overlay."
      : "Eyedropper off.");
  }
  updateHud();
}

function restoreDropperSelection() {
  if (!shapeEyedropperActive || !canvas) return;
  const active = dropperPreservedActiveObject;
  if (active && canvas.getObjects().includes(active)) {
    canvas.setActiveObject(active);
  } else {
    canvas.discardActiveObject();
  }
  canvas.requestRenderAll();
  updateSelectionPanel();
  updateLayerSelectionStyles();
}

function vinylObjectAtCanvasPoint(x, y) {
  const point = new fabric.Point(x, y);
  const objects = vinylObjects();
  for (let index = objects.length - 1; index >= 0; index--) {
    const object = objects[index];
    if (object.visible === false || object.evented === false) continue;
    object.setCoords();
    if (object.containsPoint(point)) return object;
  }
  return null;
}

function pickShapeColorFromEvent(opt) {
  const pointer = canvas.getPointer(opt.e);
  if (overlayLayerMode === "above") {
    const overlayColor = overlayColorAtCanvasPoint(pointer.x, pointer.y);
    if (overlayColor) {
      restoreDropperSelection();
      applyEditorColor(overlayColor, "source eyedropper");
      restoreDropperSelection();
      setStatus(`Picked source overlay color ${colorToHex(overlayColor).toUpperCase()}.`);
      return;
    }
  }
  const target = (opt.target?.kloudy ? opt.target : null) || vinylObjectAtCanvasPoint(pointer.x, pointer.y);
  restoreDropperSelection();
  if (target) {
    const color = hexToRgb(target.fill || "#ffffff", (target.opacity ?? 1) * 255);
    applyEditorColor(color, "shape eyedropper");
    restoreDropperSelection();
    setStatus(`Picked layer color ${colorToHex(color).toUpperCase()} without changing selection.`);
    return;
  }
  const color = overlayColorAtCanvasPoint(pointer.x, pointer.y);
  if (!color) {
    setStatus("No vinyl layer or source overlay pixel under the eyedropper.");
    return;
  }
  applyEditorColor(color, "source eyedropper");
  restoreDropperSelection();
  setStatus(`Picked source overlay color ${colorToHex(color).toUpperCase()}.`);
}

function signedScaleX(object) {
  const scale = Number(object.scaleX) || 1;
  return (object.flipX ? -1 : 1) * scale;
}

function signedScaleY(object) {
  const scale = Number(object.scaleY) || 1;
  return (object.flipY ? -1 : 1) * scale;
}

function signedScaleToFabric(value) {
  const numeric = Number(value);
  const safe = Number.isFinite(numeric) && numeric !== 0 ? numeric : 1;
  return { scale: Math.abs(safe), flip: safe < 0 };
}

function currentScaleSigns(object) {
  return {
    x: signedScaleX(object) < 0 ? -1 : 1,
    y: signedScaleY(object) < 0 ? -1 : 1,
  };
}

function updateObjectScaleSigns(object) {
  if (!object?.kloudy) return;
  object.kloudy.scaleSigns = currentScaleSigns(object);
}

function fh6SkewFromFabricDegrees(degrees, sx, sy) {
  const safeSy = Number(sy) || 1;
  return -(Math.tan((Number(degrees) || 0) * Math.PI / 180) * (Number(sx) || 1) / safeSy);
}

function multiplyMatrix(a, b) {
  return [
    a[0] * b[0] + a[2] * b[1],
    a[1] * b[0] + a[3] * b[1],
    a[0] * b[2] + a[2] * b[3],
    a[1] * b[2] + a[3] * b[3],
    a[0] * b[4] + a[2] * b[5] + a[4],
    a[1] * b[4] + a[3] * b[5] + a[5],
  ];
}

function translationMatrix(x, y) {
  return [1, 0, 0, 1, x, y];
}

function scaleMatrix(sx, sy) {
  return [sx, 0, 0, sy, 0, 0];
}

function rotationMatrix(degrees) {
  const radians = degrees * Math.PI / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);
  return [cos, sin, -sin, cos, 0, 0];
}

function skewXMatrix(value) {
  return [1, 0, value, 1, 0, 0];
}

function fh6MatrixFromData(data = []) {
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const sx = Number(data[2]) || 1;
  const sy = Number(data[3]) || 1;
  const rotation = Number(data[4]) || 0;
  const skew = Number(data[5]) || 0;
  return [
    translationMatrix(x, -y),
    rotationMatrix(-rotation),
    skewXMatrix(-skew),
    scaleMatrix(sx, sy),
  ].reduce(multiplyMatrix, [1, 0, 0, 1, 0, 0]);
}

function fabricPropsFromFh6Data(data = []) {
  const x = Number(data[0]) || 0;
  const y = Number(data[1]) || 0;
  const sx = Number(data[2]) || 1;
  const sy = Number(data[3]) || 1;
  const rotation = Number(data[4]) || 0;
  const skew = Number(data[5]) || 0;
  const fabricSkew = sx ? (-skew * sy / sx) : 0;
  return {
    left: x,
    top: -y,
    scaleX: Math.abs(sx),
    scaleY: Math.abs(sy),
    flipX: sx < 0,
    flipY: sy < 0,
    angle: -rotation,
    skewX: radiansToDegrees(Math.atan(fabricSkew)),
    skewY: 0,
  };
}

function fh6DataFromObject(object, preferredSigns = null) {
  const matrix = object.calcTransformMatrix();
  const a = matrix[0];
  const b = matrix[1];
  const c = matrix[2];
  const d = matrix[3];
  const x = matrix[4];
  const y = -matrix[5];
  const signX = preferredSigns?.x < 0 ? -1 : 1;
  const sx = signX * (Math.hypot(a, b) || 1);
  const theta = Math.atan2(b / sx, a / sx);
  const det = a * d - b * c;
  const sy = det / sx || 1;
  const cos = Math.cos(-theta);
  const sin = Math.sin(-theta);
  const localC = cos * c - sin * d;
  const skew = sy ? -(localC / sy) : 0;
  const rotation = ((-theta * 180 / Math.PI) % 360 + 360) % 360;
  return [x, y, sx, sy, rotation, skew];
}

function objectToShape(object, options = {}) {
  const includeEditorMeta = options.includeEditorMeta !== false;
  const meta = object.kloudy || {};
  const color = meta.mask && Array.isArray(meta.maskOriginalColor)
    ? normalizeColor(meta.maskOriginalColor)
    : hexToRgb(object.fill || "#ffffff", (object.opacity ?? 1) * 255);
  const extra = Array.isArray(meta.extra) ? meta.extra.slice() : [];
  updateObjectScaleSigns(object);
  const decoded = fh6DataFromObject(object, currentScaleSigns(object));
  const data = [
    round(decoded[0]),
    round(decoded[1]),
    round(decoded[2]),
    round(decoded[3]),
    round(decoded[4]),
    round(decoded[5]),
    meta.mask ? 1 : 0,
  ];
  if (extra.length > 2) data.push(...extra.slice(2));
  const shape = {
    type: Number(meta.type),
    type_word: Number(meta.type_word ?? (Number(meta.type) & 0xffff)),
    data,
    color,
    mask: Boolean(meta.mask),
    score: Number(meta.score) || 0,
    source_format: meta.source_format || "fh6_typecode",
    resource_family: meta.resource_family || null,
    resource_index: meta.resource_index || null,
    shape_name: meta.name || null,
    legacy_type: meta.legacy_type ?? null,
    legacy_divisor: meta.legacy_divisor ?? null,
    legacy_offset: Array.isArray(meta.legacy_offset) ? meta.legacy_offset.slice(0, 2) : null,
  };
  if (includeEditorMeta) {
    shape.editor_hidden = object.visible === false;
    shape.editor_locked = Boolean(meta.locked);
    shape.editor_group_id = meta.group_id || null;
    shape.editor_group_name = meta.group_name || null;
  }
  return shape;
}

function snapshotShapes() {
  return vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: true }));
}

function currentEditorGroupIds() {
  return new Set(vinylObjects().map((obj) => obj.kloudy?.group_id).filter(Boolean).map(String));
}

function pruneCollapsedLayerGroups() {
  const existing = currentEditorGroupIds();
  collapsedLayerGroups = new Set([...collapsedLayerGroups].filter((groupId) => existing.has(String(groupId))));
}

function collapsedLayerGroupIds() {
  pruneCollapsedLayerGroups();
  return [...collapsedLayerGroups];
}

function applyCollapsedLayerGroups(groupIds) {
  collapsedLayerGroups = new Set((Array.isArray(groupIds) ? groupIds : []).filter(Boolean).map(String));
  pruneCollapsedLayerGroups();
}

function persistCollapsedLayerState() {
  const collapsed = collapsedLayerGroupIds();
  if (historyIndex >= 0 && history[historyIndex]) {
    try {
      const state = JSON.parse(history[historyIndex]);
      state.editor_collapsed_groups = collapsed;
      history[historyIndex] = JSON.stringify(state);
    } catch (_err) {
      // Keep collapse state best-effort; geometry history remains valid.
    }
  }
  try {
    writeAutosavePayload(autosavePayloadFromState(snapshotEditorState()));
  } catch (err) {
    console.warn("Collapsed layer autosave skipped.", err);
  }
}

function snapshotEditorState() {
  return {
    version: 2,
    shapes: snapshotShapes(),
    editor_guides: savedGuideState(),
    editor_collapsed_groups: collapsedLayerGroupIds(),
  };
}

async function restoreShapes(shapes, options = {}) {
  const previousCollapsed = new Set(collapsedLayerGroups);
  historyLocked = true;
  clearVinylObjects({ preserveCollapsed: true });
  for (const shape of shapes) {
    const object = await makeFabricObject(shape);
    canvas.add(object);
  }
  if (Array.isArray(options.collapsedGroups)) applyCollapsedLayerGroups(options.collapsedGroups);
  else {
    collapsedLayerGroups = previousCollapsed;
    pruneCollapsedLayerGroups();
  }
  bringGuidesToBack();
  historyLocked = false;
  refreshLayers();
  syncCanvasObjectCoords();
  canvas.requestRenderAll();
}

async function restoreEditorState(snapshot) {
  const state = Array.isArray(snapshot)
    ? { shapes: snapshot, editor_guides: null }
    : (snapshot && typeof snapshot === "object" ? snapshot : {});
  await restoreShapes(Array.isArray(state.shapes) ? state.shapes : []);
  applySavedGuideState(state.editor_guides || null);
}

function resetHistory() {
  history = [];
  historyIndex = -1;
  protectedHistoryIndex = -1;
}

function autosavePayloadFromState(state) {
  return {
    format: "kloudy_fabric_editor_autosave_v1",
    name: cleanProjectBaseName(loadedName, "autosave"),
    saved_at: new Date().toISOString(),
    shapes: Array.isArray(state?.shapes) ? state.shapes : [],
    editor_guides: state?.editor_guides || savedGuideState(),
    editor_collapsed_groups: Array.isArray(state?.editor_collapsed_groups) ? state.editor_collapsed_groups : collapsedLayerGroupIds(),
  };
}

function writeAutosavePayload(payload) {
  if (!payload || !Array.isArray(payload.shapes)) return false;
  let localOk = true;
  try {
    localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(payload));
  } catch (err) {
    localOk = false;
    console.warn("Browser autosave skipped.", err);
  }
  pendingAutosavePayload = payload;
  if (!autosaveWriteTimer) {
    autosaveWriteTimer = setTimeout(() => {
      const nextPayload = pendingAutosavePayload;
      pendingAutosavePayload = null;
      autosaveWriteTimer = null;
      if (!nextPayload) return;
      fetch(EDITOR_AUTOSAVE_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextPayload),
      }).catch((err) => {
        console.warn("App-folder autosave skipped.", err);
      });
    }, 350);
  }
  return localOk;
}

function clearAutosave() {
  pendingAutosavePayload = null;
  if (autosaveWriteTimer) {
    clearTimeout(autosaveWriteTimer);
    autosaveWriteTimer = null;
  }
  try {
    localStorage.removeItem(AUTOSAVE_KEY);
  } catch (_err) {
    // Ignore storage cleanup failures.
  }
  fetch(EDITOR_AUTOSAVE_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "clear", shapes: [] }),
  }).catch(() => {
    // Direct-file/browser fallback.
  });
}

function pushHistory(reason = "change") {
  if (historyLocked) return;
  const snapshot = JSON.stringify(snapshotEditorState());
  if (history[historyIndex] === snapshot) return;
  history = history.slice(0, historyIndex + 1);
  history.push(snapshot);
  if (history.length > 80) {
    history.shift();
    if (protectedHistoryIndex >= 0) protectedHistoryIndex = Math.max(0, protectedHistoryIndex - 1);
  }
  historyIndex = history.length - 1;
  let autosaveOk = true;
  try {
    const state = JSON.parse(snapshot);
    autosaveOk = writeAutosavePayload(autosavePayloadFromState(state));
  } catch (err) {
    autosaveOk = false;
    console.warn("Autosave skipped.", err);
  }
  setStatus(`Saved ${reason}.${autosaveOk ? " Autosave updated." : " Autosave skipped because browser storage is full."}`);
}

function ensureHistoryBaseline() {
  if (historyLocked || historyIndex >= 0) return;
  history = [JSON.stringify(snapshotEditorState())];
  historyIndex = 0;
  protectedHistoryIndex = -1;
}

async function undo() {
  const floor = Math.max(0, protectedHistoryIndex);
  if (historyIndex <= floor) {
    setStatus(protectedHistoryIndex >= 0 ? "Undo stopped at loaded source." : "Nothing to undo.");
    return;
  }
  historyIndex--;
  await restoreEditorState(JSON.parse(history[historyIndex]));
  setStatus("Undo.");
}

async function redo() {
  if (historyIndex >= history.length - 1) return;
  historyIndex++;
  await restoreEditorState(JSON.parse(history[historyIndex]));
  setStatus("Redo.");
}

function round(value) {
  const n = Math.round(Number(value) * 1000000) / 1000000;
  return Math.abs(n - Math.round(n)) < 0.000001 ? Math.round(n) : n;
}

function requestCanvasRender() {
  if (!canvas || canvasRenderFrame) return;
  canvasRenderFrame = requestAnimationFrame(() => {
    canvasRenderFrame = null;
    canvas.requestRenderAll();
  });
}

function syncCanvasObjectCoords() {
  if (!canvas) return;
  canvas.calcOffset();
  canvas.getObjects().forEach((object) => object.setCoords?.());
  canvas.getActiveObject()?.setCoords?.();
}

function finishCanvasPan() {
  if (!canvas || !isPanning) return;
  // Direct viewportTransform mutation is fast while dragging, but Fabric needs
  // the transform re-applied before hit-testing lines up with the rendered view.
  canvas.setViewportTransform(canvas.viewportTransform);
  syncCanvasObjectCoords();
  updateVisualGridLayer();
  canvas.requestRenderAll();
}

function scheduleCanvasGeometrySync() {
  if (!canvas || canvasGeometryFrame) return;
  canvasGeometryFrame = requestAnimationFrame(() => {
    canvasGeometryFrame = null;
    resizeCanvas();
    syncCanvasObjectCoords();
    canvas.requestRenderAll();
    updateHud();
  });
}

function initCanvas() {
  configureEditorTransformControls();
  const canvasBg = getComputedStyle(document.documentElement).getPropertyValue("--fabric-canvas-bg").trim() || "#fffefe";
  canvas = new fabric.Canvas("canvas", {
    preserveObjectStacking: true,
    selection: true,
    selectionKey: "shiftKey",
    fireRightClick: true,
    stopContextMenu: true,
    backgroundColor: canvasBg,
    renderOnAddRemove: false,
    enableRetinaScaling: false,
    skipOffscreen: true,
    perPixelTargetFind: true,
    targetFindTolerance: VINYL_HIT_TOLERANCE,
    defaultCursor: "default",
    hoverCursor: "default",
    moveCursor: "move",
    freeDrawingCursor: "default",
  });
  styleAllTransformControls();
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  const wrap = document.querySelector(".canvasStage") || document.querySelector(".canvasWrap");
  if (window.ResizeObserver && wrap) {
    canvasResizeObserver?.disconnect?.();
    canvasResizeObserver = new ResizeObserver(() => scheduleCanvasGeometrySync());
    canvasResizeObserver.observe(wrap);
  }
  ["mousedown", "pointerdown", "touchstart"].forEach((eventName) => {
    canvas.upperCanvasEl?.addEventListener(eventName, () => canvas.calcOffset(), { capture: true, passive: true });
  });
  resetView();
  canvas.on("selection:created", handleSelectionChanged);
  canvas.on("selection:updated", handleSelectionChanged);
  canvas.on("selection:cleared", () => {
    if (selectionLockActive && !selectionLockRestoring) {
      requestAnimationFrame(() => restoreSelectionLock("a canvas misclick"));
      return;
    }
    clearSnapOverlay();
    updateSelectionPanel();
  });
  canvas.on("object:added", (event) => {
    if (event.target?.kloudy) {
      invalidateLayerStats();
      styleObjectTransformControls(event.target);
      event.target.setCoords();
    }
  });
  canvas.on("object:removed", (event) => {
    if (event.target?.kloudy) invalidateLayerStats();
  });
  canvas.on("object:modified", (event) => {
    if (event.target?.kloudyOverlay) {
      constrainSourceOverlayTransform();
      clearSnapOverlay();
      updateHud();
      setStatus("Source overlay moved. It remains reference-only and will not export.");
      return;
    }
    mirrorActiveMaskProxyToOwner();
    transformAnchorSnapshot = null;
    clearSnapOverlay();
    syncCanvasObjectCoords();
    selectedVinylObjects().forEach(updateObjectScaleSigns);
    selectedVinylObjects().forEach(rememberFontShapeTransform);
    syncMaskPreviewOutlines();
    if ($("autoOverlayColor")?.checked) {
      selectedVinylObjects().forEach((obj) => applyOverlayColorToObject(obj, { remember: true, silent: true }));
    }
    updateSelectionPanel();
    scheduleRefreshLayers();
    pushHistory("object edit");
  });
  canvas.on("object:moving", (event) => {
    if (event.target?.kloudyOverlay) {
      constrainSourceOverlayTransform();
      snapSourceOverlayToGuides(event);
      return;
    }
    leaveGuideModeForLayerEdit();
    const target = interactiveVinylTarget(event.target);
    if (target !== event.target) mirrorMaskProxyToOwner(event.target);
    applyDragAxisLock(target);
    snapTargetToGuides(target, { ...event, kloudyTransformAction: "move" });
    applyDragAxisLock(target);
    if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
    syncMaskPreviewForTarget(target);
    scheduleLiveOverlayColor(target);
  });
  ["object:scaling", "object:skewing"].forEach((eventName) => {
    canvas.on(eventName, (event) => {
      if (event.target?.kloudyOverlay) {
        constrainSourceOverlayTransform();
        snapSourceOverlayToGuides(event);
        return;
      }
      leaveGuideModeForLayerEdit();
      const target = interactiveVinylTarget(event.target);
      if (target !== event.target) mirrorMaskProxyToOwner(event.target);
      snapTargetToGuides(target, { ...event, kloudyTransformAction: eventName === "object:scaling" ? "scale" : "skew" });
      if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
      syncMaskPreviewForTarget(target);
      scheduleLiveOverlayColor(target);
    });
  });
  canvas.on("object:rotating", (event) => {
    if (event.target?.kloudyOverlay) {
      constrainSourceOverlayTransform();
      return;
    }
    leaveGuideModeForLayerEdit();
    const target = interactiveVinylTarget(event.target);
    if (target !== event.target) mirrorMaskProxyToOwner(event.target);
    snapRotationToNotches(target, event);
    renderRotationNotchOverlay(target, event);
    if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
    syncMaskPreviewForTarget(target);
    scheduleLiveOverlayColor(target);
  });
  canvas.on("mouse:wheel", (opt) => {
    const delta = opt.e.deltaY;
    let zoom = canvas.getZoom();
    zoom *= 0.999 ** delta;
    zoom = Math.min(Math.max(zoom, 0.04), 8);
    canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
    styleActiveTransformControls();
    syncSelectedShapeOutlines();
    scheduleVisualGridLayerUpdate();
    updateHud(canvas.getPointer(opt.e));
    requestCanvasRender();
    opt.e.preventDefault();
    opt.e.stopPropagation();
  });
  canvas.on("mouse:down", (opt) => {
    if (vBoxSelectActive && activeToolMode !== "guides" && activeToolMode !== "source" && !shapeEyedropperActive && opt.e.button === 0) {
      opt.target = null;
      canvas.skipTargetFind = true;
      canvas.selection = true;
      transformAnchorSnapshot = null;
      return;
    }
    if (activeToolMode === "guides") {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      cancelFabricGroupSelection();
      if (opt.e.button === 1 || opt.e.button === 2) {
        guideDraft = null;
        isPanning = true;
        lastPan = { x: opt.e.clientX, y: opt.e.clientY };
        canvas.selection = false;
        canvas.skipTargetFind = true;
        transformAnchorSnapshot = null;
        setGuideStatus("Guide mode: panning canvas. Left-drag still draws guide lines.");
        return;
      }
      if (selectGuideObject(opt.target)) return;
      beginGuideDraft(opt);
      return;
    }
    if (activeToolMode === "source") {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      if (opt.e.button === 1 || opt.e.button === 2) {
        isPanning = true;
        lastPan = { x: opt.e.clientX, y: opt.e.clientY };
        canvas.selection = false;
        canvas.skipTargetFind = true;
        transformAnchorSnapshot = null;
        setStatus("Source Move mode: panning canvas. Left-drag the source overlay to move it.");
        return;
      }
      if (!overlayImage) {
        canvas.discardActiveObject();
        setStatus("Source Move mode needs an overlay first. Add one in Overlay controls.");
        return;
      }
      canvas.selection = false;
      transformAnchorSnapshot = null;
      if (opt.target !== overlayImage) {
        canvas.setActiveObject(overlayImage);
        setStatus("Source Move mode only edits the source overlay. Drag the overlay itself to move it.");
      }
      return;
    }
    if (shapeEyedropperActive) {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      pickShapeColorFromEvent(opt);
      return;
    }
    if (opt.e.button === 1 || opt.e.button === 2) {
      isPanning = true;
      lastPan = { x: opt.e.clientX, y: opt.e.clientY };
      canvas.selection = false;
      canvas.skipTargetFind = true;
      transformAnchorSnapshot = null;
    } else if (interactiveVinylTarget(opt.target)?.kloudy || opt.target?.type === "activeSelection" || opt.target?.type === "activeselection") {
      const target = interactiveVinylTarget(opt.target);
      captureTransformAnchorSnapshot(target, opt);
      captureDragAxisSnapshot(target);
    } else {
      transformAnchorSnapshot = null;
      dragAxisSnapshot = null;
    }
  });
  canvas.on("mouse:move", (opt) => {
    if (isPanning && lastPan) {
      const vpt = canvas.viewportTransform;
      vpt[4] += opt.e.clientX - lastPan.x;
      vpt[5] += opt.e.clientY - lastPan.y;
      scheduleVisualGridLayerUpdate();
      requestCanvasRender();
      lastPan = { x: opt.e.clientX, y: opt.e.clientY };
      schedulePointerHud(canvas.getPointer(opt.e), null, "panning");
      return;
    }
    if (guideDraft && activeToolMode === "guides") {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      canvas.selection = false;
      canvas._groupSelector = null;
      updateGuideDraft(opt);
      schedulePointerHud(canvas.getPointer(opt.e));
      return;
    }
  });
  canvas.on("mouse:move", (opt) => {
    if (!isPanning && opt?.e) {
      schedulePointerHud(canvas.getPointer(opt.e), opt.target);
    }
  });
  canvas.on("mouse:up", () => {
    if (guideDraft && activeToolMode === "guides") {
      finishGuideDraft();
    }
    if (activeToolMode === "guides") canvas._groupSelector = null;
    transformAnchorSnapshot = null;
    dragAxisSnapshot = null;
    clearDragAxisLock();
    clearSnapOverlay();
    finishCanvasPan();
    isPanning = false;
    canvas.selection = !shapeEyedropperActive && activeToolMode !== "guides" && activeToolMode !== "source";
    canvas.skipTargetFind = vBoxSelectActive;
    canvas.defaultCursor = vBoxSelectActive ? "crosshair" : "default";
    canvas.hoverCursor = vBoxSelectActive ? "crosshair" : "default";
    updateHud();
  });
}

function resizeCanvas() {
  const wrap = document.querySelector(".canvasStage") || document.querySelector(".canvasWrap");
  if (!wrap || !canvas) return;
  const rect = wrap.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  if (width !== lastCanvasSize.width || height !== lastCanvasSize.height) {
    canvas.setDimensions({ width, height });
    lastCanvasSize = { width, height };
  }
  syncCanvasObjectCoords();
  updateVisualGridLayer();
  canvas.requestRenderAll();
  updateHud();
}

/*
 * The FH6 bounds guides are intentionally disabled. They were visual-only and
 * never exported, but the editor is easier to use as an open canvas.
 */
function drawBounds() {
  const group = [];
  const bounds = new fabric.Rect({
    left: FH6_BOUNDS.left,
    top: FH6_BOUNDS.top,
    width: FH6_BOUNDS.width,
    height: FH6_BOUNDS.height,
    fill: "rgba(255,255,255,0.035)",
    stroke: "#6ee7ff",
    strokeWidth: 3,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  const xAxis = new fabric.Line([-1200, 0, 1200, 0], {
    stroke: "rgba(255,255,255,0.22)",
    strokeWidth: 1,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  const yAxis = new fabric.Line([0, -1200, 0, 1200], {
    stroke: "rgba(255,255,255,0.22)",
    strokeWidth: 1,
    selectable: false,
    evented: false,
    excludeFromExport: true,
  });
  group.push(bounds, xAxis, yAxis);
  group.forEach((item) => {
    item.kloudyGuide = true;
    canvas.add(item);
    item.sendToBack();
  });
}

function editorGuideObjects() {
  return canvas ? canvas.getObjects().filter((obj) => obj.kloudyGuide) : [];
}

function clampGuideSize(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 50;
  return Math.max(5, Math.min(500, numeric));
}

function cloneGuidesForSave() {
  return guideState.guides.map((guide) => ({
    id: String(guide.id),
    x1: round(guide.x1),
    y1: round(guide.y1),
    x2: round(guide.x2),
    y2: round(guide.y2),
    constraint: ["free", "horizontal", "vertical"].includes(guide.constraint) ? guide.constraint : "free",
  }));
}

function savedGuideState() {
  return {
    version: 1,
    gridEnabled: Boolean(guideState.gridEnabled),
    gridSize: clampGuideSize(guideState.gridSize),
    gridOpacity: Math.max(5, Math.min(65, Number(guideState.gridOpacity) || 20)),
    guidesVisible: Boolean(guideState.guidesVisible),
    snapGuides: Boolean(guideState.snapGuides),
    snapGrid: Boolean(guideState.snapGrid),
    snapCtrlOnly: Boolean(guideState.snapCtrlOnly),
    snapThreshold: Math.max(4, Math.min(28, Number(guideState.snapThreshold) || 12)),
    guideConstraint: guideState.guideConstraint || "free",
    snapGuideAnchor: Boolean(guideState.snapGuideAnchor),
    snapGuideEnd: Boolean(guideState.snapGuideEnd),
    guides: cloneGuidesForSave(),
  };
}

function applySavedGuideState(saved = null) {
  const next = defaultGuideState();
  if (saved && typeof saved === "object") {
    next.gridEnabled = Boolean(saved.gridEnabled);
    next.gridSize = clampGuideSize(saved.gridSize);
    next.gridOpacity = Math.max(5, Math.min(65, Number(saved.gridOpacity) || next.gridOpacity));
    next.guidesVisible = saved.guidesVisible !== false;
    next.snapGuides = saved.snapGuides !== false;
    next.snapGrid = saved.snapGrid !== false;
    next.snapCtrlOnly = saved.snapCtrlOnly !== false;
    next.snapThreshold = Math.max(4, Math.min(28, Number(saved.snapThreshold) || next.snapThreshold));
    next.guideConstraint = ["free", "horizontal", "vertical"].includes(saved.guideConstraint) ? saved.guideConstraint : next.guideConstraint;
    next.snapGuideAnchor = saved.snapGuideAnchor === true;
    next.snapGuideEnd = Boolean(saved.snapGuideEnd);
    next.guides = Array.isArray(saved.guides)
      ? saved.guides.map((guide) => ({
        id: String(guide.id || `guide-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`),
        x1: Number(guide.x1) || 0,
        y1: Number(guide.y1) || 0,
        x2: Number(guide.x2) || 0,
        y2: Number(guide.y2) || 0,
        constraint: ["free", "horizontal", "vertical"].includes(guide.constraint) ? guide.constraint : "free",
      })).filter((guide) => Math.hypot(guide.x2 - guide.x1, guide.y2 - guide.y1) > 0.001)
      : [];
  }
  guideState = next;
  selectedGuideId = null;
  applyGuideStateToUi();
  renderGuideObjects();
}

function guideLineStyle(guide, extra = {}) {
  const selected = guide.id && guide.id === selectedGuideId;
  const manual = !guide.grid;
  const gridOpacity = Math.max(0.08, Math.min(0.85, guideState.gridOpacity / 100));
  const gridColor = cssColorVar("--editor-grid-line", "rgba(80, 72, 92, 0.42)").replace(/,\s*[0-9.]+\)$/, `, ${gridOpacity})`);
  const axisColor = cssColorVar("--editor-grid-axis", "rgba(40, 36, 48, 0.62)");
  return {
    stroke: selected
      ? cssColorVar("--editor-guide-selected", "rgba(40, 32, 44, 0.98)")
      : (manual ? cssColorVar("--editor-guide-line", "rgba(94, 52, 72, 0.92)") : (guide.axisGuide ? axisColor : gridColor)),
    strokeWidth: selected ? 3 : (manual ? 2 : 1),
    strokeDashArray: manual ? (selected ? [8, 5] : [6, 5]) : null,
    strokeUniform: true,
    selectable: manual && activeToolMode === "guides",
    evented: manual && activeToolMode === "guides",
    hasControls: false,
    hasBorders: false,
    lockMovementX: true,
    lockMovementY: true,
    hoverCursor: manual ? "pointer" : "default",
    objectCaching: true,
    excludeFromExport: true,
    ...extra,
  };
}

function makeGuideLine(guide, extra = {}) {
  const line = new fabric.Line([guide.x1, guide.y1, guide.x2, guide.y2], guideLineStyle(guide, extra));
  line.kloudyGuide = true;
  line.kloudyGuideManual = !guide.grid;
  line.kloudyGridLine = Boolean(guide.grid);
  line.axisGuide = Boolean(guide.axisGuide);
  line.kloudyGuideId = guide.id || null;
  return line;
}

function visibleCanvasBounds(pad = 80) {
  const inverse = fabric.util.invertTransform(canvas.viewportTransform);
  const corners = [
    fabric.util.transformPoint(new fabric.Point(0, 0), inverse),
    fabric.util.transformPoint(new fabric.Point(canvas.width, 0), inverse),
    fabric.util.transformPoint(new fabric.Point(0, canvas.height), inverse),
    fabric.util.transformPoint(new fabric.Point(canvas.width, canvas.height), inverse),
  ];
  return {
    minX: Math.min(...corners.map((p) => p.x)) - pad,
    maxX: Math.max(...corners.map((p) => p.x)) + pad,
    minY: Math.min(...corners.map((p) => p.y)) - pad,
    maxY: Math.max(...corners.map((p) => p.y)) + pad,
  };
}

function updateVisualGridLayer() {
  const layer = $("editorGridLayer");
  if (!layer || !canvas) return;
  if (!guideState.gridEnabled) {
    layer.hidden = true;
    layer.style.backgroundImage = "";
    return;
  }
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  let step = clampGuideSize(guideState.gridSize);
  while (step * zoom < 10) step *= 2;
  const screenStep = Math.max(2, step * zoom);
  const vpt = canvas.viewportTransform || [zoom, 0, 0, zoom, 0, 0];
  const gridOpacity = Math.max(0.08, Math.min(0.85, guideState.gridOpacity / 100));
  const gridColor = colorWithAlpha(cssColorVar("--editor-grid-line", "rgba(80, 72, 92, 0.42)"), gridOpacity);
  const axisColor = cssColorVar("--editor-grid-axis", "rgba(40, 36, 48, 0.62)");
  const width = Math.max(1, canvas.width || layer.clientWidth || 1);
  const height = Math.max(1, canvas.height || layer.clientHeight || 1);
  const xOffset = positiveModulo(vpt[4] || 0, screenStep);
  const yOffset = positiveModulo(vpt[5] || 0, screenStep);
  const backgrounds = [
    `linear-gradient(to right, ${gridColor} 1px, transparent 1px)`,
    `linear-gradient(to bottom, ${gridColor} 1px, transparent 1px)`,
  ];
  const sizes = [
    `${screenStep}px ${screenStep}px`,
    `${screenStep}px ${screenStep}px`,
  ];
  const positions = [
    `${xOffset}px 0px`,
    `0px ${yOffset}px`,
  ];
  const axisX = vpt[4] || 0;
  const axisY = vpt[5] || 0;
  if (axisX >= 0 && axisX <= width) {
    backgrounds.unshift(`linear-gradient(to right, transparent ${Math.max(0, axisX - 1)}px, ${axisColor} ${Math.max(0, axisX - 1)}px, ${axisColor} ${axisX + 1}px, transparent ${axisX + 1}px)`);
    sizes.unshift("100% 100%");
    positions.unshift("0 0");
  }
  if (axisY >= 0 && axisY <= height) {
    backgrounds.unshift(`linear-gradient(to bottom, transparent ${Math.max(0, axisY - 1)}px, ${axisColor} ${Math.max(0, axisY - 1)}px, ${axisColor} ${axisY + 1}px, transparent ${axisY + 1}px)`);
    sizes.unshift("100% 100%");
    positions.unshift("0 0");
  }
  layer.hidden = false;
  layer.style.backgroundImage = backgrounds.join(", ");
  layer.style.backgroundSize = sizes.join(", ");
  layer.style.backgroundPosition = positions.join(", ");
}

function scheduleVisualGridLayerUpdate() {
  if (visualGridFrame) return;
  visualGridFrame = requestAnimationFrame(() => {
    visualGridFrame = null;
    updateVisualGridLayer();
  });
}

function renderGuideObjects() {
  if (!canvas) return;
  canvas.getObjects().filter((obj) => obj.kloudyGuide).forEach((obj) => canvas.remove(obj));
  snapOverlayObjects = [];
  const objects = [];
  updateVisualGridLayer();
  if (guideState.guidesVisible) {
    guideState.guides.forEach((guide) => objects.push(makeGuideLine(guide)));
  }
  if (guideDraft) {
    objects.push(makeGuideLine({ ...guideDraft, id: "__draft__" }, {
      stroke: cssColorVar("--editor-guide-draft", "rgba(42, 26, 36, 0.96)"),
      strokeWidth: 2,
      strokeDashArray: [3, 3],
      selectable: false,
      evented: false,
    }));
  }
  objects.forEach((obj) => canvas.add(obj));
  layerEditorHelpers();
  updateGuideUi();
  canvas.requestRenderAll();
}

function queueGuideRender() {
  if (guideRenderQueued) return;
  guideRenderQueued = true;
  requestAnimationFrame(() => {
    guideRenderQueued = false;
    renderGuideObjects();
  });
}

function layerEditorHelpers() {
  if (overlayImage && canvas.getObjects().includes(overlayImage)) {
    if (overlayLayerMode === "above") overlayImage.bringToFront();
    else overlayImage.sendToBack();
  }
  syncMaskPreviewOutlines();
  editorGuideObjects().forEach((obj) => obj.bringToFront());
}

function bringGuidesToBack() {
  layerEditorHelpers();
}

function setOverlayLayerMode(mode) {
  overlayLayerMode = normalizeOverlayLayerMode(mode);
  localStorage.setItem(OVERLAY_LAYER_MODE_KEY, overlayLayerMode);
  if ($("overlayLayerMode")) $("overlayLayerMode").value = overlayLayerMode;
  layerEditorHelpers();
  canvas?.requestRenderAll();
  setStatus(`Overlay draws ${overlayLayerMode === "above" ? "above" : "below"} vinyl layers.`);
}

function cancelFabricGroupSelection() {
  if (!canvas) return;
  canvas.selection = false;
  canvas._groupSelector = null;
  canvas.discardActiveObject();
}

function updateGuideInteractivity() {
  const inGuideMode = activeToolMode === "guides";
  document.body.classList.toggle("guideMode", inGuideMode);
  if (canvas) {
    editorGuideObjects().forEach((obj) => {
      if (!obj.kloudyGuideManual) return;
      obj.set({
        selectable: inGuideMode,
        evented: inGuideMode,
        hoverCursor: inGuideMode ? "pointer" : "default",
      });
    });
    canvas.selection = !shapeEyedropperActive && !inGuideMode && activeToolMode !== "source";
    if (inGuideMode) canvas._groupSelector = null;
    canvas.requestRenderAll();
  }
  updateGuideUi();
}

function configureOverlayForSourceMode(enabled) {
  if (!overlayImage) return;
  overlayImage.set({
    selectable: Boolean(enabled),
    evented: Boolean(enabled),
    hasControls: false,
    hasBorders: Boolean(enabled),
    lockMovementX: false,
    lockMovementY: false,
    lockScalingX: true,
    lockScalingY: true,
    lockSkewingX: true,
    lockSkewingY: true,
    lockRotation: true,
    lockScalingFlip: true,
    perPixelTargetFind: false,
    targetFindTolerance: enabled ? 16 : 0,
    hoverCursor: enabled ? "move" : "default",
    moveCursor: enabled ? "move" : "move",
    borderColor: cssColorVar("--editor-guide-selected", "#2b1622"),
    cornerColor: cssColorVar("--editor-selection-corner", "#ffffff"),
    cornerStrokeColor: cssColorVar("--editor-selection-corner-stroke", "#2b1622"),
    cornerStyle: "rect",
    transparentCorners: false,
    cornerSize: 16,
    padding: 8,
  });
}

function updateSourceInteractivity() {
  if (!canvas) return;
  const inSourceMode = activeToolMode === "source";
  document.body.classList.toggle("sourceMoveMode", inSourceMode);
  vinylObjects().forEach((obj) => {
    const interactive = !inSourceMode && !obj.kloudy?.locked;
    obj.set({
      selectable: interactive,
      evented: interactive,
      hasControls: interactive,
      hoverCursor: interactive ? "pointer" : "default",
      moveCursor: interactive ? "move" : "default",
    });
  });
  maskPreviewOutlines.forEach((helper) => {
    const owner = helper.kloudyMaskOwner;
    const interactive = !inSourceMode && !owner?.kloudy?.locked && Boolean(helper.kloudyMaskOutline);
    helper.set({
      selectable: interactive,
      evented: interactive,
      hasControls: interactive,
      hoverCursor: interactive ? "move" : "default",
      moveCursor: interactive ? "move" : "default",
    });
  });
  configureOverlayForSourceMode(inSourceMode);
  if (inSourceMode) {
    canvas.selection = false;
    canvas.skipTargetFind = false;
    if (overlayImage) canvas.setActiveObject(overlayImage);
    else canvas.discardActiveObject();
  }
  layerEditorHelpers();
  canvas.requestRenderAll();
}

function constrainSourceOverlayTransform() {
  if (!overlayImage) return;
  const scale = Math.max(0.001, Math.max(Math.abs(Number(overlayImage.scaleX) || 1), Math.abs(Number(overlayImage.scaleY) || 1)));
  overlayImage.set({
    scaleX: scale,
    scaleY: scale,
    skewX: 0,
    skewY: 0,
    flipX: false,
    flipY: false,
  });
  overlayImage.setCoords();
}

function snapSourceOverlayToGuides(event = null) {
  if (!overlayImage || activeToolMode !== "source") return false;
  constrainSourceOverlayTransform();
  const snappingEnabled = guideState.snapGuides || (guideState.gridEnabled && guideState.snapGrid);
  if (!snappingEnabled) {
    clearSnapOverlay();
    return false;
  }
  if (guideState.snapCtrlOnly && !eventHasSnapModifier(event)) {
    clearSnapOverlay();
    return false;
  }
  const rect = overlayImage.getBoundingRect(true, true);
  const xPoints = [
    { kind: "left", value: rect.left },
    { kind: "center", value: rect.left + rect.width / 2 },
    { kind: "right", value: rect.left + rect.width },
  ];
  const yPoints = [
    { kind: "top", value: rect.top },
    { kind: "middle", value: rect.top + rect.height / 2 },
    { kind: "bottom", value: rect.top + rect.height },
  ];
  const threshold = guideState.snapThreshold / Math.max(canvas.getZoom() || 1, 0.001);
  let bestX = null;
  let bestY = null;
  guideSnapLines().forEach((line) => {
    if (line.axis === "x") {
      xPoints.forEach((point) => {
        const delta = line.value - point.value;
        const abs = Math.abs(delta);
        if (abs <= threshold && (!bestX || abs < bestX.abs)) bestX = { delta, abs, point: point.kind, source: line.source };
      });
    } else if (line.axis === "y") {
      yPoints.forEach((point) => {
        const delta = line.value - point.value;
        const abs = Math.abs(delta);
        if (abs <= threshold && (!bestY || abs < bestY.abs)) bestY = { delta, abs, point: point.kind, source: line.source };
      });
    }
  });
  if (!bestX && !bestY) {
    clearSnapOverlay();
    return false;
  }
  overlayImage.set({
    left: (overlayImage.left || 0) + (bestX?.delta || 0),
    top: (overlayImage.top || 0) + (bestY?.delta || 0),
  });
  overlayImage.setCoords();
  clearSnapOverlay();
  const now = Date.now();
  if (now - lastSnapMessageAt > 350) {
    lastSnapMessageAt = now;
    setText("guideStatus", `Source snapped ${bestX ? bestX.point : ""}${bestX && bestY ? " + " : ""}${bestY ? bestY.point : ""} to ${bestX?.source || bestY?.source}.`);
  }
  return true;
}

function updateGuideUi() {
  setText("guideCountBadge", `${guideState.guides.length} guide${guideState.guides.length === 1 ? "" : "s"}`);
  setText("guideModeLabel", activeToolMode === "guides"
    ? (selectedGuideId ? "Guide selected. Delete it or draw another line." : "Drag on canvas to draw a guide.")
    : "Select the Guides tool to draw lines.");
}

function setGuideStatus(message) {
  setText("guideStatus", message);
  setStatus(message);
}

function snapValueToGrid(value) {
  const size = clampGuideSize(guideState.gridSize);
  return Math.round((Number(value) || 0) / size) * size;
}

function snapPointToGrid(point) {
  return { x: snapValueToGrid(point.x), y: snapValueToGrid(point.y) };
}

function constrainedGuideEnd(anchor, pointer, event = null) {
  let constraint = guideState.guideConstraint;
  if (event?.shiftKey && constraint === "free") {
    constraint = Math.abs(pointer.x - anchor.x) >= Math.abs(pointer.y - anchor.y) ? "horizontal" : "vertical";
  }
  const end = { ...pointer };
  if (guideState.snapGuideEnd) {
    const snapped = snapPointToGrid(end);
    end.x = snapped.x;
    end.y = snapped.y;
  }
  if (constraint === "horizontal") end.y = anchor.y;
  if (constraint === "vertical") end.x = anchor.x;
  return end;
}

function beginGuideDraft(opt) {
  const pointer = canvas.getPointer(opt.e);
  const anchor = guideState.snapGuideAnchor ? snapPointToGrid(pointer) : pointer;
  guideDraft = {
    id: "__draft__",
    x1: anchor.x,
    y1: anchor.y,
    x2: anchor.x,
    y2: anchor.y,
    constraint: guideState.guideConstraint,
  };
  selectedGuideId = null;
  renderGuideObjects();
}

function updateGuideDraft(opt) {
  if (!guideDraft) return;
  const pointer = canvas.getPointer(opt.e);
  const end = constrainedGuideEnd({ x: guideDraft.x1, y: guideDraft.y1 }, pointer, opt.e);
  guideDraft.x2 = end.x;
  guideDraft.y2 = end.y;
  renderGuideObjects();
}

function finishGuideDraft() {
  if (!guideDraft) return;
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const length = Math.hypot(guideDraft.x2 - guideDraft.x1, guideDraft.y2 - guideDraft.y1);
  if (length < 8 / zoom) {
    guideDraft = null;
    renderGuideObjects();
    setGuideStatus("Guide was too short and was discarded.");
    return;
  }
  const guide = {
    id: `guide-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    x1: guideDraft.x1,
    y1: guideDraft.y1,
    x2: guideDraft.x2,
    y2: guideDraft.y2,
    constraint: guideDraft.constraint,
  };
  ensureHistoryBaseline();
  guideState.guides.push(guide);
  selectedGuideId = guide.id;
  guideDraft = null;
  renderGuideObjects();
  pushHistory("add guide");
  setGuideStatus(`Added ${guide.constraint === "free" ? "free" : guide.constraint} guide. Hold Control while moving shapes to snap.`);
}

function selectGuideObject(object) {
  if (!object?.kloudyGuideManual) return false;
  selectedGuideId = object.kloudyGuideId;
  canvas.discardActiveObject();
  renderGuideObjects();
  setGuideStatus("Guide selected. Press Delete or use Delete Selected Guide to remove it.");
  return true;
}

function deleteSelectedGuide() {
  if (!selectedGuideId) {
    setGuideStatus("No guide selected. Switch to Guides and click a guide line first.");
    return;
  }
  ensureHistoryBaseline();
  const before = guideState.guides.length;
  guideState.guides = guideState.guides.filter((guide) => guide.id !== selectedGuideId);
  selectedGuideId = null;
  renderGuideObjects();
  if (before !== guideState.guides.length) {
    pushHistory("delete guide");
    setGuideStatus("Deleted selected guide.");
  } else {
    saveGuideAutosave();
    setGuideStatus("Selected guide was already gone.");
  }
}

function clearGuides() {
  const hadGuides = guideState.guides.length > 0 || guideDraft;
  if (hadGuides) ensureHistoryBaseline();
  guideState.guides = [];
  guideDraft = null;
  selectedGuideId = null;
  renderGuideObjects();
  if (hadGuides) pushHistory("clear guides");
  else saveGuideAutosave();
  setGuideStatus("Cleared guide lines. Grid settings were kept.");
}

function syncGuideStateFromUi() {
  guideState.gridEnabled = Boolean($("gridEnabled")?.checked);
  guideState.gridSize = clampGuideSize($("gridSize")?.value);
  guideState.gridOpacity = Math.max(5, Math.min(65, Number($("gridOpacity")?.value) || 20));
  guideState.guidesVisible = $("guidesVisible")?.checked !== false;
  guideState.snapGuides = $("snapGuides")?.checked !== false;
  guideState.snapGrid = $("snapGrid")?.checked !== false;
  guideState.snapCtrlOnly = $("snapCtrlOnly")?.checked !== false;
  guideState.snapThreshold = Math.max(4, Math.min(28, Number($("snapThreshold")?.value) || 12));
  guideState.guideConstraint = $("guideConstraint")?.value || "free";
  guideState.snapGuideAnchor = $("snapGuideAnchor")?.checked !== false;
  guideState.snapGuideEnd = Boolean($("snapGuideEnd")?.checked);
  renderGuideObjects();
  saveGuideAutosave();
}

function applyGuideStateToUi() {
  if ($("gridEnabled")) $("gridEnabled").checked = guideState.gridEnabled;
  if ($("gridSize")) $("gridSize").value = clampGuideSize(guideState.gridSize);
  if ($("gridOpacity")) $("gridOpacity").value = guideState.gridOpacity;
  if ($("guidesVisible")) $("guidesVisible").checked = guideState.guidesVisible;
  if ($("snapGuides")) $("snapGuides").checked = guideState.snapGuides;
  if ($("snapGrid")) $("snapGrid").checked = guideState.snapGrid;
  if ($("snapCtrlOnly")) $("snapCtrlOnly").checked = guideState.snapCtrlOnly;
  if ($("snapThreshold")) $("snapThreshold").value = guideState.snapThreshold;
  if ($("guideConstraint")) $("guideConstraint").value = guideState.guideConstraint;
  if ($("snapGuideAnchor")) $("snapGuideAnchor").checked = guideState.snapGuideAnchor;
  if ($("snapGuideEnd")) $("snapGuideEnd").checked = guideState.snapGuideEnd;
  updateGuideUi();
}

function saveGuideAutosave() {
  try {
    writeAutosavePayload(autosavePayloadFromState(snapshotEditorState()));
  } catch (err) {
    console.warn("Guide autosave skipped.", err);
  }
}

function normalizeDegrees(value) {
  const numeric = Number(value) || 0;
  return ((numeric % 360) + 360) % 360;
}

function guideLineAngleDegrees(line) {
  return normalizeDegrees(Math.atan2(line.y2 - line.y1, line.x2 - line.x1) * 180 / Math.PI);
}

function projectPointToSegment(point, line) {
  const dx = line.x2 - line.x1;
  const dy = line.y2 - line.y1;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq <= 0.000001) return null;
  const rawT = ((point.x - line.x1) * dx + (point.y - line.y1) * dy) / lengthSq;
  const t = Math.max(0, Math.min(1, rawT));
  return {
    x: line.x1 + dx * t,
    y: line.y1 + dy * t,
    t,
  };
}

function guideSnapLines() {
  const lines = [];
  const bounds = visibleCanvasBounds(300);
  if (guideState.snapGuides && guideState.guidesVisible) {
    guideState.guides.forEach((guide) => {
      const dx = Math.abs(guide.x2 - guide.x1);
      const dy = Math.abs(guide.y2 - guide.y1);
      if (dx < 0.001) lines.push({ axis: "x", value: guide.x1, source: "guide", x1: guide.x1, y1: guide.y1, x2: guide.x2, y2: guide.y2, angle: 90 });
      else if (dy < 0.001) lines.push({ axis: "y", value: guide.y1, source: "guide", x1: guide.x1, y1: guide.y1, x2: guide.x2, y2: guide.y2, angle: 0 });
      else lines.push({
        axis: "line",
        source: "guide",
        x1: guide.x1,
        y1: guide.y1,
        x2: guide.x2,
        y2: guide.y2,
        angle: guideLineAngleDegrees(guide),
      });
    });
  }
  if (guideState.gridEnabled && guideState.snapGrid) {
    const step = clampGuideSize(guideState.gridSize);
    const startX = Math.floor(bounds.minX / step) * step;
    const startY = Math.floor(bounds.minY / step) * step;
    for (let x = startX, count = 0; x <= bounds.maxX && count < 600; x += step, count++) {
      lines.push({ axis: "x", value: x, source: "grid", x1: x, y1: bounds.minY, x2: x, y2: bounds.maxY, angle: 90 });
    }
    for (let y = startY, count = 0; y <= bounds.maxY && count < 600; y += step, count++) {
      lines.push({ axis: "y", value: y, source: "grid", x1: bounds.minX, y1: y, x2: bounds.maxX, y2: y, angle: 0 });
    }
  }
  return lines;
}

function domEventFromFabricEvent(event = null) {
  return event?.e || event || null;
}

function eventHasSnapModifier(event = null) {
  const domEvent = domEventFromFabricEvent(event);
  return Boolean(event?.ctrlKey || event?.metaKey || domEvent?.ctrlKey || domEvent?.metaKey);
}

function transformActionFromEvent(event = null) {
  const explicit = event?.kloudyTransformAction;
  if (explicit) return String(explicit);
  const action = String(event?.transform?.action || event?.transform?.actionPerformed || "").toLowerCase();
  if (action.includes("skew")) return "skew";
  if (action.includes("scale") || action.includes("resize")) return "scale";
  if (action.includes("rotate")) return "rotate";
  return "move";
}

function canvasPointFromEvent(event = null) {
  const domEvent = domEventFromFabricEvent(event);
  const customPoint = event?.__kloudyPointer || domEvent?.__kloudyPointer;
  if (customPoint && Number.isFinite(Number(customPoint.x)) && Number.isFinite(Number(customPoint.y))) {
    return { x: Number(customPoint.x), y: Number(customPoint.y) };
  }
  if (!canvas || !domEvent) return null;
  const hasPointerCoordinates = ["clientX", "pageX", "offsetX", "x"].some((key) => Number.isFinite(Number(domEvent[key])));
  if (!hasPointerCoordinates) return null;
  try {
    return canvas.getPointer(domEvent);
  } catch (_err) {
    return null;
  }
}

function midpoint(a, b) {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function objectCornerCoords(target) {
  target.setCoords();
  const coords = target.aCoords || target.oCoords;
  if (coords?.tl && coords?.tr && coords?.bl && coords?.br) {
    const tl = { x: coords.tl.x, y: coords.tl.y };
    const tr = { x: coords.tr.x, y: coords.tr.y };
    const bl = { x: coords.bl.x, y: coords.bl.y };
    const br = { x: coords.br.x, y: coords.br.y };
    const center = midpoint(tl, br);
    return {
      tl,
      tr,
      bl,
      br,
      center,
      left: midpoint(tl, bl),
      right: midpoint(tr, br),
      top: midpoint(tl, tr),
      bottom: midpoint(bl, br),
    };
  }
  const rect = target.getBoundingRect(true, true);
  return {
    tl: { x: rect.left, y: rect.top },
    tr: { x: rect.left + rect.width, y: rect.top },
    bl: { x: rect.left, y: rect.top + rect.height },
    br: { x: rect.left + rect.width, y: rect.top + rect.height },
    center: { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 },
    left: { x: rect.left, y: rect.top + rect.height / 2 },
    right: { x: rect.left + rect.width, y: rect.top + rect.height / 2 },
    top: { x: rect.left + rect.width / 2, y: rect.top },
    bottom: { x: rect.left + rect.width / 2, y: rect.top + rect.height },
  };
}

function guideContactSegment(coords, kind) {
  if (kind === "left") return [coords.tl, coords.bl];
  if (kind === "right") return [coords.tr, coords.br];
  if (kind === "top") return [coords.tl, coords.tr];
  if (kind === "bottom") return [coords.bl, coords.br];
  if (kind === "tl") return [coords.tl, coords.tl];
  if (kind === "tr") return [coords.tr, coords.tr];
  if (kind === "bl") return [coords.bl, coords.bl];
  if (kind === "br") return [coords.br, coords.br];
  return null;
}

function guideContactPointForKind(coords, kind) {
  return coords[kind] || coords.center;
}

function transformControlKind(event = null) {
  const transform = event?.transform || null;
  const raw = transform?.corner || transform?.cornerName || transform?.control || transform?.action || event?.corner || null;
  const value = raw ? String(raw).toLowerCase() : "";
  if (["ml", "left", "scalex-left", "scalex"].includes(value)) return "left";
  if (["mr", "right", "scalex-right"].includes(value)) return "right";
  if (["mt", "top", "scaley-top", "scaley"].includes(value)) return "top";
  if (["mb", "bottom", "scaley-bottom"].includes(value)) return "bottom";
  if (["tl", "tr", "bl", "br"].includes(value)) return value;
  if (value.includes("left")) return "left";
  if (value.includes("right")) return "right";
  if (value.includes("top")) return "top";
  if (value.includes("bottom")) return "bottom";
  return null;
}

function pointerLocalToObject(target, point) {
  if (!target || !point) return null;
  try {
    const inverse = fabric.util.invertTransform(target.calcTransformMatrix());
    return fabric.util.transformPoint(new fabric.Point(point.x, point.y), inverse);
  } catch (_err) {
    return null;
  }
}

function quadrantFromLocalPoint(local) {
  if (!local) return null;
  return `${local.y >= 0 ? "bottom" : "top"}-${local.x >= 0 ? "right" : "left"}`;
}

function sideFromLocalPoint(target, local) {
  if (!local) return "center";
  const width = Math.max(Math.abs(Number(target.width) || 1), 1);
  const height = Math.max(Math.abs(Number(target.height) || 1), 1);
  const nx = local.x / (width / 2);
  const ny = local.y / (height / 2);
  return Math.abs(nx) >= Math.abs(ny)
    ? (nx >= 0 ? "right" : "left")
    : (ny >= 0 ? "bottom" : "top");
}

function guideContactForTarget(target, event = null, preferredKind = null) {
  if (!target) return null;
  const coords = objectCornerCoords(target);
  const controlKind = preferredKind || transformControlKind(event);
  if (controlKind && controlKind !== "center") {
    return {
      kind: controlKind,
      point: guideContactPointForKind(coords, controlKind),
      segment: guideContactSegment(coords, controlKind),
      quadrant: controlKind.length === 2 ? controlKind.replace("t", "top-").replace("b", "bottom-").replace("l", "left").replace("r", "right") : null,
      source: preferredKind ? "preserved" : "control",
    };
  }
  const pointer = canvasPointFromEvent(event);
  const local = pointerLocalToObject(target, pointer);
  const inferredKind = sideFromLocalPoint(target, local);
  if (inferredKind && inferredKind !== "center") {
    return {
      kind: inferredKind,
      point: guideContactPointForKind(coords, inferredKind),
      segment: guideContactSegment(coords, inferredKind),
      quadrant: quadrantFromLocalPoint(local),
      source: "pointer",
    };
  }
  return {
    kind: "center",
    point: coords.center,
    segment: null,
    quadrant: null,
    source: "center",
  };
}

function refreshedGuideContact(target, contact) {
  return guideContactForTarget(target, null, contact?.kind || "center");
}

function axisSnapContactKind(bestX = null, bestY = null) {
  const xKind = bestX?.point;
  const yKind = bestY?.point;
  if (xKind && yKind) {
    if (yKind === "top" && xKind === "left") return "tl";
    if (yKind === "top" && xKind === "right") return "tr";
    if (yKind === "bottom" && xKind === "left") return "bl";
    if (yKind === "bottom" && xKind === "right") return "br";
    if (yKind === "middle") return xKind;
    if (xKind === "center") return yKind;
  }
  return xKind || yKind || "center";
}

function oppositeContactKind(kind) {
  const map = {
    left: "right",
    right: "left",
    top: "bottom",
    bottom: "top",
    tl: "br",
    tr: "bl",
    bl: "tr",
    br: "tl",
  };
  return map[kind] || "center";
}

function captureTransformAnchorSnapshot(target, event = null) {
  if (!target || target.kloudyGuide || target.kloudyOverlay) {
    transformAnchorSnapshot = null;
    return null;
  }
  const initialContact = guideContactForTarget(target, event);
  transformAnchorSnapshot = {
    target,
    contactKind: initialContact?.kind && initialContact.kind !== "center" ? initialContact.kind : null,
    coords: objectCornerCoords(target),
    left: Number(target.left) || 0,
    top: Number(target.top) || 0,
    angle: Number(target.angle) || 0,
    scaleX: Number(target.scaleX) || 1,
    scaleY: Number(target.scaleY) || 1,
    skewX: Number(target.skewX) || 0,
    skewY: Number(target.skewY) || 0,
  };
  return transformAnchorSnapshot;
}

function captureDragAxisSnapshot(target) {
  if (!target || target.kloudyGuide || target.kloudyOverlay) {
    dragAxisSnapshot = null;
    return null;
  }
  dragAxisSnapshot = {
    target,
    left: Number(target.left) || 0,
    top: Number(target.top) || 0,
  };
  return dragAxisSnapshot;
}

function ensureDragAxisSnapshot(target) {
  if (!target || target.kloudyGuide || target.kloudyOverlay) return null;
  if (dragAxisSnapshot?.target !== target) return captureDragAxisSnapshot(target);
  return dragAxisSnapshot;
}

function applyDragAxisLock(target) {
  if (!target || !dragAxisLock) return false;
  const snapshot = ensureDragAxisSnapshot(target);
  if (!snapshot) return false;
  if (dragAxisLock === "x") {
    target.set({ top: snapshot.top });
  } else if (dragAxisLock === "y") {
    target.set({ left: snapshot.left });
  } else {
    return false;
  }
  target.setCoords();
  return true;
}

function setDragAxisLock(axis) {
  if (dragAxisLock === axis) return;
  dragAxisLock = axis;
  const label = axis === "x" ? "X / horizontal" : "Y / vertical";
  setStatus(`Axis lock active: ${label}. Release ${axis.toUpperCase()} to drag freely.`);
}

function clearDragAxisLock(axis = null) {
  if (axis && dragAxisLock !== axis) return;
  const hadLock = Boolean(dragAxisLock);
  dragAxisLock = null;
  if (hadLock) setStatus("Axis lock released.");
}

function ensureTransformAnchorSnapshot(target) {
  if (transformAnchorSnapshot?.target === target) return transformAnchorSnapshot;
  return null;
}

function stabilizeOppositeTransformAnchor(target, contact, transformAction) {
  if (transformAction !== "scale" && transformAction !== "skew") return null;
  if (!target || !contact || contact.kind === "center") return null;
  const snapshot = ensureTransformAnchorSnapshot(target);
  if (!snapshot || snapshot.target !== target) return null;
  const anchorKind = oppositeContactKind(contact.kind);
  const originalAnchor = guideContactPointForKind(snapshot.coords, anchorKind);
  if (!originalAnchor) return null;
  const currentCoords = objectCornerCoords(target);
  const currentAnchor = guideContactPointForKind(currentCoords, anchorKind);
  if (!currentAnchor) return null;
  const deltaX = originalAnchor.x - currentAnchor.x;
  const deltaY = originalAnchor.y - currentAnchor.y;
  if (Math.hypot(deltaX, deltaY) > 0.000001) {
    target.set({
      left: (target.left || 0) + deltaX,
      top: (target.top || 0) + deltaY,
    });
    target.setCoords();
  }
  return {
    anchorKind,
    originalAnchor,
    currentAnchor,
    deltaX,
    deltaY,
  };
}

function lineObjectForSnap(line) {
  if (!line) return null;
  if (line.axis === "line") return line;
  if (Number.isFinite(Number(line.x1)) && Number.isFinite(Number(line.y1)) && Number.isFinite(Number(line.x2)) && Number.isFinite(Number(line.y2))) return line;
  const bounds = visibleCanvasBounds(300);
  if (line.axis === "x") return { ...line, x1: line.value, y1: bounds.minY, x2: line.value, y2: bounds.maxY, angle: 90 };
  if (line.axis === "y") return { ...line, x1: bounds.minX, y1: line.value, x2: bounds.maxX, y2: line.value, angle: 0 };
  return null;
}

function distancePointToSnapLine(point, line) {
  if (!point || !line) return Infinity;
  if (line.axis === "x") return Math.abs(point.x - line.value);
  if (line.axis === "y") return Math.abs(point.y - line.value);
  const projected = projectPointToSegment(point, line);
  if (!projected) return Infinity;
  return Math.hypot(projected.x - point.x, projected.y - point.y);
}

function lineIntersection(a, b) {
  if (!a || !b) return null;
  const x1 = a.x1;
  const y1 = a.y1;
  const x2 = a.x2;
  const y2 = a.y2;
  const x3 = b.x1;
  const y3 = b.y1;
  const x4 = b.x2;
  const y4 = b.y2;
  const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(denom) < 0.000001) return null;
  return {
    x: ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom,
    y: ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom,
  };
}

function contactScaleAxis(contactKind) {
  if (contactKind === "left" || contactKind === "right") return "x";
  if (contactKind === "top" || contactKind === "bottom") return "y";
  return null;
}

function axisValueForContactPoint(point, axis) {
  if (!point) return null;
  if (axis === "x") return Number(point.x);
  if (axis === "y") return Number(point.y);
  return null;
}

function exactAxisResidual(point, line) {
  if (!point || !line || (line.axis !== "x" && line.axis !== "y")) return null;
  const value = axisValueForContactPoint(point, line.axis);
  if (!Number.isFinite(value)) return null;
  return Number(line.value) - value;
}

function refineAnchoredScaleSideToAxisLine(target, contact, line, maxIterations = 4) {
  const scaleAxis = contactScaleAxis(contact?.kind);
  if (!target || !contact || !line || line.axis !== scaleAxis) return null;
  for (let attempt = 0; attempt < maxIterations; attempt++) {
    const active = refreshedGuideContact(target, contact);
    const residual = exactAxisResidual(active?.point, line);
    if (residual === null) return null;
    if (Math.abs(residual) <= 0.0000001) return { contact: active, residual };
    const anchorResult = stabilizeOppositeTransformAnchor(target, contact, "scale");
    const anchor = anchorResult?.originalAnchor;
    if (!anchor) return { contact: active, residual };
    const axisComponent = scaleAxis === "x" ? active.point.x - anchor.x : active.point.y - anchor.y;
    const desiredComponent = Number(line.value) - (scaleAxis === "x" ? anchor.x : anchor.y);
    if (Math.abs(axisComponent) < 0.0000001) return { contact: active, residual };
    const factor = desiredComponent / axisComponent;
    if (!Number.isFinite(factor) || Math.abs(factor) < 0.02 || Math.abs(factor) > 50) return { contact: active, residual };
    if (scaleAxis === "x") target.set({ scaleX: (Number(target.scaleX) || 1) * factor });
    else target.set({ scaleY: (Number(target.scaleY) || 1) * factor });
    target.setCoords();
    stabilizeOppositeTransformAnchor(target, contact, "scale");
  }
  const contactAfter = refreshedGuideContact(target, contact);
  return { contact: contactAfter, residual: exactAxisResidual(contactAfter?.point, line) };
}

function finalizeAxisMoveSnap(target, bestX = null, bestY = null) {
  if (!target || (!bestX && !bestY)) return null;
  target.setCoords();
  const rect = target.getBoundingRect(true, true);
  let deltaX = 0;
  let deltaY = 0;
  if (bestX?.line?.axis === "x") {
    const xPoints = axisSnapPointsForLine(rect, { source: "control", kind: bestX.point }, bestX.line).xPoints;
    const point = xPoints.find((item) => item.kind === bestX.point) || xPoints[0];
    if (point) deltaX = Number(bestX.line.value) - Number(point.value);
  }
  if (bestY?.line?.axis === "y") {
    const yPoints = axisSnapPointsForLine(rect, { source: "control", kind: bestY.point }, bestY.line).yPoints;
    const point = yPoints.find((item) => item.kind === bestY.point) || yPoints[0];
    if (point) deltaY = Number(bestY.line.value) - Number(point.value);
  }
  if (Math.abs(deltaX) > 0.0000001 || Math.abs(deltaY) > 0.0000001) {
    target.set({
      left: (target.left || 0) + deltaX,
      top: (target.top || 0) + deltaY,
    });
    target.setCoords();
  }
  return { deltaX, deltaY };
}

function snapAnchoredScaleSideToAxisLine(target, contact, anchorResult, threshold) {
  if (!target || !contact || !anchorResult || contact.kind === "center") return null;
  const scaleAxis = contactScaleAxis(contact.kind);
  if (!scaleAxis) return null;
  const active = refreshedGuideContact(target, contact);
  const anchor = anchorResult.originalAnchor;
  if (!active?.point || !anchor) return null;
  let best = null;
  guideSnapLines().forEach((candidate) => {
    if (scaleAxis === "x" && candidate.axis !== "x") return;
    if (scaleAxis === "y" && candidate.axis !== "y") return;
    const line = lineObjectForSnap(candidate);
    if (!line) return;
    const distance = scaleAxis === "x"
      ? Math.abs(active.point.x - line.value)
      : Math.abs(active.point.y - line.value);
    if (distance > threshold) return;
    if (!best || distance < best.distance) best = { line, distance };
  });
  if (!best) return null;
  const axisVector = {
    x: active.point.x - anchor.x,
    y: active.point.y - anchor.y,
  };
  const axisLength = Math.hypot(axisVector.x, axisVector.y);
  if (axisLength < 0.000001) return null;
  const axisComponent = scaleAxis === "x" ? axisVector.x : axisVector.y;
  if (Math.abs(axisComponent) < 0.000001) return null;
  const desiredComponent = best.line.value - (scaleAxis === "x" ? anchor.x : anchor.y);
  const t = desiredComponent / axisComponent;
  if (!Number.isFinite(t) || t <= 0.01) return null;
  const intersection = {
    x: anchor.x + axisVector.x * t,
    y: anchor.y + axisVector.y * t,
  };
  const desiredVector = { x: intersection.x - anchor.x, y: intersection.y - anchor.y };
  const desiredDistance = (desiredVector.x * axisVector.x + desiredVector.y * axisVector.y) / axisLength;
  if (!Number.isFinite(desiredDistance) || desiredDistance <= 0.01) return null;
  const factor = desiredDistance / axisLength;
  if (!Number.isFinite(factor) || Math.abs(factor) < 0.02 || Math.abs(factor) > 50) return null;
  if (scaleAxis === "x") target.set({ scaleX: (Number(target.scaleX) || 1) * factor });
  else target.set({ scaleY: (Number(target.scaleY) || 1) * factor });
  target.setCoords();
  let correctedAnchor = stabilizeOppositeTransformAnchor(target, contact, "scale");
  const refined = refineAnchoredScaleSideToAxisLine(target, contact, best.line);
  correctedAnchor = stabilizeOppositeTransformAnchor(target, contact, "scale") || correctedAnchor;
  const correctedContact = refined?.contact || refreshedGuideContact(target, contact);
  return {
    line: best.line,
    projection: intersection,
    from: active.point,
    contact: correctedContact,
    anchorKind: correctedAnchor?.anchorKind || anchorResult.anchorKind,
    distance: Math.abs(refined?.residual ?? (scaleAxis === "x"
      ? correctedContact.point.x - best.line.value
      : correctedContact.point.y - best.line.value)),
    scaleAxis,
  };
}

function guideAngleForContact(line, target, contact = null) {
  let angle = normalizeDegrees(line.angle);
  if (contact?.kind === "left" || contact?.kind === "right") {
    angle = normalizeDegrees(angle - 90);
  }
  const current = normalizeDegrees(target?.angle || 0);
  const flipped = normalizeDegrees(angle + 180);
  const angleDistance = Math.abs(((angle - current + 540) % 360) - 180);
  const flippedDistance = Math.abs(((flipped - current + 540) % 360) - 180);
  return flippedDistance < angleDistance ? flipped : angle;
}

function snapOverlayStyle(extra = {}) {
  return {
    selectable: false,
    evented: false,
    excludeFromExport: true,
    strokeUniform: true,
    objectCaching: false,
    ...extra,
  };
}

function trackSnapOverlay(object) {
  object.kloudyGuide = true;
  object.kloudySnapOverlay = true;
  snapOverlayObjects.push(object);
  canvas.add(object);
  return object;
}

function clearSnapOverlay() {
  if (!canvas) {
    snapOverlayObjects = [];
    return;
  }
  const stale = new Set(snapOverlayObjects);
  canvas.getObjects().forEach((obj) => {
    if (obj.kloudySnapOverlay || stale.has(obj)) canvas.remove(obj);
  });
  snapOverlayObjects = [];
}

function renderSnapOverlayForTarget(target, contact = null, snapResult = null) {
  if (!canvas) return;
  clearSnapOverlay();
  if (!target || target.kloudyGuide || target.kloudyOverlay) {
    requestCanvasRender();
    return;
  }
  const coords = objectCornerCoords(target);
  const center = coords.center;
  const horizontal = [coords.left, coords.right];
  const vertical = [coords.top, coords.bottom];
  const activeContact = contact || guideContactForTarget(target, null);
  const quadrantMap = {
    "top-left": [coords.tl, coords.top, center, coords.left],
    "top-right": [coords.top, coords.tr, coords.right, center],
    "bottom-left": [coords.left, center, coords.bottom, coords.bl],
    "bottom-right": [center, coords.right, coords.br, coords.bottom],
  };
  const activePolygon = quadrantMap[activeContact?.quadrant || ""];
  if (activePolygon) {
    trackSnapOverlay(new fabric.Polygon(activePolygon, snapOverlayStyle({
      fill: "rgba(114, 164, 242, 0.10)",
      stroke: "rgba(114, 164, 242, 0.30)",
      strokeWidth: 1,
    })));
  }
  trackSnapOverlay(new fabric.Line([horizontal[0].x, horizontal[0].y, horizontal[1].x, horizontal[1].y], snapOverlayStyle({
    stroke: "rgba(114, 164, 242, 0.78)",
    strokeWidth: 1.5,
    strokeDashArray: [5, 5],
  })));
  trackSnapOverlay(new fabric.Line([vertical[0].x, vertical[0].y, vertical[1].x, vertical[1].y], snapOverlayStyle({
    stroke: "rgba(114, 164, 242, 0.78)",
    strokeWidth: 1.5,
    strokeDashArray: [5, 5],
  })));
  const segment = activeContact?.segment;
  if (segment) {
    trackSnapOverlay(new fabric.Line([segment[0].x, segment[0].y, segment[1].x, segment[1].y], snapOverlayStyle({
      stroke: "rgba(255, 211, 110, 0.98)",
      strokeWidth: 3,
    })));
  }
  if (activeContact?.point) {
    trackSnapOverlay(new fabric.Circle(snapOverlayStyle({
      left: activeContact.point.x,
      top: activeContact.point.y,
      radius: 5 / Math.max(canvas.getZoom() || 1, 0.001),
      originX: "center",
      originY: "center",
      fill: "rgba(255, 211, 110, 0.98)",
      stroke: "rgba(36, 24, 38, 0.72)",
      strokeWidth: 1,
    })));
  }
  if (snapResult?.projection && snapResult?.from) {
    trackSnapOverlay(new fabric.Line([snapResult.from.x, snapResult.from.y, snapResult.projection.x, snapResult.projection.y], snapOverlayStyle({
      stroke: "rgba(255, 88, 132, 0.92)",
      strokeWidth: 2,
      strokeDashArray: [3, 3],
    })));
    trackSnapOverlay(new fabric.Circle(snapOverlayStyle({
      left: snapResult.projection.x,
      top: snapResult.projection.y,
      radius: 4 / Math.max(canvas.getZoom() || 1, 0.001),
      originX: "center",
      originY: "center",
      fill: "rgba(255, 88, 132, 0.95)",
    })));
  }
  layerEditorHelpers();
  requestCanvasRender();
}

function signedAngleDistance(a, b) {
  return ((normalizeDegrees(a) - normalizeDegrees(b) + 540) % 360) - 180;
}

function nearestRotationNotch(angle, step = 45) {
  const normalized = normalizeDegrees(angle);
  return normalizeDegrees(Math.round(normalized / step) * step);
}

function rotationNotchMetrics(target) {
  if (!target || !canvas) return null;
  const coords = objectCornerCoords(target);
  const center = coords.center;
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const corners = [coords.tl, coords.tr, coords.bl, coords.br];
  const baseRadius = Math.max(...corners.map((point) => Math.hypot(point.x - center.x, point.y - center.y)));
  const zoomWeight = Math.max(0, Math.min(1, (zoom - 0.35) / 2.25));
  return {
    center,
    zoom,
    zoomWeight,
    radius: baseRadius + (24 + zoomWeight * 28) / zoom,
    tickMinor: (12 + zoomWeight * 9) / zoom,
    tickMajor: (18 + zoomWeight * 14) / zoom,
    pointerReach: (18 + zoomWeight * 12) / zoom,
    alpha: 0.42 + zoomWeight * 0.46,
  };
}

function pointerNearRotationNotchRing(target, event = null, metrics = null) {
  const pointer = canvasPointFromEvent(event);
  const ring = metrics || rotationNotchMetrics(target);
  if (!pointer || !ring) return false;
  const distance = Math.hypot(pointer.x - ring.center.x, pointer.y - ring.center.y);
  return Math.abs(distance - ring.radius) <= ring.pointerReach;
}

function snapRotationToNotches(target, event = null) {
  if (!target || target.kloudyGuide || target.kloudyOverlay || target.kloudy?.locked) return null;
  const metrics = rotationNotchMetrics(target);
  if (!pointerNearRotationNotchRing(target, event, metrics)) return null;
  const zoom = Math.max(canvas?.getZoom() || 1, 0.001);
  const threshold = Math.max(1.5, 4 / Math.sqrt(zoom));
  const angle = normalizeDegrees(target.angle || 0);
  const notch = nearestRotationNotch(angle);
  const delta = signedAngleDistance(angle, notch);
  if (Math.abs(delta) <= threshold) {
    target.set({ angle: notch });
    target.setCoords();
    setText("guideStatus", `Rotation notch: ${round(notch)} deg.`);
    return { snapped: true, notch, delta };
  }
  return { snapped: false, notch, delta };
}

function renderRotationNotchOverlay(target, event = null) {
  if (!canvas) return;
  clearSnapOverlay();
  if (!target || target.kloudyGuide || target.kloudyOverlay) return;
  const ring = rotationNotchMetrics(target);
  if (!ring) return;
  const { center, zoom, radius } = ring;
  const nearRing = pointerNearRotationNotchRing(target, event, ring);
  const notchLine = cssColorVar("--editor-notch-line", "rgba(18, 16, 18, 0.92)");
  const notchMuted = cssColorVar("--editor-notch-muted", "rgba(18, 16, 18, 0.48)");
  const notchActive = cssColorVar("--editor-notch-active", "rgba(236, 111, 164, 0.98)");
  const ringAlpha = nearRing ? ring.alpha : Math.max(0.22, ring.alpha * 0.62);
  const tickAlpha = nearRing ? ring.alpha : Math.max(0.28, ring.alpha * 0.66);
  trackSnapOverlay(new fabric.Circle(snapOverlayStyle({
    left: center.x,
    top: center.y,
    radius,
    originX: "center",
    originY: "center",
    fill: "rgba(0,0,0,0)",
    stroke: colorWithAlpha(nearRing ? notchLine : notchMuted, ringAlpha),
    strokeWidth: nearRing ? 2.4 : 1.6,
    strokeDashArray: [4, 5],
  })));
  const activeAngle = normalizeDegrees(target.angle || 0);
  for (let angle = 0; angle < 360; angle += 45) {
    const radians = angle * Math.PI / 180;
    const major = angle % 90 === 0;
    const length = major ? ring.tickMajor : ring.tickMinor;
    const outer = {
      x: center.x + Math.cos(radians) * radius,
      y: center.y + Math.sin(radians) * radius,
    };
    const inner = {
      x: center.x + Math.cos(radians) * (radius - length),
      y: center.y + Math.sin(radians) * (radius - length),
    };
    const active = Math.abs(signedAngleDistance(activeAngle, angle)) < 0.75;
    trackSnapOverlay(new fabric.Line([inner.x, inner.y, outer.x, outer.y], snapOverlayStyle({
      stroke: active ? colorWithAlpha(notchActive, nearRing ? 0.98 : 0.62) : colorWithAlpha(nearRing ? notchLine : notchMuted, tickAlpha),
      strokeWidth: active ? (nearRing ? 4.4 : 3.2) : (major ? 2.8 : 2.1),
    })));
  }
  const pointerRadians = activeAngle * Math.PI / 180;
  trackSnapOverlay(new fabric.Line([
    center.x,
    center.y,
    center.x + Math.cos(pointerRadians) * (radius + 8 / zoom),
    center.y + Math.sin(pointerRadians) * (radius + 8 / zoom),
  ], snapOverlayStyle({
    stroke: colorWithAlpha(nearRing ? notchActive : notchMuted, nearRing ? 0.96 : 0.56),
    strokeWidth: nearRing ? 2.8 : 1.8,
  })));
  layerEditorHelpers();
  requestCanvasRender();
}

function axisSnapPoints(rect, contact = null) {
  const allX = [
    { kind: "left", value: rect.left },
    { kind: "center", value: rect.left + rect.width / 2 },
    { kind: "right", value: rect.left + rect.width },
  ];
  const allY = [
    { kind: "top", value: rect.top },
    { kind: "middle", value: rect.top + rect.height / 2 },
    { kind: "bottom", value: rect.top + rect.height },
  ];
  if (contact?.source !== "control" && contact?.source !== "preserved") {
    return { xPoints: allX, yPoints: allY };
  }
  const kind = contact.kind || "";
  const xPoints = kind.includes("l") || kind === "left"
    ? [allX[0]]
    : (kind.includes("r") || kind === "right" ? [allX[2]] : [allX[1]]);
  const yPoints = kind.includes("t") || kind === "top"
    ? [allY[0]]
    : (kind.includes("b") || kind === "bottom" ? [allY[2]] : [allY[1]]);
  return { xPoints, yPoints };
}

function axisSnapPointsForLine(rect, contact, line) {
  if (line?.source === "grid") {
    return {
      xPoints: [
        { kind: "left", value: rect.left },
        { kind: "right", value: rect.left + rect.width },
      ],
      yPoints: [
        { kind: "top", value: rect.top },
        { kind: "bottom", value: rect.top + rect.height },
      ],
    };
  }
  return axisSnapPoints(rect, contact);
}

function applyAngledGuideSnap(target, contact, line, options = {}) {
  const allowRotation = options.allowRotation !== false;
  const isSingleVinylShape = Boolean(target.kloudy) && target.type !== "activeSelection" && target.type !== "activeselection";
  let activeContact = refreshedGuideContact(target, contact);
  if (allowRotation && isSingleVinylShape && Number.isFinite(line.angle)) {
    target.set({ angle: guideAngleForContact(line, target, contact) });
    target.setCoords();
    activeContact = refreshedGuideContact(target, contact);
  }
  const projection = projectPointToSegment(activeContact.point, line);
  if (!projection) return null;
  const deltaX = projection.x - activeContact.point.x;
  const deltaY = projection.y - activeContact.point.y;
  target.set({
    left: (target.left || 0) + deltaX,
    top: (target.top || 0) + deltaY,
  });
  target.setCoords();
  return {
    projection,
    from: activeContact.point,
    contact: refreshedGuideContact(target, contact),
    angle: isSingleVinylShape ? target.angle : null,
  };
}

function snapTargetToGuides(target, event = null) {
  if (!target || target.kloudyGuide || target.kloudyOverlay) return false;
  if (isActiveSelectionObject(target)) {
    clearSnapOverlay();
    return false;
  }
  const selected = selectedVinylObjects();
  if (selected.length && unlockedObjects(selected).length !== selected.length) return false;
  if (target.kloudy?.locked) return false;
  const transformAction = transformActionFromEvent(event);
  const frozenContactKind = transformAction === "move" && transformAnchorSnapshot?.target === target
    ? transformAnchorSnapshot.contactKind
    : null;
  const allowAngledRotation = transformAction === "move";
  const snapAllowed = !guideState.snapCtrlOnly || eventHasSnapModifier(event);
  const anchoredResize = transformAction === "scale" || transformAction === "skew";
  const snappingEnabled = guideState.snapGuides || (guideState.gridEnabled && guideState.snapGrid);
  if (!anchoredResize && (!snappingEnabled || !snapAllowed)) {
    clearSnapOverlay();
    return false;
  }
  const contact = guideContactForTarget(target, event, frozenContactKind);
  const pointer = canvasPointFromEvent(event);
  target.setCoords();
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const threshold = guideState.snapThreshold / zoom;
  const cursorThreshold = (guideState.snapThreshold * 1.45) / zoom;
  if (anchoredResize) {
    if (!snappingEnabled || !snapAllowed) {
      clearSnapOverlay();
      return false;
    }
    const anchorResult = stabilizeOppositeTransformAnchor(target, contact, transformAction);
    const sideSnap = transformAction === "scale" && snapAllowed
      ? snapAnchoredScaleSideToAxisLine(target, contact, anchorResult, threshold)
      : null;
    const overlayContact = sideSnap?.contact || refreshedGuideContact(target, contact);
    renderSnapOverlayForTarget(target, overlayContact, sideSnap || (anchorResult ? {
      from: anchorResult.currentAnchor,
      projection: anchorResult.originalAnchor,
    } : null));
    const now = Date.now();
    if (now - lastSnapMessageAt > 350) {
      lastSnapMessageAt = now;
      setText("guideStatus", sideSnap
        ? `Resize anchored: ${sideSnap.anchorKind || "opposite"} side stays fixed; pulled ${contact.kind} side snapped to ${sideSnap.line.source || "guide"}.`
        : `${transformAction === "skew" ? "Skew" : "Resize"} anchored: ${anchorResult?.anchorKind || "opposite"} side stays fixed while the pulled ${contact.kind} side changes.`);
    }
    return false;
  }
  if (!snappingEnabled) {
    clearSnapOverlay();
    return false;
  }
  if (!snapAllowed) {
    clearSnapOverlay();
    return false;
  }
  const rect = target.getBoundingRect(true, true);
  let bestX = null;
  let bestY = null;
  let bestLine = null;
  guideSnapLines().forEach((line) => {
    if (line.axis === "line") {
      if (pointer && distancePointToSnapLine(pointer, line) > cursorThreshold) return;
      const projected = projectPointToSegment(contact.point, line);
      if (!projected) return;
      const dx = projected.x - contact.point.x;
      const dy = projected.y - contact.point.y;
      const distance = Math.hypot(dx, dy);
      if (distance > threshold) return;
      if (!bestLine || distance < bestLine.abs) {
        bestLine = { line, deltaX: dx, deltaY: dy, abs: distance, source: line.source, point: contact.kind, angle: line.angle, projection: projected };
      }
      return;
    }
    const { xPoints, yPoints } = axisSnapPointsForLine(rect, contact, line);
    const points = line.axis === "x" ? xPoints : yPoints;
    points.forEach((point) => {
      const delta = line.value - point.value;
      const abs = Math.abs(delta);
      if (abs > threshold) return;
      const current = line.axis === "x" ? bestX : bestY;
      if (!current || abs < current.abs) {
        const hit = { delta, abs, source: line.source, point: point.kind, line };
        if (line.axis === "x") bestX = hit;
        else bestY = hit;
      }
    });
  });
  if (!bestX && !bestY && !bestLine) {
    renderSnapOverlayForTarget(target, contact, null);
    return false;
  }
  const activeEdgeSnap = contact?.kind && contact.kind !== "center";
  const shouldUseLine = Boolean(bestLine) && (
    activeEdgeSnap ||
    ((!bestX || bestLine.abs <= bestX.abs) && (!bestY || bestLine.abs <= bestY.abs))
  );
  const isSingleVinylShape = Boolean(target.kloudy) && target.type !== "activeSelection" && target.type !== "activeselection";
  let overlayResult = null;
  let overlayContact = contact;
  if (shouldUseLine) {
    overlayResult = applyAngledGuideSnap(target, contact, bestLine.line, { allowRotation: allowAngledRotation });
    overlayContact = overlayResult?.contact || refreshedGuideContact(target, contact);
  } else {
    let axisRotated = false;
    if (transformAction === "move" && activeEdgeSnap && isSingleVinylShape) {
      const rotationLine = bestX && (!bestY || bestX.abs <= bestY.abs) ? bestX.line : bestY?.line;
      const cursorNearAxisGuide = pointer && rotationLine?.source === "guide"
        ? distancePointToSnapLine(pointer, rotationLine) <= cursorThreshold
        : false;
      if (rotationLine && rotationLine.source === "guide" && cursorNearAxisGuide && Number.isFinite(rotationLine.angle)) {
        target.set({ angle: guideAngleForContact(rotationLine, target, contact) });
        target.setCoords();
        const rotatedContact = refreshedGuideContact(target, contact);
        target.set({
          left: (target.left || 0) + (bestX ? bestX.line.value - rotatedContact.point.x : 0),
          top: (target.top || 0) + (bestY ? bestY.line.value - rotatedContact.point.y : 0),
        });
        axisRotated = true;
      }
    }
    if (!axisRotated) {
      target.set({
        left: (target.left || 0) + (bestX?.delta || 0),
        top: (target.top || 0) + (bestY?.delta || 0),
      });
    }
    target.setCoords();
    finalizeAxisMoveSnap(target, bestX, bestY);
    overlayContact = refreshedGuideContact(target, { kind: axisSnapContactKind(bestX, bestY) });
  }
  renderSnapOverlayForTarget(target, overlayContact, overlayResult);
  const now = Date.now();
  if (now - lastSnapMessageAt > 350) {
    lastSnapMessageAt = now;
    if (shouldUseLine) {
      setText("guideStatus", `Snapped ${contact.kind} edge to angled guide${allowAngledRotation && isSingleVinylShape ? ` and rotated to ${round(target.angle || 0)} deg` : " without rotating during resize/skew"}.`);
    } else {
      setText("guideStatus", `Snapped ${bestX ? bestX.point : ""}${bestX && bestY ? " + " : ""}${bestY ? bestY.point : ""} to ${bestX?.source || bestY?.source}.`);
    }
  }
  return true;
}

function resetView() {
  const zoom = Math.min(canvas.width / 2400, canvas.height / 2400);
  canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
  styleAllTransformControls();
  syncCanvasObjectCoords();
  syncSelectedShapeOutlines();
  updateVisualGridLayer();
  canvas.requestRenderAll();
  updateHud();
}

function fitDesignView() {
  const objects = vinylObjects();
  if (!objects.length) {
    resetView();
    return;
  }
  let bounds = null;
  objects.forEach((obj) => {
    obj.setCoords();
    const rect = obj.getBoundingRect(true, true);
    bounds = bounds ? {
      left: Math.min(bounds.left, rect.left),
      top: Math.min(bounds.top, rect.top),
      right: Math.max(bounds.right, rect.left + rect.width),
      bottom: Math.max(bounds.bottom, rect.top + rect.height),
    } : {
      left: rect.left,
      top: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
    };
  });
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const centerX = bounds.left + width / 2;
  const centerY = bounds.top + height / 2;
  const zoom = Math.min(canvas.width / (width * 1.18), canvas.height / (height * 1.18), 2.5);
  canvas.setViewportTransform([
    zoom, 0, 0, zoom,
    canvas.width / 2 - centerX * zoom,
    canvas.height / 2 - centerY * zoom,
  ]);
  styleAllTransformControls();
  syncCanvasObjectCoords();
  syncSelectedShapeOutlines();
  updateVisualGridLayer();
  canvas.requestRenderAll();
  updateHud();
}

function fitObjectsView(objects) {
  if (!objects.length) {
    fitDesignView();
    return;
  }
  let bounds = null;
  objects.forEach((obj) => {
    obj.setCoords();
    const rect = obj.getBoundingRect(true, true);
    bounds = bounds ? {
      left: Math.min(bounds.left, rect.left),
      top: Math.min(bounds.top, rect.top),
      right: Math.max(bounds.right, rect.left + rect.width),
      bottom: Math.max(bounds.bottom, rect.top + rect.height),
    } : {
      left: rect.left,
      top: rect.top,
      right: rect.left + rect.width,
      bottom: rect.top + rect.height,
    };
  });
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const centerX = bounds.left + width / 2;
  const centerY = bounds.top + height / 2;
  const zoom = Math.min(canvas.width / (width * 2.2), canvas.height / (height * 2.2), 6);
  canvas.setViewportTransform([
    zoom, 0, 0, zoom,
    canvas.width / 2 - centerX * zoom,
    canvas.height / 2 - centerY * zoom,
  ]);
  styleAllTransformControls();
  syncCanvasObjectCoords();
  syncSelectedShapeOutlines();
  updateVisualGridLayer();
  canvas.requestRenderAll();
  updateHud();
}

function fitSelectedView() {
  const objects = selectedVinylObjects();
  if (!objects.length) {
    setStatus("Select a layer before using Fit Selected.");
    return;
  }
  fitObjectsView(objects);
  setStatus(`Fit view to ${objects.length} selected layer(s).`);
}

async function loadJsonFile(file) {
  setBusy(`Loading JSON: ${file.name}`);
  await nextFrame();
  const text = await file.text();
  const payload = JSON.parse(text);
  const previousName = loadedName;
  const previousProjectName = currentProjectName;
  loadedName = cleanProjectBaseName(file.name, "vinyl");
  currentProjectName = null;
  try {
    await loadPayload(payload);
  } catch (err) {
    loadedName = previousName;
    currentProjectName = previousProjectName;
    throw err;
  }
}

function formatBrowserDate(mtime) {
  const numeric = Number(mtime);
  if (!Number.isFinite(numeric) || numeric <= 0) return "unknown date";
  return new Date(numeric * 1000).toLocaleString();
}

function layerLabel(count) {
  const numeric = Number(count) || 0;
  return `${numeric.toLocaleString()} layer${numeric === 1 ? "" : "s"}`;
}

function selectedJsonBrowserGroup() {
  return jsonBrowserState.groups[jsonBrowserState.selectedGroupIndex] || null;
}

function selectedJsonBrowserEntry() {
  const group = selectedJsonBrowserGroup();
  return group?.entries?.[jsonBrowserState.selectedEntryIndex] || null;
}

function setJsonBrowserStatus(message) {
  setText("jsonBrowserStatus", message);
}

function jsonBrowserSourceLabel(source = jsonBrowserState.source) {
  if (source === "editor") return "Editor export";
  if (source === "exported") return "Exported JSON";
  return "Generated final run";
}

function jsonBrowserSourceFolder(source = jsonBrowserState.source) {
  if (source === "editor") return "imgs/editor";
  if (source === "exported") return "imgs/exported";
  return "imgs/generated";
}

function setJsonBrowserPreview(entry = null) {
  const image = $("jsonBrowserPreviewImage");
  const empty = $("jsonBrowserPreviewEmpty");
  if (!image || !empty) return;
  image.onerror = () => {
    image.hidden = true;
    empty.hidden = false;
    empty.textContent = "Preview unavailable";
  };
  if (!entry?.preview_url) {
    image.hidden = true;
    empty.hidden = false;
    empty.textContent = "No preview selected";
    image.removeAttribute("src");
    return;
  }
  empty.hidden = true;
  image.hidden = false;
  image.src = `${entry.preview_url}${entry.preview_url.includes("?") ? "&" : "?"}t=${encodeURIComponent(String(entry.mtime || Date.now()))}`;
}

function renderJsonBrowserGroups() {
  const container = $("jsonBrowserGroups");
  if (!container) return;
  container.innerHTML = "";
  if (!jsonBrowserState.groups.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    if (jsonBrowserState.source === "editor") {
      empty.textContent = "No editor exports found. Export from the editor into imgs/editor, then click Refresh.";
    } else if (jsonBrowserState.source === "exported") {
      empty.textContent = "No exported JSONs found. Drop downloaded, shared, or game-exported JSONs into imgs/exported, then click Refresh.";
    } else {
      empty.textContent = "No generated final JSONs found yet. Generate a vinyl first, then click Refresh.";
    }
    container.appendChild(empty);
    return;
  }
  jsonBrowserState.groups.forEach((group, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `jsonBrowserCard${index === jsonBrowserState.selectedGroupIndex ? " active" : ""}`;
    const previewEntry = group.entries?.[0] || null;
    const thumb = document.createElement("img");
    thumb.className = "jsonBrowserThumb";
    thumb.loading = "lazy";
    thumb.alt = `${group.title || group.key || "JSON"} preview`;
    if (previewEntry?.preview_url) {
      thumb.src = previewEntry.preview_url;
    } else {
      thumb.hidden = true;
    }
    thumb.onerror = () => {
      thumb.style.display = "none";
    };
    const title = document.createElement("b");
    title.title = group.title || group.key || "";
    title.textContent = group.title || group.key || "Untitled JSON";
    const kind = document.createElement("span");
    kind.textContent = group.source === "generated"
      ? `${group.count || 0} finalized JSON${group.count === 1 ? "" : "s"}`
      : jsonBrowserSourceLabel(group.source);
    const layers = document.createElement("span");
    layers.textContent = `${layerLabel(group.max_layers || 0)} max`;
    const modified = document.createElement("span");
    modified.textContent = formatBrowserDate(group.mtime);
    button.append(thumb, title, kind, layers, modified);
    button.addEventListener("click", () => {
      jsonBrowserState.selectedGroupIndex = index;
      jsonBrowserState.selectedEntryIndex = group.entries?.length ? 0 : -1;
      renderJsonBrowserGroups();
      renderJsonBrowserEntries();
    });
    container.appendChild(button);
  });
}

function renderJsonBrowserEntries() {
  const group = selectedJsonBrowserGroup();
  const container = $("jsonBrowserEntries");
  if (!container) return;
  container.innerHTML = "";
  $("selectJsonBrowserEntry").disabled = !selectedJsonBrowserEntry();
  if (!group) {
    setText("jsonBrowserTitle", "Select a source");
    setText("jsonBrowserMeta", "JSON folders are sorted newest first. Files are sorted high layer count to low.");
    setJsonBrowserPreview(null);
    setJsonBrowserStatus("Choose a source on the left.");
    return;
  }
  setText("jsonBrowserTitle", group.title || group.key);
  setText("jsonBrowserMeta", `${jsonBrowserSourceLabel(group.source)} - ${formatBrowserDate(group.mtime)} - select any JSON below to preview and import it.`);
  setJsonBrowserPreview(selectedJsonBrowserEntry());
  (group.entries || []).forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `jsonBrowserEntry${index === jsonBrowserState.selectedEntryIndex ? " active" : ""}`;
    const textWrap = document.createElement("span");
    const name = document.createElement("b");
    name.title = entry.name || "";
    name.textContent = entry.name || "Untitled JSON";
    const path = document.createElement("span");
    path.textContent = entry.id || "";
    textWrap.append(name, path);
    const layers = document.createElement("span");
    layers.className = "jsonBrowserLayerPill";
    layers.textContent = layerLabel(entry.layers);
    button.append(textWrap, layers);
    button.addEventListener("click", () => {
      jsonBrowserState.selectedEntryIndex = index;
      renderJsonBrowserEntries();
    });
    button.addEventListener("dblclick", () => importSelectedBrowserJson());
    container.appendChild(button);
  });
  $("selectJsonBrowserEntry").disabled = !selectedJsonBrowserEntry();
  setJsonBrowserStatus(selectedJsonBrowserEntry() ? "Choose Select JSON or double-click a row." : "This source has no JSON entries.");
}

async function refreshJsonBrowser() {
  if (jsonBrowserState.loading) return;
  jsonBrowserState.loading = true;
  setText("jsonBrowserSummary", "Loading JSON browser...");
  setJsonBrowserStatus("Scanning app folders...");
  try {
    const source = $("jsonBrowserSource")?.value || "generated";
    jsonBrowserState.source = source;
    const response = await fetch(`${JSON_BROWSER_API}?source=${encodeURIComponent(source)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    jsonBrowserState.groups = Array.isArray(data.groups) ? data.groups : [];
    jsonBrowserState.selectedGroupIndex = jsonBrowserState.groups.length ? 0 : -1;
    jsonBrowserState.selectedEntryIndex = jsonBrowserState.groups[0]?.entries?.length ? 0 : -1;
    setText("jsonBrowserSummary", `${data.total_entries || 0} JSON${data.total_entries === 1 ? "" : "s"} found in ${jsonBrowserSourceFolder(source)}.`);
    renderJsonBrowserGroups();
    renderJsonBrowserEntries();
  } catch (err) {
    console.error(err);
    jsonBrowserState.groups = [];
    jsonBrowserState.selectedGroupIndex = -1;
    jsonBrowserState.selectedEntryIndex = -1;
    renderJsonBrowserGroups();
    renderJsonBrowserEntries();
    setText("jsonBrowserSummary", "JSON browser failed to load.");
    setJsonBrowserStatus(err.message || String(err));
  } finally {
    jsonBrowserState.loading = false;
  }
}

function setJsonBrowserSource(source) {
  const select = $("jsonBrowserSource");
  if (select) select.value = source;
  jsonBrowserState.source = source;
}

function selectJsonBrowserEntryById(entryId) {
  if (!entryId) return false;
  for (let groupIndex = 0; groupIndex < jsonBrowserState.groups.length; groupIndex += 1) {
    const entries = jsonBrowserState.groups[groupIndex]?.entries || [];
    const entryIndex = entries.findIndex((entry) => entry.id === entryId);
    if (entryIndex >= 0) {
      jsonBrowserState.selectedGroupIndex = groupIndex;
      jsonBrowserState.selectedEntryIndex = entryIndex;
      renderJsonBrowserGroups();
      renderJsonBrowserEntries();
      return true;
    }
  }
  return false;
}

async function openJsonBrowser() {
  const dialog = $("jsonBrowserDialog");
  if (!dialog) return;
  try {
    if (!dialog.open) dialog.showModal();
  } catch (_err) {
    dialog.setAttribute("open", "");
  }
  await refreshJsonBrowser();
}

async function importSelectedBrowserJson() {
  const entry = selectedJsonBrowserEntry();
  if (!entry) {
    setJsonBrowserStatus("Select a JSON first.");
    return;
  }
  setJsonBrowserStatus(`Loading ${entry.name}...`);
  setBusy(`Loading JSON: ${entry.name}`);
  await nextFrame();
  const previousName = loadedName;
  const previousProjectName = currentProjectName;
  loadedName = cleanProjectBaseName(entry.name, "vinyl");
  currentProjectName = null;
  try {
    const response = await fetch(`${JSON_FILE_API}?id=${encodeURIComponent(entry.id)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    await loadPayload(data.payload);
    $("jsonBrowserDialog")?.close();
    setStatus(`Imported ${entry.name} from ${jsonBrowserSourceFolder()}.`);
  } catch (err) {
    loadedName = previousName;
    currentProjectName = previousProjectName;
    showError("JSON browser import failed", err);
    setJsonBrowserStatus(err.message || String(err));
  }
}

function selectedProjectEntry() {
  return projectBrowserState.entries[projectBrowserState.selectedIndex] || null;
}

function setProjectBrowserStatus(message) {
  setText("projectBrowserStatus", message);
}

function renderProjectBrowser() {
  const container = $("projectBrowserEntries");
  if (!container) return;
  container.innerHTML = "";
  const selected = selectedProjectEntry();
  $("selectProjectEntry").disabled = !selected;
  if (!projectBrowserState.entries.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No saved projects found yet. Use Save Project to create an internal project file.";
    container.appendChild(empty);
    setProjectBrowserStatus("No internal project saves found.");
    return;
  }
  projectBrowserState.entries.forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `projectBrowserEntry${index === projectBrowserState.selectedIndex ? " active" : ""}`;
    const textWrap = document.createElement("span");
    const title = document.createElement("b");
    title.textContent = entry.title || entry.name || "Untitled project";
    const meta = document.createElement("span");
    meta.textContent = `${layerLabel(entry.layers)} - ${formatBrowserDate(entry.mtime)}`;
    textWrap.append(title, meta);
    const file = document.createElement("span");
    file.textContent = entry.name || "";
    button.append(textWrap, file);
    button.addEventListener("click", () => {
      projectBrowserState.selectedIndex = index;
      renderProjectBrowser();
    });
    button.addEventListener("dblclick", () => loadSelectedProject());
    container.appendChild(button);
  });
  setProjectBrowserStatus(selected ? "Choose Load Project or double-click a project." : "Select a project.");
}

async function refreshProjectBrowser() {
  if (projectBrowserState.loading) return;
  projectBrowserState.loading = true;
  setText("projectBrowserSummary", "Loading internal projects...");
  setProjectBrowserStatus("Scanning runtime/fabric-editor/projects...");
  try {
    const response = await fetch(PROJECT_BROWSER_API, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    projectBrowserState.entries = Array.isArray(data.entries) ? data.entries : [];
    projectBrowserState.selectedIndex = projectBrowserState.entries.length ? 0 : -1;
    setText("projectBrowserSummary", `${data.total_entries || 0} project${data.total_entries === 1 ? "" : "s"} saved inside KFPS.`);
    renderProjectBrowser();
  } catch (err) {
    console.error(err);
    projectBrowserState.entries = [];
    projectBrowserState.selectedIndex = -1;
    renderProjectBrowser();
    setText("projectBrowserSummary", "Project browser failed to load.");
    setProjectBrowserStatus(err.message || String(err));
  } finally {
    projectBrowserState.loading = false;
  }
}

async function openProjectFolder() {
  const button = $("openProjectFolder");
  if (button) button.disabled = true;
  setProjectBrowserStatus("Opening internal project folder...");
  try {
    const response = await fetch(PROJECT_OPEN_FOLDER_API, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    setProjectBrowserStatus("Project folder opened. Drop .fabric-project.json files there, then click Refresh.");
  } catch (err) {
    showError("Open project folder failed", err);
    setProjectBrowserStatus(err.message || String(err));
  } finally {
    if (button) button.disabled = false;
  }
}

async function openProjectBrowser() {
  const dialog = $("projectBrowserDialog");
  if (!dialog) return;
  try {
    if (!dialog.open) dialog.showModal();
  } catch (_err) {
    dialog.setAttribute("open", "");
  }
  await refreshProjectBrowser();
}

async function loadSelectedProject() {
  const entry = selectedProjectEntry();
  if (!entry) {
    setProjectBrowserStatus("Select a project first.");
    return;
  }
  setProjectBrowserStatus(`Loading ${entry.title || entry.name}...`);
  try {
    const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    await loadProjectPayload(data.payload, entry.title || entry.name);
    $("projectBrowserDialog")?.close();
    clearBusy(`Loaded project: ${entry.title || entry.name}`);
  } catch (err) {
    showError("Project load failed", err);
    setProjectBrowserStatus(err.message || String(err));
  }
}

async function loadStartupProjectFromQuery() {
  const projectId = startupProjectId();
  if (!projectId) return false;
  setBusy("Loading selected project...");
  try {
    const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(projectId)}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    await loadProjectPayload(data.payload, data.name || "project");
    clearBusy(`Loaded project: ${data.name || projectId}`);
    return true;
  } catch (err) {
    clearBusy("Project load failed.");
    showError("Project load failed", err);
    return false;
  }
}

async function loadPayload(payload) {
  const shapes = Array.isArray(payload.shapes) ? payload.shapes : null;
  if (!shapes) throw new Error("JSON must contain a shapes list.");
  if (!shapes.length) throw new Error("JSON shapes list is empty.");
  const hasLegacyGeometry = shapes.some((shape) => LEGACY_RECTANGLE_TYPES.has(Number(shape.type)) || LEGACY_ELLIPSE_TYPES.has(Number(shape.type)));
  const legacyOffset = hasLegacyGeometry ? computeLegacyOffset(shapes) : { x: 0, y: 0 };
  const normalized = shapes.map((shape, index) => normalizeInputShape(shape, index, legacyOffset)).filter(Boolean);
  if (!normalized.length) throw new Error("JSON did not contain any usable FH6 vinyl layers.");
  setBusy(`Building ${normalized.length} editable layer(s)...`);
  await nextFrame();
  const builtObjects = [];
  let failed = 0;
  for (const shape of normalized) {
    try {
      const object = await makeFabricObject(shape);
      builtObjects.push(object);
    } catch (err) {
      failed++;
      console.warn(err);
    }
    if ((builtObjects.length + failed) % 100 === 0) {
      setBusy(`Building layers: ${builtObjects.length}/${normalized.length}`);
      await nextFrame();
    }
  }
  if (!builtObjects.length) {
    throw new Error(`JSON did not contain any loadable FH6 vinyl layers. Failed to build ${failed}/${normalized.length}. Current canvas was left unchanged.`);
  }
  clearVinylObjects();
  resetHistory();
  builtObjects.forEach((object) => canvas.add(object));
  if (Array.isArray(payload.editor_collapsed_groups)) applyCollapsedLayerGroups(payload.editor_collapsed_groups);
  else collapsedLayerGroups.clear();
  bringGuidesToBack();
  syncCanvasObjectCoords();
  refreshLayers();
  fitDesignView();
  pushHistory("import");
  protectedHistoryIndex = historyIndex;
  clearBusy(`Loaded ${builtObjects.length}/${normalized.length} editable FH6 layer(s).${failed ? ` Failed: ${failed}.` : ""}`);
}

function clearVinylObjects(options = {}) {
  selectedShapeOutlineObjects.forEach(restoreSelectionOutline);
  selectedShapeOutlineObjects.clear();
  selectedShapeOutlineHelpers.forEach((helper) => canvas.remove(helper));
  selectedShapeOutlineHelpers.clear();
  maskPreviewOutlines.forEach((outline) => canvas.remove(outline));
  maskPreviewOutlines.clear();
  maskPreviewCutouts.forEach((cutout) => canvas.remove(cutout));
  maskPreviewCutouts.clear();
  vinylObjects().forEach((obj) => canvas.remove(obj));
  invalidateLayerStats();
  if (!options.preserveCollapsed) collapsedLayerGroups.clear();
  lastLayerListKey = null;
  dropperPreservedActiveObject = null;
}

function vinylObjects() {
  return canvas.getObjects().filter((obj) => obj.kloudy && !obj.kloudyGuide && !obj.kloudyMaskOutline && !obj.kloudyMaskCutout);
}

function interactiveVinylTarget(target) {
  return target?.kloudyMaskOwner || target;
}

function copyTransform(source, target) {
  if (!source || !target) return;
  target.set({
    left: source.left,
    top: source.top,
    scaleX: source.scaleX,
    scaleY: source.scaleY,
    angle: source.angle,
    skewX: source.skewX,
    skewY: source.skewY,
    flipX: source.flipX,
    flipY: source.flipY,
  });
  target.setCoords();
}

function mirrorMaskProxyToOwner(proxy) {
  const owner = proxy?.kloudyMaskOwner;
  if (!owner) return null;
  copyTransform(proxy, owner);
  return owner;
}

function mirrorActiveMaskProxyToOwner() {
  return mirrorMaskProxyToOwner(canvas?.getActiveObject?.());
}

function selectedVinylObjects() {
  const active = canvas.getActiveObject();
  if (!active) return [];
  if (active.kloudyMaskOwner) return [active.kloudyMaskOwner];
  if ((active.type === "activeSelection" || active.type === "activeselection") && Array.isArray(active._objects)) {
    return [...new Set(active._objects.map(interactiveVinylTarget).filter((obj) => obj.kloudy && !obj.kloudyGuide))];
  }
  return active.kloudy && !active.kloudyGuide ? [active] : [];
}

function isActiveSelectionObject(object) {
  return object && (object.type === "activeSelection" || object.type === "activeselection");
}

function selectionSetEquals(a, b) {
  if (a.length !== b.length) return false;
  const bSet = new Set(b);
  return a.every((item) => bSet.has(item));
}

function validSelectionLockObjects() {
  const current = new Set(vinylObjects());
  return selectionLockObjects.filter((obj) => current.has(obj));
}

function setActiveObjectsForSelectionLock(objects) {
  const normalized = [...new Set(objects.map(interactiveVinylTarget).filter((obj) => obj?.kloudy && !obj.kloudyGuide))];
  if (!normalized.length) return false;
  selectionLockRestoring = true;
  try {
    const active = canvas.getActiveObject();
    if (active && (isActiveSelectionObject(active) || !selectionSetEquals(selectedVinylObjects(), normalized))) {
      canvas.discardActiveObject();
    }
    normalized.forEach((obj) => obj.setCoords());
    if (normalized.length === 1) canvas.setActiveObject(normalized[0]);
    else canvas.setActiveObject(styledActiveSelection(normalized));
    canvas.requestRenderAll();
    updateSelectionPanel();
    updateLayerSelectionStyles();
  } finally {
    selectionLockRestoring = false;
  }
  return true;
}

function updateSelectionLockButton() {
  const button = $("selectionLockToggle");
  if (!button) return;
  button.classList.toggle("active", selectionLockActive);
  button.setAttribute("aria-pressed", selectionLockActive ? "true" : "false");
  button.textContent = selectionLockActive ? "Selection Locked" : "Lock Selection";
}

function releaseSelectionLock(message = "Selection lock released.") {
  const hadLock = selectionLockActive;
  selectionLockActive = false;
  selectionLockObjects = [];
  selectionLockRestoring = false;
  updateSelectionLockButton();
  if (hadLock && message) setStatus(message);
}

function restoreSelectionLock(reason = "misclick") {
  if (!selectionLockActive || selectionLockRestoring) return false;
  const objects = validSelectionLockObjects();
  if (!objects.length) {
    releaseSelectionLock("Selection lock released because the locked layer no longer exists.");
    return false;
  }
  const selected = selectedVinylObjects();
  if (selectionSetEquals(selected, objects)) return false;
  setActiveObjectsForSelectionLock(objects);
  setStatus(`Selection lock kept ${objects.length} layer(s) selected after ${reason}. Unlock to choose something else.`);
  return true;
}

function toggleSelectionLock() {
  if (selectionLockActive) {
    releaseSelectionLock();
    return;
  }
  const selected = selectedVinylObjects();
  if (!selected.length) {
    setStatus("Select one or more layers before locking the selection.");
    return;
  }
  selectionLockActive = true;
  selectionLockObjects = [...selected];
  updateSelectionLockButton();
  setStatus(`Selection locked to ${selected.length} layer(s). Misclicks will keep this selection.`);
}

function shouldInvertCurrentSelection(event = null) {
  if (!$("invertBoxSelect")?.checked || selectionInvertLocked) return false;
  const active = canvas?.getActiveObject();
  if (!isActiveSelectionObject(active)) return false;
  const selected = selectedVinylObjects();
  if (selected.length < 2) return false;
  if (event?.e?.shiftKey || event?.e?.ctrlKey || event?.e?.metaKey) return false;
  return true;
}

function invertCurrentSelection(event = null) {
  if (!shouldInvertCurrentSelection(event)) return false;
  const selectedSet = new Set(selectedVinylObjects());
  const inverted = vinylObjects().filter((obj) => obj.visible !== false && !selectedSet.has(obj));
  if (!inverted.length) {
    setStatus("Invert box select found no layers outside the box.");
    return false;
  }
  selectionInvertLocked = true;
  if (inverted.length === 1) canvas.setActiveObject(inverted[0]);
  else canvas.setActiveObject(styledActiveSelection(inverted));
  selectionInvertLocked = false;
  canvas.requestRenderAll();
  setStatus(`Invert box selected ${inverted.length} layer(s) outside the drag box.`);
  return true;
}

function handleSelectionChanged(event = null) {
  if (selectionLockActive && !selectionLockRestoring && restoreSelectionLock("a selection change")) {
    return;
  }
  if (invertCurrentSelection(event)) {
    updateSelectionPanel();
    updateLayerSelectionStyles();
    return;
  }
  const active = canvas?.getActiveObject();
  if (active) styleObjectTransformControls(active);
  updateSelectionPanel();
}

function unlockedObjects(objects) {
  return objects.filter((obj) => !obj.kloudy?.locked);
}

function setObjectLocked(object, locked) {
  if (!object?.kloudy) return;
  object.kloudy.locked = Boolean(locked);
  object.set({
    lockMovementX: Boolean(locked),
    lockMovementY: Boolean(locked),
    lockScalingX: Boolean(locked),
    lockScalingY: Boolean(locked),
    lockRotation: Boolean(locked),
    hasControls: !locked,
  });
}

function groupNameForObject(object) {
  return object?.kloudy?.group_name || "Layer Group";
}

function selectedGroupIds() {
  return [...new Set(selectedVinylObjects()
    .map((obj) => obj.kloudy?.group_id)
    .filter(Boolean))];
}

function membersForGroupIds(groupIds) {
  const ids = new Set(groupIds.filter(Boolean));
  if (!ids.size) return [];
  return vinylObjects().filter((obj) => ids.has(obj.kloudy?.group_id));
}

function selectedGroupMembers() {
  return membersForGroupIds(selectedGroupIds());
}

function selectGroupForObject(object) {
  const groupId = object?.kloudy?.group_id;
  if (!groupId) return false;
  selectObjects(membersForGroupIds([groupId]), groupNameForObject(object));
  return true;
}

function setCollapsedGroup(groupId, collapsed) {
  if (!groupId) return;
  if (collapsed) collapsedLayerGroups.add(String(groupId));
  else collapsedLayerGroups.delete(String(groupId));
  refreshLayers();
  persistCollapsedLayerState();
}

function layerListObjectKey(object) {
  if (!object) return "";
  if (!object.__kloudyLayerListId) {
    object.__kloudyLayerListId = `layer-${nextLayerListObjectId++}`;
  }
  return object.__kloudyLayerListId;
}

function registerLayerListRow(element, key, objects, displayIndex) {
  element.dataset.layerListKey = key;
  element.draggable = false;
  layerListRows.set(key, {
    key,
    objects: objects.filter(Boolean),
    displayIndex,
    element,
  });
  element.addEventListener("pointerdown", handleLayerPointerDown);
  element.addEventListener("pointermove", handleLayerPointerMove);
  element.addEventListener("pointerup", handleLayerPointerUp);
  element.addEventListener("pointercancel", cancelLayerDrag);
}

function layerRowFromEventTarget(target) {
  return target?.closest?.("[data-layer-list-key]") || null;
}

function isLayerControlTarget(target) {
  return Boolean(target?.closest?.("button, input, select, textarea, .layerGroupBadge"));
}

function layerDragLabel(objects = []) {
  if (objects.length > 1) {
    const groupName = objects[0]?.kloudy?.group_id && objects.every((obj) => obj.kloudy?.group_id === objects[0].kloudy.group_id)
      ? groupNameForObject(objects[0])
      : null;
    return groupName ? `${groupName} (${objects.length})` : `${objects.length} layers`;
  }
  return objects[0]?.kloudy?.name || "1 layer";
}

function layerDragModeLabel(mode) {
  return mode === "group" ? "Group layers" : "Move depth";
}

function ensureLayerDragGhost(state) {
  if (layerDragGhost) return layerDragGhost;
  layerDragGhost = document.createElement("div");
  layerDragGhost.className = "layerDragGhost";
  layerDragGhost.innerHTML = `
    <b>${escapeHtml(layerDragLabel(state.objects))}</b>
    <span>${escapeHtml(layerDragModeLabel(state.mode))}</span>
  `;
  document.body.appendChild(layerDragGhost);
  return layerDragGhost;
}

function updateLayerDragGhost(event) {
  if (!layerDragState) return;
  const ghost = ensureLayerDragGhost(layerDragState);
  ghost.style.left = `${event.clientX + 16}px`;
  ghost.style.top = `${event.clientY + 14}px`;
}

function clearLayerDropPreview() {
  document.querySelectorAll(".layerDropTarget, .layerDropBefore, .layerDropAfter").forEach((el) => {
    el.classList.remove("layerDropTarget", "layerDropBefore", "layerDropAfter");
  });
}

function layerScrollPane() {
  return $("layersPane");
}

function layerRowAtPoint(x, y) {
  const direct = layerRowFromEventTarget(document.elementFromPoint(x, y));
  if (direct) return direct;
  const pane = layerScrollPane();
  const paneRect = pane?.getBoundingClientRect();
  if (!paneRect || x < paneRect.left || x > paneRect.right || y < paneRect.top || y > paneRect.bottom) return null;
  let best = null;
  let bestDistance = Infinity;
  document.querySelectorAll("#layers [data-layer-list-key]").forEach((row) => {
    const rect = row.getBoundingClientRect();
    if (rect.bottom < paneRect.top || rect.top > paneRect.bottom) return;
    const centerY = rect.top + rect.height / 2;
    const distance = Math.abs(centerY - y);
    if (distance < bestDistance) {
      best = row;
      bestDistance = distance;
    }
  });
  return best;
}

function isGroupLayerKey(key) {
  return String(key || "").startsWith("group:");
}

function layerSearchActive() {
  return Boolean(($("layerSearch")?.value || "").trim());
}

function visibleLayerBlocks() {
  const displayObjects = displayObjectsFromCurrentStack();
  const displayIndex = new Map(displayObjects.map((obj, index) => [obj, index]));
  const seen = new Set();
  const blocks = [];
  document.querySelectorAll("#layers [data-layer-list-key]").forEach((row) => {
    const key = row.dataset.layerListKey;
    const entry = layerListRows.get(key);
    if (!entry?.objects?.length) return;
    if (isGroupLayerKey(key)) {
      const objects = entry.objects
        .filter((obj) => displayIndex.has(obj))
        .sort((a, b) => displayIndex.get(a) - displayIndex.get(b));
      if (!objects.length) return;
      objects.forEach((obj) => seen.add(obj));
      blocks.push({ key, objects, element: row });
      return;
    }
    const object = entry.objects[0];
    if (!object || seen.has(object)) return;
    seen.add(object);
    blocks.push({ key, objects: [object], element: row });
  });
  return blocks;
}

function layerBlockForKey(key, blocks = visibleLayerBlocks()) {
  const entry = layerListRows.get(key);
  if (!entry?.objects?.length) return null;
  if (isGroupLayerKey(key)) return blocks.find((block) => block.key === key) || null;
  const objectSet = new Set(entry.objects);
  return blocks.find((block) => block.objects.some((obj) => objectSet.has(obj))) || null;
}

function reorderCandidateBlocks(dragObjects = []) {
  const selectedSet = new Set(dragObjects);
  return visibleLayerBlocks()
    .map((block) => ({
      ...block,
      objects: block.objects.filter((obj) => !selectedSet.has(obj)),
    }))
    .filter((block) => block.objects.length && block.element?.isConnected);
}

function layerDropSlotAtPoint(event) {
  if (!layerDragState || layerDragState.mode !== "reorder") return null;
  if (layerSearchActive()) return null;
  const pane = layerScrollPane();
  const paneRect = pane?.getBoundingClientRect();
  if (!paneRect || event.clientX < paneRect.left || event.clientX > paneRect.right || event.clientY < paneRect.top || event.clientY > paneRect.bottom) return null;
  const blocks = reorderCandidateBlocks(layerDragState.objects);
  if (!blocks.length) return { index: 0, blocks };
  const rows = blocks.map((block) => ({ block, rect: block.element.getBoundingClientRect() }));
  const gaps = [{ index: 0, y: rows[0].rect.top, block: rows[0].block, side: "before" }];
  for (let index = 1; index < rows.length; index += 1) {
    gaps.push({
      index,
      y: (rows[index - 1].rect.bottom + rows[index].rect.top) / 2,
      block: rows[index].block,
      side: "before",
    });
  }
  gaps.push({
    index: rows.length,
    y: rows[rows.length - 1].rect.bottom,
    block: rows[rows.length - 1].block,
    side: "after",
  });
  let best = gaps[0];
  let bestDistance = Math.abs(event.clientY - best.y);
  gaps.slice(1).forEach((gap) => {
    const distance = Math.abs(event.clientY - gap.y);
    if (distance < bestDistance) {
      best = gap;
      bestDistance = distance;
    }
  });
  return { index: best.index, blocks, markerBlock: best.block, markerSide: best.side };
}

function updateLayerDropPreview(event) {
  if (!layerDragState) return null;
  clearLayerDropPreview();
  layerDragState.dropSlot = null;
  if (layerDragState.mode === "reorder") {
    if (layerSearchActive()) {
      setStatus("Clear the layer search before dragging layers; filtered rows cannot safely define canvas depth.");
      return null;
    }
    const slot = layerDropSlotAtPoint(event);
    if (!slot?.markerBlock?.element) return null;
    slot.markerBlock.element.classList.add(slot.markerSide === "after" ? "layerDropAfter" : "layerDropBefore");
    layerDragState.dropSlot = { index: slot.index };
    return slot.markerBlock.element;
  }
  const row = layerRowAtPoint(event.clientX, event.clientY);
  if (!row || row.dataset.layerListKey === layerDragState.key) return null;
  const previewRow = isGroupLayerKey(layerDragState.key)
    ? (layerBlockForKey(row.dataset.layerListKey)?.element || row)
    : row;
  previewRow.classList.add("layerDropTarget");
  if (layerDragState.mode === "reorder") {
    const rect = previewRow.getBoundingClientRect();
    previewRow.classList.add(event.clientY > rect.top + rect.height / 2 ? "layerDropAfter" : "layerDropBefore");
  }
  return previewRow;
}

function scrollLayerPaneDuringDrag(clientY) {
  const pane = layerScrollPane();
  if (!pane) return;
  const rect = pane.getBoundingClientRect();
  const edge = 42;
  if (clientY < rect.top + edge) pane.scrollTop -= Math.max(8, Math.round((rect.top + edge - clientY) * 0.55));
  else if (clientY > rect.bottom - edge) pane.scrollTop += Math.max(8, Math.round((clientY - (rect.bottom - edge)) * 0.55));
}

function handleLayerDragWheel(event) {
  if (!layerDragState) return;
  const pane = layerScrollPane();
  if (!pane) return;
  pane.scrollTop += event.deltaY;
  updateLayerDropPreview(event);
  event.preventDefault();
}

function selectLayerEntry(entry) {
  if (!entry?.objects?.length) return;
  if (entry.objects.length === 1) selectObjects(entry.objects, "layer");
  else selectObjects(entry.objects, "layer group");
}

function selectLayerEntryByKey(key, reason = "layer") {
  const entry = layerListRows.get(key);
  if (!entry) return false;
  selectLayerEntry(entry);
  lastLayerListKey = key;
  setStatus(entry.objects.length > 1 ? `Selected ${entry.objects.length} layer(s) by ${reason}.` : `Selected 1 layer by ${reason}.`);
  return true;
}

function clearLayerSelection(reason = "layer multi-select") {
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  updateSelectionPanel();
  updateLayerSelectionStyles();
  setStatus(`Cleared selection by ${reason}.`);
}

function selectLayerToggleByKey(key, reason = "layer multi-select") {
  const entry = layerListRows.get(key);
  if (!entry?.objects?.length) return false;
  const current = new Set(selectedVinylObjects());
  const allEntrySelected = entry.objects.every((object) => current.has(object));
  if (allEntrySelected) {
    entry.objects.forEach((object) => current.delete(object));
  } else {
    entry.objects.forEach((object) => current.add(object));
  }
  const canvasOrder = vinylObjects();
  const next = canvasOrder.filter((object) => current.has(object));
  lastLayerListKey = key;
  if (!next.length) {
    clearLayerSelection(reason);
    return true;
  }
  selectObjects(next, reason);
  setStatus(`Selected ${next.length} layer(s) by ${reason}.`);
  return true;
}

function displayObjectsFromCurrentStack() {
  return vinylObjects().slice().reverse();
}

function selectLayerRangeByKeys(startKey, endKey) {
  const start = layerListRows.get(startKey);
  const end = layerListRows.get(endKey);
  if (!start || !end) return false;
  const displayObjects = displayObjectsFromCurrentStack();
  const a = Math.max(0, Math.min(start.displayIndex, end.displayIndex));
  const b = Math.min(displayObjects.length - 1, Math.max(start.displayIndex, end.displayIndex));
  const selected = displayObjects.slice(a, b + 1);
  if (!selected.length) return false;
  selectObjects(selected, "layer range");
  lastLayerListKey = endKey;
  setStatus(`Selected layer range: ${selected.length} layer(s).`);
  return true;
}

function groupDisplayRange(startKey, endKey) {
  const start = layerListRows.get(startKey);
  const end = layerListRows.get(endKey);
  if (!start || !end) return false;
  const displayObjects = displayObjectsFromCurrentStack();
  const a = Math.max(0, Math.min(start.displayIndex, end.displayIndex));
  const b = Math.min(displayObjects.length - 1, Math.max(start.displayIndex, end.displayIndex));
  const range = displayObjects.slice(a, b + 1);
  if (range.length < 2) {
    setStatus("Drag across at least two layers to create an editor group.");
    return false;
  }
  selectObjects(range, "layer drag group");
  groupSelectedLayers();
  return true;
}

function dropLayerBlockAtSlot(dragObjects, slot) {
  const selectedSet = new Set(dragObjects || []);
  if (!selectedSet.size || !slot) return false;
  if (layerSearchActive()) {
    setStatus("Clear the layer search before dragging layers; filtered rows cannot safely define canvas depth.");
    return false;
  }
  const displayObjects = displayObjectsFromCurrentStack();
  const sourceObjects = displayObjects.filter((obj) => selectedSet.has(obj));
  if (!sourceObjects.length) return false;
  const blocks = reorderCandidateBlocks(sourceObjects);
  const insertIndex = Math.max(0, Math.min(slot.index, blocks.length));
  blocks.splice(insertIndex, 0, { key: "__dragged_layers__", objects: sourceObjects, element: null });
  const nextDisplay = blocks.flatMap((block) => block.objects);
  if (nextDisplay.length !== displayObjects.length) return false;
  if (nextDisplay.every((obj, index) => obj === displayObjects[index])) {
    setStatus("Layer order unchanged.");
    return false;
  }
  setVinylStackOrder(nextDisplay.slice().reverse());
  selectObjects(sourceObjects, sourceObjects.length > 1 ? "moved layer group" : "moved layer");
  refreshLayers();
  pushHistory("layer drag reorder");
  setStatus(`Moved ${sourceObjects.length > 1 ? `${sourceObjects.length} layers` : "1 layer"} in the layer stack.`);
  return true;
}

function handleLayerPointerDown(event) {
  if (event.button !== 0 || isLayerControlTarget(event.target)) return;
  const row = layerRowFromEventTarget(event.target);
  const key = row?.dataset.layerListKey;
  const entry = layerListRows.get(key);
  if (!row || !entry) return;
  event.preventDefault();
  row.setPointerCapture?.(event.pointerId);
  layerDragState = {
    key,
    objects: entry.objects.slice(),
    sourceElement: row,
    mode: event.shiftKey ? "group" : "reorder",
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    active: false,
  };
  document.body.classList.add("layerDragMaybe");
}

function handleLayerPointerMove(event) {
  if (!layerDragState || layerDragState.pointerId !== event.pointerId) return;
  const distance = Math.hypot(event.clientX - layerDragState.startX, event.clientY - layerDragState.startY);
  if (distance < 5) return;
  layerDragState.active = true;
  suppressLayerClick = true;
  layerDragState.sourceElement?.classList.add("layerDragSource");
  ensureLayerDragGhost(layerDragState);
  updateLayerDragGhost(event);
  document.body.classList.toggle("layerGroupingActive", layerDragState.mode === "group");
  document.body.classList.toggle("layerReorderActive", layerDragState.mode === "reorder");
  updateLayerDropPreview(event);
  scrollLayerPaneDuringDrag(event.clientY);
  event.preventDefault();
}

function handleLayerPointerUp(event) {
  if (!layerDragState || layerDragState.pointerId !== event.pointerId) return;
  const state = layerDragState;
  const targetRow = layerRowAtPoint(event.clientX, event.clientY);
  const targetKey = targetRow?.dataset.layerListKey;
  cancelLayerDrag();
  if (!state.active) {
    suppressLayerClick = true;
    setTimeout(() => { suppressLayerClick = false; }, 0);
    if (event.shiftKey && lastLayerListKey && selectLayerRangeByKeys(lastLayerListKey, state.key)) {
      event.preventDefault();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(state.key, "layer multi-select")) {
      event.preventDefault();
      return;
    }
    selectLayerEntryByKey(state.key, "layer row");
    event.preventDefault();
    return;
  }
  if (state.mode === "group") {
    if (!targetKey) return;
    groupDisplayRange(state.key, targetKey);
  } else {
    dropLayerBlockAtSlot(state.objects, state.dropSlot);
  }
  event.preventDefault();
}

function cancelLayerDrag() {
  layerDragState = null;
  document.body.classList.remove("layerDragMaybe", "layerGroupingActive", "layerReorderActive");
  clearLayerDropPreview();
  document.querySelectorAll(".layerDragSource").forEach((el) => el.classList.remove("layerDragSource"));
  if (layerDragGhost) {
    layerDragGhost.remove();
    layerDragGhost = null;
  }
  setTimeout(() => { suppressLayerClick = false; }, 0);
}

function updateLayerSelectionStyles() {
  const activeSet = new Set(selectedVinylObjects());
  layerListRows.forEach((entry) => {
    const active = entry.objects.some((obj) => activeSet.has(obj));
    entry.element.classList.toggle("active", active);
  });
  updateHud();
}

function scheduleRefreshLayers() {
  if (layerRefreshFrame) return;
  layerRefreshFrame = requestAnimationFrame(() => {
    layerRefreshFrame = null;
    refreshLayers();
  });
}

function refreshLayers() {
  if (layerRefreshFrame) {
    cancelAnimationFrame(layerRefreshFrame);
    layerRefreshFrame = null;
  }
  invalidateLayerStats();
  const list = $("layers");
  const fragment = document.createDocumentFragment();
  layerListRows = new Map();
  const objects = vinylObjects();
  layerStatsCache = {
    objects,
    count: objects.length,
    visible: objects.filter((obj) => obj.visible !== false && (obj.opacity ?? 1) > 0).length,
  };
  const activeSet = new Set(selectedVinylObjects());
  const filter = ($("layerSearch")?.value || "").trim().toLowerCase();
  const groupCounts = new Map();
  const groupNames = new Map();
  const groupVisibility = new Map();
  const groupLocks = new Map();
  objects.forEach((obj) => {
    const groupId = obj.kloudy?.group_id;
    if (!groupId) return;
    groupCounts.set(groupId, (groupCounts.get(groupId) || 0) + 1);
    groupNames.set(groupId, groupNameForObject(obj));
    const visibility = groupVisibility.get(groupId) || { visible: 0, hidden: 0 };
    if (obj.visible === false) visibility.hidden += 1;
    else visibility.visible += 1;
    groupVisibility.set(groupId, visibility);
    const locks = groupLocks.get(groupId) || { locked: 0, unlocked: 0 };
    if (obj.kloudy?.locked) locks.locked += 1;
    else locks.unlocked += 1;
    groupLocks.set(groupId, locks);
  });
  $("layerInfo").textContent = activeSet.size > 1
    ? `${activeSet.size} selected / ${objects.length} editable layer(s). Drag selection to move together.`
    : `${objects.length} editable layer(s). Export writes bottom-to-top order.`;
  const displayObjects = objects.slice().reverse();
  const renderedGroups = new Set();
  displayObjects.forEach((obj, reverseIndex) => {
    const actualIndex = objects.length - reverseIndex;
    const label = `${actualIndex}. ${obj.kloudy?.name || typeLabel(obj.kloudy?.type || 0)}`;
    const groupId = obj.kloudy?.group_id || null;
    const groupName = groupId ? groupNames.get(groupId) || groupNameForObject(obj) : "";
    const searchText = `${label} ${groupName} ${obj.kloudy?.type || ""} ${obj.kloudy?.type_word || ""}`.toLowerCase();
    if (filter && !searchText.includes(filter)) return;
    if (groupId && !renderedGroups.has(groupId)) {
      renderedGroups.add(groupId);
      const groupMembers = membersForGroupIds([groupId]);
      const groupActive = groupMembers.some((member) => activeSet.has(member));
      const visibility = groupVisibility.get(groupId) || { visible: 0, hidden: 0 };
      const locks = groupLocks.get(groupId) || { locked: 0, unlocked: 0 };
      const collapsed = collapsedLayerGroups.has(groupId);
      const groupLi = document.createElement("li");
      groupLi.className = `layerGroupRow${groupActive ? " active" : ""}${collapsed ? " collapsed" : ""}`;
      groupLi.innerHTML = `
        <button class="layerGroupTwist" type="button" title="${collapsed ? "Expand group" : "Collapse group"}">${collapsed ? "+" : "-"}</button>
        <span class="layerGroupTitle">${escapeHtml(groupName)}</span>
        <span class="layerGroupMeta">${groupMembers.length} layers | ${visibility.hidden ? `${visibility.hidden} hidden` : "visible"} | ${locks.locked ? `${locks.locked} locked` : "unlocked"}</span>
        <button class="layerIcon layerGroupVisibility" type="button" title="Hide/show this group">${visibility.visible ? "V" : "H"}</button>
        <button class="layerIcon layerGroupLock" type="button" title="Lock/unlock this group">${locks.unlocked ? "U" : "L"}</button>
      `;
      groupLi.querySelector(".layerGroupTwist").addEventListener("click", (event) => {
        event.stopPropagation();
        setCollapsedGroup(groupId, !collapsed);
      });
      groupLi.querySelector(".layerGroupVisibility").addEventListener("click", (event) => {
        event.stopPropagation();
        selectObjects(groupMembers, groupName);
        toggleSelectedGroupVisibility();
      });
      groupLi.querySelector(".layerGroupLock").addEventListener("click", (event) => {
        event.stopPropagation();
        selectObjects(groupMembers, groupName);
        toggleSelectedGroupLock();
      });
      registerLayerListRow(groupLi, `group:${groupId}`, groupMembers, reverseIndex);
      groupLi.addEventListener("click", (event) => {
        if (suppressLayerClick) return;
        if (event.shiftKey && lastLayerListKey && selectLayerRangeByKeys(lastLayerListKey, `group:${groupId}`)) return;
        if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(`group:${groupId}`, "layer multi-select")) return;
        selectObjects(groupMembers, groupName);
        lastLayerListKey = `group:${groupId}`;
      });
      fragment.appendChild(groupLi);
    }
    if (groupId && collapsedLayerGroups.has(groupId)) return;
    const li = document.createElement("li");
    li.className = "layerRow";
    if (groupId) li.classList.add("groupedLayer");
    if (activeSet.has(obj)) li.classList.add("active");
    if (obj.visible === false) li.classList.add("hiddenLayer");
    if (obj.kloudy?.locked) li.classList.add("lockedLayer");
    const color = hexToRgb(obj.fill || "#ffffff", (obj.opacity ?? 1) * 255);
    const groupBadge = obj.kloudy?.group_id
      ? `<button class="layerGroupBadge" type="button" title="Select all layers in ${escapeHtml(groupNameForObject(obj))}.">${escapeHtml(groupNameForObject(obj))} (${groupCounts.get(obj.kloudy.group_id) || 1})</button>`
      : "";
    li.innerHTML = `
      <button class="layerIcon layerVisibility" type="button" title="${obj.visible === false ? "Show layer" : "Hide layer"}">${obj.visible === false ? "H" : "V"}</button>
      <button class="layerIcon layerLock" type="button" title="${obj.kloudy?.locked ? "Unlock layer" : "Lock layer"}">${obj.kloudy?.locked ? "L" : "U"}</button>
      <span class="layerColorChip" style="--swatch:${colorToHex(color)}"></span>
      <span class="layerMain">
        <b>${escapeHtml(label)}</b>
        <small>${groupBadge} Type ${escapeHtml(obj.kloudy?.type || "unknown")} | X ${round(fh6DataFromObject(obj)[0])} Y ${round(fh6DataFromObject(obj)[1])}</small>
      </span>
    `;
    li.querySelector(".layerGroupBadge")?.addEventListener("click", (event) => {
      event.stopPropagation();
      selectGroupForObject(obj);
    });
    li.querySelector(".layerVisibility").addEventListener("click", (event) => {
      event.stopPropagation();
      obj.visible = obj.visible === false;
      canvas.requestRenderAll();
      refreshLayers();
      pushHistory("layer visibility");
    });
    li.querySelector(".layerLock").addEventListener("click", (event) => {
      event.stopPropagation();
      const locked = !obj.kloudy?.locked;
      setObjectLocked(obj, locked);
      canvas.requestRenderAll();
      refreshLayers();
      updateSelectionPanel();
      pushHistory("layer lock");
    });
    li.addEventListener("click", (event) => {
      if (suppressLayerClick) return;
      const key = layerListObjectKey(obj);
      if (event.shiftKey && lastLayerListKey && selectLayerRangeByKeys(lastLayerListKey, key)) return;
      if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(key, "layer multi-select")) return;
      selectLayerEntryByKey(key, "layer row");
    });
    registerLayerListRow(li, layerListObjectKey(obj), [obj], reverseIndex);
    fragment.appendChild(li);
  });
  list.replaceChildren(fragment);
  setText("exportWarningCount", "0");
  setText("normalExportStatus", "Compatible");
  setText("exportReadyChip", objects.length ? "Ready" : "No JSON");
  updateHud();
}

function updateSelectionPanel() {
  const selected = selectedVinylObjects();
  syncSelectedShapeOutlines(selected);
  const enabled = selected.length === 1;
  ["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput"].forEach((id) => {
    $(id).disabled = !enabled;
  });
  $("colorPicker").disabled = selected.length < 1;
  $("applyFields").disabled = selected.length < 1;
  $("applyColorToSelection").disabled = selected.length < 1;
  const maskTool = $("maskSelectedTool");
  if (maskTool) maskTool.disabled = selected.length < 1;
  ["quickDuplicateLayer", "quickDeleteLayer", "quickFitSelected"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = selected.length < 1;
  });
  const quickGroup = $("quickGroupSelected");
  if (quickGroup) quickGroup.disabled = selected.length < 2;
  const sharedAlpha = sharedSelectedAlpha(selected);
  $("opacitySlider").disabled = selected.length < 1;
  $("equalizeAlpha").disabled = selected.length < 2;
  if (!enabled) {
    $("selectedShapeName").textContent = selected.length > 1 ? `${selected.length} layers selected` : "No layer selected";
    $("selectedShapeCode").textContent = selected.length > 1
      ? (sharedAlpha === null ? "Mixed alpha. Color applies to all selected layers; alpha uses the slider value." : `Shared alpha ${sharedAlpha}. Color and alpha apply to all selected layers.`)
      : "Click a layer or a shape tile.";
    if (selected.length > 1) $("opacitySlider").value = sharedAlpha ?? rememberedColor[3] ?? 255;
    if (selected.length > 1) {
      $("layerInfo").textContent = `${selected.length} layer(s) selected. Drag the selection box to move them together. Color edits apply to unlocked selected layers.`;
    }
    refreshColorUi();
    updateLayerSelectionStyles();
    return;
  }
  const obj = selected[0];
  $("selectedShapeName").textContent = obj.kloudy?.name || typeLabel(obj.kloudy?.type || 0);
  $("selectedShapeCode").textContent = `Type ${obj.kloudy?.type || "unknown"}${obj.kloudy?.mask ? " / mask" : ""}`;
  $("colorPicker").value = colorToHex(currentPanelColor());
  $("opacitySlider").value = alphaForObject(obj);
  updateObjectScaleSigns(obj);
  const decoded = fh6DataFromObject(obj, currentScaleSigns(obj));
  $("xInput").value = round(decoded[0]);
  $("yInput").value = round(decoded[1]);
  $("sxInput").value = round(decoded[2]);
  $("syInput").value = round(decoded[3]);
  $("rotInput").value = round(decoded[4]);
  $("skewInput").value = round(obj.skewX || 0);
  refreshColorUi();
  updateLayerSelectionStyles();
}

function applySelectionFields() {
  const selected = selectedVinylObjects();
  if (selected.length > 1) {
    const editable = unlockedObjects(selected);
    if (!editable.length) {
      setStatus("Selected layers are locked. Unlock them before editing.");
      updateSelectionPanel();
      return;
    }
    if (editable.length !== selected.length) {
      setStatus(`Skipped ${selected.length - editable.length} locked layer(s). Unlock them before batch editing.`);
    }
    const alpha = Math.max(0, Math.min(255, Math.round(Number($("opacitySlider").value) || 0)));
    const color = hexToRgb($("colorPicker").value || colorToHex(rememberedColor), alpha);
    editable.forEach((obj) => {
      applyObjectColor(obj, color);
      obj.setCoords();
    });
    rememberColor(color);
    canvas.requestRenderAll();
    updateSelectionPanel();
    pushHistory("batch appearance edit");
    setStatus(`Applied ${colorToHex(color).toUpperCase()} / A ${alpha} to ${editable.length} selected layer(s).${editable.length !== selected.length ? " Locked layers were skipped." : ""}`);
    return;
  }
  const obj = selected[0];
  if (!obj || !obj.kloudy) return;
  if (obj.kloudy.locked) {
    setStatus("Selected layer is locked. Unlock it before editing.");
    updateSelectionPanel();
    return;
  }
  const color = hexToRgb($("colorPicker").value, $("opacitySlider").value);
  rememberColor(color);
  const transformProps = fabricPropsFromFh6Data([
    Number($("xInput").value) || 0,
    Number($("yInput").value) || 0,
    Number($("sxInput").value) || 1,
    Number($("syInput").value) || 1,
    Number($("rotInput").value) || 0,
    fh6SkewFromFabricDegrees(
      Number($("skewInput").value) || 0,
      Number($("sxInput").value) || 1,
      Number($("syInput").value) || 1
    ),
  ]);
  obj.set({
    ...transformProps,
  });
  applyObjectColor(obj, color);
  obj.kloudy.scaleSigns = {
    x: (Number($("sxInput").value) || 1) < 0 ? -1 : 1,
    y: (Number($("syInput").value) || 1) < 0 ? -1 : 1,
  };
  applyMaskVisual(obj);
  obj.setCoords();
  applyLiveOverlayColor(obj);
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("field edit");
}

function applyMaskVisual(obj) {
  if (!obj || !obj.kloudy) return;
  if (obj.kloudy.mask) {
    if (!Array.isArray(obj.kloudy.maskOriginalColor)) {
      obj.kloudy.maskOriginalColor = hexToRgb(obj.fill || "#ffffff", (obj.opacity ?? 1) * 255);
    }
    obj.set({
      fill: "rgba(255,36,79,0.001)",
      opacity: 1,
      stroke: null,
      strokeWidth: 0,
      globalCompositeOperation: "source-over",
      selectable: !obj.kloudy?.locked,
      evented: !obj.kloudy?.locked,
      perPixelTargetFind: false,
      targetFindTolerance: 18,
    });
  } else {
    if (Array.isArray(obj.kloudy.maskOriginalColor)) {
      const color = normalizeColor(obj.kloudy.maskOriginalColor);
      obj.set({
        fill: colorToHex(color),
        opacity: color[3] / 255,
      });
    }
    obj.set({
      stroke: null,
      strokeWidth: 0,
      globalCompositeOperation: "source-over",
      selectable: !obj.kloudy?.locked,
      evented: !obj.kloudy?.locked,
      perPixelTargetFind: $("boxVisibleOnly")?.checked ?? true,
      targetFindTolerance: ($("boxVisibleOnly")?.checked ?? true) ? VINYL_HIT_TOLERANCE : 0,
    });
    obj.kloudy.maskOriginalColor = null;
  }
  syncMaskPreviewOutlines();
}

function makeMaskHelperBaseForObject(obj) {
  const base = obj?.type === "path" && Array.isArray(obj.path)
    ? new fabric.Path(obj.path, { originX: "center", originY: "center" })
    : new fabric.Rect({
      originX: "center",
      originY: "center",
      width: Math.max(1, Number(obj?.width) || 1),
      height: Math.max(1, Number(obj?.height) || 1),
    });
  base.set({
    objectCaching: false,
    excludeFromExport: true,
  });
  return base;
}

function makeMaskCutoutForObject(obj) {
  const base = makeMaskHelperBaseForObject(obj);
  base.set({
    fill: "#000000",
    opacity: 1,
    stroke: null,
    strokeWidth: 0,
    globalCompositeOperation: "destination-out",
    selectable: false,
    evented: false,
  });
  base.kloudyMaskCutout = true;
  return base;
}

function makeMaskOutlineForObject(obj) {
  const base = makeMaskHelperBaseForObject(obj);
  base.set({
    fill: "rgba(255,36,79,0.001)",
    stroke: "#ff244f",
    strokeWidth: 4,
    strokeUniform: true,
    selectable: true,
    evented: true,
    perPixelTargetFind: false,
    targetFindTolerance: 18,
    objectCaching: false,
    excludeFromExport: true,
    globalCompositeOperation: "source-over",
    hoverCursor: "move",
    moveCursor: "move",
  });
  base.kloudyMaskOutline = true;
  base.kloudyMaskOwner = obj;
  styleObjectTransformControls(base);
  return base;
}

function syncMaskHelperTransform(obj, helper) {
  if (!obj || !helper) return;
  const locked = Boolean(obj.kloudy?.locked);
  helper.set({
    left: obj.left,
    top: obj.top,
    scaleX: obj.scaleX,
    scaleY: obj.scaleY,
    angle: obj.angle,
    skewX: obj.skewX,
    skewY: obj.skewY,
    flipX: obj.flipX,
    flipY: obj.flipY,
    visible: obj.visible !== false && Boolean(obj.kloudy?.mask),
    selectable: !locked && Boolean(helper.kloudyMaskOutline),
    evented: !locked && Boolean(helper.kloudyMaskOutline),
    hasControls: !locked && Boolean(helper.kloudyMaskOutline),
    lockMovementX: locked,
    lockMovementY: locked,
    lockScalingX: locked,
    lockScalingY: locked,
    lockRotation: locked,
  });
  helper.setCoords();
}

function syncMaskPreviewOutlines() {
  if (!canvas) return;
  const wanted = new Set(vinylObjects().filter((obj) => obj.kloudy?.mask));
  maskPreviewCutouts.forEach((cutout, obj) => {
    if (!wanted.has(obj) || !canvas.getObjects().includes(obj)) {
      canvas.remove(cutout);
      maskPreviewCutouts.delete(obj);
    }
  });
  maskPreviewOutlines.forEach((outline, obj) => {
    if (!wanted.has(obj) || !canvas.getObjects().includes(obj)) {
      canvas.remove(outline);
      maskPreviewOutlines.delete(obj);
    }
  });
  wanted.forEach((obj) => {
    let cutout = maskPreviewCutouts.get(obj);
    if (!cutout) {
      cutout = makeMaskCutoutForObject(obj);
      maskPreviewCutouts.set(obj, cutout);
      canvas.add(cutout);
    }
    let outline = maskPreviewOutlines.get(obj);
    if (!outline) {
      outline = makeMaskOutlineForObject(obj);
      maskPreviewOutlines.set(obj, outline);
      canvas.add(outline);
    }
    syncMaskHelperTransform(obj, cutout);
    syncMaskHelperTransform(obj, outline);
    cutout.bringToFront();
    outline.bringToFront();
  });
}

function syncMaskPreviewForTarget(target) {
  if (!target) return;
  const objects = isActiveSelectionObject(target) ? selectedVinylObjects() : [interactiveVinylTarget(target)];
  objects.forEach((obj) => {
    if (!obj?.kloudy?.mask) return;
    const cutout = maskPreviewCutouts.get(obj);
    const outline = maskPreviewOutlines.get(obj);
    if (cutout) syncMaskHelperTransform(obj, cutout);
    if (outline) syncMaskHelperTransform(obj, outline);
  });
}

function toggleSelectedMaskLayers() {
  const selected = selectedVinylObjects();
  if (!selected.length) {
    setStatus("Select one or more layers first.");
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus("Selected layers are locked. Unlock them before marking them as masks.");
    return;
  }
  const shouldMask = editable.some((obj) => !obj.kloudy?.mask);
  let changed = 0;
  editable.forEach((obj) => {
    if (!obj.kloudy) return;
    if (Boolean(obj.kloudy.mask) !== shouldMask) changed += 1;
    obj.kloudy.mask = shouldMask;
    applyMaskVisual(obj);
    obj.setCoords();
  });
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory(shouldMask ? "make mask layer" : "clear mask layer");
  setStatus(
    changed
      ? `${shouldMask ? "Marked" : "Cleared"} ${changed} layer(s) ${shouldMask ? "as mask/cutout layers" : "back to normal vinyl layers"}.`
      : `Selected editable layers were already ${shouldMask ? "mask layers" : "normal layers"}.`
  );
}

function equalizeSelectedAlpha() {
  const selected = selectedVinylObjects();
  if (selected.length < 2) {
    setStatus("Select two or more layers before equalizing alpha.");
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus("Selected layers are locked. Unlock them before equalizing alpha.");
    return;
  }
  const alpha = alphaForObject(editable[0]);
  editable.forEach((obj) => {
    obj.set({ opacity: alpha / 255 });
    obj.setCoords();
  });
  $("opacitySlider").value = alpha;
  rememberColor([rememberedColor[0], rememberedColor[1], rememberedColor[2], alpha]);
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("equalize alpha");
  setStatus(`Equalized ${editable.length} selected layer(s) to alpha ${alpha}.${editable.length !== selected.length ? " Locked layers were skipped." : ""}`);
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function cleanProjectBaseName(name, fallback = "vinyl") {
  let base = String(name || fallback)
    .replace(/\\/g, "/")
    .split("/")
    .pop()
    .trim();
  base = base
    .replace(/\.json$/i, "")
    .replace(/\.fabric-project$/i, "")
    .replace(/\.fabric-export$/i, "")
    .replace(/\.normal-import$/i, "")
    .replace(/\.fh6-import$/i, "");
  base = base.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/\s+/g, " ").trim();
  return base || fallback;
}

function filenameWithSuffix(baseName, suffix) {
  return `${cleanProjectBaseName(baseName)}.${suffix}.json`;
}

async function saveEditorJsonToAppFolder(name, payload) {
  const response = await fetch(EDITOR_EXPORT_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, payload }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function saveProjectToAppFolder(name, payload) {
  const response = await fetch(PROJECT_SAVE_API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, payload }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

async function exportJson() {
  if (exportSaveInProgress) {
    setStatus("Export is already saving. Wait for it to finish.");
    return;
  }
  const shapes = vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: false }));
  if (!shapes.length) {
    setStatus("Nothing to export. Import a JSON or add at least one shape first.");
    return;
  }
  const defaultName = cleanProjectBaseName(currentProjectName || loadedName, "vinyl");
  let exportName = currentProjectName;
  if (!exportName) {
    const requestedName = window.prompt("Export JSON name", defaultName);
    if (requestedName === null) {
      setStatus("JSON export cancelled.");
      return;
    }
    exportName = cleanProjectBaseName(requestedName, defaultName);
    loadedName = exportName;
  }
  const payload = { shapes };
  exportSaveInProgress = true;
  const exportButton = $("exportJson");
  if (exportButton) exportButton.disabled = true;
  try {
    const result = await saveEditorJsonToAppFolder(exportName, payload);
    setJsonBrowserSource("editor");
    await refreshJsonBrowser();
    selectJsonBrowserEntryById(result.id);
    setStatus(`Exported ${shapes.length} layer(s) to imgs/editor/${result.name || `${exportName}.fh6-import.json`}.`);
    showCornerNotice("FH6 JSON saved inside KFPS", "Open Import JSON, choose Editor exports, and import it from there.");
  } catch (err) {
    downloadText(filenameWithSuffix(exportName, "fh6-import"), JSON.stringify(payload, null, 2));
    setStatus(`Saved-to-folder failed (${err.message || err}). Downloaded ${shapes.length} layer(s) instead.`);
  } finally {
    exportSaveInProgress = false;
    if (exportButton) exportButton.disabled = false;
  }
}

async function saveProject() {
  if (projectSaveInProgress) {
    setStatus("Project save is already running. Wait for it to finish.");
    return;
  }
  if (!vinylObjects().length) {
    setStatus("Nothing to save. Import a JSON or add at least one shape first.");
    return;
  }
  const defaultName = cleanProjectBaseName(loadedName, "vinyl");
  const requestedName = window.prompt("Project name", defaultName);
  if (requestedName === null) {
    setStatus("Project save cancelled.");
    return;
  }
  const projectName = cleanProjectBaseName(requestedName, defaultName);
  loadedName = projectName;
  currentProjectName = projectName;
  const payload = {
    format: "kloudy_fabric_editor_project_v1",
    name: projectName,
    shapes: vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: true })),
    editor_guides: savedGuideState(),
    editor_collapsed_groups: collapsedLayerGroupIds(),
  };
  const sourceOverlay = sourceOverlayProjectState();
  if (sourceOverlay) payload.editor_source_overlay = sourceOverlay;
  projectSaveInProgress = true;
  const saveButton = $("saveProject");
  if (saveButton) saveButton.disabled = true;
  try {
    const result = await saveProjectToAppFolder(projectName, payload);
    clearAutosave();
    setStatus(`Saved project internally: ${result.title || projectName}`);
    showCornerNotice("Project saved inside KFPS", "Use Load Project to reopen it from the internal project browser.");
  } catch (err) {
    setStatus(`Project save failed: ${err.message || err}`);
    showError("Project save failed", err);
  } finally {
    projectSaveInProgress = false;
    if (saveButton) saveButton.disabled = false;
  }
}

async function loadProjectPayload(payload, displayName = "project") {
  setBusy(`Loading project: ${displayName}`);
  await nextFrame();
  if (!Array.isArray(payload.shapes)) throw new Error("Project JSON must contain a shapes list.");
  const previousName = loadedName;
  const projectName = cleanProjectBaseName(payload.name || displayName, "project");
  loadedName = projectName;
  currentProjectName = projectName;
  try {
    await loadPayload({
      shapes: payload.shapes,
      editor_collapsed_groups: payload.editor_collapsed_groups || [],
    });
    applySavedGuideState(payload.editor_guides || null);
    await restoreSourceOverlayFromProject(payload.editor_source_overlay || null);
  } catch (err) {
    loadedName = previousName;
    currentProjectName = null;
    throw err;
  }
}

async function loadProjectFile(file) {
  const payload = JSON.parse(await file.text());
  await loadProjectPayload(payload, file.name);
}

function viewportCenterPoint() {
  const inverse = fabric.util.invertTransform(canvas.viewportTransform);
  return fabric.util.transformPoint(new fabric.Point(canvas.width / 2, canvas.height / 2), inverse);
}

function placeNewObjectInViewport(object) {
  const center = viewportCenterPoint();
  object.set({ left: center.x, top: center.y });
  object.setCoords();
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const currentMax = Math.max(object.getScaledWidth(), object.getScaledHeight(), 1);
  const targetScreenSize = Math.max(56, Math.min(128, Math.min(canvas.width, canvas.height) * 0.14));
  const scaleFactor = targetScreenSize / (currentMax * zoom);
  object.set({
    scaleX: (object.scaleX || 1) * scaleFactor,
    scaleY: (object.scaleY || 1) * scaleFactor,
  });
  object.setCoords();
}

function shapePlacementMode() {
  return $("shapePlacementMode")?.value || "top";
}

function updateShapePlacementLabel() {
  const select = $("shapePlacementMode");
  const label = $("shapePlacementModeLabel");
  if (!select || !label) return;
  label.textContent = select.options[select.selectedIndex]?.textContent || "Add at top";
}

function shapeWordForObject(object) {
  const meta = object?.kloudy || {};
  const word = Number(meta.type_word ?? (Number(meta.type) & 0xffff));
  return Number.isFinite(word) ? (word & 0xffff) : null;
}

function resolvedResourceForObject(object) {
  const meta = object?.kloudy || {};
  if (meta.resource_family && meta.resource_index) {
    return {
      family: String(meta.resource_family),
      index: Number(meta.resource_index),
      typeCode: Number(meta.type),
      shapeWord: shapeWordForObject(object),
    };
  }
  const typeCode = Number(meta.type);
  if (Number.isFinite(typeCode)) return typeCodeToResource(typeCode);
  return null;
}

function hideGlobalShapeReplacePanel() {
  const panel = $("globalShapeReplacePanel");
  if (panel) panel.hidden = true;
}

function shapeReplaceListEntry(object) {
  const word = shapeWordForObject(object);
  if (word === null) return null;
  const resource = resolvedResourceForObject(object);
  const family = resource?.family || object.kloudy?.resource_family || "Unknown";
  const index = Number(resource?.index || object.kloudy?.resource_index || 0);
  const name = object.kloudy?.name || (resource ? shapeDisplayName(resource.family, resource.index) : `Shape word ${word}`);
  return { word, family, index, name };
}

function renderGlobalShapeReplacePanel() {
  const panel = $("globalShapeReplacePanel");
  const list = $("globalShapeReplaceList");
  if (!panel || !list) return;
  const used = new Map();
  vinylObjects().forEach((object) => {
    const entry = shapeReplaceListEntry(object);
    if (!entry) return;
    const key = String(entry.word);
    const existing = used.get(key);
    if (existing) existing.count += 1;
    else used.set(key, { ...entry, count: 1 });
  });
  list.innerHTML = "";
  if (!used.size) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No replaceable vinyl shapes are loaded.";
    list.appendChild(empty);
    panel.hidden = false;
    return;
  }
  [...used.values()]
    .sort((a, b) => a.name.localeCompare(b.name) || a.word - b.word)
    .forEach((entry) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "usedShapeButton";
      const thumb = entry.family !== "Unknown" && entry.index ? vinylResourceUrl(entry.family, entry.index, ".png") : "";
      button.innerHTML = `
        ${thumb ? `<img alt="" src="${thumb}">` : "<span></span>"}
        <span>
          <b>${escapeHtml(entry.name)}</b>
          <span>${entry.count} layer${entry.count === 1 ? "" : "s"} / word ${entry.word}</span>
        </span>
      `;
      button.addEventListener("click", () => armGlobalShapeReplacement(entry));
      list.appendChild(button);
    });
  panel.hidden = false;
}

function armGlobalShapeReplacement(entry) {
  pendingGlobalShapeReplacement = {
    word: Number(entry.word) & 0xffff,
    name: entry.name || `word ${entry.word}`,
    count: Number(entry.count) || 0,
  };
  hideGlobalShapeReplacePanel();
  const placement = $("shapePlacementMode");
  if (placement) {
    placement.value = "top";
    updateShapePlacementLabel();
  }
  canvas?.discardActiveObject();
  syncSelectedShapeOutlines([]);
  const shapeTool = document.querySelector('.toolButton[data-tool-mode="shapeLibrary"]');
  if (shapeTool) setActiveTool(shapeTool);
  else activateDockPanel("shapeLibraryPane");
  setStatus(`Global Change Shape armed for ${pendingGlobalShapeReplacement.name} (${pendingGlobalShapeReplacement.count} layer${pendingGlobalShapeReplacement.count === 1 ? "" : "s"}). Click a shape tile to replace every matching layer.`);
}

function armShapeReplacementFromLayers() {
  const selected = selectedVinylObjects();
  if (!selected.length) {
    pendingGlobalShapeReplacement = null;
    renderGlobalShapeReplacePanel();
    setStatus("No layers selected. Choose a used shape type, then click its replacement in Shape Library.");
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus("Selected layers are locked. Unlock them before changing shape type.");
    return;
  }
  pendingGlobalShapeReplacement = null;
  hideGlobalShapeReplacePanel();
  const placement = $("shapePlacementMode");
  if (placement) {
    placement.value = "replace";
    updateShapePlacementLabel();
  }
  const shapeTool = document.querySelector('.toolButton[data-tool-mode="shapeLibrary"]');
  if (shapeTool) setActiveTool(shapeTool);
  else activateDockPanel("shapeLibraryPane");
  setStatus(`Change Shape armed for ${editable.length} selected layer(s). Click a shape tile to replace them.${editable.length !== selected.length ? ` ${selected.length - editable.length} locked layer(s) will be skipped.` : ""}`);
}

function orderedSelectedVinylObjects() {
  const selected = selectedVinylObjects();
  const all = canvas.getObjects();
  return selected.slice().sort((a, b) => all.indexOf(a) - all.indexOf(b));
}

function insertionReferenceForMode(mode) {
  const ordered = orderedSelectedVinylObjects();
  if (!ordered.length) return null;
  if (mode === "below") return ordered[0];
  return ordered[ordered.length - 1];
}

function insertNewVinylObject(object, mode) {
  if (mode !== "above" && mode !== "below") {
    canvas.add(object);
    return true;
  }
  const reference = insertionReferenceForMode(mode);
  if (!reference) {
    setStatus("Select a layer before using Insert above/below selected.");
    return false;
  }
  const referenceIndex = canvas.getObjects().indexOf(reference);
  canvas.add(object);
  object.moveTo(mode === "below" ? referenceIndex : referenceIndex + 1);
  return true;
}

function insertDuplicateVinylObjects(clones, originals, mode) {
  if (mode !== "above" && mode !== "below") {
    clones.forEach((clone) => canvas.add(clone));
    return "top";
  }
  const all = canvas.getObjects();
  const orderedOriginals = originals
    .filter((obj) => all.includes(obj))
    .slice()
    .sort((a, b) => all.indexOf(a) - all.indexOf(b));
  if (!orderedOriginals.length) {
    clones.forEach((clone) => canvas.add(clone));
    return "top";
  }

  const reference = mode === "below" ? orderedOriginals[0] : orderedOriginals[orderedOriginals.length - 1];
  const referenceIndex = canvas.getObjects().indexOf(reference);
  clones.forEach((clone, offset) => {
    canvas.add(clone);
    clone.moveTo(mode === "below" ? referenceIndex + offset : referenceIndex + 1 + offset);
  });
  return mode;
}

function selectionBoundsForObjects(objects) {
  const points = [];
  objects.forEach((obj) => {
    const coords = objectCornerCoords(obj);
    points.push(coords.tl, coords.tr, coords.bl, coords.br);
  });
  if (!points.length) return null;
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  return {
    left: minX,
    top: minY,
    width: maxX - minX,
    height: maxY - minY,
    center: { x: (minX + maxX) / 2, y: (minY + maxY) / 2 },
  };
}

function reflectMatrixForBounds(bounds, axis) {
  if (!bounds?.center) return null;
  return axis === "x"
    ? [-1, 0, 0, 1, bounds.center.x * 2, 0]
    : [1, 0, 0, -1, 0, bounds.center.y * 2];
}

function applyReusableFontTransform(object, family) {
  if (!reuseLastFontSize || !isFontFamily(family) || !lastFontShapeTransform) return;
  object.set({
    scaleX: lastFontShapeTransform.scaleX,
    scaleY: lastFontShapeTransform.scaleY,
    angle: lastFontShapeTransform.angle,
    skewX: lastFontShapeTransform.skewX,
  });
  object.setCoords();
}

function updateShapeResourceOnShape(shape, family, index) {
  const typeCode = resourceToTypeCode(family, index);
  const shapeWord = resourceToShapeWord(family, index);
  return {
    ...shape,
    type: typeCode,
    type_word: shapeWord,
    resource_family: family,
    resource_index: index,
    shape_name: shapeDisplayName(family, index),
  };
}

async function replaceSelectedShapes(family, index) {
  const selected = orderedSelectedVinylObjects();
  if (!selected.length) {
    setStatus("Select one or more layers before replacing their shape type.");
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus("Selected layers are locked. Unlock them before replacing shape type.");
    return;
  }
  const replacements = [];
  for (const oldObject of editable) {
    const oldIndex = canvas.getObjects().indexOf(oldObject);
    const shape = updateShapeResourceOnShape(objectToShape(oldObject, { includeEditorMeta: true }), family, index);
    const replacement = await makeFabricObject(shape);
    replacement.visible = oldObject.visible;
    replacements.push({ oldObject, oldIndex, replacement });
  }
  replacements.forEach(({ oldObject }) => canvas.remove(oldObject));
  replacements.forEach(({ oldIndex, replacement }) => {
    canvas.add(replacement);
    replacement.moveTo(Math.max(0, oldIndex));
    if (isFontFamily(family)) rememberFontShapeTransform(replacement);
  });
  syncMaskPreviewOutlines();
  bringGuidesToBack();
  syncCanvasObjectCoords();
  selectObjects(replacements.map((item) => item.replacement), "shape replacement");
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("replace shape type");
  setStatus(`Replaced ${replacements.length} layer(s) with ${shapeDisplayName(family, index)}.${editable.length !== selected.length ? ` Skipped ${selected.length - editable.length} locked layer(s).` : ""}`);
}

async function replaceMatchingShapeWords(source, family, index) {
  const rawSourceWord = Number(source?.word);
  if (!Number.isFinite(rawSourceWord)) {
    pendingGlobalShapeReplacement = null;
    setStatus("Global Change Shape cancelled because the source shape was invalid.");
    return;
  }
  const sourceWord = rawSourceWord & 0xffff;
  const matches = vinylObjects().filter((object) => shapeWordForObject(object) === sourceWord);
  if (!matches.length) {
    pendingGlobalShapeReplacement = null;
    setStatus("No matching layers remain for that source shape.");
    return;
  }
  const editable = unlockedObjects(matches);
  if (!editable.length) {
    pendingGlobalShapeReplacement = null;
    setStatus("Matching layers are locked. Unlock them before replacing shape type.");
    return;
  }
  const replacements = [];
  for (const oldObject of editable) {
    const oldIndex = canvas.getObjects().indexOf(oldObject);
    const shape = updateShapeResourceOnShape(objectToShape(oldObject, { includeEditorMeta: true }), family, index);
    const replacement = await makeFabricObject(shape);
    replacement.visible = oldObject.visible;
    replacements.push({ oldObject, oldIndex, replacement });
  }
  replacements.forEach(({ oldObject }) => canvas.remove(oldObject));
  replacements.forEach(({ oldIndex, replacement }) => {
    canvas.add(replacement);
    replacement.moveTo(Math.max(0, oldIndex));
    if (isFontFamily(family)) rememberFontShapeTransform(replacement);
  });
  pendingGlobalShapeReplacement = null;
  syncMaskPreviewOutlines();
  bringGuidesToBack();
  syncCanvasObjectCoords();
  selectObjects(replacements.map((item) => item.replacement), "global shape replacement");
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("replace shape globally");
  setStatus(`Replaced ${replacements.length} ${source.name || `word ${sourceWord}`} layer(s) with ${shapeDisplayName(family, index)}.${editable.length !== matches.length ? ` Skipped ${matches.length - editable.length} locked layer(s).` : ""}`);
}

async function addShape(family, index) {
  if (pendingGlobalShapeReplacement) {
    await replaceMatchingShapeWords(pendingGlobalShapeReplacement, family, index);
    return;
  }
  const mode = shapePlacementMode();
  if (mode === "replace") {
    await replaceSelectedShapes(family, index);
    return;
  }
  const typeCode = resourceToTypeCode(family, index);
  const shapeWord = resourceToShapeWord(family, index);
  const shape = {
    type: typeCode,
    type_word: shapeWord,
    resource_family: family,
    resource_index: index,
    shape_name: shapeDisplayName(family, index),
    data: [0, 0, 1, 1, 0, 0, 0],
    color: rememberedColor,
    mask: false,
    score: 0,
  };
  const object = await makeFabricObject(shape);
  placeNewObjectInViewport(object);
  applyReusableFontTransform(object, family);
  if (!insertNewVinylObject(object, mode)) return;
  canvas.setActiveObject(object);
  applyLiveOverlayColor(object);
  if (isFontFamily(family)) rememberFontShapeTransform(object);
  bringGuidesToBack();
  syncCanvasObjectCoords();
  canvas.requestRenderAll();
  refreshLayers();
  updateSelectionPanel();
  pushHistory(mode === "top" ? "add shape" : `insert shape ${mode}`);
}

function setPixelArtStatus(message) {
  setText("pixelArtStatus", message);
  setStatus(message);
}

function setTextVinylStatus(message) {
  setText("textVinylStatus", message);
  setStatus(message);
}

function numberInputValue(id, fallback, min, max) {
  const raw = Number($(id)?.value);
  const value = Number.isFinite(raw) ? raw : fallback;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function setPixelArtGridInputs(grid) {
  if (!grid) return;
  const widthInput = $("pixelArtGridW");
  const heightInput = $("pixelArtGridH");
  if (widthInput) widthInput.value = String(grid.gridW);
  if (heightInput) heightInput.value = String(grid.gridH);
}

function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    if (!file) {
      reject(new Error("Choose a pixel-art source image first."));
      return;
    }
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Could not read image: ${file.name || "source"}`));
    };
    image.src = url;
  });
}

function colorDistance(a, b) {
  return Math.max(
    Math.abs(Number(a?.[0] || 0) - Number(b?.[0] || 0)),
    Math.abs(Number(a?.[1] || 0) - Number(b?.[1] || 0)),
    Math.abs(Number(a?.[2] || 0) - Number(b?.[2] || 0)),
    Math.abs(Number(a?.[3] ?? 255) - Number(b?.[3] ?? 255)),
  );
}

function pixelArtImageData(image) {
  const width = Number(image?.naturalWidth || image?.width || 1);
  const height = Number(image?.naturalHeight || image?.height || 1);
  const sampler = document.createElement("canvas");
  sampler.width = width;
  sampler.height = height;
  const ctx = sampler.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(image, 0, 0);
  return { width, height, data: ctx.getImageData(0, 0, width, height).data };
}

function pixelArtColorAt(pixelData, x, y) {
  const offset = ((y * pixelData.width) + x) * 4;
  return [
    pixelData.data[offset],
    pixelData.data[offset + 1],
    pixelData.data[offset + 2],
    pixelData.data[offset + 3],
  ];
}

function pixelArtVisible(color, alphaCutoff) {
  return Number(color?.[3] || 0) > alphaCutoff;
}

function pixelArtEdgeBetween(a, b, alphaCutoff, tolerance) {
  const aVisible = pixelArtVisible(a, alphaCutoff);
  const bVisible = pixelArtVisible(b, alphaCutoff);
  if (aVisible !== bVisible) return true;
  return aVisible && bVisible && colorDistance(a, b) > tolerance;
}

function collectPixelArtEdges(pixelData, axis, alphaCutoff, tolerance) {
  const edges = [];
  if (axis === "x") {
    const rowStep = Math.max(1, Math.floor(pixelData.height / 160));
    for (let y = 0; y < pixelData.height; y += rowStep) {
      for (let x = 1; x < pixelData.width; x++) {
        if (pixelArtEdgeBetween(
          pixelArtColorAt(pixelData, x - 1, y),
          pixelArtColorAt(pixelData, x, y),
          alphaCutoff,
          tolerance,
        )) {
          edges.push(x);
        }
      }
    }
  } else {
    const colStep = Math.max(1, Math.floor(pixelData.width / 160));
    for (let x = 0; x < pixelData.width; x += colStep) {
      for (let y = 1; y < pixelData.height; y++) {
        if (pixelArtEdgeBetween(
          pixelArtColorAt(pixelData, x, y - 1),
          pixelArtColorAt(pixelData, x, y),
          alphaCutoff,
          tolerance,
        )) {
          edges.push(y);
        }
      }
    }
  }
  return [...new Set(edges)].sort((a, b) => a - b);
}

function dominantPixelArtStep(edges, dimension) {
  if (!edges.length) return Math.max(1, Math.ceil(dimension / 256));
  const counts = new Map();
  for (let index = 1; index < edges.length; index++) {
    const diff = edges[index] - edges[index - 1];
    if (diff < 2 || diff > 96) continue;
    counts.set(diff, (counts.get(diff) || 0) + 1);
  }
  let bestStep = 1;
  let bestCount = 0;
  counts.forEach((count, step) => {
    if (count > bestCount || (count === bestCount && step > bestStep)) {
      bestStep = step;
      bestCount = count;
    }
  });
  if (bestCount < 4) return Math.max(1, Math.ceil(dimension / 256));
  return Math.max(1, bestStep);
}

function dominantPixelArtOffset(edges, step) {
  if (step <= 1 || !edges.length) return 0;
  const counts = new Map();
  edges.forEach((edge) => {
    const offset = ((edge % step) + step) % step;
    counts.set(offset, (counts.get(offset) || 0) + 1);
  });
  let bestOffset = 0;
  let bestCount = 0;
  counts.forEach((count, offset) => {
    if (count > bestCount || (count === bestCount && offset < bestOffset)) {
      bestOffset = offset;
      bestCount = count;
    }
  });
  return bestOffset;
}

function pixelArtIntervals(dimension, step, offset) {
  const effectiveStep = Math.max(1, step);
  const boundaries = new Set([0, dimension]);
  for (let position = offset; position < dimension; position += effectiveStep) {
    if (position > 0) boundaries.add(position);
  }
  const sorted = [...boundaries].sort((a, b) => a - b);
  const intervals = [];
  for (let index = 1; index < sorted.length; index++) {
    const start = sorted[index - 1];
    const end = sorted[index];
    if (end > start) intervals.push({ start, end, size: end - start });
  }
  return intervals;
}

function dominantPixelArtCell(pixelData, xInterval, yInterval, alphaCutoff, tolerance) {
  let visible = 0;
  const area = Math.max(1, xInterval.size * yInterval.size);
  const exact = new Map();
  for (let y = yInterval.start; y < yInterval.end; y++) {
    for (let x = xInterval.start; x < xInterval.end; x++) {
      const color = pixelArtColorAt(pixelData, x, y);
      if (!pixelArtVisible(color, alphaCutoff)) continue;
      visible++;
      const exactKey = `${color[0]}:${color[1]}:${color[2]}`;
      exact.set(exactKey, (exact.get(exactKey) || 0) + 1);
    }
  }
  if (!visible || visible / area < 0.55) return null;
  let bestColor = null;
  let bestCount = 0;
  exact.forEach((count, exactKey) => {
    const color = exactKey.split(":").map((value) => Number(value));
    if (count > bestCount) {
      bestCount = count;
      bestColor = color;
    }
  });
  if (!bestColor) return null;
  return [bestColor[0], bestColor[1], bestColor[2], 255];
}

function sampleDetectedPixelArtGrid(image, alphaCutoff, tolerance) {
  const pixelData = pixelArtImageData(image);
  const xEdges = collectPixelArtEdges(pixelData, "x", alphaCutoff, tolerance);
  const yEdges = collectPixelArtEdges(pixelData, "y", alphaCutoff, tolerance);
  let stepX = dominantPixelArtStep(xEdges, pixelData.width);
  let stepY = dominantPixelArtStep(yEdges, pixelData.height);
  if (stepX > 1 && stepY > 1 && Math.max(stepX, stepY) / Math.min(stepX, stepY) <= 1.35) {
    const sharedStep = Math.min(stepX, stepY);
    stepX = sharedStep;
    stepY = sharedStep;
  }
  const offsetX = dominantPixelArtOffset(xEdges, stepX);
  const offsetY = dominantPixelArtOffset(yEdges, stepY);
  const xIntervals = pixelArtIntervals(pixelData.width, stepX, offsetX);
  const yIntervals = pixelArtIntervals(pixelData.height, stepY, offsetY);
  const rows = yIntervals.map((yInterval) => (
    xIntervals.map((xInterval) => dominantPixelArtCell(pixelData, xInterval, yInterval, alphaCutoff, tolerance))
  ));
  return {
    rows,
    gridW: xIntervals.length,
    gridH: yIntervals.length,
    stepX,
    stepY,
    offsetX,
    offsetY,
  };
}

function pixelArtExactColorKey(color) {
  return `${Number(color?.[0] || 0)}:${Number(color?.[1] || 0)}:${Number(color?.[2] || 0)}:${Number(color?.[3] ?? 255)}`;
}

function buildPixelArtRuns(rows) {
  const rowRuns = rows.map((row, y) => {
    const runs = [];
    let x = 0;
    while (x < row.length) {
      const startColor = row[x];
      if (!startColor) {
        x++;
        continue;
      }
      const start = x;
      const runKey = pixelArtExactColorKey(startColor);
      x++;
      while (x < row.length && row[x] && pixelArtExactColorKey(row[x]) === runKey) x++;
      runs.push({
        x: start,
        y,
        width: x - start,
        height: 1,
        key: runKey,
        color: [...startColor],
      });
    }
    return runs;
  });
  const merged = [];
  let active = new Map();
  rowRuns.forEach((runs) => {
    const nextActive = new Map();
    runs.forEach((run) => {
      const mergeKey = `${run.x}:${run.width}:${run.key}`;
      const previous = active.get(mergeKey);
      if (previous && previous.y + previous.height === run.y) {
        previous.height += 1;
        nextActive.set(mergeKey, previous);
      } else {
        const copy = { ...run };
        merged.push(copy);
        nextActive.set(mergeKey, copy);
      }
    });
    active = nextActive;
  });
  return merged;
}

function pixelArtCanvasLayout(gridW, gridH, fitMode) {
  if (fitMode === "canvas") {
    return {
      left: FH6_BOUNDS.left,
      top: FH6_BOUNDS.top,
      cellW: FH6_BOUNDS.width / gridW,
      cellH: FH6_BOUNDS.height / gridH,
    };
  }
  const cellH = FH6_BOUNDS.height / gridH;
  const width = cellH * gridW;
  return {
    left: -width / 2,
    top: FH6_BOUNDS.top,
    cellW: cellH,
    cellH,
  };
}

function clearPreviousPixelArtLayers() {
  const previous = vinylObjects().filter((obj) => obj.kloudy?.pixel_art_generated);
  previous.forEach((obj) => canvas.remove(obj));
  return previous.length;
}

async function generatePixelArtRectangles() {
  try {
    if (!canvas) return;
    const alphaCutoff = numberInputValue("pixelArtAlphaCutoff", 128, 0, 255);
    const tolerance = numberInputValue("pixelArtTolerance", 24, 0, 80);
    setBusy("Detecting source pixel grid...");
    const image = await loadImageFromFile(pixelArtSourceFile);
    const detected = sampleDetectedPixelArtGrid(image, alphaCutoff, tolerance);
    const gridW = detected.gridW;
    const gridH = detected.gridH;
    setPixelArtGridInputs(detected);
    setBusy(`Detected ${gridW}x${gridH} source pixel grid. Building rectangles...`);
    const rows = detected.rows;
    const runs = buildPixelArtRuns(rows);
    if (!runs.length) {
      setText("pixelArtStatus", "No visible pixel-art cells found.");
      clearBusy("No visible pixel-art cells found.");
      return;
    }
    if (runs.length > 3000) {
      const ok = window.confirm(`This will create ${runs.length} layers. FH6 supports 3000 layers per vinyl. Continue anyway?`);
      if (!ok) {
        setText("pixelArtStatus", "Pixel-art generation cancelled.");
        clearBusy("Pixel-art generation cancelled.");
        return;
      }
    }
    const removed = $("pixelArtClearPrevious")?.checked ? clearPreviousPixelArtLayers() : 0;
    const layout = pixelArtCanvasLayout(gridW, gridH, "height");
    const groupId = `pixel-art-${Date.now().toString(36)}`;
    const groupName = `Pixel Art ${gridW}x${gridH}`;
    const typeCode = resourceToTypeCode("Primitives", 1);
    const shapeWord = resourceToShapeWord("Primitives", 1);
    const created = [];
    historyLocked = true;
    try {
      for (const run of runs) {
        const width = run.width * layout.cellW;
        const height = (run.height || 1) * layout.cellH;
        const centerX = layout.left + (run.x * layout.cellW) + width / 2;
        const centerY = layout.top + (run.y * layout.cellH) + height / 2;
        const shape = {
          type: typeCode,
          type_word: shapeWord,
          resource_family: "Primitives",
          resource_index: 1,
          shape_name: "Square",
          data: [
            round(centerX),
            round(-centerY),
            round(width / PIXEL_ART_SQUARE_SIZE),
            round(height / PIXEL_ART_SQUARE_SIZE),
            0,
            0,
            0,
          ],
          color: run.color,
          mask: false,
          score: 0,
          editor_group_id: groupId,
          editor_group_name: groupName,
        };
        const object = await makeFabricObject(shape);
        object.kloudy.pixel_art_generated = true;
        canvas.add(object);
        created.push(object);
      }
    } finally {
      historyLocked = false;
    }
    bringGuidesToBack();
    syncCanvasObjectCoords();
    selectObjects(created.slice(0, 200), "pixel-art generation");
    refreshLayers();
    pushHistory("generate pixel art");
    const message = `Generated ${created.length} pixel-art rectangle layer(s) from detected ${gridW}x${gridH} grid, source step ${detected.stepX}x${detected.stepY}px.${removed ? ` Removed ${removed} previous pixel-art layer(s).` : ""}`;
    setText("pixelArtStatus", message);
    clearBusy(message);
  } catch (err) {
    historyLocked = false;
    setText("pixelArtStatus", `Pixel-art generation failed: ${err.message || err}`);
    showError("Pixel-art generation failed", err);
  }
}

function textVinylFontString(fontFamily, fontSize, bold, italic) {
  const style = italic ? "italic" : "normal";
  const weight = bold ? "700" : "400";
  return `${style} ${weight} ${fontSize}px ${fontFamily || "sans-serif"}`;
}

function selectedTextVinylFontFamily() {
  const select = $("textVinylFontSelect");
  const custom = $("textVinylCustomFont");
  if (select?.value === "custom") return (custom?.value || "Segoe UI, Meiryo, sans-serif").trim();
  return (select?.value || "Segoe UI, Meiryo, sans-serif").trim();
}

function syncTextVinylFontUi() {
  const select = $("textVinylFontSelect");
  const custom = $("textVinylCustomFont");
  if (!select || !custom) return;
  custom.hidden = select.value !== "custom";
}

function loadTextVinylFontPreference() {
  const select = $("textVinylFontSelect");
  const custom = $("textVinylCustomFont");
  if (!select || !custom) return;
  const saved = localStorage.getItem(TEXT_VINYL_FONT_KEY);
  const savedCustom = localStorage.getItem(TEXT_VINYL_CUSTOM_FONT_KEY);
  if (savedCustom) custom.value = savedCustom;
  if (saved && [...select.options].some((option) => option.value === saved)) {
    select.value = saved;
  }
  syncTextVinylFontUi();
}

function saveTextVinylFontPreference() {
  const select = $("textVinylFontSelect");
  const custom = $("textVinylCustomFont");
  if (!select || !custom) return;
  localStorage.setItem(TEXT_VINYL_FONT_KEY, select.value);
  localStorage.setItem(TEXT_VINYL_CUSTOM_FONT_KEY, custom.value || "");
}

function renderTextVinylMask(text, options) {
  const lines = String(text || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .map((line) => line.length ? line : " ");
  const probe = document.createElement("canvas");
  const probeCtx = probe.getContext("2d", { willReadFrequently: true });
  probeCtx.font = textVinylFontString(options.fontFamily, options.fontSize, options.bold, options.italic);
  const lineHeight = Math.ceil(options.fontSize * 1.22);
  const padding = Math.max(8, Math.ceil(options.fontSize * 0.18));
  const width = Math.max(1, Math.ceil(Math.max(...lines.map((line) => probeCtx.measureText(line).width))));
  const height = Math.max(1, lineHeight * lines.length);
  const canvasEl = document.createElement("canvas");
  canvasEl.width = width + padding * 2;
  canvasEl.height = height + padding * 2;
  const ctx = canvasEl.getContext("2d", { willReadFrequently: true });
  ctx.clearRect(0, 0, canvasEl.width, canvasEl.height);
  ctx.font = textVinylFontString(options.fontFamily, options.fontSize, options.bold, options.italic);
  ctx.textBaseline = "top";
  ctx.textAlign = "left";
  ctx.fillStyle = "#ffffff";
  ctx.imageSmoothingEnabled = true;
  lines.forEach((line, index) => {
    ctx.fillText(line, padding, padding + index * lineHeight);
  });
  return canvasEl;
}

function textVinylCellsFromMask(mask, cellSize, alphaCutoff, coverageThreshold) {
  const width = Math.max(1, mask.width);
  const height = Math.max(1, mask.height);
  const gridW = Math.max(1, Math.ceil(width / cellSize));
  const gridH = Math.max(1, Math.ceil(height / cellSize));
  const ctx = mask.getContext("2d", { willReadFrequently: true });
  const data = ctx.getImageData(0, 0, width, height).data;
  const rows = [];
  for (let gy = 0; gy < gridH; gy++) {
    const row = [];
    const startY = gy * cellSize;
    const endY = Math.min(height, startY + cellSize);
    for (let gx = 0; gx < gridW; gx++) {
      const startX = gx * cellSize;
      const endX = Math.min(width, startX + cellSize);
      let total = 0;
      let filled = 0;
      for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
          total++;
          if (data[((y * width) + x) * 4 + 3] >= alphaCutoff) filled++;
        }
      }
      row.push(total > 0 && filled / total >= coverageThreshold);
    }
    rows.push(row);
  }
  return { rows, gridW, gridH };
}

function textVinylMaskImageData(mask) {
  const width = Math.max(1, mask.width);
  const height = Math.max(1, mask.height);
  const ctx = mask.getContext("2d", { willReadFrequently: true });
  return { width, height, data: ctx.getImageData(0, 0, width, height).data };
}

function textVinylAlphaCoverage(pixelData, startX, endX, startY, endY, alphaCutoff) {
  let total = 0;
  let filled = 0;
  for (let y = Math.max(0, startY); y < Math.min(pixelData.height, endY); y++) {
    for (let x = Math.max(0, startX); x < Math.min(pixelData.width, endX); x++) {
      total++;
      if (pixelData.data[((y * pixelData.width) + x) * 4 + 3] >= alphaCutoff) filled++;
    }
  }
  return total ? filled / total : 0;
}

function buildTextVinylCurveBands(mask, bandSize, alphaCutoff, coverageThreshold) {
  const pixelData = textVinylMaskImageData(mask);
  const runs = [];
  for (let y = 0; y < pixelData.height; y += bandSize) {
    const endY = Math.min(pixelData.height, y + bandSize);
    let x = 0;
    while (x < pixelData.width) {
      while (x < pixelData.width && textVinylAlphaCoverage(pixelData, x, x + 1, y, endY, alphaCutoff) < coverageThreshold) x++;
      if (x >= pixelData.width) break;
      const start = x;
      while (x < pixelData.width && textVinylAlphaCoverage(pixelData, x, x + 1, y, endY, alphaCutoff) >= coverageThreshold) x++;
      const width = x - start;
      if (width > 0) runs.push({ x: start, y, width, height: endY - y });
    }
  }
  return {
    runs,
    gridW: pixelData.width,
    gridH: pixelData.height,
  };
}

function buildTextVinylRects(rows) {
  const gridH = rows.length;
  const gridW = rows[0]?.length || 0;
  const visited = rows.map((row) => row.map(() => false));
  const rects = [];
  for (let y = 0; y < gridH; y++) {
    for (let x = 0; x < gridW; x++) {
      if (!rows[y][x] || visited[y][x]) continue;
      let width = 1;
      while (x + width < gridW && rows[y][x + width] && !visited[y][x + width]) width++;
      let height = 1;
      let canGrow = true;
      while (y + height < gridH && canGrow) {
        for (let dx = 0; dx < width; dx++) {
          if (!rows[y + height][x + dx] || visited[y + height][x + dx]) {
            canGrow = false;
            break;
          }
        }
        if (canGrow) height++;
      }
      for (let dy = 0; dy < height; dy++) {
        for (let dx = 0; dx < width; dx++) visited[y + dy][x + dx] = true;
      }
      rects.push({ x, y, width, height });
    }
  }
  return rects;
}

function textVinylLayout(gridW, gridH, targetHeight) {
  const center = viewportCenterPoint();
  const cellH = Math.max(0.1, targetHeight / Math.max(1, gridH));
  const cellW = cellH;
  const width = cellW * gridW;
  const height = cellH * gridH;
  return {
    left: center.x - width / 2,
    top: center.y - height / 2,
    cellW,
    cellH,
  };
}

function textVinylShapeFromBox(box, layout, resource, color, groupId, groupName, label) {
  const width = Math.max(0.01, box.width * layout.cellW);
  const height = Math.max(0.01, box.height * layout.cellH);
  const centerX = layout.left + (box.x * layout.cellW) + width / 2;
  const centerY = layout.top + (box.y * layout.cellH) + height / 2;
  const rotation = Number(box.rotation) || 0;
  const mesh = resource?.family && resource?.index ? textVinylMeshCache.get(`${resource.family}:${resource.index}`) : null;
  const naturalWidth = Math.max(0.001, mesh?.bounds?.width || PIXEL_ART_SQUARE_SIZE);
  const naturalHeight = Math.max(0.001, mesh?.bounds?.height || PIXEL_ART_SQUARE_SIZE);
  return {
    type: resource.typeCode,
    type_word: resource.shapeWord,
    resource_family: "Primitives",
    resource_index: resource.index,
    shape_name: label,
    data: [
      round(centerX),
      round(-centerY),
      round(width / naturalWidth),
      round(height / naturalHeight),
      round(-rotation),
      0,
      0,
    ],
    color,
    mask: false,
    score: 0,
    source_format: TEXT_VINYL_SOURCE_FLAG,
    editor_group_id: groupId,
    editor_group_name: groupName,
  };
}

function textVinylGridPoints(rows) {
  const points = [];
  const set = new Set();
  rows.forEach((row, y) => {
    row.forEach((filled, x) => {
      if (!filled) return;
      const key = `${x},${y}`;
      points.push({ x, y, key });
      set.add(key);
    });
  });
  return { points, set };
}

function textVinylPointKey(x, y) {
  return `${x},${y}`;
}

function textVinylGridGet(rows, x, y) {
  return y >= 0 && y < rows.length && x >= 0 && x < (rows[0]?.length || 0) && Boolean(rows[y][x]);
}

async function loadTextVinylResourceMesh(resource) {
  if (!resource?.family || !resource?.index) return null;
  const key = `${resource.family}:${resource.index}`;
  if (textVinylMeshCache.has(key)) return textVinylMeshCache.get(key);
  const url = await resolveVinylResourceUrl(resource.family, resource.index, "");
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Missing shape mesh resource: ${url}`);
  const payload = await response.json();
  const vertices = (payload.Vertices || []).map((vertex) => ({
    x: Number(vertex.X) || 0,
    y: Number(vertex.Y) || 0,
  }));
  const indices = payload.Indices || [];
  const triangles = [];
  for (let index = 0; index + 2 < indices.length; index += 3) {
    const a = vertices[indices[index]];
    const b = vertices[indices[index + 1]];
    const c = vertices[indices[index + 2]];
    if (a && b && c) triangles.push([a, b, c]);
  }
  const xs = vertices.map((vertex) => vertex.x);
  const ys = vertices.map((vertex) => vertex.y);
  const bounds = {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
  bounds.width = Math.max(0.001, bounds.maxX - bounds.minX);
  bounds.height = Math.max(0.001, bounds.maxY - bounds.minY);
  bounds.cx = (bounds.minX + bounds.maxX) / 2;
  bounds.cy = (bounds.minY + bounds.maxY) / 2;
  const mesh = { triangles, bounds };
  textVinylMeshCache.set(key, mesh);
  return mesh;
}

async function prepareTextVinylFitterMeshes(resources) {
  const unique = new Map();
  Object.values(resources || {}).forEach((resource) => {
    if (resource?.family && resource?.index) unique.set(`${resource.family}:${resource.index}`, resource);
  });
  await Promise.all([...unique.values()].map((resource) => loadTextVinylResourceMesh(resource)));
}

function textVinylPointInTriangle(px, py, a, b, c) {
  const d1 = (px - b.x) * (a.y - b.y) - (a.x - b.x) * (py - b.y);
  const d2 = (px - c.x) * (b.y - c.y) - (b.x - c.x) * (py - c.y);
  const d3 = (px - a.x) * (c.y - a.y) - (c.x - a.x) * (py - a.y);
  const hasNeg = d1 < -1e-6 || d2 < -1e-6 || d3 < -1e-6;
  const hasPos = d1 > 1e-6 || d2 > 1e-6 || d3 > 1e-6;
  return !(hasNeg && hasPos);
}

function textVinylMeshContains(mesh, meshX, meshY) {
  return Boolean(mesh?.triangles?.some(([a, b, c]) => textVinylPointInTriangle(meshX, meshY, a, b, c)));
}

function textVinylCandidateCellsFromMesh(candidate, gridW, gridH) {
  if (!candidate?.resource?.family || !candidate?.resource?.index) return null;
  const mesh = textVinylMeshCache.get(`${candidate.resource.family}:${candidate.resource.index}`);
  if (!mesh?.triangles?.length) return null;
  const angle = Number(candidate.rotation) || 0;
  const skew = Number(candidate.skew) || 0;
  const rad = angle * Math.PI / 180;
  const skewTan = Math.tan(skew * Math.PI / 180);
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const halfW = Math.max(0.01, Math.abs(candidate.width) / 2);
  const halfH = Math.max(0.01, Math.abs(candidate.height) / 2);
  const radius = Math.hypot(halfW + Math.abs(skewTan) * halfH, halfH) + 1;
  const minX = Math.max(0, Math.floor(candidate.cx - radius));
  const maxX = Math.min(gridW - 1, Math.ceil(candidate.cx + radius));
  const minY = Math.max(0, Math.floor(candidate.cy - radius));
  const maxY = Math.min(gridH - 1, Math.ceil(candidate.cy + radius));
  const cells = [];
  const { bounds } = mesh;
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const dx = (x + 0.5) - candidate.cx;
      const dy = (y + 0.5) - candidate.cy;
      let localX = dx * cos + dy * sin;
      const localY = -dx * sin + dy * cos;
      if (skewTan) localX -= skewTan * localY;
      if (Math.abs(localX) > halfW || Math.abs(localY) > halfH) continue;
      const meshX = bounds.cx + (localX / Math.max(0.001, Math.abs(candidate.width))) * bounds.width;
      const meshY = bounds.cy + (localY / Math.max(0.001, Math.abs(candidate.height))) * bounds.height;
      if (textVinylMeshContains(mesh, meshX, meshY)) cells.push({ x, y, key: textVinylPointKey(x, y) });
    }
  }
  return cells;
}

function textVinylCandidateCells(candidate, gridW, gridH) {
  const meshCells = textVinylCandidateCellsFromMesh(candidate, gridW, gridH);
  if (meshCells) return meshCells;
  const angle = Number(candidate.rotation) || 0;
  const rad = angle * Math.PI / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const halfW = Math.max(0.01, candidate.width / 2);
  const halfH = Math.max(0.01, candidate.height / 2);
  const radius = Math.hypot(halfW, halfH) + 1;
  const minX = Math.max(0, Math.floor(candidate.cx - radius));
  const maxX = Math.min(gridW - 1, Math.ceil(candidate.cx + radius));
  const minY = Math.max(0, Math.floor(candidate.cy - radius));
  const maxY = Math.min(gridH - 1, Math.ceil(candidate.cy + radius));
  const cells = [];
  for (let y = minY; y <= maxY; y++) {
    for (let x = minX; x <= maxX; x++) {
      const dx = (x + 0.5) - candidate.cx;
      const dy = (y + 0.5) - candidate.cy;
      const localX = dx * cos + dy * sin;
      const localY = -dx * sin + dy * cos;
      const nx = halfW ? localX / halfW : 0;
      const ny = halfH ? localY / halfH : 0;
      let inside = Math.abs(localX) <= halfW && Math.abs(localY) <= halfH;
      if (inside && candidate.shapeKind === "ellipse") {
        inside = (nx * nx) + (ny * ny) <= 1.0;
      } else if (inside && candidate.shapeKind === "quarterCircle") {
        inside = (nx * nx) + (ny * ny) <= 1.0 && nx >= -0.02 && ny >= -0.02;
      } else if (inside && candidate.shapeKind === "halfCircle") {
        inside = (nx * nx) + (ny * ny) <= 1.0 && nx >= -0.02;
      } else if (inside && candidate.shapeKind === "ellipseBorder") {
        const d = (nx * nx) + (ny * ny);
        const inner = Number(candidate.innerRatio) || 0.58;
        inside = d <= 1.0 && d >= inner * inner;
      } else if (inside && candidate.shapeKind === "rectBorder") {
        const inner = Number(candidate.innerRatio) || 0.58;
        inside = Math.abs(nx) <= 1.0 && Math.abs(ny) <= 1.0 && (Math.abs(nx) >= inner || Math.abs(ny) >= inner);
      } else if (inside && candidate.shapeKind === "roundedSquareBorder") {
        const corner = 0.52;
        const inner = Number(candidate.innerRatio) || 0.58;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        const outer = ax <= 1 && ay <= 1 && (
          ax <= corner || ay <= corner || ((ax - corner) ** 2 + (ay - corner) ** 2 <= (1 - corner) ** 2)
        );
        const innerCorner = corner * inner;
        const innerShape = ax <= inner && ay <= inner && (
          ax <= innerCorner || ay <= innerCorner || ((ax - innerCorner) ** 2 + (ay - innerCorner) ** 2 <= (inner - innerCorner) ** 2)
        );
        inside = outer && !innerShape;
      } else if (inside && candidate.shapeKind === "triangle") {
        inside = ny >= -1.0 && ny <= (1.0 - Math.abs(nx) * 2.0);
      } else if (inside && candidate.shapeKind === "triangleBorder") {
        const outer = ny >= -1.0 && ny <= (1.0 - Math.abs(nx) * 2.0);
        const innerScale = Number(candidate.innerRatio) || 0.56;
        const iny = ny / innerScale;
        const inx = nx / innerScale;
        const inner = iny >= -1.0 && iny <= (1.0 - Math.abs(inx) * 2.0);
        inside = outer && !inner;
      } else if (inside && candidate.shapeKind === "rightTriangle") {
        inside = nx >= -1.0 && ny >= -1.0 && nx + ny <= 0.05;
      } else if (inside && candidate.shapeKind === "rightTriangleBorder") {
        const outer = nx >= -1.0 && ny >= -1.0 && nx + ny <= 0.05;
        const innerScale = Number(candidate.innerRatio) || 0.56;
        const inx = (nx + 1) / innerScale - 1;
        const iny = (ny + 1) / innerScale - 1;
        const inner = inx >= -1.0 && iny >= -1.0 && inx + iny <= 0.05;
        inside = outer && !inner;
      } else if (inside && candidate.shapeKind === "halfCircleBorder") {
        const d = (nx * nx) + (ny * ny);
        const inner = Number(candidate.innerRatio) || 0.58;
        inside = d <= 1.0 && d >= inner * inner && nx >= -0.02;
      } else if (inside && candidate.shapeKind === "quarterDonut") {
        const d = (nx * nx) + (ny * ny);
        const inner = Number(candidate.innerRatio) || 0.58;
        inside = d <= 1.0 && d >= inner * inner && nx >= -0.02 && ny >= -0.02;
      } else if (inside && candidate.shapeKind === "taperedRect") {
        const halfWidthAtY = 1.0 - Math.max(0, ny + 1.0) * 0.18;
        inside = Math.abs(nx) <= Math.max(0.42, halfWidthAtY);
      } else if (inside && candidate.shapeKind === "pentagon") {
        const roof = 1.0 - Math.max(0, -ny - 0.15) * 1.15;
        inside = Math.abs(nx) <= Math.max(0.15, roof);
      } else if (inside && candidate.shapeKind === "roundedSquare") {
        const corner = 0.52;
        const ax = Math.abs(nx);
        const ay = Math.abs(ny);
        inside = ax <= 1 && ay <= 1 && (
          ax <= corner || ay <= corner || ((ax - corner) ** 2 + (ay - corner) ** 2 <= (1 - corner) ** 2)
        );
      }
      if (inside) {
        cells.push({ x, y, key: textVinylPointKey(x, y) });
      }
    }
  }
  return cells;
}

function scoreTextVinylCandidate(candidate, rows, remaining) {
  const gridH = rows.length;
  const gridW = rows[0]?.length || 0;
  const cells = textVinylCandidateCells(candidate, gridW, gridH);
  if (!cells.length) return null;
  let freshHits = 0;
  let oldHits = 0;
  let falseHits = 0;
  cells.forEach((cell) => {
    if (remaining.has(cell.key)) {
      freshHits++;
    } else if (textVinylGridGet(rows, cell.x, cell.y)) {
      oldHits++;
    } else {
      falseHits++;
    }
  });
  if (freshHits <= 0) return null;
  const falseRatio = falseHits / Math.max(1, cells.length);
  const coverageRatio = freshHits / Math.max(1, cells.length);
  const elongation = Math.max(candidate.width, candidate.height) / Math.max(1, Math.min(candidate.width, candidate.height));
  const score = freshHits * 5.0
    + Math.min(12, elongation) * 0.8
    - falseHits * 4.4
    - oldHits * 0.7
    - 2.0;
  return {
    ...candidate,
    cells,
    freshHits,
    falseHits,
    oldHits,
    falseRatio,
    coverageRatio,
    score,
  };
}

function textVinylCleanEnough(scored, maxFalsePerFresh = 0.10, maxFalseRatio = 0.14) {
  if (!scored) return false;
  if (scored.falseHits > Math.max(0, scored.freshHits * maxFalsePerFresh)) return false;
  if (scored.falseRatio > maxFalseRatio) return false;
  return true;
}

function textVinylCandidateFalseKeys(scored, rows) {
  const keys = new Set();
  (scored?.cells || []).forEach((cell) => {
    if (!textVinylGridGet(rows, cell.x, cell.y)) keys.add(cell.key);
  });
  return keys;
}

function textVinylUnionSize(a, b) {
  const union = new Set(a || []);
  (b || []).forEach((value) => union.add(value));
  return union.size;
}

function textVinylEstimatedFinishCost(rows, remaining, selectedCount, falseKeys) {
  const residualCount = buildTextVinylResidualRects(rows, remaining).length;
  return {
    residualCount,
    layers: selectedCount + residualCount,
    falseCount: falseKeys?.size || 0,
    cost: (selectedCount + residualCount) * 24 + (falseKeys?.size || 0) * 18,
  };
}

function textVinylStateSignature(state) {
  const remainingSample = [...state.remaining].sort().slice(0, 16).join("|");
  return `${state.selected.length}:${state.remaining.size}:${state.falseKeys.size}:${remainingSample}`;
}

function textVinylSelectBudgetedCandidates(rows, initialRemaining, candidateEntries, options = {}) {
  const maxSelected = Number(options.maxSelected) || 24;
  const beamWidth = Number(options.beamWidth) || 8;
  const candidateLimit = Number(options.candidateLimit) || 120;
  const baseline = textVinylEstimatedFinishCost(rows, initialRemaining, 0, new Set());
  let beam = [{
    selected: [],
    remaining: new Set(initialRemaining),
    falseKeys: new Set(),
    estimate: baseline,
  }];
  let best = beam[0];
  const candidates = candidateEntries.slice(0, candidateLimit);

  for (let depth = 0; depth < maxSelected; depth++) {
    const next = [];
    beam.forEach((state) => {
      candidates.forEach((entry) => {
        if (state.selected.some((selected) => selected.entry === entry)) return;
        const rescored = scoreTextVinylCandidate(entry.candidate, rows, state.remaining);
        if (!rescored || rescored.freshHits < 2) return;
        if (!textVinylCleanEnough(rescored, 0.04, 0.055)) return;
        if (rescored.falseHits > 1) return;
        const freshRatio = rescored.freshHits / Math.max(1, entry.scored?.freshHits || rescored.freshHits);
        if (freshRatio < 0.58) return;

        const remaining = new Set(state.remaining);
        rescored.cells.forEach((cell) => {
          if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
        });
        if (remaining.size >= state.remaining.size) return;

        const falseKeys = new Set(state.falseKeys);
        textVinylCandidateFalseKeys(rescored, rows).forEach((key) => falseKeys.add(key));
        const estimate = textVinylEstimatedFinishCost(rows, remaining, state.selected.length + 1, falseKeys);
        const previousEstimate = textVinylEstimatedFinishCost(rows, state.remaining, state.selected.length, state.falseKeys);
        const localGain = previousEstimate.cost - estimate.cost;
        if (localGain < 4) return;

        next.push({
          selected: [...state.selected, { entry, scored: rescored }],
          remaining,
          falseKeys,
          estimate,
        });
      });
    });
    if (!next.length) break;
    const deduped = new Map();
    next.forEach((state) => {
      const key = textVinylStateSignature(state);
      const existing = deduped.get(key);
      if (!existing || state.estimate.cost < existing.estimate.cost) deduped.set(key, state);
    });
    beam = [...deduped.values()]
      .sort((a, b) => a.estimate.cost - b.estimate.cost)
      .slice(0, beamWidth);
    if (beam[0] && beam[0].estimate.cost < best.estimate.cost) best = beam[0];
  }

  if (best.estimate.layers >= baseline.layers && best.estimate.falseCount > 0) {
    return { selected: [], remaining: new Set(initialRemaining), falseKeys: new Set(), baseline, estimate: baseline };
  }
  if (best.estimate.layers > baseline.layers) {
    return { selected: [], remaining: new Set(initialRemaining), falseKeys: new Set(), baseline, estimate: baseline };
  }
  return { ...best, baseline };
}

function textVinylRunsForAngle(points, remaining, angle, bandWidth, minFresh) {
  const rad = angle * Math.PI / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const bins = new Map();
  points.forEach((point) => {
    if (!remaining.has(point.key)) return;
    const px = point.x + 0.5;
    const py = point.y + 0.5;
    const u = px * cos + py * sin;
    const v = -px * sin + py * cos;
    const bin = Math.round(v / bandWidth);
    if (!bins.has(bin)) bins.set(bin, []);
    bins.get(bin).push({ ...point, u, v });
  });
  const candidates = [];
  bins.forEach((rows) => {
    rows.sort((a, b) => a.u - b.u);
    let run = [];
    rows.forEach((point) => {
      if (!run.length || point.u - run[run.length - 1].u <= 1.75) {
        run.push(point);
      } else {
        if (run.length >= minFresh) candidates.push(run);
        run = [point];
      }
    });
    if (run.length >= minFresh) candidates.push(run);
  });
  return candidates.map((run) => {
    const uValues = run.map((point) => point.u);
    const vValues = run.map((point) => point.v);
    const uMin = Math.min(...uValues) - 0.5;
    const uMax = Math.max(...uValues) + 0.5;
    const vMid = (Math.min(...vValues) + Math.max(...vValues)) / 2;
    const uMid = (uMin + uMax) / 2;
    return {
      kind: "stroke",
      cx: uMid * cos - vMid * sin,
      cy: uMid * sin + vMid * cos,
      width: Math.max(1, uMax - uMin),
      height: Math.max(1, bandWidth),
      rotation: angle,
    };
  });
}

function buildTextVinylResidualRects(rows, remaining) {
  const residualRows = rows.map((row, y) => row.map((_filled, x) => remaining.has(textVinylPointKey(x, y))));
  return buildTextVinylRects(residualRows);
}

function textVinylConnectedComponents(rows, remaining) {
  const seen = new Set();
  const components = [];
  const neighborOffsets = [
    [-1, -1], [0, -1], [1, -1],
    [-1, 0], [1, 0],
    [-1, 1], [0, 1], [1, 1],
  ];
  remaining.forEach((startKey) => {
    if (seen.has(startKey)) return;
    const [startX, startY] = startKey.split(",").map((value) => Number(value));
    if (!Number.isFinite(startX) || !Number.isFinite(startY)) return;
    const queue = [{ x: startX, y: startY, key: startKey }];
    const cells = [];
    seen.add(startKey);
    for (let index = 0; index < queue.length; index++) {
      const point = queue[index];
      cells.push(point);
      neighborOffsets.forEach(([dx, dy]) => {
        const x = point.x + dx;
        const y = point.y + dy;
        const key = textVinylPointKey(x, y);
        if (seen.has(key) || !remaining.has(key) || !textVinylGridGet(rows, x, y)) return;
        seen.add(key);
        queue.push({ x, y, key });
      });
    }
    if (cells.length) components.push(cells);
  });
  return components;
}

function textVinylComponentBounds(component) {
  const xs = component.map((cell) => cell.x);
  const ys = component.map((cell) => cell.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return {
    x: minX,
    y: minY,
    width: maxX - minX + 1,
    height: maxY - minY + 1,
  };
}

function textVinylComponentHoles(component, rect) {
  const componentKeys = new Set(component.map((cell) => cell.key));
  const seen = new Set();
  const holes = [];
  const keyFor = (x, y) => textVinylPointKey(x, y);
  const emptyInside = (x, y) => x >= rect.x
    && x < rect.x + rect.width
    && y >= rect.y
    && y < rect.y + rect.height
    && !componentKeys.has(keyFor(x, y));
  const flood = (startX, startY) => {
    const startKey = keyFor(startX, startY);
    if (seen.has(startKey) || !emptyInside(startX, startY)) return [];
    const queue = [{ x: startX, y: startY, key: startKey }];
    const cells = [];
    seen.add(startKey);
    for (let index = 0; index < queue.length; index++) {
      const point = queue[index];
      cells.push(point);
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dx, dy]) => {
        const x = point.x + dx;
        const y = point.y + dy;
        const key = keyFor(x, y);
        if (seen.has(key) || !emptyInside(x, y)) return;
        seen.add(key);
        queue.push({ x, y, key });
      });
    }
    return cells;
  };
  for (let x = rect.x; x < rect.x + rect.width; x++) {
    flood(x, rect.y);
    flood(x, rect.y + rect.height - 1);
  }
  for (let y = rect.y; y < rect.y + rect.height; y++) {
    flood(rect.x, y);
    flood(rect.x + rect.width - 1, y);
  }
  for (let y = rect.y; y < rect.y + rect.height; y++) {
    for (let x = rect.x; x < rect.x + rect.width; x++) {
      const cells = flood(x, y);
      if (cells.length >= 3) holes.push(cells);
    }
  }
  return holes.map((hole) => textVinylComponentBounds(hole));
}

function textVinylLoopCandidateRects(componentRect, holes) {
  if (!holes.length) return [];
  if (holes.length === 1) return [componentRect];
  return holes.map((hole) => {
    const pad = Math.max(2, Math.round(Math.min(hole.width, hole.height) * 0.55));
    const x = Math.max(componentRect.x, hole.x - pad);
    const y = Math.max(componentRect.y, hole.y - pad);
    const maxX = Math.min(componentRect.x + componentRect.width, hole.x + hole.width + pad);
    const maxY = Math.min(componentRect.y + componentRect.height, hole.y + hole.height + pad);
    return {
      x,
      y,
      width: Math.max(2, maxX - x),
      height: Math.max(2, maxY - y),
    };
  });
}

function textVinylPrimitiveResource(index) {
  return {
    family: "Primitives",
    index,
    typeCode: resourceToTypeCode("Primitives", index),
    shapeWord: resourceToShapeWord("Primitives", index),
  };
}

function textVinylShapeCandidateFromBox(box, resource, shapeKind = "rect") {
  return {
    ...box,
    cx: box.x + box.width / 2,
    cy: box.y + box.height / 2,
    shapeKind,
    resource,
  };
}

function textVinylFitterResourceSet() {
  return {
    square: textVinylPrimitiveResource(1),
    circle: textVinylPrimitiveResource(2),
    triangle: textVinylPrimitiveResource(3),
    rightTriangle: textVinylPrimitiveResource(4),
    roundedSquare: textVinylPrimitiveResource(7),
    halfCircle: textVinylPrimitiveResource(9),
    squareBorder: textVinylPrimitiveResource(11),
    circleBorder: textVinylPrimitiveResource(12),
    triangleBorder: textVinylPrimitiveResource(13),
    rightTriangleBorder: textVinylPrimitiveResource(14),
    roundedSquareBorder: textVinylPrimitiveResource(17),
    halfCircleBorder: textVinylPrimitiveResource(19),
    taperedRect: textVinylPrimitiveResource(20),
    quarterDonut: textVinylPrimitiveResource(29),
    quarterCircle: textVinylPrimitiveResource(30),
    circleHalfBorder: textVinylPrimitiveResource(32),
    pentagon: textVinylPrimitiveResource(35),
  };
}

function textVinylShapeOptionsForRect(rect, rows, remaining, options = {}) {
  const resources = textVinylFitterResourceSet();
  const aspect = Math.max(rect.width, rect.height) / Math.max(1, Math.min(rect.width, rect.height));
  const base = textVinylShapeCandidateFromBox(rect, resources.square, "rect");
  const baseScore = scoreTextVinylCandidate(base, rows, remaining);
  if (!baseScore) return [];
  const candidates = [{
    candidate: base,
    resource: resources.square,
    label: "Square",
    kind: "rect",
    score: baseScore.score,
    scored: baseScore,
  }];
  if (rect.width >= 2 && rect.height >= 2 && aspect <= 2.2) {
    [
      { resource: resources.circle, label: aspect <= 1.25 ? "Circle" : "Circle", kind: "ellipse", minFreshRatio: 0.64, maxFalse: 0.10, bonus: 7 },
      { resource: resources.roundedSquare, label: "Rounded Square", kind: "roundedSquare", minFreshRatio: 0.78, maxFalse: 0.08, bonus: 4 },
      { resource: resources.pentagon, label: "Pentagon", kind: "pentagon", minFreshRatio: 0.68, maxFalse: 0.08, bonus: 3 },
    ].forEach((option) => {
      const candidate = textVinylShapeCandidateFromBox(rect, option.resource, option.kind);
      const scored = scoreTextVinylCandidate(candidate, rows, remaining);
      if (!scored) return;
      if (scored.falseRatio > option.maxFalse) return;
      if (!textVinylCleanEnough(scored, 0.10, option.maxFalse)) return;
      if (scored.freshHits < baseScore.freshHits * option.minFreshRatio) return;
      candidates.push({ ...option, candidate, score: scored.score + option.bonus, scored });
    });
  }
  if (rect.width >= 2 && rect.height >= 2) {
    [
      { resource: resources.triangle, label: "Triangle", kind: "triangle", rotations: [0, 90, 180, 270], minFreshRatio: 0.48, maxFalse: 0.08, bonus: 6 },
      { resource: resources.rightTriangle, label: "Right Triangle", kind: "rightTriangle", rotations: [0, 90, 180, 270], minFreshRatio: 0.46, maxFalse: 0.08, bonus: 7 },
      { resource: resources.halfCircle, label: "Half Circle", kind: "halfCircle", rotations: [0, 90, 180, 270], minFreshRatio: 0.50, maxFalse: 0.10, bonus: 6 },
      { resource: resources.taperedRect, label: "Tapered Rectangle", kind: "taperedRect", rotations: [0, 180], minFreshRatio: 0.58, maxFalse: 0.08, bonus: 4 },
    ].forEach((option) => {
      option.rotations.forEach((rotation) => {
        const candidate = textVinylShapeCandidateFromBox({ ...rect, rotation }, option.resource, option.kind);
        const scored = scoreTextVinylCandidate(candidate, rows, remaining);
        if (!scored) return;
        if (scored.falseRatio > option.maxFalse) return;
        if (!textVinylCleanEnough(scored, 0.10, option.maxFalse)) return;
        if (scored.freshHits < baseScore.freshHits * option.minFreshRatio) return;
        candidates.push({ ...option, candidate, score: scored.score + option.bonus, scored });
      });
    });
  }
  if (options.includeSmallCorners && rect.width >= 2 && rect.height >= 2 && aspect <= 1.6) {
    [0, 90, 180, 270].forEach((rotation) => {
      const candidate = textVinylShapeCandidateFromBox({ ...rect, rotation }, resources.quarterCircle, "quarterCircle");
      const scored = scoreTextVinylCandidate(candidate, rows, remaining);
      if (!scored || !textVinylCleanEnough(scored, 0.08, 0.10) || scored.freshHits < Math.max(2, baseScore.freshHits * 0.42)) return;
      candidates.push({
        candidate,
        resource: resources.quarterCircle,
        label: "Quarter Circle",
        kind: "quarterCircle",
        score: scored.score + 8,
        scored,
      });
    });
  }
  return candidates.sort((a, b) => b.score - a.score);
}

function textVinylChooseResidualShape(rect, rows, remaining) {
  const square = textVinylPrimitiveResource(1);
  const candidate = textVinylShapeCandidateFromBox(rect, square, "rect");
  return { candidate, resource: square, label: "Square", score: 0 };
}

function textVinylConvexCornerCandidates(rows, remaining) {
  const quarter = textVinylFitterResourceSet().quarterCircle;
  const candidates = [];
  rows.forEach((row, y) => {
    row.forEach((filled, x) => {
      if (!filled || !remaining.has(textVinylPointKey(x, y))) return;
      const up = textVinylGridGet(rows, x, y - 1);
      const down = textVinylGridGet(rows, x, y + 1);
      const left = textVinylGridGet(rows, x - 1, y);
      const right = textVinylGridGet(rows, x + 1, y);
      [
        { ok: !up && !left, rotation: 180, x, y },
        { ok: !up && !right, rotation: 270, x: x - 1, y },
        { ok: !down && !left, rotation: 90, x, y: y - 1 },
        { ok: !down && !right, rotation: 0, x: x - 1, y: y - 1 },
      ].forEach((corner) => {
        if (!corner.ok) return;
        const candidate = textVinylShapeCandidateFromBox({
          x: corner.x,
          y: corner.y,
          width: 2,
          height: 2,
          rotation: corner.rotation,
        }, quarter, "quarterCircle");
        const scored = scoreTextVinylCandidate(candidate, rows, remaining);
        if (!scored) return;
        if (scored.freshHits < 1 || !textVinylCleanEnough(scored, 0.08, 0.12)) return;
        candidates.push(scored);
      });
    });
  });
  return candidates.sort((a, b) => b.score - a.score);
}

function textVinylBroadShapeCandidates(rows, remaining) {
  const residualRects = buildTextVinylResidualRects(rows, remaining)
    .filter((rect) => rect.width >= 2 && rect.height >= 2)
    .slice(0, 220);
  const candidates = [];
  residualRects.forEach((rect) => {
    textVinylShapeOptionsForRect(rect, rows, remaining, { includeSmallCorners: true }).forEach((candidate) => {
      if (candidate.kind === "rect") return;
      if (!candidate.scored || candidate.scored.freshHits < 3) return;
      candidates.push(candidate);
    });
  });
  return candidates.sort((a, b) => b.score - a.score);
}

function textVinylExpandedBox(rect, pad, gridW, gridH) {
  const x = Math.max(0, rect.x - pad);
  const y = Math.max(0, rect.y - pad);
  const maxX = Math.min(gridW, rect.x + rect.width + pad);
  const maxY = Math.min(gridH, rect.y + rect.height + pad);
  return {
    x,
    y,
    width: Math.max(1, maxX - x),
    height: Math.max(1, maxY - y),
  };
}

function textVinylEarlyNonSquareCandidates(rows, remaining) {
  const gridH = rows.length;
  const gridW = rows[0]?.length || 0;
  const safeEarlyLabels = new Set([
    "Circle",
    "Rounded Square",
    "Half Circle",
    "Tapered Rectangle",
    "Quarter Circle",
    "Circle Border",
    "Rounded Square Border",
    "Half Circle Border",
    "Quarter Donut",
  ]);
  const residualRects = buildTextVinylResidualRects(rows, remaining)
    .filter((rect) => rect.width * rect.height >= 2)
    .sort((a, b) => (b.width * b.height) - (a.width * a.height))
    .slice(0, 260);
  const candidates = [];
  const seen = new Set();
  residualRects.forEach((rect) => {
    [0, 1, 2, 3].forEach((pad) => {
      let box = textVinylExpandedBox(rect, pad, gridW, gridH);
      if (box.width < 2 && box.height >= 2) box = textVinylExpandedBox({ ...rect, x: rect.x - 1, width: rect.width + 2 }, pad, gridW, gridH);
      if (box.height < 2 && box.width >= 2) box = textVinylExpandedBox({ ...rect, y: rect.y - 1, height: rect.height + 2 }, pad, gridW, gridH);
      if (box.width < 2 || box.height < 2) return;
      textVinylShapeOptionsForRect(box, rows, remaining, { includeSmallCorners: true }).forEach((candidate) => {
        if (candidate.kind === "rect") return;
        if (!safeEarlyLabels.has(candidate.label)) return;
        if (!candidate.scored || candidate.scored.freshHits < 2) return;
        if (!textVinylCleanEnough(candidate.scored, 0.08, 0.10)) return;
        const key = [
          candidate.label,
          candidate.kind,
          Math.round(candidate.candidate.cx * 2),
          Math.round(candidate.candidate.cy * 2),
          Math.round(candidate.candidate.width * 2),
          Math.round(candidate.candidate.height * 2),
          Math.round(candidate.candidate.rotation || 0),
        ].join(":");
        if (seen.has(key)) return;
        seen.add(key);
        candidates.push(candidate);
      });
    });
  });
  return candidates.sort((a, b) => b.score - a.score);
}

function textVinylComponentShapeCandidates(rows, remaining) {
  const resources = textVinylFitterResourceSet();
  const candidates = [];
  textVinylConnectedComponents(rows, remaining)
    .filter((component) => component.length >= 8)
    .forEach((component) => {
      const rect = textVinylComponentBounds(component);
      if (rect.width < 3 || rect.height < 3) return;
      const componentArea = rect.width * rect.height;
      const density = component.length / Math.max(1, componentArea);
      const aspect = Math.max(rect.width, rect.height) / Math.max(1, Math.min(rect.width, rect.height));
      const holes = textVinylComponentHoles(component, rect);
      const loopRects = textVinylLoopCandidateRects(rect, holes);
      const baseOptions = [];
      const addOption = (box, resource, label, kind, rotations = [0], extra = {}) => {
        rotations.forEach((rotation) => {
          baseOptions.push({ box, resource, label, kind, rotation, ...extra });
        });
      };
      if (density <= 0.68 && rect.width >= 5 && rect.height >= 5) {
        const boxes = loopRects.length ? loopRects : [rect];
        boxes.forEach((box) => [0.52, 0.60, 0.68].forEach((innerRatio) => {
          addOption(box, resources.circleBorder, "Circle Border", "ellipseBorder", [0], { innerRatio, bonus: aspect <= 1.8 ? 18 : 10 });
          addOption(box, resources.roundedSquareBorder, "Rounded Square Border", "roundedSquareBorder", [0], { innerRatio, bonus: 12 });
          addOption(box, resources.squareBorder, "Square Border", "rectBorder", [0], { innerRatio, bonus: 9 });
        }));
        boxes.forEach((box) => {
          [0, 90, 180, 270].forEach((rotation) => {
            addOption(box, resources.halfCircleBorder, "Half Circle Border", "halfCircleBorder", [rotation], { innerRatio: 0.58, bonus: 8 });
            addOption(box, resources.quarterDonut, "Quarter Donut", "quarterDonut", [rotation], { innerRatio: 0.58, bonus: 8 });
          });
        });
      }
      if ((componentArea <= 72 || density >= 0.72) && aspect <= 1.65) {
        addOption(rect, resources.circle, "Circle", "ellipse", [0], { bonus: 8 });
        addOption(rect, resources.roundedSquare, "Rounded Square", "roundedSquare", [0], { bonus: 6 });
      }
      baseOptions.forEach((option) => {
        const candidate = textVinylShapeCandidateFromBox({ ...option.box, rotation: option.rotation }, option.resource, option.kind);
        candidate.innerRatio = option.innerRatio;
        const scored = scoreTextVinylCandidate(candidate, rows, remaining);
        if (!scored) return;
        const componentCoverage = scored.freshHits / Math.max(1, component.length);
        const minCoverage = option.kind.includes("Border") || option.kind === "quarterDonut" ? 0.24 : 0.42;
        const maxFalse = option.kind.includes("Border") || option.kind === "quarterDonut" ? 0.12 : 0.08;
        if (componentCoverage < minCoverage || !textVinylCleanEnough(scored, 0.10, maxFalse)) return;
        candidates.push({
          candidate,
          resource: option.resource,
          label: option.label,
          kind: option.kind,
          componentCoverage,
          score: scored.score + (option.bonus || 0) + componentCoverage * 24,
          scored,
        });
      });
    });
  return candidates.sort((a, b) => b.score - a.score);
}

function buildTextVinylSmartFitShapes(rows, layout, color, groupId, groupName) {
  const { points, set } = textVinylGridPoints(rows);
  const remaining = new Set(set);
  const resources = textVinylFitterResourceSet();
  const square = resources.square;
  const quarter = resources.quarterCircle;
  const gridH = rows.length;
  const gridW = rows[0]?.length || 0;
  const shapes = [];
  let componentShapeCount = 0;
  const componentTypeCounts = new Map();
  const componentSelection = textVinylSelectBudgetedCandidates(rows, remaining, textVinylComponentShapeCandidates(rows, remaining), {
    maxSelected: 10,
    beamWidth: 8,
    candidateLimit: 90,
  });
  for (const selected of componentSelection.selected) {
    if (componentShapeCount >= 10 || remaining.size <= 0) break;
    const candidate = selected.entry;
    const rescored = scoreTextVinylCandidate(candidate.candidate, rows, remaining);
    if (!rescored) continue;
    shapes.push(textVinylShapeFromBox({
      x: rescored.cx - rescored.width / 2,
      y: rescored.cy - rescored.height / 2,
      width: rescored.width,
      height: rescored.height,
      rotation: rescored.rotation,
    }, layout, candidate.resource, color, groupId, groupName, candidate.label));
    rescored.cells.forEach((cell) => {
      if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
    });
    componentShapeCount++;
    componentTypeCounts.set(candidate.label, (componentTypeCounts.get(candidate.label) || 0) + 1);
  }

  let earlyShapeCount = 0;
  const earlyTypeCounts = new Map();
  const earlySelection = textVinylSelectBudgetedCandidates(rows, remaining, [], {
    maxSelected: 24,
    beamWidth: 10,
    candidateLimit: 150,
  });
  for (const selected of earlySelection.selected) {
    if (remaining.size <= 0) break;
    const candidate = selected.entry;
    const rescored = scoreTextVinylCandidate(candidate.candidate, rows, remaining);
    if (!rescored) continue;
    shapes.push(textVinylShapeFromBox({
      x: rescored.cx - rescored.width / 2,
      y: rescored.cy - rescored.height / 2,
      width: rescored.width,
      height: rescored.height,
      rotation: rescored.rotation,
    }, layout, candidate.resource, color, groupId, groupName, candidate.label));
    rescored.cells.forEach((cell) => {
      if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
    });
    earlyShapeCount++;
    earlyTypeCounts.set(candidate.label, (earlyTypeCounts.get(candidate.label) || 0) + 1);
  }

  let strokeCount = 0;
  const candidateRules = [
    { angles: [0, 90, 45, 135], bandSizes: [1.4, 2.2, 3.2, 4.4], minFresh: 10, maxFalse: 0.10 },
    { angles: [30, 60, 120, 150], bandSizes: [2.2, 3.2, 4.4], minFresh: 14, maxFalse: 0.08 },
  ];
  const candidates = [];
  candidateRules.forEach((rule) => {
    rule.angles.forEach((angle) => {
      rule.bandSizes.forEach((bandWidth) => {
        textVinylRunsForAngle(points, set, angle, bandWidth, rule.minFresh).forEach((candidate) => {
          const scored = scoreTextVinylCandidate(candidate, rows, set);
          if (!scored) return;
          if (scored.falseRatio > rule.maxFalse) return;
          if (scored.freshHits < rule.minFresh) return;
          candidates.push({ ...scored, rule });
        });
      });
    });
  });
  candidates.sort((a, b) => b.score - a.score);
  const strokeEntries = candidates.slice(0, 900).map((candidate) => ({
    candidate: {
      cx: candidate.cx,
      cy: candidate.cy,
      width: candidate.width,
      height: candidate.height,
      rotation: candidate.rotation,
      shapeKind: "rect",
      resource: square,
    },
    resource: square,
    label: "Square",
    kind: "stroke",
    scored: candidate,
    score: candidate.score,
  }));
  const strokeSelection = textVinylSelectBudgetedCandidates(rows, remaining, strokeEntries, {
    maxSelected: Math.min(80, Math.max(10, Math.floor(points.length / 9))),
    beamWidth: 12,
    candidateLimit: 260,
  });
  for (const selected of strokeSelection.selected) {
    if (remaining.size <= 0) break;
    const candidate = selected.entry;
    const best = scoreTextVinylCandidate(candidate.candidate, rows, remaining);
    if (!best) continue;
    shapes.push(textVinylShapeFromBox({
      x: best.cx - best.width / 2,
      y: best.cy - best.height / 2,
      width: best.width,
      height: best.height,
      rotation: best.rotation,
    }, layout, square, color, groupId, groupName, "Square"));
    best.cells.forEach((cell) => {
      if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
    });
    strokeCount++;
  }

  let cornerCount = 0;
  const cornerEntries = textVinylConvexCornerCandidates(rows, remaining).slice(0, 100).map((corner) => ({
    candidate: {
      cx: corner.cx,
      cy: corner.cy,
      width: corner.width,
      height: corner.height,
      rotation: corner.rotation,
      shapeKind: "quarterCircle",
      resource: quarter,
    },
    resource: quarter,
    label: "Quarter Circle",
    kind: "corner",
    scored: corner,
    score: corner.score,
  }));
  const cornerSelection = textVinylSelectBudgetedCandidates(rows, remaining, cornerEntries, {
    maxSelected: 32,
    beamWidth: 8,
    candidateLimit: 90,
  });
  for (const selected of cornerSelection.selected) {
    if (cornerCount >= 32) break;
    const corner = selected.entry;
    const rescored = scoreTextVinylCandidate(corner.candidate, rows, remaining);
    if (!rescored) continue;
    shapes.push(textVinylShapeFromBox({
      x: rescored.cx - rescored.width / 2,
      y: rescored.cy - rescored.height / 2,
      width: rescored.width,
      height: rescored.height,
      rotation: rescored.rotation,
    }, layout, quarter, color, groupId, groupName, "Quarter Circle"));
    rescored.cells.forEach((cell) => {
      if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
    });
    cornerCount++;
  }

  let broadShapeCount = 0;
  const broadTypeCounts = new Map();
  for (const candidate of textVinylBroadShapeCandidates(rows, remaining).slice(0, 0)) {
    if (broadShapeCount >= 90) break;
    const rescored = scoreTextVinylCandidate(candidate.candidate || candidate, rows, remaining);
    if (!rescored || rescored.freshHits < 3 || !textVinylCleanEnough(rescored, 0.08, 0.10) || rescored.score < 2) continue;
    shapes.push(textVinylShapeFromBox({
      x: rescored.cx - rescored.width / 2,
      y: rescored.cy - rescored.height / 2,
      width: rescored.width,
      height: rescored.height,
      rotation: rescored.rotation,
    }, layout, candidate.resource, color, groupId, groupName, candidate.label));
    rescored.cells.forEach((cell) => {
      if (textVinylGridGet(rows, cell.x, cell.y)) remaining.delete(cell.key);
    });
    broadShapeCount++;
    broadTypeCounts.set(candidate.label, (broadTypeCounts.get(candidate.label) || 0) + 1);
  }

  const residualRects = buildTextVinylResidualRects(rows, remaining);
  const residualTypeCounts = new Map();
  residualRects.forEach((rect) => {
    const chosen = textVinylChooseResidualShape(rect, rows, remaining);
    shapes.push(textVinylShapeFromBox(chosen.candidate || rect, layout, chosen.resource, color, groupId, groupName, chosen.label));
    residualTypeCounts.set(chosen.label, (residualTypeCounts.get(chosen.label) || 0) + 1);
  });
  const typeSummary = [...componentTypeCounts, ...earlyTypeCounts, ...broadTypeCounts, ...residualTypeCounts]
    .reduce((map, [label, count]) => {
      map.set(label, (map.get(label) || 0) + count);
      return map;
    }, new Map());
  return {
    shapes,
    componentShapeCount,
    earlyShapeCount,
    strokeCount,
    cornerCount,
    broadShapeCount,
    residualCount: residualRects.length,
    typeSummary: [...typeSummary.entries()].sort((a, b) => b[1] - a[1]),
    gridW,
    gridH,
  };
}

function textVinylForzaGlyphResource(char, fontNumber) {
  const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const lower = "abcdefghijklmnopqrstuvwxyz";
  const symbolMap = {
    "%": 27,
    ":": 28,
    ";": 29,
    "/": 30,
    "$": 31,
    "£": 32,
    "¥": 33,
    "€": 34,
    "æ": 35,
    "Æ": 35,
    "^": 36,
    "ß": 37,
    "@": 38,
    "#": 39,
    "+": 40,
  };
  const safeFont = Math.max(1, Math.min(11, Number(fontNumber) || 1));
  const upperIndex = upper.indexOf(char);
  if (upperIndex >= 0) return { family: `Upper_Letters_${safeFont}`, index: upperIndex + 1 };
  const lowerIndex = lower.indexOf(char);
  if (lowerIndex >= 0) return { family: `Lower_Letters_${safeFont}`, index: lowerIndex + 1 };
  if (symbolMap[char]) return { family: `Lower_Letters_${safeFont}`, index: symbolMap[char] };
  return null;
}

function textVinylForzaLineWidth(line, fontNumber, advance) {
  let width = 0;
  for (const char of line) {
    if (char === " ") {
      width += advance * 0.58;
      continue;
    }
    width += textVinylForzaGlyphResource(char, fontNumber) ? advance : advance * 0.5;
  }
  return width;
}

function buildTextVinylForzaLetterShapes(text, options, color, groupId, groupName) {
  const fontNumber = numberInputValue("textVinylForzaFont", 1, 1, 11);
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const center = viewportCenterPoint();
  const lineHeight = options.targetHeight / Math.max(1, lines.length);
  const glyphHeight = lineHeight * 0.82;
  const scale = glyphHeight / PIXEL_ART_SQUARE_SIZE;
  const advance = glyphHeight * 0.72;
  const lineGap = lineHeight * 0.18;
  const totalHeight = lines.length * lineHeight - lineGap;
  const shapes = [];
  let unsupported = 0;
  lines.forEach((line, lineIndex) => {
    const lineWidth = textVinylForzaLineWidth(line, fontNumber, advance);
    let cursor = center.x - lineWidth / 2;
    const y = center.y - totalHeight / 2 + lineIndex * lineHeight + glyphHeight / 2;
    for (const char of line) {
      if (char === " ") {
        cursor += advance * 0.58;
        continue;
      }
      const resource = textVinylForzaGlyphResource(char, fontNumber);
      const charAdvance = resource ? advance : advance * 0.5;
      if (!resource) {
        unsupported++;
        cursor += charAdvance;
        continue;
      }
      const typeCode = resourceToTypeCode(resource.family, resource.index);
      const shapeWord = resourceToShapeWord(resource.family, resource.index);
      shapes.push({
        type: typeCode,
        type_word: shapeWord,
        resource_family: resource.family,
        resource_index: resource.index,
        shape_name: shapeDisplayName(resource.family, resource.index),
        data: [
          round(cursor + charAdvance / 2),
          round(-y),
          round(scale),
          round(scale),
          0,
          0,
          0,
        ],
        color,
        mask: false,
        score: 0,
        source_format: TEXT_VINYL_SOURCE_FLAG,
        editor_group_id: groupId,
        editor_group_name: groupName,
      });
      cursor += charAdvance;
    }
  });
  return { shapes, unsupported, fontNumber };
}

function buildTextVinylCurveShapes(runs, layout, color, groupId, groupName) {
  const square = {
    index: 1,
    typeCode: resourceToTypeCode("Primitives", 1),
    shapeWord: resourceToShapeWord("Primitives", 1),
  };
  const circle = {
    index: 2,
    typeCode: resourceToTypeCode("Primitives", 2),
    shapeWord: resourceToShapeWord("Primitives", 2),
  };
  const shapes = [];
  runs.forEach((run) => {
    const capWidth = Math.min(run.height, run.width / 2);
    if (run.width <= run.height * 1.15) {
      shapes.push(textVinylShapeFromBox(run, layout, circle, color, groupId, groupName, "Circle"));
      return;
    }
    const centerWidth = Math.max(0, run.width - capWidth * 2);
    if (centerWidth > 0.05) {
      shapes.push(textVinylShapeFromBox({
        x: run.x + capWidth,
        y: run.y,
        width: centerWidth,
        height: run.height,
      }, layout, square, color, groupId, groupName, "Square"));
    }
    shapes.push(textVinylShapeFromBox({
      x: run.x,
      y: run.y,
      width: capWidth * 2,
      height: run.height,
    }, layout, circle, color, groupId, groupName, "Circle"));
    shapes.push(textVinylShapeFromBox({
      x: run.x + run.width - capWidth * 2,
      y: run.y,
      width: capWidth * 2,
      height: run.height,
    }, layout, circle, color, groupId, groupName, "Circle"));
  });
  return shapes;
}

function clearPreviousTextVinylLayers() {
  const previous = vinylObjects().filter((obj) => obj.kloudy?.source_format === TEXT_VINYL_SOURCE_FLAG);
  previous.forEach((obj) => canvas.remove(obj));
  return previous.length;
}

async function generateTextVinylShapes() {
  try {
    if (!canvas) return;
    const text = $("textVinylInput")?.value || "";
    if (!text.trim()) {
      setTextVinylStatus("Type some text first.");
      return;
    }
    const options = {
      fontFamily: selectedTextVinylFontFamily(),
      mode: "forzaLetters",
      fontSize: numberInputValue("textVinylFontSize", 96, 12, 360),
      cellSize: numberInputValue("textVinylCellSize", 4, 1, 48),
      bandSize: numberInputValue("textVinylBandSize", 4, 1, 36),
      targetHeight: numberInputValue("textVinylHeight", 360, 20, 2000),
      alphaCutoff: numberInputValue("textVinylAlphaCutoff", 96, 0, 255),
      coverage: numberInputValue("textVinylCoverage", 18, 5, 95) / 100,
      bold: Boolean($("textVinylBold")?.checked),
      italic: Boolean($("textVinylItalic")?.checked),
    };
    setBusy("Rasterizing text...");
    await nextFrame();
    const mask = renderTextVinylMask(text, options);
    const color = normalizeColor(currentPanelColor());
    rememberColor(color);
    let shapeSpecs = [];
    let sourceWidth = 1;
    let sourceHeight = 1;
    let sourceLabel = "";
    const groupId = `text-vinyl-${Date.now().toString(36)}`;
    const groupName = `Text Vinyl ${text.trim().slice(0, 28) || "Text"}`;
    if (options.mode === "forzaLetters") {
      const built = buildTextVinylForzaLetterShapes(text, options, color, groupId, groupName);
      shapeSpecs = built.shapes;
      sourceWidth = shapeSpecs.length;
      sourceHeight = 1;
      sourceLabel = `Forza Font ${built.fontNumber}, ${shapeSpecs.length} glyph(s)${built.unsupported ? `, ${built.unsupported} unsupported character(s) skipped` : ""}`;
    } else if (options.mode === "curveBands") {
      const bands = buildTextVinylCurveBands(mask, options.bandSize, options.alphaCutoff, options.coverage);
      sourceWidth = bands.gridW;
      sourceHeight = bands.gridH;
      const layout = textVinylLayout(sourceWidth, sourceHeight, options.targetHeight);
      shapeSpecs = buildTextVinylCurveShapes(bands.runs, layout, color, groupId, groupName);
      sourceLabel = `${bands.runs.length} scanline run(s)`;
    } else if (options.mode === "smartFit") {
      const grid = textVinylCellsFromMask(mask, options.cellSize, options.alphaCutoff, options.coverage);
      const layout = textVinylLayout(grid.gridW, grid.gridH, options.targetHeight);
      await prepareTextVinylFitterMeshes(textVinylFitterResourceSet());
      const fitted = buildTextVinylSmartFitShapes(grid.rows, layout, color, groupId, groupName);
      shapeSpecs = fitted.shapes;
      sourceWidth = fitted.gridW;
      sourceHeight = fitted.gridH;
      const types = fitted.typeSummary.length
        ? ` (${fitted.typeSummary.map(([name, count]) => `${count} ${name}`).join(", ")})`
        : "";
      sourceLabel = `${fitted.componentShapeCount} component shape(s) + ${fitted.earlyShapeCount} early shape(s) + ${fitted.strokeCount} fitted stroke(s) + ${fitted.cornerCount} curve corner(s) + ${fitted.broadShapeCount} scored shape(s) + ${fitted.residualCount} residual shape(s)${types}`;
    } else {
      const grid = textVinylCellsFromMask(mask, options.cellSize, options.alphaCutoff, options.coverage);
      const rects = buildTextVinylRects(grid.rows);
      sourceWidth = grid.gridW;
      sourceHeight = grid.gridH;
      const layout = textVinylLayout(grid.gridW, grid.gridH, options.targetHeight);
      const square = {
        index: 1,
        typeCode: resourceToTypeCode("Primitives", 1),
        shapeWord: resourceToShapeWord("Primitives", 1),
      };
      shapeSpecs = rects.map((rect) => textVinylShapeFromBox(rect, layout, square, color, groupId, groupName, "Square"));
      sourceLabel = `${grid.gridW}x${grid.gridH} cells`;
    }
    if (!shapeSpecs.length) {
      setTextVinylStatus("No supported Forza letter shapes found for this text.");
      clearBusy("No supported Forza letter shapes found.");
      return;
    }
    if (shapeSpecs.length > 3000) {
      const ok = window.confirm(`This text needs ${shapeSpecs.length} layers. FH6 supports 3000 layers per vinyl. Increase Cell/Band px or continue anyway?`);
      if (!ok) {
        setTextVinylStatus("Text vinyl generation cancelled.");
        clearBusy("Text vinyl generation cancelled.");
        return;
      }
    }
    setBusy(`Building ${shapeSpecs.length} text vinyl layer(s)...`);
    const removed = $("textVinylClearPrevious")?.checked ? clearPreviousTextVinylLayers() : 0;
    const created = [];
    historyLocked = true;
    try {
      for (const shape of shapeSpecs) {
        const object = await makeFabricObject(shape);
        object.kloudy.source_format = TEXT_VINYL_SOURCE_FLAG;
        canvas.add(object);
        created.push(object);
      }
    } finally {
      historyLocked = false;
    }
    bringGuidesToBack();
    syncCanvasObjectCoords();
    selectObjects(created.slice(0, 200), "text vinyl generation");
    refreshLayers();
    pushHistory("generate text vinyl");
    const message = `Generated ${created.length} text layer(s) from ${sourceLabel}, source ${sourceWidth}x${sourceHeight}.${removed ? ` Removed ${removed} previous text layer(s).` : ""}`;
    setTextVinylStatus(message);
    clearBusy(message);
  } catch (err) {
    historyLocked = false;
    setTextVinylStatus(`Text vinyl generation failed: ${err.message || err}`);
    showError("Text vinyl generation failed", err);
  }
}

function buildShapeLibrary() {
  const select = $("shapeFamily");
  FAMILY_ORDER.forEach((family) => {
    const option = document.createElement("option");
    option.value = family;
    option.textContent = family.replaceAll("_", " ");
    select.appendChild(option);
  });
  select.value = "Primitives";
  select.addEventListener("change", renderShapeGrid);
  $("shapeSearch").addEventListener("input", renderShapeGrid);
  loadShapeNames();
  renderShapeGrid();
}

function renderShapeGrid() {
  const selectedFamily = $("shapeFamily").value;
  const query = $("shapeSearch").value.trim().toLowerCase();
  const grid = $("shapeGrid");
  grid.innerHTML = "";
  const families = (query || showFavoritesOnly) ? FAMILY_ORDER : [selectedFamily];
  for (const family of families) for (let index = 1; index <= shapeCountForFamily(family); index++) {
    const typeCode = resourceToTypeCode(family, index);
    const shapeWord = resourceToShapeWord(family, index);
    const favKey = `${family}:${index}`;
    const isFavorite = favorites.has(favKey);
    if (showFavoritesOnly && !isFavorite) continue;
    const name = shapeDisplayName(family, index);
    if (query && !shapeSearchText(family, index, typeCode).includes(query)) continue;
    const tile = document.createElement("div");
    tile.className = `shapeTile${isFavorite ? " favorite" : ""}`;
    tile.tabIndex = 0;
    tile.title = `${name}\n${family.replaceAll("_", " ")} #${index}\nType ${typeCode} / word ${shapeWord}`;
    tile.innerHTML = `
      <button class="favButton" type="button" title="${isFavorite ? "Remove favorite" : "Add favorite"}">${isFavorite ? "x" : "+"}</button>
      <img alt="" src="${vinylResourceUrl(family, index, ".png")}">
      <span class="shapeName">${escapeHtml(name)}</span>
      <span class="shapeMeta">${family.replaceAll("_", " ")} #${index}</span>
      <span class="shapeWord">word ${shapeWord}</span>
    `;
    tile.addEventListener("click", () => addShape(family, index).catch((err) => showError("Shape add failed", err)));
    tile.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        addShape(family, index).catch((err) => showError("Shape add failed", err));
      }
    });
    tile.querySelector(".favButton").addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFavorite(family, index);
    });
    const img = tile.querySelector("img");
    img.addEventListener("error", async () => {
      const fallback = await resolveVinylResourceUrl(family, index, ".png");
      if (img.getAttribute("src") === fallback) {
        img.classList.add("missingThumb");
        img.removeAttribute("src");
      } else {
        img.src = fallback;
      }
    }, { once: true });
    grid.appendChild(tile);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toggleFavorite(family, index) {
  const key = `${family}:${index}`;
  if (favorites.has(key)) favorites.delete(key);
  else favorites.add(key);
  localStorage.setItem("kloudyFabricFavorites", JSON.stringify([...favorites]));
  renderShapeGrid();
}

async function duplicateSelected() {
  const selected = selectedVinylObjects();
  const selectedSet = new Set(selected);
  const orderedSelection = orderedSelectedVinylObjects();
  const objects = unlockedObjects(orderedSelection);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus("Selected layers are locked. Unlock them before duplicating.");
    return;
  }
  if (objects.length !== selected.length) {
    setStatus(`Duplicating ${objects.length} unlocked layer(s). Skipped ${selected.length - objects.length} locked layer(s).`);
  }
  const editableSet = new Set(objects);
  const duplicateGroupMap = new Map();
  const duplicateGroupNameMap = new Map();
  objects.forEach((obj) => {
    const groupId = obj.kloudy?.group_id;
    if (!groupId || duplicateGroupMap.has(groupId)) return;
    const members = membersForGroupIds([groupId]);
    const completeGroupSelection = members.length > 1 && members.every((member) => editableSet.has(member));
    if (completeGroupSelection) {
      duplicateGroupMap.set(groupId, `group-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`);
      duplicateGroupNameMap.set(groupId, nextLayerGroupName());
    } else {
      duplicateGroupMap.set(groupId, null);
      duplicateGroupNameMap.set(groupId, null);
    }
  });
  try {
    const clones = [];
    for (const obj of objects) {
      const shape = objectToShape(obj, { includeEditorMeta: true });
      shape.data = Array.isArray(shape.data) ? shape.data.slice() : [];
      shape.data[0] = round((Number(shape.data[0]) || 0) + 30);
      shape.data[1] = round((Number(shape.data[1]) || 0) - 30);
      if (shape.editor_group_id) {
        const newGroupId = duplicateGroupMap.get(shape.editor_group_id);
        shape.editor_group_id = newGroupId;
        shape.editor_group_name = newGroupId ? duplicateGroupNameMap.get(obj.kloudy.group_id) : null;
      }
      shape.editor_locked = false;
      const clone = await makeFabricObject(shape);
      if (obj.__kloudySelectionOutline) clone.set({ shadow: obj.__kloudySelectionOutline.shadow || null });
      delete clone.__kloudySelectionOutline;
      applyMaskVisual(clone);
      clone.perPixelTargetFind = $("boxVisibleOnly")?.checked || $("pixelSelect")?.checked || false;
      clone.targetFindTolerance = clone.perPixelTargetFind ? VINYL_HIT_TOLERANCE : 0;
      clone.hoverCursor = "pointer";
      clone.moveCursor = "move";
      styleObjectTransformControls(clone);
      clones.push(clone);
    }
    const mode = shapePlacementMode();
    const placement = insertDuplicateVinylObjects(clones, objects, mode);
    if (clones.length === 1) {
      canvas.setActiveObject(clones[0]);
    } else {
      canvas.setActiveObject(styledActiveSelection(clones));
    }
    bringGuidesToBack();
    syncCanvasObjectCoords();
    refreshLayers();
    canvas.requestRenderAll();
    pushHistory(placement === "top" ? "duplicate" : `duplicate ${placement}`);
    const placementText = placement === "top" ? "at top" : `${placement} selected layer(s)`;
    setStatus(`Duplicated ${clones.length} layer(s) ${placementText}.${objects.length !== selectedSet.size ? ` Skipped ${selectedSet.size - objects.length} locked layer(s).` : ""}`);
  } catch (err) {
    showError("Duplicate failed", err);
    setStatus(`Duplicate failed: ${err.message || err}`);
  }
}

function deleteSelected() {
  const selected = selectedVinylObjects();
  if (!selected.length && selectedGuideId) {
    deleteSelectedGuide();
    return;
  }
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus("Selected layers are locked. Unlock them before deleting.");
    return;
  }
  objects.forEach((obj) => canvas.remove(obj));
  syncMaskPreviewOutlines();
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("delete");
  setStatus(`Deleted ${objects.length} layer(s).${objects.length !== selected.length ? ` Skipped ${selected.length - objects.length} locked layer(s).` : ""}`);
}

function moveSelected(direction) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus("Selected layers are locked. Unlock them before changing layer order.");
    return;
  }
  const moved = moveLayerBlock(objects, direction);
  if (!moved) {
    setStatus(`Selected layer(s) are already at the ${direction > 0 ? "front" : "back"} of the vinyl stack.`);
    return;
  }
  refreshLayers();
  pushHistory("layer order");
  setStatus(`Moved ${objects.length} unlocked layer(s) ${direction > 0 ? "forward" : "backward"}.${objects.length !== selected.length ? ` Skipped ${selected.length - objects.length} locked layer(s).` : ""}`);
}

function setVinylStackOrder(order) {
  if (!canvas) return;
  const currentObjects = canvas.getObjects();
  const currentVinyl = vinylObjects();
  const currentVinylSet = new Set(currentVinyl);
  const nextVinyl = [];
  const seen = new Set();
  order.forEach((obj) => {
    if (!currentVinylSet.has(obj) || seen.has(obj)) return;
    seen.add(obj);
    nextVinyl.push(obj);
  });
  currentVinyl.forEach((obj) => {
    if (seen.has(obj)) return;
    seen.add(obj);
    nextVinyl.push(obj);
  });
  if (nextVinyl.length !== currentVinyl.length) return;
  const restoreSelection = selectedVinylObjects().filter((obj) => currentVinylSet.has(obj));
  const nonVinyl = currentObjects.filter((obj) => !currentVinylSet.has(obj));
  if (restoreSelection.length) canvas.discardActiveObject();
  canvas._objects = nonVinyl.concat(nextVinyl);
  nextVinyl.forEach((obj) => {
    obj.canvas = canvas;
    obj.setCoords?.();
  });
  layerEditorHelpers();
  if (restoreSelection.length === 1) canvas.setActiveObject(restoreSelection[0]);
  else if (restoreSelection.length > 1) canvas.setActiveObject(styledActiveSelection(restoreSelection));
  canvas.requestRenderAll();
}

function moveLayerBlock(objects, direction) {
  const selectedSet = new Set(objects);
  const order = vinylObjects();
  if (!order.some((obj) => selectedSet.has(obj))) return false;
  let moved = false;
  if (direction > 0) {
    for (let index = order.length - 2; index >= 0; index--) {
      if (selectedSet.has(order[index]) && !selectedSet.has(order[index + 1])) {
        [order[index], order[index + 1]] = [order[index + 1], order[index]];
        moved = true;
      }
    }
  } else {
    for (let index = 1; index < order.length; index++) {
      if (selectedSet.has(order[index]) && !selectedSet.has(order[index - 1])) {
        [order[index - 1], order[index]] = [order[index], order[index - 1]];
        moved = true;
      }
    }
  }
  if (moved) setVinylStackOrder(order);
  return moved;
}

function flipSelected(axis) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus("Selected layers are locked. Unlock them before flipping.");
    return;
  }
  const active = canvas.getActiveObject();
  if (isActiveSelectionObject(active)) canvas.discardActiveObject();
  const bounds = objects.length > 1 ? selectionBoundsForObjects(objects) : null;
  const reflection = bounds ? reflectMatrixForBounds(bounds, axis) : null;
  objects.forEach((obj) => {
    if (reflection) {
      const matrix = fabric.util.multiplyTransformMatrices(reflection, obj.calcTransformMatrix());
      fabric.util.applyTransformToObject(obj, matrix);
    } else if (axis === "x") obj.set("flipX", !obj.flipX);
    else obj.set("flipY", !obj.flipY);
    updateObjectScaleSigns(obj);
    obj.setCoords();
  });
  if (objects.length === 1) canvas.setActiveObject(objects[0]);
  else canvas.setActiveObject(styledActiveSelection(objects));
  requestCanvasRender();
  updateSelectionPanel();
  scheduleRefreshLayers();
  pushHistory(axis === "x" ? "flip horizontal" : "flip vertical");
  setStatus(`Flipped ${objects.length} layer(s) ${axis === "x" ? "horizontally" : "vertically"}.${objects.length !== selected.length ? ` Skipped ${selected.length - objects.length} locked layer(s).` : ""}`);
}

function selectObjects(objects, reason) {
  const normalized = [...new Set(objects.map(interactiveVinylTarget).filter((obj) => obj?.kloudy && !obj.kloudyGuide))];
  if (!normalized.length) {
    setStatus(`No layers found for ${reason}.`);
    return;
  }
  const active = canvas.getActiveObject();
  if (isActiveSelectionObject(active)) canvas.discardActiveObject();
  normalized.forEach((obj) => obj.setCoords());
  if (normalized.length === 1) canvas.setActiveObject(normalized[0]);
  else canvas.setActiveObject(styledActiveSelection(normalized));
  canvas.requestRenderAll();
  updateSelectionPanel();
  updateLayerSelectionStyles();
  setStatus(`Selected ${normalized.length} layer(s) by ${reason}.`);
}

function nextLayerGroupName() {
  const names = new Set(vinylObjects().map((obj) => obj.kloudy?.group_name).filter(Boolean));
  for (let i = 1; i < 10000; i++) {
    const name = `Group ${i}`;
    if (!names.has(name)) return name;
  }
  return `Group ${Date.now().toString(36)}`;
}

function groupSelectedLayers() {
  const selected = selectedVinylObjects();
  if (selected.length < 2) {
    setStatus("Select two or more layers before creating a group.");
    return;
  }
  const groupId = `group-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const groupName = nextLayerGroupName();
  selected.forEach((obj) => {
    obj.kloudy.group_id = groupId;
    obj.kloudy.group_name = groupName;
  });
  collapsedLayerGroups.delete(groupId);
  refreshLayers();
  updateSelectionPanel();
  pushHistory("group layers");
  setStatus(`${groupName}: grouped ${selected.length} layer(s). Export remains flat.`);
}

function renameSelectedGroup() {
  const groupIds = selectedGroupIds();
  if (!groupIds.length) {
    setStatus("Select a grouped layer before renaming a group.");
    return;
  }
  if (groupIds.length > 1) {
    setStatus("Select one editor group before renaming.");
    return;
  }
  const members = membersForGroupIds(groupIds);
  if (!members.length) {
    setStatus("Selected group has no editable layers.");
    return;
  }
  const currentName = groupNameForObject(members[0]);
  const nextName = window.prompt("Rename editor group", currentName);
  if (nextName === null) return;
  const cleaned = nextName.trim().slice(0, 64) || currentName;
  members.forEach((obj) => {
    obj.kloudy.group_name = cleaned;
  });
  refreshLayers();
  updateSelectionPanel();
  pushHistory("rename group");
  setStatus(`Renamed editor group to ${cleaned}. Export remains flat.`);
}

function ungroupSelectedLayers() {
  const selected = selectedVinylObjects();
  const groupIds = selectedGroupIds();
  const targets = groupIds.length ? membersForGroupIds(groupIds) : selected.filter((obj) => obj.kloudy?.group_id);
  if (!targets.length) {
    setStatus("Select a grouped layer before ungrouping.");
    return;
  }
  targets.forEach((obj) => {
    if (obj.kloudy.group_id) collapsedLayerGroups.delete(obj.kloudy.group_id);
    obj.kloudy.group_id = null;
    obj.kloudy.group_name = null;
  });
  refreshLayers();
  updateSelectionPanel();
  pushHistory("ungroup layers");
  setStatus(`Removed editor grouping from ${targets.length} layer(s).`);
}

function toggleSelectedGroupVisibility() {
  const targets = selectedGroupMembers();
  if (!targets.length) {
    setStatus("Select a grouped layer before hiding/showing a group.");
    return;
  }
  const shouldHide = targets.some((obj) => obj.visible !== false);
  targets.forEach((obj) => {
    obj.visible = !shouldHide;
  });
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory(shouldHide ? "hide group" : "show group");
  setStatus(`${shouldHide ? "Hid" : "Showed"} ${targets.length} layer(s) in selected group.`);
}

function toggleSelectedGroupLock() {
  const targets = selectedGroupMembers();
  if (!targets.length) {
    setStatus("Select a grouped layer before locking/unlocking a group.");
    return;
  }
  const shouldLock = targets.some((obj) => !obj.kloudy?.locked);
  targets.forEach((obj) => setObjectLocked(obj, shouldLock));
  canvas.requestRenderAll();
  refreshLayers();
  updateSelectionPanel();
  pushHistory(shouldLock ? "lock group" : "unlock group");
  setStatus(`${shouldLock ? "Locked" : "Unlocked"} ${targets.length} layer(s) in selected group.`);
}

function nudgeSelected(dx, dy) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus("Selected layers are locked. Unlock them before nudging.");
    return;
  }
  objects.forEach((obj) => {
    obj.set({ left: (obj.left || 0) + dx, top: (obj.top || 0) + dy });
    obj.setCoords();
  });
  applyLiveOverlayColor();
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("nudge");
  if (objects.length !== selected.length) setStatus(`Nudged ${objects.length} unlocked layer(s). Skipped ${selected.length - objects.length} locked layer(s).`);
}

function setPixelSelection(enabled) {
  if ($("pixelSelect")) $("pixelSelect").checked = enabled;
  if ($("boxVisibleOnly")) $("boxVisibleOnly").checked = enabled;
  canvas.perPixelTargetFind = enabled;
  canvas.targetFindTolerance = enabled ? VINYL_HIT_TOLERANCE : 0;
  vinylObjects().forEach((obj) => {
    if (obj.kloudy?.mask) {
      obj.perPixelTargetFind = false;
      obj.targetFindTolerance = 12;
      return;
    }
    obj.perPixelTargetFind = enabled;
    obj.targetFindTolerance = enabled ? VINYL_HIT_TOLERANCE : 0;
  });
}

function rebuildOverlaySampler(img) {
  const width = img.naturalWidth || img.width || 1;
  const height = img.naturalHeight || img.height || 1;
  const sampleCanvas = document.createElement("canvas");
  sampleCanvas.width = width;
  sampleCanvas.height = height;
  const ctx = sampleCanvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, width, height);
  overlaySampler = {
    width,
    height,
    data: ctx.getImageData(0, 0, width, height).data,
  };
}

function sourceOverlayProjectState() {
  if (!overlayImage || !overlaySourceState) return null;
  const source = {
    version: 1,
    kind: overlaySourceState.kind || "image",
    file_name: overlaySourceState.fileName || "source-overlay",
    mime_type: overlaySourceState.mimeType || null,
    data_url: overlaySourceState.dataUrl || null,
    svg_text: overlaySourceState.svgText || null,
    intrinsic_width: overlaySampler?.width || overlayImage.width || null,
    intrinsic_height: overlaySampler?.height || overlayImage.height || null,
    object_width: overlayImage.width || null,
    object_height: overlayImage.height || null,
    rendered_width: overlayImage.getScaledWidth?.() || null,
    rendered_height: overlayImage.getScaledHeight?.() || null,
    transform: {
      left: round(overlayImage.left || 0),
      top: round(overlayImage.top || 0),
      scaleX: Number(overlayImage.scaleX) || 1,
      scaleY: Number(overlayImage.scaleY) || 1,
      angle: Number(overlayImage.angle) || 0,
      skewX: Number(overlayImage.skewX) || 0,
      skewY: Number(overlayImage.skewY) || 0,
      flipX: Boolean(overlayImage.flipX),
      flipY: Boolean(overlayImage.flipY),
      opacity: Number(overlayImage.opacity ?? 1),
      visible: overlayImage.visible !== false,
    },
    controls: {
      scale_percent: Number($("overlayScalePercent")?.value || $("overlayScale")?.value || 100),
      opacity_percent: Number($("overlayOpacity")?.value || Math.round((overlayImage.opacity ?? 1) * 100)),
      layer_mode: overlayLayerMode,
    },
  };
  if (layeredOverlayState) {
    source.layered_svg = {
      selected_index: Number(layeredOverlayState.selectedIndex) || 0,
      view_mode: String(layeredOverlayState.viewMode || "original"),
      width: Number(layeredOverlayState.width) || null,
      height: Number(layeredOverlayState.height) || null,
      layers: Array.isArray(layeredOverlayState.layers) ? layeredOverlayState.layers.map((layer) => ({ ...layer })) : [],
    };
  }
  return source;
}

function clearSourceOverlayState() {
  if (overlayImage && canvas?.getObjects().includes(overlayImage)) canvas.remove(overlayImage);
  overlayImage = null;
  overlaySampler = null;
  overlaySourceState = null;
  clearLayeredOverlayState();
  updateSourceInteractivity();
}

async function restoreSourceOverlayFromProject(state) {
  if (!state) {
    clearSourceOverlayState();
    return;
  }
  const fileName = String(state.file_name || "source-overlay");
  if (state.kind === "layered_svg" && state.svg_text) {
    layeredOverlayState = parseLayeredSvg(String(state.svg_text), fileName);
    const layered = state.layered_svg || {};
    layeredOverlayState.selectedIndex = Math.max(0, Math.min(
      Number(layered.selected_index) || 0,
      Math.max(0, layeredOverlayState.layers.length - 1)
    ));
    layeredOverlayState.viewMode = String(layered.view_mode || "original");
    const url = layeredSvgDataUrl();
    if (!url) throw new Error("Saved layered SVG overlay could not be rendered.");
    await loadOverlayImageFromUrl(url, fileName, { mimeType: state.mime_type || "image/svg+xml", projectState: state });
    return;
  }
  if (!state.data_url) {
    clearSourceOverlayState();
    return;
  }
  clearLayeredOverlayState();
  await loadOverlayImageFromUrl(String(state.data_url), fileName, { mimeType: state.mime_type || null, projectState: state });
}

function applyOverlayProjectTransform(state) {
  if (!overlayImage || !state?.transform) return;
  const transform = state.transform;
  overlayImage.set({
    left: Number(transform.left) || 0,
    top: Number(transform.top) || 0,
    scaleX: Number(transform.scaleX) || 1,
    scaleY: Number(transform.scaleY) || 1,
    angle: Number(transform.angle) || 0,
    skewX: Number(transform.skewX) || 0,
    skewY: Number(transform.skewY) || 0,
    flipX: Boolean(transform.flipX),
    flipY: Boolean(transform.flipY),
    opacity: Number.isFinite(Number(transform.opacity)) ? Number(transform.opacity) : 1,
    visible: transform.visible !== false,
  });
  overlayImage.setCoords();
}

function clearLayeredOverlayState() {
  layeredOverlayState = null;
  setHidden("layeredOverlayControls", true);
  const select = $("overlaySvgLayerSelect");
  if (select) select.innerHTML = "";
  setText("overlaySvgLayerInfo", "Load a layered SVG to flip through its reference, guide, and color layers.");
}

function svgLayerLabel(group) {
  return (
    group.getAttribute("inkscape:label") ||
    group.getAttributeNS?.("http://www.inkscape.org/namespaces/inkscape", "label") ||
    group.getAttribute("label") ||
    group.id ||
    "Layer"
  );
}

function styleHasDisplayNone(style) {
  return /(^|;)\s*display\s*:\s*none\s*(;|$)/i.test(String(style || ""));
}

function setSvgElementVisible(element, visible) {
  let style = element.getAttribute("style") || "";
  style = style.replace(/(^|;)\s*display\s*:\s*none\s*;?/ig, ";").replace(/^;+|;+$/g, "").trim();
  if (!visible) style = `${style ? `${style};` : ""}display:none`;
  if (style) element.setAttribute("style", style);
  else element.removeAttribute("style");
  if (visible) element.removeAttribute("display");
  else element.setAttribute("display", "none");
}

function parseLayeredSvg(text, fileName = "overlay.svg") {
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, "image/svg+xml");
  if (doc.querySelector("parsererror")) throw new Error("SVG parser rejected the file.");
  const svg = doc.documentElement;
  const groups = Array.from(svg.querySelectorAll("g")).filter((group) => {
    const label = svgLayerLabel(group);
    return group.id || label;
  });
  const layers = groups.map((group, index) => {
    const label = svgLayerLabel(group);
    const id = group.id || `svg_layer_${index}`;
    const labelLower = label.toLowerCase();
    const idLower = id.toLowerCase();
    const hidden = group.getAttribute("display") === "none" || styleHasDisplayNone(group.getAttribute("style"));
    const kind = idLower.includes("reference") || labelLower.includes("reference")
      ? "reference"
      : idLower.includes("grid") || labelLower.includes("grid")
        ? "grid"
        : idLower.includes("line") || labelLower.includes("line_art") || labelLower.includes("edge")
          ? "edge"
          : idLower.includes("canvas") || labelLower.includes("canvas")
            ? "canvas"
            : labelLower.includes("_color_") || idLower.includes("_color_") || /^l\d+_color_/.test(idLower)
              ? "color"
              : idLower.includes("glow") || labelLower.startsWith("fx_") || idLower.includes("fx")
                ? "guide"
                : "other";
    return { id, label, index, hidden, kind };
  });
  return {
    fileName,
    sourceText: text,
    width: Number(svg.getAttribute("width")?.replace(/[^\d.]/g, "")) || Number(svg.viewBox?.baseVal?.width) || 1920,
    height: Number(svg.getAttribute("height")?.replace(/[^\d.]/g, "")) || Number(svg.viewBox?.baseVal?.height) || 1080,
    layers,
    selectedIndex: Math.max(0, layers.findIndex((layer) => layer.kind === "color")),
    viewMode: "original",
  };
}

function selectedLayeredOverlayLayer() {
  if (!layeredOverlayState?.layers?.length) return null;
  return layeredOverlayState.layers[Math.max(0, Math.min(layeredOverlayState.selectedIndex, layeredOverlayState.layers.length - 1))];
}

function shouldShowSvgLayer(layer, mode, selectedLayer) {
  if (mode === "original") return !layer.hidden;
  if (mode === "color_layers") return layer.kind === "color";
  if (mode === "selected") return layer.id === selectedLayer?.id;
  if (mode === "selected_reference") return layer.id === selectedLayer?.id || layer.kind === "reference";
  if (mode === "selected_edge") return layer.id === selectedLayer?.id || layer.kind === "edge";
  return !layer.hidden;
}

function layeredSvgDataUrl() {
  if (!layeredOverlayState) return null;
  const parser = new DOMParser();
  const doc = parser.parseFromString(layeredOverlayState.sourceText, "image/svg+xml");
  if (doc.querySelector("parsererror")) return null;
  const selectedLayer = selectedLayeredOverlayLayer();
  doc.querySelectorAll("g").forEach((group) => {
    const id = group.id || "";
    const layer = layeredOverlayState.layers.find((item) => item.id === id || item.label === svgLayerLabel(group));
    if (!layer) return;
    setSvgElementVisible(group, shouldShowSvgLayer(layer, layeredOverlayState.viewMode, selectedLayer));
  });
  const serializer = new XMLSerializer();
  const text = serializer.serializeToString(doc);
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
}

function populateLayeredOverlayControls() {
  const controls = $("layeredOverlayControls");
  const select = $("overlaySvgLayerSelect");
  const modeSelect = $("overlaySvgViewMode");
  if (!controls || !select || !modeSelect || !layeredOverlayState) return;
  controls.hidden = false;
  select.innerHTML = "";
  layeredOverlayState.layers.forEach((layer, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    const suffix = layer.kind !== "color" ? ` (${layer.kind})` : "";
    option.textContent = `${String(index + 1).padStart(2, "0")} ${layer.label}${suffix}`;
    select.appendChild(option);
  });
  select.value = String(layeredOverlayState.selectedIndex);
  modeSelect.value = layeredOverlayState.viewMode;
  updateLayeredOverlayInfo();
}

function updateLayeredOverlayInfo() {
  if (!layeredOverlayState) return;
  const layer = selectedLayeredOverlayLayer();
  const colorCount = layeredOverlayState.layers.filter((item) => item.kind === "color").length;
  setText(
    "overlaySvgLayerInfo",
    `${layeredOverlayState.fileName}: ${layeredOverlayState.layers.length} layer(s), ${colorCount} color layer(s). Showing ${layer?.label || "original visibility"}.`
  );
}

function setLayeredOverlayLayer(index) {
  if (!layeredOverlayState?.layers?.length) return;
  const count = layeredOverlayState.layers.length;
  layeredOverlayState.selectedIndex = ((Number(index) % count) + count) % count;
  if ($("overlaySvgLayerSelect")) $("overlaySvgLayerSelect").value = String(layeredOverlayState.selectedIndex);
  refreshLayeredOverlayImage();
}

function setLayeredOverlayViewMode(mode) {
  if (!layeredOverlayState) return;
  layeredOverlayState.viewMode = String(mode || "original");
  refreshLayeredOverlayImage();
}

function refreshLayeredOverlayImage() {
  if (!layeredOverlayState || !overlayImage) return;
  const url = layeredSvgDataUrl();
  if (!url) {
    setStatus("Layered SVG overlay refresh failed.");
    return;
  }
  const img = new Image();
  img.onload = () => {
    rebuildOverlaySampler(img);
    overlayImage.setElement(img);
    overlayImage.set({
      width: img.width || layeredOverlayState.width,
      height: img.height || layeredOverlayState.height,
    });
    updateOverlay();
    updateLayeredOverlayInfo();
    canvas.requestRenderAll();
  };
  img.onerror = () => setStatus("Layered SVG overlay refresh failed.");
  img.src = url;
}

function canvasPointToOverlayPixel(x, y) {
  if (!overlayImage || !overlaySampler) return null;
  const inverse = fabric.util.invertTransform(overlayImage.calcTransformMatrix());
  const local = fabric.util.transformPoint(new fabric.Point(x, y), inverse);
  const px = Math.round(local.x + (overlayImage.width || overlaySampler.width) / 2);
  const py = Math.round(local.y + (overlayImage.height || overlaySampler.height) / 2);
  if (px < 0 || py < 0 || px >= overlaySampler.width || py >= overlaySampler.height) return null;
  return { x: px, y: py };
}

function overlayColorAtCanvasPoint(x, y) {
  const pixel = canvasPointToOverlayPixel(x, y);
  if (!pixel || !overlaySampler) return null;
  const pos = (pixel.y * overlaySampler.width + pixel.x) * 4;
  const alpha = overlaySampler.data[pos + 3];
  if (alpha < 24) return null;
  return [
    overlaySampler.data[pos],
    overlaySampler.data[pos + 1],
    overlaySampler.data[pos + 2],
    255,
  ];
}

function dominantOverlayColorForObject(obj) {
  if (!obj || !overlaySampler) return null;
  obj.setCoords();
  const rect = obj.getBoundingRect(true, true);
  const stepsX = Math.max(7, Math.min(44, Math.ceil(rect.width / 42)));
  const stepsY = Math.max(7, Math.min(44, Math.ceil(rect.height / 42)));
  const bins = new Map();
  const average = { count: 0, r: 0, g: 0, b: 0, a: 0 };
  for (let iy = 0; iy < stepsY; iy++) {
    const y = rect.top + rect.height * ((iy + 0.5) / stepsY);
    for (let ix = 0; ix < stepsX; ix++) {
      const x = rect.left + rect.width * ((ix + 0.5) / stepsX);
      const pixel = canvasPointToOverlayPixel(x, y);
      if (!pixel) continue;
      const pos = (pixel.y * overlaySampler.width + pixel.x) * 4;
      const r = overlaySampler.data[pos];
      const g = overlaySampler.data[pos + 1];
      const b = overlaySampler.data[pos + 2];
      const a = overlaySampler.data[pos + 3];
      if (a < 24) continue;
      average.count++;
      average.r += r;
      average.g += g;
      average.b += b;
      average.a += a;
      const key = `${r >> 4},${g >> 4},${b >> 4}`;
      const bin = bins.get(key) || { count: 0, r: 0, g: 0, b: 0, a: 0 };
      bin.count++;
      bin.r += r;
      bin.g += g;
      bin.b += b;
      bin.a += a;
      bins.set(key, bin);
    }
  }
  if ($("overlaySampleMode")?.value === "average" && average.count) {
    return [
      Math.round(average.r / average.count),
      Math.round(average.g / average.count),
      Math.round(average.b / average.count),
      255,
    ];
  }
  let best = null;
  for (const bin of bins.values()) {
    if (!best || bin.count > best.count || (bin.count === best.count && bin.a > best.a)) best = bin;
  }
  if (!best) return null;
  return [
    Math.round(best.r / best.count),
    Math.round(best.g / best.count),
    Math.round(best.b / best.count),
    255,
  ];
}

function applyOverlayColorToObject(obj, options = {}) {
  if (obj?.kloudy?.locked) {
    if (!options.silent) setStatus("Selected layer is locked. Unlock it before sampling overlay color.");
    return false;
  }
  const color = dominantOverlayColorForObject(obj);
  if (!color) {
    if (!options.silent) setStatus("No overlay color found under the selected layer.");
    return false;
  }
  const alpha = Math.round((obj.opacity ?? 1) * 255);
  const applied = [color[0], color[1], color[2], alpha];
  applyObjectColor(obj, applied);
  if (options.remember) rememberColor(applied);
  if (canvas.getActiveObject() === obj) {
    $("colorPicker").value = colorToHex(applied);
    $("opacitySlider").value = alpha;
  }
  obj.setCoords();
  if (!options.silent) setStatus(`Sampled ${$("overlaySampleMode")?.value || "dominant"} overlay color ${colorToHex(applied)}.`);
  return true;
}

function applyLiveOverlayColor(target = null) {
  if (!$("autoOverlayColor")?.checked || !overlaySampler) return false;
  const selected = selectedVinylObjects();
  const targets = unlockedObjects(selected.length ? selected : (target?.kloudy ? [target] : []));
  let changed = false;
  targets.forEach((obj) => {
    if (applyOverlayColorToObject(obj, { remember: true, silent: true })) changed = true;
  });
  if (changed) {
    updateSelectionPanel();
    canvas.requestRenderAll();
  }
  return changed;
}

function scheduleLiveOverlayColor(target) {
  if (!$("autoOverlayColor")?.checked || !overlaySampler) return;
  if (liveOverlayColorFrame) return;
  liveOverlayColorFrame = requestAnimationFrame(() => {
    liveOverlayColorFrame = null;
    applyLiveOverlayColor(target);
  });
}

function sampleOverlayColorForSelected() {
  const objects = selectedVinylObjects();
  if (!objects.length) {
    setStatus("Select one or more layers before sampling overlay color.");
    return;
  }
  const editable = unlockedObjects(objects);
  if (!editable.length) {
    setStatus("Selected layers are locked. Unlock them before sampling overlay color.");
    return;
  }
  let changed = 0;
  editable.forEach((obj) => {
    if (applyOverlayColorToObject(obj, { remember: true, silent: true })) changed++;
  });
  canvas.requestRenderAll();
  updateSelectionPanel();
  if (changed) {
    pushHistory("overlay color sample");
    setStatus(`Sampled overlay color for ${changed} selected layer(s).${editable.length !== objects.length ? ` Skipped ${objects.length - editable.length} locked layer(s).` : ""}`);
  } else {
    setStatus("No overlay pixels found under the selected layer(s).");
  }
}

function loadOverlayImageFromUrl(url, fileName, options = {}) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      if (overlayImage) canvas.remove(overlayImage);
      rebuildOverlaySampler(img);
      overlaySourceState = {
        kind: layeredOverlayState ? "layered_svg" : "image",
        fileName,
        mimeType: options.mimeType || null,
        dataUrl: layeredOverlayState ? null : url,
        svgText: layeredOverlayState?.sourceText || null,
      };
      overlayImage = new fabric.Image(img, {
        originX: "center",
        originY: "center",
        left: 0,
        top: 0,
        opacity: Number($("overlayOpacity").value) / 100,
        selectable: false,
        evented: false,
        excludeFromExport: true,
      });
      overlayImage.kloudyOverlay = true;
      if (options.projectState) {
        applyOverlayProjectTransform(options.projectState);
        if (options.projectState.controls) {
          syncOverlayScaleControls(options.projectState.controls.scale_percent || 100);
          if ($("overlayOpacity")) $("overlayOpacity").value = Math.round((overlayImage.opacity ?? 1) * 100);
        }
      } else {
        const fit = 1800 / Math.max(img.width, img.height);
        const factor = syncOverlayScaleControls($("overlayScalePercent")?.value || $("overlayScale")?.value || 100) / 100;
        overlayImage.set({ scaleX: fit * factor, scaleY: fit * factor });
      }
      canvas.add(overlayImage);
      if (layeredOverlayState) populateLayeredOverlayControls();
      if (activeToolMode === "source") updateSourceInteractivity();
      else layerEditorHelpers();
      canvas.requestRenderAll();
      setStatus(layeredOverlayState ? `Layered SVG overlay loaded: ${fileName}` : `Overlay loaded: ${fileName}`);
      updateHud();
      resolve(overlayImage);
    };
    img.onerror = () => {
      const error = new Error(`${fileName} is not a usable image.`);
      setStatus(`Overlay load failed: ${error.message}`);
      reject(error);
    };
    img.src = url;
  });
}

function addOverlayFile(file) {
  const isSvg = file.type === "image/svg+xml" || /\.svg$/i.test(file.name || "");
  const reader = new FileReader();
  reader.onerror = () => setStatus(`Overlay load failed: could not read ${file.name}.`);
  if (isSvg) {
    reader.onload = () => {
      try {
        layeredOverlayState = parseLayeredSvg(String(reader.result || ""), file.name);
      } catch (err) {
        clearLayeredOverlayState();
        setStatus(`Overlay load failed: ${err.message || "SVG could not be parsed."}`);
        return;
      }
      const url = layeredSvgDataUrl();
      if (!url) {
        clearLayeredOverlayState();
        setStatus(`Overlay load failed: ${file.name} could not be rendered.`);
        return;
      }
      loadOverlayImageFromUrl(url, file.name, { mimeType: file.type || "image/svg+xml" });
    };
    reader.readAsText(file);
    return;
  }
  clearLayeredOverlayState();
  reader.onload = () => loadOverlayImageFromUrl(reader.result, file.name, { mimeType: file.type || null });
  reader.readAsDataURL(file);
}

function updateOverlay() {
  const percent = syncOverlayScaleControls($("overlayScalePercent")?.value || $("overlayScale")?.value || 100);
  if (!overlayImage) return;
  const base = 1800 / Math.max(overlayImage.width || 1, overlayImage.height || 1);
  const factor = percent / 100;
  overlayImage.set({
    opacity: Number($("overlayOpacity").value) / 100,
    scaleX: base * factor,
    scaleY: base * factor,
  });
  layerEditorHelpers();
  canvas.requestRenderAll();
}

function toggleOverlay() {
  if (!overlayImage) {
    setStatus("No overlay loaded. Add a source overlay first.");
    return;
  }
  overlayImage.visible = !overlayImage.visible;
  canvas.requestRenderAll();
  setStatus(overlayImage.visible ? "Overlay shown." : "Overlay hidden.");
}

function removeOverlay() {
  if (!overlayImage) {
    setStatus("No overlay loaded to remove.");
    return;
  }
  canvas.remove(overlayImage);
  overlayImage = null;
  overlaySampler = null;
  overlaySourceState = null;
  clearLayeredOverlayState();
  updateSourceInteractivity();
  canvas.requestRenderAll();
  updateHud();
  setStatus("Overlay removed.");
}

function bindEnterToApply(ids) {
  ids.forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      applySelectionFields();
    });
  });
}

async function readStartupHelpConfirmed() {
  try {
    const response = await fetch(STARTUP_HELP_CONFIRMED_API, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      return data.confirmed === true;
    }
  } catch (_err) {
    // Direct file/browser fallback only. Normal app launches use the app-folder marker API.
  }
  return localStorage.getItem(STARTUP_HELP_CONFIRMED_KEY) === "true";
}

async function writeStartupHelpConfirmed() {
  try {
    const response = await fetch(STARTUP_HELP_CONFIRMED_API, { method: "POST" });
    if (response.ok) {
      const data = await response.json();
      return data.marker || true;
    }
  } catch (_err) {
    // Direct file/browser fallback only. Normal app launches use the app-folder marker API.
  }
  localStorage.setItem(STARTUP_HELP_CONFIRMED_KEY, "true");
  return null;
}

async function maybeShowStartupHelp() {
  const dialog = $("startupHelpDialog");
  if (!dialog || await readStartupHelpConfirmed()) return false;
  requestAnimationFrame(() => {
    try {
      if (!dialog.open) dialog.showModal();
    } catch (_err) {
      // If another modal is open during startup recovery, try once more shortly after.
      setTimeout(() => {
        if (!dialog.open) dialog.showModal();
      }, 250);
    }
  });
  return true;
}

function autosaveSummary(payload) {
  const count = Array.isArray(payload?.shapes) ? payload.shapes.length : 0;
  const name = cleanProjectBaseName(payload?.name || "autosave", "autosave");
  const stamp = payload?.saved_at || payload?.created || "";
  let time = "unknown time";
  if (stamp) {
    const date = new Date(stamp);
    if (!Number.isNaN(date.getTime())) time = date.toLocaleString();
  }
  return `${name} - ${count} layer${count === 1 ? "" : "s"} - saved ${time}`;
}

async function readAutosavePayload() {
  try {
    const response = await fetch(EDITOR_AUTOSAVE_API, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      if (data.exists && data.payload && Array.isArray(data.payload.shapes)) return data.payload;
    }
  } catch (_err) {
    // Direct-file/browser fallback.
  }
  try {
    const payload = JSON.parse(localStorage.getItem(AUTOSAVE_KEY) || "null");
    if (payload && Array.isArray(payload.shapes)) return payload;
  } catch (_err) {
    // Ignore broken browser autosave.
  }
  return null;
}

async function recoverAutosavePayload(payload) {
  if (!payload || !Array.isArray(payload.shapes)) {
    setStatus("Autosave recovery failed: temp save has no shapes list.");
    return;
  }
  loadedName = cleanProjectBaseName(payload.name, "autosave");
  currentProjectName = null;
  try {
    await loadPayload({
      shapes: payload.shapes,
      editor_collapsed_groups: payload.editor_collapsed_groups || [],
    });
    applySavedGuideState(payload.editor_guides || null);
    setStatus(`Recovered temp save: ${autosaveSummary(payload)}. Use Save Project if you want to keep it.`);
  } catch (err) {
    setStatus(`Autosave recovery failed: ${err.message}`);
  }
}

async function maybeShowAutosaveRecovery() {
  if (isTextVinylHarnessRun()) {
    $("autosaveRecoveryDialog")?.close();
    return false;
  }
  const payload = await readAutosavePayload();
  if (!payload || !Array.isArray(payload.shapes) || payload.shapes.length <= 0) return false;
  recoveryAutosavePayload = payload;
  const summary = $("autosaveRecoverySummary");
  if (summary) summary.textContent = `Found: ${autosaveSummary(payload)}`;
  const dialog = $("autosaveRecoveryDialog");
  if (!dialog) return false;
  requestAnimationFrame(() => {
    try {
      if (!dialog.open) dialog.showModal();
    } catch (_err) {
      setTimeout(() => {
        if (!dialog.open) dialog.showModal();
      }, 250);
    }
  });
  return true;
}

const EDITOR_TOUR_STEPS = [
  {
    title: "Start With File Actions",
    body: "Import JSON opens generated finals, editor exports, and exported JSONs. Save Project stores editable work for later; Export FH6 JSON creates the file you send back to the main KFPS importer.",
    target: ".menuGroup:first-child",
    panel: "layersPane",
    tool: "select",
  },
  {
    title: "Use The Left Tool Rail",
    body: "The left rail is your tool belt: Select, Shapes, Dropper, Guides, Overlay, Source Move, and Mask. Keyboard shortcuts match the letters shown on each button.",
    target: ".toolRail",
    tool: "select",
  },
  {
    title: "Canvas Is The Main Workspace",
    body: "The canvas is where you move, scale, rotate, skew, snap, and clean up vinyl layers. Mouse wheel zooms, middle or right drag pans, and the HUD shows position, zoom, layer count, and hover info.",
    target: ".canvasStage",
    panel: "layersPane",
    tool: "select",
    canvasPulse: true,
  },
  {
    title: "Layers Control Draw Order",
    body: "Top rows draw over lower rows, like Krita or Photoshop layers. You can select rows, range-select with Shift, multi-select with Control, group internally, hide, lock, rename groups, and reorder depth.",
    target: "#layersPane",
    panel: "layersPane",
    tool: "select",
  },
  {
    title: "Properties Are For Exact Edits",
    body: "Use Properties for exact position, scale, rotation, skew, alpha, nudge size, and selection behavior. This is where visible-only select and invert box-select live now.",
    target: "#propertiesPane",
    panel: "propertiesPane",
    tool: "select",
  },
  {
    title: "Shape Library Places And Replaces",
    body: "Library shows the FH shape set. Shape click mode decides if a tile adds a new shape, inserts above or below the current layer, or replaces selected shapes while preserving color and transform.",
    target: "#shapeLibraryPane",
    panel: "shapeLibraryPane",
    tool: "shapeLibrary",
  },
  {
    title: "Color And Dropper",
    body: "Color holds saved swatches, alpha tools, and overlay sampling. Dropper can pick from existing vinyl layers, or from the source overlay if no shape is under the click.",
    target: "#colorPane",
    panel: "colorPane",
    tool: "dropper",
  },
  {
    title: "Overlay Is Reference Only",
    body: "Overlay loads source images or layered SVGs for tracing, color sampling, and alignment. It can draw above or below the vinyl, but it never exports as a layer.",
    target: "#overlayPane",
    panel: "overlayPane",
    tool: "overlay",
  },
  {
    title: "Guides, Grid, And Pixel Art",
    body: "Guides and grid help with clean alignment and snapping. Pixel Art Auto Fill converts a source pixel grid into exact-color stretched square layers for shape-efficient pixel work.",
    target: "#guidesPane",
    panel: "guidesPane",
    tool: "guides",
    canvasPulse: true,
  },
  {
    title: "Export Check Before Import",
    body: "Export Check gives the final sanity pass. When the layer count and warnings look right, use Export FH6 JSON, then import that JSON through KFPS Outputs.",
    target: "#exportCheckPane",
    panel: "exportCheckPane",
    tool: "select",
  },
];

function tourElements() {
  return {
    layer: $("editorTourLayer"),
    card: $("editorTourCard"),
    spotlight: $("editorTourSpotlight"),
    pulse: $("editorTourCanvasPulse"),
    progress: $("editorTourProgress"),
    title: $("editorTourTitle"),
    body: $("editorTourBody"),
    back: $("editorTourBack"),
    next: $("editorTourNext"),
  };
}

function clearTourTarget() {
  document.querySelectorAll(".editorTourTarget").forEach((el) => el.classList.remove("editorTourTarget"));
}

function clampTourCard(value, min, max) {
  if (max < min) return min;
  return Math.max(min, Math.min(max, value));
}

function tourTargetRect(target) {
  if (!target) return null;
  const rect = target.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return rect;
}

function positionTourCard(target) {
  const { card, spotlight, pulse } = tourElements();
  if (!card || !spotlight) return;
  const rect = tourTargetRect(target) || {
    left: window.innerWidth / 2 - 120,
    top: window.innerHeight / 2 - 80,
    width: 240,
    height: 160,
    right: window.innerWidth / 2 + 120,
    bottom: window.innerHeight / 2 + 80,
  };
  const pad = 10;
  spotlight.style.left = `${Math.max(8, rect.left - pad)}px`;
  spotlight.style.top = `${Math.max(8, rect.top - pad)}px`;
  spotlight.style.width = `${Math.min(window.innerWidth - 16, rect.width + pad * 2)}px`;
  spotlight.style.height = `${Math.min(window.innerHeight - 16, rect.height + pad * 2)}px`;
  spotlight.style.borderRadius = rect.width > 520 || rect.height > 360 ? "24px" : "16px";

  const cardRect = card.getBoundingClientRect();
  const gap = 18;
  const preferRight = rect.left + rect.width / 2 < window.innerWidth / 2;
  let left = preferRight ? rect.right + gap : rect.left - cardRect.width - gap;
  if (left < 16 || left + cardRect.width > window.innerWidth - 16) {
    left = clampTourCard(rect.left + rect.width / 2 - cardRect.width / 2, 16, window.innerWidth - cardRect.width - 16);
  }
  let top = clampTourCard(rect.top + rect.height / 2 - cardRect.height / 2, 16, window.innerHeight - cardRect.height - 16);
  if (rect.width > window.innerWidth * 0.48 && rect.height > window.innerHeight * 0.38) {
    left = clampTourCard(window.innerWidth - cardRect.width - 24, 16, window.innerWidth - cardRect.width - 16);
    top = 110;
  }
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;

  if (pulse) {
    const canvasRect = document.querySelector(".canvasStage")?.getBoundingClientRect();
    if (canvasRect) {
      pulse.style.left = `${canvasRect.left + canvasRect.width / 2}px`;
      pulse.style.top = `${canvasRect.top + canvasRect.height / 2}px`;
      pulse.style.width = `${Math.min(320, Math.max(180, canvasRect.width * 0.24))}px`;
      pulse.style.height = `${Math.min(220, Math.max(130, canvasRect.height * 0.22))}px`;
    }
  }
}

function prepareTourStep(step) {
  if (step.panel) activateDockPanel(step.panel);
  if (step.tool) {
    const button = document.querySelector(`.toolButton[data-tool-mode="${step.tool}"]`);
    if (button) setToolRailMode(step.tool, button.dataset.tool || button.textContent.trim());
  }
  if (step.target) {
    const target = document.querySelector(step.target);
    target?.scrollIntoView?.({ block: "center", inline: "center", behavior: "smooth" });
  }
}

function showTourStep(index) {
  if (!editorTourState?.active) return;
  const step = EDITOR_TOUR_STEPS[index];
  if (!step) {
    stopEditorTour(true);
    return;
  }
  editorTourState.index = index;
  prepareTourStep(step);
  clearTourTarget();
  const { layer, pulse, progress, title, body, back, next } = tourElements();
  if (!layer) return;
  layer.hidden = false;
  document.body.classList.add("editorTourActive");
  const target = document.querySelector(step.target || ".editorShell") || document.querySelector(".editorShell");
  target?.classList.add("editorTourTarget");
  if (progress) progress.textContent = `Step ${index + 1} of ${EDITOR_TOUR_STEPS.length}`;
  if (title) title.textContent = step.title;
  if (body) body.textContent = step.body;
  if (back) back.disabled = index <= 0;
  if (next) next.textContent = index >= EDITOR_TOUR_STEPS.length - 1 ? "Finish" : "Next";
  if (pulse) pulse.hidden = !step.canvasPulse;
  setStatus(`Tour: ${step.title}`);
  requestAnimationFrame(() => requestAnimationFrame(() => positionTourCard(target)));
}

function startEditorTour() {
  $("helpDialog")?.close();
  $("shortcutsDialog")?.close();
  $("autosaveRecoveryDialog")?.close();
  editorTourState = {
    active: true,
    index: 0,
    previousTool: activeToolMode,
    previousPanel: document.querySelector(".dockPane.active")?.id || "layersPane",
  };
  showTourStep(0);
}

function stopEditorTour(completed = false) {
  if (!editorTourState) return;
  const previousTool = editorTourState.previousTool || "select";
  const previousPanel = editorTourState.previousPanel || "layersPane";
  editorTourState = null;
  clearTourTarget();
  document.body.classList.remove("editorTourActive");
  const { layer, pulse } = tourElements();
  if (layer) layer.hidden = true;
  if (pulse) pulse.hidden = true;
  activateDockPanel(previousPanel);
  const button = document.querySelector(`.toolButton[data-tool-mode="${previousTool}"]`) || document.querySelector(".toolButton[data-tool-mode='select']");
  if (button) setToolRailMode(button.dataset.toolMode || "select", button.dataset.tool || button.textContent.trim());
  if (previousTool !== "dropper") setShapeEyedropper(false, { keepTool: true, silent: true });
  setStatus(completed ? "Editor tour complete. Use Help any time for the full reference." : "Editor tour closed.");
}

function nextTourStep(delta) {
  if (!editorTourState?.active) return;
  showTourStep(editorTourState.index + delta);
}

function repositionEditorTour() {
  if (!editorTourState?.active) return;
  const step = EDITOR_TOUR_STEPS[editorTourState.index];
  const target = document.querySelector(step?.target || ".editorShell") || document.querySelector(".editorShell");
  positionTourCard(target);
}

function bindUi() {
  const initialTheme = localStorage.getItem("kloudyFabricTheme") || document.documentElement.dataset.editorTheme;
  loadEditorThemes().then(() => loadEditorThemePreference()).then((serverTheme) => {
    if (!serverTheme) applyEditorTheme(initialTheme, { persist: false });
    if (!serverTheme) saveEditorThemePreference(normalizeTheme(initialTheme));
  });
  $("editorThemeSelect")?.addEventListener("change", (event) => applyEditorTheme(event.target.value));
  $("adjustTheme")?.addEventListener("click", openThemeAdjustDialog);
  $("startEditorTour")?.addEventListener("click", startEditorTour);
  $("editorTourSkip")?.addEventListener("click", () => stopEditorTour(false));
  $("editorTourBack")?.addEventListener("click", () => nextTourStep(-1));
  $("editorTourNext")?.addEventListener("click", () => nextTourStep(1));
  window.addEventListener("resize", repositionEditorTour);
  window.addEventListener("scroll", repositionEditorTour, true);
  $("closeThemeAdjust")?.addEventListener("click", () => closeThemeAdjustDialog());
  $("themeAdjustDialog")?.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeThemeAdjustDialog();
  });
  $("saveThemeAdjust")?.addEventListener("click", saveAdjustedTheme);
  $("openJsonBrowser")?.addEventListener("click", openJsonBrowser);
  $("closeJsonBrowser")?.addEventListener("click", () => $("jsonBrowserDialog")?.close());
  $("refreshJsonBrowser")?.addEventListener("click", refreshJsonBrowser);
  $("jsonBrowserSource")?.addEventListener("change", refreshJsonBrowser);
  $("selectJsonBrowserEntry")?.addEventListener("click", importSelectedBrowserJson);
  $("loadProject")?.addEventListener("click", openProjectBrowser);
  $("closeProjectBrowser")?.addEventListener("click", () => $("projectBrowserDialog")?.close());
  $("refreshProjectBrowser")?.addEventListener("click", refreshProjectBrowser);
  $("openProjectFolder")?.addEventListener("click", openProjectFolder);
  $("selectProjectEntry")?.addEventListener("click", loadSelectedProject);
  $("importJsonFromDisk")?.addEventListener("click", () => $("jsonInput")?.click());
  $("jsonInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(`Selected JSON: ${file.name}`);
    loadJsonFile(file)
      .then(() => $("jsonBrowserDialog")?.close())
      .catch((err) => showError("JSON import failed", err))
      .finally(() => { event.target.value = ""; });
  });
  $("exportJson").addEventListener("click", exportJson);
  $("saveProject").addEventListener("click", saveProject);
  $("fitView").addEventListener("click", fitDesignView);
  $("resetView").addEventListener("click", resetView);
  $("undoBtn").addEventListener("click", undo);
  $("redoBtn").addEventListener("click", redo);
  $("selectionLockToggle")?.addEventListener("click", toggleSelectionLock);
  $("helpBtn").addEventListener("click", () => $("helpDialog").showModal());
  $("closeHelp").addEventListener("click", () => $("helpDialog").close());
  $("shortcutsBtn")?.addEventListener("click", () => $("shortcutsDialog")?.showModal());
  $("openShortcutsFromHelp")?.addEventListener("click", () => {
    $("helpDialog")?.close();
    $("shortcutsDialog")?.showModal();
  });
  $("closeShortcuts")?.addEventListener("click", () => $("shortcutsDialog")?.close());
  $("startupHelpConfirm")?.addEventListener("click", async () => {
    if ($("startupHelpDontShow")?.checked) {
      const marker = await writeStartupHelpConfirmed();
      $("startupHelpDialog")?.close();
      setStatus(marker
        ? "Startup help confirmed for this app folder. The full Help menu is available from the Help button in the top toolbar."
        : "Startup help confirmed for this browser. The full Help menu is available from the Help button in the top toolbar.");
      maybeShowAutosaveRecovery();
      return;
    }
    setStatus("Tick \"I have read and understood this\" before opening the editor.");
  });
  $("recoverAutosave")?.addEventListener("click", async () => {
    $("autosaveRecoveryDialog")?.close();
    await recoverAutosavePayload(recoveryAutosavePayload);
  });
  $("dismissAutosave")?.addEventListener("click", () => {
    $("autosaveRecoveryDialog")?.close();
    setStatus("Temp save kept. It will be offered again next launch until recovered, discarded, or replaced.");
  });
  $("discardAutosave")?.addEventListener("click", () => {
    $("autosaveRecoveryDialog")?.close();
    clearAutosave();
    recoveryAutosavePayload = null;
    setStatus("Temp save discarded.");
  });
  $("colorSwatchButton").addEventListener("click", openColorDialog);
  $("colorPanelSwatch").addEventListener("click", openColorDialog);
  $("quickColorSwatch")?.addEventListener("click", openColorDialog);
  $("shapePlacementMode")?.addEventListener("change", updateShapePlacementLabel);
  $("closeColorDialog").addEventListener("click", () => {
    commitPendingDialogColor();
    $("colorDialog").close();
  });
  $("colorDialog").addEventListener("close", commitPendingDialogColor);
  $("saveFavoriteColor").addEventListener("click", saveCurrentFavoriteColor);
  $("removeFavoriteColor").addEventListener("click", removeCurrentFavoriteColor);
  $("clearFavoriteColors").addEventListener("click", clearFavoriteColors);
  $("colorEyedropper").addEventListener("click", () => setShapeEyedropper(!shapeEyedropperActive));
  $("dialogColorPicker").addEventListener("input", (event) => {
    const selected = selectedVinylObjects();
    const alpha = selected.length === 1
      ? Math.round((selected[0].opacity ?? 1) * 255)
      : (Number($("opacitySlider")?.value) || rememberedColor[3] || 255);
    scheduleDialogColorPreview(hexToRgb(event.target.value, alpha));
  });
  $("dialogColorPicker").addEventListener("change", (event) => {
    const selected = selectedVinylObjects();
    const alpha = selected.length === 1
      ? Math.round((selected[0].opacity ?? 1) * 255)
      : (Number($("opacitySlider")?.value) || rememberedColor[3] || 255);
    commitDialogColor(hexToRgb(event.target.value, alpha));
  });
  $("applyFields").addEventListener("click", applySelectionFields);
  $("deleteLayer").addEventListener("click", deleteSelected);
  $("duplicateLayer").addEventListener("click", duplicateSelected);
  $("quickDeleteLayer")?.addEventListener("click", deleteSelected);
  $("quickDuplicateLayer")?.addEventListener("click", duplicateSelected);
  $("bringForward").addEventListener("click", () => moveSelected(1));
  $("sendBackward").addEventListener("click", () => moveSelected(-1));
  $("fitSelected").addEventListener("click", fitSelectedView);
  $("quickFitSelected")?.addEventListener("click", fitSelectedView);
  $("groupSelected").addEventListener("click", groupSelectedLayers);
  $("quickGroupSelected")?.addEventListener("click", groupSelectedLayers);
  $("renameSelectedGroup")?.addEventListener("click", renameSelectedGroup);
  $("hideSelectedGroup").addEventListener("click", toggleSelectedGroupVisibility);
  $("lockSelectedGroup").addEventListener("click", toggleSelectedGroupLock);
  $("ungroupSelected").addEventListener("click", ungroupSelectedLayers);
  $("changeSelectedShape")?.addEventListener("click", armShapeReplacementFromLayers);
  $("cancelGlobalShapeReplace")?.addEventListener("click", () => {
    pendingGlobalShapeReplacement = null;
    hideGlobalShapeReplacePanel();
    setStatus("Global Change Shape cancelled.");
  });
  $("applyColorToSelection").addEventListener("click", () => {
    const alpha = Number($("opacitySlider")?.value ?? rememberedColor[3] ?? 255);
    applyEditorColor(hexToRgb($("colorPicker")?.value || colorToHex(rememberedColor), alpha), "apply color to selection");
  });
  $("maskSelectedTool")?.addEventListener("click", toggleSelectedMaskLayers);
  $("colorPicker").addEventListener("input", applySelectionFields);
  $("opacitySlider").addEventListener("input", applySelectionFields);
  $("equalizeAlpha").addEventListener("click", equalizeSelectedAlpha);
  bindEnterToApply(["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput", "opacitySlider"]);
  $("layerSearch").addEventListener("input", refreshLayers);
  $("pixelSelect").addEventListener("change", () => setPixelSelection($("pixelSelect").checked));
  $("boxVisibleOnly").addEventListener("change", () => setPixelSelection($("boxVisibleOnly").checked));
  $("overlayInput").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) addOverlayFile(file);
    event.target.value = "";
  });
  $("overlayOpacity").addEventListener("input", updateOverlay);
  $("overlayScale").addEventListener("input", (event) => {
    syncOverlayScaleControls(event.target.value);
    updateOverlay();
  });
  $("overlayScalePercent")?.addEventListener("change", updateOverlay);
  $("overlayScalePercent")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      updateOverlay();
      event.target.blur();
    }
  });
  if ($("overlayLayerMode")) {
    $("overlayLayerMode").value = overlayLayerMode;
    $("overlayLayerMode").addEventListener("change", (event) => setOverlayLayerMode(event.target.value));
  }
  $("overlaySvgViewMode")?.addEventListener("change", (event) => setLayeredOverlayViewMode(event.target.value));
  $("overlaySvgLayerSelect")?.addEventListener("change", (event) => setLayeredOverlayLayer(Number(event.target.value)));
  $("overlaySvgPrevLayer")?.addEventListener("click", () => setLayeredOverlayLayer((layeredOverlayState?.selectedIndex || 0) - 1));
  $("overlaySvgNextLayer")?.addEventListener("click", () => setLayeredOverlayLayer((layeredOverlayState?.selectedIndex || 0) + 1));
  $("overlaySampleMode").addEventListener("change", () => {
    if ($("autoOverlayColor")?.checked) sampleOverlayColorForSelected();
  });
  $("autoOverlayColor").addEventListener("change", () => {
    if ($("autoOverlayColor").checked) applyLiveOverlayColor();
  });
  $("sampleOverlayColor").addEventListener("click", sampleOverlayColorForSelected);
  [
    "gridEnabled",
    "gridSize",
    "gridOpacity",
    "guidesVisible",
    "snapGuides",
    "snapGrid",
    "snapCtrlOnly",
    "snapThreshold",
    "guideConstraint",
    "snapGuideAnchor",
    "snapGuideEnd",
  ].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener(el.tagName === "SELECT" ? "change" : "input", syncGuideStateFromUi);
    el.addEventListener("change", syncGuideStateFromUi);
  });
  $("pixelArtInput")?.addEventListener("change", (event) => {
    pixelArtSourceFile = event.target.files?.[0] || null;
    if (!pixelArtSourceFile) {
      setPixelArtStatus("Choose a pixel-art source image.");
      return;
    }
    setPixelArtStatus(`Pixel-art source loaded: ${pixelArtSourceFile.name}. Press Generate to detect its pixel grid.`);
  });
  $("generatePixelArt")?.addEventListener("click", generatePixelArtRectangles);
  loadTextVinylFontPreference();
  $("textVinylFontSelect")?.addEventListener("change", () => {
    syncTextVinylFontUi();
    saveTextVinylFontPreference();
  });
  $("textVinylCustomFont")?.addEventListener("input", saveTextVinylFontPreference);
  $("generateTextVinyl")?.addEventListener("click", generateTextVinylShapes);
  $("deleteGuide")?.addEventListener("click", deleteSelectedGuide);
  $("clearGuides")?.addEventListener("click", clearGuides);
  $("toggleOverlay").addEventListener("click", toggleOverlay);
  $("removeOverlay").addEventListener("click", removeOverlay);
  $("showFavorites").addEventListener("click", () => {
    showFavoritesOnly = true;
    renderShapeGrid();
  });
  $("showAllShapes").addEventListener("click", () => {
    showFavoritesOnly = false;
    renderShapeGrid();
  });
  if ($("reuseLastFontSize")) {
    $("reuseLastFontSize").checked = reuseLastFontSize;
    $("reuseLastFontSize").addEventListener("change", (event) => {
      reuseLastFontSize = Boolean(event.target.checked);
      localStorage.setItem("kloudyFabricReuseLastFontSize", String(reuseLastFontSize));
      setStatus(reuseLastFontSize ? "New font shapes reuse the last edited font size." : "New font shapes use viewport placement size.");
    });
  }
  document.querySelectorAll(".dockTab").forEach((button) => {
    button.addEventListener("click", () => activateDockPanel(button.dataset.panel));
  });
  document.querySelectorAll(".toolButton").forEach((button) => {
    if (button.classList.contains("toolActionButton")) return;
    button.addEventListener("click", () => setActiveTool(button));
  });
  $("resetShortcuts")?.addEventListener("click", resetShortcuts);
  renderShortcutEditor();
  updateShortcutLabels();
  document.addEventListener("keydown", (event) => {
    if (editorTourState?.active) {
      if (event.key === "Escape") {
        event.preventDefault();
        stopEditorTour(false);
      } else if (event.key === "Enter" || event.key === "ArrowRight") {
        event.preventDefault();
        nextTourStep(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        nextTourStep(-1);
      }
      return;
    }
    if (event.target && event.target.classList?.contains("shortcutCapture")) return;
    if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    const toolAction = ["selectTool", "shapeLibrary", "dropper", "guides", "overlay", "sourceTool"].find((action) => shortcutMatches(event, action));
    if (toolAction) {
      event.preventDefault();
      if (!event.repeat) {
        const toolKey = {
          selectTool: "v",
          shapeLibrary: "s",
          dropper: "i",
          guides: "g",
          overlay: "o",
          sourceTool: "r",
        }[toolAction];
        activateToolShortcut(toolKey);
      }
      if (toolAction === "selectTool" && !vBoxSelectActive) {
        event.preventDefault();
        setVBoxSelectActive(true);
        setStatus("Hold Select shortcut: box-select override active. Drag from anywhere, even on top of a shape.");
      }
      return;
    }
    if (shortcutMatches(event, "delete") || event.key === "Backspace") {
      event.preventDefault();
      if (selectedGuideId && !selectedVinylObjects().length) {
        deleteSelectedGuide();
        return;
      }
      if (activeToolMode === "guides") {
        setGuideStatus("No guide selected. Vinyl layers are protected while the Guides tool is active.");
        return;
      }
      deleteSelected();
      return;
    }
    if (shortcutMatches(event, "undo")) {
      event.preventDefault();
      undo();
      return;
    }
    if (shortcutMatches(event, "redo")) {
      event.preventDefault();
      redo();
      return;
    }
    if (shortcutMatches(event, "duplicate")) {
      event.preventDefault();
      duplicateSelected();
      return;
    }
    if (shortcutMatches(event, "flipHorizontal")) {
      event.preventDefault();
      flipSelected("x");
      return;
    }
    if (shortcutMatches(event, "flipVertical")) {
      event.preventDefault();
      flipSelected("y");
      return;
    }
    if (shortcutMatches(event, "makeMask")) {
      event.preventDefault();
      toggleSelectedMaskLayers();
      return;
    }
    if (shortcutMatches(event, "axisLockX")) {
      event.preventDefault();
      if (!event.repeat) setDragAxisLock("x");
      return;
    }
    if (shortcutMatches(event, "axisLockY")) {
      event.preventDefault();
      if (!event.repeat) setDragAxisLock("y");
      return;
    }
    if (shortcutMatches(event, "selectionLock")) {
      event.preventDefault();
      if (!event.repeat) toggleSelectionLock();
      return;
    }
    const step = (Number($("nudgeStep").value) || 1) * (event.shiftKey ? 10 : 1);
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      nudgeSelected(-step, 0);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      nudgeSelected(step, 0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      nudgeSelected(0, -step);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      nudgeSelected(0, step);
    } else if (shortcutMatches(event, "layerForward")) {
      event.preventDefault();
      moveSelected(1);
    } else if (shortcutMatches(event, "layerBackward")) {
      event.preventDefault();
      moveSelected(-1);
    }
  });
  document.addEventListener("keyup", (event) => {
    if (event.target && event.target.classList?.contains("shortcutCapture")) return;
    if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (shortcutMatches(event, "axisLockX") || normalizeShortcutKey(event.key) === shortcutPrimaryKey("axisLockX")) {
      event.preventDefault();
      clearDragAxisLock("x");
      return;
    }
    if (shortcutMatches(event, "axisLockY") || normalizeShortcutKey(event.key) === shortcutPrimaryKey("axisLockY")) {
      event.preventDefault();
      clearDragAxisLock("y");
      return;
    }
    if (normalizeShortcutKey(event.key) !== shortcutPrimaryKey("selectTool")) return;
    if (vBoxSelectActive) {
      event.preventDefault();
      setVBoxSelectActive(false);
      setStatus("Box-select override released.");
    }
  });
  document.addEventListener("wheel", handleLayerDragWheel, { passive: false });
  window.addEventListener("blur", () => {
    if (vBoxSelectActive) setVBoxSelectActive(false);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  initCanvas();
  buildShapeLibrary();
  bindUi();
  rememberColor(rememberedColor);
  applyGuideStateToUi();
  renderGuideObjects();
  updateSelectionPanel();
  updateShapePlacementLabel();
  const loadedStartupProject = await loadStartupProjectFromQuery();
  const startupHelpShown = await maybeShowStartupHelp();
  if (!loadedStartupProject && !startupHelpShown) maybeShowAutosaveRecovery();
});
