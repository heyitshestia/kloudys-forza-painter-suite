from __future__ import annotations

import os
import string
import time
from pathlib import Path
from typing import Iterable

from .contracts import GameAdapter


SKIP_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "checkpoints",
    "generated",
    "imgs",
    "node_modules",
    "previews",
    "python",
    "reports",
    "runtime",
    "site-packages",
    "venv",
}


def unique_existing_paths(paths: Iterable[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def windows_drive_roots() -> list[Path]:
    if os.name == "nt":
        return [Path(f"{letter}:/") for letter in string.ascii_uppercase if Path(f"{letter}:/").exists()]
    return [path for path in (Path("C:/"), Path("/mnt/c"), Path("/mnt/d"), Path("/mnt/e")) if path.exists()]


def find_xboxgames_roots(drive: Path) -> list[Path]:
    found: list[Path] = []
    direct = drive / "XboxGames"
    if direct.is_dir():
        found.append(direct)
    queue: list[tuple[Path, int]] = [(drive, 0)]
    seen: set[str] = set()
    deadline = time.monotonic() + 4.0
    while queue and time.monotonic() < deadline:
        current, depth = queue.pop(0)
        try:
            key = str(current.resolve()).casefold()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if current.name.casefold() == "xboxgames":
            found.append(current)
            continue
        if depth >= 3:
            continue
        try:
            children = [item for item in current.iterdir() if item.is_dir()]
        except OSError:
            continue
        for child in children:
            name = child.name.casefold()
            if name in {"$recycle.bin", "program files", "program files (x86)", "programdata", "users", "windows"}:
                continue
            if name == "xboxgames" or depth < 2:
                queue.append((child, depth + 1))
    return unique_existing_paths(found)


def discover_xbox_game_save_roots() -> list[Path]:
    roots: list[Path] = []
    for drive in windows_drive_roots():
        for xbox_root in find_xboxgames_roots(drive):
            roots.extend((xbox_root / "GameSave", xbox_root / "GameSave" / "pgs"))
    return unique_existing_paths(roots)


def steam_install_roots() -> list[Path]:
    candidates: list[Path] = []
    try:
        import winreg  # type: ignore

        locations = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
        )
        for hive, key_name, value_name in locations:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                if value:
                    candidates.append(Path(str(value)))
            except OSError:
                continue
    except Exception:
        pass
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(Path(value) / "Steam")
    for drive in windows_drive_roots():
        candidates.extend((drive / "Steam", drive / "SteamLibrary" / "Steam"))
    return unique_existing_paths(candidates)


def discover_steam_remote_roots(app_id: str) -> list[Path]:
    roots: list[Path] = []
    for steam_root in steam_install_roots():
        userdata = steam_root / "userdata"
        if not userdata.is_dir():
            continue
        try:
            users = [item for item in userdata.iterdir() if item.is_dir()]
        except OSError:
            continue
        roots.extend(user / str(app_id) / "remote" for user in users)
    return unique_existing_paths(roots)


def discover_package_roots(adapter: GameAdapter) -> list[Path]:
    strategy = adapter.save_discovery
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    packages = Path(local_app_data) / "Packages"
    if not packages.exists():
        return []
    roots: list[Path] = []
    for pattern in strategy.package_globs:
        roots.extend(path for path in packages.glob(pattern) if path.exists())
    if strategy.package_tokens:
        try:
            package_folders = [item for item in packages.iterdir() if item.is_dir()]
        except OSError:
            package_folders = []
        tokens = tuple(token.casefold() for token in strategy.package_tokens)
        for package in package_folders:
            if any(token in package.name.casefold() for token in tokens):
                roots.extend(package / "SystemAppData" / marker for marker in strategy.package_markers)
    return unique_existing_paths(roots)


def discover_save_roots(adapter: GameAdapter, cached_roots: Iterable[Path] = ()) -> list[Path]:
    strategy = adapter.save_discovery
    roots = [
        root
        for root in cached_roots
        if (not strategy.package_tokens and not strategy.steam_app_id) or adapter.is_save_root(root)
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if strategy.local_ugc_relative and local_app_data:
        ugc_root = Path(local_app_data).joinpath(*strategy.local_ugc_relative)
        roots.extend((ugc_root / "LayerGroups", ugc_root))
    roots.extend(discover_package_roots(adapter))
    if strategy.steam_app_id:
        roots.extend(discover_steam_remote_roots(strategy.steam_app_id))
    if strategy.include_xbox_game_save:
        roots.extend(discover_xbox_game_save_roots())
    return unique_existing_paths(roots)


def is_xbox_game_save_root(root: Path) -> bool:
    text = str(root).replace("\\", "/").casefold().rstrip("/")
    return "/xboxgames/gamesave" in text


def targeted_xbox_layer_groups(root: Path) -> list[Path]:
    text = str(root).replace("\\", "/").casefold().rstrip("/")
    if text.endswith("/xboxgames/gamesave"):
        pgs_roots = [root / "pgs"]
    elif text.endswith("/xboxgames/gamesave/pgs"):
        pgs_roots = [root]
    else:
        return []
    paths: list[Path] = []
    for pgs in pgs_roots:
        if not pgs.exists():
            continue
        try:
            users = [item for item in pgs.iterdir() if item.is_dir()]
        except OSError:
            continue
        for user_folder in users:
            try:
                save_slots = [item for item in user_folder.iterdir() if item.is_dir()]
            except OSError:
                continue
            for slot in save_slots:
                containers = slot / "ContainersRoot"
                if not containers.is_dir():
                    continue
                try:
                    groups = [item for item in containers.iterdir() if item.is_dir() and item.name.startswith("LayerGroup_")]
                except OSError:
                    continue
                paths.extend(group / "C_group" for group in groups)
    return paths


def targeted_fh4_wgs_layer_groups(root: Path) -> list[Path]:
    from tools.cgroup.xbox_wgs import find_wgs_slots, read_wgs_layer_groups

    paths: list[Path] = []
    for slot in find_wgs_slots([root]):
        try:
            groups = read_wgs_layer_groups(slot)
        except (OSError, ValueError):
            continue
        paths.extend(group.cgroup_path for group in groups if group.cgroup_path and group.cgroup_path.is_file())
    return paths


def _fm8_collection_root(root: Path, collection: str) -> Path:
    if root.name.casefold() == collection.casefold():
        return root
    if root.name.casefold() == "ugc":
        return root / collection
    maybe = root / "Microsoft.ForzaMotorsport" / "UGC" / collection
    return maybe if maybe.is_dir() else root / collection


def targeted_fm8_collection(root: Path, collection: str) -> list[Path]:
    collection_root = _fm8_collection_root(root, collection)
    if not collection_root.is_dir():
        return []
    try:
        folders = [item for item in collection_root.iterdir() if item.is_dir()]
    except OSError:
        return []
    return [folder / "data" for folder in folders if (folder / "data").is_file()]


def targeted_fm8_layer_groups(root: Path) -> list[Path]:
    return targeted_fm8_collection(root, "LayerGroups")


def targeted_fm8_liveries(root: Path) -> list[Path]:
    return targeted_fm8_collection(root, "Liveries")


def is_cgroup_candidate(path: Path) -> bool:
    name = path.name.casefold()
    if name == "c_group" or name.endswith(".c_group"):
        return True
    from tools.cgroup.forza_source_decoder import probe_forza_source_kind

    return probe_forza_source_kind(path) == "cgroup"


def bounded_source_walk(root: Path, max_files: int | None, max_seconds: float | None, walk_kind: str) -> list[Path]:
    if not root.exists():
        return []
    found: list[Path] = []
    scanned = 0
    deadline = time.monotonic() + max_seconds if max_seconds is not None else None
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [name for name in dirnames if name.casefold() not in SKIP_DIRECTORY_NAMES]
        scanned += len(filenames)
        current = Path(dirpath)
        for filename in filenames:
            filename_lower = filename.casefold()
            if walk_kind == "fm8_data":
                candidate = filename_lower == "data" and current.parent.name.casefold() == "layergroups"
            elif walk_kind == "cgroup":
                candidate = is_cgroup_candidate(current / filename)
            else:
                candidate = filename_lower == "c_group" and current.name.startswith("LayerGroup_")
            if candidate:
                found.append(current / filename)
        if (max_files is not None and scanned >= max_files) or (deadline is not None and time.monotonic() >= deadline):
            break
    return found


def _targeted_sources(adapter: GameAdapter, root: Path) -> list[Path]:
    kind = adapter.save_discovery.targeted_kind
    if kind == "fm8_layer_groups":
        return targeted_fm8_layer_groups(root)
    if kind == "fh4_wgs_layer_groups":
        return targeted_fh4_wgs_layer_groups(root)
    return targeted_xbox_layer_groups(root)


def discover_save_artifacts(adapter: GameAdapter, roots: Iterable[Path]) -> list[Path]:
    roots = list(roots)
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if not path.is_file():
            return
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            return
        if key not in seen:
            seen.add(key)
            found.append(path)

    for root in roots:
        for path in _targeted_sources(adapter, root):
            add(path)
    strategy = adapter.save_discovery
    for root in roots:
        if strategy.targeted_kind != "fm8_layer_groups" and is_xbox_game_save_root(root):
            continue
        complete_walk = strategy.unbounded_matching_walk and adapter.is_save_root(root)
        for path in bounded_source_walk(
            root,
            max_files=None if complete_walk else 60_000,
            max_seconds=None if complete_walk else 18.0,
            walk_kind=strategy.walk_kind,
        ):
            add(path)
    found.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
    return found


def count_ignored_designs(adapter: GameAdapter, roots: Iterable[Path]) -> int:
    if adapter.save_discovery.ignored_design_kind != "fm8_liveries":
        return 0
    seen: set[str] = set()
    for root in roots:
        for path in targeted_fm8_liveries(root):
            try:
                seen.add(str(path.resolve()).casefold())
            except OSError:
                continue
    return len(seen)


def roots_for_sources(adapter: GameAdapter, source_paths: Iterable[Path]) -> list[Path]:
    roots: list[Path] = []
    strategy = adapter.save_discovery
    for source in source_paths:
        parts = source.parts
        lowered = [part.casefold() for part in parts]
        if "pgs" in lowered:
            roots.append(Path(*parts[: lowered.index("pgs") + 1]))
            continue
        if strategy.targeted_kind == "fm8_layer_groups" and "ugc" in lowered and "layergroups" in lowered:
            roots.append(Path(*parts[: lowered.index("ugc") + 2]))
            continue
        if strategy.steam_app_id and strategy.steam_app_id in lowered and "remote" in lowered:
            roots.append(Path(*parts[: lowered.index("remote") + 1]))
            continue
        for marker in (item.casefold() for item in strategy.package_markers):
            if marker in lowered:
                roots.append(Path(*parts[: lowered.index(marker) + 1]))
                break
    return unique_existing_paths(roots)
