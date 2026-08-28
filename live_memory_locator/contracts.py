from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


ENGINE_VERSION = "1.1.0"
DIAGNOSTIC_SCHEMA = "kfps_live_memory_locator_v1"
CACHE_SCHEMA = "kfps_live_memory_locator_cache_v1"
REPORT_INDEX_SCHEMA = "kfps_live_memory_locator_report_index_v1"

VALID_PURPOSES = frozenset(("import", "export", "diagnostic"))


def parse_address(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not a memory address")
    if isinstance(value, int):
        result = value
    else:
        result = int(str(value or "").strip(), 0)
    if result < 0x10000 or result >= 0x800000000000:
        raise ValueError(f"invalid user-space address: {value!r}")
    return result


def address_text(value: int | None) -> str:
    return f"0x{int(value):x}" if value else ""


@dataclass(frozen=True)
class LocatorRequest:
    game: str
    pid: int
    layer_count: int
    purpose: str
    output_path: Path
    limit_mb: int = 2048
    max_matches: int = 500000
    inspect_radius: int = 0x800
    fast_seconds: int = 45
    research_seconds: int = 90
    report_layers: int = 40

    def __post_init__(self) -> None:
        game = str(self.game or "").strip().lower()
        purpose = str(self.purpose or "").strip().lower().replace("-template", "")
        if purpose not in VALID_PURPOSES:
            raise ValueError(f"unsupported locator purpose: {self.purpose!r}")
        if int(self.pid) <= 0:
            raise ValueError("locator pid must be greater than zero")
        if not 0 < int(self.layer_count) <= 3000:
            raise ValueError("locator layer count must be between 1 and 3000")
        if int(self.limit_mb) <= 0 or int(self.max_matches) <= 0:
            raise ValueError("locator scan limits must be greater than zero")
        object.__setattr__(self, "game", game)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "output_path", Path(self.output_path).resolve())

    def as_dict(self) -> dict[str, Any]:
        return {
            "game": self.game,
            "pid": int(self.pid),
            "layer_count": int(self.layer_count),
            "purpose": self.purpose,
            "limits": {
                "memory_mb": int(self.limit_mb),
                "raw_matches": int(self.max_matches),
                "inspect_radius": int(self.inspect_radius),
                "fast_seconds": int(self.fast_seconds),
                "research_seconds": int(self.research_seconds),
                "report_layers": int(self.report_layers),
            },
        }


@dataclass(frozen=True)
class LocatorSelection:
    group_address: int
    table_address: int
    count_address: int | None
    table_pointer_field: int | None
    locator: str
    validated_entries: int
    vector_count: int | None = None
    capacity_count: int | None = None
    import_group_address: int | None = None
    import_count_address: int | None = None
    import_table_pointer_field: int | None = None
    import_table_address: int | None = None
    import_vector_count: int | None = None
    import_capacity_count: int | None = None
    import_target_verified: bool = False
    export_access_verified: bool = False
    flattened_from_groups: bool = False
    details: Mapping[str, Any] | None = None

    def addresses_for(self, purpose: str) -> tuple[int, int]:
        if purpose == "import":
            if not self.import_target_verified or not self.import_group_address or not self.import_table_address:
                raise ValueError("locator did not verify a single writable import table")
            return int(self.import_group_address), int(self.import_table_address)
        return int(self.group_address), int(self.table_address)

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_address": self.group_address,
            "table_address": self.table_address,
            "count_address": self.count_address,
            "table_pointer_field": self.table_pointer_field,
            "locator": self.locator,
            "validated_entries": self.validated_entries,
            "vector_count": self.vector_count,
            "capacity_count": self.capacity_count,
            "import_group_address": self.import_group_address,
            "import_count_address": self.import_count_address,
            "import_table_pointer_field": self.import_table_pointer_field,
            "import_table_address": self.import_table_address,
            "import_vector_count": self.import_vector_count,
            "import_capacity_count": self.import_capacity_count,
            "import_target_verified": self.import_target_verified,
            "export_access_verified": self.export_access_verified,
            "flattened_from_groups": self.flattened_from_groups,
            "details": dict(self.details or {}),
        }
