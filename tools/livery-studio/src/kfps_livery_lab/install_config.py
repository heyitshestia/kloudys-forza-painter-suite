"""Read-only first-launch discovery for a portable Studio installation."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

MAX_SETTINGS_BYTES = 65536
MAX_ARCHIVES = 4096
ARCHIVE_NAME = re.compile(r"[A-Za-z0-9_ -]+\.zip", re.IGNORECASE)


def _not_redirected(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Studio setup cannot use redirected files or directories.")
    return path


@lru_cache(maxsize=8)
def _module(path, prefix):
    path = _not_redirected(path)
    name = prefix + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _vehicle_module(root):
    return _module(Path(root) / "tools/livery/vehicle_assets.py", "_studio_install_vehicles_")


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("KFPS livery settings contain duplicate fields.")
        value[key] = item
    return value


def _preferred_game(root):
    for relative in ("runtime/experiments/full-livery/state/settings.json", "runtime/full-livery/settings.json"):
        path = _not_redirected(root / relative)
        try:
            with path.open("rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SETTINGS_BYTES:
                    raise ValueError("KFPS livery settings are invalid or too large.")
                body = source.read(MAX_SETTINGS_BYTES + 1)
        except FileNotFoundError:
            continue
        if len(body) > MAX_SETTINGS_BYTES:
            raise ValueError("KFPS livery settings are too large.")
        try:
            value = json.loads(body, object_pairs_hook=_pairs)
        except (ValueError, RecursionError):
            raise ValueError("KFPS livery settings are unreadable. Relink FH6 from KFPS Liveries.") from None
        if not isinstance(value, dict):
            raise ValueError("KFPS livery settings must be an object.")
        preferred = value.get("fh6_game_folder")
        if preferred is not None and not isinstance(preferred, str):
            raise ValueError("KFPS FH6 folder setting is invalid.")
        if preferred and preferred.strip():
            return preferred.strip()
    return None


def automatic_config(lab_root, expected_kfps_root=None):
    paths = _module(Path(__file__).with_name("package_paths.py"), "_studio_install_paths_")
    root = paths.default_baseline(lab_root)
    if expected_kfps_root is not None and root != Path(expected_kfps_root).resolve(strict=True):
        raise ValueError("Studio is configured for a different KFPS installation.")
    assets = _vehicle_module(root)
    game = assets.discover_fh6_game_folder(_preferred_game(root))
    if game is None:
        raise ValueError("Open KFPS Liveries and link the FH6 game or Content folder, then launch Studio again.")
    try:
        cars = assets.resolve_fh6_cars_dir(game)
    except (OSError, assets.VehicleAssetError):
        raise ValueError("No readable FH6 car archives were found. Relink the game from KFPS Liveries.") from None
    if cars.name.casefold() != "cars" or cars.parent.name.casefold() != "media":
        raise ValueError("Link the FH6 game or Content folder containing media/Cars from KFPS Liveries.")
    game = cars.parent.parent
    archives = []
    for path in cars.iterdir():
        if path.is_file() and ARCHIVE_NAME.fullmatch(path.name):
            archives.append(path)
            if len(archives) > MAX_ARCHIVES:
                raise ValueError("Too many car archives. Check the FH6 folder selected in KFPS Liveries.")
    for path in sorted(archives, key=lambda item: (item.name.casefold(), item.name)):
        _not_redirected(path)
        try:
            if assets._car_clip_in_archive(path) is not None:
                return {"kfpsRoot": str(root), "pythonExe": str(root / "python/python.exe"),
                        "gameRoot": str(game), "archive": path.name}
        except (OSError, zipfile.BadZipFile):
            continue
    raise ValueError("No readable FH6 car archives were found. Relink the game from KFPS Liveries.")
