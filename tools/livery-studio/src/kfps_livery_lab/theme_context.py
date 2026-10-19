"""Session-local host context and Studio selection; never changes KFPS preferences."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading

LAB_ROOT = Path(__file__).resolve().parents[2]
MAX_BYTES = 32 * 1024
MAX_FONT_BYTES = 8 * 1024 * 1024
COLOR_KEYS = frozenset((
    "--bg", "--shell", "--panel", "--panel2", "--panel3", "--text", "--muted", "--soft",
    "--line", "--line2", "--accent", "--accent2", "--good", "--warn", "--danger",
    "--canvas-bg", "--fabric-canvas-bg", "--editor-grid-line", "--editor-grid-axis",
    "--editor-guide-line", "--editor-guide-selected", "--editor-guide-draft", "--editor-notch-line",
    "--editor-notch-muted", "--editor-notch-active", "--editor-selection-border", "--editor-shape-outline",
    "--editor-selection-corner", "--editor-selection-corner-stroke", "--editor-skew-corner",
    "--shape-tile-bg", "--dialog-bg", "--dialog-header",
))
FONT_TYPES = {".ttf": (b"\x00\x01\x00\x00", "font/ttf", "truetype"),
              ".otf": (b"OTTO", "font/otf", "opentype"),
              ".woff": (b"wOFF", "font/woff", "woff"), ".woff2": (b"wOF2", "font/woff2", "woff2")}
FONT_ID = re.compile(r"[a-f0-9]{64}")


def _text(value, maximum, label):
    if (not isinstance(value, str) or not 0 < len(value.strip()) <= maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f"Invalid theme {label}.")
    return value.strip()


def _family(value, *, single=False):
    value = _text(value, 120 if single else 240, "font family")
    allowed = " -_." if single else " -_.,'\""
    if any(not c.isalnum() and c not in allowed for c in value):
        raise ValueError("Invalid theme font family.")
    return value


def _color(value):
    value = _text(value, 100, "color")
    if re.fullmatch(r"#(?:[a-fA-F0-9]{3}|[a-fA-F0-9]{4}|[a-fA-F0-9]{6}|[a-fA-F0-9]{8})", value):
        return value
    if value.lower() == "transparent":
        return value
    match = re.fullmatch(r"(rgb|rgba)\(\s*(\d{1,3}(?:\.\d+)?)\s*,\s*(\d{1,3}(?:\.\d+)?)\s*,\s*(\d{1,3}(?:\.\d+)?)(?:\s*,\s*(\d*(?:\.\d+)?))?\s*\)", value)
    if match and all(0 <= float(part) <= 255 for part in match.group(2, 3, 4)):
        alpha = match.group(5)
        if (match.group(1) == "rgb" and alpha is None) or (match.group(1) == "rgba" and alpha and 0 <= float(alpha) <= 1):
            return value
    raise ValueError("Theme colors must be resolved literal RGB or hexadecimal colors.")


def validate_theme(value):
    if not isinstance(value, dict) or set(value) - {"name", "variables", "fontFamily", "fontAssets"}:
        raise ValueError("Invalid resolved theme envelope.")
    values = value.get("variables")
    if not isinstance(values, dict) or not values or set(values) - COLOR_KEYS:
        raise ValueError("Theme variables must use existing editor color keys.")
    fonts = value.get("fontAssets", [])
    if not isinstance(fonts, list) or len(fonts) > 3:
        raise ValueError("A theme may select at most three font assets.")
    assets = []
    for font in fonts:
        if not isinstance(font, dict) or set(font) != {"family", "asset"}:
            raise ValueError("Invalid theme font selection.")
        asset = _text(font["asset"], 180, "font asset")
        parts = asset.split("/")
        if (any(part in ("", ".", "..") for part in parts) or not re.fullmatch(r"[A-Za-z0-9_./ -]+", asset)
                or Path(asset).suffix.lower() not in FONT_TYPES
                or not (parts[0] == "fonts" and len(parts) >= 2
                        or len(parts) >= 4 and parts[0] == "themes" and parts[2] == "fonts")):
            raise ValueError("Theme font asset is outside the bundled font roots.")
        assets.append({"family": _family(font["family"], single=True), "asset": asset})
    result = {"name": _text(value.get("name"), 120, "name"),
              "variables": {key: _color(color) for key, color in values.items()},
              "fontFamily": _family(value.get("fontFamily")), "fontAssets": assets}
    if len(json.dumps(result).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Theme context exceeds 32 KiB.")
    return result


def validate_studio_theme(value):
    fields = {"format", "id", "name", "base", "values", "fontFamily", "colorScheme"}
    if (not isinstance(value, dict) or set(value) != fields
            or value["format"] != "kfps_fabric_editor_theme_v1"
            or value["base"] not in ("pastel", "dark", "blackout", "whiteout")
            or value["colorScheme"] not in ("light", "dark")
            or not isinstance(value["values"], dict) or set(value["values"]) != COLOR_KEYS):
        raise ValueError("Invalid Studio theme format.")
    colors = {}
    for key, raw in value["values"].items():
        color = _text(raw, 200, "color")
        # Preserve supported custom CSS colors; reject all references/declarations.
        if (not re.fullmatch(r"[a-zA-Z0-9#.,%+()/ -]+", color)
                or re.search(r"\b(?:inherit|initial|unset|revert|revert-layer|currentcolor)\b", color, re.I)
                or any(name.lower() not in {"rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch", "color", "color-mix"}
                       for name in re.findall(r"([a-zA-Z][a-zA-Z0-9-]*)\s*\(", color))):
            raise ValueError("Invalid Studio theme color.")
        colors[key] = color
    family = _text(value["fontFamily"], 256, "font family")
    if any(not c.isalnum() and c not in " -_.,'\"" for c in family) or len(family.split(",")) > 8:
        raise ValueError("Invalid Studio font family.")
    result = dict(value, id=_text(value["id"], 128, "ID"), name=_text(value["name"], 128, "name"),
                  values=colors, fontFamily=family)
    if len(json.dumps(result).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Studio theme exceeds 32 KiB.")
    return result


def _persist(root, path, value):
    root.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        raise ValueError("Redirected theme context is not supported.")
    descriptor, temporary = tempfile.mkstemp(prefix=path.stem + "-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=True, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("Duplicate theme field.")
        result[key] = value
    return result


def _regular(path, root, maximum):
    root, path = Path(root), Path(path)
    if (not path.is_relative_to(root) or path == root
            or not path.resolve().is_relative_to(root.resolve()) or path.resolve() == root.resolve()):
        raise ValueError("Theme asset is outside its authorized root.")
    current = path
    while True:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("Redirected theme assets are not supported.")
        if current == root:
            break
        current = current.parent
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= maximum:
            raise ValueError("Theme asset is not a bounded regular file.")
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Theme asset is too large.")
    return data


class ThemeContext:
    def __init__(self, session_root, kfps_root):
        self.root = Path(session_root).resolve()
        if not self.root.is_relative_to((LAB_ROOT / "runs").resolve()) or self.root == (LAB_ROOT / "runs").resolve():
            raise ValueError("Theme persistence requires an isolated run.")
        self.kfps_root = Path(kfps_root).resolve()
        self.assets = self.kfps_root / "KFPS.UI/assets"
        self.path = self.root / "host-ui-theme.json"
        self.studio_path = self.root / "studio-ui-theme.json"
        self.lock = threading.RLock()
        self.value = None
        self.studio = None
        self.fonts = {}
        self.host_font_assets = []
        self.studio_font_assets = []
        self.studio_fonts = {}
        self.studio_public_fonts = []
        if self.path.exists():
            # A damaged context never prevents opening an otherwise usable Studio.
            try:
                body = _regular(self.path, self.root, MAX_BYTES)
                value = validate_theme(json.loads(body, object_pairs_hook=_pairs))
                self.value, self.fonts = self._resolve(value)
                self.host_font_assets = value["fontAssets"]
            except (OSError, ValueError, RecursionError):
                pass
        if self.studio_path.exists():
            try:
                value = json.loads(_regular(self.studio_path, self.root, MAX_BYTES), object_pairs_hook=_pairs)
                if value is not None:
                    if not isinstance(value, dict) or set(value) != {"theme", "fontAssets"}:
                        raise ValueError("Invalid saved Studio theme selection.")
                    self.studio = validate_studio_theme(value["theme"])
                    self.studio_font_assets, self.studio_public_fonts, self.studio_fonts = self._studio_font_context(
                        self.studio, value["fontAssets"])
            except (OSError, ValueError, RecursionError):
                self.studio = None
                self.studio_font_assets, self.studio_public_fonts, self.studio_fonts = [], [], {}

    def _resolve(self, value):
        fonts, public = {}, []
        for font in value["fontAssets"]:
            path = self.assets / font["asset"]
            data = _regular(path, self.kfps_root, MAX_FONT_BYTES)
            header, mime, format_name = FONT_TYPES[path.suffix.lower()]
            if data[:4] != header:
                raise ValueError("Invalid bundled font format.")
            identifier = hashlib.sha256(data).hexdigest()
            fonts[identifier] = (path, mime, identifier)
            public.append({"family": font["family"], "url": "./api/ui-font/" + identifier, "format": format_name})
        context = {key: value[key] for key in ("name", "variables", "fontFamily")}
        context["fonts"] = public
        context["revision"] = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        return context, fonts

    def get(self):
        with self.lock:
            return self.value

    def update(self, value):
        value = validate_theme(value)
        context, fonts = self._resolve(value)
        with self.lock:
            _persist(self.root, self.path, value)
            self.value, self.fonts = context, fonts
            self.host_font_assets = value["fontAssets"]
            return context

    def _studio_font_context(self, theme, assets):
        envelope = validate_theme({"name": "Studio fonts", "variables": {"--panel": "#000000"},
                                   "fontFamily": "sans-serif", "fontAssets": assets})
        families = {name.strip().strip("\"'").casefold() for name in theme["fontFamily"].split(",")}
        selected = [item for item in envelope["fontAssets"] if item["family"].casefold() in families]
        public, fonts = self._resolve(dict(envelope, fontAssets=selected))
        return selected, public["fonts"], fonts

    def effective(self):
        with self.lock:
            if self.studio is None:
                return self.value
            result = dict(self.studio, source="studio", fonts=self.studio_public_fonts)
            result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            return result

    def select(self, value):
        theme = None if value is None else validate_studio_theme(value)
        with self.lock:
            assets, public, fonts = [], [], {}
            if theme is not None:
                available = {item["family"]: item for item in self.studio_font_assets}
                available.update({item["family"]: item for item in self.host_font_assets})
                families = {name.strip().strip("\"'").casefold() for name in theme["fontFamily"].split(",")}
                wanted = [item for item in available.values() if item["family"].casefold() in families]
                assets, public, fonts = self._studio_font_context(theme, wanted)
            _persist(self.root, self.studio_path, None if theme is None else {"theme": theme, "fontAssets": assets})
            self.studio = theme
            self.studio_font_assets, self.studio_public_fonts, self.studio_fonts = assets, public, fonts
            return {"ui_theme": self.effective(), "host_ui_theme": self.value}

    def font(self, identifier):
        with self.lock:
            registry = {**self.fonts, **self.studio_fonts}
            if not FONT_ID.fullmatch(identifier) or identifier not in registry:
                return None
            path, mime, expected = registry[identifier]
        data = _regular(path, self.kfps_root, MAX_FONT_BYTES)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Bundled font changed. Launch from the host again.")
        return data, mime
