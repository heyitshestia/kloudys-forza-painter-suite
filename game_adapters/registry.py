from __future__ import annotations

from typing import Dict, Iterable

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


KNOWN_LIVERY_SIGNATURE = b"\x12\x47\x9B\x13\x29\xD9\xA2\xB1"
COMMON_SCAN_REGIONS = (
    (0x06000000, 0x02000000),
    (0x08000000, 0x02000000),
    (0x0A000000, 0x02000000),
)

MICROSOFT_STORE = StoreVariant("microsoft", "Microsoft Store / Xbox", "xbox")
STEAM = StoreVariant("steam", "Steam", "steam")

FAIL_CLOSED_OWNERSHIP = OwnershipRules(
    live_export_policy="verified_complete_group",
    live_import_policy="verified_owned_template",
    offline_export_policy="decoder_rejects_non_owned",
    offline_import_policy="new_local_record_only",
)


def _profile(key: str, label: str, process_names: tuple[str, ...], **kwargs) -> GameProfile:
    return GameProfile(
        key=key,
        label=label,
        process_names=process_names,
        signature_patterns=(KNOWN_LIVERY_SIGNATURE,),
        scan_regions=COMMON_SCAN_REGIONS,
        **kwargs,
    )


ADAPTERS: Dict[str, GameAdapter] = {
    "fh6": GameAdapter(
        key="fh6",
        bridge_key="fh6",
        label="Forza Horizon 6",
        short_label="FH6",
        aliases=("forza horizon 6",),
        capabilities=GameCapabilities(True, True, True, True),
        stores=(MICROSOFT_STORE, STEAM),
        ownership=FAIL_CLOSED_OWNERSHIP,
        save_discovery=SaveDiscoveryStrategy(
            key="fh6_local_saves",
            targeted_kind="xbox_layer_groups",
            walk_kind="layer_group_cgroup",
            include_xbox_game_save=True,
            package_globs=(
                "*Forza*/SystemAppData/wgs",
                "*Forza*/SystemAppData/Helium",
                "*Microsoft*Forza*/SystemAppData/wgs",
                "*Microsoft*Forza*/SystemAppData/Helium",
            ),
        ),
        locator=LocatorStrategy("fh6_shared_rtti", "cloudflare_then_local", True, False),
        shape_schema=ShapeSchemaCompatibility("fh6", "kfps_forza_json_v1"),
        memory_profile=_profile(
            "fh6",
            "Forza Horizon 6",
            ("ForzaHorizon6.exe", "ForzaHorizon6-Win64-Shipping.exe"),
            import_template_shape_word=0x0066,
            import_template_min_ratio=0.90,
        ),
        offline_import_handler="_create_fh6_layer_group_install_work",
        scan_notice="FH6 save-library scan reads supported local LayerGroup files and leaves game saves unchanged.",
        offline_import_summary="Creating a new FH6 vinyl group folder from the selected JSON.",
        offline_import_help="Write the selected JSON into the FH6 local save library without opening the game.",
    ),
    "fh5": GameAdapter(
        key="fh5",
        bridge_key="fh5",
        label="Forza Horizon 5",
        short_label="FH5",
        aliases=("forza horizon 5",),
        capabilities=GameCapabilities(True, True, False, True),
        stores=(MICROSOFT_STORE, STEAM),
        ownership=FAIL_CLOSED_OWNERSHIP,
        save_discovery=SaveDiscoveryStrategy(
            key="fh5_local_saves",
            targeted_kind="xbox_layer_groups",
            walk_kind="cgroup",
            include_xbox_game_save=True,
            package_tokens=("624f8b84b80", "forzahorizon5"),
            package_markers=("wgs", "Helium"),
            steam_app_id="1551360",
            unbounded_matching_walk=True,
        ),
        locator=LocatorStrategy("fh5_fixed_rtti", "packaged_fixed_descriptors", True, False),
        shape_schema=ShapeSchemaCompatibility(
            "fh5", "kfps_forza_json_v1", accepted_source_kinds=("cgroup",)
        ),
        memory_profile=_profile(
            "fh5",
            "Forza Horizon 5",
            ("ForzaHorizon5.exe",),
            fixed_rtti_descriptor_names=(b"21530671058802", b"12610023981480"),
        ),
        offline_import_handler="",
        scan_notice=(
            "FH5's first save-library scan can take time with many vinyls because each group is decoded and its "
            "preview is prepared. Later scans reuse cached previews."
        ),
        offline_import_summary="FH5 offline import is unavailable. Use online import with FH5 running.",
        offline_import_help="FH5 local save-file importing is not available. Use online import with FH5 running.",
    ),
    "fh4": GameAdapter(
        key="fh4",
        bridge_key="fh4",
        label="Forza Horizon 4",
        short_label="FH4",
        aliases=("forza horizon 4",),
        capabilities=GameCapabilities(True, True, True, True),
        stores=(MICROSOFT_STORE, STEAM),
        ownership=FAIL_CLOSED_OWNERSHIP,
        save_discovery=SaveDiscoveryStrategy(
            key="fh4_local_saves",
            targeted_kind="fh4_wgs_layer_groups",
            walk_kind="cgroup",
            package_tokens=("sunrisebasegame", "forzahorizon4"),
            package_markers=("wgs", "Helium"),
            steam_app_id="1293830",
        ),
        locator=LocatorStrategy("fh4_static_rtti", "packaged_final_build", True, False),
        shape_schema=ShapeSchemaCompatibility("fh4", "kfps_forza_json_v1"),
        memory_profile=_profile(
            "fh4",
            "Forza Horizon 4",
            ("ForzaHorizon4.exe",),
            static_module_size=0x098DEE00,
            static_rtti_descriptor_offset=0x07C820C0,
            static_rtti_vtable_offsets=(0x072A31D8,),
            static_build="1.478.564.2 Microsoft Store/Xbox",
            import_template_shape_word=0x0066,
            import_template_min_ratio=0.90,
        ),
        offline_import_handler="_create_fh4_layer_group_install_work",
        scan_notice=(
            "FH4 offline scan reads user-created vinyl groups from supported local saves. It does not edit the save "
            "or require FH4 to be running."
        ),
        offline_import_summary="Creating a new FH4 vinyl group in the local Xbox WGS save container.",
        offline_import_help=(
            "With FH4 fully closed, create a new vinyl in the Microsoft Store/Xbox WGS save after backing up the "
            "complete local slot."
        ),
    ),
    "fm8": GameAdapter(
        key="fm8",
        bridge_key="fm",
        label="Forza Motorsport",
        short_label="FM8",
        aliases=("fm", "forza motorsport", "forza motorsport 8", "motorsport"),
        capabilities=GameCapabilities(True, True, True, True),
        stores=(MICROSOFT_STORE, STEAM),
        ownership=OwnershipRules(
            live_export_policy="verified_complete_group",
            live_import_policy="verified_owned_template",
            offline_export_policy="fm8_header_and_payload_fail_closed",
            offline_import_policy="new_local_record_with_reopen_verification",
            offline_source_preflight="fm8_layer_group_files",
        ),
        save_discovery=SaveDiscoveryStrategy(
            key="fm8_local_saves",
            targeted_kind="fm8_layer_groups",
            walk_kind="fm8_data",
            include_xbox_game_save=True,
            local_ugc_relative=("Microsoft.ForzaMotorsport", "UGC"),
            package_globs=(
                "*ForzaMotorsport*/LocalCache/Local/UGC",
                "*ForzaMotorsport*/LocalState/UGC",
            ),
            steam_app_id="2440510",
            ignored_design_kind="fm8_liveries",
        ),
        locator=LocatorStrategy("fm8_owned_live_root", "dedicated_live_root", False, True),
        shape_schema=ShapeSchemaCompatibility(
            "fm8", "kfps_forza_json_v1", minimum_decoded_layers=1
        ),
        memory_profile=_profile(
            "fm",
            "Forza Motorsport",
            (
                "ForzaMotorsport.exe",
                "forza_steamworks_release_final.exe",
                "forza_gaming.desktop.x64_release_final.exe",
            ),
        ),
        offline_import_handler="_create_fm8_layer_group_install_work",
        scan_notice=(
            "FM8 offline scan uses its separate local LayerGroups/data path. It reads saved files only and does not "
            "touch the live editor or Horizon save formats."
        ),
        offline_import_summary="Creating a separate FM8 LayerGroups/data folder from the selected JSON.",
        offline_import_help="Write the selected JSON into a new FM8 local LayerGroups entry without opening the game.",
    ),
}


def get_adapter(value: str | None = None) -> GameAdapter:
    text = str(value or "fh6").strip().casefold()
    for adapter in ADAPTERS.values():
        if adapter.matches_alias(text):
            return adapter
    supported = ", ".join(adapter.short_label for adapter in ADAPTERS.values())
    raise ValueError(f"Unsupported game '{value}'. Supported games: {supported}")


def get_adapter_or_default(value: str | None = None, default: str = "fh6") -> GameAdapter:
    try:
        return get_adapter(value)
    except ValueError:
        return ADAPTERS[default]


def iter_adapters() -> Iterable[GameAdapter]:
    yield from ADAPTERS.values()


def legacy_profiles() -> Dict[str, GameProfile]:
    return {adapter.bridge_key: adapter.memory_profile for adapter in ADAPTERS.values()}
