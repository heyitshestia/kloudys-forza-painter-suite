from __future__ import annotations

import hashlib
import json
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CAR_CLIP_RE = re.compile(r"(?:^|/)carclips_(\d+)\.clipd$", re.IGNORECASE)
PROJECTION_PREFIX = "LiveryMasks/"


class VehicleAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class VehicleAsset:
    car_id: int
    model_code: str
    archive_path: str
    archive_name: str
    archive_size: int
    archive_mtime_ns: int
    clip_entry: str

    def public_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("archive_path", None)
        return data


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_fh6_cars_dir(game_folder: Path | str) -> Path:
    root = Path(game_folder).expanduser()
    candidates = [
        root,
        root / "media" / "cars",
        root / "Content" / "media" / "cars",
    ]
    if root.name.lower() == "content":
        candidates.insert(1, root / "media" / "cars")
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.zip")):
            return candidate.resolve()
    raise VehicleAssetError(
        f"FH6 car archives were not found below {root}. Choose the game folder or its Content folder."
    )


def normalize_fh6_game_folder(game_folder: Path | str) -> Path:
    """Return a stable install root after proving that it contains FH6 car data."""

    cars_dir = resolve_fh6_cars_dir(game_folder)
    if cars_dir.name.casefold() == "cars" and cars_dir.parent.name.casefold() == "media":
        return cars_dir.parent.parent.resolve()
    return cars_dir.resolve()


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).casefold() if path.exists() else str(path.absolute()).casefold()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _windows_drive_roots() -> list[Path]:
    candidates: list[Path] = []
    system_drive = str(os.environ.get("SystemDrive") or "C:").rstrip("\\/")
    if system_drive:
        candidates.append(Path(system_drive + "/"))
    try:
        import psutil

        candidates.extend(Path(item.mountpoint) for item in psutil.disk_partitions(all=False))
    except Exception:
        pass
    return [path for path in _unique_paths(candidates) if path.is_dir()]


def _running_fh6_executables() -> list[Path]:
    executables: list[Path] = []
    wanted = {"forzahorizon6.exe", "forzahorizon6-win64-shipping.exe"}
    try:
        import psutil

        for process in psutil.process_iter(["name", "exe"]):
            try:
                if str(process.info.get("name") or "").casefold() not in wanted:
                    continue
                executable = str(process.info.get("exe") or "").strip()
                if executable:
                    executables.append(Path(executable))
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                continue
    except Exception:
        pass
    return _unique_paths(executables)


def _steam_install_roots(drive_roots: Iterable[Path]) -> list[Path]:
    candidates: list[Path] = []
    try:
        import winreg

        registry_locations = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
        )
        for hive, key_name, value_name in registry_locations:
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
    for drive in drive_roots:
        candidates.extend((drive / "Steam", drive / "SteamLibrary", drive / "Games" / "Steam"))

    steam_roots = _unique_paths(candidates)
    libraries = list(steam_roots)
    path_pattern = re.compile(r'"path"\s+"([^"]+)"', re.IGNORECASE)
    for steam_root in steam_roots:
        manifest = steam_root / "steamapps" / "libraryfolders.vdf"
        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in path_pattern.finditer(text):
            libraries.append(Path(match.group(1).replace("\\\\", "\\")))
    return [path for path in _unique_paths(libraries) if path.is_dir()]


def discover_fh6_game_folder(
    preferred: Path | str | None = None,
    *,
    drive_roots: Iterable[Path] | None = None,
    process_executables: Iterable[Path] | None = None,
    steam_roots: Iterable[Path] | None = None,
) -> Path | None:
    """Find an FH6 install without recursively crawling arbitrary user folders."""

    drives = list(drive_roots) if drive_roots is not None else _windows_drive_roots()
    executables = (
        list(process_executables)
        if process_executables is not None
        else _running_fh6_executables()
    )
    libraries = list(steam_roots) if steam_roots is not None else _steam_install_roots(drives)
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred).expanduser())

    for executable in executables:
        current = Path(executable).parent
        candidates.extend((current, current / "Content"))
        candidates.extend(parent for parent in list(current.parents)[:3])

    folder_names = ("Forza Horizon 6", "ForzaHorizon6")
    for drive in drives:
        xbox_root = drive / "XboxGames"
        for name in folder_names:
            candidates.extend((xbox_root / name / "Content", xbox_root / name))
        try:
            xbox_children = list(xbox_root.iterdir()) if xbox_root.is_dir() else []
        except OSError:
            xbox_children = []
        for child in xbox_children:
            normalized = re.sub(r"[^a-z0-9]", "", child.name.casefold())
            if child.is_dir() and "forzahorizon6" in normalized:
                candidates.extend((child / "Content", child))

        windows_apps = drive / "Program Files" / "WindowsApps"
        for pattern in ("Microsoft.ForteBaseGame_*", "Microsoft.ForzaHorizon6_*"):
            try:
                candidates.extend(windows_apps.glob(pattern))
            except OSError:
                pass

    for library in libraries:
        common = library / "steamapps" / "common"
        for name in folder_names:
            candidates.extend((common / name, common / name / "Content"))

    for candidate in _unique_paths(candidates):
        try:
            return normalize_fh6_game_folder(candidate)
        except (OSError, VehicleAssetError):
            continue
    return None


def _index_signature(cars_dir: Path) -> dict[str, Any]:
    archives = list(cars_dir.glob("*.zip"))
    return {
        "cars_dir": str(cars_dir.resolve()),
        "archive_count": len(archives),
        "newest_mtime_ns": max((p.stat().st_mtime_ns for p in archives), default=0),
        "total_name_bytes": sum(len(p.name) for p in archives),
    }


def build_vehicle_asset_index(cars_dir: Path | str) -> dict[int, VehicleAsset]:
    cars = resolve_fh6_cars_dir(cars_dir)
    index: dict[int, VehicleAsset] = {}
    for archive in sorted(cars.glob("*.zip"), key=lambda p: p.name.casefold()):
        try:
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    match = CAR_CLIP_RE.search(name.replace("\\", "/"))
                    if not match:
                        continue
                    car_id = int(match.group(1))
                    stat = archive.stat()
                    index.setdefault(
                        car_id,
                        VehicleAsset(
                            car_id=car_id,
                            model_code=archive.stem,
                            archive_path=str(archive.resolve()),
                            archive_name=archive.name,
                            archive_size=stat.st_size,
                            archive_mtime_ns=stat.st_mtime_ns,
                            clip_entry=name,
                        ),
                    )
                    break
        except (OSError, zipfile.BadZipFile):
            continue
    return index


def load_or_build_vehicle_asset_index(
    game_folder: Path | str,
    cache_path: Path | str | None = None,
) -> dict[int, VehicleAsset]:
    cars_dir = resolve_fh6_cars_dir(game_folder)
    signature = _index_signature(cars_dir)
    cache = Path(cache_path) if cache_path else None
    if cache and cache.is_file():
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
            if payload.get("format") == "kfps_fh6_vehicle_asset_index_v1" and payload.get("signature") == signature:
                return {
                    int(key): VehicleAsset(**value)
                    for key, value in payload.get("vehicles", {}).items()
                }
        except (OSError, ValueError, TypeError):
            pass

    result = build_vehicle_asset_index(cars_dir)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(cache.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "format": "kfps_fh6_vehicle_asset_index_v1",
                    "signature": signature,
                    "vehicles": {str(key): asdict(value) for key, value in sorted(result.items())},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(cache)
    return result


def inspect_vehicle_archive(asset: VehicleAsset) -> dict[str, Any]:
    archive = Path(asset.archive_path)
    carbin_entries: list[str] = []
    model_entries: list[str] = []
    projection_entries: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            lower = name.casefold()
            if lower.endswith(".carbin"):
                carbin_entries.append(name)
            elif lower.endswith(".modelbin"):
                model_entries.append(name)
            if lower.startswith(PROJECTION_PREFIX.casefold()) and not name.endswith("/"):
                projection_entries.append(name)
    proxy = next((name for name in model_entries if name.casefold().endswith("scene/proxylod.modelbin")), "")
    return {
        **asset.public_metadata(),
        "archive_sha256": sha256_file(archive),
        "carbin_entries": carbin_entries,
        "model_entry_count": len(model_entries),
        "proxy_model_entry": proxy,
        "projection_entries": projection_entries,
    }


def read_projection_assets(asset: VehicleAsset) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(asset.archive_path) as bundle:
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            if name.casefold().startswith(PROJECTION_PREFIX.casefold()) and not name.endswith("/"):
                result[name] = bundle.read(info)
    return result


def read_projection_metadata(asset: VehicleAsset) -> dict[str, Any]:
    """Derive a portable projection contract without copying game assets."""
    inventory: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    with zipfile.ZipFile(asset.archive_path) as bundle:
        mask_xml = b""
        for info in bundle.infolist():
            name = info.filename.replace("\\", "/")
            if not name.casefold().startswith(PROJECTION_PREFIX.casefold()) or name.endswith("/"):
                continue
            data = bundle.read(info)
            inventory.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            if name.casefold() == "liverymasks/masks.xml":
                mask_xml = data
        if mask_xml:
            root = ET.fromstring(mask_xml)
            for element in root:
                record: dict[str, Any] = {"section": element.tag, "valid": element.attrib.get("valid", "false").lower() == "true"}
                for key in ("xorigin", "yorigin", "top", "bottom", "left", "right", "xScale", "yScale", "rotation"):
                    if key in element.attrib:
                        record[key] = float(element.attrib[key])
                for key in ("xAxis", "yAxis"):
                    if key in element.attrib:
                        record[key] = element.attrib[key]
                sections.append(record)
    return {
        "format": "kfps_vehicle_projection_map_v1",
        "model_code": asset.model_code,
        "source_inventory": sorted(inventory, key=lambda item: item["path"].casefold()),
        "sections": sections,
    }


def read_vehicle_assembly_metadata(asset: VehicleAsset) -> dict[str, Any]:
    """Read local-only inspection placement data from the car archive."""

    try:
        with zipfile.ZipFile(asset.archive_path) as bundle:
            available = {name.casefold(): name for name in bundle.namelist()}
            locator_name = available.get("locators.xml")
            if not locator_name:
                return {}
            locator_xml = bundle.read(locator_name).replace(
                b'BoneName="<root>"',
                b'BoneName="&lt;root&gt;"',
            )
            root = ET.fromstring(locator_xml)
    except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
        return {}

    wanted = {
        "carlocator_wheellf": "front_left",
        "carlocator_wheelrf": "front_right",
        "carlocator_wheellr": "rear_left",
        "carlocator_wheelrr": "rear_right",
    }
    centers: dict[str, list[float]] = {}
    for locator in root.findall(".//Locator"):
        name_element = locator.find("Name")
        transform = locator.find("SceneTransform")
        identity = str(name_element.attrib.get("value") if name_element is not None else "").casefold()
        label = wanted.get(identity)
        if not label or transform is None:
            continue
        try:
            position = [
                float(transform.attrib[f"value._{component}"])
                for component in (41, 42, 43)
            ]
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(value) for value in position):
            centers[label] = position
    if len(centers) != len(wanted):
        return {}

    front_z = (centers["front_left"][2] + centers["front_right"][2]) * 0.5
    rear_z = (centers["rear_left"][2] + centers["rear_right"][2]) * 0.5
    wheelbase = abs(front_z - rear_z)
    if wheelbase < 1.0 or wheelbase > 6.0:
        return {}

    # These dimensions are intentionally neutral inspection geometry. The car's
    # local locators provide exact placement; wheelbase-relative dimensions keep
    # the stand-ins proportionate without redistributing game tuning data.
    tire_radius = min(0.48, max(0.24, wheelbase * 0.12))
    tire_width = min(0.42, max(0.18, wheelbase * 0.095))
    return {
        "format": "kfps_fh6_local_vehicle_assembly_v1",
        "wheel_centers": centers,
        "wheelbase": wheelbase,
        "tire_radius": tire_radius,
        "tire_width": tire_width,
        "rim_radius": tire_radius * 0.70,
        "source": "local-car-locators",
        "style": "neutral-inspection-stand-in",
    }


def inspection_model_entries(asset: VehicleAsset) -> list[str]:
    """Resolve the stock, locally owned model parts needed by the inspector."""

    with zipfile.ZipFile(asset.archive_path) as bundle:
        available = {
            info.filename.replace("\\", "/").casefold(): info.filename.replace("\\", "/")
            for info in bundle.infolist()
            if info.filename.casefold().endswith(".modelbin")
        }
        try:
            manifest = ET.fromstring(bundle.read("Manifest.xml"))
        except KeyError as exc:
            raise VehicleAssetError(f"{asset.archive_name} has no Manifest.xml.") from exc

    prefix = f"game:/media/cars/{asset.model_code}/".casefold()
    entries: dict[str, str] = {}

    def add_model(model: ET.Element) -> None:
        source = str(model.attrib.get("path") or "").replace("\\", "/")
        folded = source.casefold()
        start = folded.find(prefix)
        if start < 0:
            return
        relative = source[start + len(prefix) :].lstrip("/")
        actual = available.get(relative.casefold())
        if not actual or "__slod" in actual.casefold():
            return
        identity = actual.casefold()
        include = (
            "/exterior/" in identity
            or "/scene/undercarriage/" in identity
            or "/interior/interiorlod/" in identity
        )
        if include:
            entries.setdefault(identity, actual)

    for model in manifest.findall(".//NonUpgradeablePart/Model"):
        add_model(model)

    # Stock aero parts are represented as the first/lowest PartId option in
    # each upgrade family rather than as NonUpgradeablePart records.
    stock_upgrades: dict[str, tuple[int, ET.Element]] = {}
    for part in manifest.findall(".//UpgradeablePart"):
        family = str(part.attrib.get("PartEnum") or "").casefold()
        if not family:
            continue
        try:
            part_id = int(part.attrib.get("PartId", ""))
        except ValueError:
            continue
        previous = stock_upgrades.get(family)
        if previous is None or part_id < previous[0]:
            stock_upgrades[family] = (part_id, part)
    for _, part in stock_upgrades.values():
        for model in part.findall(".//Model"):
            add_model(model)
    if not entries:
        raise VehicleAssetError(
            f"{asset.archive_name} does not expose stock inspection model parts in Manifest.xml."
        )

    def priority(name: str) -> tuple[int, str]:
        folded = name.casefold()
        if folded.endswith("/platform/body_a.modelbin"):
            return 0, folded
        if "/windows/" in folded:
            return 1, folded
        if any(token in folded for token in ("/hood/", "/doors/", "/trunk/", "/fenders/", "/bumper")):
            return 2, folded
        return 3, folded

    return sorted(entries.values(), key=priority)


def inspection_carbin_entry(asset: VehicleAsset) -> str:
    """Resolve the car scene that assembles the local chassis model instances."""

    with zipfile.ZipFile(asset.archive_path) as bundle:
        entries = [
            info.filename.replace("\\", "/")
            for info in bundle.infolist()
            if info.filename.casefold().endswith(".carbin") and not info.is_dir()
        ]
    if not entries:
        raise VehicleAssetError(f"{asset.archive_name} has no car scene.")
    expected = f"{asset.model_code}.carbin".casefold()
    exact = [entry for entry in entries if Path(entry).name.casefold() == expected]
    if len(exact) == 1:
        return exact[0]
    if len(entries) == 1:
        return entries[0]
    raise VehicleAssetError(f"{asset.archive_name} has an ambiguous car scene inventory.")
