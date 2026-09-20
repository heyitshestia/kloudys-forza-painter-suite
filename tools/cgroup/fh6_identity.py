"""Verified FH6 save destinations and fresh, unpublished vinyl headers.

This is the LayerGroup v7 layout, not the full-car livery header layout.
Never derive the local account from the most recently modified artwork.
"""
from __future__ import annotations

import json
import os
import re
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


GAME_ID = "16D460"
ACCOUNT_NAME = re.compile(r"u_([0-9]+)_16D460", re.IGNORECASE)
USER_NAME = re.compile(r"User_([0-9a-f]+)", re.IGNORECASE)
SAVE_ONE = "Save one small vinyl group in FH6 with this account, wait for saving to finish, then retry."


class FH6IdentityError(ValueError):
    pass


class FH6CreatorNameNotFound(FH6IdentityError):
    """The account is verified, but no usable vinyl creator name exists."""


class FH6DestinationChoiceRequired(FH6IdentityError):
    pass


@dataclass(frozen=True)
class VinylHeader:
    title: str
    description: str
    created: datetime
    creator_id: int
    creator: str
    layer_count: int
    asset_id: bytes
    tail: bytes


@dataclass(frozen=True)
class SaveAccount:
    directory: Path
    containers: Path
    user_id: int
    manifest: bytes

    def revalidate(self) -> None:
        if read_account(self.directory) != self:
            raise FH6IdentityError("FH6 changed the active save while importing. Close FH6 and retry.")


@dataclass(frozen=True)
class CreatorIdentity:
    account: SaveAccount
    name: str
    evidence: Path
    header_bytes: bytes

    def revalidate(self) -> None:
        self.account.revalidate()
        if _read_bounded(self.evidence, 65536) != self.header_bytes:
            raise FH6IdentityError("The FH6 creator header changed while importing. Close FH6 and retry.")


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise FH6IdentityError("FH6 save metadata exceeds its supported size.")
    return data


def parse_vinyl_header(data: bytes) -> VinylHeader:
    if len(data) > 65536 or len(data) < 4 or struct.unpack_from("<I", data)[0] != 7:
        raise FH6IdentityError("Unsupported FH6 vinyl header (expected version 7).")
    offset = 4

    def string() -> str:
        nonlocal offset
        if offset + 4 > len(data):
            raise FH6IdentityError("Truncated FH6 header string.")
        units = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        end = offset + units * 2
        if units > 4096 or end > len(data):
            raise FH6IdentityError("Invalid FH6 header string length.")
        try:
            value = data[offset:end].decode("utf-16le")
        except UnicodeError as exc:
            raise FH6IdentityError("Invalid FH6 header text.") from exc
        offset = end
        if any(ord(c) < 32 for c in value):
            raise FH6IdentityError("Invalid control character in FH6 header text.")
        return value

    title, description = string(), string()
    if offset + 28 > len(data):
        raise FH6IdentityError("Truncated FH6 header identity.")
    year, month, weekday, day, hour, minute, second, millis, flag = struct.unpack_from("<8HI", data, offset)
    try:
        created = datetime(year, month, day, hour, minute, second, millis * 1000)
    except ValueError as exc:
        raise FH6IdentityError("Invalid FH6 header creation date.") from exc
    if weekday > 6 or flag != 2:
        raise FH6IdentityError("Unsupported FH6 header metadata.")
    creator_id = struct.unpack_from("<Q", data, offset + 20)[0]
    offset += 28
    creator = string()
    tail = data[offset:]
    if len(tail) < 57 or tail[28:30] not in (b"\x01\x02", b"\x00\x02"):
        raise FH6IdentityError("Unsupported FH6 vinyl header tail.")
    count = struct.unpack_from("<I", tail, 37)[0]
    if count > 3000:
        raise FH6IdentityError("Invalid FH6 vinyl header shape count.")
    return VinylHeader(title, description, created, creator_id, creator, count, tail[41:57], tail)


def build_vinyl_header(title: str, creator_id: int, creator: str, layer_count: int,
                       *, asset_id: bytes | None = None, now: datetime | None = None) -> bytes:
    if not 0 < creator_id < 2**64 or not creator.strip() or creator.strip().casefold() == "kfps":
        raise FH6IdentityError("A verified FH6 account name and ID are required. " + SAVE_ONE)
    if any(ord(c) < 32 for c in creator) or len(creator.encode("utf-16le")) > 512:
        raise FH6IdentityError("Invalid FH6 creator name.")
    if not 1 <= layer_count <= 3000:
        raise FH6IdentityError("FH6 vinyl imports must contain between 1 and 3000 shapes.")
    title = " ".join(title.split()) or "KFPS Import"
    title = title.encode("utf-16le")[:128].decode("utf-16le", errors="ignore")
    asset_id = uuid.uuid4().bytes_le if asset_id is None else asset_id
    if len(asset_id) != 16 or asset_id == bytes(16):
        raise FH6IdentityError("Invalid FH6 vinyl ID.")
    now = now or datetime.now()

    def string(value: str) -> bytes:
        encoded = value.encode("utf-16le")
        return struct.pack("<I", len(encoded) // 2) + encoded

    result = (
        struct.pack("<I", 7) + string(title) + string("")
        + struct.pack("<8HIQ", now.year, now.month, (now.weekday() + 1) % 7,
                      now.day, now.hour, now.minute, now.second, now.microsecond // 1000,
                      2, creator_id)
        + string(creator) + bytes(28) + b"\x01\x02" + bytes(7)
        + struct.pack("<I", layer_count) + asset_id
    )
    parse_vinyl_header(result)
    return result


def read_account(directory: Path) -> SaveAccount:
    directory = directory.resolve(strict=True)
    match = ACCOUNT_NAME.fullmatch(directory.name)
    if not match or not 0 < int(match[1]) < 2**64:
        raise FH6IdentityError("Choose an FH6 account save folder, current folder, or ContainersRoot.")
    user_id = int(match[1])
    version = (directory / "current").resolve(strict=True)
    if version.parent != directory or not version.name.isdecimal():
        raise FH6IdentityError("The FH6 current save does not point to a supported version folder.")
    containers = (version / "ContainersRoot").resolve(strict=True)
    if containers.parent != version or not containers.is_dir():
        raise FH6IdentityError("FH6 ContainersRoot could not be verified.")
    manifest_path = directory / (version.name + ".json")
    if manifest_path.resolve(strict=True).parent != directory:
        raise FH6IdentityError("FH6 manifest is outside the account save folder.")
    manifest = _read_bounded(manifest_path, 8 * 1024 * 1024)
    try:
        content = json.loads(manifest)["Manifest"]
        valid = (int(content["UserId"]) == user_id and str(content["GameId"]).upper() == GAME_ID
                 and int(content["Version"]) == int(version.name))
    except (ValueError, TypeError, KeyError) as exc:
        raise FH6IdentityError("FH6 account manifest is missing or invalid.") from exc
    users = {int(m[1], 16) for child in containers.iterdir()
             if child.is_dir() and (m := USER_NAME.fullmatch(child.name))
             and child.resolve().parent == containers}
    if not valid or users != {user_id}:
        raise FH6IdentityError("FH6 account, save version, manifest, and user profile disagree. No files were written.")
    return SaveAccount(directory, containers, user_id, manifest)


def account_from_selection(path: Path) -> SaveAccount:
    resolved = path.resolve(strict=True)
    directory = next((p for p in (resolved, *resolved.parents) if ACCOUNT_NAME.fullmatch(p.name)), None)
    if directory is None:
        raise FH6IdentityError("Select this account's FH6 save root, current folder, or ContainersRoot.")
    account = read_account(directory)
    if resolved not in (directory, account.containers.parent, account.containers):
        raise FH6IdentityError("Choose the current FH6 save, not an older version or an individual vinyl.")
    return account


def _pointer_accounts(local_app_data: Path) -> tuple[dict[Path, SaveAccount], bool]:
    bases = (local_app_data / "ForzaHorizon6", local_app_data / "Packages"
             / "Microsoft.ForteBaseGame_8wekyb3d8bbwe" / "LocalCache" / "Local")
    found: dict[Path, SaveAccount] = {}
    invalid = False
    for base in bases:
        for pointer in base.glob("SaveFolderMetadata_*/LastSaveFolderLocation"):
            try:
                profile_id = int(pointer.parent.name.removeprefix("SaveFolderMetadata_"), 16)
                selected = Path(_read_bounded(pointer, 4096).decode("utf-8-sig").strip().rstrip("\x00"))
                if not selected.is_absolute():
                    raise FH6IdentityError("Invalid last-save location.")
                account = account_from_selection(selected)
                if account.user_id != profile_id:
                    raise FH6IdentityError("Last-save profile ID does not match the save.")
                found[account.containers] = account
            except (OSError, ValueError):
                invalid = True
    return found, invalid


def select_account(roots: Iterable[Path], *, destination: Path | None = None,
                   local_app_data: Path | None = None,
                   use_saved_locations: bool = True) -> SaveAccount:
    if destination is not None:
        return account_from_selection(destination)
    if use_saved_locations and local_app_data is None:
        value = os.environ.get("LOCALAPPDATA")
        local_app_data = Path(value) if value else None
    if use_saved_locations and local_app_data is not None:
        pointers, invalid = _pointer_accounts(local_app_data)
        if invalid or len(pointers) > 1:
            raise FH6DestinationChoiceRequired(
                "FH6 last-save locations are ambiguous or outdated. Choose the active account's current save folder."
            )
        if pointers:
            return next(iter(pointers.values()))
    candidates: dict[Path, SaveAccount] = {}
    for root in roots:
        root = Path(root)
        directories = [root, *root.parents]
        directories.extend(root.glob("u_*_16D460"))
        directories.extend((root / "pgs").glob("u_*_16D460"))
        for directory in directories:
            if not ACCOUNT_NAME.fullmatch(directory.name):
                continue
            try:
                account = read_account(directory)
                candidates[account.containers] = account
            except (OSError, ValueError):
                # An unverified account must not silently redirect an import to another one.
                raise FH6DestinationChoiceRequired(
                    "An FH6 save account could not be verified. Choose the active account's current save folder."
                )
    if len(candidates) != 1:
        raise FH6DestinationChoiceRequired(
            "Choose the active account's FH6 current save folder; no single verified destination was found."
        )
    return next(iter(candidates.values()))


def resolve_creator(account: SaveAccount) -> CreatorIdentity:
    matches: list[tuple[datetime, str, Path, bytes]] = []
    for path in account.containers.glob("LayerGroup_*/header"):
        try:
            if path.parent.resolve().parent != account.containers or path.resolve().parent != path.parent.resolve():
                continue
            raw = _read_bounded(path, 65536)
            header = parse_vinyl_header(raw)
            if (header.creator_id == account.user_id and header.creator.strip()
                    and header.creator.strip().casefold() != "kfps"
                    and header.asset_id != bytes(16) and 0 < header.layer_count <= 3000):
                matches.append((header.created, header.creator, path, raw))
        except (OSError, ValueError):
            continue
    if not matches:
        raise FH6CreatorNameNotFound("No verified local FH6 creator name was found. " + SAVE_ONE)
    newest = max(item[0] for item in matches)
    latest = [item for item in matches if item[0] == newest]
    if len({item[1] for item in latest}) != 1:
        raise FH6IdentityError("Conflicting FH6 creator names were found. " + SAVE_ONE)
    _, name, path, raw = latest[0]
    return CreatorIdentity(account, name, path, raw)
