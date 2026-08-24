"""Compatibility facade for legacy memory-tool imports.

New code should use :mod:`game_adapters`. Existing scripts deliberately keep the
historic ``PROFILES`` surface so standalone and bundled launch paths remain stable.
"""

from typing import Dict, Iterable

from game_adapters import (
    COMMON_SCAN_REGIONS,
    KNOWN_LIVERY_SIGNATURE,
    GameProfile,
    get_adapter,
    legacy_profiles,
)


PROFILES: Dict[str, GameProfile] = legacy_profiles()


def get_profile(key: str) -> GameProfile:
    adapter = get_adapter(key)
    return PROFILES[adapter.bridge_key]


def iter_profiles(preferred_key: str = None) -> Iterable[GameProfile]:
    if preferred_key:
        yield get_profile(preferred_key)
        return
    yield from PROFILES.values()


__all__ = [
    "COMMON_SCAN_REGIONS",
    "KNOWN_LIVERY_SIGNATURE",
    "GameProfile",
    "PROFILES",
    "get_profile",
    "iter_profiles",
]
