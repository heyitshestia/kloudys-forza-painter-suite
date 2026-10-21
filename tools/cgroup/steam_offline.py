"""Additive FH4/FH5 Steam vinyl files. Never edit profiles or Steam metadata."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Callable

from .cgroup_codec import wrap_payload
from .forza_source_decoder import cgroup_to_layers, decode_forza_source
from .horizon_vinyl_header import HorizonVinylHeader, build_vinyl_header, parse_vinyl_header


APP_IDS = {"fh4": "1293830", "fh5": "1551360"}
HEADER_NAME = re.compile(r"LayerGroup_0000_(\d{14})\.header", re.IGNORECASE)
MAX_FILE_BYTES = 2 * 1024**3
MAX_ACCOUNT_BYTES = 8 * 1024**3


class SteamSaveChangedError(RuntimeError):
    pass


class SteamRecoveryRequiredError(RuntimeError):
    pass


def _plain_path(path: Path) -> None:
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("Linked Steam save or backup paths are unsupported")
    if path.is_file() and path.stat().st_nlink != 1:
        raise ValueError("Hard-linked Steam save files are unsupported")


def _read(path: Path, limit: int) -> bytes:
    _plain_path(path)
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Steam vinyl file exceeds its size limit: {path.name}")
    return data


def _digest(path: Path) -> str:
    _plain_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png(data: bytes) -> None:
    from PIL import Image

    if len(data) > 4 * 1024**2:
        raise ValueError("Steam vinyl thumbnail exceeds 4 MiB")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or image.size != (256, 256):
                raise ValueError("Steam vinyl thumbnail must be a 256x256 PNG")
            image.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Steam vinyl thumbnail is not a valid PNG") from exc


@dataclass(frozen=True)
class SteamVinylTarget:
    game: str
    account: Path
    header_path: Path
    header: HorizonVinylHeader
    evidence: tuple[tuple[Path, str], ...]

    def revalidate(self) -> None:
        _plain_path(self.account)
        for path, digest in self.evidence:
            if _digest(path) != digest:
                raise SteamSaveChangedError("The selected Steam template changed; select it again")


def inspect_steam_target(header_path: Path | str, game: str) -> SteamVinylTarget:
    """Select one owned, unlocked draft. Never infer an account from recency."""
    if game not in APP_IDS:
        raise ValueError("Steam offline writing is limited to FH4 and FH5")
    selected = Path(header_path)
    _plain_path(selected)
    selected = selected.resolve(strict=True)
    account = selected.parent
    match = HEADER_NAME.fullmatch(selected.name)
    if not match:
        raise ValueError("Select an owned LayerGroup_0000_<timestamp>.header file")
    datetime.strptime(match[1], "%Y%m%d%H%M%S")
    remote = account.parent
    app, user, userdata = remote.parent, remote.parent.parent, remote.parent.parent.parent
    if (not re.fullmatch(r"[0-9]{1,20}", account.name) or not int(account.name)
            or remote.name.casefold() != "remote" or app.name != APP_IDS[game]
            or not re.fullmatch(r"[0-9]{1,20}", user.name)
            or userdata.name.casefold() != "userdata"):
        raise ValueError(f"Choose a {game.upper()} Steam vinyl inside userdata/<user>/{APP_IDS[game]}/remote/<account>")
    cgroup = selected.with_suffix(".C_group")
    thumb = selected.with_suffix(".thumb.png")
    raw = (
        (selected, _read(selected, 65536)),
        (cgroup, _read(cgroup, 64 * 1024**2)),
        (thumb, _read(thumb, 4 * 1024**2)),
    )
    header = parse_vinyl_header(raw[0][1], game)
    if header.creator_id != int(account.name):
        raise ValueError("The selected vinyl does not belong to this Steam save account")
    _png(raw[2][1])
    decoded = decode_forza_source(cgroup, allow_locked=False, game=game)
    if len(decoded.layers) != header.layer_count or decoded.report.get("warnings"):
        raise ValueError("Steam template header and decoded layer count must agree without warnings")
    target = SteamVinylTarget(
        game, account, selected, header,
        tuple((path, hashlib.sha256(data).hexdigest()) for path, data in raw),
    )
    target.revalidate()
    return target


def _snapshot(account: Path, *, exclude: tuple[Path, ...] = ()) -> dict[str, tuple[int, str]]:
    _plain_path(account)
    result = {}
    total = 0
    for path in sorted(account.iterdir()):
        if path in exclude:
            continue
        _plain_path(path)
        if not path.is_file():
            raise ValueError("Unsupported nested directory in this flat Steam save account")
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_ACCOUNT_BYTES or len(result) >= 50000:
            raise ValueError("Steam account exceeds the safe backup limits")
        result[path.name] = (size, _digest(path))
    return result


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _new_stem(account: Path, now: datetime) -> tuple[str, datetime]:
    # Every sibling reserves a timestamp, including an incomplete earlier import.
    occupied = {p.name.split(".", 1)[0].casefold() for p in account.iterdir()}
    for seconds in range(86400):
        date = now + timedelta(seconds=seconds)
        stem = "LayerGroup_0000_" + date.strftime("%Y%m%d%H%M%S")
        if stem.casefold() not in occupied:
            return stem, date
    raise ValueError("No free Steam vinyl timestamp was found")


@dataclass(frozen=True)
class SteamImportResult:
    cgroup_path: Path
    header_path: Path
    thumbnail_path: Path
    backup_path: Path


def create_steam_layer_group(
    target: SteamVinylTarget, *, payload: bytes, title: str, thumbnail_data: bytes,
    expected_layers: int, backup_root: Path | str, check_ready: Callable[[], None],
    now: datetime | None = None,
) -> SteamImportResult:
    """Back up, stage, verify, then add three files without overwriting anything.

    check_ready must reject a running game/Steam client. Cancellation is honored
    until publication begins. A power loss can leave partial new files; the
    backup transaction manifest identifies them. No multi-file atomicity is claimed.
    """
    if os.name != "nt":
        raise ValueError("Steam save writing is supported on Windows only")
    if not callable(check_ready):
        raise TypeError("An explicit game/Steam-closed readiness check is required")
    check_ready()
    if inspect_steam_target(target.header_path, target.game) != target:
        raise SteamSaveChangedError("The selected Steam destination changed")
    if (len(payload) < 0x24 or len(payload) > 64 * 1024**2 or payload[:8] != b"gyvl\x01\x00\x00\x00"
            or payload[0x1D] not in (0x20, 0x60)):
        raise ValueError("Steam import requires a supported, unlocked vinyl payload")
    layers, report = cgroup_to_layers(payload, game=target.game)
    if (not 1 <= expected_layers <= 3000 or len(layers) != expected_layers
            or report.get("warnings") or report.get("max_group_depth", 0) > 64):
        raise ValueError("Steam payload failed layer-count or hierarchy validation")
    _png(thumbnail_data)
    root = Path(backup_root)
    _plain_path(root)
    root = root.resolve()
    if root == target.account or target.account in root.parents:
        raise ValueError("Safety backups must be outside the Steam save account")
    before = _snapshot(target.account)
    now = now or datetime.now()
    stem, date = _new_stem(target.account, now)
    header_data = build_vinyl_header(target.header, title, expected_layers, target.game, now=date)
    files = {
        stem + ".thumb.png": thumbnail_data,
        stem + ".C_group": wrap_payload(payload),
        stem + ".header": header_data,
    }
    backup = root / (now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12])
    original = backup / "account"
    original.mkdir(parents=True, exist_ok=False)
    for name in before:
        check_ready()
        shutil.copy2(target.account / name, original / name)
    if _snapshot(original) != before or _snapshot(target.account) != before:
        raise SteamSaveChangedError(f"Steam save changed during backup. Safety backup: {backup}")
    manifest = {
        "format": "kfps_steam_vinyl_transaction_v1", "game": target.game,
        "phase": "prepared", "account": str(target.account),
        "original_files": before,
        "new_files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    _write(backup / "transaction.json", json.dumps(manifest, indent=2).encode("utf-8"))
    check_ready()
    stage = target.account / (".kfps-stage-" + uuid.uuid4().hex)
    stage.mkdir()
    published = []

    def verify(folder: Path) -> None:
        for name, data in files.items():
            if _read(folder / name, len(data)) != data:
                raise ValueError(f"Steam import readback failed: {name}")
        decoded = decode_forza_source(folder / (stem + ".C_group"), allow_locked=False, game=target.game)
        if len(decoded.layers) != expected_layers or decoded.report.get("warnings"):
            raise ValueError("Steam import failed independent reopen verification")
        if parse_vinyl_header((folder / (stem + ".header")).read_bytes(), target.game).layer_count != expected_layers:
            raise ValueError("Steam imported header count is inconsistent")

    try:
        for name, data in files.items():
            _write(stage / name, data)
        verify(stage)
        check_ready()
        target.revalidate()
        if _snapshot(target.account, exclude=(stage,)) != before:
            raise SteamSaveChangedError("Steam account changed before publishing new files")
        # Windows rename refuses an existing destination. Header is published last.
        for name in files:
            destination = target.account / name
            os.rename(stage / name, destination)
            published.append(destination)
        verify(target.account)
        if _snapshot(target.account, exclude=(stage, *published)) != before:
            raise SteamSaveChangedError("Steam account changed during publication")
        _write(backup / "committed.json", json.dumps({"new_files": list(files)}).encode("utf-8"))
    except BaseException as exc:
        retained = []
        for path in reversed(published):
            try:
                if not path.exists():
                    continue
                if _read(path, len(files[path.name])) != files[path.name]:
                    retained.append(path.name)
                else:
                    path.unlink()
            except (OSError, ValueError):
                retained.append(path.name)
        if retained:
            raise SteamRecoveryRequiredError(
                f"New files changed during rollback and were preserved: {', '.join(retained)}. Safety backup: {backup}"
            ) from exc
        raise
    finally:
        # Delete only our bounded staging files; never recursively clean save paths.
        cleanup_failed = False
        for name in files:
            path = stage / name
            try:
                if path.exists() or path.is_symlink():
                    if _read(path, len(files[name])) != files[name]:
                        cleanup_failed = True
                    else:
                        path.unlink()
            except (OSError, ValueError):
                cleanup_failed = True
        try:
            stage.rmdir()
        except OSError:
            cleanup_failed = True
        if cleanup_failed:
            raise SteamRecoveryRequiredError(
                f"Staging cleanup could not be verified; retained files at {stage}. Safety backup: {backup}"
            )
    return SteamImportResult(
        target.account / (stem + ".C_group"), target.account / (stem + ".header"),
        target.account / (stem + ".thumb.png"), backup,
    )
