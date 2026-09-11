/* global fabric, KfpsFabricAdapter */
"use strict";

const editorSettings = window.KfpsEditorPreferences || localStorage;

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
const PROJECT_SHARING_ACK_KEY = "kloudyFabricProjectSharingAcknowledged";
const PROJECT_SHARING_NOTICE_VERSION = "1";
let startupProjectWasLoaded = false;
let projectSharingConfirmationPending = false;
const LANGUAGE_NOTICE_ACK_KEY = "kloudyFabricLanguageNoticeAcknowledged";
let languageNoticeConfirmationPending = false;
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
const EDITOR_SESSION_STORAGE_KEY = "kfpsFabricEditorSession";

function editorSessionToken() {
  try {
    const hash = new URLSearchParams((window.location.hash || "").replace(/^#/, ""));
    const supplied = hash.get("session") || "";
    if (supplied) {
      window.sessionStorage.setItem(EDITOR_SESSION_STORAGE_KEY, supplied);
      window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
      return supplied;
    }
    return window.sessionStorage.getItem(EDITOR_SESSION_STORAGE_KEY) || "";
  } catch (_err) {
    return "";
  }
}

const EDITOR_MUTATION_HEADERS = Object.freeze({
  "X-KFPS-Editor-Session": editorSessionToken(),
});
const SHORTCUTS_KEY = "kloudyFabricShortcuts";
const OVERLAY_LAYER_MODE_KEY = "kloudyFabricOverlayLayerMode";
const AUTOSAVE_KEY = "kloudyFabricAutosave";
const AUTOSAVE_CLEAR_KEY = `${AUTOSAVE_KEY}:clearedRevision`;
const EDITOR_PROJECT_MAX_BYTES = 150 * 1024 * 1024;
const EDITOR_REFERENCE_MAX_BYTES = 100 * 1024 * 1024;
const editorPersistence = KfpsEditorPersistence.create({ headers: EDITOR_MUTATION_HEADERS, maxBytes: EDITOR_PROJECT_MAX_BYTES });
const AUTOSAVE_IDLE_MS = 500;
const AUTOSAVE_MAX_WAIT_MS = 2000;
const TEXT_VINYL_FONT_KEY = "kloudyFabricTextVinylFont";
const TEXT_VINYL_CUSTOM_FONT_KEY = "kloudyFabricTextVinylCustomFont";
const EDITOR_CLIPBOARD_KEY = "kloudyFabricLayerClipboard";
const EDITOR_DOCK_KEY = "kloudyFabricDockState";
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

function startupBrowseMode() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    return (params.get("browse") || "").trim().toLowerCase();
  } catch (_err) {
    return "";
  }
}

const DEFAULT_SHORTCUTS = {
  selectTool: "V",
  shapeLibrary: "S",
  textTool: "T",
  pixelArt: "P",
  dropper: "I",
  guides: "G",
  overlay: "O",
  sourceTool: "R",
  delete: "Delete",
  duplicate: "Ctrl+D",
  copy: "Ctrl+C",
  paste: "Ctrl+V",
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

const SHORTCUT_LABELS = {
  selectTool: KfpsI18n.t("Select / Move"),
  shapeLibrary: KfpsI18n.t("Shape Library"),
  textTool: KfpsI18n.t("Text Builder"),
  pixelArt: KfpsI18n.t("Pixel Art"),
  dropper: KfpsI18n.t("Eyedropper"),
  guides: KfpsI18n.t("Guides / Snap"),
  overlay: KfpsI18n.t("Reference Image"),
  sourceTool: KfpsI18n.t("Move Reference"),
  delete: KfpsI18n.t("Delete selected"),
  duplicate: KfpsI18n.t("Duplicate selected"),
  copy: KfpsI18n.t("Copy selected"),
  paste: KfpsI18n.t("Paste copied layers"),
  undo: KfpsI18n.t("Undo"),
  redo: KfpsI18n.t("Redo"),
  layerForward: KfpsI18n.t("Layer forward"),
  layerBackward: KfpsI18n.t("Layer backward"),
  flipVertical: KfpsI18n.t("Flip vertical"),
  flipHorizontal: KfpsI18n.t("Flip horizontal"),
  makeMask: KfpsI18n.t("Toggle mask layer"),
  axisLockX: KfpsI18n.t("Drag lock X axis"),
  axisLockY: KfpsI18n.t("Drag lock Y axis"),
  selectionLock: KfpsI18n.t("Lock current selection"),
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
const FULL_RESOURCE_SLOTS = Array.from({ length: 40 }, (_value, index) => index + 1);
const GRADIENT_RESOURCE_SLOTS = {
  Gradient_Shapes: FULL_RESOURCE_SLOTS,
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
const ALPHA_MESH_IMAGE_FAMILIES = new Set(["Community_Vinyls_1", "Community_Vinyls_2", "Community_Vinyls_3"]);
const ALPHA_MESH_RASTER_SCALE = 8;
const ALPHA_MESH_RASTER_MIN_SIZE = 512;
const ALPHA_MESH_RASTER_MAX_SIZE = 2048;
const SELECTION_OUTLINE_SCREEN_WIDTH = 1.65;
const MAX_VINYL_LAYERS = 3000;
const OBJECT_BUILD_CONCURRENCY = 24;
const HYBRID_RENDER_MIN_LAYERS = 300;
const HYBRID_RENDER_PREWARM_CHUNK = 64;
const HYBRID_RENDER_SETTLE_MS = 260;
const resourceCache = new Map();
const resourcePathPromiseCache = new Map();
const resourceOutlineCache = new Map();
const resourcePayloadCache = new Map();
const resourcePayloadPromiseCache = new Map();
const alphaMeshImageCache = new Map();
const fabricImageElementPromiseCache = new Map();
const fabricPathDataCache = new Map();
const selectionOutlinePathPromises = new Map();
const hybridMeshCache = new Map();
const textVinylMeshCache = new Map();
let canvas;
const vinylObjectRegistry = new KfpsEditorCore.OrderedObjectRegistry((object) => (
  Boolean(object?.kloudy)
  && !object.kloudyGuide
  && !object.kloudyMaskOutline
  && !object.kloudyMaskCutout
));
const guideObjectRegistry = new KfpsEditorCore.OrderedObjectRegistry((object) => Boolean(object?.kloudyGuide));
let hybridRenderer = null;
let hybridRenderActive = false;
let hybridRenderFrame = null;
let hybridRenderSettleTimer = null;
let hybridLowerVisibility = "";
let hybridDisabledReason = "";
let hybridHiddenObjects = [];
let hybridFabricVisibleObjects = new Set();
let isPanning = false;
let lastPan = null;
let loadedName = "untitled";
let currentProjectName = null;
let savedHistoryState = null;
let documentGeneration = 0;
let documentDirty = false;
let overlayRevision = 0;
let overlayLoadGeneration = 0;
let overlayRefreshGeneration = 0;
let savedOverlayRevision = 0;
let overlayImage = null;
let history = [];
let historyIndex = -1;
let historyLocked = false;
let protectedHistoryIndex = -1;
let lastHistoryReason = "";
let lastHistoryAt = 0;
let nudgeHistoryTimer = null;
let nudgeHistoryStarted = null;
let nudgeHistoryPending = false;
const pendingNudgeObjects = new Set();
let showFavoritesOnly = false;
let favorites = loadFavoriteShapes();
let shapeNames = { families: {} };
let shapeWords = { families: {} };
let rememberedColor = [255, 255, 255, 255];
let favoriteColors = loadFavoriteColors();
let selectedFavoriteColorSlot = 0;
let editorThemes = new Map(BUILTIN_EDITOR_THEMES.map((theme) => [theme.id, theme]));
let themeAdjustRestoreTheme = null;
let themeAdjustSaving = false;
let shapeEyedropperActive = false;
let activeToolMode = "select";
let editorAssetLibrary = null;
let overlaySampler = null;
let layeredOverlayState = null;
let overlaySourceState = null;
let liveOverlayColorFrame = null;
// Resource locations are installation-relative, never a persisted browser origin.
let resolvedResourceBase = null;
let collapsedLayerGroups = new Set();
let dropperPreservedActiveObject = null;
let guideState = defaultGuideState();
let guideDraft = null;
let guideDraftObject = null;
let guideDraftPress = null;
let guidePointer = null;
let guidePanButton = null;
let guideSpacePan = false;
let selectedGuideId = null;
let guideRenderQueued = false;
let lastSnapMessageAt = 0;
let snapOverlayObjects = [];
let transformAnchorSnapshot = null;
let reuseLastFontSize = editorSettings.getItem("kloudyFabricReuseLastFontSize") === "true";
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
let overlayLayerMode = normalizeOverlayLayerMode(editorSettings.getItem(OVERLAY_LAYER_MODE_KEY));
let maskPreviewOutlines = new Map();
let maskPreviewCutouts = new Map();
let layerListRows = new Map();
let layerListEntries = [];
let layerVirtualLayout = KfpsEditorCore.buildVirtualLayout([]);
let layerVirtualRenderFrame = null;
let renderedLayerEntries = [];
let layerVirtualStart = -1;
let layerVirtualEnd = -1;
let lastLayerFilter = "";
let lastLayerListKey = null;
let layerDragState = null;
let layerDragGhost = null;
let suppressLayerClick = false;
let nextLayerListObjectId = 1;
let nextEditorObjectId = 1;
let editorMutationRunning = false;
const editorMutationQueue = [];
let layerRefreshFrame = null;
let layerRefreshNeedsStructure = false;
let canvasRenderFrame = null;
let canvasGeometryFrame = null;
let visualGridFrame = null;
let hudUpdateFrame = null;
let pendingHudPointer = null;
let pendingHudTarget = null;
let pendingHudText = null;
let layerStatsCache = null;
let autosaveWriteTimer = null;
let autosavePendingSince = null;
let autosaveRetryTimer = null;
let autosaveRetryDelay = 2000;
let pendingAutosavePayload = null;
let autosaveRevision = 0;
let queuedAutosaveOperation = null;
let autosaveWritePromise = null;
let autosaveStatus = { state: "idle", revision: 0 };
let recoveryAutosavePayload = null;
let recoveryRestoreDepth = 0;
let unavailableSourceOverlayState = null;
let startupRecoveryHandled = false;
let recoveryReadWarning = "";
let canvasResizeObserver = null;
let lastCanvasSize = { width: 0, height: 0 };
let jsonBrowserState = {
  source: "generated",
  groups: [],
  selectedGroupIndex: -1,
  selectedEntryIndex: -1,
  loading: false,
  request: null,
};
let projectBrowserState = {
  entries: [],
  selectedIndex: -1,
  loading: false,
};
let pendingGlobalShapeReplacement = null;
let exportSaveInProgress = false;
let projectSaveInProgress = false;
let editorClipboard = null;
let textPromptResolver = null;
let confirmationResolver = null;
let dockResizeState = null;
let toastTimer = null;
let pixelArtSourceFile = null;
let pixelArtAnalysisCancel = null;
let pixelArtGenerationRunning = false;
let textVinylGenerationRunning = false;
let editorTourState = null;
const TEXT_VINYL_SOURCE_FLAG = "kfps_text_vinyl";

try {
  const savedColor = JSON.parse(editorSettings.getItem("kloudyFabricLastColor") || "null");
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
  if (key === " ") return "Space";
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
  if (event.isComposing || event.keyCode === 229 || ["Process", "Dead", "Unidentified"].includes(event.key)) return "";
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
    const saved = JSON.parse(editorSettings.getItem(SHORTCUTS_KEY) || "{}");
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
  editorSettings.setItem(SHORTCUTS_KEY, JSON.stringify(shortcuts));
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
  setStatus(KfpsI18n.t("Editor shortcuts reset to defaults."));
}

function setShortcut(action, combo) {
  const normalized = normalizeShortcutCombo(combo);
  if (!normalized || !DEFAULT_SHORTCUTS[action]) return;
  const conflict = Object.keys(DEFAULT_SHORTCUTS).find(other => other !== action && shortcutFor(other) === normalized);
  if (conflict) {
    setStatus(KfpsI18n.t("{0} is already assigned to {1}. Choose another shortcut.", normalized, SHORTCUT_LABELS[conflict] || conflict));
    return;
  }
  shortcuts[action] = normalized;
  saveShortcuts();
  renderShortcutEditor();
  updateShortcutLabels();
  setStatus(KfpsI18n.t("{0} shortcut set to {1}.", SHORTCUT_LABELS[action] || action, normalized));
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
    row.innerHTML = KfpsI18n.t("\n      <span>{0}</span>\n      <input class=\"shortcutCapture\" data-shortcut-action=\"{1}\" readonly value=\"{2}\" title=\"Click, then press a new shortcut.\">\n    ", escapeHtml(SHORTCUT_LABELS[action] || action), escapeHtml(action), escapeHtml(shortcutFor(action)));
    const input = row.querySelector("input");
    input.addEventListener("focus", () => {
      input.classList.add("capturing");
      input.value = KfpsI18n.t("Press keys...");
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
    option.textContent = theme.builtin ? KfpsI18n.t(theme.name) : KfpsI18n.t("{0} (Custom)", theme.name);
    select.appendChild(option);
  });
  select.value = normalizeTheme(current);
}

function saveEditorThemePreference(theme) {
  if (window.KfpsEditorPreferences) {
    editorSettings.setItem("kloudyFabricTheme", normalizeTheme(theme));
    return;
  }
  fetch(EDITOR_PREFS_API, {
    method: "POST",
    headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ theme: normalizeTheme(theme) }),
  }).catch(() => {
    // Direct-file launches or blocked local server writes still keep localStorage.
  });
}

function applyEditorTheme(theme, options = {}) {
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
    editorSettings.setItem("kloudyFabricTheme", safeTheme);
    saveEditorThemePreference(safeTheme);
  }
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
    const response = await fetch(EDITOR_THEMES_API, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (response.ok) {
      const data = await response.json();
      (Array.isArray(data.themes) ? data.themes : []).forEach((theme) => {
        if (!theme?.id) return;
        editorThemes.set(String(theme.id), {
          id: String(theme.id),
          name: String(theme.name || theme.id),
          builtin: Boolean(theme.builtin),
          base: BUILTIN_EDITOR_THEMES.some(entry => entry.id === theme.base) ? theme.base : "pastel",
          values: theme.values && typeof theme.values === "object" ? theme.values : {},
        });
      });
    }
  } catch (_err) {
    // Direct-file/browser fallback keeps built-in themes only.
  }
  populateEditorThemeSelect(editorSettings.getItem("kloudyFabricTheme") || "pastel");
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
  return KfpsI18n.t("\n    <div class=\"themeAdjustRow\">\n      <label for=\"theme-{0}\">{1}</label>\n      {2}\n      <input id=\"theme-{3}\" class=\"themeValueInput\" data-theme-var=\"{4}\" value=\"{5}\" spellcheck=\"false\" aria-label=\"{6} value\">\n    </div>\n  ", escapeHtml(key.slice(2)), escapeHtml(label), isHex ? KfpsI18n.t("<input class=\"themeColorInput\" type=\"color\" aria-label=\"{0} color\" value=\"{1}\" data-theme-color-for=\"{2}\">", escapeHtml(label), escapeHtml(safeValue), escapeHtml(key)) : '<span></span>', escapeHtml(key.slice(2)), escapeHtml(key), escapeHtml(safeValue), escapeHtml(label));
}

function themeFieldInput(fields, key) {
  return [...(fields?.querySelectorAll(".themeValueInput") || [])].find((input) => input.dataset.themeVar === key) || null;
}

function themeColorInput(fields, key) {
  return [...(fields?.querySelectorAll(".themeColorInput") || [])].find((input) => input.dataset.themeColorFor === key) || null;
}

function renderThemeAdjustFields(values) {
  const fields = $("themeAdjustFields");
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
  const invalid = Boolean($("themeAdjustFields")?.querySelector('[aria-invalid="true"]'));
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
  const status = $("themeAdjustStatus");
  if (status) {
    status.textContent = invalid ? KfpsI18n.t("Invalid color value") : minimum === null ? KfpsI18n.t("Text contrast: unavailable for these colors") : `${minimum < 4.5 ? KfpsI18n.t("Low text contrast") : KfpsI18n.t("Text contrast")}: ${minimum.toFixed(1)}:1`;
    status.dataset.warning = String(invalid || (minimum !== null && minimum < 4.5));
  }
  if ($("saveThemeAdjust")) $("saveThemeAdjust").disabled = themeAdjustSaving || invalid;
}

function previewThemeAdjustBase() {
  applyEditorTheme($("themeAdjustBase").value, { persist: false, preview: true });
  renderThemeAdjustFields(themeFieldCurrentValues());
}

function openThemeAdjustDialog() {
  const dialog = $("themeAdjustDialog");
  if (!dialog || themeAdjustSaving) return;
  themeAdjustRestoreTheme = normalizeTheme($("editorThemeSelect")?.value || editorSettings.getItem("kloudyFabricTheme") || "pastel");
  const current = themeById(themeAdjustRestoreTheme);
  $("themeAdjustName").value = current.builtin ? KfpsI18n.t("{0} Custom", current.name) : current.name;
  $("themeAdjustBase").replaceChildren(...[...editorThemes.values()].map(theme => {
    const option = document.createElement("option");
    option.value = theme.id;
    option.textContent = theme.builtin ? KfpsI18n.t(theme.name) : theme.name;
    return option;
  }));
  $("themeAdjustBase").value = themeAdjustRestoreTheme;
  renderThemeAdjustFields(themeFieldCurrentValues());
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
  if (themeAdjustSaving || $("themeAdjustFields")?.querySelector('[aria-invalid="true"]')) return;
  const name = cleanProjectBaseName($("themeAdjustName")?.value || "Custom Theme", "Custom Theme");
  const values = {};
  document.querySelectorAll(".themeValueInput[data-theme-var]").forEach((input) => {
    values[input.dataset.themeVar] = input.value;
  });
  themeAdjustSaving = true;
  const controls = $("themeAdjustDialog").querySelectorAll("input, select, button");
  controls.forEach(control => { control.disabled = true; });
  try {
    const response = await fetch(EDITOR_THEMES_API, {
      method: "POST",
      headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" },
      signal: AbortSignal.timeout(30000),
      body: JSON.stringify({ name, values, base: document.documentElement.dataset.editorThemeBase || "pastel" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
    await loadEditorThemes();
    const themeId = data.theme?.id;
    if (themeId) applyEditorTheme(themeId);
    themeAdjustRestoreTheme = null;
    $("themeAdjustDialog")?.close();
    setStatus(KfpsI18n.t("Saved custom editor theme: {0}.", data.theme?.name || name));
  } catch (err) {
    showError(KfpsI18n.t("Theme save failed"), err);
    setStatus(KfpsI18n.t("Theme save failed: {0}", KfpsI18n.error(err.message || err)));
  } finally {
    themeAdjustSaving = false;
    controls.forEach(control => { control.disabled = false; });
    updateThemeContrastStatus();
  }
}

function closeThemeAdjustDialog({ restore = true } = {}) {
  if (themeAdjustSaving) return;
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
  if (ALPHA_MESH_IMAGE_FAMILIES.has(String(resource.family))) return false;
  const name = shapeNames?.families?.[resource.family]?.[String(resource.index)] || "";
  return /\b(gradient|shadow|faded)\b/i.test(String(name));
}

function isGradientObject(object) {
  const meta = object?.kloudy;
  if (meta?.alpha_mesh_image) return true;
  if (!meta?.resource_family || !meta?.resource_index) return false;
  return isGradientResource({
    family: meta.resource_family,
    index: Number(meta.resource_index),
    shapeWord: Number(meta.type_word),
  });
}

function applyObjectColor(object, color, options = {}) {
  if (!object) return;
  const normalized = normalizeColor(color);
  const hex = colorToHex(normalized);
  if (object.kloudy?.mask) {
    object.kloudy.maskOriginalColor = normalized.slice();
    object.set({ fill: hex, opacity: normalized[3] / 255 });
    applyMaskVisual(object, { deferPreview: true });
    return;
  }
  object.set({ fill: hex, opacity: normalized[3] / 255 });
  if (isGradientObject(object) && fabric?.Image?.filters?.BlendColor) {
    if (options.deferImageFilter) {
      object.__kloudyPendingTint = normalized.slice();
      if (hybridRenderActive && canvas) requestHybridRender();
      return;
    }
    object.filters = [new fabric.Image.filters.BlendColor({
      color: hex,
      mode: "tint",
      alpha: 1,
    })];
    object.applyFilters();
    object.__kloudyPendingTint = null;
  }
  if (hybridRenderActive && canvas) {
    requestHybridRender();
  }
}

function shouldUseObjectPixelTargetFind(object, enabled = $("boxVisibleOnly")?.checked ?? true) {
  if (!enabled) return false;
  const complexity = Number(object?.kloudy?.render_complexity);
  return !(Number.isFinite(complexity) && complexity <= 8);
}

function applyObjectHitTestMode(object, enabled = $("boxVisibleOnly")?.checked ?? true) {
  if (!object?.kloudy || object.kloudyGuide) return;
  if (object.kloudy.mask) {
    object.set({
      perPixelTargetFind: false,
      targetFindTolerance: 12,
    });
    return;
  }
  const perPixel = shouldUseObjectPixelTargetFind(object, enabled);
  object.set({
    perPixelTargetFind: perPixel,
    targetFindTolerance: perPixel ? VINYL_HIT_TOLERANCE : 0,
  });
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
  const shapeLuminance = colorLuminance(rgb);
  const bgLuminance = colorLuminance(rgbFromCssColor(cssColorVar("--fabric-canvas-bg", "#fffefe")));
  const opacity = Math.max(0, Math.min(1, Number(object?.opacity ?? 1)));
  const useBrightOutline = opacity < 0.3 ? bgLuminance < 0.48 : shapeLuminance < 0.18;
  return {
    color: useBrightOutline ? "rgba(255, 255, 255, 0.98)" : "rgba(18, 12, 18, 0.92)",
    blur: useBrightOutline ? 13 : 10,
  };
}

function cloneFabricPathData(pathData) {
  return Array.isArray(pathData)
    ? pathData.map((segment) => (Array.isArray(segment) ? segment.slice() : segment))
    : pathData;
}

function isNativeTrianglePath(pathData) {
  return Array.isArray(pathData) && pathData.length > 0 && pathData.length % 4 === 0
    && pathData.every((part, index) => part[0] === "MLLZ"[index % 4]
      && (index % 4 === 3 || (Number.isFinite(part[1]) && Number.isFinite(part[2]))));
}

function renderNativeTriangleFill(ctx) {
  if (this.hasStroke()) return fabric.Path.prototype._renderPathCommands.call(this, ctx);
  const ox = -this.pathOffset.x;
  const oy = -this.pathOffset.y;
  ctx.beginPath();
  // Fill closes triangles implicitly; explicit closes dominate large native mesh redraws.
  for (const part of this.path) {
    if (part[0] === "M") ctx.moveTo(part[1] + ox, part[2] + oy);
    else if (part[0] === "L") ctx.lineTo(part[1] + ox, part[2] + oy);
  }
}

function makeCachedFabricPath(pathText, options = {}, cacheKey = null) {
  if (cacheKey && typeof pathText === "string" && fabric?.util?.parsePath) {
    let pathData = fabricPathDataCache.get(cacheKey);
    if (!pathData) {
      pathData = fabric.util.parsePath(pathText);
      pathData.kloudyTriangleFill = isNativeTrianglePath(pathData);
      if (pathData.kloudyTriangleFill) {
        pathData.forEach(Object.freeze);
        Object.freeze(pathData);
      }
      fabricPathDataCache.set(cacheKey, pathData);
    }
    if (pathData.kloudyTriangleFill) {
      // Native commands are immutable. Fabric owns each object's bounds and transforms.
      const object = new fabric.Path("M 0 0", options);
      object.path = pathData;
      fabric.Polyline.prototype._setPositionDimensions.call(object, options);
      object._renderPathCommands = renderNativeTriangleFill;
      return object;
    }
    const object = new fabric.Path(cloneFabricPathData(pathData), options);
    return object;
  }
  return new fabric.Path(pathText, options);
}

function objectPathCacheKey(object, kind) {
  const meta = object?.kloudy || {};
  return `${kind}:${meta.resource_family || ""}:${meta.resource_index || ""}:${meta.type || ""}`;
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

function selectionOutlineResourceForObject(object) {
  const meta = object?.kloudy;
  if (!meta?.resource_family || !meta?.resource_index) return null;
  return {
    family: String(meta.resource_family),
    index: Number(meta.resource_index),
    typeCode: Number(meta.type),
    shapeWord: Number(meta.type_word ?? (Number(meta.type) & 0xffff)),
  };
}

function needsLazySelectionOutline(object) {
  const meta = object?.kloudy;
  return Boolean(meta?.mesh_path && !meta.outline_path && !meta.outline_path_failed && selectionOutlineResourceForObject(object));
}

function refreshSelectionOutlineHelperForObject(object) {
  if (!canvas || !object) return;
  const helper = selectedShapeOutlineHelpers.get(object);
  if (helper) {
    canvas.remove(helper);
    selectedShapeOutlineHelpers.delete(object);
  }
  const selected = selectedVinylObjects();
  if (selected.length === 1 && selected[0] === object) {
    syncSelectionOutlineHelpers(new Set([object]));
    requestCanvasRender();
  }
}

function ensureSelectionOutlinePath(object) {
  if (!needsLazySelectionOutline(object)) return;
  const resolved = selectionOutlineResourceForObject(object);
  const cacheKey = resourceCacheKey(resolved);
  if (selectionOutlinePathPromises.has(cacheKey)) return;
  const promise = loadResourceOutlinePathForResolved(resolved)
    .then((outlinePath) => {
      vinylObjects().forEach((candidate) => {
        const meta = candidate?.kloudy;
        if (
          meta?.resource_family === resolved.family
          && Number(meta.resource_index) === Number(resolved.index)
          && Number(meta.type) === Number(resolved.typeCode)
        ) {
          meta.outline_path = outlinePath || "";
          meta.outline_path_failed = !outlinePath;
        }
      });
      const selected = selectedVinylObjects();
      refreshSelectionOutlineHelperForObject(selected.length === 1 ? selected[0] : object);
    })
    .catch((err) => {
      console.warn(KfpsI18n.t("Selection outline load failed."), err);
      object.kloudy.outline_path_failed = true;
      refreshSelectionOutlineHelperForObject(object);
    })
    .finally(() => selectionOutlinePathPromises.delete(cacheKey));
  selectionOutlinePathPromises.set(cacheKey, promise);
}

function makeSelectionOutlineHelper(object) {
  const usesResourcePath = Boolean(object?.kloudy?.outline_path);
  const helper = usesResourcePath
    ? makeCachedFabricPath(object.kloudy.outline_path, { originX: "center", originY: "center" }, objectPathCacheKey(object, "selection-outline"))
    : new fabric.Rect({
      originX: "center",
      originY: "center",
      width: Math.max(1, Number(object?.width) || 1),
      height: Math.max(1, Number(object?.height) || 1),
    });
  const clipPath = usesResourcePath && object?.kloudy?.mesh_path
    ? makeCachedFabricPath(object.kloudy.mesh_path, { originX: "center", originY: "center" }, objectPathCacheKey(object, "selection-clip"))
    : null;
  if (clipPath) {
    clipPath.set({
      fill: "#000",
      stroke: null,
      strokeWidth: 0,
      selectable: false,
      evented: false,
      objectCaching: false,
    });
  }
  helper.set({
    fill: "rgba(0,0,0,0)",
    opacity: 1,
    stroke: selectedShapeHalo(object).color,
    strokeWidth: 1,
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
  helper.kloudySelectionOutlineUsesResourcePath = usesResourcePath;
  return helper;
}

function selectionOutlineScaledValue(objectScale, scaleBasis = 1) {
  const scale = Number(objectScale) || 1;
  const sign = scale < 0 ? -1 : 1;
  const basis = Math.max(0.000001, Math.abs(Number(scaleBasis) || 1));
  const absoluteScale = Math.max(0.000001, Math.abs(scale) / basis);
  // The selected rim is clipped by the shape itself, so it must not be expanded.
  return sign * absoluteScale;
}

function selectionOutlineStrokeWidthForZoom(zoom = canvas?.getZoom?.() || 1) {
  return SELECTION_OUTLINE_SCREEN_WIDTH / Math.max(0.001, Number(zoom) || 1);
}

function syncSelectionOutlineHelper(object, helper) {
  if (!object || !helper) return;
  const zoom = Math.max(0.001, canvas?.getZoom?.() || 1);
  const strokeWidth = selectionOutlineStrokeWidthForZoom(zoom);
  const scaleBasis = helper.kloudySelectionOutlineUsesResourcePath
    ? Math.max(0.000001, Number(object?.kloudy?.render_scale) || 1)
    : 1;
  helper.set({
    left: object.left,
    top: object.top,
    scaleX: selectionOutlineScaledValue(object.scaleX, scaleBasis),
    scaleY: selectionOutlineScaledValue(object.scaleY, scaleBasis),
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
  const canvasObjects = new Set(canvas.getObjects());
  selectedSet = new Set([...selectedSet].filter((object) => canvasObjects.has(object)));
  // Older layer-order operations could reinsert helpers after their map entry
  // was removed. Sweep those too, including when reopening a project in-place.
  canvasObjects.forEach((helper) => {
    if (helper.kloudySelectionOutlineHelper
      && selectedShapeOutlineHelpers.get(helper.kloudySelectionOutlineOwner) !== helper) {
      canvas.remove(helper);
    }
  });
  selectedShapeOutlineHelpers.forEach((helper, object) => {
    if (!selectedSet.has(object)) {
      selectedShapeOutlineHelpers.delete(object);
      canvas.remove(helper);
    }
  });
  selectedSet.forEach((object) => {
    if (needsLazySelectionOutline(object)) {
      ensureSelectionOutlinePath(object);
      return;
    }
    let helper = selectedShapeOutlineHelpers.get(object);
    if (!helper) {
      helper = makeSelectionOutlineHelper(object);
      selectedShapeOutlineHelpers.set(object, helper);
      canvas.add(helper);
    }
    syncSelectionOutlineHelper(object, helper);
    const objectIndex = canvas.getObjects().indexOf(object);
    if (objectIndex >= 0) KfpsFabricAdapter.moveObjectTo(canvas, helper, objectIndex + 1);
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
  const target = interactiveVinylTarget(transform.target);
  if (!target?.kloudy && !isActiveSelectionObject(target)) {
    return eventData?.shiftKey
      ? fabric.controlsUtils.skewHandlerX(eventData, transform, x, y)
      : fabric.controlsUtils.scalingEqually(eventData, transform, x, y);
  }
  const mode = eventData?.shiftKey ? "skewX" : "scale";
  const object = transform.target;
  const centered = Boolean(object.centeredScaling || object.canvas?.centeredScaling)
    !== Boolean(eventData?.[object.canvas?.centeredKey || "altKey"]);
  let start = transform.kloudyCornerGesture;
  if (!start || start.mode !== mode || start.centered !== centered) {
    // Handles are deliberately drawn outside the geometry. Rebase from the
    // grabbed pointer, never from that absolute position or an old gesture mode.
    const previous = start;
    start = transform.kloudyCornerGesture = {
      mode, centered,
      pointerX: previous?.lastX ?? transform.ex, pointerY: previous?.lastY ?? transform.ey,
      matrix: object.calcOwnMatrix().slice(),
      scaleX: object.scaleX, scaleY: object.scaleY,
      skewX: Math.tan(fabric.util.degreesToRadians(object.skewX || 0)),
      skewY: Math.tan(fabric.util.degreesToRadians(object.skewY || 0)),
      flipX: object.flipX, flipY: object.flipY, angle: object.angle || 0,
    };
  }
  start.lastX = x;
  start.lastY = y;
  transform.action = mode;
  if (mode === "skewX" ? object.lockSkewingX : (object.lockScalingX || object.lockScalingY)) return false;
  return (mode === "skewX" ? editorCornerSkew : editorCornerScale)(eventData, transform, x, y);
}

function transformCornerFromPointer(_eventData, transform, x, y) {
  const object = transform.target;
  const start = transform.kloudyCornerGesture;
  const dx = x - start.pointerX;
  const dy = y - start.pointerY;
  const before = object.calcOwnMatrix().slice();
  const sideX = (transform.corner.endsWith("r") ? 1 : -1) * (start.flipX ? -1 : 1);
  const sideY = (transform.corner.startsWith("b") ? 1 : -1) * (start.flipY ? -1 : 1);
  const grabbed = new fabric.Point(sideX * object.width / 2, sideY * object.height / 2);
  const anchor = start.centered ? new fabric.Point(0, 0) : new fabric.Point(
    start.mode === "skewX" ? grabbed.x : -grabbed.x, -grabbed.y,
  );
  if (start.mode === "skewX") {
    const angle = fabric.util.degreesToRadians(start.angle);
    const span = start.skewY * (grabbed.x - anchor.x) + grabbed.y - anchor.y;
    const denominator = start.scaleX * (start.flipX ? -1 : 1) * span;
    if (Math.abs(denominator) < 1e-9) return false;
    const increment = (dx * Math.cos(angle) + dy * Math.sin(angle)) / denominator;
    object.set("skewX", fabric.util.radiansToDegrees(Math.atan(start.skewX + increment)));
  } else {
    const direction = fabric.util.transformPoint(grabbed.subtract(anchor), start.matrix, true);
    const lengthSquared = direction.x ** 2 + direction.y ** 2;
    if (lengthSquared < 1e-12) return false;
    let factor = 1 + (dx * direction.x + dy * direction.y) / lengthSquared;
    const minimum = Math.max(0.0001, object.minScaleLimit || 0) / Math.min(start.scaleX, start.scaleY);
    if (object.lockScalingFlip) factor = Math.max(minimum, factor);
    else if (Math.abs(factor) < minimum) factor = factor < 0 ? -minimum : minimum;
    object.set({
      scaleX: start.scaleX * Math.abs(factor), scaleY: start.scaleY * Math.abs(factor),
      flipX: start.flipX !== (factor < 0), flipY: start.flipY !== (factor < 0),
    });
  }
  const fixed = fabric.util.transformPoint(anchor, start.matrix);
  const moved = fabric.util.transformPoint(anchor, object.calcOwnMatrix());
  const center = object.getRelativeCenterPoint?.() || object.getCenterPoint();
  object.setPositionByOrigin(new fabric.Point(center.x + fixed.x - moved.x, center.y + fixed.y - moved.y), "center", "center");
  return object.calcOwnMatrix().some((value, index) => Math.abs(value - before[index]) > 1e-9);
}

const editorCornerSkew = fabric.controlsUtils.wrapWithFireEvent("skewing", transformCornerFromPointer);
const editorCornerScale = fabric.controlsUtils.wrapWithFireEvent("scaling", transformCornerFromPointer);

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

function editorSideScaleHandler(axis) {
  const fallback = axis === "x" ? fabric.controlsUtils.scalingX : fabric.controlsUtils.scalingY;
  const resize = fabric.controlsUtils.wrapWithFireEvent("scaling", (eventData, transform, x, y) => {
    const target = transform.target;
    if (axis === "x" ? target.lockScalingX : target.lockScalingY) return false;
    let start = transform.kloudySideResize;
    if (!start) {
      const matrix = target.calcOwnMatrix();
      if (Math.abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) < 1e-12) return false;
      start = transform.kloudySideResize = {
        matrix, inverse: fabric.util.invertTransform(matrix),
        scaleX: target.scaleX, scaleY: target.scaleY,
        skewX: Math.tan(fabric.util.degreesToRadians(target.skewX || 0)),
        skewY: Math.tan(fabric.util.degreesToRadians(target.skewY || 0)),
        flipX: target.flipX, flipY: target.flipY,
        pointer: new fabric.Point(transform.ex, transform.ey),
      };
    }
    const horizontal = axis === "x";
    const dimension = horizontal ? target.width : target.height;
    if (!(dimension > 0)) return false;
    const flipped = horizontal ? start.flipX : start.flipY;
    const side = (["mr", "mb"].includes(transform.corner) ? 1 : -1) * (flipped ? -1 : 1);
    const centered = (horizontal ? transform.originX : transform.originY) === "center";
    const delta = fabric.util.transformPoint(
      new fabric.Point(x - start.pointer.x, y - start.pointer.y), start.inverse, true,
    );
    let factor = 1 + (horizontal ? delta.x : delta.y) * side * (centered ? 2 : 1) / dimension;
    const originalScale = horizontal ? start.scaleX : start.scaleY;
    const minimum = Math.max(0.0001, target.minScaleLimit || 0) / originalScale;
    if (target.lockScalingFlip) factor = Math.max(minimum, factor);
    else if (Math.abs(factor) < minimum) factor = factor < 0 ? -minimum : minimum;
    const fx = horizontal ? factor : 1;
    const fy = horizontal ? 1 : factor;
    const anchor = new fabric.Point(
      horizontal && !centered ? -side * target.width / 2 : 0,
      !horizontal && !centered ? -side * target.height / 2 : 0,
    );
    const fixed = fabric.util.transformPoint(anchor, start.matrix);
    const before = target.calcOwnMatrix().slice();
    // Resize in the shape's basis, not the enclosing box: keep both edge
    // directions while changing one extent, including mirrored/skewed shapes.
    target.set({
      scaleX: start.scaleX * Math.abs(fx), scaleY: start.scaleY * Math.abs(fy),
      flipX: start.flipX !== (fx < 0), flipY: start.flipY !== (fy < 0),
      skewX: fabric.util.radiansToDegrees(Math.atan(start.skewX * fy / fx)),
      skewY: fabric.util.radiansToDegrees(Math.atan(start.skewY * fx / fy)),
    });
    const moved = fabric.util.transformPoint(anchor, target.calcOwnMatrix());
    const center = target.getRelativeCenterPoint?.() || target.getCenterPoint();
    target.setPositionByOrigin(new fabric.Point(center.x + fixed.x - moved.x, center.y + fixed.y - moved.y), "center", "center");
    return target.calcOwnMatrix().some((value, index) => Math.abs(value - before[index]) > 1e-9);
  });
  return (eventData, transform, x, y) => {
    const target = interactiveVinylTarget(transform.target);
    return target?.kloudy || isActiveSelectionObject(target)
      ? resize(eventData, transform, x, y)
      : fallback(eventData, transform, x, y);
  };
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
    actionHandler: editorSideScaleHandler("x"),
    actionName: "scaleX",
    render: renderFigmaSideControl("ml"),
  });
  controls.mr = new fabric.Control({
    x: 0.5,
    y: 0,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mr"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: editorSideScaleHandler("x"),
    actionName: "scaleX",
    render: renderFigmaSideControl("mr"),
  });
  controls.mt = new fabric.Control({
    x: 0,
    y: -0.5,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mt"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: editorSideScaleHandler("y"),
    actionName: "scaleY",
    render: renderFigmaSideControl("mt"),
  });
  controls.mb = new fabric.Control({
    x: 0,
    y: 0.5,
    ...generousHitArea,
    positionHandler: figmaControlPositionHandler("mb"),
    cursorStyleHandler: editorSideScaleCursorStyleHandler,
    actionHandler: editorSideScaleHandler("y"),
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

function objectEditorVisible(object) {
  return object?.__kloudyHybridHidden
    ? object.__kloudyHybridOriginalVisible !== false
    : object?.visible !== false;
}

function getLayerStats(force = false) {
  if (!force && layerStatsCache) return layerStatsCache;
  const objects = vinylObjects();
  const visible = objects.filter((obj) => objectEditorVisible(obj) && (obj.opacity ?? 1) > 0).length;
  layerStatsCache = { objects, count: objects.length, visible };
  return layerStatsCache;
}

function updateHud(pointer = null, options = {}) {
  if (!canvas) return;
  if (!options.pointerOnly) {
    const selected = selectedVinylObjects().length;
    const stats = getLayerStats(Boolean(options.forceStats));
    const zoom = `${Math.round((canvas.getZoom() || 1) * 100)}%`;
    const layerText = KfpsI18n.t("{0} layer{1}", stats.count, stats.count === 1 ? "" : "s");
    const selectionText = selected ? KfpsI18n.t("{0} selected", selected) : KfpsI18n.t("No layer selected");
    setText("selectedCount", String(selected));
    setText("visibleCount", String(stats.visible));
    setText("zoomValue", zoom);
    setText("hudLayers", layerText);
    setText("hudMode", currentHudMode(selected));
    setText("bottomZoom", zoom);
    setText("bottomLayers", layerText);
    setText("contextSelection", selectionText);
    setText("exportLayerCount", String(stats.count));
    setText("layerLimitMeter", `${stats.count} / ${MAX_VINYL_LAYERS}`);
    setHidden("emptyCanvasHint", stats.count > 0 || Boolean(overlayImage));
  }
  if (pointer) {
    const coords = `x ${round(pointer.x)}, y ${round(-pointer.y)}`;
    setText("hudCoords", coords);
    setText("bottomCoords", coords);
  }
}

function currentHudMode(selectedCount = 0) {
  if (shapeEyedropperActive || activeToolMode === "dropper") return KfpsI18n.t("Eyedropper");
  if (activeToolMode === "guides") return selectedGuideId ? KfpsI18n.t("Guide selected") : KfpsI18n.t("Draw guides");
  if (activeToolMode === "source") return overlayImage ? KfpsI18n.t("Move reference image") : KfpsI18n.t("Move Reference - no image");
  if (activeToolMode === "shapeLibrary") return KfpsI18n.t("Place from library");
  if (activeToolMode === "text") return KfpsI18n.t("Build native text");
  if (activeToolMode === "pixelArt") return KfpsI18n.t("Build pixel art");
  if (activeToolMode === "overlay") return KfpsI18n.t("Reference controls");
  return selectedCount ? KfpsI18n.t("Edit selected") : KfpsI18n.t("Select / box-select");
}

function setHoverHud(target) {
  if (!$("hudHover")) return;
  if (target?.kloudy) {
    $("hudHover").textContent = KfpsI18n.t("over {0}", target.kloudy.name || localizedTypeLabel(target.kloudy.type));
  } else {
    $("hudHover").textContent = KfpsI18n.t("over nothing");
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
  const message = KfpsI18n.error(err && err.stack ? err.stack : (err && err.message ? err.message : String(err)));
  console.error(prefix, err);
  clearBusy(`${prefix}: ${message.split("\n")[0]}`);
  showEditorMessage(prefix, message);
}

function scheduleCanvasResize() {
  requestAnimationFrame(() => {
    if (canvas) resizeCanvas();
  });
}

function showEditorMessage(title, message) {
  const dialog = $("messageDialog");
  setText("messageDialogTitle", title || KfpsI18n.t("Editor message"));
  setText("messageDialogBody", String(message || ""));
  if (!dialog) return;
  try {
    if (dialog.open) dialog.close();
    dialog.showModal();
  } catch (_err) {
    dialog.setAttribute("open", "");
  }
}

function requestTextInput(title, label, value = "", description = "") {
  const dialog = $("textPromptDialog");
  const input = $("textPromptInput");
  if (!dialog || !input) return Promise.resolve(null);
  if (textPromptResolver) {
    textPromptResolver(null);
    textPromptResolver = null;
  }
  setText("textPromptTitle", title || KfpsI18n.t("Enter a name"));
  setText("textPromptLabel", label || KfpsI18n.t("Name"));
  setText("textPromptDescription", description || "");
  input.value = String(value || "");
  return new Promise((resolve) => {
    textPromptResolver = resolve;
    try {
      if (dialog.open) dialog.close();
      dialog.showModal();
    } catch (_err) {
      dialog.setAttribute("open", "");
    }
    requestAnimationFrame(() => {
      input.focus();
      input.select();
    });
  });
}

function finishTextPrompt(value) {
  const resolver = textPromptResolver;
  textPromptResolver = null;
  if (resolver) resolver(value);
}

function finishConfirmation(value) {
  const resolver = confirmationResolver;
  confirmationResolver = null;
  if (resolver) resolver(Boolean(value));
}

function requestConfirmation(title, body, confirmLabel = KfpsI18n.t("Continue")) {
  const dialog = $("confirmationDialog");
  if (!dialog) return Promise.resolve(false);
  if (confirmationResolver) finishConfirmation(false);
  if (dialog.open) dialog.close();
  setText("confirmationDialogTitle", String(title || KfpsI18n.t("Continue?")));
  setText("confirmationDialogBody", String(body || ""));
  setText("confirmationDialogConfirm", String(confirmLabel || KfpsI18n.t("Continue")));
  return new Promise((resolve) => {
    confirmationResolver = resolve;
    try {
      dialog.showModal();
    } catch (_err) {
      dialog.setAttribute("open", "");
    }
  });
}

async function confirmWorkspaceReplacement(nextDocument) {
  if (!documentDirty) return true;
  return requestConfirmation(
    KfpsI18n.t("Unsaved editor changes"),
    KfpsI18n.t("Opening {0} replaces the current workspace. Save the project first if these changes should be kept.", nextDocument || KfpsI18n.t("another document")),
    KfpsI18n.t("Open Anyway"),
  );
}

async function startBlankCanvas() {
  if (!await confirmWorkspaceReplacement(KfpsI18n.t("a new blank canvas"))) {
    setStatus(KfpsI18n.t("Current unsaved work was kept."));
    return;
  }
  clearVinylObjects();
  clearSourceOverlayState();
  applySavedGuideState(null);
  overlayRevision = 0;
  savedOverlayRevision = 0;
  loadedName = "untitled";
  currentProjectName = null;
  resetHistory();
  ensureHistoryBaseline();
  clearAutosave();
  canvas.discardActiveObject();
  resetView();
  refreshLayers();
  updateSelectionPanel();
  refreshExportValidation();
  clearBusy(KfpsI18n.t("Blank canvas ready. Open Shapes, Text, or Pixel to begin."));
}

function nextFrame() {
  return new Promise((resolve) => {
    let frame;
    const done = () => { clearTimeout(timer); cancelAnimationFrame(frame); resolve(); };
    const timer = setTimeout(done, 100);
    frame = requestAnimationFrame(done);
  });
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
    const saved = JSON.parse(editorSettings.getItem("kloudyFabricFavoriteColors") || "[]");
    if (!Array.isArray(saved)) return [];
    return saved.map((color) => color ? normalizeColor(color) : null).slice(0, FAVORITE_COLOR_SLOTS);
  } catch (_err) {
    return [];
  }
}

function loadFavoriteShapes() {
  try {
    const saved = JSON.parse(editorSettings.getItem("kloudyFabricFavorites") || "[]");
    return new Set(Array.isArray(saved) ? saved.map(String) : []);
  } catch (_err) {
    return new Set();
  }
}

function loadLastFontShapeTransform() {
  try {
    const saved = JSON.parse(editorSettings.getItem("kloudyFabricLastFontShapeTransform") || "null");
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
  editorSettings.setItem("kloudyFabricLastFontShapeTransform", JSON.stringify(lastFontShapeTransform));
}

function saveFavoriteColors() {
  editorSettings.setItem("kloudyFabricFavoriteColors", JSON.stringify(favoriteColors));
}

function activateDockPanel(panelId) {
  if (panelId === "assetsPane") editorAssetLibrary?.refresh();
  if (panelId === "layersPane") {
    setDockVisible(true);
    setLayersCollapsed(false);
    requestAnimationFrame(() => renderVirtualLayerWindow(true));
    return;
  }
  const button = document.querySelector(`.dockTab[data-panel="${panelId}"]`);
  if (!button) return;
  setDockVisible(true);
  const group = button.closest(".dockGroup");
  if (!group) return;
  group.querySelectorAll(".dockTab").forEach((tab) => {
    const active = tab === button;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  group.querySelectorAll(".dockPane").forEach((pane) => {
    const active = pane.id === panelId;
    pane.classList.toggle("active", active);
    pane.hidden = !active;
  });
  if (panelId === "layersPane") requestAnimationFrame(() => renderVirtualLayerWindow(true));
}

function readDockState() {
  try {
    const value = JSON.parse(editorSettings.getItem(EDITOR_DOCK_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  } catch (_err) {
    return {};
  }
}

function writeDockState(patch = {}) {
  const current = readDockState();
  editorSettings.setItem(EDITOR_DOCK_KEY, JSON.stringify({ ...current, ...patch }));
}

function setDockVisible(visible, options = {}) {
  const workspace = document.querySelector(".workspace");
  if (!workspace) return;
  workspace.classList.toggle("dockCollapsed", !visible);
  const button = $("toggleRightDock");
  if (button) {
    button.classList.toggle("active", visible);
    button.setAttribute("aria-pressed", String(Boolean(visible)));
  }
  if (options.persist !== false) writeDockState({ hidden: !visible });
  scheduleCanvasResize();
  if (visible) requestAnimationFrame(() => renderVirtualLayerWindow(true));
}

function setLayersCollapsed(collapsed, options = {}) {
  const dock = document.querySelector(".rightDock");
  if (!dock) return;
  dock.classList.toggle("layersCollapsed", Boolean(collapsed));
  const button = $("collapseLayersDock");
  if (button) button.textContent = collapsed ? KfpsI18n.t("Restore") : KfpsI18n.t("Collapse");
  if (options.persist !== false) writeDockState({ layersCollapsed: Boolean(collapsed) });
  scheduleCanvasResize();
}

function restoreDockState() {
  const state = readDockState();
  const layerPercent = Math.max(25, Math.min(68, Number(state.layerPercent) || 44));
  document.querySelector(".editorShell")?.style.setProperty("--editor-layer-height", `${layerPercent}%`);
  setLayersCollapsed(Boolean(state.layersCollapsed), { persist: false });
  setDockVisible(!state.hidden, { persist: false });
}

function bindDockSplitter() {
  const splitter = $("dockSplitter");
  const dock = document.querySelector(".rightDock");
  const shell = document.querySelector(".editorShell");
  if (!splitter || !dock || !shell) return;
  splitter.addEventListener("pointerdown", (event) => {
    if (dock.classList.contains("layersCollapsed")) return;
    event.preventDefault();
    dockResizeState = { pointerId: event.pointerId };
    splitter.setPointerCapture(event.pointerId);
    splitter.classList.add("dragging");
  });
  splitter.addEventListener("pointermove", (event) => {
    if (!dockResizeState || dockResizeState.pointerId !== event.pointerId) return;
    const bounds = dock.getBoundingClientRect();
    if (bounds.height <= 0) return;
    const percent = Math.max(25, Math.min(68, ((event.clientY - bounds.top) / bounds.height) * 100));
    shell.style.setProperty("--editor-layer-height", `${percent}%`);
    dockResizeState.layerPercent = percent;
    scheduleCanvasResize();
  });
  const finish = (event) => {
    if (!dockResizeState || dockResizeState.pointerId !== event.pointerId) return;
    const percent = dockResizeState.layerPercent;
    dockResizeState = null;
    splitter.classList.remove("dragging");
    if (splitter.hasPointerCapture(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
    if (Number.isFinite(percent)) writeDockState({ layerPercent: Math.round(percent * 10) / 10 });
  };
  splitter.addEventListener("pointerup", finish);
  splitter.addEventListener("pointercancel", finish);
}

function setToolRailMode(mode, label = null) {
  if (activeToolMode === "guides" && mode !== "guides") cancelGuideInteraction();
  activeToolMode = mode || "select";
  if (activeToolMode === "guides") endHybridRenderNow();
  document.querySelectorAll(".toolButton").forEach((tool) => {
    const active = tool.dataset.toolMode === activeToolMode;
    tool.classList.toggle("active", active);
    if (!tool.classList.contains("toolActionButton")) tool.setAttribute("aria-pressed", String(active));
  });
  const activeButton = document.querySelector(`.toolButton[data-tool-mode="${activeToolMode}"]`);
  label = label || activeButton?.dataset.tool || KfpsI18n.t("Select / Move");
  setText("activeToolLabel", KfpsI18n.term(label));
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
  if (mode === "select") setStatus(KfpsI18n.t("Select mode. Drag empty canvas to box-select; mouse wheel zooms; middle/right drag pans."));
  if (mode === "shapeLibrary") setStatus(KfpsI18n.t("Shape Library open. Click a shape tile to place it in the current viewport."));
  if (mode === "text") setStatus(KfpsI18n.t("Text builder open. Text is built from editable native Forza letter shapes."));
  if (mode === "pixelArt") setStatus(KfpsI18n.t("Pixel Art builder open. Adjacent same-color pixels are merged to save layers."));
  if (mode === "guides") setStatus(KfpsI18n.t("Guides mode. Click the start and endpoint, or drag. Wheel zooms; middle/right drag or Space pans. Shift snaps to 45 degrees."));
  if (mode === "overlay") setStatus(KfpsI18n.t("Reference controls open. Reference images are editor-only and never exported."));
  if (mode === "source") setStatus(overlayImage ? KfpsI18n.t("Move Reference mode. Drag only the reference image; vinyl layers and guides are ignored. Hold Control to snap it to the grid or guides.") : KfpsI18n.t("Move Reference needs an image first. Add one in Reference controls."));
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
  if (vBoxSelectActive) setText("hudMode", KfpsI18n.t("V box select"));
  else setText("hudMode", currentHudMode(selectedVinylObjects().length));
}

function leaveGuideModeForLayerEdit() {
  if (activeToolMode !== "guides") return;
  guideDraft = null;
  selectedGuideId = null;
  setToolRailMode("select", KfpsI18n.t("Select / Move"));
  renderGuideObjects();
  setStatus(KfpsI18n.t("Guide drawing disengaged. Select mode is active while editing shapes."));
}

function resourceCountForFamilyDefinition(family) {
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
  if (!base) throw new Error(KfpsI18n.t("Unknown shape family: {0}", family));
  if (family.includes("Letters")) return (base + Number(index) - 1) & 0xffff;
  return ((base & 0xffff) + Number(index) - 1) & 0xffff;
}

async function loadResourcePath(typeCode) {
  const resolved = typeCodeToResource(typeCode);
  if (!resolved) throw new Error(KfpsI18n.t("Unsupported FH6 type code: {0}", typeCode));
  return loadResourcePathForResolved(resolved);
}

async function loadResourcePathForResolved(resolved) {
  const cacheKey = resourceCacheKey(resolved);
  if (resourceCache.has(cacheKey)) return resourceCache.get(cacheKey);
  if (resourcePathPromiseCache.has(cacheKey)) return resourcePathPromiseCache.get(cacheKey);
  const pending = (async () => {
    const payload = await loadResourcePayloadForResolved(resolved);
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
  })();
  resourcePathPromiseCache.set(cacheKey, pending);
  try {
    return await pending;
  } catch (err) {
    resourcePathPromiseCache.delete(cacheKey);
    throw err;
  }
}

function resourceCacheKey(resolved) {
  return `${resolved.family}:${resolved.index}:${resolved.typeCode || ""}`;
}

async function loadResourcePayloadForResolved(resolved) {
  const cacheKey = resourceCacheKey(resolved);
  if (resourcePayloadCache.has(cacheKey)) return resourcePayloadCache.get(cacheKey);
  if (resourcePayloadPromiseCache.has(cacheKey)) return resourcePayloadPromiseCache.get(cacheKey);
  const pending = (async () => {
    const url = await resolveVinylResourceUrl(resolved.family, resolved.index, "");
    const response = await fetch(url, { signal: AbortSignal.timeout(30000) });
    if (!response.ok) throw new Error(KfpsI18n.t("Missing shape resource: {0}", url));
    const payload = await response.json();
    resourcePayloadCache.set(cacheKey, payload);
    return payload;
  })();
  resourcePayloadPromiseCache.set(cacheKey, pending);
  try {
    return await pending;
  } catch (err) {
    resourcePayloadPromiseCache.delete(cacheKey);
    throw err;
  }
}

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

async function loadResourceOutlinePathForResolved(resolved) {
  const cacheKey = resourceCacheKey(resolved);
  if (resourceOutlineCache.has(cacheKey)) return resourceOutlineCache.get(cacheKey);
  const payload = await loadResourcePayloadForResolved(resolved);
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

function decodeVertexAlphas(payload, count) {
  const raw = payload?.VerticesAlpha;
  const alphas = new Uint8Array(Math.max(0, Number(count) || 0));
  alphas.fill(255);
  if (typeof raw === "string" && raw.length) {
    try {
      const decoded = atob(raw);
      const limit = Math.min(decoded.length, alphas.length);
      for (let i = 0; i < limit; i += 1) alphas[i] = decoded.charCodeAt(i) & 0xff;
    } catch (_err) {
      // Treat malformed alpha payloads as fully opaque mesh data.
    }
    return alphas;
  }
  if (Array.isArray(raw)) {
    const limit = Math.min(raw.length, alphas.length);
    for (let i = 0; i < limit; i += 1) {
      const value = raw[i];
      const alpha = typeof value === "number"
        ? value
        : (Array.isArray(value) ? value[value.length - 1] : (value?.A ?? value?.Alpha ?? value?.alpha));
      if (Number.isFinite(Number(alpha))) {
        alphas[i] = Math.max(0, Math.min(255, Math.round(Number(alpha))));
      }
    }
  }
  return alphas;
}

function payloadHasPartialAlpha(payload) {
  const vertices = payload?.Vertices || [];
  const alphas = decodeVertexAlphas(payload, vertices.length);
  return alphas.some((alpha) => alpha < 255);
}

function shouldUseAlphaMeshImage(resolved, payload) {
  return Boolean(resolved?.family && ALPHA_MESH_IMAGE_FAMILIES.has(String(resolved.family)) && payloadHasPartialAlpha(payload));
}

function resourceRenderComplexity(payload) {
  const vertices = Array.isArray(payload?.Vertices) ? payload.Vertices.length : 0;
  const triangles = Array.isArray(payload?.Indices) ? Math.floor(payload.Indices.length / 3) : 0;
  return Math.max(vertices, triangles);
}

function resourceVertexBounds(vertices) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const vertex of vertices || []) {
    const x = Number(vertex?.X);
    const y = Number(vertex?.Y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return { minX: -0.5, minY: -0.5, width: 1, height: 1 };
  }
  return {
    minX,
    minY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
  };
}

function alphaMeshRasterMetrics(bounds) {
  const maxDimension = Math.max(bounds.width, bounds.height, 1);
  const targetMax = Math.min(
    ALPHA_MESH_RASTER_MAX_SIZE,
    Math.max(ALPHA_MESH_RASTER_MIN_SIZE, Math.ceil(maxDimension * ALPHA_MESH_RASTER_SCALE)),
  );
  const scale = targetMax / maxDimension;
  return {
    scale,
    width: Math.max(1, Math.ceil(bounds.width * scale)),
    height: Math.max(1, Math.ceil(bounds.height * scale)),
  };
}

function trianglePixelPoints(vertices, indices, offset, bounds, scale) {
  const points = [];
  for (let i = 0; i < 3; i += 1) {
    const vertex = vertices[indices[offset + i]];
    if (!vertex) return null;
    const x = Number(vertex.X);
    const y = Number(vertex.Y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    points.push({
      x: (x - bounds.minX) * scale,
      y: (y - bounds.minY) * scale,
    });
  }
  return points;
}

function addTrianglePath(ctx, points) {
  ctx.moveTo(points[0].x, points[0].y);
  ctx.lineTo(points[1].x, points[1].y);
  ctx.lineTo(points[2].x, points[2].y);
  ctx.closePath();
}

function rasterizeAlphaTriangle(imageData, width, height, points, alphas) {
  const [p0, p1, p2] = points;
  const minX = Math.max(0, Math.floor(Math.min(p0.x, p1.x, p2.x)));
  const maxX = Math.min(width - 1, Math.ceil(Math.max(p0.x, p1.x, p2.x)));
  const minY = Math.max(0, Math.floor(Math.min(p0.y, p1.y, p2.y)));
  const maxY = Math.min(height - 1, Math.ceil(Math.max(p0.y, p1.y, p2.y)));
  const denom = ((p1.y - p2.y) * (p0.x - p2.x)) + ((p2.x - p1.x) * (p0.y - p2.y));
  if (!Number.isFinite(denom) || Math.abs(denom) < 0.00001) return;
  const data = imageData.data;
  for (let y = minY; y <= maxY; y += 1) {
    const py = y + 0.5;
    for (let x = minX; x <= maxX; x += 1) {
      const px = x + 0.5;
      const w0 = (((p1.y - p2.y) * (px - p2.x)) + ((p2.x - p1.x) * (py - p2.y))) / denom;
      const w1 = (((p2.y - p0.y) * (px - p2.x)) + ((p0.x - p2.x) * (py - p2.y))) / denom;
      const w2 = 1 - w0 - w1;
      if (w0 < -0.0001 || w1 < -0.0001 || w2 < -0.0001) continue;
      const alpha = Math.max(0, Math.min(255, Math.round((w0 * alphas[0]) + (w1 * alphas[1]) + (w2 * alphas[2]))));
      if (alpha <= 0) continue;
      const idx = ((y * width) + x) * 4;
      if (alpha <= data[idx + 3]) continue;
      data[idx] = 255;
      data[idx + 1] = 255;
      data[idx + 2] = 255;
      data[idx + 3] = alpha;
    }
  }
}

function renderAlphaMeshImagePayload(payload) {
  const vertices = payload?.Vertices || [];
  const indices = payload?.Indices || [];
  const alphas = decodeVertexAlphas(payload, vertices.length);
  const bounds = resourceVertexBounds(vertices);
  const metrics = alphaMeshRasterMetrics(bounds);
  const element = document.createElement("canvas");
  element.width = metrics.width;
  element.height = metrics.height;
  const ctx = element.getContext("2d", { willReadFrequently: true });
  const partial = [];
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const points = trianglePixelPoints(vertices, indices, i, bounds, metrics.scale);
    if (!points) continue;
    const triAlphas = [
      alphas[indices[i]] ?? 255,
      alphas[indices[i + 1]] ?? 255,
      alphas[indices[i + 2]] ?? 255,
    ];
    const minAlpha = Math.min(...triAlphas);
    const maxAlpha = Math.max(...triAlphas);
    if (maxAlpha <= 0) continue;
    if (minAlpha >= 255) {
      addTrianglePath(ctx, points);
    } else {
      partial.push({ points, alphas: triAlphas });
    }
  }
  ctx.fill();
  if (partial.length) {
    const imageData = ctx.getImageData(0, 0, metrics.width, metrics.height);
    partial.forEach((triangle) => rasterizeAlphaTriangle(imageData, metrics.width, metrics.height, triangle.points, triangle.alphas));
    ctx.putImageData(imageData, 0, 0);
  }
  return {
    element,
    renderScale: 1 / metrics.scale,
  };
}

async function loadAlphaMeshFabricImageForResolved(resolved, payload) {
  const cacheKey = resourceCacheKey(resolved);
  let rendered = alphaMeshImageCache.get(cacheKey);
  if (!rendered) {
    rendered = renderAlphaMeshImagePayload(payload);
    alphaMeshImageCache.set(cacheKey, rendered);
  }
  const image = new fabric.Image(rendered.element);
  image.kloudyRenderScale = rendered.renderScale;
  return image;
}

async function loadFabricImage(url) {
  let pending = fabricImageElementPromiseCache.get(url);
  if (!pending) {
    pending = new Promise((resolve, reject) => {
      const element = new Image();
      element.crossOrigin = "anonymous";
      const finish = (error) => {
        clearTimeout(timer);
        element.onload = element.onerror = null;
        if (error) { element.src = ""; reject(error); }
        else resolve(element);
      };
      const timer = setTimeout(() => finish(new Error(KfpsI18n.t("Failed to load image resource: {0}", url))), 30000);
      element.onload = () => finish();
      element.onerror = () => finish(new Error(KfpsI18n.t("Failed to load image resource: {0}", url)));
      element.src = url;
    });
    fabricImageElementPromiseCache.set(url, pending);
  }
  try {
    return new fabric.Image(await pending);
  } catch (err) {
    fabricImageElementPromiseCache.delete(url);
    throw err;
  }
}

function compileHybridShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const message = gl.getShaderInfoLog(shader) || KfpsI18n.t("unknown shader error");
    gl.deleteShader(shader);
    throw new Error(KfpsI18n.error(message));
  }
  return shader;
}

function createHybridProgram(gl) {
  const vertex = compileHybridShader(gl, gl.VERTEX_SHADER, `
    attribute vec2 a_position;
    attribute float a_alpha;
    uniform mat3 u_world;
    uniform mat3 u_view;
    uniform vec2 u_resolution;
    varying float v_alpha;
    void main() {
      vec3 world = u_world * vec3(a_position, 1.0);
      vec3 screen = u_view * world;
      vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
      gl_Position = vec4(clip, 0.0, 1.0);
      v_alpha = a_alpha;
    }
  `);
  const fragment = compileHybridShader(gl, gl.FRAGMENT_SHADER, `
    precision mediump float;
    uniform vec4 u_color;
    varying float v_alpha;
    void main() {
      gl_FragColor = vec4(u_color.rgb, u_color.a * v_alpha);
    }
  `);
  const program = gl.createProgram();
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program) || KfpsI18n.t("unknown program error");
    gl.deleteProgram(program);
    throw new Error(KfpsI18n.error(message));
  }
  return {
    program,
    attributes: {
      position: gl.getAttribLocation(program, "a_position"),
      alpha: gl.getAttribLocation(program, "a_alpha"),
    },
    uniforms: {
      world: gl.getUniformLocation(program, "u_world"),
      view: gl.getUniformLocation(program, "u_view"),
      resolution: gl.getUniformLocation(program, "u_resolution"),
      color: gl.getUniformLocation(program, "u_color"),
    },
  };
}

function createHybridTextureProgram(gl) {
  const vertex = compileHybridShader(gl, gl.VERTEX_SHADER, `
    attribute vec2 a_position;
    attribute vec2 a_texcoord;
    uniform mat3 u_world;
    uniform mat3 u_view;
    uniform vec2 u_resolution;
    uniform vec2 u_size;
    varying vec2 v_texcoord;
    void main() {
      vec2 local = a_position * u_size;
      vec3 world = u_world * vec3(local, 1.0);
      vec3 screen = u_view * world;
      vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
      gl_Position = vec4(clip, 0.0, 1.0);
      v_texcoord = a_texcoord;
    }
  `);
  const fragment = compileHybridShader(gl, gl.FRAGMENT_SHADER, `
    precision mediump float;
    uniform sampler2D u_texture;
    uniform float u_opacity;
    varying vec2 v_texcoord;
    void main() {
      vec4 sampled = texture2D(u_texture, v_texcoord);
      gl_FragColor = vec4(sampled.rgb, sampled.a * u_opacity);
    }
  `);
  const program = gl.createProgram();
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program) || KfpsI18n.t("unknown texture shader error");
    gl.deleteProgram(program);
    throw new Error(KfpsI18n.error(message));
  }
  return {
    program,
    attributes: {
      position: gl.getAttribLocation(program, "a_position"),
      texcoord: gl.getAttribLocation(program, "a_texcoord"),
    },
    uniforms: {
      world: gl.getUniformLocation(program, "u_world"),
      view: gl.getUniformLocation(program, "u_view"),
      resolution: gl.getUniformLocation(program, "u_resolution"),
      size: gl.getUniformLocation(program, "u_size"),
      texture: gl.getUniformLocation(program, "u_texture"),
      opacity: gl.getUniformLocation(program, "u_opacity"),
    },
  };
}

function createHybridInstancedProgram(gl) {
  const vertex = compileHybridShader(gl, gl.VERTEX_SHADER, `
    attribute vec2 a_position;
    attribute float a_alpha;
    attribute vec3 a_world0;
    attribute vec3 a_world1;
    attribute vec3 a_world2;
    attribute vec4 a_color;
    uniform mat3 u_view;
    uniform vec2 u_resolution;
    varying float v_alpha;
    varying vec4 v_color;
    void main() {
      mat3 world_matrix = mat3(a_world0, a_world1, a_world2);
      vec3 world = world_matrix * vec3(a_position, 1.0);
      vec3 screen = u_view * world;
      vec2 clip = vec2((screen.x / u_resolution.x) * 2.0 - 1.0, 1.0 - (screen.y / u_resolution.y) * 2.0);
      gl_Position = vec4(clip, 0.0, 1.0);
      v_alpha = a_alpha;
      v_color = a_color;
    }
  `);
  const fragment = compileHybridShader(gl, gl.FRAGMENT_SHADER, `
    precision mediump float;
    varying float v_alpha;
    varying vec4 v_color;
    void main() {
      gl_FragColor = vec4(v_color.rgb, v_color.a * v_alpha);
    }
  `);
  const program = gl.createProgram();
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const message = gl.getProgramInfoLog(program) || KfpsI18n.t("unknown instanced shader error");
    gl.deleteProgram(program);
    throw new Error(KfpsI18n.error(message));
  }
  return {
    program,
    attributes: {
      position: gl.getAttribLocation(program, "a_position"),
      alpha: gl.getAttribLocation(program, "a_alpha"),
      world0: gl.getAttribLocation(program, "a_world0"),
      world1: gl.getAttribLocation(program, "a_world1"),
      world2: gl.getAttribLocation(program, "a_world2"),
      color: gl.getAttribLocation(program, "a_color"),
    },
    uniforms: {
      view: gl.getUniformLocation(program, "u_view"),
      resolution: gl.getUniformLocation(program, "u_resolution"),
    },
  };
}

function initHybridRenderer() {
  if (hybridRenderer || hybridDisabledReason) return hybridRenderer;
  const element = $("hybridRenderCanvas");
  if (!element) {
    hybridDisabledReason = KfpsI18n.t("missing canvas");
    return null;
  }
  if (!element.__kloudyContextListeners) {
    element.__kloudyContextListeners = true;
    element.addEventListener("webglcontextlost", (event) => {
      window.KfpsEditorDiagnostics?.record("webgl-lost");
      event.preventDefault();
      endHybridRenderNow();
      if (hybridRenderFrame) cancelAnimationFrame(hybridRenderFrame);
      hybridRenderFrame = null;
      releaseHybridOverlay();
      hybridMeshCache.clear();
      hybridRenderer = null;
      hybridDisabledReason = "WebGL context lost";
      element.hidden = true;
      canvas?.requestRenderAll?.();
    });
    element.addEventListener("webglcontextrestored", () => {
      window.KfpsEditorDiagnostics?.record("webgl-restored");
      hybridDisabledReason = "";
      initHybridRenderer();
      canvas?.requestRenderAll?.();
    });
  }
  const gl = element.getContext("webgl", {
    alpha: true,
    antialias: true,
    depth: false,
    stencil: false,
    preserveDrawingBuffer: true,
  });
  if (!gl) {
    window.KfpsEditorDiagnostics?.record("preview-fallback", { code: 0 });
    hybridDisabledReason = KfpsI18n.t("WebGL unavailable");
    return null;
  }
  try {
    const program = createHybridProgram(gl);
    const textureProgram = createHybridTextureProgram(gl);
    const instancedExtension = gl.getExtension("ANGLE_instanced_arrays");
    const instancedProgram = instancedExtension ? createHybridInstancedProgram(gl) : null;
    const overlayBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, overlayBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -0.5, -0.5, 0, 0,
       0.5, -0.5, 1, 0,
      -0.5,  0.5, 0, 1,
      -0.5,  0.5, 0, 1,
       0.5, -0.5, 1, 0,
       0.5,  0.5, 1, 1,
    ]), gl.STATIC_DRAW);
    const overlayTexture = gl.createTexture();
    const instanceBuffer = instancedExtension ? gl.createBuffer() : null;
    gl.useProgram(program.program);
    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    hybridRenderer = {
      element,
      gl,
      ...program,
      viewMatrix: new Float32Array(9),
      overlay: {
        ...textureProgram,
        buffer: overlayBuffer,
        texture: overlayTexture,
        source: null,
      },
      instanced: instancedExtension && instancedProgram ? {
        ...instancedProgram,
        extension: instancedExtension,
        buffer: instanceBuffer,
        data: new Float32Array(MAX_VINYL_LAYERS * 13),
      } : null,
      pipelineWarmed: false,
    };
  } catch (err) {
    hybridDisabledReason = err?.message || String(err);
    window.KfpsEditorDiagnostics?.record("preview-fallback", { code: 1 });
    console.warn(KfpsI18n.t("Hybrid renderer disabled."), err);
    hybridRenderer = null;
  }
  return hybridRenderer;
}

function resizeHybridRenderer() {
  const renderer = initHybridRenderer();
  if (!renderer || !canvas || renderer.gl.isContextLost()) return false;
  const width = Math.max(1, Number(canvas.width) || 1);
  const height = Math.max(1, Number(canvas.height) || 1);
  if (renderer.element.width !== width || renderer.element.height !== height) {
    renderer.element.width = width;
    renderer.element.height = height;
  }
  renderer.gl.viewport(0, 0, width, height);
  return true;
}

function pointFromPayloadVertex(vertex) {
  if (Array.isArray(vertex)) {
    return {
      x: Number(vertex[0]),
      y: Number(vertex[1]),
      alpha: Number.isFinite(Number(vertex[2])) ? Math.max(0, Math.min(1, Number(vertex[2]))) : 1,
    };
  }
  return {
    x: Number(vertex?.X ?? vertex?.x),
    y: Number(vertex?.Y ?? vertex?.y),
    alpha: Number.isFinite(Number(vertex?.A ?? vertex?.Alpha ?? vertex?.alpha))
      ? Math.max(0, Math.min(1, Number(vertex?.A ?? vertex?.Alpha ?? vertex?.alpha) / 255))
      : 1,
  };
}

function payloadTriangleIndices(indices) {
  if (!Array.isArray(indices)) return [];
  if (indices.length && Array.isArray(indices[0])) return indices.flat();
  return indices;
}

function hybridResourceKeyFromObject(object) {
  const meta = object?.kloudy;
  if (!meta?.resource_family || !meta?.resource_index) return null;
  return `${meta.resource_family}:${Number(meta.resource_index)}:${Number(meta.type) || ""}`;
}

function hybridResolvedFromObject(object) {
  const meta = object?.kloudy;
  if (!meta?.resource_family || !meta?.resource_index) return null;
  return {
    family: String(meta.resource_family),
    index: Number(meta.resource_index),
    typeCode: Number(meta.type),
    shapeWord: Number(meta.type_word ?? (Number(meta.type) & 0xffff)),
  };
}

function hybridMeshForObject(object) {
  const renderer = initHybridRenderer();
  const key = hybridResourceKeyFromObject(object);
  if (!renderer || !key) return null;
  if (hybridMeshCache.has(key)) return hybridMeshCache.get(key);
  const resolved = hybridResolvedFromObject(object);
  const payload = resolved ? resourcePayloadCache.get(resourceCacheKey(resolved)) : null;
  const vertices = payload?.Vertices || payload?.vertices || [];
  const rawIndices = payload?.Indices || payload?.indices || payload?.triangles || [];
  if (!vertices.length || !rawIndices.length) return null;
  // Some opaque resources contain vertex-alpha bytes that the normal Fabric
  // path renderer intentionally ignores. Honor them only for resources that
  // use the editor's gradient/alpha-mesh rendering path.
  const usesVertexAlpha = isGradientObject(object);
  const decodedAlphas = usesVertexAlpha ? decodeVertexAlphas(payload, vertices.length) : null;
  const indices = payloadTriangleIndices(rawIndices);
  const packed = [];
  for (const rawIndex of indices) {
    const index = Number(rawIndex);
    const point = pointFromPayloadVertex(vertices[index]);
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) continue;
    const decoded = decodedAlphas?.[index];
    const alpha = usesVertexAlpha
      ? (decoded === undefined ? point.alpha : Math.max(0, Math.min(1, decoded / 255)))
      : 1;
    packed.push(point.x, point.y, alpha);
  }
  if (packed.length < 9) return null;
  const gl = renderer.gl;
  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(packed), gl.STATIC_DRAW);
  const mesh = { buffer, count: packed.length / 3, usesVertexAlpha };
  hybridMeshCache.set(key, mesh);
  return mesh;
}

function hybridMat3FromFabric(matrix, target = new Float32Array(9)) {
  const m = matrix || [1, 0, 0, 1, 0, 0];
  target[0] = Number(m[0]) || 0;
  target[1] = Number(m[1]) || 0;
  target[2] = 0;
  target[3] = Number(m[2]) || 0;
  target[4] = Number(m[3]) || 0;
  target[5] = 0;
  target[6] = Number(m[4]) || 0;
  target[7] = Number(m[5]) || 0;
  target[8] = 1;
  return target;
}

function hybridObjectColor(object, target = new Float32Array(4)) {
  const source = object.kloudy?.mask && Array.isArray(object.kloudy.maskOriginalColor)
    ? normalizeColor(object.kloudy.maskOriginalColor)
    : hexToRgb(object.fill || "#ffffff", (object.opacity ?? 1) * 255);
  target[0] = Math.max(0, Math.min(1, source[0] / 255));
  target[1] = Math.max(0, Math.min(1, source[1] / 255));
  target[2] = Math.max(0, Math.min(1, source[2] / 255));
  target[3] = Math.max(0, Math.min(1, source[3] / 255));
  return target;
}

function hybridLayerEligible(object) {
  const meta = object?.kloudy;
  return Boolean(
    object
    && meta
    && !object.kloudyGuide
    && !object.kloudyMaskOutline
    && !object.kloudyMaskCutout
    && meta.resource_family
    && objectEditorVisible(object)
    && (meta.mask ? (meta.maskOriginalColor?.[3] ?? 255) > 0 : (object.opacity ?? 1) > 0)
  );
}

function hybridHasUnsupportedLayers(_objects = vinylObjects()) {
  return false;
}

function hybridShouldUse(objects = vinylObjects()) {
  if (hybridDisabledReason) return false;
  if (!objects || objects.length < HYBRID_RENDER_MIN_LAYERS) return false;
  if (hybridHasUnsupportedLayers(objects)) return false;
  return Boolean(initHybridRenderer());
}

async function prewarmHybridMeshesForObjects(objects = vinylObjects()) {
  if (!hybridShouldUse(objects)) return;
  const targets = [];
  const seen = new Set();
  for (const object of objects) {
    if (!hybridLayerEligible(object)) continue;
    const key = hybridResourceKeyFromObject(object);
    if (!key || seen.has(key) || hybridMeshCache.has(key)) continue;
    seen.add(key);
    targets.push(object);
  }
  for (let index = 0; index < targets.length; index += 1) {
    hybridMeshForObject(targets[index]);
    if ((index + 1) % HYBRID_RENDER_PREWARM_CHUNK === 0) {
      await nextFrame();
    }
  }
  if (hybridRenderNow()) {
    // Draw every newly loaded resource set once while load progress is still
    // visible. Drivers can defer buffer specialization as well as shader work.
    if (!hybridRenderer.pipelineWarmed) hybridRenderer.gl.finish();
    hybridRenderer.pipelineWarmed = true;
  }
}

function hybridSetFabricLowerVisible(visible) {
  if (!canvas?.lowerCanvasEl) return;
  if (visible) {
    canvas.lowerCanvasEl.style.visibility = hybridLowerVisibility;
    hybridLowerVisibility = "";
    return;
  }
  if (canvas.lowerCanvasEl.style.visibility !== "hidden") hybridLowerVisibility = canvas.lowerCanvasEl.style.visibility || "";
  canvas.lowerCanvasEl.style.visibility = "hidden";
}

function hideHybridFabricBulkObjects(objects = vinylObjects()) {
  hybridHiddenObjects = [];
  hybridFabricVisibleObjects = new Set();
  // Fabric's lower canvas is hidden during hybrid mode, so object visibility stays intact.
  // That preserves target finding, active selections, and layer visibility while WebGL handles fills.
}

function restoreHybridFabricBulkObjects() {
  hybridHiddenObjects = [];
  hybridFabricVisibleObjects = new Set();
}

function hybridRenderStateForObject(object) {
  const state = object.__kloudyHybridRenderState || {
    world: new Float32Array(9),
    color: new Float32Array(4),
    fill: null,
    opacity: null,
    mask: null,
    maskColor: null,
  };
  hybridMat3FromFabric(object.calcTransformMatrix(), state.world);
  const maskColor = object.kloudy?.maskOriginalColor;
  const colorChanged = state.fill !== object.fill
    || state.opacity !== object.opacity
    || state.mask !== Boolean(object.kloudy?.mask)
    || state.maskColor !== maskColor
    || (Array.isArray(maskColor) && (
      state.maskR !== maskColor[0]
      || state.maskG !== maskColor[1]
      || state.maskB !== maskColor[2]
      || state.maskA !== maskColor[3]
    ));
  if (colorChanged) {
    hybridObjectColor(object, state.color);
    state.fill = object.fill;
    state.opacity = object.opacity;
    state.mask = Boolean(object.kloudy?.mask);
    state.maskColor = maskColor;
    [state.maskR, state.maskG, state.maskB, state.maskA] = Array.isArray(maskColor) ? maskColor : [null, null, null, null];
  }
  object.__kloudyHybridRenderState = state;
  return state;
}

function prepareHybridShapeProgram(renderer, viewMatrix, maskPass) {
  const gl = renderer.gl;
  gl.useProgram(renderer.program);
  gl.uniform2f(renderer.uniforms.resolution, renderer.element.width, renderer.element.height);
  gl.uniformMatrix3fv(renderer.uniforms.view, false, viewMatrix);
  gl.enableVertexAttribArray(renderer.attributes.position);
  gl.enableVertexAttribArray(renderer.attributes.alpha);
  if (maskPass) {
    gl.blendFuncSeparate(gl.ZERO, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE_MINUS_SRC_ALPHA);
  } else {
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }
}

function drawHybridShapePassFallback(renderer, objects, viewMatrix, maskPass) {
  const gl = renderer.gl;
  prepareHybridShapeProgram(renderer, viewMatrix, maskPass);
  let boundBuffer = null;
  for (const object of objects) {
    if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
    const mesh = hybridMeshForObject(object);
    if (!mesh) continue;
    if (mesh.buffer !== boundBuffer) {
      boundBuffer = mesh.buffer;
      gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buffer);
      gl.vertexAttribPointer(renderer.attributes.position, 2, gl.FLOAT, false, 12, 0);
      gl.vertexAttribPointer(renderer.attributes.alpha, 1, gl.FLOAT, false, 12, 8);
    }
    const state = hybridRenderStateForObject(object);
    gl.uniformMatrix3fv(renderer.uniforms.world, false, state.world);
    gl.uniform4fv(renderer.uniforms.color, state.color);
    gl.drawArrays(gl.TRIANGLES, 0, mesh.count);
  }
}

function prepareHybridInstancedProgram(renderer, viewMatrix, maskPass) {
  const gl = renderer.gl;
  const instanced = renderer.instanced;
  gl.useProgram(instanced.program);
  gl.uniform2f(instanced.uniforms.resolution, renderer.element.width, renderer.element.height);
  gl.uniformMatrix3fv(instanced.uniforms.view, false, viewMatrix);
  Object.values(instanced.attributes).forEach((location) => gl.enableVertexAttribArray(location));
  if (maskPass) {
    gl.blendFuncSeparate(gl.ZERO, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE_MINUS_SRC_ALPHA);
  } else {
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }
}

function drawHybridInstancedRun(renderer, mesh, states) {
  if (!mesh || !states.length) return;
  const gl = renderer.gl;
  const instanced = renderer.instanced;
  const extension = instanced.extension;
  const stride = 13;
  states.forEach((state, index) => {
    const offset = index * stride;
    instanced.data.set(state.world, offset);
    instanced.data.set(state.color, offset + 9);
  });
  gl.bindBuffer(gl.ARRAY_BUFFER, mesh.buffer);
  gl.vertexAttribPointer(instanced.attributes.position, 2, gl.FLOAT, false, 12, 0);
  gl.vertexAttribPointer(instanced.attributes.alpha, 1, gl.FLOAT, false, 12, 8);
  extension.vertexAttribDivisorANGLE(instanced.attributes.position, 0);
  extension.vertexAttribDivisorANGLE(instanced.attributes.alpha, 0);

  gl.bindBuffer(gl.ARRAY_BUFFER, instanced.buffer);
  gl.bufferData(gl.ARRAY_BUFFER, instanced.data.subarray(0, states.length * stride), gl.DYNAMIC_DRAW);
  const byteStride = stride * 4;
  gl.vertexAttribPointer(instanced.attributes.world0, 3, gl.FLOAT, false, byteStride, 0);
  gl.vertexAttribPointer(instanced.attributes.world1, 3, gl.FLOAT, false, byteStride, 12);
  gl.vertexAttribPointer(instanced.attributes.world2, 3, gl.FLOAT, false, byteStride, 24);
  gl.vertexAttribPointer(instanced.attributes.color, 4, gl.FLOAT, false, byteStride, 36);
  extension.vertexAttribDivisorANGLE(instanced.attributes.world0, 1);
  extension.vertexAttribDivisorANGLE(instanced.attributes.world1, 1);
  extension.vertexAttribDivisorANGLE(instanced.attributes.world2, 1);
  extension.vertexAttribDivisorANGLE(instanced.attributes.color, 1);
  extension.drawArraysInstancedANGLE(gl.TRIANGLES, 0, mesh.count, states.length);
}

function resetHybridInstancedDivisors(renderer) {
  const instanced = renderer.instanced;
  if (!instanced) return;
  const extension = instanced.extension;
  Object.values(instanced.attributes).forEach((location) => extension.vertexAttribDivisorANGLE(location, 0));
}

function hybridInstancingEffective(objects, maskPass) {
  let eligible = 0;
  let runs = 0;
  let previousMesh = null;
  for (const object of objects) {
    if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
    const mesh = hybridMeshForObject(object);
    if (!mesh) continue;
    eligible += 1;
    if (mesh !== previousMesh) {
      runs += 1;
      previousMesh = mesh;
    }
  }
  return eligible >= 4 && runs <= eligible * 0.65;
}

function drawHybridShapePass(renderer, objects, viewMatrix, maskPass) {
  if (!renderer.instanced || !hybridInstancingEffective(objects, maskPass)) {
    drawHybridShapePassFallback(renderer, objects, viewMatrix, maskPass);
    return;
  }
  prepareHybridInstancedProgram(renderer, viewMatrix, maskPass);
  let activeMesh = null;
  let states = [];
  const flush = () => {
    if (activeMesh && states.length) drawHybridInstancedRun(renderer, activeMesh, states);
    states = [];
  };
  for (const object of objects) {
    if (!hybridLayerEligible(object) || Boolean(object.kloudy?.mask) !== maskPass) continue;
    const mesh = hybridMeshForObject(object);
    if (!mesh) continue;
    if (activeMesh && mesh !== activeMesh) flush();
    activeMesh = mesh;
    states.push(hybridRenderStateForObject(object));
  }
  flush();
  resetHybridInstancedDivisors(renderer);
}

function releaseHybridOverlay() {
  const renderer = hybridRenderer;
  if (!renderer?.overlay) return;
  if (renderer.overlay.texture) renderer.gl.deleteTexture(renderer.overlay.texture);
  renderer.overlay.texture = null;
  renderer.overlay.source = null;
}

function drawHybridOverlay(renderer, viewMatrix) {
  if (!overlayImage || overlayImage.visible === false || (overlayImage.opacity ?? 1) <= 0) return false;
  const source = overlayImage.getElement?.() || overlayImage._element;
  if (!source) return false;
  const gl = renderer.gl;
  const overlay = renderer.overlay;
  if (!overlay.texture) overlay.texture = gl.createTexture();
  gl.useProgram(overlay.program);
  gl.bindBuffer(gl.ARRAY_BUFFER, overlay.buffer);
  gl.enableVertexAttribArray(overlay.attributes.position);
  gl.enableVertexAttribArray(overlay.attributes.texcoord);
  gl.vertexAttribPointer(overlay.attributes.position, 2, gl.FLOAT, false, 16, 0);
  gl.vertexAttribPointer(overlay.attributes.texcoord, 2, gl.FLOAT, false, 16, 8);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_2D, overlay.texture);
  if (overlay.source !== source) {
    let uploadCanvas = null;
    try {
      const width = source.naturalWidth || source.width;
      const height = source.naturalHeight || source.height;
      const limit = gl.getParameter(gl.MAX_TEXTURE_SIZE);
      let uploadSource = source;
      // Only the GPU preview is resized; sampling and project data keep the original.
      if (Math.max(width, height) > limit) {
        const scale = limit / Math.max(width, height);
        uploadCanvas = document.createElement("canvas");
        uploadCanvas.width = Math.max(1, Math.floor(width * scale));
        uploadCanvas.height = Math.max(1, Math.floor(height * scale));
        uploadCanvas.getContext("2d").drawImage(source, 0, 0, uploadCanvas.width, uploadCanvas.height);
        uploadSource = uploadCanvas;
      }
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, uploadSource);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      // Allocation failures set a WebGL error rather than throwing. Check only
      // after uploads, never on every pointer frame (which can stall the GPU).
      const uploadError = gl.getError();
      if (uploadError !== gl.NO_ERROR) throw new Error(`Reference texture upload failed (WebGL ${uploadError}).`);
      overlay.source = source;
    } finally {
      if (uploadCanvas) uploadCanvas.width = uploadCanvas.height = 1;
    }
  }
  hybridMat3FromFabric(overlayImage.calcTransformMatrix(), overlay.world || (overlay.world = new Float32Array(9)));
  gl.uniformMatrix3fv(overlay.uniforms.world, false, overlay.world);
  gl.uniformMatrix3fv(overlay.uniforms.view, false, viewMatrix);
  gl.uniform2f(overlay.uniforms.resolution, renderer.element.width, renderer.element.height);
  gl.uniform2f(overlay.uniforms.size, Math.max(1, Number(overlayImage.width) || 1), Math.max(1, Number(overlayImage.height) || 1));
  gl.uniform1i(overlay.uniforms.texture, 0);
  gl.uniform1f(overlay.uniforms.opacity, Math.max(0, Math.min(1, Number(overlayImage.opacity) || 0)));
  gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  gl.drawArrays(gl.TRIANGLES, 0, 6);
  return true;
}

function hybridCanvasBackgroundColor(renderer) {
  const raw = String(canvas.backgroundColor || cssColorVar("--fabric-canvas-bg", "#ffffff")).trim();
  if (renderer.backgroundRaw === raw && renderer.backgroundColor) return renderer.backgroundColor;
  let color = [255, 255, 255, 255];
  if (/^#[0-9a-f]{6}$/i.test(raw)) {
    color = hexToRgb(raw, 255);
  } else {
    const match = raw.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i);
    if (match) color = normalizeColor([Number(match[1]), Number(match[2]), Number(match[3]), 255]);
  }
  renderer.backgroundRaw = raw;
  renderer.backgroundColor = color;
  return color;
}

function hybridRenderNow() {
  try {
    if (!resizeHybridRenderer() || !hybridShouldUse()) {
      endHybridRenderNow();
      return false;
    }
    const objects = vinylObjects();
    const renderer = hybridRenderer;
    const gl = renderer.gl;
    gl.viewport(0, 0, renderer.element.width, renderer.element.height);
    const background = hybridCanvasBackgroundColor(renderer);
    gl.clearColor(background[0] / 255, background[1] / 255, background[2] / 255, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    const viewMatrix = hybridMat3FromFabric(canvas.viewportTransform, renderer.viewMatrix);
    const drawReference = () => {
      const required = overlayImage?.visible !== false && (overlayImage?.opacity ?? 0) > 0;
      if (!drawHybridOverlay(renderer, viewMatrix) && required) throw new Error("Reference preview unavailable.");
    };
    if (overlayLayerMode === "below") drawReference();
    drawHybridShapePass(renderer, objects, viewMatrix, false);
    if (overlayLayerMode === "above") drawReference();
    drawHybridShapePass(renderer, objects, viewMatrix, true);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    return true;
  } catch (error) {
    hybridDisabledReason = error?.message || String(error);
    endHybridRenderNow();
    releaseHybridOverlay();
    if (hybridRenderer?.element) hybridRenderer.element.hidden = true;
    canvas?.requestRenderAll?.();
    window.KfpsEditorDiagnostics?.record("preview-fallback", { code: 2 });
    console.error("Editor GPU preview disabled; using Fabric:", hybridDisabledReason);
    return false;
  }
}

function requestHybridRender() {
  if (hybridRenderFrame) return;
  hybridRenderFrame = requestAnimationFrame(() => {
    hybridRenderFrame = null;
    if (!hybridRenderActive) return;
    if (hybridRenderNow()) {
      // Keep the last complete Fabric frame visible until the preview succeeds.
      hybridSetFabricLowerVisible(false);
      hybridRenderer.element.hidden = false;
      canvas?.renderTop?.();
    }
  });
}

function beginHybridRender(reason = "interaction") {
  if (activeToolMode === "guides") return false;
  const objects = vinylObjects();
  if (!hybridShouldUse(objects)) return false;
  clearTimeout(hybridRenderSettleTimer);
  hybridRenderSettleTimer = null;
  hybridRenderActive = true;
  hideHybridFabricBulkObjects(objects);
  requestHybridRender();
  setText("hudMode", KfpsI18n.t("{0} / GPU preview", currentHudMode(selectedVinylObjects().length)));
  return true;
}

function endHybridRenderNow() {
  clearTimeout(hybridRenderSettleTimer);
  hybridRenderSettleTimer = null;
  if (hybridRenderFrame) cancelAnimationFrame(hybridRenderFrame);
  hybridRenderFrame = null;
  if (!hybridRenderActive) return;
  hybridRenderActive = false;
  hybridSetFabricLowerVisible(true);
  restoreHybridFabricBulkObjects();
  if (hybridRenderer?.element) hybridRenderer.element.hidden = true;
  canvas?.requestRenderAll?.();
  updateHud();
}

function settleHybridRender(delay = HYBRID_RENDER_SETTLE_MS) {
  if (!hybridRenderActive) return;
  clearTimeout(hybridRenderSettleTimer);
  hybridRenderSettleTimer = setTimeout(() => endHybridRenderNow(), delay);
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
      const response = await fetch(url, { cache: "force-cache", signal: AbortSignal.timeout(15000) });
      if (response.ok) {
        resolvedResourceBase = base;
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
  if (data.length < 4) throw new Error(KfpsI18n.t("Legacy shape requires at least x,y,w,h data."));
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
  if (!shape || typeof shape !== "object") return null;
  const color = normalizeColor(shape.color);
  if (index === 0 && Number(shape.type) === 1 && color[3] <= 0) return null;
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

function observeEditorObjectId(value) {
  const match = /^e(\d+)$/i.exec(String(value || ""));
  if (!match) return;
  const numericId = Number(match[1]);
  if (Number.isSafeInteger(numericId) && numericId >= nextEditorObjectId) {
    nextEditorObjectId = numericId + 1;
  }
}

function allocateEditorObjectId(reservedIds = null) {
  let editorId;
  do {
    editorId = `e${nextEditorObjectId++}`;
  } while (reservedIds?.has(editorId));
  return editorId;
}

function assignUniqueEditorIds(shapes) {
  const reservedIds = new Set();
  shapes.forEach((shape) => {
    const editorId = shape?.editor_id ? String(shape.editor_id) : "";
    if (!editorId) return;
    reservedIds.add(editorId);
    observeEditorObjectId(editorId);
  });
  const seen = new Set();
  return shapes.map((shape) => {
    let editorId = shape?.editor_id ? String(shape.editor_id) : "";
    if (!editorId || seen.has(editorId)) {
      editorId = allocateEditorObjectId(reservedIds);
      reservedIds.add(editorId);
    }
    seen.add(editorId);
    return shape?.editor_id === editorId ? shape : { ...shape, editor_id: editorId };
  });
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
  const payload = resolved ? await loadResourcePayloadForResolved(resolved) : null;
  const d = resolved ? await loadResourcePathForResolved(resolved) : await loadResourcePath(typeCode);
  const color = normalizeColor(shape.color);
  const data = shape.data || [0, 0, 1, 1, 0, 0, 0];
  const alphaMeshResource = shouldUseAlphaMeshImage(resolved, payload);
  const imageTintResource = alphaMeshResource || isGradientResource(resolved);
  const pathCacheKey = resolved ? `mesh:${resourceCacheKey(resolved)}` : `mesh:${typeCode}`;
  const renderComplexity = resourceRenderComplexity(payload);
  const shapePathForBounds = imageTintResource ? makeCachedFabricPath(d, { originX: "center", originY: "center" }, pathCacheKey) : null;
  const object = alphaMeshResource
    ? await loadAlphaMeshFabricImageForResolved(resolved, payload)
    : imageTintResource
      ? await loadFabricImage(await resolveVinylResourceUrl(resolved.family, resolved.index, ".png"))
      : makeCachedFabricPath(d, {}, pathCacheKey);
  object.set({
    originX: "center",
    originY: "center",
    ...fabricPropsFromFh6Data(data),
    stroke: null,
    strokeWidth: 0,
    objectCaching: true,
    noScaleCache: true,
    perPixelTargetFind: false,
    targetFindTolerance: 0,
    hoverCursor: "pointer",
    moveCursor: "move",
    lockScalingFlip: false,
    centeredScaling: false,
  });
  if (alphaMeshResource) {
    const renderScale = Number(object.kloudyRenderScale) || 1;
    object.set({
      scaleX: object.scaleX * renderScale,
      scaleY: object.scaleY * renderScale,
    });
  }
  if (shapePathForBounds && !alphaMeshResource) {
    object.set({
      width: Math.max(1, Number(shapePathForBounds.width) || Number(object.width) || 1),
      height: Math.max(1, Number(shapePathForBounds.height) || Number(object.height) || 1),
    });
  }
  const resolvedShapeWord = Number(resolved?.shapeWord ?? shape.type_word ?? (typeCode & 0xffff));
  const editorId = shape.editor_id ? String(shape.editor_id) : allocateEditorObjectId();
  observeEditorObjectId(editorId);
  object.kloudy = {
    editor_id: editorId,
    name: name || (typeof shape.shape_name === "string" && shape.shape_name) || (resolved ? shapeDisplayName(resolved.family, resolved.index) : typeLabel(typeCode)),
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
    alpha_mesh_image: alphaMeshResource,
    render_scale: alphaMeshResource ? (Number(object.kloudyRenderScale) || 1) : 1,
    render_complexity: renderComplexity,
    locked: Boolean(shape.editor_locked),
    group_id: shape.editor_group_id ? String(shape.editor_group_id) : null,
    group_name: shape.editor_group_name ? String(shape.editor_group_name) : null,
    mesh_path: d || null,
    outline_path: shape.outline_path || null,
    outline_path_failed: false,
    scaleSigns: {
      x: (Number(data[2]) || 1) < 0 ? -1 : 1,
      y: (Number(data[3]) || 1) < 0 ? -1 : 1,
    },
  };
  applyObjectColor(object, color);
  // The object is not on the canvas yet. Batch callers synchronize mask
  // helpers once after insertion; doing it here rescans the old canvas for
  // every layer and turns large design loads into quadratic work.
  applyMaskVisual(object, { deferPreview: true });
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

// Display-only helpers. Never use these when writing shape_name or identifiers.
function localizedShapeDisplayName(family, index) {
  const original = shapeDisplayName(family, index);
  const named = KfpsI18n.shapeLabel(original);
  if (named !== original || KfpsI18n.language !== "ko") return named;
  let word;
  try { word = resourceToShapeWord(family, index); }
  catch (_) { word = shapeWords?.families?.[family]?.[String(index)]; }
  return KfpsI18n.t("{0} slot {1}{2}", KfpsI18n.familyLabel(family), index,
    word !== undefined ? KfpsI18n.t(" / word {0}", word) : "");
}

function localizedTypeLabel(typeCode) {
  const resource = typeCodeToResource(typeCode);
  return resource ? localizedShapeDisplayName(resource.family, resource.index) : KfpsI18n.t("Unknown {0}", typeCode);
}

function shapeSearchText(family, index, typeCode) {
  return [
    family,
    family.replaceAll("_", " "),
    index,
    typeCode,
    `#${index}`,
    shapeDisplayName(family, index),
    localizedShapeDisplayName(family, index),
    KfpsI18n.familyLabel(family),
  ].join(" ").toLowerCase();
}

function shapeCountForFamily(family) {
  const named = shapeNames?.families?.[family];
  if (named && Object.keys(named).length) {
    return Math.max(
      resourceCountForFamilyDefinition(family),
      ...Object.keys(named).map((key) => Number(key) || 0),
    );
  }
  return resourceCountForFamilyDefinition(family);
}

async function loadShapeNames() {
  try {
    const [namesResponse, wordsResponse] = await Promise.all([
      fetch("/tools/fabric-editor/shape-names.json"),
      fetch("/tools/fabric-editor/shape-words.json"),
    ]);
    if (!namesResponse.ok) throw new Error(KfpsI18n.t("shape-names HTTP {0}", namesResponse.status));
    if (!wordsResponse.ok) throw new Error(KfpsI18n.t("shape-words HTTP {0}", wordsResponse.status));
    shapeNames = await namesResponse.json();
    shapeWords = await wordsResponse.json();
    renderShapeGrid();
  } catch (err) {
    console.warn(KfpsI18n.t("Shape metadata unavailable."), err);
  }
}

function rememberColor(color) {
  rememberedColor = normalizeColor(color);
  editorSettings.setItem("kloudyFabricLastColor", JSON.stringify(rememberedColor));
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
      ? KfpsI18n.t("Slot {0}: use {1} / A {2}", index + 1, colorToHex(color).toUpperCase(), color[3])
      : KfpsI18n.t("Slot {0}: empty. Click to select, then Save Color.", index + 1);
    if (color) button.style.setProperty("--swatch", colorToHex(color));
    button.addEventListener("click", () => {
      selectedFavoriteColorSlot = index;
      if (color) applyEditorColor(color, "saved color");
      else {
        renderFavoriteColors();
        setStatus(KfpsI18n.t("Selected empty color slot {0}. Choose a color, then Save Color.", index + 1));
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
  if (editable.length) beginHybridRender("color preview");
  editable.forEach((obj) => applyObjectColor(obj, normalized, { deferImageFilter: hybridRenderActive }));
  refreshColorUiFast(normalized);
  syncSelectedShapeOutlines(selected);
  if (canvas && editable.length) {
    if (hybridRenderActive) {
      requestHybridRender();
      settleHybridRender(500);
    } else canvas.requestRenderAll();
  }
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
      setStatus(KfpsI18n.t("Selected layer is locked. Unlock it before changing color."));
      return;
    }
    rememberColor(normalized);
    applyObjectColor(selected[0], normalized);
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
      setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before changing color."));
      return;
    }
    rememberColor(normalized);
    editable.forEach((obj) => {
      applyObjectColor(obj, normalized);
    });
    syncSelectedShapeOutlines(selected);
    canvas.requestRenderAll();
    updateSelectionPanel();
    pushHistory("batch color edit");
    setStatus(KfpsI18n.t("Applied {0} / A {1} to {2} selected layer(s).{3}", colorToHex(normalized).toUpperCase(), normalized[3], editable.length, editable.length !== selected.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", selected.length - editable.length) : ""));
    return;
  }
  rememberColor(normalized);
  if ($("colorPicker")) $("colorPicker").value = colorToHex(normalized);
  if ($("opacitySlider")) $("opacitySlider").value = normalized[3];
  updateSelectionPanel();
  setStatus(KfpsI18n.t("Active color set to {0}.", colorToHex(normalized).toUpperCase()));
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
  setStatus(KfpsI18n.t("Saved {0} to color slot {1}.", hex.toUpperCase(), selectedFavoriteColorSlot + 1));
}

function removeCurrentFavoriteColor() {
  const slot = Math.max(0, Math.min(FAVORITE_COLOR_SLOTS - 1, selectedFavoriteColorSlot));
  const hadColor = Boolean(favoriteColors[slot]);
  while (favoriteColors.length < FAVORITE_COLOR_SLOTS) favoriteColors.push(null);
  favoriteColors[slot] = null;
  saveFavoriteColors();
  renderFavoriteColors();
  setStatus(hadColor ? KfpsI18n.t("Cleared color slot {0}.", slot + 1) : KfpsI18n.t("Color slot {0} is already empty.", slot + 1));
}

function clearFavoriteColors() {
  favoriteColors = Array(FAVORITE_COLOR_SLOTS).fill(null);
  saveFavoriteColors();
  renderFavoriteColors();
  setStatus(KfpsI18n.t("Cleared saved colors."));
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
      ? KfpsI18n.t("Eyedropper active. Click a vinyl layer to copy its color, or click the reference image to sample it.")
      : KfpsI18n.t("Eyedropper off."));
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
    if (object.containsPoint(point)) return object;
  }
  return null;
}

function pickShapeColorFromEvent(opt) {
  const pointer = KfpsFabricAdapter.scenePoint(canvas, opt.e);
  if (overlayLayerMode === "above") {
    const overlayColor = overlayColorAtCanvasPoint(pointer.x, pointer.y);
    if (overlayColor) {
      restoreDropperSelection();
      applyEditorColor(overlayColor, "source eyedropper");
      restoreDropperSelection();
      setStatus(KfpsI18n.t("Picked reference color {0}.", colorToHex(overlayColor).toUpperCase()));
      return;
    }
  }
  const target = (opt.target?.kloudy ? opt.target : null) || vinylObjectAtCanvasPoint(pointer.x, pointer.y);
  restoreDropperSelection();
  if (target) {
    const color = hexToRgb(target.fill || "#ffffff", (target.opacity ?? 1) * 255);
    applyEditorColor(color, "shape eyedropper");
    restoreDropperSelection();
    setStatus(KfpsI18n.t("Picked layer color {0} without changing selection.", colorToHex(color).toUpperCase()));
    return;
  }
  const color = overlayColorAtCanvasPoint(pointer.x, pointer.y);
  if (!color) {
    setStatus(KfpsI18n.t("No vinyl layer or reference-image pixel under the eyedropper."));
    return;
  }
  applyEditorColor(color, "source eyedropper");
  restoreDropperSelection();
  setStatus(KfpsI18n.t("Picked reference color {0}.", colorToHex(color).toUpperCase()));
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
  const renderScale = Math.max(0.000001, Number(object?.kloudy?.render_scale) || 1);
  const rawSx = signX * (Math.hypot(a, b) || 1);
  const theta = Math.atan2(b / rawSx, a / rawSx);
  const det = a * d - b * c;
  const rawSy = det / rawSx || 1;
  const cos = Math.cos(-theta);
  const sin = Math.sin(-theta);
  const localC = cos * c - sin * d;
  const skew = rawSy ? -(localC / rawSy) : 0;
  const rotation = ((-theta * 180 / Math.PI) % 360 + 360) % 360;
  const sx = rawSx / renderScale;
  const sy = rawSy / renderScale;
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
    shape.editor_id = meta.editor_id || null;
    shape.editor_hidden = !objectEditorVisible(object);
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
    const state = history[historyIndex];
    if (state && typeof state === "object") {
      const nextState = { ...state, editor_collapsed_groups: collapsed };
      history[historyIndex] = (
        savedHistoryState && historyStatesEqual(savedHistoryState, nextState)
          ? savedHistoryState
          : nextState
      );
    }
  }
  try {
    writeAutosavePayload(
      autosavePayloadFromState(currentHistoryState() || snapshotEditorState()),
    );
  } catch (err) {
    console.warn(KfpsI18n.t("Collapsed layer autosave skipped."), err);
  }
  updateDocumentState();
  renderHistoryList();
}

function snapshotEditorState() {
  return {
    version: 2,
    shapes: snapshotShapes(),
    editor_guides: savedGuideState(),
    editor_collapsed_groups: collapsedLayerGroupIds(),
  };
}

function historyShapeSignature(shape) {
  return JSON.stringify(shape);
}

function setHistoryShapeSignature(shape, signature) {
  Object.defineProperty(shape, "__historySignature", {
    value: signature,
    configurable: true,
    enumerable: false,
    writable: true,
  });
  return shape;
}

function captureSharedHistoryState(previousState = null, changedObjects = null) {
  const objects = vinylObjects();
  const objectSet = new Set(objects);
  const previousShapes = Array.isArray(previousState?.shapes) ? previousState.shapes : [];
  // Only known non-structural edits may reuse records without re-serializing them.
  const changed = Array.isArray(changedObjects) && changedObjects.length
    && changedObjects.every(object => objectSet.has(object))
    && previousShapes.length === objects.length
    && objects.every((object, index) => object.kloudy?.editor_id
      && object.kloudy.editor_id === previousShapes[index]?.editor_id)
    ? new Set(changedObjects) : null;
  const previousById = new Map(
    (Array.isArray(previousState?.shapes) ? previousState.shapes : [])
      .map((shape) => [String(shape?.editor_id || ""), shape])
      .filter(([editorId]) => editorId),
  );
  const shapes = objects.map((object, index) => {
    if (changed && !changed.has(object)) {
      object.__kloudyHistoryShape = previousShapes[index];
      return previousShapes[index];
    }
    const shape = objectToShape(object, { includeEditorMeta: true });
    const signature = historyShapeSignature(shape);
    const editorId = String(shape.editor_id || "");
    const attached = object.__kloudyHistoryShape;
    const previous = attached?.editor_id === editorId ? attached : previousById.get(editorId);
    if (previous && previous.__historySignature === signature) {
      object.__kloudyHistoryShape = previous;
      return previous;
    }
    const next = setHistoryShapeSignature(shape, signature);
    object.__kloudyHistoryShape = next;
    return next;
  });
  return {
    version: 3,
    shapes,
    editor_guides: savedGuideState(),
    editor_collapsed_groups: collapsedLayerGroupIds(),
  };
}

function historyStatesEqual(left, right) {
  if (!left || !right || !Array.isArray(left.shapes) || !Array.isArray(right.shapes)) return false;
  if (left.shapes.length !== right.shapes.length) return false;
  if (!left.shapes.every((shape, index) => shape === right.shapes[index])) return false;
  if (JSON.stringify(left.editor_guides || null) !== JSON.stringify(right.editor_guides || null)) return false;
  return JSON.stringify(left.editor_collapsed_groups || []) === JSON.stringify(right.editor_collapsed_groups || []);
}

function historyStorageEstimate() {
  const uniqueShapes = new Set();
  let referenceBytes = 0;
  let metadataBytes = 0;
  history.forEach((state) => {
    if (!state || typeof state !== "object") return;
    (state.shapes || []).forEach((shape) => uniqueShapes.add(shape));
    referenceBytes += (state.shapes?.length || 0) * 8;
    metadataBytes += JSON.stringify({
      editor_guides: state.editor_guides || null,
      editor_collapsed_groups: state.editor_collapsed_groups || [],
    }).length;
  });
  const shapeBytes = [...uniqueShapes].reduce((total, shape) => total + (shape.__historySignature?.length || JSON.stringify(shape).length), 0);
  return { bytes: shapeBytes + referenceBytes + metadataBytes, uniqueShapes: uniqueShapes.size };
}

async function restoreShapes(shapes, options = {}) {
  const previousCollapsed = new Set(collapsedLayerGroups);
  historyLocked = true;
  clearVinylObjects({ preserveCollapsed: true });
  const normalizedShapes = assignUniqueEditorIds(shapes);
  const objects = await KfpsEditorCore.mapWithConcurrency(
    normalizedShapes,
    OBJECT_BUILD_CONCURRENCY,
    (shape) => makeFabricObject(shape),
  );
  objects.forEach((object) => canvas.add(object));
  if (Array.isArray(options.collapsedGroups)) applyCollapsedLayerGroups(options.collapsedGroups);
  else {
    collapsedLayerGroups = previousCollapsed;
    pruneCollapsedLayerGroups();
  }
  bringGuidesToBack();
  historyLocked = false;
  refreshLayers();
  syncCanvasObjectCoords();
  await prewarmHybridMeshesForObjects(vinylObjects());
  canvas.requestRenderAll();
}

function objectMatchesHistoryShape(object, shape) {
  if (!object?.kloudy || !shape) return false;
  return Number(object.kloudy.type) === Number(shape.type)
    && String(object.kloudy.resource_family || "") === String(shape.resource_family || "")
    && Number(object.kloudy.resource_index || 0) === Number(shape.resource_index || 0);
}

function applyHistoryShapeToObject(object, shape) {
  const data = Array.isArray(shape.data) ? shape.data : [0, 0, 1, 1, 0, 0, 0];
  const color = normalizeColor(shape.color);
  const props = fabricPropsFromFh6Data(data);
  const renderScale = Math.max(0.000001, Number(object.kloudy?.render_scale) || 1);
  object.set({
    ...props,
    scaleX: props.scaleX * renderScale,
    scaleY: props.scaleY * renderScale,
    visible: !shape.editor_hidden,
  });
  Object.assign(object.kloudy, {
    editor_id: String(shape.editor_id || object.kloudy.editor_id || allocateEditorObjectId()),
    name: shape.shape_name || object.kloudy.name,
    type: Number(shape.type),
    type_word: Number(shape.type_word ?? (Number(shape.type) & 0xffff)),
    resource_family: shape.resource_family || object.kloudy.resource_family || null,
    resource_index: shape.resource_index || object.kloudy.resource_index || null,
    source_format: shape.source_format || "fh6_typecode",
    legacy_type: shape.legacy_type ?? null,
    legacy_divisor: shape.legacy_divisor ?? null,
    legacy_offset: Array.isArray(shape.legacy_offset) ? shape.legacy_offset.slice(0, 2) : null,
    score: Number(shape.score) || 0,
    extra: data.slice(5),
    mask: Boolean(shape.mask || data[6]),
    locked: Boolean(shape.editor_locked),
    group_id: shape.editor_group_id ? String(shape.editor_group_id) : null,
    group_name: shape.editor_group_name ? String(shape.editor_group_name) : null,
    scaleSigns: {
      x: (Number(data[2]) || 1) < 0 ? -1 : 1,
      y: (Number(data[3]) || 1) < 0 ? -1 : 1,
    },
  });
  if (object.kloudy.mask) {
    object.kloudy.maskOriginalColor = color.slice();
    object.set({ fill: colorToHex(color), opacity: color[3] / 255 });
    applyMaskVisual(object, { deferPreview: true });
  } else {
    object.kloudy.maskOriginalColor = null;
    applyObjectColor(object, color);
    applyMaskVisual(object, { deferPreview: true });
  }
  setObjectLocked(object, object.kloudy.locked);
  applyObjectHitTestMode(object);
  styleObjectTransformControls(object);
  object.__kloudyHistoryShape = shape;
  object.setCoords();
  return object;
}

async function restoreEditorState(snapshot) {
  cancelEditorTransform();
  const generation = documentGeneration;
  const historyState = currentHistoryState();
  const state = Array.isArray(snapshot)
    ? { shapes: snapshot, editor_guides: null, editor_collapsed_groups: [] }
    : (snapshot && typeof snapshot === "object" ? snapshot : {});
  const targetShapes = assignUniqueEditorIds(Array.isArray(state.shapes) ? state.shapes : []);
  const currentObjects = vinylObjects().slice();
  const currentById = new Map(currentObjects.map((object) => [String(object.kloudy?.editor_id || ""), object]));
  const selectedIds = new Set(selectedVinylObjects().map((object) => String(object.kloudy?.editor_id || "")));
  const reused = new Set();
  const created = [];
  let buildError = null;
  let committed = false;
  try {
    const targetObjects = await KfpsEditorCore.mapWithConcurrency(
      targetShapes,
      OBJECT_BUILD_CONCURRENCY,
      async (shape) => {
        const existing = currentById.get(String(shape.editor_id || ""));
        if (existing && objectMatchesHistoryShape(existing, shape)) {
          reused.add(existing);
          return existing;
        }
        try {
          const object = await makeFabricObject(shape);
          object.__kloudyHistoryShape = shape;
          created.push(object);
          return object;
        } catch (error) {
          buildError ||= error;
          return null;
        }
      },
    );
    if (buildError) throw buildError;
    await prewarmHybridMeshesForObjects(created);
    flushPendingNudgeHistory();
    if (generation !== documentGeneration || historyState !== currentHistoryState()) return false;
    // Prepare resources and install additions before changing or releasing any
    // live objects. A failed build must not partially apply an undo.
    historyLocked = true;
    created.forEach((object) => canvas.add(object));
    if (isActiveSelectionObject(canvas.getActiveObject())) canvas.discardActiveObject();
    targetObjects.forEach((object, index) => {
      const shape = targetShapes[index];
      if (reused.has(object) && object.__kloudyHistoryShape !== shape) applyHistoryShapeToObject(object, shape);
    });
    currentObjects.forEach((object) => { if (!reused.has(object)) discardFabricObject(object); });
    committed = true;
    setVinylStackOrder(targetObjects);
    applyCollapsedLayerGroups(state.editor_collapsed_groups || []);
    applySavedGuideState(state.editor_guides || null);
    syncMaskPreviewOutlines();
    bringGuidesToBack();
    const restoredSelection = targetObjects.filter((object) => selectedIds.has(String(object.kloudy?.editor_id || "")));
    if (restoredSelection.length === 1) canvas.setActiveObject(restoredSelection[0]);
    else if (restoredSelection.length > 1) canvas.setActiveObject(styledActiveSelection(restoredSelection));
    else canvas.discardActiveObject();
    invalidateVinylObjectRegistry();
    refreshLayers();
    syncCanvasObjectCoords(restoredSelection);
    canvas.requestRenderAll();
    updateSelectionPanel();
    writeAutosavePayload(autosavePayloadFromState({ ...state, shapes: targetShapes }));
    return true;
  } finally {
    if (!committed) created.forEach(discardFabricObject);
    historyLocked = false;
  }
}

function resetHistory({ preserveGeneration = false } = {}) {
  if (!preserveGeneration) {
    documentGeneration += 1;
    recoveryRestoreDepth = 0;
  }
  pixelArtAnalysisCancel?.();
  if (nudgeHistoryTimer) clearTimeout(nudgeHistoryTimer);
  nudgeHistoryTimer = null;
  nudgeHistoryPending = false;
  history = [];
  pendingNudgeObjects.clear();
  historyIndex = -1;
  protectedHistoryIndex = -1;
  lastHistoryReason = "";
  lastHistoryAt = 0;
  savedHistoryState = null;
  updateDocumentState();
  renderHistoryList();
}

function autosavePayloadFromState(state) {
  const payload = {
    format: "kloudy_fabric_editor_autosave_v1",
    name: cleanProjectBaseName(loadedName, "autosave"),
    saved_at: new Date().toISOString(),
    editor_session: {
      project_name: currentProjectName,
      saved: !nudgeHistoryPending && state === savedHistoryState && savedOverlayRevision === overlayRevision,
    },
    shapes: Array.isArray(state?.shapes) ? state.shapes : [],
    editor_guides: state?.editor_guides || savedGuideState(),
    editor_collapsed_groups: Array.isArray(state?.editor_collapsed_groups) ? state.editor_collapsed_groups : collapsedLayerGroupIds(),
  };
  const sourceOverlay = sourceOverlayProjectState();
  if (sourceOverlay) payload.editor_source_overlay = sourceOverlay;
  return payload;
}

function nextAutosaveRevision() {
  autosaveRevision = Math.max(autosaveRevision + 1, Date.now() * 1000);
  return autosaveRevision;
}

function recoveryRevision(payload) {
  const revision = Number(payload?.recovery_revision);
  if (Number.isSafeInteger(revision) && revision > 0) return revision;
  return Math.max(0, Date.parse(payload?.saved_at || "") || 0) * 1000;
}

function reportAutosaveResult(operation, browserOk, serverOk, error) {
  window.KfpsEditorDiagnostics?.recovery(operation.recovery_revision, browserOk, serverOk);
  if (operation.recovery_revision !== autosaveRevision) return;
  const ok = browserOk || serverOk;
  autosaveStatus = { state: ok ? "saved" : "failed", revision: autosaveRevision, browserOk, serverOk, error };
  const message = serverOk ? KfpsI18n.t("Recovery saved in KFPS") : browserOk ? KfpsI18n.t("Recovery saved in this browser only") : KfpsI18n.t("Recovery failed; save the project");
  const status = $("status");
  const recoveryMessage = KfpsI18n.recoveryPattern();
  if (status && recoveryMessage.test(status.textContent)) {
    setStatus(status.textContent.replace(recoveryMessage, message));
  }
  if (!ok) showCornerNotice(KfpsI18n.t("Recovery unavailable"), error || KfpsI18n.t("Save the project to protect your changes."));
}

function drainAutosaveQueue() {
  if (autosaveWritePromise) return autosaveWritePromise;
  autosaveWritePromise = (async () => {
    while (queuedAutosaveOperation) {
      const operation = queuedAutosaveOperation;
      queuedAutosaveOperation = null;
      if (operation.recovery_revision !== autosaveRevision) continue;
      const clearing = operation.action === "clear";
      let browserOk = clearing;
      let serverOk = false;
      let retryable = true;
      let error = "";
      try {
        const result = await editorPersistence.request("recovery", { payload: operation });
        browserOk = result.browserOk;
        serverOk = result.serverOk;
        retryable = result.retryable;
        error = KfpsI18n.error(result.error || "");
      } catch (err) {
        if (err.code === "recovery_too_large") {
          retryable = false;
          error = KfpsI18n.t("Recovery exceeds the {0} MiB project limit. Use a smaller reference image.", EDITOR_PROJECT_MAX_BYTES / (1024 * 1024));
        } else error = KfpsI18n.error(err.message || String(err));
        console.warn(KfpsI18n.t("App-folder autosave skipped."), err);
      }
      if (!clearing) reportAutosaveResult(operation, browserOk, serverOk, error);
      if (serverOk) autosaveRetryDelay = 2000;
      else if (retryable && operation.recovery_revision === autosaveRevision) {
        clearTimeout(autosaveRetryTimer);
        autosaveRetryTimer = setTimeout(() => {
          autosaveRetryTimer = null;
          if (operation.recovery_revision !== autosaveRevision) return;
          queuedAutosaveOperation = operation;
          drainAutosaveQueue();
        }, autosaveRetryDelay);
        autosaveRetryDelay = Math.min(30000, autosaveRetryDelay * 2);
      }
    }
  })().finally(() => {
    autosaveWritePromise = null;
    if (queuedAutosaveOperation) return drainAutosaveQueue();
  });
  return autosaveWritePromise;
}

function flushPendingAutosave() {
  if (autosaveWriteTimer) clearTimeout(autosaveWriteTimer);
  autosaveWriteTimer = null;
  autosavePendingSince = null;
  if (pendingAutosavePayload) {
    queuedAutosaveOperation = pendingAutosavePayload;
    pendingAutosavePayload = null;
  }
  if (autosaveWritePromise && queuedAutosaveOperation) backupQueuedAutosave(queuedAutosaveOperation);
  return drainAutosaveQueue();
}

let browserBackupPromise = null;
let queuedBrowserBackup = null;
function backupQueuedAutosave(operation) {
  queuedBrowserBackup = operation;
  if (browserBackupPromise) return browserBackupPromise;
  browserBackupPromise = (async () => {
    while (queuedBrowserBackup) {
      const payload = queuedBrowserBackup;
      queuedBrowserBackup = null;
      try {
        const result = await editorPersistence.request("browserRecovery", { payload });
        if (payload.recovery_revision === autosaveRevision && payload.action !== "clear" && result.browserOk) {
          reportAutosaveResult(payload, true, autosaveStatus.serverOk === true, autosaveStatus.error || "");
        }
      } catch (_err) {
        // The ordered app-folder writer reports failure and retries independently.
      }
    }
  })().finally(() => { browserBackupPromise = null; });
  return browserBackupPromise;
}

function writeAutosavePayload(payload) {
  if (recoveryRestoreDepth) return false;
  if (!payload || !Array.isArray(payload.shapes)) return false;
  const revision = nextAutosaveRevision();
  pendingAutosavePayload = { ...payload, recovery_revision: revision };
  autosaveStatus = { state: "pending", revision };
  window.KfpsEditorDiagnostics?.queued(revision);
  clearTimeout(autosaveRetryTimer);
  autosaveRetryTimer = null;
  autosaveRetryDelay = 2000;
  if (autosavePendingSince === null) autosavePendingSince = performance.now();
  if (autosaveWriteTimer) clearTimeout(autosaveWriteTimer);
  const remaining = Math.max(0, AUTOSAVE_MAX_WAIT_MS - (performance.now() - autosavePendingSince));
  autosaveWriteTimer = setTimeout(flushPendingAutosave, Math.min(AUTOSAVE_IDLE_MS, remaining));
  return true;
}

function flushPendingAutosaveToBrowser() {
  // Native close awaits this writer. Browser unload cannot promise a last-second
  // save; frequent acknowledged checkpoints provide the recoverable boundary.
  void flushPendingAutosave();
  return false;
}

function clearAutosave() {
  recoveryAutosavePayload = null;
  const revision = nextAutosaveRevision();
  pendingAutosavePayload = null;
  autosavePendingSince = null;
  clearTimeout(autosaveRetryTimer);
  autosaveRetryTimer = null;
  autosaveRetryDelay = 2000;
  if (autosaveWriteTimer) {
    clearTimeout(autosaveWriteTimer);
    autosaveWriteTimer = null;
  }
  try {
    localStorage.removeItem(AUTOSAVE_KEY);
    localStorage.setItem(AUTOSAVE_CLEAR_KEY, String(revision));
  } catch (_err) {
    // Ignore storage cleanup failures.
  }
  autosaveStatus = { state: "cleared", revision };
  queuedAutosaveOperation = { action: "clear", shapes: [], recovery_revision: revision };
  if (autosaveWritePromise) backupQueuedAutosave(queuedAutosaveOperation);
  return drainAutosaveQueue();
}

function pushHistory(reason = "change", options = {}) {
  if (historyLocked) return;
  const previous = historyIndex >= 0 && typeof history[historyIndex] === "object" ? history[historyIndex] : null;
  const snapshot = captureSharedHistoryState(previous, nudgeHistoryTimer ? null : options.changedObjects);
  if (historyStatesEqual(previous, snapshot)) return;
  snapshot.history_reason = String(reason || "change");
  snapshot.history_at = new Date().toISOString();
  const now = performance.now();
  const coalesce = reason === "nudge"
    && lastHistoryReason === reason
    && now - lastHistoryAt < 400
    && historyIndex === history.length - 1
    && historyIndex > Math.max(0, protectedHistoryIndex);
  if (coalesce) {
    history[historyIndex] = snapshot;
  } else {
    history = history.slice(0, historyIndex + 1);
    history.push(snapshot);
    if (history.length > 80) {
      history.shift();
      if (protectedHistoryIndex >= 0) protectedHistoryIndex = Math.max(0, protectedHistoryIndex - 1);
    }
    historyIndex = history.length - 1;
  }
  lastHistoryReason = reason;
  lastHistoryAt = now;
  const autosaveOk = writeAutosavePayload(autosavePayloadFromState(snapshot));
  updateDocumentState();
  renderHistoryList();
  if (!options.validationScheduled) scheduleExportValidation();
  setStatus(KfpsI18n.t("Changed: {0}.{1}", humanizeHistoryReason(reason), autosaveOk ? KfpsI18n.t(" Recovery pending.") : KfpsI18n.t(" Recovery could not be queued.")));
}

function flushPendingNudgeHistory() {
  if (nudgeHistoryTimer) clearTimeout(nudgeHistoryTimer);
  nudgeHistoryTimer = null;
  nudgeHistoryStarted = null;
  if (!nudgeHistoryPending) return false;
  nudgeHistoryPending = false;
  const changedObjects = [...pendingNudgeObjects];
  pendingNudgeObjects.clear();
  pushHistory("nudge", { changedObjects });
  return true;
}

function scheduleNudgeHistory() {
  if (!nudgeHistoryPending) nudgeHistoryStarted = performance.now();
  nudgeHistoryPending = true;
  if (nudgeHistoryTimer) clearTimeout(nudgeHistoryTimer);
  const remaining = Math.max(0, AUTOSAVE_MAX_WAIT_MS - AUTOSAVE_IDLE_MS - (performance.now() - nudgeHistoryStarted));
  nudgeHistoryTimer = setTimeout(flushPendingNudgeHistory, Math.min(180, remaining));
  updateDocumentState();
}

function ensureHistoryBaseline() {
  if (historyLocked || historyIndex >= 0) return;
  const snapshot = captureSharedHistoryState();
  snapshot.history_reason = "blank canvas";
  snapshot.history_at = new Date().toISOString();
  history = [snapshot];
  historyIndex = 0;
  protectedHistoryIndex = -1;
  updateDocumentState();
  renderHistoryList();
}

function establishLoadedHistoryBoundary(reason = "loaded source", options = {}) {
  if (nudgeHistoryTimer) clearTimeout(nudgeHistoryTimer);
  nudgeHistoryTimer = null;
  nudgeHistoryPending = false;
  const snapshot = captureSharedHistoryState();
  pendingNudgeObjects.clear();
  snapshot.history_reason = String(reason || "loaded source");
  snapshot.history_at = new Date().toISOString();
  history = [snapshot];
  historyIndex = 0;
  protectedHistoryIndex = 0;
  lastHistoryReason = "";
  lastHistoryAt = 0;
  savedHistoryState = null;
  if (options.writeRecovery !== false) {
    writeAutosavePayload(autosavePayloadFromState(snapshot));
  }
  updateDocumentState();
  renderHistoryList();
  refreshExportValidation();
  return snapshot;
}

function humanizeHistoryReason(reason) {
  const text = String(reason || "change").replace(/[-_]+/g, " ").trim();
  const localized = KfpsI18n.history(text);
  if (localized !== text) return localized;
  return text ? text[0].toUpperCase() + text.slice(1) : KfpsI18n.t("Change");
}

function currentHistoryState() {
  return historyIndex >= 0 ? history[historyIndex] : null;
}

function hasEditableWorkspace() {
  return Boolean(canvas && (vinylObjects().length || overlayImage || unavailableSourceOverlayState
    || guideState.guides.length || currentProjectName));
}

function updateDocumentState() {
  const hasWork = hasEditableWorkspace();
  const current = currentHistoryState();
  documentDirty = hasWork && (
    !currentProjectName
    || !savedHistoryState
    || current !== savedHistoryState
    || overlayRevision !== savedOverlayRevision
    || nudgeHistoryPending
  );
  const title = !currentProjectName && loadedName === "untitled"
    ? KfpsI18n.t("Untitled vinyl")
    : cleanProjectBaseName(currentProjectName || loadedName || "untitled", "untitled");
  setText("projectNameLabel", currentProjectName ? `${title}.fabric-project.json` : KfpsI18n.t("{0} - not saved as a project", title));
  const chip = $("projectDirtyChip");
  if (chip) {
    chip.classList.toggle("dirty", documentDirty);
    chip.classList.toggle("saved", hasWork && !documentDirty);
    chip.textContent = !hasWork ? KfpsI18n.t("Blank canvas") : (documentDirty ? KfpsI18n.t("Unsaved changes") : KfpsI18n.t("Project saved"));
  }
  document.title = KfpsI18n.t("{0}{1} - KFPS Vinyl Editor", documentDirty ? "* " : "", title);
}

function markCurrentHistorySaved(projectName) {
  currentProjectName = cleanProjectBaseName(projectName || currentProjectName || loadedName, "project");
  loadedName = currentProjectName;
  savedHistoryState = currentHistoryState();
  savedOverlayRevision = overlayRevision;
  updateDocumentState();
  renderHistoryList();
}

function markOverlayChanged(reason = "reference image changed") {
  window.KfpsEditorDiagnostics?.pulse("reference");
  overlayRevision += 1;
  const state = currentHistoryState() || snapshotEditorState();
  writeAutosavePayload(autosavePayloadFromState(state));
  updateDocumentState();
  setStatus(KfpsI18n.t("{0}. Recovery pending; reference images never export.", humanizeHistoryReason(reason)));
}

let historyTimeFormatter = null;
let historyTimeLocale = null;

function historyTimeLabel(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "";
  if (!historyTimeFormatter || historyTimeLocale !== KfpsI18n.locale) {
    historyTimeLocale = KfpsI18n.locale;
    historyTimeFormatter = new Intl.DateTimeFormat(historyTimeLocale, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  return historyTimeFormatter.format(date);
}

function renderHistoryList() {
  const list = $("historyList");
  if (!list) return;
  list.replaceChildren();
  setText("historyPositionBadge", history.length ? `${historyIndex + 1} / ${history.length}` : "0 / 0");
  const floor = Math.max(0, protectedHistoryIndex);
  const canUndo = historyIndex > floor;
  const canRedo = historyIndex >= 0 && historyIndex < history.length - 1;
  ["undoBtn", "historyUndo"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = !canUndo;
  });
  ["redoBtn", "historyRedo"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = !canRedo;
  });
  if (!history.length) {
    const empty = document.createElement("p");
    empty.textContent = KfpsI18n.t("Changes will appear here after you import or add a shape.");
    list.appendChild(empty);
    return;
  }
  history.forEach((state, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "historyEntry";
    button.classList.toggle("current", index === historyIndex);
    button.classList.toggle("protected", index === protectedHistoryIndex);
    button.disabled = index < floor;
    const reason = humanizeHistoryReason(
      state?.history_reason || (index === protectedHistoryIndex ? KfpsI18n.t("loaded source") : "change"),
    );
    button.innerHTML = KfpsI18n.t("\n      <span class=\"historyEntryIndex\">{0}</span>\n      <span class=\"historyEntryText\">\n        <b>{1}</b>\n        <small>{2} layers{3}</small>\n      </span>\n      <span class=\"historyEntryState\">{4}</span>\n    ", index + 1, escapeHtml(reason), state?.shapes?.length || 0, state?.history_at ? ` / ${escapeHtml(historyTimeLabel(state.history_at))}` : "", index === historyIndex ? KfpsI18n.t("Current") : (state === savedHistoryState ? KfpsI18n.t("Saved") : ""));
    button.addEventListener("click", () => jumpToHistory(index));
    list.appendChild(button);
  });
}

function jumpToHistory(index) {
  return queueEditorMutation(async () => {
    flushPendingNudgeHistory();
    const target = Math.max(Math.max(0, protectedHistoryIndex), Math.min(history.length - 1, Number(index)));
    if (!Number.isInteger(target) || target === historyIndex) return;
    if (!await restoreEditorState(history[target])) return;
    historyIndex = target;
    lastHistoryReason = "";
    updateDocumentState();
    renderHistoryList();
    setStatus(KfpsI18n.t("Returned to {0}.", humanizeHistoryReason(history[historyIndex]?.history_reason || "change")));
  });
}

function queueEditorMutation(operation) {
  return new Promise((resolve, reject) => {
    editorMutationQueue.push({ operation, resolve, reject, generation: documentGeneration });
    drainEditorMutationQueue();
  });
}

async function drainEditorMutationQueue() {
  if (editorMutationRunning) return;
  editorMutationRunning = true;
  try {
    while (editorMutationQueue.length) {
      const task = editorMutationQueue.shift();
      try {
        task.resolve(task.generation === documentGeneration ? await task.operation() : false);
      } catch (error) {
        task.reject(error);
      }
    }
  } finally {
    editorMutationRunning = false;
    if (editorMutationQueue.length) drainEditorMutationQueue();
  }
}

function cancelEditorTransform() {
  const transform = KfpsFabricAdapter.cancelObjectTransform(canvas);
  if (!transform) return null;
  const target = interactiveVinylTarget(transform.target);
  const objects = isActiveSelectionObject(target) ? target.getObjects().map(interactiveVinylTarget) : [target];
  // The history reference describes the last committed state, not this
  // in-flight transform. Force restoration even when the snapshot is reused.
  objects.forEach((object) => { if (object) delete object.__kloudyHistoryShape; });
  transformAnchorSnapshot = null;
  dragAxisSnapshot = null;
  clearDragAxisLock();
  clearSnapOverlay();
  endHybridRenderNow();
  return transform;
}

async function undoNow() {
  flushPendingNudgeHistory();
  const interrupted = cancelEditorTransform();
  if (interrupted?.actionPerformed && currentHistoryState()) {
    if (!await restoreEditorState(currentHistoryState())) return;
    updateDocumentState();
    setStatus(KfpsI18n.t("Current drag cancelled."));
    return;
  }
  const floor = Math.max(0, protectedHistoryIndex);
  if (historyIndex <= floor) {
    setStatus(protectedHistoryIndex >= 0 ? KfpsI18n.t("Undo stopped at loaded source.") : KfpsI18n.t("Nothing to undo."));
    return;
  }
  lastHistoryReason = "";
  const target = historyIndex - 1;
  if (!await restoreEditorState(history[target])) return;
  historyIndex = target;
  updateDocumentState();
  renderHistoryList();
  setStatus(KfpsI18n.t("Undo."));
}

function undo() {
  return queueEditorMutation(undoNow);
}

async function redoNow() {
  flushPendingNudgeHistory();
  const interrupted = cancelEditorTransform();
  if (interrupted?.actionPerformed && currentHistoryState()) {
    if (!await restoreEditorState(currentHistoryState())) return;
    updateDocumentState();
  }
  if (historyIndex >= history.length - 1) return;
  lastHistoryReason = "";
  const target = historyIndex + 1;
  if (!await restoreEditorState(history[target])) return;
  historyIndex = target;
  updateDocumentState();
  renderHistoryList();
  setStatus(KfpsI18n.t("Redo."));
}

function redo() {
  return queueEditorMutation(redoNow);
}

function round(value) {
  const n = Math.round(Number(value) * 1000000) / 1000000;
  return Math.abs(n - Math.round(n)) < 0.000001 ? Math.round(n) : n;
}

function requestCanvasRender() {
  if (!canvas) return;
  if (hybridRenderActive) {
    requestHybridRender();
    return;
  }
  if (canvasRenderFrame) return;
  canvasRenderFrame = requestAnimationFrame(() => {
    canvasRenderFrame = null;
    if (hybridRenderActive) {
      requestHybridRender();
    } else {
      canvas.requestRenderAll();
    }
  });
}

function syncCanvasObjectCoords(objects = null) {
  if (!canvas) return;
  canvas.calcOffset();
  const active = canvas.getActiveObject();
  const targets = Array.isArray(objects)
    ? objects
    : [active, ...selectedVinylObjects()];
  [...new Set(targets.filter(Boolean))].forEach((object) => object.setCoords?.());
}

function finishCanvasPan() {
  if (!canvas || !isPanning) return;
  // Direct viewportTransform mutation is fast while dragging, but Fabric needs
  // the transform re-applied before hit-testing lines up with the rendered view.
  canvas.setViewportTransform(canvas.viewportTransform);
  syncCanvasObjectCoords();
  updateVisualGridLayer();
  if (hybridRenderActive) {
    requestHybridRender();
    settleHybridRender();
  } else {
    canvas.requestRenderAll();
  }
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
    fireMiddleClick: true,
    stopContextMenu: true,
    backgroundColor: canvasBg,
    renderOnAddRemove: false,
    enableRetinaScaling: false,
    skipOffscreen: true,
    perPixelTargetFind: false,
    targetFindTolerance: VINYL_HIT_TOLERANCE,
    defaultCursor: "default",
    hoverCursor: "default",
    moveCursor: "move",
    freeDrawingCursor: "default",
  });
  KfpsFabricAdapter.installSceneRenderGate(canvas, () => hybridRenderActive
    && canvas.lowerCanvasEl.style.visibility === "hidden"
    && !hybridDisabledReason);
  KfpsFabricAdapter.installCpuPixelPicking(canvas);
  KfpsFabricAdapter.installNearestControlPicking(canvas);
  window.KfpsEditorDiagnostics?.bindCanvas(canvas);
  initHybridRenderer();
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
      requestAnimationFrame(() => restoreSelectionLock(KfpsI18n.t("a canvas misclick")));
      return;
    }
    clearSnapOverlay();
    updateSelectionPanel();
  });
  canvas.on("object:added", (event) => {
    if (event.target?.kloudyGuide) guideObjectRegistry.invalidate();
    if (event.target?.kloudy) {
      invalidateVinylObjectRegistry();
      styleObjectTransformControls(event.target);
      event.target.setCoords();
      if (hybridRenderActive) requestHybridRender();
    }
  });
  canvas.on("object:removed", (event) => {
    if (event.target?.kloudyGuide) guideObjectRegistry.invalidate();
    if (event.target?.kloudy) {
      invalidateVinylObjectRegistry();
      removeVinylObjectHelpers(event.target);
      if (hybridRenderActive) requestHybridRender();
    }
  });
  canvas.on("object:modified", (event) => {
    settleHybridRender(80);
    if (event.target?.kloudyOverlay) {
      constrainSourceOverlayTransform();
      clearSnapOverlay();
      updateHud();
      if (hybridRenderActive) requestHybridRender();
      markOverlayChanged("reference image moved");
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
    scheduleRefreshLayers({ geometryOnly: true });
    pushHistory("object edit", { changedObjects: selectedVinylObjects(), validationScheduled: true });
  });
  canvas.on("object:moving", (event) => {
    if (event.target?.kloudyOverlay) {
      beginHybridRender("source overlay move");
      constrainSourceOverlayTransform();
      snapSourceOverlayToGuides(event);
      if (hybridRenderActive) requestHybridRender();
      return;
    }
    beginHybridRender("move");
    leaveGuideModeForLayerEdit();
    const target = interactiveVinylTarget(event.target);
    if (target !== event.target) mirrorMaskProxyToOwner(event.target);
    applyDragAxisLock(target);
    snapTargetToGuides(target, { ...event, kloudyTransformAction: "move" });
    applyDragAxisLock(target);
    if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
    syncMaskPreviewForTarget(target);
    scheduleLiveOverlayColor(target);
    if (hybridRenderActive) requestHybridRender();
  });
  ["object:scaling", "object:skewing"].forEach((eventName) => {
    canvas.on(eventName, (event) => {
      if (event.target?.kloudyOverlay) {
        beginHybridRender("source overlay transform");
        constrainSourceOverlayTransform();
        snapSourceOverlayToGuides(event);
        if (hybridRenderActive) requestHybridRender();
        return;
      }
      beginHybridRender(eventName);
      leaveGuideModeForLayerEdit();
      const target = interactiveVinylTarget(event.target);
      if (target !== event.target) mirrorMaskProxyToOwner(event.target);
      snapTargetToGuides(target, { ...event, kloudyTransformAction: eventName === "object:scaling" ? "scale" : "skew" });
      if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
      syncMaskPreviewForTarget(target);
      scheduleLiveOverlayColor(target);
      if (hybridRenderActive) requestHybridRender();
    });
  });
  canvas.on("object:rotating", (event) => {
    if (event.target?.kloudyOverlay) {
      beginHybridRender("source overlay rotate");
      constrainSourceOverlayTransform();
      if (hybridRenderActive) requestHybridRender();
      return;
    }
    beginHybridRender("rotate");
    leaveGuideModeForLayerEdit();
    const target = interactiveVinylTarget(event.target);
    if (target !== event.target) mirrorMaskProxyToOwner(event.target);
    snapRotationToNotches(target, event);
    renderRotationNotchOverlay(target, event);
    if (target) syncSelectedShapeOutlines(undefined, { relayer: false });
    syncMaskPreviewForTarget(target);
    scheduleLiveOverlayColor(target);
    if (hybridRenderActive) requestHybridRender();
  });
  canvas.on("mouse:wheel", (opt) => {
    window.KfpsEditorDiagnostics?.pulse("zoom");
    const delta = opt.e.deltaY;
    let zoom = canvas.getZoom();
    zoom *= 0.999 ** delta;
    zoom = Math.min(Math.max(zoom, 0.04), 8);
    beginHybridRender("zoom");
    canvas.zoomToPoint({ x: opt.e.offsetX, y: opt.e.offsetY }, zoom);
    if (activeToolMode === "guides" && guideDraft && !isPanning) updateGuideDraft(opt);
    styleActiveTransformControls();
    syncSelectedShapeOutlines();
    scheduleVisualGridLayerUpdate();
    updateHud(KfpsFabricAdapter.scenePoint(canvas, opt.e));
    if (hybridRenderActive) {
      requestHybridRender();
      settleHybridRender();
    } else {
      requestCanvasRender();
    }
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
      // Fabric owns touch events; desktop mouse gestures use the capture path.
      if (opt.e.type?.startsWith("touch")) {
        cancelFabricGroupSelection();
        if (!selectGuideObject(opt.target)) beginGuideDraft(opt);
      }
      return;
    }
    if (activeToolMode === "source") {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      if (opt.e.button === 1 || opt.e.button === 2) {
        window.KfpsEditorDiagnostics?.action("pan");
        isPanning = true;
        lastPan = { x: opt.e.clientX, y: opt.e.clientY };
        canvas.selection = false;
        canvas.skipTargetFind = true;
        transformAnchorSnapshot = null;
        setStatus(KfpsI18n.t("Move Reference mode: panning canvas. Left-drag the reference image to move it."));
        return;
      }
      if (!overlayImage) {
        canvas.discardActiveObject();
        setStatus(KfpsI18n.t("Move Reference needs an image first. Add one in Reference controls."));
        return;
      }
      canvas.selection = false;
      transformAnchorSnapshot = null;
      if (opt.target !== overlayImage) {
        canvas.setActiveObject(overlayImage);
        setStatus(KfpsI18n.t("Move Reference only edits the reference image. Drag the image itself to move it."));
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
      window.KfpsEditorDiagnostics?.action("pan");
      isPanning = true;
      lastPan = { x: opt.e.clientX, y: opt.e.clientY };
      canvas.selection = false;
      canvas.skipTargetFind = true;
      transformAnchorSnapshot = null;
      beginHybridRender("pan");
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
      beginHybridRender("pan");
      const vpt = canvas.viewportTransform;
      vpt[4] += opt.e.clientX - lastPan.x;
      vpt[5] += opt.e.clientY - lastPan.y;
      scheduleVisualGridLayerUpdate();
      requestCanvasRender();
      lastPan = { x: opt.e.clientX, y: opt.e.clientY };
      schedulePointerHud(KfpsFabricAdapter.scenePoint(canvas, opt.e), null, "panning");
      return;
    }
    if (guideDraft && activeToolMode === "guides") {
      opt.e.preventDefault();
      opt.e.stopPropagation();
      canvas.selection = false;
      canvas._groupSelector = null;
      updateGuideDraft(opt);
      schedulePointerHud(KfpsFabricAdapter.scenePoint(canvas, opt.e));
      return;
    }
  });
  canvas.on("mouse:move", (opt) => {
    if (!isPanning && opt?.e) {
      schedulePointerHud(KfpsFabricAdapter.scenePoint(canvas, opt.e), opt.target);
    }
  });
  canvas.on("mouse:up", (opt) => {
    if (activeToolMode === "guides" && guideDraft && opt?.e?.type?.startsWith("touch")) finishGuideDraft();
    if (activeToolMode === "guides") canvas._groupSelector = null;
    transformAnchorSnapshot = null;
    dragAxisSnapshot = null;
    clearDragAxisLock();
    clearSnapOverlay();
    finishCanvasPan();
    isPanning = false;
    settleHybridRender();
    canvas.selection = !shapeEyedropperActive && activeToolMode !== "guides" && activeToolMode !== "source";
    canvas.skipTargetFind = vBoxSelectActive;
    canvas.defaultCursor = vBoxSelectActive ? "crosshair" : "default";
    canvas.hoverCursor = vBoxSelectActive ? "crosshair" : "default";
    updateHud();
  });
  installGuidePointerNavigation();
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
    resizeHybridRenderer();
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
    KfpsFabricAdapter.sendObjectToBack(canvas, item);
  });
}

function editorGuideObjects() {
  if (!canvas) return [];
  return guideObjectRegistry.read(canvas.getObjects());
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
  if (activeToolMode === "guides") endGuidePan();
  guideDraft = null;
  guideDraftPress = null;
  guidePointer = null;
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
  guideDraftObject = null;
  canvas.getObjects().filter((obj) => obj.kloudyGuide).forEach((obj) => canvas.remove(obj));
  snapOverlayObjects = [];
  const objects = [];
  updateVisualGridLayer();
  if (guideState.guidesVisible) {
    guideState.guides.forEach((guide) => objects.push(makeGuideLine(guide)));
  }
  if (guideDraft) {
    guideDraftObject = makeGuideLine({ ...guideDraft, id: "__draft__" }, {
      stroke: cssColorVar("--editor-guide-draft", "rgba(42, 26, 36, 0.96)"),
      strokeWidth: 2,
      strokeDashArray: [3, 3],
      selectable: false,
      evented: false,
      objectCaching: false,
    });
    objects.push(guideDraftObject);
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
    if (overlayLayerMode === "above") KfpsFabricAdapter.bringObjectToFront(canvas, overlayImage);
    else KfpsFabricAdapter.sendObjectToBack(canvas, overlayImage);
  }
  syncMaskPreviewOutlines();
  editorGuideObjects().forEach((obj) => KfpsFabricAdapter.bringObjectToFront(canvas, obj));
}

function bringGuidesToBack() {
  layerEditorHelpers();
}

function setOverlayLayerMode(mode) {
  overlayLayerMode = normalizeOverlayLayerMode(mode);
  editorSettings.setItem(OVERLAY_LAYER_MODE_KEY, overlayLayerMode);
  if ($("overlayLayerMode")) $("overlayLayerMode").value = overlayLayerMode;
  layerEditorHelpers();
  canvas?.requestRenderAll();
  setStatus(KfpsI18n.t("Reference image draws {0} vinyl layers.", overlayLayerMode === "above" ? KfpsI18n.t("above") : KfpsI18n.t("below")));
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
    setText("guideStatus", KfpsI18n.t("Source snapped {0}{1}{2} to {3}.", bestX ? KfpsI18n.term(bestX.point) : "", bestX && bestY ? " + " : "", bestY ? KfpsI18n.term(bestY.point) : "", KfpsI18n.term(bestX?.source || bestY?.source)));
  }
  return true;
}

function updateGuideUi() {
  setText("guideCountBadge", KfpsI18n.t("{0} guide{1}", guideState.guides.length, guideState.guides.length === 1 ? "" : "s"));
  setText("guideModeLabel", activeToolMode === "guides"
    ? (selectedGuideId ? KfpsI18n.t("Guide selected. Delete it or draw another line.") : KfpsI18n.t("Click or drag to draw a guide."))
    : KfpsI18n.t("Select the Guides tool to draw lines."));
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
  const constraint = guideState.guideConstraint;
  const end = { ...pointer };
  if (guideState.snapGuideEnd) {
    const snapped = snapPointToGrid(end);
    end.x = snapped.x;
    end.y = snapped.y;
  }
  if (constraint === "horizontal") end.y = anchor.y;
  if (constraint === "vertical") end.x = anchor.x;
  if (event?.shiftKey && constraint === "free") {
    // Project onto the nearest 45-degree ray. Angle lock takes precedence over
    // endpoint-grid snapping when the anchor itself is not on the grid.
    const angle = Math.round(Math.atan2(pointer.y - anchor.y, pointer.x - anchor.x) / (Math.PI / 4)) * Math.PI / 4;
    const dx = Math.cos(angle), dy = Math.sin(angle);
    const distance = (end.x - anchor.x) * dx + (end.y - anchor.y) * dy;
    end.x = anchor.x + distance * dx;
    end.y = anchor.y + distance * dy;
  }
  return end;
}

function guideScenePoint(event) {
  // Fabric caches the pre-zoom pointer for the duration of its wheel event.
  const pointer = event.changedTouches?.[0] || event.touches?.[0] || event;
  const rect = canvas.upperCanvasEl.getBoundingClientRect();
  const point = new fabric.Point((pointer.clientX - rect.left) * canvas.width / rect.width,
    (pointer.clientY - rect.top) * canvas.height / rect.height);
  return fabric.util.transformPoint(point, fabric.util.invertTransform(canvas.viewportTransform));
}

function endGuidePan() {
  if (isPanning) finishCanvasPan();
  isPanning = false;
  lastPan = null;
  guidePanButton = null;
  guideSpacePan = false;
  guideDraftPress = null;
  if (canvas) { canvas.defaultCursor = "crosshair"; canvas.setCursor("crosshair"); }
}

function cancelGuideInteraction() {
  if (activeToolMode !== "guides" && !guideDraft) return;
  endGuidePan();
  guideDraft = null;
  guidePointer = null;
  if (canvas) renderGuideObjects();
}

function installGuidePointerNavigation() {
  const surface = canvas.upperCanvasEl;
  if (!surface.hasAttribute("tabindex")) surface.tabIndex = -1;
  // Own guide gestures before Fabric can start a selection/transform or drop
  // document listeners on an intermediate mouse-button release.
  surface.addEventListener("mousedown", event => {
    if (activeToolMode !== "guides") return;
    event.preventDefault(); event.stopImmediatePropagation();
    // Preventing the pointer default also prevents focus leaving guide inputs.
    surface.focus({ preventScroll: true });
    guidePointer = event;
    if (event.button === 1 || event.button === 2 || guideSpacePan) {
      window.KfpsEditorDiagnostics?.action("pan");
      isPanning = true;
      guidePanButton = event.button;
      lastPan = { x: event.clientX, y: event.clientY };
      guideDraftPress = null;
      canvas.setCursor("grabbing");
      return;
    }
    if (event.button !== 0) return;
    const finishing = Boolean(guideDraft);
    if (!finishing && guideState.guidesVisible) {
      const point = guideScenePoint(event);
      const guide = guideState.guides.slice().reverse().find(line => distancePointToSnapLine(point, line) <= 6 / canvas.getZoom());
      const helper = guide && editorGuideObjects().find(object => object.kloudyGuideId === guide.id);
      if (selectGuideObject(helper)) return;
    }
    cancelFabricGroupSelection();
    if (finishing) updateGuideDraft({ e: event });
    else beginGuideDraft({ e: event });
    guideDraftPress = { x: event.clientX, y: event.clientY, finishing };
  }, true);
  document.addEventListener("mousemove", event => {
    if (activeToolMode !== "guides") return;
    if (!isPanning && !guideDraftPress && event.target !== surface) { guidePointer = null; return; }
    event.preventDefault(); event.stopImmediatePropagation();
    guidePointer = event;
    if (isPanning && lastPan) {
      const vpt = canvas.viewportTransform;
      vpt[4] += event.clientX - lastPan.x;
      vpt[5] += event.clientY - lastPan.y;
      lastPan = { x: event.clientX, y: event.clientY };
      canvas.calcViewportBoundaries();
      scheduleVisualGridLayerUpdate();
      requestCanvasRender();
    } else if (guideDraft) updateGuideDraft({ e: event });
    schedulePointerHud(guideScenePoint(event), null, isPanning ? "panning" : null);
  }, true);
  document.addEventListener("mouseup", event => {
    if (activeToolMode !== "guides" || (!isPanning && !guideDraftPress)) return;
    event.preventDefault(); event.stopImmediatePropagation();
    guidePointer = event;
    if (isPanning) {
      if (!guideSpacePan && event.button === guidePanButton) endGuidePan();
      return;
    }
    if (event.button !== 0) return;
    const press = guideDraftPress;
    guideDraftPress = null;
    updateGuideDraft({ e: event });
    if (press.finishing || Math.hypot(event.clientX - press.x, event.clientY - press.y) >= 8) finishGuideDraft();
    else setGuideStatus(KfpsI18n.t("Guide start placed. Click the endpoint; Shift snaps to 45 degrees. Escape cancels."));
  }, true);
}

function beginGuideDraft(opt) {
  window.KfpsEditorDiagnostics?.pulse("guide");
  const pointer = guideScenePoint(opt.e);
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
  window.KfpsEditorDiagnostics?.pulse("guide");
  const pointer = guideScenePoint(opt.e);
  const end = constrainedGuideEnd({ x: guideDraft.x1, y: guideDraft.y1 }, pointer, opt.e);
  guideDraft.x2 = end.x;
  guideDraft.y2 = end.y;
  if (guideDraftObject) {
    guideDraftObject.set({ x1: guideDraft.x1, y1: guideDraft.y1, x2: end.x, y2: end.y });
    guideDraftObject.setCoords();
    requestCanvasRender();
  } else renderGuideObjects();
}

function finishGuideDraft() {
  guideDraftPress = null;
  if (!guideDraft) return;
  const zoom = Math.max(canvas.getZoom() || 1, 0.001);
  const length = Math.hypot(guideDraft.x2 - guideDraft.x1, guideDraft.y2 - guideDraft.y1);
  if (length < 8 / zoom) {
    guideDraft = null;
    renderGuideObjects();
    setGuideStatus(KfpsI18n.t("Guide was too short and was discarded."));
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
  setGuideStatus(KfpsI18n.t("Added {0} guide. Hold Control while moving shapes to snap.", KfpsI18n.term(guide.constraint)));
}

function selectGuideObject(object) {
  if (!object?.kloudyGuideManual) return false;
  selectedGuideId = object.kloudyGuideId;
  canvas.discardActiveObject();
  renderGuideObjects();
  setGuideStatus(KfpsI18n.t("Guide selected. Press Delete or use Delete Selected Guide to remove it."));
  return true;
}

function deleteSelectedGuide() {
  if (!selectedGuideId) {
    setGuideStatus(KfpsI18n.t("No guide selected. Switch to Guides and click a guide line first."));
    return;
  }
  ensureHistoryBaseline();
  const before = guideState.guides.length;
  guideState.guides = guideState.guides.filter((guide) => guide.id !== selectedGuideId);
  selectedGuideId = null;
  renderGuideObjects();
  if (before !== guideState.guides.length) {
    pushHistory("delete guide");
    setGuideStatus(KfpsI18n.t("Deleted selected guide."));
  } else {
    saveGuideAutosave();
    setGuideStatus(KfpsI18n.t("Selected guide was already gone."));
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
  setGuideStatus(KfpsI18n.t("Cleared guide lines. Grid settings were kept."));
}

function syncGuideStateFromUi() {
  ensureHistoryBaseline();
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
  pushHistory("guide settings", { changedObjects: [] });
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
    console.warn(KfpsI18n.t("Guide autosave skipped."), err);
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
    return KfpsFabricAdapter.scenePoint(canvas, domEvent);
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
  const label = axis === "x" ? KfpsI18n.t("X / horizontal") : KfpsI18n.t("Y / vertical");
  setStatus(KfpsI18n.t("Axis lock active: {0}. Release {1} to drag freely.", label, axis.toUpperCase()));
}

function clearDragAxisLock(axis = null) {
  if (axis && dragAxisLock !== axis) return;
  const hadLock = Boolean(dragAxisLock);
  dragAxisLock = null;
  if (hadLock) setStatus(KfpsI18n.t("Axis lock released."));
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
  snapOverlayObjects.slice().forEach((object) => {
    if (object?.canvas === canvas || canvas.getObjects().includes(object)) canvas.remove(object);
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
    setText("guideStatus", KfpsI18n.t("Rotation notch: {0} deg.", round(notch)));
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
        ? KfpsI18n.t("Resize anchored: {0} side stays fixed; pulled {1} side snapped to {2}.", KfpsI18n.message(sideSnap.anchorKind || KfpsI18n.t("opposite")), KfpsI18n.message(contact.kind), KfpsI18n.message(sideSnap.line.source || KfpsI18n.t("guide")))
        : KfpsI18n.t("{0} anchored: {1} side stays fixed while the pulled {2} side changes.", transformAction === "skew" ? KfpsI18n.t("Skew") : KfpsI18n.t("Resize"), KfpsI18n.message(anchorResult?.anchorKind || KfpsI18n.t("opposite")), KfpsI18n.message(contact.kind)));
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
      setText("guideStatus", KfpsI18n.t("Snapped {0} edge to angled guide{1}.", KfpsI18n.message(contact.kind), allowAngledRotation && isSingleVinylShape ? KfpsI18n.t(" and rotated to {0} deg", round(target.angle || 0)) : KfpsI18n.t(" without rotating during resize/skew")));
    } else {
      setText("guideStatus", KfpsI18n.t("Snapped {0}{1}{2} to {3}.", bestX ? KfpsI18n.term(bestX.point) : "", bestX && bestY ? " + " : "", bestY ? KfpsI18n.term(bestY.point) : "", KfpsI18n.term(bestX?.source || bestY?.source)));
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
    const rect = KfpsFabricAdapter.sceneBounds(obj);
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
    const rect = KfpsFabricAdapter.sceneBounds(obj);
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
    setStatus(KfpsI18n.t("Select a layer before using Fit Selected."));
    return;
  }
  fitObjectsView(objects);
  setStatus(KfpsI18n.t("Fit view to {0} selected layer(s).", objects.length));
}

async function loadJsonFile(file) {
  const generation = beginDocumentLoad();
  setBusy(KfpsI18n.t("Loading JSON: {0}", file.name));
  await nextFrame();
  const payload = await editorPersistence.request("parseFile", { file });
  return loadPayload(payload, { generation, name: cleanProjectBaseName(file.name, "vinyl"), projectName: null });
}

function formatBrowserDate(mtime) {
  const numeric = Number(mtime);
  if (!Number.isFinite(numeric) || numeric <= 0) return KfpsI18n.t("unknown date");
  return new Date(numeric * 1000).toLocaleString(KfpsI18n.locale);
}

function layerLabel(count) {
  const numeric = Number(count) || 0;
  return KfpsI18n.t("{0} layer{1}", numeric.toLocaleString(), numeric === 1 ? "" : "s");
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
  if (source === "editor") return KfpsI18n.t("Editor export");
  if (source === "exported") return KfpsI18n.t("Exported JSON");
  return KfpsI18n.t("Generated final run");
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
    empty.textContent = KfpsI18n.t("Preview unavailable");
  };
  if (!entry?.preview_url) {
    image.hidden = true;
    empty.hidden = false;
    empty.textContent = KfpsI18n.t("No preview selected");
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
      empty.textContent = KfpsI18n.t("No editor exports found. Export from the editor into imgs/editor, then click Refresh.");
    } else if (jsonBrowserState.source === "exported") {
      empty.textContent = KfpsI18n.t("No exported JSONs found. Drop downloaded, shared, or game-exported JSONs into imgs/exported, then click Refresh.");
    } else {
      empty.textContent = KfpsI18n.t("No generated final JSONs found yet. Generate a vinyl first, then click Refresh.");
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
    thumb.alt = KfpsI18n.t("{0} preview", group.title || group.key || "JSON");
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
    title.textContent = group.title || group.key || KfpsI18n.t("Untitled JSON");
    const kind = document.createElement("span");
    kind.textContent = group.source === "generated"
      ? KfpsI18n.t("{0} finalized JSON{1}", group.count || 0, group.count === 1 ? "" : "s")
      : jsonBrowserSourceLabel(group.source);
    const layers = document.createElement("span");
    layers.textContent = KfpsI18n.t("{0} max", layerLabel(group.max_layers || 0));
    const modified = document.createElement("span");
    modified.textContent = formatBrowserDate(group.mtime);
    button.append(thumb, title, kind, layers, modified);
    button.addEventListener("click", () => {
      jsonBrowserState.selectedGroupIndex = index;
      jsonBrowserState.selectedEntryIndex = group.entries?.length ? 0 : -1;
      setBrowserActiveRow(container, ".jsonBrowserCard", index);
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
    setText("jsonBrowserTitle", KfpsI18n.t("Select a source"));
    setText("jsonBrowserMeta", KfpsI18n.t("JSON folders are sorted newest first. Files are sorted high layer count to low."));
    setJsonBrowserPreview(null);
    setJsonBrowserStatus(KfpsI18n.t("Choose a source on the left."));
    return;
  }
  setText("jsonBrowserTitle", group.title || group.key);
  setText("jsonBrowserMeta", KfpsI18n.t("{0} - {1} - select any JSON below to preview and import it.", jsonBrowserSourceLabel(group.source), formatBrowserDate(group.mtime)));
  setJsonBrowserPreview(selectedJsonBrowserEntry());
  (group.entries || []).forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `jsonBrowserEntry${index === jsonBrowserState.selectedEntryIndex ? " active" : ""}`;
    const textWrap = document.createElement("span");
    const name = document.createElement("b");
    name.title = entry.name || "";
    name.textContent = entry.name || KfpsI18n.t("Untitled JSON");
    const path = document.createElement("span");
    path.textContent = entry.id || "";
    textWrap.append(name, path);
    const layers = document.createElement("span");
    layers.className = "jsonBrowserLayerPill";
    layers.textContent = layerLabel(entry.layers);
    button.append(textWrap, layers);
    button.addEventListener("click", () => {
      jsonBrowserState.selectedEntryIndex = index;
      setBrowserActiveRow(container, ".jsonBrowserEntry", index);
      setJsonBrowserPreview(entry);
    });
    button.addEventListener("dblclick", () => importSelectedBrowserJson());
    container.appendChild(button);
  });
  $("selectJsonBrowserEntry").disabled = !selectedJsonBrowserEntry();
  setJsonBrowserStatus(selectedJsonBrowserEntry() ? KfpsI18n.t("Choose Select JSON or double-click a row.") : KfpsI18n.t("This source has no JSON entries."));
}

function setBrowserActiveRow(container, selector, selectedIndex) {
  container.querySelectorAll(selector).forEach((row, index) => {
    row.classList.toggle("active", index === selectedIndex);
  });
}

async function refreshJsonBrowser() {
  jsonBrowserState.request?.abort();
  const request = new AbortController();
  jsonBrowserState.request = request;
  const timeout = setTimeout(() => request.abort(), 15000);
  jsonBrowserState.loading = true;
  setText("jsonBrowserSummary", KfpsI18n.t("Loading JSON browser..."));
  setJsonBrowserStatus(KfpsI18n.t("Scanning app folders..."));
  try {
    const source = $("jsonBrowserSource")?.value || "generated";
    jsonBrowserState.source = source;
    const response = await fetch(`${JSON_BROWSER_API}?source=${encodeURIComponent(source)}`, { cache: "no-store", signal: request.signal });
    const data = await response.json();
    if (jsonBrowserState.request !== request) return;
    if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
    jsonBrowserState.groups = Array.isArray(data.groups) ? data.groups : [];
    jsonBrowserState.selectedGroupIndex = jsonBrowserState.groups.length ? 0 : -1;
    jsonBrowserState.selectedEntryIndex = jsonBrowserState.groups[0]?.entries?.length ? 0 : -1;
    setText("jsonBrowserSummary", KfpsI18n.t("{0} JSON{1} found in {2}.", data.total_entries || 0, data.total_entries === 1 ? "" : "s", jsonBrowserSourceFolder(source)));
    renderJsonBrowserGroups();
    renderJsonBrowserEntries();
  } catch (err) {
    if (jsonBrowserState.request !== request) return;
    console.error(err);
    jsonBrowserState.groups = [];
    jsonBrowserState.selectedGroupIndex = -1;
    jsonBrowserState.selectedEntryIndex = -1;
    renderJsonBrowserGroups();
    renderJsonBrowserEntries();
    setText("jsonBrowserSummary", KfpsI18n.t("JSON browser failed to load."));
    setJsonBrowserStatus(err.message || String(err));
  } finally {
    clearTimeout(timeout);
    if (jsonBrowserState.request === request) {
      jsonBrowserState.request = null;
      jsonBrowserState.loading = false;
    }
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
  if (jsonBrowserState.loading) return;
  const entry = selectedJsonBrowserEntry();
  if (!entry) {
    setJsonBrowserStatus(KfpsI18n.t("Select a JSON first."));
    return;
  }
  if (!await confirmWorkspaceReplacement(entry.name || KfpsI18n.t("the selected JSON"))) {
    setJsonBrowserStatus(KfpsI18n.t("Current unsaved work was kept."));
    return;
  }
  setJsonBrowserStatus(KfpsI18n.t("Loading {0}...", entry.name));
  setBusy(KfpsI18n.t("Loading JSON: {0}", entry.name));
  const generation = beginDocumentLoad();
  await nextFrame();
  try {
    const data = await readEditorDocument(`${JSON_FILE_API}?id=${encodeURIComponent(entry.id)}`);
    if (!await loadPayload(data.payload, { generation, name: cleanProjectBaseName(entry.name, "vinyl"), projectName: null })) return;
    $("jsonBrowserDialog")?.close();
    setStatus(KfpsI18n.t("Imported {0} from {1}.", entry.name, jsonBrowserSourceFolder()));
  } catch (err) {
    if (generation !== documentGeneration) return;
    showError(KfpsI18n.t("JSON browser import failed"), err);
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
    empty.textContent = KfpsI18n.t("No saved projects found yet. Use Save to create an editable project.");
    container.appendChild(empty);
    setProjectBrowserStatus(KfpsI18n.t("No internal project saves found."));
    return;
  }
  projectBrowserState.entries.forEach((entry, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `projectBrowserEntry${index === projectBrowserState.selectedIndex ? " active" : ""}`;
    const textWrap = document.createElement("span");
    const title = document.createElement("b");
    title.textContent = entry.title || entry.name || KfpsI18n.t("Untitled project");
    const meta = document.createElement("span");
    meta.textContent = `${layerLabel(entry.layers)} - ${formatBrowserDate(entry.mtime)}`;
    textWrap.append(title, meta);
    const file = document.createElement("span");
    file.textContent = entry.name || "";
    button.append(textWrap, file);
    button.addEventListener("click", () => {
      projectBrowserState.selectedIndex = index;
      setBrowserActiveRow(container, ".projectBrowserEntry", index);
      setProjectBrowserStatus(KfpsI18n.t("Choose Load Project or double-click a project."));
    });
    button.addEventListener("dblclick", () => loadSelectedProject());
    container.appendChild(button);
  });
  setProjectBrowserStatus(selected ? KfpsI18n.t("Choose Load Project or double-click a project.") : KfpsI18n.t("Select a project."));
}

async function refreshProjectBrowser() {
  if (projectBrowserState.loading) return;
  projectBrowserState.loading = true;
  setText("projectBrowserSummary", KfpsI18n.t("Loading internal projects..."));
  setProjectBrowserStatus(KfpsI18n.t("Scanning runtime/fabric-editor/projects..."));
  try {
    const response = await fetch(PROJECT_BROWSER_API, { cache: "no-store", signal: AbortSignal.timeout(15000) });
    const data = await response.json();
    if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
    projectBrowserState.entries = Array.isArray(data.entries) ? data.entries : [];
    projectBrowserState.selectedIndex = projectBrowserState.entries.length ? 0 : -1;
    setText("projectBrowserSummary", KfpsI18n.t("{0} project{1} saved inside KFPS.", data.total_entries || 0, data.total_entries === 1 ? "" : "s"));
    renderProjectBrowser();
  } catch (err) {
    console.error(err);
    projectBrowserState.entries = [];
    projectBrowserState.selectedIndex = -1;
    renderProjectBrowser();
    setText("projectBrowserSummary", KfpsI18n.t("Project browser failed to load."));
    setProjectBrowserStatus(err.message || String(err));
  } finally {
    projectBrowserState.loading = false;
  }
}

async function openProjectFolder() {
  const button = $("openProjectFolder");
  if (button) button.disabled = true;
  setProjectBrowserStatus(KfpsI18n.t("Opening internal project folder..."));
  try {
    const response = await fetch(PROJECT_OPEN_FOLDER_API, {
      method: "POST",
      headers: EDITOR_MUTATION_HEADERS,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
    setProjectBrowserStatus(KfpsI18n.t("Project folder opened. Drop .fabric-project.json files there, then click Refresh."));
  } catch (err) {
    showError(KfpsI18n.t("Open project folder failed"), err);
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
    setProjectBrowserStatus(KfpsI18n.t("Select a project first."));
    return;
  }
  if (!await confirmWorkspaceReplacement(entry.title || entry.name || KfpsI18n.t("the selected project"))) {
    setProjectBrowserStatus(KfpsI18n.t("Current unsaved work was kept."));
    return;
  }
  setProjectBrowserStatus(KfpsI18n.t("Loading {0}...", entry.title || entry.name));
  try {
    const generation = beginDocumentLoad();
    const data = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`);
    if (!await loadProjectPayload(data.payload, entry.title || entry.name, { generation })) return;
    $("projectBrowserDialog")?.close();
    clearBusy(KfpsI18n.t("Loaded project: {0}", entry.title || entry.name));
  } catch (err) {
    showError(KfpsI18n.t("Project load failed"), err);
    setProjectBrowserStatus(err.message || String(err));
  }
}

async function loadStartupProjectFromQuery() {
  const projectId = startupProjectId();
  if (!projectId) return false;
  setBusy(KfpsI18n.t("Loading selected project..."));
  try {
    const generation = beginDocumentLoad();
    const data = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(projectId)}`);
    if (!await loadProjectPayload(data.payload, data.name || "project", { generation })) return true;
    clearBusy(KfpsI18n.t("Loaded project: {0}", data.name || projectId));
    return true;
  } catch (err) {
    clearBusy(KfpsI18n.t("Project load failed."));
    showError(KfpsI18n.t("Project load failed"), err);
    return false;
  }
}

function beginDocumentLoad() {
  pixelArtAnalysisCancel?.();
  recoveryRestoreDepth = 0;
  return ++documentGeneration;
}

async function loadPayload(payload, options = {}) {
  const generation = options.generation ?? beginDocumentLoad();
  if (generation !== documentGeneration) return false;
  const strict = options.strict ?? (recoveryRestoreDepth > 0);
  const shapes = Array.isArray(payload.shapes) ? payload.shapes : null;
  if (!shapes) throw new Error(KfpsI18n.t("JSON must contain a shapes list."));
  const emptyProject = strict && shapes.length === 0;
  if (!shapes.length && !emptyProject) throw new Error(KfpsI18n.t("JSON shapes list is empty."));
  const hasLegacyGeometry = shapes.some((shape) => LEGACY_RECTANGLE_TYPES.has(Number(shape?.type)) || LEGACY_ELLIPSE_TYPES.has(Number(shape?.type)));
  const legacyOffset = hasLegacyGeometry ? computeLegacyOffset(shapes) : { x: 0, y: 0 };
  const normalized = assignUniqueEditorIds(
    shapes.map((shape, index) => normalizeInputShape(shape, index, legacyOffset)).filter(Boolean),
  );
  if (strict && normalized.length !== shapes.length) {
    throw new Error(KfpsI18n.t("Some saved layers are invalid. The current canvas and recovery checkpoint were kept."));
  }
  if (!normalized.length && !emptyProject) throw new Error(KfpsI18n.t("JSON did not contain any usable FH6 vinyl layers."));
  if (normalized.length > MAX_VINYL_LAYERS) {
    throw new Error(KfpsI18n.t("This design has {0} editable layers. The editor supports up to {1} layers per vinyl.", normalized.length, MAX_VINYL_LAYERS));
  }
  setBusy(KfpsI18n.t("Building {0} editable layer(s)...", normalized.length));
  await nextFrame();
  let completed = 0;
  let failed = 0;
  const results = await KfpsEditorCore.mapWithConcurrency(
    normalized,
    OBJECT_BUILD_CONCURRENCY,
    async (shape) => {
      try {
        if (generation !== documentGeneration) return null;
        return await makeFabricObject(shape);
      } catch (err) {
        failed += 1;
        console.warn(err);
        return null;
      } finally {
        completed += 1;
        if (generation === documentGeneration && (completed % 100 === 0 || completed === normalized.length)) {
          setBusy(KfpsI18n.t("Building layers: {0}/{1}", completed - failed, normalized.length));
          await nextFrame();
        }
      }
    },
  );
  const builtObjects = results.filter(Boolean);
  if (generation !== documentGeneration) {
    builtObjects.forEach(discardFabricObject);
    return false;
  }
  if (strict && failed) {
    builtObjects.forEach(discardFabricObject);
    throw new Error(KfpsI18n.t("Some saved layers could not be restored. The current canvas and recovery checkpoint were kept."));
  }
  if (!builtObjects.length && !emptyProject) {
    throw new Error(KfpsI18n.t("JSON did not contain any loadable FH6 vinyl layers. Failed to build {0}/{1}. Current canvas was left unchanged.", failed, normalized.length));
  }
  try {
    await prewarmHybridMeshesForObjects(builtObjects);
    if (generation !== documentGeneration) {
      builtObjects.forEach(discardFabricObject);
      return false;
    }
    builtObjects.forEach((object) => canvas.add(object));
  } catch (error) {
    builtObjects.forEach(discardFabricObject);
    throw error;
  }
  clearVinylObjects({ keep: new Set(builtObjects) });
  clearSourceOverlayState();
  overlayRevision = 0;
  savedOverlayRevision = 0;
  applySavedGuideState(null);
  if (options.name !== undefined) loadedName = options.name;
  if (options.projectName !== undefined) currentProjectName = options.projectName;
  resetHistory({ preserveGeneration: true });
  if (Array.isArray(payload.editor_collapsed_groups)) applyCollapsedLayerGroups(payload.editor_collapsed_groups);
  else collapsedLayerGroups.clear();
  bringGuidesToBack();
  syncCanvasObjectCoords();
  refreshLayers();
  fitDesignView();
  hybridRenderNow();
  establishLoadedHistoryBoundary("loaded source");
  clearBusy(KfpsI18n.t("Loaded {0}/{1} editable FH6 layer(s).{2}", builtObjects.length, normalized.length, failed ? KfpsI18n.t(" Failed: {0}.", failed) : ""));
  return true;
}

function removeVinylObjectHelpers(object) {
  restoreSelectionOutline(object);
  selectedShapeOutlineObjects.delete(object);
  [selectedShapeOutlineHelpers, maskPreviewOutlines, maskPreviewCutouts].forEach((helpers) => {
    const helper = helpers.get(object);
    helpers.delete(object);
    if (helper) canvas.remove(helper);
  });
}

function discardFabricObject(object) {
  if (!object) return;
  canvas.remove(object);
  // These backing stores belong to this instance; source/resource images may be shared.
  for (const key of ["_cacheCanvas", "_filteredEl"]) {
    const element = object[key];
    if (element instanceof HTMLCanvasElement && element !== object._originalElement) {
      element.width = 1;
      element.height = 1;
    }
  }
  object.dispose?.();
}

function clearVinylObjects(options = {}) {
  cancelEditorTransform();
  endHybridRenderNow();
  canvas.discardActiveObject();
  selectedShapeOutlineObjects.forEach(restoreSelectionOutline);
  selectedShapeOutlineObjects.clear();
  selectedShapeOutlineHelpers.forEach((helper) => canvas.remove(helper));
  selectedShapeOutlineHelpers.clear();
  maskPreviewOutlines.forEach((outline) => canvas.remove(outline));
  maskPreviewOutlines.clear();
  maskPreviewCutouts.forEach((cutout) => canvas.remove(cutout));
  maskPreviewCutouts.clear();
  canvas.getObjects().filter((object) => object.kloudySelectionOutlineHelper
    || object.kloudyMaskOutline || object.kloudyMaskCutout).forEach((helper) => canvas.remove(helper));
  vinylObjects().slice().forEach((object) => { if (!options.keep?.has(object)) discardFabricObject(object); });
  invalidateLayerStats();
  if (!options.preserveCollapsed) collapsedLayerGroups.clear();
  lastLayerListKey = null;
  dropperPreservedActiveObject = null;
}

function vinylObjects() {
  if (!canvas) return [];
  return vinylObjectRegistry.read(canvas.getObjects());
}

function invalidateVinylObjectRegistry() {
  vinylObjectRegistry.invalidate();
  invalidateLayerStats();
}

function remainingLayerCapacity() {
  return Math.max(0, MAX_VINYL_LAYERS - vinylObjects().length);
}

function requireLayerCapacity(additionalLayers, action = "add layers") {
  const requested = Math.max(0, Math.floor(Number(additionalLayers)) || 0);
  const available = remainingLayerCapacity();
  if (requested <= available) return true;
  setStatus(KfpsI18n.t("Cannot {0}: {1} new layer(s) would exceed the {2}-layer maximum. {3} slot(s) remain.", KfpsI18n.term(action), requested, MAX_VINYL_LAYERS, available));
  return false;
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
  button.textContent = selectionLockActive ? KfpsI18n.t("Selection Locked") : KfpsI18n.t("Lock Selection");
}

function releaseSelectionLock(message = KfpsI18n.t("Selection lock released.")) {
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
    releaseSelectionLock(KfpsI18n.t("Selection lock released because the locked layer no longer exists."));
    return false;
  }
  const selected = selectedVinylObjects();
  if (selectionSetEquals(selected, objects)) return false;
  setActiveObjectsForSelectionLock(objects);
  setStatus(KfpsI18n.t("Selection lock kept {0} layer(s) selected after {1}. Unlock to choose something else.", objects.length, KfpsI18n.message(reason)));
  return true;
}

function toggleSelectionLock() {
  if (selectionLockActive) {
    releaseSelectionLock();
    return;
  }
  const selected = selectedVinylObjects();
  if (!selected.length) {
    setStatus(KfpsI18n.t("Select one or more layers before locking the selection."));
    return;
  }
  selectionLockActive = true;
  selectionLockObjects = [...selected];
  updateSelectionLockButton();
  setStatus(KfpsI18n.t("Selection locked to {0} layer(s). Misclicks will keep this selection.", selected.length));
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
    setStatus(KfpsI18n.t("Invert box select found no layers outside the box."));
    return false;
  }
  selectionInvertLocked = true;
  if (inverted.length === 1) canvas.setActiveObject(inverted[0]);
  else canvas.setActiveObject(styledActiveSelection(inverted));
  selectionInvertLocked = false;
  canvas.requestRenderAll();
  setStatus(KfpsI18n.t("Invert box selected {0} layer(s) outside the drag box.", inverted.length));
  return true;
}

function handleSelectionChanged(event = null) {
  if (selectionLockActive && !selectionLockRestoring && restoreSelectionLock(KfpsI18n.t("a selection change"))) {
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
  return object?.kloudy?.group_name || KfpsI18n.t("Layer Group");
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
  const entry = layerListRows.get(key) || {
    key,
    objects: objects.filter(Boolean),
    displayIndex,
  };
  entry.element = element;
  layerListRows.set(key, entry);
  element.addEventListener("pointerdown", handleLayerPointerDown);
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
    return groupName ? `${groupName} (${objects.length})` : KfpsI18n.t("{0} layers", objects.length);
  }
  return objects[0]?.kloudy?.name || KfpsI18n.t("1 layer");
}

function layerDragModeLabel(mode) {
  return mode === "group" ? KfpsI18n.t("Group layers") : KfpsI18n.t("Move depth");
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
  return $("layersViewport") || $("layersPane");
}

function scheduleVirtualLayerRender() {
  if (layerVirtualRenderFrame) return;
  layerVirtualRenderFrame = requestAnimationFrame(() => {
    layerVirtualRenderFrame = null;
    renderVirtualLayerWindow();
  });
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
  layerListEntries.forEach((entry) => {
    const key = entry.key;
    if (!entry?.objects?.length) return;
    if (isGroupLayerKey(key)) {
      const objects = entry.objects
        .filter((obj) => displayIndex.has(obj))
        .sort((a, b) => displayIndex.get(a) - displayIndex.get(b));
      if (!objects.length) return;
      objects.forEach((obj) => seen.add(obj));
      blocks.push({ key, objects, element: entry.element || null });
      return;
    }
    const object = entry.objects[0];
    if (!object || seen.has(object)) return;
    seen.add(object);
    blocks.push({ key, objects: [object], element: entry.element || null });
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
    .filter((block) => block.objects.length);
}

function layerDropSlotAtPoint(event) {
  if (!layerDragState || layerDragState.mode !== "reorder") return null;
  if (layerSearchActive()) return null;
  const pane = layerScrollPane();
  const paneRect = pane?.getBoundingClientRect();
  if (!paneRect || event.clientX < paneRect.left || event.clientX > paneRect.right || event.clientY < paneRect.top || event.clientY > paneRect.bottom) return null;
  const blocks = reorderCandidateBlocks(layerDragState.objects);
  if (!blocks.length) return { index: 0, blocks };
  const rows = blocks
    .map((block, index) => ({ block, index, rect: block.element?.isConnected ? block.element.getBoundingClientRect() : null }))
    .filter((row) => row.rect);
  if (!rows.length) return null;
  let nearest = rows[0];
  let nearestDistance = Infinity;
  rows.forEach((row) => {
    const center = row.rect.top + row.rect.height / 2;
    const distance = event.clientY < row.rect.top
      ? row.rect.top - event.clientY
      : event.clientY > row.rect.bottom
        ? event.clientY - row.rect.bottom
        : Math.abs(event.clientY - center) * 0.01;
    if (distance < nearestDistance) {
      nearest = row;
      nearestDistance = distance;
    }
  });
  const after = event.clientY >= nearest.rect.top + nearest.rect.height / 2;
  return {
    index: nearest.index + (after ? 1 : 0),
    blocks,
    markerBlock: nearest.block,
    markerSide: after ? "after" : "before",
  };
}

function updateLayerDropPreview(event) {
  if (!layerDragState) return null;
  clearLayerDropPreview();
  layerDragState.dropSlot = null;
  if (layerDragState.mode === "reorder") {
    if (layerSearchActive()) {
      setStatus(KfpsI18n.t("Clear the layer search before dragging layers; filtered rows cannot safely define canvas depth."));
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
  scheduleVirtualLayerRender();
}

function handleLayerDragWheel(event) {
  if (!layerDragState) return;
  const pane = layerScrollPane();
  if (!pane) return;
  pane.scrollTop += event.deltaY;
  renderVirtualLayerWindow();
  updateLayerDropPreview(event);
  event.preventDefault();
}

function selectLayerEntry(entry) {
  if (!entry?.objects?.length) return;
  if (entry.objects.length === 1) selectObjects(entry.objects, "layer");
  else selectObjects(entry.objects, KfpsI18n.t("layer group"));
}

function selectLayerEntryByKey(key, reason = "layer") {
  const entry = layerListRows.get(key);
  if (!entry) return false;
  selectLayerEntry(entry);
  lastLayerListKey = key;
  setStatus(entry.objects.length > 1 ? KfpsI18n.t("Selected {0} layer(s) by {1}.", entry.objects.length, KfpsI18n.message(reason)) : KfpsI18n.t("Selected 1 layer by {0}.", KfpsI18n.message(reason)));
  return true;
}

function clearLayerSelection(reason = "layer multi-select") {
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  updateSelectionPanel();
  updateLayerSelectionStyles();
  setStatus(KfpsI18n.t("Cleared selection by {0}.", KfpsI18n.message(reason)));
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
  setStatus(KfpsI18n.t("Selected {0} layer(s) by {1}.", next.length, KfpsI18n.message(reason)));
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
  selectObjects(selected, KfpsI18n.t("layer range"));
  lastLayerListKey = endKey;
  setStatus(KfpsI18n.t("Selected layer range: {0} layer(s).", selected.length));
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
    setStatus(KfpsI18n.t("Drag across at least two layers to create an editor group."));
    return false;
  }
  selectObjects(range, KfpsI18n.t("layer drag group"));
  groupSelectedLayers();
  return true;
}

function dropLayerBlockAtSlot(dragObjects, slot) {
  const selectedSet = new Set(dragObjects || []);
  if (!selectedSet.size || !slot) return false;
  if (layerSearchActive()) {
    setStatus(KfpsI18n.t("Clear the layer search before dragging layers; filtered rows cannot safely define canvas depth."));
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
    setStatus(KfpsI18n.t("Layer order unchanged."));
    return false;
  }
  setVinylStackOrder(nextDisplay.slice().reverse());
  selectObjects(sourceObjects, sourceObjects.length > 1 ? KfpsI18n.t("moved layer group") : KfpsI18n.t("moved layer"));
  refreshLayers();
  pushHistory("layer drag reorder");
  setStatus(KfpsI18n.t("Moved {0} in the layer stack.", sourceObjects.length > 1 ? KfpsI18n.t("{0} layers", sourceObjects.length) : KfpsI18n.t("1 layer")));
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
  document.addEventListener("pointermove", handleLayerPointerMove, true);
  document.addEventListener("pointerup", handleLayerPointerUp, true);
  document.addEventListener("pointercancel", cancelLayerDrag, true);
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
    if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(state.key, KfpsI18n.t("layer multi-select"))) {
      event.preventDefault();
      return;
    }
    selectLayerEntryByKey(state.key, KfpsI18n.t("layer row"));
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
  document.removeEventListener("pointermove", handleLayerPointerMove, true);
  document.removeEventListener("pointerup", handleLayerPointerUp, true);
  document.removeEventListener("pointercancel", cancelLayerDrag, true);
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


function scheduleRefreshLayers(options = {}) {
  if (!options.geometryOnly) layerRefreshNeedsStructure = true;
  if (layerRefreshFrame) return;
  layerRefreshFrame = requestAnimationFrame(() => {
    layerRefreshFrame = null;
    const rebuild = layerRefreshNeedsStructure;
    layerRefreshNeedsStructure = false;
    if (rebuild) refreshLayers();
    else {
      invalidateLayerStats();
      renderVirtualLayerWindow(true);
      scheduleExportValidation();
      updateHud();
    }
  });
}


function createVirtualLayerElement(entry, activeSet) {
  if (entry.kind === "group") {
    const li = document.createElement("li");
    const active = entry.objects.some((object) => activeSet.has(object));
    li.className = `layerGroupRow${active ? " active" : ""}${entry.collapsed ? " collapsed" : ""}`;
    li.innerHTML = KfpsI18n.t("\n      <button class=\"layerGroupTwist\" type=\"button\" title=\"{0}\">{1}</button>\n      <span class=\"layerGroupTitle\">{2}</span>\n      <span class=\"layerGroupMeta\">{3} layers | {4} | {5}</span>\n      <button class=\"layerIcon layerGroupVisibility\" type=\"button\" title=\"Hide/show this group\">{6}</button>\n      <button class=\"layerIcon layerGroupLock\" type=\"button\" title=\"Lock/unlock this group\">{7}</button>\n    ", entry.collapsed ? KfpsI18n.t("Expand group") : KfpsI18n.t("Collapse group"), entry.collapsed ? "+" : "-", escapeHtml(entry.groupName), entry.objects.length, entry.visibility.hidden ? KfpsI18n.t("{0} hidden", entry.visibility.hidden) : KfpsI18n.t("visible"), entry.locks.locked ? KfpsI18n.t("{0} locked", entry.locks.locked) : KfpsI18n.t("unlocked"), entry.visibility.visible ? "V" : "H", entry.locks.unlocked ? "U" : "L");
    li.querySelector(".layerGroupTwist").addEventListener("click", (event) => {
      event.stopPropagation();
      setCollapsedGroup(entry.groupId, !entry.collapsed);
    });
    li.querySelector(".layerGroupVisibility").addEventListener("click", (event) => {
      event.stopPropagation();
      selectObjects(entry.objects, entry.groupName);
      toggleSelectedGroupVisibility();
    });
    li.querySelector(".layerGroupLock").addEventListener("click", (event) => {
      event.stopPropagation();
      selectObjects(entry.objects, entry.groupName);
      toggleSelectedGroupLock();
    });
    li.addEventListener("click", (event) => {
      if (suppressLayerClick) return;
      if (event.shiftKey && lastLayerListKey && selectLayerRangeByKeys(lastLayerListKey, entry.key)) return;
      if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(entry.key, KfpsI18n.t("layer multi-select"))) return;
      selectObjects(entry.objects, entry.groupName);
      lastLayerListKey = entry.key;
    });
    registerLayerListRow(li, entry.key, entry.objects, entry.displayIndex);
    return li;
  }

  const obj = entry.object;
  const li = document.createElement("li");
  li.className = "layerRow";
  if (entry.groupId) li.classList.add("groupedLayer");
  if (activeSet.has(obj)) li.classList.add("active");
  if (obj.visible === false) li.classList.add("hiddenLayer");
  if (obj.kloudy?.locked) li.classList.add("lockedLayer");
  const color = hexToRgb(obj.fill || "#ffffff", (obj.opacity ?? 1) * 255);
  const groupBadge = entry.groupId
    ? KfpsI18n.t("<button class=\"layerGroupBadge\" type=\"button\" title=\"Select all layers in {0}.\">{1} ({2})</button>", escapeHtml(entry.groupName), escapeHtml(entry.groupName), entry.groupCount)
    : "";
  const data = fh6DataFromObject(obj);
  li.innerHTML = KfpsI18n.t("\n    <button class=\"layerIcon layerVisibility\" type=\"button\" title=\"{0}\">{1}</button>\n    <button class=\"layerIcon layerLock\" type=\"button\" title=\"{2}\">{3}</button>\n    <span class=\"layerColorChip\" style=\"--swatch:{4}\"></span>\n    <span class=\"layerMain\">\n      <b>{5}</b>\n      <small>{6} Type {7} | X {8} Y {9}</small>\n    </span>\n  ", obj.visible === false ? KfpsI18n.t("Show layer") : KfpsI18n.t("Hide layer"), obj.visible === false ? "H" : "V", obj.kloudy?.locked ? KfpsI18n.t("Unlock layer") : KfpsI18n.t("Lock layer"), obj.kloudy?.locked ? "L" : "U", colorToHex(color), escapeHtml(entry.label), groupBadge, escapeHtml(obj.kloudy?.type || KfpsI18n.t("unknown")), round(data[0]), round(data[1]));
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
    setObjectLocked(obj, !obj.kloudy?.locked);
    canvas.requestRenderAll();
    refreshLayers();
    updateSelectionPanel();
    pushHistory("layer lock");
  });
  li.addEventListener("click", (event) => {
    if (suppressLayerClick) return;
    if (event.shiftKey && lastLayerListKey && selectLayerRangeByKeys(lastLayerListKey, entry.key)) return;
    if ((event.ctrlKey || event.metaKey) && selectLayerToggleByKey(entry.key, KfpsI18n.t("layer multi-select"))) return;
    selectLayerEntryByKey(entry.key, KfpsI18n.t("layer row"));
  });
  registerLayerListRow(li, entry.key, entry.objects, entry.displayIndex);
  return li;
}

function renderVirtualLayerWindow(force = false) {
  const list = $("layers");
  const viewport = layerScrollPane();
  if (!list || !viewport) return;
  const range = KfpsEditorCore.virtualRange(
    layerVirtualLayout,
    viewport.scrollTop,
    viewport.clientHeight || 720,
    496,
  );
  if (!force && range.start === layerVirtualStart && range.end === layerVirtualEnd) return;
  layerVirtualStart = range.start;
  layerVirtualEnd = range.end;
  renderedLayerEntries.forEach((entry) => { entry.element = null; });
  renderedLayerEntries = layerListEntries.slice(range.start, range.end);
  const activeSet = new Set(selectedVinylObjects());
  const fragment = document.createDocumentFragment();
  renderedLayerEntries.forEach((entry) => fragment.appendChild(createVirtualLayerElement(entry, activeSet)));
  list.style.paddingTop = `${range.padTop}px`;
  list.style.paddingBottom = `${range.padBottom}px`;
  list.replaceChildren(fragment);
}

function updateLayerSelectionStyles() {
  const activeSet = new Set(selectedVinylObjects());
  renderedLayerEntries.forEach((entry) => {
    if (!entry.element?.isConnected) return;
    entry.element.classList.toggle("active", entry.objects.some((obj) => activeSet.has(obj)));
  });
  updateHud();
}

function* exportValidationSteps(objects) {
  const issues = [];
  const masks = objects.filter((object) => Boolean(object.kloudy?.mask));
  const hidden = objects.filter((object) => !objectEditorVisible(object));
  if (!objects.length) {
    issues.push({ severity: "error", message: KfpsI18n.t("Add or import at least one vinyl layer before exporting.") });
  }
  if (objects.length > MAX_VINYL_LAYERS) {
    issues.push({
      severity: "error",
      message: KfpsI18n.t("{0} layer(s) must be removed to meet the {1}-layer limit.", objects.length - MAX_VINYL_LAYERS, MAX_VINYL_LAYERS),
    });
  }

  let invalidTransforms = 0;
  let zeroScale = 0;
  let outside = 0;
  let unresolved = 0;
  let ineffectiveMasks = 0;
  let normalLayerBelow = false;
  const signatures = new Map();
  for (const object of objects) {
    yield;
    const hasNormalBelow = normalLayerBelow;
    if (!object.kloudy?.mask) normalLayerBelow = true;
    let shape;
    try {
      if (["left", "top", "scaleX", "scaleY", "angle", "skewX", "skewY"].some(key => !Number.isFinite(Number(object[key] ?? 0)))) {
        throw new Error("Invalid editor transform");
      }
      shape = objectToShape(object, { includeEditorMeta: false });
    } catch (_err) {
      invalidTransforms += 1;
      continue;
    }
    const values = Array.isArray(shape.data) ? shape.data.slice(0, 6).map(Number) : [];
    if (values.length < 6 || values.some((value) => !Number.isFinite(value))) {
      invalidTransforms += 1;
    } else if (Math.abs(values[2]) < 0.000001 || Math.abs(values[3]) < 0.000001
      || Math.abs(object.scaleX) < 0.000001 || Math.abs(object.scaleY) < 0.000001) {
      zeroScale += 1;
    }
    if (Number(shape.type) > 1000000 && !resolvedResourceForObject(object)) unresolved += 1;
    if (shape.mask && !hasNormalBelow) {
      ineffectiveMasks += 1;
    }
    try {
      const rect = object.getBoundingRect(true, true);
      const right = rect.left + rect.width;
      const bottom = rect.top + rect.height;
      if (
        right < FH6_BOUNDS.left
        || rect.left > FH6_BOUNDS.left + FH6_BOUNDS.width
        || bottom < FH6_BOUNDS.top
        || rect.top > FH6_BOUNDS.top + FH6_BOUNDS.height
      ) outside += 1;
    } catch (_err) {
      invalidTransforms += 1;
    }
    const signature = JSON.stringify({
      type: shape.type,
      data: shape.data,
      color: shape.color,
      mask: shape.mask,
    });
    signatures.set(signature, (signatures.get(signature) || 0) + 1);
  }

  const duplicateLayers = [...signatures.values()].reduce(
    (total, count) => total + Math.max(0, count - 1),
    0,
  );
  if (invalidTransforms) {
    issues.push({ severity: "error", message: KfpsI18n.t("{0} layer(s) have invalid transform data and cannot be exported safely.", invalidTransforms) });
  }
  if (zeroScale) {
    issues.push({ severity: "error", message: KfpsI18n.t("{0} layer(s) have a zero-width or zero-height scale.", zeroScale) });
  }
  if (hidden.length) {
    issues.push({ severity: "warning", message: KfpsI18n.t("{0} hidden editor layer(s) will still be included in the exported JSON.", hidden.length) });
  }
  if (outside) {
    issues.push({ severity: "warning", message: KfpsI18n.t("{0} layer(s) are completely outside the FH canvas and may be invisible in game.", outside) });
  }
  if (unresolved) {
    issues.push({ severity: "warning", message: KfpsI18n.t("{0} layer(s) use shape resources the editor could not verify.", unresolved) });
  }
  if (ineffectiveMasks) {
    issues.push({ severity: "warning", message: KfpsI18n.t("{0} mask layer(s) have no normal layer below them to cut.", ineffectiveMasks) });
  }
  if (duplicateLayers) {
    issues.push({ severity: "warning", message: KfpsI18n.t("{0} exact duplicate layer(s) were found. Keep them only if they are intentional.", duplicateLayers) });
  }
  if (objects.length && !issues.length) {
    issues.push({ severity: "info", message: KfpsI18n.t("No blocking export problems were found.") });
  }
  return {
    issues,
    errors: issues.filter((issue) => issue.severity === "error"),
    warnings: issues.filter((issue) => issue.severity === "warning"),
    masks: masks.length,
    hidden: hidden.length,
    count: objects.length,
  };
}

function exportValidation(objects = vinylObjects()) {
  const steps = exportValidationSteps(objects);
  let step;
  do { step = steps.next(); } while (!step.done);
  return step.value;
}

let exportValidationTimer = null;
let exportValidationEpoch = 0;
function scheduleExportValidation(objects = vinylObjects()) {
  const epoch = ++exportValidationEpoch;
  clearTimeout(exportValidationTimer);
  const steps = exportValidationSteps(objects);
  const slice = () => {
    if (epoch !== exportValidationEpoch) return;
    const deadline = performance.now() + 3;
    let step;
    do { step = steps.next(); } while (!step.done && performance.now() < deadline);
    if (step.done) {
      exportValidationTimer = null;
      renderExportValidationResult(step.value);
    } else exportValidationTimer = setTimeout(slice, 0);
  };
  exportValidationTimer = setTimeout(slice, 0);
}

function refreshExportValidation(objects = vinylObjects()) {
  exportValidationEpoch++;
  clearTimeout(exportValidationTimer);
  exportValidationTimer = null;
  const result = exportValidation(objects);
  renderExportValidationResult(result);
  return result;
}

function renderExportValidationResult(result) {
  const issueCount = result.errors.length + result.warnings.length;
  setText("exportMaskCount", String(result.masks));
  setText("exportHiddenCount", String(result.hidden));
  setText("exportWarningCount", String(issueCount));
  const readyLabel = !result.count
    ? KfpsI18n.t("No design")
    : (result.errors.length ? KfpsI18n.t("Blocked") : (result.warnings.length ? KfpsI18n.t("Review") : KfpsI18n.t("Ready")));
  setText("normalExportStatus", readyLabel);
  setText("exportReadyChip", readyLabel);
  setText("exportCheckBadge", readyLabel);
  const severityClass = result.errors.length ? "error" : (result.warnings.length ? "warning" : "ready");
  [document.querySelector(".statusChip"), $("exportCheckBadge")].forEach((element) => {
    if (!element) return;
    element.classList.remove("ready", "warning", "error");
    element.classList.add(severityClass);
  });
  const list = $("exportIssueList");
  if (list) {
    list.replaceChildren();
    result.issues.forEach((issue) => {
      const row = document.createElement("div");
      row.className = `exportIssue ${issue.severity}`;
      row.textContent = issue.message;
      list.appendChild(row);
    });
  }
  const exportButton = $("exportJson");
  if (exportButton) exportButton.disabled = exportSaveInProgress || Boolean(result.errors.length);
}

function refreshLayers() {
  layerRefreshNeedsStructure = false;
  if (layerRefreshFrame) {
    cancelAnimationFrame(layerRefreshFrame);
    layerRefreshFrame = null;
  }
  invalidateLayerStats();
  const list = $("layers");
  const viewport = layerScrollPane();
  const objects = vinylObjects();
  const activeSet = new Set(selectedVinylObjects());
  const filter = ($("layerSearch")?.value || "").trim().toLowerCase();
  let visibleCount = 0;
  const groupMembers = new Map();
  const groupNames = new Map();
  const groupVisibility = new Map();
  const groupLocks = new Map();
  objects.forEach((obj) => {
    if (obj.visible !== false && (obj.opacity ?? 1) > 0) visibleCount += 1;
    const rawGroupId = obj.kloudy?.group_id;
    if (!rawGroupId) return;
    const groupId = String(rawGroupId);
    const members = groupMembers.get(groupId) || [];
    members.push(obj);
    groupMembers.set(groupId, members);
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
  layerStatsCache = { objects, count: objects.length, visible: visibleCount };
  $("layerInfo").textContent = activeSet.size > 1
    ? KfpsI18n.t("{0} selected / {1} editable layer(s). Drag selection to move together.", activeSet.size, objects.length)
    : KfpsI18n.t("{0} editable layer(s). Export writes bottom-to-top order.", objects.length);

  const entries = [];
  const renderedGroups = new Set();
  const displayObjects = objects.slice().reverse();
  displayObjects.forEach((obj, displayIndex) => {
    const actualIndex = objects.length - displayIndex;
    const label = `${actualIndex}. ${obj.kloudy?.name || localizedTypeLabel(obj.kloudy?.type || 0)}`;
    const groupId = obj.kloudy?.group_id ? String(obj.kloudy.group_id) : null;
    const groupName = groupId ? (groupNames.get(groupId) || groupNameForObject(obj)) : "";
    const searchText = `${label} ${groupName} ${obj.kloudy?.type || ""} ${obj.kloudy?.type_word || ""}`.toLowerCase();
    if (filter && !searchText.includes(filter)) return;
    if (groupId && !renderedGroups.has(groupId)) {
      renderedGroups.add(groupId);
      const members = groupMembers.get(groupId) || [obj];
      entries.push({
        kind: "group",
        key: `group:${groupId}`,
        objects: members,
        displayIndex,
        groupId,
        groupName,
        collapsed: collapsedLayerGroups.has(groupId),
        visibility: groupVisibility.get(groupId) || { visible: 0, hidden: 0 },
        locks: groupLocks.get(groupId) || { locked: 0, unlocked: 0 },
        height: 62,
        element: null,
      });
    }
    if (groupId && collapsedLayerGroups.has(groupId)) return;
    entries.push({
      kind: "layer",
      key: layerListObjectKey(obj),
      object: obj,
      objects: [obj],
      displayIndex,
      groupId,
      groupName,
      groupCount: groupId ? (groupMembers.get(groupId)?.length || 1) : 0,
      label,
      height: 62,
      element: null,
    });
  });

  layerListEntries = entries;
  layerListRows = new Map(entries.map((entry) => [entry.key, entry]));
  layerVirtualLayout = KfpsEditorCore.buildVirtualLayout(entries, 62);
  layerVirtualStart = -1;
  layerVirtualEnd = -1;
  renderedLayerEntries = [];
  list.classList.add("layerVirtualized");
  list.setAttribute("aria-rowcount", String(entries.length));
  if (viewport && filter !== lastLayerFilter) viewport.scrollTop = 0;
  lastLayerFilter = filter;
  if (viewport && !viewport.dataset.virtualLayersBound) {
    viewport.dataset.virtualLayersBound = "true";
    viewport.addEventListener("scroll", scheduleVirtualLayerRender, { passive: true });
  }
  renderVirtualLayerWindow(true);
  scheduleExportValidation(objects);
  updateHud();
}

function updateSelectionPanel() {
  const selected = selectedVinylObjects();
  editorAssetLibrary?.selectionChanged();
  ["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput"].forEach(id => $(id).removeAttribute("aria-invalid"));
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
  ["copyLayer", "duplicateLayer", "deleteLayer", "bringFront", "bringForward", "sendBackward", "sendBack", "flipHorizontal", "flipVertical", "rotateLeft", "rotateRight"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = selected.length < 1;
  });
  document.querySelectorAll("[data-align]").forEach((button) => {
    button.disabled = selected.length < 1;
  });
  if ($("distributeHorizontal")) $("distributeHorizontal").disabled = selected.length < 3;
  if ($("distributeVertical")) $("distributeVertical").disabled = selected.length < 3;
  if ($("renameSelectedLayer")) $("renameSelectedLayer").disabled = selected.length !== 1;
  ["selectInverseLayers", "selectSameShape", "selectSameColor", "clearLayerSelection"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = id === "clearLayerSelection" ? selected.length < 1 : vinylObjects().length < 1;
  });
  if ($("selectAllLayers")) $("selectAllLayers").disabled = vinylObjects().length < 1;
  const quickGroup = $("quickGroupSelected");
  if (quickGroup) quickGroup.disabled = selected.length < 2;
  const sharedAlpha = sharedSelectedAlpha(selected);
  $("opacitySlider").disabled = selected.length < 1;
  $("equalizeAlpha").disabled = selected.length < 2;
  if (!enabled) {
    $("selectedShapeName").textContent = selected.length > 1 ? KfpsI18n.t("{0} layers selected", selected.length) : KfpsI18n.t("No layer selected");
    $("selectedShapeCode").textContent = selected.length > 1
      ? (sharedAlpha === null ? KfpsI18n.t("Mixed alpha. Color applies to all selected layers; alpha uses the slider value.") : KfpsI18n.t("Shared alpha {0}. Color and alpha apply to all selected layers.", sharedAlpha))
      : KfpsI18n.t("Click a layer or a shape tile.");
    if (selected.length > 1) $("opacitySlider").value = sharedAlpha ?? rememberedColor[3] ?? 255;
    if (selected.length > 1) {
      $("layerInfo").textContent = KfpsI18n.t("{0} layer(s) selected. Drag the selection box to move them together. Color edits apply to unlocked selected layers.", selected.length);
    }
    refreshColorUi();
    updateLayerSelectionStyles();
    return;
  }
  const obj = selected[0];
  $("selectedShapeName").textContent = obj.kloudy?.name || localizedTypeLabel(obj.kloudy?.type || 0);
  $("selectedShapeCode").textContent = KfpsI18n.t("Type {0}{1}", obj.kloudy?.type || KfpsI18n.t("unknown"), obj.kloudy?.mask ? KfpsI18n.t(" / mask") : "");
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

function applySelectionFields(options = {}) {
  const selected = selectedVinylObjects();
  if (selected.length > 1) {
    const editable = unlockedObjects(selected);
    if (!editable.length) {
      setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before editing."));
      updateSelectionPanel();
      return;
    }
    if (editable.length !== selected.length) {
      setStatus(KfpsI18n.t("Skipped {0} locked layer(s). Unlock them before batch editing.", selected.length - editable.length));
    }
    const alpha = Math.max(0, Math.min(255, Math.round(Number($("opacitySlider").value) || 0)));
    const color = hexToRgb($("colorPicker").value || colorToHex(rememberedColor), alpha);
    editable.forEach((obj) => applyObjectColor(obj, color));
    rememberColor(color);
    canvas.requestRenderAll();
    updateSelectionPanel();
    pushHistory("batch appearance edit");
    setStatus(KfpsI18n.t("Applied {0} / A {1} to {2} selected layer(s).{3}", colorToHex(color).toUpperCase(), alpha, editable.length, editable.length !== selected.length ? KfpsI18n.t(" Locked layers were skipped.") : ""));
    return;
  }
  const obj = selected[0];
  if (!obj || !obj.kloudy) return;
  if (obj.kloudy.locked) {
    setStatus(KfpsI18n.t("Selected layer is locked. Unlock it before editing."));
    updateSelectionPanel();
    return;
  }
  const values = {};
  for (const id of ["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput"]) {
    try {
      const value = KfpsEditorCore.parseNumericExpression($(id).value);
      if (["sxInput", "syInput"].includes(id) && Math.abs(value) < 0.000001) throw new Error(KfpsI18n.t("Scale cannot be zero."));
      if (id === "skewInput" && Math.abs(value) >= 89.9) throw new Error(KfpsI18n.t("Skew must be between -89.9 and 89.9 degrees."));
      values[id] = value;
      $(id).removeAttribute("aria-invalid");
    } catch (error) {
      $(id).setAttribute("aria-invalid", "true");
      setStatus(KfpsI18n.error(error.message));
      return false;
    }
  }
  const color = hexToRgb($("colorPicker").value, $("opacitySlider").value);
  rememberColor(color);
  const transformProps = fabricPropsFromFh6Data([
    values.xInput,
    values.yInput,
    values.sxInput,
    values.syInput,
    values.rotInput,
    fh6SkewFromFabricDegrees(
      values.skewInput,
      values.sxInput,
      values.syInput
    ),
  ]);
  obj.set({
    ...transformProps,
    scaleX: transformProps.scaleX * (obj.kloudy.render_scale || 1),
    scaleY: transformProps.scaleY * (obj.kloudy.render_scale || 1),
  });
  applyObjectColor(obj, color);
  obj.kloudy.scaleSigns = {
    x: values.sxInput < 0 ? -1 : 1,
    y: values.syInput < 0 ? -1 : 1,
  };
  applyMaskVisual(obj);
  obj.setCoords();
  applyLiveOverlayColor(obj);
  canvas.requestRenderAll();
  updateSelectionPanel();
  if (!options.preview) pushHistory("field edit", { changedObjects: [obj] });
  return true;
}

function applyMaskVisual(obj, options = {}) {
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
    });
    applyObjectHitTestMode(obj);
    obj.kloudy.maskOriginalColor = null;
  }
  if (!options.deferPreview) syncMaskPreviewOutlines();
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
  if (obj?._renderPathCommands === renderNativeTriangleFill && base.type === "path") {
    base._renderPathCommands = renderNativeTriangleFill;
  }
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
  const state = {
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
  };
  const changed = Object.keys(state).some(key => helper[key] !== state[key]);
  const viewport = canvas.viewportTransform;
  if (changed) helper.set(state);
  // Preserve coordinates when unchanged; in-place pan/zoom still invalidates them.
  if (changed || !helper.__kloudyMaskViewport
    || viewport.some((value, index) => helper.__kloudyMaskViewport[index] !== value)) {
    helper.setCoords();
    helper.__kloudyMaskViewport = viewport.slice();
  }
}

function syncMaskPreviewOutlines() {
  if (!canvas) return;
  const canvasObjectSet = new Set(canvas.getObjects());
  const wantedObjects = vinylObjects().filter((obj) => obj.kloudy?.mask);
  const wanted = new Set(wantedObjects);
  maskPreviewCutouts.forEach((cutout, obj) => {
    if (!wanted.has(obj) || !canvasObjectSet.has(obj)) {
      canvas.remove(cutout);
      maskPreviewCutouts.delete(obj);
    }
  });
  maskPreviewOutlines.forEach((outline, obj) => {
    if (!wanted.has(obj) || !canvasObjectSet.has(obj)) {
      canvas.remove(outline);
      maskPreviewOutlines.delete(obj);
    }
  });
  const orderedHelpers = [];
  wantedObjects.forEach((obj) => {
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
    orderedHelpers.push(cutout, outline);
  });
  if (!orderedHelpers.length) return;
  const helperSet = new Set(orderedHelpers);
  const currentObjects = canvas.getObjects();
  const nextObjects = currentObjects.filter((object) => !helperSet.has(object)).concat(orderedHelpers);
  if (!nextObjects.every((object, index) => currentObjects[index] === object)) {
    KfpsFabricAdapter.replaceObjectStack(canvas, nextObjects);
    nextObjects.forEach((object) => { object.canvas = canvas; });
    invalidateVinylObjectRegistry();
  }
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
    setStatus(KfpsI18n.t("Select one or more layers first."));
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before marking them as masks."));
    return;
  }
  const shouldMask = editable.some((obj) => !obj.kloudy?.mask);
  let changed = 0;
  editable.forEach((obj) => {
    if (!obj.kloudy) return;
    if (Boolean(obj.kloudy.mask) !== shouldMask) changed += 1;
    obj.kloudy.mask = shouldMask;
    applyMaskVisual(obj, { deferPreview: true });
  });
  syncMaskPreviewOutlines();
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory(shouldMask ? "make mask layer" : "clear mask layer");
  setStatus(
    changed
      ? KfpsI18n.t("{0} {1} layer(s) {2}.", shouldMask ? KfpsI18n.t("Marked") : KfpsI18n.t("Cleared"), changed, shouldMask ? KfpsI18n.t("as mask/cutout layers") : KfpsI18n.t("back to normal vinyl layers"))
      : KfpsI18n.t("Selected editable layers were already {0}.", shouldMask ? KfpsI18n.t("mask layers") : KfpsI18n.t("normal layers"))
  );
}

function equalizeSelectedAlpha() {
  const selected = selectedVinylObjects();
  if (selected.length < 2) {
    setStatus(KfpsI18n.t("Select two or more layers before equalizing alpha."));
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before equalizing alpha."));
    return;
  }
  const alpha = alphaForObject(editable[0]);
  editable.forEach((obj) => obj.set({ opacity: alpha / 255 }));
  $("opacitySlider").value = alpha;
  rememberColor([rememberedColor[0], rememberedColor[1], rememberedColor[2], alpha]);
  canvas.requestRenderAll();
  updateSelectionPanel();
  pushHistory("equalize alpha");
  setStatus(KfpsI18n.t("Equalized {0} selected layer(s) to alpha {1}.{2}", editable.length, alpha, editable.length !== selected.length ? KfpsI18n.t(" Locked layers were skipped.") : ""));
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
    headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" },
    signal: AbortSignal.timeout(30000),
    body: JSON.stringify({ name, payload }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(KfpsI18n.error(data.error || KfpsI18n.t("HTTP {0}", response.status)));
  return data;
}

async function saveProjectToAppFolder(name, payload, overwrite = false) {
  try {
    return await editorPersistence.request("saveProject", { name, payload, overwrite: Boolean(overwrite) });
  } catch (error) {
    error.message = error.code === "project_too_large"
      ? KfpsI18n.t("Project exceeds the {0} MiB save limit. Use a smaller reference image and save again.", EDITOR_PROJECT_MAX_BYTES / (1024 * 1024))
      : KfpsI18n.error(error.message);
    throw error;
  }
}

async function exportJson() {
  if (exportSaveInProgress) {
    setStatus(KfpsI18n.t("Export is already saving. Wait for it to finish."));
    return;
  }
  const shapes = vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: false }));
  if (!shapes.length) {
    setStatus(KfpsI18n.t("Nothing to export. Import a JSON or add at least one shape first."));
    return;
  }
  const validation = refreshExportValidation();
  if (validation.errors.length) {
    activateDockPanel("exportCheckPane");
    setStatus(KfpsI18n.t("Export blocked by {0} problem{1}. Open Export Check for details.", validation.errors.length, validation.errors.length === 1 ? "" : "s"));
    return;
  }
  const defaultName = cleanProjectBaseName(currentProjectName || loadedName, "vinyl");
  let exportName = currentProjectName;
  if (!exportName) {
    const requestedName = await requestTextInput(
      KfpsI18n.t("Export Vinyl JSON"),
      KfpsI18n.t("JSON name"),
      defaultName,
      KfpsI18n.t("This creates a game-ready JSON in KFPS imgs/editor. It does not replace the editable project."),
    );
    if (requestedName === null) {
      setStatus(KfpsI18n.t("JSON export cancelled."));
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
    setStatus(KfpsI18n.t("Exported {0} layer(s) to imgs/editor/{1}.", shapes.length, result.name || `${exportName}.fh6-import.json`));
    showCornerNotice(KfpsI18n.t("FH6 JSON saved inside KFPS"), KfpsI18n.t("Open Import JSON, choose Editor exports, and import it from there."));
  } catch (err) {
    downloadText(filenameWithSuffix(exportName, "fh6-import"), JSON.stringify(payload, null, 2));
    setStatus(KfpsI18n.t("Saved-to-folder failed ({0}). Downloaded {1} layer(s) instead.", KfpsI18n.error(err.message || err), shapes.length));
  } finally {
    exportSaveInProgress = false;
    refreshExportValidation();
  }
}

function editableProjectPayload(projectName) {
  const payload = {
    format: "kloudy_fabric_editor_project_v1",
    name: projectName,
    layer_count: vinylObjects().length,
    shapes: vinylObjects().map((object) => objectToShape(object, { includeEditorMeta: true })),
    editor_guides: savedGuideState(),
    editor_collapsed_groups: collapsedLayerGroupIds(),
  };
  const sourceOverlay = sourceOverlayProjectState();
  if (sourceOverlay) payload.editor_source_overlay = sourceOverlay;
  return payload;
}

async function saveProject(options = {}) {
  if (projectSaveInProgress) {
    setStatus(KfpsI18n.t("Project save is already running. Wait for it to finish."));
    return;
  }
  if (!hasEditableWorkspace()) {
    setStatus(KfpsI18n.t("Nothing to save. Add a shape, reference image, or guide first."));
    return;
  }
  const defaultName = cleanProjectBaseName(loadedName, "vinyl");
  let projectName = currentProjectName;
  if (!projectName || options.saveAs) {
    const requestedName = await requestTextInput(
      options.saveAs ? KfpsI18n.t("Save Project As") : KfpsI18n.t("Save Editable Project"),
      KfpsI18n.t("Project name"),
      options.saveAs ? cleanProjectBaseName(currentProjectName || defaultName, defaultName) : defaultName,
      KfpsI18n.t("Projects preserve editable layers, groups, guides, and the reference image. Export JSON separately when the vinyl is ready."),
    );
    if (requestedName === null) {
      setStatus(KfpsI18n.t("Project save cancelled."));
      return;
    }
    projectName = cleanProjectBaseName(requestedName, defaultName);
  }
  flushPendingNudgeHistory();
  // Reference-only projects may have no shape/history entry yet.
  ensureHistoryBaseline();
  const payload = editableProjectPayload(projectName);
  const savedRevision = { generation: documentGeneration, history: currentHistoryState(), overlay: overlayRevision };
  projectSaveInProgress = true;
  const saveButton = $("saveProject");
  const saveAsButton = $("saveProjectAs");
  if (saveButton) saveButton.disabled = true;
  if (saveAsButton) saveAsButton.disabled = true;
  try {
    const overwrite = Boolean(
      currentProjectName
      && !options.saveAs
      && cleanProjectBaseName(currentProjectName) === cleanProjectBaseName(projectName),
    );
    const result = await saveProjectToAppFolder(projectName, payload, overwrite);
    if (documentGeneration === savedRevision.generation) {
      flushPendingNudgeHistory();
      currentProjectName = cleanProjectBaseName(result.title || projectName, "project");
      loadedName = currentProjectName;
      savedHistoryState = savedRevision.history;
      savedOverlayRevision = savedRevision.overlay;
      updateDocumentState();
      renderHistoryList();
      writeAutosavePayload(autosavePayloadFromState(currentHistoryState() || snapshotEditorState()));
      setStatus(KfpsI18n.t("Saved project internally: {0}{1}", currentProjectName, documentDirty ? KfpsI18n.t(". Newer changes are still unsaved. Recovery pending.") : ""));
    }
    showCornerNotice(KfpsI18n.t("Project saved inside KFPS"), KfpsI18n.t("Saved {0}.", result.title || projectName));
  } catch (err) {
    const title = err?.code === "project_exists"
      ? KfpsI18n.t("That project name is already used")
      : KfpsI18n.t("Project save failed");
    setStatus(`${title}: ${err.message || err}`);
    showError(title, err);
  } finally {
    projectSaveInProgress = false;
    if (saveButton) saveButton.disabled = false;
    if (saveAsButton) saveAsButton.disabled = false;
  }
}

function saveProjectAs() {
  return saveProject({ saveAs: true });
}

async function loadProjectPayload(payload, displayName = "project", options = {}) {
  const generation = options.generation ?? beginDocumentLoad();
  if (generation !== documentGeneration) return false;
  setBusy(KfpsI18n.t("Loading project: {0}", displayName));
  await nextFrame();
  if (generation !== documentGeneration) return false;
  if (!Array.isArray(payload.shapes)) throw new Error(KfpsI18n.t("Project JSON must contain a shapes list."));
  const projectName = cleanProjectBaseName(payload.name || displayName, "project");
  recoveryRestoreDepth++;
  let restored = false;
  try {
    if (!await loadPayload({
      shapes: payload.shapes,
      editor_collapsed_groups: payload.editor_collapsed_groups || [],
    }, { generation, strict: true, name: projectName, projectName })) return false;
    const loadedHistory = currentHistoryState();
    applySavedGuideState(payload.editor_guides || null);
    let referenceError = null;
    try {
      await restoreSourceOverlayFromProject(payload.editor_source_overlay || null);
    } catch (err) {
      if (generation !== documentGeneration) return false;
      referenceError = err;
      clearSourceOverlayState();
      unavailableSourceOverlayState = payload.editor_source_overlay || null;
    }
    if (generation !== documentGeneration) return false;
    flushPendingNudgeHistory();
    if (currentHistoryState() !== loadedHistory) {
      restored = true;
      return true;
    }
    establishLoadedHistoryBoundary("open project", { writeRecovery: false });
    markCurrentHistorySaved(projectName);
    recoveryAutosavePayload = null;
    restored = true;
    if (referenceError) {
      savedOverlayRevision = overlayRevision - 1;
      updateDocumentState();
      setStatus(
        KfpsI18n.t("Loaded {0}, but its saved reference image could not be restored. ", projectName)
        + KfpsI18n.t("The project remains unsaved so the missing reference is not overwritten accidentally."),
      );
      showCornerNotice(
        KfpsI18n.t("Reference image unavailable"),
        KfpsI18n.error(referenceError.message || String(referenceError)),
      );
    }
    return true;
  } finally {
    if (generation === documentGeneration) recoveryRestoreDepth--;
    if (restored && generation === documentGeneration) writeAutosavePayload(autosavePayloadFromState(currentHistoryState() || snapshotEditorState()));
  }
}

async function loadProjectFile(file) {
  const generation = beginDocumentLoad();
  const payload = await editorPersistence.request("parseFile", { file });
  return loadProjectPayload(payload, file.name, { generation });
}

async function readEditorDocument(url) {
  try { return await editorPersistence.request("fetchJSON", { url }); }
  catch (error) {
    error.message = KfpsI18n.error(error.message);
    throw error;
  }
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
  label.textContent = select.options[select.selectedIndex]?.textContent || KfpsI18n.t("Add at top");
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
  const name = object.kloudy?.name || (resource ? localizedShapeDisplayName(resource.family, resource.index) : KfpsI18n.t("Shape word {0}", word));
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
    empty.textContent = KfpsI18n.t("No replaceable vinyl shapes are loaded.");
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
      button.innerHTML = KfpsI18n.t("\n        {0}\n        <span>\n          <b>{1}</b>\n          <span>{2} layer{3} / word {4}</span>\n        </span>\n      ", thumb ? `<img alt="" src="${thumb}">` : "<span></span>", escapeHtml(entry.name), entry.count, entry.count === 1 ? "" : "s", entry.word);
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
  setStatus(KfpsI18n.t("Global Change Shape armed for {0} ({1} layer{2}). Click a shape tile to replace every matching layer.", pendingGlobalShapeReplacement.name, pendingGlobalShapeReplacement.count, pendingGlobalShapeReplacement.count === 1 ? "" : "s"));
}

function armShapeReplacementFromLayers() {
  const selected = selectedVinylObjects();
  if (!selected.length) {
    pendingGlobalShapeReplacement = null;
    renderGlobalShapeReplacePanel();
    setStatus(KfpsI18n.t("No layers selected. Choose a used shape type, then click its replacement in Shape Library."));
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before changing shape type."));
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
  setStatus(KfpsI18n.t("Change Shape armed for {0} selected layer(s). Click a shape tile to replace them.{1}", editable.length, editable.length !== selected.length ? KfpsI18n.t(" {0} locked layer(s) will be skipped.", selected.length - editable.length) : ""));
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
    setStatus(KfpsI18n.t("Select a layer before using Insert above/below selected."));
    return false;
  }
  const referenceIndex = canvas.getObjects().indexOf(reference);
  canvas.add(object);
  KfpsFabricAdapter.moveObjectTo(canvas, object, mode === "below" ? referenceIndex : referenceIndex + 1);
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
    KfpsFabricAdapter.moveObjectTo(canvas, clone, mode === "below" ? referenceIndex + offset : referenceIndex + 1 + offset);
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

async function buildDetachedFabricObjects(items, build = shape => makeFabricObject(shape)) {
  const created = [];
  let failure = null;
  const results = await KfpsEditorCore.mapWithConcurrency(items, OBJECT_BUILD_CONCURRENCY, async (item, index) => {
    try {
      const object = await build(item, index);
      created.push(object);
      return object;
    } catch (error) {
      failure ||= error;
      return null;
    }
  }, { yield: nextFrame });
  // Wait for every in-flight builder before cleaning up a failed batch.
  if (failure) {
    created.forEach(discardFabricObject);
    throw failure;
  }
  return results;
}

async function replaceObjectsWithResource(objects, family, index) {
  flushPendingNudgeHistory();
  const generation = documentGeneration;
  const historyState = currentHistoryState();
  const sourceObjects = objects.slice();
  const sourceSet = new Set(sourceObjects);
  const originalOrder = vinylObjects().slice();
  const shapes = sourceObjects.map(object => updateShapeResourceOnShape(objectToShape(object, { includeEditorMeta: true }), family, index));
  const replacements = await buildDetachedFabricObjects(shapes);
  flushPendingNudgeHistory();
  if (generation !== documentGeneration || historyState !== currentHistoryState()) {
    replacements.forEach(discardFabricObject);
    return [];
  }
  try { replacements.forEach(replacement => canvas.add(replacement)); }
  catch (error) { replacements.forEach(discardFabricObject); throw error; }
  const replacementByObject = new Map(sourceObjects.map((object, i) => [object, replacements[i]]));
  sourceObjects.forEach(discardFabricObject);
  if (isFontFamily(family)) replacements.forEach(rememberFontShapeTransform);
  setVinylStackOrder(originalOrder.map((object) => (
    sourceSet.has(object) ? replacementByObject.get(object) : object
  )));
  return replacements;
}

async function replaceSelectedShapes(family, index) {
  const selected = orderedSelectedVinylObjects();
  if (!selected.length) {
    setStatus(KfpsI18n.t("Select one or more layers before replacing their shape type."));
    return;
  }
  const editable = unlockedObjects(selected);
  if (!editable.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before replacing shape type."));
    return;
  }
  const replacements = await replaceObjectsWithResource(editable, family, index);
  if (!replacements.length) return;
  selectObjects(replacements, KfpsI18n.t("shape replacement"));
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("replace shape type");
  setStatus(KfpsI18n.t("Replaced {0} layer(s) with {1}.{2}", replacements.length, localizedShapeDisplayName(family, index), editable.length !== selected.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", selected.length - editable.length) : ""));
}

async function replaceMatchingShapeWords(source, family, index) {
  const rawSourceWord = Number(source?.word);
  if (!Number.isFinite(rawSourceWord)) {
    pendingGlobalShapeReplacement = null;
    setStatus(KfpsI18n.t("Global Change Shape cancelled because the source shape was invalid."));
    return;
  }
  const sourceWord = rawSourceWord & 0xffff;
  const matches = vinylObjects().filter((object) => shapeWordForObject(object) === sourceWord);
  if (!matches.length) {
    pendingGlobalShapeReplacement = null;
    setStatus(KfpsI18n.t("No matching layers remain for that source shape."));
    return;
  }
  const editable = unlockedObjects(matches);
  if (!editable.length) {
    pendingGlobalShapeReplacement = null;
    setStatus(KfpsI18n.t("Matching layers are locked. Unlock them before replacing shape type."));
    return;
  }
  const replacements = await replaceObjectsWithResource(editable, family, index);
  if (!replacements.length) return;
  pendingGlobalShapeReplacement = null;
  selectObjects(replacements, KfpsI18n.t("global shape replacement"));
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("replace shape globally");
  setStatus(KfpsI18n.t("Replaced {0} {1} layer(s) with {2}.{3}", replacements.length, source.name || KfpsI18n.t("word {0}", sourceWord), localizedShapeDisplayName(family, index), editable.length !== matches.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", matches.length - editable.length) : ""));
}

async function addShape(family, index) {
  if (pendingGlobalShapeReplacement) {
    await replaceMatchingShapeWords(pendingGlobalShapeReplacement, family, index);
    return;
  }
  const mode = shapePlacementMode();
  if (mode === "replace") {
    const hadSelection = selectedVinylObjects().length > 0;
    await replaceSelectedShapes(family, index);
    if (hadSelection && $("shapePlacementMode")) {
      $("shapePlacementMode").value = "top";
      updateShapePlacementLabel();
      setStatus(KfpsI18n.t("Shape replaced. Placement returned to At top."));
    }
    return;
  }
  if (!requireLayerCapacity(1, KfpsI18n.t("add this shape"))) return;
  const generation = documentGeneration;
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
  if (generation !== documentGeneration || !requireLayerCapacity(1, KfpsI18n.t("add this shape"))) {
    discardFabricObject(object);
    return;
  }
  try {
    placeNewObjectInViewport(object);
    applyReusableFontTransform(object, family);
    if (!insertNewVinylObject(object, mode)) { discardFabricObject(object); return; }
  } catch (error) { discardFabricObject(object); throw error; }
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
      reject(new Error(KfpsI18n.t("Choose a pixel-art source image first.")));
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
      reject(new Error(KfpsI18n.t("Could not read image: {0}", file.name || KfpsI18n.t("source"))));
    };
    image.src = url;
  });
}

const { colorDistance, pixelArtColorAt, pixelArtVisible, pixelArtEdgeBetween, collectPixelArtEdges, dominantPixelArtStep, dominantPixelArtOffset, pixelArtIntervals, dominantPixelArtCell, pixelArtExactColorKey, buildPixelArtRuns } = KfpsPixelCore;

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
  const data = ctx.getImageData(0, 0, width, height).data;
  sampler.width = sampler.height = 1;
  return { width, height, data };
}

function sampleDetectedPixelArtGrid(image, alphaCutoff, tolerance) {
  return KfpsPixelCore.sampleDetectedPixelArtGrid(pixelArtImageData(image), alphaCutoff, tolerance);
}

function analyzePixelArtFile(file, options) {
  if (!file) return Promise.reject(new Error(KfpsI18n.t("Choose a pixel-art source image first.")));
  return new Promise((resolve, reject) => {
    const worker = new Worker("/tools/fabric-editor/editor-pixel-worker.js?v=1");
    let settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      worker.terminate();
      if (pixelArtAnalysisCancel === cancel) pixelArtAnalysisCancel = null;
      if (error) reject(error); else resolve(value);
    };
    const cancel = () => finish(Object.assign(new Error("Pixel-art analysis cancelled."), { code: "superseded" }));
    pixelArtAnalysisCancel = cancel;
    const timer = setTimeout(() => finish(new Error(KfpsI18n.t("Pixel-art analysis timed out. Try a smaller or simpler source image."))), 120000);
    worker.onerror = event => {
      event.preventDefault();
      finish(new Error(KfpsI18n.t("The pixel-art worker stopped. Your existing layers were kept.")));
    };
    worker.onmessageerror = () => finish(new Error(KfpsI18n.t("The pixel-art worker returned an unreadable response.")));
    worker.onmessage = async event => {
      if (settled) return;
      const message = event.data;
      if (message.rasterizeSvg) {
        try {
          const image = await loadImageFromFile(file);
          if (settled) return;
          const pixels = pixelArtImageData(image);
          worker.postMessage({ pixels, ...options }, [pixels.data.buffer]);
        } catch (error) { finish(error); }
      } else if (message.error) finish(new Error(KfpsI18n.error(message.error)));
      else finish(null, message.value);
    };
    try { worker.postMessage({ file, ...options }); }
    catch (error) { finish(error); }
  });
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
  previous.forEach(discardFabricObject);
  return previous.length;
}

async function generatePixelArtRectangles() {
  if (pixelArtGenerationRunning) return;
  flushPendingNudgeHistory();
  const generation = documentGeneration;
  const historyBefore = currentHistoryState();
  const created = [];
  let committed = false;
  pixelArtGenerationRunning = true;
  if ($("generatePixelArt")) $("generatePixelArt").disabled = true;
  try {
    if (!canvas) return;
    const alphaCutoff = numberInputValue("pixelArtAlphaCutoff", 128, 0, 255);
    const tolerance = numberInputValue("pixelArtTolerance", 24, 0, 80);
    const clearPrevious = Boolean($("pixelArtClearPrevious")?.checked);
    const previous = clearPrevious ? vinylObjects().filter(obj => obj.kloudy?.pixel_art_generated) : [];
    const maxRuns = MAX_VINYL_LAYERS - vinylObjects().length + previous.length;
    setBusy(KfpsI18n.t("Detecting source pixel grid..."));
    const detected = await analyzePixelArtFile(pixelArtSourceFile, { alphaCutoff, tolerance, maxRuns });
    if (generation !== documentGeneration) return;
    const gridW = detected.gridW;
    const gridH = detected.gridH;
    setPixelArtGridInputs(detected);
    if (detected.overflow) {
      const message = KfpsI18n.t("Pixel-art generation exceeds the available {0}-layer budget. Use a smaller or simpler source image.", maxRuns);
      setPixelArtStatus(message);
      clearBusy(message);
      return;
    }
    setBusy(KfpsI18n.t("Detected {0}x{1} source pixel grid. Building rectangles...", gridW, gridH));
    const runs = detected.runs;
    if (!runs.length) {
      setText("pixelArtStatus", KfpsI18n.t("No visible pixel-art cells found."));
      clearBusy(KfpsI18n.t("No visible pixel-art cells found."));
      return;
    }
    const previousCount = previous.length;
    const projectedCount = vinylObjects().length - previousCount + runs.length;
    if (projectedCount > MAX_VINYL_LAYERS) {
      const message = KfpsI18n.t("Pixel-art generation needs {0} total layers, above the {1}-layer maximum. Increase Cell px or reduce the source size.", projectedCount, MAX_VINYL_LAYERS);
      setText("pixelArtStatus", message);
      clearBusy(message);
      return;
    }
    const removed = previous.length;
    const layout = pixelArtCanvasLayout(gridW, gridH, "height");
    const groupId = `pixel-art-${Date.now().toString(36)}`;
    const groupName = `Pixel Art ${gridW}x${gridH}`;
    const typeCode = resourceToTypeCode("Primitives", 1);
    const shapeWord = resourceToShapeWord("Primitives", 1);
    const objects = await KfpsEditorCore.mapWithConcurrency(runs, OBJECT_BUILD_CONCURRENCY, async (run) => {
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
        created.push(object);
        return object;
      }, { yield: nextFrame });
    if (generation !== documentGeneration) return;
    if (currentHistoryState() !== historyBefore || nudgeHistoryPending) {
      clearBusy(KfpsI18n.t("The workspace changed during generation. Existing layers were kept. Generate again to apply it."));
      return;
    }
    objects.forEach(object => canvas.add(object));
    previous.forEach(discardFabricObject);
    committed = true;
    bringGuidesToBack();
    syncCanvasObjectCoords();
    selectObjects(objects.slice(0, 200), KfpsI18n.t("pixel-art generation"));
    refreshLayers();
    pushHistory("generate pixel art");
    const message = KfpsI18n.t("Generated {0} pixel-art rectangle layer(s) from detected {1}x{2} grid, source step {3}x{4}px.{5}", created.length, gridW, gridH, detected.stepX, detected.stepY, removed ? KfpsI18n.t(" Removed {0} previous pixel-art layer(s).", removed) : "");
    setText("pixelArtStatus", message);
    clearBusy(message);
  } catch (err) {
    if (err.code === "superseded" || generation !== documentGeneration) return;
    setText("pixelArtStatus", KfpsI18n.t("Pixel-art generation failed: {0}", KfpsI18n.error(err.message || err)));
    showError(KfpsI18n.t("Pixel-art generation failed"), err);
  } finally {
    if (!committed) created.forEach(discardFabricObject);
    pixelArtGenerationRunning = false;
    if ($("generatePixelArt")) $("generatePixelArt").disabled = false;
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
  const saved = editorSettings.getItem(TEXT_VINYL_FONT_KEY);
  const savedCustom = editorSettings.getItem(TEXT_VINYL_CUSTOM_FONT_KEY);
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
  editorSettings.setItem(TEXT_VINYL_FONT_KEY, select.value);
  editorSettings.setItem(TEXT_VINYL_CUSTOM_FONT_KEY, custom.value || "");
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
  if (!response.ok) throw new Error(KfpsI18n.t("Missing shape mesh resource: {0}", url));
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
  const digitIndex = "1234567890".indexOf(char);
  if (digitIndex >= 0) return { family: `Upper_Letters_${safeFont}`, index: digitIndex + 27 };
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
  previous.forEach(discardFabricObject);
  return previous.length;
}

async function generateTextVinylShapes() {
  if (textVinylGenerationRunning) return;
  flushPendingNudgeHistory();
  const generation = documentGeneration;
  const historyBefore = currentHistoryState();
  const created = [];
  let committed = false;
  textVinylGenerationRunning = true;
  if ($("generateTextVinyl")) $("generateTextVinyl").disabled = true;
  try {
    if (!canvas) return;
    const text = $("textVinylInput")?.value || "";
    if (!text.trim()) {
      setTextVinylStatus(KfpsI18n.t("Type some text first."));
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
    setBusy(KfpsI18n.t("Rasterizing text..."));
    await nextFrame();
    if (generation !== documentGeneration) return;
    const mask = options.mode === "forzaLetters" ? null : renderTextVinylMask(text, options);
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
      sourceLabel = KfpsI18n.t("Forza Font {0}, {1} glyph(s){2}", built.fontNumber, shapeSpecs.length, built.unsupported ? KfpsI18n.t(", {0} unsupported character(s) skipped", built.unsupported) : "");
    } else if (options.mode === "curveBands") {
      const bands = buildTextVinylCurveBands(mask, options.bandSize, options.alphaCutoff, options.coverage);
      sourceWidth = bands.gridW;
      sourceHeight = bands.gridH;
      const layout = textVinylLayout(sourceWidth, sourceHeight, options.targetHeight);
      shapeSpecs = buildTextVinylCurveShapes(bands.runs, layout, color, groupId, groupName);
      sourceLabel = KfpsI18n.t("{0} scanline run(s)", bands.runs.length);
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
      sourceLabel = KfpsI18n.t("{0} component shape(s) + {1} early shape(s) + {2} fitted stroke(s) + {3} curve corner(s) + {4} scored shape(s) + {5} residual shape(s){6}", fitted.componentShapeCount, fitted.earlyShapeCount, fitted.strokeCount, fitted.cornerCount, fitted.broadShapeCount, fitted.residualCount, types);
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
      sourceLabel = KfpsI18n.t("{0}x{1} cells", grid.gridW, grid.gridH);
    }
    if (!shapeSpecs.length) {
      setTextVinylStatus(KfpsI18n.t("No supported Forza letter shapes found for this text."));
      clearBusy(KfpsI18n.t("No supported Forza letter shapes found."));
      return;
    }
    const clearPrevious = Boolean($("textVinylClearPrevious")?.checked);
    const previous = clearPrevious ? vinylObjects().filter(obj => obj.kloudy?.source_format === TEXT_VINYL_SOURCE_FLAG) : [];
    const previousCount = previous.length;
    const projectedCount = vinylObjects().length - previousCount + shapeSpecs.length;
    if (projectedCount > MAX_VINYL_LAYERS) {
      const message = KfpsI18n.t("Text generation needs {0} total layers, above the {1}-layer maximum. Increase Cell/Band px or simplify the source.", projectedCount, MAX_VINYL_LAYERS);
      setTextVinylStatus(message);
      clearBusy(message);
      return;
    }
    setBusy(KfpsI18n.t("Building {0} text vinyl layer(s)...", shapeSpecs.length));
    const removed = previous.length;
    const objects = await KfpsEditorCore.mapWithConcurrency(shapeSpecs, OBJECT_BUILD_CONCURRENCY, async (shape) => {
        if (generation !== documentGeneration) throw Object.assign(new Error("Text generation cancelled."), { code: "superseded" });
        const object = await makeFabricObject(shape);
        object.kloudy.source_format = TEXT_VINYL_SOURCE_FLAG;
        created.push(object);
        return object;
      }, { yield: nextFrame });
    if (generation !== documentGeneration) return;
    if (currentHistoryState() !== historyBefore || nudgeHistoryPending) {
      clearBusy(KfpsI18n.t("The workspace changed during generation. Existing layers were kept. Generate again to apply it."));
      return;
    }
    objects.forEach(object => canvas.add(object));
    previous.forEach(discardFabricObject);
    committed = true;
    bringGuidesToBack();
    syncCanvasObjectCoords();
    selectObjects(objects.slice(0, 200), KfpsI18n.t("text vinyl generation"));
    refreshLayers();
    pushHistory("generate text vinyl");
    const message = KfpsI18n.t("Generated {0} text layer(s) from {1}, source {2}x{3}.{4}", created.length, sourceLabel, sourceWidth, sourceHeight, removed ? KfpsI18n.t(" Removed {0} previous text layer(s).", removed) : "");
    setTextVinylStatus(message);
    clearBusy(message);
  } catch (err) {
    if (err.code === "superseded" || generation !== documentGeneration) return;
    setTextVinylStatus(KfpsI18n.t("Text vinyl generation failed: {0}", KfpsI18n.error(err.message || err)));
    showError(KfpsI18n.t("Text vinyl generation failed"), err);
  } finally {
    if (!committed) created.forEach(discardFabricObject);
    textVinylGenerationRunning = false;
    if ($("generateTextVinyl")) $("generateTextVinyl").disabled = false;
  }
}

function buildShapeLibrary() {
  const select = $("shapeFamily");
  FAMILY_ORDER.forEach((family) => {
    const option = document.createElement("option");
    option.value = family;
    option.textContent = KfpsI18n.familyLabel(family);
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
    const name = localizedShapeDisplayName(family, index);
    if (query && !shapeSearchText(family, index, typeCode).includes(query)) continue;
    const tile = document.createElement("div");
    tile.className = `shapeTile${isFavorite ? " favorite" : ""}`;
    tile.tabIndex = 0;
    tile.title = KfpsI18n.t("{0}\n{1} #{2}\nType {3} / word {4}", name, KfpsI18n.familyLabel(family), index, typeCode, shapeWord);
    tile.innerHTML = KfpsI18n.t("\n      <button class=\"favButton\" type=\"button\" title=\"{0}\">{1}</button>\n      <img alt=\"\" src=\"{2}\">\n      <span class=\"shapeName\">{3}</span>\n      <span class=\"shapeMeta\">{4} #{5}</span>\n      <span class=\"shapeWord\">word {6}</span>\n    ", isFavorite ? KfpsI18n.t("Remove favorite") : KfpsI18n.t("Add favorite"), isFavorite ? "x" : "+", vinylResourceUrl(family, index, ".png"), escapeHtml(name), KfpsI18n.familyLabel(family), index, shapeWord);
    tile.addEventListener("click", () => addShape(family, index).catch((err) => showError(KfpsI18n.t("Shape add failed"), err)));
    tile.addEventListener("keydown", (event) => {
      if (event.target !== tile || event.isComposing) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        addShape(family, index).catch((err) => showError(KfpsI18n.t("Shape add failed"), err));
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
  editorSettings.setItem("kloudyFabricFavorites", JSON.stringify([...favorites]));
  renderShapeGrid();
}

async function duplicateSelectedNow() {
  const generation = documentGeneration;
  const selected = selectedVinylObjects();
  const selectedSet = new Set(selected);
  const orderedSelection = orderedSelectedVinylObjects();
  const objects = unlockedObjects(orderedSelection);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before duplicating."));
    return;
  }
  if (!requireLayerCapacity(objects.length, KfpsI18n.t("duplicate this selection"))) return;
  if (objects.length !== selected.length) {
    setStatus(KfpsI18n.t("Duplicating {0} unlocked layer(s). Skipped {1} locked layer(s).", objects.length, selected.length - objects.length));
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
  let clones = [];
  let inserted = false;
  try {
    const shapes = objects.map(obj => {
      const shape = objectToShape(obj, { includeEditorMeta: true });
      delete shape.editor_id;
      shape.data = Array.isArray(shape.data) ? shape.data.slice() : [];
      shape.data[0] = round((Number(shape.data[0]) || 0) + 30);
      shape.data[1] = round((Number(shape.data[1]) || 0) - 30);
      if (shape.editor_group_id) {
        const newGroupId = duplicateGroupMap.get(shape.editor_group_id);
        shape.editor_group_id = newGroupId;
        shape.editor_group_name = newGroupId ? duplicateGroupNameMap.get(obj.kloudy.group_id) : null;
      }
      shape.editor_locked = false;
      return shape;
    });
    clones = await buildDetachedFabricObjects(shapes);
    if (generation !== documentGeneration || objects.some(object => object.canvas !== canvas)
      || !requireLayerCapacity(clones.length, KfpsI18n.t("duplicate this selection"))) return;
    clones.forEach((clone, index) => {
      const obj = objects[index];
      if (obj.__kloudySelectionOutline) clone.set({ shadow: obj.__kloudySelectionOutline.shadow || null });
      delete clone.__kloudySelectionOutline;
      applyMaskVisual(clone);
      applyObjectHitTestMode(clone, $("boxVisibleOnly")?.checked || $("pixelSelect")?.checked || false);
      clone.hoverCursor = "pointer";
      clone.moveCursor = "move";
      styleObjectTransformControls(clone);
    });
    const mode = shapePlacementMode();
    const placement = insertDuplicateVinylObjects(clones, objects, mode);
    inserted = true;
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
    const placementText = placement === "top" ? KfpsI18n.t("at top") : KfpsI18n.t("{0} selected layer(s)", KfpsI18n.message(placement));
    setStatus(KfpsI18n.t("Duplicated {0} layer(s) {1}.{2}", clones.length, placementText, objects.length !== selectedSet.size ? KfpsI18n.t(" Skipped {0} locked layer(s).", selectedSet.size - objects.length) : ""));
  } catch (err) {
    if (generation !== documentGeneration) return;
    showError(KfpsI18n.t("Duplicate failed"), err);
    setStatus(KfpsI18n.t("Duplicate failed: {0}", KfpsI18n.error(err.message || err)));
  } finally {
    if (!inserted) clones.forEach(discardFabricObject);
  }
}

function duplicateSelected() {
  return queueEditorMutation(duplicateSelectedNow);
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
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before deleting."));
    return;
  }
  cancelEditorTransform();
  objects.forEach(discardFabricObject);
  syncMaskPreviewOutlines();
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory("delete");
  setStatus(KfpsI18n.t("Deleted {0} layer(s).{1}", objects.length, objects.length !== selected.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", selected.length - objects.length) : ""));
}

function moveSelected(direction) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before changing layer order."));
    return;
  }
  const moved = moveLayerBlock(objects, direction);
  if (!moved) {
    setStatus(KfpsI18n.t("Selected layer(s) are already at the {0} of the vinyl stack.", direction > 0 ? KfpsI18n.t("front") : KfpsI18n.t("back")));
    return;
  }
  refreshLayers();
  pushHistory("layer order");
  setStatus(KfpsI18n.t("Moved {0} unlocked layer(s) {1}.{2}", objects.length, direction > 0 ? KfpsI18n.t("forward") : KfpsI18n.t("backward"), objects.length !== selected.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", selected.length - objects.length) : ""));
}

function moveSelectedToEdge(front) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before changing layer order."));
    return;
  }
  const selectedSet = new Set(objects);
  const order = vinylObjects();
  const moving = order.filter((object) => selectedSet.has(object));
  const remaining = order.filter((object) => !selectedSet.has(object));
  setVinylStackOrder(front ? remaining.concat(moving) : moving.concat(remaining));
  refreshLayers();
  pushHistory(front ? "move to front" : "move to back");
  setStatus(KfpsI18n.t("Moved {0} layer(s) all the way to the {1}.", objects.length, front ? KfpsI18n.t("front") : KfpsI18n.t("back")));
}

function setVinylStackOrder(order) {
  if (!canvas) return;
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
  if (restoreSelection.length) canvas.discardActiveObject();
  // Discarding selection removes its outline. Take the stack afterwards so
  // a detached helper cannot be reintroduced as a permanent canvas object.
  const nonVinyl = canvas.getObjects().filter((obj) => !currentVinylSet.has(obj));
  KfpsFabricAdapter.replaceObjectStack(canvas, nonVinyl.concat(nextVinyl));
  invalidateVinylObjectRegistry();
  nextVinyl.forEach((obj) => {
    obj.canvas = canvas;
  });
  layerEditorHelpers();
  if (restoreSelection.length === 1) canvas.setActiveObject(restoreSelection[0]);
  else if (restoreSelection.length > 1) canvas.setActiveObject(styledActiveSelection(restoreSelection));
  canvas.requestRenderAll();
}

function moveLayerBlock(objects, direction) {
  const selectedSet = new Set(objects);
  const order = vinylObjects().slice();
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
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before flipping."));
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
  setStatus(KfpsI18n.t("Flipped {0} layer(s) {1}.{2}", objects.length, axis === "x" ? KfpsI18n.t("horizontally") : KfpsI18n.t("vertically"), objects.length !== selected.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", selected.length - objects.length) : ""));
}

function selectObjects(objects, reason) {
  const normalized = [...new Set(objects.map(interactiveVinylTarget).filter((obj) => obj?.kloudy && !obj.kloudyGuide))];
  if (!normalized.length) {
    setStatus(KfpsI18n.t("No layers found for {0}.", KfpsI18n.message(reason)));
    return;
  }
  releaseSelectionLock("");
  const active = canvas.getActiveObject();
  if (isActiveSelectionObject(active)) canvas.discardActiveObject();
  if (normalized.length === 1) canvas.setActiveObject(normalized[0]);
  else canvas.setActiveObject(styledActiveSelection(normalized));
  canvas.requestRenderAll();
  updateSelectionPanel();
  updateLayerSelectionStyles();
  setStatus(KfpsI18n.t("Selected {0} layer(s) by {1}.", normalized.length, KfpsI18n.message(reason)));
}

function selectAllLayers() {
  selectObjects(vinylObjects().filter((object) => object.visible !== false), KfpsI18n.t("Select All"));
}

function selectInverseLayers() {
  const selected = new Set(selectedVinylObjects());
  selectObjects(
    vinylObjects().filter((object) => object.visible !== false && !selected.has(object)),
    KfpsI18n.t("inverse selection"),
  );
}

function selectSameShapeLayers() {
  const source = selectedVinylObjects()[0];
  if (!source) {
    setStatus(KfpsI18n.t("Select a source layer before choosing Same Shape."));
    return;
  }
  const word = shapeWordForObject(source);
  selectObjects(
    vinylObjects().filter((object) => shapeWordForObject(object) === word),
    KfpsI18n.t("shape type"),
  );
}

function objectColorSignature(object) {
  try {
    return JSON.stringify(normalizeColor(objectToShape(object, { includeEditorMeta: false }).color));
  } catch (_err) {
    return "";
  }
}

function selectSameColorLayers() {
  const source = selectedVinylObjects()[0];
  if (!source) {
    setStatus(KfpsI18n.t("Select a source layer before choosing Same Color."));
    return;
  }
  const color = objectColorSignature(source);
  selectObjects(vinylObjects().filter((object) => objectColorSignature(object) === color), "color");
}

function clearLayerSelection() {
  releaseSelectionLock("");
  canvas.discardActiveObject();
  canvas.requestRenderAll();
  updateSelectionPanel();
  setStatus(KfpsI18n.t("Selection cleared."));
}

function selectedEditableForLayout(action, minimum = 1) {
  const selected = selectedVinylObjects();
  if (selected.length < minimum) {
    setStatus(KfpsI18n.t("Select {0} layers before {1}.", minimum === 1 ? KfpsI18n.t("one or more") : KfpsI18n.t("{0} or more", minimum), KfpsI18n.term(action)));
    return [];
  }
  const editable = unlockedObjects(selected);
  if (editable.length < minimum) {
    setStatus(KfpsI18n.t("Not enough selected layers are unlocked for {0}.", KfpsI18n.term(action)));
    return [];
  }
  if (isActiveSelectionObject(canvas.getActiveObject())) canvas.discardActiveObject();
  editable.forEach((object) => object.setCoords());
  return editable;
}

function objectAbsoluteBounds(object) {
  const rect = object.getBoundingRect(true, true);
  return {
    left: rect.left,
    top: rect.top,
    right: rect.left + rect.width,
    bottom: rect.top + rect.height,
    centerX: rect.left + rect.width / 2,
    centerY: rect.top + rect.height / 2,
  };
}

function layoutTargetBounds(objects) {
  const mode = $("alignTarget")?.value || "auto";
  if (mode === "canvas" || (mode === "auto" && objects.length === 1)) {
    return {
      left: FH6_BOUNDS.left,
      top: FH6_BOUNDS.top,
      right: FH6_BOUNDS.left + FH6_BOUNDS.width,
      bottom: FH6_BOUNDS.top + FH6_BOUNDS.height,
      centerX: FH6_BOUNDS.left + FH6_BOUNDS.width / 2,
      centerY: FH6_BOUNDS.top + FH6_BOUNDS.height / 2,
    };
  }
  const bounds = objects.map(objectAbsoluteBounds);
  const left = Math.min(...bounds.map((rect) => rect.left));
  const top = Math.min(...bounds.map((rect) => rect.top));
  const right = Math.max(...bounds.map((rect) => rect.right));
  const bottom = Math.max(...bounds.map((rect) => rect.bottom));
  return { left, top, right, bottom, centerX: (left + right) / 2, centerY: (top + bottom) / 2 };
}

function restoreLayoutSelection(objects) {
  objects.forEach((object) => object.setCoords());
  if (objects.length === 1) canvas.setActiveObject(objects[0]);
  else canvas.setActiveObject(styledActiveSelection(objects));
  syncCanvasObjectCoords(objects);
  requestCanvasRender();
  updateSelectionPanel();
  scheduleRefreshLayers();
}

function alignSelected(mode) {
  const objects = selectedEditableForLayout("aligning", 1);
  if (!objects.length) return;
  const target = layoutTargetBounds(objects);
  objects.forEach((object) => {
    const rect = objectAbsoluteBounds(object);
    const delta = KfpsEditorCore.alignmentDelta(rect, target, mode);
    object.set({ left: (object.left || 0) + delta.x, top: (object.top || 0) + delta.y });
  });
  restoreLayoutSelection(objects);
  pushHistory(`align ${mode}`);
  setStatus(KfpsI18n.t("Aligned {0} layer(s): {1}.", objects.length, humanizeHistoryReason(mode)));
}

function distributeSelected(axis) {
  const objects = selectedEditableForLayout("distributing", 3);
  if (objects.length < 3) return;
  const items = objects
    .map((object) => ({ object, bounds: objectAbsoluteBounds(object) }))
    .sort((left, right) => (
      axis === "x"
        ? left.bounds.centerX - right.bounds.centerX
        : left.bounds.centerY - right.bounds.centerY
    ));
  const deltas = KfpsEditorCore.distributionDeltas(
    items.map((item) => axis === "x" ? item.bounds.centerX : item.bounds.centerY),
  );
  items.slice(1, -1).forEach((item, index) => {
    const delta = deltas[index + 1];
    item.object.set(axis === "x"
      ? { left: (item.object.left || 0) + delta }
      : { top: (item.object.top || 0) + delta });
  });
  restoreLayoutSelection(objects);
  pushHistory(axis === "x" ? "distribute horizontal" : "distribute vertical");
  setStatus(KfpsI18n.t("Distributed {0} layers evenly {1}.", objects.length, axis === "x" ? KfpsI18n.t("horizontally") : KfpsI18n.t("vertically")));
}

function rotateSelectedQuarter(turns) {
  const objects = selectedEditableForLayout("rotating", 1);
  if (!objects.length) return;
  const bounds = layoutTargetBounds(objects);
  const radians = (Number(turns) || 0) * Math.PI / 2;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  objects.forEach((object) => {
    const center = object.getCenterPoint();
    const dx = center.x - bounds.centerX;
    const dy = center.y - bounds.centerY;
    const next = new fabric.Point(
      bounds.centerX + dx * cosine - dy * sine,
      bounds.centerY + dx * sine + dy * cosine,
    );
    object.rotate((Number(object.angle) || 0) + (Number(turns) || 0) * 90);
    object.setPositionByOrigin(next, "center", "center");
  });
  restoreLayoutSelection(objects);
  pushHistory(turns < 0 ? "rotate left" : "rotate right");
  setStatus(KfpsI18n.t("Rotated {0} layer(s) {1} by 90 degrees.", objects.length, turns < 0 ? KfpsI18n.t("left") : KfpsI18n.t("right")));
}

function loadEditorClipboard() {
  try {
    const payload = JSON.parse(localStorage.getItem(EDITOR_CLIPBOARD_KEY) || "null");
    if (payload && Array.isArray(payload.shapes)) editorClipboard = payload;
  } catch (_err) {
    editorClipboard = null;
  }
  if ($("pasteLayer")) $("pasteLayer").disabled = !editorClipboard?.shapes?.length;
}

function copySelectedLayers() {
  const objects = orderedSelectedVinylObjects();
  if (!objects.length) {
    setStatus(KfpsI18n.t("Select one or more layers before copying."));
    return;
  }
  editorClipboard = {
    format: "kfps_editor_clipboard_v1",
    copied_at: new Date().toISOString(),
    shapes: objects.map((object) => objectToShape(object, { includeEditorMeta: true })),
  };
  try {
    const serialized = JSON.stringify(editorClipboard);
    if (serialized.length <= 4_000_000) localStorage.setItem(EDITOR_CLIPBOARD_KEY, serialized);
  } catch (_err) {
    // The in-memory clipboard still works when browser storage is full.
  }
  if ($("pasteLayer")) $("pasteLayer").disabled = false;
  setStatus(KfpsI18n.t("Copied {0} layer(s).", objects.length));
}

async function pasteCopiedLayersNow() {
  const shapes = Array.isArray(editorClipboard?.shapes) ? editorClipboard.shapes : [];
  if (!shapes.length) {
    loadEditorClipboard();
    if (!editorClipboard?.shapes?.length) {
      setStatus(KfpsI18n.t("The editor layer clipboard is empty."));
      return;
    }
  }
  const sourceShapes = editorClipboard.shapes;
  return insertCopiedShapesNow(sourceShapes);
}

async function insertCopiedShapesNow(sourceShapes, { asset = false } = {}) {
  const generation = documentGeneration;
  if (!requireLayerCapacity(sourceShapes.length, KfpsI18n.t("insert these layers"))) return;
  const groupMap = new Map();
  const normalized = sourceShapes.map((source) => {
    const shape = JSON.parse(JSON.stringify(source));
    delete shape.editor_id;
    if (shape.editor_group_id) {
      if (!groupMap.has(shape.editor_group_id)) {
        groupMap.set(shape.editor_group_id, `group-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`);
      }
      shape.editor_group_id = groupMap.get(shape.editor_group_id);
    }
    shape.editor_locked = false;
    shape.data = Array.isArray(shape.data) ? shape.data.slice() : [0, 0, 1, 1, 0, 0, 0];
    shape.data[0] = round((Number(shape.data[0]) || 0) + (asset ? 0 : 30));
    shape.data[1] = round((Number(shape.data[1]) || 0) - (asset ? 0 : 30));
    return shape;
  });
  setBusy(KfpsI18n.t("Inserting {0} layer(s)...", normalized.length));
  let builtObjects = [];
  let inserted = false;
  try {
    const objects = await buildDetachedFabricObjects(normalized);
    builtObjects = objects;
    if (generation !== documentGeneration || !requireLayerCapacity(objects.length, KfpsI18n.t("insert these layers"))) return;
    if (asset && objects.length) {
      const bounds = objects.map(object => object.getBoundingRect(true, true));
      const left = Math.min(...bounds.map(rect => rect.left));
      const top = Math.min(...bounds.map(rect => rect.top));
      const right = Math.max(...bounds.map(rect => rect.left + rect.width));
      const bottom = Math.max(...bounds.map(rect => rect.top + rect.height));
      const center = fabric.util.transformPoint(new fabric.Point(canvas.width / 2, canvas.height / 2), fabric.util.invertTransform(canvas.viewportTransform));
      objects.forEach(object => { object.set({ left: object.left + center.x - (left + right) / 2, top: object.top + center.y - (top + bottom) / 2 }); object.setCoords(); });
    }
    const mode = ["above", "below"].includes(shapePlacementMode()) ? shapePlacementMode() : "top";
    insertDuplicateVinylObjects(objects, orderedSelectedVinylObjects(), mode);
    inserted = true;
    bringGuidesToBack();
    restoreLayoutSelection(objects);
    refreshLayers();
    pushHistory(asset ? "insert asset" : "paste");
    clearBusy(KfpsI18n.t("Inserted {0} layer(s).", objects.length));
  } catch (err) {
    if (generation === documentGeneration) showError(KfpsI18n.t("Insert failed"), err);
  } finally {
    if (!inserted) builtObjects.forEach(discardFabricObject);
  }
}

function pasteCopiedLayers() {
  return queueEditorMutation(pasteCopiedLayersNow);
}

function nextLayerGroupName() {
  const names = new Set(vinylObjects().map((obj) => obj.kloudy?.group_name).filter(Boolean));
  for (let i = 1; i < 10000; i++) {
    const name = KfpsI18n.t("Group {0}", i);
    if (!names.has(name)) return name;
  }
  return KfpsI18n.t("Group {0}", Date.now().toString(36));
}

function groupSelectedLayers() {
  const selected = selectedVinylObjects();
  if (selected.length < 2) {
    setStatus(KfpsI18n.t("Select two or more layers before creating a group."));
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
  setStatus(KfpsI18n.t("{0}: grouped {1} layer(s). Export remains flat.", groupName, selected.length));
}

async function renameSelectedLayer() {
  const selected = selectedVinylObjects();
  if (selected.length !== 1) {
    setStatus(KfpsI18n.t("Select exactly one layer before renaming it."));
    return;
  }
  const object = selected[0];
  const currentName = object.kloudy?.name || typeLabel(object.kloudy?.type || 0);
  const nextName = await requestTextInput(
    KfpsI18n.t("Rename Layer"),
    KfpsI18n.t("Layer name"),
    currentName,
    KfpsI18n.t("This name is for project organization and does not change the native shape used in game."),
  );
  if (nextName === null) return;
  const cleaned = String(nextName).trim().slice(0, 64) || currentName;
  object.kloudy.name = cleaned;
  refreshLayers();
  updateSelectionPanel();
  pushHistory("rename layer");
  setStatus(KfpsI18n.t("Renamed layer to {0}.", cleaned));
}

async function renameSelectedGroup() {
  const groupIds = selectedGroupIds();
  if (!groupIds.length) {
    setStatus(KfpsI18n.t("Select a grouped layer before renaming a group."));
    return;
  }
  if (groupIds.length > 1) {
    setStatus(KfpsI18n.t("Select one editor group before renaming."));
    return;
  }
  const members = membersForGroupIds(groupIds);
  if (!members.length) {
    setStatus(KfpsI18n.t("Selected group has no editable layers."));
    return;
  }
  const currentName = groupNameForObject(members[0]);
  const nextName = await requestTextInput(
    KfpsI18n.t("Rename Editor Group"),
    KfpsI18n.t("Group name"),
    currentName,
    KfpsI18n.t("Groups organize the project only. The exported game JSON remains a flat layer list."),
  );
  if (nextName === null) return;
  const cleaned = nextName.trim().slice(0, 64) || currentName;
  members.forEach((obj) => {
    obj.kloudy.group_name = cleaned;
  });
  refreshLayers();
  updateSelectionPanel();
  pushHistory("rename group");
  setStatus(KfpsI18n.t("Renamed editor group to {0}. Export remains flat.", cleaned));
}

function ungroupSelectedLayers() {
  const selected = selectedVinylObjects();
  const groupIds = selectedGroupIds();
  const targets = groupIds.length ? membersForGroupIds(groupIds) : selected.filter((obj) => obj.kloudy?.group_id);
  if (!targets.length) {
    setStatus(KfpsI18n.t("Select a grouped layer before ungrouping."));
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
  setStatus(KfpsI18n.t("Removed editor grouping from {0} layer(s).", targets.length));
}

function toggleSelectedGroupVisibility() {
  const targets = selectedGroupMembers();
  if (!targets.length) {
    setStatus(KfpsI18n.t("Select a grouped layer before hiding/showing a group."));
    return;
  }
  const shouldHide = targets.some((obj) => obj.visible !== false);
  targets.forEach((obj) => {
    obj.visible = !shouldHide;
  });
  canvas.requestRenderAll();
  refreshLayers();
  pushHistory(shouldHide ? "hide group" : "show group");
  setStatus(KfpsI18n.t("{0} {1} layer(s) in selected group.", shouldHide ? KfpsI18n.t("Hid") : KfpsI18n.t("Showed"), targets.length));
}

function toggleSelectedGroupLock() {
  const targets = selectedGroupMembers();
  if (!targets.length) {
    setStatus(KfpsI18n.t("Select a grouped layer before locking/unlocking a group."));
    return;
  }
  const shouldLock = targets.some((obj) => !obj.kloudy?.locked);
  targets.forEach((obj) => setObjectLocked(obj, shouldLock));
  canvas.requestRenderAll();
  refreshLayers();
  updateSelectionPanel();
  pushHistory(shouldLock ? "lock group" : "unlock group");
  setStatus(KfpsI18n.t("{0} {1} layer(s) in selected group.", shouldLock ? KfpsI18n.t("Locked") : KfpsI18n.t("Unlocked"), targets.length));
}

function nudgeSelected(dx, dy) {
  const selected = selectedVinylObjects();
  const objects = unlockedObjects(selected);
  if (!selected.length) return;
  if (!objects.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before nudging."));
    return;
  }
  beginHybridRender("nudge");
  const active = canvas.getActiveObject();
  if (isActiveSelectionObject(active) && objects.length === selected.length) {
    active.set({ left: (active.left || 0) + dx, top: (active.top || 0) + dy });
    active.setCoords();
    active.dirty = true;
  } else {
    objects.forEach((obj) => {
      obj.set({ left: (obj.left || 0) + dx, top: (obj.top || 0) + dy });
      obj.setCoords();
    });
  }
  applyLiveOverlayColor();
  if (hybridRenderActive) {
    requestHybridRender();
    settleHybridRender();
  } else canvas.requestRenderAll();
  updateSelectionPanel();
  objects.forEach(object => pendingNudgeObjects.add(object));
  scheduleNudgeHistory();
  if (objects.length !== selected.length) setStatus(KfpsI18n.t("Nudged {0} unlocked layer(s). Skipped {1} locked layer(s).", objects.length, selected.length - objects.length));
}

function setPixelSelection(enabled) {
  if ($("pixelSelect")) $("pixelSelect").checked = enabled;
  if ($("boxVisibleOnly")) $("boxVisibleOnly").checked = enabled;
  canvas.perPixelTargetFind = false;
  canvas.targetFindTolerance = enabled ? VINYL_HIT_TOLERANCE : 0;
  vinylObjects().forEach((obj) => {
    applyObjectHitTestMode(obj, enabled);
  });
}

function rebuildOverlaySampler(img) {
  const width = img.naturalWidth || img.width || 1;
  const height = img.naturalHeight || img.height || 1;
  releaseOverlaySampler();
  overlaySampler = { width, height, source: img, tiles: new Map(), canvas: null };
}

function releaseOverlaySampler() {
  if (overlaySampler?.canvas) overlaySampler.canvas.width = overlaySampler.canvas.height = 1;
  overlaySampler?.tiles.clear();
  overlaySampler = null;
}

function readOverlayPixel(x, y) {
  const sampler = overlaySampler;
  if (!sampler || x < 0 || y < 0 || x >= sampler.width || y >= sampler.height) return null;
  const tileSize = 256;
  const left = Math.floor(x / tileSize) * tileSize;
  const top = Math.floor(y / tileSize) * tileSize;
  const key = `${left}:${top}`;
  let tile = sampler.tiles.get(key);
  if (tile) sampler.tiles.delete(key);
  else {
    // Exact source pixels, allocated only when sampled. Keep at most 8 MiB of
    // decoded tiles instead of a second full-resolution RGBA reference image.
    const surface = sampler.canvas || (sampler.canvas = document.createElement("canvas"));
    const width = Math.min(tileSize, sampler.width - left);
    const height = Math.min(tileSize, sampler.height - top);
    surface.width = width; surface.height = height;
    const context = surface.getContext("2d", { willReadFrequently: true });
    context.drawImage(sampler.source, left, top, width, height, 0, 0, width, height);
    tile = { width, data: context.getImageData(0, 0, width, height).data };
  }
  sampler.tiles.set(key, tile);
  if (sampler.tiles.size > 32) sampler.tiles.delete(sampler.tiles.keys().next().value);
  const offset = ((y - top) * tile.width + x - left) * 4;
  return tile.data.subarray(offset, offset + 4);
}

function sourceOverlayProjectState() {
  if (!overlayImage || !overlaySourceState) return unavailableSourceOverlayState;
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
  overlayLoadGeneration++;
  overlayRefreshGeneration++;
  unavailableSourceOverlayState = null;
  releaseHybridOverlay();
  if (overlayImage) discardFabricObject(overlayImage);
  overlayImage = null;
  releaseOverlaySampler();
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
    const layeredState = parseLayeredSvg(String(state.svg_text), fileName);
    const layered = state.layered_svg || {};
    layeredState.selectedIndex = Math.max(0, Math.min(
      Number(layered.selected_index) || 0,
      Math.max(0, layeredState.layers.length - 1)
    ));
    layeredState.viewMode = String(layered.view_mode || "original");
    const url = layeredSvgDataUrl(layeredState);
    if (!url) throw new Error(KfpsI18n.t("The saved layered SVG reference could not be rendered."));
    await loadOverlayImageFromUrl(url, fileName, { mimeType: state.mime_type || "image/svg+xml", projectState: state, layeredState });
    return;
  }
  if (!state.data_url) {
    clearSourceOverlayState();
    return;
  }
  await loadOverlayImageFromUrl(String(state.data_url), fileName, { mimeType: state.mime_type || null, projectState: state, layeredState: null });
}

function applyOverlayProjectTransform(state, image = overlayImage) {
  if (!image || !state?.transform) return;
  const transform = state.transform;
  image.set({
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
  image.setCoords();
}

function clearLayeredOverlayState() {
  layeredOverlayState = null;
  setHidden("layeredOverlayControls", true);
  const select = $("overlaySvgLayerSelect");
  if (select) select.innerHTML = "";
  setText("overlaySvgLayerInfo", KfpsI18n.t("Load a layered SVG to flip through its reference, guide, and color layers."));
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
  if (doc.querySelector("parsererror")) throw new Error(KfpsI18n.t("SVG parser rejected the file."));
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

function selectedLayeredOverlayLayer(state = layeredOverlayState) {
  if (!state?.layers?.length) return null;
  return state.layers[Math.max(0, Math.min(state.selectedIndex, state.layers.length - 1))];
}

function shouldShowSvgLayer(layer, mode, selectedLayer) {
  if (mode === "original") return !layer.hidden;
  if (mode === "color_layers") return layer.kind === "color";
  if (mode === "selected") return layer.id === selectedLayer?.id;
  if (mode === "selected_reference") return layer.id === selectedLayer?.id || layer.kind === "reference";
  if (mode === "selected_edge") return layer.id === selectedLayer?.id || layer.kind === "edge";
  return !layer.hidden;
}

function layeredSvgDataUrl(state = layeredOverlayState) {
  if (!state) return null;
  const parser = new DOMParser();
  const doc = parser.parseFromString(state.sourceText, "image/svg+xml");
  if (doc.querySelector("parsererror")) return null;
  const selectedLayer = selectedLayeredOverlayLayer(state);
  doc.querySelectorAll("g").forEach((group) => {
    const id = group.id || "";
    const layer = state.layers.find((item) => item.id === id || item.label === svgLayerLabel(group));
    if (!layer) return;
    setSvgElementVisible(group, shouldShowSvgLayer(layer, state.viewMode, selectedLayer));
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
    KfpsI18n.t("{0}: {1} layer(s), {2} color layer(s). Showing {3}.", layeredOverlayState.fileName, layeredOverlayState.layers.length, colorCount, layer?.label || KfpsI18n.t("original visibility"))
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
  const target = overlayImage;
  const state = layeredOverlayState;
  const generation = ++overlayRefreshGeneration;
  const isCurrent = () => target === overlayImage && state === layeredOverlayState && generation === overlayRefreshGeneration;
  const url = layeredSvgDataUrl();
  if (!url) {
    setStatus(KfpsI18n.t("Layered SVG reference refresh failed."));
    return;
  }
  const img = new Image();
  img.onload = () => {
    if (!isCurrent()) return;
    rebuildOverlaySampler(img);
    releaseHybridOverlay();
    target.setElement(img);
    target.set({
      width: img.width || state.width,
      height: img.height || state.height,
    });
    updateOverlay();
    updateLayeredOverlayInfo();
    canvas.requestRenderAll();
  };
  img.onerror = () => { if (isCurrent()) setStatus(KfpsI18n.t("Layered SVG reference refresh failed.")); };
  img.src = url;
}

function canvasPointToOverlayPixel(x, y, inverse = null) {
  if (!overlayImage || !overlaySampler) return null;
  inverse ||= fabric.util.invertTransform(overlayImage.calcTransformMatrix());
  const local = fabric.util.transformPoint(new fabric.Point(x, y), inverse);
  const px = Math.round(local.x + (overlayImage.width || overlaySampler.width) / 2);
  const py = Math.round(local.y + (overlayImage.height || overlaySampler.height) / 2);
  if (px < 0 || py < 0 || px >= overlaySampler.width || py >= overlaySampler.height) return null;
  return { x: px, y: py };
}

function overlayColorAtCanvasPoint(x, y) {
  const pixel = canvasPointToOverlayPixel(x, y);
  if (!pixel || !overlaySampler) return null;
  const data = readOverlayPixel(pixel.x, pixel.y);
  const alpha = data[3];
  if (alpha < 24) return null;
  return [
    data[0],
    data[1],
    data[2],
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
  const inverse = fabric.util.invertTransform(overlayImage.calcTransformMatrix());
  for (let iy = 0; iy < stepsY; iy++) {
    const y = rect.top + rect.height * ((iy + 0.5) / stepsY);
    for (let ix = 0; ix < stepsX; ix++) {
      const x = rect.left + rect.width * ((ix + 0.5) / stepsX);
      const pixel = canvasPointToOverlayPixel(x, y, inverse);
      if (!pixel) continue;
      const [r, g, b, a] = readOverlayPixel(pixel.x, pixel.y);
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
    if (!options.silent) setStatus(KfpsI18n.t("Selected layer is locked. Unlock it before sampling the reference color."));
    return false;
  }
  const color = dominantOverlayColorForObject(obj);
  if (!color) {
    if (!options.silent) setStatus(KfpsI18n.t("No reference color was found under the selected layer."));
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
  if (!options.silent) setStatus(KfpsI18n.t("Sampled {0} reference color {1}.", KfpsI18n.term($("overlaySampleMode")?.value || "dominant"), colorToHex(applied)));
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
    setStatus(KfpsI18n.t("Select one or more layers before sampling a reference color."));
    return;
  }
  const editable = unlockedObjects(objects);
  if (!editable.length) {
    setStatus(KfpsI18n.t("Selected layers are locked. Unlock them before sampling a reference color."));
    return;
  }
  let changed = 0;
  editable.forEach((obj) => {
    if (applyOverlayColorToObject(obj, { remember: true, silent: true })) changed++;
  });
  canvas.requestRenderAll();
  updateSelectionPanel();
  if (changed) {
    pushHistory("reference color sample");
    setStatus(KfpsI18n.t("Sampled reference color for {0} selected layer(s).{1}", changed, editable.length !== objects.length ? KfpsI18n.t(" Skipped {0} locked layer(s).", objects.length - editable.length) : ""));
  } else {
    setStatus(KfpsI18n.t("No reference-image pixels were found under the selected layer(s)."));
  }
}

async function loadOverlayImageFromUrl(url, fileName, options = {}) {
  const generation = options.generation ?? ++overlayLoadGeneration;
  const documentToken = options.documentGeneration ?? documentGeneration;
  const layeredState = options.layeredState === undefined ? layeredOverlayState : options.layeredState;
  const isCurrent = () => generation === overlayLoadGeneration && documentToken === documentGeneration;
  if (!isCurrent()) return null;
  let objectUrl = null;
  if (String(url).startsWith("data:image/")) {
    try {
      const blob = await editorPersistence.request("referenceImage", {
        payload: { editor_source_overlay: { data_url: layeredState ? null : url, svg_text: layeredState?.sourceText || null } },
        imageUrl: layeredState ? url : null,
        maxReferenceBytes: EDITOR_REFERENCE_MAX_BYTES,
      });
      if (!isCurrent()) return null;
      objectUrl = URL.createObjectURL(blob);
    } catch (error) {
      if (!isCurrent()) return null;
      if (error.code === "reference_too_large") error.message = KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024));
      setStatus(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(error.message)));
      throw error;
    }
  }
  return new Promise((resolve, reject) => {
    const img = new Image();
    const fail = (error) => {
      clearTimeout(timer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      img.onload = img.onerror = null;
      img.src = "";
      if (isCurrent()) {
        setStatus(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(error.message)));
        reject(error);
      } else resolve(null);
    };
    const timer = setTimeout(() => fail(new Error(KfpsI18n.t("{0} is not a usable image.", fileName))), 30000);
    img.onload = () => {
      clearTimeout(timer);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      img.onload = img.onerror = null;
      if (!isCurrent()) { resolve(null); return; }
      let replacement = null;
      try {
        if (!objectUrl && new Blob([String(layeredState?.sourceText || url)]).size > EDITOR_REFERENCE_MAX_BYTES) {
          throw new Error(KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024)));
        }
        replacement = new fabric.Image(img, {
          originX: "center",
          originY: "center",
          left: 0,
          top: 0,
          opacity: Number($("overlayOpacity").value) / 100,
          selectable: false,
          evented: false,
          excludeFromExport: true,
        });
        replacement.kloudyOverlay = true;
        if (options.projectState) {
          applyOverlayProjectTransform(options.projectState, replacement);
        } else {
          const fit = 1800 / Math.max(img.width, img.height);
          const factor = syncOverlayScaleControls($("overlayScalePercent")?.value || $("overlayScale")?.value || 100) / 100;
          replacement.set({ scaleX: fit * factor, scaleY: fit * factor });
        }
        canvas.add(replacement);
        releaseHybridOverlay();
        if (overlayImage) discardFabricObject(overlayImage);
        overlayImage = replacement;
        rebuildOverlaySampler(img);
        clearLayeredOverlayState();
        layeredOverlayState = layeredState;
        overlayRefreshGeneration++;
        overlaySourceState = {
          kind: layeredState ? "layered_svg" : "image",
          fileName,
          mimeType: options.mimeType || null,
          dataUrl: layeredState ? null : url,
          svgText: layeredState?.sourceText || null,
        };
        unavailableSourceOverlayState = null;
        if (options.projectState?.controls) {
          syncOverlayScaleControls(options.projectState.controls.scale_percent || 100);
          if ($("overlayOpacity")) $("overlayOpacity").value = Math.round((overlayImage.opacity ?? 1) * 100);
        }
        // Prepare the reference texture during explicit image loading, so its
        // first upload is not deferred to the user's next drag or keypress.
        hybridRenderNow();
        if (layeredOverlayState) populateLayeredOverlayControls();
        if (activeToolMode === "source") updateSourceInteractivity();
        else layerEditorHelpers();
        canvas.requestRenderAll();
        setStatus(layeredOverlayState ? KfpsI18n.t("Layered SVG reference loaded: {0}", fileName) : KfpsI18n.t("Reference image loaded: {0}", fileName));
        updateHud();
        markOverlayChanged("reference image loaded");
        resolve(overlayImage);
      } catch (error) {
        if (replacement && replacement !== overlayImage) discardFabricObject(replacement);
        fail(error);
      }
    };
    img.onerror = () => {
      fail(new Error(KfpsI18n.t("{0} is not a usable image.", fileName)));
    };
    img.src = objectUrl || url;
  });
}

function addOverlayFile(file) {
  if (file.size > EDITOR_REFERENCE_MAX_BYTES) {
    setStatus(KfpsI18n.t("Reference exceeds the {0} MiB storage budget. Use a smaller image.", EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024)));
    return;
  }
  const isSvg = file.type === "image/svg+xml" || /\.svg$/i.test(file.name || "");
  const generation = ++overlayLoadGeneration;
  const documentToken = documentGeneration;
  const isCurrent = () => generation === overlayLoadGeneration && documentToken === documentGeneration;
  const reader = new FileReader();
  reader.onerror = () => { if (isCurrent()) setStatus(KfpsI18n.t("Reference load failed: could not read {0}.", file.name)); };
  if (isSvg) {
    reader.onload = () => {
      if (!isCurrent()) return;
      let layeredState;
      try {
        layeredState = parseLayeredSvg(String(reader.result || ""), file.name);
      } catch (err) {
        setStatus(KfpsI18n.t("Reference load failed: {0}", KfpsI18n.error(err.message || KfpsI18n.t("SVG could not be parsed."))));
        return;
      }
      const url = layeredSvgDataUrl(layeredState);
      if (!url) {
        setStatus(KfpsI18n.t("Reference load failed: {0} could not be rendered.", file.name));
        return;
      }
      loadOverlayImageFromUrl(url, file.name, { mimeType: file.type || "image/svg+xml", layeredState, generation, documentGeneration: documentToken }).catch(() => {});
    };
    reader.readAsText(file);
    return;
  }
  reader.onload = () => {
    if (isCurrent()) loadOverlayImageFromUrl(reader.result, file.name, { mimeType: file.type || null, layeredState: null, generation, documentGeneration: documentToken }).catch(() => {});
  };
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
  markOverlayChanged("reference image adjusted");
}

function toggleOverlay() {
  if (!overlayImage) {
    setStatus(KfpsI18n.t("No reference image is loaded. Add one first."));
    return;
  }
  overlayImage.visible = !overlayImage.visible;
  canvas.requestRenderAll();
  markOverlayChanged(overlayImage.visible ? "reference image shown" : "reference image hidden");
}

function removeOverlay() {
  overlayLoadGeneration++;
  overlayRefreshGeneration++;
  if (!overlayImage && !unavailableSourceOverlayState) {
    setStatus(KfpsI18n.t("No reference image is loaded to remove."));
    return;
  }
  clearSourceOverlayState();
  canvas.requestRenderAll();
  updateHud();
  markOverlayChanged("reference image removed");
}

function bindTransformInputs() {
  const ids = ["xInput", "yInput", "sxInput", "syInput", "rotInput", "skewInput"];
  let drag = null;
  function finishDrag(cancel) {
    if (!drag) return;
    const current = drag;
    drag = null;
    if (cancel) applyHistoryShapeToObject(current.object, current.shape);
    else pushHistory("numeric drag", { changedObjects: [current.object] });
    syncMaskPreviewOutlines();
    updateSelectionPanel();
    canvas.requestRenderAll();
    if (current.label.hasPointerCapture(current.pointerId)) current.label.releasePointerCapture(current.pointerId);
  }
  ids.forEach(id => {
    const input = $(id);
    let owner = null, original = "";
    input.addEventListener("focus", () => { owner = selectedVinylObjects()[0]; original = input.value; });
    const commit = () => {
      if (owner && selectedVinylObjects()[0] === owner && input.value !== original) {
        if (applySelectionFields()) original = input.value;
      }
    };
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", event => {
      if (event.isComposing) return;
      if (event.key === "Enter") { event.preventDefault(); if (!event.repeat) commit(); }
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); updateSelectionPanel(); original = input.value; }
      if (["ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault();
        try {
          input.value = round(KfpsEditorCore.parseNumericExpression(input.value) + (event.key === "ArrowUp" ? 1 : -1) * Number(input.dataset.step) * (event.shiftKey ? 10 : event.altKey ? 0.1 : 1));
          commit();
        } catch (error) { input.setAttribute("aria-invalid", "true"); setStatus(KfpsI18n.error(error.message)); }
      }
    });
  });
  document.querySelectorAll("[data-numeric-for]").forEach(label => {
    label.addEventListener("pointerdown", event => {
      const input = $(label.dataset.numericFor), object = selectedVinylObjects()[0];
      if (event.button !== 0 || input.disabled || object?.kloudy?.locked || !object) return;
      event.preventDefault();
      document.activeElement?.blur();
      flushPendingNudgeHistory();
      updateSelectionPanel();
      drag = { label, pointerId: event.pointerId, input, object, shape: objectToShape(object, { includeEditorMeta: true }), x: event.clientX, value: Number(input.value) };
      label.setPointerCapture(event.pointerId);
    });
    label.addEventListener("pointermove", event => {
      if (!drag || drag.label !== label) return;
      if (selectedVinylObjects()[0] !== drag.object) { finishDrag(true); return; }
      drag.input.value = round(drag.value + (event.clientX - drag.x) * Number(drag.input.dataset.step) * (event.shiftKey ? 10 : event.altKey ? 0.1 : 1));
      applySelectionFields({ preview: true });
    });
    label.addEventListener("pointerup", () => finishDrag(false));
    label.addEventListener("pointercancel", () => finishDrag(true));
    label.addEventListener("lostpointercapture", () => finishDrag(true));
  });
  window.addEventListener("blur", () => finishDrag(true));
  window.addEventListener("keydown", event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (!drag) return;
    if (event.key === "Escape") finishDrag(true);
    event.preventDefault(); event.stopImmediatePropagation();
  }, true);
}

function overlappingVinylObjects(point) {
  return vinylObjects().slice().reverse().filter(object => object.visible && !object.kloudy?.locked
    && (object.opacity > 0 || object.kloudy?.mask) && KfpsFabricAdapter.visiblePixelAt(canvas, object, point));
}

function bindOverlapSelection() {
  const setting = $("overlapCycle");
  setting.checked = editorSettings.getItem("kloudyFabricOverlapCycle") === "1";
  setting.addEventListener("change", () => editorSettings.setItem("kloudyFabricOverlapCycle", setting.checked ? "1" : "0"));
  let pressed = null, rightPressed = null, menu = null;
  const allowed = event => activeToolMode === "select" && !shapeEyedropperActive && !vBoxSelectActive && !isPanning
    && !selectionLockActive && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey;
  const close = () => { menu?.remove(); menu = null; };
  const select = object => {
    if (!vinylObjects().includes(object) || object.kloudy?.locked) return;
    canvas.discardActiveObject();
    restoreLayoutSelection([object]);
    updateSelectionPanel();
    canvas.requestRenderAll();
  };
  canvas.upperCanvasEl.addEventListener("mousedown", event => {
    close();
    rightPressed = event.button === 2 && allowed(event) ? { x: event.clientX, y: event.clientY } : null;
    pressed = event.button === 0 && setting.checked && allowed(event)
      && !canvas.getActiveObject()?.__corner
      ? { x: event.clientX, y: event.clientY, selected: selectedVinylObjects()[0], point: KfpsFabricAdapter.scenePoint(canvas, event) } : null;
  }, true);
  window.addEventListener("mouseup", event => {
    const down = pressed; pressed = null;
    if (!down || !allowed(event) || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 3) return;
    queueMicrotask(() => {
      const hits = overlappingVinylObjects(down.point);
      if (hits.length) select(hits[(hits.indexOf(down.selected) + 1) % hits.length]);
    });
  });
  canvas.upperCanvasEl.addEventListener("contextmenu", event => {
    if (!allowed(event) || !rightPressed || Math.hypot(event.clientX - rightPressed.x, event.clientY - rightPressed.y) > 3) return;
    rightPressed = null;
    const hits = overlappingVinylObjects(KfpsFabricAdapter.scenePoint(canvas, event));
    if (!hits.length) return;
    event.preventDefault(); close();
    menu = document.createElement("div"); menu.className = "overlapMenu";
    menu.setAttribute("role", "menu"); menu.setAttribute("aria-label", KfpsI18n.t("Overlapping layers"));
    for (const [index, object] of hits.entries()) {
      const item = document.createElement("button"); item.type = "button"; item.setAttribute("role", "menuitem");
      item.textContent = `${index + 1}. ${object.kloudy?.name || localizedTypeLabel(object.kloudy?.type)}${object.kloudy?.mask ? KfpsI18n.t(" (mask)") : ""}`;
      item.addEventListener("click", () => { select(object); close(); canvas.upperCanvasEl.focus(); });
      menu.append(item);
    }
    document.body.append(menu);
    menu.style.left = `${Math.max(4, Math.min(event.clientX, innerWidth - menu.offsetWidth - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(event.clientY, innerHeight - menu.offsetHeight - 4))}px`;
    menu.firstElementChild.focus();
  });
  document.addEventListener("pointerdown", event => { if (menu && !menu.contains(event.target)) close(); }, true);
  document.addEventListener("keydown", event => {
    if (event.isComposing || event.keyCode === 229) return;
    if (!menu) return;
    if (event.key === "Escape") { event.preventDefault(); event.stopImmediatePropagation(); close(); canvas.upperCanvasEl.focus(); }
    if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      event.preventDefault(); event.stopImmediatePropagation();
      const items = Array.from(menu.children), index = items.indexOf(document.activeElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length].focus();
    }
  }, true);
  window.addEventListener("blur", () => { close(); pressed = null; });
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
    const response = await fetch(STARTUP_HELP_CONFIRMED_API, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    if (response.ok) {
      const data = await response.json();
      return data.confirmed === true;
    }
  } catch (_err) {
    // Direct file/browser fallback only. Normal app launches use the app-folder marker API.
  }
  try { return localStorage.getItem(STARTUP_HELP_CONFIRMED_KEY) === "true"; }
  catch (_) { return false; }
}

async function writeStartupHelpConfirmed() {
  try {
    const response = await fetch(STARTUP_HELP_CONFIRMED_API, {
      method: "POST",
      headers: EDITOR_MUTATION_HEADERS,
    });
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

function maybeShowProjectSharingNotice() {
  if (editorSettings.getItem(PROJECT_SHARING_ACK_KEY) === PROJECT_SHARING_NOTICE_VERSION) return false;
  const dialog = $("projectSharingDialog");
  if (!dialog) return false;
  $("projectSharingAcknowledge").checked = false;
  $("projectSharingContinue").disabled = true;
  $("projectSharingError").hidden = true;
  if (!dialog.open) dialog.showModal();
  return true;
}

async function continueEditorStartup() {
  if (maybeShowProjectSharingNotice()) return;
  if (maybeShowLanguageNotice()) return;
  if (startupRecoveryHandled) return;
  startupRecoveryHandled = true;
  const mode = new URLSearchParams(location.search).get("mode");
  if (mode === "new") {
    await startBlankCanvas();
    const url = new URL(location.href);
    url.searchParams.delete("mode");
    window.history.replaceState(null, "", url);
  } else if (!startupProjectId() && !startupBrowseMode() && mode !== "tutorial") {
    await maybeShowAutosaveRecovery();
  }
  if (startupBrowseMode() === "json") openJsonBrowser();
}

function maybeShowLanguageNotice() {
  if (editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY) === "1") return false;
  const dialog = $("languageNoticeDialog");
  if (!dialog) return false;
  $("languageNoticeAcknowledge").checked = false;
  $("languageNoticeContinue").disabled = true;
  $("languageNoticeError").hidden = true;
  if (!dialog.open) dialog.showModal();
  return true;
}

async function confirmLanguageNotice() {
  const checkbox = $("languageNoticeAcknowledge");
  if (!checkbox.checked || languageNoticeConfirmationPending) return;
  const button = $("languageNoticeContinue");
  const error = $("languageNoticeError");
  const previous = editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY);
  let saved = false;
  languageNoticeConfirmationPending = true;
  checkbox.disabled = button.disabled = true;
  error.hidden = true;
  try {
    editorSettings.setItem(LANGUAGE_NOTICE_ACK_KEY, "1");
    if (window.KfpsEditorPreferences && !await KfpsEditorPreferences.flush()) throw new Error("Preference write failed");
    if (location.protocol === "file:" && localStorage.getItem(LANGUAGE_NOTICE_ACK_KEY) !== "1") throw new Error("Preference write failed");
    saved = true;
  } catch (_) {
    if (previous === null) editorSettings.removeItem(LANGUAGE_NOTICE_ACK_KEY);
    else editorSettings.setItem(LANGUAGE_NOTICE_ACK_KEY, previous);
    error.textContent = KfpsI18n.t("Your acknowledgment could not be saved. Please try again.");
    error.hidden = false;
  } finally {
    languageNoticeConfirmationPending = false;
    checkbox.disabled = false;
    button.disabled = !checkbox.checked;
  }
  if (saved) {
    $("languageNoticeDialog").close();
    $("editorLanguageSelect").focus();
    await continueEditorStartup();
  }
}

async function confirmProjectSharingNotice() {
  const checkbox = $("projectSharingAcknowledge");
  if (!checkbox?.checked || projectSharingConfirmationPending) return;
  const button = $("projectSharingContinue");
  const error = $("projectSharingError");
  const previous = editorSettings.getItem(PROJECT_SHARING_ACK_KEY);
  let saved = false;
  projectSharingConfirmationPending = true;
  button.disabled = checkbox.disabled = true;
  error.hidden = true;
  try {
    editorSettings.setItem(PROJECT_SHARING_ACK_KEY, PROJECT_SHARING_NOTICE_VERSION);
    if (window.KfpsEditorPreferences && !await KfpsEditorPreferences.flush()) {
      throw new Error(KfpsI18n.t("Your acknowledgment could not be saved. Please try Continue again."));
    }
    if (location.protocol === "file:" && localStorage.getItem(PROJECT_SHARING_ACK_KEY) !== PROJECT_SHARING_NOTICE_VERSION) {
      throw new Error(KfpsI18n.t("Browser storage is unavailable. Your acknowledgment could not be saved."));
    }
    saved = true;
  } catch (err) {
    // A failed save must not become a browser-only acknowledgment on restart.
    if (previous === null) editorSettings.removeItem(PROJECT_SHARING_ACK_KEY);
    else editorSettings.setItem(PROJECT_SHARING_ACK_KEY, previous);
    error.textContent = err.message || String(err);
    error.hidden = false;
  } finally {
    projectSharingConfirmationPending = false;
    checkbox.disabled = false;
    button.disabled = !checkbox.checked;
  }
  if (saved) {
    $("projectSharingDialog").close();
    await continueEditorStartup();
  }
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
  let time = KfpsI18n.t("unknown time");
  if (stamp) {
    const date = new Date(stamp);
    if (!Number.isNaN(date.getTime())) time = date.toLocaleString(KfpsI18n.locale);
  }
  return KfpsI18n.t("{0} - {1} layer{2} - saved {3}", name, count, count === 1 ? "" : "s", time);
}

async function readAutosavePayload() {
  recoveryReadWarning = "";
  const candidates = [];
  let clearedRevision = 0;
  try {
    clearedRevision = Number(localStorage.getItem(AUTOSAVE_CLEAR_KEY)) || 0;
    const browserPayload = await editorPersistence.request("parseText", { text: localStorage.getItem(AUTOSAVE_KEY) || "null" });
    if (browserPayload && Array.isArray(browserPayload.shapes)) candidates.push(browserPayload);
  } catch (_err) {
    // The app-folder copy remains available when browser storage fails.
  }
  try {
    const data = await editorPersistence.request("readRecovery");
    if (data.fallback) recoveryReadWarning = KfpsI18n.t("The newest recovery copy was unreadable. An earlier complete checkpoint was restored.");
    else if (data.error && !data.payload) recoveryReadWarning = KfpsI18n.t("Recovery could not be read. Saved projects have not been changed.");
    if (data.payload && Array.isArray(data.payload.shapes)) candidates.push(data.payload);
    clearedRevision = Math.max(clearedRevision, data.clearedRevision || 0);
  } catch (_err) {
    recoveryReadWarning = KfpsI18n.t("Recovery could not be read. Saved projects have not been changed.");
  }
  autosaveRevision = Math.max(autosaveRevision, clearedRevision, ...candidates.map(recoveryRevision));
  return candidates
    .filter((payload) => clearedRevision <= 0 || recoveryRevision(payload) > clearedRevision)
    .sort((left, right) => recoveryRevision(right) - recoveryRevision(left))[0] || null;
}

async function recoverAutosavePayload(payload) {
  if (!payload || !Array.isArray(payload.shapes)) {
    setStatus(KfpsI18n.t("Autosave recovery failed: temp save has no shapes list."));
    return false;
  }
  const generation = beginDocumentLoad();
  recoveryRestoreDepth++;
  let restored = false;
  try {
    if (!await loadPayload({
      shapes: payload.shapes,
      editor_collapsed_groups: payload.editor_collapsed_groups || [],
    }, { generation, strict: true, name: cleanProjectBaseName(payload.name, "autosave"), projectName: null })) return false;
    const loadedHistory = currentHistoryState();
    applySavedGuideState(payload.editor_guides || null);
    let referenceError = null;
    try {
      await restoreSourceOverlayFromProject(payload.editor_source_overlay || null);
    } catch (err) {
      if (generation !== documentGeneration) return false;
      referenceError = err;
      clearSourceOverlayState();
    }
    if (generation !== documentGeneration) return false;
    if (referenceError) unavailableSourceOverlayState = payload.editor_source_overlay || null;
    flushPendingNudgeHistory();
    if (currentHistoryState() !== loadedHistory) {
      restored = true;
      return true;
    }
    establishLoadedHistoryBoundary("recovered work", { writeRecovery: false });
    if (payload.editor_session?.project_name) currentProjectName = cleanProjectBaseName(payload.editor_session.project_name);
    if (payload.editor_session?.saved === true && currentProjectName && !referenceError) markCurrentHistorySaved(currentProjectName);
    recoveryAutosavePayload = null;
    restored = true;
    if (referenceError) {
      setStatus(
        KfpsI18n.t("Recovered {0}, but its reference image could not be restored. ", autosaveSummary(payload))
        + KfpsI18n.t("Its original reference data is still preserved in projects and recovery. Replace or remove it explicitly to discard it."),
      );
      showCornerNotice(
        KfpsI18n.t("Recovered without reference image"),
        KfpsI18n.error(referenceError.message || String(referenceError)),
      );
    } else {
      setStatus(KfpsI18n.t("Previous session restored: {0}.", autosaveSummary(payload)));
    }
    return true;
  } catch (err) {
    if (generation !== documentGeneration) return false;
    clearBusy();
    updateDocumentState();
    setStatus(KfpsI18n.t("Autosave recovery failed: {0}", KfpsI18n.error(err.message)));
    return false;
  } finally {
    if (generation === documentGeneration) recoveryRestoreDepth--;
    if (restored && generation === documentGeneration) writeAutosavePayload(autosavePayloadFromState(currentHistoryState() || snapshotEditorState()));
  }
}

async function maybeShowAutosaveRecovery() {
  if (isTextVinylHarnessRun()) {
    $("autosaveRecoveryDialog")?.close();
    return false;
  }
  const generation = documentGeneration;
  const payload = await readAutosavePayload();
  if (generation !== documentGeneration) return true;
  if (recoveryReadWarning) showCornerNotice(KfpsI18n.t("Recovery notice"), recoveryReadWarning);
  if (!payload || !Array.isArray(payload.shapes)) return false;
  if (!payload.shapes.length && !payload.editor_source_overlay && !payload.editor_guides?.guides?.length
    && !payload.editor_session?.project_name) return false;
  recoveryAutosavePayload = payload;
  if (window.qt?.webChannelTransport && await recoverAutosavePayload(payload)) return true;
  const summary = $("autosaveRecoverySummary");
  if (summary) summary.textContent = KfpsI18n.t("Found: {0}", autosaveSummary(payload));
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
    title: KfpsI18n.t("Open, Save, And Export"),
    body: KfpsI18n.t("New starts a blank workspace. Open JSON starts from a portable vinyl, while Open Project restores editable work. Save keeps layers, groups, guides, and your reference image; Export JSON creates the game-ready file used in KFPS Outputs."),
    target: ".menuGroup:first-child",
    panel: "propertiesPane",
    tool: "select",
  },
  {
    title: KfpsI18n.t("Choose A Tool"),
    body: KfpsI18n.t("The left rail exposes every creation mode: selection, native shapes, text, pixel art, color picking, guides, reference controls, reference movement, and masks. Picking a tool opens its matching inspector."),
    target: ".toolRail",
    tool: "select",
  },
  {
    title: KfpsI18n.t("Work On The Canvas"),
    body: KfpsI18n.t("Click or box-select layers, then move, scale, rotate, or skew them. Mouse wheel zooms; middle or right drag pans. The HUD reports the current tool, pointer position, layer count, and hovered shape."),
    target: ".canvasStage",
    panel: "propertiesPane",
    tool: "select",
    canvasPulse: true,
  },
  {
    title: KfpsI18n.t("Layers Stay In Reach"),
    body: KfpsI18n.t("The upper-right panel always shows draw order. Top rows draw over lower rows. Select, search, group, rename, hide, lock, and move layers one step or all the way forward or backward. Drag the divider to resize this list."),
    target: "#layersPane",
    panel: "layersPane",
    tool: "select",
  },
  {
    title: KfpsI18n.t("Edit Precisely"),
    body: KfpsI18n.t("Properties combines color, alpha, exact transforms, flips, quarter turns, align and distribute commands, selection helpers, and picking behavior. Locked layers are skipped instead of changed accidentally."),
    target: "#propertiesPane",
    panel: "propertiesPane",
    tool: "select",
  },
  {
    title: KfpsI18n.t("Add Native Shapes"),
    body: KfpsI18n.t("Search the native shape library or browse by family. The Place control in the toolbar adds at the top, inserts around your selection, or replaces once while preserving the selected layer's transform and appearance."),
    target: "#shapeLibraryPane",
    panel: "shapeLibraryPane",
    tool: "shapeLibrary",
  },
  {
    title: KfpsI18n.t("Build Editable Text"),
    body: KfpsI18n.t("Text converts typed characters into real native Forza letter shapes. The result remains a normal editable layer group, so you can adjust spacing, color, transforms, and layer order afterward."),
    target: "#textPane",
    panel: "textPane",
    tool: "text",
  },
  {
    title: KfpsI18n.t("Build Pixel Art"),
    body: KfpsI18n.t("Pixel Art detects a deliberate source grid and merges neighboring same-color pixels into stretched native rectangles. Check the predicted grid and layer budget before generating."),
    target: "#pixelArtPane",
    panel: "pixelArtPane",
    tool: "pixelArt",
  },
  {
    title: KfpsI18n.t("Align With Guides"),
    body: KfpsI18n.t("Draw free, horizontal, or vertical guides and enable a grid for repeated spacing. Hold Control during transforms to snap. Guides and grid lines are project helpers and never consume game layers."),
    target: "#guidesPane",
    panel: "guidesPane",
    tool: "guides",
    canvasPulse: true,
  },
  {
    title: KfpsI18n.t("Trace With A Reference"),
    body: KfpsI18n.t("Reference accepts images and layered SVGs for tracing and color sampling. Save keeps it for your next session. Export JSON never includes it or turns it into a game layer."),
    target: "#overlayPane",
    panel: "overlayPane",
    tool: "overlay",
  },
  {
    title: KfpsI18n.t("History Is Visible"),
    body: KfpsI18n.t("Every meaningful edit appears here. Click an entry to return to it, use Undo or Redo, and watch for the protected loaded-source marker. The title bar separately tells you whether the project is saved."),
    target: "#historyPane",
    panel: "historyPane",
    tool: "select",
  },
  {
    title: KfpsI18n.t("Check Before Export"),
    body: KfpsI18n.t("Export Check reports blocking transform problems plus hidden, outside-canvas, duplicate, unresolved-resource, and ineffective-mask warnings. Review the list, export, then select the file from Editor exports in KFPS Outputs."),
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
  if (progress) progress.textContent = KfpsI18n.t("Step {0} of {1}", index + 1, EDITOR_TOUR_STEPS.length);
  if (title) title.textContent = step.title;
  if (body) body.textContent = step.body;
  if (back) back.disabled = index <= 0;
  if (next) next.textContent = index >= EDITOR_TOUR_STEPS.length - 1 ? KfpsI18n.t("Finish") : KfpsI18n.t("Next");
  if (pulse) pulse.hidden = !step.canvasPulse;
  setStatus(KfpsI18n.t("Tour: {0}", step.title));
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
  setStatus(completed ? KfpsI18n.t("Editor tour complete. Use Help any time for the full reference.") : KfpsI18n.t("Editor tour closed."));
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
  $("languageNoticeDialog")?.addEventListener("cancel", event => event.preventDefault());
  $("languageNoticeAcknowledge")?.addEventListener("change", () => {
    $("languageNoticeContinue").disabled = !$("languageNoticeAcknowledge").checked;
  });
  $("languageNoticeContinue")?.addEventListener("click", confirmLanguageNotice);
  const languageSelect = $("editorLanguageSelect");
  if (languageSelect) {
    languageSelect.value = KfpsI18n.language;
    languageSelect.addEventListener("change", async () => {
      const next = languageSelect.value;
      if (!["en", "ko"].includes(next)) return;
      const previous = editorSettings.getItem(KfpsI18n.KEY);
      languageSelect.disabled = true;
      try {
        editorSettings.setItem(KfpsI18n.KEY, next);
        if (window.KfpsEditorPreferences && !await KfpsEditorPreferences.flush()) throw new Error(KfpsI18n.error("Preference write failed"));
        if (location.protocol === "file:" && localStorage.getItem(KfpsI18n.KEY) !== next) throw new Error("Preference write failed");
        showEditorMessage(KfpsI18n.t("Language saved"), KfpsI18n.t("Your language preference has been saved. Save your project, then close and reopen the editor to apply it. Your current workspace has not been changed."));
      } catch (_) {
        if (previous === null) editorSettings.removeItem(KfpsI18n.KEY);
        else editorSettings.setItem(KfpsI18n.KEY, previous);
        languageSelect.value = previous || KfpsI18n.language;
        showEditorMessage(KfpsI18n.t("Language setting could not be saved"), KfpsI18n.t("The language preference could not be saved. Your current language and workspace are unchanged."));
      } finally { languageSelect.disabled = false; }
    });
  }

  editorAssetLibrary = KfpsEditorAssets.install({
    headers: EDITOR_MUTATION_HEADERS, prompt: requestTextInput, confirm: requestConfirmation,
    notify: setStatus, download: downloadText,
    hasSelection: () => selectedVinylObjects().length > 0,
    selection: () => orderedSelectedVinylObjects().map(object => objectToShape(object, { includeEditorMeta: true })),
    insert: shapes => queueEditorMutation(() => insertCopiedShapesNow(shapes, { asset: true })),
  });
  bindTransformInputs();
  bindOverlapSelection();
  restoreDockState();
  bindDockSplitter();
  loadEditorClipboard();
  const initialTheme = editorSettings.getItem("kloudyFabricTheme") || document.documentElement.dataset.editorTheme;
  loadEditorThemes().then(() => loadEditorThemePreference()).then((serverTheme) => {
    if (!serverTheme) applyEditorTheme(initialTheme, { persist: false });
    if (!serverTheme) saveEditorThemePreference(normalizeTheme(initialTheme));
  });
  $("editorThemeSelect")?.addEventListener("change", (event) => applyEditorTheme(event.target.value));
  $("adjustTheme")?.addEventListener("click", openThemeAdjustDialog);
  $("themeAdjustBase")?.addEventListener("change", previewThemeAdjustBase);
  $("resetThemeAdjust")?.addEventListener("click", previewThemeAdjustBase);
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
  $("themeAdjustName")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat) $("saveThemeAdjust")?.click();
  });
  $("newCanvas")?.addEventListener("click", startBlankCanvas);
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
  $("jsonInput").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!await confirmWorkspaceReplacement(file.name || KfpsI18n.t("the selected JSON"))) {
      setStatus(KfpsI18n.t("Current unsaved work was kept."));
      event.target.value = "";
      return;
    }
    setBusy(KfpsI18n.t("Selected JSON: {0}", file.name));
    loadJsonFile(file)
      .then(() => $("jsonBrowserDialog")?.close())
      .catch((err) => showError(KfpsI18n.t("JSON import failed"), err))
      .finally(() => { event.target.value = ""; });
  });
  $("exportJson").addEventListener("click", exportJson);
  $("saveProject").addEventListener("click", () => saveProject());
  $("saveProjectAs")?.addEventListener("click", saveProjectAs);
  $("copyLayer")?.addEventListener("click", copySelectedLayers);
  $("pasteLayer")?.addEventListener("click", pasteCopiedLayers);
  $("fitView").addEventListener("click", fitDesignView);
  $("resetView").addEventListener("click", resetView);
  $("undoBtn").addEventListener("click", undo);
  $("redoBtn").addEventListener("click", redo);
  $("historyUndo")?.addEventListener("click", undo);
  $("historyRedo")?.addEventListener("click", redo);
  $("toggleRightDock")?.addEventListener("click", () => {
    const hidden = document.querySelector(".workspace")?.classList.contains("dockCollapsed");
    setDockVisible(Boolean(hidden));
  });
  $("collapseLayersDock")?.addEventListener("click", () => {
    const collapsed = document.querySelector(".rightDock")?.classList.contains("layersCollapsed");
    setLayersCollapsed(!collapsed);
  });
  $("selectionLockToggle")?.addEventListener("click", toggleSelectionLock);
  $("helpBtn").addEventListener("click", () => $("helpDialog").showModal());
  $("closeHelp").addEventListener("click", () => $("helpDialog").close());
  $("messageDialogClose")?.addEventListener("click", () => $("messageDialog")?.close());
  $("confirmationDialogCancel")?.addEventListener("click", () => {
    finishConfirmation(false);
    $("confirmationDialog")?.close();
  });
  $("confirmationDialogConfirm")?.addEventListener("click", () => {
    finishConfirmation(true);
    $("confirmationDialog")?.close();
  });
  $("confirmationDialog")?.addEventListener("cancel", (event) => {
    event.preventDefault();
    finishConfirmation(false);
    $("confirmationDialog")?.close();
  });
  $("confirmationDialog")?.addEventListener("close", () => {
    if (!$("confirmationDialog").open && confirmationResolver) finishConfirmation(false);
  });
  $("textPromptDialog")?.querySelector("form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    // Continue is the only submit action, including implicit Enter submission.
    finishTextPrompt($("textPromptInput")?.value ?? "");
    $("textPromptDialog")?.close();
  });
  $("textPromptCancel")?.addEventListener("click", () => {
    finishTextPrompt(null);
    $("textPromptDialog")?.close();
  });
  $("textPromptDialog")?.addEventListener("cancel", (event) => {
    event.preventDefault();
    finishTextPrompt(null);
    $("textPromptDialog")?.close();
  });
  $("textPromptDialog")?.addEventListener("close", () => {
    // A queued close event must not cancel a replacement prompt already open.
    if (!$("textPromptDialog").open && textPromptResolver) finishTextPrompt(null);
  });
  $("shortcutsBtn")?.addEventListener("click", () => $("shortcutsDialog")?.showModal());
  $("openShortcutsFromHelp")?.addEventListener("click", () => {
    $("helpDialog")?.close();
    $("shortcutsDialog")?.showModal();
  });
  $("closeShortcuts")?.addEventListener("click", () => $("shortcutsDialog")?.close());
  $("projectSharingDialog")?.addEventListener("cancel", event => event.preventDefault());
  $("projectSharingAcknowledge")?.addEventListener("change", () => {
    $("projectSharingContinue").disabled = !$("projectSharingAcknowledge").checked;
  });
  $("projectSharingContinue")?.addEventListener("click", confirmProjectSharingNotice);
  $("startupHelpConfirm")?.addEventListener("click", async () => {
    if ($("startupHelpDontShow")?.checked) {
      const marker = await writeStartupHelpConfirmed();
      $("startupHelpDialog")?.close();
      setStatus(marker
        ? KfpsI18n.t("Startup help confirmed for this app folder. The full Help menu is available from the Help button in the top toolbar.")
        : KfpsI18n.t("Startup help confirmed for this browser. The full Help menu is available from the Help button in the top toolbar."));
      return;
    }
    setStatus(KfpsI18n.t("Tick \"I have read and understood this\" before opening the editor."));
  });
  $("recoverAutosave")?.addEventListener("click", async () => {
    $("autosaveRecoveryDialog")?.close();
    await recoverAutosavePayload(recoveryAutosavePayload);
  });
  $("dismissAutosave")?.addEventListener("click", () => {
    $("autosaveRecoveryDialog")?.close();
    setStatus(KfpsI18n.t("Temp save kept. It will be offered again next launch until recovered, discarded, or replaced."));
  });
  $("discardAutosave")?.addEventListener("click", () => {
    $("autosaveRecoveryDialog")?.close();
    clearAutosave();
    recoveryAutosavePayload = null;
    setStatus(KfpsI18n.t("Temp save discarded."));
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
      : Number($("opacitySlider")?.value ?? rememberedColor[3] ?? 255);
    scheduleDialogColorPreview(hexToRgb(event.target.value, alpha));
  });
  $("dialogColorPicker").addEventListener("change", (event) => {
    const selected = selectedVinylObjects();
    const alpha = selected.length === 1
      ? Math.round((selected[0].opacity ?? 1) * 255)
      : Number($("opacitySlider")?.value ?? rememberedColor[3] ?? 255);
    commitDialogColor(hexToRgb(event.target.value, alpha));
  });
  $("applyFields").addEventListener("click", applySelectionFields);
  $("deleteLayer").addEventListener("click", deleteSelected);
  $("duplicateLayer").addEventListener("click", duplicateSelected);
  $("quickDeleteLayer")?.addEventListener("click", deleteSelected);
  $("quickDuplicateLayer")?.addEventListener("click", duplicateSelected);
  $("bringForward").addEventListener("click", () => moveSelected(1));
  $("sendBackward").addEventListener("click", () => moveSelected(-1));
  $("bringFront")?.addEventListener("click", () => moveSelectedToEdge(true));
  $("sendBack")?.addEventListener("click", () => moveSelectedToEdge(false));
  $("fitSelected").addEventListener("click", fitSelectedView);
  $("quickFitSelected")?.addEventListener("click", fitSelectedView);
  $("groupSelected").addEventListener("click", groupSelectedLayers);
  $("quickGroupSelected")?.addEventListener("click", groupSelectedLayers);
  $("renameSelectedLayer")?.addEventListener("click", renameSelectedLayer);
  $("renameSelectedGroup")?.addEventListener("click", renameSelectedGroup);
  $("hideSelectedGroup").addEventListener("click", toggleSelectedGroupVisibility);
  $("lockSelectedGroup").addEventListener("click", toggleSelectedGroupLock);
  $("ungroupSelected").addEventListener("click", ungroupSelectedLayers);
  $("changeSelectedShape")?.addEventListener("click", armShapeReplacementFromLayers);
  $("cancelGlobalShapeReplace")?.addEventListener("click", () => {
    pendingGlobalShapeReplacement = null;
    hideGlobalShapeReplacePanel();
    setStatus(KfpsI18n.t("Global Change Shape cancelled."));
  });
  $("applyColorToSelection").addEventListener("click", () => {
    const alpha = Number($("opacitySlider")?.value ?? rememberedColor[3] ?? 255);
    applyEditorColor(hexToRgb($("colorPicker")?.value || colorToHex(rememberedColor), alpha), "apply color to selection");
  });
  $("maskSelectedTool")?.addEventListener("click", toggleSelectedMaskLayers);
  $("colorPicker").addEventListener("input", applySelectionFields);
  $("opacitySlider").addEventListener("input", applySelectionFields);
  $("equalizeAlpha").addEventListener("click", equalizeSelectedAlpha);
  $("flipHorizontal")?.addEventListener("click", () => flipSelected("x"));
  $("flipVertical")?.addEventListener("click", () => flipSelected("y"));
  $("rotateLeft")?.addEventListener("click", () => rotateSelectedQuarter(-1));
  $("rotateRight")?.addEventListener("click", () => rotateSelectedQuarter(1));
  document.querySelectorAll("[data-align]").forEach((button) => {
    button.addEventListener("click", () => alignSelected(button.dataset.align));
  });
  $("distributeHorizontal")?.addEventListener("click", () => distributeSelected("x"));
  $("distributeVertical")?.addEventListener("click", () => distributeSelected("y"));
  $("selectAllLayers")?.addEventListener("click", selectAllLayers);
  $("selectInverseLayers")?.addEventListener("click", selectInverseLayers);
  $("selectSameShape")?.addEventListener("click", selectSameShapeLayers);
  $("selectSameColor")?.addEventListener("click", selectSameColorLayers);
  $("clearLayerSelection")?.addEventListener("click", clearLayerSelection);
  bindEnterToApply(["opacitySlider"]);
  $("layerSearch").addEventListener("input", refreshLayers);
  $("pixelSelect")?.addEventListener("change", () => setPixelSelection($("pixelSelect").checked));
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
    $("overlayLayerMode").addEventListener("change", (event) => {
      const previous = overlayLayerMode;
      setOverlayLayerMode(event.target.value);
      if (overlayImage && overlayLayerMode !== previous) markOverlayChanged("reference image adjusted");
    });
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
      setPixelArtStatus(KfpsI18n.t("Choose a pixel-art source image."));
      return;
    }
    setPixelArtStatus(KfpsI18n.t("Pixel-art source loaded: {0}. Press Generate to detect its pixel grid.", pixelArtSourceFile.name));
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
      editorSettings.setItem("kloudyFabricReuseLastFontSize", String(reuseLastFontSize));
      setStatus(reuseLastFontSize ? KfpsI18n.t("New font shapes reuse the last edited font size.") : KfpsI18n.t("New font shapes use viewport placement size."));
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
    if (event.isComposing || event.keyCode === 229) return;
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
    if (document.querySelector("dialog[open]")) return;
    if (activeToolMode === "guides") {
      if (event.key === "Escape") {
        event.preventDefault();
        cancelGuideInteraction();
        return;
      }
      if (event.key === "Shift" && guideDraft && guidePointer && !isPanning) {
        updateGuideDraft({ e: { clientX: guidePointer.clientX, clientY: guidePointer.clientY, shiftKey: true } });
      }
      if (event.key === " " && guidePointer && !Object.keys(shortcuts).some(action => shortcutMatches(event, action))) {
        event.preventDefault();
        if (!event.repeat && guidePointer) {
          guideSpacePan = true;
          isPanning = true;
          guideDraftPress = null;
          lastPan = { x: guidePointer.clientX, y: guidePointer.clientY };
          canvas.setCursor("grabbing");
        }
        return;
      }
    }
    const toolAction = ["selectTool", "shapeLibrary", "textTool", "pixelArt", "dropper", "guides", "overlay", "sourceTool"].find((action) => shortcutMatches(event, action));
    if (toolAction) {
      event.preventDefault();
      if (!event.repeat) {
        const toolKey = {
          selectTool: "v",
          shapeLibrary: "s",
          textTool: "t",
          pixelArt: "p",
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
        setStatus(KfpsI18n.t("Hold Select shortcut: box-select override active. Drag from anywhere, even on top of a shape."));
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
        setGuideStatus(KfpsI18n.t("No guide selected. Vinyl layers are protected while the Guides tool is active."));
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
    if (shortcutMatches(event, "copy")) {
      event.preventDefault();
      copySelectedLayers();
      return;
    }
    if (shortcutMatches(event, "paste")) {
      event.preventDefault();
      pasteCopiedLayers();
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
    if (event.key === " " && guideSpacePan) { event.preventDefault(); endGuidePan(); }
    if (event.key === "Shift" && activeToolMode === "guides" && guideDraft && guidePointer && !isPanning) {
      updateGuideDraft({ e: { clientX: guidePointer.clientX, clientY: guidePointer.clientY, shiftKey: false } });
    }
    if (event.isComposing || event.keyCode === 229) return;
    if (event.target && event.target.classList?.contains("shortcutCapture")) return;
    if (event.target && ["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) flushPendingNudgeHistory();
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
      setStatus(KfpsI18n.t("Box-select override released."));
    }
  });
  document.addEventListener("wheel", handleLayerDragWheel, { passive: false });
  document.addEventListener("pointerdown", flushPendingNudgeHistory, true);
  window.addEventListener("blur", () => {
    if (activeToolMode === "guides") { endGuidePan(); guidePointer = null; }
    flushPendingNudgeHistory();
    flushPendingAutosaveToBrowser();
    flushPendingAutosave();
    if (vBoxSelectActive) setVBoxSelectActive(false);
  });
}

window.addEventListener("beforeunload", (event) => {
  flushPendingNudgeHistory();
  flushPendingAutosaveToBrowser();
  if (documentDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "hidden") return;
  flushPendingNudgeHistory();
  flushPendingAutosaveToBrowser();
  flushPendingAutosave();
});
window.addEventListener("pagehide", flushPendingAutosaveToBrowser);

async function executeDesktopOperation(operation, payload = {}) {
  if (operation === "state") {
    flushPendingNudgeHistory();
    return { dirty: documentDirty, saving: recoveryRestoreDepth > 0 || pixelArtGenerationRunning || textVinylGenerationRunning || projectSaveInProgress || exportSaveInProgress || Boolean(editorAssetLibrary?.busy) };
  }
  if (operation === "close") {
    if (pixelArtGenerationRunning || textVinylGenerationRunning) return { ok: false, error: KfpsI18n.t("Wait for generation to finish, or start a new canvas to cancel it, before closing.") };
    if (recoveryRestoreDepth) return { ok: false, error: KfpsI18n.t("Wait for the project or recovery to finish loading before closing.") };
    if (editorAssetLibrary?.busy) return { ok: false, error: KfpsI18n.t("Wait for the asset library operation to finish before closing.") };
    flushPendingNudgeHistory();
    if (payload.action === "save") {
      await saveProject();
      if (documentDirty || projectSaveInProgress) return { ok: false, cancelled: true };
    }
    const revision = { generation: documentGeneration, history: currentHistoryState(), overlay: overlayRevision };
    flushPendingAutosaveToBrowser();
    await flushPendingAutosave();
    const settingsSaved = window.KfpsEditorPreferences ? await KfpsEditorPreferences.flush() : true;
    if (revision.generation !== documentGeneration || revision.history !== currentHistoryState() || revision.overlay !== overlayRevision) {
      return { ok: false, error: KfpsI18n.t("The document changed while preparing to close. Save the new changes first.") };
    }
    if (!settingsSaved) return { ok: false, error: KfpsI18n.t("The latest editor settings have not reached the app folder.") };
    if (hasEditableWorkspace() && autosaveStatus.serverOk !== true) return { ok: false, error: KfpsI18n.t("The latest recovery has not reached the app folder. Save the project before closing.") };
    return { ok: true };
  }
  if (operation !== "open") throw new Error(KfpsI18n.t("Unsupported editor window operation."));
  // An external launch must not replace work underneath a recovery, file, or
  // confirmation dialog already being handled in this window.
  let openDialog;
  while ((openDialog = document.querySelector("dialog[open]"))) {
    await new Promise(resolve => openDialog.addEventListener("close", resolve, { once: true }));
  }
  if (payload.project) {
    if (!await confirmWorkspaceReplacement(payload.project)) return { cancelled: true };
    const generation = beginDocumentLoad();
    const data = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(payload.project)}`);
    if (!await loadProjectPayload(data.payload, data.name || "project", { generation })) return { cancelled: true };
    clearBusy(KfpsI18n.t("Loaded project: {0}", data.name || payload.project));
  } else if (payload.mode === "new") {
    await startBlankCanvas();
  } else if (payload.mode === "json") {
    await openJsonBrowser();
  } else if (payload.mode === "tutorial") {
    const dialog = $("startupHelpDialog");
    if (dialog && !dialog.open) dialog.showModal();
  }
  if (payload.mode !== "tutorial") await maybeShowStartupHelp();
  return { ok: true };
}

window.KfpsDesktop = {
  ready: false,
  async execute(requestId, operation, payload) {
    let result;
    try { result = { ok: true, value: await executeDesktopOperation(operation, payload) }; }
    catch (err) {
      result = { ok: false, error: err.message || String(err) };
      showError(KfpsI18n.t("Editor operation failed"), err);
    }
    window.KfpsDesktopBridge?.completed(requestId, JSON.stringify(result));
  },
};

window.addEventListener("kfps-preferences-status", (event) => {
  if (event.detail?.error) setStatus(event.detail.error);
});

async function startEditor() {
  window.KfpsEditorDiagnostics?.configure({ headers: EDITOR_MUTATION_HEADERS, state: editorDiagnosticState });
  initCanvas();
  buildShapeLibrary();
  bindUi();
  startDiagnosticReadout();
  rememberColor(rememberedColor);
  applyGuideStateToUi();
  renderGuideObjects();
  updateSelectionPanel();
  updateShapePlacementLabel();
  updateDocumentState();
  renderHistoryList();
  startupProjectWasLoaded = await loadStartupProjectFromQuery();
  const startupHelpShown = await maybeShowStartupHelp();
  if (startupHelpShown) {
    $("startupHelpDialog").addEventListener("close", continueEditorStartup, { once: true });
  } else {
    await continueEditorStartup();
  }
  await nextFrame();
  window.KfpsDesktop.ready = true;
  if (window.KfpsEditorPreferences?.error) setStatus(KfpsEditorPreferences.error);
}

function editorDiagnosticState() {
  const active = canvas?.getActiveObject();
  const element = overlayImage?.getElement?.();
  return {
    editorRevision: 2026091101, ready: Boolean(window.KfpsDesktop?.ready),
    layers: vinylObjectRegistry.objects.length, objects: canvas?._objects?.length || 0,
    selected: isActiveSelectionObject(active) ? active._objects.length : active?.kloudy || active?.kloudyMaskOwner ? 1 : 0,
    shapeType: Number((active?.kloudyMaskOwner || active)?.kloudy?.type) || 0,
    helpers: selectedShapeOutlineHelpers.size, zoom: canvas?.getZoom() || 0,
    width: canvas?.width || 0, height: canvas?.height || 0, history: history.length,
    renderer: hybridDisabledReason ? "fallback" : hybridRenderActive ? "gpu-preview" : canvas ? "fabric" : "starting",
    referenceWidth: element?.naturalWidth || element?.width || 0,
    referenceHeight: element?.naturalHeight || element?.height || 0,
    referenceChars: (overlaySourceState?.dataUrl?.length || 0) + (overlaySourceState?.svgText?.length || 0),
    referenceAbove: overlayLayerMode === "above", referenceVisible: Boolean(overlayImage && overlayImage.visible !== false),
    referenceOpacity: overlayImage?.opacity || 0,
  };
}

function startDiagnosticReadout() {
  setInterval(() => {
    if ($("performancePane")?.hidden || !window.KfpsEditorDiagnostics) return;
    const data = window.KfpsEditorDiagnostics.snapshot();
    const metrics = data.metrics, state = data.state, log = data.logging;
    setText("perfFrame", KfpsI18n.t("{0} ms", metrics.frameP95.toFixed(1)));
    setText("perfWorst", KfpsI18n.t("{0} ms", metrics.frameMax.toFixed(1)));
    setText("perfStalls", String(metrics.totalGaps100));
    setText("perfTasks", String(metrics.totalTasks));
    setText("perfLayers", `${state.layers} / ${state.selected}`);
    setText("perfReference", `${state.referenceWidth} x ${state.referenceHeight}`);
    setText("perfRenderer", state.renderer === "gpu-preview" ? KfpsI18n.t("GPU preview") : state.renderer === "fallback" ? KfpsI18n.t("Fabric fallback") : "Fabric");
    setText("perfMemory", Number.isFinite(metrics.heapBytes) ? KfpsI18n.t("{0} MiB", (metrics.heapBytes / 1048576).toFixed(1)) : "-");
    const age = when => when ? KfpsI18n.t("{0} s ago", Math.max(0, Math.round((Date.now() - when) / 1000))) : KfpsI18n.t("Not confirmed");
    setText("perfRecoveryApp", age(data.recovery.serverAt));
    setText("perfRecoveryBrowser", age(data.recovery.browserAt));
    const healthy = data.transportOk && !log.error && log.last_write && Date.now() / 1000 - log.last_write < 8;
    setText("perfLog", healthy ? KfpsI18n.t("Writing locally") : KfpsI18n.t("Log writes not confirmed"));
    setText("perfDrops", String((log.dropped || 0) + metrics.clientDrops));
    $("perfLog").classList.toggle("diagnosticWarning", !healthy);
  }, 1000);
}

function beginEditorStartup() {
  startEditor().catch((err) => {
    window.KfpsDesktop.error = KfpsI18n.t("Editor operation failed") + ": " + (err.message || String(err));
    showError(KfpsI18n.t("Editor operation failed"), err);
  });
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", beginEditorStartup, { once: true });
else beginEditorStartup();
