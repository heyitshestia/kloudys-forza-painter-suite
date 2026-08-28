from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from game_adapters.contracts import GameAdapter

from .contracts import LocatorRequest, LocatorSelection, parse_address


@dataclass(frozen=True)
class ValidationResult:
    selection: LocatorSelection | None
    reasons: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.selection is not None and not self.reasons


def _optional_address(value: Any) -> int | None:
    if value in (None, "", 0, "0", "0x0"):
        return None
    return parse_address(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _shape_word_count(payload: Mapping[str, Any], word: int) -> int:
    counts = payload.get("shape_word_counts") or {}
    if not isinstance(counts, Mapping):
        return 0
    return int(counts.get(str(word)) or counts.get(word) or 0)


def validate_fast_payload(
    payload: Mapping[str, Any],
    request: LocatorRequest,
    adapter: GameAdapter,
) -> ValidationResult:
    reasons: list[str] = []
    if str(payload.get("game") or request.game).lower() not in {request.game, adapter.key, adapter.bridge_key}:
        reasons.append("locator result belongs to a different game")
    if _int_or_none(payload.get("layer_count")) != request.layer_count:
        reasons.append("locator layer count does not match the request")
    if payload.get("refused") is True:
        reasons.append(str(payload.get("refusal_reason") or "live vinyl was refused by safety policy"))
    if payload.get("no_match") is True:
        reasons.append(str(payload.get("failure_reason") or "no live vinyl group matched"))
    if reasons:
        return ValidationResult(None, tuple(reasons))

    try:
        group = parse_address(payload.get("group_address"))
        table = parse_address(payload.get("table_address"))
    except (TypeError, ValueError) as exc:
        return ValidationResult(None, (f"locator did not return a valid group/table pair: {exc}",))

    validated = _int_or_none(payload.get("validated_entries"))
    if validated != request.layer_count:
        reasons.append(f"exact layer validation was {validated}/{request.layer_count}")

    import_group = _optional_address(payload.get("import_group_address"))
    import_table = _optional_address(payload.get("import_table_address"))
    import_count = _int_or_none(payload.get("import_vector_count"))
    import_verified = payload.get("import_target_verified") is True
    if request.purpose == "import":
        if adapter.locator.require_single_import_table and (
            not import_verified or import_count != request.layer_count or not import_group or not import_table
        ):
            reasons.append("no single exact writable import table was verified")
        required_word = int(adapter.memory_profile.import_template_shape_word)
        minimum_ratio = float(adapter.memory_profile.import_template_min_ratio)
        if required_word >= 0 and minimum_ratio > 0:
            matching = _shape_word_count(payload, required_word)
            required = int(request.layer_count * minimum_ratio)
            if matching < required:
                reasons.append(
                    f"template shape check {matching}/{request.layer_count}; at least {required} are required"
                )

    if adapter.locator.require_live_export_ownership and payload.get("export_access_verified") is not True:
        reasons.append("the complete live vinyl hierarchy was not ownership-verified")
    if reasons:
        return ValidationResult(None, tuple(reasons))

    return ValidationResult(
        LocatorSelection(
            group_address=group,
            table_address=table,
            count_address=_optional_address(payload.get("count_address")),
            table_pointer_field=_optional_address(payload.get("table_pointer_field")),
            locator=str(payload.get("locator") or "profile"),
            validated_entries=validated or 0,
            vector_count=_int_or_none(payload.get("vector_count")),
            capacity_count=_int_or_none(payload.get("capacity_count")),
            import_group_address=import_group,
            import_count_address=_optional_address(payload.get("import_count_address")),
            import_table_pointer_field=_optional_address(payload.get("import_table_pointer_field")),
            import_table_address=import_table,
            import_vector_count=import_count,
            import_capacity_count=_int_or_none(payload.get("import_capacity_count")),
            import_target_verified=import_verified,
            export_access_verified=payload.get("export_access_verified") is True,
            flattened_from_groups=payload.get("flattened_from_groups") is True,
            details={
                "score": payload.get("score"),
                "samples": payload.get("samples") or [],
                "shape_word_counts": payload.get("shape_word_counts") or {},
                "group_graph": payload.get("group_graph"),
                "flattened_group_count": _int_or_none(payload.get("flattened_group_count")),
                "flattened_max_depth": _int_or_none(payload.get("flattened_max_depth")),
                "vtable": payload.get("vtable"),
                "rtti_source": payload.get("rtti_source"),
                "rtti_profile_id": payload.get("rtti_profile_id"),
                "rtti_update_code": payload.get("rtti_update_code"),
                "rtti_descriptor_offset": payload.get("rtti_descriptor_offset"),
            },
        )
    )


def fallback_candidate_sort_key(candidate: Mapping[str, Any], layer_count: int) -> tuple[int, ...]:
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, layer_count - valid_ptrs))
    duplicate_ptrs = int(candidate.get("duplicate_ptr_count") or 0)
    sample_ok = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
    exact_table = int(valid_ptrs == layer_count and invalid_ptrs == 0)
    exact_decoded = int(exact_table and sample_ok == layer_count and duplicate_ptrs == 0)
    vector_bonus = int(candidate.get("vector_ok") is True)
    source_bonus = int(candidate.get("source") == "vector_header")
    try:
        group = parse_address(candidate.get("group"))
    except (TypeError, ValueError):
        group = 0x7FFFFFFFFFFF
    try:
        table = parse_address(candidate.get("table"))
    except (TypeError, ValueError):
        table = 0x7FFFFFFFFFFF
    return (
        int(candidate.get("strict_valid") is True),
        exact_decoded,
        exact_table,
        vector_bonus,
        valid_ptrs,
        sample_ok,
        -invalid_ptrs,
        -duplicate_ptrs,
        source_bonus,
        int(candidate.get("score") or 0),
        -group,
        -table,
    )


def _fallback_rejection(
    candidate: Mapping[str, Any], request: LocatorRequest, adapter: GameAdapter
) -> str:
    valid_ptrs = int(candidate.get("valid_ptrs") or 0)
    invalid_ptrs = int(candidate.get("invalid_ptrs") or max(0, request.layer_count - valid_ptrs))
    sample_ok = int(candidate.get("layer_ok_count") or candidate.get("sample_ok_count") or 0)
    duplicate_ptrs = int(candidate.get("duplicate_ptr_count") or 0)
    if candidate.get("vector_ok") is not True:
        return "vector metadata invalid"
    if _int_or_none(candidate.get("vector_count")) != request.layer_count:
        return f"vector_count={candidate.get('vector_count')}"
    capacity = _int_or_none(candidate.get("capacity_count"))
    if capacity is None or capacity < request.layer_count:
        return f"capacity_count={candidate.get('capacity_count')}"
    if valid_ptrs != request.layer_count or invalid_ptrs:
        return f"valid_ptrs={valid_ptrs}, invalid_ptrs={invalid_ptrs}"
    if duplicate_ptrs:
        return f"duplicate_ptrs={duplicate_ptrs}"
    if sample_ok != request.layer_count:
        return f"decoded_layers={sample_ok}"
    if request.purpose == "import":
        word = int(adapter.memory_profile.import_template_shape_word)
        ratio = float(adapter.memory_profile.import_template_min_ratio)
        if word >= 0 and ratio > 0:
            counts = candidate.get("shape_word_counts_all") or candidate.get("shape_id_counts_all") or {}
            matching = int(counts.get(str(word)) or counts.get(word) or counts.get(str(word & 0xFF)) or 0)
            required = int(request.layer_count * ratio)
            if matching < required:
                return f"template_shape_check={matching}/{request.layer_count}"
    return ""


def select_fallback_candidate(
    candidates: Iterable[Mapping[str, Any]],
    request: LocatorRequest,
    adapter: GameAdapter,
) -> ValidationResult:
    ordered = sorted(
        (dict(candidate) for candidate in candidates if isinstance(candidate, Mapping)),
        key=lambda item: fallback_candidate_sort_key(item, request.layer_count),
        reverse=True,
    )
    reasons: list[str] = []
    for index, candidate in enumerate(ordered, start=1):
        rejection = _fallback_rejection(candidate, request, adapter)
        try:
            group = parse_address(candidate.get("group"))
            table = parse_address(candidate.get("table"))
        except (TypeError, ValueError):
            rejection = rejection or "missing group/table"
            group = table = 0
        if rejection:
            reasons.append(f"#{index}: {rejection}")
            continue
        count_address = group + int(adapter.memory_profile.livery_count_offset)
        table_field = group + int(adapter.memory_profile.layer_table_offset)
        selection = LocatorSelection(
            group_address=group,
            table_address=table,
            count_address=count_address,
            table_pointer_field=table_field,
            locator=f"research_{candidate.get('source') or 'count_table'}",
            validated_entries=request.layer_count,
            vector_count=request.layer_count,
            capacity_count=int(candidate.get("capacity_count") or request.layer_count),
            import_group_address=group,
            import_count_address=count_address,
            import_table_pointer_field=table_field,
            import_table_address=table,
            import_vector_count=request.layer_count,
            import_capacity_count=int(candidate.get("capacity_count") or request.layer_count),
            import_target_verified=True,
            details={"candidate": candidate, "rank": index},
        )
        return ValidationResult(selection)
    return ValidationResult(None, tuple(reasons or ("no research candidates",)))
