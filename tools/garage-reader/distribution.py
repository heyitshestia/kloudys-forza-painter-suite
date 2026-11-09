"""Closed inventory for the app-owned Garage worker."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


class DistributionError(ValueError):
    pass


def verify(root):
    root = Path(root)
    manifest = root / "manifest.json"
    try:
        if manifest.stat().st_size > 1024 * 1024:
            raise ValueError()
        inventory = json.loads(manifest.read_text(encoding="utf-8"))
        entries = inventory["files"]
        if inventory["schema"] != 1 or not isinstance(entries, dict) or not entries:
            raise ValueError()
        required = {"reader.py", "catalogue.py", "catalogue_reader.py", "distribution.py", "profile_reader.py", "profile_support.py",
                    "support/profile-support.dll", "licenses/LICENSE-Obfuscar.txt"}
        if not required <= entries.keys() or not any(p.startswith("vendor/") for p in entries):
            raise ValueError()
        found = set()
        for path in root.rglob("*"):
            if path.is_symlink() or getattr(os.path, "isjunction", lambda p: False)(path):
                raise ValueError()
            if not path.is_file():
                continue
            name = path.relative_to(root).as_posix()
            if name == "manifest.json":
                continue
            found.add(name)
            expected = entries.get(name)
            if not isinstance(expected, dict) or path.stat().st_size != expected["size"]:
                raise ValueError()
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != expected["sha256"]:
                raise ValueError()
        if found != entries.keys():
            raise ValueError()
        for name in entries:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise DistributionError("Garage support files failed verification") from None
    return inventory
