"""Fetch licensed typography and standard glyphs; no KFPS theme assets are reused."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen

DEST = Path(__file__).resolve().parents[1] / "assets" / "themes" / "rx93-psycho-frame"
GLYPHS = {
    "arrow-up": "arrow-up", "bolt": "zap", "changelog": "list-checks",
    "check": "check", "chevron-left": "chevron-left", "chevron-right": "chevron-right",
    "coffee": "coffee", "compress": "minimize-2", "cutout": "scissors",
    "community": "users-round",
    "editor": "pen-tool", "external": "external-link", "folder": "folder-open",
    "generate": "cpu", "heart": "heart", "help": "circle-question-mark", "home": "house",
    "images": "images", "json": "file-braces", "monitor": "monitor", "petal": "component",
    "refresh": "refresh-cw", "reports": "bug", "settings": "sliders-horizontal",
    "source-check": "file-check-corner", "terminal": "terminal", "tools": "wrench",
    "transfer": "arrow-right-left", "update": "download", "upscale": "maximize-2",
}


def fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": "KFPS-theme-assets"}), timeout=40) as response:
        return response.read()


def main() -> None:
    records = []
    manifest_path = DEST / "external-assets.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    revisions = previous.get("revisions", {})
    installed = {record["file"]: record for record in previous.get("files", [])}
    for repo in ("lucide-icons/lucide", "google/fonts"):
        if repo not in revisions:
            revisions[repo] = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits?per_page=1"))[0]["sha"]
    tree = json.loads(fetch(f"https://api.github.com/repos/lucide-icons/lucide/git/trees/{revisions['lucide-icons/lucide']}?recursive=1"))
    available = {entry["path"] for entry in tree["tree"]}
    missing = [glyph for glyph in GLYPHS.values() if f"icons/{glyph}.svg" not in available]
    if missing:
        raise RuntimeError(f"Review renamed Lucide glyphs before downloading: {missing}")

    def install(repo: str, source: str, target: str) -> None:
        url = f"https://raw.githubusercontent.com/{repo}/{revisions[repo]}/{source}"
        existing = installed.get(target)
        path = DEST / target
        if existing and existing["source"] == url and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == existing["sha256"]:
            records.append(existing)
            return
        data = fetch(url)
        source_hash = hashlib.sha256(data).hexdigest()
        if target.endswith(".svg"):
            ET.register_namespace("", "http://www.w3.org/2000/svg")
            svg = ET.fromstring(data)
            svg.set("stroke", "#ffffff")
            svg.set("stroke-width", "1.7")
            data = ET.tostring(svg, encoding="utf-8", xml_declaration=True)
        path = DEST / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({"file": target, "source": url, "source_sha256": source_hash, "sha256": hashlib.sha256(data).hexdigest(), "modification": "White 1.7px glyph mask for Qt tinting" if target.endswith(".svg") else None})

    for name, glyph in GLYPHS.items():
        install("lucide-icons/lucide", f"icons/{glyph}.svg", f"icons/{name}.svg")
    install("lucide-icons/lucide", "LICENSE", "licenses/Lucide-LICENSE.txt")
    for directory, filename in (("barlow", "Barlow-Medium.ttf"), ("barlowsemicondensed", "BarlowSemiCondensed-SemiBold.ttf")):
        install("google/fonts", f"ofl/{directory}/{filename}", f"fonts/{filename}")
        install("google/fonts", f"ofl/{directory}/OFL.txt", f"licenses/{directory}-OFL.txt")
    (DEST / "external-assets.json").write_text(json.dumps({"revisions": revisions, "files": records}, indent=2) + "\n", encoding="utf-8")
    print(f"Installed {len(records)} licensed files into {DEST}")


if __name__ == "__main__":
    main()
