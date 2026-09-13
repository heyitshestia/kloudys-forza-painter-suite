"""Typed editor source inventory. Inclusion policy stays with each consumer."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "KFPS.Editor/manifest.json"


def _relative(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Editor source path must be a nonempty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value or "\x00" in value:
        raise ValueError(f"Unsafe editor source path: {value}")
    return path


def load_manifest(root=ROOT, *, verify_files=True):
    root = Path(root).resolve()
    data = json.loads((root / MANIFEST.relative_to(ROOT)).read_text(encoding="utf-8"))
    if data.get("schema") != "kfps-editor-sources/1":
        raise ValueError("Unsupported editor source manifest")
    _relative(data["web_root"])
    _relative(data["profile"])
    if data.get("legacy_web_mount") != "/tools/fabric-editor/":
        raise ValueError("The editor's stable web mount cannot change implicitly")
    paths = set()
    for section in ("web", "native", "resource_trees", "shared"):
        for item in data[section]:
            value = item["path"]
            _relative(value)
            full = f'{data["web_root"]}/{value}' if section == "web" else value
            if full in paths or not re.fullmatch(r"O(?:0[1-9]|1[0-9]|20)", item["owner"]):
                raise ValueError(f"Duplicate source or invalid owner: {full}")
            paths.add(full)
            if not (root / full).resolve().is_relative_to(root):
                raise ValueError(f"Editor source resolves outside installation: {full}")
            if verify_files and not (root / full).exists():
                raise ValueError(f"Missing editor source: {full}")
    return data


def diagnostic_assets():
    return tuple(item["path"] for item in load_manifest(verify_files=False)["web"] if item.get("diagnostic"))


def editor_web_root(root=ROOT):
    root = Path(root).resolve()
    return root / load_manifest(root, verify_files=False)["web_root"]


def native_source(role, root=ROOT):
    root = Path(root).resolve()
    matches = [item["path"] for item in load_manifest(root, verify_files=False)["native"] if item["role"] == role]
    if len(matches) != 1:
        raise ValueError(f"Expected one editor source for role: {role}")
    return root / matches[0]


def check():
    data = load_manifest()
    web = ROOT / data["web_root"]
    declared = {item["path"] for item in data["web"]}
    missing = {p.name for p in web.glob("*.js")} - declared
    if missing:
        raise ValueError(f"Unregistered editor JavaScript: {sorted(missing)}")
    native = {item["path"] for item in data["native"]}
    unregistered = {path.relative_to(ROOT).as_posix() for path in (ROOT / "KFPS.Editor/src/kfps_editor").glob("*.py")} - native
    if unregistered:
        raise ValueError(f"Unregistered editor Python: {sorted(unregistered)}")
    html = (web / "index.html").read_text(encoding="utf-8")
    loaded = re.findall(r'<script[^>]+src="([^"?]+)', html)
    if set(loaded) - declared:
        raise ValueError("Page loads sources absent from the editor manifest")
    public = ROOT / "tools/support_worker/public/editor-diagnostics.mjs"
    expected = json.dumps(list(diagnostic_assets()), separators=(",", ":"))
    match = re.search(r"export const ASSETS = (\[[^;]+\]);", public.read_text(encoding="utf-8"))
    if not match or json.loads(match[1].replace("'", '"')) != json.loads(expected):
        raise ValueError("Support diagnostics source inventory is stale; run editor_manifest.py sync")
    print(f'Editor manifest: {len(declared)} web sources, {len(data["native"])} native sources verified')


def sync():
    public = ROOT / "tools/support_worker/public/editor-diagnostics.mjs"
    source = public.read_text(encoding="utf-8")
    replacement = "export const ASSETS = " + json.dumps(list(diagnostic_assets())) + ";"
    source, count = re.subn(r"export const ASSETS = \[[^;]+\];", lambda _: replacement, source)
    if count != 1:
        raise ValueError("Expected one support diagnostics inventory")
    public.write_text(source, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["sync"]:
        sync()
    check()
