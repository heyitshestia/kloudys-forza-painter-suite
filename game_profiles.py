from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class GameProfile:
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


KNOWN_LIVERY_SIGNATURE = b'\x12\x47\x9B\x13\x29\xD9\xA2\xB1'

COMMON_SCAN_REGIONS = (
    (0x06000000, 0x02000000),
    (0x08000000, 0x02000000),
    (0x0A000000, 0x02000000),
)

PROFILES: Dict[str, GameProfile] = {
    "fh6": GameProfile(
        key="fh6",
        label="Forza Horizon 6",
        process_names=("ForzaHorizon6.exe", "ForzaHorizon6-Win64-Shipping.exe"),
        # FH6 profile starts with the FH5-era vinyl editor signature as a best-effort
        # compatibility probe. Replace or extend this list after validating against a
        # live FH6 build if the scanner reports no match.
        signature_patterns=(KNOWN_LIVERY_SIGNATURE,),
        scan_regions=COMMON_SCAN_REGIONS,
    ),
    "fh5": GameProfile(
        key="fh5",
        label="Forza Horizon 5",
        process_names=("ForzaHorizon5.exe",),
        signature_patterns=(KNOWN_LIVERY_SIGNATURE,),
        scan_regions=COMMON_SCAN_REGIONS,
        # Final Steam and Microsoft Store/Xbox RTTI descriptor names. FH5 is
        # retired, so these are packaged with KFPS instead of fetched remotely.
        fixed_rtti_descriptor_names=(b"21530671058802", b"12610023981480"),
    ),
    "fh4": GameProfile(
        key="fh4",
        label="Forza Horizon 4",
        process_names=("ForzaHorizon4.exe",),
        signature_patterns=(KNOWN_LIVERY_SIGNATURE,),
        scan_regions=COMMON_SCAN_REGIONS,
        # Final Microsoft Store/Xbox build 1.478.564.2. FH4 is no longer
        # updated, but every address is still verified against live RTTI and
        # vector metadata before KFPS accepts a group.
        static_module_size=0x098DEE00,
        static_rtti_descriptor_offset=0x07C820C0,
        static_rtti_vtable_offsets=(0x072A31D8,),
        static_build="1.478.564.2 Microsoft Store/Xbox",
        import_template_shape_word=0x0066,
        import_template_min_ratio=0.90,
    ),
    "fm": GameProfile(
        key="fm",
        label="Forza Motorsport",
        process_names=(
            "ForzaMotorsport.exe",
            "forza_steamworks_release_final.exe",
            "forza_gaming.desktop.x64_release_final.exe",
        ),
        signature_patterns=(KNOWN_LIVERY_SIGNATURE,),
        scan_regions=COMMON_SCAN_REGIONS,
    ),
}


def get_profile(key: str) -> GameProfile:
    normalized = key.lower()
    if normalized not in PROFILES:
        supported = ", ".join(PROFILES)
        raise ValueError(f"Unsupported game '{key}'. Supported profiles: {supported}")
    return PROFILES[normalized]


def iter_profiles(preferred_key: str = None) -> Iterable[GameProfile]:
    if preferred_key:
        yield get_profile(preferred_key)
        return
    yield from PROFILES.values()
