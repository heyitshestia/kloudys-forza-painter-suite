from __future__ import annotations

import os
import struct
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from fh6_rtti_registry import (
    empty_registry,
    load_registry_file,
    normalize_profile,
    registry_with_profile,
    write_registry_file,
)
from native import get_base_address, read_process_memory

from .cache import LocatorCache, normalize_allocator_windows


LOCAL_RECOVERY_REGISTRY = "local-recovery-RTTI.dat"
FORCE_LOCAL_RECOVERY_ENV = "KFPS_FORCE_LOCAL_RTTI_RECOVERY"
RECOVERY_FORMAT = "kfps_fh6_local_profile_recovery_v1"
RECOVERY_VERSION = "1.0.0"
MAX_TYPE_NAME_BYTES = 128
RECOVERY_MAX_SECONDS = 60


def force_local_recovery_requested() -> bool:
    return os.environ.get(FORCE_LOCAL_RECOVERY_ENV, "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def local_registry_path(root: str | Path) -> Path:
    return Path(root) / "runtime" / "fh6-rtti" / LOCAL_RECOVERY_REGISTRY


def load_local_profiles(root: str | Path) -> tuple[list[dict[str, Any]], str]:
    path = local_registry_path(root)
    if not path.is_file():
        return [], ""
    try:
        registry = load_registry_file(path)
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    profiles = []
    for item in registry["profiles"]:
        profile = dict(item)
        profile["_registry_source"] = "local_recovery"
        profiles.append(profile)
    return profiles, ""


def merge_local_profiles(root: str | Path, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    local, _error = load_local_profiles(root)
    merged = []
    seen = set()
    for item in [*local, *profiles]:
        profile_id = str(item.get("profile_id") or "").strip()
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        merged.append(item)
    return merged


def persist_local_profile(root: str | Path, raw_profile: Mapping[str, Any]) -> dict[str, Any]:
    path = local_registry_path(root)
    try:
        registry = load_registry_file(path) if path.is_file() else empty_registry()
    except Exception:
        registry = empty_registry()
    profile = normalize_profile(dict(raw_profile))
    write_registry_file(path, registry_with_profile(registry, profile))
    return profile


def _read_u32(pid: int, address: int) -> int:
    return struct.unpack("<I", read_process_memory(pid, address, 4))[0]


def _read_u64(pid: int, address: int) -> int:
    return struct.unpack("<Q", read_process_memory(pid, address, 8))[0]


def _read_ascii(pid: int, address: int, maximum: int = MAX_TYPE_NAME_BYTES) -> str:
    raw = read_process_memory(pid, address, maximum)
    raw = raw.split(b"\0", 1)[0].rstrip(b" ")
    if not raw or any(byte < 0x21 or byte > 0x7E for byte in raw):
        return ""
    try:
        return raw.decode("ascii", "strict")
    except UnicodeDecodeError:
        return ""


def _inside(base: int, size: int, address: int, length: int = 1) -> bool:
    return base <= address and length > 0 and address + length <= base + size


def _same_process(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return (
        int(before.get("pid") or 0) == int(after.get("pid") or 0)
        and str(before.get("name") or "").casefold() == str(after.get("name") or "").casefold()
        and abs(float(before.get("started") or 0.0) - float(after.get("started") or 0.0)) < 0.001
    )


def _derive_profile_from_group(
    _probe: Any,
    pid: int,
    group_address: int,
    vtable: int,
    module_base: int,
    module_size: int,
    layer_count: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    evidence: dict[str, Any] = {"group_address": group_address, "vtable": vtable}
    if not _inside(module_base, module_size, vtable, 8) or not _inside(module_base, module_size, vtable - 8, 8):
        return None, {**evidence, "reason": "vtable_outside_main_module"}
    try:
        locator = _read_u64(pid, vtable - 8)
        raw_locator = read_process_memory(pid, locator, 0x18)
    except Exception:
        return None, {**evidence, "reason": "complete_object_locator_unreadable"}
    if not _inside(module_base, module_size, locator, 0x18) or len(raw_locator) != 0x18:
        return None, {**evidence, "reason": "complete_object_locator_outside_main_module"}

    signature, _object_offset, _constructor_offset, descriptor_rva, hierarchy_rva, self_rva = struct.unpack(
        "<6I", raw_locator
    )
    if signature != 1 or locator - self_rva != module_base:
        return None, {**evidence, "reason": "complete_object_locator_identity_invalid"}
    descriptor = module_base + descriptor_rva
    hierarchy = module_base + hierarchy_rva
    if not _inside(module_base, module_size, descriptor, 0x20) or not _inside(
        module_base, module_size, hierarchy, 0x10
    ):
        return None, {**evidence, "reason": "rtti_descriptor_outside_main_module"}

    update_code = _read_ascii(pid, descriptor + 0x10)
    if not update_code:
        return None, {**evidence, "reason": "rtti_type_name_invalid"}
    try:
        hierarchy_signature, _hierarchy_attributes, base_class_count, base_array_rva = struct.unpack(
            "<4I", read_process_memory(pid, hierarchy, 0x10)
        )
    except Exception:
        return None, {**evidence, "reason": "class_hierarchy_unreadable"}
    if hierarchy_signature != 0 or not 1 <= base_class_count <= 64:
        return None, {**evidence, "reason": "class_hierarchy_invalid"}
    base_array = module_base + base_array_rva
    if not _inside(module_base, module_size, base_array, base_class_count * 4):
        return None, {**evidence, "reason": "base_class_array_outside_main_module"}

    try:
        base_rvas = struct.unpack(
            f"<{base_class_count}I",
            read_process_memory(pid, base_array, base_class_count * 4),
        )
    except Exception:
        return None, {**evidence, "reason": "base_class_array_unreadable"}
    for base_rva in base_rvas:
        base_descriptor = module_base + base_rva
        if not _inside(module_base, module_size, base_descriptor, 0x1C):
            return None, {**evidence, "reason": "base_class_descriptor_outside_main_module"}
        try:
            base_type_rva = _read_u32(pid, base_descriptor)
        except Exception:
            return None, {**evidence, "reason": "base_class_descriptor_unreadable"}
        if not _inside(module_base, module_size, module_base + base_type_rva, 0x20):
            return None, {**evidence, "reason": "base_type_descriptor_outside_main_module"}

    raw_profile = {
        "game": "fh6",
        "module_size": module_size,
        "descriptor_offset": descriptor_rva,
        "vtable_offsets": [vtable - module_base],
        "update_code": update_code,
        "base_class_count": base_class_count,
        "game_build": "",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "calibrator_version": f"organic-{RECOVERY_VERSION}",
        "evidence": {
            "workflow": "organic_live_transfer_recovery",
            "confidence": "high",
            "scan_count": 1,
            "distinct_counts": [layer_count],
        },
    }
    try:
        normalized = normalize_profile(raw_profile)
    except Exception as exc:
        return None, {**evidence, "reason": f"profile_normalization_failed:{type(exc).__name__}"}
    normalized["_registry_source"] = "local_recovery_candidate"
    return normalized, {
        **evidence,
        "reason": "derived",
        "descriptor_offset": descriptor_rva,
        "base_class_count": base_class_count,
        "profile_id": normalized["profile_id"],
    }


def _evaluate_group_candidate(
    probe: Any,
    pid: int,
    memory_profile: Any,
    layer_count: int,
    group_address: int,
    module_base: int,
    module_size: int,
    writable_contains: Callable[[int, int], bool],
) -> tuple[dict[str, Any] | None, str]:
    try:
        vtable = _read_u64(pid, group_address)
    except Exception:
        return None, "group_vtable_unreadable"
    if not _inside(module_base, module_size, vtable, 8):
        return None, "group_vtable_outside_main_module"
    try:
        group_info = probe.read_calibrated_group_vector(
            pid,
            memory_profile,
            group_address,
            {vtable},
            max_vector_count=max(3000, layer_count),
            writable_contains=writable_contains,
        )
    except Exception:
        return None, "group_vector_unreadable"
    if not group_info or int(group_info.get("parent_group") or 0):
        return None, "group_vector_invalid"
    if int(group_info.get("current_u16") or -1) != int(layer_count):
        return None, "group_count_changed"
    profile, derivation = _derive_profile_from_group(
        probe,
        pid,
        group_address,
        vtable,
        module_base,
        module_size,
        layer_count,
    )
    if profile is None:
        return None, str(derivation.get("reason") or "rtti_derivation_failed")
    try:
        flat = probe.flatten_calibrated_group(
            pid,
            memory_profile,
            group_info,
            {vtable},
            layer_count,
            writable_contains=writable_contains,
        )
    except Exception:
        return None, "group_traversal_unreadable"
    if int(flat.get("shape_count") or 0) != int(layer_count) or int(flat.get("invalid_count") or 0):
        return None, "group_traversal_invalid"
    return {
        "group_address": group_address,
        "vtable": vtable,
        "shape_count": flat["shape_count"],
        "group_count": flat["group_count"],
        "max_depth": flat["max_depth"],
        "profile": profile,
        "derivation": derivation,
    }, ""


def _discover_cold_group(
    probe: Any,
    pid: int,
    memory_profile: Any,
    layer_count: int,
    module_base: int,
    module_size: int,
    all_regions: list[tuple[int, int, int, int]],
    writable_contains: Callable[[int, int], bool],
    seen_groups: set[int],
    rejection_counts: dict[str, int],
    deadline: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    table_offset = int(memory_profile.layer_table_offset)
    count_offset = int(memory_profile.livery_count_offset)
    required_header = max(table_offset + 24, count_offset + 2, 0x68)
    count_pattern = struct.pack("<H", int(layer_count))
    scanned_bytes = 0
    count_hits = 0
    pointer_hits = 0
    timed_out = False
    scheduled = probe.iter_balanced_region_chunks(
        pid,
        all_regions,
        overlap=required_header - 1,
        preferred_size_range=(probe.FH6_GROUP_ARENA_MIN_SIZE, probe.FH6_GROUP_ARENA_MAX_SIZE),
    )
    for _region, chunk_base, memory, unique_size in scheduled:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        scanned_bytes += int(unique_size)
        search_from = 0
        while True:
            count_position = memory.find(count_pattern, search_from)
            if count_position < 0:
                break
            search_from = count_position + 1
            count_hits += 1
            if count_hits % 2048 == 0 and time.monotonic() >= deadline:
                timed_out = True
                break
            group_offset = count_position - count_offset
            if group_offset < 0 or group_offset + required_header > len(memory):
                continue
            group_address = int(chunk_base) + group_offset
            if group_address % 8 or group_address in seen_groups:
                continue
            vtable = struct.unpack_from("<Q", memory, group_offset)[0]
            if not _inside(module_base, module_size, vtable, 8):
                continue
            pointer_hits += 1
            parent_group = struct.unpack_from("<Q", memory, group_offset + 0x60)[0]
            table_address, table_end, table_capacity = struct.unpack_from(
                "<3Q", memory, group_offset + table_offset
            )
            if parent_group or table_end <= table_address or table_capacity < table_end:
                continue
            if (table_end - table_address) % 8 or (table_capacity - table_address) % 8:
                continue
            vector_count = (table_end - table_address) // 8
            if not 1 <= vector_count <= max(3000, layer_count):
                continue
            if not writable_contains(table_address, vector_count * 8):
                continue
            seen_groups.add(group_address)
            candidate, reason = _evaluate_group_candidate(
                probe,
                pid,
                memory_profile,
                layer_count,
                group_address,
                module_base,
                module_size,
                writable_contains,
            )
            if candidate is not None:
                return candidate, {
                    "status": "match",
                    "scanned_bytes": scanned_bytes,
                    "scanned_mb": scanned_bytes // (1024 * 1024),
                    "count_hits": count_hits,
                    "pointer_hits": pointer_hits,
                }
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
        if timed_out:
            break
    return None, {
        "status": "timeout" if timed_out else "exhausted",
        "scanned_bytes": scanned_bytes,
        "scanned_mb": scanned_bytes // (1024 * 1024),
        "count_hits": count_hits,
        "pointer_hits": pointer_hits,
    }


def recover_local_profile(
    root: str | Path,
    pid: int,
    memory_profile: Any,
    layer_count: int,
    *,
    seed_payload: Mapping[str, Any] | None = None,
    process_identity: Callable[[int], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive one local FH6 profile from one exact open group tree."""
    import fh6_probe as probe

    started = time.monotonic()
    deadline = started + RECOVERY_MAX_SECONDS
    result: dict[str, Any] = {
        "format": RECOVERY_FORMAT,
        "status": "no_match",
        "reason": "No exact open FH6 group tree was found.",
        "publication": "disabled",
        "profile": None,
    }
    before = dict(process_identity(pid)) if process_identity else None
    module_base = int(get_base_address(pid))
    module_size = int(probe.read_pe_image_size(pid, module_base) or 0)
    if module_size <= 0:
        return {**result, "status": "error", "reason": "The FH6 main module size could not be read."}

    all_regions = list(probe.iter_regions(pid, type_filter=probe.MEM_PRIVATE, writable_only=True))
    writable_contains = probe.build_region_contains(all_regions)
    cache = LocatorCache(
        Path(root) / "runtime" / "live-memory" / "locator-cache.json",
        legacy_path=Path(root) / "runtime" / "fh6-rtti" / "live-locator-cache.json",
    )
    windows = [*probe.FH6_DEFAULT_ALLOCATOR_WINDOWS, *cache.all_allocator_windows("fh6")]
    seed_group = int((seed_payload or {}).get("group_address") or 0)
    if seed_group:
        windows.append(probe.allocator_window_for_address(seed_group))
    windows = normalize_allocator_windows(windows)
    scan_regions = probe.regions_in_allocator_windows(all_regions, windows)

    group_addresses = []
    if seed_group:
        group_addresses.append(seed_group)
    failed_bytes = 0
    scanned_bytes = 0
    pointer_hits = 0
    seen_groups = set(group_addresses)
    table_offset = int(memory_profile.layer_table_offset)
    count_offset = int(memory_profile.livery_count_offset)
    required_header = max(table_offset + 24, count_offset + 2, 0x68)
    timed_out = False
    for base, size, protect, region_type in scan_regions:
        if time.monotonic() >= deadline:
            timed_out = True
            break
        readable, failed, _changed, _split_reads = probe.read_region_resilient(
            pid,
            base,
            size,
            protect,
            region_type,
            max_size=probe.FH6_REGION_SCAN_CHUNK_SIZE,
            minimum_size=probe.FH6_RECOVERY_PAGE_SIZE,
        )
        failed_bytes += sum(int(item[1]) for item in failed)
        previous_end = None
        previous_tail = b""
        for readable_base, memory in readable:
            scanned_bytes += len(memory)
            if previous_end == int(readable_base) and previous_tail:
                scan_base = int(readable_base) - len(previous_tail)
                scan_memory = previous_tail + memory
            else:
                scan_base = int(readable_base)
                scan_memory = memory
            start_offset = (-scan_base) % 8
            next_time_check = start_offset
            for offset in range(
                start_offset,
                max(start_offset, len(scan_memory) - required_header + 1),
                8,
            ):
                if offset >= next_time_check:
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    next_time_check = offset + 1024 * 1024
                vtable = struct.unpack_from("<Q", scan_memory, offset)[0]
                if not _inside(module_base, module_size, vtable, 8):
                    continue
                pointer_hits += 1
                current_count = struct.unpack_from("<H", scan_memory, offset + count_offset)[0]
                parent_group = struct.unpack_from("<Q", scan_memory, offset + 0x60)[0]
                table_address, table_end, table_capacity = struct.unpack_from(
                    "<3Q", scan_memory, offset + table_offset
                )
                if current_count != layer_count or parent_group:
                    continue
                if table_end <= table_address or table_capacity < table_end:
                    continue
                if (table_end - table_address) % 8 or (table_capacity - table_address) % 8:
                    continue
                vector_count = (table_end - table_address) // 8
                if not 1 <= vector_count <= max(3000, layer_count):
                    continue
                if not writable_contains(table_address, vector_count * 8):
                    continue
                group_address = scan_base + offset
                if group_address not in seen_groups:
                    seen_groups.add(group_address)
                    group_addresses.append(group_address)
            previous_end = int(readable_base) + len(memory)
            previous_tail = memory[-(required_header - 1) :]
            if timed_out:
                break
        if timed_out:
            break
    if timed_out:
        return {
            **result,
            "status": "timeout",
            "reason": "Local FH6 compatibility recovery reached its 60-second safety limit.",
            "pointer_hits": pointer_hits,
            "scanned_mb": scanned_bytes // (1024 * 1024),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    if failed_bytes:
        return {
            **result,
            "status": "incomplete",
            "reason": "KFPS could not read every eligible FH6 livery allocator page.",
            "failed_bytes": failed_bytes,
            "scanned_mb": scanned_bytes // (1024 * 1024),
        }

    exact = []
    rejection_counts: dict[str, int] = {}
    for index, group_address in enumerate(group_addresses):
        if index % 256 == 0 and time.monotonic() >= deadline:
            return {
                **result,
                "status": "timeout",
                "reason": "Local FH6 compatibility recovery reached its 60-second safety limit.",
                "pointer_hits": pointer_hits,
                "scanned_mb": scanned_bytes // (1024 * 1024),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        candidate, reason = _evaluate_group_candidate(
            probe,
            pid,
            memory_profile,
            layer_count,
            group_address,
            module_base,
            module_size,
            writable_contains,
        )
        if candidate is None:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        exact.append(candidate)

    cold_stats = {
        "status": "not_needed",
        "scanned_bytes": 0,
        "scanned_mb": 0,
        "count_hits": 0,
        "pointer_hits": 0,
    }
    if not exact:
        cold_candidate, cold_stats = _discover_cold_group(
            probe,
            pid,
            memory_profile,
            layer_count,
            module_base,
            module_size,
            all_regions,
            writable_contains,
            seen_groups,
            rejection_counts,
            deadline,
        )
        pointer_hits += int(cold_stats.get("pointer_hits") or 0)
        scanned_bytes += int(cold_stats.get("scanned_bytes") or 0)
        if cold_candidate is not None:
            exact.append(cold_candidate)

    if process_identity:
        after = dict(process_identity(pid))
        if not _same_process(before or {}, after):
            return {
                **result,
                "status": "process_changed",
                "reason": "The FH6 process changed during local compatibility recovery.",
            }
    unique = {int(item["group_address"]): item for item in exact}
    if len(unique) != 1:
        if cold_stats.get("status") == "timeout":
            return {
                **result,
                "status": "timeout",
                "reason": "Local FH6 compatibility recovery reached its 60-second safety limit.",
                "candidate_count": len(unique),
                "pointer_hits": pointer_hits,
                "scanned_mb": scanned_bytes // (1024 * 1024),
                "cold_start": cold_stats,
                "rejection_counts": rejection_counts,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        reason = (
            "KFPS found multiple exact FH6 groups in the livery allocator; local recovery was not accepted."
            if len(unique) > 1
            else "Cold-start recovery did not find one exact open FH6 group."
        )
        return {
            **result,
            "reason": reason,
            "candidate_count": len(unique),
            "pointer_hits": pointer_hits,
            "scanned_mb": scanned_bytes // (1024 * 1024),
            "cold_start": cold_stats,
            "rejection_counts": rejection_counts,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    winner = next(iter(unique.values()))
    verified_window = probe.allocator_window_for_address(winner["group_address"])
    return {
        **result,
        "status": "derived",
        "reason": "A local FH6 compatibility profile was derived from one exact group tree.",
        "profile": winner["profile"],
        "candidate_count": 1,
        "pointer_hits": pointer_hits,
        "scanned_mb": scanned_bytes // (1024 * 1024),
        "group_count": winner["group_count"],
        "max_depth": winner["max_depth"],
        "source_group": winner["group_address"],
        "verified_allocator_window": list(verified_window),
        "cold_start": cold_stats,
        "derivation": winner["derivation"],
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
