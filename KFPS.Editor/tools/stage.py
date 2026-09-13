"""Stage only declared editor program files. Never copy an installed profile."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor.manifest import load_manifest


def stage(destination: Path) -> dict:
    destination = destination.resolve()
    # This is a qualification tool, not a publication or user-install updater.
    runs = (ROOT / "runtime/test-runs").resolve()
    if destination == runs or not destination.is_relative_to(runs):
        raise ValueError("Editor test stages must be inside runtime/test-runs")
    if destination.exists():
        raise FileExistsError("Refusing to overwrite an existing editor stage")
    manifest = load_manifest(ROOT)
    paths = {"KFPS.Editor/manifest.json", "KFPS.Editor/requirements.txt"}
    paths.update(f'{manifest["web_root"]}/{item["path"]}' for item in manifest["web"])
    paths.update(item["path"] for item in manifest["native"] if item["role"] != "bridge")
    paths.update(item["path"] for item in manifest["shared"])
    for tree in manifest["resource_trees"]:
        for source in (ROOT / tree["path"]).rglob("*"):
            if source.is_file():
                paths.add(source.relative_to(ROOT).as_posix())
    for relative in paths:
        source = ROOT / relative
        if not source.resolve().is_relative_to(ROOT) or not source.is_file() or source.is_symlink():
            raise ValueError(f"Invalid editor source: {relative}")
    destination.mkdir(parents=True)
    files = []
    for relative in sorted(paths):
        source, target = ROOT / relative, destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Staged bytes do not match: {relative}")
        files.append({"path": relative, "bytes": target.stat().st_size, "sha256": actual})
    report = {"schema": "kfps-editor-stage/1", "root": str(destination),
              "profileCopied": False, "mainUiIncluded": False, "files": files}
    (destination / "editor-stage.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = stage(args.destination)
    print(json.dumps({"root": report["root"], "files": len(report["files"]), "bytes": sum(f["bytes"] for f in report["files"])}))
