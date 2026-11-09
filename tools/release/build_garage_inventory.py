"""Regenerate the closed Garage inventory after an intentional component change."""
import argparse
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path


PINS = {"cryptography": "50.0.2", "cffi": "2.1.1", "pycparser": "3.12",
        "dnfile": "0.18.0", "dncil": "1.0.2", "pefile": "2024.8.26"}


def build(root):
    packages = {dist.metadata["Name"].lower(): dist.version
                for dist in distributions(path=[str(root / "vendor")])}
    if packages != PINS:
        raise ValueError("Garage dependency versions differ from the reviewed set")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Garage support cannot contain links")
        if not path.is_file() or path.name == "manifest.json":
            continue
        name = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            raise ValueError("Remove generated caches before recording the inventory")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files[name] = {"size": path.stat().st_size, "sha256": digest}
    return {"schema": 1, "packages": PINS, "files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "garage-reader")
    args = parser.parse_args()
    inventory = build(args.root)
    (args.root / "manifest.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    print(f"Recorded {len(inventory['files'])} Garage support files")
