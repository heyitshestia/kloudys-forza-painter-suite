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

__all__ = [
    "ADAPTERS",
    "COMMON_SCAN_REGIONS",
    "KNOWN_LIVERY_SIGNATURE",
    "GameAdapter",
    "GameCapabilities",
    "GameProfile",
    "LocatorStrategy",
    "OwnershipRules",
    "SaveDiscoveryStrategy",
    "ShapeSchemaCompatibility",
    "StoreVariant",
    "get_adapter",
    "get_adapter_or_default",
    "iter_adapters",
    "legacy_profiles",
]
