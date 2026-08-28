from .contracts import (
    GameAdapter,
    GameCapabilities,
    GameProfile,
    LocatorStrategy,
    OwnershipRules,
    SaveDiscoveryStrategy,
    ShapeSchemaCompatibility,
    StoreVariant,
)
from .registry import (
    ADAPTERS,
    COMMON_SCAN_REGIONS,
    KNOWN_LIVERY_SIGNATURE,
    get_adapter,
    get_adapter_or_default,
    iter_adapters,
    legacy_profiles,
)
from .live_processes import (
    LiveGameDetectionError,
    RunningGameProcess,
    detect_single_running_game,
    find_running_supported_games,
)

__all__ = [
    "ADAPTERS",
    "COMMON_SCAN_REGIONS",
    "KNOWN_LIVERY_SIGNATURE",
    "LiveGameDetectionError",
    "GameAdapter",
    "GameCapabilities",
    "GameProfile",
    "LocatorStrategy",
    "OwnershipRules",
    "RunningGameProcess",
    "SaveDiscoveryStrategy",
    "ShapeSchemaCompatibility",
    "StoreVariant",
    "get_adapter",
    "get_adapter_or_default",
    "detect_single_running_game",
    "find_running_supported_games",
    "iter_adapters",
    "legacy_profiles",
]
