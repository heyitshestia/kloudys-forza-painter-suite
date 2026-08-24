from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class GameProfile:
    """Memory layout data consumed by the live transfer tools."""

    key: str
    label: str
    process_names: Tuple[str, ...]
    signature_patterns: Tuple[bytes, ...]
    scan_regions: Tuple[Tuple[int, int], ...]
    validation_mirror_offset: int = 0x70
    livery_root_pointer_offset: int = 0xB8
    editor_pointer_offset: int = 0xA58
    livery_pointer_offset: int = 0x8
    livery_group_offset: int = 0x20
    livery_count_offset: int = 0x5A
    layer_table_offset: int = 0x78
    layer_position_offset: int = 0x18
    layer_scale_offset: int = 0x28
    layer_rotation_offset: int = 0x50
    layer_color_offset: int = 0x74
    layer_mask_offset: int = 0x78
    layer_shape_id_offset: int = 0x7A
    static_module_size: int = 0
    static_rtti_descriptor_offset: int = 0
    static_rtti_vtable_offsets: Tuple[int, ...] = ()
    static_rtti_descriptor_name: bytes = b".?AVCLiveryGroup@@"
    static_build: str = ""
    fixed_rtti_descriptor_names: Tuple[bytes, ...] = ()
    import_template_shape_word: int = -1
    import_template_min_ratio: float = 0.0


@dataclass(frozen=True)
class GameCapabilities:
    live_import: bool
    live_export: bool
    offline_import: bool
    offline_export: bool

    def supports(self, operation: str) -> bool:
        key = str(operation or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "online_import": "live_import",
            "online_export": "live_export",
            "save_import": "offline_import",
            "save_export": "offline_export",
            "save_scan": "offline_export",
            "library_scan": "offline_export",
        }
        return bool(getattr(self, aliases.get(key, key), False))


@dataclass(frozen=True)
class StoreVariant:
    key: str
    label: str
    save_family: str


@dataclass(frozen=True)
class OwnershipRules:
    live_export_policy: str
    live_import_policy: str
    offline_export_policy: str
    offline_import_policy: str
    offline_source_preflight: str = "decoder"


@dataclass(frozen=True)
class SaveDiscoveryStrategy:
    key: str
    targeted_kind: str
    walk_kind: str
    include_xbox_game_save: bool = False
    local_ugc_relative: Tuple[str, ...] = ()
    package_tokens: Tuple[str, ...] = ()
    package_markers: Tuple[str, ...] = ()
    package_globs: Tuple[str, ...] = ()
    steam_app_id: str = ""
    unbounded_matching_walk: bool = False
    ignored_design_kind: str = ""


@dataclass(frozen=True)
class LocatorStrategy:
    key: str
    profile_source: str
    allow_research_fallback: bool
    require_live_export_ownership: bool
    require_single_import_table: bool = True


@dataclass(frozen=True)
class ShapeSchemaCompatibility:
    canonical_game: str
    json_schema: str
    accepted_source_kinds: Tuple[str, ...] = ()
    minimum_decoded_layers: int = 0
    preserves_group_transforms: bool = True
    cross_game_native_shapes: bool = True

    def accepts_decoded_source(self, source_kind: str, layer_count: int) -> bool:
        if self.minimum_decoded_layers and int(layer_count) < self.minimum_decoded_layers:
            return False
        return not self.accepted_source_kinds or str(source_kind).lower() in self.accepted_source_kinds


@dataclass(frozen=True)
class GameAdapter:
    key: str
    bridge_key: str
    label: str
    short_label: str
    aliases: Tuple[str, ...]
    capabilities: GameCapabilities
    stores: Tuple[StoreVariant, ...]
    ownership: OwnershipRules
    save_discovery: SaveDiscoveryStrategy
    locator: LocatorStrategy
    shape_schema: ShapeSchemaCompatibility
    memory_profile: GameProfile
    offline_import_handler: str
    scan_notice: str
    offline_import_summary: str
    offline_import_help: str

    def supports(self, operation: str) -> bool:
        return self.capabilities.supports(operation)

    def accepts_decoded_source(self, source_kind: str, layer_count: int) -> bool:
        return self.shape_schema.accepts_decoded_source(source_kind, layer_count)

    def matches_alias(self, value: str) -> bool:
        normalized = str(value or "").strip().casefold()
        aliases = (self.key, self.bridge_key, *self.aliases)
        return normalized in {item.casefold() for item in aliases}

    @property
    def process_names(self) -> Tuple[str, ...]:
        return self.memory_profile.process_names

    def is_save_root(self, path: Path) -> bool:
        strategy = self.save_discovery
        if not strategy.package_tokens and not strategy.steam_app_id:
            return True
        text = str(path).replace("\\", "/").casefold()
        if any(token.casefold() in text for token in strategy.package_tokens):
            return True
        app_id = strategy.steam_app_id
        return bool(app_id and (f"/{app_id}/" in text or text.endswith(f"/{app_id}/remote")))

    def is_library_artifact(self, source_path: Path, source_folder: str, source_kind: str) -> bool:
        target_kind = self.save_discovery.targeted_kind
        if target_kind == "fm8_layer_groups":
            return (
                source_path.name.casefold() == "data"
                and source_path.parent.parent.name.casefold() == "layergroups"
            )
        if target_kind == "fh4_wgs_layer_groups" or self.save_discovery.walk_kind == "cgroup":
            return str(source_kind).casefold() == "cgroup"
        return source_path.name.casefold() == "c_group" and str(source_folder).startswith("LayerGroup_")
