from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from fh6_rtti_registry import (  # noqa: E402
    DEFAULT_RELAY_REMOTE_URL,
    MAX_PROFILES,
    RegistryError,
    download_registry,
    load_registry_file,
    normalize_registry,
    write_registry_file,
)


class SyncError(RuntimeError):
    pass


def _timestamp(value: str, label: str) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SyncError(f"{label} updated_utc is invalid") from exc
    if parsed.tzinfo is None:
        raise SyncError(f"{label} updated_utc must include a timezone")
    return parsed


def build_synced_registry(local_registry: Any, relay_registry: Any) -> tuple[dict[str, Any], bool]:
    local = normalize_registry(local_registry)
    relay = normalize_registry(relay_registry)
    if not relay["profiles"]:
        raise SyncError("the relay registry is empty")

    if relay["profiles"] == local["profiles"]:
        return local, False

    if _timestamp(relay["updated_utc"], "relay") < _timestamp(local["updated_utc"], "local"):
        raise SyncError("the relay registry is older than the checked-in registry")

    merged_profiles = list(relay["profiles"])
    seen = {profile["profile_id"] for profile in merged_profiles}
    for profile in local["profiles"]:
        if profile["profile_id"] not in seen:
            merged_profiles.append(profile)
            seen.add(profile["profile_id"])

    merged = normalize_registry(
        {
            "format": relay["format"],
            "updated_utc": relay["updated_utc"],
            "profiles": merged_profiles[:MAX_PROFILES],
        }
    )
    return merged, merged["profiles"] != local["profiles"]


def sync_registry(
    source_url: str,
    target_path: Path,
    *,
    dry_run: bool = False,
    downloader: Callable[[str], dict[str, Any]] = download_registry,
) -> dict[str, Any]:
    target = Path(target_path)
    if not target.is_file():
        raise SyncError(f"the checked-in registry does not exist: {target}")

    before = target.read_bytes()
    try:
        local = load_registry_file(target)
        relay = downloader(source_url)
        merged, changed = build_synced_registry(local, relay)
    except (OSError, RegistryError) as exc:
        raise SyncError(str(exc)) from exc

    if changed and not dry_run:
        write_registry_file(target, merged)

    newest = merged["profiles"][0]
    return {
        "changed": changed,
        "dry_run": dry_run,
        "profile_count": len(merged["profiles"]),
        "newest_profile_id": newest["profile_id"],
        "newest_game_build": newest["game_build"],
        "target_untouched": dry_run and target.read_bytes() == before,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and mirror the canonical FH6 RTTI relay registry into GitHub's fallback RTTI.dat."
    )
    parser.add_argument("--source-url", default=DEFAULT_RELAY_REMOTE_URL)
    parser.add_argument("--target", type=Path, default=REPOSITORY_ROOT / "RTTI.dat")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report without changing RTTI.dat.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = sync_registry(args.source_url, args.target, dry_run=args.dry_run)
    except SyncError as exc:
        print(f"RTTI registry sync failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
