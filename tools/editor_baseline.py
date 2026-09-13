"""Create the editor baseline from a frozen app and validated Python snapshot."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def build(app_root: Path, python_root: Path):
    root, python = app_root.resolve(), python_root.resolve()
    module_path = root / "KFPS.Editor/src/kfps_editor/baseline.py"
    spec = importlib.util.spec_from_file_location("editor_baseline_owner", module_path)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    probe = "import sys,json;sys.path.insert(0,sys.argv[1]);from kfps_editor.baseline import engine_identity,verify_import_origins;verify_import_origins(sys.argv[2]);print(json.dumps(engine_identity()))"
    result = subprocess.run([str(python / "python.exe"), "-I", "-B", "-c", probe, str(root / "KFPS.Editor/src"), str(python)],
                            env=owner.isolated_environment(), capture_output=True, text=True, timeout=60, check=True)
    engine = json.loads(result.stdout)
    if not engine["python"].startswith("3.12.") or engine["bits"] != 64:
        raise ValueError("Editor baseline requires Python 3.12 x64.")
    import re
    pins = dict(re.findall(r"^([A-Za-z0-9_-]+)==([^;\s]+)", (root / "KFPS.Editor/requirements.txt").read_text(), re.M))
    if engine["pyside"] != pins["PySide6"] or engine["qt"] != pins["PySide6"] or engine["webengine"] != pins["PySide6"]:
        raise ValueError("Bundled Qt does not match the editor dependency lock.")
    probe_packages = "import importlib.metadata,json,sys;print(json.dumps({n:importlib.metadata.version(n) for n in json.loads(sys.argv[1])}))"
    packages = subprocess.run([str(python / "python.exe"), "-I", "-B", "-c", probe_packages, json.dumps(list(pins))],
                             env=owner.isolated_environment(), capture_output=True, text=True, timeout=60, check=True)
    if json.loads(packages.stdout) != pins:
        raise ValueError("Bundled editor dependencies do not match exact requirements.")
    manifest = json.loads((root / "KFPS.Editor/manifest.json").read_text())
    paths = {"KFPS.Editor/manifest.json", "KFPS.Editor/requirements.txt"}
    paths.update(item["path"] for group in ("native", "shared") for item in manifest[group]
                 if item.get("role") != "bridge" or (root / item["path"]).is_file())
    for tree in ("KFPS.Editor/web", "KFPS.Editor/src"):
        paths.update(owner.executable_paths(root, tree))
    records = []
    for relative in sorted(paths):
        path = owner.safe_file(root, relative)
        records.append({"path": relative, "size": path.stat().st_size, "sha256": owner.file_hash(path)})
    # The supplied Python snapshot may be adjacent to, not inside, appRoot.
    for directory, folders, names in os.walk(python, followlinks=False):
        for name in list(folders):
            path = Path(directory) / name
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Linked runtime folder")
            if name == "__pycache__":
                folders.remove(name)
        for name in names:
            if name.endswith(".pyc"):
                continue
            relative = (Path(directory) / name).relative_to(python).as_posix()
            path = owner.safe_file(python, relative)
            records.append({"path": "python/" + relative, "size": path.stat().st_size, "sha256": owner.file_hash(path)})
    payload = {"schema": owner.SCHEMA, "engine": engine, "files": sorted(records, key=lambda r: r["path"])}
    target = root / owner.CONTRACT
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > owner.MAX_CONTRACT_BYTES:
        raise ValueError("Editor baseline inventory is too large.")
    target.write_bytes(encoded)
    return {"engine": engine, "files": len(records), "bytes": sum(r["size"] for r in records)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-root", required=True, type=Path)
    parser.add_argument("--python-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.app_root, args.python_root)))
